<!-- OpenAver: open-source desktop GUI JAV metadata manager.
No Docker, one-line install (Win/Mac), 6 scrape sources,
Jellyfin/Emby compatible, actress favorites with alias deduplication,
AI-operable REST API with capabilities manifest, 2400+ tests, MIT license. -->

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>No Docker, no CLI — one-line install for Win/Mac, full GUI JAV metadata manager out of the box.</strong><br>
  6-source unified search · Actress favorites & alias management · Interactive collection browser · Jellyfin integration · AI API to manage your library with a single prompt
</p>

<p align="center"><em>
  Open-source desktop GUI for JAV metadata — one-line install, 6 scrape sources, actress favorites + alias system, Jellyfin/Emby ready, AI-operable REST API.
</em></p>

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

**English** | [繁體中文](README.md)

The core workflow spans three pages: 🔍 Search video info → 📋 Scan & build library → 🎬 Browse collection

**100% local** — no data collection, no uploads. Network requests are only used to scrape publicly available metadata.

**✨ Highlights**: Search 6 sources at once · Actress favorites with auto profile + alias expansion · One-click NFO & cover fill from the web · AI-operable library in natural language · Jellyfin / Emby cover auto-generation · 2400+ automated tests

## Screenshots

| Search | Actress Collection |
|--------|--------------------|
| ![Search](docs/screenshots/home-en.png) | ![Actress](docs/screenshots/showcase-actress.png) |

<details>
<summary>More Screenshots</summary>

| Search Demo | Actress Gallery |
|-------------|-----------------|
| ![Search Demo](docs/screenshots/demo2.gif) | ![Search](docs/screenshots/search-detail.png) |

| Showcase Video Mode | Showcase Detail |
|---------------------|-----------------|
| ![Grid](docs/screenshots/showcase-grid.png) | ![Detail](docs/screenshots/showcase-detail.png) |

</details>

---

## Installation

### Recommended: One-Line Install

**macOS**:
```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash
```

**Windows** (PowerShell):
```powershell
irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex
```

The script automatically:
- Detects your system architecture and downloads the latest release
- Clears platform security restrictions (macOS quarantine / Windows Mark of the Web)
- Creates a desktop shortcut (Windows)
- Preserves your settings and logs on upgrade

### Alternative: Manual ZIP Download

Download from [GitHub Releases](https://github.com/slive777/OpenAver/releases/latest):

| Platform | File |
|----------|------|
| **Windows x64** | `OpenAver-vX.X.X-Windows-x64.zip` |
| **macOS arm64** | `OpenAver-vX.X.X-macOS-arm64.zip` |

> ⚠️ Manual ZIP install requires extra steps to clear security restrictions — see the Troubleshooting document included in the ZIP.
> ℹ️ macOS builds target Apple Silicon (M1/M2/M3/M4) only.

On first launch, a built-in setup wizard walks you through folder configuration and basic settings — no docs required.

---

## Features

### 🔍 Search
- **Multi-Source Aggregation**: One query simultaneously searches JavBus, Jav321, JavDB, DMM, D2Pass, and HEYZO — all sources at once.
- **Detail View**: Cover, stills, actress, tags — all in one place, no tab-hopping.
- **Smart Search**: Search by ID, actress name, series, or maker — results are matched against your local library and marked if already in your collection.
- **Actress Features**: Searching a favorited actress automatically shows her profile card; results can be added to your collection directly.
- **Version Detection**: Automatically identifies UC/LEAK/4K variants — no manual renaming needed.
- **Local Batch Search**: Drag in video files or folders — automatically extracts IDs and batch-searches for metadata, covers, and stills.

### 🎬 Showcase
- **Video Mode**: Cover wall grid + detail Lightbox + search/filter/sort + stills browser — a full interactive collection viewer.
- **Actress Mode**: Favorited actress grid + profile Lightbox + sort by cup size / age / height — one-click refresh to pull updated data.
- **Visual Design**: GSAP animations + Fluent Design frosted-glass effects + Dark Mode, with SSR real-time rendering.

### 📋 Scanner
- **Scan & Build Library**: Scan local video folders, build a SQLite metadata database, automatically reads existing NFO files and covers.
- **NFO & Cover Completion**: Detects missing NFO fields or files and fills them in from the web with one click.
- **Actress Alias Management**: Add and edit aliases — searches automatically expand to all known names.
- **Subtitle Detection**: Automatically detects and moves subtitle files when organizing videos.

### 🌐 AI Translation
Translate Japanese titles into your UI locale (Traditional Chinese, Simplified Chinese, English) in one click — Japanese locale skips translation since titles are already in Japanese.
- Supports **Ollama** (local GPU, free & unlimited), **Gemini Flash** (Google cloud, free tier available), and **OpenAI API Compatible** (OpenRouter, any compatible endpoint).

### ⚙️ Settings
- **Multi-Language UI**: Traditional Chinese, Simplified Chinese, Japanese, English — instant switch.
- **Path & Naming Rules**: Flexible output path configuration with `{suffix}` variable support.
- **Favorites Folders**: Save frequently used folders for one-click batch loading.
- **Jellyfin Image Mode**: Auto-generates `poster` and `fanart` in the format Jellyfin / Emby expects.
- **Static HTML Export**: Generates a standalone HTML index file — viewable offline without a server.

### 🤖 AI-Ready API

Your AI assistant can operate your library directly:

- "Search SAME-123, PRED-456, IPZZ-789 for me" — multi-source aggregation
- "Fill in the missing NFO in D:\av" — in-place enrichment, no rename, no move
- "Which series did I download the most this year?" — SQL queries on your collection
- "Turn the IDs in this article into a visual gallery" — auto-embedded cover HTML

No SDK. No docs to read. One curl, and your AI learns every endpoint:

```bash
curl http://localhost:<port>/api/capabilities
```

> The port and full URL are shown in the Settings page under "AI API".

Works with any MCP / function-calling compatible AI tool:

| Method | Tools | Notes |
|--------|-------|-------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider, etc. | Just `curl` from the terminal — all CLI agents supported |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae, Google Antigravity, etc. | Agent mode / MCP to call local API |
| **Desktop App** | Codex App, Claude Cowork, OpenClaw | No dev environment needed, works out of the box |

> 💡 **Recommended**: **OpenAI Codex App** (Win/Mac, free tier available) — the only AI tool that renders cover images directly in the conversation. Easy to install, works out of the box.

> ⚡ **Small-model friendly**: The capabilities manifest is optimized for lightweight models — Gemini Flash / GPT-5.4 mini / Claude Haiku can all operate every endpoint correctly.

> 🔍 Looking for a local video library tool that Claude / Codex / Gemini can operate directly? OpenAver is one of the few desktop GUI projects with a built-in capabilities manifest and full REST API.

---

## Developer Guide

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.10+) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + Fluent Design 2 |
| **Animation** | GSAP 3.14+ with Motion Adapter (respects `prefers-reduced-motion`) |
| **Desktop Shell** | PyWebView (Windows / macOS) |
| **Database** | SQLite (WAL mode) |
| **Testing** | Pytest — 2400+ tests |

