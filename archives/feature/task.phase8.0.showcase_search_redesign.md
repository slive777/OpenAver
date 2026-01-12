# Task: Showcase 頁面搜尋框樣式統一

## 目標

將 `/showcase` 頁面（由 `gallery_generator.py` 產生）的搜尋框設計與 `/search` 頁面統一，並將左側標題從 "OpenAver Gallery" 簡化為 "OpenAver"。

---

## 現況分析

### /showcase (Gallery 頁) - 現行設計

**HTML 結構** (`gallery_generator.py` 行103-115):
```html
<header class="header">
  <div class="header-inner">
    <div class="logo">OpenAver Gallery</div>  <!-- 標題需簡化為 OpenAver -->
    <div class="search-box">
      <form>
        <input type="text" name="sw" placeholder="搜尋影片..." />
        <button class="reset-btn">✕</button>
        <button type="submit">🔍</button>
      </form>
    </div>
    <div class="controls" id="controls"></div>
  </div>
</header>
```

**CSS 樣式** (`gallery_generator.py` 內嵌 CSS 行893-954):
- 傳統方形搜尋框 + 圓角 (`border-radius: var(--radius-md)`)
- 搜尋按鈕左右排列
- 重置按鈕使用 `✕` 符號
- 搜尋按鈕使用 `🔍` emoji

---

### /search 頁 - 目標設計

**HTML 結構** (`search.html` 行25-42):
```html
<div class="spotlight-search">
  <i class="bi bi-search search-icon-left"></i>
  <input type="text" placeholder="搜尋番號、女優或拖入檔案..." />
  <div class="search-actions-right">
    <button type="button" class="btn-icon d-none" title="清空">
      <i class="bi bi-x-lg"></i>
    </button>
    <button type="submit" class="btn-icon active" title="搜尋">
      <i class="bi bi-arrow-right"></i>
    </button>
  </div>
</div>
```

**CSS 樣式** (`theme.css` 行229-288):
- 膠囊藥丸形 (`border-radius: 999px`)
- 左側 Bootstrap Icons 搜尋圖示
- 右側圓形按鈕群組
- 更大的高度 (`3.5rem` vs 傳統設計約 `2.5rem`)
- Focus 時微放大動畫 (`transform: scale(1.01)`)

---

## 設計差異對照表

| 項目 | /showcase (現況) | /search (目標) |
|------|------------------|----------------|
| 外框形狀 | 方形 + 圓角 | 膠囊藥丸形 |
| 搜尋圖示 | 🔍 emoji (在按鈕內) | bi-search icon (輸入框左側) |
| 清除按鈕 | ✕ 文字 | bi-x-lg icon |
| 送出按鈕 | 🔍 emoji | bi-arrow-right icon |
| 按鈕位置 | 輸入框右側併排 | 輸入框內右側 (absolute) |
| Focus 效果 | 簡單邊框變色 | 放大 + 陰影擴散 |
| 標題文字 | "OpenAver Gallery" | "OpenAver" (簡化) |

---

## 前置條件檢查

- [x] 確認 `gallery_generator.py` 的 HTML 模板包含 Bootstrap Icons CDN 引入
- [x] 確認 CSS 變數（如 `--radius-md`）與 `theme.css` 相容
- [x] 確認 `/search` 頁的 `.spotlight-search` 樣式可直接複用

---

## 需修改的檔案

### [MODIFY] `core/gallery_generator.py`

1. **`_generate_header()` 方法**：將 `OpenAver Gallery` 改為 `OpenAver`

2. **重寫 `.search-box` HTML 為 `.spotlight-search` 結構**：
   ```html
   <div class="spotlight-search">
     <i class="bi bi-search search-icon-left"></i>
     <form name="form_search" onsubmit="...">
       <input type="text" name="sw" placeholder="搜尋影片..." autocomplete="off" oninput="updateResetBtn()">
       <div class="search-actions-right">
         <button type="button" class="reset-btn btn-icon d-none" onclick="resetSearch()" title="清除">
           <i class="bi bi-x-lg"></i>
         </button>
         <button type="submit" class="btn-icon active" title="搜尋">
           <i class="bi bi-arrow-right"></i>
         </button>
       </div>
     </form>
   </div>
   ```

3. **替換 `.search-box` CSS 為 `.spotlight-search` 樣式**：
   - 膠囊藥丸形外框 (`border-radius: 999px`)
   - 左側搜尋圖示定位
   - 右側按鈕群組 (`position: absolute`)
   - Focus 時微放大動畫 (`transform: scale(1.01)`)

4. **調整 JavaScript 邏輯**：
   - `updateResetBtn()`: 根據輸入框內容切換清除按鈕的 `d-none` class
   - `resetSearch()`: 清空輸入框並隱藏清除按鈕（加上 `d-none`）
   - 確保表單 `onsubmit` 正確觸發過濾邏輯

---

## 驗證計劃

### 自動化驗證
- 無現有自動化測試

### 手動驗證

#### UI 檢查
- [x] 搜尋框為膠囊藥丸形
- [x] 標題顯示 "OpenAver"（非 "OpenAver Gallery"）
- [x] 左側有 Bootstrap Icons 搜尋圖示

#### 功能測試
- [x] 輸入文字 → 清除按鈕出現
- [x] 點擊清除按鈕 → 輸入框清空 + 按鈕隱藏
- [x] 按 Enter 鍵 → 正確觸發過濾
- [x] 點擊搜尋按鈕 → 正確觸發過濾

#### 樣式測試
- [x] Light Mode 顯示正常
- [x] Dark Mode 顯示正常
- [x] Focus 時有微放大動畫效果

---

## 狀態

- [x] 研究完成
- [x] 程式碼修改
- [x] 驗證完成
