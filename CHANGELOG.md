# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.11.10] - 2026-07-10

本版主軸：**設定頁「命名區」膠囊化 + 「列表生成」兩層 IA 重排**（feature/95，Part A spec-95a／Part B spec-95b，兩個獨立部分）——把設定頁兩塊長期是「純文字輸入框 + 一長串控制項」的區域，改成更好懂、更難出錯的形態：命名區（資料夾層級／檔名格式）從手打 `{token}` 字串改成「原子變數膠囊（pill）+ 字面文字自由混排」的視覺化編輯器；列表生成設定拆成「日常常用（外層常駐）」+「離線 HTML 匯出（摺疊進階）」兩層。後端零 schema／DB 變更（僅 format-variables SSOT 端點加情境旗標）。

### Added
#### 🏷️ 命名區膠囊化（Part A）
- **資料夾層級／檔名格式改膠囊編輯器**：每個變數（番號／女優／片商／標題／後綴…）以原子「膠囊」呈現，不再是手打 `{num}` 這種容易打錯的字串；膠囊間可自由插入字面分隔符（`[` `]` `-` `_` 等）。變數選單一鍵插入、膠囊整顆刪除（× 或 Backspace 邊界原子刪，不留 `{titl` 半截），貼上時已知變數自動 tokenize、未知 `{foo}` 保留字面。複用既有 source-pill 視覺（999px accent），與 8+30 來源膠囊一致；IME 組字 / Enter guard 不誤送。
- **資料夾層級改動態清單 + 硬上限 3 層**：可「新增一層／移除此層」，最多 3 層（第 4 層 add 鈕灰化）；載入 >3 層的舊設定自動正規化為前 3 層（保後端有效層、棄第 4 層以上死資料，先 slice 再剝 `{suffix}`）。層順序以穩定 id keying，移除中間層不錯置。
- **`{suffix}` 情境隔離**：後綴變數只在「檔名格式」可用、資料夾層級選單不出現（`folder_ok` 情境旗標，由 format-variables SSOT 端點下發，前後端不再各自硬編變數清單）。

#### 🗂️ 列表生成設定兩層 IA（Part B）
- **sec-gallery 拆兩層**：外層常駐＝日常會調的（排序／順序／每頁數量／最小影片尺寸）；摺疊進階層＝只有匯出離線 HTML 才需要的（顯示模式／輸出目錄／輸出檔名），預設收合。
- **揭露文案克制化**：排序／順序／每頁加「也是你瀏覽頁（Showcase）的預設」揭露；最小尺寸 hint 改寫成「掃描／入庫閾值 — 0 = 不過濾；小於此不入庫（決定你看得到哪些片）」；離線匯出層加 Windows 本機檢視說明條（含 `file://` 成因，材質克制不搶眼）。

### Changed
- 「進階刮削設定」內的命名區改用膠囊編輯器（取代純文字輸入框）；預覽區改以 `x-text` 渲染（移除舊手動 regex escape，天然防 XSS）。
- 列表生成設定 state 旗標 `galleryAdvanced` → `galleryExport` rename（語意更準）。

### Fixed
- **冷模組快取下檔名格式膠囊編輯器持續空白**（95a-T8）：使用者首次開 app／清快取後首載時，「檔案命名格式」膠囊編輯器有時完全空白（存的格式沒渲染成膠囊）。成因是 `loadConfig` 靠單一 `$nextTick` 排的一次性 hydrate callback 在冷模組載入時序下不觸發，而該編輯器又早 mount 過了 ready-gate（資料夾層走 `x-for` 自載、不受影響）。改用 reactive `x-effect` + 響應式就緒旗標 + one-shot 收斂補載，繞過不可靠的單發 `$nextTick`（暖快取本就正常，故只在首次冷載可見）。

### Internal
- format-variables 抽成單一真理來源端點（`/api/config/format-variables`）+ `folder_ok` 情境旗標；補「format-variables ⊆ organizer 消費」契約守衛（pytest）。
- 膠囊 tokenizer（`tokenize` / `serializeTokens`）抽成純函式 + node:test round-trip 守衛（`serialize(tokenize(s)) === s`，與 whitelist 無關）；ChipEditor 為非受控 widget，`naming` closure 存參考不進 Alpine x-data（避免 contentEditable 響應式追蹤導致游標跳）。
- 命名區 ESLint 守衛（膠囊 label brace-strip／禁 raw key）+ orphan 清理 + `/design-system` 同步；列表生成 IA 加 zero-dep lint script（`scripts/lint-settings-ia.mjs` 串 `npm run lint:html`，DOM-ancestry 守 export 控制項必在摺疊內）。
- 命名區新增 i18n key 只寫 `zh_TW`（其餘三語留空靠 fallback，milestone 補譯——已知缺 16 key warning）。
- Codex PR review：95a P1（`{suffix}` 資料夾主動移除 + 前 3 層正規化「先 slice 再剝」順序）、95b P2（IA 守衛補鎖 `avlistOutputDir`／`Filename` 在摺疊內）皆已修。

### 測試
- 全套 pytest **5523 passed, 2 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint + lint-settings-ia）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm）。
- Gemini 3.1 Pro 整支 branch 第二意見：Part A（命名膠囊）**Approved**（讚 SSOT／closure 隔離 contentEditable／純函式 tokenize／slice-before-filter 順序／x-text 天然防 XSS；4 條 advisory 皆低 severity 或 future-note、無 P1）；Part B 本輪 agy 落入 sandbox 對話式 fallback 未取得有效審查（已知失敗態），correctness 由 per-task Sonnet review + Codex PR review 覆蓋。
- **95a-T8 冷載修復由 coordinator CDP 實測驗收**（`cacheDisabled` 冷載 3/3 正確 hydrate、暖載／folder 零回歸、編輯游標不跳、reset 重新 hydrate）。
- E2E-95 runbook 全跑：Part A（A1–A11）+ Part B（B0–B7）全 PASS（A0 即本版修復的 bug）。
- 視覺 hard-gate：命名膠囊觀感／兩層 IA 可掃讀性／Windows 說明條材質克制由 owner 真機驗收。

## [0.11.9] - 2026-07-10

本版主軸：**掃描頁「補資料」升級成逐片「工人在幹活」進度卡 + 命中封面飛入圖書館**（feature/94，spec-94 G1–G7）——把掃描頁「補資料」（batch-enrich SSE）從一個乾計數器 + 終端 log，升級成逐片可視的進度卡：每片輪到時即顯示「番號 · 搜尋中…」，結果回來後切到對應結局（命中／命中無封面／查無／失敗／唯讀跳過）；**命中且有可服務封面時，真封面從進度卡飛進側邊欄「瀏覽」**（＝我的圖書館），落地帶 scale/glow + 微光，進度卡上累計 badge。承接 spec-92 D 項「入庫飛入抽成共用元件（`GhostFly.playInboundFly`）、scanner 接線留未來」——本 branch 就是那個未來，**直接複用該共用入口、不新增動畫 primitive**。後端極小擴充（`EnrichResult.reason` 欄位 + SSE `result-item` 帶 reason），**刻意不碰核心 `search_jav`、零 schema/DB 變更**。

### Added
#### 🎬 掃描頁補資料逐片進度卡 + 命中封面飛入
- **逐片「工人在幹活」進度卡**：補資料時，進度區顯示「目前這片」的可視卡（番號從一開始就在，不等結果），取代乾計數器；五態可辨識——`搜尋中…`／命中封面浮現／`補到資料（無封面）`（文字非破圖）／`查無`（琥珀安靜一閃換片）／`失敗`（進 log）／`跳過（唯讀）`。**命中大聲、落空安靜**：只有真的補到可服務封面才飛入 + badge + 微光，其餘小 glyph 一閃就換片、不搶注意力。
- **命中封面飛入圖書館（兩格待命位 + 延後飛）**：進度卡分兩格——左「待命格」停駐前一片命中封面、右格顯示目前搜尋中；命中封面先進待命格停一個搜尋週期（不一出現就飛），**下一片命中時**前一片才飛向側邊欄「瀏覽」入口（複用 spec-92 `playInboundFly`），run 結束時 flush 最後一片；落地 scale/glow + 側邊欄微光；進度卡上累計 badge（本次 run 補到資料片數，run 後淡出，不做持久紅點）。延後飛用真實補資料節奏當 dwell，讓每顆封面看得清；待命格容器恆渲染固定尺寸，飛入起點 rect 恆有效、免時序 race。
- **手機／減少動態不靜默**：窄螢幕（側邊欄隱藏）逐片反饋交給本就可見的進度卡 + badge，收尾用既有 run-end summary toast（不做 per-item toast，避免批次刷屏）；減少動態下命中僅微光、不播飛行。

