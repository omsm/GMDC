// E-Rawanna IoT - Device Configuration JavaScript
// Device configuration page logic

/** Server URL / port - no prefilled defaults; operator must enter both. */
function clearServerFormFields() {
    const serverIpEl = document.getElementById('serverIp');
    const serverPortEl = document.getElementById('serverPort');
    if (serverIpEl) {
        serverIpEl.value = '';
        serverIpEl.readOnly = false;
    }
    if (serverPortEl) {
        serverPortEl.value = '';
        serverPortEl.readOnly = false;
    }
}

function applyServerConfigDefaults() {
    clearServerFormFields();
}

function getServerConnectionSettings() {
    const ipEl = document.getElementById('serverIp');
    const portEl = document.getElementById('serverPort');
    return {
        ip: (ipEl && ipEl.value.trim()) || '',
        port: (portEl && portEl.value.trim()) || '',
    };
}

// ============== Global State ==============
let config = {};
let completionStatus = {};
let discoveredDevices = {
    network: [],
    comPorts: [],
    candidates: {
        rfid: [],
        cameras: [],
        modbus: [],
        servers: [],
        all_ips: []
    }
};

// Track assigned IPs and COM ports to prevent duplicate assignments
let assignedDevices = {
    ips: {
        server: null,
        rfid: null,
        display: null,
        ioController: null
    },
    comPorts: {
        digitizer: null,
        ioController: null
    }
};

// Get app config from window (passed from template)
const APP_CONFIG = window.APP_CONFIG || {
    debug: true,
    requireDeviceInfo: false,
    enableCamera: true,
    appName: 'E-Rawanna',
    appVersion: '1.0.0',
    validCardsStartIndex: [],
    validCardCharLengths: [24, 32]
};

async function refreshFastagValidationConfig() {
    try {
        const resp = await fetch('/api/rfid/fastag-validation-rules');
        const data = await resp.json();
        if (data.status !== 200) return;
        if (!window.APP_CONFIG) window.APP_CONFIG = {};
        if (Array.isArray(data.valid_cards_start_index) && data.valid_cards_start_index.length) {
            window.APP_CONFIG.validCardsStartIndex = data.valid_cards_start_index;
        }
        if (Array.isArray(data.char_length) && data.char_length.length) {
            window.APP_CONFIG.validCardCharLengths = data.char_length;
        }
    } catch (err) {
        console.warn('[RFID] Could not refresh FASTag validation rules:', err);
    }
}

function getWizardNavSections() {
    // Prefer profile sections from server (checkpoint vs weighbridge)
    const profileSections = window.APP_CONFIG?.profile?.sections;
    if (Array.isArray(profileSections) && profileSections.length) {
        const s = profileSections.map((key) => {
            if (key === 'io_controller') return 'io-controller';
            if (key === 'voice') return 'audio';
            if (key === 'handheld_rfid') return 'handheld-rfid';
            return key;
        });
        // Camera comes after handheld RFID (not between RFID and handheld)
        if (APP_CONFIG.enableCamera && !s.includes('camera')) {
            const hhIdx = s.indexOf('handheld-rfid');
            const insertAt = hhIdx >= 0 ? hhIdx + 1 : (s.indexOf('rfid') >= 0 ? s.indexOf('rfid') + 1 : 2);
            s.splice(insertAt, 0, 'camera');
        }
        return s;
    }
    const s = ['server', 'rfid', 'handheld-rfid'];
    if (APP_CONFIG.enableCamera) s.push('camera');
    s.push('display', 'io-controller', 'digitizer', 'audio');
    return s;
}

function getWizardCompletionSections() {
    const profileSections = window.APP_CONFIG?.profile?.sections;
    if (Array.isArray(profileSections) && profileSections.length) {
        const s = [...profileSections];
        // Camera after handheld_rfid so RFID → Handheld navigation stays correct
        if (APP_CONFIG.enableCamera && !s.includes('camera')) {
            const hhIdx = s.indexOf('handheld_rfid');
            const insertAt = hhIdx >= 0 ? hhIdx + 1 : 2;
            s.splice(insertAt, 0, 'camera');
        }
        // Drop digitizer from completion if profile says no
        if (window.APP_CONFIG?.profile && !window.APP_CONFIG.profile.has_digitizer) {
            return s.filter((x) => x !== 'digitizer');
        }
        return s;
    }
    const s = ['server', 'rfid', 'handheld_rfid'];
    if (APP_CONFIG.enableCamera) s.push('camera');
    s.push('display', 'io_controller', 'digitizer', 'voice');
    return s;
}

function isCheckpointFamily() {
    return window.APP_CONFIG?.profile?.family === 'checkpoint';
}

function onRfidModeChange() {
    const mode = (document.getElementById('rfidModeSelect')?.value || 'API').toUpperCase();
    const apiCreds = document.getElementById('rfidApiCreds');
    const portGroup = document.getElementById('rfidPortGroup');
    if (apiCreds) apiCreds.style.display = mode === 'API' ? '' : 'none';
    if (portGroup) portGroup.style.display = mode === 'API' ? 'none' : '';
}

/** User-facing sensor role label (matches I/O pin UI). */
function getSensorRoleLabel(sensorNum) {
    const n = Number(sensorNum);
    if (n === 1) return 'Entry sensor';
    if (n === 2) return 'WB Sensor';
    if (n === 3) return 'Exit Sensor';
    return `Sensor ${sensorNum}`;
}

/** Keys used in iot_configuration.json io_controller.sensors */
const SENSOR_JSON_KEYS = { 1: 'entry_sensor', 2: 'wb_sensor', 3: 'exit_sensor' };
const SENSOR_LEGACY_JSON_KEYS = { 1: 'sensor1', 2: 'sensor2', 3: 'sensor3' };

function getSensorFromConfig(sensors, sensorNum) {
    if (!sensors || typeof sensors !== 'object') return {};
    const n = Number(sensorNum);
    return sensors[SENSOR_JSON_KEYS[n]] || sensors[SENSOR_LEGACY_JSON_KEYS[n]] || {};
}

/** Traffic light setup test tri-state for JSON: true = passed, null = skipped, false = not tested. */
function getTrafficLightValidatedForSave(location) {
    if (location === 'entry') return ioTestStatus.entryTLValidated;
    if (location === 'exit') return ioTestStatus.exitTLValidated;
    return false;
}

function isTrafficLightIoTestSatisfied(location) {
    const v = getTrafficLightValidatedForSave(location);
    return v === true || v === null;
}

function applyTrafficLightValidatedFromConfig(location, validated) {
    if (location !== 'entry' && location !== 'exit') return;
    const gateKey = location === 'entry' ? 'entryTL' : 'exitTL';
    const validatedKey = location === 'entry' ? 'entryTLValidated' : 'exitTLValidated';
    const statusIds = location === 'entry'
        ? ['entryTLStatus', 'entryTLRelayStatus', 'entryTLExtStatus']
        : ['exitTLStatus', 'exitTLRelayStatus', 'exitTLExtStatus'];
    if (validated === true) {
        ioTestStatus[gateKey] = true;
        ioTestStatus[validatedKey] = true;
        statusIds.forEach((id) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = 'Passed';
                el.className = 'device-status success';
            }
        });
    } else if (validated === null) {
        ioTestStatus[gateKey] = true;
        ioTestStatus[validatedKey] = null;
        statusIds.forEach((id) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = 'Skipped';
                el.className = 'device-status skipped';
            }
        });
    } else {
        ioTestStatus[gateKey] = false;
        ioTestStatus[validatedKey] = false;
        statusIds.forEach((id) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = '';
                el.className = 'device-status';
            }
        });
    }
}

/** Debug only: mark entry or exit traffic light hardware tests as satisfied without running them. */
function skipTrafficLightTest(location) {
    if (!APP_CONFIG.debug) {
        showToast('error', 'Skip', 'Traffic light skip is only available in debug mode.');
        return;
    }
    if (location !== 'entry' && location !== 'exit') return;
    applyTrafficLightValidatedFromConfig(location, null);
    const label = location === 'entry' ? 'Entry' : 'Exit';
    showToast('warning', 'Skipped', `${label} traffic light test skipped (Debug mode)`);
}

function isBoomBarrierEnabled(location, outputMode) {
    if (location !== 'entry' && location !== 'exit') return false;
    if (outputMode === 'direct') {
        return document.getElementById(`${location}BoomEnabled`)?.checked || false;
    }
    return document.getElementById(`${location}BoomRelayEnabled`)?.checked || false;
}

function boomBarrierTestsPassedForLocation(location, outputMode) {
    if (outputMode === 'direct') {
        return ioTestStatus[`${location}BBDirectOpen`] && ioTestStatus[`${location}BBDirectClose`];
    }
    return ioTestStatus[`${location}BBRelayOpen`] && ioTestStatus[`${location}BBRelayClose`];
}

/** Boom barrier setup test tri-state for JSON: true = passed, null = skipped/disabled, false = not tested. */
function getBoomBarrierValidatedForSave(location, outputMode) {
    if (!isBoomBarrierEnabled(location, outputMode)) return null;
    if (location === 'entry') return ioTestStatus.entryBBValidated;
    if (location === 'exit') return ioTestStatus.exitBBValidated;
    return false;
}

function isBoomBarrierIoTestSatisfied(location, outputMode) {
    if (!isBoomBarrierEnabled(location, outputMode)) return true;
    const v = location === 'entry' ? ioTestStatus.entryBBValidated : ioTestStatus.exitBBValidated;
    return v === true;
}

function updateBoomBarrierValidatedFromTests(location, outputMode) {
    if (!isBoomBarrierEnabled(location, outputMode)) {
        ioTestStatus[`${location}BBValidated`] = null;
        return;
    }
    if (boomBarrierTestsPassedForLocation(location, outputMode)) {
        ioTestStatus[`${location}BBValidated`] = true;
        const statusElId = outputMode === 'direct' ? `${location}BBStatus` : `${location}BBRelayStatus`;
        const statusEl = document.getElementById(statusElId);
        if (statusEl) {
            statusEl.textContent = 'Passed';
            statusEl.className = 'device-status success';
        }
    }
}

function applyBoomBarrierValidatedFromConfig(location, validated, outputMode) {
    if (location !== 'entry' && location !== 'exit') return;
    const outputModeResolved = outputMode || document.getElementById('outputMode')?.value || 'direct';
    const statusElId = outputModeResolved === 'direct' ? `${location}BBStatus` : `${location}BBRelayStatus`;
    const statusEl = document.getElementById(statusElId);
    const validatedKey = location === 'entry' ? 'entryBBValidated' : 'exitBBValidated';

    if (!isBoomBarrierEnabled(location, outputModeResolved)) {
        ioTestStatus[validatedKey] = null;
        setBoomBarrierStatusUI(location, 'Skipped', 'device-status skipped');
        return;
    }

    if (validated === true) {
        ioTestStatus[validatedKey] = true;
        if (outputModeResolved === 'direct') {
            ioTestStatus[`${location}BBDirect`] = true;
            ioTestStatus[`${location}BBDirectOpen`] = true;
            ioTestStatus[`${location}BBDirectClose`] = true;
        } else {
            ioTestStatus[`${location}BBRelay`] = true;
            ioTestStatus[`${location}BBRelayOpen`] = true;
            ioTestStatus[`${location}BBRelayClose`] = true;
        }
        if (statusEl) {
            statusEl.textContent = 'Passed';
            statusEl.className = 'device-status success';
        }
    } else {
        ioTestStatus[validatedKey] = false;
        if (outputModeResolved === 'direct') {
            ioTestStatus[`${location}BBDirect`] = false;
            ioTestStatus[`${location}BBDirectOpen`] = false;
            ioTestStatus[`${location}BBDirectClose`] = false;
        } else {
            ioTestStatus[`${location}BBRelay`] = false;
            ioTestStatus[`${location}BBRelayOpen`] = false;
            ioTestStatus[`${location}BBRelayClose`] = false;
        }
        if (statusEl) {
            statusEl.textContent = '';
            statusEl.className = 'device-status';
        }
    }
    ioTestStatus.boomBarrier =
        ioTestStatus.entryBBDirect || ioTestStatus.exitBBDirect ||
        ioTestStatus.entryBBRelay || ioTestStatus.exitBBRelay;
}

function setBoomBarrierStatusUI(location, text, className) {
    if (location !== 'entry' && location !== 'exit') return;
    [`${location}BBStatus`, `${location}BBRelayStatus`].forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = text;
            el.className = className;
        }
    });
}

function isBoomBarrierEnableToggleId(changedId) {
    return changedId === 'entryBoomEnabled' ||
        changedId === 'exitBoomEnabled' ||
        changedId === 'entryBoomRelayEnabled' ||
        changedId === 'exitBoomRelayEnabled';
}

/** Sync validated state and status when Enable checkbox is toggled (disabled = skipped). */
function syncBoomBarrierStateFromEnable(location) {
    if (location !== 'entry' && location !== 'exit') return;
    const outputMode = document.getElementById('outputMode')?.value || 'direct';
    const validatedKey = location === 'entry' ? 'entryBBValidated' : 'exitBBValidated';

    if (!isBoomBarrierEnabled(location, outputMode)) {
        ioTestStatus[validatedKey] = null;
        ioTestStatus[`${location}BBDirect`] = false;
        ioTestStatus[`${location}BBRelay`] = false;
        ioTestStatus[`${location}BBDirectOpen`] = false;
        ioTestStatus[`${location}BBDirectClose`] = false;
        ioTestStatus[`${location}BBRelayOpen`] = false;
        ioTestStatus[`${location}BBRelayClose`] = false;
        setBoomBarrierStatusUI(location, 'Skipped', 'device-status skipped');
    } else {
        ioTestStatus[validatedKey] = false;
        ioTestStatus[`${location}BBDirect`] = false;
        ioTestStatus[`${location}BBRelay`] = false;
        ioTestStatus[`${location}BBDirectOpen`] = false;
        ioTestStatus[`${location}BBDirectClose`] = false;
        ioTestStatus[`${location}BBRelayOpen`] = false;
        ioTestStatus[`${location}BBRelayClose`] = false;
        setBoomBarrierStatusUI(location, '', 'device-status');
    }
    ioTestStatus.boomBarrier =
        ioTestStatus.entryBBDirect || ioTestStatus.exitBBDirect ||
        ioTestStatus.entryBBRelay || ioTestStatus.exitBBRelay;
}

/** True when ENABLE_WB_SENSOR_TEST_SKIP is enabled in config.py (exposed as APP_CONFIG.allowSkipWbSensorTest). */
function isWbSensorSkipAllowed() {
    return !!(window.APP_CONFIG && APP_CONFIG.allowSkipWbSensorTest);
}

/** WB sensor validated: null (skipped) only when skip is allowed; otherwise treat null as not tested. */
function normalizeWbSensorValidatedFromConfig(validated) {
    if (!isWbSensorSkipAllowed() && validated === null) {
        return false;
    }
    return validated;
}

/** WB sensor (sensor2) setup test tri-state for JSON: true = passed, null = skipped, false = not tested. */
function getSensor2ValidatedForSave() {
    const v = ioTestStatus.sensor2Validated;
    if (!isWbSensorSkipAllowed() && v === null) {
        return false;
    }
    return v;
}

function isSensor2IoTestSatisfied() {
    if (!ioTestStatus.sensor2) return false;
    const v = ioTestStatus.sensor2Validated;
    if (isWbSensorSkipAllowed()) {
        return v === true || v === null;
    }
    return v === true;
}

function getSensorNumFromIoFieldId(fieldId) {
    if (!fieldId) return null;
    if (fieldId.startsWith('sensor1')) return 1;
    if (fieldId.startsWith('sensor2')) return 2;
    if (fieldId.startsWith('sensor3')) return 3;
    return null;
}

function resetSensorTestState(sensorNum) {
    const n = Number(sensorNum);
    if (n === 1) {
        ioTestStatus.sensor1 = false;
        ioTestStatus.sensor1Validated = false;
    } else if (n === 2) {
        ioTestStatus.sensor2 = false;
        ioTestStatus.sensor2Validated = false;
    } else if (n === 3) {
        ioTestStatus.sensor3 = false;
        ioTestStatus.sensor3Validated = false;
    } else {
        return;
    }
    const statusEl = document.getElementById(`sensor${n}Status`);
    if (statusEl) {
        statusEl.textContent = '';
        statusEl.className = 'device-status';
    }
}

function isEntryExitSensorIoTestSatisfied(sensorNum) {
    const n = Number(sensorNum);
    if (n === 1) {
        return ioTestStatus.sensor1 === true && ioTestStatus.sensor1Validated === true;
    }
    if (n === 3) {
        return ioTestStatus.sensor3 === true && ioTestStatus.sensor3Validated === true;
    }
    return false;
}

function getIoSaveValidationFailures(outputMode) {
    const failures = [];
    if (!isEntryExitSensorIoTestSatisfied(1)) failures.push('Entry sensor');
    if (!isCheckpointFamily()) {
        if (!isSensor2IoTestSatisfied()) failures.push('WB sensor');
        if (!isEntryExitSensorIoTestSatisfied(3)) failures.push('Exit sensor');
    }
    const tlTestsOk = (typeof allRequiredTrafficLightsSatisfied === 'function')
        ? allRequiredTrafficLightsSatisfied()
        : (isTrafficLightIoTestSatisfied('entry') && (isCheckpointFamily() || isTrafficLightIoTestSatisfied('exit')));
    if (!tlTestsOk) {
        if (typeof isBidirectionalLayout === 'function' && isBidirectionalLayout()) {
            failures.push('all traffic lights (ENTRY A and ENTRY B, entry and exit)');
        } else if (isCheckpointFamily()) {
            failures.push('entry traffic light');
        } else {
            failures.push('entry and exit traffic lights');
        }
    }
    if (isBoomBarrierValidationRequired(outputMode) && !hasRequiredBoomBarrierTestsPassed(outputMode)) {
        failures.push('enabled boom barrier');
    }
    return failures;
}

function applySensor2ValidatedFromConfig(validated) {
    applySensorValidatedFromConfig(2, normalizeWbSensorValidatedFromConfig(validated));
}

/** Entry/exit: boolean validated for JSON. WB: tri-state via applySensor2 path. */
function getSensorValidatedForSave(sensorNum) {
    const n = Number(sensorNum);
    if (n === 2) return getSensor2ValidatedForSave();
    if (n === 1) return ioTestStatus.sensor1Validated === true;
    if (n === 3) return ioTestStatus.sensor3Validated === true;
    return false;
}

function applySensorValidatedFromConfig(sensorNum, validated) {
    const n = Number(sensorNum);
    const statusEl = document.getElementById(`sensor${n}Status`);
    if (n === 2) {
        if (validated === true) {
            ioTestStatus.sensor2 = true;
            ioTestStatus.sensor2Validated = true;
            if (statusEl) {
                statusEl.textContent = 'Passed';
                statusEl.className = 'device-status success';
            }
        } else if (validated === null && isWbSensorSkipAllowed()) {
            ioTestStatus.sensor2 = true;
            ioTestStatus.sensor2Validated = null;
            if (statusEl) {
                statusEl.textContent = 'Skipped';
                statusEl.className = 'device-status skipped';
            }
        } else {
            ioTestStatus.sensor2 = false;
            ioTestStatus.sensor2Validated = false;
            if (statusEl) {
                statusEl.textContent = '';
                statusEl.className = 'device-status';
            }
        }
        return;
    }
    if (n !== 1 && n !== 3) return;
    const validatedKey = n === 1 ? 'sensor1Validated' : 'sensor3Validated';
    const gateKey = n === 1 ? 'sensor1' : 'sensor3';
    if (validated === true) {
        ioTestStatus[gateKey] = true;
        ioTestStatus[validatedKey] = true;
        if (statusEl) {
            statusEl.textContent = 'Passed';
            statusEl.className = 'device-status success';
        }
    } else {
        ioTestStatus[gateKey] = false;
        ioTestStatus[validatedKey] = false;
        if (statusEl) {
            statusEl.textContent = '';
            statusEl.className = 'device-status';
        }
    }
}

/** Config only: mark WB sensor (sensor 2) test as satisfied without running hardware. */
function skipWbSensorTest() {
    if (!window.APP_CONFIG || !APP_CONFIG.allowSkipWbSensorTest) {
        showToast('error', 'Skip', 'WB sensor skip is not enabled. Set ENABLE_WB_SENSOR_TEST_SKIP in config.py.');
        return;
    }
    ioTestStatus.sensor2 = true;
    ioTestStatus.sensor2Validated = null;
    const el = document.getElementById('sensor2Status');
    if (el) {
        el.textContent = 'Skipped';
        el.className = 'device-status skipped';
    }
    showToast('warning', 'Skipped', 'WB sensor test skipped (config-enabled bench/demo)');
}

// Keep console focused on boom-barrier debugging only.
(() => {
    if (window.__boomConsoleFilterInstalled) return;
    window.__boomConsoleFilterInstalled = true;
    const originalConsole = {
        log: console.log.bind(console),
        info: console.info.bind(console),
        warn: console.warn.bind(console),
        error: console.error.bind(console),
        debug: console.debug.bind(console)
    };
    const allow = (args) => /boom|barrier|entrybb|exitbb/i.test(args.map(a => String(a)).join(' '));
    ['log', 'info', 'warn', 'error', 'debug'].forEach((level) => {
        console[level] = (...args) => {
            if (allow(args)) originalConsole[level](...args);
        };
    });
})();

function boomLog(phase, details = {}) {
    console.log(`[BOOM][${phase}]`, details);
}

// ============== Validation Helpers ==============
function validateDeviceInfo(make, model, deviceName) {
    if (APP_CONFIG.requireDeviceInfo) {
        if (!make || !model) {
            showToast('error', 'Validation Error', `Please enter Make and Model for ${deviceName}`);
            return false;
        }
    }
    return true;
}

function initRequiredFieldIndicators() {
    // Add or remove required indicators for make/model fields based on mode
    const makeModelLabels = [
        // Server does not require make/model
        'rfidMake', 'rfidModel',
        'rfidAMake', 'rfidAModel',
        'rfidBMake', 'rfidBModel',
        'topCameraMake', 'topCameraModel',
        'frontCameraMake', 'frontCameraModel',
        'displayMake', 'displayModel',
        'ioMake', 'ioModel',
        'digitizerMake', 'digitizerModel',
        'audioMake', 'audioModel',
        'sensor1Make', 'sensor1Model',
        'entryTLMake', 'entryTLModel',
        'boomBarrierMake', 'boomBarrierModel'
    ];
    
    makeModelLabels.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            const label = field.parentElement?.querySelector('label');
            if (label) {
                // Remove existing required indicator
                const existing = label.querySelector('.required');
                if (existing) existing.remove();
                
                // Add required indicator if in production mode
                if (APP_CONFIG.requireDeviceInfo) {
                    const span = document.createElement('span');
                    span.className = 'required';
                    span.textContent = ' *';
                    label.appendChild(span);
                }
            }
        }
    });
    
    // Update debug mode indicator
    if (APP_CONFIG.debug) {
        console.log('[E-Rawanna IoT] Running in DEBUG mode - Make/Model fields are optional');
    } else {
        console.log('[E-Rawanna IoT] Running in PRODUCTION mode - Make/Model fields are required');
    }
}

// ============== Initialization ==============
document.addEventListener('DOMContentLoaded', function() {
    console.log('[Devices] Initializing page...');
    refreshFastagValidationConfig();
    
    try {
        initTheme();
        console.log('[Devices] Theme initialized');
    } catch (e) {
        console.error('[Devices] Error initializing theme:', e);
    }
    
    try {
        initNavigation();
        console.log('[Devices] Navigation initialized');
    } catch (e) {
        console.error('[Devices] Error initializing navigation:', e);
    }
    
    try {
        initRequiredFieldIndicators();
        console.log('[Devices] Required field indicators initialized');
    } catch (e) {
        console.error('[Devices] Error initializing required field indicators:', e);
    }

    try {
        setupIoPinInputOutputClasses();
        setupIoPinUniquenessHints();
    } catch (e) {
        console.error('[Devices] Error initializing I/O pin uniqueness hints:', e);
    }
    
    try {
        loadDiscoveredDevices();
        console.log('[Devices] Discovered devices loaded');
    } catch (e) {
        console.error('[Devices] Error loading discovered devices:', e);
    }
    
    try {
        applyServerConfigDefaults();
        loadConfig();
        if (typeof applyCameraUiForProfile === 'function') applyCameraUiForProfile();
        console.log('[Devices] Config loaded');
    } catch (e) {
        console.error('[Devices] Error loading config:', e);
    }
    
    try {
        loadCompletionStatus();
        console.log('[Devices] Completion status loaded');
    } catch (e) {
        console.error('[Devices] Error loading completion status:', e);
    }
    
    console.log('[Devices] Page initialization complete');
});

// ============== Load Discovered Devices from Session ==============
function loadDiscoveredDevices() {
    const storedDevices = sessionStorage.getItem('discoveredDevices');
    if (storedDevices) {
        discoveredDevices = JSON.parse(storedDevices);
        console.log('[Devices] Loaded discovered devices:', discoveredDevices);
    }
    populateDeviceDropdowns();
}

// ============== Navigation ==============
function goBack() {
    window.location.href = '/discover';
}

// ============== Placeholder for removed functions ==============
function loadSuggestedIpRange() {
    // Not needed on devices page
}

