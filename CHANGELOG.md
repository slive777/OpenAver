# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.7] - 2026-07-22

本版是一次「內部收斂＋順手修 bug」（feature/105）：把唯讀來源與一般來源在「刮完之後怎麼記帳、怎麼回報」這層——原本被抄成四份、每次改都漏抄一份的判斷邏輯——收斂成**單一實作、兩邊共用**，並替它上了機械守衛（債長不回來）。**絕大部分對使用者隱形**，實際會被感受到的是下面四個修復。

### Fixed
- **唯讀片不再誤顯示破圖**：唯讀來源的片在重刮／補缺時，若輸出夾的封面圖檔已被刪除、或跨機器路徑對不上（DB 還記著、磁碟其實沒有），以前會誤判「有封面」、讓介面拉出一張不存在的縮圖（破圖）。本版改為**實際檢查磁碟上封面在不在**，與一般來源完全一致。
- **重刮不再清空原文標題**：一般來源的片重刮時，若這次線上刮不到原文標題（originaltitle），以前會把**既有的原文標題清空**（資料庫與 NFO 都被清）。本版改為刮不到就**保留既有值**（此修復唯讀側早已有、這次補回一般側）。
- **某些片重刮不再失敗**：承上，在「既有原文標題本來就是空的 + 這次也刮不到」的特定組合下，重刮會在產生 NFO 時崩潰、該片補料失敗。本版一併修好（原文標題一律以空字串處理，不會變成無效值）。
- **批次補料單片出錯不再拖垮整批**：批次補料時，若某一片在前置解析階段就出錯，以前會**整批掛掉**；本版改為**只有該片失敗、其餘照常完成**（與一般片的逐片錯誤隔離一致）。

### Internal
純內部工程，對使用者無感、零行為變更（除上述四個 bugfix）：
- **第②層「寫後記帳＋回報」收斂**：把「有沒有可服務的封面／要不要保留既有封面／原文標題保留／回報 `hit`/`no_cover`/`not_found`/`error`」這四類判斷，從 enricher 一份＋唯讀三分支各一份（共四份手抄）收斂成單一實作。本該與一般來源相同的部分抽進新的中性模組 `core/enrich_contract.py`（兩邊都 import、無循環依賴）；唯讀限定的部分（not-found 樁列、失敗形狀）收進 `core/readonly_producer.py`；封面寫入後的焦點記帳三份拷貝收進 `core/focal_trigger.py`。刻意的唯讀／非唯讀差異（唯讀恆寫 NFO、`fields_filled` 語意）以**參數**表達、不開第二套實作。
- **防漂移雙機械閘**：新增 AST 靜態結構守衛（鎖「每個判斷只有一份、呼叫端都改呼叫同一份、舊手抄指紋不得復生」）＋ 唯讀/非唯讀 contract-parity 測試（等價輸入下兩路徑可比欄位相等 + 全欄位歸類 fail-loud，未來新增欄位漏鏡射即報紅）。這是「一勞永逸」的核心——讓第②層不會再長出第五份拷貝。
- 第①層（拿哪份 metadata／封面）與第③層（實際寫檔演算法）維持**刻意分歧、完全不動**（唯讀 local-first 零連網 vs 一般 DB→NFO→scraper merge；就地補寫 vs 整體 regenerate 進輸出夾）。

### 測試
- 全套 pytest **5603 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（static_guard 1031／css-guard／cjk_guard；i18n 102 缺 key 為既往版本 milestone 同步項、非本版）。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live）。
- 新增守衛：AST 結構守衛（`test_enrich_contract_structure.py`）＋ contract-parity（`test_readonly_enrich_contract_parity.py`）＋ 六支共用 helper/建構器 unit（`test_enrich_contract.py`）＋ focal 收斂 unit（`test_focal_trigger.py`）；兩支防漂移守衛皆做 mutation 自驗（拿掉呼叫／植入舊指紋／回退 helper → 對應守衛真的變紅）。
- 每 task 獨立 Sonnet review（T7 抓到負向鎖指紋硬編變數名 `existing`、漏掉主 target 用的 `existing_record` 近空殼，已放寬為錨定 attribute shape）＋ grok 整支 branch 第二意見（**提 1／採納 1／假陽性 0／未查證 0／增量 1**）：抓到本 branch 引入、四層 review 皆漏的回歸——原文標題保留 helper 在「DB 既有值為 SQL NULL＋這次刮不到」時回傳 `None`（而非 `''`），會讓 NFO 產生崩潰；已修為回傳恆為字串。
- 本版無新增 i18n key（純後端 + 守衛）。

## [0.12.6] - 2026-07-21

本版讓「唯讀來源」（通常是雲端分享盤）變聰明了：如果那個盤本身已經是整理好的媒體庫（影片旁邊就附了 `.nfo` 和封面圖），OpenAver 會**直接讀用它現成的資料**，不再無視它、傻傻地重新上網刮一次——更快、更省流量、也更準（撞號抓錯的問題在已整理的庫直接消失）。同時，唯讀來源的片現在也能用放大鏡補料、齒輪重刮、補劇照，而且產物一律落在獨立輸出夾，**絕不會寫回你的唯讀盤**。

