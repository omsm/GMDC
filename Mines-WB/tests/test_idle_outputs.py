"""Idle relay outputs and platform-sensor interlock."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "gmdc_common"))

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
                "entry": TrafficLight(
                    io, red_pin=4, name="a-entry", relay_on_green=True
                ),
                "exit": TrafficLight(
                    io, red_pin=0, name="a-exit", relay_on_green=True
                ),
            },
            "entry_b": {
                "entry": TrafficLight(
                    io, red_pin=5, name="b-entry", relay_on_green=True
                ),
                "exit": TrafficLight(
                    io, red_pin=1, name="b-exit", relay_on_green=True
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
        # Exit TL red (0/1 OFF); entry TL green (4/5 ON); both booms open
        self.assertEqual(io.read_coils(0, 4), [False, False, True, True])
        self.assertEqual(io.read_coils(4, 2), [True, True])

    def test_only_sensor_2_closes_both_booms(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.on_wb_occupied()
        # Idle light pattern unchanged; both booms close
        self.assertEqual(io.read_coils(0, 4), [False, False, False, False])
        self.assertEqual(io.read_coils(4, 2), [True, True])

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

    def test_entry_a_direction_sets_opposite_red_and_closes_depart_boom(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow._begin_vehicle_positioning("ENTRY_A")
        # A exit red, B exit red; A boom open, B (depart) boom closed
        self.assertEqual(io.read_coils(0, 4), [False, False, True, False])
        # A entry green, B entry red
        self.assertEqual(io.read_coils(4, 2), [True, False])

    def test_entry_a_boom_close_opens_only_channel_1_then_idle(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.ctx.transactions.direction = "ENTRY_A"
        workflow._bidirectional_boom_close_ok = True
        workflow._grant_exit_hardware()
        # A exit red, B exit green; A boom closed, B boom open
        self.assertEqual(io.read_coils(0, 4), [False, True, False, True])
        # Depart entry stays red
        self.assertEqual(io.read_coils(4, 2), [False, False])
        workflow.apply_idle_hardware()
        self.assertEqual(io.read_coils(0, 4), [False, False, True, True])
        self.assertEqual(io.read_coils(4, 2), [True, True])

    def test_entry_b_boom_close_opens_only_channel_0_then_idle(self):
        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.ctx.transactions.direction = "ENTRY_B"
        workflow._bidirectional_boom_close_ok = True
        workflow._grant_exit_hardware()
        # A exit green, B exit red; A boom open, B boom closed
        self.assertEqual(io.read_coils(0, 4), [True, False, True, False])
        workflow.force_reset()
        self.assertEqual(io.read_coils(0, 4), [False, False, True, True])
        self.assertEqual(io.read_coils(4, 2), [True, True])

    def test_entry_a_exit_grant_drives_only_depart_exit_light(self):
        """ENTRY_A grant: only B exit green; B entry stays red."""
        from config.constants import State

        workflow, io = self._workflow()
        workflow.apply_idle_signals()
        workflow.ctx.transactions.begin()
        workflow.ctx.transactions.direction = "ENTRY_A"
        workflow.ctx.state_machine.force_state(State.WEIGHT_DETAILS)
        workflow._bidirectional_boom_close_ok = False
        workflow._grant_exit_hardware()
        # pin0 A-exit red; pin1 B-exit green
        self.assertEqual(io.read_coils(0, 2), [False, True])
        # pin4 A-entry red; pin5 B-entry red (only exit light on)
        self.assertEqual(io.read_coils(4, 2), [False, False])

    def test_resolve_bidirectional_relay_pins_from_config(self):
        """Mirror main._resolve_tl_pins for bi relay.*.entry_a/b.entry|exit."""
        from typing import Any, Dict, Optional, Tuple

        def _pin(value: Any) -> Optional[int]:
            if value is None or str(value).strip() == "":
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        def _resolve_tl_pins(
            io_cfg: Dict[str, Any],
            side: str,
            do_start: int,
            direction: Optional[str] = None,
        ) -> Tuple[Optional[int], Optional[int]]:
            tl = io_cfg.get("traffic_lights") or {}
            relay = tl.get("relay") or {}
            cfg: Dict[str, Any] = {}
            if direction:
                cfg = (relay.get(direction) or {}).get(side) or {}
            if not cfg:
                cfg = relay.get(side) or {}
            pin = _pin(cfg.get("pin"))
            if pin is None:
                return None, None
            return do_start + pin, None

        io_cfg = {
            "traffic_lights": {
                "mode": "relay",
                "relay": {
                    "entry_a": {
                        "entry": {"pin": "4"},
                        "exit": {"pin": "0"},
                    },
                    "entry_b": {
                        "entry": {"pin": "5"},
                        "exit": {"pin": "1"},
                    },
                },
            }
        }
        self.assertEqual(_resolve_tl_pins(io_cfg, "entry", 0, "entry_a"), (4, None))
        self.assertEqual(_resolve_tl_pins(io_cfg, "exit", 0, "entry_a"), (0, None))
        self.assertEqual(_resolve_tl_pins(io_cfg, "entry", 0, "entry_b"), (5, None))
        self.assertEqual(_resolve_tl_pins(io_cfg, "exit", 0, "entry_b"), (1, None))