// ============== Assigned Device Management ==============
function initAssignedDevices() {
    // Initialize assigned devices from saved config
    if (config.server?.ip) {
        assignedDevices.ips.server = config.server.ip;
    }
    if (config.rfid?.ip) {
        assignedDevices.ips.rfid = config.rfid.ip;
    }
    if (config.display?.ip) {
        assignedDevices.ips.display = config.display.ip;
    }
    if (config.io_controller?.type === 'tcp' && config.io_controller?.ip) {
        assignedDevices.ips.ioController = config.io_controller.ip;
    }
    if (config.digitizer?.port) {
        assignedDevices.comPorts.digitizer = config.digitizer.port;
    }
    if (config.io_controller?.type === 'rtu' && config.io_controller?.serial_port) {
        assignedDevices.comPorts.ioController = config.io_controller.serial_port;
    }
    console.log('[Devices] Initialized assigned devices:', assignedDevices);
}

function updateAssignedDevice(deviceType, value, isIp = true) {
    if (isIp) {
        assignedDevices.ips[deviceType] = value || null;
    } else {
        assignedDevices.comPorts[deviceType] = value || null;
    }
    console.log(`[Devices] Updated assigned ${isIp ? 'IP' : 'COM port'} for ${deviceType}:`, value);
    refreshAllDropdowns();
}

function getAssignedIps(excludeDevice = null) {
    // Return list of assigned IPs, optionally excluding one device
    return Object.entries(assignedDevices.ips)
        .filter(([device, ip]) => ip && device !== excludeDevice)
        .map(([_, ip]) => ip);
}

function getAssignedComPorts(excludeDevice = null) {
    // Return list of assigned COM ports, optionally excluding one device
    return Object.entries(assignedDevices.comPorts)
        .filter(([device, port]) => port && device !== excludeDevice)
        .map(([_, port]) => port);
}

function refreshAllDropdowns() {
    // Re-populate all dropdowns with filtered devices
    populateDeviceDropdowns();
}


// ============== Device Dropdown Population ==============
function populateDeviceDropdowns() {
    // Ensure candidates object exists with all required arrays
    if (!discoveredDevices.candidates) {
        discoveredDevices.candidates = {};
    }
    const candidates = discoveredDevices.candidates;
    candidates.servers = candidates.servers || [];
    candidates.rfid = candidates.rfid || [];
    candidates.modbus = candidates.modbus || [];
    candidates.cameras = candidates.cameras || [];
    
    console.log('[Devices] Populating dropdowns with:', {
        network: discoveredDevices.network?.length || 0,
        servers: candidates.servers.length,
        rfid: candidates.rfid.length,
        modbus: candidates.modbus.length,
        cameras: candidates.cameras.length
    });
    
    // Get assigned IPs for filtering
    const serverAssignedIps = getAssignedIps('server');
    const rfidAssignedIps = getAssignedIps('rfid');
    const displayAssignedIps = getAssignedIps('display');
    const ioAssignedIps = getAssignedIps('ioController');
    
    // Server dropdown - show devices with HTTP ports (exclude assigned IPs)
    const availableServers = filterAssignedDevices(candidates.servers, serverAssignedIps);
    if (document.getElementById('serverIpSelect')) {
        populateDropdown('serverIpSelect', availableServers, 'Select discovered server...', 'server');
    }
    
    // RFID dropdown - prioritize devices with port 6000
    const rfidDevices = filterAssignedDevices(candidates.rfid, rfidAssignedIps);
    if (rfidDevices.length === 1 && !assignedDevices.ips.rfid) {
        // Auto-select if only one RFID device found and not already assigned
        populateDropdown('rfidIpSelect', rfidDevices, 'Select discovered RFID device...', 'rfid');
        const rfidSelect = document.getElementById('rfidIpSelect');
        if (rfidSelect && rfidDevices[0]?.ip) {
            rfidSelect.value = rfidDevices[0].ip;
            const autoDetect = document.getElementById('rfidAutoDetect');
            const autoIp = document.getElementById('rfidAutoIp');
            if (autoDetect) autoDetect.style.display = 'flex';
            if (autoIp) autoIp.textContent = rfidDevices[0].ip;
            onDeviceSelect('rfidIp', rfidDevices[0].ip);
        }
    } else if (rfidDevices.length > 1) {
        // Multiple RFID devices found
        populateDropdown('rfidIpSelect', rfidDevices, 'Multiple RFID devices found...', 'rfid');
    } else {
        // No RFID devices found, show all IPs (filtered)
        const availableNetwork = filterAssignedDevices(discoveredDevices.network || [], rfidAssignedIps);
        populateDropdown('rfidIpSelect', availableNetwork, 'No RFID found - Select any device...', 'rfid');
    }
    
    // Display dropdown - show all IPs (filtered)
    const availableDisplayDevices = filterAssignedDevices(discoveredDevices.network || [], displayAssignedIps);
    populateDropdown('displayIpSelect', availableDisplayDevices, 'Select discovered device...', 'display');
    
    // I/O Controller dropdown - prioritize Modbus devices (filtered)
    const modbusDevices = filterAssignedDevices(candidates.modbus, ioAssignedIps);
    if (modbusDevices.length > 0) {
        populateDropdown('ioIpSelect', modbusDevices, 'Select Modbus device...', 'ioController');
    } else {
        const availableIoDevices = filterAssignedDevices(discoveredDevices.network || [], ioAssignedIps);
        populateDropdown('ioIpSelect', availableIoDevices, 'No Modbus found - Select any device...', 'ioController');
    }
    
    // Digitizer dropdown - populate COM ports
    populateComPortDropdowns();
}

function filterAssignedDevices(devices, assignedIps) {
    // Filter out devices that are already assigned
    if (!devices || !Array.isArray(devices)) return [];
    return devices.filter(device => {
        const deviceIp = device.ip || device;
        return !assignedIps.includes(deviceIp);
    });
}

function populateDropdown(selectId, devices, placeholder, deviceType = null) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    // Save current selection to restore it
    const currentValue = select.value;
    
    select.innerHTML = `<option value="">${placeholder}</option>`;
    
    // If this device already has an assigned IP, add it first (even if assigned)
    const ownAssignedIp = deviceType ? assignedDevices.ips[deviceType] : null;
    if (ownAssignedIp) {
        // Try to find device info for the assigned IP
        const assignedDevice = findDeviceByIp(ownAssignedIp);
        const deviceTypeLabel = assignedDevice?.device_type || 'Assigned';
        
        const option = document.createElement('option');
        option.value = ownAssignedIp;
        option.textContent = `${ownAssignedIp} - ${deviceTypeLabel} (Currently assigned)`;
        select.appendChild(option);
    }
    
    devices.forEach(device => {
        const deviceIp = device.ip || device;
        // Skip if this is already added as own assigned IP
        if (deviceIp === ownAssignedIp) return;
        
        const option = document.createElement('option');
        if (device.ip) {
            option.value = device.ip;
            option.textContent = `${device.ip} - ${device.device_type || 'Unknown'}`;
        } else {
            option.value = device;
            option.textContent = device;
        }
        select.appendChild(option);
    });
    
    // Restore selection if it exists
    if (currentValue && Array.from(select.options).some(opt => opt.value === currentValue)) {
        select.value = currentValue;
    }
}

function findDeviceByIp(ip) {
    // Search in all discovered devices to find device info
    if (!discoveredDevices.network) return null;
    return discoveredDevices.network.find(d => d.ip === ip);
}

function populateComPortDropdowns() {
    // Get assigned COM ports for filtering
    const digitizerAssignedPorts = getAssignedComPorts('digitizer');
    const ioAssignedPorts = getAssignedComPorts('ioController');
    
    // Digitizer COM port
    const digitizerSelect = document.getElementById('digitizerPort');
    if (digitizerSelect) {
        const currentValue = digitizerSelect.value;
        digitizerSelect.innerHTML = '<option value="">Select port...</option>';
        
        // Add own assigned port first if exists
        const ownPort = assignedDevices.comPorts.digitizer;
        if (ownPort) {
            const option = document.createElement('option');
            option.value = ownPort;
            option.textContent = `${ownPort} (Currently assigned)`;
            digitizerSelect.appendChild(option);
        }
        
        discoveredDevices.comPorts.forEach(port => {
            const portName = port.port || port.device || port;
            // Skip if already added as own or assigned to another device
            if (portName === ownPort || digitizerAssignedPorts.includes(portName)) return;
            
            const portDesc = port.description || 'Serial Port';
            const option = document.createElement('option');
            option.value = portName;
            option.textContent = `${portName} - ${portDesc}`;
            digitizerSelect.appendChild(option);
        });
        
        // Restore selection
        if (currentValue && Array.from(digitizerSelect.options).some(opt => opt.value === currentValue)) {
            digitizerSelect.value = currentValue;
        }
    }
    
    // I/O Controller serial port
    const ioSerialSelect = document.getElementById('ioSerialPort');
    if (ioSerialSelect) {
        const currentValue = ioSerialSelect.value;
        ioSerialSelect.innerHTML = '<option value="">Select port...</option>';
        
        // Add own assigned port first if exists
        const ownPort = assignedDevices.comPorts.ioController;
        if (ownPort) {
            const option = document.createElement('option');
            option.value = ownPort;
            option.textContent = `${ownPort} (Currently assigned)`;
            ioSerialSelect.appendChild(option);
        }
        
        discoveredDevices.comPorts.forEach(port => {
            const portName = port.port || port.device || port;
            // Skip if already added as own or assigned to another device
            if (portName === ownPort || ioAssignedPorts.includes(portName)) return;
            
            const portDesc = port.description || 'Serial Port';
            const option = document.createElement('option');
            option.value = portName;
            option.textContent = `${portName} - ${portDesc}`;
            ioSerialSelect.appendChild(option);
        });
        
        // Restore selection
        if (currentValue && Array.from(ioSerialSelect.options).some(opt => opt.value === currentValue)) {
            ioSerialSelect.value = currentValue;
        }
    }
}

function onDeviceSelect(fieldId, value) {
    const input = document.getElementById(fieldId);
    if (input) {
        input.value = value;
    }
}

function toggleManualInput(fieldId) {
    const checkbox = document.getElementById(fieldId + 'Manual');
    const select = document.getElementById(fieldId + 'Select');
    const input = document.getElementById(fieldId);
    
    if (checkbox.checked) {
        if (select) select.classList.add('hidden');
        if (input) {
            input.classList.remove('hidden');
        }
    } else {
        if (select) select.classList.remove('hidden');
        if (input) input.classList.add('hidden');
    }
}

// ============== Same As First Toggle ==============
function toggleSameAsFirst(deviceType, identifier) {
    let checkboxId, infoContainerId, firstMakeId, firstModelId, targetMakeId, targetModelId;
    
    if (deviceType === 'sensor') {
        checkboxId = `sensor${identifier}SameAsFirst`;
        infoContainerId = `sensor${identifier}DeviceInfo`;
        firstMakeId = 'sensor1Make';
        firstModelId = 'sensor1Model';
        targetMakeId = `sensor${identifier}Make`;
        targetModelId = `sensor${identifier}Model`;
    } else if (deviceType === 'tl') {
        checkboxId = `${identifier}TLSameAsFirst`;
        infoContainerId = `${identifier}TLDeviceInfo`;
        firstMakeId = 'entryTLMake';
        firstModelId = 'entryTLModel';
        targetMakeId = `${identifier}TLMake`;
        targetModelId = `${identifier}TLModel`;
    }
    
    const checkbox = document.getElementById(checkboxId);
    const infoContainer = document.getElementById(infoContainerId);
    
    if (checkbox && checkbox.checked) {
        // Hide the device info fields and copy values from first
        if (infoContainer) infoContainer.classList.add('hidden');
        
        // Copy values from first device
        const firstMake = document.getElementById(firstMakeId)?.value || '';
        const firstModel = document.getElementById(firstModelId)?.value || '';
        
        const targetMake = document.getElementById(targetMakeId);
        const targetModel = document.getElementById(targetModelId);
        
        if (targetMake) targetMake.value = firstMake;
        if (targetModel) targetModel.value = firstModel;
    } else {
        // Show the device info fields
        if (infoContainer) infoContainer.classList.remove('hidden');
    }
}

// Update "same as first" values when first device changes
function syncSameAsFirstValues() {
    // Sync sensors
    for (let i = 2; i <= 3; i++) {
        const checkbox = document.getElementById(`sensor${i}SameAsFirst`);
        if (checkbox && checkbox.checked) {
            document.getElementById(`sensor${i}Make`).value = document.getElementById('sensor1Make').value;
            document.getElementById(`sensor${i}Model`).value = document.getElementById('sensor1Model').value;
        }
    }
    
    // Sync traffic lights
    const exitTLCheckbox = document.getElementById('exitTLSameAsFirst');
    if (exitTLCheckbox && exitTLCheckbox.checked) {
        document.getElementById('exitTLMake').value = document.getElementById('entryTLMake').value;
        document.getElementById('exitTLModel').value = document.getElementById('entryTLModel').value;
    }
}

// ============== Theme Management ==============
function getSystemTheme() {
    // Detect system theme preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        return 'dark';
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
        return 'light';
    }
    // Default to dark if system preference not available
    return 'dark';
}

function initTheme() {
    // Check if user has manually set a theme preference
    const manualTheme = localStorage.getItem('theme_manual');
    
    let theme;
    if (manualTheme) {
        // Use manually set theme
        theme = manualTheme;
    } else {
        // Auto-detect from system theme
        theme = getSystemTheme();
    }
    
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeIcon(theme);
    
    // Listen for system theme changes (only if no manual override)
    if (!manualTheme && window.matchMedia) {
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        mediaQuery.addEventListener('change', (e) => {
            // Only update if user hasn't manually set a preference
            if (!localStorage.getItem('theme_manual')) {
                const newTheme = e.matches ? 'dark' : 'light';
                document.documentElement.setAttribute('data-theme', newTheme);
                updateThemeIcon(newTheme);
            }
        });
    }
    
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    // Store manual preference
    localStorage.setItem('theme_manual', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
}

// ============== Navigation ==============
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    console.log('[Devices] Found', navItems.length, 'nav items');
    
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const section = this.getAttribute('data-section');
            console.log('[Devices] Nav clicked, switching to section:', section);
            showSection(section);
        });
    });
}

function showSection(sectionId) {
    console.log('[Devices] Showing section:', sectionId);
    
    // Update nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-section') === sectionId) {
            item.classList.add('active');
        }
    });
    
    // Update sections
    const sections = document.querySelectorAll('.config-section');
    console.log('[Devices] Found', sections.length, 'config sections');
    
    sections.forEach(section => {
        section.classList.remove('active');
    });
    
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.add('active');
        console.log('[Devices] Section activated:', sectionId);
    } else {
        console.error('[Devices] Section not found:', sectionId);
    }
}

function navigateToNext(currentSection) {
    const sections = getWizardNavSections();
    const currentIndex = sections.indexOf(currentSection);
    
    console.log('[Navigation] Current section:', currentSection, 'Index:', currentIndex);
    
    if (currentIndex < sections.length - 1) {
        const nextSection = sections[currentIndex + 1];
        console.log('[Navigation] Navigating to next section:', nextSection);
        showSection(nextSection);
    } else {
        console.log('[Navigation] Already at last section');
    }
}

// ============== Configuration Loading ==============
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        config = await response.json();
        populateFormFields();
        initAssignedDevices();
        refreshAllDropdowns();
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

function populateFormFields() {
    // Server URL / Port - always blank until operator enters values
    clearServerFormFields();
    
    // RFID
    if (config.rfid) {
        const rfidIpEl = document.getElementById('rfidIp');
        const rfidPortEl = document.getElementById('rfidPort');
        const rfidModeEl = document.getElementById('rfidModeSelect');
        const rfidMakeEl = document.getElementById('rfidMake');
        const rfidModelEl = document.getElementById('rfidModel');
        const rfidUserEl = document.getElementById('rfidUsername');
        const rfidPassEl = document.getElementById('rfidPassword');
        if (rfidIpEl) rfidIpEl.value = config.rfid.ip || '';
        if (rfidPortEl) rfidPortEl.value = config.rfid.port || '6000';
        if (rfidModeEl) rfidModeEl.value = config.rfid.mode || 'API';
        if (rfidMakeEl) rfidMakeEl.value = config.rfid.make || '';
        if (rfidModelEl) rfidModelEl.value = config.rfid.model || '';
        if (rfidUserEl) rfidUserEl.value = config.rfid.username || 'admin';
        if (rfidPassEl) rfidPassEl.value = config.rfid.password || '';
        if (typeof onRfidModeChange === 'function') onRfidModeChange();
    }

    // Handheld RFID
    if (config.handheld_rfid) {
        const hh = config.handheld_rfid;
        const en = document.getElementById('handheldEnabled');
        const mk = document.getElementById('handheldMake');
        const md = document.getElementById('handheldModel');
        const did = document.getElementById('handheldDeviceId');
        const hip = document.getElementById('handheldIp');
        const hport = document.getElementById('handheldPort');
        if (en) en.checked = hh.enabled !== false;
        if (mk) mk.value = hh.make || '';
        if (md) md.value = hh.model || '';
        if (did) did.value = hh.device_id || '';
        if (hip) hip.value = hh.ip || '';
        if (hport) hport.value = hh.port || '';
    }
    
    // Camera
    if (APP_CONFIG.enableCamera && config.camera) {
        const topCameraUrlEl = document.getElementById('topCameraUrl');
        const topCameraMakeEl = document.getElementById('topCameraMake');
        const topCameraModelEl = document.getElementById('topCameraModel');
        const frontCameraUrlEl = document.getElementById('frontCameraUrl');
        const frontCameraMakeEl = document.getElementById('frontCameraMake');
        const frontCameraModelEl = document.getElementById('frontCameraModel');
        if (topCameraUrlEl) topCameraUrlEl.value = config.camera.top?.rtsp_url || '';
        if (topCameraMakeEl) topCameraMakeEl.value = config.camera.top?.make || '';
        if (topCameraModelEl) topCameraModelEl.value = config.camera.top?.model || '';
        if (frontCameraUrlEl) frontCameraUrlEl.value = config.camera.front?.rtsp_url || '';
        if (frontCameraMakeEl) frontCameraMakeEl.value = config.camera.front?.make || '';
        if (frontCameraModelEl) frontCameraModelEl.value = config.camera.front?.model || '';
    }
    
    // Display
    if (config.display) {
        const displayTypeEl = document.getElementById('displayType');
        const displayIpEl = document.getElementById('displayIp');
        const displayPortEl = document.getElementById('displayPort');
        const displayMakeEl = document.getElementById('displayMake');
        const displayModelEl = document.getElementById('displayModel');
        
        if (displayTypeEl) displayTypeEl.value = config.display.type || 'api';
        if (displayIpEl) displayIpEl.value = config.display.ip || '';
        if (displayPortEl) {
            const dtype = (config.display.type || 'api').toLowerCase();
            displayPortEl.value = dtype === 'mqtt'
                ? (config.display.port || '1883')
                : (config.display.port || '8000');
        }
        if (displayMakeEl) displayMakeEl.value = config.display.make || '';
        if (displayModelEl) displayModelEl.value = config.display.model || '';
        toggleDisplayFields();
    }
    
    // Digitizer (API - digitizer-app on another PC)
    if (config.digitizer) {
        const digitizerHostEl = document.getElementById('digitizerHost');
        const digitizerApiPortEl = document.getElementById('digitizerApiPort');
        const digitizerPathEl = document.getElementById('digitizerPath');
        const digitizerTimeoutEl = document.getElementById('digitizerTimeout');
        const digitizerStableCountEl = document.getElementById('digitizerStableCount');
        const digitizerMakeEl = document.getElementById('digitizerMake');
        const digitizerModelEl = document.getElementById('digitizerModel');

        if (digitizerHostEl) digitizerHostEl.value = config.digitizer.host || '';
        if (digitizerApiPortEl) digitizerApiPortEl.value = config.digitizer.port || '8100';
        if (digitizerPathEl) digitizerPathEl.value = config.digitizer.path || '/read_stable_weight';
        if (digitizerTimeoutEl) digitizerTimeoutEl.value = config.digitizer.timeout || '30';
        if (digitizerStableCountEl) digitizerStableCountEl.value = config.digitizer.stable_count || '10';
        if (digitizerMakeEl) digitizerMakeEl.value = config.digitizer.make || '';
        if (digitizerModelEl) digitizerModelEl.value = config.digitizer.model || '';

        if (typeof updateDigitizerSavedConfig === 'function') {
            updateDigitizerSavedConfig(config.digitizer);
        }
    }
    
    // Audio (check both 'audio' and 'voice' keys for compatibility)
    const audioConfig = config.audio || config.voice || {};
    if (audioConfig) {
        const audioMakeEl = document.getElementById('audioMake');
        const audioModelEl = document.getElementById('audioModel');
        if (audioMakeEl) audioMakeEl.value = audioConfig.make || '';
        if (audioModelEl) audioModelEl.value = audioConfig.model || '';
    }
    
    // I/O Controller - new weighbridge_app compatible format
    if (config.io_controller) {
        const ioTypeEl = document.getElementById('ioType');
        const ioSlaveIdEl = document.getElementById('ioSlaveId');
        const outputModeEl = document.getElementById('outputMode');
        const ioMakeEl = document.getElementById('ioMake');
        const ioModelEl = document.getElementById('ioModel');
        
        if (ioTypeEl) ioTypeEl.value = config.io_controller.type || 'ethernet';
        if (ioSlaveIdEl) ioSlaveIdEl.value = config.io_controller.slave_id || '1';
        if (outputModeEl) outputModeEl.value = config.io_controller.output_mode || 'direct';
        if (ioMakeEl) ioMakeEl.value = config.io_controller.make || '';
        if (ioModelEl) ioModelEl.value = config.io_controller.model || '';
        
        // Connection settings
        if (config.io_controller.connection) {
            if (config.io_controller.type === 'ethernet') {
                const ioIpEl = document.getElementById('ioIp');
                const ioPortEl = document.getElementById('ioPort');
                if (ioIpEl) ioIpEl.value = config.io_controller.connection.ethernet?.ip || '';
                if (ioPortEl) ioPortEl.value = config.io_controller.connection.ethernet?.port || '502';
            } else {
                const ioSerialPortEl = document.getElementById('ioSerialPort');
                const ioBaudRateEl = document.getElementById('ioBaudRate');
                if (ioSerialPortEl) ioSerialPortEl.value = config.io_controller.connection.serial?.port || '';
                if (ioBaudRateEl) ioBaudRateEl.value = config.io_controller.connection.serial?.baud_rate || '9600';
            }
        }
        
        // Digital inputs config
        if (config.io_controller.digital_inputs) {
            const inputStartAddressEl = document.getElementById('inputStartAddress');
            const inputRegisterTypeEl = document.getElementById('inputRegisterType');
            if (inputStartAddressEl) inputStartAddressEl.value = config.io_controller.digital_inputs.start_address || '0';
            // Set register type dropdown based on function_code: "1" = "coil", "2" = "discrete"
            const functionCode = config.io_controller.digital_inputs.function_code;
            if (inputRegisterTypeEl) {
                if (functionCode === "1" || functionCode === 1) {
                    inputRegisterTypeEl.value = 'coil';
                } else if (functionCode === "2" || functionCode === 2) {
                    inputRegisterTypeEl.value = 'discrete';
                }
            }
        }
        // Digital outputs config
        if (config.io_controller.digital_outputs) {
            const outputStartAddressEl = document.getElementById('outputStartAddress');
            const outputRegisterTypeEl = document.getElementById('outputRegisterType');
            if (outputStartAddressEl) outputStartAddressEl.value = config.io_controller.digital_outputs.start_address || '0';
            // Set register type dropdown based on function_code: "5" = "coil", "6" = "holding"
            const functionCode = config.io_controller.digital_outputs.function_code;
            if (outputRegisterTypeEl) {
                if (functionCode === "5" || functionCode === 5) {
                    outputRegisterTypeEl.value = 'coil';
                } else if (functionCode === "6" || functionCode === 6) {
                    outputRegisterTypeEl.value = 'holding';
                }
            }
        }
        
        // Sensor configuration
        if (config.io_controller.sensors) {
            // Sensor 1
            const sensor1PinEl = document.getElementById('sensor1Pin');
            const sensor1DefaultSignalEl = document.getElementById('sensor1DefaultSignal');
            const sensor1MakeEl = document.getElementById('sensor1Make');
            const sensor1ModelEl = document.getElementById('sensor1Model');
            const entrySensor = getSensorFromConfig(config.io_controller.sensors, 1);
            if (sensor1PinEl) sensor1PinEl.value = entrySensor.pin || '0';
            if (sensor1DefaultSignalEl) sensor1DefaultSignalEl.value = entrySensor.default_signal || 'low';
            if (sensor1MakeEl) sensor1MakeEl.value = entrySensor.make || '';
            if (sensor1ModelEl) sensor1ModelEl.value = entrySensor.model || '';
            applySensorValidatedFromConfig(1, entrySensor.validated);
            // Sensor 2
            const sensor2PinEl = document.getElementById('sensor2Pin');
            const sensor2DefaultSignalEl = document.getElementById('sensor2DefaultSignal');
            const sensor2MakeEl = document.getElementById('sensor2Make');
            const sensor2ModelEl = document.getElementById('sensor2Model');
            const sensor2SameAsFirstEl = document.getElementById('sensor2SameAsFirst');
            const wbSensor = getSensorFromConfig(config.io_controller.sensors, 2);
            if (sensor2PinEl) sensor2PinEl.value = wbSensor.pin || '1';
            if (sensor2DefaultSignalEl) sensor2DefaultSignalEl.value = wbSensor.default_signal || 'low';
            if (sensor2MakeEl) sensor2MakeEl.value = wbSensor.make || '';
            if (sensor2ModelEl) sensor2ModelEl.value = wbSensor.model || '';
            if (wbSensor.same_as_first && sensor2SameAsFirstEl) {
                sensor2SameAsFirstEl.checked = true;
                toggleSameAsFirst('sensor', 2);
            }
            applySensor2ValidatedFromConfig(wbSensor.validated);
            // Sensor 3
            const sensor3PinEl = document.getElementById('sensor3Pin');
            const sensor3DefaultSignalEl = document.getElementById('sensor3DefaultSignal');
            const sensor3MakeEl = document.getElementById('sensor3Make');
            const sensor3ModelEl = document.getElementById('sensor3Model');
            const sensor3SameAsFirstEl = document.getElementById('sensor3SameAsFirst');
            const exitSensor = getSensorFromConfig(config.io_controller.sensors, 3);
            if (sensor3PinEl) sensor3PinEl.value = exitSensor.pin || '2';
            if (sensor3DefaultSignalEl) sensor3DefaultSignalEl.value = exitSensor.default_signal || 'low';
            if (sensor3MakeEl) sensor3MakeEl.value = exitSensor.make || '';
            if (sensor3ModelEl) sensor3ModelEl.value = exitSensor.model || '';
            if (exitSensor.same_as_first && sensor3SameAsFirstEl) {
                sensor3SameAsFirstEl.checked = true;
                toggleSameAsFirst('sensor', 3);
            }
            applySensorValidatedFromConfig(3, exitSensor.validated);
        }
        
        // Traffic Light configuration
        const tlMode = config.io_controller.traffic_lights?.mode || 'direct';
        // Get make/model from traffic_lights.entry and traffic_lights.exit if available
        const entryTLInfo = config.io_controller.traffic_lights?.entry || {};
        const exitTLInfo = config.io_controller.traffic_lights?.exit || {};
        const entryTLMakeEl = document.getElementById('entryTLMake');
        const entryTLModelEl = document.getElementById('entryTLModel');
        const exitTLMakeEl = document.getElementById('exitTLMake');
        const exitTLModelEl = document.getElementById('exitTLModel');
        if (entryTLMakeEl) entryTLMakeEl.value = entryTLInfo.make || '';
        if (entryTLModelEl) entryTLModelEl.value = entryTLInfo.model || '';
        if (exitTLMakeEl) exitTLMakeEl.value = exitTLInfo.make || '';
        if (exitTLModelEl) exitTLModelEl.value = exitTLInfo.model || '';
        
        if (tlMode === 'direct' && config.io_controller.traffic_lights?.direct) {
            const entryTL = config.io_controller.traffic_lights.direct.entry || {};
            const exitTL = config.io_controller.traffic_lights.direct.exit || {};
            const entryRedPinEl = document.getElementById('entryRedPin');
            const entryGreenPinEl = document.getElementById('entryGreenPin');
            const exitRedPinEl = document.getElementById('exitRedPin');
            const exitGreenPinEl = document.getElementById('exitGreenPin');
            if (entryRedPinEl) entryRedPinEl.value = entryTL.red_pin || '0';
            if (entryGreenPinEl) entryGreenPinEl.value = entryTL.green_pin || '1';
            if (exitRedPinEl) exitRedPinEl.value = exitTL.red_pin || '2';
            if (exitGreenPinEl) exitGreenPinEl.value = exitTL.green_pin || '3';
        } else if (config.io_controller.traffic_lights?.relay) {
            const entryTL = config.io_controller.traffic_lights.relay.entry || {};
            const exitTL = config.io_controller.traffic_lights.relay.exit || {};
            const entryTLRelayPinEl = document.getElementById('entryTLRelayPin');
            const exitTLRelayPinEl = document.getElementById('exitTLRelayPin');
            if (entryTLRelayPinEl) entryTLRelayPinEl.value = entryTL.pin || '0';
            if (exitTLRelayPinEl) exitTLRelayPinEl.value = exitTL.pin || '1';
        }
        applyTrafficLightValidatedFromConfig('entry', entryTLInfo.validated);
        applyTrafficLightValidatedFromConfig('exit', exitTLInfo.validated);
        
        // Boom Barrier configuration
        const bbMode = config.io_controller.boom_barriers?.mode || 'direct';
        // Get make/model from boom_barriers.entry and boom_barriers.exit if available
        const entryBBInfo = config.io_controller.boom_barriers?.entry || {};
        const exitBBInfo = config.io_controller.boom_barriers?.exit || {};
        const boomBarrierMakeEl = document.getElementById('boomBarrierMake');
        const boomBarrierModelEl = document.getElementById('boomBarrierModel');
        const entryBBMakeEl = document.getElementById('entryBBMake');
        const entryBBModelEl = document.getElementById('entryBBModel');
        const exitBBMakeEl = document.getElementById('exitBBMake');
        const exitBBModelEl = document.getElementById('exitBBModel');
        if (entryBBMakeEl) entryBBMakeEl.value = entryBBInfo.make || boomBarrierMakeEl?.value || '';
        if (entryBBModelEl) entryBBModelEl.value = entryBBInfo.model || boomBarrierModelEl?.value || '';
        if (exitBBMakeEl) exitBBMakeEl.value = exitBBInfo.make || boomBarrierMakeEl?.value || '';
        if (exitBBModelEl) exitBBModelEl.value = exitBBInfo.model || boomBarrierModelEl?.value || '';
        
        if (bbMode === 'direct' && config.io_controller.boom_barriers?.direct) {
            const entryBB = config.io_controller.boom_barriers.direct.entry || {};
            const exitBB = config.io_controller.boom_barriers.direct.exit || {};
            const entryBoomOpenPinEl = document.getElementById('entryBoomOpenPin');
            const entryBoomClosePinEl = document.getElementById('entryBoomClosePin');
            const entryBoomEnabledEl = document.getElementById('entryBoomEnabled');
            const exitBoomOpenPinEl = document.getElementById('exitBoomOpenPin');
            const exitBoomClosePinEl = document.getElementById('exitBoomClosePin');
            const exitBoomEnabledEl = document.getElementById('exitBoomEnabled');
            if (entryBoomOpenPinEl) entryBoomOpenPinEl.value = entryBB.open_pin || '4';
            if (entryBoomClosePinEl) entryBoomClosePinEl.value = entryBB.close_pin || '5';
            if (entryBoomEnabledEl) entryBoomEnabledEl.checked = entryBB.enabled || false;
            if (exitBoomOpenPinEl) exitBoomOpenPinEl.value = exitBB.open_pin || '5';
            if (exitBoomClosePinEl) exitBoomClosePinEl.value = exitBB.close_pin || '6';
            if (exitBoomEnabledEl) exitBoomEnabledEl.checked = exitBB.enabled || false;
        } else if (config.io_controller.boom_barriers?.relay) {
            const entryBB = config.io_controller.boom_barriers.relay.entry || {};
            const exitBB = config.io_controller.boom_barriers.relay.exit || {};
            const entryBoomRelayPinEl = document.getElementById('entryBoomRelayPin');
            const entryBoomRelayEnabledEl = document.getElementById('entryBoomRelayEnabled');
            const exitBoomRelayPinEl = document.getElementById('exitBoomRelayPin');
            const exitBoomRelayEnabledEl = document.getElementById('exitBoomRelayEnabled');
            if (entryBoomRelayPinEl) entryBoomRelayPinEl.value = entryBB.pin || '2';
            if (entryBoomRelayEnabledEl) entryBoomRelayEnabledEl.checked = entryBB.enabled || false;
            if (exitBoomRelayPinEl) exitBoomRelayPinEl.value = exitBB.pin || '3';
            if (exitBoomRelayEnabledEl) exitBoomRelayEnabledEl.checked = exitBB.enabled || false;
        }
        const outputModeForBB = config.io_controller.output_mode || bbMode || 'direct';
        applyBoomBarrierValidatedFromConfig('entry', entryBBInfo.validated, outputModeForBB);
        applyBoomBarrierValidatedFromConfig('exit', exitBBInfo.validated, outputModeForBB);
        
        toggleIOFields();
        toggleRelayFields();

        // Store a deep copy of the last-saved I/O config for change detection
        try {
            originalIoConfig = JSON.parse(JSON.stringify(config.io_controller));
            ioConfigDirty = false;
        } catch (e) {
            console.warn('[I/O Config] (devices) Failed to snapshot original config:', e);
            originalIoConfig = null;
            ioConfigDirty = false;
        }

        // Attach change listeners (idempotent – safe to call multiple times)
        initIoChangeDetection();
    }
}

