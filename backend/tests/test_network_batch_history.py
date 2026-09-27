from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.domain.network_models import NetworkBatch, NetworkBatchCounts, NetworkCheckRecord
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import DeviceConfig, NetworkCheckResult, SiteConfig


class NetworkBatchHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "history.db"
        self.repository = SqliteHistoryRepository(self.database_path)
        self.repository.initialize()
        self.config = SiteConfig(
            site_name="Test Site",
            devices=[
                DeviceConfig(name="PLC-01", ip="192.0.2.1"),
                DeviceConfig(name="PLC-02", ip="192.0.2.2"),
            ],
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _batch(self, batch_id: str = "network-1", status: str = "pending") -> NetworkBatch:
        return NetworkBatch(
            id=batch_id,
            site_name=self.config.site_name,
            mode="network_and_port",
            status=status,
            device_names=[device.name for device in self.config.devices],
            config_snapshot=self.config,
            max_concurrency=2,
            started_at=datetime.now(timezone.utc),
        )

    def _record(self, batch_id: str, device: DeviceConfig) -> NetworkCheckRecord:
        return NetworkCheckRecord(
            batch_id=batch_id,
            device_snapshot=device,
            result=NetworkCheckResult(
                device_name=device.name,
                target_ip=device.ip,
                timestamp=datetime.now(timezone.utc),
                mode="network_and_port",
                ping_state="PASS",
                ping_attempts=4,
                ping_success_count=4,
                ping_loss_percent=0,
                tcp_port=device.port,
                tcp_state="OPEN",
                overall_status="PASS",
            ),
        )

    def test_network_batch_results_survive_reopen_and_stay_separate(self) -> None:
        batch = self._batch()
        self.repository.create_network_batch(batch)
        self.repository.save_network_result(
            self._record(batch.id, self.config.devices[0]),
            NetworkBatchCounts(pass_count=1),
        )
        self.repository.update_network_batch_status(
            batch.id, "completed", completed_at=datetime.now(timezone.utc)
        )

        reopened = SqliteHistoryRepository(self.database_path)
        reopened.initialize()
        loaded_batch = reopened.get_network_batch(batch.id)
        results = reopened.list_network_results(batch.id)
        modbus_batches, modbus_total = reopened.list_batches(None)

        self.assertEqual(loaded_batch.status, "completed")
        self.assertEqual(loaded_batch.completed_device_count, 1)
        self.assertEqual(loaded_batch.pass_count, 1)
        self.assertEqual(results[0].result.device_name, "PLC-01")
        self.assertEqual(modbus_batches, [])
        self.assertEqual(modbus_total, 0)

    def test_network_batch_list_is_paginated_and_site_scoped(self) -> None:
        self.repository.create_network_batch(self._batch("network-1"))
        self.repository.create_network_batch(self._batch("network-2"))

        batches, total = self.repository.list_network_batches("Test Site", limit=1)
        other_batches, other_total = self.repository.list_network_batches("Other Site")

        self.assertEqual(len(batches), 1)
        self.assertEqual(total, 2)
        self.assertEqual(other_batches, [])
        self.assertEqual(other_total, 0)

    def test_interrupted_network_batch_is_marked_failed(self) -> None:
        self.repository.create_network_batch(self._batch(status="running"))

        self.assertEqual(self.repository.fail_interrupted_batches(), 1)
        recovered = self.repository.get_network_batch("network-1")

        self.assertEqual(recovered.status, "failed")
        self.assertEqual(recovered.error_message, "interrupted by shutdown")


if __name__ == "__main__":
    unittest.main()
