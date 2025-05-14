import uuid
from redis import Redis
from models import Order, Match
from datetime import datetime

r = Redis(host="redis", port=6379, db=0, decode_responses=True)

PLATFORM_FEE_PERCENTAGE = 0.01 # Example 1% platform fee
PLATFORM_TRADER_ID = "Platform"

def _escrow_key(trader_id: str) -> str:
    return f"escrow:{trader_id}"

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
    if amount <= 0: return False # Cannot lock zero or negative amount
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
    if amount <= 0: return False
    key = _escrow_key(trader_id)
    current_locked = get_trader_balance(trader_id)["locked"]
    if current_locked < amount:
        # This case might indicate an issue, but we release what's available up to the amount
        print(f"[ESCROW] Warning: Trying to release {amount} for {trader_id}, but only {current_locked} locked. Releasing {current_locked}.")
        amount_to_release = current_locked
    else:
        amount_to_release = amount

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

def _order_details_key(leg_id: str, order_id: str) -> str:
    return f"order_details:{leg_id}:{order_id}"

def get_order_details(leg_id: str, order_id: str) -> dict | None:
    key = _order_details_key(leg_id, order_id)
    details = r.hgetall(key)
    if not details:
        return None
    # Convert numeric fields back if needed, assuming they were stored as strings
    details["price"] = float(details.get("price", 0))
    details["qty"] = int(details.get("qty", 0))
    # ts might be an ISO string
    return details

def _book_key(side: str, leg_id: str) -> str:
    return f"{side}:{leg_id}"

