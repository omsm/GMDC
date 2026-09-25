"""
Digitizer clients for Mines-WB.

- API mode: POST /read_stable_weight (digitizer-app / digitizer-decoder HTTP)
- MQTT mode: subscribe to live weight + status from digitizer-decoder;
  request stable weight on demand. Broker runs on the Mines-WB Mac;
  decoder on another PC connects to that broker IP.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from services.api_errors import (
    KIND_HTTP,
    KIND_OK,
    KIND_SERVER,
    KIND_UNREACHABLE,
    classify_http_status,
    operator_copy,
)

logger = logging.getLogger("mines_wb.services.digitizer")

DEFAULT_TOPIC_WEIGHT = "gmdc/digitizer/weight"
DEFAULT_TOPIC_REQUEST = "gmdc/digitizer/request"
DEFAULT_TOPIC_STATUS = "gmdc/digitizer/status"
DEFAULT_HEARTBEAT_TIMEOUT_SEC = 5.0


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


class DigitizerClient:
    """HTTP digitizer client (API mode)."""

    mode = "api"

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
        self._listeners: list = []

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def set_update_listener(self, cb: Optional[Callable[[], None]]) -> None:
        self._listeners = [cb] if cb else []

    def get_current_weight(self) -> Optional[float]:
        """No live feed in API mode."""
        return None

    def is_alive(self) -> bool:
        """API mode has no continuous heartbeat; treat as unknown/ok."""
        return True

    def supports_live_weight(self) -> bool:
        return False

    def read_stable_weight(self) -> Dict[str, Any]:
        if self.demo_mode:
            logger.info("Digitizer DEMO weight=%.1f", self.demo_weight_kg)
            return {
                "ok": True,
                "weight": float(self.demo_weight_kg),
                "raw": {"stable_weight": self.demo_weight_kg, "demo": True},
            }

        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

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

        weight = _extract_weight(parsed)
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


class DigitizerMqttClient:
    """MQTT digitizer client — live weight stream + request/response stable read."""

    mode = "mqtt"

    def __init__(
        self,
        *,
        broker_host: str,
        broker_port: int = 1883,
        username: str = "",
        password: str = "",
        topic_weight: str = DEFAULT_TOPIC_WEIGHT,
        topic_request: str = DEFAULT_TOPIC_REQUEST,
        topic_status: str = DEFAULT_TOPIC_STATUS,
        client_id: str = "gmdc-mines-wb-digitizer",
        timeout: float = 30.0,
        heartbeat_timeout_sec: float = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
        demo_mode: bool = False,
        demo_weight_kg: float = 12500.0,
    ) -> None:
        self.broker_host = (broker_host or "127.0.0.1").strip() or "127.0.0.1"
        self.broker_port = int(broker_port or 1883)
        self.username = username or ""
        self.password = password or ""
        self.topic_weight = (topic_weight or DEFAULT_TOPIC_WEIGHT).strip() or DEFAULT_TOPIC_WEIGHT
        self.topic_request = (
            topic_request or DEFAULT_TOPIC_REQUEST
        ).strip() or DEFAULT_TOPIC_REQUEST
        self.topic_status = (
            topic_status or DEFAULT_TOPIC_STATUS
        ).strip() or DEFAULT_TOPIC_STATUS
        self.client_id = (client_id or "gmdc-mines-wb-digitizer").strip()
        self.timeout = float(timeout or 30.0)
        self.heartbeat_timeout_sec = float(
            heartbeat_timeout_sec or DEFAULT_HEARTBEAT_TIMEOUT_SEC
        )
        self.demo_mode = demo_mode
        self.demo_weight_kg = demo_weight_kg

        self._client = None
        self._connected = False
        self._lock = threading.RLock()
        self._current_weight: Optional[float] = None
        self._stable_weight: Optional[float] = None
        self._stable = False
        self._last_heartbeat = 0.0
        self._last_raw: Dict[str, Any] = {}
        self._pending_event = threading.Event()
        self._pending_response: Optional[Dict[str, Any]] = None
        self._awaiting_request = False
        self._listeners: list = []
        self._alive_was = True
        self._started_at = time.monotonic()

    def start(self) -> None:
        if self.demo_mode:
            self._current_weight = 0.0
            self._last_heartbeat = time.monotonic()
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt required for MQTT digitizer")
            return

        self.stop()
        cid = f"{self.client_id}-{int(time.time())}"
        try:
            client = mqtt.Client(client_id=cid, clean_session=True)
        except TypeError:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=cid,
                clean_session=True,
            )
        if self.username:
            client.username_pw_set(self.username, self.password or None)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        try:
            client.connect(self.broker_host, self.broker_port, keepalive=30)
        except Exception as exc:
            logger.error(
                "Digitizer MQTT connect failed %s:%s — %s",
                self.broker_host,
                self.broker_port,
                exc,
            )
            return
        self._client = client
        client.loop_start()
        logger.info(
            "Digitizer MQTT starting broker=%s:%s weight=%s request=%s status=%s",
            self.broker_host,
            self.broker_port,
            self.topic_weight,
            self.topic_request,
            self.topic_status,
        )

    def stop(self) -> None:
        client = self._client
        self._client = None
        self._connected = False
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass

    def set_update_listener(self, cb: Optional[Callable[[], None]]) -> None:
        self._listeners = [cb] if cb else []

    def supports_live_weight(self) -> bool:
        return True

    def get_current_weight(self) -> Optional[float]:
        if self.demo_mode:
            return 0.0
        with self._lock:
            return self._current_weight

    def is_alive(self) -> bool:
        if self.demo_mode:
            return True
        with self._lock:
            # Grace period after start before treating missing heartbeat as hang.
            if not self._last_heartbeat:
                return (time.monotonic() - self._started_at) < max(
                    8.0, self.heartbeat_timeout_sec * 2
                )
            age = time.monotonic() - self._last_heartbeat
            return age <= self.heartbeat_timeout_sec

    def read_stable_weight(self) -> Dict[str, Any]:
        if self.demo_mode:
            logger.info("Digitizer MQTT DEMO weight=%.1f", self.demo_weight_kg)
            return {
                "ok": True,
                "weight": float(self.demo_weight_kg),
                "raw": {"stable_weight": self.demo_weight_kg, "demo": True},
            }

        if not self._client or not self._connected:
            short, title = operator_copy("digitizer", KIND_UNREACHABLE)
            return {
                "ok": False,
                "weight": None,
                "message": "Digitizer MQTT not connected",
                "raw": {},
                "kind": KIND_UNREACHABLE,
                "operator_message": short,
                "popup": True,
                "popup_title": title,
            }

        with self._lock:
            self._awaiting_request = True
            self._pending_response = None
            self._pending_event.clear()

        try:
            self._client.publish(
                self.topic_request,
                json.dumps({"action": "read_stable_weight"}),
                qos=0,
            )
        except Exception as exc:
            logger.warning("Digitizer MQTT request publish failed: %s", exc)
            with self._lock:
                self._awaiting_request = False
            short, title = operator_copy("digitizer", KIND_UNREACHABLE)
            return {
                "ok": False,
                "weight": None,
                "message": str(exc),
                "raw": {},
                "kind": KIND_UNREACHABLE,
                "operator_message": short,
                "popup": True,
                "popup_title": title,
            }

        ok = self._pending_event.wait(timeout=self.timeout)
        with self._lock:
            self._awaiting_request = False
            parsed = self._pending_response
            live_stable = self._stable_weight if self._stable else None

        if not ok or not parsed:
            # Fall back to last known stable from live stream if available.
            if live_stable is not None and float(live_stable) > 0:
                logger.info(
                    "Digitizer MQTT request timed out — using live stable=%.1f",
                    live_stable,
                )
                return {
                    "ok": True,
                    "weight": float(live_stable),
                    "raw": {"stable_weight": live_stable, "source": "live_fallback"},
                    "message": "ok",
                }
            short, title = operator_copy("digitizer", KIND_UNREACHABLE)
            return {
                "ok": False,
                "weight": None,
                "message": f"No MQTT weight response within {self.timeout:.0f}s",
                "raw": {},
                "kind": KIND_UNREACHABLE,
                "operator_message": short,
                "popup": True,
                "popup_title": title,
            }

        weight = _extract_weight(parsed)
        status = parsed.get("statusCode") if isinstance(parsed, dict) else None
        if weight is None or (status is not None and int(status) != 200):
            return {
                "ok": False,
                "weight": weight,
                "raw": parsed,
                "message": "Invalid MQTT weight payload",
                "kind": KIND_HTTP,
                "operator_message": "Digitizer failed",
                "popup": False,
                "popup_title": "",
            }
        return {
            "ok": True,
            "weight": weight,
            "raw": parsed,
            "message": "ok",
        }

    def _notify(self) -> None:
        for cb in list(self._listeners):
            if not cb:
                continue
            try:
                cb()
            except Exception:
                logger.exception("Digitizer update listener failed")

    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        self._connected = rc == 0
        if rc != 0:
            logger.warning("Digitizer MQTT connect rc=%s", rc)
            return
        client.subscribe([(self.topic_weight, 0), (self.topic_status, 0)])
        self._last_heartbeat = time.monotonic()
        logger.info(
            "Digitizer MQTT connected — subscribed %s + %s",
            self.topic_weight,
            self.topic_status,
        )

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        self._connected = False
        logger.warning("Digitizer MQTT disconnected rc=%s", rc)
        self._notify()

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        raw = msg.payload.decode("utf-8", errors="replace") if msg.payload else ""
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw_text": raw}
        if not isinstance(parsed, dict):
            parsed = {"data": parsed}

        topic = msg.topic or ""
        now = time.monotonic()
        weight = _extract_weight(parsed)
        changed = False

        with self._lock:
            if topic == self.topic_status or parsed.get("heartbeat"):
                self._last_heartbeat = now
            if topic == self.topic_weight or weight is not None:
                # Weight messages also prove liveness.
                self._last_heartbeat = now
            if weight is not None:
                if self._current_weight != weight:
                    changed = True
                self._current_weight = weight
            if "stable" in parsed:
                self._stable = bool(parsed.get("stable"))
            if parsed.get("stable_weight") is not None:
                try:
                    self._stable_weight = float(parsed["stable_weight"])
                    self._stable = True
                except (TypeError, ValueError):
                    pass
            self._last_raw = parsed

            if self._awaiting_request and topic == self.topic_weight:
                # Prefer request responses; also accept stable live payloads.
                source = str(parsed.get("source") or "")
                has_stable = parsed.get("stable_weight") is not None or (
                    parsed.get("stable") and weight is not None
                )
                if source == "request" or has_stable or weight is not None:
                    self._pending_response = parsed
                    self._pending_event.set()

        if changed or topic == self.topic_status:
            self._notify()


def create_digitizer_client(settings: Any) -> Any:
    """Build API or MQTT digitizer client from Mines-WB settings."""
    dig = {}
    if hasattr(settings, "digitizer_config"):
        dig = settings.digitizer_config() or {}
    elif isinstance(getattr(settings, "raw_config", None), dict):
        dig = settings.raw_config.get("digitizer") or {}

    mode = str(
        getattr(settings, "digitizer_mode", None) or dig.get("mode") or "api"
    ).strip().lower()
    demo = bool(getattr(settings, "demo_mode", False))
    timeout = float(
        getattr(settings, "digitizer_timeout", None) or dig.get("timeout") or 30
    )

    if mode == "mqtt":
        broker = str(
            getattr(settings, "digitizer_broker_host", None)
            or dig.get("broker_host")
            or dig.get("host")
            or getattr(settings, "mqtt_broker", None)
            or "127.0.0.1"
        ).strip() or "127.0.0.1"
        port = int(
            getattr(settings, "digitizer_broker_port", None)
            or dig.get("broker_port")
            or 1883
        )
        return DigitizerMqttClient(
            broker_host=broker,
            broker_port=port,
            username=str(
                getattr(settings, "digitizer_mqtt_username", None)
                or dig.get("username")
                or ""
            ),
            password=str(
                getattr(settings, "digitizer_mqtt_password", None)
                or dig.get("password")
                or ""
            ),
            topic_weight=str(
                getattr(settings, "digitizer_topic_weight", None)
                or dig.get("topic_weight")
                or dig.get("topic_publish")
                or DEFAULT_TOPIC_WEIGHT
            ),
            topic_request=str(
                getattr(settings, "digitizer_topic_request", None)
                or dig.get("topic_request")
                or dig.get("topic_subscribe")
                or DEFAULT_TOPIC_REQUEST
            ),
            topic_status=DEFAULT_TOPIC_STATUS,
            client_id=str(dig.get("client_id") or "gmdc-mines-wb-digitizer"),
            timeout=timeout,
            heartbeat_timeout_sec=float(
                dig.get("heartbeat_timeout_sec") or DEFAULT_HEARTBEAT_TIMEOUT_SEC
            ),
            demo_mode=demo,
        )

    return DigitizerClient(
        url=settings.digitizer_url,
        timeout=timeout,
        demo_mode=demo,
        demo_weight_kg=12500.0,
    )
