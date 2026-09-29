"""Flask routes for Digitizer Decoder dashboard + weight API."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory, session
from functools import wraps

from config.settings import app_dir, is_calibrated, serial_port_configured
from core.app_context import AppContext
from services.index_engine import (
    WIZARD_CAPTURE_BYTES,
    build_indexing_from_picks,
    build_ruler,
    byte_display_repr,
    extract_weight_from_indexing,
    highlight_bands,
    picks_from_indexing,
    validate_indexing_for_calibration,
    validate_pick_indices,
)

logger = logging.getLogger("digitizer_decoder.api")


def _admin_ok() -> bool:
    return bool(session.get("admin_authenticated"))


def _require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _admin_ok():
            return jsonify({"status": 401, "message": "Admin login required"}), 401
        return fn(*args, **kwargs)

    return wrapper


def _public_config_view(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Strip secrets for non-admin callers (status still uses summary fields)."""
    out = {
        "port": cfg.get("port"),
        "status": cfg.get("status"),
        "communication": {
            "mode": ((cfg.get("communication") or {}).get("mode") or "api"),
        },
    }
    return out


def _weight_from_absolute_picks(
    sample: bytes, picks: List[Optional[int]]
) -> Optional[float]:
    i3, i4 = picks[2], picks[3]
    if i3 is None or i4 is None or i4 < i3 or i3 >= len(sample):
        return None
    field = sample[i3 : min(len(sample), i4 + 1)]
    digits = bytearray()
    for b in field:
        if 0x30 <= b <= 0x39 or b in (0x2B, 0x2D, 0x2E):
            digits.append(b)
        elif b in (0x20, 0x09):
            continue
        elif digits:
            break
    if not digits:
        text = "".join(chr(b) if 0x20 <= b < 0x7F else " " for b in field)
        m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None
    try:
        return float(digits.decode("ascii"))
    except ValueError:
        return None


def _frame_slice_from_picks(sample: bytes, picks: List[Optional[int]]) -> bytes:
    if not sample:
        return sample
    i1, _i2, _i3, i4, i5, i6 = picks
    start = i1 if i1 is not None else 0
    end_idx = i6 if i6 is not None else i5 if i5 is not None else i4
    if end_idx is None:
        return sample[start:]
    end = min(len(sample), end_idx + 1)
    while end < len(sample) and sample[end] in (0x0D, 0x0A):
        end += 1
    return sample[start:end]


def _calibration_extract(
    sample: bytes, picks: List[Optional[int]], indexing: Dict[str, Any]
) -> Optional[float]:
    w = _weight_from_absolute_picks(sample, picks)
    if w is not None:
        return w
    sliced = _frame_slice_from_picks(sample, picks)
    w = extract_weight_from_indexing(sliced, indexing)
    if w is not None:
        return w
    return extract_weight_from_indexing(sample, indexing)


