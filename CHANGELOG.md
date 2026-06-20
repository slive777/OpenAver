# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [0.9.11] - 2026-06-13

本版主軸：**外部媒體管理器相容模式（Jellyfin / Emby / Kodi）**（feature/72）。OpenAver 的 NFO 本來就是 Kodi/Jellyfin/Emby 共用的 XML schema，「基本相容」沒問題，但離「掛上去就正確顯示」還差一截——圖片命名偏好不同、多段影片（cd1/cd2）會被當成兩部片、NFO 少了幾個媒體庫排序/過濾用的欄位。本版在 Settings 新增「外部媒體管理器模式」**四態選擇器（預設｜Jellyfin｜Emby｜Kodi，每態各有一行說明）**：選任一外部模式後，刮削/整理會另存 `{番號}-poster.jpg`／`{番號}-fanart.jpg`、把 cd1/cd2/part1 等多段自動合併成一部片（第 2 段以後只跳 NFO、保留封面）、並補上 NFO 辨識欄位（番號 ID／排序／產地／語言）。掃描端也學會讀外部工具（MDCX/Javinizer）或 OpenAver 自己產生的 `{番號}-fanart/-poster.jpg`，直接接手已刮削的收藏庫。另含 issue #44 後續回報的兩個整理 pipeline 修復（B1 搬檔不再產生重複死卡、B2 已整理檔再整理標題不疊加）。

### Added
#### 🎬 外部媒體管理器相容模式 / External media-manager compatibility mode
- **F1 — 外部媒體管理器四態選擇器**：Settings 新增「外部媒體管理器模式」segmented 控件，四格「預設｜Jellyfin｜Emby｜Kodi」，每態旁邊一行說明（trailing hint，跟在選擇器同一橫列）清楚講「會產生什麼檔案」。選「預設」行為與現狀完全相同。
- **F2 — cd1/cd2 多段自動合併**：開外部模式後，偵測檔名多段 token（cd1/cd2、dvd1/dvd2、part1/part2、pt、disc）；第 1 段正常輸出 NFO + 封面，第 2 段以後**只跳過 NFO、保留封面**（媒體庫靠 NFO 認片數，只留第 1 段 NFO 就會收成「一部片、兩段」；多出的封面不破壞合併，OpenAver 自己的瀏覽頁仍逐段顯示各自封面）。多段 token 一律移到輸出檔名最尾端（夾在後綴中間會讓 Jellyfin 認不出來）。
- **F3 — NFO 補強欄位**：任一外部模式下，NFO 額外寫入 `<lockdata>`（best-effort，仍輸出但不保證生效）、`<uniqueid type="num" default="true">`（番號 ID，Jellyfin/Emby 偏好格式）、`<sorttitle>`（排序用）、`<country>Japan</country>`、`<language>ja</language>`（供媒體庫過濾）。這些欄位不影響 OpenAver 自身（OpenAver 讀資料庫、不讀 NFO）。
- **F5 — Scanner 識別外部封面**：掃描封面查找新增一層（同名圖之後、固定名稱之前），辨識 `{番號}-fanart.{ext}`（優先，橫版全圖供瀏覽顯示）與 `{番號}-poster.{ext}`（次之）。能讀回 OpenAver 自己在外部模式產生的封面，也能直接接手 MDCX/Javinizer 等工具已刮削的收藏庫。
- **F6 — Help 多版本手動指引**：Help 新增一段純文字教學，說明「同片多版本（流出/4K/中文）在 Emby/Jellyfin 合併成一筆 + 版本下拉」這件**整個生態圈都靠手動結構解決**的事該怎麼擺檔案，附可照抄的資料夾範例與兩個限制。
- **F7 — 「就地補資料 vs 整理歸檔」措辭換軸**：把 Settings/Help/新手教學描述兩條刮資料路徑的用詞，從暗示「新手用 Scanner、老手用 Search」的技能分層，改為「動不動你的檔案」的意圖區分——就地補資料（Scanner，不改名、適合唯讀網盤）vs 整理歸檔（Search，改名搬移建乾淨媒體庫）。
- **補圖入口擴及 Kodi**（72d）：掃描頁的「補齊外部封面」工具原本只在 Jellyfin/Emby 模式出現，現擴及 Kodi（Kodi 模式掃描本就產同樣的 sidecar 封面，卻拿不到補圖工具——補上既有缺口）。

### Changed
- **F4 — 文案修正**：Kodi 文案從裸 `poster.jpg` 改正為 `{番號}-poster.jpg`（72c 起 Kodi 也輸出 stem 長格式）。**保留 v0.9.7 對 Emby 的正確說明**：`{stem}-fanart.jpg` 僅 Jellyfin／Kodi 讀取，Emby 不認此 fanart 命名（海報與 NFO 在 Emby 正常）。
- **補圖流程文字中性化**（72d，mode-agnostic）：補圖按鈕/提示/通知/log 從寫死「Jellyfin 圖片」改為「外部媒體管理器圖片／封面」，三態（Jellyfin/Emby/Kodi）用戶看到的措辭一致（i18n value 中性化，key 名與端點 path 不變）。
- **Settings 外部管理器改四格 segmented**：由舊三態「關閉｜Jellyfin / Emby｜Kodi」拆成四格「預設｜Jellyfin｜Emby｜Kodi」，記住用戶選的是 Jellyfin 還是 Emby（重整頁面高亮正確）。
- **封面縮圖快取改「新安裝預設開啟」**：縮圖快取（v0.9.10 推出時預設關閉）改為**新安裝預設開啟**，比照進階搜尋畢業模式——既有用戶更新後**維持關閉**（migration 對缺 key 的舊 config 寫 `false`，不驚動老用戶），新用戶開箱即享一頁刷封面。新裝因預設即開、不觸發磁碟空間確認 modal（空庫無衝擊）。

