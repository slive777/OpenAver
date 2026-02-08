# TASK-M4b: Settings inline JS 抽離（搬移,不改邏輯）

## 目標
將 settings.html 的 L532-1305 `<script>` 區塊（約 774 行）搬移到獨立檔案，**不改邏輯、不改函數簽名**，保持 HTML 中的 `onclick="..."`, `oninput="..."`, `onchange="..."` 呼叫方式不變。

## 背景

### 前置完成
- **M2b 已完成**：scanner.html JS 模組化完成（core.js / alias.js / folders.js / init.js）
- **M3 系列已完成**：search 頁面 JS 模組化完成（core.js / ui.js / file.js / init.js）

### M4b 定義（來自 plan-24.md）

```
M4b: Settings inline JS 抽離（搬移，不改邏輯）
web/static/js/pages/settings/
├── core.js       # config 讀取/儲存
├── translate.js  # Ollama/Gemini 測試
├── folders.js    # 資料夾選擇、PyWebView API
├── format.js     # 輸出格式預覽、變數 dropdown
└── init.js       # 事件綁定、初始化
```

### 與其他頁面的比較

| 項目 | search 頁面 | scanner 頁面 | settings 頁面 |
|------|-----------|------------|--------------|
| **模組模式** | `window.SearchCore` 命名空間 | 全域函數 | 全域函數 |
| **函數簽名** | `SearchCore.doSearch()` | `generate()` | `loadConfig()`, `saveConfig()` 等 |
| **事件綁定** | init.js 中用 `addEventListener` | HTML attribute（`onclick`）+ init.js 混合 | HTML attribute + init.js 混合 |
| **狀態管理** | `state` 物件 | 全域變數 | 全域變數（`config`） |
| **PyWebView 介接** | `window.handlePyWebViewDrop()` | `window.handleFolderDrop()` | `selectOutputFolder()` 透過 pywebview.api |

### 關鍵約束

1. **函數簽名和呼叫方式不變** — HTML 中用 `onclick="testOllamaConnection()"`, `onchange="updateFolderLayers()"` 等直接呼叫，函數必須保持全域作用域
2. **不使用 ES Module** — 與 search, scanner 頁面一致，用多個 `<script src>` 標籤載入
3. **不改邏輯** — 只做搬移，不做重構（重構是後續 Phase 的工作）
4. **載入順序重要** — core.js（宣告共享狀態）→ translate.js, folders.js, format.js（功能模組）→ init.js（初始化）
5. **PyWebView API 呼叫** — `selectOutputFolder()` 使用 `window.pywebview.api`，需保持非同步結構

## 修改範圍

| 檔案/目錄 | 說明 |
|----------|------|
| `/home/peace/OpenAver/web/static/js/pages/settings/` | **新建目錄** |
| `/home/peace/OpenAver/web/static/js/pages/settings/core.js` | **新建**：config 載入/儲存、showToast |
| `/home/peace/OpenAver/web/static/js/pages/settings/translate.js` | **新建**：Ollama/Gemini 連線測試、翻譯測試 |
| `/home/peace/OpenAver/web/static/js/pages/settings/folders.js` | **新建**：資料夾選擇（PyWebView API） |
| `/home/peace/OpenAver/web/static/js/pages/settings/format.js` | **新建**：格式變數 dropdown、資料夾預覽 |
| `/home/peace/OpenAver/web/static/js/pages/settings/init.js` | **新建**：事件綁定、初始化呼叫 |
| `/home/peace/OpenAver/web/templates/settings.html` | **修改**：L532-1305 `<script>` 替換為 5 個 `<script src>` 標籤 |

## 函數依賴分析

### 1. 全域狀態變數（無，僅使用區域變數）

Settings 頁面不需要全域共享狀態（與 scanner 不同），所有狀態暫存在 DOM 中，透過 `document.getElementById()` 存取。

### 2. core.js 模組（Config 載入/儲存、Toast）

