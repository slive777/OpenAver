# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-03-31

### Added

#### 🌐 i18n 補齊 + 翻譯目標語言 (Phase 38c)
- Search 頁動態按鈕 / 標籤 i18n 補齊（searchAll / translateAll / fileCount / MODE_TEXT / cover error 共 20 key）
- 翻譯功能自動跟隨 UI 語系：繁中→繁中翻譯、簡中→簡中翻譯、英文→英文翻譯
- `LANGUAGE_PROMPTS` 三語系 prompt 模板（Ollama + Gemini）
- 日文 locale 自動跳過翻譯（原始標題本身即日文，不呼叫 API）
- Settings 翻譯測試按鈕跟隨語系（Ollama / Gemini test prompt 動態切換）
- Settings 連線狀態訊息 i18n（17 key）
- Tutorial 新手教學四語系補齊（14 key）
- i18n 測試零 warnings（所有 locale 欠債清零）

### Fixed
- Search 頁 MODE_TEXT 未知 mode graceful fallback（不再顯示 `[search.mode.xxx]`）
- Settings 翻譯測試按鈕 dark mode 文字不可見（移除 `btn-neutral`）
- `chinese_title_ai` label 改為「AI 翻譯標題」（翻譯結果可能非中文）
- locale 變更時翻譯 service singleton 正確重建

### Changed
- 測試總數 1420 → 1430（+10）

## [0.6.0] - 2026-03-29

### Added

#### 🌐 UI 多語系 i18n (Phase 38a)
- 四語系支援：繁體中文（zh-TW）、簡體中文（zh-CN）、日文（ja）、英文（en）
- `core/i18n.py` 翻譯核心模組：`t()` fallback chain、`get_merged_translations()`、Accept-Language 偵測
- `locales/` 四語系 JSON（~477 個 key），涵蓋所有頁面靜態 UI 文字
- Settings 頁語系切換按鈕（繁 → 简 → あ → EN 循環），Fluent-glass 外觀
- `base.html` 注入 `window.__i18n` + `window.t()` 供前端 JS 使用
- JavBus scraper 語系連動（locale → lang 參數自動對應）
- 字體 fallback 加入 Hiragino Sans / Yu Gothic UI / Noto Sans JP（日文假名支援）
- i18n 完整性測試（477 key × 3 locale = 1431 parametrize 測試）
- `<html lang>` 動態跟隨語系設定
- `PUT /api/config/general/locale` 加 enum 白名單驗證
- Settings 語系切換整合 dirty-check 保護

### Changed
- 測試總數 1366 → 1420（+54）
- AGENTS.md 新增 i18n review policy

## [0.5.5] - 2026-03-28

### Added

#### 🎬 字幕檔自動偵測與搬移 (Phase 37d-T1)
- 新增 `find_subtitle_files()` 掃描同目錄同名字幕檔（.srt/.ass/.ssa + 語言後綴）
- `organize_file()` 影片搬移成功後字幕自動跟隨，保留語言後綴命名
- 字幕偵測與 NFO 標記一致：sidecar 字幕存在時覆寫上游 `has_subtitle=False`

#### ⚙️ Settings 搜尋來源 UI 簡化 (Phase 37d-T2)
- 移除頁面底部獨立「主要搜尋來源」radio 區塊
- DMM/JavBus badge 可直接點擊切換，以 ●/○ 符號標示選中狀態

#### 🌐 Proxy direct 模式 (Phase 37d-T3)
- Proxy 欄位輸入 `direct` 代表已有日本 IP，免填 proxy 即可啟用 DMM
- DMMScraper direct 模式設 `trust_env=False`，確保不繼承環境 proxy 變數
- DMM 內部三處 proxy guard 移除，可用性判斷統一由呼叫端控制

#### 📖 Help 頁面更新 (Phase 37d-T4)
- 搜尋功能：Lightbox 新欄位 + 劇照按鈕說明
- Scanner：字幕檔自動偵測與搬移說明
- Showcase：Lightbox/Table 新欄位 + 劇照按鈕說明
- Scraper 來源：預設搜尋來源 / DMM 模糊搜尋 / Proxy direct 模式說明
- 疑難排解：DMM 段落補充 direct 說明

### Changed
- 測試總數 1324 → 1366（+42）

## [0.5.4] - 2026-03-28

### Added

#### 🏭 Maker 名稱對照表重建 (Phase 37c)
- `maker_mapping.json` 改為雙層格式（name_mapping + prefix_mapping），合併 DMM 72 筆名稱對照
- 新增 `core/maker_mapping.py` shared loader 模組，統一供 search / showcase / scraper 共用
- `/search` 路徑：`Video.to_legacy_dict()` 自動套用 name normalize（片假名/英文長名 → 短名）
- `/showcase` 路徑：`normalize_maker()` 改為兩步查詢（name mapping 優先 → prefix fallback）
- gfriends lookup 補齊 SCOOP → x-KMP 對應

### Changed
- 測試總數 1280 → 1324（+44）

## [0.5.3] - 2026-03-28

### Added

#### 🖼️ Sample Gallery 元件 (Phase 37b)
- extrafanart/ 本地圖片接入 Showcase Lightbox（scanner 掃描 → DB → API 全鏈路）
- 全新 `sample-gallery` overlay 元件：大圖瀏覽 + 縮圖列 + GSAP slide 動畫
- Showcase Lightbox 新增「查看樣品圖 (N)」入口按鈕
- /search Grid Lightbox 同步新增入口按鈕
- /search Detail 模式舊 sample-lightbox 完整替換為 sample-gallery
- 鍵盤導航（ESC/←/→）+ 觸控 swipe 手勢 + Reduced Motion 降級
- DB schema migration 自動補齊 `sample_images` 欄位

### Changed
- 測試總數 1250 → 1280（+30）

## [0.5.2] - 2026-03-27

### Added

#### 🔗 Metadata Pipeline 補齊 (Phase 37a)
- NFO 讀寫補齊 director/duration/series/label 四個欄位，從 Scraper 到 DB 全鏈路流通
- `parse_nfo()` 新增讀取 `<runtime>`、`<director>`、`<set><name>`、`<label>` 標籤
- `VideoInfo` dataclass 新增四欄位 + `from_dict()` 防禦性過濾未知 key（舊 cache 向下相容）
- DB schema migration 自動補齊 `director`、`label` 欄位（ALTER TABLE）
- `_get_columns()` 改為 PRAGMA 動態查詢（新舊 DB 欄位順序自動對齊）

