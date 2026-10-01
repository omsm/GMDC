import json
import os
import sys
from datetime import datetime
from typing import Optional, List

try:
    from config import (
        ENABLE_CAMERA_CONFIGURATION,
        ENABLE_WB_SENSOR_TEST_SKIP,
        BIDIRECTIONAL_ENTRY_KEYS,
        BIDIRECTIONAL_ENTRY_LABEL,
        BIDIRECTIONAL_ENTRY_A_KEY,
        BIDIRECTIONAL_ENTRY_B_KEY,
        LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY,
        LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY,
    )
except ImportError:
    ENABLE_CAMERA_CONFIGURATION = True
    ENABLE_WB_SENSOR_TEST_SKIP = False
    BIDIRECTIONAL_ENTRY_A_KEY = "entry_a"
    BIDIRECTIONAL_ENTRY_B_KEY = "entry_b"
    BIDIRECTIONAL_ENTRY_KEYS = (BIDIRECTIONAL_ENTRY_A_KEY, BIDIRECTIONAL_ENTRY_B_KEY)
    BIDIRECTIONAL_ENTRY_LABEL = {
        BIDIRECTIONAL_ENTRY_A_KEY: "ENTRY A",
        BIDIRECTIONAL_ENTRY_B_KEY: "ENTRY B",
    }
    LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY = "direction_a"
    LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY = "direction_b"


def bidirectional_entry_label(entry_key: str) -> str:
    """Human-readable label for bidirectional JSON entry key (entry_a / entry_b)."""
    return BIDIRECTIONAL_ENTRY_LABEL.get(entry_key, str(entry_key))


_SECTION_LABELS = {
    "rfid": "RFID",
    "handheld_rfid": "Handheld RFID",
    "camera": "Camera",
    "display": "Display",
    "io_controller": "I/O Controller",
    "digitizer": "Digitizer",
    "voice": "Audio",
    "server": "Server",
}


def section_label(section: str) -> str:
    """User-facing name for a wizard section key."""
    key = str(section or "").strip()
    if key in _SECTION_LABELS:
        return _SECTION_LABELS[key]
    return key.replace("_", " ").replace("-", " ").strip().title() or "section"


def _rename_dict_key(parent: dict, old_key: str, new_key: str) -> None:
    if not isinstance(parent, dict) or old_key not in parent:
        return
    if new_key not in parent:
        parent[new_key] = parent.pop(old_key)
    else:
        parent.pop(old_key, None)


def _migrate_legacy_bidirectional_direction_keys(config: dict) -> None:
    """Rename legacy direction_a / direction_b keys to entry_a / entry_b in saved JSON."""
    if not isinstance(config, dict):
        return
    pairs = (
        (LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY, BIDIRECTIONAL_ENTRY_A_KEY),
        (LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY, BIDIRECTIONAL_ENTRY_B_KEY),
    )
    rfids = config.get("rfids")
    if isinstance(rfids, dict):
        for old_k, new_k in pairs:
            _rename_dict_key(rfids, old_k, new_k)
    io = config.get("io_controller")
    if not isinstance(io, dict):
        return
    tl = io.get("traffic_lights")
    if not isinstance(tl, dict):
        return
    for old_k, new_k in pairs:
        _rename_dict_key(tl, old_k, new_k)
        direct = tl.get("direct")
        if isinstance(direct, dict):
            _rename_dict_key(direct, old_k, new_k)
        relay = tl.get("relay")
        if isinstance(relay, dict):
            relay.pop(old_k, None)

# Handle PyInstaller executable paths for config files
# Config files should be saved in the executable directory, not temp folder
if getattr(sys, 'frozen', False):
    # Running as compiled executable - save config next to exe
    base_path = os.path.dirname(sys.executable)
else:
    # Running as script - save in current directory
    base_path = os.path.dirname(os.path.abspath(__file__))
    base_path = os.path.dirname(base_path)  # Go up from services/ to project root

CONFIG_FILE = os.path.join(base_path, 'iot_configuration.json')
FINAL_CONFIG_FILE = os.path.join(base_path, 'iot_configuration.json')

# JSON sensor keys (UI: Entry sensor, WB Sensor, Exit Sensor)
_SENSOR_KEY_PAIRS = (
    ("entry_sensor", "sensor1"),
    ("wb_sensor", "sensor2"),
    ("exit_sensor", "sensor3"),
)


def _sanitize_wb_sensor_validated(config: dict) -> None:
    """Coerce wb_sensor validated null to false when WB skip is disabled in config.py."""
    if ENABLE_WB_SENSOR_TEST_SKIP:
        return
    if not isinstance(config, dict):
        return
    io = config.get("io_controller")
    if not isinstance(io, dict):
        return
    sensors = io.get("sensors")
    if not isinstance(sensors, dict):
        return
    wb = sensors.get("wb_sensor")
    if not isinstance(wb, dict):
        wb = sensors.get("sensor2")
    if isinstance(wb, dict) and wb.get("validated") is None:
        wb["validated"] = False


def _normalize_io_sensors(config: dict) -> dict:
    """Map legacy sensor1/2/3 keys to entry_sensor/wb_sensor/exit_sensor."""
    io = config.get("io_controller")
    if not isinstance(io, dict):
        return config
    sensors = io.get("sensors")
    if not isinstance(sensors, dict):
        return config
    defaults = DEFAULT_CONFIG["io_controller"]["sensors"]
    normalized = {}
    for new_key, legacy_key in _SENSOR_KEY_PAIRS:
        if new_key in sensors:
            normalized[new_key] = sensors[new_key]
        elif legacy_key in sensors:
            normalized[new_key] = sensors[legacy_key]
        else:
            normalized[new_key] = defaults[new_key]
    io["sensors"] = normalized
    config["io_controller"] = io
    return config

# Canonical top-level key order for exported iot_configuration.json
DIGITIZER_TRANSIENT_KEYS = frozenset({
    "calibration_sample_hex",
    "sample_hex",
    "topic_status",  # hardcoded in Mines-WB + digitizer-decoder backends
})

DIGITIZER_NUMERIC_DEFAULTS = {
    "baud_rate": "9600",
    "bytesize": "8",
    "stopbits": "1",
    "timeout": "10",
    "stable_count": "5",
}


def _sanitize_digitizer_section(digitizer: dict) -> dict:
    """
    Normalize digitizer config before persisting to iot_configuration.json.

    - Drops transient keys used only during calibration validation (not for runtime).
    - Fills empty numeric fields so Weighbridge-App can parse the file.
    """
    if not isinstance(digitizer, dict):
        return digitizer
    out = dict(digitizer)
    for key in DIGITIZER_TRANSIENT_KEYS:
        out.pop(key, None)
    for key, default in DIGITIZER_NUMERIC_DEFAULTS.items():
        val = out.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            out[key] = default
    return out


def _strip_camera_if_disabled(config: dict) -> None:
    """Remove camera section from exported config when the wizard is disabled."""
    if not ENABLE_CAMERA_CONFIGURATION and isinstance(config, dict):
        config.pop("camera", None)


CANONICAL_CONFIG_KEY_ORDER = (
    "schema_version",
    "checkpoint_type",
    "wb_type",
    "device_ip",
    "server",
    "rfid",
    "rfids",
    "handheld_rfid",
    "camera",
    "display",
    "digitizer",
    "io_controller",
    "status",
    "voice",
    "api_endpoints",
    "setup_info",
    "audio",
)

if not ENABLE_CAMERA_CONFIGURATION:
    CANONICAL_CONFIG_KEY_ORDER = tuple(
        key for key in CANONICAL_CONFIG_KEY_ORDER if key != "camera"
    )


def get_wb_type_from_dict(config: dict) -> str:
    """Read wb_type with legacy weighbridge_layout fallback."""
    if not isinstance(config, dict):
        return "unidirectional"
    wb_type = config.get("wb_type") or config.get("weighbridge_layout", "unidirectional")
    if wb_type not in ("unidirectional", "bidirectional"):
        return "unidirectional"
    return wb_type


def migrate_wb_type_key(config: dict) -> None:
    """Migrate legacy weighbridge_layout to wb_type."""
    if not isinstance(config, dict):
        return
    if "weighbridge_layout" in config and "wb_type" not in config:
        config["wb_type"] = config["weighbridge_layout"]
    config.pop("weighbridge_layout", None)