### Internal
- 後端只加「scraper parse → `EnrichResult.reason`」+ SSE `result-item` 帶 reason（`reason` ∈ hit／no_cover／not_found／error／readonly；normal 站台靠 `asdict` 自動流出、唯讀/例外站台字面補）；**`search_jav` 零改動**（`git diff` 該檔為空）。前端命中封面 URL 由 `file_path` 自組 `/api/gallery/thumb`，後端不吐 `cover_url`。`GET /api/capabilities` 的 batch_enrich `result_item` output_schema 同步補 `reason`。
- **獨立 sonnet review 抓到並修復一個 bulk race（P1）**：bulk 下片 A 命中排了飛入後，片 B 的 progress 於同一同步 SSE chunk 覆寫進度卡狀態會隱藏片 A 的命中封面 img（rect=0），使片 A 的 `$nextTick` 讀到退化不飛。修法：飛入起點 `x-ref` 從會隱藏的 `<img>` 移到固定尺寸、恆渲染的容器 div，rect 跨換片穩定。
- **Codex PR review P1**：`reason=hit` 原用「cover.jpg 磁碟真相」判，但前端命中封面走 `/api/gallery/thumb`，而 `/thumb` 硬性要求 DB `cover_path` 非空、不 fallback 磁碟 sidecar。兩者判準不同 → 「磁碟有 .jpg 但 DB cover_path 空」（掃描後才丟封面／db·nfo-sourced 命中跳過 `_db_upsert`）時卡片顯示 hit、`/thumb` 404 破圖、且該片仍留 missing_cover 清單。修：`reason=hit` 改為鏡射 `/thumb` 的 gate——所有寫檔完成後重讀 DB 最終狀態，`cover_path` 有值才 hit（散落 sidecar 未入 DB → 誠實回報 no_cover、不飛、不破圖）。含 P3 stale wording 併修。
- **Codex PR #98 review P2**：上條只鏡射了 `/thumb` 第一道 gate（DB `cover_path` 非空）。但 `/thumb` cache miss/disabled 時還有第二道——要讀**實體封面檔**（`uri_to_local_fs_path` 反解後 generate／fallback），檔不在 → 404。故「DB 有記 `cover_path`、但實體封面檔已被刪/移／path_mapping 失效」時仍會誤判 hit → 飛入破圖。修：`reason=hit` 改為**同時**要求 DB `cover_path` 有值 **且**用 `/thumb` 同一解析確認實體檔存在（第三個互補回歸鎖固化；stale-WebP-cache 的 false-negative 是安全方向＝不破圖，已知接受）。

### 測試
- 全套 pytest **5521 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.8 的 5498 +23：reason 映射邊界〔hit/no_cover 依「/thumb 可服務真相＝DB cover_path 有值 + 實體檔存在」分流、not_found/error 各分支〕+ 三個互補 mutation-verified 回歸鎖〔擋「cover_written alone」+ 擋「退回磁碟真相」+ 擋「只鏡射 DB gate 漏實體檔」〕+ result-item 三站台 SSE reason 契約 + /thumb 時序鎖）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，dmm 經 JP proxy live）。
- Gemini 3.1 Pro 整支 branch 第二意見：本輪未取得有效審查——agy headless 落入 apply-patch 假審模式（已知失敗態，見 AI_COLLABORATION 註記），已清理工作區殘留、確認 committed code 零污染；correctness 由 Codex auto-review（P1 已修）+ 獨立 sonnet review（P1 已修）覆蓋。
- 視覺 hard-gate：進度卡五態 + 命中飛入節奏 + badge + 手機 fallback 由 owner 真機驗收。

## [0.11.8] - 2026-07-09

本版主軸：**各刮削來源的評分/簡介補進 NFO（NFO-only，服務媒體伺服器用戶）+ 燈箱中繼資訊美化**（feature/93，spec-93 A/B）——把各來源網站**已提供**的「評分/簡介」在刮削時一併抓出、寫進該片 NFO 的 `<rating>`/`<plot>`，純粹服務透過 OpenAver 唯讀產生庫 + `.strm` 餵 Jellyfin/Emby/Kodi 的用戶（那些媒體伺服器把 `<rating>`/`<plot>` 當顯示格，現在這些格不再是空的）。**OpenAver 自身介面刻意不顯示、不進 DB、不翻譯**——延續既有 US7「NFO-only」契約，owner 判斷評分擠高分帶區辨力低、簡介是行銷文案，對自身瀏覽低價值，顯示外包給 Jellyfin。另獨立做燈箱中繼資訊的視覺層次美化。零 API/schema/DB 變更。

### Added
#### 🎬 評分/簡介補進 NFO（媒體伺服器 enrichment）
- **六個來源開始填評分 + 簡介**：刮到的評分一律正規化到 0–5，經既有 NFO writer ×2 輸出 Jellyfin 0–10 尺度。
  - **評分**（7 源）：dmm / heyzo / 1pondo・10musume / jav321 / fc2 / javdb / caribbean。
  - **簡介**（6 源）：dmm / heyzo / 1pondo・10musume / jav321 / fc2 / caribbean。
  - javbus / avsox 站上無此兩格 → 不做。
- **各來源取得方式**（除 DMM 評分外皆「同一請求免費、零額外請求」）：
  - **DMM**：簡介＝主查詢已抓回的 `description` 接線；評分＝**獨立 root probe** `reviewSummary(contentId:){average}`（比照既有 genres/sample 三態 cache，schema 不支援即永久停用、probe 失敗降級不影響主 metadata，**硬性禁止擴充主 `DETAIL_QUERY`**——那是 DMM 命脈，未知欄位會讓全片刮不到）。
  - **jav321**：同頁文字 `平均評価: N.N`（直接 0–5，非 GIF 形式，勿 ÷10）+ 描述 div。
  - **fc2**：JSON-LD `aggregateRating.ratingValue`（支援單一物件／頂層陣列／`@graph` 包裹三形狀）+ 接既有已抽卻未使用的 `div.col.des` 簡介。
  - **heyzo**：同一 JSON-LD `description`（評分早已抓）。
  - **d2pass（1pondo/10musume）**：同一 phpauto JSON 加讀 `Desc` + rating 補 `<=5` sanity guard（擋畸形值）。
  - **javdb**：`.panel-block` 文字 `評分: N.N分`（真實用戶評分；站上無簡介）。
  - **caribbean**：其 phpauto JSON API 已全面死→改走 moviepage HTML fallback 解析 `itemprop="description"` 簡介 + `meta-rating` 星數 rune-count（0–5）評分（同一已抓 HTML、零額外請求）。

### Changed
#### 🎨 燈箱中繼資訊視覺層次
- 燈箱詳情列（番號 · 片商 · 導演 · 片長 · 系列 · 發行商 · 發行日期）從同色扁平長串改為可掃讀：番號升一階色階（`--text-secondary`）+ 微加粗一眼可辨、欄位標籤微分層、中繼區以髮絲線（`--stroke-subtle`）與上方克制分隔。不加色塊/玻璃卡/accent 底，封面仍視覺主角。