// ============== Completion Status ==============
async function loadCompletionStatus() {
    try {
        const response = await fetch('/api/status');
        completionStatus = await response.json();
        updateValidationUI();
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

function updateValidationUI() {
    const sectionMap = {
        'server': 'server',
        'rfid': 'rfid',
        'handheld_rfid': 'handheld-rfid',
        ...(APP_CONFIG.enableCamera ? { 'camera': 'camera' } : {}),
        'display': 'display',
        'io_controller': 'io-controller',
        'digitizer': 'digitizer',
        'voice': 'audio',  // Backend uses 'voice', frontend uses 'audio'
        'audio': 'audio'   // Also check for 'audio' in case it's already mapped
    };
    
    Object.entries(sectionMap).forEach(([key, navSection]) => {
        const navItem = document.querySelector(`.nav-item[data-section="${navSection}"]`);
        if (navItem) {
            // Check both 'voice' and 'audio' keys for audio section
            let statusValue = completionStatus[key];
            if (statusValue === undefined && navSection === 'audio') {
                statusValue = completionStatus['voice'];
            }
            if (statusValue === undefined && navSection === 'handheld-rfid') {
                statusValue = completionStatus['handheld-rfid'];
            }
            
            // Remove all status classes first
            navItem.classList.remove('validated', 'skipped');
            
            // Check if skipped (null/None)
            if (statusValue === null || statusValue === 'null' || statusValue === 'None') {
                navItem.classList.add('skipped');
            } else if (statusValue === true || statusValue === 'true') {
                navItem.classList.add('validated');
            }
            // If false or undefined, no class is added (default state)
        }
    });
    
    // Update finish button - allow finish even if some sections are skipped
    const finishBtn = document.getElementById('finishBtn');
    // Check if all sections are either validated or skipped (not false/undefined)
    const sections = getWizardCompletionSections();
    const allComplete = sections.every(s => {
        const status = completionStatus[s];
        return status === true || status === null || status === 'true' || status === 'null' || status === 'None';
    });
    finishBtn.disabled = !allComplete;
}

function markSectionValidated(section) {
    const sectionMap = {
        'server': 'server',
        'rfid': 'rfid',
        'handheld-rfid': 'handheld_rfid',
        'handheld_rfid': 'handheld_rfid',
        'camera': 'camera',
        'display': 'display',
        // Always map to backend key 'io_controller'
        'io_controller': 'io_controller',
        'io-controller': 'io_controller',
        'digitizer': 'digitizer',
        'audio': 'voice',  // Frontend uses 'audio', backend uses 'voice'
        'voice': 'voice'
    };
    
    // Map section name for backend compatibility
    const backendSection = sectionMap[section] || section;
    completionStatus[backendSection] = true;
    // Also set frontend key for consistency
    if (backendSection === 'voice') {
        completionStatus['audio'] = true;
    }
    if (backendSection === 'handheld_rfid') {
        completionStatus['handheld-rfid'] = true;
    }
    
    // Check if all complete - use backend section names (allow skipped sections)
    const sections = getWizardCompletionSections();
    completionStatus.all_complete = sections.every(s => {
        const status = completionStatus[s];
        return status === true || status === null || status === 'true' || status === 'null' || status === 'None';
    });
    
    updateValidationUI();
}

function markSectionSkipped(section) {
    const sectionMap = {
        'server': 'server',
        'rfid': 'rfid',
        'handheld-rfid': 'handheld_rfid',
        'handheld_rfid': 'handheld_rfid',
        'camera': 'camera',
        'display': 'display',
        // Always map to backend key 'io_controller'
        'io_controller': 'io_controller',
        'io-controller': 'io_controller',
        'digitizer': 'digitizer',
        'audio': 'voice',  // Frontend uses 'audio', backend uses 'voice'
        'voice': 'voice'
    };
    
    // Map section name for backend compatibility
    const backendSection = sectionMap[section] || section;
    completionStatus[backendSection] = null;  // Set to null for skipped
    // Also set frontend key for consistency
    if (backendSection === 'voice') {
        completionStatus['audio'] = null;
    }
    if (backendSection === 'handheld_rfid') {
        completionStatus['handheld-rfid'] = null;
    }
    
    // Check if all complete - use backend section names (allow skipped sections)
    const sections = getWizardCompletionSections();
    completionStatus.all_complete = sections.every(s => {
        const status = completionStatus[s];
        return status === true || status === null || status === 'true' || status === 'null' || status === 'None';
    });
    
    updateValidationUI();
}

// ============== Server Configuration ==============
async function checkAndSaveServer() {
    const { ip, port } = getServerConnectionSettings();

    if (!ip) {
        showToast('error', 'Validation Error', 'Please enter Server URL');
        return;
    }
    if (!port) {
        showToast('error', 'Validation Error', 'Please enter Server Port');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/server/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, port })
        });
        
        const result = await response.json();
        showLoading(false);
        
        if (result.status === 200) {
            // Save configuration
            await fetch('/api/config/server', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ip, port, validated: true })
            });
            
            showToast('success', 'Success', result.message);
            markSectionValidated('server');
            updateAssignedDevice('server', ip, true);
            navigateToNext('server');
        } else {
            showToast('error', 'Connection Failed', result.message || 'Server is not reachable');
        }
    } catch (error) {
        showLoading(false);
        console.error('[Server Check] Error:', error);
        showToast('error', 'Connection Error', 'Unable to reach the configuration service');
    }
}

// ============== RFID Configuration ==============
async function checkAndSaveRFID() {
    const isManual = document.getElementById('rfidIpManual')?.checked;
    const ip = isManual 
        ? document.getElementById('rfidIp').value.trim()
        : (document.getElementById('rfidIpSelect')?.value || document.getElementById('rfidIp').value.trim());
    const port = document.getElementById('rfidPort')?.value.trim() || '';
    const mode = (document.getElementById('rfidModeSelect')?.value || 'API').toUpperCase();
    const rfidMake = document.getElementById('rfidMake')?.value.trim() || '';
    const rfidModel = document.getElementById('rfidModel')?.value.trim() || '';
    const username = document.getElementById('rfidUsername')?.value.trim() || 'admin';
    const password = document.getElementById('rfidPassword')?.value || '';
    
    if (!ip) {
        showToast('error', 'Validation Error', 'Please enter RFID reader IP');
        return;
    }
    if (mode !== 'API' && !port) {
        showToast('error', 'Validation Error', 'Please enter both IP and Port');
        return;
    }
    
    // Validate device info in production mode
    if (!validateDeviceInfo(rfidMake, rfidModel, 'RFID Reader')) {
        return;
    }
    
    showLoading(true);
    const statusEl = document.getElementById('rfidStatus');
    if (statusEl) statusEl.style.display = 'none';
    
    try {
        const response = await fetch('/api/rfid/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, port: port || '443', mode, username, password })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            if (result.mode === 'API' || result.mode === 'CLIENT' || result.mode === 'SERVER') {
                if (result.testing === true || result.test_complete === false) {
                    showLoading(false);
                    showRfidCardReadModal(result.mode, ip, port, result.push_url);
                    await pollRfidTestStatus(ip, port, rfidMake, rfidModel, result.mode);
                } else {
                    handleRfidResult(result, ip, port, rfidMake, rfidModel);
                }
            }
        } else {
            showToast('error', 'Connection Failed', result.message);
            showLoading(false);
        }
    } catch (error) {
        console.error('[RFID Check] Error:', error);
        showToast('error', 'Connection Error', 'Unable to check RFID connection');
    } finally {
        showLoading(false);
    }
}

// Module Help Modal Functions
const MODULE_HELP_CONTENT = {
    server: {
        title: 'Server Configuration Help',
        html: `<h4>What this is</h4><ul><li>Enter the <b>Server URL</b> and <b>Server Port</b> for this checkpoint.</li></ul><h4>How to verify</h4><ul><li>Click <b>Check &amp; Save</b> to confirm the server is reachable, then continue.</li></ul>`
    },
    rfid: {
        title: 'RFID Configuration Help',
        html: `<h4>What to Enter</h4><ul><li>RFID make and model number from the reader sticker.</li><li>RFID IP address and port number.</li><li>RFID connection mode.</li><li><b>RFID is Server, Application is Client:</b> the application continuously requests data from the reader.</li><li><b>RFID is Client, Application is Server:</b> the reader sends data to the application when a card is scanned (common in devices like Identium).</li></ul><h4>Validation Flow</h4><ul><li>Run <b>Check & Save</b>, then scan a card during the 30-second test window.</li><li>In the calibration popup, paste the RFID value shown in your RFID Reader application.</li><li>Click <b>Save Match</b>. The application verifies that the entered RFID exists in the raw data. This is a critical step; otherwise, truck validation can fail.</li></ul><h4>Tips</h4><ul><li>Make and model of the RFID reader are mandatory.</li><li>If RFID communication fails, first confirm that RFID data is visible in the RFID Reader application. Also enable options like heartbeat (or equivalent keep-alive) to ensure stable communication.</li></ul>`
    },
    camera: {
        title: 'Camera Configuration Help',
        html: `<h4>RTSP setup</h4><ul><li>Use full RTSP URL with credentials (rtsp://user:pass@ip:554/...).</li><li>Click <b>Check &amp; Save</b> for every displayed camera; its live preview must appear.</li><li>If a stream fails, fix the URL and try again.</li></ul><h4>Required cameras</h4><ul><li><b>Mines Entry, Exit, Tracking 1 and Tracking 2:</b> Front Camera only. Automation does not capture it because ANPR supplies the front image.</li><li><b>Tare, Vadaghat and Gross weighbridges:</b> configure both Top and Front cameras. Automation captures only Top; ANPR supplies Front.</li></ul>`
    },
    display: {
        title: 'Display Configuration Help',
        html: `<h4>Select Display Type</h4><p>Choose either <b>MQTT</b> or <b>API</b>.</p><h4>Method: MQTT</h4><ul><li>If MQTT is selected, click <b>Check & Save</b> and confirm the success toast.</li><li>On the display side, configure MQTT as:<br><b>Broker:</b> localhost:1883<br><b>Subscribe:</b> iot_display/application_to_display<br><b>Publish:</b> iot_display/display_to_application</li><li>When <b>Check & Save</b> is clicked, the application publishes to <code>iot_display/application_to_display</code>. The display must show this data and publish it back on <code>iot_display/display_to_application</code>.</li></ul><h4>Method: API</h4><ul><li><b>Option 1 (Display-hosted API):</b><br>If the API is hosted in the display device, click <b>Check & Save</b>. The application expects HTTP status <b>200</b>. If status 200 is not received, vendor should verify the API in Postman.</li><li><b>Option 2 (API hosted via IIS on Server/PC):</b><br>Set display port to <b>81</b>. Enter IP and Port in separate fields (example: IP <code>192.168.1.100</code>, Port <code>81</code>). Then click <b>Check & Save</b>. The application expects status <b>200</b>; otherwise vendor should verify the API in Postman.</li></ul>`
    },
    'io-controller': {
        title: 'I/O Controller Configuration Help',
        html: `<h4>Connection Basics</h4><ul><li>Select <b>TCP</b> or <b>Serial</b>, and set the correct slave ID.</li><li>Set input and output start addresses exactly as per the I/O card datasheet. This is mandatory for proper I/O controller configuration.</li></ul><h4>Output Mode</h4><ul><li><b>Direct:</b> Each traffic light and boom barrier action uses separate pins (for example: red_pin, green_pin, open_pin, close_pin) connected directly to the I/O controller.</li><li><b>Relay:</b> One pin per device controls a relay with NO/NC contacts.<br>Relay ON (coil=HIGH) => NO contact => GREEN<br>Relay OFF (coil=LOW) => NC contact => RED</li></ul><h4>Sensors (Cut/Uncut Logic)</h4><ul><li>Inputs are labelled <b>Entry sensor</b>, <b>WB Sensor</b>, and <b>Exit Sensor</b>.</li><li><b>Default signal</b> means sensor not-triggered (uncut) state.</li><li>During <b>Test Sensor</b>, the app first checks default state, then asks you to trigger the sensor (cut), and verifies the state change.</li><li>If the sensor is not triggered correctly, the app shows an error and configuration cannot be saved.</li><li>Enter the correct pin number and signal dropdown value based on sensor and I/O controller datasheets.</li></ul><h4>Output Testing</h4><ul><li>Test entry/exit traffic lights and boom barriers.</li><li>Confirm physical hardware state change when prompted.</li></ul><h4>Before Save</h4><ul><li>All I/O tests must pass before configuration can be saved.</li></ul>`
    },
    digitizer: {
        title: 'Digitizer Configuration Help',
        html: `<h4>Serial parameters</h4><ul><li>Set COM port, baud, parity, data bits, stop bits as per indicator manual.</li><li>Timeout and stable count affect reading reliability.</li></ul><h4>Validation</h4><ul><li>Place load on platform and run <b>Check & Save</b>.</li><li>Ensure live data appears, then choose conversion method if prompted.</li></ul>`
    },
    audio: {
        title: 'Audio Configuration Help',
        html: `<h4>Setup</h4><ul><li>Use local speaker/output device connected to application PC.</li></ul><h4>Validation</h4><ul><li>Play test audio and confirm audible output before marking validated.</li></ul>`
    }
};

function openModuleHelp(moduleKey) {
    const modal = document.getElementById('moduleHelpModal');
    const titleEl = document.getElementById('moduleHelpTitle');
    const contentEl = document.getElementById('moduleHelpContent');
    const def = MODULE_HELP_CONTENT[moduleKey];
    if (!modal || !titleEl || !contentEl || !def) return;
    titleEl.innerHTML = `<i class="bi bi-question-circle"></i> ${def.title}`;
    contentEl.innerHTML = def.html;
    modal.classList.add('active');
}

function closeModuleHelp() {
    const modal = document.getElementById('moduleHelpModal');
    if (modal) modal.classList.remove('active');
}

function simplifyErrorMessage(message) {
    const text = String(message || '').trim();
    if (!text) return 'Operation failed. Please verify settings and try again.';
    if (text.length > 180 || /traceback|exception|stack|errno|timed? out|connection refused|failed to|error:/i.test(text)) {
        return 'Operation failed. Please verify device settings and network connectivity, then try again.';
    }
    return text;
}

function showDebugErrorModal(title, message) {
    const modal = document.getElementById('debugErrorModal');
    const titleEl = document.getElementById('debugErrorTitle');
    const msgEl = document.getElementById('debugErrorMessage');
    if (!modal || !titleEl || !msgEl) return;
    titleEl.textContent = title || 'Error';
    msgEl.textContent = String(message || 'No additional debug details available.');
    modal.classList.add('active');
}

function closeDebugErrorModal() {
    const modal = document.getElementById('debugErrorModal');
    if (modal) modal.classList.remove('active');
}

// RFID Modal Functions
let pendingRfidCalibrationContext = null;
let _rfidRetryContext = null;
let _rfidPendingResult = null;

function showRfidCardReadModal(mode, ip, port, pushUrl) {
    console.log('[RFID Modal] Showing modal for mode:', mode);
    const modal = document.getElementById('rfidCardReadModal');
    if (!modal) {
        console.error('[RFID Modal] Modal element not found!');
        return;
    }

    const modeText = document.getElementById('rfidModalMode');
    const countdownEl = document.getElementById('rfidModalCountdown');
    const statusEl = document.getElementById('rfidModalStatus');
    const saveBtn = document.getElementById('rfidModalSaveBtn');
    const cancelBtn = document.getElementById('rfidModalCancelBtn');
    const retryBtn = document.getElementById('rfidModalRetryBtn');
    const dataBox = document.getElementById('rfidModalDataBox');
    const dataValue = document.getElementById('rfidModalDataValue');

    if (!modeText || !countdownEl || !statusEl) {
        console.error('[RFID Modal] Modal elements not found!');
        return;
    }

    _rfidPendingResult = null;
    window._rfidToastShownForTag = null;
    _rfidRetryContext = {
        mode,
        ip,
        port,
        rfidMake: null,
        rfidModel: null,
        directionKey: (typeof currentRfidDirectionKey !== 'undefined') ? currentRfidDirectionKey : null,
    };

    modeText.textContent = 'Please scan an RFID tag.';
    countdownEl.textContent = '30';
    if (dataBox) dataBox.style.display = 'none';
    if (dataValue) dataValue.textContent = '';

    statusEl.innerHTML = '<i class="bi bi-info-circle"></i> <span>Waiting for RFID data...</span>';
    statusEl.style.color = '';
    statusEl.style.display = '';
    if (countdownEl.parentElement) {
        countdownEl.parentElement.style.display = 'block';
    }
    // Waiting: Cancel only (no Save/Retry until test finishes)
    if (saveBtn) saveBtn.style.display = 'none';
    if (retryBtn) retryBtn.style.display = 'none';
    if (cancelBtn) cancelBtn.style.display = 'inline-block';

    modal.classList.add('active');
    console.log('[RFID Modal] Modal shown');
}

