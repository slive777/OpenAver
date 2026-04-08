<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>不需要 Docker，不需要命令列 — Win/Mac 一行安裝，打開就是完整圖形介面的 JAV 元數據管理工具。</strong><br>
  多來源聚合搜尋 · 精美 HTML 展示列表 · Jellyfin 整合 · AI API 一句話操作你的片庫
</p>

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

**[English](README_EN.md)** | 繁體中文

核心功能由三個頁面組成：🔍 搜尋影片資訊 → 📋 生成展示牆 → 🎬 瀏覽收藏

**100% 本地運行** — 不蒐集資料、不上傳任何檔案資訊，網路請求僅用於刮削公開元數據。

## 截圖預覽

![Search Hero Detail](docs/screenshots/home.png)

<details>
<summary>更多截圖</summary>

| Search Demo | 女優搜尋 Gallery |
|-------------|------------------|
| ![Search Demo](docs/screenshots/demo2.gif) | ![Search](docs/screenshots/search-detail.png) |

| Showcase Grid | Showcase 詳細 |
|---------------|---------------|
| ![Grid](docs/screenshots/showcase-grid.png) | ![Detail](docs/screenshots/showcase-detail.png) |

</details>

---

## 安裝

### 推薦方式：一行安裝

**macOS**:
```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash
```

**Windows** (PowerShell):
```powershell
irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex
```

安裝指令會自動：
- 偵測系統架構並下載最新版本
- 解除平台安全限制（macOS quarantine / Windows Mark of the Web）
- 建立桌面快捷方式（Windows）
- 保留設定與日誌檔案（升級時）

### 備用方式：手動下載 ZIP

