from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..domain.network_models import (
    NetworkBatch,
    NetworkBatchCounts,
    NetworkBatchStatus,
    NetworkCheckRecord,
)


class NetworkHistoryRepository(Protocol):
    def create_network_batch(self, batch: NetworkBatch) -> None: ...

    def update_network_batch_status(
        self,
        batch_id: str,
        status: NetworkBatchStatus,
        *,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def get_network_batch(self, batch_id: str) -> NetworkBatch: ...

    def list_network_batches(
        self,
        site_name: str | None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[NetworkBatch], int]: ...

    def save_network_result(
        self,
        record: NetworkCheckRecord,
        counts: NetworkBatchCounts,
    ) -> None: ...

    def list_network_results(self, batch_id: str) -> list[NetworkCheckRecord]: ...