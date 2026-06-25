# Agrino: ML-Powered Smart Irrigation Edge System

Agrino is an intelligent, hardware-driven embedded IoT solution designed to automate crop irrigation using machine learning. Shifting away from rigid timer-based systems or simplistic rule thresholds, Agrino analyzes real-time environmental interactions using a trained **XGBoost Regressor** model to accurately calculate irrigation requirements while maintaining an immediate localized safe fallback boundary.

---

## 🏗️ System Architecture

The core architecture operates over a multi-layered hardware-to-software pipeline:

1. **Physical Hardware Layer:** An embedded microcontroller (Arduino/compatible platform) tracks live microclimate variables via an array of sensors and triggers an electrical pump relay.
2. **Edge Ingestion & Processing Bridge (`bridgenew.py`):** A multi-threaded Python engine auto-detects the active microcontroller serial interface (`9600 Baud`). It ingests JSON packets, performs signal smoothing, coordinates inference, and appends rows to a CSV historical log file.
3. **Machine Learning Layer:** A high-performance **XGBoost Regressor** evaluates incoming scaled feature distributions to calculate continuous prediction risk coefficients ($y_{\text{pred}} \geq 0.5 \rightarrow \text{Irrigation Needed}$).
4. **Web Frontend Interface (`index.html`, `app.js`, `style.css`):** A custom botanical-themed real-time dashboard featuring live metrics, interactive telemetry charts via Chart.js, terminal monitoring streams, manual override toggles, and system historical log view tools.

---

## 🛠️ Data Handling & Technical Preprocessing

To comply with robust IoT signal ingestion criteria, data packets are processed in two sequential layers:
- **Step 1: Signal Smoothing (Moving Average Buffer):** Soil moisture inputs suffer from line noise and transient electrical fluctuations. The Python bridge applies a double-ended queue (`deque`) buffer to run a 5-sample rolling moving average to stabilize numbers before inferencing.
- **Step 2: Safety Envelope Validation:** Raw values are evaluated against physical limitations. If a sensor reports faulty metrics (e.g., `SENS ERR`), or if soil moisture plummets below a critical boundary ($<30\%$), the pipeline bypasses the ML model to engage immediate automated system safety indicators.

---

## 💻 Machine Learning Pipeline (`train.py`)

The pipeline trains an **XGBoost Regressor** on key variables down to optimized serialization formats:
- **Input Features:** `Temperature_C`, `Humidity`, and `Soil_Moisture`.
- **Target Optimization Model:** Supports raw numeric regression metrics or mapped categorical ordinal values (`low: 0.0`, `medium: 0.5`, `high: 1.0`).
- **XGBoost Hyperparameters:** 300 estimators, a maximum depth of 6, and a learning rate of 0.05.
- **Artifact Serialization:** Saves the fully optimized weights into `model_xgb.joblib` and scaling statistics into `scaler.joblib`.

---

## ⚙️ REST API Endpoint Specifications

The bridge runs on an asynchronous FastAPI server (`0.0.0.0:8001`) with the following operational endpoints:

### `GET /latest`
Fetches the current real-time structural snapshot data dictionary map.
```json
{
  "Temperature": 28.5,
  "Humidity": 64.0,
  "Soil_Moisture": 45.0,
  "Soil_Moisture_Smoothed": 45.2,
  "Light": 720,
  "Pump": false,
  "Scenario": "SYSTEM OK",
  "irrigation_prediction": 0.2314,
  "irrigation_recommended": false,
  "baseline_triggered": false,
  "ml_baseline_disagree": false,
  "model_used": "XGBoost Regressor v1.0",
  "timestamp": "2026-06-25T23:45:00.123456",
  "status": "ok",
  "manual_override": false,
  "manual_pump_state": false
}
```

### `POST /control`
Dispatches remote administrator manual overrides to control physical operational modes.

```json
{"manual_override": true, "manual_pump_state": true}
```

### `GET /view-log`
Returns the final 100 structured telemetry historical array rows from the local CSV sheet to render tables in the UI modal window.

### `GET /download-log`
Packages and download the full local `sensor_history_log.csv` file directly onto the administrator's computer.

### `GET /health`
Returns the server running status and the currently selected serial COM port interface.

## 🚀 Execution & Deployment Instructions

**Prerequisites**

Ensure your local environment runs Python 3.8+ with standard package managers.

**1. Installation**

Navigate into your system root repository folder and install dependencies using Command Prompt (cmd) or PowerShell:

`pip install fastapi uvicorn pyserial joblib scikit-learn xgboost pandas requests`

**2. Machine Learning Training Initialization**

To generate fresh serialized model configurations and check performance improvements against standard baseline logic, run:

`python train.py`

**3. Running Agrino Edge Services**

Because the system splits ingestion tasks and visualization serving into two parallel systems, open two separate terminal windows:

**Terminal A: The Core Processing Engine**

Start the Python Serial Ingestion Bridge and FastAPI backend services:

`python bridgenew.py`

_Keep this terminal running to monitor the live telemetry data matrix._

**2. Terminal B. The Frontend Application Server**

Spin up the local web service gateway to host the interface:

`python -m http.server 3000`

_Open your favorite web browser and navigate to the application ocnsole:_

```Plaintext
http://localhost:3000
```

## 👥 System Developers

**Course Project:** SAIA 3353 Machine Learning for IoT
- Areesha Hilmi, Asyura Anwar, Faqihah Firhat, Shirlyn Siew, Nadsyuha Mustafa, Wajeeha Hizam