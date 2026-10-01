// GMDC checkpoint type + weighbridge direction selection

function getWeighbridgeLayout() {
    if (typeof config !== 'undefined' && config?.wb_type) {
        return config.wb_type;
    }
    if (typeof config !== 'undefined' && config?.weighbridge_layout) {
        return config.weighbridge_layout;
    }
    return window.APP_CONFIG?.wbType
        || sessionStorage.getItem('wbType')
        || window.APP_CONFIG?.weighbridgeLayout
        || sessionStorage.getItem('weighbridgeLayout')
        || 'unidirectional';
}

function getCheckpointType() {
    if (typeof config !== 'undefined' && config?.checkpoint_type) {
        return config.checkpoint_type;
    }
    return window.APP_CONFIG?.checkpointType
        || sessionStorage.getItem('checkpointType')
        || 'checkpoint';
}

function isBidirectionalLayout() {
    return getWeighbridgeLayout() === 'bidirectional';
}

function _selectedCheckpointFamily() {
    const sel = document.getElementById('checkpointTypeSelect');
    if (!sel) return 'checkpoint';
    const opt = sel.options[sel.selectedIndex];
    return opt?.dataset?.family || 'checkpoint';
}

function _syncDirectionVisibility() {
    const family = _selectedCheckpointFamily();
    const dirBlock = document.getElementById('directionChoiceBlock');
    const isWb = family === 'weighbridge';
    if (dirBlock) dirBlock.style.display = isWb ? '' : 'none';
}

function showWeighbridgeLayoutModal(onConfirm) {
    const modal = document.getElementById('weighbridgeLayoutModal');
    if (!modal) {
        if (typeof onConfirm === 'function') {
            onConfirm('unidirectional');
        }
        return;
    }
    modal._layoutConfirmCallback = onConfirm;

    const typeSel = document.getElementById('checkpointTypeSelect');
    if (typeSel) {
        const savedType = sessionStorage.getItem('checkpointType') || getCheckpointType();
        if ([...typeSel.options].some(o => o.value === savedType)) {
            typeSel.value = savedType;
        }
        typeSel.onchange = _syncDirectionVisibility;
    }

    const saved = sessionStorage.getItem('wbType')
        || sessionStorage.getItem('weighbridgeLayout')
        || 'unidirectional';
    const radio = modal.querySelector(`input[name="weighbridgeLayoutChoice"][value="${saved}"]`);
    if (radio) radio.checked = true;

    _syncDirectionVisibility();
    modal.classList.add('active');
}

function closeWeighbridgeLayoutModal() {
    const modal = document.getElementById('weighbridgeLayoutModal');
    if (modal) modal.classList.remove('active');
}

async function confirmWeighbridgeLayoutChoice() {
    const modal = document.getElementById('weighbridgeLayoutModal');
    const typeSel = document.getElementById('checkpointTypeSelect');
    const checkpointType = typeSel?.value || getCheckpointType();
    const family = _selectedCheckpointFamily();
    const selected = family === 'weighbridge'
        ? (modal?.querySelector('input[name="weighbridgeLayoutChoice"]:checked')?.value || 'unidirectional')
        : 'unidirectional';

    sessionStorage.setItem('checkpointType', checkpointType);
    sessionStorage.setItem('wbType', selected);
    if (window.APP_CONFIG) {
        window.APP_CONFIG.checkpointType = checkpointType;
        window.APP_CONFIG.wbType = selected;
    }

    try {
        const resp = await fetch('/api/config/checkpoint-type', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                checkpoint_type: checkpointType,
                direction: selected,
                wb_type: selected,
            }),
        });
        const result = await resp.json().catch(() => ({}));
        if (typeof config !== 'undefined') {
            config.checkpoint_type = checkpointType;
            config.wb_type = selected;
        }
        if (window.APP_CONFIG && result.profile) {
            window.APP_CONFIG.profile = result.profile;
        }
        if (result.layout_changed) {
            showToast(
                'warning',
                'Checkpoint type changed',
                result.message || 'Reconfigure RFID / I/O before continuing.'
            );
            if (typeof resetLayoutDependentTestState === 'function') {
                resetLayoutDependentTestState();
            }
        }
        if (typeof syncDisplayIpFieldsVisibility === 'function') {
            syncDisplayIpFieldsVisibility();
        }
        if (typeof toggleDisplayFields === 'function') {
            toggleDisplayFields();
        }
    } catch (e) {
        console.warn('[Layout] Failed to persist checkpoint type:', e);
    }
    closeWeighbridgeLayoutModal();
    const cb = modal?._layoutConfirmCallback;
    if (typeof cb === 'function') {
        cb(selected);
    }
}

function proceedToConfigWithLayoutChoice() {
    showWeighbridgeLayoutModal(function () {
        window.location.href = '/devices';
    });
}
