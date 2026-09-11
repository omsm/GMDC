// E-Rawanna IoT - Configuration JavaScript
// Main application logic

/** Fixed server connection (read-only in UI). */
const SERVER_DEFAULT_HOST = 'localhost';
const SERVER_DEFAULT_PORT = '8080';

function applyServerConfigDefaults() {
    const serverIpEl = document.getElementById('serverIp');
    const serverPortEl = document.getElementById('serverPort');
    if (serverIpEl) {
        serverIpEl.value = SERVER_DEFAULT_HOST;
        serverIpEl.readOnly = true;
    }
    if (serverPortEl) {
        if (!serverPortEl.value || serverPortEl.value === '80') {
            serverPortEl.value = SERVER_DEFAULT_PORT;
        }
        serverPortEl.readOnly = false;
    }
}

function getServerConnectionSettings() {
    const portEl = document.getElementById('serverPort');
    const port = (portEl && portEl.value.trim()) || SERVER_DEFAULT_PORT;
    return { ip: SERVER_DEFAULT_HOST, port };
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
let scanInterval = null;

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
    const s = ['server', 'rfid'];
    if (APP_CONFIG.enableCamera) s.push('camera');
    s.push('display', 'io-controller', 'digitizer', 'audio');
    return s;
}

function getWizardCompletionSections() {
    const s = ['server', 'rfid'];
    if (APP_CONFIG.enableCamera) s.push('camera');
    s.push('display', 'io_controller', 'digitizer', 'voice');
    return s;
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
    if (!isSensor2IoTestSatisfied()) failures.push('WB sensor');
    if (!isEntryExitSensorIoTestSatisfied(3)) failures.push('Exit sensor');
    if (!isTrafficLightIoTestSatisfied('entry') || !isTrafficLightIoTestSatisfied('exit')) {
        failures.push('entry and exit traffic lights');
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
        'serverMake', 'serverModel',
        'rfidMake', 'rfidModel',
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
    refreshFastagValidationConfig();
    initTheme();
    initChecklist();
    loadSuggestedIpRange();
    initRequiredFieldIndicators();
    // Config stage initialization happens after proceeding through stages
});

// ============== Auto-detect IP Range ==============
async function loadSuggestedIpRange() {
    try {
        const response = await fetch('/api/network/ip-range');
        const data = await response.json();
        
        // Populate IP range fields
        document.getElementById('startIp').value = data.start_ip;
        document.getElementById('endIp').value = data.end_ip;
        
        console.log(`[Config] Local IP detected: ${data.local_ip}`);
        console.log(`[Config] Suggested range: ${data.start_ip} - ${data.end_ip}`);
    } catch (error) {
        console.error('Failed to get suggested IP range:', error);
        // Keep default values
    }
}

// ============== Stage Management ==============
function showStage(stageName) {
    document.querySelectorAll('.stage-container').forEach(stage => {
        stage.classList.add('hidden');
    });
    document.getElementById(stageName + 'Stage').classList.remove('hidden');
}

// ============== Checklist Stage ==============
function initChecklist() {
    const checkboxes = document.querySelectorAll('.checklist-items input[type="checkbox"]');
    const proceedBtn = document.getElementById('proceedBtn');
    
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            proceedBtn.disabled = !allChecked;
        });
    });
}

async function proceedToScan() {
    const startIp = document.getElementById('startIp').value.trim();
    const endIp = document.getElementById('endIp').value.trim();
    
    if (!startIp || !endIp) {
        showToast('error', 'Validation Error', 'Please enter both Start and End IP addresses');
        return;
    }
    
    // Show discovery stage
    showStage('discovery');
    
    // Start the scan
    try {
        const response = await fetch('/api/network/scan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_ip: startIp, end_ip: endIp })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            document.getElementById('scanTotal').textContent = result.total_ips;
            
            // Start polling for status
            scanInterval = setInterval(updateScanStatus, 500);
        } else {
            showToast('error', 'Scan Failed', result.message || 'Unable to start network scan');
        }
    } catch (error) {
        console.error('[Network Scan] Error:', error);
        showToast('error', 'Connection Error', 'Unable to connect to server. Please check if the application is running.');
    }
}

async function updateScanStatus() {
    try {
        const response = await fetch('/api/network/results');
        const data = await response.json();
        
        // Update progress
        document.getElementById('scanProgress').textContent = data.status.progress;
        document.getElementById('scanFound').textContent = data.status.found;
        document.getElementById('scanCurrentIp').textContent = 'Scanning: ' + data.status.current_ip;
        
        const percent = (data.status.progress / data.status.total) * 100;
        document.getElementById('scanProgressBar').style.width = percent + '%';
        
        // Check if scan is complete
        if (!data.status.running) {
            clearInterval(scanInterval);
            scanInterval = null;
            
            // Store discovered devices
            discoveredDevices.network = data.network_devices;
            discoveredDevices.comPorts = data.com_ports;
            discoveredDevices.candidates = data.candidates;
            
            // Show results
            showDiscoveryResults();
        }
    } catch (error) {
        console.error('Status update error:', error);
    }
}

function showDiscoveryResults() {
    document.getElementById('discoveryResults').classList.remove('hidden');
    document.getElementById('scanCurrentIp').textContent = 'Scan complete!';
    
    // Update summary
    document.getElementById('networkDeviceCount').textContent = discoveredDevices.network.length;
    document.getElementById('comPortCount').textContent = discoveredDevices.comPorts.length;
    
    // Populate network devices table
    const networkBody = document.getElementById('networkDevicesBody');
    networkBody.innerHTML = '';
    
    discoveredDevices.network.forEach(device => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ip-cell">${device.ip}</td>
            <td><span class="device-type-badge">${device.device_type}</span></td>
            <td>${device.open_ports.map(p => `<span class="port-badge">${p}</span>`).join(' ')}</td>
        `;
        networkBody.appendChild(row);
    });
    
    // Populate COM ports table
    const comBody = document.getElementById('comPortsBody');
    comBody.innerHTML = '';
    
    discoveredDevices.comPorts.forEach(port => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ip-cell">${port.device}</td>
            <td>${port.description}</td>
        `;
        comBody.appendChild(row);
    });
}

async function rescan() {
    document.getElementById('discoveryResults').classList.add('hidden');
    showStage('checklist');
}

function proceedToConfig() {
    showStage('config');
    
    // Initialize configuration stage
    initNavigation();
    applyServerConfigDefaults();
    loadConfig();
    loadCompletionStatus();
    populateDeviceDropdowns();
}

function backToDiscovery() {
    showStage('discovery');
}

