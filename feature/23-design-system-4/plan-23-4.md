# Phase 23-4: Design System 完整性審計 + 元件補齊 + Page Compositions

## Context

Phase 23-1/2/3 建立了 DaisyUI + Fluent Design 2 的視覺基礎（tokens、基礎元件、Fluent 效果），但比對 v0.2.3 穩定版後發現 `/design-system` 仍有重要功能元件缺失或不正確。Phase 23-4 的目標是**補齊所有缺口 + 建立頁面級 Mockup**，讓 design system 成為 D.4 全站遷移的完整參考。

**分支**：`feature/23-design-system-4`
**基於**：`main`（已合併 23-3）

---

## 開發規範（Codex Review 補充）

### 樣式隔離規則

防止未遷移頁面出現視覺回歸：

| 檔案 | 允許放的內容 | 禁止 |
|------|-------------|------|
| `theme.css` | 可重用 token / utility（`--fluent-*`、`.fluent-card`） | demo 專屬樣式 |
| `design-system.css` | DS 頁面專屬樣式，class 一律 `ds-` 前綴 | 通用 selector |

**例外條款**：既有業務 class（如 `.avlist-card`、`.av-card-full`）可直接使用，但必須包在 `.ds-page` 或 `.ds-*` 容器下，確保樣式不外溢到其他頁面。
| `input.css` | Tailwind / DaisyUI 設定 | 直接元素 selector |

**原則**：`theme.css` 新增的 class 必須是 D.4 遷移時各頁面會直接套用的；純展示用途的樣式只放 `design-system.css`。

### 檔案拆分

`design-system.html` 目前 1543 行，新增內容後預估超過 2500 行。採用 Jinja2 `{% include %}` 拆分：

```
web/templates/
├── design-system.html              ← 主框架（TOC + include）
└── design_system/
    ├── page-states.html            ← D.3/D.4/D.5
    ├── gallery-components.html     ← D.6/D.7/D.8
    ├── settings-components.html    ← D.9
    └── page-compositions.html      ← D.14/D.15
```

已有的區塊暫不拆（避免動太多），只有新增區塊用 include。

### 前端驗收標準

每個 Task 完成時檢查：

- [ ] Desktop 1280px + Tablet 768px + Mobile 320px 排版正常
- [ ] 鍵盤 Tab / focus-visible 可操作
- [ ] Light (wireframe) / Dark (dim) 對比度可讀
- [ ] `prefers-reduced-motion` 下動畫降級（無 transform/transition）

---

## GAP 分析摘要

| 類別 | 問題 | 嚴重度 |
|------|------|--------|
| AV Card Preview | overlay 按鈕錯誤（eye/folder → 應為 play/copy） | P0 |
| AV Card Full | 完全缺少互動按鈕（編輯/翻譯/切換來源） | P0 |
| Search 頁面狀態 | Empty/Error/Loading 三種狀態未展示 | P0 |
| Gallery 元件 | 資料夾管理、統計卡片、女優別名管理缺失 | P1 |
| Settings 元件 | 整頁元件都未出現（收合區塊、變數下拉、多層路徑） | P1 |
| Modal/Toast/Help | 對話框、互動 Toast、鍵盤快捷鍵表格缺失 | P2 |
| Page Compositions | 缺少頁面級排版 mockup，無法預覽遷移後成品 | P1 |

---

## Tasks

### GROUP 1: AV Card 修正（P0）

#### D.1: 修正 AV Card Preview Overlay Actions
- **問題**：目前 overlay 有 `bi-eye` + `bi-folder-plus`，v0.2.3 實際是播放 + 複製路徑
- **修改**：
  - 按鈕改為 `bi-play-fill`（播放）+ `bi-clipboard`（複製路徑）
  - 重新設計 overlay 布局（兩個圓形玻璃按鈕，水平居中）
  - **規格決定**：只有 Featured 卡片（第 1 張大卡）顯示 overlay；其餘 2 張小卡 hover 只有 scale + shadow（因為小卡空間不足放按鈕）
- **檔案**：`design-system.html`、`design-system.css`

