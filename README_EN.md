<p align="center">
  <img src="docs/logo.svg" alt="OpenAver Logo" width="200">
</p>

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>Modern JAV metadata manager — scrape, organize, and generate HTML showcases.</strong>
</p>

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

**🌐 English** | [繁體中文](README.md)

## 📸 Screenshots

![Home](docs/screenshots/home.jpg)

<details>
<summary>More Screenshots</summary>

| Search Demo | Showcase Demo |
|-------------|---------------|
| ![Search Demo](docs/screenshots/demo.gif) | ![Showcase Demo](docs/screenshots/demo2.gif) |

| Search Results | Showcase Grid | Showcase Detail |
|----------------|---------------|-----------------|
| ![Search Results](docs/screenshots/search-detail.png) | ![Showcase Grid](docs/screenshots/showcase-grid.png) | ![Showcase Detail](docs/screenshots/showcase-detail.png) |

</details>

## ⚠️ Disclaimer

This project is intended for personal, non-commercial use only. By using OpenAver, you agree to:
- Respect the terms of service of any website you scrape
- Use reasonable request rates to avoid overloading external services
- Not use this software for commercial purposes

You assume full responsibility for any consequences arising from your use of this project.

## 🔒 Privacy

OpenAver runs entirely on your local machine:
- ✅ No user data is collected
- ✅ No file information is uploaded to remote servers
- ✅ All operations execute locally on your computer
- ⚠️ Network requests are made only to scrape publicly available metadata

---

## ✨ Features

### 🤖 AI-Ready API

Your AI assistant can now operate your library directly:

- "Search STARS-123, ABP-456, SSIS-789 for me" — multi-source aggregation
- "Fill in the missing NFO for these 10 old files" — in-place enrichment, no rename, no move
- "Which series did I download the most this year?" — SQL queries on your collection
- "Turn the IDs mentioned in this article into a visual gallery" — auto-embedded cover HTML

No SDK. No docs to read. One curl, and your AI learns every endpoint:

```bash
curl http://localhost:38741/api/capabilities
```

Works with any MCP / function-calling compatible AI tool.

### 🔍 Spotlight Search

What sets OpenAver apart is its **multi-source aggregation**: a single query simultaneously searches JavBus, JavDB, Jav321, DMM, D2Pass, and HEYZO, merging results in real time.

- **Multi-Source Aggregation**: Simultaneous search across JavBus, JavDB, Jav321, DMM, D2Pass, HEYZO — one query, all sources.
- **Hero Detail UI**: Large cover images with frosted-glass overlay for an immersive browsing experience.
- **Smart Search**: Automatic ID normalization, prefix search, and actress name search.
- **Version Tagging**: Auto-detects UC/LEAK/4K suffixes; `{suffix}` format variable supported in file naming.
- **Actress Gallery Mode (Beta)**: When an actress search returns more than 10 titles, the view automatically switches to a gallery layout with a full actress profile Hero Card.
- **Local File Search**:
  - Drag-and-drop file filtering (by extension and size threshold)
  - Batch search: 20 files per batch, 2 concurrent requests
  - Pause / resume + batch AI translation
  - One-click load from Favorites folders
  - Open folder in system file manager

### 📝 Scanner

- **Static HTML Showcase**: Scan a local video folder and generate a self-contained, offline-ready HTML index — no server required to view it.
- **Mini Terminal**: Embedded terminal widget with real-time progress output during scanning.
- **NFO Completion**: Automatically detects and fills in missing NFO metadata files.
- **Jellyfin Integration**: Auto-generates `poster`, `thumb`, and `fanart` image files in the format Jellyfin expects — just point your library and go.
- **Cache Management**: One-click cache clear with two-step confirmation.

### ⚙️ Settings

- **Dark Mode**: Full dark mode support, automatically applied to generated Showcase viewers.
- **AI Translation**: Configure Ollama (local) or Gemini (cloud) as your translation provider.
- **Path & Naming Rules**: Flexible output path configuration with `{suffix}` variable support.
- **Favorites Folders**: Save frequently used folders for one-click batch loading.
- **File Filtering**: Set minimum video size (MB) to automatically exclude small non-video files.

### 🌐 AI Translation

OpenAver supports two translation backends that translate Japanese titles into your preferred language:

| Provider | Highlights | Speed |
|----------|-----------|-------|
| **Ollama (local)** | Free, no API limits, requires local GPU | ~0.5 s/title |
| **Gemini (Google)** | Cloud API, free tier 15 RPM | ~0.1 s/title |

