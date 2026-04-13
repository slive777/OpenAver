# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
