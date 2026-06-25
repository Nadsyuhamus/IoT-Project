/**
 * Smart Agriculture System - Core Frontend Engine
 * Language: Modern Vanilla JavaScript (ES6+)
 * Description: Handles real-time API polling, UI element mapping, 
 * and dynamic multi-dataset Chart.js updates.
 */

const API_URL = "http://localhost:8001/latest";
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
        if (data.Soil_Moisture < 30) {
            alertEl.innerText = "CRITICAL DRY";
            alertEl.className = "status-text text-alert";
        } else if (data.irrigation_recommended) {
            alertEl.innerText = "ML IRRIGATION ACTIVE";
            alertEl.className = "status-text text-warning";
        } else {
            alertEl.innerText = "SYSTEM OK";
            alertEl.className = "status-text text-ok";
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
}

/**
 * 7. CORE LIFE-CYCLE EVENT LISTENER
 * Attaches the execution routines as soon as the DOM finishes building.
 */
window.addEventListener('DOMContentLoaded', () => {
    initChart();
    setInterval(fetchLatestData, FETCH_INTERVAL);
    fetchLatestData(); // Execute immediate initial check frame
});