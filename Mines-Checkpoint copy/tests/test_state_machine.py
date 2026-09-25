"""Unit tests for Mines Entry state machine and workflow helpers."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is on path
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.constants import Event, State, TIMEOUTS
from core.state_machine import StateMachine
from core.transaction import Transaction
from core.app_context import AppContext
from core.workflow import CheckpointWorkflow
from hardware.rfid_reader import extract_id_hexes
from services.oci_client import OCIResponse, parse_truck_details


class TestExtractIdHexes(unittest.TestCase):
    def test_list_payload(self):
        payload = [
            {"data": {"idHex": "aaa"}, "type": "CUSTOM"},
            {"data": {"idHex": "bbb"}, "type": "CUSTOM"},
            {"data": {"idHex": "aaa"}, "type": "CUSTOM"},
        ]
        self.assertEqual(extract_id_hexes(payload), ["aaa", "bbb"])

    def test_empty(self):
        self.assertEqual(extract_id_hexes([]), [])
        self.assertEqual(extract_id_hexes({}), [])


class TestParseTruckDetails(unittest.TestCase):
    def test_pipe_string(self):
        s = "T|34161060000000000020444|OD05CA3273|12500|45000|500|TRIP-20260715-001|192.168.10.223"
        p = parse_truck_details(s)
        self.assertEqual(p["rfid"], "34161060000000000020444")
        self.assertEqual(p["vehicle_no"], "OD05CA3273")
        self.assertEqual(p["token_no"], "TRIP-20260715-001")
        self.assertEqual(p["device_ip"], "192.168.10.223")


class TestStateMachine(unittest.TestCase):
    def test_happy_path_transitions(self):
        sm = StateMachine()
        self.assertEqual(sm.current_state, State.IDLE)
        self.assertTrue(sm.trigger(Event.RFID_RECEIVED))
        self.assertEqual(sm.current_state, State.RFID_READ)
        self.assertTrue(sm.trigger(Event.RFID_RECEIVED))
        self.assertEqual(sm.current_state, State.RFID_VALIDATE)
        self.assertTrue(sm.trigger(Event.RFID_VALID))
        self.assertEqual(sm.current_state, State.DISPLAY_TRUCK)
        self.assertTrue(sm.trigger(Event.ANPR_MATCH))
        self.assertEqual(sm.current_state, State.ENTRY_GRANTED)
        self.assertTrue(sm.trigger(Event.ENTRY_OPENED))
        self.assertEqual(sm.current_state, State.WAIT_CROSSING)
        self.assertTrue(sm.trigger(Event.EXIT_SENSOR))
        self.assertEqual(sm.current_state, State.IDLE)

    def test_rfid_error_path(self):
        sm = StateMachine()
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_INVALID)
        self.assertEqual(sm.current_state, State.RFID_ERROR)
        sm.trigger(Event.RFID_ERROR_TIMEOUT)
        self.assertEqual(sm.current_state, State.IDLE)

    def test_manual_loop_to_grant(self):
        sm = StateMachine()
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_VALID)
        sm.trigger(Event.ANPR_MISMATCH)
        self.assertEqual(sm.current_state, State.MANUAL_UPDATE)
        sm.trigger(Event.UPDATE_STATUS_0)
        self.assertEqual(sm.current_state, State.MANUAL_UPDATE)
        sm.trigger(Event.UPDATE_STATUS_1)
        self.assertEqual(sm.current_state, State.ENTRY_GRANTED)

    def test_manual_status_2_reset(self):
        sm = StateMachine()
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_VALID)
        sm.trigger(Event.ANPR_MISMATCH)
        sm.trigger(Event.UPDATE_STATUS_2)
        self.assertEqual(sm.current_state, State.IDLE)

    def test_invalid_transition_ignored(self):
        sm = StateMachine()
        self.assertFalse(sm.trigger(Event.ANPR_MATCH))
        self.assertEqual(sm.current_state, State.IDLE)


class TestWorkflowWithMocks(unittest.TestCase):
    def setUp(self):
        AppContext.reset_instance()
        self.ctx = AppContext.get_instance()
        self.ctx.state_machine = StateMachine()
        self.ctx.transactions = __import__(
            "core.transaction", fromlist=["TransactionStore"]
        ).TransactionStore()

        settings = MagicMock()
        settings.device_ip = "192.168.10.223"
        settings.demo_mode = True
        self.ctx.settings = settings

        self.display = MagicMock()
        self.tl = MagicMock()
        self.boom = MagicMock()
        self.ctx.display = self.display
        self.ctx.traffic_light = self.tl
        self.ctx.boom_barrier = self.boom

        self.oci = MagicMock()
        self.ctx.oci = self.oci
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        self.ctx.rfid_cloud = MagicMock()
        self.ctx.rfid_cloud.prepare_idle.return_value = True
        self.ctx.rfid_cloud.stop.return_value = True
        self.workflow = CheckpointWorkflow(self.ctx)
        self.ctx.workflow = self.workflow

        # Speed up sleeps in workflow
        self._sleep_patch = patch("core.workflow.time.sleep", return_value=None)
        self._sleep_patch.start()

    def tearDown(self):
        self.workflow._cancel_crossing_timer()
        self._sleep_patch.stop()
        AppContext.reset_instance()

    def test_rfid_fail_shows_error(self):
        self.oci.validate_rfid.return_value = OCIResponse(
            ok=False, status=500, message="fail"
        )
        self.workflow.on_rfid_tags(["badtag"])
        # Wait for background RFIDCycle thread to finish (not a fixed sleep)
        deadline = time.time() + 2.0
        saw_err = False
        while time.time() < deadline:
            try:
                self.display.send.assert_any_call("RFID ERR 1")
                saw_err = True
                break
            except AssertionError:
                time.sleep(0.05)
        self.assertTrue(saw_err, "Expected display.send('RFID ERR 1') from RFID fail path")
        while time.time() < deadline:
            if self.ctx.state_machine.current_state == State.IDLE:
                break
            time.sleep(0.05)
        self.assertEqual(self.ctx.state_machine.current_state, State.IDLE)
        self.oci.validate_rfid.assert_called()

    def test_anpr_success_grants_entry(self):
        self.oci.validate_rfid.return_value = OCIResponse(
            ok=True,
            status=200,
            message="ok",
            truck_details="T|34161060000000000020444|GJXXAEXX4178|12500|45000|500|TOK1|192.168.10.223",
        )
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, message="match", raw={"anpr_status": 1}
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.workflow.on_rfid_tags(["34161060000000000020444"])
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self.ctx.state_machine.current_state == State.WAIT_CROSSING:
                break
            time.sleep(0.05)
        self.boom.open.assert_called()
        self.tl.set_green.assert_called()
        self.assertEqual(
            self.ctx.state_machine.current_state, State.WAIT_CROSSING
        )
        # exit sensor resets; boom close is deferred by BOOM_CLOSE_DELAY_SEC
        self.boom.close.reset_mock()
        self.workflow.on_exit_sensor()
        self.assertEqual(self.ctx.state_machine.current_state, State.IDLE)
        self.boom.close.assert_not_called()
        self.workflow._boom_close_timer.function()
        self.boom.close.assert_called()

    def test_manual_loop_status_0_then_1(self):
        self.oci.validate_rfid.return_value = OCIResponse(
            ok=True,
            status=200,
            truck_details="T|rfid1|OD05CA3273|1|2|3|TOK|192.168.10.223",
        )
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw={"status": 0}
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.side_effect = [
            OCIResponse(ok=False, status=0, raw={"vehicleStatus": 0}),
            OCIResponse(ok=True, status=1, raw={"vehicleStatus": 1}),
        ]
        settings = self.ctx.settings
        settings.truck_anpr_retry_timer = 0.01
        self.workflow.on_rfid_tags(["rfid1"])
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self.ctx.state_machine.current_state == State.WAIT_CROSSING:
                break
            time.sleep(0.05)
        self.display.send.assert_any_call("ANPR ERR 1")
        self.assertEqual(
            self.ctx.state_machine.current_state, State.WAIT_CROSSING
        )
        self.assertGreaterEqual(self.oci.update_truck_number.call_count, 2)

    def test_manual_status_2_resets(self):
        self.oci.validate_rfid.return_value = OCIResponse(
            ok=True,
            status=200,
            truck_details="T|rfid1|OD05CA3273|1|2|3|TOK|192.168.10.223",
        )
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw={"status": 0}
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=False, status=2, raw={"vehicleStatus": 2}
        )
        settings = self.ctx.settings
        settings.truck_anpr_retry_timer = 0.01
        self.workflow.on_rfid_tags(["rfid1"])
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self.ctx.state_machine.current_state == State.IDLE:
                break
            time.sleep(0.05)
        self.assertEqual(self.ctx.state_machine.current_state, State.IDLE)


class TestTransaction(unittest.TestCase):
    def test_start_clear(self):
        t = Transaction()
        t.start(["a", "b"])
        self.assertEqual(t.rfid_tags, ["a", "b"])
        self.assertIsNotNone(t.started_at)
        t.clear()
        self.assertEqual(t.rfid_tags, [])


if __name__ == "__main__":
    unittest.main()
