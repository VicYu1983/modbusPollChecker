# 設備檢查介面與檢查流程重構規格

## 1. 目的

目前產品有三個主頁籤：

1. `連線狀況`：設備設定、即時 Modbus 檢查與自動輪詢。
2. `網路健檢`：Ping、TCP Port、網路批次與歷史。
3. `回歸測試`：Modbus 批次、基準與比較。

前兩個頁籤都以設備為主體，重複顯示設備名稱、IP、狀態、搜尋及單台操作，造成工作流程分散。本重構將主畫面調整為：

```text
設備檢查 | 回歸測試
```

設備是否執行 Ping、TCP 或 Modbus，不再由畫面上的全域模式暫時決定，而是由每台設備保存的「預設檢查流程」決定。這可避免非 Modbus 設備被錯誤送入 Modbus 流程。

本文件是後續實作的工程規格。完成前不得只在前端新增下拉選單而未調整後端流程選擇、驗證與批次分流。

## 2. 決策摘要

| 項目 | 決策 |
| --- | --- |
| 主頁籤 | 僅保留 `設備檢查`、`回歸測試`。 |
| 流程設定位置 | 設備新增/編輯面板中的「預設檢查流程」。 |
| 批次行為 | 批次依每台設備保存的流程執行；不使用全域覆蓋模式。 |
| 非 Modbus 設備 | 可使用 Ping 或 Ping + TCP，絕不呼叫 Modbus adapter。 |
| Modbus 回歸測試 | 僅納入 `full_stack` 設備。 |
| 網路健檢歷史 | 仍獨立保存於 `network_batches`、`network_results`。 |
| Modbus 歷史 | 仍保存於既有 `check_batches`、`check_records`。 |
| 舊設備相容 | 缺少新欄位的舊 JSON 預設為 `full_stack`。 |

## 3. 名詞

| 名詞 | 定義 |
| --- | --- |
| 檢查流程 / Profile | 一台設備預設執行的檢查階層。 |
| `ping` | 僅執行 ICMP Ping。 |
| `ping_tcp` | 執行 Ping 與單一 TCP Port 建立連線。 |
| `full_stack` | 執行 Ping、TCP Port 與 Modbus 讀取。 |
| 設備檢查 | 針對目前案場設備執行其預設流程的即時或批次測試。 |
| 回歸測試 | 僅針對 Modbus `full_stack` 設備建立基準、比較與 Modbus 報告。 |

`NetworkMode` 既有值為 `network_only`、`network_and_port`、`full_stack`。本重構的 UI 與設備設定使用較清楚的 profile 名稱；API 可先維持既有值，並以轉換層處理：

| `check_profile` | 執行 API 時對應 `NetworkMode` |
| --- | --- |
| `ping` | `network_only` |
| `ping_tcp` | `network_and_port` |
| `full_stack` | `full_stack` |

## 4. 資料模型

### 4.1 新增欄位

`DeviceConfig` 新增以下欄位：

```json
{
  "check_profile": "full_stack"
}
```

允許值：

```text
ping | ping_tcp | full_stack
```

後端使用 `Literal` 驗證；前端不得以自由輸入字串實作。

### 4.2 預設與相容性

| 情境 | 行為 |
| --- | --- |
| 舊 JSON 缺少 `check_profile` | 載入為 `full_stack`。 |
| 新增設備 | 表單預設 `full_stack`。 |
| 使用者改為 Ping 或 Ping + TCP | 不刪除已存在的 Modbus 設定；只是不執行它。 |
| 使用者改回完整檢查 | 沿用先前保存的 Modbus 設定。 |
| 匯入 JSON | 欄位缺失採預設；非法 profile 使整批匯入失敗，不能部分套用。 |

`enabled` 是設備唯一的總開關：設備啟用即納入設備檢查。`network_check_enabled` 已移除，舊 JSON 若仍含此欄位會被忽略，不影響載入。

### 4.3 設備欄位規則

