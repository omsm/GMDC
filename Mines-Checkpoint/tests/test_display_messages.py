"""Display LED message format checks (Checkpoint)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config.constants import (
    MSG_ANPR_API_ERR,
    MSG_ANPR_ERR,
    MSG_ANPR_ERR_2,
    MSG_ENTRY_GRANTED_FMT,
    MSG_IDLE,
    MSG_RFID_ERR,
    MSG_RFID_OK_FMT,
)
from core.workflow import CheckpointWorkflow


class DisplayMessageTests(unittest.TestCase):
    def test_message_constants(self):
        self.assertEqual(MSG_IDLE, "Scan@RFID Card")
        self.assertEqual(MSG_RFID_ERR, "RFID ERR@ASK OPERATOR")
        self.assertEqual(MSG_RFID_OK_FMT.format(truck="OD14P7339"), "RFID VALID@OD14P7339")
        self.assertEqual(MSG_ANPR_API_ERR, "ANPR ERROR@ASK OPERATOR")
        self.assertEqual(MSG_ANPR_ERR, "ANPR ERROR@ERR-0")
        self.assertEqual(MSG_ANPR_ERR_2, "ANPR ERROR@ERR-2")
        self.assertEqual(
            MSG_ENTRY_GRANTED_FMT.format(truck="OD14P7339"),
            "Granted OD14P7339@Thank You",
        )

    def test_announce_sends_led_and_frontend(self):
        ctx = MagicMock()
        ctx.display = MagicMock()
        ctx.frontend = MagicMock()
        wf = CheckpointWorkflow(ctx)
        wf._announce("RFID ERR@ASK OPERATOR")
        ctx.display.send.assert_called_once_with("RFID ERR@ASK OPERATOR")
        ctx.frontend.publish_display.assert_called_once_with("RFID ERR@ASK OPERATOR")

    def test_rfid_api_message_is_sent_to_the_display(self):
        from services.oci_client import OCIResponse

        ctx = MagicMock()
        wf = CheckpointWorkflow(ctx)
        shown = wf._rfid_api_display(
            OCIResponse(ok=False, status=400, message="Tag not registered"),
            MSG_RFID_ERR,
        )
        self.assertEqual(shown, "Tag not registered")
        generic = wf._rfid_api_display(
            OCIResponse(ok=True, status=200, message="ok"),
            "RFID VALID@OD14P7339",
        )
        self.assertEqual(generic, "RFID VALID@OD14P7339")

    def test_idle_hardware_shows_idle_message(self):
        ctx = MagicMock()
        ctx.traffic_light = MagicMock()
        ctx.boom_barrier = MagicMock()
        ctx.display = MagicMock()
        ctx.frontend = None
        ctx.sensor_poller = None
        wf = CheckpointWorkflow(ctx)
        wf.apply_idle_hardware()
        ctx.display.send.assert_called_with(MSG_IDLE)


if __name__ == "__main__":
    unittest.main()
