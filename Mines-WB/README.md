# Mines-WB

**Version:** 1.20.0 (product **1.20** — see [`../version.md`](../version.md))

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

## Behaviour notes (1.20)

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

### Other
- OCI transport failure → LED `internet@ down`.
- Dashboard Reset holds `_manual_stop` until a new trip starts so background OCI loops exit.

Operator UI (Flow Details + Weight Read/Validation) matches the perfected TareWb dashboard.

Shared library: `gmdc_common`. Digitizer: `digitizer-app` / `digitizer-decoder`.