### Fixed
#### 🔧 整理 pipeline 附帶修復（issue #44 後續，feature/72-T-c1/T-c2）/ Organize-pipeline drive-by fixes
- **B1 — 整理搬檔時 DB 跟著搬，消除重複死卡**：先用列表生成（Scanner）原地索引一批片、之後又在搜尋頁對其中某片「整理」（改名搬移）時，舊路徑那筆會變成孤兒死卡，同一片在瀏覽出現兩張（其中一張封面壞掉）。現在整理搬檔會把 DB 那筆原地跟著搬到新路徑（保留入庫時間、瀏覽排序位置、以及你在瀏覽頁加的標籤），整理完當下就只剩一張正確的卡、不必等下次重掃。**任何外部媒體管理器模式皆修，與模式無關。**
- **B2 — 已整理過的檔再整理一次，標題不再疊加**：對 OpenAver 自己整理出來的成品檔（檔名已是 `[番號][廠商] 標題-後綴` 格式）再整理一次，過去會把整段已格式化檔名誤當「標題」塞回去，越疊越長（番號/廠商/後綴重複）。現在會辨識「這是已整理過的成品」而改用刮削/翻譯標題，並把標題開頭多餘的番號前綴剝乾淨（連舊版本已寫進磁碟/資料庫的雙重前綴也一併修好）；真正的原始下載檔名行為不變，中文標題搶救照舊。
- **cd2/part2 整理後 Showcase DB metadata 遺失**：F2 外部模式跳過 cd2 NFO 後，DB 索引改走檔名 parse → actors/tags/date/maker 掉光；B1 repath 還會用此殘缺 row 覆蓋 Scanner 已索引好的紀錄。現整理時把手上的 scraped metadata 直接傳入 upsert，cd2 row 與 cd1 一致；非多段路徑 byte-identical。

#### 🔧 外部管理器相容修正 / External-manager compat fixes
- **補圖 gate 改正向白名單、fail-closed**（72d Codex P2）：掃描頁補圖入口的開關由「不是 jellyfin_emby 就不出現」改為「是 off 才不出現」（正向白名單），新增的 Kodi/Emby 模式正確觸發、未知值安全地不觸發。
- **Kodi sidecar 一律 stem 長格式**（72b Codex P1）：Kodi 模式的封面從裸 `poster.jpg`/`fanart.jpg` 改為與 Jellyfin/Emby 相同的 `{stem}-poster.jpg`/`{stem}-fanart.jpg`，避免同資料夾多部片時裸命名互相覆蓋（多片碰撞）。
- **外部模式單片 refresh 被誤 400**（72d Codex P2-A）：切換外部管理器模式後對單片做「補資料」（refresh_full），400 守衛僅看 `.nfo`/`.jpg` 是否存在、未考慮外部圖補寫機會 → 想補 `{stem}-poster/-fanart` 的 refresh 被拒。加第三條 `will_write_external` 條件（external≠off + 底圖在 + stem 圖缺），off 模式 byte-identical。
- **Enrich 不認 MDCX/Javinizer 匯入的 `{stem}-poster/-fanart.jpg`**（72d Codex P2-B）：F5 讓 Scanner 能讀外部工具的 stem 圖，但 enrich 的 cover-gate 仍要求 `{stem}.jpg` 存在才動作 → MDCX/Javinizer 匯入夾（只有 `-poster/-fanart`、無裸底圖）enrich 後 NFO 指向不存在的 `{stem}.jpg`。改為先判 `_STEM_IMAGE_MODES`：底圖缺但 stem 圖已在磁碟且 `overwrite=false` → 直接認可現況、不重生；off 模式行為不變。

