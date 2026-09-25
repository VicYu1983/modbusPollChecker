# Modbus Poll Checker 初版開發文件

## 1. 文件目的

本文件根據 [DEVELOPMENT.md](DEVELOPMENT.md) 建立，用來指導第一版可執行的 Modbus Poll Checker。重點不是重複需求，而是將需求轉換成可以實作、測試、維護與日後擴充的開發架構。

第一版必須保留目前 Python Modbus TCP 檢查能力，並提供 React + TypeScript + Ant Design 操作介面。

## 2. 第一版目標

第一版需要完成：

1. 以案場 JSON 檔案管理 Modbus TCP 連線設定。
2. 支援多案場 JSON 設定檔匯入與匯出。
3. 顯示每台設備的連線狀態與最近檢查結果。
4. 支援新增、修改與刪除設備連線。
5. 支援單台設備檢查與全部設備檢查。
6. 支援功能碼 `01` Read Coils、`02` Read Discrete Inputs、`03` Read Holding Registers 與 `04` Read Input Registers。
7. 支援連線逾時、回應逾時、輪詢週期與輪詢延遲。
8. 保留命令列 CSV 檢查能力，避免破壞既有工作流程。

第一版不實作：

- Modbus 寫入功能。
- Modbus RTU over TCP。

## 3. 總體架構

```text
React + TypeScript + Ant Design
        | HTTP API
        v
Python API Server
        | 使用既有檢查邏輯
        v
Modbus TCP Adapter + pymodbus
        | Modbus TCP
        v
現場設備
```

原則：

- 前端不直接連線 Modbus TCP。
- 第一版以單機本地使用為前提，不建立使用者、登入或權限模型。
- 所有設定驗證以後端為準，前端驗證只負責改善使用體驗。
- Modbus 通訊細節集中在 Adapter，不允許 API 層直接操作 pymodbus。
- 設定檔格式與結果格式必須明確版本化，日後才能安全升級。

## 4. 建議目錄結構

```text
modbusPollChecker/
├── docs/
│   ├── DEVELOPMENT.md          # 需求與技術決策
│   └── INITIAL_DEVELOPMENT.md  # 本文件：初版實作規格
├── config/
│   └── devices.csv             # 既有 CSV 範例
├── backend/
│   ├── requirements.txt
│   ├── modbus_checker.py        # 既有命令列檢查程式
│   ├── app/
│       ├── main.py             # API 進入點
│       ├── schemas.py          # 設定與結果資料模型
│       ├── site_store.py       # 案場 JSON 儲存、匯入與匯出
│       ├── check_service.py    # 檢查流程與並行控制
│       └── modbus_adapter.py   # pymodbus 封裝
│   └── tests/
│       └── test_core.py         # 核心服務與 schema 測試
├── data/
│   └── site.json               # 本機案場設定（執行時建立）
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/client.ts       # API 呼叫封裝與型別
│   │   ├── App.css
│   │   └── index.css
│   └── vite.config.ts
```

## 5. 前端設計

### 5.1 技術選型

- React：管理頁面狀態與元件。
- TypeScript：固定 API、設定與檢查結果型別。
- Ant Design：表格、表單、通知、狀態標籤、匯入匯出與確認操作。
- Vite：前端開發與建置工具。

### 5.2 頁面區域

頁面維持兩個主要區域：

1. 連線狀態。
2. 新增或編輯連線。

#### 連線狀態

使用 Ant Design `Table` 顯示：

- 設備名稱。
- IP 與 Port。
- Unit ID。
- 功能碼。
- 協定位址與 PLC 顯示位址。
- 讀取數量。
- 狀態標籤：`正常`、`失敗`、`逾時`、`設定錯誤`、`未檢查`。
- 最近檢查時間。
- 最近一次值或錯誤訊息。
- 連線耗時。

提供操作：

- 檢查單台設備。
- 檢查全部設備。
- 修改連線。
- 刪除連線。
- 匯入案場 JSON。
- 匯出案場 JSON。

#### 新增連線

使用 Ant Design `Form`：

- 設備名稱：必填且不可重複。
- IP 位址：必填並驗證 IPv4 格式。
- Port：預設 `502`，範圍 `1..65535`。
- Unit ID：範圍 `0..247`。
- 功能碼：下拉選項 `01`、`02`、`03`、`04`。
- 協定位址：整數，不小於 `0`。
- PLC 位址：唯讀顯示，例如功能碼 `03` 且地址 `0` 時顯示 `40001`。
- 讀取數量：範圍 `1..125`。
- 預期值：可選，支援單值、逗號分隔或範圍。
- 位址模式：十進位或十六進位。
- 連線逾時：預設 `3000 ms`。
- 回應逾時：預設 `1000 ms`。
- 輪詢週期：預設 `0`，代表只檢查一次。
- 輪詢延遲：預設 `20 ms`。
- 啟用狀態。

### 5.3 前端狀態原則

- `siteConfig`：目前案場設定。
- `checkStatus`：每台設備最近狀態與結果。
- `formState`：新增或編輯表單。
- `isImporting` / `isChecking`：操作狀態。

