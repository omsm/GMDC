"""
Timeout Configuration Module for Weighbridge Automation System.

This module contains all timeout and timing constants that can be modified
without recompiling the executable. After building the EXE, copy this file
to the same directory as the executable to customize timeouts.

Modify these values based on your site-specific requirements:
- Entry/Exit timeouts: Adjust based on typical vehicle movement times
- Weight capture timeout: Adjust based on digitizer response time
- API timeouts: Adjust based on network/server response times
- Hardware timeouts: Adjust based on device communication speeds
- Safety delays: Adjust based on operational requirements

Version: 1.0.0
"""
__version__ = "1.0.0"

import logging
logger = logging.getLogger("weighbridge.timeout_config")

# Verification logging - confirms this file is loaded from external .py (not cached/bundled)

class TIMEOUTS:
    """All timeout values in seconds"""
    
    # Entry/Exit Timeouts
    ENTRY_TIMEOUT = 180  # Time to wait for vehicle to enter after RFID scan
    EXIT_TIMEOUT = 120  # Time to wait for vehicle to exit
    
    # Weight Capture Timeouts
    WEIGHT_CAPTURE_TIMEOUT = 300  # Max time for weight capture
    WEIGHT_STABLE_DELAY = 0.5  # Delay between weight readings
    middle_sensor_check_timeout = 120  # Align with Weighbridge-App deployment copy

    # API Timeouts
    API_REQUEST_TIMEOUT = 180  # HTTP request timeout
    WEIGHT_VALIDATION_TIMEOUT = 60  # Time to wait for weight validation callback
    
    # Hardware Timeouts
    RFID_RECONNECT_DELAY = 5  # Delay before RFID reconnection attempt
    MODBUS_TIMEOUT = 2  # Modbus communication timeout
    SERIAL_TIMEOUT = 2  # Serial port timeout
    
    # Safety Delays
    POST_EXIT_DELAY = 5  # Wait after vehicle exits before reset
    SENSOR_DEBOUNCE = 0.1  # Sensor debounce time
    
    # RFID API Delay
    RFID_WAIT_TO_API_CALL = 10  # Wait time before making RFID API call

    # RFID Socket Buffer
    # Used by IoT-Configuration RFID check/read loops and can also be reused by runtime.
    RFID_SOCKET_RECV_SIZE = 1024  # Socket recv() buffer size (bytes)

    # Digitizer serial read sizes (IoT digitizer_service.py + Weighbridge hardware/digitizer.py)
    DIGITIZER_SERIAL_READ_SIZE = 50
    DIGITIZER_SERIAL_DRAIN_MAX = 512
    DIGITIZER_SERIAL_INTER_BYTE_WAIT_MS = 80
    DIGITIZER_STALE_BUFFER_BYTES = 64
    DIGITIZER_SLOW_BAUD_THRESHOLD = 4800
    DIGITIZER_SLOW_BAUD_POLL_WAIT_S = 0.4

    # IoT digitizer calibration: minimum parsed weight (kg) for conversion method selection
    DIGITIZER_CALIBRATION_MIN_WEIGHT_KG = 500

    # I/O Controller Defaults
    # Keep these defaults when UI payload does not provide values.
    IO_CONTROLLER_ETHERNET_PORT = 502
    IO_CONTROLLER_ETHERNET_TIMEOUT = 1.0
    IO_CONTROLLER_SERIAL_TIMEOUT = 0.5


# Weight Constants
DEFAULT_STABLE_COUNT = 5  # Number of identical readings for stable weight

# RFID calibration / runtime: tag hex must start with one of these prefixes (case-insensitive)
VALID_CARDS_START_INDEX = ["341", "E28"]

# Accepted RFID/FASTag hex lengths (characters). Not every tag is 24 chars - some are 32.
# During RFID calibration, the entered tag length must match one of these.
CHAR_LENGTH = ["24", "32"]
