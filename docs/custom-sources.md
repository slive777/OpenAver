# 自訂來源說明書

這份文件寫給 AI 讀：使用者貼一個網址、說「幫我把這個站加進來」時，請依本文寫出一份載入不會被拒的 YAML 檔。敘述為繁體中文，鍵名與程式碼維持英文原樣。

## 1. 一句話說明與輸入契約

自訂來源是一份 YAML，用 CSS selector、meta 標籤或 JSON-LD 描述「怎麼從某個站的頁面抽出一部片的資料」。OpenAver 不執行任何程式碼，只照這份宣告抓頁面、抽欄位。

輸入契約：**輸入一律是番號**（例如 `ABC-123`），輸出是該番號的一筆（或多個版本）影片資料。檔案存成 `<id>.yaml`（`.yaml` 或 `.yml` 都會載入），放進自訂來源資料夾後，來源以 `custom:<id>` 的身分出現。

不支援清單（遇到請走 §11）：

- 沒有番號的片（只靠標題或關鍵字搜尋的站）。
- 需要登入、cookie、JavaScript 才看得到內容的站。
- 資料要靠 POST、多次互動或超過兩段頁面才拿得到的站。

## 2. 欄位總表

檔案大小上限 64 KiB。以下三張表列出所有合法的鍵，寫了表上沒有的鍵會被拒（reason `unknown_key`）。

### 頂層鍵

| 鍵 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `id` | 字串 | 是 | 只能用小寫英文字母、數字與連字號，第一個字元必須是英文字母或數字（不可以連字號開頭），總長 1–32 字，必須等於檔名（不含副檔名），不可與內建來源名稱衝突 |
| `name` | 字串 | 是 | 顯示名稱，1–40 字，不可含控制字元 |
| `fetch` | 字串 | 是 | `plain` 或 `tls`，見 §7 |
| `number_pattern` | 字串（regex） | 是 | 標準化後的番號必須完整符合這個 regex，否則此來源直接略過該番號；最長 200 字 |
| `steps` | list | 是 | 1 段（單段式）或 2 段（兩段式） |
| `fields` | mapping | 是 | 欄位宣告，至少要有 `title` 或 `cover` |
| `tests` | list | 是 | 驗收案例，見 §8 |

### step 的鍵

| 鍵 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `url` | 字串 | 是（第 1 段） | URL 模板，只能用 http 或 https，主機名稱必須是固定字面（占位符見 §3） |
| `candidates` | list of 字串 | 否 | 1–8 個、每個最多 16 字；依序把每個值代入 `{suffix}` 各抓一次。只能用在單段式 |
| `not_found_when` | mapping | 否 | 子鍵 `body_contains`：頁面內容含這段字串就判定查無此片 |
| `results` | mapping | 兩段式必填 | 第 1 段的搜尋結果過濾；子鍵 `css`（選出結果連結的 selector）與 `keep_if_contains`（連結的 href 或連結文字必須含這段字串，可用 `{number}`、`{number_lower}`、`{number_digits}`；代入值不做 URL 編碼，比對不分大小寫並檢查邊界，規則見 §3）。單段式不可寫 |

兩段式的第 2 段必須寫成 `- {}`（詳情頁網址來自第 1 段的搜尋結果）。

### field 的鍵

`fields` 底下的欄位名只能是這十三個：`number`、`title`、`cover`、`actors`、`tags`、`date`、`duration`、`maker`、`director`、`label`、`series`、`summary`、`sample_images`。

| 鍵 | 型別 | 說明 |
|---|---|---|
| `css` | 字串 | CSS selector；與 `meta`、`jsonld` 三選一，恰好一個 |
| `meta` | 字串 | 讀 `<meta property=…>` 或 `<meta name=…>` 的 `content`，例如 `og:title` |
| `jsonld` | 字串 | 寫成 `Type.key`，例如 `VideoObject.datePublished`，讀頁面 JSON-LD 裡該型別的該鍵 |
| `attr` | 字串 | 取元素的屬性而非文字；只可搭配 `css` |
| `all` | 布林 | 只對 list 欄位（`tags`、`actors`、`sample_images`）有效：`true` 取全部符合的值，預設只取第一個非空值。其他欄位一律只取第一個非空值，寫 `all: true` 沒有效果 |
| `then` | list | 變換鏈，見 §4 |

