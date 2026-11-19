# Project Overview

## Purpose

GMDC Yard IoT coordinates vehicle movement through mine-yard checkpoints and
weighbridges. It integrates Zebra RFID readers, Modbus TCP I/O, traffic lights,
boom barriers, sensors, ANPR, GMDC OCI APIs, displays, voice prompts, and
weighbridge digitizers.

## Product flow

```text
Mines Entry → Tare WB → Tracking Point-1 → Vadaghat/Gross WB
            → Tracking Point-2 → Final Gross WB → Mines Exit
```

The two current runtime families are:

- `Mines-Checkpoint`: mines entry, tracking, traffic, and mines-exit checkpoint
  flows. One process can host multiple lanes.
- `Mines-WB`: tare, Vadaghat, and gross weighbridge flows, including
  unidirectional and bidirectional layouts.

The RFID validation response, especially the first `truck_details` field,
selects the transaction flow. A physical checkpoint name is not automatically
a separate software profile.

## Repository map

| Path | Responsibility |
|---|---|
| `gmdc_common/` | Installable shared Python library: Modbus, sensors, RFID control, display, voice, HTTP, FSM utilities |
| `checkpoint-config/` | Commissioning UI; writes `iot_configuration.json` |
| `Mines-Checkpoint/` | Checkpoint runtime and multi-lane dashboard/API |
| `Mines-WB/` | Weighbridge runtime and weight/vehicle workflow |
| `digitizer-app/` | Serial digitizer reader and stable-weight HTTP API |
| `digitizer-decoder/` | Web/API or MQTT digitizer implementation |
| `mqtt_broker_setup/` | Local Mosquitto setup on TCP 1883 and WebSocket 9001 |
| `macos-services/` | macOS LaunchAgent service management |

`Mine-entry/`, `Tracking-point-1/`, and `TareWb-App/` are legacy/reference
copies. New work should target the current family runtimes.

## Configuration model

Configuration is JSON plus environment variables. `Mines-Checkpoint` accepts a
top-level `lanes` array; each lane has its own device IP, RFID reader,
listening port, I/O controller, display, camera, API settings, and lane ID.
`checkpoint-config/services/profiles.py` currently exposes two canonical layout
profiles: `checkpoint` and `weighbridge`. Legacy IDs normalize to one of those
families.

## Current declared version

Product version **1.24** is declared in [`version.md`](../version.md). Runtime
builds read per-app `VERSION` files (e.g. Mines-Checkpoint and Mines-WB
**1.24.0**). The digitizer-decoder keeps its own component semver in
`digitizer-decoder/VERSION` (see that README). Operator display error codes are
listed in [`ERRORS.md`](ERRORS.md).
