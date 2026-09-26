# Modbus Poll Checker 開發文件

## 1. 目的

建立一個可以讀取設備清單，逐一或並行檢查多個 Modbus TCP 設備的工具，並輸出每台設備的連線與暫存器檢查結果。

本文件先定義需求與技術方向，不包含實作程式碼。

## 2. 核心問題：能否透過 Modbus Poll 同時檢查多個 IP？

可以做到「批量檢查」，但不應先假設單一個 Modbus Poll 視窗就能同時管理多個 IP。

一般 Modbus Poll 的操作模式是一個工作階段連接一個 Modbus Server。要利用既有的 Modbus Poll 完成多 IP 檢查，必須先確認目前版本是否支援以下其中一種方式：

1. 由命令列指定 IP、Port、Slave ID、暫存器與讀取設定，並可由外部程式啟動多個實例。
2. 透過 DDE、Automation、COM 或其他外部控制介面讀取結果。
3. 允許同時執行多個 Modbus Poll 實例，且授權條款允許此使用方式。
4. 能夠匯出結果或提供可被工具解析的日誌檔案。

若上述介面不存在，Modbus Poll 比較適合用來人工確認單台設備，不適合作為批量檢測工具的執行核心。此時建議由本工具直接使用 Modbus TCP 函式庫連線多個 IP，而不是模擬操作 Modbus Poll。

## 3. 建議方案

### 第一階段：確認 Modbus Poll 整合能力

先做一個小型可行性驗證，不開發完整工具：

- 查閱目前 Modbus Poll 版本的說明文件，確認命令列、DDE/Automation、匯出與多實例支援。
- 手動建立兩個不同 IP 的連線設定，確認能否同時執行。
- 確認每個實例是否可以被識別、啟動、停止及取得成功或失敗結果。
- 確認授權是否允許自動化啟動多個實例。

驗證結果若為「可可靠控制並取得結果」，工具可以採用 Modbus Poll Adapter；否則直接採用 Modbus TCP Client Adapter。

### 第二階段：建立批量檢測工具

工具本身應該以 Adapter 抽象連線方式：

```text
設備清單 -> 檢測排程器 -> Modbus Poll Adapter 或 Modbus TCP Adapter
                         -> 統一結果模型 -> 輸出報告
```

這樣可以先支援直接 Modbus TCP 檢查，日後若確認 Modbus Poll 可自動化，再加入 Modbus Poll Adapter，不必重寫清單、排程與報告功能。

## 4. 設備清單格式

建議使用 CSV 或 JSON。CSV 適合編輯單一設備清單；JSON 作為完整案場設定檔，方便在不同案場之間匯入與匯出。

### CSV 欄位

| 欄位 | 必填 | 說明 | 範例 |
|---|---|---|---|
| `name` | 是 | 設備名稱 | `Pump-01` |
| `ip` | 是 | Modbus TCP IP | `192.168.1.101` |
| `port` | 否 | TCP Port，預設 502 | `502` |
| `unit_id` | 是 | Modbus Unit ID | `1` |
| `address` | 是 | 協定使用的起始位址；Modbus Poll 的 `0` 對應 PLC 位址 `40001` | `0` |
| `quantity` | 是 | 讀取數量 | `2` |
| `function` | 是 | 功能碼，例如 `03` 或 `04` | `03` |
| `expected` | 否 | 預期值或範圍 | `0..100` |
| `address_mode` | 否 | 位址輸入格式，`dec` 或 `hex`，預設為 `dec` | `dec` |
| `connect_timeout_ms` | 否 | 建立 TCP 連線逾時 | `3000` |
| `response_timeout_ms` | 否 | 等待 Modbus 回應逾時 | `1000` |
| `scan_rate_ms` | 否 | 自動輪詢週期；預設為 `1000 ms`。`0` 使用自動輪詢預設週期 | `1000` |
| `delay_between_polls_ms` | 否 | 同一設備兩次輪詢之間的延遲 | `20` |
| `enabled` | 否 | 是否啟用，預設為 `true` | `true` |

範例：

