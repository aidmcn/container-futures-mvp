#!/usr/bin/env python
import time
from threading import Event
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional # Added Optional

# Assuming matching.py and models.py are in the same directory or accessible in PYTHONPATH
from matching import submit_order, r, PLATFORM_TRADER_ID, get_trader_balance, lock_funds, release_funds, _book_key as matching_book_key # Renamed to avoid clash
from models import ContainerContract, Order, LegInfo, Match # Make sure Match is imported if used by submit_order directly

# --- Constants for the Scenario ---
CONTRACT_ID = "C1"
SHIPPER_A_ID = "ShipperA"
MM_TRADER_ID = "MarketMaker1"

CARRIERS = ["Maersk", "Evergreen", "COSCO", "MSC", "Hapag"]
OTHER_BIDDERS = ["CheapLtd", "FastPLC", "WealthyCorp"]

# Leg Identifiers (used as part of book IDs, e.g., L1_C1)
LEG_L1 = "L1"
LEG_L2 = "L2"
LEG_L3 = "L3"

# Estimated high costs for legs for T0 max_prepaid_cost calculation
LEG_HIGH_ESTIMATES = {LEG_L1: 9000, LEG_L2: 5000, LEG_L3: 3000}
# Target prices ShipperA (or current C1 owner) will bid for freight
LEG_TARGET_FREIGHT_BID_PRICES = {LEG_L1: 7800, LEG_L2: 3800, LEG_L3: 1800} # Slightly below lowest carrier ask
# Carrier ask prices for freight on each leg (5 carriers)
CARRIER_ASK_PRICES = {
    LEG_L1: [8000, 7500, 7000, 6500, 6000],
    LEG_L2: [4000, 3500, 3000, 2500, 2000],
    LEG_L3: [2000, 1500, 1000, 800, 600]
}
MM_FREIGHT_QUOTE_OFFSET = 100 # MM quotes +/- 100 around reference for freight
MM_CONTRACT_QUOTE_OFFSET = 50 # MM quotes +/- 50 for the main contract C1

# --- Helper Functions ---
def _pausable_sleep(duration_seconds: float, stop_event: Event, pause_event: Event, scenario_start_time_abs: float, clock_callback):
    print(f"[SEED_SLEEP] Requesting sleep for {duration_seconds:.2f}s. Stop: {stop_event.is_set()}, Pause: {pause_event.is_set()}")
    if duration_seconds <= 0:
        # Update clock immediately if duration is zero or negative, then return.
        # This ensures clock reflects the intended event time even if no actual sleep occurs.
        current_elapsed_scenario_time = time.time() - scenario_start_time_abs
        # However, for _pausable_sleep, the duration IS the delta, so clock should be advanced by that conceptually.
        # The clock_callback is usually called with total elapsed time from scenario_start_time_abs.
        # If duration_seconds is the time *until the next event*, then the clock should reflect that event time.
        # This needs careful handling. The clock_callback expects total elapsed time.
        # For now, if duration is <=0, just log and return, assuming clock is caught up by the caller.
        print(f"[SEED_SLEEP] Duration is {duration_seconds:.2f}s, returning immediately. Clock update handled by caller or next event.")
        return True # Still considered a successful 'sleep'

    slept_so_far = 0
    step = 0.1 
    while slept_so_far < duration_seconds:
        if stop_event.is_set(): 
            print("[SEED_SLEEP] Stop event during sleep.")
            return False 
        while pause_event.is_set():
            if stop_event.is_set(): 
                print("[SEED_SLEEP] Stop event during pause.")
                return False
            # print("[SEED_SLEEP] Paused...") # Can be too verbose
            time.sleep(step)
            # No clock update during pause to reflect simulation time freeze
        
        actual_step_duration = min(step, duration_seconds - slept_so_far)
        time.sleep(actual_step_duration)
        slept_so_far += actual_step_duration
        current_elapsed_scenario_time = time.time() - scenario_start_time_abs
        clock_callback(current_elapsed_scenario_time)
        
        # Check for negligible remaining time to avoid float precision issues in loop condition
        if (duration_seconds - slept_so_far) < 0.0001:
            break
    # Final clock update to ensure it reflects the full duration waited, relative to scenario start
    # This assumes clock_callback wants total elapsed time since scenario_start_time_abs
    final_elapsed_time = time.time() - scenario_start_time_abs 
    # The clock should ideally be set to the target sim time *after* the sleep completes.
    # The `current_sim_time_s` in the main `schedule` loop is the source of truth for event timing.
    # clock_callback(final_elapsed_time) # Already called in loop, this might over-report
    print(f"[SEED_SLEEP] Finished sleep. Total time elapsed in scenario: {final_elapsed_time:.2f}s")
    return True

