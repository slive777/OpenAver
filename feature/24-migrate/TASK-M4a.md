# TASK-M4a: settings.html Bootstrap → DaisyUI + Design System 遷移

## 目標

將 Settings 頁面的所有 Bootstrap class 替換為 DaisyUI + Fluent Design System，啟用 theme.css 的 `#settings-components` scope，並清理 110 行 inline `<style>` 重複定義。

## 背景

### 新舊版比較

**結構差異**：
- **新版 (v0.3.0)**：使用 Alpine.js 收合區塊（`x-data`, `x-show`, `x-collapse`），inline style 110 行
- **舊版 (v0.2.3)**：使用 Bootstrap Collapse（`data-bs-toggle`, `.collapse`），inline style 104 行
- **共同點**：Bootstrap class 保留完整（`.form-control`, `.btn-outline-primary`, `.card` 等）

**主要變化**：
- L282-291, L438-447：收合區塊從 Bootstrap Collapse → Alpine.js `x-data`
- L303-321, L348-358：變數插入 dropdown 從 Bootstrap → Alpine.js 控制
- L547：主題切換從 `data-theme` JS 控制 → Alpine.js `x-model="theme"`

### 與前期工作的關係

- **M1**（base + 簡單頁面）：已完成 help.html、showcase.html 的 DaisyUI 遷移
- **M2a**（Scanner）：已完成 scanner.html 的 Bootstrap → DaisyUI 替換
- **M3**（Search）：已完成 search.html 的 Bootstrap → DaisyUI 替換
- **M4a**（Settings）：第四個處理的複雜頁面，Bootstrap → DaisyUI + **Design System 對齊**

### 遷移範圍

**M4a 範圍**：
1. **Bootstrap → DaisyUI class 替換**（HTML + inline style 內的選擇器）
2. **加入 `id="settings-components"` scope wrapper**，啟用 theme.css L1308-1710 的 Settings 元件
3. **移除 inline `<style>` 中與 theme.css 重複的定義**（保留 Alpine.js 動畫、特殊樣式）
4. **對齊 Design System**：套用 design_system/settings-components.html 的語義 class

**不在範圍內**：
- JS 邏輯重構（功能不動，只替換 Bootstrap class）
- CSS 變數調整（theme.css 已定義完整，不需新增）

> **⚠️ Opus 審核追加**：Inline JS 中的 Bootstrap class（`spinner-border`、`text-danger`、`dropdown-item` 等）**必須在 M4a 替換**，否則 M5 移除 Bootstrap 時會壞掉。M4b 是「JS 抽離」不改 class。

## 修改範圍

| 檔案 | 說明 |
|------|------|
| `/home/peace/OpenAver/web/templates/settings.html` | 主要修改目標（HTML 模板 + inline `<style>` 清理） |

**不需修改**：
- `/home/peace/OpenAver/web/static/css/theme.css` — Settings 元件已定義完成（L1308-1710）
- `/home/peace/OpenAver/web/static/js/` — Settings 無獨立 JS 模組，所有邏輯在 HTML 內

## Bootstrap Class 審計

### 4.1 HTML 模板（靜態）

#### 表單控制項

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L132-138 | `form-check form-switch` + `form-check-input` + `form-check-label` | `settings-form-group` + `settings-label` + `toggle toggle-primary` + `label-text` | Toggle switch（女優畫廊模式） |
| L136 | `badge bg-danger` | `badge badge-error badge-sm` | Beta 標籤 |
| L144-150 | `form-check form-switch` + `form-check-input` + `form-check-label` | `settings-form-group` + `settings-label` + `toggle toggle-primary` + `label-text` | Toggle switch（無碼模式） |
| L151 | `text-muted d-block` | `settings-hint` | 說明文字（無碼模式） |
| L156-166 | `row mb-3` + `col-md-6` | `settings-form-row` + `row-label` + input | 我的最愛資料夾 |
| L162 | `form-control form-control-sm` | `input input-bordered input-sm` | 文字輸入框 |
| L164 | `text-muted` | `settings-hint` | 範例說明文字 |
| L168-175 | `row mb-3` + `col-md-6` | `settings-form-group` | 啟用標題翻譯 toggle |
| L171 | `form-check-input` | `toggle toggle-primary` | Toggle switch |
| L172 | `form-check-label` | `settings-label` + `label-text` | Toggle label |
| L179-189 | `row mb-3` + `col-md-6` | `settings-form-row` + `row-label` + select | 翻譯服務 |
| L184 | `form-select form-select-sm` | `select select-bordered select-sm` | Select 下拉選單 |
| L198-205 | `input-group input-group-sm` | `variable-input-group` | Ollama URL + 測試按鈕 |
| L199 | `form-control` | `input input-bordered input-sm` | URL 輸入框 |
| L201 | `btn btn-outline-secondary` | `btn btn-sm btn-outline btn-neutral` | 測試按鈕 |
| L205 | `text-muted` | `settings-hint` | 狀態文字 |
| L214-224 | `input-group input-group-sm` | `variable-input-group` | Ollama 模型 + 測試按鈕 |
| L215 | `form-select form-select-sm` | `select select-bordered select-sm` | 模型選擇 |
| L218 | `btn btn-outline-secondary` | `btn btn-sm btn-outline btn-neutral` | 測試模型按鈕 |
| L235-240 | `input-group input-group-sm` | `variable-input-group` | Gemini API Key + 測試按鈕 |
| L236 | `form-control` | `input input-bordered input-sm` | API Key 輸入框 |
| L237 | `btn btn-outline-secondary` | `btn btn-sm btn-outline btn-neutral` | 測試按鈕 |
| L242-245 | `form-text text-muted d-block mt-1` | `settings-hint` | Google AI Studio 連結說明 |
| L248 | `alert alert-warning mt-2 py-2` + inline style | `alert alert-warning api-key-alert` | API Key 安全警告（移除 inline style） |
| L265-273 | `input-group input-group-sm` | `variable-input-group` | Gemini 模型 + 測試按鈕 |
| L266 | `form-select form-select-sm` | `select select-bordered select-sm` | 模型選擇 |
| L269 | `btn btn-outline-secondary` | `btn btn-sm btn-outline btn-neutral` | 測試翻譯按鈕 |

#### 進階刮削設定（Collapsible）

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L282-291 | `x-data` + `collapse-toggle` + `data-bs-toggle` | `collapsible-trigger` + `collapsible-title` + `btn-icon-collapse` | 收合區塊觸發器 |
| L291 | `x-show` + `x-collapse` + `id="scraperAdvanced"` | `x-show` + `x-transition` + `collapsible-content` | 收合區塊內容 |
| L294-298 | `form-check form-switch` + `form-check-input` + `form-check-label` | `settings-form-group` + `settings-label` + `toggle` | 建立資料夾 toggle |
| L302 | `d-flex align-items-center gap-1 mb-2` | `folder-layers-row` | 資料夾層容器（外層 / 中層） |
| L303-311 | `input-group input-group-sm` + `x-data` + `dropdown` | `folder-layer-group` + input + `btn-variable-sm` | 外層資料夾 + 變數按鈕 |
| L304 | `form-control` | `input input-bordered input-sm` | 外層輸入框 |
| L306 | `btn btn-outline-secondary dropdown-toggle` | `btn-variable-sm` | 變數按鈕（小型） |
| L308-310 | `dropdown-menu dropdown-menu-end folder-layer-vars show` | `variable-menu`（Alpine.js 控制顯示） | 變數下拉列表 |
| L313-321 | `input-group input-group-sm` + `x-data` | `folder-layer-group` + input + `btn-variable-sm` | 中層資料夾 + 變數按鈕 |
| L324-333 | `input-group input-group-sm` + `x-data` | `folder-layer-group` + `input-group-text` + input + `btn-variable-sm` | 內層資料夾（整行） |
| L325 | `input-group-text` | 保留（搭配 Design System 樣式） | "內層" 前綴文字 |
| L334-339 | `mt-1` + `text-muted` + `file-earmark-play` | `folder-preview` + `preview-text` | 即時預覽路徑 |
| L348-358 | `input-group input-group-sm` + `x-data` + `dropdown` | `variable-input-group` + input + `btn-variable` | 檔案命名格式 + 變數按鈕 |
| L349 | `form-control` | `input input-bordered input-sm` | 命名格式輸入框 |
| L352 | `btn btn-outline-secondary dropdown-toggle` | `btn-variable` | 變數按鈕 |
| L354-357 | `dropdown-menu dropdown-menu-end format-vars show` | `variable-menu`（Alpine.js 控制） | 變數下拉列表 |
| L367-372 | `input-group input-group-sm` | `input-group-inline` | 標題長度限制 + 單位 |
| L368 | `form-control` | `input input-bordered input-sm` | Number input |
| L370 | `input-group-text` | `input-suffix` | 單位後綴（字元） |
| L380-385 | `input-group input-group-sm` | `input-group-inline` | 檔名長度限制 + 單位 |
| L393 | `form-control form-control-sm` | `input input-bordered input-sm` | 影片副檔名輸入框 |
| L395 | `text-muted` | `settings-hint` | 說明文字 |

