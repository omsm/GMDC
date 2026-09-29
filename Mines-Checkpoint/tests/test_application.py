"""
Mines Entry application test suite.

Covers:
  - RFID payload parsing
  - OCI payload builders (invalid-truck, status_check)
  - OCI client HTTP helpers (mocked)
  - State machine transitions
  - Full workflow: RFID fail, ANPR match, manual loop, boom-close gate
  - Crossing timeout auto-IDLE
  - Flask API endpoints (/rfid_data, /api/status, /api/reset)
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.constants import Event, State, TIMEOUTS
from config.settings import Settings, _join_url, load_settings
from core.app_context import AppContext
from core.state_machine import StateMachine
from core.transaction import Transaction, TransactionStore
from core.workflow import CheckpointWorkflow
from hardware.rfid_reader import extract_id_hexes
from services.oci_client import (
    OCIClient,
    OCIResponse,
    build_boom_close_payload,
    build_invalid_truck_payload,
    build_status_check_payload,
    document_downloaded,
    exit_document_ids,
    is_ce_truck_details,
    is_x_truck_details,
    parse_truck_details,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RFID_PAYLOAD = [
    {
        "data": {
            "CRC": "ed95",
            "PC": "3400",
            "antenna": 1,
            "idHex": "e200001d7507013115006bb9",
            "peakRssi": -31,
        },
        "timestamp": "2026-07-28T08:08:25.836+0000",
        "type": "CUSTOM",
    },
    {
        "data": {"idHex": "e200001d7507013115006bb9"},
        "type": "CUSTOM",
    },
]

TRUCK_DETAILS = (
    "T|e200001d7507013115006bb9|OD14P7339|2800|1500|500|"
    "TRIP-20260728-001|192.168.10.223"
)

CE_TRUCK_DETAILS = (
    "CE|00000000000000000015c021|OD14AF2721|45000|26000|0|"
    "9580709262|IP244245525163|OD14AF2721"
)

ANPR_RAW = {
    "anpr_image": "/tmp/anpr.jpg",
    "front_image": "/tmp/front.jpg",
    "matching_score": 50.0,
    "anpr_status": 0,
    "rfid": "e200001d7507013115006bb9",
    "vehicleNo_anpr": "OD14AF2721",
    "vehicleNo_web": "OD14P7339",
    "token": "",
}


def _wait_state(sm: StateMachine, expected: State, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sm.current_state == expected:
            return True
        time.sleep(0.05)
    return sm.current_state == expected


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------

class TestRFIDPayloadParsing(unittest.TestCase):
    def test_dedupe_id_hex(self):
        tags = extract_id_hexes(SAMPLE_RFID_PAYLOAD)
        self.assertEqual(tags, ["e200001d7507013115006bb9"])

    def test_empty_payload(self):
        self.assertEqual(extract_id_hexes([]), [])
        self.assertEqual(extract_id_hexes({}), [])
        self.assertEqual(extract_id_hexes(None), [])

    def test_wrapped_tags_key(self):
        payload = {"tags": [{"data": {"idHex": "abc123"}}]}
        self.assertEqual(extract_id_hexes(payload), ["abc123"])


class TestTruckDetailsParsing(unittest.TestCase):
    def test_pipe_delimited(self):
        p = parse_truck_details(TRUCK_DETAILS)
        self.assertEqual(p["rfid"], "e200001d7507013115006bb9")
        self.assertEqual(p["vehicle_no"], "OD14P7339")
        self.assertEqual(p["token_no"], "TRIP-20260728-001")
        self.assertEqual(p["device_ip"], "192.168.10.223")
        self.assertEqual(p["prefix"], "T")
        self.assertFalse(is_ce_truck_details(TRUCK_DETAILS))

    def test_ce_pipe_delimited(self):
        p = parse_truck_details(CE_TRUCK_DETAILS)
        self.assertEqual(p["prefix"], "CE")
        self.assertEqual(p["rfid"], "00000000000000000015c021")
        self.assertEqual(p["vehicle_no"], "OD14AF2721")
        self.assertEqual(p["token_no"], "9580709262")
        self.assertEqual(p["device_ip"], "IP244245525163")
        self.assertTrue(is_ce_truck_details(CE_TRUCK_DETAILS))

    def test_x_exit_slip_ids_from_short_string(self):
        details = (
            "X|e200001d7507013115006bb9|OD14P7339|9582209263|885|10.80.118.142"
        )
        self.assertTrue(is_x_truck_details(details))
        slip_no, slip_id = exit_document_ids(details)
        self.assertEqual(slip_no, "9582209263")
        self.assertEqual(slip_id, "885")

    def test_x_exit_slip_ids_prefer_json_keys(self):
        details = "X|rfid|VEH|1|2|10.0.0.1"
        slip_no, slip_id = exit_document_ids(
            details,
            {"loading_slip_no": "9582209263", "loadingSlipId": "885"},
        )
        self.assertEqual(slip_no, "9582209263")
        self.assertEqual(slip_id, "885")

    def test_document_downloaded_flag(self):
        waiting = OCIResponse(
            ok=True,
            status=200,
            raw={"status": 200, "documentDownloaded": False, "docDownload": 0},
        )
        ready = OCIResponse(
            ok=False,
            status=0,
            raw={
                "status": "SUCCESS",
                "statusCode": 200,
                "documentDownloaded": True,
                "docDownload": 1,
            },
        )
        self.assertFalse(document_downloaded(waiting))
        self.assertTrue(document_downloaded(ready))

    def test_empty(self):
        p = parse_truck_details("")
        self.assertEqual(p["rfid"], "")
        self.assertEqual(p["vehicle_no"], "")


class TestInvalidTruckPayload(unittest.TestCase):
    def test_filters_anpr_fields(self):
        raw = dict(ANPR_RAW)
        raw["numberplate_Image(base64)"] = "HUGE_BASE64_DATA"
        raw["camera"] = 1
        payload = build_invalid_truck_payload(
            raw,
            vehicle_no_web="OD14P7339",
            rfid="e200001d7507013115006bb9",
            token="TRIP-20260728-001",
            device_ip="192.168.10.223",
            anpr_status=0,
        )
        self.assertEqual(
            set(payload.keys()),
            {
                "vehicleNo_web",
                "vehicleNo_anpr",
                "rfid",
                "anpr_image",
                "front_image",
                "matching_score",
                "anpr_status",
                "token",
                "device_ip",
            },
        )
        self.assertEqual(payload["vehicleNo_anpr"], "OD14AF2721")
        self.assertEqual(payload["anpr_status"], "0")
        self.assertNotIn("numberplate_Image(base64)", payload)
        self.assertNotIn("camera", payload)

    def test_fallback_token_and_device_ip(self):
        payload = build_invalid_truck_payload(
            {"vehicleNo_web": "A", "vehicleNo_anpr": "B", "rfid": "R"},
            token="TOK",
            device_ip="1.2.3.4",
        )
        self.assertEqual(payload["token"], "TOK")
        self.assertEqual(payload["device_ip"], "1.2.3.4")


class TestStatusCheckPayload(unittest.TestCase):
    def test_from_anpr_response(self):
        payload = build_status_check_payload(
            ANPR_RAW, device_ip="192.168.10.223"
        )
        self.assertEqual(
            payload,
            {
                "vehicleNo_web": "OD14P7339",
                "vehicleNo_anpr": "OD14AF2721",
                "rfid": "e200001d7507013115006bb9",
                "device_ip": "192.168.10.223",
            },
        )


class TestJoinUrl(unittest.TestCase):
    def test_relative_path(self):
        self.assertEqual(
            _join_url("https://oci.example", "/ords/x"),
            "https://oci.example/ords/x",
        )

    def test_absolute_overrides_base(self):
        self.assertEqual(
            _join_url("https://oci.example", "http://192.168.1.1:5001/api/detect"),
            "http://192.168.1.1:5001/api/detect",
        )


# ---------------------------------------------------------------------------
# Unit: state machine
# ---------------------------------------------------------------------------

class TestStateMachine(unittest.TestCase):
    def test_happy_path(self):
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

    def test_manual_loop_and_grant(self):
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

    def test_manual_then_anpr_match_grant(self):
        """App always posts invalid-truck then may grant on anpr_status=1."""
        sm = StateMachine()
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_VALID)
        sm.trigger(Event.ANPR_MISMATCH)
        self.assertTrue(sm.trigger(Event.ANPR_MATCH))
        self.assertEqual(sm.current_state, State.ENTRY_GRANTED)

    def test_vehicle_status_2_reset(self):
        sm = StateMachine()
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_VALID)
        sm.trigger(Event.ANPR_MISMATCH)
        sm.trigger(Event.UPDATE_STATUS_2)
        self.assertEqual(sm.current_state, State.IDLE)

    def test_crossing_timeout(self):
        sm = StateMachine()
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_RECEIVED)
        sm.trigger(Event.RFID_VALID)
        sm.trigger(Event.ANPR_MATCH)
        sm.trigger(Event.ENTRY_OPENED)
        self.assertEqual(sm.current_state, State.WAIT_CROSSING)
        self.assertTrue(sm.trigger(Event.CROSSING_TIMEOUT))
        self.assertEqual(sm.current_state, State.IDLE)

    def test_invalid_transition_ignored(self):
        sm = StateMachine()
        self.assertFalse(sm.trigger(Event.ANPR_MATCH))
        self.assertEqual(sm.current_state, State.IDLE)


class TestTransaction(unittest.TestCase):
    def test_start_and_clear(self):
        t = Transaction()
        t.start(["a", "b"], [{"data": {"idHex": "a"}}])
        self.assertEqual(t.rfid_tags, ["a", "b"])
        self.assertIsNotNone(t.started_at)
        t.clear()
        self.assertEqual(t.rfid_tags, [])
        self.assertEqual(t.validated_rfid, "")


# ---------------------------------------------------------------------------
# Unit: OCI client (mocked HTTP)
# ---------------------------------------------------------------------------

class TestOCIClient(unittest.TestCase):
    def setUp(self):
        self.client = OCIClient(
            base_url="https://oci.example",
            username="user",
            password="pass",
            rfid_validate_url="https://oci.example/rfid-tag",
            anpr_detect_url="http://anpr.example/api/detect",
            invalid_truck_url="https://oci.example/invalid-truck-number",
            update_truck_url="https://oci.example/status_check",
            boom_close_url="https://oci.example/boom-close",
            anpr_username="anpr_user",
            anpr_password="anpr_pass",
        )

    def _mock_response(self, status_code=200, body=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.ok = 200 <= status_code < 300
        resp.json.return_value = body or {}
        resp.text = json.dumps(body or {})
        return resp

    @patch("services.oci_client.requests.Session.post")
    def test_validate_rfid_success(self, mock_post):
        mock_post.return_value = self._mock_response(
            200,
            {
                "status": 200,
                "message": "ok",
                "truck_details": TRUCK_DETAILS,
            },
        )
        resp = self.client.validate_rfid("e2000", "192.168.10.223")
        self.assertTrue(resp.ok)
        self.assertEqual(resp.status, 200)
        self.assertIn("OD14P7339", resp.truck_details)
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["auth"], ("user", "pass"))

    @patch("services.oci_client.requests.Session.post")
    def test_anpr_uses_separate_auth(self, mock_post):
        mock_post.return_value = self._mock_response(
            200, {"anpr_status": 0, "vehicleNo_anpr": "X"}
        )
        resp = self.client.anpr_detect("OD14P7339", "rfid1", token_no="TOK")
        self.assertEqual(resp.status, 0)
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["auth"], ("anpr_user", "anpr_pass"))
        self.assertEqual(args[0], "http://anpr.example/api/detect")

    @patch("services.oci_client.requests.Session.post")
    def test_anpr_connection_refused_maps_to_operator_copy(self, mock_post):
        import requests

        mock_post.side_effect = requests.exceptions.ConnectionError(
            "HTTPConnectionPool(host='localhost', port=5001): Max retries "
            "exceeded with url: /api/detect (Caused by NewConnectionError("
            "\"HTTPConnection(host='localhost', port=5001): Failed to "
            'establish a new connection: [Errno 61] Connection refused"))'
        )
        resp = self.client.anpr_detect(
            "OD14AF2721", "00000000000000000015c021", token_no="9580109262"
        )
        self.assertFalse(resp.ok)
        self.assertEqual(resp.kind, "unreachable")
        self.assertEqual(resp.operator_message, "ANPR not reachable")
        self.assertTrue(resp.popup)
        self.assertEqual(resp.popup_title, "ANPR NOT REACHABLE")
        self.assertNotIn("HTTPConnectionPool", resp.operator_message)
        self.assertIn("HTTPConnectionPool", resp.message)

    @patch("services.oci_client.requests.Session.post")
    def test_reset_checkpoint_payload_and_auth(self, mock_post):
        mock_post.return_value = self._mock_response(
            200,
            {
                "status": 200,
                "response_type": 1,
                "message": "Current checkpoint transaction reset successfully.",
            },
        )
        resp = self.client.reset_checkpoint(
            device_ip="10.10.180.12",
            rfid_no="E28068940000503F548F04BA",
            truck_details=TRUCK_DETAILS,
        )
        self.assertTrue(resp.ok)
        self.assertEqual(resp.status, 200)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["device_ip"], "10.10.180.12")
        self.assertEqual(sent["rfid_no"], "E28068940000503F548F04BA")
        self.assertEqual(sent["truck_details"], TRUCK_DETAILS)
        self.assertIn("reset_checkpoint", mock_post.call_args.args[0])
        self.assertEqual(mock_post.call_args.kwargs["auth"], ("user", "pass"))
        self.client.reset_checkpoint(device_ip="10.10.180.12")
        self.assertEqual(mock_post.call_args.kwargs["json"]["rfid_no"], "")
        self.assertEqual(mock_post.call_args.kwargs["json"]["truck_details"], "")
        self.assertEqual(mock_post.call_args.kwargs["auth"], ("user", "pass"))

    @patch("services.oci_client.requests.Session.post")
    def test_reset_checkpoint_uses_endpoint_auth(self, mock_post):
        mock_post.return_value = self._mock_response(200, {"status": 200})
        self.client.endpoint_auth["reset_checkpoint"] = (
            "GMDC_API_USER",
            "GMDC@1234",
        )
        self.client.reset_checkpoint(device_ip="10.10.180.12")
        self.assertEqual(
            mock_post.call_args.kwargs["auth"],
            ("GMDC_API_USER", "GMDC@1234"),
        )

    @patch("services.oci_client.requests.Session.post")
    def test_invalid_truck_filtered_payload(self, mock_post):
        mock_post.return_value = self._mock_response(
            201, {"status": 201, "message": "Vehicle not manually updated"}
        )
        raw = dict(ANPR_RAW)
        raw["numberplate_Image(base64)"] = "xxx"
        self.client.invalid_truck_number(
            rfid="e2000",
            truck_number="OD14P7339",
            device_ip="192.168.10.223",
            anpr_payload=raw,
            token="TRIP-1",
            anpr_status=0,
        )
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["vehicleNo_anpr"], "OD14AF2721")
        self.assertNotIn("numberplate_Image(base64)", sent)

    @patch("services.oci_client.requests.Session.post")
    def test_status_check_uses_vehicle_status(self, mock_post):
        mock_post.return_value = self._mock_response(
            200,
            {
                "statusCode": 200,
                "vehicleStatus": 0,
                "statusMessage": "Vehicle is not manually updated",
            },
        )
        resp = self.client.update_truck_number(
            anpr_payload=ANPR_RAW, device_ip="192.168.10.223"
        )
        self.assertEqual(resp.status, 0)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["vehicleNo_web"], "OD14P7339")
        self.assertEqual(sent["vehicleNo_anpr"], "OD14AF2721")

    @patch("services.oci_client.requests.Session.post")
    def test_boom_close_string_status_200(self, mock_post):
        mock_post.return_value = self._mock_response(
            200, {"status": "200", "message": " "}
        )
        resp = self.client.boom_close(
            rfid="rfid1",
            device_ip="192.168.10.223",
            truck_details=TRUCK_DETAILS,
            anpr_payload={
                **ANPR_RAW,
                "top_image": "/tmp/top.jpg",
            },
        )
        self.assertTrue(resp.ok)
        self.assertEqual(resp.status, 200)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            sent,
            {
                "rfid": "e200001d7507013115006bb9",
                "device_ip": "192.168.10.223",
                "truck_details": TRUCK_DETAILS,
                "top_image": "/tmp/top.jpg",
                "front_image": "/tmp/front.jpg",
                "anpr_image": "/tmp/anpr.jpg",
                "close-type": "auto",
            },
        )

    def test_build_boom_close_payload_from_flow(self):
        payload = build_boom_close_payload(
            {**ANPR_RAW, "top_image": "/tmp/top.jpg"},
            rfid="fallback-rfid",
            device_ip="192.168.10.223",
            truck_details=TRUCK_DETAILS,
        )
        self.assertEqual(payload["rfid"], "e200001d7507013115006bb9")
        self.assertEqual(payload["truck_details"], TRUCK_DETAILS)
        self.assertEqual(payload["top_image"], "/tmp/top.jpg")
        self.assertEqual(payload["front_image"], "/tmp/front.jpg")
        self.assertEqual(payload["anpr_image"], "/tmp/anpr.jpg")
        self.assertEqual(payload["close-type"], "auto")


# ---------------------------------------------------------------------------
# Integration: workflow with mocks
# ---------------------------------------------------------------------------

class TestWorkflow(unittest.TestCase):
    def setUp(self):
        AppContext.reset_instance()
        self.ctx = AppContext.get_instance()
        self.ctx.state_machine = StateMachine()
        self.ctx.transactions = TransactionStore()

        settings = MagicMock()
        settings.device_ip = "192.168.10.223"
        settings.demo_mode = True
        settings.anpr_enabled = True
        settings.truck_anpr_retry_timer = 0.01
        settings.vehicle_crossing_timeout = 0.15
        self.ctx.settings = settings

        self.display = MagicMock()
        self.tl = MagicMock()
        self.boom = MagicMock()
        self.ctx.display = self.display
        self.ctx.traffic_light = self.tl
        self.ctx.boom_barrier = self.boom
        self.ctx.rfid_cloud = MagicMock()
        self.ctx.rfid_cloud.prepare_idle.return_value = True
        self.ctx.rfid_cloud.stop.return_value = True

        self.oci = MagicMock()
        self.oci.reset_checkpoint.return_value = OCIResponse(
            ok=True, status=200, http_status=200
        )
        self.ctx.oci = self.oci
        self.workflow = CheckpointWorkflow(self.ctx)
        self.ctx.workflow = self.workflow

        self._sleep_patch = patch("core.workflow.time.sleep", return_value=None)
        self._sleep_patch.start()

    def tearDown(self):
        self.workflow._cancel_crossing_timer()
        self._sleep_patch.stop()
        AppContext.reset_instance()

    def _rfid_ok(self, truck_details: str = TRUCK_DETAILS):
        self.oci.validate_rfid.return_value = OCIResponse(
            ok=True, status=200, truck_details=truck_details
        )

    def test_rfid_fail_shows_error_and_idle(self):
        self.oci.validate_rfid.return_value = OCIResponse(
            ok=False, status=500, message="fail"
        )
        self.workflow.on_rfid_tags(["badtag"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.IDLE))
        self.display.send.assert_any_call("RFID ERR@ASK OPERATOR")
        self.ctx.rfid_cloud.stop.assert_called()
        self.oci.reset_checkpoint.assert_called()
        kwargs = self.oci.reset_checkpoint.call_args.kwargs
        self.assertEqual(kwargs["rfid_no"], "badtag")
        self.assertEqual(kwargs["device_ip"], "192.168.10.223")

    def test_manual_reset_without_transaction_skips_reset_api(self):
        self.workflow.force_reset()
        self.oci.reset_checkpoint.assert_not_called()

    def test_startup_notify_gmdc_reset_skips_when_idle(self):
        self.workflow.notify_gmdc_reset()
        self.oci.reset_checkpoint.assert_not_called()

    def test_manual_reset_with_transaction_sends_rfid_and_details(self):
        txn = self.ctx.transactions.current
        txn.validated_rfid = "E28068940000503F548F04BA"
        txn.truck_details = TRUCK_DETAILS
        txn.device_ip = "10.10.180.12"
        self.workflow.force_reset()
        kwargs = self.oci.reset_checkpoint.call_args.kwargs
        self.assertEqual(kwargs["device_ip"], "10.10.180.12")
        self.assertEqual(kwargs["rfid_no"], "E28068940000503F548F04BA")
        self.assertEqual(kwargs["truck_details"], TRUCK_DETAILS)

    def test_anpr_exception_retries_3_then_idle(self):
        self._rfid_ok()
        self.oci.anpr_detect.side_effect = ConnectionError("ANPR down")

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.IDLE))
        self.assertEqual(self.oci.anpr_detect.call_count, 3)
        self.display.send.assert_any_call("ANPR ERROR@ASK OPERATOR")
        self.oci.invalid_truck_number.assert_not_called()
        self.boom.open.assert_not_called()
        self.ctx.rfid_cloud.prepare_idle.assert_called()

    def test_anpr_unreachable_publishes_popup_not_raw_exception(self):
        fe = MagicMock()
        self.ctx.frontend = fe
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False,
            status=0,
            message=(
                "HTTPConnectionPool(host='localhost', port=5001): Max retries "
                "exceeded with url: /api/detect"
            ),
            http_status=0,
            raw={},
        )

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.IDLE))

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

    def test_anpr_transport_failure_response_retries_then_idle(self):
        """http_status=0 + empty raw (as _post does on RequestException)."""
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, message="Connection refused", http_status=0, raw={}
        )

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.IDLE))
        self.assertEqual(self.oci.anpr_detect.call_count, 3)
        self.display.send.assert_any_call("ANPR ERROR@ASK OPERATOR")

    def test_anpr_succeeds_on_second_retry(self):
        self._rfid_ok()
        self.oci.anpr_detect.side_effect = [
            ConnectionError("temp"),
            OCIResponse(
                ok=True,
                status=1,
                http_status=200,
                raw={**ANPR_RAW, "anpr_status": 1},
            ),
        ]
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=200, raw={"statusCode": 200}
        )
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.assertEqual(self.oci.anpr_detect.call_count, 2)
        self.boom.open.assert_called()

    def test_anpr_status_2_enters_status_check_then_resets_on_vehicle_status_2(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True,
            status=2,
            raw={**ANPR_RAW, "anpr_status": 2},
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=False,
            status=2,
            raw={"statusCode": 200, "vehicleStatus": 2},
        )

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.IDLE))
        self.display.send.assert_any_call("ANPR ERROR@ERR-2")
        self.boom.open.assert_not_called()
        self.assertEqual(self.oci.anpr_detect.call_count, 1)
        self.oci.invalid_truck_number.assert_called()
        self.oci.update_truck_number.assert_called()
        self.ctx.rfid_cloud.prepare_idle.assert_called()

    def test_anpr_status_2_status_check_success_grants_entry(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True,
            status=2,
            raw={**ANPR_RAW, "anpr_status": 2},
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={"statusCode": 200, "vehicleStatus": 1},
        )
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.display.send.assert_any_call("ANPR ERROR@ERR-2")
        self.boom.open.assert_called()
        self.assertEqual(self.oci.anpr_detect.call_count, 1)
        self.oci.update_truck_number.assert_called()

    def test_anpr_match_calls_boom_close_then_opens(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={**ANPR_RAW, "anpr_status": 1, "matching_score": 100},
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))

        self.oci.invalid_truck_number.assert_called()
        self.oci.update_truck_number.assert_not_called()
        self.oci.boom_close.assert_called()
        bc_kwargs = self.oci.boom_close.call_args.kwargs
        self.assertEqual(bc_kwargs["rfid"], "e200001d7507013115006bb9")
        self.assertEqual(bc_kwargs["device_ip"], "192.168.10.223")
        self.assertEqual(bc_kwargs["close_type"], "auto")
        self.assertEqual(bc_kwargs["truck_details"], TRUCK_DETAILS)
        self.assertIn("anpr_image", bc_kwargs["anpr_payload"])
        self.boom.open.assert_called()
        self.tl.set_green.assert_called()
        self.display.send.assert_any_call("Granted OD14P7339@Thank You")
        self.oci.download_docs.assert_not_called()

    def test_x_trip_waits_for_document_download_before_boom_close(self):
        details = (
            "X|e200001d7507013115006bb9|OD14P7339|9582209263|885|10.80.118.142"
        )
        self._rfid_ok(details)
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={**ANPR_RAW, "anpr_status": 1, "matching_score": 100},
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.download_docs.side_effect = [
            OCIResponse(
                ok=True,
                status=200,
                http_status=200,
                message="Exit documents have not been downloaded.",
                raw={
                    "status": 200,
                    "documentDownloaded": False,
                    "docDownload": 0,
                    "message": "Exit documents have not been downloaded.",
                },
            ),
            OCIResponse(
                ok=True,
                status=200,
                http_status=200,
                message="Exit documents have been downloaded.",
                raw={
                    "statusCode": 200,
                    "status": "SUCCESS",
                    "documentDownloaded": True,
                    "docDownload": 1,
                    "message": "Exit documents have been downloaded.",
                },
            ),
        ]
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))

        self.assertEqual(self.oci.download_docs.call_count, 2)
        docs_kwargs = self.oci.download_docs.call_args.kwargs
        self.assertEqual(docs_kwargs["loading_slip_no"], "9582209263")
        self.assertEqual(docs_kwargs["loading_slip_id"], "885")
        self.assertEqual(docs_kwargs["device_ip"], "10.80.118.142")
        self.oci.boom_close.assert_called_once()
        names = [call[0] for call in self.oci.mock_calls]
        self.assertLess(names.index("download_docs"), names.index("boom_close"))
        self.boom.open.assert_called()

    def test_anpr_disabled_calls_invalid_truck_then_status_check(self):
        """ANPR off still posts invalid-truck(anpr_status=2) then polls status_check."""
        self.ctx.settings.anpr_enabled = False
        self._rfid_ok()
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=1, raw={"vehicleStatus": 1, "statusCode": 200}
        )
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.oci.anpr_detect.assert_not_called()
        self.oci.invalid_truck_number.assert_called()
        inv = self.oci.invalid_truck_number.call_args.kwargs
        self.assertEqual(inv.get("anpr_status"), 2)
        self.oci.update_truck_number.assert_called()
        self.boom.open.assert_called()

    def test_ce_anpr_match_polls_check_status_until_status_code_200(self):
        """CE| truck_details: after invalid-truck, poll until statusCode 200 even on ANPR match."""
        self._rfid_ok(CE_TRUCK_DETAILS)
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={**ANPR_RAW, "anpr_status": 1, "matching_score": 100},
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.side_effect = [
            OCIResponse(
                ok=False,
                status=0,
                raw={"statusCode": 100, "statusMessage": "pending"},
            ),
            OCIResponse(
                ok=True,
                status=200,
                raw={"statusCode": 200, "vehicleNo_web": "OD14AF2721"},
            ),
        ]
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["00000000000000000015c021"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.assertEqual(self.oci.update_truck_number.call_count, 2)
        self.boom.open.assert_called()
        self.display.send.assert_any_call("Granted OD14AF2721@Thank You")

    def test_ce_anpr_mismatch_uses_status_code_not_vehicle_status(self):
        """CE mismatch waits on statusCode 200; vehicleStatus 2 must not abort."""
        self._rfid_ok(CE_TRUCK_DETAILS)
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw=ANPR_RAW
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=201
        )
        self.oci.update_truck_number.side_effect = [
            OCIResponse(
                ok=False,
                status=2,
                raw={"statusCode": 100, "vehicleStatus": 2},
            ),
            OCIResponse(
                ok=True,
                status=200,
                raw={"statusCode": 200},
            ),
        ]
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["00000000000000000015c021"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.assertEqual(self.oci.update_truck_number.call_count, 2)
        self.boom.open.assert_called()

    def test_boom_not_opened_when_boom_close_fails(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=200, raw={"statusCode": 200}
        )
        self.oci.boom_close.return_value = OCIResponse(
            ok=False, status=500, message="fail"
        )

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.boom.open.assert_not_called()
        self.tl.set_green.assert_called()

    def test_manual_loop_vehicle_status_0_then_1(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw=ANPR_RAW
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=201
        )
        self.oci.update_truck_number.side_effect = [
            OCIResponse(
                ok=False,
                status=0,
                raw={"statusCode": 200, "vehicleStatus": 0},
            ),
            OCIResponse(
                ok=True,
                status=1,
                raw={"statusCode": 200, "vehicleStatus": 1},
            ),
        ]
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.display.send.assert_any_call("ANPR ERROR@ERR-0")
        self.assertGreaterEqual(self.oci.update_truck_number.call_count, 2)
        # status_check must receive ANPR-derived payload fields
        call_kwargs = self.oci.update_truck_number.call_args.kwargs
        self.assertEqual(call_kwargs["anpr_payload"]["vehicleNo_anpr"], "OD14AF2721")
        self.boom.open.assert_called()

    def test_manual_loop_http_4xx_keeps_anpr_mismatch_warning(self):
        fe = MagicMock()
        self.ctx.frontend = fe
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw=ANPR_RAW
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=201
        )
        self.oci.update_truck_number.side_effect = [
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
                raw={"statusCode": 200, "vehicleStatus": 1},
            ),
        ]
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))

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
        self.boom.open.assert_called()

    def test_manual_loop_vehicle_status_2_resets_idle(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=False, status=0, raw=ANPR_RAW
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=201
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=False,
            status=2,
            raw={"statusCode": 200, "vehicleStatus": 2},
        )

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.IDLE))
        self.boom.open.assert_not_called()
        self.ctx.rfid_cloud.prepare_idle.assert_called()

    def test_exit_sensor_resets_to_idle(self):
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=200, raw={"statusCode": 200}
        )
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertTrue(_wait_state(self.ctx.state_machine, State.WAIT_CROSSING))
        self.boom.close.reset_mock()
        self.workflow.on_exit_sensor()
        self.assertEqual(self.ctx.state_machine.current_state, State.IDLE)
        # Boom stays up for BOOM_CLOSE_DELAY_SEC after the truck clears
        self.boom.close.assert_not_called()
        self.assertTrue(self.workflow._boom_close_timer.is_alive())
        self.workflow._boom_close_timer.function()
        self.boom.close.assert_called()
        self.oci.reset_checkpoint.assert_not_called()

    def test_crossing_timeout_auto_idle(self):
        # Use real sleep for timer; patch only RFID/OCI sleeps already patched
        self._sleep_patch.stop()
        self._rfid_ok()
        self.oci.anpr_detect.return_value = OCIResponse(
            ok=True, status=1, raw={**ANPR_RAW, "anpr_status": 1}
        )
        self.oci.invalid_truck_number.return_value = OCIResponse(
            ok=True, status=200
        )
        self.oci.update_truck_number.return_value = OCIResponse(
            ok=True, status=200, raw={"statusCode": 200}
        )
        self.oci.boom_close.return_value = OCIResponse(ok=True, status=200)

        # Patch sleep only inside RFID error / manual loop paths via short timeout
        with patch("core.workflow.time.sleep", return_value=None):
            self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
            self.assertTrue(
                _wait_state(self.ctx.state_machine, State.WAIT_CROSSING, timeout=2.0)
            )

        # Crossing timer uses real Timer (0.15s)
        self.assertTrue(
            _wait_state(self.ctx.state_machine, State.IDLE, timeout=2.0)
        )
        self.oci.reset_checkpoint.assert_called()
        self._sleep_patch.start()

    def test_free_pass_opens_barrier_then_sensor_resets_idle(self):
        fe = MagicMock()
        self.ctx.frontend = fe
        self.ctx.sensor_poller = MagicMock()
        self.workflow.start_free_pass()
        self.assertEqual(self.ctx.state_machine.current_state, State.FREE_PASS)
        self.tl.set_green.assert_called()
        self.boom.open.assert_called()
        self.display.send.assert_called_with("FREE PASS")
        fe.publish_display.assert_called_with("FREE PASS")

        self.workflow.on_rfid_tags(["e200001d7507013115006bb9"])
        self.assertEqual(self.ctx.state_machine.current_state, State.FREE_PASS)
        self.oci.validate_rfid.assert_not_called()

        self.boom.close.reset_mock()
        self.workflow.on_exit_sensor()
        self.assertEqual(self.ctx.state_machine.current_state, State.IDLE)
        self.tl.set_red.assert_called()
        self.boom.close.assert_not_called()
        self.assertTrue(self.workflow._boom_close_timer.is_alive())
        self.workflow._boom_close_timer.function()
        self.boom.close.assert_called()


# ---------------------------------------------------------------------------
# Flask API endpoints
# ---------------------------------------------------------------------------

class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        AppContext.reset_instance()
        self.ctx = AppContext.get_instance()
        self.ctx.state_machine = StateMachine()
        self.ctx.transactions = TransactionStore()
        self.ctx.settings = MagicMock(demo_mode=True, device_ip="192.168.10.223")
        self.ctx.workflow = MagicMock()
        self.ctx.rfid_reader = None
        self.ctx.io = None
        self.ctx.traffic_light = None
        self.ctx.boom_barrier = None
        self.ctx.sensor_poller = None
        self.ctx.display = None

        from api.server import create_app

        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        AppContext.reset_instance()

    def test_root(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("Checkpoint", body)
        self.assertIn("text/html", r.content_type)

    def test_health_status(self):
        r = self.client.get("/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], 200)

    def test_status(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["state"], "IDLE")

    def test_rfid_data_accepts_tags(self):
        r = self.client.post(
            "/rfid_data",
            data=json.dumps(SAMPLE_RFID_PAYLOAD),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["tags"], ["e200001d7507013115006bb9"])
        self.ctx.workflow.on_rfid_tags.assert_called()

    def test_rfid_data_rejects_empty(self):
        r = self.client.post(
            "/rfid_data",
            data=json.dumps([]),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_rfid_management(self):
        r = self.client.post("/rfid_management", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "success")

    def test_rfid_from_mobile_app_returns_oci_body(self):
        self.ctx.workflow.on_rfid_from_mobile.return_value = {
            "status": 500,
            "message": "Some error occured",
        }
        r = self.client.post(
            "/rfid_data_from_mobile_app",
            json={"rfid_data": "1234567890"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], 500)
        self.assertEqual(body["message"], "Some error occured")
        self.ctx.workflow.on_rfid_from_mobile.assert_called_once_with(
            "1234567890"
        )

    def test_rfid_from_mobile_app_missing_key(self):
        r = self.client.post("/rfid_data_from_mobile_app", json={})
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["status"], "500")
        self.assertIsNone(body["rfid_data"])
        self.assertIn("Error:", body["message"])
        self.ctx.workflow.on_rfid_from_mobile.assert_not_called()

    def test_rfid_from_mobile_app_blank_value(self):
        r = self.client.post(
            "/rfid_data_from_mobile_app",
            json={"rfid_data": "   "},
        )
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["status"], "500")
        self.assertIsNone(body["rfid_data"])
        self.ctx.workflow.on_rfid_from_mobile.assert_not_called()

    def test_reset(self):
        r = self.client.post("/api/reset")
        self.assertEqual(r.status_code, 200)
        self.ctx.workflow.force_reset.assert_called()

    def test_free_pass(self):
        r = self.client.post("/api/free-pass")
        self.assertEqual(r.status_code, 200)
        self.ctx.workflow.start_free_pass.assert_called()

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


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class TestSettings(unittest.TestCase):
    def test_load_from_iot_configuration(self):
        settings = load_settings(str(ROOT / "iot_configuration.json"))
        self.assertTrue(settings.oci_base_url)
        self.assertIn("boom-close", settings.boom_close_url)
        self.assertIn("reset_checkpoint", settings.reset_checkpoint_url)
        self.assertIn("status_check", settings.update_truck_url)
        self.assertGreater(settings.truck_anpr_retry_timer, 0)
        self.assertGreater(settings.vehicle_crossing_timeout, 0)
        self.assertEqual(
            settings.endpoint_auth.get("reset_checkpoint"),
            ("GMDC_API_USER", "GMDC@1234"),
        )

    def test_anpr_url_separate_from_oci(self):
        settings = load_settings(str(ROOT / "iot_configuration.json"))
        self.assertNotEqual(
            settings.anpr_base_url.rstrip("/"),
            settings.oci_base_url.rstrip("/"),
        )


if __name__ == "__main__":
    unittest.main()
