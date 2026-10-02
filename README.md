# Modbus Poll Checker

Modbus Poll Checker 是一套執行於本機的案場設備檢查工具，用來管理多台設備連線設定、執行即時檢查、持續輪詢設備狀態，以及保存回歸測試批次與比較基準。

每台設備可選擇不同的檢查流程：

- **Ping**：只確認設備是否可透過 ICMP 回應。
- **Ping + TCP**：確認 Ping 與指定 TCP Port 是否可連線。
- **完整檢查**：依序執行 Ping、TCP Port 與 Modbus TCP 讀取。

本專案直接使用 Python 的 Modbus TCP client 連線設備，不依賴 Modbus Poll 桌面程式。Modbus Poll 可保留作為單台設備的人工交叉驗證工具。

## 功能

- 管理案場名稱與設備連線設定
- 每台設備可設定檢查流程（Ping、Ping + TCP、完整檢查）
- 支援 Modbus TCP 功能碼 `01`、`02`、`03`、`04`
- 設定 IP、Port、Unit ID、位址、讀取數量與逾時
- **設備檢查**分頁：即時檢查單台或全部設備，不寫入歷史
- 顯示 Ping、封包遺失、TCP Port、失敗階段、Modbus 與總狀態
- 顯示診斷摘要與建議（例如 Ping 未回應但 TCP 可連線）
- 啟用自動定時檢查並即時更新設備狀態
- 儲存、讀取與清空案場設定
- **回歸測試**分頁：保存設備檢查批次與批次備註
- 顯示進度、通過率、平均回應時間、最慢設備與異常診斷
- 設定檢查批次為比較基準，查看新增異常、恢復、數值變更與延遲劣化
- 取消進行中的批次
- 刪除歷史批次與清除案場基準
- 匯出 CSV 或 HTML 檢查報告
- 透過 SQLite 保存檢查歷史

## 系統需求

- Windows 10 或更新版本
- Python 3.10 或更新版本
- Node.js 18 或更新版本
- pnpm，或可替代使用 npm
- 可連線至待檢查的設備

## 快速開始

### 1. 安裝前端依賴

在專案根目錄執行：

```powershell
cd frontend
pnpm install
```

若沒有 pnpm，也可以使用：

```powershell
npm install
```

### 2. 啟動服務

回到專案根目錄，執行：

```powershell
start.bat
```

批次檔會開啟兩個 PowerShell 視窗：

- Backend：<http://127.0.0.1:8000>
- Frontend：<http://127.0.0.1:5173>

開啟 <http://127.0.0.1:5173> 使用工具。

首次啟動時，`start.bat` 會檢查並安裝 backend Python 依賴；前端依賴仍需先在 `frontend` 目錄安裝完成。

## Windows 發布包

在開發電腦上安裝 Python 3.10 或更新版本、Node.js 22 LTS，並確保網路可下載套件。於專案根目錄執行：

```powershell
build_release.bat
```

建置完成後，發布檔會產生於 `artifacts/ModbusPollChecker-windows-x64.zip`。將 ZIP 分享給同事；同事解壓後執行裡面的 `start_release.bat`，不需要安裝 Python、Node.js 或專案套件。啟動器會選擇 `8000` 至 `8010` 間可用的本機連接埠並開啟瀏覽器。

案場設定與檢查歷史會保存在解壓目錄內的 `data/` 和 `backend/data/`；更新程式時請先備份這兩個資料夾。發布包不會包含開發電腦上的案場設定或歷史資料。

## 手動啟動

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend 啟動後可透過以下網址查看 FastAPI 文件：

- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

### Frontend

另開一個 PowerShell：

```powershell
cd frontend
pnpm run dev -- --host 127.0.0.1
```

Vite 會將 `/api` 請求代理到 `http://127.0.0.1:8000`。

## 使用流程

### 設備檢查（即時）

1. 開啟前端頁面，預設停在「設備檢查」分頁。
2. 在「新增設備」中填入名稱、檢查流程、IP 與相關設定。
3. 儲存連線設定後，可對單台設備按「重測」，或按「開始設備檢查」檢查所有啟用設備。
4. 需要持續監看時開啟「自動定時檢查」。
5. 檢查結果只顯示在畫面上，**不會寫入歷史**。

### 回歸測試（保存紀錄）

1. 切換到「回歸測試」分頁。
2. 按「開始回歸檢查」，依每台設備的預設流程執行並保存批次。
3. 檢查完成後，可將合格批次設為「基準」。
4. 後續批次可使用「比較基準」查看狀態變化與優先處理異常。
5. 可從批次列表下載 CSV 或 HTML 報告。

> 需要保留紀錄與基準比較時使用「回歸測試」；只想即時查看目前狀態時使用「設備檢查」。

## 設備設定

設備設定會以案場 JSON 保存，範例位置為 `data/家泰家悅.json`。測試或初始設備清單位於 `config/devices.csv`。

主要欄位如下：

