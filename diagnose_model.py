"""
diagnose_model.py
────────────────────────────────────────────────────────────────────────
Run this script in the same folder as your model_xgb.joblib, scaler.joblib,
and where train.py can reach irrigation_clean.csv (or it will download it
from GitHub automatically, same as train.py does).

This tells us:
  1. What the actual target variable (Irrigation_Need) values look like
  2. Whether the model is bounded 0-1 or a wider numeric range
  3. What the model predicts for a "should definitely irrigate" case
     (SM=0, hot, dry) vs a "should definitely NOT irrigate" case
     (SM=100, cool)
────────────────────────────────────────────────────────────────────────
"""

import joblib
import numpy as np
import pandas as pd
import requests
from io import StringIO

GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/jyyhaaa/IoT-Project/"
    "main/irrigation_clean.csv"
)

print("=" * 60)
print(" STEP 1: Inspect the raw target variable")
print("=" * 60)

resp = requests.get(GITHUB_RAW_URL, timeout=30)
df = pd.read_csv(StringIO(resp.text))

print(f"\nColumns found: {list(df.columns)}")
print(f"\nIrrigation_Need stats:")
print(df["Irrigation_Need"].describe())
print(f"\nFirst 10 raw values: {df['Irrigation_Need'].head(10).tolist()}")
print(f"\nNumber of unique values: {df['Irrigation_Need'].nunique()}")
print(f"Min: {df['Irrigation_Need'].min()}   Max: {df['Irrigation_Need'].max()}")

print("\n" + "=" * 60)
print(" STEP 2: Test the model on extreme cases")
print("=" * 60)

model  = joblib.load("model_xgb.joblib")
scaler = joblib.load("scaler.joblib")

test_cases = [
    {"name": "Extreme drought (hot, totally dry)",  "T": 40, "H": 20, "SM": 0},
    {"name": "Your actual reading",                  "T": 35, "H": 52, "SM": 0},
    {"name": "Mild conditions",                       "T": 25, "H": 60, "SM": 50},
    {"name": "Fully saturated, cool",                  "T": 20, "H": 80, "SM": 100},
]

for case in test_cases:
    X = np.array([[case["T"], case["H"], case["SM"]]])
    X_scaled = scaler.transform(X)
    pred = float(model.predict(X_scaled)[0])
    print(f"\n{case['name']}:")
    print(f"  Input: T={case['T']}  H={case['H']}  SM={case['SM']}")
    print(f"  Prediction: {pred:.4f}")

print("\n" + "=" * 60)
print(" INTERPRETATION GUIDE")
print("=" * 60)
print("""
If STEP 1 shows Irrigation_Need values like 0.73, 1.45, 2.91, -0.5, etc.
(NOT clean 0.0/1.0), then your model is a REGRESSION on a continuous
scale, NOT a 0-1 probability. In that case, comparing prediction >= 0.5
is the wrong decision rule entirely - you should instead compare against
percentile thresholds from the training data (e.g. top 25% = irrigate).

If STEP 1 shows only 0.0 and 1.0 values, then 0.5 threshold IS correct,
and the issue is that the model isn't confident enough even at SM=0 -
which would mean retraining with more weight on soil moisture extremes
might help.

Look at STEP 2's "Extreme drought" case - if even that doesn't produce
a prediction near 1.0 or above 0.5, the model itself needs adjustment,
not just more data.
""")