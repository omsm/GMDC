"""Application context singleton for Digitizer Decoder."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from config.settings import Settings, is_calibrated, save_config, serial_port_configured
from services.mqtt_bridge import MqttBridge
from services.serial_service import SerialService
from services.weight_runtime import WeightRuntime

logger = logging.getLogger("digitizer_decoder.context")


class AppContext:
    _instance: Optional["AppContext"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.settings: Optional[Settings] = None
        self.runtime = WeightRuntime()
        self.serial = SerialService(self.runtime)
        self.mqtt: Optional[MqttBridge] = None
        self.mqtt_status: str = "MQTT idle"
        self.version: str = "0.0.0"
        self._status_publish_lock = threading.Lock()
        self._last_status_publish = 0.0
        self.runtime.set_update_listener(self._on_runtime_update)

    @classmethod
    def get_instance(cls) -> "AppContext":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            cls._instance = None

    def bootstrap(self, settings: Settings, version: str = "0.0.0") -> None:
        self.settings = settings
        self.version = version
        self.serial.apply_config(settings.raw)
        if serial_port_configured(settings.raw):
            self.serial.start()
        self.apply_transport()

    def apply_transport(self) -> None:
        """Start MQTT for live UI status + optional weight request/response."""
        assert self.settings is not None
        mode = self.settings.communication_mode
        if self.mqtt:
            self.mqtt.stop()
            self.mqtt = None
            self.mqtt_status = "MQTT idle"

        cfg = self.settings.mqtt_cfg
        broker = str(cfg.get("broker_host") or "").strip() or "127.0.0.1"
        # Always connect MQTT for dashboard live status (WS :9001 on broker).
        # Weight request/response topics are used when mode=mqtt.
        self.mqtt = MqttBridge(
            self.runtime,
            broker_host=broker,
            broker_port=int(cfg.get("broker_port") or 1883),
            username=str(cfg.get("username") or ""),
            password=str(cfg.get("password") or ""),
            topic_publish=str(
                cfg.get("topic_publish") or "gmdc/digitizer/weight"
            ),
            topic_subscribe=str(
                cfg.get("topic_subscribe") or "gmdc/digitizer/request"
            ),
            topic_status=str(
                cfg.get("topic_status") or "gmdc/digitizer/status"
            ),
            client_id=str(
                cfg.get("client_id") or "gmdc-digitizer-decoder"
            ),
            on_status=self._on_mqtt_status,
        )
        self.mqtt.set_status_provider(self.status_snapshot)
        ok = self.mqtt.start()
        if not ok:
            self.mqtt_status = "MQTT failed to start"
        logger.info(
            "Transport mode=%s mqtt_started=%s (live status via MQTT)",
            mode,
            ok,
        )

    def _on_mqtt_status(self, msg: str) -> None:
        self.mqtt_status = msg

    def _on_runtime_update(self) -> None:
        if not (self.mqtt and self.mqtt.connected):
            return
        # Throttle UI status publishes (~10 Hz) to avoid flooding Mosquitto
        now = time.monotonic()
        with self._status_publish_lock:
            if now - self._last_status_publish < 0.1:
                return
            self._last_status_publish = now
        self.mqtt.publish_ui_status()

    def update_config(self, patch: Dict[str, Any], restart_serial: bool = True) -> bool:
        assert self.settings is not None
        merged = dict(self.settings.raw)
        for key, value in patch.items():
            if key == "communication" and isinstance(value, dict):
                comm = dict(merged.get("communication") or {})
                if "mode" in value:
                    comm["mode"] = value["mode"]
                if isinstance(value.get("api"), dict):
                    api = dict(comm.get("api") or {})
                    api.update(value["api"])
                    comm["api"] = api
                if isinstance(value.get("mqtt"), dict):
                    mqtt = dict(comm.get("mqtt") or {})
                    mqtt.update(value["mqtt"])
                    comm["mqtt"] = mqtt
                merged["communication"] = comm
            else:
                merged[key] = value
        merged["status"] = is_calibrated(merged)
        if not save_config(merged, self.settings.path):
            return False
        self.settings.raw = merged
        self.serial.apply_config(merged)
        if restart_serial:
            if serial_port_configured(merged):
                self.serial.start()
            else:
                self.serial.stop(reconnect=False)
        self.apply_transport()
        return True

    def status_snapshot(self) -> Dict[str, Any]:
        assert self.settings is not None
        snap = self.runtime.snapshot()
        return {
            "statusCode": 200,
            "service": "GMDC Digitizer Decoder",
            "version": self.version,
            "calibrated": is_calibrated(self.settings.raw),
            "serial_connected": self.serial.connected,
            "communication_mode": self.settings.communication_mode,
            "mqtt_status": self.mqtt_status,
            "mqtt_connected": bool(self.mqtt and self.mqtt.connected),
            "api": self.settings.api_cfg,
            "mqtt": {
                **{
                    k: v
                    for k, v in self.settings.mqtt_cfg.items()
                    if k != "password"
                },
                "topic_status": (
                    (self.settings.mqtt_cfg.get("topic_status") or "")
                    or "gmdc/digitizer/status"
                ),
                "password_set": bool(self.settings.mqtt_cfg.get("password")),
                "client_id_active": (
                    self.mqtt.client_id if self.mqtt else None
                ),
                "ws_port": 9001,
            },
            "serial": {
                "port": self.settings.raw.get("port"),
                "baud_rate": self.settings.raw.get("baud_rate"),
                "data_bits": self.settings.raw.get("data_bits"),
                "parity": self.settings.raw.get("parity"),
                "stop_bits": self.settings.raw.get("stop_bits"),
            },
            **snap,
        }
