# E2E 用戶旅程劇本（v2 — 2026-05-14 align 後）

> 純文字劇本，**人類用瀏覽器手動 / AI 用 Playwright MCP** 皆可照跑。
> 對應 spec：`feature/59-onboarding-help-polish/spec-59.md` §8 + plan-59c.md
> **AI 首次操作前先讀 `app-guide.md`**（同目錄）了解各頁面操作方式。

---

## 執行方式

### Server 啟動

```bash
source venv/bin/activate && uvicorn web.app:app --host 0.0.0.0 --port 8000
```

### Playwright MCP Server 選擇

| Server | 用途 | 啟動方式 |
|--------|------|---------|
| `playwright`（headless） | Clean state 跑（無 cache）；CI-like 一致性；建議 US1–US4 用 | 已在 MCP config |
| `playwright-cdp`（CDP attach） | 視覺確認、需看動畫（US3 constellation / US5 photo enrichment）；共享 Chrome 已登入狀態 | Chrome 啟動加 `--remote-debugging-port=9222` |

**Risk-2 — Cache 黏性**：CDP attach 模式會沿用 Chrome ESM module map cache；改 JS 模組後 e2e 跑前用 Incognito 視窗或切 headless server。

### 執行時機

| 時機 | 範圍 | 時間 |
|------|------|------|
| Milestone pre-merge | US1–US7 全套（外部 API 失敗 skip 並記原因） | 10–20 分 |
| Release 前 | US1–US7 全套（保險） | 10–20 分 |
| Feature branch 含 template 改動 | 受影響的 US（1–2 個） | 5 分內 |

---

## 前置條件（所有 US 共通）

- Dev server 已啟動於 `http://localhost:8000`
- DB 已有至少 10 部影片（US3–US7 需要）
- 4 locale 翻譯檔齊全（US6 需要）
- Settings 已有預設搜尋來源（US7 需要）

每個 US 在 Setup 段列獨立重置指令；US 之間 state 殘留處置見 plan-59c §7 Risk-3。

---

## US1: 新手 Onboarding

**故事**：用戶第一次開軟體 → tutorial 自動觸發 → 7 步 spotlight 走完 → 完成狀態持久化（加資料夾 / 掃描 / Showcase 依賴 PyWebView picker，不在本 US；由 US2 / US3 涵蓋實際資料流）。

### Setup

- Dev server 已啟動於 `http://localhost:8000`
- 清 tutorial flag（browser_evaluate）：
  ```js
  localStorage.removeItem('openaver_tutorial_completed');
  ```
- 確認後端 `config.json` 中 `general.tutorial_completed = false`（或無此 key）；可呼 `GET /api/tutorial-status` 確認 `{"completed": false}`
- 資料：不需預先資料（測試 onboarding 零資料狀態）

### Steps

1. `browser_navigate` → `http://localhost:8000/scanner`
2. `browser_wait_for` selector=`#tutorialOverlay.active` timeout=3s
3. `browser_snapshot` 驗：
   - `#tutorialOverlay` 存在且有 `.active` class
   - `#btnSelectFolder` 在頁面上（spotlight 模式靠 CSS box-shadow punch-out 命中此元素）
   - `#tutorialProgress` 文字含 `1 / 7`
4. `browser_click` → `#tutorialNext`；`browser_wait_for` `#tutorialProgress` text contains `2 / 7`
5. `browser_snapshot` 驗 `#btnGenerate` 在 viewport 內（step 2 spotlight 命中產生網頁按鈕）
6. `browser_click` → `#tutorialNext`；驗進度 `3 / 7`、sidebar `a[href="/scanner"]` 取得 outline（sidebar mode）
7. `browser_click` → `#tutorialNext`；驗進度 `4 / 7`、sidebar `a[href="/showcase"]` outline
8. `browser_click` → `#tutorialNext` × 3 → 依序驗 step 5/6/7：
   - step 5：sidebar `a[href="/search"]` outline、進度 `5 / 7`
   - step 6：sidebar `a[href="/settings"]` outline、進度 `6 / 7`
   - step 7：sidebar `a[href="/help"]` outline、進度 `7 / 7`、`#tutorialNext` innerText 變為 `tutorial.done` 翻譯（如「完成」/「Done」）