#### 列表生成設定

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L415-423 | `input-group input-group-sm` | `variable-input-group`（含資料夾按鈕） | 輸出目錄 + 選擇資料夾 |
| L416 | `form-control` | `input input-bordered input-sm` | 輸出目錄輸入框 |
| L418 | `btn btn-outline-secondary` | `btn btn-sm btn-outline btn-neutral` | 選擇資料夾按鈕 |
| L431 | `form-control form-control-sm` | `input input-bordered input-sm` | 輸出檔名輸入框 |
| L438-447 | `x-data` + `collapse-toggle` + `data-bs-toggle` | `collapsible-trigger` + `collapsible-content` | 進階顯示選項收合 |
| L453 | `form-select form-select-sm` | `select select-bordered select-sm` | 預設顯示模式 |
| L466-480 | `input-group input-group-sm` | 雙 select 橫排（不需 input-group） | 預設排序 + 順序 |
| L467, 476 | `form-select` | `select select-bordered select-sm` | 排序 select + 順序 select |
| L489 | `form-select form-select-sm` | `select select-bordered select-sm` | 每頁顯示數量 |
| L505-508 | `input-group input-group-sm` | `input-group-inline` | 最小影片尺寸 + 單位 |
| L506 | `form-control` | `input input-bordered input-sm` | Number input |
| L507 | `input-group-text` | `input-suffix` | 單位後綴（MB） |
| L509 | `text-muted` | `settings-hint` | 說明文字 |

#### 瀏覽與播放

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L528 | `form-control form-control-sm` | `input input-bordered input-sm` | 影片播放器路徑 |
| L530 | `text-muted` | `settings-hint` | 範例說明文字 |

#### 系統設定

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L547 | `form-select form-select-sm` + `x-model="theme"` | `select select-bordered select-sm` + `x-model="theme"` | 主題模式選擇 |
| L558 | `form-select form-select-sm` | `select select-bordered select-sm` | 啟動時開啟頁面 |
| L567-570 | `form-check form-switch` + `form-check-input` + `form-check-label` | `settings-form-group` + `settings-label` + `toggle` | 收合側邊欄 toggle |
| L571 | `text-muted` | `settings-hint` | 說明文字 |
| L584 | `btn btn-outline-danger btn-sm` | `btn btn-sm btn-outline btn-error` | 重置按鈕 |
| L599 | `btn btn-outline-primary btn-sm` | `btn btn-sm btn-outline btn-primary` | 重看新手引導按鈕 |

#### 版本 + 檢查更新

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L614 | `text-muted` | `version-text` | 版本號文字 |
| L624-628 | `d-flex align-items-center gap-2` | `update-check-wrapper` | 檢查更新容器 |
| L625 | `btn btn-outline-secondary btn-sm` | `btn btn-sm btn-outline btn-neutral` | 檢查更新按鈕 |
| L628 | `small` | `settings-hint`（或保留 inline style） | 更新狀態文字 |

#### 儲存按鈕

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L635 | `d-flex justify-content-end gap-2` | `save-btn-wrapper` | 儲存按鈕容器 |
| L636 | `btn btn-primary` | `btn btn-primary save-btn` | 儲存按鈕（加強視覺） |

#### 佈局與間距

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L117 | `container-fluid` | 保留（或改用 Tailwind `max-w-4xl mx-auto px-4`） | 主容器 |
| L124, 404, 518, 537 | `card mb-4` | `settings-card`（或保留 DaisyUI card） | 卡片容器 |
| L125, 405, 519, 538 | `card-header` | 保留（DaisyUI card-header） | 卡片標題 |
| L128, 408, 522, 541 | `card-body` | 保留（DaisyUI card-body） | 卡片內容 |
| L130, 142, 147, ... | `row mb-3` | `settings-form-row`（或保留） | 表單列 |
| L131, 148, 158, ... | `col-md-6` | 移除（改用 `settings-form-row` 自動佈局） | 欄位（6/6 分欄） |
| L281, 419, 437, 575, 590, 606 | `hr class="my-3"` | 保留（或改用 `divider`） | 分隔線 |

**統計**：
- **Toggle switch**：5 處（`.form-check-input` → `.toggle toggle-primary`）
- **Text input**：9 處（`.form-control` → `.input input-bordered input-sm`）
- **Select**：11 處（`.form-select` → `.select select-bordered select-sm`）
- **Button outline**：14 處（`.btn-outline-*` → `.btn-outline btn-*`）
- **Input group**：16 處（`.input-group` → `.variable-input-group` / `.input-group-inline`）
- **說明文字**：13 處（`.text-muted` → `.settings-hint`）
- **Alert**：1 處（`.alert alert-warning` + inline style → `.api-key-alert`）
- **Badge**：1 處（`.bg-danger` → `.badge-error`）
- **佈局**：約 30 處（`.row` + `.col-md-6` → `.settings-form-row` + 子元素）

### 4.2 Inline `<style>` 審計（L6-113）

#### 可刪除的重複定義（與 theme.css 重複）

| 行號 | CSS 規則 | theme.css 位置 | 說明 |
|------|---------|---------------|------|
| L37-43 | `.card { border: none; border-radius: 16px; ... }` | L1311-1710 scope 內無 `.card` 覆寫 | **保留**（settings 自訂樣式，theme.css 無定義） |
| L45-50 | `.card-header { background: transparent; ... }` | 同上 | **保留**（自訂樣式） |
| L52-55 | `.card-header i { color: var(--accent); ... }` | 同上 | **保留**（自訂樣式） |
| L57-59 | `.card-body { padding: 1.25rem; }` | 同上 | **保留**（自訂樣式） |
| L62-65 | `.row.mb-3 .col-md-6:first-child { display: flex; ... }` | **可刪除**（改用 `.settings-form-row`） | 替換後不需要 |
| L67-70 | `.form-label { margin-bottom: 0; ... }` | **可刪除**（改用 `.row-label`） | 替換後不需要 |
| L73-76 | `hr { border-color: var(--border-light); ... }` | **保留**（全域 hr 樣式） | Settings 自訂 |
| L79-84 | `.action-buttons { display: flex; ... }` | **保留**（未在 HTML 中使用，可能是 dead code） | 檢查後可移除 |
| L87-95 | `.collapse-toggle { color: var(--text-secondary); ... }` | L1393-1450（`.collapsible-trigger`） | **可刪除**（theme.css 已定義） |
| L97-99 | `.collapse-toggle i { transition: ... }` | L1443-1450（`.btn-icon-collapse i`） | **可刪除** |
| L101-103 | `.collapse-toggle[aria-expanded="true"] i { ... }` | L1448-1450（`.rotate-180`） | **可刪除** |
| L106-108 | `.collapse-toggle i { transition: ... }` | 重複定義（與 L97-99 相同） | **可刪除** |
| L110-112 | `.rotate-180 { transform: rotate(180deg) !important; }` | L1448-1450（`.rotate-180`） | **可刪除**（theme.css 已定義） |

