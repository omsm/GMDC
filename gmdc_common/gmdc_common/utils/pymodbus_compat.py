"""
pymodbus changed the Modbus unit / slave keyword across versions:
- 3.7+: device_id
- 3.x (many builds): unit
- older: slave

Use inspect so one codebase works with the installed client.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict


def pymodbus_unit_kw(method: Callable[..., Any], slave_id: int) -> Dict[str, int]:
    """Return a single keyword dict for the Modbus unit address on this pymodbus build."""
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        params = {}
    if "device_id" in params:
        return {"device_id": slave_id}
    if "unit" in params:
        return {"unit": slave_id}
    if "slave" in params:
        return {"slave": slave_id}
    return {}


def read_coils_compat(client: Any, address: int, count: int, slave_id: int = 1) -> Any:
    method = client.read_coils
    return method(address=address, count=count, **pymodbus_unit_kw(method, slave_id))


def read_discrete_inputs_compat(
    client: Any, address: int, count: int, slave_id: int = 1
) -> Any:
    method = client.read_discrete_inputs
    return method(address=address, count=count, **pymodbus_unit_kw(method, slave_id))


def write_coil_compat(client: Any, address: int, value: bool, slave_id: int = 1) -> Any:
    method = client.write_coil
    return method(address=address, value=value, **pymodbus_unit_kw(method, slave_id))


def write_register_compat(
    client: Any, address: int, value: int, slave_id: int = 1
) -> Any:
    method = client.write_register
    return method(address=address, value=value, **pymodbus_unit_kw(method, slave_id))


def read_holding_registers_compat(
    client: Any, address: int, count: int, slave_id: int = 1
) -> Any:
    method = client.read_holding_registers
    return method(address=address, count=count, **pymodbus_unit_kw(method, slave_id))
