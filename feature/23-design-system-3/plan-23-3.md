# Phase 23-3: Fluent Design 2 視覺強化

## 目標

延續 Phase 23-2 的 DaisyUI + Tailwind 基礎，加入 Fluent Design 2 視覺強化：

1. **Surface Hierarchy** - 清晰的表面層級系統
2. **Color Swatch 真實化** - design-system.html 展示真實 DaisyUI 變數
3. **Theme Toggle** - DS 頁面即時主題切換
4. **Fluent 視覺效果** - Acrylic、高光邊框、統一 Hover

---

## 設計原則：「Fluent 但不微軟」

OpenAver 是**媒體管理工具**，不是生產力軟體。應該比 Win11 更：
- **更暗**：媒體瀏覽適合深色調
- **更沈浸**：減少 UI chrome，讓封面成為主角
- **更動態**：卡片進出、懸停要有「呼吸感」

---

## Tasks

### Phase C.2: 視覺基底（P0 - 必做）

#### C.2: Surface Hierarchy 統一
**目標**：建立清晰的表面層級系統

**新增變數**（`theme.css` 或 `input.css`）：
```css
:root {
  /* Surface 層級（語義化 DaisyUI v5 變數）*/
  --surface-0: var(--color-base-100);  /* 最底層：body */
  --surface-1: var(--color-base-200);  /* 中間層：card, sidebar */
  --surface-2: var(--color-base-300);  /* 最上層：dropdown, modal */

  /* Stroke 邊框 */
  --stroke-subtle: color-mix(in oklch, var(--color-base-content) 8%, transparent);
  --stroke-default: color-mix(in oklch, var(--color-base-content) 16%, transparent);

  /* Glow 發光 */
  --glow-primary: color-mix(in oklch, var(--color-primary) 40%, transparent);
}
```

**修改檔案**：
- `web/static/css/theme.css`

**狀態**：⬚ 待開始

---

#### C.3: Color Swatch 真實化
**目標**：design-system.html 色盤改用 DaisyUI 原生變數

**問題**：目前展示 `--bg-sidebar`、`--accent-red` 等已不存在的變數

**修改**：
- 移除假變數展示
- 改成 DaisyUI v5 原生：`--color-base-100/200/300`、`--color-primary/secondary/accent`
- 加上即時色值顯示（JS 讀取 computed style）

**修改檔案**：
- `web/templates/design-system.html`

**狀態**：⬚ 待開始

---

#### C.4: Theme Toggle 加入 DS 頁
**目標**：design-system.html 右上角加入主題切換按鈕

**功能**：
- wireframe ↔ dim 即時切換
- 所有元件展示即時更新
- 顯示當前主題名稱

**修改檔案**：
- `web/templates/design-system.html`

**狀態**：⬚ 待開始

---

### Phase C.3: Fluent 強化（P1 - 重要）

#### C.5: Acrylic + Border Highlight
**目標**：卡片/浮層加入 Fluent 高光邊框

**效果**：
```css
.fluent-card {
  /* 頂部高光線 */
  box-shadow:
    inset 0 1px 0 color-mix(in oklch, var(--color-base-content) 8%, transparent),
    var(--fluent-shadow-4);
}

.fluent-card:hover {
  box-shadow:
    inset 0 1px 0 color-mix(in oklch, var(--color-base-content) 12%, transparent),
    var(--fluent-shadow-8),
    0 0 20px var(--glow-primary);
}
```

**修改檔案**：
- `web/static/css/input.css`（Fluent utility）

**狀態**：⬚ 待開始

---

#### C.6: Spotlight Search 玻璃膠囊
**目標**：搜尋框加入 Acrylic 效果

**效果**：
- 背景：`backdrop-filter: blur(20px)`
- 內層高光：`inset 0 1px 0 rgba(255,255,255,0.1)`
- Focus：輕微 scale(1.02) + glow

**修改檔案**：
- `web/static/css/theme.css`（`.spotlight-search`）

**狀態**：⬚ 待開始

---

#### C.7: Card Hover 機制統一
**目標**：所有卡片統一懸停效果

**統一效果**：
```css
.card-hoverable {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card-hoverable:hover {
  transform: translateY(-4px) scale(1.01);
  box-shadow: var(--fluent-shadow-16);
}
```

**套用範圍**：
- `.gallery-card`
- `.av-card`
- `.fluent-card`

**修改檔案**：
- `web/static/css/theme.css`

**狀態**：⬚ 待開始

---

### Phase C.4: Design System 完善（P2 - 錦上添花）

