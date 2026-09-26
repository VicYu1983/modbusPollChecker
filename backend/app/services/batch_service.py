from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from collections.abc import Callable
from threading import Event, Lock
from uuid import uuid4

from ..domain.diagnosis import diagnose
from ..domain.health import summarize
from ..domain.models import BatchCounts, BatchDetailResponse, CheckBatch, CheckRecord
from ..ports.checker import DeviceChecker
from ..ports.history import HistoryRepository
from ..schemas import CheckResult, DeviceConfig, SiteConfig
from .comparison_service import ComparisonService


class BatchAlreadyRunningError(RuntimeError):
    pass


class BatchService:
    def __init__(
        self,
        history: HistoryRepository,
        checker: DeviceChecker,
        max_workers: int = 10,
        comparison: ComparisonService | None = None,
    ) -> None:
        self.history = history
        self.checker = checker
        self.comparison = comparison
        self._batch_executor = ThreadPoolExecutor(max_workers=1)
        self._device_executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = Lock()
        self._active_batch_id: str | None = None
        self._active_cancel_event: Event | None = None
        self._active_futures: list[Future[CheckResult]] = []

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
            cancel_event = Event()
            self._active_cancel_event = cancel_event
            try:
                self._batch_executor.submit(
                    self._run_batch, batch, selected_devices, on_complete, cancel_event
                )
            except Exception as error:
                self._active_batch_id = None
                self._active_cancel_event = None
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
        cancel_event: Event,
    ) -> None:
        try:
            self.history.update_batch_status(batch.id, "running")
            futures: dict[Future[CheckResult], DeviceConfig] = {}
            if not cancel_event.is_set():
                futures = {
                    self._device_executor.submit(self.checker.check_device, device): device
                    for device in devices
                }
            with self._lock:
                self._active_futures = list(futures)
            if cancel_event.is_set():
                for future in futures:
                    future.cancel()
            counts = BatchCounts()
            for future in as_completed(futures):
                if future.cancelled():
                    continue
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
                "cancelled" if cancel_event.is_set() else "completed",
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
                self._active_cancel_event = None
                self._active_futures = []
            if on_complete:
                on_complete()

    def cancel_batch(self, batch_id: str) -> bool:
        with self._lock:
            if self._active_batch_id != batch_id or self._active_cancel_event is None:
                return False
            self._active_cancel_event.set()
            for future in self._active_futures:
                future.cancel()
            return True

    def get_batch(self, batch_id: str) -> BatchDetailResponse:
        batch = self.history.get_batch(batch_id)
        records = self.history.list_records(batch_id)
        comparisons = {}
        if batch.status == "completed" and self.comparison is not None:
            comparisons = {
                item.device_name: item
                for item in self.comparison.compare(batch_id).comparisons
            }
        enriched_records = []
        for record in records:
            comparison = comparisons.get(record.result.device_name)
            enriched_records.append(
                record.model_copy(
                    update={
                        "comparison_status": comparison.status if comparison else None,
                        "response_time_delta_ms": (
                            comparison.response_time_delta_ms if comparison else None
                        ),
                        "diagnosis": diagnose(
                            record.result,
                            comparison.status if comparison else None,
                        ),
                    }
                )
            )
        records = enriched_records
        health_summary = summarize(records)
        health_summary.new_failure_count = sum(
            item.status == "NEW_FAILURE" for item in comparisons.values()
        )
        return BatchDetailResponse(
            batch=batch,
            records=records,
            completed_device_count=len(records),
            health_summary=health_summary,
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

    def delete_batch(self, batch_id: str) -> None:
        self.history.delete_batch(batch_id)

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