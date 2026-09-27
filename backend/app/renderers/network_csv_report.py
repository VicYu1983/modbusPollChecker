from __future__ import annotations

import csv
import re
from io import StringIO

from ..domain.network_models import NetworkReportContext


class NetworkCsvReportRenderer:
    content_type = "text/csv; charset=utf-8"
    file_extension = "csv"

    @staticmethod
    def _cell(value: object) -> object:
        if not isinstance(value, str):
            return value if value is not None else ""
        safe_value = "'" + value if re.match(r"^[\s]*[=+\-@]", value) else value
        return safe_value

    def render(self, context: NetworkReportContext) -> bytes:
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            [
                "site_name",
                "batch_id",
                "checked_at",
                "mode",
                "device_name",
                "target_ip",
                "ping_state",
                "ping_attempts",
                "ping_success_count",
                "ping_loss_percent",
                "ping_min_ms",
                "ping_avg_ms",
                "ping_max_ms",
                "tcp_port",
                "tcp_state",
                "tcp_connect_ms",
                "max_latency_ms",
                "max_loss_percent",
                "overall_status",
                "failure_stage",
                "error_type",
                "error_message",
                "diagnosis_summary",
                "diagnosis_suggestions",
                "threshold_violations",
                "historical_sample_count",
                "historical_failure_count",
                "previous_avg_latency_ms",
                "latency_delta_ms",
                "previous_avg_loss_percent",
                "loss_delta_percent",
                "intermittent_disconnect",
                "trend_summary",
            ]
        )
        trends = {item.device_name: item for item in context.trend.devices}
        for record in context.results:
            result = record.result
            trend = trends.get(result.device_name)
            writer.writerow(
                self._cell(value)
                for value in [
                    context.batch.site_name,
                    context.batch.id,
                    result.timestamp.isoformat(),
                    result.mode,
                    result.device_name,
                    str(result.target_ip),
                    result.ping_state,
                    result.ping_attempts,
                    result.ping_success_count,
                    result.ping_loss_percent,
                    result.ping_min_ms,
                    result.ping_avg_ms,
                    result.ping_max_ms,
                    result.tcp_port,
                    result.tcp_state,
                    result.tcp_connect_ms,
                    record.device_snapshot.max_latency_ms,
                    record.device_snapshot.max_loss_percent,
                    result.overall_status,
                    result.failure_stage,
                    result.error_type,
                    result.error_message,
                    result.diagnosis_summary,
                    "; ".join(result.diagnosis_suggestions),
                    "; ".join(result.threshold_violations),
                    trend.sample_count if trend else "",
                    trend.historical_failure_count if trend else "",
                    trend.previous_avg_latency_ms if trend else "",
                    trend.latency_delta_ms if trend and trend.latency_delta_ms is not None else "",
                    trend.previous_avg_loss_percent if trend else "",
                    trend.loss_delta_percent if trend and trend.loss_delta_percent is not None else "",
                    trend.intermittent_disconnect if trend else "",
                    trend.summary if trend else "",
                ]
            )
        safe_rows = output.getvalue()
        return safe_rows.encode("utf-8-sig")