## 3. 模板變數表

`url`（以及 `results` 的 `keep_if_contains`）可用以下占位符。主機名稱部分不可使用占位符。

| 占位符 | 示例（番號 `ABC-123`） | 說明 |
|---|---|---|
| `{number}` | `ABC-123` | 標準化後的番號（大寫、連字號） |
| `{number_lower}` | `abc-123` | 小寫版 |
| `{number_digits}` | `123` | 番號**末尾的連續數字**；沒有則為空字串 |
| `{suffix}` | 依 `candidates` 逐個代入 | 只有在該 step 寫了 `candidates` 時才可用 |

只有 `steps[].url` 內的代入值會做 URL 編碼；`keep_if_contains` 的代入值不編碼。大括號必須成對，寫了其他占位符會被拒（reason `bad_template`）。

`keep_if_contains` 的比對規則：比對連結的 href 與連結文字，不分大小寫；命中的字串以數字開頭時，命中處前一個字元不能是數字，以英文字母開頭時，前一個字元不能是英文字母（中日文等其他文字不算，所以標題「中文字幕SONE-205」仍會命中）；兩種情況命中處後一個字元都不能是數字。所以 `SONE-20` 不會命中 `sone-205`，`243999` 不會命中 `fc2ppv2439990`，但 `SONE-205` 仍會命中 `sone-205c`。

## 4. 變換表

`then` 是一串變換，依序作用在抽到的每個值上。每個變換是「恰好一個鍵」的 mapping。

| 變換 | 參數 | 輸入 → 輸出 |
|---|---|---|
| `regex` | regex，必須至少有一個 capture group（沒有會被拒） | `ABC-123 示範標題` + `'^(\S+)'` → `ABC-123`；取**第一個** capture group，不符合就丟棄該值 |
| `strip_label` | 字串 | `演員：某某` + `演員：` → `某某`；開頭不符則原樣保留 |
| `split` | 分隔字串 | `甲、乙、丙` + `、` → `甲`、`乙`、`丙`（三個值，去除空白與空段） |
| `urljoin` | 必須寫 `true` | 相對網址 `/img/a.jpg` → 以頁面網址補成完整網址 |
| `div` | 非零有限數字 | `7200` + `60` → `120`（除後四捨五入，常用於秒轉分） |

寫了其他變換名會被拒（reason `unknown_transform`）。

## 5. 欄位型別層

變換跑完之後，OpenAver 依欄位名自動正規化，作者不需要自己處理：

