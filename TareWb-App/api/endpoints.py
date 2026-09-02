"""Flask endpoints for Tare WB self-hosted API."""

from __future__ import annotations

import logging
from typing import Any

from pathlib import Path

from flask import Flask, jsonify, request

from core.app_context import AppContext
from hardware import extract_id_hexes
from services.frontend_mqtt import (
    idle_update_progress,
    idle_update_status,
    load_app_version,
)

_APP_VERSION = load_app_version(Path(__file__).resolve().parent.parent)

logger = logging.getLogger("tare_wb.api.endpoints")


def _accept_rfid_payload(payload: Any, source: str):
    ctx = AppContext.get_instance()
    id_hexes = extract_id_hexes(payload)
    logger.info("POST %s tags=%s", source, id_hexes)

    if not id_hexes:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "No idHex tags found in payload",
                    "tags": [],
                }
            ),
            400,
        )

    raw_list = payload if isinstance(payload, list) else []
    if ctx.rfid_reader:
        ctx.rfid_reader.inject_payload(payload)
    elif ctx.workflow:
        ctx.workflow.on_rfid_tags(id_hexes, raw_list)
    else:
        return jsonify({"status": "error", "message": "Workflow not ready"}), 503

    return (
        jsonify(
            {
                "status": "success",
                "message": "RFID tags accepted",
                "tags": id_hexes,
                "state": ctx.state_machine.current_state.name
                if ctx.state_machine
                else None,
            }
        ),
        200,
    )


def register_routes(app: Flask) -> None:
    @app.get("/status")
    def health():
        return jsonify({"status": 200})

    @app.get("/version")
    def version():
        return jsonify({"version": _APP_VERSION})

    @app.get("/api/update/status")
    def update_status():
        return jsonify(
            {"status": 200, "data": idle_update_status(_APP_VERSION)}
        )

    @app.get("/api/update/progress")
    def update_progress():
        return jsonify({"status": 200, "data": idle_update_progress()})

    @app.post("/api/update/check")
    def update_check():
        return jsonify(
            {"status": 200, "data": idle_update_status(_APP_VERSION)}
        )

    @app.post("/api/update/apply")
    def update_apply():
        return (
            jsonify(
                {
                    "status": 501,
                    "message": "In-app updater is not enabled for TareWb-App.",
                }
            ),
            501,
        )

    @app.get("/api/camera/stream")
    def camera_stream():
        return (
            jsonify(
                {
                    "status": 404,
                    "message": "Top camera MJPEG stream is not implemented.",
                }
            ),
            404,
        )

    @app.get("/api/status")
    def status():
        ctx = AppContext.get_instance()
        return jsonify(ctx.status_snapshot())

    @app.post("/rfid_data")
    def rfid_data():
        try:
            payload: Any = request.get_json(force=True, silent=False)
        except Exception as e:
            logger.error("rfid_data invalid JSON: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 400
        if payload is None:
            return jsonify({"status": "error", "message": "Empty body"}), 400
        return _accept_rfid_payload(payload, "/rfid_data")

    @app.post("/rfid_management")
    def rfid_management():
        try:
            payload = request.get_json(force=True, silent=True)
            if payload is not None:
                logger.debug("rfid_management: %s", payload)
        except Exception:
            pass
        return jsonify({"status": "success"}), 200

    @app.post("/rfid_data_from_mobile_app")
    def rfid_data_from_mobile_app():
        try:
            payload: Any = request.get_json(force=True, silent=False)
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object with rfid_data")
            if "rfid_data" not in payload:
                raise ValueError("rfid_data key is required")
            rfid_value = payload.get("rfid_data")
            if rfid_value is None or str(rfid_value).strip() == "":
                raise ValueError("rfid_data value is blank")
            rfid_str = str(rfid_value).strip()
            logger.info(
                "POST /rfid_data_from_mobile_app rfid_data=%s", rfid_str
            )
            ctx = AppContext.get_instance()
            if not ctx.workflow:
                raise RuntimeError("Workflow not ready")
            oci_body = ctx.workflow.on_rfid_from_mobile(rfid_str)
            return jsonify(oci_body), 200
        except Exception as e:
            logger.error("rfid_data_from_mobile_app error: %s", e)
            return (
                jsonify(
                    {
                        "status": "500",
                        "message": "Error: " + str(e),
                        "rfid_data": None,
                    }
                ),
                500,
            )

    @app.post("/api/read-rfid")
    @app.post("/read_rfid")
    def read_rfid():
        try:
            payload: Any = request.get_json(force=True, silent=False)
        except Exception as e:
            return jsonify({"status": 400, "message": f"Invalid JSON: {e}"}), 400
        if payload is None:
            return jsonify({"status": 400, "message": "Empty body"}), 400
        return _accept_rfid_payload(payload, "/api/read-rfid")

    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        ctx = AppContext.get_instance()
        expected_user = "admin"
        expected_pass = "gmdc@123"
        settings = getattr(ctx, "settings", None)
        user = getattr(settings, "operator_username", None) if settings else None
        pwd = getattr(settings, "operator_password", None) if settings else None
        if isinstance(user, str) and user.strip():
            expected_user = user.strip()
        if isinstance(pwd, str) and pwd:
            expected_pass = pwd
        if username == expected_user and password == expected_pass:
            return jsonify({"status": 200, "message": "Login successful"})
        return jsonify(
            {"status": 401, "message": "Invalid username or password"}
        ), 401

    @app.post("/api/reset")
    def reset():
        ctx = AppContext.get_instance()
        if ctx.workflow:
            ctx.workflow.force_reset(announce_reset=True)
        return jsonify({"status": 200, "message": "Application reset to IDLE"})

    @app.post("/api/free-pass")
    def free_pass():
        ctx = AppContext.get_instance()
        if ctx.workflow:
            ctx.workflow.start_free_pass()
        return jsonify(
            {
                "status": 200,
                "message": "Free pass granted; waiting for exit sensor",
            }
        )

    @app.post("/api/simulate-entry")
    def simulate_entry():
        """Demo: pulse entry sensor (falling-after-occupied)."""
        ctx = AppContext.get_instance()
        if not ctx.settings or not ctx.settings.demo_mode:
            return jsonify({"status": 403, "message": "Demo mode only"}), 403
        if not ctx.sensor_poller:
            return jsonify({"status": 503, "message": "Sensor poller not ready"}), 503
        ctx.sensor_poller.simulate_entry()
        return jsonify({"status": 200, "message": "Entry sensor simulated"})

    @app.post("/api/simulate-wb")
    def simulate_wb():
        """Demo: pulse WB sensor (falling-after-occupied)."""
        ctx = AppContext.get_instance()
        if not ctx.settings or not ctx.settings.demo_mode:
            return jsonify({"status": 403, "message": "Demo mode only"}), 403
        if not ctx.sensor_poller:
            return jsonify({"status": 503, "message": "Sensor poller not ready"}), 503
        ctx.sensor_poller.simulate_wb()
        return jsonify({"status": 200, "message": "WB sensor simulated"})

    @app.post("/api/simulate-exit")
    def simulate_exit():
        """Demo: pulse exit sensor (ENTRY_B approach when bidirectional/IDLE)."""
        ctx = AppContext.get_instance()
        if not ctx.settings or not ctx.settings.demo_mode:
            return jsonify({"status": 403, "message": "Demo mode only"}), 403
        if not ctx.sensor_poller:
            return jsonify({"status": 503, "message": "Sensor poller not ready"}), 503
        ctx.sensor_poller.simulate_exit()
        return jsonify({"status": 200, "message": "Exit sensor simulated"})
