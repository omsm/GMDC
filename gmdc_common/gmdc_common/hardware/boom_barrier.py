"""Boom barrier control via Modbus coils."""

from __future__ import annotations

import logging
from typing import Optional

from gmdc_common.hardware.io_controller import IOController

logger = logging.getLogger("gmdc_common.hardware.boom_barrier")


class BoomBarrier:
    """Boom barrier (open / close). Name distinguishes entry vs exit."""

    def __init__(
        self,
        io: IOController,
        open_pin: Optional[int] = None,
        close_pin: Optional[int] = None,
        enabled: bool = True,
        name: str = "entry",
    ):
        self.io = io
        self.open_pin = open_pin
        self.close_pin = close_pin
        self.enabled = enabled
        self.name = name
        self._state = "unknown"

    def open(self) -> bool:
        if not self.enabled:
            logger.warning(
                "BoomBarrier[%s] disabled - open rejected (no fake success)",
                self.name,
            )
            return False
        if self.open_pin is None and self.close_pin is None:
            logger.error(
                "BoomBarrier[%s] no pins configured - open rejected", self.name
            )
            return False
        ok = True
        if self.close_pin is not None:
            ok = self.io.write_coil(self.close_pin, False) and ok
        if self.open_pin is not None:
            ok = self.io.write_coil(self.open_pin, True) and ok
        if ok:
            self._state = "open"
            logger.info("BoomBarrier[%s] -> OPEN", self.name)
        else:
            logger.error(
                "BoomBarrier[%s] OPEN write failed - state left as %s",
                self.name,
                self._state,
            )
        return ok

    def close(self) -> bool:
        if not self.enabled:
            logger.warning(
                "BoomBarrier[%s] disabled - close rejected (no fake success)",
                self.name,
            )
            return False
        if self.open_pin is None and self.close_pin is None:
            logger.error(
                "BoomBarrier[%s] no pins configured - close rejected", self.name
            )
            return False
        ok = True
        if self.open_pin is not None and self.close_pin is None:
            # Single-pin: LOW = closed
            ok = self.io.write_coil(self.open_pin, False) and ok
        else:
            if self.open_pin is not None:
                ok = self.io.write_coil(self.open_pin, False) and ok
            if self.close_pin is not None:
                ok = self.io.write_coil(self.close_pin, True) and ok
        if ok:
            self._state = "closed"
            logger.info("BoomBarrier[%s] -> CLOSED", self.name)
        else:
            logger.error(
                "BoomBarrier[%s] CLOSE write failed - state left as %s",
                self.name,
                self._state,
            )
        return ok

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state,
            "enabled": self.enabled,
            "open_pin": self.open_pin,
            "close_pin": self.close_pin,
        }