#### 🔧 封面代理白名單跨格式誤殺 SMB 連線磁碟機（TASK-73）/ Image-proxy whitelist cross-format false-positive
- **把 NAS 掛成「連線網路磁碟機」（`K:\` → `\\server\share`）或用 DFS／別名 UNC 的 Windows 用戶，Showcase 封面牆整片空白（影片仍正常播）的修復**。根因：封面代理 `get_image`／`get_video` 的目錄白名單比對只對「請求路徑」跑 `realpath`、沒對「config 白名單目錄」跑，而 `realpath` 會**跨格式改寫**（mapped drive→UNC、DFS／別名→真實 target）→ 兩端字串格式不同，casefold＋NFC 跨不過去 → 合法封面被當白名單外路徑 403 擋掉。現改為兩端對稱正規化（請求端 single-form；config 目錄端 dual-form：normpath＋realpath 兩候選，cache-on-success-only），任一掛載格式都對得上；既有 symlink-escape／`..` 穿越防護完整保留不破。**影片本來就走 PyWebView 直開、不受影響。**

### Internal
- **external_manager 升真四態 config**（`Literal["off","jellyfin","emby","kodi"]`）+ migration（既有存檔 `jellyfin_emby` → load 時就地改寫為 `jellyfin`，idempotent）；圖片命名分支抽共用常數 `_STEM_IMAGE_MODES = ('jellyfin','emby','kodi')`（organizer/enricher 共用，避免 drift）。`!= 'off'` 的 F3 NFO / 多段偵測分支原樣涵蓋三個非 off 值、不動。
- **多段 token 偵測** `_detect_multipart_token` / `_strip_part_token`（cd/dvd/part/pt/disc 系列，token 必落輸出檔名尾端）。
- 補圖 check/generate 後端本就 generic（只認兩 sidecar、零 Jellyfin 特有邏輯），gate 擴三態後零後端改動；`jellyfin_check` capability 描述/data 文字隨補圖中性化（端點 path 與 schema 不變、contract no-op）。

### Non-Goals（明確不做）
- **不支援 Plex**（雖 Plex 1.43.1+ 已有原生 NFO Agent，但 Plex 整合不在本版定位，Settings 不加 Plex）、**不做多版本自動合併**（整個 JAV 生態圈都靠手動結構解決，本版改文檔化手動指引 F6）、**不做 `.actors/` 演員縮圖資料夾**（Kodi-specific、無法共用）、**不做獨立輸出目錄（decoupled output）**（架構改動大、屬獨立 feature）、**不做 NFO 演員名翻譯**（日文名在 Jellyfin/Emby 顯示無問題）、**不讓 Scanner 改名**（維持唯讀原地索引定位，可安全掃唯讀網盤）、**不把版本後綴寫成 tag**、**不做 Scanner 批次整理/一鍵歸檔**（屬未來獨立 feature，本版只先把 F7 措辭換軸做好）。

### i18n
- zh_TW 文案本版交付（settings 外部管理器 hint + 補圖中性化 + Help 四模式措辭）；**milestone 已同步 zh_CN／en／ja**（external_manager 六 key + `skipped_nfo_multipart` toast + ja／zh_CN 多版本 Help + 回補 v0.9.10 漏網 19 key）。
- **Scanner 離頁警告 i18n 化**：3 條硬編碼繁中離頁警告（生成中／圖片檢查中／未存資料夾變更）改走 `window.t()` + 新增 `scanner.leave_warning` 四語系 key——非 zh_TW 用戶離頁提示不再顯示繁中（清 72d Codex P2 deferred 的 pre-existing i18n 債）。
- **Emby fanart 相容文案修正**：撤回 v0.9.11 早期「Emby 同樣支援 `{stem}-fanart.jpg`」的誤述，回復 v0.9.7 的正確說明（Emby 不認此 fanart 背景圖命名，僅 Jellyfin／Kodi 讀取；Emby 的海報與 NFO 正常）；zh_TW／README／README_EN 一併更正。

### 測試
- 全套 pytest **4089 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。
- 新增測試：`test_db_inflow`（B1 整理搬檔 DB repath）/ `test_organizer_multipart`（F2 多段 token 偵測 + 尾端）/ `test_organizer_title`（B2 已整理檔不疊加標題）/ `test_enricher`（enrich 路徑外部模式）/ `test_generate_nfo`（F3 補強欄位）/ `test_jellyfin_compat`（smoke harness，CI 排除）+ 前端守衛（settings 四態 segmented / 補圖 gate 三態化 / Kodi stem）。
- 新增測試（TASK-73 封面代理白名單）：`TestMappedDriveWhitelist`（SMB mapped-drive image/video → 200、DFS 別名 UNC → 200、間歇斷線 dual-form → 200、對稱契約守衛）；既有 symlink-escape／`..` 穿越／WinFsp normpath fallback 安全測試保持綠。
- **transient-guard**：`test_frontend_lint` 中針對舊 `jellyfin_emby` 字面 / `!= 'off'` 的 negative-fingerprint 斷言標 `[transient-guard]`（四態遷移一次性，下個 milestone 評估移除）。

## [0.9.10] - 2026-06-12

本版主軸：**本地 WebP 縮圖快取（opt-in）+ 燈箱單筆刪除**（feature/71）。部署主場景是 app 跑在 PC(SSD)、影片/圖片放在區網 Synology NAS(HDD)，封面牆一頁 90 張每張都直接打 NAS 原圖、HDD 隨機 seek + idle 喚醒 → 一張張慢慢冒。本版讓你在 Settings 手動開啟「封面縮圖快取」後，在本機把封面預先壓成集中極小的 WebP（每張約 32KB），瀏覽時從 SSD（或 OS page cache）出圖、**根本不碰 NAS**；燈箱點進去採 blur-up（小圖秒出 → 原圖載入後就地變清）。**來源真理仍在 NAS**（原圖／NFO 不動），本地只放可回收的衍生快取。另含 issue #57 的燈箱單筆刪除（只移除 DB 紀錄＋它的快取縮圖，**絕不刪你的影片檔或原始封面**），以及進階搜尋畢業移除 Beta 標記。

### Added
#### 🖼️ 本地 WebP 縮圖快取（opt-in，預設關閉）/ Local WebP thumbnail cache
- **Settings「下載劇照」同層級新增「封面縮圖快取」開關**：手動開啟；開啟前依目前片數即時估算空間（每張 ~32KB × 片數）＋ HDD 首次生成時間估算，跳確認 modal 才開始。關閉時行為與現狀完全一致（直接出原圖、不產 WebP）。
- **首次開啟背景全量生成**：開啟後在背景把整庫封面慢慢全部壓成 WebP（一次性、不卡 UI、期間可繼續用）；完成後瀏覽全程零等待。
- **Showcase grid 封面 + 相似探索節點縮圖改用本地 WebP**：一次刷一整頁而非一張張慢慢冒；serve 已存在的 WebP 時**完全不觸發任何 NAS 原圖 stat／read**（NAS 斷線仍能出已快取縮圖）。
- **燈箱 blur-up（模糊變清晰）**：大圖框先放大已快取的小 WebP（秒出、略糊）→ 原始大圖背景載入完成後就地淡入變清。
- **持續跟上新片**：凡影片進 DB（掃描／enrich／重刮）自動生成／更新該片縮圖；漏網的 lazy on-miss 即時補；封面被重刮／enrich 換新後，對應 WebP 就地以新封面重生（不顯示舊圖）。
- **WebP 放 `output/thumb/`**（DB 同層）扁平 hash 分桶、400px 寬 q80、零新依賴（用既有 Pillow）、零 ZIP 體積影響。

#### 🗑️ 燈箱單筆刪除（issue #57）/ Per-item lightbox delete
- **燈箱 metadata 行末新增常駐 muted 垃圾桶 icon**：點擊跳破壞性確認 modal，誠實說明「只從資料庫移除這筆紀錄，影片檔保留在磁碟、不會被刪除；若仍在掃描目錄內，下次掃描會重新被加回」。
- **確認後**：DB 該筆消失 + 它的快取 WebP 一併刪、grid 即時移除那張卡（Alpine splice，無整頁重載）、成功 toast。**磁碟上的影片檔與原始封面圖完全不動**；此刪除能力不揭露給 AI（human-only）。

### Changed
- **進階搜尋畢業、移除 Beta 標記**：自 v0.9.0 推出、歷經多版打磨並於 v0.9.8 起預設開啟，已長期穩定 → Settings quick-toggle 與 Help 文案的「Beta」標記移除（JavLibrary 的 BETA 不受影響，它仍是 beta）。
- **「清除所有影片快取」連動清縮圖**：清空 DB videos 表時連同清整個 `output/thumb/`；移除加入資料夾→其影片被掃描 prune 出 DB 時順手刪它們的 WebP（不留孤兒）。

### Fixed
- **關閉縮圖快取 → 確認 modal → 一律清除**：關閉 toggle 彈確認 modal，確認後**先存檔成功才**清空 `output/thumb/`（新增 DB-safe `POST /api/gallery/thumb/clear`，僅 rmtree、絕不碰 videos DB）；取消則維持啟用、快取保留。
- **prewarm／disable race 硬化**：背景預熱進行中若用戶關閉並清除快取，worker 每筆重讀設定→立即停止，不再把剛清掉的目錄重建回來；被中止時也不送誤導的「完成 N 張」通知（涵蓋 generate 成功與失敗兩種收尾）。
- **燈箱開關 flip「兩張圖重影」**：blur-up 引入的原圖 overlay 層在 grid↔燈箱飛行期間未被隱藏 → 與飛行 ghost 重疊成重影；改為飛行期隱藏整個封面容器（一次蓋住底圖＋原圖兩層）、OPEN/CLOSE 對稱還原。
- **刪除確認 modal 被燈箱蓋住**：root-fix `.fluent-modal` z-index 拉高至燈箱之上（removeActress 確認框同步受惠）。
- **重刮／Enrich 後縮圖快取不更新（舊封面殘留）**：enrich 路徑對已是 `file:///` URI 的路徑重複 encode → invalidate 刪錯 hash → 舊縮圖沒刪掉，換封面後瀏覽頁持續顯示舊封面直到手動清快取。改用冪等的 `coerce_to_file_uri`，與 canonical key 一致。
- **縮圖 serve 兩處邊界修正**：(1) 檔名含字面 `%` 的影片縮圖 404（`unquote` 二次解碼路徑）；(2) 關閉並清除快取後，舊分頁的 `/thumb` 請求仍重建 WebP（miss 路徑未 gate `thumbnail_cache_enabled`）——「關閉並清除」後現確實不再重生。
- **燈箱封面縮水 + 切換跳動 + 進星座模式後反覆縮小**：blur-up 引入的 thumb 在燈箱以 400px 原始尺寸渲染（未放大）→ 封面縮水、flip ghost 量到錯誤矩形而跳動；另星座模式退出（slip-through）路徑缺 `cover_full_url` → `@load` 永不觸發 → 多次進出累積縮小。補 similar API `cover_full_url` 欄位 + CSS `height:60vh`；slip-through 路徑亦補 blur-up 狀態 reset（抽 `_refreshLbFullBlurUp` helper，兩入口共用）。

