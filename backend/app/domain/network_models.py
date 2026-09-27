from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ..schemas import NetworkCheckResult, NetworkMode, NetworkStatus, SiteConfig, DeviceConfig


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


class NetworkDeviceTrend(BaseModel):
    device_name: str
    current_status: NetworkStatus
    sample_count: int
    historical_failure_count: int
    intermittent_disconnect: bool
    previous_avg_latency_ms: float | None = None
    current_avg_latency_ms: float | None = None
    latency_delta_ms: float | None = None
    latency_degraded: bool = False
    previous_avg_loss_percent: float | None = None
    current_loss_percent: float | None = None
    loss_delta_percent: float | None = None
    loss_degraded: bool = False
    summary: str


class NetworkBatchTrend(BaseModel):
    batch_id: str
    site_name: str
    mode: NetworkMode
    historical_batch_count: int
    latency_degraded_count: int
    loss_degraded_count: int
    intermittent_disconnect_count: int
    summary: str
    devices: list[NetworkDeviceTrend]
    generated_at: datetime


class NetworkReportContext(BaseModel):
    batch: NetworkBatch
    results: list[NetworkCheckRecord]
    trend: NetworkBatchTrend
    generated_at: datetime