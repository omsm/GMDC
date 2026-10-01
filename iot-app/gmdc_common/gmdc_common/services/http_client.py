"""Generic Basic-Auth HTTP client used by OCI / ANPR / weighbridge APIs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger("gmdc_common.services.http")


@dataclass
class HttpResponse:
    ok: bool
    status: int
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    truck_details: str = ""
    http_status: int = 0


class BasicAuthHttpClient:
    """
    Thin requests wrapper that logs every call and normalizes JSON responses
    into HttpResponse. Apps build domain-specific clients on top of this.
    """

    def __init__(
        self,
        username: str,
        password: str,
        timeout: float = 15.0,
        log_label: str = "HTTP",
    ):
        self.auth: Tuple[str, str] = (username, password)
        self.timeout = timeout
        self.log_label = log_label
        self._session = requests.Session()

    def post(
        self,
        url: str,
        payload: Dict[str, Any],
        label: str,
        auth: Optional[Tuple[str, str]] = None,
    ) -> HttpResponse:
        use_auth = auth if auth is not None else self.auth
        logger.info(
            "%s %s REQUEST url=%s auth_user=%s payload=%s",
            self.log_label,
            label,
            url,
            use_auth[0] if use_auth else None,
            payload,
        )
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
            except Exception:
                data = {"raw_text": resp.text}
            logger.info(
                "%s %s RESPONSE http=%s body=%s",
                self.log_label,
                label,
                http_status,
                data,
            )
            status_val = data.get("status", http_status if resp.ok else 0)
            try:
                status_int = int(status_val)
            except (TypeError, ValueError):
                status_int = 0
            return HttpResponse(
                ok=resp.ok and status_int in (200, 1),
                status=status_int,
                message=str(data.get("message", "")),
                raw=data if isinstance(data, dict) else {"data": data},
                truck_details=str(data.get("truck_details", "")),
                http_status=http_status,
            )
        except requests.RequestException as e:
            logger.error("%s %s ERROR: %s", self.log_label, label, e)
            return HttpResponse(
                ok=False, status=0, message=str(e), raw={}, http_status=0
            )
