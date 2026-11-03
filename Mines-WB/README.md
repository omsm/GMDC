# Mines-WB

**Version:** 1.22.0 (product **1.22** — see [`../version.md`](../version.md))

Single weighbridge runtime for GMDC yard sites (uni-directional or bi-directional).

| `checkpoint_type` | Site |
|-------------------|------|
| `tare_wb` | Tare weighbridge |
| `vadaghat_wb` | Vadaghat (gross check) |
| `gross_wb` | Final gross weighbridge |

Trip logic also uses OCI `truck_details` prefixes `T|` / `V|` / `G|`. Sample configs: `samples/`.

```bash
pip install -e ../gmdc_common
pip install -r requirements.txt
cp .env.example .env
# Live weight: run digitizer-app / digitizer-decoder on :8800 (or DEMO_MODE=true)
python main.py
```

On Mac Mini production, use a local `pyenv` and [`../macos-services/README.md`](../macos-services/README.md) (`enable-mines-wb.sh`). Project root must be `/Users/csm-gmdc/GMDC_IOT` (not Downloads).

## Behaviour notes (1.22)

### I/O + sensors
- Strict Modbus FC map (no FC fallback). I/O down → popup, reconnect, lock trips until healthy.
- Sensors are realtime (no last-value hold). Poll rate: `polling.scan_interval` in `iot_configuration.json`.

### Exit before weighbridge
- Far-side exit cut with WB clear during positioning → invalidate → `error_start` + `weight_capture_issue` × 2 → exit grant → `application_reset` on IDLE.

### Post-ANPR weight lock
- Fresh 10-identical stable sample after RFID/ANPR; that kg stays fixed for APIs / WebUI / display for the rest of the trip.

### Bidirectional traffic lights / booms
- Config: traffic-light `on_state=green` (coil ON = green).
- **IDLE / Reset:** entry green both sides, exit red both sides, both booms open.
- **Free Pass:** all lights green, both booms open.
- **Direction set:** other side all red; depart boom closed; approach entry green.
- **On WB / exit grant:** approach boom closes; only the depart **exit** light goes green.

### Tare weight-confirm reject
- `weight_status=2` → POST `reset_checkpoint` (`device_ip`, `rfid_no`, `truck_details`), then exit (no weight-details / boom-close).

### Bi-dir tare vs gross OCI URLs
| Trip | Weight-details | Boom-close |
|------|----------------|------------|
| `T\|` | `weight_details_url_tare` (fallback: `weight_details_url`) | `boom_close_url_tare` (fallback: `boom_close_url`) |
| `G\|` | `weight_details_url` | `boom_close_url` |

### Idle FTP photo upload
On every IDLE (app start or after a trip), Mines-WB launches a background FTP uploader that sends everything under `images/` to:

- Host `10.80.118.100` (override `FTP_HOST`)
- User `ftpclient` / password from `FTP_PASSWORD`
- Remote folder `/Mines-WB` (`FTP_REMOTE_DIR`)

Successful uploads are deleted locally so the next IDLE only sends new files. Disable with `FTP_ENABLED=false`.

### Display MQTT (`display_ip`)
- Set `display.display_ip` in `iot_configuration.json` (bi: also `display_ip_b`).
- App always subscribes to `display_info/{display_ip}` and immediately publishes the board letter on `pcb_id/{display_ip}` (`a` uni / Entry A, `b` Entry B on bi).
- Transaction text uses `data_info/a` (and `data_info/b` on bi).

### Other
- OCI transport failure → LED `internet@ down`.
- Dashboard Reset holds `_manual_stop` until a new trip starts so background OCI loops exit.

Operator UI (Flow Details + Weight Read/Validation) matches the perfected TareWb dashboard.

Shared library: `gmdc_common`. Digitizer: `digitizer-app` / `digitizer-decoder`.
