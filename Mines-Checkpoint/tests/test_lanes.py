"""Four checkpoint locations in one process."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import load_lane_settings, load_settings
from core.app_context import AppContext, LaneTable
from services.frontend_mqtt import FrontendMqtt


class TestLaneRouting(unittest.TestCase):
    def test_dashboard_topics_are_per_lane(self):
        frontend = FrontendMqtt.__new__(FrontendMqtt)
        frontend.topic_root = "wb_frontend/mines_entry"
        self.assertEqual(
            frontend._topic("device_status"),
            "wb_frontend/mines_entry/device_status",
        )
        self.assertEqual(
            frontend._topic("request_status"),
            "wb_frontend/mines_entry/request_status",
        )
    def test_listen_port_wins_over_shared_reader_ip(self):
        table = LaneTable()
        entry = AppContext()
        traffic_out = AppContext()
        traffic_in = AppContext()
        exit_lane = AppContext()
        table.add("mines_entry", entry, 8001, "10.80.118.57")
        table.add("traffic_in", traffic_in, 8002, "10.80.118.59")
        table.add("traffic_out", traffic_out, 8003, "10.80.118.57")
        table.add("mines_exit", exit_lane, 8004, "10.80.118.65")

        self.assertIs(table.resolve(port=8001), entry)
        self.assertIs(table.resolve(port=8003), traffic_out)
        self.assertIs(table.resolve(port=8002, remote_ip="10.80.118.57"), traffic_in)
        self.assertIs(table.resolve(remote_ip="10.80.118.59"), traffic_in)
        self.assertIs(table.resolve(remote_ip="10.80.118.57"), entry)
        self.assertIs(table.resolve(lane="mines_exit", port=8001), exit_lane)

    def test_load_keeps_each_location(self):
        settings = load_lane_settings(ROOT / "iot_configuration.json")
        self.assertEqual(
            [item.lane_id for item in settings],
            ["mines_entry", "traffic_in", "traffic_out", "mines_exit"],
        )
        by_id = {item.lane_id: item for item in settings}
        self.assertEqual(by_id["mines_entry"].rfid_listen_port, 8001)
        self.assertEqual(by_id["traffic_in"].rfid_listen_port, 8002)
        self.assertEqual(by_id["traffic_out"].rfid_listen_port, 8003)
        self.assertEqual(by_id["mines_exit"].rfid_listen_port, 8004)
        self.assertEqual(by_id["mines_entry"].mqtt_topic_tx, "data_info/a")
        self.assertEqual(by_id["traffic_in"].mqtt_topic_tx, "data_info/b")
        self.assertEqual(by_id["traffic_out"].mqtt_topic_tx, "data_info/c")
        self.assertEqual(by_id["mines_exit"].mqtt_topic_tx, "data_info/d")
        self.assertIn("10.80.118.10:8001", by_id["mines_exit"].oci_base_url)
        self.assertIn("checkpoint/rfid-tag", by_id["traffic_in"].rfid_validate_url)
        self.assertIn("mines_exit_boom_close", by_id["mines_exit"].boom_close_url)
        self.assertFalse(by_id["traffic_in"].anpr_enabled)
        self.assertTrue(by_id["mines_entry"].anpr_enabled)
        self.assertEqual(by_id["traffic_out"].display_name, "Traffic OUT")
        first = load_settings(str(ROOT / "iot_configuration.json"))
        self.assertEqual(first.lane_id, "mines_entry")
        self.assertIn("boom-close", first.boom_close_url)
        self.assertIn("status_check", first.update_truck_url)

    def test_single_file_still_loads(self):
        raw = {"wb_type": "Mines Entry", "lane_name": "Solo", "demo_mode": False}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "iot_configuration.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            loaded = load_lane_settings(path)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].lane_id, "")
        self.assertEqual(loaded[0].display_name, "Solo")


if __name__ == "__main__":
    unittest.main()