### Added
#### 📀 唯讀來源就地取用本地資料（不再無腦重刮）
- 產生列表時，來源影片旁若有 `.nfo`，直接讀它寫入資料庫（片名／番號／女優／片商／標籤／日期…），**完全不連網**；旁邊有封面圖就複製一份進輸出夾使用。三種常見情況（有 NFO 有封面／只有 NFO／只有封面）各自最省地處理。
- 即使檔名被改成片名、抽不出番號，只要 NFO 裡有番號（`<num>`／`<uniqueid>`）一樣能就地建立（番號以 NFO 為準）——整理好的庫常把檔名改成片名，這類片不再被跳過。
- 已整理成 Jellyfin/Emby 格式（`-poster.jpg` + `-fanart.jpg`）的來源，那兩張圖會**原樣複製**進輸出夾、不重新裁生，完整保留你 curate 的海報與背景圖（只有缺的那張才由封面補生）。
- 沒有任何附檔的裸片，才照舊上網刮（行為不變）。
- 對「已在別處整理好、只想在 OpenAver 裡瀏覽」的雲盤庫特別有感：秒建、不重複下載、用你自己 curate 的正確資料。

#### 🔓 唯讀來源的片也能補料／重刮／補劇照
- 以前唯讀來源的片，放大鏡、齒輪（進階重刮）、補劇照三顆按鈕是鎖住的；本版全部解禁。
- 所有寫入一律導向獨立輸出夾，**來源盤零寫入**（承重牆不變）。齒輪重刮撞號時可手動挑版本（沿用既有 JavLibrary 切換）。

### Fixed
- 刪掉本地產生的封面後，可用齒輪重刮補回（不再整批略過）。
- 修正某些第三方 NFO 把女優寫成巢狀結構時、就地取用會漏掉女優的問題。
- 補劇照回報的張數改為「實際下載成功」的數量（非「嘗試」數）；一張都沒抓到時不會清空既有紀錄。
- 批次補料對唯讀片成功後，掃描頁卡片狀態與封面動畫會正確更新（不再誤顯示成「沒變動」）；只有 NFO、沒封面的片會標為「無封面」而非硬拉一張不存在的縮圖（破圖）。
- 唯讀片按放大鏡「補缺」（缺 NFO、封面還在）不再重寫既有封面（只補缺的那份），封面真的被換掉時（齒輪重刮換新圖）才自動重跑對焦——與非唯讀完全一致。
- 修正舊版（0.11.x）唯讀來源產生的媒體庫，升級後**每部片都誤顯示放大鏡（補缺）圖示**的問題：那些片的資料其實完整（NFO 早已寫進輸出夾），只是舊版把資料庫的 NFO 時間戳記記成 0，讓介面誤判「缺 NFO」。本版升級時**自動回填**正確時間戳（依封面旁的同名 `.nfo` 實際時間），圖示即消失；只補值不刪值、找不到 `.nfo` 的片保持原狀。
- 唯讀片刮不到資料時，不再每次掃描／批次補料都被重複端出來要求重刮——比照非唯讀，標記為「已嘗試過」。
- 修正唯讀來源就地取用時，NFO 裡的**原文標題**（originaltitle）被漏讀、且重刮時會被清空的問題（現在正確保留，刮不到新值也不會覆蓋既有值）。
- 修正「補劇照」若是某部片的第一個動作時，之後正式重建會另配一個 `NUMBER-2` 目錄、導致劇照跟 NFO／封面被拆到兩個資料夾的問題。
- 修正唯讀片若封面圖檔已被刪除（但資料庫仍記著），按放大鏡「補缺」時會誤判「已有封面」而跳過、留下破圖的問題——現在會實際檢查磁碟上封面在不在，不在就重建（與非唯讀 `_write_cover` 一致）。

### Internal
- 抽出單片產生的共用核心：bulk 產生／放大鏡／齒輪／補劇照四條路共用同一套 resolve→write→upsert，杜絕目錄邏輯漂移與孤兒夾。
- 封面來源三態策略（複製本地／不下載／遠端下載）＋ metadata 與封面來源解耦；`nfo_mtime` 改實寫值。舊庫殘留的 `nfo_mtime=0`（pre-T1／0.11.x）由 app 啟動時一次性 `backfill_readonly_nfo_mtime` 回填（`cover_path` 旁同名 `.nfo` 的 stat mtime）——冪等、只補不刪、不進 per-request `init_db`。
- 唯讀端點從「拒絕」改「改道 output_dir」，語意走明確 `readonly_action` 欄位（非唯讀端完全忽略、byte-identical）。
- 前端 `is_readonly_source` 欄位與相關死碼（批次 readonly 狀態卡、i18n key、zombie CSS＋守衛）連根移除，配 lint 負向守衛防回流。

