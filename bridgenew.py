import json
import threading
import time
import os
import csv
import logging
from collections import deque
from datetime import datetime

import joblib
import numpy as np
import serial
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── CONFIGURATION ──────────────────────────────────────────────────────
SERIAL_PORT   = "/dev/cu.usbserial-120"          
BAUD_RATE     = 9600
MODEL_PATH    = "model_xgb.joblib"
SCALER_PATH   = "scaler.joblib"
OUTPUT_FILE   = "latest_reading.json"
CSV_LOG_FILE  = "sensor_history_log.csv"
ERROR_LOG     = "errors.log"
API_HOST      = "0.0.0.0"
API_PORT      = 8001

# Preprocessing
SMOOTHING_WINDOW = 5        # moving-average window for soil moisture

# ── ERROR LOGGING (keeps the live matrix clean, but nothing is hidden) ──
logging.basicConfig(
    filename=ERROR_LOG,
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

# ── LOAD TRAINED MODEL + SCALER ────────────────────────────────────────
print("[INFO] Loading model and scaler...")
model  = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)
print("[INFO] Model and scaler loaded successfully.")

# ── SHARED STATE ────────────────────────────────────────────────────────
latest_data = {
    "Temperature": None,
    "Humidity": None,
    "Soil_Moisture": None,
    "Soil_Moisture_Smoothed": None,
    "Light": None,
    "Pump": None,
    "Scenario": None,
    "irrigation_prediction": None,
    "irrigation_recommended": None,
    "baseline_triggered": None,
    "ml_baseline_disagree": None,
    "model_used": "XGBoost Regressor v1.0",
    "timestamp": None,
    "status": "waiting_for_data",
}
data_lock = threading.Lock()

# Moving-average buffer
moisture_window = deque(maxlen=SMOOTHING_WINDOW)

# ── INITIALIZE CSV LOG FILE ────────────────────────────────────────────
def init_csv_file():
    """Creates the CSV file with headers if it does not already exist."""
    if not os.path.exists(CSV_LOG_FILE):
        headers = [
            "Timestamp", "Temperature_C", "Humidity_Pct",
            "Soil_Moisture_Raw_Pct", "Soil_Moisture_Smoothed_Pct",
            "Light_Val", "Pump_State", "Scenario", "ML_Prediction_Score",
            "ML_Irrigation_Recommended", "Baseline_Triggered", "ML_Baseline_Disagree",
        ]
        with open(CSV_LOG_FILE, mode="w", newline="") as f:
            csv.writer(f).writerow(headers)
        print(f"[INFO] Initialized new CSV log storage: {CSV_LOG_FILE}")

# ── LOG DATA TO CSV ────────────────────────────────────────────────────
def log_to_csv(temp, hum, moisture_raw, moisture_smoothed, light, pump, scenario, result):
    """Appends a single structured telemetry row to the CSV file."""
    try:
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            temp, hum, moisture_raw, round(moisture_smoothed, 2),
            light, pump, scenario,
            result["irrigation_prediction"],
            result["irrigation_recommended"],
            result["baseline_triggered"],
            result["ml_baseline_disagree"],
        ]
        with open(CSV_LOG_FILE, mode="a", newline="") as f:   
            csv.writer(f).writerow(row)
    except Exception as e:
        logging.warning(f"CSV write failed: {e}")

