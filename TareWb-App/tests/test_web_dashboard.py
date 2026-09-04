"""Operator web dashboard HTTP + MQTT payload tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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
        self.assertIn("Weighbridge", body)
        self.assertIn("<h1>Weighbridge</h1>", body)
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
        self.assertNotIn("View Animation", body)
        self.assertLess(
            body.find('data-step="vehicle_entering"'),
            body.find('data-step="reading_weight"'),
        )
        self.assertLess(
            body.find('data-step="reading_weight"'),
            body.find('data-step="rfid_read"'),
        )
        self.assertIn('data-step="validating_anpr"', body)
        self.assertIn('id="weight-value"', body)
        self.assertIn("RFID / ANPR / Weight", body)

    def test_animated_html(self):
        r = self.client.get("/animated.html")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("animation-container", body)
        self.assertIn("/static/images/truck.png", body)

    def test_static_css_and_paho(self):
        css = self.client.get("/static/css/style.css")
        self.assertEqual(css.status_code, 200)
        css_body = css.get_data(as_text=True)
        self.assertIn("api-alert-popup", css_body)
        self.assertIn("step-warning-blink", css_body)
        self.assertIn("state-warning", css_body)
        self.assertIn(".flow-step.state-error .step-content", css_body)
        self.assertIn("--font-size-base", css_body)
        paho = self.client.get("/static/js/paho-mqtt.js")
        self.assertEqual(paho.status_code, 200)
        truck = self.client.get("/static/images/truck.png")
        self.assertEqual(truck.status_code, 200)

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

    def test_health_status(self):
        r = self.client.get("/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], 200)

    def test_api_status_still_json(self):
        from core.app_context import AppContext

        AppContext.reset_instance()
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["service"], "GMDC Tare Weighbridge")

    def test_camera_stream_optional(self):
        r = self.client.get("/api/camera/stream")
        self.assertEqual(r.status_code, 404)

    def test_frontend_http_poll_removed(self):
        r = self.client.get("/api/frontend")
        self.assertEqual(r.status_code, 404)

    def test_dashboard_js_uses_mqtt_host_from_page(self):
        js = self.client.get("/static/js/app.js")
        self.assertEqual(js.status_code, 200)
        body = js.get_data(as_text=True)
        self.assertIn("window.location.hostname", body)
        self.assertNotIn("/api/frontend", body)
        self.assertIn("formatWeightTonKg", body)
        self.assertIn("showApiAlert", body)
        self.assertIn("initApiAlertPopup", body)
        self.assertIn("fetch('/api/reset'", body)
        self.assertNotIn("wb_frontend/reset_application", body)
        self.assertIn("ioDependentsDisconnected", body)
        self.assertIn("failedFromStep", body)
        self.assertIn("markFailureCascade", body)

    def test_ui_reset_endpoint_plays_application_reset(self):
        from core.app_context import AppContext

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        wf = MagicMock()
        ctx.workflow = wf
        try:
            r = self.client.post("/api/reset")
            self.assertEqual(r.status_code, 200)
            wf.force_reset.assert_called_once_with(announce_reset=True)
        finally:
            AppContext.reset_instance()
        anim = self.client.get("/static/js/animated.js")
        self.assertEqual(anim.status_code, 200)
        self.assertNotIn("/api/frontend", anim.get_data(as_text=True))


class TestDeviceStatusShape(unittest.TestCase):
    def test_collect_device_status_keys(self):
        from services.frontend_mqtt import collect_device_status

        ctx = MagicMock()
        ctx.settings.rfid_config.return_value = {
            "ip": "192.168.1.10",
            "port": "5084",
        }
        ctx.settings.digitizer_url = "http://127.0.0.1:8100/read_stable_weight"
        ctx.rfid_reader.get_status.return_value = {"type": "api", "running": True}
        ctx.digitizer.demo_mode = True
        ctx.io.get_status.return_value = {
            "type": "demo",
            "connected": True,
            "host": None,
        }
        ctx.sensor_poller.get_status.return_value = {
            "entry_occupied_latch": True,
            "wb_occupied_latch": False,
            "exit_occupied_latch": False,
        }
        ctx.entry_tl.get_status.return_value = {"state": "green"}
        ctx.exit_tl.get_status.return_value = {"state": "red"}
        ctx.entry_boom.get_status.return_value = {"state": "open"}
        ctx.exit_boom.get_status.return_value = {"state": "closed"}

        devices = collect_device_status(ctx)
        self.assertTrue(devices["sensors"]["s1"])
        self.assertFalse(devices["sensors"]["s2"])
        self.assertTrue(devices["sensors"]["connected"])
        self.assertEqual(devices["traffic_light_entry"]["color"], "GREEN")
        self.assertEqual(devices["traffic_light_exit"]["color"], "RED")
        self.assertEqual(devices["boom_barrier_entry"]["position"], "Open")
        self.assertEqual(devices["boom_barrier_exit"]["position"], "Closed")
        self.assertTrue(devices["traffic_light_entry"]["connected"])
        self.assertTrue(devices["boom_barrier_entry"]["connected"])

    def test_io_disconnected_marks_dependents_disconnected(self):
        from services.frontend_mqtt import collect_device_status

        ctx = MagicMock()
        ctx.settings.rfid_config.return_value = {"ip": "192.168.1.10", "port": "5084"}
        ctx.settings.digitizer_url = "http://127.0.0.1:8100/read_stable_weight"
        ctx.rfid_reader.get_status.return_value = {"type": "api", "running": True}
        ctx.digitizer.demo_mode = True
        ctx.io.get_status.return_value = {
            "type": "modbus",
            "connected": False,
            "host": "192.168.1.50",
            "port": 502,
        }
        ctx.sensor_poller.get_status.return_value = {
            "entry_occupied_latch": True,
            "wb_occupied_latch": True,
            "exit_occupied_latch": True,
        }
        ctx.entry_tl.get_status.return_value = {"state": "green"}
        ctx.exit_tl.get_status.return_value = {"state": "red"}
        ctx.entry_boom.get_status.return_value = {"state": "open"}
        ctx.exit_boom.get_status.return_value = {"state": "closed"}

        devices = collect_device_status(ctx)
        self.assertFalse(devices["io_controller"]["connected"])
        self.assertFalse(devices["sensors"]["connected"])
        self.assertFalse(devices["sensors"]["s1"])
        self.assertFalse(devices["sensors"]["s2"])
        self.assertFalse(devices["sensors"]["s3"])
        self.assertFalse(devices["traffic_light_entry"]["connected"])
        self.assertFalse(devices["traffic_light_exit"]["connected"])
        self.assertFalse(devices["boom_barrier_entry"]["connected"])
        self.assertFalse(devices["boom_barrier_exit"]["connected"])
        self.assertEqual(devices["traffic_light_entry"]["color"], "")
        self.assertEqual(devices["boom_barrier_entry"]["position"], "")
        self.assertTrue(devices["rfid_reader"]["connected"])
        self.assertTrue(devices["digitizer"]["connected"])


class TestFrontendPublishOnWorkflow(unittest.TestCase):
    def test_positioning_publishes_step(self):
        from config.constants import Event, State
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import TareWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.settings = MagicMock()
        ctx.settings.is_bidirectional.return_value = False
        ctx.display = MagicMock()
        fe = MagicMock()
        ctx.frontend = fe
        wf = TareWbWorkflow(ctx)
        wf._begin_vehicle_positioning("ENTRY_A")
        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)
        fe.publish_position.assert_called_with(1)
        fe.publish_status.assert_called()
        step = fe.publish_status.call_args[0][0]
        self.assertEqual(step, "vehicle_entering")
        ctx.state_machine.trigger(Event.RESET)


class TestFrontendSnapshotFromFsm(unittest.TestCase):
    def test_maps_positioning_and_weight(self):
        from config.constants import Event, State
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from services.frontend_mqtt import build_frontend_snapshot

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.transactions.weight_kg = 12500
        ctx.transactions.rfid = "D2030DBE"
        ctx.transactions.vehicle_no = "OD14AE3900"
        snap = build_frontend_snapshot(ctx)
        self.assertEqual(snap["position"], -1)

        ctx.state_machine.trigger(Event.ENTRY_SENSOR)
        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)
        snap = build_frontend_snapshot(ctx)
        self.assertEqual(snap["position"], 1)
        self.assertEqual(snap["status"]["step"], "vehicle_entering")

        ctx.state_machine.trigger(Event.WB_SENSOR)
        snap = build_frontend_snapshot(ctx)
        self.assertEqual(snap["position"], 2)
        self.assertEqual(snap["digitizer"], "12500")
        self.assertEqual(snap["rfid"]["truck_number"], "OD14AE3900")


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


class TestFreePass(unittest.TestCase):
    def test_opens_all_barriers_then_exit_resets_idle(self):
        from config.constants import State
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import TareWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.settings = MagicMock()
        ctx.settings.is_bidirectional.return_value = False
        ctx.display = MagicMock()
        ctx.entry_tl = MagicMock()
        ctx.exit_tl = MagicMock()
        ctx.entry_boom = MagicMock()
        ctx.exit_boom = MagicMock()
        ctx.frontend = MagicMock()
        ctx.sensor_poller = MagicMock()
        wf = TareWbWorkflow(ctx)

        wf.start_free_pass()
        self.assertEqual(ctx.state_machine.current_state, State.FREE_PASS)
        ctx.entry_tl.set_green.assert_called()
        ctx.exit_tl.set_green.assert_called()
        ctx.entry_boom.open.assert_called()
        ctx.exit_boom.open.assert_called()
        ctx.frontend.publish_display.assert_called_with("FREE PASS")

        wf.on_entry_occupied()
        self.assertEqual(ctx.state_machine.current_state, State.FREE_PASS)

        wf.on_exit_occupied()
        self.assertEqual(ctx.state_machine.current_state, State.FREE_PASS)

        wf.on_exit_cleared()
        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        ctx.exit_tl.set_red.assert_called()


class TestOperatorLogin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.server import create_app

        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_login_success(self):
        r = self.client.post(
            "/api/login",
            json={"username": "admin", "password": "gmdc@123"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], 200)

    def test_login_rejects_bad_password(self):
        r = self.client.post(
            "/api/login",
            json={"username": "admin", "password": "wrong"},
        )
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
