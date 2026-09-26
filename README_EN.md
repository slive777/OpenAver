<!-- OpenAver: free open-source desktop GUI JAV metadata scraper & manager. No Docker, no CLI,
one-line install (Windows/macOS). Reads NFO + covers already organized by JavSP/EverAver/MDCX/
Jellyfin/Emby without re-scraping. Cover-wall browser with actress as a first-class entity
(cup/age/height sort, cross-language alias) plus a library-insights dashboard. 8 built-in scrape
sources (JavBus/Jav321/JavDB/DMM/D2Pass/HEYZO/FC2/AVSOX) + optional Metatube federation (30+).
Optionally exports NFO + covers to Jellyfin/Emby/Kodi. AI-operable REST API, 8,000+ tests, MIT. -->

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>Your ID collection — browse by cover, find by actress.</strong><br>
  Works right after install on Windows/Mac, no Docker, no command line · Bring in videos you already organized and browse them right away, no re-scraping needed
</p>

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-0078D6.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)
![Downloads](https://img.shields.io/github/downloads/slive777/OpenAver/total?color=success)
![Stars](https://img.shields.io/github/stars/slive777/OpenAver)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://img.shields.io/github/actions/workflow/status/slive777/OpenAver/test.yml?label=tests%208%2C000%2B)

English | **[繁體中文](README.md)**

Point OpenAver at the folder where you keep your videos and it turns them into a cover wall: click a cover to see stills and tags, click an actress to see all her titles, click a tag to find similar ones; whatever's missing, one click fills it in from the web.

**Videos another tool already organized get read in as-is — no re-scraping needed.** If a video already has a data file next to it (NFO — a small file that holds the title, actress, and tags) and a cover image, scanning reads it in directly and the files themselves never change — whether it was organized by JavSP, MDCX, EverAver, any other tool that writes a standard NFO + cover, or even Jellyfin/Emby's own output. Once organized, OpenAver can also generate the data files and covers Jellyfin/Emby/Kodi need for your TV's media player; don't want to install those, OpenAver on its own can browse your whole collection.

**By default, nothing about your videos is changed, moved, or deleted.** Filling in missing metadata only adds a data file and images next to the video. Only when you press "Organize" does it rename or relocate files — following the rules you set — and it never deletes. The program runs on your own computer; no account needed.

**100% local** — no data collection, no uploaded file info. Network requests are only used to scrape publicly available metadata.

⚡ **[Live Demo → openaver.slive.uk](https://openaver.slive.uk/)**

*Just mecha villains and fictional movie posters inside — zero NSFW. Safe even if your boss walks by.*

## Spec Sheet

| Item | Details |
|------|---------|
| **Platform** | Windows 10/11 · macOS (Apple Silicon, M1 and later) |
| **Install** | One-line command or double-click installer, no Docker, everything runs in the GUI |
| **Inherit an existing collection** | Reads the NFO and cover images already sitting next to your videos — scanning never changes your files |
| **Collection browsing** | Cover wall with stackable filters; actresses get their own wall, sortable by cup size / age / height |
| **Library insights** | Charts for count, year, maker, actress, tag; click any chart to narrow the view |
| **Phone & tablet** | Phones/tablets on the same Wi-Fi can browse it in a browser; closed to the outside world by default, password optional |
| **Scrape sources** | Queries 8 sources at once (JavBus/Jav321/JavDB/DMM/D2Pass/HEYZO/FC2/AVSOX); 2 more archive sources need manual verification; advanced users can add Metatube for 30+ total |
| **Media player output** | Organizing can generate the NFO and covers Jellyfin/Emby/Kodi need; works even for videos on a NAS you never move |
| **AI control** | AI tools like Claude Code/Cursor can organize your library directly from instructions |
| **AI translation** | Ollama (local, free)/Gemini/OpenAI-compatible endpoints |
| **License** | MIT, 100% local, no account, no cloud |

## Screenshots

| Search | Actress Collection |
|--------|--------------------|
| ![Search](docs/screenshots/home-en.png) | ![Actress](docs/screenshots/showcase-actress.png) |

<details>
<summary>More screenshots</summary>

| Search Demo | Actress Gallery |
|-------------|-----------------|
| ![Search Demo](docs/screenshots/demo2.gif) | ![Search](docs/screenshots/search-detail.png) |

| Showcase Video Mode | Showcase Detail |
|----------------------|------------------|
| ![Grid](docs/screenshots/showcase-grid.png) | ![Detail](docs/screenshots/showcase-detail.png) |

</details>

---

## Installation

### One-Line Install

**macOS** (open "Terminal" and paste this):
```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash
```

**Windows** (open PowerShell and paste this):
```powershell
irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex
```

> 💡 Don't want to open PowerShell? Download `OpenAver-Windows-Setup.bat` from [Releases](https://github.com/slive777/OpenAver/releases/latest) and double-click to install.

The install command automatically downloads the latest version, clears the system's security restrictions, and creates a desktop shortcut (Windows); upgrading keeps your settings, and the installer UI follows your system language.

### Manual ZIP Download

Download from [GitHub Releases](https://github.com/slive777/OpenAver/releases/latest):

| Platform | File |
|----------|------|
| **Windows x64** | `OpenAver-vX.X.X-Windows-x64.zip` |
| **macOS arm64** | `OpenAver-vX.X.X-macOS-arm64.zip` |

> ⚠️ The manual ZIP needs one extra step to clear security restrictions — see the included document. macOS is Apple Silicon only.

The first time you open it, an onboarding tour walks you through picking a folder and pressing "Generate" — no need to read the docs first.

> 🐧 **Linux**: No official installer, but you can set it up yourself as a LAN server and use it from a browser — see [`docs/linux-server.md`](docs/linux-server.md).

---

## Four Pages

OpenAver has four main pages:

1. **📋 Scanner**: Add the folders where you keep your videos and press "Generate"; titles with data files go straight into the library, missing ones get one-click completion.
2. **🎬 Showcase**: The cover wall. Browse your collection, filter, view stills, find similar titles, and manage actresses.
3. **🔍 Search**: Where newly downloaded videos get processed — drag in, look up metadata, and press "Organize" to move them into your collection.
4. **📊 Insights**: A breakdown of your whole library, click anything to narrow the view.

---

## Core Features

### 📋 Scanner: Bring your existing collection in first

- **Recognizes what others already organized**: reads a `.nfo`'s title, actress, tags, maker, series, and date; for covers, it recognizes same-name images, `-poster`/`-fanart` suffixes, `poster`/`fanart`/`cover`/`folder` files in the folder, or any image path written in the NFO, and reads `extrafanart/` too.
- **Scanning only reads, never writes**: not a single byte in the source folder is touched.
- **Fills only what's missing**: titles missing an NFO or cover are listed, one click fills them in from the web; only empty fields are filled, existing data is never overwritten.
- **Actress/tag aliases**: add aliases right in the UI; Chinese/Japanese/English synonyms auto-expand, and one person's stage names and post-retirement name are collapsed into a single card.
- **Reorder sources yourself**: drag to set your preferred order, one click switches to "uncensored mode."
- **Keeps subtitles, preserves VR tags when relocating**: subtitle files move along with the video, VR projection tags (`_180_LR`, `mkx200`) are preserved so your media player still recognizes the format.

### 🎬 Showcase: Browse by cover, find by actress

**A media player finds videos by filename; here you browse by cover, tag, and actress.**

- **Cover wall + Lightbox**: click a cover to see stills, tags, and actress info; uncensored covers auto-crop centered on the face, drag to adjust manually if needed.
- **Collected actresses show their age on release day**: her name is followed by something like `(28y)` — her age on the day that title released.
- **Stackable filters**: clicking an actress, tag, maker, director, or series ANDs them into a removable pill; clicking is an exact match, typing your own keywords stays fuzzy.
- **One-click switch between landscape cover and portrait card**: a landscape JAV cover's front is its right half, so portrait cards fit more per row — purely a display change.
- **Actress mode**: actresses get their own wall, profile cards with height, cup size, measurements, age, alias history; sortable and filterable.
- **Fill the actress wall from your own library**: press `+` for a list of who's in your library and how many titles each has, aliases merged; tap the heart to add.
- **Similar exploration**: tap the wand and similar titles orbit the main cover, pure local rule-based matching, offline, instant, no GPU needed.
- **Shows up right after organizing, and says so when unreachable**: a title organized on Search flies straight into Showcase if in range; if your library location goes offline, the status bar names which one.
- **Browse on phone or tablet too**: flip to "Server" mode in Settings, same-Wi-Fi devices browse via URL, flip back to close access immediately; interface redesigned for touch.
- **Browse offline too**: one click in Settings exports a standalone HTML file, browse without opening the app.

### 🔍 Search: where new titles come in

- **Queries all 8 sources at once**: results are automatically matched against your library and flagged if already collected; JavDB goes through its official app's data channel, so it still works even when blocked, and covers come back without a watermark.
- **Drag in files or a folder**: IDs are recognized automatically, metadata is looked up in batch, and covers and stills are pulled in. Dropping a folder **only reads the videos at that top level, not subfolders** — for your whole library, add it under Scan Folders on the Scanner page instead. You can also search by ID, actress name, series, or maker; version markers like UC/LEAK/4K become tags automatically.
- **Look before you organize**: metadata comes up in a detail view first — only once confirmed do you press "Organize" to rename, create the folder, write the NFO, and download the cover.
- **Wishlist**: save a title you're interested in but haven't picked up yet — its cover is saved locally right away, so it won't break if the source site goes down; it drops off automatically once collected.
- **Scheduled Organize**: a toggle next to "Favorites" runs a "look up → Organize" pass on that folder every 12 hours automatically; you can also press "Run now."
- **Advanced re-scrape**: change the ID and pick a source to re-fetch, preview before deciding whether to overwrite; by default your current title is kept, and the NFO title format is customizable in Settings.

### 📊 Insights: turn your whole library into charts

- **See your library's shape at a glance, then dig deeper**: total count/year/focus at the top, then a per-year bar chart, a two-ring maker pie chart, an actress Top 20, and a tag treemap; one level deeper is actress age-on-release distribution, top directors/series, a per-actress maker timeline, and who she's most often paired with.
- **Click anything to narrow the view**: click a year, an actress, or a maker and every chart narrows to that scope; click again to clear it.

### 📀 Read-only sources: videos on a NAS stay untouched and still reach your media player

Want to plug a NAS or cloud mount into Jellyfin/Emby/Kodi without copying terabytes of original files? Mark that source **read-only**.

- **Not a single byte of the source is touched**: the NFO, covers, and stills OpenAver fetches are all written to a local output folder you choose.
- **`.strm` feeds your media player directly**: a tiny file that only says where the video actually is — Emby/Jellyfin/Kodi play the original file directly, no copying needed.
- **Works even when the two machines see different paths**: set up a replacement rule and it rewrites paths automatically; existing `.strm` files get updated too.

### 🌐 AI Translation

- One click translates Japanese titles into your UI language.
- Supports **Ollama** (local, free), **Gemini Flash**, and **OpenAI-compatible endpoints**.

### 🔌 Metatube Federation (Advanced, Optional)

The 8 built-in sources work out of the box. Connect your self-hosted [Metatube](https://github.com/metatube-community/metatube-sdk-go) in Advanced Settings for **30+ community-maintained providers**, covering uncensored titles and niche makers; leaving it off has zero effect on the default experience.

### 🤖 AI-Ready API

OpenAver runs a local endpoint that publishes a description file (capabilities manifest); an AI tool reads it and can chain multiple steps to do the things too tedious for a person to bother with:

- **"Add my top 20 actresses by video count to Favorites, skip the ones already saved."**
  <sub>SQL stats → dedup check → batch favorite → download photos</sub>
- **"橋本ありな and 新ありな are the same person and she's retired — add a tag for that."**
  <sub>Create alias link → find every title under both names → batch-tag "retired"</sub>
- **"Turn the IDs mentioned in this article into an HTML page with covers."**
  <sub>Parse IDs → batch search → download covers → generate gallery HTML</sub>

One curl teaches your AI every endpoint on its own (the port is shown in the "AI API" section of the Settings page):

```bash
curl http://localhost:<port>/api/capabilities
```

<details>
<summary>Supported AI tools · Advanced usage · Power-user easter egg</summary>

Works with any function-calling AI tool:

| Method | Tool | Notes |
|--------|------|-------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider, etc. | curl straight from the terminal |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae, etc. | Agent mode calls the local REST API |
| **Desktop App** | Codex App, Google Antigravity 2.0, Claude Cowork, OpenClaw | No dev environment needed |

> 💡 Want to see covers right in the chat? **Codex App** and **Google Antigravity 2.0** both support inline display.

> ⚡ **Small-model friendly**: the manifest is optimized for lightweight models — Gemini Flash/GPT mini/Claude Haiku can all operate it correctly.

> 💻 **Want your AI to pre-read the repo?** Every endpoint is defined in [`web/routers/capabilities.py`](web/routers/capabilities.py) — an AI agent cloning the repo reads this file first and learns every tool without starting the server.

> 🪄 **Power-user easter egg: auto-find actresses in FC2 titles.** Almost no FC2 video has an actress tag, but plenty later debuted in censored titles. SQL pulls titles with an empty actress field → DeepFace matches them against Gfriends → `POST /api/user-tags` writes it back; 50 lines of Python chew through your whole library, unidentified ones get auto-clustered via DBSCAN.

</details>

---

## FAQ

**Can videos organized by OpenAver be used with Jellyfin/Emby/Kodi, or alongside them?**
Yes. Organizing also generates the NFO and cover art (poster/fanart) they read, and once they scan that folder, the cover and metadata show up correctly. OpenAver handles finding titles, fetching metadata, and browsing by cover and actress; they handle playback, and you don't need them installed either — OpenAver alone is enough to browse your whole collection.

**My videos are on a NAS or cloud drive and I don't want them moved or changed — can I still use OpenAver?**
Yes — mark that folder as "read-only." The original files are never moved or changed; fetched data files and covers go to a separate local output folder, and it can also generate `.strm` files so your media player streams the originals directly. Works for a NAS, a cloud drive mounted as a disk, or an external drive.

**Will OpenAver move, rename, or delete my files?**
Files are only moved or renamed when you press "Organize," and it never deletes; a same-name file at the target warns you first. Search, browsing, and scanning are all read-only; filling in missing metadata only adds an NFO and cover, the video itself is never touched.

**I want to switch computers or back things up — what do I need to copy?**
Your settings, library database, actress photos, thumbnails, and wishlist covers all live together in `app/output/`; copy that one folder to move machines or back up.

**Does it work on Mac? Do I need Docker?**
Yes, Apple Silicon only (M1 and later), install with one command or by downloading the ZIP; no Docker needed, it's a desktop app you use with a mouse.

**Can I browse the videos on my computer from my phone or tablet?**
Yes — turn on "Server" in Settings on the same Wi-Fi and open the URL in your phone's browser; turn it off when done, never exposed to the outside internet by default.

**What if one of the built-in scrape sources stops working?**
The 8 built-in sources back each other up; JavDB also has a channel through its official app's data path, so it usually still works even when blocked. Advanced users can connect Metatube for 30+ more sources.

**Can I still get metadata for titles the official sites have taken down?**
Yes — the desktop app connects to JavLibrary and FC2-javten, both behind Cloudflare human verification; a real browser window pops up once, then it auto-retries and fills in the result. These two only support manual exact-ID lookup in the desktop app — no batch search, not exposed to AI.

**Can AI tools operate OpenAver?**
Yes — OpenAver publishes a local description file (capabilities manifest); tools like Claude Code and Cursor read it with one curl and then organize your library, batch-favorite actresses, and add tags from instructions.

**On Windows, can it keep running in the background after I close the window?**
Yes — it minimizes to the system tray and keeps running; click the icon to reopen. Clicking the X asks whether to exit or minimize, with a "don't ask again" option; change this later under Settings → System.

---

## Developer Guide

<details>
<summary>Tech stack · Run from source · Directory structure · Building</summary>

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.12) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + Fluent Design 2 |
| **Animation** | GSAP 3.14+ + Motion Adapter (reduced-motion support) |
| **Desktop** | PyWebView (Windows/macOS) |
| **Database** | SQLite (WAL mode) |
| **Testing** | Pytest (8,000+ tests) |

### Run from Source

**Prerequisites**: Python 3.12 (matches the packaged build), Chrome/Edge, [WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

```bash
git clone https://github.com/slive777/OpenAver.git
cd OpenAver
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Development mode (hot reload)
uvicorn web.app:app --reload --reload-include 'locales/*.json' --host 127.0.0.1 --port 8000

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
│   │   ├── capabilities.py  # 🌟 AI Manifest — self-describing definitions for every endpoint (single file)
│   │   └── ...              # Other business endpoints (search / scanner / scraper / actress / ...)
│   ├── templates/      # HTML templates (DaisyUI + Fluent Design 2)
│   └── static/         # CSS/JS assets (modular JS, theme CSS)
├── core/               # Core logic
│   ├── scrapers/       # Modular scrapers (JavBus/JavDB/Jav321/FC2/AVSOX/DMM/D2Pass/HEYZO + manual sources JavLibrary/FC2-javten)
│   ├── database/       # SQLite data layer package (connection/video/actress/alias/tag_alias/migrate, WAL)
│   ├── metatube/       # Metatube federation integration
│   ├── similar/        # Rule-based similar-title ranking (tag IDF + series/maker/actress)
│   ├── focal/          # Uncensored-cover face-focus cropping
│   ├── gallery_scanner.py    # Folder scanning & library import (reads existing NFO/covers)
│   ├── organizer.py    # File organizing + null-value fallback guards
│   ├── readonly_producer.py  # Read-only source → NFO/cover/.strm output
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

</details>

---

## Troubleshooting

> 💡 See the Troubleshooting document included in the packaged ZIP, or check the [GitHub Wiki](https://github.com/slive777/OpenAver/wiki).

---

## Community & Reporting Issues

Join the [Telegram group](https://t.me/+J-U2l96gv0FjZTBl) to chat!

| Channel | Best For |
|---------|----------|
| [GitHub Issues](https://github.com/slive777/OpenAver/issues) | Bug reports, feature requests, dev discussions |
| [Telegram group](https://t.me/+J-U2l96gv0FjZTBl) | Privacy-sensitive issues, direct screenshot/video uploads |

**When reporting, please include**: a description, steps to reproduce, OS version, and the log file (from the Debug startup script).

---

## Acknowledgements

OpenAver uses and is grateful for these open-source projects:

- **[FastAPI](https://fastapi.tiangolo.com/)** — Modern Python web framework
- **[PyWebView](https://pywebview.flowrl.com/)** — Lightweight cross-platform desktop framework
- **[GSAP](https://gsap.com/)** — High-performance JavaScript animation engine
- **[DaisyUI](https://daisyui.com/)** — Component library for Tailwind CSS
- **[Tailwind CSS](https://tailwindcss.com/)** — Utility-first CSS framework
- **[Alpine.js](https://alpinejs.dev/)** — Lightweight JavaScript framework
- **[Apache ECharts](https://echarts.apache.org/)** — Charting library for the Library Insights page

Full list of third-party package versions and licenses: [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md).

## License

MIT License

---

<details>
<summary>⚠️ Disclaimer</summary>

This project is intended for personal, non-commercial use only. By using OpenAver, you agree to:
- Respect the terms of service of any website you scrape
- Use reasonable request rates
- Not use this software for commercial purposes

You assume full responsibility for any consequences arising from your use of this project.

</details>
