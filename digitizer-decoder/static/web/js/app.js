/* GMDC Digitizer Decoder — operator dashboard */
(function () {
    'use strict';

    var state = {
        sampleHex: '',
        picks: [null, null, null, null, null, null],
        cells: [],
        pollTimer: null,
        adminAuthenticated: false,
        configLoaded: false,
        mqttClient: null,
        mqttStatusTopic: 'gmdc/digitizer/status',
        mqttConnected: false,
        mqttConnecting: false,
        mqttConfigIndex: 0,
    };

    var MQTT_WS_CONFIGS = [
        { port: 9001, path: '/' },
        { port: 9001, path: '/mqtt' },
        { port: 9001, path: '/ws' },
    ];

    function $(id) { return document.getElementById(id); }

    function setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        try { localStorage.setItem('gmdc_ui_theme', theme); } catch (e) {}
        var btn = $('theme-toggle-btn');
        if (btn) btn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    }

    function tickClock() {
        var el = $('current-time');
        if (!el) return;
        el.textContent = new Date().toLocaleTimeString();
    }

    function setBadge(badgeId, textId, connected, label) {
        var badge = $(badgeId);
        var text = $(textId);
        if (text) text.textContent = label;
        if (!badge) return;
        badge.classList.remove('status-connected', 'status-disconnected', 'status-warning');
        badge.classList.add(connected ? 'status-connected' : 'status-disconnected');
    }

    async function api(path, opts) {
        var res = await fetch(path, Object.assign({
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        }, opts || {}));
        var data = await res.json().catch(function () { return {}; });
        return { ok: res.ok, status: res.status, data: data };
    }

    function setAuthUi(loggedIn) {
        state.adminAuthenticated = !!loggedIn;
        var loginBtn = $('login-button');
        var configBtn = $('config-button');
        if (loginBtn) {
            loginBtn.hidden = false;
            loginBtn.textContent = loggedIn ? 'Logout' : 'Login';
            loginBtn.classList.toggle('is-logout', !!loggedIn);
        }
        if (configBtn) configBtn.hidden = !loggedIn;
        var hint = $('setup-hint');
        if (hint) {
            hint.hidden = !!loggedIn;
        }
    }

    function openModal(id) {
        var m = $(id);
        if (!m) return;
        m.classList.add('active');
        m.classList.add('show');
    }

    function closeModal(id) {
        var m = $(id);
        if (!m) return;
        m.classList.remove('active');
        m.classList.remove('show');
    }

    function syncModeFields(mode) {
        var selected = mode || ($('cfg-mode') && $('cfg-mode').value) || 'api';
        if (selected !== 'api' && selected !== 'mqtt') selected = 'api';
        if ($('cfg-mode')) $('cfg-mode').value = selected;

        var apiBtn = $('mode-btn-api');
        var mqttBtn = $('mode-btn-mqtt');
        if (apiBtn) apiBtn.classList.toggle('is-active', selected === 'api');
        if (mqttBtn) mqttBtn.classList.toggle('is-active', selected === 'mqtt');

        var apiPanel = $('api-fields');
        var mqttPanel = $('mqtt-fields');
        if (apiPanel) apiPanel.classList.toggle('is-hidden', selected !== 'api');
        if (mqttPanel) mqttPanel.classList.toggle('is-hidden', selected !== 'mqtt');
    }

    function setCommunicationMode(mode) {
        syncModeFields(mode);
    }

    function picksSummary() {
        var labels = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6'];
        var parts = [];
        state.picks.forEach(function (p, i) {
            if (p !== null && p !== undefined) parts.push(labels[i] + '=' + p);
        });
        $('picks-summary').textContent = parts.length ? ('Picks: ' + parts.join(', ')) : 'Picks: —';
        renderBytes();
    }

    function renderBytes() {
        var grid = $('byte-grid');
        if (!grid) return;
        grid.innerHTML = '';
        state.cells.forEach(function (cell) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'dig-byte';
            btn.title = 'Index ' + cell.index;
            btn.innerHTML = '<span>' + cell.index + '</span><strong>' + (cell.repr || cell.hex) + '</strong>';
            state.picks.forEach(function (p, row) {
                if (p === cell.index) btn.classList.add('is-r' + (row + 1));
            });
            btn.addEventListener('click', function () {
                var row = parseInt($('pick-row').value, 10);
                state.picks[row] = cell.index;
                picksSummary();
            });
            grid.appendChild(btn);
        });
    }

    function fillPorts(ports, selected) {
        var sel = $('cfg-port');
        sel.innerHTML = '';
        var placeholder = document.createElement('option');
        placeholder.value = '--Select--';
        placeholder.textContent = '--Select--';
        sel.appendChild(placeholder);
        (ports || []).forEach(function (p) {
            var opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            sel.appendChild(opt);
        });
        if ((!ports || !ports.length) && (!selected || selected === '--Select--')) {
            var empty = document.createElement('option');
            empty.value = '';
            empty.textContent = 'No ports found';
            empty.disabled = true;
            sel.appendChild(empty);
        }
        if (selected && selected !== '--Select--') {
            sel.value = selected;
            if (sel.value !== selected) {
                var orphan = document.createElement('option');
                orphan.value = selected;
                orphan.textContent = selected + ' (saved)';
                orphan.selected = true;
                sel.appendChild(orphan);
            }
        } else {
            sel.value = '--Select--';
        }
    }

    async function refreshPortsList() {
        var btn = $('btn-refresh-ports');
        var keep = ($('cfg-port') && $('cfg-port').value) || '--Select--';
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Scanning…';
        }
        try {
            var portsRes = await api('/api/ports');
            if (portsRes.status === 401) {
                setAuthUi(false);
                openModal('login-modal');
                return;
            }
            if (!portsRes.ok) {
                console.error('Port scan failed', portsRes);
                return;
            }
            fillPorts((portsRes.data && portsRes.data.ports) || [], keep);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Refresh ports';
            }
        }
    }

    function applyConfigToForm(cfg) {
        cfg = cfg || {};
        var comm = cfg.communication || {};
        var api = comm.api || {};
        var mqtt = comm.mqtt || {};
        setSelectValue('cfg-baud', cfg.baud_rate);
        setSelectValue('cfg-databits', cfg.data_bits);
        setSelectValue('cfg-parity', cfg.parity);
        setSelectValue('cfg-stopbits', cfg.stop_bits);
        $('cfg-mode').value = (comm.mode === 'mqtt') ? 'mqtt' : 'api';
        $('cfg-api-host').value = api.host || '0.0.0.0';
        $('cfg-api-port').value = api.port || 8800;
        $('cfg-api-path').value = api.path || '/read_stable_weight';
        $('cfg-mqtt-host').value = mqtt.broker_host || '';
        $('cfg-mqtt-port').value = mqtt.broker_port || 1883;
        $('cfg-mqtt-user').value = mqtt.username || '';
        $('cfg-mqtt-pass').value = mqtt.password || '';
        $('cfg-mqtt-pub').value = mqtt.topic_publish || '';
        $('cfg-mqtt-sub').value = mqtt.topic_subscribe || '';
        $('cfg-mqtt-client').value = mqtt.client_id || 'gmdc-digitizer-decoder';
        syncModeFields($('cfg-mode').value);
        if (cfg.calibration_sample_hex) {
            state.sampleHex = cfg.calibration_sample_hex;
        }
    }

    function setSelectValue(id, value) {
        var el = $(id);
        if (!el) return;
        var v = (value === null || value === undefined || value === '') ? '--Select--' : String(value);
        el.value = v;
        if (el.value !== v) {
            var opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v;
            opt.selected = true;
            el.appendChild(opt);
        }
    }

    function collectConfigPatch() {
        function numOrSelect(id) {
            var v = $(id).value;
            if (v === '--Select--' || v === '') return '--Select--';
            if (id === 'cfg-stopbits') return parseFloat(v);
            if (id === 'cfg-baud' || id === 'cfg-databits') return parseInt(v, 10);
            return v;
        }
        return {
            port: $('cfg-port').value || '--Select--',
            baud_rate: numOrSelect('cfg-baud'),
            data_bits: numOrSelect('cfg-databits'),
            parity: $('cfg-parity').value || '--Select--',
            stop_bits: numOrSelect('cfg-stopbits'),
            communication: {
                mode: $('cfg-mode').value,
                api: {
                    host: $('cfg-api-host').value.trim() || '0.0.0.0',
                    port: parseInt($('cfg-api-port').value, 10) || 8800,
                    path: $('cfg-api-path').value.trim() || '/read_stable_weight',
                },
                mqtt: {
                    broker_host: $('cfg-mqtt-host').value.trim(),
                    broker_port: parseInt($('cfg-mqtt-port').value, 10) || 1883,
                    username: $('cfg-mqtt-user').value,
                    password: $('cfg-mqtt-pass').value,
                    topic_publish: $('cfg-mqtt-pub').value.trim(),
                    topic_subscribe: $('cfg-mqtt-sub').value.trim(),
                    client_id: $('cfg-mqtt-client').value.trim() || 'gmdc-digitizer-decoder',
                },
            },
        };
    }

    async function refreshStatus() {
        var res = await api('/api/status');
        if (!res.ok) return;
        applyStatusPayload(res.data || {});
        ensureMqttLive((res.data && res.data.mqtt) || {});
    }

    function applyStatusPayload(s) {
        s = s || {};
        if (typeof s.admin_authenticated === 'boolean') {
            setAuthUi(s.admin_authenticated);
        }
        if (s.version) {
            $('app-version').textContent = 'v' + s.version;
        }

        var live = s.current_weight;
        var liveEl = $('live-weight');
        if (live === null || live === undefined || live === '') {
            liveEl.textContent = '--';
            liveEl.classList.remove('is-unstable', 'is-stable-wt');
        } else {
            liveEl.textContent = Number(live).toFixed(2);
            liveEl.classList.toggle('is-stable-wt', !!s.stable);
            liveEl.classList.toggle('is-unstable', !s.stable);
        }

        $('stable-meta').textContent = s.stable
            ? ('Stable: ' + Number(s.stable_weight).toFixed(2) + ' kg (' + (s.stable_count || '--') + ')')
            : ('Waiting for stable… (' + (s.stable_count || '--') + ')');
        $('raw-line').textContent = s.last_raw || '';

        setBadge('serial-status-badge', 'serial-status-text', !!s.serial_connected,
            s.serial_connected ? 'Connected' : 'Disconnected');
        $('serial-details').textContent = 'Port: ' + ((s.serial && s.serial.port) || '--');

        var mode = (s.communication_mode || 'api').toUpperCase();
        var transportOk = !!s.mqtt_connected || state.mqttConnected;
        setBadge('transport-status-badge', 'transport-mode-text', transportOk, mode);
        $('transport-details').textContent = s.mqtt_status
            || (state.mqttConnected ? 'MQTT live' : 'MQTT connecting…');

        setBadge('calib-status-badge', 'calib-status-text', !!s.calibrated,
            s.calibrated ? 'Calibrated' : 'Not calibrated');

        var sys = $('status-text');
        if (s.serial_connected && s.calibrated) {
            sys.textContent = 'System Operational';
        } else if (!s.calibrated) {
            sys.textContent = 'Configuration required';
        } else {
            sys.textContent = 'Serial disconnected';
        }

        if (s.mqtt && s.mqtt.topic_status) {
            state.mqttStatusTopic = s.mqtt.topic_status;
        }
    }

    function ensureMqttLive(mqttCfg) {
        mqttCfg = mqttCfg || {};
        if (mqttCfg.topic_status) {
            state.mqttStatusTopic = mqttCfg.topic_status;
        }
        if (state.mqttClient || state.mqttConnecting) return;
        connectMqttStatus();
    }

    function resolvePahoClientClass() {
        if (typeof Paho === 'undefined') return null;
        if (Paho.Client) return Paho.Client;
        if (Paho.MQTT && Paho.MQTT.Client) return Paho.MQTT.Client;
        return null;
    }

    function connectMqttStatus() {
        var ClientClass = resolvePahoClientClass();
        if (!ClientClass) {
            console.warn('Paho MQTT not loaded — retrying MQTT (no HTTP poll)');
            setTimeout(connectMqttStatus, 2000);
            return;
        }

        var host = (window.location && window.location.hostname) || 'localhost';
        var cfg = MQTT_WS_CONFIGS[state.mqttConfigIndex % MQTT_WS_CONFIGS.length];
        var clientId = 'digitizer_ui_' + Math.random().toString(16).slice(2, 10);
        var client;
        state.mqttConnecting = true;

        try {
            // Constructor: new Paho.Client(host, port, path, clientId)
            client = new ClientClass(host, Number(cfg.port), cfg.path, clientId);
        } catch (e) {
            try {
                client = new ClientClass(host, Number(cfg.port), clientId);
            } catch (e2) {
                console.error('MQTT client create failed', e2);
                state.mqttConnecting = false;
                state.mqttConfigIndex += 1;
                setTimeout(connectMqttStatus, 1500);
                return;
            }
        }

        state.mqttClient = client;
        client.onConnectionLost = function (resp) {
            console.warn('MQTT connection lost', resp && resp.errorMessage);
            state.mqttConnected = false;
            state.mqttClient = null;
            state.mqttConnecting = false;
            setTimeout(connectMqttStatus, 1500);
        };
        client.onMessageArrived = function (message) {
            try {
                var payload = JSON.parse(message.payloadString || '{}');
                applyStatusPayload(payload);
            } catch (err) {
                console.warn('Bad MQTT status payload', err);
            }
        };

        console.log(
            'MQTT connecting ws://' + host + ':' + cfg.port + cfg.path +
            ' topic=' + state.mqttStatusTopic
        );
        client.connect({
            timeout: 5,
            useSSL: false,
            keepAliveInterval: 30,
            cleanSession: true,
            mqttVersion: 4,
            onSuccess: function () {
                state.mqttConnected = true;
                state.mqttConnecting = false;
                state.mqttConfigIndex = 0;
                console.log('MQTT connected — live status via', state.mqttStatusTopic);
                try {
                    client.subscribe(state.mqttStatusTopic);
                } catch (err) {
                    console.warn('MQTT subscribe failed', err);
                }
                // Never keep HTTP /api/status polling once MQTT is live
                if (state.pollTimer) {
                    clearInterval(state.pollTimer);
                    state.pollTimer = null;
                }
            },
            onFailure: function (err) {
                console.warn('MQTT connect failed', err && err.errorMessage);
                state.mqttConnected = false;
                state.mqttClient = null;
                state.mqttConnecting = false;
                state.mqttConfigIndex += 1;
                setTimeout(connectMqttStatus, 1500);
            },
        });
    }

    async function loadConfigIntoModal() {
        var portsRes = await api('/api/ports');
        if (portsRes.status === 401) {
            setAuthUi(false);
            openModal('login-modal');
            return false;
        }
        var cfgRes = await api('/api/config');
        if (!cfgRes.ok) return false;
        var cfg = (cfgRes.data && cfgRes.data.config) || {};
        fillPorts((portsRes.data && portsRes.data.ports) || [], cfg.port);
        applyConfigToForm(cfg);

        var picksRes = await api('/api/calibration/picks');
        if (picksRes.ok && picksRes.data) {
            if (Array.isArray(picksRes.data.picks)) state.picks = picksRes.data.picks;
            if (picksRes.data.sample_hex) {
                state.sampleHex = picksRes.data.sample_hex;
                try {
                    var bytes = picksRes.data.sample_hex.match(/.{1,2}/g) || [];
                    state.cells = bytes.map(function (h, i) {
                        var n = parseInt(h, 16);
                        var ch = (n >= 32 && n < 127) ? String.fromCharCode(n) : h;
                        return { index: i, hex: h, repr: ch };
                    });
                } catch (e) { state.cells = []; }
            }
            picksSummary();
        }
        state.configLoaded = true;
        return true;
    }

    async function onCapture() {
        $('preview-result').textContent = 'Capturing…';
        var res = await api('/api/capture', { method: 'POST', body: JSON.stringify({ bytes: 40 }) });
        if (!res.ok) {
            $('preview-result').textContent = (res.data && res.data.message) || 'Capture failed';
            return;
        }
        state.sampleHex = res.data.sample_hex || '';
        state.cells = res.data.cells || [];
        state.picks = [null, null, null, null, null, null];
        picksSummary();
        $('preview-result').textContent = 'Captured ' + (res.data.length || 0) + ' bytes — select R1, R3, R4';
    }

    async function onPreview() {
        var res = await api('/api/calibration/preview', {
            method: 'POST',
            body: JSON.stringify({ sample_hex: state.sampleHex, picks: state.picks }),
        });
        if (!res.ok) {
            $('preview-result').textContent = (res.data && res.data.message) || 'Preview failed';
            return;
        }
        var w = res.data.weight;
        $('preview-result').textContent = (w === null || w === undefined)
            ? 'Could not extract weight from picks'
            : ('Preview weight: ' + Number(w).toFixed(2) + ' kg');
    }

    async function onSave(ev) {
        ev.preventDefault();
        $('save-result').textContent = 'Saving…';
        var patch = collectConfigPatch();
        if (state.sampleHex && state.picks[0] !== null && state.picks[2] !== null && state.picks[3] !== null) {
            var cal = await api('/api/calibration/save', {
                method: 'POST',
                body: JSON.stringify({
                    sample_hex: state.sampleHex,
                    picks: state.picks,
                    serial: {
                        port: patch.port,
                        baud_rate: patch.baud_rate,
                        data_bits: patch.data_bits,
                        parity: patch.parity,
                        stop_bits: patch.stop_bits,
                    },
                }),
            });
            if (!cal.ok) {
                $('save-result').textContent = (cal.data && cal.data.message) || 'Calibration save failed';
                return;
            }
        }
        var res = await api('/api/config', {
            method: 'POST',
            body: JSON.stringify(patch),
        });
        if (!res.ok) {
            $('save-result').textContent = (res.data && res.data.message) || 'Save failed';
            return;
        }
        $('save-result').textContent = 'Saved. Transport: ' +
            ((res.data.snapshot && res.data.snapshot.communication_mode) || patch.communication.mode);
        await refreshStatus();
    }

    async function onTestWeight() {
        $('save-result').textContent = 'Waiting for stable weight…';
        var res = await api('/read_stable_weight', { method: 'POST', body: '{}' });
        if (res.data && res.data.statusCode === 200) {
            $('save-result').textContent = 'Stable weight: ' + Number(res.data.stable_weight).toFixed(2) + ' kg';
        } else {
            $('save-result').textContent = (res.data && (res.data.message || JSON.stringify(res.data))) || 'Failed';
        }
        await refreshStatus();
    }

    async function onLoginSubmit(ev) {
        ev.preventDefault();
        $('login-error').hidden = true;
        var res = await api('/api/login', {
            method: 'POST',
            body: JSON.stringify({
                username: $('login-username').value,
                password: $('login-password').value,
            }),
        });
        if (!res.ok) {
            $('login-error').hidden = false;
            $('login-error').textContent = (res.data && res.data.message) || 'Login failed';
            return;
        }
        closeModal('login-modal');
        setAuthUi(true);
        $('login-password').value = '';
        var ok = await loadConfigIntoModal();
        if (ok) openModal('config-modal');
    }

    async function onLoginButton() {
        if (state.adminAuthenticated) {
            await api('/api/logout', { method: 'POST', body: '{}' });
            setAuthUi(false);
            closeModal('config-modal');
            return;
        }
        $('login-error').hidden = true;
        openModal('login-modal');
        setTimeout(function () { $('login-username').focus(); }, 50);
    }

    async function onConfigButton() {
        if (!state.adminAuthenticated) {
            openModal('login-modal');
            return;
        }
        var ok = await loadConfigIntoModal();
        if (ok) openModal('config-modal');
    }

    function bind() {
        $('theme-toggle-btn').addEventListener('click', function () {
            var cur = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            setTheme(cur === 'dark' ? 'light' : 'dark');
        });
        $('login-button').addEventListener('click', onLoginButton);
        $('login-cancel-btn').addEventListener('click', function () { closeModal('login-modal'); });
        $('login-form').addEventListener('submit', onLoginSubmit);
        $('login-modal').addEventListener('click', function (e) {
            if (e.target === $('login-modal')) closeModal('login-modal');
        });
        $('config-button').addEventListener('click', onConfigButton);
        $('config-close-btn').addEventListener('click', function () { closeModal('config-modal'); });
        $('config-modal').addEventListener('click', function (e) {
            if (e.target === $('config-modal')) closeModal('config-modal');
        });
        $('cfg-mode').addEventListener('change', function () {
            syncModeFields($('cfg-mode').value);
        });
        document.querySelectorAll('.dig-mode-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setCommunicationMode(btn.getAttribute('data-mode') || 'api');
            });
        });
        syncModeFields('api');
        $('btn-capture').addEventListener('click', onCapture);
        $('btn-preview').addEventListener('click', onPreview);
        $('btn-refresh-ports').addEventListener('click', function () {
            refreshPortsList().catch(function (err) { console.error(err); });
        });
        $('config-form').addEventListener('submit', onSave);
        $('btn-test-weight').addEventListener('click', onTestWeight);
        setInterval(tickClock, 1000);
        tickClock();
    }

    document.addEventListener('DOMContentLoaded', function () {
        var saved = 'light';
        try { saved = localStorage.getItem('gmdc_ui_theme') || 'light'; } catch (e) {}
        setTheme(saved === 'dark' ? 'dark' : 'light');
        setAuthUi(false);
        bind();
        // One HTTP bootstrap, then live updates over MQTT (ws :9001)
        refreshStatus().catch(function (err) {
            console.error(err);
            $('status-text').textContent = 'Dashboard load failed';
        });
    });
})();
