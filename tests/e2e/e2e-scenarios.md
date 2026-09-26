# E2E 用戶旅程劇本（v2 — 2026-05-14 align 後）

> 純文字劇本，**人類用瀏覽器手動 / AI 用 Playwright MCP** 皆可照跑。
> 對應 spec：`feature/59-onboarding-help-polish/spec-59.md` §8 + plan-59c.md
> **AI 首次操作前先讀 `app-guide.md`**（同目錄）了解各頁面操作方式。

---

## 執行方式

### Server 啟動

```bash
source venv/bin/activate && uvicorn web.app:app --host 127.0.0.1 --port 8000
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
6. `browser_click` → `#tutorialNext`；驗進度 `3 / 7`（**v0.15.15 起 step 3 改指向 `#btnGenerate` 本身**，不再指 sidebar Scanner 連結）：
   - `browser_snapshot` 驗 `#btnGenerate` 仍在 spotlight 命中範圍（與 step 2 同一顆按鈕）
   - **驗**：提示卡內含 `.tutorial-mock-card`，其中 `.nfo-badge` 文字同時含 `13` 與 `11`（固定假數字，見 `tutorial-step3-card.js` CD-146a-3：不讀真實片庫）
   - **驗**：`.tutorial-mock-card .btn-nfo-update` 存在且帶 `disabled` — `browser_click` 該鈕**不應**觸發任何網路請求（`browser_network_requests` 比對點擊前後無新增 `/api/enrich` 類請求），純示意圖不可點
   - **驗**：提示文字（`tutorial.step3_content`）講明「已經用其他工具整理過的片會直接匯入，不重刮」
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

N/A — tutorial flow 是 browser-only，無需 PyWebView picker。Step 4（showcase，原文檔標「step 6」為舊版編號，已隨 v0.15.15 step 3 改動訂正）起才是 sidebar 模式指向對應頁面連結（CD-59-2：避開 `#btnUpdate` 首載隱藏導致 silent skip）。

### Regression 偵測點

- `#btnSelectFolder` 不存在 → tutorial step 1 silent skip → 觀察 `#tutorialProgress` 一開始就是 `2 / 7` 而非 `1 / 7`
- sidebar mode dim 區域算錯 → overlay 沒覆蓋主內容（視覺：主內容仍亮、sidebar 也被 dim）
- locale 切換後文案沒抓對 step → i18n raw key 顯示（如 `tutorial.step1_title` 字串出現在 overlay）
- `tutorial_completed` 沒持久化到後端 → 重整後 tutorial 再次自動觸發（步驟「重整後不自動觸發驗證」失敗）
- `?tutorial=restart` 不從 step 1 起算 → 進度顯示非 `1 / 7`
- step 3 的模擬卡數字（13／11）與真卡片共用的 i18n key（`scanner.stats.missing_nfo_prefix` 等）沒有同步變動 → 導覽卡片文字與真實補完列的措辭不一致，使用者事後認不出「就是導覽裡那個」
- 點 `.tutorial-mock-card .btn-nfo-update` 發出了真實請求 → `pointer-events:none` 或 `disabled` 守衛被移除，示意圖變成會誤觸的假按鈕

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
5. **觸發整理（file-list 模式批次）** — 走 file-list 流。`scrapeAll()` 只處理 `f.searched && f.searchResults.length > 0 && !f.scraped` 的 file，所以必須先 `searchAll()` 讓每個 fileList item 取得 searchResults，才能整理。順序：
   - **5a. 進 file-list 模式（明確操作）**：
     - 先確認 Settings → favorite folder 已指向放有 fixture mp4 的目錄；若未設定或目錄為空 → **skip US2 並記錄原因**
     - **清空 Search state**（step 1-4 已停在 `pageState === 'result'`，`#btnFavorite` 只在 `#emptyState` 顯示）：
       - `browser_click` → `#btnClear`（`search.html:288`，`x-show="hasContent"`，`@click="clearAll()"`）；或
       - `browser_evaluate` `() => Alpine.$data(document.querySelector('[x-data*="search"]')).clearAll()` 直接清狀態
     - `browser_wait_for` `#emptyState` 可見（`pageState === 'empty'`，`search.html:306`）
     - `browser_click` → `#btnFavorite`（`search.html:316`，`@click="loadFavorite()"`；按鈕在 `#emptyState` 內，必須先清空 result state 才能命中）
     - PyWebView/files/drop 是另一條進場路徑（`setFileList()`），browser e2e 不適用
     - `browser_wait_for` `#btnSearchAll` 可見（`search.html:758`，`x-show="listMode === 'file'"`）+ fileList 顯示 fixture
   - **5b. 先跑 searchAll**：`browser_click` → `#btnSearchAll`（`searchAll()`，`state/batch.js:140`）
   - `browser_wait_for` `#batchProgress` 出現（searchAll SSE 進行中）
   - `browser_wait_for` `#batchProgress` 消失 timeout=60s（searchAll 完成，每個 file 取得 `searched=true` + `searchResults`）
   - **5c. 跑 scrapeAll**（gate 在 `scrapeAll()` 內判，不是 button disabled）：
     - `#btnScrapeAll` 的 `:disabled` 綁的是 `isScrapeAllProcessing`（`search.html:777`），不是「有沒有可整理檔」— 該 button 在 5b 完成後仍可點，但若 fileList 無可整理檔則 click 後直接 toast
     - **驗 fileList 至少一筆**：`browser_evaluate` `() => Alpine.$data(document.querySelector('[x-data*="search"]')).fileList.filter(f => f.searched && f.searchResults?.length > 0 && !f.scraped).length`，預期 `>= 1`（對應 `batch.js:336-338` `scrapableFiles` filter）
     - `browser_click` → `#btnScrapeAll`（`scrapeAll()`，搬移檔案 + 改名 + 建目錄）
   - **失敗模式提示**：跳過 5b 或 fileList 無 searchResults，點 #btnScrapeAll 會 toast `search.toast.no_scrapable_files`（`state/batch.js:341`）
   - `browser_wait_for` `#scrapeProgress` 出現（整理 SSE 進行中；`#batchProgress` 是 searchAll 用，不通用）
   - `browser_wait_for` `#scrapeProgress` 消失 timeout=60s（整理 SSE 完成）
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
2. `browser_wait_for` selector=`[x-for="(video, index) in paginatedVideos"]` 渲染（or wait for first card `.av-card-preview:not(.hero-card)` 出現）timeout=5s
   - **驗**：grid 內卡片數 > 0、總數顯示（`videoCount` text 或 grid item count）
3. **翻頁驗收**：點 `.pager-btn`（next 箭頭 `›`，`showcase.html:1227`）
   - `browser_wait_for` page 變化（page indicator 更新或 selected option 改變）
   - **驗**：卡片內容與第 1 頁不同（取第 1 張卡片 number text 對比）
4. **進 Lightbox**：`browser_click` 任一卡片封面（`.av-card-preview:not(.hero-card)` 內 `<img>` 或封面區）
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
       -d '{"primary_name":"女僕","aliases":["メイド","maid"]}'
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
  fetch('/api/actresses/三上悠亜').then(r => r.json())
  // 預期 is_favorite: false（或 404 / 該女優 profile 不存在）
  ```
- Showcase 有至少 1 部該女優的影片

### Steps

1. `browser_navigate` → `http://localhost:8000/search`
2. `browser_type` `三上悠亜` 至搜尋框、`browser_press_key` `Enter`
3. `browser_wait_for` 搜尋結果出現；驗女優欄位含 `三上悠亜`
4. **加最愛**：找 actress favorite heart（`search.html:132-143`，`.bi-heart` → `.bi-heart-fill` 切換）
   - `browser_click` heart icon（`x-show="actressProfile && !actressProfile?.is_favorite"`）
   - `browser_wait_for` heart 變為 `.bi-heart-fill`（`is_favorite === true`）
   - **驗**：`fetch('/api/actresses/三上悠亜').then(r => r.json())` 回傳 `is_favorite === true`
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

- `GET /api/actresses/三上悠亜` 回傳含 `is_favorite === true`
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

**故事**：用戶在 Settings 頁依序切換 4 個 locale（繁 → 简 → あ → EN → 繁）→ 每次切換後驗多頁面 UI 文字在當前語系正確顯示無 raw i18n key → 驗 Dark/Light mode 切換並重載保留 → 驗 tutorial 文案在當前語系正確。

### Setup

- Dev server 已啟動於 `http://localhost:8000`
- 4 locale 翻譯檔齊全（`locales/zh_TW.json`、`locales/zh_CN.json`、`locales/ja.json`、`locales/en.json`）
- 重置 locale 為 `zh-TW`（可直接點 `.locale-toggle-btn` 循環或直接呼 API）：
  ```bash
  curl -X PUT http://localhost:8000/api/config/general/locale \
       -H "Content-Type: application/json" -d '{"value":"zh-TW"}'
  ```
- DB 有至少 1 部影片（US6 step 6 驗 Scanner 頁時用得到）
- 清 tutorial flag（確保 tutorial 可在 step 8 重播）：
  ```js
  // browser_evaluate
  localStorage.removeItem('openaver_tutorial_completed');
  ```

### Steps

1. `browser_navigate` → `http://localhost:8000/settings`；`browser_wait_for` `.locale-toggle-btn` 可見 timeout=3s
   - **驗**：`.locale-toggle-btn` innerText 為 `繁`（目前 locale = zh-TW）
2. **切換 zh-TW → zh-CN**：`browser_click` → `.locale-toggle-btn`
   - `browser_wait_for` 頁面 reload 完成（URL 仍 `/settings`）timeout=5s
   - `browser_snapshot` 驗：
     - `.locale-toggle-btn` innerText 為 `简`（locale 已切換）
     - sidebar `a[href="/showcase"]` 文字**不含** `sidebar.showcase`（無 raw key）
     - 頁面標題區文字非 `settings.` 開頭字串
3. **切換 zh-CN → ja**：`browser_click` → `.locale-toggle-btn`
   - `browser_wait_for` 頁面 reload 完成 timeout=5s
   - **驗**：`.locale-toggle-btn` innerText 為 `あ`
   - **驗**：sidebar 任一 `a[href]` innerText **不含** `sidebar.` 字串（無 raw key）
4. **切換 ja → en**：`browser_click` → `.locale-toggle-btn`
   - `browser_wait_for` 頁面 reload 完成 timeout=5s
   - **驗**：`.locale-toggle-btn` innerText 為 `EN`
   - **驗**：`#saveBtn`（settings.html:762）文字不含 `settings.action.` 字串
5. **切換 en → zh-TW（回到繁體）**：`browser_click` → `.locale-toggle-btn`
   - `browser_wait_for` 頁面 reload timeout=5s
   - **驗**：`.locale-toggle-btn` innerText 回到 `繁`
6. **Dark/Light mode 切換**：
   - `browser_click` → `.theme-toggle-btn`（settings.html:40；`@click="toggleThemeWithTransition()"`）
   - `browser_wait_for` 1s（過場動畫）
   - **驗**：`html` element 的 `data-theme` attribute 切換（light → dim 或 dim → light）
   - `browser_navigate` 重新整理 `http://localhost:8000/settings`
   - `browser_wait_for` `.theme-toggle-btn` 可見 timeout=3s
   - **驗**：`html[data-theme]` 保留上次切換後的值（重載後不 fallback）
7. **Scanner 頁 locale 驗收**：`browser_navigate` → `http://localhost:8000/scanner`
   - `browser_wait_for` `#btnGenerate` 可見 timeout=3s
   - **驗**：`#btnGenerate` innerText **不含** `scanner.` 字串（無 raw i18n key）
   - **驗**：頁面任何可見文字**不含** `tutorial.` 字串（在覆蓋 overlay 未開啟的情況下）
