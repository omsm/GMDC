# Mines-Checkpoint

Single checkpoint runtime for GMDC yard sites:

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

Operator UI (Flow Details icons) matches the perfected Mines Entry dashboard. Branding (logo / idle display) follows `checkpoint_type`.

Shared library: `gmdc_common`.
