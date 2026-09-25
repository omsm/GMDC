// Animation State
const AnimationState = {
    rfidRead: false,
    sensor1Cut: false,
    sensor2Cut: false,
    sensor3Cut: false,
    entryTLGreen: false,
    exitTLGreen: false,
    truckPosition: -1, // -1 = hidden, 0-5 = positions
    position4Reached: false,
    position5Reached: false,
    digitizerValue: 0 // Weight in kg
};

// Application version (loaded from backend)
let APP_VERSION = 'unknown';
let UPDATE_STATUS = null;
let UPDATE_PROGRESS_TIMER = null;
const UPDATE_STATUS_POLL_MS = 2 * 60 * 1000;

// MQTT Client
let mqttClient = null;
const MQTT_BROKER_HOST = (typeof window !== 'undefined' && window.location && window.location.hostname)
    ? window.location.hostname
    : 'localhost';
const MQTT_BROKER_PORT = 9001;
const MQTT_CONFIGS = [
    { port: 9001, path: '/' },
    { port: 9001, path: '/mqtt' },
    { port: 9001, path: '/ws' }
];
let currentConfigIndex = 0;
const MQTT_CLIENT_ID = 'weighbridge_frontend_' + Math.random().toString(16).substr(2, 8);

// Initialize
function init() {
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
    resetAnimation();
    updateDigitizer(0);
    // Ensure initial state is green
    const digitizerDisplay = document.getElementById('digitizer-display');
    if (digitizerDisplay) {
        digitizerDisplay.classList.add('digitizer-green');
    }
    initModalHandlers();
    loadAppVersion();
    initUpdaterUI();
    initMQTT();
}

async function fetchUpdateStatus() {
    try {
        const resp = await fetch('/api/update/status', { cache: 'no-store' });
        if (!resp.ok) return null;
        const payload = await resp.json();
        UPDATE_STATUS = payload.data || null;
        return UPDATE_STATUS;
    } catch (e) {
        console.warn('Error loading update status:', e);
        return null;
    }
}

function renderUpdateIcon(data) {
    const btn = document.getElementById('update-btn');
    if (!btn) return;
    const available = !!(data && data.update_available);
    btn.style.display = available ? 'inline-flex' : 'none';
    if (available) {
        btn.title = 'Update available: ' + (data.latest_version || 'new version');
    }
}

async function initUpdaterUI() {
    const data = await fetchUpdateStatus();
    renderUpdateIcon(data);
    setInterval(async () => {
        const d = await fetchUpdateStatus();
        renderUpdateIcon(d);
    }, UPDATE_STATUS_POLL_MS);
}

// Load application version from backend
async function loadAppVersion() {
    try {
        const resp = await fetch('/version', { cache: 'no-store' });
        if (!resp.ok) {
            console.warn('Failed to fetch version: HTTP', resp.status);
            return;
        }
        const data = await resp.json();
        APP_VERSION = (data && data.version) ? data.version : 'unknown';
        console.log('Loaded application version (animation):', APP_VERSION);
        const versionEl = document.getElementById('app-version');
        if (versionEl) {
            versionEl.textContent = 'v' + (APP_VERSION || 'unknown');
        }
    } catch (e) {
        console.warn('Error loading application version (animation):', e);
    }
}

// Show version info when info button is clicked
function showVersionInfo() {
    const version = APP_VERSION || 'unknown';
    const message = 'Application Version: ' + version;
    alert(message);
}

function openUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (!modal) return;
    const data = UPDATE_STATUS || {};
    const cur = document.getElementById('upd-current-version');
    const lat = document.getElementById('upd-latest-version');
    const notes = document.getElementById('upd-release-notes');
    const msg = document.getElementById('upd-message');
    renderUpdateProgress(displayPercentFromStatusPayload(data));
    if (cur) cur.textContent = data.current_version || APP_VERSION || 'unknown';
    if (lat) lat.textContent = data.latest_version || 'unknown';
    if (notes) notes.textContent = (data.release_notes || 'No release notes available.').toString().slice(0, 4000);
    if (msg) msg.textContent = (data && data.progress_message) ? data.progress_message : 'Ready';
    modal.classList.add('active');
    startUpdateProgressPolling();
}

function closeUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (modal) modal.classList.remove('active');
    stopUpdateProgressPolling();
}

function renderUpdateProgress(percent) {
    const safe = Math.max(0, Math.min(100, Number(percent) || 0));
    const bar = document.getElementById('upd-progress-bar');
    const label = document.getElementById('upd-progress-label');
    if (bar) bar.style.width = `${safe}%`;
    if (label) label.textContent = `${safe}%`;
}

function displayPercentFromStatusPayload(data) {
    if (!data) return 0;
    const step = data.progress_step || '';
    if (!data.applying && (step === 'checked' || step === 'idle' || step === 'error')) return 0;
    if (step === 'checking') return Math.min(5, Number(data.progress_percent) || 0);
    return Math.max(0, Math.min(100, Number(data.progress_percent) || 0));
}

function displayPercentFromProgressPayload(progress) {
    if (!progress) return 0;
    const step = progress.step || '';
    if (!progress.applying && (step === 'checked' || step === 'idle' || step === 'error')) return 0;
    if (step === 'checking') return Math.min(5, Number(progress.percent) || 0);
    return Math.max(0, Math.min(100, Number(progress.percent) || 0));
}

async function fetchUpdateProgress() {
    try {
        const resp = await fetch('/api/update/progress', { cache: 'no-store' });
        if (!resp.ok) return null;
        const payload = await resp.json();
        return payload.data || null;
    } catch (e) {
        return null;
    }
}

function startUpdateProgressPolling() {
    stopUpdateProgressPolling();
    const tick = async () => {
        const progress = await fetchUpdateProgress();
        if (!progress) return;
        renderUpdateProgress(displayPercentFromProgressPayload(progress));
        const msg = document.getElementById('upd-message');
        if (msg && progress.message) msg.textContent = progress.message;
    };
    tick();
    UPDATE_PROGRESS_TIMER = setInterval(tick, 1000);
}

function stopUpdateProgressPolling() {
    if (UPDATE_PROGRESS_TIMER) {
        clearInterval(UPDATE_PROGRESS_TIMER);
        UPDATE_PROGRESS_TIMER = null;
    }
}

async function applyUpdateNow() {
    const btn = document.getElementById('apply-update-btn');
    const msg = document.getElementById('upd-message');
    if (btn) btn.disabled = true;
    renderUpdateProgress(0);
    startUpdateProgressPolling();
    if (msg) msg.textContent = 'Downloading and preparing update...';
    try {
        const resp = await fetch('/api/update/apply', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || data.status !== 200) {
            throw new Error(data.message || 'Failed to start update');
        }
        if (msg) msg.textContent = 'Update started. Application will close now.';
    } catch (e) {
        if (msg) msg.textContent = 'Update failed: ' + e;
        if (btn) btn.disabled = false;
    }
}

// Update timestamp
function updateTimestamp() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { 
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        timeElement.textContent = timeString;
    }
}

// Reset animation
function resetAnimation() {
    AnimationState.rfidRead = false;
    AnimationState.sensor1Cut = false;
    AnimationState.sensor2Cut = false;
    AnimationState.sensor3Cut = false;
    AnimationState.entryTLGreen = false;
    AnimationState.exitTLGreen = false;
    AnimationState.truckPosition = -1;
    AnimationState.position4Reached = false;
    AnimationState.position5Reached = false;
    AnimationState.digitizerValue = 0;

    // Reset digitizer
    updateDigitizer(0);

    // Hide truck
    const truck = document.getElementById('truck');
    if (truck) {
        truck.classList.remove('visible');
        truck.style.left = '-500px';
        truck.className = 'truck';
    }

    // Reset sensors
    resetSensor(1);
    resetSensor(2);
    resetSensor(3);

    // Reset traffic lights
    setTrafficLight('entry', 'red');
    setTrafficLight('exit', 'red');

    // Update status display
    updateStatusDisplay();
}

// Start full animation sequence
function startAnimation() {
    resetAnimation();
    
    setTimeout(() => {
        triggerRFID();
    }, 500);

    setTimeout(() => {
        triggerSensor(1);
    }, 2000);

    setTimeout(() => {
        triggerSensor(2);
    }, 4000);

    setTimeout(() => {
        triggerSensor(3);
    }, 6000);

    setTimeout(() => {
        setTrafficLight('exit', 'green');
    }, 8000);
}

