"""State, Event enums and timeouts for Tare Weighbridge FSM (wb_plane.txt)."""

from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    VEHICLE_POSITIONING = auto()
    WEIGHT_CAPTURE = auto()
    RFID_READ = auto()
    RFID_VALIDATE = auto()
    RFID_ERROR = auto()
    ANPR_VALIDATE = auto()
    MANUAL_UPDATE = auto()
    FINAL_WEIGHT = auto()
    IMAGE_CAPTURE = auto()
    WEIGHT_DETAILS = auto()
    EXIT_GRANTED = auto()
    WAIT_EXIT = auto()
    ERROR = auto()
    FREE_PASS = auto()


class Event(Enum):
    ENTRY_SENSOR = auto()
    WB_SENSOR = auto()
    EXIT_SENSOR = auto()
    WEIGHT_OK = auto()
    WEIGHT_LOW = auto()
    WEIGHT_FAIL = auto()
    RFID_RECEIVED = auto()
    RFID_VALID = auto()
    RFID_INVALID = auto()
    RFID_ERROR_TIMEOUT = auto()
    ANPR_MATCH = auto()
    ANPR_MISMATCH = auto()
    ANPR_STATUS_2 = auto()
    MANUAL_OK = auto()
    UPDATE_STATUS_0 = auto()
    UPDATE_STATUS_1 = auto()
    UPDATE_STATUS_2 = auto()
    DETAILS_OK = auto()
    DETAILS_FAIL = auto()
    POSITIONING_TIMEOUT = auto()
    WEIGHT_TIMEOUT = auto()
    RFID_TIMEOUT = auto()
    EXIT_TIMEOUT = auto()
    RESET = auto()
    ERROR_OCCURRED = auto()
    FREE_PASS = auto()


class TIMEOUTS:
    """Timeouts in seconds."""

    POSITIONING_SEC = 120.0
    WEIGHT_CAPTURE_SEC = 60.0
    RFID_COLLECT_WINDOW_SEC = 5.0
    RFID_ERROR_DISPLAY_SEC = 10.0
    MANUAL_UPDATE_POLL_SEC = 5.0
    UPDATE_STATUS_2_RESET_SEC = 10.0
    EXIT_WAIT_SEC = 120.0
    # Vehicle cleared the lane - keep the boom up this long before closing
    BOOM_CLOSE_DELAY_SEC = 10.0
    OCI_REQUEST_TIMEOUT_SEC = 15.0
    DIGITIZER_TIMEOUT_SEC = 30.0
    SENSOR_POLL_SEC = 0.3
    MIN_WEIGHT_KG = 5000.0  # 5 ton gate before RFID
    ANPR_ERR_2_DISPLAY_SEC = 5.0
    WEIGHT_ERROR_DISPLAY_SEC = 5.0
    WEIGHT_CONFIRM_POLL_SEC = 5.0


MOVE_FORWARD_INTERVAL_SEC = 5.0

MSG_MOVE_FORWARD = "MOVE FORWARD"
MSG_WEIGHING = "WEIGHING"
MSG_RFID_ERR = "RFID ERR"
MSG_ANPR_ERR = "ANPR ERR 1"
MSG_ANPR_ERR_2 = "ANPR Err-2"
MSG_EXIT = "EXIT GRANTED"
MSG_FREE_PASS = "FREE PASS"
MSG_TARE_WT_ERR = "TARE WT ERR"
MSG_VADAGHAT_WT_ERR = "VADAGHAT WT ERR"
MSG_GROSS_WT_ERR = "GROSS WT ERR"
