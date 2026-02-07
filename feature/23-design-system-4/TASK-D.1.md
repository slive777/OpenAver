# D.1: 修正 AV Card Preview Overlay Actions

**狀態**：⬚ 待實作
**優先級**：P0

---

## 問題摘要

AV Card Preview 變體（Gallery 網格封面卡片）的 hover overlay 按鈕使用了錯誤的圖標和功能。目前使用 `bi-eye`（查看）+ `bi-folder-plus`（加入資料夾），但對照 v0.2.3 穩定版，實際功能應為 **播放影片** + **複製檔案路徑**。

此外，目前所有 3 張 Preview 卡片（1 大 + 2 小）都顯示 overlay，但小卡空間不足，應調整為：
- **Featured 大卡**（第 1 張）：顯示 overlay，兩個圓形玻璃按鈕，水平居中
- **小卡**（第 2、3 張）：hover 只有 scale + shadow，不顯示按鈕

**影響範圍**：`/design-system` 頁面 AV Card Variants 區塊（行 631-686）

---

## 現狀分析

### 當前 HTML 結構（design-system.html）

**Featured 大卡（行 641-654）**：
```html
<div class="av-card-preview featured">
    <div class="av-card-preview-img">
        <img src="/static/img/demo/sone-103.jpg" alt="cover">
        <div class="av-card-preview-overlay">
            <button class="btn-glass"><i class="bi bi-eye"></i></button>
            <button class="btn-glass"><i class="bi bi-folder-plus"></i></button>
        </div>
        <span class="av-card-preview-badge">HD</span>
    </div>
    <div class="av-card-preview-footer">
        <span class="av-num">SONE-103</span>
        <span class="av-actress">女優名</span>
    </div>
</div>
```

**小卡 1（行 656-665）**：
```html
<div class="av-card-preview">
    <div class="av-card-preview-img">
        <img src="/static/img/demo/mide-974.jpg" alt="cover">
        <span class="av-card-preview-badge local">本地</span>
    </div>
    <div class="av-card-preview-footer">
        <span class="av-num">MIDE-974</span>
        <span class="av-actress">女優名</span>
    </div>
</div>
```

**小卡 2（行 667-676）**：
```html
<div class="av-card-preview">
    <div class="av-card-preview-img">
        <img src="/static/img/demo/fc2-1723984.jpg" alt="cover">
        <span class="av-card-preview-badge">FC2</span>
    </div>
    <div class="av-card-preview-footer">
        <span class="av-num">FC2-PPV-1723984</span>
        <span class="av-actress">素人</span>
    </div>
</div>
```

**問題點**：
1. ❌ 圖標錯誤：`bi-eye` + `bi-folder-plus`（應為 `bi-play-fill` + `bi-clipboard`）
2. ❌ 小卡 1、2 沒有 overlay div，但 CSS 會對所有 `.av-card-preview:hover` 顯示 overlay
3. ❌ Overlay 布局未調整（應使用圓形玻璃按鈕，水平居中）

### 當前 CSS 樣式（design-system.css）

**Overlay 樣式（行 775-789）**：
```css
.av-card-preview-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, oklch(0% 0 0 / 0.7) 0%, oklch(0% 0 0 / 0.3) 50%, transparent 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    opacity: 0;
    transition: opacity var(--fluent-duration-fast) var(--fluent-ease-standard);
}

.av-card-preview:hover .av-card-preview-overlay {
    opacity: 1;
}
```

**問題點**：
- 布局使用 `gap: 0.75rem`，但未定義按鈕為圓形
- 無 `.featured` 專屬樣式，導致小卡可能誤顯示 overlay

---

## 參考：v0.2.3 原始設計

### Gallery Card Actions（v0.2.3 theme.css 行 329-344）

```css
/* Hover Overlay Actions */
.gallery-card-actions {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(2px);
    opacity: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    transition: opacity var(--duration-fast) ease;
}

.gallery-card:hover .gallery-card-actions {
    opacity: 1;
}
```

### 玻璃按鈕樣式（v0.2.3 theme.css 行 208-226）

```css
.btn-glass {
    padding: 0.4rem 1rem;
    border: 1px solid rgba(255, 255, 255, 0.4);
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.15);
    color: var(--text-inverse);
    font-size: 0.75rem;
    font-weight: 500;
    text-decoration: none;
    cursor: pointer;
    transition: all var(--duration-fast) ease;
    backdrop-filter: blur(4px);
}

.btn-glass:hover {
    background: rgba(255, 255, 255, 0.3);
    border-color: rgba(255, 255, 255, 0.6);
    color: var(--text-inverse);
}
```

