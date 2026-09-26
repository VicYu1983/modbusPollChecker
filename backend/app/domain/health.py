from __future__ import annotations

from collections.abc import Iterable

from .models import CheckRecord, HealthSummary


def summarize(records: Iterable[CheckRecord]) -> HealthSummary:
    record_list = list(records)
    passed = [record for record in record_list if record.result.status == "PASS"]
    slowest = max(passed, key=lambda record: record.result.elapsed_ms, default=None)
    device_count = len(record_list)

    return HealthSummary(
        device_count=device_count,
        pass_count=len(passed),
        fail_count=sum(record.result.status == "FAIL" for record in record_list),
        timeout_count=sum(record.result.status == "TIMEOUT" for record in record_list),
        config_error_count=sum(
            record.result.status == "CONFIG_ERROR" for record in record_list
        ),
        pass_rate=len(passed) / device_count if device_count else 0.0,
        avg_elapsed_ms=(
            sum(record.result.elapsed_ms for record in passed) / len(passed)
            if passed
            else None
        ),
        slowest_device=slowest.result.device_name if slowest else None,
        slowest_elapsed_ms=slowest.result.elapsed_ms if slowest else None,
    )