# Application analysis request
_Exported on 05/09/2026 at 20:45:51 GMT+5:30 from Cursor (3.19.7)_

---

**User**

Please anaylse this entire application. It was made with your help in another laptop, and you can find the chat transcript here: @cursor_gmdc_project_flow_development.md 

---

**Cursor**

I'll start by reading the prior chat transcript and mapping the project so the analysis covers how the app was built and how it works now.

The transcript outlines a multi-checkpoint GMDC pipeline. Next I’ll map the live code against that history so the analysis reflects what actually shipped.

I'll read the core workflows, configs, and later transcript decisions so the review matches both the original plan and the code on disk.

The planned pipeline is larger than what’s on disk. I’ll measure the three apps, their shared dependencies, and the later transcript decisions next.

The three runtimes share a Flask + FSM pattern. Next I’ll compare APIs, configs, and how much of the original six-checkpoint plan actually landed.

I have a clear picture of the three runtimes, the missing shared library, and the original seven-checkpoint plan. I’ll put the review in a canvas so you can scan architecture, gaps, and risks beside the chat.

This workspace is a **partial copy** of the GMDC yard-automation system: three Flask runtimes for a seven-site truck pipeline, and the shared library they all import is not here.

I put the full review in [GMDC application analysis](/Users/csmtech/.cursor/projects/Users-csmtech-Desktop-new-IoT/canvases/gmdc-application-analysis.canvas.tsx) so you can open it beside the chat (a canvas is a live panel for structured reviews like this — tabs, pipeline map, tables). Summary of what is actually on disk:

**What it is.** A Gujarat Mineral Development Corporation IoT line: RFID, ANPR, Modbus traffic lights/booms/sensors, Oracle OCI, and an operator dashboard over MQTT. The planned truck path is Mines Entry → Tare weighbridge → Tracking-1 → Vadaghat → Tracking-2 → Gross weighbridge → Mines Exit.

**What is in this folder.** Three apps, all the same shape (Flask + threaded FSM + `iot_configuration.json`):

| App | Role | Idle | Cycle start |
|---|---|---|---|
| `Mine-entry/` v1.0.0 | Checkpoint | TL red, boom closed, RFID scanning | Tag on `/rfid_data` |
| `Tracking-point-1/` v1.0.0 | Same FSM, different OCI URLs | Same | Same |
| `TareWb-App/` v0.1.0 | Weighbridge (also Vadaghat/Gross via config) | Entry green/open, RFID off | Entry sensor, then weight &gt; 5 t, then RFID |

Tracking-1 is a near-clone of Mines Entry. Vadaghat and Gross are **not** separate apps — they are JSON overlays on TareWb-App (`iot_configuration-vadhghat.json`, `iot_configuration-gross.json`) plus the `T|` / `V|` / `G|` prefix on `truck_details`.

**What is missing from this laptop.** `gmdc_common` (every app imports it — hardware, FSM base, RFID cloud, display), `checkpoint-config/` (the commissioning wizard), `digitizer-app/` (the `/read_stable_weight` service), plus Tracking-2 and Mines Exit. Until `gmdc_common` is copied and installed with `pip install -e`, none of these runtimes will import.

**What is solid.** Boom does not open unless OCI `boom-close` returns status 200. ANPR `0/1/2` and `vehicleStatus` are explicit. Weighbridge RTO bands and bidirectional lanes are implemented and tested (~218 unit tests).

**What to fix next.** Copy `gmdc_common` first; then clone Tracking-2 / Mines Exit from the existing checkpoint app; move passwords out of `iot_configuration.json`; put auth on `/api/reset` and `/api/free-pass`. Mines Entry’s `/api/simulate-exit` is not demo-gated, unlike the weighbridge simulate routes.

---

**User**

<timestamp>Wednesday, Sep 2, 2026, 11:31 AM (UTC+5:30)</timestamp>
<system_notification>
The following task has finished. If you were already aware, ignore this notification and do not restate prior responses.

<task>
kind: subagent
status: success
task_id: 81e21b15-0ce4-458f-9ccf-c4d07765862c
title: Explore GMDC apps
tool_call_id: call-c80a74c9-3c09-4d35-a5fc-453a3abeeaef-15
fc_ba372de6-518b-9064-b2b9-c5c06373ff2c_0
agent_id: 81e21b15-0ce4-458f-9ccf-c4d07765862c
detail: <user_visible_high_level_summary>
The GMDC IoT workspace has three checkpoint apps (~17,900 Python LOC total) that all depend on an external `gmdc_common` package not present here. Mine-entry and Tracking-point-1 share the same RFID→OCI→ANPR→boom-close FSM with different OCI API paths; TareWb-App adds weighbridge flow with digitizer, RTO tolerance, bidirectional lane support, and top-camera capture. Missing from the repo: `gmdc_common`, `checkpoint-config`, standalone digitizer-app, Tracking-point-2, Mines-exit, and separate Gross/Vadaghat apps (config variants only).
</user_visible_high_level_summary>
<response>
# GMDC IoT Architecture Analysis

**Workspace:** `/Users/csmtech/Desktop/new-IoT` 
**Total Python LOC (approx.):** Mine-entry 5,630 | Tracking-point-1 5,671 | TareWb-App 6,613 | **~17,914** 
**Chat transcript:** `/Users/csmtech/Desktop/new-IoT/cursor_gmdc_project_flow_development.md` (5,908 lines) — documents intended `gmdc_common` extraction, TareWb scaffold, bidirectional WB, RTO tolerance, and checkpoint-config wizard plans on a Windows dev machine.

---

## 1. Directory Inventory

| Path | Status | Notes |
|------|--------|-------|
| `Mine-entry/` | **Present** | Mines entry checkpoint runtime |
| `Tracking-point-1/` | **Present** | Tracking point #1 runtime |
| `TareWb-App/` | **Present** | Tare / weighbridge runtime (also serves gross & vadaghat via config) |
| `gmdc_common/` | **Missing** | Required at runtime; all apps import it |
| `checkpoint-config/` | **Missing** | Referenced as canonical config source; TareWb falls back to local JSON |
| `digitizer-app/` | **Missing** | TareWb expects HTTP `POST /read_stable_weight`; stub at `TareWb-App/demo-app/apis.py` only |
| `Tracking-point-2/` | **Missing** | Not in workspace |
| `Mines-exit/` | **Missing** | Not in workspace |
| `Vadaghat/` (app) | **Missing as app** | Config variant: `TareWb-App/iot_configuration-vadhghat.json` (`checkpoint_type: vadghat_wb`) |
| `Gross WB/` (app) | **Missing as app** | Config variant: `TareWb-App/iot_configuration-gross.json` (`checkpoint_type: gross_wb`) |
| `cursor_gmdc_project_flow_development.md` | **Present** | Full project history |
| `wb-old/` | **Missing** | Referenced in TareWb voice path fallback |

**Root contents:** only the three apps + transcript (no monorepo wrapper, no shared package).

---

## 2. Per-App Analysis

### 2.1 Mine-entry

#### Bootstrap (`Mine-entry/main.py`, 288 lines)
1. `setup_logging()` → `load_settings()` → singleton `AppContext`
2. `StateMachine`, `TransactionStore`, `OCIClient`
3. MQTT display via `create_display_service`
4. Hardware: Modbus I/O, **entry-only** TL + boom, entry sensor, single RFID (`entry_a`)
5. `MinesEntryWorkflow`, idle hardware (TL red, boom closed)
6. `FrontendMqtt` (WS broker port 9001), device monitor
7. Sensor poller start, RFID cloud prepare at IDLE (`login→mode→start`)
8. Flask API in background thread; main loop sleeps until SIGINT/SIGTERM

#### FSM (`config/constants.py` + `core/state_machine.py`)

**States (11):** `IDLE`, `RFID_READ`, `RFID_VALIDATE`, `RFID_ERROR`, `DISPLAY_TRUCK`, `ANPR_VALIDATE`, `MANUAL_UPDATE`, `ENTRY_GRANTED`, `WAIT_CROSSING`, `FREE_PASS`, `ERROR`

**Events (17):** `RFID_RECEIVED`, `RFID_VALID`, `RFID_INVALID`, `RFID_ERROR_TIMEOUT`, `ANPR_MATCH`, `ANPR_MISMATCH`, `UPDATE_STATUS_0/1/2`, `STATUS_2_TIMEOUT`, `ENTRY_OPENED`, `EXIT_SENSOR`, `CROSSING_TIMEOUT`, `RESET`, `FREE_PASS`, `ERROR_OCCURRED`

**Key timeouts:** RFID error 10s, manual poll 2s, status-2 reset 10s, crossing 60s, boom close delay 10s, ANPR 3 retries × 2s

#### Happy path
```
IDLE → RFID tag → RFID_READ → OCI rfid-tag → RFID_VALIDATE
 → DISPLAY_TRUCK → ANPR /api/detect (status=1)
 → OCI boom-close (status=200) → TL green + boom open
 → WAIT_CROSSING → entry sensor clear → delayed boom close → IDLE
```

#### Error paths
| Failure | Behavior |
|---------|----------|
| RFID invalid | `RFID_ERROR` → display "RFID ERR 1" → 10s → IDLE |
| ANPR API down | 3 retries → "ANPR API ERR" → IDLE |
| ANPR status 0/2 | `invalid-truck-number` → `MANUAL_UPDATE` poll `status_check` every 2s |
| vehicleStatus=0 | Keep polling |
| vehicleStatus=1 | Grant entry |
| vehicleStatus=2 | Wait 10s → IDLE |
| boom-close ≠ 200 | Boom **not** opened |
| Crossing timeout | Auto IDLE (config `vehicle_crossing_timeout`, default 60s) |
| Free pass | TL green + boom open → wait sensor → IDLE |

#### Hardware
| Device | Config keys | Pins (default config) |
|--------|-------------|------------------------|
| Modbus TCP | `io_controller.connection.ethernet` | 192.168.63.89:502, slave=1 |
| Entry TL | `traffic_lights.direct.entry_a.entry` | DO0 red, DO1 green |
| Entry boom | `boom_barriers.direct.entry` | DO2 open, DO3 close |
| Entry sensor | `sensors.entry_sensor` | DI0, `default_signal: low` |
| WB/exit sensors | disabled in config | — |
| RFID | `rfids.entry_a` | Zebra API mode, cloud HTTPS stop/start |

Note: `iot_configuration.json` has `"wb_type": "bidirectional"` but **Mine-entry ignores `wb_type`** — single entry lane only.

#### External APIs
| Service | URL path (defaults) |
|---------|---------------------|
| OCI rfid-tag | `/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag` |
| OCI invalid-truck | `/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number` |
| OCI status_check | `/ords/gmdc_dicsm/dlms_checkpoint/status_check` |
| OCI boom-close | `/ords/gmdc_dicsm/dlms_checkpoint/boom-close` |
| ANPR detect | `{ANPR_BASE}/api/detect` (default host 192.168.25.79:5001) |
| Digitizer | **Not used** |

#### HTTP endpoints (`api/endpoints.py`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/status`, `/version` | Health / version |
| GET | `/api/status` | Full snapshot |
| GET | `/api/update/status`, `/progress` | Updater stubs |
| POST | `/api/update/check`, `/apply` | Apply returns 501 |
| POST | `/rfid_data` | Zebra tag intake |
| POST | `/rfid_management` | Reader keepalive |
| POST | `/rfid_data_from_mobile_app` | Handheld fallback |
| POST | `/api/read-rfid`, `/read_rfid` | Aliases |
| POST | `/api/login` | Dashboard auth |
| POST | `/api/reset`, `/api/free-pass` | Operator actions |
| POST | `/api/simulate-exit` | Demo crossing trigger |

Default API port: **8000** (settings default); `.env` uses **8080**.

#### Web dashboard
- Static: `static/web/index.html`, `css/style.css`, `js/app.js`
- Flask serves `/` and `/static/*`
- Live updates via MQTT WebSocket **port 9001** (in-process broker)

#### MQTT topics

**Display (physical LED):**
- Publish: `iot_display/application_to_display`
- Subscribe: `iot_display/display_to_application`

**Dashboard (`wb_frontend/*`):**
- Publish: `position`, `display`, `rfid`, `status`, `device_status`
- Subscribe: `request_status`, `reset_application`, `free_pass`

#### Config / env
| Source | Path |
|--------|------|
| IoT JSON | `Mine-entry/iot_configuration.json` |
| Env | `Mine-entry/.env`, `.env.example` |
| Env keys | `DEMO_MODE`, `IOT_CONFIG_PATH`, `OCI_*`, `ANPR_*`, `DEVICE_IP`, `API_HOST/PORT`, `MQTT_*`, `RFID_USERNAME/PASSWORD`, `OPERATOR_*`, `VEHICLE_CROSSING_TIMEOUT` |

#### Tests (~74 cases)
| File | Tests | Coverage |
|------|-------|----------|
| `test_application.py` | 52 | RFID parsing, OCI payloads, workflow E2E, boom-close gate, crossing timeout, Flask |
| `test_state_machine.py` | 13 | All transitions |
| `test_web_dashboard.py` | 9 | MQTT snapshot / idle states |

#### VERSION
**`1.0.0`** (`Mine-entry/VERSION`)

#### Key differences vs siblings
- Same FSM as Tracking-point-1 but **Mines OCI paths** (`rfid-tag`, `boom-close`, `status_check`)
- `boom_close` sends `truck_details`, `close_type`
- No digitizer, voice, top camera, bidirectional logic

---

### 2.2 Tracking-point-1

Nearly identical shell to Mine-entry; differences are **OCI API contract** and README documentation.

#### Bootstrap
Same as Mine-entry except `TrackingPointWorkflow`, client_id `tracking_point_frontend`, logger `tracking_point.*`.

#### FSM
**Identical** states/events/timeouts to Mine-entry (`config/constants.py` is a copy).

#### Happy / error paths
Same FSM flow; `grant_entry_hardware()` calls **`checkpoint_boom_close`** with ANPR images, `top_image: null` (no local capture).

#### Hardware
Same single-entry layout; config `checkpoint_type: tracking_point_1`, `wb_type: unidirectional`, one RFID reader.

#### External APIs (Tracking-specific paths)
| Step | Path |
|------|------|
| RFID validate | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag` |
| Invalid truck | `/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number` |
| Check status | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status` |
| Boom close | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close` |

Boom-close body: `{ rfid, device_ip, front_image, anpr_image, top_image }` from ANPR response.

#### HTTP endpoints
Same list as Mine-entry (251 lines vs 258 — minor wording differences).

#### Web dashboard / MQTT
Same structure and topics as Mine-entry.

#### Config / env
- `Tracking-point-1/iot_configuration.json`
- Settings adds `front_camera_rtsp_url`, `top_camera_rtsp_url` (unused in workflow)
- `.env` mirrors Mine-entry

#### Tests (~74 cases)
Same test file structure and counts as Mine-entry (workflow class name swapped).

#### VERSION
**`1.0.0`**

#### Key differences vs Mine-entry
| Aspect | Mine-entry | Tracking-point-1 |
|--------|------------|------------------|
| OCI rfid path | `.../rfid-tag` | `.../checkpoint/rfid-tag` |
| Status poll | `status_check` | `checkpoint/check-status` |
| Boom close | `boom-close` + truck_details | `checkpoint_boom_close` + images |
| Workflow LOC | 752 | 755 |
| OCI client LOC | 467 | 471 |

---

### 2.3 TareWb-App

#### Bootstrap (`TareWb-App/main.py`, 444 lines)
1. Settings with `checkpoint_type`, `wb_type`, digitizer, voice, camera
2. `OCIClient` (+ weight-details, weight-confirm, gross-tolerance)
3. Display: console if empty display IP; else MQTT
4. `DigitizerClient`, optional `VoiceService`
5. **Dual TL + dual boom** (relay or direct mode), 3 sensors (entry/wb/exit)
6. Multi-direction RFID clouds when bidirectional
7. **No RFID start at boot** — deferred until weight > 5t
8. Idle: entry green/open, exit red/closed
9. Flask + animated dashboard route

#### FSM (`config/constants.py` + `core/state_machine.py`)

**States (15):** `IDLE`, `VEHICLE_POSITIONING`, `WEIGHT_CAPTURE`, `RFID_READ`, `RFID_VALIDATE`, `RFID_ERROR`, `ANPR_VALIDATE`, `MANUAL_UPDATE`, `FINAL_WEIGHT`, `IMAGE_CAPTURE`, `WEIGHT_DETAILS`, `EXIT_GRANTED`, `WAIT_EXIT`, `ERROR`, `FREE_PASS`

**Events (26):** includes `ENTRY_SENSOR`, `WB_SENSOR`, `EXIT_SENSOR`, `WEIGHT_OK/LOW/FAIL`, `DETAILS_OK/FAIL`, `MANUAL_OK`, timeouts, etc.

**Key constants:** `MIN_WEIGHT_KG = 5000`, positioning 120s, weight capture 60s, exit wait 120s, weight confirm poll 5s

#### Happy path (unidirectional)
```
IDLE → entry sensor → VEHICLE_POSITIONING (voice "move forward")
 → wb sensor → WEIGHT_CAPTURE → digitizer > 5000 kg
 → RFID cloud start → RFID_READ → OCI rfid-tag → ANPR
 → top camera RTSP snapshot → invalid-truck
 → FINAL_WEIGHT → RTO band check (T trips)
 → weight-details → boom-close → EXIT_GRANTED
 → exit sensor clear (delayed boom close) → IDLE
```

#### Error paths
| Failure | Behavior |
|---------|----------|
| Positioning timeout 120s | IDLE |
| Digitizer fail / weight timeout | ERROR or IDLE |
| Weight ≤ 5000 kg | IDLE (voice check_weighbridge) |
| RFID invalid / timeout | RFID_ERROR → 10s → **EXIT_GRANTED** (clear lane) |
| ANPR manual loop abort | EXIT_GRANTED |
| Tare out of RTO band | Display TARE WT ERR → `weight-confirm` loop |
| weight_status=2 | Skip weight-details & boom-close, still exit |
| Gross/V weight-details 201 | `gross-tolerance-confirm` loop |
| tolerance_status=2 | Skip second weight-details, boom-close anyway |
| Exit timeout 120s | force_reset |

#### Hardware
| Device | Unidirectional config | Bidirectional (code) |
|--------|----------------------|----------------------|
| Entry TL | relay pin DO0 | entry + exit TLs |
| Exit TL | relay pin DO1 | |
| Entry boom | relay pin DO4 | entry + exit booms |
| Exit boom | relay pin DO5 | |
| Sensors | DI0 entry, DI1 wb, DI2 exit | exit sensor = ENTRY_B approach |
| RFID | single `rfid` block | `rfids.entry_a` + `rfids.entry_b` |
| Voice | WAV files via `VoiceService` | |
| Top camera | RTSP in `camera.top.rtsp_url` | OpenCV snapshot via `gmdc_common.hardware.camera` |

Config uses **relay mode** for TL/boom; Mine/Tracking use **direct** mode.

#### External APIs
All Mine-entry APIs plus:

| API | Path |
|-----|------|
| weight-details | `/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details` |
| weight-confirm | `/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-confirm` |
| gross-tolerance-confirm | `/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-tolerance-confirm` |
| boom-close (WB) | `{truck_details}` only |
| Digitizer | `http://{host}:{port}/read_stable_weight` POST `{}` |