#### D.2: AV Card Full 加入互動元素
- **問題**：Full variant 目前是純展示，缺少 v0.2.3 的所有操作按鈕
- **新增**：
  - Header：切換來源按鈕（`bi-arrow-repeat`）、本地 badge（可點擊複製路徑）
  - Body：標籤 badges 列
  - Footer：標題旁加 編輯按鈕（`bi-pencil`）+ 翻譯按鈕（`bi-translate`）
- **樣式隔離**：互動按鈕的 CSS 放 `theme.css`（`.av-card-full-actions`），因為遷移時 search.html 會直接套用
- **檔案**：`design-system.html`、`theme.css`（`.av-card-full-actions`）

---

### GROUP 2: Search 頁面狀態（P0）

新增檔案：`web/templates/design_system/page-states.html`

#### D.3: Search Empty State
- 大圖標 `bi-film` + 說明文字
- 3 個 Action 按鈕：加入檔案 / 加入資料夾 / 我的最愛
- 小提示文字：「也可直接拖入檔案或資料夾」
- Fluent 增強：玻璃按鈕、微動畫圖標

#### D.4: Search Error State
- 警告圖標 `bi-exclamation-triangle` + 錯誤訊息
- 多檔案導航：← 1/5 →（prev/indicator/next）
- Fluent 增強：紅色微光邊框

#### D.5: Search Loading State（情境展示）
- 在 Page States 區塊中展示 Progress Indicator 在搜尋容器中的樣子
- 包含查詢標題 + spinner + 進度條
- 可引用現有 Progress 元件，補充情境脈絡

---

### GROUP 3: Gallery 頁面元件（P1）

新增檔案：`web/templates/design_system/gallery-components.html`

#### D.6: 資料夾管理區塊
- 完整 `.avlist-card` 組合：
  - Header：標題 + 新增資料夾按鈕 + 手動輸入切換
  - 手動輸入列：文字輸入框 + 新增按鈕
  - 資料夾列表（重用現有 folder-item）
  - 輸出資訊列：檔案圖標 + 路徑 + 設定連結
  - Action 區：「產生網頁」Hero 按鈕 + Loading 狀態
  - 完成區：複製路徑按鈕

#### D.7: Stats Card + NFO 更新
- 統計卡片：快取影片數量、上次執行時間
- NFO 更新列：琥珀色 badge（「需補全：N 部」）+ 漸層按鈕
- 按鈕狀態：default / loading（spinner）/ completed（check）

#### D.8: 女優別名管理卡片
- 收合式卡片（Alpine.js `x-data`）
- 表單：舊名 → 箭頭 → 新名 + 新增按鈕 + 計數顯示
- 別名列表：舊名（黃色 monospace）→ 新名（綠色 monospace）+ 已套用數 + 刪除按鈕

---

### GROUP 4: Settings 頁面元件（P1）— 理想版

新增檔案：`web/templates/design_system/settings-components.html`

**設計策略**：不忠實復刻現有 settings.html，而是直接做**理想版**作為 D.4 遷移的設計藍圖。
現有 UX 問題：4 張 card 同等權重無層級、進階設定難發現、佈局單調（全部 row/col-md-6）、版本和儲存按鈕浮在 card 外。

#### D.9a: 基礎表單元件（理想版）
- **Toggle switch + 說明文字**：DaisyUI toggle + label + description
- **Select 下拉**：主題模式 / 啟動頁面 / 翻譯服務
- **Number input + 單位後綴**：input-group + suffix（字元/MB）
- **Text input + 說明**：路徑輸入 / 播放器路徑
- UX 改善：表單列改為更有層次的 label-above-input 佈局

#### D.9b: 收合區塊 + 變數插入（理想版）
- **Collapse toggle**：卡片式設計（非僅文字連結），chevron 旋轉動畫
- **Variable dropdown**：`{num}` `{title}` `{actor}` 等變數插入，清楚顯示可用變數
- **多層資料夾輸入**：3 層連動（外層/中層/內層）+ 即時預覽路徑
- UX 改善：collapse 可被發現、變數插入視覺提示更強

#### D.9c: 特殊元件（理想版）
- **API Key 警告 Alert**：橘色 alert + 安全提示列表
- **版本 + 檢查更新**：版本文字 + 按鈕（default/loading/完成 三態）
- **儲存按鈕**：primary CTA
- UX 改善：功能性元件視覺上更突出

---

### GROUP 5: Page Compositions — 頁面級 Mockup（P1）

