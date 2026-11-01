"""Per-lane daily log routing for Mines-Checkpoint."""

from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "gmdc_common"))


class TestLaneLogging(unittest.TestCase):
    def test_slug_and_scope_route_to_lane_files(self):
        from utils.logging_setup import (
            KEEP_DAYS,
            lane_log_scope,
            setup_logging,
            slug_lane_name,
        )

        self.assertEqual(slug_lane_name("Mines Entry"), "mines_entry")
        self.assertEqual(slug_lane_name("Traffic IN"), "traffic_in")
        self.assertEqual(KEEP_DAYS, 10)

        tmp = tempfile.mkdtemp()
        log_dir = Path(tmp) / "logs"
        try:
            with patch("utils.logging_setup.LOG_DIR", log_dir):
                setup_logging(
                    lane_ids=["mines_entry", "traffic_in", "traffic_out", "mines_exit"]
                )
                log = logging.getLogger("mines_checkpoint.test_lane")
                with lane_log_scope("mines_entry"):
                    log.info("entry-only-line")
                with lane_log_scope("traffic_in"):
                    log.info("traffic-in-only-line")
                log.info("shared-main-line")

                from utils.logging_setup import _close_root_handlers

                _close_root_handlers()

                entry = (log_dir / "mines_entry" / "mines_entry.log").read_text(
                    encoding="utf-8"
                )
                traffic = (log_dir / "traffic_in" / "traffic_in.log").read_text(
                    encoding="utf-8"
                )
                main = (log_dir / "main" / "mines_checkpoint.log").read_text(
                    encoding="utf-8"
                )

                self.assertIn("entry-only-line", entry)
                self.assertNotIn("traffic-in-only-line", entry)
                self.assertIn("traffic-in-only-line", traffic)
                self.assertNotIn("entry-only-line", traffic)
                self.assertIn("shared-main-line", main)
                self.assertNotIn("entry-only-line", main)
        finally:
            from utils.logging_setup import _close_root_handlers

            _close_root_handlers()
            try:
                import shutil

                shutil.rmtree(tmp, ignore_errors=True)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