| 欄位 | 說明 |
| --- | --- |
| `name` | 設備名稱，需唯一 |
| `check_profile` | 檢查流程：`ping`、`ping_tcp` 或 `full_stack` |
| `ip` | 設備 IP |
| `port` | Modbus TCP Port，通常為 `502`（完整檢查使用） |
| `tcp_port` | Ping + TCP 檢查的目標 TCP Port（`ping_tcp` 必填） |
| `unit_id` | Modbus Unit ID |
| `address` | 內部協定位址，從 `0` 起算 |
| `quantity` | 讀取數量 |
| `function` | `01`、`02`、`03` 或 `04` |
| `expected` | 選填的預期值或範圍 |
| `address_mode` | `dec` 或 `hex` |
| `connect_timeout_ms` | TCP 連線逾時 |
| `response_timeout_ms` | Modbus 回應逾時 |
| `scan_rate_ms` | 自動輪詢週期；`0` 使用預設週期 |
| `delay_between_polls_ms` | 設備間輪詢延遲 |
| `enabled` | 是否納入檢查與輪詢 |
| `ping_enabled` | 是否執行 Ping |
| `ping_attempts` | Ping 嘗試次數 |
| `ping_timeout_ms` | 單次 Ping 逾時 |
| `ping_interval_ms` | Ping 嘗試間隔 |
| `tcp_check_enabled` | 是否執行 TCP Port 檢查 |
| `tcp_timeout_ms` | TCP 連線逾時 |
| `skip_when_ping_failed` | Ping 失敗時是否略過後續階段 |
| `max_latency_ms` | 選填的延遲門檻 |
| `max_loss_percent` | 選填的封包遺失門檻 |

畫面會將功能碼 `03` 的內部位址 `0` 顯示為常見的 PLC 位址 `40001`。不同設備的位址規則可能不同，請依設備手冊確認。

## 資料與報告

- 案場設定：`data/*.json`
- 批次歷史：backend 使用 SQLite 保存，預設資料庫位於 `backend/data/`
- 初始設備清單：`config/devices.csv`
- API 結果與報告：由 backend API 依批次 ID 產生

請勿將現場真實 IP、帳號、密碼或其他敏感資訊提交至版本控制。修改設備設定前，建議先備份 `data/` 內的案場 JSON。

## 測試與品質檢查

### Backend 測試

```powershell
cd backend
python -m unittest discover -s tests
```

### Frontend lint

```powershell
cd frontend
pnpm run lint
```

### Frontend production build

```powershell
cd frontend
pnpm run build
```

目前 build 可能顯示 JavaScript bundle 大小警告；這是已知的前端 code splitting 待辦，不會阻止 build 完成。

## 專案結構

```text
modbusPollChecker/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI 路由與啟動入口
│   │   ├── schemas.py                 # API 與領域資料模型
│   │   ├── check_service.py           # Modbus 檢查服務
│   │   ├── modbus_adapter.py          # Modbus TCP 連線實作
│   │   ├── network_adapter.py         # Ping 與 TCP Port 探測
│   │   ├── site_store.py              # 案場設定保存
│   │   ├── domain/                    # 檢查流程、診斷、健康摘要與領域模型
│   │   ├── ports/                     # 檢查、歷史與報告的介面定義
│   │   ├── services/                  # 批次、比較、趨勢與報告服務
│   │   ├── repositories/              # SQLite 歷史儲存與 migrations
│   │   └── renderers/                 # CSV 與 HTML 報告產生
│   ├── tests/                         # backend 單元與 API 測試
│   └── requirements.txt
├── config/
│   └── devices.csv                    # 初始設備清單
├── data/
│   └── *.json                         # 案場設定檔
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # 頁面狀態協調與模組組合
│   │   ├── components/                # NetworkPanel、DeviceRegressionPanel、DeviceEditor 等 UI
│   │   └── api/client.ts              # frontend API client
│   └── package.json
├── docs/                              # 開發與規格文件
└── start.bat                          # Windows 一鍵啟動
```

## 架構概覽

```text
React + Ant Design
        │
        │ /api proxy
        ▼
FastAPI
        │
        ├── Device check service
        ├── Network adapter (Ping / TCP) ─── 現場設備
        ├── Modbus TCP adapter ───────────── 現場設備
        ├── Site configuration store
        └── SQLite history repository
```

前端負責操作介面與狀態呈現，backend 負責設備通訊、批次執行、歷史保存、基準比較與報告產生。批次執行中的設備結果會持續保存，服務重新啟動後可由歷史資料恢復批次狀態。

## 主要 API

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| `POST` | `/api/device-checks/{device_name}` | 依設備檢查流程執行即時檢查（不寫入歷史） |
| `POST` | `/api/device-checks/batches` | 建立設備檢查批次（回歸測試） |
| `GET` | `/api/device-checks/batches` | 列出設備檢查批次 |
| `GET` | `/api/device-checks/batches/{batch_id}` | 取得批次結果與比較 |
| `POST` | `/api/device-checks/batches/{batch_id}/cancel` | 取消批次 |
| `DELETE` | `/api/device-checks/batches/{batch_id}` | 刪除批次 |
| `GET` | `/api/device-checks/baseline` | 取得案場基準 |
| `PUT` | `/api/device-checks/baseline` | 設定案場基準 |
| `DELETE` | `/api/device-checks/baseline` | 清除案場基準 |
| `GET` | `/api/device-checks/batches/{batch_id}/comparison` | 比較批次與基準 |
| `GET` | `/api/device-checks/batches/{batch_id}/report` | 匯出 CSV 或 HTML 報告 |

## 開發注意事項

- 修改 backend API 後，請同步確認 `frontend/src/api/client.ts` 與畫面使用方式。
- 修改資料模型或 SQLite schema 時，需補上 migration 與回歸測試。
- 批次刪除不可刪除進行中的批次，也不可直接刪除目前基準批次；請先清除基準。
- 變更 UI 元件後至少執行 `pnpm run lint` 與 `pnpm run build`。
- 不要把前端 bundle splitting、無關格式化或大型重構混入設備通訊功能修改。

## 相關文件

- [開發文件](docs/DEVELOPMENT.md)
- [初始開發記錄](docs/INITIAL_DEVELOPMENT.md)
- [設備檢查重構規格](docs/DEVICE_CHECK_REFACTOR_SPEC.md)
- [Backend requirements](backend/requirements.txt)
- [Frontend package](frontend/package.json)