def fund_trader(trader_id: str, amount: float, initial_funding: bool = False):
    key = f"escrow:{trader_id}"
    if initial_funding or not r.exists(key):
        r.hmset(key, {"balance": str(amount), "locked": "0"})
        print(f"[SEED] FUNDED (Initial): {trader_id} with {amount}")
    else:
        # For additive funding, ensure it correctly adds to existing balance.
        # Using hincrbyfloat is safer for concurrent updates if any.
        current_bal = float(r.hget(key, "balance") or "0")
        r.hset(key, "balance", str(current_bal + amount))
        print(f"[SEED] FUNDED (Added): {trader_id} with {amount}. New Balance: {current_bal + amount}")

def get_full_leg_id(base_leg_id: str, contract_id: str) -> str:
    return f"{base_leg_id}_{contract_id}" # e.g., L1_C1

def get_contract_book_id(contract_id: str) -> str:
    return f"contract:{contract_id}" # e.g., contract:C1

def _get_best_book_prices_seed(book_id: str): # Helper specific to seed logic
    bids_raw = r.zrange(f"bids:{book_id}", 0, 0, withscores=True, desc=True)
    asks_raw = r.zrange(f"asks:{book_id}", 0, 0, withscores=True)
    best_bid_price = abs(bids_raw[0][1]) if bids_raw else None
    best_ask_price = asks_raw[0][1] if asks_raw else None
    return best_bid_price, best_ask_price

def _place_mm_quotes_seed(book_id: str, mm_trader_id: str, default_ref_price: float, quote_offset: int, order_type: str, contract_id_for_leg_freight: Optional[str]=None):
    # Order type will be CONTRACT_OWNERSHIP or LEG_FREIGHT
    _, best_ask_price = _get_best_book_prices_seed(book_id)
    ref_price = best_ask_price if best_ask_price is not None else default_ref_price

    if ref_price > 0 and ref_price > quote_offset: # Ensure positive ref and bid > 0
        mm_bid_price = ref_price - quote_offset
        mm_ask_price = ref_price + quote_offset
        if mm_bid_price > 0:
            submit_order("bid", book_id, mm_bid_price, 1, mm_trader_id, order_type=order_type, container_contract_id=contract_id_for_leg_freight)
        submit_order("ask", book_id, mm_ask_price, 1, mm_trader_id, order_type=order_type, container_contract_id=contract_id_for_leg_freight)
        print(f"[SEED_MM {book_id}] Placed MM quotes: Bid {mm_bid_price}, Ask {mm_ask_price}")
    else:
        print(f"[SEED_MM {book_id}] Could not place MM quotes. Ref price: {ref_price}, Offset: {quote_offset}")

