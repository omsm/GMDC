"""MQTT transport for stable-weight request / response + live UI status."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from services.weight_runtime import WeightRuntime

logger = logging.getLogger("digitizer_decoder.mqtt")

HEARTBEAT_INTERVAL_SEC = 2.0


def _unique_client_id(base: str) -> str:
    """Prefix from config + current local datetime for a unique MQTT client id."""
    prefix = (base or "gmdc-digitizer-decoder").strip() or "gmdc-digitizer-decoder"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}"


class MqttBridge:
    """
    Subscribe for weight requests; publish stable-weight JSON responses.
    Publishes live weight only when the value changes.
    Publishes retained status snapshots + periodic heartbeats for Mines-WB sync.
    """

    def __init__(
        self,
        runtime: WeightRuntime,
        *,
        broker_host: str,
        broker_port: int = 1883,
        username: str = "",
        password: str = "",
        topic_publish: str = "gmdc/digitizer/weight",
        topic_subscribe: str = "gmdc/digitizer/request",
        topic_status: str = "gmdc/digitizer/status",
        client_id: str = "gmdc-digitizer-decoder",
        on_status: Optional[Callable[[str], None]] = None,
        heartbeat_interval_sec: float = HEARTBEAT_INTERVAL_SEC,
    ) -> None:
        self.runtime = runtime
        self.broker_host = broker_host
        self.broker_port = int(broker_port)
        self.username = username or ""
        self.password = password or ""
        self.topic_publish = topic_publish
        self.topic_subscribe = topic_subscribe
        self.topic_status = (topic_status or "gmdc/digitizer/status").strip() or (
            "gmdc/digitizer/status"
        )
        self.base_client_id = (client_id or "gmdc-digitizer-decoder").strip() or (
            "gmdc-digitizer-decoder"
        )
        self.client_id = self.base_client_id
        self.on_status = on_status
        self.heartbeat_interval_sec = max(1.0, float(heartbeat_interval_sec or 2.0))
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.RLock()
        self._status_provider: Optional[Callable[[], Dict[str, Any]]] = None
        self._last_published_weight: Optional[float] = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def set_status_provider(self, provider: Optional[Callable[[], Dict[str, Any]]]) -> None:
        self._status_provider = provider

    def start(self) -> bool:
        self.stop()
        self.client_id = _unique_client_id(self.base_client_id)
        try:
            client = mqtt.Client(
                client_id=self.client_id,
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )
        except TypeError:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id=self.client_id,
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
            logger.error("MQTT connect failed: %s", exc)
            self._set_status(f"MQTT connect failed: {exc}")
            return False
        self._client = client
        client.loop_start()
        self._start_heartbeat()
        logger.info(
            "MQTT starting broker=%s:%s client_id=%s sub=%s pub=%s status=%s",
            self.broker_host,
            self.broker_port,
            self.client_id,
            self.topic_subscribe,
            self.topic_publish,
            self.topic_status,
        )
        return True

    def stop(self) -> None:
        self._stop_heartbeat()
        with self._lock:
            client = self._client
            self._client = None
            self._connected = False
            self._last_published_weight = None
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
        self._set_status("MQTT stopped")

    def publish_weight_if_changed(
        self,
        weight: Optional[float],
        *,
        stable: bool = False,
        stable_weight: Optional[float] = None,
        force: bool = False,
    ) -> None:
        """Publish live weight only when the numeric value changes (or force)."""
        client = self._client
        if not client or not self._connected:
            return
        if weight is None and not force:
            return
        with self._lock:
            prev = self._last_published_weight
            if (
                not force
                and prev is not None
                and weight is not None
                and float(prev) == float(weight)
            ):
                return
            self._last_published_weight = weight
        payload = {
            "statusCode": 200,
            "current_weight": weight,
            "weight": weight,
            "stable": bool(stable),
            "stable_weight": stable_weight if stable else None,
            "ts": time.time(),
            "source": "live",
        }
        try:
            client.publish(
                self.topic_publish,
                json.dumps(payload),
                qos=0,
                retain=False,
            )
            logger.debug("MQTT weight change -> %s %s", self.topic_publish, payload)
        except Exception as exc:
            logger.warning("MQTT weight publish failed: %s", exc)

    def publish_live(self, payload: Dict[str, Any]) -> None:
        client = self._client
        if not client or not self._connected:
            return
        try:
            client.publish(
                self.topic_publish,
                json.dumps(payload),
                qos=0,
                retain=False,
            )
        except Exception as exc:
            logger.warning("MQTT publish failed: %s", exc)

    def publish_ui_status(self, payload: Optional[Dict[str, Any]] = None) -> None:
        """Publish live dashboard snapshot for browser / Mines-WB heartbeat."""
        client = self._client
        if not client or not self._connected:
            return
        data = payload
        if data is None and self._status_provider:
            try:
                data = self._status_provider()
            except Exception as exc:
                logger.debug("status provider failed: %s", exc)
                return
        if not data:
            return
        out = dict(data)
        out.setdefault("ts", time.time())
        out["heartbeat"] = True
        try:
            client.publish(
                self.topic_status,
                json.dumps(out, default=str),
                qos=0,
                retain=True,
            )
        except Exception as exc:
            logger.warning("MQTT status publish failed: %s", exc)

    def _start_heartbeat(self) -> None:
        self._heartbeat_stop.clear()

        def _loop() -> None:
            while not self._heartbeat_stop.wait(self.heartbeat_interval_sec):
                if self._connected:
                    self.publish_ui_status()

        self._heartbeat_thread = threading.Thread(
            target=_loop, name="DigitizerMqttHeartbeat", daemon=True
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        self._heartbeat_thread = None

    def _set_status(self, msg: str) -> None:
        logger.info(msg)
        if self.on_status:
            try:
                self.on_status(msg)
            except Exception:
                pass

    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        self._connected = rc == 0
        if rc == 0:
            client.subscribe(self.topic_subscribe, qos=0)
            self._set_status(
                f"MQTT connected — subscribed {self.topic_subscribe}"
            )
            self.publish_ui_status()
            snap = self.runtime.snapshot()
            self.publish_weight_if_changed(
                snap.get("current_weight"),
                stable=bool(snap.get("stable")),
                stable_weight=snap.get("stable_weight"),
                force=True,
            )
        else:
            self._set_status(f"MQTT connect rc={rc}")

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        self._connected = False
        self._set_status(f"MQTT disconnected rc={rc}")

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        raw = msg.payload.decode("utf-8", errors="replace") if msg.payload else ""
        logger.info("MQTT request topic=%s payload=%s", msg.topic, raw[:200])
        if not self._is_weight_request(raw):
            return
        result = self.runtime.wait_stable()
        body_obj = dict(result) if isinstance(result, dict) else {"result": result}
        body_obj.setdefault("ts", time.time())
        body_obj["source"] = "request"
        body = json.dumps(body_obj)
        try:
            client.publish(self.topic_publish, body, qos=0, retain=False)
            logger.info("MQTT response -> %s %s", self.topic_publish, body)
            weight = None
            for key in ("stable_weight", "current_weight", "weight"):
                if body_obj.get(key) is not None:
                    try:
                        weight = float(body_obj[key])
                        break
                    except (TypeError, ValueError):
                        continue
            if weight is not None:
                with self._lock:
                    self._last_published_weight = weight
        except Exception as exc:
            logger.error("MQTT response publish failed: %s", exc)

    @staticmethod
    def _is_weight_request(raw: str) -> bool:
        text = (raw or "").strip()
        if not text:
            return True
        if text.lower() in ("read_stable_weight", "weight", "stable"):
            return True
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return True
        if not isinstance(data, dict):
            return True
        action = str(data.get("action") or data.get("cmd") or "").strip().lower()
        if not action:
            return True
        return action in ("read_stable_weight", "weight", "stable", "get_weight")
