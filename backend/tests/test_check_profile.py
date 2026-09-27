from __future__ import annotations

import unittest

from app.domain.check_profile import CheckProfileConfigError, resolve_check_profile
from app.schemas import DeviceConfig


class CheckProfileTests(unittest.TestCase):
    def test_legacy_device_defaults_to_full_stack(self) -> None:
        device = DeviceConfig.model_validate({"name": "PLC-01", "ip": "192.0.2.1"})

        profile = resolve_check_profile(device)

        self.assertEqual(device.check_profile, "full_stack")
        self.assertEqual(profile.network_mode, "full_stack")
        self.assertTrue(profile.allows_modbus)
        self.assertEqual(profile.tcp_port, 502)

    def test_ping_profile_never_allows_modbus(self) -> None:
        profile = resolve_check_profile(
            DeviceConfig(name="Host", ip="192.0.2.2", check_profile="ping")
        )

        self.assertEqual(profile.network_mode, "network_only")
        self.assertFalse(profile.allows_modbus)
        self.assertIsNone(profile.tcp_port)

    def test_ping_tcp_requires_explicit_tcp_port(self) -> None:
        with self.assertRaises(ValueError):
            DeviceConfig(name="Web", ip="192.0.2.3", check_profile="ping_tcp")

        profile = resolve_check_profile(
            DeviceConfig(name="Web", ip="192.0.2.3", check_profile="ping_tcp", tcp_port=8080)
        )
        self.assertEqual(profile.network_mode, "network_and_port")
        self.assertFalse(profile.allows_modbus)
        self.assertEqual(profile.tcp_port, 8080)

    def test_disabled_device_cannot_be_resolved(self) -> None:
        with self.assertRaises(CheckProfileConfigError):
            resolve_check_profile(DeviceConfig(name="Host", ip="192.0.2.4", enabled=False))


if __name__ == "__main__":
    unittest.main()