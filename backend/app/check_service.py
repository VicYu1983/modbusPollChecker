from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from .modbus_adapter import ModbusTcpAdapter
from .schemas import CheckResult, DeviceConfig, SiteConfig


class CheckService:
    def __init__(self, adapter: ModbusTcpAdapter | None = None, max_workers: int = 10) -> None:
        self.adapter = adapter or ModbusTcpAdapter()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._status: dict[str, CheckResult] = {}
        self._lock = Lock()

    def check(self, config: SiteConfig, device_name: str | None = None) -> list[CheckResult]:
        devices = [device for device in config.devices if device.enabled]
        if device_name:
            devices = [device for device in devices if device.name == device_name]
        futures = [self.executor.submit(self.adapter.check_device, device) for device in devices]
        results = [future.result() for future in futures]
        with self._lock:
            self._status.update({result.device_name: result for result in results})
        return sorted(results, key=lambda result: result.device_name)

    def status(self) -> list[CheckResult]:
        with self._lock:
            return sorted(self._status.values(), key=lambda result: result.device_name)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)
