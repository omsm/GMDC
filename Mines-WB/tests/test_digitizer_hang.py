"""Digitizer heartbeat loss is announced only after a sustained gap."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class DigitizerHangGraceTests(unittest.TestCase):
    def _workflow(self):
        from core.app_context import AppContext
        from core.workflow import MinesWbWorkflow

        AppContext.reset_instance()
        ctx = AppContext.get_instance()
        ctx.digitizer = MagicMock()
        ctx.digitizer.supports_live_weight.return_value = True
        ctx.voice = MagicMock()
        return MinesWbWorkflow(ctx)

    def test_short_gap_does_not_announce(self):
        workflow = self._workflow()
        workflow.ctx.digitizer.is_alive.return_value = False
        workflow._maybe_notify_digitizer_hang()
        workflow.ctx.voice.digitizer_error.assert_not_called()

        workflow.ctx.digitizer.is_alive.return_value = True
        workflow._maybe_notify_digitizer_hang()
        workflow.ctx.voice.digitizer_error.assert_not_called()
        self.assertFalse(workflow._digitizer_hang_announced)
        self.assertIsNone(workflow._digitizer_hang_since)

    def test_sustained_gap_announces_once(self):
        from core.workflow import DIGITIZER_HANG_GRACE_SEC

        workflow = self._workflow()
        workflow.ctx.digitizer.is_alive.return_value = False
        workflow._maybe_notify_digitizer_hang()
        workflow._digitizer_hang_since -= DIGITIZER_HANG_GRACE_SEC
        workflow._maybe_notify_digitizer_hang()
        workflow.ctx.voice.digitizer_error.assert_called_once()

        workflow._maybe_notify_digitizer_hang()
        workflow.ctx.voice.digitizer_error.assert_called_once()
