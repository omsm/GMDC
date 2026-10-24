"""Single-coil traffic light polarity: NO = green, NC = red."""

from __future__ import annotations

import unittest

from gmdc_common.hardware.io_controller import DemoIOController
from gmdc_common.hardware.traffic_light import TrafficLight


class TrafficLightRelayTests(unittest.TestCase):
    def test_relay_on_green_uses_nc_for_red(self):
        io = DemoIOController()
        light = TrafficLight(io, red_pin=1, name="exit", relay_on_green=True)
        light.set_red()
        self.assertFalse(io.read_coils(1, 1)[0])
        light.set_green()
        self.assertTrue(io.read_coils(1, 1)[0])

    def test_legacy_relay_energizes_red(self):
        io = DemoIOController()
        light = TrafficLight(io, red_pin=1, name="exit", relay_on_green=False)
        light.set_red()
        self.assertTrue(io.read_coils(1, 1)[0])
        light.set_green()
        self.assertFalse(io.read_coils(1, 1)[0])
