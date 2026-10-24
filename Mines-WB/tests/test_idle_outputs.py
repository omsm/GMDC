"""Idle relay outputs and platform-sensor interlock."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gmdc_common.hardware.boom_barrier import BoomBarrier
from gmdc_common.hardware.io_controller import DemoIOController
from gmdc_common.hardware.traffic_light import TrafficLight


class IdleOutputTests(unittest.TestCase):
    def _workflow(self):
        from types import SimpleNamespace

        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import MinesWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = SimpleNamespace(wb_type="unidirectional")
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        io = DemoIOController()
        ctx.io = io
        ctx.entry_tl = TrafficLight(io, red_pin=0, name="entry", relay_on_green=True)
        ctx.exit_tl = TrafficLight(io, red_pin=1, name="exit", relay_on_green=True)
        ctx.entry_boom = BoomBarrier(io, open_pin=2, enabled=True, name="entry")
        ctx.exit_boom = BoomBarrier(io, open_pin=3, enabled=True, name="exit")
        return MinesWbWorkflow(ctx), io

    def test_idle_channel_states(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        coils = io.read_coils(0, 4)
        # Channel 2 NC, channel 3 NO, channel 4 NC. Channel 1 is entry green (NO).
        self.assertEqual(coils, [True, False, True, False])

    def test_platform_sensor_high_closes_channel_2(self):
        from config.constants import State

        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        io.write_coil(1, True)
        workflow.on_wb_occupied()
        self.assertEqual(workflow.ctx.state_machine.current_state, State.IDLE)
        self.assertFalse(io.read_coils(1, 1)[0])


class BidirectionalOutputTests(unittest.TestCase):
    def _workflow(self):
        from types import SimpleNamespace

        from core.app_context import AppContext
        from core.state_machine import StateMachine
        from core.transaction import TransactionStore
        from core.workflow import MinesWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = SimpleNamespace(wb_type="bidirectional")
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        io = DemoIOController()
        ctx.io = io
        ctx.traffic_lights = {
            "entry_a": {
                "entry": TrafficLight(io, name="a-entry", relay_on_green=False),
                "exit": TrafficLight(
                    io, red_pin=0, name="a-exit", relay_on_green=False
                ),
            },
            "entry_b": {
                "entry": TrafficLight(io, name="b-entry", relay_on_green=False),
                "exit": TrafficLight(
                    io, red_pin=1, name="b-exit", relay_on_green=False
                ),
            },
        }
        ctx.entry_tl = ctx.traffic_lights["entry_a"]["exit"]
        ctx.exit_tl = ctx.traffic_lights["entry_b"]["exit"]
        ctx.entry_boom = BoomBarrier(io, open_pin=2, enabled=True, name="entry")
        ctx.exit_boom = BoomBarrier(io, open_pin=3, enabled=True, name="exit")
        ctx.sensor_poller = SimpleNamespace(
            get_status=lambda: {
                "entry_active": False,
                "exit_active": False,
                "wb_active": True,
            }
        )
        return MinesWbWorkflow(ctx), io

    def test_idle_closes_lights_and_opens_booms(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        self.assertEqual(io.read_coils(0, 4), [False, False, True, True])

    def test_only_sensor_2_closes_both_booms(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.on_wb_occupied()
        self.assertEqual(io.read_coils(0, 4), [False, False, False, False])

    def test_sensor_2_with_another_sensor_leaves_booms_open(self):
        from types import SimpleNamespace

        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.ctx.sensor_poller = SimpleNamespace(
            get_status=lambda: {
                "entry_active": False,
                "exit_active": True,
                "wb_active": True,
            }
        )
        workflow.on_wb_occupied()
        self.assertEqual(io.read_coils(2, 2), [True, True])

    def test_entry_a_boom_close_opens_only_channel_1_then_idle(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.ctx.transactions.direction = "ENTRY_A"
        workflow._bidirectional_boom_close_ok = True
        workflow._grant_exit_hardware()
        self.assertEqual(io.read_coils(0, 4), [False, True, True, True])
        workflow.apply_idle_hardware()
        self.assertEqual(io.read_coils(0, 4), [False, False, True, True])

    def test_entry_b_boom_close_opens_only_channel_0_then_idle(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.ctx.transactions.direction = "ENTRY_B"
        workflow._bidirectional_boom_close_ok = True
        workflow._grant_exit_hardware()
        self.assertEqual(io.read_coils(0, 4), [True, False, True, True])
        workflow.force_reset()
        self.assertEqual(io.read_coils(0, 4), [False, False, True, True])
