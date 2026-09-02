"""Re-export shared traffic light from gmdc_common."""

from gmdc_common.hardware.traffic_light import TrafficLight  # noqa: F401

__all__ = ["TrafficLight"]
