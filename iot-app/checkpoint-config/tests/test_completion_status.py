"""Wizard completion: checkpoint camera and I/O must follow the devices the operator can see."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.config_manager import (
    DEFAULT_CONFIG,
    ConfigManager,
    io_controller_device_address,
    section_label,
)


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

    def test_bidirectional_front_pair_and_optional_top(self):
        manager = _manager("weighbridge", "bidirectional")
        manager.config["camera"]["validated"] = False
        manager.config["camera"]["front_a"] = {"validated": True}
        manager.config["camera"]["front_b"] = {"validated": True}
        manager.config["camera"]["top"]["validated"] = None
        self.assertIs(manager.get_completion_status()["camera"], True)
        manager.config["camera"]["front_b"]["validated"] = False
        self.assertIs(manager.get_completion_status()["camera"], False)


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


class TestDeviceIpFromIo(unittest.TestCase):
    def test_ethernet_uses_controller_ip(self):
        address = io_controller_device_address({
            "type": "ethernet",
            "connection": {"ethernet": {"ip": "192.168.1.50", "port": "502"}},
        })
        self.assertEqual(address, "192.168.1.50")

    def test_rtu_uses_com_port(self):
        address = io_controller_device_address({
            "type": "serial",
            "connection": {"serial": {"port": "COM4"}},
        })
        self.assertEqual(address, "COM4")

    def test_loopback_is_not_stored(self):
        self.assertEqual(
            io_controller_device_address({
                "type": "ethernet",
                "connection": {"ethernet": {"ip": "127.0.0.1"}},
            }),
            "",
        )

    def test_this_pc_lan_ip_is_not_stored(self):
        import utils.local_ip as local_ip

        real = local_ip.detect_device_ip
        local_ip.detect_device_ip = lambda: "10.0.0.8"
        try:
            self.assertEqual(
                io_controller_device_address({
                    "type": "ethernet",
                    "connection": {"ethernet": {"ip": "10.0.0.8"}},
                }),
                "",
            )
            self.assertEqual(
                io_controller_device_address({
                    "type": "ethernet",
                    "connection": {"ethernet": {"ip": "10.0.0.40"}},
                }),
                "10.0.0.40",
            )
        finally:
            local_ip.detect_device_ip = real

    def test_successful_record_keeps_controller_ip_through_finalize(self):
        manager = _manager()
        manager._save_config = lambda: True
        saved = manager.record_device_ip_from_io({
            "type": "ethernet",
            "connection": {"ethernet": {"ip": "192.168.0.77"}},
        })
        self.assertTrue(saved)
        final = manager._prepare_final_config()
        self.assertEqual(final["device_ip"], "192.168.0.77")


class TestMergeIoControllerDevice(unittest.TestCase):
    def _manager(self):
        manager = _manager()
        manager._save_config = lambda: True
        return manager

    def test_one_sensor_does_not_complete_the_module(self):
        manager = self._manager()
        ok, message = manager.merge_io_controller_device({
            "validated": True,
            "sensors": {
                "entry_sensor": {
                    "pin": "4",
                    "default_signal": "high",
                    "validated": True,
                }
            },
        })
        self.assertTrue(ok, message)
        io = manager.config["io_controller"]
        self.assertIs(io["validated"], False)
        self.assertEqual(io["sensors"]["entry_sensor"]["pin"], "4")
        self.assertIs(io["sensors"]["entry_sensor"]["validated"], True)
        self.assertEqual(io["sensors"]["wb_sensor"]["pin"], "1")
        self.assertIs(io["sensors"]["wb_sensor"]["validated"], False)
        self.assertEqual(io["sensors"]["exit_sensor"]["pin"], "2")

    def test_duplicate_pin_is_rejected_and_leaves_the_file_unchanged(self):
        manager = self._manager()
        io = manager.config["io_controller"]
        io["sensors"]["exit_sensor"]["pin"] = "5"
        io["sensors"]["exit_sensor"]["validated"] = True
        ok, message = manager.merge_io_controller_device({
            "sensors": {
                "entry_sensor": {"pin": "5", "default_signal": "low", "validated": True}
            }
        })
        self.assertFalse(ok)
        self.assertIn("pin 5", message or "")
        self.assertEqual(io["sensors"]["entry_sensor"]["pin"], "0")
        self.assertIs(io["sensors"]["entry_sensor"]["validated"], False)

    def test_skipped_light_is_stored_without_completing_the_module(self):
        manager = self._manager()
        ok, message = manager.merge_io_controller_device({
            "traffic_lights": {
                "mode": "direct",
                "direct": {"exit": {"red_pin": "", "green_pin": ""}},
                "exit": {"make": "", "model": "", "validated": None},
            }
        })
        self.assertTrue(ok, message)
        io = manager.config["io_controller"]
        self.assertIs(io["validated"], False)
        self.assertIsNone(io["traffic_lights"]["exit"]["validated"])
        self.assertEqual(io["traffic_lights"]["direct"]["entry"]["red_pin"], "0")


class TestBidirectionalRfidCompletion(unittest.TestCase):
    def test_section_completes_only_when_both_readers_are_validated(self):
        manager = _manager("weighbridge", "bidirectional")
        manager.config["rfids"] = {
            "entry_a": {"ip": "10.0.0.11", "mode": "API", "validated": True},
            "entry_b": {"ip": "10.0.0.12", "mode": "API", "validated": False},
        }
        self.assertIs(manager.get_completion_status()["rfid"], False)
        manager.config["rfids"]["entry_b"]["validated"] = True
        self.assertIs(manager.get_completion_status()["rfid"], True)


class TestCameraSaveKeepsSiblings(unittest.TestCase):
    def test_front_save_keeps_skipped_top_and_other_front(self):
        manager = _manager("weighbridge", "bidirectional")
        manager._save_config = lambda: True
        manager.config["camera"] = {
            "validated": False,
            "top": {"validated": None, "skipped": True, "rtsp_url": ""},
            "front_a": {"validated": True, "rtsp_url": "rtsp://a"},
            "front_b": {"validated": False, "rtsp_url": ""},
        }
        ok = manager.save_section("camera", {
            "front_b": {"rtsp_url": "rtsp://b", "validated": True},
            "validated": True,
        })
        self.assertTrue(ok)
        camera = manager.config["camera"]
        self.assertIsNone(camera["top"]["validated"])
        self.assertTrue(camera["front_a"]["validated"])
        self.assertTrue(camera["front_b"]["validated"])
        self.assertIs(manager.get_completion_status()["camera"], True)

        ok = manager.save_section("camera", {
            "front_a": {"validated": False},
            "validated": False,
        })
        self.assertTrue(ok)
        camera = manager.config["camera"]
        self.assertIsNone(camera["top"]["validated"])
        self.assertFalse(camera["front_a"]["validated"])
        self.assertTrue(camera["front_b"]["validated"])
        self.assertIs(manager.get_completion_status()["camera"], False)


if __name__ == "__main__":
    unittest.main()