// ============== Device Dropdown Population ==============
function populateDeviceDropdowns() {
    // Server dropdown - show devices with HTTP ports
    if (document.getElementById('serverIpSelect')) {
        populateDropdown('serverIpSelect', discoveredDevices.candidates.servers, 'Select discovered server...');
    }
    
    // RFID dropdown - prioritize devices with port 6000
    const rfidDevices = discoveredDevices.candidates.rfid;
    if (rfidDevices.length === 1) {
        // Auto-select if only one RFID device found
        populateDropdown('rfidIpSelect', rfidDevices, 'Select discovered RFID device...');
        document.getElementById('rfidIpSelect').value = rfidDevices[0].ip;
        document.getElementById('rfidAutoDetect').style.display = 'flex';
        document.getElementById('rfidAutoIp').textContent = rfidDevices[0].ip;
        onDeviceSelect('rfidIp', rfidDevices[0].ip);
    } else if (rfidDevices.length > 1) {
        // Multiple RFID devices found
        populateDropdown('rfidIpSelect', rfidDevices, 'Multiple RFID devices found...');
    } else {
        // No RFID devices found, show all IPs
        populateDropdown('rfidIpSelect', discoveredDevices.network, 'No RFID found - Select any device...');
    }
    
    // Display dropdown - show all IPs
    populateDropdown('displayIpSelect', discoveredDevices.network, 'Select discovered device...');
    
    // I/O Controller dropdown - prioritize Modbus devices
    const modbusDevices = discoveredDevices.candidates.modbus;
    if (modbusDevices.length > 0) {
        populateDropdown('ioIpSelect', modbusDevices, 'Select Modbus device...');
    } else {
        populateDropdown('ioIpSelect', discoveredDevices.network, 'No Modbus found - Select any device...');
    }
    
    // Digitizer dropdown - populate COM ports
    populateComPortDropdowns();
}

function ensureServerLocalhostDropdownOption(select) {
    if (!select) return;
    if (Array.from(select.options).some((opt) => opt.value === SERVER_DEFAULT_HOST)) {
        return;
    }
    const option = document.createElement('option');
    option.value = SERVER_DEFAULT_HOST;
    option.textContent = SERVER_DEFAULT_HOST;
    const insertBefore = select.options.length > 1 ? select.options[1] : null;
    select.insertBefore(option, insertBefore);
}

function populateDropdown(selectId, devices, placeholder) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = `<option value="">${placeholder}</option>`;
    
    if (selectId === 'serverIpSelect') {
        ensureServerLocalhostDropdownOption(select);
    }
    
    devices.forEach(device => {
        const deviceIp = device.ip || device;
        if (selectId === 'serverIpSelect' && deviceIp === SERVER_DEFAULT_HOST) return;

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
}

function populateComPortDropdowns() {
    // Digitizer COM port
    const digitizerSelect = document.getElementById('digitizerPort');
    if (digitizerSelect) {
        digitizerSelect.innerHTML = '<option value="">Select port...</option>';
        discoveredDevices.comPorts.forEach(port => {
            const option = document.createElement('option');
            option.value = port.device;
            option.textContent = `${port.device} - ${port.description}`;
            digitizerSelect.appendChild(option);
        });
    }
    
    // I/O Controller serial port
    const ioSerialSelect = document.getElementById('ioSerialPort');
    if (ioSerialSelect) {
        ioSerialSelect.innerHTML = '<option value="">Select port...</option>';
        discoveredDevices.comPorts.forEach(port => {
            const option = document.createElement('option');
            option.value = port.device;
            option.textContent = `${port.device} - ${port.description}`;
            ioSerialSelect.appendChild(option);
        });
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
            if (fieldId === 'serverIp' && !input.value.trim()) {
                input.value = SERVER_DEFAULT_HOST;
            }
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
    
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const section = this.getAttribute('data-section');
            showSection(section);
        });
    });
}

function showSection(sectionId) {
    // Update nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-section') === sectionId) {
            item.classList.add('active');
        }
    });
    
    // Update sections
    document.querySelectorAll('.config-section').forEach(section => {
        section.classList.remove('active');
    });
    
    const targetSection = document.getElementById(sectionId);
    if (targetSection) {
        targetSection.classList.add('active');
    }
}

function navigateToNext(currentSection) {
    const sections = getWizardNavSections();
    const currentIndex = sections.indexOf(currentSection);
    
    if (currentIndex < sections.length - 1) {
        showSection(sections[currentIndex + 1]);
    }
}

// ============== Configuration Loading ==============
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        config = await response.json();
        populateFormFields();
    } catch (error) {
        console.error('Failed to load config:', error);
    }
}