不要在前端保存唯一事實；每次操作完成後從後端重新取得 `siteConfig`，避免前後端設定不同步。

## 6. 後端設計

### 6.1 技術選型

建議使用 FastAPI：

- 內建 JSON 輸入輸出。
- 支援 Pydantic 資料模型與驗證。
- 支援 OpenAPI 文件。
- 適合搭配 `pymodbus`。
- 容易在 Windows 本機執行。

### 6.2 後端分層

```text
API Layer
  | 驗證 HTTP 輸入、轉換錯誤、回傳 JSON
Service Layer
  | 管理案場設定、檢查流程、並行限制與輪詢
Adapter Layer
  | 封裝 pymodbus 連線與功能碼讀取
Store Layer
  | 儲存、匯入、匯出 JSON 與既有 CSV
```

各層職責必須清楚：

- API Layer 不直接呼叫 pymodbus。
- Store Layer 不發動網路連線。
- Adapter Layer 不修改設定檔。
- Service Layer 不處理 HTTP 例外細節。

## 7. 資料模型

### 7.1 Device

```json
{
    "name": "PLC-01",
    "ip": "192.168.0.50",
    "port": 502,
    "unit_id": 1,
    "address": 0,
    "quantity": 10,
    "function": "03",
    "expected": null,
    "address_mode": "dec",
    "connect_timeout_ms": 3000,
    "response_timeout_ms": 1000,
    "scan_rate_ms": 1000,
    "delay_between_polls_ms": 20,
    "enabled": true
}
```

驗證規則：

- `name` 必填且不可為空白。
- `ip` 必須是有效 IPv4。
- `port` 範圍 `1..65535`。
- `unit_id` 範圍 `0..247`。
- `function` 只允許 `01`、`02`、`03`、`04`。
- `quantity` 範圍 `1..2000`；`03`、`04` 暫存器讀取最多 `125` 筆。
- `address_mode` 只允許 `dec`、`hex`。
- 逾時與延遲不得為負值。
- `scan_rate_ms=0` 表示單次檢查。

### 7.2 SiteConfig

```json
{
    "schema_version": 1,
    "site_name": "案場 A",
    "devices": []
}
```

規則：

- `schema_version` 固定從 `1` 開始。
- 匯入時不支援的版本必須明確拒絕。
- 匯出時必須包含 `schema_version`。
- 匯出內容不包含即時狀態、錯誤訊息或最近讀取值。

### 7.3 CheckResult

```json
{
    "device_name": "PLC-01",
    "timestamp": "2026-09-25T10:30:00+08:00",
    "status": "PASS",
    "ip": "192.168.0.50",
    "port": 502,
    "unit_id": 1,
    "function": "03",
    "address": 0,
    "plc_address": 40001,
    "quantity": 10,
    "values": [0, 1, 2],
    "elapsed_ms": 35,
    "error_type": null,
    "error_message": null
}
```

狀態只允許：

- `PASS`
- `FAIL`
- `TIMEOUT`
- `CONFIG_ERROR`
- `UNKNOWN`

## 8. API 規格

| 方法 | 路徑 | 用途 | 回應 |
|---|---|---|---|
| `GET` | `/api/site` | 取得目前案場設定 | `SiteConfig` |
| `POST` | `/api/site/import` | 驗證並取代目前案場設定 | `SiteConfig` 或錯誤明細 |
| `GET` | `/api/site/export` | 匯出目前案場 JSON | JSON 檔案 |
| `POST` | `/api/devices` | 新增設備 | 更新後設備 |
| `PUT` | `/api/devices/{name}` | 修改設備 | 更新後設備 |
| `DELETE` | `/api/devices/{name}` | 刪除設備 | `204` |
| `POST` | `/api/check` | 檢查單台或全部設備 | 檢查結果陣列 |
| `GET` | `/api/status` | 取得每台設備最近狀態 | 狀態陣列 |
| `POST` | `/api/polling/start` | 啟動依設備週期的背景輪詢 | 輪詢狀態 |
| `POST` | `/api/polling/stop` | 停止背景輪詢 | 輪詢狀態 |
| `GET` | `/api/polling/status` | 取得背景輪詢狀態 | 輪詢狀態 |

錯誤回應格式：

```json
{
    "error": "validation_error",
    "message": "設定驗證失敗",
    "details": [
        {
            "field": "devices.0.ip",
            "message": "IP 位址格式錯誤"
        }
    ]
}
```

## 9. JSON 匯入與匯出流程

### 匯入

1. 前端選擇 JSON 檔案。
2. 前端顯示案場名稱與設備數量預覽。
3. 使用者確認後上傳。
4. 後端檢查 JSON 語法與 `schema_version`。
5. 後端逐筆驗證所有設備。
6. 全部驗證成功才取代目前設定。
7. 取代完成後清除舊的連線狀態。
8. 前端重新取得案場設定。

匯入失敗時，後端不得寫入部分資料，前端必須顯示完整錯誤欄位。

### 匯出