#### HTTP endpoints
Mine-entry set **plus:**
| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/camera/stream` | Returns 404 (not implemented) |
| GET | `/animated.html` | Animation dashboard |
| POST | `/api/simulate-entry` | Demo only |
| POST | `/api/simulate-wb` | Demo only |
| POST | `/api/simulate-exit` | Demo only; ENTRY_B in bidirectional |

Reset calls `force_reset(announce_reset=True)`.

#### Web dashboard
- `index.html` — operational dashboard
- `animated.html` + `animated.js` — truck animation (TareWb only)
- Extra MQTT publish: **`wb_frontend/digitizer`** (weight kg, QoS 1)

#### MQTT topics
Same as Mine-entry + `wb_frontend/digitizer`.

#### Config files
| File | `checkpoint_type` | `wb_type` |
|------|-------------------|-----------|
| `iot_configuration.json` | `tare_wb` | `unidirectional` |
| `iot_configuratio-tare.json` | `tare_wb` | `unidirectional` |
| `iot_configuration-gross.json` | `gross_wb` | `unidirectional` |
| `iot_configuration-vadhghat.json` | `vadghat_wb` | `unidirectional` |

Config resolution: `IOT_CONFIG_PATH` → `TareWb-App/iot_configuration.json` → `../checkpoint-config/iot_configuration.json`.

#### Tests (~70 cases)
| File | Tests | Focus |
|------|-------|-------|
| `test_weight_tolerance.py` | 20 | RTO bands T/V/G, confirm loops |
| `test_bidirectional_flow.py` | 13 | ENTRY_A/B, RFID direction |
| `test_anpr_flow.py` | 12 | ANPR branches |
| `test_web_dashboard.py` | 16 | Dashboard + digitizer topic |
| `test_top_camera.py` | 5 | RTSP filename helpers |
| `test_smoke.py` | 4 | FSM, settings, digitizer demo |

Docs: `docs/Tare_WB_Test_Cases.csv` (95+ manual test case IDs).

#### VERSION
**`0.1.0`** (pre-1.0 vs checkpoint apps)

#### Key differences vs siblings
- Full weighbridge FSM (sensors → weight → RFID order inverted vs checkpoints)
- Digitizer + voice + top camera
- Dual-lane hardware + bidirectional support in code
- RTO tolerance / weight-confirm / gross-tolerance
- Largest workflow: **1,459 lines**

---

## 3. Shared vs Duplicated Code

### gmdc_common in workspace?
**No.** Zero files under `/Users/csmtech/Desktop/new-IoT/gmdc_common`. All three apps **require** `pip install -e ../gmdc_common` (documented in `TareWb-App/requirements.txt` and README). Logs show runtime used `gmdc_common.*` on Windows.

### Hardware handling pattern (all apps)

| Layer | Implementation |
|-------|----------------|
| `hardware/*.py` | **Thin re-exports** from `gmdc_common.hardware.*` |
| `services/rfid_control.py` | Re-export `gmdc_common.services.rfid_control` |
| `services/display_service.py` | Re-export `gmdc_common.services.display_service` |
| `utils/logging_setup.py` | Re-export `gmdc_common.utils.logging_setup` |
| `utils/pymodbus_compat.py` | Re-export `gmdc_common.utils.pymodbus_compat` |
| `core/state_machine.py` | App-specific `TRANSITIONS` wrapping `gmdc_common.core.state_machine.BaseStateMachine` |

TareWb additionally re-exports via `hardware/__init__.py` and imports camera/voice directly from `gmdc_common`.

### Copies vs unique (approximate)

| Files | Relationship |
|-------|--------------|
| `Mine-entry/core/workflow.py` ↔ `Tracking-point-1/core/workflow.py` | ~99% duplicate; differ in class name, boom_close call, logging |
| `Mine-entry/services/oci_client.py` ↔ Tracking | ~95% duplicate; API paths + boom payload builders differ |
| `Mine-entry/services/frontend_mqtt.py` ↔ Tracking | Near-identical (~574 lines each) |
| `Mine-entry/api/endpoints.py` ↔ Tracking | Near-identical |
| `Mine-entry/main.py` ↔ Tracking | Near-identical |
| `config/constants.py` (Mine ↔ Tracking) | **Identical** |
| `TareWb-App/core/workflow.py` | **Unique** (1,459 lines) |
| `TareWb-App/services/oci_client.py` | **Unique extension** (+RTO helpers, weight APIs, 623 lines) |
| `TareWb-App/services/digitizer_client.py` | **Unique** |
| `TareWb-App/services/voice_service.py` | Re-export only |

---

## 4. Bidirectional Weighbridge Support

**Implemented in TareWb-App only** when `wb_type == "bidirectional"` in config.

| Behavior | Detail |
|----------|--------|
| ENTRY_A | `on_entry_occupied()` while IDLE |
| ENTRY_B | `on_exit_occupied()` while IDLE (vehicle approaches from exit side) |
| RFID | Separate Zebra cloud per direction; active reader starts after weight OK; opposite reader stopped |
| Exit complete ENTRY_A | `on_exit_cleared()` after EXIT_GRANTED |
| Exit complete ENTRY_B | `on_entry_cleared()` (entry sensor on far side) |
| HTTP intake | Shared `POST /rfid_data` — no reader-IP routing |
| Demo | `POST /api/simulate-entry` / `/api/simulate-exit` when `DEMO_MODE=true` |

**Gap (from transcript):** No logical entry/exit hardware swap for ENTRY_B (wb-old had `logical_map.py`). Physical entry boom always closes at weigh; physical exit grants at end — ENTRY_B from exit side may be wrong in production without swap layer.

**Current configs:** All TareWb JSON files use `"wb_type": "unidirectional"`. Bidirectional was tested with external `checkpoint-config` (see logs in `TareWb-App/logs/tare_wb.log.1`).

Mine-entry config says `bidirectional` but app **does not implement** bidirectional logic.

---

## 5. Weight Tolerance / RTO Logic

Implemented in `TareWb-App/services/oci_client.py` + `core/workflow.py::_final_weight_and_details`.

**`truck_details` pipe format:** 
`T|RFID|VEH|rto_gross|rto_tare|tolerance|token|device_ip|…`

| Trip prefix | Band | Example (45000/15000/500) |
|-------------|------|---------------------------|
| **T** (tare) | `rto_tare ± tolerance` | 14,500 – 15,500 kg |
| **V** (vadaghat) | `(rto_gross - tolerance) … rto_gross` | 44,500 – 45,000 kg |
| **G** (gross) | Same as V | 44,500 – 45,000 kg |
| Unknown (X) | Skip check | Always OK |

**Tare out-of-band flow:**
1. Display `TARE WT ERR` / voice
2. Poll `weight-confirm` with type `u` (under) or `o` (over)
3. `weight_status=0` → retry; `1` → update tolerance field in truck_details, recapture weight; `2` → abort (exit without details)

**Gross/Vadaghat flow:**
1. Post `weight-details` first (no local pre-check)
2. If response **201** → poll `gross-tolerance-confirm` every 5s
3. `tolerance_status=1` + in-band → second `weight-details` with updated tolerance
4. `tolerance_status=2` → skip second details, still boom-close

Display errors: `TARE WT ERR`, `VADAGHAT WT ERR`, `GROSS WT ERR`.

**20 automated tests** in `test_weight_tolerance.py`.

---

## 6. Camera / ANPR / RFID Patterns

### RFID
| Pattern | Detail |
|---------|--------|
| Fixed reader | Zebra FX, mode `API` — tags via `POST /rfid_data` JSON `[{data:{idHex}}]` |
| Cloud control | HTTPS `login → mode → start/stop` on reader IP |
| Mobile fallback | `POST /rfid_data_from_mobile_app` body `{rfid_data: "..."}` |
| Collect window | Checkpoints: 2s; TareWb: 5s × 12 for timeout |
| Stop on read | Immediate cloud stop when tag received |

### ANPR
| Pattern | Detail |
|---------|--------|
| Service | Separate host from OCI (`ANPR_BASE_URL`) |
| Endpoint | `POST /api/detect` with vehicle_number, rfid, token, device_ip |
| Status | `0` mismatch, `1` match, `2` Err-2 |
| Retry | Checkpoints: 3× on transport failure; TareWb: single call in `_after_rfid_valid` |
| Images | Checkpoints: from ANPR JSON only; TareWb: + local top RTSP capture |

### Camera
| App | Capture |
|-----|---------|
| Mine-entry / Tracking | No local capture; `top_image: null` on boom-close |
| TareWb | RTSP snapshot via `gmdc_common.hardware.camera.capture_rtsp_snapshot` |
| Filename | `{TOKEN}_{dd-mm-yy-HH-MM-SS}_{TRUCK}_{IP}_TOP.jpg` or `error.jpg` |
| Stream API | `/api/camera/stream` → 404 |

---

## 7. Demo Mode

| Mechanism | Behavior |
|-----------|----------|
| Flag | `DEMO_MODE` env or `demo_mode` in JSON (default **true** in code defaults, **false** in committed `.env` files) |
| I/O | `create_io_controller(..., demo_mode=True)` → `DemoIOController` (gmdc_common) |
| Digitizer | Returns **12,500 kg** without HTTP |
| TareWb simulate | `/api/simulate-entry`, `/simulate-wb`, `/simulate-exit` (403 if not demo) |
| Mine/Tracking simulate | `/api/simulate-exit` less restricted |
| RFID | Demo reader inject path via `inject_payload` |

`TareWb-App/demo-app/apis.py`: minimal Flask returning `{weight: 44990}` on port 8001 for local digitizer testing.

---

## 8. Security / Ops Concerns

| Issue | Location |
|-------|----------|
| **gmdc_common missing** | Apps won't import without external install |
| **Secrets in repo** | `.env` files contain OCI/ANPR/RFID passwords; `iot_configuration.json` has RFID password `Csmpl@123`, RTSP creds `rtsp://zafir:Csm_12345@...` |
| **Hardcoded dashboard login** | Default `admin` / `gmdc@123` in `api/endpoints.py` (overridable via settings) |
| **Hardcoded OCI defaults** | `GMDC_API_USER` / `GMDC@1234` in all `settings.py` |
| **CORS wide open** | `Access-Control-Allow-Origin: *` on Flask |
| **No TLS** | Flask HTTP, MQTT plain, Modbus TCP |
| **JWT in logs** | Mine-entry logs contain full RFID bearer tokens |
| **API debug pause** | TareWb `.env`: `GMDC_API_DEBUG=true`, 10s pause after each OCI call |
| **In-app updater** | Stub returns 501 |
| **checkpoint-config absent** | TareWb README assumes sibling folder |

---

## 9. Line Counts of Major Files

| File | Mine-entry | Tracking-1 | TareWb-App |
|------|------------|------------|------------|
| `main.py` | 288 | 286 | 444 |
| `core/workflow.py` | 752 | 755 | **1,459** |
| `core/state_machine.py` | 57 | 57 | 69 |
| `config/constants.py` | 63 | 63 | 85 |
| `config/settings.py` | 264 | 285 | 449 |
| `services/oci_client.py` | 467 | 471 | **623** |
| `services/frontend_mqtt.py` | 574 | ~574 | 637 |
| `services/digitizer_client.py` | — | — | 104 |
| `api/endpoints.py` | 258 | 251 | 255 |
| `api/server.py` | 84 | 84 | 88 |

---

## Summary Diagram

```mermaid
flowchart TB
 subgraph missing [Missing from workspace]
 GC[gmdc_common package]
 CC[checkpoint-config]
 DA[digitizer-app]
 end

 subgraph present [Present apps]
 ME[Mine-entry v1.0.0]
 TP[Tracking-point-1 v1.0.0]
 TW[TareWb-App v0.1.0]
 end

 GC -.->|pip install -e| ME
 GC -.->|pip install -e| TP
 GC -.->|pip install -e| TW

 ME -->|RFID ANPR boom-close| OCI1[Mines OCI paths]
 TP -->|RFID ANPR checkpoint_boom_close| OCI2[Tracking OCI paths]
 TW -->|weight-details tolerance| OCI3[Weighbridge OCI paths]
 TW -->|read_stable_weight| DIG[Digitizer HTTP]
```

**Bottom line:** This workspace is a **partial checkout** of the GMDC platform — three checkpoint runtimes with thin `gmdc_common` adapters, but the shared library and config repo are absent. TareWb-App is the most capable app (weighbridge, RTO, bidirectional, camera, voice); Mine-entry and Tracking-point-1 are structurally duplicated checkpoint gates differing mainly in OCI endpoint naming. Gross WB and Vadaghat are **config profiles** of TareWb-App, not separate applications.
</response>
output_path: /Users/csmtech/.cursor/projects/Users-csmtech-Desktop-new-IoT/agent-transcripts/8557f143-1190-4689-8f2e-f07de6257b3a/subagents/81e21b15-0ce4-458f-9ccf-c4d07765862c.jsonl
</task>
</system_notification>
<user_query>Perform any necessary follow-up actions in response to the subagent completion above. If no follow-up work is needed, no further action is required. If you mention an agent or subagent in your response, link it with the `[Name](id)` Don't use generic label such as `[agent]`, `[worker]`, or `[subagent]`. For cloud subagents, when the agent has edited code, link to `[Review](bc-id#changes)`, or, if you know the exact added and deleted line counts, `[Review +A −D](bc-id#changes)`, replacing A and D with those counts. Never write A or D literally. Use `[Try Live](bc-id#desktop)` only when the agent used computer use. Don't repeat the same confirmation every time.</user_query>

---

**Cursor**

The deeper pass confirmed the review and added a few facts I’ll fold into the canvas: total LOC, the ENTRY_B hardware-swap gap, and extra security notes.

The deeper pass matched the review and added a few production details I folded into [GMDC application analysis](/Users/csmtech/.cursor/projects/Users-csmtech-Desktop-new-IoT/canvases/gmdc-application-analysis.canvas.tsx):

- **~17,900 Python lines** across the three apps
- **ENTRY_B does not remap physical lights/booms** — RFID direction works; the I/O map still treats the A-side as entry
- Mine-entry’s JSON says `wb_type: bidirectional` but **the app ignores it**
- Extra ops notes: CORS `*`, RFID tokens in logs, checkpoints retry ANPR three times while TareWb calls once

Nothing else needed unless you want to copy `gmdc_common` into this workspace next.

---

**User**

Okay so this I need to create it as an industrial application. It should have proper error handling, with proper messages to be shown in the Web-App
For example: URL: http://localhost:5001/api/detect
Payload: {
  "vehicle_number": "OD14AF2721",
  "rfid": "00000000000000000015c021",
  "token": "9580109262"
}
Response: {
  "error": "HTTPConnectionPool(host='localhost', port=5001): Max retries exceeded with url: /api/detect (Caused by NewConnectionError(\"HTTPConnection(host='localhost', port=5001): Failed to establish a new connection: [Errno 61] Connection refused\"))"
}
------------------------------------------------------------

Here the ANPR application is not reachable, so in UI, please show just like currently in red, popup is there, there will show ANPR not reachable, in this way findout all the non 200 cases, at that should show in red in their respective div, but for server error or like above error big popup show
2026-09-02 11:50:40 [ERROR] mine_entry.services.oci: OCI anpr-detect ERROR: HTTPConnectionPool(host='localhost', port=5001): Max retries exceeded with url: /api/detect (Caused by NewConnectionError("HTTPConnection(host='localhost', port=5001): Failed to establish a new connection: [Errno 61] Connection refused"))
2026-09-02 11:50:40 [WARNING] mine_entry.core.workflow: ANPR API exception attempt 1/3: HTTPConnectionPool(host='localhost', port=5001): Max retries exceeded with url: /api/detect (Caused by NewConnectionError("HTTPConnection(host='localhost', port=5001): Failed to establish a new connection: [Errno 61] Connection refused"))

---

**Cursor**

I'll trace how ANPR and other API failures reach the dashboard, then map every non-200 path so the UI can show a red inline status plus a large popup for unreachable/server errors.

I'll add operator-facing error kinds in the API layer, then wire those into the workflows and the dashboard popup so connection failures never dump raw exceptions.

Next I’ll wire the workflows so each API failure paints the matching step red and only connection/5xx errors raise the large popup.

JS is in all three dashboards. Next I’ll verify the Python error mapping and tests, then run the suites.

I’ll tighten error classification so connection failures show “ANPR not reachable” (not the raw exception), then add tests and run the suites.

Operators no longer see raw Python exceptions in the dashboard. A connection-refused ANPR call now shows **ANPR not reachable** in the ANPR step (red) and a large red popup titled **ANPR NOT REACHABLE**, in the same style as CHECK SENSOR.

The full `HTTPConnectionPool… Errno 61` text stays in the server log only.

**What the Web-App shows**

| Failure | Step (red) | Large popup |
|---|---|---|
| Service down, timeout, connection refused | Short message, e.g. `ANPR not reachable` | Yes — `ANPR NOT REACHABLE` |
| HTTP 5xx, 401, 403 | e.g. `ANPR server error` | Yes — `ANPR SERVER ERROR` |
| HTTP 4xx (reachable but rejected) | e.g. `ANPR request failed` | No — red on that step only |
| Business reject (RFID invalid, boom-close status ≠ 200, weight-details fail) | Red on that step | No |

This covers RFID, ANPR, invalid-truck, status-check, boom-close, weight-details, weight-confirm, gross-tolerance, and digitizer (Tare WB).

The popup stays until the operator taps **Dismiss** or a new cycle starts (RFID / vehicle entering). Going idle does not auto-dismiss it, so the alert is still visible after the lane resets.

Applied on Mines Entry, Tracking Point 1, and Tare WB.

---

**User**

okay now lets work on an addition. In all the application, when flow will go to IDLE mode, at that time reset is happening, but the gmdc server doesn;t know that our application is reset. So an API is now created in the server, below are the details
URL :https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint
Payload : 
{
  "device_ip": "10.10.180.12",
  "rfid_no": "E28068940000503F548F04BA",
  "truck_details": "V|E28068940000503F548F04BA|OD14P7339|45000|24500|50|9580109261|10.10.180.12"
}
 
Response : 
{
  "status": 200,
  "response_type": 1,
  "message": "Current checkpoint transaction reset successfully. RFID can be read again.",
  "device_ip": "10.10.180.12",
  "rfid_no": "E28068940000503F548F04BA",
  "truck_details": "",
  "token": "9580109261",
  "location_id": 163,
  "location_name": "Vadhghat Weighbridge",
  "reset_count": {
    "entry_log": 4,
    "checkpoint": 1,
    "movement": 1,
    "weighment": 0
  }
}

in the payload, device_ip, the rfid_no and truck_details are mandatory. This API will be called only when a transaction is active, and the vehicle movements forces the application to reset, or manually reset is pressed from UI. ALso if reset if pressed from IU, and there is no transaction started, then only device_ip will be sent, rest other empty sting

---

**Cursor**

I’ll add a reset-checkpoint OCI call on IDLE reset in all three apps: fire it when a transaction is active (or on a manual UI reset), and send only `device_ip` if nothing has started.

Settings already has a reset-checkpoint URL in Mines Entry. I’ll map every IDLE path so we notify GMDC on abort/manual reset, not on a successful cycle.

Config already has the reset URL. Next I’ll add the OCI client method and call it on abort/manual reset—not on a successful cycle.

All three apps now tell GMDC when a cycle is aborted or the operator hits Reset, so RFID can be read again on the server.

**When it is called**

| Situation | Payload |
|---|---|
| Reset from the Web-App, **no** transaction | `device_ip` + empty `rfid_no` and `truck_details` |
| Reset from the Web-App, **with** a transaction | `device_ip`, `rfid_no`, `truck_details` |
| Abort while a transaction is open (RFID/ANPR fail, crossing timeout, vehicleStatus 2, etc.) | Same three fields with whatever RFID / truck details are known |
| Successful cycle (truck cleared after boom-close) | **Not** called — GMDC already has the close |

The three keys are always sent. Hardware still goes IDLE even if this API fails; a red popup is shown if the reset service is unreachable.

Endpoint (from config, default):

`POST {oci_base_url}/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint`

---

**User**

now create a .gitignore to remove all the non required files. Also include all the folders having "log" as fodler name

---

**Cursor**

Nothing is committed yet, so a root `.gitignore` is enough. I’ll ignore log directories, secrets, caches, OS junk, and runtime captures.

Created a root `.gitignore`. Git has no commits yet, so ignored files will stay out of the repo as soon as you add and commit.

**Log folders** — any directory whose name contains `log` is ignored, including:
- `Mine-entry/logs/` and `Mine-entry/logs1/`
- `TareWb-App/logs/`
- `Tracking-point-1/logs/`
- `checkpoint-config/configuration_logs/`

**Also ignored:** `.env` (`.env.example` is kept), `__pycache__`, `.DS_Store`, `*.egg-info`, PID files, Office lock files, runtime camera folders (`TareWb-App/images/`, `Tracking-point-1/images/`, `captures/`), and Cursor chat dumps (`cursor_*.md`).

**Not ignored:** app source, configs, tests, and UI assets such as `TareWb-App/static/web/images/`.

---

**User**

make me a readme.md in the root directory, also re-analyse the code as I have added the 3 required checkpoint-config, digitizer-app, gmdc_copmmon in this directopry

---

**Cursor**

I'll re-read the apps and the three shared packages you added, then write a root README that matches how the repo actually works.

I have a clear picture of how the three shared packages sit beside the checkpoint apps. Writing the root README next.

Created [`README.md`](README.md) at the workspace root after re-reading the three packages you added and how the checkpoint apps use them.

**How the repo fits together**

- **`gmdc_common`** — shared drivers: Modbus I/O, traffic lights, booms, sensors, Zebra RFID, display, voice, and the generic FSM. Mine-entry, Tracking-point-1, Tare WB, and checkpoint-config all import it (`pip install -e ./gmdc_common`).
- **`checkpoint-config`** — commissioning UI on port 8080. It writes `iot_configuration.json` (profiles for mines entry, tracking 1/2, mines exit, tare / Vadaghat / gross WB). Digitizer here is API-only: host/port + `POST /read_stable_weight`.
- **`digitizer-app`** — standalone serial reader (PySide6). No GMDC imports. HTTP API is fixed at **:8800**. Tare WB calls that endpoint when `DEMO_MODE` is false.

**Runtimes still in this tree:** `Mine-entry/`, `Tracking-point-1/`, `TareWb-App/`. Tracking-2 and mines exit are the same checkpoint family as Mine-entry but not separate apps yet. Vadaghat / gross use the Tare WB runtime with a different `checkpoint_type`.

The README covers site flow, layout, setup, run commands, ports, and how RFID / Modbus / ANPR / OCI / the dashboard MQTT broker (port 9001) connect.

---

**User**

the reset_checkpoint API should also use the API same username and password, just like other gmdc apis

---

**Cursor**

I'll check how `reset_checkpoint` is authenticated compared to the other GMDC APIs, then align it to the same username and password.

`reset_checkpoint` is missing from the commissioning API list, so it never got username/password like the other GMDC endpoints. I'll add those fields in the config tool, defaults, and site JSON files.

`reset_checkpoint` now uses the same Basic Auth username and password as the other GMDC APIs.

**What was missing:** the commissioning UI listed URL + username + password for RFID, ANPR, status check, boom close, and weight details — but not for reset. Runtime configs had the reset URL only, so that call did not get the per-endpoint credentials.

**What changed**
- Checkpoint Config now includes a **Reset Checkpoint** row (URL, username, password) for both checkpoint and weighbridge profiles. It pre-fills from the same OCI username/password as the other GMDC endpoints.
- Site JSON files now have `reset_checkpoint_username` / `reset_checkpoint_password` next to the URL, matching boom-close and RFID.
- If those keys are blank, the client falls back to the shared OCI credentials instead of sending empty auth.

Re-open **Configure API-Endpoints** in checkpoint-config and save once if this PC’s `iot_configuration.json` was generated before this change.

---

**User**

@Untitled-1 (1-34) 

---

**Cursor**

I'll look at how Vadhghat handles out-of-tolerance weight today, then wire in this adjustment API and skip boom-close on that path.

Vadhghat currently still posts weight-details and boom-close when the weight is out of band. I’ll add the adjustment API and send the truck out without boom-close on that path.

Vadhghat now uses the weight-adjustment API when the captured weight is outside the RTO band, then lets the truck out **without** boom-close.

**When it fires** (`V|…` truck details, e.g. band 44500–45000 kg):
- Over weight → `weight_type: "o"`
- Under weight → `weight_type: "u"`

**Request**

```json
{
  "device_ip": "10.10.180.12",
  "truck_details": "V|…",
  "weight": 44990,
  "weight_type": "o"
}
```

Posted to `/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment` with the same Basic Auth as the other GMDC APIs.

**After a 200:** GMDC has already reset the Vadhghat cycle, so this lane skips `weight-details`, skips `boom-close`, skips `reset_checkpoint`, and grants exit (physical boom still opens).

**In-band Vadhghat** is unchanged: weight-details → boom-close. Tare and final gross WB are unchanged.

---

**User**

uing a start."}
2026-09-03 12:52:43 [ERROR] gmdc_common.services.rfid_control: RFID IDLE prepare failed at start
2026-09-03 12:52:43 [INFO] mine_entry.core.workflow: RFID IDLE prepare (login/mode/start) ok=False
Traceback (most recent call last):
  File "/Users/csmtech/Desktop/new-IoT/Mine-entry/main.py", line 290, in <module>
    sys.exit(main())
             ^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/Mine-entry/main.py", line 233, in main
    ctx = bootstrap()
          ^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/Mine-entry/main.py", line 219, in bootstrap
    ctx.workflow.notify_gmdc_reset()
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'MinesEntryWorkflow' object has no attribute 'notify_gmdc_reset'. Did you mean: '_notify_gmdc_reset'?

---

**Cursor**

The bootstrap is calling a public `notify_gmdc_reset` that doesn't exist on Mine-entry. I'll match it to the method the other apps actually expose.

Bootstrap calls `notify_gmdc_reset()`, but the workflow only has `_notify_gmdc_reset`. I'll add the public startup method on all three apps so they notify GMDC with empty RFID/truck fields.

The crash was a missing method: bootstrap called `notify_gmdc_reset()`, but the workflow only defined `_notify_gmdc_reset`.

That public method is now on Mine-entry, Tracking-point-1, and Tare WB. On startup it posts `reset_checkpoint` with `device_ip` and empty RFID / truck details, so GMDC can accept the next tag.

Restart Mine-entry. The earlier `RFID IDLE prepare failed at start` line is separate: the Zebra reader did not complete login/mode/start. The app should stay up now; if tags still do not come in, check reader IP, credentials, and network.

---

**User**

RESET SERVICE SERVER ERROR
Reset service server error

Dismiss
I am getting this in UI

also in terminal
URL: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint
Payload: {
  "device_ip": "192.168.10.223",
  "rfid_no": "",
  "truck_details": ""
}
Response: {
  "raw_text": "<!DOCTYPE html>\n<html>\n<style type=\"text/css\" media=\"screen\">\n\t:root {\n\t\t /* Site Elements */\n\t\t/* background select input */\n\t\t--color-site-1: #F5F4F2;\n\t\t--color-site-1-c:   #000000; /* foreground */\n\t\t--color-site-1-c-1: hsl(0, 0%, 42%); /* secondary foreground */\n\t\t--color-accent-1-1: #007ea8;\n\t\t--color-site-1-2:   #D9D9D9; /* details - border line */\n\t\t--color-accent-1: #00688C;\n\t\t--color-accent-1-c:   #FFFFFF; /* foreground */\n\t\t    /* Site Elements */\n\t\t--color-site-2:     #FFFFFF; /* background */\n\t\t--color-site-2-c:   #222222; /* foreground */\n\t\t--color-site-2-1:   #e2e8f0; /* details - border line */\n\t\t/* Oracle red */\n\t\t--color-site-3: #c74934; /* Color taken from figma spec wireframe */\n\t\t/* scrollbar */\n\t\t--color-scrollbar: #efefef;\n\t\t--color-scrollbar-thumb: #d3d3d3;\n\t\t--color-scrollbar-border: #efefef;\n\t}\n\n\t.dark-theme {\n         /* Site Elements */\n        /* background select input */\n        --color-site-1: #F5F4F2;\n        --color-site-1-c:   #FFFFFF; /* foreground */\n        --color-site-1-c-1: hsl(0, 0%, 100%); /* secondary foreground */\n        --color-accent-1-1: #007ea8;\n        --color-site-1-2:   #D9D9D9; /* details - border line */\n        --color-accent-1: #00688C;\n        --color-accent-1-c:   #FFFFFF; /* foreground */\n            /* Site Elements */\n        --color-site-2:     #333333; /* background */\n        --color-site-2-c:   #222222; /* foreground */\n        --color-site-2-1:   #FFFFFF80; /* details - border line */\n        /* Oracle red */\n        --color-site-3: #c74934; /* Color taken from figma spec wireframe */\n\t\t/* scrollbar */\n\t\t--color-scrollbar: #333333;\n\t\t--color-scrollbar-thumb: #FFFFFF80;\n\t\t--color-scrollbar-border: #FFFFFF80;\n    }\n\n\t* {\n\t\tbox-sizing: border-box;\n\t}\n\n\thtml {\n\t\tfont-size: 1rem;\n\t\tfont-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;\n\t}\n\n\thtml, body {\n\t\theight: 100%\n\t}\n\n\tbody {\n\t\tbackground-color: var( --color-site-1 ) !important;\n\t\tmargin: 0;\n\t\tbackground-repeat: repeat;\n\t\tdisplay: flex;\n\t\tflex-direction: column;\n\t\tbackground: url(\"data:image/jpeg;base64,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\");\n\t\n}\n\n\tbody.dark-theme {\n        color: var( --color-site-1-c );\n        background-color: var( --color-site-2 ) !important;\n        background-blend-mode: color-burn;\n    }\n\n\t::-webkit-scrollbar {\n\t\twidth:12px;\n\t\theight:12px;\n\t\tbackground-color: var( --color-scrollbar );\n\t}\n\n\t::-webkit-scrollbar-thumb {\n\t\tbackground-color: var( --color-scrollbar-thumb );\n\t\tborder-radius: 0.25rem;\n\t\tborder: 1px solid var( --color-scrollbar );\n\t}\n\n\t::-webkit-scrollbar-corner {\n\t\tbackground: var( --color-scrollbar );\n\t}\n\n\t.collapsible .collapsible__body::-webkit-scrollbar {\n\t\tbackground-color: #333333;\n\t}\n\n\t.collapsible .collapsible__body::-webkit-scrollbar-thumb {\n\t\tbackground-color:#999999;\n\t\tborder-color: #333;\n\t}\n\n\t.collapsible .collapsible__body::-webkit-scrollbar-corner {\n\t\tbackground: #333333;\n\t}\n\n\t.collapsible .collapsible__body {\n\t\tscrollbar-color: #999999 #333333;\n\t}\n\n\t.ords-logo {\n\t\tbackground-image: url(\"data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOTYiIGhlaWdodD0iOTYiICB2aWV3Qm94PSIwIDAgMTEwIDEzMCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KICAgIDxwYXRoIGQ9Ik01NSAxMzBMOTcuMjU2MSAxMTEuMDQyTDExMCAxMi44NjQ2TDU1IDBMMCAxMi44NjQ2TDEyLjc0MzkgMTExLjA0Mkw1NSAxMzBaIiBmaWxsPSIjQzc0NjM0Ii8+CiAgICA8cGF0aCBkPSJNNTUuMDAwNSA3NS41MjE5QzQ1Ljc1MTIgNzUuNTIxOSAzNi4wNjU4IDczLjE3MjQgMzIuMDYxNSA2OC43NTExVjc3LjAyNUMzMi4wNjE1IDgyLjI5MjggNDIuMzMwNCA4Ni41NTg0IDU1LjAwMDUgODYuNTU4NEM2Ny42NzA3IDg2LjU1ODQgNzcuOTM5NiA4Mi4yOTI4IDc3LjkzOTYgNzcuMDI1VjY4LjczNzVDNzMuOTY4OCA3My4xNjU3IDY0LjI3NjggNzUuNTIxOSA1NS4wMDA1IDc1LjUyMTlaIiBmaWxsPSJ3aGl0ZSIvPgogICAgPHBhdGggZD0iTTU1LjAzMzUgNzMuNDVDNjcuNzAyNCA3My40NSA3Ny45NzI1IDY5LjI4NDkgNzcuOTcyNSA2NC4xNDY5Qzc3Ljk3MjUgNTkuMDA4OSA2Ny43MDI0IDU0Ljg0MzggNTUuMDMzNSA1NC44NDM4QzQyLjM2NDYgNTQuODQzOCAzMi4wOTQ1IDU5LjAwODkgMzIuMDk0NSA2NC4xNDY5QzMyLjA5NDUgNjkuMjg0OSA0Mi4zNjQ2IDczLjQ1IDU1LjAzMzUgNzMuNDVaIiBmaWxsPSJ3aGl0ZSIvPgogICAgPHBhdGggZD0iTTU3LjAxMjYgNDguNzVMNTguNDI3OCAyNy43MDYyTDY2LjIzNTEgMjkuMDE5OEw1NS4wMDA0IDEyLjE4NzVMNDMuNzY1NiAyOS4wMTk4TDUxLjU3MjkgMjcuNzA2Mkw1Mi45ODgyIDQ4Ljc1SDU3LjAxMjZaIiBmaWxsPSJ3aGl0ZSIvPgogICAgPHBhdGggZD0iTTE5LjYzMjIgMjguOTkyN0MyNS43MjI0IDI5LjgzOSAzMS41MDQxIDMxLjU1MjEgMzYuMjEyNiAzNS43NjM1QzM3LjYzMzkgMzcuMTY1OSAzOC45Nzc0IDM4LjY0NjUgNDAuMjM3IDQwLjE5ODRMNDAuNTkyNSA0MC41OTExTDQ1Ljc4NCAzNy4yNzM0TDQyLjQzMDMgNDkuODgwN0wzMS4wMjc5IDQzLjczOTVWNDMuNTVMMzYuMTkyNSA0Mi40Mzk2QzMyLjc0NSAzNC43NTQ3IDI2LjM5OTggMzEuMjY3NyAxOC41NzkxIDI5Ljg1MjZMMTkuNjMyMiAyOC45OTI3WiIgZmlsbD0id2hpdGUiLz4KICAgIDxwYXRoIGQ9Ik05MC4zNjc2IDI4Ljk5MjdDODQuMjc3NCAyOS44MzkgNzguNDk1NyAzMS41NTIxIDczLjc4NzIgMzUuNzYzNUM3Mi4zNjU5IDM3LjE2NTkgNzEuMDIyNCAzOC42NDY1IDY5Ljc2MjggNDAuMTk4NEw2OS40MDczIDQwLjU5MTFMNjQuMjE1OCAzNy4yNzM0TDY3LjU2OTUgNDkuODgwN0w3OC45NzE5IDQzLjczOTVWNDMuNTVMNzMuODA3MyA0Mi40Mzk2Qzc3LjI1NDggMzQuNzU0NyA4My42IDMxLjI2NzcgOTEuNDIwNyAyOS44NTI2TDkwLjM2NzYgMjguOTkyN1oiIGZpbGw9IndoaXRlIi8+CiAgICA8cGF0aCBkPSJNNTUuMDAwNSA4OC42MTY3QzQzLjg1OTcgODguNjE2NyAzNC41MjMxIDg1LjQ4ODYgMzIuMDYxNSA4MS4yOTA2VjkwLjA5MjdDMzIuMDYxNSA5NS4zNjA0IDQyLjMzMDQgOTkuNjI2MSA1NS4wMDA1IDk5LjYyNjFDNjcuNjcwNyA5OS42MjYxIDc3LjkzOTYgOTUuMzYwNCA3Ny45Mzk2IDkwLjA5MjdWODEuMjkwNkM3NS41MDQ4IDg1LjQ4ODYgNjYuMTc0OSA4OC42MTY3IDU1LjAwMDUgODguNjE2N1oiIGZpbGw9IndoaXRlIi8+CiAgICA8cGF0aCBkPSJNNTUuMDAwNSAxMDEuNzA1QzQzLjg1OTcgMTAxLjcwNSAzNC41MjMxIDk4LjU3NjYgMzIuMDYxNSA5NC4zNzg3VjEwMy4xODFDMzIuMDYxNSAxMDguNDQ4IDQyLjMzMDQgMTEyLjcxNCA1NS4wMDA1IDExMi43MTRDNjcuNjcwNyAxMTIuNzE0IDc3LjkzOTYgMTA4LjQ0OCA3Ny45Mzk2IDEwMy4xODFWOTQuMzc4N0M3NS41MDQ4IDk4LjU4MzMgNjYuMTc0OSAxMDEuNzA1IDU1LjAwMDUgMTAxLjcwNVoiIGZpbGw9IndoaXRlIi8+Cjwvc3ZnPg==\");\n\t\tdisplay: block;\n\t\twidth: 6rem;\n\t\taspect-ratio: 1 / 1;\n\t\tmargin: auto;\n\t\ttransform: translateY(50%);\n\t}\n\n\n\tmain {\n\t\ttext-align: center;\n\t\tdisplay: flex;\n\t\tflex-direction: column;\n\t}\n\n\tmain .main-box h1 {\n\t\tfont-size: 2.5rem;\n\t\tfont-weight: normal;\n\t\tmargin: 2.5rem auto auto auto;\n\t}\n\n\tmain .main-box h3 {\n\t\tfont-weight: normal;\n\t\tmargin: 1rem 0 1rem 0;\n\t}\n\n\tmain .main-box h3 span {\n\t\tcolor: var(--color-site-3);\n\t\tfont-weight: bold;\n\t}\n\n\tmain .main-box p {\n\t\tcolor: var(--color-site-1-c-1);\n\t\tmargin: 0 0 0.5rem 0;\n\n\t}\n\n\tmain .main-box p span {\n\t\tcolor: var(--color-site-1-c);\n\t}\n\n\tmain .main-box .reasons {\n\t\tmargin: auto;\n\t\tdisplay: flex;\n\t\tflex-direction: column;\n\t\talign-items: center;\n\t}\n\n\tmain .main-box .reasons p {\n\t\tcolor: var(--color-site-1-c-1);\n\t\tmargin: 2.25rem auto 2.25rem auto;\n\t\ttext-align: left;\n\t\twidth: auto;\n\t\tdisplay: inline-block;\n\t\toverflow-wrap: anywhere;\n\t}\n\n\tmain .main-box {\n\t\tmargin: 0 auto;\n\t\tborder-radius: 0.5rem;\n\t\tbox-shadow: 0 8px 20px 0 rgb(0 0 0 / 10%);\n\t\tbackground-color: var(--color-site-2);\n\t\tborder-color: var(--color-site-2-1);\n\t\tborder-radius: 0.5rem;\n\t\tpadding: 1.25rem 1.25rem 0.2rem;\n\t\ttransition: all 0.5s;\n\t\twidth: 45rem;\n\t}\n\n\tmain .main-box.expanded {\n\t\twidth: 80rem;\n\t\ttransition: all 0.6s;\n\t}\n\n\tmain .main-box .sign-in-button {\n\t\tborder: none;\n\t\twidth: fit-content;\n\t\tmin-width: 8rem;\n\t\theight: 2.5rem;\n\t\tbackground-color: var(--color-accent-1);\n\t\tborder-radius: 0.3rem;\n\t\tdisplay: flex;\n\t\tjustify-content: center;\n\t\talign-items: center;\n\t\tmargin-bottom: 1.5rem;\n\t\tcursor: pointer;\n\t\ttext-decoration: none;\n    \tcolor: var(--color-accent-1-c);\n\t}\n\n\tmain .main-box .sign-in-button:hover {\n\t\tbackground-color: var(--color-accent-1-1);\n\t\tcursor: pointer;\n\t}\n\n\t.container {\n\t\tflex-grow: 1;\n\t\tdisplay: flex;\n\t\talign-items: center;\n\t\tjustify-content: center;\n\t}\n\n\t.layout {\n\t\tdisplay: flex;\n\t\tflex-direction: column;\n\t\tbox-sizing: border-box;\n\t\tletter-spacing: 0.176px;\n\t}\n\n\t.collapsible {\n\t\twidth: auto;\n\t\tbackground-color: var(--color-site-3);\n\t\tborder-radius: 0.3rem;\n\t\tdisplay: flex;\n\t\tflex-direction: column;\n\t\tmargin: 1rem 0;\n\t}\n\n\t.collapsible .collapsible__header {\n\t\tflex: 1;\n\t\twidth: auto;\n\t\tborder-radius: 0.3rem;\n\t\tdisplay: flex;\n\t\talign-items: center;\n\t\tpadding: 0.75rem;\n\t\tpadding-left: 0;\n\t\tjustify-content: space-between;\n\t\tcursor: pointer;\n\t}\n\n\t.collapsible .collapsible__header .copy-button {\n\t\tmargin: 0;\n\t}\n\n\t.collapsible .collapsible__header .header-buttons-right {\n\t\tdisplay: flex;\n\t\talign-items: center;\n\t}\n\n\t.collapsible .collapsible__header a {\n\t\tmargin: 0 0.5rem;\n\t\tdisplay: flex;\n\t\tcursor: pointer;\n\t\ttext-decoration: underline;\n\t}\n\n\t.collapsible .collapsible__header .collapsed .open {\n\t\tdisplay: block\n\t}\n\n\t.collapsible .collapsible__header svg {\n\t\twidth: 1.5rem;\n\t\tfill: var(--color-site-1);\n\t\taspect-ratio: 1 / 1;\n\t\tmargin: auto;\n\t}\n\n\t.collapsible .collapsible__header svg.clone {\n\t\tmargin: auto;\n\t\tfill: var(--color-site-1-c);\n\t\twidth: auto !important;\n\t}\n\n\t.collapsible .collapsible__header .collapsed .chevron-right{\n\t\tdisplay: none !important;\n\t}\n\n\t.collapsible .collapsible__header .chevron-down{\n\t\tdisplay: none;\n\t}\n\n\t.collapsible .collapsible__header .collapsed .chevron-down{\n\t\tdisplay: block !important;\n\t\tmargin-left: 0.2rem;\n    \tmargin-top: 0.2rem;\n\t}\n\t\n\t.collapsible .collapsible__header h3 {\n\t\tcolor: var(--color-site-1);\n\t\tmargin: 0;\n\t\tdisplay: flex;\n\t\tflex:1;\n\t}\n\n\t.collapsible .collapsible__body {\n\t\tbackground-color: var(--color-site-2-c);\n\t\tposition: relative;\n\t\tborder-radius: 0 0 0.3rem 0.3rem;\n\t\tpadding: 0;\n\t\tdisplay: flex;\n\t\tmax-height: 40rem;\n\t\toverflow: auto;\n\t\ttext-align: justify;\n\t\ttransition: all 0.6s;\n\t\theight: 0;\n\t\toverflow: hidden !important;\n\t}\n\n\t.collapsible .collapsible__body.collapsed {\n\t\toverflow: auto !important;\n\t\theight: 40rem;\n\t\ttransition: all 0.5s;\n\t\tpadding: 1rem;\n\t}\n\n\t.collapsible .collapsible__body code {\n\t\tcolor: var(--color-site-1-2) !important;\n\t\tposition: absolute;\n\t\ttext-align: left;\n\t\tfont-family: 'Hack','monospace', 'monospace';\n\t}\n\n\t.collapsible .collapsible__body pre {\n\t\tmargin: 0.5rem;\n\t}\n\n\n\tfooter {\n\t\tdisplay: flex;\n\t\tflex-wrap: wrap;\n\t\talign-items: center;\n\t\tpadding-left: 1rem;\n\t\tfont-size: .80rem;\n\t\tcolor: var(--color-site-1-c-1);\n\t\tmargin-top: 1.5rem;\n\t}\n\n\t.external-links-container {\n\t\tpadding: 0;\n\t\tflex-grow: 0;\n\t\tmargin: auto;\n\t}\n\n\t.external-links {\n\t\tdisplay: flex;\n\t\tflex-wrap: wrap;\n\t\tpadding: 0;\n\t\tmargin: 0;\n\t}\n\n\t.external-links li {\n\t\tlist-style: none;\n\t\tborder-right: 1px solid var(--color-site-1-2);\n\t\tmargin: auto;\n\t\tpadding: 0 0.5rem;\n\t}\n\n\t.external-links li:first-child {\n\t\tpadding-left: 0;\n\t}\n\n\t.external-links li:last-child {\n\t\tborder-right: none;\n\t}\n\n\t.external-links a, .external-links a:visited {\n\t\ttext-decoration: none;\n\t\tcolor: inherit;\n\t\twhite-space: nowrap;\n\t}\n\n\t.external-links a:hover, .external-links a:focus {\n\t\ttext-decoration: underline;\n\t}\n\n\t.copyright {\n\t\tflex-grow: 1;\n\t\ttext-align: right;\n\t\tmargin: 0 1rem;\n\t\twhite-space: nowrap;\n\t\tcolor: var(--color-site-1-c);\n\t\tmax-height: 40px;\n    \tmargin: auto 1rem auto;\n\t}\n\n\t.oracle-logo {\n\t\ttext-align: right;\n\t\tpadding: 0;\n\t\tposition: relative;\n\t\tdisplay: flex;\n\t\tflex-direction: column;\n\t\tmargin-right: 1rem;\n\t}\n\n\t.oracle-logo figure {\n\t\twidth: 2.5rem;\n\t\tdisplay: block;\n\t\taspect-ratio: 1 / 1;\n\t\tbackground-size: contain;\n\t\tmargin: auto 0;\n\t\tbackground-image: url( 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAH4AAAB+CAYAAADiI6WIAAAACXBIWXMAABcRAAAXEQHKJvM/AAAFrElEQVR4nO2cTUxdRRiGh9KUBCgJGmwhJBpuxGi0RuvGuqguyqpdsNKaGjf+4FZh4wbYuGlx29qlf3UliXZlN3VDVzWRRZPS3KYmjRckkQQKCaSoeQ+9Sb0nZT703pk5532fzQ3n3IRz7jM/38x8M23XRl752wk69kk5JxJPisSTIvGkSDwpEk+KxJMi8aRIPCkST4rEkyLxpEg8KRJPisSTIvGkSDwpEk+KxJMi8aRIPCkST4rEkyLxpEg8KRJPisSTIvGkSDwpEk+KxJMi8aRIPCkST4rEkyLxpEg8KRJPisSTsr9or72/+6DrHBp2PS8ezf7uqgy79q6Due+1ko3qgru/vpZ9rldvus2lWtgfoQkUQnzHoX732LHXXd/IKdc59HTufmh6jrz8r/+4+UfNrf563S3/dNmtzl+P/nwWkj7ZsufIUdc3ctL1nTiZu5cqKAR3v7qYFYKUSVI8mvMnxz4ulPBGNm7fcnfOzyTbAiQnHk16ZXzStXd15+4VkcXZ79ydCzPJPXlS4p8a+8QdHn0rd73ooPbfmPjQ3b+3lsybJDOcQy0vo3SAgPS5s19kXVgqJCEe0ovcn1tITX70pn7wnQ/c4Jn3c9d9bK/fc+vVhSjBE+YOOivDruOJ/tw9H2j25z962/Ot1hN1HI/h2l6lr87/4hZnL7k/567m7oUGBaDvxKlsyGkNRlHzEcvEDvii1Xg0eS+c/8Zca1IeHuFd0F31vno8d+9R3JgYi/ou0fr4w6OnzdKXr1zOmsdUx8SI1m9OjbuF6YmsC7JQmZiM+sxRxGMK1trE/3bhc1c9N527niLofjBss8hHoUcXEYso4vtHbcENanpt9lLuesog4IR8CwhsYxFFvKWkI4grSk1vBPLRUvlArcdMZQyCi8eLWiLg6rmp3LUigZYKAamP3mP2gLCZBBdveVE08UVc424EoxAfNDW+nkCxG1jWLAMYhWCZdjfQ+mE+IzRBxWO86xvCoXksQ22vs/i9PzjFRFBogopHypQPZLKUCcvcQ8ehgdy1VhO8xvsoSuqSFUT4PjpLX+MNL5jSmnWzsM7mhUTp1QGw1PrQSHwAUkrAqBNU/HYJm3ELKaSENxJUvKXJs4zziwQWpHxsLv3u+UbzCSre8oIxxrStxFKQY8xbBBZf80a4SGZIsU/8r1imZGPMXQQP7izjdCRplAE085asnI3b4aP+8OINpbt/9HQpar1lvR3LzzHmLoKLx8qbDyxcDJ6Jl6TQDLJ9f4aU8eUrP+auhSC4eJTulWs/5643gs0VsZYs/y9Z8qUhpw7xzsqc/7doBVEmcGqGFSv3YKNF0aJ8SMfGCUsiKXL0Yk1RRxGPAA99mw80+fgRi1Lz69ItEzao7Zb0rFYRbcrWmloF+cOTZ7NNCCkHfCicL335g3mWDqlZMRek2t+rDERJbsvG821t5uyT7mefd4+/MeK219fc1lLN/bW1lftODPD8lfEpN/Dmu27fgQOmJ0Cyya3PPs1dD0n0vXNoGhuPFvGBQoP+cecMmoVsRjDE7Ff9/B18Qnjva8f3vH8Oz47NIbGzjKKL30u/WAZib52qE31ZFv0cNiBYUpGLTnVmOpkMoyTW48suH8079tWldCBSMokYdfmWmb0iUT8GJYVt3Q+T5KlXZTkACQcf3f36YpJ5hMmec4egD6t0WLApWgHY2fc3lfT+gKQPOHQPCgAWO1I51fJRoB9HH16b/bYQG0KSF/8wWN9GRkvX0DNZqvbOObZxWgPUakwmYR5hZe5qkpm0u1Eo8aJ5KL2aFIknReJJkXhSJJ4UiSdF4kmReFIknhSJJ0XiSZF4UiSeFIknReJJkXhSJJ4UiSdF4kmReFIknhSJJ0XiSZF4UiSeFIknReJJkXhSJJ4UiSdF4kmReFIknhSJJ0XiSZF4UiSeFIknReJJkXhGnHP/AL4l5ZTY65aqAAAAAElFTkSuQmCC' );\n\t}\n\n\t.oracle {\n\t\tdisplay: flex;\n\t\tmargin: auto;\n\t\tflex-grow: 1;\n\t}\n\n\n\t@media (max-width: 1200px) {\n\t\tmain .main-box {\n\t\t\tmax-width: 100vw;\n\t\t}\n\t\t.external-links li {\n\t\t\tmargin: auto;\n\t\t}\n\t\t.oracle {\n\t\t\tflex-grow: 0;\n\t\t\tdisplay: flex;\n\t\t\tmargin: auto;\n\t\t\tflex-direction: column;\n\t\t\twidth: 100vw;\n\t\t}\n\t\t.copyright {\n\t\t\tmargin: auto;\n\t\t\tpadding-top: 1rem;\n\t\t}\n\t\t.oracle-logo {\n\t\t\tmargin: auto;\n\t\t\tpadding-top: 2rem;\n\t\t}\n\t}\n\n\t@font-face {\n    font-family: 'Hack';\n    src: url(\"data:font/ttf;base64,AAEAAAARAQAABAAQRFNJRwAAAAEABLiYAAAACEdTVUJ/g3y5AASvwAAAA3ZPUy8yK+co+QAAAZgAAABgVFRGQRGA77oABLM4AAAFYGNtYXCelmr8AAAaUAAADMxjdnQgyy0dcAAANXAAAAEMZnBnbTa3nDYAACccAAANdmdhc3AAAAAQAASvuAAAAAhnbHlm7jlOYQAATxQAA/e6aGVhZA2EsHMAAAEcAAAANmhoZWEJAQh8AAABVAAAACRobXR47RBB/wAAAfgAABhYbG9jYQz4AU4AADZ8AAAYmG1heHAIyw6kAAABeAAAACBuYW1l7woKXwAERtAAACGAcG9zdLl+PDkABGhQAABHZnByZXCdn4nYAAA0lAAAANwAAQAAAAMAxc134YpfDzz1AAYIAAAAAADWE8KAAAAAANbDoqT8Rv2jBUsH6wAAAAYAAgABAAAAAAABAAAHbf4dAAAE0fxG/4YFSwABAAAAAAAAAAAAAAAAAAAGBwABAAAGJQCAAB4AAAAAAAIAmgCsAIsAAAFiDXYAAAAAAAQE0QGQAAUAAAUzBMwAAACZBTMEzAAAAswAZgISAAACCwYJAwICAgIEpQAG7xAAuPsAAAAgAAAAAFNSQwAAQAAA/v8GFP4UAZoHbQHjIAABn9/XAAAEYAXVAAAAIAADBNEAaAAAAAAE0QAABNEAAATRACUE0QAlBNEAJQTRACUE0QAlBNEAJQTRACUE0QAABNEApgTRAIsE0QCLBNEAiwTRAIsE0QCLBNEAiQTRAAgE0QCJBNEACATRAMUE0QDFBNEAxQTRAMUE0QDFBNEAxQTRAMUE0QDFBNEAxQTRAOkE0QBmBNEAZgTRAGYE0QBmBNEAZgTRAIkE0QADBNEAyQTRAMkE0QDJBNEAyQTRAMkE0QDJBNEAyQTRAMkE0QDJBNEAbQTRAIkE0QCJBNEA1wTRANcE0QDXBNEA1wTR//YE0QBWBNEAiwTRAIsE0QCLBNEAiwTRAJME0QCLBNEAdQTRAHUE0QB1BNEAdQTRAHUE0QAGBNEAdQTRAHUE0QAIBNEACATRAHUE0QBIBNEArATRAMkE0QByBNEAjwTRAI8E0QCPBNEAjwTRAIsE0QCLBNEAiwTRAIsE0QCLBNEALwTRAC8E0QAvBNEALwTRAJME0QCTBNEAkwTRAJME0QCTBNEACQTRAJME0QCTBNEAkwTRAJME0QCTBNEAOQTRAAAE0QAABNEAAATRAAAE0QAABNEAEgTRACUE0QAlBNEAJQTRACUE0QAlBNEAbgTRAG4E0QBuBNEAbgTRAIgE0QCIBNEAiATRAIgE0QCIBNEAiATRAIgE0QCIBNEAiATRAIgE0QApBNEAwQTRAKQE0QCkBNEApATRAKQE0QCkBNEAewTRAIkE0QBdBNEAewTRAHwE0QB8BNEAfATRAHwE0QB8BNEAfATRAHwE0QB8BNEAxQTRAHwE0QB8BNEApwTRAJcE0QCXBNEAlwTRAJcE0QCXBNEAwwTRAEYE0QEMBNEBDATRAQwE0QEMBNEBDATRANoE0QEMBNEAyQTRAQwE0QEMBNEBDATRAO4E0QDiBNEA4gTRALQE0QCgBNEAoATRAKAE0QBMBNEAbQTRAMME0QDDBNEAwwTRAMME0QDDBNEAwwTRAIkE0QCJBNEAiQTRAIkE0QCJBNEAIATRAIkE0QCJBNEAdQTRAIkE0QAvBNEALwTRAIkE0QAOBNEAvgTRAL4E0QCJBNEBLgTRAS4E0QEuBNEA5ATRANUE0QDVBNEA1QTRANUE0QDVBNEAvATRAIME0QCDBNEAgwTRAIME0QDDBNEAwwTRAMME0QDDBNEAwwTRACcE0QDDBNEAwwTRAMME0QDDBNEAwwTRAGQE0QAABNEAAATRAAAE0QAABNEAAATRAEwE0QBoBNEAaATRAGgE0QBoBNEAaATRAMsE0QDLBNEAywTRAOIE0QDLBNEBDgTRAPQE0QAlBNEApgTRAKYE0QDXBNEA1wTRANcE0QAhBNEAxQTRAMUE0QDFBNEADwTRAIkE0QCLBNEAiwTRAIsE0QCJBNEAiQTRAA4E0QBWBNEAiQTRAHUE0QCJBNEAxQTRAIsE0QAvBNEAfATRAHwE0QBCBNEAEgTRAIkE0QBkBNEAcgTRAF0E0QCJBNEALgTRAMUE0QA0BNEAQQTRAAAE0QAsBNEAiwTRAIEE0QCpBNEAyQTRAMkE0QBtBNH/3ATRAFAE0f/SBNEAIATRAHUE0QBfBNEArwTRAA8E0QCJBNEAiQTRAD0E0QCLBNEALwTRACUE0QAlBNEAEgTRAKAE0QDJBNEADwTRAIkE0QCJBNEAggTRACUE0QAlBNEAxQTRAHUE0QB1BNEADwTRAIkE0QAaBNEAiwTRAIsE0QB1BNEAdQTRAHUE0QCzBNEAfATRAHwE0QB8BNEAfwTRANcE0QBSBNEAiQTRAHIE0QAABNEAiATRAH0E0QDvBNEBMwTRATME0QE9BNEAaQTRAHwE0QB8BNEAfATRADsE0QCpBNEAwwTRAMME0QDDBNEA7ATRAOwE0QAyBNEAPQTRAL0E0QCJBNEAvQTRAL4E0QCkBNEA1gTRAHIE0QByBNEAaATRAEwE0QClBNEAuATRAH0E0QBpBNEAvQTRALIE0QDhBNEAPATRAGgE0QAQBNEAagTRANUE0QClBNEA4QTRAOQE0QDkBNEA7gTRAEEE0QB2BNEASwTRADIE0QCJBNEAuwTRAOME0QA7BNEAqQTRANgE0QC3BNEApQTRANYE0QBcBNEAXATRAGAE0QDDBNEBxwTRADsE0QDYBNEAzQTRAK8E0QCPBNEAjwTRAHwE0QCOBNEAjgTRADsE0QCpBNEAkQTRAMME0QDDBNEAiQTRAIkE0QCJBNEA1wTRAGgE0QBoBNEAaATRAKUE0QEkBNEAaATRAKkE0QCEBNEAAATRANUE0QC5BNEAAATRACkE0QAlBNEAdQTRAMME0QB3BNEAgATRAFUE0QA2BNEAgATRAGAE0QB4BNEAgATRAEkE0QBGBNEAuwTRALgE0QBdBNEANgTRAJME0QBHBNEAXwTRADYE0QBWBNEAVgTRAEAE0QA2BNEAYATRAJME0QBgBNEALQTRAGAE0QBiBNEAkwTRACEE0QBpBNEAkwTRAEAE0QCbBNEARgTRACQE0QB1BNEARwTRAGcE0QDBBNEASQTRALgE0QC4BNEAZwTRAOME0QC3BNEAagTRAF0E0QC8BNEBlwTRAGgE0QCJBNEAvATRAL0E0QCmBNEAwgTRAJoE0QCQBNEA2QTRABgE0QCoBNEAvQTRAPIE0QBiBNEAqATRALYE0QC9BNEAtgTRAGgE0QC8BNEAkwTRATUE0QBoBNEATwTRAIkE0QAZBNEAcATRAKAE0QCfBNEAbwTRADcE0QCgBNEAngTRALcE0QAtBNEAoATRAJ4E0QCgBNEAkgTRAJ0E0QA3BNEAoATRAJ8E0QA3BNEAnwTRAC0E0QA3BNEALQTRAIIE0QA3BNEAngTRADcE0QCeBNEAVgTRAIoE0QChBNEAoATRALME0QCfBNEAjATRAIoE0QCgBNEAnwTRAJcE0QByBNEANwTRAGoE0QCzBNEAZQTRAKAE0QGVBNEAhQTRAOwE0QCYBNEAlQTRAGYE0QCPBNEAhQTRAIsE0QCDBNEAfwTRAGYE0QAbBNEAGwTRABsE0QAbBNEAGwTRABsE0QAbBNEAGwTRABsE0QAbBNEBWATRAUIE0QFGBNEAgATRAIAE0QHpBNEBPwTRAcoE0QGQBNEB6QTRAQAE0QBQBNEBxgTRAPQE0QHQBNEAAgTRAcME0QD0BNEAIgTRAMEE0QFSBNECEATRAYoE0QBmBNEAXgTRAAAE0QEdBNEBPwTRAcYE0QD0BNEAAATR/7wE0QHPBNEBWgTRACIE0QClBNEAywTRAMEE0QBYBNEA2gTRAdAE0QDBBNEAwQTRAdgE0QHYBNEAfwTRAQUE0QFDBNEBHgTRAc8E0QFaBNEBzwTRAVoE0QEoBNEB3gTRAdgE0QHYBNEA8ATRAPAE0QFnBNEBbgTRAUQE0QFEBNEA0wTRANME0QDOBNEAzgTRAckE0QHJBNEBGQTRAPoE0QE1BNEBNwTRASwE0QEsBNEBkATRAPoE0QAABNEBNQTRAI4E0QDOBNEBZATRAWQE0QFkBNEAAATRAQAE0QH+BNEA0wTRANME0QDTBNEBzwTRAc8E0QHPBNEBkwTRANME0QGsBNEBFgTRAIAE0QGsBNEBFgTRAIAE0QEpBNEBKATRAYcE0QGHBNEAvwTRAL8E0QEjBNEB1gTRAXoE0QDhBNEBeQTRALIE0QC8BNEB/wTRAWQE0QAABNEAAATRAAAE0QAABNEAAATRAAAE0QAABNEAAATRAAAE0QAABNEAAATRAAAE0QAABNEAAATRACUE0QAABNEA0gTRAHsE0QDNBNEAvgTRAPUE0QAlBNEAAATRAAAE0QCLBNEACgTRAIsE0QC4BNEACgTRAF8E0QBtBNEAAATRAAoE0QAABNEAKgTRACoE0QAvBNEAHgTRAC4E0QBqBNEANQTRACcE0QAABNEAggTRAC8E0QBoBNEAJQTRAH4E0QBYBNEApgTRAFQE0QBQBNEAUATRAFgE0QBYBNEB6QTRAIIE0QBKBNEAWATRAFgE0QCyBNH/+gTRAFgE0QBYBNEAKQTRAIEE0QB8BNECAQTRAKQE0QBYBNEAVgTRAKQE0QBYBNEApATRAFgE0QCWBNEAggTRAFgE0QBYBNEAfgTRAL4E0QAhBNEAWATRAAAE0QBYBNEAWATRAJgE0QBYBNEAWATRALoE0QA7BNEAWATRAFgE0QBYBNEAWATRAIIE0QCPBNEAuwTRAAAE0QEcBNEBHATRARwE0QEcBNEBHATRARwE0QBKBNEAdQTRALIE0QCCBNEAggTRAIIE0QD6BNEAmATRAFgE0QErBNEAOwTRADsE0QISBNEAPwTRADUE0QC8BNEB6ATRALsE0QBYBNEASgTRAFcE0QBYBNEAWATRAFgE0QBYBNEAWATRAFgE0QBYBNEAWATRAFgE0QBYBNEAWATRAFgE0QBXBNEAWATRAFgE0QBYBNEAWATRAFgE0QBXBNEASgTRAEoE0QBYBNEAWATRAFgE0QBYBNEAWATRAFgE0QBYBNEARQTRAFgE0QBYBNEAWATRAFgE0QBWBNEAVgTRAFYE0QBWBNEAVwTRAFgE0QBYBNEAWATRAFgE0QBWBNEAVgTRAFYE0QBWBNEAVgTRAFYE0QBWBNEAVgTRAFYE0QBYBNEAVgTRAFYE0QBWBNEAVgTRAFYE0QBWBNEAWATRAFgE0QBYBNEAWATRAFgE0QCDBNEAgwTRAFgE0QBYBNEAWATRAFgE0QBeBNEAXgTRAFAE0QBQBNEAUATRAFAE0QBQBNEAUATRAFAE0QBQBNEAUATRAFAE0QBQBNEAWATRAFgE0QBYBNEAWATRAFgE0QBYBNEAWATRABwE0QCDBNEAgwTRAGkE0QEJBNEAWATR//gE0f/4BNEAWgTRAFoE0QBYBNEAWATRAFYE0QBYBNEAVgTRAFYE0QBWBNEAVgTRAFgE0QBYBNEAWATRAFgE0QBWBNEAVgTRAFYE0QBWBNEAUATRAc8E0QFaBNEBzwTRAVoE0QEYBNEBGATRARgE0QEZBNEC9gTRARkE0QEYBNEBGATRARgE0QEYBNEC9QTRARgE0QIMBNEAEQTRAgwE0QIMBNEAEATRAgsE0QAQBNECAQTRABwE0QB1BNEAdQTRAFgE0QBYBNEAUATRAJYE0QBYBNEAWATRAKQE0QAlBNEBHATRALgE0QAABNEAuATRARwE0QC4BNEAQgTRALgE0QBCBNEBHATRACoE0QBCBNEAQgTRAEIE0QBCBNEAQgTRAEIE0QBCBNEAQgTRAEIE0QBZBNEAWQTRAEIE0QBCBNEBHATRAEIE0QEcBNEAQgTRAEIE0QBC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ADkAPwBLAE0ATgBSAFcAWwBmAGcAbABtAHICbwJEAnAFegJYBYoAdgCBAIIAhwCLAJYAlwCcAJ4AqQCqAKwAsQCyALgAxgDIAMkAzQDTANcA4gDjAOgA6QDuAm0FcAJuAuYCtQJOAsQCzgLGAuIFcQV3BYgFdQDzBf8C/AKRBXYFjAV5AwkCQQJCBYMGAQV0BgYFhgJAAPQGAAI6AjcCOwJTAAYGCAAEAAoABQAJAAsAEAAcABcAGQAaACwAKAApACoAEwA+AEMAQABBAEkAQgL/AEcAXwBcAF0AXgBuAEwA0gB7AHcAeQB/AHoAfgCAAIUAkQCMAI4AjwCjAKAAoQCiAIgAtwC8ALkAugDEALsC6gDCANsA2ADZANoA6gDHAOwABwB8AsIAeAAIAH0ADgCDBgkGCgARAIYADwCEABQAiQAVAIoAHQCSAJMAlAAbAJAAHgCVABgAjQYLBgwAIQCYACQAmwAjAJoGDQYOACYAnQAvAKgALQCkAKUApgAuAKcAKwCfBhoGGwYPBhAAMgCrBiAANACtADYArwA1AK4GHAYdADcAsAA6ALMAPAC1ADsAtAYiAD0AtgBGAL8AwADBAEUAvgBKAMUATwDKAFEAzABQAMsAUwDOBhEGEgBVANAAVADPBh4GHwBZANUAWADUAGUA4QBiAN4GIwYkAGQA4ABhAN0AYwDfAGkA5QBvAOsAcABzAO8AdQDyAHQA8ADxAEQAvQBgANwAIgCZAEgAwwBWANEAWgDWBYcFhQWEBYkFjgWNBY8FiwWABX4GAwYEBboFvwXABd0FowWkBaUBrwXBBcIF4wXkBeUF2wXgBdwF3wXhBd4F4gD9AP4BJQD5AR4BHQEgASEBIgEbARwBIwEFAQMBDwEWAPUA9gD3APgA+wD8AP8BAAEBAQIBBAEQAREBEwESARQBFQEZARoBGAEfASQBFwFQAVEBUgFTAVYBVwFaAVsBXAFdAV8BawFsAW4BbQFvAXABdAF1AXMBegF/AXIBWAFZAYABVAF5AXgBewF8AX0BdgF3AX4BYAFeAWoBcQEmAYEBJwGCAPoBVQEoAYMBKQGEASoBhQErAYYBLAGHAS0BiAGrAawBLgGJAS8BigEwAYsBMQGMATIBjQEzAY4BNAE1AZABNgGRATcBkgE4AZMBjwE5AZQBOgGVAa0BrgE7AZYBPAGXAT0BmAE+AZkBPwGaAUABmwFBAZwBQgGdAUMBngFEAZ8BRQGgAUYBoQFHAaIBSAGjAUkBpAFKAaUBSwGmAUwBpwFNAagBTgGpAU8BqgKrAioAawDnAGgA5ABqAOYGGQYYAHEA7QYXBhYCkgKTAo8CjgKNApQCWgJZApoCnAKdApsCmAKZApcCngV7BXwCRgJbAkkCSgJLAlwCwQMHAxYCTQJdAl4CXwYHAmACYQJSAmICYwMXAxgDGQJ3AngDGgMbAxwCawJsAtACxQLRAssCzALSAtMCzQLUAtUC1gLIAskGEwLgAuECOAI5BfAF8QXyBfMF9AX1AjwCPQI+Aj8CNgPPA8kDywPNA9ED0gPQA8oDzAPOA9QD1QPdA94D7gPvA/AD8QPfA9sECgQLBAwEEAQNBA4EDwQIBAkEGwQcBB0EFwQRBBMEFQQZBBoEGAQSBBQEFgQeBB8EIAQhBCIEIwQkBCUD6wPsBCkEJgQnBCgD/AP9BDAEMQPTBDID1gPXA9gD2QPaA9wEMwQ0BDUDyAMeAwQC8AMfAu0GAgLxAuwDAAMgAxMDIQMiAyMDCgMkAxQC/gMlAuUDJgJFAw4DJwMoAw0C9AMDAuMC+wL9AvgDxwL1AyoDKwMVAywDLQMuAy8DMAMxAzIDEgMzAzQDNQM2AzcC6QM4AzkC5AMBAu8DUQNSAvoC8wNTA1QDVQNWAwsDDAMCA2wDDwMQA20DbgNvA3AC6AN5AucDjAONA44C6wOPAvcC9gTABRgEwQS3BSIFIwUkBLkFJQUmBScEuAUoBSkFKgS6BSsFLAUtBL4FLgUvBTAFMQUyBTMFNAS/BTUFNgU3BTgFOQU6BTsEvAU8BT0FPgU/BUAFQQVCBL0FQwVEBUUFRgVHBUgFSQS7BNMExwTbBNwEzwTFBMQEyATaBNkEzgTLBMoEyQTMBM0E0gTCBMMExgTXBNgE0QTVBNYE0ATeBN0E1ARyBGoEawRsBG0EbgRvBHAEcQR6BHkEeAR3BHYEdQR0BHsEhwSIBIkEcwTfBOAE4QTiBOQE5QTmBOcE6ATpBOoE6wS0BLUEswS2BLEEsgT5BP0FCAUMBPoE/gUJBQ0FBAUGBPsE/wUKBQ4E/AUABQsFDwUFBQcEqASpBK4EmwSwBIsEmgSZBJwEigSNBI4EjwSQBJMElASRBJIEngSfBKAEoQSkBKUEpgSnBKIEowUR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AAEMGAABDMQAAQ0AAAENVAABDbwAAQ5UAAEO+AABD7gAARDsAAERZAABEhwAARJoAAETIAABE4gAARPgAAEUVAABFMAAARUkAAEVdAABFfAAARYwAAEW6AABF5wAARfcAAEYXAABGUwAARnoAAEaSAABGrwAARsQAAEbYAABG8AAARw4AAEcwAABHSwAAR2oAAEeKAABHtAAAR9cAAEgCAABILAAASFYAAEiEAABIsQAASNwAAEj+AABJRQAASWwAAEmRAABJvAAASdMAAEn2AABKGAAASmAAAEp7AABKlAAAStIAAErnAABK+gAASxUAAEsyAABLSwAAS1cAAEubAABLwgAAS98AAEwAAABMkwAATTgAAE2AAABNqQAATfYAAE4qAABOewAATqQAAE7GAABO7wAATy8AAE9aAABPqAAAT/UAAFAlAABQXAAAUIcAAFC6AABQzQAAUQQAAFEzAABRYQAAUXkAAFGQAABRpwAAUcoAAFIQAABSKwAAUl4AAFKSAABSuwAAUtwAAFMGAABTJwAAU00AAFOGAABTmwAAU7oAAFQEAABUMQAAVFAAAFReAABUkAAAVOwAAFUKAABVKwAAVW0AAFWMAABVwwAAVeQAAFYjAABWRQAAVnwAAFaXAABWxQAAVuUAAFc7AABXWgAAV3gAAFeZAABX2QAAV/UAAFg9AABYTgAAWIIAAFi5AABY3wAAWSAAAFleAABZiwAAWdYAAFn/AABaMAAAWmYAAFp7AABaogAAWukAAFsWAABbMQAAW0AAAFuDAABbuwAAW9YAAFvvAABcPAAAXGMAAFyvAABc2QAAXOoAAF0UAABdSQAAXWoAAF2cAABdywAAXhEAAF5DAABeZwAAXoQAAF7JAABe7AAAX1QAAF9jAABfqQAAX/EAAGARAABgSQAAYIAAAGCiAABg1AAAYQkAAGFjAABhjgAAYccAAGIHAABiNwAAYlQAAGKDAABiuAAAYwkAAGNMAABjdQAAY64AAGPeAABkGwAAZEcAAGRxAABksgAAZQUAAGVGAABlgwAAZcgAAGYnAABmegAAZq8AAGbpAABnSgAAZ7QAAGfvAABoGwAAaIAAAGjwAABpFgAAaVIAAGmkAABp+AAAaj4AAGpvAABquAAAaugAAGsQAABrQwAAa5UAAGuqAABr2gAAbBkAAGwzAABsZgAAbKMAAGy0AABs9AAAbTIAAG0+AABtWgAAbZYAAG3VAABuHwAAblIAAG6vAABu9AAAb08AAG+kAABv5wAAcAIAAHBzAABwuwAAcNQAAHDgAABw8gAAcQoAAHEoAABxSgAAcVsAAHF1AABxmAAAcb8AAHH8AAByHQAAcmIAAHJ0AAByrwAAcwkAAHNVAABzZQAAc3EAAHPAAABzzAAAc9sAAHPvAABz/wAAdAgAAHQbAAB0TgAAdF0AAHR1AAB0igAAdJ8AAHT+AAB1WwAAdXEAAHWtAAB11QAAdgkAAHYqAAB2ZwAAdqcAAHa7AAB2zgAAdvwAAHcrAAB3PQAAd08AAHdfAAB3bwAAd30AAHeLAAB3owAAd7sAAHfPAAB34gAAd/8AAHgfAAB4NAAAeEkAAHhaAAB4awAAeH0AAHiPAAB4nwAAeLAAAHi8AAB4yAAAePQAAHkdAAB5SAAAeXEAAHmHAAB5nQAAeaoAAHm3AAB5xAAAedEAAHneAAB56wAAefgAAHoFAAB6EgAAeh8AAHorAAB6NwAAek0AAHpiAAB6dwAAeoYAAHqVAAB6pAAAerQAAHrJAAB61QAAeuYAAHr8AAB7CAAAexgAAHstAAB7QwAAe1kAAHtpAAB7eQAAe5AAAHuoAAB75wAAe/kAAHwHAAB8JwAAfDUAAHxnAAB8gAAAfJ0AAHyxAAB8sQAAfLEAAHyxAAB8sQAAfLEAAHyxAAB8sQAAfLEAAHyxAAB8sQAAfLEAAHyxAAB8sQAAfLEAAHzlAAB85QAAfRsAAH1dAAB9mgAAfd8AAH4iAAB+bQAAfqcAAH7DAAB+7wAAf6sAAH/TAACADAAAgEoAAICPAACA4wAAgR4AAIF2AACBuwAAge4AAIILAACCLQAAgqEAAILeAACDFwAAg0wAAIN8AACDugAAg+0AAIQDAACEOwAAhGEAAIRxAACEwAAAhN0AAIUGAACFTwAAhZ8AAIXMAACF7wAAhgEAAIYwAACGeQAAhosAAIasAACGwwAAhtUAAIbhAACG9gAAh0EAAIePAACHwQAAh/IAAIgfAACIKwAAiD8AAIhQAACIaAAAiHkAAIiGAACImQAAiNwAAIj7AACJIwAAiTMAAIl6AACJ5QAAifYAAIpmAACKggAAip0AAIq0AACKzwAAiugAAIsbAACLOAAAi1oAAIt5AACLkQAAi7MAAIvfAACMAQAAjDEAAIysAACMwQAAjM4AAIzoAACM/QAAjQoAAI0dAACNSwAAjXYAAI3AAACN4wAAjigAAI5IAACOVAAAjmsAAI6GAACOqQAAjvUAAI8tAACPOQAAj4MAAI/YAACQCAAAkC0AAJBnAACQhwAAkLUAAJD3AACRPQAAkWMAAJGLAACRtAAAkdsAAJIOAACSSAAAkoEAAJLAAACTEAAAk3gAAJOqAACTzwAAlA8AAJQ3AACUVgAAlKgAAJTRAACU+gAAlSQAAJVPAACVdQAAlaMAAJXCAACV9QAAligAAJZbAACWiAAAlwYAAJdDAACXewAAl68AAJfLAACX5gAAmAEAAJgoAACYTwAAmHYAAJiNAACYpAAAmMkAAJjtAACZFwAAmUEAAJl5AACZsAAAmcMAAJnVAACZ+QAAmh4AAJouAACaPgAAmlsAAJp4AACapwAAmtUAAJrzAACbEAAAmzoAAJtqAACboAAAm8kAAJv0AACcGwAAnEUAAJxeAACcdwAAnI0AAJykAACctAAAnMQAAJ0IAACdSgAAnY4AAJ3pAACeNAAAnoAAAJ7EAACe6gAAnwYAAJ8tAACfSQAAn1oAAJ9rAACfewAAn4gAAJ+VAACfqwAAn8EAAJ/pAACgAgAAoCUAAKA0AACgRgAAoHIAAKCHAACgnAAAoM0AAKD6AAChGQAAoTcAAKFSAAChbgAAoYwAAKGqAACh1gAAof4AAKIqAACiVgAAoncAAKKYAACixgAAovUAAKMrAACjYQAAo4YAAKOUAACjogAAo7AAAKO+AACj3AAAo/EAAKQNAACkKwAApEAAAKRcAACkcQAApIYAAKSbAACksAAApMEAAKTQAACk4wAApRQAAKUwAAClRQAApVgAAKWJAAClogAApbcAAKXfAACl+gAApgQAAKYgAACmRAAApmwAAKZ/AACmtwAApv0AAKcmAACnPgAAp1IAAKdxAACnhwAAp6QAAKe3AACn1AAAp+oAAKgJAACoJgAAqEAAAKheAACofAAAqJoAAKi5AACo2QAAqP4AAKkjAACpSQAAqW4AAKmaAACp3gAAqiIAAKpyAACqkAAAqqsAAKrJAACq5AAAqv8AAKsaAACrNgAAq04AAKtrAACrggAAq6AAAKu9AACr2QAArAgAAKwuAACsVQAArIoAAKy+AACs0QAArOkAAK0BAACtGgAArTMAAK1JAACtYgAArYkAAK2uAACt1QAArgkAAK4+AACudQAArqwAAK6+AACu0AAAruAAAK7wAACvAgAArxQAAK8kAACvNAAAr1EAAK9tAACvkQAAr68AAK/TAACv7gAAsA8AALApAACwSQAAsGIAALCHAACwpAAAsMcAALDfAACxAQAAsR0AALFCAACxaQAAsYoAALG0AACx6AAAshMAALIyAACyUQAAsnMAALKWAACytQAAstQAALLzAACzEQAAsywAALNIAACzagAAs4UAALOnAACz0wAAs/sAALQlAAC0VwAAtIAAALShAAC04QAAtQsAALUiAAC1OQAAtVcAALVlAAC1hQAAtZIAALWnAAC1tAAAtckAALYBAAC2FQAAtikAALZKAAC2bAAAtnwAALaPAAC2ngAAtq0AALa8AAC2zQAAtt8AALb1AAC3CQAAtxsAALcsAAC3NgAAt08AALdnAAC3ewAAt5AAALe9AAC36gAAuBoAALhKAAC4awAAuKEAALjaAAC5EwAAuUYAALmVAAC5vgAAud4AALoAAAC6LAAAupwAALrKAAC7EQAAuzsAALuLAAC7zwAAvBIAALwoAAC8PgAAvFsAALxvAAC8gQAAvJMAALylAAC8twAAvMkAALzZAAC87gAAvQgAAL0gAAC9OAAAvVIAAL1sAAC9hgAAvaAAAL26AAC91AAAve4AAL4JAAC+IwAAvjUAAL5IAAC+YAAAvoMAAL6rAAC+zQAAvu8AAL8IAAC/MQAAv1QAAL/EAADAWwAAwNYAAMDyAADBIwAAwVwAAMGEAADBqwAAwdMAAMH8AADCDgAAwh8AAMJQAADCdQAAwqoAAMLfAADDEgAAw0kAAMOSAADD3wAAxCIAAMR1AADEmQAAxLUAAMUBAADFIwAAxVQAAMVuAADFjAAAxaAAAMW0AADFxwAAxdoAAMXkAADF8wAAxgEAAMYPAADGIAAAxjMAAMZHAADGYQAAxnAAAMZ+AADGlAAAxqcAAMa0AADGyQAAxuYAAMb8AADHGQAAxy8AAMdMAADHegAAx5IAAMeyAADH2gAAyAIAAMgPAADIKQAAyFwAAMiKAADIpAAAyMEAAMj7AADJGwAAyTsAAMllAADJhwAAya0AAMngAADKDgAAyjgAAMpYAADKhwAAyq0AAMrnAADK+QAAy0AAAMtpAADLjgAAy64AAMvKAADL7AAAzBIAAMwvAADMSQAAzIEAAMy/AADM0QAAzO4AAM0WAADNOwAAzcAAAM4DAADOPAAAzvsAAM9AAADPggAA0B4AANArAADQQAAA0F0AANB6AADQlgAA0LAAANDUAADQ/gAA0ScAANFQAADReQAA0Y0AANGZAADRrgAA0bsAANHFAADRzgAA0dwAANHkAADR+AAA0gUAANIcAADSKQAA0kkAANJcAADSbwAA0ngAANKAAADSjQAA0pkAANKjAADSrAAA0rcAANK/AADS0gAA0t8AANLwAADS/AAA0woAANMUAADTHwAA0y0AANNEAADTVwAA02oAANOBAADTjgAA06kAANO/AADT1wAA0/gAANQaAADUMwAA1E4AANR2AADUoAAA1LYAANTMAADU4gAA1PgAANUOAADVJAAA1UEAANVeAADVfAAA1ZkAANW2AADV0wAA1fsAANYnAADWUwAA1nsAANanAADW1AAA1v0AANclAADXUAAA13sAANejAADXzgAA1/kAANgiAADYPwAA2FwAANh0AADYjAAA2KkAANjGAADY3wAA2QUAANksAADZTAAA2WwAANmSAADZuQAA2dkAANoNAADaQQAA2m8AANqdAADaywAA2vkAANsvAADbZwAA250AANvVAADcAwAA3DEAANxlAADcmQAA3MgAANzaAADc7AAA3P4AAN0RAADdKgAA3UMAAN1kAADdhwAA3Z0AAN2zAADd1gAA3eMAAN37AADeCAAA3hoAAN4pAADeQgAA3k8AAN5iAADedAAA3poAAN6sAADe0AAA3twAAN7uAADfVAAA398AAN/3AADgWAAA4MAAAOEQAADhMgAA4WMAAOF2AADhkwAA4bwAAOHrAADh+wAA4gsAAOIZAADiQgAA4mMAAOJxAADilQAA4qgAAOLSAADi4wAA4wIAAOMXAADjJwAA4zsAAONKAADjdgAA45gAAOPBAADj2wAA4/QAAOQPAADkJQAA5EoAAORiAADkdwAA5I8AAOSYAADkuwAA5NoAAOTrAADlEQAA5TMAAOVqAADlegAA5YUAAOWTAADlnwAA5cAAAOXzAADmCAAA5igAAOZFAADmYQAA5o0AAOaqAADmxgAA5t0AAOb+AADnGAAA5zkAAOdnAADnfgAA56IAAOfDAADn2gAA6Bs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

