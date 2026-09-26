from __future__ import annotations

from ..domain.models import (
    BatchComparison,
    CheckBatch,
    CheckRecord,
    DeviceComparison,
    SiteBaseline,
)
from ..ports.history import HistoryRepository


COMMUNICATION_FIELDS = ("ip", "port", "unit_id", "function", "address", "quantity")
LATENCY_ABSOLUTE_THRESHOLD_MS = 100
LATENCY_RATIO_THRESHOLD = 2.0
LATENCY_MIN_BASELINE_MS = 20


class ComparisonService:
    def __init__(self, history: HistoryRepository) -> None:
        self.history = history

    def set_baseline(
        self,
        site_name: str,
        batch_id: str,
        *,
        force: bool = False,
    ) -> SiteBaseline:
        batch = self.history.get_batch(batch_id)
        if batch.site_name != site_name:
            raise ValueError("batch belongs to a different site")
        if batch.status != "completed":
            raise ValueError("only completed batches can be set as baseline")
        if batch.mode != "full":
            raise ValueError("only full-site batches can be set as baseline")
        if any((batch.fail_count, batch.timeout_count, batch.config_error_count)) and not force:
            raise BaselineRequiresConfirmationError(
                "batch has failed, timed out, or invalid devices; set force=true to confirm"
            )
        return self.history.set_baseline(site_name, batch_id)

    def compare(self, batch_id: str) -> BatchComparison:
        current_batch = self.history.get_batch(batch_id)
        if current_batch.status != "completed":
            raise ValueError("batch comparison is available after completion")

        current_records = self.history.list_records(batch_id)
        baseline = self.history.get_baseline(current_batch.site_name)
        if baseline is None:
            return BatchComparison(
                batch_id=batch_id,
                comparisons=[
                    DeviceComparison(
                        device_name=record.result.device_name,
                        status="NO_BASELINE",
                        current=record,
                    )
                    for record in current_records
                ],
            )

        baseline_batch = self.history.get_batch(baseline.baseline_batch_id)
        baseline_records = self.history.list_records(baseline.baseline_batch_id)
        baseline_by_name = {
            record.result.device_name: record for record in baseline_records
        }
        current_by_name = {record.result.device_name: record for record in current_records}

        comparisons = [
            self._compare_device(record, baseline_by_name.get(record.result.device_name))
            for record in current_records
        ]
        comparisons.extend(
            DeviceComparison(
                device_name=record.result.device_name,
                status="BASELINE_ONLY",
                baseline=record,
            )
            for record in baseline_records
            if record.result.device_name not in current_by_name
        )
        return BatchComparison(
            batch_id=batch_id,
            baseline_batch_id=baseline_batch.id,
            baseline_set_at=baseline.updated_at,
            comparisons=comparisons,
        )

    @classmethod
    def _compare_device(
        cls,
        current: CheckRecord,
        baseline: CheckRecord | None,
    ) -> DeviceComparison:
        if baseline is None:
            status = "NEW_DEVICE"
            delta = None
        else:
            current_result = current.result
            baseline_result = baseline.result
            delta = current_result.elapsed_ms - baseline_result.elapsed_ms

            if cls._config_changed(current, baseline):
                status = "CONFIG_CHANGED"
            elif baseline_result.status == "PASS" and current_result.status != "PASS":
                status = "NEW_FAILURE"
            elif baseline_result.status != "PASS" and current_result.status == "PASS":
                status = "RECOVERED"
            elif baseline_result.status != "PASS" and current_result.status != "PASS":
                status = "UNCHANGED_FAILURE"
            elif current_result.status == "PASS" and current_result.values != baseline_result.values:
                status = "VALUE_CHANGED"
            elif current_result.status == "PASS" and cls._latency_degraded(
                baseline_result.elapsed_ms,
                current_result.elapsed_ms,
            ):
                status = "LATENCY_DEGRADED"
            else:
                status = "UNCHANGED_PASS"

        return DeviceComparison(
            device_name=current.result.device_name,
            status=status,
            current=current,
            baseline=baseline,
            response_time_delta_ms=delta,
        )

    @staticmethod
    def _config_changed(current: CheckRecord, baseline: CheckRecord) -> bool:
        return any(
            getattr(current.device_snapshot, field)
            != getattr(baseline.device_snapshot, field)
            for field in COMMUNICATION_FIELDS
        )

    @staticmethod
    def _latency_degraded(baseline_ms: int, current_ms: int) -> bool:
        if baseline_ms < LATENCY_MIN_BASELINE_MS:
            return False
        return (
            current_ms - baseline_ms > LATENCY_ABSOLUTE_THRESHOLD_MS
            or current_ms / baseline_ms > LATENCY_RATIO_THRESHOLD
        )


class BaselineRequiresConfirmationError(ValueError):
    pass