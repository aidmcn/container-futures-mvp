import uuid
from redis import Redis
from models import Order, Match, ContainerContract, LegInfo, LegSettlementHold
from datetime import datetime, timezone
from typing import Optional, Literal

r = Redis(host="redis", port=6379, db=0, decode_responses=True)

PLATFORM_FEE_PERCENTAGE = 0.01 # Example 1% platform fee
PLATFORM_TRADER_ID = "Platform"

# --- Helper Key Functions --- Ensure these are at the top, before use ---
def _escrow_key(trader_id: str) -> str: return f"escrow:{trader_id}"
def _order_details_key(order_id: str) -> str: return f"order_details:{order_id}"
def _book_key(side: str, book_id: str) -> str: return f"{side}:{book_id}"
def _container_contract_key(contract_id: str) -> str: return f"container_contract:{contract_id}"
def _leg_meta_key(full_leg_id: str) -> str: return f"leg_meta:{full_leg_id}"
def _leg_settlement_hold_key(match_id: str) -> str: return f"leg_settlement_hold:{match_id}"

# Ensure this helper is available or defined here
def _redis_safe_dict(pydantic_model_instance) -> dict:
    dump = pydantic_model_instance.model_dump(mode='json')
    return { 
        k: (str(v) if isinstance(v, bool) else ("" if v is None else str(v))) 
        for k, v in dump.items() 
    }

def get_trader_balance(trader_id: str) -> dict:
    key = _escrow_key(trader_id)
    if not r.exists(key):
        # Initialize if not exists, e.g., with 0 balance and 0 locked
        r.hmset(key, {"balance": "0", "locked": "0"})
        return {"balance": 0.0, "locked": 0.0}
    balance_data = r.hgetall(key)
    return {
        "balance": float(balance_data.get("balance", "0")),
        "locked": float(balance_data.get("locked", "0"))
    }

def adjust_trader_balance(trader_id: str, amount: float, field: str = "balance") -> bool:
    """Adjusts 'balance' or 'locked'. Amount can be positive or negative."""
    key = _escrow_key(trader_id)
    try:
        # Use a pipeline for atomic increment/decrement if field is balance or locked
        pipe = r.pipeline()
        pipe.hincrbyfloat(key, field, amount)
        pipe.execute()
        print(f"[ESCROW] Adjusted {trader_id} {field} by {amount}")
        return True
    except Exception as e:
        print(f"[ESCROW] Error adjusting {trader_id} {field}: {e}")
        return False

def lock_funds(trader_id: str, amount: float) -> bool:
    """Locks funds for a trader if available balance is sufficient."""
    if amount <= 0: return True # Locking zero or negative is a no-op, not an error for caller
    key = _escrow_key(trader_id)
    current_balance = get_trader_balance(trader_id)["balance"]
    if current_balance < amount:
        print(f"[ESCROW] Insufficient balance for {trader_id} to lock {amount}. Has: {current_balance}")
        return False
    
    pipe = r.pipeline()
    pipe.hincrbyfloat(key, "balance", -amount)
    pipe.hincrbyfloat(key, "locked", amount)
    pipe.execute()
    print(f"[ESCROW] Locked {amount} for {trader_id}")
    return True

def release_funds(trader_id: str, amount: float, reason: str = "Order cancelled/expired") -> bool:
    """Releases previously locked funds back to balance."""
    if amount <= 0: return True # Releasing zero or negative is a no-op
    key = _escrow_key(trader_id)
    current_locked = get_trader_balance(trader_id)["locked"]
    amount_to_release = min(amount, current_locked) 
    if amount > current_locked:
         print(f"[ESCROW] Warning: Trying to release {amount} for {trader_id}, but only {current_locked} locked. Releasing {current_locked}.")
    if amount_to_release > 0:
        pipe = r.pipeline()
        pipe.hincrbyfloat(key, "balance", amount_to_release)
        pipe.hincrbyfloat(key, "locked", -amount_to_release)
        pipe.execute()
        print(f"[ESCROW] Released {amount_to_release} for {trader_id} ({reason})")
    return True

def transfer_funds(from_trader: str, to_trader: str, amount: float, from_field: str = "balance", to_field: str = "balance") -> bool:
    """Transfers funds between traders. Uses specified fields (balance or locked)."""
    if amount <= 0: return False
    # For simplicity, assume 'from_field' has enough. Proper check might be needed.
    # This is a simplified transfer; real systems use more robust two-phase commits or checks.
    
    # Check if from_trader has enough in the specified field
    if from_field == "locked":
        if get_trader_balance(from_trader)["locked"] < amount:
            print(f"[ESCROW] Transfer failed: {from_trader} has insufficient locked funds for {amount}")
            return False
    elif get_trader_balance(from_trader)["balance"] < amount:
        print(f"[ESCROW] Transfer failed: {from_trader} has insufficient balance for {amount}")
        return False

    pipe = r.pipeline()
    pipe.hincrbyfloat(_escrow_key(from_trader), from_field, -amount)
    pipe.hincrbyfloat(_escrow_key(to_trader), to_field, amount)
    pipe.execute()
    print(f"[ESCROW] Transferred {amount} from {from_trader} ({from_field}) to {to_trader} ({to_field})")
    return True

