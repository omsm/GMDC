"""Re-export shared display service from gmdc_common."""

from gmdc_common.services.display_service import (  # noqa: F401
    ConsoleDisplayService,
    DisplayService,
    MQTTDisplayService,
    MQTT_AVAILABLE,
    create_display_service,
    data_info_topic,
    data_info_topics_for_ips,
    display_info_topic,
    normalize_display_ips,
    normalize_pcb_letter,
    pcb_id_topic,
    pcb_letter_for_display_ip,
    pcb_letter_from_topic,
    resolve_pcb_mode,
)

__all__ = [
    "ConsoleDisplayService",
    "DisplayService",
    "MQTTDisplayService",
    "MQTT_AVAILABLE",
    "create_display_service",
    "data_info_topic",
    "data_info_topics_for_ips",
    "display_info_topic",
    "normalize_display_ips",
    "normalize_pcb_letter",
    "pcb_id_topic",
    "pcb_letter_for_display_ip",
    "pcb_letter_from_topic",
    "resolve_pcb_mode",
]
