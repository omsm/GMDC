"""Application context singleton for Mines WB."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from config.settings import Settings
    from core.state_machine import StateMachine
    from core.transaction import TransactionStore
    from core.workflow import MinesWbWorkflow
    from gmdc_common.hardware.boom_barrier import BoomBarrier
    from gmdc_common.hardware.io_controller import IOController
    from gmdc_common.hardware.rfid_reader import RFIDReader
    from gmdc_common.hardware.sensor import SensorPoller
    from gmdc_common.hardware.traffic_light import TrafficLight
    from gmdc_common.services.display_service import DisplayService
    from gmdc_common.services.rfid_control import RFIDCloudControl
    from gmdc_common.services.voice_service import VoiceService
    from services.digitizer_client import DigitizerClient
    from services.frontend_mqtt import FrontendMqtt
    from services.oci_client import OCIClient

logger = logging.getLogger("mines_wb.core.app_context")


class AppContext:
    _instance: Optional["AppContext"] = None

    def __init__(self):
        self.settings: Optional["Settings"] = None
        self.state_machine: Optional["StateMachine"] = None
        self.transactions: Optional["TransactionStore"] = None
        self.workflow: Optional["MinesWbWorkflow"] = None
        self.io: Optional["IOController"] = None
        self.entry_tl: Optional["TrafficLight"] = None
        self.exit_tl: Optional["TrafficLight"] = None
        # Bidirectional: {"entry_a"|"entry_b": {"entry": TrafficLight, "exit": TrafficLight}}
        self.traffic_lights: Dict[str, Dict[str, "TrafficLight"]] = {}
        self.entry_boom: Optional["BoomBarrier"] = None
        self.exit_boom: Optional["BoomBarrier"] = None
        self.sensor_poller: Optional["SensorPoller"] = None
        self.rfid_reader: Optional["RFIDReader"] = None
        self.rfid_cloud: Optional["RFIDCloudControl"] = None
        self.rfid_clouds: Dict[str, "RFIDCloudControl"] = {}
        self.active_rfid_direction: str = ""
        self.oci: Optional["OCIClient"] = None
        self.display: Optional["DisplayService"] = None
        self.digitizer: Optional["DigitizerClient"] = None
        self.voice: Optional["VoiceService"] = None
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
            "service": "GMDC Mines Weighbridge",
            "state": sm.current_state.name if sm else "UNKNOWN",
            "state_duration_sec": sm.state_duration_seconds if sm else 0,
            "transaction": self.transactions.to_dict() if self.transactions else {},
            "demo_mode": bool(self.settings and self.settings.demo_mode),
            "checkpoint_type": getattr(self.settings, "checkpoint_type", None),
            "display_name": getattr(self.settings, "display_name", None),
            "logo_initials": getattr(self.settings, "logo_initials", None),
            "anpr_enabled": bool(getattr(self.settings, "anpr_enabled", True)),
            "wb_type": getattr(self.settings, "wb_type", None),
            "config_path": getattr(self.settings, "config_path", None),
            "digitizer": getattr(self.settings, "digitizer_label", None)
            or getattr(self.settings, "digitizer_url", None),
            "digitizer_mode": getattr(self.settings, "digitizer_mode", None),
            "active_rfid_direction": self.active_rfid_direction or None,
            "hardware": {
                "io": self.io.get_status() if self.io else None,
                "entry_tl": self.entry_tl.get_status() if self.entry_tl else None,
                "exit_tl": self.exit_tl.get_status() if self.exit_tl else None,
                "entry_boom": self.entry_boom.get_status() if self.entry_boom else None,
                "exit_boom": self.exit_boom.get_status() if self.exit_boom else None,
                "sensors": self.sensor_poller.get_status()
                if self.sensor_poller
                else None,
                "rfid": self.rfid_reader.get_status() if self.rfid_reader else None,
            },
            "display": self.display.get_status() if self.display else None,
            "voice": self.voice.get_status() if self.voice else None,
            "history": sm.history() if sm else [],
        }
