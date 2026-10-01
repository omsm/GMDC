"""Unit tests for GMDC MQTT display protocol helpers."""

from __future__ import annotations

import unittest

from gmdc_common.services.display_service import (
    ConsoleDisplayService,
    create_display_service,
    data_info_topic,
    data_info_topics_for_ips,
    display_info_topic,
    normalize_display_ips,
    pcb_id_topic,
    pcb_letter_for_display_ip,
    resolve_pcb_mode,
)


class DisplayProtocolTests(unittest.TestCase):
    def test_topics_and_mode(self):
        self.assertEqual(resolve_pcb_mode(is_bidirectional=False), "a")
        self.assertEqual(resolve_pcb_mode(is_bidirectional=True), "b")
        self.assertEqual(data_info_topic("a"), "data_info/a")
        self.assertEqual(data_info_topic("b"), "data_info/b")
        self.assertEqual(display_info_topic("192.168.1.70"), "display_info/192.168.1.70")
        self.assertEqual(pcb_id_topic("192.168.1.70"), "pcb_id/192.168.1.70")

    def test_bi_transaction_topic_is_one_side(self):
        ips = ["10.0.0.1", "10.0.0.2"]
        self.assertEqual(
            data_info_topics_for_ips(ips, pcb_mode="b", side="a"),
            ["data_info/a"],
        )
        self.assertEqual(
            data_info_topics_for_ips(ips, pcb_mode="b", side="b"),
            ["data_info/b"],
        )
        self.assertEqual(
            data_info_topics_for_ips(ips, pcb_mode="b"),
            ["data_info/a", "data_info/b"],
        )

    def test_bi_tx_topics_both(self):
        ips = ["10.0.0.1", "10.0.0.2"]
        self.assertEqual(
            data_info_topics_for_ips(ips, pcb_mode="b"),
            ["data_info/a", "data_info/b"],
        )
        self.assertEqual(
            data_info_topics_for_ips(["10.0.0.1"], pcb_mode="a"),
            ["data_info/a"],
        )
        self.assertEqual(pcb_letter_for_display_ip("10.0.0.1", ips, pcb_mode="b"), "a")
        self.assertEqual(pcb_letter_for_display_ip("10.0.0.2", ips, pcb_mode="b"), "b")

    def test_normalize_ips(self):
        self.assertEqual(
            normalize_display_ips([" 1.1.1.1 ", "1.1.1.1", "", "2.2.2.2"]),
            ["1.1.1.1", "2.2.2.2"],
        )

    def test_console_send(self):
        svc = ConsoleDisplayService(pcb_mode="b", display_ips=["10.0.0.1", "10.0.0.2"])
        self.assertTrue(svc.send("OD14@15000 Kg"))
        st = svc.get_status()
        self.assertEqual(st["pcb_mode"], "b")
        self.assertEqual(st["topic_tx"], "data_info/a")
        self.assertEqual(st["topic_tx_list"], ["data_info/a", "data_info/b"])
        self.assertEqual(st["display_ips"], ["10.0.0.1", "10.0.0.2"])

    def test_factory_no_ips_falls_back_console(self):
        svc = create_display_service(
            "mqtt", "127.0.0.1", 1883, display_ips=[], pcb_mode="a"
        )
        self.assertIsInstance(svc, ConsoleDisplayService)


if __name__ == "__main__":
    unittest.main()
