import time
from apscheduler.schedulers.background import BackgroundScheduler
from threading import Thread, Event
from seed import schedule

# --- Global state for simulation control ---
_scheduler = None
_simulation_thread = None
_stop_event = Event() # Used to signal the simulation thread to stop/pause
_pause_event = Event() # Used to signal the simulation thread to pause

_sim_clock_seconds = 0
_is_running = False
_is_paused = False

def get_simulation_state():
    global _sim_clock_seconds, _is_running, _is_paused
    return {
        "clock": _sim_clock_seconds,
        "is_running": _is_running,
        "is_paused": _is_paused
    }

def _run_simulation_loop(seed_function):
    """Wrapper to run the seed_function and manage clock/pause/stop."""
    global _sim_clock_seconds, _is_running, _is_paused, _stop_event, _pause_event
    
    _is_running = True
    _is_paused = False
    _sim_clock_seconds = 0
    _stop_event.clear() 
    _pause_event.clear() # Ensure pause is not set initially

    print("[SCHEDULER] Simulation loop started.")
    start_time = time.time()
    
    # Pass events to the seed_function so it can check for pause/stop
    # This requires seed.schedule to be adapted.
    seed_function(_stop_event, _pause_event, _update_clock_from_seed)

    _is_running = False
    _is_paused = False # Reset pause state if stopped
    print(f"[SCHEDULER] Simulation loop finished. Final clock: {_sim_clock_seconds}")

def _update_clock_from_seed(seconds_elapsed):
    """Callback for seed.py to update the master clock."""
    global _sim_clock_seconds
    _sim_clock_seconds = int(seconds_elapsed)

def start_simulation(main_app_sim_state_ref):
    """Starts the simulation in a new thread."""
    global _simulation_thread, _is_running, _scheduler
    if _is_running:
        print("[SCHEDULER] Simulation already running.")
        return False

    # If using APScheduler for the main loop (less direct control for pause/resume of seed.py)
    # We are moving away from APScheduler for the main seed.py script to allow for better pause/resume
    # _scheduler = BackgroundScheduler()
    # _scheduler.add_job(lambda: _run_simulation_loop(schedule), trigger='date', id='simulation_job')
    # _scheduler.start()
    
    # Run the simulation loop in a separate thread for non-blocking behavior
    # Pass the original seed.schedule function
    _simulation_thread = Thread(target=_run_simulation_loop, args=(schedule,))
    _simulation_thread.daemon = True # Allow main program to exit even if thread is running
    _simulation_thread.start()
    main_app_sim_state_ref["running"] = True # Update main.py's state
    print("[SCHEDULER] Simulation thread initiated.")
    return True

def pause_simulation(main_app_sim_state_ref):
    global _is_paused, _pause_event
    if not _is_running or _is_paused:
        print(f"[SCHEDULER] Cannot pause. Running: {_is_running}, Paused: {_is_paused}")
        return False
    _is_paused = True
    _pause_event.set() # Signal the simulation thread to pause
    main_app_sim_state_ref["running"] = False # Or a new state like "paused"
    main_app_sim_state_ref["paused"] = True
    print("[SCHEDULER] Simulation paused.")
    return True

def resume_simulation(main_app_sim_state_ref):
    global _is_paused, _pause_event
    if not _is_running or not _is_paused:
        print(f"[SCHEDULER] Cannot resume. Running: {_is_running}, Paused: {_is_paused}")
        return False
    _is_paused = False
    _pause_event.clear() # Signal the simulation thread to resume
    main_app_sim_state_ref["running"] = True
    main_app_sim_state_ref["paused"] = False
    print("[SCHEDULER] Simulation resumed.")
    return True

def reset_simulation(main_app_sim_state_ref, redis_client):
    """Stops the current simulation, resets state, and clears relevant Redis data."""
    global _simulation_thread, _is_running, _is_paused, _sim_clock_seconds, _stop_event
    
    if _is_running:
        _stop_event.set() # Signal the thread to stop
        if _is_paused:
            _pause_event.clear() # If paused, need to unpause to allow it to see stop_event
        if _simulation_thread and _simulation_thread.is_alive():
            print("[SCHEDULER] Waiting for simulation thread to stop...")
            _simulation_thread.join(timeout=5) # Wait for the thread to finish
            if _simulation_thread.is_alive():
                print("[SCHEDULER] Warning: Simulation thread did not stop gracefully.")
    
    _is_running = False
    _is_paused = False
    _sim_clock_seconds = 0
    _simulation_thread = None
    _stop_event.clear()
    _pause_event.clear()

    main_app_sim_state_ref["running"] = False
    main_app_sim_state_ref["paused"] = False
    main_app_sim_state_ref["clock"] = 0

    # Clear Redis data (example keys, adjust as needed)
    print("[SCHEDULER] Flushing relevant Redis keys for reset...")
    keys_to_delete = []
    for key_pattern in ["bids:*", "asks:*", "matches:*", "orders:*", "iot", "escrow:*"]:
        keys_to_delete.extend(redis_client.keys(key_pattern))
    if keys_to_delete:
        redis_client.delete(*keys_to_delete)
        print(f"[SCHEDULER] Deleted {len(keys_to_delete)} keys from Redis.")
    else:
        print("[SCHEDULER] No relevant keys found in Redis to delete.")

    print("[SCHEDULER] Simulation reset complete. Ready to play.")
    return True

# The old start() is no longer directly used by main.py
# def start():
#     sched = BackgroundScheduler()
#     sched.add_job(schedule, trigger="date") # This was the one-time run
#     sched.start()
