# 設備批次新增功能工程開發文件

## 1. 目的

在現有「單筆新增設備」流程之上，提供批次新增功能，讓使用者能一次匯入大量設備（例如對講機系統動輒 200+ 台），免除逐筆填寫表單的負擔。

主要目標：

- 支援從 Excel/CSV 複製貼上多列資料，或上傳 CSV 檔案。
- **CSV 標題直接使用 `DeviceConfig`（案場 JSON）的欄位名稱**，系統依標題名稱對應欄位，不需人工指定欄位位置。
- 欄位可依需求增減：只填 `name, ip` 即可新增；要完整檢查則加上 `check_profile` 與 Modbus 欄位。
- 檢查類型由 `check_profile` 欄位決定（`ping` / `ping_tcp` / `full_stack`），與單筆表單的「預設檢查流程」語意一致。
- 未提供的欄位套用系統預設值（`deviceDefaults`）。
- 送出前提供可勾選的預覽表格，標示重複與格式錯誤，讓使用者只匯入乾淨資料。
- 逐筆回報新增結果，失敗不影響其他筆。

## 2. 非目標

第一版不做以下功能：

- 後端批次交易端點（`POST /api/devices/batch`）。第一版採前端迴圈逐筆呼叫既有 `POST /api/devices`，理由見第 8 節。
- 直接讀取 `.xlsx` 二進位檔。僅支援 CSV 與純文字貼上；使用者需先從 Excel 另存或複製為文字。
- 欄位別名（alias）對應。標題必須與 schema 欄位名稱完全相同（大小寫不敏感、允許前後空白），例如 `ip` 不接受 `IP位址`、`address_ip`。
- 人工欄位對應介面。欄位位置由標題決定，不提供下拉選單指定「第幾欄」。
- 修改既有單筆新增表單 `DeviceEditor` 的行為。
- 匯入後自動觸發設備檢查。匯入完成後由使用者手動執行。

## 3. 名詞定義

| 名詞 | 定義 |
| --- | --- |
| 批次新增 | 一次解析多列文字並產生多筆 `DeviceConfig` 的新增流程。 |
| 貼上來源 | 使用者在文字框中貼上的多行文字，第一列為標題，其後每行一筆設備。 |
| 標題對應 | 依 CSV 標題名稱對應到 `DeviceConfig` 欄位，取代人工欄位對應。 |
| 檢查類型 | 由 `check_profile` 欄位決定：`ping`、`ping_tcp`、`full_stack`。 |
| 預設值 | 未在 CSV 提供的欄位，套用 `deviceDefaults`（見第 7.3 節）。 |
| 預覽列 | 解析後、送出前的候選設備，含驗證狀態（可新增 / 重複 / 格式錯誤）。 |

## 4. 使用者流程

```text
切換到「批次新增」分頁
        │
        ▼
① 貼上資料或上傳 CSV（第一列為標題，標題使用 schema 欄位名稱）
        │
        ▼
② 系統依標題自動對應欄位，顯示辨識結果
        │      ├─ 已辨識欄位：name, ip, check_profile, ...
        │      ├─ 缺少必填欄位：name / ip
        │      └─ 未知標題：忽略並提示
        ▼
③ 預覽表格：勾選要匯入的列
        │
        ▼
④ 確認新增 ──► 前端迴圈逐筆 POST /api/devices
        │              │
        │              ├─ 成功：更新 devices state
        │              └─ 失敗：標記該列失敗，繼續下一筆
        ▼
⑤ 顯示結果摘要（成功 N 筆 / 失敗 M 筆）
```

## 5. 介面設計

### 5.1 位置

在 `NetworkPanel` 的「新增設備」Collapse 項目內，以 `Segmented` 切換「單筆新增 / 批次新增」兩種模式。不另開頁面或 route。

### 5.2 版面