### Internal
- 評分/簡介只改「scraper parse → `Video.rating`/`Video.summary`」這一段；carrier 產生（`internal_nfo_carriers`）、前端 strip（`strip_internal_nfo_keys`）、NFO fill-if-missing 寫入管線（`nfo_updater`/`organizer`/`enricher`/`readonly_producer`）皆為既有機制、不動；`needs_update()` 不把 plot/rating 列缺料（不觸發掃描頁「缺資料」提醒）。補回歸鎖 `TestNeedsUpdateNeverNagsPlotRating` 固化此契約。
- **Codex PR review P1**：T2 的 D4-gap mutation 驗證用的 restore `sed` 無 count、over-match，把 `_probe_genres`/`_probe_sample_images`/`DETAIL_QUERY` 三個 `{'id': content_id}` payload 一併誤改成 `{'contentId'}`，但這三個 query 宣告的是 `$id` → `DETAIL_QUERY` 送 `contentId` 使 `ppvContent(id:null)` 失敗、DMM exact/producer/enrich 全掉；DMM unit test 全 mock 在 HTTP 層、對 query↔variables 契約盲故未攔到。已修（三 payload 還原 `id`，僅 review probe 保留 `contentId`）+ 補 `TestDMMProbePayloadVariables` 監看真實 POST 斷言各 method 送出的 variables key 對應其 query `$var`（mutation 驗證會攔）。**P2**：fc2 `_get_rating` 補 `{"@graph":[…]}` 包裹形狀防禦。
- **Codex PR #97 re-review P2×3**（皆真實資料流 gap，HTTP-mock 單測看不到、靠讀真 fixture/merge 路徑抓）：〔P2-1〕自動模式 `source_merger.merge_results` backfill 欄位群含 `rating` 卻漏 `summary` → 贏的來源無簡介時合併後簡介遺失、NFO `<plot>` 恆空（多源模式下本功能形同虛設），修：`summary` 加進 `_STR_META_FIELDS`；〔P2-2〕`.get(k,'')` 在「欄位在、值 JSON null」時回 `None`，`Video.summary` 非 Optional str → `Video(summary=None)` 拋 ValidationError 被 broad except 吞 → 整片結果被丟，修：dmm/heyzo/d2pass 三處 `.get(k) or ''`；〔P2-3〕jav321 詳情頁真描述前有空 `.col-md-12` 佔位、`select_one` 停在空佔位 → summary 恆空（T3 合成 fixture 無此佔位故漏），修：scope 主 panel-body 取第一個非空 `.col-md-12`、用真實 fixture 鎖死。三者皆補回歸。
- caribbean 覆蓋經 JP proxy live 驗證（解 plan-93 D9 defer）：其 JSON API 對真實現行番號全面 404，推翻「1pondo 同一 `_parse_json` 代表家族」假設 → caribbean 走 `_parse_caribbeancom_html`，補值落該 HTML fallback。
- `core/scrapers/README.md` §1.4 新增「評分/簡介覆蓋（NFO-only）」矩陣。

### 測試
- 全套 pytest **5498 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.7 的 5447 +51：六源 rating/summary parse 邊界〔0–5 尺度、勿 ÷10 防呆、JSON-LD dict/list/@graph、rune-count 星數、正則 None fallback〕+ DMM `_probe_review` 三態＋降級不影響主 metadata＋query↔variables 契約守衛 + d2pass `<=5` guard 新舊對照 + fc2 dead 變數接線 + NFO 管線回歸鎖〔fill-if-missing 不覆蓋／不 nag plot/rating／echo 路徑空 plot〕+ Codex PR #97 re-review P2×3〔merge summary backfill／null 描述不丟片／jav321 空 col 佔位真實 fixture〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，dmm 經 JP proxy live）。
- Gemini 3.1 Pro 整支 branch 第二意見：**LGTM、零 P1/P2**（跨源一致性、parse 防禦、UI 克制皆讚，無須修改）。
- 視覺 hard-gate：燈箱 `.lb-details` 層次由 owner 真機驗收。

## [0.11.7] - 2026-07-07

本版主軸：**搜尋頁體驗優化（搜尋列不擠壓 + 整理發現性 + 入庫飛入動畫加強）**（feature/92，spec-92 A/B/C/D 四項）——純前端 UX polish + 一個 latent 正確性 bug 修復，零 API/schema/DB 變更。四個彼此獨立的痛點：搜尋列右側控制項擠壓變形、整理入口埋在頁尾難發現、整理入庫的「飛入側邊欄」動畫太不明顯、以及把該動畫抽成可跨頁複用的共用元件（本版只做 search 端接線，scanner 接線留未來 branch）。

### Added
#### 🎯 入庫飛入動畫加強（C）
- **整理入庫回饋更有實感**：某片整理成功並寫進資料庫後，一顆封面 ghost 從該片飛向側邊欄「瀏覽」入口——改為三段節奏（起飛 → 於入口旁懸停約 0.5s 微發光讓眼睛看清是哪片 → 縮入落地並帶 scale 彈跳 + 光暈），取代舊版「抵達即淡掉的小點」。
- **窄螢幕／手機不再靜默**：側邊欄隱藏時退化為「已入庫」輕量提示，不再毫無反饋；系統開啟「減少動態效果」時保留輕量落地反饋、不播飛行與縮放。

#### 🎯 整理入口更好找（B）
- **批次整理鈕常駐可見**：拖入一批檔案整理時，「批次整理 N 片」主動作恆在視線內（桌面靠既有固定插槽 + 表頭 sticky；窄視窗改貼底浮動列），不再因結果卡過高被推到畫面外要捲動才找得到。
- **單片／批次整理各有可辨識 icon**：單片＝單一檔案 icon、批次＝資料夾 icon，一眼分辨；空狀態說明文字旁內嵌同款 icon + 同色，文字與畫面上那顆按鈕對得上。

### Changed
#### ⌨️ 搜尋列右側控制項不再擠壓變形（A）
- **「自動」來源膠囊不變形**：在已有結果的頁面回搜尋框打新番號時，「自動」／來源名膠囊不再被壓縮擠壓；右側控制區預留足夠寬度（CDP 實測定值）容納最長來源名 + 清除 + 送出。
- **格狀／詳情切換鈕穩定可見**：女優／前綴搜尋有結果時，格狀↔詳情切換鈕穩定可見可點、不被裁切；打字搜尋新片時暫時讓位屬預期，結果落定後回來。

### Fixed
- **不再出現「兩組相同的 ✕」**：在已有結果的頁面重新搜尋（含用「自動」膠囊重搜）進入載入態時，取消鈕與清除鈕不再並排出現兩顆一樣的 ✕——`hasContent` 由手動維護的旗標改為自動推導的 computed 值，根治整類「漏同步一處就出 bug」的結構性缺陷。
- **整理飛入的封面永遠是「正確那片」**：先前在詳情檢視 X 片時、點清單裡另一片 Y 的「整理此片」，飛出去的會是 X 的封面；改為封面身份永久綁定被整理那片自己的資料（起飛位置才有條件借用目前顯示中的元素）。

### Internal
- 新增參數化共用動畫入口 `GhostFly.playInboundFly`（起點元素／封面 src／終點／fallback 由呼叫端傳入、不綁 search 專屬假設）取代 `playToIcon`：三段 timeline、對稱 `onComplete`/`onInterrupt` cleanup（C21，契約源 `playMobilePanelEnter/Exit`）、通用 scale/glow 落地反饋、並發序列化（`killTweensOf(toEl)` 讓最新落地勝出）。scanner 端接線留未來 branch（共用入口簽章刻意不含 search 假設）。
- `hasContent` 改 Alpine computed getter（移除散落 7 處手動賦值）；`playToIcon` 移除並加 ESLint `no-restricted-syntax` 守衛（definition site + caller site 兩 scope，mutation 自驗 RED 防復活）。i18n 新 key `search.toast.db_synced_mobile` 只寫 zh_TW（其餘三語 fallback）。守衛一律走 ESLint 不落 pytest（本版測試數持平）。