8. **Help 頁 locale 驗收**：`browser_navigate` → `http://localhost:8000/help`
   - `browser_wait_for` `h2.card-title` 至少 1 個 timeout=3s
   - **驗**：所有 `h2.card-title` innerText **不含** `help.` 字串（help.html Hero/card 均為 Jinja 渲染，非 raw key）
   - **驗**：`.terminal-copy-btn` 可見（curl copy 按鈕 render 正常，help.html:71）
9. **Tutorial 文案 locale 驗收**：`browser_navigate` → `http://localhost:8000/scanner?tutorial=restart`
   - `browser_wait_for` `#tutorialOverlay.active` timeout=3s
   - **驗**：`#tutorialTitle`（tutorial.js:97）innerText **不含** `tutorial.step1_title` 字串（當前 locale 應有翻譯顯示，非 raw key）
   - **驗**：`#tutorialProgress` 文字格式正確（含 `/`，如 `1 / 7`）
   - `browser_click` → `#tutorialClose` 關閉 tutorial（由 `tutorial.js` 動態建立，行號易漂移）

### 完成後 state

- `html[data-theme]` 保留最後切換的 theme 值
- `window.__locale` 為 `zh-TW`（最終循環回繁體）
- `/api/config/general/locale` GET 回傳 `{"value":"zh-TW"}`（可選驗）
- `#tutorialOverlay` 不存在或無 `.active` class（已關閉）
- Help 頁所有 `h2.card-title` 無 `help.` 字串

### PyWebView 例外

N/A — locale 切換、Dark/Light mode、tutorial 文案驗收均為 browser-only。Settings 頁最愛資料夾 picker 為 PyWebView-only，本 US 不涉及。

### Regression 偵測點

- locale 切換後某頁出現 raw key（如 `tutorial.step1_title` 顯示在 overlay）→ 對應 locale JSON 缺翻譯或 `window.t()` fallback 未命中；觀察：`#tutorialTitle` innerText 直接是 key 字串
- Dark mode 重載後 fallback 回 Light → `toggleThemeWithTransition` 沒把 `data-theme` 寫入 DB / localStorage；觀察：`html[data-theme]` 重載後變回預設值
- locale 循環跳過某個 locale → `cycleLocale()` 的 `order` array 缺項；觀察：`.locale-toggle-btn` 從 `简` 直接跳 `EN`（漏掉 `あ`）
- Help 頁 Hero 文字出現 `help.hero.` 開頭 raw key → Jinja `t()` 呼叫失敗（locale JSON 缺鍵 + no fallback）

---

## US7: 控制狂工作流（進階分流）

**故事**：進階用戶在 Settings 自訂命名格式 + 切換搜尋來源 + 關翻譯 → 回 Search 刮削一片驗自訂格式套用 → 在 Scanner 頁新增 Tag Alias group → 最後在 Help 頁複製 AI curl 指令。

### Setup

- Dev server 已啟動於 `http://localhost:8000`
- DB 有至少 1 部影片，且有一部**尚未刮削**的本地 MP4 fixture（US7 step 3 需要）
- Settings 已有預設命名格式（`[{num}][{maker}] {title}`）；若不確定可先呼：
  ```bash
  curl http://localhost:8000/api/config | python3 -c "import sys,json; print(json.load(sys.stdin).get('organize',{}).get('filename_format',''))"
  ```
- 清 Tag Alias（避免 step 4 衝突）：
  ```bash
  # 可選：確認現有 tag alias 不含測試用 primary name「アクション」
  curl http://localhost:8000/api/tag-aliases
  ```

### Steps

1. **修改命名格式**：`browser_navigate` → `http://localhost:8000/settings`
   - `browser_wait_for` `#filenameFormat` 可見（settings.html:546）timeout=3s
   - `browser_triple_click`（或 `browser_click` + Ctrl+A）→ 清空 `#filenameFormat` 輸入框
   - `browser_type` → `#filenameFormat` 輸入自訂格式字串：`[{num}] {title}`
   - `browser_click` → `#saveBtn`（settings.html:762；`@submit.prevent="saveConfig"`）
   - `browser_wait_for` `.toast.toast-end` 可見 timeout=3s（settings.html:823；`_toast.visible`）
   - **驗**：toast `alert` 含 class `alert-success`（非 `alert-error`）
2. **翻譯開關切換**：
   - `browser_wait_for` `#translateEnabled` 可見（settings.html:198）timeout=3s
   - `browser_evaluate` 取目前狀態：`document.getElementById('translateEnabled').checked`（記下初始值 `true`/`false`）
   - `browser_click` → `#translateEnabled`（toggle checkbox）
   - **驗**：`document.getElementById('translateEnabled').checked` 值翻轉
   - `browser_click` → `#saveBtn`；`browser_wait_for` toast timeout=3s；**驗** `alert-success`
   - `browser_navigate` 重新整理 `http://localhost:8000/settings`
   - `browser_wait_for` `#translateEnabled` 可見 timeout=3s
   - **驗**：`#translateEnabled` checked 狀態與切換後一致（設定保留）
   - （測試完還原：再 toggle 一次回原始狀態 + save）
3. **刮削一片驗自訂命名格式**：兩種路徑擇一執行：
   - **路徑 A（UI flow）**：`browser_navigate` → `http://localhost:8000/search`；用 favorite-folder / tracked dir 載入 fixture（PyWebView picker 例外），依 US2 step 5 的 file-list 三段（searchAll → 等 #batchProgress → scrapeAll → 等 #scrapeProgress）走完
   - **路徑 B（API curl，最短驗收）**：`POST /api/scrape-single`（`web/routers/scraper.py:50`，會呼 `organize_file()` 真實搬移 + 改名；對比之下 `/api/enrich-single` 只補 metadata 不改檔名，不適用）：
     ```bash
     curl -s -X POST http://localhost:8000/api/scrape-single \
       -H "Content-Type: application/json" \
       -d "{\"file_path\":\"/path/to/$FIXTURE_NUM.mp4\",\"number\":\"$FIXTURE_NUM\"}"
     # 回傳 dict：success / new_folder / new_filename
     ```
   - **驗**：兩條路徑都需確認檔名套用自訂格式：
     ```js
     // browser_evaluate（path A 完成後）
     fetch('/api/search/local-status?numbers=<番號>').then(r => r.json())
     // 預期 exists: true
     ```
     或 path B response 的 `new_filename` 字串符合 Settings 設定的 `filenameFormat` template
4. **Tag Alias 新增**：`browser_navigate` → `http://localhost:8000/scanner`
   - `browser_wait_for` `#tagAliasCard` 可見（scanner.html:394）timeout=3s
   - 若 `#tagAliasCard` 卡片折疊（`.tagAliasCardCollapsed === true`）：`browser_click` → `#tagAliasCard .card-title`（點 header 展開；scanner.html:397）
   - `browser_wait_for` `.tag-alias-wall`（scanner.html:461）或 `.actress-alias-body`（scanner.html:430）可見
   - `browser_type` `アクション` → `.actress-alias-body input[x-model="tagAliasInput"]`（scanner.html:435）
   - `browser_click` → `.actress-alias-body button[\\@click="addTagAliasGroup()"]`（scanner.html:440）
   - `browser_wait_for` `.tag-alias-wall` 出現新 chip timeout=3s
   - **驗**：`.tag-alias-wall` 內含 `アクション` 文字的 alias chip 出現
5. **Help curl 複製**：`browser_navigate` → `http://localhost:8000/help`
   - `browser_wait_for` `.terminal-copy-btn` 可見（help.html:71）timeout=3s
   - `browser_click` → `.terminal-copy-btn`（`@click="copyCurlCommand()"`）
   - **驗**：`browser_evaluate` 取剪貼簿內容：
     ```js
     navigator.clipboard.readText().then(t => t)
     ```
     預期包含 `/api/capabilities`（capabilities endpoint URL）
   - **驗**：`.terminal-copy-btn` 旁的反饋文字或 icon 變化（可選；依 UI 實作而定）

### 完成後 state

- `#filenameFormat` 在 Settings 仍顯示 `[{num}] {title}`（除非 step 2 還原動作覆蓋）
- 翻譯開關 `#translateEnabled` 已還原到初始狀態
- Tag alias `アクション` group 存在於 DB：`GET /api/tag-aliases` 回傳含 `primary_name: "アクション"` 的 group
- Help curl 按鈕可點擊且剪貼簿含 `/api/capabilities`

### PyWebView 例外

- Settings 頁「最愛資料夾」picker（`selectFavoriteFolder()`）為 PyWebView-only；本 US 不點 picker，只改命名格式與翻譯開關等文字設定，無影響。
- step 3 整理（scrape）流程若依賴 PyWebView picker 選檔 → 用 Setup 預先放好的 tracked fixture 繞過；不點 `#btnSelectFolder`。

### Regression 偵測點

- 自訂命名格式 API 沒 validate → 儲存時 `alert-error` toast（如含非法字元）；觀察：step 1 save 後 toast class 為 `alert-error`
- 翻譯開關重載後沒保留 → `saveConfig` 沒把 `translateEnabled` 寫入後端；觀察：step 2 重整後 `#translateEnabled` checked 狀態回到 opposite
- Tag alias CRUD 後 Showcase filter 沒吃到新 alias → `tag_alias` store reload 沒觸發；用 US4 驗收 `女僕` → `アクション` 的 alias 展開（若兩者 alias 有連結）
- Help curl 按鈕複製到的 URL 不含 `/api/capabilities` → `copyCurlCommand()` 函數 hardcode 的 URL 錯誤；或剪貼簿 API 在 headless 瀏覽器被 block（需 CDP attach 模式）

---

## US8: 區網存取閘門 + agent token（v0.13.7 / v0.13.8 新增）

**故事**：主人在設定頁開啟「需要密碼才能連線」→ 自己這台永遠不用輸密碼 → Help 頁出現 agent token 區塊 → 從區網位址連進來的裝置看到的是一張看不出是 OpenAver 的偽裝頁 → 改密碼後所有裝置與 token 一起失效。

> **為什麼分兩段**：閘門判的是「連進來的位址」。`localhost`／`127.0.0.1` 在閘門第 2 步就短路——**用 loopback 驗閘門會得到一個必然成功、但什麼都沒證明的結果**。故「被擋」那半必須打本機的 LAN 位址（同一台機器連自己的 LAN IP，peer 位址就是那個 LAN IP，閘門會正常生效，不需要第二台機器）。

### Setup

- Dev server 已啟動。**注意**：`uvicorn web.app:app` 起的 dev server **無法**開伺服器模式——LAN listener 需要 `standalone.py` 呼叫過 `lan_listener.wire(app, local_port=...)`，dev 模式下 toggle 會回「無法啟動 LAN 伺服器」。要跑本 US 的 [MCP] 段需先用一支 wire 過的啟動腳本（見 `web/lan_listener.py:120-135` 的 lifecycle 註解）。
- **先備份再跑**：本 US 會寫 `web/config.json`（`server_mode`）與 DB 的 `access_auth`／`access_tickets`。跑完還原。
- 起始狀態：密碼保護關閉（`GET /api/access/settings` 回 `enabled:false`）。

### Steps

1. **[MCP] 認證關閉時 Help 頁沒有多出任何東西**：`browser_navigate` → `/help`
   - **驗**：頁面文字**不含** `Agent Token`、DOM **不含** `oav_`（AC8：PIN 未開時 Help 頁與現況逐位元組相同）
2. **[MCP] 設定頁的控制組是單列不是直向堆疊**：`browser_navigate` → `/settings`，找到伺服器模式膠囊旁的「需要密碼才能連線」
   - **驗**：控制組高度約 28px 量級（**不是** 80px 的三行堆疊）、PIN 欄是四格密碼樣式（**不是**瀏覽器預設的 332px 寬 input）
   - **驗**：兩個密碼輸入框都有 `autocapitalize="off"`（手機鍵盤自動大寫會造成靜默鎖死）
