/**
 * Weighbridge Web Frontend - Application Logic
 * Demo version with simulated transaction flow
 */

// Application state
const AppState = {
    currentStep: null,
    transactionData: {
        rfid: '',
        truckNumber: '',
        weight: null,
        sensors: {
            s1: false,
            s2: false,
            s3: false
        }
    },
    steps: [
        { id: 'vehicle_entering', element: null, completed: false },
        { id: 'reading_weight', element: null, completed: false },
        { id: 'rfid_read', element: null, completed: false },
        { id: 'validating_rfid', element: null, completed: false },
        { id: 'validating_anpr', element: null, completed: false },
        { id: 'validating_weight', element: null, completed: false },
        { id: 'exit_start', element: null, completed: false },
        { id: 'exit_completed', element: null, completed: false }
    ],
    currentPosition: -1,
    currentWeight: 0,
    displayMessage: 'System Operational',
    ioDependentsDisconnected: false,
    /** First Transaction Flow step that failed; later steps stay red until idle. */
    failedFromStep: null,
    /** True while ANPR status_check loop is active (anpr_status 0/2). */
    anprUpdateActive: false,
    uiResetTimer: null
};

// Application version (loaded from backend)
let APP_VERSION = 'unknown';
let UPDATE_STATUS = null;
let UPDATE_PROGRESS_TIMER = null;
/** Match server UPDATE_CHECK_INTERVAL_SECONDS: refresh UI from /api/update/status */
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
const MQTT_CLIENT_ID = 'weighbridge_dashboard_' + Math.random().toString(16).substr(2, 8);
const DEFAULT_STEP_CONTENT = {
    vehicle_entering: 'Waiting for vehicle...',
    reading_weight: 'Weight: 0 kg',
    rfid_read: 'Waiting for RFID scan...',
    validating_rfid: 'Waiting for validation...',
    validating_anpr: 'Waiting for ANPR...',
    validating_weight: 'Waiting for weight validation...',
    exit_start: '',
    exit_completed: 'Waiting for next transaction...'
};

function stepElementId(stepId) {
    return 'step-' + String(stepId || '').replace(/_/g, '-');
}

function stepDomState(stepId) {
    const step = AppState.steps.find((s) => s.id === stepId);
    if (!step || !step.element) return 'idle';
    const el = step.element;
    if (el.classList.contains('state-error')) return 'error';
    if (el.classList.contains('state-in-progress') || el.classList.contains('state-warning')) {
        return 'loading';
    }
    if (el.classList.contains('state-success')) return 'success';
    return 'idle';
}

function setFlowIcon(iconId, state) {
    const el = document.querySelector(`.flow-icon-item[data-icon="${iconId}"]`);
    if (!el) return;
    el.setAttribute('data-state', state || 'idle');
}

function resetFlowIcons() {
    document.querySelectorAll('.flow-icon-item[data-icon]').forEach((el) => {
        el.setAttribute('data-state', 'idle');
    });
    AppState.anprUpdateActive = false;
}

function clearUiResetTimer() {
    if (AppState.uiResetTimer) {
        clearTimeout(AppState.uiResetTimer);
        AppState.uiResetTimer = null;
    }
}

function scheduleUiResetAfterExit() {
    clearUiResetTimer();
    AppState.uiResetTimer = setTimeout(() => {
        AppState.uiResetTimer = null;
        applyIdleUi();
    }, 2000);
}

function syncFlowIcons(stepId, state, message) {
    const msg = String(message || '');
    const iconState = (iconId) =>
        document.querySelector(`[data-icon="${iconId}"]`)?.getAttribute('data-state') || 'idle';

    if (stepId === 'reading_weight') {
        setFlowIcon('weight_read', stepDomState('reading_weight'));
    }

    if (stepId === 'rfid_read') {
        setFlowIcon('rfid_read', stepDomState('rfid_read'));
        if ((state === 'in_progress' || state === 'success') && stepDomState('reading_weight') === 'success') {
            setFlowIcon('weight_read', 'success');
        }
    }

    if (stepId === 'validating_rfid') {
        setFlowIcon('rfid_validation', stepDomState('validating_rfid'));
        if (state === 'in_progress' || state === 'success') {
            if (stepDomState('rfid_read') === 'idle') {
                setFlowIcon('rfid_read', 'success');
            }
        }
    }

    if (stepId === 'validating_anpr') {
        if (state === 'in_progress') {
            setFlowIcon('anpr_read', 'loading');
        } else if (state === 'warning' || state === 'error') {
            setFlowIcon('anpr_read', 'error');
            setFlowIcon('anpr_update', 'loading');
            AppState.anprUpdateActive = true;
        } else if (state === 'success') {
            setFlowIcon('anpr_read', 'success');
            if (AppState.anprUpdateActive) {
                setFlowIcon('anpr_update', 'success');
            } else {
                setFlowIcon('anpr_update', 'skipped');
            }
        } else if (/Err-0|Err-2|mismatch|not readable/i.test(msg)) {
            setFlowIcon('anpr_read', 'error');
            setFlowIcon('anpr_update', 'loading');
            AppState.anprUpdateActive = true;
        }
    }

    if (stepId === 'validating_weight') {
        setFlowIcon('weight_validation', stepDomState('validating_weight'));
        if (state === 'in_progress' || state === 'success' || state === 'error' || state === 'warning') {
            if (iconState('weight_read') === 'idle' || stepDomState('reading_weight') === 'success') {
                if (stepDomState('reading_weight') !== 'error') {
                    setFlowIcon('weight_read', 'success');
                }
            }
            if (AppState.anprUpdateActive) {
                if (iconState('anpr_update') === 'loading') {
                    setFlowIcon('anpr_update', 'success');
                }
            } else if (iconState('anpr_update') === 'idle') {
                setFlowIcon('anpr_update', 'skipped');
            }
            if (stepDomState('anpr_read') === 'idle' && iconState('anpr_read') === 'idle') {
                setFlowIcon('anpr_read', 'success');
            }
        }
    }

    if (stepId === 'exit_start') {
        setFlowIcon('vehicle_exit', stepDomState('exit_start'));
        if (state === 'in_progress' || state === 'success') {
            if (iconState('weight_read') === 'idle' && stepDomState('reading_weight') === 'success') {
                setFlowIcon('weight_read', 'success');
            }
            if (
                iconState('weight_validation') === 'idle' &&
                stepDomState('validating_weight') === 'success'
            ) {
                setFlowIcon('weight_validation', 'success');
            }
            if (AppState.anprUpdateActive) {
                if (iconState('anpr_update') === 'loading') {
                    setFlowIcon('anpr_update', 'success');
                }
            } else if (iconState('anpr_update') === 'idle') {
                setFlowIcon('anpr_update', 'skipped');
            }
        }
    }

    if (stepId === 'exit_completed') {
        if (state === 'success' || state === 'in_progress') {
            setFlowIcon('truck_exited', 'success');
            if (iconState('vehicle_exit') === 'idle') {
                setFlowIcon('vehicle_exit', 'success');
            }
            scheduleUiResetAfterExit();
        } else if (state === 'error') {
            setFlowIcon('truck_exited', 'error');
        }
    }
}