**Config 相關**：

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `loadConfig()` | L690-792 | `async () => void` | DOM, `updateTranslateOptions()`, `loadOllamaModels()`, `testGeminiConnection()` | L1303 init, L1239 reset |
| `saveConfig()` | L795-889 | `async () => void` | DOM, `showToast()` | L1230 form submit |
| `updateTranslateOptions()` | L892-908 | `() => void` | DOM, `onTranslateProviderChange()` | L753, L1221 translateEnabled change |
| `onTranslateProviderChange()` | L911-937 | `() => void` | DOM | L906, L1222 translateProvider change |

**Toast 提示**：

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `showToast()` | L1094-1101 | `(message, type = 'info') => void` | 無（使用 `alert`） | L801, L881, L884, L887 |

### 3. translate.js 模組（Ollama/Gemini 測試）

**Ollama 測試**：

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `testOllamaConnection()` | L1136-1180 | `async () => void` | DOM | L1223 testOllamaBtn click, HTML L139 onclick |
| `testModel()` | L1183-1218 | `async () => void` | DOM | L1224 testModelBtn click, HTML L155 onclick |
| `loadOllamaModels()` | L1104-1133 | `async (url, savedModel = '') => void` | DOM | L786 loadConfig |

**Gemini 測試**：

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `testGeminiConnection()` | L940-994 | `async () => void` | DOM, `populateGeminiModels()` | L749 loadConfig 自動測試, L1225 testGeminiBtn click, HTML L171 onclick |
| `populateGeminiModels()` | L997-1023 | `(models) => void` | DOM | L971 |
| `testGeminiTranslation()` | L1026-1074 | `async () => void` | DOM | L1226 testGeminiTranslateBtn click, HTML L205 onclick |

### 4. folders.js 模組（資料夾選擇）

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `selectOutputFolder()` | L1077-1091 | `async () => void` | `window.pywebview.api`, DOM | HTML L344 onclick |

### 5. format.js 模組（格式變數 dropdown、資料夾預覽）

**格式變數常數**：

| 變數 | 行號 | 類型 | 說明 | 被引用處 |
|------|------|------|------|---------|
| `formatVariables` | L534-542 | `Array<Object>` | 格式變數清單 | L545-574 dropdown 初始化 |
| `FOLDER_PREVIEW_DATA` | L577-585 | `Object` | 資料夾預覽範例資料 | L637, L657 |

**資料夾格式預覽**：

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `updateFolderLayers()` | L588-629 | `() => void` | DOM, `FOLDER_PREVIEW_DATA`, `updateFolderPreview()` | HTML L229 onchange, HTML L241,254,267 oninput, L684,718 loadConfig |
| `updateFolderPreview()` | L631-665 | `() => void` | DOM, `FOLDER_PREVIEW_DATA` | L606,628, HTML L289 oninput |

**格式變數 dropdown 初始化**（L545-574, L668-687）：
- 為所有 `.variable-menu[data-type="format"]` 填入變數項目
- 為所有 `.variable-menu[data-target^="folderLayer"]` 填入資料夾層變數
- 監聽點擊事件，插入變數到輸入框

### 6. init.js 模組（事件綁定、初始化）

**事件監聽器**：

| 事件 | 行號 | 處理函數 | 依賴 |
|------|------|---------|------|
| `translateEnabled.change` | L1221 | `updateTranslateOptions()` | core.js |
| `translateProvider.change` | L1222 | `onTranslateProviderChange()` | core.js |
| `testOllamaBtn.click` | L1223 | `testOllamaConnection()` | translate.js |
| `testModelBtn.click` | L1224 | `testModel()` | translate.js |
| `testGeminiBtn.click` | L1225 | `testGeminiConnection()` | translate.js |
| `testGeminiTranslateBtn.click` | L1226 | `testGeminiTranslation()` | translate.js |
| `settingsForm.submit` | L1228-1231 | `saveConfig()` | core.js |
| `resetBtn.click` | L1233-1248 | `loadConfig()` | core.js |
| `btnRestartTutorial.click` | L1251-1253 | 重導向至 `/search?tutorial=restart` | 無 |
| `btnCheckUpdate.click` | L1270-1300 | 檢查更新 | DOM |