新增檔案：`web/templates/design_system/page-compositions.html`

**目的**：在遷移前預覽各頁面的完整排版和視覺節奏，確認設計方向。非互動，純靜態排版。

**文字節奏檢查**：每個 Composition 完成時確認標題（H2/H3）、內文（body）、註解（small/muted）的行高與間距形成清晰的視覺層級。

#### D.14: Search Page Composition
模擬完整搜尋結果頁面：
- Acrylic header + Spotlight search bar
- Result 區：Cover（左 70%）+ Info panel（右 30%，含所有按鈕）
- File list（底部）+ batch progress bar
- 用真實 demo 數據（SONE-103 封面 + metadata）

#### D.15: Gallery Page Composition
模擬完整 Gallery 頁面：
- 資料夾管理 card（含 2-3 個 folder-item）
- 封面牆 grid（3-4 張 Preview card，含 Featured 大卡 + 小卡排列）
- Stats card + 女優別名 card（收合狀態）

#### ~~D.16: Showcase Page Composition~~ → 移至 Phase 23-5
> D.9a/b/c 已 100% 覆蓋 Settings 元件，Settings Composition 不需要。
> Showcase（gallery_output.html 重設計）規模較大且需要獨立頁面（`/showcase-preview`），
> 移至 `feature/23-design-system-5` 分支，在完整 DS 元件庫基礎上建造。
> 詳見 `feature/23-design-system-5/plan-23-5.md`

---

### GROUP 6: 補充元件 + 收尾（P2）

#### D.10: Modal / Dialog 元件
- DaisyUI modal：標題 + 內文 + 取消/確認按鈕
- Alpine.js 觸發按鈕
- Fluent styling：smoke backdrop、shadow-28、radius-xl

#### D.11: 互動 Toast Demo
- 新增「觸發 Toast」按鈕（Alpine.js show/hide）
- bottom-center slide-up 動畫
- 成功/錯誤/資訊三種樣式

#### D.12: Help 頁面元素（鍵盤快捷鍵 + Accordion）
- `kbd` 標籤樣式展示（Ctrl+K、←→、Esc、Enter）
- 快捷鍵表格（按鍵 + 說明兩欄）

#### D.13: TOC 更新 + 區塊重組 + Focus-visible 統一
- 新增 TOC 項目：Page States、Gallery Components、Settings Components、Page Compositions、Modals
- 確認 ScrollSpy script 涵蓋新區塊
- **焦點樣式升級**：所有可互動元素加 `:focus-visible` 光圈（統一 `outline: 2px solid var(--color-primary); outline-offset: 2px; box-shadow: 0 0 0 4px var(--glow-primary)`）
- **動畫節奏確認**：統一使用現有 motion token（`--duration-fast: 167ms`、`--duration-normal: 250ms`）
- **reduced-motion 統一收斂**：在 `theme.css` 末尾用單一 `@media (prefers-reduced-motion: reduce)` 區塊，一次關閉所有 transition / transform / animation，避免各元件各自處理導致遺漏
- **玻璃層級收斂**：僅 Header + Spotlight Search 使用重 blur，其餘用 surface/stroke 做層次

---

### GROUP 7: 設計審計 + 圓角修正（收尾）

#### D.17a: 穩定修正 — 硬編碼清理 + 暖底色
- 硬編碼色彩替換為語意 token（`#198754` → `var(--color-success)` 等）
- 硬編碼 `border-radius` 替換為 Fluent token（`--fluent-radius-sm/md/lg/xl`）
- 硬編碼 `rgba()` 替換為 `color-mix()` 語法
- 重複定義移除（`.ds-toast-demo`、`.rotate-180 !important`、`.info-icon-btn`）
- inline `h4` style 抽為 `.ds-group-label` / `.ds-variant-label` class
- Progress 選擇器加 `.ds-page` scope 防止外溢
- 暖奶白底色回歸（`--color-base-100: oklch(98.5% 0.005 85)`）
- **檔案**：`design-system.css`、`design-system.html`、`gallery-components.html`、`settings-components.html`、`input.css`

