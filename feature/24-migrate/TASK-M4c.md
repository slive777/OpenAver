# TASK-M4c: Settings 特殊互動驗證與修復

## 目標

驗證 Settings 頁面在 M4a/M4b 遷移後，所有特殊互動功能（Collapse 區塊、變數插入 Dropdown、Toast 通知）運作正常，並修復發現的問題。

## 背景

**前置工作**：
- **M4a** 已完成 Settings HTML class 替換（Bootstrap → DaisyUI + Design System）
- **M4b** 已完成 Settings inline JS 抽離為模組（core.js、translate.js、folders.js、format.js、init.js）

**M4c 範圍**：
- **驗證專注**：確認 Alpine.js collapsible、變數 dropdown、Toast 等互動邏輯正常
- **不改架構**：不重構 JS 邏輯，只修復因遷移導致的 bug
- **對齊 Design System**：確保元件樣式與 `/design-system/settings-components.html` 一致

## 修改範圍

| 檔案 | 說明 |
|------|------|
| `/home/peace/OpenAver/web/templates/settings.html` | 驗證 Alpine.js 指令、class 使用正確性 |
| `/home/peace/OpenAver/web/static/js/pages/settings/core.js` | 修復 `showToast()` 函數（alert → DaisyUI toast） |
| `/home/peace/OpenAver/web/static/js/pages/settings/format.js` | 驗證變數插入 dropdown 互動 |
| `/home/peace/OpenAver/web/static/css/theme.css` | 驗證 `#settings-components` scoped 樣式 |
| `/home/peace/OpenAver/web/templates/design_system/settings-components.html` | 參考規格（D.9a/D.9b/D.9c）|

## 當前狀態分析

### 1. Collapse 區塊（Alpine.js x-collapse）

**當前實作**（settings.html L216-328、L359-420）：
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
        <!-- 展開後的內容 -->
    </div>
</div>
```

**設計規格**（design-system/settings-components.html L217-284）：
- ✅ Alpine.js `x-data`、`x-show`、`x-transition` 指令使用正確
- ✅ `:class="{ 'rotate-180': expanded }"` 動畫 binding 正確
- ✅ `collapsible-trigger`、`collapsible-content` class 與 theme.css L1393-1458 對應
- ⚠️ **潛在問題**：HTML 未使用 Alpine.js `x-collapse` directive（Design System 只用了 `x-show` + `x-transition`）

**驗證項目**：
1. 點擊觸發器，展開/收合動畫流暢（無跳動）
2. Chevron 圖標旋轉 180° 動畫正常
3. `aria-expanded` 屬性正確更新（無障礙支援）
4. Light / Dim 主題切換時背景色正常

### 2. 變數插入 Dropdown（Alpine.js x-show）

**當前實作**（settings.html L264-274、L286-297）：
```html
<div class="folder-layer-group" x-data="{ open: false }">
    <input type="text" class="input input-bordered input-sm" id="folderLayer3">
    <button class="btn-variable-sm" type="button" @click="open = !open">
        <i class="bi bi-braces"></i>
    </button>
    <div x-show="open" @click.outside="open = false" x-transition
         class="variable-menu" data-target="folderLayer3">
    </div>