def release_funds_for_leg(leg_id: str, carrier_trader_id: str, bid_order_id: str):
    """Called when a leg is delivered. Releases locked funds from original bidder to carrier."""
    # This function assumes the bid_order_id contains enough info to find the original bidder
    # and the amount. For now, it's simplified.
    # We need to get the matched order details to find the price and original bidder.
    
    # This is highly simplified. A real system would look up the match details for the leg,
    # find the original bid, its price, and the bidder.
    # For MVP, we assume the seed script manages this flow and IoT events trigger this conceptually.
    # The actual transfer might have happened at match time, and this is just a conceptual step
    # or for specific types of escrow not immediately settled.
    
    # Let's assume for the MVP that the funds were already handled at match time or
    # that a more sophisticated lookup is needed.
    # This placeholder won't do much without more context on how funds are held post-match.
    print(f"[ESCROW] Conceptual: release_funds_for_leg {leg_id} to {carrier_trader_id} for order {bid_order_id}")
    # A real implementation would look up the matched price for the bid_order_id
    # and transfer from the original bidder's locked funds (if held that long) to the carrier.
    # For this MVP, we assume payment to carrier happens upon matching, and this function
    # would be for more complex escrow scenarios not yet fully detailed.
    return True

def get_order_details(order_id: str) -> Optional[Order]:
    details_dict = r.hgetall(_order_details_key(order_id))
    if not details_dict: return None
    # Handle empty strings for optional fields when re-parsing from Redis
    # Pydantic v2 should handle Optional fields with empty strings if types are correct
    # Forcing None for empty strings if needed for specific fields:
    # for k, v in details_dict.items():
    #     if v == "": details_dict[k] = None 
    try:
        return Order.model_validate(details_dict)
    except Exception as e:
        print(f"[MATCHING_ERROR] Could not validate order details for {order_id}: {details_dict}, Error: {e}")
        return None

