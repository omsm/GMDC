# GMDC Yard IoT — Version History

Workspace-level changelog for the site install (runtimes + shared packages).  
**Current version: 1.2**

Per-app `VERSION` files may differ (e.g. Mine-entry / Tracking-point-1 `1.0.0`, TareWb-App `0.1.0`, checkpoint-config `0.1.0`). This document tracks the **monorepo / product** releases.

---

## 1.2 — 2026-09-05 (latest)

Operator-facing flow icons, local OCI simulation, and MQTT broker coexistence.

### Operator UI
- Flow Details modal: step cards hidden by default; open via **Flow Details**, close with **X**
- Icon strip with loading / success / error / skipped states
  - **Checkpoints (Mine-entry, Tracking-point-1):** RFID Read → RFID Validation → ANPR Read → ANPR Update → Vehicle Exit → Truck Exited
  - **TareWb-App:** same plus **Weight Read** and **Weight Validation** (OCI weight-details)
- ANPR Update skipped when ANPR match (`anpr_status = 1`)
- UI auto-reset ~2 seconds after Truck Exited succeeds

### Demo / simulation
- `TareWb-App/demo-app/apis.py` local OCI + digitizer on **http://localhost:8001**
- Switchable scenarios (`success`, `rfid_invalid`, `weight_fail`, unreachable/confirm/status variants) via `POST /sim/scenario`
- Config/env can point `OCI_BASE_URL` at localhost for offline testing

### Platform / MQTT
- If Mosquitto already owns **:9001**, skip in-app WebSocket broker (INFO, not ERROR)
- Publish via Mosquitto TCP **:1883**; dashboard still uses `ws://…:9001`
- Applied across Mine-entry, Tracking-point-1, and TareWb-App
- checkpoint-config: Mosquitto Homebrew `sbin` detection; macOS `afplay` audio test; pywebview lifecycle so closing the window stops Flask

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
Tracking-2 and Mines Exit reuse the checkpoint family (profiles only in 1.0).

---

## Version map (quick)

| Version | Focus |
|---------|--------|
| **1.2** | Flow Details icons, Weight Validation UI, demo OCI :8001, Mosquitto/WS coexistence, macOS config-tool fixes |
| **1.1** | Shared packages + README; API/error UX; voice; OCI message text; I/O status cascade |
| **1.0** | Core checkpoint + weighbridge runtimes, hardware, OCI/ANPR, dashboards, tests |

---

## Notes for the next release

Open items tracked outside this file (e.g. `to-do.md.md`): further operator UI polish, Tracking-2 / Mines Exit runtimes, digitizer port alignment (8800 vs config defaults), bidirectional ENTRY_B hardware swap.