def migrate_gmdc_api_defaults(config: dict) -> None:
    """
    Migrate legacy wb-old serial digitizer / TCP RFID into GMDC API defaults.
    Safe to run repeatedly; only rewrites clearly-legacy shapes.
    """
    if not isinstance(config, dict):
        return
    if "schema_version" not in config:
        config["schema_version"] = 1
    from services.profiles import normalize_checkpoint_type

    config["checkpoint_type"] = normalize_checkpoint_type(config.get("checkpoint_type"))

    dig = config.get("digitizer")
    if isinstance(dig, dict):
        port_val = str(dig.get("port") or "").strip().upper()
        looks_serial = port_val.startswith("COM") or dig.get("baud_rate") is not None
        mode = str(dig.get("mode") or "").strip().lower()

        if mode == "mqtt":
            dig.setdefault("broker_host", dig.get("broker_host") or dig.get("host") or "127.0.0.1")
            dig.setdefault("broker_port", dig.get("broker_port") or "1883")
            dig.setdefault(
                "topic_weight",
                dig.get("topic_weight") or dig.get("topic_publish") or "gmdc/digitizer/weight",
            )
            dig.setdefault(
                "topic_request",
                dig.get("topic_request") or dig.get("topic_subscribe") or "gmdc/digitizer/request",
            )
            dig.setdefault("timeout", dig.get("timeout") or "30")
            dig.setdefault("stable_count", dig.get("stable_count") or "10")
            dig.pop("topic_status", None)
        else:
            needs_api_reset = mode not in ("api",) or (
                looks_serial and not str(dig.get("host") or "").strip()
            )
            if needs_api_reset:
                dig["mode"] = "api"
                if not dig.get("host"):
                    dig["host"] = ""
                if looks_serial or not str(dig.get("port") or "").isdigit():
                    dig["port"] = "8100"
                dig.setdefault("path", "/read_stable_weight")
                dig.setdefault("timeout", "30")
                dig.setdefault("stable_count", "10")
                # Drop serial-only noise from the live API section
                for key in (
                    "baud_rate",
                    "bytesize",
                    "parity",
                    "stopbits",
                    "conversion_method",
                    "indexing",
                ):
                    dig.pop(key, None)
                if dig.get("validated") and not dig.get("host"):
                    dig["validated"] = False

    rfid = config.get("rfid")
    if isinstance(rfid, dict):
        mode = str(rfid.get("mode") or "").strip().upper()
        if mode in ("", "CLIENT", "SERVER"):
            rfid["mode"] = "API"
            rfid.setdefault("username", "admin")
            rfid.setdefault("password", "")
            rfid["note"] = (
                "API mode: tags via POST /rfid_data; "
                "cloud login/mode/start/stop via HTTPS"
            )
            if mode in ("CLIENT", "SERVER") and rfid.get("validated"):
                # Force re-check under API cloud login
                rfid["validated"] = False
        rfid.setdefault("api_port", "8080")

    rfids = config.get("rfids")
    if isinstance(rfids, dict):
        for dir_key in ("entry_a", "entry_b"):
            reader = rfids.get(dir_key)
            if not isinstance(reader, dict):
                continue
            mode = str(reader.get("mode") or "").strip().upper()
            if mode in ("", "CLIENT", "SERVER"):
                reader["mode"] = "API"
                reader.setdefault("username", "admin")
                reader.setdefault("password", "")
                reader["note"] = (
                    "API mode: tags via POST /rfid_data; "
                    "cloud login/mode/start/stop via HTTPS"
                )
                if mode in ("CLIENT", "SERVER") and reader.get("validated"):
                    reader["validated"] = False
            reader.setdefault("api_port", "8081" if dir_key == "entry_b" else "8080")

    if "handheld_rfid" not in config or not isinstance(config.get("handheld_rfid"), dict):
        config["handheld_rfid"] = {
            "enabled": True,
            "ip": "",
            "port": "",
            "make": "",
            "model": "",
            "device_id": "",
            "validated": False,
        }


def order_config_keys(config: dict) -> dict:
    """Return config with stable top-level key order (RFID after server)."""
    if not isinstance(config, dict):
        return {}
    ordered = {}
    seen = set()
    for key in CANONICAL_CONFIG_KEY_ORDER:
        if key in config:
            ordered[key] = config[key]
            seen.add(key)
    for key, value in config.items():
        if key not in seen:
            ordered[key] = value
    return ordered


CANONICAL_RFID_READER_KEY_ORDER = (
    "ip",
    "port",
    "api_port",
    "mode",
    "make",
    "model",
    "username",
    "password",
    "validated",
    "manual_match_start",
    "manual_match_length",
    "manual_match_sample",
    "note",
)


def order_rfid_reader_keys(reader: dict) -> dict:
    """Return RFID reader dict with stable field order."""
    if not isinstance(reader, dict):
        return {}
    ordered = {}
    seen = set()
    for key in CANONICAL_RFID_READER_KEY_ORDER:
        if key in reader:
            ordered[key] = reader[key]
            seen.add(key)
    for key, value in reader.items():
        if key not in seen:
            ordered[key] = value
    return ordered


def order_rfids_section(rfids: dict) -> dict:
    """Return rfids section with ordered entry_a / entry_b readers."""
    if not isinstance(rfids, dict):
        return {}
    ordered = {}
    seen = set()
    for dir_key in ("entry_a", "entry_b"):
        if dir_key in rfids:
            value = rfids[dir_key]
            if isinstance(value, dict):
                ordered[dir_key] = order_rfid_reader_keys(value)
            else:
                ordered[dir_key] = value
            seen.add(dir_key)
    for key, value in rfids.items():
        if key not in seen:
            ordered[key] = value
    return ordered


def normalize_rfid_sections(config: dict) -> None:
    """Normalize key order for unidirectional rfid and bidirectional rfids readers."""
    if not isinstance(config, dict):
        return
    if isinstance(config.get("rfid"), dict):
        config["rfid"] = order_rfid_reader_keys(config["rfid"])
    if isinstance(config.get("rfids"), dict):
        config["rfids"] = order_rfids_section(config["rfids"])


def _normalize_io_pin(pin) -> Optional[str]:
    """Normalize pin for comparison; return None if empty or non-numeric."""
    if pin is None:
        return None
    text = str(pin).strip()
    if not text:
        return None
    try:
        return str(int(text))
    except ValueError:
        return None


def _add_io_pin(entries: List[tuple], pin, label: str) -> None:
    normalized = _normalize_io_pin(pin)
    if normalized is not None:
        entries.append((normalized, label))


def _device_uses_io_pin(validated) -> bool:
    """Only count pins for devices that are actively configured (validated true)."""
    return validated is True


def _boom_location_enabled(loc_data: dict) -> bool:
    if not isinstance(loc_data, dict):
        return False
    return loc_data.get("enabled") is True


def _tl_side_active(tl: dict, location: str, direction: Optional[str] = None) -> bool:
    if not isinstance(tl, dict):
        return False
    if direction in ("entry_a", "entry_b"):
        dir_meta = tl.get(direction)
        if not isinstance(dir_meta, dict):
            return False
        side_meta = dir_meta.get(location)
        if isinstance(side_meta, dict):
            return _device_uses_io_pin(side_meta.get("validated"))
        return False
    side_meta = tl.get(location)
    if isinstance(side_meta, dict):
        return _device_uses_io_pin(side_meta.get("validated"))
    return False


def _collect_tl_direct_pins(
    entries: List[tuple], tl: dict, wb_type: str
) -> None:
    direct_section = tl.get("direct") if isinstance(tl, dict) else {}
    if not isinstance(direct_section, dict):
        return
    if wb_type == "bidirectional":
        for direction in ("entry_a", "entry_b"):
            dir_label = bidirectional_entry_label(direction)
            dir_data = direct_section.get(direction)
            if not isinstance(dir_data, dict):
                continue
            for loc in ("entry", "exit"):
                if not _tl_side_active(tl, loc, direction):
                    continue
                loc_data = dir_data.get(loc)
                if not isinstance(loc_data, dict):
                    continue
                loc_label = loc.capitalize()
                _add_io_pin(
                    entries, loc_data.get("red_pin"), f"{dir_label} {loc_label} red"
                )
                _add_io_pin(
                    entries, loc_data.get("green_pin"), f"{dir_label} {loc_label} green"
                )
    else:
        for loc in ("entry", "exit"):
            if not _tl_side_active(tl, loc):
                continue
            loc_data = direct_section.get(loc)
            if not isinstance(loc_data, dict):
                continue
            loc_label = loc.capitalize()
            _add_io_pin(entries, loc_data.get("red_pin"), f"{loc_label} traffic light red")
            _add_io_pin(entries, loc_data.get("green_pin"), f"{loc_label} traffic light green")


def _collect_tl_relay_pins(entries: List[tuple], tl: dict, wb_type: str) -> None:
    relay_section = tl.get("relay") if isinstance(tl, dict) else {}
    if not isinstance(relay_section, dict):
        return
    if wb_type == "bidirectional":
        for direction in ("entry_a", "entry_b"):
            dir_label = bidirectional_entry_label(direction)
            dir_data = relay_section.get(direction)
            if not isinstance(dir_data, dict):
                continue
            for loc in ("entry", "exit"):
                if not _tl_side_active(tl, loc, direction):
                    continue
                loc_data = dir_data.get(loc)
                if not isinstance(loc_data, dict):
                    continue
                loc_label = loc.capitalize()
                _add_io_pin(
                    entries, loc_data.get("pin"), f"{dir_label} {loc_label} traffic light relay"
                )
        return
    for loc in ("entry", "exit"):
        if not _tl_side_active(tl, loc):
            continue
        loc_data = relay_section.get(loc)
        if not isinstance(loc_data, dict):
            continue
        loc_label = loc.capitalize()
        _add_io_pin(entries, loc_data.get("pin"), f"{loc_label} traffic light relay")