function populateFormFields() {
    // Server - fixed localhost:80 (read-only fields)
    applyServerConfigDefaults();
    
    // RFID
    if (config.rfid) {
        document.getElementById('rfidIp').value = config.rfid.ip || '';
        document.getElementById('rfidPort').value = config.rfid.port || '6000';
        document.getElementById('rfidMake').value = config.rfid.make || '';
        document.getElementById('rfidModel').value = config.rfid.model || '';
    }
    
    // Camera
    if (APP_CONFIG.enableCamera && config.camera) {
        document.getElementById('topCameraUrl').value = config.camera.top?.rtsp_url || '';
        document.getElementById('topCameraMake').value = config.camera.top?.make || '';
        document.getElementById('topCameraModel').value = config.camera.top?.model || '';
        document.getElementById('frontCameraUrl').value = config.camera.front?.rtsp_url || '';
        document.getElementById('frontCameraMake').value = config.camera.front?.make || '';
        document.getElementById('frontCameraModel').value = config.camera.front?.model || '';
    }
    
    // Display
    if (config.display) {
        document.getElementById('displayType').value = config.display.type || 'api';
        document.getElementById('displayIp').value = config.display.ip || '';
        if (document.getElementById('displayPort')) {
            const dtype = (config.display.type || 'api').toLowerCase();
            document.getElementById('displayPort').value = dtype === 'mqtt'
                ? (config.display.port || '1883')
                : (config.display.port || '8000');
        }
        document.getElementById('displayMake').value = config.display.make || '';
        document.getElementById('displayModel').value = config.display.model || '';
        toggleDisplayFields();
    }
    
    // Digitizer
    if (config.digitizer) {
        document.getElementById('digitizerBaud').value = config.digitizer.baud_rate || '9600';
        if (document.getElementById('digitizerDataBits')) {
            document.getElementById('digitizerDataBits').value = config.digitizer.bytesize || '8';
        }
        if (document.getElementById('digitizerParity')) {
            document.getElementById('digitizerParity').value = config.digitizer.parity || 'N';
        }
        if (document.getElementById('digitizerStopBits')) {
            document.getElementById('digitizerStopBits').value = config.digitizer.stopbits || '1';
        }
        document.getElementById('digitizerMake').value = config.digitizer.make || '';
        document.getElementById('digitizerModel').value = config.digitizer.model || '';
        if (typeof updateDigitizerSavedConfig === 'function') {
            updateDigitizerSavedConfig(config.digitizer);
        }
    }
    
    // Audio (frontend uses "audio" keys, backend uses "voice")
    const audioConfig = config.audio || config.voice || {};
    if (audioConfig) {
        document.getElementById('audioMake').value = audioConfig.make || '';
        document.getElementById('audioModel').value = audioConfig.model || '';
    }
    
    // I/O Controller
    if (config.io_controller) {
        document.getElementById('ioType').value = config.io_controller.type || 'ethernet';
        document.getElementById('ioSlaveId').value = config.io_controller.slave_id || '1';
        document.getElementById('ioIp').value = config.io_controller.ip || '';
        document.getElementById('ioPort').value = config.io_controller.port || '502';
        document.getElementById('relayType').value = config.io_controller.relay_type || 'inbuilt';
        document.getElementById('ioMake').value = config.io_controller.make || '';
        document.getElementById('ioModel').value = config.io_controller.model || '';
        
        // Sensor configuration
        if (config.io_controller.sensors) {
            // Sensor 1
            const entrySensor = getSensorFromConfig(config.io_controller.sensors, 1);
            document.getElementById('sensor1Pin').value = entrySensor.pin || '';
            document.getElementById('sensor1Make').value = entrySensor.make || '';
            document.getElementById('sensor1Model').value = entrySensor.model || '';
            applySensorValidatedFromConfig(1, entrySensor.validated);
            
            // Sensor 2
            const wbSensor = getSensorFromConfig(config.io_controller.sensors, 2);
            document.getElementById('sensor2Pin').value = wbSensor.pin || '';
            document.getElementById('sensor2Make').value = wbSensor.make || '';
            document.getElementById('sensor2Model').value = wbSensor.model || '';
            if (wbSensor.same_as_first) {
                document.getElementById('sensor2SameAsFirst').checked = true;
                toggleSameAsFirst('sensor', 2);
            }
            applySensor2ValidatedFromConfig(wbSensor.validated);
            
            // Sensor 3
            const exitSensor = getSensorFromConfig(config.io_controller.sensors, 3);
            document.getElementById('sensor3Pin').value = exitSensor.pin || '';
            document.getElementById('sensor3Make').value = exitSensor.make || '';
            document.getElementById('sensor3Model').value = exitSensor.model || '';
            if (exitSensor.same_as_first) {
                document.getElementById('sensor3SameAsFirst').checked = true;
                toggleSameAsFirst('sensor', 3);
            }
            applySensorValidatedFromConfig(3, exitSensor.validated);
        }
        
        // Traffic Light configuration
        if (config.io_controller.traffic_lights) {
            // Entry TL
            document.getElementById('entryTLMake').value = config.io_controller.traffic_lights.entry?.make || '';
            document.getElementById('entryTLModel').value = config.io_controller.traffic_lights.entry?.model || '';
            document.getElementById('entryRedPin').value = config.io_controller.traffic_lights.entry?.red_pin || '';
            document.getElementById('entryGreenPin').value = config.io_controller.traffic_lights.entry?.green_pin || '';
            
            // Exit TL
            document.getElementById('exitTLMake').value = config.io_controller.traffic_lights.exit?.make || '';
            document.getElementById('exitTLModel').value = config.io_controller.traffic_lights.exit?.model || '';
            document.getElementById('exitRedPin').value = config.io_controller.traffic_lights.exit?.red_pin || '';
            document.getElementById('exitGreenPin').value = config.io_controller.traffic_lights.exit?.green_pin || '';
            if (config.io_controller.traffic_lights.exit?.same_as_first) {
                document.getElementById('exitTLSameAsFirst').checked = true;
                toggleSameAsFirst('tl', 'exit');
            }
            const entryTLInfo = config.io_controller.traffic_lights.entry || {};
            const exitTLInfo = config.io_controller.traffic_lights.exit || {};
            applyTrafficLightValidatedFromConfig('entry', entryTLInfo.validated);
            applyTrafficLightValidatedFromConfig('exit', exitTLInfo.validated);
        }
        
        // Boom Barrier configuration
        if (config.io_controller.boom_barrier) {
            document.getElementById('bbMake').value = config.io_controller.boom_barrier.make || '';
            document.getElementById('bbModel').value = config.io_controller.boom_barrier.model || '';
            document.getElementById('boomOpenPin').value = config.io_controller.boom_barrier.open_pin || '';
            document.getElementById('boomClosePin').value = config.io_controller.boom_barrier.close_pin || '';
        }
        
        // Store a deep copy of the last-saved I/O config for change detection
        try {
            originalIoConfig = JSON.parse(JSON.stringify(config.io_controller));
            ioConfigDirty = false;
        } catch (e) {
            console.warn('[I/O Config] Failed to snapshot original config:', e);
            originalIoConfig = null;
            ioConfigDirty = false;
        }
        
        // Attach change listeners (idempotent – safe to call multiple times)
        initIoChangeDetection();
        
        toggleIOFields();
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
            const statusValue = completionStatus[key] !== undefined ? completionStatus[key] : (navSection === 'audio' ? completionStatus['voice'] : undefined);
            
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
    applyServerConfigDefaults();
    const { ip, port } = getServerConnectionSettings();
    
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
    const port = document.getElementById('rfidPort').value.trim();
    const mode = (document.getElementById('rfidModeSelect')?.value || 'CLIENT').toUpperCase();
    const rfidMake = document.getElementById('rfidMake')?.value.trim() || '';
    const rfidModel = document.getElementById('rfidModel')?.value.trim() || '';
    
    if (!ip || !port) {
        showToast('error', 'Validation Error', 'Please enter both IP and Port');
        return;
    }
    
    // Validate device info in production mode
    if (!validateDeviceInfo(rfidMake, rfidModel, 'RFID Reader')) {
        return;
    }
    
    // Show "Processing" status during connection
    showLoading(true);
    document.getElementById('rfidStatus').style.display = 'none';
    
    // Hide any existing timer display
    const timerDisplay = document.getElementById('rfidTimerDisplay');
    if (timerDisplay) {
        timerDisplay.style.display = 'none';
    }
    
    try {
        // Start the connection check (this will start the 30-second test if in CLIENT mode)
        const response = await fetch('/api/rfid/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, port, mode })
        });
        
        const result = await response.json();
        
        if (result.status === 200) {
            // Show "RFID connected" message
            showToast('success', 'RFID Connected', `RFID connected successfully. Mode: ${result.mode === 'CLIENT' ? 'RFID as Server, Application as Client' : 'Application as Server, RFID as Client'}`);
            
            // If in CLIENT mode, connection successful - now wait for RFID read
            if (result.mode === 'CLIENT') {
                // Connection successful - hide "Processing", show modal with timer
                showLoading(false);
                // Show modal and start polling for test status
                showRfidCardReadModal('CLIENT', ip, port);
                await pollRfidTestStatus(ip, port, rfidMake, rfidModel, result.mode);
            } else if (result.mode === 'SERVER') {
                // Server mode: Test runs in background thread (similar to CLIENT mode)
                showLoading(false);
                showRfidCardReadModal('SERVER', ip, port);
                await pollRfidTestStatus(ip, port, rfidMake, rfidModel, result.mode);
            }
        } else {
            showToast('error', 'Connection Failed', result.message);
            showLoading(false);
        }
    } catch (error) {
        console.error('[RFID Check] Error:', error);
        showToast('error', 'Connection Error', 'Unable to check RFID connection');
        showLoading(false);
    }
}