1. 後端產生符合 `schema_version=1` 的 JSON。
2. 檔名建議格式：`{site_name}-modbus-config.json`。
3. 前端使用下載功能保存檔案。
4. 匯出內容不包含目前狀態或檢查歷史。

## 10. 檢查與輪詢設計

### 單次檢查

單次檢查流程：

1. 載入設備設定。
2. 驗證設定。
3. 建立 Modbus TCP Client。
4. 執行功能碼 `01`、`02`、`03` 或 `04`。
5. 驗證回應與預期值。
6. 關閉連線。
7. 更新狀態。

### 並行檢查

- 使用 `ThreadPoolExecutor` 或背景工作佇列。
- 最大並行數預設 `10`。
- 同一台設備不能同時被兩個檢查工作佔用。
- 檢查結果必須以設備名稱為 key 更新狀態。

### 持續輪詢

第一版建議先將持續輪詢做成可選功能：

- `scan_rate_ms=0`：只檢查一次。
- `scan_rate_ms>0`：啟動背景工作並依週期讀取。
- 修改或刪除設備時，必須停止該設備的輪詢工作。
- 匯入新案場時，必須停止所有舊案場輪詢工作。
- 伺服器結束時，必須停止所有背景工作並關閉連線。

## 11. 既有程式整合策略

目前 [modbus_checker.py](modbus_checker.py) 已具備：

- CSV 載入。
- 基本欄位驗證。
- 地址轉換。
- Modbus TCP 檢查。
- 並行檢查。
- JSON/CSV 結果輸出。

第一版不建議直接刪除這支程式，而是：

1. 保留 CLI 功能。
2. 將 `Device`、`CheckResult` 抽成共用資料模型。
3. 將地址轉換與驗證移到共用模組。
4. 將 `check_device()` 移到 `server/modbus_adapter.py`。
5. CLI 與 API 都呼叫相同的 Adapter。

這樣可以避免 CLI 與 Web API 使用不同 Modbus 行為。

## 12. 測試策略

### 後端單元測試

優先測試：

- IP、Port、Unit ID、功能碼與數量驗證。
- 地址 `0` 與 PLC 地址 `40001` 的轉換。
- JSON 匯入成功、部分失敗與版本不支援。
- 預期值比對。
- 最大並行限制。
- 修改或刪除設備時停止輪詢。

### Modbus 測試

- 不直接在單元測試連接現場設備。
- 以 mock 或測試用 Modbus Server 驗證 `pymodbus` 呼叫。
- 使用實際設備進行整合測試時，必須使用可安全讀取的暫存器。

### 前端測試

- 表單必填欄位與數值範圍。
- PLC 位址顯示。
- 匯入確認與錯誤訊息顯示。
- 狀態表格顯示不同結果。

## 13. 可擴充設計

日後擴充時，應依照下列方式加入：

### 新增功能碼

1. 在資料模型加入允許的功能碼。
2. 在 Adapter 新增對應讀取方法。
3. 在前端下拉選項加入功能碼。
4. 加入 PLC 位址轉換測試。

### 新增 Modbus Poll Adapter

1. 定義與 `ModbusTcpAdapter` 相同的介面。
2. 實作 `check_device(device)`。
3. 在 Service Layer 依設定選擇 Adapter。
4. 不改變前端 API 與結果格式。

### 新增資料庫

1. 保留 JSON 作為案場匯入匯出格式。
2. 新增 Repository 介面。
3. JSON Store 與 Database Store 使用相同資料模型。
4. 不直接修改 API 資料格式。

## 14. 維護規範

- 所有新增設定欄位必須有預設值或明確必填規則。
- 設定格式變更時必須增加 `schema_version`。
- API 錯誤必須包含欄位層級明細。
- Modbus 例外必須轉換成穩定的 `error_type`。
- 不在日誌記錄敏感資訊。
- 前端不允許直接寫死 Modbus 行為。
- 每次修改共用資料模型時，必須同步檢查 CLI、API 與前端型別。

## 15. 第一版實作順序

1. 抽出共用資料模型與驗證模組。
2. 建立 JSON 案場設定儲存模組。
3. 建立 Modbus Adapter 並沿用既有檢查邏輯。
4. 建立 FastAPI 後端 API。
5. 建立 React + TypeScript + Ant Design 前端。
6. 完成設備狀態表格與新增表單。
7. 完成 JSON 匯入與匯出。
8. 完成單次與全部檢查。
9. 加入持續輪詢與停止機制。
10. 補齊單元測試與整合測試。

## 16. 第一版完成條件

第一版完成時必須符合：

- 可以從瀏覽器新增、修改、刪除設備。
- 可以匯入與匯出完整案場 JSON。
- 可以檢查單台設備與全部設備。
- 可以顯示 PASS、FAIL、TIMEOUT、CONFIG_ERROR 狀態。
- 可以支援 `01`、`02`、`03` 與 `04`。
- 可以設定連線逾時、回應逾時、輪詢週期與輪詢延遲。
- 匯入失敗不會造成部分設定套用。
- 命令列 CSV 檢查功能仍可執行。
- 後端驗證、匯入匯出與檢查流程有基本測試。
