import uuid
from redis import Redis
from models import Order, Match

r = Redis(host="redis", decode_responses=True)

def _book_key(side: str, leg_id: str) -> str:
    return f"{side}:{leg_id}"

def submit_order(side: str, leg_id: str, price: float, qty: int, trader: str) -> Match | None:
    """Insert order, try to cross, return a Match object if trade occurs"""
    order = Order(
        id=str(uuid.uuid4()),
        leg_id=leg_id,
        trader=trader,
        side=side,
        price=price,
        qty=qty,
    )
    opposite = "ask" if side == "bid" else "bid"
    opp_key = _book_key(opposite, leg_id)
    me_key = _book_key(side, leg_id)

    # check top of opposite book
    best_opp = r.zrange(opp_key, 0, 0, withscores=True)
    crossed = (
        best_opp
        and ((side == "bid" and price >= best_opp[0][1]) or (side == "ask" and price <= best_opp[0][1]))
    )

    if crossed:
        best_id, best_price = best_opp[0]
        r.zrem(opp_key, best_id)
        match = Match(
            id=str(uuid.uuid4()),
            leg_id=leg_id,
            bid_id=order.id if side == "bid" else best_id,
            ask_id=order.id if side == "ask" else best_id,
            price=best_price,
            qty=1,
        )
        r.xadd(f"matches:{leg_id}", match.model_dump())
        return match

    # no cross – add to book
    score = price if side == "ask" else -price
    r.zadd(me_key, {order.id: score})
    r.hset(f"orders:{leg_id}", order.id, order.model_dump_json())
    return None

def snapshot_book(leg_id: str) -> dict:
    bids = [(-score, oid) for oid, score in r.zrange(_book_key("bid", leg_id), 0, -1, withscores=True)]
    asks = [(score, oid) for oid, score in r.zrange(_book_key("ask", leg_id), 0, -1, withscores=True)]
    return {"bids": bids, "asks": asks}
