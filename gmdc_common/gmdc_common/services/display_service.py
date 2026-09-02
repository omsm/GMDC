"""MQTT (and console) display service shared by GMDC apps."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("gmdc_common.services.display")

MQTT_AVAILABLE = False
try:
    import paho.mqtt.client as mqtt

    MQTT_AVAILABLE = True
    try:
        from paho.mqtt.client import CallbackAPIVersion

        MQTT_V2 = True
    except ImportError:
        CallbackAPIVersion = None  # type: ignore
        MQTT_V2 = False
except ImportError:
    mqtt = None  # type: ignore
    MQTT_V2 = False


class DisplayService(ABC):
    @abstractmethod
    def send(self, text: str) -> bool:
        pass

    @abstractmethod
    def clear(self) -> bool:
        pass

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    def get_status(self) -> dict:
        return {"type": self.__class__.__name__}


class ConsoleDisplayService(DisplayService):
    """Fallback: log display text (demo / no MQTT)."""

    def __init__(self):
        self._last = ""

    def connect(self) -> bool:
        logger.info("ConsoleDisplayService ready")
        return True

    def disconnect(self) -> None:
        pass

    def send(self, text: str) -> bool:
        self._last = text
        logger.info("DISPLAY: %s", text)
        return True

    def clear(self) -> bool:
        self._last = ""
        logger.info("DISPLAY: [cleared]")
        return True

    def get_status(self) -> dict:
        return {"type": "console", "last": self._last}


class MQTTDisplayService(DisplayService):
    def __init__(
        self,
        broker: str,
        port: int = 1883,
        topic_tx: str = "iot_display/application_to_display",
        client_id: str = "gmdc_display",
    ):
        self.broker = broker
        self.port = port
        self.topic_tx = topic_tx
        self.client_id = client_id
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        self._last = ""

    def connect(self) -> bool:
        if not MQTT_AVAILABLE:
            logger.error("paho-mqtt not installed")
            return False
        try:
            if MQTT_V2 and CallbackAPIVersion is not None:
                self._client = mqtt.Client(
                    callback_api_version=CallbackAPIVersion.VERSION2,
                    client_id=self.client_id,
                )
            else:
                self._client = mqtt.Client(client_id=self.client_id)

            def _on_connect(client, userdata, flags, reason_code, properties=None):
                rc = reason_code if isinstance(reason_code, int) else getattr(
                    reason_code, "value", reason_code
                )
                self._connected = rc == 0
                logger.info("MQTT display connected rc=%s", rc)

            try:
                self._client.on_connect = _on_connect
            except Exception:
                pass

            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
            self._connected = True
            logger.info(
                "MQTT display connecting to %s:%s topic=%s",
                self.broker,
                self.port,
                self.topic_tx,
            )
            return True
        except Exception as e:
            logger.error("MQTT display connect failed: %s", e)
            self._connected = False
            return False

    def disconnect(self) -> None:
        with self._lock:
            if self._client:
                try:
                    self._client.loop_stop()
                    self._client.disconnect()
                except Exception:
                    pass
                self._client = None
            self._connected = False

    def send(self, text: str) -> bool:
        self._last = text
        with self._lock:
            if not self._client:
                logger.warning("MQTT display not connected - text=%s", text)
                return False
            try:
                self._client.publish(self.topic_tx, text)
                logger.info("DISPLAY MQTT -> %s: %s", self.topic_tx, text)
                return True
            except Exception as e:
                logger.error("MQTT publish failed: %s", e)
                return False

    def clear(self) -> bool:
        return self.send("")

    def get_status(self) -> dict:
        return {
            "type": "mqtt",
            "broker": self.broker,
            "port": self.port,
            "topic_tx": self.topic_tx,
            "connected": self._connected,
            "last": self._last,
        }


def create_display_service(
    display_type: str,
    broker: str,
    port: int,
    topic_tx: str,
    demo_fallback: bool = True,
    client_id: str = "gmdc_display",
) -> DisplayService:
    dtype = (display_type or "mqtt").lower()
    if dtype == "mqtt" and MQTT_AVAILABLE:
        svc = MQTTDisplayService(
            broker=broker, port=port, topic_tx=topic_tx, client_id=client_id
        )
        if svc.connect():
            return svc
        if demo_fallback:
            logger.warning("MQTT connect failed - using console display")
            return ConsoleDisplayService()
        return svc
    return ConsoleDisplayService()
