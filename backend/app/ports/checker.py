from typing import Protocol

from ..schemas import CheckResult, DeviceConfig


class DeviceChecker(Protocol):
    def check_device(self, device: DeviceConfig) -> CheckResult: ...