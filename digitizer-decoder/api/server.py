"""Flask app factory for Digitizer Decoder."""

from __future__ import annotations

import logging
import os
import secrets

from flask import Flask

from api.endpoints import register_routes
from config.settings import app_dir

logger = logging.getLogger("digitizer_decoder.server")


def create_app() -> Flask:
    web_root = os.path.join(app_dir(), "static", "web")
    app = Flask(
        "digitizer_decoder",
        static_folder=web_root,
        static_url_path="/static",
    )
    app.config["JSON_SORT_KEYS"] = False
    # Session for admin login (config modal)
    app.secret_key = os.environ.get(
        "DIGITIZER_SECRET_KEY",
        "gmdc-digitizer-decoder-local-" + secrets.token_hex(8),
    )
    register_routes(app)
    return app


def start_api_server(host: str, port: int) -> Flask:
    app = create_app()
    logger.info("Digitizer Decoder UI+API on http://%s:%s", host, port)
    app.run(host=host, port=port, threaded=True, use_reloader=False)
    return app
