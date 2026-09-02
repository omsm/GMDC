"""Tare WB state machine (wraps gmdc_common BaseStateMachine)."""

from __future__ import annotations

from typing import Dict

from config.constants import Event, State
from gmdc_common.core.state_machine import BaseStateMachine


class StateMachine(BaseStateMachine):
    """Valid transitions for tare weighbridge flow (wb_plane.txt)."""

    TRANSITIONS: Dict = {
        (State.IDLE, Event.ENTRY_SENSOR): State.VEHICLE_POSITIONING,
        (State.IDLE, Event.RESET): State.IDLE,
        (State.IDLE, Event.ERROR_OCCURRED): State.ERROR,
        (State.IDLE, Event.FREE_PASS): State.FREE_PASS,
        (State.VEHICLE_POSITIONING, Event.WB_SENSOR): State.WEIGHT_CAPTURE,
        (State.VEHICLE_POSITIONING, Event.POSITIONING_TIMEOUT): State.IDLE,
        (State.VEHICLE_POSITIONING, Event.RESET): State.IDLE,
        (State.WEIGHT_CAPTURE, Event.WEIGHT_OK): State.RFID_READ,
        (State.WEIGHT_CAPTURE, Event.WEIGHT_LOW): State.IDLE,
        (State.WEIGHT_CAPTURE, Event.WEIGHT_FAIL): State.ERROR,
        (State.WEIGHT_CAPTURE, Event.WEIGHT_TIMEOUT): State.IDLE,
        (State.WEIGHT_CAPTURE, Event.RESET): State.IDLE,
        (State.RFID_READ, Event.RFID_RECEIVED): State.RFID_VALIDATE,
        (State.RFID_READ, Event.RFID_TIMEOUT): State.RFID_ERROR,
        (State.RFID_READ, Event.RESET): State.IDLE,
        (State.RFID_VALIDATE, Event.RFID_VALID): State.ANPR_VALIDATE,
        (State.RFID_VALIDATE, Event.RFID_INVALID): State.RFID_ERROR,
        (State.RFID_VALIDATE, Event.RESET): State.IDLE,
        (State.RFID_ERROR, Event.RFID_ERROR_TIMEOUT): State.EXIT_GRANTED,
        (State.RFID_ERROR, Event.RESET): State.IDLE,
        (State.ANPR_VALIDATE, Event.ANPR_MATCH): State.FINAL_WEIGHT,
        (State.ANPR_VALIDATE, Event.ANPR_MISMATCH): State.MANUAL_UPDATE,
        (State.ANPR_VALIDATE, Event.RESET): State.IDLE,
        (State.MANUAL_UPDATE, Event.MANUAL_OK): State.FINAL_WEIGHT,
        (State.MANUAL_UPDATE, Event.UPDATE_STATUS_0): State.MANUAL_UPDATE,
        (State.MANUAL_UPDATE, Event.UPDATE_STATUS_1): State.FINAL_WEIGHT,
        (State.MANUAL_UPDATE, Event.UPDATE_STATUS_2): State.EXIT_GRANTED,
        (State.MANUAL_UPDATE, Event.RESET): State.IDLE,
        (State.FINAL_WEIGHT, Event.WEIGHT_OK): State.IMAGE_CAPTURE,
        (State.FINAL_WEIGHT, Event.WEIGHT_FAIL): State.ERROR,
        (State.FINAL_WEIGHT, Event.RESET): State.IDLE,
        (State.IMAGE_CAPTURE, Event.DETAILS_OK): State.WEIGHT_DETAILS,
        (State.IMAGE_CAPTURE, Event.DETAILS_FAIL): State.ERROR,
        (State.IMAGE_CAPTURE, Event.RESET): State.IDLE,
        (State.WEIGHT_DETAILS, Event.DETAILS_OK): State.EXIT_GRANTED,
        (State.WEIGHT_DETAILS, Event.DETAILS_FAIL): State.ERROR,
        (State.WEIGHT_DETAILS, Event.RESET): State.IDLE,
        (State.EXIT_GRANTED, Event.EXIT_SENSOR): State.IDLE,
        (State.EXIT_GRANTED, Event.EXIT_TIMEOUT): State.IDLE,
        (State.EXIT_GRANTED, Event.RESET): State.IDLE,
        (State.WAIT_EXIT, Event.EXIT_SENSOR): State.IDLE,
        (State.WAIT_EXIT, Event.EXIT_TIMEOUT): State.IDLE,
        (State.WAIT_EXIT, Event.RESET): State.IDLE,
        (State.ERROR, Event.RESET): State.IDLE,
        (State.ERROR, Event.EXIT_SENSOR): State.IDLE,
        (State.FREE_PASS, Event.EXIT_SENSOR): State.IDLE,
        (State.FREE_PASS, Event.RESET): State.IDLE,
    }

    def __init__(self):
        super().__init__(
            initial_state=State.IDLE,
            transitions=self.TRANSITIONS,
            logger_name="tare_wb.core.state_machine",
        )