function closeRfidCardReadModal() {
    const modal = document.getElementById('rfidCardReadModal');
    if (modal) {
        modal.classList.remove('active');
    }
    _rfidRetryContext = null;
    _rfidPendingResult = null;
}

async function cancelRfidCardRead() {
    try {
        await fetch('/api/rfid/stop', { method: 'POST' }).catch(() => null);
    } catch (e) { /* ignore */ }
    if (window.rfidTestTimeoutDevices) {
        clearTimeout(window.rfidTestTimeoutDevices);
        window.rfidTestTimeoutDevices = null;
    }
    closeRfidCardReadModal();
    showLoading(false);
}

async function saveRfidCardRead() {
    const pending = _rfidPendingResult;
    if (!pending || !pending.result || !pending.result.card_read) {
        showToast('warning', 'RFID', 'No RFID data to save. Scan a tag or retry.');
        return;
    }
    const { result, ip, port, rfidMake, rfidModel } = pending;
    closeRfidCardReadModal();
    handleRfidResult(result, ip, port, rfidMake, rfidModel);
}

async function retryRfidCardRead() {
    const ctx = _rfidRetryContext;
    _rfidPendingResult = null;
    closeRfidCardReadModal();
    try {
        await fetch('/api/rfid/stop', { method: 'POST' }).catch(() => null);
    } catch (e) { /* ignore */ }

    if (ctx && ctx.directionKey && typeof checkAndSaveRFID === 'function') {
        await checkAndSaveRFID(ctx.directionKey);
    } else if (typeof checkAndSaveRFID === 'function') {
        await checkAndSaveRFID();
    }
}

function showRfidModalReceivedData(tag) {
    const dataBox = document.getElementById('rfidModalDataBox');
    const dataValue = document.getElementById('rfidModalDataValue');
    if (dataValue) dataValue.textContent = tag || '';
    if (dataBox) dataBox.style.display = tag ? 'block' : 'none';
}

async function openRfidCalibrationModal(rawHexData, context) {
    await refreshFastagValidationConfig();
    const modal = document.getElementById('rfidCalibrationModal');
    const rawDataEl = document.getElementById('rfidCalibrationRawData');
    const inputEl = document.getElementById('rfidCalibrationInput');
    const resultEl = document.getElementById('rfidCalibrationResult');
    if (!modal || !rawDataEl || !inputEl || !resultEl) {
        showToast('error', 'RFID Calibration', 'Calibration modal is missing in the page.');
        return;
    }

    pendingRfidCalibrationContext = context;
    rawDataEl.value = (rawHexData || '').toUpperCase();
    inputEl.value = '';
    resultEl.style.display = 'none';
    resultEl.className = 'alert';
    resultEl.textContent = '';
    modal.classList.add('active');
    inputEl.focus();
}

function closeRfidCalibrationModal() {
    const modal = document.getElementById('rfidCalibrationModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

function showRfidCalibrationResult(message, success) {
    const resultEl = document.getElementById('rfidCalibrationResult');
    if (!resultEl) return;
    resultEl.style.display = 'block';
    resultEl.className = success ? 'alert alert-success' : 'alert alert-danger';
    resultEl.textContent = message;
}

function validateFastagRfidInput(userTag) {
    const tag = (userTag || '').trim().toUpperCase();
    if (!tag) {
        return 'Please enter RFID value from vendor application.';
    }
    if (!/^[0-9A-F]+$/.test(tag)) {
        return 'RFID must contain only hexadecimal characters (0-9, A-F).';
    }
    const rawLengths = (window.APP_CONFIG && window.APP_CONFIG.validCardCharLengths) || [24, 32];
    const validLengths = rawLengths
        .map((n) => parseInt(n, 10))
        .filter((n) => Number.isInteger(n) && n > 0);
    const allowedLengths = validLengths.length ? validLengths : [24, 32];
    if (!allowedLengths.includes(tag.length)) {
        return `RFID must be exactly ${allowedLengths.join(' or ')} hexadecimal characters.`;
    }
    const prefixes = (window.APP_CONFIG && window.APP_CONFIG.validCardsStartIndex) || [];
    const normalizedPrefixes = prefixes.map((prefix) => String(prefix).trim().toUpperCase()).filter(Boolean);
    if (!normalizedPrefixes.some((prefix) => tag.startsWith(prefix))) {
        return 'The given data is not a valid fastag';
    }
    return null;
}

async function submitRfidCalibration() {
    const rawDataEl = document.getElementById('rfidCalibrationRawData');
    const inputEl = document.getElementById('rfidCalibrationInput');
    if (!rawDataEl || !inputEl || !pendingRfidCalibrationContext) return;

    const rawHex = (rawDataEl.value || '').trim().toUpperCase();
    const userTag = (inputEl.value || '').trim().toUpperCase();
    const validationError = validateFastagRfidInput(userTag);
    if (validationError) {
        showRfidCalibrationResult(validationError, false);
        return;
    }

    const start = rawHex.indexOf(userTag);
    if (start < 0) {
        showRfidCalibrationResult('Input RFID not found in raw RFID data.', false);
        return;
    }
    const length = userTag.length;
    const end = start + length;

    await saveRfidConfig(
        pendingRfidCalibrationContext.ip,
        pendingRfidCalibrationContext.port,
        pendingRfidCalibrationContext.mode,
        pendingRfidCalibrationContext.rfidMake,
        pendingRfidCalibrationContext.rfidModel,
        true,
        {
            manual_match_start: start,
            manual_match_length: length,
            manual_match_sample: userTag
        }
    );

    closeRfidCalibrationModal();
    showToast('success', 'RFID Calibration Saved', `Match stored at index ${start} to ${end}.`);
    pendingRfidCalibrationContext = null;
}

function updateRfidModalStatus(status, message, showSave = false, showRetry = false, showCancel = true) {
    const statusEl = document.getElementById('rfidModalStatus');
    const saveBtn = document.getElementById('rfidModalSaveBtn');
    const cancelBtn = document.getElementById('rfidModalCancelBtn');
    const retryBtn = document.getElementById('rfidModalRetryBtn');
    const countdownEl = document.getElementById('rfidModalCountdown');
    
    if (!statusEl) return;
    
    let icon = 'bi-info-circle';
    let color = 'var(--primary-color)';
    
    if (status === 'success') {
        icon = 'bi-check-circle-fill';
        color = 'var(--success-color, #28a745)';
    } else if (status === 'error' || status === 'failed') {
        icon = 'bi-x-circle-fill';
        color = 'var(--error-color, #dc3545)';
    } else if (status === 'warning') {
        icon = 'bi-exclamation-triangle-fill';
        color = 'var(--warning-color, #ffc107)';
    }
    
    statusEl.innerHTML = `<i class="bi ${icon}" style="color: ${color};"></i> <span>${message}</span>`;
    statusEl.style.color = color;
    
    if (saveBtn) {
        saveBtn.style.display = showSave ? 'inline-block' : 'none';
    }
    if (retryBtn) {
        retryBtn.style.display = showRetry ? 'inline-block' : 'none';
    }
    if (cancelBtn) {
        cancelBtn.style.display = showCancel ? 'inline-block' : 'none';
    }
    
    // Hide countdown if test is complete
    if (countdownEl && (status === 'success' || status === 'failed' || status === 'error')) {
        if (countdownEl.parentElement) {
            countdownEl.parentElement.style.display = 'none';
        }
    }
}

async function pollRfidTestStatus(ip, port, rfidMake, rfidModel, mode) {
    let pollInterval;
    
    // Poll for status every 500ms
    pollInterval = setInterval(async () => {
        try {
            const statusResponse = await fetch('/api/rfid/status');
            const status = await statusResponse.json();
            
            // Get countdown element each time (in case DOM changes)
            const countdownElement = document.getElementById('rfidModalCountdown');
            
            // Update countdown - check for time_remaining in status
            if (countdownElement) {
                const timeRemaining = status.time_remaining;
                if (timeRemaining !== undefined && timeRemaining !== null) {
                    // Ensure it's a number and update the display
                    const countdownValue = Math.max(0, Math.floor(timeRemaining));
                    countdownElement.textContent = countdownValue;
                    // Debug log (remove in production)
                    if (countdownValue % 5 === 0) {  // Log every 5 seconds
                        console.log('[RFID] Countdown updated to:', countdownValue);
                    }
                } else {
                    // If time_remaining is not available, log for debugging
                    console.warn('[RFID] time_remaining not in status response. Status:', status);
                }
            } else {
                console.error('[RFID] Countdown element (rfidModalCountdown) not found in DOM!');
            }

            // Show tag as soon as backend receives it (do not wait for test_complete)
            if (status.card_read === true) {
                const liveTag = status.parsed_tag || status.card_display || status.card_data || '';
                if (liveTag) {
                    showRfidModalReceivedData(liveTag);
                    if (!window._rfidToastShownForTag || window._rfidToastShownForTag !== liveTag) {
                        window._rfidToastShownForTag = liveTag;
                        showToast('success', 'RFID', 'RFID tag data received');
                    }
                }
            }
            
            // Check if test is complete
            if (status.test_complete === true) {
                clearInterval(pollInterval);
                
                console.log('[RFID] Test complete detected, fetching final result...');
                
                // Small delay to ensure backend has updated the status
                await new Promise(resolve => setTimeout(resolve, 100));
                
                // Get final result - use status endpoint instead of check to avoid triggering new test
                const finalResponse = await fetch('/api/rfid/status');
                const finalStatus = await finalResponse.json();
                
                console.log('[RFID] Final status received:', finalStatus);
                
                // Build result object from status
                const finalResult = {
                    status: 200,
                    mode: mode,
                    testing: finalStatus.testing,
                    test_complete: finalStatus.test_complete,
                    time_remaining: finalStatus.time_remaining,
                    card_read: finalStatus.card_read,
                    card_data: finalStatus.card_data,
                    card_display: finalStatus.card_display,
                    parsed_tag: finalStatus.parsed_tag
                };
                
                if (finalStatus.test_complete) {
                    // Use message from backend if available, otherwise use defaults
                    if (finalStatus.message) {
                        finalResult.message = finalStatus.message;
                    } else if (finalStatus.card_read) {
                        finalResult.message = "Reader Connected and Valid RFID received";
                    } else {
                        finalResult.warning = true;
                        finalResult.message = "Reader Connected, but no card read";
                    }
                }
                
                console.log('[RFID] Final result:', finalResult);
                
                // Only handle result if test is actually complete
                if (finalResult.test_complete === true) {
                    // Cancel timeout since we have a final result
                    if (window.rfidTestTimeoutDevices) {
                        clearTimeout(window.rfidTestTimeoutDevices);
                        window.rfidTestTimeoutDevices = null;
                    }
                    if (_rfidRetryContext) {
                        _rfidRetryContext.rfidMake = rfidMake;
                        _rfidRetryContext.rfidModel = rfidModel;
                    }
                    _rfidPendingResult = { result: finalResult, ip, port, rfidMake, rfidModel };
                    if (finalResult.card_read === true) {
                        const tag = finalResult.parsed_tag || finalResult.card_display || finalResult.card_data || '';
                        if (tag) showRfidModalReceivedData(tag);
                        // Hide status text - only the tag value is shown in modal
                        const statusEl = document.getElementById('rfidModalStatus');
                        if (statusEl) statusEl.style.display = 'none';
                        updateRfidModalStatus('success', '', true, true, true);
                        // Right-side popup with tag only (skip if already shown live)
                        if (tag && window._rfidToastShownForTag !== tag) {
                            window._rfidToastShownForTag = tag;
                            showToast('success', 'RFID', 'RFID tag data received');
                        }
                        showLoading(false);
                    } else {
                        const statusEl = document.getElementById('rfidModalStatus');
                        if (statusEl) statusEl.style.display = '';
                        const failedMsg = finalResult.message || 'No RFID data received. Please try again.';
                        updateRfidModalStatus('failed', failedMsg, false, true, true);
                        showLoading(false);
                    }
                } else {
                    console.warn('[RFID] Final result says test not complete, waiting...');
                }
            }
        } catch (error) {
            console.error('[RFID Status Poll] Error:', error);
            clearInterval(pollInterval);
            showLoading(false);
        }
    }, 500);
    
    // Timeout after 35 seconds (safety - slightly longer than 30 second test)
    // Store handle so we can cancel it once test completes successfully
    if (window.rfidTestTimeoutDevices) {
        clearTimeout(window.rfidTestTimeoutDevices);
    }
    window.rfidTestTimeoutDevices = setTimeout(() => {
        // If modal is already closed or test finished, do nothing
        const modal = document.getElementById('rfidCardReadModal');
        if (!modal || !modal.classList.contains('active')) {
            return;
        }
        clearInterval(pollInterval);
        showLoading(false);
        updateRfidModalStatus('failed', 'No RFID data received. Please try again.', false, true, true);
        showToast('warning', 'Timeout', 'No RFID data received. Please try again.');
    }, 35000);
}

function handleRfidResult(result, ip, port, rfidMake, rfidModel) {
    showLoading(false);
    
    if (result.status === 200) {
        // Show detected mode
        const statusEl = document.getElementById('rfidStatus');
        const modeEl = document.getElementById('rfidMode');
        if (statusEl) statusEl.style.display = 'flex';
        const modeLabel = result.mode === 'API'
            ? 'API'
            : (result.mode === 'CLIENT'
                ? 'Application as Client, RFID as Server'
                : 'Application as Server, RFID as Client');
        if (modeEl) modeEl.textContent = modeLabel;

        if (result.mode === 'API') {
            if (result.card_read === true) {
                const tag = result.parsed_tag || result.card_display || result.card_data || '';
                // Toast already shown when tag arrived; avoid duplicate "RFID data received" text
                if (tag && window._rfidToastShownForTag !== tag) {
                    showToast('success', 'RFID', 'RFID tag data received');
                }
                const username = document.getElementById('rfidUsername')?.value.trim() || 'admin';
                const password = document.getElementById('rfidPassword')?.value || '';
                saveRfidConfig(ip, port || '443', 'API', rfidMake, rfidModel, true, { username, password });
            } else {
                showToast('warning', 'RFID', result.message || 'No RFID data received. Please try again.');
            }
            return;
        }
        
        // Check if card was read (CLIENT mode only)
        if (result.mode === 'CLIENT') {
            // CRITICAL: For CLIENT mode, only proceed if test is complete
            // Do NOT save or navigate if test is still running
            if (result.testing === true || result.test_complete === false) {
                console.log('[RFID] Test still running, cannot save config yet. Testing:', result.testing, 'Complete:', result.test_complete);
                // Don't save - wait for test to complete
                return;
            }
            
            // Test is complete - check result
            if (result.card_read === true) {
                // Card read successful - validate and save
                const message = result.message || "Reader Connected and Valid RFID received";
                showToast('success', 'Success', message);
                openRfidCalibrationModal(result.card_display || result.parsed_tag || result.card_data, { ip, port, mode: result.mode, rfidMake, rfidModel });
            } else {
                // Connection successful but no card read - save without validation
                const message = result.message || "Reader Connected, but no card read";
                showToast('warning', 'Warning', message);
                saveRfidConfig(ip, port, result.mode, rfidMake, rfidModel, false);
            }
        } else if (result.mode === 'SERVER') {
            // CRITICAL: For SERVER mode, only proceed if test is complete
            // Do NOT save or navigate if test is still running
            if (result.testing === true || result.test_complete === false) {
                console.log('[RFID] Test still running, cannot save config yet. Testing:', result.testing, 'Complete:', result.test_complete);
                // Don't save - wait for test to complete
                return;
            }
            
            // Test is complete - check result
            if (result.card_read === true) {
                // Card read successful - validate and save
                const message = result.message || "Reader Connected and Valid RFID received";
                showToast('success', 'Success', message);
                openRfidCalibrationModal(result.card_display || result.parsed_tag || result.card_data, { ip, port, mode: result.mode, rfidMake, rfidModel });
            } else {
                // Connection successful but no card read - save without validation
                const message = result.message || "Reader Connected, but no card read";
                showToast('warning', 'Warning', message);
                saveRfidConfig(ip, port, result.mode, rfidMake, rfidModel, false);
            }
        }
    } else {
        showToast('error', 'Connection Failed', result.message);
    }
}

async function saveRfidConfig(ip, port, mode, rfidMake, rfidModel, validated, calibrationData = {}) {
    try {
        const username = calibrationData.username
            ?? (document.getElementById('rfidUsername')?.value.trim() || 'admin');
        const password = calibrationData.password
            ?? (document.getElementById('rfidPassword')?.value || '');
        const { username: _u, password: _p, ...restCal } = calibrationData;
        console.log(`[RFID] Saving config - validated: ${validated}, mode: ${mode}`);
        await fetch('/api/config/rfid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                ip, 
                port, 
                mode, 
                make: rfidMake,
                model: rfidModel,
                username,
                password,
                validated: validated,
                ...restCal
            })
        });
        
        // Only mark as validated and navigate if validated is true
        // This prevents navigation when RFID test fails or is incomplete
        if (validated === true) {
            console.log('[RFID] Config validated, marking section and navigating to Handheld RFID...');
            markSectionValidated('rfid');
            updateAssignedDevice('rfid', ip, true);
            // Always go to Handheld RFID next when that section exists
            const sections = getWizardNavSections();
            if (sections.includes('handheld-rfid')) {
                showSection('handheld-rfid');
            } else {
                navigateToNext('rfid');
            }
        } else {
            console.log('[RFID] Config saved but NOT validated - staying on RFID page');
            // Show status but don't navigate
            document.getElementById('rfidStatus').style.display = 'flex';
        }
    } catch (error) {
        console.error('[Save RFID Config] Error:', error);
        showToast('error', 'Error', 'Failed to save RFID configuration');
    }
}

// ============== Camera Configuration ==============
function isWeighbridgeProfile() {
    const family = (window.APP_CONFIG && APP_CONFIG.profile && APP_CONFIG.profile.family) || '';
    return family === 'weighbridge';
}

function applyCameraUiForProfile() {
    const topCard = document.getElementById('topCameraCard');
    const frontCard = document.getElementById('frontCameraCard');
    if (!topCard || !frontCard) return;
    // Checkpoints configure Front only. Weighbridges configure Top + Front.
    topCard.style.display = isWeighbridgeProfile() ? '' : 'none';
    frontCard.style.display = '';
}

async function checkCamera(cameraId) {
    if (!APP_CONFIG.enableCamera) {
        showToast('error', 'Camera', 'Camera configuration is disabled.');
        return;
    }
    const urlInput = cameraId === 'top' ? 'topCameraUrl' : 'frontCameraUrl';
    const rtspUrl = document.getElementById(urlInput).value.trim();
    const cameraMake = document.getElementById(cameraId + 'CameraMake')?.value.trim() || '';
    const cameraModel = document.getElementById(cameraId + 'CameraModel')?.value.trim() || '';
    
    if (!rtspUrl) {
        showToast('error', 'Validation Error', 'Please enter RTSP URL');
        return;
    }
    
    // Validate device info in production mode
    if (!validateDeviceInfo(cameraMake, cameraModel, `${cameraId.charAt(0).toUpperCase() + cameraId.slice(1)} Camera`)) {
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/camera/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camera_id: cameraId, rtsp_url: rtspUrl })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            // Show camera feed
            const feedImg = document.getElementById(cameraId + 'CameraFeed');
            const placeholder = document.getElementById(cameraId + 'CameraPlaceholder');
            
            feedImg.src = `/video_feed/${cameraId}?t=${Date.now()}`;
            feedImg.classList.add('active');
            placeholder.classList.add('hidden');
            
            // Save configuration
            const payload = {
                [cameraId]: {
                    rtsp_url: rtspUrl,
                    make: cameraMake,
                    model: cameraModel,
                    validated: true
                }
            };
            
            await fetch('/api/config/camera', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            // Keep local config in sync for completion checks
            if (!config.camera) config.camera = {};
            if (!config.camera[cameraId]) config.camera[cameraId] = {};
            Object.assign(config.camera[cameraId], payload[cameraId]);
            
            showToast('success', 'Success', `${cameraId.charAt(0).toUpperCase() + cameraId.slice(1)} camera connected`);
            
            await loadCompletionStatus();
            showLoading(false);

            // After feed is visible, go to Display when all required cameras are done
            const cameraComplete = isCameraSectionComplete();
            if (cameraComplete) {
                markSectionValidated('camera');
                // Let the live feed show briefly before navigating
                await new Promise((resolve) => setTimeout(resolve, 2000));
                const sections = getWizardNavSections();
                if (sections.includes('display')) {
                    showSection('display');
                } else {
                    navigateToNext('camera');
                }
            } else if (isWeighbridgeProfile()) {
                const other = cameraId === 'top' ? 'front' : 'top';
                showToast(
                    'info',
                    'Camera',
                    `${cameraId.charAt(0).toUpperCase() + cameraId.slice(1)} feed OK. Check & Save ${other} camera next.`
                );
            }
            return;
        } else {
            showToast('error', 'Connection Failed', result.message || 'RTSP stream not available. Re-enter URL and try again.');
        }
    } catch (error) {
        console.error('[Camera Check] Error:', error);
        showToast('error', 'Connection Error', 'Unable to check camera connection. Re-enter RTSP URL and try again.');
    } finally {
        showLoading(false);
    }
}

/** True when required camera(s) for this profile are validated. */
function isCameraSectionComplete() {
    const cam = (config && config.camera) || {};
    const frontOk = !!(cam.front && cam.front.validated === true);
    if (isWeighbridgeProfile()) {
        const topOk = !!(cam.top && cam.top.validated === true);
        return topOk && frontOk;
    }
    // Checkpoints: Front camera only
    return frontOk;
}

async function stopCamera(cameraId) {
    if (!APP_CONFIG.enableCamera) {
        return;
    }
    try {
        await fetch(`/api/camera/stop/${cameraId}`, { method: 'POST' });
        
        const feedImg = document.getElementById(cameraId + 'CameraFeed');
        const placeholder = document.getElementById(cameraId + 'CameraPlaceholder');
        
        feedImg.src = '';
        feedImg.classList.remove('active');
        placeholder.classList.remove('hidden');
        
        showToast('success', 'Stopped', `${cameraId} camera stopped`);
    } catch (error) {
        console.error('[Camera Stop] Error:', error);
        showToast('error', 'Error', 'Unable to stop camera stream');
    }
}

// ============== Display Configuration ==============
function toggleDisplayFields() {
    const displayType = document.getElementById('displayType').value;
    const ipGroup = document.getElementById('displayIpGroup');
    const portGroup = document.getElementById('displayPortGroup');
    const mqttInfo = document.getElementById('mqttInfo');
    
    if (displayType === 'mqtt') {
        ipGroup.style.display = 'none';
        if (portGroup) portGroup.style.display = 'none';
        mqttInfo.style.display = 'block';
        const portEl = document.getElementById('displayPort');
        if (portEl && (!portEl.value || ['8000', '80', '81', '8080'].includes(portEl.value))) {
            portEl.value = '1883';
        }
    } else {
        ipGroup.style.display = 'block';
        if (portGroup) portGroup.style.display = 'block';
        mqttInfo.style.display = 'none';
    }
}

async function checkAndSaveDisplay() {
    const displayType = document.getElementById('displayType').value;
    const isManual = document.getElementById('displayIpManual')?.checked;
    const displayIp = isManual 
        ? document.getElementById('displayIp').value.trim()
        : (document.getElementById('displayIpSelect')?.value || document.getElementById('displayIp').value.trim());
    const displayPort = displayType === 'mqtt'
        ? '1883'
        : (document.getElementById('displayPort')?.value.trim() || '8000');
    const displayMake = document.getElementById('displayMake')?.value.trim() || '';
    const displayModel = document.getElementById('displayModel')?.value.trim() || '';
    
    if (displayType === 'api' && !displayIp) {
        showToast('error', 'Validation Error', 'Please enter Display IP');
        return;
    }
    if (displayType === 'api' && !displayPort) {
        showToast('error', 'Validation Error', 'Please enter Display Port');
        return;
    }
    
    // Validate device info in production mode
    if (!validateDeviceInfo(displayMake, displayModel, 'Display')) {
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/display/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: displayType, ip: displayIp, port: displayPort })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            // Save configuration
            const displayMake = document.getElementById('displayMake')?.value || '';
            const displayModel = document.getElementById('displayModel')?.value || '';
            
            await fetch('/api/config/display', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    type: displayType, 
                    ip: displayIp, 
                    port: displayPort,
                    make: displayMake,
                    model: displayModel,
                    validated: true 
                })
            });
            
            showToast('success', 'Success', result.message);
            markSectionValidated('display');
            updateAssignedDevice('display', displayIp, true);
            navigateToNext('display');
        } else {
            showToast('error', 'Connection Failed', result.message);
        }
    } catch (error) {
        console.error('[Display Check] Error:', error);
        showToast('error', 'Connection Error', 'Unable to check display connection');
    } finally {
        showLoading(false);
    }
}

