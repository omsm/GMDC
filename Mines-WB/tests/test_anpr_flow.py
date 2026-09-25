"""ANPR / OCI payload tests for Mines-WB."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEMO_MODE", "true")

from services.oci_client import (  # noqa: E402
    anpr_status_from_raw,
    build_boom_close_payload,
    build_invalid_truck_payload,
    build_status_check_payload,
    build_weight_details_payload,
)


ANPR_RAW = {
    "anpr_status": 0,
    "vehicleNo_web": "OD05CA3273",
    "vehicleNo_anpr": "OD14AH2025",
    "rfid": "D2030DBE",
    "anpr_image": "/path/anpr_crop.jpg",
    "front_image": "/path/front.jpg",
    "matching_score": 30.0,
    "token": "TRIP001",
    "device_ip": "192.168.10.223",
}


class TestPayloadBuilders(unittest.TestCase):
    def test_anpr_status_normalization(self):
        self.assertEqual(anpr_status_from_raw({"anpr_status": 1}), 1)
        self.assertEqual(anpr_status_from_raw({"anpr_status": "2"}), 2)
        self.assertEqual(anpr_status_from_raw({"best_match": {"x": 1}}), 1)
        self.assertEqual(anpr_status_from_raw({}), 0)

    def test_invalid_truck_includes_top_image(self):
        payload = build_invalid_truck_payload(
            ANPR_RAW,
            vehicle_no_web="OD05CA3273",
            rfid="D2030DBE",
            device_ip="192.168.10.223",
            anpr_status=1,
            top_image="tare_TRIP001_OD05CA3273_top.jpg",
        )
        self.assertEqual(payload["anpr_status"], "1")
        self.assertEqual(payload["vehicleNo_web"], "OD05CA3273")
        self.assertEqual(
            payload["top_image"], "tare_TRIP001_OD05CA3273_top.jpg"
        )

    def test_invalid_truck_defaults_top_image_to_error_jpg(self):
        payload = build_invalid_truck_payload(
            ANPR_RAW,
            vehicle_no_web="OD05CA3273",
            rfid="D2030DBE",
            device_ip="192.168.10.223",
            anpr_status=1,
            top_image="",
        )
        self.assertEqual(payload["top_image"], "error.jpg")

    def test_status_check_four_fields(self):
        payload = build_status_check_payload(
            ANPR_RAW,
            vehicle_no_web="OD05CA3273",
            rfid="D2030DBE",
            device_ip="192.168.10.223",
        )
        self.assertEqual(
            set(payload.keys()),
            {"vehicleNo_web", "vehicleNo_anpr", "rfid", "device_ip"},
        )

    def test_boom_close_truck_details_only(self):
        payload = build_boom_close_payload(
            truck_details="T|D2030DBE|OD05CA3273|3000|1000|0|958|IP|OD05CA3273"
        )
        self.assertEqual(list(payload.keys()), ["truck_details"])
        self.assertTrue(payload["truck_details"].startswith("T|"))

    def test_weight_details_shape(self):
        payload = build_weight_details_payload(
            current_weight="24500",
            truck_details="",
            front_image_name="tare_TRIP001_OD05CA3273_front.jpg",
            top_image_name="tare_TRIP001_OD05CA3273_top.jpg",
            anpr_image_name="anpr_TRIP001_OD05CA3273_top.jpg",
        )
        self.assertEqual(payload["current_weight"], "24500")
        self.assertIn("front_image_name", payload)
        self.assertIn("top_image_name", payload)
        self.assertIn("anpr_image_name", payload)

    def test_weight_details_defaults_top_image_name_to_error_jpg(self):
        payload = build_weight_details_payload(
            current_weight="12000",
            truck_details="T|x",
            front_image_name="front.jpg",
            top_image_name="",
            anpr_image_name="anpr.jpg",
        )
        self.assertEqual(payload["top_image_name"], "error.jpg")


class TestAnprBranchWorkflow(unittest.TestCase):
    def _make_workflow(self):
        from config.constants import State
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import MinesWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = MagicMock()
        ctx.settings.device_ip = "192.168.10.223"
        ctx.settings.anpr_enabled = True
        ctx.settings.truck_anpr_retry_timer = 0.01
        ctx.settings.top_camera_rtsp_url = ""
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.transactions.rfid = "D2030DBE"
        ctx.transactions.vehicle_no = "OD05CA3273"
        ctx.transactions.truck_details = (
            "T|D2030DBE|OD05CA3273|45000|24500|500|TRIP001|IP|OD05CA3273"
        )
        ctx.oci = MagicMock()
        from services.oci_client import OCIResponse
        ctx.oci.reset_checkpoint.return_value = OCIResponse(
            ok=True, status=200, http_status=200
        )
        ctx.digitizer = MagicMock()
        ctx.digitizer.read_stable_weight.return_value = {
            "ok": True,
            "weight": 24500.0,
        }
        ctx.display = MagicMock()
        ctx.voice = None
        ctx.entry_tl = MagicMock()
        ctx.exit_tl = MagicMock()
        ctx.entry_boom = MagicMock()
        ctx.exit_boom = MagicMock()
        # Start from ANPR_VALIDATE as after RFID_VALID
        ctx.state_machine.force_state(State.ANPR_VALIDATE)
        return MinesWbWorkflow(ctx), ctx

    def test_anpr_status_1_weight_details_then_dynamic_boom_close(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        ctx.oci.invalid_truck_number.assert_called()
        ctx.oci.update_truck_number.assert_not_called()
        self.assertEqual(ctx.oci.boom_close.call_count, 1)
        td = ctx.oci.boom_close.call_args.kwargs.get("truck_details")
        self.assertEqual(td, ctx.transactions.truck_details)
        self.assertTrue(td.startswith("T|"))
        ctx.oci.weight_details.assert_called()
        wd = ctx.oci.weight_details.call_args.kwargs
        self.assertEqual(wd["current_weight"], "24500")
        self.assertIn("top_image_name", wd)
        top_name = wd["top_image_name"]
        self.assertEqual(top_name, "error.jpg")
        inv = ctx.oci.invalid_truck_number.call_args.kwargs
        self.assertEqual(inv.get("top_image"), top_name)

    def test_anpr_disabled_calls_invalid_truck_then_status_check(self):
        """ANPR off still posts invalid-truck(anpr_status=2) then polls status_check."""
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.settings.anpr_enabled = False
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        ctx.oci.anpr_detect.assert_not_called()
        ctx.oci.invalid_truck_number.assert_called()
        inv = ctx.oci.invalid_truck_number.call_args.kwargs
        self.assertEqual(inv.get("anpr_status"), 2)
        ctx.oci.update_truck_number.assert_called()
        ctx.oci.weight_details.assert_called()

    def test_anpr_status_0_uses_status_check_then_boom_close_filled(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw={**ANPR_RAW, "anpr_status": 0}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        ctx.oci.update_truck_number.assert_called()
        self.assertEqual(ctx.oci.boom_close.call_count, 1)
        td = ctx.oci.boom_close.call_args.kwargs.get("truck_details")
        self.assertTrue(str(td).startswith("T|"))

    def test_anpr_status_0_plays_number_plate_error(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.voice = MagicMock()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw={**ANPR_RAW, "anpr_status": 0}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        ctx.voice.anpr_error.assert_called()
        ctx.voice.tech_issue.assert_not_called()

    def test_anpr_status_2_plays_number_plate_error(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.voice = MagicMock()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=2, raw={**ANPR_RAW, "anpr_status": 2}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        ctx.voice.anpr_error.assert_called()
        ctx.voice.tech_issue.assert_not_called()

    def test_status_check_http_4xx_keeps_anpr_mismatch_warning(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        fe = MagicMock()
        ctx.frontend = fe
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw={**ANPR_RAW, "anpr_status": 0}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.side_effect = [
            OCIResponse(
                ok=False,
                status=0,
                http_status=400,
                kind="http",
                operator_message="Status-check service request failed",
                raw={"message": "Vehicle is not manually updated"},
            ),
            OCIResponse(
                ok=True,
                status=1,
                raw={"vehicleStatus": 1, "statusCode": 200},
            ),
        ]
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        warning_msgs = []
        error_msgs = []
        for call in fe.publish_status.call_args_list:
            args, kwargs = call
            status = args[1] if len(args) > 1 else kwargs.get("status")
            message = args[2] if len(args) > 2 else kwargs.get("message")
            if status == "warning":
                warning_msgs.append(message)
            if status == "error":
                error_msgs.append(message)
        self.assertIn("ANPR Err-0, Number plate mismatch", warning_msgs)
        self.assertNotIn("Status-check service request failed", error_msgs)
        ctx.oci.weight_details.assert_called_once()

    def test_status_code_200_retries_until_vehicle_status_1(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw={**ANPR_RAW, "anpr_status": 0}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.side_effect = [
            OCIResponse(ok=True, status=200, raw={"statusCode": 200}),
            OCIResponse(
                ok=True,
                status=1,
                raw={"statusCode": 200, "vehicleStatus": 1},
            ),
        ]
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        self.assertEqual(ctx.oci.update_truck_number.call_count, 2)
        ctx.oci.weight_details.assert_called_once()

    def test_anpr_status_2_uses_status_check_then_continues_like_status_1(self):
        """anpr_status=2 polls status_check; vehicleStatus=1 follows weight path."""
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=2, raw={**ANPR_RAW, "anpr_status": 2}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        wf._after_rfid_valid()

        ctx.oci.invalid_truck_number.assert_called()
        inv = ctx.oci.invalid_truck_number.call_args.kwargs
        self.assertEqual(inv.get("anpr_status"), 2)
        self.assertEqual(inv.get("top_image"), "error.jpg")
        ctx.oci.update_truck_number.assert_called()
        ctx.oci.weight_details.assert_called_once()
        self.assertEqual(ctx.oci.boom_close.call_count, 1)
        td = ctx.oci.boom_close.call_args.kwargs.get("truck_details")
        self.assertTrue(str(td).startswith("T|"))

    def test_anpr_status_2_abort_on_vehicle_status_2(self):
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=2, raw={**ANPR_RAW, "anpr_status": 2}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=2, raw={"vehicleStatus": 2, "statusCode": 200}
        )

        import core.workflow as wf_mod

        original = wf_mod.TIMEOUTS.UPDATE_STATUS_2_RESET_SEC
        wf_mod.TIMEOUTS.UPDATE_STATUS_2_RESET_SEC = 0.01
        try:
            wf._after_rfid_valid()
        finally:
            wf_mod.TIMEOUTS.UPDATE_STATUS_2_RESET_SEC = original

        ctx.oci.update_truck_number.assert_called()
        ctx.oci.weight_details.assert_not_called()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)
        ctx.exit_boom.open.assert_called()

    def test_anpr_unreachable_publishes_popup_not_raw_exception(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        fe = MagicMock()
        ctx.frontend = fe
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False,
            status=0,
            message=(
                "HTTPConnectionPool(host='localhost', port=5001): Max retries "
                "exceeded with url: /api/detect"
            ),
            http_status=0,
            raw={},
        )

        wf._after_rfid_valid()

        ctx.oci.invalid_truck_number.assert_not_called()
        ctx.oci.weight_details.assert_not_called()
        error_popups = []
        for call in fe.publish_status.call_args_list:
            args, kwargs = call
            status = args[1] if len(args) > 1 else kwargs.get("status")
            message = args[2] if len(args) > 2 else kwargs.get("message")
            if status == "error" and kwargs.get("popup"):
                error_popups.append((message, kwargs.get("popup_title", "")))
        self.assertTrue(error_popups)
        message, title = error_popups[0]
        self.assertEqual(message, "ANPR not reachable")
        self.assertEqual(title, "ANPR NOT REACHABLE")
        self.assertNotIn("HTTPConnectionPool", message)

    def test_manual_reset_without_transaction_skips_reset_api(self):
        wf, ctx = self._make_workflow()
        ctx.transactions.clear()
        ctx.oci.reset_checkpoint.reset_mock()
        wf.force_reset(announce_reset=True)
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_startup_notify_gmdc_reset_skips_when_idle(self):
        wf, ctx = self._make_workflow()
        ctx.transactions.clear()
        ctx.oci.reset_checkpoint.reset_mock()
        wf.notify_gmdc_reset()
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_ui_reset_plays_application_reset_wav(self):
        wf, ctx = self._make_workflow()
        ctx.voice = MagicMock()
        wf.force_reset(announce_reset=True)
        ctx.voice.application_reset.assert_called()
        ctx.voice.stop.assert_not_called()

    def test_automatic_idle_reset_does_not_call_reset_api(self):
        wf, ctx = self._make_workflow()
        ctx.oci.reset_checkpoint.reset_mock()
        wf.force_reset()
        ctx.oci.reset_checkpoint.assert_not_called()
        wf.notify_gmdc_reset()
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_manual_reset_with_transaction_sends_rfid_and_details(self):
        wf, ctx = self._make_workflow()
        wf.force_reset(announce_reset=True)
        kwargs = ctx.oci.reset_checkpoint.call_args.kwargs
        self.assertEqual(kwargs["device_ip"], "192.168.10.223")
        self.assertEqual(kwargs["rfid_no"], "D2030DBE")
        self.assertTrue(str(kwargs["truck_details"]).startswith("T|"))

    def test_successful_exit_after_boom_close_skips_reset_api(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)
        wf._after_rfid_valid()
        ctx.oci.reset_checkpoint.reset_mock()
        wf._complete_lane_exit("vehicle crossed")
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_exit_during_boom_close_wait_skips_reset_api(self):
        """Exit sensor during the post boom-close debug wait must not reset."""
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)

        def _boom_close(**_kwargs):
            wf._complete_lane_exit("exit sensor during boom-close wait")
            return OCIResponse(ok=True, status=200)

        ctx.oci.boom_close.side_effect = _boom_close
        ctx.oci.reset_checkpoint.reset_mock()
        wf._after_rfid_valid()
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_exit_timeout_after_boom_close_skips_reset_api(self):
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        ctx.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        ctx.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)
        wf._after_rfid_valid()
        ctx.state_machine.force_state(State.EXIT_GRANTED)
        ctx.oci.reset_checkpoint.reset_mock()
        wf._on_exit_timeout()
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_anpr_unreachable_exit_does_not_call_reset_api(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow()
        ctx.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, message="down", http_status=0, raw={}
        )
        wf._after_rfid_valid()
        ctx.oci.reset_checkpoint.reset_mock()
        wf._complete_lane_exit("anpr abort")
        ctx.oci.reset_checkpoint.assert_not_called()

    def test_exit_after_rfid_error_publishes_error_not_success(self):
        from config.constants import State

        wf, ctx = self._make_workflow()
        ctx.frontend = MagicMock()
        ctx.state_machine.force_state(State.RFID_ERROR)
        statuses = []

        def _capture(step, status, message, **kwargs):
            statuses.append((step, status, message))

        ctx.frontend.publish_status.side_effect = _capture
        wf._enter_exit_granted(reason="rfid_error")
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)
        self.assertTrue(statuses)
        step, status, message = statuses[-1]
        self.assertEqual(step, "exit_start")
        self.assertEqual(status, "error")
        self.assertIn("failure", message.lower())


if __name__ == "__main__":
    unittest.main()
