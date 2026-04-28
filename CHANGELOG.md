# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
