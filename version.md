# GMDC Yard IoT — Version History

Workspace-level changelog for the site install (runtimes + shared packages).  
**Current version: 1.17**

Per-app `VERSION` files track each runtime build (e.g. Mines-Checkpoint / Mines-WB `1.17.0`). This document tracks the **monorepo / product** releases.

---

## 1.17 — 2026-10-02 (latest)

Weighing starts when the truck is only on the weighbridge sensor.

### Mines-WB positioning
- Sensor 2 cut and sensor 1 clear starts weight capture. Move Forward stops at that point
- The sensor clear event releases the occupied flag before the lane checks position, so a truck sitting only on the weighbridge sensor is not held until the positioning timer resets the lane

---

## 1.16 — 2026-10-01

Bidirectional weighbridge commissioning, live digitizer weight owned by Mines-WB, and the Vadhghat load/unload path.

### checkpoint-config
- Camera order is Front, Top on a unidirectional bridge and Front-1, Front-2, Top on a bidirectional bridge. Top can be skipped. Saving one camera keeps the other camera's tick
- Display check publishes `pcb_id`, waits 2 seconds, then publishes `data_info` once for that board
- I/O devices have an Enable switch. Off skips the device. On makes the pins editable and the relay test available. A bidirectional bridge has four traffic lights
- A successful I/O connection writes `device_ip`: the controller Ethernet IP, or the COM port when the controller is serial. That value is not the Mac's LAN address
- Both bidirectional RFID readers must pass Check & Save. Saving one reader leaves the other reader's result in place. The RFID result button is Done

### Digitizer
- In MQTT mode the decoder publishes live readings. Non-zero values go out continuously. Zero is sent once until the weight changes. A message on the request topic always publishes the current value
- Mines-WB decides stable weight: the same non-zero reading must repeat for `digitizer_stable_count` samples (default 10). Zero is not a stable capture
- HTTP `/read_stable_weight` on the decoder still waits for its own stable reading

### Mines-WB lane
- Before a trip starts, the platform weight must be 0. A non-zero idle weight plays `error_start.wav` then `Digitizer_error.wav` and does not start the transaction
- If the weight rises and then returns to 0 after the approach sensor is cut, and before only the weighbridge sensor is cut, the same clips play and the truck is sent out
- Bidirectional idle: both booms open, both entry lights green, both exit lights red. Sensor 1 starts side A. Sensor 3 starts side B. Sensor 2 never starts a trip. A non-zero idle weight blocks both approach sensors
- During a trip, the display, RFID reader, and traffic lights update only the side the truck entered. Idle text still goes to both displays
- Configured RFID API ports are opened in addition to the dashboard port (one port on a checkpoint or unidirectional bridge, two on a bidirectional bridge)

### Vadhghat (`V|` truck details)
- Allowed weight is target down to target minus tolerance, inclusive. For `45000` and `50`, that is 44950–45000 kg
- Inside the band: `vadhghat_weight_details`, then `vadhghat_boom_close`, then exit with Move forward
- Outside the band: `vadhghat_weight_adjustment` only. The boom opens. Move forward is not played
- Over the target: display `Overweight@{difference}Kg`. Voice is `error_start.wav`, then `g100.wav`, then the difference in kg. After that, only the difference repeats until the truck has exited
- Under the low end: display `Underweight@{difference}Kg`. Voice uses `g101.wav` in that first sequence, then only the difference until exit

### ANPR
- Mines-Checkpoint and Mines-WB: ANPR on with `anpr_status` 0 or 2, and ANPR switched off on the page, post `invalid-truck-number` once and then poll `status_check` until the vehicle is updated

---

## 1.15 — 2026-09-30

Operator dashboards use the liquid-glass UI on macOS, and the Transaction Flow panel stays usable on phones and tablets.