3. **[MCP] 設密碼**：勾選 → 輸入 4 位英數（例 `aB3x`）→ 儲存
   - **驗**：出現「密碼設定已儲存」；欄位顯示為遮罩 ＋ 眼睛鈕可切換真值（**真值只給本機**）
   - **驗**：打英文（不是數字）時儲存鈕是**可按的**（0.13.7 修過：寫死 4 位數字會讓英文密碼得到一顆永遠按不下去的灰按鈕）
4. **[MCP] 自己這台永不被要求密碼**：`browser_navigate` → `/`、`/settings`、`/showcase`
   - **驗**：三頁都正常顯示，沒有偽裝頁（AC2；loopback 免密碼）
5. **[MCP] Help 頁出現 agent 區塊**：`browser_navigate` → `/help`
   - **驗**：出現 `Agent Token` 標題、眼睛鈕、複製鈕、一行含 `Authorization: Bearer` 的 curl 範例、以及 SSE 已知限制那句
   - **驗**：**沒有**「重新產生」按鈕（114b-T8 拔除；作廢路徑只有「到設定頁重存密碼」一條）
   - **驗**：眼睛遮罩狀態下按複製，剪貼簿拿到的是**真值不是遮罩字串**（需 CDP attach 模式，headless 剪貼簿常被 block）
6. **[人工／curl] 區網位址三態**（打 `http://<本機 LAN IP>:<lan_port>`，**不可用 localhost**）：
   - 不帶憑證 → **200 但是偽裝頁 HTML**（無標題、無文字、只有一個不顯眼的輸入框）
   - 帶 `Authorization: Bearer <亂字串>` → **401 JSON**（`{"success":false,"reason":"unauthorized"}`），不是偽裝頁
   - 帶 `Authorization: Bearer <真 token>` → `/api/capabilities` 200，且回應裡 `network.auth` 寫明 bearer、**所有 curl 範例都帶 header**、回應本身**不含** `oav_` 真值
7. **[人工／curl] agent 真的做得到事**：照 capabilities 裡任一支 `side_effect` 端點的 example 原文執行一次寫入 → 成功且讀得回來；同一支端點**不帶 token** 再打一次 → 偽裝頁，且**確認資料沒有被寫進去**
8. **[MCP] 改密碼即全撤**：回設定頁，把密碼**存成同一組**（不改值）
   - **驗**：`/help` 的 token **換成新的一組**（R5：認證設定一被動，票與 token 全部失效，「填一模一樣的 PIN」也不例外）
9. **還原**：取消勾選密碼保護、關閉伺服器模式、還原備份的 `config.json` 與 DB

### 完成後 state

- `GET /api/access/settings` 回 `enabled:false`
- `access_tickets` 表為空
- `/help` 回到「無 agent 區塊」的形狀

### PyWebView 例外

桌面 App 走 loopback，行為與 step 4 相同（永不要求密碼）。step 6–7 的區網三態在 PyWebView 內驗不到，一律用 curl。

### Regression 偵測點

- 從區網連進來看到的是**登入畫面**而不是偽裝頁 → 偽裝設計失效（登入畫面等於向掃到 IP 的人宣告「這裡有東西且值得保護」）
- 自己這台被要求密碼 → 閘門的 loopback 判斷接錯邊（`::ffff:127.0.0.1` 形狀是最常見的漏認），症狀是**桌面版自鎖且畫面是一張假頁**，使用者完全不知道發生什麼事
- 拿錯 token 的 agent 收到 HTML 200 而不是 401 → agent 分不出「我 token 錯了」與「這台根本不是 OpenAver」
- capabilities 的範例不帶 header 或 `auth` 欄寫 `none` → agent 照抄全部 401，然後回頭說「你這台壞了」；**這條所有單元測試都會是綠的**
- 改密碼後舊裝置還連得進來 → 有人繞過 `core/access_auth.py` 直接寫票表（有一條 lint 規則在守，但它擋不掉表名不以字面值出現的寫法）
- 手機輸入正確密碼卻永遠進不去 → 輸入框少了 `autocapitalize="off"`，或存／比對前沒做 NFKC 折疊（全形數字與 ASCII 是不同碼位）

---

## US9: 封面牆條件篩選 ＋ 從片庫加入女優 ＋ 直式海報卡型（v0.13.9 ~ v0.13.14 新增）

**故事**：主人在燈箱點一個標籤 → 搜尋列長出一枚可移除的 pill、牆上只剩符合的片 → 再點一個片商，兩個條件取交集 → 切到女優牆，用 `+` 從片庫把常看的女優一次收好幾個 → 切回影片牆，把卡型換成直式海報，整面牆變直立卡只露封面正面 → 關掉 App 隔天再開，選的還在。

> **為什麼合成一個 US**：這五支 branch（115 metadata pill / 116 女優數值 pill / 117 從片庫加入 / 118 FC2 來源 / 119 直式海報）全部落在**同一面牆與同一條工具列**上，彼此的 regression 會互相掩蓋（例如 pill 讓工具列變兩行，就看不出卡型切換有沒有壞）。分開跑會把同一組幾何量五遍。

### Setup

- Dev server 已啟動，片庫非空（`GET /api/showcase/videos` 的 `total > 0`）。
- **會寫 DB 的步驟已逐條標注**（step 5 的愛心、step 7 的焦點 ✓）。不想寫就跳過那兩步，其餘全部唯讀。
- **視窗寬度以 `window.innerWidth` 為準**，不要用 `document.documentElement.clientWidth`——CSS `@media` 與 JS 的 `_isNarrow` 用的都是**含捲軸**的視窗寬，用 clientWidth 會製造一個 15px 的錯位（見 `gotchas.md` `FE-CSS-13`）。
- **headless 瀏覽器先確認 `document.visibilityState === "visible"`**，背景分頁下 Playwright 的真 click 會全部靜默無效且不報錯（`FE-MOTION-04`）。

### Steps

1. **[MCP] 點 metadata 長出 pill**：`/showcase` → 點任一張卡開燈箱 → 點標籤列的任一個標籤
   - **驗**：燈箱關閉、搜尋列出現一枚 pill（形如 `標籤：<值>`）、牆上只剩符合的片
   - **驗**：搜尋框**沒有**被填入那個標籤的文字（115 的核心：pill 取代「把字塞進搜尋框」）
   - **驗**：狀態列讀「符合 **1** 個條件的 **N** 部」
2. **[MCP] 兩枚 pill 取交集 ＋ 與打字並存**：再開一張卡 → 點片商
   - **驗**：兩枚 pill 並存、N 變小（交集不是聯集）
   - **驗**：在搜尋框打字 → 模糊比對與 pill 同時生效
   - **驗**：pill 是**精準**比對（點進來的是畫面上那一個，不會多帶別的）
3. **[MCP] 移除 pill 的三條路**：按 pill 的 ✕ ／ 搜尋框空字串時按 Backspace ／ 清除鈕
   - **驗**：三條都能移除，且**輸入法組字中（`isComposing`）按 Backspace 不刪 pill**
   - **驗**：pill 全清後回到未篩選的片數
   - **驗**：工具列**維持單列**（不因 pill 變兩行；長系列名的 pill 是第一個撐得動 grid track 的內容）
4. **[MCP] 女優數值 pill**：切女優牆 → 點任一位開燈箱 → 點年齡／身高／罩杯任一格
   - **驗**：女優牆搜尋列長出條件 pill、三顆 op 鈕（`≤` / `=` / `≥`）**即點即套**（不需要再按確認）
   - **驗**：常駐自訂區間列可填上下限；**打壞的數字（如 `1e`）不會被靜默當成沒填而套用舊值**
   - **驗**：同維度再點一次是**取代**不是疊加（真實上限 3 枚）
5. **[MCP][寫 DB] 從片庫加入女優**：女優牆搜尋列的 `+`
   - **驗**：`+` 只在「搜尋列是空的、或搜了但一個都沒找到」時出現
   - **驗**：置中彈窗列出**庫內**女優依片數由多到少；別名合併成一列、片數是合併後總數
   - **驗**：搜尋比對的是全部資料（打一個還沒被捲出來的人也找得到）、**別名也搜得到**
   - **驗**：連按 5 位 → 每列各自「排隊中 → 轉圈 → 實心愛心」，**同時 in-flight 最多 2**、同一位不管按幾下只送一次
   - **驗**：清單滑到接近底部**自動**接下一批（沒有「展開更多」按鈕）
   - **還原**：把這次加的取消收藏
6. **[MCP] 卡型選單四條 ＋ 直式海報**（`innerWidth = 1920`）：工具列模式選單
   - **驗**：選單是**四條**（完整封面／直式海報／詳細／文字），工具列圖示數量**沒有變多**
   - **驗**：選「直式海報」→ 整面牆變直立卡、一列 **7** 張、只露封面右半、常駐 footer 只剩番號
   - **驗**：**選了直式海報之後，選單仍然是四條**（若收成三條就代表切不回完整封面，使用者沒有任何復原路徑）
   - **驗**：active 標示落在「直式海報」那一條
   - **驗**：觸發鈕的 `title` 讀得到卡型（`模式: 直式海報`）
   - **驗**：切換是**原地變形**不是淡出淡入（切換期間卡片 `opacity` 全程 ≥ 0.95、grid 容器高度不塌陷）
   - **驗**：按 `A` 四段循環 完整封面 → 直式海報 → 文字 → 詳細；在**女優牆**按 `A` 一律無效
7. **[MCP][寫 DB] 直式下的人臉逃生口**：直式海報狀態下開燈箱
   - **驗**：焦點編輯鈕**出現**（完整封面時不出現、≤899px 出現）
   - **驗**：按下去 → 遮罩出現 → **真滑鼠拖得動**（往有 headroom 的那一邊；預設右裁時右側 headroom 是 0，往右拖量到的 0 位移不是 bug）→ 按 ✓ → 回牆上那張卡的裁切位置**真的變了**
   - **還原**：把焦點拖回原值，或用 `POST /api/showcase/video/save-focal` 寫回原座標
8. **[MCP] 記憶與強制直式**：
   - **驗**：`innerWidth` 拉到 800 → 畫面仍是直立卡（≤899 強制），拉回 1400 → **仍是直式海報**
   - **驗**：起始選「完整封面」走同一趟 → 拉回後**仍是完整封面**
   - **驗**：跳到 `/search` 再回 `/showcase` → 選的卡型還在；重整也還在
   - **驗**：清空 `localStorage` 重整 → 回到**完整封面**（新使用者的畫面與本版之前逐像素相同）

### 完成後 state

- pill 全清、卡型回到「完整封面」、step 5 的收藏與 step 7 的焦點已還原
- `GET /api/showcase/videos` 的 `total` 與跑之前相同

### Regression 偵測點

- 點 metadata **取代了搜尋框內容**而不是長 pill → 115 的整支功能退回舊行為
- pill 用模糊比對 → 點「山田」帶出「山田花子」，畫面看起來像是有結果、實際是錯的
- 一個叫 `constructor` 的標籤讓整面牆變空白 → alias 查表沒擋原型污染
- 工具列在 360px 被撐成兩行而 `scrollWidth <= innerWidth` **照樣通過** → grid track 用了裸 `1fr`（是裁掉不是捲動，量 scrollWidth 驗不出來，見 `FE-CSS-12`）
- 女優 pill 讓搜尋列變兩行 → pill 的 `padding` 繼承了不該繼承的值
- 從片庫加入時同一位被送兩次、或 in-flight 超過 2 → queue 的兩道不變式破了（enqueue 早退 ＋ 出隊重檢缺一）
- **選了直式海報後選單收成三條** → `_isNarrow` 與 `_posterModeActive()` 兩個語意被合併，使用者切不回完整封面
- 切換卡型時整面淡出再淡入 → Flip 的 capture 跑在狀態寫入之後，動畫靜默退化（**最終畫面看起來是對的**，只有中間幀看得出來）
- 切換卡型時 grid 高度塌陷一下再彈回 → Flip 開了 `absolute`
- 桌面切到直式海報但燈箱沒有焦點編輯鈕 → 方形／無碼封面被右裁時使用者**沒有任何修正入口**
- 首次載入（無 localStorage）的桌面畫面與上一版不同 → 預設值不是 `cover`，或新增的 CSS 沒有全部收在卡型 class 底下

