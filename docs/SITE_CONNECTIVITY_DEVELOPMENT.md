# 案場連線健檢工具工程開發文件

## 1. 目的

在現有 Modbus Poll Checker 基礎上，將工具擴充為案場設備連線健檢平台。新功能以網路可達性測試為核心，先確認設備在網路上是否可溝通，再依需求繼續檢查 TCP 服務與 Modbus 協定。

主要目標如下：

- 快速檢查案場中大多數裝置是否可透過 IP 正常溝通。
- 區分網路、TCP Port 與 Modbus 協定問題。
- 對大量設備提供可控的並行測試。
- 保存歷史測試結果，便於追蹤間歇性斷線。
- 提供現場工程師可操作的結果、診斷與報告。

本文件為工程規格，不代表所有功能會在同一次交付完成。實作應依第 12 節里程碑分批進行。

## 2. 非目標

第一階段不做以下功能：

- 任意網段掃描或資產探索。
- 主動存取或嘗試登入非設定中的設備。
- SNMP、OPC UA、MQTT 或其他協定的深度解析。
- 交換器拓撲圖或網路拓撲自動發現。
- 對設備進行寫入、設定或控制操作。
- 長期監控平台、排程告警通知或雲端同步。
- 前端 router、頁面拆分或 bundle splitting。

若未來需求擴大到網路監控平台，再評估是否另開專案。

## 3. 名詞與定位

| 名詞 | 定義 |
| --- | --- |
| 網路健檢 | 針對設定中的 IP 執行 Ping、TCP Port 與必要時的 Modbus 檢查。 |
| ICMP | 用來判斷主機基本可達性與延遲的網路協定。 |
| TCP Port 測試 | 嘗試建立 TCP 連線，判斷指定服務 Port 是否可連。 |
| Modbus 測試 | 使用既有 Modbus TCP 流程讀取指定資料。 |
| 批次 | 一次針對多個設備執行健檢的完整執行紀錄。 |
| 結果階層 | 依序呈現網路、服務 Port、Modbus 協定與資料合理性。 |

產品定位可調整為：

```text
Site Connectivity Checker：案場設備連線健檢工具
```

既有 Modbus 功能視為連線健檢中的協定層，不再作為整體產品唯一範圍。

## 4. 整體架構

```text
React + Ant Design
        │
        │ /api proxy
        ▼
FastAPI
        │
        ├── Site configuration store
        ├── Batch orchestration
        ├── Network adapter
        │   ├── ICMP ping
        │   └── TCP port
        ├── Modbus adapter
        ├── Comparison / diagnosis
        ├── SQLite history
        └── Report renderer
```

網路測試與 Modbus 測試使用不同的 adapter：

- `modbus_adapter.py`：只負責 Modbus 協定。
- `network_adapter.py`：負責 Ping 與 TCP Port。
- `check_service.py`：協調測試流程、錯誤分類與批次結果。

不要把 Ping 或 TCP 測試邏輯直接放入 `modbus_adapter.py`。

## 5. 測試分層模型

每台設備最多包含四個測試階段：

```text
L0 設定驗證
    ↓
L1 IP 可達性（ICMP Ping）
    ↓
L2 TCP Port 連線
    ↓
L3 Modbus 協定與資料合理性
```

### 5.1 L0 設定驗證

執行前驗證：

- 設備名稱不可為空。
- IP 必須是合法 IPv4；第一版不支援 IPv6。
- Port 範圍為 1～65535。
- Unit ID 範圍為 0～247。
- Modbus 位址、數量與功能碼必須合法。
- 逾時與輪詢設定必須大於或等於允許範圍。

設定失敗直接標記為 `CONFIG_ERROR`，不得進入後續網路或 Modbus 測試。

### 5.2 L1 IP 可達性

使用 ICMP Ping 測試每台設備 IP，記錄：

- 是否有回應。
- 回應時間。
- 多次測試成功率。
- 封包遺失率。
- 錯誤類型，例如 timeout、host unreachable、permission denied。

Ping 失敗不代表 Modbus 一定失敗；部分設備會停用 ICMP。因此預設策略如下：

- Ping 成功：繼續 L2。
- Ping 失敗：預設仍執行 L2，但結果須標註「Ping 未回應」。
- 若設備設定 `skip_when_ping_failed=true`，則停止並標記 `NETWORK_TIMEOUT`。

### 5.3 L2 TCP Port 測試

嘗試建立 TCP 連線到設備 IP 與指定 Port，記錄：

