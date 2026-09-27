from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from unittest.mock import patch

from app import main
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import DeviceConfig, NetworkBatchCreateRequest, NetworkCheckResult, SiteConfig
from app.services.network_batch_service import NetworkBatchService
from app.site_store import SiteStore


class PassingAdapter:
    async def check_device(self, device: DeviceConfig, mode: str) -> NetworkCheckResult:
        return NetworkCheckResult(
            device_name=device.name,
            target_ip=device.ip,
            timestamp=datetime.now(timezone.utc),
            mode=mode,
            ping_state="PASS",
            ping_attempts=1,
            ping_success_count=1,
            ping_loss_percent=0,
            tcp_port=device.port if mode != "network_only" else None,
            tcp_state="OPEN" if mode != "network_only" else "NOT_TESTED",
            overall_status="PASS",
        )


class BlockingAdapter(PassingAdapter):
    def __init__(self) -> None:
        self.started = Event()
        self.calls = 0

    async def check_device(self, device: DeviceConfig, mode: str) -> NetworkCheckResult:
        self.calls += 1
        self.started.set()
        await asyncio.Event().wait()
        return await super().check_device(device, mode)


class NetworkBatchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.store = SiteStore(root / "sites")
        self.store.save(
            SiteConfig(
                site_name="Test Site",
                devices=[
                    DeviceConfig(name="PLC-01", ip="192.0.2.1"),
                    DeviceConfig(name="PLC-02", ip="192.0.2.2"),
                ],
            )
        )
        self.repository = SqliteHistoryRepository(root / "history.db")
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_list_and_get_network_batch(self) -> None:
        service = NetworkBatchService(self.repository, PassingAdapter())  # type: ignore[arg-type]
        try:
            with patch.multiple(
                main,
                store=self.store,
                history=self.repository,
                network_batch_service=service,
            ):
                batch = main.create_network_check_batch(
                    NetworkBatchCreateRequest(site_name="Test Site", max_concurrency=2)
                )
                deadline = datetime.now(timezone.utc).timestamp() + 2
                while self.repository.get_network_batch(batch.id).status in {"pending", "running"}:
                    if datetime.now(timezone.utc).timestamp() >= deadline:
                        self.fail("network batch did not finish")
                    Event().wait(0.01)
                listing = main.list_network_check_batches("Test Site", offset=0, limit=20)
                detail = main.get_network_check_batch(batch.id)
        finally:
            service.shutdown()

        self.assertEqual(listing.total, 1)
        self.assertEqual(listing.items[0].id, batch.id)
        self.assertEqual(detail.batch.status, "completed")
        self.assertEqual(detail.completed_device_count, 2)
        self.assertEqual(detail.batch.pass_count, 2)

    def test_cancel_network_batch_api_stops_in_flight_checks(self) -> None:
        adapter = BlockingAdapter()
        service = NetworkBatchService(self.repository, adapter)  # type: ignore[arg-type]
        try:
            with patch.multiple(
                main,
                store=self.store,
                history=self.repository,
                network_batch_service=service,
            ):
                batch = main.create_network_check_batch(
                    NetworkBatchCreateRequest(site_name="Test Site", max_concurrency=1)
                )
                self.assertTrue(adapter.started.wait(timeout=1))
                response = main.cancel_network_check_batch(batch.id)
        finally:
            service.shutdown()

        stored = self.repository.get_network_batch(batch.id)
        self.assertEqual(response.id, batch.id)
        self.assertEqual(stored.status, "cancelled")
        self.assertEqual(adapter.calls, 1)


if __name__ == "__main__":
    unittest.main()
