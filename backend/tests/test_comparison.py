from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import CheckBatch, CheckRecord
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import CheckResult, DeviceConfig, SiteConfig
from app.services.comparison_service import (
    BaselineRequiresConfirmationError,
    ComparisonService,
)


class ComparisonServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(
            Path(self.temporary_directory.name) / "history.db"
        )
        self.repository.initialize()
        self.service = ComparisonService(self.repository)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def _record(
        batch_id: str,
        name: str,
        *,
        status: str = "PASS",
        values: list[int | bool] | None = None,
        elapsed_ms: int = 30,
        ip: str = "127.0.0.1",
    ) -> CheckRecord:
        device = DeviceConfig(name=name, ip=ip)
        result = CheckResult(
            device_name=name,
            timestamp=datetime.now(timezone.utc),
            status=status,
            ip=device.ip,
            port=device.port,
            unit_id=device.unit_id,
            function=device.function,
            address=device.address,
            plc_address=40001,
            quantity=device.quantity,
            values=values or [1],
            elapsed_ms=elapsed_ms,
            error_type="TIMEOUT" if status == "TIMEOUT" else None,
            error_message="response timeout" if status == "TIMEOUT" else None,
        )
        return CheckRecord(batch_id=batch_id, result=result, device_snapshot=device)

    def _save_batch(self, batch_id: str, records: list[CheckRecord]) -> None:
        devices = [record.device_snapshot for record in records]
        config = SiteConfig(site_name="Test Site", devices=devices)
        batch = CheckBatch(
            id=batch_id,
            site_name=config.site_name,
            mode="full",
            status="completed",
            device_names=[device.name for device in devices],
            config_snapshot=config,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            pass_count=sum(record.result.status == "PASS" for record in records),
            fail_count=sum(record.result.status == "FAIL" for record in records),
            timeout_count=sum(record.result.status == "TIMEOUT" for record in records),
        )
        self.repository.create_batch(batch)
        for record in records:
            self.repository.save_record(record)

    def test_comparison_classifies_regression_and_device_set_changes(self) -> None:
        baseline_records = [
            self._record("baseline", "NewFailure"),
            self._record("baseline", "Recovered", status="TIMEOUT"),
            self._record("baseline", "StillFailing", status="FAIL"),
            self._record("baseline", "ValueChanged", values=[1]),
            self._record("baseline", "Slow", elapsed_ms=30),
            self._record("baseline", "ConfigChanged"),
            self._record("baseline", "Removed"),
        ]
        current_records = [
            self._record("current", "NewFailure", status="TIMEOUT"),
            self._record("current", "Recovered"),
            self._record("current", "StillFailing", status="FAIL"),
            self._record("current", "ValueChanged", values=[2]),
            self._record("current", "Slow", elapsed_ms=200),
            self._record("current", "ConfigChanged", ip="127.0.0.2"),
            self._record("current", "Added"),
        ]
        self._save_batch("baseline", baseline_records)
        self._save_batch("current", current_records)
        self.service.set_baseline("Test Site", "baseline", force=True)

        comparison = self.service.compare("current")
        statuses = {item.device_name: item.status for item in comparison.comparisons}

        self.assertEqual(statuses["NewFailure"], "NEW_FAILURE")
        self.assertEqual(statuses["Recovered"], "RECOVERED")
        self.assertEqual(statuses["StillFailing"], "UNCHANGED_FAILURE")
        self.assertEqual(statuses["ValueChanged"], "VALUE_CHANGED")
        self.assertEqual(statuses["Slow"], "LATENCY_DEGRADED")
        self.assertEqual(statuses["ConfigChanged"], "CONFIG_CHANGED")
        self.assertEqual(statuses["Added"], "NEW_DEVICE")
        self.assertEqual(statuses["Removed"], "BASELINE_ONLY")

    def test_comparison_without_baseline_is_explicit(self) -> None:
        self._save_batch("current", [self._record("current", "PLC-01")])

        comparison = self.service.compare("current")

        self.assertIsNone(comparison.baseline_batch_id)
        self.assertEqual(comparison.comparisons[0].status, "NO_BASELINE")

    def test_failed_batch_requires_explicit_baseline_confirmation(self) -> None:
        self._save_batch(
            "failed-baseline",
            [self._record("failed-baseline", "PLC-01", status="TIMEOUT")],
        )

        with self.assertRaises(BaselineRequiresConfirmationError):
            self.service.set_baseline("Test Site", "failed-baseline")

        baseline = self.service.set_baseline(
            "Test Site",
            "failed-baseline",
            force=True,
        )
        self.assertEqual(baseline.baseline_batch_id, "failed-baseline")

    def test_baseline_is_persisted_and_can_be_cleared(self) -> None:
        self._save_batch("baseline", [self._record("baseline", "PLC-01")])

        self.service.set_baseline("Test Site", "baseline")
        reopened = SqliteHistoryRepository(self.repository.database_path)
        reopened.initialize()

        self.assertEqual(
            reopened.get_baseline("Test Site").baseline_batch_id,
            "baseline",
        )
        self.assertTrue(reopened.clear_baseline("Test Site"))
        self.assertIsNone(reopened.get_baseline("Test Site"))


if __name__ == "__main__":
    unittest.main()