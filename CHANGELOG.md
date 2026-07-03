# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [0.11.3] - 2026-07-01

本版主軸：**唯讀來源生成本地媒體庫（off 風味）**（feature/88，spec-88）——為 scanner 來源新增「唯讀」模式：勾了就不寫回來源夾，改在你指定的本地輸出夾生成一個「每片一資料夾」的媒體庫（nfo + 封面 + 劇照），並直接寫進 DB。適合把影片放在唯讀網盤／NAS 共享／Alist 掛載（不能改名搬移）的人——OpenAver 讀來源、產出整理好的本地庫，來源一個 bit 都不動，之後在 OpenAver 就能瀏覽、串流播放雲端原檔。對雲端足跡極輕（只列目錄 + 真的點播才讀那一部）。接停更的 MDCX 的棒，但預設走純文字產物、零權限門檻。

> media-server 風味（多吐 `.strm` 給 Emby/Jellyfin/Kodi 掃）＋一批 UI 調整延後至下一 branch（feature/89）；本版先交付 OpenAver 自瀏覽的完整體驗。

### Added
#### 🎯 唯讀來源 → 本地媒體庫生成（off 風味）
- **每個 scanner 來源可勾「唯讀」＋設輸出夾**：勾唯讀後不寫回來源，按既有「產生」就對該來源刮削 metadata、線上下載封面/劇照，在輸出夾生成每片一資料夾（`-poster`/`-fanart` ＋ extrafanart），並寫進 DB（`path`＝雲端原始路徑、`cover_path`/劇照指本地）。OpenAver 立即可瀏覽、從 DB 串流播放雲端原檔，封面走本地。**來源零寫入、零讀圖**（只列目錄 + 真的點播才讀那一部）。
- **手動增量、一鍵到底**：往雲盤丟新片後回 OpenAver 對該來源按「產生」，只處理新片（以 DB 為準跳過已生成的）；不背景輪詢雲盤（避免觸發網盤風控）。跑完顯示「新增／略過／刮不到／失敗」四數摘要。
- **同番號多版本防撞**：同一番號的不同版本（各自獨立 `path`）各落入獨立子資料夾、不互相覆蓋。

### Changed
- **唯讀來源整理入口給明確提示**：對唯讀來源觸發「整理（搬移/改名）」時，回明確提示「此來源唯讀，請改用生成本地媒體庫」，而非靜默失敗（含 canonical `file:///` 輸入亦正確攔截）。
- **產生完成通知反映來源失敗**：唯讀來源若整源無法存取，完成通知與 toast 走警告（不再誤報全部成功）。

### Internal
- 新增獨立 producer 服務 `core/readonly_producer.py`（全新 code surface，不重用/不碰既有搬檔 `organize_file` 與寫來源旁 `enrich_single`）；`GalleryConfig.directories` 由 `List[str]` 升級為帶 `readonly`/`output_path` 的 `DirectoryConfig`（`load_config` 加法式向後相容遷移，舊純字串 config 照常載入）＋集中存取 helper（所有 call site 走 helper，禁手寫型別判斷）；`generate_avlist` SSE 迴圈以 thread/queue 橋接 producer（worker 例外顯式接手、不靜默吞）；`/api/gallery/image` 白名單納入各來源輸出夾。DB schema／API 端點／capabilities 零變更。

