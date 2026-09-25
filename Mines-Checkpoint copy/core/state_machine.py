"""Thread-safe state machine for Mines Entry (wraps shared BaseStateMachine)."""

from __future__ import annotations

from typing import Callable, Dict

from config.constants import Event, State
from gmdc_common.core.state_machine import BaseStateMachine

StateAction = Callable[[], None]


class StateMachine(BaseStateMachine):
    """Valid transitions for Mines Entry PDF workflow."""

    TRANSITIONS: Dict = {
        (State.IDLE, Event.RFID_RECEIVED): State.RFID_READ,
        (State.IDLE, Event.RESET): State.IDLE,
        (State.IDLE, Event.FREE_PASS): State.FREE_PASS,
        (State.IDLE, Event.ERROR_OCCURRED): State.ERROR,
        (State.RFID_READ, Event.RFID_RECEIVED): State.RFID_VALIDATE,
        (State.RFID_READ, Event.RESET): State.IDLE,
        (State.RFID_VALIDATE, Event.RFID_VALID): State.DISPLAY_TRUCK,
        (State.RFID_VALIDATE, Event.RFID_INVALID): State.RFID_ERROR,
        (State.RFID_VALIDATE, Event.RESET): State.IDLE,
        (State.RFID_ERROR, Event.RFID_ERROR_TIMEOUT): State.IDLE,
        (State.RFID_ERROR, Event.RESET): State.IDLE,
        (State.DISPLAY_TRUCK, Event.ANPR_MATCH): State.ENTRY_GRANTED,
        (State.DISPLAY_TRUCK, Event.ANPR_MISMATCH): State.MANUAL_UPDATE,
        (State.DISPLAY_TRUCK, Event.RESET): State.IDLE,
        (State.ANPR_VALIDATE, Event.ANPR_MATCH): State.ENTRY_GRANTED,
        (State.ANPR_VALIDATE, Event.ANPR_MISMATCH): State.MANUAL_UPDATE,
        (State.ANPR_VALIDATE, Event.RESET): State.IDLE,
        (State.MANUAL_UPDATE, Event.UPDATE_STATUS_1): State.ENTRY_GRANTED,
        (State.MANUAL_UPDATE, Event.UPDATE_STATUS_0): State.MANUAL_UPDATE,
        (State.MANUAL_UPDATE, Event.UPDATE_STATUS_2): State.IDLE,
        (State.MANUAL_UPDATE, Event.STATUS_2_TIMEOUT): State.IDLE,
        (State.MANUAL_UPDATE, Event.ANPR_MATCH): State.ENTRY_GRANTED,
        (State.MANUAL_UPDATE, Event.RESET): State.IDLE,
        (State.ENTRY_GRANTED, Event.ENTRY_OPENED): State.WAIT_CROSSING,
        (State.ENTRY_GRANTED, Event.EXIT_SENSOR): State.IDLE,
        (State.ENTRY_GRANTED, Event.CROSSING_TIMEOUT): State.IDLE,
        (State.ENTRY_GRANTED, Event.RESET): State.IDLE,
        (State.WAIT_CROSSING, Event.EXIT_SENSOR): State.IDLE,
        (State.WAIT_CROSSING, Event.CROSSING_TIMEOUT): State.IDLE,
        (State.WAIT_CROSSING, Event.RESET): State.IDLE,
        (State.FREE_PASS, Event.EXIT_SENSOR): State.IDLE,
        (State.FREE_PASS, Event.RESET): State.IDLE,
        (State.ERROR, Event.RESET): State.IDLE,
    }

    def __init__(self):
        super().__init__(
            initial_state=State.IDLE,
            transitions=self.TRANSITIONS,
            logger_name="mines_checkpoint.core.state_machine",
        )
