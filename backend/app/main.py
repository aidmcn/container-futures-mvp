import uuid, json, os, asyncio
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from matching import submit_order, snapshot_book
from scheduler import start as start_scheduler

r = Redis(host=os.getenv("REDIS_HOST", "localhost"), decode_responses=True)
app = FastAPI()

# --- BEGIN CORS CONFIGURATION ---
origins = [
    "http://localhost",         # Common for local development
    "http://localhost:5173",    # Specifically your frontend's origin
    # You might add your actual deployed frontend origin here in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Usually needed for cookies, etc. (though maybe not for this app yet)
    allow_methods=["*"],    # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],    # Allow all headers
)
# --- END CORS CONFIGURATION ---

# Placeholder for global state or functions that scheduler will control
SIMULATION_STATE = {"running": False, "clock": 0, "scheduler_instance": None, "job": None}

# Placeholder for fetching balances - this will need actual implementation
def get_all_balances():
    # Example: fetch from Redis Hashes like escrow:TraderA
    # For now, returning dummy data
    return {
        "ShipperA": {"balance": 10000, "locked": 0},
        "Maersk": {"balance": 50000, "locked": 0},
        "CheapLtd": {"balance": 5000, "locked": 0},
        "FastPLC": {"balance": 5000, "locked": 0},
        "WealthyCorp": {"balance": 5000, "locked": 0},
        "Platform": {"balance": 100000, "locked": 0}
    }

# Placeholder for IoT progress - this will need actual implementation
def get_iot_progress():
    # Example: L1_progress: 0.0 to 1.0, L1_delivered: bool
    # For now, returning dummy data that might change based on SIMULATION_STATE["clock"]
    progress = {}
    if SIMULATION_STATE["clock"] > 10 and SIMULATION_STATE["clock"] < 25:
        progress["L1"] = {"percentage": (SIMULATION_STATE["clock"] - 10) / 15 * 100, "status": "In Transit"}
    elif SIMULATION_STATE["clock"] >= 25:
        progress["L1"] = {"percentage": 100, "status": "Delivered"}
    else:
        progress["L1"] = {"percentage": 0, "status": "Pending"}
    # Similarly for L2, L3 based on their expected delivery windows
    # This is a simplified example; real logic would track events from seed.py
    return progress

# start_scheduler() # We will call this via an endpoint now

@app.post("/orders")
def place(o: Dict[str, Any]):
    m = submit_order(o["side"], o["leg_id"], o["price"], o["qty"], o["trader"])
    return {"match": m.model_dump(mode='json') if m else None}

@app.get("/orderbook/{leg_id}")
def ob(leg_id: str):
    return snapshot_book(leg_id)

@app.websocket("/ws/{leg_id}")
async def ws_leg_updates(ws: WebSocket, leg_id: str):
    await ws.accept()
    try:
        while True:
            # For a per-leg WebSocket, balances and global IoT progress are global.
            # Orderbook and matches are per-leg.
            current_balances = get_all_balances() # Fetch current balances
            iot_progress_data = get_iot_progress() # Fetch current IoT progress
            
            data_to_send = {
                "orderbook": snapshot_book(leg_id),
                "matches": r.xrange(f"matches:{leg_id}", "-", "+", count=10),
                "iot_progress": iot_progress_data, # Send global IoT progress
                "balances": current_balances, # Send all balances
                "simulation_clock": SIMULATION_STATE["clock"] # Send current simulation time
            }
            await ws.send_text(json.dumps(data_to_send))
            await asyncio.sleep(1)  # Send updates every 1 second
            # We are not waiting for ws.receive_text() anymore for server push
            # To handle client closing, send_text will eventually raise an error

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for leg: {leg_id} (client closed connection)")
    except Exception as e:
        print(f"Error in WebSocket for leg {leg_id}: {e}")
    finally:
        print(f"WebSocket for leg {leg_id} connection scope ended.")

# Endpoints for scheduler control will be added later (Phase 2)
# /play, /pause, /reset

# Endpoint for balances (could be part of WebSocket or separate)
@app.get("/balances")
def balances_endpoint():
    return get_all_balances()

# Initial call to start the seeder logic will be moved to a /play endpoint
# For now, to allow testing the WebSocket push, we can start it manually
# if not SIMULATION_STATE["scheduler_instance"]:
#     pass # start_scheduler() # Will be controlled by /play

