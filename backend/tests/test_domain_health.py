from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.domain.health import summarize
from app.domain.models import CheckRecord
from app.schemas import CheckResult, DeviceConfig


def make_record(name: str, status: str, elapsed_ms: int) -> CheckRecord:
    device = DeviceConfig(name=name, ip="127.0.0.1")
    return CheckRecord(
        batch_id="batch-1",
        device_snapshot=device,
        result=CheckResult(
            device_name=name,
            timestamp=datetime.now(timezone.utc),
            status=status,
            ip=device.ip,
            port=device.port,
            unit_id=device.unit_id,
            function=device.function,
            address=device.address,
            plc_address=40001 + device.address,
            quantity=device.quantity,
            elapsed_ms=elapsed_ms,
        ),
    )


class HealthSummaryTests(unittest.TestCase):
    def test_summarize_counts_and_averages_only_passing_devices(self) -> None:
        summary = summarize(
            [
                make_record("PLC-01", "PASS", 20),
                make_record("PLC-02", "PASS", 40),
                make_record("PLC-03", "TIMEOUT", 1000),
                make_record("PLC-04", "FAIL", 10),
            ]
        )

        self.assertEqual(summary.device_count, 4)
        self.assertEqual(summary.pass_rate, 0.5)
        self.assertEqual(summary.avg_elapsed_ms, 30)
        self.assertEqual(summary.slowest_device, "PLC-02")
        self.assertEqual(summary.slowest_elapsed_ms, 40)
        self.assertEqual(summary.timeout_count, 1)
        self.assertEqual(summary.fail_count, 1)

    def test_empty_records_have_zero_pass_rate(self) -> None:
        summary = summarize([])

        self.assertEqual(summary.device_count, 0)
        self.assertEqual(summary.pass_rate, 0)
        self.assertIsNone(summary.avg_elapsed_ms)
        self.assertIsNone(summary.slowest_device)


if __name__ == "__main__":
    unittest.main()