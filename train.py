import warnings
warnings.filterwarnings("ignore")

import os
import sys
import joblib
import numpy as np
import pandas as pd
import requests
from io import StringIO

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

# 0.  Configuration
GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/jyyhaaa/IoT-Project/"
    "main/irrigation_clean.csv"
)

# Actual column names in the CSV (confirmed from dataset)
COL_TEMPERATURE   = "Temperature_C"
COL_HUMIDITY      = "Humidity"
COL_SOIL_MOISTURE = "Soil_Moisture"
COL_TARGET        = "Irrigation_Need"

# Internal / API-facing names (must match Node-RED payload & app.py)
FEATURES = ["Temperature", "Humidity", "Soil_Moisture"]

MODEL_PATH  = "model_xgb.joblib"
SCALER_PATH = "scaler.joblib"

RANDOM_STATE = 42
TEST_SIZE    = 0.20

# 1.  Load dataset

def load_dataset() -> pd.DataFrame:
    print("[INFO] Downloading dataset from GitHub …")
    try:
        resp = requests.get(GITHUB_RAW_URL, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        print(f"[INFO] Loaded {len(df):,} rows  |  {df.shape[1]} columns.")
        return df
    except Exception as e:
        print(f"[ERROR] Download failed: {e}")
        sys.exit(1)


# 2.  Preprocess

def preprocess(df: pd.DataFrame):
    print("\n[INFO] Raw columns:", list(df.columns))

    # Validate required columns 
    required = [COL_TEMPERATURE, COL_HUMIDITY, COL_SOIL_MOISTURE, COL_TARGET]
    missing  = [c for c in required if c not in df.columns]
    if missing:
        print(f"\n[ERROR] Missing columns: {missing}")
        print(f"        Available: {list(df.columns)}")
        print("        → Update COL_* constants at the top of train.py.")
        sys.exit(1)

    # Select, rename, drop NaN 
    df_m = df[[COL_TEMPERATURE, COL_HUMIDITY, COL_SOIL_MOISTURE, COL_TARGET]].copy()
    df_m = df_m.rename(columns={
        COL_TEMPERATURE:   "Temperature",
        COL_HUMIDITY:      "Humidity",
        COL_SOIL_MOISTURE: "Soil_Moisture",
        COL_TARGET:        "target",
    })
    df_m = df_m.dropna().reset_index(drop=True)

    # Detect and handle target type
    raw_target  = df_m["target"]
    is_numeric  = pd.api.types.is_numeric_dtype(raw_target)
    n_unique    = raw_target.nunique()

    print(f"\n[INFO] Target '{COL_TARGET}': dtype={raw_target.dtype}, unique={n_unique}")

    if is_numeric and n_unique > 10:
        # Genuine regression target (e.g. mm of water)
        print("[INFO] Mode: NUMERIC REGRESSION")
        print(f"       min={raw_target.min():.3f}  max={raw_target.max():.3f}"
              f"  mean={raw_target.mean():.3f}")
    else:
        # Binary / categorical → encode as 0.0 / 1.0
        print("[INFO] Mode: BINARY → encoded as 0.0 / 1.0")
        print(f"       Sample values: {list(raw_target.unique()[:8])}")
        positive = {"yes", "high", "1", "true", "needed", "1.0"}
        df_m["target"] = (
            raw_target.astype(str).str.strip().str.lower()
                      .isin(positive)
        ).astype(float)
        print(f"       Distribution after encoding: "
              f"{df_m['target'].value_counts().to_dict()}")

    print("\n[INFO] Feature statistics (after rename):")
    print(df_m[FEATURES + ["target"]].describe().round(3).to_string())

    X = df_m[FEATURES].values
    y = df_m["target"].values

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    # Scale (fit on train only)
    scaler     = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc  = scaler.transform(X_test)

    print(f"\n[INFO] Train: {len(X_train):,} rows  |  Test: {len(X_test):,} rows")
    return X_train_sc, X_test_sc, y_train, y_test, scaler, df_m


# 3.  Train

def train_xgboost(X_train, y_train) -> XGBRegressor:
    print("\n[INFO] Training XGBoost Regressor …")
    model = XGBRegressor(
        n_estimators    = 300,
        max_depth       = 6,
        learning_rate   = 0.05,
        subsample       = 0.8,
        colsample_bytree= 0.8,
        random_state    = RANDOM_STATE,
        n_jobs          = -1,
        verbosity       = 0,
    )
    model.fit(X_train, y_train)
    print("[INFO] Training done.")
    return model


# 4.  Evaluate

def evaluate(name: str, y_true, y_pred):
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    print(f"\n  ── {name} ──")
    print(f"     MAE  : {mae:.4f}")
    print(f"     RMSE : {rmse:.4f}")
    return mae, rmse


# 5.  Rule-based baseline

def baseline_predict(soil_moisture_arr: np.ndarray, y_test: np.ndarray) -> np.ndarray:
    """
    Converts binary rule into numeric predictions for fair MAE/RMSE comparison.
    Binary target  → 1.0 (irrigate) or 0.0 (don't)
    Numeric target → 75th pct (high) or 25th pct (low)
    """
    is_binary = set(np.unique(y_test)).issubset({0.0, 1.0})
    high = 1.0  if is_binary else float(np.percentile(y_test, 75))
    low  = 0.0  if is_binary else float(np.percentile(y_test, 25))
    return np.where(soil_moisture_arr < 30, high, low)


# 6.  Main

def main():
    print("=" * 60)
    print(" Smart Agriculture – Irrigation Prediction  (train.py)")
    print("=" * 60)

    df_raw = load_dataset()
    X_train, X_test, y_train, y_test, scaler, df_model = preprocess(df_raw)
    model = train_xgboost(X_train, y_train)

    # Evaluate
    print("\n" + "=" * 60)
    print(" EVALUATION RESULTS")
    print("=" * 60)

    y_pred_xgb = model.predict(X_test)
    xgb_mae, xgb_rmse = evaluate("XGBoost Regressor (ML Model)", y_test, y_pred_xgb)

    # Baseline – re-split identically to obtain the unscaled Soil_Moisture column
    _, df_test_raw = train_test_split(df_model, test_size=TEST_SIZE, random_state=RANDOM_STATE)
    y_test_base    = df_test_raw["target"].values
    sm_test        = df_test_raw["Soil_Moisture"].values
    y_pred_base    = baseline_predict(sm_test, y_test_base)
    base_mae, base_rmse = evaluate(
        "Rule-Based Baseline (Soil_Moisture < 30)", y_test_base, y_pred_base
    )

    # Feature importances
    print("\n[INFO] XGBoost Feature Importances (F-score):")
    for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
        bar = "█" * max(1, int(imp * 40))
        print(f"  {feat:<18} {imp:.4f}  {bar}")

    # Comparison summary
    imp_mae  = (base_mae  - xgb_mae)  / base_mae  * 100 if base_mae  > 0 else 0
    imp_rmse = (base_rmse - xgb_rmse) / base_rmse * 100 if base_rmse > 0 else 0

    print("\n" + "=" * 60)
    print(" COMPARISON SUMMARY")
    print("=" * 60)
    print(f"  {'Model':<42} {'MAE':>8} {'RMSE':>8}")
    print(f"  {'-'*42} {'-'*8} {'-'*8}")
    print(f"  {'XGBoost Regressor (ML)':<42} {xgb_mae:>8.4f} {xgb_rmse:>8.4f}")
    print(f"  {'Rule-Based Baseline (SM < 30)':<42} {base_mae:>8.4f} {base_rmse:>8.4f}")
    print(f"\n  MAE  improvement over baseline : {imp_mae:+.1f}%")
    print(f"  RMSE improvement over baseline : {imp_rmse:+.1f}%")

    # Cross-validation
    print("\n[INFO] 5-Fold CV (full dataset) …")
    sc2      = StandardScaler()
    X_all_sc = sc2.fit_transform(df_model[FEATURES].values)
    cv       = cross_val_score(
        XGBRegressor(n_estimators=300, max_depth=6, learning_rate=0.05,
                     random_state=RANDOM_STATE, verbosity=0, n_jobs=-1),
        X_all_sc, df_model["target"].values,
        scoring="neg_root_mean_squared_error", cv=5, n_jobs=-1,
    )
    print(f"  CV RMSE : {-cv.mean():.4f} ± {cv.std():.4f}")

    joblib.dump(model,  MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"\n[INFO] Saved → {MODEL_PATH}")
    print(f"[INFO] Saved → {SCALER_PATH}")
    print("\n[DONE] Run:  uvicorn app:app --reload --port 8000")


if __name__ == "__main__":
    main()
