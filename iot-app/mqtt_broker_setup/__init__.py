"""
Shared Mosquitto MQTT broker installer / ensure-running helper.

Used by checkpoint-config, Mines-Checkpoint, and Mines-WB so each app can
boot only after local MQTT (1883) and WebSocket (9001) listeners are up.
"""

from .ensure import (
    MQTT_PORT,
    WS_PORT,
    add_package_to_sys_path,
    bootstrap_local_mqtt,
    ensure_mqtt_broker_ready,
    mqtt_ports_ready,
    resolve_mqtt_tcp_port,
    resolve_mqtt_ws_port,
)

__all__ = [
    "MQTT_PORT",
    "WS_PORT",
    "add_package_to_sys_path",
    "bootstrap_local_mqtt",
    "ensure_mqtt_broker_ready",
    "mqtt_ports_ready",
    "resolve_mqtt_tcp_port",
    "resolve_mqtt_ws_port",
]
