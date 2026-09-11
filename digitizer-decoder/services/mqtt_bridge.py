"""MQTT transport for stable-weight request / response + live UI status."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from services.weight_runtime import WeightRuntime

logger = logging.getLogger("digitizer_decoder.mqtt")


def _unique_client_id(base: str) -> str:
    """Prefix from config + current local datetime for a unique MQTT client id."""
    prefix = (base or "gmdc-digitizer-decoder").strip() or "gmdc-digitizer-decoder"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}"


class MqttBridge:
    """
    Subscribe for weight requests; publish stable-weight JSON responses.
    Also publishes live dashboard status on ``topic_status`` (WebSocket UI).

    Request payloads (any of):
      {} | {"action":"read_stable_weight"} | "read_stable_weight"
    Response (publish topic):
      {"statusCode":200,"stable_weight":43000.0}
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
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.RLock()
        self._status_provider: Optional[Callable[[], Dict[str, Any]]] = None

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
            # paho-mqtt v2
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
        with self._lock:
            client = self._client
            self._client = None
            self._connected = False
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
        self._set_status("MQTT stopped")

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
        """Publish live dashboard snapshot for browser MQTT clients."""
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
        try:
            client.publish(
                self.topic_status,
                json.dumps(data, default=str),
                qos=0,
                retain=True,
            )
        except Exception as exc:
            logger.warning("MQTT status publish failed: %s", exc)

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
        body = json.dumps(result)
        try:
            client.publish(self.topic_publish, body, qos=0, retain=False)
            logger.info("MQTT response -> %s %s", self.topic_publish, body)
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
