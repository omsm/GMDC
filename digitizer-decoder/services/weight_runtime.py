"""Thread-safe live weight runtime for digitizer-decoder.

Stability validation (N identical readings) belongs to Mines-WB.
This runtime only:
  - tracks the latest current weight for MQTT / HTTP
  - maintains a local identical-reading counter for the dashboard UI (view only)
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from config.settings import READ_TIMEOUT_SEC, STABLE_READ_COUNT


class WeightRuntime:
    """Live weight store + UI-only identical-count display helper."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.connected = False
        self.current_weight: Optional[float] = None
        self.last_raw: str = ""
        self.last_raw_bytes: bytes = b""
        # UI view-only streak (not used to gate MQTT/HTTP/API consumers).
        self.view_weight: Optional[float] = None
        self.view_count_seen = 0
        self.view_count_required = STABLE_READ_COUNT
        self.read_timeout_sec = READ_TIMEOUT_SEC
        self.indexing: Optional[Dict[str, Any]] = None
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
            self.view_count_required = STABLE_READ_COUNT
            self.read_timeout_sec = READ_TIMEOUT_SEC

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self.connected = connected
            if not connected:
                self.current_weight = None
                self.view_weight = None
                self.view_count_seen = 0
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
            required = self.view_count_required

            # Dashboard streak only — never gates MQTT publish or HTTP responses.
            if weight <= 0:
                self.view_weight = None
                self.view_count_seen = 0
            elif self.view_weight is not None and weight == self.view_weight:
                self.view_count_seen += 1
                if self.view_count_seen > required:
                    self.view_count_seen = 1
            else:
                self.view_weight = weight
                self.view_count_seen = 1

            self._cond.notify_all()
        self._notify_update()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            required = self.view_count_required
            seen = self.view_count_seen
            view_ok = (
                self.view_weight is not None
                and self.view_weight > 0
                and seen >= required
            )
            return {
                "connected": self.connected,
                "current_weight": self.current_weight,
                # UI aliases (view-only; Mines-WB owns real stable validation).
                "stable": view_ok,
                "stable_weight": self.view_weight if view_ok else None,
                "stable_count": f"{seen}/{required}",
                "indexing_configured": bool(self.indexing),
                "last_raw": self.last_raw,
            }

    def current_weight_response(self) -> Dict[str, Any]:
        """
        Immediate current weight for HTTP callers.

        Does not wait for N identical readings — Mines-WB validates stability
        from the MQTT live stream (or by polling this endpoint itself).
        """
        with self._lock:
            if not self.connected:
                return {
                    "statusCode": 503,
                    "stable_weight": None,
                    "current_weight": None,
                    "message": "Digitizer serial not connected",
                }
            if self.current_weight is None:
                return {
                    "statusCode": 408,
                    "stable_weight": None,
                    "current_weight": None,
                    "message": "No weight reading yet",
                }
            weight = float(self.current_weight)
            return {
                "statusCode": 200,
                "stable_weight": weight,
                "current_weight": weight,
                "weight": weight,
                "message": "current weight (stability validated by Mines-WB)",
            }

    def wait_stable(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Backward-compatible alias — returns current weight with no wait."""
        return self.current_weight_response()
