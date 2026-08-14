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
├── fc2_official.py     # FC2OfficialScraper（`fc2` 來源的現行實作：官方站 adult.contents.fc2.com）
├── fc2_javten.py       # FC2JavtenScraper（`fc-javten` 來源：javten 鏡像站）
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
- 定義了核心資料結構 `VideoInfo`（含 `nfo_thumb` 欄位記錄 NFO 內 `<thumb>` 原始值）。
- 實作了高效的目錄掃描邏輯（`_dir_scan_cache` 目錄級快取避免同一目錄重複 listdir）。
- 包含檔名解析邏輯，能從檔名中提取番號、片名等資訊。
- 支援從 NFO 讀取既有的影片資訊。
- `find_cover_image()` — 4 層 smart fallback：L1 同名圖、L2 標準名（fanart/poster/thumb）、L3 NFO `<thumb>` 跨平台路徑解析、L4 `len(videos)==1 AND 0<len(images)<=2` 雙條件安全 fallback。修正平鋪資料夾跨片污染 bug。
- `_resolve_thumb_path()` — NFO `<thumb>` 5-case 跨平台解析（http(s) URL / `file:` URI / Windows drive letter / UNC / POSIX 相對或絕對路徑）。

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
- `init_db()` — Schema 初始化 + 遷移（41b 加 `user_tags` 欄位的 ALTER TABLE migration）。
- `user_tags` JSON 欄位 — 用戶自訂標籤（評分、書籤、分類），與 scraper `tags` 完全分離，scraper refresh 不覆蓋。
- **UPSERT 保留契約**：`upsert()` 收到 `user_tags='[]'` 時**不覆蓋** DB 既有值（避免 refresh_full 流程吞掉用戶標籤）。
- `update_user_tags(path, tags)` — 安全更新方法，只更新 user_tags 欄位 + `updated_at`，不動其他欄位。

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

### `scrapers/actress/` (orchestrator + 4 sources)
**女優資料爬蟲**
- Orchestrator 並行 4 路：Minnano-AV / Wikipedia JP / Graphis / gfriends
- C1 text cascade：Minnano → Wiki → Graphis
- 供女優卡（Hero Card）功能使用
- Phase 42e（2026-04-11）起不再使用 JavBus actress 路徑；影片 pipeline 的 `scrapers/javbus.py` 不受影響

### `scrapers/actress/gfriends.py`
**gfriends GitHub CDN 女優頭像查表**
- 透過片商映射 + jsDelivr CDN HEAD request 定位女優圖片，不下載 Filetree.json、不 clone repo。
- 維護 `MAKER_TO_GFRIENDS` 對照表，將 maker 名稱映射到 gfriends `Content/` 子資料夾。
- `lookup_gfriends(name, makers)` — 依片商優先順序嘗試，最終以 `9-AVDBS` 兜底。

### `scrapers/actress/graphis.py`
**Graphis Profile 文字解析**
- 從 `graphis.ne.jp` 搜尋並抓取女優高品質照片及個人資料。
- `scrape_graphis_photo(name)` — 回傳頭像 URL（360×508）、背景 URL（1185×835）及英文名、年齡、身高、三圍等欄位。
- `_parse_graphis_profile(html)` — 解析 `model.php` 詳情頁 HTML，提取結構化 profile 欄位。

### `nfo_updater.py`
**NFO 批次更新器**（Scanner 頁面「補全」按鈕）
- 檢查現有影片的 NFO 檔案是否缺少關鍵欄位（如片商、演員、日期、系列等）。
- 自動調用 `scraper` 補全缺失的元數據並回寫 NFO（XML patch，僅填空欄位不覆蓋）。
- 支援 SSE (Server-Sent Events) 進度串流回報。
- `parse_nfo()` 也被 `enricher.py` 共用，能正確解析 NFO 的 `<user_tag>` 元素（與 scraper `<tag>` 完全獨立）。
- `update_nfo_user_tags(nfo_path, add, remove)` — surgical update：只增刪 `<user_tag>` 元素，其他欄位完全不動。NFO 不存在時**回傳 False，不建空殼**（避免污染未刮削的影片目錄）。
- `<user_tag>` 與 `<tag>` 在 NFO 中完全分離：scraper 標籤寫 `<tag>`，用戶標籤寫 `<user_tag>`，互不混淆。
- 不寫封面、不寫 extrafanart、不更新 DB。

