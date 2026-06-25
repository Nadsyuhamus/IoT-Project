/**
 * Agrino - Core Frontend Engine
 * Language: Modern Vanilla JavaScript (ES6+)
 * Description: Handles real-time API polling, UI element mapping,
 * dynamic multi-dataset Chart.js updates with manual features, and active card alert highlighting.
 */

const API_URL = "/latest";
const FETCH_INTERVAL = 2000;

let telemetryChart = null;

// State trackers for manual control override system
let localManualOverride = false;
let localManualPumpState = false;

function initChart() {
    const ctx = document.getElementById('telemetryChart').getContext('2d');

    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Soil Moisture (%)',
                    data: [],
                    borderColor: '#10b981', // 🌿 Matched exactly to Soil widget
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    borderWidth: 2.5,
                    tension: 0.2,
                    fill: false
                },
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#f97316', // ☀️ Matched exactly to Temp widget
                    backgroundColor: 'rgba(249, 115, 22, 0.08)',
                    borderWidth: 2.5,
                    tension: 0.2,
                    fill: false
                },
                {
                    label: 'Humidity (%)',
                    data: [],
                    borderColor: '#0284c7', // 💧 Matched exactly to Humidity widget
                    backgroundColor: 'rgba(2, 132, 199, 0.08)',
                    borderWidth: 2.5,
                    tension: 0.2,
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: '#e2ebd9' }, 
                    ticks: { color: '#1f412c', font: { family: 'JetBrains Mono, monospace', size: 11 } } 
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: '#e2ebd9' }, 
                    ticks: { color: '#1f412c', font: { family: 'JetBrains Mono, monospace', size: 11 } } 
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { 
                        color: '#1f412c', 
                        boxWidth: 16, 
                        font: { size: 14, family: 'Inter, sans-serif', weight: '600' } 
                    }
                }
            }
        }
    });
}

