"""
GMDC Mines Checkpoint - IoT checkpoint backend.

Flow (PDF):
  RFID read → OCI validate → ANPR → manual truck update loop →
  grant entry (TL green, boom open) → entry sensor → reset

Hardware (iot_configuration / modbus_tcp_app):
  Modbus TCP 192.168.31.89:502 slave=1, read_fc=2 DI 0/8, write_fc=5 DO 0/8
  DO0/1 entry traffic light, DO2/3 entry boom, DI0 entry sensor
"""

from __future__ import annotations

# "auto" follows the OS. "macos" forces liquid glass. "windows" forces the earlier UI.
OS_TYPE = "auto"

import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.server import start_api_server, start_rfid_api_ports
from config.constants import State
from config.settings import load_lane_settings, load_settings
from core.app_context import AppContext, LaneTable
from core.state_machine import StateMachine
from core.transaction import TransactionStore
from core.workflow import CheckpointWorkflow
from hardware.boom_barrier import BoomBarrier
from hardware.io_controller import create_io_controller
from hardware.rfid_reader import create_rfid_reader
from hardware.sensor import SensorPoller
from hardware.traffic_light import TrafficLight
from services.display_service import create_display_service
from services.frontend_mqtt import FrontendMqtt
from services.oci_client import OCIClient
from services.rfid_control import build_rfid_cloud_control
from utils.logging_setup import setup_logging

logger = logging.getLogger("mines_checkpoint.main")


def _ensure_local_mqtt_broker() -> None:
    """Install/start Mosquitto if 1883 (MQTT) or 9001 (WS) is not listening."""
    try:
        if getattr(sys, "frozen", False):
            roots = [Path(sys.executable).resolve().parent]
        else:
            roots = [Path(__file__).resolve().parent.parent]
            roots.append(roots[0].parent)
        for root in roots:
            for path in (str(root / "mqtt_broker_setup"), str(root)):
                if path not in sys.path:
                    sys.path.insert(0, path)
        from mqtt_broker_setup import bootstrap_local_mqtt

        bootstrap_local_mqtt(__file__)
    except Exception as exc:
        logger.exception("MQTT broker ensure failed: %s", exc)


