from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..domain.models import BatchCounts, BatchStatus, CheckBatch, CheckRecord


class BatchNotFoundError(LookupError):
    pass


class BatchIsBaselineError(ValueError):
    pass


class HistoryRepository(Protocol):
    def initialize(self) -> None: ...

    def create_batch(self, batch: CheckBatch) -> None: ...

    def update_batch_status(
        self,
        batch_id: str,
        status: BatchStatus,
        *,
        completed_at: datetime | None = None,
        counts: BatchCounts | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def get_batch(self, batch_id: str) -> CheckBatch: ...

    def list_batches(
        self,
        site_name: str | None,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[CheckBatch], int]: ...

    def save_record(self, record: CheckRecord) -> None: ...

    def list_records(self, batch_id: str) -> list[CheckRecord]: ...

    def fail_interrupted_batches(self) -> int: ...