async function fetchLatestData() {
    try {
        const response = await fetch(API_URL, { headers: { 'ngrok-skip-browser-warning': '1' } });
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);

        const data = await response.json();

        if (data.status === "waiting_for_data") {
            updateConnectionStatus("AWAITING HARDWARE", "status-offline", "led-dot led-off");
            showAlert("AWAITING HARDWARE", "Sensor bridge is online but no microcontroller data received yet.", "warning");
            return;
        }

        if (data.status === "fault") {
            triggerFaultUI("HARDWARE DISCONNECTED");
            return;
        }

        updateConnectionStatus("ONLINE", "status-online", "led-dot led-off");

        // Keep core background sensory values synchronized on the screen
        document.getElementById('val-moisture').innerText = data.Soil_Moisture;
        document.getElementById('val-moisture-smooth').innerText = data.Soil_Moisture_Smoothed;
        document.getElementById('val-temp').innerText = data.Temperature;
        document.getElementById('val-humidity').innerText = data.Humidity;
        document.getElementById('val-ml-score').innerText = Number(data.irrigation_prediction).toFixed(4);
        document.getElementById('display-irrigation').innerText = data.irrigation_recommended ? "YES" : "NO";

        // ── DYNAMIC CARD CRITICAL HIGHLIGHT CHECKERS ──
        const moistureCard = document.getElementById('card-moisture');
        const tempCard     = document.getElementById('card-temp');
        const humidityCard = document.getElementById('card-humidity');

        // Soil Moisture Highlight: Critical Dry Threshold (< 30%)
        if (data.Soil_Moisture < 30) {
            moistureCard.classList.add('alert-highlight-critical');
        } else {
            moistureCard.classList.remove('alert-highlight-critical');
        }

        // Temperature Highlight: Extreme Safety Envelope Boundaries (> 38°C or < 15°C)
        if (data.Temperature > 38 || data.Temperature < 15) {
            tempCard.classList.add('alert-highlight-critical');
        } else {
            tempCard.classList.remove('alert-highlight-critical');
        }

        // Humidity Highlight: Air Waterlogging / Extreme Desiccation (> 85% or < 20%)
        if (data.Humidity > 85 || data.Humidity < 20) {
            humidityCard.classList.add('alert-highlight-critical');
        } else {
            humidityCard.classList.remove('alert-highlight-critical');
        }

        const alertEl = document.getElementById('display-alert');

        // INTERCEPT POINT: If user is actively overriding, bypass ML calculations for pump/scenarios
        if (localManualOverride) {
            document.getElementById('val-scenario').innerText = "MANUAL OVERRIDE";
            if (alertEl) {
                alertEl.innerText = "MANUAL MODE";
                alertEl.className = "status-text text-warning";
            }
            
            const pumpLed = document.getElementById('val-pump-led');
            if (pumpLed) {
                pumpLed.className = localManualPumpState ? "led-pump led-pump-active" : "led-pump led-pump-closed";
            }

            const currentTime = new Date().toLocaleTimeString();
            appendTerminalLog(`[${currentTime}] [MANUAL] Temp=${data.Temperature}°C Moisture=${data.Soil_Moisture}% Pump=${localManualPumpState ? "ON" : "OFF"}`);
            updateChartTimeline(currentTime, data.Soil_Moisture, data.Temperature, data.Humidity);
            return; 
        }

        // Standard automated operation pathway
        document.getElementById('val-scenario').innerText = data.Scenario;
        const isSensorErr = data.Scenario === "SENS ERR";

        if (isSensorErr) {
            alertEl.innerText = "SENSOR ERROR";
            alertEl.className = "status-text text-alert";
            showAlert("SENSOR NOT CONNECTED", "One or more sensors are not responding — check all wiring and connections.", "warning");
        } else if (data.Soil_Moisture < 30) {
            alertEl.innerText = "CRITICAL DRY";
            alertEl.className = "status-text text-alert";
            showAlert("CRITICAL DRY / SENSOR CHECK", `Soil moisture is at ${data.Soil_Moisture}% — critically dry or sensor may be disconnected. Check soil and wiring.`, "error");
        } else if (data.irrigation_recommended) {
            alertEl.innerText = "ML IRRIGATION ACTIVE";
            alertEl.className = "status-text text-warning";
            clearAlert();
        } else {
            alertEl.innerText = "SYSTEM OK";
            alertEl.className = "status-text text-ok";
            clearAlert();
        }

        const pumpLed = document.getElementById('val-pump-led');
        if (pumpLed) {
            pumpLed.className = data.Pump ? "led-pump led-pump-active" : "led-pump led-pump-closed";
        }

        const currentTime = new Date().toLocaleTimeString();
        appendTerminalLog(`[${currentTime}] Temp=${data.Temperature}°C  Hum=${data.Humidity}%  Moisture=${data.Soil_Moisture}%  Score=${data.irrigation_prediction}`);
        updateChartTimeline(currentTime, data.Soil_Moisture, data.Temperature, data.Humidity);

    } catch (err) {
        triggerFaultUI("BACKEND SERVICE OFFLINE");
    }
}

function appendTerminalLog(message) {
    const termBox = document.getElementById('terminal-box');
    if (termBox) {
        termBox.innerText += message + "\n";
        termBox.scrollTop = termBox.scrollHeight;
    }
}

function updateChartTimeline(timestamp, moisture, temp, hum) {
    if (!telemetryChart) return;
    if (telemetryChart.data.labels.length > 15) {
        telemetryChart.data.labels.shift();
        telemetryChart.data.datasets.forEach(ds => ds.data.shift());
    }
    telemetryChart.data.labels.push(timestamp);
    telemetryChart.data.datasets[0].data.push(moisture);
    telemetryChart.data.datasets[1].data.push(temp);
    telemetryChart.data.datasets[2].data.push(hum);
    telemetryChart.update();
}

function updateConnectionStatus(text, statusClass, ledClass) {
    document.getElementById('net-status').innerText = text;
    document.getElementById('net-status').className = statusClass;
    document.getElementById('fault-led').className = ledClass;
}

function triggerFaultUI(errorMessage) {
    updateConnectionStatus("SYSTEM FAULT", "status-offline", "led-dot led-on");

    const alertEl = document.getElementById('display-alert');
    if (alertEl) {
        alertEl.innerText = errorMessage;
        alertEl.className = "status-text text-alert";
    }

    const pumpLed = document.getElementById('val-pump-led');
    if (pumpLed) {
        pumpLed.className = "led-pump led-pump-shutdown";
    }

    const messages = {
        "HARDWARE DISCONNECTED": "Arduino or serial device is not transmitting. Check USB connection.",
        "BACKEND SERVICE OFFLINE": "Cannot reach the sensor bridge at port 8001. Ensure bridgenew.py is running."
    };
    showAlert(errorMessage, messages[errorMessage] || "An unknown system fault has occurred.", "error");
}