### Operator UI
- `OS_TYPE` at the top of each app entry point: `auto` (macOS gets liquid glass, Windows keeps the earlier UI), `macos`, or `windows`
- checkpoint-config, Mines-Checkpoint, Mines-WB, and digitizer-decoder share that switch
- Warm glass surfaces in light and dark, including status pills, device cards, and the camera dialog
- ANPR, Free Pass, and Reset sit to the right of **Transaction Flow** after operator login
- ANPR off uses the same warm glass button as the rest of the dark theme
- Weight and RFID boxes inside the flow panel use a 16px margin
- At tablet and phone widths the page stacks: **Transaction Flow** on top, **Device Status** underneath. The header, flow icons, and dialogs wrap instead of overflowing
- Camera close control is centered in Checkpoint, Weigh Bridge, and Digitizer Decoder

### Device status
- RFID shows Connected only when the configured RFID IP answers a ping. Empty, N/A, localhost, and `127.0.0.1` stay Disconnected

---

## 1.14 — 2026-09-30

checkpoint-config commissions a site as **Checkpoint** or **Weigh Bridge**. A saved front camera and a finished I/O test stay complete when you move between modules.

### Site types
- Page 1: Checkpoint or Weigh Bridge, plus the scan IP range. Weigh Bridge also asks unidirectional or bidirectional. Page 2 scans. Page 3 is device configuration.
- **Checkpoint:** front camera only, one entry sensor, one entry traffic light, one entry boom, no digitizer
- **Weigh Bridge:** top and front cameras, digitizer, entry and exit hardware. Bidirectional adds a second RFID reader and ENTRY A / ENTRY B traffic lights
- Older ids (`mines_entry`, `tracking_1`, `tracking_2`, `mines_exit`, `tare_wb`, `vadaghat_wb`, `gross_wb`) load as Checkpoint or Weigh Bridge
- RFID validation's first field still selects the trip: Checkpoint `T` / `CE` / `X`, Weigh Bridge `T` / `V` / `G`
- API endpoint list is the same for both types
- `SECURED_WEB_VIEW` at the top of `checkpoint-config/app.py`. `False` opens Safari or Chrome. `True` opens a native window at the screen size and blocks right-click and copy/paste
- Update checks read releases from `omsm/GMDC-Compiled-Application`

### Commissioning fixes
- Checkpoint camera Check & Save keeps the green tick after you open another module. Completion follows the front camera
- I/O Direct and Relay still open their own pin boxes. A checkpoint save needs the entry sensor and entry traffic light. The entry boom is required only when Enable is on (Open and Close). Hidden exit hardware is not required
- Finish names the missing steps (Camera, I/O Controller). Display topics show the IP you entered (`display_info/192.168.1.70`)

---

## 1.13 — 2026-09-29

Mines Exit waits for the exit document to download before boom close, and `reset_checkpoint` is off unless the site turns it on.

### Mines-Checkpoint — Mines Exit (`X|` truck details)
- RFID validation string starting with **`X|`** keeps the existing ANPR / status-check flow
- Before boom close, poll `POST /ords/gmdc_dicsm/dlms_checkpoint/download/docs` with `loading_slip_no`, `loading_slip_id`, and `device_ip`
- Slip ids come from the RFID JSON keys when present, otherwise from `X|rfid|vehicle|loading_slip_no|loading_slip_id|…|device_ip`
- Keep polling while `documentDownloaded` is false; when it is true, continue to boom close and the normal exit

### reset_checkpoint (`Mines-Checkpoint` and `Mines-WB`)
- `.env` **`RESET_CHECKPOINT_FLAG`** (default **false**)
- `false`: do not call `reset_checkpoint` on any reset path, including the operator Reset button
- `true`: post `reset_checkpoint` as before

---

## 1.12 — 2026-09-29

checkpoint-config RFID API commissioning (including two ports on a bidirectional weighbridge), and Mines-WB voice on startup and low weight.