---

## US10: FC2 兩條來源（[人工]，Windows 桌面版限定）

**故事**：主人搜一顆 FC2 番號 → 官方站查得到 → 換一顆官方已下架的 → 官方回不到，改在重刮彈窗把來源切到 `FC2-javten` → 跳出一個真的瀏覽器視窗完成一次人機驗證 → 資料回填。

> **為什麼整段是 [人工]**：`FC2-javten` 需要一個**真的 PyWebView 視窗**讓人點過 Cloudflare 挑戰，dev server 與 headless 瀏覽器都做不到（畫面會直接灰化並說明「僅限桌面應用程式」）。這不是缺覆蓋，是這條路徑的本質。

### Steps

1. **[人工]** 搜一顆**官方站還在**的 FC2 番號（完整格式 `FC2-PPV-xxxxxxx`）
   - **驗**：拿得到日文原題、封面、**發售日**、標籤、賣家；封面與劇照在瀏覽器實載**零破圖**
2. **[人工]** 搜一顆**官方已下架**的
   - **驗**：畫面顯示「找不到資料」（與其他七個來源逐字相同的靜默 miss——這是刻意的，不做「被擋 ≠ 查無此片」的分流）
3. **[人工]** 對同一顆開重刮彈窗 → 來源切 `FC2-javten`
   - **驗**：第一次跳出真的 javten 瀏覽器視窗，點過驗證後**自動接續查詢並回填**，之後不再每次問
   - **驗**：拿得到日文原題／封面／劇照／標籤／賣家／評分；**沒有發售日**（站方頁面結構就沒有，不是抓失敗）
   - **驗**：標籤是**日文版**（`ハメ撮り`／`素人`），不是機翻繁中
4. **[人工]** 在 dev server／區網伺服器／NAS 上看同一顆
   - **驗**：`FC2-javten` 膠囊**灰化並說明「僅限桌面應用程式」**，不會假裝在找然後回一句查無此片

### Regression 偵測點

- 查一顆**確實存在**的片卻說「找不到」→ WebView2 的 `get_current_url()` 不反映轉址（它回的是請求的 URL 不是落地 URL），改讀 `location.href`
- CF 視窗跳出來停在上一頁不動超過 90 秒 → 同視窗第二次導航到同站台時 `NavigationCompleted` 不觸發，導航前要先過一次 `about:blank`
- 兩條需要驗證的來源（JavLibrary／FC2-javten）其中一條掛掉把另一條也拖下水 → 驗證視窗沒有各自獨立
- 升級後的既有使用者**永遠看不到** `FC2-javten` → config migration 寫死了 `[0]` 而不是走訪全部 manual-only 來源（**沒有任何測試會紅**）

---

## US11: 屬性標籤 ＋ 精選 ＋ 分集片 ＋ 發售日條件 ＋ 女優卡資訊區（v0.14.0 ~ v0.14.4 新增）

**故事**：主人打開瀏覽頁 → 開燈箱點標題前那顆星把喜歡的片標起來 → 漏斗選單勾「只看精選」→ 到設定頁把封面左上角的屬性標籤打開，回來整面牆的中字／4K 片都認得出來 → 點發售日長出 `=2024-09` 條件、再打開面板改成整年 → 切到女優牆按眼睛鈕，每張卡下面攤開身高罩杯三圍，點一下就變成條件 → 找到一部分成兩段的片，牆上是一張卡不是兩張。

> **為什麼合成一個 US**：這五件事（0.14.1 屬性標籤 / 0.14.2 分集片合併 / 0.14.3 精選 / 0.14.4 發售日 pill ＋ 女優卡資訊區）全部落在**同一面牆、同一條工具列、同一個燈箱**，且**同時消費同一顆眼睛鈕的展開狀態**（兩面牆共用，見 v0.14.4 已知限制）。分開跑會把同一組幾何量五遍，且彼此的 regression 會互相掩蓋——例如屬性標籤把封面左上角佔滿，就看不出分集片的段別標記有沒有被蓋掉（**兩者都畫在封面上**）。

### Setup

- Dev server 已啟動，片庫非空；**本 US 需要庫裡至少有**：1 部已精選的片、1 組分集片（同資料夾 `-cd1`/`-cd2`）、若干帶 `中文字幕`/`4K` 標籤的片、若干有發售日的片。
  - 本機基準庫實測（2026-08-25）：2114 部、精選 6、分集片 1 組（`SNOS-102`）、中文字幕 504、4K 433、VR 4、有發售日 2035。
- **屬性標籤預設關閉**（opt-in）——step 3 之前牆上不該有任何屬性標籤，那是預設狀態不是壞掉。
- **會寫 DB 的步驟已逐條標注**（step 2 的星、step 3 的設定開關）。不想寫就跳過，其餘全部唯讀。
- 眼睛鈕的展開狀態**會被記住且兩面牆共用**（`localStorage`）——跑完 step 6 要記得收回去，否則下一個 US 的影片牆會是展開的。
- 視窗寬度以 `window.innerWidth` 為準（含捲軸），headless 先確認 `document.visibilityState === "visible"`（同 US9 Setup）。

### Steps

1. **[MCP] 精選在四種呈現裡都是唯讀星標**：`/showcase` → 找一部已精選的片
   - **驗**：番號前面帶一顆 ★，**完整封面／直式海報／詳細／文字四種卡型都有**（切一輪 `A` 鍵）
   - **驗**：**點牆上那顆星＝開燈箱**，不是取消精選（12px 的星做成可點會誤觸，v0.14.3 刻意如此）
   - **驗**：沒精選的片**什麼都不多長**（不是灰星，是沒有）
2. **[MCP][寫 DB] 燈箱那顆星是唯一的開關**：開任一張未精選的片的燈箱 → 點標題最前面那顆星
   - **驗**：金色由下往上灌滿、灌到頂迸火花；**沒有確認框、沒有 toast**
   - **驗**：關掉燈箱 → 牆上那張卡的番號前面立刻有星（不必重整）
   - **驗**：**手機寬度（≤480px）下星星點得到**——左箭頭不會蓋住它（0.14.4 改箭頭對齊封面就是為了這個；箭頭仍在視窗中央＝退版）
   - **還原**：再點一次取消精選
3. **[MCP][寫設定] 封面屬性標籤是 opt-in**：`/settings` → 列表顯示預設 → 「封面屬性標籤」
   - **驗**：**預設全關**；打開之後回 `/showcase`，中字片的封面**左上角**出現標籤
   - **驗**：**最多 3 顆**（找一部同時中字 ＋ 4K ＋ 無碼破解 ＋ VR 的片，畫面上不會擠出第 4 顆）
   - **驗**：逐項關掉其中一種 → 那一種不再顯示，**但該片的標籤本身沒有被改掉**（燈箱標籤列仍讀得到「中文字幕」）
   - **還原**：把開關轉回關閉
4. **[MCP] 分集片合成一張卡**：搜到那組 `-cd1`/`-cd2` 的片
   - **驗**：牆上是**一張卡**不是兩張；封面上有段別標記（`{n} 段`／`第 {current}／{total} 段`）
   - **驗**：`GET /api/showcase/videos` 的 `total` 把該組算成 **1**（畫面與 API 同一份判斷）
   - **驗**：開燈箱按播放 → **一段播完自動接續下一段**（瀏覽器內建播放器）
   - **驗（唯讀，不要真的按確認）**：「從收藏移除」的確認文案讀得到「這是分集片（…），確認後會一併移除全部 N 段的紀錄」——與單片版本**不同一句**
5. **[MCP] 發售日點成條件 ＋ 範圍面板**：開任一張有發售日的片 → 點發售日
   - **驗**：搜尋列長出一枚 `=YYYY-MM` 條件、牆上只剩那個月的片；**搜尋框沒有被填字**
   - **驗**：點那枚條件 → 打開面板 → 三顆鈕（`=`／`≤`／`≥`）即點即套；起訖年月可填，**月份留空＝整年**
   - **驗**：可與 ★精選、女優、標籤等其他條件**疊加取交集**；換排序不影響條件
   - **驗**：`innerWidth ≤ 480` 時發售日**仍點得出條件、但面板不開**（與年齡／身高／罩杯今天的手機行為一致，不是壞掉）
6. **[MCP] 女優牆的眼睛鈕與可點數值**：切女優牆 → 按工具列眼睛（或 `S`）
   - **驗**：每張卡下方攤開**身高／罩杯／三圍**；沒有資料的欄位不留空位，**全都查不到的那位不長空盒子**
   - **驗**：年齡／身高／罩杯**點得下去**→ 長出 `=28歲`／`=157cm`／`=B罩杯` 條件；**作品數與三圍點不下去**
   - **驗**：值是「不明」之類**看得到但點不下去**（不會產生一枚永遠篩不到人的條件）
   - **驗**：窄螢幕（≤899px）下 footer **只留名字**且名字看得見（不是被數字擠成幾個像素）
   - **驗**：滑鼠移到卡片上時 footer **不會整條空白**（影片牆同時驗一次）
   - **還原**：再按一次眼睛收回（**跨牆共用，忘了收下一個 US 會受影響**）
7. **[MCP] 燈箱換片箭頭與對焦編輯互斥**：開燈箱
   - **驗**：箭頭**對齊封面**不是視窗中央；封面上那兩顆玻璃圓盤已經拿掉（關閉鈕與魔法棒**仍是**玻璃圓盤）
   - **驗**：摸得到的範圍仍 ≥ 44px
   - **驗**：按下對焦編輯 → **箭頭藏起來**、左右滑動與 ←／→ 鍵**都不換片**；按確認／取消後恢復
8. **[MCP] 罩杯 L 以上**：女優牆排序切「罩杯」
   - **驗**：`L`／`M`／`N` 這些**排在 K 後面**（不是被當成未知丟到最後，也不是字串序排到 A 前面）

### 完成後 state

- 條件全清、卡型回「完整封面」、眼睛鈕收回、屬性標籤開關轉回關閉、step 2 的精選已還原
- `GET /api/showcase/videos` 的 `total` 與跑之前相同；`select count(*) from videos where user_rating!=0` 與跑之前相同

### Regression 偵測點

- 牆上的星**點下去取消了精選** → 12px 的星被做成可點，手指偏一點就靜默取消一片的精選
- 精選只在「完整封面」有星、切到文字模式就不見 → 星標只接了一種卡型（四種都要）
- 手機上點星卻跳到上一片 → 換片箭頭又對齊視窗中央了（0.14.4 修的正是這條）
- 屬性標籤**預設就開著** → opt-in 被翻成 opt-out，所有人的封面左上角突然多東西
- 關掉某一種屬性標籤，**該片的標籤本身也被刪了** → 顯示開關寫進了資料（不可逆）
- 屬性標籤把段別標記蓋掉（或反過來） → 兩者都畫在封面左上角，只有同時存在的片看得出來
- 分集片在牆上變成兩張卡、或 `total` 把它算成 2 → 合併只做在畫面沒做在計數（**兩邊都要**）
- 分集片的移除確認文案跟單片**逐字相同** → 使用者以為只移除一段，實際整組
- 發售日條件在手機上**把面板也開出來** → 窄螢幕沒有走與年齡／身高／罩杯同一條路
- 女優卡展開後**同一個數字上下各出現一次**（桌機年齡除外，那是已知取捨） → 窄螢幕 footer 沒有讓位
- 罩杯排序把 `L` 丟到最後 → 排序表沒有擴到 K 以上

---

## US12: 瀏覽器模式的資料夾選擇彈窗 ＋ 搜尋列跨頁一致性（v0.14.8 / v0.14.9 新增）

**故事**：主人在區網手機／NAS 上用**瀏覽器**開 OpenAver → 按「加資料夾」不再被一句「需要桌面應用程式」擋死，而是開一個資料夾選擇視窗 → 選完回來 → 切到瀏覽頁，搜尋列跟搜尋頁那條**看起來沒有動過** → 在女優分頁按 ✕，影片牆的條件**沒有被一起清掉**。

