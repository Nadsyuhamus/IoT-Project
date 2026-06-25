/**
 * Smart Agriculture System - Core Frontend Engine
 * Language: Modern Vanilla JavaScript (ES6+)
 * Description: Handles real-time API polling, UI element mapping, 
 * and dynamic multi-dataset Chart.js updates.
 */

const API_URL = "http://127.0.0.1:8001/latest";
const FETCH_INTERVAL = 2000; // Poll the Python FastAPI backend every 2000ms (2 seconds)

let telemetryChart = null;

/**
 * 1. INITIALIZE REAL-TIME TIME-SERIES STREAM GRAPH
 * Constructs a multi-axis Chart.js layout to map sensor fluctuations.
 */
function initChart() {
    const ctx = document.getElementById('telemetryChart').getContext('2d');
    
    telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], // Stores dynamic timestamp indices for the X-axis
            datasets: [
                { 
                    label: 'Soil Moisture (%)', 
                    data: [], 
                    borderColor: '#00d2ff', 
                    backgroundColor: 'rgba(0, 210, 255, 0.1)',
                    borderWidth: 2,
                    tension: 0.2, 
                    fill: false 
                },
                { 
                    label: 'Temperature (°C)', 
                    data: [], 
                    borderColor: '#ff9900', 
                    backgroundColor: 'rgba(255, 153, 0, 0.1)',
                    borderWidth: 2,
                    tension: 0.2, 
                    fill: false 
                },
                { 
                    label: 'Humidity (%)', 
                    data: [], 
                    borderColor: '#00ff88', 
                    backgroundColor: 'rgba(0, 255, 136, 0.1)',
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
                    grid: { color: '#2a2a2f' }, 
                    ticks: { color: '#8e8e93', font: { family: 'monospace' } } 
                },
                y: { 
                    min: 0, 
                    max: 100, 
                    grid: { color: '#2a2a2f' }, 
                    ticks: { color: '#8e8e93' } 
                }
            },
            plugins: { 
                legend: { 
                    position: 'top',
                    labels: { color: '#ffffff', boxWidth: 12, font: { size: 12 } } 
                } 
            }
        }
    });
}

/**
 * 2. CORE TELEMETRY EXTRACTOR & DOM MAPPER
 * Asynchronously pulls data frames from the local backend database.
 */
async function fetchLatestData() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error(`HTTP network anomaly: Status ${response.status}`);
        
        const data = await response.json();
        
        // State 1: API is running but waiting for physical microchip data transmission
        if (data.status === "waiting_for_data") {
            updateConnectionStatus("CONNECTED (AWAITING HARDWARE)", "status-offline", "led-dot led-off");
            showAlert("AWAITING HARDWARE", "Sensor bridge is online but no microcontroller data received yet.", "warning");
            return;
        }

        // State 2: Python backend has explicitly declared a serial device fault
        if (data.status === "fault") {
            triggerFaultUI("HARDWARE DISCONNECTED");
            return;
        }

        // State 3: Active stable stream. Reset indicators to healthy defaults.
        updateConnectionStatus("ONLINE", "status-online", "led-dot led-off");

        // Map numeric fields directly to text containers
        document.getElementById('val-moisture').innerText = data.Soil_Moisture;
        document.getElementById('val-moisture-smooth').innerText = data.Soil_Moisture_Smoothed;
        document.getElementById('val-temp').innerText = data.Temperature;
        document.getElementById('val-humidity').innerText = data.Humidity;
        document.getElementById('val-scenario').innerText = data.Scenario;
        document.getElementById('val-ml-score').innerText = Number(data.irrigation_prediction).toFixed(4);

        // Evaluate logical rules against current values to apply appropriate UI highlight colors
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

        // Synchronize valve actuator text representations
        document.getElementById('display-irrigation').innerText = data.irrigation_recommended ? "YES" : "NO";
        document.getElementById('val-pump').innerText = data.Pump ? "ACTIVE 💧" : "CLOSED";
        document.getElementById('val-pump').style.color = data.Pump ? "#00ff88" : "#8e8e93";

        // Generate line strings and append to the local scrolling terminal matrix
        const currentTime = new Date().toLocaleTimeString();
        appendTerminalLog(`[${currentTime}] Temp=${data.Temperature}°C, Hum=${data.Humidity}%, Moisture=${data.Soil_Moisture}% | Score=${data.irrigation_prediction}`);

        // Inject new telemetry data points directly into the timeline graph mapping arrays
        updateChartTimeline(currentTime, data.Soil_Moisture, data.Temperature, data.Humidity);

    } catch (err) {
        // Fallback: Trigger instant system safe layout if the API connection drops entirely
        triggerFaultUI("BACKEND SERVICE OFFLINE");
    }
}

