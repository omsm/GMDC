// Bidirectional weighbridge extensions (loaded after devices.js)

let currentRfidDirectionKey = null;

const BIDIRECTIONAL_ENTRY_KEYS = ['entry_a', 'entry_b'];
const BIDIRECTIONAL_ENTRY_LABELS = { entry_a: 'ENTRY A', entry_b: 'ENTRY B' };

const BIDIRECTIONAL_ENTRY_UI = {
    entry_a: { prefix: 'rfidA', assignKey: 'rfid_entry_a', label: 'ENTRY A' },
    entry_b: { prefix: 'rfidB', assignKey: 'rfid_entry_b', label: 'ENTRY B' }
};
/** @deprecated use BIDIRECTIONAL_ENTRY_UI */
const RFID_DIRECTION_UI = BIDIRECTIONAL_ENTRY_UI;

function bidirectionalEntryLabel(entryKey) {
    return BIDIRECTIONAL_ENTRY_LABELS[entryKey] || entryKey;
}

function tlIdPrefix(entryKey) {
    if (!entryKey) return '';
    return entryKey === 'entry_a' ? 'directionA' : 'directionB';
}

function getTlValidatedStateKey(directionKey, location) {
    if (!directionKey) return location === 'entry' ? 'entryTLValidated' : 'exitTLValidated';
    return `${directionKey}_${location}TLValidated`;
}

function getTlGateStateKey(directionKey, location) {
    if (!directionKey) return location === 'entry' ? 'entryTL' : 'exitTL';
    return `${directionKey}_${location}TL`;
}

function getTlStatusElementIds(directionKey, location) {
    if (!directionKey) {
        return location === 'entry'
            ? ['entryTLStatus', 'entryTLRelayStatus', 'entryTLExtStatus']
            : ['exitTLStatus', 'exitTLRelayStatus', 'exitTLExtStatus'];
    }
    const p = tlIdPrefix(directionKey);
    return [`${p}_${location}TLStatus`, `${p}_${location}TLRelayStatus`];
}

function getTlPinElementId(directionKey, location, color) {
    const colorCap = color.charAt(0).toUpperCase() + color.slice(1);
    if (!directionKey) return `${location}${colorCap}Pin`;
    return `${tlIdPrefix(directionKey)}_${location}${colorCap}Pin`;
}

function getRfidFieldIds(directionKey) {
    if (!directionKey) {
        return {
            make: 'rfidMake', model: 'rfidModel', ipSelect: 'rfidIpSelect', ipManual: 'rfidIpManual',
            ip: 'rfidIp', port: 'rfidPort', modeSelect: 'rfidModeSelect', status: 'rfidStatus', mode: 'rfidMode',
            username: 'rfidUsername', password: 'rfidPassword', apiCreds: 'rfidApiCreds', portGroup: 'rfidPortGroup',
            apiPort: 'rfidApiPort', apiPortGroup: 'rfidApiPortGroup'
        };
    }
    const p = RFID_DIRECTION_UI[directionKey]?.prefix;
    return {
        make: `${p}Make`, model: `${p}Model`, ipSelect: `${p}IpSelect`, ipManual: `${p}IpManual`,
        ip: `${p}Ip`, port: `${p}Port`, modeSelect: `${p}ModeSelect`, status: `${p}Status`, mode: `${p}Mode`,
        username: `${p}Username`, password: `${p}Password`, apiCreds: `${p}ApiCreds`, portGroup: `${p}PortGroup`,
        apiPort: `${p}ApiPort`, apiPortGroup: `${p}ApiPortGroup`
    };
}

function rfidModeStatusLabel(mode) {
    const m = String(mode || '').toUpperCase();
    if (m === 'API') return 'API';
    if (m === 'CLIENT') return 'Application as Client, RFID as Server';
    if (m === 'SERVER') return 'Application as Server, RFID as Client';
    return m || '-';
}

function onRfidDirectionModeChange(directionKey) {
    const ids = getRfidFieldIds(directionKey);
    const mode = (document.getElementById(ids.modeSelect)?.value || 'API').toUpperCase();
    const apiCreds = document.getElementById(ids.apiCreds);
    const portGroup = document.getElementById(ids.portGroup);
    const apiPortGroup = document.getElementById(ids.apiPortGroup);
    if (apiCreds) apiCreds.style.display = mode === 'API' ? '' : 'none';
    if (portGroup) portGroup.style.display = mode === 'API' ? 'none' : '';
    if (apiPortGroup) apiPortGroup.style.display = mode === 'API' ? '' : 'none';
}

function applyWeighbridgeLayoutUI() {
    const bi = typeof isBidirectionalLayout === 'function' && isBidirectionalLayout();
    const setDisplay = (id, show) => {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? '' : 'none';
    };
    setDisplay('rfidUnidirectionalBlock', !bi);
    setDisplay('rfidBidirectionalBlock', bi);
    if (typeof applyTrafficLightModeLayout === 'function') applyTrafficLightModeLayout();
    if (typeof applyCameraUiForProfile === 'function') applyCameraUiForProfile();
    const navLabel = document.getElementById('navRfidLabel');
    if (navLabel) navLabel.textContent = bi ? 'RFID Readers' : 'RFID Reader';
    if (bi) {
        onRfidDirectionModeChange('entry_a');
        onRfidDirectionModeChange('entry_b');
    } else if (typeof onRfidModeChange === 'function') {
        onRfidModeChange();
    }
    if (typeof syncVisibleIoEnableToggles === 'function') syncVisibleIoEnableToggles();
}