#### C.8: State Matrix（元件狀態矩陣）
**目標**：每個核心元件展示 default / hover / active / disabled 狀態

**展示格式**：
```
Button:  [Default] [Hover] [Active] [Disabled]
Input:   [Default] [Focus] [Error]  [Disabled]
Card:    [Default] [Hover] [Selected]
```

**修改檔案**：
- `web/templates/design-system.html`

**狀態**：⬚ 待開始

---

#### C.9: Spacing / Elevation 範例
**目標**：展示 Fluent 2 的空間與陰影系統

**內容**：
- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
- Shadow levels: shadow-2 / 4 / 8 / 16 / 28 / 64

**修改檔案**：
- `web/templates/design-system.html`

**狀態**：⬚ 待開始

---

#### C.10: Navigation Rail（收合模式）
**目標**：Sidebar 收合時改為 Navigation Rail 風格

**效果**：
- Icon 固定 24px
- Active 狀態：圓角 pill + 淡 glow
- 展開時：傳統 sidebar menu

**修改檔案**：
- `web/templates/base.html`

**狀態**：⬚ 待開始

---

## 執行順序

```
Phase C.2 - 視覺基底（馬上做）
├─ C.2: Surface Hierarchy 統一
├─ C.3: Color Swatch 真實化
└─ C.4: Theme Toggle 加入 DS 頁

Phase C.3 - Fluent 強化（看效果再做）
├─ C.5: Acrylic + Border Highlight
├─ C.6: Spotlight Search 玻璃膠囊
└─ C.7: Card Hover 機制統一

Phase C.4 - DS 完善
├─ C.8: State Matrix
├─ C.9: Spacing / Elevation 範例
└─ C.10: Navigation Rail
```

---

## 驗證清單

- [ ] C.2: Surface hierarchy 變數可用
- [ ] C.3: Color swatch 展示真實 DaisyUI 變數
- [ ] C.4: Theme toggle 即時切換
- [ ] C.5: Fluent 高光邊框效果
- [ ] C.6: Spotlight search Acrylic 效果
- [ ] C.7: Card hover 統一
- [ ] C.8: State matrix 展示完整
- [ ] C.9: Spacing/Elevation 範例
- [ ] C.10: Navigation Rail 收合模式

---

## 相關檔案

```
web/
├── static/css/
│   ├── input.css              # DaisyUI + Fluent tokens
│   ├── theme.css              # 橋接變數 + 元件樣式
│   ├── tailwind.css           # 編譯輸出
│   └── pages/
│       ├── design-system.css  # DS 頁專用
│       ├── search.css         # Progress + Drag Overlay
│       └── gallery.css        # Mini Terminal
└── templates/
    ├── base.html              # Sidebar
    └── design-system.html     # 展示頁面
```

---

## 備註

### 不採用的建議

| Codex 建議 | 不採用原因 |
|-----------|-----------|
| DaisyUI drawer 取代 offcanvas | 遷移成本 > 收益，現有 Alpine.js 方案可用 |
| 全站 Mica/Noise 背景 | 60000+ 封面頁會影響效能，改為可選啟用 |
| Terminal 改成 mockup-code | 語義不對，保留現有風格加 Acrylic |
| Card Hover「右下亮邊」| 大量卡片會太吵雜，只在焦點卡片使用 |

### 暫緩的功能

- **Navigation Rail**：需要重構 sidebar 邏輯，視情況再做
- **Ambient Light**：效能影響需評估，可能移到 Phase E (GSAP)

### ⚠️ 範圍擴大說明（2026-02-06 Code Review 決議）

**原則調整**：Phase 23-3 原訂「DS-only」，但經 Code Review 後決定：
- **正式承認 scope 已擴大**
- **保留 theme.css / input.css 的全站變更**
- **其他頁面視覺回歸留到下一個 branch 再逐頁修復**

**已知影響範圍**：

| Task | 修改檔案 | 影響 | 風險評估 |
|------|---------|------|---------|
| C.5 | `input.css` | `.fluent-card` 高光 + glow | 低 - 純視覺 |
| C.6 | `theme.css` | `.spotlight-search` Acrylic | 低 - 純視覺 |
| C.7 | `theme.css` | `.gallery-card` hover 統一 | 低 - 純視覺 |

**Known Issues**：
- 全站樣式重構中，非 `/design-system` 頁面暫時可能不穩定
- 這是預期行為，將在後續 branch 逐頁修復
- `/design-system` 頁面為當前優先，作為視覺規範參考

---

**文件版本**：1.1
**最後更新**：2026-02-06
**前置分支**：feature/23-design-system-2
