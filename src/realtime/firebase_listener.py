# FILE: src/realtime/firebase_listener.py
"""Background thread: polls Firebase Realtime Database and updates global state."""
import threading
import time
from collections import deque
from pathlib import Path
import sys
import os
import requests
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.iot import IoTAdapter

# Firebase Configuration
FIREBASE_URL = "https://synapse-60115-default-rtdb.firebaseio.com"

# Try multiple common paths (priority order)
FIREBASE_PATHS_TO_TRY = [
    os.getenv("FIREBASE_READINGS_PATH", "/sensor_readings/latest.json"),  # من ENV أول حاجة
    "/sensor_readings/latest.json",  # Nested structure
    "/latest.json",                   # Flat at root level
    "/.json",                         # Entire database root
]

# Global shared state (thread-safe with lock)
_latest_reading_lock = threading.Lock()
_latest_reading = None
_sensor_buffer = deque(maxlen=1800)  # آخر 30 دقيقة بمعدل 1 Hz


def get_latest_reading():
    """Thread-safe getter for the most recent sensor reading."""
    with _latest_reading_lock:
        return _latest_reading


def get_sensor_buffer():
    """Thread-safe getter for the rolling sensor buffer."""
    with _latest_reading_lock:
        return list(_sensor_buffer)


def _extract_sensor_data(data):
    """Extract sensor reading from various Firebase structures.
    
    Handles:
    - Flat object: {"pressure": 2.4, "flow": 12.0, ...}
    - Nested: {"sensor_readings": {"latest": {...}}}
    - Array: [{"timestamp": "...", ...}, ...]  (picks last)
    """
    if data is None:
        return None
    
    # Scenario 1: Direct object with sensor fields
    if isinstance(data, dict) and "pressure" in data:
        return data
    
    # Scenario 2: Nested under known keys
    for key in ["sensor_readings", "latest", "data", "reading"]:
        if isinstance(data, dict) and key in data:
            nested = data[key]
            if isinstance(nested, dict):
                # Check if this level has sensor data
                if "pressure" in nested:
                    return nested
                # Try one more level
                for subkey in ["latest", "current", "data"]:
                    if subkey in nested and isinstance(nested[subkey], dict):
                        if "pressure" in nested[subkey]:
                            return nested[subkey]
    
    # Scenario 3: Array of readings (pick last)
    if isinstance(data, list) and len(data) > 0:
        return data[-1]
    
    return None


def start_firebase_listener(poll_interval: float = 1.0):
    """Start background thread polling Firebase Realtime Database.
    
    Args:
        poll_interval: Seconds between each Firebase query (default 1.0 Hz)
    """
    adapter = IoTAdapter(default_pump_id="pump-001", default_run_id="live_hardware")
    
    # Auto-detect working path
    working_path = None
    for path in FIREBASE_PATHS_TO_TRY:
        endpoint = f"{FIREBASE_URL}{path}"
        try:
            response = requests.get(endpoint, timeout=3)
            if response.status_code == 200:
                data = response.json()
                extracted = _extract_sensor_data(data)
                if extracted and "pressure" in extracted:
                    working_path = path
                    print(f"✅ Auto-detected Firebase path: {path}")
                    break
        except:
            continue
    
    if not working_path:
        print("⚠️ WARNING: Could not auto-detect Firebase sensor data path.")
        print("   Set FIREBASE_READINGS_PATH environment variable to the correct path.")
        working_path = FIREBASE_PATHS_TO_TRY[0]  # Fallback
    
    firebase_endpoint = f"{FIREBASE_URL}{working_path}"

    def _poll():
        print(f"✅ Firebase listener started: {firebase_endpoint}")
        print(f"   Polling every {poll_interval}s")
        
        last_timestamp = None
        consecutive_errors = 0
        
        while True:
            try:
                response = requests.get(firebase_endpoint, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data is None:
                        time.sleep(poll_interval)
                        continue
                    
                    # Extract sensor data from whatever structure Firebase returns
                    sensor_data = _extract_sensor_data(data)
                    
                    if sensor_data is None:
                        if consecutive_errors == 0:  # Print only once
                            print(f"⚠️ Could not extract sensor data from Firebase response")
                            print(f"   Received structure: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        consecutive_errors += 1
                        time.sleep(poll_interval)
                        continue
                    
                    # Check for new reading
                    current_timestamp = sensor_data.get("timestamp")
                    if current_timestamp == last_timestamp:
                        time.sleep(poll_interval)
                        continue
                    
                    last_timestamp = current_timestamp
                    consecutive_errors = 0  # Reset error counter
                    
                    # Parse through IoTAdapter
                    record, issues = adapter.ingest_payload(sensor_data)
                    
                    # Update global state
                    with _latest_reading_lock:
                        global _latest_reading, _sensor_buffer
                        _latest_reading = {
                            "timestamp": record.timestamp.isoformat(),
                            "pressure": record.pressure,
                            "flow": record.flow,
                            "temperature": record.temperature,
                            "vibration": record.vibration,
                            "motor_current": record.motor_current,
                            "operating_load": record.operating_load,
                            "operating_regime": record.operating_regime,
                            "pump_state": record.pump_state,
                        }
                        _sensor_buffer.append(_latest_reading)
                    
                    if issues:
                        print(f"⚠️ Validation issues: {issues}")
                
                else:
                    print(f"⚠️ Firebase returned status {response.status_code}")
                    consecutive_errors += 1
                
            except requests.exceptions.RequestException as e:
                if consecutive_errors < 3:  # Print first 3 errors only
                    print(f"⚠️ Firebase connection error: {e}")
                consecutive_errors += 1
            except Exception as e:
                if consecutive_errors < 3:
                    print(f"⚠️ Unexpected error: {e}")
                consecutive_errors += 1
            
            # Exponential backoff on repeated errors
            sleep_time = poll_interval if consecutive_errors < 5 else min(poll_interval * 2, 5.0)
            time.sleep(sleep_time)

    thread = threading.Thread(target=_poll, daemon=True)
    thread.start()