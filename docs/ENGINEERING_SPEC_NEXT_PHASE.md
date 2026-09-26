# Modbus 案場回歸驗證工具：工程師實作規格

## 1. 文件目的

本文件是 [NEXT_PHASE_DEVELOPMENT.md](NEXT_PHASE_DEVELOPMENT.md) 的工程實作規格。產品文件回答「要做什麼、為什麼做」，本文件回答「怎麼做、放在哪、介面長什麼樣、以後怎麼擴充」。

實作本規格前，請先閱讀：

- [DEVELOPMENT.md](DEVELOPMENT.md)：原始需求與技術決策
- [INITIAL_DEVELOPMENT.md](INITIAL_DEVELOPMENT.md)：第一版實作規格
- [NEXT_PHASE_DEVELOPMENT.md](NEXT_PHASE_DEVELOPMENT.md)：本階段產品定義

## 2. 設計原則

### 2.1 依賴方向

依賴只能由外層指向內層，禁止反向：

```text
API Layer (FastAPI Router)
    |
    v
Application Service Layer (Batch / Comparison / Report)
    |
    v
Domain Layer (Device / Check / Comparison 領域規則)
    |
    v
Port Layer (Protocol 介面定義)
    ^
    |
Adapter Layer (ModbusTcpAdapter, 未來的 RtuAdapter)
    ^
    |
Repository Layer (SQLite 實作)
```

內層不得 import 外層模組。Domain 與 Port 層不得 import `fastapi`、`pymodbus`、`sqlite3`。

### 2.2 介面先行

所有可能替換實作的能力，都以 `typing.Protocol` 定義介面，Service 只依賴 Protocol：

- 設備檢查：`DeviceChecker`（目前實作為 `ModbusTcpAdapter`）
- 歷史儲存：`HistoryRepository`（目前實作為 `SqliteHistoryRepository`）
- 報告渲染：`ReportRenderer`（CSV、HTML 各一個實作）
- 差異比較：`ComparisonRule`（可多個規則組合）

### 2.3 不變資料

- 已完成的 `CheckRecord` 與 `CheckBatch` 不可修改，只可刪除。
- 基準批次可替換，但替換後舊基準的歷史資料仍然保留。
- 設備設定快照在批次建立時固化，後續修改設備設定不影響已完成的批次。

### 2.4 單一寫入點

- 案場設定只透過 `SiteStore` 寫入。
- 歷史資料只透過 `HistoryRepository` 寫入。
- Modbus 通訊只發生在 Adapter 層。

## 3. 目錄結構

在既有結構上擴充，新增模組以 `+` 標示：

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # API 進入點，掛載各 router
│   ├── schemas.py                 # 既有 HTTP 層資料模型
│   ├── site_store.py              # 既有案場 JSON 儲存
│   ├── check_service.py           # 既有並行檢查與輪詢
│   ├── modbus_adapter.py          # 既有 pymodbus 封裝
│   │
│   ├── domain/                    # + 領域模型與規則（無外部依賴）
│   │   ├── __init__.py
│   │   ├── models.py              # + CheckBatch / CheckRecord / Baseline / Diff
│   │   ├── health.py              # + 健康度摘要計算
│   │   └── diagnosis.py           # + 錯誤分類與建議檢查項目
│   │
│   ├── ports/                     # + 介面定義（Protocol）
│   │   ├── __init__.py
│   │   ├── checker.py             # + DeviceChecker Protocol
│   │   ├── history.py             # + HistoryRepository Protocol
│   │   └── report.py              # + ReportRenderer Protocol
│   │
│   ├── repositories/              # + 儲存實作
│   │   ├── __init__.py
│   │   ├── sqlite_history.py      # + SQLite 實作
│   │   └── migrations/            # + schema 版本遷移 SQL
│   │       ├── 0001_init.sql
│   │       └── README.md
│   │
│   ├── services/                  # + 應用服務
│   │   ├── __init__.py
│   │   ├── batch_service.py       # + 批次建立、執行、查詢
│   │   ├── comparison_service.py  # + 基準比較
│   │   ├── comparison_rules.py    # + 各種差異判定規則
│   │   └── report_service.py      # + 報告產生與檔案管理
│   │
│   ├── renderers/                 # + 報告渲染實作
│   │   ├── __init__.py
│   │   ├── csv_report.py          # + CSV 報告
│   │   ├── html_report.py         # + HTML 報告（含樣板）
│   │   └── templates/
│   │       └── report.html        # + HTML 報告樣板
│   │
│   └── routers/                   # + API 路由拆分
│       ├── __init__.py
│       ├── site.py                # + 案場與設備 CRUD（自 main.py 移出）
│       ├── check.py               # + 既有即時檢查 API
│       ├── batches.py             # + 批次 API
│       └── baseline.py            # + 基準 API
│
├── data/                          # + 執行時資料（加入 .gitignore）
│   ├── modbus_history.db          # + SQLite 資料庫
│   └── reports/                   # + 產生的報告檔案
│
└── tests/
    ├── test_core.py               # 既有
    ├── test_domain_health.py      # + 健康度計算
    ├── test_domain_diagnosis.py   # + 錯誤分類
    ├── test_comparison_rules.py   # + 差異判定
    ├── test_batch_service.py      # + 批次生命週期
    ├── test_sqlite_history.py     # + Repository 契約測試
    ├── test_renderers.py          # + 報告內容驗證
    └── test_api_batches.py        # + API 整合測試
