"""
Smart Agriculture - Mission Control Dashboard
=============================================
A high-tech monitoring console for the smart agriculture bridge.

Live values come from the bridge's REST API (/latest); trend data comes from
the CSV history log. Run the bridge first, then run this.

Run with:   streamlit run dashboard.py

NOTE: Optional/bonus dashboard. The graded visualization platform for the
project is Blynk (lecturer-approved). Present this as an extra capability.
"""

import os
import time
import math
import requests
import pandas as pd
import streamlit as st

# -- CONFIG --------------------------------------------------------------
BRIDGE_URL   = "http://localhost:8001/latest"
CSV_LOG_FILE = "sensor_history_log.csv"
REFRESH_SECS = 3
MOISTURE_DRY_THRESHOLD = 30

st.set_page_config(
    page_title="AGRI-CONTROL",
    page_icon="\U0001F6F0",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- GLOBAL STYLE: dark control-room console -----------------------------
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600&display=swap');

      html,body,[class*="css"]{ font-family:'Inter',sans-serif; }
      .stApp{
        background:
          radial-gradient(1200px 600px at 20% -10%, #0c1726 0%, transparent 60%),
          radial-gradient(1000px 700px at 100% 0%, #0a1a1c 0%, transparent 55%),
          #070b12;
        color:#cdd9ea;
      }
      #MainMenu, footer, header {visibility:hidden;}
      .block-container{ padding-top:1.2rem; max-width:1400px; }

      .cmdbar{
        display:flex; align-items:center; justify-content:space-between;
        border:1px solid #1c2a3e; border-radius:14px;
        background:linear-gradient(180deg,#0e1726,#0a111c);
        padding:14px 22px; margin-bottom:18px;
        box-shadow:0 0 0 1px rgba(40,224,210,.04), 0 18px 40px -24px rgba(0,0,0,.9);
      }
      .brand{
        font-family:'Orbitron',sans-serif; font-weight:900;
        font-size:1.5rem; letter-spacing:.18em; color:#eaf4ff;
        text-shadow:0 0 18px rgba(40,224,210,.35);
      }
      .brand .dot{ color:#28e0d2; }
      .brand-sub{
        font-family:'JetBrains Mono',monospace; font-size:.7rem;
        letter-spacing:.3em; color:#5f7a9b; margin-top:2px;
      }
      .pill{
        font-family:'JetBrains Mono',monospace; font-size:.72rem;
        letter-spacing:.12em; padding:7px 14px; border-radius:999px;
        border:1px solid #1c2a3e; background:#0a111c; color:#8fa6c2;
      }
      .pill .live{ color:#3ddc84; }
      .pill .fault{ color:#ff4d6d; }

      .panel{
        border:1px solid #1c2a3e; border-radius:14px;
        background:linear-gradient(180deg,#0d1420,#0b111b);
        padding:18px 20px; height:100%;
        box-shadow:inset 0 1px 0 rgba(255,255,255,.02);
      }
      .panel h4{
        font-family:'JetBrains Mono',monospace; font-weight:600;
        font-size:.72rem; letter-spacing:.22em; text-transform:uppercase;
        color:#5f7a9b; margin:0 0 14px 0;
        display:flex; align-items:center; gap:8px;
      }
      .panel h4::before{
        content:""; width:6px; height:6px; border-radius:50%;
        background:#28e0d2; box-shadow:0 0 10px #28e0d2;
      }

      .readout{ font-family:'Orbitron',sans-serif; font-weight:700;
        font-size:2.4rem; line-height:1; color:#eaf4ff; }
      .readout-label{ font-family:'JetBrains Mono',monospace; font-size:.68rem;
        letter-spacing:.18em; text-transform:uppercase; color:#5f7a9b;
        margin-bottom:8px; }

      .statusline{ font-family:'Orbitron',sans-serif; font-weight:700;
        font-size:1.4rem; letter-spacing:.05em; }
      .s-ok{ color:#3ddc84; text-shadow:0 0 16px rgba(61,220,132,.4);}
      .s-dry{ color:#ff4d6d; text-shadow:0 0 16px rgba(255,77,109,.4);}
      .s-ml{ color:#4d9bff; text-shadow:0 0 16px rgba(77,155,255,.4);}
      .s-fault{ color:#ff4d6d; text-shadow:0 0 20px rgba(255,77,109,.6);
        animation:blink 1s steps(2,start) infinite;}
      @keyframes blink{ 50%{opacity:.35;} }

      .kv{ display:flex; justify-content:space-between; align-items:center;
        padding:9px 0; border-bottom:1px dashed #16243a;
        font-family:'JetBrains Mono',monospace; font-size:.82rem; }
      .kv:last-child{ border-bottom:none; }
      .kv .k{ color:#5f7a9b; letter-spacing:.08em; }
      .kv .v{ color:#cdd9ea; font-weight:600; }
      .v-yes{ color:#3ddc84; } .v-no{ color:#8fa6c2; }

      .disagree{
        margin-top:12px; padding:11px 14px; border-radius:10px;
        font-family:'JetBrains Mono',monospace; font-size:.8rem;
        border:1px solid rgba(255,181,71,.4); background:rgba(255,181,71,.08);
        color:#ffce85; letter-spacing:.04em;
      }
      .agree{
        margin-top:12px; padding:11px 14px; border-radius:10px;
        font-family:'JetBrains Mono',monospace; font-size:.8rem;
        border:1px solid rgba(61,220,132,.25); background:rgba(61,220,132,.06);
        color:#79e6a6; letter-spacing:.04em;
      }
      .stTabs [data-baseweb="tab-list"]{ gap:4px; }
      .stTabs [data-baseweb="tab"]{
        font-family:'JetBrains Mono',monospace; font-size:.74rem;
        letter-spacing:.12em; text-transform:uppercase; color:#5f7a9b;
        background:#0b111b; border:1px solid #1c2a3e; border-radius:8px 8px 0 0;
      }
      .stTabs [aria-selected="true"]{ color:#28e0d2 !important; }
      .foot{ font-family:'JetBrains Mono',monospace; font-size:.68rem;
        letter-spacing:.14em; color:#3c4f6b; text-align:center; margin-top:14px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# -- DATA ----------------------------------------------------------------
def fetch_live():
    try:
        r = requests.get(BRIDGE_URL, timeout=2)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def load_history():
    if not os.path.exists(CSV_LOG_FILE):
        return None
    try:
        df = pd.read_csv(CSV_LOG_FILE)
        if "Timestamp" in df.columns:
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        return df
    except Exception:
        return None

def gauge_svg(value, vmin, vmax, label, unit, color, danger_low=None):
    """Render a 240-degree arc gauge as inline SVG."""
    if value is None:
        value = vmin
    span = (vmax - vmin) if vmax > vmin else 1
    frac = max(0.0, min(1.0, (value - vmin) / span))
    start_ang = 150
    sweep = 240
    ang = start_ang + sweep * frac

    def pt(a, r):
        rad = math.radians(a)
        return 100 + r * math.cos(rad), 100 + r * math.sin(rad)

    R = 78
    x0, y0 = pt(start_ang, R)
    x1, y1 = pt(start_ang + sweep, R)
    xv, yv = pt(ang, R)
    large_bg = 1 if sweep > 180 else 0
    val_sweep = sweep * frac
    large_val = 1 if val_sweep > 180 else 0

    danger = danger_low is not None and value < danger_low
    arc_color = "#ff4d6d" if danger else color

    return f"""
    <svg viewBox="0 0 200 170" width="100%" height="150">
      <path d="M {x0:.1f} {y0:.1f} A {R} {R} 0 {large_bg} 1 {x1:.1f} {y1:.1f}"
            fill="none" stroke="#16243a" stroke-width="12" stroke-linecap="round"/>
      <path d="M {x0:.1f} {y0:.1f} A {R} {R} 0 {large_val} 1 {xv:.1f} {yv:.1f}"
            fill="none" stroke="{arc_color}" stroke-width="12" stroke-linecap="round"
            style="filter:drop-shadow(0 0 6px {arc_color});"/>
      <circle cx="{xv:.1f}" cy="{yv:.1f}" r="6" fill="{arc_color}"
            style="filter:drop-shadow(0 0 8px {arc_color});"/>
      <text x="100" y="96" text-anchor="middle"
            style="font-family:Orbitron;font-weight:700;font-size:30px;fill:#eaf4ff;">
            {value:.0f}<tspan style="font-size:13px;fill:#5f7a9b;">{unit}</tspan></text>
      <text x="100" y="120" text-anchor="middle"
            style="font-family:'JetBrains Mono';font-size:9px;letter-spacing:2px;fill:#5f7a9b;">
            {label}</text>
    </svg>
    """

# -- HEADER --------------------------------------------------------------
live, err = fetch_live()
is_fault = bool(live and live.get("status") == "fault")
conn = '<span class="fault">LINK LOST</span>' if err else '<span class="live">TELEMETRY LIVE</span>'

st.markdown(
    f"""
    <div class="cmdbar">
      <div>
        <div class="brand">AGRI<span class="dot">.</span>CONTROL</div>
        <div class="brand-sub">SMART IRRIGATION . ML INFERENCE NODE</div>
      </div>
      <div class="pill">{conn}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if err is not None:
    st.markdown(
        f'<div class="panel"><h4>System Offline</h4>'
        f'<div style="font-family:JetBrains Mono;font-size:.85rem;color:#8fa6c2;line-height:1.6;">'
        f'No telemetry link to the sensor bridge at <b>{BRIDGE_URL}</b>.<br>'
        f'Launch the bridge (<code>python smart_agri_bridge.py</code>) with the Arduino '
        f'connected to bring this console online.</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="foot">AWAITING UPLINK ...</div>', unsafe_allow_html=True)
    time.sleep(REFRESH_SECS)
    st.rerun()

# -- PULL VALUES ---------------------------------------------------------
moisture    = live.get("Soil_Moisture")
smoothed    = live.get("Soil_Moisture_Smoothed")
temp        = live.get("Temperature")
humidity    = live.get("Humidity")
pred        = live.get("irrigation_prediction")
recommended = live.get("irrigation_recommended")
baseline    = live.get("baseline_triggered")
disagree    = live.get("ml_baseline_disagree")
scenario    = live.get("Scenario")
ts          = live.get("timestamp")

# -- GAUGE ROW -----------------------------------------------------------
g1, g2, g3, g4 = st.columns(4)
with g1:
    st.markdown('<div class="panel"><h4>Soil Moisture</h4>'
                + gauge_svg(moisture, 0, 100, "RAW %", "%", "#28e0d2",
                            danger_low=MOISTURE_DRY_THRESHOLD)
                + '</div>', unsafe_allow_html=True)
with g2:
    st.markdown('<div class="panel"><h4>Moisture . Smoothed</h4>'
                + gauge_svg(smoothed, 0, 100, "FILTERED %", "%", "#4d9bff")
                + '</div>', unsafe_allow_html=True)
with g3:
    st.markdown('<div class="panel"><h4>Temperature</h4>'
                + gauge_svg(temp, 0, 50, "DEG C", "", "#ffb547")
                + '</div>', unsafe_allow_html=True)
with g4:
    st.markdown('<div class="panel"><h4>Humidity</h4>'
                + gauge_svg(humidity, 0, 100, "REL %", "%", "#3ddc84")
                + '</div>', unsafe_allow_html=True)

st.write("")

# -- DECISION + COMPARISON ROW -------------------------------------------
d1, d2, d3 = st.columns([1.1, 1, 1])

if is_fault:
    status_cls, status_txt = "s-fault", "SYSTEM FAULT"
elif moisture is not None and moisture < MOISTURE_DRY_THRESHOLD:
    status_cls, status_txt = "s-dry", "CRITICAL DRY"
elif recommended:
    status_cls, status_txt = "s-ml", "ML IRRIGATION ACTIVE"
else:
    status_cls, status_txt = "s-ok", "SYSTEM OK"

with d1:
    score_txt = f"{pred:.3f}" if pred is not None else "-"
    bar_w = int(min(max(pred or 0, 0), 1) * 100)
    st.markdown(
        f"""
        <div class="panel">
          <h4>Decision Core</h4>
          <div class="readout-label">System Status</div>
          <div class="statusline {status_cls}">{status_txt}</div>
          <div style="margin-top:16px;" class="readout-label">ML Irrigation-Need Score</div>
          <div class="readout">{score_txt}</div>
          <div style="margin-top:10px;height:8px;border-radius:6px;background:#16243a;overflow:hidden;">
            <div style="height:100%;width:{bar_w}%;border-radius:6px;
                 background:linear-gradient(90deg,#0f6f69,#28e0d2);
                 box-shadow:0 0 12px rgba(40,224,210,.5);"></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

with d2:
    st.markdown(
        f"""
        <div class="panel">
          <h4>Actuation</h4>
          <div class="kv"><span class="k">IRRIGATION</span>
            <span class="v {'v-yes' if recommended else 'v-no'}">{'YES' if recommended else 'NO'}</span></div>
          <div class="kv"><span class="k">VALVE / PUMP</span>
            <span class="v {'v-yes' if recommended else 'v-no'}">{'OPEN' if recommended else 'CLOSED'}</span></div>
          <div class="kv"><span class="k">SCENARIO</span>
            <span class="v">{scenario if scenario else '-'}</span></div>
          <div class="kv"><span class="k">UPDATED</span>
            <span class="v">{(ts or '-')[-8:] if ts else '-'}</span></div>
        </div>
        """, unsafe_allow_html=True)

with d3:
    cmp_block = (
        '<div class="disagree">ML vs RULE - MODELS DISAGREE<br>'
        'ML logic diverges from the naive threshold here.</div>'
        if disagree else
        '<div class="agree">ML = RULE - consensus on this reading.</div>'
    )
    st.markdown(
        f"""
        <div class="panel">
          <h4>ML vs Baseline</h4>
          <div class="kv"><span class="k">ML MODEL</span>
            <span class="v {'v-yes' if recommended else 'v-no'}">{'IRRIGATE' if recommended else 'HOLD'}</span></div>
          <div class="kv"><span class="k">RULE (SM&lt;{MOISTURE_DRY_THRESHOLD})</span>
            <span class="v {'v-yes' if baseline else 'v-no'}">{'IRRIGATE' if baseline else 'HOLD'}</span></div>
          {cmp_block}
        </div>
        """, unsafe_allow_html=True)

st.write("")

# -- HISTORY -------------------------------------------------------------
st.markdown('<div class="panel"><h4>Telemetry History</h4></div>',
            unsafe_allow_html=True)
df = load_history()
if df is None or df.empty:
    st.markdown('<div style="font-family:JetBrains Mono;font-size:.8rem;color:#5f7a9b;'
                'padding:8px 2px;">No logged readings yet - charts populate as the '
                'bridge records telemetry.</div>', unsafe_allow_html=True)
else:
    df = df.tail(200)
    t1, t2 = st.tabs(["Moisture & Climate", "ML Score Trace"])
    with t1:
        cols = [c for c in ["Soil_Moisture_Raw_Pct", "Soil_Moisture_Smoothed_Pct",
                            "Temperature_C", "Humidity_Pct"] if c in df.columns]
        if cols and "Timestamp" in df.columns:
            st.line_chart(df.set_index("Timestamp")[cols], height=260)
    with t2:
        if "ML_Prediction_Score" in df.columns and "Timestamp" in df.columns:
            st.line_chart(df.set_index("Timestamp")[["ML_Prediction_Score"]], height=260)
            if "ML_Baseline_Disagree" in df.columns:
                n = int(df["ML_Baseline_Disagree"].sum())
                st.markdown(f'<div style="font-family:JetBrains Mono;font-size:.72rem;'
                            f'color:#5f7a9b;letter-spacing:.1em;">ML vs RULE DIVERGENCES '
                            f'(LAST 200): {n}</div>', unsafe_allow_html=True)

st.markdown(f'<div class="foot">AGRI.CONTROL . AUTO-SYNC {REFRESH_SECS}s . '
            f'NODE :8001 . {(ts or "")[:19].replace("T"," ")}</div>',
            unsafe_allow_html=True)

time.sleep(REFRESH_SECS)
st.rerun()