def _collect_boom_direct_pins(entries: List[tuple], direct_section: dict) -> None:
    if not isinstance(direct_section, dict):
        return
    for loc in ("entry", "exit"):
        loc_data = direct_section.get(loc)
        if not _boom_location_enabled(loc_data):
            continue
        loc_label = loc.capitalize()
        _add_io_pin(entries, loc_data.get("open_pin"), f"{loc_label} boom open")
        _add_io_pin(entries, loc_data.get("close_pin"), f"{loc_label} boom close")


def _collect_boom_relay_pins(entries: List[tuple], relay_section: dict) -> None:
    if not isinstance(relay_section, dict):
        return
    for loc in ("entry", "exit"):
        loc_data = relay_section.get(loc)
        if not _boom_location_enabled(loc_data):
            continue
        loc_label = loc.capitalize()
        _add_io_pin(entries, loc_data.get("pin"), f"{loc_label} boom relay")


def collect_io_input_pins(io: dict) -> List[tuple]:
    """Return [(normalized_pin, human_label), ...] for digital input (sensor) pins only."""
    if not isinstance(io, dict):
        return []
    entries: List[tuple] = []
    sensors = io.get("sensors") or {}
    sensor_labels = (
        ("entry_sensor", "Entry sensor"),
        ("wb_sensor", "WB sensor"),
        ("exit_sensor", "Exit sensor"),
    )
    for key, label in sensor_labels:
        sensor = sensors.get(key) if isinstance(sensors, dict) else None
        if isinstance(sensor, dict) and _device_uses_io_pin(sensor.get("validated")):
            _add_io_pin(entries, sensor.get("pin"), label)
    return entries


def collect_io_output_pins(io: dict, wb_type: str) -> List[tuple]:
    """Return [(normalized_pin, human_label), ...] for digital output (TL + boom) pins only."""
    if not isinstance(io, dict):
        return []
    if wb_type not in ("unidirectional", "bidirectional"):
        wb_type = "unidirectional"

    entries: List[tuple] = []
    output_mode = io.get("output_mode")
    tl = io.get("traffic_lights") or {}
    bb = io.get("boom_barriers") or {}
    if not output_mode:
        output_mode = tl.get("mode") if isinstance(tl, dict) else None
    if not output_mode:
        output_mode = bb.get("mode") if isinstance(bb, dict) else None
    if output_mode not in ("direct", "relay"):
        output_mode = "direct"

    if output_mode == "direct":
        _collect_tl_direct_pins(entries, tl if isinstance(tl, dict) else {}, wb_type)
        _collect_boom_direct_pins(entries, bb.get("direct") if isinstance(bb, dict) else {})
    else:
        _collect_tl_relay_pins(entries, tl if isinstance(tl, dict) else {}, wb_type)
        _collect_boom_relay_pins(entries, bb.get("relay") if isinstance(bb, dict) else {})

    return entries


def collect_io_controller_pins(io: dict, wb_type: str) -> List[tuple]:
    """Return all input + output pins (legacy helper)."""
    return collect_io_input_pins(io) + collect_io_output_pins(io, wb_type)


def _format_pin_duplicate_message(duplicates: dict, register_label: str) -> Optional[str]:
    if not duplicates:
        return None
    parts = []
    for pin in sorted(duplicates, key=lambda p: int(p)):
        labels = duplicates[pin]
        parts.append(f"pin {pin} ({', '.join(labels)})")
    if len(parts) == 1:
        return f"Duplicate {register_label} pin used by: {parts[0]}."
    return f"Duplicate {register_label} pins: " + "; ".join(parts) + "."


def _find_duplicate_pin_groups(entries: List[tuple]) -> dict:
    by_pin: dict = {}
    for pin, label in entries:
        by_pin.setdefault(pin, []).append(label)
    return {pin: labels for pin, labels in by_pin.items() if len(labels) > 1}


def validate_io_pin_uniqueness(io: dict, wb_type: str) -> Optional[str]:
    """Return error if input or output register pins are duplicated within their group."""
    input_dups = _find_duplicate_pin_groups(collect_io_input_pins(io))
    output_dups = _find_duplicate_pin_groups(collect_io_output_pins(io, wb_type))

    messages = []
    input_msg = _format_pin_duplicate_message(input_dups, "input")
    if input_msg:
        messages.append(input_msg)
    output_msg = _format_pin_duplicate_message(output_dups, "output")
    if output_msg:
        messages.append(output_msg)
    if not messages:
        return None
    return " ".join(messages)


_BIDIRECTIONAL_TL_DEFAULT_PINS = {
    "entry_a": {
        "entry": {"red_pin": "0", "green_pin": "1"},
        "exit": {"red_pin": "2", "green_pin": "3"},
    },
    "entry_b": {
        "entry": {"red_pin": "4", "green_pin": "5"},
        "exit": {"red_pin": "6", "green_pin": "7"},
    },
}


def _tl_side_meta_template() -> dict:
    return {"make": "", "model": "", "validated": False}


def _tl_side_validated_skipped(tl: dict, direction: str, side: str) -> bool:
    """True when traffic light setup was debug-skipped (validated is null)."""
    if not isinstance(tl, dict):
        return False
    dmeta = tl.get(direction)
    if not isinstance(dmeta, dict):
        return False
    side_meta = dmeta.get(side)
    return isinstance(side_meta, dict) and side_meta.get("validated") is None


def _resolve_tl_side_validated(side_meta: dict, legacy_meta: Optional[dict]):
    """Preserve tri-state validated (true / null / false) when migrating TL metadata."""
    if isinstance(side_meta, dict):
        existing = side_meta.get("validated")
        if existing is True or existing is None:
            return existing
    if isinstance(legacy_meta, dict):
        legacy_v = legacy_meta.get("validated")
        if legacy_v is True or legacy_v is None:
            return legacy_v
    return False


def _bidirectional_tl_structure_complete(tl: dict) -> bool:
    """True when direct.entry_a/b each have entry/exit pin mapping (skipped sides exempt)."""
    if not isinstance(tl, dict):
        return False
    direct = tl.get("direct")
    if not isinstance(direct, dict):
        return False
    for direction in ("entry_a", "entry_b"):
        ddir = direct.get(direction)
        if not isinstance(ddir, dict):
            return False
        for side in ("entry", "exit"):
            if _tl_side_validated_skipped(tl, direction, side):
                continue
            pins = ddir.get(side)
            if not isinstance(pins, dict):
                return False
            if not str(pins.get("red_pin", "")).strip() or not str(pins.get("green_pin", "")).strip():
                return False
    return True


def _strip_unidirectional_traffic_light_keys(tl: dict) -> None:
    if not isinstance(tl, dict):
        return
    for key in ("entry", "exit"):
        tl.pop(key, None)
    direct = tl.get("direct")
    if isinstance(direct, dict):
        direct.pop("entry", None)
        direct.pop("exit", None)
    relay = tl.get("relay")
    if isinstance(relay, dict):
        relay.pop("entry", None)
        relay.pop("exit", None)