**保留的樣式**：
- L7-25：`.settings-container`, `.spin`, `@keyframes spin` — **保留**（頁面容器 + 檢查更新動畫）
- L27-34：`.settings-header` — **保留**（可能用於標題區，雖然 HTML 中無此 class）
- L37-59：`.card`, `.card-header`, `.card-body` — **保留**（Settings 自訂卡片樣式）
- L73-76：`hr` — **保留**（全域 hr 樣式）

**移除的樣式**（約 20 行）：
- L62-70：`.row.mb-3 .col-md-6`, `.form-label` — 改用 `.settings-form-row` 後不需要
- L79-84：`.action-buttons` — 未使用（dead code）
- L87-112：`.collapse-toggle` 及相關 — theme.css 已定義 `.collapsible-trigger`

#### 需保留的 Alpine.js 動畫樣式

**無**（Alpine.js `x-transition` 使用內建動畫，無需自訂 CSS）

### 4.3 Inline JS Bootstrap Class 審計（Opus 審核追加）

> **⚠️ Critical**：settings.html 的 inline `<script>`（L645-1393）包含大量動態生成的 HTML，其中使用了 Bootstrap class。這些**必須**在 M4a 一併替換。

#### 4.3.1 `spinner-border` → `loading loading-spinner`（4 處）

| 行號 | 上下文 | Bootstrap Class | 替換為 |
|------|--------|----------------|--------|
| L1063 | `testGeminiConnection()` — Gemini 測試按鈕 | `spinner-border spinner-border-sm` | `loading loading-spinner loading-sm` |
| L1153 | `testGeminiTranslation()` — Gemini 翻譯測試按鈕 | `spinner-border spinner-border-sm` | `loading loading-spinner loading-sm` |
| L1258 | `testOllamaConnection()` — Ollama 連線按鈕 | `spinner-border spinner-border-sm` | `loading loading-spinner loading-sm` |
| L1304 | `testModel()` — Ollama 模型測試按鈕 | `spinner-border spinner-border-sm` | `loading loading-spinner loading-sm` |

#### 4.3.2 `text-danger` → `text-error`（~15 處）

| 行號 | 上下文 | 說明 |
|------|--------|------|
| L1057 | `testGeminiConnection()` | 「請輸入 API Key」錯誤 |
| L1088 | `testGeminiConnection()` | API 連接失敗 |
| L1097 | `testGeminiConnection()` | catch 錯誤 |
| L1142 | `testGeminiTranslation()` | 「請先輸入 API Key」錯誤 |
| L1147 | `testGeminiTranslation()` | 「請先選擇模型」錯誤 |
| L1173 | `testGeminiTranslation()` | 翻譯失敗 |
| L1177 | `testGeminiTranslation()` | catch 錯誤 |
| L1252 | `testOllamaConnection()` | 「請輸入 URL」錯誤 |
| L1279 | `testOllamaConnection()` | 連線失敗 |
| L1283 | `testOllamaConnection()` | catch 錯誤 |
| L1299 | `testModel()` | 「請先選擇模型」錯誤 |
| L1319 | `testModel()` | 測試失敗 |
| L1322 | `testModel()` | catch 錯誤 |
| L1402 | `btnCheckUpdate` | 檢查失敗 |
| L1405 | `btnCheckUpdate` | 網路錯誤 |

#### 4.3.3 Dropdown 動態 HTML 遷移

**format-vars dropdown（L658-679）**：

修改前：
```javascript
li.innerHTML = `<a class="dropdown-item" href="#" data-var="${v.name}">
    <code>${v.name}</code> - ${v.description}
    <small class="text-muted d-block">${v.example}</small>
</a>`;
```

修改後（Design System `.variable-item`）：
```javascript
const div = document.createElement('div');
div.className = 'variable-item';
div.dataset.var = v.name;
div.innerHTML = `
    <code class="variable-name">${v.name}</code>
    <span class="variable-desc">${v.description}</span>
    <small class="variable-example">${v.example}</small>
`;
```

**folder-layer-vars dropdown（L778-784）**：

修改前：
```javascript
menu.innerHTML = `
    <li><a class="dropdown-item" href="#" data-var="{num}">{num}</a></li>
    <li><a class="dropdown-item" href="#" data-var="{actor}">{actor}</a></li>
    ...
`;
```

修改後（Design System `.variable-item`）：
```javascript
menu.innerHTML = `
    <div class="variable-item" data-var="{num}"><code class="variable-name">{num}</code></div>
    <div class="variable-item" data-var="{actor}"><code class="variable-name">{actor}</code></div>
    ...
`;
```

**注意**：click handler 需從 `e.target.closest('[data-var]')` 改為 `e.target.closest('.variable-item')` 或保持 `[data-var]`（保持即可）。

#### 4.3.4 HTML 靜態 Dropdown Class（L309, L319, L331, L355）

| 行號 | Bootstrap Class | 替換為 | 說明 |
|------|----------------|--------|------|
| L309 | `dropdown-menu dropdown-menu-end folder-layer-vars show` | `variable-menu`（Alpine.js `x-show` 控制） | 外層變數下拉 |
| L319 | `dropdown-menu dropdown-menu-end folder-layer-vars show` | `variable-menu` | 中層變數下拉 |
| L331 | `dropdown-menu dropdown-menu-end folder-layer-vars show` | `variable-menu` | 內層變數下拉 |
| L355 | `dropdown-menu dropdown-menu-end format-vars show` | `variable-menu` | 檔案命名格式變數下拉 |

**JS selector 更新**：
- L658: `document.querySelectorAll('.format-vars')` → `.variable-menu[data-type="format"]`（或加 `data-type` 屬性區分）
- L778: `document.querySelectorAll('.folder-layer-vars')` → `.variable-menu[data-type="folder"]`

**統計**：
- `spinner-border spinner-border-sm` → `loading loading-spinner loading-sm`（4 處）
- `text-danger` → `text-error`（~15 處）
- `dropdown-item` → `variable-item`（~8 處 JS 生成）
- `dropdown-menu` → `variable-menu`（4 處 HTML + 2 處 JS selector）
- `text-muted d-block` → `variable-example`（1 處）

---

### 4.4 Design System 元件對齊

對比 `design_system/settings-components.html`（已讀），需要套用的 semantic class：

