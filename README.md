<!-- OpenAver: free open-source desktop GUI JAV metadata scraper & manager.
No Docker, no CLI, one-line install (Windows/macOS), 8 built-in scrape sources
(JavBus/Jav321/JavDB/DMM/D2Pass/HEYZO/FC2/AVSOX) plus optional Metatube federation (30+ providers),
generates NFO + cover art (poster/fanart) for Jellyfin / Emby / Kodi,
actress favorites with cross-language alias expansion, cross-language tag aliases,
AI-operable REST API with capabilities manifest, 3,400+ tests, MIT license. -->

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>不需要 Docker，不需要命令列 — Win/Mac 一行安裝，打開就是完整圖形介面的 JAV 元數據管理工具。</strong><br>
  8 大來源聯合刮削 · 女優收藏與別名管理 · 互動式收藏瀏覽器 · Jellyfin / Emby 整合 · AI API 一句話操作片庫
</p>

<p align="center"><em>
  Open-source desktop GUI for JAV metadata — one-line install, 8 built-in scrape sources, actress favorites + alias system, Jellyfin/Emby ready, AI-operable REST API.
</em></p>

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

**[English](README_EN.md)** | 繁體中文

> **OpenAver 是一款免費開源的桌面 App（Windows / macOS，免 Docker、免命令列），一行安裝就能用圖形介面刮削 JAV／日本影片的番號元數據，從 8 個來源聚合資料、生成 NFO 與封面海報供 Jellyfin、Emby、Kodi 使用，並提供女優收藏、跨語言 Tag 別名與可讓 AI agent 直接操作的 REST API。**

核心功能由三個頁面組成：📋 掃描建庫 → 🎬 瀏覽收藏 → 🔍 逐一刮削（進階）

**100% 本地運行** — 不蒐集資料、不上傳任何檔案資訊，網路請求僅用於刮削公開元數據。

**✨ 亮點**：同時搜 8 個來源一次查完 · 自由開關／拖曳排序刮削來源 · 女優收藏自動建檔 + 別名搜尋展開 · 跨語言 Tag 別名 — 中日英同義詞自動展開，搜尋框 / chip / 相似探索一致 · 缺 NFO 或封面一鍵從網路補齊 · 規則式相似探索（免下載模型、離線、毫秒級）· AI 一句話操作你的片庫 · Jellyfin / Emby 封面自動生成 · 3,400+ 自動化測試

