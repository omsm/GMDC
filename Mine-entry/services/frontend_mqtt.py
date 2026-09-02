"""
MQTT publisher for the Mines Entry operator dashboard (wb_frontend/*).

The dashboard connects over WebSocket to the in-process broker on port 9001
(ws://<checkpoint-ip>:9001). Mosquitto is optional (TCP :1883 bridge).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from services.mqtt_ws_broker import get_mqtt_ws_broker

logger = logging.getLogger("mine_entry.services.frontend_mqtt")

MQTT_AVAILABLE = False
MQTT_V2 = False
CallbackAPIVersion = None
mqtt = None

try:
    import paho.mqtt.client as mqtt

    MQTT_AVAILABLE = True
    try:
        from paho.mqtt.client import CallbackAPIVersion

        MQTT_V2 = True
    except ImportError:
        CallbackAPIVersion = None
        MQTT_V2 = False
except ImportError:
    mqtt = None


APP_VERSION_DEFAULT = "1.0.0"

IDLE_DISPLAY = "Mines Entry"

# Dashboard step ids must match static/web/index.html data-step values.
STEP_RFID_READ = "rfid_read"
STEP_VALIDATING_RFID = "validating_rfid"
STEP_VALIDATING_ANPR = "validating_anpr"
STEP_ENTRY_GRANTED = "entry_granted"
STEP_WAIT_CROSSING = "wait_crossing"
STEP_EXIT_COMPLETED = "exit_completed"


def load_app_version(project_root) -> str:
    path = project_root / "VERSION"
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text or APP_VERSION_DEFAULT
    except OSError:
        return APP_VERSION_DEFAULT


def idle_update_status(version: str) -> Dict[str, Any]:
    return {
        "update_available": False,
        "current_version": version,
        "latest_version": version,
        "release_notes": "",
        "progress_percent": 0,
        "progress_step": "idle",
        "progress_message": "",
        "applying": False,
    }


def idle_update_progress() -> Dict[str, Any]:
    return {
        "percent": 0,
        "step": "idle",
        "message": "",
        "applying": False,
    }


class FrontendMqtt:
    """Publishes live Mines Entry UI state on wb_frontend/* topics."""

    def __init__(
        self,
        broker: str = "127.0.0.1",
        port: int = 1883,
        client_id: str = "mine_entry_frontend",
        ctx: Any = None,
    ):
        self.broker = broker or "127.0.0.1"
        self.port = int(port or 1883)
        self.client_id = client_id
        self.ctx = ctx
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        self._monitor: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self.position: int = -1
        self.display: str = IDLE_DISPLAY
        self.rfid: str = ""
        self.truck_number: Optional[str] = None
        self.last_status: Dict[str, str] = {
            "step": STEP_RFID_READ,
            "status": "idle",
            "message": "Waiting for RFID scan.",
        }
        self._seq: int = 0
        self._last_sig: str = ""

        self._on_reset: Optional[Callable[[], None]] = None
        self._on_free_pass: Optional[Callable[[], None]] = None
        self._on_status_request: Optional[Callable[[], None]] = None
        self._ws_broker = get_mqtt_ws_broker()
        self._ws_broker.set_incoming_handler(self._on_ws_incoming)

        if not MQTT_AVAILABLE:
            logger.warning("paho-mqtt not installed - optional MQTT TCP bridge disabled")
            return

        try:
            if MQTT_V2 and CallbackAPIVersion is not None:
                self._client = mqtt.Client(
                    callback_api_version=CallbackAPIVersion.VERSION1,
                    client_id=client_id,
                )
            else:
                self._client = mqtt.Client(client_id=client_id)
        except Exception:
            self._client = mqtt.Client(client_id=client_id)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def connect(self) -> bool:
        ws_ok = False
        try:
            ws_ok = bool(self._ws_broker and self._ws_broker.start())
            if ws_ok:
                logger.info("Browser MQTT WebSocket ready on port %s", self._ws_broker.port)
                self.republish_snapshot()
        except Exception as e:
            logger.warning("MQTT WebSocket broker failed to start: %s", e)

        if not self._client:
            return ws_ok
        try:
            logger.info(
                "Optional MQTT TCP %s:%s (dashboard uses ws://<pc-ip>:9001)",
                self.broker,
                self.port,
            )
            self._client.connect(self.broker, self.port, keepalive=60)
            self._client.loop_start()
            for _ in range(10):
                if self._connected:
                    break
                time.sleep(0.2)
            if not self._connected:
                logger.info("External MQTT TCP not available — using in-app WebSocket broker")
            return ws_ok or self._connected
        except Exception as e:
            logger.info("MQTT TCP skipped (%s) — using in-app WebSocket broker", e)
            return ws_ok

    def disconnect(self) -> None:
        self._stop.set()
        if self._monitor and self._monitor.is_alive():
            self._monitor.join(timeout=1.5)
        if self._ws_broker:
            try:
                self._ws_broker.stop()
            except Exception:
                pass
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    def start_device_monitor(self, interval_sec: float = 0.4) -> None:
        if self._monitor and self._monitor.is_alive():
            return

        def _loop():
            while not self._stop.wait(interval_sec):
                try:
                    self.publish_device_status()
                except Exception as e:
                    logger.debug("device_status publish: %s", e)

        self._monitor = threading.Thread(
            target=_loop, name="FrontendDeviceStatus", daemon=True
        )
        self._monitor.start()

    def register_reset_handler(self, handler: Callable[[], None]) -> None:
        self._on_reset = handler

    def register_free_pass_handler(self, handler: Callable[[], None]) -> None:
        self._on_free_pass = handler

    def register_status_request_handler(self, handler: Callable[[], None]) -> None:
        self._on_status_request = handler

    def _on_connect(self, client, userdata, flags, rc):
        self._connected = rc == 0
        if rc != 0:
            logger.error("Frontend MQTT connect rc=%s", rc)
            return
        logger.info("Frontend MQTT connected %s:%s", self.broker, self.port)
        client.subscribe("wb_frontend/request_status")
        client.subscribe("wb_frontend/reset_application")
        client.subscribe("wb_frontend/free_pass")
        self.republish_snapshot()

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning("Frontend MQTT disconnected rc=%s", rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = (msg.payload or b"").decode("utf-8", errors="replace")
        if topic == "wb_frontend/request_status":
            logger.info("Frontend requested status snapshot")
            handler = self._on_status_request or self.republish_snapshot
            handler()
            return
        if topic == "wb_frontend/reset_application":
            logger.info("Frontend requested application reset payload=%s", payload)
            if self._on_reset:
                threading.Thread(
                    target=self._on_reset, name="FrontendReset", daemon=True
                ).start()
            return
        if topic == "wb_frontend/free_pass":
            logger.info("Frontend requested free pass payload=%s", payload)
            if self._on_free_pass:
                threading.Thread(
                    target=self._on_free_pass, name="FrontendFreePass", daemon=True
                ).start()

    def _on_ws_incoming(self, topic: str, payload: str) -> None:
        if topic == "wb_frontend/request_status":
            logger.info("MQTT WS status request from browser")
            handler = self._on_status_request or self.republish_snapshot
            handler()
            return
        if topic == "wb_frontend/reset_application":
            logger.info("MQTT WS reset from browser")
            if self._on_reset:
                threading.Thread(
                    target=self._on_reset, name="FrontendReset", daemon=True
                ).start()
            return
        if topic == "wb_frontend/free_pass":
            logger.info("MQTT WS free pass from browser")
            if self._on_free_pass:
                threading.Thread(
                    target=self._on_free_pass, name="FrontendFreePass", daemon=True
                ).start()

    def _publish(self, topic: str, message: str, qos: int = 0) -> bool:
        ok = False
        if getattr(self, "_ws_broker", None):
            try:
                ok = bool(self._ws_broker.publish(topic, message, qos=qos))
            except Exception as e:
                logger.debug("WS hub publish %s: %s", topic, e)
        if self._client and self._connected:
            try:
                result = self._client.publish(topic, message, qos=qos)
                ok = ok or result.rc == 0
            except Exception as e:
                logger.error("MQTT TCP publish %s failed: %s", topic, e)
        return ok

    def publish_position(self, position: int) -> bool:
        self.position = int(position)
        return self._publish("wb_frontend/position", str(self.position), qos=0)

    def publish_display(self, message: str) -> bool:
        self.display = str(message or "")
        return self._publish("wb_frontend/display", self.display, qos=0)

    def publish_rfid(
        self, rfid: str, truck_number: Optional[str] = None
    ) -> bool:
        self.rfid = str(rfid or "")
        self.truck_number = truck_number
        payload = json.dumps(
            {"rfid": self.rfid, "truck_number": self.truck_number}
        )
        return self._publish("wb_frontend/rfid", payload, qos=0)

    def publish_status(
        self,
        step: str,
        status: str,
        message: str,
        *,
        popup: bool = False,
        popup_title: str = "",
    ) -> bool:
        self.last_status = {
            "step": str(step or ""),
            "status": str(status or "info"),
            "message": str(message or ""),
            "popup": bool(popup),
            "popup_title": str(popup_title or ""),
        }
        payload = json.dumps(self.last_status)
        return self._publish("wb_frontend/status", payload, qos=0)

    def snapshot(self) -> Dict[str, Any]:
        return build_frontend_snapshot(self.ctx, publisher=self)

    def publish_device_status(self, devices: Optional[Dict[str, Any]] = None) -> bool:
        payload = devices if devices is not None else collect_device_status(self.ctx)
        return self._publish(
            "wb_frontend/device_status", json.dumps(payload), qos=0
        )

    def republish_snapshot(self) -> None:
        st = self.last_status or {}
        self.publish_position(self.position)
        self.publish_display(self.display)
        self.publish_status(
            st.get("step") or STEP_RFID_READ,
            st.get("status") or "idle",
            st.get("message") or "Waiting for RFID scan.",
            popup=bool(st.get("popup")),
            popup_title=str(st.get("popup_title") or ""),
        )
        if self.rfid:
            self.publish_rfid(self.rfid, self.truck_number)
        self.publish_device_status()

    def reset_idle(self) -> None:
        self.rfid = ""
        self.truck_number = None
        self.last_status = {
            "step": STEP_RFID_READ,
            "status": "idle",
            "message": "Waiting for RFID scan.",
        }
        self.publish_position(-1)
        self.publish_display(IDLE_DISPLAY)
        self.publish_status(
            STEP_RFID_READ,
            "idle",
            "Waiting for RFID scan.",
        )
        self.publish_device_status()


# FSM name → animation position + dashboard step.
STATE_TO_UI: Dict[str, Dict[str, Any]] = {
    "IDLE": {
        "position": -1,
        "step": STEP_RFID_READ,
        "status": "idle",
        "message": "Waiting for RFID scan.",
        "display": IDLE_DISPLAY,
    },
    "RFID_READ": {
        "position": 0,
        "step": STEP_RFID_READ,
        "status": "info",
        "message": "Reading RFID; present a valid tag.",
        "display": "READ RFID",
    },
    "RFID_VALIDATE": {
        "position": 0,
        "step": STEP_VALIDATING_RFID,
        "status": "info",
        "message": "Validating RFID with OCI.",
        "display": "VALIDATING RFID",
    },
    "RFID_ERROR": {
        "position": 0,
        "step": STEP_RFID_READ,
        "status": "error",
        "message": "RFID validation failed.",
        "display": "RFID ERR",
    },
    "DISPLAY_TRUCK": {
        "position": 1,
        "step": STEP_VALIDATING_ANPR,
        "status": "info",
        "message": "ANPR validation in progress.",
        "display": "ANPR",
    },
    "ANPR_VALIDATE": {
        "position": 1,
        "step": STEP_VALIDATING_ANPR,
        "status": "info",
        "message": "ANPR validation in progress.",
        "display": "ANPR",
    },
    "MANUAL_UPDATE": {
        "position": 1,
        "step": STEP_VALIDATING_ANPR,
        "status": "warning",
        "message": "ANPR mismatch — waiting for check-status.",
        "display": "ANPR ERR 1",
    },
    "ENTRY_GRANTED": {
        "position": 2,
        "step": STEP_ENTRY_GRANTED,
        "status": "success",
        "message": "Entry granted — proceed.",
        "display": "ENTRY GRANTED",
    },
    "WAIT_CROSSING": {
        "position": 2,
        "step": STEP_WAIT_CROSSING,
        "status": "info",
        "message": "Waiting for vehicle to clear entry sensor.",
        "display": "ENTRY GRANTED",
    },
    "ERROR": {
        "position": -1,
        "step": STEP_RFID_READ,
        "status": "error",
        "message": "Application error — reset to idle.",
        "display": IDLE_DISPLAY,
    },
    "FREE_PASS": {
        "position": 2,
        "step": STEP_WAIT_CROSSING,
        "status": "info",
        "message": "Free pass — traffic light green, boom open. Waiting for entry sensor.",
        "display": "FREE PASS",
    },
}


def build_frontend_snapshot(
    ctx: Any = None, publisher: Optional["FrontendMqtt"] = None
) -> Dict[str, Any]:
    fe = publisher or (getattr(ctx, "frontend", None) if ctx else None)
    sm = getattr(ctx, "state_machine", None) if ctx else None
    txn_store = getattr(ctx, "transactions", None) if ctx else None
    display_svc = getattr(ctx, "display", None) if ctx else None

    state_name = sm.current_state.name if sm and sm.current_state else "IDLE"
    ui = STATE_TO_UI.get(state_name) or STATE_TO_UI["IDLE"]
    position = int(ui["position"])
    status_payload = {
        "step": str(ui["step"]),
        "status": str(ui["status"]),
        "message": str(ui["message"]),
    }
    last = getattr(fe, "last_status", None) if fe else None
    if isinstance(last, dict) and last.get("step") == status_payload["step"]:
        status_payload = dict(last)

    display_text = str(ui.get("display") or IDLE_DISPLAY)
    if fe and fe.display:
        display_text = fe.display
    elif display_svc and hasattr(display_svc, "get_status"):
        last_disp = (display_svc.get_status() or {}).get("last")
        if last_disp:
            display_text = str(last_disp)

    rfid = ""
    truck = None
    txn = getattr(txn_store, "current", None) if txn_store else None
    if txn:
        rfid = str(getattr(txn, "validated_rfid", None) or getattr(txn, "rfid", "") or "")
        truck = getattr(txn, "vehicle_no", None) or getattr(txn, "truck_no", None) or None
    if fe:
        if not rfid and fe.rfid:
            rfid = fe.rfid
            truck = fe.truck_number

    payload: Dict[str, Any] = {
        "state": state_name,
        "position": position,
        "display": display_text,
        "status": status_payload,
        "rfid": {"rfid": rfid, "truck_number": truck} if rfid else None,
        "device_status": collect_device_status(ctx),
        "mqtt_connected": bool(fe and getattr(fe, "_connected", False)),
    }
    sig = json.dumps(
        {
            "state": state_name,
            "position": position,
            "display": display_text,
            "status": status_payload,
            "rfid": payload["rfid"],
        },
        sort_keys=True,
        default=str,
    )
    seq = 0
    if fe is not None and isinstance(getattr(fe, "_seq", None), int):
        if sig != getattr(fe, "_last_sig", ""):
            fe._seq = fe._seq + 1
            fe._last_sig = sig
        seq = fe._seq
    payload["seq"] = seq
    return payload


def collect_device_status(ctx: Any) -> Dict[str, Any]:
    """Shape expected by static/web/js/app.js device badges."""
    settings = getattr(ctx, "settings", None) if ctx else None
    rfid_reader = getattr(ctx, "rfid_reader", None) if ctx else None
    io = getattr(ctx, "io", None) if ctx else None
    sensors = getattr(ctx, "sensor_poller", None) if ctx else None
    tl = getattr(ctx, "traffic_light", None) if ctx else None
    boom = getattr(ctx, "boom_barrier", None) if ctx else None

    rfid_cfg = {}
    if settings and hasattr(settings, "rfid_config"):
        try:
            rfid_cfg = settings.rfid_config() or {}
        except TypeError:
            try:
                rfid_cfg = settings.rfid_config("entry_a") or {}
            except Exception:
                rfid_cfg = {}
        except Exception:
            rfid_cfg = {}
    rfid_st = rfid_reader.get_status() if rfid_reader else {}
    rfid_ip = rfid_cfg.get("ip") or rfid_st.get("host") or ""
    rfid_port = rfid_cfg.get("port") or rfid_st.get("port") or ""
    rfid_port_info = (
        f"{rfid_ip}:{rfid_port}" if rfid_ip else str(rfid_port or "N/A")
    )
    rfid_connected = bool(
        rfid_st.get("running") or rfid_st.get("connected") or rfid_st.get("type")
    )

    io_st = io.get_status() if io else {}
    io_connected = bool(io_st.get("connected"))
    io_port = io_st.get("host")
    if io_port and io_st.get("port"):
        io_port = f"{io_port}:{io_st.get('port')}"
    elif io_st.get("type") == "demo":
        io_port = "demo"
    else:
        io_port = io_port or "N/A"

    sen = sensors.get_status() if sensors else {}
    s1 = bool(sen.get("entry_active") or sen.get("entry_occupied_latch"))

    def _tl_color(device) -> str:
        if not device:
            return "RED"
        state = str((device.get_status() or {}).get("state") or "").lower()
        return "GREEN" if state == "green" else "RED"

    def _boom_pos(device) -> str:
        if not device:
            return "Closed"
        state = str((device.get_status() or {}).get("state") or "").lower()
        return "Open" if state == "open" else "Closed"

    return {
        "rfid_reader": {
            "connected": rfid_connected,
            "port": rfid_port_info,
            "details": str(rfid_st.get("type") or "API"),
        },
        "io_controller": {
            "connected": io_connected,
            "port": str(io_port),
            "details": str(io_st.get("type") or "Modbus"),
        },
        "sensors": {"s1": s1},
        "traffic_light": {"color": _tl_color(tl)},
        "boom_barrier": {"position": _boom_pos(boom)},
    }