### 測試
- 全套 pytest **5523 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（static_guard_lint／css-guard／cjk_guard）＋ `npm test`（node:test **219**，含四鈕 readonly_action intent 3 支）＋ readonly-route offload 正向守衛。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live）。
- **CDP 真機驗收**（headless Playwright 真 click、D:\123 唯讀來源）：① 生成列表就地 ingest 封面 hash-match copy（零網路）＋巢狀女優正確歸檔 ② 放大鏡真 click→ingest 零網路 ③ 補劇照 samples_only 只落劇照、nfo／封面 hash 不變、回實寫數 ④ 放大鏡／齒輪／補劇照四鈕唯讀解禁可點 ⑤ 來源零寫入。
- 每 task 獨立 Sonnet review ＋ Codex plan review（5×P1）＋ Codex diff review（P1 巢狀 actor／2×P2 劇照數・batch 欄位，皆已修）＋ grok 整支 branch 第二意見（提 5、採納 3、假陽性 1、by-design 1；**增量 2**＝抓到四層 review 都漏的 data-loss：唯讀片先補劇照、之後齒輪重刮／放大鏡會清掉既有劇照〔磁碟+DB〕；封面重刮失敗會把 DB cover_path 清空破圖——兩者已修，改比照 enricher 保留既有值）＋ Codex GitHub PR review 兩輪（第一輪 2×P2：檔名無番號但 NFO 有番號的片被跳過、批次唯讀無封面片缺 reason 硬拉破圖縮圖；第二輪 2×P2：唯讀 fill_missing 重寫既有封面／換封面後對焦不重跑；第三輪 owner 判定為「唯讀平行實作不鏡射 enrich 合約」的連環 bug、拍板一次完整對齊：三個唯讀端點一律回傳完整 EnrichResult 形狀、認 write_nfo 旗標、reason 依實際可用封面判定、fetch-samples 形狀與 fetch_samples_only 逐欄對齊、db_to_sidecar 明確拒絕——皆對齊非唯讀行為，owner 確認後修；第四輪撤回第三輪過度對齊的 write_nfo skip-gate（會造成標題變更 rescrape 刪舊 NFO 但跳過寫新 NFO 的 data-loss）改「唯讀一律寫 NFO＋明確拒絕 write_nfo=false」，並補齊 ingest／rescrape 兩條 scrape fallback 都 thread caller 的 source／javbus_lang）＋ owner 真機回報修正（Jellyfin 格式 curated `-poster` 被重畫丟棄→改原樣複製）；第五輪 owner 拍板「窮舉盤點一次收口」——除 Codex 兩 P2（not-found 未標 scrape_attempted_at＋stub row／samples-only 未記 output_dir 致 NUMBER-2 孤兒夾）外，盤點自查再抓兩條同族（original_title 從未鏡射被靜默清空、enrich-single not-found reason 應為 not_found），一次修完並排除 6 條 by-design 假分歧；第六輪 P1（pre-push 本機審抓到）：第五輪的 original_title 空值保留只做在 DB 層，NFO 寫入仍會清空 `<originaltitle>`（磁碟資料遺失＋NFO/DB 不一致），改在 `_produce_one` 寫資產前合成 effective 值讓 NFO／DB 共用同一份 meta；第七輪（owner 定調最後一輪）2×P2：唯讀封面保留只看 DB `cover_path`、不查磁碟——輸出封面被刪除時 fill_missing 放大鏡誤判「已有封面」跳過重建留破圖，改為額外 `os.path.exists` 檢查、與非唯讀 `_write_cover:236` 真正一致（enrich-single＋batch 兩處）。
- 本版新增 i18n key 只寫 zh_TW（其餘三語留空靠回退）。

## [0.12.5] - 2026-07-20

本版是一次「技術債清償」（feature/103）：把散在程式各處、只能靠人腦自律維持的東西收斂乾淨，並替每一筆清償補上一道機械守衛，讓債長不回來。**絕大部分對使用者完全隱形**，實際會被看見的只有下面三件事。

### Changed
#### 🌐 多語系介面更完整
- 原本有一批中文字（主要是各種提示與錯誤訊息）直接寫死在程式裡，切成英文／日文／簡中時仍顯示繁中。本版把約 130 行這類文字收進語言檔，未來翻譯補上後就會跟著介面語言走。
  > 本版新增的字暫時只有繁中、其他語言留空靠回退顯示繁中（正確翻譯留待後續統一補），所以**這一版切語言時這些字仍是繁中**，但已從「不可能翻」變成「翻了就生效」。

#### 🎯 拖曳檔案的番號辨識與「貼上檔名」一致
- 以前把影片檔**拖**進搜尋頁，番號辨識走的是前端一份簡化規則，比「貼上檔名」少認 5 種格式（日期式 `123456-01`、底線式、方括號 `[ABC-123]`、Tokyo Hot `n0762`、數字前綴）——同一個檔拖進去可能失敗、貼進去卻正常。本版讓拖曳與貼上走**同一套後端規則**，兩邊結果一致（先前 `PARATHD` 系列拖檔掉字即屬此類）。

#### 💬 番號辨識失敗時會明說
- 檔名認不出番號時改為**明確提示**，不再默默留空讓你以為沒反應。

### Internal
純內部工程，對使用者無感、零行為變更：
- **死碼清除**：移除 2 個已退役函式 + 8 個孤兒函式（連同其測試）。
- **logger 守衛遷移**：從 pytest 改用 ruff banned-api（TID251）機械擋「用標準 `logging` 而非 `core.logger`」。
- **前端重複收斂**：四份重複的 `mergeState`、兩份重複的 `openLocal` 各自收斂為單一共用模組。
- **中文硬編碼守衛上線**：JS 面用 eslint 自訂 AST rule、模板面用掃描腳本，植入一行硬編碼中文即 lint 報紅——這是讓 i18n 債長不回來的機械閘。
- **番號抽取鏡像連根拔除**：刪掉前端那份簡化番號規則，規則只留後端一份權威版，消除「兩份鏡像會漂移」的債源；連帶把批次拖曳／選檔的競態補強（連續操作時舊請求會被取消、不覆蓋新結果、失敗也不吞掉已選檔案）。
- **治理文件收斂**：`Alpine.store` 使用界線明文化、javbus UA 反爬意圖入註記。

