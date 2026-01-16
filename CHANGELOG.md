# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
