# TareWb-App

Tare weighbridge runtime for GMDC. Loads device config from
`checkpoint-config/iot_configuration.json` and uses `gmdc_common` for
I/O, sensors, traffic lights, boom barriers, RFID intake, display, and FSM engine.

## Setup

```powershell
cd C:\Users\bidyadhar.muduli\Desktop\GMDC
pip install -e .\gmdc_common
cd TareWb-App
pip install -r requirements.txt
copy .env.example .env
```

Ensure `checkpoint-config/iot_configuration.json` has `checkpoint_type: tare_wb`
(or set `IOT_CONFIG_PATH` / place a local `iot_configuration.json` in this folder).

## Run

```powershell
cd C:\Users\bidyadhar.muduli\Desktop\GMDC\TareWb-App
python main.py
```

Default demo mode (`DEMO_MODE=true`) uses Demo I/O + demo digitizer weight (12500 kg).

## Test cases (Excel)

```powershell
python tests/generate_test_cases_excel.py
```

Writes `docs/Tare_WB_Test_Cases.xlsx` (and `.csv`) with API, sensor, digitizer,
RFID, ANPR, status_check, camera, bidirectional, boom, E2E, and unit-map cases.

## Operator web app

Flask serves the Weighbridge dashboard on the same port as the runtime API
(default **8080** from `iot_configuration.json` `server.port`):

| URL | Page |
|-----|------|
| `http://localhost:8080/` | Operational dashboard |
| `http://localhost:8080/animated.html` | Live truck / weighbridge animation |

Live updates use **MQTT over WebSocket on port 9001** (in-process broker —
Mosquitto is not required). Open the dashboard on the weighbridge PC IP, e.g.
`http://10.30.1.102:8080/`. The browser connects to `ws://10.30.1.102:9001`.

Allow inbound **TCP 9001** on the PC firewall if you open the UI from another machine.

| MQTT topic | Direction | Payload |
|------------|-----------|---------|
| `wb_frontend/position` | backend → browser | `-1`..`5` |
| `wb_frontend/display` | backend → browser | text |
| `wb_frontend/digitizer` | backend → browser | weight kg |
| `wb_frontend/status` | backend → browser | JSON step/status/message |
| `wb_frontend/rfid` | backend → browser | JSON `{rfid, truck_number}` |
| `wb_frontend/device_status` | backend → browser | JSON device badges |
| `wb_frontend/request_status` | browser → backend | ask for retained snapshot |
| `wb_frontend/reset_application` | browser → backend | reset FSM to IDLE |
| `wb_frontend/free_pass` | browser → backend | open all lights/booms; IDLE after exit sensor |

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Operator dashboard (`index.html`) |
| GET | `/animated.html` | Animation page |
| GET | `/version` | `{ "version": "0.1.0" }` |
| GET | `/api/update/status` | Updater badge (always idle for this runtime) |
| GET | `/api/status` | FSM + hardware snapshot |
| POST | `/rfid_data` | Zebra tag push |
| POST | `/rfid_data_from_mobile_app` | Handheld `{"rfid_data":"..."}` |
| POST | `/api/reset` | Force IDLE |
| POST | `/api/free-pass` | Open all lights/booms; IDLE after exit sensor |
| POST | `/api/simulate-entry` | Demo: entry sensor ON |
| POST | `/api/simulate-wb` | Demo: WB sensor ON |
| POST | `/api/simulate-exit` | Demo: exit sensor ON |

## Flow (summary)

IDLE (entry green/open, exit red/closed) → entry occupied → MOVE FORWARD →
WB occupied → close entry / weigh → if weight > 5 t start RFID →
OCI validate → ANPR (`anpr_status` 0/1/2):

| `anpr_status` | Path |
|---------------|------|
| **1** | top photo → invalid-truck → weight → weight-details → boom-close(current `truck_details`) → exit |
| **0** | top photo → invalid-truck → `status_check` loop → weight → weight-details → boom-close(`truck_details`) → exit |
| **2** | same as **0** (`status_check` loop); when `vehicleStatus`=1 continue like **1** |

Manual loop calls `update_truck_url` (`status_check`) every 5 seconds:
`vehicleStatus` 0=retry, 1=continue (same as anpr_status=1), 2=abort. HTTP/statusCode 200 alone
does not continue the flow.

### Bidirectional approach

When `wb_type` is `bidirectional`:

- ENTRY sensor edge selects `direction=ENTRY_A`; EXIT sensor edge while IDLE
  selects `direction=ENTRY_B`. Neither edge starts RFID.
- After the digitizer returns weight > 5 t, the selected direction's reader
  performs login → mode setup → start.
- On the first RFID push, scanning is stopped immediately before validation.
- The opposite reader is stopped before the selected reader starts.
- ENTRY_A completes crossing at the EXIT sensor; ENTRY_B completes at ENTRY.

## Voice

Uses the same WAV pack layout as `wb-old/Weighbridge-App/voice`
(`information/`, `error/`, `weight_ton/`, `weight_kg/`, `VNO/`).

Playback backends:
- **Windows** — `winsound`
- **macOS** — `afplay` (built-in; Mac mini / MacBook)
- **Linux** — `aplay` or `paplay`

`TareWb-App/voice` is a junction to that pack (or place your own copy).
Gated by `voice.enabled` + `voice.validated` in IoT config (same as wb-old).

| Moment | Clip |
|--------|------|
| Startup | `welcome.wav` |
| Positioning / exit wait | `forward.wav` every 5s |
| Weighing | `please_wait.wav` (if present) |
| Final tare weight | `tare_final_weight` + Siren + ton/kg |
| RFID miss / fail | `rfid_not_found` / `error_start`+`g7` |
| ANPR fail | `error_start`+`g9` |
| Manual reset | `application_reset.wav` |