def submit_order(
    side: str, book_id: str, price: float, qty: int, trader_id: str,
    order_type: Literal["CONTRACT_OWNERSHIP", "LEG_FREIGHT"],
    container_contract_id: Optional[str] = None
) -> Optional[Match]:
    if price <= 0: return None # Validation
    if qty <= 0: return None

    order = Order(
        id=str(uuid.uuid4()), leg_id=book_id, trader=trader_id, side=side,
        price=price, qty=qty, order_type=order_type, container_contract_id=container_contract_id,
        ts=datetime.now(timezone.utc)
    )
    r.hmset(_order_details_key(order.id), _redis_safe_dict(order))
    print(f"[MATCHING] Order {order.id} ({order_type} on {book_id}) by {trader_id} for Q{qty} @ {price} stored.")

    # Lock funds for bids (for both contract ownership and leg freight)
    if side == "bid":
        lock_amount = price * qty
        if not lock_funds(trader_id, lock_amount):
            print(f"[MATCHING] Order {order.id} rejected: Insufficient funds for {trader_id} to lock {lock_amount}.")
            r.delete(_order_details_key(order.id))
            return None

    # --- Attempt to Match --- 
    opposite_side = "ask" if side == "bid" else "bid"
    opp_book_key = _book_key(opposite_side, book_id)
    
    # Corrected logic for fetching opposing orders:
    if opposite_side == "ask": # Incoming order is a BID, look for lowest ASK
        # For asks (stored with positive price), zrange gives lowest price first.
        opp_orders_raw = r.zrange(opp_book_key, 0, 0, withscores=True)
    else: # Incoming order is an ASK, look for highest BID
        # For bids (stored with negative price), zrevrange gives highest price first (most positive of the negatives).
        opp_orders_raw = r.zrevrange(opp_book_key, 0, 0, withscores=True)
    
    if opp_orders_raw:
        opp_order_id, opp_score = opp_orders_raw[0]
        opp_order_details = get_order_details(opp_order_id)
        if not opp_order_details: 
            print(f"[MATCHING_ERROR] Opposite order {opp_order_id} details not found. Book: {opp_book_key}")
            if side == "bid": release_funds(trader_id, price * qty, "Match fail, opp details missing")
            return None

        opp_price = opp_order_details.price
        can_match = (
            (side == "bid" and price >= opp_price) or
            (side == "ask" and price <= opp_price)
        )

        if can_match:
            match_price = opp_price 
            match_qty = min(qty, opp_order_details.qty) 
            bid_order = order if side == "bid" else opp_order_details
            ask_order = order if side == "ask" else opp_order_details
            match = Match(
                id=str(uuid.uuid4()), leg_id=book_id, 
                bid_id=bid_order.id, ask_id=ask_order.id,
                bid_trader=bid_order.trader, ask_trader=ask_order.trader,
                price=match_price, qty=match_qty, match_type=order_type,
                container_contract_id=container_contract_id,
                ts=datetime.now(timezone.utc)
            )
            print(f"[MATCHING] Potential Match: {match.id} on {book_id} for Q{match.qty} @ {match_price}")
            settlement_amount = match_price * match_qty
            bidder_id = bid_order.trader
            asker_id = ask_order.trader

            if order_type == "CONTRACT_OWNERSHIP": 
                if not adjust_trader_balance(bidder_id, -settlement_amount, "locked"):
                    print(f"[MATCHING_ERROR] Failed to debit locked funds from {bidder_id} for CONTRACT_OWNERSHIP match {match.id}")
                    if side == "bid": release_funds(trader_id, price * qty, "Match settlement fail, debit locked error") 
                    return None 
                platform_fee = settlement_amount * PLATFORM_FEE_PERCENTAGE
                amount_to_seller = settlement_amount - platform_fee
                adjust_trader_balance(asker_id, amount_to_seller, "balance") 
                adjust_trader_balance(PLATFORM_TRADER_ID, platform_fee, "balance") 
                if match.container_contract_id:
                    r.hset(_container_contract_key(match.container_contract_id), "current_owner_id", bidder_id)
                    next_status = r.hget(_container_contract_key(match.container_contract_id), "status") 
                    if next_status == "BOOKED": next_status = "AUCTIONING_L1"
                    r.hset(_container_contract_key(match.container_contract_id), "status", next_status)
                    print(f"[MATCHING] CONTRACT_OWNERSHIP of {match.container_contract_id} transferred to {bidder_id}")
            elif order_type == "LEG_FREIGHT":
                temp_hold = LegSettlementHold(
                    match_id=match.id, leg_id=book_id, 
                    contract_id=container_contract_id or "UNKNOWN_CONTRACT",
                    amount=settlement_amount, payer_id=bidder_id, payee_id=asker_id, 
                    status="PENDING_DELIVERY"
                )
                r.hmset(_leg_settlement_hold_key(match.id), _redis_safe_dict(temp_hold))
                print(f"[MATCHING] LEG_FREIGHT Match {match.id}: Cost {settlement_amount} for leg {book_id} put on PENDING_DELIVERY for {bidder_id}, to pay {asker_id}.")

            r.xadd(f"matches:{book_id}", _redis_safe_dict(match))
            r.zrem(opp_book_key, opp_order_id) 
            if qty == match_qty and side == "bid": 
                price_improvement = (price - match_price) * qty
                if price_improvement > 0:
                    release_funds(trader_id, price_improvement, f"Price improvement on match {match.id}")
            return match

    # No match or no opposing order: Add order to book
    score = -price if side == "bid" else price # Store bids with negative scores for correct sorting
    r.zadd(_book_key(side, book_id), {order.id: score})
    print(f"[MATCHING] Order {order.id} added to book {book_id}. Funds remain locked if bid.")

    # If this was a bid on a CONTRACT_OWNERSHIP book, update potential owner
    if side == "bid" and order_type == "CONTRACT_OWNERSHIP":
        contract_id_of_book = book_id.split(":")[-1]
        # For CONTRACT_OWNERSHIP, current_owner_id on container_contract should be updated to highest bidder
        # Get all bids for CONTRACT book, sorted highest price first
        contract_bids_raw = r.zrevrange(_book_key("bid", book_id), 0, 0, withscores=True)
        if contract_bids_raw:
            highest_bid_order_id, _ = contract_bids_raw[0]
            highest_bid_details = get_order_details(highest_bid_order_id)
            if highest_bid_details and highest_bid_details.trader:
                r.hset(_container_contract_key(contract_id_of_book), "current_owner_id", highest_bid_details.trader)
                print(f"[MATCHING] Highest bidder for contract {contract_id_of_book} (now set as current_owner_id) is {highest_bid_details.trader}")
    return None

