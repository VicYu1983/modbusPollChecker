from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean

from ..domain.network_models import NetworkBatchTrend, NetworkDeviceTrend
from ..ports.network_history import NetworkHistoryRepository


TREND_BATCH_WINDOW = 10


class NetworkTrendService:
    def __init__(self, history: NetworkHistoryRepository) -> None:
        self.history = history

    def compare(self, batch_id: str) -> NetworkBatchTrend:
        batch = self.history.get_network_batch(batch_id)
        if batch.status != "completed":
            raise ValueError("network trend is available after batch completion")

        recent_batches, _ = self.history.list_network_batches(
            batch.site_name,
            offset=0,
            limit=200,
        )
        previous_batches = [
            item
            for item in recent_batches
            if item.id != batch.id
            and item.status == "completed"
            and item.mode == batch.mode
            and item.started_at < batch.started_at
        ][:TREND_BATCH_WINDOW]
        previous_results = {
            item.id: self.history.list_network_results(item.id)
            for item in previous_batches
        }
        previous_by_device: dict[str, list[object]] = {}
        for records in previous_results.values():
            for record in records:
                previous_by_device.setdefault(record.result.device_name, []).append(record.result)

        current_results = self.history.list_network_results(batch.id)
        trends: list[NetworkDeviceTrend] = []
        for record in current_results:
            result = record.result
            historical = previous_by_device.get(result.device_name, [])
            historical_latencies = [
                item.ping_avg_ms for item in historical if item.ping_avg_ms is not None
            ]
            historical_losses = [
                item.ping_loss_percent for item in historical if item.ping_loss_percent is not None
            ]
            previous_latency = mean(historical_latencies) if historical_latencies else None
            previous_loss = mean(historical_losses) if historical_losses else None
            latency_delta = (
                result.ping_avg_ms - previous_latency
                if result.ping_avg_ms is not None and previous_latency is not None
                else None
            )
            loss_delta = (
                result.ping_loss_percent - previous_loss
                if result.ping_loss_percent is not None and previous_loss is not None
                else None
            )
            historical_failures = sum(item.overall_status != "PASS" for item in historical)
            sample_count = len(historical) + 1
            intermittent = 0 < historical_failures + (result.overall_status != "PASS") < sample_count
            latency_degraded = latency_delta is not None and latency_delta > 0
            loss_degraded = loss_delta is not None and loss_delta > 0
            summaries: list[str] = []
            if intermittent:
                summaries.append(
                    f"近 {sample_count} 次檢查中有 {historical_failures + (result.overall_status != 'PASS')} 次未完全通過"
                )
            if latency_degraded and latency_delta is not None:
                summaries.append(f"Ping 平均延遲較歷史平均增加 {latency_delta:.1f} ms")
            if loss_degraded and loss_delta is not None:
                summaries.append(f"封包遺失率較歷史平均增加 {loss_delta:.1f} 個百分點")
            trends.append(
                NetworkDeviceTrend(
                    device_name=result.device_name,
                    current_status=result.overall_status,
                    sample_count=sample_count,
                    historical_failure_count=historical_failures,
                    intermittent_disconnect=intermittent,
                    previous_avg_latency_ms=previous_latency,
                    current_avg_latency_ms=result.ping_avg_ms,
                    latency_delta_ms=latency_delta,
                    latency_degraded=latency_degraded,
                    previous_avg_loss_percent=previous_loss,
                    current_loss_percent=result.ping_loss_percent,
                    loss_delta_percent=loss_delta,
                    loss_degraded=loss_degraded,
                    summary="；".join(summaries) if summaries else "與近期同模式歷史相比無明顯惡化。",
                )
            )

        latency_count = sum(item.latency_degraded for item in trends)
        loss_count = sum(item.loss_degraded for item in trends)
        intermittent_count = sum(item.intermittent_disconnect for item in trends)
        if not previous_batches:
            summary = "尚無同模式的較早完成批次可供比較。"
        elif latency_count or loss_count or intermittent_count:
            summary = (
                f"比較最近 {len(previous_batches)} 個同模式批次："
                f"{latency_count} 台延遲增加、{loss_count} 台封包遺失增加、"
                f"{intermittent_count} 台出現間歇性未通過。"
            )
        else:
            summary = f"比較最近 {len(previous_batches)} 個同模式批次，未發現明顯網路品質惡化。"

        return NetworkBatchTrend(
            batch_id=batch.id,
            site_name=batch.site_name,
            mode=batch.mode,
            historical_batch_count=len(previous_batches),
            latency_degraded_count=latency_count,
            loss_degraded_count=loss_count,
            intermittent_disconnect_count=intermittent_count,
            summary=summary,
            devices=trends,
            generated_at=datetime.now(timezone.utc),
        )
