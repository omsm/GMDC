"""
GMDC site profiles — two configuration types.

  checkpoint   — one entry sensor, one traffic light, one boom barrier
  weighbridge  — uni or bi direction (digitizer, entry/exit lights and sensors)

Trip behavior (entry / exit / tare / vadaghat / gross) is chosen later from
the first field of the RFID validation response, not from separate site URLs.
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
    "rfid",
    "handheld_rfid",
    "display",
    "io_controller",
    "voice",
)
_WEIGHBRIDGE_SECTIONS = (
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
    "checkpoint": _checkpoint("checkpoint", "Checkpoint"),
    "weighbridge": _weighbridge("weighbridge", "Weigh Bridge"),
}

# Older configs named a specific lane. They all use one of the two layouts above.
_LEGACY_CHECKPOINT_TYPES = {
    "mines_entry",
    "tracking_1",
    "tracking_2",
    "mines_exit",
    "mines-entry",
    "mine_entry",
    "mines-exit",
    "mine_exit",
    "tracking_point_1",
    "tracking-point-1",
    "tracking_point_2",
    "tracking-point-2",
}
_LEGACY_WEIGHBRIDGE_TYPES = {
    "tare_wb",
    "vadaghat_wb",
    "gross_wb",
    "tare",
    "tare-wb",
    "gross",
    "gross-wb",
    "vadaghat",
    "vadghat_wb",
    "vadhghat_wb",
}

# Operator-facing list for the layout / type picker
CHECKPOINT_TYPE_CHOICES: List[Dict[str, str]] = [
    {"id": p.id, "label": p.label, "family": p.family}
    for p in CHECKPOINT_PROFILES.values()
]

DEFAULT_CHECKPOINT_TYPE = "checkpoint"
DEFAULT_DIRECTION = "unidirectional"  # only used when profile.directional


def normalize_checkpoint_type(checkpoint_type: Optional[str]) -> str:
    """Map a stored or legacy id to ``checkpoint`` or ``weighbridge``."""
    key = (checkpoint_type or "").strip().lower().replace(" ", "_")
    if not key:
        return DEFAULT_CHECKPOINT_TYPE
    if key in CHECKPOINT_PROFILES:
        return key
    if key in _LEGACY_WEIGHBRIDGE_TYPES:
        return "weighbridge"
    if key in _LEGACY_CHECKPOINT_TYPES:
        return "checkpoint"
    return DEFAULT_CHECKPOINT_TYPE


def get_profile(checkpoint_type: Optional[str]) -> CheckpointProfile:
    return CHECKPOINT_PROFILES[normalize_checkpoint_type(checkpoint_type)]


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

# One URL list for both site types. Lane-specific paths (tracking vs entry,
# vadaghat-only) are not selected here; RFID validation's first field picks the flow.
_COMMON_API_FIELDS = _CHECKPOINT_API_FIELDS + (_API_WEIGHT, _API_VADHGHAT_ADJUST)


def api_endpoint_fields(checkpoint_type: Optional[str] = None) -> List[Dict[str, str]]:
    """API URL rows for the finish-flow editor. Same set for Checkpoint and Weigh Bridge."""
    del checkpoint_type  # kept so existing callers can still pass a type
    return [dict(f) for f in _COMMON_API_FIELDS]


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