### checkpoint-config — RFID API port
- API mode shows **RFID_API_PORT** (uni) or two fields (bi): **ENTRY A** (default **8080**) and **ENTRY B** (default **8081**). The two bi ports must differ.
- **Check & Save** logs into the Zebra reader, sets mode, and starts inventory, then listens for **120 seconds**
- Temporary endpoints on that port: `http://{Mac IP}:{RFID_API_PORT}/rfid_data` and `/rfid_management` (the main config UI port is reused when it matches)
- A tag POST to `/rfid_data` marks the check successful and saves `api_port`
- Right-click and copy/paste are allowed in the config UI

### Mines-WB — voice
- On startup, after hardware is up, play `voice/information/welcome.wav` (when voice is enabled and validated)
- Weight **≤ `MIN_WEIGHT_KG`**: play `error/error_start.wav` then `error/weight-error.wav`, then return to IDLE. RFID login / mode / start is not run
- Weight **> `MIN_WEIGHT_KG`**: RFID login → set mode → start, then wait for `/rfid_data` (unchanged)

---

## 1.11 — 2026-09-26

macOS offline packaging vendors Homebrew + Mosquitto bottles so site Macs can install the MQTT broker without downloading brew packages.

### Vendored MQTT broker (`packaging/macos/vendor/`)
- `download_vendor.sh` fetches Homebrew `install.sh`, pinned `brew.tar.gz`, and Mosquitto bottles (+ deps: openssl, libwebsockets, cjson, …)
- Bottle / Homebrew payloads are **gitignored**; tooling + README stay tracked
- `build_macos.sh` auto-downloads vendor when missing and copies `vendor/` into `dist/Mines-Automation/`

### Install order (`mqtt_broker_setup` / checkpoint-config)
1. Use Mosquitto if already present  
2. Ensure Homebrew: system brew → local `brew.tar.gz` bootstrap → local `install.sh` → download installer  
3. Install Mosquitto from **local bottles** when present; otherwise `brew install mosquitto` (network)

### Docs
- packaging README + deploy notes describe `vendor/` and offline broker setup

---

## 1.10 — 2026-09-26

MQTT LED display protocol (Display IP identity), transaction message strings with `@` line breaks, and bi-directional dual TX.

### MQTT display protocol (`gmdc_common` + runtimes)
- Device identity = **Display IP** (not broker host): subscribe `display_info/{ip}`, answer `pcb_id/{ip}` with `a`|`b`
- Transaction text on `data_info/a` (uni / checkpoint) or **both** `data_info/a` and `data_info/b` (bi-directional WB)
- Bi PCB letters: Entry A (first IP) → `a`, Entry B (second IP) → `b`
- Publish **Welcome** once when the display MQTT client first connects
- Broker remains localhost Mosquitto (`1883`); Display IP fields are separate in IoT config

### checkpoint-config
- Uni / checkpoint: one **Display IP**; bi WB: **Display IP (Entry A)** + **Display IP (Entry B)**
- Check & Save handshake waits for `display_info`, replies `pcb_id`, then test-TX on the matching `data_info` topic(s)

### Display message strings
- LED line break uses `@` (e.g. `RFID VALID@GJ01AB1234`)
- Checkpoint RFID OK: `RFID VALID@{truck}`
- WB RFID OK: `{truck}@{weight} Kg` (T → tare / unladen weight; V/G → gross / laden)
- Dual announce kept: LED MQTT + `wb_frontend/display` for the operator UI

---

## 1.9 — 2026-09-25

Dashboard Flow Details icons aligned with real workflow events; status-check manual-update confirmation for ANPR Update.

### Flow Details icons (Mines-Checkpoint + Mines-WB)
- **RFID Read** turns green as soon as a tag is read (before OCI validate)
- **RFID Validation** turns green only when OCI RFID validate succeeds
- **ANPR Update** turns green only when `status_check` returns  
  `statusCode: 201` + `vehicleStatus: 1` (`"Vehicle is updated manually"`)