```csv
name,ip,port,unit_id,address,quantity,function,expected,address_mode,connect_timeout_ms,response_timeout_ms,scan_rate_ms,delay_between_polls_ms,enabled
Pump-01,192.168.1.101,502,1,0,2,03,0..100,dec,3000,1000,1000,20,true
Pump-02,192.168.1.102,502,1,0,2,03,0..100,dec,3000,1000,1000,20,true
Meter-01,192.168.1.103,502,3,0,4,,dec,3000,1000,0,20,true
```

注意：不同設備對位址格式可能使用 `0` 起算、`1` 起算或 `40001` 類型表示法。工具內部統一使用協定位址，並在畫面上另外顯示 PLC 位址，例如功能碼 `03` 的內部位址 `0` 顯示為 `40001`。不能只依名稱猜測位址轉換規則。

### JSON 案場設定檔

JSON 檔案以案場為單位保存設定，至少包含格式版本、案場名稱與設備清單。匯出時應匯出目前案場的完整連線設定，不包含即時連線狀態、檢查結果或暫存的錯誤訊息。

範例：

```json
{
    "schema_version": 1,
    "site_name": "案場 A",
    "devices": [
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
    ]
}
```

匯入 JSON 時必須依 `schema_version` 驗證格式，並逐筆驗證 IP、Port、Unit ID、功能碼、位址、數量、逾時與輪詢設定。驗證全部通過後，才以匯入內容取代目前案場設定；驗證失敗時不得套用部分內容，並須列出具體錯誤欄位。匯入完成後，設備應出現在「連線狀態」區域，但不應在未經使用者確認前自動對所有設備發起輪詢。

## 5. 檢測流程

1. 載入並驗證清單格式。
2. 過濾 `enabled=false` 的項目。
3. 對每台設備建立 TCP 連線，使用設定的 Port、Unit ID 與連線逾時。
4. 發送指定功能碼與讀取範圍，使用獨立的回應逾時。
5. 驗證回應的 Modbus Exception、資料長度與預期值。
6. 記錄結果：成功、連線失敗、逾時、協定錯誤、資料不符合預期或設定錯誤。
7. 自動檢查時，若 `scan_rate_ms` 大於 `0`，依設定週期輪詢；若為 `0`，使用預設 `1000 ms` 週期。
8. 輸出畫面摘要及 CSV/JSON 報告。

多台設備可以並行檢查，但必須設定最大並行數，例如預設 10 台，避免網路、設備或電腦資源被一次耗盡。

## 6. 結果格式

每筆結果至少包含：

- 檢測時間
- 設備名稱、IP、Port、Unit ID
- 使用的功能碼、位址與數量
- 狀態：`PASS`、`FAIL`、`TIMEOUT`、`CONFIG_ERROR`
- 實際回應值
- 錯誤類型與錯誤訊息
- 連線耗時

工具的退出碼建議如下：

- `0`：所有啟用設備檢查成功
- `1`：至少一台設備檢查失敗
- `2`：清單或設定格式錯誤
- `3`：工具執行錯誤

## 7. Modbus Poll 整合模式

若可行性驗證通過，整合層應負責：

- 將設備設定轉換成 Modbus Poll 所需格式。
- 每台設備啟動一個工作階段或實例。
- 設定啟動逾時、檢測逾時與強制關閉逾時。
- 解析 Modbus Poll 的輸出結果。
- 將輸出統一轉換成第 6 節的結果格式。
- 防止殘留程序，並在工具結束時清理子程序。

若 Modbus Poll 只能被人工操作，則不採用此模式，改用直接 Modbus TCP Adapter。這不影響使用者繼續用 Modbus Poll 做單台設備的人工交叉驗證。

## 8. 錯誤處理與安全限制

- 預設只允許連線到清單中的 IP，不接受任意未驗證的輸入。
- 對 IP、Port、Unit ID、功能碼、位址和數量做範圍驗證。
- 每台設備的重試次數可設定，預設最多 1 次，避免設備被大量輪詢。
- 連線逾時和讀取逾時必須分開記錄。
- 不在日誌中記錄不必要的密碼或敏感設定。
- 讀取工具第一版只允許讀取功能碼，禁止寫入線圈或暫存器。