</div>
```

**設計規格**（design-system/settings-components.html L293-344）：
- ✅ Alpine.js `x-data`、`x-show`、`@click.outside` 指令使用正確
- ✅ `variable-menu` 與 theme.css L1499-1543 對應
- ✅ 變數清單在 format.js L1-42 動態生成
- ⚠️ **潛在問題**：`variable-menu` 使用 `position: relative` 可能導致 z-index 問題（需驗證是否被父容器裁剪）

**驗證項目**：
1. 點擊 `{...}` 按鈕，dropdown 正常顯示
2. 點擊外部區域（@click.outside），dropdown 關閉
3. 點擊變數項目，變數插入到對應 input（format.js L26-41 事件監聽）
4. 多層資料夾（外層/中層/內層）的連動啟用邏輯正常（format.js L56-96）
5. 即時預覽路徑更新正常（format.js L99-133）
6. Dropdown 不被 `.card` 的 `overflow: visible` 裁剪（settings.html L42）

### 3. Toast 通知（儲存成功/失敗）

**當前實作**（core.js L252-259）：
```javascript
function showToast(message, type = 'info') {
    // 簡單的 alert，可以之後改成 Bootstrap toast
    if (type === 'success') {
        alert(message);
    } else {
        alert('錯誤: ' + message);
    }
}
```

**問題**：
- ❌ 仍使用 `alert()`，未使用 DaisyUI toast
- ❌ 註解提到「可以之後改成 Bootstrap toast」，但 Bootstrap 已移除
- ❌ 與 Search 頁面的 `showToast()` 不一致（Search 已使用 DaisyUI toast）

**目標實作**（參考 search/ui.js L1024-1097）：
```javascript
function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        console.warn('Toast container not found');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.innerHTML = `
        <div class="flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn btn-sm btn-circle btn-ghost mr-2 m-auto" onclick="this.parentElement.parentElement.remove()">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}
```

**驗證項目**：
1. 儲存成功時顯示綠色 toast（`alert-success`）
2. 儲存失敗時顯示紅色 toast（`alert-error`）
3. Toast 自動消失（3 秒後）
4. 關閉按鈕可手動關閉
5. 多個 toast 可堆疊顯示
6. Toast 樣式與 theme.css `.alert` 一致

### 4. Bootstrap JS 依賴檢查

**檢查結果**：
```bash
# HTML 中無 Bootstrap JS 依賴
grep -n "data-bs-toggle\|data-bs-target\|bootstrap\.Collapse\|bootstrap\.Dropdown" web/templates/settings.html
# 結果：無匹配

# JS 中無 Bootstrap JS 依賴
grep -rn "bootstrap\.Collapse\|bootstrap\.Dropdown" web/static/js/pages/settings/
# 結果：無匹配（只有註解提到 Bootstrap toast）
```

**結論**：
- ✅ Settings 完全使用 Alpine.js 處理互動，無 Bootstrap JS 依賴
- ⚠️ `showToast()` 函數註解誤導（「改成 Bootstrap toast」），需更新為「DaisyUI toast」

## 技術要點

### 1. Alpine.js Collapse vs x-show

**當前使用**：`x-show` + `x-transition`

```html
<div x-show="expanded" x-transition class="collapsible-content">
```

**Alpine.js x-collapse**（更推薦）：
```html
<div x-show="expanded" x-collapse class="collapsible-content">
```

**差異**：
- `x-transition`：fade in/out 動畫，無高度動畫
- `x-collapse`：高度動畫（smooth expand/collapse），更符合 collapsible 語義

**建議**：維持 `x-transition`（Design System 已採用，視覺效果一致）

### 2. Variable Dropdown 定位問題

**潛在風險**：
- `.variable-menu` 使用 `position: relative`（theme.css L1499），可能被父容器 `.card` 裁剪
- 需驗證在收合區塊（collapsible-content）內的 dropdown 是否正常顯示

**對策**：
- 若發現裁剪問題，改用 `position: absolute` + portal 技術（Alpine.js teleport）
- 或修改 `.card` 的 `overflow: visible`（settings.html L42 已設定）

### 3. Toast Container 位置

**需新增**：settings.html 缺少 toast container（Search 有 `#toastContainer`）

```html
<!-- 在 settings.html 最底部，</form> 之後新增 -->
<div id="toastContainer" class="toast toast-end toast-top" style="z-index: 9999;"></div>
```

**位置**：`toast-end toast-top`（右上角，與 DaisyUI 預設一致）

### 4. Theme.css Scoped 樣式驗證

**Scope ID**：`#settings-components`（settings.html L70）

**需驗證的 selector**（theme.css L1308-1710）：
- `#settings-components .settings-form-group`（L1311）
- `#settings-components .settings-label`（L1319）
- `#settings-components .collapsible-trigger`（L1393）
- `#settings-components .variable-menu`（L1499）
- `#settings-components .btn-variable`（L1468）
- `#settings-components .folder-preview`（L1600）