**初始化呼叫**（L1303-1304）：
```javascript
loadConfig();
loadVersion();
```

**版本資訊**：

| 函數 | 行號 | 簽名 | 依賴 | 被呼叫處 |
|------|------|------|------|---------|
| `loadVersion()` | L1256-1267 | `async () => void` | DOM | L1304 init |

## 模組分割表

| 行號 | 類型 | 函數/變數名稱 | 歸屬模組 | 備註 |
|------|------|-------------|---------|------|
| L534-542 | 常數 | `formatVariables` | format.js | 格式變數清單 |
| L545-574 | 初始化 | 格式變數 dropdown | format.js | `querySelectorAll('.variable-menu[data-type="format"]')` |
| L577-585 | 常數 | `FOLDER_PREVIEW_DATA` | format.js | 預覽範例資料 |
| L588-629 | 函數 | `updateFolderLayers()` | format.js | 資料夾層連動 |
| L631-665 | 函數 | `updateFolderPreview()` | format.js | 資料夾預覽更新 |
| L668-687 | 初始化 | 資料夾層變數 dropdown | format.js | `querySelectorAll('.variable-menu[data-target^="folderLayer"]')` |
| L690-792 | 函數 | `loadConfig()` | core.js | 載入設定 |
| L795-889 | 函數 | `saveConfig()` | core.js | 儲存設定 |
| L892-908 | 函數 | `updateTranslateOptions()` | core.js | 翻譯選項顯示/隱藏 |
| L911-937 | 函數 | `onTranslateProviderChange()` | core.js | Provider 切換 |
| L940-994 | 函數 | `testGeminiConnection()` | translate.js | Gemini API Key 測試 |
| L997-1023 | 函數 | `populateGeminiModels()` | translate.js | 填充 Gemini 模型下拉框 |
| L1026-1074 | 函數 | `testGeminiTranslation()` | translate.js | Gemini 翻譯測試 |
| L1077-1091 | 函數 | `selectOutputFolder()` | folders.js | PyWebView 選擇資料夾 |
| L1094-1101 | 函數 | `showToast()` | core.js | Toast 提示 |
| L1104-1133 | 函數 | `loadOllamaModels()` | translate.js | 載入 Ollama 模型列表 |
| L1136-1180 | 函數 | `testOllamaConnection()` | translate.js | Ollama 連線測試 |
| L1183-1218 | 函數 | `testModel()` | translate.js | Ollama 模型測試 |
| L1221 | 事件 | `translateEnabled.change` | init.js | |
| L1222 | 事件 | `translateProvider.change` | init.js | |
| L1223 | 事件 | `testOllamaBtn.click` | init.js | |
| L1224 | 事件 | `testModelBtn.click` | init.js | |
| L1225 | 事件 | `testGeminiBtn.click` | init.js | |
| L1226 | 事件 | `testGeminiTranslateBtn.click` | init.js | |
| L1228-1231 | 事件 | `settingsForm.submit` | init.js | |
| L1233-1248 | 事件 | `resetBtn.click` | init.js | |
| L1251-1253 | 事件 | `btnRestartTutorial.click` | init.js | |
| L1256-1267 | 函數 | `loadVersion()` | init.js | 版本資訊載入 |
| L1270-1300 | 事件 | `btnCheckUpdate.click` | init.js | 檢查更新 |
| L1303-1304 | 初始化 | 初始化呼叫 | init.js | `loadConfig()`, `loadVersion()` |

## 載入順序說明

### 為什麼 core.js 要第一個載入？

1. **提供核心工具函數** — `showToast()` 被 core.js 自己和其他模組呼叫
2. **Config 載入/儲存邏輯** — `loadConfig()` 會呼叫 translate.js 和 format.js 的函數，需先宣告
3. **翻譯選項控制** — `updateTranslateOptions()`, `onTranslateProviderChange()` 被 init.js 事件綁定引用

### 為什麼 format.js 要在 core.js 之後？

