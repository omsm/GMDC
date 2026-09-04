# GMDC Yard IoT

Python runtimes for Gujarat Mineral Development Corporation (GMDC) mine-yard checkpoints: RFID, Modbus I/O (traffic lights / boom barriers / sensors), ANPR, OCI APIs, weighbridge digitizer, and an operator web dashboard.

This workspace is one site install. Shared packages (`gmdc_common`, `checkpoint-config`, `digitizer-app`) live next to the checkpoint apps so every PC can commission hardware, share drivers, and run the matching site flow.

## Site flow

```
Mines entry → Tare WB → Tracking point-1 → Vadaghat (gross check WB)
           → Tracking point-2 → Final gross WB → Mines exit
```

| Stage | Folder | Status in this repo |
|-------|--------|---------------------|
| Mines Entry | `Mine-entry/` | Runtime app |
| Tare weighbridge | `TareWb-App/` | Runtime app (also has sample configs for Vadaghat / gross) |
| Tracking Point-1 | `Tracking-point-1/` | Runtime app |
| Tracking Point-2 / Mines Exit | - | Same checkpoint family as Mine-entry; not a separate app yet |
| Vadaghat / Final gross WB | `TareWb-App/` | Same weighbridge runtime; switch `checkpoint_type` in IoT config |

## Repository layout

```
new-IoT/
├── gmdc_common/          Shared library (hardware, RFID, FSM, display, voice)
├── checkpoint-config/    Commissioning UI - writes iot_configuration.json
├── digitizer-app/        Serial weighbridge reader + HTTP weight API
├── Mine-entry/           Checkpoint runtime
├── Tracking-point-1/     Checkpoint runtime (tracking OCI paths)
├── TareWb-App/           Weighbridge runtime
└── .gitignore
```

Application-specific workflow, state/event enums, and OCI payload shaping stay in each app. Device drivers and the generic FSM engine live in `gmdc_common`.

---

## Shared packages

### `gmdc_common`

Installable library (`gmdc-common`, Python ≥ 3.9). Every runtime and the config tool import it.

| Package | Contents |
|---------|----------|
| `gmdc_common.hardware` | Modbus I/O, traffic light, boom barrier, sensor poller, RFID reader, RTSP snapshot |
| `gmdc_common.services` | MQTT/console display, Zebra RFID cloud control, Basic-Auth HTTP client, voice |
| `gmdc_common.core` | Table-driven `BaseStateMachine` |
| `gmdc_common.utils` | pymodbus version-compat helpers, rotating-file logging |

Checkpoint apps re-export these from local `hardware/` and `services/` modules so app code can `from hardware import TrafficLight` while the implementation lives in one place.

Install once from the workspace root:

```bash
pip install -e ./gmdc_common
```

### `checkpoint-config`

Commissioning tool for all site types. Flask UI (WebView2 / Chrome / browser) on **http://127.0.0.1:8080**. Writes `checkpoint-config/iot_configuration.json`, which runtimes load (Tare WB also falls back to this path).

Zebra readers in API mode POST tags to the same host/port: `POST /rfid_data`.

**Profiles** (`services/profiles.py`):

| Type | Family | Digitizer | Typical I/O |
|------|--------|-----------|-------------|
| `mines_entry`, `tracking_1`, `tracking_2`, `mines_exit` | checkpoint | no | 1 traffic light, 1 boom, 1 sensor |
| `tare_wb`, `vadaghat_wb`, `gross_wb` (uni) | weighbridge | yes | 2 TL / 2 boom / 3 sensors |
| same types (bi) | weighbridge | yes | 4 TL / 2 boom / 3 sensors + dual RFID |

Digitizer in this tool is **API only**: store digitizer-app host/port and test `POST /read_stable_weight`. Serial calibration is done in `digitizer-app`, not here.

```bash
cd checkpoint-config
pip install -r requirements.txt
python app.py
```

Requires `gmdc_common` for Zebra cloud login and pymodbus helpers.

### `digitizer-app`

Standalone PySide6 desktop app. No imports from other GMDC packages.

- Reads the weighbridge digitizer over serial
- Calibrates weight extraction by ASCII byte indices
- Serves **http://0.0.0.0:8800/read_stable_weight** (`POST` or `GET`)

```json
{ "statusCode": 200, "stable_weight": 43000.0 }
```

The HTTP port is **8800** in the app. Host/port stored in `iot_configuration.json` (and tested from checkpoint-config) must match that listener. Default placeholders in the config tool use 8100 - change them to 8800 (or whatever you bind) before going live.

```bash
cd digitizer-app
pip install -r requirements.txt
python serial_ui.py
```

First run: set serial port + ASCII index calibration, Save. The dashboard and API start after that.

---

## Runtime apps

All three share the same spine: Flask API + operator dashboard, in-process MQTT WebSocket broker (**TCP 9001**), Zebra `POST /rfid_data`, OCI + ANPR clients, Modbus via `gmdc_common`.

Secrets and site overrides: copy `.env.example` → `.env` in the app folder. `DEMO_MODE=true` uses demo I/O and (on Tare WB) a demo digitizer weight instead of live hardware.

### Mine-entry

Checkpoint: RFID → OCI `rfid-tag` → ANPR → `invalid-truck-number` → grant or `status_check` poll → boom-close → sensor clear → IDLE.

