"""Re-export shared pymodbus compatibility helpers from gmdc_common."""

from gmdc_common.utils.pymodbus_compat import (  # noqa: F401
    pymodbus_unit_kw,
    read_coils_compat,
    read_discrete_inputs_compat,
    write_coil_compat,
    write_register_compat,
)

__all__ = [
    "pymodbus_unit_kw",
    "read_coils_compat",
    "read_discrete_inputs_compat",
    "write_coil_compat",
    "write_register_compat",
]
