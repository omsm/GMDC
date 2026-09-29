/**
 * Mines Checkpoint operator dashboard - live MQTT updates.
 */

const AppState = {
    currentStep: null,
    transactionData: {
        rfid: '',
        truckNumber: '',
        sensors: { s1: false }
    },
    steps: [
        { id: 'rfid_read', element: null, completed: false },
        { id: 'validating_rfid', element: null, completed: false },
        { id: 'validating_anpr', element: null, completed: false },
        { id: 'entry_granted', element: null, completed: false },
        { id: 'wait_crossing', element: null, completed: false },
        { id: 'exit_completed', element: null, completed: false }
    ],
    currentPosition: -1,
    displayMessage: 'System Operational',
    ioDependentsDisconnected: false,
    /** First Transaction Flow step that failed; later steps stay red until idle. */
    failedFromStep: null,
    /** True while ANPR status_check loop is active (anpr_status 0/2). */
    anprUpdateActive: false,
    uiResetTimer: null
};

let APP_VERSION = 'unknown';
let UPDATE_STATUS = null;
let UPDATE_PROGRESS_TIMER = null;
const UPDATE_STATUS_POLL_MS = 2 * 60 * 1000;

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
const MQTT_CLIENT_ID = 'mines_entry_dashboard_' + Math.random().toString(16).substr(2, 8);
const DEFAULT_STEP_CONTENT = {
    rfid_read: 'Waiting for RFID scan...',
    validating_rfid: 'Waiting for validation...',
    validating_anpr: 'Waiting for ANPR...',
    entry_granted: 'Waiting for grant...',
    wait_crossing: 'Waiting for vehicle to clear entry sensor...',
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

    if (stepId === 'rfid_read') {
        // Green as soon as a tag is read (before OCI)
        setFlowIcon('rfid_read', stepDomState('rfid_read'));
    }
    if (stepId === 'validating_rfid') {
        // Green only after OCI validate success
        setFlowIcon('rfid_validation', stepDomState('validating_rfid'));
        // Keep Read green while / after validation
        if (state === 'in_progress' || state === 'success' || state === 'error') {
            setFlowIcon('rfid_read', 'success');
        }
    }

    if (stepId === 'validating_anpr') {
        if (state === 'in_progress') {
            // Detect vs status-check wait: keep ANPR Read error, spin Update
            if (/check-status|status-check|Waiting for/i.test(msg)) {
                setFlowIcon('anpr_update', 'loading');
                AppState.anprUpdateActive = true;
            } else {
                setFlowIcon('anpr_read', 'loading');
            }
        } else if (state === 'warning' || state === 'error') {
            setFlowIcon('anpr_read', 'error');
            setFlowIcon('anpr_update', 'loading');
            AppState.anprUpdateActive = true;
        } else if (state === 'success') {
            if (/skipped|disabled/i.test(msg)) {
                // Operator skipped detect — status-check still runs → Update loading
                setFlowIcon('anpr_read', 'skipped');
                setFlowIcon('anpr_update', 'loading');
                AppState.anprUpdateActive = true;
            } else if (/updated manually/i.test(msg)) {
                // Only statusCode 201 + vehicleStatus 1 marks Update green
                if (iconState('anpr_read') === 'idle') {
                    setFlowIcon('anpr_read', 'error');
                }
                setFlowIcon('anpr_update', 'success');
            } else {
                // ANPR matched (no manual update) → skip Update
                setFlowIcon('anpr_read', 'success');
                if (iconState('anpr_update') === 'loading' || AppState.anprUpdateActive) {
                    setFlowIcon('anpr_update', 'skipped');
                } else if (iconState('anpr_update') === 'idle') {
                    setFlowIcon('anpr_update', 'skipped');
                }
            }
        } else if (/Err-0|Err-2|mismatch|not readable/i.test(msg)) {
            setFlowIcon('anpr_read', 'error');
            setFlowIcon('anpr_update', 'loading');
            AppState.anprUpdateActive = true;
        }
    }

    if (stepId === 'entry_granted') {
        const st = stepDomState('entry_granted');
        setFlowIcon('vehicle_exit', st);
        if (state === 'success' || state === 'in_progress') {
            const upd = iconState('anpr_update');
            // Do not force Update green here — only statusCode 201 does that.
            if (upd === 'loading') {
                setFlowIcon('anpr_update', 'skipped');
            } else if (state === 'success' && upd === 'idle') {
                setFlowIcon('anpr_update', 'skipped');
            }
            if (AppState.anprUpdateActive && iconState('anpr_read') === 'idle') {
                setFlowIcon('anpr_read', 'error');
            }
        }
    }

    if (stepId === 'wait_crossing') {
        setFlowIcon('truck_exited', state === 'error' ? 'error' : 'loading');
        if (state === 'in_progress' || state === 'success') {
            if (document.querySelector('[data-icon="vehicle_exit"]')?.getAttribute('data-state') === 'idle') {
                setFlowIcon('vehicle_exit', 'success');
            }
        }
    }

    if (stepId === 'exit_completed') {
        if (state === 'success' || state === 'in_progress') {
            setFlowIcon('truck_exited', 'success');
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
}

const SENSOR_LABELS = {
    s1: 'S1 Entry'
};

const IDLE_DANGER_SENSORS = ['s1'];

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
    Object.keys(SENSOR_LABELS).forEach((id) => {
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

function init() {
    console.log('Initializing Mines Checkpoint Dashboard...');
    AppState.steps.forEach(step => {
        step.element = document.getElementById(stepElementId(step.id));
        if (!step.element) {
            console.warn(`Step element not found: ${stepElementId(step.id)}`);
        }
    });
    applyDefaultStepContents();
    loadAppVersion();
    applySiteBranding();
    initThemeToggle();
    initUpdaterUI();
    initMQTT();
    initLoginModal();
    initResetModal();
    initFreePassModal();
    initApiAlertPopup();
    console.log('Dashboard initialized');
}

const THEME_STORAGE_KEY = 'gmdc_ui_theme';

function getPreferredTheme() {
    try {
        const stored = localStorage.getItem(THEME_STORAGE_KEY);
        if (stored === 'dark' || stored === 'light') return stored;
    } catch (e) { /* ignore */ }
    return 'light';
}

function applyTheme(theme) {
    const next = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    try {
        localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch (e) { /* ignore */ }
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        btn.title = next === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
        btn.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
    }
}

function initThemeToggle() {
    applyTheme(getPreferredTheme());
    const btn = document.getElementById('theme-toggle-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
    });
}

async function applySiteBranding() {
    try {
        const resp = await fetch('/api/status', { cache: 'no-store' });
        if (!resp.ok) return;
        const data = await resp.json();
        const name = data.display_name || data.service || 'Mines Checkpoint';
        const logo = data.logo_initials || 'MC';
        const logoEl = document.querySelector('.logo-icon');
        const titleEl = document.querySelector('.header-title h1');
        if (logoEl) logoEl.textContent = logo;
        if (titleEl) titleEl.textContent = 'Checkpoint';
        document.title = name + ' - Dashboard';
        if (typeof data.anpr_enabled === 'boolean') {
            setAnprToggleUi(data.anpr_enabled);
        }
    } catch (e) {
        console.warn('Site branding unavailable:', e);
    }
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

async function loadAppVersion() {
    try {
        const resp = await fetch('/version', { cache: 'no-store' });
        if (!resp.ok) {
            console.warn('Failed to fetch version: HTTP', resp.status);
            return;
        }
        const data = await resp.json();
        APP_VERSION = (data && data.version) ? data.version : 'unknown';
        const versionEl = document.getElementById('app-version');
        if (versionEl) {
            versionEl.textContent = 'v' + (APP_VERSION || 'unknown');
        }
    } catch (e) {
        console.warn('Error loading application version:', e);
    }
}

function showVersionInfo() {
    alert('Application Version: ' + (APP_VERSION || 'unknown'));
}

function openUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (!modal) return;
    const data = UPDATE_STATUS || {};
    const cur = document.getElementById('upd-current-version');
    const lat = document.getElementById('upd-latest-version');
    const notes = document.getElementById('upd-release-notes');
    const msg = document.getElementById('upd-message');
    renderUpdateProgress(0);
    if (cur) cur.textContent = data.current_version || APP_VERSION || 'unknown';
    if (lat) lat.textContent = data.latest_version || 'unknown';
    if (notes) notes.textContent = (data.release_notes || 'No release notes available.').toString().slice(0, 4000);
    if (msg) msg.textContent = (data && data.progress_message) ? data.progress_message : 'Ready';
    modal.classList.add('active');
}

function closeUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (modal) modal.classList.remove('active');
    if (UPDATE_PROGRESS_TIMER) {
        clearInterval(UPDATE_PROGRESS_TIMER);
        UPDATE_PROGRESS_TIMER = null;
    }
}

function renderUpdateProgress(percent) {
    const safe = Math.max(0, Math.min(100, Number(percent) || 0));
    const bar = document.getElementById('upd-progress-bar');
    const label = document.getElementById('upd-progress-label');
    if (bar) bar.style.width = `${safe}%`;
    if (label) label.textContent = `${safe}%`;
}

async function applyUpdateNow() {
    const btn = document.getElementById('apply-update-btn');
    const msg = document.getElementById('upd-message');
    if (btn) btn.disabled = true;
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
    const liveSensors = AppState.transactionData.sensors || { s1: false };
    AppState.transactionData = {
        rfid: '',
        truckNumber: '',
        sensors: liveSensors
    };

    const rfidBox = document.getElementById('rfid-display-box');
    const rfidValue = document.getElementById('rfid-value');
    const truckNumberValue = document.getElementById('truck-number-value');
    if (rfidBox) {
        rfidBox.classList.remove('has-rfid', 'has-truck');
    }
    if (rfidValue) rfidValue.textContent = '--';
    if (truckNumberValue) truckNumberValue.textContent = '--';
}

function stepIndex(stepId) {
    return AppState.steps.findIndex((s) => s.id === stepId);
}

function lastStepId() {
    const last = AppState.steps[AppState.steps.length - 1];
    return last ? last.id : null;
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
    if (!step || !step.element) {
        console.warn(`Step not found: ${stepId}`);
        return;
    }

    step.element.classList.remove('state-in-progress', 'state-success', 'state-error', 'state-warning');

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
        if (
            AppState.failedFromStep &&
            stepIndex(stepId) >= stepIndex(AppState.failedFromStep)
        ) {
            markFailureCascade(stepId);
            step.element.classList.add('state-error');
            step.completed = false;
            AppState.currentStep = null;
        } else {
            markPriorStepsComplete(stepId);
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
        // Checkpoint apps hold the error then reset to IDLE (no exit-grant).
        // Paint remaining steps red immediately for that display window.
        markFailureCascade(lastStepId() || stepId);
        step.element.classList.add('state-error');
        AppState.currentStep = null;
    } else if (state === 'warning') {
        step.element.classList.add('state-warning');
        AppState.currentStep = stepId;
    }

    const contentElement = step.element.querySelector('.step-content');
    if (!contentElement) return;
    if (data.content !== undefined) {
        contentElement.textContent = data.content;
    } else if (data.truckNumber !== undefined) {
        contentElement.textContent = `Truck No: ${data.truckNumber}`;
        AppState.transactionData.truckNumber = data.truckNumber;
    }
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

        if (
            failedSeen ||
            (AppState.failedFromStep &&
                stepIndex(step.id) >= stepIndex(AppState.failedFromStep))
        ) {
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
    if (modal) modal.classList.add('show');
}

function hideResetModal() {
    const modal = document.getElementById('reset-modal');
    if (modal) modal.classList.remove('show');
}

function applyIdleUi() {
    clearUiResetTimer();
    AppState.failedFromStep = null;
    applyDefaultStepContents();
    AppState.currentPosition = -1;
    resetFlowIcons();
    closeFlowDetailsModal();
    updateCheckSensorPopup();
}

let operatorLoggedIn = false;
let anprEnabled = true;

function setAnprToggleUi(enabled) {
    anprEnabled = !!enabled;
    const btn = document.getElementById('anpr-toggle-button');
    if (!btn) return;
    btn.textContent = anprEnabled ? 'ANPR: ON' : 'ANPR: OFF';
    btn.classList.toggle('is-on', anprEnabled);
    btn.classList.toggle('is-off', !anprEnabled);
    btn.title = anprEnabled
        ? 'ANPR enabled — click to disable (skip /api/detect)'
        : 'ANPR disabled — click to enable';
}

async function refreshAnprToggle() {
    try {
        const resp = await fetch('/api/anpr-enabled', { cache: 'no-store' });
        if (!resp.ok) return;
        const data = await resp.json();
        setAnprToggleUi(data.anpr_enabled !== false);
    } catch (e) {
        console.warn('Failed to load ANPR toggle state:', e);
    }
}

async function handleAnprToggle() {
    if (!operatorLoggedIn) return;
    const btn = document.getElementById('anpr-toggle-button');
    const next = !anprEnabled;
    if (btn) btn.disabled = true;
    try {
        const resp = await fetch('/api/anpr-enabled', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ anpr_enabled: next }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.message || ('HTTP ' + resp.status));
        }
        setAnprToggleUi(data.anpr_enabled !== false);
    } catch (e) {
        console.error('ANPR toggle failed:', e);
        alert('Failed to update ANPR setting. Please try again.');
        await refreshAnprToggle();
    } finally {
        if (btn) btn.disabled = false;
    }
}

function setOperatorUnlocked(unlocked) {
    operatorLoggedIn = !!unlocked;
    const controls = document.getElementById('flow-side-controls');
    const loginBtn = document.getElementById('login-button');
    if (controls) controls.hidden = !operatorLoggedIn;
    if (loginBtn) {
        loginBtn.textContent = operatorLoggedIn ? 'Logout' : 'Login';
        loginBtn.classList.toggle('is-logout', operatorLoggedIn);
        loginBtn.disabled = false;
    }
    if (operatorLoggedIn) {
        refreshAnprToggle();
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

    let mqttSent = false;
    if (mqttClient && mqttClient.isConnected && mqttClient.isConnected()) {
        try {
            mqttClient.publish('wb_frontend/reset_application', 'reset_application', 0);
            mqttSent = true;
        } catch (error) {
            console.warn('MQTT reset publish failed:', error);
        }
    }

    fetch('/api/reset', { method: 'POST' })
        .then((resp) => {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            applyIdleUi();
        })
        .catch((error) => {
            if (mqttSent) {
                applyIdleUi();
                return;
            }
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
    if (okBtn) okBtn.addEventListener('click', executeReset);
    if (cancelBtn) cancelBtn.addEventListener('click', hideResetModal);
    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) hideResetModal();
        });
    }
}

