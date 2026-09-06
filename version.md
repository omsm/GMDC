# GMDC Yard IoT — Version History

Workspace-level changelog for the site install (runtimes + shared packages).  
**Current version: 1.4**

Per-app `VERSION` files track each runtime build (e.g. Mines-Checkpoint / Mines-WB `1.4.0`). This document tracks the **monorepo / product** releases.

---

## 1.4 — 2026-09-06 (latest)

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
| **1.4** | Auto `device_ip` on Finish; dashboard light/dark mode toggle; runtimes read IP from IoT JSON |
| **1.3** | Family apps `Mines-Checkpoint` / `Mines-WB` via `checkpoint_type`; shared `gmdc_common` |
| **1.2** | Flow Details icons; Weight Validation UI; demo OCI :8001; Mosquitto/WS coexistence |
| **1.1** | Shared packages + README; API/error UX; voice; OCI message text; I/O status cascade |
| **1.0** | Core checkpoint + weighbridge runtimes, hardware, OCI/ANPR, dashboards, tests |

---

## Notes for the next release

Open items tracked outside this file (e.g. `to-do.md.md`): further operator UI polish, digitizer port alignment (8800 vs config defaults), bidirectional ENTRY_B hardware swap, retire legacy `Mine-entry` / `Tracking-point-1` / `TareWb-App` folders when ready.