// ============== I/O Controller Configuration ==============
let ioConnected = false;
let ioRegisterConfig = {
    inputType: 'coil',
    inputStartAddress: 8,
    outputType: 'coil',
    outputStartAddress: 0
};
let ioTestStatus = {
    sensor1: false,
    sensor1Validated: false,
    sensor2: false,
    sensor2Validated: false,
    sensor3: false,
    sensor3Validated: false,
    entryTL: false,
    entryTLValidated: false,
    exitTL: false,
    exitTLValidated: false,
    boomBarrier: false,
    entryBBValidated: false,
    exitBBValidated: false,
    entryBBDirect: false,
    exitBBDirect: false,
    entryBBRelay: false,
    exitBBRelay: false,
    entryBBDirectOpen: false,
    entryBBDirectClose: false,
    exitBBDirectOpen: false,
    exitBBDirectClose: false,
    entryBBRelayOpen: false,
    entryBBRelayClose: false,
    exitBBRelayOpen: false,
    exitBBRelayClose: false
};
// Snapshot of last-saved I/O configuration (from backend)
let originalIoConfig = null;
let ioConfigDirty = false;

// Calculate actual register address from channel number
// NOTE: Channel numbers are now 0-based (matching Modbus convention)
// Channel 0 = Start Address + 0, Channel 1 = Start Address + 1, etc.
function getInputAddress(channelNumber) {
    const channel = parseInt(channelNumber);
    if (isNaN(channel) || channel < 0) {
        console.error(`[IO] Invalid input channel number: ${channelNumber}`);
        return null;
    }
    return ioRegisterConfig.inputStartAddress + channel;
}

function getOutputAddress(channelNumber) {
    const channel = parseInt(channelNumber);
    if (isNaN(channel) || channel < 0) {
        console.error(`[IO] Invalid output channel number: ${channelNumber}`);
        return null;
    }
    const uiStartAddress = parseInt(document.getElementById('outputStartAddress')?.value);
    const outputStartAddress = Number.isNaN(uiStartAddress) ? ioRegisterConfig.outputStartAddress : uiStartAddress;
    return outputStartAddress + channel;
}

function toggleIOFields() {
    const ioType = document.getElementById('ioType').value;
    const ethernetFields = document.getElementById('ioEthernetFields');
    const serialFields = document.getElementById('ioSerialFields');
    
    if (ioType === 'ethernet') {
        ethernetFields.style.display = 'block';
        serialFields.style.display = 'none';
    } else {
        ethernetFields.style.display = 'none';
        serialFields.style.display = 'block';
        loadIOSerialPorts();
    }
}

function toggleRelayFields() {
    // output_mode: "direct" = separate pins for each light (inbuilt I/O card relay)
    // output_mode: "relay" = single pin controls external 4-channel relay module
    const outputMode = document.getElementById('outputMode').value;
    const tlDirect = document.getElementById('tlDirectMode');
    const tlRelay = document.getElementById('tlRelayMode');
    const bbDirect = document.getElementById('bbDirectMode');
    const bbRelay = document.getElementById('bbRelayMode');
    
    if (outputMode === 'direct') {
        tlDirect.style.display = 'block';
        tlRelay.style.display = 'none';
        bbDirect.style.display = 'block';
        bbRelay.style.display = 'none';
    } else {
        tlDirect.style.display = 'none';
        tlRelay.style.display = 'block';
        bbDirect.style.display = 'none';
        bbRelay.style.display = 'block';
    }
}

async function loadIOSerialPorts() {
    try {
        const response = await fetch('/api/digitizer/ports');
        const data = await response.json();
        
        const select = document.getElementById('ioSerialPort');
        select.innerHTML = '<option value="">Select port...</option>';
        
        data.ports.forEach(port => {
            const option = document.createElement('option');
            option.value = port.device;
            option.textContent = `${port.device} - ${port.description}`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load serial ports:', error);
    }
}

async function connectIOController() {
    const ioType = document.getElementById('ioType').value;
    const slaveId = document.getElementById('ioSlaveId').value;
    const outputMode = document.getElementById('outputMode').value;
    
    // Store register configuration
    ioRegisterConfig = {
        inputType: document.getElementById('inputRegisterType').value,
        inputStartAddress: parseInt(document.getElementById('inputStartAddress').value) || 0,
        outputType: document.getElementById('outputRegisterType').value,
        outputStartAddress: parseInt(document.getElementById('outputStartAddress').value) || 0
    };
    
    // Build connection data matching weighbridge_app format
    let connectionData = { 
        type: ioType, 
        slave_id: slaveId,
        output_mode: outputMode,
        connection: {
            ethernet: {
                ip: "",
                port: "502",
                timeout: "1"
            },
            serial: {
                port: "",
                baud_rate: "9600",
                bytesize: "8",
                parity: "N",
                stopbits: "1",
                timeout: "0.5"
            }
        }
    };
    
    if (ioType === 'ethernet') {
        const isManual = document.getElementById('ioIpManual')?.checked;
        const ip = isManual 
            ? document.getElementById('ioIp').value.trim()
            : (document.getElementById('ioIpSelect')?.value || document.getElementById('ioIp').value.trim());
        connectionData.connection.ethernet.ip = ip;
        connectionData.connection.ethernet.port = document.getElementById('ioPort').value.trim() || "502";
        
        if (!ip) {
            showToast('error', 'Validation Error', 'Please enter IP Address');
            return;
        }
    } else {
        connectionData.connection.serial.port = document.getElementById('ioSerialPort').value;
        connectionData.connection.serial.baud_rate = document.getElementById('ioBaudRate').value || "9600";
        
        if (!connectionData.connection.serial.port) {
            showToast('error', 'Validation Error', 'Please select Serial Port');
            return;
        }
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/io/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(connectionData)
        });
        
        const result = await response.json();
        showLoading(false);
        
        if (result.status === 200) {
            ioConnected = true;
            document.getElementById('ioPinConfig').style.display = 'block';
            const modeMsg = outputMode === 'relay' ? ' [External Relay Mode]' : ' [Direct Mode]';
            showToast('success', 'Connected', result.message + modeMsg);
            toggleRelayFields();
        } else {
            showToast('error', 'Connection Failed', result.message);
        }
    } catch (error) {
        showLoading(false);
        console.error('[I/O Controller] Connection error:', error);
        showToast('error', 'Connection Error', 'Unable to connect to I/O controller');
    }
}

// Initialize change detection for I/O controller fields (devices view).
// Safe to call multiple times; listeners will only be attached once per element.
function initIoChangeDetection() {
    const ioFieldIds = [
        'ioType', 'ioSlaveId',
        'ioIp', 'ioPort',
        'ioSerialPort', 'ioBaudRate',
        'inputRegisterType', 'inputStartAddress',
        'outputRegisterType', 'outputStartAddress',
        'outputMode',
        'ioMake', 'ioModel',
        'sensor1Pin', 'sensor1DefaultSignal', 'sensor1Make', 'sensor1Model',
        'sensor2Pin', 'sensor2DefaultSignal', 'sensor2Make', 'sensor2Model',
        'sensor3Pin', 'sensor3DefaultSignal', 'sensor3Make', 'sensor3Model',
        'entryTLMake', 'entryTLModel', 'entryRedPin', 'entryGreenPin',
        'exitTLMake', 'exitTLModel', 'exitRedPin', 'exitGreenPin',
        'entryTLRelayPin', 'exitTLRelayPin',
        'entryBoomOpenPin', 'entryBoomClosePin', 'entryBoomEnabled',
        'exitBoomOpenPin', 'exitBoomClosePin', 'exitBoomEnabled',
        'entryBoomRelayPin', 'entryBoomRelayEnabled',
        'exitBoomRelayPin', 'exitBoomRelayEnabled'
    ];

    ioFieldIds.forEach(id => {
        const el = document.getElementById(id);
        if (el && !el.dataset.ioChangeBound) {
            el.addEventListener('change', handleIoFieldChanged);
            el.addEventListener('input', handleIoFieldChanged);
            el.dataset.ioChangeBound = 'true';
        }
    });
}

function handleIoFieldChanged(event) {
    const changedId = event?.target?.id || '';

    // Enable toggle always updates Skipped/cleared UI (even when config already dirty)
    if (isBoomBarrierEnableToggleId(changedId)) {
        syncBoomBarrierStateFromEnable(changedId.startsWith('entry') ? 'entry' : 'exit');
    }

    // Only mark dirty once per load/reset
    if (ioConfigDirty) {
        return;
    }

    ioConfigDirty = true;

    boomLog('FIELD_CHANGED', { changedId });
    const boomFields = new Set([
        'entryBoomEnabled', 'exitBoomEnabled',
        'entryBoomOpenPin', 'entryBoomClosePin', 'exitBoomOpenPin', 'exitBoomClosePin',
        'entryBoomRelayEnabled', 'exitBoomRelayEnabled',
        'entryBoomRelayPin', 'exitBoomRelayPin',
        'entryBBMake', 'entryBBModel', 'exitBBMake', 'exitBBModel',
        'boomBarrierMake', 'boomBarrierModel'
    ]);
    const trafficFields = new Set([
        'entryRedPin', 'entryGreenPin', 'exitRedPin', 'exitGreenPin',
        'entryTLRelayPin', 'exitTLRelayPin',
        'entryTLMake', 'entryTLModel', 'exitTLMake', 'exitTLModel'
    ]);
    const sensorFields = new Set([
        'sensor1Pin', 'sensor2Pin', 'sensor3Pin',
        'sensor1DefaultSignal', 'sensor2DefaultSignal', 'sensor3DefaultSignal',
        'sensor1Make', 'sensor1Model', 'sensor2Make', 'sensor2Model', 'sensor3Make', 'sensor3Model'
    ]);

    // Reset only impacted test groups for better UX.
    if (boomFields.has(changedId)) {
        const isEntryField = changedId.startsWith('entry');
        const isExitField = changedId.startsWith('exit');
        const isEnableToggle = isBoomBarrierEnableToggleId(changedId);
        const isGlobalBoomField =
            changedId === 'boomBarrierMake' ||
            changedId === 'boomBarrierModel' ||
            changedId === 'outputMode';

        if (isEnableToggle) {
            // UI/state already synced above (before dirty guard)
        } else if (isEntryField) {
            ioTestStatus.entryBBValidated = false;
            ioTestStatus.entryBBDirect = false;
            ioTestStatus.entryBBRelay = false;
            ioTestStatus.entryBBDirectOpen = false;
            ioTestStatus.entryBBDirectClose = false;
            ioTestStatus.entryBBRelayOpen = false;
            ioTestStatus.entryBBRelayClose = false;
        } else if (isExitField) {
            ioTestStatus.exitBBValidated = false;
            ioTestStatus.exitBBDirect = false;
            ioTestStatus.exitBBRelay = false;
            ioTestStatus.exitBBDirectOpen = false;
            ioTestStatus.exitBBDirectClose = false;
            ioTestStatus.exitBBRelayOpen = false;
            ioTestStatus.exitBBRelayClose = false;
        } else if (isGlobalBoomField) {
            ioTestStatus.entryBBValidated = false;
            ioTestStatus.exitBBValidated = false;
            ioTestStatus.entryBBDirect = false;
            ioTestStatus.exitBBDirect = false;
            ioTestStatus.entryBBRelay = false;
            ioTestStatus.exitBBRelay = false;
            ioTestStatus.entryBBDirectOpen = false;
            ioTestStatus.entryBBDirectClose = false;
            ioTestStatus.exitBBDirectOpen = false;
            ioTestStatus.exitBBDirectClose = false;
            ioTestStatus.entryBBRelayOpen = false;
            ioTestStatus.entryBBRelayClose = false;
            ioTestStatus.exitBBRelayOpen = false;
            ioTestStatus.exitBBRelayClose = false;
        } else {
            // Safe fallback for any future boom field ids
            ioTestStatus.entryBBValidated = false;
            ioTestStatus.exitBBValidated = false;
            ioTestStatus.entryBBDirect = false;
            ioTestStatus.exitBBDirect = false;
            ioTestStatus.entryBBRelay = false;
            ioTestStatus.exitBBRelay = false;
            ioTestStatus.entryBBDirectOpen = false;
            ioTestStatus.entryBBDirectClose = false;
            ioTestStatus.exitBBDirectOpen = false;
            ioTestStatus.exitBBDirectClose = false;
            ioTestStatus.entryBBRelayOpen = false;
            ioTestStatus.entryBBRelayClose = false;
            ioTestStatus.exitBBRelayOpen = false;
            ioTestStatus.exitBBRelayClose = false;
        }

        ioTestStatus.boomBarrier =
            ioTestStatus.entryBBDirect || ioTestStatus.exitBBDirect ||
            ioTestStatus.entryBBRelay || ioTestStatus.exitBBRelay;
        boomLog('RESET_BOOM_TEST_STATE', {
            changedId,
            entryBBDirect: ioTestStatus.entryBBDirect,
            exitBBDirect: ioTestStatus.exitBBDirect,
            entryBBRelay: ioTestStatus.entryBBRelay,
            exitBBRelay: ioTestStatus.exitBBRelay
        });
    } else if (trafficFields.has(changedId)) {
        ioTestStatus.entryTL = false;
        ioTestStatus.entryTLValidated = false;
        ioTestStatus.exitTL = false;
        ioTestStatus.exitTLValidated = false;
    } else if (sensorFields.has(changedId)) {
        const sensorNum = getSensorNumFromIoFieldId(changedId);
        if (sensorNum) resetSensorTestState(sensorNum);
    } else {
        // Connection/register/function-code changes affect all tests.
        ioTestStatus = {
            sensor1: false,
            sensor1Validated: false,
            sensor2: false,
            sensor2Validated: false,
            sensor3: false,
            sensor3Validated: false,
            entryTL: false,
            entryTLValidated: false,
            exitTL: false,
            exitTLValidated: false,
            boomBarrier: false,
            entryBBValidated: false,
            exitBBValidated: false,
            entryBBDirect: false,
            exitBBDirect: false,
            entryBBRelay: false,
            exitBBRelay: false,
            entryBBDirectOpen: false,
            entryBBDirectClose: false,
            exitBBDirectOpen: false,
            exitBBDirectClose: false,
            entryBBRelayOpen: false,
            entryBBRelayClose: false,
            exitBBRelayOpen: false,
            exitBBRelayClose: false
        };
    }

    // Mark I/O section as NOT validated so user must save configuration again
    markSectionNotValidated('io-controller');
}

// Sensor Testing
async function testSensor(sensorNum) {
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const channelNum = document.getElementById(`sensor${sensorNum}Pin`).value;
    const defaultSignal = document.getElementById(`sensor${sensorNum}DefaultSignal`).value;
    const statusEl = document.getElementById(`sensor${sensorNum}Status`);
    
    if (channelNum === '' || channelNum === null || channelNum === undefined) {
        showToast('error', 'Missing Channel', `Please enter channel number for ${getSensorRoleLabel(sensorNum)}`);
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const expectedDefault = defaultSignal === 'high';
    const registerAddress = getInputAddress(channelNum);
    
    // Validate register address
    if (registerAddress === null || registerAddress < 0) {
        showToast('error', 'Invalid Channel', `Invalid channel number: ${channelNum}. Must be 0 or higher.`);
        return;
    }
    
    statusEl.textContent = 'Testing...';
    statusEl.className = 'device-status testing';
    
    // Use current UI register type to derive function code (FC1=coil, FC2=discrete).
    // This avoids stale saved config forcing wrong function code during live tests.
    const inputRegisterType = document.getElementById('inputRegisterType')?.value || ioRegisterConfig.inputType || 'discrete';
    const functionCode = inputRegisterType === 'coil' ? 1 : 2;
    
    try {
        // Step 1: Check default state (no-cut)
        const checkResponse = await fetch('/api/io/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pin_type: 'input',
                register_type: ioRegisterConfig.inputType,
                register_address: registerAddress,
                slave_id: parseInt(slaveId),
                action: 'read',
                function_code: functionCode
            })
        });
        
        const checkResult = await checkResponse.json();
        
        if (checkResult.status !== 200) {
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Read Error', checkResult.message);
            return;
        }
        
        const currentValue = checkResult.value;
        
        if (currentValue !== expectedDefault) {
            // Default state doesn't match - maybe sensor is triggered
            showToast('warning', 'Check Sensor', `${getSensorRoleLabel(sensorNum)} (addr ${registerAddress}) current state doesn't match expected default. Make sure sensor is NOT triggered.`);
            statusEl.textContent = 'Check';
            statusEl.className = 'device-status error';
            return;
        }
        
        // Step 2: Ask user to trigger the sensor using modal
        const triggerMessage = `${getSensorRoleLabel(sensorNum)} (address ${registerAddress}) default state verified (${defaultSignal.toUpperCase()}).\n\nNow please TRIGGER the sensor (cut/activate it) and click OK.`;
        
        showSensorConfirmModal(triggerMessage, async (confirmed) => {
            if (!confirmed) {
                statusEl.textContent = 'Cancelled';
                statusEl.className = 'device-status';
                resetDeviceStatus('sensor', sensorNum);
                return;
            }
            
            // Step 3: Check triggered state
            try {
                const triggerResponse = await fetch('/api/io/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        pin_type: 'input',
                        register_type: ioRegisterConfig.inputType,
                        register_address: registerAddress,
                        slave_id: parseInt(slaveId),
                        action: 'read',
                        function_code: functionCode
                    })
                });
                
                const triggerResult = await triggerResponse.json();
                
                if (triggerResult.status !== 200) {
                    statusEl.textContent = 'Error';
                    statusEl.className = 'device-status error';
                    showToast('error', 'Read Error', triggerResult.message);
                    return;
                }
                
                const triggeredValue = triggerResult.value;
                const expectedTriggered = !expectedDefault;
                
                if (triggeredValue === expectedTriggered) {
                    statusEl.textContent = 'Passed';
                    statusEl.className = 'device-status success';
                    ioTestStatus[`sensor${sensorNum}`] = true;
                    if (Number(sensorNum) === 1) {
                        ioTestStatus.sensor1Validated = true;
                    } else if (Number(sensorNum) === 2) {
                        ioTestStatus.sensor2Validated = true;
                    } else if (Number(sensorNum) === 3) {
                        ioTestStatus.sensor3Validated = true;
                    }
                    showToast('success', 'Test Passed', `${getSensorRoleLabel(sensorNum)} (address ${registerAddress}) working correctly!`);
                } else {
                    statusEl.textContent = 'Failed';
                    statusEl.className = 'device-status error';
                    showToast('error', 'Test Failed', `${getSensorRoleLabel(sensorNum)} state didn't change as expected.`);
                }
            } catch (error) {
                statusEl.textContent = 'Error';
                statusEl.className = 'device-status error';
                console.error(`[${getSensorRoleLabel(sensorNum)} Test] Error:`, error);
                showToast('error', 'Test Error', 'Unable to communicate with sensor');
            }
        });
        return;
        
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[${getSensorRoleLabel(sensorNum)} Test] Error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with sensor');
    }
}

// Traffic Light Color Testing (Internal Relay - separate Red/Green)
async function testTrafficLightColor(location, color) {
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const outputRegisterType = document.getElementById('outputRegisterType')?.value || ioRegisterConfig.outputType;
    const statusElId = location === 'entry' ? 'entryTLStatus' : 'exitTLStatus';
    const statusEl = document.getElementById(statusElId);
    
    // Get the channel for the specific color
    const channelNum = document.getElementById(`${location}${color.charAt(0).toUpperCase() + color.slice(1)}Pin`).value;
    
    if (channelNum === '' || channelNum === null || channelNum === undefined) {
        showToast('error', 'Missing Channel', `Please enter channel number for ${location} ${color} light`);
        return;
    }
    
    const registerAddress = getOutputAddress(channelNum);
    
    // Validate register address
    if (registerAddress === null || registerAddress < 0) {
        showToast('error', 'Invalid Channel', `Invalid channel number: ${channelNum}. Must be 0 or higher.`);
        return;
    }
    
    statusEl.textContent = `Testing ${color}...`;
    statusEl.className = 'device-status testing';
    
    try {
        // Step 1: Turn ON the relay
        const onResponse = await fetch('/api/io/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pin_type: 'output',
                register_type: outputRegisterType,
                register_address: registerAddress,
                slave_id: parseInt(slaveId),
                action: 'on'
            })
        });
        
        const onResult = await onResponse.json();
        
        if (onResult.status !== 200) {
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Error', onResult.message);
            return;
        }
        
        // Step 2: Show confirmation modal
        showHardwareTestModal('traffic_light', location, color, async (verified, data) => {
            // Step 3: Turn OFF the relay (always turn off after test)
            await fetch('/api/io/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pin_type: 'output',
                    register_type: outputRegisterType,
                    register_address: registerAddress,
                    slave_id: parseInt(slaveId),
                    action: 'off'
                })
            });
            
            if (verified) {
                statusEl.textContent = `${color} OK`;
                statusEl.className = 'device-status success';
                ioTestStatus[`${location}TL`] = true;
                ioTestStatus[`${location}TLValidated`] = true;
                showToast('success', 'Test Passed', `${location} ${color} light working!`);
            } else {
                statusEl.textContent = 'Failed';
                statusEl.className = 'device-status error';
                resetDeviceStatus('trafficLight', location);
                showToast('error', 'Test Failed', `${location} ${color} light not responding`);
            }
        });
        
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[Traffic Light ${location} ${color}] Test error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with traffic light');
    }
}

// Traffic Light Testing (External Relay - single channel toggle)
async function testTrafficLight(location, relayMode) {
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const outputRegisterType = document.getElementById('outputRegisterType')?.value || ioRegisterConfig.outputType;
    let statusElId = location === 'entry' ? 'entryTLExtStatus' : 'exitTLExtStatus';
    const statusEl = document.getElementById(statusElId);
    
    const channelNum = document.getElementById(`${location}TLPin`).value;
    if (channelNum === '' || channelNum === null || channelNum === undefined) {
        showToast('error', 'Missing Channel', `Please enter channel number for ${location} traffic light`);
        return;
    }
    
    const registerAddress = getOutputAddress(channelNum);
    
    // Validate register address
    if (registerAddress === null || registerAddress < 0) {
        showToast('error', 'Invalid Channel', `Invalid channel number: ${channelNum}. Must be 0 or higher.`);
        return;
    }
    
    statusEl.textContent = 'Testing...';
    statusEl.className = 'device-status testing';
    
    try {
        // Step 1: Turn ON the relay
        const onResponse = await fetch('/api/io/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pin_type: 'output',
                register_type: outputRegisterType,
                register_address: registerAddress,
                slave_id: parseInt(slaveId),
                action: 'on'
            })
        });
        
        const onResult = await onResponse.json();
        
        if (onResult.status !== 200) {
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Error', onResult.message);
            return;
        }
        
        // Step 2: Show confirmation modal
        showHardwareTestModal('traffic_light', location, color, async (verified, data) => {
            // Step 3: Turn OFF the relay
            await fetch('/api/io/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pin_type: 'output',
                    register_type: outputRegisterType,
                    register_address: registerAddress,
                    slave_id: parseInt(slaveId),
                    action: 'off'
                })
            });
            
            if (verified) {
                statusEl.textContent = 'Passed';
                statusEl.className = 'device-status success';
                ioTestStatus[`${location}TL`] = true;
                ioTestStatus[`${location}TLValidated`] = true;
                showToast('success', 'Test Passed', `${location} traffic light ${color} working!`);
            } else {
                statusEl.textContent = 'Failed';
                statusEl.className = 'device-status error';
                resetDeviceStatus('trafficLight', location);
                showToast('error', 'Test Failed', `${location} traffic light not responding`);
            }
        });
        
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[Traffic Light ${location}] Test error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with traffic light');
    }
}

// Boom Barrier Testing
async function testBoomBarrier(action, relayMode) {
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const outputRegisterType = document.getElementById('outputRegisterType')?.value || ioRegisterConfig.outputType;
    let channelNum;
    let statusElId = relayMode === 'external' ? 'bbExtStatus' : 'bbStatus';
    
    if (relayMode === 'external') {
        channelNum = document.getElementById('boomPin').value;
        if (channelNum === '' || channelNum === null || channelNum === undefined) {
            showToast('error', 'Missing Channel', 'Please enter channel number for boom barrier');
            return;
        }
    } else {
        // Internal relay: separate pins for open and close
        channelNum = action === 'open' ? document.getElementById('boomOpenPin').value : document.getElementById('boomClosePin').value;
        if (channelNum === '' || channelNum === null || channelNum === undefined) {
            showToast('error', 'Missing Channel', `Please enter ${action} channel number for boom barrier`);
            return;
        }
    }
    
    const registerAddress = getOutputAddress(channelNum);
    
    // Validate register address
    if (registerAddress === null || registerAddress < 0) {
        showToast('error', 'Invalid Channel', `Invalid channel number: ${channelNum}. Must be 0 or higher.`);
        return;
    }
    
    const statusEl = document.getElementById(statusElId);
    statusEl.textContent = `${action}ing...`;
    statusEl.className = 'device-status testing';
    
    try {
        // Step 1: Turn ON the relay (send command)
        const onResponse = await fetch('/api/io/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pin_type: 'output',
                register_type: outputRegisterType,
                register_address: registerAddress,
                slave_id: parseInt(slaveId),
                action: 'on'
            })
        });
        
        const onResult = await onResponse.json();
        
        if (onResult.status !== 200) {
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Error', onResult.message);
            return;
        }
        
        // Step 2: Show confirmation modal (using 'entry' as default location for external relay mode)
        showHardwareTestModal('boom_barrier', 'entry', action, async (verified, data) => {
            // Step 3: Turn OFF the relay (always turn off after command)
            await fetch('/api/io/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pin_type: 'output',
                    register_type: outputRegisterType,
                    register_address: registerAddress,
                    slave_id: parseInt(slaveId),
                    action: 'off'
                })
            });
            
            if (verified) {
                statusEl.textContent = `${action} OK`;
                statusEl.className = 'device-status success';
                ioTestStatus.boomBarrier = true;
                showToast('success', 'Test Passed', `Boom barrier ${action} working!`);
            } else {
                statusEl.textContent = 'Failed';
                statusEl.className = 'device-status error';
                resetDeviceStatus('boomBarrier', action);
                showToast('error', 'Test Failed', `Boom barrier ${action} not responding`);
            }
        });
        
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[Boom Barrier ${action}] Test error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with boom barrier');
    }
}

