"""Operator-facing classification of outbound HTTP failures.

Transport / 5xx errors become a large red dashboard popup.
Reachable non-200 business results stay as a red step message only.
When the API returns a human-readable message, show that in the UI DIV.
Raw exception strings never go to the UI.
"""

from __future__ import annotations

from typing import Any, Optional

KIND_OK = "ok"
KIND_BUSINESS = "business"
KIND_UNREACHABLE = "unreachable"
KIND_SERVER = "server"
KIND_HTTP = "http"

_SERVICES = {
    "anpr-detect": "ANPR",
    "rfid-validate": "RFID service",
    "invalid-truck": "Invalid-truck service",
    "update-truck": "Status-check service",
    "check-status": "Status-check service",
    "boom-close": "Boom-close service",
    "weight-details": "Weight-details service",
    "weight-confirm": "Weight-confirm service",
    "gross-tolerance-confirm": "Gross-tolerance service",
    "digitizer": "Digitizer",
    "reset-checkpoint": "Reset service",
}

_EXCEPTION_MARKERS = (
    "httpconnectionpool",
    "max retries exceeded",
    "connection refused",
    "failed to establish",
    "name or service not known",
    "nodename nor servname",
    "traceback (most recent call last)",
    "sslerror",
    "read timed out",
    "connecttimeout",
    "readtimeout",
    "connectionerror",
    "proxyerror",
    "urllib3.",
    "requests.exceptions",
)


def _name(label: str) -> str:
    return _SERVICES.get(str(label or "").strip().lower(), "Service")


def operator_copy(label: str, kind: str) -> tuple[str, str]:
    """Return (short step message, popup title)."""
    name = _name(label)
    if kind == KIND_UNREACHABLE:
        return (f"{name} not reachable", f"{name.upper()} NOT REACHABLE")
    if kind == KIND_SERVER:
        return (f"{name} server error", f"{name.upper()} SERVER ERROR")
    if kind == KIND_HTTP:
        return (f"{name} request failed", f"{name.upper()} REQUEST FAILED")
    return (f"{name} failed", f"{name.upper()} FAILED")


def classify_http_status(http_status: int) -> str:
    if http_status <= 0:
        return KIND_UNREACHABLE
    if http_status >= 500:
        return KIND_SERVER
    if http_status in (401, 403):
        return KIND_SERVER
    if 400 <= http_status < 500:
        return KIND_HTTP
    return KIND_OK


def _looks_like_exception_dump(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _EXCEPTION_MARKERS)


def extract_api_message(resp: Any) -> str:
    """Return a safe human-readable API message, or empty string."""
    if resp is None:
        return ""
    raw = getattr(resp, "raw", None)
    candidates = [getattr(resp, "message", None)]
    if isinstance(raw, dict):
        candidates.extend(
            [
                raw.get("message"),
                raw.get("statusMessage"),
                raw.get("status_message"),
                raw.get("errorMessage"),
                raw.get("error_message"),
                raw.get("error"),
                raw.get("MSG"),
                raw.get("msg"),
            ]
        )
    for value in candidates:
        text = str(value or "").strip()
        if text and not _looks_like_exception_dump(text):
            return text
    return ""


def annotate_response(resp: Any, label: str, *, kind: Optional[str] = None) -> Any:
    """Fill operator_message / popup on an OCIResponse-like object."""
    try:
        http = int(getattr(resp, "http_status", 0) or 0)
    except (TypeError, ValueError):
        http = 0
    resolved = kind or classify_http_status(http)
    api_msg = extract_api_message(resp)

    if resolved == KIND_OK:
        resp.kind = KIND_OK
        resp.popup = False
        resp.popup_title = ""
        try:
            status = int(getattr(resp, "status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        resp.operator_message = api_msg if status not in (200, 1) and api_msg else ""
        return resp

    short, title = operator_copy(label, resolved)
    if resolved != KIND_UNREACHABLE and api_msg:
        short = api_msg
    resp.kind = resolved
    resp.operator_message = short
    resp.popup = resolved in (KIND_UNREACHABLE, KIND_SERVER)
    resp.popup_title = title if resp.popup else ""
    return resp


def is_transport_failure(resp: Any) -> bool:
    """True when _post mapped a connection/timeout into http_status=0."""
    if resp is None:
        return True
    if str(getattr(resp, "kind", "") or "") == KIND_UNREACHABLE:
        return True
    if bool(getattr(resp, "ok", False)):
        return False
    raw = getattr(resp, "raw", None) or {}
    try:
        http = int(getattr(resp, "http_status", 0) or 0)
    except (TypeError, ValueError):
        http = 0
    try:
        status = int(getattr(resp, "status", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    return http == 0 and status == 0 and not raw


def is_service_alert(resp: Any) -> bool:
    """True when the operator should see a large popup (unreachable / 5xx)."""
    if resp is None:
        return False
    if is_transport_failure(resp):
        return True
    if bool(getattr(resp, "popup", False)):
        return True
    kind = str(getattr(resp, "kind", "") or "")
    if kind in (KIND_UNREACHABLE, KIND_SERVER):
        return True
    try:
        http = int(getattr(resp, "http_status", 0) or 0)
    except (TypeError, ValueError):
        http = 0
    return http >= 500 or http in (401, 403)


def is_api_failure(resp: Any) -> bool:
    """True for unreachable, 5xx/auth, or other non-200 HTTP (not ANPR 0/1/2)."""
    if resp is None:
        return True
    if is_transport_failure(resp) or is_service_alert(resp):
        return True
    kind = str(getattr(resp, "kind", "") or "")
    if kind == KIND_HTTP:
        return True
    try:
        http = int(getattr(resp, "http_status", 0) or 0)
    except (TypeError, ValueError):
        http = 0
    return 400 <= http < 500
