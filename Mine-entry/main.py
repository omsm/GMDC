"""
GMDC Mines Entry - IoT checkpoint backend.

Flow (PDF):
  RFID read → OCI validate → ANPR → manual truck update loop →
  grant entry (TL green, boom open) → entry sensor → reset

Hardware (iot_configuration / modbus_tcp_app):
  Modbus TCP 192.168.31.89:502 slave=1, read_fc=2 DI 0/8, write_fc=5 DO 0/8
  DO0/1 entry traffic light, DO2/3 entry boom, DI0 entry sensor
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Any, Dict, List, Optional

from api.server import start_api_server
from config.constants import State
from config.settings import load_settings
from core.app_context import AppContext
from core.state_machine import StateMachine
from core.transaction import TransactionStore
from core.workflow import MinesEntryWorkflow
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

logger = logging.getLogger("mine_entry.main")


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


def bootstrap() -> AppContext:
    setup_logging()
    settings = load_settings()
    AppContext.reset_instance()
    ctx = AppContext.get_instance()
    ctx.settings = settings
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
        anpr_username=settings.anpr_username,
        anpr_password=settings.anpr_password,
        endpoint_auth=settings.endpoint_auth,
    )

    ctx.display = create_display_service(
        display_type=settings.display_type,
        broker=settings.mqtt_broker,
        port=settings.mqtt_port,
        topic_tx=settings.mqtt_topic_tx,
        demo_fallback=True,
    )
    # create_display_service already connects MQTT when available

    _build_hardware(ctx)

    ctx.workflow = MinesEntryWorkflow(ctx)
    ctx.workflow.apply_idle_hardware()

    fe_broker = settings.mqtt_broker or "127.0.0.1"
    fe_port = int(settings.mqtt_port or 1883)
    if fe_port in (80, 8000, 8080, 8800):
        logger.warning(
            "display.port=%s looks like HTTP - frontend MQTT using 1883",
            fe_port,
        )
        fe_port = 1883
    ctx.frontend = FrontendMqtt(
        broker=fe_broker,
        port=fe_port,
        client_id="mine_entry_frontend",
        ctx=ctx,
    )
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
        "Mines Entry bootstrapped demo_mode=%s state=%s",
        settings.demo_mode,
        ctx.state_machine.current_state.name,
    )
    return ctx


def main() -> int:
    ctx = bootstrap()
    settings = ctx.settings
    assert settings

    start_api_server(host=settings.api_host, port=settings.api_port)
    banner = (
        "\n"
        "============================================================\n"
        "  GMDC Mines Entry running\n"
        f"  DEMO_MODE  : {settings.demo_mode}\n"
        f"  Dashboard  : http://127.0.0.1:{settings.api_port}/\n"
        f"  API        : http://127.0.0.1:{settings.api_port}/api/status\n"
        f"  MQTT WS    : ws://<this-pc-ip>:9001\n"
        f"  State      : {ctx.state_machine.current_state.name if ctx.state_machine else '?'}\n"
        "  Console idle here is normal - check the dashboard for live status.\n"
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
        if ctx.sensor_poller:
            ctx.sensor_poller.stop()
        if ctx.rfid_reader:
            ctx.rfid_reader.stop()
        if ctx.frontend:
            try:
                ctx.frontend.disconnect()
            except Exception:
                pass
        if ctx.display:
            ctx.display.disconnect()
        if ctx.io:
            ctx.io.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
