"""Diagnoses describe possible causes and checks, never assert a root cause."""

from ..schemas import CheckResult
from .models import ComparisonStatus, Diagnosis


_DIAGNOSES = {
    "CONNECTION_FAILED": Diagnosis(
        category="NETWORK",
        summary="無法建立設備 TCP 連線，可能與網路路徑或設備連線狀態有關。",
        suggestions=[
            "確認設備電源與網路指示燈",
            "檢查網路線與交換器 Port",
            "確認設備 IP 與本機網段設定",
            "確認防火牆未阻擋連線",
        ],
    ),
    "TIMEOUT": Diagnosis(
        category="MODBUS_TIMEOUT",
        summary="設備未在逾時期限內回應，可能與 Unit ID、設備負載或網路品質有關。",
        suggestions=[
            "確認 Unit ID 是否正確",
            "確認設備目前沒有忙碌或重啟",
            "檢查網路品質與延遲",
            "確認設備支援所設定的功能碼",
        ],
    ),
    "MODBUS_EXCEPTION": Diagnosis(
        category="MODBUS_EXCEPTION",
        summary="設備回覆 Modbus Exception，可能是功能碼或位址不受支援。",
        suggestions=[
            "確認設備支援所設定的功能碼",
            "確認讀取位址落在設備支援範圍",
            "確認讀取數量未超過設備限制",
        ],
    ),
    "UNEXPECTED_VALUE": Diagnosis(
        category="DATA_MISMATCH",
        summary="設備有回應，但資料與預期值不一致。",
        suggestions=[
            "確認 PLC 位址採 0 起算或 1 起算",
            "確認資料格式與讀取數量",
            "確認預期值設定與設備目前狀態",
        ],
    ),
    "LATENCY_DEGRADED": Diagnosis(
        category="LATENCY",
        summary="設備回應時間較基準增加，單次變慢不代表線路故障。",
        suggestions=[
            "檢查輪詢頻率與同時通訊負載",
            "檢查網路交換器負載與連線品質",
            "觀察設備負載及後續回應時間",
        ],
    ),
    "CONFIG_ERROR": Diagnosis(
        category="CONFIG",
        summary="設備設定未能通過檢查。",
        suggestions=[
            "確認設備設定欄位與數值範圍",
            "確認案場設定檔格式與版本",
            "確認匯入的設備資料完整",
        ],
    ),
    "CHECK_ERROR": Diagnosis(
        category="CONFIG",
        summary="檢查程序發生未預期錯誤，尚無法判定原因。",
        suggestions=[
            "確認設備設定欄位",
            "重新執行單台檢查以確認是否重現",
            "查看後端記錄中的錯誤訊息",
        ],
    ),
    "MODBUS_ERROR": Diagnosis(
        category="NETWORK",
        summary="通訊過程發生錯誤，可能與網路或設備狀態有關。",
        suggestions=[
            "確認設備仍可從本機連線",
            "檢查網路品質與交換器連線",
            "確認設備未處於重啟或忙碌狀態",
        ],
    ),
    "VALUE_CHANGED": Diagnosis(
        category="DATA_MISMATCH",
        summary="通訊成功，但回傳值與基準不同；請先確認這是否為預期的現場變更。",
        suggestions=[
            "確認設備目前運轉狀態是否與建立基準時不同",
            "確認 PLC 位址及資料格式",
            "確認此次現場調整是否預期改變此值",
        ],
    ),
    "LATENCY_DEGRADED": Diagnosis(
        category="LATENCY",
        summary="通訊仍成功，但回應時間較基準增加；單次變慢不代表線路故障。",
        suggestions=[
            "檢查輪詢頻率與同時通訊負載",
            "檢查網路交換器負載與連線品質",
            "觀察後續回應時間是否持續偏高",
        ],
    ),
    "CONFIG_CHANGED": Diagnosis(
        category="CONFIG",
        summary="設備通訊設定與基準不同，請確認是否為本次預期調整。",
        suggestions=[
            "比對 IP、Port 與 Unit ID",
            "比對功能碼、讀取位址與數量",
            "確認基準批次是否應更新",
        ],
    ),
}


def diagnose(
    result: CheckResult,
    comparison_status: ComparisonStatus | None = None,
) -> Diagnosis | None:
    if comparison_status in {"VALUE_CHANGED", "LATENCY_DEGRADED", "CONFIG_CHANGED"}:
        return _DIAGNOSES[comparison_status]
    if result.status == "PASS":
        return None
    if result.status == "CONFIG_ERROR":
        return _DIAGNOSES["CONFIG_ERROR"]
    return _DIAGNOSES.get(result.error_type or "CHECK_ERROR")