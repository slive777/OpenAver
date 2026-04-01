# OpenAver App 操作指南（AI + Playwright MCP 用）

> 跑 e2e-scenarios.md 前先讀本文件。描述各頁面的操作方式和注意事項。

---

## 通用

### 啟動
```bash
python -m web.app  # http://localhost:8000
```

### Sidebar 導航
- 點擊左上 hamburger button 開啟
- 5 個連結：搜尋(/search)、列表生成(/scanner)、瀏覽(/showcase)、說明(/help)、設定(/settings)

### Alpine State 存取
```javascript
// 取得頁面 Alpine component 資料
const container = document.querySelector('.search-container[x-data]');  // search 頁
const container = document.querySelector('.showcase-container[x-data]'); // showcase 頁
const data = Alpine.$data(container);
```

### 等待時間建議
- 番號搜尋（SSE）：8-15 秒（視來源回應速度）
- 女優名搜尋：15-30 秒（多筆結果陸續到達）
- 頁面導航：1-2 秒（含動畫）
- 語系切換：頁面會 reload，等 2 秒

---

## Search 頁 (/search)

### 搜尋框
- `textbox "搜尋番號、女優或拖入檔案..."` — 填入後按 Enter 送出
- 搜尋框右邊有清空按鈕（×）和送出按鈕（→），注意不要點錯
- **送出推薦用 Enter**，比點按鈕可靠

### 兩種顯示模式
| 模式 | 觸發條件 | 行為 |
|------|---------|------|
| **Detail** | 單筆結果（精準番號搜尋） | 自動進入，顯示封面 + 完整欄位 |
| **Grid** | 多筆結果（模糊搜尋、女優名搜尋） | 卡片 grid，點擊卡片開 Lightbox（不是切 Detail） |

- 切換模式：按鍵盤 `A` 或點擊工具列的切換按鈕
- `Alpine.$data(container).displayMode` 可查目前模式（`'detail'` 或 `'grid'`）

### Detail 模式操作
- **方向鍵導航**：ArrowRight/ArrowLeft 切換影片
- **前提**：搜尋框必須 **blur**（`document.activeElement.blur()`），否則方向鍵被輸入框吃掉
- 導航指示器 `#navIndicator` 顯示 `1/20+` 格式
- 番號顯示在 `#resultNumber`

### Grid 模式操作
- 點擊卡片封面 → 開啟 Lightbox（非切換到 Detail）
- 要測方向鍵導航，先切到 Detail 模式

### 欄位讀取（Detail 模式）
```javascript
// 取得所有 info-row 的 label 和 value
document.querySelectorAll('.info-row').forEach(row => {
  const label = row.querySelector('.info-label')?.textContent?.trim();
  const value = row.querySelector('.info-value')?.textContent?.trim();
});
```
常見欄位：演員、發行日期、片商、導演、片長、發行商、系列、標籤

### Sample Gallery
- Detail 模式下，若有 sample images，`.sample-strip` 可見
- 點擊縮圖 `.sample-thumb-btn` → 開啟 Gallery
- Gallery 開啟時方向鍵控制翻圖（不是切影片）
- ESC 關閉 Gallery，回到 Detail 模式

### SSE 搜尋注意事項
- 搜尋是 SSE 串流，結果陸續到達
- `#resultCount` 或搜尋結果數會隨時間增加
- 等到搜尋完成（進度條消失）再做後續操作最可靠

---

## Showcase 頁 (/showcase)

### 基本資訊
- 顯示 DB 中所有影片，支援搜尋、篩選、排序
- 頁面文字包含「共 N 部影片」和分頁 `1 / 23`

### 操作
- 搜尋框：輸入番號或女優名篩選
- 翻頁：「上一頁 ←」「→ 下一頁」按鈕
- Grid/List 切換：工具列按鈕
- 點擊卡片 → 開啟 Lightbox

### 鍵盤快捷鍵
- `A`：切換顯示模式
- `S`：顯示/隱藏資訊
- `←` `→`：翻頁
- `ESC`：關閉 Lightbox

---

## Settings 頁 (/settings)

### 語系切換
- `.locale-toggle-btn` 按鈕，循環：繁 → 简 → あ → EN → 繁
- 點擊後頁面 **reload**，標題會隨語系變化（設定/设置/設定/Settings）
- 有 dirty-check 保護：若有未儲存的設定變更，會先提示儲存

### Dark / Light Mode
- 右上角太陽/月亮圖示
- 切換後立即生效，設定持久化

### 搜尋來源
- 預設搜尋來源 badge 列表（DMM、JavBus、Jav321、JavDB 等）
- 點擊 badge 切換啟用/停用，綠色邊框 = 啟用
- DMM 需要 Proxy 設定才能使用

### 設定項目
- 女優畫廊模式（Beta toggle）
- 無碼模式（toggle）
- Proxy 位址 + 測試按鈕
- 我的最愛資料夾路徑
- 啟用標題翻譯（toggle）

---

## Help 頁 (/help)

- 版本號顯示在頂部 Hero Card
- AI curl 複製按鈕在 `$ curl -s http://localhost:8000/api/capabilities` 旁
- 頁面內容包含功能說明（搜尋、刮削、設定等區塊）

---

## Scanner 頁 (/scanner)

- 掃描資料夾列表（已設定的路徑）
- 「產生網頁」按鈕觸發掃描 + HTML 生成
- 快取影片數顯示
- **加入資料夾需要 PyWebView file dialog，Playwright MCP 無法觸發**

---

## Agentic AI API 使用

任何 AI agent 只需讀取 `GET /api/capabilities` 即可學會使用 OpenAver API。

```bash
curl -s http://localhost:8000/api/capabilities | jq .
```

**經驗證可用的輕量模型**：Haiku、Gemini Flash、GPT-4o Mini — 不需要 Opus/Sonnet。Capabilities 的 tool description 足夠清晰，輕量模型能正確選對 endpoint、組合參數、解讀回傳。

---

## Playwright MCP 限制

| 功能 | MCP 可做 | 需人工 |
|------|:---:|:---:|
| 頁面導航、點擊、填表、鍵盤 | ✓ | |
| 截圖、snapshot、讀 DOM | ✓ | |
| File dialog（加入檔案/資料夾） | | ✓ |
| Drag-drop 檔案 | | ✓ |
| PyWebView 原生 API | | ✓ |
| DMM 相關（需日本 IP proxy） | 需 proxy context | |