function showFreePassModal() {
    const modal = document.getElementById('free-pass-modal');
    if (modal) modal.classList.add('show');
}

function hideFreePassModal() {
    const modal = document.getElementById('free-pass-modal');
    if (modal) modal.classList.remove('show');
}

function handleFreePass() {
    if (!operatorLoggedIn) return;
    showFreePassModal();
}

function applyFreePassUi() {
    setStepState('wait_crossing', 'in_progress', {
        content: 'Free pass - traffic light green, boom open. Waiting for entry sensor.'
    });
    updateTrafficLightStatus({ color: 'GREEN' });
    updateBoomBarrierStatus({ position: 'Open' });
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
        } catch (error) {
            console.warn('MQTT free pass publish failed:', error);
        }
    }

    fetch('/api/free-pass', { method: 'POST' })
        .then((resp) => {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
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
    if (okBtn) okBtn.addEventListener('click', executeFreePass);
    if (cancelBtn) cancelBtn.addEventListener('click', hideFreePassModal);
    if (modal) {
        modal.addEventListener('click', function (event) {
            if (event.target === modal) hideFreePassModal();
        });
    }
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        hideResetModal();
        hideFreePassModal();
        closeUpdateModal();
    });
}

window.handleResetApplication = handleResetApplication;
window.handleFreePass = handleFreePass;
window.showVersionInfo = showVersionInfo;
window.openUpdateModal = openUpdateModal;
window.closeUpdateModal = closeUpdateModal;
window.applyUpdateNow = applyUpdateNow;

