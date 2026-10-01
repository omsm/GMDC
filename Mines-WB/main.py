"""
GMDC Mines Weighbridge - IoT checkpoint backend.

Flow (wb_plane.txt):
  Entry sensor → positioning → WB sensor → weight (>5 t) → RFID →
  OCI validate → ANPR → (manual loop) → final weight + images →
  weight-details → exit grant → exit sensor → IDLE

Config: checkpoint-config/iot_configuration.json (or local override).
Hardware / display / RFID cloud: gmdc_common.
"""

from __future__ import annotations

# "auto" follows the OS. "macos" forces liquid glass. "windows" forces the earlier UI.
OS_TYPE = "auto"

import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.server import start_api_server, start_rfid_api_ports
from config.settings import load_settings
from core.app_context import AppContext
from core.state_machine import StateMachine
from core.transaction import TransactionStore
from core.workflow import MinesWbWorkflow
from hardware import (
    BoomBarrier,
    SensorPoller,
    TrafficLight,
    create_io_controller,
    create_rfid_reader,
)
from services.digitizer_client import create_digitizer_client
from services.display_service import ConsoleDisplayService, create_display_service
from services.frontend_mqtt import FrontendMqtt
from services.oci_client import OCIClient
from services.rfid_control import build_rfid_cloud_control
from services.voice_service import VoiceService
from utils.logging_setup import setup_logging

logger = logging.getLogger("mines_wb.main")


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


def _io_mode(section: Dict[str, Any]) -> str:
    return str(section.get("mode") or "direct").strip().lower()


def _resolve_tl_pins(
    io_cfg: Dict[str, Any],
    side: str,
    do_start: int,
    direction: Optional[str] = None,
) -> Tuple[Optional[int], Optional[int]]:
    """
    Resolve traffic-light DO addresses.
    relay mode: single pin as red_pin (HIGH=red, LOW=green per relay_logic).
    direct mode: red_pin + green_pin.
    Bidirectional pins live under entry_a / entry_b, each with entry and exit.
    """
    tl = io_cfg.get("traffic_lights") or {}
    if _io_mode(tl) == "relay":
        relay = tl.get("relay") or {}
        cfg: Dict[str, Any] = {}
        if direction:
            cfg = (relay.get(direction) or {}).get(side) or {}
        if not cfg:
            cfg = relay.get(side) or {}
        pin = _pin(cfg.get("pin"))
        if pin is None:
            return None, None
        return do_start + pin, None

    direct = tl.get("direct") or {}
    cfg = {}
    if direction:
        cfg = (direct.get(direction) or {}).get(side) or {}
    if not cfg:
        cfg = direct.get(side) or {}
    red = _pin(cfg.get("red_pin"))
    green = _pin(cfg.get("green_pin"))
    return (
        (do_start + red) if red is not None else None,
        (do_start + green) if green is not None else None,
    )


def _resolve_boom_pins(
    io_cfg: Dict[str, Any], side: str, do_start: int
) -> Tuple[Optional[int], Optional[int], bool]:
    """
    Resolve boom open/close DO addresses + enabled.
    relay mode: single pin as open_pin (HIGH=open, LOW=close).
    """
    bb = io_cfg.get("boom_barriers") or {}
    if _io_mode(bb) == "relay":
        relay = (bb.get("relay") or {}).get(side) or {}
        pin = _pin(relay.get("pin"))
        enabled = bool(relay.get("enabled", True))
        if pin is None:
            return None, None, enabled
        return do_start + pin, None, enabled

    direct = bb.get("direct") or {}
    cfg = direct.get(side) or {}
    if not cfg:
        cfg = (direct.get("entry_a") or {}).get(side) or {}
    open_p = _pin(cfg.get("open_pin"))
    close_p = _pin(cfg.get("close_pin"))
    enabled = bool(cfg.get("enabled", True))
    return (
        (do_start + open_p) if open_p is not None else None,
        (do_start + close_p) if close_p is not None else None,
        enabled,
    )