### 測試
- 全套 pytest **5447 passed, 2 skipped**（unit + integration，排除 smoke／e2e，與 0.11.6 baseline 一致、零回歸；本版守衛全走 ESLint，故測試數持平）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。
- ESLint 守衛 mutation 自驗：植入 `this.hasContent = ...`（Group 1）／`playToIcon` 定義或呼叫（Group 1 caller + Group 6 definition）皆轉 RED。
- Codex 二審 F1（P2 並發落地反饋 race）已修（`killTweensOf` 序列化）；F2（P3，無現行回歸）記 accepted residual（`.gsap-animating` 通用性邊界＝各元件 scoped，現行 `#sidebar-showcase-link` 只 transition color/background 不觸 C21；未來 transform/filter transition 的 toEl caller 須補 scoped 規則，scanner 接線 branch 一併補、端到端驗）。
- 視覺 hard-gate：owner 真機一次驗收通過（A pill 不變形／無兩組 X、B icon 辨識 + 常駐鈕、C 飛入節奏 + 手機 fallback）。

## [0.11.6] - 2026-07-06

本版主軸：**跨機器路徑映射（WSL2+UNC path_mappings）的讀寫全棧收斂 + DB-key 命名空間守衛**（feature/91，plan-91 axis-A ＋ plan-91b axis-B）——純 correctness 重構、零使用者可見功能變更、零 API/schema 變動。針對「OpenAver 在 WSL、影片放在網路磁碟（UNC `//NAS/share`）、DB 存映射後路徑」這條情境，把兩類長期潛伏的 silent bug 一次修乾淨並上守衛擋死回不去：一是**讀取端忘了在真正碰磁碟前把 `file:///` URI 反解回本機路徑**（縮圖／封面／劇照／串流／女優裁切一律 404 或讀不到）；二是**已反解的值又被餵回 DB key 建構**、落成沒映射過的命名空間，造成 silent DB miss（重複刮削、掉 user_tags、女優照 403）。

### Fixed
- **跨機器路徑（WSL+UNC）下讀圖／串流不再靜默失敗**：縮圖、封面＋劇照、影片串流（seek 206）、女優裁切、相似探索等所有「先讀 DB 路徑再碰磁碟」的入口，統一在磁碟 I/O 前經單一入口反解映射路徑；先前在 `path_mappings` 情境下這些入口會拿映射後的路徑直接碰磁碟而 404／讀不到圖。
- **刮削不再掉使用者標籤（user_tags）live bug**：`web/routers/scraper.py` 對某片重刮時，DB key 由一個已反解的本機路徑裸建構、落成未映射命名空間，導致比對不到既有列、既有 `user_tags` 被當新片覆寫遺失。改為建 DB key 前先 forward-map 回 DB 命名空間，重刮後 user_tags 正確保留（WSL+UNC 回歸測試斷言單一 mapped row + tags union）。
- **NFO 路徑推導反解**：`core/nfo_updater.py` 由影片路徑推導 NFO 檔位置時改用顯式反解入口，跨機器映射下定位到真實本機 NFO。

### Internal
- **axis-A（讀取端反解）**：新增單一顯式入口 `uri_to_local_fs_path()`，取代 22 個站台散落的裸 `uri_to_fs_path`／`coerce` 呼叫（router／scanner／core／enrich 全棧）；27 個純磁碟用途或已處理站台補 `# uri-no-reverse:` marker 標註安全；新增 pytest AST 結構守衛 `test_uri_to_fs_path_reverse_mapping_completeness.py`（sink 白名單＝`open`／`FileResponse`／`os.path.*`／`Path.*`／`shutil.*`），偵測「反解值未經處理直接碰磁碟」→ CI 擋死。含 Codex 兩輪 PR review 修正（enricher DB 命名空間、actress_crop 主流程 403 canonical、守衛 `Path()` 擴充）。
- **axis-A drive-letter remote 反解對齊（Codex PR #94 review P2）**：`reverse_path_mapping` 補上 WSL-mount 候選前綴——當 `path_mappings` 的 remote 端是磁碟機代號（如 `Z:/share`）時，`uri_to_fs_path` 在 WSL 會把 `file:///Z:/share/...` 正規化成 `/mnt/z/share/...`，原本只比對 `Z:\share`／`Z:/share` 兩形式 → miss → fallback 回未反解的 `/mnt/z/...`（該磁碟未掛載時封面／影片／NFO 讀取失敗）。改為額外以 `to_wsl_path(win_prefix)` 產生 `/mnt` 形式候選（dedup，UNC 不受影響、零回歸）。
- **axis-B（DB round-trip 命名空間）**：新增 sink-anchored AST 守衛 `test_db_key_namespace_completeness.py`（錨 DB-key 建構點 `to_file_uri`／`is_known_cover_path`／repo 寫入，非 source），偵測「反解值裸餵 DB round-trip 無 forward-map」→ CI 擋死；獨立 marker `# db-ns-ok:`（不 overload axis-A 的 `# uri-no-reverse:`）。含 Codex 二審修正（守衛 reaching-def marker 界限、keyword sink 抽取）。
- **已接受殘留**：`core/enricher.py` `_write_nfo` 的 `user_tags is None` 分支裸 `to_file_uri` 為 dead path（所有 production 呼叫端恆傳 `user_tags != None`），marker + docstring 已註記，另開 follow-up；plan-91b D4 固化「寫入端命名空間統一（DB 一律存單一 canonical namespace）」暫緩為 feature/92+（守衛已達成 axis-B「不容易觸發」）。

### 測試
- 全套 pytest **5447 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.5 的 5365 +82：axis-A 22 站台 WSL+UNC 反解回歸〔縮圖／封面＋劇照／串流／女優裁切／相似〕+ axis-B 兩 bug 回歸〔刮削 user_tags union 單一 mapped row／enricher NFO DB 命名空間〕+ 兩支 AST 守衛自驗 21 案例〔含植入假違規 mutation 轉紅〕+ nfo_updater／path_utils／showcase／thumbnail_cache 補測 + Codex PR #94 drive-letter remote `/mnt` 候選反解回歸〔命中／backslash 形式／boundary share-vs-share2／UNC 零回歸／e2e〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。
- 真機 E2E hard-gate（WSL2+UNC+path_mappings，CDP + DB SQL 檢查）：sign-off #1–12 全過——縮圖／封面劇照／串流 seek 206／女優裁切主線／similar／enrich NFO 落反解磁碟／fetch-samples 守衛觸發／真刮 MIDV-300 user_tags union 單一 mapped row／NFO 路徑反解／readonly `.strm` 純 marker 零回歸／DB 命名空間三查詢無分裂無重複。關鍵教訓：`D:\123`（`/mnt/` 短路成 drive-letter URI）無法觸發 bug，須非 `/mnt` 路徑 + UNC mapping 才是真觸發。

## [0.11.5] - 2026-07-05

本版主軸：**唯讀來源生成媒體伺服器庫（media-server 風味）+ 跨機器路徑映射 + 唯讀寫入全面封鎖**（feature/90，spec-90 §90a/§90b/§90c）——承接 0.11.3/0.11.4 的唯讀產生庫，這版把「餵給 Emby／Jellyfin／Kodi」這條路走通：唯讀來源除了生成 OpenAver 自己瀏覽的本地庫，還多吐每片一個 `.strm` 捷徑檔給媒體伺服器掃描播放。針對「OpenAver 在這台、媒體伺服器在 NAS／別台」的跨機器情境，新增「播放端路徑替換」規則，把 `.strm` 裡的影片路徑翻成播放端看得懂的路徑；改了規則，既有 `.strm` 一鍵同步改寫。同時把唯讀來源的「零寫入」承諾補到滴水不漏：勾唯讀有破壞性確認、四個會寫回的入口在唯讀產生片上全部停用並導引、切換媒體伺服器模式時清乾淨舊唯讀來源的媒體卡（只清庫、不刪你輸出夾的檔）、產生中途斷線也乾淨收尾。

