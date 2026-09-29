"""
GMDC Digitizer Decoder — web-based weighbridge digitizer service.

Replaces the PySide serial_ui desktop shell with a Flask dashboard that keeps
the same serial indexing / stable-weight logic, and adds selectable transport:

  - API  → POST/GET /read_stable_weight (Mines-WB compatible)
  - MQTT → subscribe for requests, publish stable-weight JSON

Usage:
  cd digitizer-decoder
  pip install -r requirements.txt
  python main.py
"""

from __future__ import annotations

# "auto" follows the OS. "macos" forces liquid glass. "windows" forces the earlier UI.
OS_TYPE = "auto"

import logging
import os
import sys

# Ensure package root is on sys.path when launched as script
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.server import start_api_server
from config.settings import load_settings, version_string
from core.app_context import AppContext


def setup_logging() -> None:
    log_dir = os.path.join(ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                os.path.join(log_dir, "digitizer_decoder.log"), encoding="utf-8"
            ),
        ],
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger("digitizer_decoder.main")

    # Ensure local Mosquitto on 1883 (MQTT) + 9001 (WS) before MQTT mode connects
    try:
        repo_root = os.path.dirname(ROOT)
        for path in (os.path.join(repo_root, "mqtt_broker_setup"), repo_root):
            if path not in sys.path:
                sys.path.insert(0, path)
        from mqtt_broker_setup import bootstrap_local_mqtt

        bootstrap_local_mqtt(__file__)
    except Exception as exc:
        logger.exception("MQTT broker ensure failed: %s", exc)

    settings = load_settings()
    version = version_string()
    ctx = AppContext.get_instance()
    ctx.bootstrap(settings, version=version)

    # Prefer dedicated UI port; also expose weight API on same server so
    # Mines-WB can point digitizer URL at this host:port/read_stable_weight.
    # If ui_port differs from api.port, we bind ui_port for the dashboard and
    # document that API mode should use the same process URL.
    bind_host = str(settings.api_cfg.get("host") or "0.0.0.0")
    # Serve everything on the weight API port when mode=api so WB keeps working
    # on :8800; otherwise use ui_port (MQTT-only sites still get a dashboard).
    if settings.communication_mode == "api":
        bind_port = int(settings.api_cfg.get("port") or settings.ui_port or 8800)
    else:
        bind_port = int(settings.ui_port or settings.api_cfg.get("port") or 8765)

    mqtt_port = int((settings.mqtt_cfg or {}).get("broker_port") or 1883)
    logger.info(
        "Digitizer Decoder v%s mode=%s serial=%s bind=%s:%s mqtt=%s",
        version,
        settings.communication_mode,
        settings.raw.get("port"),
        bind_host,
        bind_port,
        mqtt_port,
    )
    print(
        f"\nGMDC Digitizer Decoder v{version}\n"
        f"  Mode       : {settings.communication_mode.upper()}\n"
        f"  Dashboard  : http://127.0.0.1:{bind_port}/\n"
        f"  Weight API : http://127.0.0.1:{bind_port}/read_stable_weight\n"
        f"  MQTT TCP   : broker port {mqtt_port} (default 1883)\n"
        f"  MQTT WS    : ws://<this-pc-ip>:9001 (frontend / Mosquitto)\n"
        f"  Serial     : {settings.raw.get('port')} "
        f"(calibrated={settings.raw.get('status')})\n"
    )
    start_api_server(bind_host, bind_port, os_type=OS_TYPE)


if __name__ == "__main__":
    main()
