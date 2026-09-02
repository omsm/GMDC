"""Per-cycle transaction context for Tracking Point."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Transaction:
    rfid_tags: List[str] = field(default_factory=list)
    raw_tags: List[dict] = field(default_factory=list)
    validated_rfid: str = ""
    vehicle_no: str = ""
    truck_no: str = ""
    token_no: str = ""
    device_ip: str = ""
    truck_details: str = ""
    anpr_status: Optional[int] = None
    anpr_raw: Dict[str, Any] = field(default_factory=dict)
    front_image: str = ""
    anpr_image: str = ""
    top_image: Optional[str] = None
    started_at: Optional[str] = None
    granted: bool = False

    def start(self, tags: List[str], raw: Optional[List[dict]] = None) -> None:
        self.clear()
        self.rfid_tags = list(tags)
        self.raw_tags = list(raw or [])
        self.started_at = datetime.now(timezone.utc).isoformat()

    def clear(self) -> None:
        self.rfid_tags = []
        self.raw_tags = []
        self.validated_rfid = ""
        self.vehicle_no = ""
        self.truck_no = ""
        self.token_no = ""
        self.device_ip = ""
        self.truck_details = ""
        self.anpr_status = None
        self.anpr_raw = {}
        self.front_image = ""
        self.anpr_image = ""
        self.top_image = None
        self.started_at = None
        self.granted = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rfid_tags": self.rfid_tags,
            "validated_rfid": self.validated_rfid,
            "vehicle_no": self.vehicle_no,
            "truck_no": self.truck_no,
            "token_no": self.token_no,
            "device_ip": self.device_ip,
            "truck_details": self.truck_details,
            "anpr_status": self.anpr_status,
            "front_image": self.front_image,
            "anpr_image": self.anpr_image,
            "top_image": self.top_image,
            "started_at": self.started_at,
            "granted": self.granted,
        }


class TransactionStore:
    """Thread-safe wrapper around the active Transaction."""

    def __init__(self):
        self._lock = threading.RLock()
        self._txn = Transaction()

    @property
    def current(self) -> Transaction:
        with self._lock:
            return self._txn

    def clear(self) -> None:
        with self._lock:
            self._txn.clear()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return self._txn.to_dict()