### Added
#### 🎯 媒體伺服器風味（.strm）+ 跨機器路徑映射
- **唯讀來源可生成 `.strm` 媒體庫給 Emby／Jellyfin／Kodi**：Settings 把模式切到 Emby／Jellyfin／Kodi 後，對唯讀來源「產生」時，除了每片一夾的 NFO＋封面，還多產一個單行 `.strm`（無 BOM）指向雲端／唯讀硬碟上的原始影片。把輸出夾指向 NAS 上一個可寫位置，媒體伺服器就能掃這批片、經 `.strm` 串流播放，而唯讀來源一個 bit 都沒被寫。
- **跨機器「播放端路徑替換」**：當播放的媒體伺服器在別台機器、看到同一顆硬碟的路徑跟 OpenAver 不一樣（例如 OpenAver 上是 `Z:\115`、NAS 上是 `/volume1/115`），到 Settings 加一條映射規則，`.strm` 內就會寫成播放端看得懂的路徑。跨命名空間比對（Windows 顯示 vs WSL 原生皆可對上），播放端路徑原樣寫入不做正規化。
- **改規則即同步改寫既有 `.strm`**：改／加／刪一條映射規則並儲存後，跳「將改寫 N 個 `.strm`」輕量確認（N 為精確計數），確認即依新規則一次改寫所有既有 `.strm`（只覆寫那一行純文字，不動 NFO／封面／DB／影片檔）；刪光規則則還原成本機路徑。OpenAver 自身播放不受影響（從 DB 串流原檔）。

#### 🎯 唯讀寫入封鎖 + 破壞性操作確認
- **勾「唯讀」跳確認**：在 Scanner 把來源勾唯讀時跳確認彈窗，白話說明唯讀代表什麼、輸出夾放哪、跨機器怎麼餵媒體伺服器；確認後才真的勾上，媒體伺服器模式下同時展開「輸出到」欄位。
- **唯讀產生片四個寫入入口停用**：對「由唯讀來源產生」的片，封面牆補圖 icon、燈箱「補資料」「補劇照」、齒輪「進階重刮」四個會寫回的入口全部停用（淺色、不可點、hover 導引「更新請至掃描頁重新產生」），播放／開資料夾／探索相似等唯讀操作照常。後端三個補資料端點也一律拒絕唯讀來源、來源零寫入。

### Changed
- **切換媒體伺服器模式會清掉舊唯讀來源的媒體卡**：在有唯讀來源時切換模式，跳破壞性確認（正確待移除數 + 白話後果 + 多分頁提醒）；確認後移除那些唯讀來源與其媒體卡，之後重新加入即可在新模式重建。**只清 DB 卡，你輸出夾裡的檔案一個都不刪**；可寫來源與其卡完全不受影響（巢狀在唯讀夾下的可寫來源也精準保留）。
- **部署文案清晰化**：把「輸出夾（產出放哪、要可寫、通常在 NAS）」與「播放端路徑替換（影片路徑跨機對應）」兩個容易混淆的欄位講清楚、界線分明；切換彈窗用詞與 checkbox 統一為「唯讀來源」；三模式一律並列「Emby／Jellyfin／Kodi」。Help 新增「唯讀來源 + 讓 Emby／Jellyfin／Kodi 掃到片（跨機器部署）」區塊，把整條部署流程用步驟講通（痛點常在事後播不出才回查，Help 是唯一會回來找的地方）。

### Fixed
- **產生中途斷線乾淨收尾**：產生過程中關分頁／重整／中斷 SSE，後端在下一個檢查點停手、不跑完整來源，尾段仍跳 HTML 產生與完成通知、保留必要收尾（媒體伺服器快取重置），正常跑完零回歸。
- **產生進行中擋切換模式**：一個分頁在產生時，另一分頁切換模式會被擋下並提示「產生進行中，請等產生完成後再切換模式」，避免背景 producer 在清卡後又把卡補回去。
- **切換模式彈窗矛盾修正**：唯讀確認彈窗的「請先去設定切模式」提示改為只在預設模式顯示，不再出現「已在 Emby／Jellyfin／Kodi 模式卻又叫你去切」的自相矛盾。

### Internal
- 新增 `scraper.strm_path_mappings` 設定（加法式遷移補預設）；`core/readonly_producer.py` 加 `.strm` 產出 + `_apply_path_mapping`（file:/// URI 空間比對、最長前綴勝、remote 端 verbatim 不正規化）；`core/readonly_source.py` 抽唯讀判定純資料流層（scraper guard 與 showcase payload `is_readonly_source` 共用）；`core/generate_state.py` 產生進行中登記表（雙 clear-hook 生命週期）。
- 破壞性端點：`POST /api/config/switch-external-manager`（枚舉離線來源 DB 卡 → delete_by_paths + 縮圖失效 → mutate_config 原子移除離線條目 + 設新模式；先 DB 後 config 可自癒失敗序；巢狀可寫來源從刪除集扣除；髒來源路徑 coerce 容錯 skip 不 500）、`POST /api/config/rewrite-strm`（dry-run 精確計數 + best-effort 就地改寫、壞列 skip 不阻斷整批）。兩端點皆使用者觸發維護操作、不揭露 capabilities。
- 前端：唯讀 checkbox 攔截式確認（`:checked` 單向綁定 + `@click.prevent`，非 x-model）、破壞性切換流程（element-bound 綁定 + isDirty 不誤判 + 三處狀態同步）、唯讀產生片四入口 native disabled、strm 映射編輯器 + 範本回顯。
- Gemini 整支 branch 二審 triage：switch 端點髒路徑 coerce 容錯（mirror 既有唯讀判定 guard）、`strmChanged` 補 optional chaining（config.scraper undefined 防崩存檔）；其餘 findings triage 為誤報或已知接受殘留。

