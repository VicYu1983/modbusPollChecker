from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import CheckResult, DeviceConfig, SiteConfig


BatchMode = Literal["single", "full"]
BatchStatus = Literal["pending", "running", "completed", "failed"]


class BatchCounts(BaseModel):
    pass_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    config_error_count: int = 0
    unknown_count: int = 0


class CheckBatch(BaseModel):
    id: str
    site_name: str
    mode: BatchMode
    status: BatchStatus
    device_names: list[str]
    config_snapshot: SiteConfig
    note: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    pass_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    config_error_count: int = 0
    unknown_count: int = 0
    error_message: str | None = None


class CheckRecord(BaseModel):
    id: int | None = None
    batch_id: str
    result: CheckResult
    device_snapshot: DeviceConfig


class SiteBaseline(BaseModel):
    site_name: str
    baseline_batch_id: str
    updated_at: datetime


class BatchListResponse(BaseModel):
    items: list[CheckBatch]
    total: int


class BatchDetailResponse(BaseModel):
    batch: CheckBatch
    records: list[CheckRecord]
    completed_device_count: int