def _pin(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _build_hardware(ctx: AppContext) -> None:
    settings = ctx.settings
    assert settings
    io_cfg = settings.io_config()
    demo = settings.demo_mode

    ctx.io = create_io_controller(io_cfg, demo_mode=demo)
    if not ctx.io.connect():
        logger.error("I/O controller failed to connect (continuing)")

    do_start = int(io_cfg.get("digital_outputs", {}).get("start_address") or 0)

    tl_cfg = (
        io_cfg.get("traffic_lights", {})
        .get("direct", {})
        .get("entry_a", {})
        .get("entry", {})
    )
    # Absolute DO addresses = do_start + configured pin offset
    red_pin = _pin(tl_cfg.get("red_pin"))
    green_pin = _pin(tl_cfg.get("green_pin"))
    ctx.traffic_light = TrafficLight(
        ctx.io,
        red_pin=(do_start + red_pin) if red_pin is not None else None,
        green_pin=(do_start + green_pin) if green_pin is not None else None,
        name="entry",
    )

    boom_cfg = io_cfg.get("boom_barriers", {}).get("direct", {}).get("entry", {})
    open_pin = _pin(boom_cfg.get("open_pin"))
    close_pin = _pin(boom_cfg.get("close_pin"))
    ctx.boom_barrier = BoomBarrier(
        ctx.io,
        open_pin=(do_start + open_pin) if open_pin is not None else None,
        close_pin=(do_start + close_pin) if close_pin is not None else None,
        enabled=bool(boom_cfg.get("enabled", True)),
        name="entry",
    )

    sensors = io_cfg.get("sensors", {})
    di_cfg = io_cfg.get("digital_inputs", {}) or {}
    di_start = int(di_cfg.get("start_address") or 0)
    poll = float(io_cfg.get("polling", {}).get("scan_interval") or 0.3)

    entry_cfg = sensors.get("entry_sensor", {}) or {}
    exit_cfg = sensors.get("exit_sensor", {}) or {}
    entry_enabled = bool(entry_cfg.get("enabled", True))
    exit_enabled = bool(exit_cfg.get("enabled", False))
    entry_pin = _pin(entry_cfg.get("pin")) if entry_enabled else None
    exit_pin = _pin(exit_cfg.get("pin")) if exit_enabled else None

    default_sig = (entry_cfg.get("default_signal") or "low").lower()
    # default_signal=low means idle is low; rising edge (active high) = vehicle present
    active_high = default_sig == "low"

    def on_vehicle_crossed():
        """
        Entry sensor cleared (TRUE→FALSE after occupied) while boom is open
        → close boom, TL red, return to IDLE.
        """
        if ctx.workflow:
            ctx.workflow.on_exit_sensor()

    ctx.sensor_poller = SensorPoller(
        ctx.io,
        entry_pin=entry_pin,
        exit_pin=exit_pin,
        di_start_address=di_start,
        poll_interval=poll,
        active_high=active_high,
        on_entry=on_vehicle_crossed if entry_pin is not None else None,
        on_exit=on_vehicle_crossed if exit_pin is not None else None,
    )
    logger.info(
        "Hardware mapped: TL red/green DO=%s/%s boom open/close DO=%s/%s "
        "entry_sensor DI=%s (di_start=%s do_start=%s demo=%s)",
        (do_start + red_pin) if red_pin is not None else None,
        (do_start + green_pin) if green_pin is not None else None,
        (do_start + open_pin) if open_pin is not None else None,
        (do_start + close_pin) if close_pin is not None else None,
        (di_start + entry_pin) if entry_pin is not None else None,
        di_start,
        do_start,
        demo,
    )

    def on_tags(id_hexes: List[str], raw: List[dict]) -> None:
        if ctx.workflow:
            ctx.workflow.on_rfid_tags(id_hexes, raw)

    rfid_cfg = settings.rfid_config("entry_a")
    ctx.rfid_reader = create_rfid_reader(
        rfid_cfg, demo_mode=demo, on_tags=on_tags
    )
    ctx.rfid_reader.start()
    # Cloud stop/start uses reader IP (e.g. https://192.168.63.87/cloud/stop)
    ctx.rfid_cloud = build_rfid_cloud_control(rfid_cfg, enabled=True)


def _activate_lane(ctx: AppContext) -> None:
    """Start one location: its own trip, Modbus link, display, and RFID reader."""
    settings = ctx.settings
    assert settings
    lane = settings.lane_id or "checkpoint"
    ctx.state_machine = StateMachine()
    ctx.transactions = TransactionStore()

    ctx.oci = OCIClient(
        base_url=settings.oci_base_url,
        username=settings.oci_username,
        password=settings.oci_password,
        rfid_validate_url=settings.rfid_validate_url,
        anpr_detect_url=settings.anpr_detect_url,
        invalid_truck_url=settings.invalid_truck_url,
        update_truck_url=settings.update_truck_url,
        boom_close_url=settings.boom_close_url,
        reset_checkpoint_url=settings.reset_checkpoint_url,
        download_docs_url=settings.download_docs_url,
        boom_close_style=settings.boom_close_style,
        anpr_username=settings.anpr_username,
        anpr_password=settings.anpr_password,
        endpoint_auth=settings.endpoint_auth,
        debug_wait_sec=(
            settings.api_wait_after_response if settings.api_debug else 0.0
        ),
    )
    if settings.api_debug and settings.api_wait_after_response > 0:
        logger.info(
            "API_DEBUG on - pause %ss after each GMDC API response (not ANPR)",
            settings.api_wait_after_response,
        )

    ctx.display = create_display_service(
        display_type=settings.display_type,
        broker=settings.mqtt_broker or "127.0.0.1",
        port=settings.mqtt_port,
        topic_tx=settings.mqtt_topic_tx or "data_info/a",
        display_ips=getattr(settings, "display_ips", None) or [],
        pcb_mode=getattr(settings, "display_pcb_mode", None) or "a",
        is_bidirectional=False,
        demo_fallback=True,
        client_id=f"mines_checkpoint_display-{lane}-{os.getpid()}",
    )
    # MQTT path publishes "Welcome" on first broker connect; console needs explicit send
    if ctx.display and getattr(ctx.display, "get_status", None):
        st = ctx.display.get_status() or {}
        if st.get("type") == "console":
            ctx.display.send("Welcome")

    _build_hardware(ctx)

    ctx.workflow = CheckpointWorkflow(ctx)
    ctx.workflow.apply_idle_hardware()

    fe_broker = settings.mqtt_broker or "127.0.0.1"
    fe_port = int(settings.mqtt_port or 1883)
    if fe_port in (80, 8000, 8080, 8800):
        logger.warning(
            "display.port=%s looks like HTTP - frontend MQTT using 1883",
            fe_port,
        )
        fe_port = 1883
    import services.frontend_mqtt as frontend_mqtt_mod
    from config.constants import MSG_IDLE

    frontend_mqtt_mod.IDLE_DISPLAY = MSG_IDLE
    ctx.frontend = FrontendMqtt(
        broker=fe_broker,
        port=fe_port,
        client_id=f"mines_checkpoint_frontend-{lane}-{os.getpid()}",
        instance_key=settings.lane_id,
        ctx=ctx,
    )
    ctx.frontend.display = MSG_IDLE
    ctx.frontend.register_reset_handler(
        lambda: ctx.workflow.force_reset() if ctx.workflow else None
    )
    ctx.frontend.register_free_pass_handler(
        lambda: ctx.workflow.start_free_pass() if ctx.workflow else None
    )
    ctx.frontend.register_status_request_handler(ctx.frontend.republish_snapshot)
    ctx.frontend.connect()
    ctx.frontend.start_device_monitor(interval_sec=0.4)

    # Start sensors after workflow + MQTT exist so an already-cut S1 is
    # published to the dashboard.
    if ctx.sensor_poller:
        ctx.sensor_poller.start()

    # IDLE RFID: login -> mode -> start
    ctx.workflow.prepare_rfid_for_idle()
    ctx.workflow.notify_gmdc_reset()
    if ctx.frontend:
        ctx.frontend.publish_device_status()
        ctx.frontend.republish_snapshot()

    logger.info(
        "Lane ready id=%s name=%s rfid_port=%s display=%s modbus=%s state=%s",
        lane,
        settings.display_name,
        settings.rfid_listen_port or settings.api_port,
        settings.mqtt_topic_tx,
        (settings.io_config().get("connection") or {})
        .get("ethernet", {})
        .get("ip"),
        ctx.state_machine.current_state.name if ctx.state_machine else "?",
    )


def _reader_ip(settings) -> str:
    block = settings.rfid_config("entry_a") if settings else {}
    if isinstance(block, dict):
        return str(block.get("ip") or "").strip()
    return ""


def bootstrap() -> AppContext:
    setup_logging()
    _ensure_local_mqtt_broker()
    first = load_settings()
    lanes = (
        load_lane_settings(Path(first.config_path))
        if first.config_path
        else [first]
    )
    AppContext.reset_instance()
    host = AppContext.get_instance()
    if len(lanes) <= 1 and not (lanes[0].lane_id if lanes else ""):
        host.settings = lanes[0] if lanes else load_settings()
        _activate_lane(host)
        return host

    table = LaneTable()
    host.lane_table = table
    host.lanes = []
    seen_modbus: Dict[str, str] = {}
    seen_display: Dict[str, str] = {}
    for settings in lanes:
        ctx = AppContext()
        ctx.settings = settings
        _activate_lane(ctx)
        lane_id = settings.lane_id or settings.display_name
        table.add(
            lane_id,
            ctx,
            int(settings.rfid_listen_port or 0),
            _reader_ip(settings),
        )
        host.lanes.append(ctx)
        modbus_ip = str(
            ((settings.io_config().get("connection") or {}).get("ethernet") or {}).get(
                "ip"
            )
            or ""
        )
        if modbus_ip and modbus_ip in seen_modbus:
            logger.warning(
                "Lane %s and %s share Modbus %s",
                seen_modbus[modbus_ip],
                lane_id,
                modbus_ip,
            )
        elif modbus_ip:
            seen_modbus[modbus_ip] = lane_id
        topic = settings.mqtt_topic_tx or ""
        if topic and topic in seen_display:
            logger.warning(
                "Lane %s and %s share display topic %s",
                seen_display[topic],
                lane_id,
                topic,
            )
        elif topic:
            seen_display[topic] = lane_id
    host.settings = lanes[0]
    logger.info("Mines Checkpoint running %s lanes in one process", len(host.lanes))
    return host


def main() -> int:
    ctx = bootstrap()
    settings = ctx.settings
    assert settings

    app = start_api_server(host=settings.api_host, port=settings.api_port, os_type=OS_TYPE)
    rfid_ports = list(settings.rfid_api_listen_ports())
    lane_lines = []
    for lane_ctx in getattr(ctx, "lanes", None) or []:
        lane_settings = lane_ctx.settings
        if not lane_settings:
            continue
        port = int(lane_settings.rfid_listen_port or 0)
        if port and port != settings.api_port and port not in rfid_ports:
            rfid_ports.append(port)
        lane_lines.append(
            f"  {lane_settings.display_name:<12} RFID :{port or settings.api_port}"
            f"  reader { _reader_ip(lane_settings) or '-'}"
            f"  display {lane_settings.mqtt_topic_tx}"
        )
    start_rfid_api_ports(app, settings.api_host, rfid_ports)
    banner = (
        "\n"
        "============================================================\n"
        "  GMDC Mines Checkpoint running\n"
        f"  Locations  : {len(getattr(ctx, 'lanes', None) or [ctx])}\n"
        f"  Dashboard  : http://127.0.0.1:{settings.api_port}/\n"
        f"  API        : http://127.0.0.1:{settings.api_port}/api/lanes\n"
        + ("\n".join(lane_lines) + "\n" if lane_lines else "")
        + f"  MQTT TCP   : {settings.mqtt_broker}:{settings.mqtt_port}\n"
        "  Point each RFID reader at its own port above.\n"
        "============================================================\n"
    )
    print(banner, flush=True)
    logger.info(
        "API listening on http://%s:%s  (POST /rfid_data, POST /rfid_data_from_mobile_app, GET /api/status)",
        settings.api_host,
        settings.api_port,
    )

    stop = False

    def _signal_handler(signum, frame):
        nonlocal stop
        logger.info("Signal %s - shutting down", signum)
        stop = True

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while not stop:
            time.sleep(0.5)
    finally:
        logger.info("Shutting down...")
        running = list(getattr(ctx, "lanes", None) or [ctx])
        for lane_ctx in running:
            if lane_ctx.sensor_poller:
                lane_ctx.sensor_poller.stop()
            if lane_ctx.rfid_reader:
                lane_ctx.rfid_reader.stop()
            if lane_ctx.frontend:
                try:
                    lane_ctx.frontend.disconnect()
                except Exception:
                    pass
            if lane_ctx.display:
                lane_ctx.display.disconnect()
            if lane_ctx.io:
                lane_ctx.io.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
