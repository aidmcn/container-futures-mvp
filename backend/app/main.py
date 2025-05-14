import uuid, json, os, asyncio
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis

# Updated imports from our modules
from matching import submit_order, snapshot_book, get_trader_balance, adjust_trader_balance, lock_funds, release_funds_for_leg, get_order_details, finalize_leg_freight_settlement
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
    if not SIMULATION_APP_STATE["running"]:
        # Return a very basic initial state for known traders when simulation is stopped
        # This helps ensure the UI shows a clean slate after reset and before play.
        initial_balances = {}
        traders_to_show_initially = [SHIPPER_A_ID, MM_TRADER_ID, PLATFORM_TRADER_ID] + CARRIERS + OTHER_BIDDERS
        for trader in traders_to_show_initially:
            initial_balances[trader] = {"balance": 0.00, "locked": 0.00}
        return initial_balances
    
    balances = {}
    # Ensure all known traders are in the list for consistent UI display
    traders_involved = [SHIPPER_A_ID, MM_TRADER_ID, PLATFORM_TRADER_ID] + CARRIERS + OTHER_BIDDERS
    for trader_name in traders_involved:
        key = _escrow_key(trader_name)
        if not r.exists(key): # Initialize if created by seed but then flushed
            r.hmset(key, {"balance": "0", "locked": "0"})
        balance_data = r.hgetall(key)
        balances[trader_name] = {
            "balance": float(balance_data.get("balance", 0)),
            "locked": float(balance_data.get("locked", 0))
        }
    return balances

def get_iot_progress_from_redis():
    if not SIMULATION_APP_STATE["running"]:
        # Return initial IoT progress if simulation is stopped
        initial_iot_progress = {}
        base_legs = [LEG_L1, LEG_L2, LEG_L3] # Base leg IDs
        for leg in base_legs:
            initial_iot_progress[leg] = {"percentage": 0, "status": "Pending"}
        return initial_iot_progress
    
    # ... (existing logic for get_iot_progress_from_redis when running - as previously accepted) ...
    # This logic uses SIMULATION_APP_STATE["clock"] and Redis data like leg_meta and iot stream
    iot_progress = {}
    contract_id_for_demo = CONTRACT_ID 
    legs_for_timeline_display = [LEG_L1, LEG_L2, LEG_L3] # Base leg IDs for UI keys
    
    iot_events_raw = r.xrevrange("iot", "+", "-", count=100) 
    delivered_legs_for_contract = set()
    for _msg_id, event_fields in iot_events_raw:
        ev_contract_id = event_fields.get("container_contract_id")
        ev_leg_id_base = event_fields.get("leg_id") 
        if ev_contract_id == contract_id_for_demo and event_fields.get("status") == "DELIVERED_FINAL_LEG":
            full_leg_id_db = f"{ev_leg_id_base}_{ev_contract_id}" # e.g. L1_C1
            delivered_legs_for_contract.add(ev_leg_id_base) # Store base leg ID
            leg_meta_status = r.hget(f"leg_meta:{full_leg_id_db}", "status")
            if leg_meta_status == "DELIVERED":
                print(f"[MAIN_IOT_PROCESS] Detected delivered IoT for {full_leg_id_db}, attempting final settlement.")
                finalize_leg_freight_settlement(ev_leg_id_base, ev_contract_id)
            
    sim_clock_seconds = SIMULATION_APP_STATE["clock"]

    for base_leg_id in legs_for_timeline_display: 
        full_leg_id_db_format = f"{base_leg_id}_{contract_id_for_demo}"
        if base_leg_id in delivered_legs_for_contract:
            iot_progress[base_leg_id] = {"percentage": 100, "status": "Delivered"}
        else:
            leg_meta_data = r.hgetall(f"leg_meta:{full_leg_id_db_format}")
            start_sim_time_s_str = leg_meta_data.get("start_sim_time_s") 
            eta_duration_s_str = leg_meta_data.get("eta_duration_s")
            if start_sim_time_s_str and eta_duration_s_str:
                start_sim_time_s = int(start_sim_time_s_str)
                eta_duration_s = int(eta_duration_s_str)
                if sim_clock_seconds >= start_sim_time_s and eta_duration_s > 0:
                    elapsed_on_leg = sim_clock_seconds - start_sim_time_s
                    percentage = min(100.0, (elapsed_on_leg / eta_duration_s) * 100.0)
                    current_status = "In Transit"
                    if percentage >= 100:
                        current_status = "Arrived (Pending IoT)" 
                    iot_progress[base_leg_id] = {"percentage": percentage, "status": current_status}
                else:
                    iot_progress[base_leg_id] = {"percentage": 0, "status": "Pending"}
            else:
                iot_progress[base_leg_id] = {"percentage": 0, "status": "Pending"}
    return iot_progress

# --- Escrow and Ownership (called by matching.py and seed.py/scheduler) ---
# This is a conceptual placement. Escrow logic is now primarily in matching.py

