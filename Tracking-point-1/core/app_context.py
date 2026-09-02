"""Application context singleton."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config.settings import Settings
    from core.state_machine import StateMachine
    from core.transaction import TransactionStore
    from core.workflow import TrackingPointWorkflow
    from hardware.boom_barrier import BoomBarrier
    from hardware.io_controller import IOController
    from hardware.rfid_reader import RFIDReader
    from hardware.sensor import SensorPoller
    from hardware.traffic_light import TrafficLight
    from services.display_service import DisplayService
    from services.frontend_mqtt import FrontendMqtt
    from services.oci_client import OCIClient
    from services.rfid_control import RFIDCloudControl

logger = logging.getLogger("tracking_point.core.app_context")


class AppContext:
    _instance: Optional["AppContext"] = None

    def __init__(self):
        self.settings: Optional["Settings"] = None
        self.state_machine: Optional["StateMachine"] = None
        self.transactions: Optional["TransactionStore"] = None
        self.workflow: Optional["TrackingPointWorkflow"] = None
        self.io: Optional["IOController"] = None
        self.traffic_light: Optional["TrafficLight"] = None
        self.boom_barrier: Optional["BoomBarrier"] = None
        self.sensor_poller: Optional["SensorPoller"] = None
        self.rfid_reader: Optional["RFIDReader"] = None
        self.rfid_cloud: Optional["RFIDCloudControl"] = None
        self.oci: Optional["OCIClient"] = None
        self.display: Optional["DisplayService"] = None
        self.frontend: Optional["FrontendMqtt"] = None

    @classmethod
    def get_instance(cls) -> "AppContext":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def status_snapshot(self) -> dict:
        sm = self.state_machine
        return {
            "state": sm.current_state.name if sm else "UNKNOWN",
            "state_duration_sec": sm.state_duration_seconds if sm else 0,
            "transaction": self.transactions.to_dict() if self.transactions else {},
            "demo_mode": bool(self.settings and self.settings.demo_mode),
            "hardware": {
                "io": self.io.get_status() if self.io else None,
                "traffic_light": self.traffic_light.get_status()
                if self.traffic_light
                else None,
                "boom_barrier": self.boom_barrier.get_status()
                if self.boom_barrier
                else None,
                "sensors": self.sensor_poller.get_status()
                if self.sensor_poller
                else None,
                "rfid": self.rfid_reader.get_status()
                if self.rfid_reader
                else None,
            },
            "display": self.display.get_status() if self.display else None,
            "history": sm.history() if sm else [],
        }
