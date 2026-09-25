from __future__ import annotations

import unittest
from datetime import datetime, timezone
from time import sleep

from app.check_service import CheckService
from app.modbus_adapter import ModbusTcpAdapter
from app.schemas import CheckResult, DeviceConfig, SiteConfig


class FakeAdapter:
    def check_device(self, device: DeviceConfig) -> CheckResult:
        return CheckResult(
            device_name=device.name,
            timestamp=datetime.now(timezone.utc),
            status="PASS",
            ip=device.ip,
            port=device.port,
            unit_id=device.unit_id,
            function=device.function,
            address=device.address,
            plc_address=40001,
            quantity=device.quantity,
            values=[1],
            elapsed_ms=1,
        )


class CoreTests(unittest.TestCase):
    def test_site_rejects_duplicate_device_names(self) -> None:
        device = {"name": "PLC-01", "ip": "127.0.0.1"}
        with self.assertRaises(ValueError):
            SiteConfig(site_name="Test", devices=[device, device])

    def test_expected_values_support_exact_and_range(self) -> None:
        self.assertTrue(ModbusTcpAdapter._matches_expected([1, 2], "1, 2"))
        self.assertTrue(ModbusTcpAdapter._matches_expected([1, 2], "0..2"))
        self.assertFalse(ModbusTcpAdapter._matches_expected([1, 3], "1, 2"))

    def test_polling_updates_status_and_stops(self) -> None:
        config = SiteConfig(
            site_name="Test",
            devices=[
                DeviceConfig(name="PLC-01", ip="127.0.0.1", scan_rate_ms=10),
            ],
        )
        service = CheckService(adapter=FakeAdapter(), max_workers=1)
        try:
            self.assertTrue(service.start_polling(lambda: config))
            sleep(0.05)
            self.assertTrue(service.polling_status().active)
            self.assertEqual(service.status()[0].device_name, "PLC-01")
            self.assertTrue(service.stop_polling())
            self.assertFalse(service.polling_status().active)
        finally:
            service.shutdown()


if __name__ == "__main__":
    unittest.main()