def _build_hardware(ctx: AppContext) -> None:
    settings = ctx.settings
    assert settings
    io_cfg = settings.io_config()
    demo = settings.demo_mode

    ctx.io = create_io_controller(io_cfg, demo_mode=demo)
    if not ctx.io.connect():
        logger.error("I/O controller failed to connect (continuing)")

    do_start = int(io_cfg.get("digital_outputs", {}).get("start_address") or 0)

    ctx.traffic_lights = {}
    if settings.is_bidirectional():
        for direction in ("entry_a", "entry_b"):
            entry_red, entry_green = _resolve_tl_pins(
                io_cfg, "entry", do_start, direction
            )
            exit_red, exit_green = _resolve_tl_pins(
                io_cfg, "exit", do_start, direction
            )
            ctx.traffic_lights[direction] = {
                "entry": TrafficLight(
                    ctx.io,
                    red_pin=entry_red,
                    green_pin=entry_green,
                    name=f"{direction}_entry",
                ),
                "exit": TrafficLight(
                    ctx.io,
                    red_pin=exit_red,
                    green_pin=exit_green,
                    name=f"{direction}_exit",
                ),
            }
        ctx.entry_tl = ctx.traffic_lights["entry_a"]["entry"]
        ctx.exit_tl = ctx.traffic_lights["entry_a"]["exit"]
        entry_red = ctx.entry_tl.red_pin
        entry_green = ctx.entry_tl.green_pin
        exit_red = ctx.exit_tl.red_pin
        exit_green = ctx.exit_tl.green_pin
    else:
        entry_red, entry_green = _resolve_tl_pins(io_cfg, "entry", do_start)
        exit_red, exit_green = _resolve_tl_pins(io_cfg, "exit", do_start)
        ctx.entry_tl = TrafficLight(
            ctx.io, red_pin=entry_red, green_pin=entry_green, name="entry"
        )
        ctx.exit_tl = TrafficLight(
            ctx.io, red_pin=exit_red, green_pin=exit_green, name="exit"
        )

    e_open, e_close, e_en = _resolve_boom_pins(io_cfg, "entry", do_start)
    x_open, x_close, x_en = _resolve_boom_pins(io_cfg, "exit", do_start)

    ctx.entry_boom = BoomBarrier(
        ctx.io, open_pin=e_open, close_pin=e_close, enabled=e_en, name="entry"
    )
    ctx.exit_boom = BoomBarrier(
        ctx.io, open_pin=x_open, close_pin=x_close, enabled=x_en, name="exit"
    )

    sensors = io_cfg.get("sensors", {}) or {}
    di_cfg = io_cfg.get("digital_inputs", {}) or {}
    di_start = int(di_cfg.get("start_address") or 0)
    poll = float(io_cfg.get("polling", {}).get("scan_interval") or 0.3)

    entry_cfg = sensors.get("entry_sensor", {}) or {}
    wb_cfg = sensors.get("wb_sensor", {}) or {}
    exit_cfg = sensors.get("exit_sensor", {}) or {}

    entry_pin = _pin(entry_cfg.get("pin"))
    wb_pin = _pin(wb_cfg.get("pin"))
    exit_pin = _pin(exit_cfg.get("pin"))

    default_sig = (entry_cfg.get("default_signal") or "low").lower()
    active_high = default_sig == "low"

    def on_entry_occ():
        if ctx.workflow:
            ctx.workflow.on_entry_occupied()

    def on_entry_clear():
        if ctx.workflow:
            ctx.workflow.on_entry_cleared()

    def on_wb_occ():
        if ctx.workflow:
            ctx.workflow.on_wb_occupied()

    def on_exit_occ():
        if ctx.workflow:
            ctx.workflow.on_exit_occupied()

    def on_exit_clear():
        if ctx.workflow:
            ctx.workflow.on_exit_cleared()

    ctx.sensor_poller = SensorPoller(
        ctx.io,
        entry_pin=entry_pin,
        exit_pin=exit_pin,
        wb_pin=wb_pin,
        di_start_address=di_start,
        poll_interval=poll,
        active_high=active_high,
        on_entry=on_entry_clear if entry_pin is not None else None,
        on_exit=on_exit_clear if exit_pin is not None else None,
        on_entry_occupied=on_entry_occ if entry_pin is not None else None,
        on_wb_occupied=on_wb_occ if wb_pin is not None else None,
        on_exit_occupied=on_exit_occ if exit_pin is not None else None,
    )
    logger.info(
        "I/O mapped demo=%s TL entry=%s/%s exit=%s/%s boom entry=%s(en=%s) "
        "exit=%s(en=%s) sensors entry=%s wb=%s exit=%s",
        demo,
        entry_red,
        entry_green,
        exit_red,
        exit_green,
        e_open,
        e_en,
        x_open,
        x_en,
        entry_pin,
        wb_pin,
        exit_pin,
    )

    def on_tags(id_hexes: List[str], raw: List[dict]) -> None:
        if ctx.workflow:
            ctx.workflow.on_rfid_tags(id_hexes, raw)

    # The HTTP intake parser is shared. In bidirectional mode, cloud controls
    # select which physical Zebra reader is scanning for the current direction.
    rfid_cfg = settings.rfid_config("entry_a")
    ctx.rfid_reader = create_rfid_reader(
        rfid_cfg, demo_mode=demo, on_tags=on_tags
    )
    ctx.rfid_reader.start()
    ctx.rfid_clouds = {}
    for direction, direction_cfg in settings.rfid_configs().items():
        cloud = build_rfid_cloud_control(direction_cfg, enabled=True)
        if cloud:
            ctx.rfid_clouds[direction] = cloud
    # Backward compatibility for unidirectional code/status.
    ctx.rfid_cloud = ctx.rfid_clouds.get("entry_a")
    logger.info(
        "RFID cloud controls wb_type=%s directions=%s",
        settings.wb_type,
        sorted(ctx.rfid_clouds),
    )


