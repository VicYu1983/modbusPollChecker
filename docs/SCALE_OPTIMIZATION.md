# 大量設備檢查效能優化工程文件

## 1. 背景

案場設備規模從數十台成長至約 460 台（本次對講機批次匯入後），未來全案場預計達 1,000 台。本文件評估現有檢查機制在此規模下的負載能力，指出瓶頸，並規劃優化工作。

本文件基於 2026-09-29 的程式碼現況分析與需求討論，涉及的主要模組：

- `backend/app/services/network_batch_service.py`（後端批次檢查）
- `backend/app/network_adapter.py`（Ping / TCP adapter）
- `frontend/src/components/NetworkPanel.tsx`（前端即時檢查）
- `backend/app/check_service.py`（Modbus 輪詢）

### 1.1 使用情境與需求

本工具定位為**案場設備連線健康度檢查工具**，主要使用情境：

1. 工程師到達案場後，快速掌握全部設備的連線健康度。
2. 作為案場完成度的匯報依據（初期自用，未來可能提供給主管）。

需求討論結論：

| 項目 | 結論 |
| --- | --- |
| 等待時間 | 不要求立即完成；允許檢查花時間，但**UI 需逐步顯示已檢查結果**（漸進更新）。 |
| 自動檢查 | 原本構想每 5 秒一輪；460 台規模下不適用。改為**每 10 分鐘一輪**，且**僅限 Ping / TCP 設備**。 |
| Modbus 檢查 | 案場部分 Modbus 模組僅允許 1–2 個同時連線，自動連線可能干擾現場運作。**一律手動觸發**（見第 4.3 節）。 |
| 匯報報告 | 暫緩。優先「把工具做到好用、會繼續用」，報告功能往後排。 |

## 2. 現況分析

### 2.1 後端批次檢查（回歸測試路徑）— 可負擔

`NetworkBatchService` 的設計適合大量設備：

| 項目 | 實作 | 評估 |
| --- | --- | --- |
| 併發控制 | `asyncio.Semaphore(batch.max_concurrency)`，上限 50、預設 20 | ✅ |
| Ping | `asyncio.create_subprocess_exec`，非同步、不阻塞事件迴圈 | ✅ |
| 取消 | `cancel_event` + active task 集合，可中途取消 | ✅ |
| 歷史寫入 | SQLite 逐筆 insert | ⚠️ 見 2.4 |
| 錯誤隔離 | 單台失敗轉為 `UNKNOWN` 結果，不中斷批次 | ✅ |

**時間估算**（`ping` profile、`ping_attempts=4`、`ping_timeout_ms=1000`）：

- 單台最壞情況（離線）：4 次 ping × (1s timeout + 2s `wait_for` buffer) ≈ 12 秒
- 460 台全離線、併發 20：460 / 20 × 12s ≈ **4.6 分鐘**
- 460 台全離線、併發 50：≈ **1.8 分鐘**
- 1,000 台全離線、併發 50：≈ **4 分鐘**
- 線上設備每次 ping 數十 ms，實務批次多在 1–3 分鐘內完成

結論：後端批次機制在 1,000 台內可負擔，瓶頸不在這裡。

### 2.2 前端即時檢查（檢查結果列表）— 真正的瓶頸

`NetworkPanel.runChecks` 的模式：

```text
前端 worker pool（maxConcurrency，預設 20）
    │
    ├─ 逐台 POST /api/network/check/one   ← 每台一個 HTTP request
    │
    └─ 收集結果更新 singleResults state
```

問題：

- 460 台 = 460 個 HTTP request，全部由瀏覽器發出。
- 全離線情境一輪約 4.6 分鐘，期間分頁不可關閉、重新整理即中斷。
- 沒有取消機制：一但開始，只能等它跑完。
- 1,000 台時 request 數量與時間翻倍，此模式不建議使用。

### 2.3 自動輪詢（autoCheck）— 間隔與範圍皆需調整

`NetworkPanel` 的自動檢查每 `autoIntervalMs`（預設 5000ms）觸發一輪 `runChecks`：

- `runAutoCheck` 有 `autoChecking` 防重入，不會疊加執行。
- 但 460 台一輪需數分鐘，5 秒間隔形同連續不斷地跑，前端與後端都持續滿載。
- 更嚴重的是：autoCheck 目前會涵蓋 `full_stack` 設備，對 Modbus 設備自動建立連線（見 2.6）。
- 1,000 台時此模式完全不可用。

### 2.4 SQLite 歷史與報告