- 是否可建立連線。
- 建立連線耗時。
- 是否連線被拒絕。
- 是否網路不可達。
- 是否逾時。

TCP Port 可連線只代表服務 Port 可達，不代表 Modbus 協定正常。

### 5.4 L3 Modbus 協定與資料合理性

沿用現有 Modbus 流程，檢查：

- Modbus TCP 連線。
- Unit ID。
- 功能碼。
- 位址與讀取數量。
- Modbus Exception。
- 回應資料長度。
- 預期值或範圍。
- 資料縮放、單位與合理值。

## 6. 狀態與結果模型

### 6.1 設備總狀態

| 狀態 | 說明 |
| --- | --- |
| `PASS` | 指定測試層全部通過。 |
| `FAIL` | 測試失敗且非 timeout。 |
| `TIMEOUT` | 測試超過逾時。 |
| `CONFIG_ERROR` | 設定錯誤，未執行或無法完成。 |
| `PARTIAL` | Ping 未回應但 TCP Port 可連線，或指定測試模式中的部分階段完成且至少一個必要階段未通過。 |
| `UNKNOWN` | 尚未檢查。 |

### 6.2 階層狀態

| 階層 | 狀態範例 | 說明 |
| --- | --- | --- |
| Ping | `PASS`、`TIMEOUT`、`UNREACHABLE`、`NOT_SUPPORTED` | 主機是否回應。 |
| TCP | `OPEN`、`CLOSED`、`TIMEOUT`、`UNREACHABLE` | Port 是否可連。 |
| Modbus | `PASS`、`FAIL`、`TIMEOUT`、`CONFIG_ERROR` | 協定與資料是否通過。 |

### 6.3 網路測試結果欄位

每筆網路測試結果至少包含：

| 欄位 | 說明 |
| --- | --- |
| `device_name` | 設備名稱。 |
| `target_ip` | 測試 IP。 |
| `timestamp` | 測試開始時間。 |
| `mode` | `network_only`、`network_and_port`、`full_stack`。 |
| `ping_attempts` | Ping 次數。 |
| `ping_success_count` | Ping 成功次數。 |
| `ping_loss_percent` | 封包遺失率。 |
| `ping_min_ms` | 最小延遲。 |
| `ping_avg_ms` | 平均延遲。 |
| `ping_max_ms` | 最大延遲。 |
| `tcp_port` | 測試 Port。 |
| `tcp_connect_ms` | TCP 連線耗時。 |
| `tcp_state` | `OPEN`、`CLOSED`、`TIMEOUT`、`UNREACHABLE`。 |
| `overall_status` | 總狀態。 |
| `failure_stage` | 第一個失敗階段。 |
| `error_type` | 錯誤分類。 |
| `error_message` | 對使用者可讀的錯誤訊息。 |

### 6.4 診斷摘要

結果應提供可讀的診斷摘要，例如：

- Ping 成功、TCP 502 開啟、Modbus 失敗：可能是 Unit ID、功能碼或位址設定錯誤。
- Ping 失敗、TCP 失敗：可能是設備離線、網路中斷或路由異常。
- Ping 失敗但 TCP 成功：設備可能停用 ICMP，通訊仍正常。
- Ping 成功但 TCP 失敗：可能是服務未啟動、Port 錯誤或防火牆阻擋。
- TCP 連線慢但成功：可能是網路品質不穩定或設備回應負載過高。

## 7. 設備設定擴充

既有設備設定保持向後相容。新增選填欄位：

| 欄位 | 型別 | 預設 | 說明 |
| --- | --- | --- | --- |
| `network_check_enabled` | boolean | `true` | 是否納入網路健檢。 |
| `ping_enabled` | boolean | `true` | 是否執行 Ping。 |
| `ping_attempts` | integer | `4` | 每次健檢的 Ping 次數。 |
| `ping_timeout_ms` | integer | `1000` | 單次 Ping 逾時。 |
| `ping_interval_ms` | integer | `200` | Ping 之間的間隔。 |
| `tcp_check_enabled` | boolean | `true` | 是否執行 TCP Port 測試。 |
| `tcp_port` | integer | `502` | 測試 Port，預設沿用 Modbus port。 |
| `tcp_timeout_ms` | integer | `2000` | TCP 連線逾時。 |
| `skip_when_ping_failed` | boolean | `false` | Ping 失敗時是否略過後續測試。 |
| `max_latency_ms` | integer \| null | `null` | 選填的延遲上限。 |
| `max_loss_percent` | number \| null | `null` | 選填的封包遺失上限。 |

