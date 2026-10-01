"""OCI / ITMR API client for Mines Entry checkpoint."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import requests

from config.constants import TIMEOUTS
from services.api_errors import KIND_OK, annotate_response

logger = logging.getLogger("mines_checkpoint.services.oci")

API_LOG_SEPARATOR = "-" * 60


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
    Parse pipe-delimited truck_details.

    Examples:
      T|rfid|vehicle|weight|...|token|device_ip
      CE|rfid|vehicle|gross|tare|tol|token|device_ip|vehicle
    """
    parts = [p.strip() for p in (truck_details or "").split("|")]
    result: Dict[str, str] = {
        "raw": truck_details or "",
        "prefix": parts[0] if parts else "",
        "rfid": "",
        "vehicle_no": "",
        "token_no": "",
        "weight": "",
        "device_ip": "",
    }
    if len(parts) >= 3:
        result["rfid"] = parts[1]
        result["vehicle_no"] = parts[2]
    if len(parts) >= 4:
        result["weight"] = parts[3]
    if len(parts) >= 7:
        result["token_no"] = parts[6]
    if len(parts) >= 2:
        prefix = (parts[0] or "").strip().upper()
        # CE responses append vehicle_no again after device_ip
        if prefix == "CE" and len(parts) >= 8:
            result["device_ip"] = parts[7]
        else:
            result["device_ip"] = parts[-1]
    return result


def truck_details_prefix(truck_details: str) -> str:
    """First pipe segment of truck_details (e.g. CE, T, V, G)."""
    raw = (truck_details or "").strip()
    if not raw:
        return ""
    return raw.split("|", 1)[0].strip().upper()


def is_ce_truck_details(truck_details: str) -> bool:
    """CE|… trips require check-status until statusCode 200 after invalid-truck."""
    return truck_details_prefix(truck_details) == "CE"


def is_x_truck_details(truck_details: str) -> bool:
    """X|… is the Mines Exit trip: wait for exit-document download before boom-close."""
    return truck_details_prefix(truck_details) == "X"


