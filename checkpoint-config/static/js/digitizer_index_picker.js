/*
 * digitizer_index_picker.js — operator byte-index picker for the digitizer.
 *
 * Flow (see digitizer-demo/FUTURE_INDEX_PICKER_UI_SPEC.md):
 *   Check & Save → POST /api/digitizer/sample (45 bytes, 10s)
 *                → index picker modal (6 rows, live preview, debounced)
 *                → Check → fresh capture + live verify
 *                → Confirm modal → onSave('index_based', indexing, sampleHex)
 *
 * The modal + confirm DOM is created on demand (idempotent) so the same picker
 * works on both index.html and devices.html.
 */

const WIZARD_CAPTURE_BYTES = 45;
let digitizerCalibrationMinWeightKg = 500;

async function refreshDigitizerCalibrationMinWeight() {
    try {
        const resp = await fetch('/api/digitizer/calibration-rules');
        const data = await resp.json();
        if (data.status === 200 && data.min_weight_kg) {
            digitizerCalibrationMinWeightKg = data.min_weight_kg;
        }
    } catch (err) {
        console.warn('[Digitizer] Could not refresh calibration min weight:', err);
    }
}

function _dpCalibrationMinKg() {
    return digitizerCalibrationMinWeightKg;
}

// Friendly UI labels (rows 1, 3, and 4 are required).
const DIGITIZER_INDEX_FRIENDLY_LABELS = [
    'Start of weight message — 1st character (required)',
    'Start of weight message — 2nd character (optional)',
    'Weight number — where digits begin (required)',
    'Weight number — where digits end (required)',
    'End of weight message — 1st character (optional)',
    'End of weight message — 2nd character (optional)',
];

const _DP_REQUIRED_ROWS = [0, 2, 3]; // zero-based rows 1, 3, and 4

function _dpIsRequiredRow(rowIndex) {
    return _DP_REQUIRED_ROWS.includes(rowIndex);
}

function _dpMissingRequiredPicks(picks) {
    for (const r of _DP_REQUIRED_ROWS) {
        const v = picks[r];
        if (v === null || v === undefined || v === '') {
            return true;
        }
    }
    return false;
}

const _dpState = {
    sampleHex: '',
    ruler: null,
    picks: [null, null, null, null, null, null],
    portSettings: null,
    onSave: null,
    savedIndexing: null,
    previewTimer: null,
    lastPreview: null,
};

// ---------------------------------------------------------------------------
// Port settings + entry point
// ---------------------------------------------------------------------------

function _dpReadPortSettings() {
    return {
        port: document.getElementById('digitizerPort')?.value || '',
        baud_rate: parseInt(document.getElementById('digitizerBaud')?.value || '9600', 10),
        bytesize: parseInt(document.getElementById('digitizerDataBits')?.value || '8', 10),
        parity: document.getElementById('digitizerParity')?.value || 'N',
        stopbits: parseFloat(document.getElementById('digitizerStopBits')?.value || '1'),
        timeout: 10,
        nbytes: WIZARD_CAPTURE_BYTES,
    };
}

/** Alias used by devices.js for port lookup after save. */
function getDigitizerPortSettingsFromForm() {
    return _dpReadPortSettings();
}

async function _dpCaptureSample(portSettings) {
    const resp = await fetch('/api/digitizer/sample', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(portSettings),
    });
    return resp.json();
}

/**
 * Entry from the digitizer "Check & Save" button.
 * @param {(method:string, indexing:object, sampleHex?:string)=>Promise|void} finalizeCallback
 */
async function runDigitizerIndexCheckAndSave(finalizeCallback) {
    await refreshDigitizerCalibrationMinWeight();
    const portSettings = _dpReadPortSettings();
    if (!portSettings.port) {
        showToast('error', 'Validation Error', 'Please select a serial port');
        return;
    }
    const make = document.getElementById('digitizerMake')?.value.trim() || '';
    const model = document.getElementById('digitizerModel')?.value.trim() || '';
    if (typeof validateDeviceInfo === 'function' &&
        !validateDeviceInfo(make, model, 'Digitizer')) {
        return;
    }

    if (typeof showLoading === 'function') showLoading(true);
    try {
        const capture = await _dpCaptureSample(portSettings);
        if (capture.status !== 200) {
            showToast('error', 'Capture Failed', capture.message || 'Could not capture digitizer sample.');
            return;
        }
        showDigitizerIndexPickerModal(capture, portSettings, finalizeCallback, _dpState.savedIndexing);
    } catch (e) {
        console.error('[Digitizer Index] capture error', e);
        showToast('error', 'Capture Error', 'Unable to capture digitizer sample.');
    } finally {
        if (typeof showLoading === 'function') showLoading(false);
    }
}