1. **loadConfig() 會呼叫 updateFolderLayers()** — L718, L684
2. **dropdown 初始化依賴 DOM 已載入** — L545, L668 使用 `querySelectorAll`
3. **避免 ReferenceError** — 若 format.js 在 init.js 之後，dropdown 初始化會失效

### 為什麼 init.js 要最後載入？

1. **依賴其他模組的函數** — `updateTranslateOptions()` (core.js), `testOllamaConnection()` (translate.js), `loadConfig()` (core.js), `loadVersion()` (init.js 自己)
2. **初始化呼叫是最後一步** — L1303-1304 的初始化呼叫依賴所有模組的函數

### 完整載入順序

```html
{% block extra_js %}
<script src="/static/js/pages/settings/core.js"></script>       <!-- 1️⃣ Config、Toast -->
<script src="/static/js/pages/settings/translate.js"></script>  <!-- 2️⃣ Ollama/Gemini 測試 -->
<script src="/static/js/pages/settings/folders.js"></script>    <!-- 3️⃣ PyWebView 資料夾選擇 -->
<script src="/static/js/pages/settings/format.js"></script>     <!-- 4️⃣ 格式預覽、dropdown -->
<script src="/static/js/pages/settings/init.js"></script>       <!-- 5️⃣ 事件綁定、初始化 -->
{% endblock %}
```

**translate.js 和 folders.js 可互換嗎？**
- ✅ 可以，它們互不依賴，只依賴 core.js
- ⚠️ 但為了可讀性，建議按功能分組排序

**format.js 能放到 translate.js 之前嗎？**
- ✅ 可以，format.js 不依賴 translate.js
- ⚠️ 但 format.js 依賴 core.js，所以必須在 core.js 之後

## 技術要點

### 1. 全域作用域策略

**不使用命名空間**（與 search 頁面不同，與 scanner 頁面相同）：
```javascript
// ❌ search 頁面模式（不適用於 settings）
window.SettingsCore = { loadConfig: function() { ... } };

// ✅ settings 頁面模式（保持全域函數）
function loadConfig() { ... }   // HTML 可用 Alpine.js x-data 或 onclick 呼叫
```

**原因**：settings.html 使用 `onchange="updateFolderLayers()"`, `onclick="testOllamaConnection()"` 等 HTML attribute，改為命名空間需修改所有 HTML，違反「不改邏輯」原則。

### 2. PyWebView API 呼叫

```javascript
// folders.js
async function selectOutputFolder() {
    if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
        alert('此功能需要在桌面應用程式中使用');
        return;
    }

    try {
        const result = await window.pywebview.api.select_folder();
        if (result && result.folder) {
            document.getElementById('avlistOutputDir').value = result.folder;
        }
    } catch (e) {
        console.error('選擇資料夾失敗:', e);
    }
}
```

- `window.pywebview.api` 是 PyWebView 注入的 API，需檢查存在性
- 非同步結構需保持，使用 `async/await`

### 3. Dropdown 初始化依賴 DOM

```javascript
// format.js - 格式變數 dropdown 初始化
document.querySelectorAll('.variable-menu[data-type="format"]').forEach(menu => {
    formatVariables.forEach(v => {
        const div = document.createElement('div');
        // ...
        menu.appendChild(div);
    });

    menu.addEventListener('click', (e) => { ... });
});
```

- `querySelectorAll` 需在 DOM 載入後執行
- 不需要 `DOMContentLoaded` 包裝，因為 `<script>` 在 `{% endblock %}` 最後（DOM 已載入）

### 4. loadConfig() 的跨模組呼叫

```javascript
// core.js - loadConfig()
async function loadConfig() {
    // ...

    // 呼叫 format.js 的函數
    updateFolderLayers();  // L718

    // 呼叫 translate.js 的函數
    await loadOllamaModels(ollamaUrl, ollamaModel);  // L786

    if (config.translate.gemini.api_key && config.translate.provider === 'gemini') {
        setTimeout(() => testGeminiConnection(), 100);  // L749
    }
}
```