| Design System Class | 用途 | 對應 HTML 區域 |
|---------------------|------|---------------|
| `.settings-form-group` | Toggle switch 容器 | L132-138, L144-150, L168-175, L294-298, L567-570 |
| `.settings-label` | Toggle switch 的 label | L135, L147, L172, L297, L569 |
| `.label-text` | Toggle switch 的文字 | L136, L148, L172, L297, L569（加上 `<span>`） |
| `.settings-hint` | 說明文字（灰色小字） | L151, L164, L205, L242, L395, L509, L530, L571 |
| `.settings-form-row` | Label + 控制項橫向佈局 | L156-166, L179-189, ... |
| `.row-label` | 左側 label | L158, L181, L195, ... |
| `.input-group-inline` | Number input + 單位後綴 | L367-372, L380-385, L505-508 |
| `.input-suffix` | 單位後綴（字元、MB） | L370, L383, L507 |
| `.collapsible-trigger` | 收合區塊觸發器（卡片式） | L283-290, L439-446 |
| `.collapsible-title` | 收合區塊標題 | L288, L444 |
| `.btn-icon-collapse` | 收合箭頭按鈕 | L289, L445（搭配 `:class="{ 'rotate-180': expanded }"`） |
| `.collapsible-content` | 收合區塊內容 | L291, L447 |
| `.variable-input-group` | 變數插入 input + 按鈕 | L348-358, L198-205（Ollama URL 也可用） |
| `.btn-variable` | 變數按鈕 | L352 |
| `.btn-variable-sm` | 小型變數按鈕（資料夾層） | L306, L316, L328 |
| `.variable-menu` | 變數下拉列表容器 | L308-310, L318-320, L330-332, L354-357（Alpine.js 控制顯示） |
| `.variable-item` | 變數列表項目 | JS 動態生成（L658-666） |
| `.variable-name`, `.variable-desc`, `.variable-example` | 變數項目內容 | JS 動態生成 |
| `.folder-layers-row` | 資料夾多層容器 | L302, L324 |
| `.folder-layer-group` | 單層資料夾 + 變數按鈕 | L303-311, L313-321, L324-333 |
| `.folder-layer-group.disabled` | 禁用狀態（外層/中層） | L303, L313（初始） |
| `.folder-separator` | 資料夾層分隔符（/） | L312 |
| `.folder-preview` | 即時預覽路徑容器 | L334-339 |
| `.preview-text` | 預覽路徑文字 | L337 |
| `.api-key-alert` | API Key 警告 Alert | L248 |
| `.alert-content`, `.alert-list`, `.alert-link` | Alert 內容結構 | L249-256 |
| `.version-text` | 版本號文字 | L614 |
| `.update-check-wrapper` | 檢查更新容器 | L624-628 |
| `.save-btn-wrapper` | 儲存按鈕容器 | L635 |
| `.save-btn` | 儲存按鈕（強化樣式） | L636 |

**Design System 新增的語義 class**（theme.css L1308-1710 已定義）：
- 相較於 Search/Scanner，Settings 引入了 **14 個新的 semantic class**
- 這些 class 封裝了 Fluent Design 規範（間距、顏色、陰影、動畫）
- **優勢**：HTML 更語義化，樣式統一，維護性高

## DaisyUI 替換方案

### 1. 核心替換規則

#### 1.1 Toggle Switch（最常用）

**Bootstrap**：
```html
<div class="form-check form-switch">
    <input class="form-check-input" type="checkbox" id="galleryModeEnabled">
    <label class="form-check-label" for="galleryModeEnabled">
        女優畫廊模式 <span class="badge bg-danger">Beta</span>
    </label>
</div>
```

**DaisyUI + Design System**：
```html
<div class="settings-form-group">
    <label class="settings-label">
        <input type="checkbox" class="toggle toggle-primary" id="galleryModeEnabled">
        <span class="label-text">女優畫廊模式 <span class="badge badge-error badge-sm">Beta</span></span>
    </label>
</div>
```

**變更點**：
- `.form-check form-switch` → `.settings-form-group`（Design System 容器）
- `.form-check-input` → `.toggle toggle-primary`（DaisyUI toggle）
- `.form-check-label` → `.settings-label`（Design System label，包含 input + text）
- **label 文字需包在 `<span class="label-text">` 內**（Design System 規範）
- `.badge bg-danger` → `.badge badge-error badge-sm`

#### 1.2 Toggle Switch + 說明文字

**Bootstrap**：
```html
<div class="form-check form-switch">
    <input class="form-check-input" type="checkbox" id="uncensoredModeEnabled">
    <label class="form-check-label" for="uncensoredModeEnabled">無碼模式</label>
</div>
<small class="text-muted">啟用時只搜尋 AVSOX / FC2，適合無碼作品</small>
```

**DaisyUI + Design System**：
```html
<div class="settings-form-group">
    <label class="settings-label">
        <input type="checkbox" class="toggle toggle-primary" id="uncensoredModeEnabled">
        <span class="label-text">無碼模式</span>
    </label>
    <small class="settings-hint">啟用時只搜尋 AVSOX / FC2，適合無碼作品</small>
</div>
```

**變更點**：
- `.text-muted` → `.settings-hint`（Design System 說明文字，自動縮排對齊）
- 說明文字移到 `.settings-form-group` 內部（作為第二個子元素）

#### 1.3 Text Input（橫向佈局）

**Bootstrap**：
```html
<div class="row mb-3">
    <div class="col-md-6">
        <label class="form-label">我的最愛資料夾</label>
        <small class="text-muted d-block">一鍵載入常用資料夾</small>
    </div>
    <div class="col-md-6">
        <input type="text" class="form-control form-control-sm" id="searchFavoriteFolder" placeholder="留空 = 系統下載資料夾">
        <small class="text-muted">範例：C:\Users\...</small>
    </div>
</div>
```

**DaisyUI + Design System**：
```html
<div class="settings-form-row">
    <label class="row-label">
        我的最愛資料夾
        <small class="settings-hint">一鍵載入常用資料夾</small>
    </label>
    <div style="flex: 1; display: flex; flex-direction: column; gap: 4px;">
        <input type="text" class="input input-bordered input-sm" id="searchFavoriteFolder" placeholder="留空 = 系統下載資料夾">
        <small class="settings-hint">範例：C:\Users\...</small>
    </div>
</div>
```

**變更點**：
- `.row mb-3` → `.settings-form-row`（Design System 橫向佈局，flex 容器）
- `.col-md-6` → 移除（改用 `.row-label` + `flex: 1` 子元素）
- `.form-label` → `.row-label`（左側 label，min-width: 140px）
- `.form-control form-control-sm` → `.input input-bordered input-sm`
- `.text-muted d-block` → `.settings-hint`（移到 label 內作為第二行）
- 右側控制項包在 `<div style="flex: 1;">` 內（自動填充剩餘空間）

#### 1.4 Select 下拉選單

**Bootstrap**：
```html
<div class="row mb-3">
    <div class="col-md-6">
        <label class="form-label">主題模式</label>
    </div>
    <div class="col-md-6">
        <select class="form-select form-select-sm" id="themeMode">
            <option value="light">淺色模式 (Light)</option>
            <option value="dim">深色模式 (Dim)</option>
        </select>
    </div>
</div>
```

**DaisyUI + Design System**：
```html
<div class="settings-form-row">
    <label class="row-label">主題模式</label>
    <select class="select select-bordered select-sm" id="themeMode">
        <option value="light">淺色模式 (Light)</option>
        <option value="dim">深色模式 (Dim)</option>
    </select>
</div>
```

**變更點**：
- `.row mb-3` + `.col-md-6` → `.settings-form-row`（自動橫向佈局）
- `.form-select form-select-sm` → `.select select-bordered select-sm`
- Label 直接放在 row 內（不需包 div）

#### 1.5 Number Input + 單位後綴

**Bootstrap**：
```html
<div class="row mb-3">
    <div class="col-md-6">
        <label class="form-label">標題長度限制</label>
    </div>
    <div class="col-md-6">
        <div class="input-group input-group-sm">
            <input type="number" class="form-control" id="maxTitleLength" value="80" min="20" max="200">
            <span class="input-group-text">字元</span>
        </div>
    </div>
</div>
```

**DaisyUI + Design System**：
```html
<div class="settings-form-row">
    <label class="row-label">標題長度限制</label>
    <div class="input-group-inline">
        <input type="number" class="input input-bordered input-sm" id="maxTitleLength" value="80" min="20" max="200">
        <span class="input-suffix">字元</span>
    </div>
</div>
```

**變更點**：
- `.input-group input-group-sm` → `.input-group-inline`（Design System 語義 class）
- `.form-control` → `.input input-bordered input-sm`
- `.input-group-text` → `.input-suffix`（Design System 單位後綴）

#### 1.6 收合區塊（Collapsible）

**Bootstrap（舊版 v0.2.3）**：
```html
<div class="mb-2">
    <a class="collapse-toggle text-decoration-none" data-bs-toggle="collapse" href="#scraperAdvanced" role="button" aria-expanded="false">
        <i class="bi bi-chevron-down"></i> 進階刮削設定
    </a>
</div>
<div class="collapse" id="scraperAdvanced">
    <!-- 進階設定內容 -->
</div>
```