def bootstrap() -> AppContext:
    setup_logging()
    _ensure_local_mqtt_broker()
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
        weight_details_url=settings.weight_details_url,
        boom_close_url=settings.boom_close_url,
        reset_checkpoint_url=settings.reset_checkpoint_url,
        weight_confirm_url=settings.weight_confirm_url,
        gross_tolerance_confirm_url=settings.gross_tolerance_confirm_url,
        vadhghat_weight_adjustment_url=settings.vadhghat_weight_adjustment_url,
        vadhghat_weight_details_url=settings.vadhghat_weight_details_url,
        vadhghat_boom_close_url=settings.vadhghat_boom_close_url,
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

    # Empty Display IP(s) → console only.
    display_ips = list(getattr(settings, "display_ips", None) or [])
    pcb_mode = getattr(settings, "display_pcb_mode", None) or (
        "b" if settings.is_bidirectional() else "a"
    )
    if not display_ips or settings.display_type == "console":
        from services.display_service import ConsoleDisplayService

        ctx.display = ConsoleDisplayService(
            pcb_mode=pcb_mode, display_ips=display_ips
        )
        logger.info(
            "Display IP empty - using console display mode=%s", pcb_mode
        )
        ctx.display.send("Welcome")
    else:
        ctx.display = create_display_service(
            display_type=settings.display_type,
            broker=settings.mqtt_broker or "127.0.0.1",
            port=settings.mqtt_port,
            topic_tx=settings.mqtt_topic_tx or f"data_info/{pcb_mode}",
            display_ips=display_ips,
            pcb_mode=pcb_mode,
            is_bidirectional=settings.is_bidirectional(),
            demo_fallback=True,
            client_id="mines_wb_display",
        )
        # MQTT publishes Welcome on first connect; console fallback needs it here
        st = ctx.display.get_status() if hasattr(ctx.display, "get_status") else {}
        if (st or {}).get("type") == "console":
            ctx.display.send("Welcome")

    ctx.digitizer = create_digitizer_client(settings)
    if hasattr(ctx.digitizer, "start"):
        ctx.digitizer.start()

    if settings.use_audio():
        if getattr(sys, "frozen", False):
            voice_base = Path(sys.executable).resolve().parent
        else:
            voice_base = Path(__file__).resolve().parent
        ctx.voice = VoiceService(
            voice_directory=settings.voice_path or settings.voice_directory,
            error_prefix=settings.voice_error_prefix,
            hardware_enabled=True,
            base_path=str(voice_base),
        )
    else:
        ctx.voice = None
        logger.info("Voice announcements skipped (voice.enabled/validated false)")

    _build_hardware(ctx)

    ctx.workflow = MinesWbWorkflow(ctx)
    if hasattr(ctx.workflow, "attach_digitizer_monitor"):
        ctx.workflow.attach_digitizer_monitor()

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
        client_id="mines_wb_frontend",
        ctx=ctx,
    )
    ctx.frontend.display = MSG_IDLE
    ctx.frontend.register_reset_handler(
        lambda: ctx.workflow.force_reset(announce_reset=True)
        if ctx.workflow
        else None
    )
    ctx.frontend.register_free_pass_handler(
        lambda: ctx.workflow.start_free_pass() if ctx.workflow else None
    )
    ctx.frontend.register_status_request_handler(ctx.frontend.republish_snapshot)
    ctx.frontend.connect()
    ctx.frontend.start_device_monitor(interval_sec=0.4)

    # Set TL/boom immediately. Do not call Zebra login/mode/start at boot;
    # the selected reader starts only after a valid > minimum weight result.
    # Do not clear display at boot — MQTT Welcome stays until first transaction message.
    if ctx.workflow:
        ctx.workflow.apply_idle_signals()

    # Start sensors after workflow + MQTT exist so an already-cut S1 is
    # published to the dashboard and can start positioning.
    if ctx.sensor_poller:
        ctx.sensor_poller.start()
    if ctx.frontend:
        ctx.frontend.publish_device_status()
        ctx.frontend.republish_snapshot()
    logger.info("RFID cloud idle at boot - login/mode/start deferred until weight OK")
    logger.info(
        "Hardware reset to IDLE (%s)",
        (
            "both entries green, both exits red, both booms open"
            if settings.is_bidirectional()
            else "entry green/open, exit red/closed"
        ),
    )

    if ctx.voice and ctx.voice.is_enabled():
        ctx.voice.welcome()

    logger.info(
        "Mines WB bootstrapped demo=%s config=%s state=%s digitizer=%s",
        settings.demo_mode,
        settings.config_path,
        ctx.state_machine.current_state.name,
        settings.digitizer_label,
    )
    return ctx


