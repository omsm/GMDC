"""
Digitizer connectivity checks for GMDC weighbridges.

- API mode: POST /read_stable_weight on digitizer-app / digitizer-decoder
- MQTT mode: connect to broker and wait for status/weight from digitizer-decoder
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

try:
    from config import DIGITIZER_DEFAULT_PORT, DIGITIZER_STABLE_WEIGHT_PATH
except ImportError:
    DIGITIZER_DEFAULT_PORT = 8100
    DIGITIZER_STABLE_WEIGHT_PATH = "/read_stable_weight"

DEFAULT_TOPIC_WEIGHT = "gmdc/digitizer/weight"
DEFAULT_TOPIC_REQUEST = "gmdc/digitizer/request"
DEFAULT_TOPIC_STATUS = "gmdc/digitizer/status"


class DigitizerApiService:
    """Reachability / live-weight test against digitizer HTTP or MQTT."""

    def check_connection(self, data: Optional[dict] = None) -> Dict[str, Any]:
        data = data or {}
        mode = str(data.get("mode") or "api").strip().lower()
        if mode == "mqtt":
            return self._check_mqtt(data)
        return self._check_api(data)

    def _check_api(self, data: dict) -> Dict[str, Any]:
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

    def _check_mqtt(self, data: dict) -> Dict[str, Any]:
        broker = str(data.get("broker_host") or data.get("host") or "").strip()
        if not broker:
            return {
                "status": 400,
                "message": "MQTT broker host is required (Mines-WB Mac IP)",
            }
        try:
            port = int(data.get("broker_port") or data.get("port") or 1883)
        except (TypeError, ValueError):
            port = 1883
        timeout = float(data.get("timeout") or 10)
        username = str(data.get("username") or "")
        password = str(data.get("password") or "")
        topic_weight = str(
            data.get("topic_weight")
            or data.get("topic_publish")
            or DEFAULT_TOPIC_WEIGHT
        ).strip() or DEFAULT_TOPIC_WEIGHT
        topic_status = DEFAULT_TOPIC_STATUS
        topic_request = str(
            data.get("topic_request")
            or data.get("topic_subscribe")
            or DEFAULT_TOPIC_REQUEST
        ).strip() or DEFAULT_TOPIC_REQUEST

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return {"status": 500, "message": "paho-mqtt is not installed"}

        got: Dict[str, Any] = {"event": threading.Event(), "payload": None, "topic": ""}

        def _on_connect(client, userdata, flags, rc):  # noqa: ANN001
            if rc != 0:
                got["rc"] = rc
                got["event"].set()
                return
            client.subscribe([(topic_status, 0), (topic_weight, 0)])
            try:
                client.publish(topic_request, "{}", qos=0)
            except Exception:
                pass

        def _on_message(client, userdata, msg):  # noqa: ANN001
            raw = msg.payload.decode("utf-8", errors="replace") if msg.payload else ""
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw_text": raw}
            got["payload"] = parsed
            got["topic"] = msg.topic
            got["event"].set()

        client_id = f"gmdc-config-digitizer-check-{int(time.time())}"
        try:
            client = mqtt.Client(client_id=client_id, clean_session=True)
        except TypeError:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=client_id,
                clean_session=True,
            )
        if username:
            client.username_pw_set(username, password or None)
        client.on_connect = _on_connect
        client.on_message = _on_message

        try:
            client.connect(broker, port, keepalive=30)
        except Exception as exc:
            logger.warning("Digitizer MQTT connect failed: %s", exc)
            return {
                "status": 400,
                "message": f"Cannot connect MQTT broker {broker}:{port} - {exc}",
                "broker": f"{broker}:{port}",
            }

        client.loop_start()
        ok = got["event"].wait(timeout=max(3.0, timeout))
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

        if got.get("rc") not in (None, 0):
            return {
                "status": 400,
                "message": f"MQTT connect rc={got.get('rc')}",
                "broker": f"{broker}:{port}",
            }
        if not ok or got["payload"] is None:
            return {
                "status": 400,
                "message": (
                    f"Connected to {broker}:{port} but no digitizer status/weight "
                    f"on {topic_status} / {topic_weight} within {timeout:.0f}s. "
                    "Start digitizer-decoder with the same broker IP and topics."
                ),
                "broker": f"{broker}:{port}",
                "topic_status": topic_status,
                "topic_weight": topic_weight,
            }

        weight = None
        parsed = got["payload"]
        if isinstance(parsed, dict):
            for key in ("stable_weight", "current_weight", "weight"):
                if parsed.get(key) is not None:
                    try:
                        weight = float(parsed[key])
                        break
                    except (TypeError, ValueError):
                        continue

        return {
            "status": 200,
            "message": (
                f"Digitizer MQTT OK via {broker}:{port}"
                + (f" - weight={weight}" if weight is not None else "")
            ),
            "broker": f"{broker}:{port}",
            "topic": got.get("topic"),
            "weight": weight,
            "raw": parsed if isinstance(parsed, dict) else {"data": parsed},
        }

    def stop(self) -> None:
        """No persistent connection for check-only service."""
        return


digitizer_api_service = DigitizerApiService()
