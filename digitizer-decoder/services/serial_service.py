"""Serial port reader for weighbridge digitizer frames."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import serial
import serial.tools.list_ports

from config.settings import is_calibrated, serial_port_configured
from services.index_engine import (
    extract_last_complete_index_frame,
    extract_weight_from_indexing,
)
from services.weight_runtime import WeightRuntime

logger = logging.getLogger("digitizer_decoder.serial")

# Fixed block size for all digitizer types (no readline).
READ_BLOCK_BYTES = 40
# Keep a short rolling window so mid-frame alignment still extracts weight.
RX_WINDOW_BYTES = READ_BLOCK_BYTES * 3


def list_serial_ports() -> List[str]:
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return sorted(ports) if ports else []


class SerialService:
    """Background serial reader that feeds WeightRuntime."""

    def __init__(self, runtime: WeightRuntime) -> None:
        self.runtime = runtime
        self._config: Dict[str, Any] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._reconnect_thread: Optional[threading.Thread] = None
        self._port: Optional[serial.Serial] = None
        self._lock = threading.RLock()
        self._running = False
        self._on_raw: Optional[Callable[[bytes], None]] = None
        self._capture_buf = bytearray()
        self._capture_target = 0
        self._capture_event = threading.Event()
        self._capture_lock = threading.Lock()
        self._rx_buf = bytearray()

    @property
    def connected(self) -> bool:
        return bool(self._running and self._port and self._port.is_open)

    def set_raw_listener(self, cb: Optional[Callable[[bytes], None]]) -> None:
        self._on_raw = cb

    def apply_config(self, config: Dict[str, Any]) -> None:
        with self._lock:
            self._config = dict(config or {})
            self.runtime.update_config(self._config)

    def _open_port(self) -> serial.Serial:
        return serial.Serial(
            port=str(self._config["port"]),
            baudrate=int(self._config["baud_rate"]),
            bytesize=int(self._config["data_bits"]),
            parity=str(self._config["parity"]),
            stopbits=float(self._config["stop_bits"]),
            timeout=0.25,
        )

    def start(self) -> bool:
        if not serial_port_configured(self._config):
            logger.warning("Serial start skipped — port settings incomplete")
            return False

        old_thread: Optional[threading.Thread] = None
        with self._lock:
            old_thread = self._thread
            self._stop.set()
            self._running = False
            if self._port and self._port.is_open:
                try:
                    self._port.close()
                except Exception:
                    pass
            self._port = None

        if old_thread and old_thread.is_alive() and old_thread is not threading.current_thread():
            old_thread.join(timeout=2.0)

        with self._lock:
            try:
                self._port = self._open_port()
                try:
                    self._port.reset_input_buffer()
                except Exception:
                    pass
            except (serial.SerialException, ValueError, TypeError) as exc:
                logger.error("Serial open failed: %s", exc)
                self.runtime.set_connected(False)
                self._start_reconnect()
                return False

            self._rx_buf = bytearray()
            self._stop.clear()
            self._running = True
            self.runtime.set_connected(True)
            self._thread = threading.Thread(
                target=self._read_loop, name="DigitizerSerial", daemon=True
            )
            self._thread.start()
            logger.info(
                "Serial connected port=%s baud=%s parity=%s read=%s bytes",
                self._config.get("port"),
                self._config.get("baud_rate"),
                self._config.get("parity"),
                READ_BLOCK_BYTES,
            )
            return True

    def stop(self, reconnect: bool = True) -> None:
        old_thread: Optional[threading.Thread] = None
        with self._lock:
            old_thread = self._thread
            self._stop.set()
            self._running = False
            if self._port and self._port.is_open:
                try:
                    self._port.close()
                except Exception:
                    pass
            self._port = None
            self._rx_buf = bytearray()
            self.runtime.set_connected(False)

        if old_thread and old_thread.is_alive() and old_thread is not threading.current_thread():
            old_thread.join(timeout=2.0)

        if reconnect:
            self._start_reconnect()

    def _start_reconnect(self) -> None:
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop, name="DigitizerReconnect", daemon=True
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self) -> None:
        while not self._running:
            if not serial_port_configured(self._config):
                time.sleep(2.0)
                continue
            if self.start():
                return
            time.sleep(2.0)

    def _read_exact(self, nbytes: int) -> bytes:
        """Block until ``nbytes`` arrive (or stop / port close). Never uses readline."""
        assert self._port is not None
        buf = bytearray()
        while len(buf) < nbytes and not self._stop.is_set():
            if not self._port.is_open:
                break
            try:
                chunk = self._port.read(nbytes - len(buf))
            except serial.SerialException:
                break
            if chunk:
                buf.extend(chunk)
        return bytes(buf)

    def _read_loop(self) -> None:
        """Always ``serial.read`` in 40-byte blocks — works for any digitizer."""
        while not self._stop.is_set() and self._port and self._port.is_open:
            try:
                chunk = self._read_exact(READ_BLOCK_BYTES)
            except serial.SerialException as exc:
                logger.warning("Serial read error: %s", exc)
                break
            except Exception as exc:
                logger.warning("Serial unexpected error: %s", exc)
                break
            if not chunk:
                continue
            self._maybe_capture(chunk)
            if self._on_raw:
                try:
                    self._on_raw(chunk)
                except Exception:
                    pass

            self._rx_buf.extend(chunk)
            if len(self._rx_buf) > RX_WINDOW_BYTES:
                del self._rx_buf[: len(self._rx_buf) - RX_WINDOW_BYTES]

            # Live UI shows the latest block; weight uses the rolling window.
            self._handle_frame(chunk, window=bytes(self._rx_buf))

        self._running = False
        self.runtime.set_connected(False)
        if not self._stop.is_set():
            self._start_reconnect()

    def _handle_frame(self, raw: bytes, window: Optional[bytes] = None) -> None:
        message = raw.decode(errors="replace").rstrip("\r\n")
        # Always surface live raw on the dashboard (even before calibration).
        self.runtime.push_raw(message, raw)

        if not is_calibrated(self._config):
            return
        indexing = self._config.get("indexing")
        if not isinstance(indexing, dict):
            return
        weight = self._extract_weight(window or raw, indexing)
        if weight is None:
            return
        logger.debug("Weight %.2f from %s", weight, message[:80])
        self.runtime.push_weight(weight, message, raw)

    def _extract_weight(
        self, raw_bytes: bytes, indexing: Dict[str, Any]
    ) -> Optional[float]:
        """Extract using indexing; tolerate missing next-frame '[' after ']'."""
        frame = extract_last_complete_index_frame(raw_bytes, indexing)
        for buf in (frame, raw_bytes):
            if not buf:
                continue
            weight = extract_weight_from_indexing(buf, indexing)
            if weight is not None:
                return weight

        # Soft: ignore frame-end (same idea as calibration preview).
        soft = dict(indexing)
        soft["frame_end_char"] = None
        weight = extract_weight_from_indexing(raw_bytes, soft)
        if weight is not None:
            return weight

        # Soft: "][" configs → allow a lone "]" end so "[42000]" works live.
        end = indexing.get("frame_end_char")
        if isinstance(end, str) and end.startswith("]") and len(end) > 1:
            soft2 = dict(indexing)
            soft2["frame_end_char"] = "]"
            return extract_weight_from_indexing(raw_bytes, soft2)
        return None

    def capture_sample(
        self, nbytes: int = READ_BLOCK_BYTES, timeout_sec: float = 5.0
    ) -> bytes:
        """Capture exactly ``nbytes`` (default 40) via ``serial.read`` only."""
        nbytes = max(1, int(nbytes or READ_BLOCK_BYTES))
        if self.connected:
            with self._capture_lock:
                self._capture_buf = bytearray()
                self._capture_target = nbytes
                self._capture_event.clear()
            self._capture_event.wait(timeout=timeout_sec)
            with self._capture_lock:
                data = bytes(self._capture_buf[:nbytes])
                self._capture_target = 0
                self._capture_buf = bytearray()
            return data

        opened = False
        port = None
        try:
            with self._lock:
                port = self._open_port()
            opened = True
            try:
                port.reset_input_buffer()
            except Exception:
                pass
            deadline = time.monotonic() + timeout_sec
            buf = bytearray()
            while time.monotonic() < deadline and len(buf) < nbytes:
                chunk = port.read(nbytes - len(buf))
                if chunk:
                    buf.extend(chunk)
            return bytes(buf[:nbytes])
        except Exception as exc:
            logger.error("Capture open failed: %s", exc)
            return b""
        finally:
            if opened and port is not None:
                try:
                    port.close()
                except Exception:
                    pass

    def _maybe_capture(self, raw: bytes) -> None:
        with self._capture_lock:
            if self._capture_target <= 0:
                return
            need = self._capture_target - len(self._capture_buf)
            if need <= 0:
                self._capture_event.set()
                return
            self._capture_buf.extend(raw[:need])
            if len(self._capture_buf) >= self._capture_target:
                self._capture_event.set()
