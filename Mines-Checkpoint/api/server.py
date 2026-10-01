"""Flask API server (background thread) + operator web dashboard."""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Optional

from flask import Flask, Response, jsonify, send_from_directory

from api.endpoints import register_routes
from utils.ui_os import inject_liquid_glass, liquid_glass_enabled

logger = logging.getLogger("mines_checkpoint.api.server")

_app: Optional[Flask] = None
_thread: Optional[threading.Thread] = None


def _resolve_static_web_dir() -> str:
    """Source tree, or PyInstaller _MEIPASS / install-dir when frozen."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        candidates = []
        if meipass:
            candidates.append(os.path.join(meipass, "static", "web"))
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "static", "web"))
        for path in candidates:
            if os.path.isdir(path):
                return os.path.abspath(path)
        return os.path.abspath(candidates[0])
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "static", "web")
    )


STATIC_WEB_DIR = _resolve_static_web_dir()


def _add_cors(app: Flask) -> None:
    try:
        from flask_cors import CORS

        CORS(app, resources={r"/*": {"origins": "*"}})
        return
    except ImportError:
        logger.warning("flask-cors not installed - using Access-Control-Allow-Origin *")

    @app.after_request
    def _cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response


def _dashboard_html(filename: str, *, liquid_glass: bool) -> Response:
    path = os.path.join(STATIC_WEB_DIR, filename)
    with open(path, encoding="utf-8") as handle:
        html = handle.read()
    if liquid_glass:
        html = inject_liquid_glass(html)
    return Response(html, mimetype="text/html")


def create_app(os_type: str = "auto") -> Flask:
    global _app
    app = Flask("mines_checkpoint", static_folder=None, template_folder=None)
    _add_cors(app)
    liquid_glass = liquid_glass_enabled(os_type)
    logger.info("Dashboard UI: %s (OS_TYPE=%s)", "liquid-glass" if liquid_glass else "classic", os_type)

    if os.path.isdir(STATIC_WEB_DIR):
        logger.info("Serving operator web UI from %s", STATIC_WEB_DIR)

        @app.get("/")
        def index():
            return _dashboard_html("index.html", liquid_glass=liquid_glass)

        @app.get("/static/<path:filename>")
        def serve_static(filename: str):
            return send_from_directory(STATIC_WEB_DIR, filename)
    else:
        logger.error("Static web directory missing: %s", STATIC_WEB_DIR)

        @app.get("/")
        def index_fallback():
            return jsonify(
                {
                    "service": "GMDC Mines Checkpoint",
                    "status": "running",
                    "error": f"Static directory not found: {STATIC_WEB_DIR}",
                }
            )

    register_routes(app)
    _app = app
    return app


def start_rfid_api_ports(app: Flask, host: str, ports: list[int]) -> None:
    """Listen for RFID tag push on each configured RFID_API_PORT.

    The application port already serves /rfid_data. These extra ports are the
    ones saved on the readers, and they stay open for the life of the process.
    """
    if not ports:
        logger.info("RFID data is served on the application port only")
        return
    from werkzeug.serving import make_server

    for port in ports:
        try:
            server = make_server(host, int(port), app, threaded=True)
        except OSError as exc:
            logger.error(
                "RFID API port %s did not open (%s). Reader posts to this port will fail.",
                port,
                exc,
            )
            continue

        threading.Thread(
            target=server.serve_forever,
            name=f"RfidApi-{port}",
            daemon=True,
        ).start()
        logger.info(
            "RFID data port open on %s:%s (POST /rfid_data, /rfid_management)",
            host,
            port,
        )


def start_api_server(host: str = "0.0.0.0", port: int = 8080, os_type: str = "auto") -> Flask:
    global _thread
    app = create_app(os_type=os_type)

    def _run():
        logger.info("Starting Flask API + web UI on %s:%s", host, port)
        app.run(host=host, port=port, threaded=True, use_reloader=False)

    _thread = threading.Thread(target=_run, name="FlaskAPI", daemon=True)
    _thread.start()
    _open_dashboard_when_ready(int(port))
    return app


def _open_dashboard_when_ready(port: int, *, delay_sec: float = 1.25) -> None:
    """Open the operator UI in the default browser once Flask is listening."""
    if os.environ.get("GMDC_NO_BROWSER", "").strip().lower() in ("1", "true", "yes"):
        logger.info("Skipping browser open (GMDC_NO_BROWSER set)")
        return

    def _open():
        import time
        import webbrowser

        time.sleep(max(0.2, float(delay_sec)))
        url = f"http://127.0.0.1:{int(port)}/"
        try:
            webbrowser.open(url)
            logger.info("Opened dashboard in browser: %s", url)
        except Exception as exc:
            logger.warning("Could not open browser for %s: %s", url, exc)

    threading.Thread(target=_open, name="OpenDashboard", daemon=True).start()
