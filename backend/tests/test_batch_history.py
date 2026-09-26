from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

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


class BlockingChecker(PassingChecker):
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def check_device(self, device: DeviceConfig) -> CheckResult:
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        return super().check_device(device)


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

    def test_cancelling_batch_stops_queued_device_checks(self) -> None:
        checker = BlockingChecker()
        service = BatchService(self.repository, checker, max_workers=1)
        config = SiteConfig(
            site_name="Test Site",
            devices=[
                DeviceConfig(name=f"PLC-{index}", ip=f"127.0.0.{index}")
                for index in range(1, 4)
            ],
        )
        try:
            batch = service.start_batch(config)
            self.assertTrue(checker.started.wait(timeout=1))
            self.assertTrue(service.cancel_batch(batch.id))
            checker.release.set()
        finally:
            checker.release.set()
            service.shutdown()

        cancelled = self.repository.get_batch(batch.id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(checker.calls, 1)
        self.assertEqual(len(self.repository.list_records(batch.id)), 1)

    def test_v1_database_migration_preserves_records_and_baseline(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy.db"
        repository = SqliteHistoryRepository(legacy_path)
        with legacy_path.open("wb"):
            pass
        import sqlite3

        connection = sqlite3.connect(legacy_path)
        try:
            connection.executescript(
                (repository.migrations_path / "0001_init.sql").read_text(encoding="utf-8")
            )
            connection.execute(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (1, ?)",
                (datetime.now(timezone.utc).isoformat(),),
            )
            connection.commit()
        finally:
            connection.close()

        batch = self._batch()
        repository.create_batch(batch)
        device = batch.config_snapshot.devices[0]
        result = PassingChecker().check_device(device)
        repository.save_record(
            CheckRecord(batch_id=batch.id, result=result, device_snapshot=device)
        )
        repository.set_baseline(batch.site_name, batch.id)

        repository.initialize()
        repository.update_batch_status(
            batch.id,
            "cancelled",
            completed_at=datetime.now(timezone.utc),
        )

        self.assertEqual(repository.get_batch(batch.id).status, "cancelled")
        self.assertEqual(len(repository.list_records(batch.id)), 1)
        self.assertEqual(
            repository.get_baseline(batch.site_name).baseline_batch_id,
            batch.id,
        )
        connection = sqlite3.connect(legacy_path)
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()