| 欄位群組 | `ping` | `ping_tcp` | `full_stack` |
| --- | --- | --- | --- |
| 名稱、IPv4、啟用狀態 | 必填 | 必填 | 必填 |
| Ping 設定 | 可設定 | 可設定 | 可設定 |
| TCP Port、TCP timeout | 不需顯示；可保留值 | 必填 | 必填 |
| Modbus Port | 不需顯示；可保留值 | 不需顯示；可保留值 | 必填 |
| Unit ID、功能碼、位址、數量 | 不需顯示且不驗證 | 不需顯示且不驗證 | 必填且驗證 |
| Modbus connect/response timeout | 不需顯示且不驗證 | 不需顯示且不驗證 | 必填且驗證 |
| 自動 Modbus 輪詢 | 不支援 | 不支援 | 可設定 |

`ping_tcp` 必須明確使用 `tcp_port`。允許 `tcp_port` 在資料層暫時為 `null`，但保存或執行 `ping_tcp` 時必須驗證其存在；不得回退為 Modbus `port`，避免非 Modbus 設備被隱性套用 502。

`full_stack` 的 `tcp_port` 若為 `null`，可使用既有 Modbus `port` 作為 TCP 測試 Port。

## 5. 後端流程

### 5.1 Profile resolver

新增集中式 profile resolver，例如：

```text
resolve_check_profile(device) -> ExecutableCheckProfile
```

責任：

- 驗證設備是否啟用、是否啟用網路健檢。
- 根據 `check_profile` 產生對應的 `NetworkMode`。
- 驗證該 profile 所需欄位。
- 決定是否允許 Modbus adapter。
- 統一產出使用者可讀的 `CONFIG_ERROR`，而不是讓 adapter 讀取不適用的 Modbus 欄位。

不得將 profile 分流散落在 FastAPI route、`NetworkBatchService` 和 React 元件中。

### 5.2 單台設備檢查

統一使用一個設備檢查入口，概念上：

```text
POST /api/device-checks/{device_name}
```

或在保留既有 API 的過渡期內，由新 endpoint 呼叫既有 network adapter 與 Modbus checker。

行為：

1. 從案場設定取得設備；前端不得提交任意 IP。
2. resolver 驗證並取得 profile。
3. `ping`：只呼叫 network adapter 的 `network_only`。
4. `ping_tcp`：只呼叫 network adapter 的 `network_and_port`。
5. `full_stack`：呼叫 network adapter 的 `full_stack`；只有 TCP `OPEN` 時才呼叫 Modbus adapter。
6. 回傳統一的「設備檢查結果」視圖，包含 profile、網路層結果、選填 Modbus 結果、診斷和門檻違規。

非 `full_stack` profile 任何情況下不得執行 Modbus adapter，包括 TCP 成功時。

### 5.3 設備檢查批次

將目前網路批次改為「依設備 profile 批次」。批次 request 不再有全域 `mode`：

```json
{
  "site_name": "家泰家悅",
  "device_names": ["Switch-01", "PLC-01"],
  "max_concurrency": 20
}
```

執行器對每台設備：

1. 呼叫 resolver。
2. 執行該設備 profile。
3. 保存 profile 快照與統一結果。
4. 以 semaphore 控制總並行數。

建議新增 `device_check_batches` / `device_check_results`，取代語意已不精準的 `network_batches` / `network_results`。若 migration 風險高，第一階段可保留資料表名稱，但 response、欄位註解與新程式碼必須使用 `device_check` 名稱，並安排後續 migration。

批次結果必須能區分：

- `check_profile`
- Ping、TCP、Modbus 各層狀態
- 總狀態與第一失敗階段
- 診斷、建議、門檻違規

### 5.4 Modbus 回歸批次

既有 `/api/check/batches` 改為只選擇：

```text
enabled == true AND check_profile == full_stack
```

若沒有 `full_stack` 設備，回傳 422 並提示「目前案場沒有啟用完整 Modbus 檢查的設備」。

手動指定 `device_names` 時，任何非 `full_stack` 名稱都必須被拒絕，錯誤訊息列出名稱。不得靜默略過，否則使用者會以為它已完成回歸測試。

自動 Modbus polling 同樣只處理 `full_stack` 設備。

### 5.5 歷史與報告

