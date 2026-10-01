# gmdc_common

Shared library for the GMDC site flow applications:

```
Mines entry → Tare WB → Tracking point-1 → Vadaghat (gross check WB)
           → Tracking point-2 → Final gross WB → Mines exit
```

## Packages

| Package | Contents |
|---------|----------|
| `gmdc_common.hardware` | Modbus I/O, traffic light, boom barrier, sensor poller, RFID reader |
| `gmdc_common.services` | MQTT/console display, Zebra RFID cloud control, Basic-Auth HTTP client |
| `gmdc_common.core` | Generic table-driven `BaseStateMachine` |
| `gmdc_common.utils` | pymodbus version-compat helpers, rotating-file logging |

Application-specific workflow, state/event enums, and OCI payload shaping stay in each app.

## Install

From the GMDC workspace root:

```powershell
pip install -e .\gmdc_common
```

Then any app can:

```python
from gmdc_common.hardware import create_io_controller, TrafficLight, BoomBarrier
from gmdc_common.services import create_display_service, RFIDCloudControl
from gmdc_common.core import BaseStateMachine
```