```

## 4. 領域模型

放在 `app/domain/models.py`，使用 Pydantic，與 HTTP 層 schema 分開。

### 4.1 CheckBatch

```python
BatchMode = Literal["single", "full", "regression"]
BatchStatus = Literal["pending", "running", "completed", "failed", "cancelled"]

class CheckBatch(BaseModel):
    id: str                          # 例如 "20260926-103000-a1b2c3"
    site_name: str
    mode: BatchMode
    status: BatchStatus
    baseline_batch_id: str | None    # 本次比較使用的基準
    device_names: list[str]          # 實際被檢查的設備（含順序）
    config_snapshot: SiteConfig      # 當時的完整案場設定
    note: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    pass_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    config_error_count: int = 0
    unknown_count: int = 0
    error_message: str | None = None
```

批次 ID 產生規則：`{UTC+8 時間}-{6 碼隨機十六進位}`，由 `BatchService` 統一產生，不接受外部傳入，避免衝突與注入。

### 4.2 CheckRecord

```python
class CheckRecord(BaseModel):
    id: int | None = None            # SQLite 自增主鍵，建立前為 None
    batch_id: str
    result: CheckResult              # 沿用既有 schemas.CheckResult
    device_snapshot: DeviceConfig    # 當時該設備的完整設定
    comparison_status: ComparisonStatus | None = None
    baseline_record_id: int | None = None
    response_time_delta_ms: int | None = None
    diagnosis: Diagnosis | None = None
```

`result` 直接內嵌既有 `CheckResult`，不重複定義欄位。這是復用性的關鍵：日後 `CheckResult` 增加欄位時，Record 自動跟進。

### 4.3 ComparisonStatus

```python
ComparisonStatus = Literal[
    "UNCHANGED_PASS",
    "NEW_FAILURE",
    "RECOVERED",
    "VALUE_CHANGED",
    "LATENCY_DEGRADED",
    "CONFIG_CHANGED",
    "BASELINE_ONLY",
    "NEW_DEVICE",
    "NO_BASELINE",
]
```

### 4.4 Diagnosis

```python
DiagnosisCategory = Literal[
    "NETWORK",        # TCP 連線失敗：線路、IP、交換器
    "MODBUS_TIMEOUT", # Modbus 回應逾時：Unit ID、設備忙碌、網路品質
    "MODBUS_EXCEPTION", # 功能碼或位址不被支援
    "DATA_MISMATCH",  # 通訊正常但值不符預期
    "LATENCY",        # 通訊正常但回應變慢
    "CONFIG",         # 設定錯誤
]

class Diagnosis(BaseModel):
    category: DiagnosisCategory
    summary: str                      # 一句話描述現象
    suggestions: list[str]            # 建議檢查項目，依優先順序
