from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ..schemas import NetworkCheckResult, NetworkMode, SiteConfig, DeviceConfig


NetworkBatchStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class NetworkBatchCounts(BaseModel):
    pass_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    config_error_count: int = 0
    partial_count: int = 0
    unknown_count: int = 0


class NetworkBatch(BaseModel):
    id: str
    site_name: str
    mode: NetworkMode
    status: NetworkBatchStatus
    device_names: list[str]
    config_snapshot: SiteConfig
    max_concurrency: int = 20
    started_at: datetime
    completed_at: datetime | None = None
    completed_device_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    config_error_count: int = 0
    partial_count: int = 0
    unknown_count: int = 0
    error_message: str | None = None


class NetworkCheckRecord(BaseModel):
    id: int | None = None
    batch_id: str
    result: NetworkCheckResult
    device_snapshot: DeviceConfig


class NetworkBatchDetailResponse(BaseModel):
    batch: NetworkBatch
    results: list[NetworkCheckRecord]
    completed_device_count: int


class NetworkBatchListResponse(BaseModel):
    items: list[NetworkBatch]
    total: int