## 9. MVP 範圍

第一版只包含：

- CSV 設備清單。
- Modbus TCP。
- 功能碼 `03`、`04`。
- 單次讀取檢查。
- 可設定最大並行數、逾時與重試次數。
- HTML 操作頁面。
- 頁面提供連線狀態與新增連線兩個主要區域。
- 支援以 JSON 匯入與匯出完整案場設定。
- 終端機摘要與 CSV/JSON 結果檔。
- 直接 Modbus TCP Adapter。

第一版不包含：

- 寫入設備資料。
- 自動修改設備設定。
- 長時間監控與告警平台。
- 依賴畫面辨識操作 Modbus Poll。
- 未確認授權前的多實例自動化。

## 10. HTML 操作頁面

第一版需要提供一個簡單、容易理解的 HTML 頁面，頁面分成兩個主要區域：

### 10.1 連線狀態

顯示目前已建立或已儲存的每條 Modbus TCP 連線，讓使用者可以快速判斷設備是否正常。

每筆連線至少顯示：

- 設備名稱。
- IP 位址與 Port。
- Unit ID。
- 目前狀態：連線中、正常、失敗、逾時或未檢查。
- 最近一次檢查時間。
- 最近一次錯誤訊息或讀取結果。
- 連線耗時。

此區域應提供：

- 手動重新檢查單一設備。
- 手動重新檢查全部設備。
- 匯入案場 JSON 設定。
- 匯出目前案場 JSON 設定。
- 清楚的成功、警告與失敗視覺狀態。
- 新增或修改連線後即時更新狀態。

### 10.2 新增連線

提供表單讓使用者新增一條 Modbus TCP 連線。表單欄位至少包含：

- 設備名稱。
- IP 位址。
- Port，預設為 `502`。
- Unit ID。
- 功能碼，第一版支援 `03` 與 `04`。
- 起始暫存器位址。
- 讀取數量。
- 預期值或範圍，可選填。
- 位址輸入格式：十進位或十六進位，預設為十進位。
- 連線逾時，預設 `3000 ms`。
- 回應逾時，預設 `1000 ms`。
- 輪詢週期，預設 `1000 ms`；自動檢查時 `0` 會使用預設週期。
- 輪詢間隔延遲，預設 `20 ms`。
- 是否啟用。

送出表單時必須先驗證 IP、Port、Unit ID、功能碼、位址、數量、逾時與輪詢週期範圍；驗證成功後才儲存設定並執行檢查。新增成功後，該連線應出現在「連線狀態」區域。驗證失敗時，欄位旁應顯示可理解的錯誤訊息，不應只顯示程式例外。畫面應同時顯示協定位址與 PLC 顯示位址，避免使用者把 `0` 與 `40001` 誤認為不同暫存器。

匯入與匯出操作應以檔案選擇器及下載功能完成，並顯示目前案場名稱。匯入前應提供預覽或確認，避免誤套用其他案場設定；匯出檔名建議包含案場名稱，例如 `site-a-config.json`。

頁面不提供寫入線圈或暫存器的功能，並且不接受未經驗證的任意連線請求。HTML 頁面可由 Python 提供本機 HTTP 服務，後端沿用既有的設備清單、檢測流程與統一結果格式。

## 11. 待確認事項

開發前需要確認：

1. Modbus Poll 的完整版本與授權類型。
2. 目標設備使用 Modbus TCP 還是需要 Modbus RTU over TCP。
3. 每台設備的 IP、Port、Unit ID、功能碼和位址規則。
4. 檢查是只判斷能否連線，還是必須驗證暫存器內容。
5. 預計同時檢查的設備數量。
6. 執行環境是 Windows 桌面、排程工作還是伺服器。
7. 結果需要保存多久，以及是否需要 Excel 可直接開啟的格式。

## 12. 結論

