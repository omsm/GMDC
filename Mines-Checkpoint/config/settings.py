"""Load settings from iot_configuration.json and environment variables."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from config.checkpoint_branding import get_brand, normalize_checkpoint_type

logger = logging.getLogger("mines_checkpoint.config")


def _package_root() -> Path:
    """Install folder when frozen; Mines-Checkpoint/ when running from source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _package_root()


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


def _resolve_mqtt_tcp_port(raw: Any) -> int:
    """Backend MQTT TCP is 1883 (ignore HTTP / WS ports from display config)."""
    try:
        port = int(raw) if raw not in (None, "") else 1883
    except (TypeError, ValueError):
        return 1883
    if port in (80, 81, 443, 8000, 8080, 8800, 8100, 9001) or port <= 0:
        return 1883
    return port


def _resolve_mqtt_ws_port(raw: Any) -> int:
    try:
        port = int(raw) if raw not in (None, "") else 9001
    except (TypeError, ValueError):
        return 9001
    return port if port > 0 else 9001


def _display_ips_from_config(
    display: Dict[str, Any], *, bidirectional: bool = False
) -> list:
    """
    Collect Display device IP(s) from iot_configuration display section.

    Uni / checkpoint: ``ip`` (primary).
    Bi-directional WB: ``ip`` (Entry A) + ``ip_b`` (Entry B).
    """
    ips = []
    primary = str(display.get("ip") or "").strip()
    if primary:
        ips.append(primary)
    secondary = str(
        display.get("ip_b")
        or display.get("ip_entry_b")
        or display.get("secondary_ip")
        or ""
    ).strip()
    if bidirectional and secondary and secondary not in ips:
        ips.append(secondary)
    # Nested list form: display.displays[{ip, role}]
    nested = display.get("displays")
    if isinstance(nested, list):
        for item in nested:
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ip") or "").strip()
            if ip and ip not in ips:
                # For uni only take first; for bi take all
                if bidirectional or not ips:
                    ips.append(ip)
                elif not bidirectional and len(ips) == 0:
                    ips.append(ip)
    return ips


def _rfid_listen_ports(blocks, *, application_port: int) -> list[int]:
    """Unique RFID_API_PORT values other than the application port."""
    try:
        app_port = int(application_port or 0)
    except (TypeError, ValueError):
        app_port = 0
    ports: list[int] = []
    seen: set[int] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        raw_port = block.get("api_port")
        if raw_port in (None, ""):
            continue
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            continue
        if port < 1 or port > 65535 or port == app_port or port in seen:
            continue
        seen.add(port)
        ports.append(port)
    return ports