9. `browser_click` → `#tutorialNext`（done）；`browser_wait_for` `#tutorialOverlay` 消失或 `:not(.active)`
10. `browser_evaluate` → `localStorage.getItem('openaver_tutorial_completed')` 預期 `=== 'true'`
11. **H1 Help verify**：`browser_click` → `#sidebar a[href="/help"]`；`browser_wait_for` URL = `/help` timeout=3s
    - **驗**：`h2.card-title` 至少 1 個存在且 innerText **不含** `help.` 字串（無 raw i18n key）
    - **驗**：`.terminal-copy-btn` 可見（curl 複製按鈕 render 正常）

**Tutorial Restart 分支**：
- `browser_navigate` → `http://localhost:8000/scanner?tutorial=restart`
- `browser_wait_for` `#tutorialOverlay.active` timeout=2s
- 驗 `#tutorialProgress` 從 `1 / 7` 開始（重播一律從 step 1）

**重整後不自動觸發驗證**：
- `browser_navigate` 重新整理 `http://localhost:8000/scanner`
- `browser_wait_for` 2s（等可能的 auto-trigger）
- `browser_snapshot` 驗 `#tutorialOverlay` 不存在或 `:not(.active)`

### 完成後 state

- `localStorage.openaver_tutorial_completed === 'true'`
- `GET /api/tutorial-status` 回 `{"completed": true}`（可選驗）
- DOM：`#tutorialOverlay` 不存在或無 `.active` class
- Help 頁所有 `h2.card-title` 無 `help.` 字串

### PyWebView 例外

N/A — tutorial flow 是 browser-only，無需 PyWebView picker。Step 6 sidebar 模式指回 `/scanner` 自身（CD-59-2：避開 `#btnUpdate` 首載隱藏導致 silent skip）。

### Regression 偵測點

- `#btnSelectFolder` 不存在 → tutorial step 1 silent skip → 觀察 `#tutorialProgress` 一開始就是 `2 / 7` 而非 `1 / 7`
- sidebar mode dim 區域算錯 → overlay 沒覆蓋主內容（視覺：主內容仍亮、sidebar 也被 dim）
- locale 切換後文案沒抓對 step → i18n raw key 顯示（如 `tutorial.step1_title` 字串出現在 overlay）
- `tutorial_completed` 沒持久化到後端 → 重整後 tutorial 再次自動觸發（步驟「重整後不自動觸發驗證」失敗）
- `?tutorial=restart` 不從 step 1 起算 → 進度顯示非 `1 / 7`

---

## US2: Search → 整理 → 即時上架

**故事**：用戶在 Search 頁查番號 → SSE 多來源結果 → 觸發整理（scrape）→ 觀察 GhostFly 飛 sidebar Showcase icon → DB 即時 upsert → 切到 Showcase 確認新片到位。

### Setup

- DB 已連上 Scanner tracked directory（否則 `db_sync_status` 會回 `not_linked`）
- 預先放小型有效 MP4 fixture（`tests/fixtures/e2e/SONE-205.mp4`，建議 < 1MB **真實 mp4**，不要用 0-byte placeholder — Scanner/filter/organize 任一層若檢查 size 或 metadata 會 skip 假檔造成假陽性）
- 該路徑須在 Settings → favorite folder 或 Scanner tracked directory 內
- 該番號尚未存在於 DB：
  ```js
  // browser_evaluate
  fetch('/api/search/local-status?numbers=SONE-205').then(r => r.json())
  // 預期 {"SONE-205":{"exists":false}}
  ```
