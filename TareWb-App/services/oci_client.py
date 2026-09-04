"""OCI / ANPR / weight-details / boom-close client for Tare Weighbridge."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import requests

from config.constants import (
    MSG_GROSS_WT_ERR,
    MSG_TARE_WT_ERR,
    MSG_VADAGHAT_WT_ERR,
    TIMEOUTS,
)
from services.api_errors import KIND_OK, annotate_response

logger = logging.getLogger("tare_wb.services.oci")

API_LOG_SEPARATOR = "-" * 50


def _json_for_log(value: Any) -> str:
    """Return API payloads and responses as readable JSON."""
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _log_api_exchange(url: str, payload: Dict[str, Any], response: Any) -> None:
    logger.info(
        "\n%s\nURL: %s\nPayload: %s\nResponse: %s\n%s",
        API_LOG_SEPARATOR,
        url,
        _json_for_log(payload),
        _json_for_log(response),
        API_LOG_SEPARATOR,
    )


@dataclass
class OCIResponse:
    ok: bool
    status: int
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    truck_details: str = ""
    http_status: int = 0
    kind: str = KIND_OK
    operator_message: str = ""
    popup: bool = False
    popup_title: str = ""


def parse_truck_details(truck_details: str) -> Dict[str, str]:
    """
    Parse T|V|G|{rfid}|{vehicle_no}|{rto_gross}|{rto_tare}|{tolerance}|{token}|{device_ip}|…

    Example:
      T|D2030DBE|OD14AE3900|45000|15000|500|9581208263|IP244245525163|OD14AE3900
    """
    parts = [p.strip() for p in (truck_details or "").split("|")]
    result: Dict[str, str] = {
        "raw": truck_details or "",
        "trip_type": "",
        "rfid": "",
        "vehicle_no": "",
        "token_no": "",
        "weight": "",
        "rto_gross": "",
        "rto_tare": "",
        "tolerance": "",
        "device_ip": "",
    }
    if parts and parts[0]:
        result["trip_type"] = parts[0][:1].upper()
    if len(parts) >= 3:
        result["rfid"] = parts[1]
        result["vehicle_no"] = parts[2]
    if len(parts) >= 4:
        result["weight"] = parts[3]
        result["rto_gross"] = parts[3]
    if len(parts) >= 5:
        result["rto_tare"] = parts[4]
    if len(parts) >= 6:
        result["tolerance"] = parts[5]
    if len(parts) >= 7:
        result["token_no"] = parts[6]
    if len(parts) >= 2:
        result["device_ip"] = parts[-1]
    return result


def _to_kg(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def rto_weight_band(truck_details: str) -> Optional[tuple]:
    """
    Approved weight window from truck_details, keyed by the first pipe field.

      T|RFID|VEH|45000|26000|500|...  tare:     25500 <= w <= 26500
      V|RFID|VEH|45000|26000|500|...  vadaghat: 44500 <= w <= 45000
      G|RFID|VEH|45000|26000|500|...  gross:    44500 <= w <= 45000
        (RTO gross − tolerance) … RTO gross; tare is not used.

    Returns (lo_kg, hi_kg, trip_type) or None to skip the check.
    """
    parsed = parse_truck_details(truck_details)
    trip = (parsed.get("trip_type") or "").upper()[:1]
    tolerance = _to_kg(parsed.get("tolerance")) or 0.0

    if trip == "T":
        tare = _to_kg(parsed.get("rto_tare"))
        if tare is None or tare <= 0:
            return None
        return (tare - tolerance, tare + tolerance, trip)

    if trip in ("V", "G"):
        gross = _to_kg(parsed.get("rto_gross"))
        if gross is None or gross <= 0:
            return None
        return (gross - tolerance, gross, trip)

    return None


def weight_type_error_display(trip: str) -> str:
    if trip == "T":
        return MSG_TARE_WT_ERR
    if trip == "V":
        return MSG_VADAGHAT_WT_ERR
    return MSG_GROSS_WT_ERR


def replace_truck_details_tolerance(
    truck_details: str, updated_tolerance: Any
) -> str:
    """
    Replace the 6th pipe field (RTO tolerance) in truck_details.

    T|RFID|VEH|45000|26000|500|token|ip|…  →  …|26000|25550|token|…
    """
    parts = [p.strip() for p in (truck_details or "").split("|")]
    if len(parts) < 6:
        return truck_details or ""
    try:
        parts[5] = str(int(float(updated_tolerance)))
    except (TypeError, ValueError):
        return truck_details or ""
    return "|".join(parts)


def under_or_over_type(current_kg: float, truck_details: str) -> str:
    """Return 'u' if under the RTO band low, else 'o'."""
    band = rto_weight_band(truck_details)
    if band is None:
        return "o"
    lo, _hi, _trip = band
    try:
        weight = float(current_kg)
    except (TypeError, ValueError):
        return "o"
    return "u" if weight < lo else "o"


def weight_within_rto_tolerance(
    current_kg: float, truck_details: str
) -> tuple:
    """
    Return (ok, message). ok is True when the band is missing (skip) or weight is inside it.
    """
    band = rto_weight_band(truck_details)
    if band is None:
        return True, ""
    lo, hi, trip = band
    try:
        weight = float(current_kg)
    except (TypeError, ValueError):
        return False, "Current weight is missing."
    if lo <= weight <= hi:
        return True, ""
    labels = {"T": "tare", "V": "vadaghat", "G": "gross"}
    label = labels.get(trip, "approved")
    return (
        False,
        f"Weight {int(weight)} kg outside RTO {label} band "
        f"{int(lo)}–{int(hi)} kg.",
    )


def anpr_status_from_raw(raw: Dict[str, Any]) -> int:
    """Normalize ANPR detect response to anpr_status 0 / 1 / 2."""
    if not isinstance(raw, dict):
        return 0
    if "anpr_status" in raw:
        try:
            return int(raw["anpr_status"])
        except (TypeError, ValueError):
            return 0
    if raw.get("best_match"):
        return 1
    if raw.get("success") and raw.get("best_match"):
        return 1
    return 0


def build_invalid_truck_payload(
    anpr_raw: Optional[Dict[str, Any]],
    *,
    vehicle_no_web: str = "",
    rfid: str = "",
    token: str = "",
    device_ip: str = "",
    anpr_status: Optional[int] = None,
    top_image: str = "",
) -> Dict[str, Any]:
    """
    Filter ANPR response into invalid-truck-number body (Mines Entry contract)
    plus top_image for tare WB.

    top_image:
      success → {TOKEN}_{ts}_{TRUCK}_{IP}_TOP.jpg
      failure → error.jpg
    Always included so OCI always receives a photo name.
    """
    raw = anpr_raw if isinstance(anpr_raw, dict) else {}
    best = raw.get("best_match") if isinstance(raw.get("best_match"), dict) else {}

    vehicle_anpr = (
        raw.get("vehicleNo_anpr")
        or raw.get("vehicle_number_anpr")
        or best.get("vehicle_ocr_value")
        or raw.get("input_vehicle")
        or ""
    )
    vehicle_web = (
        raw.get("vehicleNo_web")
        or raw.get("vehicle_number")
        or vehicle_no_web
        or ""
    )
    status_val = anpr_status if anpr_status is not None else raw.get("anpr_status")
    if status_val is None:
        status_val = raw.get("status", "")

    top = (
        str(top_image or "").strip()
        or str(raw.get("top_image") or "").strip()
        or str(raw.get("top_camera_image") or "").strip()
        or "error.jpg"
    )

    return {
        "vehicleNo_web": str(vehicle_web or ""),
        "vehicleNo_anpr": str(vehicle_anpr or ""),
        "rfid": str(raw.get("rfid") or rfid or ""),
        "anpr_image": str(
            raw.get("anpr_image") or best.get("image_filename") or ""
        ),
        "front_image": str(raw.get("front_image") or ""),
        "matching_score": str(
            raw.get("matching_score")
            if raw.get("matching_score") is not None
            else best.get("match_score")
            if best.get("match_score") is not None
            else ""
        ),
        "anpr_status": str(status_val if status_val is not None else ""),
        "token": str(raw.get("token") or raw.get("token_no") or token or ""),
        "device_ip": str(raw.get("device_ip") or device_ip or ""),
        "top_image": top,
    }


def build_status_check_payload(
    anpr_raw: Optional[Dict[str, Any]],
    *,
    vehicle_no_web: str = "",
    rfid: str = "",
    device_ip: str = "",
) -> Dict[str, Any]:
    """status_check / update_truck_url body (Mines Entry)."""
    raw = anpr_raw if isinstance(anpr_raw, dict) else {}
    return {
        "vehicleNo_web": str(raw.get("vehicleNo_web") or vehicle_no_web or ""),
        "vehicleNo_anpr": str(raw.get("vehicleNo_anpr") or ""),
        "rfid": str(raw.get("rfid") or rfid or ""),
        "device_ip": str(raw.get("device_ip") or device_ip or ""),
    }


def build_boom_close_payload(*, truck_details: str = "") -> Dict[str, Any]:
    """Tare WB boom-close body - truck_details only."""
    return {"truck_details": str(truck_details or "")}


def build_reset_checkpoint_payload(
    *,
    device_ip: str = "",
    rfid_no: str = "",
    truck_details: str = "",
) -> Dict[str, Any]:
    """Always send all three keys; unused fields are empty strings."""
    return {
        "device_ip": str(device_ip or ""),
        "rfid_no": str(rfid_no or ""),
        "truck_details": str(truck_details or ""),
    }


def build_weight_details_payload(
    *,
    current_weight: str,
    truck_details: str = "",
    front_image_name: str = "",
    top_image_name: str = "",
    anpr_image_name: str = "",
) -> Dict[str, Any]:
    """
    weight-details body.

    top_image_name:
      success → {TOKEN}_{ts}_{TRUCK}_{IP}_TOP.jpg
      failure → error.jpg
    Always included (defaults to error.jpg when missing).
    """
    top = str(top_image_name or "").strip() or "error.jpg"
    return {
        "current_weight": str(current_weight),
        "truck_details": str(truck_details or ""),
        "front_image_name": str(front_image_name or ""),
        "top_image_name": top,
        "anpr_image_name": str(anpr_image_name or ""),
    }


def build_vadhghat_weight_adjustment_payload(
    *,
    device_ip: str,
    truck_details: str,
    weight: Any,
    weight_type: str,
) -> Dict[str, Any]:
    """
    POST vadhghat_weight_adjustment when captured weight is outside RTO band.

    weight_type: "o" (over) or "u" (under).
    """
    try:
        weight_val: Any = int(float(weight))
    except (TypeError, ValueError):
        weight_val = weight
    wt = str(weight_type or "").strip().lower()[:1]
    if wt not in ("o", "u"):
        wt = "o"
    return {
        "device_ip": str(device_ip or ""),
        "truck_details": str(truck_details or ""),
        "weight": weight_val,
        "weight_type": wt,
    }


class OCIClient:
    """HTTP client for OCI weighbridge APIs and pluggable ANPR."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        rfid_validate_url: str,
        anpr_detect_url: str,
        invalid_truck_url: str,
        update_truck_url: str,
        weight_details_url: str,
        boom_close_url: str = "",
        reset_checkpoint_url: str = "",
        weight_confirm_url: str = "",
        gross_tolerance_confirm_url: str = "",
        vadhghat_weight_adjustment_url: str = "",
        anpr_username: Optional[str] = None,
        anpr_password: Optional[str] = None,
        endpoint_auth: Optional[Dict[str, Tuple[str, str]]] = None,
        timeout: float = TIMEOUTS.OCI_REQUEST_TIMEOUT_SEC,
        debug_wait_sec: float = 0.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth: Tuple[str, str] = (username, password)
        self.anpr_auth: Tuple[str, str] = (
            anpr_username or username,
            anpr_password or password,
        )
        self.endpoint_auth: Dict[str, Tuple[str, str]] = endpoint_auth or {}
        self.rfid_validate_url = rfid_validate_url
        self.anpr_detect_url = anpr_detect_url
        self.invalid_truck_url = invalid_truck_url
        self.update_truck_url = update_truck_url
        self.weight_details_url = weight_details_url
        self.boom_close_url = boom_close_url or (
            self.base_url + "/ords/gmdc_dicsm/dlms_checkpoint/boom-close"
        )
        self.reset_checkpoint_url = reset_checkpoint_url or (
            self.base_url + "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint"
        )
        self.weight_confirm_url = weight_confirm_url or (
            self.base_url
            + "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/weight-confirm"
        )
        self.gross_tolerance_confirm_url = gross_tolerance_confirm_url or (
            self.base_url
            + "/ords/gmdc_dicsm/dlms_weighbridge/validate_truck/gross-tolerance-confirm"
        )
        self.vadhghat_weight_adjustment_url = vadhghat_weight_adjustment_url or (
            self.base_url
            + "/ords/gmdc_dicsm/dlms_weighbridge/vadhghat_weight_adjustment"
        )
        self.timeout = timeout
        self.debug_wait_sec = max(0.0, float(debug_wait_sec or 0.0))
        self._session = requests.Session()

    def _auth_for(
        self, key: str, default: Optional[Tuple[str, str]] = None
    ) -> Tuple[str, str]:
        creds = self.endpoint_auth.get(key)
        if creds and creds[0] and creds[1]:
            return creds
        return default or self.auth

    def _maybe_debug_wait(self, label: str) -> None:
        """Pause after GMDC OCI calls so request/response logs can be inspected."""
        if self.debug_wait_sec <= 0:
            return
        if str(label).lower().startswith("anpr"):
            return
        logger.info(
            "API_DEBUG: waiting %ss after %s", self.debug_wait_sec, label
        )
        time.sleep(self.debug_wait_sec)

    def _post(
        self,
        url: str,
        payload: Dict[str, Any],
        label: str,
        auth: Optional[Tuple[str, str]] = None,
    ) -> OCIResponse:
        use_auth = auth if auth is not None else self.auth
        try:
            resp = self._session.post(
                url,
                json=payload,
                auth=use_auth,
                timeout=self.timeout,
            )
            http_status = resp.status_code
            try:
                data = resp.json()
            except ValueError:
                data = {"raw_text": resp.text}
            _log_api_exchange(url, payload, data)
            self._maybe_debug_wait(label)
            status_val = data.get("status", http_status if resp.ok else 0)
            try:
                status_int = int(status_val)
            except (TypeError, ValueError):
                status_int = 0
            result = OCIResponse(
                ok=resp.ok and status_int in (200, 1),
                status=status_int,
                message=str(
                    data.get("message")
                    or data.get("statusMessage")
                    or ""
                ),
                raw=data if isinstance(data, dict) else {"data": data},
                truck_details=str(data.get("truck_details", "")),
                http_status=http_status,
            )
            return annotate_response(result, label)
        except requests.RequestException as e:
            _log_api_exchange(url, payload, {"error": str(e)})
            logger.error("OCI %s ERROR: %s", label, e)
            self._maybe_debug_wait(label)
            result = OCIResponse(
                ok=False, status=0, message=str(e), raw={}, http_status=0
            )
            return annotate_response(result, label)

    def validate_rfid(self, rfid: str, device_ip: str) -> OCIResponse:
        payload = {"rfid": rfid, "device_ip": device_ip}
        resp = self._post(
            self.rfid_validate_url, payload, "rfid-validate",
            auth=self._auth_for("rfid_validate"),
        )
        resp.ok = resp.status == 200 or (
            resp.http_status == 200 and resp.status == 200
        )
        return resp

    def anpr_detect(
        self,
        vehicle_number: str,
        rfid: str,
        device_ip: str = "",
        token_no: str = "",
    ) -> OCIResponse:
        payload: Dict[str, Any] = {
            "vehicle_number": vehicle_number,
            "rfid": rfid,
        }
        if token_no:
            payload["token"] = token_no
        if device_ip:
            payload["device_ip"] = device_ip
        resp = self._post(
            self.anpr_detect_url,
            payload,
            "anpr-detect",
            auth=self._auth_for("anpr_detect", self.anpr_auth),
        )
        resp.status = anpr_status_from_raw(resp.raw)
        resp.ok = resp.status == 1
        return resp

    def invalid_truck_number(
        self,
        rfid: str,
        truck_number: str,
        device_ip: str,
        anpr_payload: Optional[Dict[str, Any]] = None,
        token: str = "",
        anpr_status: Optional[int] = None,
        top_image: str = "",
    ) -> OCIResponse:
        payload = build_invalid_truck_payload(
            anpr_payload,
            vehicle_no_web=truck_number,
            rfid=rfid,
            token=token,
            device_ip=device_ip,
            anpr_status=anpr_status,
            top_image=top_image,
        )
        return self._post(
            self.invalid_truck_url, payload, "invalid-truck",
            auth=self._auth_for("invalid_truck"),
        )

    def update_truck_number(
        self,
        rfid: str = "",
        truck_number: str = "",
        device_ip: str = "",
        anpr_payload: Optional[Dict[str, Any]] = None,
    ) -> OCIResponse:
        """
        POST status_check.
        Only vehicleStatus controls workflow: 0=retry, 1=continue, 2=abort.
        """
        payload = build_status_check_payload(
            anpr_payload,
            vehicle_no_web=truck_number,
            rfid=rfid,
            device_ip=device_ip,
        )
        resp = self._post(
            self.update_truck_url, payload, "update-truck",
            auth=self._auth_for("update_truck"),
        )
        if "vehicleStatus" in resp.raw:
            try:
                resp.status = int(resp.raw["vehicleStatus"])
            except (TypeError, ValueError):
                resp.status = 0
        else:
            # HTTP/statusCode 200 only means the request succeeded; it does not
            # approve the truck. Keep polling until vehicleStatus is present.
            resp.status = 0
        return resp

    def boom_close(self, truck_details: str = "") -> OCIResponse:
        """POST boom-close with tare WB payload {truck_details}."""
        payload = build_boom_close_payload(truck_details=truck_details)
        resp = self._post(
            self.boom_close_url, payload, "boom-close",
            auth=self._auth_for("boom_close"),
        )
        status_raw = resp.raw.get("status", resp.status)
        try:
            resp.status = int(status_raw)
        except (TypeError, ValueError):
            resp.status = 0
        resp.ok = resp.status == 200 or resp.http_status == 200
        return resp

    def reset_checkpoint(
        self,
        *,
        device_ip: str,
        rfid_no: str = "",
        truck_details: str = "",
    ) -> OCIResponse:
        """Tell GMDC this checkpoint is idle again so RFID can be re-read."""
        payload = build_reset_checkpoint_payload(
            device_ip=device_ip,
            rfid_no=rfid_no,
            truck_details=truck_details,
        )
        resp = self._post(
            self.reset_checkpoint_url,
            payload,
            "reset-checkpoint",
            auth=self._auth_for("reset_checkpoint"),
        )
        status_raw = resp.raw.get("status", resp.status)
        try:
            resp.status = int(status_raw)
        except (TypeError, ValueError):
            resp.status = 0
        resp.ok = resp.status == 200 or resp.http_status == 200
        return resp

    def weight_details(
        self,
        current_weight: str,
        truck_details: str = "",
        front_image_name: str = "",
        top_image_name: str = "",
        anpr_image_name: str = "",
    ) -> OCIResponse:
        payload = build_weight_details_payload(
            current_weight=current_weight,
            truck_details=truck_details,
            front_image_name=front_image_name,
            top_image_name=top_image_name,
            anpr_image_name=anpr_image_name,
        )
        return self._post(
            self.weight_details_url, payload, "weight-details",
            auth=self._auth_for("weight_details"),
        )

    def weight_confirm(
        self,
        truck_details: str,
        current_weight: str,
        weight_type: str,
    ) -> OCIResponse:
        """
        POST weight-confirm when current weight is outside RTO tolerance.
        weight_type: "u" (under) or "o" (over).
        Response weight_status: 0=retry same payload, 1=apply updated_tolerance
        then recapture, 2=reject.
        """
        payload = {
            "truck_details": truck_details,
            "current_weight": current_weight,
            "type": weight_type,
        }
        resp = self._post(
            self.weight_confirm_url, payload, "weight-confirm",
            auth=self._auth_for("weight_confirm"),
        )
        if "weight_status" in resp.raw:
            try:
                resp.status = int(resp.raw["weight_status"])
            except (TypeError, ValueError):
                resp.status = 0
        else:
            resp.status = 0
        return resp

    def gross_tolerance_confirm(
        self,
        current_weight: str,
        truck_details: str,
        device_ip: str,
    ) -> OCIResponse:
        """
        POST gross-tolerance-confirm after weight-details status 201 (G/V).
        Response tolerance_status: 0=retry same payload, 1=apply gross_tolerance
        and re-check band, 2=skip second weight-details.
        """
        payload = {
            "current_weight": str(current_weight or ""),
            "truck_details": truck_details or "",
            "device_ip": device_ip or "",
        }
        resp = self._post(
            self.gross_tolerance_confirm_url,
            payload,
            "gross-tolerance-confirm",
            auth=self._auth_for("gross_tolerance_confirm"),
        )
        if "tolerance_status" in resp.raw:
            try:
                resp.status = int(resp.raw["tolerance_status"])
            except (TypeError, ValueError):
                resp.status = 0
        else:
            resp.status = 0
        return resp

    def vadhghat_weight_adjustment(
        self,
        *,
        device_ip: str,
        truck_details: str,
        weight: Any,
        weight_type: str,
    ) -> OCIResponse:
        """
        POST vadhghat_weight_adjustment when Vadhghat weight is out of RTO band.
        Then the lane exits without boom-close.
        """
        payload = build_vadhghat_weight_adjustment_payload(
            device_ip=device_ip,
            truck_details=truck_details,
            weight=weight,
            weight_type=weight_type,
        )
        resp = self._post(
            self.vadhghat_weight_adjustment_url,
            payload,
            "vadhghat-weight-adjustment",
            auth=self._auth_for("vadhghat_weight_adjustment"),
        )
        status_raw = resp.raw.get("status", resp.status)
        try:
            resp.status = int(status_raw)
        except (TypeError, ValueError):
            resp.status = 0
        resp.ok = resp.status == 200 or resp.http_status == 200
        return resp
