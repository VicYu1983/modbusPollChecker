from __future__ import annotations

import csv
from io import StringIO

from ..services.report_service import ReportContext


class CsvReportRenderer:
    content_type = "text/csv; charset=utf-8"
    file_extension = "csv"

    def render(self, context: ReportContext) -> bytes:
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "site_name",
                "batch_id",
                "checked_at",
                "device_name",
                "ip",
                "port",
                "unit_id",
                "function",
                "address",
                "quantity",
                "status",
                "values",
                "elapsed_ms",
                "error_type",
                "error_message",
                "comparison_status",
                "baseline_status",
                "baseline_values",
                "baseline_elapsed_ms",
                "response_time_delta_ms",
            ]
        )
        for comparison in context.comparison.comparisons:
            record = comparison.current or comparison.baseline
            if record is None:
                continue
            result = comparison.current.result if comparison.current else None
            baseline = comparison.baseline.result if comparison.baseline else None
            writer.writerow(
                [
                    context.batch.site_name,
                    context.batch.id,
                    result.timestamp.isoformat() if result else "",
                    comparison.device_name,
                    str(record.device_snapshot.ip),
                    record.device_snapshot.port,
                    record.device_snapshot.unit_id,
                    record.device_snapshot.function,
                    record.device_snapshot.address,
                    record.device_snapshot.quantity,
                    result.status if result else "NOT_CHECKED",
                    ", ".join(str(value) for value in result.values) if result else "",
                    result.elapsed_ms if result else "",
                    result.error_type or "" if result else "",
                    result.error_message or "" if result else "",
                    comparison.status,
                    baseline.status if baseline else "",
                    ", ".join(str(value) for value in baseline.values) if baseline else "",
                    baseline.elapsed_ms if baseline else "",
                    comparison.response_time_delta_ms
                    if comparison.response_time_delta_ms is not None
                    else "",
                ]
            )
        return output.getvalue().encode("utf-8-sig")