```

Diagnosis 只提供「可能原因與建議檢查項目」，絕不輸出確定性根因（例如不可寫「網路線故障」）。此規則寫入 `domain/diagnosis.py` 的模組 docstring，並以測試檢查關鍵字。

### 4.5 HealthSummary

```python
class HealthSummary(BaseModel):
    device_count: int
    pass_count: int
    fail_count: int
    timeout_count: int
    config_error_count: int
    pass_rate: float                  # 0.0 ~ 1.0
    avg_elapsed_ms: float | None      # 只統計 PASS 的設備
    slowest_device: str | None
    slowest_elapsed_ms: int | None
    new_failure_count: int            # 需要 baseline 才有值
```

## 5. Port 層介面

### 5.1 DeviceChecker（`ports/checker.py`）

```python
class DeviceChecker(Protocol):
    def check_device(self, device: DeviceConfig) -> CheckResult: ...
```

既有 `ModbusTcpAdapter` 已自然符合此 Protocol，不需修改簽名。日後的 `ModbusRtuAdapter` 或 Modbus Poll Adapter 只要實作同樣方法即可注入。

### 5.2 HistoryRepository（`ports/history.py`）

```python
class HistoryRepository(Protocol):
    # 批次
    def create_batch(self, batch: CheckBatch) -> None: ...
    def update_batch_status(self, batch_id: str, status: BatchStatus,
                            *, completed_at: datetime | None = None,
                            counts: BatchCounts | None = None,
                            error_message: str | None = None) -> None: ...
    def get_batch(self, batch_id: str) -> CheckBatch: ...
    def list_batches(self, site_name: str | None, *,
                     offset: int = 0, limit: int = 50) -> tuple[list[CheckBatch], int]: ...
    def delete_batch(self, batch_id: str) -> None: ...

    # 結果
    def save_records(self, records: list[CheckRecord]) -> None: ...
    def list_records(self, batch_id: str) -> list[CheckRecord]: ...

    # 基準
    def set_baseline(self, site_name: str, batch_id: str) -> None: ...
    def get_baseline(self, site_name: str) -> SiteBaseline | None: ...
    def clear_baseline(self, site_name: str) -> None: ...
```

契約要求：

- 所有方法以領域模型為參數與回傳值，不回傳 SQLite row。
- `get_batch` 找不到時拋出 `BatchNotFoundError`（定義在 `ports/history.py`）。
- `delete_batch` 若批次是目前基準，拋出 `BatchIsBaselineError`。
- `list_batches` 回傳 `(批次清單, 總數)`，支援分頁。
- 寫入必須使用 transaction：批次與其 records 要嘛全部成功，要嘛全部失敗。

契約測試（`tests/test_sqlite_history.py`）以參數化方式設計，日後新增 Repository 實作時直接重用同一組測試。

### 5.3 ReportRenderer（`ports/report.py`）

```python
class ReportRenderer(Protocol):
    content_type: str        # 例如 "text/csv; charset=utf-8-sig"
    file_extension: str      # 例如 "csv"

    def render(self, report: ReportContext) -> bytes: ...
```

`ReportContext` 定義在 `domain/models.py`：

```python
class ReportContext(BaseModel):
    batch: CheckBatch
    records: list[CheckRecord]
    baseline: CheckBatch | None
    baseline_records: list[CheckRecord]
    summary: HealthSummary
    generated_at: datetime
```

Renderer 只接收 `ReportContext`，不接觸資料庫與網路。這讓 CSV、HTML、未來的 PDF 都共用同一份資料組裝邏輯。

## 6. 服務層設計

### 6.1 BatchService

```python
class BatchService:
    def __init__(
        self,
        history: HistoryRepository,
        checker: DeviceChecker,
        comparison: ComparisonService,
        diagnosis: DiagnosisEngine,
        max_workers: int = 10,
    ) -> None: ...
