import uuid, json, os
from typing import Dict, Any
from fastapi import FastAPI, WebSocket
from redis import Redis
from matching import submit_order, snapshot_book
from scheduler import start as start_scheduler

r = Redis(host=os.getenv("REDIS_HOST", "localhost"), decode_responses=True)
app = FastAPI()
start_scheduler()

@app.post("/orders")
def place(o: Dict[str, Any]):
    m = submit_order(o["side"], o["leg_id"], o["price"], o["qty"], o["trader"])
    return {"match": m.model_dump() if m else None}

@app.get("/orderbook/{leg_id}")
def ob(leg_id: str):
    return snapshot_book(leg_id)

@app.websocket("/ws/{leg_id}")
async def ws(ws: WebSocket, leg_id: str):
    await ws.accept()
    while True:
        await ws.send_text(json.dumps(snapshot_book(leg_id)))
        await ws.send_text(json.dumps({"matches": r.xrange(f"matches:{leg_id}", count=5)}))
        await ws.send_text(json.dumps({"iot": r.xrevrange("iot", count=5)}))
        await ws.receive_text()  # keep-alive