function resetDeviceStatus(deviceType, identifier) {
    // Reset test status for the device
    if (deviceType === 'sensor') {
        ioTestStatus[`sensor${identifier}`] = false;
        const id = Number(identifier);
        if (id === 1) ioTestStatus.sensor1Validated = false;
        else if (id === 2) ioTestStatus.sensor2Validated = false;
        else if (id === 3) ioTestStatus.sensor3Validated = false;
    } else if (deviceType === 'trafficLight') {
        ioTestStatus[`${identifier}TL`] = false;
        ioTestStatus[`${identifier}TLValidated`] = false;
    } else if (deviceType === 'boomBarrier') {
        if (identifier === 'entry' || identifier === 'exit') {
            ioTestStatus[`${identifier}BBValidated`] = false;
            ioTestStatus[`${identifier}BBDirect`] = false;
            ioTestStatus[`${identifier}BBRelay`] = false;
            ioTestStatus[`${identifier}BBDirectOpen`] = false;
            ioTestStatus[`${identifier}BBDirectClose`] = false;
            ioTestStatus[`${identifier}BBRelayOpen`] = false;
            ioTestStatus[`${identifier}BBRelayClose`] = false;
            ioTestStatus.boomBarrier =
                ioTestStatus.entryBBDirect || ioTestStatus.exitBBDirect ||
                ioTestStatus.entryBBRelay || ioTestStatus.exitBBRelay;
        } else {
            ioTestStatus.boomBarrier = false;
            ioTestStatus.entryBBValidated = false;
            ioTestStatus.exitBBValidated = false;
            ioTestStatus.entryBBDirect = false;
            ioTestStatus.exitBBDirect = false;
            ioTestStatus.entryBBRelay = false;
            ioTestStatus.exitBBRelay = false;
            ioTestStatus.entryBBDirectOpen = false;
            ioTestStatus.entryBBDirectClose = false;
            ioTestStatus.exitBBDirectOpen = false;
            ioTestStatus.exitBBDirectClose = false;
            ioTestStatus.entryBBRelayOpen = false;
            ioTestStatus.entryBBRelayClose = false;
            ioTestStatus.exitBBRelayOpen = false;
            ioTestStatus.exitBBRelayClose = false;
        }
    }
}

// ============== Relay Mode Test Functions ==============

async function testTrafficLightRelay(location, color) {
    // Test traffic light in relay mode using new API
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const pinField = document.getElementById(`${location}TLRelayPin`);
    const statusEl = document.getElementById(`${location}TLRelayStatus`);
    
    if (!pinField || !pinField.value) {
        showToast('error', 'Missing Pin', `Please enter relay pin for ${location} traffic light`);
        return;
    }
    
    statusEl.textContent = `Testing ${color}...`;
    statusEl.className = 'device-status testing';
    
    try {
        const response = await fetch('/api/io/test-traffic-light', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'relay',
                location: location,
                action: color,
                pins: { pin: parseInt(pinField.value) },
                slave_id: parseInt(slaveId)
            })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            // Show confirmation modal after successful write
            showHardwareTestModal('traffic_light', location, color, (confirmed, data) => {
                if (confirmed) {
                    statusEl.textContent = `${color.toUpperCase()} OK`;
                    statusEl.className = 'device-status success';
                    ioTestStatus[`${location}TL`] = true;
                    ioTestStatus[`${location}TLValidated`] = true;
                    showToast('success', 'Test Passed', `${location} traffic light ${color} working correctly!`);
                } else {
                    statusEl.textContent = 'Failed';
                    statusEl.className = 'device-status error';
                    resetDeviceStatus('trafficLight', location);
                    showToast('error', 'Test Failed', `${location} traffic light not responding correctly`);
                }
            });
        } else {
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Test Failed', result.message);
        }
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[Traffic Light ${location}] Relay test error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with traffic light');
    }
}

async function testBoomBarrierDirect(location, action) {
    // Test boom barrier in direct mode
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const openPinField = document.getElementById(`${location}BoomOpenPin`);
    const closePinField = document.getElementById(`${location}BoomClosePin`);
    const statusEl = document.getElementById(`${location}BBStatus`);
    boomLog('DIRECT_TEST_START', { location, action, outputMode: 'direct' });
    
    if (!openPinField || !openPinField.value) {
        showToast('error', 'Missing Pin', `Please enter open pin for ${location} boom barrier`);
        return;
    }
    
    if (!closePinField || !closePinField.value) {
        showToast('error', 'Missing Pin', `Please enter close pin for ${location} boom barrier`);
        return;
    }
    
    statusEl.textContent = `${action}ing...`;
    statusEl.className = 'device-status testing';
    
    try {
        const response = await fetch('/api/io/test-boom-barrier', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'direct',
                location: location,
                action: action,
                pins: { 
                    open_pin: parseInt(openPinField.value),
                    close_pin: parseInt(closePinField.value)
                },
                slave_id: parseInt(slaveId)
            })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            boomLog('DIRECT_COMMAND_OK', { location, action });
            // Show confirmation modal after successful write
            showHardwareTestModal('boom_barrier', location, action, (confirmed, data) => {
                if (confirmed) {
                    statusEl.textContent = `${action.toUpperCase()} OK`;
                    statusEl.className = 'device-status success';
                    ioTestStatus[`${location}BBDirect`] = true;
                    ioTestStatus[`${location}BBDirect${action === 'open' ? 'Open' : 'Close'}`] = true;
                    ioTestStatus.boomBarrier = ioTestStatus.entryBBDirect || ioTestStatus.exitBBDirect;
                    updateBoomBarrierValidatedFromTests(location, 'direct');
                    boomLog('DIRECT_TEST_CONFIRMED', {
                        location,
                        action,
                        entryBBDirect: ioTestStatus.entryBBDirect,
                        exitBBDirect: ioTestStatus.exitBBDirect
                    });
                    showToast('success', 'Test Passed', `${location} boom barrier ${action} working correctly!`);
                } else {
                    statusEl.textContent = 'Failed';
                    statusEl.className = 'device-status error';
                    resetDeviceStatus('boomBarrier', location);
                    boomLog('DIRECT_TEST_REJECTED', { location, action });
                    showToast('error', 'Test Failed', `${location} boom barrier not responding correctly`);
                }
            });
        } else {
            boomLog('DIRECT_COMMAND_FAILED', { location, action, message: result.message });
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Test Failed', result.message);
        }
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[Boom Barrier ${location}] Direct test error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with boom barrier');
    }
}

async function testBoomBarrierRelay(location, action) {
    // Test boom barrier in relay mode using new API
    if (!ioConnected) {
        showToast('error', 'Not Connected', 'Please connect to I/O controller first');
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const pinField = document.getElementById(`${location}BoomRelayPin`);
    const statusEl = document.getElementById(`${location}BBRelayStatus`);
    boomLog('RELAY_TEST_START', { location, action, outputMode: 'relay' });
    
    if (!pinField || !pinField.value) {
        showToast('error', 'Missing Pin', `Please enter relay pin for ${location} boom barrier`);
        return;
    }
    
    statusEl.textContent = `${action}ing...`;
    statusEl.className = 'device-status testing';
    
    try {
        const response = await fetch('/api/io/test-boom-barrier', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'relay',
                location: location,
                action: action,
                pins: { pin: parseInt(pinField.value) },
                slave_id: parseInt(slaveId)
            })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            boomLog('RELAY_COMMAND_OK', { location, action });
            // Show confirmation modal after successful write
            showHardwareTestModal('boom_barrier', location, action, (confirmed, data) => {
                if (confirmed) {
                    statusEl.textContent = `${action.toUpperCase()} OK`;
                    statusEl.className = 'device-status success';
                    ioTestStatus[`${location}BBRelay`] = true;
                    ioTestStatus[`${location}BBRelay${action === 'open' ? 'Open' : 'Close'}`] = true;
                    ioTestStatus.boomBarrier = ioTestStatus.entryBBRelay || ioTestStatus.exitBBRelay;
                    updateBoomBarrierValidatedFromTests(location, 'relay');
                    boomLog('RELAY_TEST_CONFIRMED', {
                        location,
                        action,
                        entryBBRelay: ioTestStatus.entryBBRelay,
                        exitBBRelay: ioTestStatus.exitBBRelay
                    });
                    showToast('success', 'Test Passed', `${location} boom barrier ${action} working correctly!`);
                } else {
                    statusEl.textContent = 'Failed';
                    statusEl.className = 'device-status error';
                    resetDeviceStatus('boomBarrier', location);
                    boomLog('RELAY_TEST_REJECTED', { location, action });
                    showToast('error', 'Test Failed', `${location} boom barrier not responding correctly`);
                }
            });
        } else {
            boomLog('RELAY_COMMAND_FAILED', { location, action, message: result.message });
            statusEl.textContent = 'Error';
            statusEl.className = 'device-status error';
            showToast('error', 'Test Failed', result.message);
        }
    } catch (error) {
        statusEl.textContent = 'Error';
        statusEl.className = 'device-status error';
        console.error(`[Boom Barrier ${location}] Relay test error:`, error);
        showToast('error', 'Test Error', 'Unable to communicate with boom barrier');
    }
}

function isBoomBarrierValidationRequired(outputMode) {
    if (outputMode === 'direct') {
        const entryEnabled = document.getElementById('entryBoomEnabled')?.checked || false;
        const exitEnabled = document.getElementById('exitBoomEnabled')?.checked || false;
        return entryEnabled || exitEnabled;
    }
    const entryEnabled = document.getElementById('entryBoomRelayEnabled')?.checked || false;
    const exitEnabled = document.getElementById('exitBoomRelayEnabled')?.checked || false;
    return entryEnabled || exitEnabled;
}

function hasRequiredBoomBarrierTestsPassed(outputMode) {
    const passed = isBoomBarrierIoTestSatisfied('entry', outputMode)
        && isBoomBarrierIoTestSatisfied('exit', outputMode);
    boomLog('VALIDATION_CHECK', {
        outputMode,
        entryBBValidated: ioTestStatus.entryBBValidated,
        exitBBValidated: ioTestStatus.exitBBValidated,
        passed
    });
    return passed;
}

function normalizeIoPin(pin) {
    if (pin === null || pin === undefined) return null;
    const text = String(pin).trim();
    if (!text) return null;
    const n = Number.parseInt(text, 10);
    if (Number.isNaN(n)) return null;
    return String(n);
}

function addIoPinEntry(entries, pin, label) {
    const normalized = normalizeIoPin(pin);
    if (normalized !== null) entries.push([normalized, label]);
}

function deviceUsesIoPin(validated) {
    return validated === true;
}

function sensorPinForSave(sensorNum) {
    if (!deviceUsesIoPin(getSensorValidatedForSave(sensorNum))) return '';
    const fallbacks = { 1: '0', 2: '1', 3: '2' };
    return document.getElementById(`sensor${sensorNum}Pin`)?.value ?? fallbacks[sensorNum] ?? '';
}

function uniTrafficLightDirectPinsForSave(location) {
    if (!deviceUsesIoPin(getTrafficLightValidatedForSave(location))) {
        return { red_pin: '', green_pin: '' };
    }
    const defs = location === 'entry' ? ['0', '1'] : ['2', '3'];
    return {
        red_pin: document.getElementById(`${location}RedPin`)?.value || defs[0],
        green_pin: document.getElementById(`${location}GreenPin`)?.value || defs[1]
    };
}

function uniTrafficLightRelayPinForSave(location) {
    const desc = location === 'entry'
        ? 'Relay 1: NO=Green, NC=Red'
        : 'Relay 2: NO=Green, NC=Red';
    if (!deviceUsesIoPin(getTrafficLightValidatedForSave(location))) {
        return { pin: '', description: desc };
    }
    const def = location === 'entry' ? '0' : '1';
    return {
        pin: document.getElementById(`${location}TLRelayPin`)?.value || def,
        description: desc
    };
}

function boomDirectConfigForSave(location) {
    const enabled = document.getElementById(`${location}BoomEnabled`)?.checked || false;
    if (!enabled) {
        return { open_pin: '', close_pin: null, enabled: false };
    }
    return {
        open_pin: document.getElementById(`${location}BoomOpenPin`)?.value || '',
        close_pin: document.getElementById(`${location}BoomClosePin`)?.value || null,
        enabled: true
    };
}

function boomRelayConfigForSave(location) {
    const enabled = document.getElementById(`${location}BoomRelayEnabled`)?.checked || false;
    const desc = location === 'entry'
        ? 'Relay 3: NO=Open, NC=Close'
        : 'Relay 4: NO=Open, NC=Close';
    if (!enabled) {
        return { pin: '', enabled: false, description: desc };
    }
    return {
        pin: document.getElementById(`${location}BoomRelayPin`)?.value || '',
        enabled: true,
        description: desc
    };
}

function tlSideUsesPins(tl, location, directionKey) {
    if (!tl || typeof tl !== 'object') return false;
    if (directionKey) {
        const side = tl[directionKey]?.[location];
        return side && deviceUsesIoPin(side.validated);
    }
    const side = tl[location];
    return side && deviceUsesIoPin(side.validated);
}

function boomLocationUsesPins(locData) {
    return locData && locData.enabled === true;
}

function collectIoInputPinsFromConfigData(io) {
    const entries = [];
    if (!io || typeof io !== 'object') return entries;
    const sensors = io.sensors || {};
    [
        ['entry_sensor', 'Entry sensor'],
        ['wb_sensor', 'WB sensor'],
        ['exit_sensor', 'Exit sensor']
    ].forEach(([key, label]) => {
        const sensor = sensors[key];
        if (sensor && typeof sensor === 'object' && deviceUsesIoPin(sensor.validated)) {
            addIoPinEntry(entries, sensor.pin, label);
        }
    });
    return entries;
}

function collectIoOutputPinsFromConfigData(io, wbType) {
    const entries = [];
    if (!io || typeof io !== 'object') return entries;
    const layout = wbType === 'bidirectional' ? 'bidirectional' : 'unidirectional';

    let outputMode = io.output_mode;
    const tl = io.traffic_lights || {};
    const bb = io.boom_barriers || {};
    if (!outputMode) outputMode = tl.mode || bb.mode || 'direct';
    if (outputMode !== 'direct' && outputMode !== 'relay') outputMode = 'direct';

    if (outputMode === 'direct') {
        const directTl = tl.direct || {};
        if (layout === 'bidirectional') {
            ['entry_a', 'entry_b'].forEach((dir) => {
                const dirLabel = dir === 'entry_a' ? 'ENTRY A' : 'ENTRY B';
                const dirData = directTl[dir] || {};
                ['entry', 'exit'].forEach((loc) => {
                    if (!tlSideUsesPins(tl, loc, dir)) return;
                    const locData = dirData[loc] || {};
                    const locLabel = loc.charAt(0).toUpperCase() + loc.slice(1);
                    addIoPinEntry(entries, locData.red_pin, `${dirLabel} ${locLabel} red`);
                    addIoPinEntry(entries, locData.green_pin, `${dirLabel} ${locLabel} green`);
                });
            });
        } else {
            ['entry', 'exit'].forEach((loc) => {
                if (!tlSideUsesPins(tl, loc)) return;
                const locData = directTl[loc] || {};
                const locLabel = loc.charAt(0).toUpperCase() + loc.slice(1);
                addIoPinEntry(entries, locData.red_pin, `${locLabel} traffic light red`);
                addIoPinEntry(entries, locData.green_pin, `${locLabel} traffic light green`);
            });
        }
        const directBb = bb.direct || {};
        ['entry', 'exit'].forEach((loc) => {
            const locData = directBb[loc] || {};
            if (!boomLocationUsesPins(locData)) return;
            const locLabel = loc.charAt(0).toUpperCase() + loc.slice(1);
            addIoPinEntry(entries, locData.open_pin, `${locLabel} boom open`);
            addIoPinEntry(entries, locData.close_pin, `${locLabel} boom close`);
        });
    } else {
        const relayTl = tl.relay || {};
        ['entry', 'exit'].forEach((loc) => {
            if (!tlSideUsesPins(tl, loc)) return;
            const locData = relayTl[loc] || {};
            const locLabel = loc.charAt(0).toUpperCase() + loc.slice(1);
            addIoPinEntry(entries, locData.pin, `${locLabel} traffic light relay`);
        });
        const relayBb = bb.relay || {};
        ['entry', 'exit'].forEach((loc) => {
            const locData = relayBb[loc] || {};
            if (!boomLocationUsesPins(locData)) return;
            const locLabel = loc.charAt(0).toUpperCase() + loc.slice(1);
            addIoPinEntry(entries, locData.pin, `${locLabel} boom relay`);
        });
    }
    return entries;
}

function findDuplicatePinGroups(entries) {
    const byPin = {};
    entries.forEach(([pin, label]) => {
        if (!byPin[pin]) byPin[pin] = [];
        byPin[pin].push(label);
    });
    return Object.keys(byPin).filter((pin) => byPin[pin].length > 1).sort((a, b) => Number(a) - Number(b)).map((pin) => ({
        pin,
        labels: byPin[pin]
    }));
}

function formatPinDuplicateMessage(duplicates, registerLabel) {
    if (!duplicates.length) return null;
    const parts = duplicates.map((d) => `pin ${d.pin} (${d.labels.join(', ')})`);
    if (parts.length === 1) {
        return `Duplicate ${registerLabel} pin used by: ${parts[0]}.`;
    }
    return `Duplicate ${registerLabel} pins: ${parts.join('; ')}.`;
}

function validateIoPinUniqueness(configData) {
    const wbType = (configData?.wb_type === 'bidirectional')
        ? 'bidirectional'
        : ((typeof getWeighbridgeLayout === 'function' && getWeighbridgeLayout()) || 'unidirectional');
    const inputDups = findDuplicatePinGroups(collectIoInputPinsFromConfigData(configData));
    const outputDups = findDuplicatePinGroups(collectIoOutputPinsFromConfigData(configData, wbType));
    const messages = [
        formatPinDuplicateMessage(inputDups, 'input'),
        formatPinDuplicateMessage(outputDups, 'output')
    ].filter(Boolean);
    if (!messages.length) return { ok: true };
    return { ok: false, message: messages.join(' ') };
}

function isIoInputPinFieldActive(el) {
    const id = el?.id || '';
    if (id === 'sensor1Pin') return ioTestStatus.sensor1Validated === true;
    if (id === 'sensor2Pin') return ioTestStatus.sensor2Validated === true;
    if (id === 'sensor3Pin') return ioTestStatus.sensor3Validated === true;
    return false;
}

function isIoOutputPinFieldActive(el) {
    const id = el?.id || '';
    const outputMode = document.getElementById('outputMode')?.value || 'direct';
    if (id.includes('Boom')) {
        const loc = id.toLowerCase().includes('entry') ? 'entry' : 'exit';
        return isBoomBarrierEnabled(loc, outputMode);
    }
    if (id.includes('TLRelay')) {
        const loc = id.toLowerCase().includes('entry') ? 'entry' : 'exit';
        return getTrafficLightValidatedForSave(loc) === true;
    }
    if (id.includes('RedPin') || id.includes('GreenPin')) {
        const bi = typeof isBidirectionalLayout === 'function' && isBidirectionalLayout();
        if (bi) {
            let dir = null;
            let loc = null;
            if (id.startsWith('directionA_')) {
                dir = 'entry_a';
                loc = id.includes('entry') ? 'entry' : 'exit';
            } else if (id.startsWith('directionB_')) {
                dir = 'entry_b';
                loc = id.includes('entry') ? 'entry' : 'exit';
            }
            if (dir && loc) {
                const key = getTlValidatedStateKey(dir, loc);
                return ioTestStatus[key] === true;
            }
        }
        const loc = id.toLowerCase().includes('entry') ? 'entry' : 'exit';
        return getTrafficLightValidatedForSave(loc) === true;
    }
    return false;
}

function setupIoPinUniquenessHints() {
    const bindGroup = (selector, isActiveFn) => {
        document.querySelectorAll(selector).forEach((el) => {
            if (el.dataset.ioPinHintBound === '1') return;
            el.dataset.ioPinHintBound = '1';
            el.addEventListener('input', () => {
                const form = el.closest('#io-controller') || document;
                form.querySelectorAll(`${selector}.io-pin-duplicate`).forEach((input) => {
                    input.classList.remove('io-pin-duplicate');
                });
                const pins = [];
                form.querySelectorAll(selector).forEach((input) => {
                    if (!isActiveFn(input)) return;
                    const p = normalizeIoPin(input.value);
                    if (p !== null) pins.push(p);
                });
                const counts = {};
                pins.forEach((p) => { counts[p] = (counts[p] || 0) + 1; });
                form.querySelectorAll(selector).forEach((input) => {
                    if (!isActiveFn(input)) {
                        input.classList.remove('io-pin-duplicate');
                        return;
                    }
                    const dup = normalizeIoPin(input.value);
                    if (dup !== null && counts[dup] > 1) {
                        input.classList.add('io-pin-duplicate');
                    }
                });
            });
        });
    };
    bindGroup('.io-pin-input-input', isIoInputPinFieldActive);
    bindGroup('.io-pin-input-output', isIoOutputPinFieldActive);
}

function setupIoPinInputOutputClasses() {
    const inputIds = ['sensor1Pin', 'sensor2Pin', 'sensor3Pin'];
    inputIds.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.add('io-pin-input-input');
            el.classList.remove('io-pin-input-output');
        }
    });
    document.querySelectorAll('.io-pin-input').forEach((el) => {
        if (el.classList.contains('io-pin-input-input')) return;
        el.classList.add('io-pin-input-output');
    });
}