#### 📝 NFO 批量更新擴充
- `nfo_updater` 補齊 director/duration/series/label 寫入（含 `<set><name>` 巢狀結構）
- `needs_update()` 新增四欄位缺失檢查（duration 用 `is None` 防 0 短路）

#### 🖥️ Showcase 新欄位顯示
- Grid info panel 新增系列 + 片長（有值才顯示）
- Table mode 新增「導演」「片長」兩欄
- Lightbox 新增 director/duration/series/label 四欄位（可點擊搜尋）

#### 🔍 Search Lightbox 新欄位
- Main Lightbox 新增 director/duration/series/label 顯示（有值才顯示）

### Changed
- 測試總數 1171 → 1250（+79）

## [0.5.1] - 2026-03-27

### Added

#### 🔍 DMM Scraper 增強 (Phase 36-1)
- DMM 精準搜尋補齊所有新欄位（director、duration、label、series、sample_images）
- DMM 模糊搜尋實作（legacySearchPPV 關鍵字搜尋，支援日文女優名/片商名）
- DMM 模糊搜尋 per-item enrichment（逐筆補齊完整欄位）
- DMM 模糊搜尋漸進 SSE 回報（ThreadPoolExecutor + as_completed 即時回傳）

#### ⚙️ 來源優先設定 (Phase 36-2)
- Config 新增 `primary_source` 設定（javbus/dmm 切換）
- Facade 層精準搜尋 merge 優先權依設定切換
- DMM 模糊搜尋路由 + 無 proxy 自動降級至 JavBus
- Settings UI 新增「主要來源」radio 切換（JavBus/DMM）
- Detail 模式新增 Source Link 按鈕（復用 Lightbox source_links config）

#### 📊 其他來源欄位補齊 (Phase 36-3)
- Jav321 補齊 maker、duration、series、sample_images
- AVSOX 補齊 duration、series
- HEYZO 補齊 duration、series、sample_images（tags 一併修正）
- FC2 補齊 sample_images
- D2Pass 補齊 duration、series、sample_images + caribbeancom HTML fallback

### Fixed
- DMM sample images 升級為高解析度（CDN URL pattern `-N.jpg` → `jp-N.jpg`）
- DMM sample images URL regex 加 negative lookbehind 防止雙重轉換
- DMM 模糊搜尋 hero card `_mode` 修正（`fuzzy` → `actress`）
- HEYZO XPath 修正（duration / gallery / tags / series 全部匹配真實 DOM）
- D2Pass caribbeancom JSON 404 時 HTML fallback 解析完整 Video

### Changed
- 測試總數 1073 → 1171（+98）

## [0.5.0] - 2026-03-25

### Added

#### 🔧 JavBus Scraper 完全重寫 (Phase 35-1)
- 移除 jvav 第三方依賴，自行實作 JavBus scraper（requests + BeautifulSoup）
- 精準搜尋支援所有欄位解析（欄位名 mapping，非位置推斷）
- 模糊搜尋實作（關鍵字 / 前綴 / 女優名搜尋，含分頁支援）
- 多語言預留（zh-tw / ja / en，預設繁中）
- actress_scraper 同步移除 jvav，改用自建 searchstar 請求

#### 📊 Video Model 擴充
- 新增 director（導演）、duration（片長）、label（發行商）、series（系列）、sample_images（樣品圖像）欄位
- Merge policy 擴充 — source=auto 模式下新欄位不被丟棄

#### 🖼️ Sample Images Gallery + Lightbox (Phase 35-2)
- Detail 模式封面下方新增 sample images 縮圖列（水平可滾動）
- 點擊縮圖開啟 Sample Lightbox（純圖模式，左右鍵 / swipe 切換，計數器顯示）
- 方向鍵語意不變 — Detail 模式下左右永遠切換影片，Lightbox 內切換 sample

#### 📋 Detail 模式新增欄位展示
- 搜尋頁 Detail 模式展示導演、片長、發行商、系列（有值才顯示）

#### 📦 Organizer NFO 擴充 + extrafanart
- NFO 新增 `<runtime>`、`<director>`、`<set>`（系列）、`<uniqueid>`
- jellyfin_mode 時自動下載 sample images 至 `extrafanart/` 子目錄

#### 🧪 測試基礎設施
- 首次引入 Playwright E2E 測試（`tests/e2e/`）— Detail 新欄位、Sample Lightbox、方向鍵導航
- JavBus Smoke Test — 精準搜尋新欄位驗證 + 模糊搜尋 + 多語言 tags 差異
- 測試總數 1007 → 1073（+66）

### Changed
- JavBus / JavDB title 剝除番號前綴（統一顯示）
- CI workflow 排除 e2e 測試（需 Playwright 環境）
- 一般開發測試命令更新為 `-m "not smoke and not e2e"`

### Fixed
- JavBus actresses 解析補 next-`<p>` fallback（部分頁面結構差異）
- extrafanart 覆蓋修正（已存在時不重複下載）
- Sample Strip 比例縮放 + Alpine 初始化修正 + Active 高亮
- 跨頁分頁結果排序 + logger 補齊

### Removed
- **jvav 第三方依賴完全移除**（requirements.txt、mypy.ini、actress_scraper、facade 層）

---

## [0.4.4] - 2026-03-19

### Added

#### 🎨 Lightbox 按鈕重設計 (Phase 34-4)
- Showcase Lightbox 按鈕從 footer 文字改為封面上 glass circle overlay（hover-reveal）
- Search Lightbox 新增完整 metadata panel（標題、演員、番號·片商·日期、標籤）
- Search Lightbox 新增 glass circle 按鈕（返回詳情 / 開啟資料夾 / 來源頁面）
- Source Link 瀏覽器按鈕 — 依 config `source_links` 控制（正版來源預設開啟）
- Actress mode 簡化版 Lightbox（僅封面 + 返回詳情按鈕）
- CSS tooltip + aria-label + focus-visible 無障礙支援