**檢查方式**：
1. 開啟 DevTools，選擇元素
2. 確認 theme.css 的樣式有應用（不是被 page CSS 覆蓋）
3. 確認 CSS 變數（`var(--accent)`、`var(--text-primary)` 等）解析正確

## 驗證方式

### 1. Collapse 區塊測試

#### 1.1 基礎互動
- [ ] 點擊「進階刮削設定」，內容展開（動畫流暢）
- [ ] 點擊「進階顯示選項」，內容展開（動畫流暢）
- [ ] 展開狀態下再次點擊，內容收合
- [ ] Chevron 圖標旋轉 180° 動畫正常

#### 1.2 樣式驗證
- [ ] 觸發器背景色：`color-mix(in oklch, var(--color-base-content) 2%, transparent)`
- [ ] Hover 效果：背景色變深到 3%
- [ ] 內容區邊框：`1px solid var(--border-light)`
- [ ] 內容區背景：`color-mix(in oklch, var(--color-base-content) 3%, transparent)`

#### 1.3 主題切換
- [ ] Light 模式：背景色正常
- [ ] Dim 模式：切換後背景色正常（無閃爍）

#### 1.4 無障礙
- [ ] `aria-expanded` 屬性動態更新（true/false）
- [ ] 鍵盤 Enter/Space 可觸發展開/收合
- [ ] Screen reader 正常讀取狀態

### 2. 變數插入 Dropdown 測試

#### 2.1 基礎互動
- [ ] 點擊「檔案命名格式」右側「變數」按鈕，dropdown 顯示
- [ ] 點擊外部區域，dropdown 關閉
- [ ] 點擊變數項目（如 `{num}`），變數插入到 input
- [ ] 游標位置正確（插入點在游標位置，不是結尾）

#### 2.2 多層資料夾連動
- [ ] **初始狀態**：「建立資料夾」未勾選，三層全 disabled
- [ ] 勾選「建立資料夾」，內層啟用（外層/中層 disabled）
- [ ] 內層輸入 `{num}`，中層啟用（外層 disabled）
- [ ] 中層輸入 `{actor}`，外層啟用
- [ ] 清空中層，外層自動 disabled + 清空
- [ ] 清空內層，中層自動 disabled + 清空

#### 2.3 即時預覽
- [ ] 初始預覽：`SSNI-618/[SSNI-618][SOD] 絕對領域.mp4`
- [ ] 修改檔案命名格式，預覽即時更新
- [ ] 修改資料夾層級，預覽即時更新
- [ ] 取消「建立資料夾」，預覽只顯示檔名（無路徑）

#### 2.4 Dropdown 顯示
- [ ] Dropdown 不被 `.card` 裁剪
- [ ] Dropdown 不被收合區塊（collapsible-content）裁剪
- [ ] Dropdown z-index 正確（不被其他元素遮擋）
- [ ] 變數列表滾動正常（max-height: 300px，theme.css L1505）

#### 2.5 樣式驗證
- [ ] 變數按鈕顏色：`color: var(--accent)`
- [ ] 變數按鈕背景：`color-mix(in oklch, var(--accent) 10%, transparent)`
- [ ] Hover 效果：背景色變深到 15%
- [ ] 變數項目 hover：背景色 `color-mix(in oklch, var(--color-base-content) 2%, transparent)`
- [ ] 變數名稱（code）顏色：`var(--accent)`

### 3. Toast 通知測試

#### 3.1 儲存成功
- [ ] 修改設定 → 點擊「儲存設定」
- [ ] 顯示綠色 toast：「設定已儲存」
- [ ] Toast 3 秒後自動消失
- [ ] 關閉按鈕可手動關閉

