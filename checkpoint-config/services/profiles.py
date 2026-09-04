"""
GMDC checkpoint profiles - single source of truth for which devices
each site type needs.

Families:
  checkpoint  - mines_entry, tracking_1, tracking_2, mines_exit
  weighbridge - tare_wb, vadaghat_wb, gross_wb  (uni or bi direction)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SensorSpec:
    key: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class DeviceSpec:
    key: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class CheckpointProfile:
    id: str
    label: str
    family: str  # "checkpoint" | "weighbridge"
    # Wizard sections (backend keys) in display order
    sections: Tuple[str, ...]
    sensors: Tuple[SensorSpec, ...]
    traffic_lights: Tuple[DeviceSpec, ...]
    boom_barriers: Tuple[DeviceSpec, ...]
    has_digitizer: bool = False
    has_handheld_rfid: bool = True
    # Weighbridges only: direction affects TL/BB/RFID cardinality
    directional: bool = False
    # Fixed Zebra RFID: one reader, or dual entry_a/entry_b when bi
    dual_rfid_when_bidirectional: bool = False


# ---------------------------------------------------------------------------
# Shared section tuples
# ---------------------------------------------------------------------------
_CHECKPOINT_SECTIONS = (
    "server",
    "rfid",
    "handheld_rfid",
    "display",
    "io_controller",
    "voice",
)
_WEIGHBRIDGE_SECTIONS = (
    "server",
    "rfid",
    "handheld_rfid",
    "camera",  # Top Camera RTSP (front optional / hidden in UI for WB)
    "display",
    "io_controller",
    "digitizer",
    "voice",
)

_ENTRY_SENSOR = SensorSpec("entry_sensor", "Entry Sensor")
_WB_SENSOR = SensorSpec("wb_sensor", "Weighbridge Sensor", required=False)
_EXIT_SENSOR = SensorSpec("exit_sensor", "Exit Sensor")

_TL_ENTRY = DeviceSpec("entry", "Entry Traffic Light")
_TL_EXIT = DeviceSpec("exit", "Exit Traffic Light")
_BB_ENTRY = DeviceSpec("entry", "Entry Boom Barrier")
_BB_EXIT = DeviceSpec("exit", "Exit Boom Barrier")


def _checkpoint(profile_id: str, label: str) -> CheckpointProfile:
    return CheckpointProfile(
        id=profile_id,
        label=label,
        family="checkpoint",
        sections=_CHECKPOINT_SECTIONS,
        sensors=(_ENTRY_SENSOR,),
        traffic_lights=(_TL_ENTRY,),
        boom_barriers=(_BB_ENTRY,),
        has_digitizer=False,
        has_handheld_rfid=True,
        directional=False,
        dual_rfid_when_bidirectional=False,
    )


def _weighbridge(profile_id: str, label: str) -> CheckpointProfile:
    return CheckpointProfile(
        id=profile_id,
        label=label,
        family="weighbridge",
        sections=_WEIGHBRIDGE_SECTIONS,
        sensors=(_ENTRY_SENSOR, _WB_SENSOR, _EXIT_SENSOR),
        traffic_lights=(_TL_ENTRY, _TL_EXIT),
        boom_barriers=(_BB_ENTRY, _BB_EXIT),
        has_digitizer=True,
        has_handheld_rfid=True,
        directional=True,
        dual_rfid_when_bidirectional=True,
    )


CHECKPOINT_PROFILES: Dict[str, CheckpointProfile] = {
    "mines_entry": _checkpoint("mines_entry", "Mines Entry"),
    "tracking_1": _checkpoint("tracking_1", "Tracking Point-1"),
    "tracking_2": _checkpoint("tracking_2", "Tracking Point-2"),
    "mines_exit": _checkpoint("mines_exit", "Mines Exit"),
    "tare_wb": _weighbridge("tare_wb", "Tare Weighbridge"),
    "vadaghat_wb": _weighbridge("vadaghat_wb", "Vadaghat Point (Gross Check WB)"),
    "gross_wb": _weighbridge("gross_wb", "Final Gross Weighbridge"),
}

# Operator-facing list for the layout / type picker
CHECKPOINT_TYPE_CHOICES: List[Dict[str, str]] = [
    {"id": p.id, "label": p.label, "family": p.family}
    for p in CHECKPOINT_PROFILES.values()
]

DEFAULT_CHECKPOINT_TYPE = "mines_entry"
DEFAULT_DIRECTION = "unidirectional"  # only used when profile.directional


def get_profile(checkpoint_type: Optional[str]) -> CheckpointProfile:
    key = (checkpoint_type or DEFAULT_CHECKPOINT_TYPE).strip()
    if key not in CHECKPOINT_PROFILES:
        return CHECKPOINT_PROFILES[DEFAULT_CHECKPOINT_TYPE]
    return CHECKPOINT_PROFILES[key]


def resolve_direction(profile: CheckpointProfile, direction: Optional[str]) -> str:
    if not profile.directional:
        return "unidirectional"
    d = (direction or DEFAULT_DIRECTION).strip().lower()
    if d not in ("unidirectional", "bidirectional"):
        return DEFAULT_DIRECTION
    return d


def nav_sections_for(
    checkpoint_type: Optional[str],
    *,
    enable_camera: bool = False,
) -> List[str]:
    """Backend section keys for wizard nav / completion."""
    profile = get_profile(checkpoint_type)
    sections = list(profile.sections)
    if enable_camera and "camera" not in sections:
        # Insert after rfid / handheld if present
        insert_at = 2
        if "handheld_rfid" in sections:
            insert_at = sections.index("handheld_rfid") + 1
        elif "rfid" in sections:
            insert_at = sections.index("rfid") + 1
        sections.insert(insert_at, "camera")
    return sections


def traffic_light_locations(
    checkpoint_type: Optional[str], direction: Optional[str]
) -> List[str]:
    """
    Flat location keys used by I/O forms.
    Checkpoint: ['entry']
    Uni WB: ['entry', 'exit']
    Bi WB:  ['entry_a.entry', 'entry_a.exit', 'entry_b.entry', 'entry_b.exit']
            (bidirectional JS already uses nested entry_a/entry_b - callers
             that need nested structure should use is_bidirectional_layout)
    """
    profile = get_profile(checkpoint_type)
    direction = resolve_direction(profile, direction)
    if profile.family == "checkpoint":
        return ["entry"]
    if direction == "bidirectional":
        return ["entry", "exit"]  # nested under entry_a/entry_b in JSON
    return ["entry", "exit"]


def boom_barrier_locations(checkpoint_type: Optional[str]) -> List[str]:
    profile = get_profile(checkpoint_type)
    if profile.family == "checkpoint":
        return ["entry"]
    return ["entry", "exit"]


def sensor_keys(checkpoint_type: Optional[str]) -> List[str]:
    return [s.key for s in get_profile(checkpoint_type).sensors]


def is_bidirectional_layout(
    checkpoint_type: Optional[str], direction: Optional[str]
) -> bool:
    profile = get_profile(checkpoint_type)
    return profile.directional and resolve_direction(profile, direction) == "bidirectional"


# ---------------------------------------------------------------------------
# API endpoints shown after Finish → Configure API-Endpoints?
# ---------------------------------------------------------------------------
# Each API has its own URL + username + password keys in api_endpoints.
_API_RFID = {
    "id": "rfid_validate",
    "label": "RFID Validation",
    "url_key": "rfid_validate_url",
    "base_key": "oci_base_url",
    "username_key": "rfid_validate_username",
    "password_key": "rfid_validate_password",
}
_API_ANPR = {
    "id": "anpr_detect",
    "label": "ANPR Validation",
    "url_key": "anpr_detect_url",
    "base_key": "anpr_base_url",
    "username_key": "anpr_detect_username",
    "password_key": "anpr_detect_password",
}
_API_INVALID = {
    "id": "invalid_truck",
    "label": "Invalid Truck Number Validation",
    "url_key": "invalid_truck_url",
    "base_key": "oci_base_url",
    "username_key": "invalid_truck_username",
    "password_key": "invalid_truck_password",
}
_API_STATUS = {
    "id": "status_check",
    "label": "Status Check (loop)",
    "url_key": "update_truck_url",
    "base_key": "oci_base_url",
    "username_key": "update_truck_username",
    "password_key": "update_truck_password",
}
_API_BOOM = {
    "id": "boom_close",
    "label": "Boom Close",
    "url_key": "boom_close_url",
    "base_key": "oci_base_url",
    "username_key": "boom_close_username",
    "password_key": "boom_close_password",
}
_API_RESET = {
    "id": "reset_checkpoint",
    "label": "Reset Checkpoint",
    "url_key": "reset_checkpoint_url",
    "base_key": "oci_base_url",
    "username_key": "reset_checkpoint_username",
    "password_key": "reset_checkpoint_password",
}
_API_WEIGHT = {
    "id": "weight_details",
    "label": "Weight Details",
    "url_key": "weight_details_url",
    "base_key": "oci_base_url",
    "username_key": "weight_details_username",
    "password_key": "weight_details_password",
}
_API_VADHGHAT_ADJUST = {
    "id": "vadhghat_weight_adjustment",
    "label": "Vadhghat Weight Adjustment",
    "url_key": "vadhghat_weight_adjustment_url",
    "base_key": "oci_base_url",
    "username_key": "vadhghat_weight_adjustment_username",
    "password_key": "vadhghat_weight_adjustment_password",
}

_CHECKPOINT_API_FIELDS = (
    _API_RFID,
    _API_ANPR,
    _API_INVALID,
    _API_STATUS,
    _API_BOOM,
    _API_RESET,
)
_WEIGHBRIDGE_API_FIELDS = (
    _API_RFID,
    _API_ANPR,
    _API_INVALID,
    _API_STATUS,
    _API_WEIGHT,
    _API_BOOM,
    _API_RESET,
)


def api_endpoint_fields(checkpoint_type: Optional[str] = None) -> List[Dict[str, str]]:
    """API URL rows to show in the finish-flow API endpoints editor."""
    profile = get_profile(checkpoint_type)
    fields = (
        _WEIGHBRIDGE_API_FIELDS
        if profile.family == "weighbridge"
        else _CHECKPOINT_API_FIELDS
    )
    result = [dict(f) for f in fields]
    if profile.id == "vadaghat_wb":
        result.append(dict(_API_VADHGHAT_ADJUST))
    return result


def profile_public_dict(checkpoint_type: Optional[str] = None) -> Dict[str, Any]:
    """JSON-serialisable profile info for the frontend."""
    profile = get_profile(checkpoint_type)
    return {
        "id": profile.id,
        "label": profile.label,
        "family": profile.family,
        "sections": list(profile.sections),
        "sensors": [
            {"key": s.key, "label": s.label, "required": s.required}
            for s in profile.sensors
        ],
        "traffic_lights": [
            {"key": t.key, "label": t.label, "required": t.required}
            for t in profile.traffic_lights
        ],
        "boom_barriers": [
            {"key": b.key, "label": b.label, "required": b.required}
            for b in profile.boom_barriers
        ],
        "has_digitizer": profile.has_digitizer,
        "has_handheld_rfid": profile.has_handheld_rfid,
        "directional": profile.directional,
        "dual_rfid_when_bidirectional": profile.dual_rfid_when_bidirectional,
        "api_endpoints": api_endpoint_fields(profile.id),
    }