**Alpine.js（新版 v0.3.0 + Design System）**：
```html
<div x-data="{ expanded: false }">
    <button class="collapsible-trigger" type="button" @click="expanded = !expanded" :aria-expanded="expanded.toString()">
        <span class="collapsible-title">
            <i class="bi bi-gear"></i> 進階刮削設定
        </span>
        <span class="btn-icon-collapse" aria-hidden="true">
            <i class="bi bi-chevron-down" :class="{ 'rotate-180': expanded }"></i>
        </span>
    </button>
    <div x-show="expanded" x-transition class="collapsible-content">
        <!-- 進階設定內容 -->
    </div>
</div>
```

**變更點**：
- `<a data-bs-toggle="collapse">` → `<button class="collapsible-trigger">`（卡片式按鈕，theme.css L1393-1406）
- `.collapse-toggle` → `.collapsible-trigger` + `.collapsible-title` + `.btn-icon-collapse`
- `href="#scraperAdvanced"` → `x-data` + `@click="expanded = !expanded"`
- `.collapse` → `x-show="expanded" x-transition`（Alpine.js 內建動畫）
- **箭頭旋轉**：`:class="{ 'rotate-180': expanded }`（Alpine.js 動態 class）

#### 1.7 變數插入 Dropdown

**Bootstrap（舊版）**：
```html
<div class="input-group input-group-sm">
    <input type="text" class="form-control" id="filenameFormat" value="[{num}][{maker}] {title}">
    <button class="btn btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">變數</button>
    <ul class="dropdown-menu dropdown-menu-end format-vars" data-target="filenameFormat"></ul>
</div>
```

**Alpine.js + Design System**：
```html
<div class="variable-input-group" x-data="{ open: false }">
    <input type="text" class="input input-bordered input-sm" id="filenameFormat" value="[{num}][{maker}] {title}" style="flex: 1;">
    <button class="btn-variable" type="button" @click="open = !open">
        <i class="bi bi-braces"></i> 變數
    </button>
    <ul x-show="open" @click.outside="open = false" x-transition class="variable-menu" data-target="filenameFormat" style="display: none;"></ul>
</div>
```

**變更點**：
- `.input-group input-group-sm` → `.variable-input-group`（Design System 語義 class）
- `.form-control` → `.input input-bordered input-sm`
- `.btn btn-outline-secondary dropdown-toggle` → `.btn-variable`（Design System 強調按鈕，theme.css L1468-1492）
- `data-bs-toggle="dropdown"` → `x-data="{ open: false }"` + `@click="open = !open"`
- `.dropdown-menu` → `.variable-menu`（theme.css L1499-1543 定義樣式）
- **關鍵**：加上 `<i class="bi bi-braces"></i>` icon（Design System 規範）

#### 1.8 API Key 警告 Alert

**Bootstrap（含 inline style）**：
```html
<div class="alert alert-warning mt-2 py-2" role="alert" style="font-size: 0.8rem;">
    <strong>⚠️ 安全提示：</strong>
    <ul class="mb-0 ps-3">
        <li>API Key 將以明文存儲在 config.json</li>
        <li>請勿將 config.json 分享給他人</li>
        <li>如需撤銷，請前往 <a href="..." target="_blank">Google AI Studio</a> 重新生成</li>
    </ul>
</div>
```

**DaisyUI + Design System**：
```html
<div class="alert alert-warning api-key-alert">
    <i class="bi bi-exclamation-triangle-fill"></i>
    <div class="alert-content">
        <strong>安全提示：</strong>
        <ul class="alert-list">
            <li>API Key 將以明文存儲在 config.json</li>
            <li>請勿將 config.json 分享給他人</li>
            <li>如需撤銷，請前往 <a href="..." target="_blank" class="alert-link">Google AI Studio</a> 重新生成</li>
        </ul>
    </div>
</div>
```

**變更點**：
- `.alert alert-warning mt-2 py-2` + inline `style` → `.alert alert-warning api-key-alert`（Design System class，theme.css L1627-1671）
- **移除 inline style**（`font-size: 0.8rem;` 已在 L1629 定義）
- 加入 `<i class="bi bi-exclamation-triangle-fill"></i>`（Design System 圖標）
- 內容包在 `<div class="alert-content">` 內
- `.mb-0 ps-3` → `.alert-list`（Design System 語義 class）
- `<a>` 加上 `.alert-link`（Design System 連結樣式）

#### 1.9 版本 + 檢查更新

**Bootstrap**：
```html
<div class="row mb-3">
    <div class="col-md-6">
        <label class="form-label">版本資訊</label>
    </div>
    <div class="col-md-6">
        <span id="appVersion" class="text-muted">載入中...</span>
    </div>
</div>

<div class="row">
    <div class="col-md-6">
        <label class="form-label">軟體更新</label>
        <div class="form-text">手動檢查 GitHub 是否有新版本</div>
    </div>
    <div class="col-md-6 d-flex align-items-center gap-2">
        <button type="button" class="btn btn-outline-secondary btn-sm" id="btnCheckUpdate">
            <i class="bi bi-cloud-download"></i> 檢查更新
        </button>
        <span id="updateStatus" class="small"></span>
    </div>
</div>
```

**DaisyUI + Design System**：
```html
<div class="settings-form-row">
    <label class="row-label">版本資訊</label>
    <span id="appVersion" class="version-text">載入中...</span>
</div>

<div class="settings-form-row">
    <label class="row-label">
        軟體更新
        <small class="settings-hint">手動檢查 GitHub 是否有新版本</small>
    </label>
    <div class="update-check-wrapper">
        <button type="button" class="btn btn-sm btn-outline btn-neutral" id="btnCheckUpdate">
            <i class="bi bi-cloud-download"></i> 檢查更新
        </button>
        <span id="updateStatus" class="small"></span>
    </div>
</div>
```

**變更點**：
- `.text-muted` → `.version-text`（Design System 版本號樣式，theme.css L1674-1679）
- `.form-text` → `.settings-hint`（移到 label 內）
- `.d-flex align-items-center gap-2` → `.update-check-wrapper`（Design System 容器）
- `.btn btn-outline-secondary btn-sm` → `.btn btn-sm btn-outline btn-neutral`

#### 1.10 儲存按鈕

**Bootstrap**：
```html
<div class="d-flex justify-content-end gap-2">
    <button type="submit" class="btn btn-primary" id="saveBtn">
        <i class="bi bi-save"></i> 儲存設定
    </button>
</div>
```

**DaisyUI + Design System**：
```html
<div class="save-btn-wrapper">
    <button type="submit" class="btn btn-primary save-btn" id="saveBtn">
        <i class="bi bi-save"></i> 儲存設定
    </button>
</div>
```

**變更點**：
- `.d-flex justify-content-end gap-2` → `.save-btn-wrapper`（Design System 容器，theme.css L1689-1692）
- `.btn btn-primary` → `.btn btn-primary save-btn`（加強樣式，theme.css L1695-1709，hover 時 glow + translateY）

### 2. 按鈕樣式統一規則

#### 2.1 Outline 按鈕順序

**Bootstrap**：
```html
<button class="btn btn-outline-secondary btn-sm">測試</button>
<button class="btn btn-outline-primary btn-sm">加入</button>
<button class="btn btn-outline-danger btn-sm">重置</button>
```

**DaisyUI**：
```html
<button class="btn btn-sm btn-outline btn-neutral">測試</button>
<button class="btn btn-sm btn-outline btn-primary">加入</button>
<button class="btn btn-sm btn-outline btn-error">重置</button>
```

**順序規則**：`btn` → **size** → `btn-outline` → **color**

#### 2.2 顏色對照

