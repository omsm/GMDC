"""Decoder runtime: current weight only; streak is UI view-only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.weight_runtime import WeightRuntime


class WeightRuntimeTests(unittest.TestCase):
    def test_http_returns_current_without_waiting_for_ten(self):
        rt = WeightRuntime()
        rt.set_connected(True)
        rt.push_weight(25000.0, "raw", b"raw")
        # Only 1 sample — old wait_stable would block / fail; now returns current.
        result = rt.current_weight_response()
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(result["current_weight"], 25000.0)
        self.assertEqual(result["stable_weight"], 25000.0)
        snap = rt.snapshot()
        self.assertFalse(snap["stable"])
        self.assertEqual(snap["stable_count"], "1/10")

    def test_view_streak_reaches_ten_for_ui_only(self):
        rt = WeightRuntime()
        rt.set_connected(True)
        for _ in range(10):
            rt.push_weight(25050.0, "raw", b"raw")
        snap = rt.snapshot()
        self.assertTrue(snap["stable"])
        self.assertEqual(snap["stable_weight"], 25050.0)
        self.assertEqual(snap["stable_count"], "10/10")
        # Still just current weight for consumers.
        result = rt.wait_stable()
        self.assertEqual(result["current_weight"], 25050.0)

    def test_mqtt_style_current_updates_every_push(self):
        rt = WeightRuntime()
        rt.set_connected(True)
        rt.push_weight(25000.0, "a", b"a")
        rt.push_weight(25100.0, "b", b"b")
        self.assertEqual(rt.snapshot()["current_weight"], 25100.0)
        self.assertEqual(rt.current_weight_response()["current_weight"], 25100.0)


if __name__ == "__main__":
    unittest.main()