從 [GitHub Releases](https://github.com/slive777/OpenAver/releases/latest) 下載：

| 平台 | 檔案 |
|------|------|
| **Windows x64** | `OpenAver-vX.X.X-Windows-x64.zip` |
| **macOS arm64** | `OpenAver-vX.X.X-macOS-arm64.zip` |

> ⚠️ 手動 ZIP 安裝需額外步驟解除安全限制，見下方「疑難排解」。
> ℹ️ macOS 版本僅支援 Apple Silicon (M1/M2/M3/M4)。

首次開啟會自動進入新手導覽，帶你完成資料夾與基本設定，不需要先讀文件。

---

## 核心功能

### 🔍 Spotlight Search (搜尋)
- **多來源聯合搜尋**: 同時搜尋 JavBus, Jav321, JavDB, DMM, D2Pass, HEYZO，一次查完所有來源。
- **大圖詳情頁**: 封面、劇照、演員、標籤集中顯示，不用反覆切頁找資訊。
- **智慧搜尋**: 番號、女優名、系列、片商都能搜，搜尋結果自動比對本地片庫並標示已收藏。
- **版本自動辨識**: 自動識別 UC/LEAK/4K 等版本差異，整理檔名時不用手動補。
- **女優畫廊模式 (Beta)**: 女優搜尋結果 > 10 片時自動切換為 Gallery 瀏覽，顯示女優個人資料 Hero Card。
- **劇照瀏覽**: 搜尋結果直接瀏覽完整劇照。
- **本地檔案批次搜尋**: 拖入影片檔案或資料夾，自動辨識番號並批次查詢影片資訊、封面與劇照。

### 📝 Scanner (掃描與列表生成)
- **Showcase 展示列表**: 掃描本地影片資料夾，自動生成精美的互動式展示頁面（流暢動效 + 毛玻璃特效 + Lightbox 劇照瀏覽）。
- **即時進度視窗**: 掃描到哪裡、補了哪些資料，畫面上直接看得到。
- **NFO 補全**: 自動檢測並補全缺失的 NFO 檔案。
- **字幕偵測**: 影片搬移時自動偵測並搬移同目錄字幕檔。
- **Jellyfin 圖片模式**: 自動生成 poster/thumb/fanart 供 Jellyfin 使用。
- **靜態 HTML 匯出**: 同時生成獨立的 HTML 索引檔，不需部署伺服器也能離線瀏覽。

### 🌐 AI 翻譯
- 日文標題一鍵翻譯為你的 UI 語系（繁中 / 简中 / 英文），日文模式跳過翻譯。
- 支援 **Ollama**（本地 GPU，免費無限制）、**Gemini Flash**（Google 雲端，有免費額度）和 **OpenAI API Compatible**（OpenRouter、任意相容端點）。

### ⚙️ Settings (設定)
- **Dark Mode**: 全站深色模式，自動同步至生成的展示列表。
- **路徑管理**: 靈活設定輸出路徑與檔案命名規則，支援 `{suffix}` 格式變數。
- **我的最愛資料夾**: 設定常用資料夾，一鍵載入並自動搜尋。
- **多語系 UI**: 繁中 / 简中 / 日文 / 英文，即時切換。

### 🤖 AI-Ready API

你的 AI 助手現在能直接操作你的片庫：

- 「幫我搜 SAME-123, PRED-456, IPZZ-789 的完整資訊」— 多來源聯合搜尋
- 「把 D:\av 的 NFO 資料補齊」— 原地補完，不搬移不改名
- 「我今年抓最多的系列作品是哪個？」— SQL 查詢收藏資料庫
- 「幫我把這篇文章提到的番號做成圖文並茂的網頁」— 封面自動嵌入 HTML

不需要 SDK，不需要讀文件。一行 curl，AI 自學所有端點：

```bash
curl http://localhost:<port>/api/capabilities
```

> Port 和完整 URL 可在 Settings 頁面的「AI API」區塊查看。

支援任何 MCP / function-calling 相容的 AI 工具：

| 使用方式 | 工具 | 說明 |
|----------|------|------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider 等 | 終端機直接 `curl`，所有 CLI agent 皆支援 |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae, Google Antigravity 等 | Agent 模式 / MCP 呼叫本地 API |
| **桌面 App** | Codex App, Claude Cowork, OpenClaw | 不需開發環境，開箱即用 |

> 💡 **推薦**：**OpenAI Codex App**（Win/Mac，免費方案可用）— 目前唯一能在對話中直接顯示封面圖片的 AI 工具，安裝簡單，開箱即用。

> ⚡ **小模型友善**：capabilities manifest 已針對輕量模型優化，Gemini Flash / GPT-5.4 mini / Claude Haiku 皆可正確操作所有端點。

---

## 開發者指南

### 技術架構

| 層級 | 技術 |
|------|------|
| **Backend** | FastAPI (Python 3.10+) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + Fluent Design 2 |
| **Animation** | GSAP 3.14+ + Motion Adapter (reduced-motion support) |
| **Desktop** | PyWebView (Windows/macOS) |
| **Database** | SQLite (WAL mode) |
| **Testing** | Pytest (1600+ tests) |

### 從原始碼執行

**前置需求**: Python 3.10+、Chrome/Edge、[WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

```bash
# Clone + 建立虛擬環境 + 安裝依賴
git clone https://github.com/slive777/OpenAver.git
cd OpenAver
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 開發模式 (Hot Reload)
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# 桌面模式 (Windows)
python windows/launcher.py
```

### 執行測試

```bash
source venv/bin/activate
pytest
```

### 目錄結構

```
OpenAver/
├── web/                # Web GUI (FastAPI)
│   ├── routers/        # API Endpoints (Search, Config, Scraper, Scanner, Capabilities)
│   ├── templates/      # HTML Templates (DaisyUI + Fluent Design 2)
│   └── static/         # CSS/JS Assets (Modular JS, Theme CSS)
├── core/               # 核心邏輯
│   ├── scrapers/       # 模組化爬蟲 (JavBus/JavDB/Jav321/FC2/AVSOX/DMM/D2Pass/HEYZO)
│   ├── database.py     # SQLite 資料層 (WAL mode)
│   ├── organizer.py    # 檔案整理 + fallback 空值防護
│   ├── path_utils.py   # 跨平台路徑處理 (file:// URI)
│   ├── i18n.py         # 多語系翻譯核心 (t() / fallback chain)
│   └── translate_service.py  # AI 翻譯 (Ollama/Gemini/OpenAI Compatible)
├── locales/            # 四語系 JSON (zh_TW/zh_CN/ja/en)
├── tests/              # 測試代碼 (Pytest)
└── windows/            # Windows 啟動器 (PyWebView)
```

### 打包應用程式

```bash
source venv/bin/activate
python build.py          # Windows
python build_macos.py    # macOS
```

---

## 疑難排解

> 💡 如果您使用上方推薦的 **一行安裝**，以下步驟通常不需要。疑難排解僅適用於手動 ZIP 安裝。

### 升級注意事項（ZIP 手動安裝）

覆蓋安裝可能殘留舊版 Python 套件，導致啟動失敗。**升級前請先刪除 `python` 資料夾**：

- **Windows**: 刪除 `%USERPROFILE%\OpenAver\python\`
- **macOS**: 刪除 `~/OpenAver/python/`

### Windows 程式無法啟動 / 閃退

**原因**: Windows Mark of the Web 封鎖了從網路下載的執行檔。

**解法**:
1. 對下載的 ZIP 點擊 **右鍵** → **內容**
2. 勾選 **「解除封鎖 (Unblock)」** → 確定
3. 重新解壓縮並執行 `OpenAver.bat`

*或者使用 7-Zip 解壓縮，通常可避開此問題。*

**啟動腳本**:
- `OpenAver.bat` — 正常啟動
- `OpenAver_Debug.bat` — 調試版本（顯示詳細日誌），日誌檔案：`%USERPROFILE%\OpenAver\logs\debug.log`

### macOS 無法開啟 / 安全性警告

**原因**: macOS Gatekeeper 阻擋未簽名的應用程式。

在終端機依序執行：
```bash
cd ~/Downloads/OpenAver
xattr -dr com.apple.quarantine .
./OpenAver.command
```

設定完成後，之後可直接雙擊 `OpenAver.command` 執行。

**啟動腳本**:
- `OpenAver.command` — 正常啟動
- `OpenAver_Debug.command` — 調試版本，日誌檔案：`~/OpenAver/logs/debug.log`

### 介面顯示異常 / 空白（所有安裝方式）

**原因**: 缺少 WebView2 Runtime（常見於 Windows 10 或虛擬機）。

**解法**: 下載並安裝 [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)。

---

## 社群與回報問題

加入 [Telegram 群組](https://t.me/+J-U2l96gv0FjZTBl) 與其他使用者交流討論！

| 管道 | 適用情境 |
|------|----------|
| [GitHub Issues](https://github.com/slive777/OpenAver/issues) | Bug 回報、功能建議、開發討論 |
| [Telegram 群組](https://t.me/+J-U2l96gv0FjZTBl) | 隱私敏感問題、截圖/影片直傳 |

**回報時請附上**: 問題描述、重現步驟、OS 版本、日誌檔案（執行 Debug 版啟動腳本取得）。

---

## 致謝

OpenAver 使用並感謝以下開源專案：

- **[FastAPI](https://fastapi.tiangolo.com/)** - 現代化的 Python Web 框架
- **[PyWebView](https://pywebview.flowrl.com/)** - 輕量級的跨平台桌面應用框架
- **[GSAP](https://gsap.com/)** - 高效能 JavaScript 動畫引擎
- **[DaisyUI](https://daisyui.com/)** - Tailwind CSS 元件庫
- **[Tailwind CSS](https://tailwindcss.com/)** - Utility-first CSS 框架
- **[Alpine.js](https://alpinejs.dev/)** - 輕量級 JavaScript 框架

## License

MIT License

---

<details>
<summary>⚠️ 免責聲明</summary>

本專案僅供個人學習研究使用，請使用者遵守：
- 尊重網站服務條款
- 合理控制請求頻率
- 不用於商業目的

使用本專案造成的任何後果由使用者自行承擔。

</details>