function openFlowDetailsModal() {
    const modal = document.getElementById('flow-details-modal');
    if (!modal) return;
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
}

function closeFlowDetailsModal() {
    const modal = document.getElementById('flow-details-modal');
    if (!modal) return;
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
}

function initFlowDetailsUi() {
    const openBtn = document.getElementById('flow-details-btn');
    const closeBtn = document.getElementById('flow-details-close');
    const modal = document.getElementById('flow-details-modal');
    if (openBtn) openBtn.addEventListener('click', openFlowDetailsModal);
    if (closeBtn) closeBtn.addEventListener('click', closeFlowDetailsModal);
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeFlowDetailsModal();
        });
    }
    syncFlowIcons();
}

function formatSensorCuts(sensors) {
    const cuts = [];
    if (sensors.s1) cuts.push('Sensor 1 Cut');
    if (sensors.s2) cuts.push('Sensor 2 Cut');
    if (sensors.s3) cuts.push('Sensor 3 Cut');
    return cuts.join(', ') || '';
}

const SENSOR_LABELS = {
    s1: 'S1 Entry',
    s2: 'S2 Weighbridge',
    s3: 'S3 Exit'
};

/** Idle danger warning is only for platform (WB) and exit - not entry. */
const IDLE_DANGER_SENSORS = ['s2', 's3'];

function isApplicationIdle() {
    return AppState.currentPosition === -1;
}

function isIdleDangerSensor(sensorId) {
    return IDLE_DANGER_SENSORS.indexOf(String(sensorId || '').toLowerCase()) !== -1;
}

function activeIdleSensors() {
    const sensors = AppState.transactionData.sensors || {};
    return IDLE_DANGER_SENSORS.filter((id) => !!sensors[id]);
}

function updateCheckSensorPopup() {
    const popup = document.getElementById('check-sensor-popup');
    if (!popup) return;
    const active = isApplicationIdle() ? activeIdleSensors() : [];
    const show = active.length > 0;
    popup.classList.toggle('is-visible', show);
    popup.setAttribute('aria-hidden', show ? 'false' : 'true');
    const list = document.getElementById('check-sensor-list');
    if (list) {
        list.innerHTML = active
            .map((id) => '<li>' + (SENSOR_LABELS[id] || id.toUpperCase()) + ' active</li>')
            .join('');
    }
    ['s1', 's2', 's3'].forEach((id) => {
        paintSensorBadge(id, !!(AppState.transactionData.sensors || {})[id]);
    });
}

function showApiAlert(title, detail) {
    const popup = document.getElementById('api-alert-popup');
    if (!popup) return;
    const titleEl = document.getElementById('api-alert-title');
    const detailEl = document.getElementById('api-alert-detail');
    if (titleEl) titleEl.textContent = title || 'SERVICE ERROR';
    if (detailEl) detailEl.textContent = detail || '';
    popup.classList.add('is-visible');
    popup.setAttribute('aria-hidden', 'false');
}

function hideApiAlert() {
    const popup = document.getElementById('api-alert-popup');
    if (!popup) return;
    popup.classList.remove('is-visible');
    popup.setAttribute('aria-hidden', 'true');
}

function initApiAlertPopup() {
    const btn = document.getElementById('api-alert-dismiss');
    if (btn) btn.addEventListener('click', hideApiAlert);
}

// Initialize application
function init() {
    console.log('Initializing Weighbridge Dashboard...');
    
    // Initialize step elements
    AppState.steps.forEach(step => {
        step.element = document.getElementById(stepElementId(step.id));
        if (!step.element) {
            console.warn(`Step element not found: ${stepElementId(step.id)}`);
        }
    });
    
    applyDefaultStepContents();
    
    // Load application version for info button
    loadAppVersion();
    initUpdaterUI();

    // Live updates: MQTT WebSocket on the same host, port 9001
    initMQTT();
    initLoginModal();
    initResetModal();
    initFreePassModal();
    initApiAlertPopup();
    
    console.log('Dashboard initialized');
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
        console.log('Loaded application version:', APP_VERSION);
        const versionEl = document.getElementById('app-version');
        if (versionEl) {
            versionEl.textContent = 'v' + (APP_VERSION || 'unknown');
        }
    } catch (e) {
        console.warn('Error loading application version:', e);
    }
}

