from __future__ import annotations

from typing import Protocol

from ..domain.network_models import NetworkReportContext


class NetworkReportRenderer(Protocol):
    content_type: str
    file_extension: str

    def render(self, context: NetworkReportContext) -> bytes: ...