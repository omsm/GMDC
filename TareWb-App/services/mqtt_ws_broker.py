"""
Minimal MQTT 3.1.1 broker over WebSocket (port 9001).

Paho JS in the dashboard connects here:
  ws://<weighbridge-ip>:9001/  (also /mqtt and /ws)

If Mosquitto (or another process) already owns :9001, the in-app broker
skips binding and FrontendMqtt publishes over MQTT TCP :1883 instead —
the browser still uses ws://<pc-ip>:9001 on Mosquitto.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import logging
import socket
import struct
import threading
from typing import Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("tare_wb.services.mqtt_ws")

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MQTT_WS_PORT = 9001

CONNACK = b"\x20\x02\x00\x00"
PINGRESP = b"\xd0\x00"


def encode_remaining_length(length: int) -> bytes:
    out = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length > 0:
            digit |= 0x80
        out.append(digit)
        if length == 0:
            break
    return bytes(out)


def decode_remaining_length(buf: bytes, start: int = 1) -> Tuple[int, int]:
    multiplier = 1
    value = 0
    pos = start
    while True:
        if pos >= len(buf):
            return -1, start
        digit = buf[pos]
        pos += 1
        value += (digit & 127) * multiplier
        if (digit & 128) == 0:
            return value, pos
        multiplier *= 128
        if multiplier > 128 * 128 * 128:
            return -1, pos


def mqtt_str(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("!H", len(data)) + data


def encode_publish(
    topic: str, payload: bytes, qos: int = 0, packet_id: int = 1, retain: bool = False
) -> bytes:
    # Paho JS over this hub is reliable with QoS 0. QoS 1 retained PUBLISH
    # was aborting remaining dashboard subscriptions (device_status/status).
    header = 0x30
    if retain:
        header |= 0x01
    variable = mqtt_str(topic)
    remaining = encode_remaining_length(len(variable) + len(payload))
    return bytes([header]) + remaining + variable + payload


def topic_matches(filter_topic: str, topic: str) -> bool:
    if filter_topic == topic:
        return True
    if filter_topic == "#":
        return True
    if filter_topic.endswith("/#"):
        prefix = filter_topic[:-2]
        return topic == prefix or topic.startswith(prefix + "/")
    if "+" in filter_topic:
        fparts = filter_topic.split("/")
        tparts = topic.split("/")
        if len(fparts) != len(tparts):
            return False
        for fp, tp in zip(fparts, tparts):
            if fp not in ("+", tp):
                return False
        return True
    return False


def _ws_accept(key: str) -> str:
    digest = hashlib.sha1((key + WS_MAGIC).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _ws_handshake(raw: bytes) -> Optional[bytes]:
    try:
        text = raw.decode("iso-8859-1")
    except Exception:
        return None
    if "Upgrade: websocket" not in text and "upgrade: websocket" not in text.lower():
        return None
    key = ""
    protocol = ""
    for line in text.split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
        if line.lower().startswith("sec-websocket-protocol:"):
            protocol = line.split(":", 1)[1].strip()
    if not key:
        return None
    extra = ""
    if "mqtt" in protocol.lower():
        extra = "Sec-WebSocket-Protocol: mqtt\r\n"
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {_ws_accept(key)}\r\n"
        f"{extra}"
        "\r\n"
    ).encode("ascii")


def decode_ws_frames(buf: bytearray) -> Tuple[List[Tuple[int, bytes]], bytearray]:
    messages: List[Tuple[int, bytes]] = []
    while True:
        if len(buf) < 2:
            break
        b1, b2 = buf[0], buf[1]
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        idx = 2
        if length == 126:
            if len(buf) < 4:
                break
            length = struct.unpack("!H", buf[2:4])[0]
            idx = 4
        elif length == 127:
            if len(buf) < 10:
                break
            length = struct.unpack("!Q", buf[2:10])[0]
            idx = 10
        mask = b""
        if masked:
            if len(buf) < idx + 4:
                break
            mask = bytes(buf[idx : idx + 4])
            idx += 4
        if len(buf) < idx + length:
            break
        payload = bytes(buf[idx : idx + length])
        del buf[: idx + length]
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x8:  # close
            messages.append((0x8, b""))
            break
        if opcode in (0x0, 0x1, 0x2, 0x9, 0xA):
            messages.append((opcode, payload))
    return messages, buf


def encode_ws_frame(payload: bytes, opcode: int = 0x2) -> bytes:
    header = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header += bytes([n])
    elif n < 65536:
        header += b"\x7e" + struct.pack("!H", n)
    else:
        header += b"\x7f" + struct.pack("!Q", n)
    return header + payload


class _Client:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.subs: Set[str] = set()
        self.lock = threading.Lock()

    def send_mqtt(self, packet: bytes) -> None:
        self.send_ws(packet, opcode=0x2)

    def send_ws(self, payload: bytes, opcode: int = 0x2) -> None:
        try:
            with self.lock:
                self.sock.sendall(encode_ws_frame(payload, opcode=opcode))
        except OSError:
            pass


class MqttWebSocketBroker:
    """In-process MQTT-over-WebSocket hub for wb_frontend/*."""

    def __init__(self, host: str = "0.0.0.0", port: int = MQTT_WS_PORT):
        self.host = host
        self.port = int(port)
        self._sock: Optional[socket.socket] = None
        self._clients: List[_Client] = []
        self._retained: Dict[str, Tuple[bytes, int]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_incoming: Optional[Callable[[str, str], None]] = None
        self._pid = 0
        self._running = False

    def set_incoming_handler(self, handler: Callable[[str, str], None]) -> None:
        self._on_incoming = handler

    def _next_packet_id(self) -> int:
        self._pid = (self._pid % 65535) + 1
        return self._pid

    @property
    def running(self) -> bool:
        return bool(self._running and self._thread and self._thread.is_alive())

    def start(self) -> bool:
        if self.running:
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(32)
            sock.settimeout(1.0)
            self._sock = sock
        except OSError as e:
            in_use = getattr(e, "errno", None) in (
                getattr(errno, "EADDRINUSE", 48),
                48,
                98,
            ) or "Address already in use" in str(e)
            if in_use:
                logger.info(
                    "MQTT WebSocket port %s already in use (Mosquitto or another "
                    "broker) — skipping in-app broker. Browser keeps using "
                    "ws://<pc-ip>:%s; this app publishes over MQTT TCP :1883.",
                    self.port,
                    self.port,
                )
            else:
                logger.error(
                    "MQTT WebSocket bind %s:%s failed: %s", self.host, self.port, e
                )
            self._running = False
            return False
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, name="MqttWS", daemon=True)
        self._thread.start()
        logger.info(
            "MQTT WebSocket broker on ws://0.0.0.0:%s (browser: ws://<pc-ip>:%s)",
            self.port,
            self.port,
        )
        return True

    def stop(self) -> None:
        self._running = False
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.sock.close()
            except OSError:
                pass

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = True) -> bool:
        if not self.running:
            return False
        data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload or b"")
        qos_i = 0
        keep = retain and not topic.endswith(
            ("request_status", "reset_application", "free_pass")
        )
        if keep:
            with self._lock:
                self._retained[topic] = (data, qos_i)
        packet = encode_publish(topic, data, qos=0, retain=keep)
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            if any(topic_matches(flt, topic) for flt in client.subs):
                client.send_mqtt(packet)
        return True

    def _accept_loop(self) -> None:
        assert self._sock
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            logger.info("MQTT WS client %s", addr)
            threading.Thread(
                target=self._client_loop, args=(conn,), name="MqttWSClient", daemon=True
            ).start()

    def _client_loop(self, conn: socket.socket) -> None:
        client = _Client(conn)
        buf = bytearray()
        mqtt_buf = bytearray()
        try:
            conn.settimeout(30.0)
            hdr = b""
            while b"\r\n\r\n" not in hdr:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                hdr += chunk
            resp = _ws_handshake(hdr)
            if not resp:
                conn.close()
                return
            conn.sendall(resp)
            extra = hdr.split(b"\r\n\r\n", 1)[1]
            buf.extend(extra)
            with self._lock:
                self._clients.append(client)
            while not self._stop.is_set():
                try:
                    data = conn.recv(8192)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf.extend(data)
                frames, buf = decode_ws_frames(buf)
                for opcode, payload in frames:
                    if opcode == 0x8:
                        return
                    if opcode == 0x9:
                        client.send_ws(payload, opcode=0xA)
                        continue
                    if opcode == 0xA:
                        continue
                    mqtt_buf.extend(payload)
                    mqtt_buf = self._handle_mqtt(client, mqtt_buf)
        except OSError:
            pass
        finally:
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
            try:
                conn.close()
            except OSError:
                pass

    def _handle_mqtt(self, client: _Client, buf: bytearray) -> bytearray:
        while len(buf) >= 2:
            remaining, hdr_end = decode_remaining_length(buf, 1)
            if remaining < 0:
                break
            total = hdr_end + remaining
            if len(buf) < total:
                break
            packet = bytes(buf[:total])
            del buf[:total]
            ptype = packet[0] >> 4
            body = packet[hdr_end:]
            if ptype == 1:  # CONNECT
                client.send_mqtt(CONNACK)
            elif ptype == 3:  # PUBLISH
                pkt_id = self._on_client_publish(packet[0], body)
                if pkt_id:
                    client.send_mqtt(b"\x40\x02" + pkt_id)
            elif ptype == 8:  # SUBSCRIBE
                self._on_subscribe(client, body)
            elif ptype == 12:  # PINGREQ
                client.send_mqtt(PINGRESP)
            elif ptype == 14:  # DISCONNECT
                break
        return buf

    def _on_subscribe(self, client: _Client, body: bytes) -> None:
        if len(body) < 2:
            return
        pkt_id = body[:2]
        idx = 2
        granted = bytearray()
        while idx + 2 <= len(body):
            tlen = struct.unpack("!H", body[idx : idx + 2])[0]
            idx += 2
            topic = body[idx : idx + tlen].decode("utf-8", errors="replace")
            idx += tlen
            qos = 0
            if idx < len(body):
                qos = body[idx] & 0x03
                idx += 1
            client.subs.add(topic)
            granted.append(0x00)
            logger.info("MQTT WS subscribe %s", topic)
        remaining = encode_remaining_length(2 + len(granted))
        client.send_mqtt(b"\x90" + remaining + pkt_id + bytes(granted))
        with self._lock:
            retained = list(self._retained.items())
        for topic, (payload, _qos) in retained:
            if any(topic_matches(flt, topic) for flt in client.subs):
                client.send_mqtt(encode_publish(topic, payload, qos=0, retain=True))

    def _on_client_publish(self, header: int, body: bytes) -> Optional[bytes]:
        qos = (header >> 1) & 0x03
        if len(body) < 2:
            return None
        tlen = struct.unpack("!H", body[:2])[0]
        topic = body[2 : 2 + tlen].decode("utf-8", errors="replace")
        idx = 2 + tlen
        pkt_id = None
        if qos:
            pkt_id = body[idx : idx + 2]
            idx += 2
        payload = body[idx:].decode("utf-8", errors="replace")
        logger.info("MQTT WS from browser topic=%s payload=%s", topic, payload[:80])
        retain = bool(header & 0x01)
        self.publish(topic, payload, qos=qos, retain=retain)
        handler = self._on_incoming
        if handler:
            handler(topic, payload)
        return pkt_id if qos == 1 else None


_BROKER: Optional[MqttWebSocketBroker] = None
_BROKER_LOCK = threading.Lock()


def get_mqtt_ws_broker(port: int = MQTT_WS_PORT) -> MqttWebSocketBroker:
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is None:
            _BROKER = MqttWebSocketBroker(port=port)
        return _BROKER
