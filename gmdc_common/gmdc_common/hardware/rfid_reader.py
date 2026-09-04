"""RFID reader TCP client/server - forwards tag batches to application callback."""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("gmdc_common.hardware.rfid")


def extract_id_hexes(payload: Any) -> List[str]:
    """
    Extract unique idHex values from RFID reader JSON payload.
    Accepts a list of tag objects or a single object / dict wrapper.
    """
    tags: List[Any]
    if isinstance(payload, dict):
        if "tags" in payload:
            tags = payload["tags"]
        elif "data" in payload and isinstance(payload["data"], list):
            tags = payload["data"]
        else:
            tags = [payload]
    elif isinstance(payload, list):
        tags = payload
    else:
        return []

    seen: Set[str] = set()
    ordered: List[str] = []
    for item in tags:
        if not isinstance(item, dict):
            continue
        data = item.get("data", item)
        if not isinstance(data, dict):
            continue
        hex_id = data.get("idHex") or data.get("idhex") or data.get("epc")
        if not hex_id:
            continue
        hex_id = str(hex_id).strip()
        if hex_id and hex_id not in seen:
            seen.add(hex_id)
            ordered.append(hex_id)
    return ordered


class RFIDReader:
    """Base RFID reader with optional TCP bridge."""

    def __init__(
        self,
        on_tags: Optional[Callable[[List[str], List[dict]], None]] = None,
    ):
        self.on_tags = on_tags
        self._running = False

    def start(self) -> bool:
        self._running = True
        return True

    def stop(self) -> None:
        self._running = False

    def inject_payload(self, payload: Any) -> List[str]:
        """Process a payload (used by HTTP /rfid_data and TCP)."""
        tags_raw = payload if isinstance(payload, list) else [payload]
        id_hexes = extract_id_hexes(payload)
        if self.on_tags and id_hexes:
            raw_list = tags_raw if isinstance(tags_raw, list) else []
            self.on_tags(id_hexes, raw_list if isinstance(payload, list) else tags_raw)
        return id_hexes

    def get_status(self) -> dict:
        return {"type": "base", "running": self._running}


class TCPRFIDReader(RFIDReader):
    """
    CLIENT mode: connect to RFID reader (reader is TCP server).
    SERVER mode: listen; RFID reader connects to us.
    """

    def __init__(
        self,
        host: str,
        port: int,
        mode: str = "CLIENT",
        on_tags: Optional[Callable[[List[str], List[dict]], None]] = None,
        reconnect_sec: float = 3.0,
    ):
        super().__init__(on_tags=on_tags)
        self.host = host
        self.port = port
        self.mode = mode.upper()
        self.reconnect_sec = reconnect_sec
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._stop = threading.Event()

    def start(self) -> bool:
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name=f"RFID-{self.mode}", daemon=True
        )
        self._thread.start()
        logger.info(
            "RFIDReader started mode=%s %s:%s", self.mode, self.host, self.port
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        if self.mode == "SERVER":
            self._run_server()
        else:
            self._run_client()

    def _run_client(self) -> None:
        while not self._stop.is_set():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((self.host, self.port))
                self._sock = sock
                logger.info("RFID client connected to %s:%s", self.host, self.port)
                self._read_loop(sock)
            except Exception as e:
                logger.warning(
                    "RFID client error: %s - retry in %ss", e, self.reconnect_sec
                )
            finally:
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
            self._stop.wait(self.reconnect_sec)

    def _run_server(self) -> None:
        while not self._stop.is_set():
            server = None
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                bind_host = "0.0.0.0"
                server.bind((bind_host, self.port))
                server.listen(1)
                server.settimeout(2.0)
                self._sock = server
                logger.info("RFID server listening on %s:%s", bind_host, self.port)
                while not self._stop.is_set():
                    try:
                        conn, addr = server.accept()
                        logger.info("RFID reader connected from %s", addr)
                        self._read_loop(conn)
                        conn.close()
                    except socket.timeout:
                        continue
            except Exception as e:
                logger.warning("RFID server error: %s", e)
            finally:
                if server:
                    try:
                        server.close()
                    except Exception:
                        pass
                self._sock = None
            self._stop.wait(self.reconnect_sec)

    def _read_loop(self, sock: socket.socket) -> None:
        buffer = ""
        sock.settimeout(1.0)
        while not self._stop.is_set():
            try:
                data = sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                buffer = self._try_parse_buffer(buffer)
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug("RFID read loop end: %s", e)
                break

    def _try_parse_buffer(self, buffer: str) -> str:
        buffer = buffer.strip()
        if not buffer:
            return ""
        try:
            payload = json.loads(buffer)
            self.inject_payload(payload)
            return ""
        except json.JSONDecodeError:
            pass
        if "\n" in buffer:
            lines = buffer.split("\n")
            rest = lines[-1]
            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.inject_payload(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON RFID line")
            return rest
        if len(buffer) > 1_000_000:
            logger.warning("RFID buffer overflow - clearing")
            return ""
        return buffer

    def get_status(self) -> dict:
        return {
            "type": "tcp",
            "mode": self.mode,
            "host": self.host,
            "port": self.port,
            "running": self._running,
        }


class DemoRFIDReader(RFIDReader):
    """No TCP - tags arrive only via inject_payload (/rfid_data)."""

    def get_status(self) -> dict:
        return {"type": "demo", "running": self._running}


class ApiRFIDReader(RFIDReader):
    """
    HTTP/API-based RFID (Zebra cloud push, mobile app, /rfid_data).

    No TCP socket to the reader. Tags arrive via Flask endpoints;
    cloud start/stop/mode is handled separately by RFIDCloudControl.
    """

    def get_status(self) -> dict:
        return {
            "type": "api",
            "running": self._running,
            "intake": "POST /rfid_data or POST /rfid_data_from_mobile_app",
        }


def create_rfid_reader(
    rfid_cfg: Dict[str, Any],
    demo_mode: bool = False,
    on_tags: Optional[Callable[[List[str], List[dict]], None]] = None,
) -> RFIDReader:
    if demo_mode or not rfid_cfg:
        return DemoRFIDReader(on_tags=on_tags)

    mode = (rfid_cfg.get("mode") or "API").upper()
    # API / HTTP / CLOUD: reader pushes tags to our Flask API - no TCP bridge
    if mode in ("API", "HTTP", "CLOUD", "REST", "HTTPS"):
        logger.info(
            "RFID mode=%s - using HTTP intake (/rfid_data); TCP client disabled",
            mode,
        )
        return ApiRFIDReader(on_tags=on_tags)

    host = rfid_cfg.get("ip") or "0.0.0.0"
    port = int(rfid_cfg.get("port") or 5555)
    if mode == "SERVER":
        host = "0.0.0.0"
    return TCPRFIDReader(
        host=host, port=port, mode=mode, on_tags=on_tags
    )