| Bootstrap | DaisyUI | 說明 |
|-----------|---------|------|
| `btn-outline-primary` | `btn-outline btn-primary` | 主要動作（藍色） |
| `btn-outline-secondary` | `btn-outline btn-neutral` | 次要動作（灰色） |
| `btn-outline-warning` | `btn-outline btn-warning` | 警告（橘色） |
| `btn-outline-danger` | `btn-outline btn-error` | 危險動作（紅色） |
| `btn-outline-success` | `btn-outline btn-success` | 成功（綠色） |

### 3. Badge 替換

| Bootstrap | DaisyUI | 說明 |
|-----------|---------|------|
| `badge bg-danger` | `badge badge-error badge-sm` | 錯誤 badge（小尺寸） |

## `#settings-components` Scope 啟用

### 1. 加入 Scope Wrapper

在 `settings.html` 的主容器加上 `id="settings-components"`：

**修改前（L117）**：
```html
<div class="container-fluid">
    <h4 class="mb-4">
        <i class="bi bi-gear"></i> 設定
    </h4>
```

**修改後**：
```html
<div id="settings-components" class="container-fluid">
    <h4 class="mb-4">
        <i class="bi bi-gear"></i> 設定
    </h4>
```

### 2. Scope 生效的元件

加上 `#settings-components` 後，theme.css L1308-1710 的所有 Settings 元件自動生效：

- `.settings-form-group`（toggle 容器）
- `.settings-label`（toggle label）
- `.settings-hint`（說明文字，自動縮排）
- `.settings-form-row`（橫向佈局）
- `.row-label`（左側 label）
- `.input-group-inline`（number input + 單位）
- `.input-suffix`（單位後綴）
- `.collapsible-trigger`（收合觸發器，卡片樣式）
- `.collapsible-title`（收合標題）
- `.btn-icon-collapse`（箭頭按鈕）
- `.collapsible-content`（收合內容）
- `.variable-input-group`（變數插入容器）
- `.btn-variable`（變數按鈕，強調樣式）
- `.btn-variable-sm`（小型變數按鈕）
- `.variable-menu`（變數下拉列表）
- `.variable-item`, `.variable-name`, `.variable-desc`, `.variable-example`（變數列表項目）
- `.folder-layers-row`（資料夾多層容器）
- `.folder-layer-group`（單層資料夾）
- `.folder-layer-group.disabled`（禁用狀態）
- `.folder-separator`（分隔符）
- `.folder-preview`（預覽容器）
- `.preview-text`（預覽文字）
- `.api-key-alert`（API Key 警告）
- `.alert-content`, `.alert-list`, `.alert-link`（Alert 內容）
- `.version-text`（版本號）
- `.update-check-wrapper`（檢查更新容器）
- `.save-btn-wrapper`（儲存按鈕容器）
- `.save-btn`（儲存按鈕強化）

## 技術要點

### 1. DaisyUI Toggle vs Bootstrap Switch

#### 1.1 HTML 結構差異

**Bootstrap**：
```html
<div class="form-check form-switch">
    <input class="form-check-input" type="checkbox" id="myToggle">
    <label class="form-check-label" for="myToggle">Label 在右側</label>
</div>
```

**DaisyUI**：
```html
<label class="settings-label">
    <input type="checkbox" class="toggle toggle-primary" id="myToggle">
    <span class="label-text">Label 在右側</span>
</label>
```

**差異**：
- Bootstrap：`<input>` + `<label>` 為兄弟元素，用 `for` 屬性關聯
- DaisyUI：`<label>` 包住 `<input>` + text，無需 `for` 屬性

#### 1.2 Settings 語義 class 的必要性

**為什麼不直接用 DaisyUI `.form-control`？**
- DaisyUI `.form-control` 是**垂直佈局**（label 在上，input 在下）
- Settings 需要**橫向佈局**（label 在左，toggle 在右）
- Design System 的 `.settings-label` 改為 `flex-direction: row`（theme.css L1320-1324）

**為什麼要 `<span class="label-text">`？**
- DaisyUI toggle 預設與 label 文字「垂直置中對齊」
- 加上 `.label-text` 後可以精確控制文字樣式（字重、顏色、間距）
- 支援 Badge 等內嵌元件（如 `<span class="badge badge-error">Beta</span>`）

### 2. `.settings-hint` 的自動縮排

#### 2.1 Toggle 區塊的縮排

**CSS 規則**（theme.css L1343-1345）：
```css
#settings-components .settings-form-group .settings-hint {
    margin-left: 48px; /* toggle 寬度 (36px) + gap (12px) */
}
```

**效果**：
```
[Toggle] 啟用標題翻譯
         ↑ 說明文字自動對齊 label text
```

#### 2.2 Form Row 的說明文字不縮排

**CSS 規則**（theme.css L1336-1340）：
```css
#settings-components .settings-hint {
    font-size: 0.8rem;
    color: var(--text-muted);
    line-height: 1.4;
    /* 無 margin-left，保持左對齊 */
}
```

**效果**：
```
Label          [Input]
               範例：C:\Users\...
```

### 3. 收合區塊的卡片式設計

#### 3.1 為什麼從 `<a>` 改為 `<button>`？

**Bootstrap Collapse**：
```html
<a class="collapse-toggle" data-bs-toggle="collapse" href="#scraperAdvanced">
    <i class="bi bi-chevron-down"></i> 進階刮削設定
</a>
```

**Design System**：
```html
<button class="collapsible-trigger" type="button" @click="expanded = !expanded">
    <span class="collapsible-title">
        <i class="bi bi-gear"></i> 進階刮削設定
    </span>
    <span class="btn-icon-collapse">
        <i class="bi bi-chevron-down" :class="{ 'rotate-180': expanded }"></i>
    </span>
</button>
```

**理由**：
- **語義正確**：觸發器是「按鈕」，不是「連結」
- **無障礙性**：screen reader 會正確識別為 `button[role="button"]`
- **樣式控制**：button 可以用 `:hover`、`:active` 狀態，`<a>` 需要額外 class
- **卡片設計**：Design System 的 `.collapsible-trigger` 是卡片式按鈕（背景、邊框、陰影），`<a>` 無法實現

#### 3.2 Alpine.js 動畫

**Bootstrap Collapse**：
```html
<div class="collapse" id="scraperAdvanced">...</div>
```
- 使用 Bootstrap JS `Collapse.toggle()` 控制展開/收合
- 動畫效果：`height` transition

**Alpine.js**：
```html
<div x-show="expanded" x-transition class="collapsible-content">...</div>
```
- `x-show="expanded"`：控制顯示/隱藏
- `x-transition`：內建動畫（opacity + transform），無需自訂 CSS
- **優勢**：無需引入 Bootstrap JS（減少依賴）

### 4. 變數插入 Dropdown 的樣式升級

#### 4.1 按鈕視覺強化

**Bootstrap**：
```html
<button class="btn btn-outline-secondary dropdown-toggle">變數</button>
```
- 灰色邊框，hover 時填充灰色背景
- 無 icon，只有文字 + dropdown 箭頭

**Design System**：
```html
<button class="btn-variable">
    <i class="bi bi-braces"></i> 變數
</button>
```
- **強調色邊框**（`border: 1px solid var(--accent)`），主題色背景（10% opacity）
- **Braces icon**（`{}`），更直觀表示「變數」
- **Hover glow**（`box-shadow: 0 0 0 2px var(--glow-subtle)`，theme.css L1484-1487）

#### 4.2 Dropdown 列表的結構

**Bootstrap**：
```html
<ul class="dropdown-menu">
    <li><a class="dropdown-item" href="#" data-var="{num}">
        <code>{num}</code> - 番號
        <small class="text-muted d-block">SONE-205</small>
    </a></li>
</ul>
```

**Design System**：
```html
<div class="variable-menu">
    <div class="variable-item">
        <code class="variable-name">{num}</code>
        <span class="variable-desc">番號</span>
        <small class="variable-example">例：SONE-205</small>
    </div>
</div>
```

