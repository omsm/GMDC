"""Application context singleton."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config.settings import Settings
    from core.state_machine import StateMachine
    from core.transaction import TransactionStore
    from core.workflow import CheckpointWorkflow
    from hardware.boom_barrier import BoomBarrier
    from hardware.io_controller import IOController
    from hardware.rfid_reader import RFIDReader
    from hardware.sensor import SensorPoller
    from hardware.traffic_light import TrafficLight
    from services.display_service import DisplayService
    from services.frontend_mqtt import FrontendMqtt
    from services.oci_client import OCIClient
    from services.rfid_control import RFIDCloudControl

logger = logging.getLogger("mines_checkpoint.core.app_context")


class LaneTable:
    """Four locations running inside one process.

    A tag is routed by the HTTP port the reader posts to, then by an explicit
    lane id, then by the reader IP when that IP belongs to only one lane.
    """

    def __init__(self) -> None:
        self.order: list[str] = []
        self.by_id: dict[str, "AppContext"] = {}
        self.by_port: dict[int, str] = {}
        self.by_reader_ip: dict[str, str] = {}
        self._ambiguous_ips: set[str] = set()

    def add(self, lane_id: str, ctx: "AppContext", port: int, reader_ip: str) -> None:
        self.order.append(lane_id)
        self.by_id[lane_id] = ctx
        if port:
            self.by_port[int(port)] = lane_id
        ip = str(reader_ip or "").strip()
        if not ip or ip in self._ambiguous_ips:
            return
        previous = self.by_reader_ip.get(ip)
        if previous and previous != lane_id:
            self.by_reader_ip.pop(ip, None)
            self._ambiguous_ips.add(ip)
            return
        self.by_reader_ip[ip] = lane_id

    def resolve(self, port: int = 0, lane: str = "", remote_ip: str = "") -> Optional["AppContext"]:
        name = str(lane or "").strip()
        if name and name in self.by_id:
            return self.by_id[name]
        try:
            listen = int(port or 0)
        except (TypeError, ValueError):
            listen = 0
        if listen and listen in self.by_port:
            return self.by_id[self.by_port[listen]]
        ip = str(remote_ip or "").strip()
        if ip and ip in self.by_reader_ip:
            return self.by_id[self.by_reader_ip[ip]]
        if self.order:
            return self.by_id[self.order[0]]
        return None


def active_context() -> "AppContext":
    """Lane for this HTTP request, or the single running context."""
    host = AppContext.get_instance()
    table = getattr(host, "lane_table", None)
    if not isinstance(table, LaneTable) or not table.by_id:
        return host
    port = 0
    lane = ""
    remote_ip = ""
    try:
        from flask import has_request_context, request

        if has_request_context():
            port = int(request.environ.get("SERVER_PORT") or 0)
            view = request.view_args or {}
            lane = str(
                view.get("lane_id")
                or request.args.get("lane")
                or request.headers.get("X-Lane")
                or ""
            )
            remote_ip = str(request.remote_addr or "")
    except Exception:
        pass
    chosen = table.resolve(port=port, lane=lane, remote_ip=remote_ip)
    return chosen or host


class AppContext:
    _instance: Optional["AppContext"] = None

    def __init__(self):
        self.settings: Optional["Settings"] = None
        self.state_machine: Optional["StateMachine"] = None
        self.transactions: Optional["TransactionStore"] = None
        self.workflow: Optional["CheckpointWorkflow"] = None
        self.io: Optional["IOController"] = None
        self.traffic_light: Optional["TrafficLight"] = None
        self.boom_barrier: Optional["BoomBarrier"] = None
        self.sensor_poller: Optional["SensorPoller"] = None
        self.rfid_reader: Optional["RFIDReader"] = None
        self.rfid_cloud: Optional["RFIDCloudControl"] = None
        self.oci: Optional["OCIClient"] = None
        self.display: Optional["DisplayService"] = None
        self.frontend: Optional["FrontendMqtt"] = None
        self.lane_table: Optional[LaneTable] = None

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
        settings = self.settings
        return {
            "state": sm.current_state.name if sm else "UNKNOWN",
            "state_duration_sec": sm.state_duration_seconds if sm else 0,
            "transaction": self.transactions.to_dict() if self.transactions else {},
            "demo_mode": bool(settings and settings.demo_mode),
            "checkpoint_type": getattr(settings, "checkpoint_type", "") if settings else "",
            "lane_id": getattr(settings, "lane_id", "") if settings else "",
            "display_name": getattr(settings, "display_name", "") if settings else "",
            "rfid_listen_port": getattr(settings, "rfid_listen_port", 0) if settings else 0,
            "logo_initials": getattr(settings, "logo_initials", "") if settings else "",
            "anpr_enabled": bool(getattr(settings, "anpr_enabled", True)) if settings else True,
            "service": getattr(settings, "service_name", "GMDC Mines Checkpoint")
            if settings
            else "GMDC Mines Checkpoint",
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
