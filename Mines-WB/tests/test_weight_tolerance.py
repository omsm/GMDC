"""RTO weight tolerance and exit-sensor uncut→cut→uncut tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "gmdc_common"))

os.environ.setdefault("DEMO_MODE", "true")

from services.oci_client import (  # noqa: E402
    build_vadhghat_weight_adjustment_payload,
    parse_truck_details,
    replace_truck_details_tolerance,
    rto_weight_band,
    under_or_over_type,
    vadhghat_weight_delta,
    weight_within_rto_tolerance,
)

TARE_DETAILS = (
    "T|D2030DBE|OD14AE3900|45000|15000|500|9581208263|IP244245525163|OD14AE3900"
)
VADAGHAT_DETAILS = (
    "V|D2030DBE|OD14AE3900|45000|15000|500|9581208263|IP244245525163|OD14AE3900"
)
GROSS_DETAILS = (
    "G|D2030DBE|OD14AE3900|45000|15000|500|9581208263|IP244245525163|OD14AE3900"
)


class TestRtoWeightBand(unittest.TestCase):
    def test_parses_tare_gross_tolerance(self):
        parsed = parse_truck_details(TARE_DETAILS)
        self.assertEqual(parsed["trip_type"], "T")
        self.assertEqual(parsed["rto_gross"], "45000")
        self.assertEqual(parsed["rto_tare"], "15000")
        self.assertEqual(parsed["tolerance"], "500")
        self.assertEqual(parsed["vehicle_no"], "OD14AE3900")

    def test_tare_band_is_plus_minus_tolerance(self):
        lo, hi, trip = rto_weight_band(TARE_DETAILS)
        self.assertEqual(trip, "T")
        self.assertEqual(lo, 14500)
        self.assertEqual(hi, 15500)
        self.assertTrue(weight_within_rto_tolerance(14500, TARE_DETAILS)[0])
        self.assertTrue(weight_within_rto_tolerance(15500, TARE_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(14499, TARE_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(15501, TARE_DETAILS)[0])

    def test_vadaghat_band_is_gross_minus_tolerance_to_gross(self):
        lo, hi, trip = rto_weight_band(VADAGHAT_DETAILS)
        self.assertEqual(trip, "V")
        self.assertEqual(lo, 44500)
        self.assertEqual(hi, 45000)
        self.assertTrue(weight_within_rto_tolerance(44500, VADAGHAT_DETAILS)[0])
        self.assertTrue(weight_within_rto_tolerance(45000, VADAGHAT_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(44499, VADAGHAT_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(45001, VADAGHAT_DETAILS)[0])

    def test_gross_band_from_rfid_string(self):
        """G|…|45000|26000|500|… → (45000-500) to 45000; tare is unused."""
        details = (
            "G|00000000000000000015c021|OD14AF2721|45000|26000|500|"
            "9581908261|10.10.180.1|OD14AF2721"
        )
        parsed = parse_truck_details(details)
        self.assertEqual(parsed["rto_gross"], "45000")
        self.assertEqual(parsed["rto_tare"], "26000")
        self.assertEqual(parsed["tolerance"], "500")
        lo, hi, trip = rto_weight_band(details)
        self.assertEqual(trip, "G")
        self.assertEqual((lo, hi), (44500.0, 45000.0))
        self.assertTrue(weight_within_rto_tolerance(44500, details)[0])
        self.assertTrue(weight_within_rto_tolerance(45000, details)[0])
        self.assertFalse(weight_within_rto_tolerance(44499, details)[0])
        self.assertFalse(weight_within_rto_tolerance(45001, details)[0])
        self.assertFalse(weight_within_rto_tolerance(26000, details)[0])

    def test_gross_band_matches_vadaghat(self):
        lo, hi, trip = rto_weight_band(GROSS_DETAILS)
        self.assertEqual(trip, "G")
        self.assertEqual((lo, hi), (44500, 45000))
        self.assertTrue(weight_within_rto_tolerance(44750, GROSS_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(46000, GROSS_DETAILS)[0])

    def test_prefix_selects_tare_vs_vadaghat_vs_gross_field(self):
        """Same numbers; only the first pipe field changes which RTO weight is used."""
        t_lo, t_hi, t_trip = rto_weight_band(TARE_DETAILS)
        v_lo, v_hi, v_trip = rto_weight_band(VADAGHAT_DETAILS)
        g_lo, g_hi, g_trip = rto_weight_band(GROSS_DETAILS)
        self.assertEqual((t_trip, t_lo, t_hi), ("T", 14500, 15500))
        self.assertEqual((v_trip, v_lo, v_hi), ("V", 44500, 45000))
        self.assertEqual((g_trip, g_lo, g_hi), ("G", 44500, 45000))
        self.assertTrue(weight_within_rto_tolerance(15000, TARE_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(15000, VADAGHAT_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(15000, GROSS_DETAILS)[0])
        self.assertTrue(weight_within_rto_tolerance(44750, VADAGHAT_DETAILS)[0])
        self.assertFalse(weight_within_rto_tolerance(44750, TARE_DETAILS)[0])

    def test_vadhghat_delta_is_minus_only(self):
        details = (
            "V|34161fa820328ee847f17ca0|GJ12CT8178|45000|1500|50|"
            "9582209263|10.80.118.140|GJ12CT8177"
        )
        self.assertEqual(vadhghat_weight_delta(45000, details), ("o", 0))
        self.assertEqual(vadhghat_weight_delta(44950, details), ("o", 0))
        self.assertEqual(vadhghat_weight_delta(45010, details), ("o", 10))
        self.assertEqual(vadhghat_weight_delta(44940, details), ("u", 10))

    def test_unknown_prefix_skips_check(self):
        ok, _ = weight_within_rto_tolerance(
            99999,
            "X|D2030DBE|OD14AE3900|45000|15000|500|TOK|IP|OD14AE3900",
        )
        self.assertTrue(ok)

    def test_replace_tolerance_field(self):
        updated = replace_truck_details_tolerance(TARE_DETAILS, 25550)
        self.assertEqual(
            updated,
            "T|D2030DBE|OD14AE3900|45000|15000|25550|9581208263|IP244245525163|OD14AE3900",
        )
        lo, hi, trip = rto_weight_band(updated)
        self.assertEqual(trip, "T")
        self.assertEqual((lo, hi), (15000 - 25550, 15000 + 25550))


class TestFinalWeightToleranceWorkflow(unittest.TestCase):
    def _make_workflow(self, truck_details: str, weight: float):
        from config.constants import State
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import MinesWbWorkflow
        from services.oci_client import OCIResponse

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = MagicMock()
        ctx.settings.device_ip = "192.168.10.223"
        ctx.settings.top_camera_rtsp_url = ""
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.transactions.truck_details = truck_details
        ctx.transactions.vehicle_no = "OD14AE3900"
        ctx.oci = MagicMock()
        ctx.oci.reset_checkpoint.return_value = OCIResponse(
            ok=True, status=200, http_status=200
        )
        ctx.oci.weight_details.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.boom_close.return_value = OCIResponse(ok=True, status=200)
        ctx.oci.vadhghat_weight_adjustment.return_value = OCIResponse(
            ok=True, status=200, http_status=200, message="adjusted"
        )
        ctx.oci.vadhghat_weight_details.return_value = OCIResponse(
            ok=True, status=200, http_status=200
        )
        ctx.oci.vadhghat_boom_close.return_value = OCIResponse(
            ok=True, status=200, http_status=200
        )
        ctx.digitizer = MagicMock()
        ctx.digitizer.read_stable_weight.return_value = {
            "ok": True,
            "weight": weight,
        }
        ctx.display = MagicMock()
        ctx.voice = MagicMock()
        ctx.entry_tl = MagicMock()
        ctx.exit_tl = MagicMock()
        ctx.entry_boom = MagicMock()
        ctx.exit_boom = MagicMock()
        ctx.state_machine.force_state(State.FINAL_WEIGHT)
        return MinesWbWorkflow(ctx), ctx

    def test_tare_in_band_submits_weight_details(self):
        from config.constants import State

        wf, ctx = self._make_workflow(TARE_DETAILS, 15000)
        wf._final_weight_and_details(boom_close_after=TARE_DETAILS)
        ctx.oci.weight_details.assert_called_once()
        ctx.oci.boom_close.assert_called_once()
        ctx.voice.speak_weight.assert_called_once_with("t", 15000.0)
        ctx.voice.tare_weight_error.assert_not_called()
        ctx.voice.weight_out_of_tolerance.assert_not_called()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_tare_under_weight_confirm_approved_continues_flow(self):
        """Under-weight → confirm status 1 + recapture in new band → details."""
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(TARE_DETAILS, 14000)
        ctx.oci.weight_confirm.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={"weight_status": "1", "updated_tolerance": 25550},
        )
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=TARE_DETAILS)
        ctx.oci.weight_confirm.assert_called()
        call_kw = ctx.oci.weight_confirm.call_args.kwargs
        self.assertEqual(call_kw["weight_type"], "u")
        self.assertEqual(call_kw["current_weight"], "14000")
        self.assertEqual(ctx.digitizer.read_stable_weight.call_count, 2)
        details_td = ctx.oci.weight_details.call_args.kwargs["truck_details"]
        self.assertIn("|25550|", details_td)
        self.assertEqual(
            ctx.oci.boom_close.call_args.kwargs["truck_details"], details_td
        )
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_tare_over_weight_confirm_approved_continues_flow(self):
        """Over-weight → confirm status 1 + recapture in new band → details."""
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(TARE_DETAILS, 16000)
        ctx.oci.weight_confirm.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={"weight_status": "1", "updated_tolerance": 25550},
        )
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=TARE_DETAILS)
        ctx.oci.weight_confirm.assert_called()
        call_kw = ctx.oci.weight_confirm.call_args.kwargs
        self.assertEqual(call_kw["weight_type"], "o")
        self.assertEqual(call_kw["current_weight"], "16000")
        ctx.oci.weight_details.assert_called_once()
        self.assertIn("|25550|", ctx.oci.weight_details.call_args.kwargs["truck_details"])
        ctx.oci.boom_close.assert_called_once()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_tare_out_of_band_rejected_skips_details(self):
        """weight_status=2 → skip weight_details & boom_close, just exit."""
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(TARE_DETAILS, 16000)
        ctx.oci.weight_confirm.return_value = OCIResponse(
            ok=True, status=2, raw={"weight_status": "2"}
        )
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=TARE_DETAILS)
        ctx.oci.weight_confirm.assert_called()
        ctx.oci.weight_details.assert_not_called()
        ctx.oci.boom_close.assert_not_called()
        ctx.display.send.assert_any_call("TARE WT ERR", side=None)
        ctx.voice.weight_out_of_tolerance.assert_called_with("T")
        ctx.voice.speak_weight.assert_not_called()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_weight_confirm_polls_until_status_1(self):
        """weight_status=0 retries, then status 1 recaptures and continues."""
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(TARE_DETAILS, 16000)
        ctx.oci.weight_confirm.side_effect = [
            OCIResponse(
                ok=True,
                status=0,
                raw={"weight_status": "0", "updated_tolerance": 0},
            ),
            OCIResponse(
                ok=True,
                status=0,
                raw={"weight_status": "0", "updated_tolerance": 0},
            ),
            OCIResponse(
                ok=True,
                status=1,
                raw={"weight_status": "1", "updated_tolerance": 25550},
            ),
        ]
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=TARE_DETAILS)
        self.assertEqual(ctx.oci.weight_confirm.call_count, 3)
        ctx.oci.weight_details.assert_called_once()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_recapture_still_out_confirms_again_with_updated_tolerance(self):
        """Status 1 with tight tolerance → recapture still out → confirm again."""
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(TARE_DETAILS, 16000)
        ctx.oci.weight_confirm.side_effect = [
            OCIResponse(
                ok=True,
                status=1,
                raw={"weight_status": "1", "updated_tolerance": 50},
            ),
            OCIResponse(
                ok=True,
                status=1,
                raw={"weight_status": "1", "updated_tolerance": 20000},
            ),
        ]
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=TARE_DETAILS)
        self.assertEqual(ctx.oci.weight_confirm.call_count, 2)
        second = ctx.oci.weight_confirm.call_args_list[1].kwargs
        self.assertIn("|50|", second["truck_details"])
        self.assertEqual(second["weight_type"], "o")
        details_td = ctx.oci.weight_details.call_args.kwargs["truck_details"]
        self.assertIn("|20000|", details_td)
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_gross_in_band_weight_details_200_skips_confirm(self):
        """G + weight-details 200 → boom_close, no weight-confirm / gross-confirm."""
        from config.constants import State

        wf, ctx = self._make_workflow(GROSS_DETAILS, 44750)
        wf._final_weight_and_details(boom_close_after=GROSS_DETAILS)
        ctx.oci.weight_confirm.assert_not_called()
        ctx.oci.gross_tolerance_confirm.assert_not_called()
        ctx.oci.weight_details.assert_called_once()
        ctx.oci.boom_close.assert_called_once()
        ctx.voice.speak_weight.assert_called_once_with("g", 44750.0)
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_gross_weight_details_201_confirm_ok_resubmits_details(self):
        """G + 201 → gross-tolerance-confirm 1 in-band → second weight-details."""
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(GROSS_DETAILS, 42000)
        ctx.oci.weight_details.side_effect = [
            OCIResponse(ok=False, status=201, raw={"status": 201}),
            OCIResponse(ok=True, status=200, raw={"status": 200}),
        ]
        ctx.oci.gross_tolerance_confirm.return_value = OCIResponse(
            ok=True,
            status=1,
            raw={"tolerance_status": "1", "gross_tolerance": 3000},
        )
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=GROSS_DETAILS)
        ctx.oci.weight_confirm.assert_not_called()
        ctx.oci.gross_tolerance_confirm.assert_called()
        call_kw = ctx.oci.gross_tolerance_confirm.call_args.kwargs
        self.assertEqual(call_kw["current_weight"], "42000")
        self.assertEqual(call_kw["device_ip"], "192.168.10.223")
        self.assertEqual(ctx.oci.weight_details.call_count, 2)
        details_td = ctx.oci.weight_details.call_args_list[1].kwargs["truck_details"]
        self.assertIn("|3000|", details_td)
        ctx.oci.boom_close.assert_called_once()
        self.assertEqual(
            ctx.oci.boom_close.call_args.kwargs["truck_details"], details_td
        )
        ctx.voice.speak_weight.assert_called_once_with("g", 42000.0)
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_gross_tolerance_status_2_skips_second_details_opens_boom(self):
        from config.constants import State
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(GROSS_DETAILS, 42000)
        ctx.oci.weight_details.return_value = OCIResponse(
            ok=False, status=201, raw={"status": 201}
        )
        ctx.oci.gross_tolerance_confirm.return_value = OCIResponse(
            ok=True, status=2, raw={"tolerance_status": "2", "gross_tolerance": 0}
        )
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=GROSS_DETAILS)
        ctx.oci.weight_confirm.assert_not_called()
        ctx.oci.weight_details.assert_called_once()
        ctx.oci.boom_close.assert_called_once()
        ctx.voice.speak_weight.assert_not_called()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_gross_tolerance_polls_until_status_1_in_band(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(GROSS_DETAILS, 42000)
        ctx.oci.weight_details.side_effect = [
            OCIResponse(ok=False, status=201, raw={"status": 201}),
            OCIResponse(ok=True, status=200, raw={"status": 200}),
        ]
        ctx.oci.gross_tolerance_confirm.side_effect = [
            OCIResponse(
                ok=True, status=0, raw={"tolerance_status": "0", "gross_tolerance": 0}
            ),
            OCIResponse(
                ok=True, status=0, raw={"tolerance_status": "0", "gross_tolerance": 0}
            ),
            OCIResponse(
                ok=True,
                status=1,
                raw={"tolerance_status": "1", "gross_tolerance": 3000},
            ),
        ]
        with patch("core.workflow.time.sleep", return_value=None):
            wf._final_weight_and_details(boom_close_after=GROSS_DETAILS)
        self.assertEqual(ctx.oci.gross_tolerance_confirm.call_count, 3)
        ctx.oci.weight_confirm.assert_not_called()
        ctx.oci.vadhghat_weight_adjustment.assert_not_called()
        self.assertEqual(ctx.oci.weight_details.call_count, 2)

    def test_gross_out_of_band_skips_weight_confirm(self):
        """G/V no longer use tare weight-confirm; they post weight-details first."""
        wf, ctx = self._make_workflow(GROSS_DETAILS, 44000)
        wf._final_weight_and_details(boom_close_after=GROSS_DETAILS)
        ctx.oci.weight_confirm.assert_not_called()
        ctx.oci.vadhghat_weight_adjustment.assert_not_called()
        ctx.oci.weight_details.assert_called_once()
        ctx.oci.boom_close.assert_called_once()

    def test_vadaghat_in_band_posts_details_and_boom_close(self):
        from config.constants import State

        wf, ctx = self._make_workflow(VADAGHAT_DETAILS, 44750)
        wf._final_weight_and_details(boom_close_after=VADAGHAT_DETAILS)
        ctx.oci.vadhghat_weight_adjustment.assert_not_called()
        ctx.oci.weight_details.assert_not_called()
        ctx.oci.boom_close.assert_not_called()
        ctx.oci.vadhghat_weight_details.assert_called_once()
        ctx.oci.vadhghat_boom_close.assert_called_once()
        ctx.voice.speak_weight.assert_called_once_with("g", 44750.0)
        ctx.voice.move_forward.assert_called()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_vadaghat_over_weight_calls_adjustment_skips_boom_close(self):
        from config.constants import State

        wf, ctx = self._make_workflow(VADAGHAT_DETAILS, 46000)
        wf._final_weight_and_details(boom_close_after=VADAGHAT_DETAILS)
        ctx.oci.vadhghat_weight_adjustment.assert_called_once()
        call_kw = ctx.oci.vadhghat_weight_adjustment.call_args.kwargs
        self.assertEqual(call_kw["weight"], 46000)
        self.assertEqual(call_kw["weight_type"], "o")
        self.assertEqual(call_kw["device_ip"], "192.168.10.223")
        self.assertEqual(call_kw["truck_details"], VADAGHAT_DETAILS)
        ctx.oci.weight_details.assert_not_called()
        ctx.oci.boom_close.assert_not_called()
        ctx.oci.vadhghat_weight_details.assert_not_called()
        ctx.oci.vadhghat_boom_close.assert_not_called()
        ctx.oci.weight_confirm.assert_not_called()
        ctx.voice.weight_out_of_tolerance.assert_not_called()
        ctx.voice.vadhghat_difference.assert_any_call("o", 1000, intro=True)
        ctx.voice.move_forward.assert_not_called()
        ctx.voice.speak_weight.assert_not_called()
        ctx.display.send.assert_any_call("Overweight@1000Kg", side=None)
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_vadaghat_under_weight_calls_adjustment_with_u(self):
        from config.constants import State

        wf, ctx = self._make_workflow(VADAGHAT_DETAILS, 44000)
        wf._final_weight_and_details(boom_close_after=VADAGHAT_DETAILS)
        call_kw = ctx.oci.vadhghat_weight_adjustment.call_args.kwargs
        self.assertEqual(call_kw["weight_type"], "u")
        self.assertEqual(call_kw["weight"], 44000)
        ctx.oci.weight_details.assert_not_called()
        ctx.oci.boom_close.assert_not_called()
        ctx.oci.vadhghat_weight_details.assert_not_called()
        ctx.oci.vadhghat_boom_close.assert_not_called()
        ctx.voice.weight_out_of_tolerance.assert_not_called()
        ctx.voice.vadhghat_difference.assert_any_call("u", 500, intro=True)
        ctx.voice.move_forward.assert_not_called()
        ctx.voice.speak_weight.assert_not_called()
        ctx.display.send.assert_any_call("Underweight@500Kg", side=None)
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

    def test_weight_details_non_200_does_not_announce(self):
        from services.oci_client import OCIResponse

        wf, ctx = self._make_workflow(GROSS_DETAILS, 44750)
        ctx.oci.weight_details.return_value = OCIResponse(
            ok=False, status=409, http_status=409
        )
        wf._final_weight_and_details(boom_close_after=GROSS_DETAILS)
        ctx.voice.speak_weight.assert_not_called()
        ctx.voice.weight_submit_error_by_status.assert_called()
    def test_payload_matches_gmdc_contract(self):
        details = (
            "V|E28068940000503F548F04BA|OD14P7339|45000|24500|50|9580109261|10.10.180.12"
        )
        payload = build_vadhghat_weight_adjustment_payload(
            device_ip="10.10.180.12",
            truck_details=details,
            weight=44990,
            weight_type="o/u",
        )
        self.assertEqual(
            payload,
            {
                "device_ip": "10.10.180.12",
                "truck_details": details,
                "weight": 44990,
                "weight_type": "o",
            },
        )
        self.assertEqual(under_or_over_type(44990, details), "o")
        self.assertEqual(under_or_over_type(44940, details), "u")

    @patch("services.oci_client.requests.Session.post")
    def test_client_posts_adjustment_with_gmdc_auth(self, mock_post):
        from services.oci_client import OCIClient

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "status": 200,
            "response_type": 1,
            "message": "Vadhghat weight adjustment processed successfully.",
        }
        mock_resp.text = "{}"
        mock_post.return_value = mock_resp
        client = OCIClient(
            base_url="https://gmuatociexp.gmdcltd.co.in",
            username="user",
            password="pass",
            rfid_validate_url="https://x/rfid",
            anpr_detect_url="https://x/anpr",
            invalid_truck_url="https://x/inv",
            update_truck_url="https://x/upd",
            weight_details_url="https://x/wd",
            endpoint_auth={
                "vadhghat_weight_adjustment": ("GMDC_API_USERS", "GMDC@123"),
            },
        )
        details = (
            "V|E28068940000503F548F04BA|OD14P7339|45000|24500|50|"
            "9580109261|10.10.180.12"
        )
        resp = client.vadhghat_weight_adjustment(
            device_ip="10.10.180.12",
            truck_details=details,
            weight=44990.0,
            weight_type="o",
        )
        self.assertTrue(resp.ok)
        self.assertEqual(resp.status, 200)
        sent = mock_post.call_args.kwargs["json"]
        self.assertEqual(sent["device_ip"], "10.10.180.12")
        self.assertEqual(sent["truck_details"], details)
        self.assertEqual(sent["weight"], 44990)
        self.assertEqual(sent["weight_type"], "o")
        self.assertEqual(
            mock_post.call_args.kwargs["auth"],
            ("GMDC_API_USERS", "GMDC@123"),
        )
        self.assertIn("vadhghat_weight_adjustment", mock_post.call_args.args[0])


class TestWeightVoiceClips(unittest.TestCase):
    def test_maps_kg_to_ton_and_10kg_filenames(self):
        from services.voice_service import VoiceService

        self.assertEqual(VoiceService.weight_clip_parts(15000), (15, 0))
        self.assertEqual(VoiceService.weight_clip_parts(12500), (12, 500))
        self.assertEqual(VoiceService.weight_clip_parts(44750), (44, 750))
        self.assertEqual(VoiceService.weight_clip_parts(12505), (12, 510))
        self.assertEqual(VoiceService.weight_clip_parts(12995), (13, 0))


if __name__ == "__main__":
    unittest.main()
