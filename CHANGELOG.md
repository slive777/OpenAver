# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