### `enricher.py`
**單一影片原地補完**（`POST /api/enrich-single`，Agentic AI 用）
- 三種模式：`fill_missing`（DB→NFO→scraper 逐層補齊）、`db_to_sidecar`（僅從 DB 寫出）、`refresh_full`（強制重抓覆蓋）。
- 可寫 NFO（full rewrite via `organizer.generate_nfo()`）、封面、extrafanart。
- `fill_missing` / `refresh_full` 模式會同步更新 SQLite DB，包含 `nfo_mtime` 同步（避免 collection_analysis 的 missing_nfo 計數不減）。
- 支援 `source` / `javbus_lang` 參數透傳給 scraper（指定來源 + 切換 JavBus 語系）。
- 依賴 `nfo_updater.parse_nfo()` 讀取既有 NFO、`organizer.py` 寫出檔案。

## 工具函式

### `path_utils.py`
**跨平台路徑處理**
- 解決 Windows、WSL (Windows Subsystem for Linux)、Linux 與 macOS 之間的路徑格式差異。
- 支援將 WSL 路徑轉換為 Windows 可讀取的 `file:///` 格式，確保在 Windows 瀏覽器中能直接開啟本地檔案。
- `uri_to_fs_path()` — file:// URI → 當前環境 FS 路徑轉換。
- `to_file_uri(fs_path, path_mappings)` — 正向映射：FS 路徑 → file:// URI（含 path_mappings 用於 WSL 環境）。內含 boundary check（避免 `/home/user/share` 誤命中 `/home/user/share2`）+ trailing separator normalize（charset rstrip）。
- `reverse_path_mapping(fs_path, path_mappings)` — `to_file_uri` 的反向操作：把 Windows/UNC FS 路徑轉回 WSL local mount path。同樣具備 boundary check + trailing normalize 對稱保護。三區模型 Zone 1 的責任聚集點，業務層不應自行做路徑分隔符替換。

### `video_extensions.py`
**影片副檔名 Single Source of Truth**
- 集中定義所有影片副檔名常數，其他模組一律從此處 import，不得各自硬編碼。
- `DEFAULT_VIDEO_EXTENSIONS` — 預設支援的副檔名 tuple（穩定順序）。
- `SAFE_PROXY_EXTENSIONS` — HTTP 檔案代理安全白名單（frozenset），不受用戶設定影響。
- `ZERO_SIZE_EXTENSIONS` — 不受 min_size 過濾的副檔名（如 `.strm`）。
- `normalize_extensions(exts)` — 正規化副檔名清單（strip、lowercase、補前導點）。
- `get_video_extensions(config)` / `get_proxy_extensions(config)` — 從 config 讀取，附 fallback。

### `nfo_utils.py`
**NFO 檔案工具函數**
- `sanitize_nfo_bytes(raw)` — 修正 NFO 中非法的 bare `&`，使 malformed XML 可被正常解析。在 bytes 層級操作，保留 CDATA 區塊原封不動。

### `nfo_read.py`
**NFO 欄位定位的韌性規則（單一所有權，spec-113 F-1）**
- 原本 `enricher._nfo_to_meta`、`gallery_scanner.VideoScanner.parse_nfo`、`readonly_producer._nfo_to_producer_meta` 三份各自實作「同一個欄位可能長成哪幾種樣子」，且韌性程度互不相同（第三方 NFO 的巢狀 actor / `<maker>` / `<release>` 讀不到 → 被誤判為缺漏 → 被刮削覆寫）。
- `nfo_text(root, tag)` — 讀單一 tag 的 text，strip 後回傳；tag 不存在／`.text is None`／全空白統一回 `''`。
- `nfo_first_text(root, tags)` — 依序試多個 tag 名，回傳第一個 strip 後非空的值（**全空白視為沒有**，不會吃掉後面合法的候選）。
- `nfo_actor_names()` — 扁平 `<actor>` 與巢狀 `<actors><actor><name>` 皆讀得到（any-depth），strip 後過濾空字串。
- `nfo_merged_tags()` — 合併 `<tag>` 與 `<genre>`，保序去重、過濾空白。
- `nfo_series_name()` / `nfo_runtime_minutes()` — `<set>` 系列名（掃到第一個有 `<name>` 的）／`<runtime>` 轉整數（容忍前後空白）。
- **不在這裡**：欄位缺漏怎麼判、要不要觸發刮削、寫回誰的資料結構——那是三個呼叫端各自的決策。