> **為什麼合成一個 US**：兩支 branch（128 瀏覽器 UX、129 搜尋列 parity）改的是**同兩條搜尋列與同一組彈窗容器**；129 的幾何對齊是靠改 `--spotlight-*-slot` 那組變數達成的，而那組變數同時被彈窗觸發鈕消費——分開跑會漏掉「對齊修好了但按鈕被壓扁」這一類（見 `gotchas.md` `FE-CSS-15`）。

### Setup

- **必須以瀏覽器（非 PyWebView）開啟**——彈窗只在沒有桌面 bridge 時才是這條路；桌面版按同一顆鈕開的是原生對話框，本 US 不涵蓋。
- 至少設定過一個掃描來源（決定彈窗第一次打開的起點）。
- 三個入口各自記自己的上次位置（`localStorage`）——跑完把三個 key 清掉，否則下次跑起點不是預期值。
- **不要按到「選取此資料夾」以外會寫 config 的路徑**（設定頁輸出夾會寫 `config.json`）。

### Steps

1. **[MCP] 四個入口都開得起來**：`/search` 加檔案／加資料夾、`/settings` 輸出資料夾、`/scanner` 加來源
   - **驗**：四個入口**都不再吐「此功能需要在桌面應用程式中使用」**
   - **驗**：彈窗有麵包屑、單擊資料夾進去、「上一層」、以及一顆**常駐**的「選取此資料夾」
   - **驗**：第一次打開的起點是**第一個掃描來源的上一層**（完全沒設過來源才從根目錄）
2. **[MCP] 三個入口各記各的**：在掃描頁選一層深目錄 → 關掉 → 開設定頁的輸出夾
   - **驗**：設定頁**不會**跳到掃描頁剛選的那層
3. **[MCP] 取消要真的取消**（`FE-TIMING-08` 的那條）：選定資料夾後在回應回來前按 Escape／✕／取消，**以及**「取消後立刻重開一個新的選擇器」
   - **驗**：舊的那次選取**不會**回頭寫進畫面、不會蓋掉新選的資料夾、**不會把新開的視窗關掉**
   - **驗**：兩種情況**都要驗**（只驗後者的話 `closeBrowseDir` 那把 gen 是偵測不到的死碼）
4. **[MCP] 拖資料夾進掃描頁不再靜默**：把一個資料夾拖進 `/scanner`
   - **驗**：覆蓋層關掉後**有話說**（「瀏覽器無法直接讀取拖放檔案的路徑，已為您開啟資料夾選擇器」）並**直接把彈窗開起來**
   - **驗**：搜尋頁與掃描頁的拖放提示層**長一樣**（進場動畫、字級、內距、圖示陰影四項；129 以搜尋頁那版為準統一）
5. **[MCP] 兩頁搜尋列逐值對齊**：在 `1024 / 1100 / 1280 / 1440 / 1920` 五個寬度下，量 `/search` 與 `/showcase` 搜尋列外框與輸入框的 `getBoundingClientRect()`
   - **驗**：五個寬度**逐值相同**（1100px 曾經一邊 680px、一邊 430px）
   - **驗**：`/search` 右側**永遠保留約 15px 的捲軸空白帶**（那是必須付的：瀏覽頁的同一段空間真的被捲軸佔著）
   - **驗**：說明文字在**空狀態**裡（不在搜尋列下方），**手機上看得到**
   - **量測前提**：讀 `window.innerWidth`（含捲軸）不是 `clientWidth`（`FE-CSS-13`）
6. **[MCP] 手機兩枚條件不撐成三行**：`innerWidth = 390`，掛兩枚短條件標籤
   - **驗**：兩枚在**同一行**、搜尋列**單行高度**（曾經各佔一行 ＋ 第三行空白輸入框）
   - **已知限制**：兩枚**長**標籤（例如兩個女優名字）仍會各佔一行，那不是 regression
7. **[MCP] ✕ 只管當前分頁**：影片牆掛條件 → 切女優牆
   - **驗**：女優牆一片空白時**不冒出 ✕**（顯示條件只看當前分頁）
   - **驗**：在女優牆按 ✕ **不會**清掉影片牆的搜尋字與條件
   - **驗**：女優分頁打的字**重整後還在**
   - **驗**：搜尋字精準命中某位最愛女優時上方那張大卡，**切頁再切回來還在**（不必重打名字）

### 完成後 state

- 三個入口的「上次位置」localStorage key 已清、`config.json` 的輸出夾未被改動
- 兩牆的搜尋字與條件已清空

### Regression 偵測點

- 瀏覽器按「加資料夾」又回到一句「需要桌面應用程式」→ 四個死路其中一個沒接上
- 取消之後舊回應照樣寫進畫面／關掉新視窗 → 旁支那條 fetch 的 generation guard 掉了（`FE-TIMING-08`）
- 拖資料夾進掃描頁**毫無反應** → 靜默失敗回來了（路徑拿不到是瀏覽器限制，靜默不是）
- 1100px 下兩頁搜尋列寬度不同 → parity 退版，切頁時看得到它變形
- `/search` 右側那條 15px 空白帶消失 → `scrollbar-gutter` 被拿掉，兩頁又對不齊（**只在有捲軸的頁面才看得出來**）
- 搜尋列上的按鈕被壓扁 → slot 變數調小但 `.btn-icon` 沒有 `flex-shrink: 0`（`FE-CSS-15`，**內容不會溢出，是按鈕自己縮**）
- 在女優牆按 ✕ 把影片牆的條件清掉 → 清除範圍又變回全域

---

## US13: Windows 啟動、安裝與代理環境（[人工]，Windows 桌面版限定）

**故事**：主人的電腦開著 Clash／v2rayN／公司代理 → 雙擊 `OpenAver_Debug.bat` → App **正常開起來**（不是吐一段 Python 錯誤就結束）。啟動真的失敗時，畫面上那句話**查得到東西**、`debug.log` 裡**真的有原因**。

> **為什麼整段是 [人工]**：代理環境、WebView2 安裝身分、系統訊息視窗、剪貼簿與安裝視窗都在 **Windows 真機的打包產物**上，headless 與 WSL 都做不到。自動化測試涵蓋的是「環境變數那一種代理設定」；**登錄檔那一種只有真機驗得到**。

### Steps

1. **[人工]** 開著代理軟體（環境變數 ＋ 登錄檔兩種設定各試一次）雙擊 `OpenAver_Debug.bat`
   - **驗**：App 正常開起來；探活那句「好了沒？」**沒有被送去代理**（連自己不該過代理）
2. **[人工]** 人為讓伺服器起不來（佔掉端口／擋掉程序），看兩種失敗文案
   - **驗**：**等太久** → 告訴你**實際用的那個端口號**（不是寫死的 8000）
   - **驗**：**程序自己掛了** → **幾秒內**就講（不是乾等 30 秒），而且**不會**把你導去查端口
   - **驗**：兩句都印出 `debug.log` 的**完整路徑**（`C:\Users\你\OpenAver\logs\debug.log`）
   - **驗**：`debug.log` 裡**真的留下最後一次連線失敗的原因**（只留一次，不洗版）
3. **[人工]** 用一般身分（非系統管理員）安裝的 WebView2 的機器上開 App
   - **驗**：認得出來，不會誤判成「沒裝」
   - **驗**：提示視窗是**系統訊息視窗**；安裝視窗**不會閃退**；網址**自動進剪貼簿**
4. **[人工]** 查 `debug.log`
   - **驗**：「視窗沒顯示」不再被記成「用戶取消」

### Regression 偵測點

- 開著代理就崩 → `NO_PROXY`／`trust_env` 那條又被繞過（**只有真的開著代理的機器看得出來**）
- 失敗文案又回到寫死的「端口 8000」→ 使用者照著查永遠查不到東西
- `debug.log` 是空的 → 探活失敗的原因沒有落地，那句「請查看 debug.log」又變成空頭支票
- 少數情況（OpenAver 選好的端口在啟動前一刻被搶走）`debug.log` 只有探活失敗紀錄、查不到真因——**這是已接受的 residual，不是 regression**（uvicorn 綁定失敗走 `sys.exit(1)` ＋ 它自己的 logger 不 propagate，見 plan-130a 殘留段）

---

## US14: 書籤（Wishlist）牆與燈箱（v0.15.8 ~ v0.15.10 新增）

**故事**：主人在搜尋頁查到一部還沒入手的片，先按書籤收起來 → 切到「書籤」分頁看牆 → 點卡開燈箱看大圖、往左右滑看下一部 → 片放久了卡片上會多一行「放了幾天」→ 從書籤清單移除一筆，或者片已經入庫了讓系統自己把它收掉。

> **為什麼合成一個 US**：140/141 兩支 branch（牆＋燈箱基本功能、後續動效與 aging 標籤）改的是同一面牆與同一個燈箱狀態機，分開跑會漏掉「牆上卡片與燈箱內容對不上同一筆資料」這類串接問題。

### Setup

- Dev server 已啟動，書籤清單非空（`GET /api/wishlist` 回傳陣列長度 `>= 1`；本機 dev DB 目前有 10 筆，足夠測）。
- **全程唯讀**：只看牆、開關燈箱、往返切換分頁；**不按移除鈕**（`removeFromWishlist` / `removeFromWishlistInLightbox` 會真的刪掉那筆書籤資料，dev DB 是共用測試資料不做這個）。
- 若 `GET /api/wishlist` 回傳空陣列 → **skip 全部書籤相關 step 並記錄原因**（沒有資料可看）。

### Steps

1. **[MCP] 切到書籤分頁**：`/search` → 點搜尋列左側切換鈕（`#wishlistToggleBtn`，書籤圖示，非 `#searchQuery` 旁那顆放大鏡）
   - **驗**：`.wishlist-panel` 顯示、`.wishlist-grid` 內卡片數與 `GET /api/wishlist` 的筆數一致
   - **驗**：搜尋框、空狀態、結果卡（`#emptyState` / `#resultCard` / `#loadingState`）都**不顯示**（`listMode === 'wishlist'` 互斥閘）
   - **驗**：`#wishlistToggleBtn` 上的角標數字（`.mode-toggle-badge`）與清單筆數一致
2. **[MCP] 卡片內容與「放了幾天」**：`browser_snapshot` 看牆上任一張卡
   - **驗**：卡片露番號（`.av-num`）與女優（`.av-actress`）、hover 區塊有標題
   - **驗**：若該筆 `created_at` 夠久（依 `classifyWishlistAging()` 判，14 天／30 天兩道門檻），卡片右上有 `.wishlist-aging` 標籤讀「N 天前加入」；未達 14 天不顯示（**驗**至少一個 stage1、一個 stage2 各出現一次，或記錄「本次資料全落在同一 stage」）
   - **已知例外**（`wishlist-aging.js`）：`release_date` 在未來（預售片）時無論放了多久都強制 stage 0（不顯示 aging 標籤）——實測本機資料裡放了 68 天的一筆因為是預售片而**不**顯示標籤，這是設計行為，不是 regression，別誤判
3. **[MCP] 開燈箱＋左右導航**：點任一張卡
   - **驗**：`.wishlist-lightbox` 取得 `.show` class、大圖 `<img>` 顯示（或 `.cover-error-placeholder` 破圖占位，兩者擇一，不可雙秀或雙無）
   - **驗**：燈箱有「開原站」（`source_url` 非空時才出現）與「移除書籤」兩顆下游動作鈕（**只看存在，不按移除那顆**）
   - ⚠️ **選 nav 按鈕陷阱（實測踩過）**：一般搜尋結果燈箱與書籤燈箱**共用同一組 class**（`.lightbox-nav-prev`／`.lightbox-nav-next`），`document.querySelector('.lightbox-nav-next')` 在兩個燈箱都存在的 DOM 裡會抓到**第一個**（通常是關著的那個），click 沒有任何效果也不報錯。務必先 `document.querySelector('.wishlist-lightbox').querySelector('.lightbox-nav-next')` 縮限範圍
   - `browser_click` 右箭頭（`wishlistLightboxIndex < length-1` 時可見）→ **驗**大圖換成下一筆、番號跟著換（實測：`.wishlist-lightbox img` 的 `alt` 從 `SNOS-365` 變 `MIDV-960`，index 0→1；讀值前留一個 evaluate tick，click 與讀值同一次 `browser_evaluate` 呼叫內可能搶在 Alpine reactive 更新之前）
   - `browser_click` 左箭頭回到上一筆 → **驗**回到 step 3 開的那張卡的番號（往返一致，不錯位）