- ANPR match / CE `statusCode: 200` / entry-granted paths no longer force Update green

### Workflow / UI wiring
- Publish `rfid_read` success on tag capture; `validating_rfid` success only after OCI OK
- Publish `"Vehicle is updated manually"` on manual update confirmation so the dashboard can tick Update
- ANPR-disabled path still runs invalid-truck then status-check (mismatch 0/2 behaviour unchanged)

---

## 1.8 — 2026-09-11

Digitizer MQTT commissioning polish, checkpoint-config wizard cleanup, and config persistence across re-runs.

### Digitizer MQTT (shipped end-to-end)
- checkpoint-config: digitizer mode **API | MQTT** (broker host = Mines-WB Mac; decoder on another PC)
- Status / heartbeat topic hardcoded as `gmdc/digitizer/status` (not shown in UI; both apps)
- Mines-WB MQTT client: subscribe weight + status; request stable weight for capture/validation
- IDLE gate: WB+exit clear **and** live weight **0** before entry cut (`weighbridge_0`); stops after entry
- Hang notify when decoder heartbeat is lost; decoder publishes weight only on value change

### checkpoint-config UX
- **Server** module removed from `/devices` wizard (not required for finish)
- Re-run **keeps** `iot_configuration.json` and section `validated` flags (no automatic wipe on checklist load)
- Explicit **Start fresh configuration** on checklist when a full wipe is needed
- Editing any section field immediately sets that section `validated: false` (+ root `status: false`) in JSON

---

## 1.7 — 2026-09-11

Digitizer Decoder web service, shared local Mosquitto bootstrap (1883 + 9001), and leaner dashboard MQTT publishing.

### Digitizer Decoder (`digitizer-decoder/`)
- New Flask web app replacing the PySide `digitizer-app` shell for field use
- Same ASCII index calibration + stable-weight logic; Mines-style dashboard
- Transport toggle: **API** (`/read_stable_weight`) or **MQTT** (request → stable → publish)
- Admin login unlocks Configuration (serial, transport, calibration)
- Serial: fixed **40-byte** reads (no `readline`); refresh-ports control in UI
- Live dashboard status over **MQTT WebSocket** (`gmdc/digitizer/status` on broker WS `:9001`); one HTTP bootstrap only
- Live weight always shown; **red** while unstable, **green** when stable; stable count wraps `1…10` then back to `1`
- Frame-end calibration: when operator picks `][`, store `]` so single `[xxxxx]` frames extract live
- Sample Arduino simulator (`arduino-app/`) streams zero-padded `[00000]`…`[50000]` with ADC averaging + hysteresis

### Local MQTT broker (`mqtt_broker_setup/`)
- Shared installer/ensure helper: check **1883** (MQTT) and **9001** (WebSocket); if down → install Mosquitto, write conf, start service/daemon
- Wired at startup for **checkpoint-config**, **Mines-Checkpoint**, **Mines-WB**, **Mine-entry**, **Tracking-point-1**, **TareWb-App**, and **digitizer-decoder**
- Settings expose `mqtt_port` (1883) and `mqtt_ws_port` (9001); HTTP/WS ports from display config are not used as TCP MQTT ports

### Dashboard MQTT traffic
- Frontend MQTT topics publish **only on real payload change** (device status monitor still polls hardware; MQTT send is change-gated)
- Browser connect / `request_status` / reset still force a full snapshot

### Digitizer MQTT (checkpoint-config + Mines-WB)
- Commissioning UI: digitizer mode **API | MQTT** with broker/topics (broker = Mines-WB Mac; decoder on another PC)
- Mines-WB MQTT client subscribes to weight + status; requests stable weight for capture/validation
- IDLE gate: WB+exit must be clear **and** live digitizer weight must be **0** before entry cut (same `weighbridge_0` announcement); check stops after entry
- Hang sync: decoder status heartbeat ~2s; Mines-WB notifies if heartbeat is lost
- Decoder publishes weight topic only when the weight value changes

