"""Display LED message format checks (Mines-WB)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config.constants import (
    MSG_ANPR_API_ERR,
    MSG_ANPR_ERR,
    MSG_ANPR_ERR_2,
    MSG_IDLE,
    MSG_RFID_ERR,
    MSG_RFID_OK_FMT,
    MSG_WEIGHT_DETAILS_FMT,
    MSG_WEIGHING_FMT,
)
from core.workflow import MinesWbWorkflow


class DisplayMessageTests(unittest.TestCase):
    def test_message_constants(self):
        self.assertEqual(MSG_IDLE, "Enter The@Vehicle")
        self.assertEqual(MSG_RFID_ERR, "RFID ERR@ASK OPERATOR")
        self.assertEqual(MSG_RFID_OK_FMT.format(truck="OD14AE3900", weight=15000), "OD14AE3900@15000 Kg")
        self.assertEqual(MSG_ANPR_API_ERR, "ANPR ERROR@ASK OPERATOR")
        self.assertEqual(MSG_ANPR_ERR, "ANPR ERROR@ERR-0")
        self.assertEqual(MSG_ANPR_ERR_2, "ANPR ERROR@ERR-2")
        self.assertEqual(MSG_WEIGHING_FMT.format(weight=15250), "Checking Weight@15250")
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
        wf._announce("Enter The@Vehicle")
        ctx.display.send.assert_called_once_with("Enter The@Vehicle")
        ctx.frontend.publish_display.assert_called_once_with("Enter The@Vehicle")


if __name__ == "__main__":
    unittest.main()
