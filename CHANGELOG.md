# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [0.11.12] - 2026-07-12

本版主軸：**javdb 在 released 版復活 — 打包 metadata 修復 + 打包產物 runtime 驗證守衛**（feature/97，spec-97／plan-97，T1–T5）。**這是 0.11.10 之後第一個實際面向用戶的 GitHub release**（0.11.11 為純內部 test-deflation 里程碑、不單獨發版）。使用者唯一可感知的變化：**released 版（Windows/macOS ZIP）指定 javdb 來源搜尋，行為終於與開發環境一致**——能命中就命中，真的查無才回「無結果」。

根因已實證（非推理）：`build.py`／`build_macos.py` 打包瘦身刪除**所有 `*.dist-info`**；`curl_cffi` 的 `__init__` 在 **import 當下**讀自己的 package metadata（`importlib.metadata`），dist-info 不在 → 拋 `PackageNotFoundError`（`ImportError` 子類）→ 被 `core/scrapers/javdb.py` 的 `except ImportError` **靜默吞掉** → `CURL_CFFI_AVAILABLE=False` → 之後每次 javdb 搜尋在第一行就 `return None`、**零 HTTP 請求、零 log**。8 源金絲雀／全套 pytest／smoke 全在 dev venv 跑（dist-info 完好），永遠測不到 packaged 環境的斷裂——所以「測試全綠 → 出貨 → 用戶回報壞的」這條路一直沒被堵。**歷來所有 released Windows/macOS 版的 javdb 從第一天就不能用**（不是先前假設的 CF ban——released 版根本沒發過 HTTP）。

### Fixed
- **javdb released 版永遠「無結果」**：打包不再剝除 `.dist-info`，curl_cffi 在產物內能正常 import，javdb 恢復可用（owner 真機 2026-07-12 實證：補 dist-info + 重啟後搜 DLDSS-491 命中）。全保留 dist-info 壓縮代價僅 ~0.3MB（Windows ZIP 34.8 → 35.1MB，遠低於 48MB 上限）。
- **javdb 在非 ASCII 安裝路徑（中文/日文等同語系）搜尋 `curl error 77`**（feature/98，接續上條 dist-info 修復後才浮現的第二層問題）：打包 launcher 設 `PYTHONUTF8=1` → curl_cffi 用 UTF-8 編 CA 憑證檔案路徑，但 libcurl `fopen` 用系統 ANSI code page（`GetACP`，如 cp950）→ 非 ASCII 路徑對不上 → `curl: (77) error setting certificate verify locations` → javdb 靜默無結果。改用 `locale.getencoding()`（回 ANSI code page、**不受 UTF-8 mode 影響**）編 bytes 覆寫 `CAINFO`，**同語系**非 ASCII 路徑（含**預設** `C:\Users\<中文>\OpenAver`，中文 Windows 使用者預設安裝就中招的族群）javdb 恢復可用；仍完整驗證 TLS、不複製檔案。**javdb-only**（全 repo 唯一 curl_cffi 消費者；`avsox` 走一般 `requests`／OpenSSL 不受影響）。跨語系/emoji 安裝路徑（字元非當前 code page 可表示，極罕見）優雅降級（log warning 一次 + 退回原行為），workaround＝改用純英文安裝路徑。
- **番號 7 字母前綴（如 `PARATHD`）拖檔進來被截斷掉開頭字母**：`parathd-02976.mp4` 拖入被讀成 `arathd-02976`（掉 `P`）→ 找不到資料，而文字輸入正常。根因＝檔名抽番號的字母長度上限（`extract_number`／`organizer`／前端 `file.js` 為 5/6）比 codebase 內已有且已測試的基準（`gallery_scanner` 的 7，含 8 字母英文單字守衛）窄，`re.search`／JS regex 滑窗掉首字。把三處落後上限對齊到 7（`{1,7}`/`{2,7}`）；一併修前端「手動輸入番號」逃生口（`formatNumber` 原把 `PARATHD-02976` 絞成 `RATHD-02976`）。`gallery_scanner`（本就是 7）與 `is_prefix_only`（語意不同、故意保 6）不動。**DMM 原檔下載檔名**（`1sdms00808`／`h_839shic00023` 這類 content-id，issue #86）刻意**不**自動轉標準番號——DMM 特殊映射永遠加不完、且用 per-maker 學習映射，改由用戶輸入正確番號、逃生口兜底。