// Show version info when info button is clicked
function showVersionInfo() {
    const version = APP_VERSION || 'unknown';
    const message = 'Application Version: ' + version;
    // Simple, dependency-free UI for now
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

/** Bar only reflects download/apply; a finished GitHub check must not look like 100% downloaded. */
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

// Reset all steps to default (grey) state
function resetAllSteps() {
    AppState.failedFromStep = null;
    AppState.steps.forEach(step => {
        if (step.element) {
            step.element.classList.remove(
                'state-in-progress',
                'state-success',
                'state-error',
                'state-warning'
            );
            step.completed = false;
        }
    });
    AppState.currentStep = null;
    AppState.currentPosition = -1;
    AppState.currentWeight = 0;
    const liveSensors = AppState.transactionData.sensors || { s1: false, s2: false, s3: false };
    AppState.transactionData = {
        rfid: '',
        truckNumber: '',
        weight: null,
        sensors: liveSensors
    };
    
    // Reset RFID display
    const rfidBox = document.getElementById('rfid-display-box');
    const rfidValue = document.getElementById('rfid-value');
    const truckNumberValue = document.getElementById('truck-number-value');
    
    if (rfidBox) {
        rfidBox.classList.remove('has-rfid', 'has-truck', 'has-weight');
    }
    if (rfidValue) {
        rfidValue.textContent = '--';
    }
    if (truckNumberValue) {
        truckNumberValue.textContent = '--';
    }
    const weightValue = document.getElementById('weight-value');
    if (weightValue) {
        weightValue.textContent = '--';
    }
}

// Set step state
function stepIndex(stepId) {
    return AppState.steps.findIndex((s) => s.id === stepId);
}

function markFailureCascade(throughStepId) {
    const fromIdx = stepIndex(AppState.failedFromStep);
    const throughIdx = stepIndex(throughStepId);
    if (fromIdx < 0) return;
    const endIdx = throughIdx >= fromIdx ? throughIdx : AppState.steps.length - 1;
    for (let i = fromIdx; i <= endIdx; i++) {
        const step = AppState.steps[i];
        if (!step || !step.element) continue;
        step.element.classList.remove(
            'state-in-progress',
            'state-success',
            'state-warning'
        );
        step.element.classList.add('state-error');
        step.completed = false;
        if (i === fromIdx) continue;
        const contentElement = step.element.querySelector('.step-content');
        if (!contentElement) continue;
        const text = (contentElement.textContent || '').trim();
        const defaults = DEFAULT_STEP_CONTENT[step.id] || '';
        if (!text || text === '-' || text === defaults) {
            contentElement.textContent = 'Skipped due to earlier failure.';
        }
    }
}

function setStepState(stepId, state, data = {}) {
    const step = AppState.steps.find(s => s.id === stepId);
    if (!step) {
        console.warn(`⚠️ Step not found in AppState: ${stepId}. Available steps:`, AppState.steps.map(s => s.id));
        return;
    }
    if (!step.element) {
        console.warn(`⚠️ Step element not found: ${stepId}. Element ID should be: step-${stepId.replace('_', '-')}`);
        return;
    }
    
    // Remove all states
    step.element.classList.remove('state-in-progress', 'state-success', 'state-error', 'state-warning');
    
    // Apply new state
    if (state === 'in_progress') {
        markPriorStepsComplete(stepId);
        if (
            AppState.failedFromStep &&
            stepIndex(stepId) >= stepIndex(AppState.failedFromStep)
        ) {
            markFailureCascade(stepId);
            step.element.classList.add('state-error');
            AppState.currentStep = null;
        } else {
            step.element.classList.add('state-in-progress');
            AppState.currentStep = stepId;
        }
    } else if (state === 'success') {
        markPriorStepsComplete(stepId);
        if (
            AppState.failedFromStep &&
            stepIndex(stepId) >= stepIndex(AppState.failedFromStep)
        ) {
            markFailureCascade(stepId);
            step.element.classList.add('state-error');
            step.completed = false;
            AppState.currentStep = null;
        } else {
            step.element.classList.add('state-success');
            step.completed = true;
            AppState.currentStep = null;
        }
    } else if (state === 'error') {
        if (
            !AppState.failedFromStep ||
            stepIndex(stepId) < stepIndex(AppState.failedFromStep)
        ) {
            AppState.failedFromStep = stepId;
        }
        // Later steps (exit after failure) paint the cascade red; the first
        // failure only marks itself.
        if (stepIndex(stepId) > stepIndex(AppState.failedFromStep)) {
            markFailureCascade(stepId);
        }
        step.element.classList.add('state-error');
        AppState.currentStep = null;
    } else if (state === 'warning') {
        step.element.classList.add('state-warning');
        AppState.currentStep = stepId;
    } else {
        // Default state (grey)
        step.element.classList.remove('state-in-progress', 'state-success', 'state-error', 'state-warning');
    }
    
    // Update content if data provided
    const contentElement = step.element.querySelector('.step-content');
    if (!contentElement) {
        console.error(`❌ Content element not found for step: ${stepId}`);
        syncFlowIcons(stepId, state, data.content);
        return;
    }
    
    if (data.content !== undefined) {
        contentElement.textContent = data.content;
        console.log(`✅ Updated step ${stepId} content to: "${data.content}"`);
    } else if (data.sensors) {
        // Handle sensor updates for vehicle_entering and exit_start
        const sensorText = formatSensorCuts(data.sensors);
        contentElement.textContent = sensorText;
        // Update AppState sensors
        AppState.transactionData.sensors = { ...data.sensors };
    } else if (data.weight !== undefined) {
        // Handle weight updates for reading_weight
        if (stepId === 'reading_weight') {
            contentElement.textContent = `Weight: ${data.weight} kg`;
        } else if (stepId === 'validating_weight') {
            // For validating_weight, show truck number and weight
            const truckNo = AppState.transactionData.truckNumber || '';
            contentElement.textContent = `Truck Number: ${truckNo}, Weight: ${data.weight} kg`;
        }
        AppState.transactionData.weight = data.weight;
    } else if (data.truckNumber !== undefined) {
        // Handle truck number updates for validating_rfid
        contentElement.textContent = `Truck No: ${data.truckNumber}`;
        AppState.transactionData.truckNumber = data.truckNumber;
    }
    
    console.log(`Step ${stepId} set to ${state}`, data);
    syncFlowIcons(stepId, state, data.content);
}

function markPriorStepsComplete(stepId) {
    let reached = false;
    let failedSeen = false;
    AppState.steps.forEach((step) => {
        if (step.id === stepId) {
            reached = true;
            return;
        }
        if (reached || !step.element) return;

        if (
            step.element.classList.contains('state-error') ||
            step.id === AppState.failedFromStep
        ) {
            failedSeen = true;
            step.element.classList.remove(
                'state-in-progress',
                'state-success',
                'state-warning'
            );
            step.element.classList.add('state-error');
            return;
        }

        if (failedSeen || (AppState.failedFromStep && stepIndex(step.id) >= stepIndex(AppState.failedFromStep))) {
            step.element.classList.remove(
                'state-in-progress',
                'state-success',
                'state-warning'
            );
            step.element.classList.add('state-error');
            step.completed = false;
            return;
        }

        step.element.classList.remove('state-in-progress', 'state-error', 'state-warning');
        step.element.classList.add('state-success');
        step.completed = true;
    });
}

function applyDefaultStepContents() {
    resetAllSteps();
    Object.keys(DEFAULT_STEP_CONTENT).forEach((stepId) => {
        setStepState(stepId, 'default', { content: DEFAULT_STEP_CONTENT[stepId] });
    });
}

function showResetModal() {
    const modal = document.getElementById('reset-modal');
    if (modal) {
        modal.classList.add('show');
    }
}

function hideResetModal() {
    const modal = document.getElementById('reset-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

function applyIdleUi() {
    clearUiResetTimer();
    stopRfidCountdown();
    AppState.failedFromStep = null;
    applyDefaultStepContents();
    AppState.currentPosition = -1;
    AppState.currentWeight = 0;
    resetFlowIcons();
    closeFlowDetailsModal();
    updateCheckSensorPopup();
}

let operatorLoggedIn = false;

function setOperatorUnlocked(unlocked) {
    operatorLoggedIn = !!unlocked;
    const controls = document.getElementById('operator-controls');
    const loginBtn = document.getElementById('login-button');
    if (controls) controls.hidden = !operatorLoggedIn;
    if (loginBtn) {
        loginBtn.textContent = operatorLoggedIn ? 'Logout' : 'Login';
        loginBtn.classList.toggle('is-logout', operatorLoggedIn);
        loginBtn.disabled = false;
    }
}

function handleLoginButtonClick() {
    if (operatorLoggedIn) {
        setOperatorUnlocked(false);
        return;
    }
    showLoginModal();
}

function showLoginModal() {
    const modal = document.getElementById('login-modal');
    const err = document.getElementById('login-error');
    const spinner = document.getElementById('login-spinner');
    if (err) {
        err.hidden = true;
        err.textContent = '';
    }
    if (spinner) spinner.hidden = true;
    if (modal) modal.classList.add('show');
    const user = document.getElementById('login-username');
    if (user) user.focus();
}

function hideLoginModal() {
    const modal = document.getElementById('login-modal');
    const form = document.getElementById('login-form');
    const spinner = document.getElementById('login-spinner');
    if (spinner) spinner.hidden = true;
    if (form) form.reset();
    if (modal) modal.classList.remove('show');
}

function setLoginBusy(busy) {
    const spinner = document.getElementById('login-spinner');
    const submit = document.getElementById('login-submit-btn');
    const cancel = document.getElementById('login-cancel-btn');
    if (spinner) spinner.hidden = !busy;
    if (submit) submit.disabled = busy;
    if (cancel) cancel.disabled = busy;
}

function submitOperatorLogin(event) {
    if (event) event.preventDefault();
    const username = (document.getElementById('login-username') || {}).value || '';
    const password = (document.getElementById('login-password') || {}).value || '';
    const err = document.getElementById('login-error');
    if (err) {
        err.hidden = true;
        err.textContent = '';
    }
    setLoginBusy(true);
    fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password: password })
    })
        .then((resp) => resp.json().then((body) => ({ ok: resp.ok, body })))
        .then(({ ok, body }) => {
            if (!ok) {
                throw new Error((body && body.message) || 'Login failed');
            }
            setOperatorUnlocked(true);
            hideLoginModal();
        })
        .catch((error) => {
            if (err) {
                err.textContent = error.message || 'Invalid username or password';
                err.hidden = false;
            }
        })
        .finally(() => setLoginBusy(false));
}

