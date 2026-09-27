from __future__ import annotations

from dataclasses import dataclass

from ..schemas import CheckProfile, DeviceConfig, NetworkMode


class CheckProfileConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ExecutableCheckProfile:
    name: CheckProfile
    network_mode: NetworkMode
    allows_modbus: bool
    tcp_port: int | None


def resolve_check_profile(device: DeviceConfig) -> ExecutableCheckProfile:
    if not device.enabled:
        raise CheckProfileConfigError("設備未啟用。")
    if not device.network_check_enabled:
        raise CheckProfileConfigError("設備未啟用設備檢查。")

    if device.check_profile == "ping":
        return ExecutableCheckProfile("ping", "network_only", False, None)
    if device.check_profile == "ping_tcp":
        if device.tcp_port is None:
            raise CheckProfileConfigError("Ping + TCP 設備必須設定 TCP Port。")
        return ExecutableCheckProfile("ping_tcp", "network_and_port", False, device.tcp_port)
    return ExecutableCheckProfile("full_stack", "full_stack", True, device.tcp_port or device.port)