### Added
#### 🛡️ 打包產物 runtime 驗證守衛（制度化，堵死 dev-only 測試盲區）
- **`scripts/verify_artifact_imports.py`**：用**產物自帶的 Python** 全量 import site-packages 每個頂層套件，任一 fail → build fail。stdlib-only（跑在尚未驗證的 embedded python 上）、layout 無關（`sys.path` 探測，不寫死 Windows `Lib/` vs macOS `lib/pythonX.Y/`）。這正是「dev venv 測全綠、released curl_cffi import 就炸」盲區的守衛本體——刪掉任一套件的 dist-info 或整包，守衛必紅。
- **`scripts/audit_build_artifact.py` 加 dist-info 靜態檢查**（廉價第一道，掃 ZIP 不 import，兩平台皆查）：(a) curl_cffi 套件在但其 `*.dist-info/METADATA` 缺 → hard-fail（點名真兇）；(b) 大規模零 dist-info → hard-fail（防未來全刪回歸）。靜態不取代真 import（「檔案都在，跑起來才知道壞」）。
- **CI `build.yml` 重排**：新增 `verify-windows`（windows-latest）job 下載 Windows ZIP、用產物自帶 `python.exe` 跑 import sweep（Windows ZIP 是 ubuntu cross-build，build 機跑不了 win embedded python）；macOS build job 內就地跑 audit + sweep。**Release 上傳 gate 在 verify 之後**（守衛綠才發版）；macOS 首次掛上 audit（`--max-mb 60`，因 mac baseline 49MB、uvloop 為合法依賴，不照搬 Windows 48）。

### Changed
- **javdb 兩條靜默失敗路徑補診斷 log**（零行為變更，只加可觀測性）：curl_cffi 不可用 → 首次搜尋 log 一次 warning（含原始例外，一次性不刷屏）；HTTP 非 200 → log status code。排查本 bug 最貴的成本就是「零 log」——連「有沒有發請求」都要靠猜。

### 測試
- 全套 pytest **4995 passed, 1 skipped**（unit + integration，排除 smoke／e2e，較 0.11.11 的 4985 +10：dist-info 靜態檢查 7 案例〔curl_cffi 缺 metadata／大規模零 dist-info／mac 皆 hard-fail，含 mutation〕+ javdb 診斷 log 3 案例〔warning 一次含例外／None 容錯不 NameError／非 200 status code，含 mutation〕）＋ `ruff check .` 綠 ＋ `npm run lint` 綠。
- 產物守衛 mutation 實證（對本機 Windows 產物、WSL interop 跑產物自帶 python.exe）：正常 GREEN；刪 curl_cffi dist-info → `PackageNotFoundError` exit 1（本次事故的自動化重演）；刪整包 → 依賴鏈全列 exit 1；還原 → GREEN。audit 真 fixture：新 build GREEN、歷史壞 ZIP（v0.11.10，零 dist-info）RED。
- 來源金絲雀：**7 源 PASS + fc2 SKIP**（unreachable／no probe，站方連線問題非 parser 回歸，advisory；**javdb 本身金絲雀 PASS**——parser 一直健康，壞的是打包）。
- 每 task 獨立 Sonnet structured review（T2/T3/T4/T5 findings 皆修：產物守衛 scanned==0 假綠守衛／audit if-no-files-found／CI YAML semantics／javdb test importorskip）。CI dispatch dry-run + Codex PR review 為 push 後最終網。
- **本版另 bundle 兩個後續修復**（feature/98 javdb error 77 + 番號 cap 對齊）：全套 pytest 升至 **5030 passed / 1 skipped**（+35 自 4995：javdb CAINFO 12 案〔非 win／ASCII 路徑 no-op／ACP 可編→bytes 覆寫 CAINFO／`UnicodeEncodeError` 降級 warn-once／cache sentinel／併發 publish-after-compute／import-time 優雅降級，皆 mutation 驗〕+ 番號 cap 對齊回歸鎖〔parathd 各形式／合成 7 字母／8 字母維持不變非回歸／Tokyo Hot・日期・FC2 collision guard／organizer 殘留碎片／前端逃生口，皆 mutation 驗〕）；`npm test` 39 pass；`ruff check .` ＋ `npm run lint:js` 綠。兩者各經獨立 Sonnet review + Codex 二審（javdb import-time 降級測試、番號 `extractChineseTitle`／DMM 恆真斷言、organizer 無鎖）皆修並 mutation 證明。