可以先定義一份 IP 與讀取規則清單，再批量檢查多台設備；但「透過 Modbus Poll」能否自動完成，取決於目前版本提供的外部控制能力與授權。建議先驗證 Modbus Poll 的自動化介面，同時將工具設計成可替換 Adapter。若 Modbus Poll 沒有穩定的批量控制方式，就由工具直接使用 Modbus TCP 連線，這會比啟動多個 GUI 實例更穩定、容易記錄結果，也更適合後續排程執行。

## 13. Modbus 通訊套件選擇

不需要自行實作 Modbus TCP 封包，也不需要依賴 Modbus Poll。通訊套件通常已經處理以下工作：

- 建立與關閉 TCP 連線。
- 發送 Modbus 功能碼請求。
- 解析正常回應與 Modbus Exception。
- 設定連線逾時與讀取逾時。
- 將暫存器資料轉成整數或位元組資料。

### 可選套件

| 開發語言 | 套件 | 適合情境 |
|---|---|---|
| Python | `pymodbus` | 快速開發、批量檢查、排程工具與報告輸出；優先推薦 |
| .NET / C# | `NModbus` | Windows 桌面工具、服務或需要正式安裝程式的情境 |
| Node.js | `modbus-serial` | 已有 JavaScript/TypeScript 後端或 Web 控制介面 |
| Go | `github.com/goburrow/modbus` | 單一執行檔、長時間執行服務與部署簡單 |

### 初步建議

若目前沒有既定技術棧，第一版建議使用 Python 與 `pymodbus`：

1. 以 CSV/JSON 載入設備清單。
2. 每台設備建立獨立的 Modbus TCP Client。
3. 使用非同步工作或受控的執行緒池並行檢查多個 IP。
4. 將所有例外轉換成統一的 `PASS`、`FAIL`、`TIMEOUT` 和 `CONFIG_ERROR` 結果。
5. 輸出終端機摘要、CSV 與 JSON 報告。

這個方案會把 Modbus Poll 保留為人工交叉驗證工具，而不是正式檢查流程的依賴。選定套件後，仍需用實際設備確認位址格式、Unit ID、功能碼、資料型別與逾時行為。

## 14. Web 技術決策

本專案採用「React + TypeScript + Ant Design + Python」，不使用 Node.js 作為 Modbus 後端。

### 前端

- 使用 React 與 TypeScript 建立頁面。
- 使用 Ant Design 提供表單、表格、通知、狀態標籤與匯入匯出操作元件。
- 顯示連線狀態、設備清單與檢查結果。
- 提供新增、修改與刪除連線。
- 提供案場 JSON 設定檔匯入與匯出。
- 透過 HTTP API 呼叫 Python 後端，不直接連線 Modbus TCP。

### 後端

- 使用 Python 提供本機 HTTP API。
- 沿用 `pymodbus` 建立 Modbus TCP 連線與讀取資料。
- 負責 JSON/CSV 設定檔驗證與儲存。
- 負責執行單次檢查、持續輪詢與並行檢查。
- 將檢查結果轉換成前端使用的統一 JSON 格式。

### 連線方式

```text
瀏覽器 React + TypeScript + Ant Design
          -> HTTP API
Python Web Server + pymodbus
          -> Modbus TCP
現場設備
```

瀏覽器不能直接建立一般 TCP Socket，因此 Modbus TCP 連線必須由 Python 後端執行。React 前端建置後的靜態檔案預計由同一個 Python Web Server 提供，使用者啟動 Python 程式後，以瀏覽器開啟本機網址即可操作。

### 第一版 API 方向

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/site` | 取得目前案場設定與設備清單 |
| `POST` | `/api/site/import` | 匯入並驗證案場 JSON |
| `GET` | `/api/site/export` | 匯出目前案場 JSON |
| `POST` | `/api/devices` | 新增設備連線設定 |
| `PUT` | `/api/devices/{name}` | 修改設備連線設定 |
| `DELETE` | `/api/devices/{name}` | 刪除設備連線設定 |
| `POST` | `/api/check` | 執行單台或全部設備檢查 |
| `GET` | `/api/status` | 取得目前連線狀態與最近結果 |