def _migrate_traffic_lights_to_bidirectional(tl: dict) -> None:
    """Ensure bidirectional traffic_lights shape; migrate legacy uni entry/exit when present."""
    if not isinstance(tl, dict):
        return

    if _bidirectional_tl_structure_complete(tl):
        _strip_unidirectional_traffic_light_keys(tl)
        return

    direct = tl.setdefault("direct", {})
    if not isinstance(direct, dict):
        direct = {}
        tl["direct"] = direct

    legacy_direct_entry = direct.pop("entry", None) if isinstance(direct.get("entry"), dict) else None
    legacy_direct_exit = direct.pop("exit", None) if isinstance(direct.get("exit"), dict) else None
    legacy_meta_entry = tl.pop("entry", None) if isinstance(tl.get("entry"), dict) else None
    legacy_meta_exit = tl.pop("exit", None) if isinstance(tl.get("exit"), dict) else None

    relay = tl.setdefault("relay", {})
    if isinstance(relay, dict):
        legacy_relay_entry = relay.pop("entry", None) if isinstance(relay.get("entry"), dict) else None
        legacy_relay_exit = relay.pop("exit", None) if isinstance(relay.get("exit"), dict) else None
    else:
        legacy_relay_entry = legacy_relay_exit = None
        relay = {}
        tl["relay"] = relay

    for direction in ("entry_a", "entry_b"):
        defaults = _BIDIRECTIONAL_TL_DEFAULT_PINS[direction]
        dir_direct = direct.setdefault(direction, {})
        if not isinstance(dir_direct, dict):
            dir_direct = {}
            direct[direction] = dir_direct

        for side in ("entry", "exit"):
            pin_defaults = defaults[side]
            side_direct = dir_direct.setdefault(side, {})
            if not isinstance(side_direct, dict):
                side_direct = {}
                dir_direct[side] = side_direct

            legacy_pins = None
            if direction == "entry_a":
                if side == "entry" and legacy_direct_entry:
                    legacy_pins = legacy_direct_entry
                elif side == "exit" and legacy_direct_exit:
                    legacy_pins = legacy_direct_exit

            if legacy_pins:
                for pin_key in ("red_pin", "green_pin", "pin"):
                    if pin_key in legacy_pins and legacy_pins[pin_key] not in (None, ""):
                        if pin_key == "pin":
                            side_direct.setdefault("red_pin", legacy_pins["pin"])
                        else:
                            side_direct[pin_key] = legacy_pins[pin_key]

            side_direct.setdefault("red_pin", pin_defaults["red_pin"])
            side_direct.setdefault("green_pin", pin_defaults["green_pin"])

            dir_meta = tl.setdefault(direction, {})
            if not isinstance(dir_meta, dict):
                dir_meta = {}
                tl[direction] = dir_meta
            side_meta = dir_meta.setdefault(side, _tl_side_meta_template())
            if not isinstance(side_meta, dict):
                side_meta = _tl_side_meta_template()
                dir_meta[side] = side_meta

            legacy_meta = None
            if direction == "entry_a":
                legacy_meta = legacy_meta_entry if side == "entry" else legacy_meta_exit
            if legacy_meta:
                if legacy_meta.get("make") not in (None, ""):
                    side_meta["make"] = legacy_meta.get("make", "")
                if legacy_meta.get("model") not in (None, ""):
                    side_meta["model"] = legacy_meta.get("model", "")
            side_meta.setdefault("make", "")
            side_meta.setdefault("model", "")
            side_meta["validated"] = _resolve_tl_side_validated(side_meta, legacy_meta)


def validate_bidirectional_traffic_lights(io: dict, wb_type: str) -> Optional[str]:
    """Return error if bidirectional traffic_lights structure or pins are incomplete."""
    if wb_type != "bidirectional":
        return None
    if not isinstance(io, dict):
        return "I/O controller configuration is missing for bidirectional traffic lights."
    tl = io.get("traffic_lights")
    if not isinstance(tl, dict):
        return "Bidirectional traffic lights configuration is missing."
    direct = tl.get("direct")
    if not isinstance(direct, dict):
        return "Bidirectional traffic lights direct pin mapping is missing."

    for direction in BIDIRECTIONAL_ENTRY_KEYS:
        dir_label = bidirectional_entry_label(direction)
        dmeta = tl.get(direction)
        if not isinstance(dmeta, dict):
            return f"{dir_label} traffic light metadata is missing."
        ddir = direct.get(direction)
        if not isinstance(ddir, dict):
            return f"{dir_label} traffic light pin mapping is missing."
        for side in ("entry", "exit"):
            side_label = side.capitalize()
            pins = ddir.get(side)
            if not isinstance(pins, dict):
                return f"{dir_label} {side_label} traffic light pins are missing."
            if not _tl_side_active(tl, side, direction):
                continue
            output_mode = io.get("output_mode") or tl.get("mode") or "direct"
            if output_mode == "direct":
                for pin_key in ("red_pin", "green_pin"):
                    val = pins.get(pin_key)
                    if val is None or str(val).strip() == "":
                        return (
                            f"{dir_label} {side_label} traffic light is missing "
                            f"{pin_key.replace('_', ' ')}."
                        )
    return None


def _default_rfid_reader_dict(api_port: str = "8080") -> dict:
    """Default Zebra API-mode reader block (uni or bi entry)."""
    return {
        "ip": "",
        "port": "443",
        "api_port": str(api_port),
        "mode": "API",
        "make": "Zebra",
        "model": "fx900",
        "username": "admin",
        "password": "",
        "validated": False,
        "manual_match_start": 0,
        "manual_match_length": 24,
        "manual_match_sample": "",
        "note": (
            "API mode: tags via POST /rfid_data; "
            "cloud login/mode/start/stop via HTTPS"
        ),
    }


def _deep_copy_default_rfids() -> dict:
    return {
        "entry_a": _default_rfid_reader_dict("8080"),
        "entry_b": _default_rfid_reader_dict("8081"),
    }


def _invalidate_layout_dependent_sections(config: dict) -> None:
    """Clear RFID / traffic-light validation when wb_type changes (uni ↔ bi)."""
    if not isinstance(config, dict):
        return

    rfid = config.get("rfid")
    if isinstance(rfid, dict):
        rfid["validated"] = False

    rfids = config.get("rfids")
    if isinstance(rfids, dict):
        for direction in ("entry_a", "entry_b"):
            reader = rfids.get(direction)
            if isinstance(reader, dict):
                reader["validated"] = False

    # Display count / pcb_mode depends on uni vs bi
    display = config.get("display")
    if isinstance(display, dict):
        display["validated"] = False
        wb = str(
            config.get("wb_type") or config.get("weighbridge_layout") or ""
        ).strip().lower()
        display["pcb_mode"] = "b" if wb == "bidirectional" else "a"
        display["mqtt_topic_tx"] = f"data_info/{display['pcb_mode']}"
        if wb != "bidirectional":
            display["ip_b"] = ""

    io = config.get("io_controller")
    if isinstance(io, dict):
        io["validated"] = False
        tl = io.get("traffic_lights")
        if isinstance(tl, dict):
            for key in ("entry", "exit", "entry_a", "entry_b"):
                block = tl.get(key)
                if not isinstance(block, dict):
                    continue
                if key in ("entry", "exit"):
                    block["validated"] = False
                else:
                    for side in ("entry", "exit"):
                        side_meta = block.get(side)
                        if isinstance(side_meta, dict):
                            side_meta["validated"] = False

    meta = config.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["layout_change_pending"] = True


