import os
import time
import logging
import numpy as np
import joblib

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Paths (override via environment variables for Docker / cloud deployment)
MODEL_PATH  = os.getenv("MODEL_PATH",  "model_xgb.joblib")
SCALER_PATH = os.getenv("SCALER_PATH", "scaler.joblib")

# Load artefacts once at startup
try:
    model  = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    log.info("Model  loaded ← %s", MODEL_PATH)
    log.info("Scaler loaded ← %s", SCALER_PATH)
except FileNotFoundError as exc:
    log.critical("Artefact missing: %s  →  run train.py first.", exc.filename)
    raise SystemExit(1) from exc

# App
app = FastAPI(
    title       = "Smart Agriculture – Irrigation Prediction API",
    description = (
        "Predicts irrigation need from Temperature, Humidity, "
        "and Soil_Moisture sensor readings sent by Node-RED."
    ),
    version = "1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Schemas

class SensorReading(BaseModel):
    """
    Exact JSON format expected from Student A's Node-RED flow.
    Note: the model was trained with Temperature_C renamed to Temperature.
    """
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "Temperature":   28.5,
                    "Humidity":      65.0,
                    "Soil_Moisture": 22.3,
                }
            ]
        }
    }
 
    Temperature:   float = Field(..., description="Air temperature (°C)")
    Humidity:      float = Field(..., description="Relative humidity (%)")
    Soil_Moisture: float = Field(..., description="Soil moisture (%)")
 
    @model_validator(mode="after")
    def validate_ranges(self):
        if not (-50 <= self.Temperature <= 70):
            raise ValueError(f"Temperature {self.Temperature} outside plausible range (−50 to 70 °C).")
        if not (0 <= self.Humidity <= 100):
            raise ValueError(f"Humidity {self.Humidity} must be 0–100 %.")
        if not (0 <= self.Soil_Moisture <= 100):
            raise ValueError(f"Soil_Moisture {self.Soil_Moisture} must be 0–100 %.")
        return self


class PredictionResponse(BaseModel):
    irrigation_prediction: float   # model output (0–1 if binary, or mm if numeric)
    irrigation_recommended: bool   # True when prediction > 0.5 (binary) or above mean
    baseline_triggered:     bool   # True when Soil_Moisture < 30 (rule-based signal)
    model_used:             str
    features_received:      dict
    inference_ms:           float


# Endpoints

@app.get("/health", tags=["utility"])
def health():
    """Liveness probe – poll from Node-RED or Docker HEALTHCHECK."""
    return {"status": "ok", "model": MODEL_PATH, "scaler": SCALER_PATH}


@app.post("/predict", response_model=PredictionResponse, tags=["inference"])
def predict(reading: SensorReading):
    """
    Accept sensor data → return irrigation prediction.

    Response fields
    ---------------
    irrigation_prediction  : raw model output
    irrigation_recommended : True if model output indicates irrigation is needed
    baseline_triggered     : True if Soil_Moisture < 30 (rule-based reference)
    inference_ms           : server-side latency in milliseconds
    """
    t0 = time.perf_counter()

    try:
        # Feature vector in the exact order used during training
        X = np.array([[
            reading.Temperature,
            reading.Humidity,
            reading.Soil_Moisture,
        ]])

        X_scaled   = scaler.transform(X)
        prediction = float(model.predict(X_scaled)[0])

    except Exception as exc:
        log.error("Inference error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Inference failed: {exc}") from exc

    elapsed_ms = (time.perf_counter() - t0) * 1_000

    # Determine boolean recommendation
    # Works for both binary (0/1) and numeric targets
    irrigation_recommended = prediction >= 0.5

    # Rule-based baseline flag
    baseline_triggered = reading.Soil_Moisture < 30

    log.info(
        "T=%.1f  H=%.1f  SM=%.1f  →  pred=%.4f  recommended=%s  baseline=%s  %.2fms",
        reading.Temperature, reading.Humidity, reading.Soil_Moisture,
        prediction, irrigation_recommended, baseline_triggered, elapsed_ms,
    )

    return PredictionResponse(
        irrigation_prediction  = round(prediction, 4),
        irrigation_recommended = irrigation_recommended,
        baseline_triggered     = baseline_triggered,
        model_used             = "XGBoost Regressor v1.0",
        features_received      = reading.model_dump(),
        inference_ms           = round(elapsed_ms, 3),
    )


# Dev entry-point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
