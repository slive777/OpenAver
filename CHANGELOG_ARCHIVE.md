# Changelog Archive (v0.1.0 ~ v0.11.12)

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 此檔案為歷史封存，最新版本紀錄請見 [CHANGELOG.md](CHANGELOG.md)

## 版本索引

> 定位某版完整內容：搜尋 `## [版本號]`（編輯器 Ctrl-F 或 `grep -n '## \[X.Y.Z\]'`），再讀該段；無需載入整檔。

### 0.11.x

- [0.11.12] 2026-07-12 — javdb released 版打包 metadata 修復（dist-info 剝除根因）+ 非 ASCII 路徑 CAINFO 修復 + 番號 7 字母前綴截斷修復 + 打包產物 runtime 驗證守衛
- [0.11.11] 2026-07-12 — 前端靜態守衛 pytest→lint 全面遷移（test-deflation −70%，`test_frontend_lint.py` 16,749→5,041 行）+ 新 lint 基建（i18n_lint/static_guard_lint/css-guard）
- [0.11.10] 2026-07-10 — 設定頁命名區膠囊化 + 列表生成兩層 IA 重排
- [0.11.9] 2026-07-10 — 掃描頁補資料逐片進度卡 + 命中封面飛入圖書館
- [0.11.8] 2026-07-09 — 各來源評分/簡介補進 NFO（媒體伺服器 enrichment）+ 燈箱中繼資訊美化
- [0.11.7] 2026-07-07 — 搜尋頁體驗優化（搜尋列不擠壓 + 整理發現性 + 入庫飛入動畫加強）
- [0.11.6] 2026-07-06 — 跨機器路徑映射（WSL2+UNC）讀寫全棧收斂 + DB-key 命名空間守衛
- [0.11.5] 2026-07-05 — 唯讀來源生成媒體伺服器庫（.strm 風味）+ 跨機器路徑映射 + 唯讀寫入全面封鎖
- [0.11.4] 2026-07-04 — 唯讀產生庫地基（output_dir 記憶原地更新）+ 掃描頁「試過」記憶 + 來源刪檔 DB-only 清死卡
- [0.11.3] 2026-07-01 — 唯讀來源生成本地媒體庫首發（off 風味，scanner 唯讀+輸出夾生成本地 NFO+封面+劇照）
- [0.11.2] 2026-06-30 — core/database.py 模組化拆分（六子模組套件+永久 facade，消除 Alias repo 鏡像重複碼）
- [0.11.1] 2026-06-28 — JavLibrary 同番號多版本手動切換（三入口封面挑版本，桌面限定）
- [0.11.0] 2026-06-27 — JavBus 過度泛用清償，exact 番號搜尋改依優先序 cascade

### 0.10.x

- [0.10.11] 2026-06-24 — Windows 一鍵安裝捷徑 + Help 頁更新按鈕
- [0.10.10] 2026-06-24 — 封面比例自適應（燈箱不留白）+ 行動相似探索面板
- [0.10.9] 2026-06-22 — Windows 系統匣關閉行為（最小化背景執行）
- [0.10.8] 2026-06-22 — 手機體驗完整化 + 觸控滑動換片 + 伺服器模式 header 精修
- [0.10.7] 2026-06-21 — LAN 伺服器模式（一鍵開放區網手機瀏覽）
- [0.10.6] 2026-06-21 — 前端離線可靠性（本機化第三方套件 + Starlette 安全鎖版）
- [0.10.5] 2026-06-21 — 開發工具鏈硬化（ruff/eslint/stylelint 進 CI）
- [0.10.4] 2026-06-20 — Fluent 材質系統全站統一（6 角色 + 浮動玻璃 chrome）
- [0.10.3] 2026-06-20 — MPA 跨頁無縫轉場（View Transitions）
- [0.10.2] 2026-06-19 — 前端呈現優化合輯（行動相容 + 搜尋詳情資訊密度重排）
- [0.10.1] 2026-06-18 — 進階搜尋發現性重設計（來源膠囊常駐化，移除長壓手勢）
- [0.10.0] 2026-06-18 — 來源穩定性 + 測試硬化（8 源健康金絲雀 + avsox 復活 + Tokyo Hot 修復）

### 0.9.x

- [0.9.11] 2026-06-13 — 外部媒體管理器相容模式（Jellyfin/Emby/Kodi 四態：poster/fanart 命名 + cd1/cd2 合併 + NFO 補欄）
- [0.9.10] 2026-06-12 — 本地 WebP 縮圖快取（opt-in，SSD 出圖不碰 NAS）+ 燈箱單筆刪除（只刪 DB row）
- [0.9.9] 2026-06-11 — 新增 JavLibrary 來源（BETA，桌面專屬，借 PyWebView 過 Cloudflare 人機驗證）
- [0.9.8] 2026-06-06 — dim 暗色主題色彩編碼修復（補 --color-primary/--color-warning，膠囊色相碰撞根除）
- [0.9.7] 2026-06-06 — VR 投影標籤保留 + 自動 VR tag（改名保留 token + NFO 加 VR genre）
- [0.9.6] 2026-06-06 — 封面三態 skeleton/淡入/破圖 + Showcase console 清零（SVG `<template>` bug 修正）
- [0.9.5] 2026-06-06 — async def 同步 I/O 移出 event loop（NAS HDD 凍屏根治）+ 並發硬化 config 鎖
- [0.9.4] 2026-06-04 — 拔除 `primary_source`，搜尋路由統一以 Active Row 拖曳順序為唯一真理
- [0.9.3] 2026-06-03 — Settings IA 退回單欄、metatube 膠囊三態語意修正、無碼 segmented 控件
- [0.9.2] 2026-06-01 — metatube HTTP client 接通（30 provider + SSRF 防護 + NFO `<plot>` 寫出）
- [0.9.1] 2026-05-30 — 進階重刮彈窗（任一片改番號挑來源預覽後覆蓋），三入口統一
- [0.9.0] 2026-05-29 — scraper-federation B1：SourceConfig schema + Settings 6-tab IA + 掃描來源 tab

### 0.8.x

- [0.8.10] 2026-05-28 — 技術債清理：SSRF 白名單、Scanner DB-miss tag 修正、女優查詢改 json_each
- [0.8.9] 2026-05-15 — Onboarding Scanner-first 翻轉、E2E 劇本 v2（7 User Story）、測試守衛體檢
- [0.8.8] 2026-05-13 — 跨語言 Tag Alias 系統 + Search→Showcase pipeline 即時化 + GhostFly 飛行
- [0.8.7] 2026-05-10 — 拔除 CLIP ML 引擎，改純規則式 metadata 多訊號相似探索，ZIP 回 ~43MB
- [0.8.6] 2026-05-09 — 以圖搜圖 Beta（CLIP 512 維向量 + 探索星空 UI），opt-in 80MB 模型本地推論
- [0.8.5] 2026-05-03 — eslint flat config + stylelint 補工具鏈，pytest frontend_lint 測試縮減 50%
- [0.8.4] 2026-05-03 — 全站前端 ESM 模組化（Import Maps + per-page main.js，三大巨型單檔拆解）
- [0.8.3] 2026-05-02 — Alpine 官方插件升級（persist/collapse/focus/intersect）+ 通知中心（sidebar 鈴鐺）
- [0.8.2] 2026-04-29 — ui-conventions 套用剩餘 5 頁，alert()/confirm() 全換 fluent-modal/toast
- [0.8.1] 2026-04-29 — ui-conventions 擴展到 Showcase 女優模式 + Search，Lightbox 開門動畫共用化
- [0.8.0] 2026-04-28 — Fluent 2 視覺語言統一（token / 白名單 / ease 三角色 / §6 5 檢查點，Showcase 影片模式）

### 0.7.x

- [0.7.8] 2026-04-26 — 女優模式動畫補齊 + Physics2D Burst 換照片 picker + Actress Lightbox ghost-fly
- [0.7.7] 2026-04-25 — WinFsp/rclone 相容修正、劇照幽靈 URL 根治、字幕標記誤認番號修正
- [0.7.6] 2026-04-18 — Scanner 一鍵補完大批量（>500 片）confirm gate + resume 流程修正
- [0.7.5] 2026-04-16 — Ghost Fly Grid↔Lightbox 轉場動畫、Floating Hearts 特效、7 步新手教學
- [0.7.4] 2026-04-14 — Actress Alias CRUD 系統 + Scanner 一鍵缺 NFO/封面補完（batch-enrich SSE）
- [0.7.3] 2026-04-13 — Showcase 女優模式（Grid/Lightbox/CRUD）+ 精準匹配 Hero Card
- [0.7.2] 2026-04-12 — Actress Favorite 系統（DB + 照片下載）+ /search DB 優先查詢整合
- [0.7.1] 2026-04-11 — 女優爬蟲重整（Minnano + Wikipedia JP + 4 路 Orchestrator）+ JavBus 女優移除
- [0.7.0] 2026-04-10 — AI API 平台（batch-enrich / fix-numbers / analysis）+ User Tags + 封面補抓

### 0.6.x

- [0.6.7] 2026-04-09 — 整理動效回饋（checkmark/shake/進度條）+ Load More 三入口動畫 + CTA 文案
- [0.6.6] 2026-04-09 — Alpine.js 技術債清理（inline x-data 抽離、消除 window.SearchCore 全域）
- [0.6.5] 2026-04-09 — OpenAI Compatible 翻譯 Provider + Grid「載入更多」+ DMM 分頁 offset 修正
- [0.6.4] 2026-04-04 — Scanner Jellyfin 圖片檢查改手動觸發、打包修復、Design System 元件補齊
- [0.6.3] 2026-04-02 — 測試分層修正（integration→unit）+ E2E 場景清單 + Agentic AI 驗證
- [0.6.2] 2026-04-01 — Agentic AI API 平台（batch-search / generate-from-ids / enrich-single / SQL / capabilities）
- [0.6.1] 2026-03-31 — i18n 補齊（翻譯跟隨 UI 語系 + Tutorial 四語系 + 日文自動跳過翻譯）
- [0.6.0] 2026-03-29 — 四語系 UI i18n（繁中/簡中/日文/英文，~477 key，Settings 語系切換按鈕）

### 0.5.x

- [0.5.5] 2026-03-28 — 字幕檔自動跟隨整理 + Proxy direct 模式 + Settings 搜尋來源 UI 簡化
- [0.5.4] 2026-03-28 — Maker 名稱對照表重建（雙層格式 + DMM 72 筆），統一供三路徑共用
- [0.5.3] 2026-03-28 — Sample Gallery 元件（extrafanart 本地劇照 + GSAP slide 動畫 + 鍵盤/swipe）
- [0.5.2] 2026-03-27 — Metadata Pipeline 補齊（director/duration/series/label NFO 全鏈路 + Showcase 顯示）
- [0.5.1] 2026-03-27 — DMM Scraper 增強（模糊搜尋 SSE + per-item enrichment）+ 各來源欄位補齊
- [0.5.0] 2026-03-25 — JavBus Scraper 完全重寫（移除 jvav）+ Sample Images Gallery + Video Model 擴充

### 0.4.x

- [0.4.4] 2026-03-19 — Lightbox 按鈕改 glass circle overlay + 安裝升級腳本自動清舊版 python/
- [0.4.3] 2026-03-13 — 流暢轉場動畫系統（Showcase/Search）+ 自動化安裝腳本 + Debug 腳本
- [0.4.2] 2026-03-11 — GSAP Showcase 動效系統（全頁動畫）+ Alpine 效能優化（videos[] 移出 reactive）
- [0.4.1] 2026-03-08 — 測試套件整合（去重 + conftest 統一 + 結構歸位 + 覆蓋率補強）
- [0.4.0] 2026-03-08 — GSAP 搜尋頁動畫系統（SSE 漸進搜尋 + Staging Card + Ghost Shared-Cover 轉場）
- [0.4.0] 2026-01-21 — SQLite Data Layer + Thin Client 重構（已併入 0.2.1）

### 0.3.x

- [0.3.6] 2026-02-20 — UNC 路徑修正（WinFsp/NAS 影片播放），path_utils 全反斜線輸出保證
- [0.3.5] 2026-02-20 — suffix_keywords 版本標記 + Jellyfin 圖片模式 + 路徑工具統一 + Design System 補齊
- [0.3.3] 2026-02-19 — Scraper 來源擴充（D2Pass / HEYZO / DMM + Proxy）+ 女優資料卡（gfriends/Graphis）
- [0.3.2] 2026-02-18 — GSAP 前置 + Fluent Material Boost（Canvas/Shell/Surface 三層毛玻璃）
- [0.3.1] 2026-02-11 — Showcase 動態化（SQLite SSR + Grid/Table/List 三模式）+ Alpine.js 全站遷移
- [0.3.0] 2026-02-08 — Bootstrap → DaisyUI 全站遷移 + Alpine.js + 路由 /gallery → /scanner
- [0.3.0] 2026-01-20 — Scraper 模組化（BaseScraper + 5 模組）+ 無碼搜尋（已併入 0.2.1）

### 0.2.x

- [0.2.4] 2026-02-07 — Design System（Fluent Design 2 + AV Card 4 變體 + Toast/Button 元件）
- [0.2.3] 2026-01-23 — Gallery 路徑名搜尋 + 點擊 📁 badge 複製路徑到剪貼簿
- [0.2.2] 2026-01-22 — 番號後綴清理（-UC/-UNCEN 等），搜尋查詢與檔名萃取一致
- [0.2.1] 2026-01-22 — FC2/無碼搜尋 + SQLite 本地片庫 + Actress alias 管理（scraper 模組化整合版）
- [0.2.0] 2026-01-18 — macOS 支援（Apple Silicon）+ 多來源循環切換 + Gemini 翻譯雙引擎

### 0.1.x

- [0.1.4] 2026-01-17 — Tutorial Step 5 + 教學範例檔（Windows 包）+ 測試框架（115 case）
- [0.1.3] 2026-01-17 — path_utils 集中化路徑處理，NFO updater / image proxy 全部改用
- [0.1.1] 2026-01-17 — 圖片 proxy Windows 路徑修正 + Settings 手動更新檢查按鈕
- [0.1.0] 2026-01-15 — 初始版本（Spotlight Search + Gallery Generator + Ollama 翻譯 + PyWebView）

## [0.11.12] - 2026-07-12

本版主軸：**javdb 在 released 版復活 — 打包 metadata 修復 + 打包產物 runtime 驗證守衛**（feature/97，spec-97／plan-97，T1–T5）。**這是 0.11.10 之後第一個實際面向用戶的 GitHub release**（0.11.11 為純內部 test-deflation 里程碑、不單獨發版）。使用者唯一可感知的變化：**released 版（Windows/macOS ZIP）指定 javdb 來源搜尋，行為終於與開發環境一致**——能命中就命中，真的查無才回「無結果」。

根因已實證（非推理）：`build.py`／`build_macos.py` 打包瘦身刪除**所有 `*.dist-info`**；`curl_cffi` 的 `__init__` 在 **import 當下**讀自己的 package metadata（`importlib.metadata`），dist-info 不在 → 拋 `PackageNotFoundError`（`ImportError` 子類）→ 被 `core/scrapers/javdb.py` 的 `except ImportError` **靜默吞掉** → `CURL_CFFI_AVAILABLE=False` → 之後每次 javdb 搜尋在第一行就 `return None`、**零 HTTP 請求、零 log**。8 源金絲雀／全套 pytest／smoke 全在 dev venv 跑（dist-info 完好），永遠測不到 packaged 環境的斷裂——所以「測試全綠 → 出貨 → 用戶回報壞的」這條路一直沒被堵。**歷來所有 released Windows/macOS 版的 javdb 從第一天就不能用**（不是先前假設的 CF ban——released 版根本沒發過 HTTP）。

### Fixed
- **javdb released 版永遠「無結果」**：打包不再剝除 `.dist-info`，curl_cffi 在產物內能正常 import，javdb 恢復可用（owner 真機 2026-07-12 實證：補 dist-info + 重啟後搜 DLDSS-491 命中）。全保留 dist-info 壓縮代價僅 ~0.3MB（Windows ZIP 34.8 → 35.1MB，遠低於 48MB 上限）。
- **javdb 在非 ASCII 安裝路徑（中文/日文等同語系）搜尋 `curl error 77`**（feature/98，接續上條 dist-info 修復後才浮現的第二層問題）：打包 launcher 設 `PYTHONUTF8=1` → curl_cffi 用 UTF-8 編 CA 憑證檔案路徑，但 libcurl `fopen` 用系統 ANSI code page（`GetACP`，如 cp950）→ 非 ASCII 路徑對不上 → `curl: (77) error setting certificate verify locations` → javdb 靜默無結果。改用 `locale.getencoding()`（回 ANSI code page、**不受 UTF-8 mode 影響**）編 bytes 覆寫 `CAINFO`，**同語系**非 ASCII 路徑（含**預設** `C:\Users\<中文>\OpenAver`，中文 Windows 使用者預設安裝就中招的族群）javdb 恢復可用；仍完整驗證 TLS、不複製檔案。**javdb-only**（全 repo 唯一 curl_cffi 消費者；`avsox` 走一般 `requests`／OpenSSL 不受影響）。跨語系/emoji 安裝路徑（字元非當前 code page 可表示，極罕見）優雅降級（log warning 一次 + 退回原行為），workaround＝改用純英文安裝路徑。
- **番號 7 字母前綴（如 `PARATHD`）拖檔進來被截斷掉開頭字母**：`parathd-02976.mp4` 拖入被讀成 `arathd-02976`（掉 `P`）→ 找不到資料，而文字輸入正常。根因＝檔名抽番號的字母長度上限（`extract_number`／`organizer`／前端 `file.js` 為 5/6）比 codebase 內已有且已測試的基準（`gallery_scanner` 的 7，含 8 字母英文單字守衛）窄，`re.search`／JS regex 滑窗掉首字。把三處落後上限對齊到 7（`{1,7}`/`{2,7}`）；一併修前端「手動輸入番號」逃生口（`formatNumber` 原把 `PARATHD-02976` 絞成 `RATHD-02976`）。`gallery_scanner`（本就是 7）與 `is_prefix_only`（語意不同、故意保 6）不動。**DMM 原檔下載檔名**（`1sdms00808`／`h_839shic00023` 這類 content-id，issue #86）刻意**不**自動轉標準番號——DMM 特殊映射永遠加不完、且用 per-maker 學習映射，改由用戶輸入正確番號、逃生口兜底。

### Added
#### 🛡️ 打包產物 runtime 驗證守衛（制度化，堵死 dev-only 測試盲區）
- **`scripts/verify_artifact_imports.py`**：用**產物自帶的 Python** 全量 import site-packages 每個頂層套件，任一 fail → build fail。stdlib-only（跑在尚未驗證的 embedded python 上）、layout 無關（`sys.path` 探測，不寫死 Windows `Lib/` vs macOS `lib/pythonX.Y/`）。這正是「dev venv 測全綠、released curl_cffi import 就炸」盲區的守衛本體——刪掉任一套件的 dist-info 或整包，守衛必紅。
- **`scripts/audit_build_artifact.py` 加 dist-info 靜態檢查**（廉價第一道，掃 ZIP 不 import，兩平台皆查）：(a) curl_cffi 套件在但其 `*.dist-info/METADATA` 缺 → hard-fail（點名真兇）；(b) 大規模零 dist-info → hard-fail（防未來全刪回歸）。靜態不取代真 import（「檔案都在，跑起來才知道壞」）。
- **CI `build.yml` 重排**：新增 `verify-windows`（windows-latest）job 下載 Windows ZIP、用產物自帶 `python.exe` 跑 import sweep（Windows ZIP 是 ubuntu cross-build，build 機跑不了 win embedded python）；macOS build job 內就地跑 audit + sweep。**Release 上傳 gate 在 verify 之後**（守衛綠才發版）；macOS 首次掛上 audit（`--max-mb 60`，因 mac baseline 49MB、uvloop 為合法依賴，不照搬 Windows 48）。

### Changed
- **javdb 兩條靜默失敗路徑補診斷 log**（零行為變更，只加可觀測性）：curl_cffi 不可用 → 首次搜尋 log 一次 warning（含原始例外，一次性不刷屏）；HTTP 非 200 → log status code。排查本 bug 最貴的成本就是「零 log」——連「有沒有發請求」都要靠猜。

### 測試
- 全套 pytest **4995 passed, 1 skipped**（unit + integration，排除 smoke／e2e，較 0.11.11 的 4985 +10：dist-info 靜態檢查 7 案例〔curl_cffi 缺 metadata／大規模零 dist-info／mac 皆 hard-fail，含 mutation〕+ javdb 診斷 log 3 案例〔warning 一次含例外／None 容錯不 NameError／非 200 status code，含 mutation〕）＋ `ruff check .` 綠 ＋ `npm run lint` 綠。
- 產物守衛 mutation 實證（對本機 Windows 產物、WSL interop 跑產物自帶 python.exe）：正常 GREEN；刪 curl_cffi dist-info → `PackageNotFoundError` exit 1（本次事故的自動化重演）；刪整包 → 依賴鏈全列 exit 1；還原 → GREEN。audit 真 fixture：新 build GREEN、歷史壞 ZIP（v0.11.10，零 dist-info）RED。
- 來源金絲雀：**7 源 PASS + fc2 SKIP**（unreachable／no probe，站方連線問題非 parser 回歸，advisory；**javdb 本身金絲雀 PASS**——parser 一直健康，壞的是打包）。
- 每 task 獨立 Sonnet structured review（T2/T3/T4/T5 findings 皆修：產物守衛 scanned==0 假綠守衛／audit if-no-files-found／CI YAML semantics／javdb test importorskip）。CI dispatch dry-run + Codex PR review 為 push 後最終網。
- **本版另 bundle 兩個後續修復**（feature/98 javdb error 77 + 番號 cap 對齊）：全套 pytest 升至 **5030 passed / 1 skipped**（+35 自 4995：javdb CAINFO 12 案〔非 win／ASCII 路徑 no-op／ACP 可編→bytes 覆寫 CAINFO／`UnicodeEncodeError` 降級 warn-once／cache sentinel／併發 publish-after-compute／import-time 優雅降級，皆 mutation 驗〕+ 番號 cap 對齊回歸鎖〔parathd 各形式／合成 7 字母／8 字母維持不變非回歸／Tokyo Hot・日期・FC2 collision guard／organizer 殘留碎片／前端逃生口，皆 mutation 驗〕）；`npm test` 39 pass；`ruff check .` ＋ `npm run lint:js` 綠。兩者各經獨立 Sonnet review + Codex 二審（javdb import-time 降級測試、番號 `extractChineseTitle`／DMM 恆真斷言、organizer 無鎖）皆修並 mutation 證明。

## [0.11.11] - 2026-07-12

本版主軸：**前端靜態守衛 pytest → lint 全面遷移（test-deflation）**（feature/96，5 plan 96a–96e／3 PR `0.11.11ab`→`0.11.11cd`→`0.11.11`）——**純內部工程里程碑：零產品碼、對使用者完全隱形、不單獨發 GitHub release**（下一個面向用戶的 0.11.12 才是 0.11.10 後第一個實際 release）。north-star（owner 拍板）：**能用 lint 機械處理的，就不該進 pytest、也不該耗 Codex 審**——把 `tests/unit/test_frontend_lint.py` 裡「讀原始碼做字串/結構斷言」的前端靜態守衛搬回它們該去的工具層（eslint／stylelint／node `.mjs` lint 腳本），並止血讓它不再長回來。收益不是測試數字，是把機械式字串存在檢查移出 AI review 的注意力預算。

### Internal
#### 🧹 test-deflation 成果
- **`test_frontend_lint.py` 16,749 行/214 class → 5,041 行/59 class（−70%）**。殘留組成全數記帳：E2E-block 52 class（替代網＝旅程測試，待未來 E2E branch）+ slim-residual 4 class（pytest-justified 極性/scope 語意，逐一標籤）+ 混合殘餘；**8,000 行過渡上限達標**（4,000 完成上限待 E2E branch 適用）。
- **KEEP-justified 36 class relocate 進 `tests/unit/frontend_contracts/`**（7 檔 4,148 行）：跨檔 contract／method-body ordering／call-count／brace-scope 等 node 字串檢查不忠實的真守衛，純搬移零行為變更（pure-move gate：collect test-id 差集空 + byte-for-byte 驗證），明文排除行數棘輪計量。
#### 🛠️ 新 lint 基建（全掛 `npm run lint`，自動進 CI）
- **`scripts/i18n_lint.mjs`**（96a）：i18n key 存在性／四語 parity（warn）／禁詞（「推薦」「風味」）。
- **`scripts/static_guard_lint.mjs`**（96b 建、96d/96e 擴）：表驅動靜態守衛引擎，**886 rule／9 kind**（required/forbidden-string、dup-id、structure-count、tag-scan、inline-style-token、order、file-absent、paired-string〔檔含 A 必含 B〕）+ scope 機制（anchor 缺席 fail-closed、braceBalanced method-body 計數、stripLineComments 注釋剝除）。
- **`scripts/css-guard.mjs`**（96c）：41 CSS-block rule（fluent-materials／poster-crop／z-index 跨檔序／vt-anchor／selector-scope 等）+ stylelint 接線。
- **eslint 新 `SEL_*` 家族**：showModal／tracked-eventsource／longpress／clip-ban／window.open(path) 等 no-restricted-syntax，逐一追加進全部 flat-config 群（防 scoped-group replace trap）。
- **P0 止血**：pre-merge SA-pre-6 改 content-based lint-guard 偵測（掃斷言內容非 class 名，未標 `[lint-guard:*]` 即 BLOCKER）+ `test_frontend_lint.py` 行數硬上限。
#### 🔬 遷移品質方法論（本 branch 最貴的教訓，已固化進 plan-context gotcha）
- **每條遷移 mutation 驗證**：先建網 → 故意破壞 target 必 RED／還原必 GREEN → 才刪 pytest；刪除 commit 附「被刪 class → 替代網 rule」對照表（96e-T5 由獨立 review 50/50 逐條對帳）。
- **Codex 累計抓 7 條「替代網比原 pytest 弱」（scope-narrowing fail-open）全數修復**：element-bound 屬性值未綁值／`\b` 誤當屬性名邊界／class token 非 token 比對／whole-text 掃描被 property-scoped 弱化／複合 scope 漏 1200-char 窗上限／greedy 量詞偏離 find-first 語意／單 match 漏 multi-tag。通則固化：**遷移前記下原 pytest 掃描粒度，替代網必須同粒度，寧 fail-closed 不 fail-open**；mutation 必含 wrong-location 負向案。
- 遷移過程亦修正一個原 pytest 既有錨定 bug（VT head-script 守衛誤鎖無關 script tag，獨立 review 重演證實後改鎖真正 timing-critical script）。

### 測試
- 全套 pytest **4985 passed, 1 skipped**（unit + integration，排除 smoke／e2e，較 0.11.10 的 5523 淨 −538：被刪守衛已由 lint 層 886+41 rule 等價承接，覆蓋面不減、Codex/pytest 注意力預算下降）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint + css-guard + static_guard_lint + i18n_lint + lint-settings-ia）綠 ＋ `npm test`（node:test 28）綠。
- 來源金絲雀：**7 源 PASS + fc2 SKIP**（unreachable／no probe，站方連線問題非 parser 回歸，advisory 記錄）。
- Codex PR review：PR-1 P2×1（eslint persistence.js group 補 selector）、PR-2 P1/P2/P3×4（scope-narrowing）、PR-3 前置審 P1×2+P2×1（1200 窗上限＋lazy 量詞＋multi-tag defer）皆修復並 mutation 證明（修前 GREEN=缺口證實 → 修後 RED）。

## [0.11.10] - 2026-07-10

本版主軸：**設定頁「命名區」膠囊化 + 「列表生成」兩層 IA 重排**（feature/95，Part A spec-95a／Part B spec-95b，兩個獨立部分）——把設定頁兩塊長期是「純文字輸入框 + 一長串控制項」的區域，改成更好懂、更難出錯的形態：命名區（資料夾層級／檔名格式）從手打 `{token}` 字串改成「原子變數膠囊（pill）+ 字面文字自由混排」的視覺化編輯器；列表生成設定拆成「日常常用（外層常駐）」+「離線 HTML 匯出（摺疊進階）」兩層。後端零 schema／DB 變更（僅 format-variables SSOT 端點加情境旗標）。

### Added
#### 🏷️ 命名區膠囊化（Part A）
- **資料夾層級／檔名格式改膠囊編輯器**：每個變數（番號／女優／片商／標題／後綴…）以原子「膠囊」呈現，不再是手打 `{num}` 這種容易打錯的字串；膠囊間可自由插入字面分隔符（`[` `]` `-` `_` 等）。變數選單一鍵插入、膠囊整顆刪除（× 或 Backspace 邊界原子刪，不留 `{titl` 半截），貼上時已知變數自動 tokenize、未知 `{foo}` 保留字面。複用既有 source-pill 視覺（999px accent），與 8+30 來源膠囊一致；IME 組字 / Enter guard 不誤送。
- **資料夾層級改動態清單 + 硬上限 3 層**：可「新增一層／移除此層」，最多 3 層（第 4 層 add 鈕灰化）；載入 >3 層的舊設定自動正規化為前 3 層（保後端有效層、棄第 4 層以上死資料，先 slice 再剝 `{suffix}`）。層順序以穩定 id keying，移除中間層不錯置。
- **`{suffix}` 情境隔離**：後綴變數只在「檔名格式」可用、資料夾層級選單不出現（`folder_ok` 情境旗標，由 format-variables SSOT 端點下發，前後端不再各自硬編變數清單）。

#### 🗂️ 列表生成設定兩層 IA（Part B）
- **sec-gallery 拆兩層**：外層常駐＝日常會調的（排序／順序／每頁數量／最小影片尺寸）；摺疊進階層＝只有匯出離線 HTML 才需要的（顯示模式／輸出目錄／輸出檔名），預設收合。
- **揭露文案克制化**：排序／順序／每頁加「也是你瀏覽頁（Showcase）的預設」揭露；最小尺寸 hint 改寫成「掃描／入庫閾值 — 0 = 不過濾；小於此不入庫（決定你看得到哪些片）」；離線匯出層加 Windows 本機檢視說明條（含 `file://` 成因，材質克制不搶眼）。

### Changed
- 「進階刮削設定」內的命名區改用膠囊編輯器（取代純文字輸入框）；預覽區改以 `x-text` 渲染（移除舊手動 regex escape，天然防 XSS）。
- 列表生成設定 state 旗標 `galleryAdvanced` → `galleryExport` rename（語意更準）。

### Fixed
- **冷模組快取下檔名格式膠囊編輯器持續空白**（95a-T8）：使用者首次開 app／清快取後首載時，「檔案命名格式」膠囊編輯器有時完全空白（存的格式沒渲染成膠囊）。成因是 `loadConfig` 靠單一 `$nextTick` 排的一次性 hydrate callback 在冷模組載入時序下不觸發，而該編輯器又早 mount 過了 ready-gate（資料夾層走 `x-for` 自載、不受影響）。改用 reactive `x-effect` + 響應式就緒旗標 + one-shot 收斂補載，繞過不可靠的單發 `$nextTick`（暖快取本就正常，故只在首次冷載可見）。

### Internal
- format-variables 抽成單一真理來源端點（`/api/config/format-variables`）+ `folder_ok` 情境旗標；補「format-variables ⊆ organizer 消費」契約守衛（pytest）。
- 膠囊 tokenizer（`tokenize` / `serializeTokens`）抽成純函式 + node:test round-trip 守衛（`serialize(tokenize(s)) === s`，與 whitelist 無關）；ChipEditor 為非受控 widget，`naming` closure 存參考不進 Alpine x-data（避免 contentEditable 響應式追蹤導致游標跳）。
- 命名區 ESLint 守衛（膠囊 label brace-strip／禁 raw key）+ orphan 清理 + `/design-system` 同步；列表生成 IA 加 zero-dep lint script（`scripts/lint-settings-ia.mjs` 串 `npm run lint:html`，DOM-ancestry 守 export 控制項必在摺疊內）。
- 命名區新增 i18n key 只寫 `zh_TW`（其餘三語留空靠 fallback，milestone 補譯——已知缺 16 key warning）。
- Codex PR review：95a P1（`{suffix}` 資料夾主動移除 + 前 3 層正規化「先 slice 再剝」順序）、95b P2（IA 守衛補鎖 `avlistOutputDir`／`Filename` 在摺疊內）皆已修。

### 測試
- 全套 pytest **5523 passed, 2 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint + lint-settings-ia）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm）。
- Gemini 3.1 Pro 整支 branch 第二意見：Part A（命名膠囊）**Approved**（讚 SSOT／closure 隔離 contentEditable／純函式 tokenize／slice-before-filter 順序／x-text 天然防 XSS；4 條 advisory 皆低 severity 或 future-note、無 P1）；Part B 本輪 agy 落入 sandbox 對話式 fallback 未取得有效審查（已知失敗態），correctness 由 per-task Sonnet review + Codex PR review 覆蓋。
- **95a-T8 冷載修復由 coordinator CDP 實測驗收**（`cacheDisabled` 冷載 3/3 正確 hydrate、暖載／folder 零回歸、編輯游標不跳、reset 重新 hydrate）。
- E2E-95 runbook 全跑：Part A（A1–A11）+ Part B（B0–B7）全 PASS（A0 即本版修復的 bug）。
- 視覺 hard-gate：命名膠囊觀感／兩層 IA 可掃讀性／Windows 說明條材質克制由 owner 真機驗收。

## [0.11.9] - 2026-07-10

本版主軸：**掃描頁「補資料」升級成逐片「工人在幹活」進度卡 + 命中封面飛入圖書館**（feature/94，spec-94 G1–G7）——把掃描頁「補資料」（batch-enrich SSE）從一個乾計數器 + 終端 log，升級成逐片可視的進度卡：每片輪到時即顯示「番號 · 搜尋中…」，結果回來後切到對應結局（命中／命中無封面／查無／失敗／唯讀跳過）；**命中且有可服務封面時，真封面從進度卡飛進側邊欄「瀏覽」**（＝我的圖書館），落地帶 scale/glow + 微光，進度卡上累計 badge。承接 spec-92 D 項「入庫飛入抽成共用元件（`GhostFly.playInboundFly`）、scanner 接線留未來」——本 branch 就是那個未來，**直接複用該共用入口、不新增動畫 primitive**。後端極小擴充（`EnrichResult.reason` 欄位 + SSE `result-item` 帶 reason），**刻意不碰核心 `search_jav`、零 schema/DB 變更**。

### Added
#### 🎬 掃描頁補資料逐片進度卡 + 命中封面飛入
- **逐片「工人在幹活」進度卡**：補資料時，進度區顯示「目前這片」的可視卡（番號從一開始就在，不等結果），取代乾計數器；五態可辨識——`搜尋中…`／命中封面浮現／`補到資料（無封面）`（文字非破圖）／`查無`（琥珀安靜一閃換片）／`失敗`（進 log）／`跳過（唯讀）`。**命中大聲、落空安靜**：只有真的補到可服務封面才飛入 + badge + 微光，其餘小 glyph 一閃就換片、不搶注意力。
- **命中封面飛入圖書館（兩格待命位 + 延後飛）**：進度卡分兩格——左「待命格」停駐前一片命中封面、右格顯示目前搜尋中；命中封面先進待命格停一個搜尋週期（不一出現就飛），**下一片命中時**前一片才飛向側邊欄「瀏覽」入口（複用 spec-92 `playInboundFly`），run 結束時 flush 最後一片；落地 scale/glow + 側邊欄微光；進度卡上累計 badge（本次 run 補到資料片數，run 後淡出，不做持久紅點）。延後飛用真實補資料節奏當 dwell，讓每顆封面看得清；待命格容器恆渲染固定尺寸，飛入起點 rect 恆有效、免時序 race。
- **手機／減少動態不靜默**：窄螢幕（側邊欄隱藏）逐片反饋交給本就可見的進度卡 + badge，收尾用既有 run-end summary toast（不做 per-item toast，避免批次刷屏）；減少動態下命中僅微光、不播飛行。

### Internal
- 後端只加「scraper parse → `EnrichResult.reason`」+ SSE `result-item` 帶 reason（`reason` ∈ hit／no_cover／not_found／error／readonly；normal 站台靠 `asdict` 自動流出、唯讀/例外站台字面補）；**`search_jav` 零改動**（`git diff` 該檔為空）。前端命中封面 URL 由 `file_path` 自組 `/api/gallery/thumb`，後端不吐 `cover_url`。`GET /api/capabilities` 的 batch_enrich `result_item` output_schema 同步補 `reason`。
- **獨立 sonnet review 抓到並修復一個 bulk race（P1）**：bulk 下片 A 命中排了飛入後，片 B 的 progress 於同一同步 SSE chunk 覆寫進度卡狀態會隱藏片 A 的命中封面 img（rect=0），使片 A 的 `$nextTick` 讀到退化不飛。修法：飛入起點 `x-ref` 從會隱藏的 `<img>` 移到固定尺寸、恆渲染的容器 div，rect 跨換片穩定。
- **Codex PR review P1**：`reason=hit` 原用「cover.jpg 磁碟真相」判，但前端命中封面走 `/api/gallery/thumb`，而 `/thumb` 硬性要求 DB `cover_path` 非空、不 fallback 磁碟 sidecar。兩者判準不同 → 「磁碟有 .jpg 但 DB cover_path 空」（掃描後才丟封面／db·nfo-sourced 命中跳過 `_db_upsert`）時卡片顯示 hit、`/thumb` 404 破圖、且該片仍留 missing_cover 清單。修：`reason=hit` 改為鏡射 `/thumb` 的 gate——所有寫檔完成後重讀 DB 最終狀態，`cover_path` 有值才 hit（散落 sidecar 未入 DB → 誠實回報 no_cover、不飛、不破圖）。含 P3 stale wording 併修。
- **Codex PR #98 review P2**：上條只鏡射了 `/thumb` 第一道 gate（DB `cover_path` 非空）。但 `/thumb` cache miss/disabled 時還有第二道——要讀**實體封面檔**（`uri_to_local_fs_path` 反解後 generate／fallback），檔不在 → 404。故「DB 有記 `cover_path`、但實體封面檔已被刪/移／path_mapping 失效」時仍會誤判 hit → 飛入破圖。修：`reason=hit` 改為**同時**要求 DB `cover_path` 有值 **且**用 `/thumb` 同一解析確認實體檔存在（第三個互補回歸鎖固化；stale-WebP-cache 的 false-negative 是安全方向＝不破圖，已知接受）。

### 測試
- 全套 pytest **5521 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.8 的 5498 +23：reason 映射邊界〔hit/no_cover 依「/thumb 可服務真相＝DB cover_path 有值 + 實體檔存在」分流、not_found/error 各分支〕+ 三個互補 mutation-verified 回歸鎖〔擋「cover_written alone」+ 擋「退回磁碟真相」+ 擋「只鏡射 DB gate 漏實體檔」〕+ result-item 三站台 SSE reason 契約 + /thumb 時序鎖）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，dmm 經 JP proxy live）。
- Gemini 3.1 Pro 整支 branch 第二意見：本輪未取得有效審查——agy headless 落入 apply-patch 假審模式（已知失敗態，見 AI_COLLABORATION 註記），已清理工作區殘留、確認 committed code 零污染；correctness 由 Codex auto-review（P1 已修）+ 獨立 sonnet review（P1 已修）覆蓋。
- 視覺 hard-gate：進度卡五態 + 命中飛入節奏 + badge + 手機 fallback 由 owner 真機驗收。

## [0.11.8] - 2026-07-09

本版主軸：**各刮削來源的評分/簡介補進 NFO（NFO-only，服務媒體伺服器用戶）+ 燈箱中繼資訊美化**（feature/93，spec-93 A/B）——把各來源網站**已提供**的「評分/簡介」在刮削時一併抓出、寫進該片 NFO 的 `<rating>`/`<plot>`，純粹服務透過 OpenAver 唯讀產生庫 + `.strm` 餵 Jellyfin/Emby/Kodi 的用戶（那些媒體伺服器把 `<rating>`/`<plot>` 當顯示格，現在這些格不再是空的）。**OpenAver 自身介面刻意不顯示、不進 DB、不翻譯**——延續既有 US7「NFO-only」契約，owner 判斷評分擠高分帶區辨力低、簡介是行銷文案，對自身瀏覽低價值，顯示外包給 Jellyfin。另獨立做燈箱中繼資訊的視覺層次美化。零 API/schema/DB 變更。

### Added
#### 🎬 評分/簡介補進 NFO（媒體伺服器 enrichment）
- **六個來源開始填評分 + 簡介**：刮到的評分一律正規化到 0–5，經既有 NFO writer ×2 輸出 Jellyfin 0–10 尺度。
  - **評分**（7 源）：dmm / heyzo / 1pondo・10musume / jav321 / fc2 / javdb / caribbean。
  - **簡介**（6 源）：dmm / heyzo / 1pondo・10musume / jav321 / fc2 / caribbean。
  - javbus / avsox 站上無此兩格 → 不做。
- **各來源取得方式**（除 DMM 評分外皆「同一請求免費、零額外請求」）：
  - **DMM**：簡介＝主查詢已抓回的 `description` 接線；評分＝**獨立 root probe** `reviewSummary(contentId:){average}`（比照既有 genres/sample 三態 cache，schema 不支援即永久停用、probe 失敗降級不影響主 metadata，**硬性禁止擴充主 `DETAIL_QUERY`**——那是 DMM 命脈，未知欄位會讓全片刮不到）。
  - **jav321**：同頁文字 `平均評価: N.N`（直接 0–5，非 GIF 形式，勿 ÷10）+ 描述 div。
  - **fc2**：JSON-LD `aggregateRating.ratingValue`（支援單一物件／頂層陣列／`@graph` 包裹三形狀）+ 接既有已抽卻未使用的 `div.col.des` 簡介。
  - **heyzo**：同一 JSON-LD `description`（評分早已抓）。
  - **d2pass（1pondo/10musume）**：同一 phpauto JSON 加讀 `Desc` + rating 補 `<=5` sanity guard（擋畸形值）。
  - **javdb**：`.panel-block` 文字 `評分: N.N分`（真實用戶評分；站上無簡介）。
  - **caribbean**：其 phpauto JSON API 已全面死→改走 moviepage HTML fallback 解析 `itemprop="description"` 簡介 + `meta-rating` 星數 rune-count（0–5）評分（同一已抓 HTML、零額外請求）。

### Changed
#### 🎨 燈箱中繼資訊視覺層次
- 燈箱詳情列（番號 · 片商 · 導演 · 片長 · 系列 · 發行商 · 發行日期）從同色扁平長串改為可掃讀：番號升一階色階（`--text-secondary`）+ 微加粗一眼可辨、欄位標籤微分層、中繼區以髮絲線（`--stroke-subtle`）與上方克制分隔。不加色塊/玻璃卡/accent 底，封面仍視覺主角。

### Internal
- 評分/簡介只改「scraper parse → `Video.rating`/`Video.summary`」這一段；carrier 產生（`internal_nfo_carriers`）、前端 strip（`strip_internal_nfo_keys`）、NFO fill-if-missing 寫入管線（`nfo_updater`/`organizer`/`enricher`/`readonly_producer`）皆為既有機制、不動；`needs_update()` 不把 plot/rating 列缺料（不觸發掃描頁「缺資料」提醒）。補回歸鎖 `TestNeedsUpdateNeverNagsPlotRating` 固化此契約。
- **Codex PR review P1**：T2 的 D4-gap mutation 驗證用的 restore `sed` 無 count、over-match，把 `_probe_genres`/`_probe_sample_images`/`DETAIL_QUERY` 三個 `{'id': content_id}` payload 一併誤改成 `{'contentId'}`，但這三個 query 宣告的是 `$id` → `DETAIL_QUERY` 送 `contentId` 使 `ppvContent(id:null)` 失敗、DMM exact/producer/enrich 全掉；DMM unit test 全 mock 在 HTTP 層、對 query↔variables 契約盲故未攔到。已修（三 payload 還原 `id`，僅 review probe 保留 `contentId`）+ 補 `TestDMMProbePayloadVariables` 監看真實 POST 斷言各 method 送出的 variables key 對應其 query `$var`（mutation 驗證會攔）。**P2**：fc2 `_get_rating` 補 `{"@graph":[…]}` 包裹形狀防禦。
- **Codex PR #97 re-review P2×3**（皆真實資料流 gap，HTTP-mock 單測看不到、靠讀真 fixture/merge 路徑抓）：〔P2-1〕自動模式 `source_merger.merge_results` backfill 欄位群含 `rating` 卻漏 `summary` → 贏的來源無簡介時合併後簡介遺失、NFO `<plot>` 恆空（多源模式下本功能形同虛設），修：`summary` 加進 `_STR_META_FIELDS`；〔P2-2〕`.get(k,'')` 在「欄位在、值 JSON null」時回 `None`，`Video.summary` 非 Optional str → `Video(summary=None)` 拋 ValidationError 被 broad except 吞 → 整片結果被丟，修：dmm/heyzo/d2pass 三處 `.get(k) or ''`；〔P2-3〕jav321 詳情頁真描述前有空 `.col-md-12` 佔位、`select_one` 停在空佔位 → summary 恆空（T3 合成 fixture 無此佔位故漏），修：scope 主 panel-body 取第一個非空 `.col-md-12`、用真實 fixture 鎖死。三者皆補回歸。
- caribbean 覆蓋經 JP proxy live 驗證（解 plan-93 D9 defer）：其 JSON API 對真實現行番號全面 404，推翻「1pondo 同一 `_parse_json` 代表家族」假設 → caribbean 走 `_parse_caribbeancom_html`，補值落該 HTML fallback。
- `core/scrapers/README.md` §1.4 新增「評分/簡介覆蓋（NFO-only）」矩陣。

### 測試
- 全套 pytest **5498 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.7 的 5447 +51：六源 rating/summary parse 邊界〔0–5 尺度、勿 ÷10 防呆、JSON-LD dict/list/@graph、rune-count 星數、正則 None fallback〕+ DMM `_probe_review` 三態＋降級不影響主 metadata＋query↔variables 契約守衛 + d2pass `<=5` guard 新舊對照 + fc2 dead 變數接線 + NFO 管線回歸鎖〔fill-if-missing 不覆蓋／不 nag plot/rating／echo 路徑空 plot〕+ Codex PR #97 re-review P2×3〔merge summary backfill／null 描述不丟片／jav321 空 col 佔位真實 fixture〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，dmm 經 JP proxy live）。
- Gemini 3.1 Pro 整支 branch 第二意見：**LGTM、零 P1/P2**（跨源一致性、parse 防禦、UI 克制皆讚，無須修改）。
- 視覺 hard-gate：燈箱 `.lb-details` 層次由 owner 真機驗收。

## [0.11.7] - 2026-07-07

本版主軸：**搜尋頁體驗優化（搜尋列不擠壓 + 整理發現性 + 入庫飛入動畫加強）**（feature/92，spec-92 A/B/C/D 四項）——純前端 UX polish + 一個 latent 正確性 bug 修復，零 API/schema/DB 變更。四個彼此獨立的痛點：搜尋列右側控制項擠壓變形、整理入口埋在頁尾難發現、整理入庫的「飛入側邊欄」動畫太不明顯、以及把該動畫抽成可跨頁複用的共用元件（本版只做 search 端接線，scanner 接線留未來 branch）。

### Added
#### 🎯 入庫飛入動畫加強（C）
- **整理入庫回饋更有實感**：某片整理成功並寫進資料庫後，一顆封面 ghost 從該片飛向側邊欄「瀏覽」入口——改為三段節奏（起飛 → 於入口旁懸停約 0.5s 微發光讓眼睛看清是哪片 → 縮入落地並帶 scale 彈跳 + 光暈），取代舊版「抵達即淡掉的小點」。
- **窄螢幕／手機不再靜默**：側邊欄隱藏時退化為「已入庫」輕量提示，不再毫無反饋；系統開啟「減少動態效果」時保留輕量落地反饋、不播飛行與縮放。

#### 🎯 整理入口更好找（B）
- **批次整理鈕常駐可見**：拖入一批檔案整理時，「批次整理 N 片」主動作恆在視線內（桌面靠既有固定插槽 + 表頭 sticky；窄視窗改貼底浮動列），不再因結果卡過高被推到畫面外要捲動才找得到。
- **單片／批次整理各有可辨識 icon**：單片＝單一檔案 icon、批次＝資料夾 icon，一眼分辨；空狀態說明文字旁內嵌同款 icon + 同色，文字與畫面上那顆按鈕對得上。

### Changed
#### ⌨️ 搜尋列右側控制項不再擠壓變形（A）
- **「自動」來源膠囊不變形**：在已有結果的頁面回搜尋框打新番號時，「自動」／來源名膠囊不再被壓縮擠壓；右側控制區預留足夠寬度（CDP 實測定值）容納最長來源名 + 清除 + 送出。
- **格狀／詳情切換鈕穩定可見**：女優／前綴搜尋有結果時，格狀↔詳情切換鈕穩定可見可點、不被裁切；打字搜尋新片時暫時讓位屬預期，結果落定後回來。

### Fixed
- **不再出現「兩組相同的 ✕」**：在已有結果的頁面重新搜尋（含用「自動」膠囊重搜）進入載入態時，取消鈕與清除鈕不再並排出現兩顆一樣的 ✕——`hasContent` 由手動維護的旗標改為自動推導的 computed 值，根治整類「漏同步一處就出 bug」的結構性缺陷。
- **整理飛入的封面永遠是「正確那片」**：先前在詳情檢視 X 片時、點清單裡另一片 Y 的「整理此片」，飛出去的會是 X 的封面；改為封面身份永久綁定被整理那片自己的資料（起飛位置才有條件借用目前顯示中的元素）。

### Internal
- 新增參數化共用動畫入口 `GhostFly.playInboundFly`（起點元素／封面 src／終點／fallback 由呼叫端傳入、不綁 search 專屬假設）取代 `playToIcon`：三段 timeline、對稱 `onComplete`/`onInterrupt` cleanup（C21，契約源 `playMobilePanelEnter/Exit`）、通用 scale/glow 落地反饋、並發序列化（`killTweensOf(toEl)` 讓最新落地勝出）。scanner 端接線留未來 branch（共用入口簽章刻意不含 search 假設）。
- `hasContent` 改 Alpine computed getter（移除散落 7 處手動賦值）；`playToIcon` 移除並加 ESLint `no-restricted-syntax` 守衛（definition site + caller site 兩 scope，mutation 自驗 RED 防復活）。i18n 新 key `search.toast.db_synced_mobile` 只寫 zh_TW（其餘三語 fallback）。守衛一律走 ESLint 不落 pytest（本版測試數持平）。

### 測試
- 全套 pytest **5447 passed, 2 skipped**（unit + integration，排除 smoke／e2e，與 0.11.6 baseline 一致、零回歸；本版守衛全走 ESLint，故測試數持平）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。
- ESLint 守衛 mutation 自驗：植入 `this.hasContent = ...`（Group 1）／`playToIcon` 定義或呼叫（Group 1 caller + Group 6 definition）皆轉 RED。
- Codex 二審 F1（P2 並發落地反饋 race）已修（`killTweensOf` 序列化）；F2（P3，無現行回歸）記 accepted residual（`.gsap-animating` 通用性邊界＝各元件 scoped，現行 `#sidebar-showcase-link` 只 transition color/background 不觸 C21；未來 transform/filter transition 的 toEl caller 須補 scoped 規則，scanner 接線 branch 一併補、端到端驗）。
- 視覺 hard-gate：owner 真機一次驗收通過（A pill 不變形／無兩組 X、B icon 辨識 + 常駐鈕、C 飛入節奏 + 手機 fallback）。

## [0.11.6] - 2026-07-06

本版主軸：**跨機器路徑映射（WSL2+UNC path_mappings）的讀寫全棧收斂 + DB-key 命名空間守衛**（feature/91，plan-91 axis-A ＋ plan-91b axis-B）——純 correctness 重構、零使用者可見功能變更、零 API/schema 變動。針對「OpenAver 在 WSL、影片放在網路磁碟（UNC `//NAS/share`）、DB 存映射後路徑」這條情境，把兩類長期潛伏的 silent bug 一次修乾淨並上守衛擋死回不去：一是**讀取端忘了在真正碰磁碟前把 `file:///` URI 反解回本機路徑**（縮圖／封面／劇照／串流／女優裁切一律 404 或讀不到）；二是**已反解的值又被餵回 DB key 建構**、落成沒映射過的命名空間，造成 silent DB miss（重複刮削、掉 user_tags、女優照 403）。

### Fixed
- **跨機器路徑（WSL+UNC）下讀圖／串流不再靜默失敗**：縮圖、封面＋劇照、影片串流（seek 206）、女優裁切、相似探索等所有「先讀 DB 路徑再碰磁碟」的入口，統一在磁碟 I/O 前經單一入口反解映射路徑；先前在 `path_mappings` 情境下這些入口會拿映射後的路徑直接碰磁碟而 404／讀不到圖。
- **刮削不再掉使用者標籤（user_tags）live bug**：`web/routers/scraper.py` 對某片重刮時，DB key 由一個已反解的本機路徑裸建構、落成未映射命名空間，導致比對不到既有列、既有 `user_tags` 被當新片覆寫遺失。改為建 DB key 前先 forward-map 回 DB 命名空間，重刮後 user_tags 正確保留（WSL+UNC 回歸測試斷言單一 mapped row + tags union）。
- **NFO 路徑推導反解**：`core/nfo_updater.py` 由影片路徑推導 NFO 檔位置時改用顯式反解入口，跨機器映射下定位到真實本機 NFO。

### Internal
- **axis-A（讀取端反解）**：新增單一顯式入口 `uri_to_local_fs_path()`，取代 22 個站台散落的裸 `uri_to_fs_path`／`coerce` 呼叫（router／scanner／core／enrich 全棧）；27 個純磁碟用途或已處理站台補 `# uri-no-reverse:` marker 標註安全；新增 pytest AST 結構守衛 `test_uri_to_fs_path_reverse_mapping_completeness.py`（sink 白名單＝`open`／`FileResponse`／`os.path.*`／`Path.*`／`shutil.*`），偵測「反解值未經處理直接碰磁碟」→ CI 擋死。含 Codex 兩輪 PR review 修正（enricher DB 命名空間、actress_crop 主流程 403 canonical、守衛 `Path()` 擴充）。
- **axis-A drive-letter remote 反解對齊（Codex PR #94 review P2）**：`reverse_path_mapping` 補上 WSL-mount 候選前綴——當 `path_mappings` 的 remote 端是磁碟機代號（如 `Z:/share`）時，`uri_to_fs_path` 在 WSL 會把 `file:///Z:/share/...` 正規化成 `/mnt/z/share/...`，原本只比對 `Z:\share`／`Z:/share` 兩形式 → miss → fallback 回未反解的 `/mnt/z/...`（該磁碟未掛載時封面／影片／NFO 讀取失敗）。改為額外以 `to_wsl_path(win_prefix)` 產生 `/mnt` 形式候選（dedup，UNC 不受影響、零回歸）。
- **axis-B（DB round-trip 命名空間）**：新增 sink-anchored AST 守衛 `test_db_key_namespace_completeness.py`（錨 DB-key 建構點 `to_file_uri`／`is_known_cover_path`／repo 寫入，非 source），偵測「反解值裸餵 DB round-trip 無 forward-map」→ CI 擋死；獨立 marker `# db-ns-ok:`（不 overload axis-A 的 `# uri-no-reverse:`）。含 Codex 二審修正（守衛 reaching-def marker 界限、keyword sink 抽取）。
- **已接受殘留**：`core/enricher.py` `_write_nfo` 的 `user_tags is None` 分支裸 `to_file_uri` 為 dead path（所有 production 呼叫端恆傳 `user_tags != None`），marker + docstring 已註記，另開 follow-up；plan-91b D4 固化「寫入端命名空間統一（DB 一律存單一 canonical namespace）」暫緩為 feature/92+（守衛已達成 axis-B「不容易觸發」）。

### 測試
- 全套 pytest **5447 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.5 的 5365 +82：axis-A 22 站台 WSL+UNC 反解回歸〔縮圖／封面＋劇照／串流／女優裁切／相似〕+ axis-B 兩 bug 回歸〔刮削 user_tags union 單一 mapped row／enricher NFO DB 命名空間〕+ 兩支 AST 守衛自驗 21 案例〔含植入假違規 mutation 轉紅〕+ nfo_updater／path_utils／showcase／thumbnail_cache 補測 + Codex PR #94 drive-letter remote `/mnt` 候選反解回歸〔命中／backslash 形式／boundary share-vs-share2／UNC 零回歸／e2e〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。
- 真機 E2E hard-gate（WSL2+UNC+path_mappings，CDP + DB SQL 檢查）：sign-off #1–12 全過——縮圖／封面劇照／串流 seek 206／女優裁切主線／similar／enrich NFO 落反解磁碟／fetch-samples 守衛觸發／真刮 MIDV-300 user_tags union 單一 mapped row／NFO 路徑反解／readonly `.strm` 純 marker 零回歸／DB 命名空間三查詢無分裂無重複。關鍵教訓：`D:\123`（`/mnt/` 短路成 drive-letter URI）無法觸發 bug，須非 `/mnt` 路徑 + UNC mapping 才是真觸發。

## [0.11.5] - 2026-07-05

本版主軸：**唯讀來源生成媒體伺服器庫（media-server 風味）+ 跨機器路徑映射 + 唯讀寫入全面封鎖**（feature/90，spec-90 §90a/§90b/§90c）——承接 0.11.3/0.11.4 的唯讀產生庫，這版把「餵給 Emby／Jellyfin／Kodi」這條路走通：唯讀來源除了生成 OpenAver 自己瀏覽的本地庫，還多吐每片一個 `.strm` 捷徑檔給媒體伺服器掃描播放。針對「OpenAver 在這台、媒體伺服器在 NAS／別台」的跨機器情境，新增「播放端路徑替換」規則，把 `.strm` 裡的影片路徑翻成播放端看得懂的路徑；改了規則，既有 `.strm` 一鍵同步改寫。同時把唯讀來源的「零寫入」承諾補到滴水不漏：勾唯讀有破壞性確認、四個會寫回的入口在唯讀產生片上全部停用並導引、切換媒體伺服器模式時清乾淨舊唯讀來源的媒體卡（只清庫、不刪你輸出夾的檔）、產生中途斷線也乾淨收尾。

### Added
#### 🎯 媒體伺服器風味（.strm）+ 跨機器路徑映射
- **唯讀來源可生成 `.strm` 媒體庫給 Emby／Jellyfin／Kodi**：Settings 把模式切到 Emby／Jellyfin／Kodi 後，對唯讀來源「產生」時，除了每片一夾的 NFO＋封面，還多產一個單行 `.strm`（無 BOM）指向雲端／唯讀硬碟上的原始影片。把輸出夾指向 NAS 上一個可寫位置，媒體伺服器就能掃這批片、經 `.strm` 串流播放，而唯讀來源一個 bit 都沒被寫。
- **跨機器「播放端路徑替換」**：當播放的媒體伺服器在別台機器、看到同一顆硬碟的路徑跟 OpenAver 不一樣（例如 OpenAver 上是 `Z:\115`、NAS 上是 `/volume1/115`），到 Settings 加一條映射規則，`.strm` 內就會寫成播放端看得懂的路徑。跨命名空間比對（Windows 顯示 vs WSL 原生皆可對上），播放端路徑原樣寫入不做正規化。
- **改規則即同步改寫既有 `.strm`**：改／加／刪一條映射規則並儲存後，跳「將改寫 N 個 `.strm`」輕量確認（N 為精確計數），確認即依新規則一次改寫所有既有 `.strm`（只覆寫那一行純文字，不動 NFO／封面／DB／影片檔）；刪光規則則還原成本機路徑。OpenAver 自身播放不受影響（從 DB 串流原檔）。

#### 🎯 唯讀寫入封鎖 + 破壞性操作確認
- **勾「唯讀」跳確認**：在 Scanner 把來源勾唯讀時跳確認彈窗，白話說明唯讀代表什麼、輸出夾放哪、跨機器怎麼餵媒體伺服器；確認後才真的勾上，媒體伺服器模式下同時展開「輸出到」欄位。
- **唯讀產生片四個寫入入口停用**：對「由唯讀來源產生」的片，封面牆補圖 icon、燈箱「補資料」「補劇照」、齒輪「進階重刮」四個會寫回的入口全部停用（淺色、不可點、hover 導引「更新請至掃描頁重新產生」），播放／開資料夾／探索相似等唯讀操作照常。後端三個補資料端點也一律拒絕唯讀來源、來源零寫入。

### Changed
- **切換媒體伺服器模式會清掉舊唯讀來源的媒體卡**：在有唯讀來源時切換模式，跳破壞性確認（正確待移除數 + 白話後果 + 多分頁提醒）；確認後移除那些唯讀來源與其媒體卡，之後重新加入即可在新模式重建。**只清 DB 卡，你輸出夾裡的檔案一個都不刪**；可寫來源與其卡完全不受影響（巢狀在唯讀夾下的可寫來源也精準保留）。
- **部署文案清晰化**：把「輸出夾（產出放哪、要可寫、通常在 NAS）」與「播放端路徑替換（影片路徑跨機對應）」兩個容易混淆的欄位講清楚、界線分明；切換彈窗用詞與 checkbox 統一為「唯讀來源」；三模式一律並列「Emby／Jellyfin／Kodi」。Help 新增「唯讀來源 + 讓 Emby／Jellyfin／Kodi 掃到片（跨機器部署）」區塊，把整條部署流程用步驟講通（痛點常在事後播不出才回查，Help 是唯一會回來找的地方）。

### Fixed
- **產生中途斷線乾淨收尾**：產生過程中關分頁／重整／中斷 SSE，後端在下一個檢查點停手、不跑完整來源，尾段仍跳 HTML 產生與完成通知、保留必要收尾（媒體伺服器快取重置），正常跑完零回歸。
- **產生進行中擋切換模式**：一個分頁在產生時，另一分頁切換模式會被擋下並提示「產生進行中，請等產生完成後再切換模式」，避免背景 producer 在清卡後又把卡補回去。
- **切換模式彈窗矛盾修正**：唯讀確認彈窗的「請先去設定切模式」提示改為只在預設模式顯示，不再出現「已在 Emby／Jellyfin／Kodi 模式卻又叫你去切」的自相矛盾。

### Internal
- 新增 `scraper.strm_path_mappings` 設定（加法式遷移補預設）；`core/readonly_producer.py` 加 `.strm` 產出 + `_apply_path_mapping`（file:/// URI 空間比對、最長前綴勝、remote 端 verbatim 不正規化）；`core/readonly_source.py` 抽唯讀判定純資料流層（scraper guard 與 showcase payload `is_readonly_source` 共用）；`core/generate_state.py` 產生進行中登記表（雙 clear-hook 生命週期）。
- 破壞性端點：`POST /api/config/switch-external-manager`（枚舉離線來源 DB 卡 → delete_by_paths + 縮圖失效 → mutate_config 原子移除離線條目 + 設新模式；先 DB 後 config 可自癒失敗序；巢狀可寫來源從刪除集扣除；髒來源路徑 coerce 容錯 skip 不 500）、`POST /api/config/rewrite-strm`（dry-run 精確計數 + best-effort 就地改寫、壞列 skip 不阻斷整批）。兩端點皆使用者觸發維護操作、不揭露 capabilities。
- 前端：唯讀 checkbox 攔截式確認（`:checked` 單向綁定 + `@click.prevent`，非 x-model）、破壞性切換流程（element-bound 綁定 + isDirty 不誤判 + 三處狀態同步）、唯讀產生片四入口 native disabled、strm 映射編輯器 + 範本回顯。
- Gemini 整支 branch 二審 triage：switch 端點髒路徑 coerce 容錯（mirror 既有唯讀判定 guard）、`strmChanged` 補 optional chaining（config.scraper undefined 防崩存檔）；其餘 findings triage 為誤報或已知接受殘留。

### 測試
- 全套 pytest **5365 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.4 的 5171 +194：strm 產出/單行無 BOM/off 不產 strm + 路徑映射三類+邊界/跨命名空間+尾分隔符 + rewrite 端點多片/刪規則還原/off no-op/只動 strm/dry-run 計數/mapped output_dir 反解 + switch 端點 purge 全契約/巢狀可寫扣除/髒路徑容錯 + 唯讀 enrich guard 三端點+混合批/巢狀可寫 override 矩陣 + SSE 斷線生命週期/尾段 abort + 前端停用態/確認彈窗/切換流程守衛 + 五審 file:/// URI 型來源前綴映射對齊 DB 命名空間〔WSL+映射匹配/非映射 canonical/非 WSL round-trip〕 + 整份儲存↔切換真互斥雙向 guard/窗口釋放/重疊存檔第一個結束仍擋切換/三方重疊全清才放行 + 掃描中改 strm 映射 gate〔映射變更擋存檔/未變放行/無 generate 放行〕 + rewrite-strm 掃描中拒絕含 dry_run + strm 映射 fresh getter〔覆寫勝凍結/None 回退凍結/空覆寫寫原始路徑/produce_source getter 供新映射 vs 無 getter 用凍結/getter 在 NFO 後 _write_strm 前才求值的時序鎖〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**7 源 PASS + 1 SKIP**（javbus／jav321／heyzo／d2pass／avsox／javdb／dmm 全 PASS；fc2 unreachable/no probe → SKIP 非 fail，pre-merge live 健康檢查）。
- E2E 真機驗收（CDP + 檔案驗證）：6 大硬閘門全過——strm 規範（單行/無 BOM/正確路徑）、唯讀零寫入（來源逐位元不變）、映射改寫 ≥3 檔抽查 + 刪規則還原、四寫入入口停用態 + tooltip、破壞性切換 purge（零檔案刪除）、產生中擋切換（兩分頁 toast）。
- Codex PR review（90c 二審 Finding 2/3 + PR #93 一審 P2×2〔巢狀可寫 override 唯讀判定、mapped output_dir reverse-map〕 + PR #93 二審 P1+P2×2：巢狀歸屬改「最具體〔最長匹配〕前綴勝」修回上一輪「可寫一律壓唯讀」對反向巢狀〔可寫父+唯讀子〕的回歸〔showcase/scraper/purge 共用同一 is_path_readonly〕、切模式 purge 改雙向互斥〔try_begin_switch 佔全窗口 + generate 掛號 try_mark_generate_active 檢查，杜絕切模式進行中才開始的 generate 把剛 purge 的卡補回〕 + PR #93 三審 P2×2：strm 改寫時 source path 也走 reverse-map〔補上一輪只反解 output_dir 的漏網，WSL+gallery.path_mappings 下改寫內容 == 初次生成內容〕、半填映射規則丟棄〔remote 空的規則前端不存 + 後端 _apply_path_mapping skip，避免前綴被剝只剩後綴破壞 strm〕 + PR #93 四審 P2×1：switch 也序列化〔try_begin_switch 補檢查 _switch_active，第二個重疊 switch 回 switch_in_progress 拒絕，否則第一個 end_switch 會在第二個窗口中清旗標讓 generate 趁隙補回卡〕 + 主動對抗性自審 P1×1：整份設定儲存也讓開 switch 窗口〔update_config 在 is_switch_in_progress 時拒絕，防另一分頁帶舊 directories 快照把剛 purge 的離線來源條目寫回 config；次秒級窗口〕 + PR #93 五審 P2×2：〔P2-f〕唯讀來源前綴改走 `to_file_uri(uri_to_fs_path(path), mappings)` canonical 化〔取代 coerce_to_file_uri 對 file:/// URI 型來源原樣回不套 mapping 的漏——producer 存 DB row 是 mapped 命名空間，URI 型來源前綴對不上 → 唯讀 guard/showcase 旗標/switch purge 全 miss；config.py `_safe_prefixes` 併入共用同一 helper 杜絕重複實作漂移〕、〔P2-e〕整份儲存↔切換改真互斥〔取代上一輪 is_switch_in_progress preflight 的 TOCTOU：存檔可在 switch 開始前通過檢查、卻在 switch 做完後才落盤 → lost-update。改 update_config 持 config-save 窗口、try_begin_switch 見窗口即拒絕，兩者同一 _lock 原子不交錯；owner 拍板互斥鎖，殘留「切換已全做完後才到的舊快照存檔」記為已知限制、靠破壞性 confirm『其他分頁請重整』提示兜底。五審二次 Codex：窗口旗標從 bool 改 **token-set**〔比照 generate 的 _active_tokens〕——bool 版下兩個重疊存檔第一個結束就把共享旗標清掉、第二個仍在寫窗口內 switch 就能進場，race 重新暴露；per-token add/discard 讓第一個結束不清掉第二個窗口，switch 續擋到最後一個存檔結束〕 + PR #93 五審三次 P2×1：〔strm 映射 vs generate〕掃描/產生進行中 gate 掉「有動到 scraper.strm_path_mappings」的整份存檔與 rewrite-strm〔generate 起始把 config 凍結一場沿用，中途改映射存檔 → 該次 generate 之後才產出的 .strm 仍用舊映射且無自動重寫 → 靜默半修永久指錯；owner 拍板精準 gate：is_generate_in_progress 短路後才 diff，只擋真動到映射的存檔、改主題/檔名等不受影響，rewrite-strm 端點同擋含 dry_run，前端顯示 warning toast『掃描完成後再改』〕 + PR #93 五審四次 P2×1：〔strm 映射斷線尾巴殘留〕gate 只看 is_generate_in_progress，但 SSE watcher 偵測到斷線即清 generate token，producer 每片 checkpoint 才看 should_abort → token 清空後仍會多做完當下這片、此時另一分頁可存新映射 → 那片用凍結舊映射落檔且不自癒〔比 P1 殘留嚴重：不像 switch race 下次 generate 自癒〕；owner 拍板 option C：produce_source 注入 strm_mappings_getter，media-server 模式每片寫 .strm 前重讀 fresh 映射〔scanner 注入 load_config().scraper.strm_path_mappings，無 lru_cache 每次讀 disk〕，讓斷線尾巴那片也用當前映射；getter=None 回退凍結 config，既有呼叫/rewrite/測試零行為變更〕 + PR #93 五審五次 P2×1：〔getter 求值時機〕getter 原在 produce_source 片處理開頭 snapshot，但 _write_movie_assets 接著下載封面/生成圖/寫 NFO 才輪到 _write_strm、期間存的新映射會被漏掉 → 改傳 getter callable 往下、在 _write_strm 前一刻才求值（封面/NFO 都寫完後）。殘留降至「getter() 回傳→open() 寫檔」微秒級 GIL 排程窗口，與 generate_state.py 既記錄之 owner-accepted 殘留同類（徹底封死需 option A 綁 token 生命週期至 worker 真停手，已評估否決：跨檔重構+token 洩漏風險比原 bug 更糟）〕）+ Opus 審核（purge 巢狀誤刪 / rewrite 壞列容錯）+ Gemini 整支 branch 二審皆已 triage 修正。

## [0.11.4] - 2026-07-04

本版主軸：**唯讀產生庫「地基」+ 掃描頁「試過」提醒 UX + 來源刪檔清死卡**（feature/89，spec-89 §89a/§89b）——承接 0.11.3 的 off 風味唯讀產生庫，先把「OpenAver 生成的片」變成**一等公民**：系統記住每部片生成在哪個資料夾、這份記憶不被其他操作洗掉，於是重新產生／強制重刮回到同一資料夾原地更新，不再每次多長一個重複垃圾夾（沒封面的片也記得住位置）。站在這塊地基上，再修掃描頁三個惱人問題：已刮過／已生成的片不再被「缺資料」嘮叨、刮不到的片試過一次就跳過不再每次重打、唯讀網盤掉線時明確警告而非靜默報成功，並在來源端刪檔後清掉庫裡對應的死卡（**只清 DB、不動你輸出夾裡的檔案**）。89a 地基多半使用者無感，但讓 89b 與後續 feature/90 全部乾淨。

### Added
#### 🎯 生成片一等公民身分 + 記住輸出夾（89a 地基）
- **重新產生／強制重刮不再長重複夾**：新增 `videos.output_dir` 欄位記住每部片生成的資料夾（同時作為「這是 OpenAver 生成的」可靠標記）——之後重刮回到同一夾原地更新。無封面的片也記得住位置。
- **off 風味輸出夾免設定**：唯讀來源「預設／自瀏覽」風味的產物固定落在 App 自管位置 `output/lib/<來源名>`（比照縮圖、女優封面的慣例），畫面上不再顯示輸出夾欄位、也不會發生「忘設輸出夾→產生 0 片」。給媒體伺服器（Emby/Jellyfin/Kodi）用的風味才可指定任意輸出夾（供後續 feature/90）。
- **同一部片多格式各自有夾**：`.mp4` + `.mkv` 落入不同資料夾、不互相覆蓋。

#### 🎯 掃描頁「試過」記憶（89b）
- **試過／已生成的片不再被嘮叨**：新增 `scrape_attempted_at`「試過」記憶，任何被實際刮過一次（含成功、天生沒封面、查無資料）或 off 已生成的片，都不再出現在底部「缺資料」提示；提示只留給真的還沒處理的片。
- **刮不到的片只試一次**：查無資料的片試過後自動跳過、不再每次重刮（除非強制或改名），仍以檔名顯示在封面牆讓你自行改番號重刮／補封面／留著。

### Changed
- **原地覆蓋精準清殘檔**：重刮同片時，若標題被片商修正（`{番號} {標題}` 檔名改變），舊標題的殘檔會被精準清除、不再越堆越多（只清本片系列檔、不動你自己放進資料夾的檔）。
- **兩顆「缺資料」藥丸文案去重疊**：「NFO 欄位不全」（已刮過只是資料不全）與「缺 NFO 檔案／缺封面檔案」（本體缺件）一眼可辨。

### Fixed
- **唯讀網盤掉線不再誤報成功**：唯讀來源掛載掉線／讀取中途出錯時明確警告並略過（scanner 頁完成 toast、通知中心、完成通知三處都走警告），絕不在資訊不完整時亂清庫。
- **`output_dir` 身分不被補完／重刮洗掉**：`upsert`／`upsert_batch`／enricher 對 producer row 補完或重刮不再弄丟它的位置記憶（否則預設批次補完會例行性洗掉、身分與記位失效）。
- **WSL＋UNC mapped 輸出根定位正確**：`output_dir`／封面落地判斷走 targeted reverse-map，跨機器路徑映射下拿到真實本機路徑。
- **off 固定夾封面可經 image proxy 讀取**：`resolve_output_root` 共用 helper 讓 off 固定輸出夾同步進 `/api/gallery/image` 白名單（否則剛生成的封面／劇照經 proxy 一律 404、OpenAver 自己看不到圖）。
- **producer／「試過」markers 不被重掃或整理搬移洗掉**：`output_dir`／`scrape_attempted_at` 在 `upsert`／`upsert_batch`／`repath` 三處都加「incoming 空／0 則保留既有」保護，避免一般來源「查無資料」的片在資料夾重掃或整理搬移（rename→repath）時被 default 值覆寫、tried 歸零後又跑回「缺資料」提示。
- **重刮寫到一半失敗不再兩頭空**：舊資產清除從「寫新資產之前清」改為「寫成功之後才清、且只清替換已寫成的」——若封面下載失敗或 NFO 寫入失敗，該片先前可用的封面／NFO **保留不動**（同名直接覆寫不預刪、改標題才清舊系列且各資產只在新檔寫成時才刪舊檔），不會清掉舊的卻又沒補上新的。

### Removed
- **來源刪檔清庫裡死卡**：在網盤／NAS 刪了某片後，下次對該來源產生時（**確認來源可達、清單完整且非空**的前提下）清掉庫裡對應的死卡。**預設只清 DB 卡、零檔案系統刪除**（你輸出夾裡的 nfo／封面／資料夾不動）。partial-scan（部分路徑讀取失敗）或空列表時整源不清（保守優先，寧可留死卡也不誤刪活著的片）。
- **拔除無狀態重算夾機制**：刪掉舊的跑時 cover-owners map／hash 尾碼消歧（`_build_owners` 等）改由 DB 存值 + increment 分配；連帶移除失去唯一呼叫者的 `cover_index` 死碼鏈。

### Internal
- DB schema 加法遷移 `output_dir TEXT DEFAULT ''` + `scrape_attempted_at REAL DEFAULT 0`（含一次性 backfill：已有封面／NFO／已生成的舊片自動視為「試過」；舊庫升級不需重建、不報錯）；新增 `get_attempted_index`／`update_scrape_attempted_at`／`insert_if_ignore`／`is_output_dir_taken` repo 方法。
- `resolve_output_root(source, config)` 單一真理 helper（off 固定 / media-server 設定），三 call site（producer output_root、`no_output` guard、image 白名單）共用。
- `_should_skip` 改單一 `attempted` 信號 + `force` 強制重刮參數（僅函式層 plumbing，UI 觸發點為 follow-on）。**行為變化**：移除磁碟 cover 檢查後，外部誤刪輸出夾封面不再自動 self-heal 重建（省成本優先，folder 正確性交給記憶輸出夾地基）。
- 唯讀來源 reachability guard + partial-scan `skipped_paths` 訊號；DB-row-only prune 的「本次列表」用原始掃描清單（非已處理集合），避免把「存在但被 skip」的片誤判消失而刪卡；prune 一併與非唯讀分支對等 invalidate 縮圖快取；完成通知 `no_output`／`unreachable`／`partial` 五步映射打通（per-source warn SSE + 計數 + completion warn-gate + scanner 頁 toast）。

### 測試
- 全套 pytest **5171 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.3 的 5031 +140：89a output_dir 欄位/upsert 對稱保護/佔用查詢 + output_dir/scrape_attempted_at upsert/upsert_batch/repath 三處對稱保護 + stale-clean 寫成功後才清（NFO/cover 失敗保留舊資產） + resolve_output_root 真值表/來源名確定性短碼/image 白名單含 off 根 + 夾位讀存 idempotent/B1/B2/increment + stale title-drift 精準清 + mapped-output 定位/enrich 保留 + 89b scrape_attempted_at 遷移/backfill〔含 output_dir 反推 mutation 鎖〕/三寫入點標記/`_should_skip` skip 矩陣+force + missing-check 排除 produced/tried + reachability/partial 三訊號矩陣 + DB-row-only prune〔跨來源隔離·partial 抑制·只刪 DB 不動檔·should_abort 尾巴防誤刪 mutation 鎖·不誤報成功三情境〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。

## [0.11.3] - 2026-07-01

本版主軸：**唯讀來源生成本地媒體庫（off 風味）**（feature/88，spec-88）——為 scanner 來源新增「唯讀」模式：勾了就不寫回來源夾，改在你指定的本地輸出夾生成一個「每片一資料夾」的媒體庫（nfo + 封面 + 劇照），並直接寫進 DB。適合把影片放在唯讀網盤／NAS 共享／Alist 掛載（不能改名搬移）的人——OpenAver 讀來源、產出整理好的本地庫，來源一個 bit 都不動，之後在 OpenAver 就能瀏覽、串流播放雲端原檔。對雲端足跡極輕（只列目錄 + 真的點播才讀那一部）。接停更的 MDCX 的棒，但預設走純文字產物、零權限門檻。

> media-server 風味（多吐 `.strm` 給 Emby/Jellyfin/Kodi 掃）＋一批 UI 調整延後至下一 branch（feature/89）；本版先交付 OpenAver 自瀏覽的完整體驗。

### Added
#### 🎯 唯讀來源 → 本地媒體庫生成（off 風味）
- **每個 scanner 來源可勾「唯讀」＋設輸出夾**：勾唯讀後不寫回來源，按既有「產生」就對該來源刮削 metadata、線上下載封面/劇照，在輸出夾生成每片一資料夾（`-poster`/`-fanart` ＋ extrafanart），並寫進 DB（`path`＝雲端原始路徑、`cover_path`/劇照指本地）。OpenAver 立即可瀏覽、從 DB 串流播放雲端原檔，封面走本地。**來源零寫入、零讀圖**（只列目錄 + 真的點播才讀那一部）。
- **手動增量、一鍵到底**：往雲盤丟新片後回 OpenAver 對該來源按「產生」，只處理新片（以 DB 為準跳過已生成的）；不背景輪詢雲盤（避免觸發網盤風控）。跑完顯示「新增／略過／刮不到／失敗」四數摘要。
- **同番號多版本防撞**：同一番號的不同版本（各自獨立 `path`）各落入獨立子資料夾、不互相覆蓋。

### Changed
- **唯讀來源整理入口給明確提示**：對唯讀來源觸發「整理（搬移/改名）」時，回明確提示「此來源唯讀，請改用生成本地媒體庫」，而非靜默失敗（含 canonical `file:///` 輸入亦正確攔截）。
- **產生完成通知反映來源失敗**：唯讀來源若整源無法存取，完成通知與 toast 走警告（不再誤報全部成功）。

### Internal
- 新增獨立 producer 服務 `core/readonly_producer.py`（全新 code surface，不重用/不碰既有搬檔 `organize_file` 與寫來源旁 `enrich_single`）；`GalleryConfig.directories` 由 `List[str]` 升級為帶 `readonly`/`output_path` 的 `DirectoryConfig`（`load_config` 加法式向後相容遷移，舊純字串 config 照常載入）＋集中存取 helper（所有 call site 走 helper，禁手寫型別判斷）；`generate_avlist` SSE 迴圈以 thread/queue 橋接 producer（worker 例外顯式接手、不靜默吞）；`/api/gallery/image` 白名單納入各來源輸出夾。DB schema／API 端點／capabilities 零變更。

### 測試
- 全套 pytest **5031 passed, 2 skipped**（unit + integration，排除 smoke/e2e，較 0.11.2 的 4848 +183：config schema/helper/向後相容遷移 + producer 列檔/增量跳過/防撞葉層/寫檔/upsert + SSE thread-queue 橋接/四數摘要/來源級例外契約 + image 白名單 + organize guard(含 file:/// 邊界) + off 風味端到端驗收）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。

## [0.11.2] - 2026-06-30

本版主軸：**core/database.py 模組化拆分**（feature/87，spec-87）——把 2,152 行的單一 `core/database.py` 重構成 `core/database/` 套件，降低 AI 輔助編輯時的長 context 出錯率。**零行為變更、零使用者可見影響、零 API/schema/SQL 變動**。分兩階段：87a 純機械搬移、87b 消除兩個鏡像 repo 的重複碼。對外 `from core.database import X` 路徑字面不變（永久 facade）。

### Internal
- **87a 套件化 + 永久 facade**：`core/database.py` 拆成 `core/database/` 套件，依領域分 `connection` / `video` / `alias` / `tag_alias` / `actress` / `migrate` 六個子模組，`__init__.py` 作為永久 re-export facade（含私有 `_migrate_old_aliases`）。19 個 production 檔與 34 個 test 檔的 import 路徑零改動；唯一 test 調整是 4 個 `get_db_path` monkeypatch target 字串機械式對齊（拆檔後子模組各持 binding 副本所致）。新增 facade export 守衛測試。
- **87b 消除 alias/tag_alias 鏡像重複碼**：`AliasRepository` 與 `TagAliasRepository` 原為逐位元鏡像（差異僅三軸：表名、SQL alias token、record 類），抽出私有共用基類 `_AliasRepositoryBase[T]`（Generic），12 個共用 method 上移、body 逐字保留僅套 `self._table` / `self._sql_alias` / `self._record_cls` 參數化。`sync_from_favorite` 維持 `AliasRepository` 獨有；CD-58-3「uniqueness 只查本表、不跨查」語意由表名參數化結構性保證。淨刪 549 行重複碼。
- 新增跨 repo 行為等價性護欄測試（參數化並列比對兩 repo 的 CRUD/resolve/uniqueness），作為 dedup 安全網。

### 測試
- 全套 pytest **4848 passed, 2 skipped**（unit + integration，排除 smoke / e2e；較 0.11.1 的 4799 +49：facade export 守衛 +1、跨 repo 等價性 +32、87a 過程零淨增、87b 淨變化 0）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live）。
- 等價性網以 mutation 實證：故意拼錯任一條 json_each 查詢即令對應 repo 測試紅燈，且跨 repo 網能定位到出錯的那個 repo。

## [0.11.1] - 2026-06-28

本版主軸：**JavLibrary 同番號多版本手動切換**（feature/86，spec-86）——AV 番號會被不同片商跨年代重複使用（如 `MIDV-013`：舊片 vs MOODYZ 新片），預設都抓到先收錄的舊片。本版讓你在 JavLibrary 看封面手動挑版本。範圍刻意極小：僅 JavLibrary、僅手動入口、桌面 standalone 限定（需 CF transport），不進批次、不揭露 AI。

### Added
#### 🎬 JavLibrary 同番號多版本切換器
- 🎯 **看封面手動挑版本**：同一番號在 JavLibrary 有多個版本（撞號）時，預覽卡出現封面 `‹ ›` 左右切換器 + 琥珀色「找到 X 部同番號作品 N/M」標示，按左右即時翻版本（封面/標題/日期/片商/tags 同步），游標預設停在**最新發行日**那部（多數人要的新片）。一次抓齊所有候選，翻頁不重打。
- 🎯 **三個手動入口都支援**：
  - **搜尋框直搜**：進階搜尋選 JavLibrary → 多版本跳預覽卡 + 切換器 → ✓「採用此版本」進結果區（不寫檔）。
  - **燈箱換來源**：對某片開「換來源」選 JavLibrary → 切換器 → ✓ 寫入選定版本的 NFO/封面（保留「覆蓋不可逆」警告）。
  - **結果卡替換來源**：先用別的來源找到、再「替換來源」成 JavLibrary 多版本 → 切換器 → ✓「替換此版本」就地替換當前卡（不寫檔）。

### Changed
- **「找到 X 部」撞號提示改琥珀色**（同不可逆警語色系，「注意」語意）更顯眼。
- **JavLibrary pill 在搜尋頁進階搜尋解除隱藏**：改由「桌面限定」gate 統一管（非桌面仍灰化不可點）。

### Fixed
- **搜尋頁挑版本後可再次開啟**：採用某版本後，exact 結果頁保留「再開來源/版本挑選」入口（不再因搜尋框與結果同步而消失）；限搜尋 workflow，批次/檔案模式不受污染。
- **搜尋頁挑版本路徑同步搜尋框 query**：採用版本後搜尋框、輸入法判斷、工作階段還原不再殘留舊番號。
- **番號邊界比對補前置**：候選列舉避免把 `AMIDV-010` 之類前置黏連號誤收為 `MIDV-010` 的版本。

### Internal
- scraper 新增同番號全版本列舉（`search_all_versions` / `fetch_by_detail_url`，新片優先排序）+ helper 抽取；後端 `/api/rescrape/preview` 多版本回 `candidates[]`、`EnrichRequest` 新增 `detail_url`（confirm server-side 重抓，不揭露 AI）；前端 rescrape modal 三入口 candidates 短狀態 + 切換器 partial。
- `core/scrapers/README.md` 的「JavLibrary 手動版本切換」由 pending → done。

### 測試
- 全套 pytest **4799 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.11.0 的 4747 +52：scraper 列舉/排序/邊界 + 後端 candidates/detail_url/CF + 前端 state/切換器/入口路由/守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live）。
- Windows 真機驗收：MIDV-013（3 版本）三入口切換器 + 採用皆通過。
- Codex PR review P2 × 2（search 採用 query 同步 / file-mode 入口 gate）已修；Gemini 整支 branch 第二意見 P1 × 1（番號前置邊界）已修。

## [0.11.0] - 2026-06-27

本版主軸：**JavBus 過度泛用清償 + exact 番號搜尋改優先序 cascade**（feature/85，spec-85）——技術債清償與行為修正，預期淨刪碼、不新增使用者功能。核心是讓「來源優先序」這個既有設定**真的被尊重**：以前直接搜番號時，只要 JavBus 有啟用就會搶先回結果（即使你把 DMM 排第一），現在改成嚴格依你拖曳的優先順序逐一查、命中即回。並移除依賴已死端點的 JavBus variant（同番號多版本）探查死碼。

### Changed
#### 🎯 exact 番號搜尋尊重來源優先序（行為分水嶺）
- **直接搜番號改為「優先序串接」**：以前 exact 番號走 fan-out 全打再 merge，且 JavBus 以「是否啟用」為門檻搶先短路——把 DMM 排第一也可能拿到 JavBus 的結果。現在改為依來源優先順序逐一查（cascade），第一個命中的來源即回，DMM 排第一就真的先查 DMM。fuzzy / partial / actress 等其他模式行為不變（已加護欄鎖定不波及）。
- **`/api/search/sources` 依設定回來源順序**：搜尋燈箱的 ⟳ 手動換源輪替順序，現在跟著你在設定頁拖曳的來源優先順序走（以前固定不變）。輪替集合維持 8 個內建來源。

### Fixed
- **DMM 在掃描產生頁 / 單片補資料時不再缺席**：`generate-from-ids` 與 `scrape_single` 路徑先前漏傳 proxy 設定，導致需要 proxy 的 DMM 在資料庫未命中時無法進場；現補齊透傳。
- **JavBus 前綴搜尋的篩選參數真正生效**：前綴搜尋 URL 的 `type` 參數先前用錯接法（`&type=` 落在路徑而非查詢字串），伺服器不解析、前綴過濾從未生效；改為正確的 `?type=`。

### Removed
- **拔除 JavBus variant（同番號多版本）維度死碼**：variant 探查依賴 JavBus 已改版回 404 的搜尋端點，永遠撈不到東西卻每次多打一次請求、增加被 ban 風險。全棧移除——後端 variant 探查與 `/api/search` 的 `variant_id` 參數、前端燈箱的 variant 輪替維度、相關死碼常數，並加 ESLint 語法樹守衛防止回流。對使用者無可見功能損失（該功能本就壞著）。

### Internal
- `normalize_number` 解耦為獨立函式，番號正規化不再無謂實例化 JavBusScraper。
- `D7` 來源順序 helper（`get_switchable_source_ids_ordered`）採 present-then-append + 限縮正規 8 內建來源：partial 設定檔下補齊缺席來源、且過濾掉 schema 合法但不可切換的未知 builtin id（避免前端輪到時打到無效來源吃 400）。
- `D8` `JavBusScraper.search_by_keyword` 補 docstring 標明非生產主路徑（介面履約的循序參考實作，不可刪）。
- 新增 `core/scrapers/README.md` 記錄各來源能力矩陣、碰撞行為與搜尋路由決策。

### 測試
- 全套 pytest **4747 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.11 的 4735 +12：cascade exact 路由 / fuzzy-partial 護欄 / proxy_url 透傳 / D7 switchable 來源 present-then-append 與未知 builtin 排除 / partial-config API order / D9 URL 格式）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- Gemini 3.1 Pro 整支 branch 第二意見：LGTM、零 P1/P2。
- Codex 評估期 P1 × 2（D7 partial-config 集合縮小 / D7 未過濾未知 builtin id）已於評估階段修正並補守衛測試。

## [0.10.11] - 2026-06-24

本版主軸：**Windows 一鍵安裝捷徑 + Help 頁更新按鈕**（feature/84）——兩條並行：84a 新增 `OpenAver-Windows-Setup.bat` 雙擊即可觸發 PowerShell 安裝流程（配合 `chcp 65001` 確保中文正常顯示）；84b 在 Help 頁（限桌面 App）新增「更新」按鈕，偵測安裝路徑後以 confirm modal 導引用戶操作（情況 A 預設路徑 / 情況 B 非預設路徑），確認後開外部終端執行安裝腳本。

### Added
#### 🪟 Windows 雙擊安裝捷徑（84a）
- 🎯 **`OpenAver-Windows-Setup.bat`**：新增於 repo root，雙擊即呼叫 PowerShell 以 `irm | iex` 方式執行安裝腳本；加入 `chcp 65001` 確保 UTF-8 終端顯示；CI Release 同步上傳此 bat 至 GitHub Release Assets。

#### ⬆️ Help 頁一鍵更新（84b）
- 🎯 **桌面 App 專屬更新按鈕**：偵測到有新版時，Help 頁出現「更新」按鈕（`is_desktop` Jinja gate，桌面 App 才顯示）。
- 🎯 **路徑分流 confirm modal**：點更新先呼叫 `/api/install-context` 偵測是否裝在預設路徑——情況 A（預設）顯示「關閉後依畫面提示繼續」；情況 B（非預設）顯示需手動搬移步驟——確認後呼叫 `/api/trigger-update` 開外部終端執行安裝腳本，操作結果以 toast 回饋。
- 🎯 **後端新增三個元件**：`_is_mac_desktop()`（macOS 桌面 App 偵測）；`GET /api/install-context`（路徑比對，非桌面回 403）；`POST /api/trigger-update`（Windows → PowerShell `CREATE_NEW_CONSOLE`，macOS → osascript Terminal；不揭露給 AI agent）。

### 測試
- 全套 pytest **4735 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.10 的 4710 +25：`_is_mac_desktop()` 真值表 + install-context 路徑算法 + trigger-update subprocess/403 + capabilities 守衛 + Help 頁 Alpine binding 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（含 avsox/dmm/javdb 全綠）。
- Gemini 3.1 Pro 審查：3 條 advisory（hardcoded URL 設計取捨、路徑推斷 fallback 保護、macOS fire-and-forget 設計），無 P1/BLOCKER。
- Codex PR review P1 × 2 已修：API `HTTPException.detail` 改固定中文字串；`_showHelpToast()` 改用 `_toast` Alpine state + `showToast()` 並補 toast DOM。

## [0.10.10] - 2026-06-24

本版主軸：**封面比例自適應 + 行動相似探索面板**（feature/83）——兩條並行：83a 讓燈箱封面不留空白（寬比例作品自動填滿容器、AR 不污染女優模式）；83b 在行動裝置新增相似探索面板（全螢幕疊加 + 六張爆射卡 + 封面飛行進/退場 + 主圖播放按鈕）。

### Added
#### 🪄 行動相似探索面板（83b）
- 🎯 **行動版相似探索**：手機/平板燈箱新增星形爆射相似面板——點 🪄 按鈕開啟全螢幕疊加，六張相似卡從中心爆射散開，中央主圖以飛行動畫從燈箱封面轉入。
- 🎯 **封面飛行進/退場**：主圖以 ghost-fly 動畫從燈箱封面飛入面板（enter），關閉時原路飛回（exit）；進退場期間播放按鈕自動隱藏，不懸空。
- 🎯 **主圖播放按鈕**：相似面板主圖底部中央有播放圓鈕（對齊桌面星空模式，44×44 Fluent 玻璃材質）；drill 動畫中鎖定、無路徑影片時隱藏。
- 🎯 **drill 並發硬化**：快速切換相似卡時舊 drill 立即中止、新 drill 接管；runId guard 確保舊的動畫/狀態不干擾新結果。

### Changed
#### 🖼️ 燈箱封面比例自適應（83a）
- 🎯 **封面不再留白**：燈箱封面改採 aspect-box/modal-hug 模型，以圖片載入事件讀取實際比例，寬比例（橫版封面）自動填滿容器，不再出現上下空白；破圖/未載入時安全回退不塌陷、不污染女優模式比例。
- 搜尋燈箱、搜尋詳情頁封面區同步採用同款模型；search detail 封面留白與劇照截斷一併修正。

### Fixed
- 修正 83a/83b-T1 引入後 `TestCoverLoadingUx67Guard` 四條守衛因 `:class has-cover` 新屬性 + T1 注釋位移雙因導致正則 stale。

### Fixed（行動 UX 優化合輯，fix/0.10-mobile-ux-polish）
- 🎯 **封面牆行動搜尋 toolbar 滾動自動收合**：≤480px 往下滾超過 50px（相對 toolbar 展開當下位置）且搜尋欄位為空時自動收合；有搜尋文字不收。
- 🎯 **封面牆 header 行動搜尋 icon 搜尋中顯示 ✕**：有搜尋條件（tag 點擊 / 女優 / 文字）時 navbar 搜尋 icon 切換為 ✕，點擊一鍵清除所有篩選；URL / persisted state 帶入的初始搜尋也正確同步 icon 狀態。
- 🎯 **Settings toast 行動版移至底部**：≤480px 時 toast 不再從頂部彈出（易被行動瀏覽器 chrome 遮住），改固定於底部顯示。
- 🎯 **伺服器模式切換加確認彈窗**：避免誤觸；點確認才執行切換，點取消維持原狀；同模式不觸發彈窗。
- 🎯 **搜尋列輸入法 compose 態 icon 互斥**：compose 態時隱藏 Grid toggle，避免三個 icon 同時顯示擠爆搜尋列空間。

### 測試
- 全套 pytest **4710 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較初版 4686 +24：行動 UX 守衛 + 伺服器模式確認守衛 + icon 互斥守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**7 PASS、1 SKIP**（jav321 unreachable，已知正常）。
- Gemini 3.1 Pro 審查：LGTM；P2（同模式觸發彈窗）已修（early return guard）。
- Codex PR review P2（showcaseHasSearch 初始化缺漏）已修（init-time sync 補齊）。

## [0.10.9] - 2026-06-22

本版主軸：**Windows 系統匣關閉行為**（feature/82）——在 Windows 點關閉視窗時可選擇「最小化到系統匣繼續背景執行」或「完整退出」並記住選擇，系統匣常駐圖示隨時喚回視窗或切換行為。核心 close-to-tray 由社群貢獻者 @YongCard（PR #77）提供，本版合併後做穩定性硬化並補上設定頁入口。

### Added
#### 🖥️ Windows 系統匣關閉行為
- 啟動即在系統匣顯示 OpenAver 圖示；關閉主視窗時以原生單選提示選擇退出、最小化到系統匣或取消，並可勾「不再顯示」記住選擇。系統匣選單與提示會跟隨介面語系，支援單擊或雙擊重新開啟視窗、切換關閉行為及完整退出 OpenAver。（感謝 @YongCard 貢獻 PR #77）
- **設定 → 系統設定 新增「關閉視窗時」下拉**：可事後改回每次詢問／最小化到系統匣／直接結束，與系統匣選單、關閉提示三方同步；此選項僅在 Windows 桌面 App 顯示。

### Fixed
- **完整退出時正確關閉 LAN 伺服器 listener**：先前 Windows 完整退出（關窗選結束／系統匣結束／強制關閉）皆未停掉對外 listener，可能造成下次啟動偶發 port 佔用；現統一在退出 chokepoint 關閉。

### Internal
- 關閉行為偏好從 `window_state.json` 搬到 `config.general`（單一真理；載入時非法／缺值一律矯正回 `ask`，不破壞舊設定載入）；持久化失敗時保留 session-local 偏好、不中斷關窗流程（best-effort，恢復搬遷前語義）。
- 原生層 grep 測試改 AST 結構守衛（防誤刪、不假驗 ctypes 行為）；ctypes 行為正確性由真機驗收涵蓋。

### 測試
- 全套 pytest **4650 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.8 的 4597 +53：LAN listener 退出 regression / close_action 注入 round-trip + session-local fallback / GeneralConfig 欄位 + 非法持久值矯正 migration / is_windows_desktop 真值表 / Settings 下拉前端守衛 / 原生層 AST 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- Gemini 3.1 Pro 整支 branch 第二意見（A 原生層 / B 整合層分群）：零 P1/P2；Codex implementation review P1（持久化失敗冒泡 UI）+ P1（session 偏好失效）+ P2（非法持久值未矯正）已修。

## [0.10.8] - 2026-06-22

本版主軸：**手機體驗完整化 + 觸控互動 + 伺服器模式 header 精修**（feature/81）——承接 0.10.7 LAN 伺服器模式，把「手機連進來後每頁都好用」補齊：窄螢幕破版修補、加到主畫面有專屬圖示、封面牆與燈箱可左右滑換片，並把設定頁的伺服器模式區塊收斂成更精簡的一排。純前端 / 零後端 API / DB 改動（help 網址顯示為既有 server 模式邏輯的呈現微調）。

### Added
#### 📱 行動完整度（窄螢幕地板 360px）
- 🎯 **封面牆行動搜尋改右上 icon**：手機（≤480px）在封面牆不再被一條搜尋列佔掉頂部空間，改為右上角一顆搜尋 icon，點開才滑出搜尋與篩選/排序控制，用完收起——垂直空間全留給封面。漢堡（左上）與搜尋（右上）各據一角不互遮。平板 / 桌面維持原樣。
- 🎯 **加到主畫面有專屬 App 圖示**：把網址加到手機主畫面會顯示精緻的 OpenAver 圖示（非網頁截圖）；開啟時手機狀態列顏色隨主題融入（深色主題深底、淺色主題淺底）。
- 🎯 **封面左右滑換片**：手機在影片燈箱（封面牆 + 搜尋）可左右滑切換上一 / 下一片，搜尋詳情頁的封面區也可左右滑換上一 / 下一筆——與既有 `<` `>` 箭頭並存，垂直捲動不受影響。劇照、相似推薦等彈窗開啟時不會誤觸換片。

### Changed
#### ⚙️ 伺服器模式 header 收斂（桌面）
- **設定頁 server-mode 收成一排**：「單機 ｜ 伺服器」膠囊移到設定標題右側；開「伺服器」時「伺服器」字以**琥珀色**突顯（＝正在對外曝露）；連線網址去掉 `http://` 只顯示 `ip:port`（複製時剪貼簿仍是完整網址）；複製鈕改純 icon；區網存取警語收進 `?` 提示，不再佔獨立第二排。
- **複製 icon 全站統一**：Help 頁的 curl 複製鈕從 `📋` emoji 改為與全站一致的剪貼簿圖示。
- **Help curl 在桌面主機顯示可分享網址**：開啟伺服器模式後，桌面主機看 Help 的 `curl` 範例會顯示可直接貼給區網其他裝置 / AI agent 的 LAN 網址（而非本機回環位址）；單機模式維持本機位址；取不到 LAN IP 時安全退回本機位址。遠端裝置本就顯示自己的網址、不受影響。

### Fixed
- **設定 / 說明頁在 360px 窄螢幕破版修補**：設定頁外部媒體管理器說明、metatube 連線網址、Help 的 `curl` 指令等長字串不再水平溢出；控件不重疊、不被截斷。
- **封面圓鈕在窄螢幕不再變形**：封面上的播放 / 開資料夾 / 補資料圓鈕在 390px 及更窄的 3 欄格下維持正圓（不再被壓成橢圓），且整體縮小、少擋封面。
- **平板 / 窄窗（481–899px）封面佈局修正**：不再出現「每列 2 個橫式全幅封面」的稀疏佈局，改為比照手機的 4 欄直式右裁封面格；封面牆切換到燈箱時不再「先放大再縮回」的破圖。
- **通知抽屜在手機不被切左緣**：≤480px 通知抽屜改為頂列下方全寬面板（不再因錨定右側鈴鐺而切掉左緣或超出視口）。
- **重刮預覽在手機可讀**：重刮預覽視窗在 360px 改為封面與資訊上下直排，不再左右互擠、文字截斷。

### Internal
- 觸控 swipe 偵測抽為共用純函式 `web/static/js/shared/swipe.js`（`detectSwipe`，含 `|dX|>|dY|` 軸判別防垂直捲動誤觸），三場景（showcase / search 燈箱、detail）各自掛載、沿用既有 prev/next 與 GSAP 切換動畫；全程 passive 不 `preventDefault`，垂直捲動零受損。
- 通知抽屜手機全寬面板改實心填底（移除 backdrop-filter），免疫 0.10.4 的 view-transition 逐格採樣 bug。
- 新增前端守衛：swipe helper 簽名 / 攔截短路串 / 容器隔離（含 detail 封面區排除水平縮圖列）、apple-touch-icon、動態 theme-color、grid 斷點 JS↔CSS 對齊、行動浮層 CSS 結構。

### 測試
- 全套 pytest **4597 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.7 的 4467 +130：swipe helper / 三場景掛載與攔截守衛、行動工具列 / poster 斷點 / apple-touch-icon / theme-color 守衛、server header DOM / clipboard icon / help base_url 守衛、行動浮層 CSS 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- **Gemini 3.1 Pro 三群（A / B / C）分別第二意見：全 Approved / LGTM、零 P1/P2**（僅 cosmetic 級 P3 建議，未採納）；Codex review P2（detail swipe 與水平縮圖列衝突）已修。

## [0.10.7] - 2026-06-21

本版主軸：**LAN 伺服器模式**——讓你在桌面 App 一鍵把這台機器開放給「同一個 Wi-Fi / 區網」的手機、平板、別台電腦，用瀏覽器連進來瀏覽封面牆、線上看片、查番號（feature/80 A 群）。預設仍是「單機」，行為與舊版完全相同。

### Added
- 🎯 **伺服器模式切換**：設定頁右上角新增「單機 ｜ 伺服器」膠囊。切到「伺服器」後下方出現一條連線網址（例如 `http://192.168.1.50:50123`）+ 一鍵複製，把網址用手機瀏覽器打開即可消費；切回「單機」立刻關閉對外。
- 🎯 **即時生效、不用重啟**：切到伺服器當下就在背景開好對外連線，手機馬上連得到，不需要關開 App；切回單機立即停止對外。
- 🎯 **Help 新增「伺服器模式」說明區**：包含怎麼用、安全提醒，以及第一次開啟時系統防火牆會詢問請按「允許」、不小心按了「取消」之後怎麼到防火牆設定救回（Windows / macOS 步驟）。

### Changed
- **單機模式不再跳系統防火牆提示**：桌面 App 平常只綁定本機回環位址（`127.0.0.1`），只有在你主動切到「伺服器」時才會綁定對外位址、觸發一次系統防火牆授權（按「允許」即可，之後記住）。舊用戶更新後維持單機、不會無端冒出防火牆提示。

### Security
- **區網存取閘門**：非本機的連線預設一律擋下（回 403），只有在「伺服器」模式下才放行同區網裝置；本機與桌面 App 自身永遠正常。不信任 `X-Forwarded-For` 偽造、連線來源無法判定時一律從嚴（fail-closed）。
- **開關型別嚴格驗正**：伺服器模式開關只接受布林真假值，擋掉字串 `"false"` 這類會被誤判成「開啟」的輸入，避免意外對外開放。
- 伺服器模式開關**不揭露給 AI agent**（capabilities 守衛把關），避免 agent 自行把機器切成對外開放。

### Non-Goals（本版不含、已規劃）
- **手機完整度**（Settings / Scanner / Help 在 360px 窄螢幕的破版補丁）延後至 feature/81；目前手機連入後 search / showcase 主消費頁已相容，設定 / 掃描頁在極窄螢幕仍有少量排版瑕疵。
- **外網存取 / 帳號密碼 / Web 目錄選擇器 / Docker・NAS 部署**：本版定位 LAN-only 個人 / 家庭用，外網請自接 VPN（如 Tailscale）；NAS 一鍵部署留 epic-synology。

### Internal
- Dual-listener 架構：主回環 listener 永遠運行，伺服器模式由 thread-safe 的 `LanListenerManager` 動態起停第二個 `0.0.0.0` listener（`lifespan="off"` 共用同一 app、不重跑啟動初始化）。
- toggle 端點交易一致性：啟用先起 listener 成功才寫設定（寫入失敗則回滾停掉 listener）；停用先寫設定（閘門即時生效）再停 listener——runtime 與持久化狀態不分離。
- 開發 / 伺服器部署（直接跑 uvicorn、未經桌面啟動器）下膠囊優雅降級回錯誤提示，不崩潰。

### 測試
- 全套 pytest **4467 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.6 的 4435 +32：LAN 閘門矩陣 / listener 生命週期 / toggle 端點 / HOST 拆分 AST 守衛 / 前端膠囊・橫條守衛 / capabilities 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- **Gemini 3.1 Pro 整支 branch 第二意見：LGTM、零 P1/P2/P3**（架構 / 安全 / rollback / AST 守衛獲正面評價）；Codex review P1×2 + P2 已修（toggle 交易一致性 / 例外不外洩前端 / banner 訊息精準）。

## [0.10.6] - 2026-06-21

本版主軸：**前端離線可靠性**——把第三方套件打包進本機、前端錯誤可觀測、修精簡版 Windows 上的啟動問題（feature/79）。

### Added
- 🎯 **離線可用**：GSAP / Alpine.js / 圖示字型改從本機載入，斷網或 CDN 連不到時介面仍完整可用（封面牆、燈箱、動畫、所有互動照常運作）。
- 🎯 **前端錯誤自動記錄**：前端發生錯誤時自動寫進本機 debug.log（純本機、零外送），方便日後排查問題。（背景靜默，一般使用無感）

### Changed
- 🔒 **依賴版本鎖定（可重現建置）**：`requirements.txt` 全面精確鎖版（exact-pin）到已測版本，`requirements-test.txt` 與 macOS 打包都改為繼承 / 安裝同一份鎖版——同一版本號每次都打包出**相同的依賴版本**，避免上游套件靜默升級造成非預期行為。

### Fixed
- 🔒 鎖定 Starlette 至最新修補版 1.3.1，清除 ASGI 底層全部已知安全通報——含 Windows 上透過 `/static` 特製路徑觸發對外 SMB/NTLM 連線洩漏帳號雜湊（CVE-2026-48818）、表單請求資源耗盡 DoS（CVE-2026-54283）等。
- 修正精簡版 / 部分第三方工具處理過的 Windows 上，某些頁面（如掃描頁）按鈕失效、顯示異常的問題（MIME 強制宣告，issue #66）。
- 修正影片燈箱開啟刪除確認框時，按 Esc 會連燈箱一起關、方向鍵會跳到下一部影片的問題。
- 修正掃描頁在模組未載入時顯示 `[object HTMLElement]` 的小問題（改為乾淨空白）。
- 修正 Windows 偵錯啟動檔（OpenAver_Debug.bat）未開啟完整偵錯日誌的問題（對齊 macOS）。

## [0.10.5] - 2026-06-21

本版主軸：**開發工具鏈硬化——lint 守衛進 CI、ruff 補 Python 缺口、清殭屍工具**（feature/78）。純開發工具鏈，**產品 runtime / API / DB / UI 零改動**，產品仍零 node 依賴（node 只在 CI runner）。緣起：前端 lint（eslint + stylelint）過去純本地、CI 只跑 pytest，沒人本地跑就漏；Python 端缺自動守衛（unused import / bare except / 閉包 loop-var 等無人擋）；mypy config 齊全卻從不執行＝假象保護。本版把「擋得住回歸」這件事接上 CI，不再靠開發者記得本地跑。

### Added
- **ruff 導入**：新增 `pyproject.toml`（`[tool.ruff]`，6 規則族 E722/F/B/T201/S110/S112，排除 venv/tools/tests）。存量 184 處違規清零、行為保留：unused import/var 自動修；`raise ... from e`、`zip(strict=)`、閉包 loop-var 綁定等逐條手動修（皆與原行為逐位元相同）。
- **CI lint-frontend job**：`.github/workflows/test.yml` 新增平行 job 跑 `npm ci` + `npm run lint`（eslint + stylelint）+ `ruff check .`，與既有 pytest job 各自獨立擋 PR。
- **CI/工具鏈守衛測試**（`tests/unit/test_ci_workflow_guard.py`）：防 lint job 被靜默移除、ruff 版本兩處漂移、mypy 殭屍復活。

### Changed
- **package-lock.json 進版控**：移除 `.gitignore` 排除行，CI `npm ci` 可重現安裝、鎖定 eslint/stylelint 版本不漂移。
- **ruff 版本鎖定**：`requirements-test.txt` 與 CI 兩處精確 pin `ruff==0.15.17`（lint 是 PR gate，避免 upstream 自動升級在 repo 無改動下讓 CI 轉紅），並以守衛鎖成單一真理源。

### Removed
- **mypy 殭屍**：刪 `mypy.ini` + `requirements-test.txt` 的 mypy / types-requests（config 齊全但 CI 從不跑、歷史 findings 無一條 mypy 可抓）。

### Internal
- **path_utils 契約守衛擴及 `tests/`**：手寫 `file:///` / `[8:]` strip / shadow path helper 在測試碼也擋；先修守衛自傷（自描述文字加 `# path-contract-ok` 錨點）再擴範圍，真違規清零。
- **AGENTS.md `Out of scope` 增量**：新增 Ruff 子段（哪些 Python 問題已由 ruff 接管、reviewer 不再人肉 flag）+ path_utils 契約行；修正過時宣稱（unused var 已歸 ruff）。
- **backstop 保守審計**：lint 進 CI 後逐條審 `test_frontend_lint.py`（182 class）哪些可退役——本版 0 退役（可表達為 lint rule 的重複守衛前幾輪已退，現存皆 HTML 掃描 / 跨檔 contract / line-allowlist 等 lint 不可表達者）；大規模 deflation 留 milestone。
- 新增 `PyYAML` 明確宣告（CI guard 自己的依賴，不再吃 transitive）。`build.py` EXCLUDE_PACKAGES 加 ruff、移除 mypy 殘留（防進 ZIP）。

### Non-Goals（明確不做）
- 不採 `ruff format` / black / pre-commit hook（避免大 diff 汙染 blame、擾 commit 流程）；不全開 ruff 規則（只選定 6 類控存量）。
- 不為拉型別覆蓋率補 type hint（**刪** mypy，不是餵它）。
- 不在本版做 JS 硬編碼 CJK 守衛（eslint AST 不適用、需先 i18n 化現有字串 → 綁下次 milestone i18n sweep）。
- 不動產品 runtime / API / DB / UI；不把 node 帶進產品 ZIP；不重寫 `test_frontend_lint.py`（大規模 deflation 留 milestone）。

### 測試
- 全套 pytest **4367 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.4 的 4355 +12：新增工具鏈守衛 + ruff 清理觸發的重收集）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。

## [0.10.4] - 2026-06-20

本版主軸：**Fluent 材質系統全站統一 — 6 角色材質 + B 浮動 chrome**（feature/77）。純前端、零後端／API／DB、**theme.css 全程零改**——所有材質規則寫進全站最後載入的 `fluent-materials.css`（source-order 覆寫），永不觸發 Tailwind recompile。全部 `[data-theme="dim"]`-scoped（light 模式維持現狀；dim 下材質才生效，避免 light 引用未定義 token 導致背景消失）。把過去零散的「材質三層」收斂成一套**單一 token 系統的 6 角色**：Mica canvas（整頁氛圍）→ Glass shell（側欄／頁首／工具列等殼層）→ Glass panel（閱讀面）→ Glass caption（卡片標題條）→ Glass overlay（燈箱／modal／popover／抽屜）→ Media frame（星空外框）。封面海報維持 100% 乾淨（不加任何 blur／tint，封面是主角）。並把「浮動圓角玻璃條」從 showcase 工具列擴及 search 搜尋列與 settings／scanner 頁首，桌面 chrome 視覺統一。

### Added
#### 🎨 6 角色 Fluent 材質系統（77a / 77b）
- **Mica canvas**：body 整頁漸層氛圍底（fixed、無 blur、隱形級顆粒 grain ~0.03 soft-light），全站 dim 套用。
- **Glass shell**：sidebar／頁首／工具列／footer／手機 nav・抽屜統一毛玻璃殼層（blur-light + saturate + 邊緣高光 inset）。
- **Glass panel**：Settings／Help／Scanner／Search 閱讀面卡片（較重 blur）；卡內子面板只用 sub-tint 不疊第二層 backdrop-filter（避免糊上加糊 + GPU 浪費）。
- **Glass caption**：grid 卡底部標題條改玻璃漸層（gradient + fill，hover 升不透明），**封面海報零材質**、**卡片不加 per-card backdrop-filter**（90 卡效能）；hover 收斂出貨值並中和舊 accent glow。影片卡與女優卡同步。
- **Glass overlay**：lightbox 改單一連續玻璃 shell（metadata 退為 hairline 分隔、非卡中卡）；modal box 用專用 uniform fill token 保護密集文字；help popover／variable-menu／scanner 資料夾下拉／通知抽屜統一浮層玻璃。
- **Media frame**：星空中央封面補 neutral hairline border、與 slot 外框共用同一 token（dim 下整片一致）。

#### 🛸 B 浮動 chrome（77c）
- **showcase 工具列**圓角浮動玻璃條（封面從底下滑過）；**search 搜尋列**桌面（≥1024px）同款浮動圓角（mobile 維持全寬層架，行動相容不變）。
- **Settings／Scanner 頁首**桌面浮動圓角 + 四邊框，並修正標題文字貼左緣（補水平 padding）；置中窄欄頁採「欄寬對齊」（不側內縮，避免與下方滿欄卡片左緣錯位）。

#### 🌗 chrome 置頂條 dim↔light 主題一致（77d）
- **search 搜尋列／Settings／Scanner 頁首／showcase 工具列**的浮動圓角玻璃從原本只在 dim 生效，擴及 **light 模式**——同一條 chrome 在深色／淺色主題下形狀（圓角／浮動／邊框）與材質（玻璃）一致（先前 light 下這些置頂條無浮動、無玻璃，與 dim 長得不一樣）。
- **light 玻璃**為近白霜面 acrylic：半透明 fill（base-100 @55%）+ backdrop blur + 細暗髮絲邊框，深色文字／icon 維持可讀；以 DaisyUI base 調色盤 derive（theme-aware，不硬編碼）。
- **範圍限定**：只置頂條 shell 角色雙主題；其他材質角色（panel／caption／overlay／media-frame）與其餘 shell 面（sidebar／offcanvas／top-navbar／footer）維持 dim-only、light 現狀不變。

### Changed
- **lightbox / modal 由實心 surface 改浮層玻璃**：燈箱內容與 modal 框從 `--surface-2` 實心改為玻璃材質（padding-box／border-box 邊框漸層 + backdrop-filter）；燈箱背幕 scrim 維持中性、封面不染色（否決環境光取色方案）。

### Fixed
- **search 燈箱背景「逐格模糊」（POC 否決效果意外引入）**：search 開 lightbox 時背景每張封面各自被模糊、footer 番號卻銳利（showcase 是整片均勻糊）。根因為 feature/76 給 `#main-content` 加的 `view-transition-name` 使該元素成為 backdrop root，破壞 `position:fixed` 燈箱 scrim 的 `backdrop-filter` 跨格採樣。修法：用 `:has()` 僅在燈箱開啟時退掉該 vt-name（純 CSS、零 JS、feature/76 導航轉場保留），背景恢復整片統一模糊。
- **Settings／Scanner 頁首標題貼左緣**：補水平 padding，文字離邊。

### Internal
- 材質規則 **shell 角色置頂條（search／頁首／toolbar）77d 起雙主題**（dim + light，消費同名 shell token，light 值另定義於新 `[data-theme="light"]` 區塊）；**其餘材質角色與 shell 面維持 `[data-theme="dim"]`-scoped**（light IACVT 安全）。blur 一律走 token（無 hardcoded `blur(30px)`）；每處 `backdrop-filter` 雙寫 `-webkit-backdrop-filter`（macOS WKWebView）。
- 守衛測試套件 `tests/unit/test_fluent_materials_guards.py` 由 12 → **14 條**：77d 改寫 3 條（#2 backdrop 角色分流＝置頂條允許非 dim、其餘須 dim；#10/#11 浮動幾何改 theme-agnostic 斷言）+ 新增 2 條（`test_light_shell_tokens_complete`＝6 個 shell token 須同存 dim+light block 防 IACVT；`test_non_shell_roles_stay_dim_scoped`＝panel／caption／overlay／media-frame 須維持 dim-scoped 防 S-2 越界）。dim-scope／`-webkit-`／no-blur 三條仍標 `[CI-backstop]`（CI 只跑 pytest，stylelint 純本地）。
- 移除 Design System 頁舊「Materials Layer System」demo（HTML subsection + `.ds-material-*` CSS 共 306 行），已被新 `#ds-fluent-materials` 6 角色 demo 完整取代；不留殭屍。

### Non-Goals（明確不做）
- **不動 theme.css**（全寫 fluent-materials.css 覆寫層，免 recompile footgun）、**封面海報零材質**（不加 blur／tint，封面是主角）、**caption 不加 per-card backdrop-filter**（90 卡效能）、**light 材質僅 shell 置頂條雙主題**（77d；其餘角色維持 dim-only、light 現狀不變，不做全材質 light 移植）、**不做封面環境光取色**（scrim 中性）、**不 SPA 化 / 不改後端任何路由・API・DB**。

### 測試
- 全套 pytest **4355 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.3 的 4334 +21；77d +2 守衛）+ `npm run lint`（eslint + stylelint）綠。
- `TestFluentMaterialsGuards` **14 條**（含 3 條 `[CI-backstop]`；77d 改寫 3 + 新增 2）。
- 視覺驗收（CP-B1 / CP-C1）：dim 下 showcase／search／settings／scanner／help 五頁材質 + 浮動 chrome，由 owner 真機眼驗（純視覺，不跑 e2e 截圖）。
- 視覺驗收（CP-D1，77d）：light↔dim 並排，chrome 置頂條形狀＋材質一致、light 玻璃對比可讀，由 owner 真機眼驗並拍板採更玻璃版（fill 55% / saturate 140%）。

## [0.10.3] - 2026-06-20

本版主軸：**MPA 跨頁無縫轉場（Cross-Document View Transitions）**（feature/76）。純前端、零後端/DB/依賴。每次點 sidebar 切頁的白屏閃爍消失，改為主內容區約 250ms 平滑淡入淡出（crossfade），sidebar／logo／通知鈴鐺等持久殼元素視覺靜止不重繪——用瀏覽器原生的跨文件 View Transition 達成，不需 SPA 化、不引入前端路由。漸進增強：不支援的舊版 WebView2／瀏覽器、開啟「減少動態效果」的用戶自動退回現狀硬切，功能零損失、UI 零差異。Showcase 因常駐動畫（燈箱環境光／相似探索星空）與大頁快照成本退出轉場、維持硬切。另含兩個一併修掉的問題：主題切換圓形展開被新命名群組破壞、以及 showcase／search 狀態框在前端初始化前的閃爍（FOUC）。

### Added
#### ✨ 跨頁無縫轉場
- 點 sidebar 切頁（搜尋／掃描／設定／說明之間）從「白屏＋整頁重建」變成「主內容區平滑淡換」；左側 sidebar 與頂部鈴鐺視覺靜止、像焊在原地。
- 純 CSS 啟用（`@view-transition`）＋命名持久區，零 JS 攔截導航——保留瀏覽器原生語義（Ctrl/⌘+點擊開新分頁、右鍵選單等照常）。
- 漸進增強：不支援的環境與「減少動態效果」偏好自動硬切退化，無報錯、無功能損失。
- 小螢幕漢堡選單（offcanvas）導航同樣有轉場。

### Changed
- **Showcase 退出轉場（維持硬切）**：showcase 是全站最重頁且有常駐動畫，進出一律即時硬切（`<head>` 內 parser-blocking script 於 `pageswap`／`pagereveal` 依目的地 URL 呼叫 `skipTransition()`），避免動畫被拍成凍結幀、並省去大頁快照成本。

### Fixed
- **主題切換圓形展開被跨頁命名群組破壞**：跨頁轉場用的 `view-transition-name` 對同頁的主題切換動畫同樣生效，導致 sidebar／主內容脫離整頁快照、圓形展開失效。修法：主題切換期間暫時取消兩區命名、塌回整頁單一快照（specificity 提升、不論順序皆勝）。
- **Showcase／搜尋頁狀態框初始化閃爍（FOUC）**：載入中／空狀態／錯誤三個狀態框缺 `x-cloak`，前端框架啟動前會裸露疊閃一幀；補齊 `x-cloak`（showcase 5 處、搜尋頁 1 處）。

### Internal
- 設定頁既有的主題切換 root 轉場規則作用域化（`html.theme-transition-active` 前綴），不再汙染導航到設定／設計系統頁的整頁淡換。
- stylelint 禁止手動 `view-transition-name: root`；新增跨檔 DOM／CSS 契約守衛（命名／作用域／showcase head script 位置與 parser-blocking／state-page x-cloak，後者以 BeautifulSoup 抓取不受屬性順序影響）。

### Non-Goals（明確不做）
- 不 SPA 化、不引入前端路由、不用 HTMX 整頁 swap、不做共享元素（封面跨頁飛行）轉場、不加 loading bar／骨架屏／prefetch、不在設定加轉場開關、不改後端任何路由／API。
- 守衛路徑（設定未存檔／掃描串流中放棄離開）的程式導航維持硬切（owner 簽核；程式導航本就不觸發跨文件轉場、現狀即硬切、零回歸）。
- showcase 狀態框硬編碼字串的多語系化留 milestone。

### 測試
- 全套 pytest **4334 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.2 的 4308 +26）+ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- 新增測試：`TestPageTransitionDomGuard`（命名 / showcase opt-out / head script 在 head 且 parser-blocking）、`TestPageTransitionSettingsScopeGuard`（settings root 作用域化 exhaustive negative + theme-transition.js class lifecycle）、`TestStatePageCloakGuard`（bs4，showcase 5 / search 2 state-page x-cloak）。
- 跨瀏覽器實機（CDP Chromium 146）：showcase↔他頁雙向硬切（skip）、非 showcase crossfade、主題切換期間命名塌回 root、各頁 console 0 error。

## [0.10.2] - 2026-06-19

本版主軸：**前端呈現優化合輯——行動裝置相容 + 搜尋詳情資訊密度重排**（feature/75）。純前端（CSS / Jinja template / 少量 JS 門檻），**零後端 / DB / serializer / API 改動**。緣起：owner 籌備開放同 LAN 手機連上同一台 server，把三組「以後再說」的呈現痛點推進「本版必修」——搜尋詳情右欄稀疏、翻譯標題沉底；JAV 橫式完整封包封面被裁得帶脊帶封背；以及 hover-only 操作 / scroll trap / JS↔CSS 斷點不一致 / tablet toolbar 裂版等讓真實手機無法操作的缺口。本版分兩階段（plan-75a：封面裁切共用規則 + 行動基礎相容 + 手機相似模式；plan-75b：搜尋詳情重排 + showcase 影片卡 poster 格），並追加燈箱封面去 letterbox 死白、grid→燈箱動畫落地接縫修復，最後把整套行動修正移植到結構近乎雙胞胎的搜尋頁。

### Added
#### 🔍 搜尋詳情資訊密度重排（US1）/ Search detail density rework
- 中文翻譯標題區塊從右欄最底**上移到番號下方、metadata 上方**（不再需捲過 8 個稀疏 row 才看到翻譯）；右欄加寬 320→390px；取消 `.av-card-full-body` 撐高（top-pack，消除大視窗下片名與 metadata 間的拉伸留白）。
- metadata 改**雙欄緊湊排版**：發行日期｜片長、片商｜廠牌各兩兩並排（`.info-grid-pair`），演員 / 系列 / 導演 / Tags 各佔獨行；全欄改 inline label-value（取消舊「label 在上、值在下」block 排法）。≤1024px 折疊單欄時雙欄自動回單欄。

#### 🖼️ 封面正面裁切共用規則（US2）/ Poster-crop shared rule
- 新增 `--poster-crop-ratio`（≈0.71，直式）CSS 變數作單一真理；JAV 完整橫式封包封面只露「封面正面」（`object-position: right center`，取消舊 `100% 20%` 帶脊帶封背的裁法）。星空 slot / 相似主片 / motion-lab clip 三處裁切點統一引用同一規則。

#### 📱 行動裝置基礎相容 + 手機相似模式（US3 / US4）/ Mobile compatibility + similar mode
- **US3 四小修**：搜尋詳情手機可垂直捲動（解 scroll trap）；星空白屏修復（JS bail-to-mobile 門檻與 CSS 隱藏門檻對齊 768→960）；`pointer: coarse` 觸控裝置下 showcase 影片卡 overlay / footer 標題 / 女優卡 overlay 常駐可達（不需 hover）；tablet（769–1023px）toolbar 補規則不裂版。
- **US4 手機相似模式重整**：手機點星空進「主片 + 4 相似推薦」乾淨視圖——修好「只渲染 2 片 / 點不到 / 主片文字被蓋」，相似區移到 metadata 前、主片精簡呈現、4 片全可見可點。

#### 🎴 行動裝置 showcase + 搜尋影片卡 poster 格（US5 / T9）/ Mobile poster grid
- **≤480px** showcase 影片卡改**直式 3 欄 poster 格**（比照女優格），番號單行 ellipsis、女優名次行隱藏；桌面 / tablet 維持橫式 3:2 不變。
- **搜尋頁 grid+lightbox 同款行動修正**（T9）：搜尋頁是 showcase 的近雙胞胎（共用 showcase.css / ghost-fly / 燈箱 DOM、卡片 class 相同），把 3 欄 poster 格 / caption / 觸控 footer 還原 / 燈箱封面去 letterbox / grid→燈箱動畫旗標全部 port 到搜尋頁；全進 search.css，showcase 端零改動。

### Changed
- **燈箱封面貼合原圖比例消死白**（T8）：≤480px 影片燈箱封面從 `object-fit:contain` 在 60vh 高框 letterbox（上下大片死白）改為貼合原圖比例（容器 + img 皆 gate `.has-cover`）；副作用順帶根治 grid→燈箱動畫落地的 cover→contain 接縫（盒比例=圖比例後兩者等價）。女優燈箱、無封面 / 404 影片燈箱皆以 `.has-cover` 三條件排除、不受影響。

### Fixed
- **grid→燈箱 ghost-fly 落地變形**（T7）：≤480px poster 格縮圖（cover 右半）飛進燈箱（完整封面）落地瞬間 cover→contain 硬切變形；改為 ghost 對齊縮圖右裁 + 落地 0.12s crossfade 溶接（女優模式比例對稱、無此問題）。
- **觸控 poster 格番號 caption 被標題層蓋住**（Codex P1）：US3c 的 `@media(pointer:coarse)` 無條件把 `.footer-default` 藏起、改顯 `.footer-hover` 標題層，導致 US5 的番號截斷作用在不可見層；補 `≤480px ∩ pointer:coarse` 交集規則還原番號層。
- **無封面 / 404 影片燈箱塌盒**（Codex P2）：`.has-cover` gate 加上 `!actressLightboxMode() && !!cover && !_heroLightboxImageError` 三條件，避免封面缺失時 `min-height:0` 把 cover 區（含絕對定位的 placeholder / 動作鈕）塌成 0 高。

### Internal
- poster-crop / has-cover / posterCrop 旗標等裁切邏輯一律封裝在 `ghost-fly.js` / token，呼叫端（state-lightbox.js / grid-mode.js）只傳中性旗標，守住 `test_ghost_fly_cropmode` 邊界。搜尋頁 port 採 Parallel（獨立 `.search-grid` / `.search-container` 規則）而非 widen showcase 選擇器，避免動到已驗證的 showcase 規則與守衛；判別子用 `.search-container`（頁面根）隔離兩頁。
- 新增 stylelint rule 禁 `object-position: 100% 20%`（CSS 層），inline HTML 與 selector-scoped 檢查走 pytest（依 CLAUDE.md lint 守衛路由）。

### Non-Goals（明確不做）
- **不做完整 RWD 星空**（手機正確 fallback 到靜態相似列表，星空動畫保持桌面專屬）、**不為無碼封面特判裁切**（一律套同一右裁規則）、**不改後端搜尋路由 / DB / serializer / API 欄位**（pure frontend）、**不改桌面/tablet showcase 影片卡橫式 3:2**、**不在搜尋詳情新增 plot/description 欄位**（只重排現有欄位）、**不改 showcase 燈箱桌面版 metadata 排版**。

### 測試
- 全套 pytest **4308 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.1 的 4249 +59）+ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- 新增測試：US1 搜尋詳情重排守衛（標題置頂 / grid-pair / id 保留 / 右欄 CSS）、US2 poster-crop token + 三裁切點、US3 門檻對齊 + similar safety、US4 手機相似 DOM 順序 + JS 門檻、US5 showcase 3 欄 + poster-crop scope + caption、T7 ghost-fly crossfade 契約、T8 cover-fit、T9 搜尋頁 port（`TestUS9SearchGridMobileFix`）等前端守衛；既有 `TestSwitchSourceBtnRemoved` regex 隨 US1 DOM 重排更新。
- **transient-guard**（下個 milestone 評估刪除）：本版多條「單向遷移後不回退」負向守衛——US1 footer wrapper rename、poster-crop 值/門檻遷移（`100% 20%` / `width:120px` / `4/5` / threshold 768 / 單欄 `1fr`）等標記 `[transient-guard]`；`TestSimilarSlotGsapGuard` 的整檔 JS 字面 ban 屬「應為 eslint 但 CI 未跑 eslint」的 CI backstop，保留至 `npm run lint` 進 CI。

## [0.10.1] - 2026-06-18

本版主軸：**進階搜尋發現性重設計（來源膠囊常駐化）+ 畢業退 toggle + 全面零長壓**（feature/74）。「自訂來源搜尋／挑來源重刮」這個 power 功能過去只能靠**隱形長壓**觸發——畫面零提示、桌面用戶幾乎不長壓，等於對沒讀文件的人隱形；而 🔄 鈕又一顆扛兩意圖（tap=重整、長壓=挑來源）。本版把「來源範圍」從隱藏模式改成**處處可見的來源膠囊**：搜尋列打字後浮出「自動」膠囊（點開挑單一來源）、結果面板把 🔄 換成常駐「目前來源膠囊」（顯示這筆是哪個源找到的 + 點擊換源）、換來源預覽改用唯讀膠囊讓截圖一眼辨識來源。同時**全面移除所有長壓手勢**（覆寫舊「降級保留」決定）、把 Showcase 進階重刮收斂到燈箱齒輪 ⚙，並讓進階搜尋正式**畢業為永久常駐核心**（移除 Settings 開關 + config 欄位 + 一次性 migration）。**後端搜尋路由零改動**（Active Row 仍是唯一真理，本版只改入口可見性）。

### Added
#### 🔎 搜尋列常駐「自動」來源膠囊（US1）/ Always-on auto source pill
- **搜尋列打字後、送出前**（compose 態，番號／女優／前綴模式皆同）在提交鈕左側浮出一顆低調的「自動」來源膠囊，作為「挑來源」的可見把手；**空框不顯示**（維持 Spotlight 乾淨）、**一送出搜尋即隱藏**（出處改由結果面板膠囊承擔，避免重複/誤導）、改動查詢字回 compose 態重新出現。
- 點膠囊開來源 picker，挑某源即以該源跑一次精確搜尋（沿用既有行為）；膠囊用可點互動樣式（pointer + hover），看得出可點、非純標籤。
- **一次性語意**：不記憶、不黏著、不 override Active Row 自動路由（預設搜尋仍走 Active Row 排序）。

#### 🏷️ 結果面板「目前來源膠囊」取代 🔄（US2）/ Result-panel current-source pill
- 搜尋結果 detail 面板**移除 🔄 重新整理按鈕**，原位置改放「目前來源膠囊」：顯示這筆結果是哪個源找到的（有碼藍／無碼綠色彩編碼），點膠囊開來源 picker——picker 內「自動」＝原 🔄 的「換到下一個來源」循環、某具體源＝換成該源的結果（in-place 替換當前卡）。
- 換源／循環中膠囊呈 loading、失敗 shake、完成後即時反映新來源；↗（開原始連結）／📁（本地徽章）行為不變。

#### 🖼️ 換來源預覽顯示來源膠囊（US3）/ Rescrape-preview source pill
- showcase 換來源／重刮的「預覽確認」步驟，把「你剛挑的來源」從純文字「· JavBus」改成 `source-pill` 呈現，採**唯讀 flat 變體**（無 hover、無 pointer，與可點膠囊一眼可分）——確認/截圖時一眼辨識用了哪個源。零 DB 欄位、零 serializer 改動。

### Changed
#### 🚫 全面移除長壓手勢（US4 + 跨 US 原則）/ All long-press gestures removed
- **所有入口的隱形長壓全部移除**（覆寫舊「長壓不刪、只降級」決定，owner 2026-06-18 拍板）：搜尋列提交鈕、結果面板 🔄、Showcase 封面牆／燈箱補資料鈕——次要動作改為看得見的控件或收斂到既有可見入口。
- **Showcase 補資料鈕 🔍**：`tap`＝自動補資料維持不變；長壓移除。**進階重刮／換源收斂到燈箱齒輪 ⚙**（本就可見）——grid 小卡只保留「自動補資料」一個動作，要指定來源重刮就進燈箱點 ⚙。
- 長壓基礎設施本體（`long-press.js` helper、兩頁 mixin 接線、design-system 長壓 demo card）全數退役——全 codebase 零長壓。

#### 🎓 進階搜尋畢業、永久常駐（US6）/ Advanced search graduated to always-on
- **Settings 移除「進階搜尋」開關**：自 v0.9.8 default-on、v0.9.10 de-Beta 後長期穩定 → 正式畢業為永久常駐核心；來源膠囊與 picker 永遠可用、燈箱齒輪 ⚙ 常駐顯示（不再被開關綁架）。
- **移除 `advanced_search_enabled` config 欄位** + 一次性 load-time strip migration：舊 config.json 殘留任何值（含 `false`）載入時即刪除並存檔（**刻意覆寫舊偏好**——畢業核心功能不被舊設定半殘；反轉 v0.9.8「保留偏好」設計）。缺 key 則 no-op、冪等。

### Help / i18n
- **Help 文案改寫零長壓（zh_TW）**：進階搜尋 picker 五入口教學從「長壓送出鈕／🔄 長壓／缺卡長壓／燈箱 ⚙」改寫為新可見控件模型（搜尋列「自動」膠囊／結果面板來源膠囊／補資料鈕 tap 自動補／燈箱 ⚙ 進階重刮），不再教不存在的手勢；移除 Settings 進階搜尋 toggle 相關文案 key（保留 metatube keyword hint）。
- **zh_CN／en／ja 文案 + 2 個 tooltip key（`search.auto_pill.tooltip`／`search.source_pill.tooltip`）milestone 同步**（owner 拍板多語系重複內容等 milestone）；其間非 zh_TW 用戶 help 暫留舊敘述（已知可接受）。README／README_EN 無長壓敘述，不動。

### Internal
- source-pill 抽 Jinja macro（`_macros/source_pill.html`）共用，三處（搜尋列／結果面板／換源預覽）覆用同一元件；新增 `.source-pill--flat` 唯讀變體 CSS（保留色彩 tint、關掉 pointer/hover/focus 互動）。
- picker「自動」cycle rewire（結果面板膠囊接 switchSource 循環）；rescrapePreview effective source 計算（auto→實際 `_source`）。
- 長壓退役連帶清除 `rescrapeEnabled()` / `window.__ADVANCED_SEARCH__.enabled` gate（齒輪 `x-show` 改常駐）、`'enrich'` entryPoint 文字殘留（純註解、無真死分支）；mergeState 鏈只移除 `longPressState` 一行、不改 spread（保 getter reactivity）。

### Non-Goals（明確不做）
- **不改後端搜尋路由**（Active Row 仍是唯一真理，本版只改入口可見性）、**不為 showcase 既有影片補「來源出處」DB 欄位**（換源預覽膠囊顯示的是「剛挑的源」非「原紀錄來源」）、**搜尋列膠囊不做持久黏著範圍**（不記憶、不 override 路由）、**不保留任何長壓加速鍵**、**不為 grid 卡新增進階重刮入口**（收斂到燈箱齒輪）、**US6 只退總開關**（逐源 enable/disable、Parts Bin、Active Row 排序全保留）、**不做一次性 coachmark**、**JavLibrary 進搜尋列（接 CF flow）列可選 follow-on、本版不含**。

### 測試
- 全套 pytest **4249 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- 新增測試：`TestMigrationAdvancedSearchEnabled`（config 欄位 strip migration 3 案）+ source-pill macro／搜尋列膠囊 state gate／結果面板膠囊／flat CSS／換源預覽膠囊／效力來源等前端守衛；退役 toggle/gate/長壓 helper-mechanics/demo 守衛（畢業退役多於新增，4258→4249）。
- **transient-guard**：本版多條「單向遷移後不回退」負向守衛（bootstrap 去 enabled / 長壓退役 / toggle 退役 / 齒輪去 gate 等）標記下個 milestone 評估移除。

## [0.10.0] - 2026-06-18

本版主軸：**來源穩定性 + 測試硬化**（feature/73，0.10 線首版）。不是新功能，是**可信度硬化**——讓你相信「來源還活著、parser 沒爛、我的 NFO 不會被默默寫壞」。兩個觸發點：外部 AI 審查回報「測試覆蓋率不足」（查證後確認帳面被 smoke skip 低估，但流程定型前的歷史真債確實存在，最高風險是會改寫用戶 NFO 卻零測試的 `nfo_updater`），以及用戶回報 Tokyo Hot 番號（`n0762`）永遠查不到。本版做了六件事：把 8 個來源用真實番號做成「健康金絲雀」smoke 套件（連不上只警告、改版才報紅）、修掉 Tokyo Hot 單字母番號被誤插 hyphen 的 bug、清償五項離線單元測試真債、立覆蓋率流程地板防老債再被遺忘、復活站方轉 SPA 後失效的 avsox 來源、並把舊 smoke 與金絲雀重疊的冗餘測試整併清掉。

### Added
#### 🐤 8 源真實番號健康金絲雀 smoke 套件 / Source canary smoke suite
- **新增 `tests/smoke/test_source_canary.py`**：對 8 個 fan-out 來源（有碼 javbus/jav321/javdb/dmm + 無碼 d2pass/heyzo/fc2/avsox）各用 3~5 個常青真實番號做真連線健康檢查。**三態判讀**：連不上/逾時/404/空結果 → **skip + 警告**（無碼片易下架、javdb 查多被 ban 都正常，不擋 PR）；拿到正常 HTTP 回應卻解析空 → **fail**（網站改版打死 parser，這才是要修的）；拿到 Video + 番號相符 + 核心欄位有料 → pass。**多番號 quorum**：同源 ≥1 番號 pass 即綠，全部「拿到回應卻解析空」才紅。
- **結構式斷言**：只驗「有 Video + number 相符 + title/cover 非空」算 parser 健康，不驗 maker/series/date 精確值（那些會隨站方資料微調誤報，精確值回歸交給離線 mock）。標 `@pytest.mark.smoke`、不進 CI、pre-merge / milestone 手動跑當金絲雀，失敗靠人工判讀「下架/被 ban（忽略）」還是「改版（修 parser）」。

#### 📊 覆蓋率流程地板（cov-floor）/ Coverage floor
- **新增 `scripts/run_cov.sh` + `.coveragerc`**：把「增量審計」的盲區補上「存量地板」——`pytest --cov=core --cov=web --cov-fail-under=84`（地板 84% = 實測 86% − 2pp 緩衝防 flaky）。效果：下次誰碰到老模組被強迫順手補測試，老債漸進清償。`web/*`（端點 I/O，integration 部分覆蓋）omit；`core/scrapers/utils.py` 刻意保留在地板內（大半是已測純邏輯）。CI 不強制此 fail-under（CI 維持只跑 pytest、不擋 PR）。

### Fixed
#### 🔧 Tokyo Hot 單字母無碼番號修復 / Tokyo Hot single-letter number fix
- **`[無碼]n0762 Tokyo Hot` 這類單字母前綴無碼番號不再查無**。根因：`n0762` 被正規化成 `n-0762`（多插一個 hyphen），送進 scraper 全部 404。查證發現問題不在無碼源，而在 hyphen 把查詢打死——Tokyo Hot 其實由 JavBus / JAV321 收錄（兩者都接 `N0762` 無 hyphen、都拒 `N-0762`），只是它們從沒收到合法查詢。修法（採「單字母 + 恰 4 位數字 → 不插 hyphen」窄規則，涵蓋 n/k/c/m/s 全系列，雙重約束天然排除所有有碼 collision）：`normalize_number` / `validate_number`（`base.py`）+ `extract_number`（`utils.py`，檔名也能抽出）三個 regex 觸點。**通用番號（`sone103` → `SONE-103`）完全不回歸**，不需新源/改路由（既有 JavBus/JAV321 即可）。

#### 🔧 avsox scraper 復活 / avsox scraper revival
- **avsox 來源恢復「給番號回得了料」**。站方已從 server-side render 轉純 client-side Vue SPA 且對 `requests` 回 403，舊 XPath scraper 只拿到空殼、任何番號都回 None（8 源裡唯一的通用無碼聚合站等於斷一條腿）。改打 SPA 背後的**兩段式 JSON API**（search → movie detail），number/title/cover（含 caribbean/1pondo/heyzo/Tokyo Hot 型）都回得了；既有單元測試改 JSON-mock + 真實 fixture，金絲雀 avsox 從紅轉綠。

### Changed
#### 🧪 測試技術債清償（五項離線單元測試）/ Offline unit-test debt repayment
- 全部 mock / fixture 驅動、不連網，補在流程定型前零測試或低覆蓋的程式上（按風險）：`core/nfo_updater.py`（**會改寫用戶 NFO 檔**的 add_actor / tags 去重 / user_tag 重寫 / 補欄分支，最高風險）、`core/translate_service.py`（_clean_output / batch 解析 + Gemini 四分支）、`core/scrapers/javdb.py`（fixture 離線測試 14%→68%）、`core/scrapers/jav321.py`（genre tags + else 分支 64%→72%）、`core/nfo_utils.py`（CDATA 區塊不被誤 sanitize 43%→100%）。離線 fixture 同趟由金絲雀 research sweep 順手抓存（既驗 live 番號又餵離線 mock）。

#### 🧹 source smoke 整併（consolidation）/ Source smoke consolidation
- 金絲雀上線後，對三個舊 source-smoke 檔（`test_scraper_live.py` / `test_scrapers.py` / `test_javbus_smoke.py`，33 測試）做 inventory，發現混用四種職責，分四桶各別處置（**整併而非裸刪、先有替代品才退役**）：桶 A 14 個 liveness **退役**（金絲雀 quorum 嚴格替代）；桶 B 欄位斷言**搬離線**（javdb tags + javbus JUR-688/SNOS-143 HTML fixture，deterministic、不受站方微調誤報）；桶 C 9 個金絲雀不覆蓋的獨特 live 路徑（fan-out / 女優 / smart_search 無碼路由 / keyword / 多語言 tags）收進新 `test_extra_paths_live.py`（slim live，連不上顯式 skip）；桶 D 9 個純邏輯測試**搬 `tests/unit/`**（原誤放 smoke 目錄、CI 看不見）。三舊檔覆蓋全有去處後刪除。

### Internal
- 金絲雀架構：純 decision-core（`_canary_core.py`，三態判讀邏輯不連網、可 deterministic 單元測試）+ probe（`_probe.py`，`_probe_reachable` 走各 scraper 既有 reachability）+ 番號清單（`_canary_numbers.py`）。
- 爬蟲 HTML/JSON fixture 落 `tests/fixtures/scrapers/`（`.gitattributes` `-whitespace` 豁免保 byte-faithful + `.gitignore` negation 放行 `*.html`）。
- Tokyo Hot 入口層守衛（`is_number_format` gate + `search_jav` 把 `N0762` 傳進 scraper）。

### Non-Goals（明確不做）
- **不把 `javlibrary` 納入 smoke**（CF 真人驗證 + 桌面專屬，無法自動化）、**不在 CI 跑真連線 smoke**（CI 維持只 pytest unit+integration、不連網）、**不做欄位級 live 回歸測試**（smoke 只結構式金絲雀；精確值回歸歸離線 mock）、**不為拉覆蓋率硬補** `app.py`/`config.py`/`gemini.py` 的連線 I/O 與頁面路由、**不重分類 metatube `TOKYO-HOT`**（用戶決議；雖確認誤歸有碼，與番號修復無關）、**不重寫 scraper 架構**（avsox 只讓它重新抓得到料）、**不建來源自動下架偵測/告警系統**（金絲雀失敗靠人工判讀）、**US6 不裸刪**（替代品存在前絕不刪原測試）。

### 測試
- 全套 pytest **4238 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.9.11 的 4089 +149）+ `npm run lint`（eslint + stylelint）綠。
- 覆蓋率地板：`core`+`web` **86.28% ≥ 84%**（`scripts/run_cov.sh`）。
- 來源金絲雀：**8 源全 PASS**（含 avsox 復活）。
- 新增測試：`test_source_canary` / `test_source_canary_logic`（三態 + quorum decision-core）/ `test_extract_number`（Tokyo Hot 單字母 + 截斷邊界）/ `test_scraper_parser`（normalize 路徑）/ `test_avsox_scraper`（改 JSON-mock + Tokyo Hot）/ `test_nfo_updater` / `test_translate_service` / `test_javdb_scraper` / `test_jav321_scraper` / `test_nfo_utils`（離線債）/ `test_scraper_smoke_pure_logic`（桶 D 搬遷）/ `test_javbus_scraper`（JUR-688/SNOS-143 fixture）/ `test_extra_paths_live`（桶 C slim live）。


## [0.9.11] - 2026-06-13

本版主軸：**外部媒體管理器相容模式（Jellyfin / Emby / Kodi）**（feature/72）。OpenAver 的 NFO 本來就是 Kodi/Jellyfin/Emby 共用的 XML schema，「基本相容」沒問題，但離「掛上去就正確顯示」還差一截——圖片命名偏好不同、多段影片（cd1/cd2）會被當成兩部片、NFO 少了幾個媒體庫排序/過濾用的欄位。本版在 Settings 新增「外部媒體管理器模式」**四態選擇器（預設｜Jellyfin｜Emby｜Kodi，每態各有一行說明）**：選任一外部模式後，刮削/整理會另存 `{番號}-poster.jpg`／`{番號}-fanart.jpg`、把 cd1/cd2/part1 等多段自動合併成一部片（第 2 段以後只跳 NFO、保留封面）、並補上 NFO 辨識欄位（番號 ID／排序／產地／語言）。掃描端也學會讀外部工具（MDCX/Javinizer）或 OpenAver 自己產生的 `{番號}-fanart/-poster.jpg`，直接接手已刮削的收藏庫。另含 issue #44 後續回報的兩個整理 pipeline 修復（B1 搬檔不再產生重複死卡、B2 已整理檔再整理標題不疊加）。

### Added
#### 🎬 外部媒體管理器相容模式 / External media-manager compatibility mode
- **F1 — 外部媒體管理器四態選擇器**：Settings 新增「外部媒體管理器模式」segmented 控件，四格「預設｜Jellyfin｜Emby｜Kodi」，每態旁邊一行說明（trailing hint，跟在選擇器同一橫列）清楚講「會產生什麼檔案」。選「預設」行為與現狀完全相同。
- **F2 — cd1/cd2 多段自動合併**：開外部模式後，偵測檔名多段 token（cd1/cd2、dvd1/dvd2、part1/part2、pt、disc）；第 1 段正常輸出 NFO + 封面，第 2 段以後**只跳過 NFO、保留封面**（媒體庫靠 NFO 認片數，只留第 1 段 NFO 就會收成「一部片、兩段」；多出的封面不破壞合併，OpenAver 自己的瀏覽頁仍逐段顯示各自封面）。多段 token 一律移到輸出檔名最尾端（夾在後綴中間會讓 Jellyfin 認不出來）。
- **F3 — NFO 補強欄位**：任一外部模式下，NFO 額外寫入 `<lockdata>`（best-effort，仍輸出但不保證生效）、`<uniqueid type="num" default="true">`（番號 ID，Jellyfin/Emby 偏好格式）、`<sorttitle>`（排序用）、`<country>Japan</country>`、`<language>ja</language>`（供媒體庫過濾）。這些欄位不影響 OpenAver 自身（OpenAver 讀資料庫、不讀 NFO）。
- **F5 — Scanner 識別外部封面**：掃描封面查找新增一層（同名圖之後、固定名稱之前），辨識 `{番號}-fanart.{ext}`（優先，橫版全圖供瀏覽顯示）與 `{番號}-poster.{ext}`（次之）。能讀回 OpenAver 自己在外部模式產生的封面，也能直接接手 MDCX/Javinizer 等工具已刮削的收藏庫。
- **F6 — Help 多版本手動指引**：Help 新增一段純文字教學，說明「同片多版本（流出/4K/中文）在 Emby/Jellyfin 合併成一筆 + 版本下拉」這件**整個生態圈都靠手動結構解決**的事該怎麼擺檔案，附可照抄的資料夾範例與兩個限制。
- **F7 — 「就地補資料 vs 整理歸檔」措辭換軸**：把 Settings/Help/新手教學描述兩條刮資料路徑的用詞，從暗示「新手用 Scanner、老手用 Search」的技能分層，改為「動不動你的檔案」的意圖區分——就地補資料（Scanner，不改名、適合唯讀網盤）vs 整理歸檔（Search，改名搬移建乾淨媒體庫）。
- **補圖入口擴及 Kodi**（72d）：掃描頁的「補齊外部封面」工具原本只在 Jellyfin/Emby 模式出現，現擴及 Kodi（Kodi 模式掃描本就產同樣的 sidecar 封面，卻拿不到補圖工具——補上既有缺口）。

### Changed
- **F4 — 文案修正**：Kodi 文案從裸 `poster.jpg` 改正為 `{番號}-poster.jpg`（72c 起 Kodi 也輸出 stem 長格式）。**保留 v0.9.7 對 Emby 的正確說明**：`{stem}-fanart.jpg` 僅 Jellyfin／Kodi 讀取，Emby 不認此 fanart 命名（海報與 NFO 在 Emby 正常）。
- **補圖流程文字中性化**（72d，mode-agnostic）：補圖按鈕/提示/通知/log 從寫死「Jellyfin 圖片」改為「外部媒體管理器圖片／封面」，三態（Jellyfin/Emby/Kodi）用戶看到的措辭一致（i18n value 中性化，key 名與端點 path 不變）。
- **Settings 外部管理器改四格 segmented**：由舊三態「關閉｜Jellyfin / Emby｜Kodi」拆成四格「預設｜Jellyfin｜Emby｜Kodi」，記住用戶選的是 Jellyfin 還是 Emby（重整頁面高亮正確）。
- **封面縮圖快取改「新安裝預設開啟」**：縮圖快取（v0.9.10 推出時預設關閉）改為**新安裝預設開啟**，比照進階搜尋畢業模式——既有用戶更新後**維持關閉**（migration 對缺 key 的舊 config 寫 `false`，不驚動老用戶），新用戶開箱即享一頁刷封面。新裝因預設即開、不觸發磁碟空間確認 modal（空庫無衝擊）。

### Fixed
#### 🔧 整理 pipeline 附帶修復（issue #44 後續，feature/72-T-c1/T-c2）/ Organize-pipeline drive-by fixes
- **B1 — 整理搬檔時 DB 跟著搬，消除重複死卡**：先用列表生成（Scanner）原地索引一批片、之後又在搜尋頁對其中某片「整理」（改名搬移）時，舊路徑那筆會變成孤兒死卡，同一片在瀏覽出現兩張（其中一張封面壞掉）。現在整理搬檔會把 DB 那筆原地跟著搬到新路徑（保留入庫時間、瀏覽排序位置、以及你在瀏覽頁加的標籤），整理完當下就只剩一張正確的卡、不必等下次重掃。**任何外部媒體管理器模式皆修，與模式無關。**
- **B2 — 已整理過的檔再整理一次，標題不再疊加**：對 OpenAver 自己整理出來的成品檔（檔名已是 `[番號][廠商] 標題-後綴` 格式）再整理一次，過去會把整段已格式化檔名誤當「標題」塞回去，越疊越長（番號/廠商/後綴重複）。現在會辨識「這是已整理過的成品」而改用刮削/翻譯標題，並把標題開頭多餘的番號前綴剝乾淨（連舊版本已寫進磁碟/資料庫的雙重前綴也一併修好）；真正的原始下載檔名行為不變，中文標題搶救照舊。
- **cd2/part2 整理後 Showcase DB metadata 遺失**：F2 外部模式跳過 cd2 NFO 後，DB 索引改走檔名 parse → actors/tags/date/maker 掉光；B1 repath 還會用此殘缺 row 覆蓋 Scanner 已索引好的紀錄。現整理時把手上的 scraped metadata 直接傳入 upsert，cd2 row 與 cd1 一致；非多段路徑 byte-identical。

#### 🔧 外部管理器相容修正 / External-manager compat fixes
- **補圖 gate 改正向白名單、fail-closed**（72d Codex P2）：掃描頁補圖入口的開關由「不是 jellyfin_emby 就不出現」改為「是 off 才不出現」（正向白名單），新增的 Kodi/Emby 模式正確觸發、未知值安全地不觸發。
- **Kodi sidecar 一律 stem 長格式**（72b Codex P1）：Kodi 模式的封面從裸 `poster.jpg`/`fanart.jpg` 改為與 Jellyfin/Emby 相同的 `{stem}-poster.jpg`/`{stem}-fanart.jpg`，避免同資料夾多部片時裸命名互相覆蓋（多片碰撞）。
- **外部模式單片 refresh 被誤 400**（72d Codex P2-A）：切換外部管理器模式後對單片做「補資料」（refresh_full），400 守衛僅看 `.nfo`/`.jpg` 是否存在、未考慮外部圖補寫機會 → 想補 `{stem}-poster/-fanart` 的 refresh 被拒。加第三條 `will_write_external` 條件（external≠off + 底圖在 + stem 圖缺），off 模式 byte-identical。
- **Enrich 不認 MDCX/Javinizer 匯入的 `{stem}-poster/-fanart.jpg`**（72d Codex P2-B）：F5 讓 Scanner 能讀外部工具的 stem 圖，但 enrich 的 cover-gate 仍要求 `{stem}.jpg` 存在才動作 → MDCX/Javinizer 匯入夾（只有 `-poster/-fanart`、無裸底圖）enrich 後 NFO 指向不存在的 `{stem}.jpg`。改為先判 `_STEM_IMAGE_MODES`：底圖缺但 stem 圖已在磁碟且 `overwrite=false` → 直接認可現況、不重生；off 模式行為不變。

#### 🔧 封面代理白名單跨格式誤殺 SMB 連線磁碟機（TASK-73）/ Image-proxy whitelist cross-format false-positive
- **把 NAS 掛成「連線網路磁碟機」（`K:\` → `\\server\share`）或用 DFS／別名 UNC 的 Windows 用戶，Showcase 封面牆整片空白（影片仍正常播）的修復**。根因：封面代理 `get_image`／`get_video` 的目錄白名單比對只對「請求路徑」跑 `realpath`、沒對「config 白名單目錄」跑，而 `realpath` 會**跨格式改寫**（mapped drive→UNC、DFS／別名→真實 target）→ 兩端字串格式不同，casefold＋NFC 跨不過去 → 合法封面被當白名單外路徑 403 擋掉。現改為兩端對稱正規化（請求端 single-form；config 目錄端 dual-form：normpath＋realpath 兩候選，cache-on-success-only），任一掛載格式都對得上；既有 symlink-escape／`..` 穿越防護完整保留不破。**影片本來就走 PyWebView 直開、不受影響。**

### Internal
- **external_manager 升真四態 config**（`Literal["off","jellyfin","emby","kodi"]`）+ migration（既有存檔 `jellyfin_emby` → load 時就地改寫為 `jellyfin`，idempotent）；圖片命名分支抽共用常數 `_STEM_IMAGE_MODES = ('jellyfin','emby','kodi')`（organizer/enricher 共用，避免 drift）。`!= 'off'` 的 F3 NFO / 多段偵測分支原樣涵蓋三個非 off 值、不動。
- **多段 token 偵測** `_detect_multipart_token` / `_strip_part_token`（cd/dvd/part/pt/disc 系列，token 必落輸出檔名尾端）。
- 補圖 check/generate 後端本就 generic（只認兩 sidecar、零 Jellyfin 特有邏輯），gate 擴三態後零後端改動；`jellyfin_check` capability 描述/data 文字隨補圖中性化（端點 path 與 schema 不變、contract no-op）。

### Non-Goals（明確不做）
- **不支援 Plex**（雖 Plex 1.43.1+ 已有原生 NFO Agent，但 Plex 整合不在本版定位，Settings 不加 Plex）、**不做多版本自動合併**（整個 JAV 生態圈都靠手動結構解決，本版改文檔化手動指引 F6）、**不做 `.actors/` 演員縮圖資料夾**（Kodi-specific、無法共用）、**不做獨立輸出目錄（decoupled output）**（架構改動大、屬獨立 feature）、**不做 NFO 演員名翻譯**（日文名在 Jellyfin/Emby 顯示無問題）、**不讓 Scanner 改名**（維持唯讀原地索引定位，可安全掃唯讀網盤）、**不把版本後綴寫成 tag**、**不做 Scanner 批次整理/一鍵歸檔**（屬未來獨立 feature，本版只先把 F7 措辭換軸做好）。

### i18n
- zh_TW 文案本版交付（settings 外部管理器 hint + 補圖中性化 + Help 四模式措辭）；**milestone 已同步 zh_CN／en／ja**（external_manager 六 key + `skipped_nfo_multipart` toast + ja／zh_CN 多版本 Help + 回補 v0.9.10 漏網 19 key）。
- **Scanner 離頁警告 i18n 化**：3 條硬編碼繁中離頁警告（生成中／圖片檢查中／未存資料夾變更）改走 `window.t()` + 新增 `scanner.leave_warning` 四語系 key——非 zh_TW 用戶離頁提示不再顯示繁中（清 72d Codex P2 deferred 的 pre-existing i18n 債）。
- **Emby fanart 相容文案修正**：撤回 v0.9.11 早期「Emby 同樣支援 `{stem}-fanart.jpg`」的誤述，回復 v0.9.7 的正確說明（Emby 不認此 fanart 背景圖命名，僅 Jellyfin／Kodi 讀取；Emby 的海報與 NFO 正常）；zh_TW／README／README_EN 一併更正。

### 測試
- 全套 pytest **4089 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。
- 新增測試：`test_db_inflow`（B1 整理搬檔 DB repath）/ `test_organizer_multipart`（F2 多段 token 偵測 + 尾端）/ `test_organizer_title`（B2 已整理檔不疊加標題）/ `test_enricher`（enrich 路徑外部模式）/ `test_generate_nfo`（F3 補強欄位）/ `test_jellyfin_compat`（smoke harness，CI 排除）+ 前端守衛（settings 四態 segmented / 補圖 gate 三態化 / Kodi stem）。
- 新增測試（TASK-73 封面代理白名單）：`TestMappedDriveWhitelist`（SMB mapped-drive image/video → 200、DFS 別名 UNC → 200、間歇斷線 dual-form → 200、對稱契約守衛）；既有 symlink-escape／`..` 穿越／WinFsp normpath fallback 安全測試保持綠。
- **transient-guard**：`test_frontend_lint` 中針對舊 `jellyfin_emby` 字面 / `!= 'off'` 的 negative-fingerprint 斷言標 `[transient-guard]`（四態遷移一次性，下個 milestone 評估移除）。

## [0.9.10] - 2026-06-12

本版主軸：**本地 WebP 縮圖快取（opt-in）+ 燈箱單筆刪除**（feature/71）。部署主場景是 app 跑在 PC(SSD)、影片/圖片放在區網 Synology NAS(HDD)，封面牆一頁 90 張每張都直接打 NAS 原圖、HDD 隨機 seek + idle 喚醒 → 一張張慢慢冒。本版讓你在 Settings 手動開啟「封面縮圖快取」後，在本機把封面預先壓成集中極小的 WebP（每張約 32KB），瀏覽時從 SSD（或 OS page cache）出圖、**根本不碰 NAS**；燈箱點進去採 blur-up（小圖秒出 → 原圖載入後就地變清）。**來源真理仍在 NAS**（原圖／NFO 不動），本地只放可回收的衍生快取。另含 issue #57 的燈箱單筆刪除（只移除 DB 紀錄＋它的快取縮圖，**絕不刪你的影片檔或原始封面**），以及進階搜尋畢業移除 Beta 標記。

### Added
#### 🖼️ 本地 WebP 縮圖快取（opt-in，預設關閉）/ Local WebP thumbnail cache
- **Settings「下載劇照」同層級新增「封面縮圖快取」開關**：手動開啟；開啟前依目前片數即時估算空間（每張 ~32KB × 片數）＋ HDD 首次生成時間估算，跳確認 modal 才開始。關閉時行為與現狀完全一致（直接出原圖、不產 WebP）。
- **首次開啟背景全量生成**：開啟後在背景把整庫封面慢慢全部壓成 WebP（一次性、不卡 UI、期間可繼續用）；完成後瀏覽全程零等待。
- **Showcase grid 封面 + 相似探索節點縮圖改用本地 WebP**：一次刷一整頁而非一張張慢慢冒；serve 已存在的 WebP 時**完全不觸發任何 NAS 原圖 stat／read**（NAS 斷線仍能出已快取縮圖）。
- **燈箱 blur-up（模糊變清晰）**：大圖框先放大已快取的小 WebP（秒出、略糊）→ 原始大圖背景載入完成後就地淡入變清。
- **持續跟上新片**：凡影片進 DB（掃描／enrich／重刮）自動生成／更新該片縮圖；漏網的 lazy on-miss 即時補；封面被重刮／enrich 換新後，對應 WebP 就地以新封面重生（不顯示舊圖）。
- **WebP 放 `output/thumb/`**（DB 同層）扁平 hash 分桶、400px 寬 q80、零新依賴（用既有 Pillow）、零 ZIP 體積影響。

#### 🗑️ 燈箱單筆刪除（issue #57）/ Per-item lightbox delete
- **燈箱 metadata 行末新增常駐 muted 垃圾桶 icon**：點擊跳破壞性確認 modal，誠實說明「只從資料庫移除這筆紀錄，影片檔保留在磁碟、不會被刪除；若仍在掃描目錄內，下次掃描會重新被加回」。
- **確認後**：DB 該筆消失 + 它的快取 WebP 一併刪、grid 即時移除那張卡（Alpine splice，無整頁重載）、成功 toast。**磁碟上的影片檔與原始封面圖完全不動**；此刪除能力不揭露給 AI（human-only）。

### Changed
- **進階搜尋畢業、移除 Beta 標記**：自 v0.9.0 推出、歷經多版打磨並於 v0.9.8 起預設開啟，已長期穩定 → Settings quick-toggle 與 Help 文案的「Beta」標記移除（JavLibrary 的 BETA 不受影響，它仍是 beta）。
- **「清除所有影片快取」連動清縮圖**：清空 DB videos 表時連同清整個 `output/thumb/`；移除加入資料夾→其影片被掃描 prune 出 DB 時順手刪它們的 WebP（不留孤兒）。

### Fixed
- **關閉縮圖快取 → 確認 modal → 一律清除**：關閉 toggle 彈確認 modal，確認後**先存檔成功才**清空 `output/thumb/`（新增 DB-safe `POST /api/gallery/thumb/clear`，僅 rmtree、絕不碰 videos DB）；取消則維持啟用、快取保留。
- **prewarm／disable race 硬化**：背景預熱進行中若用戶關閉並清除快取，worker 每筆重讀設定→立即停止，不再把剛清掉的目錄重建回來；被中止時也不送誤導的「完成 N 張」通知（涵蓋 generate 成功與失敗兩種收尾）。
- **燈箱開關 flip「兩張圖重影」**：blur-up 引入的原圖 overlay 層在 grid↔燈箱飛行期間未被隱藏 → 與飛行 ghost 重疊成重影；改為飛行期隱藏整個封面容器（一次蓋住底圖＋原圖兩層）、OPEN/CLOSE 對稱還原。
- **刪除確認 modal 被燈箱蓋住**：root-fix `.fluent-modal` z-index 拉高至燈箱之上（removeActress 確認框同步受惠）。
- **重刮／Enrich 後縮圖快取不更新（舊封面殘留）**：enrich 路徑對已是 `file:///` URI 的路徑重複 encode → invalidate 刪錯 hash → 舊縮圖沒刪掉，換封面後瀏覽頁持續顯示舊封面直到手動清快取。改用冪等的 `coerce_to_file_uri`，與 canonical key 一致。
- **縮圖 serve 兩處邊界修正**：(1) 檔名含字面 `%` 的影片縮圖 404（`unquote` 二次解碼路徑）；(2) 關閉並清除快取後，舊分頁的 `/thumb` 請求仍重建 WebP（miss 路徑未 gate `thumbnail_cache_enabled`）——「關閉並清除」後現確實不再重生。
- **燈箱封面縮水 + 切換跳動 + 進星座模式後反覆縮小**：blur-up 引入的 thumb 在燈箱以 400px 原始尺寸渲染（未放大）→ 封面縮水、flip ghost 量到錯誤矩形而跳動；另星座模式退出（slip-through）路徑缺 `cover_full_url` → `@load` 永不觸發 → 多次進出累積縮小。補 similar API `cover_full_url` 欄位 + CSS `height:60vh`；slip-through 路徑亦補 blur-up 狀態 reset（抽 `_refreshLbFullBlurUp` helper，兩入口共用）。

### Internal
- 縮圖核心模組 `core/thumbnail_cache.py`（hash 命名 / 原子寫 temp+os.replace / generate 失敗 fallback 原圖 / invalidate / clear_all）、`thumbnail_cache_enabled` config plumbing、serve 端點 + lazy 生成 + prewarm 端點、showcase/similar serializer 切 thumb url、失效掛鉤（掃描/enrich/重刮/單筆刪除/清快取）+ serve race 硬化、多輪 Codex review（並發正確性 / prewarm-clear race / disable-skip-done / generate-fail edge，皆 RED→GREEN 實證）。

### Non-Goals（明確不做）
- 不與 Jellyfin/Emby 共用縮圖（hash-keyed 私有 WebP，與既有 `generate_jellyfin_images()` 正交）、不偵測「手動偷換磁碟封面」（失效走事件驅動，重掃/清快取即可）、不鏡像加入資料夾目錄結構（扁平 hash 分桶）、不刪任何磁碟檔（只動 DB row + 衍生 WebP）、不做「刪除後永久不再加回」的 tombstone、不改 Search 頁封面來源、不導 virtual scroll / HTTP2。

### 測試
- 全套 pytest **3845 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。
- 新增：`test_thumbnail_cache`（核心模組）/ `test_api_thumb`（serve / prewarm / clear / prewarm-clear race 5 案）+ async-offload 正斷言（get_thumb / thumb_prewarm / thumb_clear / delete_video 皆 def）+ 前端守衛（縮圖開關 / blur-up / 單筆刪除 element-bound / disable modal / ghost-fly both-restore / z-index contract）。
- **transient-guard**：71b-T1 燈箱刪除鈕位置守衛 `test_t7_delete_trash_button_in_lightbox_details_row` 標 `[transient-guard]`（搬位 relayout 一次性，下個 milestone 評估移除）。

## [0.9.9] - 2026-06-11

本版單一主軸：**新增 JavLibrary 來源（BETA，桌面專屬）**（feature/70）。JavLibrary 是社群索引站，metatube 聯邦 30+ 來源都沒收錄——它擁有別處拿不到的最豐富社群標籤、用戶評分、以及冷門/長尾番號。但全站受 Cloudflare 人機驗證保護、純自動抓一律失敗。OpenAver 的解法：借桌面版 PyWebView 彈出真實瀏覽器視窗，讓你手動點一次驗證，之後在「已過驗證的分頁」裡抓取。因此 JavLibrary **只在桌面 standalone 可用**、**只能在進階搜尋／重刮來源選單以精確番號查詢**、並標示 BETA。

### Added
#### 🆕 JavLibrary 來源（BETA）/ JavLibrary source (BETA)
- **進階搜尋／重刮來源選單新增 JavLibrary（BETA 徽章）**：最豐富社群標籤、用戶評分、冷門番號；metatube 聯邦沒收錄的長尾片在這裡找得到。
- **Cloudflare 驗證流程**：有效期間內透明直接出結果；首次或過期自動彈出 JavLibrary 視窗，你點一下人機驗證（＋ 18 歲同意），系統自動重試並回填結果；驗證未完成或逾時會明確通知——不假裝成功、不靜默換來源。
- **僅桌面 standalone 可用**：dev / 伺服器模式下 JavLibrary 選項灰色不可點，附帶說明；不會出現在 AI 能力清單（`is_beta + manual_only` 雙重排除）。
- **永不進自動搜尋池**：不佔來源順序上限、不參與路由選擇、不影響其他來源行為。

### Internal
- 平台無關 CF transport DI 接縫（`core/cf_transport.py` Protocol）＋ PyWebView 實作（`windows/cf_transport_impl.py`）＋ 來源註冊（`utils/source_config`、scraper、config migration）＋ picker BETA 視覺 / 非桌面 gate ＋ `/api/cf/status`、`/api/cf/abandon` 端點 ＋ 前端 poll 協調（後端無狀態，try-fetch-first）。
- **`_wv_fetch` auto-retry（12s×3）**：同一 session 其他番號 1 秒就回、特定番號卡滿 40 秒才 timeout（隱藏視窗 mid-fetch 導航、JS callback 永不觸發）；縮短單次 timeout 至 12 秒、最多 3 次重試、每次使用獨立 queue + callback（舊 attempt 的遲發 callback 落進已廢棄的 queue，不汙染下一次）；修復 START-492 等間歇性「無結果」。
- 三輪 AI review（Codex ＋ Opus）修正：age-gate 偵測收窄為 `agreeBtn`（避免正常頁 footer 誤判）、search 入口防 500（結構化回應 ＋ 隱藏 JL pill）、`begin_solve` 例外防護、單一命中 `detail_url` 留空、番號核對守衛防回錯片。
- **70c hardening pass**（TASK-70c-B，第二輪 Opus review）：
  - **殭屍行程修正（B1，P1）**：`_on_main_closing` 設 `quitting=True` 後加 `jl_win.destroy()`——pywebview 只在 `instances==0` 才 `_shutdown()`，隱藏的 JL 視窗若未銷毀，關閉主視窗後 process 持續佔 port；此修正啟用了原本的 quitting-guard（舊 dead code）。
  - **關窗攔截（T70c-A，close-intercept）**：`_on_jl_closing` 回 `False` 取消關閉 → 用戶按 ✕ 只隱藏，transport 物件存活、免重啟（Layer 1 root-fix）；`_on_main_closing` quitting=True guard 讓 app 退出時正常放行。
  - **spinner CSS（B2，P2-1）**：`rescrape-cf-waiting` 底下 `.pill-spin` 缺 ancestor-scoped 規則 → 渲染空白；補 `.rescrape-cf-waiting .pill-spin` + 容器 flex layout（token-based，複用 `source-pill-spin` keyframes）。
  - **通知 i18n（B3，P3-2）**：`/api/cf/abandon` 的 `emit_notification` `message=` 硬編碼中文 → EN/JA 看到中文；`title_key = notif.jl_cf_timeout` 四語系均已有翻譯，直接移除 `message=`，toast 僅顯示 title（i18n-compliant，零架構改動）。
  - **守衛強化（P3-1）**：`cf_needed` 位置守衛由 `js.index("cf_needed")`（命中第 185 行註解）改錨 `data.cf_needed`（實際消費表達式）；`TestRescrapeModalSearchHideJlPillGuard` 改錨完整 `x-show` 表達式（L49），防止留空殼字串騙過守衛。
  - **B1 AST 守衛**：`test_standalone_init_order_guard.py` 新增 `test_on_main_closing_destroys_jl_win` 鎖定 `jl_win.destroy()` 呼叫（AST，防靜默回退）。

### Fixed
#### 🔧 JavLibrary CF flow 修通（70d）/ CF re-verify flow fixed
- **40 分鐘後重新驗證從「永久壞、要重開程式」變「打一次勾自動完成」**：clearance 過期後，舊流程把隱藏視窗導到首頁（那裡沒有 CF 可解），又因 `evaluate_js` 在 CF 頁卡 20 秒拖垮整個 JS 橋接 → JavLibrary 從此壞掉、必須重啟。現在彈窗直接帶你到「剛被擋下的搜尋頁」，你點一次人機驗證（或它自己過），視窗約 9 秒自動關閉、結果自動回填——全程不必碰 18 歲同意鈕、不必點頁面任何內容。
- 18+ 同意閘改用 `over18=18` cookie（站台真值；舊 `over18=1` 不被接受、遮罩不消）；此為視覺正確性，不影響資料抓取（mask 是 client-side overlay，從不擋 fetch/parse）。
- **CF 驗證等待提示語氣修正**：等待文案從「請點一下人機驗證」改為「驗證中，通過後自動繼續」（四語系）——CF 常自動過關、多數情況不需主動點，提示語氣改為陳述、避免誤導用戶一定要操作。

### Non-Goals（明確不做）
- 不支援 server / NAS / Docker（CF 需真人 ＋ 真瀏覽器 ＋ 桌面 GUI）、不做自動繞過 CF、不做模糊／演員搜尋、Transport A（cookie→curl_cffi）結構性死路不實作。

- **`fetch()` 主動設 `over18` cookie（Codex P2）**：`fetch()` 在呼叫 `_wv_fetch` 前先主動設 `over18=18` cookie，冷啟動 CF 自動過關後首次 fetch 不會收到 18+ 同意閘 → 不再靜默「無結果」。備用路徑：若 cookie 仍未抑制閘門（race/agreeBtn），改拋 `CfChallengeRequired` 路入 solve/poll 流程，而非回傳空殼 HTML。*`fetch()` now sets the `over18` cookie proactively so the 18+ age gate never returns as empty "no results" (Codex P2); persistent-gate fallback routes into the solve flow.*

### 測試
- 全套 pytest **3743 passed, 2 skipped**（unit ＋ integration，排除 smoke / e2e）＋ `npm run lint`（eslint ＋ stylelint）綠。
- 新增測試：`test_cf_transport` / `test_javlibrary_parser` / `test_javlibrary_scraper` / `test_javlibrary_contracts` / `test_cf_transport_impl` / `test_javlibrary_cf_flow` / `test_api_cf_endpoints` ＋ 前端守衛（`TestJavlibraryPickerT5Guard` / `T6Guard` / `SearchHideJlPillGuard`）＋ 70c-B 強化守衛（`test_on_main_closing_destroys_jl_win` ＋ 強化 cf_needed / x-show 守衛）＋ `_wv_fetch` retry 守衛（`test_retry_then_succeed` / `test_all_attempts_exhausted_raises_timeout` / `test_stale_callback_isolation`）＋ over18 cookie / age-gate fallback 守衛（`test_age_gate_html_raises_cf_challenge_required` / `test_fetch_sets_over18_cookie_before_fetch`）。

## [0.9.8] - 2026-06-06

本版單一主軸：**dim（暗色）主題色彩編碼修復**（feature/69），純前端 CSS、零後端、零依賴、零 i18n、零 ZIP 影響。問題：切到 dim 主題時大量「靠顏色區分狀態」的 UI 變得無法分辨——有碼 vs 無碼來源膠囊長一樣、metatube 連沒連看不出、segmented 選中態消失、警告 banner 跟一般容器混同。根因兩 factor 疊加：(A) 狀態用 `color-mix(語義色 ≤15%, transparent/surface)` 當背景 tint，dim surface 近黑（oklch 26–31%）把低% 色調吃光；(B) dim 沒 override `--color-primary` → 有碼膠囊掉回 DaisyUI 萊姆綠（139°），與無碼 success 綠（166°）只差 27° → 都綠。修復後每個色彩編碼狀態在 dim 下都能一眼辨識，且 light 主題完全不回歸。

### Fixed
#### 🎨 dim 主題色彩編碼 / dim color encoding
- **token patch（根 unlock）**：`theme.css` 的 `[data-theme="dim"]` 區補 `--color-primary`（`oklch(0.66 0.04 250)`，與 light 同 250° 冷色家族、調亮供暗底對比、遠離綠相 → 根除膠囊色相碰撞）+ `--color-warning`（`#ff9f0a` Apple dark-mode amber）。cascade 自動改善所有引用這兩 token 的 dim border/文字通道。
- **來源膠囊**（跨 Settings 掃描來源 / Search / 進階重刮三入口共用）：dim 下有碼（primary 冷藍）vs 無碼（success 綠）一眼可辨；啟用態 tint + solid 色邊；Parts Bin 不可達 warning 色邊；載入 spinner 對比提升。
- **Settings**：segmented 選中態（亮面 + 1.5px inset accent 環，純結構信號）、suffix-tag（改 oklch + accent 邊）、metatube 已連線 status banner（綠 tint + 3px 左色條）、來源上限/全停用警告 banner、tier-hint / focus 環。
- **散點**：進階重刮彈窗 inline-error / 取消鈕 / 數字輸入 focus、showcase 取樣鈕、女優別名 primary 膠囊。
- **color-mix 色相插值修正**（CDP 終驗發現）：tint/border 的 `color-mix` partner 一律用 `transparent`（同 base 慣例）——dim surface 帶藍色相（264°），oklch 與暖色 mix 會沿色相環插值變調（amber→紫）；`transparent` 無色相 → 精準保留語義色。

### Changed
- **進階搜尋 picker 預設改為開啟**：`advanced_search_enabled` 預設值 `false` → `true`（三源對齊：`config.default.json` seed / `AppConfig` Pydantic default / `state-config.js` Alpine 初值）。新用戶／恢復原廠即可在掃描來源頁直接挑單一來源重刮，不需先進設定頁手動開啟；「下載劇照」維持預設關閉（兩者正交）。現有用戶 config.json 既有值不被覆蓋（migration 設計，保留既有偏好）。
- **design-system**：補進階重刮彈窗 + metatube 連線 banner 兩 demo（dim 驗證面）；膠囊 999px 白名單標題「5 類」→「7 類」+ 補類 6（source-pill）/ 類 7（segmented）交叉引用卡；過時 notification center 註解修正。修掉新增 demo 引入的 duplicate `id="settings-components"`（Codex P3）。

### Non-Goals（明確不做）
- 不改 light 主題行為、不換主題 / 不調 surface 明度、不新增第二套狀態色（一律走命名 token）、不碰 design-system 完整 dedupe（→ feature/70）。

### 測試
- CDP 雙主題實機終驗（design-system demo + 生產 /settings 掃描來源頁）：dim 各色彩編碼狀態可辨（amber 67° / 膠囊 blue 250° vs green 147°）、light computed 全 base 值零回歸。
- 全套 pytest 綠（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠；無 pytest 守衛（CLAUDE.md lint-guard：CSS 字串守衛歸 stylelint）。

## [0.9.7] - 2026-06-06

本版主軸：**VR 投影標籤保留 + 自動 VR tag**（feature/68），純後端、單檔 `core/organizer.py`、零新依賴、零 ZIP 影響、零 i18n、零 UI。問題根因：頭顯 App（DeoVR / HereSphere / Skybox / Pigasus）100% 靠「**檔名 token**」判斷 VR 投影/立體格式（`_180_LR` / `_3dh` / `mkx200`…），不讀 NFO；而 OpenAver 改名是用模板從頭重組檔名，原檔名的 VR token **不會被帶過來** → 改名後 VR 檔在頭顯 App 變成平面 2D 播放。本版讓改名時偵測原檔名的 VR token 並**原樣保留**到輸出檔名尾端，同時在 NFO 加一個 `VR` tag/genre。**無 toggle、無需用戶輸入；檔名無 VR token 時輸出 byte 級零變化**（2D 轉檔 / 一般片完全不受影響）。同梱兩處先前的小修正：`/static` no-cache 根治 stale cache、「Jellyfin / Emby 圖片模式」正名。

### Added
#### 🥽 VR 投影標籤保留 + 自動 VR tag / VR projection tag preservation
- **檔名 VR token 偵測 + 原樣保留**：改名時偵測原檔名的 VR 投影/立體 token（投影 `180`/`360`/`180x180`/`EAC360`、鏡頭 `MKX200`/`VRCA220`/`FISHEYE`、立體 `3DH`/`SBS`/`LR`/`TB`…），把「首個~末個 VR token 的 raw 子字串」原樣（不正規化、不砍、保大小寫）接到輸出檔名尾端。sidecar（poster/fanart/NFO）跟隨同 stem 命名不破。
- **自動 VR tag**：偵測到 VR token 的影片，NFO 加 `<tag>VR</tag>` + `<genre>VR</genre>`（固定英文，技術標籤不 i18n），供 Emby/Jellyfin 過濾分類。
- **高精準偵測（零誤判導向）**：唯一字串 token（`MKX200`/`180x180`/`3DH`…，無真番號長這樣）單獨成立；高誤判 token（裸 `180`/`360`/`LR`/`SBS`…）須**同一連續 cluster 內共現**才算數——孤立的 `MIRD-180`/`REBD-360`/`title_LR` 等真番號 → 不算 VR、檔名零變化。

### Changed
- **「Jellyfin 圖片模式」→「Jellyfin / Emby 圖片模式」**：label 與 hint 文案修正（`settings.scraper.jellyfin_mode_{label,hint}`，4 語系 zh_TW/zh_CN/en/ja）+ README / README_EN feature 條目。澄清相容性事實——`{stem}-poster.jpg` 與 Kodi-style NFO 兩者 Emby 與 Jellyfin 皆可讀（親核 Emby 官方 `Movie-Naming.md` 確認支援 `{name}-poster.ext`），`{stem}-fanart.jpg` 僅 Jellyfin 讀取（Emby backdrop/fanart 不支援 `{name}-` 前綴命名，只認 standalone `fanart.jpg`）。**刻意不**額外產生 standalone `fanart.jpg`：用戶若關閉資料夾模式（多片同目錄）會撞檔。配置欄位 `jellyfin_mode` 維持不變、無 migration、無行為變化。

### Fixed
- **`/static` heuristic stale cache**：以 `NoCacheStaticFiles(StaticFiles)` 子類替換 `web/app.py:75` 的原生 `StaticFiles` mount。override `file_response`，在 `super().file_response()` 回傳後對已建好的 response 物件做 post-construction headers mutation（`response.headers["Cache-Control"] = "no-cache"`），200 `FileResponse` 與 304 `NotModifiedResponse` 兩條路徑均有效。ETag / Last-Modified / 304 機制完整保留（同檔案未變回 304 空 body，有變才回 200 新版，免 hard-reload）。封面圖代理的 24h 強快取（`scanner.py get_image`）與影片 Range streaming 完全不受影響（不經此 mount）。
  - **桌面端（PyWebView）零副作用**：`webview.start()` 預設 `private_mode=True, storage_path=None`（pywebview ≥ 6.0 的 `start()` 參數，非 `create_window()` 參數）→ 非持久 WebView2 profile，每次啟動空快取；`no-cache` 對它只是 in-session localhost 多一次可忽略的重驗（< 1ms）。
  - **真正受益者**：`feature/epic-synology.md` 的 Server / NAS(.spk) / Docker 模式——client 端持久瀏覽器快取在 server 更新（換檔 + 重啟）後本不清除，此修正確保下次載入必重驗並取到新版。

### Internal
- **VR 偵測「先切 token 再分類 + 連續 run 共現」演算法**（`_detect_vr_cluster`）：切詞法天然繞掉 monolithic regex 的 `_LR` 底線邊界 bug；共現限定在連續 VR-token run 內（中間夾 non-VR token 即斷開），避免散落 token 跨任意文字誤共現。截斷保護新建獨立 budget path（VR cluster 不被 `max_filename_length` 切掉）；NFO VR tag 對 `<tag>`/`<genre>` 各做 case-insensitive 去重（scraper 已給 VR 不重複）。VR token 全程不進任何 strip 路徑（與「中字」偵測後移除標記相反），並剝除 extracted_title 尾端殘留以免與尾端保留雙寫。

### Non-Goals（明確不做）
- 不做 toggle / 用戶自訂 token 清單（自動偵測）、不做 token 正規化（降低相容性）、不保留解析度/裝置 token（`8K`/`60fps`/`samsung`）、不碰影片轉碼、不做 VR poster 不裁切（issue #6 獨立）、不串接 Emby/DeoVR/DLNA（用戶端的事）。enricher / nfo_updater 不改名路徑不在範圍（VR 偵測是 organize_file 職責）。

### 測試
- 新增 `tests/unit/test_organizer.py` VR 測試（5 class、46+ case）：偵測層全 DoD 表（命中/None/混大小寫/bracket-paren/誤判防護 `1080`/`color`/`SIVR-999`）+ 檔名組裝（suffix×VR 順序 / 超長截斷保護 / 零變化）+ NFO 去重（scraper VR 不重複 / has_vr 兩條分切 / 中字共存 / byte-identical）+ 端到端 wiring + Codex 兩輪 review 回歸（連續 run / 雙寫 / bracket 雙寫 / 多 confirmed run）。
- 新增 `tests/integration/test_static_cache_headers.py`：兩條契約測試（200 帶 `cache-control: no-cache` + `etag`；304 仍帶 `cache-control: no-cache`）。
- 全套 pytest **3588 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。

## [0.9.6] - 2026-06-06

本版單一主軸：**封面載入體感優化（Cover Loading UX）+ Showcase Console 清零**，純前端、零後端、零新依賴。兩條正交軌。**Track A**：封面在 NAS(HDD) 上一頁 90 張陸續慢慢冒，過去圖沒到是空白、到了「啪」一下出現；本版讓每張 grid 卡片與 Hero card 在等待時顯示 skeleton/shimmer、圖到淡入、抓不到顯示業界標準破圖 icon——把 HDD 喚醒/seek 的等待填上「正在載入」的視覺。**不縮短實際載入**（那是縮圖快取的事），只解「等待時看到什麼」。**Track B**：清掉 `/showcase` 開 F12 固定噴的 4 條 console 紅字——SVG namespace 下誤放 `<template x-for>`（3 條）+ 過時的 `unload` 事件（1 條，site-wide）；修好 SVG bug 後相似探索的連接線也恢復顯示（原被 bug 壓住從未畫出）。

*This release has one theme: **Cover Loading UX + Showcase console cleanup** — pure frontend, zero backend, zero new deps, two orthogonal tracks. **Track A**: covers on a NAS HDD trickle in (≈90/page); previously the wait was blank then a hard "pop". Now each grid card and the Hero card shows a skeleton/shimmer while waiting, fades the cover in on load, and shows an industry-standard broken-image icon when there's no cover — filling the HDD spin-up/seek wait with a "loading" visual. It does not speed up actual loading (that's the thumbnail cache's job); it only fixes "what you see while waiting." **Track B**: clears the 4 console errors on `/showcase` — a `<template x-for>` mistakenly placed inside an SVG namespace (3) + a deprecated site-wide `unload` listener (1); fixing the SVG bug also restores the similar-explore connector lines (previously never drawn, suppressed by the bug).*

### Added
#### 🎴 封面三態（grid + Hero）/ Cover three-state
- **Showcase grid 每張卡片**：載入中 skeleton + shimmer → `@load` 淡入封面 → 無封面/抓不到顯破圖 icon。首屏前 8 張封面 `loading=eager` + `fetchpriority=high`（最先看到的先到），其餘維持 `lazy`。
- **Hero card**（最愛女優精準命中時最上方那張大圖）：補齊到與 grid 一致的三態（獨立旗標，因 Hero 是女優照片非影片封面）。
- 卡片以 `aspect-ratio` 佔位，圖到不位移（無 layout shift）；尊重系統「減少動態」（shimmer/淡入退化為靜態）。

#### 🔇 Showcase console 清零 / Console cleanup
- 相似探索的 rail/sweep 連接線從「永遠畫不出來」恢復為正常渲染（修好 SVG bug 的附帶效果）。

### Changed
- 相似探索 stage 的 SVG 連接線由 Alpine `<template x-for>` 動態產生改為 12 組靜態 `<line>`（鏡射 motion-lab 既有無錯寫法），根除 SVG namespace 下 `<template>` 無 `.content` 的 console error。
- 頁面卸載 cleanup 由 `unload` 事件改用 bfcache-safe 的 `pagehide`（新版 Chrome 以 Permissions-Policy 封鎖 `unload`）。

### Fixed
- **搜尋頁/設計系統頁封面隱形回歸（Codex 二次審核發現）**：封面淡入的 `opacity:0` 預設規則因共用 scope 洩漏到同樣載入 showcase.css 的 `/search` 與 `/design-system`（兩頁的卡片 img 無淡入機制），會讓搜尋結果封面與元件展示 demo 整片隱形；改用 compound `.showcase-container` scope 收斂，只命中 showcase 頁。
- **Hero 無女優照片時的空白框**：最愛女優若無照片，`<img src="">` 不觸發 load/error 而顯空白；改為無照片直接顯破圖 icon（與 grid 一致）。
- **bfcache cleanup 回歸（Codex 二次審核發現）**：`unload`→`pagehide` 後，頁面進 back/forward cache 時 `pagehide` 以 `persisted=true` 觸發會誤跑一次性 cleanup（拆 SSE/abort/resize listener），按 Back 還原（不重跑 init）後頁面缺資源；改為僅在真正丟棄（`persisted=false`）才 cleanup。僅瀏覽器存取會踩，PyWebView 桌面端無此路徑。
- **stale/404 封面 fallback 可見性硬化（Codex 二次審核發現）**：grid 封面 stale/搬移導致 404 時，`handleCoverError` 換 placeholder 後封面可見性原本只依賴 placeholder 二次 `@load` 觸發 `_imgLoaded`（實測 Chromium 會觸發、可見，但屬脆弱隱性依賴）；改為 `handleCoverError` 直接設 `_imgLoaded=true`，破圖 placeholder 確定性顯示、不再依賴 `@load`。僅影響 showcase grid（table/list 無封面、hero/search/lightbox 走各自路徑）。

### Added（守衛 / Guards）
- `tests/unit/test_frontend_lint.py::TestCoverLoadingUx67Guard`：HTML/CSS 三態契約守衛（SVG 無 `<template>`、12 組靜態 rail/sweep id、grid/hero `@load` 綁定、淡入不掛 GSAP 專屬容器、reduced-motion 退化、淡入 scope 收斂於 `.showcase-container`）；`eslint.config.mjs` 加 `addEventListener('unload')` 禁令。
  - 註：HTML/CSS 守衛走 pytest 而非 eslint/stylelint，因 eslint 不解析 Jinja `.html`、選擇器歸屬無法用 stylelint 表達（CD-67-8 既定例外）；可 eslint 化的 `unload` 禁令已在 eslint。屬永久守衛（HTML binding / 架構契約），非 transient。

### Non-Goals（明確不做）
- 不縮短實際載入時間（縮圖快取押後）、不做伺服端 HDD 狀態偵測、不導 HTMX、不重做 Search 頁、不做 Lightbox 大圖載入態（同封面 URL 已快取、秒開無等待）。

### 測試
- 全套 pytest **3538 passed, 2 skipped**（unit + integration，排除 smoke/e2e）+ `npm run lint`（eslint + stylelint）綠。
- CDP 終驗（含生產環境 NAS HDD 實機）：`/showcase` console 0 error、相似探索 rail+sweep 24 條渲染、grid 三態（skeleton 淡入實況）、首屏 eager+high、`/search` 與 `/design-system` 封面可見。

## [0.9.5] - 2026-06-06

本版單一主軸：**把所有「在 `async def` 路由裡裸跑、會打慢 I/O（NAS 檔案 stat / HDD 上的 sqlite / config 檔 / 同步 HTTP）的同步呼叫」移出 event loop**，讓載圖／播放／切頁／任一慢請求不再互相凍住整個 app。純後端技術收斂，**無新 UI、無新設定、無新端點、零新依賴、零 ZIP 影響**；既有功能行為與輸出 byte 級不變。根因：FastAPI 對 `def` 路由會自動丟 threadpool，但 `async def` 路由的函式體直接跑在 event loop 上——裡面任何同步阻塞呼叫都會卡住整個 loop，連帶讓別的請求（含切到新頁的 HTML/API）排不進 loop，畫面就凍住。手段二選一：body 無 `await` → 直接改宣告為 `def`（最便宜，Starlette 自動 threadpool）；body 必須保留 `await` → 把阻塞段包進 `await asyncio.to_thread(...)`。逐處人工確認、不全域 sed。新增 AST 回歸守衛永久防止新路由再犯。

*This release has one theme: **move every synchronous slow-I/O call (NAS file stat / sqlite on HDD / config files / sync HTTP) that was bare-running inside an `async def` route off the event loop**, so loading covers / playback / pagination / any slow request no longer freeze the whole app for each other. Pure backend convergence — no new UI/settings/endpoints, zero new deps, zero ZIP impact; existing behavior is byte-identical. Root cause: FastAPI auto-threadpools `def` routes, but an `async def` route body runs directly on the event loop, so any synchronous blocking call there stalls the entire loop (including the HTML/API for switching pages). Two fixes: no `await` in body → convert to `def` (Starlette auto-threadpools); must keep `await` → wrap the blocking segment in `await asyncio.to_thread(...)`. Done per-call by hand, no global sed. A new AST regression guard permanently prevents new routes from reintroducing the bug.*

### Changed

#### ⚡ async def → def（body 無 await，Starlette 自動 threadpool）
- **止血 hot path**：`get_image` / `get_video`（封面/影片代理）轉 def，一次涵蓋 realpath/exists/getsize/load_config 全部裸跑 stat（每張封面 = 多次 NAS stat，HDD 喚醒時單次可達數百 ms～數秒）
- **純讀 DB 路由 11 處**轉 def：scanner `get_stats`/`clear_cache`/`check_update`/`check_missing`/`view_list`/`get_actress_stats`、showcase `get_videos`/`get_video`、search `get_favorite_files`/`get_local_status`、`motion_lab_data`
- **config/設定檔 I/O 路由 9 處**轉 def：config 7 路由 + `get_scraper_sources` + `get_favorite_scanner_link`（load_config/save_config 移出 loop）

#### 🧵 必留 async → to_thread 包阻塞段
- **翻譯/AI 路由 5 處**：gemini/openai/translate/ollama 測試與翻譯端點的 `load_config` 包 `await asyncio.to_thread(...)`（body 有 httpx await，不能轉 def）
- **半套 offload 補齊**：actress 照片 3 路由 / `jellyfin_image_check` / metatube `connect` 先前只 to_thread 了重活，同 body 的 `init_db`/`repo.*`/`load_config`/`save_config`/同步 HTTP 仍裸跑 → 抽 helper（`_check_cover_path`/`_load_actress`/`_connect_sync` 等）一併移出 loop
- **SSE 外層 + 檔案走訪**：`search_stream`/`batch_enrich`/`list_photo_candidates` 的 pre-stream load_config/DB、`filter_files` 的整段 exists/stat/iterdir 檔案走訪移出 loop（內層 generator 維持原樣）

### Added
- **`tests/integration/test_async_offload_guard.py`**：AST 靜態守衛掃 `web/routers/*.py`，斷言每個 `async def` 路由（含巢狀 async generator）的 body 不得裸跑慢 I/O（直接呼叫或經「含阻塞 I/O 的 sync helper」間接呼叫皆抓）；並正斷言 T1–T3 轉 def 的 24 個 handler 維持 `def`，防回退。新路由自動納入掃描。

### Fixed / Internal
- **Codex review 補三處二階卡 loop**：`search_stream` 內層 async generator 裸呼 `_fetch_actress_profile_with_db`（init_db/repo + DB-miss 同步 scraper HTTP）、metatube `connect` dedup path 裸呼 `_persist_allow_lan`（load/save_config）、`translate_title`/`translate_batch` 裸呼 `get_translate_service`（冷啟動 load_config）全補 to_thread
- **守衛強化**：下潛巢狀 async generator（跑在 loop 上）、per-file 推斷「含阻塞 I/O 的 sync helper」並抓其裸呼叫、排除 generator function（呼叫只建物件、body 由 threadpool 迭代）
- `jellyfin_image_check` 的 `get_db_path`（含 mkdir I/O）一併折進 helper，該路由 body 全乾淨

#### 🔒 並發硬化（plan-66b 後續收斂）— 補回 offload 拆掉的隱式序列化
async-offload 把 `async def`（無 await）改 `def`（Starlette threadpool ~40 並發）/ 加 `to_thread` 後，**拆掉了 event loop 對 handler 的隱式互斥**；凡「pre-branch 靠 loop 序列化才安全」的共享可變資源（config.json RMW / metatube runtime state / cold-start 單例 / 非-config 檔案寫入），offload 後變真並發 → lost-update / TOCTOU。全庫 5-subagent 稽核 + Codex review 後逐處補回協調機制：
- **config.json 寫入序列化 + 原子寫（T1，最大）**：`core/config.py` 加 process-wide `threading.Lock`（非 asyncio.Lock——def 路由跑 threadpool thread），public-locked + private-unlocked 分層 + 原子寫（`tempfile.mkstemp`+`os.replace`）；新增 `mutate_config(mutator)` 把整個 load→改→save 收進單一 critical section。修掉「並切 theme+font（150ms debounce）靜默 lost-update」（每用戶會中）；config 三 RMW 路由 + metatube `_connect_sync`/`_persist_allow_lan` + `get_common_context` locale 首寫全遷移至 `mutate_config`，delete 走 `reset_config_file`（消 exists/unlink TOCTOU）
- **metatube startup generation 帶回（T2）**：lifespan 不再於 `await` 後重讀 `state.generation`（與已修的 `/connect` race 同型 TOCTOU），`startup_reconnect` 回傳 `(names, gen)`；連線臨界段共用 `_connect_lock`
- **metatube `/test` 原子 snapshot（T3）**：新增 `state.probe_snapshot()` 單鎖內取 `(names, gen, base_url, token)`，消「分 4 次讀夾出不一致組合」（names 仍沿用 `_availability` keys，行為不變）
- **translate 單例 init 鎖（T4）**：`get_translate_service` double-checked locking，消 threadpool 並發冷啟動 double-init
- **actress photo 檔寫競態（T4b）**：`_write_actress_photo` 改 `unlink(missing_ok=True)` + temp/`os.replace` 原子寫，消同 actress 並發 local_crop 的 glob/unlink TOCTOU（500）與 torn 檔
- **守衛擴充（T5）**：`test_async_offload_guard.py` 新增 AST 守衛——`web/routers/*.py` + `web/app.py` 禁裸呼 `save_config`（唯一白名單 = `config.py::update_config` full-replace），新路由再犯即報錯

*Concurrency hardening (plan-66b): the offload removed the event loop's implicit serialization, so shared mutable resources that were "safe only because the loop serialized them" became truly concurrent. Re-added coordination per path: a process-wide `threading.Lock` + atomic write + `mutate_config()` RMW helper in `core/config.py` (fixes the silent theme+font lost-update every user hits); metatube startup generation carry-back + shared `_connect_lock`; an atomic `/test` `probe_snapshot()`; a double-checked translate-singleton lock; lock-free atomic actress-photo write (`unlink(missing_ok)` + `os.replace`); and an AST guard banning bare `save_config` outside the `update_config` whitelist across routers + `web/app.py`. Pure backend, zero new deps, byte-identical behavior aside from the added coordination.*

### Non-Goals（明確不做）
- 不導 HTMX（卡死根源在後端 loop，非前端換頁）、不做縮圖/WebP/快取（thumbnail-cache 押後）、不解單請求自身慢（HDD 喚醒/seek 的單張延遲）、不換 aiosqlite、不調 threadpool limiter

### 測試
- 全套 pytest **3523 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠
- 守衛 RED→GREEN 驗證 + 5 種 control（bare-helper / sync-generator / async-gen 內阻塞 / to_thread 包裝 / async-gen 內 bare-helper）全對
- 並發硬化（plan-66b）每處皆**確定性測試**（`threading.Barrier`/`Event`/`lock.locked()` 斷言，非真 race flaky）：no-lost-update / atomic-no-temp-leftover / migration-no-deadlock / startup-generation-carry-back / probe-snapshot / singleton-init-once / actress-photo-atomic / save_config 守衛 RED-check

## [0.9.4] - 2026-06-04

本版單一主軸：讓「掃描來源」頁的 **Active Row 拖曳順序成為所有搜尋路由的唯一真理**，徹底移除 `primary_source` 概念。改完後邏輯收斂成一句話：**順序就是一切**。先前搜尋路由其實有兩套真理在打架——拖曳順序（auto 合併早已照它走）vs. 殘留的 `primary_source` 欄位（Settings 底部那塊標「已停用設定」的 radio，但對精準 DMM 短路與模糊 routing 仍暗中 live）。本版把這個會誤導人的隱性 gap 連根拔除：**精準搜尋**拔掉 DMM 整包短路（Rule 4a）、封面改跟 Active Row 順序（移除 hardcode 反浮水印優先序）、只用啟用中來源；**模糊搜尋**（女優名/關鍵字）從寫死 dmm/javbus 改成照 Active Row 順序的 fallback 鏈（循序試、命中即停、always-on 無視啟用），候選池實測收斂為 javbus + dmm（jav321 keyword 恆回空、javdb 連續模糊呼叫會被 Cloudflare ban）；**進階搜尋**（picker 單源覆寫）維持原樣不動。`primary_source` 從 schema 欄位、config 預設、no-op 傳遞點、Settings radio UI 到舊 config key 全清（含一次性 strip migration），Help 補一句說明「模糊鏈 always-on：停用的來源仍會被模糊搜尋用到」。

*This release has one theme: make the Scan-Sources page's **Active Row drag-order the sole source of truth for all search routing**, fully removing the `primary_source` concept — "order is everything." Routing previously had two competing truths: drag-order (which auto-merge already followed) vs. a residual `primary_source` field (the "deprecated setting" radio at the bottom of Settings, still secretly live for the exact-search DMM short-circuit and fuzzy routing). This misleading hidden gap is removed at the root: **exact search** drops the DMM whole-result short-circuit (Rule 4a), covers now follow Active Row order (hardcoded anti-watermark priority removed), and only enabled sources participate; **fuzzy search** (actress/keyword) changes from hardcoded dmm/javbus to an Active-Row-ordered fallback chain (try-in-order, stop-on-hit, always-on regardless of enabled state), with the candidate pool empirically narrowed to javbus + dmm (jav321 keyword always returns empty; javdb gets Cloudflare-banned on repeated fuzzy calls); **advanced search** (picker single-source override) is unchanged. `primary_source` is purged from the schema field, config default, no-op pass-through call sites, the Settings radio UI, and old config keys (with a one-time strip migration). Help gains a note that the fuzzy chain is always-on — disabled sources are still used by fuzzy search.*

### Changed

#### 🎯 精準搜尋（番號）— 完全照 Active Row 順序
- **拔掉 DMM 短路（Rule 4a）**：`smart_search` 不再有 DMM 整包短路分支；一律走 fan-out + merge，Active Row 順序第一個有結果的來源整包為主、缺欄往後補
- **封面跟順序**：合併封面改吃 `user_order`（移除 `DEFAULT_COVER_PRIORITY` 與 `cover_priority` 參數的硬編碼 `javbus→jav321→javdb` 優先序）；想要反浮水印封面把該來源排前面即可
- **只用啟用中來源**：精準搜尋只考慮 Active Row 啟用中的來源（停用過濾）

#### 🔍 模糊搜尋（女優名/關鍵字）— 照順序的 fallback 鏈
- **有序 fallback 鏈**：依 `get_all_source_ids_ordered()`（含停用來源）∩ 候選池循序試，回空/不可用往下、命中即停，不 fan-out、不需 dedup
- **always-on**：模糊鏈無視啟用——停用的候選池來源仍照順序被使用（與精準的「啟用過濾」刻意不同；Help 已揭露）
- **候選池收斂為 javbus + dmm**：實測 jav321 keyword 搜尋恆回空、javdb 連續模糊呼叫觸發 Cloudflare/IP ban → 從候選池移除（兩者在精準番號搜尋與封面 merge 仍照常使用）；AVSOX 仍排除（無碼專用）
- **保住 javbus 獨有能力**：DMM 排前面但無 proxy / 打中文女優名回空時，鏈續試 javbus（無 proxy 直連 + 吃中文名）

### Added
- **Help 模糊 always-on 揭露**：Help「來源啟停與排序」段補一句「模糊搜尋例外：用女優名／關鍵字模糊搜尋時，即使來源被停用仍會照排序被用到（停用只影響番號精準搜尋）」（zh_TW 先行）

### Removed
- **`primary_source` 概念徹底移除**：`SearchConfig.primary_source` 欄位 + `web/config.default.json` 預設值 + `search_jav`/`smart_search`/`search_actress`/enricher/router 的 no-op 傳遞點與簽章參數全清
- **Settings「預設搜尋來源（已停用設定）」radio block**：`source-badges-row` 複合元件（radio + CENSORED/UNCENSORED badge 列 + 說明）+ `state-config.js` 的 `primarySource`/`SOURCE_NAMES`/`UNCENSORED_SOURCES`/`isSourceActive` + `settings.css` Source Badges section + design-system D.10 demo + zh_TW 兩個 deprecated key 全拔（`isDmmAvailable`/`CENSORED_SOURCES` 保留，Active Row 仍用）

### Fixed / Internal
- **strip migration**：`load_config()` 直接 return raw dict 不經 Pydantic validate，舊 `config.json` 殘留的 `primary_source` key 不會被自動剝除 → `core/config.py` 加一次性 strip（載入時 `del` + 觸發 save）
- **`_fuzzy_one` 統一 adapter**：四源 keyword 入口（DMM None→[]、JavDB Video→dict、JavBus 抽 `_javbus_keyword_search`）歸一為 `list[dict]`；`search_actress` 改 thin wrapper；seed 僅由首發動源送一次；DMM `_source='dmm'` 補齊與 javbus 一致（內部欄位）
- **無碼模式 × 模糊回空**：維持現況「安靜回空」+ 加設計意圖註解（無碼模式下模糊搜尋預期回空，非 bug）；AVSOX `search_by_keyword` 標 dead-code 註解

### 測試
- 既有 routing 測試**改寫**反映新行為（不靠舊短路綠燈）：`test_pipeline_routing`（拔 DMM-first 短路、改 fan-out / 模糊鏈）、`test_source_merger`（封面跟 user_order）、`test_core_config`（strip migration）、`test_scraper_callbacks`/`test_new_scrapers`/`test_api_enrich`/`test_api_rescrape_preview`（移除 primary_source 斷言）
- 新增 `test_fuzzy_chain.py`（鏈順序 / 候選池過濾 / DMM 無 proxy fallback / always-on 停用仍用 / 非模糊源跳過 / seed-once / dmm `_source`）+ `test_source_settings.py`（`FUZZY_SEARCH_SOURCES` 內容）
- 移除過時前端守衛 `test_primary_source_deprecated_marker`（[transient-guard]，被守的 deprecated block 已拔除）
- 全套 pytest **3464 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠

### i18n
- 本版交付 zh_TW 文案（`help.scraper.fuzzy_always_on`）；移除 zh_TW 的 `primary_source_deprecated_hint`/`note` + dangling `settings.search.default_source_hint`；其他 3 語系（zh_CN / en / ja）的對應 key 差異依專案 i18n 規範**待 milestone 同步**

### 已知行為（非本版範圍）
- **JavBus 變體探測（Rule 4b，feature/61 既有）仍在**：精準搜番號時，javbus 啟用且該番號有 variant 記錄（多數主流番號）→ javbus 整包早退、無視 Active Row 順序。本版只拔 DMM 短路（Rule 4a），未動 variant probe；故「精準搜順序就是一切」在 javbus 啟用且有該番號時不完全成立（variant probe 同時驅動版本切換器，需一併考量），留待後續獨立 branch 評估。

## [0.9.3] - 2026-06-03

本版是 v0.9 scraper-federation epic 三段（B1/B2/B3）全部 ship 後的 **UX 收斂插入段**（feature/64-settings-help-ux-polish，排在 javlibrary B4 之前），純前端、不動任何後端行為。連續三段堆功能留下幾處 UX 粗糙邊，本段一次收齊：**A — 進階重刮 picker metatube 膠囊三態語意修正**（可達的 metatube 來源不再被畫成 disabled 灰底刪除線，只有真的連不上才 offline 樣式；搜尋情境彈窗標題改「進階搜尋」）；**B — Settings IA 退回單欄三分類**（v0.9.0 的 6-tab 拆掉，進階回歸各 section 內嵌摺疊，舊用戶熟悉的「一長條 + 進階就在功能旁」手感回來；header 下新增 quick-toggle 列放下載劇照 + 進階搜尋；搜尋來源卡版面微調）；**C — Help 內容修正 + metatube 教學卡**（進階搜尋說明併進 Search 卡）；**D — 移除 dev-only `/settings-mock` POC**（route/template/i18n/guard 全清）。收尾 64e 再做一輪精修：quick-toggle label 去括號 + 進階搜尋 Beta 改膠囊 + 說明改 help-popover（列全 5 入口）、無碼 batchbar 改 segmented 雙段控件（全開｜無碼）+ 計數器移右、刪常駐 footnote、DMM proxy row 搬到 metatube 連線區正上方、Help picker 補完整 5 入口。

*This release is the UX-consolidation insert after all three blocks of the v0.9 scraper-federation epic shipped (feature/64-settings-help-ux-polish, slotted before the javlibrary B4 block). Pure frontend, zero backend behavior change. It cleans up the rough edges left by three feature-stacking releases: **A — three-state metatube pill semantics** in the advanced re-scrape picker (reachable metatube sources no longer rendered as disabled grey/strikethrough — only truly-unreachable ones get the offline style; the search-context modal title now reads "Advanced Search"); **B — Settings IA reverted to a single-column three-category layout** (the v0.9.0 6-tab nav is gone, "advanced" folds back inline within each section, restoring the familiar "one long page, advanced right next to the feature" feel; a quick-toggle row under the header hosts Download Sample Images + Advanced Search; the search-sources card layout is tuned); **C — Help content fixes + a metatube tutorial card**; **D — removal of the dev-only `/settings-mock` POC**. The 64e finishing pass polishes further: de-parenthesized quick-toggle label, Advanced-Search "Beta" as a badge with a 5-entry help-popover, the uncensored batch bar rebuilt as a two-segment control (Open-all ｜ Uncensored) with the counter moved right, the persistent footnote removed, the DMM proxy row moved directly above the metatube connection area, and the Help picker filled out to all 5 entry points.*

### Added

#### 🎛️ A — 進階重刮 picker 三態語意

- **metatube 膠囊三態**：可達 metatube 來源畫成正常可選態（無刪除線）；不可達才 offline 灰化 + 提示；內建來源由使用者開關控制，與 metatube 連線狀態視覺分流
- **搜尋情境標題**：從搜尋框長壓開的進階彈窗標題改顯「進階搜尋」（依入口切換，US-A2）

#### 🗂️ B — Settings 單欄三分類 IA

- **quick-toggle 列**：header 下、section 上，放「下載劇照」+「進階搜尋」兩個常用開關
- **進階就地摺疊**：各 section 的進階設定回歸該功能旁的 x-collapse 摺疊塊（取代 v0.9.0 獨立 advanced tab），metatube 連線區由 enable toggle gate
- **搜尋來源卡版面微調**：toggle 下移、proxy 上移貼近 DMM 來源

#### 📖 C — Help 內容 + metatube 教學

- **metatube 教學卡** + Help 內容修正；進階搜尋說明併進 Search 卡
- **Help 進階搜尋 picker 補完整 5 入口**：搜尋框長壓／結果面板 🔄 長壓／封面牆缺卡長壓／燈箱缺卡長壓／燈箱番號旁 ⚙，符號編號（①②③④⑤）與 Settings 進階搜尋 popover 文案一致

#### ✨ 64e — 收尾精修

- **quick-toggle 精修**：下載劇照 label 去括號（extrafanart 說明留 `?` popover）；進階搜尋「Beta」改 `.source-pill-badge` 膠囊，說明從常駐 `<small>` 改 help-popover（列全 5 入口）
- **無碼 segmented 控件**：batchbar 改藥丸型雙段「全開 ｜ 無碼模式」；點全開段全開至 cap（metatube 佔滿時顯示 cap 飽和提示、不 silent no-op），點無碼段關 4 有碼源；計數器移到 batchbar 右側並加 `?` popover
- **DMM proxy row 搬位**：整個 proxy 控件（hint + 輸入框 + 測試鈕）搬到 metatube 連線 toggle 正上方，貼近 DMM 來源 + 連線區

### Changed

- **Settings IA 退回單欄**：v0.9.0 的 6-tab + 探索期一度加入的 quick-jump sticky nav **最終移除**（spec §11 為準），回到單一長條三分類，降低跨分頁認知斷裂
- **進階搜尋 toggle label**：去 `(Beta)` 括號，Beta 改膠囊呈現
- **無碼區互動**：「離開無碼模式」改為點 segmented 的「全開」段（不再是 toggle off）
- **`allBuiltinEnabled` getter + `uncensoredMode` 空陣列 guard**：segmented 高亮判斷新增 getter，並修 `sources=[]` 初始載入的 vacuous-true 誤高亮邊界

### Removed

- **dev-only `/settings-mock` POC 全清**（CD-64-D1）：route（`web/routers/settings_mock.py`）+ template（`settings_mock.html`）+ 相關 i18n / guard 一併拔除，不留殭屍（從未揭露於 capabilities）
- **常駐 `disabled_footnote`**：搜尋來源卡的 jargon footnote 移除（HTML + 4 locale key + `.settings-sources-footnote` CSS 徹底拔除）；`warn_all_disabled`（條件顯示）簡化口語化保留

### Fixed

- **help-popover `pre-line` scope（Codex P2）**：64e-1 的 `white-space: pre-line` 誤加在共用 `.help-popover__body`，使其他用 `<br>` + template 換行的 popover 多出空白行；改為 `.help-popover__body--multiline` modifier，只進階搜尋 5 入口清單套用
- **Settings header 手機防溢出（Codex P2/P3）** + 清殘留 `.settings-tab` CSS
- **DMM proxy-grey 呈現 + nav `aria-current`（TASK-64b-0 Codex P2/P3）**

### i18n

- **本版交付 zh_TW 文案**：quick-toggle / 進階搜尋 5 入口 popover / 無碼 segmented / 計數器 popover / Help metatube 教學 + picker 5 入口等新 UI 文字 zh_TW 先行；`disabled_footnote` 4 locale 同步刪除保持乾淨；其他 3 語系（zh_CN / en / ja）依專案 i18n 規範**待 milestone 同步**

### 測試

- 守衛更新：進階 picker 三態 + 彈窗標題契約（TestPicker64aThreeStateGuard）、Settings 單欄結構重寫、quick-toggle help-popover contract（`test_advanced_search_has_help_popover`）、proxy row 位置（`test_proxy_row_before_metatube_toggle`）；移除過時的 6-panel / activeTab / settings_mock 守衛
- 全套 pytest 3439 passed, 2 skipped（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠
- transient-guard 標記數未增（驗收閘 TASK-64e-4）

## [0.9.2] - 2026-06-01

本版是 v0.9 scraper-federation epic 的第三段（B3，**完結篇**），feature/63-metatube-http-mode 三軌道出貨。主軸是把「**自架 metatube server → 一次解鎖 30 個 provider**」這條線全程打通：**63a — 後端 HTTP client + 資料映射**（metatube 連線狀態 singleton、provider 清單、MovieInfo → Video mapper、連線 canary probe 並行測 30 源）；**63b — Settings 連線區接線**（填 URL + Bearer token 按連線真的動起來、30 個 provider 落進 Parts Bin、probe 自動測一輪並灰化測不到的來源、SSRF URL 驗證 + LAN 自架 opt-in、[重新測試] 鈕）；**63c — Routing 整合 + NFO 強化 + DMM proxy 灰化**（已 promote 的 metatube provider 跟內建 8 來源走同一條自動搜尋管道；無碼番號 FC2/HEYZO/日期型優先吃 metatube 無碼源；metatube 簡介寫進 NFO `<plot>` 給 Jellyfin 用；scraper-sources capability 注入 available map；DMM 需 proxy 時進階 picker 灰化提示）。本段完成 = v0.9 scraper-federation epic 全部兌現。

*This is v0.9 scraper-federation epic, Block 3 — the final block (feature/63-metatube-http-mode). Three tracks wire everything together: **63a — HTTP client + data mapping** (MetatubeConnectionState singleton, provider enumeration, MovieInfo → Video mapper, canary probe running in parallel across all 30 sources); **63b — Settings connection wiring** (the connect form now actually works — fill URL + optional Bearer token, hit Connect, 30 providers land in the Parts Bin, a probe round greys out unreachable sources with contextual hints, SSRF URL guard with LAN opt-in, [Re-test] button); **63c — routing integration + NFO enrichment + DMM proxy indicator** (promoted metatube providers participate in the same auto-search pipeline as built-in sources; uncensored numbers FC2/HEYZO/date-format prefer active metatube uncensored sources; metatube summary written to NFO `<plot>` for Jellyfin; scraper-sources capability gains availability_map; DMM greys out in the picker when proxy is not configured). B3 completion = v0.9 scraper-federation epic fully delivered.*

### Added

#### 🔌 63a — Metatube HTTP 後端基建

- **後端 HTTP client**：`MetatubeHttpClient` 打 metatube REST API（單 provider 並行 search / info），多結果自動消歧取最佳，完整 exception 階層（`MetatubeError` 基底 + `MetatubeUnavailable` / `MetatubeAuthError` / `MetatubeNotFound` / `MetatubeClientError` / `MetatubeProtocolError`）
- **MovieInfo → Video mapper**：metatube `MovieInfo` 轉 OpenAver `Video`；新增 `Video.summary` 欄（僅供 NFO 寫出，不顯示、不入庫 DB 搜尋）
- **MetatubeConnectionState singleton**：執行期連線狀態 + availability map；不寫 config，重啟歸零後由 connect 端點重建

#### 🔌 63b — Settings 連線區接線（US1 / US2 / US3 / US5 / US9）

- **連線表單接真**：填 Server URL + 可選 Bearer token，按 [連線] 真的打 `/v1/providers`；成功 → 「✓ 已連線」狀態 + 下方展開 Parts Bin（30 個 provider 膠囊，全 `enabled=false`，不自動 promote）；失敗 → toast 說明原因，維持 idle
- **Parts Bin promote / demote**：Parts Bin 點膠囊 → 進 Active Row；Active Row 點膠囊 → 退回 Parts Bin；跟內建來源互動方式一致，cap 10 共用
- **連線 probe 灰化（US9）**：連線成功後自動測一輪 30 來源（並行 canary probe）；測不到的膠囊灰化 + 顯示常見成因提示（不斷言是哪個原因）；[重新測試] 鈕可手動重跑
- **SSRF URL 驗證（US5）**：`validate_metatube_url()` 拒絕內網 IP / loopback / 私有 CIDR / 非 http(s) scheme；自架區網需勾「LAN 自架」opt-in 才放行
- **進階 tab enable toggle**：Settings › 進階 metatube 開關控制整個 Section 3 是否顯示；未啟用時 Parts Bin / 連線區完全隱藏

#### 🔍 63c — Routing 整合 + 功能強化（US2 / US4 / US7 / US8 / US10）

- **metatube 源進主力搜尋管道**：已 promote 且可達的 metatube provider 自動加入 auto 搜尋 / scanner / NFO 補完 / enrich，跟內建 8 來源並行，結果按使用者排序合併去重（第一個成功來源整包贏）
- **進階 picker 吃 metatube 真資料（US8）**：進階搜尋 picker 列出所有啟用來源（含 metatube），選定單源整包贏，不再硬編碼分組
- **無碼 staged promotion（US4）**：FC2 / HEYZO / 日期型無碼番號優先路由到已啟用且可達的 metatube 無碼源（`_get_uncensored_sources` metatube 優先），fallback 維持內建
- **summary 寫進 NFO `<plot>`（US7）**：metatube 回傳的影片簡介寫入 NFO `<plot>` 欄，供 Jellyfin / Emby / Kodi 讀取；OpenAver 自身不顯示、不入庫；同步補 `<rating>` 數值欄 + `<mpaa>JP-18+` 固定值
- **DMM proxy 灰化（US10）**：DMM 標記 `requires_proxy=true`；Settings 掃描來源 + 進階 picker 兩個入口，proxy 未設定時 DMM 膠囊灰化並顯示提示
- **scraper-sources capability 注入 availability_map**：`GET /api/scraper-sources` 回傳的 capability 同步帶入各 metatube provider 的 `available` 狀態，讓 AI agent 知道哪些源此刻可達

### Changed

- **metatube 進階 picker 分組改資料驅動**：移除 B2 預留的靜態 Recommended 群組殘留，改由後端 availability_map 驅動（§7.5 徹底清理）
- **NFO writer 補齊三欄**：新增 `summary → <plot>`、`rating → <rating>`、`<mpaa>JP-18+` 寫出邏輯；`to_legacy_dict()` 不含 summary（不影響 DB 搜尋索引）

### Fixed

- **Active Row unavailable metatube 可 demote（63d）**：移除 demote guard 對 `available=false` 的限制，讓測不到的 metatube 膠囊可正常點下去退回 Parts Bin（guard 不再與 availability 耦合）
- **connect 後端 token canary 驗證**：connect 時以真實 token 打 canary 端點驗證 auth，修復「token 填錯仍顯示已連線」的靜默成功問題
- **Parts Bin data-available binding 強制字串化**：修復 Alpine.js `x-bind:data-available` 對 `false` 直接 remove attribute 的陷阱，改強制字串化確保灰化 CSS binding 正確觸發
- **probe-failed Parts Bin pill 改用可見警示屬性（Codex P3）**：原本設的 `--pill-accent` 在膠囊 `data-enabled="false"` 下不被讀取（等於無效），改為直接驅動 `border-color` + slash icon 警示色（`--color-warning`），測不到的來源視覺明顯可辨
- **batch-search echo strip（Codex P1）**：批次搜尋回傳結果移除多餘的 echo 欄位
- **nfo_updater NFO parity（Codex P2）**：`nfo_updater` 補齊與 `nfo_writer` 相同的三欄寫出邏輯（parity）

### Security

- **SSRF 防護 metatube URL 驗證（US5）**：新增 `validate_metatube_url()`（`core/metatube/validation.py`）—— `ipaddress` + `getaddrinfo` 雙重驗證拒絕 RFC-1918 私有 CIDR / loopback / 非 http(s) scheme；不勾「LAN 自架」時內網 URL 一律拒絕，無 SSRF 攻擊面

### Internal

- **metatube SourceConfig 前置**：`SourceConfig` schema 加 metatube 有碼 provider 映射清單 + builder helper；63a 起所有 metatube 來源由此單一 schema 管理，不再散落硬編碼
- **connect / disconnect / status / test 4 API 端點**：`/api/settings/metatube/connect`、`/api/settings/metatube/disconnect`、`/api/settings/metatube/status`、`/api/settings/metatube/test` 四端點處理連線生命週期
- **stale probe guard**：連線前清舊 availability key，避免 reconnect 後殘留舊 probe 結果
- **port validate + persist rollback**：connect 端點補 port range 驗證 + 失敗時 rollback config，防止寫入無效設定

### i18n

- **本版交付 zh_TW 文案**：metatube 連線 / probe / toggle / DMM proxy hint / Parts Bin pill hint / Help 頁 SQLite 寫鎖說明等新 UI 文字 zh_TW 先行；其他 3 語系（zh_CN / en / ja）依專案 i18n 規範**待 milestone 同步**

### 測試

- 新增測試覆蓋：metatube HTTP client / MovieInfo mapper / probe 狀態 / ConnectionState / URL validation / routing 整合 / 無碼 staged promotion / NFO plot-rating-mpaa 寫出 / connect + probe 端點 / capability availability_map gate + Parts Bin pill binding 契約守衛
- 全套 pytest 綠（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠

## [0.9.1] - 2026-05-30

本版是 v0.9 scraper-federation epic 的第二段（B2），feature/62-showcase-advanced-rescrape 三軌道出貨。主軸是全新的**進階重新刮削彈窗（Advanced Re-scrape）**：以前重抓資料只能對「找不到資料的缺卡」做，現在你可以對**任何一片**改番號、挑來源重抓，先看預覽卡再決定要不要覆蓋。三條軌道把這個彈窗接到三個入口：**62a — 彈窗本體**（模糊背景的浮層，番號可直接編輯、來源膠囊點一下就搜、預覽卡可換頁挑結果，✗ 取消 / ✓ 套用；來源膠囊抽成跨頁共用元件）；**62b — Showcase 入口**（lightbox 番號旁多了 ⚙ 進階鈕，缺卡長壓也能進同一個彈窗，套用後固定整包覆蓋並即時刷新畫面，改過的番號會持久化；新增 `video_rescrape_with_source` AI capability）；**62c — Search 入口統一 + 結果面板 🔄 長壓挑來源**（搜尋頁長壓搜尋鈕改用同一個彈窗，取代舊的精簡 radio picker；結果卡的 🔄 鈕長壓可挑來源、只替換當前這張卡）。

*This release is v0.9 scraper-federation epic, Block 2 (feature/62-showcase-advanced-rescrape). The centerpiece is a new **Advanced Re-scrape modal**: previously re-scraping was limited to cards missing data — now you can pick **any** video, edit its number, choose a source, re-fetch, preview the result card, and only then decide whether to overwrite. Three tracks wire this modal into three entry points: **62a — the modal itself** (a blurred-backdrop overlay with an editable number, click-to-search source pills, a paginated preview card, and ✗ cancel / ✓ apply; the source pill is extracted into a cross-page shared component); **62b — Showcase entry** (a ⚙ advanced button next to the number in the lightbox, long-press on missing cards opens the same modal, applying always does a full overwrite with instant refresh and persists any corrected number; adds the `video_rescrape_with_source` AI capability); **62c — unified Search entry + results-panel 🔄 long-press source pick** (the search bar long-press now opens the same modal instead of the old slim radio picker; the results card's 🔄 button long-press lets you pick a source and replace just the current card).*

### Added

#### 🪟 62a — 進階重新刮削彈窗

- **任一片都能重刮**：不再限定缺資料的卡，任何影片都能改番號 + 挑來源重新抓資料
- **彈窗互動**：模糊背景浮層，番號可直接編輯、來源膠囊點一下立即搜尋、預覽卡可換頁挑不同結果，✗ 取消 / ✓ 套用
- **預覽再覆蓋**：套用前先看到抓回來的預覽卡，確認沒問題才寫入（預覽只搜不寫，封面僅供前端顯示不下載）

#### 🎬 62b — Showcase 進階重刮入口

- **lightbox ⚙ 進階鈕**：放在番號旁，點開進階重刮彈窗（需在進階設定開啟 Beta）
- **缺卡長壓入口**：Showcase grid 與 lightbox 的補資料鈕長壓 700ms 進同一個彈窗，輕點維持原本的快速補資料
- **套用即時刷新**：Showcase 套用後固定整包覆蓋並當場更新畫面，改過的番號也會正確存檔（透過 NFO `<num>` 持久化）

#### 🔄 62c — Search 入口統一 + 結果面板挑來源

- **搜尋頁入口統一**：長壓搜尋鈕改開同一個進階重刮彈窗（番號可編輯 + 來源膠囊即點即搜），取代舊的精簡 radio picker；點來源直接進正常結果區
- **結果面板 🔄 長壓挑來源（US7）**：🔄 鈕輕點維持原本的循環切換；長壓開來源選單，用選定來源重抓當前番號、只替換當前這張卡（不重設整列結果），之後輕點從選定來源接續循環

#### 🤖 AI Capability

- **新增 `video_rescrape_with_source`**：讓 AI agent 可指定番號 + 來源重刮並覆蓋資料；屬有副作用、不可逆操作，標記 `confirmation_required: true`，description 含覆蓋風險說明（指向既有 `/api/enrich-single` 端點，與補缺面 `enrich_single` 並存為同端點雙風險面）

### Changed

- **Search 進階入口改用共用彈窗**：移除 B1 時期的精簡 radio picker（`advancedPickerModal` DOM + 相關 CSS），改 include 共用重刮彈窗 partial
- **三入口共用長壓 helper**：Showcase / Search / 結果面板三處長壓統一接 `shared/long-press.js`，並在 `/design-system` 登記 long-press pattern
- **重刮彈窗 metatube 分組改 data-driven**：彈窗來源分組改資料驅動（為 B3 metatube 連線預留，不再硬編碼分組）

### Fixed

- **重刮彈窗層級修正**：彈窗正確浮到 lightbox 上層，修復玻璃 backdrop class 開關
- **`refresh_full` 分裂守衛一般化**（Codex P1）：守衛從「NFO 與 cover 皆已存在」放寬為「不會寫出任何 sidecar 檔」就擋下，補上 `write_nfo=false + write_cover=false` 的純 DB-only 路徑（避免 200 success 但零寫檔、只動 DB 的分裂狀態）
- **switch-source 持久化**（Codex P2）：結果面板長壓挑來源成功後補 `saveState()`，對齊輕點切換路徑，修復「換源後 session restore / 離開回來會回舊卡」
- **長壓旗標鍵盤兜底**（Codex P3）：關閉彈窗時清長壓殘留旗標，涵蓋鍵盤 / 輔助技術觸發（無 mousedown 前導）的路徑

### Internal

- **共用基建**：來源膠囊抽成 unscoped 跨頁共用元件 + bootstrap partial；新增 `/api/rescrape/preview`（只搜不寫，復用 B1 search 路徑）
- **SSRF 防護維持**（CD-62-3）：commit 重抓不透傳 `scraper_data`，後端自行重抓，預覽封面僅遠端 URL 經 `/api/proxy-image` 顯示，無 SSRF 攻擊面
- **switch-source async race 防護**：開窗同步捕捉目標卡 ref，await 回來後四重 stale 判斷才寫回，導覽期間自由重指派不誤寫
- **eslint flat-config guard 超集化**（Codex P3）：`state-rescrape.js` 的 Group 7 rule 重述為 Group 6 完整 selector 超集 + 62c 自己的負向規則（避免 flat config 不 merge 導致守衛漏洞）
- **孤兒 i18n key 清理**（4 locale 對稱）：移除 B1 picker 移除後無引用的 8 個 `settings.advanced_search.picker_*` key
- **原始碼 EOL 正規化**：一次性 CRLF→LF（73 檔純 EOL 轉換，內容零變更）+ 新增 `.gitattributes` per-extension 規則防復發（Windows 腳本保留 CRLF）

### i18n

- **本版僅交付 zh_TW 文案**：`showcase.rescrape.*` 等新文案的其他 3 語系（zh_CN / en / ja）依專案 i18n 規範**待 milestone 同步**

### 測試

- 新增測試覆蓋：重刮預覽端點 + `refresh_full` 分裂守衛、三入口長壓 / tap 分流契約守衛、鎖番號修正持久化契約鏈（前端 prefill + 後端 `number` 欄位）、switch-source 挑來源守衛、`video_rescrape_with_source` capability 旗標 / 風險詞 / contract（tool count 38→39）
- 全套 pytest 3036 passed, 2 skipped（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠

## [0.9.0] - 2026-05-29

本版是 v0.9 scraper-federation epic 的第一段（B1），feature/61-settings-ia-sources 三軌道出貨：**61a — 後端資料驅動來源 schema**（使用者無感的基礎重構：來源清單從寫死改為 SourceConfig schema、config.json 新增 sources 段、routing 收斂到單一真理來源）；**61b — Settings 分區 IA 重設計**（頂部 6 個分頁取代原本捲一頁的設計，URL 深連結 + 記住上次分頁 + 平滑淡入動畫）；**61c — 掃描來源 tab + Metatube 骨架 + 進階搜尋 picker（Beta）+ scraper-sources capability**（使用者第一次可以直接管理哪些來源參與自動搜尋）。

*This release is v0.9 scraper-federation epic, Block 1 (feature/61-settings-ia-sources). Three tracks: **61a — data-driven source schema** (user-invisible backend refactor: source list moved from hardcoded to SourceConfig schema, config.json gains a `sources` section, routing converges to a single source of truth); **61b — Settings tabbed IA redesign** (6-tab top nav replaces the single-scroll page, with deep-linkable URLs, last-tab memory, and smooth fade-in transitions); **61c — Scan Sources tab + Metatube skeleton + Advanced Search picker (Beta) + scraper-sources capability** (users can now directly manage which sources participate in automatic searches).*

### Added

#### 🗂️ 61b — Settings 分區 IA 重設計

- **頂部 6 分頁導覽**：顯示偏好 / 刮削行為 / 掃描來源 / 整理規則 / AI 翻譯 / 進階；點分頁直達對應區塊，不用捲整頁
- **URL 深連結**：支援 `/settings#sources` 等 hash 直連，分享設定位置、AI agent 可精確導航
- **記住上次分頁**：重新開啟 Settings 自動回到上次停留的分頁
- **切換動畫**：分頁內容平滑淡入，尊重系統 `prefers-reduced-motion`
- **手機橫向捲動分頁列**：小螢幕不換行，橫滑切換

#### 🎛️ 61c — 掃描來源 tab（v2 Two-Zone）

- **8 個內建來源膠囊**：JavBus / Jav321 / JavDB / DMM / D2Pass / HEYZO / FC2 / AVSOX，點一下開關，拖曳改搜尋優先順序，即時生效不用存
- **「無碼模式」一鍵切換**：停用所有有碼來源；手動點回任一有碼來源自動取消無碼模式
- **同時啟用上限 10 個**：超過上限操作擋下，顯示提示
- **全部停用警告**：所有來源停用時顯示警告，並說明 always-on 例外規則（模糊搜尋鏈 / 無碼 fallback 等）

#### 🔌 61c — Metatube 連線區骨架（B1 預留）

- **未啟用時不顯示**：Metatube 整區預設隱藏，啟用後才展開（連線實作待 B3）
- **連線狀態機**：兩個主狀態 — 「待連線表單」與「已連線 + 摺疊 provider 清單（Parts Bin）」

#### 🔍 61c — 進階搜尋 picker（Beta）

- **預設關閉**，在 Settings › 進階 開啟後生效
- **搜尋頁長壓搜尋鈕**跳出來源選單，可挑單一來源（含未啟用的）做一次性覆寫搜尋，不改變常駐啟用設定

#### 🤖 AI Capability

- **新增 `GET /api/scraper-sources`**：AI agent 可查使用者目前啟用、會用於自動搜尋的來源清單；不揭露停用來源、進階專用來源或連線設定

### Changed

#### ⚙️ 61a — 後端整理（使用者無感）

- **來源清單資料驅動化**：`SourceConfig` schema 取代寫死的 scraper list；config.json 升級時既有設定字面 100% 保留，無碼模式欄位自動轉換
- **Routing 單一真理來源**：停用的來源不再出現在自動搜尋管道；保留四條 always-on 規則（模糊搜尋鏈 / 無碼番號 fallback / capability filter / 精確搜尋前置）
- **多來源結果合併抽共用函數**：文字 / 後設欄位依使用者拖曳順序「第一個成功來源整包贏」；封面獨立優先序維持 JavBus > Jav321 > JavDB（反浮水印）
- **來源 enum / 無碼模式判斷收斂到單一 helper**：消除散落硬編碼

### Internal

- **i18n 4 語系同步**：zh_TW / zh_CN / en / ja 全部補齊 Settings 分頁 + 掃描來源 + 進階搜尋 UI 文字；`/settings-mock` POC keys 維持 zh_TW only（B4 移除）
- **Codex review 收斂**：多輪 review 修正實作細節（狀態機邊界 / capability filter 邏輯 / merger 邊界 / picker 互動）

### 測試

- 新增測試覆蓋：資料模型 migration / capability endpoint / 拖曳 persist / 多來源 merger / 進階 picker 互動
- `pipeline_routing` 測試加環境隔離（不受 ambient config 影響）
- 全套 pytest 2937 passed（unit + integration，排除 smoke / e2e）

## [0.8.10] - 2026-05-28

本版是 v0.9 主軸 epic（scraper federation）開工前的技術債清理包（feature/60-tech-debt-cleanup），六項收尾：**B3 SSRF 安全修補**（`/api/proxy-image` 新增 URL 白名單 guard，scheme 強制 https、雙 set 分離 root domain 子域 endswith 比對 vs exact host 嚴格匹配，非白名單一律 403）；**B1 Scanner DB-miss tag 修復**（DB-miss 路徑 scraper 回傳 key 為 `tags` 不是 `genres`，導致新番整理後 NFO `<genre>` 永遠空白，1 行修正）；**B2 JavBus ConnectionError 強化**（三個 HTTP 請求點 + `search_by_keyword` 內外兩層 catch，DNS 失效 / proxy 斷線時批次搜尋跳過繼續而非整批崩潰）；**R3 女優查詢 json_each 重寫**（`count_by_actress` / `get_videos_by_actress` / `get_videos_by_actress_names` 三 method 從 4-LIKE-OR full-table scan 改 `json_each` + `json_valid` guard，與既有 `count_videos_for_actress_names` 對齊，「巨乳」不再誤中「巨乳波多野」、`actresses='[]'` 不誤中、同片 primary+alias 兩名不重複）；**R2 frontend-stack-roles.md 同步**（HTMX 已於 Phase 47 取消引入，主規範文件加 2026-04-26 banner + 段落 ⚠️ 規劃中標記，消除每個新 AI session 找 hx-* 的固定認知稅）；**L1 gallery_generator LEGACY 標注**（reverse-engineered 早期 god file 加 docstring 終止 AI review 重複建議拆分）。Bonus：capabilities `proxy_image` 描述同步白名單 + 403 行為。

*This release is the tech-debt cleanup before the v0.9 scraper-federation epic (feature/60-tech-debt-cleanup). Six fixes: **B3 SSRF patch** (`/api/proxy-image` URL allowlist guard with https-only scheme, dual-set design — root domains with subdomain endswith vs exact hosts with strict match; non-allowlist → 403); **B1 Scanner DB-miss tag fix** (scrapers return `tags` key not `genres`; NFO `<genre>` was always blank after scraping new numbers; 1-line fix); **B2 JavBus ConnectionError hardening** (3 HTTP call sites + `search_by_keyword` two-layer catch; batch search now survives DNS/proxy failures instead of crashing the whole batch); **R3 actress json_each rewrite** (`count_by_actress` / `get_videos_by_actress` / `get_videos_by_actress_names` switch from 4-LIKE-OR full-table scan to `json_each` + `json_valid` guard, mirroring the existing `count_videos_for_actress_names`; "巨乳" no longer false-matches "巨乳波多野", `actresses='[]'` no longer matches, same video with primary+alias no longer duplicated); **R2 frontend-stack-roles.md sync** (HTMX was cancelled in Phase 47 — main spec doc now has a 2026-04-26 banner + ⚠️ 規劃中 section markers, eliminating the cognitive tax for every new AI session); **L1 gallery_generator LEGACY annotation** (reverse-engineered early god file gets a docstring to stop recurring AI review split suggestions). Bonus: capabilities `proxy_image` description synced with allowlist + 403 behavior.*

### Security

- **B3 `/api/proxy-image` SSRF 白名單防護**（`web/routers/search.py`）：新增 `_is_allowed_image_url()` helper + 兩個 set 嚴格分離（CD-60-1）：
  - `_ALLOWED_IMAGE_ROOT_DOMAINS`：scraper 圖片來源（javbus / jav321 / heyzo / caribbeancom / 1pondo / 10musume / avsox.* / javten / jdbstatic — JavDB CDN，覆蓋 c0/c1/c2 等 numbered subdomain），含子域 endswith 比對
  - `_ALLOWED_IMAGE_EXACT_HOSTS`：CDN / 女優照固定 host 嚴格匹配，不允子域繞過（pics.dmm.co.jp / awsimgsrc.dmm.co.jp / www.dmm.co.jp / javdb.com / cdn.jsdelivr.net / upload.wikimedia.org / Graphis 三變體 / Minnano 兩變體，對齊 `core/actress_photo.py::PHOTO_HOST_WHITELIST`）
  - scheme 強制 `https`；非白名單一律 403（不發出 `requests.get`，無 SSRF 攻擊面）
- **B3 silent except 修復**：原 `except Exception: pass` 改為 `logger.exception(...)`，response 維持 404（不洩漏 exception detail 給前端）
- **Capabilities 同步**（Codex review）：`proxy_image` description / output_schema 加註白名單規則 + 403 行為

### Fixed

- **B1 Scanner DB-miss tag key 修復**（`web/routers/scanner.py:1243`）：`r.get('genres', [])` → `r.get('tags', [])`；scrapers/models.py:46 實際 key 為 `tags`，原寫法導致 DB-miss scrape 路徑 VideoInfo.genre 永遠空字串、NFO `<genre>` 空白
- **B2 JavBus ConnectionError 攔截**（`core/scrapers/javbus.py`）：
  - 方案一：`search()` / `get_ids_from_search()` / `_fetch_by_id()` 三處 except 從 `requests.Timeout` 擴為 `(requests.Timeout, requests.ConnectionError)`，統一 re-raise 為 `TimeoutError`
  - 方案二（defense in depth）：`search_by_keyword()` outer call 對 `get_ids_from_search` 加 try / except `(TimeoutError, requests.ConnectionError)` 攔截後回空 list（Codex review P1 修正：原版只 wrap inner loop，外層 call 失敗仍會穿透）；inner loop except 加 `requests.ConnectionError` 兜底

### Refactored

- **R3 女優查詢 LIKE → json_each**（`core/database.py`）：三個 method 改寫，與既有 `count_videos_for_actress_names` 對齊
  - `count_by_actress` → `SELECT COUNT(DISTINCT videos.rowid) FROM videos, json_each(videos.actresses) WHERE json_valid(...) AND json_each.value = ?`
  - `get_videos_by_actress` → 同上 + `SELECT DISTINCT videos.*` + `ORDER BY videos.id`
  - `get_videos_by_actress_names` → 取代原 UNION-of-LIKE，改 `je.value IN (placeholders)` + `SELECT DISTINCT videos.*`（F3 修正：保留同片 primary+alias 兩名時不重複的 UNION 語意）
  - 全部加 `json_valid()` 防 NULL / malformed JSON crash + `except sqlite3.OperationalError` 兼容舊版 SQLite 無 json_each
- CD-60-4：本 branch 不加 generated column + index，視 benchmark 結果 defer 到後續 branch

### Internal

- **R2 `frontend-stack-roles.md` 更新（本地 only）**：HTMX 已於 Phase 47 取消引入，主規範文件頂部加 2026-04-26 banner + HTMX 邊界 / 共存規則 / 程式碼速查三段加 ⚠️ 規劃中標記。檔案落在 gitignored `feature/` 目錄，更動本地保留不進 commit；AC-5 regression check `grep -r "hx-boost\|hx-get\|hx-post\|hx-trigger" web/` 結果為空已確認
- **L1 `core/gallery_generator.py` LEGACY docstring**：1859 行 god file（reverse-engineered from `archives/avlist_py/generator.py`）頂部加 LEGACY 標注 + AI Reviewer 三條明示指示（不拆分 / 不改寫 f-string template / 修改前先 grep `/api/gallery` caller），終止每輪 AI review 重複建議拆分的對話成本（CD-60-5）

### 測試

- 新增測試 31 case：B3 `TestProxyImageSSRF`（13 case，含 Codex round-2 P1 新增的 JavDB CDN `c0.jdbstatic.com` allow case）+ B1 `test_scanner_generate_from_ids.py`（3 case）+ R3 `test_database_actress_queries.py`（10 case）+ B2 `TestConnectionErrorHandling`（5 case，含 Codex round-1 P1 新增的 outer get_ids_from_search failure case）
- 既有測試更新：`test_proxy_image_unknown_domain_no_referer` 斷言 200 → 403 + `mock_get.assert_not_called()`

## [0.8.9] - 2026-05-15

本版是 v0.9 release candidate 前的最後 polish 包（feature/59-onboarding-help-polish），三軌道出貨：**主軸 59a — Onboarding & Help 翻轉**（新手敘事從 Search-first「文件管理員心智」翻為 Scanner-first「相簿心智」：7 步 tutorial 重排 / Help 頁 3 卡 + Next Steps + Tag Alias + power_user 區塊 / README 同步 / 4 locale parity）；**主軸 59b — test_frontend_lint.py 體檢**（2026-05-14 4-agent audit；DELETE 2 + REFACTOR 1 過時 transient-guard pytest class；pre-merge SA-pre-7 /simplify review + transient-guard 生命週期 checklist 引入）；**主軸 59c — E2E 用戶旅程劇本 v2**（24 舊 scenarios 全面審計後改寫為 7 個 User Story 串連 US1-US7，純文字劇本「人類用瀏覽器 / AI 用 Playwright MCP」雙軌可跑；Codex 5 輪 + CDP 實機抽跑驗收）。Bonus：PyWebView 視窗幾何（位置 / 大小）跨重啟持久化。

*This release is the final polish bundle before v0.9 RC (feature/59-onboarding-help-polish). Three tracks: **Track 59a — Onboarding & Help flip** (new-user narrative pivots from Search-first "file-manager mindset" to Scanner-first "photo-album mindset": 7-step tutorial reordered, Help page 3-card + Next Steps + Tag Alias + power_user sections, README sync, 4-locale parity); **Track 59b — test_frontend_lint.py audit** (4-agent audit on 2026-05-14; DELETE 2 + REFACTOR 1 obsolete transient-guard pytest classes; pre-merge SA-pre-7 /simplify review + transient-guard lifecycle checklist); **Track 59c — E2E user-journey playbook v2** (24 old scenarios fully audited and rewritten as 7-User-Story serial US1-US7, plain-text playbook runnable by humans-in-browser and AI-via-Playwright-MCP; verified by 5 rounds of Codex review + live CDP run). Bonus: PyWebView window geometry persists across launches.*

### Added

#### 🎓 59a — Onboarding & Help Scanner-first 翻轉

- **Tutorial step array Scanner-first 重排**：7 步順序翻轉為「加入片庫 → 產生網頁 → NFO 補全 → Showcase → 進階 Search / Settings / Help」，首步聚焦 `#btnSelectFolder` 降低新手認知門檻
- **`default_page` shipped default 改 scanner**：全新安裝預設打開 Scanner 頁（既有用戶 `config.json` 不受影響）
- **Help 頁 4 個新區塊**：「✅ 完成！接下來試試」mini-list / 「想要更多控制？」分流段 / Tag 別名管理段（v0.8.8 A3 補文檔）/ 既有段落補強（A2 alias 展開、B1 dropdown picker、B0 NFO skip）
- **Help 卡片順序對齊 tutorial step 1-4**（CD-59-12）：Scanner → Showcase → 相似探索 → Tag Alias
- **README 補齊**：tagline 翻轉、L25 工作流程順序、Scanner 段補 Tag Alias bullet、新增「Search → Showcase 即時化」段、`GPT-5.4 mini` → `GPT mini`（去版號）
- **4 locale parity**：zh_TW / zh_CN / en / ja 全部翻譯到位，tutorial 7 步 + Help 新區塊（共 ~17 新增 keys × 4 + 23 修值 keys × 4）

#### 🧪 59b — test_frontend_lint.py 體檢

- **pre-merge.md SA-pre-7 步驟**：可選 `/simplify` review skill 引入（建議 diff > 200 行時跑）
- **pre-merge.md transient-guard 生命週期 checklist**：負向 fingerprint 守衛標 `[transient-guard]` 下個 milestone 刪，含 4 條例外保留（安全 / Alpine contract / regression fingerprint / 中文 i18n fingerprint）

#### 🎭 59c — E2E 用戶旅程劇本 v2

- **`tests/e2e/e2e-scenarios.md` 全面改寫**（192 行 → 661 行 → polish 後）：7 個 User Story 串連 US1-US7
  - US1: 新手 Onboarding（11 steps，含 tutorial restart 分支 + Help verify）
  - US2: Search → 整理 → 即時上架（11 steps，file-list 流 searchAll → scrapeAll）
  - US3: Showcase 瀏覽 + Lightbox + 魔杖探索（10 steps，含 ESC 2 段式）
  - US4: 跨語言 Tag Alias 篩選（8 steps）
  - US5: 女優最愛流（8 steps）
  - US6: i18n 完整切換（9 steps）
  - US7: 控制狂工作流（6 steps）
- **Appendix C: Capabilities Smoke**（5 個 curl quick-smoke A1-A5，optional / 不算 milestone 必跑）
- **檔頭含 Playwright MCP 雙 server 用法**（`playwright` headless vs `playwright-cdp` attach）+ Risk-2 cache 黏性 mitigation 指引
- **24 個舊 scenarios 全數歸併 / deprecated**：strikethrough + 一行 reason 保留歷史

#### 🪟 Bonus — PyWebView 視窗幾何持久化

- PyWebView 視窗位置 + 大小跨重啟記憶（commit `20f1788`）；按用戶決定**不揭露**進 docs（CD-59-8）

### Changed

- **Tutorial auto-trigger pathname**：`/search` → `/scanner`（CD-59-3，`/` 保留作首頁 redirect）
- **Help Hero CTA**：`/search?tutorial=restart` → `/scanner?tutorial=restart`（CD-59-5，i18n key 與 value 不動）
- **Help 3 步卡 icon + 文案**：`bi-search` / `bi-list-ul` / `bi-collection-play` → `bi-folder-plus` / `bi-file-earmark-play` / `bi-magic`（i18n key 不動只改 value，CD-59-4）
- **Capabilities `image_display` 升級為多 agent 結構**：原 `codex_app` 單一子物件改為 `agents` map，新增 **Antigravity 2.0 artifact 面板** 指引（artifact_dir hint + 絕對路徑/正斜線/`![]()` 三規則 + carousel 語法實測備註）與 `terminal_cli` fallback；同步 README 把 Google Antigravity 從 IDE 桶移到桌面 App 桶，推薦文案改為「Codex App（對話內嵌）/ Antigravity（artifact 面板）」雙選

### Internal

- **`tests/unit/test_frontend_lint.py` 行數體檢**：DELETE 2 class（`TestSettingsSimplify` / `TestProxyDirectGuard`，transient-guard 生命週期已結束）+ REFACTOR 1 class（`TestSettingsSourceBadge` 的 `primarySource` 正向 assert 併入既有 `TestSettingsESMGuard.test_settings_html_xdata_is_settings`，整 class 刪）；總 test 數 468 → 465
- **`tests/unit/test_frontend_lint.py` 更新 `TestTutorialExpandGuard`**：對齊 Scanner-first step IDs
- **`web/templates/help.html` CRLF → LF**：行尾正規化，消 diff 噪音

### Fixed

- Codex 5 輪 review 修正 e2e-scenarios.md：US2/US7 整理流程 `#btnScrapeAll` 需 `listMode === 'file'` + 進度 selector 改 `#scrapeProgress`（`#batchProgress` 是 searchAll 用）；US5 三處 `/api/favorite-actresses` → `GET /api/actresses/{name}`；US4 tag alias payload `"primary"` → `"primary_name"`；Appendix C A3 補 `file_path` required；A5 `ids/output_dir` → `numbers` + 回傳改 `html_path/video_count`
- Codex 第 4 輪：US2 step 5a 補「先清 search state（`#btnClear` / `clearAll()` → 等 `#emptyState`）」才能 click `#btnFavorite`
- CDP 抽跑驗收：US3 grid 卡片實際 class 是 `.av-card-preview:not(.hero-card)`，原文件誤寫 `.video-card`

## [0.8.8] - 2026-05-13

本版是 v0.9 release candidate 前的 polish 包（feature/58-tag-alias-polish），雙主軸出貨：**主軸 A — alias / 變體一致性**（A1 Scanner 多字母後綴 regex / A2 女優 alias 換頭像本地展開 / A3 跨語言 Tag Alias 系統 / A4 AI tag 揭露端點 / A5 規則式相似探索吃 DB tag_aliases）；**主軸 B — Search→Showcase pipeline 即時化**（B0 最愛資料夾 NFO skip / B1 Scanner dropdown picker + inline 連動狀態 / B2 整理完即時寫 DB + GhostFly 飛到 sidebar Showcase icon）。共通主題是「同一概念有多種表記法」（`アリス = 愛麗絲 = Alice`、`メイド = 女僕`、`abp-321 = abp-321ch`）在系統內各路徑的處理一致化。

*This release is the v0.9 release candidate polish bundle (feature/58-tag-alias-polish). Two tracks: **Track A — alias / variant consistency** (A1 Scanner multi-letter suffix regex, A2 actress alias expand on local photo candidates, A3 cross-language Tag Alias system, A4 AI tag capability, A5 rule-based similar discovery reads DB tag_aliases); **Track B — Search→Showcase pipeline real-time** (B0 favorite folder NFO skip, B1 Scanner dropdown picker + inline link status, B2 in-flow DB upsert + GhostFly fly-to-sidebar animation). Common theme: the same concept rendered multiple ways gets consistent handling across every code path.*

### Added

#### 🏷️ 58 — Tag Alias & Pre-release Polish（A 軌 alias / B 軌 pipeline）

**主軸 A — Alias 一致性**

- **A1 Scanner 檔名 regex 擴張**：`core/gallery_scanner.py` `NUM_PATTERNS` 尾段 `[a-z]` → `[a-z]+`，支援 `abp-321ch.mp4` / `ipzz-789ch.mp4` / `abp-321uncen.mp4` 等多字母後綴。負面 case 不誤抓（`my-vacation-2024` 前綴超過 6 字母上限、`abp-3212024` 無分隔符避免主番號貪婪衝突）
- **A2 女優換頭像本地候選 alias 展開**：`/api/actresses/{name}/photo-candidates` 本地路徑先呼叫 `AliasRepository.resolve(name)` 展開 alias set 再多名查詢，雲端路徑（graphis / gfriends / wiki / minnano）保持只用 primary 名（避免錯人）
- **A3 跨語言 Tag Alias 系統**：
  - 新 `tag_aliases` DB 表（鏡射 `actress_aliases` schema）+ `TagAliasRepository` + 6 條 CRUD 端點（`web/routers/tag_alias.py`，prefix `/api/tag-aliases`，409 衝突回應）
  - Scanner 新「Tag 別名管理」緊湊 chip 牆卡片（多 group 連續排列 `flex-wrap`，組間 `1.5rem` / 組內 `0.25rem` 純 spacing 分組；primary 粉紅 / alias 灰沿用 actress 同色系）+ icon-only `+` 加 alias 按鈕 + AI hint popover（卡片右上 `?` 含 tooltip + window-narrow fallback）
  - Showcase tag chip 點擊 / 搜尋框輸入皆自動展開同義詞（對齊 actress alias `_nameToGroup` 既有 contract，`_tagToGroup` 雙向 case-insensitive map）
  - 既有 actress alias `+ + 別名` 按鈕 bug 順手修正
- **A4 AI Tag 揭露端點**：`GET /api/tags/top?limit=N&min_count=M`（json_each SQL，預設 limit=100 max=500、min_count=2）+ capabilities.json 三條 entry（`tag_alias_crud_read` / `tag_alias_crud_write` 含 `side_effect=true` + `confirmation_required=true` + 風險說明 / `tags_top`）；同義判斷外包給 agent 端 LLM，後端純資料供應
- **A5 SimilarRanker DB 整合**：`core/similar/canonicalize.py` 載入時 lazy merge hardcoded 18 對 + DB partition groups（DB 優先），module-level dict cache；A3 CRUD 4 條寫入端點成功後自動呼叫 `_invalidate_cache()` + `SimilarRanker._instance_cache_invalidate()` → 用戶建 alias 後星座模式立即生效，不需重啟。DB read 失敗 try/except + warning，靜默 fallback 回 hardcoded-only

**主軸 B — Search→Showcase pipeline 即時化**

- **B0 最愛資料夾 NFO skip**：`POST /api/search/filter-files` response `files` 從 `list[str]` → `list[{path, has_nfo}]`，判定為「同目錄 stem case-insensitive + 副檔名 `.nfo` case-insensitive」（不開內容、不查 DB、不看封面）。前端 `searchableFiles` / `failedFiles` 雙 filter 加 `!f.has_nfo` guard，已整理檔顯示灰字「已整理」chip 但不自動 scrape — flat 結構 favorite folder 不再每次重打外部 API
- **B1 Scanner dropdown picker + inline 連動狀態**：Settings「我的最愛資料夾」加「從 Scanner 追蹤資料夾選擇」dropdown 按鈕（純前端 Web browser 也能用）+ inline `text-sm` 連動狀態行（綠字 `✓ 已連動 Scanner` / 黃字 `⚠ 不在追蹤範圍`）。新端點 `GET /api/settings/favorite-scanner-link` + helper `core/settings_link.py:find_matched_directory()` 走 `path_utils.py` + path_mappings 跨平台 WSL/NAS 比對
- **B2 Search 整理完即時寫 DB + GhostFly 完成動畫**：`organize_file()` 成功後 `core/db_inflow.py:try_inflow_upsert()` 依 `find_matched_directory()` 判斷目標路徑，若在 Scanner `gallery.directories` 範圍內 → `VideoScanner.scan_file()` → `VideoRepository.upsert(video)`（path file:/// URI 為冪等 key）。response 加 `db_sync_status` 三態 enum（`synced` / `not_linked` / `failed`），前端 `synced` → `GhostFly.playToIcon()` 封面從來源飛到 `#sidebar-showcase-link` 並 `pulse-once`，`not_linked` / `failed` → 對應 toast。失敗 try/except 不影響 organize 結果

### Changed

- **GhostFly API**：新增 `playToIcon(fromEl, toEl, options)` method（`web/static/js/shared/ghost-fly.js`），支援任意 element 為終點（B2 sidebar icon 飛行用），既有 `playGridToLightbox` / `playLightboxToGrid` 不動
- **Scanner alias 區「+ 別名」按鈕**：actress alias 既有 icon `+` 與文字 `+ 別名` 渲染重複加號 bug 修正為單 `+`；tag alias 區直接採 icon-only `+` 配 aria-label
- **規則式相似探索 canonicalize**：從 hardcoded-only → hardcoded + DB partition map merge，hardcoded 18 對永久保留作 offline fallback 不污染 DB

### Fixed

- B0/B1/B2 Codex review 一輪：path_utils 合規 + WSL mapping + .nfo 資料夾誤判（誤把資料夾內含 `.nfo` 視為單檔 has_nfo）
- B1 Scanner dropdown trigger 點開立刻被自身 `@click.outside` 關閉 → 加 `@click.stop`
- A5 Codex review：SimilarRanker 既有 instance cache 同步 invalidate（避免 ranker 拿舊 alias map）+ alias key 小寫正規化對齊比對端
- A3-3 Codex P2/P3：(?) tooltip 鍵盤 enter/space 冒泡到 header 觸發 collapse + narrow-screen popover 向右 overflow
- A3 Tag 別名管理 (?) tooltip 被 `space-between` 推到中間 → `margin-right: auto` 貼齊標題
- B1 dropdown 背景透明 → inline style token 名稱錯誤（`--color-bg-surface` 等 5 個變數查無），對齊 design-system `.toolbar-dropdown` 標準 token
- B2 scrapeAll 漏接 `db_sync_status` + 起飛點寫死 `#resultCover` 在 grid/file-list 視角 width=0 → 抽 `_handleDbSyncFeedback` 共用 helper + `_findDbSyncSourceEl` 五級 fallback 確保任何視角都有可見起飛點

### Internal

- 移除 `tests/unit/test_frontend_lint.py` 兩個違反 CLAUDE.md「Lint 守衛規則」的 pytest class（`TestShowcaseTagAliasGuard` / `TestScannerTagAliasGuard`）— 對齊 v0.8.5 確立的 eslint/stylelint 守衛遷移政策

## [0.8.7] - 2026-05-10

本版拔除 v0.8.6「以圖搜圖（CLIP Visual Search, Beta）」全部 ML 引擎，改為純規則式 metadata 多訊號相似搜尋。
無需下載模型、無外部依賴、無 opt-in flow，Lightbox 魔杖按鈕開箱即用。主 ZIP 從 271MB 回 ~43MB baseline。

*This release rips out the v0.8.6 "Visual Search (CLIP Beta)" ML engine and replaces it with rule-based 
metadata multi-signal similarity. No model download, no external deps, no opt-in flow — Lightbox magic 
wand works out of the box. Main ZIP returns from 271MB to ~43MB baseline.*

### Removed

#### ⚠️ BREAKING — v0.8.6 CLIP 視覺搜尋下架（CLIP Visual Search Removed）
- 移除 `core/clip/` 整目錄（CLIPProvider / LocalONNXProvider / ClipIndexer / 影像 preprocessing / 模型下載 / cosine ranking）
- 移除 `web/routers/clip.py` + `web/routers/clip_lifecycle.py`（4 個 lifecycle endpoints + similar-covers 舊實作）
- 移除 ML 依賴：`onnxruntime` / `numpy` / `huggingface_hub` / `hf_xet`（連帶 scipy 等傳遞依賴）
- 移除 Settings「以圖搜圖（Beta）」opt-in flow（toggle / status box / disable modal / popover；57c 已拔 UI，57d 拔後端）
- 移除 11 個純後端 CLIP 測試檔（~2700 行）
- 主 ZIP 體積從 271MB 回 ~43MB baseline

*BREAKING: removes core/clip/ entire module + clip routers + ML deps (onnxruntime/numpy/huggingface_hub/hf_xet)
+ Settings opt-in UI + 11 backend test files (~2700 lines). Main ZIP: 271MB → ~43MB.*

### Added
#### 🔍 57 — 相似影片探索（規則式 / Rule-Based Similar Discovery）
（57a/57b/57c 成果在此一併歸檔；57d 主要是物理拔除 + ZIP 體積驗收）
- 純規則式相似度排序器 `core/similar/`：IDF-weighted tag Jaccard 主訊號 + 系列 / 片商 / 年份 / 片長 / cast 桶多訊號加成 + MMR diversity rerank（λ=0.7）
- hardcoded 同義對表（~30 條）+ stopword 列表（~14 條），v0.8.8 後可透過 tag_aliases UI 動態維護
- Lightbox 魔杖按鈕**直接可用**，無需 Settings 啟用，無需下載模型
- API contract `GET /api/similar-covers/by-number/{number}` / `GET /api/similar-covers/{video_id}` 完全不變（前端零改動）

*Added: rule-based similarity ranker (`core/similar/`) with IDF-weighted Jaccard + multi-signal scoring + MMR diversity. 
Hardcoded synonym map (~30 pairs) + stopwords (~14). Lightbox magic wand works without enable gate. API contract preserved.*

### Changed
- 探索星空動畫 UI 資產（56b/56c）100% 保留（CSS class `.clip-*` → `.similar-*`，state factory `state-clip.js` → `state-similar.js`，i18n key `clip_mode.*` → `similar_mode.*`）— 57c 完成

### Fixed
- N/A（57 系列為 feature replacement 非 bug fix）

## [0.8.6] - 2026-05-09

本版完整出貨「以圖搜圖（Beta）」（feature/56）— OpenAver 第一個視覺搜尋功能。在 Showcase Lightbox 加魔杖按鈕，點下去進入「探索星空」模式：原封面飛中央變主圖、12 顆星辰繞主圖排列、香檳金星線從中央延伸到各星辰，點任一顆即「鑽入」變新主圖無限探索。技術層用 OpenAI CLIP 模型把每張封面轉成 512 維特徵向量、cosine similarity 排序，封面進入 CLIP 前自動裁切右半邊（避開左標題雜訊），對「相同女優」自動降權確保結果多樣性。預設關閉，Settings opt-in 後下載 80MB INT8 模型,全程本地推論不上傳。AI agent 可透過新揭露的 `similar_covers_by_number` 端點找視覺相似番。

*This release ships visual search ("以圖搜圖", Beta) feature 56 — OpenAver's first vision-based discovery: click the magic wand in Lightbox → 12 cover stars surround the main image with champagne-gold rails from center → click any star to "dive in" and explore endlessly. Backed by OpenAI CLIP 512-d embeddings, cosine similarity, right-half cover crop (avoids left-side title noise), and same-actress diversity penalty. Opt-in (off by default); 80MB INT8 model downloaded locally on enable. AI agents can discover visually similar videos via the newly-exposed `similar_covers_by_number` capability.*

### Added

#### 🪄 56 — 以圖搜圖（CLIP Visual Search, Beta）

- **56a 引擎基座**：CLIPProvider ABC + LocalONNXProvider + 模型下載 sha256 校驗 + 影像 preprocessing（右半裁切 + CLIP normalize）+ 批次索引 runner（斷點續傳）+ `GET /api/similar-covers/by-number/{number}` 端點（cosine + diversity penalty −0.15）+ DB schema migration（`clip_embedding` BLOB + `clip_model_id` 欄位 + 模型版本一致性檢查）
- **56b 探索星空 Lab**：sandbox `/clip-lab`（後沉澱到 `/motion-lab` Constellation tab）— 12 anchor pool + 隨機抽 8 + Rails 三態（persist/enter/exit）+ Slip-through continuous mode + Hover dim + Star Field dust + Hover Reveal corridor stars + Phase Acknowledge keystone pulse；GSAP DrawSVGPlugin + CustomEase（fluent-decel）；prefers-reduced-motion 直接呈現終態
- **56c Showcase 整合**：Lightbox 左上角魔杖按鈕 + 0.4s 香檳金光帶預演（左→右橫掃 + 左半 darken / 右半 brighten）+ GhostFly cropMode 進場（封面飛中央變主圖、只呈現右半邊，CSS `aspect-ratio` + `object-position: right center` 零成本裁切）+ slip-through 鑽入新主圖無限探索；4 路徑退出（X / 背景 / 主圖非 play 區 / ESC）；手機（< 768px）降級為主圖下方 grid 顯示前 4 張（Alpine x-collapse）
- **56d 後端基礎**：`ClipConfig` schema（`enabled: bool=False`, `model_path`）+ 4 lifecycle endpoints（`POST /api/clip/enable` SSE 串流下載+索引進度 / `POST /api/clip/disable` 刪檔+清 DB / `GET /api/clip/status` 跨頁返回快照 / `POST /api/clip/test-inference`）+ Scanner 隱性增量索引（fire-and-forget asyncio task，無 UI 提示對齊「不打擾」氣氛）+ 啟動自癒（model_id 不一致自動清空舊 embedding）
- **56e Settings UI**：圖像策略區塊新增「以圖搜圖（Beta）」開關（紅字 Beta badge + popover 說明）+ 三階段 status box（download → indexing → ready）+ SSE 進度推 + 跨頁返回 polling 還原進度 + DB 刪除等級紅色警告 modal 關閉確認（明示刪 80MB 模型 + 清空所有 CLIP 索引不可復原）+ Showcase magic button SSR gate（`window.__CLIP_ENABLED__`，未啟用完全隱藏入口）
- **56f 收尾**：Settings ready 後測試推論按鈕（toast 顯示耗時 ms）+ Capabilities 揭露 `similar_covers_by_number` / `similar_covers` 兩 read-only 端點給 AI agent（4 個 lifecycle endpoint 不揭露對齊「純 UI flow 不揭露」原則）+ Help 頁「以圖搜圖（Beta）」card（原理 / 使用方式 / Beta 限制 / 啟用關閉 4 段）+ 17 `help.clip.*` zh_TW i18n key（其他 locale milestone 補齊）

#### 📚 README

- README.md 新增「以圖搜圖（Beta）」段落（與 AI 翻譯同層級），3 bullet 說明 OpenAI CLIP 512 維向量分析封面 + Lightbox 探索星空操作流程 + opt-in 80MB 模型本地推論

### Changed

#### 🛠️ Lint 守衛遷移

- `TestClipStageGuard.test_no_filter_brightness_in_clip_files` 從 pytest 遷移到 eslint `no-restricted-syntax`（新增 `SEL_FILTER_BRIGHTNESS`，scoped to `state-clip.js` + `constellation-host.js`），對齊 CLAUDE.md「Lint 守衛規則」

### Internal

- 已知 lint-guard exception：`test_no_slot_icon_overlay_in_templates` 暫保留 pytest（HTML linter 工具盲區 — stylelint 不讀 HTML、eslint 原生不處理；待後續 PR 評估 `@html-eslint/eslint-plugin` 後遷移）
- 後端 `TEST_IMAGE_PATH` 從 `sc-1.jpg`（不存在）修正為 `sone-103.jpg`（demo 目錄實際存在的圖）

## [0.8.5] - 2026-05-03

本版治好 frontend_lint pytest 膨脹（feature/55）。一個月內測試套件從 1634 → 2976 暴增 +82%，新增的 1342 tests 幾乎全來自兩個 `test_frontend_lint.py`，根因是「沒 eslint / stylelint 可用，開發者只能拿 pytest 守 lint 規則」。本版補上工具鏈正確層：eslint flat config 守 JS 語法（`no-alert` / `no-console` / `no-restricted-syntax`）、stylelint 守 CSS token、可折疊的跨檔 contract 用 method folding 折疊、死碼測試直接刪除，最後加四層防膨脹機制（lint config + AGENTS.md 邊界宣告 + CLAUDE.md 規則 + pre-merge SA-pre-6 偵測）讓這種膨脹未來無法復發。frontend_lint 兩檔合計 905 → 450 tests（−50%），用戶完全無感知。

*This release fixes the frontend_lint pytest bloat (feature/55). The test suite ballooned from 1634 → 2976 (+82%) in one month because there was no eslint/stylelint to enforce JS/CSS lint rules — developers used pytest as a substitute. This release introduces the correct tooling layer (eslint flat config + stylelint config), folds cross-file contract tests via method folding, deletes dead-code guards, and locks in four anti-bloat mechanisms so this class of bloat cannot recur. The two `test_frontend_lint.py` files go from 905 → 450 tests (−50%) with zero user-facing changes.*

### Changed

#### 🛠️ 55 — Lint Toolchain & Test Deflation

- **55a 死碼守衛刪除**：移除 10 個 D 類 class（41 tests）— 守的程式碼 path 已永久消失（`bridge.js` / `showcase/core.js` 等已刪除，guard 自身成為死碼）
- **55b stylelint toolchain**：新建 `package.json` + `stylelint.config.js`（extends `stylelint-config-standard`），引入 `color-no-hex` / `declaration-property-value-disallowed-list`（transition / filter / blur / border-radius / box-shadow）/ `selector-disallowed-list`，移除 B 類 ~25 個 CSS hardcoded 守衛 tests；HTML inline style scan 部分降為 C 類保留至 55d
- **55c eslint flat config**：新建 `eslint.config.mjs`（ESLint 9 flat config，三段不重疊 file glob 結構防 rule 覆蓋），規則含 `no-alert` 全域 / `no-console` search pages 限定 / `no-restricted-syntax` `document.createElement` state mixins 限定 + `showModal` search state 限定 + `window.confirm` 全域；移除 13 個 A 類 tests；4 處合法 inline `// eslint-disable-next-line` 含理由 + 日期（CD-55-7 格式）
- **55d C 類 method folding**：~79 個跨檔 contract 守衛 class（543 tests）依 CD-55-3 風格折疊為 ~119 個 method（for-loop + fail message 含被測字串），不使用 `@pytest.mark.parametrize`（會讓 collect 數不降）；E 類保護清單（ESM / GSAP / lifecycle / cross-file API 共 ~285 tests）完全不動
- **55e 根目錄檔案消滅**：搬移 48 個 class 從 `tests/test_frontend_lint.py` → `tests/unit/test_frontend_lint.py`，刪除根目錄檔案（修正 CLAUDE.md「測試分層規則」違規）；搬移過程修正 2 個潛在 bug（class-level `PROJECT_ROOT` 路徑誤算 + helper 缺 return）
- **55f 四層防膨脹機制**：M1 lint config（55b/c 已建）/ M2 AGENTS.md 加 `Out of scope` + `Test bloat policy` 兩段（明示 ESLint / Stylelint 各自實際 file scope + 仍由 pytest 守的清單）/ M3 CLAUDE.md 加「Lint 守衛規則」段 / M4 pre-merge.md SA-pre-3 加 `npm run lint` + SA-pre-6 加 lint-guard 偵測規則

### 為什麼不繼續優化其他測試

55 系列收尾後曾考慮開 feature/56-test-deflation-runtime 處理運行時代碼測試（`test_path_utils.py` / `test_collection_sql.py` / `test_organizer.py` 等）的重複熱點。Sonnet 對 `tests/unit/` 全範圍做完 read-only audit 後，實際可削僅 ~78 tests（low + medium 風險），未達 200 tests 門檻 → **放棄計畫**。理由：(1) runtime code 測試與 lint guard 風險屬性不同，刪錯會掩蓋真實 bug，需逐 test 判讀，邊際效益低；(2) 剩餘重複多為「security boundary 鏡射」「format 變數展開」這類，folding 後診斷可讀性下降反而是負價值；(3) 全套 2406 passed 已是健康基準，不為刪而刪。日後若特定模組重構觸發再做。

## [0.8.4] - 2026-05-03

本版完成全站前端 JS 的 ESM 模組化（feature/54）。把 showcase/core.js（2725 行）、scanner.js（1546 行）、settings.js（972 行）等巨型單檔，以及 search 的 window.SearchStateMixin_* 全域模式，全部遷移到原生 ESM（`import/export`）。Import Maps 統一路徑別名，每個頁面有獨立的 `main.js` 入口，依賴關係從隱性約定變成明確的 import 語句。對用戶完全無感知——功能、動畫、資料行為完全不變。

*This release completes the frontend ESM migration (feature/54). The monolithic showcase/core.js (2725 lines), scanner.js (1546 lines), settings.js (972 lines) and the search window.SearchStateMixin_* globals are all migrated to native ESM (import/export) with Import Maps path aliases and per-page main.js entry points. Zero user-facing changes.*

### Changed

#### 🏗️ 54 — 全站前端 ESM 模組化

- **54a ESM 基礎建設**：base.html 加 Import Maps（`@/shared/`、`@/components/`、`@/showcase/` 等 6 個路徑別名）+ `{% block pre_alpine_module %}` slot；7 個共用工具（ghost-fly、burst-picker、motion-adapter、path-utils、page-lifecycle、motion-prefs）加 ESM export + window 橋接（過渡期向後相容）
- **54d Settings 拆解**：settings.js（972 行）→ state-config / state-providers / state-ui + main.js；settings.js 刪除
- **54c Scanner 拆解**：scanner.js（1546 行）→ state-scan / state-nfo / state-alias / state-batch + main.js；scanner.js 刪除
- **54b Showcase 拆解**：core.js（2725 行）→ state-base / state-videos / state-actress / state-lightbox + main.js；core.js 刪除；descriptor-preserving mergeState 保留 getter
- **54e Search 遷移**：8 個 `window.SearchStateMixin_*` 全域模式 → ESM `export function`；新增 `search/main.js`（descriptor-preserving mergeState）；state/index.js 刪除

## [0.8.3] - 2026-05-02

本版帶來兩個獨立升級包：53a 補齊四個 Alpine 官方插件（焦點鎖、切頁狀態保留、平滑展開、指向交叉偵測），同時修正 showcase 切頁殘留動畫鬼影；53b 新增全站通知中心（sidebar 鈴鐺 + 抽屜），讓 Scanner 掃描與批次補完的開始/完成/失敗事件即時可見，從任何頁面甚至跨裝置都能查閱，不再需要停在 Scanner 頁面等待。

*This release includes two upgrade packs: 53a adds four official Alpine plugins (focus trap, persistent state, smooth collapse, intersection observer) and fixes animation ghost on page leave; 53b adds a global Notification Center (sidebar bell + drawer) for real-time visibility of Scanner and batch-enrich events across all pages and devices.*

### Added

#### 🔔 53b — 通知中心（Notification Center）
- **sidebar 鈴鐺 + 通知抽屜**：help 上方常駐鈴鐺 icon，有未讀事件時亮彩色點（資訊藍 / 成功綠 / 警告黃 / 錯誤紅），點開抽屜從右側滑出顯示最近 10 筆事件記錄
- **後端 buffer**：deque maxlen=10，RLock thread-safe，`emit_notification()` helper 供任意 router 呼叫
- **Scanner / Batch-enrich 接入**：掃描開始（info）/ 完成（success）/ 部分失敗（warn）/ 中斷（error）四種狀態通知；批次補完同樣三段接入
- **跨裝置一致**：通知 buffer 存在後端程序記憶體，電腦跑掃描、手機打開也能看到同一份記錄
- **3 個 REST 端點**：GET /api/notifications（查詢）/ POST /api/notifications/read（標已讀）/ DELETE /api/notifications（清空）
- **i18n 14 個 notif.* key**（zh_TW.json）；其他語系 milestone 補齊
- **Capabilities 3 個新 tool**：get_notifications / mark_notifications_read / clear_notifications（含 side_effect / confirmation_required 安全標記）
- **Unit test 5 + Integration test 6**：buffer 邏輯與 API 端點完整覆蓋

#### 🔌 53a — Alpine 輕量升級包
- **Alpine 釘版 3.15.12**：persist / collapse / focus / intersect / anchor 5 個插件統一版本，不再使用 3.x.x 浮動版
- **showcase Lightbox 焦點鎖**（x-trap.inert）：Lightbox 開啟時 Tab 鍵只在燈箱內循環，背景對螢幕閱讀器標記 aria-hidden
- **showcase_state 改 $persist**：篩選條件、排序、模式切頁後自動保留（升級後舊的 localStorage 值仍可讀取）
- **settings 摺疊展開動畫**（x-collapse）：進階刮削設定 / 進階顯示選項展開收合從硬切換改為平滑高度動畫
- **scanner 女優別名管理**：header 整列可點擊展開（不只圖示）

### Fixed

- **showcase 切頁不殘留鬼影**：頁面離開時補呼叫 `_resetPicker()` + `GhostFly.cleanupStaleGhosts()`，快速切頁後不出現浮動圖片殘像
- **Ghost-fly lightbox 關閉疊圖**：關閉反向動畫期間隱藏 lightbox 大圖，避免新舊動畫疊圖
- **Photo picker burst 修正**：hover 凍結 + desktop layout reflow + 改 method B defer-burst（partial 置中 + loading 完整覆蓋）
- **scanner 通知 early return 修正**：directories 未設定時 early return 不再殘留孤兒 "掃描開始" 通知
- **鈴鐺 icon 對齊**：nav-link--bell 改用 -webkit-fill-available 消除 button UA fit-content 造成的 2.5px 右偏

## [0.8.2] - 2026-04-29

本版把 ui-conventions 套用到剩餘 5 頁（scanner / settings / help / design-system / motion-lab），並把幾條與「軟體靈魂」對不上的舊互動清掉：原生 `confirm()` / `alert()` 替換成風格一致的 fluent-modal 與 toast，showcase toolbar per-page 下拉移除（Settings 為唯一真理來源）。對使用者而言視覺更整齊、確認對話更貼近主視覺、複製失敗時用得到完整訊息（不再只看到截斷 500 字）。

*This release applies ui-conventions to the remaining 5 utility/demo pages and cleans up legacy interactions (native confirm/alert → fluent-modal/toast). No user-facing feature changes — only consistency, polish, and accessibility improvements.*

### Added

#### 🎯 52.1 — 5 頁靜態 UI 修齊（Phase 1）
- scanner / settings / help / design-system / motion-lab 五頁 §1-§4 + §6 5 檢查點修齊（commits 3ce4c7f / ba804bf / 26131be / c0185a7 / 20713ac / 95b5e0a / a50014f / 21be2b6 / 19e9725 / 9eb64db / 8a94ba7 / ca8952a / a2ae5f8 / 6e4e617 / 93c0a1e / 6e4e584 / 40de310）
- design-system 新增 §1 pill 5 類白名單 / §2 三階 token / §3 overlay 5 swatch / §4 spacing 三層 / §6 5 檢查點 pass-fail demo（commits 6e4e617 / 93c0a1e / 6e4e584）
- settings.css §6 .input / .select / settings-header 沿用 plan-50 P1b 完整規格（commits 26131be / c0185a7 / 95b5e0a）
- motion_lab.html §1 blur / §2 shadow / §3 color & radius / §5 transition token 化（commits 5ba0285 / 35d141e / 7f44a76 / 7adbfec / 29cf36e / 060c5a5）
- TestSettingsCssHardcoded / TestHelpCssHardcoded / TestDesignSystemCssHardcoded / TestMotionLabHtmlHardcoded 4 條 lint guard

#### 🎯 52.2 — Motion Lab 動畫 demo 補齊（Phase 2）
- 新增 §5 三角色 ease 並排 demo（fluent / fluent-decel / fluent-accel）+ T2.1 範圍 ease 殘留清（commit 1fd4fd4）
- 新增 §5 Duration 三 bucket demo（fast 167ms / medium 333ms / emphasis 500ms 並排對照）+ T2.2 範圍 ease 殘留清（commit 41b7751）
- 新增 §5 Special Motion 白名單 demo（Burst / Floating Hearts / showcaseSettle / SourcePulse）+ T2.3 範圍 ease 殘留清（commit 5dbcc82）

#### 🎯 52.3 — Soul-Alignment Cleanup（Phase 3）
- Showcase toolbar per-page 下拉移除，Settings 接管為唯一真理來源（既有 localStorage 殘留 fallback 到 settings default，無 migration）(commit 6201b91)
- `removeActress()` / `resetConfig()` / `deleteAliasGroup()` 三處原生 `confirm()` 改 fluent-modal + i18n 4 keys 各一組（commits 4b784fe / ee37b37 / 492d650）
- 15 處 `alert()` 改 showToast + i18n 14 keys（scanner ×8 含 1 處 fluent-modal `<pre>` 可選取 dump 取代 truncate 500 字 / settings ×1 / search file-list ×5 / search result-card ×1）(commit f2d2b67)

### Fixed
- T3.2 codex P2：`items_per_page` 預設值用 `??` 而非 `||`，保留合法 numeric 0（避免被 falsy 0 吞掉）(commit 0d195bc)
- T3.6 codex P2：scanner.js copyLogs / copyOutputPath 兩處 `navigator.clipboard.writeText` 補 availability guard，clipboard undefined 時 fallback 才會觸發（之前 sync TypeError 跳過 .catch chain，用戶以為「複製成功」）(commit 37db4bd)
- T3.7：result-card.js / showcase/core.js `openLocal()` 同類 pre-existing bug sweep — 三元 guard 把 sync TypeError 收斂為 `Promise.resolve(false)` 重用既有 fail UX；新增通用 lint guard 防未來新檔再犯（commit 397a412）
- Phase 1 codex 5 條 finding（commit 783c6c4）
- Phase 2 codex motion_lab.html `--accent-primary` / `--accent-secondary` 統一 + skip-note 文案（commit 968ce51）

## [0.8.1] - 2026-04-29

本版把 Phase 50 在 Showcase 影片模式驗證過的 ui-conventions（Fluent 2 token / 白名單 / ease 三角色 / §6 5 檢查點）擴展到 Showcase 女優模式 + Search 整頁，並把 lightbox 開門動畫從兩邊各自實作整併到 `shared/ghost-fly.js` 共用。對使用者而言三個主要 surface 視覺與動畫節奏接續，沒有功能變化。

*This release applies the ui-conventions validated in Phase 50 (Showcase video mode) to Showcase actress mode and the Search page, and consolidates the lightbox-open animation into a shared `ghost-fly.js` implementation. No user-facing feature changes.*

### Added

#### 🎯 51.1 — Showcase 女優模式 conventions 套用（Phase 1）
- 女優模式擴散感受確認 — Phase 50 共用動畫函式 default ease 已對齊三角色，女優 grid 進場 / 排序 / 篩選 / 模式切換感受可接受 (commit 891060a)
- showcase.css 女優段靜態修齊 — actress card / lightbox / picker overlay / picker card 等 ~14 違規 row 對齊 §1-§4 + §5 CSS transition token 化 (commit d2a2de6)
- `playHeroCardAppear` ease 試改 fluent-decel（power2.out → fluent-decel，duration 0.3s 保留 hardcoded 白名單）(commit 9dcff7a)
- `_fadeMetadataPanel` 改三角色 fluent + DURATION.fast（女優 lightbox metadata 淡入淡出）(commit a85f54b)
- §6 5 檢查點：女優 picker-refresh-btn radius / stroke / focus 對齊（非 DaisyUI .btn 但需 §6 精神）(commit 11ac5e8)

#### 🎯 51.2 — Search 頁靜態修齊（Phase 2）
- input.css 新增 `--overlay-letterbox` token + `--overlay-badge` token（§3 角色色白名單擴張）(commits 0080118 / 6224b08)
- search.css §1/§2/§3 靜態修齊 — hardcoded blur / shadow / radius / color 全 token 化（~50 違規 row）(commit 41f2a5b)
- search.css §4 spacing 三層修齊 — 8pt layout 3 處 / 6px optical 註記 2 處 / stroke 放行 (commit 89d52b6)
- §6 5 檢查點：search 頁 .btn / .input / .dropdown / .spotlight-search 5 檢查點全通過（沿 Phase 50 T5 完整實作規格） (commit 5dd7a61)

#### 🎯 51.3 — Search GSAP 系統 ease 對齊（Phase 3）
- §5 白名單預登記：Staging Card `back.out(1.4)` + playOrganizeSuccess checkmark `back.out(1.7)` + playOrganizeFail shake `power1.inOut 0.08s` 三招牌動畫保留不動
- `playDetailEntry` cover + info 段 → fluent-decel + DURATION.emphasis (commit 0c351c6)
- `playGridToDetail` / `playDetailToGrid` ghost 飛行 → fluent (standard) (commit 941bf3c)
- `playDetailToGrid` settle pulse → fluent（0.18s 加 §5 hardcoded duration 白名單）(commit ce80424)
- `playSlideIn` / `playHeroRemove` / `playGridSettle duration` / `playLightboxSwitch` / `playSampleGallerySwitch` / `playProgressUpdate` / `playAppendCascade` / `playGridFadeIn` 對齊三角色（commits e4b8d2f / 3505e36 / 3190d9a / 9bb2931 / cbf160c / ec7b4c1 / 926faf4 / a304752）
- `playCoverSwap` → fluent（0.15s 加白名單，意圖即「快速替換無感切換」）(commit 1c0c1b9)
- `playMiniBurst` → fluent-decel 試改（back.out(1.2) → decel；感受待 dev server 驗證）(commit c3a4eb4)
- `playOrganizeSuccess` row green flash → fluent-accel（離場淡出，0.8s 加白名單沿 showcaseSettle 模式）(commit 70d7f20)

#### 🎯 51.4 — Lightbox 共用化（Phase 4）
- 新增 `GhostFly.playLightboxOpen` 共用實作於 `shared/ghost-fly.js`，採 showcase 版完整 cleanup 契約（onComplete + onInterrupt 各對 content/coverImg 做 clearProps，防連點殘留 stutter）(commit 8bf9158)
- `ShowcaseAnimations.playLightboxOpen` 改 delegate（傳 `timelineId: 'showcaseLightboxOpen'` 維持 killLightboxAnimations 行為） (commit f3cbafe)
- `SearchAnimations.playLightboxOpen` 改 delegate（不傳 timelineId 沿用預設 `'lightboxOpen'` 維持 grid-mode.js kill 路徑；search 連點 interrupt 行為從 silent 改為 clearProps 正向改善）(commit 35ab2f0)
- 兩 caller 各刪 ~73 / ~56 行重複碼，淨減 ~70 行 → lightbox 開門動畫 single source of truth

### Fixed
- T2.4 codex P2：tag 編輯 inline btn fallback 補完（.tag-add-btn dashed restore + .tag-confirm/.tag-cancel）(commit d5940f8)
- T3.13/T3.15 codex P3：同步 Phase 3 改動後過時 JSDoc default 註解 (commit f341398)
- T4 codex P3：delegate guard 改 `typeof window.GhostFly?.playLightboxOpen === 'function'` — 防 cache invalidation 場景（舊 cached ghost-fly.js + 新 page animations.js）下舊 GhostFly object 缺新 method 導致 TypeError 炸掉 lightbox open (commit 5e4dc63)

## [0.8.0] - 2026-04-28

本版聚焦在 Showcase 影片模式的視覺語言統一（Phase 50 Charter Pilot）。把 Fluent 2 的設計規範完整套用到 token、白名單、ease 三角色、§6 5 檢查點，並把 visual-charter 從一次性提案升級為正式的 ui-conventions 工作流文件，之後新做頁面有規範可循。對使用者而言介面更一致、動畫節奏更自然，沒有功能變化。

*This release unifies the visual language across Showcase video mode (Phase 50 Charter Pilot) by applying Fluent 2 conventions to tokens, allow-lists, and the three-role ease system. No user-facing feature changes.*

### Added

#### 🎯 50.1 — Phase 1 靜態修齊（charter §1–§4 + §6）
- 新增 Fluent token 一階對應（blur / shadow / radius / spacing / overlay color），整個 Showcase 視覺基準對齊 (commit 30ce8f2)
- Blur / Shadow 三階分明，弱 / 中 / 強層級不再亂跳 (commit 6685c49)
- Radius 改用 token，pill 形狀走白名單統一寫法 (commit 8139716)
- Spacing 三層分明，6px 個案保留並逐個審判，避免一刀切 (commit 8b1c977)
- Overlay 顏色 4 階 token 化，hover / active / disabled 不再各自為政 (commit e04812e)
- DaisyUI 的 .btn / .input 在 Showcase 範圍內加 scoped Fluent 覆寫，第三方元件不污染全域 (commit 4afdc35)

#### 🎯 50.2 — Phase 2 動畫修齊（charter §5 ease 三角色）
- 新增 Fluent CustomEase 三角色（standard / decel / accel）並在 GSAP 註冊，動畫節奏統一語彙 (commit 9579801)
- motion-adapter.js 5 處預設 ease 全部換成三角色 (commit 3b58dd8)
- 進場動畫（playEntry stagger）改用 fluent-decel，視覺更自然 (commit 5c89afc)
- 排序動畫（playFlipReorder）改用 fluent，標準互動節奏 (commit 7cfc4b6)
- 篩選翻轉（playFlipFilter）三段拆 fluent / decel / accel (commit 9fb93b9)
- 模式切換（playModeCrossfade）拆 fluent-accel + fluent-decel，淡出淡入手感對稱 (commit 06f2129)
- Lightbox 開啟（playLightboxOpen）三段對齊 fluent-decel (commit 5c20842)
- LightboxSwitch + SampleGallerySwitch 切換動畫換 fluent (commit 8ee3d56)
- 容器淡入 / 來源 pulse（playContainerFadeIn / playSourcePulse）改 fluent (commit ef02b5b)
- motion 模組新增 DURATION 三角色常數，業務 caller 全面套用，硬編碼 ms 從業務層消失 (commit e6586c6)
- showcase.css 7 處 transition 硬編碼換成 fluent token (commit 9b286b1)

### Fixed
- 檔名截斷後尾端 `.` 在 Windows NTFS 被靜默剝除導致 `shutil.move` 失敗（#31），新增 win32-only 截斷後 rstrip helper，Mac / Linux / WSL ext4 行為不變 (commit f718f8f)
- Search lightbox 在 Showcase 啟用時定位錯誤，回退 body.fluent-canvas 的 backdrop-filter 改寫 (commit de57171)
- Lightbox backdrop 30px 模糊太重，UX 仲裁後降到 12px（覆蓋 charter §2 字面值）(commit e586a56)
- playLightboxOpen 殘留動畫片段清理，加進 charter §5 white-list (commit 6f1d39e)
- Codex review v3 Phase 1 P1a / P1b / P2 收斂 — Token 命名一致性、tailwind.css 隔離、白名單覆蓋邊界 (commit b37d5df)

### Chore
- tailwind.css 一次性重編，把 Phase 50 之前累積的 source drift（alias UI / .stack / .invisible / DaisyUI 5.5.17 升級殘留）帶入，避免污染 Phase 50 token diff (commit 197f9a0)

## [0.7.8] - 2026-04-26

本版聚焦在 Showcase 女優模式的全方位打磨：補齊模式切換動畫、新增女優照片更換功能（含 Physics2D burst picker）、Picker overlay 改為純 CSS viewport-anchored 全裝置適配、以及 Actress Lightbox ghost-fly 補全與 Footer 視覺重設計。

### Added

#### ✨ 49a — 女優模式動畫與燈箱強化
- **模式切換補 fade-out 動畫**：切換影片↔女優模式時加入淡出動畫，搭配 `prefers-reduced-motion` 守衛，動效關閉時直接切換不閃爍
- **Actress 燈箱 video_count 前置顯示**：女優燈箱第二行直接顯示出演影片數，不需展開才看到
- **Alias 即時查詢 + tooltip**：女優燈箱別名欄位即時從後端拉取並顯示 tooltip，不再需要重新整理
- **女優→影片跨模式 ghost-fly**：從女優燈箱切回影片時，封面執行 ghost fly 飛行動畫，降級環境自動跳過
- **底部 Footer 三段式整合**：Footer 重構為左段（資料庫統計）+ 中段（搜尋詞）+ 右段（版本）三段式佈局

#### ✨ 49b — 女優照片更換功能
- **Actress 燈箱換照片入口**：燈箱新增更換照片按鈕，四語系支援（繁中/簡中/日文/英文）
- **Physics2D Burst 動畫 picker**：點擊換照後彈出 burst 動畫 picker，6 張候選卡 back.out 單段彈出、settle tween + race token 雙重防抖、單行 nowrap 不換行
- **後端 SSE photo-candidates 端點**：即時串流回傳候選照片，修正 SSE candidate handler race bug（中間候選卡不顯示）
- **後端 `POST /api/actresses/{name}/photo`**：換照片 + 裁切（crop）一步到位
- **BurstPicker 抽共用模組**：picker 邏輯提取為可複用模組 `burst-picker.js`

#### ✨ 49c — Picker Overlay 跨裝置體驗
- **Picker overlay 移出 lightbox-content**：overlay 從 lightbox 內移至 `<body>` 層級，純 CSS `position: fixed` viewport-anchored，避免被 lightbox 裁切
- **卡片升級 150×200（4:5 比例）**：picker 候選卡尺寸調大，封面展示更清晰
- **Tablet / Mobile 改 grid repeat(3)**：平板強制 3+3 兩行、手機底部 sheet 改 `grid` + `repeat(3, minmax(0, 1fr))`，不再溢出
- **移除 picker-name-chip**：簡化 picker UI，姓名標籤從卡片上移除

#### ✨ 49d — Actress Lightbox Ghost-fly 補全 + Footer 重設計
- **Actress mode lightbox open 補 ghost-fly**：開啟女優燈箱時補上與影片模式對齊的 ghost-fly 動畫，`closeLightbox` closingIndex 按模式分流，補 actress mode fly-back
- **Footer 視覺重設計**：數字改 17px monospace 700 加粗主導；影片數用 `--accent` 配色、女優數用 `--accent-pink`；label 降階為 caption 字級；搜尋詞加 `footer-search-term` 樣式壓回繼承色
- **Footer 架構修正**：center 段改 `position: absolute` 居中解耦三段；left/right 加 `flex-shrink: 0`，三段互不推擠
- **Footer 對齊 sidebar 修跑版**：修正 49a-T4 既有設計 bug（sidebar `z-index: 1000` 蓋住 footer 左側 60–200px），Codex P2 fix 補 `footer-search-term` max-width clamp

### Fixed
- **49a Codex P1+P2**：ghost flag 邊界、pager picker 守衛、actress 空資料容錯、alias refetch 時序
- **49b Codex 8 issues**：P1 × 4（SSE race、候選卡去重、photo POST 路徑比對、crop 參數驗證）+ P2 × 4（文案、picker dismiss、UI 細節、型別守衛）
- **49c Codex F1/F2/F3**：視覺對齊修正 + 守衛強化；picker DOM scope bug（`$el` → `$refs.pickerCoverImg`）；3 picker bug 一批（grid 不刷新 + hover tooltip + 雙 `?` URL）

### Refactor
- **BurstPicker 抽共用模組**（49b）：picker 邏輯集中管理，後續新增 picker 場景可直接複用
- **移除 rescrape dead code**（49b）：清理未使用的 rescrape 路徑，減少維護負擔
- **Picker overlay JS 定位 helper 退役**（49c）：V2 純 CSS 取代 JS 計算，移除 `_positionPickerOverlay()` helper
- **刪除 /picker-lab dev sandbox**（49c）：開發驗測沙盒完成任務後清除，避免遺留路由

### Tests
- `TestPickerIntegrationGuard 22/22 pass`、`test_frontend_lint 439/439 pass`
- 全套 2588 → **2705 tests passed**（+117 net；49b dedupe 2 個重複測試）
- 兩個 pre-existing baseline failure（`TestNoHardcodedColors` / `TestMotionInfra _fadeMetadataPanel`）與 49 系列無關，追蹤中

## [0.7.7] - 2026-04-25

本版主要修正三大長期困擾用戶的問題：WinFsp/rclone 掛載磁碟 Showcase 封面全空白、刮削後劇照幽靈 URL 導致 Showcase 破圖、以及含字幕標記的檔名造成片名識別錯誤。同時新增 Showcase 燈箱一鍵補抓劇照入口，以及整理格式 `{month}`/`{day}` 兩個新變數。

### Fixed

#### 🐛 48a — 字幕標記 / Detail 封面 / IME / 長路徑修正
- **中文字幕標記不再被誤認為片名**：`[中字]`、`【中文字幕】`、`-中字` 等標記在搜尋結果、翻譯功能、整理重命名中均正確剝除，不再導致片名亂掉或翻譯鈕消失（前後端同步修正）
- **Detail 面板封面不再被裁切**：影片詳細資料的封面圖統一改為完整顯示（letterbox/pillarbox），與 Grid/燈箱風格一致
- **中文/日文輸入法選字時不再誤觸搜尋**：輸入法組字過程中按 Enter 選字，不再提前送出搜尋
- **掃描部分失敗時不誤刪既有紀錄**：資料夾有部分無法讀取（如權限問題）時，掃描結果不完整不再觸發誤刪紀錄（Codex P1 regression fix）

#### 🐛 48b — 劇照幽靈 URL 根本修正 + 孤兒清理
- **刮削後未下載劇照時不再寫入遠端 URL**：以往刮削完但劇照尚未下載時，資料庫會存入 scraper 的遠端 URL，導致 Showcase 劇照顯示為 403 錯誤；現在只有實際下載成功才寫入本機 file:/// URI
- **補抓劇照後路徑正確**：在 Showcase 燈箱補抓劇照後，畫面立即更新且路徑正確，不再出現無法載入的情況
- **孤兒劇照自動清理**：掃描時自動偵測並移除資料庫中磁碟上已不存在的劇照記錄，避免前端顯示破圖（非 file:/// 舊格式一律保留，避免誤刪舊資料）

#### 🐛 48c — WinFsp / rclone 掛載磁碟相容
- **使用 rclone + WinFsp 掛載磁碟不再顯示空白封面**：此前 `os.path.realpath()` 在 WinFsp 底層 API 不支援時直接拋 OSError 導致所有圖片/影片回傳 500 錯誤，現改為 `try: realpath except OSError: normpath` 降級 pattern，正常環境保留 symlink escape 保護、FUSE 環境降級支援
- **部分日期整理時正確跳出警告**：scraper 只抓到 `2015-06`（無日）時，用戶用 `{day}` 變數整理會產生「未知日」資料夾，現會正確觸發 UI 警告 toast（Codex P2 fix）

### Added

#### ✨ Showcase 劇照補抓入口（48b）
- **燈箱新增「補抓劇照」雲朵按鈕**：影片尚無劇照時，燈箱右上角顯示 pill 造型 + Bootstrap icon + Apple Blue 配色的補抓按鈕，一鍵從線上抓取；多片共用資料夾時提示先搬移再補抓
- **新增 `POST /api/scraper/fetch-samples` 端點**：劇照補抓專用 API，含多片資料夾 gate 保護；Agentic AI capabilities 同步揭露（27 → 28 tools）

#### ✨ 整理格式新增月份 / 日期變數（48c）
- **`{month}` / `{day}` 格式變數**：資料夾與檔名整理範本可使用 `{month}`（2位月份）和 `{day}`（2位日期），補齊原有 `{year}` / `{date}`；用戶可自行組合 ISO (`{year}-{month}-{day}`)、DMY (`{day}/{month}/{year}`)、任意格式
- **修正 {date} 未出現在資料夾層級變數選單**：原本 Settings 的資料夾層級變數選單漏列 `{date}`，用戶必須手動輸入（issue #28 報告者：smallghost）
- **設定頁面 UI + 說明頁面 + 四語系 i18n 同步更新**

#### ✨ Windows 長路徑警告（48a）
- **掃描完成後顯示超長路徑警告**：Windows 上路徑超過 260 字元的檔案可能無法讀取，掃描結束後會以 toast 顯示數量並記錄詳細清單到 debug.log（macOS / Linux 不受影響）

### Changed
- **`_detect_suffixes` 拼接順序說明明確化**：確認「多個 keyword 時輸出按 keyword 列表順序拼接，不按檔名順序」為 canonical 化設計；`suffix_keywords_hint` 四語系補充說明

### Tests
- 全套 2436 → **2588 tests passed** (+152 net)

### Known Issues（追蹤中）
- `_validate_sample_images()` cleanup pass 在 FUSE 環境仍可能誤刪 DB 劇照 URI，追蹤於 `feature/48-polish-fixes/spec-48c.md` #10，v0.7.8 加 retry-then-soft-fail 修復

## [0.7.6] - 2026-04-18

### Fixed
- **Scanner 一鍵補完在缺資料 > 500 片時按鈕 disabled**：後端 `/api/gallery/missing-check` 移除 500 cap（原本超過 500 回 `items: null`，前端因此 disable 按鈕），現在永遠回完整清單。前端 `missingItems > 500` 時彈 confirm dialog 讓用戶明確同意後才啟動。Rate limit 由 `/api/batch-enrich` 自己的 20/batch + delay 處理
- **Resume 流程改用 options pattern**：`resumeMissingEnrich()` 不再提前清 `localStorage.avlist_enrich_pending`，改由 `runMissingEnrich({ skipConfirm: true })` 統一管理清除時機（避免大批量 resume 被 confirm dialog 取消時丟失 pending 恢復點）

### Added
- **大批量 confirm dialog**：i18n 四語系新增 6 個 `scanner.stats.missing_enrich_confirm_*` keys（純文字，前端用 `<span x-text>` + `<strong x-text>` 組裝數字）

### Tests
- 全套 2436 → 2450 tests passed (+14 net)
- 新增：backend `TestMissingCheckAPI` 4 個 500/501/5000 邊界測試 + frontend lint 5 個 guard tests（含 `resumeMissingEnrich` regex 函式體守護）

## [0.7.5] - 2026-04-16

### Added

#### 🎯 46 — UI Polish
- **Ghost Fly 轉場**：Grid↔Lightbox 封面飛行動畫（共用 `ghost-fly.js` 模組，Search + Showcase 雙頁面支援）
- **新手教學擴充為 7 步**：涵蓋搜尋、收藏、女優、Scanner、設定完整流程
- **Floating Hearts 粒子特效**：Hero Card 已收藏愛心點擊時噴射心形粒子
- **女優模式 camera icon**：切回影片模式時加 crossfade 動畫
- **Toolbar 響應式統一**：影片模式 5 個 icon 整組同時換行，不再逐個掉落
- **Alias Guard**：`sync_from_favorite()` 空 aliases 不再建空記錄
- **README AI-Ready API 重寫**：多步驟工作流範例（top 20 女優收藏、別名 + tag、Gallery HTML）
- **打包版 README 跨平台對齊**：Windows / macOS 疑難排解、啟動腳本說明補齊

### Fixed
- **User-tag 無法被搜尋**：Showcase 頁面搜尋框的 searchable 欄位清單漏掉 `user_tags`，用戶自訂 tag 輸入後搜不到對應影片，已補上
- **User-tag dark mode 對比度**：`color: var(--text-inverse)` → `var(--color-primary-content)`
- **GSAP Lightbox ease/scale 微調**：`scale 0.92 → 0.95`、`back.out → power2.out`、`gsap-animating` 時序提前
- **狀態同步修正**：模式切換保留各自搜尋詞 + addFavorite/rescrape 後立即刷新 Grid + removeActress 後重算精準匹配
- **女優 icon 統一**：`bi-person` → `bi-person-circle` 全站同步
- **en.json 單位**：`showcase.unit.films` 補 "films" 單位
- **模式切換 disabled binding 移除**：搜尋欄有文字時不再禁用切換按鈕

### Tests
- 全套 2416 → 2436 tests passed（+20 net）

## [0.7.4] - 2026-04-14

### Added

#### 🎯 45 — Actress Alias 系統 + Scanner 一鍵補完
- **Actress Alias CRUD**：`AliasRecord` + `AliasRepository`（SQLite `actress_aliases` 表）+ 7 個 REST 端點（CRUD + online search）+ 舊 `actress_name_mapping` 表自動遷移
- **Favorite 同步**：加入收藏時自動寫入 alias record（orchestrator aliases → DB）
- **搜尋展開**：alias-aware lookup — 搜尋任一別名自動展開為所有已知名稱，video_count 聚合顯示
- **Showcase alias 展開**：Lightbox aliases chips 從 DB alias record 讀取，不再只靠 scraper 回傳
- **Scanner Alias UI 重設計**：舊雙欄 old/new 輸入 → primary name + chips pills 單一輸入框，支援篩選、新增、線上搜尋建議
- **舊 alias 系統清除**：移除 `nfo_updater.py` alias 相關 974 行 + 8 個舊端點，Scanner router 從 820→350 行
- **Scanner 缺 NFO/封面偵測**：`GET /api/gallery/missing-check` 端點 + 掃描完成後自動顯示缺失計數 pill
- **一鍵補完**：呼叫 `batch-enrich` SSE 分批補齊缺 NFO/封面，支援 localStorage 暫停/續傳
- **Capabilities**：新增 `alias_crud_read`、`alias_crud_write`、`alias_search_online` 三工具（共 27 tools）
- **i18n 四語系同步**：alias UI + missing pill 所有文字 + scanner stats 文案優化

### Fixed
- **Search bar 搜尋後跑版**：`--spotlight-right-slot: 8.5rem` override 修正右側 3 按鈕溢出
- **Scanner pill 文案混淆**：「快取影片」→「已掃描」/「需補全」→「NFO 欄位不全」/「補全」→「補齊欄位」/「補完」→「一鍵補完」，四語系同步
- **Codex review fixes**：DDL `applied_count` 移除 + alias map init 載入 + seed 刪除
- **batch-enrich stream 中斷**：未收到 `done` SSE event 時不再跳過整批，正確儲存 pending
- **dismissResume 狀態洩漏**：忽略 resume 後重新從 DB 拿 missingItems，pill 按鈕可用

### Tests
- 全套 2317 → 2416 tests passed（+99 net）
- 新增：alias repository 28 + alias API 28 + favorite sync 12 + search alias resolve 18 + scanner missing-check 8 + frontend guard 22 + scanner lint 11

## [0.7.3] - 2026-04-13

### Added

#### 🎯 44 — Actress Showcase 模式 + 精準匹配 Hero Card
- **Showcase 女優模式**：toolbar 切換影片 Grid ↔ 女優收藏 Grid，含搜尋、排序（名稱/年齡/罩杯/身高/新增日期）
- **女優卡片**：160px/220px 密集 Grid，三欄 footer（名稱 + 年齡/排序指標 + 影片數），hover 顯示身體數據
- **女優 Lightbox**：5-row 佈局（照片+愛心 / metadata / aliases chips / info chips / URL 連結），chips +N 收合展開
- **CRUD 操作**：加入收藏（POST favorite）、重新抓取（rescrape）、移除收藏（DELETE）、搜尋相關影片（bi-camera-reels）
- **精準匹配 Hero Card**：搜尋框輸入已收藏女優名 → 搜尋框出現 ♥，Grid 上方顯示 hero card（照片 + 年齡 + 身體數據）
- **搜尋框愛心 Icon**：metadata tag 點擊未收藏女優 → ♡ 可點擊加入收藏 → ♥ + hero card 出現
- **Lightbox -1 Sentinel 導航**：hero card lightbox ↔ 影片 lightbox 左右鍵無縫切換
- **GSAP 動畫**：女優模式 crossfade 切換、卡片 entry stagger、排序 FLIP、hero card 出現/消失過渡
- **Segmented Mode Toggle**：glass capsule 設計（bi-film | bi-person 圖示）
- **`GET /api/actresses`** 列表端點 — video_count + is_favorite
- **i18n 四語系同步**：女優模式 + hero card 所有 UI 文字 + `common.no_image` 共用 key
- **Capabilities**：rescrape 端點揭露

### Fixed
- **`is_favorite` API contract**：`_actress_to_response()` 補上 `is_favorite: True`（DB 中的女優即收藏）
- **Hero card 寬度**：從 `.showcase-grid` 外移入 grid 內（同 /search pattern），grid 自動控制寬度
- **Metadata scope**：`searchFromMetadata(term, type)` 只有 actress tag 觸發精準匹配，片商/系列/標籤不再誤觸
- **`searchActressFilms` 入口**：補上 `_checkPreciseActressMatch` 呼叫
- **`toggleActressMode` state leak**：切換模式時清除精準匹配狀態
- **ja.json typo**：`showcase.actress.favorited` 中文→日文修正
- **Dropdown hit area**：全寬 items + z-index 堆疊修正
- **Grid overlay**：bottom-aligned + focus-within 鍵盤修正
- **POST favorite/rescrape**：回傳真實 video_count

### Tests
- 全套 2167 → 2317 tests passed（+150 net）
- 新增：actress showcase API 11 + CSS spotlight 4 + frontend lint 109 + integration 1 + capabilities 1

## [0.7.2] - 2026-04-12

### Added

#### 🎯 43 — Actress Favorite 系統 + /search 整合
- **DB `actresses` 表 + ActressRepository CRUD**：`save`（ON CONFLICT DO UPDATE 保留 `created_at`）/ `get_by_name` / `delete_by_name` / `get_all` / `exists`
- **照片下載模組 `core/actress_photo.py`**：Referer 設定（graphis/gfriends/wiki/minnano）、Content-Type 副檔名推斷、glob 刪舊檔覆蓋
- **API Router `web/routers/actress.py`** 四端點：
  - `POST /api/actresses/favorite` — cache 優先 + fallback orchestrator + 照片下載 + makers 前綴→片商名轉換
  - `GET /api/actresses/{name}` — 已收藏女優查詢
  - `DELETE /api/actresses/{name}` — DB + 本地照片刪除
  - `GET /api/actresses/photo/{name}` — 本地照片 binary response
- **Orchestrator `ProfileResult` namedtuple**：`get_actress_profile` 回傳 `(data, timed_out)` 結構化結果，區分 timeout vs not-found
- **`get_cached_profile()` 公開 cache 讀取**：收藏流程 cache hit 時不打網路
- **/search DB 優先查詢**：已收藏女優搜尋時完全本地回應（0 網路請求）+ `is_favorite` 旗標
- **Hero Card footer 重設計**：左 name 右 age，hover 顯示 height · cup · 三圍
- **愛心收藏 overlay**（`.av-card-preview-overlay` + `.btn-glass-circle`）：未收藏 hover 空心可點擊；已收藏常駐實心純指示（CD-10）
- **Actress Lightbox 重建**：上圖下文 5 rows（名稱+愛心 / 核心 metadata / aliases chips / info chips / URL 連結）；chips 超過 N 個 +剩餘數 badge 可展開
- **Source link icon**：lightbox cover-actions 位置，點擊開啟文字來源頁面（minnano / Wikipedia JP）；已收藏或無文字來源時不顯示
- **i18n 四語系同步**：`search.actress.*` + `search.unit.age/cup` 共 7 keys × 4 語系
- **Capabilities 三端點**：`favorite_actress` / `get_actress` / `unfavorite_actress`（含 side_effect + confirmation_required 安全標記）

### Fixed
- **aliases `[object Object]` bug**：minnano scraper 回傳 dict list，新增 `_flatten_aliases()` helper 在存入 DB 和前端回傳時 flatten 為純字串 list
- **Race condition**：`addFavoriteActress()` 加 captured profile reference + await 後 stale-check（同 41d pattern）
- **URL scheme XSS 防護**：新增 `_safeUrl()` http(s) 白名單 guard，blog_url / official_url 不再直接綁 `:href`
- **422 validation response**：全域 `RequestValidationError` handler 回固定中文格式
- **makers 精度**：番號前綴→片商名轉換（`load_prefix_mapping`），保序去重維持 gfriends probe 優先順序
- **CSS hardcoded color**：`#ff4d6d` 改用 `--color-favorite` CSS 變數
- **Hero card guard test**：搜尋範圍 800→1200 字元（適應 T5 overlay 偏移）

### Tests
- 全套 2129 → 2167 tests passed（+38 net）
- 新增：`test_actress_repository.py`（13）、`test_actress_photo.py`（6）、`test_actress_aliases_flatten.py`（6）、`test_api_actress.py`（12）
- 更新：orchestrator tests（ProfileResult 型別）、actress_profile tests（DB 優先查詢）、capabilities tests（+3 tools）

## [0.7.1] - 2026-04-11

### Added

#### 📦 42a — Actress Scraper 模組搬遷
- 女優爬蟲整合到 `core/scrapers/actress/` 子目錄（純 mechanical refactor，零行為變更）
- 3 個舊檔刪除：`core/actress_scraper.py` / `core/graphis_scraper.py` / `core/gfriends_lookup.py`
- Router 2 個 call site + 30+ test imports + 41 patch targets 全量更新

#### 🌐 42b — 新增 2 個女優資料來源 + Orchestrator 重寫
- **Minnano-AV scraper**（C1 primary text source）— 5/5 覆蓋 birth/BWH/身高/罩杯/出生地，另帶 aliases / agency / debut_work / tags 富欄位
- **Wikipedia JP scraper**（C1 secondary）— 獨有 nickname + Commons 照片（只回 raw URL + `photo_needs_resize` 旗標，下載/resize/cache 延後到 Phase 43）
- **Orchestrator 重寫**：4 路並行（minnano + wiki + graphis + gfriends）+ C1 text cascade + C4 mixed return shape（新 nested 欄位 + legacy flat shortcuts 並存，舊 consumer 零改動）
- **TD-1 Age Fix**：`current_age` 一律從 `text.birth` 即時計算，不再從任何 source 讀 stale age
- Codex review 3 bugs fix + Minnano field list 2nd-review 修正

#### 🔍 42c — Scraper 巡檢 + 優化
- Playwright MCP 實地巡檢 4 個 live scraper（Minnano / Wiki JP / Graphis / gfriends），findings 歸檔於 `plan-42-research/scraper-review/`
- **T7.1 gfriends AI-Fix 順序翻轉**：先試 `AI-Fix-{name}.jpg` 再 fallback 原版，修正涼森れむ 被 119×170 低解析 input 原檔卡住、拿不到 476×680 AI-Fix 輸出的 bug
- **T7.2 wiki_ja 別名欄位 + photo alt guard**：從 `別名`/`芸名` 欄位解析 aliases + 防止非女優照片（alt 不含目標名）被當成女優頭像
- **T7.3 graphis hobby 純 JP 化**：hobby 欄位 strip 掉 EN 翻譯部分，統一日文輸出
- Codex review 2 bugs fix

#### 🧹 42e — Actress JavBus 永久移除
- **移除 `core/scrapers/actress/javbus.py`**（225 行 dead code）— 42c T2 decision gate 技術上判定可修（識別出 parser DOM bug + session/warmup 策略可穩定繞過 driver-verify），但重新評估後決定永久移除
- **架構分離**：影片 pipeline 的 `core/scrapers/javbus.py` 完全不動，影片和女優資料來源從此完全分開，維護責任邊界清晰
- Orchestrator `all_sources` dict 移除 `"javbus"` key（不保留 None slot，schema 乾淨）
- 3 個 test 檔案清理：`test_scraper_actress_javbus.py` 整檔刪 + `test_actress_profile.py` 13 處 javbus patch + `test_scraper_actress_orchestrator.py` 3 個 schema slot test
- **Supersedes**: Phase 42d（條件性升級計畫整份廢棄）

### Changed
- `core/scrapers/actress/` 為最終 baseline：orchestrator 4 路並行為唯一實作（minnano + wiki + graphis + gfriends）
- `core/README.md` actress 段落更新為「orchestrator + 4 sources」描述

### Tests
- 全套 2045 → 2129 tests passed（+84 net，含新增與刪除平衡）
- 42b 新增：orchestrator 4 路整合測試（TestHappyPath / TestC1Cascade / TestPhotoCascade / TestTD1Age / TestComputeAgeUnit / TestLegacyFlatConsistency / TestCacheTTL / TestMeaningfulTextFilter）
- 42c 新增：gfriends 4 case + wiki_ja 4 新 case + graphis parser 5 test
- 42e 刪除：`test_scraper_actress_javbus.py` 整檔 9 tests + `test_actress_profile.py` 1 dead test + `test_scraper_actress_orchestrator.py` 3 schema slot tests
- **測試目錄修正**：`test_scraper_actress_orchestrator.py` 從 `tests/integration/` 搬到 `tests/unit/`（全 mock 無 TestClient，按 CLAUDE.md 分類規則應在 unit/；42b 遺留的目錄分類錯誤，pre-merge 一併修正）

## [0.7.0] - 2026-04-10

### Added

#### 🤖 41a — AI Metadata Management API
- `POST /api/batch-enrich` SSE streaming 批次補資料（path 去重 + scraper cache + 逐筆 durable 寫入）
- `POST /api/collection/fix-numbers/preview` + `/apply` 異常番號修正（4 種 server-side 規則 + 兩階段安全流程）
- `GET /api/collection/analysis` + `POST /api/collection/analysis/groups` 收藏診斷端點（5 種 group：no_nfo / corrupted_numbers / japanese_tags / missing_core / missing_secondary）
- `enrich-single` 加 `source` + `javbus_lang` 參數
- Capabilities 同步揭露 5 個新 tool（含 side_effect / confirmation_required 安全標記）

#### 🏷️ 41b — User Tags（DB + NFO + API + 雙頁 UI 三層整合）
- DB 新增 `user_tags` JSON 欄位（`refresh_full` 不覆蓋）
- NFO 獨立 `<user_tag>` 元素（與 `<tag>` 完全分離，scraper tags 與用戶 tags 不混淆）
- 新增 `POST /api/user-tags` + `GET /api/user-tags` 端點
- Search 頁 user_tags UI（新增/刪除）改接 API 持久化
- Showcase Lightbox user_tags UI（新增/刪除）整合
- scrape-single 寫出 NFO 時 `<tag>` 與 `<user_tag>` 分離寫出
- Capabilities 揭露 user_tags tool + database_schema 同步

#### 🖼️ 41c — Cover Image Fix + Showcase 一鍵補資料
- Scanner `find_cover_image()` 重寫為 4 層 smart fallback：L1 同名圖、L2 標準名、L3 NFO `<thumb>` 跨平台路徑解析（5-case：URL/file:URI/Windows drive/UNC/POSIX）、L4 `len(videos)==1 AND 0<len(images)<=2` 雙條件安全 fallback
- 修正平鋪資料夾下 MTES-035 跨片污染 bug
- Showcase API 加 `has_cover` / `has_nfo` 欄位 + 新增 `GET /api/showcase/video?path=...` 單筆查詢端點（serializer helper 共用）
- Grid + Lightbox 加「補資料」enrich icon：無封面卡片 icon 常駐顯示 + missing-cover overlay；有封面但無 NFO 卡片 hover-only icon；mode 自動選擇（無封面 → refresh_full / 有封面無 NFO → fill_missing）；點擊後 spinner + cache-bust + 原地刷新單張卡片
- `handleCoverError` 機制：cover 載入失敗時自動 downgrade `has_cover` → enrich icon 出現（self-healing for NAS 搬檔/離線）
- Lightbox 無封面塌陷修復：`.lightbox-cover` 加 min-width/min-height + placeholder SVG 升級為「無封面」empty state

#### 🔧 41d — PR #22 Codex Review Cleanup
- **T1+T2** 路徑契約：新增 `path_utils.reverse_path_mapping()` helper + `collection.py _resolve_user_tag_paths()` 改用 helper（消除 inline `replace('\\', '/')` 違規）
- **T3+T5** Race condition：`result-card.js` 4 處 await 後寫入修正（`confirmAddTag` / `removeUserTag` / `fetchUserTagsForCurrent` / `_translateWithAILogic` Gemini 分支）— 改用 await 前 captured object reference，避免切檔時 user_tags 或 translated_title 寫到錯片
- **T4** i18n：showcase placeholder SVG 移除 hardcoded 中文「無封面」— `_NO_COVER_PLACEHOLDER` IIFE 在 i18n 載入前執行，改為純圖示 empty state
- **T6** Codex P1+P2：`reverse_path_mapping()` boundary check（避免 `//NAS/share` 誤命中 `//NAS/share2/...` 導致 NFO 寫到錯目錄）+ trailing slash normalize（避免 `/sharevideo.mp4` 缺斜線或 `/share//video.mp4` 雙斜線）
- **T7** 對稱修正：`to_file_uri()` mapping branch 同型 P1+P2 修正（forward 方向 canonicalization 一致性）
- **T8** Capabilities：補揭露 3 個 GET endpoint（`get_user_tags` / `showcase_videos` / `showcase_video`）— POST/GET 對等性 + Showcase 業務層查詢揭露給 AI agent

#### 🧪 Tests
- 全套 1818 → 2045 tests passed（+227 個 test functions；pytest collect 含 parametrize 展開）
- 41a 新增：collection_sql regression、batch-enrich SSE 11 test、fix-numbers 12 unit + 3 integration、analysis 23 unit + 5 integration
- 41b 新增：user_tags unit 18 + integration 42 + search 整合 9 + frontend guard 17
- 41c 新增：cover_image 33 test（4 層 fallback × 5-case 跨平台）、showcase API 12 test
- 41d 新增：path_utils 28 test（reverse_path_mapping 10 baseline + 10 P1/P2 boundary + to_file_uri 8 對稱）、user_tags integration 4、capabilities 2、frontend guard 1 test gap fix

### Fixed
- SQL API `[]` false positive（單引號字面值內的 `[]` 不再被擋）
- enrich 後 nfo_mtime 未同步到 DB 導致 analysis missing_nfo 不減

### Known Issues
- v0.6.5 / v0.6.6 / v0.6.7 git tag 未打（CHANGELOG entry 已存在），release 時補
- i18n: `showcase.action.enrich` / `showcase.enrich.success` / `showcase.enrich.failed` 三個 key 缺 zh_CN / en / ja（zh_TW 已有），milestone 補齊

## [0.6.7] - 2026-04-09

### Added

#### 🎨 CTA 文案重構 (Phase 39c-T1)
- 四語系 CTA 按鈕文案統一改為「整理」語意（「產生全部」→「批次整理」、「產生 NFO + 封面」→「整理此片」）
- tooltip 加上具體說明（重命名 + 建資料夾 + NFO）
- Help 頁說明文字同步更新

#### ✨ 整理動效回饋 (Phase 39c-T2)
- 單片整理成功 checkmark pop-in + row 綠色 flash 動畫
- 單片整理失敗按鈕 shake 動畫
- 批次整理進度條即時 smooth 更新 + per-file 動效回饋
- `alert()` 阻斷式彈窗全面替換為非阻斷 toast 通知（7 處）

#### 🚀 Load More 三入口動畫 (Phase 39c-T3)
- Grid「載入更多」：新卡片 stagger fade-in cascade
- Detail next 到最後一片：自動載入 + slide 換場到第 21 片
- Lightbox next 到最後一片：自動載入 + crossfade 到第 21 片
- `loadMore()` 重構為三入口共用基礎（trigger 參數 + 回傳值）

### Fixed
- Lightbox close race condition — await 期間關閉後不再偷改 currentIndex
- 批次整理進度條第二次執行不再殘留上次 width
- Lightbox prev/next arrow 加 loading 回饋（disabled + spinner）

## [0.6.6] - 2026-04-09

### Changed

#### 🏗️ Alpine.js 技術債清理 (Phase 39b)
- motion_lab.html 914 行 inline x-data 抽離 → `motion-lab-state.js`
- scanner.html 1126 行 inline script 抽離 → `scanner.js`
- 6 頁面統一改用 `Alpine.data()` 正式註冊（取代 window 全域函數）
- Search 頁消除 `window.SearchCore`（47→0 處）、`_x_dataStack`（6→0 處）循環委派
- 刪除 `bridge.js`、`init.js`；`core.js` 精簡為常數
- `window.SearchUI.showState()` 27 處改為 Alpine reactive 直接賦值

### Fixed
- Search `clearAll()` 補齊 10 個 runtime UI state 欄位 reset（lightboxOpen、displayMode 等）
- scanner.js 移除 10 個 production console.log
- `loadAppConfig()` tooltip 改走 i18n（新增 `search.action.load_favorite_folder`）

## [0.6.5] - 2026-04-09

### Added

#### 🔌 OpenAI Compatible 翻譯 Provider (Phase 39a-T2)
- 新增 OpenAI Compatible 翻譯 Provider — 支援任意 OpenAI 相容 API 端點（OpenRouter、本地 LLM 等）
- Settings 頁新增 OpenAI Compatible 設定區塊（Base URL + API Key + Model 選擇）

#### 🔍 搜尋改善 (Phase 39a-T4)
- Grid 模式底部新增「載入更多」按鈕
- Lightbox 最後一張按 Next 自動觸發載入更多

#### ⚙️ Gemini 精簡 (Phase 39a-T3)
- Gemini model 下拉精簡為 4 個推薦 model（allowlist 取代動態過濾）

### Changed
- locale 劇照用詞統一：「Sample Image」→「Stills」、「樣品圖」→「劇照」
- README_EN 用詞同步對齊

### Fixed

#### 🐛 關鍵修復
- DMM 分頁 offset 寫死 0 — 搜尋第二頁以後結果重複 (T5)
- OpenAI Settings UI：select 切換 + 錯誤細化 + auto-fetch + custom model 持久化
- XSS 修正 + ja locale short-circuit
- loadMore() shared state desync — Lightbox/Grid/Detail currentIndex 不再被靜默修改
- Gemini model fallback — 舊 model 不在 allowlist 時自動選第一個

## [0.6.4] - 2026-04-04

### Added

#### 🔧 Scanner 改善 (Phase 40c)
- Jellyfin 圖片檢查改為手動觸發（AbortController + 三狀態機）
- jellyfin-check TTL 60 秒快取（HDD NAS 用戶重複點擊不再重跑全量掃描）

#### 📦 打包修復 + 文件 (Phase 38e)
- 「下載劇照」拆分為獨立設定，與 Jellyfin 模式解耦
- 新增 README_EN.md 英文版 + 繁中版語系切換連結
- README.md 繁中版內容更新（v0.6.x 功能同步）

### Changed

#### 🎨 前端品質改善 (Phase 40a–40d)
- Design System 各頁元件 Demo 補齊（Showcase / Search / Settings / Help / Motion Lab）
- 頁面生命週期強化：interval 具名 ref + timer/listener 記憶體洩漏清理 + settings lifecycle gate
- Showcase Lightbox 關閉行為對齊 Search（移除 mousemove anti-pattern + 1 秒延遲門控）
- Showcase 鍵盤 preventDefault + 動畫 optional chaining 對齊 Search
- Sample Gallery 背景點擊關閉修正（sg-main-wrap @click.self）

### Fixed

#### 🐛 關鍵修復
- 打包遺漏 locales 目錄（i18n 所有 UI 文字全空修復）
- jellyfin_image_check asyncio.to_thread 消除 event loop 阻塞
- NFO 補全移除 series/label 必查 + Jellyfin 封面提示優化
- Inline Style 清理 + DS scope guard 移除

## [0.6.3] - 2026-04-02

### Changed

#### 🔧 開發流程穩定化 (Phase 38d)
- 測試分層修正：integration mock-only 測試搬回 unit（296→210 integration、1030→1111 unit）
- rate_limit mock patch target 修正 — 全套測試 4:02 → 1:29
- E2E 場景清單（17 UI + 5 Agentic AI API 場景）+ App 操作指南
- Agentic AI 驗證：Haiku 即可正確操作 capabilities API
- .gitignore 加入 .playwright-mcp/
- 測試總數 1326 → 1321（-5 重複刪除）

## [0.6.2] - 2026-04-01

### Added

#### 🤖 Agentic AI API 平台 (Phase 38b)
- `POST /api/batch-search` — 批量番號搜尋，一次多筆結構化回傳
- `POST /api/gallery/generate-from-ids` — 番號列表產生自訂 Gallery HTML，封面自動 base64 嵌入（可分享）
- `POST /api/enrich-single` — 舊片原地補完（fill_missing / db_to_sidecar / refresh_full），不搬移不改名
- `POST /api/collection/sql` — Read-only SQL 查詢收藏資料庫，12 層安全防護
- `GET /api/capabilities` — Self-describing AI manifest，一個 curl 就能學會使用 OpenAver
- `GET /api/search` 新增 `since` 日期過濾 + `discovery` 輕量探索模式
- Help 頁 Hero Card 右欄新增 AI 整合入口（Terminal box + 一鍵複製 curl）
- `skill_setup` 欄位建議 agent 註冊為 SKILL.md
- Gallery HTML 封面嵌入：Referer 自動補齊（JavBus/DMM/Jav321）+ embed 統計

### Fixed
- `generate-from-ids` scrape 路徑封面欄位名修正（`cover_url` → `cover`，對齊 legacy dict）
- `enrich-single` DB path/cover_path 寫入格式修正（file:/// URI 契約）
- `enrich-single` NFO 寫入時自動偵測字幕（`find_subtitle_files`）
- `enrich-single` config 區段修正（`config["search"]` 取代 `config["scraper"]`）
- `_missing_fields` series 空字串視為缺失（與 director/label 一致）

### Changed
- 測試總數 1430 → 1634（+204）

## [0.6.1] - 2026-03-31

### Added

#### 🌐 i18n 補齊 + 翻譯目標語言 (Phase 38c)
- Search 頁動態按鈕 / 標籤 i18n 補齊（searchAll / translateAll / fileCount / MODE_TEXT / cover error 共 20 key）
- 翻譯功能自動跟隨 UI 語系：繁中→繁中翻譯、簡中→簡中翻譯、英文→英文翻譯
- `LANGUAGE_PROMPTS` 三語系 prompt 模板（Ollama + Gemini）
- 日文 locale 自動跳過翻譯（原始標題本身即日文，不呼叫 API）
- Settings 翻譯測試按鈕跟隨語系（Ollama / Gemini test prompt 動態切換）
- Settings 連線狀態訊息 i18n（17 key）
- Tutorial 新手教學四語系補齊（14 key）
- i18n 測試零 warnings（所有 locale 欠債清零）

### Fixed
- Search 頁 MODE_TEXT 未知 mode graceful fallback（不再顯示 `[search.mode.xxx]`）
- Settings 翻譯測試按鈕 dark mode 文字不可見（移除 `btn-neutral`）
- `chinese_title_ai` label 改為「AI 翻譯標題」（翻譯結果可能非中文）
- locale 變更時翻譯 service singleton 正確重建

### Changed
- 測試總數 1420 → 1430（+10）

## [0.6.0] - 2026-03-29

### Added

#### 🌐 UI 多語系 i18n (Phase 38a)
- 四語系支援：繁體中文（zh-TW）、簡體中文（zh-CN）、日文（ja）、英文（en）
- `core/i18n.py` 翻譯核心模組：`t()` fallback chain、`get_merged_translations()`、Accept-Language 偵測
- `locales/` 四語系 JSON（~477 個 key），涵蓋所有頁面靜態 UI 文字
- Settings 頁語系切換按鈕（繁 → 简 → あ → EN 循環），Fluent-glass 外觀
- `base.html` 注入 `window.__i18n` + `window.t()` 供前端 JS 使用
- JavBus scraper 語系連動（locale → lang 參數自動對應）
- 字體 fallback 加入 Hiragino Sans / Yu Gothic UI / Noto Sans JP（日文假名支援）
- i18n 完整性測試（477 key × 3 locale = 1431 parametrize 測試）
- `<html lang>` 動態跟隨語系設定
- `PUT /api/config/general/locale` 加 enum 白名單驗證
- Settings 語系切換整合 dirty-check 保護

### Changed
- 測試總數 1366 → 1420（+54）
- AGENTS.md 新增 i18n review policy

## [0.5.5] - 2026-03-28

### Added

#### 🎬 字幕檔自動偵測與搬移 (Phase 37d-T1)
- 新增 `find_subtitle_files()` 掃描同目錄同名字幕檔（.srt/.ass/.ssa + 語言後綴）
- `organize_file()` 影片搬移成功後字幕自動跟隨，保留語言後綴命名
- 字幕偵測與 NFO 標記一致：sidecar 字幕存在時覆寫上游 `has_subtitle=False`

#### ⚙️ Settings 搜尋來源 UI 簡化 (Phase 37d-T2)
- 移除頁面底部獨立「主要搜尋來源」radio 區塊
- DMM/JavBus badge 可直接點擊切換，以 ●/○ 符號標示選中狀態

#### 🌐 Proxy direct 模式 (Phase 37d-T3)
- Proxy 欄位輸入 `direct` 代表已有日本 IP，免填 proxy 即可啟用 DMM
- DMMScraper direct 模式設 `trust_env=False`，確保不繼承環境 proxy 變數
- DMM 內部三處 proxy guard 移除，可用性判斷統一由呼叫端控制

#### 📖 Help 頁面更新 (Phase 37d-T4)
- 搜尋功能：Lightbox 新欄位 + 劇照按鈕說明
- Scanner：字幕檔自動偵測與搬移說明
- Showcase：Lightbox/Table 新欄位 + 劇照按鈕說明
- Scraper 來源：預設搜尋來源 / DMM 模糊搜尋 / Proxy direct 模式說明
- 疑難排解：DMM 段落補充 direct 說明

### Changed
- 測試總數 1324 → 1366（+42）

## [0.5.4] - 2026-03-28

### Added

#### 🏭 Maker 名稱對照表重建 (Phase 37c)
- `maker_mapping.json` 改為雙層格式（name_mapping + prefix_mapping），合併 DMM 72 筆名稱對照
- 新增 `core/maker_mapping.py` shared loader 模組，統一供 search / showcase / scraper 共用
- `/search` 路徑：`Video.to_legacy_dict()` 自動套用 name normalize（片假名/英文長名 → 短名）
- `/showcase` 路徑：`normalize_maker()` 改為兩步查詢（name mapping 優先 → prefix fallback）
- gfriends lookup 補齊 SCOOP → x-KMP 對應

### Changed
- 測試總數 1280 → 1324（+44）

## [0.5.3] - 2026-03-28

### Added

#### 🖼️ Sample Gallery 元件 (Phase 37b)
- extrafanart/ 本地圖片接入 Showcase Lightbox（scanner 掃描 → DB → API 全鏈路）
- 全新 `sample-gallery` overlay 元件：大圖瀏覽 + 縮圖列 + GSAP slide 動畫
- Showcase Lightbox 新增「查看樣品圖 (N)」入口按鈕
- /search Grid Lightbox 同步新增入口按鈕
- /search Detail 模式舊 sample-lightbox 完整替換為 sample-gallery
- 鍵盤導航（ESC/←/→）+ 觸控 swipe 手勢 + Reduced Motion 降級
- DB schema migration 自動補齊 `sample_images` 欄位

### Changed
- 測試總數 1250 → 1280（+30）

## [0.5.2] - 2026-03-27

### Added

#### 🔗 Metadata Pipeline 補齊 (Phase 37a)
- NFO 讀寫補齊 director/duration/series/label 四個欄位，從 Scraper 到 DB 全鏈路流通
- `parse_nfo()` 新增讀取 `<runtime>`、`<director>`、`<set><name>`、`<label>` 標籤
- `VideoInfo` dataclass 新增四欄位 + `from_dict()` 防禦性過濾未知 key（舊 cache 向下相容）
- DB schema migration 自動補齊 `director`、`label` 欄位（ALTER TABLE）
- `_get_columns()` 改為 PRAGMA 動態查詢（新舊 DB 欄位順序自動對齊）

#### 📝 NFO 批量更新擴充
- `nfo_updater` 補齊 director/duration/series/label 寫入（含 `<set><name>` 巢狀結構）
- `needs_update()` 新增四欄位缺失檢查（duration 用 `is None` 防 0 短路）

#### 🖥️ Showcase 新欄位顯示
- Grid info panel 新增系列 + 片長（有值才顯示）
- Table mode 新增「導演」「片長」兩欄
- Lightbox 新增 director/duration/series/label 四欄位（可點擊搜尋）

#### 🔍 Search Lightbox 新欄位
- Main Lightbox 新增 director/duration/series/label 顯示（有值才顯示）

### Changed
- 測試總數 1171 → 1250（+79）

## [0.5.1] - 2026-03-27

### Added

#### 🔍 DMM Scraper 增強 (Phase 36-1)
- DMM 精準搜尋補齊所有新欄位（director、duration、label、series、sample_images）
- DMM 模糊搜尋實作（legacySearchPPV 關鍵字搜尋，支援日文女優名/片商名）
- DMM 模糊搜尋 per-item enrichment（逐筆補齊完整欄位）
- DMM 模糊搜尋漸進 SSE 回報（ThreadPoolExecutor + as_completed 即時回傳）

#### ⚙️ 來源優先設定 (Phase 36-2)
- Config 新增 `primary_source` 設定（javbus/dmm 切換）
- Facade 層精準搜尋 merge 優先權依設定切換
- DMM 模糊搜尋路由 + 無 proxy 自動降級至 JavBus
- Settings UI 新增「主要來源」radio 切換（JavBus/DMM）
- Detail 模式新增 Source Link 按鈕（復用 Lightbox source_links config）

#### 📊 其他來源欄位補齊 (Phase 36-3)
- Jav321 補齊 maker、duration、series、sample_images
- AVSOX 補齊 duration、series
- HEYZO 補齊 duration、series、sample_images（tags 一併修正）
- FC2 補齊 sample_images
- D2Pass 補齊 duration、series、sample_images + caribbeancom HTML fallback

### Fixed
- DMM sample images 升級為高解析度（CDN URL pattern `-N.jpg` → `jp-N.jpg`）
- DMM sample images URL regex 加 negative lookbehind 防止雙重轉換
- DMM 模糊搜尋 hero card `_mode` 修正（`fuzzy` → `actress`）
- HEYZO XPath 修正（duration / gallery / tags / series 全部匹配真實 DOM）
- D2Pass caribbeancom JSON 404 時 HTML fallback 解析完整 Video

### Changed
- 測試總數 1073 → 1171（+98）

## [0.5.0] - 2026-03-25

### Added

#### 🔧 JavBus Scraper 完全重寫 (Phase 35-1)
- 移除 jvav 第三方依賴，自行實作 JavBus scraper（requests + BeautifulSoup）
- 精準搜尋支援所有欄位解析（欄位名 mapping，非位置推斷）
- 模糊搜尋實作（關鍵字 / 前綴 / 女優名搜尋，含分頁支援）
- 多語言預留（zh-tw / ja / en，預設繁中）
- actress_scraper 同步移除 jvav，改用自建 searchstar 請求

#### 📊 Video Model 擴充
- 新增 director（導演）、duration（片長）、label（發行商）、series（系列）、sample_images（樣品圖像）欄位
- Merge policy 擴充 — source=auto 模式下新欄位不被丟棄

#### 🖼️ Sample Images Gallery + Lightbox (Phase 35-2)
- Detail 模式封面下方新增 sample images 縮圖列（水平可滾動）
- 點擊縮圖開啟 Sample Lightbox（純圖模式，左右鍵 / swipe 切換，計數器顯示）
- 方向鍵語意不變 — Detail 模式下左右永遠切換影片，Lightbox 內切換 sample

#### 📋 Detail 模式新增欄位展示
- 搜尋頁 Detail 模式展示導演、片長、發行商、系列（有值才顯示）

#### 📦 Organizer NFO 擴充 + extrafanart
- NFO 新增 `<runtime>`、`<director>`、`<set>`（系列）、`<uniqueid>`
- jellyfin_mode 時自動下載 sample images 至 `extrafanart/` 子目錄

#### 🧪 測試基礎設施
- 首次引入 Playwright E2E 測試（`tests/e2e/`）— Detail 新欄位、Sample Lightbox、方向鍵導航
- JavBus Smoke Test — 精準搜尋新欄位驗證 + 模糊搜尋 + 多語言 tags 差異
- 測試總數 1007 → 1073（+66）

### Changed
- JavBus / JavDB title 剝除番號前綴（統一顯示）
- CI workflow 排除 e2e 測試（需 Playwright 環境）
- 一般開發測試命令更新為 `-m "not smoke and not e2e"`

### Fixed
- JavBus actresses 解析補 next-`<p>` fallback（部分頁面結構差異）
- extrafanart 覆蓋修正（已存在時不重複下載）
- Sample Strip 比例縮放 + Alpine 初始化修正 + Active 高亮
- 跨頁分頁結果排序 + logger 補齊

### Removed
- **jvav 第三方依賴完全移除**（requirements.txt、mypy.ini、actress_scraper、facade 層）

---

## [0.4.4] - 2026-03-19

### Added

#### 🎨 Lightbox 按鈕重設計 (Phase 34-4)
- Showcase Lightbox 按鈕從 footer 文字改為封面上 glass circle overlay（hover-reveal）
- Search Lightbox 新增完整 metadata panel（標題、演員、番號·片商·日期、標籤）
- Search Lightbox 新增 glass circle 按鈕（返回詳情 / 開啟資料夾 / 來源頁面）
- Source Link 瀏覽器按鈕 — 依 config `source_links` 控制（正版來源預設開啟）
- Actress mode 簡化版 Lightbox（僅封面 + 返回詳情按鈕）
- CSS tooltip + aria-label + focus-visible 無障礙支援

#### 📦 安裝升級改善
- install.ps1 / install.sh 升級時自動清除舊版 `python/` 目錄（避免套件混版）
- README 新增 ZIP 手動安裝升級說明

#### ⚙️ Config source_links
- 新增 `source_links` 設定區段（8 個來源開關，正版預設 true）
- 深層合併 migration — 既有用戶自動補齊新設定、不覆蓋已有值

#### 🔧 PyWebView API
- 新增 `open_url()` — 系統瀏覽器開啟 URL（http/https scheme 限制）

### Changed

#### 🧹 程式碼品質清理 (Phase 34-3)
- 死碼清理 — `sys.path.insert` 殘留、unused wrapper、dead import 移除
- Logger 統一 — 全站改用 `core.logger.get_logger`
- SSE Helper 統一 — scanner.py `send()` 提取為 `_sse_event()`
- Showcase GSAP 歸位 — `core.js` 直接 GSAP 呼叫移至 `animations.js`
- Config 模組抽取 — `load_config`/`save_config` 從 router 移至 `core/config.py`

#### 🧪 測試與 CI
- 測試結構歸位 — 6 孤兒測試移入 unit/integration/smoke 正確目錄
- 測試品質提升 — 重複 setup 消除 + 弱斷言加強
- CI test.yml 修正 — pytest 涵蓋根目錄 + cache 版本隔離
- 測試總數 974 → 1007（+33）

### Fixed

#### 🔒 安全加固
- 2 處 exception 洩漏修復（str(e) → 固定訊息）
- SSE 洩漏封堵 + smoke 斷言補強
- Source Link 前端 scheme 驗證 + noopener,noreferrer 防護
- open_url macOS/Linux returncode 檢查
- 封面載入失敗時 Lightbox 按鈕仍可操作

---

## [0.4.3] - 2026-03-13

### Added

#### 📺 流暢轉場動畫系統完善
- Showcase 和搜尋頁面轉場動畫
- 分頁、篩選、排序時自然過渡
- 載入時柔和脈衝效果
- 詳細面板淡入淡出
- 模式切換流暢動畫

### Changed

#### 🚀 安裝體驗全面改善
- 自動化安裝腳本（curl / PowerShell）— 無需手動解決系統安全限制
- README 新增詳細 5 步手動安裝流程
- 新增 Debug 腳本（Windows OpenAver_Debug.bat / macOS OpenAver_Debug.command）

### Fixed

#### 💎 穩定性與效能
- 修正 Showcase/Search 頁面 lightbox 閉包競態（closeLightbox 改用 250ms delayed clear，高延遲環境不再短暫閃爍）
- 修正初始載入時的畫面閃爍
- macOS launcher 完全脫離 TTY（nohup 實作）
- 大量資料（6000+ 筆影片）時頁面反應更快
- OpenAver_Debug.command 補充環境變數（OPENAVER_DEBUG=1）
- README 疑難排解大幅擴充（Windows/macOS 分別說明）

---

## [0.4.2] - 2026-03-11

### Added

#### 🎬 GSAP Showcase 動效系統 (Phase 33)

**Showcase 頁面全面 GSAP 動效**
- 初始載入 Settle 動畫（scale pulse，不碰 opacity 不閃爍）
- 分頁切換 stagger out/in + 自動 scrollTo 頂部
- 篩選進出場 Flip 動畫（onEnter/onLeave）
- 排序洗牌 Flip 動畫（captureFlipState + reorder）
- 模式切換 crossfade（Grid/Table/List 淡入）
- Lightbox 開啟/關閉/切換 GSAP 動效 + animating guard

**Search 頁面動效增強**
- Lightbox GSAP 動效（open/close/switch）
- 頁面返回 Settle 動畫（與 Showcase 一致的 scale pulse）
- playGridSettle C21 防護（clearProps + onInterrupt）

**Motion Lab 沙盒**
- 新增 /motion-lab 頁面，用於動畫原型開發與調參
- 包含：初始載入、排序洗牌、篩選進出場、分頁切換 demo

### Changed

#### ⚡ Alpine 效能優化

- **F1**: `videos[]` / `filteredVideos[]` 移出 Alpine reactive scope，改為 closure 變數（6000 筆不再建立 Proxy）
- **F2**: Grid mode 禁用 perPage=0「全部」選項，三個攔截點自動降級為 120

### Fixed

#### 🐛 閃爍根治

- **F3**: `playSettle` 取代 `playEntry` 初始載入（scale-only pulse，不碰 opacity → 不閃）
- **F3**: 移除 `x-init="init()"` 雙重呼叫（Alpine 3 自動呼叫 init 方法，同時存在導致 double init）
- **CI**: `TestIsVideoFile` 在 Ubuntu CI 缺 pywebview 時 skip（Windows-only 套件）

#### 🧪 測試套件整合 (Phase 32)

- **U12**: 影片副檔名統一 — `core/video_extensions.py` Single Source of Truth
- **U13**: 測試去重 + conftest 統一 + 結構歸位（778 → 740 tests）
- **U14**: 覆蓋率補強（740 → 803 tests）— validators / scanner / config / API 安全
- **U15**: 品質修正 — 弱斷言加強 + 過大測試拆分

## [0.4.1] - 2026-03-08

### Changed

#### 🧪 測試套件整合 (Phase 32)

**U13 — 去重 + conftest 統一 + 結構歸位**
- 刪除 `test_smoke.py` 與 `test_scraper_parser.py` 重疊的 76 個測試（778 → 740）
- `make_client(mock_targets)` / `make_populated_db(videos)` factory fixture 統一至 `tests/unit/conftest.py`
- `test_scrapers.py` 連外測試加 `@pytest.mark.smoke` 標記
- 4 個重複 scraper search tests 合併為 `@pytest.mark.parametrize`

**U14 — 覆蓋率補強**
- 新增 `test_scraper_validators.py` — `is_number_format` / `is_partial_number` / `is_prefix_only` 邊界測試
- 新增 `test_gallery_scanner.py` — `parse_nfo` / `parse_filename` / `find_cover_image` 測試
- 新增 `test_api_config_endpoints.py` — Tutorial flow + DELETE config 整合測試
- 新增 `test_api_scanner.py` — `/api/gallery/video` 安全測試（403 invalid ext/dir）+ player 測試
- 覆蓋率 740 → 803（+63 tests）

**U15 — 品質修正**
- 拆分 6 個過大測試（17/17/11/20/15/11 assertions → 各 3+ 小測試）
- 弱斷言加強：`len()>0` → 驗具體值/結構，`is not None` → 驗型別/欄位
- `test_init_db_creates_table` 加 PRAGMA schema 驗證
- `test_scrapers.py` 連外測試加強結構驗證（Actress/str 型別檢查）
- 最終測試數 817 passed, 18 deselected (smoke)

---

## [0.4.0] - 2026-03-08

### Added

#### 🎬 GSAP 搜尋頁動畫系統 (Phase 31)

**Motion Infrastructure**
- Motion Lab 沙盒頁（動畫選型與調參環境）
- GSAP 3.12→3.14 升版

**SSE 漸進搜尋協議**
- Backend SSE Protocol — seed + result-item + result-complete 三階段事件
- Frontend Skeleton Grid — seed 驅動 skeleton 卡片佈局
- `search_partial()` 漸進回傳支援（result_callback 透傳）

**Staging Card + Mini-Burst 動畫**
- Staging Card 蓄能 UI — 封面預覽 + 計數 badge + rotating border
- Mini-Burst 動畫 — 時間窗口 batching + 座標偏移飛入 grid
- Stream Buffer 機制 — debounce flush + final-burst race 修正

**Grid↔Detail 轉場**
- Ghost Shared-Cover Transition — FLIP 動畫 + crossfade fallback
- Detail Entry 動畫 — card full 進場 + info 滑入
- Detail Navigation Slide — 左右滑動 + C18 interrupt（killTweensOf，無 lock）

**Cover State Machine**
- `_resetCoverState()` 集中式重置（16 條路徑統一）
- `handleCoverError()` 雙階段 stale defense
- Cover loading shimmer + `_coverLoaded` lifecycle

**SearchAll 競態修正**
- `_searchFileBackground()` 背景搜尋方法（不碰共享 UI 狀態）
- `searchAll()` 並行安全（Promise.all 內只用背景搜尋）

**_failed Slot 完整處理**
- `display: none` 取代 `visibility: hidden`（CSS Grid 無留白）
- 導航/Lightbox _failed skip（navigate + prevLightbox + nextLightbox）
- 計數/canGo/navIndicator _failed-aware
- `hasVisiblePrev()` / `hasVisibleNext()` Lightbox 箭頭方法

#### ⚙️ Settings 動畫
- Theme toggle 圓弧展開動畫

#### 🧪 測試
- `search_partial()` callback 行為測試
- searchAll race guard tests（6 new）
- C30 guard tests（9 new）— navigate/lightbox/canGo/counts/repoint
- 測試總數 731

### Changed
- 後端 `search_prefix`/`search_actress` 統一 title 過濾（拒絕空殼結果）
- File search 動畫整合（searchForFile → playDetailEntry, switchToFile → playSlideIn）

### Fixed
- Grid→Detail 封面偶發消失（ghost opacity 殘留 + 快取不觸發 @load）
- Cover state machine：switchSource reset + empty coverUrl guard
- searchAll 競態：背景搜尋不碰 currentFileIndex/searchResults/displayMode
- _failed repoint 條件式修正（不覆蓋使用者已選中的項目）

---

## [0.3.6] - 2026-02-20

### Fixed

#### 🔗 UNC 路徑修正 (Phase 29)
- **`to_windows_path()` 正斜線 UNC 支援** — `//server/share/...` 正確轉換為 `\\server\share\...`，修復 NAS 影片播放、開啟資料夾、Scraper 拖入失敗
- **`to_windows_path()` 全反斜線輸出** — `C:/path` 一律轉為 `C:\path`，Windows Explorer 等原生 API 需要反斜線
- **Showcase CI 11 tests 修復** — 移除多餘 `normalize_path()` 疊加，`to_file_uri()` 直接處理所有路徑格式
- **`organize_file()` 安全修正** — PermissionError 獨立捕捉 + `str(e)` 改固定中文訊息，防止內部錯誤細節洩漏

### Added
- **UNC 路徑守衛測試** — `to_windows_path()` 正斜線 UNC / 多餘斜線正規化 / 雙向一致性
- **WSL `/mnt/c/` → `file:///C:/` 整合測試** — 路徑轉換端到端驗證
- **`organize_file()` 安全測試** — PermissionError + Exception 不洩漏原始訊息
- **回歸守衛測試** — `to_file_uri()` 跨平台直通（不依賴 `normalize_path`）
- **靜態守衛強化** — 掃描範圍收窄 + regex 比對精確化
- **CLAUDE.md 路徑 Gotchas** — 文件化 `normalize_path + to_file_uri` 疊加陷阱、`to_windows_path` 全反斜線保證
- `AGENTS.md` — Codex bot code review 指引

---

## [0.3.5] - 2026-02-20

### Added

#### 🏷️ 版本標記與覆蓋保護 (T1)
- suffix_keywords config + `{suffix}` 格式變數 — UC/LEAK/4K 等標記自動偵測
- Search suffix badge + 覆蓋引導彈窗 — 已有檔案時提示用戶確認
- Scraper API duplicate response — 覆蓋保護傳前端

#### 📦 Fallback 空值防護 (T2)
- `format_string()` fallback — 資料夾層級空值時自動降級，避免空資料夾
- scrape response fallback warning toast — 刮削空值欄位提示

#### 🌐 批次翻譯 (T3)
- translateAll() — 雲端搜尋模式批次翻譯按鈕 + 翻譯 icon 藍色化

#### 📂 系統檔案管理員整合 (T5)
- openLocal() — Search Detail/Grid + Showcase 統一「開啟資料夾」功能
- PyWebView API `open_folder()` — 系統檔案管理員開啟

#### 🖼️ Jellyfin 圖片模式 (T6)
- crop_to_poster() + organize_file() — Jellyfin 圖片自動生成
- Scanner Jellyfin 圖片批次補齊 — SSE 串流 + 偵測邏輯
- NFO poster/thumb/fanart 標籤修正 — .png→.jpg + Jellyfin 後綴

#### 🔗 路徑工具統一 (T7)
- `uri_to_fs_path()` — 新增 file:// URI → FS 路徑轉換
- 前端 `pathToDisplay()` — 統一路徑顯示格式
- Path Guardrails 守衛測試 — 路徑違規清零

#### 🎨 Design System 補齊 (T8)
- DS 圖示庫補齊 — 21 個缺漏 icon
- DS 色盤補齊 — `--color-warning-content` + `--color-translate` token
- DS 元件補齊 — suffix-badge / override modal / toast warning / mini-terminal
- DS 文件補齊 — Showcase Toolbar + Jellyfin Image Row

#### ⚙️ Settings / Help 重構 (T4, T9)
- Settings 簡化 — 移除版本/更新/新手引導，viewerPlayer 併入系統設定
- Help 全面重構 — hero card + Alpine 檢查更新 + 新增區塊（格式變數/Showcase/Scraper 來源）
- 檔名長度限制 Help Icon — 路徑長度說明浮動面板

#### 🗑️ Scanner 清除快取
- 清除快取 icon + DaisyUI modal 兩步確認 + DELETE API

### Changed
- `folder_layers` 預設改為 `{actor}`
- Toast 描述四種變體 + snippet `#d4d4d4` token 化

### Fixed

#### 🔒 安全加固 (28-4)
- **str(e) 外洩修正** — 7 個 router 共 27 處 `str(e)` 改為固定中文訊息 + server-side log
- **語意版本比較** — tuple 比較取代字串比較，支援 prerelease strip
- **SSE onerror guard** — 正常關閉不再觸發假「連線中斷」錯誤 (×3 處)
- **restoreState() crash** — optional chaining 保護已遷移函式呼叫
- **check-update 硬上限** — `asyncio.wait_for()` 防止 DNS 失敗無限等待
- **logger.exception** — translate.py 保留 traceback 便於排錯

#### 🧪 測試品質提升 (28-4)
- 共用 `tests/unit/conftest.py` — 消除 4 檔重複 fixture
- `test_frontend_lint.py` 相對路徑修正
- `test_api_gallery.py` 斷言加強 — 消除永遠 pass 的弱斷言
- 測試總數 523 → 564（+41）

---

## [0.3.3] - 2026-02-19

### Added

#### 🔍 Scraper 來源擴充 (Phase 27)
- **D2PassScraper** — 1Pondo / Caribbeancom / 10musume 三站聯合無碼爬蟲（共享 JSON API）
- **HEYZOScraper** — JSON-LD + HTML table 解析
- **DMMScraper** — GraphQL API + 日本 IP Proxy 支援（從 feature/ 遷移至 core/scrapers/）
- DMM Tags — GraphQL `genres` 探測（Capability Cache）+ HTML fallback 雙路徑
- Settings Proxy 欄位 — DMM HTTP Proxy 輸入 + 測試連線按鈕
- Settings Source Badge — 有碼/無碼來源 tag-badge 狀態顯示（取代純文字 hint）
- Fast-Path 前綴路由 — FC2/HEYZO 搜尋省掉無謂 D2Pass request
- `extract_number()` 擴充 — 支援底線格式 `DDMMYY_NNN`（1Pondo/10musume）
- 未知 source 白名單驗證 — `search_jav` 回傳 None + API 400
- 新增 `tests/test_new_scrapers.py`（D2Pass/HEYZO/DMM/Pipeline/Fast-Path 共 41 測試案例）

#### 👤 Grid 模式女優資料卡增強 (Phase 26)
- **gfriends 圖片查表** — 最高優先女優頭像來源（GitHub CDN）
- **Graphis Profile 文字解析** — 英文名 / 身高 / 三圍 / 興趣
- Lightbox 導航修正 — 女優頭像可方向鍵移動到封面
- 新增 16 測試案例（gfriends lookup + Graphis text parsing）

### Changed
- Uncensored 偵測擴充 — 支援 HEYZO 前綴 + D2Pass 日期格式
- Uncensored mode 路由擴充 — D2Pass → HEYZO → FC2 → AVSOX
- DMM Top-1 優先順序 — proxy 有值時 DMM 排有碼第一
- Regex 統一 — `\d{6}[-_]\d{2,}` 三處一致（extract_number / is_uncensored × 2）
- `folder_layers` 預設改為 `{actor}`

### Fixed
- Caribbeancom + 1Pondo 封面 fallback — `ThumbHigh` 為 null 時構造 URL
- HEYZO JSON-LD list guard — `@graph` 陣列格式防禦
- DMM empty prefix guard — 空 prefix 不發無謂 request
- JavGuru 移除 — HTML 結構不穩定 + 封面 CDN 失效

### Removed
- JavGuru scraper（HTML 結構不穩定，封面 CDN 失效）
- Settings 來源純文字 hint（改為 Source Badge）

---

## [0.3.2] - 2026-02-18

### Added

#### 🎨 GSAP 前置準備 + Fluent Material Boost (Phase 25)

**Motion Infrastructure (T1–T6)**
- `motion-prefs.js` — `matchMedia` reduced-motion JS 橋接（`OpenAver.prefersReducedMotion`）
- `motion-adapter.js` — 共用 GSAP 封裝（`playEnter` / `playLeave` / `playStagger` / `playModal` + `createContext` 生命週期清理）
- GSAP 3.12.5 CDN 載入（base.html，在 Alpine 之前同步載入）
- `TestMotionInfra` 守衛測試（motion-prefs / motion-adapter / 載入順序 / 無直接 gsap 呼叫）

**Design System 同步清理 (T7)**
- Hero Card 女優資料卡展示
- Toast 變體對照表（fluent-toast / search-toast / settings-toast）
- File Item 5 狀態動態控制展示

**Fluent Material Boost (T8)**
- Canvas Layer（Mica 氛圍背景）— 全頁 radial-gradient + SVG noise overlay（light/dim 各一組）
- Shell Acrylic — Sidebar `backdrop-filter: blur(30px) saturate(140%)` + Offcanvas `fluent-acrylic`
- `.fluent-toolbar` utility class（blur 16px + saturate 130%）
- Surface Elevation — 卡片 `inset 0 1px 0` 頂部高光 + Fluent shadow 層次分離
- `help.css` 新建 — Help 頁卡片材質統一
- Design System Materials Layer System 展示（Canvas / Shell / Surface 三層 demo + 對照表）

### Changed
- Scanner `$refs` fallback 移除（4 處 `getElementById` → `this.$refs`）
- Search `$refs` 遷移（3 處 `getElementById` → `$refs` / Alpine state）
- `@keyframes spin` 統一至 theme.css（移除 search.css / settings.css / design-system.css 重複）
- `--ds-glow-rgb` 變數化 — 全站 18 處 `rgba(90, 200, 250, ...)` → `rgba(var(--ds-glow-rgb), ...)`
- Settings `.card` border-radius 硬編碼 `16px` → `var(--radius-lg)` token
- Settings `.card` shadow-sm → shadow-4 + inset 高光 + stroke-default
- Scanner `.mini-terminal` dim mode 實色 → `color-mix` 半透明
- Search bar `backdrop-filter` 從 `blur(10px)` 升級至 `blur(16px) saturate(130%)`
- Settings/Scanner header 新增 Acrylic 材質（backdrop-filter + border-bottom）
- Sidebar 實色背景 → `color-mix 75%` 半透明 + Acrylic
- Offcanvas `bg-base-200` → `fluent-acrylic`

### Fixed
- Scanner/Showcase 只顯示當前設定資料夾的影片（DB 保留全部當 cache）
- Ollama 翻譯 prompt 重構 — system message + few-shot 解決漢字重標題輸出日文問題
- Ollama `num_predict` 100→500 — think mode 模型推理耗盡 token 導致無回應
- JavDB「發行日期」誤判為片商 + maker 快取日期值防護
- macOS README 解壓路徑修正
- macOS 打包移除 Alpha 標記 — 正式版命名

### Removed
- Design System Legacy 區塊（Bootstrap Buttons/Card/Tabs、未使用的 av-card-thumbnail/compact）
- Design System 重複展示（Shadow Grid、NavRail Expanded、舊版 Toast）

---

## [0.3.1] - 2026-02-11

### Added

#### 🖼️ Showcase 動態化 (Phase 24-2)
- `/api/showcase/videos` API 端點 — SQLite SSR 取代靜態 iframe
- `showcase.html` 全面重寫 — Image Grid + Detail Table + Text List 三種顯示模式
- Lightbox 元件 — Smart Close + metadata + 鍵盤導航
- Card hover footer + glass button overlay
- Toast 通知系統（Design System fluent-toast）
- 搜尋邏輯（多關鍵字 AND + 模糊番號匹配）
- 排序邏輯（8 種欄位 + asc/desc + random 洗牌）
- 快捷鍵完整實作 + 底部提示列
- Config 整合 + 狀態持久化（localStorage + URL state）
- Status bar 影片統計 + 分頁控制
- Showcase API 單元測試（12 cases）

#### 🔀 Alpine.js 全站遷移 (Phase 24-3)
- Search 結果改用 AV Card Full 統一卡片
- Settings Alpine.js 狀態管理（主題 toggle + dirty check + fluent-modal）
- Scanner Alpine 基礎架構（資料夾管理 + SSE 串流 + 女優別名 + Log Terminal 增強）
- Sidebar 純 localStorage 驅動（消除收合閃爍）
- 全站字體大小 5 階調整 + configSync 即時同步
- Settings 格式變數 dropdown 簡化（tag-badge + 預覽列）

#### 🎯 Search Grid Mode + 女優資料卡 (Phase 24-4)
- Alpine 骨架 + 狀態容器 — `state.js` 1734L 單檔拆為 9 個 mixin 模組
- 搜尋流程 + 導航遷移至 Alpine（SSE/REST/navigate/loadMore）
- 結果卡片 template binding 取代 `displayResult()`
- 檔案列表 + 拖拽遷移至 Alpine（x-for/computed）
- Grid Mode — 封面牆 + Lightbox + 女優自動切換
- 女優資料卡（Graphis + JavBus 雙來源並行 + Detail Banner + Hero Card）
- 本地匹配提示 + Rotating Border 動畫
- 搜尋進度豐富化（來源名稱 + 完成提示）

#### 🔍 D.6 最終驗收 (Phase 24-5)
- 前端遷移守衛測試 `test_frontend_lint.py`（靜態分析 4 類規則）
- `_syncToCore()` 統一 helper — 集中 29 處 coreState 同步
- GSAP 就緒度報告

### Changed
- 全站 Alpine.js 統一 — 零 vanilla inline handler、零 Bootstrap 殘留
- `theme.css` 硬編碼 hex / rgba → CSS 變數 + `color-mix()` 語法統一
- `design-system.css` 13 處 hex → CSS 變數（`--gradient-cyan/indigo/purple`）
- Settings theme toggle 只保留 icon（移除 Light/Dim 文字）
- `/search` copyPath 統一複製資料夾路徑（與 `/showcase` 一致）
- `[LOCAL FALLBACK]` 標記語義化為 `[API FALLBACK]`
- Showcase 從靜態 iframe 改為 SQLite SSR 動態頁面

### Fixed
- Windows cp950 編碼全面修復（`print()` → `logger` + `PYTHONUTF8`）
- Rotating Border 本地匹配從轉 1 圈改為 5 圈
- NFO 補全 cache 漏傳 `nfo_mtime` 導致永遠不觸發
- Sidebar 收合閃爍（純 localStorage + inline script 同步）

### Removed
- 舊 iframe Gallery 端點 / service / JS / CSS
- 所有 vanilla inline event handler
- Bootstrap 殘留 class（零殘留確認）
- `[LOCAL FALLBACK]` 標記

---

## [0.3.0] - 2026-02-08

### Added

#### 🔄 Bootstrap → DaisyUI 全站遷移 (Phase 24)
- DaisyUI + Tailwind CSS 取代 Bootstrap 5，完成前端框架替換
- Alpine.js 取代 Bootstrap JS（sidebar、offcanvas、collapse、toast）
- Design System 3 套 scope 機制（`.ds-page` / `.ds-gallery-composition` / `#settings-components`）
- `.text-muted` utility class（綁定 `--text-muted` 變數）

#### 📁 路由改名 `/gallery` → `/scanner`
- 頁面路由語義化：Scanner = 掃描 + 列表生成
- `/gallery` 自動 302 重定向到 `/scanner`（向後相容）
- Config `default_page: "gallery"` 自動映射到 `/scanner`

#### 📦 JS 模組化
- Settings inline JS 抽離為 5 個獨立模組（core/translate/folders/format/init）
- Scanner inline JS 抽離為 4 個獨立模組（core/alias/folders/init）

### Changed
- 所有頁面使用 DaisyUI 元件（btn/input/select/toggle/card/badge/alert）
- Bootstrap grid（`.row`/`.col-md-*`）→ Tailwind grid/flex
- Bootstrap form（`.form-control`/`.form-select`/`.form-check`）→ DaisyUI
- `settings.html` `container-fluid` 移除、`card-header` → `settings-card-header`
- `search.css` 移除 29 行與 theme.css 重複的 `.state-page` + `.empty-actions`
- `showcase.html` 加入 `.ds-page` scope 啟用 Design System 狀態元件
- Settings 排序區塊脆弱 selector `div[style*=...]` → `.sort-row` 語義 class
- Tailwind CSS 重新編譯（v4.1.18 + DaisyUI 5.5.17）

### Removed
- Bootstrap CSS CDN（保留 Bootstrap Icons）
- Bootstrap JS CDN
- `[LOCAL FALLBACK]` 標記（函數保留作為 API fallback 機制）
- `web/routers/gallery.py`（重命名為 `scanner.py`）

---

## [0.2.4] - 2026-02-07

### Added

#### 🎨 Design System (Phase 23)
- `/design-system` 頁面展示所有 UI 元件
- Fluent Design 2 視覺語言（毛玻璃、12px 圓角、複合陰影）
- 統一圓角 Token 系統（`--radius-xs/sm/md/lg/pill`）
- Space Grotesk 字型用於標題
- AV Card 4 種變體（Thumbnail/Preview/Full/Compact）
- 背景光暈 + 噪點紋理視覺效果

#### 🧩 Design System Phase 23-4
- Toast 元件（4 種語意色 + 3 段倒計時動畫 + hover 暫停）
- Button 元件（Primary/Secondary/Ghost/Outline/Icon/Link 6 種變體）
- Help 頁面元素（鍵盤快捷鍵表 + Kbd 尺寸變體）
- Focus-visible 統一規則 + reduced-motion 無障礙收斂
- Search / Gallery Page Composition 頁面級 Mockup
- Settings 特殊元件展示（收合區塊 + 變數插入 Dropdown）

### Changed
- Dark mode 文字對比度修復
- Gallery Card hover 改為右側聚焦（`transform-origin: 65% center`）
- Hex 色彩顯示動態讀取 CSS 變數
- README 翻譯速度說明更新（Ollama 5s → 0.5s）
- 硬編碼色彩 / 圓角 / rgba 全面替換為 Fluent Design Token
- `transition: all` 替換為具體屬性（效能優化）
- 所有動畫 easing 統一使用 Fluent Token（`--fluent-ease-standard` / `--ease-out`）
- 暖奶白底色回歸（`--color-base-100: oklch(98.5% 0.005 85)`）
- Card 圖片圓角對齊：底部接觸 footer 處改為直角

### Removed
- 刪除廢棄測試腳本 `test_task2_integration.sh`

---

## [0.2.3] - 2026-01-23

### Added

#### 📁 Gallery 搜尋增強
- Gallery HTML 搜尋支援路徑名稱（`v.path`）
- 可用舊女優名搜尋（即使已改名，檔名路徑仍保留原名）

#### 📋 本地標記互動
- 點擊 📁 badge 複製檔案路徑到剪貼簿
- 多版本時複製全部路徑（換行分隔）
- Toast 提示複製成功/失敗

---

## [0.2.2] - 2026-01-22

### Fixed

#### 🔧 後綴清理（檔名 + 搜尋查詢）
- `extract_number()` - 從檔名提取番號時清理 -UC/-UNCEN/-UNCENSORED/-LEAK/-LEAKED 後綴
- `is_number_format()` - 搜尋查詢格式驗證時清理後綴
- `normalize_number()` - 番號正規化時清理後綴
- 後綴必須有分隔符（`-` 或 `_`），避免誤刪 JUC-123 等合法前綴
- 檔名 `SONE-103-UC.mp4` 和搜尋查詢 `SONE-103-UC` 現在都能正確處理

### Added

#### 🧪 整合測試
- 新增 `TestSearchQueryIntegration` 測試類，驗證搜尋流程完整性
- 新增 JUC-123 回歸測試，防止前綴誤刪

---

## [0.2.1] - 2026-01-22

### Added

#### 🔍 FC2 / Uncensored Search
- FC2-PPV number search support
- Caribbeancom / 1Pondo uncensored numbers
- AVSOX scraper for uncensored content

#### 🎯 Uncensored Mode Toggle
- Settings page switch to search AVSOX / FC2 only

#### 🗄️ Local Library
- SQLite database tracks scanned videos
- Search page shows "in library" green dot indicator
- Actress alias management (auto-apply during scan)
- User tags (saved to NFO)

### Changed
- Scraper architecture modularized (Phase 16)
- Frontend logic moved to backend APIs (Phase 17)
- Test framework expanded to 311 cases
- Tutorial samples: added FC2-PPV-1723984 (11 total)

### Removed
- DMM scraper temporarily removed (requires Japan IP)

---

## [0.4.0] - 2026-01-21

> ⚠️ Merged into 0.2.1

### Added

#### 🗄️ SQLite Data Layer (Phase 18)
- SQLite database with WAL mode for local video metadata
- Gallery Scanner stores video info (path, number, actresses, mtime)
- `/search` page shows local status indicator (green dot = already in library)
- Actress alias management (Settings page)
- Auto-apply aliases during Gallery scan
- User tags in `/search` (frontend state, written to NFO on generate)

#### 🔄 Thin Client Refactor (Phase 17)
- Business logic centralized to backend
- New `/api/parse-filename` endpoint for batch filename parsing
- `/api/translate` auto-skips non-Japanese text
- `/api/search/sources` returns unified source configuration
- Frontend simplified: removed duplicate logic (hasJapanese, extractNumber, etc.)

### Changed
- Test framework expanded to 315 test cases
- Frontend JS reduced complexity (uses backend APIs)

### Fixed
- Path format consistency in database (`file:///` URI)
- Alias application correctly reloads DB after NFO updates
- `/api/search/local-status` properly initializes database

---

## [0.3.0] - 2026-01-20

> ⚠️ Merged into 0.2.1

### Added

#### 🔧 Scraper Modularization (Phase 16)
- New `core/scrapers/` module with BaseScraper abstract class
- 5 modular scrapers: JavBusScraper, JAV321Scraper, JavDBScraper, FC2Scraper, AVSOXScraper
- Pydantic data models: Video, Actress, ScraperConfig
- Type hints throughout scraper modules

#### 🔍 Uncensored Search Mode
- FC2 番號搜尋支援 (FC2-PPV-XXXXXX)
- Caribbeancom / 1Pondo 無碼番號支援 (XXXXXX-XXX 格式)
- AVSOX 爬蟲專門處理無碼內容

#### 🎯 Precise Search Enhancement
- 精準搜尋支援指定來源 (javbus/jav321/javdb/fc2/avsox)
- 多來源同時查詢，自動合併結果

### Changed
- Scraper architecture refactored from monolithic to modular design
- Test framework expanded to 153 test cases
- Pydantic models updated to v2 ConfigDict syntax

### Removed
- DMM scraper temporarily removed (requires Japan IP, pending testing)
- Backup available at `/feature/dmm.py`

---

## [0.2.0] - 2026-01-18

### Added

#### 🍎 macOS Support (Alpha)
- macOS arm64 (Apple Silicon M1/M2/M3/M4) packaging support
- PyWebView + WebKit integration with full feature parity
- GitHub Actions automated macOS ZIP builds
- Gatekeeper bypass documentation

#### 🔄 Multi-Source Cycling
- New ⟳ button to cycle between javbus/jav321/javdb sources
- Lazy-load queries with caching to avoid duplicate requests
- Toast notifications when switching sources

#### 📁 Multi-Level Directory Structure
- Three-field input UI (outer/middle/inner layers)
- Cascading enable logic (right-to-left: inner→middle→outer)
- Real-time preview showing full path + filename
- "Create Folder" toggle linked to all fields

#### 🤖 AI Translation Enhancements
- Dual engine support: local Ollama and Google Gemini
- Gemini Safety Settings optimization (98-99% success rate)
- Translation service abstraction layer (Strategy Pattern)
- Gemini mode: click-to-translate only translates current item (API rate limit friendly)
- Recommended model: gemini-flash-lite-latest

#### ✨ UX Improvements
- Title edit field changed to textarea for multi-line display
- Settings page preview now updates in real-time
- Mixed-format number support (e.g., T28-103)

### Changed
- Translation provider UI improved: "Gemini (Google Cloud)" vs "Ollama (Local)"
- Test framework expanded to 126 test cases

### Fixed
- `/api/translate` endpoint now correctly supports Gemini provider
- Settings page preview displays correct values on load
- Cross-platform `open_file()` fix (macOS: `open`, Linux: `xdg-open`)

---

## [0.1.4] - 2026-01-17

### Added
- Tutorial Step 5: Guide users to try sample files immediately after onboarding
- Sample files folder ("教學檔案") included in Windows package with 10 searchable examples
- Comprehensive test framework (115 test cases: unit + integration + smoke)

### Changed
- Tutorial card now has "large" variant for final step emphasis
- Test samples moved to `tests/samples/` for cleaner project structure

---

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