### Internal
- 縮圖核心模組 `core/thumbnail_cache.py`（hash 命名 / 原子寫 temp+os.replace / generate 失敗 fallback 原圖 / invalidate / clear_all）、`thumbnail_cache_enabled` config plumbing、serve 端點 + lazy 生成 + prewarm 端點、showcase/similar serializer 切 thumb url、失效掛鉤（掃描/enrich/重刮/單筆刪除/清快取）+ serve race 硬化、多輪 Codex review（並發正確性 / prewarm-clear race / disable-skip-done / generate-fail edge，皆 RED→GREEN 實證）。

### Non-Goals（明確不做）
- 不與 Jellyfin/Emby 共用縮圖（hash-keyed 私有 WebP，與既有 `generate_jellyfin_images()` 正交）、不偵測「手動偷換磁碟封面」（失效走事件驅動，重掃/清快取即可）、不鏡像加入資料夾目錄結構（扁平 hash 分桶）、不刪任何磁碟檔（只動 DB row + 衍生 WebP）、不做「刪除後永久不再加回」的 tombstone、不改 Search 頁封面來源、不導 virtual scroll / HTTP2。

### 測試
- 全套 pytest **3845 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。
- 新增：`test_thumbnail_cache`（核心模組）/ `test_api_thumb`（serve / prewarm / clear / prewarm-clear race 5 案）+ async-offload 正斷言（get_thumb / thumb_prewarm / thumb_clear / delete_video 皆 def）+ 前端守衛（縮圖開關 / blur-up / 單筆刪除 element-bound / disable modal / ghost-fly both-restore / z-index contract）。
- **transient-guard**：71b-T1 燈箱刪除鈕位置守衛 `test_t7_delete_trash_button_in_lightbox_details_row` 標 `[transient-guard]`（搬位 relayout 一次性，下個 milestone 評估移除）。

