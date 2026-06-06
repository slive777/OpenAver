<!-- OpenAver: free open-source desktop GUI JAV metadata scraper & manager.
No Docker, no CLI, one-line install (Windows/macOS), 8 built-in scrape sources
(JavBus/Jav321/JavDB/DMM/D2Pass/HEYZO/FC2/AVSOX) plus optional Metatube federation (30+ providers),
generates NFO + cover art (poster/fanart) for Jellyfin / Emby / Kodi,
actress favorites with cross-language alias expansion, cross-language tag aliases,
AI-operable REST API with capabilities manifest, 3,400+ tests, MIT license. -->

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>No Docker, no command line — one-line install for Win/Mac, a full GUI JAV metadata manager the moment you open it.</strong><br>
  8-source unified scraping · Actress favorites & alias management · Interactive collection browser · Jellyfin / Emby integration · An AI API that operates your library from a single prompt
</p>

<p align="center"><em>
  Open-source desktop GUI for JAV metadata — one-line install, 8 built-in scrape sources, actress favorites + alias system, Jellyfin/Emby/Kodi ready, AI-operable REST API.
</em></p>

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

**English** | [繁體中文](README.md)

> **OpenAver is a free, open-source desktop app (Windows/macOS, no Docker, no CLI) that scrapes JAV metadata from 8 sources and generates NFO files + cover art for Jellyfin, Emby, and Kodi — with actress collections, cross-language tag aliases, and a built-in REST API that lets AI agents operate your library.**

The core workflow spans three pages: 📋 Scan & build library → 🎬 Browse collection → 🔍 Per-ID scraping (advanced)

**100% local** — no data collection, no uploaded file info. Network requests are only used to scrape publicly available metadata.

**✨ Highlights**: Search 8 sources in one query · Toggle and drag-reorder scrape sources freely · Actress favorites with auto profiles + alias-expanded search · Cross-language tag aliases — Chinese/Japanese/English synonyms auto-expand consistently across the search box, chips, and similar-video exploration · One-click NFO & cover fill from the web · Rule-based similar-video exploration (no model download, offline, millisecond response) · Operate your library in natural language with AI · Jellyfin / Emby cover auto-generation · 3,400+ automated tests

