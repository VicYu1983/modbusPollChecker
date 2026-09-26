# Modbus Poll Checker

Modbus Poll Checker 是一套執行於本機的 Modbus TCP 案場檢查工具，用來管理多台設備連線設定、執行單台或全案場檢查、持續輪詢設備狀態，以及保存回歸測試批次與比較基準。

本專案直接使用 Python 的 Modbus TCP client 連線設備，不依賴 Modbus Poll 桌面程式。Modbus Poll 可保留作為單台設備的人工交叉驗證工具。

## 功能

- 管理案場名稱與設備連線設定
- 支援 Modbus TCP 功能碼 `01`、`02`、`03`、`04`
- 設定 IP、Port、Unit ID、位址、讀取數量與逾時
- 執行單台或全部設備檢查
- 顯示 `PASS`、`FAIL`、`TIMEOUT`、`CONFIG_ERROR` 狀態
- 啟用自動輪詢並即時更新設備狀態
- 儲存、讀取與清空案場設定
- 保存回歸檢查批次與批次備註
- 顯示進度、通過率、平均回應時間、最慢設備與異常診斷
- 設定檢查批次為比較基準，查看新增異常、恢復與數值變更
- 取消進行中的批次
- 刪除歷史批次與清除案場基準
- 匯出 CSV 或 HTML 檢查報告
- 透過 SQLite 保存檢查歷史

## 系統需求

- Windows 10 或更新版本
- Python 3.10 或更新版本
- Node.js 18 或更新版本
- pnpm，或可替代使用 npm
- 可連線至待檢查的 Modbus TCP 設備

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

1. 開啟前端頁面。
2. 在「連線狀況」中新增設備，填入 IP、Port、Unit ID、功能碼與讀取設定。
3. 儲存連線設定後執行單台檢查，或使用「全部檢查」檢查所有啟用設備。
4. 需要持續監看時開啟自動輪詢。
5. 在「回歸測試」輸入批次備註並開始完整檢查。
6. 檢查完成後，可將合格批次設為案場基準。
7. 後續批次可使用「比較基準」查看狀態變化與優先處理異常。
8. 從批次歷史下載 CSV 或 HTML 報告。

## 設備設定

設備設定會以案場 JSON 保存，範例位置為 `data/家泰家悅.json`。測試或初始設備清單位於 `config/devices.csv`。

主要欄位如下：

| 欄位 | 說明 |
| --- | --- |
| `name` | 設備名稱，需唯一 |
| `ip` | Modbus TCP 設備 IP |
| `port` | TCP Port，通常為 `502` |
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
│   │   ├── main.py              # FastAPI 路由與啟動入口
│   │   ├── check_service.py     # 單台與批次檢查服務
│   │   ├── modbus_adapter.py    # Modbus TCP 連線實作
│   │   ├── schemas.py            # API 與領域資料模型
│   │   └── site_store.py         # 案場設定保存
│   ├── tests/                    # backend 單元與 API 測試
│   └── requirements.txt
├── config/
│   └── devices.csv              # 初始設備清單
├── data/
│   └── *.json                   # 案場設定檔
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 頁面狀態協調與模組組合
│   │   ├── components/          # SiteHeader、DeviceTable、DeviceEditor 等 UI
│   │   └── api/client.ts         # frontend API client
│   └── package.json
├── docs/
│   ├── DEVELOPMENT.md           # 原始需求與技術方向
│   └── INITIAL_DEVELOPMENT.md   # 初始開發記錄
└── start.bat                    # Windows 一鍵啟動
```

## 架構概覽

```text
React + Ant Design
        │
        │ /api proxy
        ▼
FastAPI
        │
        ├── Check service
        ├── Modbus TCP adapter ─── 現場設備
        ├── Site configuration store
        └── SQLite history repository
```

前端負責操作介面與狀態呈現，backend 負責設備通訊、批次執行、歷史保存、基準比較與報告產生。批次執行中的設備結果會持續保存，服務重新啟動後可由歷史資料恢復批次狀態。

## 開發注意事項

- 修改 backend API 後，請同步確認 `frontend/src/api/client.ts` 與畫面使用方式。
- 修改資料模型或 SQLite schema 時，需補上 migration 與回歸測試。
- 批次刪除不可刪除進行中的批次，也不可直接刪除目前基準批次；請先清除基準。
- 變更 UI 元件後至少執行 `pnpm run lint` 與 `pnpm run build`。
- 不要把前端 bundle splitting、無關格式化或大型重構混入設備通訊功能修改。

## 相關文件

- [開發文件](docs/DEVELOPMENT.md)
- [初始開發記錄](docs/INITIAL_DEVELOPMENT.md)
- [Backend requirements](backend/requirements.txt)
- [Frontend package](frontend/package.json)