function updateTimestamp() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    const timeElement = document.getElementById('current-time');
    if (timeElement) timeElement.textContent = timeString;
}

function initMQTT() {
    if (typeof Paho === 'undefined') {
        console.error('Paho MQTT library not loaded.');
        setTimeout(() => {
            if (typeof Paho !== 'undefined') {
                initMQTT();
            } else {
                setTimeout(initMQTT, 5000);
            }
        }, 100);
        return;
    }

    if (currentConfigIndex >= MQTT_CONFIGS.length) {
        console.error('All MQTT connection configurations failed.');
        currentConfigIndex = 0;
        setTimeout(initMQTT, 10000);
        return;
    }

    const config = MQTT_CONFIGS[currentConfigIndex];
    try {
        let ClientClass;
        if (Paho.Client) {
            ClientClass = Paho.Client;
        } else if (Paho.MQTT && Paho.MQTT.Client) {
            ClientClass = Paho.MQTT.Client;
        } else {
            throw new Error('Paho Client class not found.');
        }

        mqttClient = new ClientClass(MQTT_BROKER_HOST, config.port, config.path, MQTT_CLIENT_ID);
        mqttClient.onConnectionLost = onConnectionLost;
        mqttClient.onMessageArrived = onMessageArrived;
        mqttClient.connect({
            onSuccess: onConnect,
            onFailure: onConnectFailure,
            timeout: 3,
            keepAliveInterval: 30,
            cleanSession: true,
            useSSL: false,
            mqttVersion: 4
        });
        console.log(`[${currentConfigIndex + 1}/${MQTT_CONFIGS.length}] Trying MQTT: ws://${MQTT_BROKER_HOST}:${config.port}${config.path}`);
    } catch (error) {
        console.error('Error initializing MQTT:', error);
        currentConfigIndex++;
        setTimeout(initMQTT, 2000);
    }
}

