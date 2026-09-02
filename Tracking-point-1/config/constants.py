"""State, Event enums and timeout constants for Tracking Point FSM."""

from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    RFID_READ = auto()
    RFID_VALIDATE = auto()
    RFID_ERROR = auto()
    DISPLAY_TRUCK = auto()
    ANPR_VALIDATE = auto()
    MANUAL_UPDATE = auto()
    ENTRY_GRANTED = auto()
    WAIT_CROSSING = auto()
    FREE_PASS = auto()
    ERROR = auto()


class Event(Enum):
    RFID_RECEIVED = auto()
    RFID_VALID = auto()
    RFID_INVALID = auto()
    RFID_ERROR_TIMEOUT = auto()
    ANPR_MATCH = auto()
    ANPR_MISMATCH = auto()
    UPDATE_STATUS_0 = auto()
    UPDATE_STATUS_1 = auto()
    UPDATE_STATUS_2 = auto()
    STATUS_2_TIMEOUT = auto()
    ENTRY_OPENED = auto()
    EXIT_SENSOR = auto()
    CROSSING_TIMEOUT = auto()
    RESET = auto()
    FREE_PASS = auto()
    ERROR_OCCURRED = auto()


class TIMEOUTS:
    """Timeouts in seconds (from PDF workflow)."""

    RFID_ERROR_DISPLAY_SEC = 10.0
    MANUAL_UPDATE_POLL_SEC = 2.0
    UPDATE_STATUS_2_RESET_SEC = 10.0
    RFID_COLLECT_WINDOW_SEC = 2.0
    OCI_REQUEST_TIMEOUT_SEC = 15.0
    SENSOR_POLL_SEC = 0.3
    MODBUS_TIMEOUT_SEC = 1.0
    VEHICLE_CROSSING_TIMEOUT_SEC = 60.0
    # Vehicle cleared the sensor - keep the boom up this long before closing
    BOOM_CLOSE_DELAY_SEC = 10.0
    ANPR_API_MAX_RETRIES = 3
    ANPR_API_RETRY_DELAY_SEC = 2.0
    ANPR_ERR_2_DISPLAY_SEC = 5.0  # wait after Err-2 retry failure before IDLE


# Display messages (PDF)
MSG_RFID_ERR = "RFID ERR 1"
MSG_ANPR_ERR = "ANPR ERR 1"
MSG_ANPR_ERR_2 = "ANPR Err-2"
MSG_ANPR_API_ERR = "ANPR API ERR"
MSG_ENTRY_GRANTED_FMT = "{truck} Entry Granted"
MSG_FREE_PASS = "FREE PASS"
