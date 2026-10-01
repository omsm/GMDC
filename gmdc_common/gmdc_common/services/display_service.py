"""MQTT (and console) display service shared by GMDC apps.

Protocol (device identity = Display IP):
  - Always subscribe:  display_info/{display_ip}
  - On any message:    publish pcb_id/{display_ip}  payload \"a\" or \"b\"
      Uni / checkpoint (1 IP): always site pcb_mode (usually a)
      Bi (2 IPs): first IP → a (Entry A), second IP → b (Entry B)
  - Transaction text:
      Uni / checkpoint: publish data_info/a (or data_info/{pcb_mode})
      Bi-directional idle: publish data_info/a AND data_info/b
      Bi-directional transaction: publish only the side the vehicle entered
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Union

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

TOPIC_DISPLAY_INFO_PREFIX = "display_info"
TOPIC_PCB_ID_PREFIX = "pcb_id"
TOPIC_DATA_INFO_PREFIX = "data_info"


def normalize_display_ips(ips: Optional[Union[str, Sequence[str]]]) -> List[str]:
    """Return unique non-empty display IP strings (order preserved)."""
    if ips is None:
        return []
    if isinstance(ips, str):
        raw = [ips]
    else:
        raw = list(ips)
    out: List[str] = []
    seen = set()
    for item in raw:
        ip = str(item or "").strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        out.append(ip)
    return out


def resolve_pcb_mode(*, is_bidirectional: bool = False) -> str:
    """PCB / data_info mode letter: a = uni/checkpoint, b = bi-directional WB."""
    return "b" if is_bidirectional else "a"


def display_info_topic(display_ip: str) -> str:
    return f"{TOPIC_DISPLAY_INFO_PREFIX}/{str(display_ip).strip()}"


def pcb_id_topic(display_ip: str) -> str:
    return f"{TOPIC_PCB_ID_PREFIX}/{str(display_ip).strip()}"


def data_info_topic(pcb_mode: str) -> str:
    mode = str(pcb_mode or "a").strip().lower()[:1] or "a"
    if mode not in ("a", "b"):
        mode = "a"
    return f"{TOPIC_DATA_INFO_PREFIX}/{mode}"


def data_info_topics_for_ips(
    display_ips: Sequence[str], *, pcb_mode: str = "a", side: Optional[str] = None
) -> List[str]:
    """
    TX topics for configured displays.

    Uni / checkpoint (1 IP, mode a): data_info/a
    Bi-directional (2 IPs): data_info/a and data_info/b (Entry A + Entry B)

    ``side`` "a" or "b" keeps only that topic when both exist.
    """
    ips = normalize_display_ips(display_ips)
    if len(ips) >= 2:
        topics = [data_info_topic("a"), data_info_topic("b")]
    else:
        mode = str(pcb_mode or "a").strip().lower()[:1] or "a"
        if mode not in ("a", "b"):
            mode = "a"
        topics = [data_info_topic(mode)]
    letter = str(side or "").strip().lower()[:1]
    if letter in ("a", "b") and data_info_topic(letter) in topics:
        return [data_info_topic(letter)]
    return topics


def pcb_letter_for_display_ip(
    display_ip: str, display_ips: Sequence[str], *, pcb_mode: str = "a"
) -> str:
    """
    PCB reply letter for a Display IP.

    Uni: always site pcb_mode (usually a).
    Bi with 2 IPs: first IP → a (Entry A), second IP → b (Entry B).
    """
    ips = normalize_display_ips(display_ips)
    ip = str(display_ip or "").strip()
    if len(ips) >= 2:
        for idx, configured in enumerate(ips):
            if configured.lower() == ip.lower():
                return "a" if idx == 0 else "b"
        return "b"
    mode = str(pcb_mode or "a").strip().lower()[:1] or "a"
    return mode if mode in ("a", "b") else "a"


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

    def __init__(self, pcb_mode: str = "a", display_ips: Optional[Sequence[str]] = None):
        self._last = ""
        mode = str(pcb_mode or "a").strip().lower()[:1] or "a"
        self.pcb_mode = mode if mode in ("a", "b") else "a"
        self.display_ips = normalize_display_ips(display_ips)

    def connect(self) -> bool:
        logger.info(
            "ConsoleDisplayService ready mode=%s ips=%s",
            self.pcb_mode,
            self.display_ips,
        )
        return True

    def disconnect(self) -> None:
        pass

    def send(self, text: str, side: Optional[str] = None) -> bool:
        self._last = text
        topics = data_info_topics_for_ips(
            self.display_ips, pcb_mode=self.pcb_mode, side=side
        )
        for topic in topics:
            logger.info("DISPLAY[%s]: %s", topic, text)
        return True

    def clear(self) -> bool:
        self._last = ""
        logger.info("DISPLAY: [cleared]")
        return True

    def get_status(self) -> dict:
        topics = data_info_topics_for_ips(
            self.display_ips, pcb_mode=self.pcb_mode
        )
        return {
            "type": "console",
            "pcb_mode": self.pcb_mode,
            "display_ips": list(self.display_ips),
            "topic_tx": topics[0] if topics else data_info_topic(self.pcb_mode),
            "topic_tx_list": topics,
            "last": self._last,
        }


class MQTTDisplayService(DisplayService):
    """
    MQTT display client.

    Subscribes to display_info/{ip} for each configured Display IP and answers
    pcb_id/{ip} with a/b (per IP on bi).     Transaction payloads go to data_info/a (uni). On a bidirectional
    bridge, idle text goes to both boards and a transaction goes only to
    the side the vehicle entered.
    """

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        display_ips: Optional[Sequence[str]] = None,
        pcb_mode: str = "a",
        client_id: str = "gmdc_display",
        topic_tx: Optional[str] = None,
    ):
        self.broker = broker or "127.0.0.1"
        self.port = int(port or 1883)
        self.display_ips = normalize_display_ips(display_ips)
        mode = str(pcb_mode or "a").strip().lower()[:1] or "a"
        self.pcb_mode = mode if mode in ("a", "b") else "a"
        self._tx_topics = data_info_topics_for_ips(
            self.display_ips, pcb_mode=self.pcb_mode
        )
        self.topic_tx = self._tx_topics[0] if self._tx_topics else data_info_topic(
            self.pcb_mode
        )
        if topic_tx and str(topic_tx).startswith(TOPIC_DATA_INFO_PREFIX):
            # Keep legacy single topic only when uni (1 IP)
            if len(self.display_ips) < 2:
                self.topic_tx = str(topic_tx)
                self._tx_topics = [self.topic_tx]
        self.client_id = client_id
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        self._last = ""
        self._handshake_counts = {ip: 0 for ip in self.display_ips}
        self._welcome_sent = False

    def _publish_text(self, client, text: str, side: Optional[str] = None) -> bool:
        """Publish transaction text. ``side`` limits a bidirectional board."""
        topics = data_info_topics_for_ips(
            self.display_ips, pcb_mode=self.pcb_mode, side=side
        )
        self._tx_topics = topics
        if topics:
            self.topic_tx = topics[0]
        ok_any = False
        for topic in topics:
            try:
                client.publish(topic, str(text), qos=1)
                logger.info("DISPLAY MQTT -> %s: %s", topic, text)
                ok_any = True
            except Exception as e:
                logger.error("MQTT publish failed topic=%s: %s", topic, e)
        return ok_any

    def connect(self) -> bool:
        if not MQTT_AVAILABLE:
            logger.error("paho-mqtt not installed")
            return False
        if not self.display_ips:
            logger.error("MQTT display requires at least one Display IP")
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
                if self._connected:
                    for ip in self.display_ips:
                        topic = display_info_topic(ip)
                        client.subscribe(topic)
                        logger.info("MQTT display subscribed %s", topic)
                    # Once per process: publish Welcome when MQTT first connects
                    if not self._welcome_sent:
                        self._welcome_sent = True
                        try:
                            if self._publish_text(client, "Welcome"):
                                self._last = "Welcome"
                        except Exception as exc:
                            logger.warning("Welcome publish failed: %s", exc)
                logger.info("MQTT display connected rc=%s", rc)

            def _on_message(client, userdata, msg):
                self._handle_display_info(msg.topic, msg.payload)

            self._client.on_connect = _on_connect
            self._client.on_message = _on_message

            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
            self._connected = True
            logger.info(
                "MQTT display connecting to %s:%s mode=%s ips=%s tx=%s",
                self.broker,
                self.port,
                self.pcb_mode,
                self.display_ips,
                self._tx_topics,
            )
            return True
        except Exception as e:
            logger.error("MQTT display connect failed: %s", e)
            self._connected = False
            return False

    def _handle_display_info(self, topic: str, payload: bytes) -> None:
        topic = str(topic or "")
        prefix = f"{TOPIC_DISPLAY_INFO_PREFIX}/"
        if not topic.startswith(prefix):
            return
        display_ip = topic[len(prefix) :].strip()
        if display_ip not in self.display_ips:
            match = next(
                (ip for ip in self.display_ips if ip.lower() == display_ip.lower()),
                None,
            )
            if not match:
                logger.debug("Ignoring display_info for unknown IP topic=%s", topic)
                return
            display_ip = match
        try:
            raw = payload.decode("utf-8", errors="replace") if payload else ""
        except Exception:
            raw = ""
        ok = self._publish_pcb_id(display_ip)
        letter = pcb_letter_for_display_ip(
            display_ip, self.display_ips, pcb_mode=self.pcb_mode
        )
        self._handshake_counts[display_ip] = (
            self._handshake_counts.get(display_ip, 0) + 1
        )
        logger.info(
            "display_info/%s received (%r) -> pcb_id/%s = %s ok=%s",
            display_ip,
            raw[:80],
            display_ip,
            letter,
            ok,
        )

    def _publish_pcb_id(self, display_ip: str) -> bool:
        with self._lock:
            if not self._client:
                return False
            try:
                topic = pcb_id_topic(display_ip)
                letter = pcb_letter_for_display_ip(
                    display_ip, self.display_ips, pcb_mode=self.pcb_mode
                )
                self._client.publish(topic, str(letter), qos=1)
                return True
            except Exception as e:
                logger.error("pcb_id publish failed: %s", e)
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

    def send(self, text: str, side: Optional[str] = None) -> bool:
        self._last = text
        with self._lock:
            if not self._client:
                logger.warning("MQTT display not connected - text=%s", text)
                return False
            return self._publish_text(self._client, text, side=side)

    def clear(self) -> bool:
        return self.send("")

    def get_status(self) -> dict:
        topics = data_info_topics_for_ips(
            self.display_ips, pcb_mode=self.pcb_mode
        )
        return {
            "type": "mqtt",
            "broker": self.broker,
            "port": self.port,
            "pcb_mode": self.pcb_mode,
            "display_ips": list(self.display_ips),
            "topic_tx": topics[0] if topics else data_info_topic(self.pcb_mode),
            "topic_tx_list": topics,
            "handshake_counts": dict(self._handshake_counts),
            "connected": self._connected,
            "last": self._last,
        }


def create_display_service(
    display_type: str,
    broker: str,
    port: int,
    topic_tx: str = "",
    demo_fallback: bool = True,
    client_id: str = "gmdc_display",
    display_ips: Optional[Union[str, Sequence[str]]] = None,
    pcb_mode: str = "a",
    is_bidirectional: bool = False,
) -> DisplayService:
    """
    Build display service.

    ``display_ips``: device IP(s) used in display_info/pcb_id topics.
    ``pcb_mode`` / ``is_bidirectional``: a (uni/checkpoint) or b (bi WB).
    Broker is the MQTT broker (usually localhost), not the display device IP.
    """
    dtype = (display_type or "mqtt").lower()
    mode = str(pcb_mode or "").strip().lower()[:1]
    if mode not in ("a", "b"):
        mode = resolve_pcb_mode(is_bidirectional=is_bidirectional)
    ips = normalize_display_ips(display_ips)

    if dtype == "mqtt" and MQTT_AVAILABLE:
        if not ips:
            logger.warning("No Display IP configured - using console display")
            return ConsoleDisplayService(pcb_mode=mode, display_ips=ips)
        svc = MQTTDisplayService(
            broker=broker or "127.0.0.1",
            port=port,
            display_ips=ips,
            pcb_mode=mode,
            client_id=client_id,
            topic_tx=topic_tx or None,
        )
        if svc.connect():
            return svc
        if demo_fallback:
            logger.warning("MQTT connect failed - using console display")
            return ConsoleDisplayService(pcb_mode=mode, display_ips=ips)
        return svc
    return ConsoleDisplayService(pcb_mode=mode, display_ips=ips)