```text
┌─ 新增設備 ─────────────────────────────────────────────┐
│   [ 單筆新增 ] [ 批次新增 ]        ← Segmented 切換      │
├────────────────────────────────────────────────────────┤
│ ① 貼上資料（第一列為標題）                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │ name,ip,check_profile                             │  │
│  │ 管理中心,192.168.1.2,ping                         │  │
│  │ 消防閘道器,192.168.0.50,full_stack                │  │
│  └──────────────────────────────────────────────────┘  │
│   [上傳 CSV]   分隔符: 自動▾                            │
│                                                        │
│ ② 欄位辨識結果                                          │
│   ✅ 已辨識：name, ip, check_profile                    │
│   ⚠️ 未知標題（將忽略）：ty, ro, sm, gw                 │
│   ❌ 缺少必填：無                                       │
│                                                        │
│ ③ 預覽表格                                              │
│  ┌────┬──────────┬─────────────┬────────────┬────────┐│
│  │ ✓  │ name      │ ip          │ check_profile │ 狀態 ││
│  │ ☑  │ 管理中心  │ 192.168.1.2 │ ping       │ 可新增 ││
│  │ ☐  │ 社區櫃台  │ 192.168.1.3 │ ping       │ 名稱重複││
│  │ ☐  │ (無名稱)  │ 999.1.1.1   │ ping       │ IP錯誤 ││
│  └────┴──────────┴─────────────┴────────────┴────────┘│
│  共 12 筆 · 可新增 10 · 重複 1 · 錯誤 1                 │
│                          [ 取消 ] [ 確認新增 10 筆 ]    │
└────────────────────────────────────────────────────────┘
```

### 5.3 互動細節

- TextArea 內容變更時即時重新解析預覽（debounce 300ms）。
- 預覽表格欄位依 CSV 實際出現的標題動態產生，並依 schema 順序排列。
- 預設勾選狀態：`可新增` 勾選；`重複`、`格式錯誤` 不勾選。
- `重複` 定義：名稱已存在於現有 `devices`，或批次內先前已出現同名。
- `格式錯誤` 定義：必填欄位缺漏、IP 格式錯誤、或欄位值超出允許範圍（見第 6.4 節）。
- 未知標題不阻擋匯入，僅在 ② 提示，該欄資料忽略。
- 確認新增按鈕停用條件：無勾選列，或缺少必填欄位（`name`、`ip`）。
- 匯入中顯示 Progress；完成後顯示 `成功 N 筆、失敗 M 筆`，失敗列保留在預覽表格中並標示原因，供使用者修正後重試。

## 6. 輸入格式解析

### 6.1 標題對應規則

第一列固定視為標題列。系統將每個標題正規化（trim、轉小寫）後，與 `DeviceConfig` 欄位名稱比對：

1. **標題符合 schema 欄位名稱** → 該欄資料對應到該欄位。
2. **標題不符合任何欄位名稱** → 標示為「未知標題」，該欄資料忽略，並在 ② 提示。
3. **缺少必填欄位**（`name`、`ip`）→ 停用確認新增，提示使用者補齊。
4. **缺少選填欄位** → 套用預設值（第 7.3 節）。

### 6.2 欄位規格

| 欄位 | 必填 | 型別 | 預設值 | 驗證規則 |
| --- | --- | --- | --- | --- |
| `name` | ✅ | string | — | 不可空白；不可與現有或批次內設備重複 |
| `ip` | ✅ | string | — | IPv4 格式（沿用 `DeviceEditor` regex） |
| `check_profile` | 選填 | enum | `full_stack` | `ping` / `ping_tcp` / `full_stack` |
| `port` | 選填 | int | 502 | 1–65535 |
| `unit_id` | 選填 | int | 1 | 0–247 |
| `function` | 選填 | enum | `03` | `01` / `02` / `03` / `04` |
| `address` | 選填 | int | 0 | ≥ 0 |
| `quantity` | 選填 | int | 10 | 1–2000 |
| `expected` | 選填 | string | `null` | 逗號分隔整數，或留空 |
| `address_mode` | 選填 | enum | `dec` | `dec` / `hex` |
| `connect_timeout_ms` | 選填 | int | 3000 | ≥ 1 |
| `response_timeout_ms` | 選填 | int | 1000 | ≥ 1 |
| `scan_rate_ms` | 選填 | int | 1000 | ≥ 0 |
| `delay_between_polls_ms` | 選填 | int | 20 | ≥ 0 |
| `enabled` | 選填 | bool | `true` | `true`/`false`/`1`/`0`/`是`/`否` |
| `tcp_port` | 選填 | int | `null` | 1–65535，`ping_tcp` 時必填 |
| `ping_enabled` | 選填 | bool | `true` | 同上 bool 規則 |
| `ping_attempts` | 選填 | int | 4 | ≥ 1 |
| `ping_timeout_ms` | 選填 | int | 1000 | ≥ 1 |
| `ping_interval_ms` | 選填 | int | 200 | ≥ 0 |
| `tcp_check_enabled` | 選填 | bool | `true` | 同上 bool 規則 |
| `tcp_timeout_ms` | 選填 | int | 2000 | ≥ 1 |
| `skip_when_ping_failed` | 選填 | bool | `false` | 同上 bool 規則 |
| `max_latency_ms` | 選填 | int | `null` | ≥ 0 或留空 |
| `max_loss_percent` | 選填 | int | `null` | 0–100 或留空 |