function initLoginModal() {
    setOperatorUnlocked(false);
    const loginBtn = document.getElementById('login-button');
    const form = document.getElementById('login-form');
    const cancel = document.getElementById('login-cancel-btn');
    const modal = document.getElementById('login-modal');
    if (loginBtn) loginBtn.addEventListener('click', handleLoginButtonClick);
    if (form) form.addEventListener('submit', submitOperatorLogin);
    if (cancel) cancel.addEventListener('click', hideLoginModal);
    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) hideLoginModal();
        });
    }
}

function handleResetApplication() {
    if (!operatorLoggedIn) return;
    showResetModal();
}

function executeReset() {
    hideResetModal();

    const resetButton = document.getElementById('reset-button');
    const originalText = resetButton ? resetButton.textContent : 'Reset';
    if (resetButton) {
        resetButton.textContent = 'Resetting...';
        resetButton.disabled = true;
    }

    // HTTP only - MQTT + POST both called force_reset and cut application_reset.wav.
    fetch('/api/reset', { method: 'POST' })
        .then((resp) => {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            console.log('Application reset to IDLE');
            applyIdleUi();
        })
        .catch((error) => {
            console.error('Reset failed:', error);
            alert('Failed to reset the application. Please try again.');
        })
        .finally(() => {
            if (resetButton) {
                setTimeout(() => {
                    resetButton.textContent = originalText;
                    resetButton.disabled = false;
                }, 1500);
            }
        });
}