- `loadConfig()` 會呼叫其他模組的函數，需確保載入順序正確
- `updateFolderLayers()` (format.js) 必須在 core.js 載入後定義
- `loadOllamaModels()`, `testGeminiConnection()` (translate.js) 必須在 core.js 載入後定義

### 5. 與 scanner 頁面模式對比

| 項目 | scanner 頁面 | settings 頁面 |
|------|------------|--------------|
| **全域狀態變數** | `directories`, `config`, `isGenerating` | 無（狀態在 DOM 中） |
| **DOM 引用** | 直接用 `document.getElementById()` | 直接用 `document.getElementById()` |
| **函數暴露** | `function generate()` (全域) | `function loadConfig()` (全域) |
| **模組通訊** | 直接呼叫（同全域作用域） | 直接呼叫（同全域作用域） |
| **PyWebView 介接** | `window.handleFolderDrop()` (拖曳) | `selectOutputFolder()` (選擇資料夾) |
| **特殊功能** | SSE EventSource（generate, runNfoUpdate） | 格式變數 dropdown、翻譯測試 |

### 6. 格式變數 dropdown 的事件委派

```javascript
// format.js - L558-573
menu.addEventListener('click', (e) => {
    e.preventDefault();
    const item = e.target.closest('[data-var]');
    if (item) {
        const targetId = menu.dataset.target;
        const input = document.getElementById(targetId);
        const cursorPos = input.selectionStart;
        const textBefore = input.value.substring(0, cursorPos);
        const textAfter = input.value.substring(cursorPos);
        input.value = textBefore + item.dataset.var + textAfter;
        input.focus();
        input.setSelectionRange(cursorPos + item.dataset.var.length, cursorPos + item.dataset.var.length);
        // 更新預覽
        if (targetId === 'folderFormat') updateFolderPreview();
    }
});
```

- 使用 `e.target.closest('[data-var]')` 事件委派處理動態生成的項目
- 插入變數後自動更新游標位置（`setSelectionRange`）

## settings.html 修改

### 修改前（L532-1305）
```html
{% block extra_js %}
<script>
    // 格式變數清單
    const formatVariables = [ ... ];
    // ... 774 行 JS ...
    loadConfig();
    loadVersion();
</script>
{% endblock %}
```

### 修改後
```html
{% block extra_js %}
<script src="/static/js/pages/settings/core.js"></script>
<script src="/static/js/pages/settings/translate.js"></script>
<script src="/static/js/pages/settings/folders.js"></script>
<script src="/static/js/pages/settings/format.js"></script>
<script src="/static/js/pages/settings/init.js"></script>
{% endblock %}
```

**行號變化**：
- 原本 L532-1305（774 行）→ 替換為 6 行
- 總行數從 1306 行 → 537 行

## 驗證方式

### 1. 檔案結構檢查

```bash
# 檢查目錄和檔案是否建立
ls -lh web/static/js/pages/settings/
# 預期：core.js, translate.js, folders.js, format.js, init.js 五個檔案

# 檢查 settings.html 是否正確引用
grep -A 6 "{% block extra_js %}" web/templates/settings.html
# 預期：5 個 <script src> 標籤
```

### 2. 函數全域性檢查（Console 測試）

在瀏覽器 Console：
```javascript
// 檢查全域函數是否存在
typeof loadConfig              // "function"
typeof saveConfig              // "function"
typeof updateFolderLayers      // "function"
typeof testOllamaConnection    // "function"
typeof testGeminiConnection    // "function"
typeof selectOutputFolder      // "function"

// 檢查常數是否存在
typeof formatVariables         // "object" (Array)
typeof FOLDER_PREVIEW_DATA     // "object"
```

### 3. Pytest（API 測試，確保邏輯不變）

```bash
source venv/bin/activate && pytest tests/integration/test_api_config.py -v
source venv/bin/activate && pytest tests/integration/test_api_ollama.py -v
source venv/bin/activate && pytest tests/integration/test_api_gemini.py -v
```

**說明**：M4b 只搬移 JS，不改邏輯，API 行為不變，測試應全部通過。

### 4. 手動 UI 驗證（Checklist）