---

**Cursor**

The popup is from startup `reset_checkpoint` with empty RFID/truck fields; GMDC is returning an HTML error page instead of JSON. I'll stop that idle call and only notify GMDC when there is a real transaction.

Reset is using username/password from `iot_configuration.json` (`GMDC_API_USER`), while the other GMDC APIs use `.env` (`GMDC_API_USERS`). ORDS then returns an HTML error page, which the UI treats as a server error. I'll align credentials and skip the idle empty-payload call that triggered the popup.

The popup was from the **startup** `reset_checkpoint` call, not from a real truck cycle.

Two things were wrong:

1. **Wrong credentials.** `iot_configuration.json` had a separate reset username/password. RFID and the other GMDC APIs use `OCI_USERNAME` / `OCI_PASSWORD` from `.env`. ORDS rejected reset and returned an HTML error page, which the dashboard showed as **RESET SERVICE SERVER ERROR**.
2. **Empty payload.** Startup sent `rfid_no` and `truck_details` as empty strings. GMDC does not accept that.

Reset now uses the same OCI credentials as the other APIs. It is **not** called when there is no RFID / truck details (startup and idle UI reset). It still runs when a transaction is open (RFID fail, abort, reset mid-cycle).

Restart Mine-entry and dismiss the old popup; it should not come back on boot.

