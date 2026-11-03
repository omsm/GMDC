"""Re-export shared Modbus I/O from gmdc_common."""

from gmdc_common.hardware.io_controller import (  # noqa: F401
    DemoIOController,
    IOController,
    IO_CONNECTION_FAILURE_MSG,
    IO_NOT_CONFIGURED_MSG,
    ModbusTCPController,
    PYMODBUS_AVAILABLE,
    create_io_controller,
    is_controller_host_configured,
)

__all__ = [
    "DemoIOController",
    "IOController",
    "IO_CONNECTION_FAILURE_MSG",
    "IO_NOT_CONFIGURED_MSG",
    "ModbusTCPController",
    "PYMODBUS_AVAILABLE",
    "create_io_controller",
    "is_controller_host_configured",
]
