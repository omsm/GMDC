# GMDC Checkpoint Config

Common commissioning tool for all GMDC site types (copied from `wb-old/IoT-Configuration`, refactored for profiles).

## Decisions locked

| Topic | Choice |
|-------|--------|
| Digitizer | **API only** - digitizer-app host/port + `POST /read_stable_weight` |
| Handheld RFID | **Full device** - make/model/IP/ID + check |
| Stack | Flask + WebView2/Chrome + vanilla JS |
| RFID | Zebra **mode=API** - app is HTTP server (`/rfid_data`); Mine-entry pattern |

## Checkpoint profiles

| Type | Family | Digitizer | TL / BB / Sensors |
|------|--------|-----------|-------------------|
| mines_entry, tracking_1, tracking_2, mines_exit | checkpoint | no | 1 / 1 / 1 |
| tare_wb, vadaghat_wb, gross_wb (uni) | weighbridge | yes | 2 / 2 / 3 |
| tare_wb, vadaghat_wb, gross_wb (bi) | weighbridge | yes | 4 / 2 / 3 |

Profiles live in `services/profiles.py`.

## Run

```powershell
cd C:\Users\bidyadhar.muduli\Desktop\GMDC\checkpoint-config
pip install -r requirements.txt
python app.py
```

Opens on http://127.0.0.1:8080 (same host/port the Zebra reader POSTs tags to: `/rfid_data`)

## Still TODO

- PDF report: checkpoint_type wording
- Digitizer-app must implement `POST /read_stable_weight` before live WB weight tests work
