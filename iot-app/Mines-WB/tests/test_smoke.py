"""Smoke tests for Mines-WB bootstrap and FSM transitions."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEMO_MODE", "true")


class TestStateMachine(unittest.TestCase):
    def test_idle_to_positioning_to_weight(self):
        from config.constants import Event, State
        from core.state_machine import StateMachine

        sm = StateMachine()
        self.assertEqual(sm.current_state, State.IDLE)
        self.assertTrue(sm.trigger(Event.ENTRY_SENSOR))
        self.assertEqual(sm.current_state, State.VEHICLE_POSITIONING)
        self.assertTrue(sm.trigger(Event.WB_SENSOR))
        self.assertEqual(sm.current_state, State.WEIGHT_CAPTURE)
        self.assertTrue(sm.trigger(Event.WEIGHT_OK))
        self.assertEqual(sm.current_state, State.RFID_READ)


class TestSettings(unittest.TestCase):
    def test_loads_checkpoint_config(self):
        from config.settings import load_settings

        s = load_settings()
        self.assertTrue(s.config_path)
        self.assertEqual(s.checkpoint_type, "weighbridge")
        self.assertTrue(s.digitizer_url.startswith("http"))
        self.assertIn("reset_checkpoint", s.reset_checkpoint_url)
        self.assertIn("vadhghat_weight_adjustment", s.vadhghat_weight_adjustment_url)
        self.assertEqual(
            s.endpoint_auth.get("reset_checkpoint"),
            ("GMDC_API_USERS", "GMDC@123"),
        )


class TestDigitizerDemo(unittest.TestCase):
    def test_demo_weight(self):
        from services.digitizer_client import DigitizerClient

        dig = DigitizerClient("http://127.0.0.1:9/x", demo_mode=True)
        result = dig.read_stable_weight()
        self.assertTrue(result["ok"])
        self.assertEqual(result["weight"], 12500.0)


class TestApiDebugWait(unittest.TestCase):
    def test_waits_after_gmdc_not_anpr(self):
        from unittest.mock import patch

        from services.oci_client import OCIClient

        client = OCIClient(
            base_url="http://example",
            username="u",
            password="p",
            rfid_validate_url="http://example/rfid",
            anpr_detect_url="http://example/anpr",
            invalid_truck_url="http://example/inv",
            update_truck_url="http://example/upd",
            weight_details_url="http://example/wd",
            debug_wait_sec=10.0,
        )
        with patch("services.oci_client.time.sleep") as sleep:
            client._maybe_debug_wait("weight-confirm")
            client._maybe_debug_wait("anpr-detect")
        sleep.assert_called_once_with(10.0)


if __name__ == "__main__":
    unittest.main()