```

職責：

1. `start_batch(site, mode, device_names, note, baseline_batch_id) -> CheckBatch`
   - 驗證設備存在、啟用。
   - 建立 `pending` 批次並保存設定快照。
   - 提交背景執行（見 6.3），立即回傳。
2. `_run_batch(batch_id)`
   - 狀態轉為 `running`。
   - 並行檢查，每完成一台設備就：
     1. 呼叫 `ComparisonService` 計算差異。
     2. 呼叫 `DiagnosisEngine` 產生診斷。
     3. 即時寫入 record（讓前端可看到部分進度）。
   - 完成後彙整計數，狀態轉為 `completed`。
3. `cancel_batch(batch_id)`：標記 `cancelled`，停止未執行的設備檢查。

錯誤處理：

- 單台設備檢查拋出未預期例外時，轉為該設備的 `CONFIG_ERROR`/`UNKNOWN` record，不中斷整個批次。
- 批次層級例外（例如資料庫寫入失敗）才將批次標記為 `failed` 並記錄 `error_message`。

### 6.2 ComparisonService 與 ComparisonRule

採用規則管線（Rule Pipeline），每條規則獨立、可測試、可啟用：

```python
class ComparisonRule(Protocol):
    name: str
    def evaluate(self, ctx: ComparisonContext) -> ComparisonStatus | None: ...
```

規則依序評估，第一個回傳非 `None` 的規則決定結果：

| 順序 | 規則 | 判定 |
|---|---|---|
| 1 | `NoBaselineRule` | 無基準批次 → `NO_BASELINE` |
| 2 | `NewDeviceRule` | 基準中無此設備 → `NEW_DEVICE` |
| 3 | `ConfigChangedRule` | 設定快照關鍵欄位不同 → `CONFIG_CHANGED` |
| 4 | `NewFailureRule` | 基準 PASS 且本次 FAIL/TIMEOUT → `NEW_FAILURE` |
| 5 | `RecoveredRule` | 基準非 PASS 且本次 PASS → `RECOVERED` |
| 6 | `ValueChangedRule` | 雙方 PASS 且 values 不同 → `VALUE_CHANGED` |
| 7 | `LatencyDegradedRule` | 雙方 PASS 且超過回應時間門檻 → `LATENCY_DEGRADED` |
| 8 | 預設 | `UNCHANGED_PASS` |

`ConfigChangedRule` 只比較影響通訊語意的欄位：

```python
COMMUNICATION_FIELDS = ("ip", "port", "unit_id", "function", "address", "quantity")
```

不包含 `expected`、`scan_rate_ms` 等不影響線路通訊的欄位。欄位清單定義為模組常數，方便日後調整。

`LatencyDegradedRule` 的門檻設計：

```python
class LatencyPolicy(BaseModel):
    absolute_ms: int = 100       # 本次 - 基準 > 100 ms
    ratio: float = 2.0           # 本次 / 基準 > 2.0
    min_baseline_ms: int = 20    # 基準低於此值不判定（避免低基數誤報）
```

門檻物件放在案場層級設定（schema_version 升級時加入），第一階段可先用全域預設值。

### 6.3 執行模型

- 批次執行使用獨立的 `ThreadPoolExecutor`（與既有 `CheckService` 的 executor 分開），避免批次工作與背景輪詢互相搶佔。
- **回歸批次執行前，暫停背景輪詢**：呼叫 `CheckService.stop_polling()`，批次完成後依 API 請求中的 `resume_polling` 旗標決定是否恢復。此行為寫入 API 文件與前端提示。
- 每台設備的 record 完成後立即寫入，前端以輪詢 `GET /api/check/batches/{id}` 觀察進度；不引入 WebSocket/SSE，降低第一階段複雜度（API 回應格式已預留欄位，未來可平滑升級）。

### 6.4 ReportService

```python
class ReportService:
    def __init__(self, history: HistoryRepository,
                 renderers: dict[str, ReportRenderer],
                 output_dir: Path) -> None: ...

    def generate(self, batch_id: str, format: str) -> ReportFile: ...