function initResetModal() {
    const modal = document.getElementById('reset-modal');
    const okBtn = document.getElementById('modal-ok-btn');
    const cancelBtn = document.getElementById('modal-cancel-btn');

    if (okBtn) {
        okBtn.addEventListener('click', executeReset);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', hideResetModal);
    }
    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) {
                hideResetModal();
            }
        });
    }
}

function showFreePassModal() {
    const modal = document.getElementById('free-pass-modal');
    if (modal) {
        modal.classList.add('show');
    }
}

function hideFreePassModal() {
    const modal = document.getElementById('free-pass-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

function handleFreePass() {
    if (!operatorLoggedIn) return;
    showFreePassModal();
}

function applyFreePassUi() {
    setStepState('exit_start', 'in_progress', {
        content: 'Free pass - all lights green, all booms open. Waiting for exit sensor.'
    });
    updateTrafficLightStatus('entry', { color: 'GREEN' });
    updateTrafficLightStatus('exit', { color: 'GREEN' });
    updateBoomBarrierStatus('entry', { position: 'Open' });
    updateBoomBarrierStatus('exit', { position: 'Open' });
}

function executeFreePass() {
    hideFreePassModal();

    const btn = document.getElementById('free-pass-button');
    const originalText = btn ? btn.textContent : 'Free Pass';
    if (btn) {
        btn.textContent = 'Opening...';
        btn.disabled = true;
    }

    let mqttSent = false;
    if (mqttClient && mqttClient.isConnected && mqttClient.isConnected()) {
        try {
            mqttClient.publish('wb_frontend/free_pass', 'free_pass', 0);
            mqttSent = true;
            console.log('Free pass request sent over MQTT');
        } catch (error) {
            console.warn('MQTT free pass publish failed:', error);
        }
    }

    fetch('/api/free-pass', { method: 'POST' })
        .then((resp) => {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            console.log('Free pass granted - waiting for exit sensor');
            applyFreePassUi();
        })
        .catch((error) => {
            if (mqttSent) {
                applyFreePassUi();
                return;
            }
            console.error('Free pass failed:', error);
            alert('Failed to start free pass. Please try again.');
        })
        .finally(() => {
            if (btn) {
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.disabled = false;
                }, 1500);
            }
        });
}

function initFreePassModal() {
    const modal = document.getElementById('free-pass-modal');
    const okBtn = document.getElementById('free-pass-ok-btn');
    const cancelBtn = document.getElementById('free-pass-cancel-btn');

    if (okBtn) {
        okBtn.addEventListener('click', executeFreePass);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', hideFreePassModal);
    }
    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) {
                hideFreePassModal();
            }
        });
    }
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') {
            return;
        }
        hideResetModal();
        hideFreePassModal();
    });
}

window.handleResetApplication = handleResetApplication;
window.handleFreePass = handleFreePass;

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
    
    // Subscribe once with a wildcard so status + device_status always arrive.
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

    updateSystemStatus('Connected', true);
}

function requestCurrentStatus() {
    if (!mqttClient || !mqttClient.isConnected()) {
        console.warn('MQTT not connected, cannot request status');
        return;
    }
    try {
        mqttClient.publish('wb_frontend/request_status', 'request', 0);
        console.log('Requested current status from backend over MQTT');
    } catch (error) {
        console.error('Error requesting status:', error);
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
        // Update system status
        updateSystemStatus('Disconnected', false);
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
            AppState.displayMessage = payload;
            updateSystemStatus(payload, true);
        } else if (topic === 'wb_frontend/digitizer') {
            // Handle digitizer message (weight as string)
            const weight = parseInt(payload, 10);
            if (!isNaN(weight) && weight >= 0) {
                AppState.currentWeight = weight;
                updateWeightDisplay(weight);
            }
        } else if (topic === 'wb_frontend/status') {
            // Handle detailed status message (JSON)
            try {
                const statusData = JSON.parse(payload);
                handleStatusMessage(statusData);
            } catch (e) {
                console.error('Error parsing status message:', e);
            }
        } else if (topic === 'wb_frontend/device_status') {
            // Handle device status message (JSON)
            try {
                const deviceStatus = JSON.parse(payload);
                handleDeviceStatus(deviceStatus);
            } catch (e) {
                console.error('Error parsing device status message:', e);
            }
        } else if (topic === 'wb_frontend/rfid') {
            // Handle RFID data message (JSON)
            try {
                const rfidData = JSON.parse(payload);
                handleRfidData(rfidData);
            } catch (e) {
                console.error('Error parsing RFID message:', e);
            }
        }
    } catch (error) {
        console.error('Error processing MQTT message:', error);
    }
}

// Handle status message from backend
let rfidCountdownTimer = null;
let rfidCountdownStepId = null;

function stopRfidCountdown() {
    if (rfidCountdownTimer) {
        clearInterval(rfidCountdownTimer);
        rfidCountdownTimer = null;
    }
    rfidCountdownStepId = null;
}