---

**User**

@Untitled-1 (1-8) 

---

**Cursor**

I'll check how ANPR mismatch and status-check are shown on the dashboards, then align Tracking Point with the yellow blink used on the other checkpoints.

Check-status HTTP 4xx was replacing the mismatch warning with a red “request failed” message, and the warning step had no yellow blink. I’ll keep the waiting copy, treat reachable 4xx as still waiting, and add the blink on all three dashboards.

Tracking Point was showing **“Status-check service request failed”** because check-status HTTP 4xx was treated as a dead API. That is the normal “not updated yet” retry, so the ANPR step now stays on the mismatch wait copy and blinks yellow on all three dashboards.

**What the operator sees**
- ANPR Validation Process shows **“ANPR mismatch — waiting for check-status.”** (or the Err-2 / status-2 variant).
- That step **blinks yellow** on Mine-entry, Tracking Point, and Tare weighbridge.
- Unreachable / 5xx check-status still raises the red popup. Reachable 4xx no longer turns the step red.

Hard-refresh the dashboard (or restart the app) so the new CSS loads. I verified this with the workflow and CSS tests; I could not exercise the live blink in a browser here.

---

**User**

When Move forward is being done, then announce the TareWb-App/voice/information/forward.wav file

---

**Cursor**

I'll find where “Move forward” is triggered in TareWb and wire it to play `voice/information/forward.wav`.

