from __future__ import annotations

import asyncio
import errno
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic

from .schemas import DeviceConfig, NetworkCheckResult, NetworkMode


@dataclass(frozen=True)
class PingProbeResult:
    state: str
    success_count: int
    latencies_ms: tuple[float, ...] = ()
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class TcpProbeResult:
    state: str
    elapsed_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None


class NetworkAdapter:
    async def check_device(
        self,
        device: DeviceConfig,
        mode: NetworkMode = "network_and_port",
    ) -> NetworkCheckResult:
        started_at = datetime.now(timezone.utc)
        target_ip = str(device.ip)
        tcp_port = device.tcp_port or device.port

        if device.ip.version != 4:
            return NetworkCheckResult(
                device_name=device.name,
                target_ip=device.ip,
                timestamp=started_at,
                mode=mode,
                ping_state="UNKNOWN",
                ping_attempts=0,
                ping_success_count=0,
                tcp_port=tcp_port if mode != "network_only" else None,
                tcp_state="NOT_TESTED",
                overall_status="CONFIG_ERROR",
                failure_stage="CONFIG",
                error_type="ipv4_required",
                error_message="第一版僅支援 IPv4，未執行網路測試。",
            )

        if not device.network_check_enabled:
            return self._config_error(device, mode, started_at, "network_check_disabled", "此設備未啟用網路健檢。")

        ping = await self._ping_device(device) if device.ping_enabled else PingProbeResult(
            state="NOT_SUPPORTED", success_count=0, error_type="ping_disabled", error_message="Ping 未啟用。"
        )
        tcp = TcpProbeResult(state="NOT_TESTED")
        should_test_tcp = mode != "network_only" and device.tcp_check_enabled

        if should_test_tcp and not (device.skip_when_ping_failed and ping.state != "PASS"):
            tcp = await self._test_tcp(target_ip, tcp_port, device.tcp_timeout_ms)
        elif should_test_tcp and device.skip_when_ping_failed:
            tcp = TcpProbeResult(state="NOT_TESTED", error_type="skipped_after_ping_failure")

        overall_status, failure_stage, error_type, error_message = self._summarize(
            mode, ping, tcp, should_test_tcp
        )
        latencies = ping.latencies_ms
        attempts = device.ping_attempts if device.ping_enabled else 0
        successful_pings = min(ping.success_count, attempts)
        return NetworkCheckResult(
            device_name=device.name,
            target_ip=device.ip,
            timestamp=started_at,
            mode=mode,
            ping_state=ping.state,
            ping_attempts=attempts,
            ping_success_count=successful_pings,
            ping_loss_percent=(100 * (attempts - successful_pings) / attempts) if attempts else None,
            ping_min_ms=min(latencies) if latencies else None,
            ping_avg_ms=sum(latencies) / len(latencies) if latencies else None,
            ping_max_ms=max(latencies) if latencies else None,
            tcp_port=tcp_port if should_test_tcp else None,
            tcp_connect_ms=tcp.elapsed_ms,
            tcp_state=tcp.state,
            overall_status=overall_status,
            failure_stage=failure_stage,
            error_type=error_type or tcp.error_type or ping.error_type,
            error_message=error_message or tcp.error_message or ping.error_message,
        )

    async def _ping_device(self, device: DeviceConfig) -> PingProbeResult:
        latencies: list[float] = []
        saw_unreachable = False
        saw_unknown_output = False
        for attempt in range(device.ping_attempts):
            try:
                process = await asyncio.create_subprocess_exec(
                    "ping",
                    *(self._ping_arguments(str(device.ip), device.ping_timeout_ms)),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), timeout=device.ping_timeout_ms / 1000 + 2
                    )
                except TimeoutError:
                    self._kill_ping_process(process)
                    await process.communicate()
                    return PingProbeResult(
                        "TIMEOUT", len(latencies), tuple(latencies), "ping_timeout", "Ping 測試逾時。"
                    )
                except asyncio.CancelledError:
                    self._kill_ping_process(process)
                    await process.communicate()
                    raise
            except FileNotFoundError:
                return PingProbeResult(
                    "NOT_SUPPORTED", len(latencies), tuple(latencies), "ping_not_supported", "系統找不到 ping 指令。"
                )
            except PermissionError:
                return PingProbeResult(
                    "UNKNOWN", len(latencies), tuple(latencies), "permission_denied", "目前權限無法執行 Ping。"
                )
            except NotImplementedError:
                return PingProbeResult(
                    "NOT_SUPPORTED", len(latencies), tuple(latencies), "ping_not_supported", "此系統不支援 Ping 子程序。"
                )
            except OSError:
                return PingProbeResult(
                    "UNKNOWN", len(latencies), tuple(latencies), "ping_error", "無法啟動 Ping 測試。"
                )

            output = (stdout + b"\n" + stderr).decode(errors="replace")
            parsed = self._parse_ping_output(output)
            if parsed:
                latencies.extend(parsed)
            elif self._is_unreachable(output):
                saw_unreachable = True
            elif process.returncode == 0:
                saw_unknown_output = True

            if attempt + 1 < device.ping_attempts and device.ping_interval_ms:
                await asyncio.sleep(device.ping_interval_ms / 1000)

        if latencies:
            return PingProbeResult("PASS", len(latencies), tuple(latencies))
        if saw_unreachable:
            return PingProbeResult(
                "UNREACHABLE", 0, error_type="host_unreachable", error_message="目標主機或網路無法到達。"
            )
        if saw_unknown_output:
            return PingProbeResult(
                "UNKNOWN", 0, error_type="ping_parse_error", error_message="無法解析 Ping 回應。"
            )
        return PingProbeResult("TIMEOUT", 0, error_type="ping_timeout", error_message="Ping 未收到回應。")

    @staticmethod
    def _kill_ping_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass

    @staticmethod
    def _ping_arguments(target_ip: str, timeout_ms: int) -> tuple[str, ...]:
        if sys.platform == "win32":
            return ("-n", "1", "-w", str(timeout_ms), target_ip)
        return ("-c", "1", "-W", str(max(1, (timeout_ms + 999) // 1000)), target_ip)

    @staticmethod
    def _parse_ping_output(output: str) -> list[float]:
        matches = re.findall(
            r"(?:time|時間)\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*ms",
            output,
            flags=re.IGNORECASE,
        )
        return [float(value.replace(",", ".")) for value in matches]

    @staticmethod
    def _is_unreachable(output: str) -> bool:
        return bool(
            re.search(
                r"destination\s+(?:host|net(?:work)?)\s+unreachable|"
                r"目的(?:主機|地主機)(?:無法|不可)連線|一般性錯誤",
                output,
                flags=re.IGNORECASE,
            )
        )

    async def _test_tcp(self, host: str, port: int, timeout_ms: int) -> TcpProbeResult:
        started = monotonic()
        writer: asyncio.StreamWriter | None = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout_ms / 1000
            )
            return TcpProbeResult("OPEN", (monotonic() - started) * 1000)
        except TimeoutError:
            return TcpProbeResult("TIMEOUT", error_type="tcp_timeout", error_message="TCP 連線逾時。")
        except ConnectionRefusedError:
            return TcpProbeResult("CLOSED", error_type="connection_refused", error_message="TCP Port 拒絕連線。")
        except OSError as error:
            if error.errno in {errno.ENETUNREACH, errno.EHOSTUNREACH, 10051, 10065}:
                return TcpProbeResult(
                    "UNREACHABLE", error_type="network_unreachable", error_message="目標網路或主機無法到達。"
                )
            return TcpProbeResult("CLOSED", error_type="tcp_error", error_message="TCP Port 無法建立連線。")
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    @staticmethod
    def _summarize(
        mode: NetworkMode,
        ping: PingProbeResult,
        tcp: TcpProbeResult,
        should_test_tcp: bool,
    ) -> tuple[str, str | None, str | None, str | None]:
        if mode == "network_only" or not should_test_tcp:
            if ping.state == "PASS":
                return "PASS", None, None, None
            if ping.state == "TIMEOUT":
                return "TIMEOUT", "PING", ping.error_type, ping.error_message
            if ping.state == "UNREACHABLE":
                return "FAIL", "PING", ping.error_type, ping.error_message
            return "UNKNOWN", "PING", ping.error_type, ping.error_message

        if tcp.state == "NOT_TESTED" and tcp.error_type == "skipped_after_ping_failure":
            return "TIMEOUT", "PING", "network_timeout", "Ping 未通過，依設備設定略過後續測試。"

        if tcp.state == "OPEN":
            if ping.state == "PASS":
                return "PASS", None, None, None
            return (
                "PARTIAL",
                "PING",
                "ping_no_response",
                "Ping 未回應，但 TCP Port 可連線，設備可能停用 ICMP。",
            )
        if tcp.state == "TIMEOUT":
            return "TIMEOUT", "TCP", tcp.error_type, tcp.error_message
        if tcp.state in {"CLOSED", "UNREACHABLE"}:
            return "FAIL", "TCP", tcp.error_type, tcp.error_message
        if ping.state == "TIMEOUT":
            return "TIMEOUT", "PING", ping.error_type, ping.error_message
        return "UNKNOWN", "TCP", tcp.error_type or ping.error_type, tcp.error_message or ping.error_message

    @staticmethod
    def _config_error(
        device: DeviceConfig,
        mode: NetworkMode,
        timestamp: datetime,
        error_type: str,
        message: str,
    ) -> NetworkCheckResult:
        return NetworkCheckResult(
            device_name=device.name,
            target_ip=device.ip,
            timestamp=timestamp,
            mode=mode,
            ping_state="UNKNOWN",
            ping_attempts=0,
            ping_success_count=0,
            tcp_port=None,
            tcp_state="NOT_TESTED",
            overall_status="CONFIG_ERROR",
            failure_stage="CONFIG",
            error_type=error_type,
            error_message=message,
        )