## [0.9.9] - 2026-06-11

本版單一主軸：**新增 JavLibrary 來源（BETA，桌面專屬）**（feature/70）。JavLibrary 是社群索引站，metatube 聯邦 30+ 來源都沒收錄——它擁有別處拿不到的最豐富社群標籤、用戶評分、以及冷門/長尾番號。但全站受 Cloudflare 人機驗證保護、純自動抓一律失敗。OpenAver 的解法：借桌面版 PyWebView 彈出真實瀏覽器視窗，讓你手動點一次驗證，之後在「已過驗證的分頁」裡抓取。因此 JavLibrary **只在桌面 standalone 可用**、**只能在進階搜尋／重刮來源選單以精確番號查詢**、並標示 BETA。

### Added
#### 🆕 JavLibrary 來源（BETA）/ JavLibrary source (BETA)
- **進階搜尋／重刮來源選單新增 JavLibrary（BETA 徽章）**：最豐富社群標籤、用戶評分、冷門番號；metatube 聯邦沒收錄的長尾片在這裡找得到。
- **Cloudflare 驗證流程**：有效期間內透明直接出結果；首次或過期自動彈出 JavLibrary 視窗，你點一下人機驗證（＋ 18 歲同意），系統自動重試並回填結果；驗證未完成或逾時會明確通知——不假裝成功、不靜默換來源。
- **僅桌面 standalone 可用**：dev / 伺服器模式下 JavLibrary 選項灰色不可點，附帶說明；不會出現在 AI 能力清單（`is_beta + manual_only` 雙重排除）。
- **永不進自動搜尋池**：不佔來源順序上限、不參與路由選擇、不影響其他來源行為。

### Internal
- 平台無關 CF transport DI 接縫（`core/cf_transport.py` Protocol）＋ PyWebView 實作（`windows/cf_transport_impl.py`）＋ 來源註冊（`utils/source_config`、scraper、config migration）＋ picker BETA 視覺 / 非桌面 gate ＋ `/api/cf/status`、`/api/cf/abandon` 端點 ＋ 前端 poll 協調（後端無狀態，try-fetch-first）。
- **`_wv_fetch` auto-retry（12s×3）**：同一 session 其他番號 1 秒就回、特定番號卡滿 40 秒才 timeout（隱藏視窗 mid-fetch 導航、JS callback 永不觸發）；縮短單次 timeout 至 12 秒、最多 3 次重試、每次使用獨立 queue + callback（舊 attempt 的遲發 callback 落進已廢棄的 queue，不汙染下一次）；修復 START-492 等間歇性「無結果」。
- 三輪 AI review（Codex ＋ Opus）修正：age-gate 偵測收窄為 `agreeBtn`（避免正常頁 footer 誤判）、search 入口防 500（結構化回應 ＋ 隱藏 JL pill）、`begin_solve` 例外防護、單一命中 `detail_url` 留空、番號核對守衛防回錯片。
- **70c hardening pass**（TASK-70c-B，第二輪 Opus review）：
  - **殭屍行程修正（B1，P1）**：`_on_main_closing` 設 `quitting=True` 後加 `jl_win.destroy()`——pywebview 只在 `instances==0` 才 `_shutdown()`，隱藏的 JL 視窗若未銷毀，關閉主視窗後 process 持續佔 port；此修正啟用了原本的 quitting-guard（舊 dead code）。
  - **關窗攔截（T70c-A，close-intercept）**：`_on_jl_closing` 回 `False` 取消關閉 → 用戶按 ✕ 只隱藏，transport 物件存活、免重啟（Layer 1 root-fix）；`_on_main_closing` quitting=True guard 讓 app 退出時正常放行。
  - **spinner CSS（B2，P2-1）**：`rescrape-cf-waiting` 底下 `.pill-spin` 缺 ancestor-scoped 規則 → 渲染空白；補 `.rescrape-cf-waiting .pill-spin` + 容器 flex layout（token-based，複用 `source-pill-spin` keyframes）。
  - **通知 i18n（B3，P3-2）**：`/api/cf/abandon` 的 `emit_notification` `message=` 硬編碼中文 → EN/JA 看到中文；`title_key = notif.jl_cf_timeout` 四語系均已有翻譯，直接移除 `message=`，toast 僅顯示 title（i18n-compliant，零架構改動）。
  - **守衛強化（P3-1）**：`cf_needed` 位置守衛由 `js.index("cf_needed")`（命中第 185 行註解）改錨 `data.cf_needed`（實際消費表達式）；`TestRescrapeModalSearchHideJlPillGuard` 改錨完整 `x-show` 表達式（L49），防止留空殼字串騙過守衛。
  - **B1 AST 守衛**：`test_standalone_init_order_guard.py` 新增 `test_on_main_closing_destroys_jl_win` 鎖定 `jl_win.destroy()` 呼叫（AST，防靜默回退）。