**差異**：
- `<ul> + <li> + <a>` → `<div> + <div>`（更語義化，避免 list-style 干擾）
- `.dropdown-item` → `.variable-item`（垂直排列 name + desc + example）
- 三個語義 class：`.variable-name`（code 背景）、`.variable-desc`（主文字）、`.variable-example`（灰色小字）

### 5. 資料夾多層連動的 JS 邏輯

#### 5.1 連動規則（右→左）

**規則**：內層 → 中層 → 外層（由內向外逐層啟用）

```javascript
function updateFolderLayers() {
    const createFolder = document.getElementById('createFolder').checked;
    const layer3Input = document.getElementById('folderLayer3');  // 內層
    const layer2Input = document.getElementById('folderLayer2');  // 中層
    const layer1Input = document.getElementById('folderLayer1');  // 外層

    // 如果「建立資料夾」未勾選，全部 disabled
    if (!createFolder) {
        layer3Input.disabled = true;
        layer2Input.disabled = true;
        layer1Input.disabled = true;
        return;
    }

    // 「建立資料夾」已勾選，啟用內層
    layer3Input.disabled = false;

    // 連動啟用
    const layer3HasValue = !!layer3Input.value.trim();
    const layer2HasValue = !!layer2Input.value.trim();

    layer2Input.disabled = !layer3HasValue;  // 內層有值才啟用中層
    layer1Input.disabled = !layer2HasValue;  // 中層有值才啟用外層

    // 禁用時清空
    if (layer2Input.disabled) layer2Input.value = '';
    if (layer1Input.disabled) layer1Input.value = '';
}
```

**HTML 配合**：
```html
<div class="folder-layer-group" :class="{ 'disabled': !layer3HasValue }">
    <input type="text" class="input input-bordered input-sm" id="folderLayer2" :disabled="!layer3HasValue">
    <button class="btn-variable-sm" :disabled="!layer3HasValue">...</button>
</div>
```

**視覺效果**：
- 禁用狀態：`.folder-layer-group.disabled { opacity: 0.5; }`（theme.css L1558-1560）
- 輸入框灰化：`:disabled` 狀態
- 按鈕無法點擊：`:disabled` 狀態

### 6. API Key Alert 的無障礙性

#### 6.1 ARIA 屬性

**Bootstrap**：
```html
<div class="alert alert-warning" role="alert">
    <strong>⚠️ 安全提示：</strong>
    ...
</div>
```

**Design System（保留）**：
```html
<div class="alert alert-warning api-key-alert" role="alert">
    <i class="bi bi-exclamation-triangle-fill"></i>
    <div class="alert-content">
        <strong>安全提示：</strong>
        ...
    </div>
</div>
```

**改進**：
- `role="alert"`：保留（screen reader 會朗讀為「警告」）
- **Emoji 改 Icon**：`⚠️` → `<i class="bi bi-exclamation-triangle-fill">`（更清晰，支援主題色）
- **結構語義**：`.alert-content` + `.alert-list` + `.alert-link`（更易於樣式控制）

### 7. 版本文字的 Monospace Font

**CSS 規則**（theme.css L1674-1679）：
```css
#settings-components .version-text {
    font-size: 0.875rem;
    color: var(--accent);
    font-weight: 600;
    font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
}
```

**效果**：
```
版本資訊    v0.3.0  ← Monospace font，數字對齊更整齊
```

### 8. 儲存按鈕的 Hover 動畫

**CSS 規則**（theme.css L1702-1705）：
```css
#settings-components .save-btn:hover {
    box-shadow: 0 0 0 4px var(--glow-subtle);  /* 4px glow */
    transform: translateY(-1px);  /* 上浮 1px */
}
```

**效果**：
- Hover 時按鈕「浮起來」（微動畫）
- 周圍出現主題色 glow（強調 CTA）

## 驗證方式

### 1. Grep 檢查（Bootstrap Class 殘留）

#### 1.1 HTML 模板檢查

```bash
# 檢查 settings.html 中的 Bootstrap class
grep -n "form-check\|form-control\|form-select\|btn-outline-primary\|btn-outline-secondary\|btn-outline-danger\|text-muted\|d-block\|row mb-3\|col-md-6\|input-group\|badge bg-danger\|d-flex\|justify-content-end" web/templates/settings.html

# 預期：零結果（全部替換完成）
```

#### 1.2 Inline `<style>` 檢查

```bash
# 檢查 inline style 中的 Bootstrap 選擇器
grep -n "\.form-check\|\.form-control\|\.form-select\|\.row\.mb-3\|\.col-md-6\|\.collapse-toggle" web/templates/settings.html

# 預期：零結果（重複定義已移除）
```

#### 1.3b Inline JS 檢查（Opus 審核追加）

```bash
# 檢查 inline JS 中的 Bootstrap class
grep -n "spinner-border\|text-danger\|dropdown-item\|dropdown-menu\|folder-layer-vars\|format-vars" web/templates/settings.html

# 預期：零結果（全部替換為 DaisyUI / Design System class）
```

#### 1.3 Scope ID 檢查

```bash
# 檢查是否有 id="settings-components"
grep -n 'id="settings-components"' web/templates/settings.html

# 預期：1 個結果（L117 或附近）
```

### 2. Pytest（API 測試）

```bash
# Settings 功能相關的 API 測試（config 讀寫）
source venv/bin/activate && pytest tests/integration/test_api_config.py -v

# 預期：全部通過（M4a 只改 HTML，不改 API）
```

### 3. 手動 UI 驗證（Checklist）

#### 3.1 Toggle Switch

- [ ] **女優畫廊模式**：toggle 顯示正常，Beta badge 為紅色
- [ ] **無碼模式**：toggle 下方說明文字左對齊（縮排 48px）
- [ ] **啟用標題翻譯**：toggle 正常，點擊時下方「翻譯選項」顯示/隱藏
- [ ] **建立資料夾**：toggle 正常，關閉時資料夾層輸入框禁用
- [ ] **收合側邊欄**：toggle 下方說明文字對齊

#### 3.2 Text Input

- [ ] **我的最愛資料夾**：輸入框正常，placeholder 顯示，說明文字在下方
- [ ] **Ollama URL**：輸入框正常，「測試」按鈕在右側
- [ ] **Gemini API Key**：密碼輸入框正常（type="password"），測試按鈕在右側

#### 3.3 Select 下拉選單

- [ ] **翻譯服務**：select 顯示正常，選項切換時 Ollama/Gemini 欄位顯示/隱藏
- [ ] **主題模式**：select 顯示正常，選擇「深色模式」時主題切換（Alpine.js `x-model`）
- [ ] **啟動時開啟頁面**：select 顯示正常

#### 3.4 Number Input + 單位

- [ ] **標題長度限制**：number input 正常，右側「字元」單位顯示
- [ ] **檔名長度限制**：number input 正常，右側「字元」單位顯示
- [ ] **最小影片尺寸**：number input 正常，右側「MB」單位顯示，下方說明文字顯示

#### 3.5 收合區塊

- [ ] **進階刮削設定**：
  - 收合觸發器為「卡片式按鈕」（背景、邊框、圓角）
  - 點擊時箭頭旋轉 180 度（Alpine.js `:class="{ 'rotate-180': expanded }"`）
  - 內容區塊展開時有動畫（`x-transition`）
  - Hover 時觸發器背景變深
- [ ] **進階顯示選項**：同上

#### 3.6 變數插入 Dropdown

- [ ] **檔案命名格式**：
  - 輸入框正常
  - 「變數」按鈕為**強調樣式**（主題色邊框 + 背景，有 `{}` icon）
  - 點擊按鈕時下拉列表顯示（Alpine.js `x-show="open"`）
  - 點擊列表項目時變數插入輸入框（JS `click` event）
  - 點擊外部時下拉列表關閉（`@click.outside="open = false"`）