#### 3.2 儲存失敗
- [ ] 模擬 API 錯誤（斷網或修改 core.js）
- [ ] 顯示紅色 toast：「儲存失敗: {錯誤訊息}」
- [ ] Toast 3 秒後自動消失
- [ ] 關閉按鈕可手動關閉

#### 3.3 多個 Toast
- [ ] 快速儲存多次（製造多個 toast）
- [ ] Toast 堆疊顯示（不重疊）
- [ ] 每個 toast 獨立倒數消失

#### 3.4 樣式驗證
- [ ] Toast 容器位置：右上角（`toast-end toast-top`）
- [ ] 成功 toast：`alert-success`（綠色）
- [ ] 錯誤 toast：`alert-error`（紅色）
- [ ] 關閉按鈕：圓形 ghost 按鈕 + X 圖標
- [ ] z-index: 9999（不被其他元素遮擋）

### 4. 整合測試

#### 4.1 完整儲存流程
- [ ] 修改「主題模式」 → 儲存 → Toast 顯示 → 刷新頁面 → 設定保留
- [ ] 修改「檔案命名格式」 → 儲存 → Toast 顯示 → 刷新頁面 → 設定保留
- [ ] 修改「資料夾層級」 → 儲存 → Toast 顯示 → 刷新頁面 → 設定保留

#### 4.2 主題切換
- [ ] Light 模式：所有元件（collapsible、dropdown、toast）顏色正常
- [ ] Dim 模式：切換後所有元件顏色正常
- [ ] 無佈局跳動或閃爍

#### 4.3 Console 檢查
- [ ] 無紅色 Error（特別是 Alpine.js 相關）
- [ ] 無 Warning（特別是 CSS class 找不到）
- [ ] 無 404（CSS/JS 資源載入成功）

### 5. 自動化測試

```bash
# Settings API 測試
source venv/bin/activate && pytest tests/integration/test_api_config.py -v

# 預期：全部通過（M4c 只改 JS 邏輯，API 不變）
```

## 修復清單

### Fix 1: Toast 函數改為 DaisyUI

**檔案**：`/home/peace/OpenAver/web/static/js/pages/settings/core.js`

**修改前**（L252-259）：
```javascript
function showToast(message, type = 'info') {
    // 簡單的 alert，可以之後改成 Bootstrap toast
    if (type === 'success') {
        alert(message);
    } else {
        alert('錯誤: ' + message);
    }
}
```

**修改後**：
```javascript
function showToast(message, type = 'success') {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) {
        console.warn('Toast container not found');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.innerHTML = `
        <div class="flex items-center gap-2">
            <span class="flex-1">${message}</span>
            <button type="button" class="btn btn-sm btn-circle btn-ghost" onclick="this.parentElement.parentElement.remove()">
                <i class="bi bi-x"></i>
            </button>
        </div>
    `;

    toastContainer.appendChild(toast);

    // 3 秒後自動移除
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 3000);
}
```

**說明**：
- 使用 DaisyUI `.alert` 元件（`alert-success`、`alert-error`）
- 關閉按鈕改用 `.btn-circle` + `.btn-ghost`（與 Search 頁面一致）
- 自動消失時間 3 秒（與 Search 頁面一致）

### Fix 2: 新增 Toast Container

**檔案**：`/home/peace/OpenAver/web/templates/settings.html`

**位置**：在 `</form>` 之後、`</div>` 之前（L527 附近）

**新增內容**：
```html
<!-- Toast 通知容器 -->
<div id="toastContainer" class="toast toast-end toast-top" style="z-index: 9999;"></div>
```

**說明**：
- DaisyUI toast 容器必須手動建立（不像 Bootstrap 有全域 toast）
- `toast-end toast-top`：右上角位置
- z-index 9999：確保在所有元素之上

### Fix 3: 調整 Toast 呼叫（可選）

**檔案**：`/home/peace/OpenAver/web/static/js/pages/settings/core.js`

**修改前**（L196）：
```javascript
showToast('儲存失敗: ' + result.error, 'danger');
```

**修改後**：
```javascript
showToast('儲存失敗: ' + result.error, 'error');
```