function syncWeighbridgeLayoutFromConfig() {
    const layout = config?.wb_type || config?.weighbridge_layout
        || (typeof getWeighbridgeLayout === 'function' ? getWeighbridgeLayout() : 'unidirectional');
    sessionStorage.setItem('wbType', layout);
    if (window.APP_CONFIG) window.APP_CONFIG.wbType = layout;
}

function resetLayoutDependentTestState() {
    if (typeof ioTestStatus === 'undefined') return;
    ioTestStatus.sensor1 = false;
    ioTestStatus.sensor1Validated = false;
    ioTestStatus.sensor2 = false;
    ioTestStatus.sensor2Validated = false;
    ioTestStatus.sensor3 = false;
    ioTestStatus.sensor3Validated = false;
    ioTestStatus.entryTL = false;
    ioTestStatus.entryTLValidated = false;
    ioTestStatus.exitTL = false;
    ioTestStatus.exitTLValidated = false;
    ['entry_a', 'entry_b'].forEach((dir) => {
        ['entry', 'exit'].forEach((loc) => {
            ioTestStatus[`${dir}_${loc}TL`] = false;
            ioTestStatus[`${dir}_${loc}TLValidated`] = false;
        });
    });
    if (typeof markSectionNotValidated === 'function') {
        markSectionNotValidated('rfid');
        markSectionNotValidated('io-controller');
    }
    if (typeof loadCompletionStatus === 'function') {
        loadCompletionStatus();
    }
}

function getRfidDirectionIpFromForm(directionKey) {
    const ids = getRfidFieldIds(directionKey);
    const isManual = document.getElementById(ids.ipManual)?.checked;
    if (isManual) {
        return document.getElementById(ids.ip)?.value.trim() || '';
    }
    return (
        document.getElementById(ids.ipSelect)?.value
        || document.getElementById(ids.ip)?.value.trim()
        || ''
    );
}

function setRfidDirectionIpField(directionKey, ip) {
    if (!ip) return;
    const ids = getRfidFieldIds(directionKey);
    const selectEl = document.getElementById(ids.ipSelect);
    const ipEl = document.getElementById(ids.ip);
    const manualCb = document.getElementById(ids.ipManual);
    const fieldBase = ids.ip;
    let inSelect = false;
    if (selectEl) {
        inSelect = Array.from(selectEl.options).some((o) => o.value === ip);
        if (inSelect) selectEl.value = ip;
    }
    if (manualCb && ipEl) {
        if (inSelect) {
            manualCb.checked = false;
            ipEl.value = ip;
        } else {
            manualCb.checked = true;
            ipEl.value = ip;
        }
        if (typeof toggleManualInput === 'function') {
            toggleManualInput(fieldBase);
        }
    }
}

function readRfidDirectionFromForm(directionKey, options = {}) {
    const { validatedOverride } = options;
    const ids = getRfidFieldIds(directionKey);
    const ip = getRfidDirectionIpFromForm(directionKey);
    const mode = (document.getElementById(ids.modeSelect)?.value || 'API').toUpperCase();
    const port = (document.getElementById(ids.port)?.value || (mode === 'API' ? '443' : '6000')).trim();
    const apiPort = (document.getElementById(ids.apiPort)?.value || '').trim();
    const make = document.getElementById(ids.make)?.value.trim() || '';
    const model = document.getElementById(ids.model)?.value.trim() || '';
    const username = document.getElementById(ids.username)?.value.trim() || 'admin';
    const password = document.getElementById(ids.password)?.value || '';
    const existing = (config.rfids && config.rfids[directionKey]) || {};
    const validated = validatedOverride !== undefined ? validatedOverride : existing.validated;
    const extra = {
        username,
        password,
        note: existing.note || (
            mode === 'API'
                ? 'API mode: tags via POST /rfid_data; cloud login/mode/start/stop via HTTPS'
                : undefined
        ),
        manual_match_start: existing.manual_match_start,
        manual_match_length: existing.manual_match_length,
        manual_match_sample: existing.manual_match_sample
    };
    if (mode === 'API' && apiPort) {
        extra.api_port = apiPort;
    } else if (existing.api_port != null) {
        extra.api_port = existing.api_port;
    }
    return buildOrderedRfidReader(ip, port, mode, make, model, validated, extra);
}

function buildBidirectionalRfidsPayload(activeDirectionKey, activeReader) {
    return {
        entry_a: activeDirectionKey === 'entry_a'
            ? activeReader
            : readRfidDirectionFromForm('entry_a'),
        entry_b: activeDirectionKey === 'entry_b'
            ? activeReader
            : readRfidDirectionFromForm('entry_b')
    };
}

function applyBidirectionalRfidValidatedFromConfig(directionKey, validated, mode) {
    const ids = getRfidFieldIds(directionKey);
    const statusEl = document.getElementById(ids.status);
    const modeEl = document.getElementById(ids.mode);
    if (validated === true) {
        if (statusEl) statusEl.style.display = 'flex';
        if (modeEl && mode) modeEl.textContent = rfidModeStatusLabel(mode);
    } else if (validated === false || validated == null) {
        if (statusEl) statusEl.style.display = 'none';
        if (modeEl) modeEl.textContent = '-';
    }
}

function updateBidirectionalRfidSectionCompletion() {
    if (!isBidirectionalLayout() || !config.rfids) return;
    const aOk = config.rfids.entry_a?.validated === true;
    const bOk = config.rfids.entry_b?.validated === true;
    if (aOk && bOk) {
        if (typeof markSectionValidated === 'function') markSectionValidated('rfid');
    } else if (typeof markSectionNotValidated === 'function') {
        // Keep a saved reader validated. A full invalidate clears both entries.
        markSectionNotValidated('rfid', { persist: false });
    }
    if (typeof loadCompletionStatus === 'function') {
        loadCompletionStatus();
    }
}