Translation language automatically follows the UI locale setting (Traditional Chinese, Simplified Chinese, or English). Japanese UI locale skips translation since titles are already in Japanese.

**⚠️ Gemini API Key Security**

- Your API key is stored in plaintext in `web/config.json`
- **Do not share `config.json` or upload it to a public location**
- To revoke: visit [Google AI Studio](https://aistudio.google.com/apikey) and regenerate your key

### 🤖 Agentic AI Support

OpenAver's self-describing API works with all major AI tools:

| Method | Tools | Notes |
|--------|-------|-------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider, etc. | Just `curl` from the terminal — all CLI agents supported |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae, Google Antigravity, etc. | Agent mode / MCP to call local API |
| **Desktop App** | Codex App, Claude Cowork, OpenClaw | ⭐ Cover images rendered inline — best experience |

> 💡 **Recommended**: **Codex App** (free tier available) — cover images embedded directly in responses for at-a-glance browsing.

> ⚡ **Small-model friendly**: The capabilities manifest is optimized for lightweight models — Gemini Flash / GPT-4o mini / Claude Haiku can all operate every endpoint correctly.

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.10+) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x |
| **Animation** | GSAP 3.14+ with Motion Adapter (respects `prefers-reduced-motion`) |
| **Desktop Shell** | PyWebView (Windows / macOS) |
| **Database** | SQLite (WAL mode) |
| **i18n** | 4 locales: Traditional Chinese, Simplified Chinese, Japanese, English |
| **Testing** | Pytest — 1600+ tests (unit + integration, fully mocked) |

## 📥 Installation

### Recommended: One-Line Install

The install script handles all platform-specific setup automatically — security flags, shortcuts, and clean upgrades included.

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
- Removes macOS quarantine flags (no manual `xattr` needed)
- Unblocks Windows download restrictions (no manual Unblock needed)
- Creates a desktop shortcut (Windows)
- Preserves your settings and logs on upgrade
- Cleans up the old Python runtime to prevent version conflicts

### Alternative: Manual ZIP Download

