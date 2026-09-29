# GMDC Checkpoint Config

Common commissioning tool for all GMDC site types (copied from `wb-old/IoT-Configuration`, refactored for profiles).

## Decisions locked

| Topic | Choice |
|-------|--------|
| Digitizer | **API only** - digitizer-app host/port + `POST /read_stable_weight` |
| Handheld RFID | **Full device** - make/model/IP/ID + check |
| Stack | Flask + WebView2/Chrome + vanilla JS |
| RFID | Zebra **mode=API** - app is HTTP server (`/rfid_data`); Mine-entry pattern |

## Site types

| Type | Direction | Digitizer | TL / BB / Sensors |
|------|-----------|-----------|-------------------|
| Checkpoint | — | no | 1 / 1 / 1 |
| Weigh Bridge | unidirectional | yes | 2 / 2 / 3 |
| Weigh Bridge | bidirectional | yes | 4 / 2 / 3 |

Profiles live in `services/profiles.py`. Older ids (`mines_entry`, `tracking_1`, `tare_wb`, …) load as Checkpoint or Weigh Bridge. RFID validation's first field selects the trip flow. API URLs are the same for both types.

`SECURED_WEB_VIEW` at the top of `app.py`: `False` opens Safari or Chrome; `True` opens a native window at the screen size and blocks right-click and copy/paste.

## Run

```powershell
cd C:\Users\bidyadhar.muduli\Desktop\GMDC\checkpoint-config
pip install -r requirements.txt
python app.py
```

Opens on http://127.0.0.1:8080 (same host/port the Zebra reader POSTs tags to: `/rfid_data`)

## Still TODO

- After the packaging script builds the executables, upload that build to GitHub releases on https://github.com/omsm/GMDC-Compiled-Application using the version number. Update checks already read `omsm/GMDC-Compiled-Application` releases.
- PDF report: checkpoint_type wording
- Digitizer-app must implement `POST /read_stable_weight` before live WB weight tests work