// Trigger RFID read
function triggerRFID() {
    if (AnimationState.rfidRead) return;
    
    AnimationState.rfidRead = true;
    AnimationState.truckPosition = 0;

    // Show truck
    const truck = document.getElementById('truck');
    if (truck) {
        truck.classList.add('visible');
        truck.style.left = '-100px';  // Matches CSS .truck.position-0 { left: -210px; }
        truck.className = 'truck visible position-0';
    }

    // Set entry traffic light to green
    setTrafficLight('entry', 'green');

    updateStatusDisplay();
}

// Trigger sensor
function triggerSensor(sensorNum) {
    const sensorKey = `sensor${sensorNum}Cut`;
    
    if (AnimationState[sensorKey]) return;

    AnimationState[sensorKey] = true;
    AnimationState.truckPosition = sensorNum;

    // Activate sensor indicator
    const sensorIndicator = document.getElementById(`sensor${sensorNum}-indicator`);
    if (sensorIndicator) {
        sensorIndicator.classList.add('active');
    }

    // Move truck
    const truck = document.getElementById('truck');
    if (truck && AnimationState.truckPosition >= 0) {
        // These values should match the CSS position classes (fixed pixels)
        const positions = {
            1: '170px',   // Matches CSS .truck.position-1 { left: 70px; }
            2: '500px',  // Matches CSS .truck.position-2 { left: 420px; }
            3: '800px'   // Matches CSS .truck.position-3 { left: 840px; }
        };
        truck.style.left = positions[sensorNum] || truck.style.left;
        truck.className = `truck visible position-${sensorNum}`;
    }

    // Special actions for sensor 2 (middle)
    if (sensorNum === 2) {
        // Vehicle at center - could trigger weight reading
    }

    // Special actions for sensor 3 (exit)
    if (sensorNum === 3) {
        // Vehicle at exit - open exit traffic light
        setTimeout(() => {
            setTrafficLight('exit', 'green');
        }, 500);
    }

    updateStatusDisplay();
}

// Trigger position (for positions 4 and 5)
function triggerPosition(positionNum) {
    if (positionNum === 4) {
        if (AnimationState.position4Reached) return;
        AnimationState.position4Reached = true;
        AnimationState.truckPosition = 4;

        // Move truck to position 4
        const truck = document.getElementById('truck');
        if (truck && AnimationState.truckPosition >= 0) {
            truck.style.left = '980px';  // Matches CSS .truck.position-4 { left: 980px; }
            truck.className = 'truck visible position-4';
        }
    } else if (positionNum === 5) {
        if (AnimationState.position5Reached) return;
        AnimationState.position5Reached = true;
        AnimationState.truckPosition = 5;

        // Move truck to position 5
        const truck = document.getElementById('truck');
        if (truck && AnimationState.truckPosition >= 0) {
            truck.style.left = '1400px';  // Matches CSS .truck.position-5 { left: 1330px; }
            truck.className = 'truck visible position-5';
        }

        // Set traffic light to red after position 5
        setTimeout(() => {
            setTrafficLight('exit', 'red');
        }, 500);
    }

    updateStatusDisplay();
}

// Reset sensor
function resetSensor(sensorNum) {
    const sensorIndicator = document.getElementById(`sensor${sensorNum}-indicator`);
    if (sensorIndicator) {
        sensorIndicator.classList.remove('active');
    }
}

// Set traffic light state
function setTrafficLight(type, state) {
    const tlElement = document.getElementById(`${type}-traffic-light`);
    if (!tlElement) return;

    const lights = tlElement.querySelectorAll('.light');
    lights.forEach(light => light.classList.remove('active'));

    if (state === 'red') {
        lights[0].classList.add('active');
        AnimationState[`${type}TLGreen`] = false;
    } else if (state === 'yellow') {
        lights[1].classList.add('active');
    } else if (state === 'green') {
        lights[2].classList.add('active');
        AnimationState[`${type}TLGreen`] = true;
    }

    updateStatusDisplay();
}

