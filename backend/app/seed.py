import time, uuid
from matching import submit_order, r

LEG1, LEG2, LEG3 = "L1", "L2", "L3"
CARRIERS = ["Maersk", "Evergreen", "COSCO", "MSC", "Hapag"]
SHIPPER = "ShipperA"

def fund(trader: str, amt: float):
    r.hset(f"escrow:{trader}", mapping={"balance": amt, "locked": 0})

def schedule():
    time.sleep(3) # Optional delay to avoid Redis race condition on startup
    fund(SHIPPER, 20_000)

    # preload carrier asks for each leg
    for leg, base in [(LEG1, 8000), (LEG2, 4000), (LEG3, 2000)]:
        for i, c in enumerate(CARRIERS):
            submit_order("ask", leg, base - i * 500, 1, c)

    # 10 s – SHZ→RTM matches
    time.sleep(10)
    submit_order("bid", LEG1, 8000, 1, SHIPPER)

    # 25 s – mark delivered (escrow release)
    time.sleep(15)
    r.xadd("iot", {"leg_id": LEG1, "status": "delivered"})

    # 30 s – two new bids for container ownership
    time.sleep(5) # Current time: +10 (L1 match) + 15 (L1 deliver) + 5 = +30s
    print("[SEEDER @ +30s] Submitting two bids for CONT leg")
    submit_order("bid", "CONT", 1000, 1, "CheapLtd")
    submit_order("bid", "CONT", 1200, 1, "FastPLC") # FastPLC is current highest bidder

    # +40 s: higher bidder overbids (use same submit_order)
    # This means FastPLC (or another entity) bids higher for the container.
    # If "winning" implies being the highest bid, this is it.
    # If "winning" implies matching an ask, "CONT" leg currently has no asks.
    time.sleep(10) # Current time: +30s + 10s = +40s
    print("[SEEDER @ +40s] FastPLC overbids on CONT leg")
    # Assuming FastPLC increases their own bid, or another higher bidder appears.
    # Let's make a new, even higher bid from a different entity for clarity.
    submit_order("bid", "CONT", 1500, 1, "WealthyCorp") 

    # 55 s – RTM→DUB
    # Need to adjust sleep: current time is +40s. Need +15s to reach +55s.
    time.sleep(15) # Current time: +40s + 15s = +55s
    print("[SEEDER @ +55s] Submitting bid for L2")
    submit_order("bid", LEG2, 4000, 1, SHIPPER)

    # 70 s – final legs delivered
    # Need to adjust sleep: current time is +55s. Need +15s to reach +70s.
    time.sleep(15) # Current time: +55s + 15s = +70s
    print("[SEEDER @ +70s] Marking L2 & L3 delivered")
    r.xadd("iot", {"leg_id": LEG2, "status": "delivered"})
    r.xadd("iot", {"leg_id": LEG3, "status": "delivered"})
