"""
Ensure a local Mosquitto broker is listening on MQTT 1883 and WS 9001.

If either port is not accepting connections, runs the bundled installer
(mosquitto_setup.setup_mosquitto): install → write conf → start service.
"""

from __future__ import annotations

import logging
import socket
import sys
import time
from typing import Any, Callable, Optional, Tuple

logger = logging.getLogger("mqtt_broker_setup.ensure")

MQTT_PORT = 1883
WS_PORT = 9001

ProgressCallback = Optional[Callable[[int, str], None]]


def _port_open(host: str, port: int, timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def mqtt_ports_ready(
    host: str = "127.0.0.1",
    mqtt_port: int = MQTT_PORT,
    ws_port: int = WS_PORT,
) -> bool:
    """True when both backend MQTT and frontend WebSocket ports accept TCP."""
    mqtt_ok = _port_open(host, mqtt_port)
    ws_ok = _port_open(host, ws_port)
    logger.info(
        "Local MQTT ports: %s:%s=%s  %s:%s=%s",
        host,
        mqtt_port,
        "up" if mqtt_ok else "down",
        host,
        ws_port,
        "up" if ws_ok else "down",
    )
    return mqtt_ok and ws_ok


def _wait_for_ports(
    host: str = "127.0.0.1",
    mqtt_port: int = MQTT_PORT,
    ws_port: int = WS_PORT,
    attempts: int = 20,
    delay_sec: float = 0.5,
) -> bool:
    for i in range(attempts):
        if mqtt_ports_ready(host, mqtt_port, ws_port):
            return True
        time.sleep(delay_sec)
        if i and i % 4 == 0:
            logger.info(
                "Waiting for Mosquitto on %s/%s (try %s/%s)...",
                mqtt_port,
                ws_port,
                i + 1,
                attempts,
            )
    return mqtt_ports_ready(host, mqtt_port, ws_port)


def ensure_mqtt_broker_ready(
    app_data_path: Optional[str] = None,
    progress_callback: ProgressCallback = None,
    force_setup: bool = False,
    host: str = "127.0.0.1",
    mqtt_port: int = MQTT_PORT,
    ws_port: int = WS_PORT,
) -> Tuple[bool, str]:
    """
    Ensure local Mosquitto is installed, configured (1883 + 9001), and running.

    Returns:
        (success, message)
    """
    def _progress(percent: int, message: str) -> None:
        if progress_callback:
            try:
                progress_callback(percent, message)
            except Exception:
                pass
        logger.info("[%s%%] %s", percent, message)

    try:
        if not force_setup and mqtt_ports_ready(host, mqtt_port, ws_port):
            msg = (
                f"MQTT broker already listening on {mqtt_port} (mqtt) "
                f"and {ws_port} (websocket)"
            )
            _progress(100, msg)
            return True, msg

        _progress(
            0,
            f"MQTT broker not ready on {mqtt_port}/{ws_port} — "
            "installing/configuring Mosquitto...",
        )

        # Local import so path setup in callers is enough
        from mosquitto_setup import setup_mosquitto  # type: ignore

        status = setup_mosquitto(
            progress_callback=_progress,
            app_data_path=app_data_path,
        )
        if not isinstance(status, dict):
            return False, "Mosquitto setup returned unexpected result"

        if not status.get("success"):
            message = status.get("message") or "Mosquitto setup failed"
            # Still succeed if ports came up (e.g. service start reported soft fail)
            if _wait_for_ports(host, mqtt_port, ws_port, attempts=6):
                return True, (
                    f"MQTT broker is listening on {mqtt_port}/{ws_port} "
                    f"(setup reported: {message})"
                )
            return False, message

        if _wait_for_ports(host, mqtt_port, ws_port):
            msg = status.get("message") or (
                f"Mosquitto ready on {mqtt_port} (mqtt) and {ws_port} (ws)"
            )
            return True, msg

        return False, (
            "Mosquitto setup finished but ports "
            f"{mqtt_port} and/or {ws_port} are not accepting connections. "
            "Check mosquitto.conf listeners and the broker service."
        )
    except Exception as exc:
        logger.exception("ensure_mqtt_broker_ready failed")
        # Last chance: ports may already be up from a previous install
        if mqtt_ports_ready(host, mqtt_port, ws_port):
            return True, (
                f"MQTT ports {mqtt_port}/{ws_port} are up "
                f"(ensure error ignored: {exc})"
            )
        return False, f"MQTT broker ensure failed: {exc}"


def resolve_mqtt_tcp_port(raw_port: Any = None) -> int:
    """
    Backend MQTT TCP port is always 1883.

    Display/API HTTP ports (80, 81, 8000, …) and WS port 9001 must not be used
    as the paho-mqtt TCP connect port.
    """
    try:
        port = int(raw_port) if raw_port not in (None, "") else MQTT_PORT
    except (TypeError, ValueError):
        return MQTT_PORT
    if port in (80, 81, 443, 8000, 8080, 8800, 8100, WS_PORT) or port <= 0:
        return MQTT_PORT
    return port


def resolve_mqtt_ws_port(raw_port: Any = None) -> int:
    """Frontend MQTT-over-WebSocket port is always 9001."""
    try:
        port = int(raw_port) if raw_port not in (None, "") else WS_PORT
    except (TypeError, ValueError):
        return WS_PORT
    return port if port > 0 else WS_PORT


def add_package_to_sys_path() -> str:
    """
    Insert this package directory on sys.path so `mosquitto_setup` imports work.
    Returns the package directory path.
    """
    import os

    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    parent = os.path.dirname(pkg_dir)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return pkg_dir


def bootstrap_local_mqtt(
    caller_file: str,
    *,
    fatal: bool = False,
) -> Tuple[bool, str]:
    """
    Ensure Mosquitto on 1883 + 9001 for any GMDC app.

    Resolves repo-root ``mqtt_broker_setup`` from the caller's ``__file__``
    (app lives one level under the monorepo root).
    """
    import os
    from pathlib import Path

    app_dir = Path(caller_file).resolve().parent
    repo_root = app_dir.parent
    shared = repo_root / "mqtt_broker_setup"
    for path in (str(shared), str(repo_root)):
        if path not in sys.path:
            sys.path.insert(0, path)

    add_package_to_sys_path()
    ok, message = ensure_mqtt_broker_ready(app_data_path=str(app_dir))
    if ok:
        logger.info("MQTT broker ready: %s", message)
    else:
        logger.error("MQTT broker not ready: %s", message)
        logger.error(
            "Need listeners on %s (mqtt) and %s (websocket)",
            MQTT_PORT,
            WS_PORT,
        )
        if fatal:
            raise RuntimeError(message)
    return ok, message