---

## 1.6 — 2026-09-10

Updated default Zebra RFID CUSTOM **mode payload** in shared `gmdc_common`, plus package bump.

### RFID mode payload (`gmdc_common`)
- Default `DEFAULT_MODE_PAYLOAD` in `gmdc_common/gmdc_common/services/rfid_control.py` retuned for current site readers:
  - Antenna **5**, transmit power **30**
  - `antennaStopCondition` duration **100**
  - Query: `tagpopulation` 10, `sel` **NOT_SL**, session **S1**
  - TID `selects` mask (`800600`) for inventory filtering
  - Report filter **PER_ANTENNA** duration **1**
- Per-site override still supported via `mode_payload` under the RFID section in `iot_configuration.json` (falls back to the shared default when omitted)
- `gmdc-common` package version set to **0.2.8**

### Mines-Checkpoint
- `POST /rfid_data` logs the inbound RFID JSON payload for field debugging

---

## 1.5 — 2026-09-08

Operator ANPR toggle and clarified OCI invalid-truck / status-check rules, including CE trips on Mines-Checkpoint.

### Operator UI — ANPR toggle
- After login, **ANPR: ON/OFF** beside Free Pass / Reset on **Mines-Checkpoint** and **Mines-WB**
- Persists `anpr_enabled` in `iot_configuration.json` via `GET/POST /api/anpr-enabled`
- When **OFF**: skip `/api/detect`; call **invalid-truck** with `anpr_status: 2`; continue grant (checkpoint) or weight path (WB) without status-check (unless CE — see below)

### OCI — invalid-truck / status-check
- **invalid-truck** is always called after RFID validation (match, mismatch, and ANPR disabled)
- **status-check** (non-CE): only on ANPR mismatch (`anpr_status` **0** or **2**), polled until `vehicleStatus` allows continue/abort
- **ANPR match (`1`)** and **ANPR disabled** (non-CE): no status-check; proceed after invalid-truck

### Mines-Checkpoint — CE trips
- When RFID `truck_details` starts with **`CE|`**, after invalid-truck poll **check-status** for **all** ANPR outcomes (**0 / 1 / 2**) and when ANPR is disabled
- Loop until body **`statusCode == 200`**, then grant entry
- CE `truck_details` parsing uses the correct `device_ip` field (not the trailing vehicle number)
- **Mines-WB** has no CE status-check path

---

## 1.4 — 2026-09-06

Auto device IP from the commissioning PC, plus operator dashboard dark mode.

### Device IP
- On **checkpoint-config Finish**, detect this PC’s LAN IPv4 and write top-level `device_ip` into `iot_configuration.json`
- Preference: **Ethernet** first, then Wi-Fi, then other / UDP fallback (`utils/local_ip.py`)
- Field is **backend-only** — not shown in the commissioning UI, finish toast, or PDF report
- **Mines-Checkpoint** and **Mines-WB** load `device_ip` from IoT config for OCI payloads; `.env` `DEVICE_IP` is fallback only

### Operator UI — dark mode
- Header toggle (top right) switches light ↔ dark on **Mines-Checkpoint** and **Mines-WB** dashboards
- Theme preference stored in browser `localStorage` (`gmdc_ui_theme`) and restored on load
- Dark theme remaps existing CSS design tokens (no separate stylesheet)

---

## 1.3 — 2026-09-06

Family runtimes: one checkpoint app and one weighbridge app, selected by `checkpoint_type`.

### Family apps (workspace layout)
- **`Mines-Checkpoint/`** — single checkpoint runtime for:
  - `mines_entry`, `tracking_1`, `tracking_2`, `mines_exit`
  - OCI path defaults and boom-close body style (`entry` vs `tracking`) follow `checkpoint_type`
- **`Mines-WB/`** — single weighbridge runtime for:
  - `tare_wb`, `vadaghat_wb`, `gross_wb`
  - Same perfected TareWb operator UI (Flow Details + Weight Read / Weight Validation)