def finalize_leg_freight_settlement(base_leg_id: str, contract_id: str):
    print(f"[SETTLEMENT] Attempting finalize for delivered leg {base_leg_id} of contract {contract_id}.")
    pending_match_ids = []
    full_leg_id_delivered = f"{base_leg_id}_{contract_id}" # Construct full leg ID

    for key in r.scan_iter(match=_leg_settlement_hold_key("*")):
        hold_data_dict = r.hgetall(key)
        # Check if hold_data_dict.get("leg_id") matches full_leg_id_delivered
        if (
            hold_data_dict.get("leg_id") == full_leg_id_delivered and # Compare with full leg ID
            hold_data_dict.get("contract_id") == contract_id and
            hold_data_dict.get("status") == "PENDING_DELIVERY"
        ):
            match_id_from_hold = hold_data_dict.get("match_id")
            if match_id_from_hold:
                pending_match_ids.append(match_id_from_hold)
            else:
                print(f"[SETTLEMENT_WARN] Hold data for key {key} is missing match_id field.")

    if not pending_match_ids:
        print(f"[SETTLEMENT] No PENDING_DELIVERY settlements for {full_leg_id_delivered} of {contract_id}. Check match_id or leg_id naming in hold.")
        return False

    all_settled_ok = True
    for match_id in pending_match_ids:
        hold_key = _leg_settlement_hold_key(match_id)
        hold_data_dict = r.hgetall(hold_key)
        if not hold_data_dict: continue 
        try:
            hold = LegSettlementHold.model_validate(hold_data_dict)
        except Exception as e:
            print(f"[SETTLEMENT_ERROR] Invalid hold data for match {match_id}: {e}"); all_settled_ok = False; continue

        print(f"[SETTLEMENT] Processing hold for match {match_id}: Payer {hold.payer_id}, Payee {hold.payee_id}, Amount {hold.amount}")
        if not adjust_trader_balance(hold.payer_id, -hold.amount, "locked"):
            print(f"[SETTLEMENT_ERROR] Failed to debit locked funds from {hold.payer_id} for match {match_id}. Amount {hold.amount}")
            all_settled_ok = False; continue
        platform_fee = hold.amount * PLATFORM_FEE_PERCENTAGE
        amount_to_carrier = hold.amount - platform_fee
        adjust_trader_balance(hold.payee_id, amount_to_carrier, "balance")
        adjust_trader_balance(PLATFORM_TRADER_ID, platform_fee, "balance")
        r.hset(hold_key, "status", "SETTLED")
        # Use base_leg_id for leg_meta key structure used in seed.py
        r.hset(_leg_meta_key(f"{base_leg_id}_{hold.contract_id}"), "status", "SETTLED")
        print(f"[SETTLEMENT] Leg {base_leg_id} (Match {match_id}) SETTLED for {contract_id}.")
    return all_settled_ok

def snapshot_book(book_id: str) -> dict:
    bids_raw = r.zrange(_book_key("bid", book_id), 0, -1, withscores=True, score_cast_func=float)
    asks_raw = r.zrange(_book_key("ask", book_id), 0, -1, withscores=True, score_cast_func=float)
    
    bids_with_qty = []
    for order_id, score in bids_raw:
        details = get_order_details(order_id)
        qty = details.qty if details else 0
        bids_with_qty.append((abs(score), order_id, qty))
    
    asks_with_qty = []
    for order_id, score in asks_raw:
        details = get_order_details(order_id)
        qty = details.qty if details else 0
        asks_with_qty.append((score, order_id, qty))

    bids_sorted = sorted(bids_with_qty, key=lambda x: x[0], reverse=True)
    return {"bids": bids_sorted, "asks": asks_with_qty}

def release_funds_on_delivery(leg_id: str, original_match_id: str):
    """
    Conceptual. If there's a secondary settlement upon delivery.
    This would require storing match details, identifying participants and amounts.
    For MVP, current settlement is at match time.
    If L1 bar snaps green causes ShipperA.locked to decrease and CarrierX.balance to increase,
    it means the Carrier was the one who got paid. The ShipperA placed the bid.
    This is consistent if the Carrier was the one who posted the ASK that ShipperA's BID matched.
    The current matching logic already pays the asker (Carrier) and reduces bidder's (ShipperA) locked funds.
    So, this function might be redundant if all settlement is immediate.
    Let's assume for now that the existing match settlement covers this for L1, L2, L3.
    """
    print(f"[ESCROW CONCEPT] Delivery event for leg {leg_id}, original match {original_match_id}. Funds already settled at match time under current model.")
    # If a specific delayed payment to carrier from shipper is needed, implement here.
    # Example: if ShipperA still had funds locked specifically *for freight*, release to Carrier.
    # This would imply the carrier was not the original asker, or a different type of escrow.
    # For now, this function doesn't change balances as current logic settles payment to asker on match.
    return True