Hardware: 1 RFID (Zebra API), 1 handheld fallback, 1 traffic light, 1 boom, 1 entry sensor.

Config: `Mine-entry/iot_configuration.json` (or `IOT_CONFIG_PATH`). Default Flask port from `API_PORT` (8000); set `API_PORT=8080` if the Zebra reader is pointed at the config-tool port.

```
IDLE → RFID → validate → ANPR → boom / TL → sensor clear → IDLE
```

### Tracking-point-1

Same process as Mine-entry with tracking-point OCI paths:

| Step | Path |
|------|------|
| RFID | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag` |
| Invalid truck | `/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number` |
| Status | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status` |
| Boom close | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close` |

Boom-close carries `front_image` / `anpr_image` from ANPR (no local camera). `top_image` is always `null`.

Config: `Tracking-point-1/iot_configuration.json`. Profile id in checkpoint-config is `tracking_1`; the runtime sample file uses `checkpoint_type: tracking_point_1`.

### TareWb-App

Weighbridge: entry sensor → position → WB sensor → digitizer (> 5 t) → RFID → OCI → ANPR → top photo → weight-details → exit grant → exit sensor → IDLE.

Loads config in this order: `IOT_CONFIG_PATH`, local `TareWb-App/iot_configuration.json`, then `checkpoint-config/iot_configuration.json`. Flask port comes from `server.port` in that file (sample: **8080**).

Bidirectional (`wb_type: bidirectional`): ENTRY vs EXIT sensor edge selects direction; RFID starts only after weight > 5 t on the selected reader.

```bash
# Weighbridge PC also needs digitizer-app running when DEMO_MODE=false
```

---

## How the pieces connect

```
checkpoint-config  ──writes──►  iot_configuration.json
                                      │
digitizer-app :8800  ◄── POST /read_stable_weight ──  TareWb-App
                                      │
gmdc_common  ◄── import ──  Mine-entry / Tracking-point-1 / TareWb-App / checkpoint-config
                                      │
                         Zebra FX ── POST /rfid_data ──► runtime Flask
                         Modbus TCP ── I/O ──► TL / boom / sensors
                         ANPR ── /api/detect
                         GMDC OCI ── RFID / status / boom-close / reset_checkpoint
                         Browser ── http://<pc-ip>:<api-port>/  +  ws://<pc-ip>:9001
```

Manual UI reset (and abort with an open transaction) calls OCI `reset_checkpoint` so GMDC can accept the next RFID. A successful cycle that ends after boom-close does **not** call that API.

---

## Prerequisites

- Python **3.9+**
- pip
- On a live site: Modbus I/O, Zebra FX (API mode), ANPR service, OCI reachability
- Weighbridge only: `digitizer-app` on the serial PC, host/port matching IoT config
- Operator UI from another machine: allow inbound **TCP** on the Flask port and **9001**

Mosquitto is optional. The dashboard uses the in-process MQTT WebSocket broker on port 9001.

## Setup

From the workspace root:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ./gmdc_common
```

Then install the app you are running:

```bash
pip install -r Mine-entry/requirements.txt
pip install -r Tracking-point-1/requirements.txt
pip install -r TareWb-App/requirements.txt
# commissioning / digitizer as needed:
pip install -r checkpoint-config/requirements.txt
pip install -r digitizer-app/requirements.txt
```

```bash
cp Mine-entry/.env.example Mine-entry/.env
cp Tracking-point-1/.env.example Tracking-point-1/.env
cp TareWb-App/.env.example TareWb-App/.env
```

Commission devices with `checkpoint-config`, then copy or point `IOT_CONFIG_PATH` at the generated `iot_configuration.json` for that PC.

## Run

```bash
python checkpoint-config/app.py          # http://127.0.0.1:8080
python digitizer-app/serial_ui.py        # HTTP :8800
python Mine-entry/main.py
python Tracking-point-1/main.py
python TareWb-App/main.py
```

Operator dashboard (same port as the runtime API):

| URL | Page |
|-----|------|
| `http://<pc-ip>:<api-port>/` | Operational dashboard |
| `http://<pc-ip>:<api-port>/animated.html` | Live animation (Tare WB) |

Live updates: `ws://<pc-ip>:9001`.

## Tests

```bash
python -m unittest discover -s Mine-entry/tests -v
python -m unittest discover -s Tracking-point-1/tests -v
python -m unittest discover -s TareWb-App/tests -v
```

## Ports (typical)

| Service | Port |
|---------|------|
| checkpoint-config UI + RFID intake | 8080 |
| Mine-entry / Tracking-point-1 Flask | `API_PORT` (default 8000; use 8080 to match Zebra) |
| Tare WB Flask | `server.port` in IoT config (sample 8080) |
| Dashboard MQTT WebSocket | 9001 |
| Digitizer HTTP API | **8800** (app) |
| Modbus TCP | 502 |
| MQTT display broker (optional Mosquitto) | 1883 |

## Per-app docs

- [`gmdc_common/README.md`](gmdc_common/README.md)
- [`checkpoint-config/README.md`](checkpoint-config/README.md)
- [`digitizer-app/README.md`](digitizer-app/README.md)
- [`TareWb-App/README.md`](TareWb-App/README.md)
- [`Tracking-point-1/README.md`](Tracking-point-1/README.md)
