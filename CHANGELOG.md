# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-01-18

### Added

#### 🍎 macOS 支援 (Alpha)
- macOS arm64 (Apple Silicon M1/M2/M3/M4) 打包支援
- PyWebView + WebKit 整合，功能與 Windows 版一致
- GitHub Actions 自動打包 macOS ZIP
- Gatekeeper 繞過說明文件

#### 🔄 多來源循環切換
- 新增 ⟳ 按鈕，可在 javbus/jav321/javdb 之間循環切換
- 懶加載查詢 + 快取機制，避免重複請求
- 跨來源切換時顯示 Toast 提示

#### 📁 多層目錄結構
- 三欄位輸入框 UI（外層/中層/內層）
- 連動啟用邏輯（右到左：內→中→外）
- 即時預覽顯示完整路徑 + 檔名
- 「建立資料夾」開關連動所有欄位

#### 🤖 AI 翻譯進化
- 支援本地 Ollama 和 Google Gemini 雙引擎
- Gemini Safety Settings 優化（成功率 98-99%）
- 翻譯服務抽象層（策略模式）
- Gemini 模式點擊翻譯只翻譯當前片（避免 API 限制）
- 推薦模型：gemini-flash-lite-latest

#### ✨ 體驗優化
- 片名編輯框改用 textarea，支援多行顯示
- 設定頁預覽即時更新修復
- 混合格式番號支援（如 T28-103）

### Changed
- 翻譯服務選項 UI 改進：「Gemini（Google 雲端）」vs「Ollama（本地）」
- 測試框架升級至 126 個測試案例

### Fixed
- `/api/translate` 端點現在正確支援 Gemini provider
- 設定頁載入時預覽顯示正確值
- 跨平台 `open_file()` 修復（macOS: `open`, Linux: `xdg-open`）

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