MOVE FORWARD currently delays the first clip by 5 seconds, and config still points at `static/voice`. I’ll play `voice/information/forward.wav` as soon as MOVE FORWARD starts, and point the pack at `TareWb-App/voice`.

When the weighbridge shows **MOVE FORWARD**, it now plays `TareWb-App/voice/information/forward.wav` immediately.

That clip was already mapped in the voice service, but positioning waited 5 seconds before the first play, and config pointed at `static/voice` instead of `voice`. Both are fixed. The same clip still repeats every 5 seconds until the truck is on the platform or leaves after exit grant.

Put the WAV at:

`TareWb-App/voice/information/forward.wav`

Restart TareWb so the new `voice.directory` takes effect.

---

**User**

URL: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/vadhghat_boom_close
Payload: {
  "truck_details": "V|00000000000000000015c01b|OD14AE3900|45000|26000|50|9580109261|10.10.180.12"
}
Response: {
  "status": 200,
  "message": "Vadhghat Boom Close completed successfully."
}
--------------------------------------------------
2026-09-03 13:22:12 [INFO] tare_wb.services.oci: API_DEBUG: waiting 10.0s after boom-close
2026-09-03 13:22:17 [INFO] gmdc_common.hardware.sensor: Exit sensor TRUE (occupied) addr=2
2026-09-03 13:22:19 [INFO] gmdc_common.hardware.sensor: Exit sensor FALSE (cleared) addr=2 - falling edge
2026-09-03 13:22:19 [INFO] tare_wb.core.workflow: EXIT sensor cleared - vehicle crossed - resetting to IDLE
2026-09-03 13:22:19 [INFO] tare_wb.core.workflow: Force reset to IDLE
2026-09-03 13:22:19 [INFO] tare_wb.core.workflow: Notifying GMDC reset device_ip=10.10.180.12 rfid=00000000000000000015c01b has_details=True manual=False
2026-09-03 13:22:19 [INFO] tare_wb.services.oci: 
--------------------------------------------------
URL: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint
Payload: {
  "device_ip": "10.10.180.12",
  "rfid_no": "00000000000000000015c01b",
  "truck_details": "V|00000000000000000015c01b|OD14AE3900|45000|26000|50|9580109261|10.10.180.12"
}
Response: {
  "status": 409,
  "response_type": 0,
  "message": "Reset is not allowed because Boom Close is already completed for the current checkpoint.",
  "device_ip": "10.10.180.12",
  "rfid_no": "00000000000000000015c01b",
  "truck_details": "V|00000000000000000015c01b|OD14AE3900|45000|26000|50|9580109261|10.10.180.12",
  "token": "9580109261",
  "location_id": 163,
  "location_name": "Vadhgath Weighbridge",
  "reset_count": {
    "entry_log": 0,
    "checkpoint": 0,
    "movement": 0,
    "weighment": 0
  }
}