**說明**：
- DaisyUI 使用 `alert-error`（不是 `alert-danger`）
- 統一 type 參數為 `'success'` 或 `'error'`

## 完成條件

### 必要條件
- [ ] Collapse 區塊展開/收合動畫流暢（2 個區塊都測試）
- [ ] Chevron 圖標旋轉 180° 動畫正常
- [ ] 變數插入 dropdown 顯示/關閉正常
- [ ] 變數點擊後正確插入到 input（游標位置正確）
- [ ] 多層資料夾連動啟用邏輯正常（3 層測試）
- [ ] 即時預覽路徑更新正常
- [ ] Toast 顯示成功/失敗訊息（綠色/紅色）
- [ ] Toast 自動消失（3 秒）+ 手動關閉按鈕正常
- [ ] `showToast()` 改為 DaisyUI toast（移除 `alert()`）
- [ ] Toast container 已新增到 HTML
- [ ] Light / Dim 主題切換正常（所有元件）
- [ ] 無 console error / warning（特別是 Alpine.js 相關）
- [ ] pytest 通過（`test_api_config.py`）
- [ ] 手動 UI 驗證 Checklist 全部勾選

### 加分條件
- [ ] Dropdown z-index 正常（不被其他元素遮擋）
- [ ] 無障礙測試通過（`aria-expanded`、鍵盤操作）
- [ ] 多個 toast 堆疊顯示正常
- [ ] 視覺效果與 `/design-system/settings-components.html` 一致

## 風險與對策

| 風險 | 可能性 | 影響 | 對策 |
|------|--------|------|------|
| Alpine.js 版本不支援 `x-collapse` | 低 | 中 | 維持 `x-transition`（Design System 已採用） |
| Dropdown 被 `.card` 裁剪 | 中 | 中 | settings.html L42 已設 `overflow: visible`，若仍裁剪則改用 Alpine teleport |
| Toast container z-index 不足 | 低 | 中 | 設 z-index: 9999，若仍被遮擋則檢查父元素 z-index |
| `showToast()` type 參數不一致 | 低 | 低 | 統一使用 `'success'` / `'error'`（不用 `'danger'`）|
| Alpine.js 未載入（CDN 失敗） | 極低 | 高 | base.html 使用 CDN + integrity，若失敗需 fallback 到本地檔案 |
| theme.css scope 樣式未應用 | 低 | 中 | 檢查 settings.html L70 是否有 `id="settings-components"` |
| 變數插入游標位置錯誤 | 低 | 中 | format.js L32-37 已處理 `selectionStart`，若錯誤需檢查 textarea focus 狀態 |

## 參考檔案

| 檔案 | 路徑 | 用途 |
|------|------|------|
| settings.html | `/home/peace/OpenAver/web/templates/settings.html` | 主要驗證目標（HTML） |
| core.js | `/home/peace/OpenAver/web/static/js/pages/settings/core.js` | 修改目標（showToast 函數） |
| format.js | `/home/peace/OpenAver/web/static/js/pages/settings/format.js` | 驗證目標（變數插入邏輯） |
| theme.css (L1308-1710) | `/home/peace/OpenAver/web/static/css/theme.css` | Settings scoped 樣式規格 |
| settings-components.html | `/home/peace/OpenAver/web/templates/design_system/settings-components.html` | Design System 規格（D.9a/D.9b/D.9c） |
| search/ui.js (L1024-1097) | `/home/peace/OpenAver/web/static/js/pages/search/ui.js` | Toast 實作參考 |
| TASK-M3a.md | `/home/peace/OpenAver/feature/24-migrate/TASK-M3a.md` | Search 遷移參考（template） |
| Alpine.js Docs | https://alpinejs.dev/directives/show | `x-show`、`x-transition`、`x-collapse` 文檔 |
| DaisyUI Alert | https://daisyui.com/components/alert/ | Alert 元件用法 |
| DaisyUI Toast | https://daisyui.com/components/toast/ | Toast 容器佈局 |
