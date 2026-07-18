# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### 測試
- 全套 pytest **5348 passed, 1 skipped**（unit + integration，排除 smoke／e2e）＋ `ruff check .` 綠 ＋ `npm run lint` 綠（static_guard_lint 1034 條）＋ `npm test`（node:test 118）。
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

## 0.11.x 系列 (v0.11.0 ~ v0.11.10, 2026-06-27 ~ 2026-07-10)

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

測試數 4735 → 5523。

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
