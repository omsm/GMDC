"""State, Event enums and timeouts for Mines Weighbridge FSM (wb_plane.txt)."""

from __future__ import annotations

import logging
import os
from enum import Enum, auto

logger = logging.getLogger("mines_wb.config.constants")


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
    """Timeouts in seconds (overridable via .env — see apply_timeouts_from_env)."""

    POSITIONING_SEC = 120.0
    WEIGHT_CAPTURE_SEC = 60.0
    # How long RFID_READ waits for the first tag after the reader starts.
    RFID_COLLECT_TIMEOUT_SEC = 60.0
    RFID_COLLECT_WINDOW_SEC = 5.0  # legacy alias; prefer RFID_COLLECT_TIMEOUT_SEC
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


# Back-compat alias (prefer TIMEOUTS.MOVE_FORWARD_INTERVAL_SEC).
MOVE_FORWARD_INTERVAL_SEC = TIMEOUTS.MOVE_FORWARD_INTERVAL_SEC

MSG_NO_RFID_READ = "No RFID read within the time period"

_TIMEOUT_ENV_ATTRS = (
    "POSITIONING_SEC",
    "WEIGHT_CAPTURE_SEC",
    "RFID_COLLECT_TIMEOUT_SEC",
    "RFID_COLLECT_WINDOW_SEC",
    "RFID_ERROR_DISPLAY_SEC",
    "MANUAL_UPDATE_POLL_SEC",
    "UPDATE_STATUS_2_RESET_SEC",
    "EXIT_WAIT_SEC",
    "BOOM_CLOSE_DELAY_SEC",
    "OCI_REQUEST_TIMEOUT_SEC",
    "DIGITIZER_TIMEOUT_SEC",
    "SENSOR_POLL_SEC",
    "MIN_WEIGHT_KG",
    "ANPR_ERR_2_DISPLAY_SEC",
    "WEIGHT_ERROR_DISPLAY_SEC",
    "WEIGHT_CONFIRM_POLL_SEC",
    "MOVE_FORWARD_INTERVAL_SEC",
)


def apply_timeouts_from_env() -> None:
    """Override TIMEOUTS from matching .env keys (after load_dotenv)."""
    global MOVE_FORWARD_INTERVAL_SEC
    for attr in _TIMEOUT_ENV_ATTRS:
        raw = os.getenv(attr)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            setattr(TIMEOUTS, attr, float(raw))
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid %s=%r", attr, raw)
    MOVE_FORWARD_INTERVAL_SEC = TIMEOUTS.MOVE_FORWARD_INTERVAL_SEC

MSG_IDLE = "   Enter@  Vehicle"
MSG_MOVE_FORWARD = "    MOVE@  FORWARD"
MSG_MOVE_BACKWARD = "  MOVE@  BACKWARD"
MSG_WEIGHING_FMT = "Weight@{weight}"
MSG_WEIGHING = " Checking@  Weight"
MSG_RFID_ERR = "RFID ERR@ASK OPERATOR"
# Tare (T): unladen; Vadaghat/Gross (V/G): laden — see Workflow._rfid_ok_display
MSG_RFID_OK_FMT = "{truck}@{weight} Kg"
MSG_ANPR_ERR = "ANPR ERROR@ERR-0"
MSG_ANPR_ERR_2 = "ANPR ERROR@ERR-2"
MSG_ANPR_API_ERR = "ANPR ERROR@ASK OPERATOR"
MSG_WEIGHT_DETAILS_FMT = "{truck} Weight@{weight} Kg"
MSG_EXIT = "   EXIT@  GRANTED"
MSG_FREE_PASS = "   FREE@  PASS"
MSG_TARE_WT_ERR = "TARE WT@  ERR"
MSG_VADAGHAT_WT_ERR = "VADAGHAT WT@  ERR"
MSG_GROSS_WT_ERR = "GROSS WT@  ERR"
