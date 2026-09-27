from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ..schemas import NetworkCheckResult, NetworkMode, NetworkStatus, SiteConfig, DeviceConfig


NetworkBatchStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
NetworkBatchMode = NetworkMode | Literal["mixed"]


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
    mode: NetworkBatchMode
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
    comparison: "DeviceCheckBatchComparison | None" = None


DeviceComparisonStatus = Literal[
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


class DeviceCheckComparison(BaseModel):
    device_name: str
    status: DeviceComparisonStatus
    current_status: str | None = None
    baseline_status: str | None = None
    latency_delta_ms: float | None = None
    loss_delta_percent: float | None = None
    value_changed: bool = False


class DeviceCheckBatchComparison(BaseModel):
    batch_id: str
    baseline_batch_id: str | None = None
    baseline_set_at: datetime | None = None
    comparisons: list[DeviceCheckComparison]


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
    mode: NetworkMode | Literal["mixed"]
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