# ── PRINT LIVE FEED MATRIX ─────────────────────────────────────────────
def print_live_feed_matrix(temp, hum, moisture_raw, moisture_smoothed,
                           light, pump, scenario, result, alert_str, status_str="ONLINE"):
    """Clears the screen and draws the live telemetry matrix."""
    os.system('cls' if os.name == 'nt' else 'clear')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    disagree = "** ML vs RULE DISAGREE **" if result["ml_baseline_disagree"] else "agree"

    print("┌──────────────────────────────────────────────────────────────┐")
    print("│         SMART AGRICULTURE SYSTEMS INTEGRATION MATRIX          │")
    print(f"│  Time: {timestamp:<21} Status: {status_str:<24} │")
    print("├──────────────────────────────┬───────────────────────────────┤")
    print("│      ENVIRONMENT SENSORS     │       SYSTEM INFERENCE        │")
    print("├──────────────────────────────┼───────────────────────────────┤")
    print(f"│ Temperature   : {temp:<5} °C   │ ML Pred Score : {result['irrigation_prediction']:<13.4f} │")
    print(f"│ Humidity      : {hum:<5} %    │ ML Irrigation : {str(result['irrigation_recommended']):<13} │")
    print(f"│ Moist (raw)   : {moisture_raw:<5} %    │ Rule Baseline : {str(result['baseline_triggered']):<13} │")
    print(f"│ Moist (smooth): {moisture_smoothed:<5.1f} %    │ Agreement     : {disagree:<13} │")
    print(f"│ Light Level   : {str(light):<13}│ Valve Action  : {str(pump):<13} │")
    print("├──────────────────────────────┴───────────────────────────────┤")
    print("│                      LIVE SYSTEM LOGIC                       │")
    print("├──────────────────────────────────────────────────────────────┤")
    print(f"│ Scenario      : {str(scenario):<44} │")
    print(f"│ System Alert  : {alert_str:<44} │")
    print("└──────────────────────────────────────────────────────────────┘")
    print(f"[INFO] Local CSV backup active: {CSV_LOG_FILE}   Errors -> {ERROR_LOG}")

# ── INFERENCE FUNCTION ─────────────────────────────────────────────────
def run_inference(temperature, humidity, soil_moisture_smoothed, soil_moisture_raw):
    """Runs the model on smoothed features and compares against the naive baseline."""
    X = np.array([[temperature, humidity, soil_moisture_smoothed]])
    X_scaled = scaler.transform(X)                       
    prediction = float(model.predict(X_scaled)[0])

    irrigation_recommended = prediction >= 0.5
    baseline_triggered = soil_moisture_raw < 30          

    return {
        "irrigation_prediction": round(prediction, 4),
        "irrigation_recommended": irrigation_recommended,
        "baseline_triggered": baseline_triggered,
        "ml_baseline_disagree": irrigation_recommended != baseline_triggered,
    }

# ── WRITE LATEST DATA TO FILE ──────────────────────────────────────────
def write_output_file():
    with data_lock:
        snapshot = dict(latest_data)
    try:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(snapshot, f, indent=2)
    except Exception as e:
        logging.warning(f"JSON write failed: {e}")

# ── UPDATE STATE ON LOCAL FAULT ────────────────────────────────────────
def set_fault_state(error_msg):
    """Updates the internal state representation to declare a system fault."""
    with data_lock:
        latest_data.update({
            "status": "fault",
            "Scenario": "SYSTEM FAULT",
            "Pump": False,
            "irrigation_recommended": False
        })
    write_output_file()
    
    # Render a simplified fault panel directly to the local terminal
    os.system('cls' if os.name == 'nt' else 'clear')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("┌──────────────────────────────────────────────────────────────┐")
    print("│         SMART AGRICULTURE SYSTEMS INTEGRATION MATRIX          │")
    print(f"│  Time: {timestamp:<21} Status: SYSTEM FAULT             │")
    print("├──────────────────────────────────────────────────────────────┤")
    print(f"│  CRITICAL ERROR: {error_msg:<43} │")
    print("└──────────────────────────────────────────────────────────────┘")


