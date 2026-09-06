"""
Digitizer-app HTTP client.

POST {host}:{port}/read_stable_weight with {} and parse stable weight.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.api_errors import (
    KIND_HTTP,
    KIND_SERVER,
    KIND_UNREACHABLE,
    classify_http_status,
    operator_copy,
)

logger = logging.getLogger("mines_wb.services.digitizer")


class DigitizerClient:
    def __init__(
        self,
        url: str,
        timeout: float = 30.0,
        demo_mode: bool = False,
        demo_weight_kg: float = 12500.0,
    ):
        self.url = url
        self.timeout = timeout
        self.demo_mode = demo_mode
        self.demo_weight_kg = demo_weight_kg

    def read_stable_weight(self) -> Dict[str, Any]:
        if self.demo_mode:
            logger.info("Digitizer DEMO weight=%.1f", self.demo_weight_kg)
            return {
                "ok": True,
                "weight": float(self.demo_weight_kg),
                "raw": {"stable_weight": self.demo_weight_kg, "demo": True},
            }

        logger.info("Digitizer POST %s", self.url)
        try:
            req = Request(
                self.url,
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                http_status = resp.getcode()
        except HTTPError as e:
            body = (e.read() or b"").decode("utf-8", errors="replace")
            logger.warning("Digitizer HTTP %s: %s", e.code, body[:300])
            kind = classify_http_status(int(e.code or 0))
            if kind == KIND_OK:
                kind = KIND_HTTP
            short, title = operator_copy("digitizer", kind)
            popup = kind in (KIND_UNREACHABLE, KIND_SERVER)
            return {
                "ok": False,
                "weight": None,
                "message": f"HTTP {e.code}",
                "raw": body,
                "kind": kind,
                "operator_message": short,
                "popup": popup,
                "popup_title": title if popup else "",
            }
        except URLError as e:
            logger.warning("Digitizer unreachable: %s", e)
            short, title = operator_copy("digitizer", KIND_UNREACHABLE)
            return {
                "ok": False,
                "weight": None,
                "message": str(e.reason),
                "raw": {},
                "kind": KIND_UNREACHABLE,
                "operator_message": short,
                "popup": True,
                "popup_title": title,
            }
        except Exception as e:
            logger.exception("Digitizer read failed")
            short, title = operator_copy("digitizer", KIND_UNREACHABLE)
            return {
                "ok": False,
                "weight": None,
                "message": str(e),
                "raw": {},
                "kind": KIND_UNREACHABLE,
                "operator_message": short,
                "popup": True,
                "popup_title": title,
            }

        parsed: Any = {}
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw_text": body}

        weight = self._extract_weight(parsed)
        if http_status != 200:
            kind = classify_http_status(http_status)
            short, title = operator_copy("digitizer", kind)
            popup = kind in (KIND_UNREACHABLE, KIND_SERVER)
            return {
                "ok": False,
                "weight": weight,
                "http_status": http_status,
                "raw": parsed if isinstance(parsed, dict) else {"data": parsed},
                "message": f"HTTP {http_status}",
                "kind": kind,
                "operator_message": short,
                "popup": popup,
                "popup_title": title if popup else "",
            }
        if weight is None:
            return {
                "ok": False,
                "weight": None,
                "http_status": http_status,
                "raw": parsed if isinstance(parsed, dict) else {"data": parsed},
                "message": "No weight field in response",
                "kind": KIND_HTTP,
                "operator_message": "Digitizer failed",
                "popup": False,
                "popup_title": "",
            }
        return {
            "ok": True,
            "weight": weight,
            "http_status": http_status,
            "raw": parsed if isinstance(parsed, dict) else {"data": parsed},
            "message": "ok",
        }

    @staticmethod
    def _extract_weight(parsed: Any) -> Optional[float]:
        if not isinstance(parsed, dict):
            return None
        for key in (
            "stable_weight",
            "current_weight",
            "weight",
            "NetMineralWeight",
            "c_weight",
        ):
            if key in parsed and parsed[key] is not None:
                try:
                    return float(parsed[key])
                except (TypeError, ValueError):
                    continue
        data = parsed.get("data")
        if isinstance(data, dict):
            for key in ("stable_weight", "current_weight", "weight"):
                if key in data and data[key] is not None:
                    try:
                        return float(data[key])
                    except (TypeError, ValueError):
                        continue
        return None