## [0.11.11] - 2026-07-12

本版主軸：**前端靜態守衛 pytest → lint 全面遷移（test-deflation）**（feature/96，5 plan 96a–96e／3 PR `0.11.11ab`→`0.11.11cd`→`0.11.11`）——**純內部工程里程碑：零產品碼、對使用者完全隱形、不單獨發 GitHub release**（下一個面向用戶的 0.11.12 才是 0.11.10 後第一個實際 release）。north-star（owner 拍板）：**能用 lint 機械處理的，就不該進 pytest、也不該耗 Codex 審**——把 `tests/unit/test_frontend_lint.py` 裡「讀原始碼做字串/結構斷言」的前端靜態守衛搬回它們該去的工具層（eslint／stylelint／node `.mjs` lint 腳本），並止血讓它不再長回來。收益不是測試數字，是把機械式字串存在檢查移出 AI review 的注意力預算。

### Internal
#### 🧹 test-deflation 成果
- **`test_frontend_lint.py` 16,749 行/214 class → 5,041 行/59 class（−70%）**。殘留組成全數記帳：E2E-block 52 class（替代網＝旅程測試，待未來 E2E branch）+ slim-residual 4 class（pytest-justified 極性/scope 語意，逐一標籤）+ 混合殘餘；**8,000 行過渡上限達標**（4,000 完成上限待 E2E branch 適用）。
- **KEEP-justified 36 class relocate 進 `tests/unit/frontend_contracts/`**（7 檔 4,148 行）：跨檔 contract／method-body ordering／call-count／brace-scope 等 node 字串檢查不忠實的真守衛，純搬移零行為變更（pure-move gate：collect test-id 差集空 + byte-for-byte 驗證），明文排除行數棘輪計量。
#### 🛠️ 新 lint 基建（全掛 `npm run lint`，自動進 CI）
- **`scripts/i18n_lint.mjs`**（96a）：i18n key 存在性／四語 parity（warn）／禁詞（「推薦」「風味」）。
- **`scripts/static_guard_lint.mjs`**（96b 建、96d/96e 擴）：表驅動靜態守衛引擎，**886 rule／9 kind**（required/forbidden-string、dup-id、structure-count、tag-scan、inline-style-token、order、file-absent、paired-string〔檔含 A 必含 B〕）+ scope 機制（anchor 缺席 fail-closed、braceBalanced method-body 計數、stripLineComments 注釋剝除）。
- **`scripts/css-guard.mjs`**（96c）：41 CSS-block rule（fluent-materials／poster-crop／z-index 跨檔序／vt-anchor／selector-scope 等）+ stylelint 接線。
- **eslint 新 `SEL_*` 家族**：showModal／tracked-eventsource／longpress／clip-ban／window.open(path) 等 no-restricted-syntax，逐一追加進全部 flat-config 群（防 scoped-group replace trap）。
- **P0 止血**：pre-merge SA-pre-6 改 content-based lint-guard 偵測（掃斷言內容非 class 名，未標 `[lint-guard:*]` 即 BLOCKER）+ `test_frontend_lint.py` 行數硬上限。
#### 🔬 遷移品質方法論（本 branch 最貴的教訓，已固化進 plan-context gotcha）
- **每條遷移 mutation 驗證**：先建網 → 故意破壞 target 必 RED／還原必 GREEN → 才刪 pytest；刪除 commit 附「被刪 class → 替代網 rule」對照表（96e-T5 由獨立 review 50/50 逐條對帳）。
- **Codex 累計抓 7 條「替代網比原 pytest 弱」（scope-narrowing fail-open）全數修復**：element-bound 屬性值未綁值／`\b` 誤當屬性名邊界／class token 非 token 比對／whole-text 掃描被 property-scoped 弱化／複合 scope 漏 1200-char 窗上限／greedy 量詞偏離 find-first 語意／單 match 漏 multi-tag。通則固化：**遷移前記下原 pytest 掃描粒度，替代網必須同粒度，寧 fail-closed 不 fail-open**；mutation 必含 wrong-location 負向案。
- 遷移過程亦修正一個原 pytest 既有錨定 bug（VT head-script 守衛誤鎖無關 script tag，獨立 review 重演證實後改鎖真正 timing-critical script）。

