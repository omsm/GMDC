"""Modbus TCP I/O controller shared by all GMDC checkpoint apps."""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

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


class DemoIOController(IOController):
    """In-memory coil/input store for demo_mode (no hardware)."""

    def __init__(self):
        self._coils: Dict[int, bool] = {}
        self._inputs: Dict[int, bool] = {}
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        logger.info("DemoIOController connected")
        return True

    def disconnect(self) -> None:
        self._connected = False

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

    def get_status(self) -> dict:
        with self._lock:
            return {
                "type": "demo",
                "connected": self._connected,
                "coils": dict(self._coils),
                "inputs": dict(self._inputs),
            }


class ModbusTCPController(IOController):
    """
    Modbus TCP client.

    Verified controller pattern used on site:
      host:port, slave=1, read_fc=2 (DI), write_fc=5 (coil), di=0/8, do=0/8
    """

    #: Failed transactions in a row before the socket is torn down and reopened.
    #: A fresh socket drops frames queued by a desynchronised or shared device
    #: (pymodbus "request ask for transaction_id=N but got id=M, Skipping.").
    RESYNC_AFTER_FAILURES = 3

    def __init__(
        self,
        host: str,
        port: int = 502,
        slave_id: int = 1,
        timeout: float = 1.0,
        read_fc: int = 2,
        write_fc: int = 5,
        di_start: int = 0,
        do_start: int = 0,
    ):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout
        self.read_fc = int(read_fc)
        self.write_fc = int(write_fc)
        self.di_start = int(di_start)
        self.do_start = int(do_start)
        self._client = None
        self._lock = threading.Lock()
        self._failures = 0

    def connect(self) -> bool:
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        if not PYMODBUS_AVAILABLE:
            logger.error("pymodbus not installed")
            return False
        try:
            self._client = ModbusTcpClient(
                host=self.host, port=self.port, timeout=self.timeout
            )
            ok = self._client.connect()
            self._failures = 0
            if ok:
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
            else:
                logger.error(
                    "ModbusTCP failed to connect %s:%s", self.host, self.port
                )
            return bool(ok)
        except Exception as e:
            logger.exception("ModbusTCP connect error: %s", e)
            return False

    def disconnect(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _note_result_locked(self, ok: bool, op: str) -> None:
        """Reopen the socket after a run of failed transactions."""
        if ok:
            self._failures = 0
            return
        self._failures += 1
        if self._failures < self.RESYNC_AFTER_FAILURES:
            return
        logger.warning(
            "ModbusTCP %s failed %s times on %s:%s - reopening socket to resync",
            op,
            self._failures,
            self.host,
            self.port,
        )
        self._close_locked()
        self._connect_locked()

    def write_coil(self, address: int, value: bool) -> bool:
        """Write one DO. address is absolute coil/register address (do_start + pin)."""
        with self._lock:
            if not self._client:
                return False
            try:
                if self.write_fc == 6:
                    result = write_register_compat(
                        self._client, address, 1 if value else 0, self.slave_id
                    )
                else:
                    result = write_coil_compat(
                        self._client, address, bool(value), self.slave_id
                    )
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
        with self._lock:
            if not self._client:
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
        Read digital inputs using configured read_fc:
          2 = discrete inputs (FC2), 1 = coils (FC1).
        """
        with self._lock:
            if not self._client:
                return None
            try:
                if self.read_fc == 1:
                    result = read_coils_compat(
                        self._client, address, count, self.slave_id
                    )
                else:
                    result = read_discrete_inputs_compat(
                        self._client, address, count, self.slave_id
                    )
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
        return {
            "type": "modbus_tcp",
            "host": self.host,
            "port": self.port,
            "slave_id": self.slave_id,
            "read_fc": self.read_fc,
            "write_fc": self.write_fc,
            "di_start": self.di_start,
            "do_start": self.do_start,
            "connected": self._client is not None
            and getattr(self._client, "connected", False),
        }


def create_io_controller(
    io_cfg: Dict[str, Any], demo_mode: bool = False
) -> IOController:
    if demo_mode:
        return DemoIOController()

    conn = io_cfg.get("connection", {}).get("ethernet", {})
    host = conn.get("ip") or "127.0.0.1"
    port = int(conn.get("port") or 502)
    timeout = float(conn.get("timeout") or 1.0)
    slave_id = int(io_cfg.get("slave_id") or 1)

    di_cfg = io_cfg.get("digital_inputs", {}) or {}
    do_cfg = io_cfg.get("digital_outputs", {}) or {}
    read_fc = int(di_cfg.get("function_code") or 2)
    write_fc = int(do_cfg.get("function_code") or 5)
    di_start = int(di_cfg.get("start_address") or 0)
    do_start = int(do_cfg.get("start_address") or 0)

    return ModbusTCPController(
        host=host,
        port=port,
        slave_id=slave_id,
        timeout=timeout,
        read_fc=read_fc,
        write_fc=write_fc,
        di_start=di_start,
        do_start=do_start,
    )