```

- 依 `format` 從 `renderers` 選擇實作，未知格式拋出 `UnsupportedReportFormatError`。
- 檔名格式：`{site_name}_{batch_id}.{extension}`，對檔名做非法字元清理。
- 產生後寫入 `backend/data/reports/`，API 以 `FileResponse` 回傳。
- 同一批次同一格式重複請求時可直接重用既有檔案（以檔名判斷），或加 `?refresh=1` 強制重產。

## 7. SQLite Schema

### 7.1 遷移機制

- 建立 `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)`。
- 啟動時依序執行 `migrations/` 下未套用的 SQL。
- 每個 migration 一個檔案，檔名前綴為遞增四位數版本。
- 禁止修改已發布的 migration 檔，只能新增。

### 7.2 初始 Schema（`0001_init.sql`）

```sql
CREATE TABLE check_batches (
    id                 TEXT PRIMARY KEY,
    site_name          TEXT NOT NULL,
    mode               TEXT NOT NULL CHECK (mode IN ('single','full','regression')),
    status             TEXT NOT NULL CHECK (status IN ('pending','running','completed','failed','cancelled')),
    baseline_batch_id  TEXT,
    device_names_json  TEXT NOT NULL,
    config_snapshot    TEXT NOT NULL,   -- SiteConfig JSON
    note               TEXT,
    started_at         TEXT NOT NULL,   -- ISO 8601
    completed_at       TEXT,
    pass_count         INTEGER NOT NULL DEFAULT 0,
    fail_count         INTEGER NOT NULL DEFAULT 0,
    timeout_count      INTEGER NOT NULL DEFAULT 0,
    config_error_count INTEGER NOT NULL DEFAULT 0,
    unknown_count      INTEGER NOT NULL DEFAULT 0,
    error_message      TEXT
);

CREATE TABLE check_records (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id              TEXT NOT NULL REFERENCES check_batches(id) ON DELETE RESTRICT,
    device_name           TEXT NOT NULL,
    result_json           TEXT NOT NULL,    -- CheckResult JSON
    device_snapshot_json  TEXT NOT NULL,    -- DeviceConfig JSON
    comparison_status     TEXT,
    baseline_record_id    INTEGER,
    response_time_delta_ms INTEGER,
    diagnosis_json        TEXT
);

CREATE INDEX idx_records_batch ON check_records(batch_id);
CREATE INDEX idx_records_batch_status ON check_records(batch_id, comparison_status);
CREATE INDEX idx_batches_site_started ON check_batches(site_name, started_at DESC);

CREATE TABLE site_baselines (
    site_name         TEXT PRIMARY KEY,
    baseline_batch_id TEXT NOT NULL REFERENCES check_batches(id) ON DELETE RESTRICT,
    updated_at        TEXT NOT NULL
);
```

設計說明：

- 領域物件以 JSON 欄保存，避免每次模型加欄位都要寫 migration；查詢所需的欄位（`device_name`、`comparison_status`、計數）單獨建欄位與索引。
- `ON DELETE RESTRICT` 確保基準批次與其 records 不會被誤刪；`delete_batch` 在應用層再次檢查。
- 時間一律以 ISO 8601 含時區字串保存，由 Pydantic 負責序列化/反序列化。

### 7.3 資料庫位置與生命週期

- 預設路徑：`backend/data/modbus_history.db`，可用環境變數 `MODBUS_HISTORY_DB` 覆寫（測試時指向暫存檔）。
- 啟動時建立目錄與資料庫；不存在的遷移失敗應讓服務明確啟動失敗，不靜默降級。
- 連線管理：每次操作開啟短連線（`sqlite3` context manager），不持有全域連線，避免執行緒共用問題。

## 8. API 詳細規格

Router 拆分後，`main.py` 只負責：建立 app、註冊 router、掛載例外處理器、啟動/關閉事件。

### 8.1 批次 API

| 方法 | 路徑 | 說明 |
|---|---|---|
| `POST` | `/api/check/batches` | 建立批次，回傳 `202 Accepted` + 批次物件 |
| `GET` | `/api/check/batches` | 分頁查詢，參數：`site_name`、`offset`、`limit`、`status` |
| `GET` | `/api/check/batches/{id}` | 批次摘要 + records（含 comparison 與 diagnosis） |
| `POST` | `/api/check/batches/{id}/cancel` | 取消執行中的批次 |
| `DELETE` | `/api/check/batches/{id}` | 刪除批次（基準批次回傳 `409`） |
| `GET` | `/api/check/batches/{id}/report?format=csv` | 下載報告，`format` 支援 `csv`、`html` |

建立請求：

```json
{
    "mode": "regression",
    "site_name": "案場 A",
    "device_names": null,
    "baseline_batch_id": null,
    "note": "交換器更換後驗證",
    "resume_polling": true
}
```

規則：

- `mode=regression` 且未提供 `baseline_batch_id` 時，自動使用該案場目前基準；仍無基準則 `comparison_status=NO_BASELINE`，不算錯誤。
- `device_names=null` 表示全部啟用設備；否則逐一驗證設備存在且啟用，不存在的名稱回傳 `422` 並列出欄位明細。
- 回傳 `202` 是因為批次非同步執行；前端用 `GET` 輪詢狀態。

### 8.2 基準 API

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/sites/{site_name}/baseline` | 取得基準資訊，無基準回傳 `404` |
| `PUT` | `/api/sites/{site_name}/baseline` | 設定基準，body：`{"batch_id": "...", "force": false}` |
| `DELETE` | `/api/sites/{site_name}/baseline` | 清除基準 |

