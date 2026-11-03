"""Shared Modbus I/O, traffic lights, boom barriers, sensors and RFID readers."""

from gmdc_common.hardware.boom_barrier import BoomBarrier
from gmdc_common.hardware.camera import (
    build_top_photo_filename,
    capture_rtsp_snapshot,
    get_local_ip,
    sanitize_filename_part,
)
from gmdc_common.hardware.io_controller import (
    DemoIOController,
    IOController,
    IO_CONNECTION_FAILURE_MSG,
    IO_NOT_CONFIGURED_MSG,
    ModbusTCPController,
    create_io_controller,
    is_controller_host_configured,
)
from gmdc_common.hardware.rfid_reader import (
    ApiRFIDReader,
    DemoRFIDReader,
    RFIDReader,
    TCPRFIDReader,
    create_rfid_reader,
    extract_id_hexes,
)
from gmdc_common.hardware.sensor import SensorPoller
from gmdc_common.hardware.traffic_light import TrafficLight

__all__ = [
    "BoomBarrier",
    "build_top_photo_filename",
    "capture_rtsp_snapshot",
    "DemoIOController",
    "get_local_ip",
    "IOController",
    "IO_CONNECTION_FAILURE_MSG",
    "IO_NOT_CONFIGURED_MSG",
    "ModbusTCPController",
    "create_io_controller",
    "is_controller_host_configured",
    "ApiRFIDReader",
    "DemoRFIDReader",
    "RFIDReader",
    "TCPRFIDReader",
    "create_rfid_reader",
    "extract_id_hexes",
    "sanitize_filename_part",
    "SensorPoller",
    "TrafficLight",
]
