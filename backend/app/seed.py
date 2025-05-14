import time
from threading import Event # For type hinting
from matching import submit_order, r, PLATFORM_TRADER_ID, get_trader_balance
from datetime import datetime

LEG1, LEG2, LEG3 = "L1", "L2", "L3"
CARRIERS = ["Maersk", "Evergreen", "COSCO", "MSC", "Hapag"]
SHIPPER = "ShipperA"

MM_TRADER_ID = "MarketMaker1"
MM_SPREAD = 50      # MM bids below best ask, asks above best bid
MM_QUOTE_OFFSET = 25 # How far from the reference price the MM quotes

def fund(trader: str, amt: float):
    r.hset(f"escrow:{trader}", mapping={"balance": amt, "locked": 0})
    print(f"[SEED] Funded {trader} with {amt}")

def _pausable_sleep(duration_seconds: float, stop_event: Event, pause_event: Event, start_abs_time: float, clock_callback):
    """A time.sleep replacement that respects pause and stop events and updates clock."""
    slept_so_far = 0
    step = 0.1 # Check for pause/stop every 100ms
    while slept_so_far < duration_seconds:
        if stop_event.is_set():
            print("[SEED] Stop event received during sleep.")
            return False # Indicate stop
        
        while pause_event.is_set():
            if stop_event.is_set():
                print("[SEED] Stop event received during pause.")
                return False # Indicate stop
            time.sleep(step) # Sleep in small steps while paused
            # Update clock even while paused if necessary, or only when running
            # For now, clock progresses based on actual progression of scenario time

        time.sleep(min(step, duration_seconds - slept_so_far))
        slept_so_far += step
        current_elapsed = time.time() - start_abs_time
        clock_callback(current_elapsed)
    return True # Indicate normal completion

def _get_best_book_prices(leg_id: str):
    bids_raw = r.zrange(_book_key("bid", leg_id), 0, 0, withscores=True, desc=True) # Highest bid
    asks_raw = r.zrange(_book_key("ask", leg_id), 0, 0, withscores=True) # Lowest ask
    best_bid_price = abs(bids_raw[0][1]) if bids_raw else None
    best_ask_price = asks_raw[0][1] if asks_raw else None
    return best_bid_price, best_ask_price

def _place_mm_quotes(leg_id: str, reference_ask_price: float | None, reference_bid_price: float | None):
    print(f"[MM SEED {leg_id}] Updating MM quotes. Ref Ask: {reference_ask_price}, Ref Bid: {reference_bid_price}")
    # Cancel previous MM orders for this leg (simplified: assume only one bid/ask pair by MM)
    # A more robust MM would track its order IDs. For MVP, this might remove other MMs if ID is generic.
    # For simplicity, we'll just place new ones. Old ones will expire or be hit.

    mm_bid_price, mm_ask_price = None, None

    if reference_ask_price is not None:
        mm_bid_price = reference_ask_price - MM_QUOTE_OFFSET 
        mm_ask_price = reference_ask_price + MM_QUOTE_OFFSET 
    elif reference_bid_price is not None: # No asks, but bids exist
        mm_bid_price = reference_bid_price - MM_QUOTE_OFFSET
        mm_ask_price = reference_bid_price + MM_QUOTE_OFFSET
    else: # Empty book, use a default reasonable price if possible, or skip
        print(f"[MM SEED {leg_id}] Book is empty, cannot determine reference for MM quotes based on existing orders.")
        # Example: Default for L1 if book is empty
        if leg_id == LEG1: mm_bid_price, mm_ask_price = 5000, 5100 
        elif leg_id == LEG2: mm_bid_price, mm_ask_price = 2500, 2600
        elif leg_id == LEG3: mm_bid_price, mm_ask_price = 1000, 1100

    if mm_bid_price and mm_bid_price > 0:
        submit_order("bid", leg_id, mm_bid_price, 1, MM_TRADER_ID)
        print(f"[MM SEED {leg_id}] Placed MM bid @ {mm_bid_price}")
    if mm_ask_price and mm_ask_price > 0:
        submit_order("ask", leg_id, mm_ask_price, 1, MM_TRADER_ID)
        print(f"[MM SEED {leg_id}] Placed MM ask @ {mm_ask_price}")

