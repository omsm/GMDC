# Mines-WB

Single weighbridge runtime for GMDC yard sites:

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
# Live weight: run digitizer-app on :8800 (or DEMO_MODE=true)
python main.py
```

Operator UI (Flow Details + Weight Read/Validation icons) matches the perfected TareWb dashboard.

Shared library: `gmdc_common`. Digitizer: `digitizer-app`.
