"""Load settings from checkpoint-config/iot_configuration.json (or local override)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from config.wb_branding import get_brand, normalize_checkpoint_type

logger = logging.getLogger("mines_wb.config")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_CONFIG_CANDIDATES = (
    PROJECT_ROOT / "iot_configuration.json",
    WORKSPACE_ROOT / "checkpoint-config" / "iot_configuration.json",
)


def _join_url(base: str, path_or_url: str) -> str:
    p = (path_or_url or "").strip()
    if p.lower().startswith("http://") or p.lower().startswith("https://"):
        return p.rstrip("/")
    base = (base or "").rstrip("/")
    if not p:
        return base
    if not p.startswith("/"):
        p = "/" + p
    return base + p


@dataclass
class Settings:
    demo_mode: bool = True
    device_ip: str = "192.168.10.223"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    checkpoint_type: str = "tare_wb"
    wb_type: str = "unidirectional"
    display_name: str = "Tare Weighbridge"
    logo_initials: str = "TW"
    service_name: str = "GMDC Mines WB"

    oci_base_url: str = "https://gmuatociexp.gmdcltd.co.in"
    oci_username: str = "GMDC_API_USER"
    oci_password: str = "GMDC@1234"
    rfid_validate_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag"
    invalid_truck_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number"
    update_truck_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/status_check"
    boom_close_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/boom-close"
    reset_checkpoint_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint"
    weight_details_path: str = (
        "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details"
    )
    weight_confirm_path: str = (
        "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-confirm"
    )
    gross_tolerance_confirm_path: str = (
        "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-tolerance-confirm"
    )
    vadhghat_weight_adjustment_path: str = (
        "/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment"
    )

    anpr_base_url: str = "http://192.168.25.79:5001"
    anpr_detect_path: str = "/api/detect"
    anpr_username: str = "GMDC_API_USER"
    anpr_password: str = "GMDC@1234"
    # Seconds between status_check polls while vehicleStatus == 0
    truck_anpr_retry_timer: float = 5.0
    operator_username: str = "admin"
    operator_password: str = "gmdc@123"
    # After each GMDC (non-ANPR) API response, pause so logs are easier to read
    api_debug: bool = False
    api_wait_after_response: float = 0.0

    # Per-endpoint Basic Auth: key -> (username, password)
    endpoint_auth: Dict[str, tuple] = field(default_factory=dict)

    digitizer_host: str = ""
    digitizer_port: int = 8100
    digitizer_path: str = "/read_stable_weight"
    digitizer_timeout: float = 30.0
    digitizer_stable_count: int = 10
    min_weight_kg: float = 5000.0

    # Top Camera RTSP from checkpoint-config camera.top
    top_camera_rtsp_url: str = ""

    mqtt_broker: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_topic_tx: str = "iot_display/application_to_display"
    mqtt_topic_rx: str = "iot_display/display_to_application"
    display_type: str = "mqtt"

    voice_enabled: bool = True
    voice_validated: bool = True
    voice_directory: str = "voice"
    voice_error_prefix: bool = True
    voice_path: str = ""  # resolved absolute directory

    config_path: str = ""
    raw_config: Dict[str, Any] = field(default_factory=dict)

    def use_audio(self) -> bool:
        """Match wb-old: enabled AND validated."""
        return bool(self.voice_enabled and self.voice_validated)

    @property
    def rfid_validate_url(self) -> str:
        return _join_url(self.oci_base_url, self.rfid_validate_path)

    @property
    def anpr_detect_url(self) -> str:
        return _join_url(self.anpr_base_url, self.anpr_detect_path)

    @property
    def invalid_truck_url(self) -> str:
        return _join_url(self.oci_base_url, self.invalid_truck_path)

    @property
    def update_truck_url(self) -> str:
        return _join_url(self.oci_base_url, self.update_truck_path)

    @property
    def boom_close_url(self) -> str:
        return _join_url(self.oci_base_url, self.boom_close_path)

    @property
    def reset_checkpoint_url(self) -> str:
        return _join_url(self.oci_base_url, self.reset_checkpoint_path)

    @property
    def weight_details_url(self) -> str:
        return _join_url(self.oci_base_url, self.weight_details_path)

    @property
    def weight_confirm_url(self) -> str:
        return _join_url(self.oci_base_url, self.weight_confirm_path)

    @property
    def gross_tolerance_confirm_url(self) -> str:
        return _join_url(self.oci_base_url, self.gross_tolerance_confirm_path)

    @property
    def vadhghat_weight_adjustment_url(self) -> str:
        return _join_url(self.oci_base_url, self.vadhghat_weight_adjustment_path)

    @property
    def digitizer_url(self) -> str:
        host = self.digitizer_host or "127.0.0.1"
        path = self.digitizer_path or "/read_stable_weight"
        if not path.startswith("/"):
            path = "/" + path
        return f"http://{host}:{self.digitizer_port}{path}"

    def io_config(self) -> Dict[str, Any]:
        return self.raw_config.get("io_controller", {})

    def is_bidirectional(self) -> bool:
        return str(self.wb_type or "").strip().lower() == "bidirectional"

    def rfid_configs(self) -> Dict[str, Dict[str, Any]]:
        """Return direction-keyed fixed RFID reader configs."""
        if self.is_bidirectional():
            rfids = self.raw_config.get("rfids") or {}
            return {
                key: dict(rfids.get(key) or {})
                for key in ("entry_a", "entry_b")
                if isinstance(rfids.get(key), dict)
            }
        rfid = self.raw_config.get("rfid")
        return {"entry_a": dict(rfid)} if isinstance(rfid, dict) else {}

    def rfid_config(self, direction: str = "entry_a") -> Dict[str, Any]:
        """Return the active direction's fixed Zebra reader block."""
        if isinstance(self.raw_config.get("rfid"), dict):
            return self.raw_config["rfid"]
        rfids = self.raw_config.get("rfids") or {}
        key = str(direction or "entry_a").strip().lower()
        if isinstance(rfids.get(key), dict):
            return rfids[key]
        return {}

    def digitizer_config(self) -> Dict[str, Any]:
        return self.raw_config.get("digitizer", {}) or {}

    def handheld_config(self) -> Dict[str, Any]:
        return self.raw_config.get("handheld_rfid", {}) or {}