@dataclass
class Settings:
    demo_mode: bool = True
    device_ip: str = "192.168.10.223"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Site profile: mines_entry | tracking_1 | tracking_2 | mines_exit
    checkpoint_type: str = "mines_entry"
    display_name: str = "Mines Entry"
    logo_initials: str = "ME"
    service_name: str = "GMDC Mines Checkpoint"
    boom_close_style: str = "entry"  # entry | tracking

    oci_base_url: str = "https://gmuatociexp.gmdcltd.co.in"
    oci_username: str = "GMDC_API_USER"
    oci_password: str = "GMDC@1234"
    rfid_validate_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag"
    invalid_truck_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number"
    update_truck_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/status_check"
    boom_close_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/boom-close"
    reset_checkpoint_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint"
    download_docs_path: str = "/ords/gmdc_dicsm/dlms_checkpoint/download/docs"

    # ANPR is a separate service (different host from OCI)
    anpr_base_url: str = "http://192.168.25.79:5001"
    anpr_detect_path: str = "/api/detect"
    anpr_username: str = "GMDC_API_USER"
    anpr_password: str = "GMDC@1234"

    # Per-endpoint Basic Auth: key -> (username, password)
    endpoint_auth: Dict[str, tuple] = field(default_factory=dict)

    # Seconds between status_check retries while vehicleStatus == 0
    truck_anpr_retry_timer: float = 2.0
    operator_username: str = "admin"
    operator_password: str = "gmdc@123"
    # Seconds to wait for exit sensor after entry granted before auto-IDLE
    vehicle_crossing_timeout: float = 10.0

    # When False, skip /api/detect; invalid-truck uses anpr_status=0
    anpr_enabled: bool = True

    # POST reset_checkpoint only when RESET_CHECKPOINT_FLAG=true
    reset_checkpoint_flag: bool = False

    # Pause after each GMDC OCI response when API_DEBUG=true (not ANPR)
    api_debug: bool = False
    api_wait_after_response: float = 0.0

    mqtt_broker: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_ws_port: int = 9001
    mqtt_topic_tx: str = "data_info/a"
    mqtt_topic_rx: str = "display_info"
    display_type: str = "mqtt"
    # Device IP(s) for display_info/{ip} / pcb_id/{ip}; pcb_mode a|b
    display_ips: list = field(default_factory=list)
    display_pcb_mode: str = "a"

    config_path: str = ""
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

    @property
    def download_docs_url(self) -> str:
        return _join_url(self.oci_base_url, self.download_docs_path)

    def io_config(self) -> Dict[str, Any]:
        return self.raw_config.get("io_controller", {})

    def rfid_config(self, key: str = "entry_a") -> Dict[str, Any]:
        return self.raw_config.get("rfids", {}).get(key, {})

    def rfid_api_listen_ports(self) -> list[int]:
        """The checkpoint RFID_API_PORT, when it is not the application port."""
        blocks = []
        rfid = self.raw_config.get("rfid") if isinstance(self.raw_config, dict) else None
        if isinstance(rfid, dict):
            blocks.append(rfid)
        entry = self.rfid_config("entry_a")
        if isinstance(entry, dict) and entry:
            blocks.append(entry)
        return _rfid_listen_ports(blocks, application_port=self.api_port)


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
    from config.constants import apply_timeouts_from_env

    apply_timeouts_from_env()

    path = Path(
        config_path
        or os.getenv("IOT_CONFIG_PATH")
        or (
            Path(os.getenv("GMDC_INSTALL_ROOT")) / "iot_configuration.json"
            if os.getenv("GMDC_INSTALL_ROOT")
            else None
        )
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
        "download_docs": _endpoint_cred(
            api_eps, "download_docs_username", "download_docs_password",
            oci_user, oci_pass,
        ),
    }

    anpr_path = api_eps.get("anpr_detect_url") or "/api/detect"
    if os.getenv("ANPR_DETECT_URL"):
        anpr_path = os.getenv("ANPR_DETECT_URL")

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
        demo_mode=_env_bool("DEMO_MODE", raw.get("demo_mode", True)),
        device_ip=device_ip,
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        checkpoint_type=checkpoint_type,
        display_name=brand.label,
        logo_initials=brand.logo,
        service_name=brand.service_name,
        boom_close_style=brand.boom_close_style,
        oci_base_url=oci_base.rstrip("/"),
        oci_username=oci_user,
        oci_password=oci_pass,
        rfid_validate_path=api_eps.get(
            "rfid_validate_url", brand.rfid_validate_path
        ),
        invalid_truck_path=api_eps.get(
            "invalid_truck_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number",
        ),
        update_truck_path=api_eps.get(
            "update_truck_url",
            brand.update_truck_path,
        ),
        boom_close_path=api_eps.get(
            "boom_close_url",
            brand.boom_close_path,
        ),
        reset_checkpoint_path=api_eps.get(
            "reset_checkpoint_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint",
        ),
        download_docs_path=api_eps.get(
            "download_docs_url",
            "/ords/gmdc_dicsm/dlms_checkpoint/download/docs",
        ),
        anpr_base_url=anpr_base.rstrip("/"),
        anpr_detect_path=anpr_path,
        anpr_username=anpr_user,
        anpr_password=anpr_pass,
        endpoint_auth=endpoint_auth,
        reset_checkpoint_flag=_env_bool("RESET_CHECKPOINT_FLAG", False),
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
        anpr_enabled=_env_bool(
            "ANPR_ENABLED",
            bool(raw.get("anpr_enabled", True)),
        ),
        api_debug=_env_bool("API_DEBUG", False) or _env_bool(
            "GMDC_API_DEBUG", False
        ),
        api_wait_after_response=float(
            os.getenv("API_WAIT_AFTER_RESPONSE")
            or os.getenv("GMDC_API_WAIT_AFTER_RESPONSE")
            or 0
        ),
        mqtt_broker=os.getenv("MQTT_BROKER") or "127.0.0.1",
        mqtt_port=_resolve_mqtt_tcp_port(
            os.getenv("MQTT_PORT") or display.get("port") or "1883"
        ),
        mqtt_ws_port=_resolve_mqtt_ws_port(os.getenv("MQTT_WS_PORT") or "9001"),
        mqtt_topic_tx=display.get("mqtt_topic_tx") or "data_info/a",
        mqtt_topic_rx=display.get("mqtt_topic_rx") or "display_info",
        display_type=(display.get("type") or "mqtt").lower(),
        display_ips=_display_ips_from_config(display, bidirectional=False),
        display_pcb_mode="a",
        config_path=str(path),
        raw_config=raw,
    )
    logger.info(
        "Mines-Checkpoint type=%s boom_style=%s anpr_enabled=%s OCI=%s ANPR=%s",
        settings.checkpoint_type,
        settings.boom_close_style,
        settings.anpr_enabled,
        settings.oci_base_url,
        settings.anpr_detect_url,
    )
    return settings


def persist_anpr_enabled(settings: Settings, enabled: bool) -> bool:
    """Update in-memory settings and write anpr_enabled to iot_configuration.json."""
    settings.anpr_enabled = bool(enabled)
    if isinstance(settings.raw_config, dict):
        settings.raw_config["anpr_enabled"] = bool(enabled)
    path = Path(settings.config_path) if settings.config_path else Path()
    if not path.is_file():
        logger.warning("Cannot persist anpr_enabled - config file missing: %s", path)
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
        data["anpr_enabled"] = bool(enabled)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        logger.info("Persisted anpr_enabled=%s to %s", enabled, path)
        return True
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.error("Failed to persist anpr_enabled: %s", e)
        return False