const MODULE_HELP_CONTENT = {
    server: {
        title: 'Server Configuration Help',
        html: `<h4>What to enter</h4><ul><li>Enter central server IP and port.</li><li>Use the same endpoint host used by production weighbridge app.</li></ul><h4>How to verify</h4><ul><li>Click <b>Check & Save</b>.</li><li>Status must show successful connectivity.</li></ul><h4>Common issues</h4><ul><li>Wrong subnet/VLAN routing.</li><li>Port blocked by firewall.</li></ul>`
    },
    rfid: {
        title: 'RFID Configuration Help',
        html: `<h4>What to Enter</h4><ul><li>RFID make and model number from the reader sticker.</li><li>RFID IP address and port number.</li><li>RFID connection mode.</li><li><b>RFID is Server, Application is Client:</b> the application continuously requests data from the reader.</li><li><b>RFID is Client, Application is Server:</b> the reader sends data to the application when a card is scanned (common in devices like Identium).</li></ul><h4>Validation Flow</h4><ul><li>Run <b>Check & Save</b>, then scan a card during the 30-second test window.</li><li>In the calibration popup, paste the RFID value shown in your RFID Reader application.</li><li>Click <b>Save Match</b>. The application verifies that the entered RFID exists in the raw data. This is a critical step; otherwise, truck validation can fail.</li></ul><h4>Tips</h4><ul><li>Make and model of the RFID reader are mandatory.</li><li>If RFID communication fails, first confirm that RFID data is visible in the RFID Reader application. Also enable options like heartbeat (or equivalent keep-alive) to ensure stable communication.</li></ul>`
    },
    camera: {
        title: 'Camera Configuration Help',
        html: `<h4>RTSP setup</h4><ul><li>Use full RTSP URL with credentials.</li><li>Configure both Top and Front cameras.</li></ul><h4>Validation</h4><ul><li>Click each camera <b>Check & Save</b>.</li><li>Live frame must appear in preview area.</li></ul>`
    },
    display: {
        title: 'Display Configuration Help',
        html: `<h4>Select Display Type</h4><p>Choose either <b>MQTT</b> or <b>API</b>.</p><h4>Method: MQTT</h4><ul><li>If MQTT is selected, click <b>Check & Save</b> and confirm the success toast.</li><li>On the display side, configure MQTT as:<br><br><b>Broker:</b> localhost:1883<br><b>Subscribe:</b> iot_display/application_to_display<br><b>Publish:</b> iot_display/display_to_application</li><li>When <b>Check & Save</b> is clicked, the application publishes to <code>iot_display/application_to_display</code>. The display must show this data and publish it back on <code>iot_display/display_to_application</code>.</li></ul><h4>Method: API</h4><ul><li><b>Option 1 (Display-hosted API):</b><br>If the API is hosted in the display device, click <b>Check & Save</b>. The application expects HTTP status <b>200</b>. If status 200 is not received, vendor should verify the API in Postman.</li><li><b>Option 2 (API hosted via IIS on Server/PC):</b><br>Set display port to <b>81</b>. Enter IP and Port in separate fields (example: IP <code>192.168.1.100</code>, Port <code>81</code>). Then click <b>Check & Save</b>. The application expects status <b>200</b>; otherwise vendor should verify the API in Postman.</li></ul>`
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

function showRfidCardReadModal(mode, ip, port) {
    console.log('[RFID Modal] Showing modal for mode:', mode);
    const modal = document.getElementById('rfidCardReadModal');
    if (!modal) {
        console.error('[RFID Modal] Modal element not found!');
        return;
    }
    
    const modeText = document.getElementById('rfidModalMode');
    const countdownEl = document.getElementById('rfidModalCountdown');
    const statusEl = document.getElementById('rfidModalStatus');
    const closeBtn = document.getElementById('rfidModalCloseBtn');
    
    if (!modeText || !countdownEl || !statusEl) {
        console.error('[RFID Modal] Modal elements not found!');
        return;
    }
    
    if (mode === 'CLIENT') {
        modeText.textContent = `RFID is connected, please scan card to validate`;
        countdownEl.textContent = '30';
    } else {
        modeText.textContent = `RFID will be connected after card is read. please scan card to validate`;
        countdownEl.textContent = '30';
    }
    
    // Reset status and show countdown
    statusEl.innerHTML = '<i class="bi bi-info-circle"></i> <span>Waiting for RFID card read...</span>';
    statusEl.style.color = '';
    if (countdownEl.parentElement) {
        countdownEl.parentElement.style.display = 'block';
    }
    closeBtn.style.display = 'none';
    
    // Show modal
    modal.classList.add('active');
    console.log('[RFID Modal] Modal shown');
}

function closeRfidCardReadModal() {
    const modal = document.getElementById('rfidCardReadModal');
    modal.classList.remove('active');
}

function updateRfidModalStatus(status, message, showClose = false) {
    const statusEl = document.getElementById('rfidModalStatus');
    const closeBtn = document.getElementById('rfidModalCloseBtn');
    const countdownEl = document.getElementById('rfidModalCountdown');
    
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
    
    if (showClose) {
        closeBtn.style.display = 'block';
    }
    
    // Hide countdown if test is complete
    if (status === 'success' || status === 'failed' || status === 'error') {
        countdownEl.parentElement.style.display = 'none';
    }
}

let pendingRfidCalibrationContext = null;

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
    if (modal) modal.classList.remove('active');
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

async function pollRfidTestStatus(ip, port, rfidMake, rfidModel, mode) {
    const countdownElement = document.getElementById('rfidModalCountdown');
    const maxTime = 30;  // Both CLIENT and SERVER modes use 30 seconds
    let pollInterval;
    
    // Poll for status every 500ms
    pollInterval = setInterval(async () => {
        try {
            const statusResponse = await fetch('/api/rfid/status');
            const status = await statusResponse.json();
            
            // Update countdown
            if (countdownElement && status.time_remaining !== undefined) {
                countdownElement.textContent = status.time_remaining;
            }
            
            // Check if test is complete
            if (status.test_complete === true) {
                clearInterval(pollInterval);
                // Cancel timeout since we have a final result
                if (rfidTestTimeout) {
                    clearTimeout(rfidTestTimeout);
                    rfidTestTimeout = null;
                }
                
                console.log('[RFID] Test complete detected, fetching final result...');
                
                // Small delay to ensure backend has updated the status
                await new Promise(resolve => setTimeout(resolve, 100));
                
                // Get final result - use status endpoint instead of check to avoid triggering new test
                // The status endpoint just returns current status without starting new test
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
                    if (finalResult.card_read === true) {
                        const successMsg = finalResult.message || "Reader Connected and Valid RFID received";
                        updateRfidModalStatus('success', successMsg, true);
                        closeRfidCardReadModal();
                        handleRfidResult(finalResult, ip, port, rfidMake, rfidModel);
                    } else {
                        const failedMsg = finalResult.message || "Reader Connected, but no card read";
                        updateRfidModalStatus('failed', failedMsg, true);
                        // Don't close modal automatically - let user close it
                        handleRfidResult(finalResult, ip, port, rfidMake, rfidModel);
                    }
                } else {
                    console.warn('[RFID] Final result says test not complete, waiting...');
                }
            }
        } catch (error) {
            console.error('[RFID Status Poll] Error:', error);
            clearInterval(pollInterval);
            updateRfidModalStatus('error', 'Error checking RFID status', true);
            showLoading(false);
        }
    }, 500);
    
    // Timeout after maxTime + 5 seconds (safety)
    rfidTestTimeout = setTimeout(() => {
        // If modal is already closed or test finished, do nothing
        const modal = document.getElementById('rfidCardReadModal');
        if (!modal || !modal.classList.contains('active')) {
            return;
        }
        clearInterval(pollInterval);
        if (countdownElement && countdownElement.textContent !== '0') {
            updateRfidModalStatus('error', 'Test timeout - Please try again', true);
        }
    }, (maxTime + 5) * 1000);
}

function handleRfidResult(result, ip, port, rfidMake, rfidModel) {
    showLoading(false);
    
    if (result.status === 200) {
        // Show detected mode
        document.getElementById('rfidStatus').style.display = 'flex';
        document.getElementById('rfidMode').textContent = result.mode === 'CLIENT' 
            ? 'Application as Client, RFID as Server' 
            : 'Application as Server, RFID as Client';
        
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
        await fetch('/api/config/rfid', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                ip, 
                port, 
                mode, 
                make: rfidMake,
                model: rfidModel,
                validated: validated,
                ...calibrationData
            })
        });
        
        // Only mark as validated and navigate if validated is true
        // This prevents navigation when RFID test fails or is incomplete
        if (validated === true) {
            console.log('[RFID] Config validated, marking section and navigating...');
            markSectionValidated('rfid');
            navigateToNext('rfid');
        } else {
            console.log('[RFID] Config saved but NOT validated - staying on RFID page');
            // Show status but don't navigate - user can try again
        }
    } catch (error) {
        console.error('[Save RFID Config] Error:', error);
        showToast('error', 'Error', 'Failed to save RFID configuration');
    }
}