def _endpoint_cred(
    api_eps: Dict[str, Any],
    user_key: str,
    pass_key: str,
    fallback_user: str,
    fallback_pass: str,
) -> tuple:
    return (
        str(api_eps.get(user_key) or fallback_user or ""),
        str(api_eps.get(pass_key) or fallback_pass or ""),
    )


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def resolve_config_path(config_path: Optional[str] = None) -> Path:
    if config_path:
        return Path(config_path)
    env = os.getenv("IOT_CONFIG_PATH")
    if env:
        return Path(env)
    for candidate in DEFAULT_CONFIG_CANDIDATES:
        if candidate.is_file():
            return candidate
    return DEFAULT_CONFIG_CANDIDATES[0]


def load_settings(config_path: Optional[str] = None) -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    from config.constants import apply_timeouts_from_env

    apply_timeouts_from_env()

    path = resolve_config_path(config_path)
    raw: Dict[str, Any] = {}
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        logger.info("Loaded IoT config from %s", path)
    else:
        logger.warning("IoT config not found at %s - using defaults", path)

    api_eps = raw.get("api_endpoints", {}) or {}
    display = raw.get("display", {}) or {}
    dig = raw.get("digitizer", {}) or {}
    voice = raw.get("voice", {}) or {}
    camera = raw.get("camera", {}) or {}
    top_cam = camera.get("top", {}) if isinstance(camera.get("top"), dict) else {}

    oci_base = (
        os.getenv("OCI_BASE_URL")
        or api_eps.get("oci_base_url")
        or "https://gmuatociexp.gmdcltd.co.in"
    )
    anpr_base = (
        os.getenv("ANPR_BASE_URL")
        or api_eps.get("anpr_base_url")
        or "http://192.168.25.79:5001"
    )
    oci_user = (
        os.getenv("OCI_USERNAME")
        or api_eps.get("oci_username")
        or "GMDC_API_USER"
    )
    oci_pass = (
        os.getenv("OCI_PASSWORD")
        or api_eps.get("oci_password")
        or "GMDC@1234"
    )
    anpr_user = (
        os.getenv("ANPR_USERNAME")
        or api_eps.get("anpr_detect_username")
        or api_eps.get("anpr_username")
        or oci_user
    )
    anpr_pass = (
        os.getenv("ANPR_PASSWORD")
        or api_eps.get("anpr_detect_password")
        or api_eps.get("anpr_password")
        or oci_pass
    )

    endpoint_auth = {
        "rfid_validate": _endpoint_cred(
            api_eps, "rfid_validate_username", "rfid_validate_password",
            oci_user, oci_pass,
        ),
        "anpr_detect": _endpoint_cred(
            api_eps, "anpr_detect_username", "anpr_detect_password",
            anpr_user, anpr_pass,
        ),
        "invalid_truck": _endpoint_cred(
            api_eps, "invalid_truck_username", "invalid_truck_password",
            oci_user, oci_pass,
        ),
        "update_truck": _endpoint_cred(
            api_eps, "update_truck_username", "update_truck_password",
            oci_user, oci_pass,
        ),
        "weight_details": _endpoint_cred(
            api_eps, "weight_details_username", "weight_details_password",
            oci_user, oci_pass,
        ),
        "boom_close": _endpoint_cred(
            api_eps, "boom_close_username", "boom_close_password",
            oci_user, oci_pass,
        ),
        "reset_checkpoint": _endpoint_cred(
            api_eps, "reset_checkpoint_username", "reset_checkpoint_password",
            oci_user, oci_pass,
        ),
        "weight_confirm": _endpoint_cred(
            api_eps, "weight_confirm_username", "weight_confirm_password",
            api_eps.get("weight_details_username") or oci_user,
            api_eps.get("weight_details_password") or oci_pass,
        ),
        "gross_tolerance_confirm": _endpoint_cred(
            api_eps,
            "gross_tolerance_confirm_username",
            "gross_tolerance_confirm_password",
            api_eps.get("weight_details_username") or oci_user,
            api_eps.get("weight_details_password") or oci_pass,
        ),
        "vadhghat_weight_adjustment": _endpoint_cred(
            api_eps,
            "vadhghat_weight_adjustment_username",
            "vadhghat_weight_adjustment_password",
            api_eps.get("weight_details_username") or oci_user,
            api_eps.get("weight_details_password") or oci_pass,
        ),
    }

    dig_port = dig.get("port") or "8100"
    try:
        dig_port_i = int(dig_port)
    except (TypeError, ValueError):
        dig_port_i = 8100

    checkpoint_type = normalize_checkpoint_type(
        os.getenv("CHECKPOINT_TYPE") or raw.get("checkpoint_type")
    )
    brand = get_brand(checkpoint_type)

    # Prefer LAN IP written by checkpoint-config finish; .env DEVICE_IP is fallback only
    config_device_ip = str(raw.get("device_ip") or "").strip()
    env_device_ip = str(os.getenv("DEVICE_IP") or "").strip()
    device_ip = config_device_ip or env_device_ip or "192.168.10.223"
    if config_device_ip:
        logger.info("device_ip from iot_configuration.json: %s", config_device_ip)
    elif env_device_ip:
        logger.warning(
            "device_ip missing in IoT config - using DEVICE_IP from .env: %s",
            env_device_ip,
        )

    settings = Settings(
        demo_mode=_env_bool("DEMO_MODE", bool(raw.get("demo_mode", True))),
        device_ip=device_ip,
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT") or raw.get("server", {}).get("port") or 8000),
        checkpoint_type=checkpoint_type,
        wb_type=str(raw.get("wb_type") or "unidirectional"),
        display_name=brand.label,
        logo_initials=brand.logo,
        service_name=brand.service_name,
        oci_base_url=oci_base.rstrip("/"),
        oci_username=oci_user,
        oci_password=oci_pass,
        rfid_validate_path=api_eps.get(
            "rfid_validate_url", "/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag"
        ),
        invalid_truck_path=api_eps.get(
            "invalid_truck_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number",
        ),
        update_truck_path=api_eps.get(
            "update_truck_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/status_check",
        ),
        boom_close_path=api_eps.get(
            "boom_close_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/boom-close",
        ),
        reset_checkpoint_path=api_eps.get(
            "reset_checkpoint_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint",
        ),
        weight_details_path=api_eps.get(
            "weight_details_url",
            "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details",
        ),
        weight_confirm_path=api_eps.get(
            "weight_confirm_url",
            "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-confirm",
        ),
        gross_tolerance_confirm_path=api_eps.get(
            "gross_tolerance_confirm_url",
            "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-tolerance-confirm",
        ),
        vadhghat_weight_adjustment_path=api_eps.get(
            "vadhghat_weight_adjustment_url",
            "/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment",
        ),
        anpr_base_url=anpr_base.rstrip("/"),
        anpr_detect_path=api_eps.get("anpr_detect_url") or "/api/detect",
        anpr_username=anpr_user,
        anpr_password=anpr_pass,
        truck_anpr_retry_timer=float(
            os.getenv("TRUCK_ANPR_RETRY_TIMER")
            or raw.get("truck_anpr_retry_timer")
            or 5.0
        ),
        operator_username=str(
            os.getenv("OPERATOR_USERNAME")
            or api_eps.get("operator_username")
            or "admin"
        ),
        operator_password=str(
            os.getenv("OPERATOR_PASSWORD")
            or api_eps.get("operator_password")
            or "gmdc@123"
        ),
        api_debug=_env_bool("API_DEBUG", False) or _env_bool(
            "GMDC_API_DEBUG", False
        ),
        api_wait_after_response=float(
            os.getenv("API_WAIT_AFTER_RESPONSE")
            or os.getenv("GMDC_API_WAIT_AFTER_RESPONSE")
            or 0
        ),
        endpoint_auth=endpoint_auth,
        digitizer_host=str(dig.get("host") or os.getenv("DIGITIZER_HOST") or ""),
        digitizer_port=int(os.getenv("DIGITIZER_PORT") or dig_port_i),
        digitizer_path=str(
            dig.get("path") or os.getenv("DIGITIZER_PATH") or "/read_stable_weight"
        ),
        digitizer_timeout=float(
            os.getenv("DIGITIZER_TIMEOUT") or dig.get("timeout") or 30
        ),
        digitizer_stable_count=int(
            os.getenv("DIGITIZER_STABLE_COUNT") or dig.get("stable_count") or 10
        ),
        min_weight_kg=float(os.getenv("MIN_WEIGHT_KG") or 5000),
        top_camera_rtsp_url=str(
            os.getenv("TOP_CAMERA_RTSP_URL")
            or top_cam.get("rtsp_url")
            or ""
        ).strip(),
        mqtt_broker=os.getenv("MQTT_BROKER") or (display.get("ip") or "").strip() or "",
        mqtt_port=int(
            os.getenv("MQTT_PORT")
            or (
                display.get("port")
                if (display.get("ip") or "").strip()
                else "1883"
            )
            or "1883"
        ),
        mqtt_topic_tx=display.get(
            "mqtt_topic_tx", "iot_display/application_to_display"
        ),
        mqtt_topic_rx=display.get(
            "mqtt_topic_rx", "iot_display/display_to_application"
        ),
        # Empty IP → console (avoids MQTT hang on bogus 127.0.0.1:8000)
        display_type=(
            "console"
            if not (display.get("ip") or "").strip()
            else (display.get("type") or "mqtt").lower()
        ),
        voice_enabled=_env_bool(
            "VOICE_ENABLED",
            bool(voice.get("enabled", True)),
        ),
        voice_validated=bool(voice.get("validated", True)),
        voice_directory=str(
            os.getenv("VOICE_DIRECTORY") or voice.get("directory") or "voice"
        ),
        voice_error_prefix=bool(voice.get("error_prefix", True)),
        config_path=str(path),
        raw_config=raw,
    )

    from gmdc_common.services.voice_service import resolve_voice_directory

    legacy_voice = (
        WORKSPACE_ROOT / "wb-old" / "Weighbridge-App" / "voice"
    )
    settings.voice_path = resolve_voice_directory(
        str(PROJECT_ROOT),
        configured=settings.voice_directory,
        extra_candidates=[str(legacy_voice)],
    )
    logger.info(
        "Mines WB settings: type=%s config=%s digitizer=%s OCI=%s ANPR=%s "
        "demo=%s voice=%s top_camera=%s",
        settings.checkpoint_type,
        settings.config_path,
        settings.digitizer_url,
        settings.oci_base_url,
        settings.anpr_detect_url,
        settings.demo_mode,
        settings.voice_path if settings.use_audio() else "off",
        "set" if settings.top_camera_rtsp_url else "missing",
    )
    return settings