// Update status display
function updateStatusDisplay() {
    const rfidStatus = document.getElementById('rfid-status');
    if (rfidStatus) {
        rfidStatus.textContent = AnimationState.rfidRead ? 'Read' : 'Not Read';
        rfidStatus.style.color = AnimationState.rfidRead ? '#00875a' : '#6b778c';
        rfidStatus.style.background = AnimationState.rfidRead ? '#e3fcef' : '#f4f5f7';
    }

    const entryTLStatus = document.getElementById('entry-tl-status');
    if (entryTLStatus) {
        entryTLStatus.textContent = AnimationState.entryTLGreen ? 'Green' : 'Red';
        entryTLStatus.style.color = AnimationState.entryTLGreen ? '#00875a' : '#de350b';
        entryTLStatus.style.background = AnimationState.entryTLGreen ? '#e3fcef' : '#ffebe6';
    }

    const exitTLStatus = document.getElementById('exit-tl-status');
    if (exitTLStatus) {
        exitTLStatus.textContent = AnimationState.exitTLGreen ? 'Green' : 'Red';
        exitTLStatus.style.color = AnimationState.exitTLGreen ? '#00875a' : '#de350b';
        exitTLStatus.style.background = AnimationState.exitTLGreen ? '#e3fcef' : '#ffebe6';
    }
}

// Update digitizer display
function updateDigitizer(weight) {
    AnimationState.digitizerValue = weight;
    
    // Format weight to 7 digits (pad with zeros)
    const weightStr = Math.floor(weight).toString().padStart(7, '0');
    
    // Check if position is -1 (IDLE) and weight is non-zero -> show red with flashing
    const isIdleWithWeight = AnimationState.truckPosition === -1 && weight !== 0;
    const isZero = weight === 0;
    
    console.log(`[Digitizer] Updating display: weight=${weight}, position=${AnimationState.truckPosition}, isIdleWithWeight=${isIdleWithWeight}, isZero=${isZero}`);
    
    // Get digitizer display container
    const digitizerDisplay = document.getElementById('digitizer-display');
    const flashingIndicator = document.getElementById('digitizer-flashing-indicator');
    
    // Update flashing indicator visibility
    if (flashingIndicator) {
        if (isIdleWithWeight) {
            flashingIndicator.style.display = 'block';
        } else {
            flashingIndicator.style.display = 'none';
        }
    }
    
    // Update color class on digitizer display
    if (digitizerDisplay) {
        digitizerDisplay.classList.remove('digitizer-red', 'digitizer-green');
        if (isIdleWithWeight) {
            digitizerDisplay.classList.add('digitizer-red');
        } else {
            digitizerDisplay.classList.add('digitizer-green');
        }
    }
    
    // Segment patterns for digits 0-9
    const segmentPatterns = {
        '0': ['a', 'b', 'c', 'd', 'e', 'f'],
        '1': ['b', 'c'],
        '2': ['a', 'b', 'd', 'e', 'g'],
        '3': ['a', 'b', 'c', 'd', 'g'],
        '4': ['b', 'c', 'f', 'g'],
        '5': ['a', 'c', 'd', 'f', 'g'],
        '6': ['a', 'c', 'd', 'e', 'f', 'g'],
        '7': ['a', 'b', 'c'],
        '8': ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
        '9': ['a', 'b', 'c', 'd', 'f', 'g']
    };
    
    // Update each digit
    const digits = document.querySelectorAll('.seven-segment-display .digit');
    digits.forEach((digit, index) => {
        const digitValue = index < weightStr.length ? weightStr[index] : '0';
        const activeSegments = segmentPatterns[digitValue] || [];
        
        // Reset all segments
        digit.querySelectorAll('.segment').forEach(seg => {
            seg.classList.remove('active');
        });
        
        // Activate required segments
        activeSegments.forEach(segName => {
            const seg = digit.querySelector(`.seg-${segName}`);
            if (seg) {
                seg.classList.add('active');
            }
        });
    });
}

// Update top display text
function updateTopDisplay(text) {
    const topDisplay = document.getElementById('top-display');
    if (topDisplay) {
        const displayContent = topDisplay.querySelector('.display-content');
        if (displayContent) {
            displayContent.textContent = text;
        }
    }
}

