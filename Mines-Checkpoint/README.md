# Mines-Checkpoint

**Version:** 1.20.0 (product **1.20** — see [`../version.md`](../version.md))

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

On Mac Mini production, use a local `pyenv` and [`../macos-services/README.md`](../macos-services/README.md) (`enable-mines-checkpoint.sh`). Project root must be `/Users/csm-gmdc/GMDC_IOT` (not Downloads).

## Behaviour notes (1.20)

- **RFID keepalive:** while IDLE, each Zebra `/rfid_management` queues cloud `login → mode → start` (`prepare_idle`) without blocking the HTTP 200.
- **OCI down:** transport failures publish LED `internet@ down`.
- **ANPR off:** optional front RTSP JPEG per lane under `images/<lane_id>/` (see 1.19).

Operator UI (Flow Details icons) matches the perfected Mines Entry dashboard. Branding follows `checkpoint_type`.

Shared library: `gmdc_common`.
