"""
Handheld RFID validation for the GMDC config tool.

Check & Save waits until the handheld POSTs:
  {"rfid_data": "<non-blank tag>"}
to /rfid_data_from_mobile_app (same contract as Mine-entry).
Blank / whitespace-only rfid_data does not complete the test.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_WAIT_SECONDS = 60


class HandheldRfidService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset_status_unlocked()

    def _reset_status_unlocked(self) -> None:
        self._status: Dict[str, Any] = {
            "testing": False,
            "test_complete": False,
            "time_remaining": 0,
            "rfid_received": False,
            "rfid_data": None,
            "message": None,
            "skipped": False,
        }
        self._deadline = 0.0
        self._pending_meta: Dict[str, Any] = {}

    def stop(self) -> None:
        with self._lock:
            was_testing = self._status.get("testing")
            self._status["testing"] = False
            if was_testing and not self._status.get("test_complete"):
                self._status["test_complete"] = True
                self._status["message"] = "Handheld RFID test cancelled"
                self._status["time_remaining"] = 0

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            if self._status.get("testing") and not self._status.get("test_complete"):
                remaining = max(0, int(self._deadline - time.time()))
                self._status["time_remaining"] = remaining
                if remaining <= 0:
                    self._status["testing"] = False
                    self._status["test_complete"] = True
                    self._status["rfid_received"] = False
                    self._status["message"] = (
                        "Timed out waiting for handheld POST "
                        '{"rfid_data": "<tag>"} to /rfid_data_from_mobile_app'
                    )
            return dict(self._status)

    def start_wait(
        self,
        data: Optional[dict] = None,
        wait_seconds: int = DEFAULT_WAIT_SECONDS,
    ) -> Dict[str, Any]:
        """Validate identity fields and start waiting for a live tag POST."""
        data = data or {}
        make = str(data.get("make") or "").strip()
        model = str(data.get("model") or "").strip()
        device_id = str(data.get("device_id") or data.get("id") or "").strip()
        ip = str(data.get("ip") or "").strip()
        port = str(data.get("port") or "").strip()
        enabled = data.get("enabled", True)

        if not enabled:
            with self._lock:
                self._reset_status_unlocked()
                self._status.update(
                    {
                        "testing": False,
                        "test_complete": True,
                        "skipped": True,
                        "message": "Handheld RFID disabled (skipped)",
                    }
                )
            return {
                "status": 200,
                "message": "Handheld RFID disabled (skipped)",
                "skipped": True,
                "testing": False,
                "test_complete": True,
            }

        if not make or not model:
            return {
                "status": 400,
                "message": "Handheld RFID make and model are required",
            }
        if not device_id and not ip:
            return {
                "status": 400,
                "message": "Provide handheld device_id or IP address",
            }

        try:
            timeout = int(wait_seconds)
        except (TypeError, ValueError):
            timeout = DEFAULT_WAIT_SECONDS
        if timeout < 10:
            timeout = 10
        if timeout > 180:
            timeout = 180

        with self._lock:
            self._reset_status_unlocked()
            self._pending_meta = {
                "make": make,
                "model": model,
                "device_id": device_id,
                "ip": ip,
                "port": port,
                "enabled": True,
            }
            self._deadline = time.time() + timeout
            self._status.update(
                {
                    "testing": True,
                    "test_complete": False,
                    "time_remaining": timeout,
                    "rfid_received": False,
                    "rfid_data": None,
                    "skipped": False,
                    "message": (
                        "Waiting for handheld POST "
                        '{"rfid_data": "<tag>"} on /rfid_data_from_mobile_app'
                    ),
                }
            )

        logger.info(
            "Handheld RFID wait started (%ss) for %s %s",
            timeout,
            make,
            model,
        )
        return {
            "status": 200,
            "message": (
                f"Waiting up to {timeout}s for handheld to POST "
                '{"rfid_data": "<non-blank tag>"} to /rfid_data_from_mobile_app'
            ),
            "testing": True,
            "test_complete": False,
            "time_remaining": timeout,
            "make": make,
            "model": model,
            "device_id": device_id,
            "ip": ip,
            "port": port,
        }

    def receive_rfid_payload(self, payload: Any) -> Dict[str, Any]:
        """
        Accept body from handheld. Valid success body:
          {"rfid_data": "<non-blank>"}
        Blank / missing rfid_data does not complete the wait.
        """
        if not isinstance(payload, dict):
            return {
                "http_status": 500,
                "body": {
                    "status": "500",
                    "message": "Error: JSON body must be an object with rfid_data",
                    "rfid_data": None,
                },
            }

        if "rfid_data" not in payload:
            return {
                "http_status": 500,
                "body": {
                    "status": "500",
                    "message": "Error: rfid_data key is required",
                    "rfid_data": None,
                },
            }

        raw = payload.get("rfid_data")
        if raw is None or str(raw).strip() == "":
            logger.info("Handheld POST rejected: blank rfid_data")
            return {
                "http_status": 500,
                "body": {
                    "status": "500",
                    "message": "Error: rfid_data value is blank",
                    "rfid_data": None,
                },
            }

        rfid_str = str(raw).strip()

        with self._lock:
            if not self._status.get("testing") or self._status.get("test_complete"):
                return {
                    "http_status": 500,
                    "body": {
                        "status": "500",
                        "message": "Error: No handheld RFID test is waiting",
                        "rfid_data": None,
                    },
                }

            self._status.update(
                {
                    "testing": False,
                    "test_complete": True,
                    "time_remaining": 0,
                    "rfid_received": True,
                    "rfid_data": rfid_str,
                    "message": f"Handheld RFID received: {rfid_str}",
                }
            )
            meta = dict(self._pending_meta)

        logger.info("Handheld RFID accepted rfid_data=%s", rfid_str)
        return {
            "http_status": 200,
            "body": {
                "status": "200",
                "message": "RFID received by checkpoint-config",
                "rfid_data": rfid_str,
                **{k: v for k, v in meta.items() if v},
            },
        }


handheld_rfid_service = HandheldRfidService()