### Fixed
#### 🔧 JavLibrary CF flow 修通（70d）/ CF re-verify flow fixed
- **40 分鐘後重新驗證從「永久壞、要重開程式」變「打一次勾自動完成」**：clearance 過期後，舊流程把隱藏視窗導到首頁（那裡沒有 CF 可解），又因 `evaluate_js` 在 CF 頁卡 20 秒拖垮整個 JS 橋接 → JavLibrary 從此壞掉、必須重啟。現在彈窗直接帶你到「剛被擋下的搜尋頁」，你點一次人機驗證（或它自己過），視窗約 9 秒自動關閉、結果自動回填——全程不必碰 18 歲同意鈕、不必點頁面任何內容。
- 18+ 同意閘改用 `over18=18` cookie（站台真值；舊 `over18=1` 不被接受、遮罩不消）；此為視覺正確性，不影響資料抓取（mask 是 client-side overlay，從不擋 fetch/parse）。
- **CF 驗證等待提示語氣修正**：等待文案從「請點一下人機驗證」改為「驗證中，通過後自動繼續」（四語系）——CF 常自動過關、多數情況不需主動點，提示語氣改為陳述、避免誤導用戶一定要操作。

### Non-Goals（明確不做）
- 不支援 server / NAS / Docker（CF 需真人 ＋ 真瀏覽器 ＋ 桌面 GUI）、不做自動繞過 CF、不做模糊／演員搜尋、Transport A（cookie→curl_cffi）結構性死路不實作。

- **`fetch()` 主動設 `over18` cookie（Codex P2）**：`fetch()` 在呼叫 `_wv_fetch` 前先主動設 `over18=18` cookie，冷啟動 CF 自動過關後首次 fetch 不會收到 18+ 同意閘 → 不再靜默「無結果」。備用路徑：若 cookie 仍未抑制閘門（race/agreeBtn），改拋 `CfChallengeRequired` 路入 solve/poll 流程，而非回傳空殼 HTML。*`fetch()` now sets the `over18` cookie proactively so the 18+ age gate never returns as empty "no results" (Codex P2); persistent-gate fallback routes into the solve flow.*

### 測試
- 全套 pytest **3743 passed, 2 skipped**（unit ＋ integration，排除 smoke / e2e）＋ `npm run lint`（eslint ＋ stylelint）綠。
- 新增測試：`test_cf_transport` / `test_javlibrary_parser` / `test_javlibrary_scraper` / `test_javlibrary_contracts` / `test_cf_transport_impl` / `test_javlibrary_cf_flow` / `test_api_cf_endpoints` ＋ 前端守衛（`TestJavlibraryPickerT5Guard` / `T6Guard` / `SearchHideJlPillGuard`）＋ 70c-B 強化守衛（`test_on_main_closing_destroys_jl_win` ＋ 強化 cf_needed / x-show 守衛）＋ `_wv_fetch` retry 守衛（`test_retry_then_succeed` / `test_all_attempts_exhausted_raises_timeout` / `test_stale_callback_isolation`）＋ over18 cookie / age-gate fallback 守衛（`test_age_gate_html_raises_cf_challenge_required` / `test_fetch_sets_over18_cookie_before_fetch`）。

## [0.9.8] - 2026-06-06

本版單一主軸：**dim（暗色）主題色彩編碼修復**（feature/69），純前端 CSS、零後端、零依賴、零 i18n、零 ZIP 影響。問題：切到 dim 主題時大量「靠顏色區分狀態」的 UI 變得無法分辨——有碼 vs 無碼來源膠囊長一樣、metatube 連沒連看不出、segmented 選中態消失、警告 banner 跟一般容器混同。根因兩 factor 疊加：(A) 狀態用 `color-mix(語義色 ≤15%, transparent/surface)` 當背景 tint，dim surface 近黑（oklch 26–31%）把低% 色調吃光；(B) dim 沒 override `--color-primary` → 有碼膠囊掉回 DaisyUI 萊姆綠（139°），與無碼 success 綠（166°）只差 27° → 都綠。修復後每個色彩編碼狀態在 dim 下都能一眼辨識，且 light 主題完全不回歸。

