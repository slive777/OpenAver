# E2E 用戶旅程劇本（v2 — 2026-05-14 align 後）

> 純文字劇本，**人類用瀏覽器手動 / AI 用 Playwright MCP** 皆可照跑。
> 對應 spec：`feature/59-onboarding-help-polish/spec-59.md` §8 + plan-59c.md
> **AI 首次操作前先讀 `app-guide.md`**（同目錄）了解各頁面操作方式。

---

## 執行方式

### Server 啟動

```bash
source venv/bin/activate && uvicorn web.app:app --host 0.0.0.0 --port 8000
```

### Playwright MCP Server 選擇

| Server | 用途 | 啟動方式 |
|--------|------|---------|
| `playwright`（headless） | Clean state 跑（無 cache）；CI-like 一致性；建議 US1–US4 用 | 已在 MCP config |
| `playwright-cdp`（CDP attach） | 視覺確認、需看動畫（US3 constellation / US5 photo enrichment）；共享 Chrome 已登入狀態 | Chrome 啟動加 `--remote-debugging-port=9222` |

**Risk-2 — Cache 黏性**：CDP attach 模式會沿用 Chrome ESM module map cache；改 JS 模組後 e2e 跑前用 Incognito 視窗或切 headless server。

### 執行時機

| 時機 | 範圍 | 時間 |
|------|------|------|
| Milestone pre-merge | US1–US7 全套（外部 API 失敗 skip 並記原因） | 10–20 分 |
| Release 前 | US1–US7 全套（保險） | 10–20 分 |
| Feature branch 含 template 改動 | 受影響的 US（1–2 個） | 5 分內 |

---

## 前置條件（所有 US 共通）

- Dev server 已啟動於 `http://localhost:8000`
- DB 已有至少 10 部影片（US3–US7 需要）
- 4 locale 翻譯檔齊全（US6 需要）
- Settings 已有預設搜尋來源（US7 需要）

每個 US 在 Setup 段列獨立重置指令；US 之間 state 殘留處置見 plan-59c §7 Risk-3。

---

## US1: 新手 Onboarding

> _T59c-2 待補完_

---

## US2: Search → 整理 → 即時上架

> _T59c-3 待補完_

---

## US3: Showcase 瀏覽 + Lightbox + 魔杖探索

> _T59c-3 待補完_

---

## US4: 跨語言 Tag Alias 篩選

> _T59c-4 待補完_

---

## US5: 女優最愛流

> _T59c-4 待補完_

---

## US6: i18n 完整切換

> _T59c-5 待補完_

---

## US7: 控制狂工作流（進階分流）

> _T59c-5 待補完_

---

## Appendix C: Capabilities Smoke（Optional, curl-only）

> _T59c-5 待補完_

---

## ~~舊版 Scenarios（2026-05-14 前）~~ [歷史保留]

> 以下 24 個 scenarios（v1 格式 S/C/T/H/N/X/A）已在 2026-05-14 plan-59c §2 審計後，
> 全數合併進 US1–US7 或標 deprecated。逐項處置原因見下表，原 step 內容已在
> git history（commit before 59c-1）保留，本檔不再重複文字。

### Search

- ~~**S1. 番號精準搜尋**~~ → 併入 US2 step 1–3
- ~~**S2. Detail 模式欄位顯示**~~ → 併入 US2 Sub-A（detail card render 驗收）
- ~~**S3. 方向鍵導航**~~ → 併入 US2 Sub-B（多筆 query 才執行，`N >= 2` 條件）
- ~~**S4. 女優名搜尋**~~ → 併入 US5 step 1–2
- ~~**S5. 拖入檔案/加入檔案**~~ → **deprecated**（PyWebView-only：drag-drop 觸發 file dialog 無法 browser 跑；US2 setup 以「預設已有番號」繞過）

### Showcase

- ~~**C1. 頁面載入 + 卡片渲染**~~ → 併入 US3 step 1
- ~~**C2. 搜尋篩選**~~ → 併入 US4 step 1–2
- ~~**C3. 翻頁**~~ → 併入 US3 step 2（atomic inline）
- ~~**C4. Lightbox**~~ → 併入 US3 step 3–5（含魔杖按鈕補強）

### Settings

- ~~**T1. 語系切換**~~ → 併入 US6 step 1–3
- ~~**T2. Dark / Light Mode**~~ → 保留為獨立 step in US6 step 5
- ~~**T3. 搜尋來源切換**~~ → 併入 US7 step 2
- ~~**T4. 翻譯開關**~~ → 併入 US7 step 3

### Help

- ~~**H1. 頁面載入**~~ → 併入 US1 step 9–10（tutorial 完成後從 sidebar 連 `/help`，驗 `h2.card-title` 非 raw i18n key + `.terminal-copy-btn` 可見）
- ~~**H2. AI curl 複製**~~ → 保留為 US7 末尾 step（capabilities curl 複製）

### Scanner

- ~~**N1. 頁面載入**~~ → 併入 US1 step 1（tutorial 觸發前導覽至 Scanner 頁）
- ~~**N2. 掃描 + 產生網頁**~~ → **deprecated**（PyWebView-only：Scanner 加資料夾依賴原生 picker，瀏覽器無法穩定驅動；scan trigger button 可由實作者選做 atomic check）

### 跨頁面

- ~~**X1. Sidebar 導航**~~ → **deprecated**（US1 step 5–7 已逐一 sidebar 導航，獨立 scenario 冗餘）
- ~~**X2. 頁面間狀態不互相污染**~~ → 保留為 Regression 偵測點 in US2 / US3

### Agentic API

- ~~**A1. 探索搜尋**~~ → 移至 Appendix C（API-only / curl）
- ~~**A2. 批量搜尋**~~ → 移至 Appendix C
- ~~**A3. 補完 metadata**~~ → 移至 Appendix C（寫 DB，需 disposable fixture）
- ~~**A4. 收藏庫查詢**~~ → 移至 Appendix C
- ~~**A5. 生成 HTML 清單**~~ → 移至 Appendix C（寫檔，需 disposable fixture 或暫目錄）

> **CD-59-23**：scenarios 不重複 integration 已測的單端點 contract；A1–A5 維持 curl/API 格式不轉成 browser step，移出 US7 主體放 Appendix C，不算 milestone 必跑。