Please dont call the reset, if boom close API was success. Reset will only be called if the button is pressed, and from rfid validation - boom close wihtin this flow the reset was done

---

**Cursor**

GMDC is rejecting reset after a successful boom-close. I’ll find every reset call in the TareWb flow and keep it only for the reset button and for aborts before boom-close succeeds.

Boom-close returned 200, then the 10s debug wait left `_gmdc_needs_reset` set, so the exit sensor posted reset and GMDC returned 409. I’ll clear that flag as soon as boom-close is sent, and only call reset on the button or an abort before boom-close succeeds.

GMDC returned 409 because **reset ran after a successful boom-close**. The 10s post-call wait let the exit sensor fire first, while the app still thought the cycle was incomplete.

**Reset is now only sent when:**
- The operator presses Reset, or
- RFID was validated and boom-close never succeeded (ANPR fail, abort, etc.)

**Reset is not sent when:**
- Boom-close returned 200, including if the truck clears the exit sensor during that wait
- Exit timeout after a successful boom-close

Restart TareWb so this takes effect. A completed Vadhghat boom-close should go to IDLE without calling `reset_checkpoint`.

---

**User**

RFID was validated and boom-close never succeeded (ANPR fail, abort, etc.)
Remove tgus. only when reset is pressed from UI then reset api will be called

---

**Cursor**

Reset will only POST when the operator presses Reset in the UI. I’ll remove the abort-path calls after RFID validation.

`reset_checkpoint` now runs **only when Reset is pressed in the UI**.

It is no longer called for ANPR failure, abort, lane exit, exit timeout, free pass, or app startup. Those still return the lane to IDLE locally; they just do not tell GMDC to reset.

Restart TareWb so this takes effect.

---

**User**

Now lets work on voice
/Users/csmtech/Desktop/new-IoT/TareWb-App/voice/error/weighbridge_0.wav This will run when in IDLE condition, the sensor 2 and 3 is cut

---

**Cursor**

I’ll map how IDLE and sensors 2/3 work in TareWb, then play `voice/error/weighbridge_0.wav` when those two are cut while idle.

When IDLE and both the platform sensor (s2) and exit sensor (s3) are occupied, I’ll play `weighbridge_0.wav` and keep repeating until that condition clears.

When the weighbridge is **IDLE** and **sensor 2 (platform)** and **sensor 3 (exit)** are both cut, it now plays `voice/error/weighbridge_0.wav`.

The clip repeats every 5 seconds until one of those sensors clears, Reset is pressed, or a normal entry starts. In bidirectional mode this also blocks treating the exit cut as ENTRY_B, because the truck is already on the platform.

Restart TareWb so the new voice mapping is loaded.

---

**User**

