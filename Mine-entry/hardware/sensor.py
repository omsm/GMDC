"""Re-export shared sensor poller from gmdc_common."""

from gmdc_common.hardware.sensor import SensorPoller  # noqa: F401

__all__ = ["SensorPoller"]
