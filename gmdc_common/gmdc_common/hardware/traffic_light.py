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
        relay_on_green: bool = False,
    ):
        self.io = io
        self.red_pin = red_pin
        self.green_pin = green_pin
        self.name = name
        # Single-coil relay polarity:
        #   relay_on_green True  → coil HIGH = green (NO), coil LOW = red (NC)
        #   relay_on_green False → coil HIGH = red (NO), coil LOW = green (NC)
        self.relay_on_green = bool(relay_on_green)
        self._state = "unknown"

    def _is_single_coil(self) -> bool:
        """One Modbus DO drives both colours via NO/NC contacts."""
        return self.green_pin is None and self.red_pin is not None

    def _write(self, address: Optional[int], value: bool) -> bool:
        if address is None:
            return True
        ok = bool(self.io.write_coil(address, value))
        if ok:
            logger.info(
                "TrafficLight[%s] write coil=%s value=%s ok",
                self.name,
                address,
                value,
            )
        else:
            logger.error(
                "TrafficLight[%s] write coil=%s value=%s FAILED "
                "(check Modbus link / DO address)",
                self.name,
                address,
                value,
            )
        return ok

    def set_red(self) -> bool:
        ok = True
        if self._is_single_coil():
            # Energize when NO = red; de-energize when NO = green.
            ok = self._write(self.red_pin, not self.relay_on_green) and ok
        else:
            if self.green_pin is not None:
                ok = self._write(self.green_pin, False) and ok
            if self.red_pin is not None:
                ok = self._write(self.red_pin, True) and ok
        self._state = "red"
        logger.info("TrafficLight[%s] -> RED", self.name)
        return ok

    def set_green(self) -> bool:
        ok = True
        if self._is_single_coil():
            ok = self._write(self.red_pin, self.relay_on_green) and ok
        else:
            if self.red_pin is not None:
                ok = self._write(self.red_pin, False) and ok
            if self.green_pin is not None:
                ok = self._write(self.green_pin, True) and ok
        self._state = "green"
        logger.info("TrafficLight[%s] -> GREEN", self.name)
        return ok

    def set_off(self) -> bool:
        ok = True
        if self.red_pin is not None:
            ok = self._write(self.red_pin, False) and ok
        if self.green_pin is not None:
            ok = self._write(self.green_pin, False) and ok
        self._state = "off"
        logger.info("TrafficLight[%s] -> OFF", self.name)
        return ok

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state,
            "red_pin": self.red_pin,
            "green_pin": self.green_pin,
            "relay_on_green": self.relay_on_green,
            "single_coil": self._is_single_coil(),
        }
