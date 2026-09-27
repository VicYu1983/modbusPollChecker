from __future__ import annotations

from datetime import datetime, timezone

from ..domain.network_models import (
    DeviceCheckBatchComparison,
    DeviceCheckComparison,
    DeviceComparisonStatus,
    NetworkCheckRecord,
)
from ..ports.network_history import NetworkHistoryRepository


LATENCY_ABSOLUTE_THRESHOLD_MS = 100
LATENCY_RATIO_THRESHOLD = 2.0
LATENCY_MIN_BASELINE_MS = 20


class DeviceCheckComparisonService:
    def __init__(self, history: NetworkHistoryRepository) -> None:
        self.history = history

    def set_baseline(self, site_name: str, batch_id: str) -> datetime:
        batch = self.history.get_network_batch(batch_id)
        if batch.site_name != site_name:
            raise ValueError("batch belongs to a different site")
        if batch.status != "completed":
            raise ValueError("only completed batches can be set as baseline")
        return self.history.set_device_check_baseline(site_name, batch_id)

    def clear_baseline(self, site_name: str) -> bool:
        return self.history.clear_device_check_baseline(site_name)

    def get_baseline(self, site_name: str) -> str | None:
        return self.history.get_device_check_baseline(site_name)

    def compare(self, batch_id: str) -> DeviceCheckBatchComparison:
        current_batch = self.history.get_network_batch(batch_id)
        if current_batch.status != "completed":
            raise ValueError("comparison is available after batch completion")

        current_records = self.history.list_network_results(batch_id)
        baseline_id = self.history.get_device_check_baseline(current_batch.site_name)
        if baseline_id is None:
            return DeviceCheckBatchComparison(
                batch_id=batch_id,
                comparisons=[
                    DeviceCheckComparison(
                        device_name=record.result.device_name,
                        status="NO_BASELINE",
                        current_status=record.result.overall_status,
                    )
                    for record in current_records
                ],
            )

        baseline_records = self.history.list_network_results(baseline_id)
        baseline_by_name = {record.result.device_name: record for record in baseline_records}
        current_by_name = {record.result.device_name: record for record in current_records}

        comparisons = [
            self._compare_device(record, baseline_by_name.get(record.result.device_name))
            for record in current_records
        ]
        comparisons.extend(
            DeviceCheckComparison(
                device_name=record.result.device_name,
                status="BASELINE_ONLY",
                baseline_status=record.result.overall_status,
            )
            for record in baseline_records
            if record.result.device_name not in current_by_name
        )
        return DeviceCheckBatchComparison(
            batch_id=batch_id,
            baseline_batch_id=baseline_id,
            baseline_set_at=datetime.now(timezone.utc),
            comparisons=comparisons,
        )

    @classmethod
    def _compare_device(
        cls,
        current: NetworkCheckRecord,
        baseline: NetworkCheckRecord | None,
    ) -> DeviceCheckComparison:
        current_result = current.result
        if baseline is None:
            return DeviceCheckComparison(
                device_name=current_result.device_name,
                status="NEW_DEVICE",
                current_status=current_result.overall_status,
            )

        baseline_result = baseline.result
        latency_delta = (
            current_result.ping_avg_ms - baseline_result.ping_avg_ms
            if current_result.ping_avg_ms is not None and baseline_result.ping_avg_ms is not None
            else None
        )
        loss_delta = (
            current_result.ping_loss_percent - baseline_result.ping_loss_percent
            if current_result.ping_loss_percent is not None
            and baseline_result.ping_loss_percent is not None
            else None
        )
        value_changed = cls._values_changed(current_result, baseline_result)

        if cls._config_changed(current, baseline):
            status: DeviceComparisonStatus = "CONFIG_CHANGED"
        elif baseline_result.overall_status == "PASS" and current_result.overall_status != "PASS":
            status = "NEW_FAILURE"
        elif baseline_result.overall_status != "PASS" and current_result.overall_status == "PASS":
            status = "RECOVERED"
        elif baseline_result.overall_status != "PASS" and current_result.overall_status != "PASS":
            status = "UNCHANGED_FAILURE"
        elif value_changed:
            status = "VALUE_CHANGED"
        elif cls._latency_degraded(baseline_result.ping_avg_ms, current_result.ping_avg_ms):
            status = "LATENCY_DEGRADED"
        else:
            status = "UNCHANGED_PASS"

        return DeviceCheckComparison(
            device_name=current_result.device_name,
            status=status,
            current_status=current_result.overall_status,
            baseline_status=baseline_result.overall_status,
            latency_delta_ms=latency_delta,
            loss_delta_percent=loss_delta,
            value_changed=value_changed,
        )

    @staticmethod
    def _values_changed(current: object, baseline: object) -> bool:
        current_modbus = getattr(current, "modbus_result", None)
        baseline_modbus = getattr(baseline, "modbus_result", None)
        if current_modbus is None or baseline_modbus is None:
            return False
        return current_modbus.values != baseline_modbus.values

    @staticmethod
    def _config_changed(current: NetworkCheckRecord, baseline: NetworkCheckRecord) -> bool:
        current_device = current.device_snapshot
        baseline_device = baseline.device_snapshot
        return (
            str(current_device.ip) != str(baseline_device.ip)
            or current_device.check_profile != baseline_device.check_profile
            or current_device.tcp_port != baseline_device.tcp_port
            or current_device.port != baseline_device.port
            or current_device.unit_id != baseline_device.unit_id
            or current_device.function != baseline_device.function
            or current_device.address != baseline_device.address
            or current_device.quantity != baseline_device.quantity
        )

    @staticmethod
    def _latency_degraded(baseline_ms: float | None, current_ms: float | None) -> bool:
        if baseline_ms is None or current_ms is None:
            return False
        if baseline_ms < LATENCY_MIN_BASELINE_MS:
            return False
        return (
            current_ms - baseline_ms >= LATENCY_ABSOLUTE_THRESHOLD_MS
            and current_ms >= baseline_ms * LATENCY_RATIO_THRESHOLD
        )