#### D.17b: Fluent 風格強化 — Easing + Transition 精簡
- 所有 `ease` / `ease-in-out` 替換為 Fluent token（`var(--fluent-ease-standard)` / `var(--ease-out)`）
- 所有 `transition: all` 替換為具體屬性列表（效能優化）
- `.btn-hero` base 樣式 unscope 至 `theme.css` 全域，刪除 gallery-scoped 重複定義
- Glass 層級註解（Heavy / Medium / None）加入 `theme.css` 頂部
- **檔案**：`theme.css`、`design-system.css`

#### D.18: Card 圖片圓角對齊 — 底部直角修正
- `.av-card-preview-img` / `.gallery-card-img` 的 `border-radius` 從四角 8px 改為只圓頂部（`var(--radius-sm) var(--radius-sm) 0 0`）
- Card States 3 個 placeholder `<div>` inline style 同步修正
- **檔案**：`design-system.css`、`theme.css`、`design-system.html`

---

## 執行順序

```
Phase 1 - P0 修正（先修好再加新的）          ✅ 完成
  D.1  修正 Preview Overlay                 ✅
  D.2  Full Card 加入互動元素                ✅
  D.3  Search Empty State                   ✅
  D.4  Search Error State                   ✅
  D.5  Search Loading State                 ✅

Phase 2 - P1 補齊（頁面級元件）              ✅ 完成
  D.6  資料夾管理區塊                        ✅
  D.7  Stats Card + NFO 更新                ✅
  D.8  女優別名管理卡片                      ✅
  D.9  Settings 表單元件展示                 ✅

Phase 3 - P1 Page Compositions（頁面級 mockup） ✅ 完成
  D.14 Search Page Composition              ✅
  D.15 Gallery Page Composition             ✅
  (D.16 → 移至 23-design-system-5)

Phase 4 - P2 收尾                           ✅ 完成
  D.10 Modal / Dialog                       ✅
  D.11 互動 Toast Demo                      ✅
  D.12 Help 頁面元素                         ✅
  D.13 TOC + Focus-visible + 收尾           ✅

Phase 5 - 設計審計 + 圓角修正                ✅ 完成
  D.17a 穩定修正（硬編碼清理 + 暖底色）       ✅
  D.17b Fluent 風格強化（easing + transition） ✅
  D.18  Card 圖片圓角對齊                    ✅
```

---

## 修改檔案清單

| 檔案 | 用途 | 規則 |
|------|------|------|
| `web/templates/design-system.html` | 主框架 + TOC + `{% include %}` | 新區塊用 include 拆分 |
| `web/templates/design_system/page-states.html` | D.3/D.4/D.5 | 新增 |
| `web/templates/design_system/gallery-components.html` | D.6/D.7/D.8 | 新增 |
| `web/templates/design_system/settings-components.html` | D.9 | 新增 |
| `web/templates/design_system/page-compositions.html` | D.14/D.15/D.16 | 新增 |
| `web/static/css/pages/design-system.css` | DS 專屬樣式（`ds-` 前綴） | demo 展示用 |
| `web/static/css/theme.css` | 可重用元件樣式 | 遷移時各頁面會直接套用的 |

**參考檔案 — v0.2.3 穩定版快照**（唯讀）：

> 改版前的穩定版本，所有功能元件的「正確外觀」參考來源。
> 絕對路徑：`/home/peace/OpenAver/feature/OpenAver 0.2.3/`

- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/templates/search.html`
- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/templates/gallery.html`
- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/templates/settings.html`
- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/templates/help.html`
- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/static/css/theme.css`
- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/static/css/pages/search.css`
- `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/static/css/pages/gallery.css`

---

## 驗證方式

### 後端
- `source venv/bin/activate && pytest tests/ -v --ignore=tests/smoke -m "not smoke"`

### 前端（每個 Task 完成時）
- [ ] 啟動 dev server，瀏覽 `/design-system` 確認新區塊顯示
- [ ] Desktop 1280px + Tablet 768px + Mobile 320px 排版正常
- [ ] Light (wireframe) / Dark (dim) 切換，對比度可讀
- [ ] 鍵盤 Tab 順序合理，focus-visible 光圈可見
- [ ] `prefers-reduced-motion` 下無 transform/transition 動畫

### 最終驗收
- [ ] 對照 v0.2.3 每個頁面，確認所有元件都有對應展示
- [ ] Page Compositions 視覺節奏滿意
- [ ] 互動元素可操作（toast、modal、collapse）
- [ ] 無 console error / warning
