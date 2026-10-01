"""Thread-safe, table-driven state machine used by all GMDC apps."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Tuple, TypeVar

logger = logging.getLogger("gmdc_common.core.state_machine")

StateT = TypeVar("StateT", bound=Enum)
EventT = TypeVar("EventT", bound=Enum)

StateAction = Callable[[], None]


class BaseStateMachine:
    """
    Generic FSM. Apps subclass (or wrap) this and supply their own
    State / Event enums plus a TRANSITIONS table.
    """

    def __init__(
        self,
        *,
        initial_state: Enum,
        transitions: Dict[Tuple[Enum, Enum], Enum],
        max_history: int = 50,
        logger_name: Optional[str] = None,
    ):
        self.TRANSITIONS = dict(transitions)
        self._state = initial_state
        self._lock = threading.RLock()
        self._entry_actions: Dict[Enum, StateAction] = {}
        self._exit_actions: Dict[Enum, StateAction] = {}
        self._state_history: list = []
        self._max_history = max_history
        self._state_entered_at: datetime = datetime.now()
        self._log = (
            logging.getLogger(logger_name)
            if logger_name
            else logger
        )

    @property
    def current_state(self) -> Enum:
        with self._lock:
            return self._state

    @property
    def state_duration_seconds(self) -> float:
        with self._lock:
            return (datetime.now() - self._state_entered_at).total_seconds()

    def on_enter(self, state: Enum, action: StateAction) -> None:
        self._entry_actions[state] = action

    def on_exit(self, state: Enum, action: StateAction) -> None:
        self._exit_actions[state] = action

    def can_transition(self, event: Enum) -> bool:
        with self._lock:
            return (self._state, event) in self.TRANSITIONS

    def trigger(self, event: Enum) -> bool:
        with self._lock:
            key = (self._state, event)
            if key not in self.TRANSITIONS:
                self._log.debug(
                    "Ignored event %s in state %s",
                    getattr(event, "name", event),
                    getattr(self._state, "name", self._state),
                )
                return False

            old = self._state
            new = self.TRANSITIONS[key]

            exit_action = self._exit_actions.get(old)
            if exit_action and old != new:
                try:
                    exit_action()
                except Exception as e:
                    self._log.exception(
                        "Exit action %s failed: %s",
                        getattr(old, "name", old),
                        e,
                    )

            self._state = new
            self._state_entered_at = datetime.now()
            self._state_history.append(
                {
                    "from": getattr(old, "name", str(old)),
                    "to": getattr(new, "name", str(new)),
                    "event": getattr(event, "name", str(event)),
                    "at": self._state_entered_at.isoformat(),
                }
            )
            if len(self._state_history) > self._max_history:
                self._state_history = self._state_history[-self._max_history :]

            self._log.info(
                "FSM %s --[%s]--> %s",
                getattr(old, "name", old),
                getattr(event, "name", event),
                getattr(new, "name", new),
            )

            if old != new:
                entry_action = self._entry_actions.get(new)
                if entry_action:
                    try:
                        entry_action()
                    except Exception as e:
                        self._log.exception(
                            "Entry action %s failed: %s",
                            getattr(new, "name", new),
                            e,
                        )
            return True

    def force_state(self, state: Enum) -> None:
        with self._lock:
            self._log.warning(
                "Force state %s -> %s",
                getattr(self._state, "name", self._state),
                getattr(state, "name", state),
            )
            self._state = state
            self._state_entered_at = datetime.now()

    def history(self) -> list:
        with self._lock:
            return list(self._state_history)
