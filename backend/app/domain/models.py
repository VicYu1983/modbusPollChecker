from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas import CheckResult, DeviceConfig, SiteConfig


BatchMode = Literal["single", "full"]
BatchStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


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


ComparisonStatus = Literal[
    "UNCHANGED_PASS",
    "UNCHANGED_FAILURE",
    "NEW_FAILURE",
    "RECOVERED",
    "VALUE_CHANGED",
    "LATENCY_DEGRADED",
    "CONFIG_CHANGED",
    "BASELINE_ONLY",
    "NEW_DEVICE",
    "NO_BASELINE",
]


class DeviceComparison(BaseModel):
    device_name: str
    status: ComparisonStatus
    current: CheckRecord | None = None
    baseline: CheckRecord | None = None
    response_time_delta_ms: int | None = None


class BatchComparison(BaseModel):
    batch_id: str
    baseline_batch_id: str | None = None
    baseline_set_at: datetime | None = None
    comparisons: list[DeviceComparison]


class ReportContext(BaseModel):
    batch: CheckBatch
    records: list[CheckRecord]
    comparison: BatchComparison
    generated_at: datetime


class BatchListResponse(BaseModel):
    items: list[CheckBatch]
    total: int


class BatchDetailResponse(BaseModel):
    batch: CheckBatch
    records: list[CheckRecord]
    completed_device_count: int