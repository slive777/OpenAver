# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
