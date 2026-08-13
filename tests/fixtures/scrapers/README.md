# Scraper fixtures — FC2 兩條來源

FC2 有兩個 scraper，fixture 依前綴分開：

| 前綴 | 站台 | scraper |
|------|------|---------|
| `fc2official_` | `adult.contents.fc2.com`（官方） | `core/scrapers/fc2_official.py`（來源 id `fc2`） |
| `fcjavten_` | `javten.com`（備份鏡像） | `core/scrapers/fc2_javten.py`（來源 id `fc-javten`）※ 由 plan-118a T3 接管 |

來源：`feature/118-fc2-dual-source/poc-artifacts/`（POC 當日 byte-faithful 複製；不得 reformat / strip 尾空白）。

> **行尾會被正規化，這是預期的**：`.gitattributes:9` 的 `*.html text eol=lf` 對本目錄照樣生效
> （`tests/fixtures/**/*.html -whitespace` 只關掉 `git diff --check` 的尾空白告警，**沒有**關掉 eol 轉換）。
> 站方送的是 CRLF，進版控後是 LF。**這不是「被 reformat」**：
> BE-ENV-04 在乎的尾空白**逐行保留**，且實測解析結果逐欄位相同
> （`fcjavten_4938117`：移除 992 個 CR、29 行尾空白全留、標題／片商／標籤／圖片數／`text_content()` 長度皆不變）。
> 118b 的 `fc2official_*` 當初也是這樣進來的（`a_4938576.html` 3 行 CRLF → 進版控少 3 bytes），已出貨驗證過。
> **加新 fixture 時直接 `cp`，不要為了「保住 CRLF」去動 `.gitattributes`**——那會讓本目錄長出第二套慣例。

## 官方站（`fc2official_`）

| 檔名 | 番號 | 抓取日期 | 當時官方是否仍上架 | 守的是哪條 CD |
|------|------|----------|-------------------|---------------|
| `fc2official_4938576.html` | FC2-PPV-4938576 | 2026-08-13 | 仍上架 | CD-118b-3（og:title 截斷、JSON-LD `name` 完整） |
| `fc2official_4938582.html` | FC2-PPV-4938582 | 2026-08-13 | 仍上架 | CD-118b-5／6／9（標籤 scope、兩個 softDevice、劇照兩種寬度） |
| `fc2official_1723984.html` | FC2-PPV-1723984 | 2026-08-13 | 仍上架 | CD-118b-7 正向側（`reviewCount=72`、`ratingValue=5`）＋ CD-118b-8（JSON-LD image 為 `http://`） |
| `fc2official_1723985_notfound.html` | FC2-PPV-1723985 | 2026-08-13 | 不存在的番號（HTTP 200 軟 404） | CD-118b-4／5（HTTP 200 軟 404、20 個假標籤） |

### 軟 404 事實（CD-118b-4 判準依據）

`fc2official_1723985_notfound.html`（來源 `s_1723985.html`）是 **HTTP 200** 的軟 404，**31,403 bytes**，與另一份不存在番號的頁面（`s_3000000.html`）**位元組數完全相同**。後人不必重跑 POC 即可用此事實。

## javten 鏡像站（`fcjavten_`）

**這三顆片的存在意義：官方站已經沒有它們了。** `fc-javten` 這條來源存在的唯一理由就是補這一塊，
所以 fixture 刻意全部挑「官方已下架」的片——用還在官方站的片當 fixture，測不出這條來源的價值。

| 檔名 | 番號 | 抓取日期 | 抓取當時官方站是否仍有 | 頁面語言 | 用途 |
|------|------|----------|----------------------|---------|------|
| `fcjavten_4914771.html` | FC2-PPV-4914771 | 2026-08-14 | **已下架** | **日文**（無語言段） | AC-2.2／AC-2.3 主檔 |
| `fcjavten_4938117.html` | FC2-PPV-4938117 | 2026-08-14 | **已下架** | **日文**（無語言段） | 同上 |
| `fcjavten_4938221.html` | FC2-PPV-4938221 | 2026-08-14 | **已下架** | **日文**（無語言段） | 同上 |
| `fcjavten_4914771_tw.html` | FC2-PPV-4914771 | 2026-08-14 | **已下架** | 繁中（`/tw/`，**標籤是機翻**） | AC-2.3 的對照側 |
| `fcjavten_4938117_tw.html` | FC2-PPV-4938117 | 2026-08-14 | **已下架** | 繁中（`/tw/`） | 同上 |
| `fcjavten_4938221_tw.html` | FC2-PPV-4938221 | 2026-08-14 | **已下架** | 繁中（`/tw/`） | 同上 |
| `fcjavten_9999999_notfound.html` | 9999999（不存在） | 2026-08-14 | — | 繁中 | CD-118a-19 查無此片 |

### 為什麼要收 `_tw` 對照檔

AC-2.3 要的是「日文原題，不是繁中機翻」。**實測機翻咬到的是標籤，不是標題**——
同一片日文版標籤是 `['ハメ撮り','制服','素人',…]`，`/tw/` 版是 `['奇聞趣事','均勻','業餘',…]`，
而**標題兩邊都是日文原題**。所以可證偽點只能放在標籤，而那需要同一顆片的兩種語言各一份。
沒有對照檔的話，「我們真的拿到日文版」只能靠斷言字面，測不出回歸。

### 日文版 URL 契約（CD-118a-19 的依據，2026-08-14 實測）

- 日文版 ＝ **無語言段 ＋ 必須帶標題 slug**：`/video/{內部id}/id{番號}/{slug}`
- **`/ja/` 是 404**；**少了 slug 是 500**；`/video/{亂數id}/id{番號}` 是 404（內部 id 躲不掉）
- 命中 → 從 `/search?kw=N` **302 到** `/video/\d+/id<番號>/…`；查無 → **不重導**，停在 `/search?kw=N`（title `Search For : N`）
- **判準用最終 URL 的形狀，不偵測任何文案字串**

### 這三顆的解析結果與 owner 既有 DB 逐欄相同

標題／`maker`／`tags` 逐字相符，`rating` 皆 5.0、`samples` 皆 5 張——
**這證明庫裡的 FC2 資料當初就是從這條日文路徑抓的**，fixture 不是憑空造的樣本。

### 站方沒有發售日

整份 HTML 中 `販売日`／`発売日` 出現 **0 次**。`fc-javten` 結構性拿不到發售日（官方站有）。
不要試圖從別處推導——那會寫一個編出來的日期進 NFO。
