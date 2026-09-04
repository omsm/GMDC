# Tracking Point-1

Checkpoint runtime for GMDC tracking points. Same process flow as **Mine-entry**,
with tracking-point OCI API paths and boom-close image payload.

## Hardware

| Device | Count |
|--------|-------|
| RFID reader (Zebra API mode) | 1 |
| Handheld RFID | 1 (config + mobile fallback) |
| Front camera | via ANPR service (no local capture) |
| Traffic light | 1 |
| Boom barrier | 1 |
| Display (MQTT) | 1 |
| Sensor | 1 (entry) |
| I/O controller | 1 |

## Checkpoint OCI APIs

| Step | Path |
|------|------|
| RFID validate | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag` |
| Invalid truck (after ANPR) | `/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number` |
| Check status | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status` |
| Boom close | `/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close` |

Same as Mine-entry for **invalid-truck-number** (posted after every ANPR result `0`/`1`/`2` before grant or manual poll).

## Flow

```
IDLE → RFID → rfid-tag → Display → ANPR
     → invalid-truck-number
     → (match) boom-close → TL/boom
       OR (mismatch) check-status poll → boom-close → TL/boom
     → sensor clear → IDLE
```

Boom-close body:

```json
{
  "rfid": "D2030DBE",
  "device_ip": "IP244245525163",
  "front_image": "<from ANPR response front_image>",
  "anpr_image": "<from ANPR response anpr_image>",
  "top_image": null
}
```

- No local RTSP photo capture - `front_image` / `anpr_image` come from the ANPR `/api/detect` response (same as Mine-entry).
- `top_image` is always `null`.

## Setup

```powershell
cd C:\Users\bidyadhar.muduli\Desktop\GMDC
pip install -e .\gmdc_common
cd Tracking-point-1
pip install -r requirements.txt
copy .env.example .env
```

## Run

```powershell
cd C:\Users\bidyadhar.muduli\Desktop\GMDC\Tracking-point-1
python main.py
python -m unittest discover -s tests -v
```

Flask listens on `API_PORT` (default 8000). RFID reader POSTs tags to `/rfid_data`
(same pattern as Mine-entry; use port 8080 if matching Zebra push URL).

## Config

`iot_configuration.json` next to the app (or `IOT_CONFIG_PATH`).
Set `checkpoint_type: tracking_point_1`, one RFID under `rfids.entry_a`,
and the checkpoint `api_endpoints` above.
