# D.2: AV Card Full 加入互動元素

**狀態**：⬚ 待實作
**優先級**：P0

---

## 問題摘要

設計系統中的 AV Card Full 變體（用於搜尋結果詳情頁面）目前是純靜態展示，缺少 v0.2.3 穩定版中的所有互動元素。這些互動按鈕是核心功能（切換資料來源、編輯標題、AI 翻譯、複製本地路徑、查看標籤），必須在 D.4 全站遷移前補齊到設計系統中，作為視覺參考和樣式來源。

缺失的互動元素包括：
- **Header 區**：切換來源按鈕（`bi-arrow-repeat`）、本地 badge（可點擊複製路徑）
- **Body 區**：標籤 badges 列（顯示作品分類標籤）
- **Footer 區**：編輯標題按鈕（`bi-pencil`）、AI 翻譯按鈕（`bi-translate`）

---

## 現狀分析

### 當前 Full Card 結構（design-system.html 第 689-724 行）

```html
<!-- Full 變體 -->
<div class="ds-subsection">
    <h3>2. Full（詳細頁面）</h3>
    <p class="ds-desc">用於搜尋結果詳情，左右分區佈局</p>
    <div class="ds-card-demo">
        <div class="av-card-full">
            <div class="av-card-full-cover">
                <img src="/static/img/demo/cawd-441.jpg" alt="full cover">
            </div>
            <div class="av-card-full-info">
                <div class="av-card-full-header">
                    <h4 class="av-num">CAWD-441</h4>
                    <span class="local-badge">本地</span>
                    <!-- ❌ 缺少切換來源按鈕 -->
                    <!-- ❌ local-badge 無點擊互動樣式 -->
                </div>
                <div class="av-card-full-body">
                    <div class="info-row">
                        <span class="info-label">演員</span>
                        <span class="info-value">女優名稱</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">發行日期</span>
                        <span class="info-value">2024-01-15</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">片商</span>
                        <span class="info-value">Kawaii</span>
                    </div>
                    <!-- ❌ 缺少標籤列 info-row -->
                </div>
                <div class="av-card-full-footer">
                    <span class="info-label">標題</span>
                    <p class="info-value">作品標題範例，可能很長需要換行顯示</p>
                    <!-- ❌ 缺少編輯/翻譯按鈕 -->
                </div>
            </div>
        </div>
    </div>
</div>
```

### 當前相關 CSS（design-system.css 第 883-906 行）

```css
.av-card-full-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border-light);
    margin-bottom: 1rem;
}

.av-card-full-header h4 {
    font-size: 1.35rem;
    color: var(--accent);
    margin: 0;
    font-weight: 700;
}

.av-card-full-body {
    flex: 1;
}

.av-card-full-footer {
    padding-top: 1rem;
    border-top: 1px solid var(--border-light);
}
```

現有 CSS 定義了基礎佈局，但缺少互動按鈕和 badge 的樣式定義。

---

## 參考：v0.2.3 原始設計

### Info Panel 完整結構（search.html 第 155-208 行）

```html
<div class="info-section">
    <!-- Header: 番號 + 本地標記 + 切換來源按鈕 -->
    <div class="info-header">
        <h4 class="info-number" id="resultNumber">-</h4>
        <span id="localBadge" class="local-badge d-none" title="本地已有">📁</span>
        <button id="switchSourceBtn" class="btn btn-link p-0"
            onclick="switchSource()" title="切換版本">
            <i class="bi bi-arrow-repeat"></i>
        </button>
    </div>

    <!-- Body: 各項資訊列（包含標籤） -->
    <div class="info-body">
        <div class="info-row">
            <div class="info-label">演員</div>
            <div class="info-value" id="resultActors">-</div>
        </div>
        <div class="info-row">
            <div class="info-label">發行日期</div>
            <div class="info-value" id="resultDate">-</div>
        </div>
        <div class="info-row">
            <div class="info-label">片商</div>
            <div class="info-value" id="resultMaker">-</div>
        </div>
        <div class="info-row">
            <div class="info-label">標籤</div>
            <div class="info-value" id="resultTags">-</div>
        </div>
    </div>

    <!-- Footer: 標題 + 編輯/翻譯按鈕 -->
    <div class="info-footer">
        <div class="info-label">標題</div>
        <div class="info-title d-flex align-items-start" id="titleContainer">
            <span id="resultTitle" style="flex:1;">-</span>
            <button id="editTitleBtn" class="btn btn-sm btn-link p-0 ms-1"
                onclick="startEditTitle()" title="編輯標題">
                <i class="bi bi-pencil text-muted"></i>
            </button>
            <button id="translateBtn" class="btn btn-sm btn-link p-0 ms-1 d-none"
                onclick="translateWithAI()" title="批次翻譯 10 片">
                <i class="bi bi-translate"></i>
            </button>
            <span id="translateSpinner" class="spinner-border spinner-border-sm ms-1 d-none"></span>
        </div>
    </div>
</div>
```

