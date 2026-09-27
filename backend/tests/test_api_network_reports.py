from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import main
from app.domain.network_models import NetworkBatch, NetworkBatchCounts, NetworkCheckRecord
from app.renderers.network_csv_report import NetworkCsvReportRenderer
from app.renderers.network_html_report import NetworkHtmlReportRenderer
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import DeviceConfig, NetworkCheckResult, SiteConfig
from app.services.network_report_service import NetworkReportService
from app.services.network_trend_service import NetworkTrendService


class NetworkReportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(Path(self.temporary_directory.name) / "history.db")
        self.repository.initialize()
        self.device = DeviceConfig(name="PLC-01", ip="192.0.2.10")
        self.config = SiteConfig(site_name="Test Site", devices=[self.device])
        self.started = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self._save("previous", self.started - timedelta(days=1), 4.0, "PASS")
        self._save("current", self.started, 12.0, "PASS")
        self.trends = NetworkTrendService(self.repository)
        self.reports = NetworkReportService(
            self.repository,
            self.trends,
            {"csv": NetworkCsvReportRenderer(), "html": NetworkHtmlReportRenderer()},
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _save(self, batch_id: str, started: datetime, latency: float, status: str) -> None:
        batch = NetworkBatch(
            id=batch_id,
            site_name=self.config.site_name,
            mode="network_and_port",
            status="completed",
            device_names=[self.device.name],
            config_snapshot=self.config,
            started_at=started,
            completed_at=started + timedelta(seconds=1),
        )
        self.repository.create_network_batch(batch)
        result = NetworkCheckResult(
            device_name=self.device.name,
            target_ip=self.device.ip,
            timestamp=started,
            mode="network_and_port",
            ping_state="PASS",
            ping_attempts=4,
            ping_success_count=4,
            ping_loss_percent=0,
            ping_avg_ms=latency,
            tcp_port=502,
            tcp_state="OPEN",
            overall_status=status,
            diagnosis_summary="指定網路測試階段均通過。",
        )
        self.repository.save_network_result(
            NetworkCheckRecord(batch_id=batch_id, result=result, device_snapshot=self.device),
            NetworkBatchCounts(pass_count=1 if status == "PASS" else 0),
        )

    def test_trend_and_csv_html_download_routes(self) -> None:
        with patch.multiple(
            main,
            history=self.repository,
            network_trend_service=self.trends,
            network_report_service=self.reports,
        ):
            trend = main.get_network_batch_trend("current")
            csv_response = main.download_network_batch_report("current", "csv")
            html_response = main.download_network_batch_report("current", "html")

        self.assertEqual(trend.historical_batch_count, 1)
        self.assertEqual(trend.devices[0].latency_delta_ms, 8)
        self.assertIn("text/csv", csv_response.headers["content-type"])
        self.assertIn("filename*=UTF-8''Test%20Site_current.csv", csv_response.headers["content-disposition"])
        self.assertIn(b"diagnosis_summary", csv_response.body)
        self.assertIn("text/html", html_response.headers["content-type"])
        self.assertIn("歷史趨勢摘要".encode(), html_response.body)

    def test_running_batch_report_returns_conflict(self) -> None:
        running = NetworkBatch(
            id="running",
            site_name=self.config.site_name,
            mode="network_and_port",
            status="running",
            device_names=[self.device.name],
            config_snapshot=self.config,
            started_at=self.started,
        )
        self.repository.create_network_batch(running)
        with patch.object(main, "network_report_service", self.reports):
            with self.assertRaises(HTTPException) as raised:
                main.download_network_batch_report("running", "csv")

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