#### 📦 安裝升級改善
- install.ps1 / install.sh 升級時自動清除舊版 `python/` 目錄（避免套件混版）
- README 新增 ZIP 手動安裝升級說明

#### ⚙️ Config source_links
- 新增 `source_links` 設定區段（8 個來源開關，正版預設 true）
- 深層合併 migration — 既有用戶自動補齊新設定、不覆蓋已有值

#### 🔧 PyWebView API
- 新增 `open_url()` — 系統瀏覽器開啟 URL（http/https scheme 限制）

### Changed

#### 🧹 程式碼品質清理 (Phase 34-3)
- 死碼清理 — `sys.path.insert` 殘留、unused wrapper、dead import 移除
- Logger 統一 — 全站改用 `core.logger.get_logger`
- SSE Helper 統一 — scanner.py `send()` 提取為 `_sse_event()`
- Showcase GSAP 歸位 — `core.js` 直接 GSAP 呼叫移至 `animations.js`
- Config 模組抽取 — `load_config`/`save_config` 從 router 移至 `core/config.py`

#### 🧪 測試與 CI
- 測試結構歸位 — 6 孤兒測試移入 unit/integration/smoke 正確目錄
- 測試品質提升 — 重複 setup 消除 + 弱斷言加強
- CI test.yml 修正 — pytest 涵蓋根目錄 + cache 版本隔離
- 測試總數 974 → 1007（+33）

### Fixed

#### 🔒 安全加固
- 2 處 exception 洩漏修復（str(e) → 固定訊息）
- SSE 洩漏封堵 + smoke 斷言補強
- Source Link 前端 scheme 驗證 + noopener,noreferrer 防護
- open_url macOS/Linux returncode 檢查
- 封面載入失敗時 Lightbox 按鈕仍可操作

---

## [0.4.3] - 2026-03-13

### Added

#### 📺 流暢轉場動畫系統完善
- Showcase 和搜尋頁面轉場動畫
- 分頁、篩選、排序時自然過渡
- 載入時柔和脈衝效果
- 詳細面板淡入淡出
- 模式切換流暢動畫

### Changed

#### 🚀 安裝體驗全面改善
- 自動化安裝腳本（curl / PowerShell）— 無需手動解決系統安全限制
- README 新增詳細 5 步手動安裝流程
- 新增 Debug 腳本（Windows OpenAver_Debug.bat / macOS OpenAver_Debug.command）

### Fixed

#### 💎 穩定性與效能
- 修正 Showcase/Search 頁面 lightbox 閉包競態（closeLightbox 改用 250ms delayed clear，高延遲環境不再短暫閃爍）
- 修正初始載入時的畫面閃爍
- macOS launcher 完全脫離 TTY（nohup 實作）
- 大量資料（6000+ 筆影片）時頁面反應更快
- OpenAver_Debug.command 補充環境變數（OPENAVER_DEBUG=1）
- README 疑難排解大幅擴充（Windows/macOS 分別說明）

---

## [0.4.2] - 2026-03-11

### Added

#### 🎬 GSAP Showcase 動效系統 (Phase 33)

**Showcase 頁面全面 GSAP 動效**
- 初始載入 Settle 動畫（scale pulse，不碰 opacity 不閃爍）
- 分頁切換 stagger out/in + 自動 scrollTo 頂部
- 篩選進出場 Flip 動畫（onEnter/onLeave）
- 排序洗牌 Flip 動畫（captureFlipState + reorder）
- 模式切換 crossfade（Grid/Table/List 淡入）
- Lightbox 開啟/關閉/切換 GSAP 動效 + animating guard

**Search 頁面動效增強**
- Lightbox GSAP 動效（open/close/switch）
- 頁面返回 Settle 動畫（與 Showcase 一致的 scale pulse）
- playGridSettle C21 防護（clearProps + onInterrupt）

**Motion Lab 沙盒**
- 新增 /motion-lab 頁面，用於動畫原型開發與調參
- 包含：初始載入、排序洗牌、篩選進出場、分頁切換 demo

### Changed

#### ⚡ Alpine 效能優化

- **F1**: `videos[]` / `filteredVideos[]` 移出 Alpine reactive scope，改為 closure 變數（6000 筆不再建立 Proxy）
- **F2**: Grid mode 禁用 perPage=0「全部」選項，三個攔截點自動降級為 120

### Fixed

#### 🐛 閃爍根治

- **F3**: `playSettle` 取代 `playEntry` 初始載入（scale-only pulse，不碰 opacity → 不閃）
- **F3**: 移除 `x-init="init()"` 雙重呼叫（Alpine 3 自動呼叫 init 方法，同時存在導致 double init）
- **CI**: `TestIsVideoFile` 在 Ubuntu CI 缺 pywebview 時 skip（Windows-only 套件）

#### 🧪 測試套件整合 (Phase 32)

- **U12**: 影片副檔名統一 — `core/video_extensions.py` Single Source of Truth
- **U13**: 測試去重 + conftest 統一 + 結構歸位（778 → 740 tests）
- **U14**: 覆蓋率補強（740 → 803 tests）— validators / scanner / config / API 安全
- **U15**: 品質修正 — 弱斷言加強 + 過大測試拆分

## [0.4.1] - 2026-03-08

### Changed

#### 🧪 測試套件整合 (Phase 32)

**U13 — 去重 + conftest 統一 + 結構歸位**
- 刪除 `test_smoke.py` 與 `test_scraper_parser.py` 重疊的 76 個測試（778 → 740）
- `make_client(mock_targets)` / `make_populated_db(videos)` factory fixture 統一至 `tests/unit/conftest.py`
- `test_scrapers.py` 連外測試加 `@pytest.mark.smoke` 標記
- 4 個重複 scraper search tests 合併為 `@pytest.mark.parametrize`

**U14 — 覆蓋率補強**
- 新增 `test_scraper_validators.py` — `is_number_format` / `is_partial_number` / `is_prefix_only` 邊界測試
- 新增 `test_gallery_scanner.py` — `parse_nfo` / `parse_filename` / `find_cover_image` 測試
- 新增 `test_api_config_endpoints.py` — Tutorial flow + DELETE config 整合測試
- 新增 `test_api_scanner.py` — `/api/gallery/video` 安全測試（403 invalid ext/dir）+ player 測試
- 覆蓋率 740 → 803（+63 tests）