# Default configuration for GMDC checkpoint / weighbridge apps
DEFAULT_CONFIG = {
    "schema_version": 1,
    "device_ip": "",
    "checkpoint_type": "checkpoint",
    "wb_type": "unidirectional",
    "server": {
        "ip": "",
        "port": "",
        "validated": False
    },
    # Fixed Zebra reader: Application is HTTP server; reader pushes tags to /rfid_data
    "rfid": {
        "ip": "",
        "port": "5555",
        "api_port": "8080",
        "mode": "API",
        "make": "Zebra",
        "model": "fx900",
        "username": "admin",
        "password": "",
        "validated": False,
        "manual_match_start": 0,
        "manual_match_length": 24,
        "manual_match_sample": "",
        "note": "API mode: tags via POST /rfid_data; cloud login/mode/start/stop via HTTPS"
    },
    # Bidirectional weighbridge: two Zebra readers (ENTRY A / ENTRY B), same API mode
    "rfids": {
        "entry_a": {
            "ip": "",
            "port": "443",
            "api_port": "8080",
            "mode": "API",
            "make": "Zebra",
            "model": "fx900",
            "username": "admin",
            "password": "",
            "validated": False,
            "manual_match_start": 0,
            "manual_match_length": 24,
            "manual_match_sample": "",
            "note": "API mode: tags via POST /rfid_data; cloud login/mode/start/stop via HTTPS"
        },
        "entry_b": {
            "ip": "",
            "port": "443",
            "api_port": "8081",
            "mode": "API",
            "make": "Zebra",
            "model": "fx900",
            "username": "admin",
            "password": "",
            "validated": False,
            "manual_match_start": 0,
            "manual_match_length": 24,
            "manual_match_sample": "",
            "note": "API mode: tags via POST /rfid_data; cloud login/mode/start/stop via HTTPS"
        },
    },
    # Handheld / mobile RFID fallback (posts to /rfid_data_from_mobile_app)
    "handheld_rfid": {
        "enabled": True,
        "ip": "",
        "port": "",
        "make": "",
        "model": "",
        "device_id": "",
        "validated": False
    },
    "camera": {
        "top": {
            "rtsp_url": "",
            "make": "",
            "model": "",
            "validated": False
        },
        "front": {
            "rtsp_url": "",
            "make": "",
            "model": "",
            "validated": False
        }
    },
    "display": {
        "type": "mqtt",
        "ip": "",
        "ip_b": "",
        "port": "1883",
        "broker": "127.0.0.1",
        "pcb_mode": "a",
        "mqtt_topic_tx": "data_info/a",
        "mqtt_topic_rx": "display_info",
        "make": "",
        "model": "",
        "validated": False
    },
    # Digitizer: API (HTTP) or MQTT (decoder on another PC; broker on Mines-WB Mac)
    "digitizer": {
        "mode": "api",
        "host": "",
        "port": "8100",
        "path": "/read_stable_weight",
        "broker_host": "127.0.0.1",
        "broker_port": "1883",
        "username": "",
        "password": "",
        "topic_weight": "gmdc/digitizer/weight",
        "topic_request": "gmdc/digitizer/request",
        "timeout": "30",
        "stable_count": "10",
        "validated": False,
        "make": "",
        "model": ""
    },
    "io_controller": {
        "type": "ethernet",
        "output_mode": "direct",
        "connection": {
            "ethernet": {
                "ip": "",
                "port": "502",
                "timeout": "1"
            },
            "serial": {
                "port": "",
                "baud_rate": "9600",
                "bytesize": "8",
                "parity": "N",
                "stopbits": "1",
                "timeout": "0.5"
            }
        },
        "slave_id": "1",
        "polling": {
            "scan_interval": "0.3",
            "delay": "0.3"
        },
        "function_codes": {
            "read_coils": "1",
            "read_discrete_inputs": "2",
            "read_holding_registers": "3",
            "read_input_registers": "4",
            "write_single_coil": "5",
            "write_single_register": "6",
            "write_multiple_coils": "15",
            "write_multiple_registers": "16"
        },
        "digital_inputs": {
            "start_address": "",
            "count": "8",
            "function_code": "",
            "mapping": {
                "sensor_entry": {"address": "0", "description": "Entry sensor"},
                "sensor_platform": {"address": "1", "description": "Platform sensor"},
                "sensor_exit": {"address": "2", "description": "Exit sensor"},
            }
        },
        "digital_outputs": {
            "start_address": "",
            "count": "8",
            "function_code": "",
            "mode_description": {
                "direct": "Each light/barrier has separate pins (red_pin, green_pin, open_pin, close_pin)",
                "relay": "Single pin per device controls a relay with NO/NC contacts"
            },
            "mapping": {
                "traffic_light_entry_red": {"address": "0", "description": "Entry red light"},
                "traffic_light_entry_green": {"address": "1", "description": "Entry green light"},
                "traffic_light_exit_red": {"address": "2", "description": "Exit red light"},
                "traffic_light_exit_green": {"address": "3", "description": "Exit green light"},
                "barrier_entry_open": {"address": "4", "description": "Open entry barrier"},
                "barrier_exit_open": {"address": "5", "description": "Open exit barrier"}
            }
        },
        "sensors": {
            "entry_sensor": {"pin": "0", "default_signal": "low", "validated": False},
            "wb_sensor": {"pin": "1", "default_signal": "low", "validated": False},
            "exit_sensor": {"pin": "2", "default_signal": "low", "validated": False}
        },
        "traffic_lights": {
            "mode": "direct",
            "relay_logic": {
                "description": "Relay ON (coil=HIGH) = NO contact = GREEN, Relay OFF (coil=LOW) = NC contact = RED",
                "on_state": "green",
                "off_state": "red"
            },
            "direct": {
                "entry": {"red_pin": "0", "green_pin": "1"},
                "exit": {"red_pin": "2", "green_pin": "3"}
            },
            "relay": {
                "entry": {"pin": "0", "description": "Relay 1: NO=Green, NC=Red"},
                "exit": {"pin": "1", "description": "Relay 2: NO=Green, NC=Red"}
            },
            "entry": {"make": "", "model": "", "validated": False},
            "exit": {"make": "", "model": "", "validated": False}
        },
        "boom_barriers": {
            "mode": "direct",
            "relay_logic": {
                "description": "Relay ON (coil=HIGH) = NO contact = OPEN, Relay OFF (coil=LOW) = NC contact = CLOSE",
                "on_state": "open",
                "off_state": "close"
            },
            "direct": {
                "entry": {"open_pin": "4", "close_pin": None, "enabled": False},
                "exit": {"open_pin": "5", "close_pin": None, "enabled": False}
            },
            "relay": {
                "entry": {"pin": "2", "enabled": False, "description": "Relay 3: NO=Open, NC=Close"},
                "exit": {"pin": "3", "enabled": False, "description": "Relay 4: NO=Open, NC=Close"}
            },
            "entry": {"make": "", "model": "", "validated": False},
            "exit": {"make": "", "model": "", "validated": False}
        },
        "validated": False
    },
    "status": False,
    "voice": {
        "enabled": True,
        "directory": "voice",
        "error_prefix": True,
        "validated": False
    },
    "api_endpoints": {
        "oci_base_url": "https://gmuatociexp.gmdcltd.co.in",
        "rfid_validate_url": "/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag",
        "anpr_base_url": "http://192.168.25.79:5001",
        "anpr_detect_url": "/api/detect",
        "invalid_truck_url": "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number",
        "update_truck_url": "/ords/gmdc_dicsm/dlms_checkpoint/status_check",
        "boom_close_url": "/ords/gmdc_dicsm/dlms_checkpoint/boom-close",
        "reset_checkpoint_url": "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint",
        "weight_details_url": "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details",
        "vadhghat_weight_adjustment_url": "/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment",
        # Per-endpoint credentials
        "rfid_validate_username": "GMDC_API_USER",
        "rfid_validate_password": "GMDC@1234",
        "anpr_detect_username": "GMDC_API_USER",
        "anpr_detect_password": "GMDC@1234",
        "invalid_truck_username": "GMDC_API_USER",
        "invalid_truck_password": "GMDC@1234",
        "update_truck_username": "GMDC_API_USER",
        "update_truck_password": "GMDC@1234",
        "boom_close_username": "GMDC_API_USER",
        "boom_close_password": "GMDC@1234",
        "reset_checkpoint_username": "GMDC_API_USER",
        "reset_checkpoint_password": "GMDC@1234",
        "weight_details_username": "GMDC_API_USER",
        "weight_details_password": "GMDC@1234",
        "vadhghat_weight_adjustment_username": "GMDC_API_USER",
        "vadhghat_weight_adjustment_password": "GMDC@1234",
        # Legacy shared keys (kept for older configs / fallback)
        "oci_username": "GMDC_API_USER",
        "oci_password": "GMDC@1234",
        "anpr_username": "GMDC_API_USER",
        "anpr_password": "GMDC@1234",
    },
    "setup_info": {
        "weighbridge_details": "",
        "weighbridge_location": "",
        "vendor_company": "",
        "verified_by": "",
        "verification_date": ""
    },
    "ip_range": {
        "start_ip": "192.168.1.1",
        "end_ip": "192.168.1.254"
    }
}


if not ENABLE_CAMERA_CONFIGURATION:
    DEFAULT_CONFIG.pop("camera", None)


_LOOPBACK_DEVICE_IPS = {"127.0.0.1", "0.0.0.0", "localhost", "::1"}


def io_controller_device_address(io_payload: dict) -> str:
    """Address to store as device_ip after a successful I/O connection.

    Ethernet stores the controller IP from the connection form.
    MODBUS RTU stores the COM port. This PC's own LAN address is never used.
    """
    if not isinstance(io_payload, dict):
        return ""
    kind = str(io_payload.get("type") or "ethernet").strip().lower()
    connection = io_payload.get("connection") if isinstance(io_payload.get("connection"), dict) else {}
    if kind in ("serial", "rtu"):
        serial = connection.get("serial") if isinstance(connection.get("serial"), dict) else {}
        return str(serial.get("port") or "").strip()
    ethernet = connection.get("ethernet") if isinstance(connection.get("ethernet"), dict) else {}
    ip = str(ethernet.get("ip") or "").strip()
    if not ip or ip.lower() in _LOOPBACK_DEVICE_IPS:
        return ""
    try:
        from utils.local_ip import detect_device_ip

        local_ip = detect_device_ip()
    except Exception:
        local_ip = None
    if local_ip and ip == str(local_ip).strip():
        return ""
    return ip


