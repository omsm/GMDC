"""Operator web dashboard HTTP + MQTT payload tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEMO_MODE", "true")


class TestWebPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.server import create_app

        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_dashboard_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("Checkpoint", body)
        self.assertIn("<h1>Checkpoint</h1>", body)
        self.assertIn("data-step", body)
        self.assertNotIn("Start Transaction", body)
        self.assertNotIn("Next Step", body)
        self.assertIn("reset-modal", body)
        self.assertIn("Confirm Reset", body)
        self.assertIn("Cancel", body)
        self.assertIn("Free Pass", body)
        self.assertIn("Confirm Free Pass", body)
        self.assertIn("login-modal", body)
        self.assertIn("Operator Login", body)
        self.assertIn("check-sensor-popup", body)
        self.assertIn("CHECK SENSOR", body)
        self.assertIn('id="api-alert-popup"', body)
        self.assertIn("api-alert-dismiss", body)
        self.assertIn('id="login-button"', body)
        self.assertIn('data-step="rfid_read"', body)
        self.assertIn('data-step="validating_anpr"', body)
        self.assertIn('data-step="wait_crossing"', body)
        self.assertLess(
            body.find('data-step="rfid_read"'),
            body.find('data-step="validating_rfid"'),
        )
        self.assertLess(
            body.find('data-step="validating_anpr"'),
            body.find('data-step="entry_granted"'),
        )

    def test_static_css_and_paho(self):
        css = self.client.get("/static/css/style.css")
        self.assertEqual(css.status_code, 200)
        paho = self.client.get("/static/js/paho-mqtt.js")
        self.assertEqual(paho.status_code, 200)
        js = self.client.get("/static/js/app.js")
        self.assertEqual(js.status_code, 200)
        body = js.get_data(as_text=True)
        self.assertIn("window.location.hostname", body)
        self.assertIn("MQTT_CLIENT_ID", body)
        self.assertNotIn("/api/frontend", body)
        self.assertIn("showApiAlert", body)
        self.assertIn("initApiAlertPopup", body)
        self.assertIn("failedFromStep", body)
        self.assertIn("markFailureCascade", body)
        css_body = css.get_data(as_text=True)
        self.assertIn("api-alert-popup", css_body)
        self.assertIn("step-warning-blink", css_body)
        self.assertIn("state-warning", css_body)

    def test_health_status(self):
        r = self.client.get("/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], 200)

    def test_version_and_updater(self):
        v = self.client.get("/version")
        self.assertEqual(v.status_code, 200)
        self.assertIn("version", v.get_json())
        st = self.client.get("/api/update/status")
        self.assertEqual(st.status_code, 200)
        data = st.get_json()["data"]
        self.assertFalse(data["update_available"])
        self.assertEqual(data["progress_step"], "idle")
        pr = self.client.get("/api/update/progress")
        self.assertEqual(pr.status_code, 200)
        self.assertEqual(pr.get_json()["data"]["percent"], 0)

    def test_api_status_still_json(self):
        from core.app_context import AppContext

        AppContext.reset_instance()
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["state"], "UNKNOWN")

    def test_frontend_http_poll_removed(self):
        r = self.client.get("/api/frontend")
        self.assertEqual(r.status_code, 404)


class TestDeviceStatusShape(unittest.TestCase):
    def test_collect_device_status_keys(self):
        from services.frontend_mqtt import collect_device_status

        ctx = MagicMock()
        ctx.settings.rfid_config.return_value = {
            "ip": "192.168.63.87",
            "port": "5084",
        }
        ctx.rfid_reader.get_status.return_value = {
            "type": "tcp",
            "running": True,
            "connected": True,
        }
        ctx.io.get_status.return_value = {
            "type": "demo",
            "connected": True,
            "host": None,
        }
        ctx.sensor_poller.get_status.return_value = {
            "entry_occupied_latch": True,
        }
        ctx.traffic_light.get_status.return_value = {"state": "red"}
        ctx.boom_barrier.get_status.return_value = {"state": "closed"}

        with patch("services.frontend_mqtt._host_pings", return_value=True):
            devices = collect_device_status(ctx)
        self.assertTrue(devices["sensors"]["s1"])
        self.assertTrue(devices["sensors"]["connected"])
        self.assertEqual(devices["traffic_light"]["color"], "RED")
        self.assertEqual(devices["boom_barrier"]["position"], "Closed")
        self.assertTrue(devices["traffic_light"]["connected"])
        self.assertTrue(devices["rfid_reader"]["connected"])
        self.assertNotIn("digitizer", devices)
        self.assertNotIn("traffic_light_exit", devices)

        ctx.settings.rfid_config.return_value = {}
        ctx.rfid_reader.get_status.return_value = {"type": "api", "running": True}
        offline = collect_device_status(ctx)
        self.assertFalse(offline["rfid_reader"]["connected"])
        self.assertEqual(offline["rfid_reader"]["port"], "N/A")

    def test_io_disconnected_marks_dependents_disconnected(self):
        from services.frontend_mqtt import collect_device_status

        ctx = MagicMock()
        ctx.settings.rfid_config.return_value = {
            "ip": "192.168.63.87",
            "port": "5084",
        }
        ctx.rfid_reader.get_status.return_value = {"type": "api", "running": True}
        ctx.io.get_status.return_value = {
            "type": "modbus",
            "connected": False,
            "host": "192.168.1.50",
        }
        ctx.sensor_poller.get_status.return_value = {
            "entry_occupied_latch": True,
        }
        ctx.traffic_light.get_status.return_value = {"state": "green"}
        ctx.boom_barrier.get_status.return_value = {"state": "open"}

        with patch("services.frontend_mqtt._host_pings", return_value=False):
            devices = collect_device_status(ctx)
        self.assertFalse(devices["io_controller"]["connected"])
        self.assertFalse(devices["sensors"]["connected"])
        self.assertFalse(devices["sensors"]["s1"])
        self.assertFalse(devices["traffic_light"]["connected"])
        self.assertFalse(devices["boom_barrier"]["connected"])
        self.assertEqual(devices["traffic_light"]["color"], "")
        self.assertEqual(devices["boom_barrier"]["position"], "")
        self.assertFalse(devices["rfid_reader"]["connected"])


class TestFrontendSnapshotFromFsm(unittest.TestCase):
    def test_maps_rfid_and_crossing(self):
        from config.constants import Event
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from services.frontend_mqtt import build_frontend_snapshot

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.transactions.current.validated_rfid = "e200001d"
        ctx.transactions.current.vehicle_no = "OD14P7339"
        snap = build_frontend_snapshot(ctx)
        self.assertEqual(snap["position"], -1)
        self.assertEqual(snap["status"]["step"], "rfid_read")

        ctx.state_machine.trigger(Event.RFID_RECEIVED)
        snap = build_frontend_snapshot(ctx)
        self.assertEqual(snap["position"], 0)
        self.assertEqual(snap["status"]["step"], "rfid_read")

        ctx.state_machine.trigger(Event.RFID_RECEIVED)
        ctx.state_machine.trigger(Event.RFID_VALID)
        ctx.state_machine.trigger(Event.ANPR_MATCH)
        snap = build_frontend_snapshot(ctx)
        self.assertEqual(snap["position"], 2)
        self.assertEqual(snap["status"]["step"], "entry_granted")
        self.assertEqual(snap["rfid"]["truck_number"], "OD14P7339")


class TestMqttWsBroker(unittest.TestCase):
    def test_topic_match_and_publish_packet(self):
        from services.mqtt_ws_broker import encode_publish, topic_matches

        self.assertTrue(topic_matches("wb_frontend/position", "wb_frontend/position"))
        self.assertTrue(topic_matches("wb_frontend/#", "wb_frontend/position"))
        self.assertFalse(topic_matches("wb_frontend/display", "wb_frontend/position"))
        pkt = encode_publish("wb_frontend/position", b"-1", qos=0)
        self.assertEqual(pkt[0] >> 4, 3)
        self.assertIn(b"wb_frontend/position", pkt)
        self.assertTrue(pkt.endswith(b"-1"))
        retained = encode_publish("wb_frontend/device_status", b"{}", qos=0, retain=True)
        self.assertEqual(retained[0] & 0x01, 0x01)


if __name__ == "__main__":
    unittest.main()