第一版每台設備僅設定一個主要 TCP Port，預設沿用 Modbus `port`；多 Port 測試待後續需求確認後再擴充。第一版不增加設備分組欄位，先以設備名稱搜尋與狀態篩選設備。

設備 JSON 新增欄位時：

- 舊檔案缺少新欄位時使用預設值。
- 不允許匯入時因新欄位缺失而失敗。
- 欄位驗證失敗時不得套用部分設備。

## 8. 測試模式

### 8.1 `network_only`

只執行 ICMP Ping。適合快速確認大量設備是否在線。

### 8.2 `network_and_port`

執行 Ping 與 TCP Port。適合區分網路問題與服務問題。

### 8.3 `full_stack`

執行 Ping、TCP Port 與 Modbus。適合完整檢查。

預設模式為 `network_and_port`，Modbus 測試維持獨立操作。這可避免大量使用者在只想確認網路時發出不必要的 Modbus 請求。

## 9. API 規格

### 9.1 執行網路健檢

```http
POST /api/network/check
```

Request：

```json
{
  "site_name": "家泰家悅",
  "device_names": ["PLC-01", "PLC-02"],
  "mode": "network_and_port"
}
```

`device_names` 省略時代表所有 `network_check_enabled=true` 的設備。

Response：

```json
{
  "batch_id": "01J2K4N6B8Q6G8A5P2A7H8D3B8"
}
```

### 9.2 取得單台即時網路測試

```http
POST /api/network/check/one
```

Request：

```json
{
  "device_name": "PLC-01",
  "mode": "network_and_port"
}
```

Response：

```json
{
  "device_name": "PLC-01",
  "target_ip": "192.168.0.50",
  "timestamp": "2026-09-26T10:00:00Z",
  "mode": "network_and_port",
  "ping_attempts": 4,
  "ping_success_count": 4,
  "ping_loss_percent": 0,
  "ping_min_ms": 1.2,
  "ping_avg_ms": 1.8,
  "ping_max_ms": 2.4,
  "tcp_port": 502,
  "tcp_connect_ms": 8.4,
  "tcp_state": "OPEN",
  "overall_status": "PASS",
  "failure_stage": null,
  "error_type": null,
  "error_message": null
}
```

### 9.3 歷史與報告

網路健檢與 Modbus 使用獨立的批次與結果歷史，避免兩種測試的結果欄位、比較語意互相混用。網路批次使用 `network_batches` 與 `network_results` 保存；網路健檢 API 使用獨立路由：

- `GET /api/network/batches`：分頁列出網路健檢批次。
- `GET /api/network/batches/{batch_id}`：回傳網路批次與詳細結果。
- `POST /api/network/batches/{batch_id}/cancel`：取消進行中的網路批次。
- `GET /api/network/batches/{batch_id}/report?format=csv`
- `GET /api/network/batches/{batch_id}/report?format=html`

Report 需包含網路測試欄位，不能只輸出 Modbus 結果。

## 10. 前端 UI 規格

### 10.1 頁籤

主畫面新增第三個頁籤：

```text
連線狀況 | 網路健檢 | 回歸測試
```

「連線狀況」維持既有 Modbus 管理與即時檢查。「網路健檢」專注於 Ping、TCP Port 與歷史結果。

### 10.2 網路健檢畫面

畫面至少包含：

- 執行模式選擇。
- 開始網路健檢按鈕。
- 最大並行數與逾時設定入口。
- 設備總數、在線數、異常數。
- 設備結果表格。
- 批次歷史與報告下載。

### 10.3 結果表格欄位

| 欄位 | 說明 |
| --- | --- |
| 設備 | 名稱與 IP。 |
| Ping | 成功/失敗與平均延遲。 |
| 封包遺失 | 百分比。 |
| TCP Port | Port 狀態與連線耗時。 |
| 失敗階段 | Ping、TCP、Modbus 或設定。 |
| 總狀態 | `PASS`、`FAIL`、`TIMEOUT`、`PARTIAL` 等。 |
| 診斷 | 主要錯誤與建議。 |
| 操作 | 單台測試、查看歷史。 |

### 10.4 診斷呈現

失敗項目應優先排序：

1. `CONFIG_ERROR`
2. `TIMEOUT`
3. `FAIL`
4. `PARTIAL`
5. `PASS`

診斷建議應簡短明確，避免顯示原始 exception stack。

## 11. 後端實作設計

### 11.1 目錄結構

建議調整為：

```text
backend/app/
├── main.py
├── schemas.py
├── check_service.py
├── network_service.py
├── network_adapter.py
├── modbus_adapter.py
├── site_store.py
├── diagnosis/
├── reports/
└── repositories/
```