// ============== Camera Configuration ==============
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
            const cameraMake = document.getElementById(cameraId + 'CameraMake')?.value || '';
            const cameraModel = document.getElementById(cameraId + 'CameraModel')?.value || '';
            
            await fetch('/api/config/camera', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    [cameraId]: { 
                        rtsp_url: rtspUrl, 
                        make: cameraMake,
                        model: cameraModel,
                        validated: true 
                    }
                })
            });
            
            showToast('success', 'Success', `${cameraId.charAt(0).toUpperCase() + cameraId.slice(1)} camera connected`);
            
            // Check if both cameras are validated
            await loadCompletionStatus();
        } else {
            showToast('error', 'Connection Failed', result.message);
        }
    } catch (error) {
        console.error('[Camera Check] Error:', error);
        showToast('error', 'Connection Error', 'Unable to check camera connection');
    } finally {
        showLoading(false);
    }
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
function getInputAddress(channelNumber) {
    return ioRegisterConfig.inputStartAddress + (parseInt(channelNumber) - 1);
}

function getOutputAddress(channelNumber) {
    const uiStartAddress = parseInt(document.getElementById('outputStartAddress')?.value);
    const outputStartAddress = Number.isNaN(uiStartAddress) ? ioRegisterConfig.outputStartAddress : uiStartAddress;
    return outputStartAddress + (parseInt(channelNumber) - 1);
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
    const relayType = document.getElementById('relayType').value;
    const tlInternal = document.getElementById('tlInternalRelay');
    const tlExternal = document.getElementById('tlExternalRelay');
    const bbInternal = document.getElementById('bbInternalRelay');
    const bbExternal = document.getElementById('bbExternalRelay');
    
    if (relayType === 'inbuilt') {
        tlInternal.style.display = 'block';
        tlExternal.style.display = 'none';
        bbInternal.style.display = 'block';
        bbExternal.style.display = 'none';
    } else {
        tlInternal.style.display = 'none';
        tlExternal.style.display = 'block';
        bbInternal.style.display = 'none';
        bbExternal.style.display = 'block';
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
    
    // Store register configuration
    ioRegisterConfig = {
        inputType: document.getElementById('inputRegisterType').value,
        inputStartAddress: parseInt(document.getElementById('inputStartAddress').value) || 0,
        outputType: document.getElementById('outputRegisterType').value,
        outputStartAddress: parseInt(document.getElementById('outputStartAddress').value) || 0
    };
    
    let connectionData = { type: ioType, slave_id: slaveId };
    
    if (ioType === 'ethernet') {
        const isManual = document.getElementById('ioIpManual')?.checked;
        connectionData.ip = isManual 
            ? document.getElementById('ioIp').value.trim()
            : (document.getElementById('ioIpSelect')?.value || document.getElementById('ioIp').value.trim());
        connectionData.port = document.getElementById('ioPort').value.trim();
        
        if (!connectionData.ip) {
            showToast('error', 'Validation Error', 'Please enter IP Address');
            return;
        }
    } else {
        connectionData.serial_port = document.getElementById('ioSerialPort').value;
        connectionData.baud_rate = document.getElementById('ioBaudRate').value;
        
        if (!connectionData.serial_port) {
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
            showToast('success', 'Connected', result.message + ` | Input starts at ${ioRegisterConfig.inputStartAddress}, Output starts at ${ioRegisterConfig.outputStartAddress}`);
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

// Initialize change detection for I/O controller fields.
// Safe to call multiple times; listeners will only be attached once per element.
function initIoChangeDetection() {
    const ioFieldIds = [
        'ioType', 'ioSlaveId',
        'ioIp', 'ioPort',
        'ioSerialPort', 'ioBaudRate',
        'inputRegisterType', 'inputStartAddress',
        'outputRegisterType', 'outputStartAddress',
        'relayType',
        'ioMake', 'ioModel',
        'sensor1Pin', 'sensor1DefaultSignal', 'sensor1Make', 'sensor1Model',
        'sensor2Pin', 'sensor2DefaultSignal', 'sensor2Make', 'sensor2Model', 'sensor2SameAsFirst',
        'sensor3Pin', 'sensor3DefaultSignal', 'sensor3Make', 'sensor3Model', 'sensor3SameAsFirst',
        'entryTLMake', 'entryTLModel', 'entryRedPin', 'entryGreenPin',
        'exitTLMake', 'exitTLModel', 'exitRedPin', 'exitGreenPin', 'exitTLSameAsFirst',
        'bbMake', 'bbModel', 'boomOpenPin', 'boomClosePin',
        // External relay fields (if present)
        'entryTLPin', 'exitTLPin',
        'boomPin', 'bbExtMake', 'bbExtModel'
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

function boomLog(phase, details = {}) {
    console.log(`[BOOM][${phase}]`, details);
}

function getIoOutputMode() {
    // Prefer new UI id if present; fallback to legacy relayType mapping.
    const outputModeEl = document.getElementById('outputMode');
    if (outputModeEl && outputModeEl.value) return outputModeEl.value; // 'direct' | 'relay'

    const relayTypeEl = document.getElementById('relayType');
    if (relayTypeEl && relayTypeEl.value) {
        return relayTypeEl.value === 'inbuilt' ? 'direct' : 'relay';
    }
    return 'direct';
}

function handleIoFieldChanged(event) {
    // Only mark dirty once per load/reset
    if (ioConfigDirty) {
        return;
    }

    ioConfigDirty = true;

    const changedId = event?.target?.id || '';
    boomLog('FIELD_CHANGED', { changedId });

    const boomFields = new Set([
        'entryBoomEnabled', 'exitBoomEnabled',
        'entryBoomOpenPin', 'entryBoomClosePin', 'exitBoomOpenPin', 'exitBoomClosePin',
        'entryBoomRelayEnabled', 'exitBoomRelayEnabled',
        'entryBoomRelayPin', 'exitBoomRelayPin',
        'entryBBMake', 'entryBBModel', 'exitBBMake', 'exitBBModel',
        'boomBarrierMake', 'boomBarrierModel',
        // legacy ids still treated as boom-related
        'bbMake', 'bbModel', 'bbExtMake', 'bbExtModel', 'boomOpenPin', 'boomClosePin', 'boomPin'
    ]);
    const trafficFields = new Set([
        'entryRedPin', 'entryGreenPin', 'exitRedPin', 'exitGreenPin',
        'entryTLRelayPin', 'exitTLRelayPin',
        'entryTLMake', 'entryTLModel', 'exitTLMake', 'exitTLModel',
        // legacy ids
        'entryTLPin', 'exitTLPin'
    ]);
    const sensorFields = new Set([
        'sensor1Pin', 'sensor2Pin', 'sensor3Pin',
        'sensor1DefaultSignal', 'sensor2DefaultSignal', 'sensor3DefaultSignal',
        'sensor1Make', 'sensor1Model', 'sensor2Make', 'sensor2Model', 'sensor3Make', 'sensor3Model'
    ]);

    if (boomFields.has(changedId)) {
        const isEntryField = changedId.startsWith('entry');
        const isExitField = changedId.startsWith('exit');
        const isGlobalBoomField =
            changedId === 'boomBarrierMake' ||
            changedId === 'boomBarrierModel' ||
            changedId === 'outputMode' ||
            changedId === 'relayType';

        if (isEntryField) {
            ioTestStatus.entryBBDirect = false;
            ioTestStatus.entryBBRelay = false;
            ioTestStatus.entryBBDirectOpen = false;
            ioTestStatus.entryBBDirectClose = false;
            ioTestStatus.entryBBRelayOpen = false;
            ioTestStatus.entryBBRelayClose = false;
        } else if (isExitField) {
            ioTestStatus.exitBBDirect = false;
            ioTestStatus.exitBBRelay = false;
            ioTestStatus.exitBBDirectOpen = false;
            ioTestStatus.exitBBDirectClose = false;
            ioTestStatus.exitBBRelayOpen = false;
            ioTestStatus.exitBBRelayClose = false;
        } else if (isGlobalBoomField) {
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
            ioTestStatus.entryBBDirectOpen && ioTestStatus.entryBBDirectClose ||
            ioTestStatus.exitBBDirectOpen && ioTestStatus.exitBBDirectClose ||
            ioTestStatus.entryBBRelayOpen && ioTestStatus.entryBBRelayClose ||
            ioTestStatus.exitBBRelayOpen && ioTestStatus.exitBBRelayClose;

        boomLog('RESET_BOOM_TEST_STATE', {
            changedId,
            entryBBDirectOpen: ioTestStatus.entryBBDirectOpen,
            entryBBDirectClose: ioTestStatus.entryBBDirectClose,
            exitBBDirectOpen: ioTestStatus.exitBBDirectOpen,
            exitBBDirectClose: ioTestStatus.exitBBDirectClose,
            entryBBRelayOpen: ioTestStatus.entryBBRelayOpen,
            entryBBRelayClose: ioTestStatus.entryBBRelayClose,
            exitBBRelayOpen: ioTestStatus.exitBBRelayOpen,
            exitBBRelayClose: ioTestStatus.exitBBRelayClose
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
    
    if (!channelNum) {
        showToast('error', 'Missing Channel', `Please enter channel number for ${getSensorRoleLabel(sensorNum)}`);
        return;
    }
    
    const slaveId = document.getElementById('ioSlaveId').value;
    const expectedDefault = defaultSignal === 'high';
    const registerAddress = getInputAddress(channelNum);
    const inputRegisterType = document.getElementById('inputRegisterType')?.value || ioRegisterConfig.inputType || 'discrete';
    const functionCode = inputRegisterType === 'coil' ? 1 : 2;
    
    statusEl.textContent = 'Testing...';
    statusEl.className = 'device-status testing';
    
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
        
        // Step 2: Ask user to trigger the sensor
        const triggerConfirm = confirm(`${getSensorRoleLabel(sensorNum)} (address ${registerAddress}) default state verified (${defaultSignal.toUpperCase()}).\n\nNow please TRIGGER the sensor (cut/activate it) and click OK.`);
        
        if (!triggerConfirm) {
            statusEl.textContent = 'Cancelled';
            statusEl.className = 'device-status';
            resetDeviceStatus('sensor', sensorNum);
            return;
        }
        
        // Step 3: Check triggered state
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
    
    if (!channelNum) {
        showToast('error', 'Missing Channel', `Please enter channel number for ${location} ${color} light`);
        return;
    }
    
    const registerAddress = getOutputAddress(channelNum);
    
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
        
        // Step 2: Ask user to verify
        const verified = confirm(`${location.charAt(0).toUpperCase() + location.slice(1)} ${color.toUpperCase()} light turned ON (address ${registerAddress}).\n\nIs the ${color} light ON?\n\nClick OK if YES, Cancel if NO.`);
        
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
    if (!channelNum) {
        showToast('error', 'Missing Channel', `Please enter channel number for ${location} traffic light`);
        return;
    }
    
    const registerAddress = getOutputAddress(channelNum);
    
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
        
        // Step 2: Ask user to verify
        const verified = confirm(`${location.charAt(0).toUpperCase() + location.slice(1)} Traffic Light relay turned ON (address ${registerAddress}).\n\nDid the traffic light change?\n\nClick OK if YES, Cancel if NO.`);
        
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
            showToast('success', 'Test Passed', `${location} traffic light working!`);
        } else {
            statusEl.textContent = 'Failed';
            statusEl.className = 'device-status error';
            resetDeviceStatus('trafficLight', location);
            showToast('error', 'Test Failed', `${location} traffic light not responding`);
        }
        
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
        if (!channelNum) {
            showToast('error', 'Missing Channel', 'Please enter channel number for boom barrier');
            return;
        }
    } else {
        // Internal relay: separate pins for open and close
        channelNum = action === 'open' ? document.getElementById('boomOpenPin').value : document.getElementById('boomClosePin').value;
        if (!channelNum) {
            showToast('error', 'Missing Channel', `Please enter ${action} channel number for boom barrier`);
            return;
        }
    }
    
    const statusEl = document.getElementById(statusElId);
    statusEl.textContent = `${action}ing...`;
    statusEl.className = 'device-status testing';
    
    const registerAddress = getOutputAddress(channelNum);
    
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
        
        // Step 2: Ask user to verify
        const verified = confirm(`Boom Barrier ${action.toUpperCase()} command sent (relay ON at address ${registerAddress}).\n\nDid the boom barrier ${action}?\n\nClick OK if YES, Cancel if NO.`);
        
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
            // Legacy single-pin boom test: treat as relay-mode action for overall validation
            ioTestStatus[`entryBBRelay${action === 'open' ? 'Open' : 'Close'}`] = true;
            ioTestStatus.boomBarrier = ioTestStatus.entryBBRelayOpen && ioTestStatus.entryBBRelayClose;
            showToast('success', 'Test Passed', `Boom barrier ${action} working!`);
        } else {
            statusEl.textContent = 'Failed';
            statusEl.className = 'device-status error';
            resetDeviceStatus('boomBarrier', action);
            showToast('error', 'Test Failed', `Boom barrier ${action} not responding`);
        }
        
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
            ioTestStatus[`${identifier}BBDirect`] = false;
            ioTestStatus[`${identifier}BBRelay`] = false;
            ioTestStatus[`${identifier}BBDirectOpen`] = false;
            ioTestStatus[`${identifier}BBDirectClose`] = false;
            ioTestStatus[`${identifier}BBRelayOpen`] = false;
            ioTestStatus[`${identifier}BBRelayClose`] = false;
        } else {
            ioTestStatus.boomBarrier = false;
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
    if (!isBoomBarrierValidationRequired(outputMode)) return true;
    if (outputMode === 'direct') {
        const entryEnabled = document.getElementById('entryBoomEnabled')?.checked || false;
        const exitEnabled = document.getElementById('exitBoomEnabled')?.checked || false;
        const entryPassed = ioTestStatus.entryBBDirectOpen && ioTestStatus.entryBBDirectClose;
        const exitPassed = ioTestStatus.exitBBDirectOpen && ioTestStatus.exitBBDirectClose;
        const passed = (!entryEnabled || entryPassed) && (!exitEnabled || exitPassed);
        boomLog('VALIDATION_CHECK_DIRECT', {
            entryEnabled, exitEnabled,
            entryBBDirectOpen: ioTestStatus.entryBBDirectOpen,
            entryBBDirectClose: ioTestStatus.entryBBDirectClose,
            exitBBDirectOpen: ioTestStatus.exitBBDirectOpen,
            exitBBDirectClose: ioTestStatus.exitBBDirectClose,
            passed
        });
        return passed;
    }
    const entryEnabled = document.getElementById('entryBoomRelayEnabled')?.checked || false;
    const exitEnabled = document.getElementById('exitBoomRelayEnabled')?.checked || false;
    const entryPassed = ioTestStatus.entryBBRelayOpen && ioTestStatus.entryBBRelayClose;
    const exitPassed = ioTestStatus.exitBBRelayOpen && ioTestStatus.exitBBRelayClose;
    const passed = (!entryEnabled || entryPassed) && (!exitEnabled || exitPassed);
    boomLog('VALIDATION_CHECK_RELAY', {
        entryEnabled, exitEnabled,
        entryBBRelayOpen: ioTestStatus.entryBBRelayOpen,
        entryBBRelayClose: ioTestStatus.entryBBRelayClose,
        exitBBRelayOpen: ioTestStatus.exitBBRelayOpen,
        exitBBRelayClose: ioTestStatus.exitBBRelayClose,
        passed
    });
    return passed;
}

async function saveIOConfig() {
    const ioType = document.getElementById('ioType').value;
    const slaveId = document.getElementById('ioSlaveId').value;
    const relayType = document.getElementById('relayType').value;
    const ioMake = document.getElementById('ioMake')?.value.trim() || '';
    const ioModel = document.getElementById('ioModel')?.value.trim() || '';
    
    // Validate I/O controller device info in production mode
    if (!validateDeviceInfo(ioMake, ioModel, 'I/O Controller')) {
        return;
    }

    const outputMode = getIoOutputMode();
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
    
    // Get sensor make/model (use first sensor's values if "same as first" is checked)
    const getSensorMakeModel = (num) => {
        const sameAsFirst = document.getElementById(`sensor${num}SameAsFirst`)?.checked;
        if (num > 1 && sameAsFirst) {
            return {
                make: document.getElementById('sensor1Make')?.value || '',
                model: document.getElementById('sensor1Model')?.value || '',
                same_as_first: true
            };
        }
        return {
            make: document.getElementById(`sensor${num}Make`)?.value || '',
            model: document.getElementById(`sensor${num}Model`)?.value || '',
            same_as_first: false
        };
    };
    
    let configData = {
        type: ioType,
        slave_id: slaveId,
        relay_type: relayType,
        make: document.getElementById('ioMake')?.value || '',
        model: document.getElementById('ioModel')?.value || '',
        sensors: {
            entry_sensor: {
                pin: document.getElementById('sensor1Pin').value,
                default_signal: document.getElementById('sensor1DefaultSignal').value,
                ...getSensorMakeModel(1),
                validated: getSensorValidatedForSave(1)
            },
            wb_sensor: {
                pin: document.getElementById('sensor2Pin').value,
                default_signal: document.getElementById('sensor2DefaultSignal').value,
                ...getSensorMakeModel(2),
                validated: getSensor2ValidatedForSave()
            },
            exit_sensor: {
                pin: document.getElementById('sensor3Pin').value,
                default_signal: document.getElementById('sensor3DefaultSignal').value,
                ...getSensorMakeModel(3),
                validated: getSensorValidatedForSave(3)
            }
        },
        traffic_lights: {},
        boom_barrier: {},
        validated: true
    };
    
    // Add connection info
    if (ioType === 'ethernet') {
        const isManual = document.getElementById('ioIpManual')?.checked;
        configData.ip = isManual 
            ? document.getElementById('ioIp').value.trim()
            : (document.getElementById('ioIpSelect')?.value || document.getElementById('ioIp').value.trim());
        configData.port = document.getElementById('ioPort').value.trim();
    } else {
        configData.serial_port = document.getElementById('ioSerialPort').value;
        configData.baud_rate = document.getElementById('ioBaudRate').value;
    }
    
    // Get TL make/model (use entry's values if "same as first" is checked for exit)
    const getExitTLMakeModel = () => {
        const sameAsFirst = document.getElementById('exitTLSameAsFirst')?.checked;
        if (sameAsFirst) {
            return {
                make: document.getElementById('entryTLMake')?.value || '',
                model: document.getElementById('entryTLModel')?.value || '',
                same_as_first: true
            };
        }
        return {
            make: document.getElementById('exitTLMake')?.value || '',
            model: document.getElementById('exitTLModel')?.value || '',
            same_as_first: false
        };
    };
    
    // Add relay config based on type
    if (relayType === 'inbuilt') {
        configData.traffic_lights = {
            entry: {
                red_pin: document.getElementById('entryRedPin').value,
                green_pin: document.getElementById('entryGreenPin').value,
                make: document.getElementById('entryTLMake')?.value || '',
                model: document.getElementById('entryTLModel')?.value || '',
                validated: getTrafficLightValidatedForSave('entry')
            },
            exit: {
                red_pin: document.getElementById('exitRedPin').value,
                green_pin: document.getElementById('exitGreenPin').value,
                ...getExitTLMakeModel(),
                validated: getTrafficLightValidatedForSave('exit')
            }
        };
        configData.boom_barrier = {
            open_pin: document.getElementById('boomOpenPin').value,
            close_pin: document.getElementById('boomClosePin').value,
            make: document.getElementById('bbMake')?.value || '',
            model: document.getElementById('bbModel')?.value || '',
            tested: ioTestStatus.boomBarrier
        };
    } else {
        configData.traffic_lights = {
            entry: { 
                pin: document.getElementById('entryTLPin').value,
                make: document.getElementById('entryTLMake')?.value || '',
                model: document.getElementById('entryTLModel')?.value || '',
                validated: getTrafficLightValidatedForSave('entry')
            },
            exit: { 
                pin: document.getElementById('exitTLPin').value,
                ...getExitTLMakeModel(),
                validated: getTrafficLightValidatedForSave('exit')
            }
        };
        configData.boom_barrier = {
            pin: document.getElementById('boomPin').value,
            make: document.getElementById('bbExtMake')?.value || '',
            model: document.getElementById('bbExtModel')?.value || '',
            tested: ioTestStatus.boomBarrier
        };
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
    const finalizeSave = async (method, indexing, sampleHex) => {
        const port = document.getElementById('digitizerPort')?.value || '';
        const baudRate = document.getElementById('digitizerBaud')?.value || '9600';
        const dataBits = document.getElementById('digitizerDataBits')?.value || '8';
        const parity = document.getElementById('digitizerParity')?.value || 'N';
        const stopBits = document.getElementById('digitizerStopBits')?.value || '1';
        const make = document.getElementById('digitizerMake')?.value || '';
        const model = document.getElementById('digitizerModel')?.value || '';

        const timeout = document.getElementById('digitizerTimeout')?.value?.trim() || '10';
        const stableCount = document.getElementById('digitizerStableCount')?.value?.trim() || '5';

        const payload = {
            port,
            baud_rate: baudRate,
            bytesize: dataBits,
            parity: parity,
            stopbits: stopBits,
            timeout,
            stable_count: stableCount,
            make: make,
            model: model,
            validated: true,
            conversion_method: method,
            indexing: indexing,
        };
        if (sampleHex) {
            payload.calibration_sample_hex = sampleHex;
        }

        await fetch('/api/config/digitizer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        if (typeof updateDigitizerSavedConfig === 'function') {
            updateDigitizerSavedConfig(payload);
        }
        showToast('success', 'Success', 'Digitizer weight parsing saved.');
        markSectionValidated('digitizer');
        navigateToNext('digitizer');
    };

    await runDigitizerIndexCheckAndSave(finalizeSave);
}

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
        'io_controller': 'io_controller'
    };
    const configSection = sectionMap[section] || section;
    
    // Mark as not validated
    completionStatus[configSection] = false;
    
    // Update all_complete status
    const sections = getWizardCompletionSections();
    completionStatus.all_complete = sections.every(s => completionStatus[s]);
    
    // Update UI
    updateCompletionStatus();
    // Also refresh sidebar validation icons
    if (typeof updateValidationUI === 'function') {
        updateValidationUI();
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
        
        // Mark section as skipped in local state
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
document.getElementById('finishBtn').addEventListener('click', function() {
    // Open the finish modal instead of directly finishing
    openFinishModal();
});

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

function openImportConfigModal() {
    const modal = document.getElementById('importConfigModal');
    const fileEl = document.getElementById('importConfigFile');
    if (fileEl) fileEl.value = '';
    modal.classList.add('active');
}

function closeImportConfigModal() {
    const modal = document.getElementById('importConfigModal');
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
            
            // Generate and download PDF report (API returns JSON with base64 PDF, not raw bytes)
            let pdfDownloadSucceeded = false;
            try {
                const pdfResponse = await fetch('/api/generate-pdf-report', { method: 'POST' });
                const contentType = (pdfResponse.headers.get('Content-Type') || '').toLowerCase();

                const showPdfFailure = (detail) => {
                    const msg = detail || 'Configuration saved but PDF report could not be generated';
                    console.error('PDF generation error:', detail);
                    showToast('warning', 'PDF Generation Failed', msg);
                };

                if (pdfResponse.ok && contentType.includes('application/json')) {
                    const data = await pdfResponse.json();
                    if (data.status === 200 && data.data) {
                        const bin = atob(data.data);
                        const bytes = new Uint8Array(bin.length);
                        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                        const pdfBlob = new Blob([bytes], { type: data.mime_type || 'application/pdf' });
                        let filename = data.filename || `IoT_Configuration_Report_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)}.pdf`;

                        const url = window.URL.createObjectURL(pdfBlob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = filename;
                        a.style.display = 'none';
                        document.body.appendChild(a);
                        a.click();
                        setTimeout(() => {
                            document.body.removeChild(a);
                            window.URL.revokeObjectURL(url);
                        }, 100);

                        pdfDownloadSucceeded = true;
                        showToast('success', 'PDF Generated', 'Configuration report PDF has been downloaded');
                    } else {
                        showPdfFailure(data.message);
                    }
                } else if (pdfResponse.ok) {
                    const pdfBlob = await pdfResponse.blob();
                    let filename = `IoT_Configuration_Report_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)}.pdf`;
                    const contentDisposition = pdfResponse.headers.get('Content-Disposition');
                    if (contentDisposition) {
                        const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                        if (filenameMatch && filenameMatch[1]) {
                            filename = filenameMatch[1].replace(/['"]/g, '');
                        }
                    }
                    const url = window.URL.createObjectURL(pdfBlob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = filename;
                    a.style.display = 'none';
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(() => {
                        document.body.removeChild(a);
                        window.URL.revokeObjectURL(url);
                    }, 100);
                    pdfDownloadSucceeded = true;
                    showToast('success', 'PDF Generated', 'Configuration report PDF has been downloaded');
                } else {
                    let errDetail = null;
                    try {
                        const errorData = await pdfResponse.json();
                        errDetail = errorData.message || null;
                    } catch (_) { /* ignore */ }
                    showPdfFailure(errDetail);
                }
            } catch (pdfError) {
                console.error('Error generating PDF:', pdfError);
                showToast('warning', 'PDF Generation Failed', pdfError.message || 'Configuration saved but PDF report could not be generated');
            } finally {
                // Hide loading overlay after PDF generation completes
                showLoading(false);
            }
            
            // Show completion message and close application after OK is clicked
            setTimeout(() => {
                    const pdfNote = pdfDownloadSucceeded
                        ? 'PDF report has been downloaded.'
                        : 'PDF report could not be generated; your configuration file was still saved.';
                    alert(`Configuration completed successfully!\n\nVerified by: ${verifiedBy}\n\nConfiguration saved to: ${result.file}\n\n${pdfNote}`);
                
                // Close the application after alert is confirmed
                fetch('/api/close', { method: 'POST' })
                    .then(() => {
                        // Give a moment for the close request to process
                        setTimeout(() => {
                            window.close();
                        }, 100);
                    })
                    .catch(err => {
                        console.error('Error closing application:', err);
                        // Fallback: try to close window directly
                        window.close();
                    });
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

document.getElementById('importConfigModal')?.addEventListener('click', function(e) {
    if (e.target === this) {
        closeImportConfigModal();
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
// Timeout handle for RFID card-read test, so we can cancel it on success
let rfidTestTimeout = null;

function showToast(type, title, message) {
    const ribbon = document.getElementById('notificationRibbon');
    const icon = document.getElementById('notifIcon');
    const text = document.getElementById('notifText');
    
    // Clear any existing timeout
    if (notificationTimeout) {
        clearTimeout(notificationTimeout);
    }
    
    // Set icon based on type
    const icons = {
        success: 'bi-check-circle-fill',
        error: 'bi-x-circle-fill',
        warning: 'bi-exclamation-triangle-fill'
    };
    
    const rawMessage = String(message || '');
    const installerMessage = (type === 'error' && !APP_CONFIG.debug)
        ? simplifyErrorMessage(rawMessage)
        : rawMessage;
    icon.className = 'bi ' + icons[type];
    text.textContent = installerMessage;
    
    // Set ribbon type
    ribbon.className = 'notification-ribbon ' + type;
    
    // Show ribbon
    setTimeout(() => {
        ribbon.classList.add('show');
    }, 10);
    
    // Auto hide after 5 seconds
    notificationTimeout = setTimeout(() => {
        hideNotification();
    }, 5000);

    if (type === 'error' && APP_CONFIG.debug) {
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