`PUT` 規則：

- 批次必須存在、屬於該案場、且 `status=completed`，否則 `409` 或 `422`。
- 批次含有 FAIL/TIMEOUT/CONFIG_ERROR 時，必須 `force=true` 才允許，回應中附警告欄位。

### 8.3 錯誤格式

沿用既有 `ErrorResponse`（`error` / `message` / `details`），新增錯誤代碼：

- `batch_not_found`
- `batch_is_baseline`
- `batch_not_completed`
- `unsupported_report_format`
- `baseline_not_found`

HTTP 例外由統一的 exception handler 轉換，Service 層只拋領域例外（`BatchNotFoundError` 等），映射表集中在 `routers/__init__.py`。

## 9. 領域服務細節

### 9.1 DiagnosisEngine（`domain/diagnosis.py`）

輸入 `CheckResult`（與可選的比較資訊），輸出 `Diagnosis`。以純函式查表實作：

```python
def diagnose(result: CheckResult) -> Diagnosis | None:
    if result.status == "PASS":
        return None
    ...
```

對應表（錯誤類型 → 分類 → 建議項目）：

| error_type / status | category | suggestions（依序） |
|---|---|---|
| `CONNECTION_FAILED` | NETWORK | 設備電源與網路指示燈、網路線與交換器 Port、IP 設定與網段、防火牆 |
| `TIMEOUT` | MODBUS_TIMEOUT | Unit ID 是否正確、設備是否忙碌、網路品質與延遲、功能碼是否被設備支援 |
| `MODBUS_EXCEPTION` | MODBUS_EXCEPTION | 功能碼支援性、位址範圍、quantity 上限 |
| `UNEXPECTED_VALUE` | DATA_MISMATCH | PLC 位址偏移（0/1 起算）、資料格式、預期值設定 |
| `LATENCY_DEGRADED` | LATENCY | 輪詢頻率、網路負載、交換器、設備回應能力 |
| `CONFIG_ERROR` | CONFIG | 設備設定欄位、schema_version、匯入來源 |

建議文字集中定義在模組頂層常數（日後可抽成 JSON 資源檔以支援多語系），前端直接顯示 `suggestions`，不自行硬編診斷文字。

### 9.2 健康度計算（`domain/health.py`）

- 純函式：`summarize(records: list[CheckRecord]) -> HealthSummary`。
- `avg_elapsed_ms` 只統計 `PASS` 設備，避免失敗的長逾時扭曲平均值。
- `pass_rate` 分母為 0 時回傳 `0.0` 並在 API 文件註明。

## 10. 前端實作規格

### 10.1 路由與狀態

目前前端是單頁 `App.tsx`。本階段引入路由（`react-router`）：

| 路由 | 畫面 |
|---|---|
| `/` | 快速回歸檢查（新首頁） |
| `/devices` | 既有設備管理與檢查表格 |
| `/batches` | 批次歷史 |
| `/batches/:id` | 批次明細與差異 |

考量：`react-router` 是新依賴；若希望先不引入，可以 `useState` 切換頁籤過渡，但資料模型與 API client 應直接按路由版設計，避免二次修改。

### 10.2 API Client

