"""Load / persist digitizer-decoder configuration."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("digitizer_decoder.config")

STABLE_READ_COUNT = 10
READ_TIMEOUT_SEC = 30.0
WIZARD_CAPTURE_BYTES = 40

DEFAULT_COMMUNICATION: Dict[str, Any] = {
    "mode": "api",
    "api": {
        "host": "0.0.0.0",
        "port": 8800,
        "path": "/read_stable_weight",
    },
    "mqtt": {
        "broker_host": "",
        "broker_port": 1883,
        "username": "",
        "password": "",
        "topic_publish": "",
        "topic_subscribe": "",
        "topic_status": "gmdc/digitizer/status",
        "client_id": "gmdc-digitizer-decoder",
    },
}

DEFAULT_ADMIN: Dict[str, Any] = {
    "username": "admin",
    "password": "gmdc@123",
}

# Blank first-run template (no serial port / indexing until admin configures)
DEFAULT_CONFIG: Dict[str, Any] = {
    "port": "--Select--",
    "baud_rate": "--Select--",
    "data_bits": "--Select--",
    "parity": "--Select--",
    "stop_bits": "--Select--",
    "status": False,
    "indexing": None,
    "calibration_sample_hex": "",
    "communication": deepcopy(DEFAULT_COMMUNICATION),
    "admin": deepcopy(DEFAULT_ADMIN),
    "ui_port": 8765,
}


def app_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path() -> str:
    return os.path.join(app_dir(), "config.json")


def version_string() -> str:
    path = os.path.join(app_dir(), "VERSION")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


@dataclass
class Settings:
    raw: Dict[str, Any] = field(default_factory=dict)
    path: str = ""

    @property
    def communication_mode(self) -> str:
        comm = self.raw.get("communication") or {}
        mode = str(comm.get("mode") or "api").strip().lower()
        return mode if mode in ("api", "mqtt") else "api"

    @property
    def api_cfg(self) -> Dict[str, Any]:
        comm = self.raw.get("communication") or {}
        api = dict(DEFAULT_COMMUNICATION["api"])
        api.update(comm.get("api") or {})
        return api

    @property
    def mqtt_cfg(self) -> Dict[str, Any]:
        comm = self.raw.get("communication") or {}
        mqtt = dict(DEFAULT_COMMUNICATION["mqtt"])
        mqtt.update(comm.get("mqtt") or {})
        # Always keep TCP broker on 1883 unless an explicit non-HTTP port is set
        try:
            port = int(mqtt.get("broker_port") or 1883)
        except (TypeError, ValueError):
            port = 1883
        if port in (80, 81, 443, 8000, 8080, 8800, 8100, 9001) or port <= 0:
            port = 1883
        mqtt["broker_port"] = port
        return mqtt

    @property
    def admin_username(self) -> str:
        admin = self.raw.get("admin") if isinstance(self.raw.get("admin"), dict) else {}
        user = str((admin or {}).get("username") or DEFAULT_ADMIN["username"]).strip()
        return user or "admin"

    @property
    def admin_password(self) -> str:
        admin = self.raw.get("admin") if isinstance(self.raw.get("admin"), dict) else {}
        pwd = (admin or {}).get("password")
        if pwd is None or pwd == "":
            return str(DEFAULT_ADMIN["password"])
        return str(pwd)

    @property
    def ui_port(self) -> int:
        try:
            return int(self.raw.get("ui_port") or 8765)
        except (TypeError, ValueError):
            return 8765

    @property
    def weight_api_port(self) -> int:
        try:
            return int(self.api_cfg.get("port") or 8800)
        except (TypeError, ValueError):
            return 8800

    def serial_dict(self) -> Dict[str, Any]:
        return {
            "port": self.raw.get("port"),
            "baud_rate": self.raw.get("baud_rate"),
            "data_bits": self.raw.get("data_bits"),
            "parity": self.raw.get("parity"),
            "stop_bits": self.raw.get("stop_bits"),
            "indexing": self.raw.get("indexing"),
            "calibration_sample_hex": self.raw.get("calibration_sample_hex"),
            "status": self.raw.get("status"),
        }


def _normalize(config: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(DEFAULT_CONFIG)
    incoming = config if isinstance(config, dict) else {}
    out.update(incoming)
    for legacy in (
        "machine_id",
        "stable_count",
        "weight_scale",
        "weight_offset",
        "read_timeout_sec",
        "api_host",
        "api_port",
    ):
        out.pop(legacy, None)
    comm = deepcopy(DEFAULT_COMMUNICATION)
    incoming_comm = incoming.get("communication")
    if isinstance(incoming_comm, dict):
        mode = str(incoming_comm.get("mode") or "api").strip().lower()
        comm["mode"] = mode if mode in ("api", "mqtt") else "api"
        if isinstance(incoming_comm.get("api"), dict):
            comm["api"].update(incoming_comm["api"])
        if isinstance(incoming_comm.get("mqtt"), dict):
            comm["mqtt"].update(incoming_comm["mqtt"])
    out["communication"] = comm
    admin = deepcopy(DEFAULT_ADMIN)
    incoming_admin = incoming.get("admin")
    if isinstance(incoming_admin, dict):
        if incoming_admin.get("username") not in (None, ""):
            admin["username"] = str(incoming_admin.get("username")).strip()
        if "password" in incoming_admin and incoming_admin.get("password") is not None:
            admin["password"] = str(incoming_admin.get("password"))
    out["admin"] = admin
    if not out.get("indexing"):
        out["indexing"] = None
    # status is derived later by callers via is_calibrated(); keep False when blank
    if out.get("indexing") is None:
        out["status"] = False
    return out


def load_settings(path: Optional[str] = None) -> Settings:
    cfg_path = path or config_path()
    if not os.path.exists(cfg_path):
        data = deepcopy(DEFAULT_CONFIG)
        save_config(data, cfg_path)
        logger.info("Created blank config at %s", cfg_path)
        return Settings(raw=data, path=cfg_path)
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to load config %s: %s — using defaults", cfg_path, exc)
        loaded = {}
    data = _normalize(loaded if isinstance(loaded, dict) else {})
    return Settings(raw=data, path=cfg_path)


def save_config(config: Dict[str, Any], path: Optional[str] = None) -> bool:
    cfg_path = path or config_path()
    data = _normalize(config)
    try:
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        logger.info("Saved config to %s", cfg_path)
        return True
    except OSError as exc:
        logger.error("Failed to save config: %s", exc)
        return False


def serial_port_configured(config: Dict[str, Any]) -> bool:
    """True when COM port + serial parameters are set (indexing optional)."""
    port = str(config.get("port") or "").strip()
    if not port or port in ("--Select--", "No ports found"):
        return False
    for key in ("baud_rate", "data_bits", "parity", "stop_bits"):
        val = config.get(key)
        if val is None or val == "" or val == "--Select--":
            return False
    return True


def is_calibrated(config: Dict[str, Any]) -> bool:
    from services.index_engine import validate_indexing_for_calibration

    if not serial_port_configured(config):
        return False
    indexing = config.get("indexing")
    if not indexing or not isinstance(indexing, dict):
        return False
    if validate_indexing_for_calibration(indexing):
        return False
    return True