function onConnect() {
    const config = MQTT_CONFIGS[currentConfigIndex];
    console.log(`MQTT connected to ws://${MQTT_BROKER_HOST}:${config.port}${config.path}`);
    currentConfigIndex = 0;
    mqttClient.subscribe('wb_frontend/#', {
        onSuccess: () => {
            console.log('Subscribed to wb_frontend/#');
            requestCurrentStatus();
        },
        onFailure: (error) => {
            console.error('Failed to subscribe to wb_frontend/#:', error);
            setTimeout(requestCurrentStatus, 400);
        }
    });
    updateSystemStatus('Connected', true);
}

function requestCurrentStatus() {
    if (!mqttClient || !mqttClient.isConnected()) return;
    try {
        mqttClient.publish('wb_frontend/request_status', 'request', 0);
    } catch (error) {
        console.error('Error requesting status:', error);
    }
}

function onConnectFailure(error) {
    const config = MQTT_CONFIGS[currentConfigIndex];
    console.error(`MQTT connection failed to ws://${MQTT_BROKER_HOST}:${config.port}${config.path}:`, error.errorMessage || error);
    currentConfigIndex++;
    setTimeout(initMQTT, 2000);
}

function onConnectionLost(responseObject) {
    if (responseObject.errorCode !== 0) {
        console.error('MQTT connection lost:', responseObject.errorMessage);
        currentConfigIndex = 0;
        updateSystemStatus('Disconnected', false);
        setTimeout(initMQTT, 5000);
    }
}

