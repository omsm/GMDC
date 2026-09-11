# Digitizer Decoder

Web replacement for the PySide `digitizer-app/serial_ui.py` shell.

Same serial indexing + stable-weight logic, with a **Mines-Checkpoint / Mines-WB** style dashboard and selectable transport:

| Mode | Behavior |
|------|----------|
| **API** | `POST/GET /read_stable_weight` → `{"statusCode":200,"stable_weight":…}` (Mines-WB compatible) |
| **MQTT** | Subscribe on request topic → wait stable → publish JSON on response topic |

The original `digitizer-app/` PySide UI remains available unchanged.

Product version: **1.7** (see root [`version.md`](../version.md)).

## Layout

```
digitizer-decoder/
  main.py                 # entrypoint (+ local Mosquitto ensure)
  config.json             # serial + communication settings
  config/settings.py
  core/app_context.py     # application management
  services/
    index_engine.py       # ASCII index extraction (from digitizer-app)
    weight_runtime.py     # stable-weight waiter
    serial_service.py     # fixed 40-byte reads + reconnect
    mqtt_bridge.py        # MQTT request/response + live status
  api/                    # Flask dashboard + weight API
  static/web/             # operator UI (MQTT WS status)
  arduino-app/            # sample Arduino weight simulator
```

## Setup

```bash
cd digitizer-decoder
pip install -r requirements.txt
python main.py
```

Open the printed dashboard URL (default **http://127.0.0.1:8800/** in API mode). Local Mosquitto is ensured on **1883** / **9001** via `mqtt_broker_setup`.

## Configure

1. **Serial** — port / baud / data bits / parity / stop bits (use **Refresh ports** after plugging USB)
2. **Communication** — choose **API** or **MQTT** and fill parameters  
3. **Calibration** — Capture sample → pick R1 / R3 / R4 → Save  

Serial reads are fixed **40-byte** chunks (not line-based). Live raw/weight can appear once the port is open; calibration still required for stable publish.

### Live dashboard status (MQTT)

Retained snapshots on `gmdc/digitizer/status` over broker WebSocket **:9001**. The UI connects with Paho; HTTP `/api/status` is used only for a one-shot bootstrap if MQTT is unavailable.

Live weight is always shown: **red** while unstable, **green** when stable. Stable count wraps `1…10` then restarts at `1`.

### MQTT weight topics

- **Subscribe** (`topic_subscribe`): empty `{}` or `{"action":"read_stable_weight"}`  
- **Publish** (`topic_publish`): `{"statusCode":200,"stable_weight":43000.0}`

## HTTP (always available on the dashboard port)

```bash
curl -X POST http://127.0.0.1:8800/read_stable_weight \
  -H "Content-Type: application/json" -d "{}"
```

Point Mines-WB `digitizer` URL at this host/port when using API mode.

## Admin login

Default credentials (in `config.json` → `admin`):

- Username: `admin`
- Password: `gmdc@123`

Dashboard shows live weight only. After login, use **Configuration** for serial, API/MQTT, and calibration (popup).