// Initialize MQTT Connection
function initMQTT() {
    // Wait for Paho library to load
    if (typeof Paho === 'undefined') {
        console.error('Paho MQTT library not loaded. Please check the script tag.');
        // Retry after a short delay
        setTimeout(() => {
            if (typeof Paho !== 'undefined') {
                initMQTT();
            } else {
                console.error('Paho MQTT library failed to load. Retrying in 5 seconds...');
                setTimeout(initMQTT, 5000);
            }
        }, 100);
        return;
    }
    
    // Try next configuration
    if (currentConfigIndex >= MQTT_CONFIGS.length) {
        console.error('All MQTT connection configurations failed. Please check your Mosquitto WebSocket configuration.');
        console.log('To enable WebSocket in Mosquitto, add to mosquitto.conf:');
        console.log('  listener 1883');
        console.log('  protocol mqtt');
        console.log('  listener 9001');
        console.log('  protocol websockets');
        currentConfigIndex = 0; // Reset and retry all configs
        setTimeout(initMQTT, 10000); // Wait 10 seconds before retrying
        return;
    }
    
    const config = MQTT_CONFIGS[currentConfigIndex];
    
    try {
        // Create MQTT client - handle different library versions
        let ClientClass;
        if (Paho.Client) {
            // Newer version: Paho.Client
            ClientClass = Paho.Client;
        } else if (Paho.MQTT && Paho.MQTT.Client) {
            // Older version: Paho.MQTT.Client
            ClientClass = Paho.MQTT.Client;
        } else {
            throw new Error('Paho Client class not found. Available: ' + Object.keys(Paho).join(', '));
        }
        
        // Constructor: new Paho.Client(host, port, path, clientId)
        mqttClient = new ClientClass(MQTT_BROKER_HOST, config.port, config.path, MQTT_CLIENT_ID);
        
        // Set callback handlers
        mqttClient.onConnectionLost = onConnectionLost;
        mqttClient.onMessageArrived = onMessageArrived;
        
        // Connect options
        const connectOptions = {
            onSuccess: onConnect,
            onFailure: onConnectFailure,
            timeout: 3,
            keepAliveInterval: 30,
            cleanSession: true,
            useSSL: false,
            mqttVersion: 4
        };
        
        // Connect to broker
        console.log(`[${currentConfigIndex + 1}/${MQTT_CONFIGS.length}] Trying MQTT connection: ws://${MQTT_BROKER_HOST}:${config.port}${config.path}`);
        mqttClient.connect(connectOptions);
        
    } catch (error) {
        console.error('Error initializing MQTT:', error);
        console.error('Error details:', error.message);
        // Try next configuration
        currentConfigIndex++;
        setTimeout(initMQTT, 2000);
    }
}

// MQTT Connection Success
function onConnect() {
    const config = MQTT_CONFIGS[currentConfigIndex];
    console.log(`✅ MQTT Connected successfully to ws://${MQTT_BROKER_HOST}:${config.port}${config.path}`);
    
    // Reset config index on successful connection
    currentConfigIndex = 0;
    
    mqttClient.subscribe('wb_frontend/#', {
        onSuccess: () => {
            console.log('✅ Subscribed to wb_frontend/#');
            requestCurrentStatus();
        },
        onFailure: (error) => {
            console.error('❌ Failed to subscribe to wb_frontend/#:', error);
            setTimeout(requestCurrentStatus, 400);
        }
    });
}

// Request current status from backend
function requestCurrentStatus() {
    if (!mqttClient || !mqttClient.isConnected()) {
        console.warn('MQTT not connected, cannot request status');
        return;
    }
    
    try {
        const topic = 'wb_frontend/request_status';
        const payload = 'request';  // Simple message to trigger status publish
        
        // Use publish method directly instead of Message object
        mqttClient.publish(topic, payload, 0);
        console.log('📤 Requested current status from backend');
    } catch (error) {
        console.error('❌ Error requesting status:', error);
    }
}

// MQTT Connection Failure
function onConnectFailure(error) {
    const config = MQTT_CONFIGS[currentConfigIndex];
    console.error(`❌ MQTT Connection failed to ws://${MQTT_BROKER_HOST}:${config.port}${config.path}:`, error.errorMessage || error);
    
    // Try next configuration
    currentConfigIndex++;
    setTimeout(() => {
        console.log('Trying next MQTT configuration...');
        initMQTT();
    }, 2000);
}

