# 案場資料與檢查歷史備份

## 資料位置

- 案場設備設定：專案根目錄的 `data/*.json`。
- 批次、檢查結果與基準：`backend/data/modbus_history.db`。
- SQLite migration：`backend/app/repositories/migrations/`，屬於程式版本檔，不需單獨備份。

案場設定 JSON 與 SQLite 歷史資料分開保存。只備份其中一種，無法同時還原設備設定與檢查歷史。

## 建議備份方式

### 備份案場設定

複製專案根目錄的 `data` 資料夾至安全位置。案場設定可透過應用程式的儲存/讀取操作匯出與還原。

### 備份 SQLite 歷史

SQLite 使用線上備份 API，可在服務執行時建立一致性快照。於專案根目錄執行以下 PowerShell 命令，將備份寫到專案外的資料夾：

```powershell
$backupPath = Join-Path $env:USERPROFILE "Documents\ModbusBackups\modbus_history_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
New-Item -ItemType Directory -Force (Split-Path $backupPath) | Out-Null
Push-Location backend
python -c "import sqlite3; source = sqlite3.connect('data/modbus_history.db'); target = sqlite3.connect(r'$backupPath'); source.backup(target); target.close(); source.close()"
Pop-Location
```

確認輸出檔案存在且大小大於 0，再把同一時間點的案場 JSON 一起備份。備份檔不要存進 `backend/data`，也不要提交到 Git。

若無法使用線上備份 API，先停止後端，再複製資料庫檔；不可在服務仍寫入時直接複製 SQLite 主檔。

## 還原方式

1. 停止後端服務。
2. 將要還原的資料庫複製為 `backend/data/modbus_history.db`。
3. 將對應案場 JSON 放回專案根目錄的 `data` 資料夾。
4. 啟動後端，確認服務正常啟動並完成資料庫 migration。
5. 查詢案場、批次歷史與基準，確認資料完整後再開始新的現場檢查。

還原會覆蓋目前的歷史資料。操作前先把目前資料庫另存一份；不要直接手動修改 SQLite 資料表。

## 建議頻率

在案場驗收、重大線路調整、批次清理或更新程式前建立備份。若歷史資料具有交付或追溯用途，將備份複製到另一個磁碟或受控的公司儲存位置。