function populateBidirectionalRfidFields() {
    if (!isBidirectionalLayout() || !config.rfids) return;
    ['entry_a', 'entry_b'].forEach((dir) => {
        const data = config.rfids[dir] || {};
        const ids = getRfidFieldIds(dir);
        const makeEl = document.getElementById(ids.make);
        const modelEl = document.getElementById(ids.model);
        const portEl = document.getElementById(ids.port);
        const modeEl = document.getElementById(ids.modeSelect);
        const userEl = document.getElementById(ids.username);
        const passEl = document.getElementById(ids.password);
        const apiPortEl = document.getElementById(ids.apiPort);
        if (makeEl) makeEl.value = data.make || '';
        if (modelEl) modelEl.value = data.model || '';
        if (modeEl) modeEl.value = data.mode || 'API';
        if (portEl) portEl.value = data.port || (String(data.mode || 'API').toUpperCase() === 'API' ? '443' : '6000');
        if (apiPortEl) apiPortEl.value = data.api_port || (dir === 'entry_b' ? '8081' : '8080');
        if (userEl) userEl.value = data.username || 'admin';
        if (passEl && data.password != null) passEl.value = data.password;
        setRfidDirectionIpField(dir, data.ip || '');
        onRfidDirectionModeChange(dir);
        applyBidirectionalRfidValidatedFromConfig(dir, data.validated, data.mode);
    });
    updateBidirectionalRfidSectionCompletion();
}

function populateBidirectionalTrafficLights() {
    if (!isBidirectionalLayout() || !config.io_controller?.traffic_lights) return;
    const tl = config.io_controller.traffic_lights;
    const tlMode = tl.mode || 'direct';
    ['entry_a', 'entry_b'].forEach((dir) => {
        const prefix = tlIdPrefix(dir);
        const dmeta = tl[dir] || {};
        ['entry', 'exit'].forEach((loc) => {
            const info = dmeta[loc] || {};
            const makeEl = document.getElementById(`${prefix}_${loc}TLMake`);
            const modelEl = document.getElementById(`${prefix}_${loc}TLModel`);
            if (makeEl) makeEl.value = info.make || '';
            if (modelEl) modelEl.value = info.model || '';
            if (tlMode === 'direct' && tl.direct?.[dir]) {
                const pins = tl.direct[dir][loc] || {};
                const redEl = document.getElementById(`${prefix}_${loc}RedPin`);
                const greenEl = document.getElementById(`${prefix}_${loc}GreenPin`);
                if (redEl && pins.red_pin != null) redEl.value = pins.red_pin;
                if (greenEl && pins.green_pin != null) greenEl.value = pins.green_pin;
            }
            if (tlMode === 'relay' && tl.relay?.[dir]?.[loc]) {
                const pinEl = document.getElementById(`${prefix}_${loc}TLRelayPin`);
                if (pinEl && tl.relay[dir][loc].pin != null) pinEl.value = tl.relay[dir][loc].pin;
            }
            const enableId = tlMode === 'relay'
                ? `${prefix}_${loc}TLRelayEnabled`
                : `${prefix}_${loc}TLEnabled`;
            const enableEl = document.getElementById(enableId);
            if (enableEl) enableEl.checked = info.enabled === true || info.validated === true;
            applyTrafficLightValidatedFromConfig(loc, info.validated, dir);
        });
    });
}

function initBidirectionalAssignedDevices() {
    if (!config.rfids) return;
    if (config.rfids.entry_a?.ip) {
        assignedDevices.ips.rfid_entry_a = config.rfids.entry_a.ip;
    }
    if (config.rfids.entry_b?.ip) {
        assignedDevices.ips.rfid_entry_b = config.rfids.entry_b.ip;
    }
}

/** Assigned IPs to hide from dropdown - excludes self and peer so swap/interchange is possible. */
function getAssignedIpsForBidirectionalRfid(directionKey) {
    const selfKey = RFID_DIRECTION_UI[directionKey]?.assignKey;
    const peerKey = RFID_DIRECTION_UI[
        directionKey === 'entry_a' ? 'entry_b' : 'entry_a'
    ]?.assignKey;
    if (typeof assignedDevices === 'undefined' || !assignedDevices.ips) return [];
    return Object.entries(assignedDevices.ips)
        .filter(([device, ip]) => {
            if (!ip) return false;
            if (device === selfKey || device === peerKey) return false;
            return true;
        })
        .map(([, ip]) => ip);
}

function populateBidirectionalRfidDropdowns() {
    if (!isBidirectionalLayout()) return;
    const candidates = discoveredDevices.candidates?.rfid || [];
    ['entry_a', 'entry_b'].forEach((dir) => {
        const ui = RFID_DIRECTION_UI[dir];
        const assigned = getAssignedIpsForBidirectionalRfid(dir);
        const available = filterAssignedDevices(candidates, assigned);
        populateDropdown(`${ui.prefix}IpSelect`, available, 'Select discovered RFID device...', ui.assignKey);
    });
}

