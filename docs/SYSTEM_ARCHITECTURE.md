# System Architecture

## Runtime topology

```text
checkpoint-config ──writes──► iot_configuration.json
                                      │
gmdc_common ◄──── imported by ────────┼── Mines-Checkpoint
                                      ├── Mines-WB
                                      └── checkpoint-config

Zebra FX ──HTTP POST /rfid_data──► runtime Flask API
Modbus TCP :502 ──────────────────► lights, barriers, sensors
ANPR service /api/detect ─────────► runtime workflow
GMDC OCI APIs ────────────────────► validation/status/boom/reset/weight
MQTT TCP :1883 ◄──────────────────► runtime/display/digitizer services
MQTT WebSocket :9001 ◄────────────► browser dashboards
Digitizer HTTP :8800 ────────────► Mines-WB (API mode)
```

Startup may ensure a local Mosquitto broker. The application publishes over
MQTT TCP; browser clients use the broker WebSocket listener.

## Shared library boundaries

`gmdc_common` owns reusable device and service primitives:

- `hardware/io_controller.py`: strict Modbus FC1/FC2 reads and FC5/FC6 writes
- `hardware/sensor.py`: polling, edge handling, realtime sensor state
- `hardware/traffic_light.py` and `hardware/boom_barrier.py`: honest output
  state; failed writes do not claim success
- `services/rfid_control.py`: Zebra cloud login, mode, start/stop control
- display, voice, HTTP, logging, and pymodbus compatibility helpers
- generic state-machine utilities

Application-specific workflow, state transitions, OCI payloads, and dashboards
remain in the family runtime.

## Mines-Checkpoint

`Mines-Checkpoint/main.py` loads one settings object per lane and creates one
application context per lane. `LaneTable` routes RFID events by listening port
and reader IP. The application starts one shared Flask API plus per-lane
hardware/service contexts.

The production configuration has four lanes:

| Lane | Typical ID | RFID port | Display topic |
|---|---|---:|---|
| Mines Entry | `mines_entry` | 8001 | `data_info/a` |
| Traffic IN | `traffic_in` | 8002 | `data_info/b` |
| Traffic OUT | `traffic_out` | 8003 | `data_info/c` |
| Mines Exit | `mines_exit` | 8004 | `data_info/d` |

The exact values must be read from the deployed JSON; this table describes the
current repository configuration and is not a replacement for commissioning.

Checkpoint flow is broadly:

```text
RFID → OCI validation → optional ANPR → grant/status polling
     → boom/light action → sensor clear → IDLE
```

## Mines-WB

The weighbridge runtime handles entry/exit sensors, digitizer weight, RFID,
ANPR, OCI calls, weight confirmation, boom barriers, and lane reset. It supports
unidirectional and bidirectional layouts. After RFID and ANPR, Mines-WB owns a
fresh stable-weight capture and locks that transaction weight; later live
digitizer changes do not replace the locked value.

## Modbus and sensor safety

Function-code behavior is strict:

- configured read FC1 means FC1 coils only
- configured read FC2 means FC2 discrete inputs only
- configured write FC5 means single-coil writes only
- configured write FC6 means single-register writes only
- no FC1/FC2 fallback is allowed

Sensor values are realtime-only. A failed read returns no valid sample and does
not create a synthetic value or a ghost edge. I/O health loss locks the
workflow, aborts/blocks unsafe transactions, and recovers only after the
controller is healthy.

For the current Modbus debounce implementation, a soft Modbus exception is
counted. At the second soft failure on the digital-input path, the socket is
reconnected and the input is read again. A successful fresh read updates the
sensor and clears the soft-failure state. A failed fresh read becomes the
third failure and marks I/O unhealthy. Hard transport exceptions still resync
immediately.

## RFID integration

The verified Zebra CUSTOM JSON in
`gmdc_common/gmdc_common/services/rfid_control.py` is a fixed integration
contract and must not be changed casually. Important verified parameters are
antennas 5 and 6, TID memory selection, pointer 6, length 24, mask `800600`,
31/31 transmit power, and per-antenna reporting.

The runtime additionally uses the reader's HTTP/API mode, configured reader IP,
reader/cloud controls, and the runtime `/rfid_data` endpoint. These surrounding
settings are lane-specific and must not be confused with the fixed CUSTOM
reader profile.

## MQTT contracts

### Display

- Runtime publishes display text to the configured `data_info/<pcb>` topic.
- Display handshake uses `display_info/<display_ip>` and publishes the PCB
  letter on `pcb_id/<display_ip>`.
- Browser dashboards use MQTT WebSocket port 9001.

### Digitizer

- Digitizer MQTT weight topic: `gmdc/digitizer/weight`.
- Status topic: `gmdc/digitizer/status`.
- Request topic: `gmdc/digitizer/request`.
- Decoder/backend publishes current readings, including zero/repeated values.
- Stability ownership belongs to Mines-WB; decoder streak display is
  informational.

## External API contracts

The runtimes call configurable GMDC OCI endpoints for RFID validation,
invalid-truck handling, status polling, boom close, reset, and weighbridge
weight details. ANPR is a separate `/api/detect` service. Endpoint paths and
credentials are configuration concerns; do not infer site-specific values from
defaults.