function startRfidCountdown(stepId, baseMessage, seconds) {
    stopRfidCountdown();
    let remaining = Math.max(0, Math.floor(Number(seconds) || 0));
    rfidCountdownStepId = stepId;
    const paint = () => {
        if (rfidCountdownStepId !== stepId) {
            return;
        }
        const msg = remaining > 0
            ? `${baseMessage} (${remaining}s)`
            : baseMessage;
        setStepState(stepId, 'in_progress', { content: msg });
    };
    paint();
    if (remaining <= 0) {
        return;
    }
    rfidCountdownTimer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
            stopRfidCountdown();
            setStepState(stepId, 'in_progress', { content: baseMessage });
            return;
        }
        paint();
    }, 1000);
}

function handleStatusMessage(statusData) {
    const { step, status, message } = statusData;
    console.log('📨 Handling status message:', step, status, message);
    
    // Find the step in AppState
    const stepObj = AppState.steps.find(s => s.id === step);
    
    if (!step) {
        console.warn('⚠️ Status message missing step field:', statusData);
        return;
    }
    
    if (!stepObj) {
        console.warn('⚠️ Status message received for unknown step:', step, 'Available steps:', AppState.steps.map(s => s.id));
        return;
    }
    
    if (!stepObj.element) {
        console.warn('⚠️ Step element not found for:', step);
        return;
    }
    
    console.log('✅ Updating step:', step, 'to state:', status, 'with message:', message);

    stopRfidCountdown();

    if (status === 'error') {
        setStepState(step, 'error', { content: message });
        if (statusData.popup) {
            showApiAlert(statusData.popup_title || message, message);
        }
        return;
    }
    if (status === 'info' && (step === 'rfid_read' || step === 'vehicle_entering')) {
        hideApiAlert();
    }

    const countdown = Number(statusData.countdown_sec);
    if (
        Number.isFinite(countdown) &&
        countdown > 0 &&
        step === 'rfid_read' &&
        (status === 'info' || status === 'in_progress')
    ) {
        startRfidCountdown(step, message || DEFAULT_STEP_CONTENT.rfid_read, countdown);
        return;
    }

    if (status === 'idle' || status === 'default') {
        setStepState(step, 'default', { content: message });
        return;
    } 
    // Update the appropriate step with the status message
    if (status === 'success') {
        setStepState(step, 'success', { content: message });
    } else if (status === 'warning') {
        setStepState(step, 'warning', { content: message });
    } else {
        // info or in_progress
        setStepState(step, 'in_progress', { content: message });
    }
}

// Handle position message
function handlePositionMessage(position) {
    console.log('Handling position:', position);
    AppState.currentPosition = position;
    
    if (position === -1) {
        applyIdleUi();
        updateWeightDisplay(0);
    } else {
        updateCheckSensorPopup();
    }
    // Note: Detailed status messages are now handled via wb_frontend/status topic
    // Position messages are used for state tracking only
}

// Update weight display
function formatWeightTonKg(weightKg) {
    const total = Math.max(0, Math.floor(Number(weightKg) || 0));
    const tonnes = Math.floor(total / 1000);
    const remKg = total % 1000;
    return tonnes + ' T ' + remKg + ' kg';
}

function showTransactionInfoBox() {
    // RFID / ANPR / Weight panel stays visible; values update in place.
}

function updateInfoBoxWeight(weightKg) {
    const weightValue = document.getElementById('weight-value');
    const rfidBox = document.getElementById('rfid-display-box');
    const total = Math.max(0, Math.floor(Number(weightKg) || 0));
    if (weightValue) {
        weightValue.textContent = total > 0 ? formatWeightTonKg(total) : '--';
    }
    if (rfidBox && total > 0) {
        rfidBox.classList.add('has-weight');
        showTransactionInfoBox();
    }
}

function updateWeightDisplay(weight) {
    AppState.currentWeight = weight;
    AppState.transactionData.weight = weight;
    updateInfoBoxWeight(weight);

    // Update reading_weight step based on current position
    if (AppState.currentPosition === 3) {
        // Position 3: Vehicle at centre, weight capture in progress
        // Update weight continuously during capture
        setStepState('reading_weight', 'in_progress', { weight: weight });
    } else if (AppState.currentPosition === 4 || AppState.currentPosition === 5) {
        // After weight capture, keep the final weight on reading_weight.
        // validating_weight is owned by wb_frontend/status (success/error).
        setStepState('reading_weight', 'success', { weight: weight });
    } else if (AppState.currentPosition >= 0 && AppState.currentPosition < 3) {
        // Before weight capture, weight might be published during pre-flight checks
        // Don't update the step yet, but store the weight
    }
}

// Handle device status message from backend
function handleDeviceStatus(devices) {
    console.log('📡 Device status update received:', devices);
    
    // Update RFID Reader
    if (devices.rfid_reader) {
        updateDeviceStatus('rfid-reader', devices.rfid_reader);
    }
    
    // Update Digitizer
    if (devices.digitizer) {
        updateDeviceStatus('digitizer', devices.digitizer);
    }
    
    // Update I/O Controller
    if (devices.io_controller) {
        updateDeviceStatus('io-controller', devices.io_controller);
    }
    AppState.ioDependentsDisconnected = !!(
        (devices.io_controller && devices.io_controller.connected === false) ||
        (devices.sensors && devices.sensors.connected === false)
    );

    // Update Sensors
    if (devices.sensors || AppState.ioDependentsDisconnected) {
        const s1 = AppState.ioDependentsDisconnected
            ? false
            : !!(devices.sensors.s1 || devices.sensors.sensor1);
        const s2 = AppState.ioDependentsDisconnected
            ? false
            : !!(devices.sensors.s2 || devices.sensors.sensor2);
        const s3 = AppState.ioDependentsDisconnected
            ? false
            : !!(devices.sensors.s3 || devices.sensors.sensor3);
        AppState.transactionData.sensors = { s1, s2, s3 };
        updateSensorStatus('s1', s1);
        updateSensorStatus('s2', s2);
        updateSensorStatus('s3', s3);
        updateCheckSensorPopup();
    }
    
    // Update Traffic Lights
    if (AppState.ioDependentsDisconnected) {
        updateTrafficLightStatus('entry', { connected: false });
        updateTrafficLightStatus('exit', { connected: false });
    } else {
        if (devices.traffic_light_entry) {
            updateTrafficLightStatus('entry', devices.traffic_light_entry);
        }
        if (devices.traffic_light_exit) {
            updateTrafficLightStatus('exit', devices.traffic_light_exit);
        }
    }
    
    // Update Boom Barriers
    if (AppState.ioDependentsDisconnected) {
        updateBoomBarrierStatus('entry', { connected: false });
        updateBoomBarrierStatus('exit', { connected: false });
    } else {
        if (devices.boom_barrier_entry) {
            updateBoomBarrierStatus('entry', devices.boom_barrier_entry);
        }
        if (devices.boom_barrier_exit) {
            updateBoomBarrierStatus('exit', devices.boom_barrier_exit);
        }
    }
}

