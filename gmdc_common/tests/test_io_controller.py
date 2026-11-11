"""Strict Modbus I/O mapping, last-value sensors, honest boom/TL writes."""

from __future__ import annotations

import sys
import time
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


class _FakeBits:
    def __init__(self, bits, error=False):
        self.bits = list(bits)
        self._error = error

    def isError(self):
        return self._error


class ModbusSoftFailDebounceTests(unittest.TestCase):
    def test_resync_threshold_is_debounced(self):
        self.assertEqual(ModbusTCPController.RESYNC_AFTER_FAILURES, 3)
        self.assertEqual(ModbusTCPController.CLEAR_FAILURES_AFTER_SUCCESSES, 3)

    def _controller(self):
        ctrl = ModbusTCPController(host="10.80.118.136", port=502)
        ctrl._client = MagicMock()
        ctrl._client.connected = True
        ctrl._healthy = True
        return ctrl

    def test_single_modbus_exception_keeps_socket_and_health(self):
        ctrl = self._controller()
        health = []
        ctrl.set_health_callback(lambda ok, msg: health.append((ok, msg)))
        ctrl._client.read_discrete_inputs.return_value = _FakeBits([], error=True)

        self.assertIsNone(ctrl.read_discrete_inputs(1, 1))
        self.assertEqual(ctrl._failures, 1)
        self.assertTrue(ctrl._healthy)
        self.assertEqual(health, [])
        ctrl._client.close.assert_not_called()

    def test_three_soft_fails_resync_and_lock(self):
        ctrl = self._controller()
        client = ctrl._client
        health = []
        ctrl.set_health_callback(lambda ok, msg: health.append((ok, msg)))
        client.read_discrete_inputs.return_value = _FakeBits([], error=True)
        # Avoid real TCP on the reconnect path after threshold.
        ctrl._connect_locked = MagicMock(return_value=True)

        for _ in range(3):
            self.assertIsNone(ctrl.read_discrete_inputs(1, 1))

        time.sleep(0.05)
        self.assertFalse(ctrl._healthy)
        self.assertTrue(any(ok is False for ok, _ in health))
        client.close.assert_called()
        ctrl._connect_locked.assert_called()

    def test_second_soft_fail_reconnects_and_returns_fresh_input(self):
        ctrl = self._controller()
        client = ctrl._client
        client.read_discrete_inputs.side_effect = [
            _FakeBits([], error=True),
            _FakeBits([], error=True),
            _FakeBits([True], error=False),
        ]
        original_connect = ctrl._connect_locked

        def reconnect():
            # Reconnect the same fake client, as ModbusTcpClient would.
            ctrl._client = client
            client.connected = True
            return True

        ctrl._connect_locked = MagicMock(side_effect=reconnect)

        self.assertIsNone(ctrl.read_discrete_inputs(1, 1))
        self.assertEqual(ctrl._failures, 1)
        self.assertEqual(ctrl.read_discrete_inputs(1, 1), [True])
        self.assertEqual(ctrl._failures, 0)
        ctrl._connect_locked.assert_called_once()
        client.close.assert_called_once()

    def test_second_wb_failure_reconnects_before_fresh_retry(self):
        """Healthy entry/exit reads do not prevent the WB reconnect retry."""
        ctrl = self._controller()
        client = ctrl._client
        health = []
        ctrl.set_health_callback(lambda ok, msg: health.append((ok, msg)))
        ctrl._connect_locked = MagicMock(
            side_effect=lambda: setattr(ctrl, "_client", client) or True
        )

        def read_side_effect(*args, **kwargs):
            address = kwargs.get("address", args[0] if args else None)
            if address == 1:
                return _FakeBits([], error=True)
            return _FakeBits([False], error=False)

        ctrl._client.read_discrete_inputs.side_effect = read_side_effect

        # First WB failure is returned to the poller. The second WB failure
        # reconnects, then the fresh read still fails and marks I/O down.
        for _ in range(2):
            self.assertIsNotNone(ctrl.read_discrete_inputs(0, 1))
            self.assertIsNotNone(ctrl.read_discrete_inputs(2, 1))
            wb = ctrl.read_discrete_inputs(1, 1)

        time.sleep(0.05)
        self.assertIsNone(wb)
        self.assertFalse(ctrl._healthy)
        self.assertTrue(any(ok is False for ok, _ in health))
        # One reconnect before the fresh retry, and one after the third
        # failed read when the controller is marked unhealthy.
        self.assertEqual(ctrl._connect_locked.call_count, 2)

    def test_hard_transport_error_resyncs_immediately(self):
        ctrl = self._controller()
        health = []
        ctrl.set_health_callback(lambda ok, msg: health.append((ok, msg)))
        ctrl._client.read_discrete_inputs.side_effect = ConnectionError("reset")
        ctrl._connect_locked = MagicMock(return_value=True)

        self.assertIsNone(ctrl.read_discrete_inputs(1, 1))
        time.sleep(0.05)
        self.assertFalse(ctrl._healthy)
        self.assertTrue(any(ok is False for ok, _ in health))
        ctrl._connect_locked.assert_called()


if __name__ == "__main__":
    unittest.main()