def _first_text(raw: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _looks_like_ip(value: str) -> bool:
    text = (value or "").strip()
    parts = text.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def exit_document_ids(
    truck_details: str, raw: Optional[Dict[str, Any]] = None
) -> tuple[str, str]:
    """
    loading_slip_no and loading_slip_id for an X| mines-exit trip.

    RFID JSON keys win. Otherwise:
      long:  X|rfid|vehicle|…|slip_no|slip_id|device_ip  (slip at index 6 and 7)
      short: X|rfid|vehicle|slip_no|slip_id|…|device_ip
    """
    body = raw if isinstance(raw, dict) else {}
    slip_no = _first_text(body, "loading_slip_no", "loadingSlipNo")
    slip_id = _first_text(body, "loading_slip_id", "loadingSlipId")
    if truck_details_prefix(truck_details) != "X":
        return slip_no, slip_id

    parts = [p.strip() for p in (truck_details or "").split("|")]
    if len(parts) >= 8:
        slip_no = slip_no or parts[6]
        if not slip_id and parts[7] and not _looks_like_ip(parts[7]):
            slip_id = parts[7]
    elif len(parts) >= 5:
        slip_no = slip_no or parts[3]
        if not slip_id and parts[4] and not _looks_like_ip(parts[4]):
            slip_id = parts[4]
    return slip_no, slip_id


def document_downloaded(resp: OCIResponse) -> bool:
    """True when download/docs says the exit document is on the GMDC app."""
    raw = getattr(resp, "raw", None) or {}
    flag = raw.get("documentDownloaded")
    if isinstance(flag, bool):
        return flag
    if isinstance(flag, str) and flag.strip().lower() in ("true", "1", "yes"):
        return True
    try:
        if int(raw.get("docDownload")) == 1:
            return True
    except (TypeError, ValueError):
        pass
    return False


def status_code_from_response(resp: OCIResponse) -> Optional[int]:
    """Read numeric statusCode from check-status / OCI JSON body."""
    raw = getattr(resp, "raw", None) or {}
    if "statusCode" not in raw:
        return None
    try:
        return int(raw["statusCode"])
    except (TypeError, ValueError):
        return None


def vehicle_status_from_response(resp: OCIResponse) -> Optional[int]:
    """Read vehicleStatus from status_check JSON (0=retry, 1=ok, 2=abort)."""
    raw = getattr(resp, "raw", None) or {}
    if "vehicleStatus" not in raw:
        return None
    try:
        return int(raw["vehicleStatus"])
    except (TypeError, ValueError):
        return None


def is_manual_anpr_update_response(resp: OCIResponse) -> bool:
    """
    ANPR Update icon turns green only for manual update confirmation:
      {"statusCode": 201, "vehicleStatus": 1, "statusMessage": "Vehicle is updated manually"}
    """
    return (
        status_code_from_response(resp) == 201
        and vehicle_status_from_response(resp) == 1
    )


def build_invalid_truck_payload(
    anpr_raw: Optional[Dict[str, Any]],
    *,
    vehicle_no_web: str = "",
    rfid: str = "",
    token: str = "",
    device_ip: str = "",
    anpr_status: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Filter ANPR response into the invalid_truck_number API contract:

    {
      "vehicleNo_web": "",
      "vehicleNo_anpr": "",
      "rfid": "",
      "anpr_image": "",
      "front_image": "",
      "matching_score": "",
      "anpr_status": "",
      "token": "",
      "device_ip": ""
    }
    """
    raw = anpr_raw if isinstance(anpr_raw, dict) else {}
    best = raw.get("best_match") if isinstance(raw.get("best_match"), dict) else {}

    vehicle_anpr = (
        raw.get("vehicleNo_anpr")
        or raw.get("vehicle_number_anpr")
        or raw.get("detected_vehicle")
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
    status_val = raw.get("anpr_status", anpr_status)
    if status_val is None:
        status_val = raw.get("status", "")

    return {
        "vehicleNo_web": str(vehicle_web or ""),
        "vehicleNo_anpr": str(vehicle_anpr or ""),
        "rfid": str(raw.get("rfid") or rfid or ""),
        "anpr_image": str(raw.get("anpr_image") or best.get("image_filename") or ""),
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
    }


def build_boom_close_payload(
    anpr_raw: Optional[Dict[str, Any]] = None,
    *,
    style: str = "entry",
    rfid: str = "",
    device_ip: str = "",
    truck_details: str = "",
    close_type: str = "auto",
    front_image: str = "",
    anpr_image: str = "",
    top_image: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Boom-close body.

    style=entry (mines_entry / mines_exit):
      rfid, device_ip, truck_details, top/front/anpr images (strings), close-type

    style=tracking (tracking_1 / tracking_2):
      rfid, device_ip, front_image, anpr_image, top_image (may be JSON null)
    """
    raw = anpr_raw if isinstance(anpr_raw, dict) else {}
    best = raw.get("best_match") if isinstance(raw.get("best_match"), dict) else {}

    front = (
        front_image
        or raw.get("front_image")
        or best.get("front_image")
        or ""
    )
    anpr = (
        anpr_image
        or raw.get("anpr_image")
        or best.get("image_filename")
        or best.get("anpr_image")
        or ""
    )

    if (style or "entry").lower() == "tracking":
        if top_image is None and not raw.get("top_image") and not best.get("top_image"):
            top_val = None
        else:
            top_val = str(
                top_image
                if top_image is not None
                else raw.get("top_image")
                or raw.get("top_camera_image")
                or best.get("top_image")
                or ""
            ).strip() or None
        return {
            "rfid": str(raw.get("rfid") or rfid or ""),
            "device_ip": str(raw.get("device_ip") or device_ip or ""),
            "front_image": str(front or ""),
            "anpr_image": str(anpr or ""),
            "top_image": top_val,
        }

    return {
        "rfid": str(raw.get("rfid") or rfid or ""),
        "device_ip": str(raw.get("device_ip") or device_ip or ""),
        "truck_details": str(
            raw.get("truck_details") or truck_details or ""
        ),
        "top_image": str(
            top_image
            if top_image is not None
            else raw.get("top_image")
            or raw.get("top_camera_image")
            or best.get("top_image")
            or ""
        ),
        "front_image": str(front or ""),
        "anpr_image": str(anpr or ""),
        "close-type": str(close_type or "auto"),
    }


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


def build_status_check_payload(
    anpr_raw: Optional[Dict[str, Any]],
    *,
    vehicle_no_web: str = "",
    rfid: str = "",
    device_ip: str = "",
) -> Dict[str, Any]:
    """
    Filter ANPR /api/detect response into status_check payload:

    {
      "vehicleNo_web": "",
      "vehicleNo_anpr": "",
      "rfid": "",
      "device_ip": ""
    }
    """
    raw = anpr_raw if isinstance(anpr_raw, dict) else {}
    return {
        "vehicleNo_web": str(
            raw.get("vehicleNo_web") or vehicle_no_web or ""
        ),
        "vehicleNo_anpr": str(raw.get("vehicleNo_anpr") or ""),
        "rfid": str(raw.get("rfid") or rfid or ""),
        "device_ip": str(raw.get("device_ip") or device_ip or ""),
    }


class OCIClient:
    """
    HTTP client for OCI checkpoint APIs and separate ANPR service.

    OCI endpoints (rfid / invalid / update) use OCI Basic Auth.
    ANPR detect uses its own base URL + Basic Auth (may differ from OCI).
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        rfid_validate_url: str,
        anpr_detect_url: str,
        invalid_truck_url: str,
        update_truck_url: str,
        boom_close_url: str = "",
        reset_checkpoint_url: str = "",
        download_docs_url: str = "",
        boom_close_style: str = "entry",
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
        self.boom_close_style = (boom_close_style or "entry").lower()
        self.boom_close_url = boom_close_url or (
            self.base_url + "/ords/gmdc_dicsm/dlms_checkpoint/boom-close"
        )
        self.reset_checkpoint_url = reset_checkpoint_url or (
            self.base_url + "/ords/gmdc_dicsm/dlms_checkpoint/reset_checkpoint"
        )
        self.download_docs_url = download_docs_url or (
            self.base_url + "/ords/gmdc_dicsm/dlms_checkpoint/download/docs"
        )
        self.timeout = timeout
        self.debug_wait_sec = max(0.0, float(debug_wait_sec or 0.0))
        self._session = requests.Session()

    def _auth_for(self, key: str, default: Optional[Tuple[str, str]] = None) -> Tuple[str, str]:
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
                message=str(data.get("message", "")),
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
        # RFID success is status 200 per PDF
        if resp.http_status == 200 and resp.status == 200:
            resp.ok = True
        elif resp.status == 200:
            resp.ok = True
        else:
            resp.ok = False
        return resp

    def anpr_detect(
        self,
        vehicle_number: str,
        rfid: str,
        token_no: str = "",
        device_ip: str = "",
    ) -> OCIResponse:
        payload: Dict[str, Any] = {
            "vehicle_number": vehicle_number,
            "rfid": rfid,
        }
        if token_no:
            payload["token"] = token_no
        if device_ip:
            payload["device_ip"] = device_ip
        # ANPR uses its own host + Basic Auth
        resp = self._post(
            self.anpr_detect_url,
            payload,
            "anpr-detect",
            auth=self._auth_for("anpr_detect", self.anpr_auth),
        )
        # Normalize ANPR status: prefer anpr_status / status; else success/best_match
        raw = resp.raw
        if "anpr_status" in raw:
            try:
                resp.status = int(raw["anpr_status"])
            except (TypeError, ValueError):
                resp.status = 0
        # elif "status" in raw:
            # try:
                # resp.status = int(raw["status"])
            # except (TypeError, ValueError):
                # pass
        # else:
            # Fallback when ANPR returns success/best_match shape
            # if raw.get("success") and raw.get("best_match"):
                # resp.status = 1
            # else:
                # resp.status = 0
        # resp.ok = resp.status == 1
        return resp

    def invalid_truck_number(
        self,
        rfid: str,
        truck_number: str,
        device_ip: str,
        anpr_payload: Optional[Dict[str, Any]] = None,
        token: str = "",
        anpr_status: Optional[int] = None,
    ) -> OCIResponse:
        """
        POST invalid-truck-number with filtered ANPR fields only
        (no numberplate base64 / extra keys).
        """
        payload = build_invalid_truck_payload(
            anpr_payload,
            vehicle_no_web=truck_number,
            rfid=rfid,
            token=token,
            device_ip=device_ip,
            anpr_status=anpr_status,
        )
        return self._post(
            self.invalid_truck_url, payload, "invalid-truck",
            auth=self._auth_for("invalid_truck"),
        )

    def download_docs(
        self,
        loading_slip_no: str,
        loading_slip_id: str,
        device_ip: str,
    ) -> OCIResponse:
        """
        POST download/docs. documentDownloaded false means keep polling;
        true means the exit document is ready for boom-close.
        """
        payload = {
            "loading_slip_no": str(loading_slip_no or ""),
            "loading_slip_id": str(loading_slip_id or ""),
            "device_ip": str(device_ip or ""),
        }
        return self._post(
            self.download_docs_url,
            payload,
            "download-docs",
            auth=self._auth_for("download_docs"),
        )

    def boom_close(
        self,
        rfid: str = "",
        device_ip: str = "",
        close_type: str = "auto",
        truck_details: str = "",
        anpr_payload: Optional[Dict[str, Any]] = None,
        top_image: Optional[str] = None,
        front_image: str = "",
        anpr_image: str = "",
        style: Optional[str] = None,
    ) -> OCIResponse:
        """
        POST boom-close before opening boom.
        Body shape follows boom_close_style (entry vs tracking).
        Success when status == 200.
        """
        use_style = (style or self.boom_close_style or "entry").lower()
        # Tracking sites send top_image JSON null unless an explicit path is passed
        top_arg: Optional[str]
        if use_style == "tracking" and top_image is None:
            top_arg = None
        else:
            top_arg = top_image if top_image is not None else ""

        payload = build_boom_close_payload(
            anpr_payload,
            style=use_style,
            rfid=rfid,
            device_ip=device_ip,
            truck_details=truck_details,
            close_type=close_type,
            front_image=front_image,
            anpr_image=anpr_image,
            top_image=top_arg if use_style == "tracking" else (top_image or ""),
        )
        if front_image:
            payload["front_image"] = str(front_image)
        if anpr_image:
            payload["anpr_image"] = str(anpr_image)
        if use_style != "tracking" and top_image:
            payload["top_image"] = str(top_image)

        resp = self._post(
            self.boom_close_url, payload, "boom-close",
            auth=self._auth_for("boom_close"),
        )
        # Response may use status as string "200"
        status_raw = resp.raw.get("status", resp.status)
        try:
            resp.status = int(status_raw)
        except (TypeError, ValueError):
            resp.status = 0
        resp.ok = resp.status == 200
        return resp

    def update_truck_number(
        self,
        rfid: str = "",
        truck_number: str = "",
        device_ip: str = "",
        anpr_payload: Optional[Dict[str, Any]] = None,
    ) -> OCIResponse:
        """
        POST status_check with fields from ANPR /api/detect response:
        vehicleNo_web, vehicleNo_anpr, rfid, device_ip
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
        # Prefer vehicleStatus from status_check API
        # vehicleStatus: 0 = not updated (retry), 1 = updated (grant), 2 = abort/reset
        if "vehicleStatus" in resp.raw:
            try:
                resp.status = int(resp.raw["vehicleStatus"])
            except (TypeError, ValueError):
                resp.status = 0
        elif "status" in resp.raw:
            try:
                resp.status = int(resp.raw["status"])
            except (TypeError, ValueError):
                pass
        elif "statusCode" in resp.raw:
            try:
                code = int(resp.raw["statusCode"])
                # Keep body statusCode on resp.status when vehicleStatus absent
                # (CE check-status success is statusCode == 200).
                resp.status = code
                resp.ok = code == 200
            except (TypeError, ValueError):
                resp.status = 0
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
