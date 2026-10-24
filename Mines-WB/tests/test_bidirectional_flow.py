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
        from core.workflow import MinesWbWorkflow

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
        ctx.voice.is_multi_play_active.return_value = False

        workflow = MinesWbWorkflow(ctx)
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
        ctx.voice.move_forward.assert_called()
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
        ctx.voice.move_forward.assert_called()
        workflow.force_reset()

    def test_transaction_display_and_lights_stay_on_the_entry_side(self):
        workflow, ctx = self._make_workflow()
        ctx.display.send = MagicMock()
        ctx.traffic_lights = {
            "entry_a": {"entry": MagicMock(), "exit": MagicMock()},
            "entry_b": {"entry": MagicMock(), "exit": MagicMock()},
        }
        ctx.entry_tl = ctx.traffic_lights["entry_a"]["entry"]
        ctx.exit_tl = ctx.traffic_lights["entry_a"]["exit"]

        workflow.on_entry_occupied()

        _args, kwargs = ctx.display.send.call_args
        self.assertEqual(kwargs.get("side"), "a")
        ctx.traffic_lights["entry_b"]["entry"].set_red.assert_not_called()
        ctx.traffic_lights["entry_b"]["exit"].set_green.assert_not_called()
        ctx.exit_boom.close.assert_not_called()
        workflow.force_reset()

        ctx.display.send.reset_mock()
        workflow.on_exit_occupied()
        _args, kwargs = ctx.display.send.call_args
        self.assertEqual(kwargs.get("side"), "b")
        workflow.force_reset()

    def test_idle_s2_and_s3_cut_plays_weighbridge_0(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.settings.wb_type = "unidirectional"
        ctx.sensor_poller = MagicMock()
        ctx.sensor_poller.get_status.return_value = {
            "wb_active": True,
            "exit_active": True,
            "wb_occupied_latch": True,
            "exit_occupied_latch": True,
        }

        workflow.on_wb_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        ctx.voice.weighbridge_0.assert_called()
        ctx.voice.move_forward.assert_not_called()
        workflow.force_reset()

    def test_idle_s2_and_s3_cut_blocks_entry_b(self):
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.sensor_poller = MagicMock()
        ctx.sensor_poller.get_status.return_value = {
            "wb_active": True,
            "exit_active": True,
            "wb_occupied_latch": True,
            "exit_occupied_latch": True,
        }

        workflow.on_exit_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        ctx.voice.weighbridge_0.assert_called()
        ctx.rfid_clouds["entry_b"].prepare_idle.assert_not_called()
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

    def test_bidirectional_idle_opens_both_booms_and_entry_lights(self):
        workflow, ctx = self._make_workflow()
        ctx.traffic_lights = {
            "entry_a": {"entry": MagicMock(), "exit": MagicMock()},
            "entry_b": {"entry": MagicMock(), "exit": MagicMock()},
        }
        ctx.entry_tl = ctx.traffic_lights["entry_a"]["entry"]
        ctx.exit_tl = ctx.traffic_lights["entry_a"]["exit"]
        ctx.entry_boom.open.reset_mock()
        ctx.exit_boom.open.reset_mock()
        ctx.exit_boom.close.reset_mock()

        workflow.apply_idle_hardware()

        ctx.entry_boom.open.assert_called()
        ctx.exit_boom.open.assert_called()
        ctx.exit_boom.close.assert_not_called()
        for direction in ("entry_a", "entry_b"):
            ctx.traffic_lights[direction]["entry"].set_green.assert_called()
            ctx.traffic_lights[direction]["exit"].set_green.assert_called()
            ctx.traffic_lights[direction]["exit"].set_red.assert_not_called()
        self.assertIsNone(getattr(workflow, "_boom_close_timer"))

    def test_unidirectional_reset_closes_exit_boom_immediately(self):
        workflow, ctx = self._make_workflow()
        ctx.settings.wb_type = "unidirectional"
        ctx.exit_boom.close.reset_mock()

        workflow.force_reset()

        ctx.exit_boom.close.assert_called_once()
        self.assertIsNone(getattr(workflow, "_boom_close_timer"))

    def test_entry_sensor_does_not_start_while_idle_weight_is_nonzero(self):
        import time
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.settings.wb_type = "unidirectional"
        ctx.digitizer = MagicMock()
        ctx.digitizer.supports_live_weight.return_value = True
        ctx.digitizer.get_current_weight.return_value = 8000.0

        workflow.on_entry_occupied()

        self.assertEqual(ctx.state_machine.current_state, State.IDLE)
        ctx.voice.move_forward.assert_not_called()
        for _ in range(40):
            if ctx.voice.check_weighbridge_weight.called:
                break
            time.sleep(0.02)
        ctx.voice.check_weighbridge_weight.assert_called()
        workflow.force_reset()

    def test_idle_nonzero_weight_plays_digitizer_check(self):
        import time

        workflow, ctx = self._make_workflow()
        ctx.digitizer = MagicMock()
        ctx.digitizer.supports_live_weight.return_value = True
        ctx.digitizer.get_current_weight.return_value = 8000.0

        workflow._on_digitizer_update()

        for _ in range(40):
            if ctx.voice.check_weighbridge_weight.called:
                break
            time.sleep(0.02)
        ctx.voice.check_weighbridge_weight.assert_called()
        ctx.voice.weighbridge_0.assert_not_called()
        workflow.force_reset()

    def test_weight_drop_before_wb_only_starts_exit(self):
        import time
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.sensor_poller = MagicMock()
        ctx.sensor_poller.get_status.return_value = {
            "entry_active": True,
            "wb_active": False,
            "exit_active": False,
        }
        ctx.digitizer = MagicMock()
        ctx.digitizer.supports_live_weight.return_value = True
        ctx.digitizer.get_current_weight.return_value = 0.0
        workflow.on_entry_occupied()
        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)

        ctx.digitizer.get_current_weight.return_value = 0.0
        workflow._on_digitizer_update()
        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)
        ctx.voice.check_weighbridge_weight.assert_not_called()

        ctx.digitizer.get_current_weight.return_value = 12000.0
        workflow._on_digitizer_update()
        ctx.digitizer.get_current_weight.return_value = 0.0
        workflow._on_digitizer_update()

        for _ in range(50):
            if ctx.state_machine.current_state == State.EXIT_GRANTED:
                break
            time.sleep(0.02)
        self.assertEqual(ctx.state_machine.current_state, State.EXIT_GRANTED)
        ctx.voice.check_weighbridge_weight.assert_called()
        ctx.exit_boom.open.assert_called()
        workflow.force_reset()

    def test_entry_clear_while_wb_cut_starts_weight(self):
        """Sensor 1 clear while sensor 2 is cut starts weighing, even if the latch is stale."""
        import time
        from config.constants import State

        workflow, ctx = self._make_workflow()
        ctx.sensor_poller = MagicMock()
        ctx.sensor_poller.get_status.return_value = {
            "entry_active": False,
            "entry_occupied_latch": True,
            "wb_active": True,
            "exit_active": False,
            "exit_occupied_latch": False,
        }
        ctx.digitizer = MagicMock()
        ctx.digitizer.supports_live_weight.return_value = False
        ctx.digitizer.read_stable_weight.return_value = {"ok": False, "weight": None}
        workflow.on_entry_occupied()
        self.assertEqual(ctx.state_machine.current_state, State.VEHICLE_POSITIONING)
        workflow.on_entry_cleared()
        for _ in range(50):
            if ctx.digitizer.read_stable_weight.called:
                break
            time.sleep(0.02)
        ctx.digitizer.read_stable_weight.assert_called()
        workflow.force_reset()


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

    def test_bidirectional_opens_both_rfid_ports_besides_the_app(self):
        from config.settings import Settings

        settings = Settings(
            api_port=8000,
            wb_type="bidirectional",
            raw_config={
                "rfid": {"api_port": "8080"},
                "rfids": {
                    "entry_a": {"api_port": "8080"},
                    "entry_b": {"api_port": "8081"},
                },
            },
        )
        self.assertEqual(settings.rfid_api_listen_ports(), [8080, 8081])

    def test_unidirectional_opens_only_the_single_rfid_port(self):
        from config.settings import Settings

        settings = Settings(
            api_port=8000,
            wb_type="unidirectional",
            raw_config={
                "rfid": {"api_port": "8080"},
                "rfids": {
                    "entry_a": {"api_port": "8080"},
                    "entry_b": {"api_port": "8081"},
                },
            },
        )
        self.assertEqual(settings.rfid_api_listen_ports(), [8080])

    def test_rfid_port_already_on_the_application_is_not_opened_again(self):
        from config.settings import Settings

        settings = Settings(
            api_port=8080,
            wb_type="unidirectional",
            raw_config={"rfid": {"api_port": "8080"}},
        )
        self.assertEqual(settings.rfid_api_listen_ports(), [])


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

    def test_clear_callback_sees_released_latch(self):
        from gmdc_common.hardware.io_controller import DemoIOController
        from gmdc_common.hardware.sensor import SensorPoller

        poller = SensorPoller(DemoIOController(), entry_pin=0)
        seen = {}

        def on_clear():
            seen["latch"] = poller.get_status()["entry_occupied_latch"]

        poller._last_entry = False
        poller._entry_occupied = True
        poller._handle_channel(
            name="Entry",
            pin=0,
            current=False,
            prev=True,
            occupied=True,
            callback=on_clear,
            store=lambda value: setattr(poller, "_entry_occupied", value),
        )
        self.assertFalse(seen["latch"])

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
