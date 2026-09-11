"""Thread-safe live / stable weight runtime (from digitizer-app WeightRuntime)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from config.settings import READ_TIMEOUT_SEC, STABLE_READ_COUNT


class WeightRuntime:
    """Thread-safe live weight + stable-weight waiter used by HTTP / MQTT."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.connected = False
        self.current_weight: Optional[float] = None
        self.last_raw: str = ""
        self.last_raw_bytes: bytes = b""
        self.stable_weight: Optional[float] = None
        self.stable_count_seen = 0
        self.stable_count_required = STABLE_READ_COUNT
        self.read_timeout_sec = READ_TIMEOUT_SEC
        self.indexing: Optional[Dict[str, Any]] = None
        self._stable_latched = False
        self._cond = threading.Condition(self._lock)
        self._on_update: Optional[Callable[[], None]] = None

    def set_update_listener(self, cb: Optional[Callable[[], None]]) -> None:
        self._on_update = cb

    def _notify_update(self) -> None:
        cb = self._on_update
        if not cb:
            return
        try:
            cb()
        except Exception:
            pass

    def update_config(self, config: Dict[str, Any]) -> None:
        with self._lock:
            self.indexing = config.get("indexing") or None
            self.stable_count_required = STABLE_READ_COUNT
            self.read_timeout_sec = READ_TIMEOUT_SEC

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self.connected = connected
            if not connected:
                self.current_weight = None
                self.stable_weight = None
                self.stable_count_seen = 0
                self._stable_latched = False
                self.last_raw = ""
                self.last_raw_bytes = b""
            self._cond.notify_all()
        self._notify_update()

    def push_raw(self, raw_message: str, raw_bytes: bytes) -> None:
        """Update live raw display without requiring a parsed weight."""
        with self._lock:
            self.last_raw = raw_message
            self.last_raw_bytes = raw_bytes
        self._notify_update()

    def push_weight(self, weight: float, raw_message: str, raw_bytes: bytes) -> None:
        with self._lock:
            self.current_weight = weight
            self.last_raw = raw_message
            self.last_raw_bytes = raw_bytes
            required = self.stable_count_required

            if weight <= 0:
                self.stable_weight = None
                self.stable_count_seen = 0
                self._stable_latched = False
            elif self.stable_weight is not None and weight == self.stable_weight:
                self.stable_count_seen += 1
                if self.stable_count_seen >= required:
                    self._stable_latched = True
                # Wrap after required so UI never shows 11/10, 19/10, …
                if self.stable_count_seen > required:
                    self.stable_count_seen = 1
            else:
                self.stable_weight = weight
                self.stable_count_seen = 1
                self._stable_latched = False

            self._cond.notify_all()
        self._notify_update()

    def is_stable(self) -> bool:
        with self._lock:
            if (
                self._stable_latched
                and self.stable_weight is not None
                and self.stable_weight > 0
            ):
                return True
            return (
                self.stable_weight is not None
                and self.stable_weight > 0
                and self.stable_count_seen >= self.stable_count_required
            )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            stable = self.is_stable()
            return {
                "connected": self.connected,
                "current_weight": self.current_weight,
                "stable": stable,
                "stable_weight": self.stable_weight if stable else None,
                "stable_count": f"{self.stable_count_seen}/{self.stable_count_required}",
                "indexing_configured": bool(self.indexing),
                "last_raw": self.last_raw,
            }

    def wait_stable(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        deadline = time.monotonic() + (
            self.read_timeout_sec if timeout is None else timeout
        )
        with self._cond:
            while True:
                if not self.connected:
                    return {
                        "statusCode": 503,
                        "stable_weight": None,
                        "message": "Digitizer serial not connected",
                    }
                if self.is_stable():
                    return {
                        "statusCode": 200,
                        "stable_weight": self.stable_weight,
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {
                        "statusCode": 408,
                        "stable_weight": self.current_weight,
                        "message": (
                            f"Stable weight not reached "
                            f"({self.stable_count_seen}/{self.stable_count_required})"
                        ),
                    }
                self._cond.wait(timeout=min(remaining, 0.25))