- **日期**（`date`）：接受 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY.MM.DD`（月日可只有一位，後面可帶 `T` 開頭的時間尾巴）與 `YYYY年M月D日`；統一輸出 `YYYY-MM-DD`，不是合法日期就留空。
- **片長**（`duration`）：取文字裡第一個數字（只認非負數字，不認負號，例如 `-5` 會取到 `5`；可含小數），四捨五入成分鐘；結果為 0 或文字裡沒有數字就留空。
- **網址**（`cover`、`sample_images`）：相對網址以頁面網址補全；只接受 http／https；其他丟棄。
- **清單**（`tags`、`actors`、`sample_images`）：去除空白、去除重複、保持順序。沒寫 `all: true` 只取第一個非空值（`all` 只對這三個欄位有效）。

## 6. `not_found` 三判準與結果形狀

抓一個番號的結果只有幾種：`ok`（一筆）、`multiple`（多個版本）、`not_found`（查無）、錯誤，以及番號不符 `number_pattern` 時的略過。

判定 `not_found` 的三個情況：

1. 頁面回 404（只適用單段式的頁面與兩段式的詳情頁；兩段式的搜尋頁任何非 200 的回應，含 404，都是錯誤 `http_status`）。
2. 頁面內容含 `not_found_when` 的 `body_contains` 字串。
3. 兩段式的搜尋結果過濾後沒有任何連結。

一個站的搜尋常對「查無」也回 200，這時就需要 `not_found_when`。

多版本：同一番號抽到多個詳情頁（單段式的多個 `candidates`，或兩段式的多個結果）且番號都吻合，結果是 `multiple`，依 `date` 由新到舊排序；兩段式最多抓前 5 個詳情頁。

單段式有多個 `candidates` 時，若某個候選逾時或連不上（reason `timeout`、`network`），就不再嘗試後面的候選（站多半是掛了）。兩段式的詳情頁即使某一頁逾時或連不上，也會繼續抓其餘詳情頁（搜尋頁已成功代表站是活的）。

部分頁面失敗不影響其他頁：只要還有一頁成功就算成功。**全部頁面都失敗**才回錯誤，reason 取第一個失敗頁的。

### 載入被拒的 reason

載入時任何問題都會得到下列 reason 之一（多數附出錯的鍵路徑；YAML 語法類錯誤 `yaml_syntax`、`duplicate_key`、`alias`、`unsafe_tag`、`too_large` 沒有路徑，只能自己檢查整份檔案）。AI 看到哪個就照右欄修：

| reason | 常見原因與修法 |
|---|---|
| `yaml_syntax` | YAML 語法錯誤；檢查縮排、引號 |
| `duplicate_key` | 同一層出現重複的鍵；刪掉其一 |
| `alias` | 用了 YAML 別名（`&`／`*`）；改成直接重寫 |
| `unsafe_tag` | 用了 `!!` 之類的 YAML tag；拿掉 |
| `too_large` | 檔案超過 64 KiB；精簡 |
| `unknown_key` | 寫了表上沒有的鍵；對照 §2 |
| `bad_id` | `id` 含大寫、底線等不允許的字元、以連字號開頭或超過 32 字；改名 |
| `reserved_id` | `id` 與內建來源名稱衝突；換一個 |
| `id_filename_mismatch` | `id` 不等於檔名；兩者改成一致 |
| `bad_pattern` | regex 無法編譯、過長或沒有 capture group；或 `tests` 的番號不符 `number_pattern` |
| `bad_template` | URL 模板有不支援的占位符、大括號不成對、主機名稱含占位符，或指向 IP／本機；見 §3、§12 |
| `bad_selector` | CSS selector 語法錯誤 |
| `missing_negative_assert` | `tests` 沒有任何負向斷言；見 §8 |
| `missing_not_found_case` | `tests` 沒有任何一案 `status: not_found`；見 §8 |
| `fetch_cf_unsupported` | 寫了 `fetch: cf`；此版不支援，見 §7 |
| `unknown_fetch` | `fetch` 不是 `plain` 或 `tls` |
| `unknown_transform` | `then` 裡出現未知的變換名；對照 §4 |
| `bad_value` | 其他值錯誤：缺必填欄位、型別不對、`div` 為零、`urljoin` 不是 `true`、`fields` 沒有 `title` 或 `cover` 等 |

## 7. `fetch` 兩種模式怎麼選

- `plain`：一般 HTTP 請求。**先試這個。**
- `tls`：模擬瀏覽器的 TLS 指紋。只有在 `plain` 被站方擋（回 403）、而用瀏覽器指紋的 curl 可以通過時才改用。
- `cf`（Cloudflare 驗證）此版不支援，寫了載入即被拒（reason `fetch_cf_unsupported`）。

抓取時的規則：只有 200 與 404 算正常回應，其他狀態碼都是錯誤（兩段式的搜尋頁連 404 也算錯誤）；重導向最多跟隨 5 跳，每一跳都重新檢查位址；單頁 body 上限 5 MiB。

## 8. 驗收格式與負向斷言

`tests` 是一串案例，每個案例的鍵只有 `number`、`status`、`expect`：

- `number`：真實存在的番號，必須符合自己的 `number_pattern`。
- `status`：`ok`（預設）、`multiple`（預期多版本）、`not_found`（預期查無，不需 `expect`）。
- `expect`：對抽到的欄位下斷言。鍵是欄位名，加上後綴表示斷言種類：

| 寫法 | 意義 |
|---|---|
| `title` | 完全相等；值只收字串、整數或字串 list（不收浮點數、不收 bool） |
| `title_contains`（後綴 `_contains`） | 字串含此片段；值須為非空字串 |
| `tags_include`（後綴 `_include`） | list 欄位至少含這些值；值須為非空字串 list，只能用在 list 欄位 |
| `tags_exclude`（後綴 `_exclude`） | list 欄位不得含這些值（負向）；值須為非空字串 list，只能用在 list 欄位 |
| `tags_max`（後綴 `_max`） | list 欄位長度不得超過此整數（負向）；值須為非負整數，只能用在 list 欄位 |

規則：每個 `ok`／`multiple` 案例至少一項正向斷言；整份 `tests` 至少要有一項負向斷言（`_exclude` 或 `_max`，只計 `ok`／`multiple` 案例），否則被拒（reason `missing_negative_assert`）。整份 `tests` 也至少要有一案 `status: not_found`（用一個站上不存在的番號），否則被拒（reason `missing_not_found_case`）；理由：有些站對查無的番號照樣回 200，沒有查無案就驗不出這種軟 404。理由：selector 沒限定到內容容器時，常會把導覽列、推薦區的連結一起抓進 `tags`，標籤暴增卻不會讓正向斷言失敗；`tags_max` 能擋住這種「看起來有抽到、其實抽太多」的情況。

### 執行階段的錯誤 reason

驗收或實際查詢時，抓取失敗會得到下列 reason 之一：

| reason | 意思 |
|---|---|
| `http_status` | 回應不是 200／404（附狀態碼）；兩段式的搜尋頁只接受 200，404 也是這個錯誤 |
| `blocked_target` | 目標位址未通過公網檢查（含重導向後的位址） |
| `network` | 連線失敗 |
| `timeout` | 逾時 |
| `too_large` | 回應超過 5 MiB |
| `redirect_limit` | 重導向超過 5 跳 |
| `parse_empty` | 頁面抽不到 `title` 也抽不到 `cover`，或 `number` 欄位為空 |
| `transport_unavailable` | `tls` 模式所需元件不可用 |
| `unexpected` | 未預期的內部錯誤 |

## 9. 完整範例

下面兩份範例內容全為虛構（網址用 `.example`），可直接改寫。注意兩點：selector 都限定在內容容器（`main.detail` 或 `article.entry`）之內，避免撞到導覽列；`tests` 都有 `tags_max`。存檔時檔名必須是 `<id>.yaml`，例如第一份存成 `single-demo.yaml`。

### 單段式（og meta ＋ 限定容器的 css）

<!-- example -->
```yaml
id: single-demo
name: 示範單段式
fetch: plain
number_pattern: '[A-Za-z]{2,6}-\d{2,5}'
steps:
  - url: "https://single-demo.example/watch/{number_lower}"
    not_found_when: {body_contains: "page-not-found"}
