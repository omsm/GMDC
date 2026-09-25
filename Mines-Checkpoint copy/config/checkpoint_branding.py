"""
Checkpoint site profiles for Mines-Checkpoint.

One runtime serves mines_entry, tracking_1/2, and mines_exit. Behavior that
differs by site (OCI path defaults, boom-close body shape, dashboard labels)
is keyed by ``checkpoint_type`` in iot_configuration.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


# Profile ids used by checkpoint-config/services/profiles.py
CHECKPOINT_TYPES = (
    "mines_entry",
    "tracking_1",
    "tracking_2",
    "mines_exit",
)

# Accept legacy / alternate spellings from older JSON samples
_ALIASES = {
    "mines-entry": "mines_entry",
    "mine_entry": "mines_entry",
    "tracking_point_1": "tracking_1",
    "tracking-point-1": "tracking_1",
    "tracking_point_2": "tracking_2",
    "tracking-point-2": "tracking_2",
    "mines-exit": "mines_exit",
    "mine_exit": "mines_exit",
}


@dataclass(frozen=True)
class CheckpointBrand:
    checkpoint_type: str
    label: str  # idle display / dashboard title stem
    logo: str  # two-letter header badge
    service_name: str  # Flask /version service string
    # "entry" = truck_details + close-type body; "tracking" = images + top_image null
    boom_close_style: str
    # Default OCI relative paths when api_endpoints omit a key
    rfid_validate_path: str
    update_truck_path: str
    boom_close_path: str


_BRANDS: Dict[str, CheckpointBrand] = {
    "mines_entry": CheckpointBrand(
        checkpoint_type="mines_entry",
        label="Mines Entry",
        logo="ME",
        service_name="GMDC Mines Checkpoint",
        boom_close_style="entry",
        rfid_validate_path="/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag",
        update_truck_path="/ords/gmdc_dicsm/dlms_checkpoint/status_check",
        boom_close_path="/ords/gmdc_dicsm/dlms_checkpoint/boom-close",
    ),
    "tracking_1": CheckpointBrand(
        checkpoint_type="tracking_1",
        label="Tracking Point-1",
        logo="T1",
        service_name="GMDC Mines Checkpoint",
        boom_close_style="tracking",
        rfid_validate_path="/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag",
        update_truck_path="/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status",
        boom_close_path="/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close",
    ),
    "tracking_2": CheckpointBrand(
        checkpoint_type="tracking_2",
        label="Tracking Point-2",
        logo="T2",
        service_name="GMDC Mines Checkpoint",
        boom_close_style="tracking",
        rfid_validate_path="/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag",
        update_truck_path="/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status",
        boom_close_path="/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close",
    ),
    "mines_exit": CheckpointBrand(
        checkpoint_type="mines_exit",
        label="Mines Exit",
        logo="MX",
        service_name="GMDC Mines Checkpoint",
        boom_close_style="entry",
        rfid_validate_path="/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag",
        update_truck_path="/ords/gmdc_dicsm/dlms_checkpoint/status_check",
        boom_close_path="/ords/gmdc_dicsm/dlms_checkpoint/boom-close",
    ),
}


def normalize_checkpoint_type(raw: Optional[str]) -> str:
    key = (raw or "").strip().lower().replace(" ", "_")
    if not key:
        return "mines_entry"
    key = _ALIASES.get(key, key)
    if key in _BRANDS:
        return key
    return "mines_entry"


def get_brand(checkpoint_type: Optional[str]) -> CheckpointBrand:
    return _BRANDS[normalize_checkpoint_type(checkpoint_type)]
