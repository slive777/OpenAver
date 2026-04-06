<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>No Docker, no CLI — one-line install for Win/Mac, full GUI JAV metadata manager out of the box.</strong><br>
  Multi-source search · Beautiful HTML showcases · Jellyfin integration · AI API to manage your library with a single prompt
</p>

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

**English** | [繁體中文](README.md)

The core workflow spans three pages: 🔍 Search video info → 📋 Generate showcase → 🎬 Browse collection

**100% local** — no data collection, no uploads. Network requests are only used to scrape publicly available metadata.

## Screenshots

![Search Hero Detail](docs/screenshots/home-en.png)

<details>
<summary>More Screenshots</summary>

| Search Demo | Actress Gallery |
|-------------|-----------------|
| ![Search Demo](docs/screenshots/demo2.gif) | ![Search](docs/screenshots/search-detail.png) |

| Showcase Grid | Showcase Detail |
|---------------|-----------------|
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

> ⚠️ Manual ZIP install requires extra steps to clear security restrictions — see Troubleshooting below.
> ℹ️ macOS builds target Apple Silicon (M1/M2/M3/M4) only.

On first launch, a built-in setup wizard walks you through folder configuration and basic settings — no docs required.

---

## Features

### 🔍 Spotlight Search
- **Multi-Source Aggregation**: One query simultaneously searches JavBus, JavDB, Jav321, DMM, D2Pass, and HEYZO.
- **Detail View**: Cover, sample images, actress, tags — all in one place, no tab-hopping.
- **Smart Search**: Search by ID, actress name, series, or maker — results are matched against your local library and marked if already in your collection.
- **Version Detection**: Automatically identifies UC/LEAK/4K variants — no manual renaming needed.
- **Actress Gallery Mode (Beta)**: When an actress search returns 10+ titles, the view switches to a gallery layout with a full profile Hero Card.
- **Sample Gallery**: Browse full sample images directly from search results.
- **Local Batch Search**: Drag in video files or folders — automatically extracts IDs and batch-searches for metadata, covers, and sample images.

### 📝 Scanner
- **Showcase Pages**: Scan a local video folder and generate beautiful, interactive showcase pages (smooth animations + frosted-glass effects + Lightbox gallery).
- **Live Progress**: See exactly what's being scanned and updated in real time.
- **NFO Completion**: Automatically detects and fills in missing NFO metadata files.
- **Subtitle Detection**: Automatically detects and moves subtitle files when organizing videos.
- **Jellyfin Integration**: Auto-generates `poster`, `thumb`, and `fanart` images in the format Jellyfin expects.
- **Static HTML Export**: Also generates a standalone HTML index file — viewable offline without a server.

### 🌐 AI Translation
Most metadata fields (actress, maker, label, tags) are already in English from the source — but titles remain in Japanese. AI translation fills that gap automatically.
- Supports **Ollama** (local GPU, free & unlimited) and **Gemini Flash** (Google cloud, free tier available).
- Translation language follows your UI locale (English, Traditional Chinese, Simplified Chinese). Japanese locale skips translation since titles are already in Japanese.

### ⚙️ Settings
- **Dark Mode**: Full dark mode support, automatically applied to generated showcases.
- **Path & Naming Rules**: Flexible output path configuration with `{suffix}` variable support.
- **Favorites Folders**: Save frequently used folders for one-click batch loading.
- **Multi-Language UI**: Traditional Chinese, Simplified Chinese, Japanese, English — instant switch.

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
| **Testing** | Pytest — 1600+ tests |

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
│   └── translate_service.py  # AI translation (Ollama/Gemini)
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

> 💡 If you used the recommended **one-line install**, most issues below do not apply.

### Upgrading (ZIP Manual Install)

Overlaying a new ZIP can leave stale Python packages behind. **Before upgrading, delete the `python` folder**:

- **Windows**: Delete `%USERPROFILE%\OpenAver\python\`
- **macOS**: Delete `~/OpenAver/python/`

### Windows — App Won't Start / Crashes

**Cause**: Windows Mark of the Web blocks downloaded executables.

**Fix**:
1. Right-click the downloaded ZIP → **Properties**
2. Check **Unblock** → OK
3. Re-extract and run `OpenAver.bat`

*Alternatively, extract with 7-Zip to bypass this restriction.*

**Startup scripts**:
- `OpenAver.bat` — Normal launch
- `OpenAver_Debug.bat` — Debug launch (verbose logging), log file: `%USERPROFILE%\OpenAver\logs\debug.log`

### macOS — App Blocked by Gatekeeper

**Cause**: macOS Gatekeeper blocks unsigned applications.

Run in Terminal:
```bash
cd ~/Downloads/OpenAver
xattr -dr com.apple.quarantine .
./OpenAver.command
```

After initial setup, you can double-click `OpenAver.command` directly.

**Startup scripts**:
- `OpenAver.command` — Normal launch
- `OpenAver_Debug.command` — Debug launch, log file: `~/OpenAver/logs/debug.log`

### Blank UI / Missing Effects (All Install Methods)

**Cause**: Missing WebView2 Runtime (common on Windows 10 and VMs).

**Fix**: Download and install the [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703).

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