def submit_order(side: str, leg_id: str, price: float, qty: int, trader: str) -> Match | None:
    if price <= 0:
        print(f"[MATCHING] Order rejected for {trader}: Price must be positive. Got {price}")
        return None
    if qty <= 0:
        print(f"[MATCHING] Order rejected for {trader}: Quantity must be positive. Got {qty}")
        return None

    order_id = str(uuid.uuid4())
    order_ts = datetime.utcnow()
    order = Order(
        id=order_id,
        leg_id=leg_id,
        trader=trader,
        side=side,
        price=price,
        qty=qty,
        ts=order_ts 
    )

    order_details_payload = order.model_dump(mode="json")
    for k, v in order_details_payload.items():
        if not isinstance(v, (str, int, float, bytes)):
            order_details_payload[k] = str(v)
    r.hmset(_order_details_key(leg_id, order.id), order_details_payload)
    print(f"[MATCHING] Stored order details for {order_id}: {order_details_payload}")

    if side == "bid":
        lock_amount = price * qty
        if not lock_funds(trader, lock_amount):
            print(f"[MATCHING] Order rejected for {trader}: insufficient funds to lock {lock_amount} for bid.")
            r.delete(_order_details_key(leg_id, order.id))
            return None 

    opposite = "ask" if side == "bid" else "bid"
    opp_key = _book_key(opposite, leg_id)
    me_key  = _book_key(side, leg_id)

    # Critical section: Check for match and execute atomically if possible
    # For simplicity in MVP, we don't use WATCH/MULTI for the whole block but should for production.
    best_opp_raw = r.zrange(opp_key, 0, 0, withscores=True)
    crossed = False
    match_price = 0.0
    best_opp_order_id = None
    best_opp_price_abs = 0.0

    if best_opp_raw:
        best_opp_order_id_cand, best_opp_score = best_opp_raw[0]
        best_opp_price_abs_cand = abs(best_opp_score)
        
        if side == "bid" and price >= best_opp_price_abs_cand:
            crossed = True
            match_price = best_opp_price_abs_cand # Match at existing ask price
            best_opp_order_id = best_opp_order_id_cand
            best_opp_price_abs = best_opp_price_abs_cand
        elif side == "ask" and price <= best_opp_price_abs_cand:
            crossed = True
            match_price = best_opp_price_abs_cand # Match at existing bid price
            best_opp_order_id = best_opp_order_id_cand
            best_opp_price_abs = best_opp_price_abs_cand

    if crossed and best_opp_order_id:
        best_opp_order_details = get_order_details(leg_id, best_opp_order_id)
        if not best_opp_order_details:
            print(f"[MATCHING] CRITICAL: Opposite order {best_opp_order_id} details not found. Match failed.")
            if side == "bid":
                release_funds(trader, price * qty, reason=f"Match failed, opponent {best_opp_order_id} details missing")
            return None

        opp_trader = best_opp_order_details["trader"]
        match_qty = 1 # MVP assumes qty=1

        # Determine bid_trader_id and ask_trader_id for the Match object
        current_bid_trader = trader if side == "bid" else opp_trader
        current_ask_trader = trader if side == "ask" else opp_trader
        
        # --- Escrow Settlement --- 
        settlement_amount = match_price * match_qty

        print(f"[MATCHING] Attempting match: {side} order {order_id} ({trader}) vs {opposite} order {best_opp_order_id} ({opp_trader}) at price {match_price} for qty {match_qty}")

        # 1. Debit bidder's LOCKED funds by settlement_amount.
        #    (lock_funds already moved from bidder's balance to locked)
        current_bidder_locked = get_trader_balance(current_bid_trader)["locked"]
        if current_bidder_locked < settlement_amount:
            print(f"[ESCROW] CRITICAL ERROR: Bidder {current_bid_trader} has only {current_bidder_locked} locked, needs {settlement_amount} for match {order_id} vs {best_opp_order_id}. Match aborted.")
            # This case should ideally not happen if lock_funds worked and no race conditions.
            # Release originally locked funds for the incoming order if it was a bid.
            if side == "bid":
                 release_funds(trader, price * qty, reason="Match aborted, insufficient locked funds found during settlement attempt")
            return None
        
        adjust_trader_balance(current_bid_trader, -settlement_amount, field="locked")
        
        # 2. Calculate platform fee and amount to asker
        platform_fee = settlement_amount * PLATFORM_FEE_PERCENTAGE
        amount_to_asker = settlement_amount - platform_fee

        # 3. Credit asker's BALANCE by amount_to_asker.
        adjust_trader_balance(current_ask_trader, amount_to_asker, field="balance")
        
        # 4. Credit PLATFORM_TRADER_ID's BALANCE by platform_fee.
        adjust_trader_balance(PLATFORM_TRADER_ID, platform_fee, field="balance")
        
        print(f"[ESCROW] Match Settlement: Bidder {current_bid_trader} locked reduced by {settlement_amount}. Asker {current_ask_trader} balance +{amount_to_asker}. Platform balance +{platform_fee}.")

        # Remove matched order from the book (assuming full match)
        r.zrem(opp_key, best_opp_order_id)
        # If incoming order was fully matched, it's not added to the book.
        # If it was a bid, its original locked amount was for price*qty. If match_price < price, 
        # the difference should be released from locked back to balance for the bidder.
        if side == "bid":
            price_improvement_refund = (price - match_price) * qty
            if price_improvement_refund > 0:
                release_funds(trader, price_improvement_refund, reason=f"Price improvement for match on {order_id}")
                print(f"[ESCROW] Price improvement: {trader} refunded {price_improvement_refund}")
        
        # Create and store the match with trader info
        match = Match(
            id=str(uuid.uuid4()), leg_id=leg_id,
            bid_id=order.id if side == "bid" else best_opp_order_id,
            ask_id=order.id if side == "ask" else best_opp_order_id,
            bid_trader=current_bid_trader,
            ask_trader=current_ask_trader,
            price=match_price, qty=match_qty, ts=datetime.utcnow()
        )
        match_payload_prep = match.model_dump(mode="json")
        payload_final = {k: str(v) if not isinstance(v, (str, int, float, bytes)) else v for k, v in match_payload_prep.items()}
        r.xadd(f"matches:{leg_id}", payload_final)
        print(f"[MATCHING] Match recorded: {match.id} on leg {leg_id}")

        if leg_id == "CONT":
            # Bidder of the matched order on CONT leg becomes the owner
            owner_trader = current_bid_trader # This is the trader who placed the successful bid
            r.set("current_container_owner", owner_trader)
            print(f"[MATCHING] New container owner for CONT: {owner_trader} from bid {match.bid_id}")
        
        return match
    else:
        # No cross – add order to book
        score = price if side == "ask" else -price
        r.zadd(me_key, {order.id: score})
        print(f"[MATCHING] Order {order.id} ({side} {leg_id} {price} {qty} {trader}) added to book. Funds remain locked if bid.")
        # Update current_container_owner if a new highest bid is placed on CONT leg
        if side == "bid" and leg_id == "CONT":
            # Get all bids for CONT leg, sorted highest price first
            cont_bids_raw = r.zrange(_book_key("bid", "CONT"), 0, -1, withscores=True, desc=True)
            if cont_bids_raw:
                highest_bid_order_id, _ = cont_bids_raw[0] # First one is highest due to desc=True
                highest_bid_details = get_order_details("CONT", highest_bid_order_id)
                if highest_bid_details and highest_bid_details.get("trader"):
                    new_owner = highest_bid_details["trader"]
                    r.set("current_container_owner", new_owner)
                    print(f"[MATCHING] New potential container owner (highest bid) for CONT: {new_owner}")
        return None

def snapshot_book(leg_id: str) -> dict:
    bids_raw = r.zrange(_book_key("bid", leg_id), 0, -1, withscores=True, score_cast_func=float)
    asks_raw = r.zrange(_book_key("ask", leg_id), 0, -1, withscores=True, score_cast_func=float)
    
    bids_with_qty = []
    for order_id, score in bids_raw:
        details = get_order_details(leg_id, order_id)
        qty = int(details.get("qty", 0)) if details else 0
        bids_with_qty.append((abs(score), order_id, qty))
    
    asks_with_qty = []
    for order_id, score in asks_raw:
        details = get_order_details(leg_id, order_id)
        qty = int(details.get("qty", 0)) if details else 0
        asks_with_qty.append((score, order_id, qty))

    # Sort bids by price descending (highest price first)
    bids_sorted = sorted(bids_with_qty, key=lambda x: x[0], reverse=True)
    # Asks are already sorted by price ascending by Redis zrange
    
    # Return format: { bids: [[price, id, qty]], asks: [[price, id, qty]] }
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