function onMessageArrived(message) {
    const topic = message.destinationName;
    const payload = message.payloadString;
    try {
        if (topic === 'wb_frontend/position') {
            const position = parseInt(payload, 10);
            if (!isNaN(position)) handlePositionMessage(position);
        } else if (topic === 'wb_frontend/display') {
            AppState.displayMessage = payload;
            updateSystemStatus(payload, true);
        } else if (topic === 'wb_frontend/status') {
            handleStatusMessage(JSON.parse(payload));
        } else if (topic === 'wb_frontend/device_status') {
            handleDeviceStatus(JSON.parse(payload));
        } else if (topic === 'wb_frontend/rfid') {
            handleRfidData(JSON.parse(payload));
        }
    } catch (error) {
        console.error('Error processing MQTT message:', error);
    }
}

function handleStatusMessage(statusData) {
    const { step, status, message } = statusData;
    if (!step) return;
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
    if (status === 'idle' || status === 'default') {
        setStepState(step, 'default', { content: message });
        return;
    }
    if (status === 'success') {
        setStepState(step, 'success', { content: message });
    } else if (status === 'warning') {
        setStepState(step, 'warning', { content: message });
    } else {
        setStepState(step, 'in_progress', { content: message });
    }
}

function handlePositionMessage(position) {
    AppState.currentPosition = position;
    if (position === -1) applyIdleUi();
    else updateCheckSensorPopup();
}

