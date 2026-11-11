# Data and Configuration Schema

## Database status

There is no database engine, migration system, ORM model, or SQL schema in the
current repository. Do not invent a database schema for this project. Runtime
state is in memory; deployment configuration is JSON/environment based.

## Configuration documents

The main persisted document is `iot_configuration.json`. It may contain either
a single configuration object or a top-level `lanes` array.

Common top-level/lane sections include:

| Section/key | Purpose |
|---|---|
| `checkpoint_type` | Canonical layout family or legacy alias |
| `lane_id`, `lane_name`, `wb_type` | Physical location identity/label |
| `device_ip` | Runtime/site computer identity used by APIs |
| `server` | Application host/port metadata |
| `rfids.entry_a`, `rfids.entry_b` | Reader IP, port, API mode, credentials, and validation metadata |
| `camera.front` / weighbridge camera settings | RTSP camera configuration |
| `display` | MQTT broker, display IP, PCB mode, and topics |
| `digitizer` | Serial/API/MQTT digitizer settings |
| `io_controller` | Modbus connection, slave, function codes, and address maps |
| `api_endpoints` | OCI/ANPR endpoint overrides and endpoint credentials |
| `polling` | Sensor polling interval and related settings |
| `voice` | Voice asset/backend configuration |
| `lanes` | Multiple checkpoint lane objects |

The exact accepted fields are implemented by each runtime's settings loader and
the commissioning tool. Configuration examples are not a substitute for
validating a deployed site's addresses and credentials.

## Runtime state

Each lane has in-memory state-machine/workflow state, sensor occupancy and edge
state, I/O health, RFID transaction data, ANPR result, and (for Mines-WB) a
locked transaction weight. This state is not a durable database record.

Images are stored on the filesystem under runtime image directories and may be
uploaded by the FTP background service. Logs are rotating files.

## API data contracts

The public runtime API includes:

- `POST /rfid_data`: Zebra/API RFID tag intake
- `POST /rfid_data_from_mobile_app`: mobile/manual RFID intake where enabled
- `GET /api/status`: current operator/device/workflow status
- update/status endpoints exposed by the runtime dashboard

The precise request and response payloads are implemented in
`Mines-Checkpoint/api/`, `Mines-WB/api/`, and their workflow/service modules.
Do not document undocumented fields as guaranteed contracts.

## MQTT data contracts

Display:

- `data_info/<pcb_letter>`: display text
- `display_info/<display_ip>`: display handshake/input
- `pcb_id/<display_ip>`: PCB identity response

Digitizer:

- `gmdc/digitizer/weight`: current weight readings
- `gmdc/digitizer/status`: decoder/device status
- `gmdc/digitizer/request`: read/control requests

Payload shapes should be changed only with coordinated runtime, decoder, and
dashboard updates.

## Secrets

Reader credentials, API credentials, RTSP credentials, FTP credentials, and
tokens may occur in `.env` or commissioning JSON. They are operational secrets,
not schema examples. Keep them out of documentation, commits, and diagnostics.
