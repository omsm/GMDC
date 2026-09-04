"""
Digitizer-app HTTP client for GMDC weighbridges.

The digitizer runs on another PC and exposes POST /read_stable_weight.
This config tool only stores host/port and verifies the endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

try:
    from config import DIGITIZER_DEFAULT_PORT, DIGITIZER_STABLE_WEIGHT_PATH
except ImportError:
    DIGITIZER_DEFAULT_PORT = 8100
    DIGITIZER_STABLE_WEIGHT_PATH = "/read_stable_weight"


class DigitizerApiService:
    """Reachability / live-weight test against digitizer-app."""

    def check_connection(self, data: Optional[dict] = None) -> Dict[str, Any]:
        data = data or {}
        host = str(data.get("host") or data.get("ip") or "").strip()
        port = str(data.get("port") or DIGITIZER_DEFAULT_PORT).strip()
        path = str(
            data.get("path") or DIGITIZER_STABLE_WEIGHT_PATH or "/read_stable_weight"
        ).strip()
        if not path.startswith("/"):
            path = "/" + path
        timeout = float(data.get("timeout") or 30)

        if not host:
            return {"status": 400, "message": "Digitizer-app host is required"}

        url = f"http://{host}:{port}{path}"
        logger.info("Digitizer API check POST %s timeout=%s", url, timeout)
        try:
            req = Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=timeout) as resp:
                http_status = resp.getcode()
                body_text = resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            body_text = (e.read() or b"").decode("utf-8", errors="replace")
            logger.warning("Digitizer API HTTPError %s: %s", e.code, body_text[:300])
            return {
                "status": 400,
                "message": f"Digitizer-app returned HTTP {e.code}",
                "url": url,
                "raw": body_text[:500],
            }
        except URLError as e:
            logger.warning("Digitizer API URLError: %s", e)
            return {
                "status": 400,
                "message": f"Cannot reach digitizer-app at {host}:{port} - {e.reason}",
                "url": url,
            }
        except Exception as e:
            logger.exception("Digitizer API check failed")
            return {"status": 500, "message": str(e), "url": url}

        weight = None
        parsed: Any = {}
        try:
            parsed = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            parsed = {"raw_text": body_text}

        if isinstance(parsed, dict):
            for key in (
                "stable_weight",
                "current_weight",
                "weight",
                "NetMineralWeight",
                "c_weight",
            ):
                if key in parsed and parsed[key] is not None:
                    try:
                        weight = float(parsed[key])
                        break
                    except (TypeError, ValueError):
                        continue
            # Nested data
            if weight is None and isinstance(parsed.get("data"), dict):
                for key in ("stable_weight", "current_weight", "weight"):
                    if key in parsed["data"]:
                        try:
                            weight = float(parsed["data"][key])
                            break
                        except (TypeError, ValueError):
                            continue

        ok = http_status == 200
        message = (
            f"Digitizer-app OK - stable weight={weight}"
            if ok and weight is not None
            else ("Digitizer-app reachable (HTTP 200)" if ok else f"HTTP {http_status}")
        )
        return {
            "status": 200 if ok else 400,
            "message": message,
            "url": url,
            "http_status": http_status,
            "weight": weight,
            "raw": parsed if isinstance(parsed, dict) else {"data": parsed},
        }

    def stop(self) -> None:
        """No persistent connection for API mode."""
        return


digitizer_api_service = DigitizerApiService()