- 每批次每台寫一列：460 台 × 每天 10 批 = 4,600 列/天。SQLite 在百萬列等級前無需遷移。
- 單批 460 筆的 HTML/CSV 報告體積與渲染時間增加，屬可接受範圍，但需驗證前端下載與顯示。

### 2.5 Windows ping 子程序

每台每次 ping spawn 一個 `ping.exe`。併發 50 時同時最多 50 個子程序，Windows 可處理；但多批次並行或併發拉滿時會有短暫程序風暴。建議大量設備併發設 30–50，不超過上限 50。

### 2.6 Modbus 連線限制（安全性議題）

案場部分 Modbus 模組（BA 系統）僅允許 1–2 個同時連線，且平時正被樓控系統持續輪詢。若本工具自動對這些設備建立 Modbus 連線：

- 可能搶佔連線名額，導致樓控系統讀取失敗，**影響現場運作**。
- 或被設備拒絕連線，使檢查結果失真。

此為比效能更重要的**安全性限制**，必須在設計上明確隔離。

## 3. 非目標

- 不更換 SQLite 為其他資料庫（現有寫入量遠未達瓶頸）。
- 不實作分散式或多程序架構（單機 FastAPI 足夠）。
- 不修改 Modbus 輪詢（`check_service.py`）的執行緒模型——`full_stack` 設備數量少（目前 6 台），`ThreadPoolExecutor(max_workers=10)` 足夠。
- 不做前端 bundle splitting（與本主題無關）。
- **不實作匯報報告功能**（分組統計、趨勢圖表）。依需求討論，優先確保工具好用、會被持續使用，報告往後排。
- **不讓 Modbus 檢查進入自動輪詢**（見 4.3）。

## 4. 優化方案

### 4.1 方案 A：前端即時檢查改走批次端點 + 漸進更新（優先級 1）

將 `NetworkPanel` 的「開始設備檢查」從逐台 `POST /api/network/check/one` 改為：

1. 呼叫既有 `POST /api/network/check`（`NetworkBatchCreateRequest`，含 `max_concurrency`）建立批次。
2. 每 2 秒輪詢 `GET /api/network/batches/{batch_id}`，**將已完成的設備結果逐步寫入 `singleResults`**，讓 UI 漸進顯示「已檢查 87/460、正常 80、異常 7」。
3. 直到 `status` 為 `completed` / `failed` / `cancelled`。
4. 提供「取消」按鈕，呼叫既有 `POST /api/network/batches/{batch_id}/cancel`。

優點：

- 後端 Semaphore 統一管理併發，前端只發 1 個建立請求 + 少量輪詢請求。
- **符合需求：允許檢查花時間，但 UI 逐步更新**（後端批次本就逐台寫入 SQLite，輪詢即可取得進度）。
- 分頁可關閉、重新整理後仍可從批次歷史讀回結果。
- 取消機制免費獲得。
- 460 台與 1,000 台行為一致。

實作要點：

- 輪詢間隔 2 秒；`NetworkBatchDetailResponse` 已含每台結果，直接映射。
- 前端保留 `maxConcurrency` 選擇（20–50），傳入 `max_concurrency`。
- 批次進行中停用「開始設備檢查」按鈕，顯示批次進度（已完成 / 總數）。
- 單台重測（表格內的 reload 按鈕）保留原本 `/api/network/check/one`，不受影響。

### 4.2 方案 B：autoCheck 改為「Ping 專用、10 分鐘間隔」（優先級 2）

修訂原本的「加長間隔」構想，改為明確的範圍與頻率限制：

- **範圍限制**：autoCheck 僅涵蓋 `ping` / `ping_tcp` profile 的設備，**排除 `full_stack`**（見 4.3）。
- **間隔調整**：`autoIntervalMs` 選項改為 60s / 300s / 600s（預設 600s）。
- **規模提示**：設備數 > 100 時，自動檢查開關預設關閉，並顯示提示：「設備數量較多，自動檢查僅涵蓋 Ping/TCP 設備，間隔 10 分鐘」。
- autoCheck 內部改為建立批次 + 輪詢，與手動檢查共用路徑（方案 A）。

### 4.3 方案 C：Modbus 檢查安全規則（優先級 2，安全性）

因案場 Modbus 模組連線數受限，訂定以下規則：

1. **Modbus 檢查一律手動觸發**，永不進入 autoCheck。
2. **Modbus 檢查併發固定為 1**（序列執行），不與其他設備並行。`full_stack` 設備目前僅 6 台，序列檢查最多數十秒。
3. **UI 明確警告**：對 `full_stack` 設備執行檢查時，提示「此檢查會與設備建立 Modbus 連線，若設備正被樓控系統使用，可能互相干擾」。
4. 未來若需要，可在設備設定新增「允許自動 Modbus 檢查」開關（預設關）；第一版直接禁止自動即可。