- Shared **`gmdc_common`** for both families
- Sample configs under each app’s `samples/` folder
- Dashboard logo / title / idle display follow `checkpoint_type` via `/api/status`
- Root **README.md** updated for the two-family layout
- Legacy folders `Mine-entry/`, `Tracking-point-1/`, `TareWb-App/` kept as reference copies

### How to switch site type
- Set `checkpoint_type` in `iot_configuration.json`, or `CHECKPOINT_TYPE` in `.env`
- Copy a profile from `samples/` over `iot_configuration.json` when commissioning a new PC

---

## 1.2 — 2026-09-05

Operator-facing flow icons, local OCI simulation, and MQTT broker coexistence.

### Operator UI
- Flow Details modal: step cards hidden by default; open via **Flow Details**, close with **X**
- Icon strip with loading / success / error / skipped states
  - **Checkpoints:** RFID Read → RFID Validation → ANPR Read → ANPR Update → Vehicle Exit → Truck Exited
  - **Weighbridge:** same plus **Weight Read** and **Weight Validation** (OCI weight-details)
- ANPR Update skipped when ANPR match (`anpr_status = 1`)
- UI auto-reset ~2 seconds after Truck Exited succeeds

### Demo / simulation
- Local OCI + digitizer simulator on **http://localhost:8001** (`demo-app/apis.py`)
- Switchable scenarios via `POST /sim/scenario`

### Platform / MQTT
- If Mosquitto already owns **:9001**, skip in-app WebSocket broker (INFO, not ERROR)
- Publish via Mosquitto TCP **:1883**; dashboard still uses `ws://…:9001`
- checkpoint-config: Mosquitto Homebrew `sbin` detection; macOS `afplay` audio test; pywebview lifecycle

---

## 1.1 — 2026-09

Shared packages restored in-repo; operator UX hardening; weighbridge voice and OCI correctness.

### Workspace
- Added **gmdc_common**, **checkpoint-config**, and **digitizer-app** beside the three runtimes
- Root **README.md** documenting site flow, layout, ports, and setup

### Operator UX (all three runtimes)
- Operator-facing API error kinds (no raw Python exceptions in the dashboard)
- Large popup for unreachable / server errors (e.g. ANPR not reachable)
- Yellow blink while waiting on ANPR / status-check mismatch
- Prefer OCI response `message` / `statusMessage` in step DIVs (bold red, larger fonts)
- Failure cascade: failed step and later steps stay red (TareWb exit-after-fail; checkpoints hold then IDLE)
- Device Status: when I/O controller is down, sensors / traffic lights / boom barriers show Disconnected

### Weighbridge (TareWb-App)
- `move-forward` voice path and timing during positioning
- `backward.wav` when exit sensor (S3) is cut during positioning (invalid alignment)
- Reset plays `application_reset.wav` once (dashboard no longer double-fires MQTT + HTTP)
- Final weight announcement only after weight-details HTTP **200** (tare / Vadhghat / gross intro clips + ton/kg files)
- OCI reset uses `.env` `OCI_USERNAME` / `OCI_PASSWORD` (not a separate JSON credential)

### OCI / Vadhghat
- Vadhghat weight-adjustment / gross-tolerance confirm paths aligned with business rules

---

## 1.0 — Baseline product

First complete yard install on this codebase: checkpoint + weighbridge FSMs, hardware integration, and dashboards.

### Runtimes
| App | Role |
|-----|------|
| **Mine-entry** | Checkpoint: RFID → OCI `rfid-tag` → ANPR → boom-close → sensor clear → IDLE |
| **Tracking-point-1** | Same FSM; tracking OCI paths (`checkpoint/rfid-tag`, `check-status`, `checkpoint_boom_close` + ANPR images) |
| **TareWb-App** | Weighbridge: sensors → digitizer (&gt; 5 t) → RFID → OCI/ANPR → weight-details → exit; Vadaghat/gross via `checkpoint_type` |

