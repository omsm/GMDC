# GMDC Checkpoint Configuration Tool
# Copied from wb-old/IoT-Configuration and being refactored for all GMDC site types.

# =====================================================
# DEBUG MODE
# =====================================================
DEBUG = True

# =====================================================
# CAMERA CONFIGURATION UI
# =====================================================
# Checkpoints configure Front; weighbridges configure Top + Front.
ENABLE_CAMERA_CONFIGURATION = True

# =====================================================
# WB SENSOR I/O TEST SKIP (CONFIG-ONLY)
# =====================================================
ENABLE_WB_SENSOR_TEST_SKIP = False

# =====================================================
# DIGITIZER MODE
# =====================================================
# API: configure digitizer-app host/port and test POST /read_stable_weight
# (serial COM / index picker removed for GMDC - digitizer runs on another PC)
DIGITIZER_MODE = "api"
DIGITIZER_DEFAULT_PORT = 8100
DIGITIZER_STABLE_WEIGHT_PATH = "/read_stable_weight"

import os

# =====================================================
# APPLICATION UI LAUNCH
# =====================================================
APPLICATION_UI_MODE = "auto"
WEBVIEW_WINDOW_READY_TIMEOUT = 15
CHROME_EXECUTABLE_PATH = ""

# =====================================================
# BIDIRECTIONAL ENTRY LABELS (JSON keys + UI)
# =====================================================
BIDIRECTIONAL_ENTRY_A_KEY = "entry_a"
BIDIRECTIONAL_ENTRY_B_KEY = "entry_b"
BIDIRECTIONAL_ENTRY_KEYS = (BIDIRECTIONAL_ENTRY_A_KEY, BIDIRECTIONAL_ENTRY_B_KEY)
BIDIRECTIONAL_ENTRY_LABEL = {
    BIDIRECTIONAL_ENTRY_A_KEY: "ENTRY A",
    BIDIRECTIONAL_ENTRY_B_KEY: "ENTRY B",
}
LEGACY_BIDIRECTIONAL_DIRECTION_A_KEY = "direction_a"
LEGACY_BIDIRECTIONAL_DIRECTION_B_KEY = "direction_b"

# =====================================================
# APPLICATION SETTINGS
# =====================================================
APP_NAME = "GMDC Checkpoint Config"

_default_version = "0.1.0"
try:
    import sys
    _candidate_paths = []
    if getattr(sys, "frozen", False):
        _exe_dir = os.path.dirname(sys.executable)
        _candidate_paths.append(os.path.join(_exe_dir, "app_version.txt"))
    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_current_dir)
    _candidate_paths.append(os.path.join(_project_root, "app_version.txt"))
    _candidate_paths.append(os.path.join(_current_dir, "app_version.txt"))
    _candidate_paths.append(os.path.join(os.getcwd(), "app_version.txt"))
    for _version_path in _candidate_paths:
        if os.path.exists(_version_path):
            with open(_version_path, "r", encoding="utf-8") as _vf:
                _file_version = _vf.read().strip()
                if _file_version:
                    _default_version = _file_version
                    break
except Exception:
    pass

APP_VERSION = _default_version
UPDATE_CHECK_INTERVAL_SECONDS = 120

HOST = "0.0.0.0"
# Must match Zebra HTTP POST destination (same as Mine-entry / site app):
# http://<pc-ip>:8080/rfid_data
PORT = 8080

# =====================================================
# NETWORK SCANNER SETTINGS
# =====================================================
SCAN_TIMEOUT = 0.3
MAX_SCAN_THREADS = 50

# =====================================================
# DEVICE PORTS
# =====================================================
RFID_DEFAULT_PORT = 5555  # Zebra cloud / unused for API tag push
MODBUS_DEFAULT_PORT = 502
RTSP_DEFAULT_PORT = 554
MQTT_DEFAULT_PORT = 1883

# =====================================================
# SERIAL PORT SETTINGS (I/O Modbus RTU only - not digitizer)
# =====================================================
DEFAULT_BAUD_RATE = 9600
AVAILABLE_BAUD_RATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

# =====================================================
# FILE PATHS
# =====================================================
CONFIG_FILE = "iot_configuration.json"
FINAL_CONFIG_FILE = "iot_configuration.json"

# =====================================================
# VALIDATION SETTINGS
# =====================================================
REQUIRE_DEVICE_INFO = not DEBUG

# Config schema version for GMDC multi-checkpoint configs
SCHEMA_VERSION = 1
