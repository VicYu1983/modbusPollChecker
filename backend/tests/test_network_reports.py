from __future__ import annotations

import csv
from io import StringIO
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.network_models import NetworkBatch, NetworkBatchCounts, NetworkCheckRecord
from app.renderers.network_csv_report import NetworkCsvReportRenderer
from app.renderers.network_html_report import NetworkHtmlReportRenderer
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import DeviceConfig, NetworkCheckResult, SiteConfig
from app.services.network_report_service import NetworkReportService
from app.services.network_trend_service import NetworkTrendService


class NetworkReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(Path(self.temporary_directory.name) / "history.db")
        self.repository.initialize()
        self.device = DeviceConfig(name="=<img src=x>", ip="192.0.2.10", max_latency_ms=15, max_loss_percent=10)
        self.config = SiteConfig(site_name="Site <North>", devices=[self.device])
        self.current_time = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self._save_batch("prior", self.current_time - timedelta(days=1), 10, 0, "PASS")
        self._save_batch("current", self.current_time, 20, 25, "FAIL")
        self.service = NetworkReportService(
            self.repository,
            NetworkTrendService(self.repository),
            {"csv": NetworkCsvReportRenderer(), "html": NetworkHtmlReportRenderer()},
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _save_batch(
        self,
        batch_id: str,
        started_at: datetime,
        latency: float,
        loss: float,
        status: str,
    ) -> None:
        batch = NetworkBatch(
            id=batch_id,
            site_name=self.config.site_name,
            mode="network_and_port",
            status="completed",
            device_names=[self.device.name],
            config_snapshot=self.config,
            started_at=started_at,
            completed_at=started_at + timedelta(seconds=1),
        )
        self.repository.create_network_batch(batch)
        result = NetworkCheckResult(
            device_name=self.device.name,
            target_ip=self.device.ip,
            timestamp=started_at,
            mode="network_and_port",
            ping_state="PASS",
            ping_attempts=4,
            ping_success_count=4,
            ping_loss_percent=loss,
            ping_avg_ms=latency,
            tcp_port=502,
            tcp_connect_ms=5,
            tcp_state="OPEN",
            overall_status=status,
            failure_stage="PING" if status == "FAIL" else None,
            error_type="network_quality_threshold" if status == "FAIL" else None,
            error_message="延遲與封包遺失超過門檻" if status == "FAIL" else None,
            diagnosis_summary="網路品質超過設備設定門檻。" if status == "FAIL" else "通過",
            diagnosis_suggestions=["檢查線路與交換器 Port。"],
            threshold_violations=["Ping 平均延遲 20.0 ms 超過上限 15 ms"] if status == "FAIL" else [],
        )
        self.repository.save_network_result(
            NetworkCheckRecord(batch_id=batch_id, result=result, device_snapshot=self.device),
            NetworkBatchCounts(pass_count=1 if status == "PASS" else 0, fail_count=1 if status == "FAIL" else 0),
        )

    def test_csv_contains_network_fields_trend_and_formula_protection(self) -> None:
        report = self.service.render("current", "csv")
        rows = list(csv.DictReader(StringIO(report.content.decode("utf-8-sig"))))
        row = rows[0]

        self.assertEqual(report.filename, "Site _North__current.csv")
        self.assertTrue(report.content.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(row["device_name"], "'=<img src=x>")
        self.assertIn("ping_loss_percent", row)
        self.assertIn("threshold_violations", row)
        self.assertIn("latency_delta_ms", row)
        self.assertEqual(row["latency_delta_ms"], "10.0")
        self.assertEqual(row["loss_delta_percent"], "25.0")

    def test_html_report_escapes_dynamic_values_and_shows_trend(self) -> None:
        report = self.service.render("current", "html")
        document = report.content.decode("utf-8")

        self.assertIn("Site &lt;North&gt;", document)
        self.assertIn("=&lt;img src=x&gt;", document)
        self.assertNotIn("<North>", document)
        self.assertIn("歷史趨勢摘要", document)
        self.assertIn("延遲增加", document)
        self.assertIn("Ping 平均延遲 20.0 ms 超過上限", document)

    def test_reports_require_completed_network_batches(self) -> None:
        running = NetworkBatch(
            id="running",
            site_name=self.config.site_name,
            mode="network_and_port",
            status="running",
            device_names=[self.device.name],
            config_snapshot=self.config,
            started_at=self.current_time,
        )
        self.repository.create_network_batch(running)

        with self.assertRaises(ValueError):
            self.service.render("running", "csv")


if __name__ == "__main__":
    unittest.main()