- 若 fixture 或 linked directory 不存在 → **skip US2 並記錄原因**
- Search 頁初始狀態（清除任何殘留搜尋）

### Steps

1. `browser_navigate` → `http://localhost:8000/search`
2. `browser_type` 番號 `SONE-205` 至搜尋輸入框，`browser_press_key` `Enter`
3. `browser_wait_for` selector=`#resultCard` (x-show pageState === 'result') timeout=15s
4. **Sub-A — Detail card render 驗收**：`browser_snapshot` 驗
   - `#resultCard` 內含封面 `<img>` 已載入（`naturalWidth > 0`）
   - 番號 text 含 `SONE-205`、女優欄位非空、片商欄位非空
   - 多來源指示器（如 source badge）至少 1 個
5. **觸發整理（file-list 模式批次）** — 若 Setup 走 file-list 流：
   - 點 `#btnScrapeAll`（`web/templates/search.html:774`）
   - `browser_wait_for` `#batchProgress` 出現（`batchState.isProcessing === true`）
   - `browser_wait_for` `#batchProgress` 消失 timeout=60s（SSE 完成）
6. **GhostFly + DB sync 觀察**：
   - 整理觸發後 `[data-search-ghost]` 元素於 DOM 短暫出現（飛行中）→ 動畫結束後自動移除
   - `browser_wait_for` `#sidebar-showcase-link.pulse-once` timeout=5s（一圈停止；`base.html:537,541`）
   - **驗 db_sync_status**：`browser_evaluate` 取最後一筆 organize response：
     ```js
     // batch.js:94 處設 result.db_sync_status；無公開 API 觀測，靠 _handleDbSyncFeedback toast
     // 改驗 toast：page console 應印 [GhostFly] 或 toast text 含 "已整理"
     ```
7. `browser_navigate` → `/showcase`；驗剛整理的片出現在 grid（搜尋框輸入 `SONE-205` 應命中 1 筆）
8. **Sub-B — 多筆 query 導航**（**獨立 sub-flow，與 organize 流分開跑**；條件 `N >= 2`）：
   - `browser_navigate` → `/search`，搜 `SSIS`（預期多筆）
   - 切到 Detail mode（按 `A` 鍵或點切換按鈕）；驗 navIndicator 顯示 `1/N`，`N >= 2`
   - `browser_press_key` `Tab` 或 click 非搜尋框元素以 blur（方向鍵在搜尋框 focus 時不觸發）
   - `browser_press_key` `ArrowRight` → 驗番號改變、indicator `2/N`
   - `browser_press_key` `ArrowLeft` → 回 `1/N`
   - 驗 Sample Gallery 全程未開啟（無 `.sample-gallery.show` 之類）

### 完成後 state

- `SONE-205` 在 DB 中存在：`fetch('/api/search/local-status?numbers=SONE-205')` 回 `{"SONE-205":{"exists":true}}`
- Sidebar showcase link 有過 `pulse-once` 動畫（class 自動移除，1 圈後恢復）
- DOM 無 `[data-search-ghost]` 殘留元素（GhostFly clone 已清除）

### PyWebView 例外

- S5「拖入檔案」依賴 PyWebView file dialog / drag-drop → 用「Setup 預設已有番號」繞過，不在 browser 跑
- 若走 file-list 模式整理本地檔案，「加入檔案」按鈕 picker 亦為 PyWebView-only → US2 假設 fixture 已位於 tracked directory，不點 picker

### Regression 偵測點

- `db_sync_status` 沒觸發 → SSE 斷線或 `try_inflow_upsert` 失敗 → `#sidebar-showcase-link.pulse-once` 不出現
- GhostFly clone 殘留 DOM → 動畫結束未清理 → `[data-search-ghost]` 元素留在 body
- 起飛點抓錯（grid / file-list 視角 width=0）→ B2 fix `_findDbSyncSourceEl` 五級 fallback；觀察動畫起點偏離預期
- 方向鍵在搜尋框 focus 時被觸發 → 切片亂跳；應 blur 後才生效
- X2 跨頁污染：切到 Showcase 再回 Search，搜尋結果意外殘留 / 清空（視設計而定，記錄當時行為）

