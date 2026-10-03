"""MQTT mode publishes every weight, including repeats and 0 kg, every 200 ms."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mqtt_bridge import MqttBridge
from services.weight_runtime import WeightRuntime


class _Client:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload)))


class _Message:
    def __init__(self, topic, payload=b"{}"):
        self.topic = topic
        self.payload = payload


def _bridge(stream=True):
    runtime = WeightRuntime()
    runtime.set_connected(True)
    bridge = MqttBridge(
        runtime,
        broker_host="127.0.0.1",
        weight_stream=stream,
    )
    client = _Client()
    bridge._client = client
    bridge._connected = True
    return bridge, runtime, client


class TestMqttWeightStream(unittest.TestCase):
    def test_publishes_every_sample_including_repeats_and_zero(self):
        bridge, _runtime, client = _bridge()
        self.assertEqual(bridge.weight_publish_interval_sec, 0.2)
        bridge.publish_weight(0)
        bridge.publish_weight(0)
        bridge.publish_weight(12500)
        bridge.publish_weight(12500.0)
        bridge.publish_weight(0)
        bridge.publish_weight(0)
        weights = [body["weight"] for _topic, body in client.published]
        self.assertEqual(weights, [0.0, 0.0, 12500.0, 12500.0, 0.0, 0.0])
        self.assertEqual(client.published[0][0], "gmdc/digitizer/weight")

    def test_current_weight_is_republished_on_each_tick(self):
        bridge, runtime, client = _bridge()
        runtime.push_weight(43000, "43000", b"43000")
        bridge.publish_current_weight()
        bridge.publish_current_weight()
        weights = [body["weight"] for _topic, body in client.published]
        self.assertEqual(weights, [43000.0, 43000.0])

    def test_request_topic_publishes_current_value_immediately(self):
        bridge, runtime, client = _bridge()
        runtime.push_weight(0, "0", b"0")
        bridge.publish_weight(0)
        self.assertEqual(len(client.published), 1)
        bridge._on_message(None, None, _Message("gmdc/digitizer/request", b"{}"))
        self.assertEqual(len(client.published), 2)
        topic, body = client.published[-1]
        self.assertEqual(topic, "gmdc/digitizer/weight")
        self.assertEqual(body["source"], "request")
        self.assertEqual(body["current_weight"], 0.0)
        self.assertEqual(body["weight"], 0.0)

    def test_api_mode_does_not_publish_weight(self):
        bridge, _runtime, client = _bridge(stream=False)
        bridge.publish_weight(10)
        bridge._on_message(None, None, _Message("gmdc/digitizer/request"))
        self.assertEqual(client.published, [])


if __name__ == "__main__":
    unittest.main()