// Update device status in UI
function updateDeviceStatus(deviceId, status) {
    // Find the device item by looking for device name in the DOM
    const deviceItems = document.querySelectorAll('.device-item');
    
    deviceItems.forEach(item => {
        const deviceName = item.querySelector('.device-name');
        if (!deviceName) return;
        
        let match = false;
        if (deviceId === 'rfid-reader' && deviceName.textContent.includes('RFID Reader')) {
            match = true;
        } else if (deviceId === 'digitizer' && deviceName.textContent.includes('Digitizer')) {
            match = true;
        } else if (deviceId === 'io-controller' && deviceName.textContent.includes('I/O Controller')) {
            match = true;
        }
        
        if (match) {
            const statusElement = item.querySelector('.device-status');
            const detailsElement = item.querySelector('.device-details');
            
            if (statusElement) {
                const indicator = statusElement.querySelector('.status-indicator');
                
                // Find text node (status text is usually the last text node)
                let statusTextNode = null;
                for (let i = statusElement.childNodes.length - 1; i >= 0; i--) {
                    const node = statusElement.childNodes[i];
                    if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
                        statusTextNode = node;
                        break;
                    }
                }
                
                if (status.connected) {
                    statusElement.className = 'device-status status-connected';
                    if (indicator) indicator.style.backgroundColor = '#28a745';
                    if (statusTextNode) {
                        statusTextNode.textContent = 'Connected';
                    } else {
                        // Remove all text nodes and add new one
                        Array.from(statusElement.childNodes).forEach(node => {
                            if (node.nodeType === Node.TEXT_NODE) {
                                node.remove();
                            }
                        });
                        statusElement.appendChild(document.createTextNode('Connected'));
                    }
                } else {
                    statusElement.className = 'device-status status-disconnected';
                    if (indicator) indicator.style.backgroundColor = '#dc3545';
                    if (statusTextNode) {
                        statusTextNode.textContent = 'Disconnected';
                    } else {
                        Array.from(statusElement.childNodes).forEach(node => {
                            if (node.nodeType === Node.TEXT_NODE) {
                                node.remove();
                            }
                        });
                        statusElement.appendChild(document.createTextNode('Disconnected'));
                    }
                }
            }
            
            if (detailsElement && status.port) {
                if (deviceId === 'rfid-reader') {
                    detailsElement.textContent = `Port: ${status.port}`;
                } else if (deviceId === 'digitizer') {
                    detailsElement.textContent = `Port: ${status.port}`;
                } else if (deviceId === 'io-controller') {
                    detailsElement.textContent = status.port !== 'N/A' ? `Port: ${status.port}` : 'Modbus RTU';
                }
            }
        }
    });
}

function paintSensorBadge(sensorId, active) {
    const sensorItems = document.querySelectorAll('.sensor-item');
    sensorItems.forEach(item => {
        const sensorName = item.querySelector('.sensor-name');
        if (sensorName && sensorName.textContent.trim().toUpperCase() === sensorId.toUpperCase()) {
            const stateElement = item.querySelector('.sensor-state');
            if (stateElement) {
                if (AppState.ioDependentsDisconnected) {
                    stateElement.className = 'sensor-state state-disconnected';
                    stateElement.textContent = 'Disconnected';
                } else if (active) {
                    const danger = isApplicationIdle() && isIdleDangerSensor(sensorId);
                    stateElement.className = danger
                        ? 'sensor-state state-active state-danger'
                        : 'sensor-state state-active';
                    stateElement.textContent = 'Active';
                } else {
                    stateElement.className = 'sensor-state state-inactive';
                    stateElement.textContent = 'Inactive';
                }
            }
        }
    });
}

// Update sensor status
function updateSensorStatus(sensorId, active) {
    const key = String(sensorId || '').toLowerCase();
    if (!AppState.transactionData.sensors) {
        AppState.transactionData.sensors = { s1: false, s2: false, s3: false };
    }
    if (key in AppState.transactionData.sensors) {
        AppState.transactionData.sensors[key] = !!active;
    }
    paintSensorBadge(sensorId, active);
}

function _writeNamedDeviceStatus(item, className, color, text) {
    const statusElement = item.querySelector('.device-status');
    if (!statusElement) return;
    const indicator = statusElement.querySelector('.status-indicator');
    let statusTextNode = null;
    for (let i = statusElement.childNodes.length - 1; i >= 0; i--) {
        const node = statusElement.childNodes[i];
        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
            statusTextNode = node;
            break;
        }
    }
    statusElement.className = className;
    if (indicator) indicator.style.backgroundColor = color;
    if (statusTextNode) {
        statusTextNode.textContent = text;
    } else {
        Array.from(statusElement.childNodes).forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                node.remove();
            }
        });
        statusElement.appendChild(document.createTextNode(text));
    }
}