async function saveIOConfig() {
    const ioType = document.getElementById('ioType').value;
    const slaveId = document.getElementById('ioSlaveId').value;
    const outputMode = document.getElementById('outputMode').value;
    const ioMake = document.getElementById('ioMake')?.value.trim() || '';
    const ioModel = document.getElementById('ioModel')?.value.trim() || '';
    
    // Validate I/O controller device info in production mode
    if (!validateDeviceInfo(ioMake, ioModel, 'I/O Controller')) {
        return;
    }

    // Ensure all I/O devices have passed their tests before saving configuration
    const boomBarrierPassed = hasRequiredBoomBarrierTestsPassed(outputMode);
    boomLog('SAVE_IO_VALIDATION', {
        outputMode,
        sensor1: ioTestStatus.sensor1,
        sensor2: ioTestStatus.sensor2,
        sensor3: ioTestStatus.sensor3,
        entryTL: ioTestStatus.entryTL,
        exitTL: ioTestStatus.exitTL,
        boomBarrierPassed
    });
    const ioFailures = getIoSaveValidationFailures(outputMode);
    if (ioFailures.length > 0) {
        const ioSaveMsg = `Please run and pass all required I/O tests before saving configuration. Still needed: ${ioFailures.join(', ')}.`;
        showToast('error', 'Validation Error', ioSaveMsg);
        markSectionNotValidated('io-controller');
        return;
    }
    
    // Sync "same as first" values before saving
    syncSameAsFirstValues();
    
    // Build configuration matching weighbridge_app format
    let configData = {
        type: ioType,
        output_mode: outputMode,
        connection: {
            ethernet: {
                ip: "",
                port: "502",
                timeout: "1"
            },
            serial: {
                port: "",
                baud_rate: "9600",
                bytesize: "8",
                parity: "N",
                stopbits: "1",
                timeout: "0.5"
            }
        },
        slave_id: slaveId,
        polling: {
            scan_interval: "0.3",
            delay: "0.3"
        },
        function_codes: {
            read_coils: "1",
            read_discrete_inputs: "2",
            read_holding_registers: "3",
            read_input_registers: "4",
            write_single_coil: "5",
            write_single_register: "6",
            write_multiple_coils: "15",
            write_multiple_registers: "16"
        },
        digital_inputs: {
            start_address: document.getElementById('inputStartAddress')?.value || "0",
            count: "8",
            function_code: (() => {
                // Map register type to function code: "coil" = "1", "discrete" = "2"
                const registerType = document.getElementById('inputRegisterType')?.value || "discrete";
                return registerType === "coil" ? "1" : "2";
            })(),
            mapping: {}
        },
        digital_outputs: {
            start_address: document.getElementById('outputStartAddress')?.value || "0",
            count: "8",
            function_code: (() => {
                // Map register type to function code: "coil" = "5", "holding" = "6"
                const registerType = document.getElementById('outputRegisterType')?.value || "coil";
                return registerType === "coil" ? "5" : "6";
            })(),
            mode_description: {
                direct: "Each light/barrier has separate pins (red_pin, green_pin, open_pin, close_pin)",
                relay: "Single pin per device controls a relay with NO/NC contacts"
            },
            mapping: {}
        },
        sensors: {
            entry_sensor: {
                pin: sensorPinForSave(1),
                default_signal: document.getElementById('sensor1DefaultSignal')?.value || "low",
                validated: getSensorValidatedForSave(1)
            },
            wb_sensor: {
                pin: sensorPinForSave(2),
                default_signal: document.getElementById('sensor2DefaultSignal')?.value || "low",
                validated: getSensor2ValidatedForSave()
            },
            exit_sensor: {
                pin: sensorPinForSave(3),
                default_signal: document.getElementById('sensor3DefaultSignal')?.value || "low",
                validated: getSensorValidatedForSave(3)
            }
        },
        traffic_lights: {
            mode: outputMode,
            relay_logic: {
                description: "Relay ON (coil=HIGH) = NO contact = RED, Relay OFF (coil=LOW) = NC contact = GREEN",
                on_state: "red",
                off_state: "green"
            },
            direct: {
                entry: { red_pin: "", green_pin: "" },
                exit: { red_pin: "", green_pin: "" }
            },
            relay: {
                entry: { pin: "", description: "Relay 1: NO=Red, NC=Green" },
                exit: { pin: "", description: "Relay 2: NO=Red, NC=Green" }
            }
        },
        boom_barriers: {
            mode: outputMode,
            relay_logic: {
                description: "Relay ON (coil=HIGH) = NO contact = OPEN, Relay OFF (coil=LOW) = NC contact = CLOSE",
                on_state: "open",
                off_state: "close"
            },
            direct: {
                entry: { open_pin: "", close_pin: null, enabled: false },
                exit: { open_pin: "", close_pin: null, enabled: false }
            },
            relay: {
                entry: { pin: "", enabled: false, description: "Relay 3: NO=Open, NC=Close" },
                exit: { pin: "", enabled: false, description: "Relay 4: NO=Open, NC=Close" }
            }
        },
        make: ioMake,
        model: ioModel,
        validated: true
    };
    
    // Add connection info based on type
    if (ioType === 'ethernet') {
        const isManual = document.getElementById('ioIpManual')?.checked;
        const ip = isManual 
            ? document.getElementById('ioIp').value.trim()
            : (document.getElementById('ioIpSelect')?.value || document.getElementById('ioIp').value.trim());
        configData.connection.ethernet.ip = ip;
        configData.connection.ethernet.port = document.getElementById('ioPort').value.trim() || "502";
    } else {
        configData.connection.serial.port = document.getElementById('ioSerialPort').value;
        configData.connection.serial.baud_rate = document.getElementById('ioBaudRate').value || "9600";
    }
    
    // Add traffic light and boom barrier config based on output mode
    const biLayout = (config?.wb_type === 'bidirectional')
        || (typeof isBidirectionalLayout === 'function' && isBidirectionalLayout());
    if (outputMode === 'direct') {
        if (!biLayout) {
            configData.traffic_lights.direct.entry = uniTrafficLightDirectPinsForSave('entry');
            configData.traffic_lights.direct.exit = uniTrafficLightDirectPinsForSave('exit');
        }
        configData.boom_barriers.direct.entry = boomDirectConfigForSave('entry');
        configData.boom_barriers.direct.exit = boomDirectConfigForSave('exit');
    } else {
        if (!biLayout) {
            configData.traffic_lights.relay.entry = uniTrafficLightRelayPinForSave('entry');
            configData.traffic_lights.relay.exit = uniTrafficLightRelayPinForSave('exit');
        }
        configData.boom_barriers.relay.entry = boomRelayConfigForSave('entry');
        configData.boom_barriers.relay.exit = boomRelayConfigForSave('exit');
    }

    // If boom barrier enable controls are disabled in UI, force all enabled flags to false.
    const boomEnableControls = [
        document.getElementById('entryBoomEnabled'),
        document.getElementById('exitBoomEnabled'),
        document.getElementById('entryBoomRelayEnabled'),
        document.getElementById('exitBoomRelayEnabled')
    ].filter(Boolean);
    const boomControlsDisabled = boomEnableControls.length > 0 && boomEnableControls.every(el => el.disabled);
    if (boomControlsDisabled) {
        configData.boom_barriers.direct.entry.enabled = false;
        configData.boom_barriers.direct.exit.enabled = false;
        configData.boom_barriers.relay.entry.enabled = false;
        configData.boom_barriers.relay.exit.enabled = false;
    }
    
    // Add make/model for traffic lights and boom barriers
    if (biLayout && typeof buildBidirectionalTrafficLightsForSave === 'function') {
        buildBidirectionalTrafficLightsForSave(outputMode, configData);
    } else {
        configData.traffic_lights.entry = {
            make: document.getElementById('entryTLMake')?.value.trim() || '',
            model: document.getElementById('entryTLModel')?.value.trim() || '',
            validated: getTrafficLightValidatedForSave('entry')
        };
        configData.traffic_lights.exit = {
            make: document.getElementById('exitTLMake')?.value.trim() || '',
            model: document.getElementById('exitTLModel')?.value.trim() || '',
            validated: getTrafficLightValidatedForSave('exit')
        };
    }
    configData.boom_barriers.entry = {
        make: document.getElementById('entryBBMake')?.value.trim() || document.getElementById('boomBarrierMake')?.value.trim() || '',
        model: document.getElementById('entryBBModel')?.value.trim() || document.getElementById('boomBarrierModel')?.value.trim() || '',
        validated: getBoomBarrierValidatedForSave('entry', outputMode)
    };
    configData.boom_barriers.exit = {
        make: document.getElementById('exitBBMake')?.value.trim() || document.getElementById('boomBarrierMake')?.value.trim() || '',
        model: document.getElementById('exitBBModel')?.value.trim() || document.getElementById('boomBarrierModel')?.value.trim() || '',
        validated: getBoomBarrierValidatedForSave('exit', outputMode)
    };

    const pinCheck = validateIoPinUniqueness(configData);
    if (!pinCheck.ok) {
        showToast('error', 'Duplicate I/O pin', pinCheck.message);
        markSectionNotValidated('io-controller');
        return;
    }
    
    try {
        await fetch('/api/config/io_controller', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(configData)
        });
        
        // After a successful save, reset dirty flag and resnapshot config
        try {
            originalIoConfig = JSON.parse(JSON.stringify(configData));
            ioConfigDirty = false;
        } catch (e) {
            ioConfigDirty = false;
        }

        showToast('success', 'Saved', 'I/O Controller configuration saved');
        markSectionValidated('io_controller');
        
        // Update assigned device based on connection type
        if (ioType === 'ethernet') {
            updateAssignedDevice('ioController', configData.connection.ethernet.ip, true);
            assignedDevices.comPorts.ioController = null;
        } else {
            updateAssignedDevice('ioController', configData.connection.serial.port, false);
            assignedDevices.ips.ioController = null;
        }
        
        navigateToNext('io-controller');
    } catch (error) {
        console.error('[I/O Config] Save error:', error);
        showToast('error', 'Save Error', 'Unable to save I/O controller configuration');
    }
}

// ============== Digitizer Configuration ==============
async function refreshSerialPorts() {
    try {
        // Use discovered COM ports if available, otherwise fetch from API
        if (discoveredDevices.comPorts.length > 0) {
            populateComPortDropdowns();
            
            // Select saved port if exists
            if (config.digitizer?.port) {
                document.getElementById('digitizerPort').value = config.digitizer.port;
            }
            return;
        }
        
        const response = await fetch('/api/digitizer/ports');
        const data = await response.json();
        
        discoveredDevices.comPorts = data.ports;
        populateComPortDropdowns();
        
        // Select saved port if exists
        if (config.digitizer?.port) {
            document.getElementById('digitizerPort').value = config.digitizer.port;
        }
    } catch (error) {
        console.error('Failed to load serial ports:', error);
    }
}

async function checkAndSaveDigitizer() {
    // GMDC: digitizer-app HTTP API (host/port + /read_stable_weight)
    const host = document.getElementById('digitizerHost')?.value?.trim() || '';
    const port = document.getElementById('digitizerApiPort')?.value?.trim() || '8100';
    const path = document.getElementById('digitizerPath')?.value?.trim() || '/read_stable_weight';
    const timeout = document.getElementById('digitizerTimeout')?.value?.trim() || '30';
    const stableCount = document.getElementById('digitizerStableCount')?.value?.trim() || '10';
    const make = document.getElementById('digitizerMake')?.value || '';
    const model = document.getElementById('digitizerModel')?.value || '';

    if (!host) {
        showToast('error', 'Digitizer', 'Host / IP is required');
        return;
    }

    showLoading(true);
    try {
        const response = await fetch('/api/digitizer/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'api', host, port, path, timeout }),
        });
        const result = await response.json();
        showLoading(false);

        const consoleEl = document.getElementById('digitizerConsole');
        const outputEl = document.getElementById('digitizerOutput');
        if (consoleEl) consoleEl.style.display = 'block';
        if (outputEl) {
            // Digitizer Data: show weight in KG only (not full API JSON).
            const weight = result.weight;
            if (weight !== null && weight !== undefined && weight !== '' && !Number.isNaN(Number(weight))) {
                outputEl.textContent = `${Number(weight)} KG`;
            } else if (result.status === 200) {
                outputEl.textContent = 'Weight not available';
            } else {
                outputEl.textContent = result.message || 'Digitizer check failed';
            }
        }

        if (result.status !== 200) {
            showToast('error', 'Digitizer', result.message || 'API check failed');
            return;
        }

        const payload = {
            mode: 'api', host, port, path, timeout,
            stable_count: stableCount, make, model, validated: true,
        };
        const saveResp = await fetch('/api/config/digitizer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const saveData = await saveResp.json();
        if (!saveResp.ok || saveData.status !== 200) {
            throw new Error(saveData.message || 'Failed to save digitizer configuration');
        }

        showToast('success', 'Success', result.message || 'Digitizer-app saved');
        markSectionValidated('digitizer');
        if (typeof updateAssignedDevice === 'function') {
            updateAssignedDevice('digitizer', host + ':' + port, false);
        }
        navigateToNext('digitizer');
    } catch (err) {
        showLoading(false);
        console.error('[Digitizer API] Error:', err);
        showToast('error', 'Digitizer', err.message || 'Check failed');
    }
}

async function checkAndSaveHandheldRfid() {
    const enabled = document.getElementById('handheldEnabled')?.checked !== false;
    const make = document.getElementById('handheldMake')?.value?.trim() || '';
    const model = document.getElementById('handheldModel')?.value?.trim() || '';
    const deviceId = document.getElementById('handheldDeviceId')?.value?.trim() || '';
    const ip = document.getElementById('handheldIp')?.value?.trim() || '';
    const port = document.getElementById('handheldPort')?.value?.trim() || '';

    showLoading(true);
    try {
        const response = await fetch('/api/handheld-rfid/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled, make, model, device_id: deviceId, ip, port, wait_seconds: 60,
            }),
        });
        const result = await response.json();
        showLoading(false);

        if (result.status !== 200) {
            showToast('error', 'Handheld RFID', result.message || 'Check failed');
            return;
        }

        // Disabled = skip without live tag
        if (result.skipped) {
            await fetch('/api/config/handheld_rfid', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: false, make, model, device_id: deviceId, ip, port, validated: null,
                }),
            });
            showToast('success', 'Handheld RFID', result.message);
            markSectionSkipped('handheld_rfid');
            navigateToNext('handheld-rfid');
            return;
        }

        // Live wait for {"rfid_data": "<non-blank>"}
        if (result.testing === true || result.test_complete === false) {
            openHandheldRfidWaitModal(result.time_remaining || 60);
            await pollHandheldRfidWait({ enabled, make, model, deviceId, ip, port });
            return;
        }

        showToast('error', 'Handheld RFID', 'Unexpected response from handheld check');
    } catch (err) {
        showLoading(false);
        closeHandheldRfidWaitModal();
        showToast('error', 'Handheld RFID', err.message || 'Check failed');
    }
}

let _handheldPollInterval = null;
let _handheldPollTimeout = null;
let _handheldPendingMeta = null;
let _handheldPendingTag = null;

function updateHandheldModalActions(showSave, showRetry, showCancel = true) {
    const saveBtn = document.getElementById('handheldModalSaveBtn');
    const retryBtn = document.getElementById('handheldModalRetryBtn');
    const cancelBtn = document.getElementById('handheldModalCancelBtn');
    if (saveBtn) saveBtn.style.display = showSave ? 'inline-block' : 'none';
    if (retryBtn) retryBtn.style.display = showRetry ? 'inline-block' : 'none';
    if (cancelBtn) cancelBtn.style.display = showCancel ? 'inline-block' : 'none';
}

function setHandheldModalStatus(kind, message) {
    const statusEl = document.getElementById('handheldModalStatus');
    if (!statusEl) return;
    let icon = 'bi-info-circle';
    let color = 'var(--primary-color)';
    if (kind === 'success') {
        icon = 'bi-check-circle-fill';
        color = 'var(--success-color, #28a745)';
    } else if (kind === 'failed' || kind === 'error') {
        icon = 'bi-x-circle-fill';
        color = 'var(--error-color, #dc3545)';
    } else if (kind === 'warning') {
        icon = 'bi-exclamation-triangle-fill';
        color = 'var(--warning-color, #ffc107)';
    }
    statusEl.innerHTML = `<i class="bi ${icon}" style="color: ${color};"></i> <span>${message}</span>`;
    statusEl.style.color = color;
}

function showHandheldModalReceivedData(tag) {
    const dataBox = document.getElementById('handheldModalDataBox');
    const dataValue = document.getElementById('handheldModalDataValue');
    if (dataValue) dataValue.textContent = tag || '';
    if (dataBox) dataBox.style.display = tag ? 'block' : 'none';
}

function openHandheldRfidWaitModal(seconds) {
    const modal = document.getElementById('handheldRfidWaitModal');
    const countdown = document.getElementById('handheldModalCountdown');
    const urlEl = document.getElementById('handheldReceiveUrl');
    if (countdown) {
        countdown.textContent = String(seconds || 60);
    }
    const countdownWrap = document.getElementById('handheldModalCountdownWrap');
    if (countdownWrap) countdownWrap.style.display = 'block';
    if (urlEl) {
        const host = window.location.hostname || '127.0.0.1';
        const cfgPort = window.location.port || String(window.APP_CONFIG?.configPort || 8080);
        urlEl.textContent = `http://${host}:${cfgPort}/rfid_data_from_mobile_app`;
    }
    _handheldPendingTag = null;
    showHandheldModalReceivedData('');
    const hhStatus = document.getElementById('handheldModalStatus');
    if (hhStatus) hhStatus.style.display = '';
    setHandheldModalStatus('info', 'Waiting for Non-blank TAG Data...');
    updateHandheldModalActions(false, false, true);
    if (modal) modal.classList.add('active');
}

function closeHandheldRfidWaitModal() {
    const modal = document.getElementById('handheldRfidWaitModal');
    if (modal) modal.classList.remove('active');
    if (_handheldPollInterval) {
        clearInterval(_handheldPollInterval);
        _handheldPollInterval = null;
    }
    if (_handheldPollTimeout) {
        clearTimeout(_handheldPollTimeout);
        _handheldPollTimeout = null;
    }
    _handheldPendingMeta = null;
    _handheldPendingTag = null;
}

async function cancelHandheldRfidWait() {
    try {
        await fetch('/api/handheld-rfid/stop', { method: 'POST' });
    } catch (e) {
        console.warn('[Handheld] stop failed', e);
    }
    closeHandheldRfidWaitModal();
    showLoading(false);
    showToast('warning', 'Handheld RFID', 'Wait cancelled - no tick until a valid rfid_data is received');
}

async function saveHandheldRfidWait() {
    const meta = _handheldPendingMeta;
    const tag = _handheldPendingTag;
    if (!meta || !tag) {
        showToast('warning', 'Handheld RFID', 'No RFID data to save. Scan a tag or retry.');
        return;
    }
    try {
        await fetch('/api/config/handheld_rfid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                enabled: meta.enabled,
                make: meta.make,
                model: meta.model,
                device_id: meta.deviceId,
                ip: meta.ip,
                port: meta.port,
                validated: true,
                last_rfid_data: tag,
            }),
        });
        closeHandheldRfidWaitModal();
        showToast('success', 'Handheld RFID', 'RFID tag data received');
        markSectionValidated('handheld_rfid');
        navigateToNext('handheld-rfid');
    } catch (err) {
        console.error('[Handheld] save failed', err);
        showToast('error', 'Handheld RFID', 'Failed to save handheld RFID configuration');
    }
}

async function retryHandheldRfidWait() {
    try {
        await fetch('/api/handheld-rfid/stop', { method: 'POST' });
    } catch (e) {
        console.warn('[Handheld] stop failed', e);
    }
    closeHandheldRfidWaitModal();
    await checkAndSaveHandheldRfid();
}

async function pollHandheldRfidWait(meta) {
    _handheldPendingMeta = meta;
    _handheldPendingTag = null;
    return new Promise((resolve) => {
        _handheldPollInterval = setInterval(async () => {
            try {
                const resp = await fetch('/api/handheld-rfid/status');
                const st = await resp.json();
                const countdown = document.getElementById('handheldModalCountdown');
                if (countdown && typeof st.time_remaining === 'number') {
                    countdown.textContent = String(st.time_remaining);
                }

                // Show tag live when received (before test_complete if applicable)
                if (st.rfid_received && st.rfid_data) {
                    showHandheldModalReceivedData(st.rfid_data);
                }

                if (!st.test_complete) return;

                clearInterval(_handheldPollInterval);
                _handheldPollInterval = null;
                if (_handheldPollTimeout) {
                    clearTimeout(_handheldPollTimeout);
                    _handheldPollTimeout = null;
                }

                if (countdown) {
                    const wrap = document.getElementById('handheldModalCountdownWrap');
                    if (wrap) wrap.style.display = 'none';
                }

                if (st.rfid_received && st.rfid_data) {
                    _handheldPendingTag = st.rfid_data;
                    showHandheldModalReceivedData(st.rfid_data);
                    setHandheldModalStatus('success', '');
                    const hhStatus = document.getElementById('handheldModalStatus');
                    if (hhStatus) hhStatus.style.display = 'none';
                    // Keep modal open - Save / Retry / Cancel
                    updateHandheldModalActions(true, true, true);
                    showToast('success', 'Handheld RFID', 'RFID tag data received');
                    showLoading(false);
                    resolve(true);
                    return;
                }

                setHandheldModalStatus('failed', st.message || 'No RFID data received. Please try again.');
                updateHandheldModalActions(false, true, true);
                showLoading(false);
                resolve(false);
            } catch (err) {
                console.error('[Handheld] poll error', err);
            }
        }, 500);

        _handheldPollTimeout = setTimeout(() => {
            if (_handheldPollInterval) {
                clearInterval(_handheldPollInterval);
                _handheldPollInterval = null;
            }
            const wrap = document.getElementById('handheldModalCountdownWrap');
            if (wrap) wrap.style.display = 'none';
            setHandheldModalStatus('failed', 'No RFID data received. Please try again.');
            updateHandheldModalActions(false, true, true);
            showLoading(false);
            showToast('warning', 'Handheld RFID', 'Timed out waiting for RFID data');
            resolve(false);
        }, 70000);
    });
}

(function applyProfileVisibility() {
    const profile = window.APP_CONFIG && window.APP_CONFIG.profile;
    if (!profile) return;
    if (!profile.has_digitizer) {
        const nav = document.getElementById('navDigitizer');
        const sec = document.getElementById('digitizer');
        if (nav) nav.style.display = 'none';
        if (sec) sec.style.display = 'none';
    }
    // Checkpoint family: 1 sensor, 1 TL, 1 BB - hide WB/exit hardware cards
    if (profile.family === 'checkpoint') {
        document.querySelectorAll('.profile-wb-only').forEach((el) => {
            el.style.display = 'none';
        });
    }
    if (typeof applyCameraUiForProfile === 'function') applyCameraUiForProfile();
    if (typeof onRfidModeChange === 'function') onRfidModeChange();
})();

// ============== Digitizer Conversion Method Modal ==============
let digitizerMethodConfirmHandler = null;

function showDigitizerMethodModal(candidates, dataSample, onConfirm) {
    const overlay = document.getElementById('digitizerMethodOverlay');
    const body = document.getElementById('digitizerMethodBody');
    const rawOutput = document.getElementById('digitizerMethodRawOutput');
    const confirmBtn = document.getElementById('digitizerMethodConfirmBtn');

    if (!overlay || !body || !confirmBtn) {
        console.error('[Digitizer] Method modal elements not found');
        showToast('error', 'Conversion Selection Error', 'Digitizer method selection modal is unavailable. Please refresh and try again.');
        return;
    }

    // Populate raw data preview (similar to digitizer console)
    if (rawOutput) {
        rawOutput.innerHTML = '';
        if (Array.isArray(dataSample) && dataSample.length > 0) {
            dataSample.forEach(entry => {
                const div = document.createElement('div');
                div.className = 'log-entry';
                div.innerHTML = `<span class="log-time">[${entry.time}]</span>${entry.data}`;
                rawOutput.appendChild(div);
            });
        } else {
            rawOutput.innerHTML = '<div class="log-entry text-muted">No raw data sample available.</div>';
        }
    }

    body.innerHTML = '';

    candidates.forEach((cand, index) => {
        const id = `digitizer-method-${cand.id}`;
        const wrapper = document.createElement('div');
        wrapper.className = 'form-check';
        wrapper.innerHTML = `
            <input class="form-check-input" type="radio" name="digitizerMethod" id="${id}" value="${cand.id}" ${index === 0 ? 'checked' : ''}>
            <label class="form-check-label" for="${id}">
                <strong>${cand.label}</strong> &nbsp; 
                <span class="text-info">(Parsed weight: ${cand.weight} kg)</span>
            </label>
        `;
        body.appendChild(wrapper);
    });

    digitizerMethodConfirmHandler = () => {
        const selected = document.querySelector('input[name="digitizerMethod"]:checked');
        const methodId = selected ? selected.value : null;
        hideDigitizerMethodModal();
        onConfirm(methodId);
    };

    confirmBtn.onclick = digitizerMethodConfirmHandler;
    overlay.style.display = 'flex';
}

function hideDigitizerMethodModal() {
    const overlay = document.getElementById('digitizerMethodOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

async function stopDigitizer() {
    try {
        await fetch('/api/digitizer/stop', { method: 'POST' });
        document.getElementById('digitizerConsole').style.display = 'none';
        showToast('success', 'Stopped', 'Digitizer connection stopped');
    } catch (error) {
        console.error('[Digitizer Stop] Error:', error);
        showToast('error', 'Error', 'Unable to stop digitizer');
    }
}

function clearDigitizerConsole() {
    document.getElementById('digitizerOutput').innerHTML = '';
}

// ============== Audio Configuration ==============
let audioTestPassed = false;

async function playTestAudio() {
    const btn = document.querySelector('.btn-audio');
    const validateBtn = document.getElementById('audioValidateBtn');

    if (!btn) return;

    btn.disabled = true;
    if (validateBtn) {
        validateBtn.disabled = true;
    }

    try {
        const response = await fetch('/api/audio/test', {
            method: 'POST'
        });
        const result = await response.json();

        if (response.ok && result.success) {
            audioTestPassed = true;
            if (validateBtn) {
                validateBtn.disabled = false;
            }
            showToast('success', 'Audio OK', 'Test audio played successfully on this PC.');
        } else {
            audioTestPassed = false;
            if (validateBtn) {
                validateBtn.disabled = true;
            }

            const reason = result.reason || '';
            if (reason === 'NO_AUDIO_DRIVER') {
                showToast('error', 'Audio Error', 'Audio System is not connected to this PC. Please connect and retry');
            } else {
                showToast('error', 'Audio Error', result.message || 'Failed to play test audio');
            }
        }
    } catch (error) {
        console.error('[Audio Test] Error:', error);
        audioTestPassed = false;
        const validateBtn = document.getElementById('audioValidateBtn');
        if (validateBtn) {
            validateBtn.disabled = true;
        }
        showToast('error', 'Audio Error', 'Unable to run audio test on this PC');
    } finally {
        btn.disabled = false;
    }
}

async function validateAudio() {
    if (!audioTestPassed) {
        showToast('error', 'Audio Not Tested', 'Please run the audio test and ensure it plays successfully before marking as validated.');
        return;
    }

    const audioMake = document.getElementById('audioMake')?.value.trim() || '';
    const audioModel = document.getElementById('audioModel')?.value.trim() || '';
    
    // Validate device info in production mode
    if (!validateDeviceInfo(audioMake, audioModel, 'Audio Device')) {
        return;
    }
    
    try {
        // Backend uses 'voice' section name
        await fetch('/api/config/voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                make: audioMake,
                model: audioModel,
                validated: true 
            })
        });
        
        showToast('success', 'Success', 'Audio configuration validated');
        markSectionValidated('audio');
    } catch (error) {
        console.error('[Audio Validation] Error:', error);
        showToast('error', 'Error', 'Unable to save audio validation');
    }
}