- [ ] **Config 載入/儲存**
  - [ ] 頁面載入後自動填入設定值（translate enabled, provider, theme 等）
  - [ ] 修改設定後點擊「儲存設定」按鈕（toast 提示）
  - [ ] 點擊「重置為預設值」按鈕（confirm 對話框 → 恢復預設值）

- [ ] **翻譯服務 - Ollama**
  - [ ] 切換 Provider 為 Ollama（Ollama 欄位顯示，Gemini 隱藏）
  - [ ] 點擊「測試」按鈕（連線測試、模型列表載入）
  - [ ] 選擇模型後點擊「測試」按鈕（模型測試）

- [ ] **翻譯服務 - Gemini**
  - [ ] 切換 Provider 為 Gemini（Gemini 欄位顯示，Ollama 隱藏）
  - [ ] 輸入 API Key 後點擊「測試」按鈕（找到模型、模型下拉框啟用）
  - [ ] 選擇模型後點擊「測試」按鈕（翻譯測試成功）

- [ ] **資料夾格式預覽**
  - [ ] 勾選/取消「建立資料夾」（資料夾層輸入框啟用/禁用）
  - [ ] 在「內層」輸入框輸入變數（「中層」啟用、預覽更新）
  - [ ] 在「中層」輸入框輸入變數（「外層」啟用、預覽更新）
  - [ ] 點擊變數按鈕（dropdown 顯示、點擊變數插入到輸入框）
  - [ ] 修改「檔案命名格式」（預覽即時更新）

- [ ] **輸出資料夾選擇**
  - [ ] 點擊資料夾選擇按鈕（PyWebView 對話框）— 🖥️ 需桌面應用

- [ ] **系統設定**
  - [ ] 切換主題模式（頁面即時切換 light/dim）
  - [ ] 點擊「重看新手引導」（跳轉到 `/search?tutorial=restart`）
  - [ ] 點擊「檢查更新」（顯示版本資訊或更新連結）

- [ ] **無 Console Error**
  - [ ] 開啟 DevTools Console，無 `Uncaught ReferenceError` 或 `xxx is not defined`
  - [ ] 無 CORS 或 404 錯誤（5 個 .js 檔案正確載入）

### 5. 載入順序驗證

在各模組第一行加入 console.log：
```javascript
// core.js
console.log('[Settings] core.js loaded');

// translate.js
console.log('[Settings] translate.js loaded');

// folders.js
console.log('[Settings] folders.js loaded');

// format.js
console.log('[Settings] format.js loaded');

// init.js
console.log('[Settings] init.js loaded');
```

預期 Console 輸出順序：
```
[Settings] core.js loaded
[Settings] translate.js loaded
[Settings] folders.js loaded
[Settings] format.js loaded
[Settings] init.js loaded
```

若順序錯誤（如 format.js 在 core.js 前），`loadConfig()` 呼叫 `updateFolderLayers()` 會出現 `ReferenceError: updateFolderLayers is not defined`。

## 完成條件

- [ ] `/home/peace/OpenAver/web/static/js/pages/settings/` 目錄建立
- [ ] `core.js`, `translate.js`, `folders.js`, `format.js`, `init.js` 五個檔案建立
- [ ] settings.html L532-1305 `<script>` 區塊替換為 5 個 `<script src>` 標籤
- [ ] `grep "<script>" web/templates/settings.html` 只顯示 5 個 `<script src>` 標籤（無 inline `<script>`）
- [ ] pytest 通過（`test_api_config.py`, `test_api_ollama.py`, `test_api_gemini.py`）
- [ ] Console 檢查：所有全域函數和常數存在
- [ ] 手動 UI 驗證 Checklist 全部勾選
- [ ] 無 Console Error / ReferenceError
- [ ] 載入順序驗證正確（core → translate → folders → format → init）

## 風險與對策