---

## US3: Showcase 瀏覽 + Lightbox + 魔杖探索

**故事**：用戶開 Showcase 看收藏 → 翻頁 → 點卡片進 Lightbox → 鍵盤切片 → 點魔杖進相似探索（似星空 constellation）→ 鑽入新主圖。

### Setup

- Showcase 已有至少 10 部影片（依 `videoCount` 計）
- DB 已建好 metadata（cover_url / actresses / tags 完整）
- 清 similar mode 殘留：`browser_evaluate` 設 `Alpine.store?` 或直接重整頁面
- 清 lightbox 殘留：URL 無 `?id=` 等深連結參數

### Steps

1. `browser_navigate` → `http://localhost:8000/showcase`
2. `browser_wait_for` selector=`[x-for="(video, index) in paginatedVideos"]` 渲染（or wait for first card `.video-card` 出現）timeout=5s
   - **驗**：grid 內卡片數 > 0、總數顯示（`videoCount` text 或 grid item count）
3. **翻頁驗收**：點 `.pager-btn`（next 箭頭 `›`，`showcase.html:1227`）
   - `browser_wait_for` page 變化（page indicator 更新或 selected option 改變）
   - **驗**：卡片內容與第 1 頁不同（取第 1 張卡片 number text 對比）
4. **進 Lightbox**：`browser_click` 任一卡片封面（`.video-card` 內 `<img>` 或封面區）
   - `browser_wait_for` selector=`.showcase-lightbox.show` timeout=2s（`showcase.html:517-518`，`lightboxOpen` 為 true 時加 `.show`）
5. **鍵盤導航**：
   - `browser_press_key` `ArrowRight` → 驗番號 / 封面更新（lightbox 內主圖換片）
   - `browser_press_key` `ArrowLeft` → 回前一片
   - `browser_press_key` `Escape` → 驗 `.showcase-lightbox` 失去 `.show` class（lightbox 關閉）
6. **魔杖進入相似探索**：重開 lightbox（重複 step 4）
   - `browser_click` → `.lightbox-similar-btn`（`showcase.html:532`，內含 `<i class="bi bi-magic">`）
   - `browser_wait_for` selector=`.similar-stage` 可見且 `similarModeOpen === true` timeout=3s（`state-similar.js:75`）
7. **Constellation 動畫驗收**：
   - **驗**：`.similar-stage-inner` 渲染、`.similar-rail` 至少 1 條非 `.rail--hidden`（`showcase.html:1072`）
   - **驗**：周圍有相似片 card（plan 預期 8 張）
8. **鑽入（slip-through）**：`browser_click` 任一相似片 card
   - `browser_wait_for` 主圖更新（封面飛中央）
   - **驗**：仍在 similar mode（`.similar-stage` 仍可見），不是退回 Lightbox
9. **退出 similar mode 而非整個 Lightbox**：`browser_press_key` `Escape`
   - **驗**：`.similar-stage` 消失 / `similarModeOpen === false`
   - **驗**：`.showcase-lightbox.show` 仍存在（lightbox 主體還在）
10. `browser_press_key` `Escape` 再一次 → 驗 lightbox 完全關閉

### 完成後 state

- `.showcase-lightbox` 失去 `.show` class
- `.similar-stage` 不可見 / `similarModeOpen === false`
- DOM 無 `[data-search-ghost]` clone 殘留
- URL 未殘留 lightbox state（依設計：可能保留 `?id=`，記錄當時行為）

### PyWebView 例外

N/A — Showcase / Lightbox / 魔杖 探索 完整 browser-only。

### Regression 偵測點

