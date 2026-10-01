"""Traffic light control via Modbus coils."""

from __future__ import annotations

import logging
from typing import Optional

from gmdc_common.hardware.io_controller import IOController

logger = logging.getLogger("gmdc_common.hardware.traffic_light")


class TrafficLight:
    """Traffic light (red / green / off). Name distinguishes entry vs exit."""

    def __init__(
        self,
        io: IOController,
        red_pin: Optional[int] = None,
        green_pin: Optional[int] = None,
        name: str = "entry",
    ):
        self.io = io
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.name = name
        self._state = "unknown"

    def set_red(self) -> bool:
        ok = True
        if self.green_pin is not None:
            ok = self.io.write_coil(self.green_pin, False) and ok
        if self.red_pin is not None:
            ok = self.io.write_coil(self.red_pin, True) and ok
        self._state = "red"
        logger.info("TrafficLight[%s] -> RED", self.name)
        return ok

    def set_green(self) -> bool:
        ok = True
        if self.red_pin is not None:
            ok = self.io.write_coil(self.red_pin, False) and ok
        if self.green_pin is not None:
            ok = self.io.write_coil(self.green_pin, True) and ok
        self._state = "green"
        logger.info("TrafficLight[%s] -> GREEN", self.name)
        return ok

    def set_off(self) -> bool:
        ok = True
        if self.red_pin is not None:
            ok = self.io.write_coil(self.red_pin, False) and ok
        if self.green_pin is not None:
            ok = self.io.write_coil(self.green_pin, False) and ok
        self._state = "off"
        logger.info("TrafficLight[%s] -> OFF", self.name)
        return ok

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state,
            "red_pin": self.red_pin,
            "green_pin": self.green_pin,
        }