### 測試
- 全套 pytest **5347 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（eslint／stylelint／`static_guard_lint` 1039 條／cjk_guard_lint）＋ `npm test`（node:test **212**，含 T5 競態／fallback 守衛 4 支）。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。
- T5（唯一有 runtime 行為變更的 task）**CDP 真機驗收 3 oracle 全 PASS**（拖日期式番號→辨識成功／拖無番號檔→明確提示／連拖競態→正確取後者無殘留）。
- 每 task 獨立 Sonnet review ＋ Codex PR review（P1：批次 abort 未貫穿 parse 階段，已修＋真 A/B 競態守衛）＋ grok 整支 branch 第二意見（LGTM；提出 2 條皆 P3，採納 1＝T6 誤把 metatube 連線 toast 文案「Provider 清單」改成「Parts Bin」造成設定頁內部不一致，已還原；此條 Codex 與 per-task review 皆未觸及，為 holistic branch review 的增量發現）。
- 本版新增 i18n key 只寫 zh_TW，其餘三語留空靠回退。

## [0.12.4] - 2026-07-18

本版修好「改過名（有別名）的女優換照片特別難」的兩個問題（feature/102，spec-102 Part A＋B）。之前這類女優在照片挑選視窗裡：本機候選一選就失敗、雲端又永遠查不到圖，體感就是「換圖整個壞掉」。

### Fixed
#### 🖼️ 別名片的本機候選選了就能換（Part A）
- 修好「照片挑選視窗給我看的本機封面候選，只要那張封面來自她改名前（別名）名下的影片，一選必跳『抓取失敗，請稍後再試』」。根因是產生候選與儲存驗證用了不同的名字展開範圍；現在兩端一致，**看得到的候選就選得了**。
- 安全邊界不變：不屬於這位女優（含其別名）名下的影片路徑，仍然一律拒絕。無別名的女優行為與以前完全一致。

### Added
#### 🔄 重抓時自動輪流用別名向線上圖庫查詢（Part B）
- 在照片挑選視窗按 🔄 重抓，雲端查詢會自動輪流用她的每個名字查（主名 → 別名依序 → 繞回主名）。剛改名的女優線上圖庫多半只認舊名，之前永遠 0 命中；現在多按幾次 🔄 就能撈到掛在舊名下的雲端照片。
- **使用者無感、UI 零改動**：沒有新按鈕、不顯示目前用哪個名字查（刻意設計——這是「增加圖片來源」的內部機制，不是要操作的功能）。無別名的女優按 🔄 行為與以前完全一致。換一位女優後輪替自動從主名重新開始。

#### 🖱️ 滑鼠滾輪也能切上一片／下一片（102d）
- 搜尋頁詳情、燈箱（影片／女優）、劇照瀏覽：**橫向滾輪往右撥＝下一個**（等同按右方向鍵），往左撥＝上一個；showcase 牆也能用橫向滾輪翻上下頁。
- 燈箱和劇照這類全螢幕檢視裡，**垂直滾輪也能切**（滾下＝下一張、滾上＝上一張）——多數滑鼠沒有橫向滾輪，這讓一般滑鼠也用得到。一般頁面的垂直滾輪維持捲動頁面、完全不受影響。
- 防誤觸設計：一撥只切一張（觸控板慣性連發不會飛過好幾張）；縮圖列、資訊面板等本來就能捲動的區域維持原生捲動，不會被搶走。

### Internal
- **CI 測試瘦身（102c）**：把「真的跑人臉偵測」收斂到少數顯式回歸測試，其餘佈線／端點測試改用固定座標 mock——全套測試本地 267s → 180s（CI 約 5 分鐘 → 3 分鐘內），測試行為覆蓋不減、零產品碼變更（含 mutation 驗證測試沒變空殼）。

### 測試
- 全套 pytest **5348 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（static_guard_lint 1034 條）＋ `npm test`（node:test **139**，含滾輪導航 20 案）。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查）。
- 輪替全序列以 **CDP 真機實測**（headless Playwright 真 click）：首開無參數、三連 🔄 查詢名 主名→別名1→別名2→繞回、換人歸零、無別名逐位一致、儲存身分正確（驗後資料已還原）。
- 每 task 獨立 Sonnet review ＋ Codex PR review（P0 手刻 URI 已修、二審通過）＋ Gemini 整支 branch 第二意見（5 條 findings 全數為既有設計已覆蓋，0 採納）。
- 本版 **UI 零改動、零新增 i18n key**。

## [0.12.3] - 2026-07-18

本版把焦點（對臉裁切）這條線的尾巴收乾淨（feature/101，spec-101 四部分 A/B/C/D）。前幾版已經讓無碼封面在 app 裡自動對準人臉、也能手動微調；這版補上「媒體伺服器海報也對臉」、把燈箱按下對焦鈕的等待過程做得更連續好懂、清掉兩塊內部技術債，並讓影片對焦鈕只在真的會用到時才出現。承重牆不變：**全程只存焦點座標，你的封面圖檔一個位元都不會被改寫**。

### Added
#### 🎯 媒體伺服器海報也會對準臉（Part A）
- 給 Jellyfin／Emby／Kodi 掃描用的實體海報檔（`-poster.jpg`），無碼片在產生時現在會自動偵測人臉、以臉為中心裁切（跟 metatube 一樣的基礎功能）。有碼片與偵測不到臉的封面維持原本裁法、位元級零變化。
- **不管用哪個來源刮的**（內建 8 源或 metatube 聯邦）一視同仁；四個會產生海報的路徑（整理、補完、唯讀來源生成、掃描頁補圖）全數納入。

### Changed
#### 🎯 燈箱對焦「按下 → 找到」全程視覺連續（Part B）
- 按下對焦鈕後那 2–3 秒，星空等待動畫與亮窗落定改為**交棒重疊**——星空淡出的同時亮窗收斂到臉上，中間不再有硬切／空窗閃一下。
- **一眼看出有沒有抓到臉**：找到臉 → 亮窗收斂落定；沒找到 → 亮窗直接以基準位置淡入、不收斂（用「有沒有收」這個動作區分，不用顏色，不依賴色覺）。
- 收斂過程中你就伸手拖曳 → 立刻交給你的手，動畫讓位不跟你打架。

