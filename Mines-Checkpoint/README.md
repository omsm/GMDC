# Mines-Checkpoint

**Version:** 1.22.0 (product **1.22** — see [`../version.md`](../version.md))

Single checkpoint runtime for GMDC yard sites. One process can run multiple lanes from `lanes` in `iot_configuration.json` (Mines Entry, Traffic IN/OUT, Mines Exit).

| `checkpoint_type` | Site |
|-------------------|------|
| `mines_entry` | Mines Entry |
| `tracking_1` | Tracking Point-1 |
| `tracking_2` | Tracking Point-2 |
| `mines_exit` | Mines Exit |

Set type + OCI paths in `iot_configuration.json` (or `IOT_CONFIG_PATH`). Sample files live in `samples/`.

```bash
pip install -e ../gmdc_common
pip install -r requirements.txt
cp .env.example .env
python main.py
```

**Crossing timer (`.env`):** after RFID/ANPR grant (boom open, TL green), if the truck does not clear the sensor the lane auto-resets to IDLE after:

```env
VEHICLE_CROSSING_TIMEOUT_SEC=60
```

Change that value and restart the app. `.env` overrides per-lane `vehicle_crossing_timeout` in `iot_configuration.json`.

On Mac Mini production, use a local `pyenv` and [`../macos-services/README.md`](../macos-services/README.md) (`enable-mines-checkpoint.sh`). Project root must be `/Users/csm-gmdc/GMDC_IOT` (not Downloads).

## Behaviour notes (1.22)

- **I/O + sensors:** strict Modbus FCs; I/O down → popup / reconnect / lock trips; sensors realtime (no last-value hold). Poll: `polling.scan_interval`.
- **Idle FTP photo upload:** on every IDLE (start or after a trip), a background FTP uploader sends all files under `images/` (including lane folders) to `10.80.118.100` as user `ftpclient`, remote `/Mines-Checkpoint`. Configure via `FTP_*` in `.env`. Successful uploads are removed locally.
- **Display MQTT:** set `display.display_ip` per lane in `iot_configuration.json`. App subscribes to `display_info/{display_ip}` and immediately publishes that lane’s letter on `pcb_id/{display_ip}`:
  - Mines Entry → `a` · Traffic IN → `b` · Traffic OUT → `c` · Mines Exit → `d`
  - Transaction text uses matching `data_info/a|b|c|d`
- **RFID keepalive:** while IDLE, each Zebra `/rfid_management` queues cloud `login → mode → start` (`prepare_idle`) without blocking the HTTP 200.
- **OCI down:** transport failures publish LED `internet@ down`.
- **ANPR off:** optional front RTSP JPEG per lane under `images/<lane_id>/` (see 1.19).

Operator UI (Flow Details icons) matches the perfected Mines Entry dashboard. Branding follows `checkpoint_type`.

Shared library: `gmdc_common`.
