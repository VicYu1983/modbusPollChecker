from __future__ import annotations

from ..schemas import DeviceConfig, NetworkCheckResult


def diagnose_network(
    result: NetworkCheckResult,
    device: DeviceConfig,
) -> NetworkCheckResult:
    violations: list[str] = []
    if (
        device.max_latency_ms is not None
        and result.ping_avg_ms is not None
        and result.ping_avg_ms > device.max_latency_ms
    ):
        violations.append(
            f"Ping 平均延遲 {result.ping_avg_ms:.1f} ms 超過上限 {device.max_latency_ms} ms"
        )
    if (
        device.max_loss_percent is not None
        and result.ping_loss_percent is not None
        and result.ping_loss_percent > device.max_loss_percent
    ):
        violations.append(
            f"Ping 封包遺失 {result.ping_loss_percent:.1f}% 超過上限 {device.max_loss_percent:g}%"
        )

    if violations:
        violation_message = "；".join(violations)
        if result.overall_status == "PASS":
            result.overall_status = "FAIL"
            result.failure_stage = "PING"
            result.error_type = "network_quality_threshold"
            result.error_message = violation_message
        elif not result.error_message:
            result.error_message = violation_message
        elif not all(violation in result.error_message for violation in violations):
            result.error_message = f"{result.error_message}；{violation_message}"

    result.threshold_violations = violations
    if result.failure_stage == "CONFIG":
        result.diagnosis_summary = result.error_message or "設備網路設定無效，未執行測試。"
        result.diagnosis_suggestions = ["確認設備 IP 與網路健檢設定。"]
    elif result.failure_stage == "MODBUS":
        result.diagnosis_summary = "網路與 TCP 已通，但 Modbus 協定檢查未通過。"
        result.diagnosis_suggestions = [
            "確認 Unit ID、功能碼、暫存器位址與讀取數量。",
            "確認設備 Modbus TCP 服務設定。",
        ]
    elif violations:
        result.diagnosis_summary = "網路品質超過設備設定門檻。"
        result.diagnosis_suggestions = [
            "檢查設備網路連線與交換器 Port。",
            "確認現場網路負載、線路品質與設備回應狀況。",
        ]
    elif result.tcp_state == "OPEN" and result.ping_state != "PASS":
        result.diagnosis_summary = "Ping 未回應，但 TCP Port 可連線；設備可能停用 ICMP。"
        result.diagnosis_suggestions = [
            "確認設備或網路設備是否封鎖 ICMP；TCP 服務目前可連線。"
        ]
    elif result.failure_stage == "TCP" and result.ping_state == "PASS":
        result.diagnosis_summary = "Ping 成功，但指定 TCP Port 無法連線。"
        result.diagnosis_suggestions = [
            "確認服務是否啟動、Port 設定是否正確，以及防火牆規則。"
        ]
    elif result.failure_stage == "TCP":
        result.diagnosis_summary = "Ping 與 TCP 連線皆未通過。"
        result.diagnosis_suggestions = [
            "確認設備電源、IP 設定、網路路由與防火牆。"
        ]
    elif result.failure_stage == "PING":
        result.diagnosis_summary = "Ping 未收到回應。"
        result.diagnosis_suggestions = [
            "確認設備 IP 與網路連線；若設備封鎖 ICMP，改以 TCP 狀態判斷服務可達性。"
        ]
    elif result.overall_status == "PASS":
        result.diagnosis_summary = "指定網路測試階段均通過。"
        result.diagnosis_suggestions = []
    else:
        result.diagnosis_summary = result.error_message or "網路測試結果無法判定。"
        result.diagnosis_suggestions = ["檢查測試環境與設備網路設定後重新測試。"]
    return result
