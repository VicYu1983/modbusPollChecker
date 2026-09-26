from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from pydantic import BaseModel

from ..domain.models import ReportContext
from ..ports.history import HistoryRepository
from ..ports.report import ReportRenderer
from .comparison_service import ComparisonService


class RenderedReport(BaseModel):
    content: bytes
    content_type: str
    file_extension: str
    filename: str


class UnsupportedReportFormatError(ValueError):
    pass


class ReportService:
    def __init__(
        self,
        history: HistoryRepository,
        comparison: ComparisonService,
        renderers: Mapping[str, ReportRenderer],
    ) -> None:
        self.history = history
        self.comparison = comparison
        self.renderers = dict(renderers)

    def render(self, batch_id: str, report_format: str) -> RenderedReport:
        renderer = self.renderers.get(report_format)
        if renderer is None:
            raise UnsupportedReportFormatError(report_format)
        batch = self.history.get_batch(batch_id)
        if batch.status != "completed":
            raise ValueError("report is available after batch completion")
        context = ReportContext(
            batch=batch,
            records=self.history.list_records(batch_id),
            comparison=self.comparison.compare(batch_id),
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