function handleDeviceStatus(devices) {
    if (devices.rfid_reader) updateDeviceStatus('rfid-reader', devices.rfid_reader);
    if (devices.io_controller) updateDeviceStatus('io-controller', devices.io_controller);
    AppState.ioDependentsDisconnected = !!(
        (devices.io_controller && devices.io_controller.connected === false) ||
        (devices.sensors && devices.sensors.connected === false)
    );
    if (devices.sensors || AppState.ioDependentsDisconnected) {
        const s1 = AppState.ioDependentsDisconnected
            ? false
            : !!(devices.sensors && (devices.sensors.s1 || devices.sensors.sensor1));
        if (!AppState.transactionData.sensors) {
            AppState.transactionData.sensors = { s1: false };
        }
        AppState.transactionData.sensors.s1 = s1;
        updateSensorStatus('s1', s1);
        updateCheckSensorPopup();
    }
    if (AppState.ioDependentsDisconnected) {
        updateTrafficLightStatus({ connected: false });
        updateBoomBarrierStatus({ connected: false });
    } else {
        if (devices.traffic_light) updateTrafficLightStatus(devices.traffic_light);
        if (devices.boom_barrier) updateBoomBarrierStatus(devices.boom_barrier);
    }
}

function updateDeviceStatus(deviceId, status) {
    const deviceItems = document.querySelectorAll('.device-item');
    deviceItems.forEach(item => {
        const deviceName = item.querySelector('.device-name');
        if (!deviceName) return;
        let match = false;
        if (deviceId === 'rfid-reader' && deviceName.textContent.includes('RFID Reader')) match = true;
        else if (deviceId === 'io-controller' && deviceName.textContent.includes('I/O Controller')) match = true;
        if (!match) return;

        const statusElement = item.querySelector('.device-status');
        const detailsElement = item.querySelector('.device-details');
        if (statusElement) {
            const indicator = statusElement.querySelector('.status-indicator');
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
                if (statusTextNode) statusTextNode.textContent = 'Connected';
                else statusElement.appendChild(document.createTextNode('Connected'));
            } else {
                statusElement.className = 'device-status status-disconnected';
                if (indicator) indicator.style.backgroundColor = '#dc3545';
                if (statusTextNode) statusTextNode.textContent = 'Disconnected';
                else statusElement.appendChild(document.createTextNode('Disconnected'));
            }
        }
        if (detailsElement && status.port) {
            detailsElement.textContent = deviceId === 'io-controller' && status.port === 'N/A'
                ? 'Modbus TCP'
                : `Port: ${status.port}`;
        }
    });
}

