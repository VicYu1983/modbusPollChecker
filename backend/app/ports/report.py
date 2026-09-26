from __future__ import annotations

from typing import Protocol

from ..domain.models import ReportContext

class ReportRenderer(Protocol):
    content_type: str
    file_extension: str

    def render(self, context: ReportContext) -> bytes: ...