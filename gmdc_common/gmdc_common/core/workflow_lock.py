"""Helpers for serializing workflow entry points (sensors, RFID, reset, I/O)."""

from __future__ import annotations

import threading
from typing import Any, Optional


def sensor_io_recovery_ok(io: Any, poller: Any) -> bool:
    """True only when sensor polls and the Modbus controller are both healthy."""
    if poller is not None:
        st = poller.get_status() if hasattr(poller, "get_status") else {}
        if not (st or {}).get("read_healthy", True):
            return False
    if io is None:
        return True
    if hasattr(io, "is_configured") and not io.is_configured():
        return False
    if hasattr(io, "get_status"):
        status = io.get_status() or {}
        if not status.get("healthy", False):
            return False
    if hasattr(io, "is_connected") and not io.is_connected():
        return False
    return True


class WorkflowLock:
    """Reentrant mutex for one lane workflow (timer, sensor, RFID, API reset)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()

    @property
    def rlock(self) -> threading.RLock:
        return self._lock

    def acquire_nonblocking(self) -> bool:
        return self._lock.acquire(blocking=False)

    def release(self) -> None:
        self._lock.release()