- ESC 在 similar mode 直接關 Lightbox → 應只退 similar mode（兩段式）；現象：`.showcase-lightbox` 一次 ESC 就消失
- 鍵盤導航在搜尋框 focus 時觸發 → ArrowLeft/Right 改變字元而非切片
- Similar stage rail 全部 `.rail--hidden` → 動畫初始化失敗（`playInitialExpand` 沒跑或 GSAP 沒載）
- 翻頁後 lightbox 開啟回到 page 1 → 翻頁 state 沒保留
- `.lightbox-similar-btn` 不可見 → SSR `__CLIP_ENABLED__` 或 router 沒揭露魔杖（v0.8.7 後規則式應永遠可見，若 hidden 表示誤觸 v0.8.6 opt-in gate 殘留）

---

## US4: 跨語言 Tag Alias 篩選

**故事**：用戶在 Showcase 用中文 tag 搜尋 → alias 自動展開（中⇄日⇄英）→ 結果含同義詞匹配 → 點 tag chip 進一步篩選。

### Setup

- DB 有至少 1 個 tag alias group（如「女僕」⇄「メイド」⇄「maid」）；可透過 Scanner 頁 Tag 別名管理 chip 牆預建，或：
  ```bash
  curl -X POST http://localhost:8000/api/tag-aliases \
       -H "Content-Type: application/json" \
       -d '{"primary":"女僕","aliases":["メイド","maid"]}'
  ```
- Showcase 有對應 tag 的影片（至少 1 部 tags 含「メイド」，但**不**含「女僕」）
- 清空 Showcase 搜尋框（`browser_evaluate $store...` 或重整）

### Steps

1. `browser_navigate` → `http://localhost:8000/showcase`
2. `browser_wait_for` `filteredCount` 顯示初始總數（`showcase.html:1170` `<b x-text="filteredCount">`）
3. `browser_click` Showcase 搜尋框（`x-model="search"`，`showcase.html:72`）
4. `browser_type` `女僕`（中文 primary）
5. `browser_wait_for` alias 展開觸發：grid 重新 filter
   - **驗**：`filteredCount` 變化（包含 alias 命中結果）
   - **驗**：含「メイド」tag 的影片出現（雖然搜尋框是中文）
6. `browser_evaluate` 確認 `_tagToGroup` 雙向 map 已載入：
   ```js
   // Alpine store 或 window-level state；可透過 fetch 確認 API 同步
   fetch('/api/tag-aliases').then(r => r.json())
   ```
7. **點 tag chip 進一步篩選**：在任一影片卡片內找 `.lb-tag` 或 grid tag chip（`@click.prevent.stop="searchFromMetadata(tag.trim(), 'tag')"`，`showcase.html:378`）
   - `browser_click` 其中一個 tag chip
   - **驗**：搜尋框 `x-model="search"` 更新為 chip 文字、grid 再次 filter
8. **清除搜尋驗收**：清空搜尋框（`browser_type` 空字串或 `browser_press_key` `Escape` if cleared on ESC）
   - **驗**：`filteredCount` 回到 step 2 初始總數、所有影片回來

### 完成後 state

- 搜尋框 `search` model 為空
- `filteredCount === videoCount`（無篩選狀態）
- DB `tag_aliases` group 仍存在（清理由用戶手動或 disposable fixture 處理）

### PyWebView 例外

N/A — Tag alias UI / chip 互動 完全 browser-only。

### Regression 偵測點

- Alias 不展開 → `_tagToGroup` map 沒載入或 `/api/tag-aliases` 端點失敗 → 中文搜尋只匹配 tag 字串完全相同的影片
- Chip click 沒更新 `search` model → `searchFromMetadata` 沒設置 store；觀察搜尋框 input value 未改變
- A5 SimilarRanker DB 整合 cache 失效 → CRUD 後 ranker 仍用舊 alias map（不在本 US 範圍，由 US3 魔杖驗收 cover）
- 搜尋框清空後 `filteredCount` 卡在篩選態 → `applyFilterAndSort` 未在 `search` 變為 `''` 時觸發