#### 影片對焦鈕只在真的會用到時才出現（Part D）
- 電腦寬螢幕看片時，封面本來就是完整的、對焦鈕按了在當前畫面看不出效果，現在**桌面預設收起這顆鈕**；**手機／窄視窗**（封面被裁成直式 poster 時）才顯示，行為與以前完全一致。拖動視窗跨過寬窄邊界時，鈕即時跟著出現／消失、不需重整。
  > 說明：這**不是**「這顆鈕沒用」。焦點是有跨畫面後果的儲存值——桌面收起拿掉的只是「桌面預設你自己將來用窄視窗看同一片時的裁切」這個極少用到的情況；桌面當前 viewport 本來就看不到這個裁切效果。

### Fixed
- 修好「**換照片視窗開著時按左右鍵切片，之後對焦鈕不見、手機滑不動**」（Part B；`_pickerOpen` 狀態洩漏，按一次 Esc 或關燈箱即恢復，本版直接根治）。
- 修好「**偵測沒找到臉時，對焦窗停在全幅、看不到遮罩**」（Part B；改為落回右裁基準，照樣可拖曳存入）。
- 對焦忙碌等待的 spinner 一律會轉起來（Part B）。
- 修好「**某些瀏覽器／開了廣告攔截器時，影片對焦按 ✓ 出現『裁切設定儲存失敗』**」（Part D）——存檔請求的網址剛好長得像影片廣告連結，被廣告／隱私攔截器在瀏覽器端擋掉、根本沒送到伺服器；把該端點改名解除，行為完全不變。

### Internal
- 女優對焦裁切比例的前後端兩份數值加了**自動一致性守衛**（改一邊漏改另一邊會被 lint 擋下，防「錯框」類靜默 bug）；移除一個從未實作過的 `photo_needs_resize` 殘留欄位（Part C）。純內部工程，對使用者無感、零行為變更。

### 已知限制
- **手動焦點不進媒體伺服器海報**：你在 app 裡手動拉的焦點是 app 的東西、不外流到 `-poster.jpg`（海報走獨立的自動偵測，這是刻意的產品邊界，不是缺陷）。
- **海報烤好後才改焦點 → 海報維持舊裁切**：海報是單向匯出產物、不會因你之後改焦點而自動重烤。**逃生口**：到掃描頁對該片補一次圖即會重烤更新（與「既有庫需重掃一次才補焦」同一個既有概念）。

### 測試
- 全套 pytest **5338 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（eslint／stylelint／`static_guard_lint` **1034** 條）。
- 來源金絲雀：**8 源全 PASS**（javbus／jav321／heyzo／d2pass／avsox／fc2／javdb／dmm，pre-merge live 健康檢查；heyzo 較 0.12.2 已恢復）。
- 每 task 獨立 Sonnet review ＋ Codex PR／本地 review ＋ **CDP 冷載／存檔實測**（影片對焦 icon 依窄螢幕條件顯示、resize 即時翻、✓ 存檔端點改名後真的 200 存入）＋ **整支 branch holistic 第二意見**（Sonnet，LGTM；3 條 P3 maintainability residual 記錄待未來清理，非本版 bug）。
- **i18n 三語（zh_CN／en／ja）本版新增 key 暫留空**、靠 fallback 顯示 zh_TW（正確翻譯歸 milestone）。

## [0.12.2] - 2026-07-16

本版主軸：**女優照片可以自己上傳了 + 女優也能對焦**（feature/100，spec-100／plan-100a＋100b＋100c）。之前女優牆的照片只能靠系統自動抓（線上圖庫或本機影片封面），想換成自己喜歡的照片得摸到資料夾手動塞檔案；而且女優頭像一律置中裁切，偶爾裁的位置不理想也沒辦法調整。這版把兩塊補齊，並在收尾時把對焦互動簡化成與影片一致（只在照片夠寬時才出現對焦鈕、只可左右拖）。

### Added
#### 📤 女優照片可以自己上傳
- 燈箱右上角加一顆上傳鈕，桌面選檔或手機開相簿都能用，選好照片就直接變成主圖（JPEG／PNG／WebP／GIF 都吃）。
- 上傳的照片存的是你選的原圖、不額外裁切也不跑偵測，跟「線上抓」「本地切割」一樣快、幾乎零等待。
- 檔案太大或格式不支援時會跳出明確提示，不會讓你以為按了沒反應；失敗時 picker 視窗會留著方便你直接重選再試。

#### 🎯 女優頭像也能手動對焦
- 燈箱裡女優名字那一行加一顆對焦鈕（和影片的對焦鈕同一個位置），按下去會自動抓一次臉的位置，抓到後可以左右拖曳微調，✓ 存起來、✗ 取消不寫入。
- 對焦鈕只有在「照片明顯偏寬、接近方形」、真的有左右可調空間時才出現。絕大多數直式沙龍照本來置中就對準臉了，這類照片不會冒出一顆按了也沒什麼好調的鈕。
- 就算這張照片抓不到臉（例如非正臉照、藝術照），框會停在置中位置，你還是可以手動左右拖到想要的地方存起來，不會卡住、也不會失敗給你看。
- 存好之後，牆上的縮圖跟燈箱大圖會立刻一起變成新的裁切位置，不需要重新整理頁面。

