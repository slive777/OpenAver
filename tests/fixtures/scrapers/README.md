# Scraper fixtures

## 為什麼這裡不再收真站 HTML

owner 2026-08-15 拍板（TASK-118a-T13）：「除非 canary 發現然後我手動測試確實連不上，
不然根本不會去改爬蟲部份的 code。判斷要改爬蟲的 code 唯一依據就是 canary 多次 NG 我也
實測用不了，這時候會開著網站讓你用 chrome gui 比較 code 和網站實際結構。」

在這個工作模型下，「餵一份本地 HTML/JSON 進 parser、斷言解析出哪些欄位」這類測試**抓
不到任何東西**：站方改版時本地真檔還是舊結構，測試照樣全綠、線上全滅；而真的要修
parser 的那一刻，這批測試是因為餵的是舊結構而轉紅，第一件事就是刪掉它們重寫。
**它們在唯一會發生的路徑上扮演的是摩擦，不是防線。**

歷史佐證（`git log core/scrapers/`）：近三個月 62 顆 commit，真正的解析 bug 全部是外部
打出來的，沒有一次是離線測試抓到的——
- `7480bd12` HEYZO 站方把 JSON-LD 改成 JS 執行期注入 → 解析全滅（離線測試當時全綠）
- `a61d77d6` jav321 空 `col-md-12` 佔位 → Codex 讀**真 fixture** 抓到
- `7ce9255d` javbus `&type=1` → 三方實證 ＋ live

因此本目錄**不再收任何真站 HTML / JSON**。2026-10-10 刪掉最後一批（157 的 `xcity_*.html` 4 份、
164 的 `tests/fixtures/custom_sources/*.html` 11 份），`.gitignore` 也拿掉了對本目錄 `*.html` 的
例外——`tests/` 下的 HTML 預設不進版控，要加就得改 `.gitignore`，review 看得到。
剩下的 `dmm_crawl_groups.json` 驗的是**我們出貨的** DMM 對照表，不是站方結構。站台健康度改由 owner 手動跑的活站 canary
承擔；爬蟲層在 CI 的自動覆蓋只留檔名／dispatcher／聚合層／契約守衛。

`core/scrapers/fc2_javten.py`（來源 id `fc-javten`）與 `javlibrary` 另有 CF 擋在前面
（`curl_cffi` 三種 impersonate 實測全 403），結構上也不可能做 canary——這兩條來源的
迴歸偵測只能靠真實使用者回報。

> **不要用合成 HTML 補回解析驗證。** 合成 HTML 會抹平空佔位與 null，那是假綠——
> `v0.11.8` 就是這樣讓 Codex 抓到 3 條 bug。要嘛真檔要嘛沒有。

### 行尾／eol 說明（歷史慣例，若日後再收真檔仍適用）

> **行尾會被正規化，這是預期的**：`.gitattributes:9` 的 `*.html text eol=lf` 對本目錄照樣生效
> （`tests/fixtures/**/*.html -whitespace` 只關掉 `git diff --check` 的尾空白告警，**沒有**關掉 eol 轉換）。
> 站方送的是 CRLF，進版控後是 LF。**這不是「被 reformat」**：
> BE-ENV-04 在乎的尾空白**逐行保留**，且實測解析結果逐欄位相同。
> 118b 的 `fc2official_*` 當初就是這樣進來的（`a_4938576.html` 3 行 CRLF → 進版控少 3 bytes），已出貨驗證過。
> **加新 fixture 時直接 `cp`，不要為了「保住 CRLF」去動 `.gitattributes`**——那會讓本目錄長出第二套慣例。

---

## 站台事實（與檔案存不存在無關，後人不必重跑 POC）

### 官方站軟 404（CD-118b-4 判準依據，2026-08-13 實測）

不存在的 FC2 番號（例如 `FC2-PPV-1723985`）在 `adult.contents.fc2.com` 回 **HTTP 200**
軟 404，頁面約 **31,403 bytes**，與另一份不存在番號（`s_3000000.html`）**位元組數完全
相同**。後人不必重跑 POC 即可用此事實。

### javten 機翻咬的是標籤，不是標題（2026-08-14 實測）

同一片日文版標籤是 `['ハメ撮り','制服','素人',…]`，`/tw/` 版是 `['奇聞趣事','均勻','業餘',…]`，
而**標題兩邊都是日文原題**。所以「有沒有拿到日文版」的可證偽點只能放在標籤。

### javten 日文版 URL 契約（CD-118a-19 的依據，2026-08-14 實測）

- 日文版 ＝ **無語言段 ＋ 必須帶標題 slug**：`/video/{內部id}/id{番號}/{slug}`
- **`/ja/` 是 404**；**少了 slug 是 500**；`/video/{亂數id}/id{番號}` 是 404（內部 id 躲不掉）
- 命中 → 從 `/search?kw=N` **302 到** `/video/\d+/id<番號>/…`；查無 → **不重導**，停在 `/search?kw=N`（title `Search For : N`）
- **判準用最終 URL 的形狀，不偵測任何文案字串**

### javten 解析結果與 owner 既有 DB 逐欄相同（2026-08-14 實測三顆已下架片）

標題／`maker`／`tags` 逐字相符，`rating` 皆 5.0、`samples` 皆 5 張——
**這證明庫裡的 FC2 資料當初就是從這條日文路徑抓的**，解析器對得上真實資料。

### javten 站方沒有發售日（2026-08-14 實測）

整份 HTML 中 `販売日`／`発売日` 出現 **0 次**。`fc-javten` 結構性拿不到發售日（官方站有）。
不要試圖從別處推導——那會寫一個編出來的日期進 NFO。

### 官方站欄位契約（CD-118b，2026-08-13 實測）

- **CD-118b-3**：`og:title` 會截斷，JSON-LD `name` 才是完整標題
- **CD-118b-5／6／9**：標籤 scope、兩個 softDevice、劇照兩種寬度
- **CD-118b-7**：`reviewCount`／`ratingValue` 從 JSON-LD 取
- **CD-118b-8**：JSON-LD image 可能是 `http://`（需升成 https）
