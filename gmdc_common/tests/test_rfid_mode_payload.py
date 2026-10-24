"""Zebra set_mode transmitPower must match the enabled antenna count."""

from __future__ import annotations

import unittest

from gmdc_common.services.rfid_control import (
    DEFAULT_MODE_PAYLOAD,
    align_transmit_power,
)


class RfidModePayloadTests(unittest.TestCase):
    def test_default_enables_antennas_5_and_6(self):
        self.assertEqual(DEFAULT_MODE_PAYLOAD["antennas"], [5, 6])
        self.assertEqual(DEFAULT_MODE_PAYLOAD["transmitPower"], [[30], [30]])

    def test_flat_power_is_wrapped_for_one_antenna(self):
        body = align_transmit_power(
            {"antennas": [5], "transmitPower": [30]}
        )
        self.assertEqual(body["transmitPower"], [[30]])

    def test_single_power_is_repeated_for_each_antenna(self):
        body = align_transmit_power(
            {"antennas": [1, 2], "transmitPower": [27]}
        )
        self.assertEqual(body["transmitPower"], [[27], [27]])

    def test_matching_nested_power_is_left_alone(self):
        payload = {"antennas": [5], "transmitPower": [[30]]}
        self.assertEqual(align_transmit_power(payload)["transmitPower"], [[30]])
        self.assertEqual(payload["transmitPower"], [[30]])


if __name__ == "__main__":
    unittest.main()