### Changed
- 換了新照片之後（不管是上傳自己的圖、線上重新抓、還是本地切割影片封面），舊的手動對焦位置會自動失效、改回置中裁切——避免舊的對焦位置歪打到新照片上。

### 已知限制
- **桌面手動換檔（自己把圖丟進 `output/Gfriends` 資料夾）不會自動清掉既有的對焦設定**：如果這位女優之前用對焦鈕存過焦點位置，之後又手動把資料夾裡的照片換掉，舊的焦點位置會繼續套用在新照片上，可能會裁到不理想的地方。**逃生口**：再上傳一次照片，或是再按一次對焦鈕重新設定一次，兩者都會蓋掉舊的焦點。

### 測試
- 全套 pytest **5289 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（eslint／stylelint／`static_guard_lint` **1007** 條）＋ `npm test`（node:test **112**）。
- **對焦互動於 100c 收尾定案**（女優對焦鈕只在照片橫向可拖幅度 ≥20% 時出現、只左右拖、Y 軸整條移除）：CD-11「不得復活」forbidden 守衛對 `computeMaskAxis`／`_maskFocalY`／`translateY`／牆格 Y 軸 object-position 輸出各自 mutation 單獨紅→還原綠；零行為變更以 headless CDP 冷載實測（全 22 位女優恰 5 位顯示對焦鈕；editor／render 兩側刪碼前後行為逐項一致；影片路徑零回歸）。
- **上傳點擊路徑**另以 CDP 實測：`x-show="_focalIconVisible()"` 五條件在依序切換 22 位女優全程無 staleness（method 無條件讀 5 旗標避開 `&&` 短路漏訂閱）。
- 來源金絲雀：**7 源 PASS + heyzo FAIL**（0 healthy／回空內容，疑站方改版或連線問題；**與本版 diff 無關**——本版零 scraper 改動，advisory 已記待查）。
- 每 task 獨立 Sonnet review ＋ Codex PR review（100a 三條換圖失敗語意）＋ Codex 本地 review（100b／100c）皆修並 mutation／CDP 證明。
- **i18n 三語（zh_CN／en／ja）本版新增 key 暫留空**、靠 fallback 顯示 zh_TW（正確翻譯歸 milestone）。

## [0.12.1] - 2026-07-15

本版主軸：**焦點裁切收尾——燈箱拖曳微調 + 唯讀來源補焦**（feature/99，spec-99／plan-99a＋99b）。0.12.0 把自動對焦的地基做完了，但留了三個尾巴：燈箱的手動微調是明示的「過渡版」互動、唯讀來源不會自動對焦、牆上小格對偏側臉只是近似。本版把三個都收掉。承重牆不變：**全程只存焦點座標，你的封面圖檔一個位元都不會被改寫**。

### Added
#### 🎯 燈箱焦點編輯：點一下 → 拖一下 → 存
- **新互動取代 0.12.0 的過渡版**：點焦點 icon → **自動對焦**（跑一次偵測、只做預覽不寫入）→ **左右拖曳**亮窗微調到你要的位置 → **✓ 存／✗ 取消**。舊版那套「點窗切換右裁／對臉、點窗外儲存」已移除。
- **偵測抓不到臉也能用**：偵測沒結果就停在右裁基準，你照樣可以直接拖到想要的位置存起來——歪臉封面（0.12.0 的已知限制）從此有了手動逃生口。
- **所見即所得**：燈箱裡拖到哪，牆上小格就裁到哪。

#### 🗂️ 唯讀來源也會自動對焦
- NAS／雲端的**唯讀來源**（off／`.strm` 媒體庫）掃描時現在也會自動偵測焦點，與一般來源一致。**既有的庫重新掃描一次即可補上**（不會改動來源任何檔案）。

### Fixed
- **牆上小格對偏側臉的裁切不再是近似**（0.12.0 已知限制）：小格改用與燈箱大圖同一套 aspect 換算，臉明顯偏一側時小格與燈箱的裁切位置一致，不再有落差、也不再把偏側臉切掉一點。
- **臉貼在封面極左／極右時，拖曳起手有死區**：偵測到的臉很靠邊時，亮窗視覺上停在封面邊界、拖曳卻從邊界外開始算，導致往回拖要先「空拖」一段（臉在極右時約封面寬度的 17%）窗子才開始動。三處幾何換算（顯示／拖曳起手／拖曳中）現在共用同一個鉗制函式。
- **偵測中換封面不會把舊圖的座標寫到新圖上**：背景偵測跑到一半、封面剛好被重刮換掉時，舊圖算出的焦點不再會蓋到新封面（compare-and-store 守衛）。

### Changed
- **重刮且實際換圖**時，該片的手動焦點會降回自動——手動座標是對著舊封面拉的，對新圖已失效。同封面重刮則完整保留你的手動決定。
- 移除 `POST /video/crop-mode` 端點（0.12.0 過渡互動的後端），改為 `POST /video/focal` 原子寫入；`POST /video/detect-focal` 改為純預覽（不再寫 DB）。兩者皆未揭露於 `GET /api/capabilities`（純 UI 互動，AI agent 用不到），故 capabilities 無變更。

### 已知限制
- **臉明顯歪斜的封面可能抓不到**（偵測器走單一角度）：會退回右裁基準，此時**可在燈箱手動拖曳指定**（本版讓這句成真）。改進偵測器本身為 spec-99 Non-Goal。
- **既有影片庫需重掃一次才補焦**（沿自 0.12.0）：不掃描就不動；到掃描頁重新掃描一次即會補上尚無焦點的無碼片。