### 關鍵樣式（v0.2.3 search.css + theme.css）

#### 本地標記（search.css 第 654-662 行）
```css
.local-badge {
    font-size: 1rem;
    margin-left: 0.5rem;
    cursor: pointer;
}

.local-badge:hover {
    opacity: 0.8;
}
```

#### 切換來源按鈕（search.css 第 267-281 行）
```css
#switchSourceBtn {
    font-size: 1.25rem;
    color: var(--text-secondary);
    opacity: 0.6;
    transition: opacity 0.2s, transform 0.2s;
}

#switchSourceBtn:hover {
    opacity: 1;
    transform: scale(1.1);
}

#switchSourceBtn:disabled {
    opacity: 0.3;
}
```

#### 標籤 badges（search.css 第 333-344 行）
```css
.tag-badge {
    font-size: 0.65rem;
    margin: 1px;
    padding: 2px 6px;
    background: var(--border-light);
    color: var(--text-secondary);
}

.tag-badge.subtitle {
    background: #198754;
    color: #fff;
}
```

#### 圖標按鈕（theme.css 第 180-204 行）
```css
.btn-icon {
    width: 36px;
    height: 36px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    cursor: pointer;
    font-size: 1.125rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
    transition: all var(--duration-fast) ease;
}

.btn-icon:hover {
    background: var(--bg-body);
    color: var(--text-primary);
}

.btn-icon.active {
    background: var(--accent);
    color: var(--text-inverse);
}
```

---

## 解決方案

### 設計決策

1. **Fluent Design 2 升級**：v0.2.3 使用 Bootstrap 樣式（`.btn-link`），在 Fluent 風格下改用圓角圖標按鈕 + 毛玻璃 hover 效果
2. **樣式隔離策略**：
   - 可重用的互動按鈕樣式放 `theme.css`（`.av-card-full-actions`、`.info-icon-btn`），因為 D.4 遷移時 search.html 會直接套用
   - Demo 專屬的模擬數據樣式（如假的標籤內容）放 `design-system.css`
3. **互動元素**：
   - 本地 badge：保留 emoji 📁，加 hover opacity + tooltip
   - 切換來源按鈕：`bi-arrow-repeat` + hover scale 動畫
   - 編輯/翻譯按鈕：`bi-pencil` / `bi-translate` + muted 顏色，hover 變 accent
4. **標籤列**：使用真實 tag-badge 樣式（可直接沿用 search.css 現有的 `.tag-badge`）

### 佈局調整

- **Header**：`h4.av-num` + `.local-badge` + `.info-icon-btn`（切換來源），用 `gap: 0.5rem` 對齊
- **Body**：新增標籤列 `.info-row`，內含多個 `.tag-badge`
- **Footer**：`.info-label` + `.info-value` 改用 flexbox，右側加按鈕組 `.av-card-full-footer-actions`

---

## 實作內容

### 檔案 1：`web/templates/design-system.html`

#### 修改位置：第 699-721 行（av-card-full-info 區塊）