def schedule(stop_event: Event, pause_event: Event, clock_callback):
    """ 
    Main seeding and event scheduling logic.
    """
    print("[SEED] Starting main schedule sequence...")
    start_abs_time = time.time()

    if not _pausable_sleep(1, stop_event, pause_event, start_abs_time, clock_callback): return # Short initial delay
    
    fund(SHIPPER, 20_000)
    fund(MM_TRADER_ID, 100_000) # Fund the Market Maker
    traders_to_initialize = [PLATFORM_TRADER_ID] + CARRIERS + ["CheapLtd", "FastPLC", "WealthyCorp"]
    for trader_id in traders_to_initialize:
        get_trader_balance(trader_id) # Initializes if not exists
        print(f"[SEED] Ensured/Initialized escrow for {trader_id}")

    print("[SEED] Preloading carrier asks & initial MM quotes...")
    initial_carrier_ask_prices = {}
    # Leg 1 asks: 8000, 7500, 7000, 6500, 6000
    for i, c in enumerate(CARRIERS):
        price = 8000 - i * 500
        if i == len(CARRIERS) -1 : initial_carrier_ask_prices[LEG1] = price # Lowest ask for MM ref
        submit_order("ask", LEG1, price, 1, c)
    _place_mm_quotes(LEG1, initial_carrier_ask_prices.get(LEG1), None)

    # Leg 2 asks: 4000, 3500, 3000, 2500, 2000
    for i, c in enumerate(CARRIERS):
        price = 4000 - i * 500
        if i == len(CARRIERS) -1 : initial_carrier_ask_prices[LEG2] = price
        submit_order("ask", LEG2, price, 1, c)
    _place_mm_quotes(LEG2, initial_carrier_ask_prices.get(LEG2), None)

    # Leg 3 asks: 2000, 1500, 1000, 800, 600
    l3_ask_prices = [2000, 1500, 1000, 800, 600]
    for i, c in enumerate(CARRIERS):
        if i < len(l3_ask_prices):
            price = l3_ask_prices[i]
            if i == len(l3_ask_prices) -1 : initial_carrier_ask_prices[LEG3] = price
            submit_order("ask", LEG3, price, 1, c)
    _place_mm_quotes(LEG3, initial_carrier_ask_prices.get(LEG3), None)

    # Timeline events start from simulation clock perspective
    # +10s: L1 match
    print("[SEED] Waiting for L1 match event (target T+10s from scenario start)...")
    if not _pausable_sleep(10 - (time.time() - start_abs_time), stop_event, pause_event, start_abs_time, clock_callback): return 
    r.mset({f"leg_info:{LEG1}:start_sim_time_s": int(time.time() - start_abs_time), f"leg_info:{LEG1}:eta_duration_s": 15})
    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] Submitting bid for L1.")
    submit_order("bid", LEG1, 8000, 1, SHIPPER)

    # +25s: L1 delivered
    if not _pausable_sleep(15, stop_event, pause_event, start_abs_time, clock_callback): return
    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] Marking L1 delivered.")
    r.xadd("iot", {"leg_id": LEG1, "status": "delivered", "ts": datetime.utcnow().isoformat()})

    # +30s: CONT bids
    if not _pausable_sleep(5, stop_event, pause_event, start_abs_time, clock_callback): return
    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] Submitting CONT bids.")
    submit_order("bid", "CONT", 1000, 1, "CheapLtd")
    submit_order("bid", "CONT", 1200, 1, "FastPLC")

    # +40s: CONT overbid
    if not _pausable_sleep(10, stop_event, pause_event, start_abs_time, clock_callback): return
    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] WealthyCorp overbids CONT.")
    submit_order("bid", "CONT", 1500, 1, "WealthyCorp")

    # +55s: L2 match
    if not _pausable_sleep(15, stop_event, pause_event, start_abs_time, clock_callback): return
    r.mset({f"leg_info:{LEG2}:start_sim_time_s": int(time.time() - start_abs_time), f"leg_info:{LEG2}:eta_duration_s": 15})
    # L3 also effectively starts its journey with L2 for eta calculation for timeline
    r.mset({f"leg_info:{LEG3}:start_sim_time_s": int(time.time() - start_abs_time), f"leg_info:{LEG3}:eta_duration_s": 15})
    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] Submitting bid for L2.")
    submit_order("bid", LEG2, 4000, 1, SHIPPER)

    # +70s: L2 & L3 delivered
    if not _pausable_sleep(15, stop_event, pause_event, start_abs_time, clock_callback): return
    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] Marking L2 & L3 delivered.")
    r.xadd("iot", {"leg_id": LEG2, "status": "delivered", "ts": datetime.utcnow().isoformat()})
    r.xadd("iot", {"leg_id": LEG3, "status": "delivered", "ts": datetime.utcnow().isoformat()})

    print(f"[SEED @ T+{int(time.time() - start_abs_time)}s] Seed script fully completed.")
