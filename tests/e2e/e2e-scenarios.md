# E2E 場景清單

> 人工或 Playwright MCP 皆可執行。每個場景標記 MCP 可測或需人工。
> Milestone 時依 `feature/AI_COLLABORATION/milestone.md` SA-mile-4 執行。
> **AI 首次操作前先讀 `app-guide.md`**（同目錄），了解各頁面操作方式和注意事項。

---

## 前置條件

- App 已啟動：`python -m web.app`（預設 `http://localhost:8000`）
- 有至少一個已掃描的資料夾（Showcase 有資料）

---

## Search 頁

### S1. 番號精準搜尋 [MCP]

1. 前往 `/search`
2. 輸入 `SONE-205`，按搜尋
3. 等待 SSE 結果出現
4. **驗證**：封面圖顯示、番號文字 = `SONE-205`、有女優名

### S2. Detail 模式欄位顯示 [MCP]

1. 承 S1，結果應自動進入 Detail 模式
2. **驗證**：標題、女優、日期、來源、片長、發行商欄位可見且非空

### S3. 方向鍵導航 [MCP]

1. 搜尋 `SSIS`（預期多筆結果）
2. 多筆結果預設進入 Grid 模式 → 切換到 Detail 模式（點擊切換按鈕或用 `A` 快捷鍵）
3. 確認導航指示器顯示 `1/N`（N >= 2）
4. Blur 搜尋框（方向鍵在搜尋框 focus 時不觸發導航）
5. 按 ArrowRight → 番號改變、指示器變 `2/N`
6. 按 ArrowLeft → 番號還原、指示器變 `1/N`
7. **驗證**：Sample Gallery 全程未開啟

### S4. 女優名搜尋 [MCP]

1. 輸入女優名（如 `三上悠亜`），按搜尋
2. 等待結果
3. **驗證**：出現多筆結果，女優欄位包含搜尋的名字

### S5. 拖入檔案/加入檔案 [人工]

1. 拖入一個影片檔案到搜尋框
2. **驗證**：自動辨識番號並開始搜尋

> MCP 無法觸發 PyWebView file dialog / drag-drop

---

## Showcase 頁

### C1. 頁面載入 + 卡片渲染 [MCP]

1. 前往 `/showcase`
2. **驗證**：顯示影片總數、卡片封面圖可見、分頁器顯示頁數

### C2. 搜尋篩選 [MCP]

1. 在 Showcase 搜尋框輸入番號或女優名
2. 按搜尋
3. **驗證**：結果數量減少、卡片內容符合搜尋條件

### C3. 翻頁 [MCP]

1. 點擊「下一頁」
2. **驗證**：頁碼變為 2、卡片內容與第 1 頁不同

### C4. Lightbox [MCP]

1. 點擊任一卡片封面
2. **驗證**：Lightbox 開啟、顯示詳細資訊
3. 按 ESC → Lightbox 關閉

---

## Settings 頁

### T1. 語系切換 [MCP]

1. 前往 `/settings`
2. 點擊語系按鈕（繁 → 简 → あ → EN 循環）
3. **驗證**：頁面 UI 文字隨語系切換變化
4. 重新載入頁面 → 語系設定保留

### T2. Dark / Light Mode [MCP]

1. 點擊 theme 切換按鈕
2. **驗證**：背景色 / 文字色切換
3. 重新載入 → 設定保留

### T3. 搜尋來源切換 [MCP]

1. 切換預設搜尋來源（如取消勾選 JavDB）
2. **驗證**：設定保存成功（Toast 或 UI 反饋）
3. 重新載入 → 設定保留

### T4. 翻譯開關 [MCP]

1. 切換「啟用標題翻譯」開關
2. **驗證**：開關狀態變化、設定保存

---

## Help 頁

### H1. 頁面載入 [MCP]

1. 前往 `/help`
2. **驗證**：版本號顯示（v0.6.x）、內容正常渲染、無 JS 錯誤

### H2. AI curl 複製 [MCP]

1. 點擊 curl 指令旁的複製按鈕
2. **驗證**：剪貼簿內容包含 `http://localhost:8000/api/capabilities`

---

## Scanner 頁

### N1. 頁面載入 [MCP]

1. 前往 `/scanner`
2. **驗證**：掃描資料夾表單可見、快取影片數顯示

### N2. 掃描 + 產生網頁 [人工]

1. 確認有已設定的掃描資料夾
2. 點擊「產生網頁」
3. **驗證**：掃描進度顯示、完成後產出 HTML 檔案

> MCP 可點擊「產生網頁」按鈕，但需已有設定好的資料夾路徑

---

## 跨頁面

### X1. Sidebar 導航 [MCP]

1. 點擊 hamburger menu
2. 逐一點擊 5 個連結
3. **驗證**：每頁正確載入、無 crash

### X2. 頁面間狀態不互相污染 [MCP]

1. 在 Search 搜尋一個番號
2. 切到 Showcase → 切回 Search
3. **驗證**：Search 頁回到初始狀態（或保留上次搜尋結果，視設計而定）

---

## Agentic AI API（模擬 AI agent 只讀過 capabilities）

> 模擬一個只看過 `GET /api/capabilities` 回傳的 AI agent，用自然語言任務驅動 API 呼叫。
> 驗證方式：curl 或 Python requests，不經瀏覽器。
> **模型要求**：輕量模型即可（Haiku / Gemini Flash / GPT-4o Mini），不需要 Opus/Sonnet。
> Capabilities manifest 的 description 足夠清晰，輕量模型能正確選對 endpoint + 組合參數。

### A1. 探索搜尋 [API]

- 任務：「查一下 SONE-205 這部片的資訊」
- 預期行為：agent 從 capabilities 學到 `GET /api/search`，呼叫 `?q=SONE-205&discovery=true`
- **驗證**：回傳 JSON 包含 title、actresses、date、cover_url

### A2. 批量搜尋 [API]

- 任務：「幫我查這三部片：SONE-205、SSIS-960、JUR-688」
- 預期行為：agent 用 `POST /api/batch-search`
- **驗證**：回傳 3 筆結果，每筆有 number + metadata

### A3. 補完 metadata [API]

- 任務：「這部片的 NFO 資訊不完整，幫我補齊」
- 預期行為：agent 用 `POST /api/enrich-single` with `mode=fill_missing`
- **驗證**：回傳成功，updated_fields 列出補齊的欄位
- **前提**：需要 DB 中有該片且確實缺欄位

### A4. 收藏庫查詢 [API]

- 任務：「查我收藏裡三上悠亜演的所有片」
- 預期行為：agent 用 `POST /api/collection/sql` with `SELECT * FROM videos WHERE actresses LIKE '%三上悠亜%'`
- **驗證**：回傳 rows 包含正確結果

### A5. 生成 HTML 清單 [API]

- 任務：「用這些番號產生一份可分享的 HTML」
- 預期行為：agent 用 `POST /api/gallery/generate-from-ids`
- **驗證**：回傳 HTML 內容，包含封面圖（base64 嵌入）
