from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from time import monotonic
from collections.abc import Callable

from .modbus_adapter import ModbusTcpAdapter
from .schemas import CheckResult, DeviceConfig, PollingStatus, SiteConfig

DEFAULT_POLL_INTERVAL_MS = 1000


class CheckService:
    def __init__(self, adapter: ModbusTcpAdapter | None = None, max_workers: int = 10) -> None:
        self.adapter = adapter or ModbusTcpAdapter()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._status: dict[str, CheckResult] = {}
        self._lock = Lock()
        self._polling_thread: Thread | None = None
        self._polling_stop = Event()
        self._started_at: datetime | None = None
        self._last_poll_at: datetime | None = None

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

    def start_polling(self, config_loader: Callable[[], SiteConfig]) -> bool:
        with self._lock:
            if self._polling_thread and self._polling_thread.is_alive():
                return False
            self._polling_stop.clear()
            self._started_at = datetime.now(timezone.utc)
            self._polling_thread = Thread(
                target=self._polling_loop,
                args=(config_loader,),
                name="modbus-polling",
                daemon=True,
            )
            self._polling_thread.start()
            return True

    def stop_polling(self) -> bool:
        with self._lock:
            thread = self._polling_thread
            if not thread or not thread.is_alive():
                self._polling_thread = None
                return False
            self._polling_stop.set()
        thread.join(timeout=5)
        with self._lock:
            self._polling_thread = None
        return True

    def polling_status(self) -> PollingStatus:
        with self._lock:
            active = bool(self._polling_thread and self._polling_thread.is_alive())
            return PollingStatus(
                active=active,
                started_at=self._started_at if active else None,
                last_poll_at=self._last_poll_at,
            )

    def _polling_loop(self, config_loader: Callable[[], SiteConfig]) -> None:
        next_due: dict[str, float] = {}
        while not self._polling_stop.is_set():
            config = config_loader()
            now = monotonic()
            devices = [
                device for device in config.devices
                if device.enabled
            ]
            active_names = {device.name for device in devices}
            next_due = {name: due for name, due in next_due.items() if name in active_names}
            for device in devices:
                due = next_due.setdefault(device.name, now)
                if due > now:
                    continue
                self.check(config, device.name)
                with self._lock:
                    self._last_poll_at = datetime.now(timezone.utc)
                poll_interval_ms = device.scan_rate_ms or DEFAULT_POLL_INTERVAL_MS
                next_due[device.name] = monotonic() + poll_interval_ms / 1000
                if self._polling_stop.wait(device.delay_between_polls_ms / 1000):
                    return

            wait_seconds = min(
                (max(0, due - monotonic()) for due in next_due.values()),
                default=1.0,
            )
            self._polling_stop.wait(min(wait_seconds, 1.0))

    def shutdown(self) -> None:
        self.stop_polling()
        self.executor.shutdown(wait=True, cancel_futures=True)
