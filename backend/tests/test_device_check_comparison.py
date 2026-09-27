from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import main
from app.domain.network_models import NetworkBatch, NetworkBatchCounts, NetworkCheckRecord
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import CheckResult, DeviceConfig, NetworkCheckResult, SiteConfig
from app.services.device_check_comparison_service import DeviceCheckComparisonService


class DeviceCheckComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(
            Path(self.temporary_directory.name) / "history.db"
        )
        self.repository.initialize()
        self.service = DeviceCheckComparisonService(self.repository)
        self.config = SiteConfig(
            site_name="Test Site",
            devices=[
                DeviceConfig(name="PLC-01", ip="192.0.2.1"),
                DeviceConfig(name="PLC-02", ip="192.0.2.2"),
            ],
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _store_batch(
        self,
        batch_id: str,
        *,
        status: str = "completed",
        results: list[NetworkCheckRecord] | None = None,
    ) -> NetworkBatch:
        batch = NetworkBatch(
            id=batch_id,
            site_name=self.config.site_name,
            mode="mixed",
            status="pending",
            device_names=[device.name for device in self.config.devices],
            config_snapshot=self.config,
            max_concurrency=2,
            started_at=datetime.now(timezone.utc),
        )
        self.repository.create_network_batch(batch)
        for record in results or []:
            self.repository.save_network_result(record, NetworkBatchCounts(pass_count=1))
        self.repository.update_network_batch_status(
            batch_id, status, completed_at=datetime.now(timezone.utc)
        )
        return self.repository.get_network_batch(batch_id)

    def _record(
        self,
        batch_id: str,
        device: DeviceConfig,
        *,
        overall_status: str = "PASS",
        ping_avg_ms: float | None = 10.0,
        values: list[int] | None = None,
    ) -> NetworkCheckRecord:
        modbus = None
        if values is not None:
            modbus = CheckResult(
                device_name=device.name,
                timestamp=datetime.now(timezone.utc),
                status="PASS",
                ip=device.ip,
                port=device.port,
                unit_id=device.unit_id,
                function=device.function,
                address=device.address,
                plc_address=40001 + device.address,
                quantity=device.quantity,
                values=values,
                elapsed_ms=3,
            )
        return NetworkCheckRecord(
            batch_id=batch_id,
            device_snapshot=device,
            result=NetworkCheckResult(
                device_name=device.name,
                target_ip=device.ip,
                timestamp=datetime.now(timezone.utc),
                mode="full_stack",
                ping_state="PASS" if overall_status == "PASS" else "UNREACHABLE",
                ping_attempts=4,
                ping_success_count=4 if overall_status == "PASS" else 0,
                ping_loss_percent=0 if overall_status == "PASS" else 100,
                ping_avg_ms=ping_avg_ms,
                tcp_port=device.port,
                tcp_state="OPEN",
                overall_status=overall_status,
                modbus_result=modbus,
            ),
        )

    def test_compare_without_baseline_marks_no_baseline(self) -> None:
        self._store_batch(
            "batch-1",
            results=[self._record("batch-1", self.config.devices[0])],
        )

        comparison = self.service.compare("batch-1")

        self.assertIsNone(comparison.baseline_batch_id)
        self.assertEqual(comparison.comparisons[0].status, "NO_BASELINE")

    def test_compare_detects_new_failure_and_recovery(self) -> None:
        self._store_batch(
            "baseline",
            results=[
                self._record("baseline", self.config.devices[0], overall_status="PASS"),
                self._record("baseline", self.config.devices[1], overall_status="FAIL"),
            ],
        )
        self.service.set_baseline("Test Site", "baseline")
        self._store_batch(
            "current",
            results=[
                self._record("current", self.config.devices[0], overall_status="FAIL"),
                self._record("current", self.config.devices[1], overall_status="PASS"),
            ],
        )

        comparison = self.service.compare("current")
        by_name = {item.device_name: item for item in comparison.comparisons}

        self.assertEqual(by_name["PLC-01"].status, "NEW_FAILURE")
        self.assertEqual(by_name["PLC-02"].status, "RECOVERED")

    def test_compare_detects_value_change_and_latency_degradation(self) -> None:
        self._store_batch(
            "baseline",
            results=[
                self._record("baseline", self.config.devices[0], values=[1, 2]),
                self._record("baseline", self.config.devices[1], ping_avg_ms=50.0),
            ],
        )
        self.service.set_baseline("Test Site", "baseline")
        self._store_batch(
            "current",
            results=[
                self._record("current", self.config.devices[0], values=[1, 3]),
                self._record("current", self.config.devices[1], ping_avg_ms=200.0),
            ],
        )

        comparison = self.service.compare("current")
        by_name = {item.device_name: item for item in comparison.comparisons}

        self.assertEqual(by_name["PLC-01"].status, "VALUE_CHANGED")
        self.assertTrue(by_name["PLC-01"].value_changed)
        self.assertEqual(by_name["PLC-02"].status, "LATENCY_DEGRADED")
        self.assertEqual(by_name["PLC-02"].latency_delta_ms, 150.0)

    def test_compare_marks_new_and_baseline_only_devices(self) -> None:
        self._store_batch(
            "baseline",
            results=[self._record("baseline", self.config.devices[0])],
        )
        self.service.set_baseline("Test Site", "baseline")
        self._store_batch(
            "current",
            results=[self._record("current", self.config.devices[1])],
        )

        comparison = self.service.compare("current")
        by_name = {item.device_name: item for item in comparison.comparisons}

        self.assertEqual(by_name["PLC-02"].status, "NEW_DEVICE")
        self.assertEqual(by_name["PLC-01"].status, "BASELINE_ONLY")

    def test_set_baseline_requires_completed_batch(self) -> None:
        self._store_batch("running", status="running")

        with self.assertRaises(ValueError):
            self.service.set_baseline("Test Site", "running")

    def test_compare_requires_completed_batch(self) -> None:
        self._store_batch("running", status="running")

        with self.assertRaises(ValueError):
            self.service.compare("running")

    def test_delete_device_check_batch_route(self) -> None:
        self._store_batch("batch-1", results=[self._record("batch-1", self.config.devices[0])])

        with patch.object(main, "history", self.repository):
            response = main.delete_device_check_batch("batch-1")

        self.assertEqual(response.status_code, 204)
        with self.assertRaises(LookupError):
            self.repository.get_network_batch("batch-1")

    def test_delete_baseline_device_check_batch_returns_conflict(self) -> None:
        self._store_batch("batch-1", results=[self._record("batch-1", self.config.devices[0])])
        self.service.set_baseline("Test Site", "batch-1")

        with patch.object(main, "history", self.repository):
            with self.assertRaises(HTTPException) as raised:
                main.delete_device_check_batch("batch-1")

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