> 欄位名稱與 `data/家泰家悅.json` 的 `devices[]` 物件鍵完全一致，可直接參照該檔。

### 6.3 檢查類型判定

檢查類型完全由 `check_profile` 欄位決定，與單筆表單的 Segmented 選項相同：

| `check_profile` | 檢查內容 | 需要 Modbus 欄位 |
| --- | --- | --- |
| `ping` | 僅 ICMP Ping | 否 |
| `ping_tcp` | Ping + TCP Port | 否（但需 `tcp_port`） |
| `full_stack` | Ping + TCP + Modbus 讀取 | 是（`unit_id`、`function`、`address`、`quantity`） |

- 未提供 `check_profile` 時，預設為 `full_stack`（與 `deviceDefaults` 一致）。
- 若 `check_profile` 為 `ping` 或 `ping_tcp`，Modbus 相關欄位即使有值也不驗證、不影響檢查。
- 同一批可混用不同 `check_profile`（每列各自判定），因為類型是逐列欄位而非全域設定。

### 6.4 邊界情況

- 空行與僅含空白字元的行忽略。
- 欄位值前後空白去除（trim）；標題比對大小寫不敏感。
- 布林值接受 `true`/`false`/`1`/`0`/`是`/`否`（大小寫不敏感）。
- 數值欄位若無法轉為整數 → 該列標示 `格式錯誤`。
- 來源名稱含逗號時（如 `"管理中心,警衛室"`）：第一版不支援引號包裹的 CSV 解析；若偵測到引號包裹欄位，提示使用者改用 Tab 分隔貼上。
- 同一列欄位數多於標題數 → 多餘欄位忽略；少於標題數 → 缺少的欄位視為空值。

## 7. 資料模型

### 7.1 解析結果（前端內部）

```ts
type ParsedRow = {
  /** 來源行號，1-based，用於錯誤回報 */
  lineNumber: number;
  /** 依標題對應後、套用預設值完成的設備設定 */
  device: DeviceConfig;
  /** 驗證狀態 */
  issue: "OK" | "DUPLICATE_NAME" | "INVALID_IP" | "INVALID_VALUE" | "MISSING_REQUIRED";
  /** 錯誤說明，issue 非 OK 時提供 */
  detail?: string;
};

type ParseResult = {
  rows: ParsedRow[];
  /** 已辨識的 schema 欄位名稱 */
  recognizedColumns: string[];
  /** 未知標題，將被忽略 */
  unknownColumns: string[];
  /** 缺少的必填欄位 */
  missingRequired: string[];
};
```

### 7.2 送出 payload

每筆設備沿用既有 `DeviceConfig` schema（`frontend/src/api/client.ts`）。CSV 有提供的欄位用該列值，未提供的套用預設值：

```json
{
  "name": "管理中心",
  "ip": "192.168.1.2",
  "port": 502,
  "unit_id": 1,
  "address": 0,
  "quantity": 1,
  "function": "03",
  "expected": null,
  "address_mode": "dec",
  "connect_timeout_ms": 3000,
  "response_timeout_ms": 1000,
  "scan_rate_ms": 1000,
  "delay_between_polls_ms": 20,
  "enabled": true,
  "check_profile": "ping",
  "ping_enabled": true,
  "ping_attempts": 4,
  "ping_timeout_ms": 1000,
  "ping_interval_ms": 200,
  "tcp_check_enabled": true,
  "tcp_port": null,
  "tcp_timeout_ms": 2000,
  "skip_when_ping_failed": false,
  "max_latency_ms": null,
  "max_loss_percent": null
}
```