| 風險 | 可能性 | 影響 | 對策 |
|------|--------|------|------|
| **ReferenceError: updateFolderLayers is not defined** | 高 | loadConfig() 失敗 | 確保 format.js 在 core.js 後、init.js 前載入 |
| **onchange 函數找不到** | 中 | HTML attribute 呼叫失效 | 確保函數在全域作用域（不用命名空間） |
| **formatVariables 未定義** | 中 | dropdown 初始化失敗 | 確保 format.js 載入完成後再執行 dropdown 初始化 |
| **PyWebView API 檢查失效** | 低 | 桌面應用選擇資料夾失效 | 保持 `typeof window.pywebview` 檢查邏輯 |
| **loadOllamaModels 非同步問題** | 低 | Ollama 模型列表不顯示 | 保持 `await loadOllamaModels()` |
| **Gemini 自動測試觸發失敗** | 低 | 有 API Key 時不自動載入模型 | 保持 `setTimeout(() => testGeminiConnection(), 100)` 延遲執行 |
| **dropdown 事件委派失效** | 低 | 點擊變數無反應 | 確保 `e.target.closest('[data-var]')` 邏輯正確搬移 |
| **CORS 錯誤（.js 檔案 404）** | 極低 | 模組無法載入 | 檢查檔案路徑、nginx 設定、重啟服務 |

## 模組內容概要

### core.js（約 160 行）
- `loadConfig()` — L690-792（103 行）
- `saveConfig()` — L795-889（95 行）
- `updateTranslateOptions()` — L892-908（17 行）
- `onTranslateProviderChange()` — L911-937（27 行）
- `showToast()` — L1094-1101（8 行）

### translate.js（約 165 行）
- `testGeminiConnection()` — L940-994（55 行）
- `populateGeminiModels()` — L997-1023（27 行）
- `testGeminiTranslation()` — L1026-1074（49 行）
- `loadOllamaModels()` — L1104-1133（30 行）
- `testOllamaConnection()` — L1136-1180（45 行）
- `testModel()` — L1183-1218（36 行）

### folders.js（約 15 行）
- `selectOutputFolder()` — L1077-1091（15 行）

### format.js（約 180 行）
- `formatVariables` 常數 — L534-542（9 行）
- 格式變數 dropdown 初始化 — L545-574（30 行）
- `FOLDER_PREVIEW_DATA` 常數 — L577-585（9 行）
- `updateFolderLayers()` — L588-629（42 行）
- `updateFolderPreview()` — L631-665（35 行）
- 資料夾層變數 dropdown 初始化 — L668-687（20 行）

### init.js（約 85 行）
- 事件綁定 — L1221-1226（6 行）
- `settingsForm.submit` — L1228-1231（4 行）
- `resetBtn.click` — L1233-1248（16 行）
- `btnRestartTutorial.click` — L1251-1253（3 行）
- `loadVersion()` — L1256-1267（12 行）
- `btnCheckUpdate.click` — L1270-1300（31 行）
- 初始化呼叫 — L1303-1304（2 行）

**總計**：~605 行（原 774 行，扣除空行和註解）

## 實作順序建議

1. **建立目錄**：`mkdir -p web/static/js/pages/settings`
2. **建立 core.js**：複製 L690-908, L1094-1101
3. **建立 translate.js**：複製 L940-1023, L1026-1074, L1104-1218
4. **建立 folders.js**：複製 L1077-1091
5. **建立 format.js**：複製 L534-687
6. **建立 init.js**：複製 L1221-1304
7. **修改 settings.html**：L532-1305 替換為 5 個 `<script src>` 標籤
8. **測試**：開啟頁面 → Console 檢查 → 測試功能 → 檢查 UI
9. **Pytest**：確保 API 測試通過
10. **Commit**：`refactor(M4b): settings.html inline JS 抽離到獨立檔案`

**預計修改量**：
- 新增 5 個檔案（~605 行）
- 修改 settings.html（-774 行，+6 行）
- 無邏輯變更，純搬移

---

**TASK 狀態**：🟡 待執行
**預計時間**：1-2 小時（搬移 + 測試）
**優先級**：Medium（M4a 完成後進行）
**依賴**：無（M4a 是 HTML/CSS 修改，與 M4b 獨立）