class ConfigManager:
    def __init__(self):
        self.config = self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON file or return defaults"""
        # Always start with defaults (status will be False)
        config = DEFAULT_CONFIG.copy()
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    config = self._deep_merge(config, loaded)
                    config = _normalize_io_sensors(config)
                    migrate_wb_type_key(config)
                    migrate_gmdc_api_defaults(config)
            except (json.JSONDecodeError, IOError):
                pass  # Use defaults
        
        # Always reset status to False when application starts
        config["status"] = False
        migrate_wb_type_key(config)
        migrate_gmdc_api_defaults(config)
        self._sanitize_config_for_layout(config)
        return order_config_keys(config)
    
    def _deep_merge(self, base, override):
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _save_config(self):
        """Save configuration to JSON file"""
        try:
            migrate_wb_type_key(self.config)
            self._sanitize_config_for_layout(self.config)
            self.config = order_config_keys(self.config)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except IOError:
            return False
    
    def get_all(self):
        """Get all configuration (includes backend-only fields such as device_ip)."""
        return self.config

    def get_all_for_frontend(self):
        """
        Config payload for the commissioning UI.

        device_ip is the I/O controller address (or COM port) captured when Connect succeeds.
        It must not appear in the UI.
        """
        data = self._deep_copy(self.config)
        if isinstance(data, dict):
            data.pop("device_ip", None)
        return data
    
    def get_section(self, section):
        """Get configuration for a specific section"""
        if section == "device_ip":
            return {}
        return self.config.get(section, {})

    def get_wb_type(self) -> str:
        """Return unidirectional or bidirectional (default unidirectional)."""
        return get_wb_type_from_dict(self.config)

    def get_api_endpoint_fields(self) -> list:
        """Profile-specific API URL fields for the finish-flow editor."""
        from services.profiles import api_endpoint_fields

        return api_endpoint_fields(self.config.get("checkpoint_type"))

    def get_weighbridge_layout(self) -> str:
        """Deprecated alias for get_wb_type."""
        return self.get_wb_type()

    def set_wb_type(self, wb_type: str):
        """Persist weighbridge type choice. Returns (success, layout_changed)."""
        if wb_type not in ("unidirectional", "bidirectional"):
            return False, False
        old_type = self.get_wb_type()
        layout_changed = old_type != wb_type
        if layout_changed:
            _invalidate_layout_dependent_sections(self.config)
        self.config["wb_type"] = wb_type
        self.config.pop("weighbridge_layout", None)
        self._sanitize_config_for_layout(self.config)
        return self._save_config(), layout_changed

    def set_weighbridge_layout(self, layout: str):
        """Deprecated alias for set_wb_type."""
        return self.set_wb_type(layout)

    def validate_bidirectional_traffic_lights_for_config(
        self, io: Optional[dict] = None, wb_type: Optional[str] = None
    ) -> Optional[str]:
        io_data = io if io is not None else (self.config.get("io_controller") or {})
        layout = wb_type if wb_type is not None else self.get_wb_type()
        return validate_bidirectional_traffic_lights(io_data, layout)

    @staticmethod
    def _sanitize_config_for_layout(config: dict) -> None:
        """Remove legacy keys that do not apply to the active weighbridge layout."""
        if not isinstance(config, dict):
            return
        migrate_wb_type_key(config)
        layout = get_wb_type_from_dict(config)

        if layout == "bidirectional":
            _migrate_legacy_bidirectional_direction_keys(config)
            config.pop("rfid", None)
            if not isinstance(config.get("rfids"), dict):
                config["rfids"] = _deep_copy_default_rfids()
            else:
                rfids = config["rfids"]
                for dir_key in ("entry_a", "entry_b"):
                    if not isinstance(rfids.get(dir_key), dict):
                        rfids[dir_key] = _default_rfid_reader_dict(
                            "8081" if dir_key == "entry_b" else "8080"
                        )
            io = config.get("io_controller")
            if isinstance(io, dict):
                tl = io.get("traffic_lights")
                if isinstance(tl, dict):
                    _migrate_traffic_lights_to_bidirectional(tl)
                    _strip_unidirectional_traffic_light_keys(tl)
        else:
            config.pop("rfids", None)
            io = config.get("io_controller")
            if isinstance(io, dict):
                tl = io.get("traffic_lights")
                if isinstance(tl, dict):
                    for key in (
                        *BIDIRECTIONAL_ENTRY_KEYS,
                        LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY,
                        LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY,
                    ):
                        tl.pop(key, None)
                    direct = tl.get("direct")
                    if isinstance(direct, dict):
                        for key in (
                            *BIDIRECTIONAL_ENTRY_KEYS,
                            LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY,
                            LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY,
                        ):
                            direct.pop(key, None)
                    relay = tl.get("relay")
                    if isinstance(relay, dict):
                        for key in (
                            *BIDIRECTIONAL_ENTRY_KEYS,
                            LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY,
                            LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY,
                        ):
                            relay.pop(key, None)

        normalize_rfid_sections(config)
        _sanitize_wb_sensor_validated(config)
        digitizer = config.get("digitizer")
        if isinstance(digitizer, dict):
            config["digitizer"] = _sanitize_digitizer_section(digitizer)
        _strip_camera_if_disabled(config)

    def validate_bidirectional_rfids(self, rfids: dict) -> Optional[str]:
        """Return error if entry_a/entry_b share IP or RFID_API_PORT."""
        if not isinstance(rfids, dict):
            return None
        a = rfids.get("entry_a") or {}
        b = rfids.get("entry_b") or {}
        if not isinstance(a, dict) or not isinstance(b, dict):
            return None
        ip_a = (a.get("ip") or "").strip()
        ip_b = (b.get("ip") or "").strip()
        if ip_a and ip_b and ip_a == ip_b:
            return (
                f"{bidirectional_entry_label(BIDIRECTIONAL_ENTRY_A_KEY)} and "
                f"{bidirectional_entry_label(BIDIRECTIONAL_ENTRY_B_KEY)} cannot use the same RFID IP address. "
                "Assign a unique IP to each reader."
            )
        mode_a = str(a.get("mode") or "").strip().upper()
        mode_b = str(b.get("mode") or "").strip().upper()
        port_a = str(a.get("api_port") or "").strip()
        port_b = str(b.get("api_port") or "").strip()
        if mode_a == "API" and mode_b == "API" and port_a and port_b and port_a == port_b:
            return (
                f"{bidirectional_entry_label(BIDIRECTIONAL_ENTRY_A_KEY)} and "
                f"{bidirectional_entry_label(BIDIRECTIONAL_ENTRY_B_KEY)} must use different "
                "RFID_API_PORT values."
            )
        return None

    def validate_io_pin_uniqueness(
        self, io: Optional[dict] = None, wb_type: Optional[str] = None
    ) -> Optional[str]:
        """Return error message if sensor/TL/boom pins are not unique on the I/O card."""
        io_data = io if io is not None else (self.config.get("io_controller") or {})
        layout = wb_type if wb_type is not None else self.get_wb_type()
        return validate_io_pin_uniqueness(io_data, layout)
    
    def save_all(self, data):
        """Save all configuration (preserve backend-only device_ip from UI payloads)."""
        existing_device_ip = self.config.get("device_ip", "") if isinstance(self.config, dict) else ""
        payload = data if isinstance(data, dict) else {}
        # Never accept device_ip from the frontend
        payload = dict(payload)
        payload.pop("device_ip", None)
        self.config = payload
        if existing_device_ip:
            self.config["device_ip"] = existing_device_ip
        self._sanitize_config_for_layout(self.config)
        return self._save_config()

    def record_device_ip_from_io(self, io_payload: dict) -> bool:
        """Write device_ip when the I/O controller connection succeeds.

        Ethernet: the controller IP the operator connected to.
        RTU: the COM port. This machine's LAN IP is not stored.
        """
        address = io_controller_device_address(io_payload)
        if not address:
            return False
        self.config["device_ip"] = address
        return self._save_config()

    def merge_io_controller_device(self, partial: dict):
        """Save one I/O device into io_controller without marking the module complete."""
        if not isinstance(partial, dict) or not partial:
            return False, "Nothing to save"
        incoming = dict(partial)
        incoming.pop("validated", None)
        current = self.config.get("io_controller")
        if not isinstance(current, dict):
            current = self._deep_copy(DEFAULT_CONFIG.get("io_controller") or {})
        merged = self._deep_merge(self._deep_copy(current), incoming)
        err = self.validate_io_pin_uniqueness(merged, self.get_wb_type())
        if err:
            return False, err
        self.config["io_controller"] = merged
        if not self._save_config():
            return False, "Could not save I/O device"
        return True, None
    
    def save_section(self, section, data):
        """Save configuration for a specific section"""
        if section == "device_ip":
            # Set from a successful I/O connection, not from the UI.
            return False
        if section == "rfids":
            self.config["rfids"] = (
                order_rfids_section(data) if isinstance(data, dict) else {}
            )
        elif section == "io_controller":
            self.config["io_controller"] = data if isinstance(data, dict) else {}
        elif section in self.config:
            if isinstance(self.config[section], dict) and isinstance(data, dict):
                self.config[section] = self._deep_merge(self.config[section], data)
            else:
                self.config[section] = data
        else:
            self.config[section] = data
        if section == "digitizer" and isinstance(self.config.get("digitizer"), dict):
            self.config["digitizer"] = _sanitize_digitizer_section(self.config["digitizer"])
        if section == "display" and isinstance(self.config.get("display"), dict):
            disp = self.config["display"]
            wb = self.get_wb_type()
            mode = "b" if wb == "bidirectional" else "a"
            disp["pcb_mode"] = mode
            disp["mqtt_topic_tx"] = f"data_info/{mode}"
            disp["mqtt_topic_rx"] = "display_info"
            ip = str(disp.get("ip") or "").strip()
            ip_b = str(disp.get("ip_b") or "").strip()
            if disp.get("validated"):
                if not ip:
                    logger.warning("display validated but ip missing")
                    return False
                if wb == "bidirectional":
                    if not ip_b:
                        logger.warning("bi-directional display requires ip_b")
                        return False
                    if ip_b == ip:
                        logger.warning("display ip and ip_b must differ")
                        return False
                else:
                    disp["ip_b"] = ""
        if section == "rfids" and self.get_wb_type() == "bidirectional":
            err = self.validate_bidirectional_rfids(self.config.get("rfids") or {})
            if err:
                return False
        if section == "io_controller":
            err = self.validate_io_pin_uniqueness(
                data if isinstance(data, dict) else {},
                self.get_wb_type(),
            )
            if err:
                return False
        self._sanitize_config_for_layout(self.config)
        return self._save_config()

    def import_configuration_for_upgrade(
        self,
        uploaded_config: dict,
        revalidate_sections: Optional[List[str]] = None,
    ) -> bool:
        """
        Import an older `iot_configuration.json` into the current schema.

        Validation policy:
        - Force re-validation (validated=false) for the given sections:
          - RFID, Display, Digitizer, Voice(Audio)
        - Auto-validate the remaining sections so UI completion can continue.
        - Always set root `status=false` so Weighbridge-App gating remains correct.
        """
        if not isinstance(uploaded_config, dict):
            return False

        if revalidate_sections is None:
            revalidate_sections = ["rfid", "display", "digitizer", "voice"]

        # Start from defaults to ensure newly added keys exist,
        # then merge the uploaded file on top.
        merged = self._deep_merge(self._deep_copy(DEFAULT_CONFIG), uploaded_config)

        migrate_wb_type_key(merged)
        if get_wb_type_from_dict(merged) not in ("unidirectional", "bidirectional"):
            merged["wb_type"] = "unidirectional"

        # Always reset gating status after import.
        merged["status"] = False
        self._sanitize_config_for_layout(merged)
        merged = order_config_keys(merged)

        def _set_validated(section_key: str, value: bool):
            sec = merged.get(section_key)
            if isinstance(sec, dict) and "validated" in sec:
                sec["validated"] = value
            elif isinstance(sec, dict):
                sec["validated"] = value

        # 1) Auto-validate everything except the revalidate sections
        # Server
        if "server" in merged:
            _set_validated("server", True)

        # Camera: needs both top and front for completion status
        if ENABLE_CAMERA_CONFIGURATION:
            cam = merged.get("camera")
            if isinstance(cam, dict):
                top = cam.get("top")
                if isinstance(top, dict):
                    top["validated"] = True
                front = cam.get("front")
                if isinstance(front, dict):
                    front["validated"] = True

        # I/O controller
        if "io_controller" in merged:
            _set_validated("io_controller", True)

        # Voice(Audio)
        if "voice" in merged:
            _set_validated("voice", True)

        # 2) Force re-validation for selected sections
        for section_key in revalidate_sections:
            _set_validated(section_key, False)

        self.config = merged
        return self._save_config()
    
    def reset_section(self, section):
        """Reset a section to default values"""
        if section == "camera" and not ENABLE_CAMERA_CONFIGURATION:
            return False
        if section in DEFAULT_CONFIG:
            self.config[section] = self._deep_copy(DEFAULT_CONFIG[section])
            return self._save_config()
        return False

    def reset_all(self):
        """
        Reset entire configuration to defaults.
        Only for explicit "Start fresh configuration" — not on checklist load.
        """
        config = self._deep_copy(DEFAULT_CONFIG)
        config["status"] = False
        migrate_wb_type_key(config)
        migrate_gmdc_api_defaults(config)
        self._sanitize_config_for_layout(config)
        self.config = order_config_keys(config)
        return self._save_config()
    
    def _deep_copy(self, obj):
        """Deep copy a dictionary or list"""
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._deep_copy(item) for item in obj]
        else:
            return obj
    
    def set_validated(self, section, validated=True):
        """Set validation status for a section"""
        if section in self.config:
            if isinstance(self.config[section], dict):
                self.config[section]['validated'] = validated
                return self._save_config()
        return False

    def invalidate_section(self, section: str) -> bool:
        """
        Mark a wizard section as not validated and clear root status.
        Used when the operator edits fields after a successful Check & Save.
        """
        key = str(section or "").strip()
        aliases = {
            "audio": "voice",
            "io-controller": "io_controller",
            "handheld-rfid": "handheld_rfid",
        }
        key = aliases.get(key, key)
        if not key:
            return False

        self.config["status"] = False

        if key == "rfid":
            rfid = self.config.get("rfid")
            if isinstance(rfid, dict):
                rfid["validated"] = False
            rfids = self.config.get("rfids")
            if isinstance(rfids, dict):
                for side in ("entry_a", "entry_b"):
                    reader = rfids.get(side)
                    if isinstance(reader, dict):
                        reader["validated"] = False
        elif key == "camera":
            cam = self.config.get("camera")
            if not isinstance(cam, dict):
                cam = {}
                self.config["camera"] = cam
            cam["validated"] = False
            for sub in ("top", "front", "front_a", "front_b"):
                block = cam.get(sub)
                if isinstance(block, dict):
                    block["validated"] = False
        elif key == "io_controller":
            io = self.config.get("io_controller")
            if isinstance(io, dict):
                io["validated"] = False
                sensors = io.get("sensors")
                if isinstance(sensors, dict):
                    for sensor in sensors.values():
                        if isinstance(sensor, dict):
                            sensor["validated"] = False
                for group_key in ("traffic_lights", "boom_barriers"):
                    group = io.get(group_key)
                    if not isinstance(group, dict):
                        continue
                    for block in group.values():
                        if isinstance(block, dict):
                            if "validated" in block:
                                block["validated"] = False
                            for side_meta in block.values():
                                if isinstance(side_meta, dict) and "validated" in side_meta:
                                    side_meta["validated"] = False
        elif key in self.config and isinstance(self.config[key], dict):
            self.config[key]["validated"] = False
        else:
            return False

        return self._save_config()
    
    def set_status(self, status=True):
        """Set the root-level status field"""
        self.config["status"] = status
        return self._save_config()
    
    def get_status(self):
        """Get the root-level status field"""
        return self.config.get("status", False)
    
    def _rfid_section_complete(self) -> bool:
        """RFID completion: one reader (uni) or both directions (bi)."""
        if self.get_wb_type() == "bidirectional":
            rfids = self.config.get("rfids") or {}
            if not isinstance(rfids, dict):
                return False
            a = rfids.get("entry_a") or {}
            b = rfids.get("entry_b") or {}
            a_ok = isinstance(a, dict) and a.get("validated") is True
            b_ok = isinstance(b, dict) and b.get("validated") is True
            return a_ok and b_ok
        rfid = self.config.get("rfid") or {}
        return isinstance(rfid, dict) and rfid.get("validated") is True

    def _camera_completion(self, profile):
        """
        Camera nav status.

        Checkpoint requires Front only. Weigh Bridge requires Top and Front.
        Bidirectional Weigh Bridge requires Front Entry A and Front Entry B.
        Top may be skipped (validated null).
        A stale parent ``validated: false`` must not hide a camera that already
        passed Check & Save.
        """
        camera_config = self.config.get("camera") or {}
        if not isinstance(camera_config, dict):
            return False
        top_block = camera_config.get("top") if isinstance(camera_config.get("top"), dict) else {}
        front_block = camera_config.get("front") if isinstance(camera_config.get("front"), dict) else {}
        top_valid = top_block.get("validated", False)
        front_valid = front_block.get("validated", False)
        parent = camera_config.get("validated", None)

        if getattr(profile, "family", "") == "weighbridge":
            if self.get_wb_type() == "bidirectional":
                front_a = camera_config.get("front_a") if isinstance(camera_config.get("front_a"), dict) else {}
                front_b = camera_config.get("front_b") if isinstance(camera_config.get("front_b"), dict) else {}
                top_ok = top_valid is True or top_valid is None
                fronts_ok = front_a.get("validated") is True and front_b.get("validated") is True
                if top_ok and fronts_ok:
                    return True
                if parent is None and top_valid is None and front_a.get("validated") is None and front_b.get("validated") is None:
                    return None
                return False
            if top_valid is True and front_valid is True:
                return True
            if parent is None and top_valid is None and front_valid is None:
                return None
            return False

        if front_valid is True:
            return True
        if front_valid is None and parent is None:
            return None
        return False

    def _checkpoint_io_devices_complete(self, io: dict) -> bool:
        """Checkpoint I/O: entry sensor, entry traffic light, entry boom if enabled."""
        sensors = io.get("sensors") if isinstance(io.get("sensors"), dict) else {}
        entry_sensor = sensors.get("entry_sensor") if isinstance(sensors.get("entry_sensor"), dict) else {}
        if entry_sensor.get("validated") is not True:
            return False

        lights = io.get("traffic_lights") if isinstance(io.get("traffic_lights"), dict) else {}
        entry_light = lights.get("entry") if isinstance(lights.get("entry"), dict) else {}
        light_validated = entry_light.get("validated", False)
        if light_validated is not True and light_validated is not None:
            return False

        barriers = io.get("boom_barriers") if isinstance(io.get("boom_barriers"), dict) else {}
        mode = str(io.get("output_mode") or barriers.get("mode") or "direct")
        if mode not in ("direct", "relay"):
            mode = "direct"
        mode_block = barriers.get(mode) if isinstance(barriers.get(mode), dict) else {}
        entry_cfg = mode_block.get("entry") if isinstance(mode_block.get("entry"), dict) else {}
        if entry_cfg.get("enabled"):
            entry_meta = barriers.get("entry") if isinstance(barriers.get("entry"), dict) else {}
            if entry_meta.get("validated") is not True:
                return False
        return True

    def _io_completion(self, profile):
        """I/O nav status. Parent true/null wins; otherwise required devices for this site."""
        io = self.config.get("io_controller") or {}
        if not isinstance(io, dict):
            return False
        parent = io.get("validated", False)
        if parent is None:
            return None
        if parent is True:
            return True
        if getattr(profile, "family", "") == "checkpoint":
            return self._checkpoint_io_devices_complete(io)
        if self._traffic_lights_complete():
            return True
        return False

    def _traffic_lights_complete(self) -> bool:
        """Traffic lights validated under io_controller for current layout."""
        io_config = self.config.get("io_controller") or {}
        tl = io_config.get("traffic_lights") or {}
        if not isinstance(tl, dict):
            return False
        if self.get_wb_type() == "bidirectional":
            for direction in ("entry_a", "entry_b"):
                dmeta = tl.get(direction) or {}
                if not isinstance(dmeta, dict):
                    return False
                for side in ("entry", "exit"):
                    side_meta = dmeta.get(side) or {}
                    v = side_meta.get("validated") if isinstance(side_meta, dict) else False
                    if v is not True and v is not None:
                        return False
            return True
        entry_meta = tl.get("entry") or {}
        exit_meta = tl.get("exit") or {}
        entry_v = entry_meta.get("validated") if isinstance(entry_meta, dict) else False
        exit_v = exit_meta.get("validated") if isinstance(exit_meta, dict) else False
        return (entry_v is True or entry_v is None) and (exit_v is True or exit_v is None)

    def get_checkpoint_type(self) -> str:
        """Active site type: checkpoint or weighbridge."""
        from services.profiles import normalize_checkpoint_type
        return normalize_checkpoint_type(self.config.get("checkpoint_type"))

    def set_checkpoint_type(self, checkpoint_type: str, direction: Optional[str] = None):
        """
        Set checkpoint_type and optional wb_type (direction for weighbridges).
        Returns (success, layout_changed).
        """
        from services.profiles import (
            CHECKPOINT_PROFILES,
            get_profile,
            resolve_direction,
        )
        if checkpoint_type not in CHECKPOINT_PROFILES:
            return False, False
        profile = get_profile(checkpoint_type)
        old_type = self.get_checkpoint_type()
        old_dir = self.get_wb_type()
        new_dir = resolve_direction(profile, direction if direction is not None else old_dir)
        layout_changed = (old_type != checkpoint_type) or (
            profile.directional and old_dir != new_dir
        )
        self.config["checkpoint_type"] = checkpoint_type
        self.config["wb_type"] = new_dir
        self.config["schema_version"] = 1
        if layout_changed:
            _invalidate_layout_dependent_sections(self.config)
            # Drop digitizer if switching away from weighbridge
            if not profile.has_digitizer:
                dig = self.config.get("digitizer")
                if isinstance(dig, dict):
                    dig["validated"] = False
        self._save_config()
        return True, layout_changed

    def get_completion_status(self):
        """Get completion status of all sections for the active profile."""
        from services.profiles import nav_sections_for, get_profile

        status = {}
        sections = nav_sections_for(
            self.get_checkpoint_type(),
            enable_camera=ENABLE_CAMERA_CONFIGURATION,
        )
        profile = get_profile(self.get_checkpoint_type())

        for section in sections:
            if section == 'rfid':
                if self._rfid_section_complete():
                    status[section] = True
                else:
                    if self.get_wb_type() == "bidirectional" and profile.dual_rfid_when_bidirectional:
                        rfids = self.config.get("rfids") or {}
                        a_v = (rfids.get("entry_a") or {}).get("validated", False)
                        b_v = (rfids.get("entry_b") or {}).get("validated", False)
                        if a_v is None and b_v is None:
                            status[section] = None
                        else:
                            status[section] = False
                    else:
                        status[section] = (self.config.get("rfid") or {}).get("validated", False)
                continue
            if section == 'handheld_rfid':
                hh = self.config.get("handheld_rfid") or {}
                if not hh.get("enabled", True):
                    status[section] = None  # skipped / disabled
                else:
                    status[section] = hh.get("validated", False)
                continue
            if section == 'digitizer':
                if not profile.has_digitizer:
                    status[section] = True
                    continue
                status[section] = (self.config.get("digitizer") or {}).get("validated", False)
                continue
            if section == 'io_controller':
                status[section] = self._io_completion(profile)
                continue
            if section == 'camera':
                if not ENABLE_CAMERA_CONFIGURATION:
                    status[section] = True
                    continue
                status[section] = self._camera_completion(profile)
                continue
            if section == 'voice':
                voice_config = self.config.get('voice', {})
                validated_value = voice_config.get('validated')
                if validated_value is not None:
                    status[section] = validated_value
                else:
                    status[section] = True
                continue
            validated_value = self.config.get(section, {}).get('validated', False)
            status[section] = validated_value

        status['all_complete'] = all(
            s is True or s is None or s == 'true' or s == 'null' or s == 'None'
            for s in status.values() if s != 'all_complete'
        )
        return status
    
    def finalize(self):
        """Finalize configuration and save to iot_configuration.json"""
        status = self.get_completion_status()
        
        if not status['all_complete']:
            # Find incomplete sections (not validated and not skipped)
            incomplete = [k for k, v in status.items() if k != 'all_complete' and v is not True and v is not None]
            needed = ", ".join(section_label(name) for name in incomplete)
            return {
                "status": 400,
                "message": f"Configuration incomplete. Still needed: {needed}"
            }
        
        try:
            final_config = self._prepare_final_config()
        except ValueError as e:
            return {
                "status": 400,
                "message": str(e),
            }
        
        migrate_wb_type_key(final_config)
        normalize_rfid_sections(final_config)
        final_config = order_config_keys(final_config)
        self.config = final_config
        
        # Save to iot_configuration.json
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(final_config, f, indent=2)
            
            return {
                "status": 200,
                "message": "Configuration finalized and saved successfully",
                "file": CONFIG_FILE,
            }
        except IOError as e:
            return {
                "status": 500,
                "message": f"Failed to save configuration: {str(e)}"
            }
    
    def _prepare_final_config(self):
        """Prepare final configuration for weighbridge_app"""
        # Deep copy to avoid modifying original
        final = self._deep_copy(self.config)
        self._sanitize_config_for_layout(final)

        if self.get_wb_type() == "bidirectional":
            err = self.validate_bidirectional_rfids(final.get("rfids") or {})
            if err:
                raise ValueError(err)

        err = self.validate_io_pin_uniqueness(final.get("io_controller") or {})
        if err:
            raise ValueError(err)

        if self.get_wb_type() == "bidirectional":
            err = validate_bidirectional_traffic_lights(
                final.get("io_controller") or {}, "bidirectional"
            )
            if err:
                raise ValueError(err)
        
        # Update setup_info with verification date
        if 'setup_info' in final:
            final['setup_info']['verification_date'] = datetime.now().strftime('%Y-%m-%d')

        # device_ip was stored when the I/O controller connected.
        # Keep that controller IP or COM port. Do not replace it with this PC's address.
        final["device_ip"] = str(final.get("device_ip") or "").strip()
        
        # Remove internal fields not needed by weighbridge_app
        fields_to_remove = ['ip_range', '_meta']
        for field in fields_to_remove:
            final.pop(field, None)
        
        # Set 'validated' flags to True for all sections, but preserve None (skipped) values
        self._set_all_validated(final, True)
        
        return final
    
    def _set_all_validated(self, obj, value):
        """Recursively set all 'validated' fields to a value, but preserve None (skipped) values"""
        if isinstance(obj, dict):
            if 'validated' in obj:
                # Only set if current value is not None (preserve skipped sections)
                if obj['validated'] is not None:
                    obj['validated'] = value
            for v in obj.values():
                self._set_all_validated(v, value)
        elif isinstance(obj, list):
            for item in obj:
                self._set_all_validated(item, value)