// Update traffic light status
function updateTrafficLightStatus(type, status) {
    const deviceItems = document.querySelectorAll('.device-item');
    deviceItems.forEach(item => {
        const deviceName = item.querySelector('.device-name');
        if (deviceName && deviceName.textContent.includes(`Traffic Light (${type === 'entry' ? 'Entry' : 'Exit'})`)) {
            if (status.connected === false || AppState.ioDependentsDisconnected) {
                _writeNamedDeviceStatus(item, 'device-status status-disconnected', '#dc3545', 'Disconnected');
            } else if (status.color === 'GREEN') {
                _writeNamedDeviceStatus(item, 'device-status status-active', '#28a745', 'Green');
            } else {
                _writeNamedDeviceStatus(item, 'device-status status-inactive', '#dc3545', 'Red');
            }
        }
    });
}

// Update boom barrier status
function updateBoomBarrierStatus(type, status) {
    const deviceItems = document.querySelectorAll('.device-item');
    deviceItems.forEach(item => {
        const deviceName = item.querySelector('.device-name');
        if (deviceName && deviceName.textContent.includes(`Boom Barrier (${type === 'entry' ? 'Entry' : 'Exit'})`)) {
            if (status.connected === false || AppState.ioDependentsDisconnected) {
                _writeNamedDeviceStatus(item, 'device-status status-disconnected', '#dc3545', 'Disconnected');
            } else if (status.position === 'Open') {
                _writeNamedDeviceStatus(item, 'device-status status-active', '#28a745', 'Open');
            } else {
                _writeNamedDeviceStatus(item, 'device-status status-inactive', '#dc3545', 'Closed');
            }
        }
    });
}

// Handle RFID data
function handleRfidData(rfidData) {
    console.log('📡 RFID data received:', rfidData);
    
    const rfidBox = document.getElementById('rfid-display-box');
    const rfidValue = document.getElementById('rfid-value');
    const truckNumberValue = document.getElementById('truck-number-value');
    
    if (!rfidBox || !rfidValue || !truckNumberValue) {
        console.warn('RFID display elements not found');
        return;
    }
    
    // Update RFID value
    if (rfidData.rfid) {
        rfidValue.textContent = rfidData.rfid;
        rfidBox.classList.add('has-rfid');
        
        // Update AppState
        AppState.transactionData.rfid = rfidData.rfid;
    }
    
    // Update truck number
    if (rfidData.truck_number) {
        truckNumberValue.textContent = rfidData.truck_number;
        rfidBox.classList.add('has-truck');
        
        // Update AppState
        AppState.transactionData.truckNumber = rfidData.truck_number;
    } else {
        // Truck number not available yet
        truckNumberValue.textContent = '--';
        rfidBox.classList.remove('has-truck');
    }
    
    // Show the box if RFID is available
    if (rfidData.rfid) {
        showTransactionInfoBox();
    }
    if (AppState.currentWeight) {
        updateInfoBoxWeight(AppState.currentWeight);
    }
}

// Update system status
function updateSystemStatus(message, connected) {
    const statusText = document.getElementById('status-text');
    const statusIndicator = document.querySelector('.status-indicator-dot');
    
    if (statusText) {
        statusText.textContent = message;
    }
    
    if (statusIndicator) {
        if (connected) {
            statusIndicator.style.backgroundColor = '#28a745';
        } else {
            statusIndicator.style.backgroundColor = '#dc3545';
        }
    }
}

// Camera Modal Functions
let cameraStreamInterval = null;

function openCameraModal() {
    const modal = document.getElementById('camera-modal');
    const streamImg = document.getElementById('camera-stream');
    const loadingDiv = document.getElementById('camera-loading');
    const errorDiv = document.getElementById('camera-error');
    
    if (!modal) return;
    
    modal.classList.add('active');
    loadingDiv.style.display = 'flex';
    errorDiv.style.display = 'none';
    streamImg.classList.remove('active');
    
    // Start streaming
    const streamUrl = '/api/camera/stream';
    streamImg.src = streamUrl + '?t=' + Date.now(); // Add timestamp to prevent caching
    streamImg.onload = () => {
        loadingDiv.style.display = 'none';
        streamImg.classList.add('active');
    };
    streamImg.onerror = () => {
        loadingDiv.style.display = 'none';
        errorDiv.style.display = 'flex';
    };
    
    // Refresh stream every 30ms for smooth playback (MJPEG stream)
    cameraStreamInterval = setInterval(() => {
        streamImg.src = streamUrl + '?t=' + Date.now();
    }, 30);
}

function closeCameraModal() {
    const modal = document.getElementById('camera-modal');
    const streamImg = document.getElementById('camera-stream');
    
    if (!modal) return;
    
    modal.classList.remove('active');
    
    // Stop streaming
    if (cameraStreamInterval) {
        clearInterval(cameraStreamInterval);
        cameraStreamInterval = null;
    }
    
    streamImg.src = '';
    streamImg.classList.remove('active');
}

// Initialize camera modal event listeners
function initCameraModal() {
    const cameraBtn = document.getElementById('camera-btn');
    const closeBtn = document.getElementById('camera-modal-close');
    const modal = document.getElementById('camera-modal');
    
    if (cameraBtn) {
        cameraBtn.addEventListener('click', openCameraModal);
    }
    
    if (closeBtn) {
        closeBtn.addEventListener('click', closeCameraModal);
    }
    
    // Close modal when clicking outside
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeCameraModal();
            }
        });
    }
    
    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal && modal.classList.contains('active')) {
            closeCameraModal();
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    init();
    initCameraModal();
    initFlowDetailsUi();
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
});

