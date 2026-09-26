from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import CheckBatch, CheckRecord
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import CheckResult, DeviceConfig, SiteConfig
from app.services.batch_service import BatchService


class PassingChecker:
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
            plc_address=40001 + device.address,
            quantity=device.quantity,
            values=[10],
            elapsed_ms=3,
        )


class BatchHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "history.db"
        self.repository = SqliteHistoryRepository(self.database_path)
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _batch(self) -> CheckBatch:
        config = SiteConfig(
            site_name="Test Site",
            devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1")],
        )
        return CheckBatch(
            id="batch-1",
            site_name=config.site_name,
            mode="full",
            status="pending",
            device_names=["PLC-01"],
            config_snapshot=config,
            started_at=datetime.now(timezone.utc),
        )

    def test_batch_and_records_survive_repository_recreation(self) -> None:
        batch = self._batch()
        self.repository.create_batch(batch)
        device = batch.config_snapshot.devices[0]
        result = PassingChecker().check_device(device)
        self.repository.save_record(
            CheckRecord(batch_id=batch.id, result=result, device_snapshot=device)
        )

        reopened_repository = SqliteHistoryRepository(self.database_path)
        reopened_repository.initialize()
        loaded_batch = reopened_repository.get_batch(batch.id)
        loaded_records = reopened_repository.list_records(batch.id)

        self.assertEqual(str(loaded_batch.config_snapshot.devices[0].ip), "127.0.0.1")
        self.assertEqual(loaded_records[0].result.values, [10])
        self.assertEqual(loaded_records[0].device_snapshot.name, "PLC-01")

    def test_batch_service_persists_completed_batch_and_results(self) -> None:
        service = BatchService(self.repository, PassingChecker(), max_workers=2)
        config = SiteConfig(
            site_name="Test Site",
            devices=[
                DeviceConfig(name="PLC-01", ip="127.0.0.1"),
                DeviceConfig(name="PLC-02", ip="127.0.0.2"),
            ],
        )
        try:
            batch = service.start_batch(config, note="after wiring change")
        finally:
            service.shutdown()

        completed = self.repository.get_batch(batch.id)
        records = self.repository.list_records(batch.id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.pass_count, 2)
        self.assertEqual(completed.config_snapshot, config)
        self.assertEqual(len(records), 2)
        self.assertEqual(completed.note, "after wiring change")

    def test_list_batches_is_paginated_and_scoped_by_site(self) -> None:
        self.repository.create_batch(self._batch())
        batches, total = self.repository.list_batches("Test Site", limit=1)
        other_batches, other_total = self.repository.list_batches("Other Site")

        self.assertEqual(len(batches), 1)
        self.assertEqual(total, 1)
        self.assertEqual(other_batches, [])
        self.assertEqual(other_total, 0)


if __name__ == "__main__":
    unittest.main()