### 測試
- 全套 pytest **4985 passed, 1 skipped**（unit + integration，排除 smoke／e2e，較 0.11.10 的 5523 淨 −538：被刪守衛已由 lint 層 886+41 rule 等價承接，覆蓋面不減、Codex/pytest 注意力預算下降）＋ `ruff check .` 綠 ＋ `npm run lint`（eslint + stylelint + css-guard + static_guard_lint + i18n_lint + lint-settings-ia）綠 ＋ `npm test`（node:test 28）綠。
- 來源金絲雀：**7 源 PASS + fc2 SKIP**（unreachable／no probe，站方連線問題非 parser 回歸，advisory 記錄）。
- Codex PR review：PR-1 P2×1（eslint persistence.js group 補 selector）、PR-2 P1/P2/P3×4（scope-narrowing）、PR-3 前置審 P1×2+P2×1（1200 窗上限＋lazy 量詞＋multi-tag defer）皆修復並 mutation 證明（修前 GREEN=缺口證實 → 修後 RED）。

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

## 0.11.x 系列 (v0.11.0 ~ v0.11.6, 2026-06-27 ~ 2026-07-06)

- **v0.11.0**：JavBus 過度泛用清償 + exact 番號搜尋改優先序 cascade（feature/85）——直接搜番號改為依你拖曳的來源優先順序逐一查詢（cascade，命中即回），JavBus 不再無視優先序搶先短路；DMM proxy 透傳修復、前綴搜尋 `type` 參數修正；拔除已死的 JavBus variant（同番號多版本）探查死碼。
- **v0.11.1**：JavLibrary 同番號多版本手動切換（feature/86）——搜尋框直搜／燈箱換來源／結果卡替換來源三入口皆可看封面手動挑撞號版本（游標預設停最新發行日），桌面 standalone 限定（需 CF transport）。
- **v0.11.2**：`core/database.py` 模組化拆分（feature/87）——2,152 行單檔拆成 `core/database/` 套件（六個領域子模組 + 永久 re-export facade），消除 `AliasRepository`／`TagAliasRepository` 鏡像重複碼（共用泛型基類），零行為／API／schema 變更。
- **v0.11.3**：唯讀來源生成本地媒體庫「off 風味」首發（feature/88）——scanner 來源可勾「唯讀」＋設輸出夾，來源零寫入下生成每片一資料夾的本地庫（NFO + 封面 + 劇照）並直接寫進 DB，供 OpenAver 自身瀏覽／串流播放雲端原檔；給 Emby/Jellyfin/Kodi 的 media-server（`.strm`）風味延後至下一版（feature/89）。

- **v0.11.4**：唯讀產生庫「地基」+ 掃描頁「試過」記憶 + 來源刪檔清死卡（feature/89）——生成片記住輸出夾（`videos.output_dir`）重刮原地更新不長重複夾、off 風味固定輸出夾免設定；試過／已生成的片不再被「缺資料」嘮叨、刮不到只試一次；唯讀網盤掉線明確警告不誤報成功；來源刪檔後 DB-row-only 清死卡（零檔案刪除）。
- **v0.11.5**：唯讀來源生成媒體伺服器庫「.strm 風味」+ 跨機器路徑映射 + 唯讀寫入全面封鎖（feature/90）——唯讀來源可產出 `.strm` 捷徑檔給 Emby/Jellyfin/Kodi 掃描播放，跨機器「播放端路徑替換」規則讓 `.strm` 內路徑翻成播放端看得懂的形式、改規則一鍵同步改寫既有 `.strm`；同時把唯讀來源「零寫入」補到滴水不漏（勾唯讀破壞性確認、四個寫入入口全面停用、切模式清舊媒體卡、產生中斷乾淨收尾）。
- **v0.11.6**：跨機器路徑映射（WSL2+UNC）讀寫全棧收斂 + DB-key 命名空間守衛（feature/91）——純 correctness 重構：修好「讀取端忘了在碰磁碟前把映射路徑反解回本機路徑」導致縮圖／封面／串流跨機器讀不到的一類 silent bug，以及「已反解路徑又被裸餵回 DB key」導致重刮掉使用者標籤、女優照 403 的另一類；兩支 AST 結構守衛擋死回歸。

測試數 4735 → 5447。

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