### `nfo_stat.py`
**`.nfo` 修改時間讀取的例外語意（單一所有權，spec-113 F-5）**
- 原本全庫**六處**各自手寫「stat 已選定的 sidecar `.nfo` 拿 mtime」，配了**五種**不同例外處理（`OSError` ×2、`Exception` ×1、逐列 `continue` ×1、**完全無保護 ×2**）——無保護的那兩處會讓「確認檔案存在」與「真的去讀」之間的競態炸掉整次操作。
- `nfo_mtime_or_none(target, *, on_error)` — `target` duck-type 成任何有 `.stat()` 的東西（`Path` 或 `os.DirEntry`，讓已經持有 DirEntry 的 `os.scandir()` 呼叫端不必重 stat）。**只吃 `OSError`**，其餘例外一律往外拋（那是呼叫端的 bug）；`on_error` 自己拋的例外原樣傳出，這是呼叫端 opt-in「重拋」語意的方式。
- **不在這裡**：sidecar 路徑怎麼定位、既有值該不該被覆寫、結果怎麼寫進 DB——全留在呼叫端。
- 覆寫語意（`NFO_MTIME_REFRESH` / `NFO_MTIME_ON_UPSERT` / `NFO_MTIME_FILL_MISSING`）**刻意不收斂**，但改為呼叫端**具名可見**，不再靠函式預設值繼承。

### `atomic_write.py`
**原子寫入 primitive（單一所有權，spec-113 F-2）**
- `atomic_write(dest, *, mode, encoding, suffix)` — context manager：在 `dest.parent` 建唯一暫存檔（`mkstemp`）→ yield 檔案物件 → 關檔 → `os.replace` 換上去；**兩條失敗路徑（寫入中例外／replace 失敗）都會清掉暫存檔**再往外拋。
- 收斂了四處手寫實作：`config.py`（設定檔）、`thumbnail_cache.py`（縮圖）、`actress_photo.py`（下載女優照片）、`web/routers/actress.py`（上傳裁切照片）。
- **刻意不在這裡**：上鎖、刪同名舊檔、把失敗轉成 `False`、決定 `dest` 在哪——全部留在呼叫端。清舊檔一律排在 `os.replace` 成功**之後**（`os.replace` 在 Windows 不保證成功，見 `gotchas-backend.md` BE-ENV-01）。
- ⚠️ 模組內對 `os.replace` / `tempfile.mkstemp` **必須用屬性存取**（禁 `from os import replace`），否則測試端 `patch("core.atomic_write.os.replace")` 會失效——由 `tests/unit/test_atomic_write_boundary_guard.py` 的 AST 守衛鎖住。

### `image_host_policy.py`
**圖片來源 host 放行政策 registry（單一所有權，spec-113 F-6）**
- `IMAGE_HOSTS: tuple[ImageHost, ...]` — 宣告式清單，每筆宣告 `host` / `match`（`exact` | `root`）/ `schemes` / `consumers`（`download` | `proxy`）/ `photo_source` / `path_prefix` / `port`。
- `download_hosts_for(photo_source)` — 女優照片下載端的允許 host 集合；未知 source 回空 set（fail-closed）。
- `proxy_rules()` — `/api/proxy-image` 的 `(exact_hosts, root_domains)`。
- `proxy_dynamic_hosts()` — **動態**條目（目前只有「使用者當下連著的那台 metatube」），值取自 `core/metatube/state.py::connected_base_url()`，**每次呼叫重算不快取**，所以 disconnect 立即撤銷放行。
- **兩端的允許集合刻意不相等**：下載端是 exact-only、允許 http、綁 `photo_source`；proxy 端強制 https、有 root-domain 邊界比對。registry 的價值是讓「不相等」變成**被宣告的**，不是把它們統一（合併會失去 source 綁定、放寬 scheme、把 `github.com` 這類下載來源擴大成 proxy 可任意抓取的目標）。
- **刻意不在這裡**：URL 解析與 scheme／port／path 的實際判斷——那些留在兩個消費端（`core/actress_photo.py::validate_photo_url()` 與 `web/routers/search.py::_is_allowed_image_url()`）。registry 只宣告，不執行。
- ⚠️ 兩個消費端**不得再自行宣告 domain-shaped 字面容器**——由 `tests/unit/test_image_host_policy_boundary_guard.py` 的 AST 守衛鎖住（含全庫「禁止分開讀 `metatube_state.is_connected` / `.base_url`」的原子存取禁令）。

### `logger.py`
**統一日誌模組**
- `setup_logging(log_dir, console_level)` — 初始化日誌系統（由 `standalone.py` 呼叫一次），設定 RotatingFileHandler（10MB × 5 份）與 Console Handler。
- `get_logger(name)` — 取得指定模組的 logger，統一使用 `OpenAver.*` 命名空間。