後端不需任何修改：`POST /api/devices` 已存在且 schema 不變。

### 7.3 預設值來源

未提供的欄位一律套用 `frontend/src/components/formDefaults.ts` 的 `deviceDefaults`，與單筆新增表單共用同一份預設值，避免兩處定義不一致。

```ts
export const deviceDefaults: DeviceConfig = {
  name: "",
  ip: "",
  port: 502,
  unit_id: 1,
  address: 0,
  quantity: 10,
  function: "03",
  expected: "",
  address_mode: "dec",
  connect_timeout_ms: 3000,
  response_timeout_ms: 1000,
  scan_rate_ms: 1000,
  delay_between_polls_ms: 20,
  enabled: true,
  check_profile: "full_stack",
};
```

## 8. 送出策略：前端迴圈（方案 A）

### 8.1 理由

- 既有 `POST /api/devices` 已含驗證（名稱重複、IP 格式），逐筆呼叫可直接沿用，失敗訊息逐筆回報。
- 既有 `saveSite` 為整份覆蓋式寫入，若新增批次端點需處理合併邏輯，複雜度較高。
- 實務批次規模（數十至數百筆）在 HTTP 逐筆呼叫下可接受。

### 8.2 併發控制

- 併發上限 5，沿用 `NetworkPanel.runChecks` 的 worker-pool 模式實作。
- 每筆完成後更新預覽表格該列狀態（`新增成功` / `新增失敗: <原因>`）。

### 8.3 失敗處理

- 單筆失敗不中斷整批。
- 全部完成後顯示摘要。失敗列保留勾選狀態與錯誤訊息，使用者可修正名稱後重試（重試僅送出失敗列）。

### 8.4 未來升級路徑（方案 B）

若未來單批超過 500 筆或需要原子性（全成功或全失敗），再新增：

```
POST /api/devices/batch
Body: { "devices": [DeviceConfig, ...] }
Response: { "results": [{ "name": "...", "status": "created" | "failed", "error": "..." }] }
```

介面層不需改動，僅替換 `api` 呼叫。

## 9. 檔案變更清單

| 檔案 | 變更 | 說明 |
| --- | --- | --- |
| `frontend/src/components/BatchAddPanel.tsx` | 新增 | 批次新增主元件，含解析、欄位辨識、預覽、送出邏輯。 |
| `frontend/src/utils/batchParse.ts` | 新增 | 純函式解析模組，依標題對應 schema 欄位。 |
| `frontend/src/components/NetworkPanel.tsx` | 修改 | 在「新增設備」Collapse 內加入 Segmented 切換單筆/批次。 |
| `frontend/src/api/client.ts` | 不變 | 沿用 `addDevice`。 |
| `frontend/src/App.tsx` | 修改 | 傳入 `devices`（供重複檢查）與 `onBatchAdded`（更新 state）callback。 |
| `backend/` | 不變 | 無需修改。 |

### 9.1 元件介面

```tsx
type BatchAddPanelProps = {
  /** 現有設備，用於名稱重複檢查 */
  existingDevices: Device[];
  /** 批次新增完成後回呼，傳入成功新增的 DeviceConfig 陣列 */
  onBatchAdded: (added: DeviceConfig[]) => void | Promise<void>;
};
```

### 9.2 解析模組

解析邏輯（分隔符偵測、標題對應、型別轉換、驗證）抽成純函式，放在 `frontend/src/utils/batchParse.ts`，不依賴 React，方便單元測試：

```ts
/** 偵測分隔符：Tab > 逗號 > 分號 */
export function detectDelimiter(text: string): "\t" | "," | ";";

/** 解析多行文字為 ParseResult */
export function parseBatchText(
  text: string,
  options?: {
    delimiter?: "\t" | "," | ";" | "auto";
    /** 現有名稱，用於重複檢查 */
    existingNames?: string[];
  }
): ParseResult;
```

`parseBatchText` 內部流程：