在 `frontend/src/api/client.ts` 增加：

- `createBatch(req) -> Batch`
- `getBatch(id) -> BatchDetail`
- `listBatches(params) -> { items, total }`
- `cancelBatch(id)`
- `deleteBatch(id)`
- `getBaseline(siteName)` / `setBaseline(siteName, batchId, force)` / `clearBaseline(siteName)`
- `getReportUrl(id, format)`（回傳 URL 字串供 `<a download>` 使用）

TypeScript 型別與後端 Pydantic 模型對齊。回歸檢查進度用 `setInterval` 輪詢 `getBatch`，批次進入終態（`completed`/`failed`/`cancelled`）後停止輪詢。

### 10.3 快速回歸檢查畫面

版面由上而下：

1. 案場名稱 + 目前基準（時間與批次號；無基準時顯示引導文案）。
2. 備註輸入 +「開始回歸檢查」按鈕（執行中禁用，並顯示輪詢已暫停的提示）。
3. 進度條：已完成設備數 / 總數。
4. `HealthSummary` 統計卡片。
5. 異常設備表格置頂（`NEW_FAILURE`、`LATENCY_DEGRADED`、`VALUE_CHANGED`、`CONFIG_CHANGED`），每台顯示 `Diagnosis.summary` 與可展開的 `suggestions`。
6. 「設為基準」與「下載報告（CSV / HTML）」按鈕，批次完成後才啟用。

### 10.4 復用既有元件

- 狀態 Tag 色彩定義抽成共用模組，批次明細與既有設備表格共用。
- `toDevice` / `toConfig` 轉換函式移到 `frontend/src/api/mappers.ts`，避免新畫面複製。

## 11. 擴充性設計檢核表

實作時以下擴充必須「只新增、不修改核心」才算合格：

| 擴充情境 | 預期做法 |
|---|---|
| 新增 Modbus RTU over TCP | 新增 `ModbusRtuAdapter` 實作 `DeviceChecker`；設備設定加 `connection_type` 欄位（schema_version 升級）；Service 依欄位選擇 Adapter |
| 新增 PDF 報告 | 新增 `PdfReportRenderer` 並註冊進 `ReportService.renderers`；API `format=pdf` 自動可用 |
| 新增告警通知 | 新增 `NotificationPort` 與實作；在 `BatchService` 完成鉤子中呼叫；不改比較與儲存邏輯 |
| 更換資料庫 | 新增 Repository 實作，通過同一組契約測試；修改組裝處（`main.py` 依賴注入）即可 |
| 新增比較規則 | 新增 `ComparisonRule` 並插入管線順序；既有規則與測試不受影響 |
| 多案場使用者權限 | 在 API 層加驗證依賴；領域與儲存層不需要知道使用者概念 |

## 12. 相容性與資料遷移

### 12.1 設定檔

- 本階段不變更 `SiteConfig.schema_version`（維持 `1`）。
- `LatencyPolicy` 等案場層級設定第一階段使用程式內預設值，待需要由使用者調整時再升級 schema 至 `2`，屆時匯入器必須同時接受 `1` 與 `2`。

### 12.2 既有記憶體狀態

- 既有 `GET /api/status` 與 polling API 行為不變，批次功能是疊加而非取代。
- 升級前已存在於記憶體的狀態不遷入資料庫；文件與更新說明中告知使用者重新執行一次完整檢查以建立首批歷史。

### 12.3 輪詢語意修正（破壞性變更）

自動檢查的預設週期為 `1000 ms`；`scan_rate_ms=0` 時沿用此預設週期：

- 在更新說明中明確標註。
- 新增設備的前後端預設值均為 `1000`。
- 舊案場中保存為 `0` 的設備仍會在自動檢查時每秒輪詢。
- 測試需驗證 `scan_rate_ms=0` 時採用預設輪詢週期。

## 13. 測試策略

### 13.1 測試金字塔

