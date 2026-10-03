"""Mines-WB decides stable weight from the decoder's live readings."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.digitizer_client import DigitizerMqttClient


class _Publisher:
    def __init__(self):
        self.payloads = []

    def publish(self, topic, payload, qos=0):
        self.payloads.append((topic, payload))


def _client(stable_count=3, timeout=0.4):
    client = DigitizerMqttClient(
        broker_host="127.0.0.1",
        stable_count=stable_count,
        timeout=timeout,
    )
    client._client = _Publisher()
    client._connected = True
    return client


def _weight(client, value):
    class Message:
        topic = "gmdc/digitizer/weight"
        payload = json.dumps({"current_weight": value, "weight": value}).encode()

    client._on_message(None, None, Message())


class TestMqttStableWeight(unittest.TestCase):
    def test_same_nonzero_reading_becomes_stable(self):
        client = _client()
        _weight(client, 43000)
        _weight(client, 43000)
        self.assertFalse(client._stable)
        _weight(client, 43000)
        result = client.read_stable_weight()
        self.assertTrue(result["ok"])
        self.assertEqual(result["weight"], 43000.0)

    def test_single_reading_is_not_accepted_before_stable_count(self):
        client = _client(stable_count=10, timeout=0.2)
        _weight(client, 45120)
        result = client.read_stable_weight()
        self.assertFalse(result["ok"])
        self.assertIsNone(result["weight"])

    def test_zero_never_counts_as_stable(self):
        client = _client(stable_count=2, timeout=0.3)
        _weight(client, 0)
        _weight(client, 0)
        _weight(client, 0)
        result = client.read_stable_weight()
        self.assertFalse(result["ok"])
        self.assertIsNone(result["weight"])

    def test_weight_change_restarts_the_stable_count(self):
        client = _client(stable_count=3)
        _weight(client, 100)
        _weight(client, 100)
        _weight(client, 200)
        _weight(client, 200)
        self.assertFalse(client._stable)
        _weight(client, 200)
        self.assertTrue(client._stable)
        self.assertEqual(client._stable_weight, 200.0)


if __name__ == "__main__":
    unittest.main()
