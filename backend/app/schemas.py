from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator, model_validator


FunctionCode = Literal["01", "02", "03", "04"]
AddressMode = Literal["dec", "hex"]
Status = Literal["PASS", "FAIL", "TIMEOUT", "CONFIG_ERROR", "UNKNOWN"]


class DeviceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    ip: IPvAnyAddress
    port: int = Field(default=502, ge=1, le=65535)
    unit_id: int = Field(default=1, ge=0, le=247)
    address: int = Field(default=0, ge=0)
    quantity: int = Field(default=1, ge=1, le=2000)
    function: FunctionCode = "03"
    expected: str | None = None
    address_mode: AddressMode = "dec"
    connect_timeout_ms: int = Field(default=3000, gt=0)
    response_timeout_ms: int = Field(default=1000, gt=0)
    scan_rate_ms: int = Field(default=0, ge=0)
    delay_between_polls_ms: int = Field(default=20, ge=0)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_register_quantity(self) -> "DeviceConfig":
        if self.function in {"03", "04"} and self.quantity > 125:
            raise ValueError("quantity must be between 1 and 125 for register reads")
        return self


class SiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    site_name: str = Field(min_length=1, max_length=100)
    devices: list[DeviceConfig] = Field(default_factory=list)

    @field_validator("site_name")
    @classmethod
    def site_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("site_name must not be blank")
        return value.strip()

    @field_validator("devices")
    @classmethod
    def device_names_must_be_unique(cls, devices: list[DeviceConfig]) -> list[DeviceConfig]:
        names = [device.name for device in devices]
        if len(names) != len(set(names)):
            raise ValueError("device names must be unique")
        return devices


class CheckResult(BaseModel):
    device_name: str
    timestamp: datetime
    status: Status
    ip: IPvAnyAddress
    port: int
    unit_id: int
    function: FunctionCode
    address: int
    plc_address: int
    quantity: int
    values: list[int | bool] = Field(default_factory=list)
    elapsed_ms: int = Field(ge=0)
    error_type: str | None = None
    error_message: str | None = None


class CheckRequest(BaseModel):
    device_name: str | None = None


class BatchCreateRequest(BaseModel):
    site_name: str | None = None
    device_names: list[str] | None = None
    note: str | None = Field(default=None, max_length=500)
    resume_polling: bool = True


class PollingStatus(BaseModel):
    active: bool
    started_at: datetime | None = None
    last_poll_at: datetime | None = None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