### 測試
- 全套 pytest **5365 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.4 的 5171 +194：strm 產出/單行無 BOM/off 不產 strm + 路徑映射三類+邊界/跨命名空間+尾分隔符 + rewrite 端點多片/刪規則還原/off no-op/只動 strm/dry-run 計數/mapped output_dir 反解 + switch 端點 purge 全契約/巢狀可寫扣除/髒路徑容錯 + 唯讀 enrich guard 三端點+混合批/巢狀可寫 override 矩陣 + SSE 斷線生命週期/尾段 abort + 前端停用態/確認彈窗/切換流程守衛 + 五審 file:/// URI 型來源前綴映射對齊 DB 命名空間〔WSL+映射匹配/非映射 canonical/非 WSL round-trip〕 + 整份儲存↔切換真互斥雙向 guard/窗口釋放/重疊存檔第一個結束仍擋切換/三方重疊全清才放行 + 掃描中改 strm 映射 gate〔映射變更擋存檔/未變放行/無 generate 放行〕 + rewrite-strm 掃描中拒絕含 dry_run + strm 映射 fresh getter〔覆寫勝凍結/None 回退凍結/空覆寫寫原始路徑/produce_source getter 供新映射 vs 無 getter 用凍結/getter 在 NFO 後 _write_strm 前才求值的時序鎖〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**7 源 PASS + 1 SKIP**（javbus／jav321／heyzo／d2pass／avsox／javdb／dmm 全 PASS；fc2 unreachable/no probe → SKIP 非 fail，pre-merge live 健康檢查）。
- E2E 真機驗收（CDP + 檔案驗證）：6 大硬閘門全過——strm 規範（單行/無 BOM/正確路徑）、唯讀零寫入（來源逐位元不變）、映射改寫 ≥3 檔抽查 + 刪規則還原、四寫入入口停用態 + tooltip、破壞性切換 purge（零檔案刪除）、產生中擋切換（兩分頁 toast）。
- Codex PR review（90c 二審 Finding 2/3 + PR #93 一審 P2×2〔巢狀可寫 override 唯讀判定、mapped output_dir reverse-map〕 + PR #93 二審 P1+P2×2：巢狀歸屬改「最具體〔最長匹配〕前綴勝」修回上一輪「可寫一律壓唯讀」對反向巢狀〔可寫父+唯讀子〕的回歸〔showcase/scraper/purge 共用同一 is_path_readonly〕、切模式 purge 改雙向互斥〔try_begin_switch 佔全窗口 + generate 掛號 try_mark_generate_active 檢查，杜絕切模式進行中才開始的 generate 把剛 purge 的卡補回〕 + PR #93 三審 P2×2：strm 改寫時 source path 也走 reverse-map〔補上一輪只反解 output_dir 的漏網，WSL+gallery.path_mappings 下改寫內容 == 初次生成內容〕、半填映射規則丟棄〔remote 空的規則前端不存 + 後端 _apply_path_mapping skip，避免前綴被剝只剩後綴破壞 strm〕 + PR #93 四審 P2×1：switch 也序列化〔try_begin_switch 補檢查 _switch_active，第二個重疊 switch 回 switch_in_progress 拒絕，否則第一個 end_switch 會在第二個窗口中清旗標讓 generate 趁隙補回卡〕 + 主動對抗性自審 P1×1：整份設定儲存也讓開 switch 窗口〔update_config 在 is_switch_in_progress 時拒絕，防另一分頁帶舊 directories 快照把剛 purge 的離線來源條目寫回 config；次秒級窗口〕 + PR #93 五審 P2×2：〔P2-f〕唯讀來源前綴改走 `to_file_uri(uri_to_fs_path(path), mappings)` canonical 化〔取代 coerce_to_file_uri 對 file:/// URI 型來源原樣回不套 mapping 的漏——producer 存 DB row 是 mapped 命名空間，URI 型來源前綴對不上 → 唯讀 guard/showcase 旗標/switch purge 全 miss；config.py `_safe_prefixes` 併入共用同一 helper 杜絕重複實作漂移〕、〔P2-e〕整份儲存↔切換改真互斥〔取代上一輪 is_switch_in_progress preflight 的 TOCTOU：存檔可在 switch 開始前通過檢查、卻在 switch 做完後才落盤 → lost-update。改 update_config 持 config-save 窗口、try_begin_switch 見窗口即拒絕，兩者同一 _lock 原子不交錯；owner 拍板互斥鎖，殘留「切換已全做完後才到的舊快照存檔」記為已知限制、靠破壞性 confirm『其他分頁請重整』提示兜底。五審二次 Codex：窗口旗標從 bool 改 **token-set**〔比照 generate 的 _active_tokens〕——bool 版下兩個重疊存檔第一個結束就把共享旗標清掉、第二個仍在寫窗口內 switch 就能進場，race 重新暴露；per-token add/discard 讓第一個結束不清掉第二個窗口，switch 續擋到最後一個存檔結束〕 + PR #93 五審三次 P2×1：〔strm 映射 vs generate〕掃描/產生進行中 gate 掉「有動到 scraper.strm_path_mappings」的整份存檔與 rewrite-strm〔generate 起始把 config 凍結一場沿用，中途改映射存檔 → 該次 generate 之後才產出的 .strm 仍用舊映射且無自動重寫 → 靜默半修永久指錯；owner 拍板精準 gate：is_generate_in_progress 短路後才 diff，只擋真動到映射的存檔、改主題/檔名等不受影響，rewrite-strm 端點同擋含 dry_run，前端顯示 warning toast『掃描完成後再改』〕 + PR #93 五審四次 P2×1：〔strm 映射斷線尾巴殘留〕gate 只看 is_generate_in_progress，但 SSE watcher 偵測到斷線即清 generate token，producer 每片 checkpoint 才看 should_abort → token 清空後仍會多做完當下這片、此時另一分頁可存新映射 → 那片用凍結舊映射落檔且不自癒〔比 P1 殘留嚴重：不像 switch race 下次 generate 自癒〕；owner 拍板 option C：produce_source 注入 strm_mappings_getter，media-server 模式每片寫 .strm 前重讀 fresh 映射〔scanner 注入 load_config().scraper.strm_path_mappings，無 lru_cache 每次讀 disk〕，讓斷線尾巴那片也用當前映射；getter=None 回退凍結 config，既有呼叫/rewrite/測試零行為變更〕 + PR #93 五審五次 P2×1：〔getter 求值時機〕getter 原在 produce_source 片處理開頭 snapshot，但 _write_movie_assets 接著下載封面/生成圖/寫 NFO 才輪到 _write_strm、期間存的新映射會被漏掉 → 改傳 getter callable 往下、在 _write_strm 前一刻才求值（封面/NFO 都寫完後）。殘留降至「getter() 回傳→open() 寫檔」微秒級 GIL 排程窗口，與 generate_state.py 既記錄之 owner-accepted 殘留同類（徹底封死需 option A 綁 token 生命週期至 worker 真停手，已評估否決：跨檔重構+token 洩漏風險比原 bug 更糟）〕）+ Opus 審核（purge 巢狀誤刪 / rewrite 壞列容錯）+ Gemini 整支 branch 二審皆已 triage 修正。

## [0.11.4] - 2026-07-04

本版主軸：**唯讀產生庫「地基」+ 掃描頁「試過」提醒 UX + 來源刪檔清死卡**（feature/89，spec-89 §89a/§89b）——承接 0.11.3 的 off 風味唯讀產生庫，先把「OpenAver 生成的片」變成**一等公民**：系統記住每部片生成在哪個資料夾、這份記憶不被其他操作洗掉，於是重新產生／強制重刮回到同一資料夾原地更新，不再每次多長一個重複垃圾夾（沒封面的片也記得住位置）。站在這塊地基上，再修掃描頁三個惱人問題：已刮過／已生成的片不再被「缺資料」嘮叨、刮不到的片試過一次就跳過不再每次重打、唯讀網盤掉線時明確警告而非靜默報成功，並在來源端刪檔後清掉庫裡對應的死卡（**只清 DB、不動你輸出夾裡的檔案**）。89a 地基多半使用者無感，但讓 89b 與後續 feature/90 全部乾淨。

### Added
#### 🎯 生成片一等公民身分 + 記住輸出夾（89a 地基）
- **重新產生／強制重刮不再長重複夾**：新增 `videos.output_dir` 欄位記住每部片生成的資料夾（同時作為「這是 OpenAver 生成的」可靠標記）——之後重刮回到同一夾原地更新。無封面的片也記得住位置。
- **off 風味輸出夾免設定**：唯讀來源「預設／自瀏覽」風味的產物固定落在 App 自管位置 `output/lib/<來源名>`（比照縮圖、女優封面的慣例），畫面上不再顯示輸出夾欄位、也不會發生「忘設輸出夾→產生 0 片」。給媒體伺服器（Emby/Jellyfin/Kodi）用的風味才可指定任意輸出夾（供後續 feature/90）。
- **同一部片多格式各自有夾**：`.mp4` + `.mkv` 落入不同資料夾、不互相覆蓋。

#### 🎯 掃描頁「試過」記憶（89b）
- **試過／已生成的片不再被嘮叨**：新增 `scrape_attempted_at`「試過」記憶，任何被實際刮過一次（含成功、天生沒封面、查無資料）或 off 已生成的片，都不再出現在底部「缺資料」提示；提示只留給真的還沒處理的片。
- **刮不到的片只試一次**：查無資料的片試過後自動跳過、不再每次重刮（除非強制或改名），仍以檔名顯示在封面牆讓你自行改番號重刮／補封面／留著。

### Changed
- **原地覆蓋精準清殘檔**：重刮同片時，若標題被片商修正（`{番號} {標題}` 檔名改變），舊標題的殘檔會被精準清除、不再越堆越多（只清本片系列檔、不動你自己放進資料夾的檔）。
- **兩顆「缺資料」藥丸文案去重疊**：「NFO 欄位不全」（已刮過只是資料不全）與「缺 NFO 檔案／缺封面檔案」（本體缺件）一眼可辨。