1. 依分隔符切出標題列與資料列。
2. 標題正規化後對應 `DeviceConfig` 欄位，產生 `recognizedColumns` / `unknownColumns`。
3. 逐列將字串轉為對應型別（int / bool / enum），失敗則標示 `INVALID_VALUE`。
4. 未提供的欄位套用 `deviceDefaults`。
5. 驗證必填、IP 格式、名稱重複，產生 `issue`。

## 10. 驗證與測試

### 10.1 單元測試（`batchParse.ts`）

| 案例 | 期望 |
| --- | --- |
| `name,ip` 兩欄 | 全部解析為 `OK`，其餘欄位套用預設值 |
| 完整欄位 CSV（參照 `家泰家悅.json`） | 每欄正確對應與轉型 |
| 標題大小寫不同（`Name,IP`） | 仍正確辨識 |
| 未知標題（`ty,ro,sm`） | 列入 `unknownColumns`，不影響匯入 |
| 缺少 `name` 或 `ip` | `missingRequired` 非空，停用送出 |
| `check_profile=ping` | 不驗證 Modbus 欄位 |
| `check_profile=full_stack` 缺 `quantity` | 套用預設值 10 |
| 非法 IP（`999.1.1.1`） | 標示 `INVALID_IP` |
| 非整數的 `port`（`abc`） | 標示 `INVALID_VALUE` |
| 布林值 `是` / `否` | 正確轉為 `true` / `false` |
| 批次內名稱重複 | 後者標示 `DUPLICATE_NAME` |
| 空行、空白行 | 忽略，不產生列 |
| Tab 分隔貼上（Excel 預設） | 自動偵測為 Tab |
| 引號包裹欄位 | 提示改用 Tab 貼上 |

### 10.2 整合測試

- 既有 `backend/tests/test_api_batches.py` 模式：以 TestClient 逐筆 `POST /api/devices` 驗證後端行為不變（此為回歸確認，不需新測試）。
- 前端以 `data/家泰家悅.json` 的欄位結構建立測試 CSV，驗證完整欄位可正確匯入。

### 10.3 手動驗收清單

- [ ] 從 Excel 複製多列（含 Tab）貼上可正確解析。
- [ ] 上傳 CSV 檔可正確解析。
- [ ] 只提供 `name,ip` 兩欄即可成功新增。
- [ ] 提供 `check_profile` 可正確決定檢查類型。
- [ ] 未知標題顯示於 ② 提示且被忽略。
- [ ] 缺少必填欄位時確認新增按鈕停用。
- [ ] 重複名稱與非法 IP 預設不勾選。
- [ ] 確認新增後預覽表格逐筆顯示結果。
- [ ] 部分失敗時可修正後僅重試失敗列。
- [ ] 新增成功的設備出現在檢查結果列表，且可排序。

## 11. 里程碑

| 階段 | 內容 | 驗收 |
| --- | --- | --- |
| M1 | `batchParse.ts` 純函式 + 單元測試 | 10.1 全數通過 |
| M2 | `BatchAddPanel` UI（貼上、欄位辨識、預覽） | 可完整走完 ①–③ |
| M3 | 送出迴圈 + 結果回報 + App.tsx 接線 | 可完整走完 ①–⑤ |
| M4 | CSV 檔上傳、未知標題提示 | 手動驗收清單全數通過 |

## 12. 風險與備案

| 風險 | 說明 | 備案 |
| --- | --- | --- |
| 標題名稱不符 schema | 使用者自訂標題（如 `IP位址`）無法辨識 | ② 明確列出未知標題；文件提供欄位名稱對照表（第 6.2 節） |
| 引號 CSV 解析 | 第一版不支援，實務來源多為 Excel 直接複製 | 偵測到引號時提示改用 Tab 貼上 |
| 大批次效能 | 500+ 筆逐筆 HTTP 呼叫較慢 | 升級至方案 B 批次端點 |
| 名稱重複判定 | 與現有設備同名會被後端拒絕 | 預覽即時標示，預設不勾選 |
| 型別轉換錯誤 | 使用者填入非數值（如 `port=abc`） | 逐列標示 `INVALID_VALUE`，預設不勾選 |
