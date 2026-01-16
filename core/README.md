# OpenAver Core 模組說明

本目錄 (`core/`) 包含 OpenAver 的核心邏輯與後端功能實作。以下是各檔案的功能說明：

## 核心功能

### `scraper.py`
**影片資訊爬蟲**
- 負責從各大網站（JavBus, JavDB, Jav321, DMM 等）搜尋與抓取影片元數據。
- 實作了多來源整合搜尋 `search_jav()`。
- 包含處理 JavDB 與 JavBus 爬取邏輯。
- 維護片商對照表 (`maker_mapping.json`) 的載入與更新。

### `gallery_generator.py`
**HTML 畫廊生成器**
- 負責將影片列表 (`VideoInfo`) 生成為單一的靜態 HTML 檔案。
- 包含完整的現代化前端介面邏輯（Vue-like 的原生 JS 實作）。
- 支援多種檢視模式（詳細列表、圖片卡片、文字列表）。
- 內建搜尋、排序、分頁、主題切換（深色/淺色）與 Lightbox 功能。

### `gallery_scanner.py`
**檔案掃描與解析**
- 負責掃描本地資料夾，識別影片檔案與 NFO 檔案。
- 定義了核心資料結構 `VideoInfo`。
- 實作了高效的目錄掃描邏輯（支援快取）。
- 包含檔名解析邏輯，能從檔名中提取番號、片名等資訊。
- 支援從 NFO 讀取既有的影片資訊。

### `organizer.py`
**檔案整理工具**
- 負責影片檔案的整理、重命名與移動。
- 支援自訂資料夾與檔名格式。
- 自動下載封面圖片與生成 NFO 檔案。
- 包含中文片名提取邏輯（從檔名中智慧識別中文標題）。

## 輔助服務

### `search_gallery_service.py`
**搜尋結果展示服務**
- 連接 `scraper` 與 `gallery_generator` 的橋樑。
- 將網路搜尋結果轉換為 Gallery HTML 格式以便在前端展示。
- 實作「女優卡 (Hero Card)」邏輯：當搜尋結果主要集中在某位女優時，自動抓取並置頂顯示該女優的個人資料。

### `actress_scraper.py`
**女優資料爬蟲**
- 負責從 JavBus 抓取女優的詳細個人資料（身高、三圍、生日等）。
- 用於 `search_gallery_service.py` 生成女優卡。

### `nfo_updater.py`
**NFO 批次更新器**
- 檢查現有影片的 NFO 檔案是否缺少關鍵欄位（如片商、演員）。
- 自動調用 `scraper` 補全缺失的元數據並回寫 NFO。
- 支援 SSE (Server-Sent Events) 進度串流回報。

## 工具函式

### `path_utils.py`
**跨平台路徑處理**
- 解決 Windows、WSL (Windows Subsystem for Linux)、Linux 與 macOS 之間的路徑格式差異。
- 支援將 WSL 路徑轉換為 Windows 可讀取的 `file:///` 格式，確保在 Windows 瀏覽器中能直接開啟本地檔案。