---

## US5: 女優最愛流

**故事**：用戶在 Search 查女優名 → 看 actress profile → 加最愛 → 切到 Showcase 女優模式 → 點女優卡進 actress lightbox → 換頭像（alias 展開本地候選）。

### Setup

- 至少 1 個女優在 Search 端有 profile 可查（如 `三上悠亜`）
- 該女優目前**不**在最愛清單（避免 false positive）：
  ```js
  fetch('/api/favorite-actresses').then(r => r.json())
  // 預期 list 不含 三上悠亜
  ```
- Showcase 有至少 1 部該女優的影片

### Steps

1. `browser_navigate` → `http://localhost:8000/search`
2. `browser_type` `三上悠亜` 至搜尋框、`browser_press_key` `Enter`
3. `browser_wait_for` 搜尋結果出現；驗女優欄位含 `三上悠亜`
4. **加最愛**：找 actress favorite heart（`search.html:132-143`，`.bi-heart` → `.bi-heart-fill` 切換）
   - `browser_click` heart icon（`x-show="actressProfile && !actressProfile?.is_favorite"`）
   - `browser_wait_for` heart 變為 `.bi-heart-fill`（`is_favorite === true`）
   - **驗**：`fetch('/api/favorite-actresses')` 包含 `三上悠亜`
5. `browser_navigate` → `http://localhost:8000/showcase`
6. **切到女優模式**：點女優模式 toggle（`showcase.html:57,63` `@click="...toggleActressMode()"`）
   - `browser_wait_for` `showFavoriteActresses === true`（`state-actress.js:14`）
   - **驗**：actress grid 渲染（女優卡片代替影片卡片）
7. **點女優卡開 actress lightbox**：`browser_click` 任一女優卡（如 `三上悠亜`）
   - `browser_wait_for` `.actress-lightbox-meta` 可見（`showcase.html:582`）
   - **驗**：女優 metadata 渲染、影片清單可見
8. **換頭像（alias 本地候選）**：找「換頭像」按鈕 / `manage_photo_path` 入口
   - 點換頭像 → 預期跳本地候選清單 modal（**PyWebView 例外**：folder picker 為原生 API，瀏覽器無法觸發 → 改驗 alias 展開後候選列表的 UI 渲染，不驗 picker 本身）
   - **驗**：候選列表展開 alias 名做多名查詢（v0.8.8 A2）— UI 顯示候選圖片來自 alias 名查詢

### 完成後 state

- `三上悠亜` 在 `/api/favorite-actresses` 清單中（`is_favorite === true`）
- Showcase 處於 `showFavoriteActresses === true` 模式（或保留依用戶切換歷史）
- DB 無寫入意外的 photo path（picker 沒實際選擇）

### PyWebView 例外

- **換頭像 picker**：`window.pywebview.api.select_file()` 為 PyWebView-only；瀏覽器 fallback 行為依設計（可能跳 alert 或 silent skip）
- **繞過策略**：步驟 8 改驗「alias 展開候選列表」UI 渲染，不驗實際選圖；如需驗 photo 寫入，改用 API `POST /api/actresses/{name}/photo` 直接 curl

### Regression 偵測點

- 加最愛後 heart icon 沒更新 → state sync 失敗、`actressProfile.is_favorite` 未刷新
- 女優模式切換後 grid 沒重新 filter → `toggleActressMode` 沒觸發 `applyFilterAndSort` 或 `paginatedActresses` 未更新
- Alias 展開沒套用到本地候選查詢 → v0.8.8 A2 regression（本地路徑應呼 `AliasRepository.resolve(name)` 展開）
- Actress lightbox 開啟後鍵盤 ESC 不關 → 焦點鎖 / `x-trap` 設定錯

