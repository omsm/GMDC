"""Bidirectional approach sensor and RFID reader selection tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestBidirectionalFlow(unittest.TestCase):
    def _make_workflow(self):
        from config.settings import Settings
        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import TareWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = Settings(
            wb_type="bidirectional",
            raw_config={
                "rfids": {
                    "entry_a": {"ip": "192.168.1.10", "mode": "API"},
                    "entry_b": {"ip": "192.168.1.11", "mode": "API"},
                }
            },
        )
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        ctx.rfid_clouds = {
            "entry_a": MagicMock(),
            "entry_b": MagicMock(),
        }
        for cloud in ctx.rfid_clouds.values():
            cloud.prepare_idle.return_value = True
            cloud.stop.return_value = True
        ctx.rfid_cloud = ctx.rfid_clouds["entry_a"]
        ctx.display = MagicMock()
        ctx.entry_tl = MagicMock()
        ctx.exit_tl = MagicMock()
        ctx.entry_boom = MagicMock()
        ctx.exit_boom = MagicMock()
        ctx.voice = MagicMock()

        workflow = TareWbWorkflow(ctx)
        return workflow, ctx

    def test_entry_sensor_selects_entry_a_reader(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        workflow.on_entry_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)
        self.assertEqual(ctx.transactions.direction, "ENTRY_A")
        self.assertEqual(ctx.active_rfid_direction, "")
        # Sensor selection records direction but does not start RFID.
        ctx.rfid_clouds["entry_a"].prepare_idle.assert_not_called()
        ctx.rfid_clouds["entry_b"].prepare_idle.assert_not_called()
        ctx.voice.weighbridge_janch.assert_called_once()
        workflow.force_reset()

    def test_exit_sensor_selects_entry_b_reader_while_idle(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        workflow.on_exit_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)
        self.assertEqual(ctx.transactions.direction, "ENTRY_B")
        self.assertEqual(ctx.active_rfid_direction, "")
        ctx.rfid_clouds["entry_b"].prepare_idle.assert_not_called()
        ctx.rfid_clouds["entry_a"].prepare_idle.assert_not_called()
        ctx.voice.weighbridge_janch.assert_called_once()
        workflow.force_reset()

    def test_rfid_tags_ignored_while_sensor_active(self):
        workflow, ctx = self._make_workflow()
        workflow.on_entry_occupied()

        workflow.on_rfid_tags(["E200001D"])

        self.assertIsNone(workflow._pending_rfid_tags)
        ctx.rfid_clouds["entry_a"].prepare_idle.assert_not_called()
        ctx.rfid_clouds["entry_b"].prepare_idle.assert_not_called()
        workflow.force_reset()

    def test_rfid_starts_only_after_weight_ok(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        workflow.on_exit_occupied()
        ctx.state_machine.force_state(State.RFID_READ)

        workflow._enter_rfid_read()

        ctx.rfid_clouds["entry_b"].prepare_idle.assert_called_once()
        ctx.rfid_clouds["entry_a"].prepare_idle.assert_not_called()
        self.assertEqual(ctx.active_rfid_direction, "entry_b")
        workflow.force_reset()

    def test_rfid_stops_immediately_when_tag_received(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.transactions.direction = "ENTRY_A"
        ctx.state_machine.force_state(State.RFID_READ)
        workflow._awaiting_rfid = True
        workflow._rfid_started_direction = "entry_a"
        # Keep validation from starting; immediate stop happens first.
        workflow._worker_lock.acquire()
        try:
            workflow.on_rfid_tags(["E200001D"])
        finally:
            workflow._worker_lock.release()

        ctx.rfid_clouds["entry_a"].stop.assert_called()
        self.assertEqual(workflow._rfid_started_direction, "")

    def test_entry_b_crossing_completes_on_entry_sensor_clear(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.transactions.direction = "ENTRY_B"
        ctx.state_machine.force_state(State.EXIT_GRANTED)

        workflow.on_entry_occupied()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)

        workflow.on_entry_cleared()
        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        self.assertEqual(ctx.transactions.direction, "")

    def test_entry_b_does_not_reset_on_same_side_exit_sensor(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.transactions.direction = "ENTRY_B"
        ctx.state_machine.force_state(State.EXIT_GRANTED)

        workflow.on_exit_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)
        self.assertEqual(ctx.transactions.direction, "ENTRY_B")

    def test_unidirectional_exit_sensor_does_not_start_vehicle(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.settings.wb_type = "unidirectional"

        workflow.on_exit_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        ctx.rfid_clouds["entry_b"].prepare_idle.assert_not_called()

    def test_exit_crossing_waits_for_uncut_then_defers_boom_close(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.settings.wb_type = "unidirectional"
        ctx.state_machine.force_state(State.EXIT_GRANTED)
        ctx.exit_boom.close.reset_mock()

        workflow.on_exit_occupied()
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)
        ctx.exit_boom.close.assert_not_called()

        workflow.on_exit_cleared()
        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        ctx.exit_boom.close.assert_not_called()
        timer = getattr(workflow, "_boom_close_timer")
        self.assertIsNotNone(timer)
        timer.function()
        ctx.exit_boom.close.assert_called_once()
        workflow.force_reset()

    def test_timeout_reset_closes_exit_boom_immediately(self):
        workflow, ctx = self._make_workflow()
        ctx.exit_boom.close.reset_mock()

        workflow.force_reset()

        ctx.exit_boom.close.assert_called_once()
        self.assertIsNone(getattr(workflow, "_boom_close_timer"))


class TestBidirectionalSettings(unittest.TestCase):
    def test_rfid_configs_returns_both_direction_readers(self):
        from config.settings import Settings

        settings = Settings(
            wb_type="bidirectional",
            raw_config={
                "rfids": {
                    "entry_a": {"ip": "10.0.0.1"},
                    "entry_b": {"ip": "10.0.0.2"},
                }
            },
        )

        self.assertEqual(set(settings.rfid_configs()), {"entry_a", "entry_b"})
        self.assertEqual(settings.rfid_config("entry_b")["ip"], "10.0.0.2")


class TestSensorAlreadyActive(unittest.TestCase):
    def test_already_true_sensor_fires_occupied_callback(self):
        from gmdc_common.hardware.io_controller import DemoIOController
        from gmdc_common.hardware.sensor import SensorPoller

        occupied = []
        poller = SensorPoller(
            DemoIOController(),
            entry_pin=0,
            on_entry_occupied=lambda: occupied.append("edge"),
        )
        new_occupied = poller._handle_channel(
            name="Entry",
            pin=0,
            current=True,
            prev=True,
            occupied=False,
            callback=None,
            occupied_callback=lambda: occupied.append("active"),
        )
        self.assertTrue(new_occupied)
        self.assertEqual(occupied, ["active"])

    def test_reset_edge_state_clears_previous_sample(self):
        from gmdc_common.hardware.io_controller import DemoIOController
        from gmdc_common.hardware.sensor import SensorPoller

        poller = SensorPoller(DemoIOController(), entry_pin=0)
        poller._prev_entry = True
        poller._entry_occupied = True
        poller.reset_edge_state()
        self.assertFalse(poller._prev_entry)
        self.assertFalse(poller._entry_occupied)


if __name__ == "__main__":
    unittest.main()
