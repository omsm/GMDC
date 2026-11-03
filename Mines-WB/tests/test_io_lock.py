"""I/O controller down locks the weighbridge workflow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "gmdc_common"))

from config.constants import State
from core.app_context import AppContext
from core.state_machine import StateMachine
from core.transaction import TransactionStore
from core.workflow import MinesWbWorkflow
from gmdc_common.hardware.io_controller import DemoIOController


class IOLockTests(unittest.TestCase):
    def _workflow(self):
        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.settings = SimpleNamespace(wb_type="unidirectional", demo_mode=True)
        ctx.state_machine = StateMachine()
        ctx.transactions = TransactionStore()
        io = DemoIOController()
        io.connect()
        ctx.io = io
        ctx.voice = MagicMock()
        ctx.frontend = MagicMock()
        wf = MinesWbWorkflow(ctx)
        return wf, io

    def test_io_fault_blocks_positioning_and_plays_voice(self):
        wf, _io = self._workflow()
        wf.on_io_health(False, "I/O connection failure. Please Check !")
        self.assertTrue(wf.io_is_locked())
        wf.ctx.voice.weighbridge_0.assert_called()
        pub = wf.ctx.frontend.publish_status
        self.assertTrue(pub.called)
        kwargs = pub.call_args.kwargs
        self.assertTrue(kwargs.get("popup"))
        self.assertIn("I/O", kwargs.get("popup_title", ""))

        wf.on_entry_occupied()
        self.assertEqual(wf.ctx.state_machine.current_state, State.IDLE)

    def test_io_recovery_clears_lock(self):
        wf, _io = self._workflow()
        wf.on_io_health(False, "I/O connection failure. Please Check !")
        wf.on_io_health(True, "")
        self.assertFalse(wf.io_is_locked())

    def test_not_configured_message(self):
        wf, _io = self._workflow()
        wf.on_io_health(False, "Controller not configured. Please Check!")
        kwargs = wf.ctx.frontend.publish_status.call_args.kwargs
        self.assertEqual(kwargs.get("popup_title"), "CONTROLLER NOT CONFIGURED")


if __name__ == "__main__":
    unittest.main()