def register_routes(app: Flask, os_type: str = "auto") -> None:
    from flask import Response

    from ui_os import inject_liquid_glass, liquid_glass_enabled

    static_root = os.path.join(app_dir(), "static", "web")
    liquid_glass = liquid_glass_enabled(os_type)

    @app.get("/")
    def index():
        path = os.path.join(static_root, "index.html")
        with open(path, encoding="utf-8") as handle:
            html = handle.read()
        if liquid_glass:
            html = inject_liquid_glass(html)
        return Response(html, mimetype="text/html")

    @app.get("/api/status")
    def api_status():
        ctx = AppContext.get_instance()
        snap = ctx.status_snapshot()
        snap["admin_authenticated"] = _admin_ok()
        return jsonify(snap)

    @app.post("/api/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        ctx = AppContext.get_instance()
        assert ctx.settings is not None
        if (
            username == ctx.settings.admin_username
            and password == ctx.settings.admin_password
        ):
            session["admin_authenticated"] = True
            session.permanent = True
            return jsonify({"status": 200, "message": "Login successful"})
        return jsonify({"status": 401, "message": "Invalid username or password"}), 401

    @app.post("/api/logout")
    def logout():
        session.pop("admin_authenticated", None)
        return jsonify({"status": 200, "message": "Logged out"})

    @app.get("/api/session")
    def session_status():
        return jsonify({"status": 200, "admin_authenticated": _admin_ok()})

    @app.get("/api/ports")
    @_require_admin
    def api_ports():
        from services.serial_service import list_serial_ports

        return jsonify({"status": 200, "ports": list_serial_ports()})

    @app.get("/api/config")
    @_require_admin
    def get_config():
        ctx = AppContext.get_instance()
        assert ctx.settings is not None
        cfg = dict(ctx.settings.raw)
        # Do not send admin password hash-equivalent to browser unnecessarily —
        # still needed so admin can change password in UI; keep as-is for local yard PC.
        return jsonify({"status": 200, "config": cfg, "calibrated": is_calibrated(cfg)})

    @app.post("/api/config")
    @_require_admin
    def post_config():
        ctx = AppContext.get_instance()
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"status": 400, "message": "JSON object required"}), 400
        # Never allow blanking admin via accidental omit — merge handled in update_config
        ok = ctx.update_config(data, restart_serial=True)
        if not ok:
            return jsonify({"status": 500, "message": "Failed to save config"}), 500
        return jsonify(
            {
                "status": 200,
                "calibrated": is_calibrated(ctx.settings.raw),
                "snapshot": ctx.status_snapshot(),
            }
        )

    @app.post("/api/serial/restart")
    @_require_admin
    def serial_restart():
        ctx = AppContext.get_instance()
        assert ctx.settings is not None
        if not serial_port_configured(ctx.settings.raw):
            return jsonify({"status": 400, "message": "Serial port not configured"}), 400
        ok = ctx.serial.start()
        return jsonify({"status": 200 if ok else 500, "connected": ctx.serial.connected})

    @app.post("/api/capture")
    @_require_admin
    def capture():
        ctx = AppContext.get_instance()
        assert ctx.settings is not None
        body = request.get_json(silent=True) or {}
        nbytes = int(body.get("bytes") or WIZARD_CAPTURE_BYTES)
        sample = ctx.serial.capture_sample(nbytes=nbytes, timeout_sec=5.0)
        if not sample:
            return jsonify(
                {"status": 408, "message": "No serial data captured", "sample_hex": ""}
            ), 408
        hex_str = sample.hex()
        cells = [
            {"index": i, "hex": f"{b:02x}", "repr": byte_display_repr(b)}
            for i, b in enumerate(sample)
        ]
        return jsonify(
            {
                "status": 200,
                "sample_hex": hex_str,
                "length": len(sample),
                "ruler": build_ruler(sample),
                "cells": cells,
            }
        )

    @app.post("/api/calibration/preview")
    @_require_admin
    def calibration_preview():
        body = request.get_json(silent=True) or {}
        sample_hex = str(body.get("sample_hex") or "")
        picks_raw = body.get("picks") or []
        try:
            sample = bytes.fromhex(sample_hex)
        except ValueError:
            return jsonify({"status": 400, "message": "Invalid sample_hex"}), 400
        picks: List[Optional[int]] = []
        for p in list(picks_raw)[:6]:
            if p is None or p == "":
                picks.append(None)
            else:
                try:
                    picks.append(int(p))
                except (TypeError, ValueError):
                    picks.append(None)
        while len(picks) < 6:
            picks.append(None)
        err = validate_pick_indices(picks, len(sample))
        if err:
            return jsonify({"status": 400, "message": err}), 400
        indexing = build_indexing_from_picks(picks, sample)
        weight = _calibration_extract(sample, picks, indexing)
        bands = highlight_bands(picks)
        return jsonify(
            {
                "status": 200,
                "indexing": indexing,
                "weight": weight,
                "bands": bands,
                "indexing_error": validate_indexing_for_calibration(indexing),
            }
        )

    @app.post("/api/calibration/save")
    @_require_admin
    def calibration_save():
        ctx = AppContext.get_instance()
        body = request.get_json(silent=True) or {}
        sample_hex = str(body.get("sample_hex") or "")
        picks_raw = body.get("picks") or []
        serial_patch = body.get("serial") or {}
        try:
            sample = bytes.fromhex(sample_hex)
        except ValueError:
            return jsonify({"status": 400, "message": "Invalid sample_hex"}), 400
        picks: List[Optional[int]] = []
        for p in list(picks_raw)[:6]:
            if p is None or p == "":
                picks.append(None)
            else:
                try:
                    picks.append(int(p))
                except (TypeError, ValueError):
                    picks.append(None)
        while len(picks) < 6:
            picks.append(None)
        err = validate_pick_indices(picks, len(sample))
        if err:
            return jsonify({"status": 400, "message": err}), 400
        indexing = build_indexing_from_picks(picks, sample)
        idx_err = validate_indexing_for_calibration(indexing)
        if idx_err:
            return jsonify({"status": 400, "message": idx_err}), 400
        weight = _calibration_extract(sample, picks, indexing)
        patch = {
            "indexing": indexing,
            "calibration_sample_hex": sample_hex,
            **{k: serial_patch[k] for k in (
                "port", "baud_rate", "data_bits", "parity", "stop_bits"
            ) if k in serial_patch},
        }
        ok = ctx.update_config(patch, restart_serial=True)
        if not ok:
            return jsonify({"status": 500, "message": "Save failed"}), 500
        return jsonify(
            {
                "status": 200,
                "weight": weight,
                "calibrated": is_calibrated(ctx.settings.raw),
                "indexing": indexing,
            }
        )

    @app.get("/api/calibration/picks")
    @_require_admin
    def calibration_picks_from_config():
        ctx = AppContext.get_instance()
        assert ctx.settings is not None
        indexing = ctx.settings.raw.get("indexing")
        sample_hex = ctx.settings.raw.get("calibration_sample_hex") or ""
        picks = [None] * 6
        if indexing and sample_hex:
            try:
                sample = bytes.fromhex(sample_hex)
                picks = picks_from_indexing(sample, indexing)
            except ValueError:
                picks = [None] * 6
        return jsonify(
            {
                "status": 200,
                "picks": picks,
                "sample_hex": sample_hex,
                "indexing": indexing,
            }
        )

    # Compatibility with Mines-WB DigitizerClient
    @app.route("/read_stable_weight", methods=["GET", "POST", "OPTIONS"])
    def read_stable_weight():
        if request.method == "OPTIONS":
            resp = app.make_response(("", 204))
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return resp
        ctx = AppContext.get_instance()
        result = ctx.runtime.wait_stable()
        http_status = 200 if result.get("statusCode") == 200 else int(
            result.get("statusCode") or 500
        )
        logger.info("read_stable_weight -> %s", result)
        resp = jsonify(result)
        resp.status_code = http_status
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp

    @app.get("/health")
    def health():
        ctx = AppContext.get_instance()
        return jsonify(ctx.status_snapshot())