function validateBidirectionalRfidsPayload(payload) {
    const ipA = (payload?.entry_a?.ip || '').trim();
    const ipB = (payload?.entry_b?.ip || '').trim();
    if (ipA && ipB && ipA === ipB) {
        showToast(
            'error',
            'Duplicate RFID IP',
            'Both directions still use the same IP. Update the other direction or use Swap Readers.'
        );
        return false;
    }
    const modeA = String(payload?.entry_a?.mode || '').toUpperCase();
    const modeB = String(payload?.entry_b?.mode || '').toUpperCase();
    const portA = String(payload?.entry_a?.api_port || '').trim();
    const portB = String(payload?.entry_b?.api_port || '').trim();
    if (modeA === 'API' && modeB === 'API' && portA && portB && portA === portB) {
        showToast(
            'error',
            'Duplicate RFID_API_PORT',
            'ENTRY A and ENTRY B must use different RFID_API_PORT values.'
        );
        return false;
    }
    return true;
}

/**
 * When user points one direction at the other reader's IP before updating the peer form,
 * exchange IPs in the save payload using the previously saved reader for the active slot.
 */
function resolveBidirectionalRfidsPayloadForSave(activeDirectionKey, activeReader) {
    let payload = buildBidirectionalRfidsPayload(activeDirectionKey, activeReader);
    const ipA = (payload.entry_a?.ip || '').trim();
    const ipB = (payload.entry_b?.ip || '').trim();
    if (!ipA || !ipB || ipA !== ipB) return payload;

    const savedThis = config.rfids?.[activeDirectionKey];
    const otherKey = activeDirectionKey === 'entry_a' ? 'entry_b' : 'entry_a';
    const savedOther = config.rfids?.[otherKey];
    const savedIpThis = (savedThis?.ip || '').trim();
    const savedIpOther = (savedOther?.ip || '').trim();
    if (!savedIpThis || !savedIpOther || savedIpThis === savedIpOther) return payload;

    const activeIp = (activeReader.ip || '').trim();
    const otherFormIp = getRfidDirectionIpFromForm(otherKey).trim();

    if (activeIp === savedIpOther && otherFormIp === savedIpOther && activeIp !== savedIpThis) {
        const otherReader = orderExistingRfidReader({ ...savedThis, validated: false });
        payload = {
            entry_a: activeDirectionKey === 'entry_a'
                ? activeReader
                : otherReader,
            entry_b: activeDirectionKey === 'entry_b'
                ? activeReader
                : otherReader
        };
        showToast(
            'info',
            'Readers exchanged',
            'ENTRY A and ENTRY B IPs were swapped in configuration. Re-test both readers when ready.'
        );
    }
    return payload;
}

function buildOrderedRfidReader(ip, port, mode, rfidMake, rfidModel, validated, calibrationData = {}) {
    const reader = {
        ip,
        port,
        mode,
        make: rfidMake,
        model: rfidModel,
        username: calibrationData.username ?? 'admin',
        password: calibrationData.password ?? '',
        validated,
        manual_match_start: calibrationData.manual_match_start ?? -1,
        manual_match_length: calibrationData.manual_match_length ?? 0,
        manual_match_sample: calibrationData.manual_match_sample ?? ''
    };
    if (calibrationData.api_port != null && calibrationData.api_port !== '') {
        reader.api_port = String(calibrationData.api_port);
    }
    if (calibrationData.note) {
        reader.note = calibrationData.note;
    } else if (String(mode || '').toUpperCase() === 'API') {
        reader.note = 'API mode: tags via POST /rfid_data; cloud login/mode/start/stop via HTTPS';
    }
    Object.keys(calibrationData).forEach((k) => {
        if (!Object.prototype.hasOwnProperty.call(reader, k)) {
            reader[k] = calibrationData[k];
        }
    });
    return reader;
}

function orderExistingRfidReader(reader = {}) {
    return buildOrderedRfidReader(
        reader.ip || '',
        reader.port || '',
        reader.mode || 'API',
        reader.make || '',
        reader.model || '',
        reader.validated,
        {
            username: reader.username,
            password: reader.password,
            note: reader.note,
            api_port: reader.api_port,
            manual_match_start: reader.manual_match_start,
            manual_match_length: reader.manual_match_length,
            manual_match_sample: reader.manual_match_sample
        }
    );
}