fields:
  number:   {css: "main.detail h1", then: [{regex: '^([A-Za-z0-9]+-\d+)'}]}
  title:    {meta: "og:title", then: [{regex: '^\S+\s+(.+)$'}]}
  cover:    {meta: "og:image"}
  tags:     {css: 'main.detail .genres a', all: true}
  actors:   {css: 'main.detail .cast a', all: true}
  date:     {meta: "og:video:release_date"}
  duration: {meta: "og:video:duration", then: [{div: 60}]}
tests:
  - number: ABC-123
    expect: {number: ABC-123, title_contains: "示範標題甲", tags_include: ["示範類型"], tags_max: 12}
  - number: ZZZ-999
    status: not_found
```

### 兩段式（搜尋 → 過濾 → 詳情頁 ＋ JSON-LD）

<!-- example -->
```yaml
id: two-step-demo
name: 示範兩段式
fetch: tls
number_pattern: '[A-Za-z]{2,6}-\d{2,5}'
steps:
  - url: "https://two-step-demo.example/search/{number}"
    not_found_when: {body_contains: "search-empty"}
    results: {css: "article.entry h3 a", keep_if_contains: "{number_lower}"}
  - {}
fields:
  number:  {css: "article.entry h1", then: [{regex: '^([A-Za-z0-9]+-\d+)'}]}
  title:   {css: "article.entry h1", then: [{regex: '^\S+\s+(.+)$'}]}
  cover:   {jsonld: "VideoObject.thumbnailUrl"}
  tags:    {css: "article.entry .tag-list a", all: true}
  date:    {jsonld: "VideoObject.datePublished"}
