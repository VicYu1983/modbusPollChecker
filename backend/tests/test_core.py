from __future__ import annotations

import unittest
from datetime import datetime, timezone
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch

from app.check_service import CheckService
from app.modbus_adapter import ModbusTcpAdapter
from app.schemas import CheckResult, DeviceConfig, SiteConfig


class FakeResponse:
    def __init__(self, bits: list[bool] | None = None, registers: list[int] | None = None) -> None:
        self.bits = bits or []
        self.registers = registers or []

    def isError(self) -> bool:
        return False


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[str] = []
        self.comm_params = SimpleNamespace(timeout_response=None)

    def connect(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def read_coils(self, **_: object) -> FakeResponse:
        self.calls.append("01")
        return self.response

    def read_discrete_inputs(self, **_: object) -> FakeResponse:
        self.calls.append("02")
        return self.response

    def read_holding_registers(self, **_: object) -> FakeResponse:
        self.calls.append("03")
        return self.response

    def read_input_registers(self, **_: object) -> FakeResponse:
        self.calls.append("04")
        return self.response


class FakeAdapter:
    def __init__(self) -> None:
        self.checked_devices: list[str] = []

    def check_device(self, device: DeviceConfig) -> CheckResult:
        self.checked_devices.append(device.name)
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
    def test_device_scan_rate_defaults_to_one_second(self) -> None:
        device = DeviceConfig(name="PLC-01", ip="127.0.0.1")
        self.assertEqual(device.scan_rate_ms, 1000)

    def test_site_rejects_duplicate_device_names(self) -> None:
        device = {"name": "PLC-01", "ip": "127.0.0.1"}
        with self.assertRaises(ValueError):
            SiteConfig(site_name="Test", devices=[device, device])

    def test_expected_values_support_exact_and_range(self) -> None:
        self.assertTrue(ModbusTcpAdapter._matches_expected([1, 2], "1, 2"))
        self.assertTrue(ModbusTcpAdapter._matches_expected([1, 2], "0..2"))
        self.assertFalse(ModbusTcpAdapter._matches_expected([1, 3], "1, 2"))

    def test_read_function_codes_use_correct_requests_and_addresses(self) -> None:
        responses = {
            "01": FakeResponse(bits=[True, False]),
            "02": FakeResponse(bits=[False, True]),
            "03": FakeResponse(registers=[10, 11]),
            "04": FakeResponse(registers=[20, 21]),
        }
        for function, expected_address in (("01", 1), ("02", 10001), ("03", 40001), ("04", 30001)):
            client = FakeClient(responses[function])
            device = DeviceConfig(name=f"PLC-{function}", ip="127.0.0.1", function=function)
            with patch("app.modbus_adapter.ModbusTcpClient", return_value=client):
                result = ModbusTcpAdapter().check_device(device)
            self.assertEqual(client.calls, [function])
            self.assertEqual(result.plc_address, expected_address)
            self.assertEqual(client.comm_params.timeout_response, 1.0)

    def test_polling_updates_status_and_stops(self) -> None:
        config = SiteConfig(
            site_name="Test",
            devices=[
                DeviceConfig(name="PLC-01", ip="127.0.0.1", scan_rate_ms=1000),
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

    def test_polling_rechecks_devices_with_zero_scan_rate(self) -> None:
        config = SiteConfig(
            site_name="Test",
            devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1", scan_rate_ms=0)],
        )
        adapter = FakeAdapter()
        service = CheckService(adapter=adapter, max_workers=1)
        try:
            with patch("app.check_service.DEFAULT_POLL_INTERVAL_MS", 10):
                self.assertTrue(service.start_polling(lambda: config))
                sleep(0.05)
                self.assertGreaterEqual(adapter.checked_devices.count("PLC-01"), 2)
                self.assertEqual(service.status()[0].device_name, "PLC-01")
        finally:
            service.shutdown()


if __name__ == "__main__":
    unittest.main()
