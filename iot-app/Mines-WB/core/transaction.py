"""Per-cycle transaction data for tare weighbridge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TransactionStore:
    direction: str = ""
    rfid: str = ""
    vehicle_no: str = ""
    weight_kg: Optional[float] = None
    truck_details: str = ""
    tags: List[str] = field(default_factory=list)
    front_image: str = ""
    top_image: str = ""
    anpr_image: str = ""
    anpr_status: Optional[int] = None
    anpr_raw: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[str] = None
    notes: str = ""

    def begin(self) -> None:
        self.clear()
        self.started_at = datetime.now().isoformat(timespec="seconds")

    def clear(self) -> None:
        self.direction = ""
        self.rfid = ""
        self.vehicle_no = ""
        self.weight_kg = None
        self.truck_details = ""
        self.tags = []
        self.front_image = ""
        self.top_image = ""
        self.anpr_image = ""
        self.anpr_status = None
        self.anpr_raw = {}
        self.started_at = None
        self.notes = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "rfid": self.rfid,
            "vehicle_no": self.vehicle_no,
            "weight_kg": self.weight_kg,
            "truck_details": self.truck_details,
            "tags": list(self.tags),
            "front_image": self.front_image,
            "top_image": self.top_image,
            "anpr_image": self.anpr_image,
            "anpr_status": self.anpr_status,
            "started_at": self.started_at,
            "notes": self.notes,
        }