/Users/csmtech/Desktop/new-IoT/TareWb-App/voice/error/number-plate-error.wav
This will play when the anpr API (http://localhost:5001/api/detect) response "anpr_status": 0 or 2.

---

**Cursor**

ANPR status 0 and 2 currently play the generic technical-issue clip. I’ll switch those to `number-plate-error.wav`, and keep the technical clip only when the ANPR API itself fails.

When `/api/detect` returns **`anpr_status` 0 or 2**, TareWb now plays `voice/error/number-plate-error.wav`.

If the ANPR service is down or returns a server error, it still uses the technical-issue clip, not the number-plate file.

Restart TareWb so the new mapping is loaded.

---

**User**

/Users/csmtech/Desktop/new-IoT/TareWb-App/voice/information/application_reset.wav
Impklement when reset is fired from UI button

---

**Cursor**

UI Reset already maps to `application_reset.wav`, but other clips can stop or defer it. I’ll make that clip play whenever Reset is pressed, and add a test for it.

Pressing **Reset** in the TareWb UI now plays `voice/information/application_reset.wav`.

That path was already wired (`announce_reset=True` from the button). It now always plays that clip, even if another announcement was running, and it does not play on automatic idle resets.

Restart TareWb, then confirm Reset from the dashboard.

---

**User**

/Users/csmtech/Desktop/new-IoT/TareWb-App/voice/information/backward.wav
Play this when in WB vehicle positioning is going on and sensor 3 gets cut. according to rule only asensor 2 should be cut for a valid weight positioning

---

**Cursor**

During vehicle positioning, only the platform sensor (s2) should be cut. I’ll play `backward.wav` if the exit sensor (s3) is cut, and keep weight capture from starting in that case.

I’ll play `backward.wav` if the exit sensor (s3) is cut during positioning, and only start weighing when the platform sensor (s2) is cut and s3 is clear.

I’ll check that UI Reset still plays `application_reset.wav`, and fix it if that path is missing or getting interrupted.

UI Reset already plays that clip, but the dashboard currently sends reset twice (MQTT and HTTP), which can cut the audio off. I’ll make the button fire reset once and stop other voice loops first.

The UI **Reset** button now plays `voice/information/application_reset.wav`.

Flow:

1. Operator confirms Reset on the dashboard  
2. Browser posts to `/api/reset` (once — it no longer also publishes MQTT, which was cutting the clip off)  
3. `force_reset(announce_reset=True)` plays `application_reset.wav`

Restart TareWb-App and refresh the dashboard so the updated JS is loaded. Then press Reset — you should hear the clip once.

---

**User**

/Users/csmtech/Desktop/new-IoT/TareWb-App/voice/information/filled_final_weight.wav with weight from weight_kg, weight_ton. The file name is created according to weight so plan accordingly
This will be played when URL: https://gmuatociexp.gmdcltd.co.in/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-weight-details and for tare and vadhghar status is 200

---

**Cursor**

I'll look at how weight voice files are named and where the weight-details API succeeds, then wire `filled_final_weight.wav` plus the matching kg/ton clips.

`speak_weight` already exists; I'll check when it runs versus the weight-details 200 response, and how tare vs gross vs Vadhghat choose the intro clip.

I'll play the final-weight sequence only after weight-details returns 200, using `filled_final_weight.wav` (or tare intro) plus the matching `weight_ton/{n}.wav` and `weight_kg/{n0}.wav` clips.

Final weight is announced only after **weight-details returns 200** (gross, tare, and Vadhghat). It no longer plays before that API call.

**Sequence** (example 12 500 kg):

1. `information/filled_final_weight.wav` — gross and Vadhghat  
   `information/tare_final_weight.wav` — tare  
2. `weight_ton/Siren.wav`  
3. `weight_ton/{tons}.wav` → `12.wav`  
4. `weight_kg/{kg}.wav` → `500.wav` (10 kg steps; skipped if remainder is 0)

It does **not** play if details fail, Vadhghat goes to weight-adjustment, or tare confirm is rejected.

Restart TareWb-App so the change is live.

---

**User**

Lets add one more thing. In Device Status, when I/O Controller gets disconnected, set all sensors, TL and Boom Barrier as Disconencted, as they are dependent on I/O Controller

---

**Cursor**

I'll find how Device Status is built and shown, then mark sensors, traffic lights, and boom barriers disconnected whenever the I/O controller is down.

I'll mark sensors, traffic lights, and boom barriers disconnected whenever the I/O controller is down, in the status payload and on the Device Status panel.

When the I/O controller drops, Device Status now treats everything wired through it as disconnected.

**Shows Disconnected**
- Sensors (S1–S3 on weighbridge; S1 on Mine-entry / Tracking Point)
- Traffic lights
- Boom barriers

**Unchanged**
- RFID reader
- Digitizer (weighbridge only)

Stale “Active / Green / Open” values are cleared so a dead Modbus link cannot look like live hardware. RFID and digitizer keep their own status.

This is on TareWb, Mine-entry, and Tracking Point. Restart the app and refresh the dashboard so the new JS loads. I could not click through the live panel here; after refresh, disconnect I/O and confirm those badges flip to Disconnected.

---

**User**

For API valiodation in UI, if there is any error, then show the msg in the UI DIV
Ex: In RFID VALIDATION PROCESS, message shows RFID service request failed, but I want to show "Gross RFID cannot be processed because Vadhghat Boom Close is not completed for this vehicle and loading slip." this message comes from API Response Similar for all the API responses messages

---

**Cursor**

I'll find where RFID validation failures become the generic UI message and wire through the API response text instead.

The UI is using generic `operator_message` text instead of the API body. I'll prefer the safe API `message` for HTTP/business errors across all three apps, and surface it in the validation step.

API error text from the response body is now shown in the Transaction Flow step DIV.

**Before:** generic copy like `RFID service request failed`  
**After:** the API `message` / `statusMessage`, e.g.  
`Gross RFID cannot be processed because Vadhghat Boom Close is not completed for this vehicle and loading slip.`

Applies to RFID, ANPR, boom-close, weight-details, status-check, and the other OCI calls — same path for TareWb, Mine-entry, and Tracking Point.

**Still generic only when:**
- the service is unreachable / connection error (no safe body text)
- the body has no usable message

Raw exception dumps are still never shown in the UI.

Restart the app after deploy so the change is live.

---

**User**

Also this error show in bold and red color font and increase the size of all fonts

---

**Cursor**

I'll update the Transaction Flow step styles so errors render bold and red, and bump overall font sizes.

I'll make error step text bold and red, and bump dashboard font sizes across all three apps.

Updated across TareWb, Mine-entry, and Tracking Point:

- **Error step messages** — bold, red (`#de350b`), larger (20px)
- **Overall fonts** — base UI raised from 14px → 16px; step content, panel titles, device labels, and sensors also bumped

Hard-refresh the dashboard (Ctrl/Cmd+Shift+R) so the new CSS loads.

---

**User**

VEHICLE WEIGHBRIDGE ALIGNMENT PROCESS
Vehicle approaching weighbridge — move forward.
READING WEIGHT PROCESS
Vehicle on platform — capturing weight.
RFID READ PROCESS
Reading RFID at platform; present a valid tag.
RFID VALIDATION PROCESS
Gross RFID cannot be processed because Vadhghat Boom Close is not completed for this vehicle and loading slip.

Then according to rule car exits. then all thje divs from RFID Validation Process should have red div, but it goes green. 

---

**Cursor**

I'll trace the RFID-validation failure → exit path and fix the step DIVs so they stay red instead of flipping green.

Exit after RFID failure was publishing success, which greened every earlier step. I'll keep the failure cascade red from the failed step onward.

I'll only paint later steps red when exit starts, so RFID validation stays the sole red step until then.

The exit step was published as **success**, and that greened every earlier step — including the failed RFID validation.

**Fixed behavior**
1. RFID validation fails → that step stays **red** with the API message  
2. After the timeout, exit is granted as **error** (“Exit after failure — clear the lane.”)  
3. All steps from **RFID Validation** onward stay/turn **red** (ANPR, weight, exit)  
4. Earlier steps (alignment, weight, RFID read) stay **green**  
5. Idle/reset clears the cascade

Hard-refresh the dashboard after restart so the updated JS loads.

---

**User**

the above change, have you implementd in all application, or only TareWb-App? If yes then all good, if not then update the code according to their flow

---

**Cursor**

Checking Mine-entry and Tracking Point flows now — the red failure cascade was only done in TareWb; I'll align the others if their exit/reset paths need it.

It was only in TareWb. Mine-entry and Tracking Point reset to idle after failures (no exit-grant), but later steps can still overwrite a red step as green — I'll port the failure-cascade UI to match their flow.

It was **only in TareWb** before. It’s now in **all three**, adapted to each flow:

| App | Failure behavior |
|-----|------------------|
| **TareWb** | Fail → hold → **exit granted** (lane clear). From failed step onward stays **red**; earlier steps stay green. |
| **Mine-entry / Tracking Point** | Fail → hold → **reset IDLE** (no exit-grant). From failed step through the rest of the flow turns **red** during the hold, then clears on idle. |

Also for Mine-entry / Tracking Point:
- RFID error maps to **RFID Validation** (not RFID Read)
- `vehicleStatus=2` shows the API/error message in red before reset
- Later steps (e.g. wait-crossing after boom-close fail) no longer overwrite a red step as green

Restart each app and hard-refresh the dashboards.

---

**User**

Operator Login username and password please add to .env

---

**Cursor**

I'll find where operator login credentials are set and move them into `.env`.

Login already reads `OPERATOR_USERNAME` / `OPERATOR_PASSWORD`; they're commented out in `.env`. I'll enable them in all three apps' `.env` and `.env.example`.

Operator login is now set in `.env` for all three apps:

```env
OPERATOR_USERNAME=admin
OPERATOR_PASSWORD=gmdc@123
```

Added to:
- `TareWb-App/.env` (+ `.env.example`)
- `Mine-entry/.env` (+ `.env.example`)
- `Tracking-point-1/.env` (+ `.env.example`)

Settings already read these for `/api/login`. Restart the app after changing them. `.env` stays gitignored.

---

**User**

2026-09-04 11:03:54 [INFO] gmdc_common.services.rfid_control: RFID cloud start http=200 body=
2026-09-04 11:03:54 [INFO] gmdc_common.services.rfid_control: RFID IDLE prepare complete - reader scanning
2026-09-04 11:03:54 [INFO] tare_wb.core.workflow: RFID cloud start direction=entry_a (login/mode/start) ok=True
2026-09-04 11:03:54 [INFO] tare_wb.core.workflow: RFID_READ - waiting for tags via /rfid_data
2026-09-04 11:03:59 [INFO] werkzeug: 192.168.31.87 - - [04/Sep/2026 11:03:59] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 11:04:52 [INFO] werkzeug: 192.168.31.87 - - [04/Sep/2026 11:04:52] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 11:04:54 [WARNING] tare_wb.core.workflow: RFID collect timeout
2026-09-04 11:04:54 [INFO] tare_wb.core.state_machine: FSM RFID_READ --[RFID_TIMEOUT]--> RFID_ERROR
2026-09-04 11:04:54 [INFO] gmdc_common.services.voice: Voice: RFID not found
2026-09-04 11:04:54 [INFO] gmdc_common.services.rfid_control: RFID cloud stop PUT https://192.168.31.87/cloud/stop (Bearer)
2026-09-04 11:04:55 [INFO] gmdc_common.services.rfid_control: RFID cloud stop http=200 body=
2026-09-04 11:04:55 [INFO] tare_wb.core.workflow: RFID cloud stop direction=entry_a ok=True
When this case arises in WB, then show in UI "No RFID read within the time period" instead of "RFID Validation error". Also when RFID read starts, show the countdown timer. And in .env of every application put all the timers so that it can be configured later. 

---

**Cursor**

I'll find the RFID timeout path, wire the new UI message and countdown, and expose the timers in each app's `.env`.

Implementing the timeout message and countdown for TareWb, and wiring all timers from `.env` across the three apps.

Updating workflow, MQTT, frontend, and env-based timeout loading across all apps.

Done. Here’s what changed for the RFID collect-timeout case on Tare WB:

**UI (TareWb)**
- Timeout now shows **“No RFID read within the time period”** on the RFID Read step (not “RFID validation failed”).
- When RFID read starts, the step shows a live countdown, e.g. `Reading RFID at platform; present a valid tag. (60s)`.

**Timers in `.env`**
- All workflow timers are listed in `.env` / `.env.example` for **TareWb-App**, **Mine-entry**, and **Tracking-point-1**.
- They load via `apply_timeouts_from_env()` on startup.
- WB RFID wait is `RFID_COLLECT_TIMEOUT_SEC` (default **60**).

Restart the weighbridge app and hard-refresh the dashboard to pick this up. To change the wait window, set `RFID_COLLECT_TIMEOUT_SEC` in `TareWb-App/.env`.

---

**User**

2026-09-04 11:28:11 [INFO] tare_wb.services.digitizer: Digitizer POST http://localhost:8001/read_stable_weight
2026-09-04 11:28:11 [WARNING] tare_wb.core.workflow: Final weight out of tolerance type=T: Weight 44970 kg outside RTO tare band 25500–26500 kg.
2026-09-04 11:28:11 [INFO] gmdc_common.services.display: DISPLAY: TARE WT ERR
2026-09-04 11:28:11 [INFO] tare_wb.core.workflow: Announce: TARE WT ERR
2026-09-04 11:28:11 [INFO] gmdc_common.services.voice: Voice: Tare Weight Error T7
2026-09-04 11:28:11 [INFO] tare_wb.core.workflow: weight-confirm type=o weight=44970 truck_details='T|00000000000000000015c021|OD14AF2721|45000|26000|500|9580309262|10.10.180.1|F3300'

During this case, when weight isn't within tolerance, Here announcement I want g2.wav for gross and Vadhghat and t1.wav for tare

---

**Cursor**

I'll find where the out-of-tolerance weight voice is chosen and switch it to `t1.wav` for tare and `g2.wav` for gross/Vadhghat.

Updated. Out-of-tolerance weight now plays:

- **Tare (T):** `t1.wav` (was `t7.wav`)
- **Gross / Vadhghat (G/V):** `g2.wav`

Restart the weighbridge app so the voice change is picked up.

---

**User**

@Untitled-1 (26-47) When this API response api_status is 0 or 2, then immediately play rfid_502.wav

For the logs, implem ent rotate time, so that day wise log will be stored and only last 10 days log will be stored

---

**Cursor**

I'll handle both: play `rfid_502.wav` immediately on ANPR status 0/2, and set up day-wise log rotation keeping the last 10 days.

Moving the ANPR voice to fire right after status 0/2, and switching shared logging to midnight rotation with a 10-day retention.

Mine-entry/Tracking don't wire voice, so I'll keep the ANPR clip change on TareWb only and finish log rotation there.

Done on both items:

**ANPR voice (TareWb)**  
When `/api/detect` returns `anpr_status` **0 or 2**, `rfid_502.wav` plays immediately after the response — before top photo / invalid-truck.

**Log rotation (all 3 apps via `gmdc_common`)**  
Logs now rotate at **midnight**, with dated backups like `tare_wb.log.2026-09-03`, and only the **last 10 days** are kept.

Restart the apps to pick this up.

---

**User**

@Untitled-1 (19-21) 

---

**Cursor**

I'll update the ANPR status UI messages to the Err-0 / Err-2 wording you specified.

Updated ANPR Validation Process UI text in all three apps:

- **Status 0:** `ANPR Err-0, Number plate mismatch`
- **Status 2:** `ANPR Err-2, Number not readable`

---

**User**

@Untitled-1 (1-35) 

---

**Cursor**

I'll redesign the operator UIs to

 an icon-based progress strip, with full step details behind a Flow Details modal. Exploring the current dashboards first.

Implementing the icon strip and Flow Details modal across all three dashboards, keeping existing step DOM for MQTT/tests.

Operator dashboards now use an icon-first flow view.

**All apps**
- Step cards are hidden by default; open them with **Flow Details** (large modal + ×).
- RFID / truck / weight info box stays as-is on WB.

**Weighbridge**
- Icon strip: **RFID → ANPR → WEIGHT** with corner badge: loading / tick / cross.

**Mine-entry & Tracking**
- Icons: **RFID Read → RFID Validation → ANPR Read → ANPR Update → Vehicle Exit → Truck Exited**
- ANPR Update is skipped when ANPR matches (`anpr_status=1`); otherwise it goes loading after Err-0/Err-2.
- After **Truck Exited** succeeds, UI resets after **2 seconds**.

Hard-refresh the dashboards (Ctrl/Cmd+Shift+R) after restarting the apps.

---

**User**

RFID INFORMATION
RFID: e200001d7507013115006bb9
Truck Number: --
Currenly this is shown openly after RFID is read. But show this everytime with -- values

---

**Cursor**

I'll make the RFID info box always visible with `--` defaults instead of only showing after a read.

The RFID info panel is now always visible on all three dashboards, with `--` for empty fields. Values fill in when a tag/truck/weight arrives, and reset to `--` on idle. Hard-refresh the page to see it.

---

**User**

pip3 install -r requirements.txt 
Collecting flask==3.0.0 (from -r requirements.txt (line 1))
  Obtaining dependency information for flask==3.0.0 from https://files.pythonhosted.org/packages/36/42/015c23096649b908c809c69388a805a571a3bea44362fe87e33fc3afa01f/flask-3.0.0-py3-none-any.whl.metadata
  Using cached flask-3.0.0-py3-none-any.whl.metadata (3.6 kB)
Collecting flask-cors==4.0.0 (from -r requirements.txt (line 2))
  Obtaining dependency information for flask-cors==4.0.0 from https://files.pythonhosted.org/packages/10/69/1e6cfb87117568a9de088c32d6258219e9d1ff7c131abf74249ef2031279/Flask_Cors-4.0.0-py2.py3-none-any.whl.metadata
  Using cached Flask_Cors-4.0.0-py2.py3-none-any.whl.metadata (5.4 kB)
Collecting numpy==1.24.3 (from -r requirements.txt (line 3))
  Using cached numpy-1.24.3.tar.gz (10.9 MB)
  Installing build dependencies ... done
  Getting requirements to build wheel ... done
ERROR: Exception:
Traceback (most recent call last):
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/cli/base_command.py", line 180, in exc_logging_wrapper
    status = run_func(*args)
             ^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/cli/req_command.py", line 248, in wrapper
    return func(self, options, args)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/commands/install.py", line 377, in run
    requirement_set = resolver.resolve(
                      ^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/resolver.py", line 92, in resolve
    result = self._result = resolver.resolve(
                            ^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/resolvelib/resolvers.py", line 546, in resolve
    state = resolution.resolve(requirements, max_rounds=max_rounds)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/resolvelib/resolvers.py", line 397, in resolve
    self._add_to_criteria(self.state.criteria, r, parent=None)
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/resolvelib/resolvers.py", line 173, in _add_to_criteria
    if not criterion.candidates:
           ^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/resolvelib/structs.py", line 156, in __bool__
    return bool(self._sequence)
           ^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py", line 155, in __bool__
    return any(self)
           ^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py", line 143, in <genexpr>
    return (c for c in iterator if id(c) not in self._incompatible_ids)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py", line 47, in _iter_built
    candidate = func()
                ^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/factory.py", line 206, in _make_candidate_from_link
    self._link_candidate_cache[link] = LinkCandidate(
                                       ^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 293, in __init__
    super().__init__(
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 156, in __init__
    self.dist = self._prepare()
                ^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 225, in _prepare
    dist = self._prepare_distribution()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/resolution/resolvelib/candidates.py", line 304, in _prepare_distribution
    return preparer.prepare_linked_requirement(self._ireq, parallel_builds=True)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/operations/prepare.py", line 538, in prepare_linked_requirement
    return self._prepare_linked_requirement(req, parallel_builds)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/operations/prepare.py", line 653, in _prepare_linked_requirement
    dist = _get_prepared_distribution(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/operations/prepare.py", line 69, in _get_prepared_distribution
    abstract_dist.prepare_distribution_metadata(
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/distributions/sdist.py", line 48, in prepare_distribution_metadata
    self._install_build_reqs(finder)
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/distributions/sdist.py", line 118, in _install_build_reqs
    build_reqs = self._get_build_requires_wheel()
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/distributions/sdist.py", line 95, in _get_build_requires_wheel
    return backend.get_requires_for_build_wheel()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_internal/utils/misc.py", line 697, in get_requires_for_build_wheel
    return super().get_requires_for_build_wheel(config_settings=cs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/pyproject_hooks/_impl.py", line 166, in get_requires_for_build_wheel
    return self._call_hook('get_requires_for_build_wheel', {
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/pyproject_hooks/_impl.py", line 321, in _call_hook
    raise BackendUnavailable(data.get('traceback', ''))
pip._vendor.pyproject_hooks._impl.BackendUnavailable: Traceback (most recent call last):
  File "/Users/csmtech/Desktop/new-IoT/checkpoint-config/venv/lib/python3.12/site-packages/pip/_vendor/pyproject_hooks/_in_process/_in_process.py", line 77, in _build_backend
    obj = import_module(mod_path)
          ^^^^^^^^^^^^^^^^^^^^^^^
  File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/importlib/__init__.py", line 90, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1381, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1354, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1304, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "<frozen importlib._bootstrap>", line 1381, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1354, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1325, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 929, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 994, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/private/var/folders/g6/6fv0j8zx6wqd0d2901l5pp1c0000gn/T/pip-build-env-bzr2aenp/overlay/lib/python3.12/site-packages/setuptools/__init__.py", line 10, in <module>
    import distutils.core
ModuleNotFoundError: No module named 'distutils'


[notice] A new release of pip is available: 23.2.1 -> 26.2.1
[notice] To update, run: pip install --upgrade pip Resolve this in checkpoint-config

---

**Cursor**

`numpy==1.24.3` doesn't support Python 3.12 (no wheels; build fails without `distutils`). I'll update `checkpoint-config` requirements for 3.12.

Fixed. On Python 3.12, `numpy==1.24.3` has no wheels and fails to build because `distutils` was removed.

Updated `checkpoint-config/requirements.txt`:
- `numpy` → `1.26.4`
- `opencv-python` → `4.10.0.84`
- `PyInstaller` → `6.11.1`

`pip install -r requirements.txt` completed successfully in your venv.

---

**User**

<timestamp>Friday, Sep 4, 2026, 4:29 PM (UTC+5:30)</timestamp>
<system_notification>
The following task has finished. If you were already aware, ignore this notification and do not restate prior responses.

<task>
kind: shell
status: success
task_id: 424978
title: Upgrade pip and install updated requirements
tool_call_id: call-2bc571e0-0448-4c08-9b90-ce1598c6335c-227
fc_add4e683-70e0-9e33-9f9f-704dc5a081d3_1
output_path: /Users/csmtech/.cursor/projects/Users-csmtech-Desktop-new-IoT/terminals/424978.txt
</task>
</system_notification>
<user_query>Briefly inform the user about the task result and perform any follow-up actions (if needed). If there's no follow-ups needed, don't explicitly say that.</user_query>

---

**Cursor**

`pip install -r requirements.txt` finished successfully in `checkpoint-config` — Python 3.12–compatible `numpy`, `opencv-python`, and `PyInstaller` are installed.

---

**User**

(venv) csmtech@CSM checkpoint-config % python3 app.py
2026-09-04 16:30:14 - __main__ - INFO - ==================================================
2026-09-04 16:30:14 - __main__ - INFO - GMDC Checkpoint Config v0.1.0 - Starting
2026-09-04 16:30:14 - __main__ - INFO - Mode: DEBUG
2026-09-04 16:30:14 - __main__ - INFO - Camera configuration UI: enabled
2026-09-04 16:30:14 - __main__ - INFO - Log file: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log
2026-09-04 16:30:14 - __main__ - INFO - ==================================================
*** Terminating app due to uncaught exception 'NSInternalInconsistencyException', reason: 'NSWindow should only be instantiated on the main thread!'
*** First throw call stack:
(
	0   CoreFoundation                      0x00000001823171f0 __exceptionPreprocess + 176
	1   libobjc.A.dylib                     0x0000000181d9291c objc_exception_throw + 88
	2   CoreFoundation                      0x000000018233abc8 _CFBundleGetValueForInfoKey + 0
	3   AppKit                              0x00000001866ef2c4 -[NSWindow _initContent:styleMask:backing:defer:contentView:] + 260
	4   AppKit                              0x00000001866ef1b4 -[NSWindow initWithContentRect:styleMask:backing:defer:] + 48
	5   libtk8.6.dylib                      0x000000012540dd48 TkMacOSXMakeRealWindowExist + 572
	6   libtk8.6.dylib                      0x000000012540d998 TkWmMapWindow + 60
	7   libtk8.6.dylib                      0x0000000125365410 Tk_MapWindow + 148
	8   libtk8.6.dylib                      0x000000012536de68 MapFrame + 76
	9   libtcl8.6.dylib                     0x0000000125297178 TclServiceIdle + 72
	10  libtcl8.6.dylib                     0x0000000125278514 Tcl_DoOneEvent + 120
	11  libtk8.6.dylib                      0x00000001253ff360 TkpInit + 800
	12  libtk8.6.dylib                      0x00000001253668fc Initialize + 2356
	13  _tkinter.cpython-312-darwin.so      0x0000000107d8e390 Tcl_AppInit + 92
	14  _tkinter.cpython-312-darwin.so      0x0000000107d89404 Tkapp_New + 548
	15  _tkinter.cpython-312-darwin.so      0x0000000107d891dc _tkinter_create_impl + 268
	16  _tkinter.cpython-312-darwin.so      0x0000000107d88cb4 _tkinter_create + 236
	17  Python                              0x0000000105563774 cfunction_vectorcall_FASTCALL + 96
	18  Python                              0x000000010566628c _PyEval_EvalFrameDefault + 47356
	19  Python                              0x00000001054f4c50 _PyObject_FastCallDictTstate + 96
	20  Python                              0x0000000105591d3c slot_tp_init + 208
	21  Python                              0x0000000105587008 type_call + 148
	22  Python                              0x00000001054f4ecc _PyObject_MakeTpCall + 128
	23  Python                              0x00000001056663f0 _PyEval_EvalFrameDefault + 47712
	24  Python                              0x00000001054f8fdc method_vectorcall + 368
	25  Python                              0x000000010577da84 thread_run + 92
	26  Python                              0x00000001056ef8fc pythread_wrapper + 48
	27  libsystem_pthread.dylib             0x00000001821ebc58 _pthread_start + 136
	28  libsystem_pthread.dylib             0x00000001821e6c1c thread_start + 8
)
libc++abi: terminating due to uncaught exception of type NSException
zsh: abort      python3 app.py

---

**Cursor**

The crash is from creating a Tk/NSWindow off the main thread on macOS. I'll find where that window is opened and move it onto the main thread.

Splash creates a Tk window on a background thread; macOS forbids that. Skipping the Tk splash on Darwin.

The crash came from the startup splash creating a Tk window on a **background thread** — macOS requires `NSWindow` on the main thread.

On macOS, the Tk splash and Mosquitto progress UI are now skipped. Run again:

```bash
python3 app.py
```

---

**User**

(venv) csmtech@CSM checkpoint-config % python3 app.py
2026-09-04 16:33:49 - __main__ - INFO - ==================================================
2026-09-04 16:33:49 - __main__ - INFO - GMDC Checkpoint Config v0.1.0 - Starting
2026-09-04 16:33:49 - __main__ - INFO - Mode: DEBUG
2026-09-04 16:33:49 - __main__ - INFO - Camera configuration UI: enabled
2026-09-04 16:33:49 - __main__ - INFO - Log file: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log
2026-09-04 16:33:49 - __main__ - INFO - ==================================================
2026-09-04 16:33:49 - iot_config.splash - INFO - Skipping Tk splash on macOS (NSWindow must be created on the main thread)
2026-09-04 16:33:49 - __main__ - INFO - Closing splash screen...
2026-09-04 16:33:49 - __main__ - INFO - Importing Mosquitto manager...
2026-09-04 16:33:49 - __main__ - INFO - Checking Mosquitto MQTT broker...
2026-09-04 16:33:49 - __main__ - INFO - Calling ensure_mosquitto_ready()...
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - ensure_mosquitto_ready() called
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - App data path: /Users/csmtech/Desktop/new-IoT/checkpoint-config
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - Creating Mosquitto progress window...
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - Skipping Mosquitto progress UI on macOS (Tk main-thread restriction)
2026-09-04 16:33:49 - mosquitto_setup - INFO - ============================================================
2026-09-04 16:33:49 - mosquitto_setup - INFO - Starting Mosquitto Broker Setup
2026-09-04 16:33:49 - mosquitto_setup - INFO - ============================================================
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - [0%] Checking Mosquitto installation...
2026-09-04 16:33:49 - mosquitto_setup - INFO - Mosquitto not found on system
2026-09-04 16:33:49 - mosquitto_setup - INFO - Mosquitto not found. Proceeding with installation...
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - [0%] Downloading Mosquitto installer...
2026-09-04 16:33:49 - mosquitto_setup - INFO - Downloading Mosquitto 2.0.18 installer...
2026-09-04 16:33:49 - mosquitto_setup - INFO - URL: https://mosquitto.org/files/binary/win64/mosquitto-2.0.18-install-windows-x64.exe
2026-09-04 16:33:49 - utils.mosquitto_manager - INFO - [0%] Starting download...
2026-09-04 16:33:50 - mosquitto_setup - ERROR - Error downloading Mosquitto installer: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)>
2026-09-04 16:33:50 - mosquitto_setup - ERROR - Failed to download Mosquitto installer
2026-09-04 16:33:50 - __main__ - INFO - Mosquitto setup completed: success=False, message=Failed to download Mosquitto installer
2026-09-04 16:33:50 - __main__ - ERROR - Mosquitto setup failed: Failed to download Mosquitto installer
2026-09-04 16:33:50 - __main__ - ERROR - 
================================================================================
2026-09-04 16:33:50 - __main__ - ERROR - MOSQUITTO SETUP FAILED
2026-09-04 16:33:50 - __main__ - ERROR - ================================================================================
2026-09-04 16:33:50 - __main__ - ERROR - Error: Failed to download Mosquitto installer
2026-09-04 16:33:50 - __main__ - ERROR - The application cannot start without Mosquitto broker.
2026-09-04 16:33:50 - __main__ - ERROR - Please install Mosquitto manually or run as administrator.
2026-09-04 16:33:50 - __main__ - ERROR - ================================================================================
2026-09-04 16:33:50 - iot_config.fatal - CRITICAL - Mosquitto MQTT broker is required but setup failed.

Failed to download Mosquitto installer

Install Mosquitto or run the application as administrator.
See log: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log
GMDC Checkpoint Config
Mosquitto MQTT broker is required but setup failed.

Failed to download Mosquitto installer

Install Mosquitto or run the application as administrator.
See log: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log

Press Enter to exit...

Implement mqtt installation for macos with proper scripting

---

**Cursor**

I'll inspect the current Mosquitto setup and add a proper macOS install path (Homebrew/binary), instead of the Windows installer.

Implementing Homebrew-based Mosquitto install/start/config for macOS, and branching the setup flow by platform.

Preferring an app-local Mosquitto config on macOS so websockets settings apply when we start the broker.

macOS Mosquitto setup is implemented in `checkpoint-config/mosquitto_setup.py`.

On Darwin it now:
1. Detects Homebrew (`/opt/homebrew` or `/usr/local`)
2. Runs `brew install mosquitto` (no Windows `.exe` download)
3. Writes an app-local config with MQTT `1883` + websockets `9001`
4. Starts Mosquitto as a daemon (falls back to `brew services start`)

Run again:

```bash
python3 app.py
```

First run may take a few minutes while Homebrew installs Mosquitto. If Homebrew isn’t available, install it from https://brew.sh first.

---

**User**

(venv) csmtech@CSM checkpoint-config % python3 app.py
2026-09-04 16:40:27 - __main__ - INFO - ==================================================
2026-09-04 16:40:27 - __main__ - INFO - GMDC Checkpoint Config v0.1.0 - Starting
2026-09-04 16:40:27 - __main__ - INFO - Mode: DEBUG
2026-09-04 16:40:27 - __main__ - INFO - Camera configuration UI: enabled
2026-09-04 16:40:27 - __main__ - INFO - Log file: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log
2026-09-04 16:40:27 - __main__ - INFO - ==================================================
2026-09-04 16:40:27 - iot_config.splash - INFO - Skipping Tk splash on macOS (NSWindow must be created on the main thread)
2026-09-04 16:40:27 - __main__ - INFO - Closing splash screen...
2026-09-04 16:40:28 - __main__ - INFO - Importing Mosquitto manager...
2026-09-04 16:40:28 - __main__ - INFO - Checking Mosquitto MQTT broker...
2026-09-04 16:40:28 - __main__ - INFO - Calling ensure_mosquitto_ready()...
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - ensure_mosquitto_ready() called
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - App data path: /Users/csmtech/Desktop/new-IoT/checkpoint-config
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - Creating Mosquitto progress window...
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - Skipping Mosquitto progress UI on macOS (Tk main-thread restriction)
2026-09-04 16:40:28 - mosquitto_setup - INFO - ============================================================
2026-09-04 16:40:28 - mosquitto_setup - INFO - Starting Mosquitto Broker Setup
2026-09-04 16:40:28 - mosquitto_setup - INFO - ============================================================
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - [0%] Checking Mosquitto installation...
2026-09-04 16:40:28 - mosquitto_setup - INFO - Mosquitto not found on system
2026-09-04 16:40:28 - mosquitto_setup - INFO - Mosquitto not found. Installing via Homebrew...
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - [5%] Installing Mosquitto via Homebrew...
2026-09-04 16:40:28 - mosquitto_setup - INFO - Using Homebrew at: /opt/homebrew/bin/brew
2026-09-04 16:40:28 - utils.mosquitto_manager - INFO - [10%] Checking Homebrew Mosquitto formula...
2026-09-04 16:40:30 - utils.mosquitto_manager - INFO - [20%] Installing Mosquitto with Homebrew (may take a few minutes)...
2026-09-04 16:40:30 - mosquitto_setup - INFO - Running: brew install mosquitto
2026-09-04 16:40:45 - mosquitto_setup - INFO - brew install stdout:
==> Would install 1 formula:
mosquitto
==> Would install 4 dependencies for mosquitto:
cjson
libevent
libuv
libwebsockets
==> Would upgrade 2 dependencies for mosquitto:
ca-certificates
openssl@3
==> Installing dependencies for mosquitto: cjson, libevent, libuv and libwebsockets
==> Installing mosquitto dependency: cjson
==> Pouring cjson--1.7.19.arm64_tahoe.bottle.tar.gz
🍺  /opt/homebrew/Cellar/cjson/1.7.19: 24 files, 244.4KB
==> Installing mosquitto dependency: libevent
==> Pouring libevent--2.1.13.arm64_tahoe.bottle.tar.gz
🍺  /opt/homebrew/Cellar/libevent/2.1.13: 58 files, 2.3MB
==> Installing mosquitto dependency: libuv
==> Pouring libuv--1.52.1.arm64_tahoe.bottle.tar.gz
🍺  /opt/homebrew/Cellar/libuv/1.52.1: 35 files, 1.3MB
==> Installing mosquitto dependency: libwebsockets
==> Pouring libwebsockets--5.0.0.arm64_tahoe.bottle.tar.gz
🍺  /opt/homebrew/Cellar/libwebsockets/5.0.0: 139 files, 2.9MB
==> Installing mosquitto
==> Pouring mosquitto--2.1.2_1.arm64_tahoe.bottle.tar.gz
🍺  /opt/homebrew/Cellar/mosquitto/2.1.2_1: 87 files, 2.6MB
==> Caveats
==> mosquitto
mosquitto has been installed with a default configuration file.
You can make changes to the configuration by editing:
    /opt/homebrew/etc/mosquitto/mosquitto.conf

To start mosquitto now and restart at login:
  brew services start mosquitto
Or, if you don't want/need a background service you can just run:
  /opt/homebrew/opt/mosquitto/sbin/mosquitto -c /opt/homebrew/etc/mosquitto/mosquitto.conf

2026-09-04 16:40:45 - mosquitto_setup - INFO - brew install stderr:
==> Auto-updating Homebrew...
Adjust how often this is run with `$HOMEBREW_AUTO_UPDATE_SECS` or disable with
`$HOMEBREW_NO_AUTO_UPDATE=1`. Hide these hints with `$HOMEBREW_NO_ENV_HINTS=1` (see `man brew`).
==> Downloading bottle manifests
✔︎ Bottle Manifest mosquitto (2.1.2_1)
==> Fetching downloads for: mosquitto
✔︎ Bottle Manifest libevent (2.1.13)
✔︎ Bottle Manifest libuv (1.52.1)
✔︎ Bottle Manifest ca-certificates (2026-08-13)
✔︎ Bottle Manifest openssl@3 (3.6.4)
✔︎ Bottle Manifest cjson (1.7.19)
✔︎ Bottle Manifest libwebsockets (5.0.0)
✔︎ Bottle cjson (1.7.19)
✔︎ Bottle ca-certificates (2026-08-13)
✔︎ Bottle libevent (2.1.13)
✔︎ Bottle libwebsockets (5.0.0)
✔︎ Bottle mosquitto (2.1.2_1)
✔︎ Bottle libuv (1.52.1)
✔︎ Bottle openssl@3 (3.6.4)

2026-09-04 16:40:45 - mosquitto_setup - INFO - Mosquitto not found on system
2026-09-04 16:40:45 - mosquitto_setup - ERROR - brew install finished but mosquitto binary was not found
2026-09-04 16:40:45 - mosquitto_setup - ERROR - brew install finished but mosquitto binary was not found
2026-09-04 16:40:45 - __main__ - INFO - Mosquitto setup completed: success=False, message=brew install finished but mosquitto binary was not found
2026-09-04 16:40:45 - __main__ - ERROR - Mosquitto setup failed: brew install finished but mosquitto binary was not found
2026-09-04 16:40:45 - __main__ - ERROR - 
================================================================================
2026-09-04 16:40:45 - __main__ - ERROR - MOSQUITTO SETUP FAILED
2026-09-04 16:40:45 - __main__ - ERROR - ================================================================================
2026-09-04 16:40:45 - __main__ - ERROR - Error: brew install finished but mosquitto binary was not found
2026-09-04 16:40:45 - __main__ - ERROR - The application cannot start without Mosquitto broker.
2026-09-04 16:40:45 - __main__ - ERROR - Please install Mosquitto manually or run as administrator.
2026-09-04 16:40:45 - __main__ - ERROR - ================================================================================
2026-09-04 16:40:45 - iot_config.fatal - CRITICAL - Mosquitto MQTT broker is required but setup failed.

brew install finished but mosquitto binary was not found

Install Mosquitto or run the application as administrator.
See log: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log
GMDC Checkpoint Config
Mosquitto MQTT broker is required but setup failed.

brew install finished but mosquitto binary was not found

Install Mosquitto or run the application as administrator.
See log: /Users/csmtech/Desktop/new-IoT/checkpoint-config/configuration_logs/IoT-Configuration.log

Press Enter to exit...

Please check and run the application on your own, till no errors comes ourt

---

**Cursor**

Homebrew puts the binary in `sbin`, not `bin`. I'll fix detection, then run the app until it starts cleanly.

---

**User**

Audio Error

Audio System is not connected to this PC. Please connect and retry
But there is mac mini speaker and also aux output is there
Audio Error

Audio System is not connected to this PC. Please connect and retry
2026-09-04 16:55:56 - urllib3.connectionpool - DEBUG - https://api.github.com:443 "GET /repos/omsm/RajMines-Application/releases/latest HTTP/1.1" 200 1025
2026-09-04 16:56:14 - werkzeug - INFO - 192.168.31.87 - - [04/Sep/2026 16:56:14] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 16:56:45 - services.audio_service - DEBUG - [AudioService] Attempting to play test audio at: /Users/csmtech/Desktop/new-IoT/checkpoint-config/static/audio/test_audio.wav
2026-09-04 16:56:45 - services.audio_service - ERROR - [AudioService] Failed to play audio: Windows audio system not available (winsound missing)

---

**Cursor**

The audio service is Windows-only (`winsound`). I'll add macOS playback support so the Mac mini speakers/AUX work.

Audio test on macOS was failing because the service only used Windows `winsound`.

It now uses **`afplay`** on macOS (same as the weighbridge voice stack). Local test playback succeeded.

Restart `python3 app.py` and run the audio test again — you should hear `test_audio.wav` on the Mac mini speakers/AUX.

---

**User**

2026-09-04 16:54:38 - services.network_scanner - INFO - [NetworkScanner] Scan complete. Found 4 devices
2026-09-04 16:54:39 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:39] "GET /api/network/status HTTP/1.1" 200 -
2026-09-04 16:54:39 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:39] "GET /api/network/results HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "POST /api/config/checkpoint-type HTTP/1.1" 200 -
2026-09-04 16:54:49 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:54:49 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /devices HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/css/bootstrap-icons.css HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/css/bootstrap.min.css HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/css/style.css HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/js/digitizer_index_picker.js HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/js/weighbridge-bidirectional.js HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/js/weighbridge-layout.js HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/js/bootstrap.bundle.min.js HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/js/devices.js HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /api/config HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /api/status HTTP/1.1" 200 -
2026-09-04 16:54:49 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:54:49 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /api/rfid/fastag-validation-rules HTTP/1.1" 200 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2 HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/fonts/bootstrap-icons.woff2 HTTP/1.1" 304 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/audio/test_audio.wav HTTP/1.1" 206 -
2026-09-04 16:54:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:54:49] "GET /static/audio/test_audio.wav HTTP/1.1" 206 -
2026-09-04 16:55:02 - utils.browser_launcher - WARNING - Google Chrome not found; cannot launch app mode
2026-09-04 16:55:02 - utils.browser_launcher - INFO - Chrome not available; opening default browser
2026-09-04 16:55:02 - utils.browser_launcher - INFO - Opened URL in default browser: http://127.0.0.1:8080
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:55:02 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:02 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET / HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/css/bootstrap.min.css HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/js/checklist.js HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/js/weighbridge-layout.js HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/js/bootstrap.bundle.min.js HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/css/bootstrap-icons.css HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/css/style.css HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "POST /api/config/reset-all HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2 HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /api/network/ip-range HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /static/fonts/bootstrap-icons.woff2 HTTP/1.1" 200 -
2026-09-04 16:55:02 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:02] "GET /favicon.ico HTTP/1.1" 404 -
2026-09-04 16:55:13 - werkzeug - INFO - 192.168.31.87 - - [04/Sep/2026 16:55:13] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 16:55:14 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:14 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET / HTTP/1.1" 200 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/css/style.css HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/css/bootstrap-icons.css HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/css/bootstrap.min.css HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/js/bootstrap.bundle.min.js HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/js/checklist.js HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/js/weighbridge-layout.js HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "POST /api/config/reset-all HTTP/1.1" 200 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /static/fonts/bootstrap-icons.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:14 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:14] "GET /api/network/ip-range HTTP/1.1" 200 -
2026-09-04 16:55:17 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:17 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET / HTTP/1.1" 200 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/css/bootstrap-icons.css HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/css/style.css HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/js/bootstrap.bundle.min.js HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/css/bootstrap.min.css HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/js/checklist.js HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/js/weighbridge-layout.js HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/fonts/bootstrap-icons.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/css/bootstrap-icons.css HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/js/weighbridge-layout.js HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/css/bootstrap.min.css HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/js/bootstrap.bundle.min.js HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/css/style.css HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/js/checklist.js HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "POST /api/config/reset-all HTTP/1.1" 200 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /static/fonts/bootstrap-icons.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:17 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:17] "GET /api/network/ip-range HTTP/1.1" 200 -
2026-09-04 16:55:18 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:18 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /devices HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/css/bootstrap-icons.css HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/css/bootstrap.min.css HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/css/style.css HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/js/digitizer_index_picker.js HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/js/weighbridge-bidirectional.js HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/js/devices.js HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/js/weighbridge-layout.js HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/js/bootstrap.bundle.min.js HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /api/config HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /api/status HTTP/1.1" 200 -
2026-09-04 16:55:18 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:18 - utils.timeout_config_loader - INFO - [CONFIG] Loaded timeout_config.py from: /Users/csmtech/Desktop/new-IoT/checkpoint-config/timeout_config.py
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /api/rfid/fastag-validation-rules HTTP/1.1" 200 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/fonts/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/fonts/bootstrap-icons.woff2 HTTP/1.1" 304 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/audio/test_audio.wav HTTP/1.1" 206 -
2026-09-04 16:55:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:18] "GET /static/audio/test_audio.wav HTTP/1.1" 206 -
2026-09-04 16:55:26 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:26] "GET /favicon.ico HTTP/1.1" 404 -
2026-09-04 16:55:28 - services.audio_service - DEBUG - [AudioService] Attempting to play test audio at: /Users/csmtech/Desktop/new-IoT/checkpoint-config/static/audio/test_audio.wav
2026-09-04 16:55:28 - services.audio_service - ERROR - [AudioService] Failed to play audio: Windows audio system not available (winsound missing)
2026-09-04 16:55:28 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:28] "POST /api/audio/test HTTP/1.1" 500 -
2026-09-04 16:55:34 - services.audio_service - DEBUG - [AudioService] Attempting to play test audio at: /Users/csmtech/Desktop/new-IoT/checkpoint-config/static/audio/test_audio.wav
2026-09-04 16:55:34 - services.audio_service - ERROR - [AudioService] Failed to play audio: Windows audio system not available (winsound missing)
2026-09-04 16:55:34 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:55:34] "POST /api/audio/test HTTP/1.1" 500 -
2026-09-04 16:55:56 - urllib3.connectionpool - DEBUG - Starting new HTTPS connection (1): api.github.com:443
2026-09-04 16:55:56 - urllib3.connectionpool - DEBUG - https://api.github.com:443 "GET /repos/omsm/RajMines-Application/releases/latest HTTP/1.1" 200 1025
2026-09-04 16:56:14 - werkzeug - INFO - 192.168.31.87 - - [04/Sep/2026 16:56:14] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 16:56:45 - services.audio_service - DEBUG - [AudioService] Attempting to play test audio at: /Users/csmtech/Desktop/new-IoT/checkpoint-config/static/audio/test_audio.wav
2026-09-04 16:56:45 - services.audio_service - ERROR - [AudioService] Failed to play audio: Windows audio system not available (winsound missing)
2026-09-04 16:56:45 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:56:45] "POST /api/audio/test HTTP/1.1" 500 -
2026-09-04 16:56:49 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:56:49] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:57:02 - werkzeug - INFO - 192.168.31.87 - - [04/Sep/2026 16:57:02] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 16:57:14 - werkzeug - INFO - 192.168.31.87 - - [04/Sep/2026 16:57:14] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 16:57:18 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:57:18] "GET /api/update/status HTTP/1.1" 200 -
2026-09-04 16:57:58 - urllib3.connectionpool - DEBUG - Starting new HTTPS connection (1): api.github.com:443
2026-09-04 16:57:58 - urllib3.connectionpool - DEBUG - https://api.github.com:443 "GET /repos/omsm/RajMines-Application/releases/latest HTTP/1.1" 200 1025
2026-09-04 16:58:14 - werkzeug - INFO - 192.168.31.87 - - [04/Sep/2026 16:58:14] "POST /rfid_management HTTP/1.1" 200 -
2026-09-04 16:58:43 - services.audio_service - DEBUG - [AudioService] Attempting to play test audio at: /Users/csmtech/Desktop/new-IoT/checkpoint-config/static/audio/test_audio.wav
2026-09-04 16:58:43 - services.audio_service - ERROR - [AudioService] Failed to play audio: Windows audio system not available (winsound missing)
2026-09-04 16:58:43 - werkzeug - INFO - 127.0.0.1 - - [04/Sep/2026 16:58:43] "POST /api/audio/test HTTP/1.1" 500 -
^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^C^Czsh: terminated  python3 app.py
(venv) csmtech@CSM checkpoint-config % /Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/multiprocessing/resource_tracker.py:224: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
This happened when: I cross on macos window to close, then application didn't stop, then CMD+F4 forcefully closed