// ---------------------------------------------------------------------------
// Modal DOM (created once, reused)
// ---------------------------------------------------------------------------

function _dpEnsureModal() {
    if (document.getElementById('digitizerIndexOverlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'digitizerIndexOverlay';
    overlay.className = 'custom-modal-overlay digitizer-index-overlay';
    overlay.style.display = 'none';
    overlay.innerHTML = `
        <div class="custom-modal digitizer-index-modal">
            <div class="custom-modal-header">
                <h3>Set Weight Byte Positions</h3>
            </div>
            <div class="custom-modal-body">
                <div class="digitizer-index-capture-info" id="digitizerIndexCaptureInfo"></div>
                <div class="digitizer-index-legend">
                    <span class="idx-legend idx-band-start">Frame start</span>
                    <span class="idx-legend idx-band-weight">Weight slice</span>
                    <span class="idx-legend idx-band-end">Frame end</span>
                </div>
                <div class="digitizer-index-ruler" id="digitizerIndexRuler"></div>
                <table class="digitizer-index-table" id="digitizerIndexTable">
                    <thead>
                        <tr>
                            <th>#</th><th>What to set</th><th>Use</th><th>Pos</th><th>Char</th>
                        </tr>
                    </thead>
                    <tbody id="digitizerIndexTableBody"></tbody>
                </table>
                <div class="digitizer-index-preview" id="digitizerIndexPreview">Preview: —</div>
                <div class="digitizer-index-hint" id="digitizerIndexHint">
                    Required: row 1 (start of weight message — 1st character), rows 3–4 (weight number).
                    Preview must be at least ${_dpCalibrationMinKg()} kg.
                </div>
                <div class="digitizer-index-error" id="digitizerIndexError"></div>
            </div>
            <div class="custom-modal-footer">
                <button class="btn btn-secondary" type="button" id="digitizerIndexCancelBtn">Cancel</button>
                <button class="btn btn-secondary" type="button" id="digitizerIndexRecaptureBtn">Recapture</button>
                <button class="btn btn-primary" type="button" id="digitizerIndexCheckBtn" disabled>Check</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    const confirm = document.createElement('div');
    confirm.id = 'digitizerIndexConfirmOverlay';
    confirm.className = 'custom-modal-overlay digitizer-index-confirm-overlay';
    confirm.style.display = 'none';
    confirm.innerHTML = `
        <div class="custom-modal digitizer-index-confirm-modal">
            <div class="custom-modal-header"><h3>Confirm Weight</h3></div>
            <div class="custom-modal-body">
                <p>Please confirm the weight shown now is the same as the digitizer display.</p>
                <div class="digitizer-index-confirm-weight" id="digitizerIndexConfirmWeight">—</div>
                <div class="digitizer-index-ruler" id="digitizerIndexConfirmRuler"></div>
            </div>
            <div class="custom-modal-footer">
                <button class="btn btn-secondary" type="button" id="digitizerIndexConfirmCancelBtn">Cancel</button>
                <button class="btn btn-primary" type="button" id="digitizerIndexConfirmBtn">Confirm</button>
            </div>
        </div>`;
    document.body.appendChild(confirm);

    document.getElementById('digitizerIndexCancelBtn').addEventListener('click', _dpCloseModal);
    document.getElementById('digitizerIndexRecaptureBtn').addEventListener('click', _dpRecapture);
    document.getElementById('digitizerIndexCheckBtn').addEventListener('click', _dpOnCheck);
}

// ---------------------------------------------------------------------------
// Open / render
// ---------------------------------------------------------------------------

function showDigitizerIndexPickerModal(captureResult, portSettings, onSave, savedIndexing) {
    _dpEnsureModal();
    _dpState.sampleHex = captureResult.sample_hex || '';
    _dpState.ruler = captureResult.ruler || null;
    _dpState.portSettings = portSettings;
    _dpState.onSave = onSave;
    _dpState.savedIndexing = savedIndexing || null;
    _dpState.picks = [null, null, null, null, null, null];

    const info = document.getElementById('digitizerIndexCaptureInfo');
    const ps = portSettings;
    info.textContent = `Captured ${captureResult.length} bytes from ${ps.port} @ ${ps.baud_rate} `
        + `${ps.bytesize}-${ps.parity}-${ps.stopbits}`;

    _dpRenderRuler('digitizerIndexRuler', _dpState.ruler, null);
    _dpRenderTable();

    document.getElementById('digitizerIndexError').textContent = '';
    document.getElementById('digitizerIndexOverlay').style.display = 'flex';

    if (savedIndexing) {
        restorePicksFromSavedIndexing(_dpState.sampleHex, savedIndexing).then(() => {
            _dpRenderTable();
            refreshDigitizerIndexPreview();
        });
    } else {
        refreshDigitizerIndexPreview();
    }
}

function _dpCloseModal() {
    const o = document.getElementById('digitizerIndexOverlay');
    if (o) o.style.display = 'none';
}

function _dpCloseConfirm() {
    const o = document.getElementById('digitizerIndexConfirmOverlay');
    if (o) o.style.display = 'none';
}

function _dpRenderRuler(containerId, ruler, highlights) {
    const container = document.getElementById(containerId);
    if (!container || !ruler) {
        if (container) container.innerHTML = '<em>No sample</em>';
        return;
    }
    const bands = {};
    if (highlights) {
        (highlights.frame_start || []).forEach(i => { bands[i] = 'idx-band-start'; });
        (highlights.weight || []).forEach(i => { bands[i] = 'idx-band-weight'; });
        (highlights.frame_end || []).forEach(i => { bands[i] = 'idx-band-end'; });
    }
    let html = '<div class="idx-ruler-track">';
    (ruler.bytes || []).forEach(b => {
        const band = bands[b.index] || '';
        html += `<div class="idx-col ${band}">`
            + `<div class="idx-col-index">${b.index}</div>`
            + `<div class="idx-col-data">${_dpEscape(b.repr)}</div>`
            + `</div>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

function _dpRenderTable() {
    const body = document.getElementById('digitizerIndexTableBody');
    const maxIdx = _dpState.ruler ? (_dpState.ruler.length - 1) : 0;
    let html = '';
    for (let r = 0; r < 6; r++) {
        const sl = r + 1;
        const required = _dpIsRequiredRow(r);
        const pick = _dpState.picks[r];
        const enabled = required || pick !== null;
        const bandClass = (r < 2) ? 'idx-band-start' : (r < 4 ? 'idx-band-weight' : 'idx-band-end');
        html += `<tr class="${bandClass}" data-row="${r}">`
            + `<td>${sl}</td>`
            + `<td>${DIGITIZER_INDEX_FRIENDLY_LABELS[r]}</td>`
            + `<td><input type="checkbox" class="dp-enable" data-row="${r}" `
            + `${enabled ? 'checked' : ''} ${required ? 'disabled' : ''}></td>`
            + `<td><input type="number" class="dp-index" data-row="${r}" min="0" max="${maxIdx}" `
            + `value="${pick !== null ? pick : ''}" ${enabled ? '' : 'disabled'}`
            + `${required ? ' required aria-required="true"' : ''}></td>`
            + `<td class="dp-char" data-row="${r}">${_dpCharAt(pick)}</td>`
            + `</tr>`;
    }
    body.innerHTML = html;

    body.querySelectorAll('.dp-enable').forEach(cb => {
        cb.addEventListener('change', _dpOnRowInput);
    });
    body.querySelectorAll('.dp-index').forEach(inp => {
        inp.addEventListener('input', _dpOnRowInput);
    });
}

function _dpCharAt(idx) {
    if (idx === null || idx === undefined || !_dpState.ruler) return '';
    const b = (_dpState.ruler.bytes || [])[idx];
    return b ? _dpEscape(b.repr) : '';
}

function _dpEscape(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// Input handling + preview
// ---------------------------------------------------------------------------

function _dpGatherPicks() {
    const picks = [null, null, null, null, null, null];
    const body = document.getElementById('digitizerIndexTableBody');
    if (!body) return picks;
    for (let r = 0; r < 6; r++) {
        const cb = body.querySelector(`.dp-enable[data-row="${r}"]`);
        const inp = body.querySelector(`.dp-index[data-row="${r}"]`);
        const required = _dpIsRequiredRow(r);
        const enabled = required || (cb && cb.checked);
        if (inp) inp.disabled = !enabled;
        if (enabled && inp && inp.value !== '') {
            const v = parseInt(inp.value, 10);
            picks[r] = Number.isNaN(v) ? null : v;
        }
    }
    return picks;
}

function _dpOnRowInput() {
    _dpState.picks = _dpGatherPicks();
    const body = document.getElementById('digitizerIndexTableBody');
    for (let r = 0; r < 6; r++) {
        const cell = body.querySelector(`.dp-char[data-row="${r}"]`);
        if (cell) cell.innerHTML = _dpCharAt(_dpState.picks[r]);
    }
    if (_dpState.previewTimer) clearTimeout(_dpState.previewTimer);
    _dpState.previewTimer = setTimeout(refreshDigitizerIndexPreview, 200);
}

async function refreshDigitizerIndexPreview() {
    _dpState.picks = _dpGatherPicks();
    let data;
    try {
        const resp = await fetch('/api/digitizer/index-preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sample_hex: _dpState.sampleHex, picks: _dpState.picks }),
        });
        data = await resp.json();
    } catch (e) {
        console.error('[Digitizer Index] preview error', e);
        return;
    }
    _dpState.lastPreview = data;
    _dpApplyPreview(data);
}

function _dpApplyPreview(data) {
    const previewEl = document.getElementById('digitizerIndexPreview');
    const errorEl = document.getElementById('digitizerIndexError');
    const checkBtn = document.getElementById('digitizerIndexCheckBtn');

    _dpRenderRuler('digitizerIndexRuler', _dpState.ruler, data.highlights);
    _dpMarkDuplicates();

    if (_dpMissingRequiredPicks(_dpState.picks)) {
        errorEl.textContent =
            'Set row 1 (start of weight message — 1st character) and rows 3–4 (weight number).';
        previewEl.textContent = 'Preview: —';
        checkBtn.disabled = true;
        return;
    }

    if (data.validation_error) {
        errorEl.textContent = data.validation_error;
        previewEl.textContent = 'Preview: —';
        checkBtn.disabled = true;
        return;
    }
    errorEl.textContent = '';

    const weight = data.weight;
    if (weight === null || weight === undefined) {
        previewEl.textContent = 'Preview: no weight (check positions)';
        checkBtn.disabled = true;
        return;
    }
    previewEl.textContent = `Preview: ${weight} kg`;
    const minKg = _dpCalibrationMinKg();
    const ok = weight >= minKg;
    checkBtn.disabled = !ok;
    previewEl.classList.toggle('dp-weight-ok', ok);
    previewEl.classList.toggle('dp-weight-low', !ok);
}

function _dpMarkDuplicates() {
    const body = document.getElementById('digitizerIndexTableBody');
    if (!body) return;
    const counts = {};
    _dpState.picks.forEach(p => { if (p !== null) counts[p] = (counts[p] || 0) + 1; });
    for (let r = 0; r < 6; r++) {
        const inp = body.querySelector(`.dp-index[data-row="${r}"]`);
        if (!inp) continue;
        const p = _dpState.picks[r];
        const dup = p !== null && counts[p] > 1;
        inp.classList.toggle('digitizer-index-duplicate', dup);
    }
}

// ---------------------------------------------------------------------------
// Recapture / Check / Confirm
// ---------------------------------------------------------------------------

async function _dpRecapture() {
    if (typeof showLoading === 'function') showLoading(true);
    try {
        const capture = await _dpCaptureSample(_dpState.portSettings);
        if (capture.status !== 200) {
            showToast('error', 'Capture Failed', capture.message || 'Could not capture sample.');
            return;
        }
        _dpState.sampleHex = capture.sample_hex || '';
        _dpState.ruler = capture.ruler || null;
        const info = document.getElementById('digitizerIndexCaptureInfo');
        const ps = _dpState.portSettings;
        info.textContent = `Captured ${capture.length} bytes from ${ps.port} @ ${ps.baud_rate} `
            + `${ps.bytesize}-${ps.parity}-${ps.stopbits}`;
        _dpRenderTable();
        refreshDigitizerIndexPreview();
    } catch (e) {
        console.error('[Digitizer Index] recapture error', e);
        showToast('error', 'Capture Error', 'Unable to recapture sample.');
    } finally {
        if (typeof showLoading === 'function') showLoading(false);
    }
}

async function runDigitizerIndexLiveCheck(portSettings) {
    const capture = await _dpCaptureSample(portSettings);
    if (capture.status !== 200) {
        return { ok: false, message: capture.message || 'Capture failed.' };
    }
    let preview;
    try {
        const resp = await fetch('/api/digitizer/index-preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sample_hex: capture.sample_hex, picks: _dpState.picks }),
        });
        preview = await resp.json();
    } catch (e) {
        return { ok: false, message: 'Live verify failed.' };
    }
    if (preview.validation_error) {
        return { ok: false, message: preview.validation_error };
    }
    if (preview.weight === null || preview.weight === undefined) {
        return { ok: false, message: 'No weight parsed from the live sample. Check positions.' };
    }
    const minKg = _dpCalibrationMinKg();
    if (!(preview.weight >= minKg)) {
        return {
            ok: false,
            message: `Live weight ${preview.weight} kg must be at least ${minKg} kg.`,
        };
    }
    return { ok: true, weight: preview.weight, indexing: preview.indexing, ruler: capture.ruler };
}

async function _dpOnCheck() {
    if (typeof showLoading === 'function') showLoading(true);
    try {
        const result = await runDigitizerIndexLiveCheck(_dpState.portSettings);
        if (!result.ok) {
            document.getElementById('digitizerIndexError').textContent = result.message;
            return;
        }
        showDigitizerIndexConfirmModal(
            result,
            async () => {
                _dpCloseConfirm();
                _dpCloseModal();
                if (typeof _dpState.onSave === 'function') {
                    await _dpState.onSave('index_based', result.indexing, _dpState.sampleHex);
                }
            },
            () => { _dpCloseConfirm(); }
        );
    } catch (e) {
        console.error('[Digitizer Index] check error', e);
        document.getElementById('digitizerIndexError').textContent = 'Live check failed.';
    } finally {
        if (typeof showLoading === 'function') showLoading(false);
    }
}

function showDigitizerIndexConfirmModal(verifyResult, onConfirm, onCancel) {
    _dpEnsureModal();
    document.getElementById('digitizerIndexConfirmWeight').textContent = `Live weight: ${verifyResult.weight} kg`;
    _dpRenderRuler('digitizerIndexConfirmRuler', verifyResult.ruler, null);
    const overlay = document.getElementById('digitizerIndexConfirmOverlay');
    overlay.style.display = 'flex';

    const confirmBtn = document.getElementById('digitizerIndexConfirmBtn');
    const cancelBtn = document.getElementById('digitizerIndexConfirmCancelBtn');
    const newConfirm = confirmBtn.cloneNode(true);
    const newCancel = cancelBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirm, confirmBtn);
    cancelBtn.parentNode.replaceChild(newCancel, cancelBtn);
    newConfirm.addEventListener('click', onConfirm);
    newCancel.addEventListener('click', onCancel);
}

// ---------------------------------------------------------------------------
// Saved parsing panel + restore
// ---------------------------------------------------------------------------

async function restorePicksFromSavedIndexing(sampleHex, indexing) {
    try {
        const resp = await fetch('/api/digitizer/index-picks-from-indexing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sample_hex: sampleHex, indexing }),
        });
        const data = await resp.json();
        if (data.status === 200 && Array.isArray(data.picks)) {
            _dpState.picks = data.picks.map(v => (v === null ? null : parseInt(v, 10)));
        }
    } catch (e) {
        console.error('[Digitizer Index] restore picks error', e);
    }
    return _dpState.picks;
}

function updateDigitizerSavedConfig(config) {
    const panel = document.getElementById('digitizerSavedParsing');
    if (!panel) return;
    const dig = (config && config.digitizer) || config || {};
    if (dig.conversion_method === 'index_based' && dig.indexing) {
        _dpState.savedIndexing = dig.indexing;
        const ix = dig.indexing;
        panel.style.display = 'block';
        panel.innerHTML = `
            <div class="digitizer-saved-title">Saved Weight Parsing (index based)</div>
            <table class="digitizer-saved-table">
                <tr><td>Frame start</td><td>${_dpEscape(ix.frame_start_char ?? '—')}</td></tr>
                <tr><td>Frame end</td><td>${_dpEscape(ix.frame_end_char ?? '—')}</td></tr>
                <tr><td>Weight start (offset)</td><td>${ix.weight_start}</td></tr>
                <tr><td>Weight end (exclusive)</td><td>${ix.weight_end}</td></tr>
                <tr><td>Decimals / Scale</td><td>${ix.decimals ?? 0} / ${ix.scale ?? 1}</td></tr>
            </table>`;
    } else {
        _dpState.savedIndexing = null;
        panel.style.display = 'none';
        panel.innerHTML = '';
    }
}
