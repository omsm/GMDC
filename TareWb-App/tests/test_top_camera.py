"""Top camera filename / capture helpers."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "gmdc_common"))

os.environ.setdefault("DEMO_MODE", "true")

from gmdc_common.hardware.camera import (  # noqa: E402
    build_top_photo_filename,
    get_local_ip,
)


class TestTopPhotoNaming(unittest.TestCase):
    def test_filename_shape(self):
        name = build_top_photo_filename(
            token_no="TRIP-20260715-001",
            truck_no="OD05CA3273",
            checkpoint_ip="192.168.10.223",
            when=datetime(2026, 8, 6, 19, 54, 30),
        )
        self.assertEqual(
            name,
            "TRIP-20260715-001_06-08-26-19-54-30_OD05CA3273_192.168.10.223_TOP.jpg",
        )

    def test_sanitizes_unsafe_chars(self):
        name = build_top_photo_filename(
            token_no="A/B C",
            truck_no="OD*05",
            checkpoint_ip="10.0.0.1",
            when=datetime(2026, 1, 2, 3, 4, 5),
        )
        self.assertEqual(name, "A_B_C_02-01-26-03-04-05_OD_05_10.0.0.1_TOP.jpg")

    def test_local_ip_fallback(self):
        ip = get_local_ip(fallback="9.9.9.9")
        self.assertTrue(ip)
        self.assertNotIn(" ", ip)


class TestCaptureTopPhotoWorkflow(unittest.TestCase):
    def test_capture_uses_rtsp_and_sets_txn(self):
        from core.app_context import AppContext
        from core.transaction import TransactionStore
        from core.workflow import TareWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = MagicMock()
        ctx.settings.device_ip = "192.168.10.223"
        ctx.settings.top_camera_rtsp_url = "rtsp://cam/stream"
        ctx.transactions = TransactionStore()
        ctx.transactions.vehicle_no = "OD05CA3273"
        ctx.transactions.truck_details = (
            "T|RFID|OD05CA3273|0|0|0|TOK99|192.168.10.223"
        )
        wf = TareWbWorkflow(ctx)

        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            with patch("core.workflow.IMAGES_DIR", images), patch(
                "core.workflow.capture_rtsp_snapshot", return_value=True
            ) as snap, patch(
                "core.workflow.get_local_ip", return_value="10.30.1.102"
            ), patch(
                "core.workflow.build_top_photo_filename",
                return_value="TOK99_06-08-26-19-00-00_OD05CA3273_10.30.1.102_TOP.jpg",
            ):
                wf._capture_top_photo()
                snap.assert_called_once()
                self.assertEqual(
                    ctx.transactions.top_image,
                    "TOK99_06-08-26-19-00-00_OD05CA3273_10.30.1.102_TOP.jpg",
                )
                self.assertEqual(
                    ctx.transactions.anpr_raw.get("top_image"),
                    ctx.transactions.top_image,
                )

    def test_capture_failure_uses_error_jpg(self):
        from core.app_context import AppContext
        from core.transaction import TransactionStore
        from core.workflow import TareWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = MagicMock()
        ctx.settings.device_ip = "192.168.10.223"
        ctx.settings.top_camera_rtsp_url = "rtsp://cam/stream"
        ctx.transactions = TransactionStore()
        ctx.transactions.vehicle_no = "OD05CA3273"
        ctx.transactions.truck_details = (
            "T|RFID|OD05CA3273|0|0|0|TOK99|192.168.10.223"
        )
        wf = TareWbWorkflow(ctx)

        with tempfile.TemporaryDirectory() as tmp:
            images = Path(tmp)
            with patch("core.workflow.IMAGES_DIR", images), patch(
                "core.workflow.capture_rtsp_snapshot", return_value=False
            ), patch(
                "core.workflow.get_local_ip", return_value="10.30.1.102"
            ):
                wf._capture_top_photo()
                self.assertEqual(ctx.transactions.top_image, "error.jpg")
                self.assertEqual(
                    ctx.transactions.anpr_raw.get("top_image"), "error.jpg"
                )
                self.assertTrue((images / "error.jpg").exists())


if __name__ == "__main__":
    unittest.main()