**實際使用的圖標**（v0.2.3 實際頁面觀察）：
- 播放按鈕：`bi-play-fill`
- 複製路徑按鈕：`bi-clipboard`

**設計特點**：
- 使用 `rgba(0, 0, 0, 0.4)` 半透明黑底 + `backdrop-filter: blur(2px)` 輕微模糊
- 按鈕使用 `.btn-glass` class，白色玻璃質感
- 圓形圖標，居中排列

---

## 解決方案

### 設計決策

1. **Featured 卡片專屬 overlay**：只有 `.av-card-preview.featured` 顯示 overlay
2. **圓形玻璃按鈕**：設計 `.btn-glass-circle` class，用於 overlay 內
3. **圖標修正**：
   - 第 1 個按鈕：`bi-play-fill`（播放影片）
   - 第 2 個按鈕：`bi-clipboard`（複製路徑）
4. **小卡 hover**：只保留 `scale + shadow` 效果，無 overlay

### 樣式隔離規則

- **`design-system.css`**：放 Demo 專屬樣式
  - `.ds-card-mosaic .av-card-preview.featured .av-card-preview-overlay`（只在 DS 頁面生效）
  - `.btn-glass-circle`（圓形玻璃按鈕，可能在 D.4 遷移時移至 `theme.css`）
- **`theme.css`**：不修改（overlay 相關樣式目前僅用於 DS 頁面展示）

---

## 實作內容

### 檔案 1：`web/templates/design-system.html`

#### 修改 1：Featured 卡片 overlay 圖標（行 644-646）

**Before**:
```html
<div class="av-card-preview-overlay">
    <button class="btn-glass"><i class="bi bi-eye"></i></button>
    <button class="btn-glass"><i class="bi bi-folder-plus"></i></button>
</div>
```

**After**:
```html
<div class="av-card-preview-overlay">
    <button class="btn-glass-circle" title="播放影片"><i class="bi bi-play-fill"></i></button>
    <button class="btn-glass-circle" title="複製路徑"><i class="bi bi-clipboard"></i></button>
</div>
```

**變更說明**：
- 圖標改為 `bi-play-fill` + `bi-clipboard`
- 按鈕 class 改為 `.btn-glass-circle`（圓形玻璃按鈕）
- 加入 `title` 屬性提升無障礙性

#### 修改 2：小卡 1、2 移除 overlay（確認現狀）

**檢查點**：
- 小卡 1（行 656-665）已無 `.av-card-preview-overlay` → ✅ 無需修改
- 小卡 2（行 667-676）已無 `.av-card-preview-overlay` → ✅ 無需修改

**CSS 確認**：確保 CSS 不會對小卡誤顯示 overlay（見檔案 2）

---

### 檔案 2：`web/static/css/pages/design-system.css`

#### 修改 1：限制 overlay 只顯示在 Featured 卡片（行 775-789）

**Before**:
```css
.av-card-preview-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, oklch(0% 0 0 / 0.7) 0%, oklch(0% 0 0 / 0.3) 50%, transparent 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    opacity: 0;
    transition: opacity var(--fluent-duration-fast) var(--fluent-ease-standard);
}

.av-card-preview:hover .av-card-preview-overlay {
    opacity: 1;
}
```

**After**:
```css
/* Overlay 只顯示在 Featured 大卡 */
.av-card-preview.featured .av-card-preview-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, oklch(0% 0 0 / 0.7) 0%, oklch(0% 0 0 / 0.3) 50%, transparent 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    opacity: 0;
    transition: opacity var(--fluent-duration-fast) var(--fluent-ease-standard);
}

.av-card-preview.featured:hover .av-card-preview-overlay {
    opacity: 1;
}
```

**變更說明**：
- Selector 改為 `.av-card-preview.featured .av-card-preview-overlay`（只作用於 Featured 卡片）
- `gap` 調整為 `1rem`（圓形按鈕間距略寬）

#### 修改 2：新增圓形玻璃按鈕樣式（插入在 `.av-card-preview-overlay` 之後）

**插入位置**：行 789 後

**新增內容**：
```css
/* 圓形玻璃按鈕（用於 Overlay Actions） */
.btn-glass-circle {
    width: 48px;
    height: 48px;
    border: 1px solid rgba(255, 255, 255, 0.4);
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.15);
    color: oklch(100% 0 0);
    font-size: 1.25rem;
    cursor: pointer;
    transition: all var(--fluent-duration-fast) var(--fluent-ease-standard);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 12px oklch(0% 0 0 / 0.3);
}

.btn-glass-circle:hover {
    background: rgba(255, 255, 255, 0.3);
    border-color: rgba(255, 255, 255, 0.6);
    transform: scale(1.08);
    box-shadow: 0 6px 16px oklch(0% 0 0 / 0.4);
}

.btn-glass-circle:active {
    transform: scale(0.95);
}
```