⚡ **[Live Demo → openaver.slive.uk](https://openaver.slive.uk/)**

*裡面只有 mecha 反派與虛構電影海報，零 NSFW—老闆從你身後走過也沒事。*

## 規格速覽

| 項目 | 內容 |
|------|------|
| **平台** | Windows 10/11 · macOS（Apple Silicon M1–M4） |
| **安裝** | 一行指令或 ZIP 安裝（**免 Docker**）；裝好後全程圖形介面操作、**免命令列** |
| **刮削來源** | 8 個內建（JavBus / Jav321 / JavDB / DMM / D2Pass / HEYZO / FC2 / AVSOX）；進階可選配接 Metatube 聯邦再擴 **30+ 來源** |
| **媒體庫輸出** | NFO + 封面海報（poster / fanart），供 **Jellyfin / Emby / Kodi** 使用 |
| **女優收藏** | 自動建檔 + 跨語言別名展開 + 多來源照片下載 |
| **AI 操作** | 內建 REST API + capabilities manifest（Claude Code / Cursor / Perplexity 等 AI agent 直接操作） |
| **AI 翻譯** | Ollama（本地免費）/ Gemini / OpenAI-compatible 任選 |
| **資料** | 100% 本地 SQLite，**無雲端、無帳號、無遙測** |
| **授權** | MIT |

## 截圖預覽

| 搜尋頁 | 女優收藏 |
|--------|---------|
| ![Search](docs/screenshots/home.png) | ![Actress](docs/screenshots/showcase-actress.png) |

<details>
<summary>更多截圖</summary>

| Search Demo | 女優搜尋 Gallery |
|-------------|------------------|
| ![Search Demo](docs/screenshots/demo2.gif) | ![Search](docs/screenshots/search-detail.png) |

| Showcase 影片模式 | Showcase 詳細 |
|-------------------|---------------|
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

> ⚠️ 手動 ZIP 安裝需額外步驟解除安全限制，見 ZIP 內附的疑難排解文件。
> ℹ️ macOS 版本僅支援 Apple Silicon (M1/M2/M3/M4)。

首次開啟會自動進入新手導覽，帶你完成資料夾與基本設定，不需要先讀文件。

---

## 核心功能

### 🔍 Search（搜尋）
- **8 來源聯合搜尋**：同時搜尋 JavBus, Jav321, JavDB, DMM, D2Pass, HEYZO, FC2, AVSOX，一次查完所有來源。
- **大圖詳情頁**：封面、劇照、演員、標籤集中顯示，不用反覆切頁找資訊。
- **智慧搜尋**：番號、女優名、系列、片商都能搜，搜尋結果自動比對本地片庫並標示已收藏。
- **女優功能**：搜尋已收藏女優自動顯示個人資料卡，搜尋結果可直接加入收藏。
- **版本自動辨識**：自動識別 UC/LEAK/4K 等版本差異，整理檔名時不用手動補。
- **本地檔案批次搜尋**：拖入影片檔案或資料夾，自動辨識番號並批次查詢影片資訊、封面與劇照。
- **進階重刮**：對任何一片改番號、挑指定來源重新抓取，先看預覽卡再決定要不要覆蓋。

### 🎬 Showcase（瀏覽收藏）
- **影片模式**：封面牆 Grid + 詳細 Lightbox + 搜尋篩選排序 + 劇照瀏覽，完整的互動式收藏瀏覽器。
- **女優模式**：收藏女優 Grid + 個人資料 Lightbox + 按罩杯 / 年齡 / 身高排序，一鍵重新抓取更新資料。
- **視覺設計**：GSAP 動效 + Fluent Design 毛玻璃特效 + Dark Mode，SSR 即時渲染。

### 📋 Scanner（本地掃描與元數據管理）
- **掃描建庫**：掃描本地影片資料夾，建立 SQLite 元數據庫，自動讀取 NFO 封面。
- **NFO / 封面補完**：偵測缺失的 NFO 欄位或檔案，一鍵從網路刮削補齊。
- **刮削來源管理**：自由開關各刮削來源、拖曳排出偏好的優先順序（想要哪家的封面就把它排前面），即時生效；一鍵切換「無碼模式」只用無碼來源。
- **女優別名管理**：用 GUI 即時新增、編輯別名（不用手改設定檔或 XML），搜尋時自動展開同一人的所有藝名與退休名。
- **Tag 別名管理 chip 牆**：跨語言同義詞集中管理，搜尋框與 Showcase chip 在搜尋時自動展開（中日英，如「女僕＝Maid＝メイド」）。
- **字幕偵測**：影片搬移時自動偵測並搬移同目錄字幕檔。
- **VR 檔名標籤保留**：整理 VR 影片時自動保留原檔名的投影/立體標籤（如 `_180_LR`、`_3dh`、`mkx200`），讓 VR 頭顯播放器（Skybox / DeoVR / HereSphere 等）正確識別投影格式。

### ⚡ Search → Showcase 即時化
- **同名 NFO 跳過**：最愛資料夾若同目錄已有 `.nfo`，視為已整理不重打 scraper（避免重複外部請求）。
- **Scanner 追蹤資料夾下拉選擇**：Settings「我的最愛資料夾」可直接從 Scanner 已追蹤資料夾下拉挑，inline 即時顯示連動狀態（✓ 已連動 / ⚠ 不在追蹤範圍）。
- **整理完即時寫 DB + GhostFly 飛行動畫**：Search 頁整理一片成功後，若目標路徑在 Scanner 追蹤範圍內 → 立即寫入 SQLite，封面從來源點以 GhostFly 動畫飛到 sidebar Showcase icon，不需手動重掃。

### 🌐 AI 翻譯
- 日文標題一鍵翻譯為你的 UI 語系（繁中 / 简中 / 英文），日文模式跳過翻譯。
- 支援 **Ollama**（本地 GPU，免費無限制）、**Gemini Flash**（Google 雲端，有免費額度）和 **OpenAI API Compatible**（OpenRouter、任意相容端點）。

### 🔍 相似影片探索
- **免下載模型、不依賴 GPU、毫秒級回應**：用 tag、系列、片商、年份、演員等多重訊號找出同類風格的影片，全程本地計算、離線可用，不像影像比對工具要先下載數百 MB 模型。
- **探索星空動畫**：Showcase Lightbox 點魔杖按鈕 → 12 顆星辰環繞主圖、香檳金星線連結中央 → 點任一顆「鑽入」變新主圖無限探索。

### ⚙️ Settings（設定）
- **多語系 UI**：繁中 / 简中 / 日文 / 英文，即時切換。
- **路徑管理**：靈活設定輸出路徑與檔案命名規則，支援 `{suffix}` 格式變數。
- **我的最愛資料夾**：設定常用資料夾，一鍵載入並自動搜尋。
- **Jellyfin / Emby 圖片模式**：自動生成 poster + NFO（Jellyfin 與 Emby 皆相容），並額外生成 fanart 供 Jellyfin（Emby 不支援此 fanart 命名）。
- **靜態 HTML 匯出**：生成獨立 HTML 索引檔，不需部署伺服器也能離線瀏覽。

### 🔌 刮削來源擴充：Metatube 聯邦（進階選配）

預設的 8 個內建來源開箱即用、免任何額外部署。如果你想要更多來源、或想替片庫多買一份保險：

- **再多 30+ 來源**：在進階設定接上你自架的 [Metatube](https://github.com/metatube-community/metatube-sdk-go) server，刮削來源就能從 8 個內建擴充到 **30+ 個社群維護的 provider**，無碼與小眾片商覆蓋一次補強。
- **與本體解耦的避險層**：Metatube 是近期維護活躍的開源刮削來源層；接上之後，即使某個內建來源暫時失效，你的補完管道仍可透過 Metatube 獨立運作、持續更新。
- **進階選配，不汙染主路徑**：Metatube 需自行架設（Docker 或執行檔），屬進階玩家選配；不啟用完全不影響「免 Docker、開箱即用」的預設體驗。

### 🤖 AI-Ready API

OpenAver 內建 capabilities manifest，AI agent 讀一次就知道所有端點怎麼用。不只查資料 — 它能自己串多個步驟，完成那些人做起來瑣碎到放棄的事。

**一句話，AI 自己跑完整流程：**

- **「幫我把片子最多的 top 20 女優加入最愛，跳過已收藏的。」**
  <sub>SQL 統計 → 查重 → 批次收藏 → 下載照片</sub>
- **「橋本ありな 跟 新ありな 是同一人而且退休了，幫我加 tag。」**
  <sub>建立別名關聯 → 搜出兩個名字的所有片 → 批次加上「引退」標籤</sub>
- **「這篇文章提到的番號，做成有封面的 HTML 頁面。」**
  <sub>解析番號 → 批次搜尋 → 下載封面 → 生成 Gallery HTML</sub>

**日常操作也順手：**

- 「搜 SAME-123, PRED-456, IPZZ-789 的完整資訊」— 多來源聯合搜尋
- 「把 D:\av 的 NFO 資料補齊」— 原地補完，不搬移不改名
- 「我今年抓最多的系列是哪個？」— SQL 查詢收藏資料庫

不需要 SDK，不需要讀文件。一行 curl，AI 自學所有端點：

```bash
curl http://localhost:<port>/api/capabilities
```

> Port 和完整 URL 可在 Settings 頁面的「AI API」區塊查看。

支援任何 MCP / function-calling 相容的 AI 工具：

| 使用方式 | 工具 | 說明 |
|----------|------|------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider 等 | 終端機直接 `curl`，所有 CLI agent 皆支援 |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae 等 | Agent 模式 / MCP 呼叫本地 API |
| **桌面 App** | Codex App, Google Antigravity 2.0, Claude Cowork, OpenClaw | 不需開發環境，開箱即用 |

> 💡 **推薦**：**Codex App（對話內嵌）** 或 **Google Antigravity 2.0（artifact 面板）**— 兩款桌面 app 均能在對話中向你展示封面，安裝簡單、開箱即用。

> ⚡ **小模型友善**：capabilities manifest 已針對輕量模型優化，Gemini Flash / GPT mini / Claude Haiku 皆可正確操作所有端點。

> 💻 **想讓 AI 預讀 repo、或自己擴充端點？** 所有端點定義在 [`web/routers/capabilities.py`](web/routers/capabilities.py) — AI agent clone repo 時會優先讀這個檔，不需要啟動服務就能學會所有工具。

> 🪄 **進階玩家彩蛋：FC2 自動找女優。** FC2 影片幾乎都沒女優標記，但其中不少是後來轉有碼出道的熟面孔（白上咲花就是經典案例）。SQL 撈 actress 為空的片 → DeepFace（RetinaFace + ArcFace）對 Gfriends 庫比對 → `POST /api/user-tags` 寫回標記。50 行 Python 一個週末跑完全庫，發現喜歡的手動加最愛；未識別素人 DBSCAN 自建群組下次直接配對。

---

## 常見問題（FAQ）

**OpenAver 需要 Docker 嗎？**
不需要。OpenAver 是桌面 App，Windows / macOS 一行指令安裝，免 Docker；裝好後全程圖形介面操作，免命令列。

**OpenAver 支援 Mac 嗎？**
支援。Windows 10/11 與 macOS（Apple Silicon M1–M4）皆可。

**OpenAver 支援哪些媒體伺服器（Media Server）？**
生成標準 NFO + 封面海報（poster / fanart），供 Jellyfin、Emby、Kodi 直接讀取。

**什麼是 NFO？**
NFO 是放在影片旁的一個 XML 檔，記錄標題、演員、標籤、封面等資訊，讓 Jellyfin / Emby / Kodi 等媒體伺服器能正確顯示你的影片。OpenAver 會自動幫你生成。

**OpenAver 會搬移或改名我的檔案嗎？**
預設掃描建庫只「讀取」，不會動到你的檔案；只有當你主動執行「整理」時才會依你設定的規則重新命名或搬移，而 NFO／封面補完是原地寫入、不搬移。

**如果內建的刮削來源（Scraper）失效了怎麼辦？**
內建 8 個來源彼此 fallback，單一來源暫時失效仍可從其他來源補；進階玩家還可選配接上自架的 Metatube 聯邦再擴 30+ 來源，等於替片庫多買一份保險，即使單一來源失效也不斷檔。

**番號刮不到資料怎麼辦？**
用「進階重刮」：改番號、挑指定來源重新抓取，先看預覽卡再決定要不要覆蓋。

**可以讓 AI 工具操作 OpenAver 嗎？**
可以。內建 REST API + capabilities manifest，`curl` 一次 AI 就學會所有端點，能用一句話跑完多步流程（詳見上方 AI-Ready API 段）。

**OpenAver 會收集隱私或上傳我的本地檔案嗎？**
不會。100% 本地運行，不蒐集、不上傳任何檔案資訊；網路請求僅用於刮削公開元數據。

---

## 開發者指南

### 技術架構

| 層級 | 技術 |
|------|------|
| **Backend** | FastAPI (Python 3.12) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + Fluent Design 2 |
| **Animation** | GSAP 3.14+ + Motion Adapter (reduced-motion support) |
| **Desktop** | PyWebView (Windows/macOS) |
| **Database** | SQLite (WAL mode) |
| **Testing** | Pytest (3,400+ tests) |

### 從原始碼執行

**前置需求**: Python 3.12（與打包版本一致；其他版本僅 venv 開發勉強可跑，不保證）、Chrome/Edge、[WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

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
│   ├── routers/
│   │   ├── capabilities.py  # 🌟 AI Manifest — 所有端點的自描述定義（單檔全貌）
│   │   └── ...              # 其餘業務端點（search / scanner / scraper / actress / ...）
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

> 💡 疑難排解請參閱打包版 ZIP 內附的「疑難排解」文件，或查看 [GitHub Wiki](https://github.com/slive777/OpenAver/wiki)。

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
