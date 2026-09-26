from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app import main
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import BatchCreateRequest, CheckResult, DeviceConfig, SiteConfig
from app.services.batch_service import BatchService
from app.site_store import SiteStore


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
            values=[1],
            elapsed_ms=2,
        )


class BatchApiTests(unittest.TestCase):
    def test_create_list_and_get_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            site_store = SiteStore(root / "sites")
            config = SiteConfig(
                site_name="Test Site",
                devices=[DeviceConfig(name="PLC-01", ip="127.0.0.1")],
            )
            site_store.save(config)
            repository = SqliteHistoryRepository(root / "history.db")
            service = BatchService(repository, PassingChecker(), max_workers=1)
            repository.initialize()

            try:
                with patch.multiple(
                    main,
                    store=site_store,
                    history=repository,
                    batch_service=service,
                ):
                    batch = main.create_check_batch(
                        BatchCreateRequest(
                            site_name="Test Site",
                            note="field regression",
                        )
                    )
                    service.shutdown()
                    detail = main.get_check_batch(batch.id)
                    batches = main.list_check_batches(
                        site_name="Test Site",
                        offset=0,
                        limit=50,
                    )
            finally:
                service.shutdown()

            self.assertEqual(batch.status, "pending")
            self.assertEqual(detail.completed_device_count, 1)
            self.assertEqual(detail.batch.status, "completed")
            self.assertEqual(detail.records[0].result.status, "PASS")
            self.assertEqual(batches.total, 1)
            self.assertEqual(batches.items[0].id, batch.id)


if __name__ == "__main__":
    unittest.main()