若一次搬移檔案風險過高，可先新增 adapter 與 service，不改動既有目錄。

### 11.2 Network adapter

負責：

- 執行 Ping。
- 執行 TCP 連線測試。
- 控制單台設備的 timeout。
- 將 OS、socket 與 ping subprocess 錯誤轉換成統一錯誤模型。

Ping 實作建議：

- Windows 使用 `ping -n {attempts} -w {timeout_ms} {ip}`。
- 解析 Windows 中文/英文輸出時不要依賴完整句子，優先解析：
  - `time<1ms`、`time=1ms`、`時間<1ms` 等延遲格式。
  - `Lost = N`、`遺失 = N` 等統計格式。
  - `Destination host unreachable`、`目的主機無法連線` 等錯誤。
- 解析結果失敗時標記為 `UNKNOWN`，不得直接視為設備離線。
- 若作業系統不支援 ping subprocess，應回傳 `NOT_SUPPORTED`。

TCP 測試建議：

- 使用非阻塞 socket 或 `asyncio.open_connection`。
- 使用獨立 timeout，不受全域輪詢 interval 影響。
- 只測試連線建立，不傳送應用層資料。
- 測試完成後立即關閉連線。

### 11.3 Network service

負責：

- 讀取設備設定。
- 過濾 `enabled` 與 `network_check_enabled`。
- 套用測試模式。
- 限制最大並行數。
- 彙總每台設備的 Ping、TCP 與總狀態。
- 產生診斷摘要。
- 將結果交給批次與歷史層。

並行建議：

- 預設最大並行數 20。
- 允許設定上限，例如 50。
- 超過上限時使用 semaphore 控制。
- 不允許一次對所有設備建立無上限的 socket 或 subprocess。

### 11.4 批次歷史

沿用既有 SQLite repository 的交易與生命週期原則，但網路批次使用獨立資料表及 repository：

- 批次與結果交易式寫入。
- 進行中批次可取消。
- 服務重啟後可恢復狀態。
- 基準批次與進行中批次不可刪除。
- 刪除批次時同時刪除相關結果。

網路結果保存於 `network_results`，不得塞入既有 Modbus `CheckRecord` 欄位，以維持各結果模型的型別與語意清楚。

## 12. 里程碑

### M1：網路 adapter 與單台測試

交付項目：

- `network_adapter.py`
- Ping 與 TCP Port 測試
- 統一錯誤模型
- 單台 API
- 單元測試

驗收條件：

- 可在 Windows 測試單一 IP。
- Ping 與 TCP 失敗可分開呈現。
- 錯誤不會讓 backend crash。
- Ping subprocess 不會殘留。

### M2：批次網路健檢

交付項目：

- 多台設備並行測試。
- 最大並行數控制。
- 批次狀態與進度。
- 取消批次。
- 歷史保存。

驗收條件：

- 200 台設備測試不會造成系統資源耗盡。
- 批次可取消並正確停止後續設備。
- 歷史頁可查詢完整結果。

### M3：前端網路健檢頁籤

交付項目：

- 新頁籤。
- 測試模式與結果表格。
- 單台重測。
- 批次歷史與報告入口。

驗收條件：

- 表格大量資料時仍可操作。
- 異常設備可快速篩選。
- 畫面不混雜 Modbus 位址設定。

### M4：診斷與報告

交付項目：

- 網路診斷摘要。
- CSV 與 HTML 網路欄位。
- 間歇性斷線趨勢摘要。
- 延遲與封包遺失門檻。

驗收條件：

- 報告可追蹤測試時間、設備、狀態與錯誤階段。
- Ping 失敗但 TCP 成功的案例可正確標示。
- 歷史比較可發現延遲變高與封包遺失變差。

### M5：長時間穩定性測試

交付項目：

- 指定次數或期間的重複測試。
- 成功率統計。
- 離線事件記錄。
- 服務重啟復原驗證。

驗收條件：

- 連續執行不會造成記憶體或資料庫持續異常成長。
- 歷史查詢分頁正常。
- 服務重啟後正在執行與已完成的批次狀態正確。

## 13. 測試策略

### 13.1 Backend 單元測試

覆蓋：

- Ping 輸出解析。
- Ping timeout、unreachable、permission denied。
- TCP open、closed、timeout、unreachable。
- 設定驗證。
- 並行上限。
- 批次取消。
- 歷史保存與刪除。
- 診斷分類。

### 13.2 API 測試

覆蓋：