// ============== Reset Section ==============
async function resetSection(section) {
    try {
        const response = await fetch(`/api/config/${section}/reset`, { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 200) {
            // Mark section as NOT validated when reset
            markSectionNotValidated(section);
            await loadConfig();
            showToast('success', 'Reset', `${section} configuration reset to defaults`);
        } else {
            showToast('error', 'Error', result.message);
        }
    } catch (error) {
        console.error('[Reset Section] Error:', error);
        showToast('error', 'Error', 'Unable to reset configuration');
    }
}

function markSectionNotValidated(section) {
    // Map section names if needed
    const sectionMap = {
        'io-controller': 'io_controller',
        'io_controller': 'io_controller',
        'audio': 'voice'  // Frontend uses 'audio', backend uses 'voice'
    };
    const configSection = sectionMap[section] || section;
    
    // Mark as not validated - update completion status if it exists
    if (typeof completionStatus !== 'undefined') {
        completionStatus[configSection] = false;
        // Also clear frontend key if it's audio
        if (configSection === 'voice') {
            completionStatus['audio'] = false;
        }
        
        // Update all_complete status - use backend section names
        const sections = getWizardCompletionSections();
        completionStatus.all_complete = sections.every(s => completionStatus[s]);
        
        // Update UI if function exists
        if (typeof updateValidationUI === 'function') {
            updateValidationUI();
        }
    }
    
    console.log(`[Reset] Section '${configSection}' marked as not validated`);
}

// ============== Skip Section (Debug Only) ==============
async function skipSection(section) {
    if (!APP_CONFIG.debug) {
        showToast('error', 'Skip', 'Skip is only available in debug mode.');
        return;
    }
    const skippableSections = ['display', 'audio'];
    if (!skippableSections.includes(section)) {
        showToast('error', 'Skip', 'Only display and audio can be skipped in debug mode.');
        return;
    }
    const sectionMap = {
        'io-controller': 'io_controller',
        'audio': 'voice'  // Frontend uses 'audio', backend uses 'voice'
    };
    
    const configSection = sectionMap[section] || section;
    
    try {
        // Special handling for camera - needs both top and front validated, plus camera section itself
        if (section === 'camera') {
            await fetch('/api/config/camera', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    validated: null,  // Mark camera section as skipped (None/null)
                    top: { validated: null },
                    front: { validated: null }
                })
            });
        } else {
            await fetch(`/api/config/${configSection}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ validated: null })  // Set to null for skipped
            });
        }
        
        // Reload completion status to ensure UI is updated
        await loadCompletionStatus();
        
        // Mark section as skipped in local state (use original section name for frontend)
        markSectionSkipped(section);
        
        showToast('warning', 'Skipped', `${section} configuration skipped (Debug mode)`);
        
        // Navigate to next section - normalize section name for navigation
        // Navigation uses hyphenated names (io-controller), but HTML may use underscores (io_controller)
        const navSectionMap = {
            'io_controller': 'io-controller',
            'io-controller': 'io-controller',
            'audio': 'audio',
            'voice': 'audio'
        };
        const navSection = navSectionMap[section] || section;
        navigateToNext(navSection);
    } catch (error) {
        console.error('[Skip Section] Error:', error);
        showToast('error', 'Error', 'Unable to skip section');
    }
}

// ============== Finish Configuration ==============
// Initialize finish button listener
const finishBtn = document.getElementById('finishBtn');
if (finishBtn) {
    finishBtn.addEventListener('click', function() {
        openApiEndpointsAskModal();
    });
}

function openFinishModal() {
    const modal = document.getElementById('finishModal');
    modal.classList.add('active');
    
    // Set today's date as default
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('verificationDate').value = today;
}

function closeFinishModal() {
    const modal = document.getElementById('finishModal');
    modal.classList.remove('active');
}

// ---- API Endpoints finish-flow ----
let _apiEndpointsAdminPassword = '';
let _apiEndpointFieldDefs = [];

function _joinApiUrl(base, pathOrUrl) {
    const p = String(pathOrUrl || '').trim();
    if (!p) return String(base || '').trim();
    if (/^https?:\/\//i.test(p)) return p;
    const b = String(base || '').replace(/\/$/, '');
    return b + (p.startsWith('/') ? p : '/' + p);
}

function openApiEndpointsAskModal() {
    const modal = document.getElementById('apiEndpointsAskModal');
    if (!modal) {
        openFinishModal();
        return;
    }
    modal.classList.add('active');
}

function closeApiEndpointsAskModal() {
    document.getElementById('apiEndpointsAskModal')?.classList.remove('active');
}

function declineApiEndpointsConfig() {
    closeApiEndpointsAskModal();
    openFinishModal();
}

function acceptApiEndpointsConfig() {
    closeApiEndpointsAskModal();
    openApiEndpointsPasswordModal();
}

function openApiEndpointsPasswordModal() {
    const modal = document.getElementById('apiEndpointsPasswordModal');
    const input = document.getElementById('apiEndpointsAdminPassword');
    const err = document.getElementById('apiEndpointsAdminError');
    if (err) {
        err.style.display = 'none';
        err.textContent = '';
    }
    if (input) {
        input.value = '';
        setTimeout(() => input.focus(), 50);
    }
    modal?.classList.add('active');
}

function closeApiEndpointsPasswordModal(skipToFinish = true) {
    document.getElementById('apiEndpointsPasswordModal')?.classList.remove('active');
    _apiEndpointsAdminPassword = '';
    if (skipToFinish) {
        openFinishModal();
    }
}

async function submitApiEndpointsAdminPassword() {
    const input = document.getElementById('apiEndpointsAdminPassword');
    const err = document.getElementById('apiEndpointsAdminError');
    const password = (input?.value || '').trim();
    if (!password) {
        if (err) {
            err.textContent = 'Password is required';
            err.style.display = 'block';
        }
        return;
    }

    showLoading(true, 'Verifying admin password...');
    try {
        const resp = await fetch('/api/admin/verify-api-endpoints-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.status !== 200) {
            if (err) {
                err.textContent = data.message || 'Invalid admin password';
                err.style.display = 'block';
            }
            showToast('error', 'Admin Password', data.message || 'Invalid admin password');
            return;
        }

        _apiEndpointsAdminPassword = password;
        _apiEndpointFieldDefs = Array.isArray(data.api_fields) ? data.api_fields : [];
        document.getElementById('apiEndpointsPasswordModal')?.classList.remove('active');
        populateApiEndpointsEditor(data.api_endpoints || {}, _apiEndpointFieldDefs);
        openApiEndpointsEditModal();
    } catch (e) {
        console.error('[API Endpoints] verify error:', e);
        showToast('error', 'Error', 'Unable to verify admin password');
    } finally {
        showLoading(false);
    }
}

function openApiEndpointsEditModal() {
    const profile = window.APP_CONFIG?.profile || {};
    const subtitle = document.getElementById('apiEndpointsEditSubtitle');
    if (subtitle) {
        subtitle.textContent = `Configure URLs and passwords for ${profile.label || 'this checkpoint'}`;
    }
    document.getElementById('apiEndpointsEditModal')?.classList.add('active');
}

function closeApiEndpointsEditModal(continueFinish = false) {
    document.getElementById('apiEndpointsEditModal')?.classList.remove('active');
    _apiEndpointsAdminPassword = '';
    if (continueFinish) {
        openFinishModal();
    }
}

function populateApiEndpointsEditor(endpoints, fields) {
    const container = document.getElementById('apiEndpointsFields');
    if (!container) return;
    container.innerHTML = '';

    (fields || []).forEach((field) => {
        const urlVal = _joinApiUrl(
            endpoints[field.base_key],
            endpoints[field.url_key]
        );
        const userKey = field.username_key;
        const passKey = field.password_key;
        // Prefer per-endpoint creds; fall back to legacy shared keys
        const legacyUser = field.id === 'anpr_detect'
            ? (endpoints.anpr_username || endpoints.oci_username || '')
            : (endpoints.oci_username || '');
        const legacyPass = field.id === 'anpr_detect'
            ? (endpoints.anpr_password || endpoints.oci_password || '')
            : (endpoints.oci_password || '');
        const userVal = (userKey && endpoints[userKey]) || legacyUser || '';
        const passVal = (passKey && endpoints[passKey]) || legacyPass || '';

        const row = document.createElement('div');
        row.className = 'api-endpoint-row';
        row.style.cssText = 'border:1px solid #e5e7eb; border-radius:8px; padding:12px 14px; margin-bottom:14px; background:#fafbfc;';
        row.dataset.fieldId = field.id;
        row.dataset.urlKey = field.url_key;
        row.dataset.baseKey = field.base_key || '';
        row.dataset.usernameKey = userKey || '';
        row.dataset.passwordKey = passKey || '';
        row.innerHTML = `
            <div class="form-group" style="margin-bottom:8px;">
                <label style="margin-bottom:0;"><strong>${field.label}</strong></label>
            </div>
            <div class="form-group" style="margin-bottom:10px;">
                <label>URL</label>
                <input type="text" class="form-control api-ep-url" value="${_escapeHtmlAttr(urlVal)}"
                       placeholder="https://host/path" autocomplete="off">
            </div>
            <div class="form-row" style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                <div class="form-group" style="margin-bottom:0;">
                    <label>Username</label>
                    <input type="text" class="form-control api-ep-username" value="${_escapeHtmlAttr(userVal)}"
                           placeholder="API username" autocomplete="off">
                </div>
                <div class="form-group" style="margin-bottom:0;">
                    <label>Password</label>
                    <div class="input-group">
                        <input type="password" class="form-control api-ep-password" value="${_escapeHtmlAttr(passVal)}"
                               placeholder="API password" autocomplete="off">
                        <button type="button" class="btn btn-outline-secondary api-ep-toggle-pass" title="Show / hide password">
                            <i class="bi bi-eye"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(row);
    });

    container.querySelectorAll('.api-ep-toggle-pass').forEach((btn) => {
        btn.addEventListener('click', function() {
            const input = this.parentElement.querySelector('.api-ep-password');
            const icon = this.querySelector('i');
            if (!input) return;
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            if (icon) {
                icon.classList.toggle('bi-eye', !show);
                icon.classList.toggle('bi-eye-slash', show);
            }
            this.title = show ? 'Hide password' : 'Show password';
        });
    });
}

function _escapeHtmlAttr(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function _splitBaseAndPath(fullUrl) {
    const u = String(fullUrl || '').trim();
    if (!u) return { base: '', path: '' };
    try {
        const parsed = new URL(u);
        const base = `${parsed.protocol}//${parsed.host}`;
        const path = parsed.pathname + (parsed.search || '');
        return { base, path: path || '/' };
    } catch (_) {
        return { base: '', path: u };
    }
}

async function saveApiEndpointsAndContinue() {
    if (!_apiEndpointsAdminPassword) {
        showToast('error', 'Admin Password', 'Admin session expired - please try again');
        closeApiEndpointsEditModal(false);
        openApiEndpointsPasswordModal();
        return;
    }

    const payload = {
        password: _apiEndpointsAdminPassword,
    };

    document.querySelectorAll('#apiEndpointsFields .api-endpoint-row').forEach((row) => {
        const urlKey = row.dataset.urlKey;
        const baseKey = row.dataset.baseKey;
        const usernameKey = row.dataset.usernameKey;
        const passwordKey = row.dataset.passwordKey;
        const url = row.querySelector('.api-ep-url')?.value?.trim() || '';
        const username = row.querySelector('.api-ep-username')?.value?.trim() || '';
        const password = row.querySelector('.api-ep-password')?.value || '';

        if (urlKey === 'anpr_detect_url' && baseKey === 'anpr_base_url') {
            const parts = _splitBaseAndPath(url);
            if (parts.base) payload.anpr_base_url = parts.base;
            payload.anpr_detect_url = parts.path || url;
        } else if (urlKey && baseKey === 'oci_base_url') {
            const parts = _splitBaseAndPath(url);
            if (parts.base) payload.oci_base_url = parts.base;
            payload[urlKey] = parts.path || url;
        } else if (urlKey) {
            payload[urlKey] = url;
        }

        if (usernameKey) payload[usernameKey] = username;
        if (passwordKey) payload[passwordKey] = password;
    });

    showLoading(true, 'Saving API endpoints...');
    try {
        const resp = await fetch('/api/config/api_endpoints', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.status !== 200) {
            showToast('error', 'Save Failed', data.message || 'Unable to save API endpoints');
            return;
        }
        showToast('success', 'API Endpoints', 'API endpoints saved');
        closeApiEndpointsEditModal(true);
    } catch (e) {
        console.error('[API Endpoints] save error:', e);
        showToast('error', 'Error', 'Unable to save API endpoints');
    } finally {
        showLoading(false);
    }
}

document.getElementById('apiEndpointsAskModal')?.addEventListener('click', function(e) {
    if (e.target === this) declineApiEndpointsConfig();
});
document.getElementById('apiEndpointsPasswordModal')?.addEventListener('click', function(e) {
    if (e.target === this) closeApiEndpointsPasswordModal(true);
});
document.getElementById('apiEndpointsEditModal')?.addEventListener('click', function(e) {
    if (e.target === this) closeApiEndpointsEditModal(true);
});
document.getElementById('apiEndpointsAdminPassword')?.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        submitApiEndpointsAdminPassword();
    }
});
document.getElementById('apiEndpointsAdminPassToggle')?.addEventListener('click', function() {
    const input = document.getElementById('apiEndpointsAdminPassword');
    const icon = this.querySelector('i');
    if (!input) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    if (icon) {
        icon.classList.toggle('bi-eye', !show);
        icon.classList.toggle('bi-eye-slash', show);
    }
    this.title = show ? 'Hide password' : 'Show password';
});

// ============== Import Previous Configuration ==============
function openImportConfigModal() {
    const modal = document.getElementById('importConfigModal');
    const fileEl = document.getElementById('importConfigFile');
    if (!modal) return;
    if (fileEl) fileEl.value = '';
    modal.classList.add('active');
}

function closeImportConfigModal() {
    const modal = document.getElementById('importConfigModal');
    if (!modal) return;
    modal.classList.remove('active');
}

async function importPreviousConfig() {
    const fileEl = document.getElementById('importConfigFile');
    const file = fileEl?.files?.[0];
    if (!file) {
        showToast('warning', 'No File Selected', 'Please choose an older iot_configuration.json first.');
        return;
    }

    showLoading(true, 'Importing configuration...');

    try {
        const formData = new FormData();
        formData.append('configFile', file);

        const response = await fetch('/api/import-config', {
            method: 'POST',
            body: formData
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.status !== 200) {
            showToast('error', 'Import Failed', result.message || 'Unable to import configuration');
            return;
        }

        closeImportConfigModal();
        showToast(
            'success',
            'Imported',
            'RFID/Display/Digitizer/Audio marked for re-validation. Other modules auto-validated.'
        );

        // Refresh UI
        await loadConfig();
        await loadCompletionStatus();
    } catch (error) {
        console.error('[Import Config] Error:', error);
        showToast('error', 'Import Error', 'Unable to import configuration');
    } finally {
        showLoading(false);
    }
}

// Close import modal on outside click
document.getElementById('importConfigModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeImportConfigModal();
    }
});

// ============== Auto Import Legacy Configuration ==============
function closeAutoImportConfigModal() {
    const modal = document.getElementById('autoImportConfigModal');
    if (!modal) return;
    modal.classList.remove('active');
}

async function confirmAutoImportConfig() {
    const modal = document.getElementById('autoImportConfigModal');
    if (!modal) return;

    showLoading(true, 'Auto-importing old configuration...');

    try {
        const response = await fetch('/api/auto-import-config', { method: 'POST' });
        const result = await response.json().catch(() => ({}));

        if (!response.ok || result.status !== 200) {
            showToast('error', 'Auto Import Failed', result.message || 'Unable to auto-fetch legacy configuration');
            return;
        }

        closeAutoImportConfigModal();
        showToast('success', 'Imported', 'Legacy configuration imported. RFID/Display/Digitizer/Audio marked for re-validation.');

        await loadConfig();
        await loadCompletionStatus();
    } catch (error) {
        console.error('[Auto Import] Error:', error);
        showToast('error', 'Auto Import Error', 'Unable to auto-fetch legacy configuration');
    } finally {
        showLoading(false);
    }
}

async function submitFinalConfig() {
    // Validate required fields
    const vendorCompany = document.getElementById('vendorCompany').value.trim();
    const verifiedBy = document.getElementById('verifiedBy').value.trim();
    const verificationDate = document.getElementById('verificationDate').value;
    const remarks = document.getElementById('remarks').value.trim();
    
    // Check required fields
    if (!vendorCompany || !verifiedBy) {
        showToast('error', 'Validation Error', 'Please fill all required fields');
        return;
    }
    
    showLoading(true);
    
    try {
        // First save the setup info
        const setupInfo = {
            vendor_company: vendorCompany,
            verified_by: verifiedBy,
            verification_date: verificationDate,
            remarks: remarks,
            setup_timestamp: new Date().toISOString()
        };
        
        await fetch('/api/config/setup_info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(setupInfo)
        });
        
        // Then finalize
        const response = await fetch('/api/finish', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 200) {
            closeFinishModal();
            showToast('success', 'Configuration Complete', 'Setup completed successfully!');
            
            // Hide initial loading, then show specific message for PDF generation
            showLoading(false);
            showLoading(true, 'Configuration is completed. Please wait, we are creating a report...');
            
            // Generate PDF report on server (saved in reports folder; API may return JSON + base64)
            try {
                const pdfResponse = await fetch('/api/generate-pdf-report', { method: 'POST' });
                const contentType = (pdfResponse.headers.get('Content-Type') || '').toLowerCase();

                const showPdfFailure = (detail) => {
                    const msg = detail || 'Configuration saved but PDF report could not be generated';
                    console.error('PDF generation error (devices view):', detail);
                    showToast('warning', 'PDF Generation Failed', msg);
                };

                if (pdfResponse.ok && contentType.includes('application/json')) {
                    const data = await pdfResponse.json();
                    if (data.status === 200 && data.data) {
                        showToast('success', 'PDF Generated', 'Configuration report PDF has been created in the reports folder');
                    } else {
                        showPdfFailure(data.message);
                    }
                } else if (pdfResponse.ok) {
                    showToast('success', 'PDF Generated', 'Configuration report PDF has been created in the reports folder');
                } else {
                    let errDetail = null;
                    try {
                        const errorData = await pdfResponse.json();
                        errDetail = errorData.message || null;
                    } catch (_) { /* ignore */ }
                    showPdfFailure(errDetail);
                }
            } catch (pdfError) {
                console.error('Error generating PDF (devices view):', pdfError);
                showToast('warning', 'PDF Generation Failed', pdfError.message || 'Configuration saved but PDF report could not be generated');
            } finally {
                // Hide loading overlay after PDF generation completes
                showLoading(false);
            }
            
            // Show completion message, then auto-close the application
            setTimeout(() => {
                // Only show "Configuration saved to:" if DEBUG mode is enabled
                const configFileLine = APP_CONFIG.debug 
                    ? `<p><strong>Configuration saved to:</strong> ${result.file}</p>`
                    : '';
                
                const completionMessage = `
                    <div style="text-align: center; padding: 20px;">
                        <i class="bi bi-check-circle-fill" style="font-size: 48px; color: #28a745; margin-bottom: 15px;"></i>
                        <h3 style="margin-bottom: 15px;">Configuration Completed Successfully!</h3>
                        <p style="color: var(--text-muted); margin-bottom: 10px;">Application will close automatically...</p>
                        <div class="completion-details" style="text-align: left; background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 20px;">
                            <p><strong>Verified by:</strong> ${verifiedBy}</p>
                            ${configFileLine}
                        </div>
                    </div>
                `;
                showCompletionModal(completionMessage);
                // Auto-close shortly after success (no OK click required)
                setTimeout(() => {
                    closeCompletionModal();
                }, 2000);
            }, 1000); // Increased delay to allow PDF download to complete
            return; // Exit early to prevent finally block from hiding loading
        } else {
            showToast('error', 'Error', result.message);
        }
    } catch (error) {
        console.error('[Finish Config] Error:', error);
        showToast('error', 'Error', 'Unable to finalize configuration');
    } finally {
        showLoading(false);
    }
}

// Close modal on outside click
document.getElementById('finishModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeFinishModal();
    }
});

// ============== Modal Functions ==============
let sensorConfirmCallback = null;
let hardwareTestCallback = null;
let currentHardwareTestData = null;

// Completion Modal
function showCompletionModal(content) {
    const modal = document.getElementById('completionModal');
    const contentEl = document.getElementById('completionModalContent');
    if (modal && contentEl) {
        contentEl.innerHTML = content;
        modal.style.display = 'flex';
    }
}

function closeCompletionModal() {
    const modal = document.getElementById('completionModal');
    if (modal) {
        modal.style.display = 'none';
    }
    // Close backend + frontend window after setup completes
    const closeFrontend = () => {
        try {
            // Chrome --app windows often ignore a bare window.close()
            window.open('', '_self');
            window.close();
        } catch (e) { /* ignore */ }
        try {
            if (window.chrome && window.chrome.runtime && window.chrome.runtime.PlatformOs) {
                window.close();
            }
        } catch (e) { /* ignore */ }
    };

    fetch('/api/close', { method: 'POST' })
        .then(() => {
            setTimeout(closeFrontend, 150);
            setTimeout(closeFrontend, 800);
        })
        .catch(err => {
            console.error('Error closing application:', err);
            closeFrontend();
        });
}

// Sensor Confirmation Modal
function showSensorConfirmModal(message, callback) {
    const modal = document.getElementById('sensorConfirmModal');
    const contentEl = document.getElementById('sensorConfirmContent');
    if (modal && contentEl) {
        contentEl.innerHTML = `<p>${message.replace(/\n/g, '<br>')}</p>`;
        sensorConfirmCallback = callback;
        modal.style.display = 'flex';
    }
}

function closeSensorConfirmModal(confirmed) {
    const modal = document.getElementById('sensorConfirmModal');
    if (modal) {
        modal.style.display = 'none';
    }
    if (sensorConfirmCallback) {
        sensorConfirmCallback(confirmed);
        sensorConfirmCallback = null;
    }
}

// Hardware Test Confirmation Modal
function showHardwareTestModal(deviceType, location, action, callback) {
    const modal = document.getElementById('hardwareTestModal');
    const contentEl = document.getElementById('hardwareTestContent');
    if (modal && contentEl) {
        let message = '';
        const locationName = location.charAt(0).toUpperCase() + location.slice(1);
        
        if (deviceType === 'traffic_light') {
            const colorName = action === 'red' ? 'RED' : 'GREEN';
            message = `Have the ${locationName} traffic light really turned ${colorName}?<br><br>Please check manually by looking at the traffic light.`;
        } else if (deviceType === 'boom_barrier') {
            const actionName = action === 'open' ? 'OPENED' : 'CLOSED';
            message = `Has the ${locationName} boom barrier really ${actionName}?<br><br>Please check manually by looking at the boom barrier.`;
        }
        
        contentEl.innerHTML = `<p>${message}</p>`;
        hardwareTestCallback = callback;
        currentHardwareTestData = { deviceType, location, action };
        modal.style.display = 'flex';
    }
}

function closeHardwareTestModal(confirmed) {
    const modal = document.getElementById('hardwareTestModal');
    if (modal) {
        modal.style.display = 'none';
    }
    if (hardwareTestCallback) {
        hardwareTestCallback(confirmed, currentHardwareTestData);
        hardwareTestCallback = null;
        currentHardwareTestData = null;
    }
}

// Close modals on outside click
document.getElementById('completionModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeCompletionModal();
    }
});

document.getElementById('sensorConfirmModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeSensorConfirmModal(false);
    }
});

document.getElementById('hardwareTestModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeHardwareTestModal(false);
    }
});

document.getElementById('moduleHelpModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeModuleHelp();
    }
});

document.getElementById('debugErrorModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeDebugErrorModal();
    }
});

// ============== UI Utilities ==============
function showLoading(show, message = null) {
    const overlay = document.getElementById('loadingOverlay');
    const span = overlay.querySelector('span');
    if (show) {
        if (message) {
            span.textContent = message;
        } else {
            span.textContent = 'Processing...';
        }
        overlay.classList.add('active');
    } else {
        overlay.classList.remove('active');
        // Reset to default message when hiding
        span.textContent = 'Processing...';
    }
}

let notificationTimeout = null;

function showToast(type, title, message) {
    const ribbon = document.getElementById('notificationRibbon');
    const icon = document.getElementById('notifIcon');
    const text = document.getElementById('notifText');
    if (!ribbon || !icon || !text) {
        console.warn('[Toast]', type, title, message);
        return;
    }
    
    // Clear any existing timeout
    if (notificationTimeout) {
        clearTimeout(notificationTimeout);
    }
    
    // Set icon based on type
    const icons = {
        success: 'bi-check-circle-fill',
        error: 'bi-x-circle-fill',
        warning: 'bi-exclamation-triangle-fill',
        info: 'bi-info-circle-fill'
    };
    
    const debugOn = !!(window.APP_CONFIG && window.APP_CONFIG.debug);
    const rawMessage = String(message || '');
    const installerMessage = (type === 'error' && !debugOn)
        ? simplifyErrorMessage(rawMessage)
        : rawMessage;
    icon.className = 'bi ' + (icons[type] || icons.info);
    text.textContent = installerMessage;
    
    // Set ribbon type
    ribbon.className = 'notification-ribbon ' + type;
    
    // Show ribbon
    setTimeout(() => {
        ribbon.classList.add('show');
    }, 10);
    
    // Auto hide after 10 seconds
    notificationTimeout = setTimeout(() => {
        hideNotification();
    }, 10000);

    if (type === 'error' && debugOn) {
        showDebugErrorModal(title || 'Error', rawMessage || 'No additional debug details available.');
    }
}

function hideNotification() {
    const ribbon = document.getElementById('notificationRibbon');
    ribbon.classList.remove('show');
    
    if (notificationTimeout) {
        clearTimeout(notificationTimeout);
        notificationTimeout = null;
    }
}

