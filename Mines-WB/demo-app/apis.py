"""
Local OCI + digitizer simulator for Mines WB (port 8001).

Replaces https://gmuatociexp.gmdcltd.co.in so the app can run without UAT.

Usage:
  python apis.py
  # then set OCI_BASE_URL=http://localhost:8001 (or api_endpoints.oci_base_url)

Switch scenario (success / error cases):
  curl -X POST http://localhost:8001/sim/scenario -H 'Content-Type: application/json' \\
       -d '{"scenario":"weight_fail"}'
  curl http://localhost:8001/sim/scenario
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, request

app = Flask(__name__)

# Digitizer weight — keep in band for default TARE_DETAILS (tare=25950 ± 500).
# DEFAULT_WEIGHT = float(os.getenv("SIM_WEIGHT_KG", "25950")) # TareWb
DEFAULT_WEIGHT = float(os.getenv("SIM_WEIGHT_KG", "44950")) # VadhghatWb

# Pipe format used by Mines WB: trip|rfid|veh|gross|tare|tol|token|ip|veh
TARE_DETAILS = (
    "T|D2030DBE|OD14AE3900|45000|25950|500|9581208263|IP244245525163|OD14AE3900"
)

SCENARIOS = {
    "success": "Happy path — RFID valid, weight-details 200, boom-close 200",
    "rfid_invalid": "RFID validate returns business reject (status 0)",
    "rfid_unreachable": "RFID validate HTTP 503 (service down popup)",
    "weight_fail": "weight-details business fail (status 400)",
    "weight_unreachable": "weight-details HTTP 503 (service down popup)",
    "weight_confirm_reject": "weight-confirm returns weight_status=2 (abort)",
    "weight_confirm_ok": "weight-confirm returns weight_status=1 + updated_tolerance",
    "status_abort": "status_check vehicleStatus=2 (manual ANPR abort)",
    "status_retry": "status_check vehicleStatus=0 forever (manual wait)",
    "status_ok": "status_check vehicleStatus=1 (manual continue)",
}

_state: Dict[str, Any] = {
    "scenario": os.getenv("SIM_SCENARIO", "success").strip().lower() or "success",
    "status_check_calls": 0,
    "weight_confirm_calls": 0,
}


def _scenario() -> str:
    name = str(_state.get("scenario") or "success").strip().lower()
    return name if name in SCENARIOS else "success"


def _ok(extra: Optional[Dict[str, Any]] = None, http: int = 200) -> Tuple[Any, int]:
    body: Dict[str, Any] = {"status": 200, "message": "OK"}
    if extra:
        body.update(extra)
    return jsonify(body), http


def _biz_fail(message: str, status: int = 0, http: int = 200) -> Tuple[Any, int]:
    return jsonify({"status": status, "message": message}), http


def _unreachable(service: str) -> Tuple[Any, int]:
    return (
        jsonify(
            {
                "status": 0,
                "message": f"{service} simulated unreachable",
            }
        ),
        503,
    )


def _log(label: str, payload: Any) -> None:
    print(f"[demo-oci] scenario={_scenario()} {label} body={payload}")


# ---------------------------------------------------------------------------
# Sim control
# ---------------------------------------------------------------------------
@app.get("/")
def home():
    return jsonify(
        {
            "service": "Mines WB local OCI + digitizer simulator",
            "port": 8001,
            "scenario": _scenario(),
            "scenarios": SCENARIOS,
            "hint": "POST /sim/scenario {\"scenario\":\"weight_fail\"}",
            "digitizer": "POST /read_stable_weight",
            "oci_base": "http://localhost:8001",
        }
    )


@app.get("/sim/scenario")
def get_scenario():
    return jsonify(
        {
            "scenario": _scenario(),
            "description": SCENARIOS[_scenario()],
            "scenarios": SCENARIOS,
            "counters": {
                "status_check_calls": _state["status_check_calls"],
                "weight_confirm_calls": _state["weight_confirm_calls"],
            },
        }
    )


@app.post("/sim/scenario")
def set_scenario():
    data = request.get_json(silent=True) or {}
    name = str(
        data.get("scenario") or request.args.get("scenario") or ""
    ).strip().lower()
    if name not in SCENARIOS:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"unknown scenario {name!r}",
                    "scenarios": list(SCENARIOS),
                }
            ),
            400,
        )
    _state["scenario"] = name
    _state["status_check_calls"] = 0
    _state["weight_confirm_calls"] = 0
    print(f"[demo-oci] scenario set -> {name}")
    return jsonify({"ok": True, "scenario": name, "description": SCENARIOS[name]})


@app.post("/sim/reset")
def reset_counters():
    _state["status_check_calls"] = 0
    _state["weight_confirm_calls"] = 0
    return jsonify({"ok": True, "scenario": _scenario()})


# ---------------------------------------------------------------------------
# Digitizer
# ---------------------------------------------------------------------------
@app.post("/read_stable_weight")
def read_stable_weight():
    weight = DEFAULT_WEIGHT
    # Optional override for out-of-band tests without changing truck_details.
    if _scenario() == "weight_confirm_reject":
        weight = float(os.getenv("SIM_OUT_OF_BAND_WEIGHT_KG", "14000"))
    elif _scenario() == "weight_confirm_ok":
        # First reads can be out of band; after confirm, app re-reads — keep simple.
        weight = float(os.getenv("SIM_OUT_OF_BAND_WEIGHT_KG", "14000"))
    _log("digitizer", {"weight": weight})
    return jsonify({"weight": weight, "ok": True})


# ---------------------------------------------------------------------------
# OCI: RFID validate (tare / gross)
# ---------------------------------------------------------------------------
def _rfid_validate():
    payload = request.get_json(silent=True) or {}
    _log("rfid-validate", payload)
    scen = _scenario()
    if scen == "rfid_unreachable":
        return _unreachable("RFID service")
    if scen == "rfid_invalid":
        return _biz_fail("Invalid RFID tag", status=0)
    return _ok(
        {
            "truck_details": TARE_DETAILS,
            "message": "RFID validated",
        }
    )


@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/tare_rfid_tag")
@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross_rfid_tag")
@app.post("/ords/gmdc_dicsm/dlms_checkpoint/rfid-tag")
def rfid_validate():
    return _rfid_validate()


# ---------------------------------------------------------------------------
# OCI: invalid-truck / status_check / reset
# ---------------------------------------------------------------------------
@app.post("/ords/gmdc_dicsm/dlms_checkpoint/invalid-truck-number")
def invalid_truck():
    payload = request.get_json(silent=True) or {}
    _log("invalid-truck", payload)
    return _ok({"message": "invalid-truck recorded"})


@app.post("/ords/gmdc_dicsm/dlms_checkpoint/status_check")
def status_check():
    payload = request.get_json(silent=True) or {}
    _state["status_check_calls"] = int(_state["status_check_calls"]) + 1
    _log("status_check", payload)
    scen = _scenario()
    if scen == "status_abort":
        return jsonify(
            {
                "status": 200,
                "statusCode": 200,
                "vehicleStatus": 2,
                "message": "Manual abort",
            }
        )
    if scen == "status_retry":
        return jsonify(
            {
                "status": 200,
                "statusCode": 200,
                "vehicleStatus": 0,
                "message": "Waiting for operator",
            }
        )
    # success / status_ok / default: continue (statusCode 201 = manual update)
    return jsonify(
        {
            "status": 200,
            "statusCode": 201,
            "vehicleStatus": 1,
            "statusMessage": "Vehicle is updated manually",
            "message": "Vehicle is updated manually",
        }
    )


@app.post("/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint")
def reset_checkpoint():
    payload = request.get_json(silent=True) or {}
    _log("reset_checkpoint", payload)
    return _ok({"message": "checkpoint reset"})


# ---------------------------------------------------------------------------
# OCI: boom-close
# ---------------------------------------------------------------------------
@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/tare_boom_close")
@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross_boom_close")
@app.post("/ords/gmdc_dicsm/dlms_checkpoint/boom-close")
def boom_close():
    payload = request.get_json(silent=True) or {}
    _log("boom-close", payload)
    return _ok({"message": "boom closed"})


# ---------------------------------------------------------------------------
# OCI: weight-details / weight-confirm / gross-tolerance / vadhghat
# ---------------------------------------------------------------------------
@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-details")
@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-weight-details")
def weight_details():
    payload = request.get_json(silent=True) or {}
    _log("weight-details", payload)
    scen = _scenario()
    if scen == "weight_unreachable":
        return _unreachable("Weight-details service")
    if scen == "weight_fail":
        return _biz_fail("Weight validation failed", status=400)
    return _ok({"message": "Weight validation successful"})


@app.post("/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-confirm")
def weight_confirm():
    payload = request.get_json(silent=True) or {}
    _state["weight_confirm_calls"] = int(_state["weight_confirm_calls"]) + 1
    _log("weight-confirm", payload)
    scen = _scenario()
    if scen == "weight_confirm_reject":
        return jsonify(
            {
                "status": 200,
                "weight_status": 2,
                "message": "Weight confirm rejected",
            }
        )
    if scen == "weight_confirm_ok":
        # Raise tolerance so 14000 falls in band around RTO tare 25950? Better:
        # return updated_tolerance large enough that app re-checks after confirm.
        # Band = tare ± tolerance; with tare 25950 and tol 12000 → 13950–37950.
        return jsonify(
            {
                "status": 200,
                "weight_status": 1,
                "updated_tolerance": 12000,
                "message": "Tolerance updated",
            }
        )
    # Default: approve with enough tolerance for current weight
    return jsonify(
        {
            "status": 200,
            "weight_status": 1,
            "updated_tolerance": 12000,
            "message": "OK",
        }
    )


@app.post(
    "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-tolerance-confirm"
)
def gross_tolerance_confirm():
    payload = request.get_json(silent=True) or {}
    _log("gross-tolerance-confirm", payload)
    return jsonify(
        {
            "status": 200,
            "tolerance_status": "1",
            "gross_tolerance": 3000,
            "message": "OK",
        }
    )


@app.post("/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment")
def vadhghat_weight_adjustment():
    payload = request.get_json(silent=True) or {}
    _log("vadhghat_weight_adjustment", payload)
    return _ok({"message": "adjustment recorded"})


if __name__ == "__main__":
    print("=" * 60)
    print("Mines WB demo OCI + digitizer on http://0.0.0.0:8001")
    print(f"Scenario: {_scenario()}  ({SCENARIOS[_scenario()]})")
    print("Change: POST /sim/scenario {\"scenario\":\"weight_fail\"}")
    print("Point TareWb: OCI_BASE_URL=http://localhost:8001")
    print("=" * 60)
    app.run(host="0.0.0.0", port=8001, debug=True)