⚡ **[Live Demo → openaver.slive.uk](https://openaver.slive.uk/)**

*Just mecha villains and fictional movie posters inside — zero NSFW, totally safe to open with your boss walking by.*

## Spec Sheet

| Item | Details |
|------|---------|
| **Platform** | Windows 10/11 · macOS (Apple Silicon M1–M4) |
| **Install** | One-line command or ZIP install (**no Docker**); once installed, everything runs in the GUI — **no CLI** |
| **Scrape sources** | 8 built-in (JavBus / Jav321 / JavDB / DMM / D2Pass / HEYZO / FC2 / AVSOX); advanced users can optionally federate **Metatube (30+ more providers)** |
| **Media server output** | NFO + cover art (poster / fanart) for **Jellyfin / Emby / Kodi** |
| **Actress collection** | Auto profiles + cross-language alias expansion + multi-source photo download |
| **AI control** | Built-in REST API + capabilities manifest (Claude Code / Cursor / Perplexity and other AI agents operate it directly) |
| **AI translation** | Ollama (local, free) / Gemini / OpenAI-compatible — your choice |
| **Data** | 100% local SQLite — **no cloud, no account, no telemetry** |
| **License** | MIT |

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
- **8-Source Unified Search**: One query simultaneously searches JavBus, Jav321, JavDB, DMM, D2Pass, HEYZO, FC2, and AVSOX — all sources at once.
- **Detail View**: Cover, stills, actress, tags — all in one place, no tab-hopping.
- **Smart Search**: Search by ID, actress name, series, or maker — results are matched against your local library and marked if already in your collection.
- **Actress Features**: Searching a favorited actress automatically shows her profile card; results can be added to your collection directly.
- **Version Detection**: Automatically identifies UC/LEAK/4K variants — no manual renaming needed.
- **Local Batch Search**: Drag in video files or folders — automatically extracts IDs and batch-searches for metadata, covers, and stills.
- **Advanced Re-Scrape**: For any title, change the ID and re-fetch from a specific source — preview the result card before deciding whether to overwrite.

### 🎬 Showcase
- **Video Mode**: Cover wall grid + detail Lightbox + search/filter/sort + stills browser — a full interactive collection viewer.
- **Actress Mode**: Favorited actress grid + profile Lightbox + sort by cup size / age / height — one-click refresh to pull updated data.
- **Visual Design**: GSAP animations + Fluent Design frosted-glass effects + Dark Mode, with SSR real-time rendering.

### 📋 Scanner (local scan & metadata management)
- **Scan & Build Library**: Scan local video folders, build a SQLite metadata database, automatically reads existing NFO files and covers.
- **NFO & Cover Completion**: Detects missing NFO fields or files and fills them in from the web with one click.
- **Scrape-Source Management**: Toggle each scrape source on/off and drag to reorder your preferred priority (want a particular site's covers? move it to the top) — changes take effect instantly; one click switches to "uncensored mode" to use uncensored sources only.
- **Actress Alias Management**: Add and edit aliases live through the GUI (no editing config files or XML) — searches automatically expand to all of a person's stage names and post-retirement names.
- **Tag Alias Management chip wall**: Manage cross-language synonyms in one place; the search box and Showcase chips auto-expand them at query time (Chinese/Japanese/English, e.g. "Maid＝メイド＝女僕").
- **Subtitle Detection**: Automatically detects and moves subtitle files in the same folder when relocating videos.
- **VR Filename Tag Preservation**: When organizing VR videos, automatically preserves the original filename's projection/stereo tags (e.g. `_180_LR`, `_3dh`, `mkx200`) so VR headset players (Skybox / DeoVR / HereSphere, etc.) detect the projection format correctly.

### ⚡ Search → Showcase, Made Instant
- **Same-Name NFO Skip**: If your favorites folder already has a `.nfo` next to the video, it's treated as organized and the scraper is skipped (avoids redundant external requests).
- **Scanner Tracked-Folder Dropdown**: In Settings, "My Favorites Folder" can be picked directly from Scanner's already-tracked folders, with inline live status (✓ linked / ⚠ not in tracking scope).
- **Instant DB Write + GhostFly Animation**: After organizing a title on the Search page, if the target path is within Scanner's tracking scope → it's written to SQLite immediately, and the cover flies from the source spot to the sidebar Showcase icon via a GhostFly animation — no manual rescan needed.

### 🌐 AI Translation
- Translate Japanese titles into your UI locale (Traditional Chinese, Simplified Chinese, English) in one click — Japanese locale skips translation since titles are already in Japanese.
- Supports **Ollama** (local GPU, free & unlimited), **Gemini Flash** (Google cloud, free tier available), and **OpenAI API Compatible** (OpenRouter, any compatible endpoint).

### 🔍 Similar-Video Exploration
- **No model download, no GPU, millisecond response, fully offline**: Uses multiple signals — tags, series, maker, year, cast — to surface videos with a similar style, all computed locally and usable offline. No need to download the hundreds of megabytes of models that image-similarity tools require.
- **Star-Field Exploration Animation**: In the Showcase Lightbox, tap the wand button → 12 stars orbit the main cover, champagne-gold lines connecting them to the center → tap any star to "dive in" and make it the new center for endless exploration.

### ⚙️ Settings
- **Multi-Language UI**: Traditional Chinese, Simplified Chinese, Japanese, English — instant switch.
- **Path & Naming Rules**: Flexible output path configuration with `{suffix}` variable support.
- **Favorites Folders**: Save frequently used folders for one-click batch loading.
- **Jellyfin / Emby Image Mode**: Auto-generates a `poster` + NFO (read by both Jellyfin and Emby), plus a Jellyfin `fanart` (Emby doesn't support this fanart filename).
- **Static HTML Export**: Generates a standalone HTML index file — viewable offline without a server.

### 🔌 Scrape-Source Expansion: Metatube Federation (advanced, optional)

The 8 built-in sources work out of the box, with no extra deployment required. If you want even more sources — or an extra layer of insurance for your library:

- **30+ more sources**: In advanced settings, connect your own self-hosted [Metatube](https://github.com/metatube-community/metatube-sdk-go) server and your scrape sources expand from the 8 built-ins to **30+ community-maintained providers**, strengthening coverage of uncensored and niche makers all at once.
- **A decoupled fallback layer**: Metatube is an actively maintained open-source scrape-source layer. Once connected, it acts as a decoupled fallback so that even if a built-in source temporarily breaks, your enrichment pipeline keeps running independently through Metatube.
- **Advanced and optional — it won't pollute the main path**: Metatube is self-hosted (Docker or binary) and aimed at advanced users. Leaving it disabled has zero impact on the default "no Docker, works out of the box" experience.

### 🤖 AI-Ready API

OpenAver ships a capabilities manifest — your AI agent reads it once and knows every endpoint. It doesn't just look things up; it chains multiple steps to handle the tedious work you'd never bother doing by hand.

**One sentence, full automated workflow:**

- **"Add my top 20 actresses by video count to favorites, skip ones already saved."**
  <sub>SQL stats → dedup check → batch favorite → download photos</sub>
- **"橋本ありな and 新ありな are the same person and she's retired — tag them."**
  <sub>Create alias link → find all videos under both names → batch-tag "retired"</sub>
- **"Turn the video IDs in this article into an HTML page with covers."**
  <sub>Parse IDs → batch search → download covers → generate gallery HTML</sub>

**Everyday operations work too:**

- "Search SAME-123, PRED-456, IPZZ-789 for me" — multi-source aggregation
- "Fill in the missing NFO in D:\av" — in-place enrichment, no rename, no move
- "Which series did I download the most this year?" — SQL query on your collection

No SDK. No docs to read. One curl, and your AI learns every endpoint:

```bash
curl http://localhost:<port>/api/capabilities
```

> The port and full URL are shown in the Settings page under "AI API".

Works with any MCP / function-calling compatible AI tool:

| Method | Tools | Notes |
|--------|-------|-------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider, etc. | Just `curl` from the terminal — all CLI agents supported |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae, etc. | Agent mode / MCP to call local API |
| **Desktop App** | Codex App, Google Antigravity 2.0, Claude Cowork, OpenClaw | No dev environment needed, works out of the box |

> 💡 **Recommended**: **Codex App (inline chat)** or **Google Antigravity 2.0 (artifact panel)** — both desktop apps display covers directly in your conversation flow. Easy to install, works out of the box.

> ⚡ **Small-model friendly**: The capabilities manifest is optimized for lightweight models — Gemini Flash / GPT mini / Claude Haiku can all operate every endpoint correctly.

> 💻 **Want your AI to pre-read the repo, or extend endpoints yourself?** Every endpoint is defined in [`web/routers/capabilities.py`](web/routers/capabilities.py) — AI agents cloning the repo will read this file first and learn every tool without even starting the server.

> 🪄 **Power-user easter egg: auto-identify actresses in FC2 videos.** FC2 videos almost never have actress tags, but many feature familiar faces who later debuted in censored productions (Shirakami Sakura is a classic case). SQL pulls titles with an empty actress field → DeepFace (RetinaFace + ArcFace) matches against the Gfriends library → `POST /api/user-tags` writes the tags back. 50 lines of Python runs your whole library over a weekend; manually favorite the ones you like, and unidentified amateurs get auto-clustered into groups via DBSCAN for direct matching next time.

---

## FAQ

**Does OpenAver need Docker?**
No. OpenAver is a desktop app installed with a single command on Windows / macOS — no Docker. Once installed, everything runs in the GUI, with no command line.

**Does OpenAver work on Mac?**
Yes. It runs on Windows 10/11 and macOS (Apple Silicon M1–M4).

**Which media servers does OpenAver support?**
It generates standard NFO files + cover art (poster / fanart) that Jellyfin, Emby, and Kodi can read directly.

**What is an NFO file?**
An NFO is an XML file placed next to your video that records the title, cast, tags, cover, and more, so media servers like Jellyfin / Emby / Kodi can display your videos correctly. OpenAver generates them for you automatically.

**Will OpenAver rename or move my files?**
By default, scanning only "reads" your files — it never touches them. Files are renamed or moved only when you actively run "organize," following the rules you set, and NFO/cover completion is written in place without moving anything.

**What if a built-in scraper source breaks?**
The 8 built-in sources fall back on one another, so if one source is temporarily down you can still fill in from the others. Advanced users can additionally federate a self-hosted Metatube server for 30+ more sources — extra insurance for your library so a single failing source never stalls you.

**A number won't scrape — what can I do?**
Use "Advanced Re-Scrape": change the ID and re-fetch from a specific source, and preview the result card before deciding whether to overwrite.

**Can AI tools operate OpenAver?**
Yes. With the built-in REST API + capabilities manifest, one `curl` teaches your AI every endpoint, and it can run multi-step workflows from a single prompt (see the AI-Ready API section above).

**Does OpenAver collect data or upload my local files?**
No. It runs 100% locally and never collects or uploads any file info; network requests are only used to scrape publicly available metadata.

---

## Developer Guide

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.12) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + Fluent Design 2 |
| **Animation** | GSAP 3.14+ with Motion Adapter (respects `prefers-reduced-motion`) |
| **Desktop Shell** | PyWebView (Windows / macOS) |
| **Database** | SQLite (WAL mode) |
| **Testing** | Pytest — 3,400+ tests |

### Run from Source

**Prerequisites**: Python 3.12 (matches the packaged build; other versions may work for venv development only, no guarantees), Chrome/Edge, [WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

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
│   ├── routers/
│   │   ├── capabilities.py  # 🌟 AI Manifest — self-describing definitions of every endpoint (single file)
│   │   └── ...              # Other business endpoints (search / scanner / scraper / actress / ...)
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