### 測試
- 全套 pytest **5233 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠 ＋ `npm test`（node:test **89**，含拖曳死區鉗制 6 案）。
- 模擬純 Linux CI（pytest plugin 設 `CURRENT_ENV='linux'`）261 passed——WSL 綠不等於 CI 綠（`to_file_uri` 的 `path_mappings` 分支寫死 `CURRENT_ENV == 'wsl'`）。
- **e2e**：`tests/e2e/test_showcase_focal_e2e.py`（CI 排除、milestone 才跑）。破壞性測試的安全邊界改為**結構性**——`page.route` 攔在瀏覽器網路層 + `fulfill()`，讓「寫進真實 DB」不可能發生，而非事後偵測。
- **真機驗收**（owner，唯讀來源 4 片 FC2/HEYZO + 1 片 1pondo）：重掃 3 片有封面者全數排入偵測並 commit（驗證 §3.10 bulk 設計對既有庫成立）；9 筆既有 `manual` 值逐一比對完全未變；自動偵測 x=`0.2926` 與先前手動拉的值完全一致。**未**真機驗證：換封面 race 本體（時序窄 ~3s，改由真 DB mutation 測試覆蓋）、首刮 read-back（owner 選擇跳過，同由真 DB 測試覆蓋）。
- Codex PR review 三輪 + 99b P1（focal 候選迴圈 per-iteration abort gate）皆已修復並 mutation 證明。
- Gemini 整支 branch 第二意見：分 4 群審，**1 條真命中**（拖曳死區 P2，已修並補 fail-closed 守衛 + node test）；其餘 6 條經查證為誤報（`focalCellObjectPosition` 首行即 null-safe／`crop_mode` 為 `NOT NULL DEFAULT 'auto'`／`repath` 的 `old_row` 非 caller 傳入且該 race 下 UPDATE 本就影響 0 列／桌面 rail 補 `$watch` 與對照組同為 no-op）。

## [0.12.0] - 2026-07-14

本版主軸：**焦點裁切——無碼封面自動對準人臉**（feature/98，spec-98／plan-98a＋98b，98a 地基 T1–T6 ＋ 98b 影片 T1–T7）。過去無碼片（FC2、素人、uncensored 廠牌）封面一律「切右半邊」，臉常被切掉一半或切在邊緣；本版讓這類封面在牆上小格與燈箱大圖都**以人臉為中心裁切**，看起來整齊得多。有碼片維持原樣（右裁），零額外成本。

### Added
#### 🎯 焦點裁切：無碼封面自動對準人臉
- **自動對焦**：無碼片刮削或掃描入庫時，背景自動偵測封面人臉、算出焦點座標；牆上小格、相似探索、燈箱大圖都改以人臉為中心裁切。抓不到臉的封面優雅退回原本的右裁，不會出錯。
- **只認無碼片**：以番號／廠牌精準判斷（FC2、素人標籤、uncensored 廠牌白名單）。有碼片完全不跑偵測、零成本，行為與以前一模一樣。
- **不阻塞**：偵測在背景進行，刮削／掃描不會因此變慢；同一張封面若短時間重複觸發，只算最新一次。
- **絕不改封面檔**：全程只把「焦點座標」存進 OpenAver 自己的資料庫，顯示時才即時裁切——你的原始封面圖檔一個位元都不會被改寫。
- **燈箱手動微調**：燈箱大圖可切換「右裁／對臉」、對漏判的封面手動觸發偵測（此互動為過渡版，見下「已知限制」）。

### Fixed
- 燈箱焦點遮罩先前在真機上完全點不動（幾何算錯 + 淡入過場卡住看不見）已修好，並補上切換影片時的競態保護。

### 已知限制
- **燈箱遮罩的操作方式為過渡版**（點 icon → 點窗切換 → 點窗外儲存），不夠直覺；下一版（spec-99）會改成「點 icon 自動對焦 → 左右拖曳微調 → ✓ 存／✗ 取消」。此過渡互動**不代表最終 UX**。（**已於 0.12.1 取代**）
- **臉明顯歪斜的封面可能抓不到**（偵測器走單一角度），會退回右裁；可在燈箱手動微調（過渡版）或等下一版拖曳指定。（**仍然成立**；0.12.1 起可在燈箱拖曳指定）
- **既有影片庫需重掃一次才補焦**——本版不會被動回填舊庫（不掃描就不動）；到掃描頁**重新掃描一次**，即會自動補上尚無焦點的無碼片（不必改動任何檔案）。
- **唯讀來源尚未納入自動對焦**——NAS／雲端的唯讀來源（off／`.strm` 媒體庫）目前掃描不會自動偵測焦點，將於後續版本支援。（**已於 0.12.1 修復**）
- **牆上小格對偏側臉的裁切為近似**——臉在正中的封面對得準；臉明顯偏一側時，小格的裁切位置與燈箱大圖（精準）會有落差、偏側臉可能仍被切一點。後續版本會讓小格與大圖一致精準。（**已於 0.12.1 修復**）

## 0.11.x 系列 (v0.11.0 ~ v0.11.12, 2026-06-27 ~ 2026-07-12)