# --- T0: Booking Logic --- 
def action_t0_create_and_book_container_contract(
    contract_id: str, shipper_id: str, origin_port: str, final_dest_port: str, 
    legs_config: List[Dict[str, Any]], container_type_desc: str = "40ft_STD_USE"
) -> Optional[ContainerContract]:
    print(f"[SEED T0] Contract {contract_id} for {shipper_id}: {origin_port} to {final_dest_port}")
    max_total_journey_cost = sum(leg_cfg["high_estimate"] for leg_cfg in legs_config) + 2000 
    
    # Ensure shipper has enough balance for max_prepaid_cost, then lock it.
    current_shipper_balance = get_trader_balance(shipper_id).get("balance", 0.0)
    if current_shipper_balance < max_total_journey_cost:
        needed_top_up = max_total_journey_cost - current_shipper_balance
        fund_trader(shipper_id, needed_top_up) # Top up if needed (fund_trader adds to existing)
        print(f"[SEED T0] Topped up {shipper_id} balance by {needed_top_up} to cover max prepaid cost.")

    if not lock_funds(shipper_id, max_total_journey_cost):
        print(f"[SEED T0] CRITICAL FAIL: Could not lock max prepaid cost {max_total_journey_cost} for {shipper_id}")
        return None
    print(f"[SEED T0] Locked {max_total_journey_cost} from {shipper_id} for contract {contract_id}.")

    contract = ContainerContract(
        id=contract_id, contract_type=container_type_desc, origin_port=origin_port,
        final_destination_port=final_dest_port, initial_shipper_id=shipper_id,
        current_owner_id=shipper_id, status="BOOKED", max_prepaid_cost=max_total_journey_cost,
        final_eta_ts=None 
    )
    
    contract_dict_to_store = contract.model_dump(mode='json')
    redis_safe_contract_data = { 
        k: (str(v) if isinstance(v, bool) else ("" if v is None else str(v))) # Ensure ALL non-None are strings for hmset
        for k, v in contract_dict_to_store.items() 
    }
    # ---- DEBUG PRINT ----
    print(f"[SEED DEBUG] About to HMSET container_contract:{contract_id}. Data for Redis: {redis_safe_contract_data}")
    for k, v in redis_safe_contract_data.items():
        print(f"[SEED DEBUG]    Key: '{k}', Value: '{v}', Type: {type(v)}")
    # ---- END DEBUG PRINT ----
    r.hmset(f"container_contract:{contract_id}", redis_safe_contract_data)
    print(f"[SEED T0] Stored ContainerContract {contract_id} in Redis.") # Removed data from this log for brevity

    for leg_cfg in legs_config:
        full_leg_id = get_full_leg_id(leg_cfg["id"], contract_id)
        leg_meta = LegInfo(
            leg_id=leg_cfg["id"], contract_id=contract_id, origin=leg_cfg["origin"],
            destination=leg_cfg["destination"], status="PENDING_AUCTION"
        )
        leg_meta_dict_to_store = leg_meta.model_dump(mode='json')
        redis_safe_leg_meta = { 
            k: (str(v) if isinstance(v, bool) else ("" if v is None else str(v))) # Ensure ALL non-None are strings
            for k, v in leg_meta_dict_to_store.items() 
        }
        # ---- DEBUG PRINT ----
        print(f"[SEED DEBUG] About to HMSET leg_meta:{full_leg_id}. Data for Redis: {redis_safe_leg_meta}")
        # ---- END DEBUG PRINT ----
        r.hmset(f"leg_meta:{full_leg_id}", redis_safe_leg_meta)
        print(f"[SEED T0] Initialized leg_meta for {full_leg_id}.") # Removed data from log
    return contract

