import json
import threading
import time
from datetime import datetime

import joblib
import numpy as np
import serial
from fastapi import FastAPI
import uvicorn

# ── CONFIGURATION ──────────────────────────────────────────────────────
SERIAL_PORT   = "COM7"          # Confirmed from Device Manager
BAUD_RATE     = 9600            # Must match Serial.begin(9600) in Arduino firmware
MODEL_PATH    = "model_xgb.joblib"
SCALER_PATH   = "scaler.joblib"
OUTPUT_FILE   = "latest_reading.json"   # Streamlit / any file-based dashboard reads this
API_HOST      = "0.0.0.0"
API_PORT      = 8001            # Different port from old FastAPI (8000) to avoid clashes

# ── LOAD TRAINED MODEL + SCALER (same artefacts as Project 1) ──────────
print("[INFO] Loading model and scaler...")
model  = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)
print("[INFO] Model and scaler loaded successfully.")

# ── SHARED STATE ────────────────────────────────────────────────────────
# This dictionary holds the most recent reading + prediction.
# Both the file-writer and the API read from this same object.
latest_data = {
    "Temperature": None,
    "Humidity": None,
    "Soil_Moisture": None,
    "Light": None,
    "Pump": None,
    "Scenario": None,
    "irrigation_prediction": None,
    "irrigation_recommended": None,
    "baseline_triggered": None,
    "model_used": "XGBoost Regressor v1.0",
    "timestamp": None,
    "status": "waiting_for_data"
}
data_lock = threading.Lock()  # Prevents file/API reading while serial thread is writing


# ── INFERENCE FUNCTION (mirrors app.py's /predict logic exactly) ──────
def run_inference(temperature, humidity, soil_moisture):
    """
    Takes raw sensor values (already 0-100 scale) and returns the same
    prediction structure as the original FastAPI /predict endpoint.
    """
    X = np.array([[temperature, humidity, soil_moisture]])
    X_scaled = scaler.transform(X)
    prediction = float(model.predict(X_scaled)[0])

    irrigation_recommended = prediction >= 0.5
    baseline_triggered = soil_moisture < 30

    return {
        "irrigation_prediction": round(prediction, 4),
        "irrigation_recommended": irrigation_recommended,
        "baseline_triggered": baseline_triggered,
    }


# ── WRITE LATEST DATA TO FILE ──────────────────────────────────────────
def write_output_file():
    with data_lock:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(latest_data, f, indent=2)


# ── SERIAL READING LOOP (runs in background thread) ────────────────────
def serial_loop():
    print(f"[INFO] Opening serial port {SERIAL_PORT} at {BAUD_RATE} baud...")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    except Exception as e:
        print(f"[ERROR] Could not open {SERIAL_PORT}: {e}")
        print("[ERROR] Check that the Arduino is plugged in and COM7 is correct.")
        return

    time.sleep(2)  # Allow Arduino to reset after serial connection opens
    print("[INFO] Serial connection established. Listening for data...")

    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Parse the JSON line sent by the Arduino firmware
            sensor_data = json.loads(line)

            temperature   = sensor_data.get("Temperature_C")
            humidity      = sensor_data.get("Humidity")
            soil_moisture = sensor_data.get("Soil_Moisture")
            light         = sensor_data.get("Light")
            pump          = sensor_data.get("Pump")
            scenario      = sensor_data.get("Scenario")

            # Skip incomplete readings instead of crashing
            if temperature is None or humidity is None or soil_moisture is None:
                print(f"[WARN] Incomplete reading, skipping: {line}")
                continue

            # Run ML inference using the same logic as Project 1's app.py
            result = run_inference(temperature, humidity, soil_moisture)

            # Update shared state safely
            with data_lock:
                latest_data["Temperature"]   = temperature
                latest_data["Humidity"]      = humidity
                latest_data["Soil_Moisture"] = soil_moisture
                latest_data["Light"]         = light
                latest_data["Pump"]          = pump
                latest_data["Scenario"]      = scenario
                latest_data["irrigation_prediction"]  = result["irrigation_prediction"]
                latest_data["irrigation_recommended"] = result["irrigation_recommended"]
                latest_data["baseline_triggered"]     = result["baseline_triggered"]
                latest_data["timestamp"] = datetime.now().isoformat()
                latest_data["status"] = "ok"

            write_output_file()

            print(
                f"[DATA] T={temperature:.1f}  H={humidity:.1f}  SM={soil_moisture:.1f}  "
                f"-> pred={result['irrigation_prediction']:.4f}  "
                f"recommended={result['irrigation_recommended']}"
            )

        except json.JSONDecodeError:
            print(f"[WARN] Could not parse line as JSON: {line}")
        except Exception as e:
            print(f"[ERROR] Unexpected error in serial loop: {e}")
            time.sleep(1)


# ── REST API (for Flutter or any HTTP-based dashboard) ─────────────────
app = FastAPI(
    title="Smart Agriculture - Live Sensor Bridge",
    description="Serves the latest Arduino sensor reading and ML prediction.",
)


@app.get("/latest")
def get_latest_reading():
    """Returns the most recent sensor reading and irrigation prediction."""
    with data_lock:
        return dict(latest_data)


@app.get("/health")
def health_check():
    """Simple liveness check for the bridge script itself."""
    return {"status": "running", "serial_port": SERIAL_PORT}


# ── MAIN ENTRY POINT ────────────────────────────────────────────────────
if __name__ == "__main__":
    # Start the serial reading loop in a background thread so the API
    # can run at the same time in the main thread.
    serial_thread = threading.Thread(target=serial_loop, daemon=True)
    serial_thread.start()

    print(f"[INFO] Starting API server at http://localhost:{API_PORT}/latest")
    print(f"[INFO] Writing live data to: {OUTPUT_FILE}")
    print("[INFO] Press CTRL+C to stop.")

    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")