**U15 — 品質修正**
- 拆分 6 個過大測試（17/17/11/20/15/11 assertions → 各 3+ 小測試）
- 弱斷言加強：`len()>0` → 驗具體值/結構，`is not None` → 驗型別/欄位
- `test_init_db_creates_table` 加 PRAGMA schema 驗證
- `test_scrapers.py` 連外測試加強結構驗證（Actress/str 型別檢查）
- 最終測試數 817 passed, 18 deselected (smoke)

---

## [0.4.0] - 2026-03-08

### Added

#### 🎬 GSAP 搜尋頁動畫系統 (Phase 31)

**Motion Infrastructure**
- Motion Lab 沙盒頁（動畫選型與調參環境）
- GSAP 3.12→3.14 升版

**SSE 漸進搜尋協議**
- Backend SSE Protocol — seed + result-item + result-complete 三階段事件
- Frontend Skeleton Grid — seed 驅動 skeleton 卡片佈局
- `search_partial()` 漸進回傳支援（result_callback 透傳）

**Staging Card + Mini-Burst 動畫**
- Staging Card 蓄能 UI — 封面預覽 + 計數 badge + rotating border
- Mini-Burst 動畫 — 時間窗口 batching + 座標偏移飛入 grid
- Stream Buffer 機制 — debounce flush + final-burst race 修正

**Grid↔Detail 轉場**
- Ghost Shared-Cover Transition — FLIP 動畫 + crossfade fallback
- Detail Entry 動畫 — card full 進場 + info 滑入
- Detail Navigation Slide — 左右滑動 + C18 interrupt（killTweensOf，無 lock）

**Cover State Machine**
- `_resetCoverState()` 集中式重置（16 條路徑統一）
- `handleCoverError()` 雙階段 stale defense
- Cover loading shimmer + `_coverLoaded` lifecycle

**SearchAll 競態修正**
- `_searchFileBackground()` 背景搜尋方法（不碰共享 UI 狀態）
- `searchAll()` 並行安全（Promise.all 內只用背景搜尋）

**_failed Slot 完整處理**
- `display: none` 取代 `visibility: hidden`（CSS Grid 無留白）
- 導航/Lightbox _failed skip（navigate + prevLightbox + nextLightbox）
- 計數/canGo/navIndicator _failed-aware
- `hasVisiblePrev()` / `hasVisibleNext()` Lightbox 箭頭方法

#### ⚙️ Settings 動畫
- Theme toggle 圓弧展開動畫

#### 🧪 測試
- `search_partial()` callback 行為測試
- searchAll race guard tests（6 new）
- C30 guard tests（9 new）— navigate/lightbox/canGo/counts/repoint
- 測試總數 731

### Changed
- 後端 `search_prefix`/`search_actress` 統一 title 過濾（拒絕空殼結果）
- File search 動畫整合（searchForFile → playDetailEntry, switchToFile → playSlideIn）

### Fixed
- Grid→Detail 封面偶發消失（ghost opacity 殘留 + 快取不觸發 @load）
- Cover state machine：switchSource reset + empty coverUrl guard
- searchAll 競態：背景搜尋不碰 currentFileIndex/searchResults/displayMode
- _failed repoint 條件式修正（不覆蓋使用者已選中的項目）

---

## [0.3.6] - 2026-02-20

### Fixed

#### 🔗 UNC 路徑修正 (Phase 29)
- **`to_windows_path()` 正斜線 UNC 支援** — `//server/share/...` 正確轉換為 `\\server\share\...`，修復 NAS 影片播放、開啟資料夾、Scraper 拖入失敗
- **`to_windows_path()` 全反斜線輸出** — `C:/path` 一律轉為 `C:\path`，Windows Explorer 等原生 API 需要反斜線
- **Showcase CI 11 tests 修復** — 移除多餘 `normalize_path()` 疊加，`to_file_uri()` 直接處理所有路徑格式
- **`organize_file()` 安全修正** — PermissionError 獨立捕捉 + `str(e)` 改固定中文訊息，防止內部錯誤細節洩漏

### Added
- **UNC 路徑守衛測試** — `to_windows_path()` 正斜線 UNC / 多餘斜線正規化 / 雙向一致性
- **WSL `/mnt/c/` → `file:///C:/` 整合測試** — 路徑轉換端到端驗證
- **`organize_file()` 安全測試** — PermissionError + Exception 不洩漏原始訊息
- **回歸守衛測試** — `to_file_uri()` 跨平台直通（不依賴 `normalize_path`）
- **靜態守衛強化** — 掃描範圍收窄 + regex 比對精確化
- **CLAUDE.md 路徑 Gotchas** — 文件化 `normalize_path + to_file_uri` 疊加陷阱、`to_windows_path` 全反斜線保證
- `AGENTS.md` — Codex bot code review 指引

---

## [0.3.5] - 2026-02-20

### Added

#### 🏷️ 版本標記與覆蓋保護 (T1)
- suffix_keywords config + `{suffix}` 格式變數 — UC/LEAK/4K 等標記自動偵測
- Search suffix badge + 覆蓋引導彈窗 — 已有檔案時提示用戶確認
- Scraper API duplicate response — 覆蓋保護傳前端

#### 📦 Fallback 空值防護 (T2)
- `format_string()` fallback — 資料夾層級空值時自動降級，避免空資料夾
- scrape response fallback warning toast — 刮削空值欄位提示

#### 🌐 批次翻譯 (T3)
- translateAll() — 雲端搜尋模式批次翻譯按鈕 + 翻譯 icon 藍色化

#### 📂 系統檔案管理員整合 (T5)
- openLocal() — Search Detail/Grid + Showcase 統一「開啟資料夾」功能
- PyWebView API `open_folder()` — 系統檔案管理員開啟

#### 🖼️ Jellyfin 圖片模式 (T6)
- crop_to_poster() + organize_file() — Jellyfin 圖片自動生成
- Scanner Jellyfin 圖片批次補齊 — SSE 串流 + 偵測邏輯
- NFO poster/thumb/fanart 標籤修正 — .png→.jpg + Jellyfin 後綴