def main() -> int:
    ctx = bootstrap()
    settings = ctx.settings
    assert settings

    app = start_api_server(host=settings.api_host, port=settings.api_port, os_type=OS_TYPE)
    rfid_ports = settings.rfid_api_listen_ports()
    start_rfid_api_ports(app, settings.api_host, rfid_ports)

    banner = (
        "\n"
        "============================================================\n"
        "  GMDC Mines Weighbridge running\n"
        f"  DEMO_MODE  : {settings.demo_mode}\n"
        f"  Dashboard  : http://127.0.0.1:{settings.api_port}/\n"
        f"  Animation  : http://127.0.0.1:{settings.api_port}/animated.html\n"
        f"  API        : http://127.0.0.1:{settings.api_port}/api/status\n"
        f"  RFID ports : {', '.join(str(p) for p in rfid_ports) or 'application port'}\n"
        f"  MQTT TCP   : {settings.mqtt_broker}:{settings.mqtt_port}\n"
        f"  MQTT WS    : ws://<this-pc-ip>:{settings.mqtt_ws_port}\n"
        f"  Config     : {settings.config_path}\n"
        f"  Digitizer  : {settings.digitizer_label}\n"
        f"  State      : {ctx.state_machine.current_state.name if ctx.state_machine else '?'}\n"
        f"  Waiting for "
        f"{'ENTRY or EXIT sensor' if settings.is_bidirectional() else 'ENTRY sensor'}"
        f"{' (POST /api/simulate-entry or /api/simulate-exit when DEMO_MODE=true)' if settings.demo_mode and settings.is_bidirectional() else ' (POST /api/simulate-entry when DEMO_MODE=true)' if settings.demo_mode else ''}\n"
        "  Console idle here is normal - check /api/status for liveness.\n"
        "============================================================\n"
    )
    print(banner, flush=True)
    logger.info(
        "API on http://%s:%s  POST /rfid_data, GET /api/status",
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
        if ctx.workflow:
            try:
                ctx.workflow.stop_all_rfid_readers()
            except Exception:
                pass
        if ctx.frontend:
            try:
                ctx.frontend.disconnect()
            except Exception:
                pass
        if ctx.digitizer and hasattr(ctx.digitizer, "stop"):
            try:
                ctx.digitizer.stop()
            except Exception:
                pass
        if ctx.display:
            ctx.display.disconnect()
        if ctx.io:
            ctx.io.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
