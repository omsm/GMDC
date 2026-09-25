"""Tests for bidirectional traffic light finalize validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.config_manager import (
    ConfigManager,
    _bidirectional_tl_structure_complete,
    _migrate_traffic_lights_to_bidirectional,
    validate_bidirectional_traffic_lights,
)


def _bi_io(
    entry_a_entry_validated=True,
    entry_a_exit_validated=True,
    entry_b_entry_validated=True,
    entry_b_exit_validated=True,
    entry_a_pins=None,
    entry_b_pins=None,
):
    """Minimal bidirectional I/O block for validate_bidirectional_traffic_lights."""
    entry_a_pins = entry_a_pins or {
        "entry": {"red_pin": "0", "green_pin": "1"},
        "exit": {"red_pin": "2", "green_pin": "3"},
    }
    entry_b_pins = entry_b_pins or {
        "entry": {"red_pin": "4", "green_pin": "5"},
        "exit": {"red_pin": "6", "green_pin": "7"},
    }

    def side_meta(validated):
        return {"make": "", "model": "", "validated": validated}

    return {
        "output_mode": "direct",
        "traffic_lights": {
            "mode": "direct",
            "direct": {
                "entry_a": entry_a_pins,
                "entry_b": entry_b_pins,
            },
            "entry_a": {
                "entry": side_meta(entry_a_entry_validated),
                "exit": side_meta(entry_a_exit_validated),
            },
            "entry_b": {
                "entry": side_meta(entry_b_entry_validated),
                "exit": side_meta(entry_b_exit_validated),
            },
        },
    }


class TestValidateBidirectionalTrafficLights(unittest.TestCase):
    def test_unidirectional_returns_none(self):
        io = _bi_io()
        self.assertIsNone(validate_bidirectional_traffic_lights(io, "unidirectional"))

    def test_all_active_with_pins_ok(self):
        self.assertIsNone(validate_bidirectional_traffic_lights(_bi_io(), "bidirectional"))

    def test_entry_b_skipped_empty_pins_ok(self):
        io = _bi_io(
            entry_b_entry_validated=None,
            entry_b_exit_validated=None,
            entry_b_pins={
                "entry": {"red_pin": "", "green_pin": ""},
                "exit": {"red_pin": "", "green_pin": ""},
            },
        )
        self.assertIsNone(validate_bidirectional_traffic_lights(io, "bidirectional"))

    def test_entry_a_skipped_empty_pins_ok(self):
        io = _bi_io(
            entry_a_entry_validated=None,
            entry_a_exit_validated=None,
            entry_a_pins={
                "entry": {"red_pin": "", "green_pin": ""},
                "exit": {"red_pin": "", "green_pin": ""},
            },
        )
        self.assertIsNone(validate_bidirectional_traffic_lights(io, "bidirectional"))

    def test_single_side_skipped_ok(self):
        io = _bi_io(
            entry_a_entry_validated=None,
            entry_a_pins={
                "entry": {"red_pin": "", "green_pin": ""},
                "exit": {"red_pin": "2", "green_pin": "3"},
            },
        )
        self.assertIsNone(validate_bidirectional_traffic_lights(io, "bidirectional"))

    def test_active_side_missing_red_pin_errors(self):
        io = _bi_io(
            entry_a_pins={
                "entry": {"red_pin": "", "green_pin": "1"},
                "exit": {"red_pin": "2", "green_pin": "3"},
            },
        )
        err = validate_bidirectional_traffic_lights(io, "bidirectional")
        self.assertIsNotNone(err)
        self.assertIn("ENTRY A", err)
        self.assertIn("Entry", err)
        self.assertIn("red pin", err)

    def test_not_tested_false_skips_pin_check(self):
        io = _bi_io(
            entry_b_entry_validated=False,
            entry_b_exit_validated=False,
            entry_b_pins={
                "entry": {"red_pin": "", "green_pin": ""},
                "exit": {"red_pin": "", "green_pin": ""},
            },
        )
        self.assertIsNone(validate_bidirectional_traffic_lights(io, "bidirectional"))


class TestMigrateTrafficLightsPreservesSkip(unittest.TestCase):
    """Regression: debug-skipped TL sides must stay validated=null after sanitize/save."""

    def _user_like_tl(self):
        return {
            "mode": "direct",
            "direct": {
                "entry_a": {
                    "entry": {"red_pin": "0", "green_pin": "1"},
                    "exit": {"red_pin": "2", "green_pin": "3"},
                },
                "entry_b": {
                    "entry": {"red_pin": "", "green_pin": ""},
                    "exit": {"red_pin": "", "green_pin": ""},
                },
            },
            "relay": {},
            "entry_a": {
                "entry": {"make": "", "model": "", "validated": None},
                "exit": {"make": "", "model": "", "validated": None},
            },
            "entry_b": {
                "entry": {"make": "", "model": "", "validated": None},
                "exit": {"make": "", "model": "", "validated": None},
            },
        }

    def test_structure_complete_when_entry_b_skipped(self):
        tl = self._user_like_tl()
        self.assertTrue(_bidirectional_tl_structure_complete(tl))

    def test_migrate_preserves_null_validated(self):
        tl = self._user_like_tl()
        _migrate_traffic_lights_to_bidirectional(tl)
        for direction in ("entry_a", "entry_b"):
            for side in ("entry", "exit"):
                self.assertIsNone(
                    tl[direction][side]["validated"],
                    f"{direction}.{side} should remain skipped (null)",
                )

    def test_legacy_uni_migration_preserves_null_validated(self):
        tl = {
            "mode": "direct",
            "direct": {
                "entry": {"red_pin": "0", "green_pin": "1"},
                "exit": {"red_pin": "2", "green_pin": "3"},
            },
            "entry": {"make": "M", "model": "X", "validated": None},
            "exit": {"make": "", "model": "", "validated": True},
        }
        _migrate_traffic_lights_to_bidirectional(tl)
        self.assertIsNone(tl["entry_a"]["entry"]["validated"])
        self.assertTrue(tl["entry_a"]["exit"]["validated"])

    def test_sanitize_io_controller_preserves_null(self):
        config = {
            "wb_type": "bidirectional",
            "io_controller": {
                "output_mode": "direct",
                "traffic_lights": self._user_like_tl(),
            },
        }
        ConfigManager._sanitize_config_for_layout(config)
        tl = config["io_controller"]["traffic_lights"]
        self.assertIsNone(tl["entry_b"]["entry"]["validated"])
        self.assertIsNone(tl["entry_a"]["entry"]["validated"])


if __name__ == "__main__":
    unittest.main()