- 單台網路測試。
- 批次網路健檢。
- 不存在設備。
- 非法 IP、Port、timeout。
- 批次取消。
- 歷史查詢與報告下載。

### 13.3 Frontend 驗證

- 新頁籤渲染。
- 測試模式選擇。
- 結果表格與錯誤提示。
- 批次進度輪詢。
- 大量設備分頁。
- lint 與 production build。

### 13.4 現場驗收測試

至少驗證：

- 一台正常設備。
- 一台離線設備。
- 一台封鎖 Ping 但 TCP 正常的設備。
- 一台 IP 錯誤設備。
- 一台 Port 錯誤設備。
- 多台設備同時測試。
- 網路切斷與恢復。
- 服務重啟後歷史仍完整。

## 14. 效能與安全限制

- 只允許測試案場設定中明確登錄的 IP。
- 不接受前端輸入任意 IP 進行網段掃描。
- Ping 與 TCP 測試必須有逾時。
- 子程序必須在取消或逾時時被清理。
- 並行數必須可設定且有上限。
- 歷史資料需分頁查詢。
- 不在報告或 log 中保存敏感資訊。
- 錯誤訊息應轉換為可讀內容，不直接暴露系統路徑或 stack trace。

## 15. 資料保留與容量

第一版預設保留最近 90 天且最多 200 個批次，以先達到的條件為準。自動清理時不得刪除進行中的批次或目前被指定為基準的批次。保留期限與批次上限集中設定，不寫死於 UI。

資料查詢與清理策略：

- 批次列表分頁。
- 單一批次結果可依設備名稱或狀態查詢。
- 定期清理符合保留條件的舊批次及其結果。
- 清理失敗需記錄可診斷的 backend log，不能中斷新批次執行。
- 提供手動刪除批次與清除基準。

長期趨勢分析可在 M5 之後再評估是否增加 daily rollup 或獨立 metrics 表。

## 16. 相容性

- 既有 Modbus 設定、API、歷史與基準比較不可破壞。
- 新欄位需有預設值。
- 舊案場 JSON 匯入後仍可使用。
- 既有 `連線狀況` 與 `回歸測試` 頁籤行為不變。
- 新增網路健檢不得影響既有自動輪詢功能。

## 17. 第一版決策

以下決策作為第一版實作依據；若現場需求改變，應更新本節及其相依資料/API 規格：

1. **ICMP Ping 不保證可用。** 設備可能停用或封鎖 ICMP；Ping 失敗不直接判定設備離線，預設仍繼續 TCP Port 測試，並明確呈現 Ping 未回應。
2. **第一版僅支援 IPv4。** IPv6 設定視為不支援，不發起網路測試；API 回傳可辨識的 `CONFIG_ERROR`，錯誤訊息指出第一版僅接受 IPv4。
3. **Ping 失敗但 TCP Port 成功時，總狀態為 `PARTIAL`。** 診斷說明「設備可能停用 ICMP，TCP 通訊正常」。若 Ping 失敗且 TCP 也失敗，依 TCP 結果標記 `TIMEOUT` 或 `FAIL`。
4. **網路健檢與 Modbus 歷史分開保存。** 網路測試使用 `network_batches` 與 `network_results`；不與既有 Modbus 基準批次混用。
5. **第一版每台設備只測一個 TCP Port。** 預設沿用設備的 Modbus `port`，必要時可透過 `tcp_port` 指定不同的單一 Port；多 Port 掃描不在第一版範圍。
6. **第一版不加入設備分組欄位。** 先提供設備名稱搜尋與狀態篩選；樓層、系統或設備類型分類待需求明確後再設計。
7. **網路健檢歷史保留最近 90 天且最多 200 個批次，以先達到者為準。** 進行中的批次與指定為基準的批次不得自動清除；清除策略需可設定並留下執行紀錄。

## 18. 後續評估項目

- IPv6 支援。
- 多 TCP Port 與設備分組。
- 是否需要將網路批次設為獨立網路基準，以比較延遲與封包遺失趨勢。
- 歷史保留策略是否需改為案場可設定。

## 19. 建議實作順序

1. 建立 `network_adapter.py` 與錯誤模型。
2. 完成單台 Ping/TCP API 與單元測試。
3. 建立批次 service 與並行控制。
4. 保存網路測試歷史。
5. 新增前端「網路健檢」頁籤。
6. 擴充報告與診斷。
7. 進行現場驗收與長時間穩定性測試。

此順序可讓每個階段都有可測試成果，並避免一次把網路、批次、歷史與 UI 全部混合修改。
