from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.network_models import NetworkBatch, NetworkBatchCounts, NetworkCheckRecord
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import DeviceConfig, NetworkCheckResult, SiteConfig
from app.services.network_trend_service import NetworkTrendService


class NetworkTrendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(Path(self.temporary_directory.name) / "history.db")
        self.repository.initialize()
        self.device = DeviceConfig(name="PLC-01", ip="192.0.2.10")
        self.config = SiteConfig(site_name="Test Site", devices=[self.device])
        self.base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _save_batch(
        self,
        batch_id: str,
        index: int,
        *,
        latency: float,
        loss: float,
        status: str = "PASS",
        mode: str = "network_and_port",
    ) -> None:
        started_at = self.base_time + timedelta(days=index)
        batch = NetworkBatch(
            id=batch_id,
            site_name=self.config.site_name,
            mode=mode,
            status="completed",
            device_names=[self.device.name],
            config_snapshot=self.config,
            started_at=started_at,
            completed_at=started_at + timedelta(seconds=2),
        )
        self.repository.create_network_batch(batch)
        result = NetworkCheckResult(
            device_name=self.device.name,
            target_ip=self.device.ip,
            timestamp=started_at,
            mode=mode,
            ping_state="PASS" if status == "PASS" else "TIMEOUT",
            ping_attempts=4,
            ping_success_count=4 if status == "PASS" else 0,
            ping_loss_percent=loss,
            ping_avg_ms=latency,
            tcp_port=self.device.port if mode != "network_only" else None,
            tcp_state="OPEN" if mode != "network_only" else "NOT_TESTED",
            overall_status=status,
        )
        self.repository.save_network_result(
            NetworkCheckRecord(
                batch_id=batch_id,
                result=result,
                device_snapshot=self.device,
            ),
            NetworkBatchCounts(
                pass_count=1 if status == "PASS" else 0,
                timeout_count=1 if status == "TIMEOUT" else 0,
                fail_count=1 if status == "FAIL" else 0,
            ),
        )

    def test_compares_recent_same_mode_latency_loss_and_interruption(self) -> None:
        self._save_batch("prior-pass", 0, latency=10, loss=0)
        self._save_batch("prior-fail", 1, latency=10, loss=0, status="FAIL")
        self._save_batch("other-mode", 2, latency=50, loss=90, mode="network_only")
        self._save_batch("current", 3, latency=20, loss=25)

        trend = NetworkTrendService(self.repository).compare("current")
        device_trend = trend.devices[0]

        self.assertEqual(trend.historical_batch_count, 2)
        self.assertEqual(device_trend.previous_avg_latency_ms, 10)
        self.assertEqual(device_trend.latency_delta_ms, 10)
        self.assertEqual(device_trend.previous_avg_loss_percent, 0)
        self.assertEqual(device_trend.loss_delta_percent, 25)
        self.assertTrue(device_trend.intermittent_disconnect)
        self.assertEqual(device_trend.historical_failure_count, 1)

    def test_trend_requires_completed_batch(self) -> None:
        batch = NetworkBatch(
            id="running",
            site_name=self.config.site_name,
            mode="network_only",
            status="running",
            device_names=[self.device.name],
            config_snapshot=self.config,
            started_at=self.base_time,
        )
        self.repository.create_network_batch(batch)

        with self.assertRaises(ValueError):
            NetworkTrendService(self.repository).compare(batch.id)


if __name__ == "__main__":
    unittest.main()