async function saveRfidDirectionConfig(ip, port, mode, rfidMake, rfidModel, validated, directionKey, calibrationData = {}) {
    const activeReader = buildOrderedRfidReader(
        ip, port, mode, rfidMake, rfidModel, validated, calibrationData
    );
    const payload = resolveBidirectionalRfidsPayloadForSave(directionKey, activeReader);
    if (!validateBidirectionalRfidsPayload(payload)) {
        return;
    }
    const otherKey = directionKey === 'entry_a' ? 'entry_b' : 'entry_a';

    const postRfids = async () => {
        let response;
        try {
            response = await fetch('/api/config/rfids', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (error) {
            console.error('[Save RFID Config] Error:', error);
            showToast('error', 'Error', 'Failed to save RFID configuration');
            return null;
        }

        let body = {};
        try {
            body = await response.json();
        } catch (e) { /* ignore */ }

        if (!response.ok || body.status === 400) {
            showToast('error', 'Save Failed', body.message || 'Failed to save RFID configuration');
            if (typeof markSectionNotValidated === 'function') {
                markSectionNotValidated('rfid', { persist: false });
            }
            return null;
        }
        return body;
    };

    const saved = typeof withSectionSaveGuard === 'function'
        ? await withSectionSaveGuard('rfid', postRfids)
        : await postRfids();
    if (!saved) return;

    config.rfids = payload;
    if (payload.entry_a?.ip) {
        updateAssignedDevice(RFID_DIRECTION_UI.entry_a.assignKey, payload.entry_a.ip, true);
    }
    if (payload.entry_b?.ip) {
        updateAssignedDevice(RFID_DIRECTION_UI.entry_b.assignKey, payload.entry_b.ip, true);
    }
    populateBidirectionalRfidFields();
    populateBidirectionalRfidDropdowns();

    if (validated === true) {
        applyBidirectionalRfidValidatedFromConfig(directionKey, true, mode);
        const aOk = payload.entry_a?.validated === true;
        const bOk = payload.entry_b?.validated === true;
        if (aOk && bOk) {
            markSectionValidated('rfid');
            const sections = (typeof getWizardNavSections === 'function') ? getWizardNavSections() : [];
            if (sections.includes('handheld-rfid') && typeof showSection === 'function') {
                showSection('handheld-rfid');
            } else {
                navigateToNext('rfid');
            }
        } else {
            markSectionNotValidated('rfid', { persist: false });
            showToast(
                'success',
                'Saved',
                `${RFID_DIRECTION_UI[directionKey].label} RFID saved. Configure and test ${RFID_DIRECTION_UI[otherKey].label}.`
            );
        }
    } else {
        applyBidirectionalRfidValidatedFromConfig(directionKey, false, mode);
        markSectionNotValidated('rfid', { persist: false });
    }
    updateBidirectionalRfidSectionCompletion();
    return true;
}

async function swapBidirectionalRfidReaders() {
    if (!isBidirectionalLayout()) return;
    const a = config.rfids?.entry_a;
    const b = config.rfids?.entry_b;
    if (!a?.ip && !b?.ip) {
        showToast('warning', 'Swap', 'Configure at least one RFID reader before swapping.');
        return;
    }

    const payload = {
        entry_a: orderExistingRfidReader({ ...(b || {}), validated: false }),
        entry_b: orderExistingRfidReader({ ...(a || {}), validated: false })
    };
    if (!validateBidirectionalRfidsPayload(payload)) return;

    try {
        const response = await fetch('/api/config/rfids', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok || body.status === 400) {
            showToast('error', 'Swap Failed', body.message || 'Could not swap RFID readers');
            return;
        }
    } catch (error) {
        console.error('[Swap RFID Readers] Error:', error);
        showToast('error', 'Swap Failed', 'Could not swap RFID readers');
        return;
    }

    config.rfids = payload;
    updateAssignedDevice(RFID_DIRECTION_UI.entry_a.assignKey, payload.entry_a?.ip || null, true);
    updateAssignedDevice(RFID_DIRECTION_UI.entry_b.assignKey, payload.entry_b?.ip || null, true);
    populateBidirectionalRfidFields();
    populateBidirectionalRfidDropdowns();
    applyBidirectionalRfidValidatedFromConfig('entry_a', false, null);
    applyBidirectionalRfidValidatedFromConfig('entry_b', false, null);
    if (typeof markSectionNotValidated === 'function') markSectionNotValidated('rfid');
    updateBidirectionalRfidSectionCompletion();
    showToast(
        'success',
        'Readers swapped',
        'ENTRY A and ENTRY B RFID settings were exchanged. Run Check & Save on each entry to re-test.'
    );
}

async function resetRfidDirection(directionKey) {
    const ids = getRfidFieldIds(directionKey);
    ['make', 'model', 'ip'].forEach((k) => {
        const el = document.getElementById(ids[k]);
        if (el) el.value = '';
    });
    const portEl = document.getElementById(ids.port);
    if (portEl) portEl.value = '443';
    const apiPortEl = document.getElementById(ids.apiPort);
    if (apiPortEl) apiPortEl.value = directionKey === 'entry_b' ? '8081' : '8080';
    const userEl = document.getElementById(ids.username);
    if (userEl) userEl.value = 'admin';
    const passEl = document.getElementById(ids.password);
    if (passEl) passEl.value = '';
    const manualCb = document.getElementById(ids.ipManual);
    if (manualCb) manualCb.checked = false;
    const selectEl = document.getElementById(ids.ipSelect);
    if (selectEl) selectEl.value = '';
    if (typeof toggleManualInput === 'function') toggleManualInput(ids.ip);

    const modeEl = document.getElementById(ids.modeSelect);
    if (modeEl) modeEl.value = 'API';
    onRfidDirectionModeChange(directionKey);
    applyBidirectionalRfidValidatedFromConfig(directionKey, false, null);

    const clearedReader = buildOrderedRfidReader('', '443', 'API', '', '', false, {
        username: 'admin',
        password: '',
        api_port: directionKey === 'entry_b' ? '8081' : '8080',
        manual_match_start: -1,
        manual_match_length: 0,
        manual_match_sample: ''
    });
    const payload = buildBidirectionalRfidsPayload(directionKey, clearedReader);
    try {
        const response = await fetch('/api/config/rfids', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok || body.status === 400) {
            showToast('error', 'Reset Failed', body.message || 'Could not reset RFID direction');
            return;
        }
        config.rfids = payload;
    } catch (error) {
        console.error('[Reset RFID Direction] Error:', error);
        showToast('error', 'Reset Failed', 'Could not reset RFID direction');
        return;
    }

    const ui = RFID_DIRECTION_UI[directionKey];
    updateAssignedDevice(ui.assignKey, null, true);
    if (typeof markSectionNotValidated === 'function') markSectionNotValidated('rfid');
    updateBidirectionalRfidSectionCompletion();
    showToast('info', 'Reset', `${ui.label} RFID settings cleared.`);
}

function buildBidirectionalTrafficLightsForSave(outputMode, configData) {
    const tl = configData.traffic_lights;
    tl.direct = { entry_a: { entry: {}, exit: {} }, entry_b: { entry: {}, exit: {} } };
    tl.entry_a = { entry: {}, exit: {} };
    tl.entry_b = { entry: {}, exit: {} };
    if (outputMode === 'direct') {
        ['entry_a', 'entry_b'].forEach((dir) => {
            const prefix = tlIdPrefix(dir);
            const defaultPins = dir === 'entry_a'
                ? { entry: ['0', '1'], exit: ['2', '3'] }
                : { entry: ['4', '5'], exit: ['6', '7'] };
            ['entry', 'exit'].forEach((loc) => {
                const [redDefault, greenDefault] = defaultPins[loc];
                const validated = getTrafficLightValidatedForSave(loc, dir);
                const active = validated === true;
                tl.direct[dir][loc] = {
                    red_pin: active
                        ? (document.getElementById(`${prefix}_${loc}RedPin`)?.value || redDefault)
                        : '',
                    green_pin: active
                        ? (document.getElementById(`${prefix}_${loc}GreenPin`)?.value || greenDefault)
                        : ''
                };
                tl[dir][loc] = {
                    make: document.getElementById(`${prefix}_${loc}TLMake`)?.value.trim() || '',
                    model: document.getElementById(`${prefix}_${loc}TLModel`)?.value.trim() || '',
                    enabled: active || validated === false,
                    validated
                };
            });
        });
    } else {
        tl.relay = { entry_a: { entry: {}, exit: {} }, entry_b: { entry: {}, exit: {} } };
        const relayDefaults = { entry_a: { entry: '0', exit: '1' }, entry_b: { entry: '2', exit: '3' } };
        ['entry_a', 'entry_b'].forEach((dir) => {
            const prefix = tlIdPrefix(dir);
            ['entry', 'exit'].forEach((loc) => {
                const validated = getTrafficLightValidatedForSave(loc, dir);
                const active = validated === true;
                tl.relay[dir][loc] = {
                    pin: active
                        ? (document.getElementById(`${prefix}_${loc}TLRelayPin`)?.value || relayDefaults[dir][loc])
                        : '',
                    description: 'NO=Green, NC=Red'
                };
                tl[dir][loc] = {
                    make: '',
                    model: '',
                    enabled: active || validated === false,
                    validated
                };
            });
        });
    }
    delete tl.entry;
    delete tl.exit;
    const direct = tl.direct;
    if (direct && typeof direct === 'object') {
        delete direct.entry;
        delete direct.exit;
    }
    const relay = tl.relay;
    if (relay && typeof relay === 'object') {
        delete relay.entry;
        delete relay.exit;
    }
}

function allRequiredTrafficLightsSatisfied() {
    if (typeof isCheckpointFamily === 'function' && isCheckpointFamily()) {
        return isTrafficLightIoTestSatisfied('entry');
    }
    if (!isBidirectionalLayout()) {
        return isTrafficLightIoTestSatisfied('entry') && isTrafficLightIoTestSatisfied('exit');
    }
    return ['entry_a', 'entry_b'].every((dir) =>
        isTrafficLightIoTestSatisfied('entry', dir) && isTrafficLightIoTestSatisfied('exit', dir)
    );
}

(function patchDevicesForBidirectional() {
    if (typeof assignedDevices !== 'undefined' && assignedDevices.ips) {
        assignedDevices.ips.rfid_entry_a = assignedDevices.ips.rfid_entry_a || null;
        assignedDevices.ips.rfid_entry_b = assignedDevices.ips.rfid_entry_b || null;
    }

    const _getTrafficLightValidatedForSave = getTrafficLightValidatedForSave;
    getTrafficLightValidatedForSave = function (location, directionKey) {
        if (typeof isTrafficLightEnabled === 'function' && !isTrafficLightEnabled(location, directionKey)) {
            return null;
        }
        if (!directionKey) return _getTrafficLightValidatedForSave(location);
        const key = getTlValidatedStateKey(directionKey, location);
        return ioTestStatus[key];
    };

    const _isTrafficLightIoTestSatisfied = isTrafficLightIoTestSatisfied;
    isTrafficLightIoTestSatisfied = function (location, directionKey) {
        const v = getTrafficLightValidatedForSave(location, directionKey);
        return v === true || v === null;
    };

    const _applyTrafficLightValidatedFromConfig = applyTrafficLightValidatedFromConfig;
    applyTrafficLightValidatedFromConfig = function (location, validated, directionKey) {
        if (!directionKey) return _applyTrafficLightValidatedFromConfig(location, validated);
        const gateKey = getTlGateStateKey(directionKey, location);
        const validatedKey = getTlValidatedStateKey(directionKey, location);
        const statusIds = getTlStatusElementIds(directionKey, location);
        if (validated === true) {
            ioTestStatus[gateKey] = true;
            ioTestStatus[validatedKey] = true;
            statusIds.forEach((id) => {
                const el = document.getElementById(id);
                if (el) { el.textContent = 'Passed'; el.className = 'device-status success'; }
            });
        } else if (validated === null) {
            ioTestStatus[gateKey] = true;
            ioTestStatus[validatedKey] = null;
            statusIds.forEach((id) => {
                const el = document.getElementById(id);
                if (el) { el.textContent = 'Skipped'; el.className = 'device-status skipped'; }
            });
        } else {
            ioTestStatus[gateKey] = false;
            ioTestStatus[validatedKey] = false;
            statusIds.forEach((id) => {
                const el = document.getElementById(id);
                if (el) { el.textContent = ''; el.className = 'device-status'; }
            });
        }
    };

    const _skipTrafficLightTest = skipTrafficLightTest;
    skipTrafficLightTest = function (location, directionKey) {
        if (!APP_CONFIG.debug) {
            showToast('error', 'Skip', 'Traffic light skip is only available in debug mode.');
            return;
        }
        if (!directionKey) return _skipTrafficLightTest(location);
        applyTrafficLightValidatedFromConfig(location, null, directionKey);
        if (typeof persistTrafficLightDevice === 'function') {
            persistTrafficLightDevice(location, directionKey);
        }
        const label = RFID_DIRECTION_UI[directionKey]?.label || directionKey;
        showToast('warning', 'Skipped', `${label} ${location} traffic light test skipped (Debug mode)`);
    };

    const _onDeviceSelect = onDeviceSelect;
    onDeviceSelect = function (fieldId, value, assignKey) {
        _onDeviceSelect(fieldId, value);
        if (assignKey && value) updateAssignedDevice(assignKey, value, true);
    };

    const _populateDeviceDropdowns = populateDeviceDropdowns;
    populateDeviceDropdowns = function () {
        _populateDeviceDropdowns();
        populateBidirectionalRfidDropdowns();
    };

    const _initAssignedDevices = initAssignedDevices;
    initAssignedDevices = function () {
        _initAssignedDevices();
        initBidirectionalAssignedDevices();
    };

    const _loadConfig = loadConfig;
    loadConfig = async function () {
        await _loadConfig();
        syncWeighbridgeLayoutFromConfig();
        populateBidirectionalRfidFields();
        populateBidirectionalTrafficLights();
        applyWeighbridgeLayoutUI();
    };

    const _populateFormFields = populateFormFields;
    populateFormFields = function () {
        _populateFormFields();
        syncWeighbridgeLayoutFromConfig();
        populateBidirectionalRfidFields();
        populateBidirectionalTrafficLights();
        applyWeighbridgeLayoutUI();
    };

    const _checkAndSaveRFID = checkAndSaveRFID;
    checkAndSaveRFID = async function (directionKey) {
        currentRfidDirectionKey = directionKey || null;
        if (!isBidirectionalLayout() || !directionKey) {
            return _checkAndSaveRFID();
        }
        const ids = getRfidFieldIds(directionKey);
        const isManual = document.getElementById(ids.ipManual)?.checked;
        const ip = isManual
            ? document.getElementById(ids.ip)?.value.trim()
            : (document.getElementById(ids.ipSelect)?.value || document.getElementById(ids.ip)?.value.trim());
        const port = document.getElementById(ids.port)?.value.trim() || '';
        const mode = (document.getElementById(ids.modeSelect)?.value || 'API').toUpperCase();
        const rfidMake = document.getElementById(ids.make)?.value.trim() || '';
        const rfidModel = document.getElementById(ids.model)?.value.trim() || '';
        const username = document.getElementById(ids.username)?.value.trim() || 'admin';
        const password = document.getElementById(ids.password)?.value || '';
        const apiPort = document.getElementById(ids.apiPort)?.value.trim() || '';
        const label = RFID_DIRECTION_UI[directionKey].label;
        if (!ip) {
            showToast('error', 'Validation Error', `Please enter RFID reader IP for ${label}`);
            return;
        }
        if (mode !== 'API' && !port) {
            showToast('error', 'Validation Error', `Please enter both IP and Port for ${label}`);
            return;
        }
        if (mode === 'API' && !apiPort) {
            showToast('error', 'Validation Error', `Please enter RFID_API_PORT for ${label}`);
            return;
        }
        if (mode === 'API' && apiPort) {
            const otherKey = directionKey === 'entry_a' ? 'entry_b' : 'entry_a';
            const otherIds = getRfidFieldIds(otherKey);
            const otherMode = (document.getElementById(otherIds.modeSelect)?.value || 'API').toUpperCase();
            const otherApiPort = document.getElementById(otherIds.apiPort)?.value.trim() || '';
            if (otherMode === 'API' && otherApiPort && otherApiPort === apiPort) {
                showToast(
                    'error',
                    'Duplicate RFID_API_PORT',
                    `${label} RFID_API_PORT must differ from ${RFID_DIRECTION_UI[otherKey].label}.`
                );
                return;
            }
        }
        if (!validateDeviceInfo(rfidMake, rfidModel, `${label} RFID Reader`)) return;

        showLoading(true);
        const statusEl = document.getElementById(ids.status);
        if (statusEl) statusEl.style.display = 'none';
        try {
            await fetch('/api/rfid/stop', { method: 'POST' }).catch(() => null);
            const response = await fetch('/api/rfid/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ip,
                    port: port || '443',
                    mode,
                    username,
                    password,
                    api_port: apiPort || undefined,
                })
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
                } else {
                    handleRfidResult(result, ip, port, rfidMake, rfidModel);
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
    };

    const _saveRfidConfig = saveRfidConfig;
    saveRfidConfig = async function (ip, port, mode, rfidMake, rfidModel, validated, calibrationData = {}) {
        if (isBidirectionalLayout() && currentRfidDirectionKey) {
            try {
                const ids = getRfidFieldIds(currentRfidDirectionKey);
                const username = calibrationData.username
                    ?? (document.getElementById(ids.username)?.value.trim() || 'admin');
                const password = calibrationData.password
                    ?? (document.getElementById(ids.password)?.value || '');
                await saveRfidDirectionConfig(
                    ip,
                    port,
                    mode,
                    rfidMake,
                    rfidModel,
                    validated,
                    currentRfidDirectionKey,
                    { ...calibrationData, username, password }
                );
                const statusEl = document.getElementById(ids.status);
                const modeEl = document.getElementById(ids.mode);
                if (statusEl) statusEl.style.display = 'flex';
                if (modeEl) modeEl.textContent = rfidModeStatusLabel(mode);
            } catch (error) {
                console.error('[Save RFID Config] Error:', error);
                showToast('error', 'Error', 'Failed to save RFID configuration');
            }
            return;
        }
        return _saveRfidConfig(ip, port, mode, rfidMake, rfidModel, validated, calibrationData);
    };

    const _handleRfidResult = handleRfidResult;
    handleRfidResult = function (result, ip, port, rfidMake, rfidModel) {
        if (isBidirectionalLayout() && currentRfidDirectionKey) {
            const ids = getRfidFieldIds(currentRfidDirectionKey);
            showLoading(false);
            if (result.status === 200) {
                const statusEl = document.getElementById(ids.status);
                const modeEl = document.getElementById(ids.mode);
                if (statusEl) statusEl.style.display = 'flex';
                if (modeEl) modeEl.textContent = rfidModeStatusLabel(result.mode);
                if (result.mode === 'API') {
                    if (result.card_read === true) {
                        const tag = result.parsed_tag || result.card_display || result.card_data || '';
                        const username = document.getElementById(ids.username)?.value.trim() || 'admin';
                        const password = document.getElementById(ids.password)?.value || '';
                        const apiPort = document.getElementById(ids.apiPort)?.value.trim() || '';
                        showToast('success', 'RFID', 'RFID tag data received');
                        saveRfidConfig(ip, port || '443', 'API', rfidMake, rfidModel, true, {
                            username,
                            password,
                            api_port: apiPort || undefined,
                        });
                    } else {
                        showToast('warning', 'RFID', result.message || 'No RFID data received. Please try again.');
                    }
                    return;
                }
                if (result.testing === true || result.test_complete === false) return;
                if (result.card_read === true) {
                    showToast('success', 'Success', result.message || 'Reader Connected and Valid RFID received');
                    openRfidCalibrationModal(result.card_display || result.parsed_tag || result.card_data, {
                        ip, port, mode: result.mode, rfidMake, rfidModel
                    });
                } else {
                    showToast('warning', 'Warning', result.message || 'Reader Connected, but no card read');
                    saveRfidConfig(ip, port, result.mode, rfidMake, rfidModel, false);
                }
            } else {
                showToast('error', 'Connection Failed', result.message);
            }
            return;
        }
        return _handleRfidResult(result, ip, port, rfidMake, rfidModel);
    };

    const _testTrafficLightColor = testTrafficLightColor;
    testTrafficLightColor = async function (arg1, arg2, arg3) {
        let directionKey = null;
        let location;
        let color;
        if (arg3 !== undefined) {
            directionKey = arg1;
            location = arg2;
            color = arg3;
        } else {
            location = arg1;
            color = arg2;
        }
        if (!directionKey) {
            return _testTrafficLightColor(location, color);
        }
        if (!ioConnected) {
            showToast('error', 'Not Connected', 'Please connect to I/O controller first');
            return;
        }
        const slaveId = document.getElementById('ioSlaveId').value;
        const outputRegisterType = document.getElementById('outputRegisterType')?.value || ioRegisterConfig.outputType;
        const statusIds = getTlStatusElementIds(directionKey, location);
        const statusEl = document.getElementById(statusIds[0]);
        const channelNum = document.getElementById(getTlPinElementId(directionKey, location, color))?.value;
        if (channelNum === '' || channelNum == null) {
            showToast('error', 'Missing Channel', `Please enter channel number for ${location} ${color} light`);
            return;
        }
        const registerAddress = getOutputAddress(channelNum);
        if (registerAddress === null || registerAddress < 0) {
            showToast('error', 'Invalid Channel', `Invalid channel number: ${channelNum}`);
            return;
        }
        if (statusEl) {
            statusEl.textContent = `Testing ${color}...`;
            statusEl.className = 'device-status testing';
        }
        try {
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
                if (statusEl) { statusEl.textContent = 'Error'; statusEl.className = 'device-status error'; }
                showToast('error', 'Error', onResult.message);
                return;
            }
            showHardwareTestModal('traffic_light', location, color, async (verified) => {
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
                const gateKey = getTlGateStateKey(directionKey, location);
                const validatedKey = getTlValidatedStateKey(directionKey, location);
                if (verified) {
                    if (statusEl) { statusEl.textContent = `${color} OK`; statusEl.className = 'device-status success'; }
                    ioTestStatus[gateKey] = true;
                    ioTestStatus[validatedKey] = true;
                    if (typeof persistTrafficLightDevice === 'function') {
                        persistTrafficLightDevice(location, directionKey);
                    }
                    showToast('success', 'Test Passed', `${location} ${color} light working!`);
                } else {
                    if (statusEl) { statusEl.textContent = 'Failed'; statusEl.className = 'device-status error'; }
                    ioTestStatus[gateKey] = false;
                    ioTestStatus[validatedKey] = false;
                    showToast('error', 'Test Failed', `${location} ${color} light not responding`);
                }
            });
        } catch (error) {
            if (statusEl) { statusEl.textContent = 'Error'; statusEl.className = 'device-status error'; }
            showToast('error', 'Test Error', 'Unable to communicate with traffic light');
        }
    };

    document.addEventListener('DOMContentLoaded', function () {
        ['entry_a', 'entry_b'].forEach((dir) => {
            ['entry', 'exit'].forEach((loc) => {
                ioTestStatus[getTlValidatedStateKey(dir, loc)] = false;
                ioTestStatus[getTlGateStateKey(dir, loc)] = false;
            });
        });
        applyWeighbridgeLayoutUI();
    });
})();
