"""Load settings from iot_configuration.json and environment variables."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

logger = logging.getLogger("tracking_point.config")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _join_url(base: str, path_or_url: str) -> str:
    """If path_or_url is absolute (http/https), return it; else join with base."""
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

    oci_base_url: str = "https://gmuatociexp.gmdcltd.co.in"
    oci_username: str = "GMDC_API_USER"
    oci_password: str = "GMDC@1234"
    rfid_validate_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag"
    invalid_truck_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number"
    update_truck_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status"
    boom_close_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close"
    reset_checkpoint_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint"

    # ANPR is a separate service (different host from OCI)
    anpr_base_url: str = "http://192.168.25.79:5001"
    anpr_detect_path: str = "/api/detect"
    anpr_username: str = "GMDC_API_USER"
    anpr_password: str = "GMDC@1234"

    # Per-endpoint Basic Auth: key -> (username, password)
    endpoint_auth: Dict[str, tuple] = field(default_factory=dict)

    operator_username: str = "admin"
    operator_password: str = "gmdc@123"

    # Seconds between status_check retries while vehicleStatus == 0
    truck_anpr_retry_timer: float = 2.0
    # Seconds to wait for exit sensor after entry granted before auto-IDLE
    vehicle_crossing_timeout: float = 10.0

    mqtt_broker: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_topic_tx: str = "iot_display/application_to_display"
    mqtt_topic_rx: str = "iot_display/display_to_application"
    display_type: str = "mqtt"

    front_camera_rtsp_url: str = ""
    top_camera_rtsp_url: str = ""

    raw_config: Dict[str, Any] = field(default_factory=dict)

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

    def io_config(self) -> Dict[str, Any]:
        return self.raw_config.get("io_controller", {})

    def rfid_config(self, key: str = "entry_a") -> Dict[str, Any]:
        return self.raw_config.get("rfids", {}).get(key, {})


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _endpoint_cred(
    api_eps: Dict[str, Any],
    user_key: str,
    pass_key: str,
    fallback_user: str,
    fallback_pass: str,
) -> tuple:
    user = str(api_eps.get(user_key) or fallback_user or "")
    password = str(api_eps.get(pass_key) or fallback_pass or "")
    return (user, password)


def load_settings(config_path: Optional[str] = None) -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")

    path = Path(
        config_path
        or os.getenv("IOT_CONFIG_PATH")
        or (PROJECT_ROOT / "iot_configuration.json")
    )
    raw: Dict[str, Any] = {}
    if path.is_file():
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        logger.info("Loaded IoT config from %s", path)
    else:
        logger.warning("IoT config not found at %s - using defaults", path)

    api_eps = raw.get("api_endpoints", {})
    display = raw.get("display", {})
    camera = raw.get("camera", {}) or {}
    front_cam = camera.get("front", {}) if isinstance(camera.get("front"), dict) else {}
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
        "boom_close": _endpoint_cred(
            api_eps, "boom_close_username", "boom_close_password",
            oci_user, oci_pass,
        ),
        "reset_checkpoint": _endpoint_cred(
            api_eps, "reset_checkpoint_username", "reset_checkpoint_password",
            oci_user, oci_pass,
        ),
    }

    anpr_path = api_eps.get("anpr_detect_url") or "/api/detect"
    if os.getenv("ANPR_DETECT_URL"):
        anpr_path = os.getenv("ANPR_DETECT_URL")

    settings = Settings(
        demo_mode=_env_bool("DEMO_MODE", raw.get("demo_mode", True)),
        device_ip=os.getenv("DEVICE_IP", "192.168.10.223"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        oci_base_url=oci_base.rstrip("/"),
        oci_username=oci_user,
        oci_password=oci_pass,
        rfid_validate_path=api_eps.get(
            "rfid_validate_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/rfid-tag",
        ),
        invalid_truck_path=api_eps.get(
            "invalid_truck_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number",
        ),
        update_truck_path=api_eps.get(
            "update_truck_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/checkpoint/check-status",
        ),
        boom_close_path=api_eps.get(
            "boom_close_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/checkpoint_boom_close",
        ),
        reset_checkpoint_path=api_eps.get(
            "reset_checkpoint_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint",
        ),
        anpr_base_url=anpr_base.rstrip("/"),
        anpr_detect_path=anpr_path,
        anpr_username=anpr_user,
        anpr_password=anpr_pass,
        endpoint_auth=endpoint_auth,
        truck_anpr_retry_timer=float(
            os.getenv("TRUCK_ANPR_RETRY_TIMER")
            or raw.get("truck_anpr_retry_timer")
            or 2
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
        vehicle_crossing_timeout=float(
            os.getenv("VEHICLE_CROSSING_TIMEOUT")
            or raw.get("vehicle_crossing_timeout")
            or 10
        ),
        mqtt_broker=os.getenv("MQTT_BROKER")
        or display.get("ip")
        or "127.0.0.1",
        mqtt_port=int(os.getenv("MQTT_PORT") or display.get("port") or "1883"),
        mqtt_topic_tx=display.get(
            "mqtt_topic_tx", "iot_display/application_to_display"
        ),
        mqtt_topic_rx=display.get(
            "mqtt_topic_rx", "iot_display/display_to_application"
        ),
        display_type=(display.get("type") or "mqtt").lower(),
        front_camera_rtsp_url=str(
            os.getenv("FRONT_CAMERA_RTSP")
            or front_cam.get("rtsp_url")
            or ""
        ).strip(),
        top_camera_rtsp_url=str(
            os.getenv("TOP_CAMERA_RTSP")
            or top_cam.get("rtsp_url")
            or ""
        ).strip(),
        raw_config=raw,
    )
    logger.info(
        "API URLs: RFID=%s invalid-truck=%s check-status=%s boom-close=%s ANPR=%s",
        settings.rfid_validate_url,
        settings.invalid_truck_url,
        settings.update_truck_url,
        settings.boom_close_url,
        settings.anpr_detect_url,
    )
    return settings
