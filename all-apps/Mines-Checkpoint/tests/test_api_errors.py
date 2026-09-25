"""Operator-facing HTTP error classification."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEMO_MODE", "true")

from services.api_errors import (  # noqa: E402
    KIND_HTTP,
    KIND_OK,
    KIND_SERVER,
    KIND_UNREACHABLE,
    annotate_response,
    classify_http_status,
    is_api_failure,
    is_service_alert,
    is_transport_failure,
    operator_copy,
)


class TestApiErrors(unittest.TestCase):
    def test_anpr_unreachable_copy(self):
        short, title = operator_copy("anpr-detect", KIND_UNREACHABLE)
        self.assertEqual(short, "ANPR not reachable")
        self.assertEqual(title, "ANPR NOT REACHABLE")

    def test_classify_status(self):
        self.assertEqual(classify_http_status(0), KIND_UNREACHABLE)
        self.assertEqual(classify_http_status(500), KIND_SERVER)
        self.assertEqual(classify_http_status(401), KIND_SERVER)
        self.assertEqual(classify_http_status(404), KIND_HTTP)
        self.assertEqual(classify_http_status(200), KIND_OK)

    def test_annotate_connection_refused_never_leaks_exception(self):
        raw_err = (
            "HTTPConnectionPool(host='localhost', port=5001): Max retries "
            "exceeded with url: /api/detect"
        )
        resp = SimpleNamespace(
            ok=False, status=0, message=raw_err, raw={}, http_status=0
        )
        annotate_response(resp, "anpr-detect")
        self.assertEqual(resp.kind, KIND_UNREACHABLE)
        self.assertEqual(resp.operator_message, "ANPR not reachable")
        self.assertTrue(resp.popup)
        self.assertEqual(resp.popup_title, "ANPR NOT REACHABLE")
        self.assertNotIn("HTTPConnectionPool", resp.operator_message)

    def test_http_200_is_not_a_popup(self):
        resp = SimpleNamespace(
            ok=True, status=1, message="ok", raw={"anpr_status": 1}, http_status=200
        )
        annotate_response(resp, "anpr-detect")
        self.assertEqual(resp.kind, KIND_OK)
        self.assertEqual(resp.operator_message, "")
        self.assertFalse(resp.popup)
        self.assertFalse(is_api_failure(resp))
        self.assertFalse(is_transport_failure(resp))

    def test_mocked_ok_true_is_not_transport_failure(self):
        resp = SimpleNamespace(ok=True, status=200, raw={}, http_status=0)
        self.assertFalse(is_transport_failure(resp))
        self.assertFalse(is_api_failure(resp))

    def test_business_rfid_500_status_is_not_transport(self):
        resp = SimpleNamespace(
            ok=False, status=500, message="fail", raw={}, http_status=0
        )
        self.assertFalse(is_transport_failure(resp))

    def test_http_404_is_red_step_not_popup(self):
        resp = SimpleNamespace(
            ok=False, status=0, message="not found", raw={}, http_status=404
        )
        annotate_response(resp, "anpr-detect")
        self.assertEqual(resp.kind, KIND_HTTP)
        self.assertEqual(resp.operator_message, "not found")
        self.assertFalse(resp.popup)
        self.assertTrue(is_api_failure(resp))
        self.assertFalse(is_service_alert(resp))

    def test_rfid_http_error_shows_api_body_message(self):
        msg = (
            "Gross RFID cannot be processed because Vadhghat Boom Close "
            "is not completed for this vehicle and loading slip."
        )
        resp = SimpleNamespace(
            ok=False,
            status=409,
            message=msg,
            raw={"status": 409, "message": msg},
            http_status=409,
        )
        annotate_response(resp, "rfid-validate")
        self.assertEqual(resp.operator_message, msg)
        self.assertFalse(resp.popup)

    def test_http_503_is_popup(self):
        resp = SimpleNamespace(
            ok=False, status=0, message="bad gateway", raw={}, http_status=503
        )
        annotate_response(resp, "rfid-validate")
        self.assertEqual(resp.operator_message, "bad gateway")
        self.assertTrue(resp.popup)
        self.assertEqual(resp.popup_title, "RFID SERVICE SERVER ERROR")
        self.assertTrue(is_service_alert(resp))


if __name__ == "__main__":
    unittest.main()
