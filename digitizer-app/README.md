# GMDC Digitizer App

Standalone PySide6 desktop app: reads weighbridge digitizer over serial, calibrates weight extraction by ASCII byte indices, and serves a local HTTP API.

No dependency on other GMDC packages.

## Setup

```bash
pip install -r requirements.txt
python serial_ui.py
```

## Config (two rows)

| Row | Contents |
|-----|----------|
| 1 | Serial port (two columns: port/baud/data bits · parity/stop bits) |
| 2 | Raw data ASCII index calibration (capture → click bytes → preview) |

Local HTTP API always listens on `0.0.0.0:8800` (not configurable in UI).

### Setup order

1. On first run, Config opens: set **serial port** + **ASCII index calibration**, then Save.
2. Only after that does the dashboard open and read weight (index-based only - no free-form parse).

Calibration steps: Capture sample → pick R1/R3/R4 → Save.  
Stored in `config.json` as `indexing` + `calibration_sample_hex`.

## HTTP API

```bash
curl -X POST http://127.0.0.1:8800/read_stable_weight -H "Content-Type: application/json" -d "{}"
```

```json
{
  "statusCode": 200,
  "stable_weight": 43000.0
}
```