4. **[MCP] 關閉燈箱三條路**：分別測試 `.lightbox-close` 按鈕、點遮罩空白處（`@click="closeWishlistLightbox()"`）、`Escape` 鍵（若有綁）
   - **驗**：三種都能關閉，關閉後 `.wishlist-lightbox` 失去 `.show`，牆與搜尋列狀態未被清空
5. **[MCP] 切回搜尋結果分頁**：點放大鏡那顆 `.mode-toggle-btn`
   - **驗**：回到 `listMode !== 'wishlist'` 的一般搜尋畫面，之前的搜尋框內容／狀態未被書籤分頁污染

### 完成後 state

- `listMode` 回到非 wishlist、`.wishlist-lightbox` 已關閉
- `GET /api/wishlist` 筆數與跑之前相同（全程未觸發移除）

### PyWebView 例外

N/A — 書籤牆／燈箱純瀏覽器互動，不依賴原生 picker。「加入書籤」（搜尋結果卡上的 ★／🔖 按鈕）與「移除書籤」因為會真的寫 DB，本 US 不觸發，留給 [人工] 或 disposable fixture 環境驗證。

### Regression 偵測點

- 切到書籤分頁後空狀態／結果卡任一個還留在畫面上 → `listMode` 互斥閘漏了一處
- 牆上卡片數與角標數字兜不起來 → `wishlistCount` 與 `wishlistItems.length` 兩個來源沒同步
- 剛加入的書籤在牆上永遠灰底「無圖」、切走切回也不會好 → `:src` 的 `item.created_at` 閘被拿掉（見 search.html branch review P2-1 註解），樂觀 unshift 在封面真的寫檔前就發出請求
- 燈箱左右導航後大圖番號沒換、只有外框動畫換了 → `wishlistLightboxIndex` 更新了但 `currentWishlistLightboxItem()` 讀到舊 index
- 點遮罩關閉時連牆上捲動位置或搜尋框內容一起被清掉 → 燈箱關閉與 `clearAll()` 誤共用了同一個 handler
- `.wishlist-aging` 在剛加入（`created_at` 很新）的卡片上也顯示 → aging stage 的門檻算反了

---

## US15: 瀏覽頁封面／海報切換 ＋ 設定頁「顯示表格與清單」（v0.15.2 新增）

**故事**：主人在瀏覽頁想看直式海報而不是完整封面 → 右上角只有一顆圖示按鈕，點一下整面牆原地變形，不再跳出下拉選單問「表格／清單」——那兩種呈現預設藏起來，想要的話去設定頁開一顆開關才會回到下拉選單。

### Setup

- Dev server 已啟動，`/showcase` 片庫非空。
- **不要按到設定頁的「儲存」**：只驗 checkbox 本身可以勾/取消勾（`x-model`，純前端狀態），**不觸發整包 config 的 POST**——那會真的把 `show_table_list` 寫回 `config.json`，不是「切換再還原」這種可逆動作。
- `innerWidth = 1280`（桌面寬度，避開 `_isNarrow` 分流）。

### Steps

1. **[MCP] 預設只有一顆封面／海報切換鈕**：`/showcase` → `browser_snapshot` 工具列
   - **驗**：`show_table_list` 預設關（`config.json` 目前 `gallery.show_table_list` 未設或 `false`）時，`.showcase-toolbar` 只出現**一顆**不帶下拉的圖示鈕（無 `.toolbar-dropdown-wrap` 包住的模式鈕），沒有「表格／清單」選項
2. **[MCP] 點一下原地切封面／海報**：`browser_click` 該鈕
   - **驗**：`.showcase-grid` 加上 `shape-poster` class、卡片變直式（與 US9 step 6 的直式海報**同一份**卡型，`A` 鍵循環行為在 US9 已涵蓋，這裡只驗**唯一按鈕**觸發同一效果）
   - **驗**：按鈕 icon 與 `title` 同步切換（`bi-person-badge` ↔ `bi-person-vcard`，`title` 讀出目前模式）
   - **驗**：切換是原地變形不是整面淡出淡入（`.av-card-preview` 在切換期間 `opacity` 全程 ≥ 0.95，複用 US9 的驗法）
   - 再點一次切回完整封面，**驗**牆面與按鈕 icon 都還原
3. **[MCP] 設定頁開關（不儲存）**：`/settings` → 捲到「列表生成」卡片 → 找到「顯示表格與清單」那一列的 checkbox（`x-model="form.showTableList"`）
   - **驗**：checkbox 目前狀態與 `GET /api/config` 的 `gallery.show_table_list` 一致（預設應為未勾）
   - `browser_click` 勾選 → **驗**：checkbox 變勾選（純前端 `x-model`，此時尚未送出）
   - 旁邊 `?` 說明鈕（`.help-popover-btn`）點開 → **驗**：`.help-popover` 顯示說明文字
   - **不按儲存**，直接 `browser_navigate` 離開設定頁（狀態捨棄，`config.json` 不變）
4. **[人工，需要能保存設定]** 實際按下設定頁儲存、開啟「顯示表格與清單」→ 回 `/showcase` 驗工具列的模式鈕變回下拉選單（四條：完整封面／直式海報／表格／清單，對照 US9 step 6 選單），確認完再切回關閉並儲存還原——因為這一步會真的動 `config.json`，本輪 MCP 執行跳過，留給人工或下一輪有 disposable config 的環境驗證。

### 完成後 state

- `/showcase` 卡型已切回預設「完整封面」
- `config.json` 的 `gallery.show_table_list` 未被本輪任何 MCP 動作改動（step 3 全程未送出表單）

### Regression 偵測點

- 預設狀態下工具列冒出下拉選單（四條選項）而不是單一切換鈕 → `showTableList` 的預設值或條件判斷反了，新使用者一裝好就看到「多一層選單」的舊行為
- 點切換鈕整面淡出再淡入 → Flip capture 時序退化（同 US9 已知坑）
- 設定頁 checkbox 的視覺狀態與 `GET /api/config` 不一致 → 表單初始化沒讀到後端值，使用者以為設定生效其實沒有
- 未按儲存就離開設定頁，`config.json` 卻被改了 → 表單存在自動送出的副作用（例如 `x-model` 綁到了一個會觸發 watcher 自動 PATCH 的欄位）

---

## US16: 搜尋頁空狀態命名範例 ＋ 定時整理面板 ＋ 最愛未追蹤提醒（v0.15.13 / v0.15.15 新增）

**故事**：主人第一次看到搜尋頁空狀態，四顆按鈕各自被一行文字解釋：加檔案／加資料夾先查資料不動檔案；★ 我的最愛告訴你它指哪個資料夾、會列出裡面全部影片；🕘 定時整理每 12 小時自動處理那個資料夾；最後一行用**主人自己當下的命名設定**算出一個範例，告訴他按下「整理」之後檔案會變成什麼樣子。點開「定時整理」面板可以看目前有沒有開、上次執行結果，還能立刻手動跑一次。如果主人的最愛資料夾根本沒被 Scanner 追蹤，這裡會先用琥珀色小字提醒，而不是等整理完才發現瀏覽頁找不到那些片。

### Setup

- Dev server 已啟動；`/search` 清空搜尋狀態回到 `#emptyState`（`browser_click` `#btnClear` 或 `clearAll()`）。
- **定時整理開關屬於「切換再還原」允許範圍**（面板的 enable checkbox 點擊即時 POST `/api/search/auto-organize/config`，非經「儲存」按鈕）：可以開了再關回去，**但絕不按「立即執行」**（`runNow()` 會真的觸發掃描整理，搬動 dev DB 對應資料夾裡的檔案）。
- 目前 dev 環境 `general.favorite_folder` 為空字串（未設定）——步驟 3 的「已設定」分支與「未被追蹤」警示在本環境**驗不到**，用 [人工] 標注，需要換一個「已設定最愛資料夾但該資料夾不在 Scanner tracked directories」的環境才能重現。

### Steps

1. **[MCP] 空狀態四行說明**：`browser_snapshot` `#emptyState .empty-explainer`
   - **驗**：第一行讀 `search.empty.explain_add`（加入／拖入先查資料）
   - **驗**：`favoriteConfigured()` 為 false 時（本環境現況）顯示「★ 我的最愛」未設定那一行（`search.empty.explain_favorite_unset`），**不**顯示已設定那一行
   - **驗**：🕘 定時整理那一行（`search.empty.explain_auto_organize`）恆顯示，不看設定狀態
   - **驗**：`namingPreviewReady()` 為 true 時，最後一行 `<code>` 內容是**真實算出來的檔名範例**（非空字串、非原樣未替換的 `{}` token），並帶「改規則 → 設定」連結（`href="/settings#filenameFormat"`）
2. **[MCP] 命名範例與設定頁「同一份算法」**：記錄 step 1 的 `<code>` 文字 → `browser_navigate` `/settings#filenameFormat` → 找 `.folder-preview.naming-preview .preview-text`（設定頁「預覽」列）
   - ⚠️ **實測訂正**：兩處呼叫的是同一個 `buildNamingPreview()` 純函式（`shared/naming-preview.js`），但**代入的 token 值不同**——搜尋頁空狀態代入的是**變數名稱本身**（`window.t('settings.var.'+name)`，例如「女優」「番號」「片商」，實測輸出 `女優/[番號][片商] 女優-標題後綴.mp4`），設定頁代入的是**固定範例資料**（`SSNI-618`／`三上悠亞`／`SOD` 等，實測輸出 `三上悠亞/[SSNI-618][SOD] 三上悠亞-絕對領域-4k.mp4`）。**不是逐字相同**，「同一份程式碼」指的是算法／token 替換邏輯共用，不是輸出字串共用——原始草稿假設「兩邊文字逐字相同」是錯的，已依實測訂正。
   - **驗**：兩處的**結構**一致——資料夾層（`createFolder` 開時才有）＋ `[num][maker]` ＋ `actor-title` ＋ `suffix` ＋ `.mp4`，token 出現的相對順序與括號包法相同，只有代入值不同
   - **驗**：在設定頁把「建立資料夾」關掉 → 設定頁預覽的資料夾層消失；回搜尋頁空狀態（不重整，`appConfig` 需重新載入或觀察下次進頁）→ 命名範例前綴的資料夾層也應消失（同一份 `scraper.create_folder` 設定值）
3. **[MCP] 定時整理面板開合**：回 `/search` 空狀態 → `browser_click` `#btnAutoOrganize`
   - **驗**：`.auto-organize-panel` 展開，欄位：啟用開關（checkbox）、「立即執行」按鈕（`:disabled` 在 `!folderIsSet`）、目前解析路徑（`.auto-organize-panel__path`）、警語（`.auto-organize-panel__warning`）
   - **驗**：面板開啟只發一個 `/api/search/auto-organize/status` 請求（`browser_network_requests` 確認未重複打）
