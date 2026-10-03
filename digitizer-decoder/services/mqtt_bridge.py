"""MQTT transport for live digitizer weight and dashboard status."""

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
WEIGHT_PUBLISH_INTERVAL_SEC = 0.2


def _unique_client_id(base: str) -> str:
    """Prefix from config + current local datetime for a unique MQTT client id."""
    prefix = (base or "gmdc-digitizer-decoder").strip() or "gmdc-digitizer-decoder"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}"


class MqttBridge:
    """
    In MQTT mode the decoder only reads the digitizer and publishes it.
    Every weight, including zero and repeats, is published every 200 ms.
    A message on the request topic publishes the current value immediately.
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
        weight_stream: bool = False,
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
        self.weight_stream = bool(weight_stream)
        self.weight_publish_interval_sec = WEIGHT_PUBLISH_INTERVAL_SEC
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.RLock()
        self._status_provider: Optional[Callable[[], Dict[str, Any]]] = None
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._weight_stop = threading.Event()
        self._weight_thread: Optional[threading.Thread] = None

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
        self._start_weight_publisher()
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
        self._stop_weight_publisher()
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

    def publish_weight(
        self,
        weight: Optional[float],
        *,
        source: str = "live",
    ) -> None:
        """Publish one weight sample, including zero and repeated values."""
        if not self.weight_stream:
            return
        client = self._client
        if not client or not self._connected:
            return
        if weight is None:
            return
        try:
            numeric = float(weight)
        except (TypeError, ValueError):
            return
        payload = {
            "statusCode": 200,
            "current_weight": numeric,
            "weight": numeric,
            "ts": time.time(),
            "source": source,
        }
        try:
            client.publish(
                self.topic_publish,
                json.dumps(payload),
                qos=0,
                retain=False,
            )
            logger.debug("MQTT weight -> %s %s", self.topic_publish, payload)
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

    def publish_current_weight(self, *, source: str = "live") -> None:
        """Publish the latest digitizer reading, including zero."""
        current = self.runtime.snapshot().get("current_weight")
        self.publish_weight(current, source=source)

    def _start_weight_publisher(self) -> None:
        """Publish the current weight every 200 ms while MQTT mode is on."""
        self._stop_weight_publisher()
        if not self.weight_stream:
            return
        self._weight_stop.clear()

        def _loop() -> None:
            while not self._weight_stop.is_set():
                if self._connected:
                    self.publish_current_weight(source="live")
                if self._weight_stop.wait(self.weight_publish_interval_sec):
                    break

        self._weight_thread = threading.Thread(
            target=_loop, name="DigitizerMqttWeight", daemon=True
        )
        self._weight_thread.start()

    def _stop_weight_publisher(self) -> None:
        self._weight_stop.set()
        thread = self._weight_thread
        self._weight_thread = None
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.0)

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
            if self.weight_stream:
                client.subscribe(self.topic_subscribe, qos=0)
                self._set_status(
                    f"MQTT connected — subscribed {self.topic_subscribe}"
                )
            else:
                self._set_status("MQTT connected")
            self.publish_ui_status()
        else:
            self._set_status(f"MQTT connect rc={rc}")

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        self._connected = False
        self._set_status(f"MQTT disconnected rc={rc}")

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        if not self.weight_stream:
            return
        if (msg.topic or "") != self.topic_subscribe:
            return
        raw = msg.payload.decode("utf-8", errors="replace") if msg.payload else ""
        logger.info("MQTT request topic=%s payload=%s", msg.topic, raw[:200])
        snap = self.runtime.snapshot()
        self.publish_weight(snap.get("current_weight"), source="request")