| 功能 | 設備檢查 | 回歸測試 |
| --- | --- | --- |
| 歷史 | 所有 profile | 僅 `full_stack` Modbus 批次 |
| CSV / HTML | 顯示 profile、網路階層、選填 Modbus、診斷、趨勢 | 既有 Modbus 比較結果 |
| 趨勢 | 同一設備且相同 profile 比較 | 既有基準比較 |
| 基準 | 不設定 Modbus 基準 | 可設定、清除、比較 |

趨勢查詢不得將 Ping-only 結果和完整檢查結果混在同一基準樣本中。

## 6. 前端資訊架構

### 6.1 頁籤

主頁籤固定為：

```text
設備檢查 | 回歸測試
```

移除獨立的 `連線狀況`、`網路健檢` 頁籤，不再讓使用者在兩個列表中查找同一設備。

### 6.2 設備檢查頁

頁面分為五個區域：

1. 摘要：已納入設備、完全通過、需注意、最近批次完成數。
2. 設備檢查操作列：開始設備檢查、最大並行數、進行中進度與取消。
3. 單一設備列表：唯一的設備主表。
4. 歷史趨勢：選取完成批次後顯示趨勢摘要與每台設備差異。
5. 批次歷史：設備檢查歷史、查看結果、CSV/HTML 下載。

設備主表共用搜尋、狀態篩選和排序，建議欄位：

| 欄位 | 顯示規則 |
| --- | --- |
| 設備 | 名稱、IP。 |
| 檢查流程 | Ping、Ping + TCP、完整檢查。 |
| Ping | 有執行時顯示狀態、平均延遲與遺失率。 |
| TCP | profile 非 Ping 時顯示 Port、狀態與連線耗時。 |
| Modbus | 僅完整檢查顯示狀態；其他顯示「不適用」。 |
| 總狀態 | PASS、PARTIAL、FAIL、TIMEOUT、CONFIG_ERROR。 |
| 診斷 | 摘要、門檻違規與 tooltip 建議。 |
| 操作 | 重測單台、編輯設備。 |

不要在此頁額外放另一張「Modbus 連線狀態」或「網路結果」表格。

### 6.3 新增 / 編輯設備面板

表單頂部新增：

```text
預設檢查流程
[ Ping | Ping + TCP | 完整檢查 ]
```

使用 segmented control 或 radio group，不使用普通文字輸入。選項須有清楚標籤：

| 值 | UI 標籤 | 簡短說明 |
| --- | --- | --- |
| `ping` | Ping | 僅確認 IP 是否可達。 |
| `ping_tcp` | Ping + TCP | 確認 IP 與指定服務 Port。 |
| `full_stack` | 完整檢查 | 確認 Ping、TCP 與 Modbus 資料讀取。 |

表單依 profile 顯示欄位群組，不適用群組應折疊或隱藏，不能只是 disabled 後仍佔滿面板：

```text
共用設定：名稱、IP、流程、啟用、Ping 參數、品質門檻
TCP 設定：僅 Ping + TCP / 完整檢查
Modbus 設定：僅完整檢查
輪詢設定：僅完整檢查
```

profile 切換時：

- 保留已輸入的隱藏欄位值。
- 即時清除已不適用欄位的前端驗證錯誤。
- 保存時由後端做最終驗證。
- 切回完整檢查後恢復先前 Modbus 值。

### 6.4 回歸測試頁

保留既有基準、比較、報告與歷史功能，但文字必須明確指出：

```text
回歸測試僅包含預設檢查流程為「完整檢查」的設備。
```

摘要顯示 eligible device count；無 eligible device 時停用開始按鈕並顯示原因。

## 7. API 遷移

### 7.1 新 API 目標

| API | 用途 |
| --- | --- |
| `POST /api/device-checks/{device_name}` | 依設備 profile 檢查單台。 |
| `POST /api/device-checks/batches` | 依設備 profile 建立批次。 |
| `GET /api/device-checks/batches` | 取得設備檢查歷史。 |
| `GET /api/device-checks/batches/{id}` | 取得批次與設備結果。 |
| `POST /api/device-checks/batches/{id}/cancel` | 取消進行中批次。 |
| `GET /api/device-checks/batches/{id}/trend` | 取得相同 profile 的趨勢。 |
| `GET /api/device-checks/batches/{id}/report?format=csv|html` | 下載設備檢查報告。 |