4. **[MCP][切換再還原，需先設好最愛資料夾] 啟用開關**：⚠️ **實測訂正**——checkbox 的 `:disabled` 綁的是 `loading || (!folderIsSet && !enabled)`：本機 dev 環境 `search.favorite_folder` 是空字串（`folderIsSet === false`）且目前 `enabled === false`，兩個條件同時成立 ⇒ checkbox **一開始就是 disabled**，點擊沒有任何反應、也不會發任何 `POST` 請求（實測 `browser_network_requests` 在點擊前後完全相同，只有 step 3 那筆 `status`）。這一步**只有在已經設定最愛資料夾（`folderIsSet === true`）的環境才能做**：
   - 記錄目前 `enabled` 狀態 → `browser_click` 勾選 checkbox
   - **驗**：checkbox 變勾選、按鈕 `:class` 從 `btn-outline` 變 `btn-accent`（`#btnAutoOrganize` 本身）
   - `browser_network_requests` 驗有一筆 `POST /api/search/auto-organize/config` body `{"enabled":true}` 且回應 `success`
   - **還原**：再點一次 checkbox 關閉，驗證恢復 `btn-outline` 且再打一次 POST `{"enabled":false}` 成功；`GET /api/config` 確認 `auto_organize.enabled` 回到 `false`
   - 本輪 dev 環境無最愛資料夾 → **SKIPPED**（checkbox disabled，無法點擊；不是 bug，是設計行為：沒有資料夾就不該能開定時整理）
5. **[人工]** 最愛資料夾**已設定但不在 Scanner 追蹤清單**時的琥珀色提醒：需要先把 `general.favorite_folder` 設成一個不在 `scanner.directories` 內的路徑（真的寫 config，本輪不做）→ 驗空狀態「★ 我的最愛」那行後面多一句 `search.empty.explain_favorite_untracked`（琥珀色）；再把該路徑加進 Scanner 追蹤清單 → 驗那句提醒消失
6. **[人工][寫檔]** 「立即執行」定時整理：按 `.auto-organize-panel` 的「立即執行」鈕會真的觸發掃描與搬檔，需要 disposable fixture 目錄才能安全驗證，本輪不做

### 完成後 state

- `.auto-organize-panel` 已關閉、`auto_organize.enabled` 已還原為跑之前的值（本輪為 `false`）
- `/search` 回到清空狀態

### Regression 偵測點

- 空狀態說明列回到「查資料 vs 動檔案」的三行抽象敘述 → 146a 的四行對應按鈕的改版被回退
- 命名範例列在 `appConfig` 或 `formatVariables` 任一個還沒 ready 時就顯示（半截字串或 raw token）→ `namingPreviewReady()` 只擋了其中一個輸入（CodeRabbit 曾抓到只擋 `appConfig` 漏了 `formatVariables`）
- 空狀態範例與設定頁預覽兩邊文字不一致 → 共用函式被其中一邊繞過、各自維護了一份邏輯
- 定時整理開關按下去畫面顯示「開著」、但 `GET /api/config` 讀回仍是 `false` → 失敗時只回滾了 `this.enabled` 沒有連 DOM `checked` 一起還原（component 註解裡明講的那個坑）
- 連點兩下開關，最終落地的值不是使用者最後一次點的那個 → `loading` 早退沒有把 checkbox DOM 狀態拉回

---

## US17: 唯讀來源卡片 ＋ 來源不可連狀態 ＋ javdb 資料路徑（[人工] 為主，v0.15.1 / v0.15.11 / v0.15.12 新增）

**故事**：主人把一顆隨身碟／NAS 掛成唯讀來源 → 瀏覽頁那些影片檔也各自長出卡片，可以搜尋、可以看，但改不了自訂標籤、補不了 NFO；碟拔掉之後，瀏覽頁底部直接寫出「這個來源連不到」而不是讓整面牆空著讓人猜；搜尋番號時，走 javdb 的那條資料路徑換了取得資料的方式，過去查不到的（路徑含中日韓文字、被 javdb 擋下來）現在大多查得到。

> **為什麼整段以 [人工] 為主**：三者都需要**真實的環境狀態**——唯讀來源需要另一個真的掛載點與檔案；來源不可連需要一個曾經連過、現在真的斷線的來源（`GET /api/showcase/source-status` 在本機 dev 環境目前回空陣列，沒有可觀察的不可連來源）；javdb 資料路徑是外部站台行為與封裝格式判斷，屬於資料正確性而非 UI 互動，不是瀏覽器能驗的東西。

### Steps

1. **[人工]** 設定一個 `readonly: true` 的掃描來源（`scanner.directories[].readonly = true`），資料夾內放幾部沒有 NFO 的影片檔 → 掃描
   - **驗**：`/showcase` 牆上每一個影片檔都各自長出一張卡片（過去唯讀來源會漏掉部分檔案，0.15.12 起逐檔都留卡）
   - **驗**：同一個檔名，唯讀來源與一般掃描解出**同一個番號**（片商對照表對唯讀來源一體適用）
   - **驗**：對唯讀來源的片開燈箱改自訂標籤 → 標籤寫進 DB，**不會**寫回來源資料夾本身的任何檔案
   - **驗**：掃描頁「補完 NFO 欄位」對唯讀來源的片**不出現**或點了不動作（唯讀來源不能被寫入）
   - **驗**：對唯讀來源的片重刮之後，先前設的自訂標籤**還在**（不會被清空）
2. **[人工]** 拔掉／斷開一個曾經連上的來源（USB 拔線、NAS 斷網）→ 回 `/showcase`
   - **驗**：畫面下方 footer 有一行講「連不到」的提示（`showcase.status.source_unreachable_list` 或 `_count`，取決於斷線來源數 ≤2 或 >2），不是整面空白或無聲失敗
   - **驗**：碟沒插的情況下，封面牆仍然**一次畫完**（不會因為輪詢不可連來源卡住渲染）
3. **[人工]** 搜一顆 javdb 路徑相關的番號（路徑含中日韓文字的安裝環境、或過去會被 javdb 擋下來的番號）
   - **驗**：查得到資料、封面**沒有**中央浮水印，片長／導演／發行商／系列／劇照五個欄位有補齊
   - **驗**：片商欄位不再誤植發行商的值；標題沒有混入「顯示原標題」字樣

### Regression 偵測點

- 唯讀來源的片被漏掉沒卡片、或番號與一般掃描解出不同值 → 0.15.12 那批唯讀來源修復其中一項退版
- 唯讀來源的自訂標籤寫回了來源資料夾（而不是只進 DB）→ 唯讀承諾被破壞，真的動了使用者的來源檔案
- 來源斷線時瀏覽頁整面空白、看不出原因 → `unreachableSources` 沒被畫出來或 fetch 失敗整個吞掉
- javdb 查詢又開始出現封面中央浮水印，或片商／發行商欄位互換 → v0.15.1 的資料通道退回舊的網頁解析路徑

---

## US18: 五個頁面的左邊緣對齊（v0.15.15 新增，材質零改動）

**故事**：主人從搜尋頁切到瀏覽頁再切到說明頁，過去內容會左右各跳幾個像素——因為每一頁的內縮值各寫各的（16／24／32px 三種都有）。這一版收斂到同一個來源，讓五個頁面的工具列／頁首外框左緣與底下內容左緣**對在同一條垂直線上**，**外觀材質（浮動工具列的玻璃、卡片模糊底、空狀態外框）一個都沒有動**。

### Setup

- Dev server 已啟動，`innerWidth = 1280`（桌面寬度，避開手機/平板的 `--mobile-topbar-height` 分流）。
- 純量測、零互動，不寫任何資料。

### Steps

1. **[MCP] 逐頁量測 `.main-content` 左邊界**：對 `/search`、`/showcase`、`/settings`、`/scanner`、`/help` 五頁依序 `browser_navigate` → `browser_evaluate`：
   ```js
   () => document.querySelector('.main-content')?.getBoundingClientRect().left
   ```
   - **驗**：五個頁面回傳值**逐值相同**（同一個 `--page-gutter` token，`theme.css:66`；實測 sidebar 展開寬度下五頁皆為 `60`，`padding-left` 皆 `24px` ⇒ 內容實際起點 `84px` 逐頁相同，**PASS**）
2. **[MCP] 內容起點對齊**：對 `/showcase`、`/settings`、`/scanner`、`/help` 四頁量測第一個內容區塊（`.showcase-grid` / 第一個 `.settings-section .card` / `.page-layer` 第一個子元素）的 `getBoundingClientRect().left`
   - **驗**：與 step 1 的 `.main-content` 內容起點（`left + padding-left`，實測 `84`）**相等**（或差在 1px 內）——四頁**實測皆為 `84`，PASS**
   - ⚠️ **`/search` 不用這個方法測**：`.spotlight-search` 是**置中**的搜尋框（實測 `left ≈ 373`，視窗置中，非貼左），不是貼左的工具列，跟其他四頁的比較基準不同源，勉強比較會誤判成錯位；`#emptyState` 內容區本身仍走 `.main-content` 同一個 padding token（實測 `108` = `84 + 24`，那多出的 24 是 `#emptyState` 自己的置中/内距設計，不是本 US 要驗的目標）
   - ⚠️ **`.showcase-toolbar` 不能直接拿來跟 `.showcase-grid` 比**：桌面（≥1024px）下 `.showcase-toolbar` 走**既有的**「B floating」浮動玻璃卡設計（`fluent-materials.css` Rule 13b，`margin-inline: var(--layer-inset)`，兩側都內縮，實測 `left = 108 = 84 + 24`），這是**先於 0.15.15、獨立的既有設計**（浮動工具列離頁面邊緣有意留白），**不是**本版左邊緣對齊修復的目標、也不是 regression——別把這個 24px 誤判成沒對齊
3. **[MCP] 平板寬度只出現一種導覽**：`browser_resize` 到 `992` 與 `1023` 兩個寬度分別檢查
   - **驗**：側欄（`#sidebar`）與手機頂欄（`.mobile-topbar` 或等效 class）**不同時出現**——過去 992~1023 這段兩者會同時出現
4. **[MCP] 平板／手機上瀏覽頁工具列與設定頁頁首不被頂欄蓋住**：`browser_resize` 到 `390`（手機）與 `1023`（平板上緣）分別測 `/showcase` 與 `/settings`
   - **驗**：`/settings` 在 390px 下 `.settings-header` 的 `getBoundingClientRect().top === 64`（`--mobile-topbar-height` 4rem，`position:sticky`）——**實測 PASS**，頁首緊貼頂欄下緣，沒有被蓋住
   - ⚠️ **`.showcase-toolbar` 在 ≤480px 預設是收合的**（`showcase.css` 註解「sticky→fixed 移出文件流」），390px 下 `top` 實測是負值（`-73`，捲出畫面外），**這不是 bug**——手機頂欄的搜尋圖示鈕（`.navbar-search-btn`）點開後才會展開，展開後（`.showcase-toolbar.mobile-toolbar-open`）實測 `top === 64`，同樣緊貼頂欄下緣，**PASS**。別在收合狀態下直接斷言 `top >= 64` 會誤判成蓋住
   - 1023px（平板上緣）下兩頁皆 `top === 64`，**PASS**

### 完成後 state

- 純量測，viewport 可留在最後一次 resize（不影響其他 US，執行順序上建議放在其他 US 之後或各 US 自行在 Setup 重設 viewport）

### Regression 偵測點

- 五頁 `.main-content` 左邊界或 padding-left 不相等 → 某一頁還在用舊的內縮值（16／24／32px 三選一沒收斂）
- `/showcase`／`/settings`／`/scanner`／`/help` 任一頁的內容起點與 `.main-content` 內容起點（`left+padding-left`）錯位 1px 以上 → 該頁沒有改吃同一個 `--page-gutter` token
- 992~1023 寬度側欄與手機頂欄同時出現 → 平板寬度的斷點判斷沒收斂成互斥
- 手機/平板上 `.showcase-toolbar` 或 `.settings-header` 的 `top` 小於頂欄高度 → 捲動後工具列/頁首被頂欄蓋住，點不到

---

## US19: 片庫分析頁 ＋ 發行時年齡 ＋ 掃描頁數字點得開（v0.16.0 ~ v0.16.8 新增）

