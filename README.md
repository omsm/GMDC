# GMDC Yard IoT

Python runtimes for Gujarat Mineral Development Corporation (GMDC) mine-yard checkpoints: RFID, Modbus I/O (traffic lights / boom barriers / sensors), ANPR, OCI APIs, weighbridge digitizer, and an operator web dashboard.

This workspace is one site install. Shared packages (`gmdc_common`, `checkpoint-config`, `digitizer-app`) live next to two family runtimes so every PC can commission hardware, share drivers, and run the matching site flow via `checkpoint_type`.

**Current product version:** see [`version.md`](version.md) (**1.15**).

## Site flow

```
Mines entry → Tare WB → Tracking point-1 → Vadaghat (gross check WB)
           → Tracking point-2 → Final gross WB → Mines exit
```

| Stage | Runtime folder | Config type | Trip prefix |
|-------|----------------|-------------|-------------|
| Mines Entry, Tracking, Mines Exit | `Mines-Checkpoint/` | `checkpoint` | `T` / `CE` / `X` |
| Tare, Vadaghat, Final gross | `Mines-WB/` | `weighbridge` | `T` / `V` / `G` |

Legacy folders `Mine-entry/`, `Tracking-point-1/`, and `TareWb-App/` remain as reference copies; **new work should use `Mines-Checkpoint` and `Mines-WB`**.

## Repository layout

```
new-IoT/
├── gmdc_common/          Shared library (hardware, RFID, FSM, display, voice)
├── checkpoint-config/    Commissioning UI - writes iot_configuration.json
├── digitizer-app/        PySide serial weighbridge reader + HTTP weight API
├── digitizer-decoder/    Web digitizer (API or MQTT) + operator dashboard
├── mqtt_broker_setup/    Ensure local Mosquitto on 1883 + WebSocket 9001
├── Mines-Checkpoint/     Checkpoint family runtime (entry / tracking / exit)
├── Mines-WB/             Weighbridge family runtime (tare / vadaghat / gross)
└── version.md
```

Application-specific workflow, state/event enums, and OCI payload shaping stay in each family app. Device drivers and the generic FSM engine live in `gmdc_common`.

---

## Shared packages

### `gmdc_common`

Installable library (`gmdc-common`, Python ≥ 3.9). Both runtimes and the config tool import it.

| Package | Contents |
|---------|----------|
| `gmdc_common.hardware` | Modbus I/O, traffic light, boom barrier, sensor poller, RFID reader, RTSP snapshot |
| `gmdc_common.services` | MQTT/console display, Zebra RFID cloud control, Basic-Auth HTTP client, voice |
| `gmdc_common.core` | Table-driven `BaseStateMachine` |
| `gmdc_common.utils` | pymodbus version-compat helpers, rotating-file logging |

```bash
pip install -e ./gmdc_common
```

### `checkpoint-config`

Commissioning tool for all site types. Flask UI on **http://127.0.0.1:8080**. Writes `iot_configuration.json` used by the runtimes.

**Profiles** (`services/profiles.py`):

| Type | Family | Digitizer | Typical I/O |
|------|--------|-----------|-------------|
| `checkpoint` | **Mines-Checkpoint** | no | Front camera, 1 sensor, 1 TL, 1 boom |
| `weighbridge` (uni or bi) | **Mines-WB** | yes | Top + front cameras; entry/exit hardware; dual RFID when bi |

Older ids (`mines_entry`, `tracking_*`, `mines_exit`, `tare_wb`, `vadaghat_wb`, `gross_wb`) load as `checkpoint` or `weighbridge`. The RFID validation prefix still selects the trip.

### `digitizer-app`

Standalone PySide6 serial reader. HTTP API: **http://0.0.0.0:8800/read_stable_weight**.

### `digitizer-decoder`

Web replacement for the PySide shell (same calibration / stable-weight logic). Dashboard default **http://127.0.0.1:8800/**. Modes: **API** (`/read_stable_weight`) or **MQTT** request/response. Live UI status over MQTT WebSocket (`gmdc/digitizer/status` on **:9001**). See [`digitizer-decoder/README.md`](digitizer-decoder/README.md).