| 層級 | 範圍 | 工具 |
|---|---|---|
| 領域單元測試 | health、diagnosis、comparison rules | unittest，無 I/O |
| Repository 契約測試 | SQLite CRUD、transaction、約束 | 暫存檔資料庫 |
| Service 測試 | BatchService 生命週期、取消、錯誤路徑 | Fake Repository + Fake Checker |
| API 測試 | 路由、狀態碼、錯誤格式 | FastAPI `TestClient` |
| 前端測試 | 進度輪詢、異常置頂、基準確認流程 | Vitest + Testing Library（新增） |

### 13.2 關鍵測試案例

- 批次中單台設備拋出未預期例外 → 批次仍 `completed`，該設備 record 為錯誤狀態。
- 批次與 records 寫入中途失敗 → 資料庫無殘留半成品（transaction 驗證）。
- 刪除目前基準批次 → `409` 且資料未被刪除。
- `force=false` 設定含失敗的批次為基準 → `409`。
- 基準低於 `min_baseline_ms` 時不產生 `LATENCY_DEGRADED`。
- 回歸批次執行期間背景輪詢已暫停（以 Fake Checker 計數驗證）。
- CSV 報告包含 BOM（`utf-8-sig`）使 Excel 正確顯示中文。

### 13.3 命名與假資料

測試用 `FakeChecker` 放在 `tests/fakes.py`，支援：

- 依設備名稱回傳預設結果表。
- 模擬例外與逾時。
- 記錄呼叫次數（驗證並行與輪詢暫停）。

## 14. 實作順序與驗收

### Phase 2A：歷史基礎

1. 修正 `scan_rate_ms=0` 輪詢語意 + 測試。
2. 建立 `domain/models.py`、`ports/`、SQLite Repository + migrations。
3. 建立 `BatchService`（先同步執行，再改背景執行）。
4. 建立批次 API + Service 測試。

驗收：重啟服務後可查詢先前批次；既有 API 全部不變。

### Phase 2B：基準與比較

1. `ComparisonService` + 規則管線 + 全部規則測試。
2. 基準 API + `force` 流程。
3. `DiagnosisEngine` + 對應表測試。
4. 批次明細 API 回傳 comparison 與 diagnosis。

驗收：刻意讓一台設備失敗，新批次顯示 `NEW_FAILURE` 且附診斷建議。

### Phase 2C：現場工作流程與報告

1. 前端快速回歸檢查畫面與進度輪詢。
2. 批次歷史與明細畫面。
3. CSV / HTML Renderer + ReportService + 下載 API。
4. 基準設定/更換的確認對話框。

驗收：從載入案場到拿到 HTML 報告，不超過 5 次點擊。

### Phase 2D：穩定性

1. 批次取消。
2. 大量設備（200+）的查詢分頁與前端效能。
3. 資料庫備份說明文件。
4. 前端 bundle 分割（路由級 lazy import）。

## 15. 風險與對策

| 風險 | 影響 | 對策 |
|---|---|---|
| 批次執行中服務被關閉 | 批次永遠停在 `running` | 啟動時將 `running` 批次標記為 `failed`（`error_message="interrupted by shutdown"`） |
| SQLite 長期增長 | 磁碟空間、查詢變慢 | 索引設計（7.2）+ Phase 2D 提供批次清理；文件說明備份方式 |
| 設定快照使批次資料量變大 | 每批次重複保存完整設定 | 第一階段接受（案場設備量通常 < 數百台）；日後可用 snapshot 雜湊去重 |
| 前端輪詢頻率過高 | 後端負載 | 批次查詢間隔 ≥ 1 秒；批次完成後停止輪詢 |
| 診斷建議被當成確定根因 | 誤導現場判斷 | 文案規範（4.4）+ 測試檢查文案不含斷言式字眼 |

## 16. 維護規範補充

在 [INITIAL_DEVELOPMENT.md](INITIAL_DEVELOPMENT.md) 第 14 節基礎上增加：

- 新增領域模型欄位時，同步檢查：SQLite JSON 欄位相容性、前端型別、報告樣板。
- Repository 介面變更時，必須同步更新契約測試，並確認所有實作通過。
- 比較規則順序變更屬於行為變更，需在文件與更新說明中標註。
- 報告樣板修改後，以固定測試資料產生報告並人工檢視一次。
- 新增 migration 後，必須驗證從空資料庫與從上一版資料庫兩種路徑都能啟動。
