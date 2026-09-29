"""Wizard completion: checkpoint camera and I/O must follow the devices the operator can see."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.config_manager import DEFAULT_CONFIG, ConfigManager, section_label


def _manager(checkpoint_type="checkpoint", wb_type="unidirectional"):
    manager = ConfigManager.__new__(ConfigManager)
    manager.config = copy.deepcopy(DEFAULT_CONFIG)
    manager.config["checkpoint_type"] = checkpoint_type
    manager.config["wb_type"] = wb_type
    return manager


class TestSectionLabels(unittest.TestCase):
    def test_raw_keys_are_not_shown_to_operators(self):
        self.assertEqual(section_label("io_controller"), "I/O Controller")
        self.assertEqual(section_label("handheld_rfid"), "Handheld RFID")
        self.assertEqual(section_label("camera"), "Camera")


class TestCameraCompletion(unittest.TestCase):
    def test_checkpoint_front_stays_complete_when_parent_flag_is_stale(self):
        manager = _manager("checkpoint")
        manager.config["camera"]["validated"] = False
        manager.config["camera"]["front"]["validated"] = True
        manager.config["camera"]["top"]["validated"] = False
        status = manager.get_completion_status()
        self.assertIs(status["camera"], True)

    def test_checkpoint_without_front_is_incomplete(self):
        manager = _manager("checkpoint")
        manager.config["camera"]["front"]["validated"] = False
        status = manager.get_completion_status()
        self.assertIs(status["camera"], False)

    def test_weighbridge_needs_top_and_front(self):
        manager = _manager("weighbridge")
        manager.config["camera"]["validated"] = False
        manager.config["camera"]["front"]["validated"] = True
        manager.config["camera"]["top"]["validated"] = False
        self.assertIs(manager.get_completion_status()["camera"], False)
        manager.config["camera"]["top"]["validated"] = True
        self.assertIs(manager.get_completion_status()["camera"], True)


class TestIoCompletion(unittest.TestCase):
    def _pass_checkpoint_entry(self, manager, boom_enabled=False, boom_validated=False):
        io = manager.config["io_controller"]
        io["validated"] = False
        io["output_mode"] = "relay"
        io["sensors"]["entry_sensor"]["validated"] = True
        io["sensors"]["wb_sensor"]["validated"] = False
        io["sensors"]["exit_sensor"]["validated"] = False
        io["traffic_lights"]["entry"]["validated"] = True
        io["traffic_lights"]["exit"]["validated"] = False
        io["boom_barriers"]["relay"]["exit"]["enabled"] = True
        io["boom_barriers"]["relay"]["entry"]["enabled"] = boom_enabled
        io["boom_barriers"]["entry"]["validated"] = boom_validated
        io["boom_barriers"]["exit"]["validated"] = False

    def test_checkpoint_ignores_hidden_exit_boom_and_exit_light(self):
        manager = _manager("checkpoint")
        self._pass_checkpoint_entry(manager)
        self.assertIs(manager.get_completion_status()["io_controller"], True)

    def test_checkpoint_enabled_entry_boom_still_required(self):
        manager = _manager("checkpoint")
        self._pass_checkpoint_entry(manager, boom_enabled=True, boom_validated=False)
        self.assertIs(manager.get_completion_status()["io_controller"], False)
        manager.config["io_controller"]["boom_barriers"]["entry"]["validated"] = True
        self.assertIs(manager.get_completion_status()["io_controller"], True)

    def test_finish_message_uses_names_not_keys(self):
        manager = _manager("checkpoint")
        result = manager.finalize()
        self.assertEqual(result["status"], 400)
        self.assertIn("I/O Controller", result["message"])
        self.assertIn("Camera", result["message"])
        self.assertNotIn("io_controller", result["message"])
        self.assertNotIn("{", result["message"])


if __name__ == "__main__":
    unittest.main()