**設計細節**：
- 固定尺寸 `48px × 48px`（符合 Fluent Design touch target 規範）
- 圓形：`border-radius: 50%`
- 玻璃質感：半透明白底 + `backdrop-filter: blur(8px)`
- Hover 效果：`scale(1.08)` + 強化陰影
- Active 效果：`scale(0.95)` 按下回饋

#### 修改 3：小卡 hover 效果保留（確認現狀）

**檢查點**：行 747-755 的 `.av-card-preview:hover` 樣式

**確認無誤**：
```css
.av-card-preview:hover {
    transform: translateY(-4px) scale(1.01);
    box-shadow:
        inset 0 1px 0 color-mix(in oklch, var(--color-base-content) 12%, transparent),
        0 0 0 2px var(--accent),
        0 0 20px var(--glow-primary),
        var(--fluent-shadow-16);
    border-color: var(--accent);
}
```

此樣式會套用到所有 `.av-card-preview`，包含小卡，符合預期（小卡只有 scale + shadow，無 overlay）。

---

## 變更總結

| 檔案 | 變更類型 | 說明 |
|------|---------|------|
| `web/templates/design-system.html` | 修改 | Featured 卡片 overlay 圖標改為 `bi-play-fill` + `bi-clipboard`，按鈕改用 `.btn-glass-circle` |
| `web/static/css/pages/design-system.css` | 修改 + 新增 | 限制 overlay 只顯示在 Featured 卡片，新增 `.btn-glass-circle` 圓形玻璃按鈕樣式 |

**影響行數**：
- `design-system.html`：3 行修改（行 644-646）
- `design-system.css`：37 行修改/新增（行 775-789 修改，插入 28 行新樣式）

---

## 驗證方式

### 視覺驗證

1. **啟動 dev server**：`python -m web.app`
2. **瀏覽 `/design-system`**，滾動到 **AV Card Variants** 區塊（第 6 區塊）
3. **Featured 大卡（SONE-103）**：
   - Hover 時顯示 overlay
   - 兩個圓形玻璃按鈕，水平居中
   - 左邊按鈕圖標為 `播放`（▶），右邊為 `剪貼板`（📋）
   - 按鈕 hover 時有 scale 放大效果
4. **小卡 1（MIDE-974）+ 小卡 2（FC2-PPV-1723984）**：
   - Hover 時**不顯示** overlay
   - 只有卡片本身的 scale + shadow + 發光邊框效果

### 互動驗證

1. **鍵盤 Tab**：
   - 焦點可移至兩個圓形按鈕
   - `:focus-visible` 光圈可見（若已實作，見 D.13）
2. **按鈕 hover**：
   - 背景變亮（`rgba(255, 255, 255, 0.3)`）
   - 邊框變亮（`rgba(255, 255, 255, 0.6)`）
   - 按鈕放大 8%（`scale(1.08)`）
3. **按鈕 active**：
   - 按下時縮小 5%（`scale(0.95)`）

### RWD 驗證

- **Desktop 1280px**：Featured 大卡顯示正常，按鈕不擁擠
- **Tablet 768px**：Mosaic layout 變單欄，Featured 卡片 `aspect-ratio: 3/2`，按鈕仍可見
- **Mobile 320px**：按鈕尺寸 48px 符合 touch target 規範

### 主題切換驗證

- **Light (wireframe)**：
  - Overlay 黑色漸層清晰
  - 白色玻璃按鈕對比度足夠
- **Dark (dim)**：
  - Overlay 漸層在深色封面上可見
  - 玻璃按鈕邊框亮度足夠

### 無障礙驗證

- **Screen Reader**：`title` 屬性（「播放影片」、「複製路徑」）可朗讀
- **Reduced Motion**：`prefers-reduced-motion: reduce` 下，按鈕 `transform` 效果應降級（需 D.13 統一處理）

---

## 備註

### 圖標語義

- **`bi-play-fill`**：實心播放圖標，直觀表示「播放影片」操作
- **`bi-clipboard`**：剪貼板圖標，表示「複製檔案路徑到剪貼板」操作

### 未來遷移考量

- `.btn-glass-circle` 可能在 D.4 全站遷移時移至 `theme.css`，供其他頁面重用
- 若 Gallery 頁面的 Preview 卡片需要相同 overlay，可直接套用此樣式

### 相關 Task

- **D.2**：AV Card Full 加入互動元素（同樣需要按鈕樣式）
- **D.13**：統一 `:focus-visible` 光圈樣式、`prefers-reduced-motion` 降級
