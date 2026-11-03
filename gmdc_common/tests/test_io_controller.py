"""Strict Modbus I/O mapping, last-value sensors, honest boom/TL writes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gmdc_common.hardware.boom_barrier import BoomBarrier
from gmdc_common.hardware.io_controller import (
    DemoIOController,
    LOCALHOST_HOSTS,
    ModbusTCPController,
    create_io_controller,
    is_controller_host_configured,
)
from gmdc_common.hardware.sensor import SensorPoller
from gmdc_common.hardware.traffic_light import TrafficLight


class CreateIOControllerTests(unittest.TestCase):
    def test_localhost_marked_not_configured(self):
        io = create_io_controller(
            {
                "connection": {"ethernet": {"ip": "127.0.0.1", "port": 502}},
                "digital_inputs": {"function_code": 2, "start_address": 0},
                "digital_outputs": {"function_code": 5, "start_address": 0},
            },
            demo_mode=False,
        )
        self.assertFalse(io.is_configured())
        self.assertFalse(io.connect())
        st = io.get_status()
        self.assertFalse(st.get("configured"))
        self.assertIn("not configured", st.get("last_error", "").lower())

    def test_rejects_invalid_function_codes(self):
        with self.assertRaises(ValueError):
            create_io_controller(
                {
                    "connection": {"ethernet": {"ip": "192.168.1.10"}},
                    "digital_inputs": {"function_code": 3},
                    "digital_outputs": {"function_code": 5},
                }
            )
        with self.assertRaises(ValueError):
            create_io_controller(
                {
                    "connection": {"ethernet": {"ip": "192.168.1.10"}},
                    "digital_inputs": {"function_code": 2},
                    "digital_outputs": {"function_code": 15},
                }
            )

    def test_requires_function_codes(self):
        with self.assertRaises(ValueError):
            create_io_controller(
                {
                    "connection": {"ethernet": {"ip": "192.168.1.10"}},
                    "digital_inputs": {},
                    "digital_outputs": {"function_code": 5},
                }
            )

    def test_host_helper(self):
        self.assertFalse(is_controller_host_configured("127.0.0.1"))
        self.assertFalse(is_controller_host_configured(""))
        self.assertTrue(is_controller_host_configured("192.168.31.89"))
        for host in LOCALHOST_HOSTS:
            self.assertFalse(is_controller_host_configured(host))


class SensorRealtimeTests(unittest.TestCase):
    def test_no_fc1_fallback_and_clears_on_read_failure(self):
        io = MagicMock()
        io.read_fc = 2
        io.read_discrete_inputs.side_effect = [
            [True],
            None,
            [False],
        ]
        io.read_coils.side_effect = AssertionError("FC1 fallback must not run")

        edges = []
        poller = SensorPoller(
            io,
            entry_pin=0,
            di_start_address=0,
            on_entry=lambda: edges.append("clear"),
            on_entry_occupied=lambda: edges.append("occ"),
        )
        self.assertTrue(poller._read_active(0))
        poller._last_entry = True
        poller._prev_entry = True
        poller._entry_occupied = True

        # Failed read → realtime clear (no ghost clear callback).
        self.assertIsNone(poller._read_active(0))
        io.read_coils.assert_not_called()
        poller._mark_failure()
        self.assertFalse(poller._last_entry)
        self.assertFalse(poller._entry_occupied)
        self.assertFalse(poller._prev_entry)
        self.assertEqual(edges, [])

        self.assertFalse(poller._read_active(0))


class BoomAndTrafficHonestyTests(unittest.TestCase):
    def test_boom_disabled_rejects(self):
        io = DemoIOController()
        io.connect()
        boom = BoomBarrier(io, open_pin=2, enabled=False, name="entry")
        self.assertFalse(boom.open())
        self.assertEqual(boom.get_status()["state"], "unknown")
        self.assertFalse(boom.close())

    def test_boom_missing_pins_rejects(self):
        io = DemoIOController()
        io.connect()
        boom = BoomBarrier(io, enabled=True, name="entry")
        self.assertFalse(boom.open())
        self.assertFalse(boom.close())

    def test_boom_failed_write_keeps_state(self):
        io = DemoIOController()
        io.connect()
        boom = BoomBarrier(io, open_pin=2, enabled=True, name="entry")
        self.assertTrue(boom.open())
        self.assertEqual(boom.get_status()["state"], "open")
        io.write_coil = MagicMock(return_value=False)
        self.assertFalse(boom.close())
        self.assertEqual(boom.get_status()["state"], "open")

    def test_traffic_light_missing_pins_rejects(self):
        io = DemoIOController()
        io.connect()
        tl = TrafficLight(io, name="entry")
        self.assertFalse(tl.set_red())
        self.assertFalse(tl.set_green())
        self.assertEqual(tl.get_status()["state"], "unknown")

    def test_traffic_light_failed_write_keeps_state(self):
        io = DemoIOController()
        io.connect()
        tl = TrafficLight(io, red_pin=0, name="entry", relay_on_green=True)
        self.assertTrue(tl.set_green())
        self.assertEqual(tl.get_status()["state"], "green")
        io.write_coil = MagicMock(return_value=False)
        self.assertFalse(tl.set_red())
        self.assertEqual(tl.get_status()["state"], "green")


class ModbusImmediateResyncTests(unittest.TestCase):
    def test_resync_threshold_is_immediate(self):
        self.assertEqual(ModbusTCPController.RESYNC_AFTER_FAILURES, 1)


if __name__ == "__main__":
    unittest.main()