#### 🔗 路徑工具統一 (T7)
- `uri_to_fs_path()` — 新增 file:// URI → FS 路徑轉換
- 前端 `pathToDisplay()` — 統一路徑顯示格式
- Path Guardrails 守衛測試 — 路徑違規清零

#### 🎨 Design System 補齊 (T8)
- DS 圖示庫補齊 — 21 個缺漏 icon
- DS 色盤補齊 — `--color-warning-content` + `--color-translate` token
- DS 元件補齊 — suffix-badge / override modal / toast warning / mini-terminal
- DS 文件補齊 — Showcase Toolbar + Jellyfin Image Row

#### ⚙️ Settings / Help 重構 (T4, T9)
- Settings 簡化 — 移除版本/更新/新手引導，viewerPlayer 併入系統設定
- Help 全面重構 — hero card + Alpine 檢查更新 + 新增區塊（格式變數/Showcase/Scraper 來源）
- 檔名長度限制 Help Icon — 路徑長度說明浮動面板

#### 🗑️ Scanner 清除快取
- 清除快取 icon + DaisyUI modal 兩步確認 + DELETE API

### Changed
- `folder_layers` 預設改為 `{actor}`
- Toast 描述四種變體 + snippet `#d4d4d4` token 化

### Fixed

#### 🔒 安全加固 (28-4)
- **str(e) 外洩修正** — 7 個 router 共 27 處 `str(e)` 改為固定中文訊息 + server-side log
- **語意版本比較** — tuple 比較取代字串比較，支援 prerelease strip
- **SSE onerror guard** — 正常關閉不再觸發假「連線中斷」錯誤 (×3 處)
- **restoreState() crash** — optional chaining 保護已遷移函式呼叫
- **check-update 硬上限** — `asyncio.wait_for()` 防止 DNS 失敗無限等待
- **logger.exception** — translate.py 保留 traceback 便於排錯

#### 🧪 測試品質提升 (28-4)
- 共用 `tests/unit/conftest.py` — 消除 4 檔重複 fixture
- `test_frontend_lint.py` 相對路徑修正
- `test_api_gallery.py` 斷言加強 — 消除永遠 pass 的弱斷言
- 測試總數 523 → 564（+41）

---

## [0.3.3] - 2026-02-19

### Added

#### 🔍 Scraper 來源擴充 (Phase 27)
- **D2PassScraper** — 1Pondo / Caribbeancom / 10musume 三站聯合無碼爬蟲（共享 JSON API）
- **HEYZOScraper** — JSON-LD + HTML table 解析
- **DMMScraper** — GraphQL API + 日本 IP Proxy 支援（從 feature/ 遷移至 core/scrapers/）
- DMM Tags — GraphQL `genres` 探測（Capability Cache）+ HTML fallback 雙路徑
- Settings Proxy 欄位 — DMM HTTP Proxy 輸入 + 測試連線按鈕
- Settings Source Badge — 有碼/無碼來源 tag-badge 狀態顯示（取代純文字 hint）
- Fast-Path 前綴路由 — FC2/HEYZO 搜尋省掉無謂 D2Pass request
- `extract_number()` 擴充 — 支援底線格式 `DDMMYY_NNN`（1Pondo/10musume）
- 未知 source 白名單驗證 — `search_jav` 回傳 None + API 400
- 新增 `tests/test_new_scrapers.py`（D2Pass/HEYZO/DMM/Pipeline/Fast-Path 共 41 測試案例）

#### 👤 Grid 模式女優資料卡增強 (Phase 26)
- **gfriends 圖片查表** — 最高優先女優頭像來源（GitHub CDN）
- **Graphis Profile 文字解析** — 英文名 / 身高 / 三圍 / 興趣
- Lightbox 導航修正 — 女優頭像可方向鍵移動到封面
- 新增 16 測試案例（gfriends lookup + Graphis text parsing）

### Changed
- Uncensored 偵測擴充 — 支援 HEYZO 前綴 + D2Pass 日期格式
- Uncensored mode 路由擴充 — D2Pass → HEYZO → FC2 → AVSOX
- DMM Top-1 優先順序 — proxy 有值時 DMM 排有碼第一
- Regex 統一 — `\d{6}[-_]\d{2,}` 三處一致（extract_number / is_uncensored × 2）
- `folder_layers` 預設改為 `{actor}`

### Fixed
- Caribbeancom + 1Pondo 封面 fallback — `ThumbHigh` 為 null 時構造 URL
- HEYZO JSON-LD list guard — `@graph` 陣列格式防禦
- DMM empty prefix guard — 空 prefix 不發無謂 request
- JavGuru 移除 — HTML 結構不穩定 + 封面 CDN 失效

### Removed
- JavGuru scraper（HTML 結構不穩定，封面 CDN 失效）
- Settings 來源純文字 hint（改為 Source Badge）

---

## [0.3.2] - 2026-02-18

### Added

#### 🎨 GSAP 前置準備 + Fluent Material Boost (Phase 25)

**Motion Infrastructure (T1–T6)**
- `motion-prefs.js` — `matchMedia` reduced-motion JS 橋接（`OpenAver.prefersReducedMotion`）
- `motion-adapter.js` — 共用 GSAP 封裝（`playEnter` / `playLeave` / `playStagger` / `playModal` + `createContext` 生命週期清理）
- GSAP 3.12.5 CDN 載入（base.html，在 Alpine 之前同步載入）
- `TestMotionInfra` 守衛測試（motion-prefs / motion-adapter / 載入順序 / 無直接 gsap 呼叫）

**Design System 同步清理 (T7)**
- Hero Card 女優資料卡展示
- Toast 變體對照表（fluent-toast / search-toast / settings-toast）
- File Item 5 狀態動態控制展示

**Fluent Material Boost (T8)**
- Canvas Layer（Mica 氛圍背景）— 全頁 radial-gradient + SVG noise overlay（light/dim 各一組）
- Shell Acrylic — Sidebar `backdrop-filter: blur(30px) saturate(140%)` + Offcanvas `fluent-acrylic`
- `.fluent-toolbar` utility class（blur 16px + saturate 130%）
- Surface Elevation — 卡片 `inset 0 1px 0` 頂部高光 + Fluent shadow 層次分離
- `help.css` 新建 — Help 頁卡片材質統一
- Design System Materials Layer System 展示（Canvas / Shell / Surface 三層 demo + 對照表）