### 測試
- 全套 pytest **5031 passed, 2 skipped**（unit + integration，排除 smoke/e2e，較 0.11.2 的 4848 +183：config schema/helper/向後相容遷移 + producer 列檔/增量跳過/防撞葉層/寫檔/upsert + SSE thread-queue 橋接/四數摘要/來源級例外契約 + image 白名單 + organize guard(含 file:/// 邊界) + off 風味端到端驗收）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。

## [0.11.2] - 2026-06-30

本版主軸：**core/database.py 模組化拆分**（feature/87，spec-87）——把 2,152 行的單一 `core/database.py` 重構成 `core/database/` 套件，降低 AI 輔助編輯時的長 context 出錯率。**零行為變更、零使用者可見影響、零 API/schema/SQL 變動**。分兩階段：87a 純機械搬移、87b 消除兩個鏡像 repo 的重複碼。對外 `from core.database import X` 路徑字面不變（永久 facade）。

### Internal
- **87a 套件化 + 永久 facade**：`core/database.py` 拆成 `core/database/` 套件，依領域分 `connection` / `video` / `alias` / `tag_alias` / `actress` / `migrate` 六個子模組，`__init__.py` 作為永久 re-export facade（含私有 `_migrate_old_aliases`）。19 個 production 檔與 34 個 test 檔的 import 路徑零改動；唯一 test 調整是 4 個 `get_db_path` monkeypatch target 字串機械式對齊（拆檔後子模組各持 binding 副本所致）。新增 facade export 守衛測試。
- **87b 消除 alias/tag_alias 鏡像重複碼**：`AliasRepository` 與 `TagAliasRepository` 原為逐位元鏡像（差異僅三軸：表名、SQL alias token、record 類），抽出私有共用基類 `_AliasRepositoryBase[T]`（Generic），12 個共用 method 上移、body 逐字保留僅套 `self._table` / `self._sql_alias` / `self._record_cls` 參數化。`sync_from_favorite` 維持 `AliasRepository` 獨有；CD-58-3「uniqueness 只查本表、不跨查」語意由表名參數化結構性保證。淨刪 549 行重複碼。
- 新增跨 repo 行為等價性護欄測試（參數化並列比對兩 repo 的 CRUD/resolve/uniqueness），作為 dedup 安全網。

### 測試
- 全套 pytest **4848 passed, 2 skipped**（unit + integration，排除 smoke / e2e；較 0.11.1 的 4799 +49：facade export 守衛 +1、跨 repo 等價性 +32、87a 過程零淨增、87b 淨變化 0）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live）。
- 等價性網以 mutation 實證：故意拼錯任一條 json_each 查詢即令對應 repo 測試紅燈，且跨 repo 網能定位到出錯的那個 repo。

## [0.11.1] - 2026-06-28

本版主軸：**JavLibrary 同番號多版本手動切換**（feature/86，spec-86）——AV 番號會被不同片商跨年代重複使用（如 `MIDV-013`：舊片 vs MOODYZ 新片），預設都抓到先收錄的舊片。本版讓你在 JavLibrary 看封面手動挑版本。範圍刻意極小：僅 JavLibrary、僅手動入口、桌面 standalone 限定（需 CF transport），不進批次、不揭露 AI。

### Added
#### 🎬 JavLibrary 同番號多版本切換器
- 🎯 **看封面手動挑版本**：同一番號在 JavLibrary 有多個版本（撞號）時，預覽卡出現封面 `‹ ›` 左右切換器 + 琥珀色「找到 X 部同番號作品 N/M」標示，按左右即時翻版本（封面/標題/日期/片商/tags 同步），游標預設停在**最新發行日**那部（多數人要的新片）。一次抓齊所有候選，翻頁不重打。
- 🎯 **三個手動入口都支援**：
  - **搜尋框直搜**：進階搜尋選 JavLibrary → 多版本跳預覽卡 + 切換器 → ✓「採用此版本」進結果區（不寫檔）。
  - **燈箱換來源**：對某片開「換來源」選 JavLibrary → 切換器 → ✓ 寫入選定版本的 NFO/封面（保留「覆蓋不可逆」警告）。
  - **結果卡替換來源**：先用別的來源找到、再「替換來源」成 JavLibrary 多版本 → 切換器 → ✓「替換此版本」就地替換當前卡（不寫檔）。

### Changed
- **「找到 X 部」撞號提示改琥珀色**（同不可逆警語色系，「注意」語意）更顯眼。
- **JavLibrary pill 在搜尋頁進階搜尋解除隱藏**：改由「桌面限定」gate 統一管（非桌面仍灰化不可點）。

### Fixed
- **搜尋頁挑版本後可再次開啟**：採用某版本後，exact 結果頁保留「再開來源/版本挑選」入口（不再因搜尋框與結果同步而消失）；限搜尋 workflow，批次/檔案模式不受污染。
- **搜尋頁挑版本路徑同步搜尋框 query**：採用版本後搜尋框、輸入法判斷、工作階段還原不再殘留舊番號。
- **番號邊界比對補前置**：候選列舉避免把 `AMIDV-010` 之類前置黏連號誤收為 `MIDV-010` 的版本。

### Internal
- scraper 新增同番號全版本列舉（`search_all_versions` / `fetch_by_detail_url`，新片優先排序）+ helper 抽取；後端 `/api/rescrape/preview` 多版本回 `candidates[]`、`EnrichRequest` 新增 `detail_url`（confirm server-side 重抓，不揭露 AI）；前端 rescrape modal 三入口 candidates 短狀態 + 切換器 partial。
- `core/scrapers/README.md` 的「JavLibrary 手動版本切換」由 pending → done。

### 測試
- 全套 pytest **4799 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.11.0 的 4747 +52：scraper 列舉/排序/邊界 + 後端 candidates/detail_url/CF + 前端 state/切換器/入口路由/守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live）。
- Windows 真機驗收：MIDV-013（3 版本）三入口切換器 + 採用皆通過。
- Codex PR review P2 × 2（search 採用 query 同步 / file-mode 入口 gate）已修；Gemini 整支 branch 第二意見 P1 × 1（番號前置邊界）已修。

## [0.11.0] - 2026-06-27

本版主軸：**JavBus 過度泛用清償 + exact 番號搜尋改優先序 cascade**（feature/85，spec-85）——技術債清償與行為修正，預期淨刪碼、不新增使用者功能。核心是讓「來源優先序」這個既有設定**真的被尊重**：以前直接搜番號時，只要 JavBus 有啟用就會搶先回結果（即使你把 DMM 排第一），現在改成嚴格依你拖曳的優先順序逐一查、命中即回。並移除依賴已死端點的 JavBus variant（同番號多版本）探查死碼。

### Changed
#### 🎯 exact 番號搜尋尊重來源優先序（行為分水嶺）
- **直接搜番號改為「優先序串接」**：以前 exact 番號走 fan-out 全打再 merge，且 JavBus 以「是否啟用」為門檻搶先短路——把 DMM 排第一也可能拿到 JavBus 的結果。現在改為依來源優先順序逐一查（cascade），第一個命中的來源即回，DMM 排第一就真的先查 DMM。fuzzy / partial / actress 等其他模式行為不變（已加護欄鎖定不波及）。
- **`/api/search/sources` 依設定回來源順序**：搜尋燈箱的 ⟳ 手動換源輪替順序，現在跟著你在設定頁拖曳的來源優先順序走（以前固定不變）。輪替集合維持 8 個內建來源。

### Fixed
- **DMM 在掃描產生頁 / 單片補資料時不再缺席**：`generate-from-ids` 與 `scrape_single` 路徑先前漏傳 proxy 設定，導致需要 proxy 的 DMM 在資料庫未命中時無法進場；現補齊透傳。
- **JavBus 前綴搜尋的篩選參數真正生效**：前綴搜尋 URL 的 `type` 參數先前用錯接法（`&type=` 落在路徑而非查詢字串），伺服器不解析、前綴過濾從未生效；改為正確的 `?type=`。

### Removed
- **拔除 JavBus variant（同番號多版本）維度死碼**：variant 探查依賴 JavBus 已改版回 404 的搜尋端點，永遠撈不到東西卻每次多打一次請求、增加被 ban 風險。全棧移除——後端 variant 探查與 `/api/search` 的 `variant_id` 參數、前端燈箱的 variant 輪替維度、相關死碼常數，並加 ESLint 語法樹守衛防止回流。對使用者無可見功能損失（該功能本就壞著）。

### Internal
- `normalize_number` 解耦為獨立函式，番號正規化不再無謂實例化 JavBusScraper。
- `D7` 來源順序 helper（`get_switchable_source_ids_ordered`）採 present-then-append + 限縮正規 8 內建來源：partial 設定檔下補齊缺席來源、且過濾掉 schema 合法但不可切換的未知 builtin id（避免前端輪到時打到無效來源吃 400）。
- `D8` `JavBusScraper.search_by_keyword` 補 docstring 標明非生產主路徑（介面履約的循序參考實作，不可刪）。
- 新增 `core/scrapers/README.md` 記錄各來源能力矩陣、碰撞行為與搜尋路由決策。

### 測試
- 全套 pytest **4747 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.11 的 4735 +12：cascade exact 路由 / fuzzy-partial 護欄 / proxy_url 透傳 / D7 switchable 來源 present-then-append 與未知 builtin 排除 / partial-config API order / D9 URL 格式）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- Gemini 3.1 Pro 整支 branch 第二意見：LGTM、零 P1/P2。
- Codex 評估期 P1 × 2（D7 partial-config 集合縮小 / D7 未過濾未知 builtin id）已於評估階段修正並補守衛測試。

## [0.10.11] - 2026-06-24

本版主軸：**Windows 一鍵安裝捷徑 + Help 頁更新按鈕**（feature/84）——兩條並行：84a 新增 `OpenAver-Windows-Setup.bat` 雙擊即可觸發 PowerShell 安裝流程（配合 `chcp 65001` 確保中文正常顯示）；84b 在 Help 頁（限桌面 App）新增「更新」按鈕，偵測安裝路徑後以 confirm modal 導引用戶操作（情況 A 預設路徑 / 情況 B 非預設路徑），確認後開外部終端執行安裝腳本。

### Added
#### 🪟 Windows 雙擊安裝捷徑（84a）
- 🎯 **`OpenAver-Windows-Setup.bat`**：新增於 repo root，雙擊即呼叫 PowerShell 以 `irm | iex` 方式執行安裝腳本；加入 `chcp 65001` 確保 UTF-8 終端顯示；CI Release 同步上傳此 bat 至 GitHub Release Assets。

#### ⬆️ Help 頁一鍵更新（84b）
- 🎯 **桌面 App 專屬更新按鈕**：偵測到有新版時，Help 頁出現「更新」按鈕（`is_desktop` Jinja gate，桌面 App 才顯示）。
- 🎯 **路徑分流 confirm modal**：點更新先呼叫 `/api/install-context` 偵測是否裝在預設路徑——情況 A（預設）顯示「關閉後依畫面提示繼續」；情況 B（非預設）顯示需手動搬移步驟——確認後呼叫 `/api/trigger-update` 開外部終端執行安裝腳本，操作結果以 toast 回饋。
- 🎯 **後端新增三個元件**：`_is_mac_desktop()`（macOS 桌面 App 偵測）；`GET /api/install-context`（路徑比對，非桌面回 403）；`POST /api/trigger-update`（Windows → PowerShell `CREATE_NEW_CONSOLE`，macOS → osascript Terminal；不揭露給 AI agent）。

### 測試
- 全套 pytest **4735 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.10 的 4710 +25：`_is_mac_desktop()` 真值表 + install-context 路徑算法 + trigger-update subprocess/403 + capabilities 守衛 + Help 頁 Alpine binding 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（含 avsox/dmm/javdb 全綠）。
- Gemini 3.1 Pro 審查：3 條 advisory（hardcoded URL 設計取捨、路徑推斷 fallback 保護、macOS fire-and-forget 設計），無 P1/BLOCKER。
- Codex PR review P1 × 2 已修：API `HTTPException.detail` 改固定中文字串；`_showHelpToast()` 改用 `_toast` Alpine state + `showToast()` 並補 toast DOM。

## [0.10.10] - 2026-06-24

本版主軸：**封面比例自適應 + 行動相似探索面板**（feature/83）——兩條並行：83a 讓燈箱封面不留空白（寬比例作品自動填滿容器、AR 不污染女優模式）；83b 在行動裝置新增相似探索面板（全螢幕疊加 + 六張爆射卡 + 封面飛行進/退場 + 主圖播放按鈕）。

### Added
#### 🪄 行動相似探索面板（83b）
- 🎯 **行動版相似探索**：手機/平板燈箱新增星形爆射相似面板——點 🪄 按鈕開啟全螢幕疊加，六張相似卡從中心爆射散開，中央主圖以飛行動畫從燈箱封面轉入。
- 🎯 **封面飛行進/退場**：主圖以 ghost-fly 動畫從燈箱封面飛入面板（enter），關閉時原路飛回（exit）；進退場期間播放按鈕自動隱藏，不懸空。
- 🎯 **主圖播放按鈕**：相似面板主圖底部中央有播放圓鈕（對齊桌面星空模式，44×44 Fluent 玻璃材質）；drill 動畫中鎖定、無路徑影片時隱藏。
- 🎯 **drill 並發硬化**：快速切換相似卡時舊 drill 立即中止、新 drill 接管；runId guard 確保舊的動畫/狀態不干擾新結果。

### Changed
#### 🖼️ 燈箱封面比例自適應（83a）
- 🎯 **封面不再留白**：燈箱封面改採 aspect-box/modal-hug 模型，以圖片載入事件讀取實際比例，寬比例（橫版封面）自動填滿容器，不再出現上下空白；破圖/未載入時安全回退不塌陷、不污染女優模式比例。
- 搜尋燈箱、搜尋詳情頁封面區同步採用同款模型；search detail 封面留白與劇照截斷一併修正。

### Fixed
- 修正 83a/83b-T1 引入後 `TestCoverLoadingUx67Guard` 四條守衛因 `:class has-cover` 新屬性 + T1 注釋位移雙因導致正則 stale。

### Fixed（行動 UX 優化合輯，fix/0.10-mobile-ux-polish）
- 🎯 **封面牆行動搜尋 toolbar 滾動自動收合**：≤480px 往下滾超過 50px（相對 toolbar 展開當下位置）且搜尋欄位為空時自動收合；有搜尋文字不收。
- 🎯 **封面牆 header 行動搜尋 icon 搜尋中顯示 ✕**：有搜尋條件（tag 點擊 / 女優 / 文字）時 navbar 搜尋 icon 切換為 ✕，點擊一鍵清除所有篩選；URL / persisted state 帶入的初始搜尋也正確同步 icon 狀態。
- 🎯 **Settings toast 行動版移至底部**：≤480px 時 toast 不再從頂部彈出（易被行動瀏覽器 chrome 遮住），改固定於底部顯示。
- 🎯 **伺服器模式切換加確認彈窗**：避免誤觸；點確認才執行切換，點取消維持原狀；同模式不觸發彈窗。
- 🎯 **搜尋列輸入法 compose 態 icon 互斥**：compose 態時隱藏 Grid toggle，避免三個 icon 同時顯示擠爆搜尋列空間。

### 測試
- 全套 pytest **4710 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較初版 4686 +24：行動 UX 守衛 + 伺服器模式確認守衛 + icon 互斥守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**7 PASS、1 SKIP**（jav321 unreachable，已知正常）。
- Gemini 3.1 Pro 審查：LGTM；P2（同模式觸發彈窗）已修（early return guard）。
- Codex PR review P2（showcaseHasSearch 初始化缺漏）已修（init-time sync 補齊）。

## [0.10.9] - 2026-06-22

本版主軸：**Windows 系統匣關閉行為**（feature/82）——在 Windows 點關閉視窗時可選擇「最小化到系統匣繼續背景執行」或「完整退出」並記住選擇，系統匣常駐圖示隨時喚回視窗或切換行為。核心 close-to-tray 由社群貢獻者 @YongCard（PR #77）提供，本版合併後做穩定性硬化並補上設定頁入口。

### Added
#### 🖥️ Windows 系統匣關閉行為
- 啟動即在系統匣顯示 OpenAver 圖示；關閉主視窗時以原生單選提示選擇退出、最小化到系統匣或取消，並可勾「不再顯示」記住選擇。系統匣選單與提示會跟隨介面語系，支援單擊或雙擊重新開啟視窗、切換關閉行為及完整退出 OpenAver。（感謝 @YongCard 貢獻 PR #77）
- **設定 → 系統設定 新增「關閉視窗時」下拉**：可事後改回每次詢問／最小化到系統匣／直接結束，與系統匣選單、關閉提示三方同步；此選項僅在 Windows 桌面 App 顯示。

### Fixed
- **完整退出時正確關閉 LAN 伺服器 listener**：先前 Windows 完整退出（關窗選結束／系統匣結束／強制關閉）皆未停掉對外 listener，可能造成下次啟動偶發 port 佔用；現統一在退出 chokepoint 關閉。

### Internal
- 關閉行為偏好從 `window_state.json` 搬到 `config.general`（單一真理；載入時非法／缺值一律矯正回 `ask`，不破壞舊設定載入）；持久化失敗時保留 session-local 偏好、不中斷關窗流程（best-effort，恢復搬遷前語義）。
- 原生層 grep 測試改 AST 結構守衛（防誤刪、不假驗 ctypes 行為）；ctypes 行為正確性由真機驗收涵蓋。

### 測試
- 全套 pytest **4650 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.8 的 4597 +53：LAN listener 退出 regression / close_action 注入 round-trip + session-local fallback / GeneralConfig 欄位 + 非法持久值矯正 migration / is_windows_desktop 真值表 / Settings 下拉前端守衛 / 原生層 AST 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- Gemini 3.1 Pro 整支 branch 第二意見（A 原生層 / B 整合層分群）：零 P1/P2；Codex implementation review P1（持久化失敗冒泡 UI）+ P1（session 偏好失效）+ P2（非法持久值未矯正）已修。

## [0.10.8] - 2026-06-22

本版主軸：**手機體驗完整化 + 觸控互動 + 伺服器模式 header 精修**（feature/81）——承接 0.10.7 LAN 伺服器模式，把「手機連進來後每頁都好用」補齊：窄螢幕破版修補、加到主畫面有專屬圖示、封面牆與燈箱可左右滑換片，並把設定頁的伺服器模式區塊收斂成更精簡的一排。純前端 / 零後端 API / DB 改動（help 網址顯示為既有 server 模式邏輯的呈現微調）。

### Added
#### 📱 行動完整度（窄螢幕地板 360px）
- 🎯 **封面牆行動搜尋改右上 icon**：手機（≤480px）在封面牆不再被一條搜尋列佔掉頂部空間，改為右上角一顆搜尋 icon，點開才滑出搜尋與篩選/排序控制，用完收起——垂直空間全留給封面。漢堡（左上）與搜尋（右上）各據一角不互遮。平板 / 桌面維持原樣。
- 🎯 **加到主畫面有專屬 App 圖示**：把網址加到手機主畫面會顯示精緻的 OpenAver 圖示（非網頁截圖）；開啟時手機狀態列顏色隨主題融入（深色主題深底、淺色主題淺底）。
- 🎯 **封面左右滑換片**：手機在影片燈箱（封面牆 + 搜尋）可左右滑切換上一 / 下一片，搜尋詳情頁的封面區也可左右滑換上一 / 下一筆——與既有 `<` `>` 箭頭並存，垂直捲動不受影響。劇照、相似推薦等彈窗開啟時不會誤觸換片。

### Changed
#### ⚙️ 伺服器模式 header 收斂（桌面）
- **設定頁 server-mode 收成一排**：「單機 ｜ 伺服器」膠囊移到設定標題右側；開「伺服器」時「伺服器」字以**琥珀色**突顯（＝正在對外曝露）；連線網址去掉 `http://` 只顯示 `ip:port`（複製時剪貼簿仍是完整網址）；複製鈕改純 icon；區網存取警語收進 `?` 提示，不再佔獨立第二排。
- **複製 icon 全站統一**：Help 頁的 curl 複製鈕從 `📋` emoji 改為與全站一致的剪貼簿圖示。
- **Help curl 在桌面主機顯示可分享網址**：開啟伺服器模式後，桌面主機看 Help 的 `curl` 範例會顯示可直接貼給區網其他裝置 / AI agent 的 LAN 網址（而非本機回環位址）；單機模式維持本機位址；取不到 LAN IP 時安全退回本機位址。遠端裝置本就顯示自己的網址、不受影響。

### Fixed
- **設定 / 說明頁在 360px 窄螢幕破版修補**：設定頁外部媒體管理器說明、metatube 連線網址、Help 的 `curl` 指令等長字串不再水平溢出；控件不重疊、不被截斷。
- **封面圓鈕在窄螢幕不再變形**：封面上的播放 / 開資料夾 / 補資料圓鈕在 390px 及更窄的 3 欄格下維持正圓（不再被壓成橢圓），且整體縮小、少擋封面。
- **平板 / 窄窗（481–899px）封面佈局修正**：不再出現「每列 2 個橫式全幅封面」的稀疏佈局，改為比照手機的 4 欄直式右裁封面格；封面牆切換到燈箱時不再「先放大再縮回」的破圖。
- **通知抽屜在手機不被切左緣**：≤480px 通知抽屜改為頂列下方全寬面板（不再因錨定右側鈴鐺而切掉左緣或超出視口）。
- **重刮預覽在手機可讀**：重刮預覽視窗在 360px 改為封面與資訊上下直排，不再左右互擠、文字截斷。

### Internal
- 觸控 swipe 偵測抽為共用純函式 `web/static/js/shared/swipe.js`（`detectSwipe`，含 `|dX|>|dY|` 軸判別防垂直捲動誤觸），三場景（showcase / search 燈箱、detail）各自掛載、沿用既有 prev/next 與 GSAP 切換動畫；全程 passive 不 `preventDefault`，垂直捲動零受損。
- 通知抽屜手機全寬面板改實心填底（移除 backdrop-filter），免疫 0.10.4 的 view-transition 逐格採樣 bug。
- 新增前端守衛：swipe helper 簽名 / 攔截短路串 / 容器隔離（含 detail 封面區排除水平縮圖列）、apple-touch-icon、動態 theme-color、grid 斷點 JS↔CSS 對齊、行動浮層 CSS 結構。

### 測試
- 全套 pytest **4597 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.7 的 4467 +130：swipe helper / 三場景掛載與攔截守衛、行動工具列 / poster 斷點 / apple-touch-icon / theme-color 守衛、server header DOM / clipboard icon / help base_url 守衛、行動浮層 CSS 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- **Gemini 3.1 Pro 三群（A / B / C）分別第二意見：全 Approved / LGTM、零 P1/P2**（僅 cosmetic 級 P3 建議，未採納）；Codex review P2（detail swipe 與水平縮圖列衝突）已修。

## [0.10.7] - 2026-06-21

本版主軸：**LAN 伺服器模式**——讓你在桌面 App 一鍵把這台機器開放給「同一個 Wi-Fi / 區網」的手機、平板、別台電腦，用瀏覽器連進來瀏覽封面牆、線上看片、查番號（feature/80 A 群）。預設仍是「單機」，行為與舊版完全相同。

### Added
- 🎯 **伺服器模式切換**：設定頁右上角新增「單機 ｜ 伺服器」膠囊。切到「伺服器」後下方出現一條連線網址（例如 `http://192.168.1.50:50123`）+ 一鍵複製，把網址用手機瀏覽器打開即可消費；切回「單機」立刻關閉對外。
- 🎯 **即時生效、不用重啟**：切到伺服器當下就在背景開好對外連線，手機馬上連得到，不需要關開 App；切回單機立即停止對外。
- 🎯 **Help 新增「伺服器模式」說明區**：包含怎麼用、安全提醒，以及第一次開啟時系統防火牆會詢問請按「允許」、不小心按了「取消」之後怎麼到防火牆設定救回（Windows / macOS 步驟）。

### Changed
- **單機模式不再跳系統防火牆提示**：桌面 App 平常只綁定本機回環位址（`127.0.0.1`），只有在你主動切到「伺服器」時才會綁定對外位址、觸發一次系統防火牆授權（按「允許」即可，之後記住）。舊用戶更新後維持單機、不會無端冒出防火牆提示。

### Security
- **區網存取閘門**：非本機的連線預設一律擋下（回 403），只有在「伺服器」模式下才放行同區網裝置；本機與桌面 App 自身永遠正常。不信任 `X-Forwarded-For` 偽造、連線來源無法判定時一律從嚴（fail-closed）。
- **開關型別嚴格驗正**：伺服器模式開關只接受布林真假值，擋掉字串 `"false"` 這類會被誤判成「開啟」的輸入，避免意外對外開放。
- 伺服器模式開關**不揭露給 AI agent**（capabilities 守衛把關），避免 agent 自行把機器切成對外開放。

### Non-Goals（本版不含、已規劃）
- **手機完整度**（Settings / Scanner / Help 在 360px 窄螢幕的破版補丁）延後至 feature/81；目前手機連入後 search / showcase 主消費頁已相容，設定 / 掃描頁在極窄螢幕仍有少量排版瑕疵。
- **外網存取 / 帳號密碼 / Web 目錄選擇器 / Docker・NAS 部署**：本版定位 LAN-only 個人 / 家庭用，外網請自接 VPN（如 Tailscale）；NAS 一鍵部署留 epic-synology。

### Internal
- Dual-listener 架構：主回環 listener 永遠運行，伺服器模式由 thread-safe 的 `LanListenerManager` 動態起停第二個 `0.0.0.0` listener（`lifespan="off"` 共用同一 app、不重跑啟動初始化）。
- toggle 端點交易一致性：啟用先起 listener 成功才寫設定（寫入失敗則回滾停掉 listener）；停用先寫設定（閘門即時生效）再停 listener——runtime 與持久化狀態不分離。
- 開發 / 伺服器部署（直接跑 uvicorn、未經桌面啟動器）下膠囊優雅降級回錯誤提示，不崩潰。

### 測試
- 全套 pytest **4467 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.6 的 4435 +32：LAN 閘門矩陣 / listener 生命週期 / toggle 端點 / HOST 拆分 AST 守衛 / 前端膠囊・橫條守衛 / capabilities 守衛）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- **Gemini 3.1 Pro 整支 branch 第二意見：LGTM、零 P1/P2/P3**（架構 / 安全 / rollback / AST 守衛獲正面評價）；Codex review P1×2 + P2 已修（toggle 交易一致性 / 例外不外洩前端 / banner 訊息精準）。

## [0.10.6] - 2026-06-21

本版主軸：**前端離線可靠性**——把第三方套件打包進本機、前端錯誤可觀測、修精簡版 Windows 上的啟動問題（feature/79）。

### Added
- 🎯 **離線可用**：GSAP / Alpine.js / 圖示字型改從本機載入，斷網或 CDN 連不到時介面仍完整可用（封面牆、燈箱、動畫、所有互動照常運作）。
- 🎯 **前端錯誤自動記錄**：前端發生錯誤時自動寫進本機 debug.log（純本機、零外送），方便日後排查問題。（背景靜默，一般使用無感）

### Changed
- 🔒 **依賴版本鎖定（可重現建置）**：`requirements.txt` 全面精確鎖版（exact-pin）到已測版本，`requirements-test.txt` 與 macOS 打包都改為繼承 / 安裝同一份鎖版——同一版本號每次都打包出**相同的依賴版本**，避免上游套件靜默升級造成非預期行為。

### Fixed
- 🔒 鎖定 Starlette 至最新修補版 1.3.1，清除 ASGI 底層全部已知安全通報——含 Windows 上透過 `/static` 特製路徑觸發對外 SMB/NTLM 連線洩漏帳號雜湊（CVE-2026-48818）、表單請求資源耗盡 DoS（CVE-2026-54283）等。
- 修正精簡版 / 部分第三方工具處理過的 Windows 上，某些頁面（如掃描頁）按鈕失效、顯示異常的問題（MIME 強制宣告，issue #66）。
- 修正影片燈箱開啟刪除確認框時，按 Esc 會連燈箱一起關、方向鍵會跳到下一部影片的問題。
- 修正掃描頁在模組未載入時顯示 `[object HTMLElement]` 的小問題（改為乾淨空白）。
- 修正 Windows 偵錯啟動檔（OpenAver_Debug.bat）未開啟完整偵錯日誌的問題（對齊 macOS）。

## [0.10.5] - 2026-06-21

本版主軸：**開發工具鏈硬化——lint 守衛進 CI、ruff 補 Python 缺口、清殭屍工具**（feature/78）。純開發工具鏈，**產品 runtime / API / DB / UI 零改動**，產品仍零 node 依賴（node 只在 CI runner）。緣起：前端 lint（eslint + stylelint）過去純本地、CI 只跑 pytest，沒人本地跑就漏；Python 端缺自動守衛（unused import / bare except / 閉包 loop-var 等無人擋）；mypy config 齊全卻從不執行＝假象保護。本版把「擋得住回歸」這件事接上 CI，不再靠開發者記得本地跑。

### Added
- **ruff 導入**：新增 `pyproject.toml`（`[tool.ruff]`，6 規則族 E722/F/B/T201/S110/S112，排除 venv/tools/tests）。存量 184 處違規清零、行為保留：unused import/var 自動修；`raise ... from e`、`zip(strict=)`、閉包 loop-var 綁定等逐條手動修（皆與原行為逐位元相同）。
- **CI lint-frontend job**：`.github/workflows/test.yml` 新增平行 job 跑 `npm ci` + `npm run lint`（eslint + stylelint）+ `ruff check .`，與既有 pytest job 各自獨立擋 PR。
- **CI/工具鏈守衛測試**（`tests/unit/test_ci_workflow_guard.py`）：防 lint job 被靜默移除、ruff 版本兩處漂移、mypy 殭屍復活。

### Changed
- **package-lock.json 進版控**：移除 `.gitignore` 排除行，CI `npm ci` 可重現安裝、鎖定 eslint/stylelint 版本不漂移。
- **ruff 版本鎖定**：`requirements-test.txt` 與 CI 兩處精確 pin `ruff==0.15.17`（lint 是 PR gate，避免 upstream 自動升級在 repo 無改動下讓 CI 轉紅），並以守衛鎖成單一真理源。

### Removed
- **mypy 殭屍**：刪 `mypy.ini` + `requirements-test.txt` 的 mypy / types-requests（config 齊全但 CI 從不跑、歷史 findings 無一條 mypy 可抓）。

### Internal
- **path_utils 契約守衛擴及 `tests/`**：手寫 `file:///` / `[8:]` strip / shadow path helper 在測試碼也擋；先修守衛自傷（自描述文字加 `# path-contract-ok` 錨點）再擴範圍，真違規清零。
- **AGENTS.md `Out of scope` 增量**：新增 Ruff 子段（哪些 Python 問題已由 ruff 接管、reviewer 不再人肉 flag）+ path_utils 契約行；修正過時宣稱（unused var 已歸 ruff）。
- **backstop 保守審計**：lint 進 CI 後逐條審 `test_frontend_lint.py`（182 class）哪些可退役——本版 0 退役（可表達為 lint rule 的重複守衛前幾輪已退，現存皆 HTML 掃描 / 跨檔 contract / line-allowlist 等 lint 不可表達者）；大規模 deflation 留 milestone。
- 新增 `PyYAML` 明確宣告（CI guard 自己的依賴，不再吃 transitive）。`build.py` EXCLUDE_PACKAGES 加 ruff、移除 mypy 殘留（防進 ZIP）。

### Non-Goals（明確不做）
- 不採 `ruff format` / black / pre-commit hook（避免大 diff 汙染 blame、擾 commit 流程）；不全開 ruff 規則（只選定 6 類控存量）。
- 不為拉型別覆蓋率補 type hint（**刪** mypy，不是餵它）。
- 不在本版做 JS 硬編碼 CJK 守衛（eslint AST 不適用、需先 i18n 化現有字串 → 綁下次 milestone i18n sweep）。
- 不動產品 runtime / API / DB / UI；不把 node 帶進產品 ZIP；不重寫 `test_frontend_lint.py`（大規模 deflation 留 milestone）。

### 測試
- 全套 pytest **4367 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.4 的 4355 +12：新增工具鏈守衛 + ruff 清理觸發的重收集）+ `ruff check .` 綠 + `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。

## [0.10.4] - 2026-06-20

本版主軸：**Fluent 材質系統全站統一 — 6 角色材質 + B 浮動 chrome**（feature/77）。純前端、零後端／API／DB、**theme.css 全程零改**——所有材質規則寫進全站最後載入的 `fluent-materials.css`（source-order 覆寫），永不觸發 Tailwind recompile。全部 `[data-theme="dim"]`-scoped（light 模式維持現狀；dim 下材質才生效，避免 light 引用未定義 token 導致背景消失）。把過去零散的「材質三層」收斂成一套**單一 token 系統的 6 角色**：Mica canvas（整頁氛圍）→ Glass shell（側欄／頁首／工具列等殼層）→ Glass panel（閱讀面）→ Glass caption（卡片標題條）→ Glass overlay（燈箱／modal／popover／抽屜）→ Media frame（星空外框）。封面海報維持 100% 乾淨（不加任何 blur／tint，封面是主角）。並把「浮動圓角玻璃條」從 showcase 工具列擴及 search 搜尋列與 settings／scanner 頁首，桌面 chrome 視覺統一。

### Added
#### 🎨 6 角色 Fluent 材質系統（77a / 77b）
- **Mica canvas**：body 整頁漸層氛圍底（fixed、無 blur、隱形級顆粒 grain ~0.03 soft-light），全站 dim 套用。
- **Glass shell**：sidebar／頁首／工具列／footer／手機 nav・抽屜統一毛玻璃殼層（blur-light + saturate + 邊緣高光 inset）。
- **Glass panel**：Settings／Help／Scanner／Search 閱讀面卡片（較重 blur）；卡內子面板只用 sub-tint 不疊第二層 backdrop-filter（避免糊上加糊 + GPU 浪費）。
- **Glass caption**：grid 卡底部標題條改玻璃漸層（gradient + fill，hover 升不透明），**封面海報零材質**、**卡片不加 per-card backdrop-filter**（90 卡效能）；hover 收斂出貨值並中和舊 accent glow。影片卡與女優卡同步。
- **Glass overlay**：lightbox 改單一連續玻璃 shell（metadata 退為 hairline 分隔、非卡中卡）；modal box 用專用 uniform fill token 保護密集文字；help popover／variable-menu／scanner 資料夾下拉／通知抽屜統一浮層玻璃。
- **Media frame**：星空中央封面補 neutral hairline border、與 slot 外框共用同一 token（dim 下整片一致）。

#### 🛸 B 浮動 chrome（77c）
- **showcase 工具列**圓角浮動玻璃條（封面從底下滑過）；**search 搜尋列**桌面（≥1024px）同款浮動圓角（mobile 維持全寬層架，行動相容不變）。
- **Settings／Scanner 頁首**桌面浮動圓角 + 四邊框，並修正標題文字貼左緣（補水平 padding）；置中窄欄頁採「欄寬對齊」（不側內縮，避免與下方滿欄卡片左緣錯位）。

#### 🌗 chrome 置頂條 dim↔light 主題一致（77d）
- **search 搜尋列／Settings／Scanner 頁首／showcase 工具列**的浮動圓角玻璃從原本只在 dim 生效，擴及 **light 模式**——同一條 chrome 在深色／淺色主題下形狀（圓角／浮動／邊框）與材質（玻璃）一致（先前 light 下這些置頂條無浮動、無玻璃，與 dim 長得不一樣）。
- **light 玻璃**為近白霜面 acrylic：半透明 fill（base-100 @55%）+ backdrop blur + 細暗髮絲邊框，深色文字／icon 維持可讀；以 DaisyUI base 調色盤 derive（theme-aware，不硬編碼）。
- **範圍限定**：只置頂條 shell 角色雙主題；其他材質角色（panel／caption／overlay／media-frame）與其餘 shell 面（sidebar／offcanvas／top-navbar／footer）維持 dim-only、light 現狀不變。

### Changed
- **lightbox / modal 由實心 surface 改浮層玻璃**：燈箱內容與 modal 框從 `--surface-2` 實心改為玻璃材質（padding-box／border-box 邊框漸層 + backdrop-filter）；燈箱背幕 scrim 維持中性、封面不染色（否決環境光取色方案）。

### Fixed
- **search 燈箱背景「逐格模糊」（POC 否決效果意外引入）**：search 開 lightbox 時背景每張封面各自被模糊、footer 番號卻銳利（showcase 是整片均勻糊）。根因為 feature/76 給 `#main-content` 加的 `view-transition-name` 使該元素成為 backdrop root，破壞 `position:fixed` 燈箱 scrim 的 `backdrop-filter` 跨格採樣。修法：用 `:has()` 僅在燈箱開啟時退掉該 vt-name（純 CSS、零 JS、feature/76 導航轉場保留），背景恢復整片統一模糊。
- **Settings／Scanner 頁首標題貼左緣**：補水平 padding，文字離邊。

### Internal
- 材質規則 **shell 角色置頂條（search／頁首／toolbar）77d 起雙主題**（dim + light，消費同名 shell token，light 值另定義於新 `[data-theme="light"]` 區塊）；**其餘材質角色與 shell 面維持 `[data-theme="dim"]`-scoped**（light IACVT 安全）。blur 一律走 token（無 hardcoded `blur(30px)`）；每處 `backdrop-filter` 雙寫 `-webkit-backdrop-filter`（macOS WKWebView）。
- 守衛測試套件 `tests/unit/test_fluent_materials_guards.py` 由 12 → **14 條**：77d 改寫 3 條（#2 backdrop 角色分流＝置頂條允許非 dim、其餘須 dim；#10/#11 浮動幾何改 theme-agnostic 斷言）+ 新增 2 條（`test_light_shell_tokens_complete`＝6 個 shell token 須同存 dim+light block 防 IACVT；`test_non_shell_roles_stay_dim_scoped`＝panel／caption／overlay／media-frame 須維持 dim-scoped 防 S-2 越界）。dim-scope／`-webkit-`／no-blur 三條仍標 `[CI-backstop]`（CI 只跑 pytest，stylelint 純本地）。
- 移除 Design System 頁舊「Materials Layer System」demo（HTML subsection + `.ds-material-*` CSS 共 306 行），已被新 `#ds-fluent-materials` 6 角色 demo 完整取代；不留殭屍。

### Non-Goals（明確不做）
- **不動 theme.css**（全寫 fluent-materials.css 覆寫層，免 recompile footgun）、**封面海報零材質**（不加 blur／tint，封面是主角）、**caption 不加 per-card backdrop-filter**（90 卡效能）、**light 材質僅 shell 置頂條雙主題**（77d；其餘角色維持 dim-only、light 現狀不變，不做全材質 light 移植）、**不做封面環境光取色**（scrim 中性）、**不 SPA 化 / 不改後端任何路由・API・DB**。

### 測試
- 全套 pytest **4355 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.3 的 4334 +21；77d +2 守衛）+ `npm run lint`（eslint + stylelint）綠。
- `TestFluentMaterialsGuards` **14 條**（含 3 條 `[CI-backstop]`；77d 改寫 3 + 新增 2）。
- 視覺驗收（CP-B1 / CP-C1）：dim 下 showcase／search／settings／scanner／help 五頁材質 + 浮動 chrome，由 owner 真機眼驗（純視覺，不跑 e2e 截圖）。
- 視覺驗收（CP-D1，77d）：light↔dim 並排，chrome 置頂條形狀＋材質一致、light 玻璃對比可讀，由 owner 真機眼驗並拍板採更玻璃版（fill 55% / saturate 140%）。

## [0.10.3] - 2026-06-20

本版主軸：**MPA 跨頁無縫轉場（Cross-Document View Transitions）**（feature/76）。純前端、零後端/DB/依賴。每次點 sidebar 切頁的白屏閃爍消失，改為主內容區約 250ms 平滑淡入淡出（crossfade），sidebar／logo／通知鈴鐺等持久殼元素視覺靜止不重繪——用瀏覽器原生的跨文件 View Transition 達成，不需 SPA 化、不引入前端路由。漸進增強：不支援的舊版 WebView2／瀏覽器、開啟「減少動態效果」的用戶自動退回現狀硬切，功能零損失、UI 零差異。Showcase 因常駐動畫（燈箱環境光／相似探索星空）與大頁快照成本退出轉場、維持硬切。另含兩個一併修掉的問題：主題切換圓形展開被新命名群組破壞、以及 showcase／search 狀態框在前端初始化前的閃爍（FOUC）。

### Added
#### ✨ 跨頁無縫轉場
- 點 sidebar 切頁（搜尋／掃描／設定／說明之間）從「白屏＋整頁重建」變成「主內容區平滑淡換」；左側 sidebar 與頂部鈴鐺視覺靜止、像焊在原地。
- 純 CSS 啟用（`@view-transition`）＋命名持久區，零 JS 攔截導航——保留瀏覽器原生語義（Ctrl/⌘+點擊開新分頁、右鍵選單等照常）。
- 漸進增強：不支援的環境與「減少動態效果」偏好自動硬切退化，無報錯、無功能損失。
- 小螢幕漢堡選單（offcanvas）導航同樣有轉場。

### Changed
- **Showcase 退出轉場（維持硬切）**：showcase 是全站最重頁且有常駐動畫，進出一律即時硬切（`<head>` 內 parser-blocking script 於 `pageswap`／`pagereveal` 依目的地 URL 呼叫 `skipTransition()`），避免動畫被拍成凍結幀、並省去大頁快照成本。

### Fixed
- **主題切換圓形展開被跨頁命名群組破壞**：跨頁轉場用的 `view-transition-name` 對同頁的主題切換動畫同樣生效，導致 sidebar／主內容脫離整頁快照、圓形展開失效。修法：主題切換期間暫時取消兩區命名、塌回整頁單一快照（specificity 提升、不論順序皆勝）。
- **Showcase／搜尋頁狀態框初始化閃爍（FOUC）**：載入中／空狀態／錯誤三個狀態框缺 `x-cloak`，前端框架啟動前會裸露疊閃一幀；補齊 `x-cloak`（showcase 5 處、搜尋頁 1 處）。

### Internal
- 設定頁既有的主題切換 root 轉場規則作用域化（`html.theme-transition-active` 前綴），不再汙染導航到設定／設計系統頁的整頁淡換。
- stylelint 禁止手動 `view-transition-name: root`；新增跨檔 DOM／CSS 契約守衛（命名／作用域／showcase head script 位置與 parser-blocking／state-page x-cloak，後者以 BeautifulSoup 抓取不受屬性順序影響）。

### Non-Goals（明確不做）
- 不 SPA 化、不引入前端路由、不用 HTMX 整頁 swap、不做共享元素（封面跨頁飛行）轉場、不加 loading bar／骨架屏／prefetch、不在設定加轉場開關、不改後端任何路由／API。
- 守衛路徑（設定未存檔／掃描串流中放棄離開）的程式導航維持硬切（owner 簽核；程式導航本就不觸發跨文件轉場、現狀即硬切、零回歸）。
- showcase 狀態框硬編碼字串的多語系化留 milestone。

### 測試
- 全套 pytest **4334 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.2 的 4308 +26）+ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- 新增測試：`TestPageTransitionDomGuard`（命名 / showcase opt-out / head script 在 head 且 parser-blocking）、`TestPageTransitionSettingsScopeGuard`（settings root 作用域化 exhaustive negative + theme-transition.js class lifecycle）、`TestStatePageCloakGuard`（bs4，showcase 5 / search 2 state-page x-cloak）。
- 跨瀏覽器實機（CDP Chromium 146）：showcase↔他頁雙向硬切（skip）、非 showcase crossfade、主題切換期間命名塌回 root、各頁 console 0 error。

## [0.10.2] - 2026-06-19

本版主軸：**前端呈現優化合輯——行動裝置相容 + 搜尋詳情資訊密度重排**（feature/75）。純前端（CSS / Jinja template / 少量 JS 門檻），**零後端 / DB / serializer / API 改動**。緣起：owner 籌備開放同 LAN 手機連上同一台 server，把三組「以後再說」的呈現痛點推進「本版必修」——搜尋詳情右欄稀疏、翻譯標題沉底；JAV 橫式完整封包封面被裁得帶脊帶封背；以及 hover-only 操作 / scroll trap / JS↔CSS 斷點不一致 / tablet toolbar 裂版等讓真實手機無法操作的缺口。本版分兩階段（plan-75a：封面裁切共用規則 + 行動基礎相容 + 手機相似模式；plan-75b：搜尋詳情重排 + showcase 影片卡 poster 格），並追加燈箱封面去 letterbox 死白、grid→燈箱動畫落地接縫修復，最後把整套行動修正移植到結構近乎雙胞胎的搜尋頁。

### Added
#### 🔍 搜尋詳情資訊密度重排（US1）/ Search detail density rework
- 中文翻譯標題區塊從右欄最底**上移到番號下方、metadata 上方**（不再需捲過 8 個稀疏 row 才看到翻譯）；右欄加寬 320→390px；取消 `.av-card-full-body` 撐高（top-pack，消除大視窗下片名與 metadata 間的拉伸留白）。
- metadata 改**雙欄緊湊排版**：發行日期｜片長、片商｜廠牌各兩兩並排（`.info-grid-pair`），演員 / 系列 / 導演 / Tags 各佔獨行；全欄改 inline label-value（取消舊「label 在上、值在下」block 排法）。≤1024px 折疊單欄時雙欄自動回單欄。

#### 🖼️ 封面正面裁切共用規則（US2）/ Poster-crop shared rule
- 新增 `--poster-crop-ratio`（≈0.71，直式）CSS 變數作單一真理；JAV 完整橫式封包封面只露「封面正面」（`object-position: right center`，取消舊 `100% 20%` 帶脊帶封背的裁法）。星空 slot / 相似主片 / motion-lab clip 三處裁切點統一引用同一規則。

#### 📱 行動裝置基礎相容 + 手機相似模式（US3 / US4）/ Mobile compatibility + similar mode
- **US3 四小修**：搜尋詳情手機可垂直捲動（解 scroll trap）；星空白屏修復（JS bail-to-mobile 門檻與 CSS 隱藏門檻對齊 768→960）；`pointer: coarse` 觸控裝置下 showcase 影片卡 overlay / footer 標題 / 女優卡 overlay 常駐可達（不需 hover）；tablet（769–1023px）toolbar 補規則不裂版。
- **US4 手機相似模式重整**：手機點星空進「主片 + 4 相似推薦」乾淨視圖——修好「只渲染 2 片 / 點不到 / 主片文字被蓋」，相似區移到 metadata 前、主片精簡呈現、4 片全可見可點。

#### 🎴 行動裝置 showcase + 搜尋影片卡 poster 格（US5 / T9）/ Mobile poster grid
- **≤480px** showcase 影片卡改**直式 3 欄 poster 格**（比照女優格），番號單行 ellipsis、女優名次行隱藏；桌面 / tablet 維持橫式 3:2 不變。
- **搜尋頁 grid+lightbox 同款行動修正**（T9）：搜尋頁是 showcase 的近雙胞胎（共用 showcase.css / ghost-fly / 燈箱 DOM、卡片 class 相同），把 3 欄 poster 格 / caption / 觸控 footer 還原 / 燈箱封面去 letterbox / grid→燈箱動畫旗標全部 port 到搜尋頁；全進 search.css，showcase 端零改動。

### Changed
- **燈箱封面貼合原圖比例消死白**（T8）：≤480px 影片燈箱封面從 `object-fit:contain` 在 60vh 高框 letterbox（上下大片死白）改為貼合原圖比例（容器 + img 皆 gate `.has-cover`）；副作用順帶根治 grid→燈箱動畫落地的 cover→contain 接縫（盒比例=圖比例後兩者等價）。女優燈箱、無封面 / 404 影片燈箱皆以 `.has-cover` 三條件排除、不受影響。

### Fixed
- **grid→燈箱 ghost-fly 落地變形**（T7）：≤480px poster 格縮圖（cover 右半）飛進燈箱（完整封面）落地瞬間 cover→contain 硬切變形；改為 ghost 對齊縮圖右裁 + 落地 0.12s crossfade 溶接（女優模式比例對稱、無此問題）。
- **觸控 poster 格番號 caption 被標題層蓋住**（Codex P1）：US3c 的 `@media(pointer:coarse)` 無條件把 `.footer-default` 藏起、改顯 `.footer-hover` 標題層，導致 US5 的番號截斷作用在不可見層；補 `≤480px ∩ pointer:coarse` 交集規則還原番號層。
- **無封面 / 404 影片燈箱塌盒**（Codex P2）：`.has-cover` gate 加上 `!actressLightboxMode() && !!cover && !_heroLightboxImageError` 三條件，避免封面缺失時 `min-height:0` 把 cover 區（含絕對定位的 placeholder / 動作鈕）塌成 0 高。

### Internal
- poster-crop / has-cover / posterCrop 旗標等裁切邏輯一律封裝在 `ghost-fly.js` / token，呼叫端（state-lightbox.js / grid-mode.js）只傳中性旗標，守住 `test_ghost_fly_cropmode` 邊界。搜尋頁 port 採 Parallel（獨立 `.search-grid` / `.search-container` 規則）而非 widen showcase 選擇器，避免動到已驗證的 showcase 規則與守衛；判別子用 `.search-container`（頁面根）隔離兩頁。
- 新增 stylelint rule 禁 `object-position: 100% 20%`（CSS 層），inline HTML 與 selector-scoped 檢查走 pytest（依 CLAUDE.md lint 守衛路由）。

### Non-Goals（明確不做）
- **不做完整 RWD 星空**（手機正確 fallback 到靜態相似列表，星空動畫保持桌面專屬）、**不為無碼封面特判裁切**（一律套同一右裁規則）、**不改後端搜尋路由 / DB / serializer / API 欄位**（pure frontend）、**不改桌面/tablet showcase 影片卡橫式 3:2**、**不在搜尋詳情新增 plot/description 欄位**（只重排現有欄位）、**不改 showcase 燈箱桌面版 metadata 排版**。

### 測試
- 全套 pytest **4308 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.10.1 的 4249 +59）+ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- 新增測試：US1 搜尋詳情重排守衛（標題置頂 / grid-pair / id 保留 / 右欄 CSS）、US2 poster-crop token + 三裁切點、US3 門檻對齊 + similar safety、US4 手機相似 DOM 順序 + JS 門檻、US5 showcase 3 欄 + poster-crop scope + caption、T7 ghost-fly crossfade 契約、T8 cover-fit、T9 搜尋頁 port（`TestUS9SearchGridMobileFix`）等前端守衛；既有 `TestSwitchSourceBtnRemoved` regex 隨 US1 DOM 重排更新。
- **transient-guard**（下個 milestone 評估刪除）：本版多條「單向遷移後不回退」負向守衛——US1 footer wrapper rename、poster-crop 值/門檻遷移（`100% 20%` / `width:120px` / `4/5` / threshold 768 / 單欄 `1fr`）等標記 `[transient-guard]`；`TestSimilarSlotGsapGuard` 的整檔 JS 字面 ban 屬「應為 eslint 但 CI 未跑 eslint」的 CI backstop，保留至 `npm run lint` 進 CI。

## [0.10.1] - 2026-06-18

本版主軸：**進階搜尋發現性重設計（來源膠囊常駐化）+ 畢業退 toggle + 全面零長壓**（feature/74）。「自訂來源搜尋／挑來源重刮」這個 power 功能過去只能靠**隱形長壓**觸發——畫面零提示、桌面用戶幾乎不長壓，等於對沒讀文件的人隱形；而 🔄 鈕又一顆扛兩意圖（tap=重整、長壓=挑來源）。本版把「來源範圍」從隱藏模式改成**處處可見的來源膠囊**：搜尋列打字後浮出「自動」膠囊（點開挑單一來源）、結果面板把 🔄 換成常駐「目前來源膠囊」（顯示這筆是哪個源找到的 + 點擊換源）、換來源預覽改用唯讀膠囊讓截圖一眼辨識來源。同時**全面移除所有長壓手勢**（覆寫舊「降級保留」決定）、把 Showcase 進階重刮收斂到燈箱齒輪 ⚙，並讓進階搜尋正式**畢業為永久常駐核心**（移除 Settings 開關 + config 欄位 + 一次性 migration）。**後端搜尋路由零改動**（Active Row 仍是唯一真理，本版只改入口可見性）。

### Added
#### 🔎 搜尋列常駐「自動」來源膠囊（US1）/ Always-on auto source pill
- **搜尋列打字後、送出前**（compose 態，番號／女優／前綴模式皆同）在提交鈕左側浮出一顆低調的「自動」來源膠囊，作為「挑來源」的可見把手；**空框不顯示**（維持 Spotlight 乾淨）、**一送出搜尋即隱藏**（出處改由結果面板膠囊承擔，避免重複/誤導）、改動查詢字回 compose 態重新出現。
- 點膠囊開來源 picker，挑某源即以該源跑一次精確搜尋（沿用既有行為）；膠囊用可點互動樣式（pointer + hover），看得出可點、非純標籤。
- **一次性語意**：不記憶、不黏著、不 override Active Row 自動路由（預設搜尋仍走 Active Row 排序）。

#### 🏷️ 結果面板「目前來源膠囊」取代 🔄（US2）/ Result-panel current-source pill
- 搜尋結果 detail 面板**移除 🔄 重新整理按鈕**，原位置改放「目前來源膠囊」：顯示這筆結果是哪個源找到的（有碼藍／無碼綠色彩編碼），點膠囊開來源 picker——picker 內「自動」＝原 🔄 的「換到下一個來源」循環、某具體源＝換成該源的結果（in-place 替換當前卡）。
- 換源／循環中膠囊呈 loading、失敗 shake、完成後即時反映新來源；↗（開原始連結）／📁（本地徽章）行為不變。

#### 🖼️ 換來源預覽顯示來源膠囊（US3）/ Rescrape-preview source pill
- showcase 換來源／重刮的「預覽確認」步驟，把「你剛挑的來源」從純文字「· JavBus」改成 `source-pill` 呈現，採**唯讀 flat 變體**（無 hover、無 pointer，與可點膠囊一眼可分）——確認/截圖時一眼辨識用了哪個源。零 DB 欄位、零 serializer 改動。

### Changed
#### 🚫 全面移除長壓手勢（US4 + 跨 US 原則）/ All long-press gestures removed
- **所有入口的隱形長壓全部移除**（覆寫舊「長壓不刪、只降級」決定，owner 2026-06-18 拍板）：搜尋列提交鈕、結果面板 🔄、Showcase 封面牆／燈箱補資料鈕——次要動作改為看得見的控件或收斂到既有可見入口。
- **Showcase 補資料鈕 🔍**：`tap`＝自動補資料維持不變；長壓移除。**進階重刮／換源收斂到燈箱齒輪 ⚙**（本就可見）——grid 小卡只保留「自動補資料」一個動作，要指定來源重刮就進燈箱點 ⚙。
- 長壓基礎設施本體（`long-press.js` helper、兩頁 mixin 接線、design-system 長壓 demo card）全數退役——全 codebase 零長壓。

#### 🎓 進階搜尋畢業、永久常駐（US6）/ Advanced search graduated to always-on
- **Settings 移除「進階搜尋」開關**：自 v0.9.8 default-on、v0.9.10 de-Beta 後長期穩定 → 正式畢業為永久常駐核心；來源膠囊與 picker 永遠可用、燈箱齒輪 ⚙ 常駐顯示（不再被開關綁架）。
- **移除 `advanced_search_enabled` config 欄位** + 一次性 load-time strip migration：舊 config.json 殘留任何值（含 `false`）載入時即刪除並存檔（**刻意覆寫舊偏好**——畢業核心功能不被舊設定半殘；反轉 v0.9.8「保留偏好」設計）。缺 key 則 no-op、冪等。

### Help / i18n
- **Help 文案改寫零長壓（zh_TW）**：進階搜尋 picker 五入口教學從「長壓送出鈕／🔄 長壓／缺卡長壓／燈箱 ⚙」改寫為新可見控件模型（搜尋列「自動」膠囊／結果面板來源膠囊／補資料鈕 tap 自動補／燈箱 ⚙ 進階重刮），不再教不存在的手勢；移除 Settings 進階搜尋 toggle 相關文案 key（保留 metatube keyword hint）。
- **zh_CN／en／ja 文案 + 2 個 tooltip key（`search.auto_pill.tooltip`／`search.source_pill.tooltip`）milestone 同步**（owner 拍板多語系重複內容等 milestone）；其間非 zh_TW 用戶 help 暫留舊敘述（已知可接受）。README／README_EN 無長壓敘述，不動。

### Internal
- source-pill 抽 Jinja macro（`_macros/source_pill.html`）共用，三處（搜尋列／結果面板／換源預覽）覆用同一元件；新增 `.source-pill--flat` 唯讀變體 CSS（保留色彩 tint、關掉 pointer/hover/focus 互動）。
- picker「自動」cycle rewire（結果面板膠囊接 switchSource 循環）；rescrapePreview effective source 計算（auto→實際 `_source`）。
- 長壓退役連帶清除 `rescrapeEnabled()` / `window.__ADVANCED_SEARCH__.enabled` gate（齒輪 `x-show` 改常駐）、`'enrich'` entryPoint 文字殘留（純註解、無真死分支）；mergeState 鏈只移除 `longPressState` 一行、不改 spread（保 getter reactivity）。

### Non-Goals（明確不做）
- **不改後端搜尋路由**（Active Row 仍是唯一真理，本版只改入口可見性）、**不為 showcase 既有影片補「來源出處」DB 欄位**（換源預覽膠囊顯示的是「剛挑的源」非「原紀錄來源」）、**搜尋列膠囊不做持久黏著範圍**（不記憶、不 override 路由）、**不保留任何長壓加速鍵**、**不為 grid 卡新增進階重刮入口**（收斂到燈箱齒輪）、**US6 只退總開關**（逐源 enable/disable、Parts Bin、Active Row 排序全保留）、**不做一次性 coachmark**、**JavLibrary 進搜尋列（接 CF flow）列可選 follow-on、本版不含**。

### 測試
- 全套 pytest **4249 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。
- 來源金絲雀：**8 源全 PASS**（pre-merge live 健康檢查）。
- 新增測試：`TestMigrationAdvancedSearchEnabled`（config 欄位 strip migration 3 案）+ source-pill macro／搜尋列膠囊 state gate／結果面板膠囊／flat CSS／換源預覽膠囊／效力來源等前端守衛；退役 toggle/gate/長壓 helper-mechanics/demo 守衛（畢業退役多於新增，4258→4249）。
- **transient-guard**：本版多條「單向遷移後不回退」負向守衛（bootstrap 去 enabled / 長壓退役 / toggle 退役 / 齒輪去 gate 等）標記下個 milestone 評估移除。

## [0.10.0] - 2026-06-18

本版主軸：**來源穩定性 + 測試硬化**（feature/73，0.10 線首版）。不是新功能，是**可信度硬化**——讓你相信「來源還活著、parser 沒爛、我的 NFO 不會被默默寫壞」。兩個觸發點：外部 AI 審查回報「測試覆蓋率不足」（查證後確認帳面被 smoke skip 低估，但流程定型前的歷史真債確實存在，最高風險是會改寫用戶 NFO 卻零測試的 `nfo_updater`），以及用戶回報 Tokyo Hot 番號（`n0762`）永遠查不到。本版做了六件事：把 8 個來源用真實番號做成「健康金絲雀」smoke 套件（連不上只警告、改版才報紅）、修掉 Tokyo Hot 單字母番號被誤插 hyphen 的 bug、清償五項離線單元測試真債、立覆蓋率流程地板防老債再被遺忘、復活站方轉 SPA 後失效的 avsox 來源、並把舊 smoke 與金絲雀重疊的冗餘測試整併清掉。

### Added
#### 🐤 8 源真實番號健康金絲雀 smoke 套件 / Source canary smoke suite
- **新增 `tests/smoke/test_source_canary.py`**：對 8 個 fan-out 來源（有碼 javbus/jav321/javdb/dmm + 無碼 d2pass/heyzo/fc2/avsox）各用 3~5 個常青真實番號做真連線健康檢查。**三態判讀**：連不上/逾時/404/空結果 → **skip + 警告**（無碼片易下架、javdb 查多被 ban 都正常，不擋 PR）；拿到正常 HTTP 回應卻解析空 → **fail**（網站改版打死 parser，這才是要修的）；拿到 Video + 番號相符 + 核心欄位有料 → pass。**多番號 quorum**：同源 ≥1 番號 pass 即綠，全部「拿到回應卻解析空」才紅。
- **結構式斷言**：只驗「有 Video + number 相符 + title/cover 非空」算 parser 健康，不驗 maker/series/date 精確值（那些會隨站方資料微調誤報，精確值回歸交給離線 mock）。標 `@pytest.mark.smoke`、不進 CI、pre-merge / milestone 手動跑當金絲雀，失敗靠人工判讀「下架/被 ban（忽略）」還是「改版（修 parser）」。

#### 📊 覆蓋率流程地板（cov-floor）/ Coverage floor
- **新增 `scripts/run_cov.sh` + `.coveragerc`**：把「增量審計」的盲區補上「存量地板」——`pytest --cov=core --cov=web --cov-fail-under=84`（地板 84% = 實測 86% − 2pp 緩衝防 flaky）。效果：下次誰碰到老模組被強迫順手補測試，老債漸進清償。`web/*`（端點 I/O，integration 部分覆蓋）omit；`core/scrapers/utils.py` 刻意保留在地板內（大半是已測純邏輯）。CI 不強制此 fail-under（CI 維持只跑 pytest、不擋 PR）。

### Fixed
#### 🔧 Tokyo Hot 單字母無碼番號修復 / Tokyo Hot single-letter number fix
- **`[無碼]n0762 Tokyo Hot` 這類單字母前綴無碼番號不再查無**。根因：`n0762` 被正規化成 `n-0762`（多插一個 hyphen），送進 scraper 全部 404。查證發現問題不在無碼源，而在 hyphen 把查詢打死——Tokyo Hot 其實由 JavBus / JAV321 收錄（兩者都接 `N0762` 無 hyphen、都拒 `N-0762`），只是它們從沒收到合法查詢。修法（採「單字母 + 恰 4 位數字 → 不插 hyphen」窄規則，涵蓋 n/k/c/m/s 全系列，雙重約束天然排除所有有碼 collision）：`normalize_number` / `validate_number`（`base.py`）+ `extract_number`（`utils.py`，檔名也能抽出）三個 regex 觸點。**通用番號（`sone103` → `SONE-103`）完全不回歸**，不需新源/改路由（既有 JavBus/JAV321 即可）。

#### 🔧 avsox scraper 復活 / avsox scraper revival
- **avsox 來源恢復「給番號回得了料」**。站方已從 server-side render 轉純 client-side Vue SPA 且對 `requests` 回 403，舊 XPath scraper 只拿到空殼、任何番號都回 None（8 源裡唯一的通用無碼聚合站等於斷一條腿）。改打 SPA 背後的**兩段式 JSON API**（search → movie detail），number/title/cover（含 caribbean/1pondo/heyzo/Tokyo Hot 型）都回得了；既有單元測試改 JSON-mock + 真實 fixture，金絲雀 avsox 從紅轉綠。

### Changed
#### 🧪 測試技術債清償（五項離線單元測試）/ Offline unit-test debt repayment
- 全部 mock / fixture 驅動、不連網，補在流程定型前零測試或低覆蓋的程式上（按風險）：`core/nfo_updater.py`（**會改寫用戶 NFO 檔**的 add_actor / tags 去重 / user_tag 重寫 / 補欄分支，最高風險）、`core/translate_service.py`（_clean_output / batch 解析 + Gemini 四分支）、`core/scrapers/javdb.py`（fixture 離線測試 14%→68%）、`core/scrapers/jav321.py`（genre tags + else 分支 64%→72%）、`core/nfo_utils.py`（CDATA 區塊不被誤 sanitize 43%→100%）。離線 fixture 同趟由金絲雀 research sweep 順手抓存（既驗 live 番號又餵離線 mock）。

#### 🧹 source smoke 整併（consolidation）/ Source smoke consolidation
- 金絲雀上線後，對三個舊 source-smoke 檔（`test_scraper_live.py` / `test_scrapers.py` / `test_javbus_smoke.py`，33 測試）做 inventory，發現混用四種職責，分四桶各別處置（**整併而非裸刪、先有替代品才退役**）：桶 A 14 個 liveness **退役**（金絲雀 quorum 嚴格替代）；桶 B 欄位斷言**搬離線**（javdb tags + javbus JUR-688/SNOS-143 HTML fixture，deterministic、不受站方微調誤報）；桶 C 9 個金絲雀不覆蓋的獨特 live 路徑（fan-out / 女優 / smart_search 無碼路由 / keyword / 多語言 tags）收進新 `test_extra_paths_live.py`（slim live，連不上顯式 skip）；桶 D 9 個純邏輯測試**搬 `tests/unit/`**（原誤放 smoke 目錄、CI 看不見）。三舊檔覆蓋全有去處後刪除。

### Internal
- 金絲雀架構：純 decision-core（`_canary_core.py`，三態判讀邏輯不連網、可 deterministic 單元測試）+ probe（`_probe.py`，`_probe_reachable` 走各 scraper 既有 reachability）+ 番號清單（`_canary_numbers.py`）。
- 爬蟲 HTML/JSON fixture 落 `tests/fixtures/scrapers/`（`.gitattributes` `-whitespace` 豁免保 byte-faithful + `.gitignore` negation 放行 `*.html`）。
- Tokyo Hot 入口層守衛（`is_number_format` gate + `search_jav` 把 `N0762` 傳進 scraper）。

### Non-Goals（明確不做）
- **不把 `javlibrary` 納入 smoke**（CF 真人驗證 + 桌面專屬，無法自動化）、**不在 CI 跑真連線 smoke**（CI 維持只 pytest unit+integration、不連網）、**不做欄位級 live 回歸測試**（smoke 只結構式金絲雀；精確值回歸歸離線 mock）、**不為拉覆蓋率硬補** `app.py`/`config.py`/`gemini.py` 的連線 I/O 與頁面路由、**不重分類 metatube `TOKYO-HOT`**（用戶決議；雖確認誤歸有碼，與番號修復無關）、**不重寫 scraper 架構**（avsox 只讓它重新抓得到料）、**不建來源自動下架偵測/告警系統**（金絲雀失敗靠人工判讀）、**US6 不裸刪**（替代品存在前絕不刪原測試）。

### 測試
- 全套 pytest **4238 passed, 2 skipped**（unit + integration，排除 smoke / e2e，較 0.9.11 的 4089 +149）+ `npm run lint`（eslint + stylelint）綠。
- 覆蓋率地板：`core`+`web` **86.28% ≥ 84%**（`scripts/run_cov.sh`）。
- 來源金絲雀：**8 源全 PASS**（含 avsox 復活）。
- 新增測試：`test_source_canary` / `test_source_canary_logic`（三態 + quorum decision-core）/ `test_extract_number`（Tokyo Hot 單字母 + 截斷邊界）/ `test_scraper_parser`（normalize 路徑）/ `test_avsox_scraper`（改 JSON-mock + Tokyo Hot）/ `test_nfo_updater` / `test_translate_service` / `test_javdb_scraper` / `test_jav321_scraper` / `test_nfo_utils`（離線債）/ `test_scraper_smoke_pure_logic`（桶 D 搬遷）/ `test_javbus_scraper`（JUR-688/SNOS-143 fixture）/ `test_extra_paths_live`（桶 C slim live）。

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