### 7.2 過渡與移除

第一階段可保留下列舊 API 以相容既有前端或腳本：

- `POST /api/network/check/one`
- `POST /api/network/check`
- `/api/network/batches/*`

但舊 API 必須標註 deprecated，內部轉呼叫新的 device-check service；不得維護兩份行為不同的 orchestration。

待前端切換與至少一個版本的相容期結束後，再移除舊 `/api/network/*` 路由及對應 client methods。

## 8. 遷移步驟

1. 在 schema、前端型別、device defaults 與 JSON migration 加入 `check_profile`，預設 `full_stack`。
2. 建立 profile resolver 與單元測試。
3. 讓單台及設備檢查批次依 profile 分流；驗證非完整設備不呼叫 Modbus adapter。
4. 限制 Modbus polling 與回歸批次只處理完整檢查設備。
5. 建立或遷移設備檢查歷史資料模型，保存 profile snapshot。
6. 前端先新增 profile 表單欄位與條件欄位群組。
7. 合併「連線狀況」與「網路健檢」為「設備檢查」，改用唯一設備表。
8. 調整回歸測試的 eligible-device 提示與空狀態。
9. 切換 API client 至新 device-check routes；確認報告與趨勢連結。
10. 移除已不用的重複元件、全域網路模式選單與 deprecated API。

每一步都必須可獨立測試及回退。資料表實際更名應安排在 schema/API 行為穩定後，避免把 UI 重構和大量歷史 migration 綁在同一次發布。

## 9. 測試策略

### 9.1 後端

- 舊 JSON 沒有 `check_profile` 時預設為 `full_stack`。
- 非法 profile 不能保存或匯入。
- `ping` 設備只啟動 Ping，不建立 TCP 或 Modbus client。
- `ping_tcp` 設備建立 TCP，但絕不呼叫 Modbus adapter。
- `full_stack` 只有 TCP `OPEN` 才呼叫 Modbus adapter。
- `ping_tcp` 缺少 `tcp_port` 回傳 `CONFIG_ERROR`。
- Modbus 回歸批次不包含 Ping/Ping+TCP 設備。
- 手動指定非完整設備給 Modbus 回歸批次回傳 422 且列出設備名稱。
- 設備檢查批次的 profile snapshot、取消、並行上限、歷史、報告與趨勢正確。
- 趨勢只比較同一 profile 的結果。

### 9.2 前端

- 頁籤只顯示「設備檢查」、「回歸測試」。
- 編輯器切換三種 profile 時，欄位群組與驗證正確。
- 選擇 Ping 或 Ping+TCP 時，表單不顯示 Modbus 必填錯誤。
- 設備檢查頁只有一份設備主表，能顯示所有 profile 的適用欄位。
- 單台重測遵循設備 profile，不提供全域覆蓋模式。
- 回歸頁顯示完整檢查設備數量與空狀態。
- lint、production build 通過。

### 9.3 現場驗收

至少準備：

1. 一台僅允許 Ping 的主機。
2. 一台 HTTP、BACnet 或其他非 Modbus TCP 服務，使用 Ping + TCP 並指定非 502 Port。
3. 一台正常 Modbus TCP 設備，使用完整檢查。
4. 一台封鎖 ICMP 但 TCP 正常的設備。
5. 一台 TCP Port 不開啟的設備。
6. 一台 TCP 正常但 Unit ID/位址錯誤的 Modbus 設備。

驗收重點：非 Modbus 設備沒有任何 Modbus 請求；完整檢查設備仍可完成既有回歸比較；同一設備表能清楚區分「不適用」與「測試失敗」。

## 10. 非目標

- 不將非 Modbus 協定做深度應用層解析。
- 不做任意 IP/網段掃描。
- 不把網路健檢結果與 Modbus 基準批次混成同一種比較基準。
- 不在本重構加入設備群組、排程告警或雲端同步。
- 不進行手機專版設計；維持現有基本響應式行為即可。