**Before（第 699-721 行）：**
```html
<div class="av-card-full-info">
    <div class="av-card-full-header">
        <h4 class="av-num">CAWD-441</h4>
        <span class="local-badge">本地</span>
    </div>
    <div class="av-card-full-body">
        <div class="info-row">
            <span class="info-label">演員</span>
            <span class="info-value">女優名稱</span>
        </div>
        <div class="info-row">
            <span class="info-label">發行日期</span>
            <span class="info-value">2024-01-15</span>
        </div>
        <div class="info-row">
            <span class="info-label">片商</span>
            <span class="info-value">Kawaii</span>
        </div>
    </div>
    <div class="av-card-full-footer">
        <span class="info-label">標題</span>
        <p class="info-value">作品標題範例，可能很長需要換行顯示</p>
    </div>
</div>
```

**After：**
```html
<div class="av-card-full-info">
    <div class="av-card-full-header">
        <h4 class="av-num">CAWD-441</h4>
        <span class="local-badge" title="本地已有，點擊複製路徑">📁</span>
        <button class="info-icon-btn" title="切換資料來源">
            <i class="bi bi-arrow-repeat"></i>
        </button>
    </div>
    <div class="av-card-full-body">
        <div class="info-row">
            <span class="info-label">演員</span>
            <span class="info-value">乙白沙也加</span>
        </div>
        <div class="info-row">
            <span class="info-label">發行日期</span>
            <span class="info-value">2024-01-15</span>
        </div>
        <div class="info-row">
            <span class="info-label">片商</span>
            <span class="info-value">Kawaii</span>
        </div>
        <div class="info-row">
            <span class="info-label">標籤</span>
            <div class="info-value">
                <span class="tag-badge">美少女</span>
                <span class="tag-badge">單體作品</span>
                <span class="tag-badge">中出</span>
                <span class="tag-badge subtitle">中文字幕</span>
            </div>
        </div>
    </div>
    <div class="av-card-full-footer">
        <div class="av-card-full-footer-content">
            <span class="info-label">標題</span>
            <div class="info-value-with-actions">
                <p class="info-value">【圧倒的4K映像でヌク！】 ボクの彼女は「天然系」の究極エロかわ美少女。幸せ同棲イチャラブ性活 乙白さやか</p>
                <div class="av-card-full-footer-actions">
                    <button class="info-icon-btn" title="編輯標題">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="info-icon-btn" title="AI 批次翻譯 10 部">
                        <i class="bi bi-translate"></i>
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>
```

---

### 檔案 2：`web/static/css/theme.css`

#### 新增位置：第 478 行之後（在檔案末尾，shake animation 之後）

**新增內容：**
```css
/* ========== AV Card Full: Interactive Elements ========== */

/* Info Icon Button - 用於 Full Card header/footer 的圖標按鈕 */
.info-icon-btn {
    width: 28px;
    height: 28px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    cursor: pointer;
    font-size: 1rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    transition: all var(--duration-fast) var(--ease-out);
    flex-shrink: 0;
}

.info-icon-btn:hover {
    background: var(--border-light);
    color: var(--accent);
    transform: scale(1.08);
}

.info-icon-btn:active {
    transform: scale(0.95);
}

.info-icon-btn:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    box-shadow: 0 0 0 4px rgba(90, 200, 250, 0.2);
}

/* Local Badge - 可點擊複製路徑 */
.local-badge {
    font-size: 1rem;
    cursor: pointer;
    transition: opacity var(--duration-fast) var(--ease-out);
    user-select: none;
    -webkit-user-select: none;
}

.local-badge:hover {
    opacity: 0.7;
}

.local-badge:active {
    transform: scale(0.9);
}

/* AV Card Full Footer - 標題區塊佈局 */
.av-card-full-footer-content {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.info-value-with-actions {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
}

.info-value-with-actions .info-value {
    flex: 1;
    min-width: 0; /* Prevent text overflow */
}

.av-card-full-footer-actions {
    display: flex;
    gap: 0.25rem;
    flex-shrink: 0;
}

/* Dark Mode 調整（DaisyUI theme = dim） */
[data-theme="dim"] .info-icon-btn:hover {
    background: rgba(255, 255, 255, 0.08);
}

/* Tag Badge - 從 search.css 移至 theme.css 供全站使用 */
.tag-badge {
    font-size: 0.65rem;
    margin: 1px;
    padding: 2px 6px;
    background: var(--border-light);
    color: var(--text-secondary);
    border-radius: var(--radius-xs, 4px);
    display: inline-block;
}

.tag-badge.subtitle {
    background: #198754;
    color: #fff;
}
```