- [ ] **資料夾多層**：
  - 初始狀態：外層/中層 disabled（灰化），內層 enabled
  - 內層輸入值後，中層自動 enabled
  - 中層輸入值後，外層自動 enabled
  - 清空內層後，中層/外層自動 disabled + 清空
  - 即時預覽路徑正確顯示（範例：`SSNI-618/[SSNI-618][SOD] 絕對領域.mp4`）

#### 3.7 API Key 警告

- [ ] **安全警告**：
  - 顯示為橘色 alert（DaisyUI `.alert-warning`）
  - 左側有 `⚠️` icon（`bi-exclamation-triangle-fill`）
  - 文字為列表（`<ul>` + `<li>`）
  - 連結為藍色底線（`.alert-link`）

#### 3.8 版本 + 檢查更新

- [ ] **版本資訊**：
  - 版本號為 Monospace 字體（`'SF Mono', 'Fira Code', Consolas`）
  - 顏色為主題色（`var(--accent)`）
- [ ] **檢查更新按鈕**：
  - Default 狀態：「檢查更新」按鈕
  - Loading 狀態：按鈕 disabled，顯示 spinner + "檢查中..."
  - Completed（有更新）：顯示綠色 badge「新版本 vX.X.X 可用」+ 下載連結
  - Completed（已最新）：顯示灰色文字「已是最新版本」
  - Completed（錯誤）：顯示紅色文字「網路錯誤」

#### 3.9 儲存按鈕

- [ ] **儲存設定按鈕**：
  - 位於表單最下方，右對齊
  - Hover 時有 glow 效果（4px 主題色陰影）
  - Hover 時按鈕上浮 1px（`translateY(-1px)`）
  - 點擊後正常儲存（console 無 error）

#### 3.10 主題切換

- [ ] **Light 模式**：
  - 所有元件（toggle、input、select、button、alert）顏色正常
  - 收合區塊背景為淺色
  - 變數按鈕為淺色主題色背景
- [ ] **Dim 模式**：
  - 切換主題後所有元件顏色正常
  - 收合區塊背景為深色
  - 變數按鈕為深色主題色背景
  - 無閃爍或佈局跳動

#### 3.11 Console 檢查

- [ ] **無 Error**：開啟 DevTools Console，無紅色錯誤訊息
- [ ] **無 Warning**：無 CSS class 找不到的警告
- [ ] **無 Layout Shift**：無 CLS（Cumulative Layout Shift）警告

### 4. 視覺回歸測試

對比 `design_system/settings-components.html` 的 Design System 規範：
- Toggle switch 樣式一致（toggle 寬度、間距、說明文字縮排）
- Select 邊框樣式一致（`select-bordered`）
- Number input + 單位後綴樣式一致（`.input-suffix` 顏色、字重）
- 收合區塊卡片樣式一致（背景、邊框、陰影、hover 效果）
- 變數按鈕強調樣式一致（主題色邊框、背景、icon、hover glow）
- API Key alert 樣式一致（icon、文字大小、列表間距）
- 儲存按鈕 hover 動畫一致（glow + translateY）

## 完成條件

### 必要條件

- [ ] HTML 模板中所有 Bootstrap class 替換完成（約 100 處）
- [ ] Inline JS 中所有 Bootstrap class 替換完成（`spinner-border` ×4、`text-danger` ×15、`dropdown-item` ×8、`dropdown-menu` ×4）
- [ ] 加上 `id="settings-components"` scope wrapper（L117）
- [ ] Inline `<style>` 重複定義移除（約 20 行）
- [ ] Design System 語義 class 套用完成（14 個新 class）
- [ ] `grep -n "form-check\|form-control\|form-select\|btn-outline-primary\|btn-outline-secondary" web/templates/settings.html` 結果為空
- [ ] `grep -n "spinner-border\|text-danger\|dropdown-item\|dropdown-menu\|folder-layer-vars\|format-vars" web/templates/settings.html` 結果為空（inline JS）
- [ ] `grep -n "\.form-check\|\.form-control\|\.collapse-toggle" web/templates/settings.html` 結果為空（inline style）
- [ ] `grep -n 'id="settings-components"' web/templates/settings.html` 結果為 1
- [ ] pytest 通過（config API 測試）
- [ ] 手動 UI 驗證 Checklist 全部勾選
- [ ] Light / Dim 主題切換正常
- [ ] 無 console error / warning

### 加分條件

- [ ] Playwright 視覺回歸測試通過（對比 Design System）
- [ ] Performance Lighthouse 評分 ≥ 90
- [ ] Accessibility WCAG 2.1 AA 級別無違規

## 風險與對策

| 風險 | 可能性 | 影響 | 對策 |
|------|--------|------|------|
| Alpine.js 收合動畫與 Bootstrap Collapse 行為不一致 | 中 | 中 | 使用 Alpine.js `x-transition` 內建動畫，無需自訂 CSS。測試展開/收合流暢度 |
| `.settings-hint` 縮排在 toggle 和 form row 中不一致 | 中 | 中 | theme.css L1343-1345 針對 `.settings-form-group .settings-hint` 加 `margin-left: 48px`，form row 的 hint 無縮排 |
| 資料夾多層連動 JS 邏輯與 Alpine.js 衝突 | 低 | 高 | Alpine.js 只控制 dropdown 顯示，連動邏輯仍用原 JS `updateFolderLayers()`。測試禁用/啟用狀態 |
| 變數插入 dropdown 的 Alpine.js `@click.outside` 無效 | 低 | 中 | 確保 `x-data="{ open: false }"` 在正確層級，dropdown 外層有 `@click.outside` |
| API Key alert 的 inline style 移除後樣式錯誤 | 低 | 中 | theme.css L1627-1671 已定義 `.api-key-alert` 樣式，移除前先檢查 CSS 規則是否完整 |
| 主題切換時 Alpine.js `x-model="theme"` 未同步 | 低 | 高 | 確保 `x-model="theme"` 綁定正確，測試 select 切換時 `data-theme` attribute 是否更新 |
| 儲存按鈕 hover 動畫在 mobile 無效 | 極低 | 低 | Mobile 無 hover 狀態，無需處理。Desktop 測試 hover glow + translateY |
| Inline `<style>` 誤刪必要樣式（如 `.spin` 動畫） | 低 | 中 | 只刪除與 theme.css 重複的定義，保留 `.settings-container`, `.spin`, `.card` 等自訂樣式 |

## 參考檔案

| 檔案 | 路徑 | 用途 |
|------|------|------|
| settings.html | `/home/peace/OpenAver/web/templates/settings.html` | 主要修改目標（HTML + inline style） |
| settings.html (舊版) | `/home/peace/OpenAver/feature/OpenAver 0.2.3/web/templates/settings.html` | 對比舊版結構 |
| theme.css | `/home/peace/OpenAver/web/static/css/theme.css` | Settings 元件定義（L1308-1710） |
| settings-components.html | `/home/peace/OpenAver/web/templates/design_system/settings-components.html` | Design System 規格參考 |
| TASK-M3a.md | `/home/peace/OpenAver/feature/24-migrate/TASK-M3a.md` | Search 遷移參考（template） |
| TASK-M2a.md | `/home/peace/OpenAver/feature/24-migrate/TASK-M2a.md` | Scanner 遷移參考 |
| DaisyUI Toggle | https://daisyui.com/components/toggle/ | Toggle switch 用法 |
| DaisyUI Select | https://daisyui.com/components/select/ | Select 下拉選單用法 |
| DaisyUI Alert | https://daisyui.com/components/alert/ | Alert 樣式參考 |
| Alpine.js x-show | https://alpinejs.dev/directives/show | 顯示/隱藏控制 |
| Alpine.js x-transition | https://alpinejs.dev/directives/transition | 過渡動畫 |
| Alpine.js @click.outside | https://alpinejs.dev/directives/on#click-outside | 外部點擊關閉 dropdown |