tests:
  - number: ABC-123
    status: multiple
    expect: {number: ABC-123, title_contains: "示範標題乙", tags_include: ["示範類型"], tags_max: 15}
  - number: ZZZ-999
    status: not_found
```

## 10. AI 作業流程 checklist

1. **抓一頁**：拿使用者給的網址（或用 `curl` 抓同一個站的詳情頁），確認不需要登入、內容在原始 HTML 裡（不靠 JavaScript 產生）。
2. **找欄位**：先看 `<meta property="og:…">` 與 `<script type="application/ld+json">`，有就優先用 `meta`／`jsonld`；沒有再用 `css`。
3. **selector 限定容器**：每個 `css` 都以內容容器開頭（如 `main.detail …`、`article.entry …`），不要直接寫 `a` 或 `.tag`，否則會抓到導覽列與推薦區。
4. **判斷單段或兩段**：網址能由番號直接組出詳情頁就用單段式；要先搜尋再點進去就用兩段式，並寫 `results` 的過濾條件，且第 2 段寫 `- {}`。
5. **決定 `fetch`**：先 `plain`，被擋再 `tls`（§7）。
6. **寫 `tests`**：至少兩案，一個真實存在的番號（正向斷言加 `tags_max`）與一個不存在的番號（`status: not_found`）。
7. **自我檢查**：`id` 等於檔名；`number_pattern` 能完整符合每個測試番號；`fields` 有 `title` 或 `cover`；`then` 的 regex 都有 capture group；沒有用到未知的鍵。載入被拒就對照 §6 的 reason 表修正。
8. 站方改版或查不到時不要硬湊：走 §11。

## 11. 表達不了的站

有些站用這套語言表達不了（需要登入、需要執行 JavaScript、沒有番號、需要超過兩段頁面）。遇到這種站，請不要硬寫一份會失敗的 YAML，改請使用者**開 issue**，並附上：

- 該站的網址（最好是一個詳情頁的完整網址）。
- 需要抽出的欄位清單（例如標題、封面、標籤）。
- 你判斷表達不了的原因（例如「內容由 JavaScript 產生」）。

## 12. 已知限制

1. **只能連公開網路位址**：`url` 不能寫 IP 位址，也不能是 `localhost`、`.local`、`.internal` 結尾的主機；國際化網域要寫 punycode（`xn--…`），含非 ASCII 字元的主機名稱會被拒。重導向後的每一跳也會重新檢查。
2. **不執行 JavaScript、不支援登入或 cookie**；`fetch: cf` 此版不支援（寫了載入即被拒，reason `fetch_cf_unsupported`）。
3. **DNS rebinding 殘留**：站方若刻意在檢查與連線之間更改 DNS 解析結果，可繞過公網限制；單人 LAN 使用場景下已接受此殘留。
4. **Windows 非 ASCII 路徑**：OpenAver 安裝路徑含非 ASCII 字元時，`fetch: tls` 模式可能無法建立 HTTPS 連線（CA 憑證路徑問題）→ 改用 `fetch: plain`，或把 OpenAver 裝在純英文路徑。
5. **沒有番號的片不在範圍**：輸入契約就是番號（見 §1）。
6. **文字編碼只看 HTTP 標頭**：解碼只依回應標頭的 `charset`（沒有就當 UTF-8），不讀 HTML 內的 `<meta charset>`；只在 `<meta>` 宣告 Shift_JIS 等編碼的站可能出現亂碼。

其他需要知道的：

- 站改版會讓來源失效，需要自己重跑驗收並修正 selector。
- `date` 取自站內欄位，不保證是發行日。
- 查詢太頻繁時 IP 可能被站方封鎖。