### Fixed
- **唯讀網盤掉線不再誤報成功**：唯讀來源掛載掉線／讀取中途出錯時明確警告並略過（scanner 頁完成 toast、通知中心、完成通知三處都走警告），絕不在資訊不完整時亂清庫。
- **`output_dir` 身分不被補完／重刮洗掉**：`upsert`／`upsert_batch`／enricher 對 producer row 補完或重刮不再弄丟它的位置記憶（否則預設批次補完會例行性洗掉、身分與記位失效）。
- **WSL＋UNC mapped 輸出根定位正確**：`output_dir`／封面落地判斷走 targeted reverse-map，跨機器路徑映射下拿到真實本機路徑。
- **off 固定夾封面可經 image proxy 讀取**：`resolve_output_root` 共用 helper 讓 off 固定輸出夾同步進 `/api/gallery/image` 白名單（否則剛生成的封面／劇照經 proxy 一律 404、OpenAver 自己看不到圖）。
- **producer／「試過」markers 不被重掃或整理搬移洗掉**：`output_dir`／`scrape_attempted_at` 在 `upsert`／`upsert_batch`／`repath` 三處都加「incoming 空／0 則保留既有」保護，避免一般來源「查無資料」的片在資料夾重掃或整理搬移（rename→repath）時被 default 值覆寫、tried 歸零後又跑回「缺資料」提示。
- **重刮寫到一半失敗不再兩頭空**：舊資產清除從「寫新資產之前清」改為「寫成功之後才清、且只清替換已寫成的」——若封面下載失敗或 NFO 寫入失敗，該片先前可用的封面／NFO **保留不動**（同名直接覆寫不預刪、改標題才清舊系列且各資產只在新檔寫成時才刪舊檔），不會清掉舊的卻又沒補上新的。

### Removed
- **來源刪檔清庫裡死卡**：在網盤／NAS 刪了某片後，下次對該來源產生時（**確認來源可達、清單完整且非空**的前提下）清掉庫裡對應的死卡。**預設只清 DB 卡、零檔案系統刪除**（你輸出夾裡的 nfo／封面／資料夾不動）。partial-scan（部分路徑讀取失敗）或空列表時整源不清（保守優先，寧可留死卡也不誤刪活著的片）。
- **拔除無狀態重算夾機制**：刪掉舊的跑時 cover-owners map／hash 尾碼消歧（`_build_owners` 等）改由 DB 存值 + increment 分配；連帶移除失去唯一呼叫者的 `cover_index` 死碼鏈。

### Internal
- DB schema 加法遷移 `output_dir TEXT DEFAULT ''` + `scrape_attempted_at REAL DEFAULT 0`（含一次性 backfill：已有封面／NFO／已生成的舊片自動視為「試過」；舊庫升級不需重建、不報錯）；新增 `get_attempted_index`／`update_scrape_attempted_at`／`insert_if_ignore`／`is_output_dir_taken` repo 方法。
- `resolve_output_root(source, config)` 單一真理 helper（off 固定 / media-server 設定），三 call site（producer output_root、`no_output` guard、image 白名單）共用。
- `_should_skip` 改單一 `attempted` 信號 + `force` 強制重刮參數（僅函式層 plumbing，UI 觸發點為 follow-on）。**行為變化**：移除磁碟 cover 檢查後，外部誤刪輸出夾封面不再自動 self-heal 重建（省成本優先，folder 正確性交給記憶輸出夾地基）。
- 唯讀來源 reachability guard + partial-scan `skipped_paths` 訊號；DB-row-only prune 的「本次列表」用原始掃描清單（非已處理集合），避免把「存在但被 skip」的片誤判消失而刪卡；prune 一併與非唯讀分支對等 invalidate 縮圖快取；完成通知 `no_output`／`unreachable`／`partial` 五步映射打通（per-source warn SSE + 計數 + completion warn-gate + scanner 頁 toast）。

### 測試
- 全套 pytest **5171 passed, 2 skipped**（unit + integration，排除 smoke／e2e，較 0.11.3 的 5031 +140：89a output_dir 欄位/upsert 對稱保護/佔用查詢 + output_dir/scrape_attempted_at upsert/upsert_batch/repath 三處對稱保護 + stale-clean 寫成功後才清（NFO/cover 失敗保留舊資產） + resolve_output_root 真值表/來源名確定性短碼/image 白名單含 off 根 + 夾位讀存 idempotent/B1/B2/increment + stale title-drift 精準清 + mapped-output 定位/enrich 保留 + 89b scrape_attempted_at 遷移/backfill〔含 output_dir 反推 mutation 鎖〕/三寫入點標記/`_should_skip` skip 矩陣+force + missing-check 排除 produced/tried + reachability/partial 三訊號矩陣 + DB-row-only prune〔跨來源隔離·partial 抑制·只刪 DB 不動檔·should_abort 尾巴防誤刪 mutation 鎖·不誤報成功三情境〕）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。

## 0.11.x 系列 (v0.11.0 ~ v0.11.3, 2026-06-27 ~ 2026-07-01)

- **v0.11.0**：JavBus 過度泛用清償 + exact 番號搜尋改優先序 cascade（feature/85）——直接搜番號改為依你拖曳的來源優先順序逐一查詢（cascade，命中即回），JavBus 不再無視優先序搶先短路；DMM proxy 透傳修復、前綴搜尋 `type` 參數修正；拔除已死的 JavBus variant（同番號多版本）探查死碼。
- **v0.11.1**：JavLibrary 同番號多版本手動切換（feature/86）——搜尋框直搜／燈箱換來源／結果卡替換來源三入口皆可看封面手動挑撞號版本（游標預設停最新發行日），桌面 standalone 限定（需 CF transport）。
- **v0.11.2**：`core/database.py` 模組化拆分（feature/87）——2,152 行單檔拆成 `core/database/` 套件（六個領域子模組 + 永久 re-export facade），消除 `AliasRepository`／`TagAliasRepository` 鏡像重複碼（共用泛型基類），零行為／API／schema 變更。
- **v0.11.3**：唯讀來源生成本地媒體庫「off 風味」首發（feature/88）——scanner 來源可勾「唯讀」＋設輸出夾，來源零寫入下生成每片一資料夾的本地庫（NFO + 封面 + 劇照）並直接寫進 DB，供 OpenAver 自身瀏覽／串流播放雲端原檔；給 Emby/Jellyfin/Kodi 的 media-server（`.strm`）風味延後至下一版（feature/89）。

測試數 4735 → 5031。

## 0.10.x 系列 (v0.10.0 ~ v0.10.11, 2026-06-18 ~ 2026-06-24)

- **來源穩定性 + 測試硬化**（v0.10.0，feature/73）：8 源真實番號健康金絲雀 smoke（三態 quorum 判讀）+ avsox 復活（站方轉 SPA 後改打背後 JSON API）+ Tokyo Hot 單字母無碼番號查無修復 + 覆蓋率地板 84%（`cov-floor`）+ 五項高風險模組（含會改寫用戶 NFO 的 `nfo_updater`）離線單元測試債清償。
- **前端呈現與發現性優化**（v0.10.1～v0.10.2，feature/74/75）：進階搜尋畢業為永久常駐核心，隱形長壓手勢全面移除、改「來源膠囊」處處可見觸發挑源／換源；搜尋詳情資訊密度重排、封面正面裁切共用規則、行動裝置基礎相容（scroll trap／星空門檻／觸控 overlay）補齊。
- **開發工具鏈硬化 + 前端離線可靠性**（v0.10.5～v0.10.6，feature/78/79）：`ruff` + eslint/stylelint 進 CI 擋 PR（先前純本地、沒人本地跑就漏）；GSAP/Alpine/圖示字型改本機載入斷網仍可用、前端錯誤自動記錄；`requirements.txt` 精確鎖版並把 Starlette 鎖至最新修補版清除已知 CVE。
- **MPA 跨頁轉場 + Fluent 材質統一**（v0.10.3～v0.10.4，feature/76/77）：純 CSS View Transitions 讓 sidebar 切頁白屏閃爍改平滑淡換（Showcase 因常駐動畫維持硬切）；全站材質收斂成單一 token 系統的 6 角色（Mica canvas／Glass shell／panel／caption／overlay／Media frame）+ 浮動圓角玻璃 chrome 擴及 search／settings／scanner。
- **LAN 伺服器模式 + 手機體驗完整化**（v0.10.7～v0.10.11，feature/80/81/82/83/84）：一鍵把桌面 App 開放給同區網手機／平板瀏覽（dual-listener + 區網存取閘門）；手機加主畫面圖示、封面／燈箱左右滑換片、窄螢幕破版修補；Windows 系統匣關閉行為（最小化背景執行）；燈箱封面比例自適應不留白 + 行動星形爆射相似探索面板；Windows 雙擊安裝捷徑 + Help 頁一鍵更新按鈕。