### Fixed
#### 🎨 dim 主題色彩編碼 / dim color encoding
- **token patch（根 unlock）**：`theme.css` 的 `[data-theme="dim"]` 區補 `--color-primary`（`oklch(0.66 0.04 250)`，與 light 同 250° 冷色家族、調亮供暗底對比、遠離綠相 → 根除膠囊色相碰撞）+ `--color-warning`（`#ff9f0a` Apple dark-mode amber）。cascade 自動改善所有引用這兩 token 的 dim border/文字通道。
- **來源膠囊**（跨 Settings 掃描來源 / Search / 進階重刮三入口共用）：dim 下有碼（primary 冷藍）vs 無碼（success 綠）一眼可辨；啟用態 tint + solid 色邊；Parts Bin 不可達 warning 色邊；載入 spinner 對比提升。
- **Settings**：segmented 選中態（亮面 + 1.5px inset accent 環，純結構信號）、suffix-tag（改 oklch + accent 邊）、metatube 已連線 status banner（綠 tint + 3px 左色條）、來源上限/全停用警告 banner、tier-hint / focus 環。
- **散點**：進階重刮彈窗 inline-error / 取消鈕 / 數字輸入 focus、showcase 取樣鈕、女優別名 primary 膠囊。
- **color-mix 色相插值修正**（CDP 終驗發現）：tint/border 的 `color-mix` partner 一律用 `transparent`（同 base 慣例）——dim surface 帶藍色相（264°），oklch 與暖色 mix 會沿色相環插值變調（amber→紫）；`transparent` 無色相 → 精準保留語義色。

### Changed
- **進階搜尋 picker 預設改為開啟**：`advanced_search_enabled` 預設值 `false` → `true`（三源對齊：`config.default.json` seed / `AppConfig` Pydantic default / `state-config.js` Alpine 初值）。新用戶／恢復原廠即可在掃描來源頁直接挑單一來源重刮，不需先進設定頁手動開啟；「下載劇照」維持預設關閉（兩者正交）。現有用戶 config.json 既有值不被覆蓋（migration 設計，保留既有偏好）。
- **design-system**：補進階重刮彈窗 + metatube 連線 banner 兩 demo（dim 驗證面）；膠囊 999px 白名單標題「5 類」→「7 類」+ 補類 6（source-pill）/ 類 7（segmented）交叉引用卡；過時 notification center 註解修正。修掉新增 demo 引入的 duplicate `id="settings-components"`（Codex P3）。

### Non-Goals（明確不做）
- 不改 light 主題行為、不換主題 / 不調 surface 明度、不新增第二套狀態色（一律走命名 token）、不碰 design-system 完整 dedupe（→ feature/70）。

### 測試
- CDP 雙主題實機終驗（design-system demo + 生產 /settings 掃描來源頁）：dim 各色彩編碼狀態可辨（amber 67° / 膠囊 blue 250° vs green 147°）、light computed 全 base 值零回歸。
- 全套 pytest 綠（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠；無 pytest 守衛（CLAUDE.md lint-guard：CSS 字串守衛歸 stylelint）。

## [0.9.7] - 2026-06-06

本版主軸：**VR 投影標籤保留 + 自動 VR tag**（feature/68），純後端、單檔 `core/organizer.py`、零新依賴、零 ZIP 影響、零 i18n、零 UI。問題根因：頭顯 App（DeoVR / HereSphere / Skybox / Pigasus）100% 靠「**檔名 token**」判斷 VR 投影/立體格式（`_180_LR` / `_3dh` / `mkx200`…），不讀 NFO；而 OpenAver 改名是用模板從頭重組檔名，原檔名的 VR token **不會被帶過來** → 改名後 VR 檔在頭顯 App 變成平面 2D 播放。本版讓改名時偵測原檔名的 VR token 並**原樣保留**到輸出檔名尾端，同時在 NFO 加一個 `VR` tag/genre。**無 toggle、無需用戶輸入；檔名無 VR token 時輸出 byte 級零變化**（2D 轉檔 / 一般片完全不受影響）。同梱兩處先前的小修正：`/static` no-cache 根治 stale cache、「Jellyfin / Emby 圖片模式」正名。

### Added
#### 🥽 VR 投影標籤保留 + 自動 VR tag / VR projection tag preservation
- **檔名 VR token 偵測 + 原樣保留**：改名時偵測原檔名的 VR 投影/立體 token（投影 `180`/`360`/`180x180`/`EAC360`、鏡頭 `MKX200`/`VRCA220`/`FISHEYE`、立體 `3DH`/`SBS`/`LR`/`TB`…），把「首個~末個 VR token 的 raw 子字串」原樣（不正規化、不砍、保大小寫）接到輸出檔名尾端。sidecar（poster/fanart/NFO）跟隨同 stem 命名不破。
- **自動 VR tag**：偵測到 VR token 的影片，NFO 加 `<tag>VR</tag>` + `<genre>VR</genre>`（固定英文，技術標籤不 i18n），供 Emby/Jellyfin 過濾分類。
- **高精準偵測（零誤判導向）**：唯一字串 token（`MKX200`/`180x180`/`3DH`…，無真番號長這樣）單獨成立；高誤判 token（裸 `180`/`360`/`LR`/`SBS`…）須**同一連續 cluster 內共現**才算數——孤立的 `MIRD-180`/`REBD-360`/`title_LR` 等真番號 → 不算 VR、檔名零變化。

