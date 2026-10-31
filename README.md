<!-- OpenAver: free open-source desktop GUI JAV metadata scraper & manager. No Docker, no CLI,
one-line install (Windows/macOS). Reads NFO + covers already organized by JavSP/EverAver/MDCX/
Jellyfin/Emby without re-scraping. Cover-wall browser with actress as a first-class entity
(cup/age/height sort, cross-language alias) plus a library-insights dashboard. 8 built-in scrape
sources (JavBus/Jav321/JavDB/DMM/D2Pass/HEYZO/FC2/AVSOX) + optional Metatube federation (30+)
+ custom YAML sources an AI agent can write for any site with per-title pages. The desktop app can
also connect to a library hosted on a NAS or another PC. Optionally exports NFO + covers to
Jellyfin/Emby/Kodi. AI-operable REST API, 3,300+ tests, MIT. -->

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>你的番號收藏，用封面逛、用女優找。</strong><br>
  Windows/Mac 裝好就能用，免 Docker、免指令 · 以前整理好的片直接拿來逛，不必重新抓資料
</p>

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-0078D6.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)
![Downloads](https://img.shields.io/github/downloads/slive777/OpenAver/total?color=success)
![Stars](https://img.shields.io/github/stars/slive777/OpenAver)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://img.shields.io/github/actions/workflow/status/slive777/OpenAver/test.yml?label=tests%203%2C300%2B)

**[English](README_EN.md)** | 繁體中文

把放片的資料夾指給 OpenAver，它會做成一面封面牆：點封面看劇照和標籤，點女優看她的所有片，點標籤找同類；資料不全按一下就從網路補上。

**名字裡的 Open，意思是不綁死你：**

- **進得來**：JavSP、MDCX、EverAver 整理過的收藏直接讀，不用重新抓資料。影片旁只要有資料檔（NFO，記著片名、女優、標籤）和封面圖，掃描就讀進來，檔案原封不動；Jellyfin／Emby 或其他寫標準 NFO＋封面的工具整理過的也行。
- **出得去**：整理好的資料檔和封面，Jellyfin／Emby／Kodi 直接認得，接上電視就能播；哪天不用 OpenAver 了，資料都還在你自己的資料夾裡。
- **原始碼公開**：MIT 授權、免費，誰都能看、能改。

**預設不改、不搬、不刪你的影片。** 補資料只會在影片旁邊新增資料檔和圖。只有你按「整理」，才會依你定的規則改名或搬家，而且絕不刪除。程式在你自己的電腦跑，不用註冊。

**100% 本地運行** — 不蒐集資料、不上傳任何檔案資訊，網路請求僅用於刮削公開元數據。

⚡ **[Live Demo → openaver.slive.uk](https://openaver.slive.uk/)**

*裡面只有 mecha 反派與虛構電影海報，零 NSFW。老闆從你身後走過也沒事。*

## 規格速覽

| 項目 | 內容 |
|------|------|
| **平台** | Windows 10/11 · macOS（Apple 晶片 M1 之後） |
| **安裝** | 一行指令或雙擊安裝，免 Docker，全程圖形介面 |
| **接手既有收藏** | 影片旁已有的 NFO 和封面圖直接讀，掃描不改你的檔 |
| **收藏瀏覽** | 封面牆可疊篩選；女優牆可依罩杯、年齡、身高排序 |
| **片庫分析** | 片數、年份、片商、女優、標籤，可疊選，點一下進瀏覽頁 |
| **手機平板** | 同 Wi-Fi 手機／平板瀏覽器可逛；預設不對外，可設密碼 |
| **片庫在 NAS 上** | 桌面 App 連過去用，播放器、字幕、真人驗證不受瀏覽器限制 |
| **抓資料的來源** | 一次查 8 家：JavBus、Jav321、JavDB、DMM、D2Pass、HEYZO、FC2、AVSOX；另 2 家要手動過驗證；可接 Metatube（30+），或請 AI 加自訂來源 |
| **給播放軟體用** | 整理時可產出 Jellyfin/Emby/Kodi 要的 NFO 與封面 |
| **AI 操作** | Claude Code/Cursor 等 AI 工具可以直接下指令整理片庫 |
| **AI 翻譯** | Ollama（本地免費）/Gemini/Claude/OpenAI 相容端點 |
| **授權** | MIT，不用註冊，資料不上傳 |

## 截圖預覽

| 搜尋頁 | 女優收藏 |
|--------|---------|
| ![Search](docs/screenshots/home.png) | ![Actress](docs/screenshots/showcase-actress.png) |

<details>
<summary>更多截圖</summary>

| 搜尋示範 | 女優搜尋 |
|-------------|------------------|
| ![Search Demo](docs/screenshots/demo2.gif) | ![Search](docs/screenshots/search-detail.png) |

| 瀏覽頁・影片 | 瀏覽頁・單片 |
|-------------------|---------------|
| ![Grid](docs/screenshots/showcase-grid.png) | ![Detail](docs/screenshots/showcase-detail.png) |

</details>

---

## 安裝

### 一行安裝

**macOS**（打開「終端機」貼上）:
```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash
```

**Windows**（打開 PowerShell 貼上）:
```powershell
irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex
```

> 💡 不想開 PowerShell：到 [Releases](https://github.com/slive777/OpenAver/releases/latest) 下載 `OpenAver-Windows-Setup.bat` 雙擊安裝。

安裝指令會自己下載最新版、解除系統的安全限制，Windows 還會建立桌面捷徑。升級會保留你的設定，安裝畫面跟著系統語言走。

### 手動下載 ZIP

從 [GitHub Releases](https://github.com/slive777/OpenAver/releases/latest) 下載：

| 平台 | 檔案 |
|------|------|
| **Windows x64** | `OpenAver-vX.X.X-Windows-x64.zip` |
| **macOS arm64** | `OpenAver-vX.X.X-macOS-arm64.zip` |

> ⚠️ 手動 ZIP 需多一步解除安全限制，詳見內附文件；macOS 限 Apple 晶片。

第一次打開會有新手導覽，帶你指定資料夾、按「更新片庫」，不必先讀文件。

> 🐧 **Linux**：無官方安裝程式，可自架區網伺服器用瀏覽器操作，步驟見 [`docs/linux-server.md`](docs/linux-server.md)。

> 🗄️ **Synology NAS**：手動安裝 `.spk`（beta），步驟見 [`docs/synology.md`](docs/synology.md)。

---

## 核心功能

### 📋 片庫管理：先把現有收藏接進來

- **認得別人整理過的東西**：`.nfo` 的片名、女優、標籤、片商、系列、日期，常見檔名的封面（`-poster`、`fanart`、`folder`…）和 `extrafanart/` 都讀。
- **缺什麼補什麼**：掃完列出缺 NFO／缺封面的片，一鍵從網路補齊；只填空欄位，不覆蓋已有資料。
- **女優／標籤別名**：可直接加。中日英、藝名和退休名收成一張卡，打舊名或新名都是同一份片單。
- **來源順序自己排**：拖曳排出偏好順序，一鍵切「無碼模式」只用無碼來源。
- **搬檔時帶走字幕、保留 VR 標籤**：字幕檔跟著走，VR 投影標籤（`_180_LR`、`mkx200`）保留，播放軟體才認得。

### 🎬 瀏覽：用封面逛、用女優找

**播放軟體用檔名找片；這裡用封面、標籤、女優。**

- **封面牆＋大圖**：點封面看劇照、標籤、女優資料，無碼片自動對準人臉裁切，不滿意可手動拖。
- **收藏女優直接看到發行時年齡**：名字後面會多出像 `(28y)` 這樣的標示，她拍那部片當天的年齡。
- **篩選可以一層層疊**：點女優、標籤、片商、導演、系列，只留下全部符合的片；用點的是精確比對，打字是模糊搜尋。
- **橫式封面↔直式卡片一鍵切**：JAV 封面正面在右半邊，切成直式卡片一列放更多，純畫面變形。
- **女優模式**：女優自己一面牆，資料卡含身高、罩杯、三圍、年齡、別名歷史，可排序可篩選。
- **從自己的片庫補女優牆**：按 `+` 看「庫裡有誰、各幾片」清單，別名自動合併，點愛心加入。
- **相似探索**：點魔杖，同類片圍著主圖，斷線也能看。
- **整理完馬上看得到**：在搜尋頁整理成功的片直接飛進瀏覽頁；片庫連不到時，底部狀態列會寫出是哪一個。
- **手機、平板也能逛**：設定裡切「伺服器」，同 Wi-Fi 用瀏覽器就能逛，用完切回「單機」關閉對外，介面為觸控重做。
- **離線也能逛**：設定頁一鍵匯出離線網頁，不開程式也能離線看。

### 🔍 搜尋：新片從這裡進來

- **8 家一次查**：對上片庫，收過的會標出來；JavDB 走官方 App 通道，被擋多半仍查得到，封面無浮水印。
- **拖檔案或資料夾進來**：自動認番號、批次查資料、抓封面和劇照，檔名裡的 UC／LEAK／4K 會變成標籤。
- **拖資料夾只看這一層，不往子資料夾找**：整座片庫請到「片庫管理」頁用「掃描資料夾」加入。
- **模糊搜尋三家接力**：打女優、系列、導演、片商或番號前綴，就列出作品。JavBus、DMM、JavDB 照你的順序接力；DMM 含預購片。
- **片商最新作品**：還沒搜尋時，搜尋框下面列出你最近最常收的幾家片商，點一下看它最新出了什麼。
- **看完再整理**：先看大圖確認封面、演員、標籤，按「整理」才改名、建資料夾、寫 NFO、下載封面。
- **書籤**：想看但還沒入手的片先收起來，封面存本機不怕原站掛掉，入庫後自動消失。
- **定時整理**：「待整理」（下載完成資料夾）旁一顆開關，開著後每 12 小時自動查資料、整理，也可立刻執行。
- **已入庫的片可以重抓**：改番號、指定來源，先預覽再決定要不要覆蓋；預設保留現在的標題，NFO 裡的標題格式也能自訂。

### 📊 片庫分析：整座片庫變成看得懂的圖

- **先看全貌，再看細一層**：片數、年份、片商、女優前 25、標籤；往下還有發行時年齡、導演、系列、片商年表、同片搭檔。
- **點了就縮小，而且可以疊**：年份、女優、片商可以同時選，年份還能拖出一段區間，整頁圖表一起變。
- **看到想看的直接過去**：點片數、標籤、導演、系列，帶著目前的條件跳到瀏覽頁看那幾部片；沒收藏的女優在這頁一鍵收藏。

### 📀 唯讀來源：NAS 上的片不搬、不改，也能進播放軟體

想把 NAS 或雲端掛載的收藏掛進 Jellyfin／Emby／Kodi 又不想複製幾 TB 原檔：把那來源標成**唯讀**。

- **來源一個位元組都不動**：只讀，NFO、封面、劇照全部寫到你指定的本地輸出夾。
- **`.strm` 直接餵播放軟體**：只寫著「影片在哪裡」的小檔案，Emby、Kodi 掃到就能播原檔，不用複製。
- **Jellyfin 10.11.7 起 `.strm` 只能寫網址**，寫硬碟路徑的不播。已有網址的（如 Alist／OpenList）用「播放端路徑替換」填開頭，例：`/volume1/cloud` → `http://nas:5244/d/115`。
- **兩台電腦路徑不一樣也行**：路徑不一樣時設一組替換規則自動改寫，既有 `.strm` 一併更新。

### 🌐 AI 翻譯

- 大圖上片名旁一顆翻譯鈕，日文片名一鍵換成你的介面語言，原文留著、可以復原。
- 支援 **Ollama**（本地免費）、**Gemini Flash**、**Claude**、**OpenAI 相容端點**。

### 🔌 接上 Metatube（進階，可不裝）

進階設定可接自架的 [Metatube](https://github.com/metatube-community/metatube-sdk-go)，多 30+ 家，補無碼和小眾片商。

### 🧩 自訂來源：把網站加成來源

內建來源沒收的片——中文片、動畫、片商自己的官網——只要那個網站每部片有自己的編號頁、不用登入就看得到，就能加進來。

- **跟 AI 說一句話就好**：「幫我把 https://… 這個站加成 OpenAver 的自訂來源」，AI 會寫好規則檔、上傳、跑驗收，通過就自動啟用。
- **規則檔只是設定**：只寫片名、封面、女優在哪，不執行程式。想手寫見 [`docs/custom-sources.md`](docs/custom-sources.md)。
- **怎麼用**：入庫後在大圖 ⚙ 重刮時選它。新片入庫和自動搜尋不問它。網站改版就再驗收一次。

想讓魔杖的相似探索也比對封面長得像不像：請 AI 助理照 [`docs/external-ai.md`](docs/external-ai.md) 架圖片相似與人臉對焦的端點；沒架就維持內建做法。

### 🤖 AI agent 幫你打理片庫

本機有一份給 AI 讀的說明。Claude Code、Cursor 讀完就能自己串好幾個步驟，做你懶得一筆筆做的事：

- **「幫我把片子最多的 top 20 女優加入收藏，跳過已收藏的。」**
- **「橋本ありな 跟 新ありな 是同一人而且退休了，幫我加 tag。」**
- **「這篇文章提到的番號，做成有封面的 HTML 頁面。」**
- **「每週一幫我看收藏的女優有沒有新片，有就加進書籤。」**
- **「這個網站的片我也想抓資料，幫我加成來源。」**

一行 curl 讓 AI 自學所有端點（Port 見 Settings 頁「AI API」）：

```bash
curl http://localhost:<port>/api/capabilities
```

<details>
<summary>支援的 AI 工具 · 進階用法 · 玩家彩蛋</summary>

支援任何 function-calling AI 工具：

| 使用方式 | 工具 | 說明 |
|----------|------|------|
| **CLI** | Claude Code, Codex CLI, Gemini CLI, Aider 等 | 終端機直接 `curl` 即可 |
| **IDE** | Cursor, GitHub Copilot in VS Code, Windsurf, Trae 等 | Agent 模式呼叫本地 REST API |
| **桌面 App** | Codex App, Google Antigravity 2.0, Claude Cowork, OpenClaw | 不需開發環境，開箱即用 |

> 💡 想在對話裡看到封面：**Codex App** 或 **Google Antigravity 2.0** 都支援內嵌顯示。

> ⚡ 小模型也行：Gemini Flash、GPT mini、Claude Haiku 都能操作。

> 🪄 **進階玩家彩蛋：FC2 自動找女優。** FC2 多數片沒女優標記，其中不少後來轉有碼出道。SQL 撈空片 → DeepFace 比對 Gfriends → `POST /api/user-tags` 寫回；50 行 Python 跑全庫，未識別的用 DBSCAN 分組。

</details>

---

## 常見問題（FAQ）

**用 OpenAver 整理好的片，能不能給 Jellyfin/Emby/Kodi 用、或跟它們一起用？**
可以。整理時一併產出 NFO 和封面，影片留在原地，Jellyfin、Emby、Kodi 掃到就會顯示；OpenAver 管找片和逛收藏，它們管播放。

**片子在 NAS 或雲端硬碟上，不想搬也不想被改，可以用嗎？**
可以。資料夾設成「唯讀」，原檔不動，資料檔和封面寫到本機，外接碟也行。也能產生 `.strm` 給 Emby、Kodi 播（Jellyfin 10.11.7 起只能寫網址，見上方）。

**OpenAver 會搬移、改名或刪除我的檔案嗎？**
只有按「整理」才會改名或搬家，而且不刪除；同名檔會先問你。其他操作不動影片，補資料只在旁邊加 NFO 和封面。

**換電腦或想備份，需要複製哪些東西？**
設定檔、片庫資料庫、女優照片、縮圖、書籤封面全部集中在 `app/output/` 這個資料夾；複製這一個資料夾就能換電腦或備份。

**Mac 可以用嗎？要裝 Docker 嗎？**
可以。限 Apple 晶片（M1 之後），一行指令或 ZIP，免 Docker。

**片庫放在 NAS 上，可以用桌面 App 直接連過去嗎？**
可以。NAS（Synology 套件或 Linux）或另一台電腦跑 OpenAver，桌面 App 側欄「連線」填網址和密碼。比瀏覽器多三件：用自己的播放器（讀得到 `.srt`）、JavLibrary／FC2-javten 的真人驗證、打開片所在資料夾。路徑不同就設對照表；主機需 0.17.7 以上。

**電腦裡的片子可以用手機或平板逛嗎？**
可以，同一 Wi-Fi 下設定裡打開「伺服器」，手機瀏覽器開網址就能逛，用完關掉不暴露外網。

**如果內建的刮削來源（Scraper）失效了怎麼辦？**
8 家會互相補位，一家失效，其他家還查得到。JavDB 另有 App 通道，被擋時多半仍查得到；也可接 Metatube，或請 AI 加來源。

**內建來源沒有的片（中文片、動畫）也抓得到資料嗎？**
可以，只要那個網站每部片有自己的編號頁、不用登入，就能請 AI 把它加成自訂來源；片入庫後在大圖 ⚙ 重刮時選它即可。

**官方站已經下架的片還查得到資料嗎？**
查得到。桌面版的 JavLibrary、FC2-javten 會跳視窗讓你點一下，通過後自動填回。只限手動精確查，不進批次，也不給 AI。

**可以讓 AI 工具操作 OpenAver 嗎？**
可以。本機有一份給 AI 讀的說明，Claude Code、Cursor 這類工具用一行指令讀完，就能整理片庫、收藏女優、加標籤。

**Windows 關閉視窗後可以在背景跑嗎？**
可以縮到系統匣繼續跑，點圖示再打開；按 X 會問退出或縮小，可勾「不再顯示」記住，之後到「設定 → 系統設定」調整。

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
| **Testing** | Pytest (3,300+ tests) |

### 從原始碼執行

**前置需求**: Python 3.12（與打包版本一致）、Chrome/Edge、[WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703) (Windows 10/VM)

```bash
git clone https://github.com/slive777/OpenAver.git
cd OpenAver
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 開發模式 (Hot Reload)
uvicorn web.app:app --reload --reload-include 'locales/*.json' --host 127.0.0.1 --port 8000

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
│   ├── scrapers/       # 模組化爬蟲 (JavBus/JavDB/Jav321/FC2/AVSOX/DMM/D2Pass/HEYZO + 手動來源 JavLibrary/FC2-javten)
│   ├── database/       # SQLite 資料層套件 (connection/video/actress/alias/tag_alias/migrate, WAL)
│   ├── metatube/       # Metatube 聯邦整合
│   ├── similar/        # 規則式相似片排序 (tag IDF + 系列/片商/女優)
│   ├── focal/          # 無碼封面人臉對焦裁切
│   ├── gallery_scanner.py    # 資料夾掃描入庫（讀既有 NFO/封面）
│   ├── organizer.py    # 檔案整理 + fallback 空值防護
│   ├── readonly_producer.py  # 唯讀來源 → NFO/封面/.strm 輸出
│   ├── path_utils.py   # 跨平台路徑處理 (file:// URI)
│   ├── i18n.py         # 多語系翻譯核心 (t() / fallback chain)
│   └── translate_service.py  # AI 翻譯 (Ollama/Gemini/Claude/OpenAI Compatible)
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

> 💡 請參閱打包版 ZIP 內附的「疑難排解」文件，或看 [GitHub Wiki](https://github.com/slive777/OpenAver/wiki)。

---

## 社群與回報問題

加入 [Telegram 群組](https://t.me/+J-U2l96gv0FjZTBl) 交流討論！

| 管道 | 適用情境 |
|------|----------|
| [GitHub Issues](https://github.com/slive777/OpenAver/issues) | Bug 回報、功能建議、開發討論 |
| [Telegram 群組](https://t.me/+J-U2l96gv0FjZTBl) | 隱私敏感問題、截圖/影片直傳 |

**回報時請附上**：問題描述、重現步驟、OS 版本、日誌檔案（Debug 版啟動腳本取得）。

---

## 致謝

OpenAver 使用並感謝以下開源專案：

- **[FastAPI](https://fastapi.tiangolo.com/)** - 現代化 Python Web 框架
- **[PyWebView](https://pywebview.flowrl.com/)** - 輕量跨平台桌面框架
- **[GSAP](https://gsap.com/)** - 高效能 JavaScript 動畫引擎
- **[DaisyUI](https://daisyui.com/)** - Tailwind CSS 元件庫
- **[Tailwind CSS](https://tailwindcss.com/)** - Utility-first CSS 框架
- **[Alpine.js](https://alpinejs.dev/)** - 輕量 JavaScript 框架
- **[Apache ECharts](https://echarts.apache.org/)** - 片庫分析頁的圖表函式庫

完整的第三方套件版本與授權清單見 [`docs/THIRD_PARTY.md`](docs/THIRD_PARTY.md)。

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
