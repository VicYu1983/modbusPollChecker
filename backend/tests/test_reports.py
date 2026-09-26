from __future__ import annotations

import csv
from io import StringIO
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import CheckBatch, CheckRecord
from app.renderers.csv_report import CsvReportRenderer
from app.renderers.html_report import HtmlReportRenderer
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import CheckResult, DeviceConfig, SiteConfig
from app.services.comparison_service import ComparisonService
from app.services.report_service import ReportService


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(
            Path(self.temporary_directory.name) / "history.db"
        )
        self.repository.initialize()
        self.comparison = ComparisonService(self.repository)
        self.service = ReportService(
            self.repository,
            self.comparison,
            {"csv": CsvReportRenderer(), "html": HtmlReportRenderer()},
        )
        self._save_batch("baseline", [
            self._record("baseline", "PLC-01", values=[1]),
            self._record("baseline", "PLC-02", values=[2]),
        ])
        self._save_batch("current", [self._record("current", "PLC-01", values=[9])])
        self.comparison.set_baseline("Site <North>", "baseline")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def _record(batch_id: str, name: str, *, values: list[int]) -> CheckRecord:
        device = DeviceConfig(name=name, ip="127.0.0.1")
        result = CheckResult(
            device_name=name,
            timestamp=datetime.now(timezone.utc),
            status="PASS",
            ip=device.ip,
            port=device.port,
            unit_id=device.unit_id,
            function=device.function,
            address=device.address,
            plc_address=40001,
            quantity=device.quantity,
            values=values,
            elapsed_ms=25,
        )
        return CheckRecord(batch_id=batch_id, result=result, device_snapshot=device)

    def _save_batch(self, batch_id: str, records: list[CheckRecord]) -> None:
        config = SiteConfig(
            site_name="Site <North>",
            devices=[record.device_snapshot for record in records],
        )
        self.repository.create_batch(
            CheckBatch(
                id=batch_id,
                site_name=config.site_name,
                mode="full",
                status="completed",
                device_names=[record.result.device_name for record in records],
                config_snapshot=config,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                pass_count=len(records),
            )
        )
        for record in records:
            self.repository.save_record(record)

    def test_csv_includes_utf8_bom_and_baseline_only_devices(self) -> None:
        report = self.service.render("current", "csv")

        self.assertEqual(report.filename, "Site _North__current.csv")
        self.assertTrue(report.content.startswith(b"\xef\xbb\xbf"))
        text = report.content.decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(text)))
        changed = next(row for row in rows if row["device_name"] == "PLC-01")
        self.assertEqual(changed["comparison_status"], "VALUE_CHANGED")
        self.assertIn("BASELINE_ONLY", text)
        self.assertIn("PLC-02", text)

    def test_html_escapes_site_name_and_lists_baseline_only_devices(self) -> None:
        report = self.service.render("current", "html")
        document = report.content.decode("utf-8")

        self.assertIn("Site &lt;North&gt;", document)
        self.assertNotIn("<North>", document)
        self.assertIn("BASELINE_ONLY", document)
        self.assertIn("PLC-02", document)


if __name__ == "__main__":
    unittest.main()