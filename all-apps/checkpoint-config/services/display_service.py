"""Display connectivity checks for checkpoint-config wizard."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt
import requests
from requests.exceptions import RequestException, Timeout

logger = logging.getLogger(__name__)

TOPIC_DISPLAY_INFO = "display_info"
TOPIC_PCB_ID = "pcb_id"
TOPIC_DATA_INFO = "data_info"


class DisplayService:
    def __init__(self):
        self.mqtt_client = None
        self.mqtt_connected = False

    def check_connection(
        self,
        display_type: str,
        display_ip: str = "",
        display_port: Optional[str] = None,
        *,
        display_ips: Optional[List[str]] = None,
        pcb_mode: str = "a",
        broker: str = "localhost",
        broker_port: int = 1883,
        wait_sec: float = 8.0,
    ) -> Dict[str, Any]:
        """Check display connectivity based on type.

        MQTT protocol:
          1. Subscribe display_info/{ip} for each Display IP
          2. Wait for device message
          3. Publish pcb_id/{ip} = a|b (Entry A → a, Entry B → b on bi)
          4. Publish test payload on data_info/a (and data_info/b when bi)
        """
        if display_type == "api":
            return self._check_api(display_ip, display_port)
        if display_type == "mqtt":
            ips = []
            if display_ips:
                ips = [str(x).strip() for x in display_ips if str(x).strip()]
            elif display_ip:
                ips = [str(display_ip).strip()]
            return self._check_mqtt(
                ips,
                pcb_mode=pcb_mode,
                broker=broker,
                broker_port=int(broker_port or 1883),
                wait_sec=wait_sec,
            )
        return {"status": 400, "message": f"Unknown display type: {display_type}"}

    def _check_api(self, display_ip, display_port=None):
        if not display_ip:
            return {"status": 400, "message": "Display IP is required"}

        port = str(display_port or "8000").strip()
        if not port.isdigit():
            return {"status": 400, "message": "Display Port must be numeric"}

        url = f"http://{display_ip}:{port}/display_data"
        display_payload = {"data": "Hello World"}
        try:
            response = requests.post(url, json=display_payload, timeout=10)
            if response.status_code == 200:
                return {
                    "status": 200,
                    "message": "Display connected successfully via API",
                }
            return {
                "status": response.status_code,
                "message": f"Display responded with status: {response.status_code}",
            }
        except Timeout:
            return {
                "status": 408,
                "message": "Connection timed out. Display not responding.",
            }
        except RequestException:
            logger.exception(
                "Display API connectivity check failed for %s:%s", display_ip, port
            )
            return {
                "status": 500,
                "message": (
                    "Unable to connect to Display API. "
                    "Please verify display IP/port and API availability."
                ),
            }

    def _check_mqtt(
        self,
        display_ips: List[str],
        *,
        pcb_mode: str = "a",
        broker: str = "localhost",
        broker_port: int = 1883,
        wait_sec: float = 8.0,
    ) -> Dict[str, Any]:
        mode = str(pcb_mode or "a").strip().lower()[:1] or "a"
        if mode not in ("a", "b"):
            mode = "a"
        ips = []
        seen = set()
        for ip in display_ips or []:
            ip = str(ip or "").strip()
            if ip and ip not in seen:
                seen.add(ip)
                ips.append(ip)
        if not ips:
            return {
                "status": 400,
                "message": "Display IP is required for MQTT validation",
            }

        results: List[Dict[str, Any]] = []
        bi = len(ips) >= 2
        for idx, ip in enumerate(ips):
            letter = ("a" if idx == 0 else "b") if bi else mode
            one = self._check_mqtt_one(
                ip,
                pcb_letter=letter,
                tx_both=bi,
                broker=broker,
                broker_port=broker_port,
                wait_sec=wait_sec,
            )
            results.append({"ip": ip, **one})
            if one.get("status") != 200:
                return {
                    "status": one.get("status", 500),
                    "message": (
                        f"Display {ip}: {one.get('message', 'check failed')}"
                    ),
                    "results": results,
                    "pcb_mode": mode,
                }

        if len(ips) == 1:
            return {
                "status": 200,
                "message": (
                    f"Display {ips[0]} OK — subscribed display_info/{ips[0]}, "
                    f"answered pcb_id/{ips[0]}={mode}, "
                    f"published data_info/{mode}"
                ),
                "results": results,
                "pcb_mode": mode,
            }
        return {
            "status": 200,
            "message": (
                f"Both displays OK ({', '.join(ips)}) — "
                f"pcb a/b per Entry; tx data_info/a and data_info/b"
            ),
            "results": results,
            "pcb_mode": mode,
        }

    def _check_mqtt_one(
        self,
        display_ip: str,
        *,
        pcb_letter: str,
        tx_both: bool,
        broker: str,
        broker_port: int,
        wait_sec: float,
    ) -> Dict[str, Any]:
        letter = str(pcb_letter or "a").strip().lower()[:1] or "a"
        if letter not in ("a", "b"):
            letter = "a"
        info_topic = f"{TOPIC_DISPLAY_INFO}/{display_ip}"
        pcb_topic = f"{TOPIC_PCB_ID}/{display_ip}"
        data_topics = (
            [f"{TOPIC_DATA_INFO}/a", f"{TOPIC_DATA_INFO}/b"]
            if tx_both
            else [f"{TOPIC_DATA_INFO}/{letter}"]
        )
        got_info = threading.Event()
        received_payload = {"text": ""}

        client = mqtt.Client()
        connected = {"ok": False}

        def on_connect(client, userdata, flags, rc):
            connected["ok"] = rc == 0
            if rc == 0:
                client.subscribe(info_topic)

        def on_message(client, userdata, msg):
            if msg.topic == info_topic:
                try:
                    received_payload["text"] = msg.payload.decode(
                        "utf-8", errors="replace"
                    )
                except Exception:
                    received_payload["text"] = ""
                # Answer pcb_id immediately (a for Entry A, b for Entry B)
                client.publish(pcb_topic, str(letter), qos=1)
                got_info.set()

        try:
            client.on_connect = on_connect
            client.on_message = on_message
            client.connect(broker, int(broker_port), 60)
            client.loop_start()

            deadline = time.time() + 5
            while not connected["ok"] and time.time() < deadline:
                time.sleep(0.05)
            if not connected["ok"]:
                self._safe_stop(client)
                return {
                    "status": 500,
                    "message": f"Failed to connect to MQTT broker at {broker}:{broker_port}",
                }

            # Wait for display device to publish on display_info/{ip}
            if not got_info.wait(timeout=max(1.0, float(wait_sec))):
                self._safe_stop(client)
                return {
                    "status": 408,
                    "message": (
                        f"No message on {info_topic} within {wait_sec:.0f}s. "
                        "Power on the display and ensure it publishes its "
                        f"identity on {info_topic}."
                    ),
                }

            # Transmit test transaction payload (both a+b on bi)
            test_msg = "TEST@OK"
            for data_topic in data_topics:
                client.publish(data_topic, test_msg, qos=1)
            time.sleep(0.3)
            self._safe_stop(client)
            tx_desc = ", ".join(f"{t}={test_msg!r}" for t in data_topics)
            return {
                "status": 200,
                "message": (
                    f"Handshake OK (rx={received_payload['text']!r}); "
                    f"pcb_id={letter}; tx {tx_desc}"
                ),
                "info_topic": info_topic,
                "pcb_topic": pcb_topic,
                "data_topics": data_topics,
                "data_topic": data_topics[0],
            }
        except Exception:
            self._safe_stop(client)
            logger.exception("Display MQTT connectivity check failed for %s", display_ip)
            return {
                "status": 500,
                "message": (
                    "MQTT validation failed. Please verify broker status "
                    "and Display IP topic configuration."
                ),
            }

    @staticmethod
    def _safe_stop(client) -> None:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass

    def disconnect(self):
        return {"status": 200, "message": "Display disconnected"}
