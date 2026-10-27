"""Display LED message format checks (Mines-WB)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config.constants import (
    MSG_ANPR_API_ERR,
    MSG_ANPR_ERR,
    MSG_ANPR_ERR_2,
    MSG_IDLE,
    MSG_INVALID_WEIGHT,
    MSG_RFID_ERR,
    MSG_RFID_OK_FMT,
    MSG_WEIGHT_DETAILS_FMT,
    MSG_WEIGHING_FMT,
    State,
)
from core.state_machine import StateMachine
from core.workflow import MinesWbWorkflow


class DisplayMessageTests(unittest.TestCase):
    def test_message_constants(self):
        self.assertEqual(MSG_IDLE, "Enter@Vehicle")
        self.assertEqual(MSG_INVALID_WEIGHT, "Invalid Weight")
        self.assertEqual(MSG_RFID_OK_FMT.format(truck="OD14AE3900", weight=15000), "OD14AE3900@15000 Kg")
        self.assertEqual(MSG_WEIGHING_FMT.format(weight=15250), "Tare Weight@15250")
        self.assertEqual(
            MSG_WEIGHT_DETAILS_FMT.format(truck="OD14AE3900", weight=15250),
            "OD14AE3900 Weight@15250 Kg",
        )

    def test_rfid_ok_tare_uses_unladen_rto_tare(self):
        from services.oci_client import parse_truck_details

        wf = MinesWbWorkflow.__new__(MinesWbWorkflow)
        parsed = parse_truck_details(
            "T|RFID1|OD14AE3900|45000|15000|500|TOKEN|10.0.0.1"
        )
        txn = MagicMock(vehicle_no="OD14AE3900", rfid="RFID1", weight_kg=14800.0)
        self.assertEqual(wf._rfid_ok_display(parsed, txn), "OD14AE3900@15000 Kg")

    def test_rfid_ok_gross_uses_laden_rto_gross(self):
        from services.oci_client import parse_truck_details

        wf = MinesWbWorkflow.__new__(MinesWbWorkflow)
        parsed = parse_truck_details(
            "G|RFID1|OD14P7339|45000|26000|500|TOKEN|10.0.0.1"
        )
        txn = MagicMock(vehicle_no="OD14P7339", rfid="RFID1", weight_kg=44000.0)
        self.assertEqual(wf._rfid_ok_display(parsed, txn), "OD14P7339@45000 Kg")

    def test_rfid_ok_vadhghat_uses_laden_rto_gross(self):
        from services.oci_client import parse_truck_details

        wf = MinesWbWorkflow.__new__(MinesWbWorkflow)
        parsed = parse_truck_details(
            "V|RFID1|OD14P7339|45000|24500|50|TOKEN|10.0.0.1"
        )
        txn = MagicMock(vehicle_no="OD14P7339", rfid="RFID1", weight_kg=44750.0)
        self.assertEqual(wf._rfid_ok_display(parsed, txn), "OD14P7339@45000 Kg")

    def test_rfid_api_message_is_sent_to_the_display(self):
        from services.oci_client import OCIResponse

        wf = MinesWbWorkflow.__new__(MinesWbWorkflow)
        shown = wf._rfid_api_display(
            OCIResponse(
                ok=False,
                status=403,
                message="No loading slip is available against the RFID.",
            ),
            MSG_RFID_ERR,
        )
        self.assertEqual(shown, "No loading slip is available against the RFID.")
        generic = wf._rfid_api_display(
            OCIResponse(ok=True, status=200, message="ok"),
            "OD14AE3900@15000 Kg",
        )
        self.assertEqual(generic, "OD14AE3900@15000 Kg")

    def test_announce_sends_led_and_frontend(self):
        ctx = MagicMock()
        ctx.display = MagicMock()
        ctx.frontend = MagicMock()
        wf = MinesWbWorkflow.__new__(MinesWbWorkflow)
        wf.ctx = ctx
        wf._announce(MSG_IDLE)
        ctx.display.send.assert_called_once_with(MSG_IDLE, side=None)
        ctx.frontend.publish_display.assert_called_once_with(MSG_IDLE)


def _run_weight_capture(weight, min_kg=5000, live_after=None):
    ctx = MagicMock()
    ctx.settings.min_weight_kg = min_kg
    ctx.settings.wb_type = "unidirectional"
    ctx.settings.device_ip = "10.0.0.1"
    ctx.rfid_clouds = {}
    ctx.rfid_cloud = None
    ctx.sensor_poller = None
    ctx.state_machine = StateMachine()
    ctx.state_machine.force_state(State.VEHICLE_POSITIONING)
    ctx.digitizer.read_stable_weight.return_value = {"ok": True, "weight": weight}
    ctx.digitizer.supports_live_weight.return_value = live_after is not None
    ctx.digitizer.get_current_weight.return_value = live_after
    wf = MinesWbWorkflow(ctx)
    wf._weight_capture_cycle()
    return ctx, wf


class WeightDisplayTests(unittest.TestCase):
    def test_below_min_weight_waits_until_zero_then_idle(self):
        ctx, _wf = _run_weight_capture(3000, live_after=0.0)
        ctx.display.send.assert_any_call(MSG_INVALID_WEIGHT, side=None)
        ctx.frontend.publish_display.assert_any_call(MSG_INVALID_WEIGHT)
        ctx.voice.weight_error.assert_not_called()
        ctx.display.send.assert_called_with(MSG_IDLE, side=None)
        self.assertEqual(ctx.state_machine.current_state, State.IDLE)

    def test_below_min_weight_loops_error_until_zero(self):
        ctx = MagicMock()
        ctx.settings.min_weight_kg = 5000
        ctx.settings.wb_type = "unidirectional"
        ctx.settings.device_ip = "10.0.0.1"
        ctx.rfid_clouds = {}
        ctx.rfid_cloud = None
        ctx.sensor_poller = None
        ctx.state_machine = StateMachine()
        ctx.state_machine.force_state(State.VEHICLE_POSITIONING)
        ctx.digitizer.read_stable_weight.return_value = {"ok": True, "weight": 3000}
        ctx.digitizer.supports_live_weight.return_value = True
        ctx.digitizer.get_current_weight.side_effect = [2500.0, 1200.0, 0.0]
        wf = MinesWbWorkflow(ctx)
        wf._weight_capture_cycle()
        self.assertEqual(ctx.voice.weight_error.call_count, 2)
        ctx.display.send.assert_any_call(MSG_INVALID_WEIGHT, side=None)
        ctx.display.send.assert_called_with(MSG_IDLE, side=None)
        self.assertEqual(ctx.state_machine.current_state, State.IDLE)

    def test_above_min_weight_shows_current_weight(self):
        ctx, _wf = _run_weight_capture(15000)
        ctx.display.send.assert_called_with("Tare Weight@15000", side=None)
        ctx.frontend.publish_display.assert_called_with("Tare Weight@15000")
        self.assertEqual(ctx.state_machine.current_state, State.RFID_READ)


if __name__ == "__main__":
    unittest.main()