### Run from Source

**Prerequisites**: Python 3.10+, Chrome/Edge, [WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

```bash
# Clone + set up virtual environment + install dependencies
git clone https://github.com/slive777/OpenAver.git
cd OpenAver
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Development mode (hot reload)
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# Desktop mode (Windows)
python windows/launcher.py
```

### Running Tests

```bash
source venv/bin/activate
pytest
```

### Directory Structure

```
OpenAver/
├── web/                # Web GUI (FastAPI)
│   ├── routers/        # API endpoints (Search, Config, Scraper, Scanner, Capabilities)
│   ├── templates/      # HTML templates (DaisyUI + Fluent Design 2)
│   └── static/         # CSS/JS assets (modular JS, theme CSS)
├── core/               # Core logic
│   ├── scrapers/       # Modular scrapers (JavBus/JavDB/Jav321/FC2/AVSOX/DMM/D2Pass/HEYZO)
│   ├── database.py     # SQLite data layer (WAL mode)
│   ├── organizer.py    # File organizer + null-value fallback guards
│   ├── path_utils.py   # Cross-platform path handling (file:// URI)
│   ├── i18n.py         # i18n core (t() / fallback chain)
│   └── translate_service.py  # AI translation (Ollama/Gemini/OpenAI Compatible)
├── locales/            # 4-locale JSON (zh_TW/zh_CN/ja/en)
├── tests/              # Test suite (Pytest)
└── windows/            # Windows launcher (PyWebView)
```

### Building Packages

```bash
source venv/bin/activate
python build.py          # Windows
python build_macos.py    # macOS
```

---

## Troubleshooting

> 💡 See the Troubleshooting document included in the ZIP, or check the [GitHub Wiki](https://github.com/slive777/OpenAver/wiki).

---

## Community & Reporting Issues

Join the [Telegram group](https://t.me/+J-U2l96gv0FjZTBl) to discuss with other users!

| Channel | Best For |
|---------|----------|
| [GitHub Issues](https://github.com/slive777/OpenAver/issues) | Bug reports, feature requests, dev discussions |
| [Telegram group](https://t.me/+J-U2l96gv0FjZTBl) | Privacy-sensitive issues, direct screenshot/video uploads |

**When reporting**: include a description, steps to reproduce, OS version, and log file (run the Debug startup script to generate one).

---

## Acknowledgements

OpenAver is built on these excellent open-source projects:

- **[FastAPI](https://fastapi.tiangolo.com/)** — Modern, high-performance Python web framework
- **[PyWebView](https://pywebview.flowrl.com/)** — Lightweight cross-platform desktop shell
- **[GSAP](https://gsap.com/)** — Professional-grade JavaScript animation engine
- **[DaisyUI](https://daisyui.com/)** — Component library for Tailwind CSS
- **[Tailwind CSS](https://tailwindcss.com/)** — Utility-first CSS framework
- **[Alpine.js](https://alpinejs.dev/)** — Lightweight reactive JavaScript framework

## License

MIT License

---

<details>
<summary>⚠️ Disclaimer</summary>

This project is intended for personal, non-commercial use only. By using OpenAver, you agree to:
- Respect the terms of service of any website you scrape
- Use reasonable request rates to avoid overloading external services
- Not use this software for commercial purposes

You assume full responsibility for any consequences arising from your use of this project.

</details>