**故事**：主人切到側欄新出現的「片庫分析」（頒獎台圖示）看整個片庫的分布——歷年片數、
片商占比、女優 Top 20、標籤樹圖；點一根年份長條或一列女優，整頁縮成那個範圍再看一次，
下半部深挖收藏女優發行時幾歲、導演／系列排行、每位女優歷年主要片商、誰其實散在很多家、
選了女優之後她最常跟誰同片。同一批版本也讓瀏覽頁的封面牆與燈箱直接看得到收藏女優「拍
這部片時幾歲」、掃描頁那些只給一個數字的地方點下去看得到清單，以及重刮視窗多一個「保留
標題」的逃生口。

### Setup

- Dev server 已啟動，片庫非空（`GET /api/showcase/videos` 的 `total > 0`）。
- 全程唯讀：不點「產生網頁」／整理／收藏／重刮送出／存檔／語系切換。
- 片庫分析頁與發行時年齡都依賴「收藏女優有生日 + 照片」與「片有完整發行日」，dev DB
  資料可能不齊；缺前提時該步驟回報 `N/A(precondition)` 並寫明缺什麼，不算 FAIL。

### Steps

1. **[MCP] Sidebar 導航**：`/showcase` 頁展開側欄，找「瀏覽」下方頒獎台圖示的新連結
   （`nav.insights`，`href="/insights"`）→ 點擊
   - **驗**：導向 `/insights`，`.insights-container[x-data="libraryInsights"]` 存在
2. **[MCP] 常駐四格**：讀 `#tileCount .insights-tile-value`、`#tileYear`、`#tileFocus`
   - **驗**：`#tileCount` 顯示非 `—` 的數字（`snapshotError` 為 false 時），下方有一行
     「全庫 N 部」（`totalCountLabel()`）
   - **驗**：`#tileYear`／`#tileFocus` 初始顯示淡色「全部」（`insights.all_years` /
     `insights.all_focus`），非 raw i18n key
3. **[MCP] 圖表渲染**：依序確認以下 echart 容器存在且有內容（`canvas` 或
   `getBoundingClientRect().height > 0`）：`#yearsChart`、`#donutChart`、`#top20List .top20-row`
   （count > 0）、`#tagsChart`、`#ageChart`、`#directorChart`、`#seriesChart`、
   `.gantt-card .gantt-table`（或 `.gantt-empty` 若無資料）、`#row6 .solo-row`（或 `.solo-empty`）
   - **驗**：至少 `#yearsChart`／`#donutChart`／`#top20List` 三者非空（片庫非空的前提下）
   - 若某卡片顯示「沒有資料」（`insights.no_data`）而非空白/報錯，視為 PASS（資料真的沒有）
4. **[MCP] 點年份長條設定焦點**：`#yearsChart` 內找一根長條點擊（ECharts canvas 點擊座標，
   或退而求其次用 `dispatchAction` 驗證邏輯；若 canvas 座標點擊不可靠，記錄實際點法）
   - **驗**：點擊後 `#tileYear` 顯示該年份數字、多一顆 `×` 清除鈕
   - **驗**：點 `×`（`insights.clear_year`）→ `#tileYear` 回到「全部」
5. **[MCP] 點 Top-20 列設定女優焦點**：`#top20List .top20-row:first-child` 點擊
   - **驗**：`#tileFocus` 顯示該女優名字（`insights.focus_type_actress`）與 `×`
   - **驗**：`#costarCard`（「與她同片」）從 `x-show` 隱藏變成可見，`#costarList` 有列或
     顯示 empty 態
   - **驗**：點 `#tileFocus` 的 `×`（`insights.clear_focus`）→ 焦點清除，`#costarCard` 隱藏
6. **[MCP] 主要片商年表 年/年齡 toggle**：`.insights-gantt-toggle` 兩顆按鈕
   - **驗**：預設 `year` 高亮（`is-on`），點「年齡」按鈕 → class 切到年齡那顆、
     `.gantt-table` 內容改變（軸從年份換成歲數）或顯示 `.gantt-empty`
   - 若 dev DB 沒有女優同時有生日又有主要片商年資料 → `N/A(precondition)`
7. **[MCP] 選了年份卻沒有片**：選一個 `#tileYear` 年份，若該年份剛好焦點女優無片
   - **驗**：受影響卡片顯示「這個期間沒有符合的片」（`insights.period_empty`），與
     `insights.no_data`（全庫本來就沒資料）文字不同
   - 若挑不到這種年份組合 → `N/A(precondition)`，記錄嘗試過的年份
8. **[MCP] bfcache 回退**：從 `/insights` 點 sidebar 導到 `/showcase`，再用瀏覽器上一頁
   （`browser_navigate_back` 或等效）回 `/insights`
   - **驗**：圖表仍渲染（不是白頁或卡在載入中）
9. **[MCP] Showcase 燈箱顯示發行時年齡**：`/showcase` 開一張有收藏女優（且該女優有生日）
   的卡片燈箱，讀 `.lb-actress-core` 或女優名那一行
   - **驗**：收藏女優名字後面出現 ` (NNy)` 格式
   - 若 dev DB 找不到「收藏 + 有生日 + 完整發行日」的組合 → `N/A(precondition)`，寫明缺什麼
10. **[MCP] Showcase 封面牆資訊展開顯示年齡**：同一張卡在牆上點眼睛（資訊展開）按鈕
    - **驗**：卡片底下女優那一行同樣出現 ` (NNy)`（多人片）或單人片卡片底部女優名後出現
      年齡（規則見 CHANGELOG 0.16.7）
11. **[MCP] 掃描頁數字點得開**：`/scanner` 找「NFO 與封面都缺」／「缺 NFO」／「缺封面」／
    「NFO 欄位不全」／「外部媒體管理器封面缺失」任一顯示中的數字（`.number-drilldown-number-btn`）
    → 點擊
    - **驗**：跳出 `.number-drilldown-popover`，內含標題、共幾部（`countLabel`）、清單列
      （番號或檔名）、複製按鈕（`.number-drilldown-copy-btn`）
    - **驗**：按 `Escape` → popover 關閉（`open === false`），焦點回到觸發鈕
    - 不點複製按鈕的「複製」動作本身（避免寫剪貼簿造成不可預期副作用時打斷腳本）；若點了
      只驗 toast 文案，不驗真的貼進系統剪貼簿
    - 若掃描頁目前所有計數皆為 0（沒有缺件）→ `N/A(precondition)`
12. **[MCP] 燈箱 ⚙ 進階重刮「保留標題」勾選**：`/showcase` 開一張卡燈箱 → 點 ⚙ →
    輸入/沿用番號 → 點「自動」來源 pill 觸發預覽（讀取外部來源，非寫入）
    - **驗**：預覽結果的標題與目前標題不同時，出現「保留標題：「〈目前標題〉」」勾選
      （`showcase.rescrape.preserve_title`），**預設勾選**
    - **完成**：按左上 ✗ 或 Esc 關閉，**不按確認 ✓**（避免寫入）
    - 若外部來源查無結果、或標題剛好相同（勾選不出現）→ 記錄實際情況，不算 FAIL
13. **[MCP] 說明頁批次搜尋 help 文字**：`/help` 找 `help.batch.add_folder` 對應段落
    - **驗**：文字包含「只讀這一層」／「不往子資料夾找」的措辭（不是舊版「批次搜尋整個
      資料夾（含子目錄）」），且不是 raw i18n key

### 完成後 state

- `/insights` 的年份／焦點已清除（step 4/5 有 clear）
- 燈箱、重刮 dialog、掃描頁 popover 皆已關閉
- 未寫入任何 DB／設定／剪貼簿

### Regression 偵測點

- `/insights` 進頁後圖表容器空白且無 `no_data`/`period_empty` 文案 → ECharts 初始化失敗或
  資料契約壞了
- 點年份/女優後 `#tileYear`/`#tileFocus` 沒有反應，或 `×` 按了焦點沒清 → 焦點狀態機壞了
- 選了年份後長條數字被改成 0（而非用亮暗表示選取）→ 違反「數字永遠顯示完整歷年收藏」的設計
- 從 `/showcase` bfcache 返回 `/insights` 白頁或圖表消失 → 上次載入中途離開的清理沒做好
- 燈箱／封面牆年齡格式跑掉（不是 ` (NNy)`）、或兩位以上女優的封面牆卡片底部（眼睛關閉時）
  誤顯示年齡 → 違反「多人時單獨一個歲數看不出是誰的」規則
- 掃描頁數字 popover 點不開、或開了抓不到清單列 → `numberDrilldown` payload 契約壞了
- 重刮預覽標題相同時仍顯示「保留標題」勾選 → `rescrapeShowPreserveTitle()` 判斷條件壞了
- `/help` 批次搜尋段落仍寫「含子目錄」等舊文字 → i18n key 沒同步新行為

---

## Appendix C: Capabilities Smoke（Optional, curl-only）

> 純 curl/API 測試，非 browser user story，**不算 milestone 必跑**。
> CD-59-23：不重複 integration 已覆蓋的單端點 contract；僅作 Agentic AI quick-smoke 清單。
> A3/A5 有寫檔副作用，需先備 disposable fixture 或確認資料可覆蓋。

### 前置條件

```bash
# Dev server 已啟動
source venv/bin/activate && uvicorn web.app:app --host 127.0.0.1 --port 8000

# （A3/A5 用）準備 disposable fixture 番號（確認 DB 內存在或可覆蓋）
FIXTURE_NUM="SONE-205"  # 換成實際有資料的番號（A1-A5 共用，務必在同一 shell session 執行）
```

### A1：探索搜尋

```bash
curl -s "http://localhost:8000/api/search?q=SONE-205&discovery=true" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('title','MISSING'), d.get('actresses','MISSING'), d.get('cover_url','MISSING')[:30])"
```

**驗收**：`title`、`actresses`、`cover_url` 三欄均非 `MISSING` 且非空字串。

### A2：批量搜尋

```bash
curl -s -X POST http://localhost:8000/api/batch-search \
  -H "Content-Type: application/json" \
  -d '{"numbers":["SONE-205","SSIS-001","IPX-001"]}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'count={len(d.get(\"results\",[]))}')"
```

**驗收**：回傳 `count=3`（3 筆結果，部分可能為 `not_found` 但結構存在）。

### A3：補完 metadata（寫 DB — 需 disposable fixture）

```bash
curl -s -X POST http://localhost:8000/api/enrich-single \
  -H "Content-Type: application/json" \
  -d "{\"file_path\":\"/path/to/$FIXTURE_NUM.mp4\",\"number\":\"$FIXTURE_NUM\",\"mode\":\"fill_missing\"}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('updated_fields:', d.get('updated_fields','MISSING'))"
```

**驗收**：回傳含 `updated_fields` 欄位（可為空 list，表示無需補完）；不回 5xx 錯誤。
**副作用**：寫入 DB（`$FIXTURE_NUM` 的 metadata 可能被更新）。

### A4：收藏庫查詢

```bash
curl -s -X POST http://localhost:8000/api/collection/sql \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM videos"}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('rows:', d.get('rows','MISSING'))"
```

**驗收**：回傳 `rows` 非空（如 `[[10]]`）；不回 5xx 或 `{"error":...}` 結構。

### A5：生成 HTML 清單（寫檔 — 需 disposable fixture 或暫目錄）

```bash
# 用 FIXTURE_NUM 作為 numbers 輸入（endpoint 吃 numbers 不吃 ids）
curl -s -X POST http://localhost:8000/api/gallery/generate-from-ids \
  -H "Content-Type: application/json" \
  -d "{\"numbers\":[\"$FIXTURE_NUM\"]}" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('html_path:', d.get('html_path','MISSING'), 'video_count:', d.get('video_count','MISSING'), 'missing:', d.get('missing',[]))"
```

**驗收**：`html_path` 非空字串、`video_count >= 1`（FIXTURE_NUM 在 DB 中時）；回傳是 JSON 不是 HTML 本文。
**副作用**：endpoint 自行決定輸出路徑（通常落在 `output/` 目錄）；測後可手動清掉產出檔案。

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