---

### 檔案 3：`web/static/css/pages/design-system.css`

#### 修改位置：第 906 行之後（.av-card-full-footer 之後）

**新增內容（DS 頁面專屬的 Demo 樣式補充）：**
```css
/* AV Card Full: Demo-specific adjustments */
.ds-page .av-card-full-header {
    /* Ensure header buttons align properly in demo */
    align-items: center;
}

.ds-page .av-card-full-header .av-num {
    flex: 1; /* Push badge and button to the right */
}

/* Tag badges in Full card body */
.ds-page .av-card-full-body .info-value {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}
```

---

## 變更總結

| 檔案 | 變更類型 | 說明 |
|------|---------|------|
| `web/templates/design-system.html` | 修改 | 第 699-721 行：av-card-full-info 區塊補齊互動元素（切換按鈕、標籤列、編輯/翻譯按鈕） |
| `web/static/css/theme.css` | 新增 | 第 478 行後：新增 `.info-icon-btn`、`.local-badge`、`.av-card-full-footer-actions` 等可重用樣式（約 60 行） |
| `web/static/css/pages/design-system.css` | 新增 | 第 906 行後：新增 DS 頁面專屬的 demo 佈局調整（約 10 行） |

---

## 驗證方式

### 視覺檢查
1. 啟動 dev server，瀏覽 `/design-system`，滾動到「AV Card 變體 → 2. Full（詳細頁面）」
2. 檢查 Full card 右側 info panel：
   - Header：番號 + 本地 badge（📁）+ 切換按鈕（↻ 圖標）對齊正常
   - Body：標籤列顯示 4 個 badge（3 個灰色 + 1 個綠色「中文字幕」）
   - Footer：標題文字 + 右側兩個按鈕（✏️ 編輯、🌐 翻譯）

### 互動測試
- Hover 本地 badge：opacity 降低
- Hover 切換按鈕：背景變淺灰 + 圖標變 accent 色 + 輕微放大
- Hover 編輯/翻譯按鈕：同上
- Tab 鍵盤導航：按鈕可聚焦，focus-visible 光圈正常顯示

### 響應式測試
- Desktop (1280px)：佈局正常，按鈕不換行
- Tablet (768px)：av-card-full 改為上下堆疊（已有 RWD 樣式，第 1081-1094 行），按鈕仍在標題右側
- Mobile (320px)：同上

### 主題切換
- Light (wireframe) 模式：文字清晰，按鈕 hover 可見
- Dark (dim) 模式：按鈕 hover 背景使用 `rgba(255, 255, 255, 0.08)`，對比度足夠

### 無障礙
- 所有按鈕有 `title` 屬性（tooltip）
- 鍵盤可操作，focus-visible 樣式明確
- 顏色對比度符合 WCAG AA（text-muted 在 hover 變 accent）

### 對照 v0.2.3
- 打開 `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/templates/search.html`
- 確認所有 info-section 的互動元素（切換、badge、編輯、翻譯）都已在 Full card 中呈現
- 視覺風格已升級為 Fluent Design 2（圓角按鈕、hover 動畫），但功能完整性對齊

---

## 注意事項

1. **樣式隔離**：`theme.css` 中的 `.info-icon-btn` 等樣式會被 D.4 全站遷移直接使用，確保 class 命名通用且不依賴 DS 頁面特定結構
2. **Tag badge 樣式遷移**：`.tag-badge` 原在 `search.css`，現移至 `theme.css` 供全站使用（`/design-system` 頁面不載入 `search.css`）
3. **動畫降級**：`theme.css` 末尾已有 `@media (prefers-reduced-motion: reduce)` 統一處理（D.13），本 task 只需確保按鈕使用 `transition` 不使用 `animation`
4. **Bootstrap 依賴**：v0.2.3 使用 `.btn-sm .btn-link`，此版本改用自定義 `.info-icon-btn`，尺寸和間距已調整為 Fluent 風格（28px vs Bootstrap 的 31px）