### `mqtt_broker_setup`

Shared helper used at app startup: if MQTT **1883** or WS **9001** is down, install/configure/start local Mosquitto so dashboards and digitizer MQTT can connect.

---

## Runtime apps

Both share: Flask API + operator dashboard, MQTT WebSocket (**9001**), Zebra `POST /rfid_data`, OCI + ANPR, Modbus via `gmdc_common`.

Copy `.env.example` → `.env`. `DEMO_MODE=true` uses demo I/O (and demo weight on Mines-WB).

### Mines-Checkpoint

RFID → OCI validate → ANPR → grant / status poll → boom-close → sensor clear → IDLE.

OCI path defaults and boom-close body follow `checkpoint_type`:

| Type | Boom-close style |
|------|------------------|
| `mines_entry`, `mines_exit` | `truck_details` + `close-type` |
| `tracking_1`, `tracking_2` | ANPR images; `top_image` may be JSON `null` |

Sample configs: `Mines-Checkpoint/samples/`. Operator UI is the perfected Flow Details icon dashboard (same as Mines Entry).

```bash
cd Mines-Checkpoint
cp samples/iot_configuration-tracking-1.json iot_configuration.json   # example
python main.py
```

### Mines-WB

Entry sensor → position → WB sensor → digitizer (> 5 t) → RFID → OCI → ANPR → weight-details → exit → IDLE.

Also driven by `truck_details` prefixes `T|` / `V|` / `G|`. Sample configs: `Mines-WB/samples/`. Operator UI matches the perfected TareWb Flow Details strip (including Weight Read / Weight Validation).

```bash
cd Mines-WB
python main.py
# Live weight also needs: python ../digitizer-app/serial_ui.py
```

---

## How the pieces connect

```
checkpoint-config  ──writes──►  iot_configuration.json
                                      │
digitizer-app :8800  ◄── POST /read_stable_weight ──  Mines-WB
                                      │
gmdc_common  ◄── import ──  Mines-Checkpoint / Mines-WB / checkpoint-config
                                      │
                         Zebra FX ── POST /rfid_data ──► runtime Flask
                         Modbus TCP ── TL / boom / sensors
                         ANPR ── /api/detect
                         GMDC OCI ── RFID / status / boom-close / reset
                         Browser ── http://<pc-ip>:<api-port>/  +  ws://<pc-ip>:9001
```

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ./gmdc_common
pip install -r Mines-Checkpoint/requirements.txt
pip install -r Mines-WB/requirements.txt
cp Mines-Checkpoint/.env.example Mines-Checkpoint/.env
cp Mines-WB/.env.example Mines-WB/.env
```

## Run

```bash
python checkpoint-config/app.py
python digitizer-app/serial_ui.py
python Mines-Checkpoint/main.py
python Mines-WB/main.py
```

## Tests

```bash
python -m unittest discover -s Mines-Checkpoint/tests -v
python -m unittest discover -s Mines-WB/tests -v
```

## Ports (typical)

| Service | Port |
|---------|------|
| checkpoint-config UI + RFID | 8080 |
| Mines-Checkpoint Flask | `API_PORT` (often 8000/8080) |
| Mines-WB Flask | `server.port` in IoT config (sample 8080) |
| Dashboard MQTT WebSocket | 9001 |
| Digitizer HTTP | **8800** |
| Modbus TCP | 502 |
| Optional Mosquitto | 1883 |

## Per-app docs

- [`Mines-Checkpoint/README.md`](Mines-Checkpoint/README.md)
- [`Mines-WB/README.md`](Mines-WB/README.md)
- [`gmdc_common/README.md`](gmdc_common/README.md)
- [`checkpoint-config/README.md`](checkpoint-config/README.md)
- [`digitizer-app/README.md`](digitizer-app/README.md)
- [`version.md`](version.md)