### Shared capabilities
- Flask API + vanilla JS operator dashboard
- In-process MQTT WebSocket broker on **:9001** (`wb_frontend/*` topics)
- Zebra RFID API intake (`POST /rfid_data`), Modbus TCP I/O via shared drivers
- Boom opens only when OCI boom-close returns status **200**
- ANPR `anpr_status` 0 / 1 / 2 and manual `status_check` / `check-status` polling
- `DEMO_MODE` for demo I/O (and demo weight on WB)
- Unit tests for FSMs, ANPR branches, WB RTO tolerance, bidirectional lane logic

### Planned site line (not all as separate folders)
```
Mines entry → Tare WB → Tracking-1 → Vadaghat → Tracking-2 → Gross WB → Mines exit
```
Tracking-2 and Mines Exit were profiles only in 1.0 (now covered by Mines-Checkpoint in 1.3).

---

## Version map (quick)

| Version | Focus |
|---------|--------|
| **1.17** | Weighing starts when only the weighbridge sensor is cut; the clear event no longer leaves the truck on Move Forward |
| **1.16** | Bi-directional commissioning; Mines-WB stable weight; Vadhghat in-band details/boom-close and out-of-band adjustment with Overweight/Underweight |
| **1.15** | Liquid glass on macOS (`OS_TYPE`); RFID online is an IP ping; Transaction Flow stays on top when the dashboard stacks |
| **1.14** | Config types are Checkpoint or Weigh Bridge; front-camera tick stays; checkpoint I/O ignores hidden exit hardware |
| **1.13** | Mines Exit `X|` polls download/docs until documentDownloaded; `RESET_CHECKPOINT_FLAG` gates reset_checkpoint |
| **1.12** | RFID_API_PORT Check & Save (120s, bi two ports); welcome.wav on WB start; low weight plays weight-error then IDLE |
| **1.11** | macOS vendor Homebrew + Mosquitto bottles; local-first broker install in Mines-Automation bundle |
| **1.10** | MQTT display protocol (Display IP / pcb_id / data_info); bi TX a+b; Welcome on connect; `@` message strings |
| **1.9** | Flow icons: RFID Read on tag; RFID Validation on OCI; ANPR Update only on statusCode 201 |
| **1.8** | Digitizer MQTT E2E; hardcoded status topic; no Server wizard step; config reuse on re-run; invalidate-on-edit |
| **1.7** | Digitizer Decoder; Mosquitto ensure; change-only UI MQTT; digitizer MQTT in config/Mines-WB; idle weight=0 + hang sync |
| **1.6** | Retuned default Zebra RFID `DEFAULT_MODE_PAYLOAD` in `gmdc_common` (0.2.8); optional per-site `mode_payload` override |
| **1.5** | ANPR ON/OFF toggle; invalid-truck always; status-check on mismatch 0/2; CE trips require check-status for all ANPR cases (Checkpoint) |
| **1.4** | Auto `device_ip` on Finish; dashboard light/dark mode toggle; runtimes read IP from IoT JSON |
| **1.3** | Family apps `Mines-Checkpoint` / `Mines-WB` via `checkpoint_type`; shared `gmdc_common` |
| **1.2** | Flow Details icons; Weight Validation UI; demo OCI :8001; Mosquitto/WS coexistence |
| **1.1** | Shared packages + README; API/error UX; voice; OCI message text; I/O status cascade |
| **1.0** | Core checkpoint + weighbridge runtimes, hardware, OCI/ANPR, dashboards, tests |

---

## Notes for the next release

Open items tracked outside this file (e.g. `to-do.md.md`): align PySide `digitizer-app` MQTT publish-on-change with decoder, bidirectional ENTRY_B hardware swap, retire legacy `Mine-entry` / `Tracking-point-1` / `TareWb-App` folders when ready.