// MQTT Connection Lost
function onConnectionLost(responseObject) {
    if (responseObject.errorCode !== 0) {
        console.error('MQTT Connection lost:', responseObject.errorMessage);
        // Reset config index to start from beginning (port 9001 only)
        currentConfigIndex = 0;
        // Attempt to reconnect
        setTimeout(() => {
            console.log('Attempting to reconnect MQTT on port 9001...');
            initMQTT();
        }, 5000);
    }
}

// MQTT Message Arrived
function onMessageArrived(message) {
    const topic = message.destinationName;
    const payload = message.payloadString;
    
    console.log('MQTT Message received - Topic:', topic, 'Payload:', payload);
    
    try {
        if (topic === 'wb_frontend/position') {
            // Handle position message (-1 for reset, 0-5 for positions)
            const position = parseInt(payload, 10);
            if (!isNaN(position) && position >= -1 && position <= 5) {
                handlePositionMessage(position);
            }
        } else if (topic === 'wb_frontend/display') {
            // Handle display message (string)
            updateTopDisplay(payload);
        } else if (topic === 'wb_frontend/digitizer') {
            // Handle digitizer message (weight as string)
            const weight = parseInt(payload, 10);
            if (!isNaN(weight) && weight >= 0) {
                console.log(`[Digitizer] Received weight update: ${weight}, current position: ${AnimationState.truckPosition}`);
                updateDigitizer(weight);
            } else {
                console.warn(`[Digitizer] Invalid weight value: ${payload}`);
            }
        }
    } catch (error) {
        console.error('Error processing MQTT message:', error);
    }
}

// Handle position message
function handlePositionMessage(position) {
    console.log('Handling position:', position);
    
    if (position === -1) {
        // Position -1: Reset animation
        resetAnimation();
    } else if (position === 0) {
        // Position 0: RFID read - show truck
        triggerRFID();
    } else if (position >= 1 && position <= 3) {
        // Positions 1-3: Sensor cuts
        triggerSensor(position);
    } else if (position === 4) {
        // Position 4: Vehicle exit start
        triggerPosition(4);
    } else if (position === 5) {
        // Position 5: Vehicle exit completed
        triggerPosition(5);
    }
}

// Handle reset application button click
// Show reset confirmation modal
function showResetModal() {
    const modal = document.getElementById('reset-modal');
    if (modal) {
        modal.classList.add('show');
    }
}

// Hide reset confirmation modal
function hideResetModal() {
    const modal = document.getElementById('reset-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

// Handle reset application button click
function handleResetApplication() {
    if (!mqttClient || !mqttClient.isConnected()) {
        console.error('MQTT client not connected, cannot send reset request');
        alert('MQTT not connected. Please wait for connection...');
        return;
    }
    showResetModal();
}

function executeReset() {
    hideResetModal();

    try {
        mqttClient.publish('wb_frontend/reset_application', 'reset_application', 0);
        console.log('Reset application request sent over MQTT');

        const resetButton = document.getElementById('reset-button');
        if (resetButton) {
            const originalText = resetButton.textContent;
            resetButton.textContent = 'Resetting...';
            resetButton.disabled = true;
            resetButton.style.opacity = '0.6';
            setTimeout(() => {
                resetButton.textContent = originalText;
                resetButton.disabled = false;
                resetButton.style.opacity = '1';
            }, 2000);
        }
    } catch (error) {
        console.error('Error sending reset request:', error);
        alert('Failed to send reset request. Please try again.');
    }
}

// Initialize modal event handlers
function initModalHandlers() {
    const modal = document.getElementById('reset-modal');
    const okBtn = document.getElementById('modal-ok-btn');
    const cancelBtn = document.getElementById('modal-cancel-btn');
    
    // OK button - execute reset
    if (okBtn) {
        okBtn.addEventListener('click', executeReset);
    }
    
    // Cancel button - close modal
    if (cancelBtn) {
        cancelBtn.addEventListener('click', hideResetModal);
    }
    
    // Close modal when clicking outside the modal content
    if (modal) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                hideResetModal();
            }
        });
    }
    
    // Close modal on Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            hideResetModal();
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', init);