/**
 * 3. LOG TERMINAL MANAGER
 * Appends formatted lines to the log element and handles auto-scrolling behaviors.
 */
function appendTerminalLog(message) {
    const termBox = document.getElementById('terminal-box');
    if (termBox) {
        termBox.innerText += message + "\n";
        termBox.scrollTop = termBox.scrollHeight; // Automatically pin scroll frame to base
    }
}

/**
 * 4. CHART TIMESHIFT MATRIX MANAGER
 * Pushes historical timeline indices, keeping view frame tracking stable.
 */
function updateChartTimeline(timestamp, moisture, temp, hum) {
    if (!telemetryChart) return;

    // Constrain graph view to a rolling window of the 15 most recent data blocks
    if (telemetryChart.data.labels.length > 15) {
        telemetryChart.data.labels.shift();
        telemetryChart.data.datasets[0].data.shift(); // Evict oldest Moisture point
        telemetryChart.data.datasets[1].data.shift(); // Evict oldest Temperature point
        telemetryChart.data.datasets[2].data.shift(); // Evict oldest Humidity point
    }

    // Insert fresh tracking vectors
    telemetryChart.data.labels.push(timestamp);
    telemetryChart.data.datasets[0].data.push(moisture);
    telemetryChart.data.datasets[1].data.push(temp);
    telemetryChart.data.datasets[2].data.push(hum);
    
    // Smoothly re-render the canvas matrix frame
    telemetryChart.update();
}

/**
 * 5. UTILITY STATUS REFRESHER
 * Changes header status components cleanly.
 */
function updateConnectionStatus(text, statusClass, ledClass) {
    document.getElementById('net-status').innerText = text;
    document.getElementById('net-status').className = statusClass;
    document.getElementById('fault-led').className = ledClass;
}

/**
 * 6. SYSTEM WIDE FAULT MITIGATION ENGINE
 * Safely changes interface structures when hardware errors happen.
 */
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
        pumpEl.style.color = "#ff3333";
    }

    const messages = {
        "HARDWARE DISCONNECTED": "Arduino or serial device is not transmitting. Check USB connection.",
        "BACKEND SERVICE OFFLINE": "Cannot reach the sensor bridge at port 8001. Ensure bridge.py is running."
    };
    showAlert(errorMessage, messages[errorMessage] || "An unknown system fault has occurred.", "error");
}

/**
 * 7. ALERT BANNER CONTROLLER
 */
let alertDismissed = false;

function showAlert(title, message, type) {
    if (alertDismissed) return;
    const banner = document.getElementById('alert-banner');
    const titleEl = document.getElementById('alert-title');
    const msgEl = document.getElementById('alert-msg');
    const iconEl = document.getElementById('alert-icon');
    const timeEl = document.getElementById('alert-time');

    titleEl.innerText = title;
    msgEl.innerText = message;
    timeEl.innerText = new Date().toLocaleTimeString();
    iconEl.innerText = type === 'error' ? '⛔' : '⚠';

    banner.className = `alert-banner alert-${type}`;
}

function clearAlert() {
    alertDismissed = false;
    const banner = document.getElementById('alert-banner');
    banner.className = 'alert-banner alert-hidden';
}

function dismissAlert() {
    alertDismissed = true;
    const banner = document.getElementById('alert-banner');
    banner.className = 'alert-banner alert-hidden';
}

/**
 * 7. CORE LIFE-CYCLE EVENT LISTENER
 * Attaches the execution routines as soon as the DOM finishes building.
 */
async function openLogModal() {
    document.getElementById('log-modal').style.display = 'flex';
    const container = document.getElementById('log-table-container');
    container.innerHTML = 'Loading...';
    try {
        const res = await fetch('http://127.0.0.1:8001/view-log');
        const data = await res.json();
        if (data.error || !data.headers.length) {
            container.innerHTML = `<p style="color:#8e8e93;">${data.error || 'No data yet.'}</p>`;
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
        container.innerHTML = '<p style="color:#ff3333;">Failed to load log data.</p>';
    }
}

function closeLogModal(event) {
    if (!event || event.target === document.getElementById('log-modal') || event.target.classList.contains('modal-close-btn')) {
        document.getElementById('log-modal').style.display = 'none';
    }
}

window.addEventListener('DOMContentLoaded', () => {
    initChart();
    setInterval(fetchLatestData, FETCH_INTERVAL);
    fetchLatestData();
});