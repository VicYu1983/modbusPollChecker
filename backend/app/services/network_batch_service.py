from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock
from uuid import uuid4

from ..domain.check_profile import CheckProfileConfigError, resolve_check_profile
from ..domain.network_diagnosis import diagnose_network
from ..domain.network_models import (
    NetworkBatch,
    NetworkBatchCounts,
    NetworkBatchDetailResponse,
    NetworkCheckRecord,
)
from ..ports.checker import DeviceChecker
from ..ports.network_history import NetworkHistoryRepository
from ..schemas import DeviceConfig, NetworkCheckResult, NetworkMode, SiteConfig
from ..network_adapter import NetworkAdapter
from .device_check_comparison_service import DeviceCheckComparisonService


class NetworkBatchAlreadyRunningError(RuntimeError):
    pass


class NetworkBatchService:
    def __init__(
        self,
        history: NetworkHistoryRepository,
        adapter: NetworkAdapter,
        *,
        modbus_checker: DeviceChecker | None = None,
        max_concurrency_limit: int = 50,
        comparison: "DeviceCheckComparisonService | None" = None,
    ) -> None:
        self.history = history
        self.adapter = adapter
        self.modbus_checker = modbus_checker
        self.comparison = comparison
        self.max_concurrency_limit = max_concurrency_limit
        self._batch_executor = ThreadPoolExecutor(max_workers=1)
        self._lock = Lock()
        self._active_batch_id: str | None = None
        self._active_cancel_event: Event | None = None
        self._active_loop: asyncio.AbstractEventLoop | None = None
        self._active_tasks: set[asyncio.Task[tuple[DeviceConfig, NetworkCheckResult] | None]] = set()

    def start_batch(
        self,
        config: SiteConfig,
        *,
        device_names: list[str] | None = None,
        mode: NetworkMode | None = None,
        max_concurrency: int = 20,
    ) -> NetworkBatch:
        if not 1 <= max_concurrency <= self.max_concurrency_limit:
            raise ValueError(f"max_concurrency must be between 1 and {self.max_concurrency_limit}")

        available_devices = [
            device for device in config.devices
            if device.enabled
        ]
        if device_names is None:
            selected_devices = available_devices
        else:
            if not device_names:
                raise ValueError("at least one device must be selected")
            if len(device_names) != len(set(device_names)):
                raise ValueError("device names must be unique")
            by_name = {device.name: device for device in available_devices}
            missing = [name for name in device_names if name not in by_name]
            if missing:
                raise ValueError(f"unknown, disabled, or network-disabled devices: {', '.join(missing)}")
            selected_devices = [by_name[name] for name in device_names]
        if not selected_devices:
            raise ValueError("site has no network-enabled devices to check")

        with self._lock:
            if self._active_batch_id is not None:
                raise NetworkBatchAlreadyRunningError(self._active_batch_id)
            now = datetime.now(timezone.utc)
            batch = NetworkBatch(
                id=f"network-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}",
                site_name=config.site_name,
                mode=mode or "mixed",
                status="pending",
                device_names=[device.name for device in selected_devices],
                config_snapshot=config,
                max_concurrency=max_concurrency,
                started_at=now,
            )
            self.history.create_network_batch(batch)
            cancel_event = Event()
            self._active_batch_id = batch.id
            self._active_cancel_event = cancel_event
            try:
                self._batch_executor.submit(self._run_batch, batch, selected_devices, cancel_event)
            except Exception:
                self._active_batch_id = None
                self._active_cancel_event = None
                self.history.update_network_batch_status(
                    batch.id,
                    "failed",
                    completed_at=datetime.now(timezone.utc),
                    error_message="無法啟動網路批次。",
                )
                raise
            return batch

    def _run_batch(
        self,
        batch: NetworkBatch,
        devices: list[DeviceConfig],
        cancel_event: Event,
    ) -> None:
        try:
            self.history.update_network_batch_status(batch.id, "running")
            counts = asyncio.run(self._run_devices(batch, devices, cancel_event))
            final_status = "cancelled" if cancel_event.is_set() else "completed"
            self.history.update_network_batch_status(
                batch.id,
                final_status,
                completed_at=datetime.now(timezone.utc),
            )
        except Exception:
            self.history.update_network_batch_status(
                batch.id,
                "failed",
                completed_at=datetime.now(timezone.utc),
                error_message="網路批次執行失敗。",
            )
        finally:
            with self._lock:
                self._active_batch_id = None
                self._active_cancel_event = None
                self._active_loop = None
                self._active_tasks = set()

    async def _run_devices(
        self,
        batch: NetworkBatch,
        devices: list[DeviceConfig],
        cancel_event: Event,
    ) -> NetworkBatchCounts:
        loop = asyncio.get_running_loop()
        with self._lock:
            self._active_loop = loop

        semaphore = asyncio.Semaphore(batch.max_concurrency)

        async def check_one(
            device: DeviceConfig,
        ) -> tuple[DeviceConfig, NetworkCheckResult] | None:
            if cancel_event.is_set():
                return None
            async with semaphore:
                if cancel_event.is_set():
                    return None
                try:
                    profile = resolve_check_profile(device)
                    result = await self.adapter.check_device(device, profile.network_mode)
                    result.check_profile = profile.name
                    result.tcp_port = profile.tcp_port if profile.network_mode != "network_only" else None
                except asyncio.CancelledError:
                    raise
                except CheckProfileConfigError as error:
                    result = self._config_result(device, error)
                except Exception:
                    result = self._error_result(device, device.check_profile)
                if result.check_profile == "full_stack" and result.tcp_state == "OPEN" and self.modbus_checker:
                    try:
                        modbus = await asyncio.to_thread(self.modbus_checker.check_device, device)
                        result.modbus_status = modbus.status
                        result.modbus_error_type = modbus.error_type
                        result.modbus_error_message = modbus.error_message
                        result.modbus_result = modbus
                        if modbus.status != "PASS":
                            result.overall_status = modbus.status
                            result.failure_stage = "MODBUS"
                            result.error_type = modbus.error_type
                            result.error_message = modbus.error_message
                    except Exception:
                        result.overall_status = "UNKNOWN"
                        result.failure_stage = "MODBUS"
                        result.error_type = "modbus_check_error"
                        result.error_message = "Modbus 測試發生未預期錯誤。"
                        result.modbus_status = "UNKNOWN"
                        result.modbus_error_type = result.error_type
                        result.modbus_error_message = result.error_message
                result = diagnose_network(result, device)
                return device, result

        tasks = {asyncio.create_task(check_one(device)) for device in devices}
        with self._lock:
            self._active_tasks = tasks

        pending = set(tasks)
        counts = NetworkBatchCounts()
        count_fields = {
            "PASS": "pass_count",
            "FAIL": "fail_count",
            "TIMEOUT": "timeout_count",
            "CONFIG_ERROR": "config_error_count",
            "PARTIAL": "partial_count",
            "UNKNOWN": "unknown_count",
        }
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.cancelled():
                    continue
                try:
                    completed = task.result()
                except Exception:
                    continue
                if completed is None:
                    continue
                device, result = completed
                field = count_fields[result.overall_status]
                setattr(counts, field, getattr(counts, field) + 1)
                self.history.save_network_result(
                    NetworkCheckRecord(
                        batch_id=batch.id,
                        result=result,
                        device_snapshot=device,
                    ),
                    counts,
                )
        return counts

    @staticmethod
    def _config_result(device: DeviceConfig, error: Exception) -> NetworkCheckResult:
        return NetworkCheckResult(
            device_name=device.name,
            target_ip=device.ip,
            timestamp=datetime.now(timezone.utc),
            mode="network_only",
            check_profile=device.check_profile,
            ping_state="UNKNOWN",
            ping_attempts=0,
            ping_success_count=0,
            tcp_port=None,
            tcp_state="NOT_TESTED",
            overall_status="CONFIG_ERROR",
            failure_stage="CONFIG",
            error_type="profile_config_error",
            error_message=str(error),
        )

    @staticmethod
    def _error_result(device: DeviceConfig, profile: str) -> NetworkCheckResult:
        mode: NetworkMode = {
            "ping": "network_only",
            "ping_tcp": "network_and_port",
            "full_stack": "full_stack",
        }.get(profile, "network_only")  # type: ignore[assignment]
        return NetworkCheckResult(
            device_name=device.name,
            target_ip=device.ip,
            timestamp=datetime.now(timezone.utc),
            mode=mode,
            check_profile=profile,  # type: ignore[arg-type]
            ping_state="UNKNOWN",
            ping_attempts=0,
            ping_success_count=0,
            tcp_port=device.tcp_port or device.port if mode != "network_only" else None,
            tcp_state="NOT_TESTED",
            overall_status="UNKNOWN",
            error_type="network_check_error",
            error_message="網路測試發生未預期錯誤。",
        )

    def cancel_batch(self, batch_id: str) -> bool:
        with self._lock:
            if self._active_batch_id != batch_id or self._active_cancel_event is None:
                return False
            self._active_cancel_event.set()
            loop = self._active_loop
            tasks = tuple(self._active_tasks)
        if loop is not None and not loop.is_closed():
            def cancel_active_tasks() -> None:
                for task in tasks:
                    if not task.done():
                        task.cancel()

            try:
                loop.call_soon_threadsafe(cancel_active_tasks)
            except RuntimeError:
                pass
        return True

    def get_batch(self, batch_id: str) -> NetworkBatchDetailResponse:
        batch = self.history.get_network_batch(batch_id)
        results = self.history.list_network_results(batch_id)
        comparison = None
        if batch.status == "completed" and self.comparison is not None:
            try:
                comparison = self.comparison.compare(batch_id)
            except ValueError:
                comparison = None
        return NetworkBatchDetailResponse(
            batch=batch,
            results=results,
            completed_device_count=len(results),
            comparison=comparison,
        )

    def shutdown(self) -> None:
        with self._lock:
            batch_id = self._active_batch_id
        if batch_id is not None:
            self.cancel_batch(batch_id)
        self._batch_executor.shutdown(wait=True, cancel_futures=False)