// ── ALERT BANNER ────────────────────────────────────────────────────────────

let alertDismissed = false;
let currentAlertCondition = null; 

function showAlert(title, message, type) {
    if (currentAlertCondition !== title) {
        alertDismissed = false;
        currentAlertCondition = title;
    }

    if (alertDismissed) return;

    const banner = document.getElementById('alert-banner');
    document.getElementById('alert-title').innerText = title;
    document.getElementById('alert-msg').innerText = message;
    document.getElementById('alert-icon').innerText = type === 'error' ? '⛔' : '⚠';
    document.getElementById('alert-time').innerText = new Date().toLocaleTimeString();
    banner.className = `alert-banner alert-${type}`;
}

function clearAlert() {
    alertDismissed = false;
    currentAlertCondition = null; 
    document.getElementById('alert-banner').className = 'alert-banner alert-hidden';
}

function dismissAlert() {
    alertDismissed = true;
    document.getElementById('alert-banner').className = 'alert-banner alert-hidden';
}

// ── SYSTEM CONTROL DISPATCHERS ──────────────────────────────────────────────────

async function sendControlState() {
    try {
        await fetch("/control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                manual_override: localManualOverride,
                manual_pump_state: localManualPumpState
            })
        });
    } catch (err) {
        console.error("Failed to transmit manual control state payload:", err);
    }
}

function handleOverrideToggle(isChecked) {
    localManualOverride = isChecked;
    const pumpBtn = document.getElementById("manual-pump-btn");
    
    pumpBtn.disabled = !isChecked;
    if (!isChecked) {
        localManualPumpState = false;
        pumpBtn.innerText = "VALVE: OFF";
        pumpBtn.style.background = "";
        pumpBtn.style.color = "";
    } else {
        pumpBtn.innerText = "VALVE: FORCE CLOSED";
        pumpBtn.style.background = "rgba(232, 51, 74, 0.1)";
        pumpBtn.style.color = "var(--status-crit)";
    }
    
    sendControlState();
}

function handleManualPumpClick() {
    if (!localManualOverride) return;
    
    localManualPumpState = !localManualPumpState;
    const pumpBtn = document.getElementById("manual-pump-btn");
    
    if (localManualPumpState) {
        pumpBtn.innerText = "VALVE: FORCE OPEN 💧";
        pumpBtn.style.background = "var(--accent-dim)";
        pumpBtn.style.color = "var(--accent)";
    } else {
        pumpBtn.innerText = "VALVE: FORCE CLOSED";
        pumpBtn.style.background = "rgba(232, 51, 74, 0.1)";
        pumpBtn.style.color = "var(--status-crit)";
    }
    
    sendControlState();
}

// ── LOG MODAL ────────────────────────────────────────────────────────────────

async function openLogModal() {
    document.getElementById('log-modal').style.display = 'flex';
    const container = document.getElementById('log-table-container');
    container.innerHTML = 'Loading...';
    try {
        const res = await fetch('/view-log', { headers: { 'ngrok-skip-browser-warning': '1' } });
        const data = await res.json();
        if (data.error || !data.headers.length) {
            container.innerHTML = `<p style="padding:16px;font-family:monospace;color:#3a5242;">${data.error || 'No data yet.'}</p>`;
            return;
        }
        let html = '<table class="log-table"><thead><tr>';
        data.headers.forEach(h => { html += `<th>${h}</th>`; });
        html += '</tr></thead><tbody>';
        [...data.rows].reverse().forEach(row => {
            html += '<tr>' + row.map(cell => `<td>${cell}</td>`).join('') + '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p style="padding:16px;font-family:monospace;color:#e8334a;">Failed to load log data.</p>';
    }
}

function closeLogModal(event) {
    if (!event || event.target === document.getElementById('log-modal') || event.target.classList.contains('modal-close-btn')) {
        document.getElementById('log-modal').style.display = 'none';
    }
}

// ── INIT ─────────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', () => {
    initChart();
    setInterval(fetchLatestData, FETCH_INTERVAL);
    fetchLatestData();
});