"""Modbus TCP I/O controller shared by all GMDC checkpoint apps."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from gmdc_common.utils.pymodbus_compat import (
    read_coils_compat,
    read_discrete_inputs_compat,
    write_coil_compat,
    write_register_compat,
)

logger = logging.getLogger("gmdc_common.hardware.io")

try:
    from pymodbus.client import ModbusTcpClient

    PYMODBUS_AVAILABLE = True
except ImportError:
    try:
        from pymodbus.client.sync import ModbusTcpClient  # type: ignore

        PYMODBUS_AVAILABLE = True
    except ImportError:
        ModbusTcpClient = None  # type: ignore
        PYMODBUS_AVAILABLE = False

# Industry Modbus function codes (strict — no cross-fallback).
FC_READ_COILS = 1
FC_READ_DISCRETE_INPUTS = 2
FC_WRITE_SINGLE_COIL = 5
FC_WRITE_SINGLE_REGISTER = 6

ALLOWED_READ_FC = frozenset({FC_READ_COILS, FC_READ_DISCRETE_INPUTS})
ALLOWED_WRITE_FC = frozenset({FC_WRITE_SINGLE_COIL, FC_WRITE_SINGLE_REGISTER})

LOCALHOST_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", ""})

HealthCallback = Callable[[bool, str], None]

IO_NOT_CONFIGURED_MSG = "Controller not configured. Please Check!"
IO_CONNECTION_FAILURE_MSG = "I/O connection failure. Please Check !"


class IOController(ABC):
    """Abstract Modbus I/O controller."""

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def write_coil(self, address: int, value: bool) -> bool:
        pass

    @abstractmethod
    def read_coils(self, address: int, count: int = 1) -> Optional[List[bool]]:
        pass

    @abstractmethod
    def read_discrete_inputs(
        self, address: int, count: int = 1
    ) -> Optional[List[bool]]:
        pass

    @abstractmethod
    def get_status(self) -> dict:
        pass

    def is_connected(self) -> bool:
        return bool((self.get_status() or {}).get("connected"))

    def is_configured(self) -> bool:
        return True

    def set_health_callback(self, callback: Optional[HealthCallback]) -> None:
        return None

    def ensure_connected(self) -> bool:
        """Reconnect if needed. Return True when the link is usable."""
        return self.is_connected()


class DemoIOController(IOController):
    """In-memory coil/input store for demo_mode (no hardware)."""

    def __init__(self):
        self._coils: Dict[int, bool] = {}
        self._inputs: Dict[int, bool] = {}
        self._lock = threading.Lock()
        self._connected = False
        self.read_fc = FC_READ_DISCRETE_INPUTS
        self.write_fc = FC_WRITE_SINGLE_COIL
        self._health_callback: Optional[HealthCallback] = None

    def connect(self) -> bool:
        self._connected = True
        logger.info("DemoIOController connected")
        self._emit_health(True, "")
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._emit_health(False, "Demo I/O disconnected")

    def write_coil(self, address: int, value: bool) -> bool:
        with self._lock:
            self._coils[address] = bool(value)
        logger.debug("Demo write_coil addr=%s value=%s", address, value)
        return True

    def read_coils(self, address: int, count: int = 1) -> Optional[List[bool]]:
        with self._lock:
            return [self._coils.get(address + i, False) for i in range(count)]

    def read_discrete_inputs(
        self, address: int, count: int = 1
    ) -> Optional[List[bool]]:
        with self._lock:
            return [self._inputs.get(address + i, False) for i in range(count)]

    def set_input(self, address: int, value: bool) -> None:
        """Test helper: simulate sensor input."""
        with self._lock:
            self._inputs[address] = bool(value)

    def is_connected(self) -> bool:
        return bool(self._connected)

    def is_configured(self) -> bool:
        return True

    def set_health_callback(self, callback: Optional[HealthCallback]) -> None:
        self._health_callback = callback

    def ensure_connected(self) -> bool:
        if self._connected:
            return True
        return self.connect()

    def _emit_health(self, healthy: bool, message: str) -> None:
        cb = self._health_callback
        if not cb:
            return
        try:
            cb(healthy, message)
        except Exception:
            logger.exception("I/O health callback failed")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "type": "demo",
                "connected": self._connected,
                "configured": True,
                "healthy": self._connected,
                "read_fc": self.read_fc,
                "write_fc": self.write_fc,
                "coils": dict(self._coils),
                "inputs": dict(self._inputs),
                "last_error": "",
            }


class ModbusTCPController(IOController):
    """
    Modbus TCP client with strict function-code mapping.

      read_fc=1 → FC1 Read Coils only (via read_discrete_inputs routing)
      read_fc=2 → FC2 Read Discrete Inputs only
      write_fc=5 → FC5 Write Single Coil only
      write_fc=6 → FC6 Write Single Register only

    There is no FC2↔FC1 cross-fallback on failure.
    On any transaction failure the socket is closed and reopened immediately.
    """

    #: Immediate reconnect on the first failed transaction.
    RESYNC_AFTER_FAILURES = 1

    def __init__(
        self,
        host: str,
        port: int = 502,
        slave_id: int = 1,
        timeout: float = 1.0,
        read_fc: int = FC_READ_DISCRETE_INPUTS,
        write_fc: int = FC_WRITE_SINGLE_COIL,
        di_start: int = 0,
        do_start: int = 0,
        configured: bool = True,
    ):
        self.host = str(host or "").strip()
        self.port = int(port)
        self.slave_id = int(slave_id)
        self.timeout = float(timeout)
        self.read_fc = int(read_fc)
        self.write_fc = int(write_fc)
        self.di_start = int(di_start)
        self.do_start = int(do_start)
        self._configured = bool(configured)
        self._client = None
        self._lock = threading.Lock()
        self._failures = 0
        self._healthy = False
        self._last_error = ""
        self._health_callback: Optional[HealthCallback] = None

        if self.read_fc not in ALLOWED_READ_FC:
            raise ValueError(
                f"Unsupported digital_inputs.function_code={self.read_fc}; "
                f"allowed={sorted(ALLOWED_READ_FC)}"
            )
        if self.write_fc not in ALLOWED_WRITE_FC:
            raise ValueError(
                f"Unsupported digital_outputs.function_code={self.write_fc}; "
                f"allowed={sorted(ALLOWED_WRITE_FC)}"
            )

    def set_health_callback(self, callback: Optional[HealthCallback]) -> None:
        self._health_callback = callback

    def is_configured(self) -> bool:
        return self._configured and is_controller_host_configured(self.host)

    def is_connected(self) -> bool:
        with self._lock:
            return self._client_connected_locked()

    def _client_connected_locked(self) -> bool:
        return bool(
            self._client is not None
            and getattr(self._client, "connected", False)
        )

    def _emit_health_locked(self, healthy: bool, message: str) -> None:
        prev = self._healthy
        self._healthy = bool(healthy)
        if healthy:
            self._last_error = ""
        elif message:
            self._last_error = str(message)
        if prev == self._healthy:
            return
        cb = self._health_callback
        if not cb:
            return
        err = self._last_error
        healthy_flag = bool(healthy)

        def _run() -> None:
            try:
                cb(healthy_flag, err)
            except Exception:
                logger.exception("I/O health callback failed")

        threading.Thread(target=_run, name="IOHealthNotify", daemon=True).start()

    def connect(self) -> bool:
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        if not self.is_configured():
            self._last_error = IO_NOT_CONFIGURED_MSG
            self._emit_health_locked(False, self._last_error)
            logger.error("ModbusTCP connect refused - controller not configured")
            return False
        if not PYMODBUS_AVAILABLE:
            self._last_error = "pymodbus not installed"
            self._emit_health_locked(False, self._last_error)
            logger.error("pymodbus not installed")
            return False
        try:
            self._close_locked()
            self._client = ModbusTcpClient(
                host=self.host, port=self.port, timeout=self.timeout
            )
            ok = bool(self._client.connect())
            if ok:
                self._failures = 0
                self._last_error = ""
                logger.info(
                    "ModbusTCP connected %s:%s slave=%s read_fc=%s write_fc=%s "
                    "di_start=%s do_start=%s",
                    self.host,
                    self.port,
                    self.slave_id,
                    self.read_fc,
                    self.write_fc,
                    self.di_start,
                    self.do_start,
                )
                self._emit_health_locked(True, "")
            else:
                self._last_error = (
                    f"{IO_CONNECTION_FAILURE_MSG} ({self.host}:{self.port})"
                )
                logger.error(
                    "ModbusTCP failed to connect %s:%s", self.host, self.port
                )
                self._close_locked()
                self._emit_health_locked(False, self._last_error)
            return ok
        except Exception as e:
            self._last_error = f"{IO_CONNECTION_FAILURE_MSG} ({e})"
            logger.exception("ModbusTCP connect error: %s", e)
            self._close_locked()
            self._emit_health_locked(False, self._last_error)
            return False

    def disconnect(self) -> None:
        with self._lock:
            self._close_locked()
            self._emit_health_locked(False, "I/O disconnected")

    def _close_locked(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception as exc:
                logger.debug("ModbusTCP close error: %s", exc)
            self._client = None

    def ensure_connected(self) -> bool:
        with self._lock:
            if self._client_connected_locked():
                return True
            return self._connect_locked()

    def _note_result_locked(self, ok: bool, op: str) -> None:
        """Reopen the socket immediately after a failed transaction."""
        if ok:
            self._failures = 0
            if not self._healthy:
                self._emit_health_locked(True, "")
            return
        self._failures += 1
        if self._failures < self.RESYNC_AFTER_FAILURES:
            return
        msg = f"{IO_CONNECTION_FAILURE_MSG} ({op})"
        logger.warning(
            "ModbusTCP %s failed on %s:%s - reopening socket immediately",
            op,
            self.host,
            self.port,
        )
        self._close_locked()
        self._emit_health_locked(False, msg)
        self._connect_locked()

    def write_coil(self, address: int, value: bool) -> bool:
        """Write one DO. address is absolute coil/register address (do_start + pin)."""
        with self._lock:
            if not self._client_connected_locked():
                if not self._connect_locked():
                    return False
            try:
                if self.write_fc == FC_WRITE_SINGLE_REGISTER:
                    result = write_register_compat(
                        self._client, address, 1 if value else 0, self.slave_id
                    )
                elif self.write_fc == FC_WRITE_SINGLE_COIL:
                    result = write_coil_compat(
                        self._client, address, bool(value), self.slave_id
                    )
                else:
                    logger.error("Unsupported write_fc=%s", self.write_fc)
                    self._note_result_locked(False, "write_coil")
                    return False
                ok = result is not None and not (
                    hasattr(result, "isError") and result.isError()
                )
                logger.debug(
                    "write_fc=%s addr=%s value=%s ok=%s",
                    self.write_fc,
                    address,
                    value,
                    ok,
                )
                self._note_result_locked(ok, "write_coil")
                return ok
            except Exception as e:
                logger.error("write failed addr=%s: %s", address, e)
                self._note_result_locked(False, "write_coil")
                return False

    def read_coils(self, address: int, count: int = 1) -> Optional[List[bool]]:
        """Always FC1 Read Coils — never used as a DI fallback."""
        with self._lock:
            if not self._client_connected_locked():
                if not self._connect_locked():
                    return None
            try:
                result = read_coils_compat(
                    self._client, address, count, self.slave_id
                )
                if result is None or (
                    hasattr(result, "isError") and result.isError()
                ):
                    self._note_result_locked(False, "read_coils")
                    return None
                bits = list(result.bits[:count])
                self._note_result_locked(True, "read_coils")
                return [bool(b) for b in bits]
            except Exception as e:
                logger.error("read_coils failed: %s", e)
                self._note_result_locked(False, "read_coils")
                return None

    def read_discrete_inputs(
        self, address: int, count: int = 1
    ) -> Optional[List[bool]]:
        """
        Read digital inputs using the *configured* read_fc only:
          2 = FC2 discrete inputs, 1 = FC1 coils.

        Failure returns None — callers must not invent a value or switch FC.
        """
        with self._lock:
            if not self._client_connected_locked():
                if not self._connect_locked():
                    return None
            try:
                if self.read_fc == FC_READ_COILS:
                    result = read_coils_compat(
                        self._client, address, count, self.slave_id
                    )
                elif self.read_fc == FC_READ_DISCRETE_INPUTS:
                    result = read_discrete_inputs_compat(
                        self._client, address, count, self.slave_id
                    )
                else:
                    logger.error("Unsupported read_fc=%s", self.read_fc)
                    self._note_result_locked(False, "read_discrete_inputs")
                    return None
                if result is None or (
                    hasattr(result, "isError") and result.isError()
                ):
                    logger.error(
                        "read_fc=%s failed addr=%s count=%s: %s",
                        self.read_fc,
                        address,
                        count,
                        result,
                    )
                    self._note_result_locked(False, "read_discrete_inputs")
                    return None
                bits = list(result.bits[:count])
                self._note_result_locked(True, "read_discrete_inputs")
                return [bool(b) for b in bits]
            except Exception as e:
                logger.error("read_discrete_inputs failed: %s", e)
                self._note_result_locked(False, "read_discrete_inputs")
                return None

    def get_status(self) -> dict:
        with self._lock:
            connected = self._client_connected_locked()
            return {
                "type": "modbus_tcp",
                "host": self.host,
                "port": self.port,
                "slave_id": self.slave_id,
                "read_fc": self.read_fc,
                "write_fc": self.write_fc,
                "di_start": self.di_start,
                "do_start": self.do_start,
                "configured": self.is_configured(),
                "connected": connected,
                "healthy": bool(self._healthy and connected),
                "last_error": self._last_error,
            }


def is_controller_host_configured(host: Optional[str]) -> bool:
    text = str(host or "").strip().lower()
    return bool(text) and text not in LOCALHOST_HOSTS


def create_io_controller(
    io_cfg: Dict[str, Any], demo_mode: bool = False
) -> IOController:
    if demo_mode:
        return DemoIOController()

    conn = io_cfg.get("connection", {}).get("ethernet", {}) or {}
    host = str(conn.get("ip") or "").strip()
    port = int(conn.get("port") or 502)
    timeout = float(conn.get("timeout") or 1.0)
    slave_id = int(io_cfg.get("slave_id") or 1)

    di_cfg = io_cfg.get("digital_inputs", {}) or {}
    do_cfg = io_cfg.get("digital_outputs", {}) or {}

    raw_read = di_cfg.get("function_code")
    raw_write = do_cfg.get("function_code")
    if raw_read in (None, ""):
        raise ValueError(
            "digital_inputs.function_code is required (1=coils, 2=discrete inputs)"
        )
    if raw_write in (None, ""):
        raise ValueError(
            "digital_outputs.function_code is required (5=coil, 6=register)"
        )
    read_fc = int(raw_read)
    write_fc = int(raw_write)
    if read_fc not in ALLOWED_READ_FC:
        raise ValueError(
            f"digital_inputs.function_code={read_fc} invalid; "
            f"use 1 (coils) or 2 (discrete inputs)"
        )
    if write_fc not in ALLOWED_WRITE_FC:
        raise ValueError(
            f"digital_outputs.function_code={write_fc} invalid; "
            f"use 5 (write coil) or 6 (write register)"
        )

    di_start = int(di_cfg.get("start_address") or 0)
    do_start = int(do_cfg.get("start_address") or 0)
    configured = is_controller_host_configured(host)
    if not configured:
        logger.error(
            "I/O controller host missing or localhost (%r) - not configured",
            host,
        )

    return ModbusTCPController(
        host=host or "127.0.0.1",
        port=port,
        slave_id=slave_id,
        timeout=timeout,
        read_fc=read_fc,
        write_fc=write_fc,
        di_start=di_start,
        do_start=do_start,
        configured=configured,
    )