- **v0.11.0**：JavBus 過度泛用清償 + exact 番號搜尋改優先序 cascade（feature/85）——直接搜番號改為依你拖曳的來源優先順序逐一查詢（cascade，命中即回），JavBus 不再無視優先序搶先短路；DMM proxy 透傳修復、前綴搜尋 `type` 參數修正；拔除已死的 JavBus variant（同番號多版本）探查死碼。
- **v0.11.1**：JavLibrary 同番號多版本手動切換（feature/86）——搜尋框直搜／燈箱換來源／結果卡替換來源三入口皆可看封面手動挑撞號版本（游標預設停最新發行日），桌面 standalone 限定（需 CF transport）。
- **v0.11.2**：`core/database.py` 模組化拆分（feature/87）——2,152 行單檔拆成 `core/database/` 套件（六個領域子模組 + 永久 re-export facade），消除 `AliasRepository`／`TagAliasRepository` 鏡像重複碼（共用泛型基類），零行為／API／schema 變更。
- **v0.11.3**：唯讀來源生成本地媒體庫「off 風味」首發（feature/88）——scanner 來源可勾「唯讀」＋設輸出夾，來源零寫入下生成每片一資料夾的本地庫（NFO + 封面 + 劇照）並直接寫進 DB，供 OpenAver 自身瀏覽／串流播放雲端原檔；給 Emby/Jellyfin/Kodi 的 media-server（`.strm`）風味延後至下一版（feature/89）。

- **v0.11.4**：唯讀產生庫「地基」+ 掃描頁「試過」記憶 + 來源刪檔清死卡（feature/89）——生成片記住輸出夾（`videos.output_dir`）重刮原地更新不長重複夾、off 風味固定輸出夾免設定；試過／已生成的片不再被「缺資料」嘮叨、刮不到只試一次；唯讀網盤掉線明確警告不誤報成功；來源刪檔後 DB-row-only 清死卡（零檔案刪除）。
- **v0.11.5**：唯讀來源生成媒體伺服器庫「.strm 風味」+ 跨機器路徑映射 + 唯讀寫入全面封鎖（feature/90）——唯讀來源可產出 `.strm` 捷徑檔給 Emby/Jellyfin/Kodi 掃描播放，跨機器「播放端路徑替換」規則讓 `.strm` 內路徑翻成播放端看得懂的形式、改規則一鍵同步改寫既有 `.strm`；同時把唯讀來源「零寫入」補到滴水不漏（勾唯讀破壞性確認、四個寫入入口全面停用、切模式清舊媒體卡、產生中斷乾淨收尾）。
- **v0.11.6**：跨機器路徑映射（WSL2+UNC）讀寫全棧收斂 + DB-key 命名空間守衛（feature/91）——純 correctness 重構：修好「讀取端忘了在碰磁碟前把映射路徑反解回本機路徑」導致縮圖／封面／串流跨機器讀不到的一類 silent bug，以及「已反解路徑又被裸餵回 DB key」導致重刮掉使用者標籤、女優照 403 的另一類；兩支 AST 結構守衛擋死回歸。

- **v0.11.7**：搜尋頁體驗優化（feature/92）——搜尋列右側控制項不再擠壓變形、整理入口常駐可見更好找、整理入庫「飛入側邊欄」動畫加強為三段節奏，並抽成可跨頁複用的共用元件；順手修好「重新整理已有結果頁面時出現兩組 ✕」的 latent bug。
- **v0.11.8**：各刮削來源評分/簡介補進 NFO（feature/93，NFO-only）——七源評分、六源簡介寫進 `<rating>`/`<plot>`，純服務媒體伺服器（Jellyfin/Emby/Kodi）用戶，OpenAver 自身介面不顯示；順手美化燈箱中繼資訊視覺層次。
- **v0.11.9**：掃描頁「補資料」升級成逐片進度卡 + 命中封面飛入圖書館（feature/94）——補資料時逐片可視進度（搜尋中／命中／查無／失敗／唯讀跳過），真封面命中飛入側邊欄「瀏覽」入口。
- **v0.11.10**：設定頁命名區膠囊化 + 列表生成兩層 IA 重排（feature/95）——檔案命名格式從手打字串改成「變數膠囊 + 字面文字」視覺化編輯器、資料夾層級改動態清單（硬上限 3 層）；列表生成設定拆成日常常用（常駐）+ 離線 HTML 匯出（摺疊進階）。
- **v0.11.11**：前端靜態守衛 pytest → lint 全面遷移（feature/96，test-deflation）——純內部工程里程碑（零產品碼、對使用者隱形）：把 `test_frontend_lint.py` 裡「讀原始碼做字串/結構斷言」的守衛搬回工具層（新增 `i18n_lint`／`static_guard_lint`／`css-guard` 三支 `.mjs` + eslint `SEL_*` 家族），`test_frontend_lint.py` 16,749→5,041 行（−70%）、36 個真 contract class relocate 進 `frontend_contracts/`；north-star＝「能用 lint 機械處理的不進 pytest、不耗 Codex 審」。
- **v0.11.12**：javdb 在 released 版復活（feature/97）——打包瘦身刪除所有 `.dist-info` 導致 curl_cffi import-time 拋 `PackageNotFoundError`、被靜默吞掉，released Windows/macOS 版 javdb 從第一天就零 HTTP 請求；不再剝除 dist-info 即修復，並補打包產物 runtime 驗證守衛（`verify_artifact_imports.py` + dist-info 靜態檢查 + CI verify job）堵死 dev-only 測試盲區；本版另 bundle 兩個後續修復：非 ASCII 安裝路徑 `curl error 77`（CAINFO 改用 ANSI code page 編碼）+ 番號 7 字母前綴拖檔截斷修復。

測試數 4735 → 5523（v0.11.10）→ 4985（v0.11.11 test-deflation：守衛遷 lint 層等價承接，−538 非覆蓋損失）→ 5030（v0.11.12，+45：打包產物驗證守衛 + javdb CAINFO + 番號 cap 對齊回歸鎖）。

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
