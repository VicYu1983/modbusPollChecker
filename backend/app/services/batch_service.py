from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from collections.abc import Callable
from threading import Lock
from uuid import uuid4

from ..domain.models import BatchCounts, BatchDetailResponse, CheckBatch, CheckRecord
from ..ports.checker import DeviceChecker
from ..ports.history import HistoryRepository
from ..schemas import CheckResult, DeviceConfig, SiteConfig


class BatchAlreadyRunningError(RuntimeError):
    pass


class BatchService:
    def __init__(
        self,
        history: HistoryRepository,
        checker: DeviceChecker,
        max_workers: int = 10,
    ) -> None:
        self.history = history
        self.checker = checker
        self._batch_executor = ThreadPoolExecutor(max_workers=1)
        self._device_executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = Lock()
        self._active_batch_id: str | None = None

    def start_batch(
        self,
        config: SiteConfig,
        device_names: list[str] | None = None,
        note: str | None = None,
        on_complete: Callable[[], None] | None = None,
    ) -> CheckBatch:
        enabled_devices = [device for device in config.devices if device.enabled]
        if device_names is None:
            selected_devices = enabled_devices
        else:
            if not device_names:
                raise ValueError("at least one device must be selected")
            if len(device_names) != len(set(device_names)):
                raise ValueError("device names must be unique")
            by_name = {device.name: device for device in enabled_devices}
            missing = [name for name in device_names if name not in by_name]
            if missing:
                raise ValueError(f"unknown or disabled devices: {', '.join(missing)}")
            selected_devices = [by_name[name] for name in device_names]
        if not selected_devices:
            raise ValueError("site has no enabled devices to check")

        with self._lock:
            if self._active_batch_id is not None:
                raise BatchAlreadyRunningError(self._active_batch_id)
            now = datetime.now(timezone.utc)
            batch = CheckBatch(
                id=f"{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}",
                site_name=config.site_name,
                mode="full" if device_names is None else "single",
                status="pending",
                device_names=[device.name for device in selected_devices],
                config_snapshot=config,
                note=note,
                started_at=now,
            )
            self.history.create_batch(batch)
            self._active_batch_id = batch.id
            try:
                self._batch_executor.submit(
                    self._run_batch, batch, selected_devices, on_complete
                )
            except Exception as error:
                self._active_batch_id = None
                self.history.update_batch_status(
                    batch.id,
                    "failed",
                    completed_at=datetime.now(timezone.utc),
                    error_message=str(error),
                )
                raise
            return batch

    def _run_batch(
        self,
        batch: CheckBatch,
        devices: list[DeviceConfig],
        on_complete: Callable[[], None] | None,
    ) -> None:
        try:
            self.history.update_batch_status(batch.id, "running")
            futures: dict[Future[CheckResult], DeviceConfig] = {
                self._device_executor.submit(self.checker.check_device, device): device
                for device in devices
            }
            counts = BatchCounts()
            for future in as_completed(futures):
                device = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = self._error_result(device, error)
                self.history.save_record(
                    CheckRecord(
                        batch_id=batch.id,
                        result=result,
                        device_snapshot=device,
                    )
                )
                count_field = {
                    "PASS": "pass_count",
                    "FAIL": "fail_count",
                    "TIMEOUT": "timeout_count",
                    "CONFIG_ERROR": "config_error_count",
                    "UNKNOWN": "unknown_count",
                }[result.status]
                setattr(counts, count_field, getattr(counts, count_field) + 1)
            self.history.update_batch_status(
                batch.id,
                "completed",
                completed_at=datetime.now(timezone.utc),
                counts=counts,
            )
        except Exception as error:
            self.history.update_batch_status(
                batch.id,
                "failed",
                completed_at=datetime.now(timezone.utc),
                error_message=str(error),
            )
        finally:
            with self._lock:
                self._active_batch_id = None
            if on_complete:
                on_complete()

    def get_batch(self, batch_id: str) -> BatchDetailResponse:
        batch = self.history.get_batch(batch_id)
        records = self.history.list_records(batch_id)
        return BatchDetailResponse(
            batch=batch,
            records=records,
            completed_device_count=len(records),
        )

    def list_batches(
        self,
        site_name: str | None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[CheckBatch], int]:
        return self.history.list_batches(
            site_name,
            offset=offset,
            limit=limit,
        )

    @staticmethod
    def _error_result(device: DeviceConfig, error: Exception) -> CheckResult:
        base_addresses = {"01": 1, "02": 10001, "03": 40001, "04": 30001}
        return CheckResult(
            device_name=device.name,
            timestamp=datetime.now(timezone.utc),
            status="UNKNOWN",
            ip=device.ip,
            port=device.port,
            unit_id=device.unit_id,
            function=device.function,
            address=device.address,
            plc_address=base_addresses[device.function] + device.address,
            quantity=device.quantity,
            values=[],
            elapsed_ms=0,
            error_type="CHECK_ERROR",
            error_message=str(error),
        )

    def shutdown(self) -> None:
        self._batch_executor.shutdown(wait=True, cancel_futures=False)
        self._device_executor.shutdown(wait=True, cancel_futures=False)