---

## US6: i18n 完整切換

> _T59c-5 待補完_

---

## US7: 控制狂工作流（進階分流）

> _T59c-5 待補完_

---

## Appendix C: Capabilities Smoke（Optional, curl-only）

> _T59c-5 待補完_

---

## ~~舊版 Scenarios（2026-05-14 前）~~ [歷史保留]

> 以下 24 個 scenarios（v1 格式 S/C/T/H/N/X/A）已在 2026-05-14 plan-59c §2 審計後，
> 全數合併進 US1–US7 或標 deprecated。逐項處置原因見下表，原 step 內容已在
> git history（commit before 59c-1）保留，本檔不再重複文字。

### Search

- ~~**S1. 番號精準搜尋**~~ → 併入 US2 step 1–3
- ~~**S2. Detail 模式欄位顯示**~~ → 併入 US2 Sub-A（detail card render 驗收）
- ~~**S3. 方向鍵導航**~~ → 併入 US2 Sub-B（多筆 query 才執行，`N >= 2` 條件）
- ~~**S4. 女優名搜尋**~~ → 併入 US5 step 1–2
- ~~**S5. 拖入檔案/加入檔案**~~ → **deprecated**（PyWebView-only：drag-drop 觸發 file dialog 無法 browser 跑；US2 setup 以「預設已有番號」繞過）

### Showcase

- ~~**C1. 頁面載入 + 卡片渲染**~~ → 併入 US3 step 1
- ~~**C2. 搜尋篩選**~~ → 併入 US4 step 1–2
- ~~**C3. 翻頁**~~ → 併入 US3 step 2（atomic inline）
- ~~**C4. Lightbox**~~ → 併入 US3 step 3–5（含魔杖按鈕補強）

### Settings

- ~~**T1. 語系切換**~~ → 併入 US6 step 1–3
- ~~**T2. Dark / Light Mode**~~ → 保留為獨立 step in US6 step 5
- ~~**T3. 搜尋來源切換**~~ → 併入 US7 step 2
- ~~**T4. 翻譯開關**~~ → 併入 US7 step 3

### Help

- ~~**H1. 頁面載入**~~ → 併入 US1 step 9–10（tutorial 完成後從 sidebar 連 `/help`，驗 `h2.card-title` 非 raw i18n key + `.terminal-copy-btn` 可見）
- ~~**H2. AI curl 複製**~~ → 保留為 US7 末尾 step（capabilities curl 複製）

### Scanner

- ~~**N1. 頁面載入**~~ → 併入 US1 step 1（tutorial 觸發前導覽至 Scanner 頁）
- ~~**N2. 掃描 + 產生網頁**~~ → **deprecated**（PyWebView-only：Scanner 加資料夾依賴原生 picker，瀏覽器無法穩定驅動；scan trigger button 可由實作者選做 atomic check）

### 跨頁面

- ~~**X1. Sidebar 導航**~~ → **deprecated**（US1 step 5–7 已逐一 sidebar 導航，獨立 scenario 冗餘）
- ~~**X2. 頁面間狀態不互相污染**~~ → 保留為 Regression 偵測點 in US2 / US3

### Agentic API

- ~~**A1. 探索搜尋**~~ → 移至 Appendix C（API-only / curl）
- ~~**A2. 批量搜尋**~~ → 移至 Appendix C
- ~~**A3. 補完 metadata**~~ → 移至 Appendix C（寫 DB，需 disposable fixture）
- ~~**A4. 收藏庫查詢**~~ → 移至 Appendix C
- ~~**A5. 生成 HTML 清單**~~ → 移至 Appendix C（寫檔，需 disposable fixture 或暫目錄）

> **CD-59-23**：scenarios 不重複 integration 已測的單端點 contract；A1–A5 維持 curl/API 格式不轉成 browser step，移出 US7 主體放 Appendix C，不算 milestone 必跑。
