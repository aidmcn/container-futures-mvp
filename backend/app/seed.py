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
    time.sleep(5)
    submit_order("bid", "CONT", 1000, 1, "CheapLtd")
    submit_order("bid", "CONT", 1200, 1, "FastPLC")

    # 55 s – RTM→DUB
    time.sleep(25)
    submit_order("bid", LEG2, 4000, 1, SHIPPER)

    # 70 s – final legs delivered
    time.sleep(15)
    r.xadd("iot", {"leg_id": LEG2, "status": "delivered"})
    r.xadd("iot", {"leg_id": LEG3, "status": "delivered"})