測試數 4089 → 4735。

---

## 0.9.x 系列 (v0.9.0 ~ v0.9.11, 2026-05-29 ~ 2026-06-13)

- Scraper Federation + metatube HTTP 聯邦（30 provider Parts Bin + promote/demote + 無碼 staged + SSRF 驗證）、Settings 分區 IA + 資料驅動來源 schema + 進階重刮彈窗
- Active Row 拖曳順序成搜尋路由唯一真理（拔除 primary_source）；async-offload 慢 I/O 移出 event loop（NAS stat / sqlite / config / 同步 HTTP）+ config 鎖/原子寫 + AST 守衛；封面三態（skeleton/shimmer/破圖）+ Showcase console 清零
- 新增來源：JavLibrary（BETA，桌面借 PyWebView 過 Cloudflare）+ avsox 復活（轉 JSON API）+ Tokyo Hot 單字母番號修復；8 源真實番號健康金絲雀 smoke（三態 quorum 判讀）+ cov-floor 84% 流程地板
- 本地 WebP 縮圖快取（opt-in，SSD 出圖不碰 NAS + blur-up 燈箱）+ 燈箱單筆刪除（只刪 DB row）；VR 投影標籤保留 + 自動 VR tag
- 外部媒體管理器相容（Jellyfin/Emby/Kodi 四態：poster/fanart 命名 + cd1/cd2 合併 + NFO 補欄 + Scanner 識別外部封面）；dim 暗色主題色彩編碼修復；進階搜尋畢業為永久常駐核心

測試數 2937 → 4089。

## 0.8.x 系列 (v0.8.0 ~ v0.8.10, 2026-04-28 ~ 2026-05-28)

- Charter Pilot：Fluent 2 視覺語言全站統一（§1–§6 + ease/DURATION 三角色）+ Ghost-fly Lightbox 共用化 + Alpine 釘版四插件 + 全站通知中心
- 全站前端 ESM 模組化（Import Maps，巨型單檔全解體）+ lint toolchain（eslint flat config + stylelint，frontend_lint 905→450）
- 以圖搜圖 CLIP Beta 出貨後轉向純規則式相似度排序器（拔 ML 依賴、主 ZIP 271MB→43MB）
- Tag Alias 跨語言系統 + Search→Showcase pipeline 即時化（GhostFly + DB 即時 upsert）+ Onboarding Scanner-first 翻轉 + SSRF 白名單 + 女優查詢 json_each 重寫

測試數 2705 起（系列歷經 CLIP 上下架與 lint 瘦身，末值未單列）。

## 0.7.x 系列 (v0.7.0 ~ v0.7.8, 2026-04-10 ~ 2026-04-26)

- Agentic AI API 平台首發（batch-search / generate-from-ids / enrich-single / collection-sql / capabilities manifest）
- User Tags 三層整合（DB + NFO `<user_tag>` + API + Search/Showcase 雙頁 UI）
- Actress Favorite + Showcase 女優模式（actresses DB + Orchestrator 4 路並行 + 女優 Grid/Lightbox/Hero + GSAP）+ Actress Alias CRUD
- Scanner 一鍵補完（missing-check + batch-enrich SSE 分批）+ Ghost Fly 轉場 + WinFsp/rclone 掛載相容 + 劇照幽靈 URL 修正

測試數 1818 → 2705。

## 0.6.x 系列 (v0.6.0 ~ v0.6.7, 2026-03-29 ~ 2026-04-09)

- 四語系 i18n 建立（繁中/簡中/日文/英文，~477 key + `core/i18n.py` + `window.t()` + JavBus lang 連動）
- Agentic AI API 初版（batch-search / generate-from-ids / enrich-single / collection-sql / capabilities）+ OpenAI Compatible 翻譯 Provider
- Alpine.js 技術債清理（6 頁統一 `Alpine.data()` 註冊、移除 bridge.js/init.js、SearchCore 全域消除）
- Scanner Jellyfin 圖片手動觸發 + TTL 快取 + 前端動效補強（checkmark/shake + Load More stagger + alert→toast）

測試數 1366 → 1634。

## 0.5.x 系列 (v0.5.0 ~ v0.5.5, 2026-03-25 ~ 2026-03-28)

JavBus Scraper 完全重寫（移除 jvav 第三方依賴）+ Video Model 擴充（director/duration/label/series/sample_images）+ Sample Gallery 元件（extrafanart 全鏈路）+ Metadata Pipeline 補齊（NFO 讀寫全欄位）+ Maker 名稱對照表重建（雙層 JSON + shared loader）+ DMM 模糊搜尋 + 全來源欄位補齊（Jav321/AVSOX/HEYZO/FC2/D2Pass）+ 字幕檔自動偵測搬移 + Proxy direct 模式。測試數 1007 → 1366。

## 0.4.x 系列 (v0.4.0 ~ v0.4.4, 2026-03-08 ~ 2026-03-19)

GSAP 搜尋頁動畫系統（SSE 漸進搜尋 + Mini-Burst + Grid↔Detail 共享封面轉場 + Cover State Machine）+ GSAP Showcase 動效系統（Flip 排序 + stagger 分頁 + Motion Lab）+ Lightbox 重設計（glass circle overlay + metadata panel）+ Source Link 設定 + 安裝腳本升級 + 測試套件大整合（去重 + conftest 統一 + 覆蓋率補強）。測試數 731 → 1007。

## 0.3.x 系列 (v0.3.0 ~ v0.3.6, 2026-02-08 ~ 2026-02-20)

Bootstrap → DaisyUI + Alpine.js 全站遷移 + Showcase 動態化（SQLite SSR 取代靜態 iframe）+ Search Grid Mode + 女優資料卡（Graphis + JavBus 並行）+ Fluent Material Boost（Mica/Acrylic）+ GSAP 前置基礎建設 + Scraper 擴充（D2Pass/HEYZO/DMM/gfriends/Graphis）+ 路徑工具統一（uri_to_fs_path/pathToDisplay）+ UNC 路徑修正 + 版本標記覆蓋保護 + Jellyfin 圖片模式。測試數 523 → 817。

## 0.2.x 系列 (v0.2.0 ~ v0.2.4, 2026-01-22 ~ 2026-02-07)

Design System 建立（Fluent Design 2 視覺語言 + AV Card 4 變體 + Token 系統）+ macOS 支援（Alpha）+ AI 翻譯雙引擎（Ollama + Gemini）+ 多層目錄結構 + FC2/無碼搜尋 + SQLite 本地收藏庫 + Scraper 模組化架構（5 個獨立 scraper）+ 番號後綴清理修正。測試數 126 → 564。

## 0.1.x 系列 (v0.1.0 ~ v0.1.4, 2026-01-15 ~ 2026-01-17)

初始版本發布：多來源番號搜尋（JavBus/Jav321/JavDB）+ Gallery UI + 智慧搜尋 + 批次搜尋 + NFO 自動補全 + Settings（Dark Mode + Ollama 翻譯 + 輸出格式設定）+ 新手教學（Tutorial 4 步驟）+ Windows 打包 + 路徑工具統一（path_utils）+ 版本管理集中化。測試數 115 → 311。

> 完整歷史紀錄請見 [CHANGELOG_ARCHIVE.md](CHANGELOG_ARCHIVE.md)