# --- API Endpoints ---
@app.post("/play")
async def play_simulation():
    global SIMULATION_APP_STATE
    print("[API /play] Received request. Current state:", SIMULATION_APP_STATE)
    # Pass a copy or be careful if sim_start modifies it directly before status is confirmed
    if sim_start(SIMULATION_APP_STATE): 
        # SIMULATION_APP_STATE should be updated by sim_start to set running=True
        print("[API /play] sim_start call successful. New state expected:", SIMULATION_APP_STATE)
        return {"message": "Simulation started/resumed."}
    else:
        print("[API /play] sim_start call failed or simulation already running. State:", SIMULATION_APP_STATE)
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

@app.get("/current_owner/{contract_id}")
def get_current_owner_endpoint(contract_id: str):
    owner = r.hget(_container_contract_key(contract_id), "current_owner_id")
    return {"current_owner": owner if owner else "N/A", "contract_id": contract_id}

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

@app.websocket("/ws/{book_id_ws_param}")
async def websocket_endpoint_generic_book(ws: WebSocket, book_id_ws_param: str):
    await ws.accept()
    print(f"[WS_CONNECT] Accepted connection for book: {book_id_ws_param}, client: {ws.client}")
    
    is_contract_book_ws = book_id_ws_param.startswith("contract:")
    contract_id_context = book_id_ws_param.split(':')[-1] if is_contract_book_ws else book_id_ws_param.split('_')[-1]
    if not contract_id_context: 
        contract_id_context = "C1" # Fallback for demo, should ideally not be needed
        print(f"[WS_WARN] contract_id_context fell back to C1 for book_id: {book_id_ws_param}")

    try:
        while True:
            # If simulation is not running, send a minimal, clean state
            if not SIMULATION_APP_STATE["running"] and SIMULATION_APP_STATE["clock"] == 0:
                # This state is for when reset has occurred and play hasn't been pressed yet
                snapshot_data = {"bids": [], "asks": []}
                matches_data = []
                iot_data = get_iot_progress_from_redis() # Will return initial pending state
                balance_data = get_all_balances_from_redis() # Will return initial zeroed state
                owner = "N/A"
                status = "UNKNOWN"
            else:
                # Simulation is running or has run, fetch live/last data from Redis
                snapshot_data = snapshot_book(book_id_ws_param)
                matches_data = r.xrange(f"matches:{book_id_ws_param}", "-", "+", count=20)
                iot_data = get_iot_progress_from_redis()
                balance_data = get_all_balances_from_redis()
                contract_details_dict = r.hgetall(_container_contract_key(contract_id_context)) # Define contract_id_context as before
                owner = contract_details_dict.get("current_owner_id", "N/A")
                status = contract_details_dict.get("status", "UNKNOWN")

            data_to_send = {
                "book_id": book_id_ws_param,
                "orderbook": snapshot_data,
                "matches": matches_data,
                "iot_progress": iot_data,
                "balances": balance_data,
                "simulation_clock": SIMULATION_APP_STATE["clock"],
                "is_running": SIMULATION_APP_STATE["running"],
                "is_paused": SIMULATION_APP_STATE["paused"],
                "current_container_owner": owner,
                "container_status": status
            }
            await ws.send_text(json.dumps(data_to_send))
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        print(f"[WS_DISCONNECT] WebSocket disconnected for book: {book_id_ws_param} (client closed gracefully)")
    except Exception as e:
        import traceback
        print(f"[WS_UNHANDLED_ERROR] Unhandled error in WebSocket for book {book_id_ws_param}: {type(e).__name__} - {e}\n{traceback.format_exc()}")
    finally:
        print(f"[WS_CLOSE] WebSocket scope ended for book: {book_id_ws_param}.")

# Need to import _container_contract_key from matching or define locally if used
# from matching import _container_contract_key is problematic due to potential circular imports
# Better to define key functions in a shared utils or directly here if simple.

def _container_contract_key(contract_id: str) -> str: # Duplicated for direct use
    return f"container_contract:{contract_id}"

# Ensure CONTRACT_ID, SHIPPER_A_ID, etc. and _escrow_key are available if not imported
# These might need to be defined or imported from seed/matching if not already present globally in main.py
CONTRACT_ID = "C1" 
SHIPPER_A_ID = "ShipperA"
MM_TRADER_ID = "MarketMaker1"
PLATFORM_TRADER_ID = "Platform"
CARRIERS = ["Maersk", "Evergreen", "COSCO", "MSC", "Hapag"]
OTHER_BIDDERS = ["CheapLtd", "FastPLC", "WealthyCorp"]
LEG_L1 = "L1"
LEG_L2 = "L2"
LEG_L3 = "L3"

def _escrow_key(trader_id: str) -> str: return f"escrow:{trader_id}" # Local def for main

print("[API] FastAPI app initialized.")


