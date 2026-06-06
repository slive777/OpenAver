# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.7] - 2026-06-06

本版主軸：**VR 投影標籤保留 + 自動 VR tag**（feature/68），純後端、單檔 `core/organizer.py`、零新依賴、零 ZIP 影響、零 i18n、零 UI。問題根因：頭顯 App（DeoVR / HereSphere / Skybox / Pigasus）100% 靠「**檔名 token**」判斷 VR 投影/立體格式（`_180_LR` / `_3dh` / `mkx200`…），不讀 NFO；而 OpenAver 改名是用模板從頭重組檔名，原檔名的 VR token **不會被帶過來** → 改名後 VR 檔在頭顯 App 變成平面 2D 播放。本版讓改名時偵測原檔名的 VR token 並**原樣保留**到輸出檔名尾端，同時在 NFO 加一個 `VR` tag/genre。**無 toggle、無需用戶輸入；檔名無 VR token 時輸出 byte 級零變化**（2D 轉檔 / 一般片完全不受影響）。同梱兩處先前的小修正：`/static` no-cache 根治 stale cache、「Jellyfin / Emby 圖片模式」正名。

*This release's main theme: **VR projection-tag preservation + automatic VR tag** (feature/68) — pure backend, single file `core/organizer.py`, zero new deps, zero ZIP impact, zero i18n, zero UI. Root cause: VR headset apps (DeoVR / HereSphere / Skybox / Pigasus) decide projection/stereo format 100% from the **filename token** (`_180_LR` / `_3dh` / `mkx200`…), not from NFO; but OpenAver's rename rebuilds the filename from a template, so the original VR token was dropped → renamed VR files played flat 2D in the headset. Now the rename detects the original filename's VR token and **preserves it verbatim** at the end of the output filename, and adds a `VR` tag/genre to the NFO. **No toggle, no user input; output is byte-identical when there's no VR token** (2D transcodes / ordinary files are wholly unaffected). Also bundles two earlier small fixes: `/static` no-cache, and the "Jellyfin / Emby Image Mode" rename.*

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

---

## 0.5.x 系列 (v0.5.0 ~ v0.5.5, 2026-03-25 ~ 2026-03-28)

JavBus Scraper 完全重寫（移除 jvav 第三方依賴）+ Video Model 擴充（director/duration/label/series/sample_images）+ Sample Gallery 元件（extrafanart 全鏈路）+ Metadata Pipeline 補齊（NFO 讀寫全欄位）+ Maker 名稱對照表重建（雙層 JSON + shared loader）+ DMM 模糊搜尋 + 全來源欄位補齊（Jav321/AVSOX/HEYZO/FC2/D2Pass）+ 字幕檔自動偵測搬移 + Proxy direct 模式。測試數 1007 → 1366。

## 0.4.x 系列 (v0.4.0 ~ v0.4.4, 2026-03-08 ~ 2026-03-19)

GSAP 搜尋頁動畫系統（SSE 漸進搜尋 + Mini-Burst + Grid↔Detail 共享封面轉場 + Cover State Machine）+ GSAP Showcase 動效系統（Flip 排序 + stagger 分頁 + Motion Lab）+ Lightbox 重設計（glass circle overlay + metadata panel）+ Source Link 設定 + 安裝腳本升級 + 測試套件大整合（去重 + conftest 統一 + 覆蓋率補強）。測試數 731 → 1007。

## 0.3.x 系列 (v0.3.0 ~ v0.3.6, 2026-02-08 ~ 2026-02-20)

Bootstrap → DaisyUI + Alpine.js 全站遷移 + Showcase 動態化（SQLite SSR 取代靜態 iframe）+ Search Grid Mode + 女優資料卡（Graphis + JavBus 並行）+ Fluent Material Boost（Mica/Acrylic）+ GSAP 前置基礎建設 + Scraper 擴充（D2Pass/HEYZO/DMM/gfriends/Graphis）+ 路徑工具統一（uri_to_fs_path/pathToDisplay）+ UNC 路徑修正 + 版本標記覆蓋保護 + Jellyfin 圖片模式。測試數 523 → 817。

## 0.2.x 系列 (v0.2.0 ~ v0.2.4, 2026-01-22 ~ 2026-02-07)

Design System 建立（Fluent Design 2 視覺語言 + AV Card 4 變體 + Token 系統）+ macOS 支援（Alpha）+ AI 翻譯雙引擎（Ollama + Gemini）+ 多層目錄結構 + FC2/無碼搜尋 + SQLite 本地收藏庫 + Scraper 模組化架構（5 個獨立 scraper）+ 番號後綴清理修正。測試數 126 → 564。

## 0.1.x 系列 (v0.1.0 ~ v0.1.4, 2026-01-15 ~ 2026-01-17)

初始版本發布：多來源番號搜尋（JavBus/Jav321/JavDB）+ Gallery UI + 智慧搜尋 + 批次搜尋 + NFO 自動補全 + Settings（Dark Mode + Ollama 翻譯 + 輸出格式設定）+ 新手教學（Tutorial 4 步驟）+ Windows 打包 + 路徑工具統一（path_utils）+ 版本管理集中化。測試數 115 → 311。

> 完整歷史紀錄請見 [CHANGELOG_ARCHIVE.md](CHANGELOG_ARCHIVE.md)