### Changed
- Scanner `$refs` fallback 移除（4 處 `getElementById` → `this.$refs`）
- Search `$refs` 遷移（3 處 `getElementById` → `$refs` / Alpine state）
- `@keyframes spin` 統一至 theme.css（移除 search.css / settings.css / design-system.css 重複）
- `--ds-glow-rgb` 變數化 — 全站 18 處 `rgba(90, 200, 250, ...)` → `rgba(var(--ds-glow-rgb), ...)`
- Settings `.card` border-radius 硬編碼 `16px` → `var(--radius-lg)` token
- Settings `.card` shadow-sm → shadow-4 + inset 高光 + stroke-default
- Scanner `.mini-terminal` dim mode 實色 → `color-mix` 半透明
- Search bar `backdrop-filter` 從 `blur(10px)` 升級至 `blur(16px) saturate(130%)`
- Settings/Scanner header 新增 Acrylic 材質（backdrop-filter + border-bottom）
- Sidebar 實色背景 → `color-mix 75%` 半透明 + Acrylic
- Offcanvas `bg-base-200` → `fluent-acrylic`

### Fixed
- Scanner/Showcase 只顯示當前設定資料夾的影片（DB 保留全部當 cache）
- Ollama 翻譯 prompt 重構 — system message + few-shot 解決漢字重標題輸出日文問題
- Ollama `num_predict` 100→500 — think mode 模型推理耗盡 token 導致無回應
- JavDB「發行日期」誤判為片商 + maker 快取日期值防護
- macOS README 解壓路徑修正
- macOS 打包移除 Alpha 標記 — 正式版命名

### Removed
- Design System Legacy 區塊（Bootstrap Buttons/Card/Tabs、未使用的 av-card-thumbnail/compact）
- Design System 重複展示（Shadow Grid、NavRail Expanded、舊版 Toast）

---

## [0.3.1] - 2026-02-11

### Added

#### 🖼️ Showcase 動態化 (Phase 24-2)
- `/api/showcase/videos` API 端點 — SQLite SSR 取代靜態 iframe
- `showcase.html` 全面重寫 — Image Grid + Detail Table + Text List 三種顯示模式
- Lightbox 元件 — Smart Close + metadata + 鍵盤導航
- Card hover footer + glass button overlay
- Toast 通知系統（Design System fluent-toast）
- 搜尋邏輯（多關鍵字 AND + 模糊番號匹配）
- 排序邏輯（8 種欄位 + asc/desc + random 洗牌）
- 快捷鍵完整實作 + 底部提示列
- Config 整合 + 狀態持久化（localStorage + URL state）
- Status bar 影片統計 + 分頁控制
- Showcase API 單元測試（12 cases）

#### 🔀 Alpine.js 全站遷移 (Phase 24-3)
- Search 結果改用 AV Card Full 統一卡片
- Settings Alpine.js 狀態管理（主題 toggle + dirty check + fluent-modal）
- Scanner Alpine 基礎架構（資料夾管理 + SSE 串流 + 女優別名 + Log Terminal 增強）
- Sidebar 純 localStorage 驅動（消除收合閃爍）
- 全站字體大小 5 階調整 + configSync 即時同步
- Settings 格式變數 dropdown 簡化（tag-badge + 預覽列）

#### 🎯 Search Grid Mode + 女優資料卡 (Phase 24-4)
- Alpine 骨架 + 狀態容器 — `state.js` 1734L 單檔拆為 9 個 mixin 模組
- 搜尋流程 + 導航遷移至 Alpine（SSE/REST/navigate/loadMore）
- 結果卡片 template binding 取代 `displayResult()`
- 檔案列表 + 拖拽遷移至 Alpine（x-for/computed）
- Grid Mode — 封面牆 + Lightbox + 女優自動切換
- 女優資料卡（Graphis + JavBus 雙來源並行 + Detail Banner + Hero Card）
- 本地匹配提示 + Rotating Border 動畫
- 搜尋進度豐富化（來源名稱 + 完成提示）

#### 🔍 D.6 最終驗收 (Phase 24-5)
- 前端遷移守衛測試 `test_frontend_lint.py`（靜態分析 4 類規則）
- `_syncToCore()` 統一 helper — 集中 29 處 coreState 同步
- GSAP 就緒度報告

### Changed
- 全站 Alpine.js 統一 — 零 vanilla inline handler、零 Bootstrap 殘留
- `theme.css` 硬編碼 hex / rgba → CSS 變數 + `color-mix()` 語法統一
- `design-system.css` 13 處 hex → CSS 變數（`--gradient-cyan/indigo/purple`）
- Settings theme toggle 只保留 icon（移除 Light/Dim 文字）
- `/search` copyPath 統一複製資料夾路徑（與 `/showcase` 一致）
- `[LOCAL FALLBACK]` 標記語義化為 `[API FALLBACK]`
- Showcase 從靜態 iframe 改為 SQLite SSR 動態頁面

### Fixed
- Windows cp950 編碼全面修復（`print()` → `logger` + `PYTHONUTF8`）
- Rotating Border 本地匹配從轉 1 圈改為 5 圈
- NFO 補全 cache 漏傳 `nfo_mtime` 導致永遠不觸發
- Sidebar 收合閃爍（純 localStorage + inline script 同步）

### Removed
- 舊 iframe Gallery 端點 / service / JS / CSS
- 所有 vanilla inline event handler
- Bootstrap 殘留 class（零殘留確認）
- `[LOCAL FALLBACK]` 標記

---

## [0.3.0] - 2026-02-08

### Added

#### 🔄 Bootstrap → DaisyUI 全站遷移 (Phase 24)
- DaisyUI + Tailwind CSS 取代 Bootstrap 5，完成前端框架替換
- Alpine.js 取代 Bootstrap JS（sidebar、offcanvas、collapse、toast）
- Design System 3 套 scope 機制（`.ds-page` / `.ds-gallery-composition` / `#settings-components`）
- `.text-muted` utility class（綁定 `--text-muted` 變數）