### 4.4 方案 D：報告渲染驗證（優先級 3，低成本確認）

- 以 460 台實際批次產生 HTML 與 CSV 報告，量測渲染時間與檔案大小。
- 若 HTML 報告 > 10 MB 或渲染 > 5 秒，再評估分頁渲染或延遲載入；否則不做。
- 匯報報告（分組統計、趨勢）依需求討論暫緩，不在本文件範圍。

## 5. 檔案變更清單

| 檔案 | 變更 | 方案 |
| --- | --- | --- |
| `frontend/src/components/NetworkPanel.tsx` | `runChecks` 改為建立批次 + 輪詢 + 漸進更新；加入取消按鈕；autoCheck 範圍與間隔調整；Modbus 警告 | A、B、C |
| `frontend/src/api/client.ts` | 確認 `createNetworkCheckBatch`、`getNetworkBatch`、`cancelNetworkBatch` 已存在，缺則補 | A |
| `backend/app/services/network_batch_service.py` | 確認 `full_stack` 可指定併發 1（或前端建立批次時傳入） | C |
| `backend/` | 其餘不變（端點已齊備） | — |
| `docs/` | 本文件 | — |

## 6. 驗證計畫

### 6.1 功能驗證

- [ ] 460 台設備，併發 50，批次完成時間 < 3 分鐘（全離線 < 5 分鐘）。
- [ ] 批次進行中，UI 每 2 秒更新已檢查數量與結果（漸進顯示）。
- [ ] 批次進行中按取消，5 秒內停止且批次狀態為 `cancelled`。
- [ ] 批次進行中重新整理頁面，可從批次歷史讀回結果。
- [ ] 單台重測（表格 reload）仍走 `/api/network/check/one`，正常運作。
- [ ] autoCheck 僅涵蓋 `ping` / `ping_tcp` 設備，`full_stack` 設備不被自動檢查。
- [ ] 對 `full_stack` 設備手動檢查時顯示 Modbus 干擾警告。

### 6.2 負載驗證

- [ ] 批次執行期間，後端程序 ping.exe 同時存在數 ≤ 併發上限。
- [ ] 批次執行期間，API 其他端點（設備 CRUD、歷史查詢）回應正常。
- [ ] SQLite 批次歷史寫入無鎖死；批次完成後歷史查詢正常。
- [ ] Modbus 檢查序列執行，同時僅 1 個 Modbus 連線。

### 6.3 回歸確認

- 既有 `backend/tests/test_network_batch_service.py`、`test_api_network_batches.py` 全數通過（後端未改動，預期不受影響）。

## 7. 里程碑

| 階段 | 內容 | 驗收 |
| --- | --- | --- |
| O1 | 方案 A：前端改走批次端點 + 輪詢 + 漸進更新 + 取消 | 6.1 前五項通過 |
| O2 | 方案 C：Modbus 安全規則（手動限定、併發 1、UI 警告） | 6.1 後兩項、6.2 最後一項通過 |
| O3 | 方案 B：autoCheck 範圍與間隔調整 | 6.1 第六項通過 |
| O4 | 方案 D：460 台報告渲染量測 | 記錄數據，決定是否需進一步處理 |

## 8. 風險與備案

| 風險 | 說明 | 備案 |
| --- | --- | --- |
| 批次輪詢間隔過長 | 使用者感覺結果更新延遲 | 間隔 2 秒起步，必要時降至 1 秒 |
| 後端同時僅允許一個批次 | `NetworkBatchAlreadyRunningError`（409） | 前端收到 409 時提示「已有批次執行中」並顯示該批次狀態 |
| 離線設備拖長批次 | 4 attempts × timeout 全額等待 | 已由併發吸收；必要時提供「快速模式」（attempts=1）選項 |
| ping.exe 程序風暴 | 多來源同時觸發批次 | 後端已有單一批次限制；前端 autoCheck 防護（方案 B）降低觸發頻率 |
| Modbus 干擾現場運作 | 自動連線搶佔樓控系統名額 | 方案 C：Modbus 一律手動、併發 1、UI 警告 |
| 使用者誤以為 autoCheck 涵蓋全部設備 | 自動檢查跳過 `full_stack` 設備 | UI 明確標示 autoCheck 範圍，並在結果列表區分「自動 / 手動」來源 |