# --- Main Scenario Schedule --- 
def schedule(stop_event: Event, pause_event: Event, clock_callback):
    print("[SEED] ====== Schedule Function Entered ======") # New log
    scenario_start_time_abs = time.time()
    current_sim_time_s = 0
    clock_callback(current_sim_time_s) # Ensures clock is 0 at the very start of this attempt
    print(f"[SEED @ T+{current_sim_time_s}s] Initial clock set by callback.")

    try:
        # Initial fixed delay to ensure clock updates once
        initial_delay_target = 1 # Target 1s simulation time for first event (funding)
        print(f"[SEED @ T+{current_sim_time_s}s] About to perform initial sleep for {initial_delay_target}s simulation time.")
        sleep_duration = initial_delay_target - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback):
            print("[SEED] Initial _pausable_sleep returned False. Exiting schedule.") 
            return
        current_sim_time_s = initial_delay_target # Explicitly set sim time
        clock_callback(current_sim_time_s)      # Explicitly update global clock
        print(f"[SEED @ T+{current_sim_time_s}s] Initial sleep finished. Global clock updated.")

        # Initial funding 
        print(f"[SEED @ T+{current_sim_time_s}s] Initializing trader accounts...")
        fund_trader(SHIPPER_A_ID, 300000, initial_funding=True)
        fund_trader(MM_TRADER_ID, 200000, initial_funding=True)
        for carrier in CARRIERS: fund_trader(carrier, 100000, initial_funding=True)
        for bidder in OTHER_BIDDERS: fund_trader(bidder, 50000, initial_funding=True)
        get_trader_balance(PLATFORM_TRADER_ID)

        print(f"[SEED @ T+{current_sim_time_s}s] Creating ContainerContract {CONTRACT_ID}...")
        legs_config_c1 = [
            {"id": LEG_L1, "origin": "Shenzhen", "destination": "Rotterdam", "high_estimate": LEG_HIGH_ESTIMATES[LEG_L1], "target_freight_bid": LEG_TARGET_FREIGHT_BID_PRICES[LEG_L1], "carrier_asks": CARRIER_ASK_PRICES[LEG_L1], "delivery_duration": 15, "freight_auction_sim_time": 5, "iot_delivery_sim_time": 25},
            {"id": LEG_L2, "origin": "Rotterdam", "destination": "Dublin",    "high_estimate": LEG_HIGH_ESTIMATES[LEG_L2], "target_freight_bid": LEG_TARGET_FREIGHT_BID_PRICES[LEG_L2], "carrier_asks": CARRIER_ASK_PRICES[LEG_L2], "delivery_duration": 15, "freight_auction_sim_time": 50, "iot_delivery_sim_time": 70},
            {"id": LEG_L3, "origin": "Dublin",    "destination": "Nenagh",      "high_estimate": LEG_HIGH_ESTIMATES[LEG_L3], "target_freight_bid": LEG_TARGET_FREIGHT_BID_PRICES[LEG_L3], "carrier_asks": CARRIER_ASK_PRICES[LEG_L3], "delivery_duration": 15, "freight_auction_sim_time": 52, "iot_delivery_sim_time": 70}
        ]
        container_c1 = action_t0_create_and_book_container_contract(CONTRACT_ID, SHIPPER_A_ID, "Shenzhen", "Nenagh", legs_config_c1)
        if not container_c1: print("[SEED_ERROR] Failed to create C1."); return 
        initial_c1_contract_ref_price = container_c1.max_prepaid_cost * 0.1 
        _place_mm_quotes_seed(get_contract_book_id(CONTRACT_ID), MM_TRADER_ID, initial_c1_contract_ref_price, MM_CONTRACT_QUOTE_OFFSET, "CONTRACT_OWNERSHIP")
        # --- Event Timeline ---    
        target_event_time = 5
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        leg1_full_id = get_full_leg_id(LEG_L1, CONTRACT_ID)
        print(f"[SEED @ T+{current_sim_time_s}s] Opening auction for Leg {leg1_full_id}")
        r.hmset(f"leg_meta:{leg1_full_id}", {"status": "AUCTION_OPEN"})
        for i, carrier_name in enumerate(CARRIERS):
            ask_price = legs_config_c1[0]["carrier_asks"][i]
            submit_order("ask", leg1_full_id, ask_price, 1, carrier_name, order_type="LEG_FREIGHT", container_contract_id=CONTRACT_ID)
        _place_mm_quotes_seed(leg1_full_id, MM_TRADER_ID, legs_config_c1[0]["carrier_asks"][-1], MM_FREIGHT_QUOTE_OFFSET, "LEG_FREIGHT", CONTRACT_ID)
        target_event_time = 10
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        owner_c1 = r.hget(f"container_contract:{CONTRACT_ID}", "current_owner_id") or SHIPPER_A_ID
        print(f"[SEED @ T+{current_sim_time_s}s] {owner_c1} bids for {leg1_full_id} freight.")
        submit_order("bid", leg1_full_id, legs_config_c1[0]["target_freight_bid"], 1, owner_c1, order_type="LEG_FREIGHT", container_contract_id=CONTRACT_ID)
        r.hmset(f"leg_meta:{leg1_full_id}", {"status": "IN_TRANSIT"})
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "IN_TRANSIT_L1"})
        r.mset({f"leg_info:{leg1_full_id}:start_sim_time_s": current_sim_time_s, f"leg_info:{leg1_full_id}:eta_duration_s": legs_config_c1[0]["delivery_duration"]})
        target_event_time = 25
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        print(f"[SEED @ T+{current_sim_time_s}s] IoT: Leg {LEG_L1} of {CONTRACT_ID} delivered.")
        r.xadd("iot", {"container_contract_id": CONTRACT_ID, "leg_id": LEG_L1, "status": "DELIVERED_FINAL_LEG", "ts": datetime.now(timezone.utc).isoformat()})
        r.hmset(f"leg_meta:{leg1_full_id}", {"status": "DELIVERED"})
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "DELIVERED_L1_AWAITING_L2"})
        target_event_time = 30
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        c1_book_id = get_contract_book_id(CONTRACT_ID)
        print(f"[SEED @ T+{current_sim_time_s}s] Shippers bidding for ownership of {CONTRACT_ID}.")
        submit_order("bid", c1_book_id, 1000, 1, "CheapLtd", order_type="CONTRACT_OWNERSHIP")
        submit_order("bid", c1_book_id, 1200, 1, "FastPLC", order_type="CONTRACT_OWNERSHIP")
        current_owner_of_c1_for_ask = r.hget(f"container_contract:{CONTRACT_ID}", "current_owner_id") or SHIPPER_A_ID
        submit_order("ask", c1_book_id, 1450, 1, current_owner_of_c1_for_ask, order_type="CONTRACT_OWNERSHIP")
        print(f"[SEED @ T+{current_sim_time_s}s] Owner {current_owner_of_c1_for_ask} places Ask for {CONTRACT_ID} @ 1450.")
        target_event_time = 40
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        print(f"[SEED @ T+{current_sim_time_s}s] WealthyCorp overbids for {CONTRACT_ID}.")
        submit_order("bid", c1_book_id, 1500, 1, "WealthyCorp", order_type="CONTRACT_OWNERSHIP")
        target_event_time = 50
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        leg2_full_id = get_full_leg_id(LEG_L2, CONTRACT_ID)
        print(f"[SEED @ T+{current_sim_time_s}s] Opening auction for Leg {leg2_full_id}")
        r.hmset(f"leg_meta:{leg2_full_id}", {"status": "AUCTION_OPEN"})
        for i, carrier_name in enumerate(CARRIERS):
            ask_price = legs_config_c1[1]["carrier_asks"][i]
            submit_order("ask", leg2_full_id, ask_price, 1, carrier_name, order_type="LEG_FREIGHT", container_contract_id=CONTRACT_ID)
        _place_mm_quotes_seed(leg2_full_id, MM_TRADER_ID, legs_config_c1[1]["carrier_asks"][-1], MM_FREIGHT_QUOTE_OFFSET, "LEG_FREIGHT", CONTRACT_ID)
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "AUCTIONING_L2"})
        target_event_time = 55
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        owner_c1 = r.hget(f"container_contract:{CONTRACT_ID}", "current_owner_id") or SHIPPER_A_ID
        print(f"[SEED @ T+{current_sim_time_s}s] {owner_c1} bids for {leg2_full_id} freight.")
        submit_order("bid", leg2_full_id, legs_config_c1[1]["target_freight_bid"], 1, owner_c1, order_type="LEG_FREIGHT", container_contract_id=CONTRACT_ID)
        r.hmset(f"leg_meta:{leg2_full_id}", {"status": "IN_TRANSIT"})
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "IN_TRANSIT_L2"})
        r.mset({f"leg_info:{leg2_full_id}:start_sim_time_s": current_sim_time_s, f"leg_info:{leg2_full_id}:eta_duration_s": legs_config_c1[1]["delivery_duration"]})
        target_event_time = 57 
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        leg3_full_id = get_full_leg_id(LEG_L3, CONTRACT_ID)
        print(f"[SEED @ T+{current_sim_time_s}s] Opening auction for Leg {leg3_full_id}")
        r.hmset(f"leg_meta:{leg3_full_id}", {"status": "AUCTION_OPEN"})
        for i, carrier_name in enumerate(CARRIERS):
            ask_price = legs_config_c1[2]["carrier_asks"][i]
            submit_order("ask", leg3_full_id, ask_price, 1, carrier_name, order_type="LEG_FREIGHT", container_contract_id=CONTRACT_ID)
        _place_mm_quotes_seed(leg3_full_id, MM_TRADER_ID, legs_config_c1[2]["carrier_asks"][-1], MM_FREIGHT_QUOTE_OFFSET, "LEG_FREIGHT", CONTRACT_ID)
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "AUCTIONING_L3"})
        target_event_time = 60
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        owner_c1 = r.hget(f"container_contract:{CONTRACT_ID}", "current_owner_id") or SHIPPER_A_ID
        print(f"[SEED @ T+{current_sim_time_s}s] {owner_c1} bids for {leg3_full_id} freight.")
        submit_order("bid", leg3_full_id, legs_config_c1[2]["target_freight_bid"], 1, owner_c1, order_type="LEG_FREIGHT", container_contract_id=CONTRACT_ID)
        r.hmset(f"leg_meta:{leg3_full_id}", {"status": "IN_TRANSIT"})
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "IN_TRANSIT_L3"})
        r.mset({f"leg_info:{leg3_full_id}:start_sim_time_s": current_sim_time_s, f"leg_info:{leg3_full_id}:eta_duration_s": legs_config_c1[2]["delivery_duration"]})
        target_event_time = 70
        sleep_duration = target_event_time - current_sim_time_s
        if not _pausable_sleep(sleep_duration, stop_event, pause_event, scenario_start_time_abs, clock_callback): return
        current_sim_time_s = target_event_time; clock_callback(current_sim_time_s)
        print(f"[SEED @ T+{current_sim_time_s}s] IoT: Leg {LEG_L2} of {CONTRACT_ID} delivered.")
        r.xadd("iot", {"container_contract_id": CONTRACT_ID, "leg_id": LEG_L2, "status": "DELIVERED_FINAL_LEG", "ts": datetime.now(timezone.utc).isoformat()})
        r.hmset(f"leg_meta:{leg2_full_id}", {"status": "DELIVERED"})
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "DELIVERED_L2_AWAITING_L3"})
        print(f"[SEED @ T+{current_sim_time_s}s] IoT: Leg {LEG_L3} of {CONTRACT_ID} delivered (Final Destination).")
        r.xadd("iot", {"container_contract_id": CONTRACT_ID, "leg_id": LEG_L3, "status": "DELIVERED_FINAL_LEG", "ts": datetime.now(timezone.utc).isoformat()})
        r.hmset(f"leg_meta:{leg3_full_id}", {"status": "DELIVERED"})
        r.hmset(f"container_contract:{CONTRACT_ID}", {"status": "DELIVERED_FINAL"})
        contract_data_final = r.hgetall(f"container_contract:{CONTRACT_ID}")
        initial_shipper_final = contract_data_final.get("initial_shipper_id", SHIPPER_A_ID)
        shipper_final_locked_funds = get_trader_balance(initial_shipper_final)["locked"]
        if shipper_final_locked_funds > 0:
            release_funds(initial_shipper_final, shipper_final_locked_funds, f"Residual escrow refund for completed {CONTRACT_ID}")
            print(f"[SEED @ T+{current_sim_time_s}s] Refunded {shipper_final_locked_funds} final residual to {initial_shipper_final}.")

        print(f"[SEED @ T+{current_sim_time_s}s] ===== Full Scenario Script Completed =====")

    except Exception as e:
        import traceback
        print(f"[SEED_ERROR] Unhandled exception in schedule thread: {type(e).__name__} - {e}")
        print(traceback.format_exc())
    finally:
        print("[SEED] Schedule function finished.")

# Ensure imports from matching are sufficient for helpers like _book_key if used internally by seed helpers
# from matching import _book_key # This was renamed to matching_book_key if used locally