def serial_loop():
    init_csv_file()

    while True:
        print(f"[INFO] Attempting to open serial port {SERIAL_PORT}...")
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            time.sleep(2)  
            print("[INFO] Serial connection established. Syncing matrix...")
        except Exception as conn_err:
            print(f"[CRITICAL] Unable to open {SERIAL_PORT}: {conn_err}")
            logging.warning(f"Serial open failed: {conn_err}")
            set_fault_state("SERIAL PORT REJECTED / DISCONNECTED")
            time.sleep(5)  
            continue

        # Inner loop: active data reading frame
        while True:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                sensor_data = json.loads(line)

                temperature   = sensor_data.get("Temperature_C")
                humidity      = sensor_data.get("Humidity")
                soil_moisture = sensor_data.get("Soil_Moisture")
                light         = sensor_data.get("Light")
                pump          = sensor_data.get("Pump")
                scenario      = sensor_data.get("Scenario")

                if temperature is None or humidity is None or soil_moisture is None:
                    logging.warning(f"Incomplete reading skipped: {line}")
                    continue

                # Preprocessing step 1: moving-average smoothing 
                moisture_window.append(soil_moisture)
                soil_moisture_smoothed = sum(moisture_window) / len(moisture_window)

                result = run_inference(
                    temperature, humidity, soil_moisture_smoothed, soil_moisture
                )

                with data_lock:
                    latest_data.update({
                        "Temperature": temperature,
                        "Humidity": humidity,
                        "Soil_Moisture": soil_moisture,
                        "Soil_Moisture_Smoothed": round(soil_moisture_smoothed, 2),
                        "Light": light,
                        "Pump": pump,
                        "Scenario": scenario,
                        "irrigation_prediction": result["irrigation_prediction"],
                        "irrigation_recommended": result["irrigation_recommended"],
                        "baseline_triggered": result["baseline_triggered"],
                        "ml_baseline_disagree": result["ml_baseline_disagree"],
                        "timestamp": datetime.now().isoformat(),
                        "status": "ok",
                    })

                write_output_file()

                if soil_moisture < 30:
                    logic_alert_str = "CRITICAL DRY"
                elif result["irrigation_recommended"]:
                    logic_alert_str = "ML IRRIGATION ACTIVE"
                else:
                    logic_alert_str = "SYSTEM OK"

                # 1. Output Live matrix visualization directly to terminal screen
                print_live_feed_matrix(
                    temperature, humidity, soil_moisture, soil_moisture_smoothed,
                    light, pump, scenario, result, logic_alert_str, status_str="ONLINE"
                )

                # 2. Append state results into your local CSV backup log
                log_to_csv(
                    temperature, humidity, soil_moisture, soil_moisture_smoothed,
                    light, pump, scenario, result
                )

            except (serial.SerialException, OSError) as hardware_disconnect:
                print("\n[CRITICAL] USB hardware disconnected mid-stream!")
                logging.warning(f"Hardware disconnect: {hardware_disconnect}")
                set_fault_state("USB WIRE UNPLUGGED DETECTED")
                try:
                    ser.close()
                except Exception:
                    pass
                break  

            except json.JSONDecodeError:
                logging.warning(f"Could not parse line as JSON: {line}")
            except Exception as loop_err:
                logging.warning(f"Unexpected loop error: {loop_err}")
                time.sleep(1)

# ── REST API (Exposes endpoints for custom UI folder extraction widgets) ──
app = FastAPI(title="Smart Agriculture - Live Sensor Bridge")

# CORS middleware activation block
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/latest")
def get_latest_reading():
    with data_lock:
        return dict(latest_data)

@app.get("/health")
def health_check():
    return {"status": "running", "serial_port": SERIAL_PORT}

@app.get("/download-log")
def download_log_file():
    if os.path.exists(CSV_LOG_FILE):
        return FileResponse(CSV_LOG_FILE, media_type='text/csv', filename="agriculture_telemetry_history.csv")
    return {"error": "Log file not generated yet. Awaiting initial hardware transmission stream."}

@app.get("/view-log")
def view_log_file():
    if not os.path.exists(CSV_LOG_FILE):
        return {"error": "Log file not generated yet.", "rows": [], "headers": []}
    try:
        with open(CSV_LOG_FILE, "r") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            rows = list(reader)[-100:]
        return {"headers": headers, "rows": rows}
    except Exception as e:
        return {"error": str(e), "rows": [], "headers": []}

# ── EXECUTION ENTRY POINT ───────────────────────────────────────────────
if __name__ == "__main__":
    serial_thread = threading.Thread(target=serial_loop, daemon=True)
    serial_thread.start()
    print("[INFO] Starting background sub-systems...")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="error")