#### 📁 路由改名 `/gallery` → `/scanner`
- 頁面路由語義化：Scanner = 掃描 + 列表生成
- `/gallery` 自動 302 重定向到 `/scanner`（向後相容）
- Config `default_page: "gallery"` 自動映射到 `/scanner`

#### 📦 JS 模組化
- Settings inline JS 抽離為 5 個獨立模組（core/translate/folders/format/init）
- Scanner inline JS 抽離為 4 個獨立模組（core/alias/folders/init）

### Changed
- 所有頁面使用 DaisyUI 元件（btn/input/select/toggle/card/badge/alert）
- Bootstrap grid（`.row`/`.col-md-*`）→ Tailwind grid/flex
- Bootstrap form（`.form-control`/`.form-select`/`.form-check`）→ DaisyUI
- `settings.html` `container-fluid` 移除、`card-header` → `settings-card-header`
- `search.css` 移除 29 行與 theme.css 重複的 `.state-page` + `.empty-actions`
- `showcase.html` 加入 `.ds-page` scope 啟用 Design System 狀態元件
- Settings 排序區塊脆弱 selector `div[style*=...]` → `.sort-row` 語義 class
- Tailwind CSS 重新編譯（v4.1.18 + DaisyUI 5.5.17）

### Removed
- Bootstrap CSS CDN（保留 Bootstrap Icons）
- Bootstrap JS CDN
- `[LOCAL FALLBACK]` 標記（函數保留作為 API fallback 機制）
- `web/routers/gallery.py`（重命名為 `scanner.py`）

---

## [0.2.4] - 2026-02-07

### Added

#### 🎨 Design System (Phase 23)
- `/design-system` 頁面展示所有 UI 元件
- Fluent Design 2 視覺語言（毛玻璃、12px 圓角、複合陰影）
- 統一圓角 Token 系統（`--radius-xs/sm/md/lg/pill`）
- Space Grotesk 字型用於標題
- AV Card 4 種變體（Thumbnail/Preview/Full/Compact）
- 背景光暈 + 噪點紋理視覺效果

#### 🧩 Design System Phase 23-4
- Toast 元件（4 種語意色 + 3 段倒計時動畫 + hover 暫停）
- Button 元件（Primary/Secondary/Ghost/Outline/Icon/Link 6 種變體）
- Help 頁面元素（鍵盤快捷鍵表 + Kbd 尺寸變體）
- Focus-visible 統一規則 + reduced-motion 無障礙收斂
- Search / Gallery Page Composition 頁面級 Mockup
- Settings 特殊元件展示（收合區塊 + 變數插入 Dropdown）

### Changed
- Dark mode 文字對比度修復
- Gallery Card hover 改為右側聚焦（`transform-origin: 65% center`）
- Hex 色彩顯示動態讀取 CSS 變數
- README 翻譯速度說明更新（Ollama 5s → 0.5s）
- 硬編碼色彩 / 圓角 / rgba 全面替換為 Fluent Design Token
- `transition: all` 替換為具體屬性（效能優化）
- 所有動畫 easing 統一使用 Fluent Token（`--fluent-ease-standard` / `--ease-out`）
- 暖奶白底色回歸（`--color-base-100: oklch(98.5% 0.005 85)`）
- Card 圖片圓角對齊：底部接觸 footer 處改為直角

### Removed
- 刪除廢棄測試腳本 `test_task2_integration.sh`

---

## [0.2.3] - 2026-01-23

### Added

#### 📁 Gallery 搜尋增強
- Gallery HTML 搜尋支援路徑名稱（`v.path`）
- 可用舊女優名搜尋（即使已改名，檔名路徑仍保留原名）

#### 📋 本地標記互動
- 點擊 📁 badge 複製檔案路徑到剪貼簿
- 多版本時複製全部路徑（換行分隔）
- Toast 提示複製成功/失敗

---

## [0.2.2] - 2026-01-22

### Fixed

#### 🔧 後綴清理（檔名 + 搜尋查詢）
- `extract_number()` - 從檔名提取番號時清理 -UC/-UNCEN/-UNCENSORED/-LEAK/-LEAKED 後綴
- `is_number_format()` - 搜尋查詢格式驗證時清理後綴
- `normalize_number()` - 番號正規化時清理後綴
- 後綴必須有分隔符（`-` 或 `_`），避免誤刪 JUC-123 等合法前綴
- 檔名 `SONE-103-UC.mp4` 和搜尋查詢 `SONE-103-UC` 現在都能正確處理

### Added

#### 🧪 整合測試
- 新增 `TestSearchQueryIntegration` 測試類，驗證搜尋流程完整性
- 新增 JUC-123 回歸測試，防止前綴誤刪

---

## [0.2.1] - 2026-01-22

### Added

#### 🔍 FC2 / Uncensored Search
- FC2-PPV number search support
- Caribbeancom / 1Pondo uncensored numbers
- AVSOX scraper for uncensored content

#### 🎯 Uncensored Mode Toggle
- Settings page switch to search AVSOX / FC2 only

#### 🗄️ Local Library
- SQLite database tracks scanned videos
- Search page shows "in library" green dot indicator
- Actress alias management (auto-apply during scan)
- User tags (saved to NFO)

### Changed
- Scraper architecture modularized (Phase 16)
- Frontend logic moved to backend APIs (Phase 17)
- Test framework expanded to 311 cases
- Tutorial samples: added FC2-PPV-1723984 (11 total)

### Removed
- DMM scraper temporarily removed (requires Japan IP)

---

## [0.4.0] - 2026-01-21

> ⚠️ Merged into 0.2.1

### Added

#### 🗄️ SQLite Data Layer (Phase 18)
- SQLite database with WAL mode for local video metadata
- Gallery Scanner stores video info (path, number, actresses, mtime)
- `/search` page shows local status indicator (green dot = already in library)
- Actress alias management (Settings page)
- Auto-apply aliases during Gallery scan
- User tags in `/search` (frontend state, written to NFO on generate)

