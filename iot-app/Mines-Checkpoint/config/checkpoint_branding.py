"""
Checkpoint site profile for Mines-Checkpoint.

checkpoint-config stores ``checkpoint`` (older files may say mines_entry,
tracking_1, tracking_2, or mines_exit). Those all use the same OCI paths.
The first field of the RFID validation ``truck_details`` string (T / CE / X)
selects the trip flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_CHECKPOINT_ALIASES = {
    "mines-entry",
    "mine_entry",
    "mines_entry",
    "tracking_1",
    "tracking_2",
    "tracking_point_1",
    "tracking-point-1",
    "tracking_point_2",
    "tracking-point-2",
    "mines-exit",
    "mine_exit",
    "mines_exit",
    "checkpoint",
}


@dataclass(frozen=True)
class CheckpointBrand:
    checkpoint_type: str
    label: str
    logo: str
    service_name: str
    boom_close_style: str
    rfid_validate_path: str
    update_truck_path: str
    boom_close_path: str


_COMMON = CheckpointBrand(
    checkpoint_type="checkpoint",
    label="Checkpoint",
    logo="CP",
    service_name="GMDC Mines Checkpoint",
    boom_close_style="entry",
    rfid_validate_path="/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag",
    update_truck_path="/ords/gmdc_dicsm/dlms_checkpoint/status_check",
    boom_close_path="/ords/gmdc_dicsm/dlms_checkpoint/boom-close",
)


def normalize_checkpoint_type(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower().replace(" ", "_")
    if not key or key in _CHECKPOINT_ALIASES:
        return "checkpoint"
    return "checkpoint"


def get_brand(checkpoint_type: Optional[str]) -> CheckpointBrand:
    normalize_checkpoint_type(checkpoint_type)
    return _COMMON