---

**Cursor**

Two issues: audio still from the old process, and on macOS the webview readiness check is Windows-only so it tears down the window and leaves Flask running after the browser closes. Fixing webview lifecycle and Chrome detection.

The hang after closing the window came from the macOS UI launcher path — not from Cmd+F4 itself.

**What went wrong**
1. On macOS, the Windows “is the window visible?” check always failed, so after ~15s the app **destroyed the native webview** and fell back to Chrome.
2. Chrome isn’t installed on this Mac → it opened the **default browser**.
3. Closing that browser tab **does not stop Flask**, so `python3 app.py` kept running until you force-killed it.

**What we fixed**
- Skip the Windows HWND monitor on macOS/Linux so `webview.start()` stays open until you close the native window.
- Use Cocoa for pywebview on Darwin.
- When the UI session ends (webview or Chrome), shut the process down cleanly (`os._exit` after cleanup).
- If it falls back to the default browser, log that you must **Ctrl+C** in the terminal (browser tab close still can’t stop the server).

**What you should do**
1. Fully stop any leftover process (`Ctrl+C`, or kill old `python3 app.py`).
2. Restart: `python3 app.py` from the venv.
3. You should see a log like: `Starting native webview on darwin...`
4. Close the **app window** (red traffic light) — the process should exit.
5. Audio test should use **afplay** after restart (not the old winsound error).

Optional: install Google Chrome if you want Chrome app-mode as a fallback; without it, auto mode uses pywebview then the system browser.

---

**User**

just like the UI you have done for Mines Entry, with multiple icons, use TareWb-App

---

**Cursor**

I'll compare the Mine Entry multi-icon UI with TareWb-App and align TareWb to the same pattern.

Expanding TareWb from 3 condensed icons to a full Mines Entry–style multi-icon strip mapped to the weighbridge flow.

TareWb now uses the same multi-icon strip pattern as Mines Entry.

**Icon strip (7 steps)**  
RFID Read → RFID Validation → ANPR Read → ANPR Update → WEIGHT → Vehicle Exit → Truck Exited

**Behavior**
- Step cards stay in **Flow Details** (hidden by default)
- Icons show loading / success / error / skipped (ANPR Update skipped when ANPR matches)
- UI resets ~2s after Truck Exited succeeds

Hard-refresh the TareWb dashboard to pick up the changes.

---

**User**

in tare-wb also add the weight api validation

---

**Cursor**

I'll look at how weight API validation works elsewhere and what's already in TareWb, then wire it in.

Adding a separate Weight Validation icon (for the weight-details API), matching RFID Read / RFID Validation.

TareWb now has a dedicated **Weight Validation** step in the icon strip, same pattern as RFID Validation.

**Icon strip**  
RFID Read → RFID Validation → ANPR Read → ANPR Update → **Weight Read** → **Weight Validation** → Vehicle Exit → Truck Exited

- **Weight Read** — digitizer / platform weight  
- **Weight Validation** — OCI weight-details API (loading / success / error)

Flow Details title and MQTT copy now say “Weight Validation” as well. Hard-refresh the dashboard to see it.

---

**User**

@TareWb-App/logs/tare_wb.log check this logs and update the demo-app so that instead of https://gmuatociexp.gmdcltd.co.in i will call http://localhost:8001 so internal simulation. Make success and error cases

---

**Cursor**

I'll inspect the tare_wb logs and the current demo-app, then wire localhost:8001 simulation endpoints for success and error cases.

Building a localhost:8001 OCI simulator with success/error scenarios and pointing TareWb at it.

Logs showed TareWb calling **UAT OCI** (`https://gmuatociexp.gmdcltd.co.in`) while the digitizer was already on `:8001`. Demo-app now simulates both.

**What changed**
- `demo-app/apis.py` — local OCI + digitizer on **:8001** with switchable scenarios
- `iot_configuration.json` + `.env` — `OCI_BASE_URL=http://localhost:8001`

**Run**
```bash
cd TareWb-App/demo-app && python3 apis.py
# restart TareWb so it picks up OCI_BASE_URL
```

**Scenarios**
| Scenario | What it tests |
|---|---|
| `success` (default) | Full happy path |
| `rfid_invalid` | RFID business reject |
| `rfid_unreachable` | RFID 503 popup |
| `weight_fail` | Weight Validation red step |
| `weight_unreachable` | Weight-details 503 popup |
| `weight_confirm_reject` | Out-of-band + confirm abort |
| `weight_confirm_ok` | Confirm updates tolerance |
| `status_abort` / `status_retry` / `status_ok` | Manual ANPR status_check |

```bash
curl -X POST http://localhost:8001/sim/scenario \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"weight_fail"}'
curl http://localhost:8001/sim/scenario
```

To use real UAT again, set `OCI_BASE_URL=https://gmuatociexp.gmdcltd.co.in` (or remove it) and restore `oci_base_url` in config.

---

**User**

2026-09-04 17:44:54 [INFO] tare_wb.main: RFID cloud controls wb_type=unidirectional directions=['entry_a']
2026-09-04 17:44:54 [ERROR] tare_wb.services.mqtt_ws: MQTT WebSocket bind 0.0.0.0:9001 failed: [Errno 48] Address already in use
2026-09-04 17:44:54 [INFO] tare_wb.services.frontend_mqtt: Optional MQTT TCP 127.0.0.1:1883 (dashboard uses ws://<pc-ip>:9001)
2026-09-04 17:44:54 [INFO] tare_wb.services.frontend_mqtt: Frontend MQTT connected 127.0.0.1:1883
MQTT websocket error why? Resolve it

---

**Cursor**

Port 9001 is already bound — I'll find what's holding it and fix the MQTT WebSocket startup so this doesn't keep happening.

Mosquitto already owns port 9001. I'll adjust the app so it uses that broker instead of failing the in-app WebSocket bind.

**Cause:** Mosquitto is already listening on **port 9001** (WebSocket). TareWb also tried to start its in-app MQTT WebSocket broker on the same port → `Address already in use`.

That is expected on your machine. The app already connected to Mosquitto on **TCP 1883**, and the dashboard should use Mosquitto’s **ws://…:9001**.

**Fix applied**
- If `:9001` is taken, skip the in-app broker (INFO, not ERROR)
- Publish via Mosquitto TCP `:1883` → browsers on WS `:9001` still get updates
- Same handling in Mine-entry and Tracking-point

After restart you should see something like:
`Using external MQTT broker: TCP 127.0.0.1:1883 + WebSocket :9001 (in-app WS skipped — port already bound)`

Keep Mosquitto running — do **not** free 9001 unless you want the in-app broker instead.

