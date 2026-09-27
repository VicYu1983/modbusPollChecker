from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock
from time import monotonic

from app.network_adapter import NetworkAdapter
from app.repositories.sqlite_history import SqliteHistoryRepository
from app.schemas import DeviceConfig, NetworkCheckResult, SiteConfig
from app.services.network_batch_service import NetworkBatchService


class PassingNetworkAdapter:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    async def check_device(self, device: DeviceConfig, mode: str) -> NetworkCheckResult:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        with self.lock:
            self.active -= 1
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


class BlockingNetworkAdapter:
    def __init__(self) -> None:
        self.started = Event()
        self.cancelled = Event()
        self.calls = 0

    async def check_device(self, device: DeviceConfig, mode: str) -> NetworkCheckResult:
        self.calls += 1
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")


class RaisingNetworkAdapter:
    async def check_device(self, device: DeviceConfig, mode: str) -> NetworkCheckResult:
        raise RuntimeError("internal probe failure")


class NetworkBatchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = SqliteHistoryRepository(Path(self.temporary_directory.name) / "history.db")
        self.repository.initialize()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _config(self, count: int = 5) -> SiteConfig:
        return SiteConfig(
            site_name="Test",
            devices=[
                DeviceConfig(
                    name=f"PLC-{index}",
                    ip=f"192.0.2.{index}",
                    network_check_enabled=index != count,
                )
                for index in range(1, count + 1)
            ],
        )

    def test_batch_limits_concurrency_filters_network_disabled_and_saves_progress(self) -> None:
        adapter = PassingNetworkAdapter()
        service = NetworkBatchService(self.repository, adapter)  # type: ignore[arg-type]
        try:
            batch = service.start_batch(self._config(), max_concurrency=2)
            deadline = monotonic() + 2
            while self.repository.get_network_batch(batch.id).status in {"pending", "running"}:
                if monotonic() >= deadline:
                    self.fail("network batch did not finish")
                Event().wait(0.01)
        finally:
            service.shutdown()

        detail = service.get_batch(batch.id)
        self.assertEqual(detail.batch.status, "completed")
        self.assertEqual(detail.batch.completed_device_count, 4)
        self.assertEqual(detail.batch.pass_count, 4)
        self.assertEqual(len(detail.results), 4)
        self.assertLessEqual(adapter.max_active, 2)

    def test_cancellation_stops_in_flight_and_queued_devices(self) -> None:
        adapter = BlockingNetworkAdapter()
        service = NetworkBatchService(self.repository, adapter)  # type: ignore[arg-type]
        try:
            batch = service.start_batch(self._config(count=3), max_concurrency=1)
            self.assertTrue(adapter.started.wait(timeout=1))
            self.assertTrue(service.cancel_batch(batch.id))
        finally:
            service.shutdown()

        detail = service.get_batch(batch.id)
        self.assertEqual(detail.batch.status, "cancelled")
        self.assertEqual(adapter.calls, 1)
        self.assertTrue(adapter.cancelled.is_set())
        self.assertEqual(detail.completed_device_count, 0)

    def test_two_hundred_devices_stay_within_default_safe_concurrency(self) -> None:
        adapter = PassingNetworkAdapter()
        service = NetworkBatchService(self.repository, adapter)  # type: ignore[arg-type]
        try:
            batch = service.start_batch(self._config(count=200))
            deadline = monotonic() + 5
            while self.repository.get_network_batch(batch.id).status in {"pending", "running"}:
                if monotonic() >= deadline:
                    self.fail("200-device network batch did not finish")
                Event().wait(0.01)
        finally:
            service.shutdown()

        detail = service.get_batch(batch.id)
        self.assertEqual(detail.batch.status, "completed")
        self.assertEqual(detail.completed_device_count, 199)
        self.assertLessEqual(adapter.max_active, 20)

    def test_unexpected_probe_errors_are_saved_as_unknown(self) -> None:
        service = NetworkBatchService(self.repository, RaisingNetworkAdapter())  # type: ignore[arg-type]
        try:
            batch = service.start_batch(self._config(count=2), device_names=["PLC-1"])
            deadline = monotonic() + 2
            while self.repository.get_network_batch(batch.id).status in {"pending", "running"}:
                if monotonic() >= deadline:
                    self.fail("network batch did not finish")
                Event().wait(0.01)
        finally:
            service.shutdown()

        detail = service.get_batch(batch.id)
        self.assertEqual(detail.batch.status, "completed")
        self.assertEqual(detail.batch.unknown_count, 1)
        self.assertEqual(detail.results[0].result.overall_status, "UNKNOWN")

    def test_rejects_unavailable_devices_and_excessive_concurrency(self) -> None:
        service = NetworkBatchService(self.repository, NetworkAdapter())
        try:
            with self.assertRaises(ValueError):
                service.start_batch(self._config(), device_names=["missing"])
            with self.assertRaises(ValueError):
                service.start_batch(self._config(), max_concurrency=51)
        finally:
            service.shutdown()


if __name__ == "__main__":
    unittest.main()
