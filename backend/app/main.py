import uuid, json, os, asyncio
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis

# Updated imports from our modules
from matching import submit_order, snapshot_book, get_trader_balance, adjust_trader_balance, lock_funds, release_funds_for_leg, get_order_details
from scheduler import start_simulation as sim_start, pause_simulation as sim_pause, \
                      resume_simulation as sim_resume, reset_simulation as sim_reset, \
                      get_simulation_state as sim_get_state

# Initialize Redis connection (ensure decode_responses=True for strings)
r = Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0, decode_responses=True)
app = FastAPI()

# CORS Configuration (remains the same)
origins = ["http://localhost", "http://localhost:5173"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Simulation State (managed by main.py, updated by scheduler.py callbacks/polling) ---
# This state is what the UI will primarily reflect for global simulation status.
# scheduler.py will have its own internal state for managing the thread/events.
SIMULATION_APP_STATE = {"running": False, "paused": False, "clock": 0}

# --- Data Fetching Functions ---
def get_all_balances_from_redis():
    balances = {}
    escrow_keys = r.keys("escrow:*")
    traders_involved = ["ShipperA"] + [f"Carrier{i+1}" for i in range(5)] + ["CheapLtd", "FastPLC", "WealthyCorp", "Platform"]
    
    # Ensure all traders have an initial entry if not present
    for trader_name in traders_involved:
        key = f"escrow:{trader_name}"
        if not r.exists(key):
            r.hmset(key, {"balance": 0, "locked": 0})
            print(f"Initialized escrow for {trader_name}")
        
        balance_data = r.hgetall(key)
        balances[trader_name] = {
            "balance": float(balance_data.get("balance", 0)),
            "locked": float(balance_data.get("locked", 0))
        }
    return balances

def get_iot_progress_from_redis():
    iot_progress = {}
    legs_for_timeline = ["L1", "L2", "L3"]
    iot_events_raw = r.xrevrange("iot", "+", "-", count=100) # Get last 100 IoT events
    
    delivered_legs = set()
    for _msg_id, event_fields in iot_events_raw:
        leg_id = event_fields.get("leg_id")
        if event_fields.get("status") == "delivered":
            delivered_legs.add(leg_id)
            
    sim_clock_seconds = SIMULATION_APP_STATE["clock"]

    for leg in legs_for_timeline:
        if leg in delivered_legs:
            iot_progress[leg] = {"percentage": 100, "status": "Delivered"}
        else:
            start_sim_time_s_str = r.get(f"leg_info:{leg}:start_sim_time_s")
            eta_duration_s_str = r.get(f"leg_info:{leg}:eta_duration_s")

            if start_sim_time_s_str and eta_duration_s_str:
                start_sim_time_s = int(start_sim_time_s_str)
                eta_duration_s = int(eta_duration_s_str)
                
                if sim_clock_seconds >= start_sim_time_s and eta_duration_s > 0:
                    elapsed_on_leg = sim_clock_seconds - start_sim_time_s
                    percentage = min(100.0, (elapsed_on_leg / eta_duration_s) * 100.0)
                    iot_progress[leg] = {"percentage": percentage, "status": "In Transit" if percentage < 100 else "Pending"}
                else:
                    iot_progress[leg] = {"percentage": 0, "status": "Pending"}
            else:
                # leg hasn't started according to Redis info, or info missing
                iot_progress[leg] = {"percentage": 0, "status": "Pending"}
    return iot_progress

# --- Escrow and Ownership (called by matching.py and seed.py/scheduler) ---
# This is a conceptual placement. Escrow logic is now primarily in matching.py

# --- API Endpoints ---
@app.post("/play")
async def play_simulation():
    global SIMULATION_APP_STATE
    if sim_start(SIMULATION_APP_STATE): # Pass our app state reference to the scheduler module
        return {"message": "Simulation started/resumed."}
    return {"message": "Simulation already running or failed to start."}

@app.post("/pause")
async def pause_simulation_endpoint():
    global SIMULATION_APP_STATE
    if SIMULATION_APP_STATE["running"] and not SIMULATION_APP_STATE["paused"]:
        if sim_pause(SIMULATION_APP_STATE):
             return {"message": "Simulation paused."}
    return {"message": "Simulation not running or already paused."}

@app.post("/resume") # Added for completeness, Play can often double as resume
async def resume_simulation_endpoint():
    global SIMULATION_APP_STATE
    if SIMULATION_APP_STATE["running"] and SIMULATION_APP_STATE["paused"]:
        if sim_resume(SIMULATION_APP_STATE):
            return {"message": "Simulation resumed."}
    return {"message": "Simulation not paused or not running."}

@app.post("/reset")
async def reset_simulation_endpoint():
    global SIMULATION_APP_STATE
    if sim_reset(SIMULATION_APP_STATE, r): # Pass Redis client to scheduler for flushing
        return {"message": "Simulation reset."}
    return {"message": "Failed to reset simulation."}

@app.post("/orders")
def place_order_endpoint(o: Dict[str, Any]):
    # Add pre-order validation or escrow locking here if needed outside submit_order
    # For now, submit_order handles it.
    print(f"[API] Received order: {o}")
    match_result = submit_order(o["side"], o["leg_id"], float(o["price"]), int(o["qty"]), o["trader"])
    return {"match": match_result.model_dump(mode='json') if match_result else None}

@app.get("/orderbook/{leg_id}")
def get_orderbook_endpoint(leg_id: str):
    return snapshot_book(leg_id)

@app.get("/balances")
def get_balances_endpoint():
    return get_all_balances_from_redis()

@app.get("/current_owner")
def get_current_owner_endpoint():
    # Logic to determine current owner of "CONT" leg
    # This could check for the latest successful bid on CONT or a specific Redis key
    # For now, a placeholder. This should be updated by matching logic for CONT.
    owner = r.get("current_container_owner") # Assuming matching.py sets this key
    return {"current_owner": owner if owner else "N/A"}

# --- WebSocket Endpoint --- 
async def update_simulation_app_state():
    """Periodically updates SIMULATION_APP_STATE from scheduler's state."""
    global SIMULATION_APP_STATE
    while True:
        sch_state = sim_get_state() # Get state from scheduler.py
        SIMULATION_APP_STATE["clock"] = sch_state["clock"]
        SIMULATION_APP_STATE["running"] = sch_state["is_running"]
        SIMULATION_APP_STATE["paused"] = sch_state["is_paused"]
        await asyncio.sleep(0.5) # Update rate for app state polling

@app.on_event("startup")
async def on_startup():
    # Start the background task to poll scheduler state
    asyncio.create_task(update_simulation_app_state())
    # Initialize balances for known traders if they don't exist
    get_all_balances_from_redis() # Call once to ensure traders are in Redis
    print("[API] Application startup complete. Polling scheduler state.")

@app.websocket("/ws/{leg_id}") # Name changed to avoid conflict if any
async def websocket_endpoint_leg(ws: WebSocket, leg_id: str):
    await ws.accept()
    try:
        while True:
            current_balances = get_all_balances_from_redis()
            iot_progress_data = get_iot_progress_from_redis()
            current_owner = r.get("current_container_owner") or "N/A"
            
            data_to_send = {
                "orderbook": snapshot_book(leg_id),
                "matches": r.xrange(f"matches:{leg_id}", "-", "+", count=20), # More matches
                "iot_progress": iot_progress_data,
                "balances": current_balances,
                "simulation_clock": SIMULATION_APP_STATE["clock"],
                "is_running": SIMULATION_APP_STATE["running"],
                "is_paused": SIMULATION_APP_STATE["paused"],
                "current_owner": current_owner
            }
            await ws.send_text(json.dumps(data_to_send))
            await asyncio.sleep(1) # Send updates every 1 second
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for leg: {leg_id}")
    except Exception as e:
        print(f"ERROR in WebSocket for leg {leg_id}: {type(e).__name__} - {e}")
    finally:
        print(f"WebSocket for leg {leg_id} connection scope ended.")

print("[API] FastAPI app initialized.")


