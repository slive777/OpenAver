# OpenAver Core 模組說明

本目錄 (`core/`) 包含 OpenAver 的核心邏輯與後端功能實作。以下是各檔案的功能說明：

## 核心功能

### `scraper.py`
**影片資訊爬蟲 Facade**
- 負責調度各來源爬蟲模組（JavBus, JavDB, Jav321, FC2, AVSOX）。
- 實作了多來源整合搜尋 `search_jav()`。
- 維護片商對照表 (`maker_mapping.json`) 的載入與更新。
- 實際爬取邏輯已移至 `scrapers/` 子模組。

### `scrapers/` 子模組
**模組化爬蟲架構** (Phase 16 重構)

```
scrapers/
├── __init__.py         # 統一導出
├── base.py             # BaseScraper 抽象類
├── models.py           # Pydantic 資料模型
├── utils.py            # 共用工具函數
├── javbus.py           # JavBusScraper
├── jav321.py           # JAV321Scraper
├── javdb.py            # JavDBScraper (需 curl_cffi)
├── fc2.py              # FC2Scraper
├── avsox.py            # AVSOXScraper
├── dmm.py              # DMMScraper (GraphQL API + Proxy)
├── d2pass.py           # D2PassScraper (1Pondo/Caribbeancom/10musume)
└── heyzo.py            # HEYZOScraper (JSON-LD + HTML table)
```

#### `scrapers/utils.py`
**共用工具函數** (Phase 17 擴充)
- `extract_number()` - 從檔名提取番號
- `normalize_number()` - 番號格式標準化
- `has_japanese()` - 日文檢測（平假名+片假名）
- `has_chinese()` - 中文檢測
- `check_subtitle()` - 字幕標記偵測
- `format_number()` - 番號格式化
- `SOURCE_ORDER` / `SOURCE_NAMES` - 來源配置常數

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
- 支援自訂資料夾與檔名格式（多層目錄結構）。
- 自動下載封面圖片與生成 NFO 檔案。
- 包含中文片名提取邏輯（從檔名中智慧識別中文標題）。
- 字幕偵測與中文檢測改從 `scrapers/utils.py` 導入。
- `format_string()` fallback — 資料夾層級空值時自動降級。
- `{suffix}` 格式變數 — UC/LEAK/4K 等版本標記支援。

### `database.py`
**SQLite 資料層**
- WAL mode 高效讀寫。
- `VideoRepository` — 影片快取 CRUD + `clear_all()` 一鍵清除。
- `init_db()` — Schema 初始化 + 遷移。

### `translate_service.py`
**AI 翻譯服務**
- 抽象基類 `TranslateService` 定義統一介面。
- `OllamaTranslateService` - 本地 Ollama 翻譯（批次處理）。
- `GeminiTranslateService` - Google Gemini API 翻譯。
  - 內建 `safetySettings` (BLOCK_NONE) 避免內容過濾。
  - 批次翻譯改為逐片調用以提高成功率。
- 工廠函數 `create_translate_service()` 根據配置創建服務。

### `version.py`
**版本資訊**
- 集中管理版本號 `__version__`。
- 供 Help 頁面與打包腳本使用。

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
- `uri_to_fs_path()` — file:// URI → 當前環境 FS 路徑轉換。