#### 🔄 Thin Client Refactor (Phase 17)
- Business logic centralized to backend
- New `/api/parse-filename` endpoint for batch filename parsing
- `/api/translate` auto-skips non-Japanese text
- `/api/search/sources` returns unified source configuration
- Frontend simplified: removed duplicate logic (hasJapanese, extractNumber, etc.)

### Changed
- Test framework expanded to 315 test cases
- Frontend JS reduced complexity (uses backend APIs)

### Fixed
- Path format consistency in database (`file:///` URI)
- Alias application correctly reloads DB after NFO updates
- `/api/search/local-status` properly initializes database

---

## [0.3.0] - 2026-01-20

> ⚠️ Merged into 0.2.1

### Added

#### 🔧 Scraper Modularization (Phase 16)
- New `core/scrapers/` module with BaseScraper abstract class
- 5 modular scrapers: JavBusScraper, JAV321Scraper, JavDBScraper, FC2Scraper, AVSOXScraper
- Pydantic data models: Video, Actress, ScraperConfig
- Type hints throughout scraper modules

#### 🔍 Uncensored Search Mode
- FC2 番號搜尋支援 (FC2-PPV-XXXXXX)
- Caribbeancom / 1Pondo 無碼番號支援 (XXXXXX-XXX 格式)
- AVSOX 爬蟲專門處理無碼內容

#### 🎯 Precise Search Enhancement
- 精準搜尋支援指定來源 (javbus/jav321/javdb/fc2/avsox)
- 多來源同時查詢，自動合併結果

### Changed
- Scraper architecture refactored from monolithic to modular design
- Test framework expanded to 153 test cases
- Pydantic models updated to v2 ConfigDict syntax

### Removed
- DMM scraper temporarily removed (requires Japan IP, pending testing)
- Backup available at `/feature/dmm.py`

---

## [0.2.0] - 2026-01-18

### Added

#### 🍎 macOS Support (Alpha)
- macOS arm64 (Apple Silicon M1/M2/M3/M4) packaging support
- PyWebView + WebKit integration with full feature parity
- GitHub Actions automated macOS ZIP builds
- Gatekeeper bypass documentation

#### 🔄 Multi-Source Cycling
- New ⟳ button to cycle between javbus/jav321/javdb sources
- Lazy-load queries with caching to avoid duplicate requests
- Toast notifications when switching sources

#### 📁 Multi-Level Directory Structure
- Three-field input UI (outer/middle/inner layers)
- Cascading enable logic (right-to-left: inner→middle→outer)
- Real-time preview showing full path + filename
- "Create Folder" toggle linked to all fields

#### 🤖 AI Translation Enhancements
- Dual engine support: local Ollama and Google Gemini
- Gemini Safety Settings optimization (98-99% success rate)
- Translation service abstraction layer (Strategy Pattern)
- Gemini mode: click-to-translate only translates current item (API rate limit friendly)
- Recommended model: gemini-flash-lite-latest

#### ✨ UX Improvements
- Title edit field changed to textarea for multi-line display
- Settings page preview now updates in real-time
- Mixed-format number support (e.g., T28-103)

### Changed
- Translation provider UI improved: "Gemini (Google Cloud)" vs "Ollama (Local)"
- Test framework expanded to 126 test cases

### Fixed
- `/api/translate` endpoint now correctly supports Gemini provider
- Settings page preview displays correct values on load
- Cross-platform `open_file()` fix (macOS: `open`, Linux: `xdg-open`)

---

## [0.1.4] - 2026-01-17

### Added
- Tutorial Step 5: Guide users to try sample files immediately after onboarding
- Sample files folder ("教學檔案") included in Windows package with 10 searchable examples
- Comprehensive test framework (115 test cases: unit + integration + smoke)

### Changed
- Tutorial card now has "large" variant for final step emphasis
- Test samples moved to `tests/samples/` for cleaner project structure

---

## [0.1.3] - 2026-01-17

### Fixed
- NFO updater now uses centralized `path_utils.normalize_path()` for Windows compatibility
- Image proxy refactored to use `path_utils.normalize_path()` (removed duplicate code)
- Settings dropdown menus no longer clipped by card overflow
- Default folder format changed to `{actor}`
- Default filename format changed to `[{num}][{maker}] {title}`

### Changed
- Centralized all path conversion logic in `core/path_utils.py`

---

## [0.1.1] - 2026-01-17

### Fixed
- Image proxy now correctly handles Windows native paths (previously always converted to WSL format)
- Settings page: "格式" label corrected to "資料夾名稱"
- Help page version number now dynamically loaded

### Added
- Manual update check button in Settings (privacy-friendly, no auto-connect)
- Centralized version management (`VERSION` constant in app.py)

---

## [0.1.0] - 2026-01-15

### Added

#### 🔍 Search
- Spotlight Search with multi-source aggregation (JavBus, Jav321, JavDB)
- Gallery Style UI with Hero Detail and glassmorphism effects
- Smart search with auto-normalization and prefix matching
- Actress search with Gallery Mode (auto-switch when >10 results)
- Drag & drop file search with automatic filtering
- Batch search (20 files per batch, 2 concurrent)
- Pause/Resume functionality
- Favorite folder quick load

#### 📝 Gallery Generator
- Static HTML gallery generation from local folders
- Mini-Terminal for real-time progress display
- Automatic NFO file completion

#### ⚙️ Settings
- Full Dark Mode support
- Ollama integration for title translation
- Flexible output path and naming rules
- Favorite folder configuration
- File size filtering

#### 🎓 Onboarding
- Spotlight Tutorial for first-time users
- 4-step guided tour (Search → Files → Gallery → Settings)
- Dual storage mechanism (API + localStorage fallback)
- Tutorial restart from Settings/Help pages

#### 🛠️ Technical
- FastAPI backend with Jinja2 templates
- PyWebView desktop wrapper (Windows)
- Bootstrap 5 with custom Gallery Design System
- Comprehensive test suite (Pytest)

#### 📦 Packaging
- Windows portable build (PyWebView + EdgeChromium)
- Rotating log system (5 files × 10MB)
- WebView2 Runtime detection
- User-friendly error messages

### Known Issues
- JavDB may require IP rotation due to rate limiting
- Windows 10/VM requires Edge WebView2 Runtime installation
