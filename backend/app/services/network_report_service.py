from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from ..domain.network_models import NetworkReportContext
from ..ports.network_history import NetworkHistoryRepository
from ..ports.network_report import NetworkReportRenderer
from .network_trend_service import NetworkTrendService
from .report_service import RenderedReport, UnsupportedReportFormatError


class NetworkReportService:
    def __init__(
        self,
        history: NetworkHistoryRepository,
        trend_service: NetworkTrendService,
        renderers: Mapping[str, NetworkReportRenderer],
    ) -> None:
        self.history = history
        self.trend_service = trend_service
        self.renderers = dict(renderers)

    def render(self, batch_id: str, report_format: str) -> RenderedReport:
        renderer = self.renderers.get(report_format)
        if renderer is None:
            raise UnsupportedReportFormatError(report_format)
        batch = self.history.get_network_batch(batch_id)
        if batch.status != "completed":
            raise ValueError("network report is available after batch completion")
        context = NetworkReportContext(
            batch=batch,
            results=self.history.list_network_results(batch_id),
            trend=self.trend_service.compare(batch_id),
            generated_at=datetime.now(timezone.utc),
        )
        safe_site_name = "".join(
            "_" if character in '<>:"/\\|?*' else character
            for character in batch.site_name
        ).strip(". ") or "site"
        return RenderedReport(
            content=renderer.render(context),
            content_type=renderer.content_type,
            file_extension=renderer.file_extension,
            filename=f"{safe_site_name}_{batch.id}.{renderer.file_extension}",
        )