function paintSensorBadge(sensorId, active) {
    document.querySelectorAll('.sensor-item').forEach(item => {
        const sensorName = item.querySelector('.sensor-name');
        if (sensorName && sensorName.textContent.trim().toUpperCase() === sensorId.toUpperCase()) {
            const stateElement = item.querySelector('.sensor-state');
            if (!stateElement) return;
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
    });
}

function updateSensorStatus(sensorId, active) {
    const key = String(sensorId || '').toLowerCase();
    if (!AppState.transactionData.sensors) {
        AppState.transactionData.sensors = { s1: false };
    }
    if (key in AppState.transactionData.sensors) {
        AppState.transactionData.sensors[key] = !!active;
    }
    paintSensorBadge(sensorId, active);
}

function _setNamedDeviceState(deviceLabel, active, activeText, inactiveText) {
    document.querySelectorAll('.device-item').forEach(item => {
        const deviceName = item.querySelector('.device-name');
        if (!deviceName || deviceName.textContent.trim() !== deviceLabel) return;
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
        if (AppState.ioDependentsDisconnected) {
            statusElement.className = 'device-status status-disconnected';
            if (indicator) indicator.style.backgroundColor = '#dc3545';
            if (statusTextNode) statusTextNode.textContent = 'Disconnected';
            else statusElement.appendChild(document.createTextNode('Disconnected'));
            return;
        }
        statusElement.className = active ? 'device-status status-active' : 'device-status status-inactive';
        if (indicator) indicator.style.backgroundColor = active ? '#28a745' : '#dc3545';
        const text = active ? activeText : inactiveText;
        if (statusTextNode) statusTextNode.textContent = text;
        else statusElement.appendChild(document.createTextNode(text));
    });
}

function updateTrafficLightStatus(status) {
    _setNamedDeviceState('Traffic Light', status.color === 'GREEN', 'Green', 'Red');
}

function updateBoomBarrierStatus(status) {
    _setNamedDeviceState('Boom Barrier', status.position === 'Open', 'Open', 'Closed');
}

function handleRfidData(rfidData) {
    const rfidBox = document.getElementById('rfid-display-box');
    const rfidValue = document.getElementById('rfid-value');
    const truckNumberValue = document.getElementById('truck-number-value');
    if (!rfidBox || !rfidValue || !truckNumberValue) return;
    if (rfidData.rfid) {
        rfidValue.textContent = rfidData.rfid;
        rfidBox.classList.add('has-rfid');
        AppState.transactionData.rfid = rfidData.rfid;
    }
    if (rfidData.truck_number) {
        truckNumberValue.textContent = rfidData.truck_number;
        rfidBox.classList.add('has-truck');
        AppState.transactionData.truckNumber = rfidData.truck_number;
    } else {
        truckNumberValue.textContent = '--';
        rfidBox.classList.remove('has-truck');
    }
}

function updateSystemStatus(message, connected) {
    const statusText = document.getElementById('status-text');
    const statusIndicator = document.querySelector('.status-indicator-dot');
    if (statusText) statusText.textContent = message;
    if (statusIndicator) {
        statusIndicator.style.backgroundColor = connected ? '#28a745' : '#dc3545';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    init();
    initFlowDetailsUi();
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
});
