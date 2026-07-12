<!-- OpenAver: free open-source desktop GUI JAV metadata scraper & manager.
No Docker, no CLI, one-line install (Windows/macOS). A cover-wall browser built for how
this genre is actually browsed — navigate by cover + tag, actress as a first-class entity
(profile cards, cup/age/height sort, cross-language alias). 8 built-in scrape sources
(JavBus/Jav321/JavDB/DMM/D2Pass/HEYZO/FC2/AVSOX) plus optional Metatube federation (30+ providers).
Optionally exports NFO + cover art (poster/fanart) to Jellyfin / Emby / Kodi.
AI-operable REST API with capabilities manifest, 4,000+ tests, MIT license. -->

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>不需要 Docker、不需要命令列 — Win/Mac 一行安裝，打開就是完整圖形介面的 JAV 收藏管理工具。</strong><br>
  封面牆瀏覽收藏 · 女優收藏與跨語言別名 · 8 大來源聯合刮削 · AI API 一句話操作片庫
</p>

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-0078D6.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)
![Downloads](https://img.shields.io/github/downloads/slive777/OpenAver/total?color=success)
![Stars](https://img.shields.io/github/stars/slive777/OpenAver)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://img.shields.io/github/actions/workflow/status/slive777/OpenAver/test.yml?label=tests%204%2C000%2B)

**[English](README_EN.md)** | 繁體中文

> **這不只是「把資料餵給 Jellyfin 的刮削器」。** OpenAver 負責找片、整理、逛收藏、探索相似——它的 Showcase 以**封面 tag** 為導航主軸，還有**專屬的女優瀏覽模式**（個人資料卡、罩杯／年齡／身高排序、跨語言別名自動收攏同一人的所有藝名與退休名），是為「一整櫃番號收藏」的實際逛法打造的瀏覽器。刮削完想丟客廳媒體中心看，再一鍵輸出 NFO／封面海報給 Jellyfin／Emby／Kodi——也可以不丟，Showcase 本身就是完整的瀏覽體驗。

核心由三個頁面組成：📋 掃描建庫 → 🎬 瀏覽收藏 → 🔍 逐一刮削（進階）。**預設只「查資料」（搜尋／瀏覽都是純讀取）；只有你按「整理」才會「動檔案」**——依你設定的規則重新命名或搬移影片檔，其餘時候完全不碰你的檔案。

**100% 本地運行** — 不蒐集資料、不上傳任何檔案資訊，網路請求僅用於刮削公開元數據。

⚡ **[Live Demo → openaver.slive.uk](https://openaver.slive.uk/)**

*裡面只有 mecha 反派與虛構電影海報，零 NSFW—老闆從你身後走過也沒事。*

## 規格速覽

| 項目 | 內容 |
|------|------|
| **平台** | Windows 10/11 · macOS（Apple Silicon M1–M4） |
| **安裝** | 一行指令或 ZIP 安裝（**免 Docker**）；裝好後全程圖形介面操作、**免命令列** |
| **收藏瀏覽** | Showcase 封面牆 + Lightbox：影片模式（封面/tag 導航 + 相似探索）、女優模式（資料卡 + 罩杯/年齡/身高排序 + 跨語言別名） |
| **多裝置存取** | 一鍵切換伺服器模式，同 Wi-Fi 的手機 / 平板用瀏覽器即可瀏覽收藏（**即時生效、免重啟、免設定**；預設單機完全不對外） |
| **刮削來源** | 8 個內建（JavBus / Jav321 / JavDB / DMM / D2Pass / HEYZO / FC2 / AVSOX）；進階可選配接 Metatube 聯邦再擴 **30+ 來源** |
| **媒體庫輸出（選配）** | 一鍵生成 NFO + 封面海報（poster / fanart）給 **Jellyfin / Emby / Kodi**；唯讀來源可不下載原檔、本地生成 `.strm` 媒體庫直接串流 |
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

> 💡 不想開 PowerShell 的 Windows 用戶：也可以到 [Releases](https://github.com/slive777/OpenAver/releases/latest) 下載 `OpenAver-Windows-Setup.bat`，雙擊即可跑完同一套安裝。

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

### 🎬 Showcase（互動式收藏瀏覽器）

**媒體伺服器的導航軸是片名和資料夾；OpenAver 的導航軸是封面、tag、女優——這才是這個 genre 的實際逛法。**

- **封面牆 + Lightbox**：以封面為主軸逛收藏，點封面進詳情燈箱看劇照、tag、女優資訊。
- **以 tag 篩選與排序**：封面牆用 tag chip 當導航（中日英同義詞自動展開），可按日期 / 番號 / 女優 / 片商 / 檔案大小等多軸排序。
- **女優瀏覽模式**：女優單獨成一個逛法——收藏女優封面牆 + 個人資料燈箱（身高、罩杯、三圍、年齡、別名歷史），按罩杯 / 年齡 / 身高 / 片數排序；跨語言別名把同一人的所有藝名與退休名收攏成一張卡。
- **相似探索**：燈箱點魔杖 → 同風格的番號環繞主圖，點任一顆「鑽入」繼續探索。以 **tag IDF** 加權再混系列、片商、女優等共同點本地比對，找出同類片（規則式，非行為推薦演算法），離線即時、免 GPU、免下載模型。
- **整理完即時出現**：在 Search 整理一片成功、且目標在掃描範圍內 → 立刻寫入 SQLite、封面飛進 Showcase，不必手動重掃。
- **手機 / 平板也能逛**：設定裡一鍵切到「伺服器」，同 Wi-Fi 的手機、平板用瀏覽器打開網址，就能逛同一個收藏——即時生效、不用重啟、不用裝任何東西；用完切回「單機」立刻關閉對外。整個介面為觸控與直式螢幕重做，封面可左右滑換片。

### 🔍 Search（搜尋與刮削）

- **8 來源聯合搜尋**：同時搜尋 JavBus, Jav321, JavDB, DMM, D2Pass, HEYZO, FC2, AVSOX，一次查完；結果自動比對本地片庫並標示已收藏。
- **大圖詳情頁**：封面、劇照、演員、標籤集中顯示，不用反覆切頁找資訊。
- **智慧搜尋**：番號、女優名、系列、片商都能搜。
- **版本自動辨識**：自動識別 UC / LEAK / 4K 等版本差異，整理檔名時不用手動補。
- **本地檔案批次搜尋**：拖入影片檔案或資料夾，自動辨識番號並批次查詢資訊、封面與劇照。
- **進階重刮**：番號刮不到、或想換來源時，改番號／挑指定來源重新抓取，先看預覽卡再決定要不要覆蓋。

### 📋 Scanner（建庫與元數據管理）

- **掃描建庫**：掃描本地影片資料夾，建立 SQLite 元數據庫，自動讀取既有 NFO 與封面。
- **NFO / 封面補完**：偵測缺失的 NFO 欄位或檔案，一鍵從網路刮削補齊——**新增 NFO／封面檔在影片旁**（原地寫入），不動到影片本身。（NFO = 放在影片旁的 XML 元數據檔，供 Jellyfin / Emby / Kodi 讀取標題、演員、標籤。）
- **女優 / Tag 別名管理**：用 GUI 即時新增、編輯別名（不用手改設定檔或 XML），搜尋時中日英同義詞自動展開（如「女僕＝Maid＝メイド」、同一人的所有藝名與退休名）。
- **刮削來源管理**：自由開關各來源、拖曳排出偏好順序（想要哪家的封面就排前面），即時生效；一鍵切換「無碼模式」只用無碼來源。
- **整理時保留字幕與 VR 標籤**：搬移影片時自動偵測並帶走同目錄字幕檔；VR 影片保留原檔名的投影/立體標籤（如 `_180_LR`、`mkx200`），讓 Skybox / DeoVR / HereSphere 等頭顯播放器正確識別。

### 📀 唯讀來源 → 生成媒體庫 + `.strm` 串流

想把 NAS、雲端掛載、或任何「不想被工具碰」的原始收藏掛進客廳媒體中心，又不想複製一份幾 TB 的原檔？把來源標成**唯讀**即可：

- **來源不動一個位元組**：標了「唯讀」的掃描來源，OpenAver 不搬、不改、不寫那個資料夾——只讀元數據。刮好的 NFO + 封面 + extrafanart 全部改寫到你指定的**本地**輸出夾，一片一資料夾。
- **`.strm` 直接餵媒體中心**：不必把原檔複製一份，生成 `.strm` 指向來源原始位置，**Emby / Jellyfin / Kodi** 掃到就能直接串流播放。等於用 OpenAver 當「只出元數據、不出檔案」的刮削前端，接手停更的 MDCX 那一棒。
- **跨機器路徑映射**：OpenAver 這台看到的路徑，和媒體伺服器那台看到的不一樣時（不同掛載點 / WSL / UNC），設一組替換規則自動改寫進 `.strm`；日後改規則，既有 `.strm` 一併同步改寫。

### 🌐 AI 翻譯

- 日文標題一鍵翻譯為你的 UI 語系（繁中 / 简中 / 英文），日文模式跳過翻譯。
- 支援 **Ollama**（本地 GPU，免費無限制）、**Gemini Flash**（有免費額度）和 **OpenAI API Compatible**（OpenRouter、任意相容端點）。

### ⚙️ Settings（設定）

- **多語系 UI**：繁中 / 简中 / 日文 / 英文，即時切換。
- **路徑與命名規則**：靈活設定輸出路徑與檔名規則，支援 `{suffix}` 格式變數。
- **我的最愛資料夾**：設定常用的**影片資料夾路徑**（不是女優最愛），一鍵載入並自動搜尋。
- **外部媒體管理器模式（選配）**：選 Jellyfin / Emby / Kodi，刮削後自動生成對應命名的 poster + fanart 與相容 NFO，想掛客廳媒體庫時掛進去即正確顯示（poster 與 NFO 三者通用；`{stem}-fanart` 僅 Jellyfin／Kodi 讀取，Emby 不認此 fanart 命名）。
- **靜態 HTML 匯出**：生成獨立 HTML 索引檔，不需部署伺服器也能離線瀏覽。

### 🔌 刮削來源擴充：Metatube 聯邦（進階選配）

預設的 8 個內建來源開箱即用、免任何額外部署。如果你想要更多來源、或想替片庫多買一份保險：

- **再多 30+ 來源**：在進階設定接上你自架的 [Metatube](https://github.com/metatube-community/metatube-sdk-go) server，刮削來源就能從 8 個內建擴充到 **30+ 個社群維護的 provider**，無碼與小眾片商覆蓋一次補強。
- **與本體解耦的避險層**：Metatube 是持續活躍維護的開源刮削來源層；接上之後，即使某個內建來源暫時失效，你的補完管道仍可透過 Metatube 獨立運作、持續更新。
- **進階選配，不汙染主路徑**：Metatube 需自行架設（Docker 或執行檔），屬進階玩家選配；不啟用完全不影響「免 Docker、開箱即用」的預設體驗。

### 🤖 AI-Ready API

內建 capabilities manifest，AI agent 讀一次就知道所有端點怎麼用——不只查資料，還能自己串多個步驟，完成那些人做起來瑣碎到放棄的事。

**一句話，AI 自己跑完整流程：**

- **「幫我把片子最多的 top 20 女優加入最愛，跳過已收藏的。」**
  <sub>SQL 統計 → 查重 → 批次收藏 → 下載照片</sub>
- **「橋本ありな 跟 新ありな 是同一人而且退休了，幫我加 tag。」**
  <sub>建立別名關聯 → 搜出兩個名字的所有片 → 批次加上「引退」標籤</sub>
- **「這篇文章提到的番號，做成有封面的 HTML 頁面。」**
  <sub>解析番號 → 批次搜尋 → 下載封面 → 生成 Gallery HTML</sub>

不需要 SDK，不需要讀文件，一行 curl 讓 AI 自學所有端點：

```bash
curl http://localhost:<port>/api/capabilities
```

> Port 和完整 URL 可在 Settings 頁面的「AI API」區塊查看。

<details>
<summary>支援的 AI 工具 · 進階用法 · 玩家彩蛋</summary>

支援任何 function-calling 相容的 AI 工具：

| 使用方式 | 工具 | 說明 |
|----------|------|------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider 等 | 終端機直接 `curl`，所有 CLI agent 皆支援 |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae 等 | Agent 模式呼叫本地 REST API |
| **桌面 App** | Codex App, Google Antigravity 2.0, Claude Cowork, OpenClaw | 不需開發環境，開箱即用 |

> 💡 對話內想看到封面：**Codex App（對話內嵌）** 或 **Google Antigravity 2.0（artifact 面板）** 兩款桌面 app 都能在對話中向你展示封面，安裝簡單、開箱即用。

> ⚡ **小模型友善**：capabilities manifest 已針對輕量模型優化，Gemini Flash / GPT mini / Claude Haiku 皆可正確操作所有端點。

> 💻 **想讓 AI 預讀 repo、或自己擴充端點？** 所有端點定義在 [`web/routers/capabilities.py`](web/routers/capabilities.py) — AI agent clone repo 時會優先讀這個檔，不需要啟動服務就能學會所有工具。

> 🪄 **進階玩家彩蛋：FC2 自動找女優。** FC2 影片幾乎都沒女優標記，但其中不少是後來轉有碼出道的熟面孔（白上咲花就是經典案例）。SQL 撈 actress 為空的片 → DeepFace（RetinaFace + ArcFace）對 Gfriends 庫比對 → `POST /api/user-tags` 寫回標記。50 行 Python 一個週末跑完全庫，發現喜歡的手動加最愛；未識別素人 DBSCAN 自建群組下次直接配對。

</details>

---

## 常見問題（FAQ）

**OpenAver 和 Jellyfin / Emby / Kodi 有什麼不同？**
分工不同。Jellyfin / Emby / Kodi 是把影片擺上客廳大螢幕播放的媒體伺服器，以「一部電影」為單位、用片名和資料夾組織。OpenAver 是你自己的番號收藏室——用封面牆逛、用 tag 橫向延伸、用女優縱向深挖，找片、整理、探索相似都在這裡完成。兩者各就其位：刮削完想丟客廳媒體中心看時，一鍵輸出 NFO + 封面就能掛進 Jellyfin / Emby / Kodi。

**OpenAver 需要 Docker 嗎？**
不需要。OpenAver 是桌面 App，Windows / macOS 一行指令安裝，免 Docker；裝好後全程圖形介面操作，免命令列。

**OpenAver 支援 Mac 嗎？**
支援。Windows 10/11 與 macOS（Apple Silicon M1–M4）皆可。

**OpenAver 會搬移、改名或刪除我的檔案嗎？**
預設只「查資料」（搜尋、瀏覽都是純讀取），掃描建庫也只讀不動。只有你主動按「整理」時才會動檔案：依你設定的規則**搬移或重新命名影片檔，但絕不刪除**；遇到目標位置已有同名檔會先提醒你，再由你決定是否覆蓋。NFO 與封面則是**新增**在影片旁的檔案（原地寫入），不會動到影片本身。

**Windows 關閉視窗後可以在背景運行嗎？**
可以。點擊右上角 X 時可選擇退出或最小化到系統匣，並可勾「不再顯示」記住選擇；單擊或雙擊右下角 OpenAver 圖示可重新開啟。也可到「設定 → 系統設定 → 關閉視窗時」事後調整。

**如果內建的刮削來源（Scraper）失效了怎麼辦？**
內建 8 個來源彼此 fallback，單一來源暫時失效仍可從其他來源補；進階玩家還可選配接上自架的 Metatube 聯邦再擴 30+ 來源，等於替片庫多買一份保險。

**為什麼 JavLibrary 來源不能用 AI 或批次自動抓取？**
因為 OpenAver 選擇尊重 JavLibrary 全站的 Cloudflare 人機驗證。桌面版用戶本來就是真人——首次或驗證過期時會彈出一個真的 JavLibrary 瀏覽器視窗，你手動點一次驗證，系統再自動重試並回填結果。所以 JavLibrary（BETA）只支援桌面版的手動精確番號查詢，不參與批量／自動搜尋、也不開放給 AI agent。換來的好處是：那些連 Metatube 30+ 來源都沒收錄的冷門長尾番號與社群標籤，OpenAver 也能在合規前提下抓到。

**可以讓 AI 工具操作 OpenAver 嗎？**
可以。內建 REST API + capabilities manifest，`curl` 一次 AI 就學會所有端點，能用一句話跑完多步流程（詳見上方 AI-Ready API 段）。

**OpenAver 會收集隱私或上傳我的本地檔案嗎？**
不會。100% 本地運行，不蒐集、不上傳任何檔案資訊；網路請求僅用於刮削公開元數據。

---

## 開發者指南

<details>
<summary>技術架構 · 從原始碼執行 · 目錄結構 · 打包</summary>

### 技術架構

| 層級 | 技術 |
|------|------|
| **Backend** | FastAPI (Python 3.12) |
| **Frontend** | Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + Fluent Design 2 |
| **Animation** | GSAP 3.14+ + Motion Adapter (reduced-motion support) |
| **Desktop** | PyWebView (Windows/macOS) |
| **Database** | SQLite (WAL mode) |
| **Testing** | Pytest (4,000+ tests) |

### 從原始碼執行

**前置需求**: Python 3.12（與打包版本一致）、Chrome/Edge、[WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

```bash
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

</details>

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
