/**
 * Agrino - Core Frontend Engine
 * Language: Modern Vanilla JavaScript (ES6+)
 * Description: Handles real-time API polling, UI element mapping,
 * and dynamic multi-dataset Chart.js updates.
 */

const API_URL = "/latest";
const FETCH_INTERVAL = 2000;

let telemetryChart = null;

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
                    borderColor: '#00c26f',
                    backgroundColor: 'rgba(0, 194, 111, 0.08)',
                    borderWidth: 2,
                    tension: 0.2,
                    fill: false
                },
                {
                    label: 'Temperature (°C)',
                    data: [],
                    borderColor: '#d4890a',
                    backgroundColor: 'rgba(212, 137, 10, 0.08)',
                    borderWidth: 2,
                    tension: 0.2,
                    fill: false
                },
                {
                    label: 'Humidity (%)',
                    data: [],
                    borderColor: '#8aaa94',
                    backgroundColor: 'rgba(138, 170, 148, 0.08)',
                    borderWidth: 2,
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
                    grid: { color: '#182418' },
                    ticks: { color: '#3a5242', font: { family: 'JetBrains Mono, monospace', size: 10 } }
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: '#182418' },
                    ticks: { color: '#3a5242', font: { family: 'JetBrains Mono, monospace', size: 10 } }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#8aaa94', boxWidth: 12, font: { size: 11, family: 'Inter, sans-serif' } }
                }
            }
        }
    });
}

async function fetchLatestData() {
    try {
        const response = await fetch(API_URL);
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

        document.getElementById('val-moisture').innerText = data.Soil_Moisture;
        document.getElementById('val-moisture-smooth').innerText = data.Soil_Moisture_Smoothed;
        document.getElementById('val-temp').innerText = data.Temperature;
        document.getElementById('val-humidity').innerText = data.Humidity;
        document.getElementById('val-scenario').innerText = data.Scenario;
        document.getElementById('val-ml-score').innerText = Number(data.irrigation_prediction).toFixed(4);

        const alertEl = document.getElementById('display-alert');
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

        document.getElementById('display-irrigation').innerText = data.irrigation_recommended ? "YES" : "NO";
        document.getElementById('val-pump').innerText = data.Pump ? "ACTIVE 💧" : "CLOSED";
        document.getElementById('val-pump').style.color = data.Pump ? "#00c26f" : "#3a5242";

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

    const pumpEl = document.getElementById('val-pump');
    if (pumpEl) {
        pumpEl.innerText = "CLOSED (SAFETY SHUTDOWN)";
        pumpEl.style.color = "#e8334a";
    }

    const messages = {
        "HARDWARE DISCONNECTED": "Arduino or serial device is not transmitting. Check USB connection.",
        "BACKEND SERVICE OFFLINE": "Cannot reach the sensor bridge at port 8001. Ensure bridgenew.py is running."
    };
    showAlert(errorMessage, messages[errorMessage] || "An unknown system fault has occurred.", "error");
}

// ── ALERT BANNER ────────────────────────────────────────────────────────────

let alertDismissed = false;

function showAlert(title, message, type) {
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
    document.getElementById('alert-banner').className = 'alert-banner alert-hidden';
}

function dismissAlert() {
    alertDismissed = true;
    document.getElementById('alert-banner').className = 'alert-banner alert-hidden';
}

// ── LOG MODAL ────────────────────────────────────────────────────────────────

async function openLogModal() {
    document.getElementById('log-modal').style.display = 'flex';
    const container = document.getElementById('log-table-container');
    container.innerHTML = 'Loading...';
    try {
        const res = await fetch('/view-log');
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