### Changed
- **「Jellyfin 圖片模式」→「Jellyfin / Emby 圖片模式」**：label 與 hint 文案修正（`settings.scraper.jellyfin_mode_{label,hint}`，4 語系 zh_TW/zh_CN/en/ja）+ README / README_EN feature 條目。澄清相容性事實——`{stem}-poster.jpg` 與 Kodi-style NFO 兩者 Emby 與 Jellyfin 皆可讀（親核 Emby 官方 `Movie-Naming.md` 確認支援 `{name}-poster.ext`），`{stem}-fanart.jpg` 僅 Jellyfin 讀取（Emby backdrop/fanart 不支援 `{name}-` 前綴命名，只認 standalone `fanart.jpg`）。**刻意不**額外產生 standalone `fanart.jpg`：用戶若關閉資料夾模式（多片同目錄）會撞檔。配置欄位 `jellyfin_mode` 維持不變、無 migration、無行為變化。

### Fixed
- **`/static` heuristic stale cache**：以 `NoCacheStaticFiles(StaticFiles)` 子類替換 `web/app.py:75` 的原生 `StaticFiles` mount。override `file_response`，在 `super().file_response()` 回傳後對已建好的 response 物件做 post-construction headers mutation（`response.headers["Cache-Control"] = "no-cache"`），200 `FileResponse` 與 304 `NotModifiedResponse` 兩條路徑均有效。ETag / Last-Modified / 304 機制完整保留（同檔案未變回 304 空 body，有變才回 200 新版，免 hard-reload）。封面圖代理的 24h 強快取（`scanner.py get_image`）與影片 Range streaming 完全不受影響（不經此 mount）。
  - **桌面端（PyWebView）零副作用**：`webview.start()` 預設 `private_mode=True, storage_path=None`（pywebview ≥ 6.0 的 `start()` 參數，非 `create_window()` 參數）→ 非持久 WebView2 profile，每次啟動空快取；`no-cache` 對它只是 in-session localhost 多一次可忽略的重驗（< 1ms）。
  - **真正受益者**：`feature/epic-synology.md` 的 Server / NAS(.spk) / Docker 模式——client 端持久瀏覽器快取在 server 更新（換檔 + 重啟）後本不清除，此修正確保下次載入必重驗並取到新版。

### Internal
- **VR 偵測「先切 token 再分類 + 連續 run 共現」演算法**（`_detect_vr_cluster`）：切詞法天然繞掉 monolithic regex 的 `_LR` 底線邊界 bug；共現限定在連續 VR-token run 內（中間夾 non-VR token 即斷開），避免散落 token 跨任意文字誤共現。截斷保護新建獨立 budget path（VR cluster 不被 `max_filename_length` 切掉）；NFO VR tag 對 `<tag>`/`<genre>` 各做 case-insensitive 去重（scraper 已給 VR 不重複）。VR token 全程不進任何 strip 路徑（與「中字」偵測後移除標記相反），並剝除 extracted_title 尾端殘留以免與尾端保留雙寫。

### Non-Goals（明確不做）
- 不做 toggle / 用戶自訂 token 清單（自動偵測）、不做 token 正規化（降低相容性）、不保留解析度/裝置 token（`8K`/`60fps`/`samsung`）、不碰影片轉碼、不做 VR poster 不裁切（issue #6 獨立）、不串接 Emby/DeoVR/DLNA（用戶端的事）。enricher / nfo_updater 不改名路徑不在範圍（VR 偵測是 organize_file 職責）。

### 測試
- 新增 `tests/unit/test_organizer.py` VR 測試（5 class、46+ case）：偵測層全 DoD 表（命中/None/混大小寫/bracket-paren/誤判防護 `1080`/`color`/`SIVR-999`）+ 檔名組裝（suffix×VR 順序 / 超長截斷保護 / 零變化）+ NFO 去重（scraper VR 不重複 / has_vr 兩條分切 / 中字共存 / byte-identical）+ 端到端 wiring + Codex 兩輪 review 回歸（連續 run / 雙寫 / bracket 雙寫 / 多 confirmed run）。
- 新增 `tests/integration/test_static_cache_headers.py`：兩條契約測試（200 帶 `cache-control: no-cache` + `etag`；304 仍帶 `cache-control: no-cache`）。
- 全套 pytest **3588 passed, 2 skipped**（unit + integration，排除 smoke / e2e）+ `npm run lint`（eslint + stylelint）綠。

---

## 0.9.x 系列 — 早期 (v0.9.0 ~ v0.9.6, 2026-05-29 ~ 2026-06-06)

（0.9.7 起見上方全文；此處為 0.9 系列早期 patch 摘要）

- Scraper Federation 三段：B1 Settings 分區 IA + 資料驅動來源 schema / B2 Showcase 進階重刮彈窗 + Search 入口統一 / B3 Metatube HTTP 聯邦（30 provider Parts Bin + promote/demote + 無碼 staged + SSRF 驗證）
- Federation UX Polish：metatube 膠囊三態語意 + Settings IA 退單欄三分類 + quick-toggle + 無碼 segmented 控件
- Active Row Routing：Active Row 拖曳順序成搜尋路由唯一真理、徹底移除 primary_source
- Async Offload + 並發硬化：慢 I/O 移出 event loop（NAS stat / sqlite / config / 同步 HTTP）+ config 寫入鎖/原子寫 + AST 回歸守衛
- Cover Loading UX：grid/Hero 封面三態（skeleton/shimmer/破圖 icon）+ Showcase console 清零

測試數 2937 → 3538。

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