If your network environment blocks running scripts (corporate proxy, etc.), download from [GitHub Releases](https://github.com/slive777/OpenAver/releases/latest):

| Platform | File |
|----------|------|
| **Windows x64** | `OpenAver-vX.X.X-Windows-x64.zip` |
| **macOS arm64** | `OpenAver-vX.X.X-macOS-arm64.zip` |

**⚠️ Manual ZIP install** requires additional steps to clear platform security restrictions — see the Troubleshooting section below.

> ℹ️ macOS builds target Apple Silicon (M1/M2/M3/M4) only.

---

## 🚀 Quick Start (from Source)

### Prerequisites
- Python 3.10+
- Chrome or Edge (used by PyWebView)
- **Microsoft Edge WebView2 Runtime** (required on Windows 10 and VMs)

### Setup
```bash
# 1. Clone the repository
git clone https://github.com/slive777/OpenAver.git
cd OpenAver

# 2. Create a virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Run
```bash
# Development mode (hot reload)
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# Desktop mode (Windows)
python windows/launcher.py
```

## ❓ Troubleshooting

> 💡 If you used the recommended **one-line install**, most issues below do not apply. This section is primarily for manual ZIP installations.

### Upgrading (ZIP Manual Install)

Overlaying a new ZIP on an existing installation can leave stale Python packages behind, causing startup failures or version conflicts. **Before upgrading, delete the `python` folder**, then extract the new ZIP:

- **Windows**: Delete `%USERPROFILE%\OpenAver\python\`
- **macOS**: Delete `~/OpenAver/python/`

> 💡 The one-line installer handles this automatically.

### ZIP Install Issues

#### 1. Windows — App Won't Start / Crashes Immediately

**Cause**: Windows Mark of the Web security blocks executables and DLLs downloaded from the internet.

**Fix**:
1. Right-click the downloaded `OpenAver-Windows-x64.zip`
2. Select **Properties**
3. At the bottom, check **Unblock**, then click OK
4. Re-extract the ZIP and run `OpenAver.bat`

*Alternatively, extract with 7-Zip — it typically bypasses this restriction.*

**Startup scripts**:
- **OpenAver.bat** — Normal launch (startup banner only, no verbose logging)
- **OpenAver_Debug.bat** — Debug launch (console window with full log output)

**When something goes wrong, run `OpenAver_Debug.bat`**:
1. Double-click `OpenAver_Debug.bat`
2. The console shows detailed error messages
3. Logs are saved to: `%USERPROFILE%\OpenAver\logs\debug.log`
4. Attach the console output or log file to a [GitHub Issue](https://github.com/slive777/OpenAver/issues)

#### 2. macOS — App Blocked by Gatekeeper

**Cause**: macOS Gatekeeper blocks unsigned applications.

**Full install steps** (copy and paste each command):

**[Step 1]** Download the ZIP
- Safari auto-extracts it; look for the folder in your Downloads directory

**[Step 2]** Open Terminal
- Press ⌘ + Space to open Spotlight
- Type `Terminal` and press Enter

**[Step 3]** Navigate to the folder
```bash
cd ~/Downloads/OpenAver
```

**[Step 4]** Remove the quarantine flag (required)
```bash
xattr -dr com.apple.quarantine .
```

**[Step 5]** Launch the app
```bash
./OpenAver.command
```

💡 After the initial setup, you can double-click `OpenAver.command` directly.

**Startup scripts**:
- **OpenAver.command** — Normal launch (background process, no log output)
- **OpenAver_Debug.command** — Debug launch (terminal shows detailed logs)

**When something goes wrong, run `OpenAver_Debug.command`**:
1. Double-click `OpenAver_Debug.command` (or run `./OpenAver_Debug.command` in Terminal)
2. The terminal displays detailed log output
3. Logs are also saved to: `~/OpenAver/logs/debug.log`
4. Attach the log file to a [GitHub Issue](https://github.com/slive777/OpenAver/issues)

### All Installation Methods

#### Blank UI / Missing Frosted-Glass Effects

**Cause**: Missing WebView2 Runtime or insufficient GPU acceleration (common on Windows 10 and virtual machines).

**Fix**: Download and install the [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703).

## 💬 Community

Join the [Telegram group](https://t.me/+J-U2l96gv0FjZTBl) to discuss with other users!

---

## 🐛 Reporting Issues

Found a bug or want to request a feature? Please report through one of the following channels:

### 📌 General Issues / Feature Requests
→ [GitHub Issues](https://github.com/slive777/OpenAver/issues)
- Best for developer discussions and feature requests
- Issues and solutions are archived for others to find

**Please include**:
- What went wrong
- Steps to reproduce
- Your environment (OS version, packaged build or source)
- Log file (if available)

### 🔒 NSFW / Privacy-Sensitive Issues
→ [Telegram group](https://t.me/+J-U2l96gv0FjZTBl)
- Private channel — supports direct screenshot and video uploads
- Use when you cannot share content publicly

### Getting Logs (Windows Packaged Build)
1. Run `OpenAver_Debug.bat`
2. Reproduce the issue
3. Log location: `%USERPROFILE%\OpenAver\logs\debug.log`
4. Attach the log file to a GitHub Issue or Telegram message

---

## 🧪 Running Tests

The project includes API integration tests and core logic unit tests.

```bash
source venv/bin/activate
pytest
```

## 📂 Directory Structure

```
OpenAver/
├── web/                # Web GUI (FastAPI)
│   ├── routers/        # API endpoints (Search, Config, Scraper, Scanner)
│   ├── templates/      # HTML templates (DaisyUI + Fluent Design 2)
│   └── static/         # CSS/JS assets (modular JS, theme CSS)
├── core/               # Core logic
│   ├── scrapers/               # Modular scrapers (JavBus/JavDB/Jav321/FC2/AVSOX/DMM/D2Pass/HEYZO)
│   ├── database.py             # SQLite data layer (WAL mode)
│   ├── organizer.py            # File organizer + null-value fallback guards
│   ├── path_utils.py           # Cross-platform path handling (file:// URI)
│   └── translate_service.py    # AI translation (Ollama/Gemini)
├── tests/              # Test suite (Pytest)
└── windows/            # Windows launcher (PyWebView)
```

## Building the Windows Package

```bash
# Run inside the virtual environment
source venv/bin/activate
python build.py
```

## 🙏 Acknowledgements

OpenAver is built on these excellent open-source projects:

- **[FastAPI](https://fastapi.tiangolo.com/)** — Modern, high-performance Python web framework
- **[PyWebView](https://pywebview.flowrl.com/)** — Lightweight cross-platform desktop shell
- **[GSAP](https://gsap.com/)** — Professional-grade JavaScript animation engine
- **[DaisyUI](https://daisyui.com/)** — Component library for Tailwind CSS
- **[Tailwind CSS](https://tailwindcss.com/)** — Utility-first CSS framework
- **[Alpine.js](https://alpinejs.dev/)** — Lightweight reactive JavaScript framework

Many thanks to all the contributors who make these projects possible.

## License

MIT License
