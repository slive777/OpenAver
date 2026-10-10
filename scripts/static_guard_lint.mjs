#!/usr/bin/env node
/**
 * static_guard_lint.mjs — 靜態文字契約 linter（96b-T1 骨架 + 96b-T2 結構型 kind）
 *
 * 表驅動引擎：`RULES` 陣列（{file, kind, pattern, anyOf?, scope?, count?, note, ...}）+
 * `evalRule(rule, ROOT)` dispatcher。取代 test_frontend_lint.py 大量「某字串必存在／
 * 必不存在／結構順序／結構計數」的純字串/regex/DOM 結構 class（north-star：能用 lint
 * 機械處理的不進 pytest、不耗 Codex 審）。
 *
 * kind 集合：
 *   - required-string（T1）：`pattern` 必須出現（`anyOf: true` 時陣列只需其一命中；
 *     `count` 給定時要求出現次數 ≥ count；預設 1）
 *   - forbidden-string（T1）：`pattern` 不得出現
 *   - dup-id（T2）：單檔內 `id="..."` 屬性值不可重複（`\sid="([^"]+)"` 全域掃描）
 *   - structure-count（T2）：`pattern` 出現次數 `count`（EXACT，`n !== count`）或
 *     `min`（LOWER-BOUND，`n < min`）二擇一，不可同時給/都不給（載入時驗證）
 *   - tag-scan（T2）：抽出特定元素開標籤或視窗，套 required/forbidden，四個 mode：
 *     class-tag（class 錨定 lookahead，single 或 multi）、nested-count（巢狀 depth-
 *     tracking 直接子計數）、anchor-first-tag（anchor 後第一個匹配 tag）、window
 *     （anchor 起固定字元數視窗，含 requiredAttr 存在性斷言 + 全視窗 forbidden 掃描）
 *   - inline-style-token（T2）：遞迴掃 `.html`，逐 tag 檢查「屬性 A 存在 且 style 含
 *     pattern B」co-occurrence（NoInlineStyleDisplay 專用）
 *   - order（T2，獨立 kind）：斷言多個 pattern 的出現位置符合指定順序關係（`items`
 *     + 可選 `occurrence`:'first'|'last'（預設 first）+ 可選 `pairs`（省略時鏈式
 *     items[0]<items[1]<...）+ 可選 `scope`）
 *
 * required-string / forbidden-string / structure-count / order 皆支援可選 `scope`：
 *   - 單一 RegExp（T1）：`.exec()` 後取 match[1]（無 group 則 match[0]）子字串範圍
 *   - `{anchor: RegExp, window: number}`：從 anchor.exec() 的 match.start() 起算固定
 *     字元數視窗（含 anchor 本身）
 *   - `{anchor: RegExp, braceBalanced: true}`：anchor 需匹配到含結尾 `{` 的方法簽名，
 *     從該 `{` 起逐字元計數 depth 直到平衡，回傳方法體（port Python `_extract_method_body`
 *     逐字元迴圈，非 regex 猜大括號配對）
 * scope anchor 找不到＝獨立錯誤（不可誤判為 pattern 缺席／forbidden 通過）；
 * brace-balanced 到檔案結尾仍未平衡＝視同 anchor 找不到，明確報錯。
 *
 * `rule.stripLineComments: true`（96e-T2，Opus 裁決 1）：套用在 resolveScope 抽出的
 * scopedText 上，逐行以 `(?<!:)//.*$` 剝除行內/整行 `//` 注釋後才做 pattern 比對
 * （byte-for-byte port pytest `TestCoverCacheBustGuard._strip_line_comments`，lookbehind
 * 保護 `https://` 不被誤砍）。防止「target 字串移進行內注釋」造成 fail-open false-pass。
 *
 * `file` 欄支援單檔路徑字串，或 `{dir, ext: string[], recursive?: boolean, exclude?: string[]}`
 * 目錄變體。預設非遞迴（複刻 pytest `glob("*.html")` 排除子目錄語意，NoVanillaHandlers
 * 需要）；`recursive: true` 為 `rglob` 語意（NoInlineStyleDisplay 需要，含子目錄如
 * design_system/）；`exclude` 排除特定檔名（NoHardcodedColors 排除 design-system.html /
 * motion_lab.html 兩個 demo 頁）。
 *
 * ESM/JS-structure 家族（§inventory E，96b-T3）：port 為既有 required-string/forbidden-string
 * row（`.map()` DRY，非新 kind——4 頁 ESM guard 逐頁不同構，見 RULES 內逐頁註解），加兩個
 * 泛用引擎新能力：
 *   - `kind: 'file-absent'`（main-loop 特殊分支，見下）：檔案存在＝違規、不存在＝通過
 *     （與其餘 kind「讀檔失敗＝error」語意相反，須在 main loop 的 read-fail-is-error 通用
 *     路徑之前攔截）。
 *   - `tag-scan` 的 tag 內斷言新增 `requiredAnyOf: (string|RegExp)[]`（OR 語意，僅
 *     TestBurstPickerGuard 用到；既有 `required` 維持 AND-only）。
 *
 * 用法：
 *   node scripts/static_guard_lint.mjs                 # 掃真 repo
 *   node scripts/static_guard_lint.mjs <scratch-root>   # 掃 scratch 副本（供 mutation 自驗）
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve, sep } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..');

// ---- args：scratch-root 覆蓋（比照 i18n_lint.mjs 的 argv.find 拆 flag 與 path）----
const argv = process.argv.slice(2);
const rootArg = argv.find((a) => !a.startsWith('--'));
const ROOT = rootArg ? resolve(rootArg) : REPO_ROOT;

// 149a：state-lightbox.js 拆成 5 片（核心 ＋ mask/picker/tags/samples）。
// whole-file forbidden 的「退役字面不得復活」禁令，拆前掃的是整份 2697 行，
// 拆後必須同時覆蓋五個檔才維持等價涵蓋——只守核心＋mask 會讓字面搬進 picker/tags/samples 靜默通過。
const LIGHTBOX_SLICE_FILES = [
  'web/static/js/pages/showcase/state-lightbox.js',
  'web/static/js/pages/showcase/state-lightbox-mask.js',
  'web/static/js/pages/showcase/state-lightbox-picker.js',
  'web/static/js/pages/showcase/state-lightbox-samples.js',
  'web/static/js/pages/showcase/state-lightbox-tags.js',
];

// ---- RULES ----
// note 一律標明來源 class（供 T6 對照表直接引用）。
const RULES = [
  // ---- [TestShowcaseMetadataGuard] showcase.html：10 個 all-of required + 1 個 any-of ----
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'video.series', note: '[TestShowcaseMetadataGuard] metadata binding' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'video.duration', note: '[TestShowcaseMetadataGuard] metadata binding' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'video.director', note: '[TestShowcaseMetadataGuard] metadata binding' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'table-cell-duration', note: '[TestShowcaseMetadataGuard] metadata binding' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'currentLightboxVideo?.director', note: '[TestShowcaseMetadataGuard] lightbox field' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'currentLightboxVideo?.duration', note: '[TestShowcaseMetadataGuard] lightbox field' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'currentLightboxVideo?.series', note: '[TestShowcaseMetadataGuard] lightbox field' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'currentLightboxVideo?.label', note: '[TestShowcaseMetadataGuard] lightbox field' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'lb-details', note: '[TestShowcaseMetadataGuard] lightbox field' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "searchFromMetadata(currentLightboxVideo?.director, 'director')", note: '[TestShowcaseMetadataGuard] searchFromMetadata call' },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', anyOf: true,
    pattern: ["searchFromMetadata(video.series, 'series')", "searchFromMetadata(currentLightboxVideo?.series, 'series')"],
    note: '[TestShowcaseMetadataGuard] series searchFromMetadata call (grid panel or lightbox, OR)',
  },
  { file: 'web/templates/showcase.html', kind: 'structure-count', pattern: 'bi bi-eye toggle-info-eye-icon" :class="{ \'toggle-info-eye-icon-hidden\': infoVisible }"', count: 2, note: '[TASK-148b-T4] 影片牆／女優牆眼睛按鈕各一個 bi-eye <i>（CD-148b-8 交叉淡入）。用 structure-count 不用 required-string：後者的 count 是下限（:5518 的 n < rule.count），第三顆同款圖示會被放行——同檔 :355 的 100b-T1/P2-1 記過同一個坑' },
  { file: 'web/templates/showcase.html', kind: 'structure-count', pattern: 'bi bi-eye-slash toggle-info-eye-icon" :class="{ \'toggle-info-eye-icon-hidden\': !infoVisible }"', count: 2, note: '[TASK-148b-T4] 影片牆／女優牆眼睛按鈕各一個 bi-eye-slash <i>（CD-148b-8 交叉淡入）。exact 計數理由同上一條' },

  // ---- [lint-guard 101d-T2] 焦點適用邊界就地註解不得被順手刪（spec-101 §7.3-2 要求就地註解；plan-101d §5.2/§5.3）----
  // 錨四處「刻意不同/刻意不接」設計意圖註解的唯一關鍵句。刪任一句即紅（mutation 自驗）。
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'per-image 門檻刻意不同', note: '[lint-guard 101d-T2] 影片 gate≠女優 gate 就地註解（plan-101d §2.2）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '與影片 _posterModeActive() 刻意不同', note: '[lint-guard 101d-T2] 女優側反向指引註解（plan-101d §2.2）' },
  { file: 'web/static/css/pages/showcase/08-remainder.css', kind: 'required-string', pattern: '相似卡刻意固定右裁（桌面', note: '[lint-guard 101d-T2] 桌面 similar 卡固定右裁註解（plan-101d §5.3）' },
  { file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string', pattern: '相似卡刻意固定右裁（手機 burst', note: '[lint-guard 101d-T2] 手機 burst similar 卡固定右裁註解（plan-101d §5.3）' },

  // ---- [lint-guard 124b-T4] 女優卡資訊區數值可點（薄守衛，不得回退成純顯示）----
  // 設計尚未經 owner 真機驗收 ⇒ 只鎖「不得回退到已知壞值（點不下去）」，
  // 不寫 token 清單／順序／視覺的重型對帳（task-workflow.md Step 1、feature/108 教訓）。
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '_onActressCardMetadataClick(part.dim, part.value)',
    note: '[lint-guard 124b-T4] 女優卡資訊區年齡/身高/罩杯可點（CD-124b-13）' },

  // ---- [lint-guard 124c-T1] 燈箱換片箭頭錨定封面（plan-124c CD-1/CD-2）----
  // 存在性守衛（粗顆粒）：只保證兩條宣告還在。行為正確性由 T1 的 CDP 量測負責（FE-GUARD-06）。
  { file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: 'anchor-name: --lb-cover',
    note: '[lint-guard 124c-T1] 燈箱箭頭錨定封面：錨點宣告（刪掉＝箭頭回視窗中心，手機重新搶 ★ 的點擊）' },
  { file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: 'top: anchor(--lb-cover center, 50%)',
    note: '[lint-guard 124c-T1] 燈箱箭頭錨定封面：對齊宣告 ＋ 無錨點時的 50% fallback（兩者同一條字面，不可拆）' },

  // ---- [lint-guard 152d-codex-fix] settings ? 浮層說明文案接線 ----
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: "t('settings.scraper.focal_help')", note: '[lint-guard 152d-codex-fix] ? 浮層的說明文案接線' },
  // [lint-guard 152d-popover-up] 人臉自動對焦那一列是「刮削與翻譯」卡的最後一列，浮層往下展開
  // 會溢出卡片底邊；而 .card 在 dim 主題有 backdrop-filter（fluent-materials.css Rule 14）自成
  // stacking context，浮層的 z-index:50 逃不出那張卡 ⇒ 被下一張卡（列表生成）的背景蓋住後半段。
  // 兩條一組鎖住修法的兩半：class 掛在 HTML 上、規則存在於 CSS 裡。任一半沒了浮層就靜默被蓋住，
  // 而這是純視覺後果，前端測試不會紅（沒有 Alpine runtime、也不量佈局）。
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'class="help-popover help-popover--up"', note: '[lint-guard 152d-popover-up] focal ? 浮層往上展開的 class 接線（卡片最後一列，往下會被下一張卡蓋住）' },
  { file: 'web/static/css/components/help-popover.css', kind: 'required-string', pattern: '.help-popover--up {', note: '[lint-guard 152d-popover-up] --up modifier 的 CSS 規則本體（bottom:100% 翻轉展開方向）' },

  // ---- [TestMaskToggleGuard] 98b-T4 起家、99a-T3 沿用：遮罩綁定 / 生命週期 guard / no-硬編-ratio / endpoint URL ----
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@click="openMask', note: '[TestMaskToggleGuard] mask toggle icon button 綁 openMask' },
  // 98b P2 fix（Codex）：commit/re-check guard 由 path 比對（_maskVideoPath/sessionPath）
  // 升級為單調遞增 session id（_maskSession）——path 比對在「同片重開」邊界不夠精確。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'this._maskSession++',
    scope: { anchor: /openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] openMask 遞增 _maskSession（每次開啟即新 session，Codex P2）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'this._maskSession++',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _resetMask 遞增 _maskSession（換片/關燈箱使舊 session 失效，Codex P2）',
  },
  // 98b P2 fix(二)（Codex）：新 session 起手/invalidate 必須清 _maskDetecting——舊 detect await 的
  // finally 因 session 不符會跳過清 spinner，不在此重置則新遮罩頂著卡死 spinner。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'this._maskDetecting = false',
    scope: { anchor: /openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] openMask 清 _maskDetecting（新 session 起手非偵測中，防舊 spinner 漏入，Codex P2）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'this._maskDetecting = false',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _resetMask 清 _maskDetecting（invalidate 時防偵測態漏進下個 session，Codex P2）',
  },
  // 99a-T3：原本錨定 `async toggleMaskMode()` / `async closeMask()` 的兩條 session-recheck 規則
  // 因該兩函式整條移除而 anchor-not-found（引擎不變式：硬錯，阻斷 npm run lint）。改錨定承接
  // 相同語意的新函式——toggleMaskMode 的「翻頁後 session recheck」併入 openMask 自身的
  // force-detect await；closeMask 的「async 存檔前後 session recheck」由 confirmMask 承接。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'session === this._maskSession',
    scope: { anchor: /async\s+openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] openMask force-detect await 後 session re-check（不誤動已切走的別片 UI；99a-T3 承接原 toggleMaskMode 語意）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'session === this._maskSession',
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] confirmMask await 後 session re-check（不誤存已切走的別片；99a-T3 承接原 closeMask 語意）',
  },
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: '_maskVideoPath',
    note: '[TestMaskToggleGuard] 舊 path-based guard 變數不得復活（已由 _maskSession 取代，Codex P2）（149a：五個分片同禁）',
  })),
  // 98b-T6：亮窗幾何改 reactive data（imperative $nextTick 算），禁量測-in-binding 復活。
  // 100b-T1（CD-4/CD-5）：遮罩 DOM 抽出 web/templates/_macros/focal_mask.html partial，
  // 下列 6 條（原標 #2/#3/#4/#5/#6/#9）file: 改指向 partial——守護對象（遮罩互動綁定 /
  // 退役字樣 forbidden）隨 DOM 一起搬家，否則 forbidden 3 條會靜默轉綠成死守衛（CD-5）。
  { file: 'web/templates/_macros/focal_mask.html', kind: 'required-string', pattern: ':style="_maskWinStyle"', note: '[TestMaskToggleGuard] .lb-mask-window 綁 reactive data _maskWinStyle（非量測-in-binding）' },
  { file: 'web/templates/_macros/focal_mask.html', kind: 'forbidden-string', pattern: '_maskWindowStyle()', note: '[TestMaskToggleGuard] 禁 :style 內呼叫量測方法（stale 幾何反模式 98b-T6）' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', pattern: "$watch('currentLightboxVideo?.path'", note: '[TestMaskToggleGuard] 換片 _resetMask 視覺防線（CD-98b-8，防遮罩畫到下一片）' },
  // 99a-T1a 已刪除 /crop-mode 路由；99a-T3 移除前端這條 fetch 呼叫（closeMask 整條拆掉，改
  // confirmMask 打 /video/focal）。TASK-99a-T1a 原文把「這條 required-string 規則的正式替換」
  // 定在 99a-T4，但 99a-T3 task card 的 Opus correction A 覆核後裁定：required-string 規則若
  // 原樣留著，字串消失後會軟性 RED（pattern 缺席，非 anchor 錯——不阻斷 npm run lint，但整套
  // lint 會帶著一條「已知會紅」的規則跑，不符 `npm run lint` 全綠的收工標準）。故 T3 移除本條
  // （非留給 T4），T4 仍照原計畫新增拖曳/V-X/gating-class 三條全新斷言。
  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '/api/showcase/video/detect-focal', note: '[TestMaskToggleGuard] detect-focal endpoint fetch URL' },
  // [lint-guard 101d-T3] 影片對焦存檔端點不得復名為 `/api/showcase/video/focal`——該路徑「video/ 緊接 focal」
  // 像影片廣告 beacon，會被 ad/privacy 過濾清單（uBlock/AdGuard/Brave/Pi-hole）在瀏覽器端 net::ERR_FAILED
  // 秒殺，✓ 存檔請求根本到不了 server（2026-07-18 owner 實測 + CDP/Network 診斷）。正名 video/save-focal。
  // 註：`video/detect-focal`/`video/save-focal` 皆不含子字串 `video/focal`（video/ 後非恰為 focal）→ 不誤觸。
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: '/api/showcase/video/focal',
    note: '[lint-guard 101d-T3] 影片對焦存檔端點禁復名 video/focal（撞廣告過濾清單），用 video/save-focal（149a：五個分片同禁）',
  })),
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'getComputedStyle',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 讀 CSS var（getComputedStyle）非 JS 硬編比例',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '--poster-crop-ratio',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 讀 --poster-crop-ratio（單一真理）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'forbidden-string', pattern: '0.71',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 不得硬編 0.71（比例讀 CSS var）',
  },
  {
    // 99a Gemini P2 回歸鎖：拖曳起手的 startLeft 必須 clamp（否則臉貼邊時窗子停在界內、
    // 拖曳從界外起算＝死區）。刻意鎖「const startLeft = clampMaskWinLeft(」整串而非裸的
    // Math.max/Math.min——後者在 _maskDragStart 的 brace scope 內另有 onMove 也在用，
    // 會 fail-open（拔掉起手 clamp 仍綠）。
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: 'const startLeft = clampMaskWinLeft(',
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a：_maskDragStart 起手 startLeft 須經 clampMaskWinLeft 鉗進封面邊界',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'forbidden-string', pattern: /2\s*\/\s*3/,
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 不得硬編 2/3 比例（讀 CSS var）',
  },

  // 🔴 遷移粒度守則（CLAUDE.md）：`Math.min(W, H*r)` / `Math.min(H, W/r)` 的幾何數學原本天然
  // 落在 _computeMaskWinStyle 那 4 條 scope 規則的掃描範圍內；100b-T2a 把它搬到
  // shared/mask-geometry.js（可測試性 + G1 單一 writer）後，該檔一度是零規則覆蓋的新盲區——
  // 未來若有人在 computeMaskWinGeometry() 內誤植字面比例（把參數 r 改寫死 0.75），原本的
  // 「比例必須讀 CSS var、不得硬編」契約會靜默失守。替代網須同粒度、寧 fail-closed 不 fail-open：
  // 比例一律走參數 r，本檔不得出現任何字面比例常數。
  {
    file: 'web/static/js/shared/mask-geometry.js', kind: 'forbidden-string', pattern: '0.71',
    note: '[TestMaskToggleGuard] 100b-T2a：mask-geometry.js 不得硬編影片比例 0.71（一律走參數 r，由呼叫端讀 CSS var）',
  },
  {
    file: 'web/static/js/shared/mask-geometry.js', kind: 'forbidden-string', pattern: '0.75',
    note: '[TestMaskToggleGuard] 100b-T2a：mask-geometry.js 不得硬編女優比例 0.75（一律走參數 r，由呼叫端讀 CSS var）',
  },
  {
    file: 'web/static/js/shared/mask-geometry.js', kind: 'forbidden-string', pattern: /2\s*\/\s*3/,
    note: '[TestMaskToggleGuard] 100b-T2a：mask-geometry.js 不得硬編 2/3 比例（同 _computeMaskWinStyle 的既有禁令，遷移後同粒度補網）',
  },

  // ---- [TestMaskToggleGuard] 99a-T4：T3 新互動（force-detect 預覽 + 左右拖曳 + ✓/✗）回填守衛 ----
  // §1 拖曳 wiring（4）：.lb-mask-window 起手綁定 + 函式定義存在 + 退役 toggle handler 兩檔 forbidden。
  {
    file: 'web/templates/_macros/focal_mask.html', kind: 'required-string',
    pattern: '@pointerdown="_maskDragStart($event)"',
    note: '[TestMaskToggleGuard] 99a-T4：.lb-mask-window 綁新拖曳起手（取代 98b @click="toggleMaskMode()"）',
  },
  {
    file: 'web/templates/_macros/focal_mask.html', kind: 'forbidden-string', pattern: 'toggleMaskMode',
    note: '[TestMaskToggleGuard] 99a-T4：退役 toggle handler 不得復活（thorough-cleanup lock）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: '_maskDragStart(evt) {',
    note: '[TestMaskToggleGuard] 99a-T4：拖曳起手函式定義存在',
  },
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: 'toggleMaskMode',
    note: '[TestMaskToggleGuard] 99a-T4：退役 toggle handler 不得復活（thorough-cleanup lock）（149a：五個分片同禁）',
  })),

  // §2 退役識別字 forbidden-string（3，比照既有 _maskVideoPath 先例 :136）：_maskMode/closeMask
  // 全域零殘留，本 task 補鎖住這個「巧合乾淨」的狀態，防未來以舊名復活。
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: '_maskMode',
    note: '[TestMaskToggleGuard] 99a-T4：退役 default⇄auto toggle 狀態不得復活（thorough-cleanup lock）（149a：五個分片同禁）',
  })),
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: 'closeMask',
    note: '[TestMaskToggleGuard] 99a-T4：退役「點窗外隱式存」函式不得以舊名復活（confirmMask/cancelMask 已取代）（149a：五個分片同禁）',
  })),
  {
    file: 'web/templates/_macros/focal_mask.html', kind: 'forbidden-string', pattern: 'closeMask',
    note: '[TestMaskToggleGuard] 99a-T4：overlay @click.self 不得指回舊 closeMask（現為 cancelMask）',
  },

  // §3 拖曳 listener 對稱 add/remove（6，scope-anchored——flat required-string 驗不出「掛在對的
  // 函式、解在對的函式」，見 TASK-99a-T4 技術要點 §3 的「錯位置」反例）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "document.addEventListener('pointermove'",
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskDragStart 掛 pointermove（拖曳跟手核心）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "document.addEventListener('pointerup'",
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskDragStart 掛 pointerup（放開結束拖曳）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "document.addEventListener('pointercancel'",
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskDragStart 掛 pointercancel（系統中斷手勢時仍收尾，防洩漏）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "document.removeEventListener('pointermove'",
    scope: { anchor: /_maskRemoveDragListeners\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskRemoveDragListeners 對稱移除 pointermove（防洩漏）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "document.removeEventListener('pointerup'",
    scope: { anchor: /_maskRemoveDragListeners\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskRemoveDragListeners 對稱移除 pointerup（防洩漏）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "document.removeEventListener('pointercancel'",
    scope: { anchor: /_maskRemoveDragListeners\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskRemoveDragListeners 對稱移除 pointercancel（防洩漏）',
  },

  // §4 V/X handler + gating class（8：5 + 3 顆原按鈕 gate）
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@click.stop="confirmMask()"',
    note: '[TestMaskToggleGuard] 99a-T4：✓ 鈕綁 confirmMask（CD-6 就地佔 .cover-actions）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@click.stop="cancelMask()"',
    note: '[TestMaskToggleGuard] 99a-T4：✗ 鈕綁 cancelMask',
  },
  {
    file: 'web/templates/_macros/focal_mask.html', kind: 'required-string', pattern: '@click.self="cancelMask()"',
    note: '[TestMaskToggleGuard] 99a-T4：overlay 點窗外 = ✗（owner 定案，非 closeMask）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'cancelMask() {',
    note: '[TestMaskToggleGuard] 99a-T4：cancelMask 函式定義存在',
  },
  // confirmMask 定義本身已被既有規則（:131-135，scope anchor `async confirmMask()`）transitively
  // 鎖住——若函式被砍/改名，該既有規則的 anchor-not-found 會直接硬錯，不需要本 task 重複加一條。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ":class=\"{'cover-actions--focal-edit': _maskVisible}\"",
    note: '[TestMaskToggleGuard] 99a-T4：.cover-actions 容器 focal-edit gating class 綁定（CD-6，桌面 hover-only 常顯解法）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="!_maskVisible" @click="playVideo(',
    note: '[TestMaskToggleGuard] 99a-T4：play 鈕編輯中暫隱（CD-6）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="!_maskVisible" @click="openLocal(',
    note: '[TestMaskToggleGuard] 99a-T4：開資料夾鈕編輯中暫隱（CD-6）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="shouldShowEnrichButton(currentLightboxVideo) && !_maskVisible"',
    note: '[TestMaskToggleGuard] 99a-T4：補缺鈕編輯中暫隱（CD-6，錨完整值防 has_cover/has_nfo 條件被誤刪只剩 !_maskVisible）；149b：條件改抽成 shouldShowEnrichButton()，has_cover/has_nfo 的判斷邏輯本身由 enrich-gate.js 的 node:test 守，這條 required-string 只守『呼叫點沒有被誤刪成只剩 !_maskVisible』這個原本要守的目的',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="shouldShowEnrichButton(video)"',
    note: '[EnrichGate] 149b-CD-10：卡片補資料鈕的呼叫點（與燈箱 :359 那條成對）。'
        + '判斷邏輯由 enrich-gate.js 的 node:test 守，這條只守「呼叫點沒有被改回內聯條件或被誤刪」。'
        + '⚠ 兩條必須成對存在——只留一條會讓卡片與燈箱的顯示條件靜默漂移（149a 教訓）。',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="!currentLightboxVideo?.has_cover && !currentLightboxVideo?.number && !_maskVisible"',
    note: '[EnrichGate] 149b-CD-11：封面逃生口提示的顯示條件（spec §2.5：沒封面「且」沒番號，真實庫 373 部）。'
        + '拿掉「沒番號」那半會讓提示也長在 75 部有番號、🔍 本來就有效的片上——那句提示會叫使用者去手動放圖，'
        + '而正確做法是按 🔍。實測：拿掉之後 npm run lint:html 1335 條全綠，這條是唯一的安全網。',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '        shouldShowEnrichButton,',
    note: '[EnrichGate] 149b-CD-9：卡片與燈箱兩顆 🔍 都靠 stateLightbox() 回傳物件把這個函式送進 Alpine scope。'
        + '刪掉這一行 → 兩處 x-show 求值成 undefined → 兩顆按鈕同時永久消失，而 npm run lint 1336 條、'
        + 'npm test 1630 條、./scripts/check.sh 全綠（實測）。eslint 也不會抓孤兒 import（實測 exit 0）。'
        + '前導 8 空白是刻意的：它把 return 物件裡的屬性與 import 那一行區分開。',
  },

  // ---- [LbActorAgeRefresh] 149b-CD-3：燈箱女優列「發行時年齡」六個刷新點的計數守衛 ----
  // 規則：`_refreshLbActorAges()` 必須緊跟每一處既有 `_refreshLbFullBlurUp()`（五處，字面相同），
  // 第六處在 state-actress.js loadActresses() 成功路徑，字面帶 `?.`（獨立第五條規則，見下）。
  // exact count 而非 required-string 的下限：後者放行「多加一次」，這裡任何一處漏改／多改
  // 都要被抓到（漏改＝使用者看到上一部片的舊歲數；多改＝重複刷新非本 task 的範圍）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'structure-count',
    pattern: 'this._refreshLbFullBlurUp();', count: 2,
    note: '[LbActorAgeRefresh] 149b-CD-3：state-lightbox.js 兩個既有 blur-up 刷新點（_setLightboxIndex／refreshVideoData）。'
        + 'exact count 鎖住既有呼叫點沒有被誤刪或重複——本 task 不動這支既有 helper 本身，只確保它仍在原處，'
        + '因為下一條規則要求 _refreshLbActorAges() 緊跟在它後面。',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'structure-count',
    pattern: 'this._refreshLbActorAges();', count: 2,
    note: '[LbActorAgeRefresh] 149b-CD-3：state-lightbox.js 兩處刷新點（_setLightboxIndex :186 之後、'
        + 'refreshVideoData :941 之後）。漏掉任一處：換片或補資料成功後燈箱顯示上一部片的女優歲數，'
        + '不是資料錯誤而是顯示錯誤（spec §2.3 存在的理由就是別顯示錯的數字）。',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'structure-count',
    pattern: 'this._refreshLbFullBlurUp();', count: 3,
    note: '[LbActorAgeRefresh] 149b-CD-3：state-similar.js 三個既有 blur-up 刷新點（:466／:490／:1720）。'
        + 'exact count 鎖住既有呼叫點沒有被誤刪或重複，理由同上一條。',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'structure-count',
    pattern: 'this._refreshLbActorAges();', count: 3,
    note: '[LbActorAgeRefresh] 149b-CD-3：state-similar.js 三個相似探索退出路徑的刷新點（:466／:490／:1720，'
        + '三處缺一不可）。使用者從相似探索挑一部相似片、退出後回到燈箱，任一處漏改都會讓名字旁邊寫的是'
        + '上一部片的歲數（mutation 點②驗的正是這件事）。',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: 'this._refreshLbActorAges?.();', count: 1,
    note: '[LbActorAgeRefresh] 149b-CD-3 刷新契約第 6 點：生日資料是非同步到位的，'
        + '這一行是「燈箱已經開著時，資料到了要重算一次」的唯一觸發點。刪掉它 → 使用者在資料還沒回來時開燈箱，'
        + '年齡永遠不出現，除非他關掉燈箱再開一次。exact count 而非 required-string：後者 count 是下限，'
        + '第二個誤增的呼叫點會被放行。⚠ 這一行的字面帶 ?.，與另外五處不同，所以不會被 state-lightbox.js／'
        + 'state-similar.js 那四條的計數涵蓋——必須獨立一條。',
  },

  // ---- [TestMaskToggleGuard] 99a-T5：detect-first 重新設計（Bug 1 修法）+ 星空等待動畫 lifecycle ----
  // 舊 race 旗標退役（比照既有 _maskVideoPath/_maskMode/closeMask 先例 :136/193/197/201）。
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: '_maskUserAdjusted',
    note: '[TestMaskToggleGuard] 99a-T5：detect-first 重新設計後 race 在結構上不可能，舊自查補強旗標不得復活（thorough-cleanup lock）（149a：五個分片同禁）',
  })),

  // 新 gating 條件字面存在（.lb-mask-window + ✓ + ✗ 三處，count-based 確保三處都改到，防未來
  // 重構把其中一處漏改回舊的單旗標 x-show="_maskVisible"）。
  // 100b-T1（Opus 裁決 D 待決問題1）：原 count:3 拆兩條——引擎的 count 是單一 file: 內計數，
  // 無跨檔加總語法。.lb-mask-window 那份隨 DOM 搬進 partial（count:1）；✓/✗ 兩份仍在
  // showcase.html 的 .cover-actions（未搬動，count:2）。
  { file: 'web/templates/_macros/focal_mask.html', kind: 'required-string', pattern: 'x-show="_maskVisible && !_maskDetecting"', count: 1, note: '[TestMaskToggleGuard] 99a-T5→100b-T1：.lb-mask-window 收窄 gating（detect 完成才可拖），partial 內僅 1 處' },
  // 100b Codex P2-1 fix：showcase.html 內同一 pattern 其實出現 4 次（女優 ✓/✗ + 影片 ✓/✗），
  // 但舊規則 count:2 是「下限」（evalRequiredString：n < count 才報錯）而非「恰好 2」——
  // 只要總數 ≥2，砍掉其中一個分支（例如整個影片 ✓/✗）也會被誤判通過，守衛形同虛設。
  // 拆成兩條 scope-anchored 規則，各自錨到專屬 <template x-if> 分支（全檔僅出現一次，
  // 唯一性已用 grep 確認），window 只需蓋過該分支內的 ✓/✗ 兩處、且在下一分支的同 pattern
  // 之前收尾，兩個分支才能被「各自」的 count:2 下限獨立守住。
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'x-show="_maskVisible && !_maskDetecting"', count: 2, scope: { anchor: /<template x-if="currentLightboxActress">/, window: 8800 }, note: '[TestMaskToggleGuard] 99a-T5→100b-T1→100b P2-1 fix：女優分支 ✓ + ✗ 兩處收窄 gating（detect 完成才可提交），scope 錨到女優 <template x-if> 分支，count=2 獨立鎖住兩處都改到（window 含 100b P2-2 fix 新增的 photo-frame wrapper 註解，與下一條影片 scope 的 anchor 相距 15069 字元，仍安全不重疊）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'x-show="_maskVisible && !_maskDetecting"', count: 2, scope: { anchor: /<template x-if="currentLightboxVideo && !currentLightboxActress">/, window: 9000 }, note: '[TestMaskToggleGuard] 99a-T5→100b-T1→100b P2-1 fix：影片分支 ✓ + ✗ 兩處收窄 gating（detect 完成才可提交），scope 錨到影片 <template x-if> 分支，count=2 獨立鎖住兩處都改到' },

  // 星空等待動畫函式定義存在（ghost-fly.js）+ callsite（state-lightbox.js openMask，唯一啟動點）。
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'function playFocalDetectWait', note: '[TestMaskToggleGuard] 99a-T5：ghost-fly.js 定義星空等待迴圈動畫（start）' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'function stopFocalDetectWait', note: '[TestMaskToggleGuard] 99a-T5：ghost-fly.js 定義星空等待動畫停止（stop）' },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'playFocalDetectWait',
    scope: { anchor: /async\s+openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：openMask 啟動星空等待動畫（單一入口）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'prefersReducedMotion',
    scope: { anchor: /async\s+openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：openMask 啟動星空動畫前 PRM guard（C23 per-callsite，比照 state-similar.js isPRM pattern）',
  },

  // _maskStopWaitAnim 對稱停止 helper：定義存在 + 內部呼叫 GhostFly.stopFocalDetectWait +
  // 三個生命週期端點（openMask finally / _resetMask / _maskTeardown）都呼叫它（比照既有
  // _maskRemoveDragListeners 的「定義一次、多處對稱呼叫」寫法）。
  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopWaitAnim() {', note: '[TestMaskToggleGuard] 99a-T5：星空等待動畫對稱停止 helper 函式定義存在' },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'stopFocalDetectWait',
    scope: { anchor: /_maskStopWaitAnim\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：_maskStopWaitAnim 呼叫 GhostFly.stopFocalDetectWait',
  },
  {
    // 101b-T2（§A-5 修訂框）改鎖：_maskStopWaitAnim() 隨 fallback 分支搬進 _maskStartSettle
    // （openMask finally 現在只呼叫 _maskStartSettle(sawFace)，不再直呼 _maskStopWaitAnim()）
    // ⇒ 該字面字串離開 openMask 的 brace scope，anchor 必須跟著改指 _maskStartSettle。
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopWaitAnim()',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T2：_maskStartSettle 的 fallback 分支（g0===null / 動畫層不可用 / PRM）呼叫 _maskStopWaitAnim（防 repeat:-1 loop 洩漏，CD-4b/CD-11a/CD-4c 同一分支）',
  },
  {
    // 101b-T2：正常（收斂）路徑改用 handoffFocalDetectWait 交棒（不 clearProps），
    // 與上一條的 fallback 路徑（全停）互斥地 scoped 在同一函式內。
    // 🔴 pattern 必須鎖**呼叫形式**（含 `(this._maskWaitTl)`），不可只鎖裸識別字
    //    `handoffFocalDetectWait`——同一 scope 內 canAnimate gate 的
    //    `typeof window.GhostFly.handoffFocalDetectWait === 'function'` 也含該識別字，
    //    裸鎖會被 gate 那行**恆滿足** ⇒ 真正的交棒呼叫整行刪掉仍綠（fail-open）。
    //    此為 101b-T2 獨立 review 實跑 mutation 抓到（刪 :1376 呼叫、留 gate → 不紅）。
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'handoffFocalDetectWait(this._maskWaitTl)',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T2（CD-4b）：_maskStartSettle 正常路徑呼叫 GhostFly.handoffFocalDetectWait(this._maskWaitTl) 交棒星空（不 clearProps）',
  },
  {
    // 101b-T2（CD-4c）：C23 per-callsite PRM guard 隨 gate 搬進 _maskStartSettle（比照既有 :344
    // openMask 內的同名 required rule——canAnimate 的組成之一）。
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'prefersReducedMotion',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T2（CD-4c）：_maskStartSettle 的 canAnimate gate 含 PRM 檢查（C23 per-callsite）',
  },
  {
    // Codex PR review P2 修正：canAnimate gate 必須連 `this._maskWaitTl`，缺席時
    // handoffFocalDetectWait(null) 解構會拋 TypeError、卡死 settling 狀態。
    // 🔴 pattern 必須鎖**連接形式** `&& this._maskWaitTl`，不可只鎖裸識別字
    //    `_maskWaitTl`——同一 scope 內 :1386 有 `handoffFocalDetectWait(this._maskWaitTl)`
    //    呼叫，裸鎖會被那行**恆滿足** ⇒ gate 本身被拿掉仍綠（fail-open，與 :369-373
    //    handoffFocalDetectWait 呼叫式那條抓到的同型陷阱）。
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '&& this._maskWaitTl',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] Codex PR review P2：_maskStartSettle 的 canAnimate gate 連 this._maskWaitTl，缺 wait handle 時退瞬現而非解構 null 拋錯',
  },
  {
    // 101b-T5：步驟③原本無條件寫 `this._maskWinStyle = g0;`（全幅）——hasFace 時 g0 是
    // 收斂起點（步驟⑥的 proxy tween 會覆寫），但 !hasFace 沒有任何後續步驟收斂，等於
    // 讓「沒找到臉」永久停在全幅，遮罩對使用者隱形（scrim 無可暗化區域），違反 spec
    // §4.2「沒找到臉→亮窗直接以基準位置淡入，不收斂」。修法：
    // `hasFace ? g0 : (this._computeMaskWinStyle() || this._maskWinStyle)`（與既有 PRM
    // fallback 分支 :1380 呼叫同一個 _computeMaskWinStyle()，CD-8 的直接編碼）。
    // 鎖 `hasFace ? g0` 字面，防止未來被誤還原成單行 `this._maskWinStyle = g0;`。
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: 'hasFace ? g0',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T5：_maskStartSettle 步驟③ no-face 落基準幾何（hasFace ? g0 : _computeMaskWinStyle()），不永久停在全幅',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopWaitAnim()',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：_resetMask 呼叫 _maskStopWaitAnim（換片/關燈箱/ESC 中斷路徑）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopWaitAnim()',
    scope: { anchor: /_maskTeardown\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：_maskTeardown 防禦性再保險呼叫 _maskStopWaitAnim（比照 _maskRemoveDragListeners 先例）',
  },
  {
    // 101b-T2（§A-3 落點表 #3）：GhostFly export 守衛——漏 export ⇒ canAnimate 恆 false ⇒
    // 收斂永不播，而所有 DoD 照樣綠（fallback 是合法路徑）。比照 :336-337 def 家族形狀。
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'handoffFocalDetectWait: handoffFocalDetectWait',
    note: '[TestMaskToggleGuard] 101b-T2（CD-4b）：GhostFly public object 必須 export handoffFocalDetectWait',
  },

  // 101b-T3（§A-5）：_maskStopSettleAnim 對稱停止 helper——T2 只落地了實作，未替它建任何
  // static_guard 規則（改鎖的 :359-365 借走的是 _maskStopWaitAnim 的 anchor）。比照星空
  // 家族（:352 起）「定義存在 + 生命週期端點各自呼叫」的既有形狀補齊。
  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopSettleAnim() {',
    note: '[TestMaskToggleGuard] 101b-T3：收斂補間對稱停止 helper 函式定義存在' },

  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopSettleAnim()',
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T3（CD-10）：_maskDragStart 拖曳接管呼叫 _maskStopSettleAnim' },

  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopSettleAnim()',
    scope: { anchor: /_maskTeardown\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T3（§A-5）：_maskTeardown 防禦性再保險呼叫 _maskStopSettleAnim' },

  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '_maskStopSettleAnim()',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T3（§A-5）：_resetMask 中斷路徑（換片/關燈箱/ESC）呼叫 _maskStopSettleAnim' },

  { file: 'web/templates/_macros/focal_mask.html', kind: 'required-string', pattern: "'lb-mask-window--settling': _maskSettling",
    note: '[TestMaskToggleGuard] 101b-T3（CD-5）：.lb-mask-window :class 綁 --settling guard class' },

  { file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string', pattern: '.lb-mask-window--settling',
    note: '[TestMaskToggleGuard] 101b-T3（CD-5/C21）：--settling class 停用 transition 規則存在' },

  // 101b-T6：修 spinner 靜止不轉——CDP 像素驗證證實根因是 <i class="bi spin"> 預設
  // display:inline（Bootstrap Icons 只把 .bi::before 偽元素設 inline-block），CSS transform
  // 對 non-replaced inline box 不產生視覺效果，animation 確實在跑（computed transform 逐
  // frame 變化）卻視覺靜止——這正是前兩次修法都沒解到、CDP 只量 computed transform 會被騙的
  // 病灶。只鎖 animation 字串仍可能假綠（拿掉 display:inline-block 那行，animation 字串仍在，
  // 但視覺照樣不轉）——兩條都鎖，anchor scope 到 .lb-mask-spinner .bi.spin 規則本體，
  // braceBalanced 防止改到其他規則的同名字串。
  { file: 'web/static/css/pages/showcase/08-remainder.css', kind: 'required-string',
    pattern: ['display: inline-block;', 'animation: spin 1s linear infinite !important;'],
    scope: { anchor: /\.lb-mask-spinner \.bi\.spin\s*\{/, braceBalanced: true },
    note: '[TestMaskSpinnerRotateGuard] 101b-T6：.lb-mask-spinner .bi.spin 真正修復需 display:inline-block（承重，讓 inline icon 變可 transform 的盒子）+ animation !important（蓋過 PRM blanket，owner 訴求「不存在靜態模式」）兩條並存，缺一視覺仍不轉' },

  // ---- Codex 本地 review 修正（Fix A）：_actressPhotoLoaded 不該被 _maskTeardown 清掉 ----
  // 病灶：_maskTeardown 原本會把此旗標設回 false，但 confirmMask/cancelMask → _maskTeardown
  // 之後沒有任何路徑會把它重新判定回真值（URL 未變的已載入 img 不會重觸發 @load）——focal
  // 按鈕的 x-show 因而永久消失，直到關燈箱重開或切換女優才恢復。回歸鎖：禁止在 _maskTeardown
  // 函式體內出現「清掉此旗標」的字面組合；真正該清（且會被 _refreshActressPhotoLoaded 重新
  // 判定）的收尾路徑是 _resetMask，兩者語意不同不可一併刪除。
  // 🔴 100c-T2（CD-5）：pattern 擴成陣列——新增的 _actressPhotoWideEnough 若被「為了對稱」
  // 加進 _maskTeardown()，會讓 Fix A 的病灶重新可達（icon 在 confirm/cancel 後永久消失），
  // 而純字面 '_actressPhotoLoaded = false' 抓不到 '_actressPhotoWideEnough = false' 這個
  // 不同字面（已實證）。同理禁止呼叫 _clearActressPhotoState(（兩旗標同焚的 helper，呼叫
  // 它等同直接寫兩行清除字面，繞過前兩條字面禁令）。evalForbiddenString 原生把 pattern
  // 正規化成陣列逐一檢查（陣列先例：main.js:1214 / state-lightbox.js 等 forbidden-string
  // 規則），語意是「陣列內任一命中即報錯」。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'forbidden-string',
    pattern: ['_actressPhotoLoaded = false', '_actressPhotoWideEnough = false', '_clearActressPhotoState('],
    scope: { anchor: /_maskTeardown\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] Fix A（100c-T2 擴陣列）：_maskTeardown 不可再清 _actressPhotoLoaded / _actressPhotoWideEnough，亦不可呼叫 _clearActressPhotoState()（旗標生命週期屬燈箱照片本身，清在此會讓 focal 按鈕 confirm/cancel 後永久消失、無自我修復路徑；真正該清的收尾是 _resetMask，其後必經 _refreshActressPhotoLoaded 重新判定）',
  },

  // ---- Codex 本地 review 修正（Fix B）：confirmMask 的 actress-sync gate 須讀 await 前捕獲值 ----
  // 病灶：原本 gate 讀 this._maskKind 的即時值——await 期間使用者切走女優 →
  // nextActressLightbox → _setActressLightboxIndex → _resetMask 把 this._maskKind 清空 →
  // gate 誤判成 video 分支，跳過 _syncActressesArray，牆格停在存檔前的裁法。回歸鎖：禁止在
  // confirmMask 函式體內出現讀即時值的字面組合，必須改讀 await 前捕獲的 kind 區域變數
  // （與 _onPickerSelect／_uploadActressPhoto 的 by-captured-name 模式一致）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'forbidden-string',
    pattern: 'this._maskKind ===',
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] Fix B：confirmMask 不可讀 this._maskKind 即時值——await 期間切走女優會被 _resetMask 清空，須改讀 await 前捕獲的 kind（防退回讀即時值造成牆格漏同步）',
  },

  // ---- [TestMaskToggleGuard] 100b-T2b（§B-1f）：上傳女優照片主流程 — wiring + 六個必踩點的機械可鎖部分 ----
  // 女優 wiring 正向鎖：隱藏 file input + accept + 上傳鈕 + handler 綁定，四者缺一即代表
  // 接線斷掉（例如 accept 被砍 → 手機端也能選非圖片檔，spec §3.7-3 失守）。
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'type="file"', note: '[TestMaskToggleGuard] 100b-T2b：隱藏 file input 存在（裁決 6）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'accept="image/*"', note: '[TestMaskToggleGuard] 100b-T2b：file input accept 限定圖片（spec §3.7-3，後端四格式皆收）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'style="display:none"', note: '[TestMaskToggleGuard] 100b-T2b：隱藏 input 用 inline style（裁決 6，避開 .hidden specificity 坑）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '$refs.actressPhotoUploadInput.click()', note: '[TestMaskToggleGuard] 100b-T2b：上傳鈕觸發隱藏 input（$refs，非 $el，G3/坑7 對齊）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@change="_uploadActressPhoto($event)"', note: '[TestMaskToggleGuard] 100b-T2b：file input @change 綁 _uploadActressPhoto' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'class="picker-upload-btn"', note: '[TestMaskToggleGuard] 100b-T2b：.picker-upload-btn 按鈕存在（裁決 5，同 .picker-refresh-btn 排）' },
  { file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string', pattern: 'async _uploadActressPhoto(evt) {', note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 函式定義存在' },

  // 必踩點 #1（mutation 反向驗：拿掉這行 → 必紅）：同一檔案連選兩次 change 不會再觸發，
  // 排在 await（fetch）之前——scope 內若把這行搬到 fetch 之後，本規則仍會通過字面存在性
  // 檢查，但「排序」語意已由函式本體 review + CDP ⓪ 實測把關（lint 只鎖存在性）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: "evt.target.value = '';",
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 必須清空 evt.target.value（同檔重選需要 change 再次觸發，spec §3.1 禁「點了沒反應」）',
  },
  // 必踩點 #6 上半（改資料無條件執行）：_syncActressesArray by-name 呼叫存在。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'this._syncActressesArray(capturedName, data);',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 上傳成功後同步 _syncActressesArray（stale-success #6 上半，改資料無條件做）',
  },
  // §B-2b 第三呼叫點：上傳成功後刷新 _actressPhotoLoaded（新圖需重新等載入/快取判定）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'this._refreshActressPhotoLoaded();',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 成功且仍是同一位女優時呼叫 _refreshActressPhotoLoaded（§B-2b 第三呼叫點）',
  },
  // CD-9：錯誤分流依 HTTP status，不依 body code；無 409。鎖 413/415 兩個字面分支存在，
  // 證明「依 status 分流」這個決策點沒被改寫成單一籠統 catch。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'resp.status === 413',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：CD-9 413→upload_too_large 分支存在',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'resp.status === 415',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：CD-9 415→upload_bad_format 分支存在',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'forbidden-string', pattern: 'resp.status === 409',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：CD-9 明訂上傳無 409（v3 砍了 compare token），不得復活',
  },
  // 必踩點 #3（mutation 反向驗：把這行改成 this._closePicker() → 必紅）：失敗分支刻意
  // 與既有候選換圖的 catch（_onPickerSelect 呼叫 _closePicker()）分歧，不可關 picker。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'forbidden-string', pattern: 'this._closePicker();',
    scope: { anchor: /if\s*\(!resp\.ok\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 失敗分支（!resp.ok）不得關 picker（spec §3.1+§C 刻意分歧，非漏改）',
  },
  // [TestPickerLeakGuard] 101b-T4：影片/搜尋模式下經 hero-card 開啟女優燈箱、開了換照片
  // picker 卻不關、直接按左右箭頭切片這條路徑上 _pickerOpen 永遠停在 true 的洩漏（spec
  // §4.6／plan-101b §C／CD-13）。排序而非旗標：兩函式開頭關閉殘留 picker，讓壞狀態不可能。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'if (this._pickerOpen) this._closePicker();',
    scope: { anchor: /prevLightboxVideo\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestPickerLeakGuard] 101b-T4：prevLightboxVideo 開頭關閉殘留 picker（spec §4.6，排序而非旗標）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'if (this._pickerOpen) this._closePicker();',
    scope: { anchor: /nextLightboxVideo\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestPickerLeakGuard] 101b-T4：nextLightboxVideo 開頭關閉殘留 picker（spec §4.6，排序而非旗標）',
  },
  // spec §3.7-7「零偵測成本」：上傳流程全程不得呼叫 detect-focal（by-construction，本
  // 規則把它機械鎖住——「不做某事」測試鎖不到，只有守衛鎖得到）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'forbidden-string', pattern: 'detect-focal',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：spec §3.7-7 零偵測成本——_uploadActressPhoto scope 內不得出現 detect-focal',
  },
  // 🔴 CD-10 訂正（Opus 2026-07-16 裁決，CDP 實測背書）：上傳成功後**必須**顯式同步
  // currentLightboxActress.photo_url，否則燈箱主圖不會換。CD-10 原主張「currentLightboxActress
  // 與 paginatedActresses[idx] 是同一個物件 ⇒ _syncActressesArray 改一邊即改兩邊 ⇒ 顯式同步是
  // 冗餘」——但 _fetchLiveAliases（state-actress.js:791）的 Object.assign 在開燈箱後 +17ms 就把
  // currentLightboxActress 換成脫鉤副本（CDP 實測），該前提實務上恆不成立。
  // ⚠️ 這條鎖的價值在於「間歇性」：alias 回 404 的女優（實測 21 位中 18 位）前提僥倖成立、
  // 拿掉本行也照樣正常；只有 alias 回 200 的 3 位會壞 ⇒ 人工抽測與 CDP 抽樣都可能整批放行。
  // 資料相依的間歇失敗只有守衛鎖得到。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'this.currentLightboxActress.photo_url = data.photo_url;',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 成功後顯式同步 currentLightboxActress.photo_url（CD-10 訂正：_fetchLiveAliases 的 Object.assign 讓「同物件」前提失效，缺此行燈箱主圖不換）',
  },
  // §B-2b 第四呼叫點（Opus 2026-07-16 裁決）：換候選成功換 URL 後亦須刷新，與上傳同形。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'this._refreshActressPhotoLoaded();',
    scope: { anchor: /async\s+_onPickerSelect\s*\(\s*candidate\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_onPickerSelect 換候選成功後呼叫 _refreshActressPhotoLoaded（§B-2b 第四呼叫點，photo_url 一變就要重新等載入）',
  },
  // 🔴 §B-2b lifecycle 契約的「未快取路徑」唯一 writer。100c-T2（CD-5）：_actressPhotoLoaded
  // 與 _actressPhotoWideEnough 兩旗標的完整生命週期收成兩個 helper（_clearActressPhotoState/
  // _readyActressPhotoState），有且只有兩個地方能設值：$nextTick complete-check（已快取
  // 路徑，呼叫 _readyActressPhotoState）與本 @load（未快取路徑）。上傳/換候選回的是
  // cache-bust URL（?v={mtime_ns}-{size}，必然 cache miss）⇒ 拿掉本行，focal 按鈕在上傳
  // 成功後永久消失（x-show 綁 _actressPhotoLoaded/_actressPhotoWideEnough，且無任何錯誤
  // 訊息）＝典型「全綠但功能不可用」（feedback_guards_cant_prove_usable）。鏡射 video 側
  // :733 的同型寫入點。CDP 另有未快取路徑的真機驗收（守衛只證「寫入點存在」，證不出
  // 「圖載完旗標真的翻」）。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '@load="_readyActressPhotoState($el)"',
    note: '[TestMaskToggleGuard] 100c-T2：女優封面 img 的 @load 是兩旗標在未快取路徑（上傳/換候選的 cache-bust URL）的唯一 writer',
  },

  // ---- [TestMaskToggleGuard] 100b-T4：狀態同步 + 前端序列化 ----

  // 裁決 1（Opus 審核，2026-07-16）：confirmMask 女優分支必須補上 paginatedActresses[idx]
  // 陣列側寫入，與 _uploadActressPhoto／_onPickerSelect 對稱（改資料一律 by-name 呼叫
  // _syncActressesArray）。alias 回 200 的女優（21 位中 3 位）缺此行 ⇒ 牆上小格存檔後不會
  // 立即生效（違反 spec §3.4 末條），且是資料相依的間歇失敗（alias 回 404 的 18 位僥倖正常）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "this._syncActressesArray(targetObj.name, { auto_focal: data.auto_focal, crop_mode: 'manual' });",
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：confirmMask 女優分支補上 paginatedActresses[idx] 陣列側寫入（Opus 裁決 1）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: "if (kind === 'actress') {",
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4／Fix C 修正：confirmMask 陣列側寫入須 gate 在 kind===actress（video 分支沒有 paginatedActresses 可查，兩者是正交資料，不得誤觸發）——Fix B 把即時值 this._maskKind 改為 await 前捕獲的 kind 區域變數，pattern 同步更新',
  },
  // 🔴 防止已被推翻的錯誤前提復活：舊註解主張 actress 分支的 targetObj 與
  // paginatedActresses[idx] 恆為同一物件參考（本 branch 稱其為「CD-10 同物件參考」）——
  // 已被 CDP 實測推翻三次，本 branch 已為它付出代價（錯的理由比沒有理由更危險）。
  // 全檔禁止再出現這句字面舊註解。
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string',
    pattern: 'CD-10 同物件參考',
    note: '[TestMaskToggleGuard] 100b-T4：禁止復活已被 CDP 實測推翻的舊註解（currentLightboxActress 與 paginatedActresses[idx] 不保證同一物件，見 plan-100b.md CD-10 訂正框）（149a：五個分片同禁）',
  })),

  // 裁決 4-b／G2：.picker-upload-btn 互斥鎖必須 !! 強制 boolean（fresh session 下
  // _pickerSelected 若為 undefined，裸讀會讓按鈕一開始就不可點，且靜態分析全過）。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ':disabled="!!_pickerSelected"',
    note: '[TestMaskToggleGuard] 100b-T4：.picker-upload-btn 互斥鎖 G2 !! coercion（CD-8／裁決 4-b）',
  },

  // 裁決 5：.picker-candidate-card 是 <div>，HTML `disabled` 只對 form control 生效，
  // 掛在 div 上會被瀏覽器靜默忽略（看起來鎖了、其實沒鎖）。互斥改走既有 @click guard
  // （_onPickerHoverIn／_onPickerHoverOut／_onPickerSelect 三者開頭皆
  // `if (this._pickerSelected) return;`，49c-era 既有碼，先前無 lint 鎖住不被回歸刪除）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'if (this._pickerSelected) return;',
    scope: { anchor: /_onPickerHoverIn\s*\(\s*el\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：_onPickerHoverIn 互斥 guard 回歸鎖（裁決 5——.picker-candidate-card 是 div，:disabled 無效，改走此 @click guard）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'if (this._pickerSelected) return;',
    scope: { anchor: /async\s+_onPickerHoverOut\s*\(\s*el\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：_onPickerHoverOut 互斥 guard 回歸鎖（裁決 5，同上）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'if (this._pickerSelected) return;',
    scope: { anchor: /async\s+_onPickerSelect\s*\(\s*candidate\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：_onPickerSelect 互斥 guard 回歸鎖（裁決 5，同上——AC-13 race lock 兼任兩角色：候選列互斥 + 原有的重複點擊防護）',
  },

  // 100b Codex P2-3 fix：openActressPicker() 唯一入口加互斥 guard——.picker-refresh-btn
  // （showcase.html）原本只用 :disabled="_pickerLoading" 擋，burst 完成後 loading=false
  // 但上傳/換候選正在等 fetch resolve（_pickerSelected=true）的視窗內仍可點，CDP 實測
  // 2026-07-16 重現：點擊後 _resetPicker() 把正在等待的 fetch 變孤兒 callback，與新一輪
  // SSE 競爭，原 fetch resolve 時的 _closePicker() 會把使用者剛開的新 picker session 一併
  // 關掉。guard 加在函式入口（覆蓋兩個既有 callsite），沿用既有 _onPickerHoverIn／
  // _onPickerHoverOut／_onPickerSelect 同款 early-return 慣例。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'if (this._pickerSelected) return;',
    scope: { anchor: /async\s+openActressPicker\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b P2-3 fix：openActressPicker 互斥 guard 回歸鎖（.picker-refresh-btn 在上傳/換候選 in-flight 期間再次觸發會與原 fetch 競爭關閉 picker，CDP 2026-07-16 實測重現）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ':disabled="_pickerLoading || !!_pickerSelected"',
    note: '[TestMaskToggleGuard] 100b P2-3 fix：.picker-refresh-btn 互斥鎖含 _pickerSelected（比照 .picker-upload-btn 的 G2 !! coercion 慣例），UI 側呈現不可點狀態，非唯一防線（見同檔 openActressPicker 函式層 guard）',
  },

  // 裁決 4-c／CD-8 承重前提：上傳 in-flight 期間 _pickerOpen 恆為 true，_closePicker() 必須
  // 排在 await fetch 之後（picker 一關，.cover-actions 復活、🗑️ 可達，CD-8「不鎖刪除鈕」的
  // 論證即失效）。本規則只證字面順序，證不出執行時序（catch/提早 return 是否遵守）——
  // 最終把關仍是 CDP 實測 .cover-actions 的 pointer-events（DoD④-c）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'order',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    items: [
      { pattern: /await\s+fetch\(/ },
      { pattern: /this\._closePicker\(\)/ },
    ],
    note: '[TestMaskToggleGuard] 100b-T4：CD-8 承重前提——_closePicker() 必須排在 await fetch 之後（picker 在請求 resolve 前不得關閉，否則 .cover-actions 復活、🗑️ 可達）',
  },

  // §A／CD-6：女優牆格三件套（@load + 兩條 $watch），比照 video 牆格 :330-333，ratioVar
  // 傳 --actress-crop-ratio（CD-3）。count:3 涵蓋 @load 呼叫本身 + 兩個 $watch callback 內
  // 各自呼叫一次，缺一即代表接線不全（例如漏改成不帶 ratioVar 的 2-arg 呼叫，會誤用
  // 預設 --poster-crop-ratio）。
  // 100c-T3b：砍 axisMode 後三處呼叫收斂為 3-arg，pattern 錨完整引數列（比照 :2997-3003
  // 「錨完整 @load 值」慣例）——只認到 '--actress-crop-ratio' 這一段會被誤刪掉 ratioVar 的
  // 2-arg 呼叫（退回吃預設 --poster-crop-ratio，女優小格誤用影片比例）假綠放行。
  {
    file: 'web/templates/showcase.html', kind: 'required-string', count: 3,
    pattern: "applyCellFocal($el, actress, '--actress-crop-ratio')",
    note: '[TestMaskToggleGuard] 100c-T3b：女優牆格 @load + 兩條 $watch 三件套皆傳 --actress-crop-ratio（CD-3，比照 video 三件套；錨完整引數列防 ratioVar 被砍掉假綠。axisMode 已於 100c-T3b 隨 Y 軸一起收斂移除）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: "$watch('actress.auto_focal',",
    note: '[TestMaskToggleGuard] 100b-T4：女優牆格 x-init watcher 鎖 auto_focal（DoD①：✓ 存入後小格立即對準臉，不需重載）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: "$watch('actress.crop_mode',",
    note: '[TestMaskToggleGuard] 100b-T4：女優牆格 x-init watcher 鎖 crop_mode（DoD②-a：換照片後回置中裁）',
  },

  // ---- [TestMaskToggleGuard] 100b-T5：收尾守衛（CD-5，§D）----

  // T2a 裁決 3 留給本 task：既有 4 條 _computeMaskWinStyle scope rule（getComputedStyle
  // required／--poster-crop-ratio required／0.71 forbidden／2/3 forbidden，:151-180）只鎖住
  // 影片那一半的字面字串。--actress-crop-ratio 的正向鎖原本不存在——若有人把三元式的 actress
  // 分支砍掉（例如「清理」成恆讀 --poster-crop-ratio），既有 4 條規則全數維持綠燈（它們只驗
  // --poster-crop-ratio 存在／0.71 不存在，證不出 actress 分支還在），女優遮罩會在 T2a 已修好
  // 的地方靜默退化回 NaN 幾何。鏡射既有 :157-160 required 規則，同一 anchor、同一 scope。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string', pattern: '--actress-crop-ratio',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T5：_computeMaskWinStyle 讀 --actress-crop-ratio（CD-3 正向鎖，鏡射既有 --poster-crop-ratio required）',
  },

  // §A／101c-T1：女優裁窗比例雙真理 parity 守衛（cross-file-equal，第 10 個 kind）。
  // 後端 _FOCAL_DETECT_RATIO(actress.py) 與前端 --actress-crop-ratio(theme.css) 是兩份獨立真理、
  // 無任何機制強制同步（兩處註解皆自承）。改一邊漏改另一邊 → 後端依新 ratio 判主軸可能回 Y 軸、
  // 前端仍鎖 X 軸拖曳 → 靜默錯框。此守衛鎖「一致」（CD-4：不寫死 0.75，同步改綠、單改一邊紅）。
  // 🔴 pattern 錨死完整 --actress-crop-ratio:，不可寬鬆匹配到相鄰的 --poster-crop-ratio:0.71（theme.css:561）。
  {
    kind: 'cross-file-equal',
    label: 'actress-crop-ratio parity',
    // 🔴 數值 pattern 擷取完整數值 literal（含科學記號 0.75e-1），並以行首/行尾錨定實際
    // assignment（m flag），否則 `[0-9.]+` 只抓 e 之前的前綴：後端改成合法值 0.75e-1(=0.075)、
    // 前端維持 0.75，兩邊都截在 e、都擷到 "0.75" → 假性相等放行（Codex P2）。CSS 端 `;` 前不許
    // 單位後綴（0.75rem 之類）造成假綠——不匹配即 fail-closed 轉紅（安全方向）。
    sources: [
      { file: 'web/routers/actress.py',   pattern: /^_FOCAL_DETECT_RATIO\s*=\s*([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)\s*(?:#.*)?$/m },
      { file: 'web/static/css/theme.css', pattern: /^\s*--actress-crop-ratio:\s*([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)\s*;/m },
    ],
    note: '[TestRatioParityGuard] spec-101 §5.1：女優裁窗比例後端(_FOCAL_DETECT_RATIO)與前端(--actress-crop-ratio)雙真理，無強制同步機制，此守衛鎖一致（CD-4：鎖一致非鎖 0.75）',
  },

  // CD-1：女優不得裸讀 --poster-crop-ratio、不得在 state-actress.js 內另起一套 _mask* 平行實作
  // （走同一組 _mask* 函式 + axis 參數，不複製）。全檔掃描，不需 scope——state-actress.js 今天
  // 對兩者皆零出現（已查），本規則純屬回歸鎖，防未來有人「順手」在這裡加女優專用的遮罩/比例邏輯。
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string', pattern: '--poster-crop-ratio',
    note: '[TestMaskToggleGuard] 100b-T5：CD-1／CD-3——state-actress.js 不得裸讀 --poster-crop-ratio（女優比例走 _maskTarget()/computeAndApply 既有 dispatch，不得繞過）',
  },
  {
    // 🔴 本規則為何不誤中 state-actress.js 既有的 `this._resetMask()` / `this._refreshActressPhotoLoaded()`
    // ——精確機制（別寫成「因為大寫 M」或「因為沒底線前綴」，那兩種說法都不準）：
    //   pattern `_mask` 是 **case-sensitive 子字串**比對，要求「底線**緊接**小寫 m」。
    //   `_resetMask` 拆開是 `_` + `reset` + `Mask` → 唯一的底線後面接的是 `r`；
    //   `_refreshActressPhotoLoaded` 同理（底線後接 `r`）。**兩者都有底線前綴，只是底線後不是 m。**
    //   ⇒ 命中的只會是 `_maskAxis` / `_maskFocalX` / `_maskKind` 這種 `_mask*` 識別字家族**本身**
    //   被定義或參照——那正是 CD-1 要擋的「平行實作」訊號。
    // ⚠️ 邊界很窄：若日後有人在本檔寫 `this._maskVisible` 之類的**讀取**（非平行實作），也會紅。
    //   那是刻意的 fail-closed——女優的遮罩狀態一律走 state-lightbox.js 的共用 `_mask*`，
    //   state-actress.js 不該直接碰它們（CD-1：不複製到 state-actress.js）。
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string', pattern: '_mask',
    note: '[TestMaskToggleGuard] 100b-T5：CD-1——state-actress.js 不得出現 _mask* 平行實作或直接碰 _mask* 狀態（呼叫 this._resetMask() 這類共用方法不受影響：底線後接 r 非 m，見上方註解的精確機制）',
  },

  // v3 已砍 compare token 機制（CD-9：無 409），_maskExpectedFp 是 v2 殘留識別字，全檔零出現
  // （已查）。防它以「還原相容性」之類理由復活——一旦復活即代表有人試圖繞過 CD-9 的三桶錯誤
  // 分流，重新做回 fingerprint-based CAS。
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string', pattern: '_maskExpectedFp',
    note: '[TestMaskToggleGuard] 100b-T5：v2 殘留識別字 _maskExpectedFp 不得復活（v3 無 token，CD-9/§B-1b 明訂）（149a：五個分片同禁）',
  })),

  // spec §3.7-7「零偵測成本」：_uploadActressPhoto 已有同型規則（100b-T2b，:457-459）；
  // _onPickerSelect（換候選）是另一個不該觸發偵測的入口，同一責任、同一 scope 寫法，
  // T2b 當時刻意留給本 task（TASK-100b-T2.md 裁決 3）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'forbidden-string', pattern: 'detect-focal',
    scope: { anchor: /async\s+_onPickerSelect\s*\(\s*candidate\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T5：spec §3.7-7 零偵測成本——_onPickerSelect scope 內不得出現 detect-focal',
  },

  {
    // 100c-T3a：軸向 modifier 已移除（CD-6：唯一可拖方向恆為橫向），cursor: ew-resize 契約
    // 搬進 .lb-mask-window 基礎規則——scope-anchored（非裸 required-string）：本檔附近仍可能
    // 有規劃註解字面提到「ew-resize」，裸的 required-string 會被那類註解假綠掉（本 branch
    // 已踩過三次的 fail-open 形狀）。錨定實際 CSS rule block，只在該 block 內斷言。
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string', pattern: 'ew-resize',
    scope: { anchor: /\.lb-mask-window\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T3a：.lb-mask-window 基礎規則的 cursor: ew-resize（Y 軸砍除後唯一可拖方向併回基礎規則，取代舊 grab；scope 錨定防同檔規劃註解假綠）',
  },

  // ---- [TestMaskToggleGuard] 100c-T3a：CD-11 Y 軸/軸向判定/凍結模式不得復活 ----
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string',
    pattern: ['this._maskFocalY', 'this._maskAxis', 'this._maskFrozen', 'computeMaskAxis('],
    note: '[TestMaskToggleGuard] 100c-T3a／CD-11：Y 軸/軸向判定/凍結模式不得復活（spec-100c §3.3 廢止）——鎖程式碼形式（this. 前綴/呼叫括號），散文註解仍可提及裸名（149a：五個分片同禁）',
  })),
  {
    file: 'web/static/js/shared/mask-geometry.js', kind: 'forbidden-string',
    pattern: ['translateY', 'computeMaskAxis'],
    note: '[TestMaskToggleGuard] 100c-T3a／CD-11：Y 軸 transform 輸出與軸向判定函式不得復活（spec-100c §3.3）——加入本規則前已改寫 file header 與 computeMaskDragRoom JSDoc 中提及被刪函式的文字，避免規則自我毒殺',
  },

  // ---- [TestMaskToggleGuard] 100c-T3b：CD-11 focalCellObjectPosition 的 Y 軸輸出字面不得復活 ----
  // 鎖輸出而非 axisMode 參數：100b-T3 的原始事故是「自判軸向、不加參數」，鎖參數擋不住這個
  // 復活形狀；docstring 純文字描述輸出格式不含此 template literal 語法，不會誤中（加規則前已
  // grep -c '`center ${' focal.js = 0，核實不假紅）。
  {
    file: 'web/static/js/shared/focal.js', kind: 'forbidden-string',
    pattern: '`center ${',
    note: '[TestMaskToggleGuard] 100c-T3b／CD-11：focalCellObjectPosition 的 Y 軸 object-position 輸出字面不得復活（spec-100c §3.3）——鎖輸出而非 axisMode 參數：100b-T3 的原始事故是「自判軸向、不加參數」，鎖參數擋不住這個復活形狀；docstring 純文字描述輸出格式不含此 template literal 語法，不會誤中',
  },

  // ---- [TestMaskToggleGuard] 100c-T2：女優 focal icon 搬家 + 五條件顯示邏輯 + 20% 門檻接線 ----
  // CD-8：全庫零守衛在看這顆鈕（實查——:97 的 @click="openMask 規則無 scope/count，兩分支各一
  // 顆鈕都能滿足它，未錨定女優鈕的 DOM 位置/class/x-show 條件）。本節新增機械可檢部分；
  // icon 到底出不出現／tooltip 是否真的浮現／picker 開啟時是否真的按不到——這些行為性質
  // lint 語法表達不了，唯一手段是 CDP（見 TASK-100c-T2.md DoD 3）。
  //
  // 🔴 五條件收成 _focalIconVisible() method（不直接寫成 x-show 的 && 字面鏈）：JS `&&`
  // 短路求值下，一旦前段條件為 false，後段條件不會被讀取，Alpine 的 effect 依賴收集因此
  // 漏訂閱鏈末條件（見 showcase.html 按鈕上方註解 + _focalIconVisible() 定義處完整說明）。
  // method 內用獨立陳述式無條件讀完全部 5 個旗標再組合，保證每次求值都完整訂閱依賴——
  // showcase.html 仍用 x-show 綁定本 method（與影片版一致）。
  // x-show 綁定點（scope 錨 .actress-lb-header，鎖最終形＝method + x-show）：
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="_focalIconVisible()"',
    scope: { anchor: /<div class="actress-lb-header">/, window: 3200 },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1/CD-8）：女優 focal icon x-show 綁定 _focalIconVisible()（五條件收成 method 避開 && 短路漏訂閱），不得寫回裸 && 字面鏈',
  },
  // method 本體：五個「無條件讀取」陳述式 + 完整 return 組合（CD-1 五條件，逐一獨立 required
  // ⇒ card DoD 1 的「拿掉每條條件」逐一對應到這 6 條規則其中之一單獨紅，比原本單一大字面
  // required-string 更精準——任何一條被拿掉都直接對應到它自己的守衛，不會混在一起判讀）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'const notEditing = !this._maskVisible;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件① !_maskVisible 無條件讀取',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'const hasPhoto = !!this.currentLightboxActress?.photo_url;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件② photo_url 無條件讀取',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'const loaded = this._actressPhotoLoaded;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件③ _actressPhotoLoaded 無條件讀取',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'const wideEnough = this._actressPhotoWideEnough;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1/CD-7）：_focalIconVisible 條件④ _actressPhotoWideEnough 無條件讀取（20% 門檻）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'const pickerClosed = !this._pickerOpen;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件⑤ !_pickerOpen 無條件讀取（picker 開啟保護，搬出 .cover-actions 後 CSS gate 不再涵蓋，必須顯式擋）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'return notEditing && hasPhoto && loaded && wideEnough && pickerClosed;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 完整五條件組合（錨完整 return 字面，防片段假綠）',
  },
  // DOM 位置：icon 必須在 .actress-lb-header 內（搬遷目的地），不得殘留在 .cover-actions。
  // scope-anchor 到 .actress-lb-header 的 brace-balanced 視窗內斷言 class/click/title 三個
  // 屬性同時存在——三者同 scope 命中即代表「搬對地方了」，任一個字面單獨存在別處都不會通過。
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'class="lb-mask-btn"',
    scope: { anchor: /<div class="actress-lb-header">/, window: 3200 },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1/CD-8）：.lb-mask-btn 必須在 .actress-lb-header 視窗內（DOM 位置鎖，防搬回 .cover-actions）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: 'class="lb-action-btn"\n                                        x-show="!_maskVisible && !!currentLightboxActress?.photo_url',
    note: '[TestMaskToggleGuard] 100c-T2（CD-2）：女優 focal icon 不得沿用舊 .lb-action-btn class + 舊三條件 x-show 組合（回歸鎖：防搬遷被 revert 回 .cover-actions 內的舊寫法）',
  },
  // CD-2：:title=（非 :data-tooltip=）——.lb-action-btn[data-tooltip]::after 只認 .lb-action-btn，
  // 换 class 不換屬性會讓 tooltip 靜默消失（零 lint 可抓「CSS 規則沒被觸發」，只能鎖屬性字面本身）。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ':title="t(\'showcase.lightbox.mask_toggle\')"\n                                        :aria-label="t(\'showcase.lightbox.mask_toggle\')">\n                                    <i class="bi bi-person-bounding-box"></i>',
    scope: { anchor: /<div class="actress-lb-header">/, window: 3200 },
    note: '[TestMaskToggleGuard] 100c-T2（CD-2）：女優 focal icon 用原生 :title=（非 :data-tooltip=），鏡射影片版 .lb-mask-btn（:849）',
  },

  // 兩個 helper 的呼叫點接線鎖（CD-5）。改用 scope-anchored required-string 精確鎖各呼叫點，
  // 不用 count：required-string 的 count 是**下限**（n < count → 紅），抓不到「多加一個非法
  // 呼叫者」，且純字面 count 會被註解子字串一起命中而虛增 → 假綠。真正的「唯一 writer」保護
  // 靠設計本身（只有 helper 寫旗標）＋ Fix A forbidden 擋 _maskTeardown，已足夠；此處只需
  // 正向鎖「該接的呼叫點都在」，不需反向鎖「別處不准呼叫」（那是 over-engineering）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: 'this._clearActressPhotoState()',
    scope: { anchor: /_refreshActressPhotoLoaded\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-5）：_refreshActressPhotoLoaded() 起手呼叫 _clearActressPhotoState()（切換/開啟女優先清兩旗標）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: 'this._clearActressPhotoState()',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-5）：_resetMask() 呼叫 _clearActressPhotoState()（換片/關燈箱清兩旗標，其後必經 _refreshActressPhotoLoaded 重新判定）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox-picker.js', kind: 'required-string',
    pattern: '_readyActressPhotoState(',
    scope: { anchor: /_refreshActressPhotoLoaded\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-5）：_refreshActressPhotoLoaded() 的 $nextTick 內呼叫 _readyActressPhotoState()（已快取路徑；未快取路徑那次由 showcase.html @load required 規則鎖）',
  },

  // ---- [TestSearchLightboxMetadataGuard] search.html：5 個 required ----
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'currentLightboxVideo()?.director', note: '[TestSearchLightboxMetadataGuard] lightbox field' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'currentLightboxVideo()?.duration', note: '[TestSearchLightboxMetadataGuard] lightbox field' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'currentLightboxVideo()?.series', note: '[TestSearchLightboxMetadataGuard] lightbox field' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'currentLightboxVideo()?.label', note: '[TestSearchLightboxMetadataGuard] lightbox field' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'lb-details', note: '[TestSearchLightboxMetadataGuard] lightbox field' },

  // ---- [TestShowcaseHeroCard] required 半邊 + forbidden（同批簡單字串）+ animations.js required ----
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'hero-card', note: '[TestShowcaseHeroCard] hero card structure' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "t('common.no_image')", note: '[TestShowcaseHeroCard] hero card structure' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "searchFromMetadata(actress.trim(), 'actress')", note: '[TestShowcaseHeroCard] hero card structure' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: '<span>No Image</span>', note: '[TestShowcaseHeroCard] retired no-image markup' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'playHeroCardAppear', note: '[TestShowcaseHeroCard] animations.js' },

  // ---- [TestNoVanillaHandlers] web/templates/*.html（非遞迴，天然排除 design_system/） ----
  {
    file: { dir: 'web/templates', ext: ['.html'] },
    kind: 'forbidden-string',
    pattern: /(?<=\s)on(?:click|change|submit|keydown|input)\s*=\s*["']/i,
    note: '[TestNoVanillaHandlers] no inline vanilla event handler',
  },

  // ---- [TestActressIconGuard] ----
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: /class="bi bi-person(?!-circle|-heart)"/,
    note: '[TestActressIconGuard] showcase.html bi-person (non circle/heart)',
  },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'bi-person-badge', note: '[TestActressIconGuard] scanner.html bi-person-badge' },

  // ---- [TestSwitchSourceBtnRemoved] ----
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'id="switchSourceBtn"', note: '[TestSwitchSourceBtnRemoved] switchSourceBtn id gone' },
  // 🔴 window 實測與定值理由（Opus 2026-09-03，141b-T7）：
  //   區塊 anchor→閉合 </div> = 7268；下一個兄弟 .sample-gallery 起點 = 7326；
  //   該兄弟區域內第一個 bi-* 圖示 = 7802（bi-x-lg）。
  //   取 7500：給書籤燈箱尾端約 230 字元餘裕，同時離 7802 還有 300 字元。
  // ⚠️ **不要把窗貼齊區塊邊界**。forbidden-string 要擋的正是「有人在區塊尾端加了不該有的東西」，
  //   而新加的內容會把區塊撐長——窗貼齊邊界時，新加的字面立刻落在窗外，守衛靜默失效。
  //   （實測：貼齊到 7275 時，在尾端種 bi-play-fill 落在 7276-7288，一個字元之差就抓不到。）
  //   上限由「兄弟元素裡第一個合法的同類字面」決定，不是由區塊邊界決定。
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-arrow-repeat',
    scope: /<div class="av-card-full-header">([\s\S]*?)<\/div>\s*<div class="av-card-full-(?:title|body)">/,
    note: '[TestSwitchSourceBtnRemoved] bi-arrow-repeat gone from .av-card-full-header scope',
  },

  // ---- [TestSearchSubmitBtnNoLongPress]（scoped forbidden ×4） ----
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressStart', scope: /<button\b[^>]*\bid="btnSubmit"[^>]*>/, note: '[TestSearchSubmitBtnNoLongPress] #btnSubmit tag no long-press' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressEnd', scope: /<button\b[^>]*\bid="btnSubmit"[^>]*>/, note: '[TestSearchSubmitBtnNoLongPress] #btnSubmit tag no long-press' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressCancel', scope: /<button\b[^>]*\bid="btnSubmit"[^>]*>/, note: '[TestSearchSubmitBtnNoLongPress] #btnSubmit tag no long-press' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressClickGuard', scope: /<button\b[^>]*\bid="btnSubmit"[^>]*>/, note: '[TestSearchSubmitBtnNoLongPress] #btnSubmit tag no long-press' },

  // ---- [T8-LoadMoreListModeSearchGuard]（TASK-158-T8，遷移自 wishlist-state.test.mjs
  // 舊 node:test「search.html Load More 按鈕 x-show 含 listMode === 'search'」，CD-158-4③
  // 更正錨點：這段 x-show 掛在外層 <div class="text-center py-4">，不是 <button>——scope
  // 用 lookahead 錨定同一個 <div> 的 x-show 值以 hasMoreResults 開頭（全檔唯一 token），
  // 與 :3023 TestOutputPathVisibilityGuard 同一種「錨定 x-show 值」寫法，不比對整個 class
  // 屬性，故不受屬性順序影響（FE-GUARD-17 雙向驗收：合法重排仍綠）----
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: "listMode === 'search'",
    scope: /<div\b(?=[^>]*\sx-show="hasMoreResults[^"]*")[^>]*>/,
    note: "[T8-LoadMoreListModeSearchGuard] Load More <div> 的 x-show 需含 listMode === 'search'（scope 錨定 hasMoreResults token，CD-158-4③）",
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: "displayMode === 'grid'",
    scope: /<div\b(?=[^>]*\sx-show="hasMoreResults[^"]*")[^>]*>/,
    note: "[T8-LoadMoreGridOnlyGuard] Load More <div> 的 x-show 需含 displayMode === 'grid'（清單／詳細模式不該出現封面牆的載入更多）",
  },

  // ---- [TestUS1IdPreserved] ----
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'id="resultActors"', note: '[TestUS1IdPreserved] result id preserved' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'id="resultDate"', note: '[TestUS1IdPreserved] result id preserved' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'id="resultMaker"', note: '[TestUS1IdPreserved] result id preserved' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'id="resultTags"', note: '[TestUS1IdPreserved] result id preserved' },

  // ---- [TestUS1FooterClassRemoved]（forbidden wrapper + required 子 class，互補） ----
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'class="av-card-full-footer"', note: '[TestUS1FooterClassRemoved] wrapper renamed, must not remain' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'class="av-card-full-footer-content"', note: '[TestUS1FooterClassRemoved] child class must survive (not over-deleted)' },

  // ---- [TestDesignSystemLongPressCard]（3 個 forbidden） ----
  { file: 'web/templates/design_system/settings-components.html', kind: 'forbidden-string', pattern: 'D.14', note: '[TestDesignSystemLongPressCard] D.14 long-press demo card retired' },
  { file: 'web/templates/design_system/settings-components.html', kind: 'forbidden-string', pattern: 'longPressStart', note: '[TestDesignSystemLongPressCard] D.14 long-press demo card retired' },
  { file: 'web/templates/design_system/settings-components.html', kind: 'forbidden-string', pattern: 'long-press.js', note: '[TestDesignSystemLongPressCard] D.14 long-press demo card retired' },

  // ---- [118a-T7] BETA 徽章反向鎖（spec F3，owner 2026-08-14 拍板移除，不換文案） ----
  // 這不是把舊守衛換個地方守——舊的 test_modal_builtin_pill_has_beta_badge 鎖的是「徽章必須存在」，
  // 元件整個移除後那個不變式被**反轉**了。這裡鎖的是回歸：BETA 不得重新長回任何一個渲染點。
  // 使用者後果（若回歸）：兩支能用的來源又被標成「這功能還沒做好」，而它們只是偶爾要過一次驗證。
  // `.source-pill-mt-badge`（metatube 的 m 角標）是不同 class，不受這些規則影響。
  { file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: 'source-pill-badge', note: '[118a-T7] BETA badge removed (spec F3); AC-3.2 now carried by aria-disabled + title + toast' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'source-pill-badge', note: '[118a-T7] BETA badge removed (spec F3)' },
  { file: 'web/templates/_macros/source_pill.html', kind: 'forbidden-string', pattern: 'beta_badge', note: '[118a-T7] dead macro param removed (no caller ever passed it)' },
  { file: 'web/templates/design_system/settings-components.html', kind: 'forbidden-string', pattern: 'source-pill-badge', note: '[118a-T7] BETA badge demo retired with the component' },
  { file: 'web/static/css/components/source-pill.css', kind: 'forbidden-string', pattern: '.source-pill-badge', note: '[118a-T7] component deleted; re-add only with a real use case' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'manual_only_badge', note: '[118a-T7] i18n key deleted from all 4 locales' },

  // ---- [TestGridSettlePulse]（只港 flat required 半邊，method-body window 半邊留 T2） ----
  { file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'playGridSettle', note: '[TestGridSettlePulse] animations.js flat required (method-body window half deferred to T2)' },
  { file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'CustomEase.create("settle"', note: '[TestGridSettlePulse] animations.js flat required (method-body window half deferred to T2)' },

  // ---- [TestFetchAbortController]（純 flat required，含 count-based） ----
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_abortControllers: {}', note: '[TestFetchAbortController] base.js abort state' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_getAbortSignal(', note: '[TestFetchAbortController] search-flow.js abort methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_abortAllFetches(', note: '[TestFetchAbortController] search-flow.js abort methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_abortAllFetches()', note: '[TestFetchAbortController] search-flow.js abort methods' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: "_getAbortSignal('loadMore')", note: '[TestFetchAbortController] navigation.js signal usage' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: 'AbortError', note: '[TestFetchAbortController] navigation.js AbortError handling' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string', pattern: "_getAbortSignal('translateAll')", note: '[TestFetchAbortController] batch.js signal usage' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string', pattern: 'AbortError', note: '[TestFetchAbortController] batch.js AbortError handling' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string', pattern: "_getAbortSignal('setFileList')", note: '[TestFetchAbortController] file-list.js signal usage' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string', pattern: "_getAbortSignal('loadFavorite')", note: '[TestFetchAbortController] file-list.js signal usage' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string', pattern: 'AbortError', count: 2, note: '[TestFetchAbortController] file-list.js AbortError x2 (count-based, precise)' },

  // ---- [TestTimerTracking]（只港 required 半邊，禁半邊刻意不建網） ----
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_timers: {}', note: '[TestTimerTracking] base.js timer registry' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_setTimer(', note: '[TestTimerTracking] search-flow.js timer methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_clearAllTimers(', note: '[TestTimerTracking] search-flow.js timer methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_clearAllTimers()', note: '[TestTimerTracking] search-flow.js timer methods' },
  { file: 'web/static/js/pages/search/state/persistence.js', kind: 'required-string', pattern: "_setTimer('autosave'", note: '[TestTimerTracking] persistence.js timer' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string', pattern: "_setTimer('loadFavorite'", note: '[TestTimerTracking] file-list.js timer' },

  // ---- [TestTimerTracking exclude-half]（96b-T6 補網：test_timer_tracking_js_excludes，退役 pattern
  // 3 條 forbidden-string，關閉 T1 記錄的技術缺口後才整刪 TestTimerTracking） ----
  { file: 'web/static/js/pages/search/state/base.js', kind: 'forbidden-string', pattern: '_toastTimer: null', note: '[TestTimerTracking exclude-half] base.js 舊 _toastTimer 已移除' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'forbidden-string', pattern: '_toastTimer =', note: '[TestTimerTracking exclude-half] result-card.js 舊 _toastTimer 已移除' },
  { file: 'web/static/js/pages/search/state/persistence.js', kind: 'forbidden-string', pattern: 'saveTimeout', note: '[TestTimerTracking exclude-half] persistence.js 舊 saveTimeout 已移除' },

  // ---- [TestTutorialExpandGuard]（handoff 96a→96b，7 個 step-id required） ----
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'folder'", note: '[TestTutorialExpandGuard] tutorial step id' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'generate'", note: '[TestTutorialExpandGuard] tutorial step id' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'scanner'", note: '[TestTutorialExpandGuard] tutorial step id' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'showcase'", note: '[TestTutorialExpandGuard] tutorial step id' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'search'", note: '[TestTutorialExpandGuard] tutorial step id' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'settings'", note: '[TestTutorialExpandGuard] tutorial step id' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', pattern: "id: 'help'", note: '[TestTutorialExpandGuard] tutorial step id' },

  // ==== 96b-T2：結構型 kind（dup-id / structure-count / tag-scan / inline-style-token / order） ====

  // ---- [TestSettingsPanelStructureGuard] settings.html（4 method：order + structure-count + required + dup-id） ----
  {
    file: 'web/templates/settings.html', kind: 'order',
    items: [
      { pattern: '<form id="settingsForm"' },
      { pattern: 'class="settings-section"' },
      { pattern: 'class="settings-section"', occurrence: 'last' },
      { pattern: '</form>' },
    ],
    note: '[TestSettingsPanelStructureGuard] test_form_wraps_all_three_sections — <form> 包住第一到最後一個 .settings-section',
  },
  {
    file: 'web/templates/settings.html', kind: 'structure-count',
    pattern: 'class="settings-section"', count: 3,
    note: '[TestSettingsPanelStructureGuard] test_form_wraps_all_three_sections — 恰 3 個 .settings-section（exact）',
  },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'id="sec-search"', note: '[TestSettingsPanelStructureGuard] test_form_wraps_all_three_sections — section id' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'id="sec-gallery"', note: '[TestSettingsPanelStructureGuard] test_form_wraps_all_three_sections — section id' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'id="sec-system"', note: '[TestSettingsPanelStructureGuard] test_form_wraps_all_three_sections — section id' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'class="settings-panel"', note: '[TestSettingsPanelStructureGuard] test_sections_single_column_no_activetab_gating — 舊 wrapper 不得殘留' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'x-show="activeTab', note: '[TestSettingsPanelStructureGuard] test_sections_single_column_no_activetab_gating — 不可 activeTab x-show gating' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'x-if="activeTab', note: '[TestSettingsPanelStructureGuard] test_sections_single_column_no_activetab_gating — 不可 activeTab x-if gating' },
  ...[
    'settingsForm', 'saveBtn',
    'translateEnabled', 'translateProvider', 'translateOptions',
    'ollamaUrl', 'ollamaModel', 'geminiApiKey', 'geminiModel',
    'ollamaFields', 'geminiFields', 'openaiFields',
    'searchFavoriteFolder', 'avlistOutputDir', 'avlistOutputFilename',
    'avlistMinSize', 'defaultPage', 'viewerPlayer',
    'createFolder',
    'filenameFormat', 'maxTitleLength', 'maxFilenameLength', 'videoExtensions',
    'avlistMode', 'avlistSort', 'avlistOrder',
    'avlistItemsPerPage',
  ].map((id) => ({
    file: 'web/templates/settings.html', kind: 'required-string', pattern: `id="${id}"`,
    note: '[TestSettingsPanelStructureGuard] test_all_form_ids_preserved — form id 全保留',
  })),
  { file: 'web/templates/settings.html', kind: 'dup-id', note: '[TestSettingsPanelStructureGuard] test_no_duplicate_ids — 單檔內 id 不可重複' },

  // ---- [lint-guard 152d-T-D3] 人臉自動對焦 toggle 接線 ----
  // 這顆 toggle 的接線斷掉時前端測試會全綠（npm lint／npm test／pytest pill 全不執行
  // Alpine @change）。取代 152c `test_toggle_row_has_no_interactive_write_path` 的反向
  // 斷言（那時鎖「沒有 @change」；現在鎖「有 @change 且掛在 data-focal-auto-pill 那顆上」）。
  {
    file: 'web/templates/settings.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<input\b(?=[^>]*\bdata-focal-auto-pill\b)[^>]*>/,
    required: ['@change="setFocalDeviceDisabled($event)"'],
    note: '[lint-guard 152d-T-D3] data-focal-auto-pill <input> 必須綁 @change="setFocalDeviceDisabled($event)"（接線斷掉時前端測試全綠；取代 152c test_toggle_row_has_no_interactive_write_path）',
  },

  // ---- [TestStatePageCloakGuard] div.state-page 全 x-cloak（tag-scan class-tag multi） ----
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'state-page', multi: true, expectedCount: 6,
    required: ['x-cloak'],
    note: '[TestStatePageCloakGuard] test_showcase_state_pages_cloaked — showcase.html 6 個 div.state-page 皆 x-cloak（116a-T4 新增「有收藏但篩選後為零」分支，5→6；不變式不變：每一個都要 x-cloak）',
  },
  {
    file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'state-page', multi: true, expectedCount: 2,
    required: ['x-cloak'],
    note: '[TestStatePageCloakGuard] test_search_state_pages_cloaked — search.html 2 個 div.state-page 皆 x-cloak',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'showcase-grid',
    required: ['shape-poster', 'cardShape'],
    note: '[119-T5fix] .showcase-grid 必須帶 shape-poster 綁定 —— 沒有它 cardShape 到不了 CSS，選直式海報畫面完全沒反應',
  },
  {
    file: 'web/templates/base.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'a', className: 'rotating-border-spotlight',
    required: ['active-once'],
    note: '[133a-T3] 側欄「瀏覽」必須帶 active-once —— 少了它就退回「永遠轉」，'
        + '整頁永遠無法靜止（spec §1.5：燈箱開著時 13fps vs 61fps）',
  },

  // ---- [TestShowcaseToolbarStructureGuard] 影片模式 .toolbar-controls 直接子 .control-group == 1（tag-scan nested-count） ----
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'nested-count',
    outerAnchor: /<div[^>]+class="[^"]*toolbar-section toolbar-controls[^"]*"[^>]+x-show="!showFavoriteActresses"[^>]*>/,
    outerTagName: 'div', innerToken: 'control-group', expected: 1,
    note: '[TestShowcaseToolbarStructureGuard] test_video_mode_toolbar_has_two_control_groups — direct .control-group 應為 1（docstring 過期，assert 為準）',
  },

  // ---- [TestScannerXShowCssConflictGuard] .manual-input / .done-actions 不可裸 x-show（tag-scan class-tag single） ----
  {
    file: 'web/templates/scanner.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'manual-input',
    forbidden: ['x-show='],
    required: [/:style="\{\s*display:\s*manualInputVisible\s*\?\s*'flex'\s*:\s*'none'\s*\}"/],
    note: '[TestScannerXShowCssConflictGuard] test_manual_input_style_binding_on_element — .manual-input 須 :style ternary，不可裸 x-show',
  },
  {
    file: 'web/templates/scanner.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'done-actions',
    required: ['id="doneActions"', /:style="\{\s*display:\s*doneActionsVisible\s*\?\s*'flex'\s*:\s*'none'\s*\}"/],
    forbidden: ['x-show='],
    note: '[TestScannerXShowCssConflictGuard] test_done_actions_style_binding_on_element — .done-actions 須 :style ternary，不可裸 x-show',
  },

  // ---- [TestNoInlineStyleDisplay] 遞迴掃 web/templates/**/*.html（inline-style-token） ----
  {
    file: { dir: 'web/templates', ext: ['.html'], recursive: true },
    kind: 'inline-style-token',
    note: '[TestNoInlineStyleDisplay] test_no_inline_style_display_with_x_show — x-show 元素不可 style="display:none"（遞迴含子目錄）',
  },

  // ---- [TestInlineStyleCleanup]（discrepancy：全 forbidden-string，T1 kind 已足夠） ----
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'style="position: relative;"', note: '[TestInlineStyleCleanup] test_settings_no_inline_position_relative_for_popover' },
  { file: 'web/templates/motion_lab.html', kind: 'forbidden-string', pattern: /style=["'][^"']*object-fit\s*:\s*cover[^"']*["']/, note: '[TestInlineStyleCleanup] test_motion_lab_no_inline_object_fit' },
  {
    file: 'web/templates/design-system.html', kind: 'forbidden-string',
    pattern: /style=["']padding:\s*(?:1(?:\.5)?rem\s+(?:1\.5rem|2rem)|1rem\s+1\.5rem);\s*background:\s*var\(--bg-card\);\s*border-radius:\s*var\(--radius-md\);["']/,
    note: '[TestInlineStyleCleanup] test_design_system_no_inline_bg_card_pattern',
  },

  // ---- [TestHelpPopoverGuard]（structure-count min ×4 + forbidden-string ×2，discrepancy：純 HTML 字串，無 CSS 半邊） ----
  { file: 'web/templates/settings.html', kind: 'structure-count', pattern: 'class="help-popover"', min: 2, note: '[TestHelpPopoverGuard] test_settings_html_contains — help-popover >=2（min）' },
  { file: 'web/templates/settings.html', kind: 'structure-count', pattern: 'class="help-popover-btn"', min: 2, note: '[TestHelpPopoverGuard] test_settings_html_contains — help-popover-btn >=2（min）' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'box-shadow: var(--shadow-4)', note: '[TestHelpPopoverGuard] test_settings_html_contains — broken shadow token 不可殘留' },
  { file: 'web/templates/scanner.html', kind: 'structure-count', pattern: 'class="help-popover"', min: 1, note: '[TestHelpPopoverGuard] test_scanner_html_contains — help-popover >=1（min）' },
  { file: 'web/templates/scanner.html', kind: 'structure-count', pattern: 'class="help-popover-btn"', min: 1, note: '[TestHelpPopoverGuard] test_scanner_html_contains — help-popover-btn >=1（min）' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'box-shadow: var(--shadow-4)', note: '[TestHelpPopoverGuard] test_scanner_html_contains — broken shadow token 不可殘留' },

  // ---- [TestSourcePillMacroTypeButton] _macros/source_pill.html（root button element-bound） ----
  {
    file: 'web/templates/_macros/source_pill.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<button\b[^>]*class="source-pill[^>]*>/,
    required: [/type\s*=\s*"button"/],
    forbidden: [':class='],
    note: '[TestSourcePillMacroTypeButton] test_root_button_has_type_button + test_root_button_has_no_alpine_class_binding — root <button> tag',
  },
  { file: 'web/templates/_macros/source_pill.html', kind: 'required-string', pattern: /\{\{\s*attrs\s*\|\s*safe\s*\}\}/, note: '[TestSourcePillMacroTypeButton] test_attrs_output_via_safe — attrs 必須 |safe 輸出' },
  { file: 'web/templates/_macros/source_pill.html', kind: 'forbidden-string', pattern: /\{\{\s*attrs\s*\}\}/, note: '[TestSourcePillMacroTypeButton] test_attrs_output_via_safe — 不可裸 {{ attrs }}（無 |safe）' },
  {
    file: 'web/templates/_macros/source_pill.html', kind: 'required-string', pattern: 'source-pill--action',
    scope: /\{%\s*if\s+variant\b.*?\{%\s*endif\s*%\}/s,
    note: '[TestSourcePillMacroTypeButton] test_variant_branches_emit_both_classes — variant 分支含 source-pill--action',
  },
  {
    file: 'web/templates/_macros/source_pill.html', kind: 'required-string', pattern: 'source-pill--flat',
    scope: /\{%\s*if\s+variant\b.*?\{%\s*endif\s*%\}/s,
    note: '[TestSourcePillMacroTypeButton] test_variant_branches_emit_both_classes — variant 分支含 source-pill--flat',
  },
  { file: 'web/templates/_macros/source_pill.html', kind: 'required-string', pattern: 'class="pill-spin"', note: '[TestSourcePillMacroTypeButton] test_inner_child_classes_present' },
  { file: 'web/templates/_macros/source_pill.html', kind: 'required-string', pattern: 'class="pill-name"', note: '[TestSourcePillMacroTypeButton] test_inner_child_classes_present' },

  // ---- [TestHeroImageErrorGuard] CD-96-20(b) 強化：整視窗掃描 + @error 存在性斷言（tag-scan window） ----
  {
    file: 'web/templates/search.html', kind: 'tag-scan', mode: 'window',
    anchor: /class="[^"]*hero-card[^"]*"/, window: 1200,
    requiredAttr: /@error="[^"]*"/,
    forbidden: ['target.src', '.src =', 'onerror'],
    note: '[TestHeroImageErrorGuard] test_hero_card_error_handler_excludes — CD-96-20(b) 強化：整個 hero-card 1200 字視窗禁 target.src/.src =/onerror + @error 須存在',
  },

  // ---- [TestUS1TitleAboveMetadata] .av-card-full-title 必須在 .av-card-full-body 之前（order） ----
  {
    file: 'web/templates/search.html', kind: 'order',
    items: [
      { pattern: 'class="av-card-full-title"' },
      { pattern: 'class="av-card-full-body"' },
    ],
    note: '[TestUS1TitleAboveMetadata] test_title_block_precedes_body',
  },

  // ---- [TestUS1InfoGridPairPresent]（structure-count min + scope required/forbidden，discrepancy：不需 tag-scan） ----
  { file: 'web/templates/search.html', kind: 'structure-count', pattern: 'class="info-grid-pair"', min: 2, note: '[TestUS1InfoGridPairPresent] test_two_grid_pairs_and_date_duration_paired — >=2 個 .info-grid-pair（min）' },
  {
    file: 'web/templates/search.html', kind: 'required-string', pattern: 'search.label.date',
    scope: /class="info-grid-pair"[\s\S]*?class="info-grid-pair"/,
    note: '[TestUS1InfoGridPairPresent] test_two_grid_pairs_and_date_duration_paired — 日期在第一對 info-grid-pair 內',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string', pattern: 'search.label.duration',
    scope: /class="info-grid-pair"[\s\S]*?class="info-grid-pair"/,
    note: '[TestUS1InfoGridPairPresent] test_two_grid_pairs_and_date_duration_paired — 片長在第一對 info-grid-pair 內',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'search.label.maker',
    scope: /class="info-grid-pair"[\s\S]*?class="info-grid-pair"/,
    note: '[TestUS1InfoGridPairPresent] test_two_grid_pairs_and_date_duration_paired — 片商不應在第一對 info-grid-pair 內',
  },

  // ---- [TestUS1InfoCellInBody]（structure-count exact，scope-to-EOF，discrepancy：不需 tag-scan） ----
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'class="av-card-full-body"', note: '[TestUS1InfoCellInBody] test_info_cell_inside_body — .av-card-full-body 必須存在' },
  {
    file: 'web/templates/search.html', kind: 'structure-count', pattern: 'class="info-cell"', count: 4,
    scope: /class="av-card-full-body"([\s\S]*)$/,
    note: '[TestUS1InfoCellInBody] test_info_cell_inside_body — body 之後恰 4 個 .info-cell（exact）',
  },

  // ---- [TestUS5VideoCoverFitMobile] / [TestUS9SearchGridMobileFix]（discrepancy：flat required-string，非 tag-scan） ----
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "'has-cover': !!currentLightboxVideo?.cover_url", note: '[TestUS5VideoCoverFitMobile] test_video_lightbox_cover_has_cover_class' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "'has-cover': !actressLightboxMode() && !!resolveCoverUrl(currentLightboxVideo()) && !_heroLightboxImageError", note: '[TestUS9SearchGridMobileFix] test_search_lightbox_has_cover_class（TASK-113c-T7：改用 resolveCoverUrl() 純函式，內部含 _previewFailed error-time fallback，preview_cover_url 優先 fallback cover 語意不變）' },

  // ---- [TestActressCoreMetadataVideoCount]（order + required，brace-balanced scope，handoff 已解除留置 AD-96b-2） ----
  // 116a-T3：anchor 由 _actressCoreMetadata 改為 _actressCoreMetadataParts（函式被結構化陣列版原地取代）。
  // 等價遷移：4 條規則、scope 語意、鎖的內容全部不變，只換錨定的函式名。
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: 'video_count',
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadataParts\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestActressCoreMetadataVideoCount] test_video_count_pushed_first — 方法體含 video_count',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: 'showcase.unit.films',
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadataParts\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestActressCoreMetadataVideoCount] test_video_count_pushed_first — 方法體含 showcase.unit.films i18n key',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'order',
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadataParts\s*\([^)]*\)\s*\{/, braceBalanced: true },
    items: [
      { pattern: /parts\.push\([^)]*video_count[^)]*\)/ },
      { pattern: /parts\.push\([^)]*\.age[^)]*\)/ },
    ],
    note: '[TestActressCoreMetadataVideoCount] test_video_count_pushed_first — video_count push 必須在 age push 之前（前置，brace-balanced scope）',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /typeof\s+\w+\.video_count\s*===\s*['"]number['"]/,
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadataParts\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestActressCoreMetadataVideoCount] test_video_count_typeof_number_guard — typeof a.video_count === \'number\' guard',
  },

  // ---- [TestNoHardcodedColors] HTML inline hex（非遞迴頂層 + exclude 2 個 demo 頁，discrepancy：CSS 半邊已由 stylelint 接管） ----
  {
    file: { dir: 'web/templates', ext: ['.html'], exclude: ['design-system.html', 'motion_lab.html'] },
    kind: 'forbidden-string',
    pattern: /style\s*=\s*(["'])(?:(?!\1).)*#[0-9a-fA-F]{3,8}/,
    note: '[TestNoHardcodedColors] test_no_hardcoded_colors_in_html — HTML inline style 不可 hardcode hex color（CSS 半邊已由 stylelint color-no-hex 接管，T55b）',
  },

  // ---- [TestGridSettlePulse]（required 半邊 method-body window，禁 rotation 半邊刻意不建網，留 T4 SEL_GRID_ROTATION） ----
  {
    file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: 'playGridSettle',
    scope: { anchor: /_triggerStagingExit\s*\(\s*\)\s*\{/, window: 1000 },
    note: '[TestGridSettlePulse] test_grid_settle_pulse_method_bodies — _triggerStagingExit 呼叫 playGridSettle（method-body window 半邊）',
  },
  {
    file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'killTweensOf',
    scope: { anchor: /playGridSettle:\s*function/, window: 3000 },
    note: '[TestGridSettlePulse] test_grid_settle_pulse_method_bodies — playGridSettle 方法體含 killTweensOf（禁 rotation 半邊留 T4 SEL_GRID_ROTATION，不建雙重網）',
  },

  // ---- offline_guards Guard 1/2/3（forbidden-string / scope required+forbidden / tag-scan anchor-first-tag） ----
  { file: 'web/templates/base.html', kind: 'forbidden-string', pattern: 'cdn.jsdelivr.net', note: '[offline_guards Guard1] test_base_html_references_no_cdn_host' },
  {
    file: 'web/templates/base.html', kind: 'required-string', pattern: '/api/client-log',
    scope: /<script\b[^>]*>(?:(?!<\/script>).)*?client-log.*?<\/script>/s,
    note: '[offline_guards Guard2] test_beacon_targets_relative_client_log_only — beacon script 須 POST 相對 /api/client-log',
  },
  {
    file: 'web/templates/base.html', kind: 'forbidden-string', pattern: /https?:\/\/[^"'\s]*client-log/,
    scope: /<script\b[^>]*>(?:(?!<\/script>).)*?client-log.*?<\/script>/s,
    note: '[offline_guards Guard2] test_beacon_targets_relative_client_log_only — 不可絕對 http(s) client-log URL（zero-egress C3）',
  },
  {
    file: 'web/templates/base.html', kind: 'tag-scan', mode: 'anchor-first-tag',
    anchor: /<head\b[^>]*>/i, tagPattern: /<script\b[^>]*>/i,
    forbidden: ['type="module"', 'defer', 'async'],
    note: '[offline_guards Guard3] test_beacon_script_is_parser_blocking_classic — <head> 內第一個 <script>（beacon）須 parser-blocking classic',
  },

  // ---- offline_guards Guard 6（discrepancy 確認：非 dup-id，forbidden-string ×4） ----
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'id="outputPathDisplay"', note: '[offline_guards Guard6] test_scanner_html_drops_self_colliding_ids' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'id="progressStatus"', note: '[offline_guards Guard6] test_scanner_html_drops_self_colliding_ids' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'id="statTotal"', note: '[offline_guards Guard6] test_scanner_html_drops_self_colliding_ids' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'id="statLastRun"', note: '[offline_guards Guard6] test_scanner_html_drops_self_colliding_ids' },

  // ---- [fluent_materials_guards::test_load_order]（order，3-anchor，2 組獨立 pairs） ----
  {
    file: 'web/templates/base.html', kind: 'order',
    items: [
      { pattern: '{% block extra_css %}' },
      { pattern: /<link[^>]*href="\/static\/css\/theme\.css"[^>]*>/ },
      { pattern: /<link[^>]*fluent-materials\.css[^>]*>/ },
    ],
    pairs: [[0, 2], [1, 2]],
    note: '[fluent_materials_guards::test_load_order] fluent-materials.css 必須在 extra_css block 之後、也在 theme.css 之後（CD-A2 source-order）',
  },

  // ==== 96b-T3：ESM/JS-structure 家族（§inventory E，port 自 tests/unit/test_frontend_lint.py）====
  // 4 頁 per-page ESM guard 逐頁不同構（export 前綴/bridge 命名/x-data rename 有無/
  // descriptor-merge 範圍/circular-import 判斷單位皆不同，見 TASK-96b-T3.md〈現況分析〉表），
  // 不開 esm-page kind，逐條分解成既有 required-string/forbidden-string（頁內部均一處用
  // .map() 做 DRY，4 頁彼此不共用同一個 map 函式）。

  // ---- [TestImportMapGuard] base.html importmap + pre_alpine_module slot + ghost-fly.js ESM export/bridge ----
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'type="importmap"', note: '[TestImportMapGuard] test_importmap_exists' },
  ...['"@/shared/"', '"@/components/"', '"@/showcase/"', '"@/scanner/"', '"@/settings/"', '"@/search/"'].map((alias) => ({
    file: 'web/templates/base.html', kind: 'required-string', pattern: alias,
    note: '[TestImportMapGuard] test_importmap_aliases',
  })),
  { file: 'web/templates/base.html', kind: 'required-string', pattern: '{% block pre_alpine_module %}', note: '[TestImportMapGuard] test_pre_alpine_module_slot' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'export', note: '[TestImportMapGuard] test_ghost_fly_has_export' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'window.GhostFly = GhostFly', note: '[TestImportMapGuard] test_ghost_fly_window_bridge' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'type="module" src="/static/js/shared/ghost-fly.js"', note: '[TestImportMapGuard] test_ghost_fly_script_tag_is_module (required half)' },
  { file: 'web/templates/base.html', kind: 'forbidden-string', pattern: '<script defer src="/static/js/shared/ghost-fly.js">', note: '[TestImportMapGuard] test_ghost_fly_script_tag_is_module (forbidden half — 舊 tag 殘留防呆)' },

  // ---- [TestESMExportGuard] 5 個 shared/components 共用工具：export + window bridge + base.html script tag ----
  // motion-adapter.js 不在 requiresExport 名單：103-T1 刪除唯一的
  // `export { motion as MotionAdapter };`（死碼——全庫零 `import { MotionAdapter }`
  // 消費端，該檔以 <script type="module" src="...">「入口模組」形式載入，非被
  // import 消費）；window bridge（window.OpenAver.motion）與 base.html script tag
  // 檢查不受影響、仍是所有現役呼叫端的存取路徑。
  ...[
    ['web/static/js/shared/burst-picker.js', 'window.BurstPicker', '/static/js/shared/burst-picker.js', true],
    ['web/static/js/components/motion-adapter.js', 'window.OpenAver.motion', '/static/js/components/motion-adapter.js', false],
    ['web/static/js/components/page-lifecycle.js', 'window.__registerPage', '/static/js/components/page-lifecycle.js', true],
    ['web/static/js/components/motion-prefs.js', 'window.OpenAver', '/static/js/components/motion-prefs.js', true],
  ].flatMap(([file, bridge, scriptPath, requiresExport]) => ([
    ...(requiresExport ? [{ file, kind: 'required-string', pattern: 'export', note: `[TestESMExportGuard] ${file} export` }] : []),
    { file, kind: 'required-string', pattern: bridge, note: `[TestESMExportGuard] ${file} window bridge (${bridge})` },
    { file: 'web/templates/base.html', kind: 'required-string', pattern: `type="module" src="${scriptPath}"`, note: `[TestESMExportGuard] base.html ${scriptPath} script tag is module` },
    { file: 'web/templates/base.html', kind: 'forbidden-string', pattern: `<script defer src="${scriptPath}">`, note: `[TestESMExportGuard] base.html ${scriptPath} no residual defer tag` },
  ])),
  // path-utils.js：export + pathToDisplay 兩個獨立斷言（pytest 用 `and` 併在同一行，本質是
  // 2 個各自的 required-string，勿漏這個與其他 4 檔不對稱的地方）+ window bridge
  { file: 'web/static/js/components/path-utils.js', kind: 'required-string', pattern: 'export', note: '[TestESMExportGuard] path-utils.js export' },
  { file: 'web/static/js/components/path-utils.js', kind: 'required-string', pattern: 'pathToDisplay', note: '[TestESMExportGuard] path-utils.js exports pathToDisplay（獨立斷言，非與 export 合併成一條）' },
  { file: 'web/static/js/components/path-utils.js', kind: 'required-string', pattern: 'window.pathToDisplay', note: '[TestESMExportGuard] path-utils.js window bridge' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'type="module" src="/static/js/components/path-utils.js"', note: '[TestESMExportGuard] base.html path-utils.js script tag is module' },
  { file: 'web/templates/base.html', kind: 'forbidden-string', pattern: '<script defer src="/static/js/components/path-utils.js">', note: '[TestESMExportGuard] base.html path-utils.js no residual defer tag' },

  // ---- [TestSettingsESMGuard] 54d：settings state 模組 + main.js + settings.html ----
  ...[
    ['state-config.js', 'stateConfig'],
    ['state-providers.js', 'stateProviders'],
    ['state-ui.js', 'stateUI'],
  ].map(([file, fn]) => ({
    file: `web/static/js/pages/settings/${file}`, kind: 'required-string',
    pattern: `export function ${fn}`,
    note: `[TestSettingsESMGuard] ${file} exports ${fn}`,
  })),
  // ---- [TestMergeStateSharedGuard] T3：mergeState() 收斂進 shared/merge-state.js ----
  // 合併邏輯本體（descriptor-preserving merge）現在只有 1 份實作，斷言集中在此檔案，
  // 不再逐頁驗證函式體字面。但只驗這裡會產生假綠（shared 對、某頁沒接上），
  // 故 4 個 main.js 各自新增兩條行首 anchored 斷言（見各頁區塊）：
  //   ① 具名 import 綁定 `import { mergeState } from '@/shared/merge-state.js'`
  //      ——只比對 module 路徑字串會放行 default import（shared 無 default export，
  //        瀏覽器在模組實例化階段就 SyntaxError，但 lint 全盲）。
  //   ② 實際呼叫 `mergeState(` ——只驗 import 存在會放行「保留 import 但改用
  //      Object.assign 組裝」，那會靜默丟失 getter/setter descriptor，
  //      正是 mergeState 存在要防的 bug，且 runtime 不報錯。
  // 兩處皆為 Codex PR review P2 補強（原僅路徑 substring）。三層斷言
  //（shared 本體運算式 + 具名 import + 呼叫）合起來才是完整的 pure-move gate（CD-10）。
  {
    // ⚠ 鎖「整條運算式」而非 Object.getOwnPropertyDescriptors / Object.defineProperties
    // 兩個字面各自存在——後者是整檔 substring 比對，而本檔 docblock 剛好把這兩個名字
    // 都寫進散文裡，導致連 Object.assign 這種普通回歸都測不出來（T3 review 實測假綠）。
    // 改鎖含 target/part 的完整呼叫式後，換 API（assign）與換參數順序兩類 mutation 皆轉紅；
    // `^[ \t]*` 開頭使 docblock 行（必有 `*` 前綴）不可能誤命中。
    file: 'web/static/js/shared/merge-state.js', kind: 'required-string',
    pattern: /^[ \t]*Object\.defineProperties\(target, Object\.getOwnPropertyDescriptors\(part\)\);[ \t]*$/m,
    note: '[TestMergeStateSharedGuard] test_merge_state_uses_descriptor_preserving_merge — descriptor 合併運算式整條鎖定（非字面各自存在，防 docblock 假綠）',
  },
  {
    file: 'web/static/js/shared/merge-state.js', kind: 'required-string',
    pattern: 'export function mergeState',
    note: '[TestMergeStateSharedGuard] test_merge_state_is_named_export — 四頁皆用具名 import，非 default export',
  },
  { file: 'web/static/js/pages/settings/main.js', kind: 'required-string', pattern: 'alpine:init', note: '[TestSettingsESMGuard] test_main_js_exists_and_has_alpine_init' },
  { file: 'web/static/js/pages/settings/main.js', kind: 'required-string', pattern: "Alpine.data('settings',", note: '[TestSettingsESMGuard] test_main_js_registers_settings_name (required half)' },
  { file: 'web/static/js/pages/settings/main.js', kind: 'forbidden-string', pattern: "Alpine.data('settingsPage'", note: '[TestSettingsESMGuard] test_main_js_registers_settings_name (forbidden half)' },
  { file: 'web/static/js/pages/settings/main.js', kind: 'required-string', pattern: '@/settings/', note: '[TestSettingsESMGuard] test_main_js_uses_importmap_alias' },
  ...['state-config.js', 'state-providers.js', 'state-ui.js'].map((file) => ({
    file: `web/static/js/pages/settings/${file}`, kind: 'forbidden-string',
    pattern: /^\s*import\b[^\n]*\b(?:state-config|state-providers|state-ui)\b/m,
    note: `[TestSettingsESMGuard] test_no_circular_state_imports — ${file} 頂層 import 不可引用 settings 3 個 state 模組檔名（含自身，忠實 port，自我引用不可能發生）`,
  })),
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'pre_alpine_module', note: '[TestSettingsESMGuard] test_settings_html_has_pre_alpine_module (block)' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'settings/main.js', note: '[TestSettingsESMGuard] test_settings_html_has_pre_alpine_module (main.js script)' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'x-data="settings"', note: '[TestSettingsESMGuard] test_settings_html_xdata_is_settings (required half)' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'x-data="settingsPage"', note: '[TestSettingsESMGuard] test_settings_html_xdata_is_settings (forbidden half)' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: '/pages/settings.js', note: '[TestSettingsESMGuard] test_settings_html_no_settings_js_script' },
  { file: 'web/static/js/pages/settings.js', kind: 'file-absent', note: '[TestSettingsESMGuard] test_settings_js_deleted — 舊 settings.js 應已刪除' },
  {
    file: { dir: 'web/templates', ext: ['.html'], recursive: true }, kind: 'forbidden-string',
    pattern: 'x-data="settingsPage"',
    note: '[TestSettingsESMGuard] test_no_settings_page_xdata_in_templates — 全 templates 遞迴不可殘留',
  },
  {
    file: { dir: 'web/static/js/pages', ext: ['.js'], recursive: true }, kind: 'forbidden-string',
    pattern: "Alpine.data('settingsPage'",
    note: "[TestSettingsESMGuard] test_no_settings_page_alpine_data_in_js — pages/**/*.js 遞迴不可殘留",
  },
  { file: 'web/static/js/pages/settings/main.js', kind: 'forbidden-string', pattern: 'settingsPage', note: '[TestSettingsESMGuard] test_main_js_no_settingspage_reference — main.js 全檔不含 settingsPage 字面（比 Alpine.data 那條更廣，2 條各自照抄）' },
  {
    file: 'web/static/js/pages/settings/main.js', kind: 'required-string',
    pattern: /^[ \t]*import[ \t]*\{[ \t]*mergeState[ \t]*\}[ \t]*from[ \t]*'@\/shared\/merge-state\.js';/m,
    note: '[TestSettingsESMGuard] test_main_js_imports_merge_state — 具名 import 綁定（防 default import 假綠，Codex P2）',
  },
  {
    file: 'web/static/js/pages/settings/main.js', kind: 'required-string',
    pattern: /^[ \t]*Alpine\.data\('settings',[ \t]*\(\)[ \t]*=>[ \t]*mergeState\(/m,
    note: '[TestSettingsESMGuard] test_main_js_calls_merge_state — 實際呼叫 mergeState(...)，非 Object.assign 等替代品（防 descriptor 丟失假綠，Codex P2）',
  },
  { file: 'web/static/js/pages/settings/main.js', kind: 'forbidden-string', pattern: '...stateConfig()', note: '[TestSettingsESMGuard] test_main_js_uses_descriptor_merge (forbidden half — 只驗 1/3 factory 的 spread，弱於 scanner/showcase/search 頁，故意不補強成一致，CD-96-9)' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'get isDirty()', note: '[TestSettingsESMGuard] test_state_config_has_getter_isDirty — isDirty 須為 getter 非 plain prop（settings 頁獨有斷言）' },
  // ---- 165-T9：自訂來源是獨立元件，父層分片不可長出 customSrc 狀態；掛載點不可改名 ----
  ...['state-config.js', 'state-source-probe.js'].map((file) => ({
    file: `web/static/js/pages/settings/${file}`, kind: 'forbidden-string', pattern: 'customSrc',
    note: `[lint-guard 165-T9-parent-isolation] ${file} 不可出現 customSrc（自訂來源獨立元件，不進 mergeState 分片）`,
  })),
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'x-data="customSources"', note: '[lint-guard 165-T9-mount-point] 設定頁須掛載 customSources 元件' },
  { file: 'web/templates/help.html', kind: 'required-string', pattern: "t('help.scraper.custom_what')", note: '[lint-guard 165-T11-help-section] 說明頁 Scraper 卡須有「自訂來源」一節（哨兵 key custom_what）' },

  // ---- [TestScannerESMGuard] 54c：scanner state 模組 + main.js + scanner.html ----
  ...[
    ['state-scan.js', 'stateScan'],
    ['state-batch.js', 'stateBatch'],
    ['state-alias.js', 'stateAlias'],
  ].map(([file, fn]) => ({
    file: `web/static/js/pages/scanner/${file}`, kind: 'required-string',
    pattern: `export function ${fn}`,
    note: `[TestScannerESMGuard] ${file} exports ${fn}`,
  })),
  { file: 'web/static/js/pages/scanner/main.js', kind: 'required-string', pattern: 'alpine:init', note: '[TestScannerESMGuard] test_main_js_exists_and_has_alpine_init' },
  { file: 'web/static/js/pages/scanner/main.js', kind: 'required-string', pattern: "Alpine.data('scanner',", note: '[TestScannerESMGuard] test_main_js_registers_scanner_name (required half)' },
  { file: 'web/static/js/pages/scanner/main.js', kind: 'forbidden-string', pattern: "Alpine.data('scannerPage'", note: '[TestScannerESMGuard] test_main_js_registers_scanner_name (forbidden half)' },
  { file: 'web/static/js/pages/scanner/main.js', kind: 'required-string', pattern: '@/scanner/', note: '[TestScannerESMGuard] test_main_js_uses_importmap_alias' },
  {
    file: 'web/static/js/pages/scanner/main.js', kind: 'required-string',
    pattern: /^[ \t]*import[ \t]*\{[ \t]*mergeState[ \t]*\}[ \t]*from[ \t]*'@\/shared\/merge-state\.js';/m,
    note: '[TestScannerESMGuard] test_main_js_imports_merge_state — 具名 import 綁定（防 default import 假綠，Codex P2）',
  },
  {
    file: 'web/static/js/pages/scanner/main.js', kind: 'required-string',
    pattern: /^[ \t]*Alpine\.data\('scanner',[ \t]*\(\)[ \t]*=>[ \t]*mergeState\(/m,
    note: '[TestScannerESMGuard] test_main_js_calls_merge_state — 實際呼叫 mergeState(...)，非 Object.assign 等替代品（防 descriptor 丟失假綠，Codex P2）',
  },
  ...['stateScan()', 'stateBatch()', 'stateAlias()'].map((fn) => ({
    file: 'web/static/js/pages/scanner/main.js', kind: 'forbidden-string', pattern: `...${fn}`,
    note: '[TestScannerESMGuard] test_main_js_no_plain_spread_merge — 3 factory 全禁（強於 settings 頁只驗 1 個）',
  })),
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string', pattern: 'checkMissing() {', note: '[TestScannerESMGuard] test_state_scan_no_batch_functions' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string', pattern: 'runMissingEnrich', note: '[TestScannerESMGuard] test_state_scan_no_batch_functions' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string', pattern: 'resumeMissingEnrich', note: '[TestScannerESMGuard] test_state_scan_no_batch_functions' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'forbidden-string', pattern: 'generate(', note: '[TestScannerESMGuard] test_state_batch_no_scan_functions' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'forbidden-string', pattern: 'runNfoUpdate', note: '[TestScannerESMGuard] test_state_batch_no_scan_functions' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'forbidden-string', pattern: 'runJellyfinImageUpdate', note: '[TestScannerESMGuard] test_state_batch_no_scan_functions' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'forbidden-string', pattern: 'copyOutputPath', note: '[TestScannerESMGuard] test_state_batch_no_scan_functions' },
  ...['state-scan.js', 'state-batch.js', 'state-alias.js'].map((file) => ({
    file: `web/static/js/pages/scanner/${file}`, kind: 'forbidden-string',
    pattern: /^\s*import\b[^\n]*\b(?:state-scan|state-batch|state-alias)\b/m,
    note: `[TestScannerESMGuard] test_no_circular_state_imports — ${file} 頂層 import 不可引用 scanner 3 個 state 模組檔名（含自身，忠實 port）`,
  })),
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'pre_alpine_module', note: '[TestScannerESMGuard] test_scanner_html_has_pre_alpine_module (block)' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'scanner/main.js', note: '[TestScannerESMGuard] test_scanner_html_has_pre_alpine_module (main.js script)' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'x-data="scanner"', note: '[TestScannerESMGuard] test_scanner_html_xdata_is_scanner (required half)' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'x-data="scannerPage"', note: '[TestScannerESMGuard] test_scanner_html_xdata_is_scanner (forbidden half)' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: '/pages/scanner.js', note: '[TestScannerESMGuard] test_scanner_html_no_scanner_js_script' },
  { file: 'web/static/js/pages/scanner.js', kind: 'file-absent', note: '[TestScannerESMGuard] test_scanner_js_deleted — 舊 scanner.js 應已刪除' },
  {
    file: { dir: 'web/templates', ext: ['.html'], recursive: true }, kind: 'forbidden-string',
    pattern: 'x-data="scannerPage"',
    note: '[TestScannerESMGuard] test_no_scanner_page_xdata_in_templates — 全 templates 遞迴不可殘留',
  },
  {
    file: { dir: 'web/static/js/pages', ext: ['.js'], recursive: true }, kind: 'forbidden-string',
    pattern: "Alpine.data('scannerPage'",
    note: '[TestScannerESMGuard] test_no_scanner_page_alpine_data_in_js — pages/**/*.js 遞迴不可殘留',
  },
  { file: 'web/static/js/pages/scanner/main.js', kind: 'forbidden-string', pattern: 'scannerPage', note: '[TestScannerESMGuard] test_main_js_no_scannerpage_reference — main.js 全檔不含 scannerPage 字面（比 Alpine.data 那條更廣）' },

  // ---- [TestShowcaseESMGuard] 54b：showcase state 模組 + main.js + showcase.html ----
  ...[
    ['state-base.js', 'stateBase'],
    ['state-videos.js', 'stateVideos'],
    ['state-actress.js', 'stateActress'],
    ['state-lightbox.js', 'stateLightbox'],
    ['state-lightbox-mask.js', 'stateLightboxMask'],
    ['state-lightbox-picker.js', 'stateLightboxPicker'],
    ['state-lightbox-samples.js', 'stateLightboxSamples'],
    ['state-lightbox-tags.js', 'stateLightboxTags'],
  ].map(([file, fn]) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'required-string',
    pattern: `export function ${fn}`,
    note: `[TestShowcaseESMGuard] ${file} exports ${fn}`,
  })),
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', anyOf: true,
    pattern: ['export var _videos', 'export let _videos'],
    note: '[TestShowcaseESMGuard] test_state_base_exists_and_exports — export var/let _videos（OR）',
  },
  ...['_videos', '_filteredVideos', '_actresses', '_filteredActresses'].map((name) => ({
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', pattern: name,
    note: '[TestShowcaseESMGuard] test_state_base_has_shared_array_exports',
  })),
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'forbidden-string', pattern: 'openLightbox(', note: '[TestShowcaseESMGuard] test_state_base_no_lightbox_functions' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'forbidden-string', pattern: 'closeLightbox(', note: '[TestShowcaseESMGuard] test_state_base_no_lightbox_functions' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'forbidden-string', pattern: '_PICKER_PARAMS', note: '[TestShowcaseESMGuard] test_state_base_no_picker_params' },
  { file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: 'alpine:init', note: '[TestShowcaseESMGuard] test_main_js_exists_and_has_alpine_init' },
  {
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', anyOf: true,
    pattern: ["Alpine.data('showcase',", 'Alpine.data("showcase",'],
    note: '[TestShowcaseESMGuard] test_main_js_registers_showcase_name (required half, 雙引號變體 OR)',
  },
  { file: 'web/static/js/pages/showcase/main.js', kind: 'forbidden-string', pattern: ["Alpine.data('showcaseState'", 'Alpine.data("showcaseState"'], note: '[TestShowcaseESMGuard] test_main_js_registers_showcase_name (forbidden half, 雙引號變體亦禁)' },
  { file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: '@/showcase/', note: '[TestShowcaseESMGuard] test_main_js_uses_importmap_alias' },
  {
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string',
    pattern: /^[ \t]*import[ \t]*\{[ \t]*mergeState[ \t]*\}[ \t]*from[ \t]*'@\/shared\/merge-state\.js';/m,
    note: '[TestShowcaseESMGuard] test_main_js_imports_merge_state — 具名 import 綁定（防 default import 假綠，Codex P2）',
  },
  {
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string',
    pattern: /^[ \t]*return[ \t]*mergeState\(/m,
    note: '[TestShowcaseESMGuard] test_main_js_calls_merge_state — 實際呼叫 mergeState(...)，非 Object.assign 等替代品（防 descriptor 丟失假綠，Codex P2）',
  },
  ...['stateBase()', 'stateVideos()', 'stateActress()', 'stateLightbox()', 'stateLightboxMask()', 'stateLightboxPicker()', 'stateLightboxTags()', 'stateLightboxSamples()'].map((fn) => ({
    file: 'web/static/js/pages/showcase/main.js', kind: 'forbidden-string', pattern: `...${fn}`,
    note: '[TestShowcaseESMGuard] test_main_js_no_plain_spread_merge — 8 factory 全禁',
  })),
  ...['stateBase', 'stateVideos', 'stateActress', 'stateLightbox', 'stateLightboxMask', 'stateLightboxPicker', 'stateLightboxSamples', 'stateLightboxTags'].map((fn) => ({
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: `${fn}.call(this)`,
    note: '[TestShowcaseESMGuard] test_main_js_factory_calls_use_call_this — 唯一有此斷言的頁（settings/scanner/search 皆未檢查）',
  })),
  { file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: 'window.showcaseState', note: '[TestShowcaseESMGuard] test_main_js_has_window_showcase_state_bridge — 唯一有 window bridge 斷言的頁' },
  ...['state-videos.js', 'state-actress.js', 'state-lightbox.js', 'state-lightbox-mask.js', 'state-lightbox-picker.js', 'state-lightbox-samples.js', 'state-lightbox-tags.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string',
    pattern: /^\s*import\b[^\n]*\b(?:stateBase|stateVideos|stateActress|stateLightbox|stateLightboxMask|stateLightboxPicker|stateLightboxSamples|stateLightboxTags)\b/m,
    note: `[TestShowcaseESMGuard] test_no_circular_state_factory_imports — ${file} 頂層 import 不可含 6 個 factory 函式名（判斷單位是 factory 名非檔名；state-base.js 本身不驗）`,
  })),
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /^import\s*\{[^}]*\b_killLightboxTimelines\b[^}]*\}\s*from\s*'@\/showcase\/state-base\.js'/m,
    note: '[TestShowcaseESMGuard] test_state_lightbox_imports_kill_timelines' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string', pattern: 'loadActresses', note: '[TestShowcaseESMGuard] test_state_videos_no_actress_functions' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string', pattern: 'addFavoriteActress', note: '[TestShowcaseESMGuard] test_state_videos_no_actress_functions' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string', pattern: /^\s+openLightbox\s*\(/m, note: '[TestShowcaseESMGuard] test_state_actress_no_lightbox_functions — 方法定義 regex（行首縮排+openLightbox(，防誤殺 this.openLightbox(...) 呼叫）' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string', pattern: /^\s+closeLightbox\s*\(/m, note: '[TestShowcaseESMGuard] test_state_actress_no_lightbox_functions' },
  ...['state-base.js', 'state-videos.js', 'state-actress.js', 'state-lightbox.js', 'state-lightbox-mask.js', 'state-lightbox-picker.js', 'state-lightbox-samples.js', 'state-lightbox-tags.js', 'main.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string',
    pattern: /^(?!\s)(?!\/\/)(?!\*)[^\n]*window\.gsap/m,
    note: `[TestShowcaseESMGuard] test_no_gsap_at_module_top_level — ${file} 頂層非註解行不可含 window.gsap`,
  })),
  ...['state-base.js', 'state-videos.js', 'state-actress.js', 'state-lightbox.js', 'state-lightbox-mask.js', 'state-lightbox-picker.js', 'state-lightbox-samples.js', 'state-lightbox-tags.js', 'main.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string',
    pattern: /^gsap\b/m,
    note: `[TestShowcaseESMGuard] test_no_gsap_at_module_top_level — ${file} 頂層行不可以 gsap 識別字開頭`,
  })),
  ...['state-base.js', 'state-videos.js', 'state-actress.js', 'state-lightbox.js', 'state-lightbox-mask.js', 'state-lightbox-picker.js', 'state-lightbox-samples.js', 'state-lightbox-tags.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string', pattern: 'this._PICKER_PARAMS',
    note: `[TestShowcaseESMGuard] test_no_this_picker_params_in_state_modules — ${file} 不可 this._PICKER_PARAMS（main.js 不在此列）`,
  })),
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'pre_alpine_module', note: '[TestShowcaseESMGuard] test_showcase_html_has_pre_alpine_module (block)' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'showcase/main.js', note: '[TestShowcaseESMGuard] test_showcase_html_has_pre_alpine_module (main.js script)' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'x-data="showcase"', note: '[TestShowcaseESMGuard] test_showcase_html_xdata_is_showcase (required half)' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: 'x-data="showcaseState"', note: '[TestShowcaseESMGuard] test_showcase_html_xdata_is_showcase (forbidden half)' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: 'core.js', note: '[TestShowcaseESMGuard] test_showcase_html_no_core_js_script — 舊檔案名是 core.js，非 /pages/showcase.js（命名慣例與其他 3 頁不同）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'animations.js', note: '[TestShowcaseESMGuard] test_showcase_html_still_has_animations_js — B5 不動 animations.js' },
  { file: 'web/static/js/pages/showcase/core.js', kind: 'file-absent', note: '[TestShowcaseESMGuard] test_core_js_deleted — 舊 core.js 磁碟檔應已刪除' },
  {
    file: { dir: 'web/templates', ext: ['.html'], recursive: true }, kind: 'forbidden-string',
    pattern: 'x-data="showcaseState"',
    note: '[TestShowcaseESMGuard] test_no_showcase_state_xdata_in_templates — 全 templates 遞迴不可殘留',
  },
  {
    file: { dir: 'web/static/js/pages', ext: ['.js'], recursive: true }, kind: 'forbidden-string',
    pattern: ["Alpine.data('showcaseState'", 'Alpine.data("showcaseState"'],
    note: '[TestShowcaseESMGuard] test_no_showcase_state_alpine_data_in_js — pages/**/*.js 遞迴不可殘留（雙引號變體亦禁）',
  },

  // ---- [TestSearchESMGuard] 54e：search state 模組（searchStateXxx 前綴，未 rename Alpine 元件）+ main.js + search.html ----
  ...[
    ['base.js', 'searchStateBase'],
    ['persistence.js', 'searchStatePersistence'],
    ['search-flow.js', 'searchStateSearchFlow'],
    ['navigation.js', 'searchStateNavigation'],
    ['batch.js', 'searchStateBatch'],
    ['result-card.js', 'searchStateResultCard'],
    ['file-list.js', 'searchStateFileList'],
    ['grid-mode.js', 'searchStateGridMode'],
  ].map(([file, fn]) => ({
    file: `web/static/js/pages/search/state/${file}`, kind: 'required-string',
    pattern: `export function ${fn}`,
    note: `[TestSearchESMGuard] state/${file} exports ${fn}`,
  })),
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: 'alpine:init', note: '[TestSearchESMGuard] test_main_js_exists_and_has_alpine_init' },
  {
    file: 'web/static/js/pages/search/main.js', kind: 'required-string', anyOf: true,
    pattern: ["Alpine.data('searchPage'", 'Alpine.data("searchPage"'],
    note: '[TestSearchESMGuard] test_main_js_registers_search_page_name — search 元件名從未改過，required-only，無 forbidden 半邊',
  },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: '@/search/state/', note: '[TestSearchESMGuard] test_main_js_uses_importmap_alias — 用 @/search/ alias 接 state/ 子路徑，非第 7 個 alias' },
  {
    file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: /^[ \t]*import[ \t]*\{[ \t]*mergeState[ \t]*\}[ \t]*from[ \t]*'@\/shared\/merge-state\.js';/m,
    note: '[TestSearchESMGuard] test_main_js_imports_merge_state — 具名 import 綁定（防 default import 假綠，Codex P2）',
  },
  {
    file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: /^[ \t]*return[ \t]*mergeState\(/m,
    note: '[TestSearchESMGuard] test_main_js_calls_merge_state — 實際呼叫 mergeState(...)，非 Object.assign 等替代品（防 descriptor 丟失假綠，Codex P2）',
  },
  { file: 'web/static/js/pages/search/main.js', kind: 'forbidden-string', pattern: '...searchStateBase()', note: '[TestSearchESMGuard] test_main_js_uses_merge_state_not_spread — 只驗 1/8 factory 的 spread（同 settings 頁弱範圍，忠實照抄不補強）' },
  ...['base.js', 'persistence.js', 'search-flow.js', 'navigation.js', 'batch.js', 'result-card.js', 'file-list.js', 'grid-mode.js'].map((file) => ({
    file: `web/static/js/pages/search/state/${file}`, kind: 'forbidden-string', pattern: 'window.SearchStateMixin_',
    note: `[TestSearchESMGuard] test_no_window_mixin_in_state_modules — state/${file} 不可殘留舊全域名稱`,
  })),
  ...['base.js', 'persistence.js', 'search-flow.js', 'navigation.js', 'batch.js', 'result-card.js', 'file-list.js', 'grid-mode.js'].map((file, _i, allFiles) => {
    const self = file.replace('.js', '');
    const alt = allFiles.map((f) => f.replace('.js', '')).filter((n) => n !== self).join('|');
    return {
      file: `web/static/js/pages/search/state/${file}`, kind: 'forbidden-string',
      pattern: new RegExp(`^\\s*import\\b[^\\n]*\\bstate/(?:${alt})\\b`, 'm'),
      note: `[TestSearchESMGuard] test_no_circular_state_imports — state/${file} 頂層 import 不可引用其餘 7 個 state/<other> 路徑片段（排除自身，判斷單位是路徑片段非檔名/factory 名）`,
    };
  }),
  { file: { dir: 'web/static/js/pages/search', ext: ['.js'], recursive: true }, kind: 'forbidden-string', pattern: 'window.SearchStateMixin_', note: '[TestSearchESMGuard] test_no_window_search_state_mixin_in_pages_js — pages/search/**/*.js 遞迴不可殘留（涵蓋 main.js/advanced-picker.js 等 8 個 state 檔以外的檔案）' },
  { file: { dir: 'web/templates', ext: ['.html'], recursive: true }, kind: 'forbidden-string', pattern: 'window.SearchStateMixin_', note: '[TestSearchESMGuard] test_no_window_search_state_mixin_in_templates — 全 templates 遞迴不可殘留' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'pre_alpine_module', note: '[TestSearchESMGuard] test_search_html_has_pre_alpine_module (block)' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'search/main.js', note: '[TestSearchESMGuard] test_search_html_has_pre_alpine_module (main.js script)' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'x-data="searchPage"', note: '[TestSearchESMGuard] test_search_html_xdata_is_search_page — required-only，search 從未 rename，無 forbidden 半邊（勿無腦加對稱 forbidden，會恆假）' },
  ...['state/base.js', 'state/persistence.js', 'state/search-flow.js', 'state/navigation.js', 'state/batch.js', 'state/result-card.js', 'state/file-list.js', 'state/grid-mode.js', 'state/index.js'].map((script) => ({
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: script,
    note: '[TestSearchESMGuard] test_search_html_no_old_state_script_tags — 9 個舊 classic script tag 逐一禁止（search 原本是多檔 classic script，無單一舊主檔）',
  })),
  { file: 'web/static/js/pages/search/state/index.js', kind: 'file-absent', note: '[TestSearchESMGuard] test_search_state_index_js_deleted — 舊 index.js 應已刪除（54e 職責改由 main.js 接替）' },

  // ---- [TestBurstPickerGuard] 49b-T4a：burst-picker.js 抽出（早於 54a ESM 遷移，與 TestESMExportGuard 對同一 tag 有時序重疊但需各自建網）----
  { file: 'web/static/js/shared/burst-picker.js', kind: 'required-string', pattern: 'window.BurstPicker', note: '[TestBurstPickerGuard] test_burst_picker_js_contains — window.BurstPicker' },
  ...[
    'playPickerBurst', 'playPickerFloat', 'playPickerHoverIn', 'playPickerHoverOut',
    'playPickerFlipReplace', 'playPickerExitAll', 'playPickerReverseAll',
  ].map((method) => ({
    file: 'web/static/js/shared/burst-picker.js', kind: 'required-string', pattern: `${method}:`,
    note: `[TestBurstPickerGuard] test_burst_picker_js_contains — burst-picker.js 需定義 ${method}`,
  })),
  ...[
    'playPickerBurst', 'playPickerFloat', 'playPickerHoverIn', 'playPickerHoverOut',
    'playPickerFlipReplace', 'playPickerExitAll', 'playPickerReverseAll',
  ].map((method) => ({
    file: 'web/static/js/pages/motion-lab.js', kind: 'forbidden-string',
    pattern: new RegExp(`${escapeRegExp(method)}\\s*:\\s*function`),
    note: `[TestBurstPickerGuard] test_burst_picker_js_contains — motion-lab.js 不應仍內嵌 ${method} 方法定義`,
  })),
  { file: 'web/static/js/pages/motion-lab-state.js', kind: 'required-string', pattern: 'window.BurstPicker.playPicker', note: '[TestBurstPickerGuard] test_burst_picker_js_contains — motion-lab-state.js 呼叫新模組' },
  { file: 'web/static/js/pages/motion-lab-state.js', kind: 'forbidden-string', pattern: /window\.MotionLab\.playPicker\w+/, note: '[TestBurstPickerGuard] test_burst_picker_js_contains — motion-lab-state.js 不可殘留舊呼叫 window.MotionLab.playPicker*' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: '/static/js/shared/burst-picker.js', note: '[TestBurstPickerGuard] test_base_html_loads_burst_picker — script 引用存在' },
  {
    file: 'web/templates/base.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<script[^>]*burst-picker\.js[^>]*>/, multi: true,
    requiredAnyOf: ['defer', 'type="module"'],
    note: '[TestBurstPickerGuard] test_base_html_loads_burst_picker — 每個 burst-picker.js script tag 需 defer 或 type="module"（OR，非 AND；與 TestESMExportGuard 對同一 tag 有重疊但不同斷言，兩者各自需要各自的替代網，T6 才能各自判斷是否可刪）',
  },

  // ---- [TestShowcaseCoreJsSearchableFields] showcase/state-videos.js searchable fields（required-only subset，非 exact-set，勿加禁多餘欄位半邊）----
  ...[
    'title', 'original_title', 'actresses', 'number', 'maker', 'tags',
    'release_date', 'path', 'director', 'series', 'label', 'user_tags',
  ].map((f) => ({
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: `video.${f}`,
    scope: /const\s+searchable\s*=\s*\[([\s\S]*?)\]\.filter\(Boolean\)/,
    note: `[TestShowcaseCoreJsSearchableFields] searchable array 必須含 video.${f}（required-only subset，允許多餘欄位，不驗 exact-set，見 CD-96-9 忠實原則）`,
  })),

  // ==== 96b-T4（Opus-resolved）：port 自 test_frontend_lint.py 的 text-based 斷言，非 eslint domain ====

  // ---- [TestMotionInfra::test_no_direct_gsap_calls_in_pages] pages/**/*.js + components/**/*.js
  // 遞迴禁直接 gsap.(to|from|fromTo|set|timeline)( / ScrollTrigger.(create|batch)( 呼叫。
  // 原 pytest 是純文字 regex 掃描（find_pattern_in_file），非 AST 語意，故留在 static_guard_lint
  // 而非 eslint（Opus-resolved 決策 1：eslint no-restricted-syntax 對這 7 個分散白名單檔缺乏
  // 精準 file-scope 手段，改用本引擎既有的 dir-mode exclude，比開 5 個新 eslint
  // group 更省事且不擴大 flat-config 陷阱攻擊面）。
  // 7 檔白名單（動態座標計算 / adapter 本體 / per-host lifecycle 合法呼叫）：
  //   〔7 檔＝96b-T4 自來源 pytest allowed_files 逐字 port，該 pytest 已於 feature/96
  //     遷移時刪除，本清單即現存唯一真理〕
  //   components/motion-adapter.js、pages/motion-lab.js、pages/motion-lab-state.js、
  //   pages/search/animations.js、pages/showcase/animations.js、
  //   pages/motion-lab/constellation-host.js、pages/showcase/state-similar.js。
  // exclude 比對「相對於 dir 的相對路徑」（非 basename）：basename 比對會讓未來新增的同名檔
  // （如 pages/foo/animations.js）被誤放行，故改用完整相對路徑，與來源 pytest 語意一致
  // （Codex P2 fix，2026-07）。
  // 101b-T2 曾把 state-lightbox.js 加入白名單（settle timeline 直接呼叫 gsap）——Codex PR#110
  // P2-2 指出「整檔 exclude」讓該 2000+ 行檔未來任何直接 gsap 呼叫都靜默放行。修正：把
  // _maskStartSettle/_maskClearSettleProps 的 GSAP 編排移入 ghost-fly.js（shared/，已是 focal
  // 動畫家族的家，不在 pages 掃描範圍），state-lightbox.js 現零直接 gsap 呼叫，故移出白名單、
  // 恢復守衛覆蓋（未來任何回潮直接 gsap 會被此規則擋下）。
  {
    file: {
      dir: 'web/static/js/pages', ext: ['.js'], recursive: true,
      exclude: [
        'motion-lab.js',
        'motion-lab-state.js',
        'search/animations.js',
        'showcase/animations.js',
        'motion-lab/constellation-host.js',
        'showcase/state-similar.js',
      ],
    },
    kind: 'forbidden-string',
    pattern: /(?:gsap\.(?:to|from|fromTo|set|timeline)\(|ScrollTrigger\.(?:create|batch)\()/,
    note: '[TestMotionInfra] test_no_direct_gsap_calls_in_pages — pages/**/*.js 禁直接 GSAP/ScrollTrigger 呼叫（白名單 7 檔 exclude by-relpath）',
  },
  {
    file: { dir: 'web/static/js/components', ext: ['.js'], recursive: true, exclude: ['motion-adapter.js'] },
    kind: 'forbidden-string',
    pattern: /(?:gsap\.(?:to|from|fromTo|set|timeline)\(|ScrollTrigger\.(?:create|batch)\()/,
    note: '[TestMotionInfra] test_no_direct_gsap_calls_in_pages — components/**/*.js 禁直接 GSAP/ScrollTrigger 呼叫（motion-adapter.js 白名單 exclude by-relpath）',
  },

  // ==== 96b-T6 Phase 1：orphan-net-gap 補網（TASK-96b-T6.md §C，Opus-resolved 決策 (a)）====
  // TestMotionInfra 的 test_motion_js_files_contain / test_base_html_loads_gsap_and_adapters 兩個
  // method 從未被 T1-T5 任一張卡建網（T1 的 14-class 清單未列入，T2/T3/T4/T5 亦未補），是橫跨 5 個
  // task 的協調斷點。本節依 CD-96b-9 補齊，讓 TestMotionInfra 全部 3 method 皆有替代網後才可整刪。

  // ---- [TestMotionInfra] test_motion_js_files_contain — motion-prefs.js / motion-adapter.js 必要 API 字串 ----
  { file: 'web/static/js/components/motion-prefs.js', kind: 'required-string', pattern: 'prefersReducedMotion', note: '[TestMotionInfra] test_motion_js_files_contain — motion-prefs.js API' },
  { file: 'web/static/js/components/motion-prefs.js', kind: 'required-string', pattern: 'openaver:motion-pref-change', note: '[TestMotionInfra] test_motion_js_files_contain — motion-prefs.js API' },
  { file: 'web/static/js/components/motion-prefs.js', kind: 'required-string', pattern: 'addListener', note: '[TestMotionInfra] test_motion_js_files_contain — motion-prefs.js API' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'createContext', note: '[TestMotionInfra] test_motion_js_files_contain — motion-adapter.js API' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'playEnter', note: '[TestMotionInfra] test_motion_js_files_contain — motion-adapter.js API' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'playLeave', note: '[TestMotionInfra] test_motion_js_files_contain — motion-adapter.js API' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'playStagger', note: '[TestMotionInfra] test_motion_js_files_contain — motion-adapter.js API' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'playModal', note: '[TestMotionInfra] test_motion_js_files_contain — motion-adapter.js API' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: '_shouldAnimate', note: '[TestMotionInfra] test_motion_js_files_contain — motion-adapter.js API' },

  // ---- [TestMotionInfra] test_base_html_loads_gsap_and_adapters — base.html 載入 4 個 script 且順序正確 ----
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'gsap.min.js', note: '[TestMotionInfra] test_base_html_loads_gsap_and_adapters — base.html script' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'motion-prefs.js', note: '[TestMotionInfra] test_base_html_loads_gsap_and_adapters — base.html script' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'motion-adapter.js', note: '[TestMotionInfra] test_base_html_loads_gsap_and_adapters — base.html script' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'alpine.min.js', note: '[TestMotionInfra] test_base_html_loads_gsap_and_adapters — base.html script' },
  {
    file: 'web/templates/base.html', kind: 'order',
    items: [
      { pattern: 'gsap.min.js' },
      { pattern: 'motion-prefs.js' },
      { pattern: 'motion-adapter.js' },
      { pattern: 'alpine.min.js' },
    ],
    note: '[TestMotionInfra] test_base_html_loads_gsap_and_adapters — 載入順序 gsap < motion-prefs < motion-adapter < alpine（4-anchor 鏈式）',
  },

  // ---- [TestEventSourceTracking] test_event_source_tracking_js_contains — 從未被 T1-T5 任一張卡建網
  // （T5 只建了 forbidden 半邊 eslint SEL_TRACKED_EVENTSOURCE，required 半邊是本卡發現的第二個
  // orphan-net-gap），本節補齊 required 半邊後 class 全部 2 method 皆有替代網。 ----
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_activeConnections', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — base.js connection registry' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_trackConnection', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — search-flow.js tracking methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_untrackConnection', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — search-flow.js tracking methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_closeAllConnections', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — search-flow.js tracking methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_trackConnection(new EventSource(', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — search-flow.js tracking methods' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: '_closeAllConnections()', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — search-flow.js tracking methods' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string', pattern: '_trackConnection(', note: '[TestEventSourceTracking] test_event_source_tracking_js_contains — file-list.js tracking method' },

  // ---- [TestOpenAIErrorI18nGuard] settings/state-providers.js：openai error 分支使用 window.t(errorKey)
  // i18n，非裸 error.message（39a-PR-fix P1）。實測全部 3 個 method 皆 required-string 正斷言，
  // 無任何 forbidden 半邊 —— 正確歸屬 static_guard_lint required-string，不是 eslint
  // SEL_NO_ERR_IN_ALERT 的來源（Opus-resolved 決策 2 / TASK-96b-T4.md §3.2 修正 inventory 誤判）。
  {
    file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string', pattern: 'settings.status.openai_',
    scope: { anchor: /async\s+fetchOpenAIModels\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestOpenAIErrorI18nGuard] test_fetch_models_error_uses_i18n — fetchOpenAIModels() error 分支含 settings.status.openai_ 動態 errorKey 拼接',
  },
  {
    file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string', pattern: 'settings.status.openai_',
    scope: { anchor: /async\s+testOpenAITranslation\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestOpenAIErrorI18nGuard] test_translate_error_uses_i18n — testOpenAITranslation() error 分支含 settings.status.openai_ 動態 errorKey 拼接',
  },
  {
    file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string',
    pattern: "window.t('settings.status.openai_connection_failed')",
    note: "[TestOpenAIErrorI18nGuard] test_fetch_catch_uses_i18n — fetchOpenAIModels() catch 分支使用 window.t('settings.status.openai_connection_failed')，不顯示裸 error.message",
  },

  // ---- [TestNoDuplicateNativeDialog::test_duplicate_modal_uses_modal_open_class] search.html
  // 含 duplicateModalOpen（Alpine state-driven pattern）。實測目標是 HTML required-string
  // （非 JS、非 forbidden），eslint 只吃 .js 檔管不到 HTML —— 此 required-string 半邊 +
  // eslint SEL_SHOW_MODAL（universal ban，本 task 已泛化）兩者合力才是完整替代網（見
  // TASK-96b-T4.md §1a）。此列補齊此前遺漏的 required-string 半邊（gap-fill）。
  {
    file: 'web/templates/search.html', kind: 'required-string', pattern: 'duplicateModalOpen',
    note: '[TestNoDuplicateNativeDialog] test_duplicate_modal_uses_modal_open_class — search.html 含 duplicateModalOpen（Alpine state pattern，非原生 showModal/close）',
  },

  // ==== 96b-T5（Opus-resolved 決策 2）：SEL_CROPMODE_LITERAL — port 自
  // tests/unit/test_ghost_fly_cropmode.py::TestGhostFlyCropModeBoundary（3 method） ====
  // 規則 1+2：cropMode / 'right-half' 只能出現在 shared/ghost-fly.js（定義站）+
  // pages/showcase/state-similar.js（CROPMODE_CALLER_WHITELIST 唯一白名單 caller，經 GhostFly API）。
  // state-lightbox.js / state-base.js 不在此白名單內（它們屬於下面規則 3 的獨立掃描名單，
  // plan 文字曾誤讀成同一份白名單，本卡已用 grep 驗證全 repo 目前只有 ghost-fly.js /
  // state-similar.js 兩檔含這些字串）。exclude 比對「相對於 dir 的相對路徑」（非 basename）：
  // basename 比對會讓未來新增的同名檔（如另一份 state-similar.js）誤放行，改用完整相對路徑
  // 與來源 pytest CROPMODE_CALLER_WHITELIST 語意一致（Codex P2 fix，2026-07）。
  {
    file: { dir: 'web/static/js', ext: ['.js'], recursive: true, exclude: ['shared/ghost-fly.js', 'pages/showcase/state-similar.js'] },
    kind: 'forbidden-string', pattern: 'cropMode',
    note: '[TestGhostFlyCropModeBoundary] test_cropmode_string_only_in_ghost_fly — cropMode 只能出現在 ghost-fly.js（定義站）/ state-similar.js（白名單 caller，exclude by-relpath）',
  },
  {
    file: { dir: 'web/static/js', ext: ['.js'], recursive: true, exclude: ['shared/ghost-fly.js', 'pages/showcase/state-similar.js'] },
    kind: 'forbidden-string', pattern: ["'right-half'", '"right-half"'],
    note: '[TestGhostFlyCropModeBoundary] test_right_half_literal_only_in_ghost_fly — right-half 字面量只能出現在 ghost-fly.js（定義站）/ state-similar.js（白名單 caller，exclude by-relpath）',
  },
  // 規則 3：state-lightbox.js / state-base.js 禁 objectPosition...right（同一行）。
  // state-similar.js 在 pytest 是 CALLER_SCOPE_FILES 的一員但因白名單命中而 pytest.skip，
  // 不建列（與白名單語意一致，不對它重複套用此禁令）。
  ...LIGHTBOX_SLICE_FILES.map((f) => ({
    file: f, kind: 'forbidden-string',
    pattern: /objectPosition[^\n]*right/,
    note: '[TestGhostFlyCropModeBoundary] test_caller_scope_no_object_position_right (state-lightbox.js) — 禁自算 objectPosition: right，須走 createCoverGhost(..., { cropMode })（149a：五個分片同禁）',
  })),
  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: /^import\s*\{[^}]*\bcomputeMaskSettleGeometry\b[^}]*\}\s*from\s*'@\/shared\/mask-geometry\.js'/m,
    note: '[TestShowcaseESMGuard] state-lightbox-mask.js 必須 import computeMaskSettleGeometry——'
        + 'no-undef 全域關閉（eslint.config.mjs:284，Alpine runtime global），'
        + '裸識別字 required-string 會被呼叫點矇混（:1592 實測過同一種壞形狀），只有鎖 import 陳述式才守得住' },
  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: /^import\s*\{[^}]*\bparseFocal\b[^}]*\}\s*from\s*'@\/shared\/focal\.js'/m,
    note: '[TestMaskToggleGuard] state-lightbox-mask.js 必須 import parseFocal——'
        + 'no-undef 全域關閉（eslint.config.mjs:284），裸識別字 required-string 會被呼叫點矇混，'
        + '只有鎖 import 陳述式才守得住' },
  { file: 'web/static/js/pages/showcase/state-lightbox-mask.js', kind: 'required-string',
    pattern: /^import\s*\{[^}]*\bclampMaskWinLeft\b[^}]*\}\s*from\s*'@\/shared\/focal\.js'/m,
    note: '[TestMaskToggleGuard] state-lightbox-mask.js 必須 import clampMaskWinLeft——'
        + 'no-undef 全域關閉（eslint.config.mjs:284），裸識別字 required-string 會被呼叫點矇混，'
        + '只有鎖 import 陳述式才守得住' },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'forbidden-string',
    pattern: /objectPosition[^\n]*right/,
    note: '[TestGhostFlyCropModeBoundary] test_caller_scope_no_object_position_right (state-base.js) — 禁自算 objectPosition: right，須走 createCoverGhost(..., { cropMode })',
  },

  // ==== 96b-T5（額外港入，補 §3.1 缺口）：TestLongPressTouchSuppression 的
  // test_grid_enrich_btn_longpress_retired / test_lightbox_enrich_btn_longpress_retired
  // 兩個 HTML tag-scoped method（submit btn + switchSourceBtn 兩條已由 T1 覆蓋，見既有
  // TestSearchSubmitBtnNoLongPress / TestSwitchSourceBtnRemoved rows）。使
  // TestLongPressTouchSuppression 全部 4 method 皆有替代網，供 T6 安全整刪。 ====
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'button', className: 'enrich-btn',
    forbidden: [
      'longPressStart', 'longPressEnd', 'longPressCancel', 'longPressClickGuard',
      '@mousedown', '@mouseup', '@mouseleave', '@touchstart', '@touchend', '@touchcancel',
    ],
    required: ['@click.stop="enrichVideo(video)"'],
    note: '[TestLongPressTouchSuppression] test_grid_enrich_btn_longpress_retired — grid .btn-glass-circle.enrich-btn 已無長壓接線，tap=enrichVideo(video)',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<button\b(?=[^>]*class="lb-action-btn")(?=[^>]*enrichVideo\(currentLightboxVideo\))[^>]*>/,
    forbidden: [
      'longPressStart', 'longPressEnd', 'longPressCancel', 'longPressClickGuard',
      '@mousedown', '@mouseup', '@mouseleave', '@touchstart', '@touchend', '@touchcancel',
    ],
    required: ['@click.stop="enrichVideo(currentLightboxVideo)"'],
    note: '[TestLongPressTouchSuppression] test_lightbox_enrich_btn_longpress_retired — lightbox .lb-action-btn（enrichVideo(currentLightboxVideo)）已無長壓接線',
  },

  // ==== 96d-T1：rescrape 家族遷移（TASK-96d-T1.md，10 live pytest class 非-CSS 半邊）====

  // ---- [TestSimilarStageGuard] state-similar.js 整合 contract（57c-T4+T5）----
  { file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: "from '@/showcase/state-similar.js'", note: "[TestSimilarStageGuard] test_main_js_imports_and_merges_state_similar — main.js import state-similar" },
  { file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: 'stateSimilar.call(this)', note: '[TestSimilarStageGuard] test_main_js_imports_and_merges_state_similar — main.js mergeState chain' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'export const SIMILAR_ANCHORS', note: '[TestSimilarStageGuard] test_state_similar_exports_similar_anchors' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: /export\s+function\s+stateSimilar\s*\(/, note: '[TestSimilarStageGuard] test_state_similar_exposes_similar_mode_methods — stateSimilar factory export' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'openSimilarMode', note: '[TestSimilarStageGuard] test_state_similar_exposes_similar_mode_methods — 4 主流程 method' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'closeSimilarMode', note: '[TestSimilarStageGuard] test_state_similar_exposes_similar_mode_methods — 4 主流程 method' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'initSimilarStage', note: '[TestSimilarStageGuard] test_state_similar_exposes_similar_mode_methods — 4 主流程 method' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'destroySimilarStage', note: '[TestSimilarStageGuard] test_state_similar_exposes_similar_mode_methods — 4 主流程 method' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'similar-stage', note: '[TestSimilarStageGuard] test_similar_stage_sibling_dom_in_showcase_html — sibling DOM backdrop class' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'initSimilarStage()', note: '[TestSimilarStageGuard] test_similar_stage_sibling_dom_in_showcase_html — x-effect lifecycle init' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'destroySimilarStage()', note: '[TestSimilarStageGuard] test_similar_stage_sibling_dom_in_showcase_html — x-effect lifecycle destroy' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'similar-stage-inner', note: '[TestSimilarStageGuard] test_similar_stage_sibling_dom_in_showcase_html — 960x620 inner stage' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'SIMILAR_ANCHORS', note: '[TestSimilarStageGuard] test_similar_stage_sibling_dom_in_showcase_html — x-for anchor 對齊 export' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: 'slot-icon-overlay', note: '[TestSimilarStageGuard] test_no_slot_icon_overlay_in_templates (showcase.html)' },
  { file: 'web/templates/motion_lab.html', kind: 'forbidden-string', pattern: 'slot-icon-overlay', note: '[TestSimilarStageGuard] test_no_slot_icon_overlay_in_templates (motion_lab.html)' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: /\b(?:on|play|build|calc|destroy|init|open|close)Clip[A-Z]/, note: '[TestSimilarStageGuard] test_no_clip_alpine_methods_in_showcase_and_similar — showcase.html 半邊（state-similar.js 半邊由 eslint SEL_CLIP_METHOD_IDENT 覆蓋，Group 5b）' },

  // ---- [TestSimilarMainStaticFocalOrder] Codex PR#107 P2：_buildSimilarMainStatic 內
  //   stageInner.appendChild(img) 必須在 applyFocalToImg(img, ...) 之前——applyCellFocal 對
  //   已快取封面走同步分支，當場 getComputedStyle 讀 --poster-crop-ratio（:root 變數），
  //   detached element 讀不到 inherited custom property（回空字串 → parseFloat NaN），
  //   會誤清 objectPosition。時序修法，非旗標繞過。 ----
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'order',
    scope: { anchor: /(?:^|\n)\s*_buildSimilarMainStatic\s*\([^)]*\)\s*\{/, braceBalanced: true },
    items: [
      { pattern: /stageInner\.appendChild\(img\)/ },
      { pattern: /this\.applyFocalToImg\(img,\s*this\.currentLightboxVideo\)/ },
    ],
    note: '[TestSimilarMainStaticFocalOrder] appendChild(img) 必須在 applyFocalToImg(img, ...) 之前（避免 detached element getComputedStyle 讀不到 --poster-crop-ratio）',
  },

  // ---- [TestRescrapeEntryGuard] showcase ⚙ gear 唯一進階重刮入口（62b-1 → 74b US4 → 74c-T1/T3）----
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /<button[^>]*\bclass="lb-rescrape-gear"[^>]*>\s*<i[^>]*\bbi-gear\b/,
    note: '[TestRescrapeEntryGuard] test_gear_has_bi_gear_icon — ⚙ gear button 內必須含 bi-gear icon',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: "openRescrape(currentLightboxVideo, 'lightbox')",
    scope: /<button\b[^>]*?\bclass="lb-rescrape-gear".*?<\/button>/s,
    note: "[TestRescrapeEntryGuard] test_gear_opens_rescrape_lightbox — ⚙ @click 必須 openRescrape(currentLightboxVideo, 'lightbox')",
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: /x-show="[^"]*"/,
    scope: /<button\b[^>]*?\bclass="lb-rescrape-gear".*?<\/button>/s,
    note: '[TestRescrapeEntryGuard] test_gear_gated_by_rescrape_enabled — 74c-T1：⚙ 齒輪已退役 x-show gate（negative 半邊）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: "openRescrape(currentLightboxVideo, 'lightbox')",
    scope: /<button\b[^>]*?\bclass="lb-rescrape-gear".*?<\/button>/s,
    note: "[TestRescrapeEntryGuard] test_gear_gated_by_rescrape_enabled — @click 仍在（齒輪行為不變，positive 半邊，冗餘但忠實 port）",
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: "t('showcase.rescrape.entry_tooltip')",
    scope: /<button\b[^>]*?\bclass="lb-rescrape-gear".*?<\/button>/s,
    note: '[TestRescrapeEntryGuard] test_gear_tooltip_uses_i18n_key — ⚙ 用 i18n key，不硬編碼',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', pattern: /[\s:]aria-label="[^"]*entry_tooltip/,
    scope: /<button\b[^>]*?\bclass="lb-rescrape-gear".*?<\/button>/s,
    note: '[TASK-104-T4] test_gear_tooltip_uses_i18n_key — ⚙ 缺 aria-label（可及性）；104-T4 移除 readonly 三元後改靜態 Jinja 屬性（原僅接受 Alpine `:aria-label` 動態綁定，拓寬比對前綴涵蓋兩種形式）。round-3 P3：改用 `[\\s:]` 前綴取代 `\\b`（`-` 也是 word-boundary，`\\baria-label` 會誤過 `data-aria-label`）',
  },
  { file: 'web/static/js/shared/long-press.js', kind: 'file-absent', note: '[TestRescrapeEntryGuard] test_long_press_helper_retired — 74c-T3：long-press.js 已刪除，不得再存在' },
  { file: 'web/static/js/pages/showcase/main.js', kind: 'forbidden-string', pattern: "from '@/shared/long-press.js'", note: '[TestRescrapeEntryGuard] test_main_js_imports_and_merges_long_press — showcase main.js 已移除 long-press import' },
  { file: 'web/static/js/pages/showcase/main.js', kind: 'forbidden-string', pattern: 'longPressState', note: '[TestRescrapeEntryGuard] test_main_js_imports_and_merges_long_press — showcase main.js 已移除 longPressState 接線' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string', pattern: 'rescrapeEnabled', note: '[TestRescrapeEntryGuard] test_rescrape_enabled_method_in_mixin — 74c-T1：rescrapeEnabled() 已退役' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'window.__ADVANCED_SEARCH__', note: '[TestRescrapeEntryGuard] test_rescrape_enabled_method_in_mixin — window.__ADVANCED_SEARCH__ 仍在（sources/proxy/CF live 消費者）' },

  // ---- [TestSearchRescrapeEntryGuard] Search 進階搜尋入口改用 62a 共用重刮彈窗（62c-1）----
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: "from '@/shared/state-rescrape.js'", note: '[TestSearchRescrapeEntryGuard] test_search_main_imports_rescrape_state — search main.js import rescrapeState' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: /rescrapeState\s*\(/, note: '[TestSearchRescrapeEntryGuard] test_search_main_imports_rescrape_state — search main.js mergeState chain' },
  { file: 'web/static/js/pages/search/main.js', kind: 'forbidden-string', pattern: "from '@/shared/long-press.js'", note: '[TestSearchRescrapeEntryGuard] test_search_main_imports_long_press_state — 74c-T3：search main.js 已移除 long-press import' },
  { file: 'web/static/js/pages/search/main.js', kind: 'forbidden-string', pattern: 'longPressState', note: '[TestSearchRescrapeEntryGuard] test_search_main_imports_long_press_state — 74c-T3：search main.js 已移除 longPressState' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "{% include '_rescrape_modal.html' %}", note: '[TestSearchRescrapeEntryGuard] test_search_html_includes_rescrape_modal' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedPickerModal', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_picker_modal — B1 picker DOM 整塊已移除' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedPickerConfirm', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_picker_modal — B1 picker DOM 整塊已移除' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedPickerSelected', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_picker_modal — B1 picker DOM 整塊已移除' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedPickerClose', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_picker_modal — B1 picker DOM 整塊已移除' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedPickerBuiltinSources', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_picker_modal — B1 picker DOM 整塊已移除' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedPickerMetatubeSources', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_picker_modal — B1 picker DOM 整塊已移除' },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@mousedown',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_longpress_retired_for_auto_pill — #btnSubmit 不應再有 @mousedown 長壓 wiring',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressStart',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_longpress_retired_for_auto_pill — #btnSubmit 不應再接 longPressStart',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@mousedown',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_six_events_retired — #btnSubmit 六長壓事件全移除',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@mouseup',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_six_events_retired — #btnSubmit 六長壓事件全移除',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@mouseleave',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_six_events_retired — #btnSubmit 六長壓事件全移除',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@touchstart',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_six_events_retired — #btnSubmit 六長壓事件全移除',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@touchend',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_six_events_retired — #btnSubmit 六長壓事件全移除',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@touchcancel',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_six_events_retired — #btnSubmit 六長壓事件全移除',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: '@click',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_click_guard_retired — #btnSubmit 不應再有 @click（回歸純 type="submit"）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressClickGuard',
    scope: /<button\b(?:(?!<\/button>).)*?\bid="btnSubmit"(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSearchRescrapeEntryGuard] test_submit_btn_click_guard_retired — #btnSubmit 不應再含 longPressClickGuard',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedLongPressSubmitGuard',
    scope: /<form\b[^>]*\bid="searchForm"[^>]*@submit\.prevent="([^"]*)"/,
    note: '[TestSearchRescrapeEntryGuard] test_form_submit_guard_removed — form @submit 不應再含 advancedLongPressSubmitGuard',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string', pattern: 'doSearch()',
    scope: /<form\b[^>]*\bid="searchForm"[^>]*@submit\.prevent="([^"]*)"/,
    note: '[TestSearchRescrapeEntryGuard] test_form_submit_guard_removed — form @submit 應直接走 doSearch()',
  },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedLongPressStart', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_long_press_wiring' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedLongPressEnd', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_long_press_wiring' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedLongPressCancel', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_long_press_wiring' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedLongPressClickGuard', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_long_press_wiring' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'advancedLongPressSubmitGuard', note: '[TestSearchRescrapeEntryGuard] test_search_html_no_advanced_long_press_wiring' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedLongPressStart', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedLongPressEnd', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedLongPressCancel', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedLongPressClickGuard', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedLongPressSubmitGuard', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: '_advancedLongPressFired', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: '_advancedLongPressTimer', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'LONG_PRESS_MS', note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — 整套 advancedLongPress* mixin 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'required-string', pattern: /async\s+advancedSearch\s*\(/, note: '[TestSearchRescrapeEntryGuard] test_picker_long_press_mixin_removed — advancedSearch(source) 本體保留' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedPickerOpen', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedPickerSelected', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedPickerClose', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedPickerConfirm', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedPickerBuiltinSources', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: 'advancedPickerMetatubeSources', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'forbidden-string', pattern: '_advancedSortedSources', note: '[TestSearchRescrapeEntryGuard] test_picker_dead_methods_removed — B1 picker-modal 專屬 method 已移除' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'advancedSearch(', note: '[TestSearchRescrapeEntryGuard] test_search_branch_uses_advanced_search — search 分支成功路徑必須走 advancedSearch(' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: /rescrapeEntryPoint\s*===\s*'search'/, note: '[TestSearchRescrapeEntryGuard] test_search_branch_uses_advanced_search — 以 rescrapeEntryPoint === \'search\' 分流' },
  // 註：test_search_branch_no_fallback_search（"fallbackSearch" not in src）已由既有 eslint
  // Group 7（shared/state-rescrape.js）的 SEL selector `CallExpression[callee.property.name='fallbackSearch']`
  // 覆蓋，不新增 RULES 列（見 TASK-96d-T1.md §3 row 46 disposition）。
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "{% include '_advanced_search_bootstrap.html' %}", note: '[TestSearchRescrapeEntryGuard] test_bootstrap_include_not_regressed — 不回歸 62a-0：search.html 仍 include bootstrap' },

  // ---- [TestSwitchSourcePickGuard] 結果面板 🔄 長壓挑來源 wiring + entryPoint 分支 + 番號可編輯（62c-3 US7）----
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'id="switchSourceBtn"', note: '[TestSwitchSourcePickGuard] test_switch_source_btn_retired — TASK-74a-T3：#switchSourceBtn 整顆退役' },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressStart',
    scope: /<button\b(?:(?!<\/button>).)*?openSourceUrl(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSwitchSourcePickGuard] test_open_source_url_btn_not_touched — ↗ openSourceUrl 鈕不得沾長壓 wiring',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressEnd',
    scope: /<button\b(?:(?!<\/button>).)*?openSourceUrl(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSwitchSourcePickGuard] test_open_source_url_btn_not_touched — ↗ openSourceUrl 鈕不得沾長壓 wiring',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressCancel',
    scope: /<button\b(?:(?!<\/button>).)*?openSourceUrl(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSwitchSourcePickGuard] test_open_source_url_btn_not_touched — ↗ openSourceUrl 鈕不得沾長壓 wiring',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'longPressClickGuard',
    scope: /<button\b(?:(?!<\/button>).)*?openSourceUrl(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSwitchSourcePickGuard] test_open_source_url_btn_not_touched — ↗ openSourceUrl 鈕不得沾長壓 wiring',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'openSwitchSourcePicker',
    scope: /<button\b(?:(?!<\/button>).)*?openSourceUrl(?:(?!<\/button>).)*?<\/button>/s,
    note: '[TestSwitchSourcePickGuard] test_open_source_url_btn_not_touched — ↗ openSourceUrl 鈕不得沾長壓 wiring',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: /(?::readonly|\breadonly)\b/,
    scope: /<input\b(?:(?!>).)*?\bclass="rescrape-num-input"(?:(?!>).)*?>/s,
    note: '[TestSwitchSourcePickGuard] test_number_input_editable_in_all_entry_points — 番號 input 不得有 readonly / :readonly 綁定（2026-05-31 放開唯讀）',
  },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: /openSwitchSourcePicker\s*\(\s*\)\s*\{/, note: '[TestSwitchSourcePickGuard] test_open_switch_source_picker_method_present — openSwitchSourcePicker method' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: /openRescrape\(\s*null\s*,\s*'switch-source'\s*\)/, note: "[TestSwitchSourcePickGuard] test_open_switch_source_picker_method_present — openRescrape(null,'switch-source')" },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: '_switchTarget', note: '[TestSwitchSourcePickGuard] test_open_switch_source_picker_method_present — _switchTarget（race 防覆蓋錯卡）' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: /rescrapeEntryPoint\s*===\s*'switch-source'/, note: '[TestSwitchSourcePickGuard] test_switch_source_branch_present — rescrapeEntryPoint === \'switch-source\' 分流' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'seedSwitchState', note: '[TestSwitchSourcePickGuard] test_switch_source_branch_present — switch-source 分支呼叫 window.SearchUI.seedSwitchState' },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'switch-source',
    scope: /rescrapeEntryPoint\s*:\s*'lightbox'\s*,\s*\/\/([^\n]*)/,
    note: "[TestSwitchSourcePickGuard] test_entry_point_comment_lists_switch_source — rescrapeEntryPoint 宣告行末註解須列出 'switch-source'",
  },
  { file: 'web/static/js/pages/search/ui.js', kind: 'required-string', pattern: /function\s+seedSwitchState\s*\(/, note: '[TestSwitchSourcePickGuard] test_ui_exports_seed_switch_state — seedSwitchState 函式定義' },
  {
    file: 'web/static/js/pages/search/ui.js', kind: 'required-string', pattern: 'seedSwitchState',
    scope: /window\.SearchUI\s*=\s*\{([^}]*)\}/s,
    note: '[TestSwitchSourcePickGuard] test_ui_exports_seed_switch_state — window.SearchUI 必須 export seedSwitchState',
  },

  // ---- [TestSwitchSourceAutoCycle] picker「自動」pill 直接走 switchSource() 循環（TASK-74a-T4 US2）----
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'closeRescrape(',
    scope: /rescrapeEntryPoint\s*===\s*'switch-source'\s*&&\s*sourceId\s*===\s*'auto'\s*\)\s*\{(.*?)\}/s,
    note: '[TestSwitchSourceAutoCycle] test_switch_source_auto_short_circuit_branch_present — short-circuit 分支內須呼叫 closeRescrape()',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'switchSource(',
    scope: /rescrapeEntryPoint\s*===\s*'switch-source'\s*&&\s*sourceId\s*===\s*'auto'\s*\)\s*\{(.*?)\}/s,
    note: '[TestSwitchSourceAutoCycle] test_switch_source_auto_short_circuit_branch_present — short-circuit 分支內須呼叫 switchSource()',
  },

  // ---- [TestRescrapeSourcesSeededAtInit] 結果面板來源膠囊 rescrapeSources 需 init 就有料（TASK-74a-T5 US2 修）----
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'window.__ADVANCED_SEARCH__',
    scope: /^\s*rescrapeSources:\s*(.+?),\s*$/m,
    note: '[TestRescrapeSourcesSeededAtInit] test_rescrape_sources_initializer_seeds_from_bootstrap — 初始化器須從 window.__ADVANCED_SEARCH__.sources 灌入',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'sources',
    scope: /^\s*rescrapeSources:\s*(.+?),\s*$/m,
    note: '[TestRescrapeSourcesSeededAtInit] test_rescrape_sources_initializer_seeds_from_bootstrap — 初始化器須從 window.__ADVANCED_SEARCH__.sources 灌入',
  },

  // ---- [TestRescrapePreviewSourcePill] 換源預覽 flat 唯讀膠囊 template contract（TASK-74b-T2 US3）----
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: "{% from '_macros/source_pill.html' import source_pill %}", note: '[TestRescrapePreviewSourcePill] test_macro_import_present' },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrape-preview-source-pill',
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: '[TestRescrapePreviewSourcePill] _preview_pill_call helper — 錨定抽出的 macro 呼叫確實是 preview 膠囊（防抓錯 pill）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: /variant\s*=\s*'flat'/,
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: "[TestRescrapePreviewSourcePill] test_preview_pill_is_flat_variant — preview 膠囊必須 variant='flat'（唯讀）",
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrapePreview && rescrapePreview.sourceName',
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: '[TestRescrapePreviewSourcePill] test_preview_pill_name_null_safe — name 必須 null-safe（CD-74b-11）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', anyOf: true,
    pattern: ['tabindex=\\"-1\\"', 'tabindex="-1"'],
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: '[TestRescrapePreviewSourcePill] test_preview_pill_readonly_attrs — tabindex=-1（唯讀移出 tab 序，含跳脫變體 OR）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'source-pill--uncensored',
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: '[TestRescrapePreviewSourcePill] test_preview_pill_readonly_attrs — 動態 uncensored :class（依 sourceCensored）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'sourceCensored',
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: '[TestRescrapePreviewSourcePill] test_preview_pill_readonly_attrs — 動態 uncensored :class（依 sourceCensored）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: '@click',
    scope: /\{\{\s*source_pill\((.*?)\)\s*\}\}/s,
    note: '[TestRescrapePreviewSourcePill] test_preview_pill_readonly_attrs — preview 膠囊唯讀，不得有 @click',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string',
    pattern: '&nbsp;·&nbsp;<span x-text="rescrapePreview && rescrapePreview.sourceName"',
    note: '[TestRescrapePreviewSourcePill] test_old_plaintext_source_removed — 舊純文字 span 已移除',
  },

  // ---- [TestRescrapePreviewEffectiveSource] rescrapePreview 組裝算 effective source + sourceCensored（TASK-74b-T2 US3）----
  // ⚠ 雙 scope：Scope-Whole（無 capture group，取 match[0]）vs Scope-Body（含 capture group，取
  // match[1]）——同一段原始 pytest _assembly() 回傳 (whole, body) 兩種擷取，不可共用同一 regex 物件
  // （見 TASK-96d-T1.md §8）。
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: "sourceId === 'auto'",
    scope: /const previewSourceId =[\s\S]*?this\.rescrapePreview = \{[\s\S]*?\};/,
    note: "[TestRescrapePreviewEffectiveSource] test_effective_source_auto_branch — previewSourceId 在 auto 時取 data._source（Scope-Whole）",
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'data._source',
    scope: /const previewSourceId =[\s\S]*?this\.rescrapePreview = \{[\s\S]*?\};/,
    note: '[TestRescrapePreviewEffectiveSource] test_effective_source_auto_branch — previewSourceId 在 auto 時取 data._source（Scope-Whole）',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: '_resolveSourceName(previewSourceId)',
    scope: /const previewSourceId =[\s\S]*?this\.rescrapePreview = \{([\s\S]*?)\};/s,
    note: '[TestRescrapePreviewEffectiveSource] test_source_name_uses_effective_id — sourceName 用 previewSourceId 解析（Scope-Body）',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'sourceCensored',
    scope: /const previewSourceId =[\s\S]*?this\.rescrapePreview = \{([\s\S]*?)\};/s,
    note: '[TestRescrapePreviewEffectiveSource] test_source_censored_field — rescrapePreview 加 sourceCensored 欄位（Scope-Body）',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'is_censored',
    scope: /const previewSourceId =[\s\S]*?this\.rescrapePreview = \{([\s\S]*?)\};/s,
    note: '[TestRescrapePreviewEffectiveSource] test_source_censored_field — rescrapePreview 加 sourceCensored 欄位（Scope-Body）',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: '?? true',
    scope: /const previewSourceId =[\s\S]*?this\.rescrapePreview = \{([\s\S]*?)\};/s,
    note: '[TestRescrapePreviewEffectiveSource] test_source_censored_field — 找不到 source → ?? true（藍 fallback，Scope-Body）',
  },

  // ---- [TestRescrapeModalGuard] 進階重刮彈窗 partial 結構 / i18n / include（非-CSS 半邊，96c CG-XP-01 已建 CSS 半邊）----
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: "rescrapeStep === 'pick'", note: '[TestRescrapeModalGuard] test_partial_two_step_structure — pick step' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: "rescrapeStep === 'preview'", note: '[TestRescrapeModalGuard] test_partial_two_step_structure — preview step' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'class="modal fluent-modal', note: '[TestRescrapeModalGuard] test_partial_uses_fluent_modal_pattern — 沿用 modal fluent-modal class' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: "{ 'modal-open': rescrapeOpen }", note: "[TestRescrapeModalGuard] test_partial_uses_fluent_modal_pattern — :class=\"{ 'modal-open': rescrapeOpen }\" 開關" },
  { file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: '.showModal()', note: '[TestRescrapeModalGuard] test_partial_uses_fluent_modal_pattern — 不應使用原生 .showModal()' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'source-pill source-pill--action', note: '[TestRescrapeModalGuard] test_partial_uses_source_pill_action_class' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'x-for="s in rescrapeMetatubeSources()"', note: '[TestRescrapeModalGuard] test_metatube_group_is_data_driven — Metatube 分組 data-driven' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: '<div class="rescrape-group-sep">Metatube</div>', note: '[TestRescrapeModalGuard] test_metatube_group_is_data_driven — Metatube group-sep label（品牌名不走 i18n，CD-62-12）' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'source-pill-mt-badge', note: '[TestRescrapeModalGuard] test_metatube_group_is_data_driven — metatube type badge' },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'x-show="rescrapeMetatubeSources().length === 0"',
    scope: /<div class="rescrape-empty-note"([^>]*)>/,
    note: '[TestRescrapeModalGuard] test_metatube_empty_note_is_conditional — group_metatube_empty note 條件化',
  },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: '/api/proxy-image?url=', note: '[TestRescrapeModalGuard] test_preview_img_uses_proxy_image — preview cover 走 proxy-image（CD-62-14 #8）' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'encodeURIComponent', note: '[TestRescrapeModalGuard] test_preview_img_uses_proxy_image — preview img URL encodeURIComponent' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: '/api/gallery/image', note: '[TestRescrapeModalGuard] test_preview_img_uses_proxy_image — 禁用 /api/gallery/image（給 DB file:///）' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrape-confirm-btn cancel', note: '[TestRescrapeModalGuard] test_confirm_row_has_cancel_and_confirm_buttons — ✗ 鈕' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrape-confirm-btn confirm', note: '[TestRescrapeModalGuard] test_confirm_row_has_cancel_and_confirm_buttons — ✓ 鈕' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "{% include '_rescrape_modal.html' %}", note: '[TestRescrapeModalGuard] test_showcase_includes_partial' },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"modal_title"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.modal_title',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"number_label"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.number_label',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"filename_hint"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.filename_hint',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"source_question"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.source_question',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"auto_source"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.auto_source',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"not_found"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.not_found',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"overwrite_warning"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.overwrite_warning',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"confirm"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.confirm',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"back_to_pick"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.back_to_pick',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"success"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.success',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"fail"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.fail',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"search_title"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.search_title（64a 新增）',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '"offline_tooltip"',
    scope: { anchor: /"rescrape"\s*:\s*\{/, braceBalanced: true },
    note: '[TestRescrapeModalGuard] test_zh_tw_has_rescrape_keys — showcase.rescrape.offline_tooltip（64a 新增）',
  },

  // ---- [TestSourcePillSharedComponentGuard] source pill 抽成共用 component + bootstrap partial（非-CSS 半邊，96c CG-XP-02 已建 CSS 半邊，TASK-62a-0）----
  { file: 'web/templates/base.html', kind: 'required-string', pattern: '/static/css/components/source-pill.css', note: '[TestSourcePillSharedComponentGuard] test_base_html_links_source_pill_css' },
  { file: 'web/templates/_advanced_search_bootstrap.html', kind: 'required-string', pattern: 'window.__ADVANCED_SEARCH__', note: '[TestSourcePillSharedComponentGuard] test_bootstrap_partial_exists_with_injection' },
  { file: 'web/templates/_advanced_search_bootstrap.html', kind: 'required-string', pattern: 'config.sources', note: '[TestSourcePillSharedComponentGuard] test_bootstrap_partial_exists_with_injection' },
  { file: 'web/templates/_advanced_search_bootstrap.html', kind: 'forbidden-string', pattern: 'config.advanced_search_enabled', note: '[TestSourcePillSharedComponentGuard] test_bootstrap_partial_exists_with_injection — 74c-T1：enabled 行已退役' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "{% include '_advanced_search_bootstrap.html' %}", note: '[TestSourcePillSharedComponentGuard] test_search_and_showcase_include_bootstrap (search.html)' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "{% include '_advanced_search_bootstrap.html' %}", note: '[TestSourcePillSharedComponentGuard] test_search_and_showcase_include_bootstrap (showcase.html)' },
  { file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'window.__ADVANCED_SEARCH__ =', note: '[TestSourcePillSharedComponentGuard] test_search_html_no_inline_advanced_search — 改走 include' },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: /settings-sources-pill(?!s\b)/,
    note: '[TestSourcePillSharedComponentGuard] test_settings_html_uses_source_pill_class — settings.html pill markup 改用 source-pill（派生 regex，等價原 strip-then-check：settings-sources-pills 複數容器合法保留，其餘 settings-sources-pill 前綴殘留違規）',
  },

  // ═══════════════ 96d-T2：Metatube 家族（3 pure-96d + 3 cross-plan primary=96d 非-CSS 半邊）═══════════════

  // ---- [TestMetatubeB3Guard] CD-63b-3：state-config.js STUB 移除 + 真實 fetch + helpers；settings.html 更新（11 個斷言，#5 與 TestMetatubeB4Guard#6 同 file+pattern 共用列） ----
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'STUB connect', note: '[TestMetatubeB3Guard] test_stub_connect_removed' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'STUB disconnect', note: '[TestMetatubeB3Guard] test_stub_disconnect_removed' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: "'/api/settings/metatube/connect'", note: '[TestMetatubeB3Guard] test_connect_uses_real_fetch' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: "'/api/settings/metatube/disconnect'", note: '[TestMetatubeB3Guard] test_disconnect_uses_real_fetch' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'startProbePolling', note: '[TestMetatubeB3Guard]+[TestMetatubeB4Guard] startProbePolling present — test_start_probe_polling_present / test_js_has_start_probe_polling（同 file+kind+pattern，合併單列）' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'stopProbePolling', note: '[TestMetatubeB3Guard] test_stop_probe_polling_present' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'hydrateMetatubeStatus', note: '[TestMetatubeB3Guard] test_hydrate_metatube_status_present' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'onMetatubeEnabledChange', note: '[TestMetatubeB3Guard] test_on_metatube_enabled_change_present' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'metatubeLanMode', note: '[TestMetatubeB3Guard] test_settings_html_has_metatube_lan_mode' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'metatubeConnecting', note: '[TestMetatubeB3Guard] test_settings_html_has_metatube_connecting' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'metatubeEnableToggle', note: '[TestMetatubeB3Guard] test_settings_html_has_metatube_enable_toggle' },

  // ---- [TestMetatubeB4Guard] CD-63b-4：probe UI 視覺層（進度列/retest/hint 移除/grey-out）（8 個斷言，#6 已併入 B3 上方共用列，本段物理新增 7） ----
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'mt_probe_testing', note: '[TestMetatubeB4Guard] test_html_has_mt_probe_testing_key' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'metatubeRetest', note: '[TestMetatubeB4Guard] test_html_has_metatube_retest_call' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'settings-mt-probe-hint', note: '[TestMetatubeB4Guard] test_html_has_no_probe_hint_details' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'data-available', note: '[TestMetatubeB4Guard] test_html_has_data_available_binding' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'metatubeRetest', note: '[TestMetatubeB4Guard] test_js_has_metatube_retest' },
  // test_js_has_start_probe_polling（B4#6）已與 B3#5 合併，見上方共用列。
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 's.available === false', note: '[TestMetatubeB4Guard] test_js_promote_metatube_has_available_check' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'mt_promote_unavailable_warning', note: '[TestMetatubeB4Guard] test_js_promote_metatube_has_unavailable_warning_key' },

  // ---- [118a-T9] CF 來源逐來源可用性：bootstrap 必須注入 cf_sites（per-site 快照） ----
  { file: 'web/templates/_advanced_search_bootstrap.html', kind: 'required-string', pattern: 'cf_sites', note: '[118a-T9] bootstrap 未注入 cf_sites — isJlUnavailable per-site gate 會 fallback 到全域 cf_transport_available，javten 視窗建立失敗時會連坐灰化 javlibrary' },

  // ---- [118a-T9] 不可用理由的兩個交付點各自鎖住（tooltip / toast） ----
  // 為什麼要兩條而不是一條「檔案裡有 cfUnavailableMessageKey 就好」：那是 whole-file
  // 存在性，只要其中一個綁定點退回硬編碼字面就抓不到（T9 review 實測：只把 :title 改回
  // 'showcase.rescrape.jl_desktop_only'、留 @click 正確 → 舊式斷言仍全綠）。
  // 使用者後果：hover 灰化膠囊看到「僅限桌面應用程式」但他人就在桌面版 —— 那正是本 task 要修的矛盾訊息。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: /:title="isJlUnavailable\(s\)\s*\?\s*window\.t\(cfUnavailableMessageKey\(\)\)/,
    note: '[118a-T9] builtin pill 的 :title（tooltip）未走 cfUnavailableMessageKey() — 灰化膠囊的 tooltip 會回到「僅限桌面應用程式」那句矛盾訊息',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: /@click="isJlUnavailable\(s\)\s*\?\s*showToast\(window\.t\(cfUnavailableMessageKey\(\)\)/,
    note: '[118a-T9] builtin pill 的 @click（toast）未走 cfUnavailableMessageKey() — 點擊灰化膠囊會回到「僅限桌面應用程式」那句矛盾訊息',
  },

  // ---- [TestMetatubePickerWiringGuard] 63c-3：進階 picker 接 metatube 真資料（routable gate / metatube 分組未刪，4 個斷言） ----
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'rescrapeMetatubeSources', note: '[TestMetatubePickerWiringGuard] test_state_rescrape_keeps_routable_gate — rescrapeMetatubeSources 存在' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'routable === true', note: '[TestMetatubePickerWiringGuard] test_state_rescrape_keeps_routable_gate — routable gate 保留' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: "s.type === 'metatube'", note: '[TestMetatubePickerWiringGuard] test_state_rescrape_keeps_routable_gate — type === metatube filter' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrapeMetatubeSources()', note: '[TestMetatubePickerWiringGuard] test_modal_metatube_grouping_present' },

  // ---- [TestMetatubeB5RecommendedRemoved] CD-63b-7：靜態 Recommended 群組殘留徹底拔除（10 個斷言，「推薦」locale-value forbidden-word 半邊已由 96a i18n_lint.mjs FORBIDDEN_WORDS 覆蓋，本段不重建） ----
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 's.recommended', note: '[TestMetatubeB5RecommendedRemoved] test_settings_html_no_recommended_filter' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'mt_recommended_label', note: '[TestMetatubeB5RecommendedRemoved] test_settings_html_no_recommended_i18n_keys' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'mt_other_label', note: '[TestMetatubeB5RecommendedRemoved] test_settings_html_no_recommended_i18n_keys' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'settings-mt-group-head', note: '[TestMetatubeB5RecommendedRemoved] test_settings_html_no_group_head_class' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'recommended:', note: '[TestMetatubeB5RecommendedRemoved] test_state_config_no_recommended_mock_field' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'recommended: i < 4', note: '[TestMetatubeB5RecommendedRemoved] test_state_config_no_recommended_mock_field — 與上一列同 pytest 語句的第二個字面（超集關係，逐條複製不合併，見 TASK-96d-T2.md 待審查點 3）' },
  { file: 'web/static/css/components/source-pill.css', kind: 'forbidden-string', pattern: '.rec-star', note: '[TestMetatubeB5RecommendedRemoved] test_source_pill_css_no_rec_star' },
  { file: 'web/static/css/pages/settings.css', kind: 'forbidden-string', pattern: 'settings-mt-group-head', note: '[TestMetatubeB5RecommendedRemoved] test_settings_css_no_group_head' },
  {
    file: 'locales/zh_TW.json', kind: 'forbidden-string', pattern: '"mt_recommended_label"',
    scope: { anchor: /"sources"\s*:\s*\{/, braceBalanced: true },
    note: '[TestMetatubeB5RecommendedRemoved] test_zh_tw_no_recommended_label_keys — settings.sources 範圍內（非全檔，"sources" 字面值鍵在 L220 不含 `{` 不誤配）',
  },
  {
    file: 'locales/zh_TW.json', kind: 'forbidden-string', pattern: '"mt_other_label"',
    scope: { anchor: /"sources"\s*:\s*\{/, braceBalanced: true },
    note: '[TestMetatubeB5RecommendedRemoved] test_zh_tw_no_recommended_label_keys — settings.sources 範圍內',
  },

  // ---- [163a-T6a] 設定頁 Proxy 範圍切換／空白灰化／測試鈕／拿掉「請先設定代理」攔截 ----
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: "proxyScope: 'dmm'",
    stripLineComments: true,
    note: "[163a-T6a-init] 使用者開設定頁 → 範圍鈕要有預設值「僅 DMM」才不會一片空白（form 須宣告 proxyScope: 'dmm'）",
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'this.form.proxyScope = config.search?.proxy_scope',
    stripLineComments: true,
    note: '[163a-T6a-load] 使用者存過「所有來源」→ 重開設定頁要還原，否則再按儲存就悄悄改回「僅 DMM」',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'proxy_scope: this.form.proxyScope',
    stripLineComments: true,
    note: '[163a-T6a-save] 使用者選「所有來源」按儲存 → 設定檔要真的寫入，否則封面與女優照片仍不走代理',
  },
  {
    file: 'web/templates/settings.html', kind: 'structure-count', pattern: /(?<![\w:-]):disabled="!form\.proxyUrl\.trim\(\)"/, count: 2,
    note: '[163a-T6a-disabled] Proxy 欄空白時兩顆範圍鈕都要灰掉，否則畫面看似設了範圍、實際沒有代理可走',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: /(?<![\w:-])@click="form\.proxyScope = 'dmm'"/,
    note: "[163a-T6a-bind] 使用者按「僅 DMM」要真的切過去",
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: /(?<![\w:-])@click="form\.proxyScope = 'all'"/,
    note: "[163a-T6a-bind] 使用者按「所有來源」要真的切過去，否則 NAS 的封面與女優照片無法走代理",
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'isDmmAvailable',
    note: '[163a-T6a-no-intercept-js] 使用者 Proxy 空白時點 DMM 膠囊要能開關，不得被「請先設定代理」攔住',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'requires_proxy',
    note: '[163a-T6a-no-intercept-js] 使用者 Proxy 空白時點 DMM 膠囊要能開關，不得被「請先設定代理」攔住',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'dmm_proxy_required_hint',
    note: '[163a-T6a-no-intercept-js] 使用者 Proxy 空白時點 DMM 膠囊要能開關，不得被「請先設定代理」攔住',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'isDmmAvailable',
    note: '[163a-T6a-no-intercept-tpl] 設定頁 DMM 膠囊不得因 Proxy 空白而灰化成像被停用',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'data-proxy-required',
    note: '[163a-T6a-no-intercept-tpl] 設定頁 DMM 膠囊不得因 Proxy 空白而灰化成像被停用',
  },

  // ---- [163a-T6b] 重刮視窗／搜尋頁 picker：被拒／連不到顯示紅字、拿掉「請先設定代理」攔截 ----
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'rescrapeAccessError = {',
    stripLineComments: true,
    note: '[163a-T6b-set] 使用者在重刮視窗指定 DMM、DMM 拒絕連線 → 要看到「拒絕連線」，不能只說「找不到」而讓人以為 DMM 沒這片',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'structure-count', pattern: 'this._clearRescrapeErrors();', count: 10,
    note: '[163a-T6b-reset]（165-T10 搬遷）原 7 處 `rescrapeAccessError = null` 集中為 helper；呼叫點數棘輪。使用者被拒後按「換來源」／關窗再開／改番號 → 紅字要消失；開窗、番號空白、送出前、查無 fallback、網路失敗 catch、回選單、關窗各清一次，少一處上一個來源的紅字就黏在畫面上',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /_clearRescrapeErrors\(\) \{\s*this\.rescrapeNotFound = false;\s*this\.rescrapeAccessError = null;\s*this\.rescrapeCustomError = null;/,
    note: '[163a-T6b-reset]（165-T10 搬遷）helper 本體必須同時清 not-found／access／custom 三種紅字，少一個就會兩行紅字並存',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'onRescrapeNumberInput() {\n            this._clearRescrapeErrors();',
    note: '[163a-T6b-modal-reset-body]（165-T10 搬遷補）使用者被拒後改番號 → 紅字要立刻消失；helper 呼叫必須是該方法第一個敘述；要重排就同步改這條，粗顆粒守衛',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: "window.t('showcase.rescrape.access_refused'",
    stripLineComments: true,
    note: '[163a-T6b-msg] 使用者指定來源被拒 → 紅字要寫「拒絕連線」而不是「找不到」，才知道該查網路／代理',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: "window.t('showcase.rescrape.access_unreachable'",
    stripLineComments: true,
    note: '[163a-T6b-msg] 使用者指定來源連不到 → 紅字要寫「連不到，請檢查網路或代理設定」',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: "window.t('showcase.rescrape.access_advice_jp_ip'",
    stripLineComments: true,
    note: '[163a-T6b-msg] DMM 被拒 → 要多給「部分地區需要日本 IP」建議句',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'requires_proxy',
    scope: { anchor: /rescrapeAccessAdvice\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[163a-T6b-advice-gate] JavDB 等不需日本 IP 的來源被拒 → 不得被叫去設日本 IP 代理；建議句只依來源的 requires_proxy 屬性附加',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: /(?<![\w:-])x-show="rescrapeAccessError"/,
    note: '[163a-T6b-modal-block] 來源被拒時重刮視窗要有紅字區塊，否則使用者按了沒反應、不知道要做什麼',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrapeAccessMessage(rescrapeAccessError)',
    note: '[163a-T6b-modal-block] 紅字區塊要顯示映射後的訊息文字',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: /@input="[^"]*onRescrapeNumberInput\(\)/,
    note: '[163a-T6b-modal-reset]（165-T10 搬遷）使用者被拒後改番號 → 紅字要立刻消失，否則舊來源的錯誤蓋在新番號上',
  },
  {
    file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'required-string', pattern: /errorText = this\._advancedAccessText\(data\)/,
    stripLineComments: true,
    note: '[163a-T6b-picker] 使用者在搜尋頁指定來源被拒 → 錯誤文字要走介面語言映射，不顯示後端寫死的中文',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: 'isSourceProxyBlocked',
    note: '[163a-T6b-no-intercept] 使用者 Proxy 空白時點重刮視窗的 DMM 膠囊要直接查詢，不得被擋或沒反應',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string', pattern: 'isSourceProxyBlocked',
    note: '[163a-T6b-no-intercept] 使用者 Proxy 空白時點重刮視窗的 DMM 膠囊要直接查詢，不得被擋或沒反應',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: 'dmm_proxy_required_hint',
    note: '[163a-T6b-no-intercept] 使用者 Proxy 空白時點重刮視窗的 DMM 膠囊要直接查詢，不得跳「請先設定代理」',
  },

  // ---- [163a-T7] AC-12：說明頁／AI 描述／locale 不得再教人把 direct 填進 Proxy 欄；舊 help key 名不得回流 ----
  ...[
    'locales/zh_TW.json', 'locales/zh_CN.json', 'locales/ja.json', 'locales/en.json',
    'web/templates/settings.html', 'web/templates/help.html', 'web/routers/capabilities.py',
  ].flatMap((f) => [
    {
      file: f, kind: 'forbidden-string',
      pattern: /<code>\s*direct\s*<\/code>|(?:輸入|输入)\s*(?:<code>)?direct\b|enter\s+direct\b|direct\s*と入力|Proxy\s+direct\s*模式|Proxy\s+Direct\s+Mode|Proxy\s+ダイレクトモード/i,
      note: '[163a-T7-direct-fill] 使用者照說明把 direct 填進 Proxy 欄 → 欄位存成無效代理位址，DMM（或所選範圍內的來源）連線全部失敗；Proxy 留空＝系統代理，不需要任何特殊字樣',
    },
    {
      file: f, kind: 'forbidden-string',
      pattern: /\b(?:h6_proxy_direct|proxy_direct_vpn|proxy_direct_how|dmm_direct)\b/,
      note: '[163a-T7-old-key] 舊 direct 小節的 help key 名回流 → 說明頁標題顯示原始 key 字樣，或舊 direct 教學譯文復活',
    },
  ]),

  // ---- [163b-T1] 探測路徑只准吃請求體快照，不得讀已儲存的設定 ----
  ...['core/source_probe.py', 'web/routers/source_probe.py'].flatMap((f) =>
    ['load_config', 'current_settings'].map((word) => ({
      file: f, kind: 'forbidden-string', pattern: word,
      note: '[163b-T1-no-live-read] 使用者輸入新代理不按儲存就按測試 → 探測若讀了已儲存的設定，結果反映的是舊代理，且畫面完全看不出來',
    })),
  ),

  // ---- [163b-T7a] windows/ 與 core/cf_transport.py 不得自己讀 Proxy 欄的設定值 ----
  ...[
    { dir: 'windows', ext: ['.py'], recursive: true },
    'core/cf_transport.py',
  ].map((target) => ({
    file: target, kind: 'forbidden-string', pattern: 'proxy_url',
    note: '[163b-T7a-no-proxy-url-in-windows] 驗證視窗要走哪個代理只能問 core.proxy_policy 的 cf_window_proxy；windows 層若自己讀代理設定欄位，就會繞過「僅 DMM／所有來源」的範圍判斷，使用者選「僅 DMM」卻發現 JavLibrary／FC2-javten 的視窗也被送進代理',
  })),

  // ---- [163b-T7b] 重開提示的接線（node:test 看不到模板；外觀不守） ----
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: /(?<![\w:-])x-show="cfWindowProxyRestartNeeded"/,
    note: '[163b-T7b-restart-hint-wired] 使用者存了新代理、提示永遠不出現 → 以為 JavLibrary／FC2-javten 已改走新代理，其實要重開 OpenAver 才會換',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: /this\.cfWindowProxyRestartNeeded = result\.cf_window_proxy_restart_needed === true/,
    note: '[163b-T7b-restart-hint-state] 使用者存了新代理、後端說要重開但前端沒讀到 → 提示不出現，以為已改走新代理',
  },

  // ---- [163b-T3] 舊測試鈕與舊端點確實消失 ----
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'testProxy',
    note: '[163b-T3-no-old-test-btn] 使用者在 Proxy 欄旁按到只測 DMM 的舊鈕 → 打到已拿掉的端點只看到網路錯誤，誤以為自己的代理壞了',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'settings.search.test_dmm',
    note: '[163b-T3-no-old-test-btn] 使用者在 Proxy 欄旁按到只測 DMM 的舊鈕 → 打到已拿掉的端點只看到網路錯誤，誤以為自己的代理壞了',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: '/api/proxy/test',
    note: '[163b-T3-no-old-test-btn] 使用者在 Proxy 欄旁按到只測 DMM 的舊鈕 → 打到已拿掉的端點只看到網路錯誤，誤以為自己的代理壞了',
  },
  {
    file: { dir: 'web/static/js', ext: ['.js'], recursive: true }, kind: 'forbidden-string', pattern: '/api/proxy/test',
    note: '[163b-T3-no-old-test-btn] 使用者在 Proxy 欄旁按到只測 DMM 的舊鈕 → 打到已拿掉的端點只看到網路錯誤，誤以為自己的代理壞了',
  },
  {
    file: { dir: 'web/static/js', ext: ['.js'], recursive: true }, kind: 'forbidden-string', pattern: 'testProxy',
    note: '[163b-T3-no-old-test-btn] 使用者在 Proxy 欄旁按到只測 DMM 的舊鈕 → 打到已拿掉的端點只看到網路錯誤，誤以為自己的代理壞了',
  },

  // ---- [163b-T4a] 測試連線只在按下時跑：唯一 fetch、唯一入口、模板接線 ----
  // 目錄規則不加 recursive：__tests__/ 不被掃，行為測試才能呼叫測試入口方法。
  {
    file: 'web/static/js/pages/settings/state-source-probe.js', kind: 'structure-count', pattern: '/api/sources/probe', count: 1,
    note: '[163b-T4a-fetch-once] 使用者按一次「測試連線」→ 若分片裡呼叫兩次，代理與 IP 多吃一倍流量且兩輪結果互相覆蓋（註解也不得寫出端點字面，structure-count 不剝 .js 註解）',
  },
  {
    file: { dir: 'web/static/js/pages/settings', ext: ['.js'], exclude: ['state-source-probe.js'] }, kind: 'forbidden-string', pattern: '/api/sources/probe',
    note: '[163b-T4a-no-stray-fetch] 使用者只是開設定頁或改設定，沒按「測試連線」→ 若別處偷呼叫探測端點，十個來源網站會被連一輪（走他的代理與 IP）',
  },
  {
    file: { dir: 'web/static/js/pages/settings', ext: ['.js'], exclude: ['state-source-probe.js'] }, kind: 'forbidden-string', pattern: 'runSrcProbe',
    note: '[163b-T4a-no-stray-run] 使用者只是開設定頁或改設定，沒按「測試連線」→ 若別處呼叫測試入口方法，來源網站會被偷偷連一輪',
  },
  {
    file: 'web/templates/settings.html', kind: 'structure-count', pattern: /(?<![\w:-])@click="runSrcProbe\(\)"/, count: 1,
    note: '[163b-T4a-run-once-tpl] 使用者按「測試連線」→ 模板裡只能有這一個入口；少了鈕沒反應，多了別處也會觸發探測',
  },
  {
    file: 'web/templates/settings.html', kind: 'structure-count', pattern: "$watch('srcProbeKey', () => clearSrcProbe())", count: 1,
    note: '[163b-T4a-watch-wired] 使用者測完後改了 Proxy 欄、範圍或膠囊開關 → 沒接線舊結果會一直留著，以為新設定已驗過（node:test 看不到模板）',
  },

  // ---- [163b-T4b] 膠囊上的狀態點與原因句：接線釘子（node:test 看不到模板；外觀不守） ----
  ...[
    ['dot-click-stop', '@click.stop="toggleSrcProbeTip(s.id)"', '使用者點狀態點想看原因 → 沒擋冒泡會把這顆膠囊翻成停用、結果被清空，且悄悄改了來源設定'],
    ['dot-enter-stop', '@keydown.enter.stop', '鍵盤使用者 Tab 到狀態點按 Enter 想看原因 → 沒擋冒泡會翻膠囊開關、全部點消失'],
    ['dot-space-stop', '@keydown.space.stop', '鍵盤使用者在狀態點按空白想看原因 → 沒擋冒泡會讓膠囊進入抓取排序或翻開關'],
    ['dot-no-drag', '@mousedown.prevent', '使用者想點狀態點看原因、按住時手稍微移動 → 沒取消 mousedown 會變成拖曳整顆膠囊，放到別顆上就把來源順序存檔了，原因句也沒出來'],
    ['dot-type-button', 'type="button"', '使用者點一下狀態點 → 漏寫 type 會送出整份設定表單，沒按儲存卻存了'],
    ['dot-gated', 'x-show="srcProbeIcon(s.id)"', '測試前或改設定後 → 沒有結果的膠囊不該掛著空白點，否則以為新設定已驗過'],
  ].map(([tag, literal, why]) => ({
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: new RegExp('(?<![\\w:-])' + literal.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
    scope: /<button\b[^>]*class="source-pill-probe"[^>]*>/s,
    note: `[163b-T4b-${tag}] ${why}`,
  })),
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: /(?<![\w:-])x-text="srcProbeTipText"/,
    scope: /<[a-z]+\b[^>]*class="source-pill-probe-tip"[^>]*>/s,
    note: '[163b-T4b-tip-wired] 手機或鍵盤使用者點了狀態點 → 膠囊列下方沒有原因句，只知道「被擋」不知道原因與日本 IP 建議',
  },
  ...['locales/zh_TW.json', 'web/static/js/pages/settings/source-probe-logic.js', 'web/templates/settings.html'].flatMap((file) =>
    ['地區限制', '區域封鎖'].map((word) => ({
      file, kind: 'forbidden-string', pattern: word,
      note: '[163b-T4b-no-region-claim] javdb App 通道被拒絕時畫面斷言「' + word + '」→ 使用者去換 IP，其實換 IP 沒用',
    }))),

  // ---- [TestDmmProxyRequiredGuard] 63c-6：DMM requires_proxy 灰化，非-CSS 半邊（CSS 半邊已隨 163a-T6b 拔除）----
  // Scope A：clickActiveRowPill 函數體。⚠ Python 原始 regex 用 \Z（Python string-end anchor）+ re.DOTALL；
  // JS 無 \Z（\Z 在 JS regex 是字面 "Z"），faithful port 用 $（配合僅 's' flag、無 'm' flag，JS $ 即絕對字串結尾，等價 Python \Z）。
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'window.confirm',
    scope: /clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|$)/s,
    note: '[TestDmmProxyRequiredGuard] test_click_active_row_pill_no_window_confirm — Scope A（\\Z→$ port）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: 'window.confirm',
    scope: /x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestDmmProxyRequiredGuard] test_rescrape_modal_builtin_pill_no_window_confirm — Scope D',
  },

  // ---- [TestPicker64aThreeStateGuard] 64a：進階 picker 三態膠囊語意 + 標題依入口，非-CSS Jinja markup 半邊（CSS 半邊已由 96c css-guard CG-RO-03 覆蓋，本段不重建）----
  // Scope E = DmmProxy Scope D（同一 regex、同一 builtin button target，共用字面）。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'data-enabled="true"',
    scope: /x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestPicker64aThreeStateGuard] test_builtin_pill_data_enabled_hardcoded_true — Scope E（=DmmProxy Scope D）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: ':data-enabled',
    scope: /x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestPicker64aThreeStateGuard] test_builtin_pill_data_enabled_hardcoded_true — Scope E（=DmmProxy Scope D），builtin 不得綁 s.enabled',
  },
  // Scope F：metatube pill 全 attrs。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: ':data-enabled',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_data_enabled_binds_available — Scope F',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 's.available',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_data_enabled_binds_available + test_metatube_pill_offline_aria_disabled_and_guard — Scope F（兩測同 file+kind+pattern+scope，合併單列）',
  },
  // Scope G：metatube pill :data-enabled 屬性值（組合 regex，等價 pytest 兩層擷取，見 TASK-96d-T2.md §「本卡新用法」）。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 's.available',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+[^>]*?:data-enabled="([^"]+)"[^>]*>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_data_enabled_binds_available — Scope G（:data-enabled 值本身，非全 attrs）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string', pattern: 's.enabled',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+[^>]*?:data-enabled="([^"]+)"[^>]*>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_data_enabled_binds_available — Scope G，值域鎖定精準度（見本卡 Scope G vs F mutation 驗證）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: ':aria-disabled',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_offline_aria_disabled_and_guard — Scope F',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'offline_tooltip',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_offline_aria_disabled_and_guard — Scope F',
  },
  // Scope H：metatube pill @click 屬性值。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 's.available',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+[^>]*?@click="([^"]+)"[^>]*>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_offline_aria_disabled_and_guard — Scope H（@click 值 offline guard）',
  },
  // Scope I：metatube pill :disabled 屬性值。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'rescrapeLoadingSource',
    scope: /x-for="s in rescrapeMetatubeSources\(\)"[^>]*>.*?<button\s+[^>]*?:disabled="([^"]+)"[^>]*>/s,
    note: '[TestPicker64aThreeStateGuard] test_metatube_pill_offline_aria_disabled_and_guard — Scope I（native :disabled 只綁 loading）',
  },
  // Scope J：modal title h3（無 capture group，取 match[0]）。
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'x-text',
    scope: /class="fluent-modal-title".*?<\/h3>/s,
    note: '[TestPicker64aThreeStateGuard] test_modal_title_switches_by_entrypoint — Scope J',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: "rescrapeEntryPoint === 'search'",
    scope: /class="fluent-modal-title".*?<\/h3>/s,
    note: '[TestPicker64aThreeStateGuard] test_modal_title_switches_by_entrypoint — Scope J',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'search_title',
    scope: /class="fluent-modal-title".*?<\/h3>/s,
    note: '[TestPicker64aThreeStateGuard] test_modal_title_switches_by_entrypoint — Scope J',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'modal_title',
    scope: /class="fluent-modal-title".*?<\/h3>/s,
    note: '[TestPicker64aThreeStateGuard] test_modal_title_switches_by_entrypoint — Scope J',
  },

  // ==== 96d-T3：motion-token 家族遷移（TASK-96d-T3.md，10 live pytest class，1 子測 must-stay-pytest）====
  // TestShowcaseAnimationsGuard.test_core_js_no_direct_gsap_getById（scope-exclusion forbidden：
  // 「_killLightboxTimelines 函式體之外」不得出現 gsap.getById(）不遷——engine 只有「限定 scope
  // 內」沒有「排除 scope 外」的能力，count-equality 變通會引入比 pytest 更脆弱的假陽性
  // （見 TASK-96d-T3.md「必留 pytest 清單」節）。該 class 因此為 motion 家族內唯一
  // slim-residual（其餘 4 子測全遷，此 1 子測留 pytest）。

  // ---- [TestFluentCustomEaseRegistered] motion-adapter.js CustomEase 三角色同步註冊 ----
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "CustomEase.create('fluent'", note: "[TestFluentCustomEaseRegistered] test_fluent_standard_registered" },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "CustomEase.create('fluent-decel'", note: "[TestFluentCustomEaseRegistered] test_fluent_decel_registered" },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "CustomEase.create('fluent-accel'", note: "[TestFluentCustomEaseRegistered] test_fluent_accel_registered" },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "typeof CustomEase !== 'undefined'", note: '[TestFluentCustomEaseRegistered] test_register_is_guarded' },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'forbidden-string',
    pattern: /DOMContentLoaded[\s\S]*CustomEase\.create\('fluent'/,
    note: "[TestFluentCustomEaseRegistered] test_register_is_synchronous — conditional-order 技巧：只在「DOMContentLoaded 先出現、CustomEase.create('fluent' 隨後再出現」（即 fluent 註冊被包進 handler 之違規情境）才匹配；現況檔案無 DOMContentLoaded 字面，vacuous pass（4 種情境推導見 TASK-96d-T3.md §1）",
  },

  // ---- [TestMotionDurationConstants] motion.DURATION 三角色常數 + 雙檔 usage-count（min-bound）+ white-list ----
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'DURATION:', note: '[TestMotionDurationConstants] test_duration_constants_exposed — DURATION 物件定義' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'fast:', note: '[TestMotionDurationConstants] test_duration_constants_exposed — fast 角色' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: '0.167', note: '[TestMotionDurationConstants] test_duration_constants_exposed — fast=0.167' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'medium:', note: '[TestMotionDurationConstants] test_duration_constants_exposed — medium 角色' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: '0.333', note: '[TestMotionDurationConstants] test_duration_constants_exposed — medium=0.333' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'emphasis:', note: '[TestMotionDurationConstants] test_duration_constants_exposed — emphasis 角色' },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: '0.5', note: '[TestMotionDurationConstants] test_duration_constants_exposed — emphasis=0.5' },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: 'motion.DURATION.', count: 4,
    note: '[TestMotionDurationConstants] test_adapter_callers_use_duration_constants — js.count("motion.DURATION.") >= 4（required-string count=min-bound，非 structure-count exact）',
  },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'OpenAver.motion.DURATION.', count: 7,
    note: '[TestMotionDurationConstants] test_animations_callers_use_duration_constants — js.count("OpenAver.motion.DURATION.") >= 7（min-bound；現況恰貼齊門檻，mutation 高風險列）。TASK-141b-T1：原為 8，playEntry/playFlipFilter 各帶走 1 次搬去 shared/grid-motion.js，由下一列接住（7+2=9，總覆蓋未減）',
  },
  {
    file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'OpenAver.motion.DURATION.', count: 2,
    note: '[TestMotionDurationConstants] TASK-141b-T1：playEntry/playFlipFilter 搬家後的新家，接住從 animations.js 移出的那 2 次（min-bound）',
  },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'params.duration || 0.8', note: '[TestMotionDurationConstants] test_white_list_durations_preserved — showcaseSettle 招牌曲線白名單' },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'duration: 0.3',
    scope: { anchor: /playHeroCardAppear/, window: 800 },
    note: '[TestMotionDurationConstants] test_white_list_durations_preserved — playHeroCardAppear 女優專屬白名單（800 字元視窗）',
  },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'options.duration : 0.1',
    scope: { anchor: /playSourcePulse/, window: 800 },
    note: '[TestMotionDurationConstants] test_white_list_durations_preserved — playSourcePulse 低於 fast bucket 白名單（800 字元視窗）',
  },

  // ---- [TestMotionAdapterFluentDefaults] motion-adapter.js 5 default ease → fluent 角色（per-fn lazy-lookahead scope）----
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "opts.ease || 'fluent-decel'",
    scope: /playEnter:[\s\S]*?(?=\/\*\*)/,
    note: "[TestMotionAdapterFluentDefaults] test_play_enter_default_fluent_decel",
  },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "opts.ease || 'fluent-accel'",
    scope: /playLeave:[\s\S]*?(?=\/\*\*)/,
    note: "[TestMotionAdapterFluentDefaults] test_play_leave_default_fluent_accel",
  },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "opts.ease || 'fluent-decel'",
    scope: /playStagger:[\s\S]*?(?=\/\*\*)/,
    note: "[TestMotionAdapterFluentDefaults] test_play_stagger_default_fluent_decel",
  },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "opts.ease || 'fluent'",
    scope: /playFadeTo:[\s\S]*?(?=\/\*\*)/,
    note: "[TestMotionAdapterFluentDefaults] test_play_fade_to_default_fluent — required 半邊",
  },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'forbidden-string', pattern: "opts.ease || 'fluent-decel'",
    scope: /playFadeTo:[\s\S]*?(?=\/\*\*)/,
    note: "[TestMotionAdapterFluentDefaults] test_play_fade_to_default_fluent — forbidden 半邊",
  },
  {
    file: 'web/static/js/components/motion-adapter.js', kind: 'required-string', pattern: "opts.ease || 'fluent-decel'",
    scope: /playModal:[\s\S]*?(?=\/\*\*)/,
    note: "[TestMotionAdapterFluentDefaults] test_play_modal_default_fluent_decel",
  },
  { file: 'web/static/js/components/motion-adapter.js', kind: 'forbidden-string', pattern: "opts.ease || 'power", note: '[TestMotionAdapterFluentDefaults] test_no_legacy_power_ease_defaults — unscoped 全檔' },

  // ---- [TestShowcaseAnimationsFluent] showcase/animations.js + ghost-fly.js + search/animations.js ease → fluent 角色 ----
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: "params.easing || 'fluent-decel'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playEntry' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "params.ease || 'fluent'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playFlipReorder' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "ease: 'fluent-accel'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playModeCrossfade' },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "ease: 'fluent-decel'", count: 2,
    note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playFlipFilter onEnter ×2（存在性斷言 + js.count(...) >= 2 合併為單一 count-based 列）',
  },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "ease: 'fluent'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playLightboxSwitch/playSampleGallerySwitch' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "options.ease || 'fluent-decel'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playContainerFadeIn/playSourcePulse' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'CustomEase.create("showcaseSettle"', note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — white-list 招牌曲線' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'GhostFly.playLightboxOpen', note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — T4.2 delegate' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'showcaseLightboxOpen', note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — T4.2 delegate' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "typeof window.GhostFly?.playLightboxOpen === 'function'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — T4.2 delegate guard' },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', anyOf: true,
    pattern: ['gsap.fromTo', 'tl.fromTo'],
    note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playModeCrossfade fromTo call（OR）',
  },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', anyOf: true,
    pattern: ["'use strict'", "\"'use strict'\""],
    note: "[TestShowcaseAnimationsFluent] test_animations_js_contains — strict mode declaration（單/雙引號變體 OR）",
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: "ease: 'power2.out'", count: 3,
    scope: { anchor: /playLightboxOpen:/, window: 4500 },
    note: '[TestShowcaseAnimationsFluent] test_ghost_fly_js_contains — playLightboxOpen 三段 power2.out（backdrop/content/cover，min-bound，現況恰貼齊門檻）',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: "clearProps: 'transform,opacity'", count: 4,
    scope: { anchor: /playLightboxOpen:/, window: 4500 },
    note: '[TestShowcaseAnimationsFluent] test_ghost_fly_js_contains — clearProps ×4（onComplete+onInterrupt，min-bound，現況恰貼齊門檻）',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'forbidden-string', pattern: "ease: 'fluent-decel'",
    scope: { anchor: /playLightboxOpen:/, window: 4500 },
    note: '[TestShowcaseAnimationsFluent] test_ghost_fly_js_contains — playLightboxOpen 不應誤改成 fluent-decel（保留 power2.out 白名單）',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', anyOf: true,
    pattern: ['white-list', 'ghost-fly'],
    scope: { anchor: /playLightboxOpen:/, window: 4500 },
    note: '[TestShowcaseAnimationsFluent] test_ghost_fly_js_contains — white-list/ghost-fly 標注註解（OR）',
  },
  {
    file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'GhostFly.playLightboxOpen',
    scope: { anchor: /playLightboxOpen: function/, window: 800 },
    note: '[TestShowcaseAnimationsFluent] test_search_animations_js_contains — Phase 51 T4.3 delegate',
  },
  {
    file: 'web/static/js/pages/search/animations.js', kind: 'forbidden-string', pattern: 'showcaseLightboxOpen',
    scope: { anchor: /playLightboxOpen: function/, window: 800 },
    note: '[TestShowcaseAnimationsFluent] test_search_animations_js_contains — search 頁不應殘留 showcase 專屬命名',
  },
  {
    file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: "typeof window.GhostFly?.playLightboxOpen === 'function'",
    scope: { anchor: /playLightboxOpen: function/, window: 800 },
    note: '[TestShowcaseAnimationsFluent] test_search_animations_js_contains — typeof guard',
  },

  // ---- [TestMotionLabT2EaseRoles] motion_lab.html + motion-lab.js §5 Ease Roles demo ----
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'fluent-decel', note: '[TestMotionLabT2EaseRoles] test_html_contains_fluent_decel' },
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'fluent-accel', note: '[TestMotionLabT2EaseRoles] test_html_contains_fluent_accel' },
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'ease-roles', note: '[TestMotionLabT2EaseRoles] test_html_has_ease_roles_tab' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playEaseRolesDemo', note: '[TestMotionLabT2EaseRoles] test_js_has_play_ease_roles_demo' },
  {
    file: 'web/static/js/pages/motion-lab.js', kind: 'forbidden-string', pattern: 'power3.out',
    scope: /playCardStreamIn:[\s\S]*?(?=\n {8}\/\*\*)/,
    note: '[TestMotionLabT2EaseRoles] test_js_no_bare_back_out_in_stream — playCardStreamIn 不含裸 power3.out（lazy-lookahead 到下個 8-space 縮排 /** 標記）',
  },
  {
    file: 'web/static/js/pages/motion-lab.js', kind: 'forbidden-string', pattern: 'power2.out',
    scope: /playCardStreamIn:[\s\S]*?(?=\n {8}\/\*\*)/,
    note: '[TestMotionLabT2EaseRoles] test_js_no_bare_back_out_in_stream — playCardStreamIn 不含裸 power2.out（同上 scope）',
  },

  // ---- [TestMotionLabT2DurationBuckets] motion_lab.html + motion-lab.js §5 Duration Buckets demo ----
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'duration-buckets', note: '[TestMotionLabT2DurationBuckets] test_html_has_duration_buckets_tab' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playDurationBucketsDemo', note: '[TestMotionLabT2DurationBuckets] test_js_has_play_duration_buckets_demo' },
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'DURATION.fast', note: '[TestMotionLabT2DurationBuckets] test_html_shows_duration_fast_label' },

  // ---- [TestMotionLabT2SpecialMotion] motion_lab.html + motion-lab.js §5 Special Motion 白名單 demo ----
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'special-motion', note: '[TestMotionLabT2SpecialMotion] test_html_has_special_motion_tab' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playSpecialMotionCheckmarkDemo', note: '[TestMotionLabT2SpecialMotion] test_js_has_play_special_motion_checkmark_demo' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playSpecialMotionShakeDemo', note: '[TestMotionLabT2SpecialMotion] test_js_has_play_special_motion_shake_demo' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playSpecialMotionPulseDemo', note: '[TestMotionLabT2SpecialMotion] test_js_has_play_special_motion_pulse_demo' },
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'whitelist-skip-note', note: '[TestMotionLabT2SpecialMotion] test_html_has_whitelist_skip_note' },

  // ---- [TestShowcaseAnimationsGuard] B5-B15/T20 Showcase GSAP 基礎設施（slim-residual：4/5 子測遷，
  // test_core_js_no_direct_gsap_getById 留 pytest，見上方 96d-T3 header 說明）----
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'window.ShowcaseAnimations', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 IIFE + global object' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'prefersReducedMotion', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'playEntry', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 method stub' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'playFlipReorder', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 method stub' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'playFlipFilter', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 method stub' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'captureFlipState', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B7' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'capturePositions', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B7' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'playModeCrossfade', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 method stub' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'registerPlugin(Flip)', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 plugin registration' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'showcaseSettle', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B5' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'gsap.killTweensOf', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B6 playEntry impl' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'getBoundingClientRect', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B6' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'gsap.set', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B6' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'Flip.getState', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B7 captureFlipState/capturePositions' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: '.av-card-preview', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B7' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'data-flip-id', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B7' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'Flip.from', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8 playFlipFilter' },
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'onEnter', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'onLeave', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'clearProps', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'return gsap.fromTo', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8 playFlipFilter returns tweens' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'return gsap.to', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  // 🔴 Codex PR#177 第 2 輪 P3（Opus 2026-09-03）：B8 群組的搬家只做了一半。
  // T1 把 playFlipFilter 從 animations.js 搬進 grid-motion.js 時，只有 onEnter/onLeave 兩條
  // 跟著改 `file`；`Flip.from` / `clearProps` / `return gsap.fromTo` / `return gsap.to` 四條
  // 仍指向 animations.js——而那個檔裡**別的方法**（playFlipReorder / playModeCrossfade /
  // pick-star）恰好也有同樣字面，於是把 grid-motion.js 裡 playFlipFilter 的那些行為刪掉，
  // lint 照樣全綠（三次獨立 mutation 實測，全部 green）⇒ **搬家把覆蓋率靜默削掉了**。
  // 這正是 gotchas FE-GUARD-26 記的兩種錯法之一。
  // 依該條的判定法：grep 舊檔剩餘次數——四條全部非零（1 / 15 / 3 / 1），代表 animations.js
  // 那幾列仍在合法地守 B12 與其他方法 ⇒ **純新增四列守新家，不動舊列、總覆蓋只增不減**。
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'Flip.from',
    stripLineComments: true,
    note: '[TestShowcaseAnimationsGuard] B8 playFlipFilter 的 Flip.from（TASK-141b-T1 搬家後的新家）。stripLineComments 是必要的：grid-motion.js 的行內註解本身含 `Flip.from` 字面，不剝掉的話刪掉真正的呼叫仍會 false-pass（實測踩過）。' },
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'clearProps', count: 3,
    note: '[TestShowcaseAnimationsGuard] B8：playEntry 兩處 ＋ playFlipFilter onComplete 一處。count 鎖 3，少任何一處都轉紅。' },
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'return gsap.fromTo', count: 2,
    note: '[TestShowcaseAnimationsGuard] B8：playFlipFilter 的 onEnter 兩個分支各回一條 tween。' },
  { file: 'web/static/js/shared/grid-motion.js', kind: 'required-string', pattern: 'return gsap.to',
    note: '[TestShowcaseAnimationsGuard] B8：playFlipFilter 的 onLeave 回傳的 tween。' },
  {
    file: 'web/static/css/theme.css',
    kind: 'required-string',
    pattern: ':is(.ds-gallery-composition .flip-guard, .ds-gallery-composition.flip-guard)',
    count: 2,
    note: '[branch review / Codex PR#177 第 2 輪 P3] B15 的 flip-guard 覆蓋規則必須同時接受兩種形狀：瀏覽頁的「composition 與 flip-guard 分屬兩層」與書籤牆的「兩個 class 疊在同一元素」（search.html:1208 的 .wishlist-grid 本身就帶 ds-gallery-composition）。只寫後代形式的話，書籤牆的卡片**0 命中**（真瀏覽器實測），收合時 hover 的 transform 會跟 GSAP FLIP 搶——而這條規則存在的唯一理由就是蓋掉它。兩處（本體 ＋ :hover）都要，所以 count 鎖 2。瀏覽頁實測不受影響（新舊 selector 命中數同為 91）。',
  },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: '.fromTo', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B12 playFlipReorder manual fromTo' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'killLightboxAnimations', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — T20' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "getById('showcaseLightboxOpen')", note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — T20' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "getById('showcaseLightboxSwitch')", note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — T20' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'typeof gsap', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — T20' },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', anyOf: true,
    pattern: ['gsap.fromTo', 'tl.fromTo'],
    note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B10 playModeCrossfade fromTo call（OR）',
  },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', anyOf: true,
    pattern: ["'use strict'", "\"'use strict'\""],
    note: "[TestShowcaseAnimationsGuard] test_animations_js_contains — B5 strict mode declaration（單/雙引號變體 OR）",
  },
  { file: 'web/static/css/theme.css', kind: 'required-string', pattern: 'flip-guard', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B15 theme.css flip-guard rule' },
  { file: 'web/static/css/theme.css', kind: 'required-string', pattern: 'transform: none', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B15 theme.css flip-guard rule' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'animations.js', note: '[TestShowcaseAnimationsGuard] test_showcase_html_contains — animations.js script tag' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'data-flip-id', note: '[TestShowcaseAnimationsGuard] test_showcase_html_contains — data-flip-id' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: 'Flip.min.js', note: '[TestShowcaseAnimationsGuard] test_showcase_html_contains — 不重複載入 Flip.min.js' },
  // _read_core_js() 合併讀取 state-base.js + state-videos.js + state-lightbox.js 三檔；engine 不支援
  // 多檔合併成單一文字塊，改單檔化指向 state-videos.js（已逐字面 grep 核對現況下語意完全等價，
  // 「位置收斂」而非縮窄，見 TASK-96d-T3.md §「合併讀取檔案的單檔化處理」）。
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'playEntry', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B6 playEntry call（單檔化，見上）' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'ShowcaseAnimations', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '_animateFilter', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B8 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'playFlipFilter', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B8 playFlipFilter call 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '_animatePageChange', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B9 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'scrollTo(0, 0)', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B9 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'playModeCrossfade', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B10 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'ShowcaseAnimations?.playModeCrossfade?.(', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B10 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'capturePositions', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B12 sort helper 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'playFlipReorder', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B12 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'flip-guard', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B12/B13 flip-guard management 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '_animGeneration', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B13 generation token guard 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '_sortWithFlip', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B13 method 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'captureFlipState', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B15 _animateFilter 單檔化' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'updatePagination', note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B7 單檔化' },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', anyOf: true,
    pattern: ['savedPage', 'saved_page', 'savePage'],
    note: '[TestShowcaseAnimationsGuard] test_core_js_contains — B7 _sortWithFlip page preservation（OR，單檔化）',
  },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '_animatePageChange',
    scope: { anchor: /prevPage\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestShowcaseAnimationsGuard] test_core_js_prev_next_page_call_animate_page_change — prevPage() 方法體須呼叫 _animatePageChange（brace-balanced，單檔化：方法定義唯一位於 state-videos.js）',
  },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '_animatePageChange',
    scope: { anchor: /nextPage\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestShowcaseAnimationsGuard] test_core_js_prev_next_page_call_animate_page_change — nextPage() 方法體須呼叫 _animatePageChange（brace-balanced，單檔化）',
  },
  // test_core_js_no_direct_gsap_getById（scope-exclusion forbidden）不建 RULES 列，留 pytest（見上方 header）。

  // ---- [TestMotionLabShowcase] B11 Motion Lab Showcase demo 完整性（determination：required-string
  // 網，非直刪——Showcase tab / 4 個 demo 方法皆確認仍存在運作中，非死碼殘留，見 TASK-96d-T3.md
  // 「determination」節 grep 證據）----
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'showcase', note: '[TestMotionLabShowcase] test_motion_lab_html_contains — showcase tab（寬鬆子字串，與原 pytest 同寬）' },
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: "tab === 'showcase'", note: '[TestMotionLabShowcase] test_motion_lab_html_contains — Alpine tab 切換邏輯' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playShowcaseEntry', note: '[TestMotionLabShowcase] test_motion_lab_js_contains — B1' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playFlipReorder', note: '[TestMotionLabShowcase] test_motion_lab_js_contains — B2' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playFlipFilter', note: '[TestMotionLabShowcase] test_motion_lab_js_contains — B3' },
  { file: 'web/static/js/pages/motion-lab.js', kind: 'required-string', pattern: 'playPageTransition', note: '[TestMotionLabShowcase] test_motion_lab_js_contains — B4' },

  // ---- [TestGhostFlyPlayLightboxOpen] ghost-fly.js playLightboxOpen 共用實作守衛（unscoped，
  // 與 TestShowcaseAnimationsFluent.test_ghost_fly_js_contains 同檔不同 class/scope，互補不重複）----
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'playLightboxOpen', note: '[TestGhostFlyPlayLightboxOpen] test_ghost_fly_play_lightbox_open_contains' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'clearProps', note: '[TestGhostFlyPlayLightboxOpen] test_ghost_fly_play_lightbox_open_contains' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'timelineId', note: '[TestGhostFlyPlayLightboxOpen] test_ghost_fly_play_lightbox_open_contains' },

  // ==== 96d-T4：scanner-strm 家族（string-contains/tag-scan，含 CD-96d-7 負守衛 + CD-96d-5 slim-residual）====

  // ---- [TestStrmMappingGuard] settings.html strm 路徑映射 CRUD 編輯器 + state-config.js array→dict 轉換 +
  // scanner.html 跨機器提醒（純 string-contains，pure-96d，無 cross-plan 半邊）----
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'x-for="(rule, idx) in form.strmRules"', note: '[TestStrmMappingGuard] test_settings_html_has_editor — strmRules x-for row 編輯器' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'x-model="rule.local"', note: '[TestStrmMappingGuard] test_settings_html_has_editor — 本機前綴欄' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'x-model="rule.remote"', note: '[TestStrmMappingGuard] test_settings_html_has_editor — 播放端前綴欄' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: "['jellyfin','emby','kodi'].includes(form.externalManager)", note: '[TestStrmMappingGuard] test_settings_html_has_editor — media-server 風味 x-show gating（無空格版，勿與 scanner.html 有空格版混淆）' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: '@click="addStrmRule()"', note: '[TestStrmMappingGuard] test_settings_html_has_editor — 新增規則' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: '@click="removeStrmRule(idx)"', note: '[TestStrmMappingGuard] test_settings_html_has_editor — 刪除規則' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'addStrmRule()', note: '[TestStrmMappingGuard] test_config_js_has_methods_and_conversion' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'removeStrmRule(idx)', note: '[TestStrmMappingGuard] test_config_js_has_methods_and_conversion' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'Object.fromEntries(', note: '[TestStrmMappingGuard] test_config_js_has_methods_and_conversion — array→dict 轉換' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'strm_path_mappings:', note: '[TestStrmMappingGuard] test_config_js_has_methods_and_conversion — payload 寫入' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'strmTemplateDirs', note: '[TestStrmMappingGuard] test_config_js_has_methods_and_conversion — 範本回顯 getter' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'strmPathMappings', note: '[TestStrmMappingGuard] test_config_js_no_dict_passthrough — 舊 dict passthrough 已移除' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'scanner.folder.cross_machine_hint', note: '[TestStrmMappingGuard] test_scanner_html_has_cross_machine_hint' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'scanner.folder.cross_machine_settings_link', note: '[TestStrmMappingGuard] test_scanner_html_has_cross_machine_hint' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: "['jellyfin', 'emby', 'kodi'].includes(config?.scraper?.external_manager)", note: '[TestStrmMappingGuard] test_scanner_html_has_cross_machine_hint — media-server 風味 x-show gating（有空格版，勿與 settings.html 無空格版混淆）' },

  // ---- [TestReadonlyConfirmGuard] scanner.html 唯讀 checkbox 確認 modal 骨架 + 攔截邏輯 + state-scan.js
  // （cross-plan：96d 建 HTML/JS 半邊；i18n key + 「風味」半邊 → 96a i18n_lint，不建）----
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: ':checked="dir.readonly"', note: '[TestReadonlyConfirmGuard] test_scanner_html_checkbox_intercepted — 單向綁定，避免勾選閃爍' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: '@click.prevent="onReadonlyToggleClick(idx', note: '[TestReadonlyConfirmGuard] test_scanner_html_checkbox_intercepted — checkbox click 攔截（開放子字串，忠實照抄 pytest 原字面，故意不含收尾括號）' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string', pattern: 'x-model="dir.readonly"', note: '[TestReadonlyConfirmGuard] test_scanner_html_checkbox_intercepted — 不可殘留舊雙向綁定（CD-96d-7 負守衛）' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: "'modal-open': readonlyConfirmModalOpen", note: '[TestReadonlyConfirmGuard] test_scanner_html_has_confirm_modal' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: '@click="readonlyConfirmAccept()"', note: '[TestReadonlyConfirmGuard] test_scanner_html_has_confirm_modal' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: '@click="readonlyConfirmCancel()"', note: '[TestReadonlyConfirmGuard] test_scanner_html_has_confirm_modal' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'readonlyConfirmModalOpen && readonlyConfirmCancel()', note: '[TestReadonlyConfirmGuard] test_scanner_html_esc_chain_includes_readonly_confirm' },
  ...[
    'scanner.readonly_confirm_modal.title',
    'scanner.readonly_confirm_modal.cancel',
    'scanner.readonly_confirm_modal.confirm',
    'scanner.readonly_confirm_modal.intro',
    'scanner.readonly_confirm_modal.output_hint_offline',
    'scanner.readonly_confirm_modal.output_hint_media_server',
    'scanner.readonly_confirm_modal.nas_hint',
  ].map((key) => ({
    file: 'web/templates/scanner.html', kind: 'required-string', pattern: key,
    note: '[TestReadonlyConfirmGuard] test_scanner_html_i18n_keys_referenced — for-loop 7 key',
  })),
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string', pattern: '_detectReadonly', note: '[TestReadonlyConfirmGuard] test_state_scan_js_no_detect_readonly — 整支移除，含函式宣告與消費者（CD-96d-7 負守衛）' },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'readonly: false', count: 2,
    note: '[TestReadonlyConfirmGuard] test_state_scan_js_new_folders_readonly_false — addFolderPath/addManualPath 各自 push readonly: false（現況恰 2 次，L455/L480，高風險貼齊門檻列）',
  },
  ...[
    'readonlyConfirmModalOpen',
    'readonlyConfirmTargetIdx',
    'onReadonlyToggleClick',
    'readonlyConfirmCancel',
    'readonlyConfirmAccept',
  ].map((name) => ({
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: name,
    note: '[TestReadonlyConfirmGuard] test_state_scan_js_has_confirm_state_and_methods — for-loop 5 項',
  })),

  // ---- [TestOutputPathVisibilityGuard] scanner.html .folder-item-output x-show 白名單顯隱
  // （pure-96d，scope 綁定 x-show 屬性值本身（非整個 tag），CD-96d-7 負守衛：本卡最高風險列，
  // scanner.html 唯一 fail-open 守衛。bound to x-show value (Codex 96d P1 fix)：原 tag-scan
  // 掃整個開頭 tag，required 字串移到 x-show 以外的屬性也會誤判綠燈（fail-open exploit）；
  // 改用 capture-group scope 只在 x-show="..." 的值內比對，逐字對齊 pytest div.get("x-show","")；
  // token-aware class match (Codex 96d P2 fix)：class 比對改用 buildTagWithClassRegex 同款
  // (?<![\w-])…(?![\w-]) token 邊界，逐字對齊 pytest soup.find(class_=...) 的 token 語意
  // （非 exact-equality），避免該 div 未來多掛第二個 class 時 pytest 綠燈但 lint 誤判 scope-not-found；
  // attribute-name boundary via \s not \b (Codex 96d P1 fix round-3)：\b 是 word-boundary 不是
  // HTML 屬性名邊界，`-` 是 non-word char，會讓 \bx-show= 誤配到 data-x-show= 裡的 x-show=、
  // \bclass= 誤配到 data-class= 裡的 class=（真正的 x-show/class 屬性已被改名移除仍誤判綠燈，
  // fail-open）；改用 \s（屬性名前必為空白/換行/縮排分隔符，data- 前綴屬性前只有 `-` 沒有空白）----
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: 'dir.readonly',
    scope: /<div\b(?=[^>]*\sclass="[^"]*(?<![\w-])folder-item-output(?![\w-])[^"]*")[^>]*?\sx-show="([^"]*)"/,
    note: '[TestOutputPathVisibilityGuard] test_folder_item_output_xshow_gated_by_external_manager_whitelist — bound to x-show value (Codex 96d P1 fix)：fail-closed 白名單 required（CD-96d-7）',
  },
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: "['jellyfin', 'emby', 'kodi'].includes(config?.scraper?.external_manager)",
    scope: /<div\b(?=[^>]*\sclass="[^"]*(?<![\w-])folder-item-output(?![\w-])[^"]*")[^>]*?\sx-show="([^"]*)"/,
    note: '[TestOutputPathVisibilityGuard] test_folder_item_output_xshow_gated_by_external_manager_whitelist — bound to x-show value (Codex 96d P1 fix)：fail-closed 白名單 required（CD-96d-7）',
  },
  {
    file: 'web/templates/scanner.html', kind: 'forbidden-string',
    pattern: "!== 'off'",
    scope: /<div\b(?=[^>]*\sclass="[^"]*(?<![\w-])folder-item-output(?![\w-])[^"]*")[^>]*?\sx-show="([^"]*)"/,
    note: '[TestOutputPathVisibilityGuard] test_folder_item_output_xshow_gated_by_external_manager_whitelist — bound to x-show value (Codex 96d P1 fix)：fail-open forbidden（CD-96d-7）',
  },

  // ---- [TASK-104-T4] showcase.html 唯讀四鈕解禁：舊 96d readonly-disabled 鏡像正向守衛（element-bound
  // tag-scan，原 [TestReadonlyDisabledStateGuard]）已隨 104-T4 解禁四鈕整段移除——is_readonly_source /
  // is-readonly-disabled / readonly_tooltip 三者皆從 showcase.html 拔除，正向 required 規則會恆紅，故砍除
  // 整組（含冗餘的讀取類負守衛子陣列，已被下方 CD-104-10 全檔負向規則涵蓋）。CSS 半邊 CG-RO-01
  // （scripts/css-guard.mjs）已同步整條移除——.is-readonly-disabled class 定義本身也已從
  // showcase.css 刪除（拔除要徹底，見該檔 CG-RO-01 移除註記）。
  // ---- [CD-104-10] showcase.html 全檔負向守衛：is_readonly_source 零殘留（防四鈕 copy-paste 漏改復活）----
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: 'is_readonly_source',
    note: '[TASK-104-T4] test_showcase_html_no_is_readonly_source — 唯讀四鈕已解禁，is_readonly_source 欄位/綁定不得殘留（CD-104-10 全檔負向守衛）',
  },

  // ---- [TestRewriteStrmConfirmGuard] settings.html rewrite 確認 modal 骨架 + tone + state-config.js
  // saveConfig media-server 存後鉤 + confirmRewriteStrm 實際端點呼叫（cross-plan：96a i18n+風味 半邊不建；
  // CD-96d-5 已定案：rewrite_failed>=2 子測 slim-residual 留 pytest，本卡不建 RULES 覆蓋，見下方獨立註解）----
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: "'modal-open': rewriteStrmConfirmOpen", note: '[TestRewriteStrmConfirmGuard] test_settings_html_has_rewrite_confirm_modal' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: '@click="confirmRewriteStrm()"', note: '[TestRewriteStrmConfirmGuard] test_settings_html_has_rewrite_confirm_modal' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: '@click="cancelRewriteStrm()"', note: '[TestRewriteStrmConfirmGuard] test_settings_html_has_rewrite_confirm_modal' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'rewriteStrmConfirmOpen && cancelRewriteStrm()', note: '[TestRewriteStrmConfirmGuard] test_settings_html_rewrite_esc_chain' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'class="btn btn-primary" @click="confirmRewriteStrm()"', note: '[TestRewriteStrmConfirmGuard] test_settings_html_rewrite_headsup_tone — 確認鈕須 btn-primary（heads-up 非破壞性）' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string', pattern: 'btn-error" @click="confirmRewriteStrm()"', note: '[TestRewriteStrmConfirmGuard] test_settings_html_rewrite_headsup_tone — 不得用 btn-error（CD-96d-7 負守衛，與上一列互補）' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: 'settings.scraper.strm_mapping.rewrite_confirm.body', note: '[TestRewriteStrmConfirmGuard] test_settings_html_rewrite_i18n_body_with_count — body i18n key' },
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: 'pendingRewriteCount',
    scope: { anchor: /settings\.scraper\.strm_mapping\.rewrite_confirm\.body/, window: 200 },
    note: '[TestRewriteStrmConfirmGuard] test_settings_html_rewrite_i18n_body_with_count — body x-text 200 字視窗內須含 count 插值',
  },
  ...['title', 'cancel', 'confirm'].map((key) => ({
    file: 'web/templates/settings.html', kind: 'required-string', pattern: `settings.scraper.strm_mapping.rewrite_confirm.${key}`,
    note: '[TestRewriteStrmConfirmGuard] test_settings_html_rewrite_i18n_body_with_count — for-loop 3 key',
  })),
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'rewriteStrmConfirmOpen: false', note: '[TestRewriteStrmConfirmGuard] test_config_js_stubs_declared' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'pendingRewriteCount: 0', note: '[TestRewriteStrmConfirmGuard] test_config_js_stubs_declared' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'confirmRewriteStrm()', note: '[TestRewriteStrmConfirmGuard] test_config_js_methods_present' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'cancelRewriteStrm()', note: '[TestRewriteStrmConfirmGuard] test_config_js_methods_present' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: '/api/config/rewrite-strm?dry_run=true', note: '[TestRewriteStrmConfirmGuard] test_config_js_saveconfig_hook_condition — dry-run 計數呼叫' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'prevStrmMappings', note: '[TestRewriteStrmConfirmGuard] test_config_js_saveconfig_hook_condition — 存前快照（映射變更判定）' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: "['jellyfin', 'emby', 'kodi'].includes(this.form.externalManager)", note: '[TestRewriteStrmConfirmGuard] test_config_js_saveconfig_hook_condition — media-server 模式 gate（含 this.form. 前綴，勿與 scanner.html 版混淆）' },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: "'/api/config/rewrite-strm'",
    scope: /async confirmRewriteStrm\(\)[\s\S]*?(?=cancelRewriteStrm\(\))/,
    note: '[TestRewriteStrmConfirmGuard] test_config_js_confirm_calls_real_endpoint_and_toast — 實際改寫端點呼叫，無 dry_run（RWS-scope 方法體）',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'settings.scraper.strm_mapping.rewrite_done',
    scope: /async confirmRewriteStrm\(\)[\s\S]*?(?=cancelRewriteStrm\(\))/,
    note: '[TestRewriteStrmConfirmGuard] test_config_js_confirm_calls_real_endpoint_and_toast — rewrite_done toast i18n key（RWS-scope 方法體）',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'result.rewritten',
    scope: /async confirmRewriteStrm\(\)[\s\S]*?(?=cancelRewriteStrm\(\))/,
    note: '[TestRewriteStrmConfirmGuard] test_config_js_confirm_calls_real_endpoint_and_toast — toast 帶端點回的精確 rewritten 數（RWS-scope 方法體）',
  },
  // [lint-guard: pytest-justified｜method-block-scoped count｜CD-96d-5] test_config_js_confirm_calls_real_endpoint_and_toast
  // 內 `block.count("...rewrite_failed") >= 2`（live L9546-9547）子測 OPUS 裁決：CD-96d-5 是已定案 canonical
  // decision，字面維持「確定留 pytest」，本卡不建 RULES 列覆蓋（TASK-96d-T4.md「與 CD-96d-5 矛盾的研究發現」節提出
  // 可用 required-string + RWS-scope（見上 3 列同一 scope）+ count: 2 忠實表達的替代方案，供未來重新裁決參考，
  // 但本次遵照裁決不採納）。故該 pytest 方法本身（含已被上方 3 列覆蓋的前 3 段斷言）仍不可整刪——pytest 是以方法
  // 為刪除單位、非以 assert 為單位，T5 需處理此細節。

  // ==== 96e-T2：MIGRATE 組建網（TASK-96e-T2.md，10 live pytest class，只建網不刪 pytest）====

  // ---- [TestSwipeHelperGuard] web/static/js/shared/swipe.js（全 WF） ----
  {
    file: 'web/static/js/shared/swipe.js', kind: 'required-string',
    pattern: /export\s+function\s+detectSwipe\s*\(\s*startX\s*,\s*startY\s*,\s*endX\s*,\s*endY\s*,\s*threshold\s*\)/,
    note: '[TestSwipeHelperGuard] test_detect_swipe_signature — 五參數簽名',
  },
  { file: 'web/static/js/shared/swipe.js', kind: 'required-string', pattern: 'Math.abs(dX) > Math.abs(dY)', note: '[TestSwipeHelperGuard] test_axis_discrimination_present' },
  { file: 'web/static/js/shared/swipe.js', kind: 'required-string', pattern: 'Math.abs(dX) > threshold', note: '[TestSwipeHelperGuard] test_threshold_from_param_not_hardcoded — threshold 由參數傳入' },
  { file: 'web/static/js/shared/swipe.js', kind: 'forbidden-string', pattern: 'Math.abs(dX) > 50', note: '[TestSwipeHelperGuard] test_threshold_from_param_not_hardcoded — 不可寫死 50' },
  { file: 'web/static/js/shared/swipe.js', kind: 'required-string', pattern: "'left'", note: '[TestSwipeHelperGuard] test_direction_strings_present' },
  { file: 'web/static/js/shared/swipe.js', kind: 'required-string', pattern: "'right'", note: '[TestSwipeHelperGuard] test_direction_strings_present' },

  // ---- [TestCoverCacheBustGuard] state-lightbox.js refreshVideoData()（method-body brace-balanced，
  // stripLineComments: true — Opus 裁決 1：擴 dispatcher，不接受「target 移進行內注釋」fail-open）----
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /data\.video\.cover_url\s*=\s*[^;\n]*\+\s*['"]&t=/,
    scope: { anchor: /async\s+refreshVideoData\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[TestCoverCacheBustGuard] test_cover_url_has_cache_bust — cover_url cache-bust（stripLineComments 防注釋混淆 false-pass）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /data\.video\.cover_full_url\s*=\s*[^;\n]*\+\s*['"]&t=/,
    scope: { anchor: /async\s+refreshVideoData\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[TestCoverCacheBustGuard] test_cover_full_url_has_cache_bust — cover_full_url cache-bust（stripLineComments 防注釋混淆 false-pass）',
  },

  // ---- [TestSearchFileJsSubtitleHelper] web/static/js/pages/search/file.js ----
  { file: 'web/static/js/pages/search/file.js', kind: 'required-string', pattern: 'function stripSubtitleMarkers(', note: '[TestSearchFileJsSubtitleHelper] test_file_js_contains' },
  { file: 'web/static/js/pages/search/file.js', kind: 'required-string', pattern: '_SUBTITLE_BRACKETS', note: '[TestSearchFileJsSubtitleHelper] test_file_js_contains' },
  { file: 'web/static/js/pages/search/file.js', kind: 'required-string', pattern: '_SUBTITLE_TEXT_MARKERS', note: '[TestSearchFileJsSubtitleHelper] test_file_js_contains' },
  { file: 'web/static/js/pages/search/file.js', kind: 'forbidden-string', pattern: '/^中文字幕\\s*/', note: '[TestSearchFileJsSubtitleHelper] test_file_js_contains — 殘缺舊 regex 不可回歸' },
  {
    file: 'web/static/js/pages/search/file.js', kind: 'required-string', pattern: 'stripSubtitleMarkers(name)',
    scope: { anchor: /function\s+extractChineseTitle\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestSearchFileJsSubtitleHelper] test_extract_chinese_title_uses_strip_helper',
  },
  {
    file: 'web/static/js/pages/search/file.js', kind: 'forbidden-string', pattern: 'name.replace(/^中文字幕',
    scope: { anchor: /function\s+extractChineseTitle\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestSearchFileJsSubtitleHelper] test_extract_chinese_title_uses_strip_helper — 不可回歸內嵌殘缺 regex',
  },

  // ---- [TestLongPathWarning] web/static/js/pages/scanner/state-scan.js（WF + WIN(500)） ----
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'long_paths', note: '[TestLongPathWarning] test_scanner_js_long_path_warning' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'showToast', note: '[TestLongPathWarning] test_scanner_js_long_path_warning' },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', anyOf: true, pattern: ["'warn'", '"warn"'],
    scope: { anchor: /long_paths/, window: 500 },
    note: '[TestLongPathWarning] test_scanner_js_long_path_warning — warn toast type（500-char window）',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: '6000',
    scope: { anchor: /long_paths/, window: 500 },
    note: '[TestLongPathWarning] test_scanner_js_long_path_warning — toast duration',
  },
  // 103-T6：文案本體隨 i18n 收斂搬進 locales/zh_TW.json，守衛同步改錨到新家（遷移粒度守則：
  // 守衛跟著被守的內容走，不在 JS 側留字面誘餌註解——那會讓規則永遠綠、失去 load-bearing 性）。
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: '260',
    scope: { anchor: /"long_paths_warning"/, window: 160 },
    note: '[TestLongPathWarning] test_scanner_js_long_path_warning — 260 字元門檻（103-T6 起錨在 i18n 文案）',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string', pattern: 'debug.log',
    scope: { anchor: /"long_paths_warning"/, window: 160 },
    note: '[TestLongPathWarning] test_scanner_js_long_path_warning — debug.log 引導字串（103-T6 起錨在 i18n 文案）',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'scanner.toast.long_paths_warning',
    scope: { anchor: /long_paths/, window: 500 },
    note: '[TestLongPathWarning] 103-T6：JS 側須確實呼叫該 i18n key（接線檢查，防「文案在 JSON 但沒人用」假綠）',
  },

  // ---- [TestReadonlySourceErrorToastGuard] web/static/js/pages/scanner/state-scan.js（WF + WIN×2 + 複合窄 scope）----
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'data.readonly_stats', note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_source_errors' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'source_errors', note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_source_errors' },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', anyOf: true, pattern: ["'warn'", '"warn"'],
    scope: { anchor: /const srcErrors/, window: 1600 },
    note: "[TestReadonlySourceErrorToastGuard] test_done_toast_consults_source_errors + test_done_toast_consults_per_video_failed（共用 warn 斷言）。103-T6：文案搬 i18n 後 window.t() 呼叫較原字面長，'warn' 由 1300 外推到 1485，window 1300→1600。實測 anchor 後兩個 'warn' 落在 1485／2022，1600 只涵蓋第一個——刪掉真正的 'warn' 仍會 RED，未因放寬而假綠。",
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: '.failed',
    scope: { anchor: /const srcErrors/, window: 1300 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_per_video_failed',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'const noOutput',
    scope: { anchor: /const srcErrors/, window: 1200 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: '.no_output',
    scope: { anchor: /const srcErrors/, window: 1200 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'const unreachable',
    scope: { anchor: /const srcErrors/, window: 1200 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: '.unreachable',
    scope: { anchor: /const srcErrors/, window: 1200 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'const partial',
    scope: { anchor: /const srcErrors/, window: 1200 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: '.partial',
    scope: { anchor: /const srcErrors/, window: 1200 },
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'noOutput > 0',
    // Codex PR review（96e 替代網）：原 pytest 是 idx=js.find("const srcErrors") 起算
    // 1200-char window，window 內再 find "if (srcErrors > 0" 取 300-char cond_window。
    // 舊 [\s\S]*? 在兩 anchor 間無上限，若未來條件搬到 1200 字外 pytest 會 RED
    // 而 lint 仍 GREEN（fail-open）。改 {0,1168}：1200 扣掉 "const srcErrors"（15
    // 字）與 "if (srcErrors > 0"（17 字）字面長度；trailing 同理 300−17=283（pytest cond_window 自條件起算含 needle）。gap 量詞必須 lazy `{0,1168}?`——pytest window.find() 鎖「第一個」if 命中，greedy 會鎖窗內最後一個、兩條件並存時 fail-open（Codex 二審）。忠實對齊原窗語意（§11 fail-closed）。
    scope: /const\s+srcErrors[\s\S]{0,1168}?if\s*\(srcErrors\s*>\s*0[\s\S]{0,283}/,
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial — warn 判斷條件納入 noOutput',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'unreachable > 0',
    // Codex PR review（96e 替代網）：原 pytest 是 idx=js.find("const srcErrors") 起算
    // 1200-char window，window 內再 find "if (srcErrors > 0" 取 300-char cond_window。
    // 舊 [\s\S]*? 在兩 anchor 間無上限，若未來條件搬到 1200 字外 pytest 會 RED
    // 而 lint 仍 GREEN（fail-open）。改 {0,1168}：1200 扣掉 "const srcErrors"（15
    // 字）與 "if (srcErrors > 0"（17 字）字面長度；trailing 同理 300−17=283（pytest cond_window 自條件起算含 needle）。gap 量詞必須 lazy `{0,1168}?`——pytest window.find() 鎖「第一個」if 命中，greedy 會鎖窗內最後一個、兩條件並存時 fail-open（Codex 二審）。忠實對齊原窗語意（§11 fail-closed）。
    scope: /const\s+srcErrors[\s\S]{0,1168}?if\s*\(srcErrors\s*>\s*0[\s\S]{0,283}/,
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial — warn 判斷條件納入 unreachable',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'partial > 0',
    // Codex PR review（96e 替代網）：原 pytest 是 idx=js.find("const srcErrors") 起算
    // 1200-char window，window 內再 find "if (srcErrors > 0" 取 300-char cond_window。
    // 舊 [\s\S]*? 在兩 anchor 間無上限，若未來條件搬到 1200 字外 pytest 會 RED
    // 而 lint 仍 GREEN（fail-open）。改 {0,1168}：1200 扣掉 "const srcErrors"（15
    // 字）與 "if (srcErrors > 0"（17 字）字面長度；trailing 同理 300−17=283（pytest cond_window 自條件起算含 needle）。gap 量詞必須 lazy `{0,1168}?`——pytest window.find() 鎖「第一個」if 命中，greedy 會鎖窗內最後一個、兩條件並存時 fail-open（Codex 二審）。忠實對齊原窗語意（§11 fail-closed）。
    scope: /const\s+srcErrors[\s\S]{0,1168}?if\s*\(srcErrors\s*>\s*0[\s\S]{0,283}/,
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial — warn 判斷條件納入 partial',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string', pattern: 'pruned > 0',
    // Codex PR review（96e 替代網）：原 pytest 是 idx=js.find("const srcErrors") 起算
    // 1200-char window，window 內再 find "if (srcErrors > 0" 取 300-char cond_window。
    // 舊 [\s\S]*? 在兩 anchor 間無上限，若未來條件搬到 1200 字外 pytest 會 RED
    // 而 lint 仍 GREEN（fail-open）。改 {0,1168}：1200 扣掉 "const srcErrors"（15
    // 字）與 "if (srcErrors > 0"（17 字）字面長度；trailing 同理 300−17=283（pytest cond_window 自條件起算含 needle）。gap 量詞必須 lazy `{0,1168}?`——pytest window.find() 鎖「第一個」if 命中，greedy 會鎖窗內最後一個、兩條件並存時 fail-open（Codex 二審）。忠實對齊原窗語意（§11 fail-closed）。
    scope: /const\s+srcErrors[\s\S]{0,1168}?if\s*\(srcErrors\s*>\s*0[\s\S]{0,283}/,
    note: '[TestReadonlySourceErrorToastGuard] test_done_toast_consults_no_output_unreachable_partial — pruned 非警告，不可誤納入 warn 判斷',
  },

  // ---- [TestScannerCopyFailModal] state-scan.js + scanner.html（全 WF） ----
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'openCopyFailModal', note: '[TestScannerCopyFailModal] test_scanner_copy_fail_modal_contains' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'closeCopyFailModal', note: '[TestScannerCopyFailModal] test_scanner_copy_fail_modal_contains' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: 'copyFailModalOpen', note: '[TestScannerCopyFailModal] test_scanner_copy_fail_modal_contains' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'copy_fail_modal.title', note: '[TestScannerCopyFailModal] test_scanner_copy_fail_modal_contains' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'copy-fail-pre', note: '[TestScannerCopyFailModal] test_scanner_copy_fail_modal_contains' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'copyFailModalOpen && closeCopyFailModal', note: '[TestScannerCopyFailModal] test_scanner_copy_fail_modal_contains' },

  // ---- [TestPageLifecycleGuard] base.html + 4 頁 __registerPage（live 是 4 頁，非 plan-96e 文字寫的 3 頁）----
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'page-lifecycle.js', note: '[TestPageLifecycleGuard] test_base_html_loads_page_lifecycle' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: '__registerPage', note: '[TestPageLifecycleGuard] test_settings_js_calls_register_page' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: '__registerPage', note: '[TestPageLifecycleGuard] test_search_main_js_calls_register_page' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', pattern: '__registerPage', note: '[TestPageLifecycleGuard] test_showcase_core_calls_register_page' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string', pattern: '__registerPage', note: '[TestPageLifecycleGuard] test_scanner_html_calls_register_page（方法名誤導，實讀 .js）' },

  // ---- [TestMotionLabStateGuard] motion_lab.html + motion-lab-state.js（WF ×4 + EL ×1，§11 gotcha #1）----
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'x-data="motionLabPage"', note: '[TestMotionLabStateGuard] test_motion_lab_html_contains' },
  { file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: 'motion-lab-state.js', note: '[TestMotionLabStateGuard] test_motion_lab_html_contains' },
  {
    file: 'web/templates/motion_lab.html', kind: 'forbidden-string', pattern: /x-data="[^"]{100,}"/,
    note: '[TestMotionLabStateGuard] test_motion_lab_html_contains — 無巨型 inline x-data 物件（39b-T1 已抽離至 JS）',
  },
  {
    file: 'web/templates/motion_lab.html', kind: 'required-string', pattern: /<script[^>]*motion-lab-state\.js[^>]*>/,
    note: '[TestMotionLabStateGuard] test_motion_lab_html_contains — motion-lab-state.js script tag 存在',
  },
  {
    // Codex PR review（96e 替代網）：原 pytest 對「所有」匹配 motion-lab-state.js 的
    // script tag 逐一（for tag in tags）禁 defer；舊寫法用 scope（RegExp.exec 只取
    // 第一個匹配）只驗第一個 tag，若日後出現第二個同 src tag 帶 defer 會漏過
    // （fail-open）。改 forbidden-string 雙 lookahead（無 scope）：pattern 本身表達
    // 「任何 script tag 同時含 motion-lab-state.js 與 defer」＝ RED，whole-text scan
    // 天然涵蓋所有出現點，不限首個。
    file: 'web/templates/motion_lab.html', kind: 'forbidden-string',
    pattern: /<script(?=[^>]*\bdefer\b)(?=[^>]*motion-lab-state\.js)[^>]*>/,
    note: '[TestMotionLabStateGuard] test_motion_lab_html_contains — 任一 motion-lab-state.js script tag 皆不可帶 defer（whole-text scan，涵蓋所有出現點）',
  },
  { file: 'web/static/js/pages/motion-lab-state.js', kind: 'required-string', pattern: 'function motionLabPage()', note: '[TestMotionLabStateGuard] test_motion_lab_state_js_contains' },
  { file: 'web/static/js/pages/motion-lab-state.js', kind: 'required-string', pattern: 'init()', note: '[TestMotionLabStateGuard] test_motion_lab_state_js_contains' },
  { file: 'web/static/js/pages/motion-lab-state.js', kind: 'required-string', pattern: 'destroy()', note: '[TestMotionLabStateGuard] test_motion_lab_state_js_contains' },

  // ---- [TestScannerStateGuard] scanner.html（只建 subtest 1，subtest 2 test_scanner_no_inline_script
  // 極性衝突 + per-match 行數計數無對應 kind，維持不建網、pytest-justified 殘餘——Opus 裁決 2）----
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'pre_alpine_module', note: '[TestScannerStateGuard] test_scanner_html_has_pre_alpine_module_block' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'scanner/main.js', note: '[TestScannerStateGuard] test_scanner_html_has_pre_alpine_module_block' },

  // ---- [TestFetchSamplesButton] showcase.html test_html_contains（HTML-attr 半邊）
  // + test_core_js_contains（Opus 裁決 3：內部機制歸屬 96e，字串 pin 到實際所在檔）----
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'button', className: 'fetch-samples-btn',
    required: ['x-show=', 'sample_images', '@click=', 'fetchSamples', ':disabled=', '_fetchSamplesFailed'],
    note: '[TestFetchSamplesButton] test_html_contains — fetch-samples-btn 開標籤必要屬性',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', anyOf: true, pattern: [/^!!/, '=== true'],
    scope: /<button\b(?=[^>]*class="[^"]*(?<![\w-])fetch-samples-btn(?![\w-])[^"]*")[^>]*:disabled=["']([^"']+)["'][^>]*>/,
    note: '[TestFetchSamplesButton] test_html_contains — :disabled boolean coercion（!! 開頭或 === true，§11 gotcha #1 AV capture-group scope）',
  },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'x-text=', note: '[TestFetchSamplesButton] test_html_contains（pytest 原斷言 or-html 恆等 WF，照抄行為）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'showcase.samples.fetch_btn', note: '[TestFetchSamplesButton] test_html_contains' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'bi bi-cloud-download', note: '[TestFetchSamplesButton] test_html_contains' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '_fetchSamplesLoading', note: '[TestFetchSamplesButton] test_html_contains' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'showcase.samples.fetching', note: '[TestFetchSamplesButton] test_html_contains' },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: '☁',
    scope: /<button\b(?=[^>]*class="[^"]*(?<![\w-])fetch-samples-btn(?![\w-])[^"]*")[^>]*>[\s\S]*?<\/button>/,
    note: '[TestFetchSamplesButton] test_html_contains — btn_region 內不可含 ☁ emoji（element-region-scoped）',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: /_fetchSamplesLoading\s*:/,
    note: '[TestFetchSamplesButton] test_core_js_contains — state 初始化（pin 到實際所在檔 state-actress.js，pytest 原是雙檔串接 in 判斷）',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: /_fetchSamplesFailed\s*:/,
    note: '[TestFetchSamplesButton] test_core_js_contains — state 初始化（pin 到實際所在檔 state-actress.js）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: /^\s+async\s+fetchSamples\s*\(/m,
    note: '[TestFetchSamplesButton] test_core_js_contains — fetchSamples method 定義（regex 鎖方法定義，防被 _fetchSamplesFailed/_fetchSamplesLoading 子字串矇混，149a-T5 修）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_fetchSamplesFailed = {}',
    scope: { anchor: /closeLightbox\s*\(\s*\)\s*\{/, window: 2000 },
    note: '[TestFetchSamplesButton] test_core_js_contains — closeLightbox() 須 reset _fetchSamplesFailed = {}（2000-char window）',
  },

  // ── 96e-T3（TestNoAlertInSearchJs）：clipboard availability guard ──────────
  // Opus 裁決 1：plan 草案 SEL_CLIPBOARD_OPTIONAL_CHAIN（eslint per-node ban）會在
  // 4/5 現行合法檔（guard-if / 三元條件形式，呼叫本身非 optional）立即 RED，否決。
  // 改走 static_guard_lint：scanner/state-scan.js 兩處呼叫點 guard count:2（required-string）
  // + 全 web/static/js 檔級 pairing（paired-string，新 kind）。
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: 'navigator.clipboard?.writeText', count: 2,
    note: '[TestNoAlertInSearchJs] test_scanner_clipboard_has_availability_guard — scanner/state-scan.js 需 ≥2 處 guard（copyLogs L1053 附近 + copyOutputPath L720 附近）',
  },
  {
    file: { dir: 'web/static/js', ext: ['.js'], recursive: true }, kind: 'paired-string',
    ifPresent: 'navigator.clipboard.writeText', thenRequire: 'navigator.clipboard?.writeText',
    note: '[TestNoAlertInSearchJs] test_all_clipboard_writetext_files_have_availability_guard — 全 web/static/js 任何用 navigator.clipboard.writeText 的檔案須同檔含 ?. guard 形式',
  },

  // ── 96e-T3（TestSimilarSlotGsapGuard）：GSAP width literal 守衛（9 條） ─────
  // Opus 裁決 2：plan 草案 SEL_GSAP_WIDTH_LITERAL（AST width property ban）會擴大涵蓋範圍
  // （禁一切數字 width literal，非原 pytest 只防特定歷史迴歸值）+ eslint 無法表達正向必須
  // 存在斷言（POSTER_CROP_RATIO/SLOT_W/MAIN_W/width: 107），否決。全走 static_guard_lint。
  {
    file: 'web/static/js/shared/constellation/animations.js', kind: 'forbidden-string', pattern: 'width: 120',
    note: '[TestSimilarSlotGsapGuard] test_animations_no_width_120_literal',
  },
  {
    file: 'web/static/js/shared/constellation/animations.js', kind: 'forbidden-string', pattern: 'width: 200',
    note: '[TestSimilarSlotGsapGuard] test_animations_no_width_200_literal',
  },
  {
    file: 'web/static/js/shared/constellation/animations.js', kind: 'required-string', pattern: 'POSTER_CROP_RATIO',
    note: '[TestSimilarSlotGsapGuard] test_animations_has_poster_crop_ratio_const',
  },
  {
    file: 'web/static/js/shared/constellation/animations.js', kind: 'required-string', pattern: 'SLOT_W',
    note: '[TestSimilarSlotGsapGuard] test_animations_has_slot_w_const',
  },
  {
    file: 'web/static/js/shared/constellation/animations.js', kind: 'required-string', pattern: 'MAIN_W',
    note: '[TestSimilarSlotGsapGuard] test_animations_has_main_w_const',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'forbidden-string', pattern: 'width: 120',
    note: '[TestSimilarSlotGsapGuard] test_state_similar_no_width_120',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'width: 107',
    note: '[TestSimilarSlotGsapGuard] test_state_similar_has_width_107',
  },
  {
    file: 'web/static/js/pages/motion-lab/constellation-host.js', kind: 'forbidden-string', pattern: 'width: 120',
    note: '[TestSimilarSlotGsapGuard] test_constellation_host_no_width_120',
  },
  {
    file: 'web/static/js/pages/motion-lab/constellation-host.js', kind: 'required-string', pattern: 'width: 107',
    note: '[TestSimilarSlotGsapGuard] test_constellation_host_has_width_107',
  },

  // ── 96e-T3（TestVideoPlaybackGuard〔b〕）：3 個 .py 檔硬編影片副檔名 set 禁令 ──
  {
    file: 'core/gallery_scanner.py', kind: 'forbidden-string',
    pattern: /=\s*\{[^}]*'\.mp4'[^}:]*'\.avi'[^}:]*\}/s,
    note: '[TestVideoPlaybackGuard] test_no_hardcoded_video_extensions_in_modules — gallery_scanner.py 不可硬編影片副檔名 set（須 import core.video_extensions SSOT）',
  },
  {
    file: 'web/routers/scanner.py', kind: 'forbidden-string',
    pattern: /=\s*\{[^}]*'\.mp4'[^}:]*'\.avi'[^}:]*\}/s,
    note: '[TestVideoPlaybackGuard] test_no_hardcoded_video_extensions_in_modules — scanner.py 不可硬編影片副檔名 set',
  },
  {
    // TASK-150a-T1：get_video() 搬到 gallery_media.py 後的對等規則（scanner.py 原規則不動）。
    file: 'web/routers/gallery_media.py', kind: 'forbidden-string',
    pattern: /=\s*\{[^}]*'\.mp4'[^}:]*'\.avi'[^}:]*\}/s,
    note: '[TestVideoPlaybackGuard] test_no_hardcoded_video_extensions_in_modules — gallery_media.py 不可硬編影片副檔名 set（須 import core.video_extensions SSOT）',
  },
  {
    file: 'windows/pywebview_api.py', kind: 'forbidden-string',
    pattern: /=\s*\{[^}]*'\.mp4'[^}:]*'\.avi'[^}:]*\}/s,
    note: '[TestVideoPlaybackGuard] test_no_hardcoded_video_extensions_in_modules — pywebview_api.py 不可硬編影片副檔名 set',
  },

  // ── 96e-T3（TestVideoPlaybackGuard，Opus 自裁納入）：state-videos.js JS 半邊 ────
  // plan CD-96e-5 三分法漏列的第四半邊（test_video_api_files_contain 的
  // '/api/gallery/player' in state-videos.js 斷言）——不補則 T5 整刪
  // test_video_api_files_contain 時會靜默失網，故本卡納入。
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: '/api/gallery/player',
    note: '[TestVideoPlaybackGuard] test_video_api_files_contain（JS 半邊，plan CD-96e-5 三分法未明列，96e-T3 研究補洞）',
  },
  {
    // CD-120a-11：playVideo 方法體內禁止 await——window.open 前若插入 await，
    // 手機／區網按播放會被瀏覽器當廣告彈窗擋掉、什麼都不會發生。
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string', pattern: 'await',
    scope: { anchor: /playVideo\s*\(\s*path\s*\)\s*\{/, braceBalanced: true },
    note: '[CD-120a-11] playVideo 內 window.open 前若插入 await，手機／區網按播放會被瀏覽器當廣告彈窗擋掉、什麼都不會發生',
  },

  // 120a-T1：.lb-full 原圖載不到時才會出現提示 pill。綁定必須是 img.lb-full 開標籤屬性
  // （tag-scan class-tag），不得用裸 required-string——註解裡同一句話會 fail-open（FE-GUARD-03）。
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'img', className: 'lb-full',
    required: ['@error="_handleLbFullError($event)"'],
    note: '[120a-T1] .lb-full 必須綁 @error=_handleLbFullError，否則原圖載不到時封面區沒有提示',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: 'pointer-events: none',
    scope: { anchor: /\.lb-full-hint\s*\{/, braceBalanced: true },
    note: '[120a-T1] .lb-full-hint 必須 pointer-events:none，否則會擋住封面操作區／sparkle 點擊',
  },
  {
    // 120a-T4：pill 可見性必須綁「圖沒載成功」。錨到 .lb-full-hint 開標籤
    // （tag-scan class-tag），不得用裸 required-string——註解裡同一句話會 fail-open（FE-GUARD-03）。
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'lb-full-hint',
    required: ['!_lbFullLoaded'],
    note: '[120a-T4] 這個條件掉了，翻片時機不巧會在一張好好的封面上蓋一句「封面讀不到」',
  },

  // ── 96e-T4：TestPageTransitionDomGuard / TestPageTransitionSettingsScopeGuard /
  // TestT4FooterStructure 三個混合 class 的 template/JS 半邊（CSS 半邊已由 96c
  // css-guard CG-XP-03/04/05 承接）。只建網，不刪 pytest（T5 兩半邊皆綠後整刪）。────

  // A1 — base.html <main id="main-content"> + <nav id="sidebar">（whole-file，正向，合併一條）
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: ['id="main-content"', 'id="sidebar"'],
    note: '[TestPageTransitionDomGuard] test_base_html_main_content_id + test_base_html_sidebar_id',
  },
  // A2 — head-region 內 pagereveal/pageswap/skipTransition（head-scoped，正向）
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: ['pagereveal', 'pageswap', 'skipTransition'],
    scope: /[\s\S]*?(?=<\/head>)/,
    note: '[TestPageTransitionDomGuard] test_base_html_showcase_skip_script_in_head — head-scoped 三 token',
  },
  // A3 — 含 skipTransition 的 <script> 開標籤不可帶 module/defer/async（element-bound，負向 ×4）
  {
    file: 'web/templates/base.html', kind: 'forbidden-string',
    pattern: ['type="module"', "type='module'", 'defer', 'async'],
    scope: /(<script\b[^>]*>)(?:(?!<\/script>)[\s\S])*?skipTransition/,
    note: '[TestPageTransitionDomGuard] test_base_html_showcase_skip_script_in_head — VT head-script 負向（CD-96-20c，required-string-only port 會漏此負向斷言）',
  },

  // B — theme-transition.js class lifecycle（whole-file，正向 ×3）
  {
    file: 'web/static/js/pages/settings/theme-transition.js', kind: 'required-string',
    pattern: ["classList.add('theme-transition-active')", 'transition.finished', "classList.remove('theme-transition-active')"],
    note: '[TestPageTransitionSettingsScopeGuard] test_theme_transition_js_class_lifecycle',
  },

  // C1 — showcase.html footer 結構/快捷鍵/pager 17 個字串（whole-file，正向）
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      'class="showcase-footer"', 'class="footer-left"', 'class="footer-center"', 'class="footer-right"',
      'bi-film', 'bi-person-circle', '<kbd>A</kbd>', '<kbd>S</kbd>', '<kbd>ESC</kbd>', '<kbd>←</kbd>', '<kbd>→</kbd>',
      'class="footer-pager"', 'x-show="!showFavoriteActresses && totalPages > 1"',
      'prevPage()', 'nextPage()', 'x-ref="pageSelectFooter"', 'class="pager-current"', 'openPagePicker',
    ],
    note: '[TestT4FooterStructure] test_showcase_html_contains — footer 結構/快捷鍵/pager 存在',
  },
  // C2 — 舊 class="showcase-status-bar" 不應殘留（whole-file，負向）
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: 'class="showcase-status-bar"',
    note: '[TestT4FooterStructure] test_showcase_html_contains — 舊 status-bar class 不應殘留',
  },
  // C3 — showcase-footer 開標籤不可含 x-data（element-bound，負向）
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'showcase-footer',
    forbidden: ['x-data'],
    note: '[TestT4FooterStructure] test_showcase_html_contains — showcase-footer 開標籤不可含 x-data（§11 gotcha 1/3：element-bound + class-token 邊界，用既有 buildTagWithClassRegex）',
  },
  // C4 — state-videos.js 含 openPagePicker + showPicker（whole-file，正向，跨檔）
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: ['openPagePicker', 'showPicker'],
    note: '[TestT4FooterStructure] test_showcase_html_contains — core.js openPagePicker 用 showPicker 實作',
  },

  // ==== 98b-T3：focal render 綁定守衛（binding existence + helper existence + imperative pairing）====
  // north-star：template `:style` 綁定字面 / imperative helper 存在性是靜態字串契約 → lint 不進 pytest。
  // no-`!important` 不變式（inline 必勝前提）由 css-guard.mjs CG-FOCAL-01 守（object-position 半邊）。

  // -- Binding existence（99a-T2：:style="focalStyle(...)" → @load="applyCellFocal(...)" load-gated
  //    imperative wiring；98b-T6 姊妹案例，reactive :style 不會因 load 事件重跑，見 TASK-99a-T2 §4）--
  // 錨定完整 @load="..." 屬性值（非裸 applyCellFocal(...) 子字串）：F1/F4 的裸呼叫式也出現在
  // 同 tag 的 x-init $watch callback body 內（() => applyCellFocal(...)），若只認裸子字串，刪掉
  // @load 的 applyCellFocal 仍會被 $watch body 命中而假綠（偵測力洩漏）。錨 @load=" 前綴 + 完整值
  // 才唯一。F2 無 $watch，其 (anchor.id) 參數形已唯一，但一併錨 @load=" 前綴保持一致。
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@load="video._imgLoaded = true; applyCellFocal($el, video)"', note: '[TestFocalRenderGuard] F1 grid img @load applyCellFocal wiring（錨完整 @load 值，防 $watch body 假綠）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@load="applyCellFocal($el, _getSlotItem(anchor.id))"', note: '[TestFocalRenderGuard] F2 similar desktop slot img @load applyCellFocal wiring' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@load="applyCellFocal($el, item)"', note: '[TestFocalRenderGuard] F4 similar mobile burst img @load applyCellFocal wiring（錨完整 @load 值，防 $watch body 假綠）' },
  // -- $watch existence：grid / mobile 兩站（穩定物件參考）需 auto_focal + crop_mode 即時重套；
  //    similar 桌面 slot 故意不加（x-for scope 只有 anchor，無穩定 video/item 可 $watch，見 §3 F2） --
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "$watch('video.auto_focal'", note: '[TestFocalRenderGuard] F1 grid x-init $watch(video.auto_focal) 即時重套' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "$watch('video.crop_mode'", note: '[TestFocalRenderGuard] F1 grid x-init $watch(video.crop_mode) 即時重套' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "$watch('item.auto_focal'", note: '[TestFocalRenderGuard] F4 mobile drill x-init $watch(item.auto_focal) 即時重套' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "$watch('item.crop_mode'", note: '[TestFocalRenderGuard] F4 mobile drill x-init $watch(item.crop_mode) 即時重套' },

  // -- Helper existence：state-videos.js / state-similar.js 皆改 import focal-cell.js（applyCellFocal）--
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: "'@/shared/focal-cell.js'", note: '[TestFocalRenderGuard] state-videos.js imports focal-cell.js' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string', pattern: 'applyCellFocal', note: '[TestFocalRenderGuard] state-videos.js 揭露 applyCellFocal 供 template 呼叫' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: "'@/shared/focal-cell.js'", note: '[TestFocalRenderGuard] state-similar.js imports focal-cell.js' },
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'applyFocalToImg', note: '[TestFocalRenderGuard] state-similar.js applyFocalToImg helper' },

  // -- Imperative pairing：state-similar.js applyFocalToImg 出現 >=7 次（helper def 1 + I-a…I-e/I-g 六個 .src= 成對）--
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string', pattern: 'applyFocalToImg', count: 7, note: '[TestFocalRenderGuard] state-similar.js applyFocalToImg helper + 6 imperative pairings（I-a..I-e,I-g；count 鎖成對，移除任一 .src= 配對即 RED）' },

  // -- Imperative pairing：BurstPicker 鏡射來源卡 objectPosition（focal-agnostic，只搬呈現）--
  { file: 'web/static/js/shared/burst-picker.js', kind: 'required-string', pattern: 'coverImg.style.objectPosition = selectedImg.style.objectPosition', note: '[TestFocalRenderGuard] I-f burst-picker.js 正常動畫 objectPosition 鏡射' },
  { file: 'web/static/js/shared/burst-picker.js', kind: 'required-string', pattern: '_covImg.style.objectPosition = _selImg.style.objectPosition', note: '[TestFocalRenderGuard] I-f burst-picker.js reduced-motion objectPosition 鏡射' },

  // ==== PR#108 Codex 二審 P2-A：picker 開啟時擋女優切換（防張冠李戴）====
  // prevActressLightbox()/nextActressLightbox() 是鍵盤 ArrowLeft/Right 女優分支
  // （handleKeydown）與 .lightbox-nav-prev/-next @click 的共同 chokepoint；手機 swipe
  // 已在 _lbTouchEnd 對 _pickerOpen 做同語意 pure-block guard（獨立、非本規則涵蓋範圍）。
  // scope-anchored（braceBalanced）鎖住 guard 存在於「這兩個函式本體內」，而非全檔任意處
  // 出現同一字面字串——防未來重構把 guard 搬去別的、不涵蓋鍵盤/點擊路徑的地方卻讓 flat
  // required-string 誤判通過。
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'if (this._pickerOpen) return;',
    scope: { anchor: /prevActressLightbox\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[P2-A pickerOpen-guard] PR#108 二審：prevActressLightbox() 起手擋 picker 開啟時的女優切換（張冠李戴防護）',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'if (this._pickerOpen) return;',
    scope: { anchor: /nextActressLightbox\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[P2-A pickerOpen-guard] PR#108 二審：nextActressLightbox() 起手擋 picker 開啟時的女優切換（張冠李戴防護）',
  },

  // ==== PR#108 nit-1：P2-A 的視覺對應——picker 開啟時女優導覽箭頭必須隱藏 ====
  // 上面兩條鎖「點了不會張冠李戴」，這兩條鎖「不會出現死點擊」：沒有 `!_pickerOpen &&`
  // 箭頭仍 x-show 可見、點下去 P2-A guard 純擋 ⇒ 不換人；且 nav 的 @click.stop 壓掉
  // overlay 的 @click.outside（Alpine .outside 是 bubble-phase）⇒ 也不關 picker ⇒
  // 零回饋死點擊，違反 repo「絕不點了沒反應」。
  // pattern 含整條三元式＝連**影片分支維持原樣**一起鎖（見下）。運算元順序被 pattern
  // 固定只是鎖住出貨形狀，不代表順序承重——Alpine effect 每次重新收集依賴，短路未讀到的
  // 運算元不會造成 stale（兩種順序皆安全，詳見 showcase.html 該處註解）。
  // ⚠️ 影片分支刻意不加可見性 guard：hero-card 開 picker 後按箭頭走 prev/nextLightboxVideo
  // ＝真的會換片、不是死點擊，藏掉反而是回歸。但該路徑**另有既有缺陷**（未 _closePicker()
  // ⇒ _pickerOpen 洩漏），正解是排序（函式開頭補 _closePicker()）而非旗標，屬影片路徑改動、
  // 需獨立 CDP 驗證，已列 follow-up——**不要**把它誤讀成「影片分支已經沒事」。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="!_maskVisible && (showFavoriteActresses ? (!_pickerOpen && actressLightboxIndex > 0) : hasVisiblePrev())"',
    scope: { anchor: /<button class="lightbox-nav lightbox-nav-prev"/, window: 400 },
    note: '[nit-1 nav-arrow-picker] PR#108：picker 開啟時隱藏女優「上一位」箭頭（防死點擊）；影片分支 hasVisiblePrev() 維持零改動',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="!_maskVisible && (showFavoriteActresses ? (!_pickerOpen && actressLightboxIndex < filteredActressCount - 1) : hasVisibleNext())"',
    scope: { anchor: /<button class="lightbox-nav lightbox-nav-next"/, window: 400 },
    note: '[nit-1 nav-arrow-picker] PR#108：picker 開啟時隱藏女優「下一位」箭頭（防死點擊）；影片分支 hasVisibleNext() 維持零改動',
  },

  // ---- [TestHelpAutoCheckToggle] help.html：107-P1-T3 啟動時檢查更新 toggle ----
  { file: 'web/templates/help.html', kind: 'required-string', pattern: 'data-is-desktop=', note: '[lint-guard 107-P1-T3] .help-container 注入 is_desktop 訊號（init gate 輸入）' },
  { file: 'web/templates/help.html', kind: 'required-string', pattern: 'data-auto-check-update=', note: '[lint-guard 107-P1-T3] .help-container 注入 auto_check_update 初值（SSR，無 fetch race）' },
  { file: 'web/templates/help.html', kind: 'required-string', pattern: 'x-model="autoCheckUpdate"', note: '[lint-guard 107-P1-T3] toggle 綁 autoCheckUpdate state（AC-A1）' },
  { file: 'web/templates/help.html', kind: 'required-string', pattern: '@change="saveAutoCheckUpdate()"', note: '[lint-guard 107-P1-T3] toggle 切換即時 PUT 持久化（AC-A1）' },
  { file: 'web/templates/help.html', kind: 'required-string', pattern: "t('help.hero.auto_check_toggle')", note: '[lint-guard 107-P1-T3] toggle 文案走 i18n key（不硬編碼）' },
  // help.js 必須落在 pre_alpine_module block（Alpine Core defer 之前）——ES module 隱式 defer，
  // 放 extra_js（Alpine 之後）會讓 alpine:init listener 註冊太晚、helpPage 靜默不 hydrate（no error，
  // CDP-only 才抓得到；107-P1-T3 CDP 實測踩過）。scope 視窗鎖 module script 緊接 block 內，防移回 extra_js。
  // 參 gotchas-frontend §「ESM type=module 與 Alpine CDN defer 的初始化時序」。
  {
    file: 'web/templates/help.html', kind: 'required-string',
    pattern: 'pages/help.js',
    // scope = pre_alpine_module block BODY（capture group）。若 help.js 移出此 block（如移回
    // extra_js），block body 不再含它 → RED。用 block body 而非 char-window：緊鄰的 extra_js
    // block 落在固定字元窗內會讓 window 版假綠（Codex/Sonnet mutation 抓到，見 feedback_mutation_anchor_precision）。
    scope: /\{%\s*block pre_alpine_module\s*%\}([\s\S]*?)\{%\s*endblock\s*%\}/,
    note: '[lint-guard 107-P1-T3] help.js module script 須在 pre_alpine_module block body 內（早於 Alpine Core，防 hydrate 時序 bug 回歸）',
  },
  // 遷自 tests/unit/test_frontend_lint.py TestHelpPage.test_help_html_contains（SA-pre-6：
  // 該 class 無 [lint-guard] 標記，兩條純 HTML 屬性存在性字面斷言應走 lint 而非 pytest）。
  {
    file: 'web/templates/help.html', kind: 'required-string',
    pattern: 'type="module" src="/static/js/pages/help.js"',
    note: '[lint-guard 107-P1-T3] help.js 以 ES module 載入（隱式 defer；alpine:init 註冊 helpPage，時序安全）— 遷自 test_frontend_lint.py TestHelpPage',
  },
  {
    file: 'web/templates/help.html', kind: 'forbidden-string',
    pattern: 'defer',
    scope: /<script[^>]*help\.js[^>]*>/,
    note: '[lint-guard 107-P1-T3] help.js script tag 禁顯式 defer（module 已隱式 defer）— 遷自 test_frontend_lint.py',
  },

  // ---- [lint-guard:110b-T6] help.js：/api/trigger-update 三層護欄的自訂 header ----
  // 端點（web/app.py trigger_update）要求 X-OpenAver-Desktop-Action header 存在
  // 才放行（CD-110b-5 ③）。這個 header 一旦被誰「清理」掉，桌面版更新按鈕會
  // 靜默壞掉（回 403，使用者只看到 toast 錯誤）——純 JS 字面字串存在性，走 lint
  // 不走 pytest（CLAUDE.md「Lint 守衛規則」north-star）。
  // P2-2 fix（Codex PR #122）：原本是 whole-file required-string，只證明字面字串「在
  // 檔案某處存在」，不證明它真的在 confirmUpdate() 的 fetch 呼叫裡——把它搬進同檔案
  // 的註解、常數、或無關 method 都能維持全綠，但桌面更新會靜默 403。改用既有的
  // {anchor, braceBalanced} scope 機制（見本檔開頭 §scope 三形式）把掃描範圍收斂到
  // confirmUpdate() 的大括號平衡方法體，並加開 stripLineComments（同 §「rule.stripLineComments」
  // 段落）防止字面字串被搬進方法體內的行內註解仍判線過。兩者都是本檔既有的表驅動能力，
  // 沿用形狀、非新發明機制。
  {
    file: 'web/static/js/pages/help.js', kind: 'required-string',
    pattern: 'X-OpenAver-Desktop-Action',
    scope: { anchor: /async\s+confirmUpdate\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 110b-T6] confirmUpdate() fetch 帶自訂 header，防 /api/trigger-update 護欄靜默失效（P2-2：錨定 method body + 剝註解，防字面移出 fetch 仍全綠）',
  },

  // ---- [lint-guard:108-T4] G4：js-open-folder marker 只在兩顆 folder 按鈕上（T3 鎖）----
  // 108-T3 把「隱藏 folder 按鈕」的判斷全部收斂到 CSS 的 .js-open-folder marker（G3，
  // css-guard.mjs CG-TOUCH-03）；若這個 class 被誤搬到 play/enrich 鈕、或多加了第三個，
  // CSS gate 會安靜地隱藏/漏藏錯的按鈕（跑起來看不出來，要點兩下才發現）。三條互補：
  //  G4a：全檔恰好 2 個 .js-open-folder（防「多加了一個」）。
  //  G4b/G4c：卡片格 / 燈箱 各自的 folder 按鈕，逐 element scope 綁 openLocal(＋bi-folder2-open
  //           圖示（防「搬到別的按鈕」——被搬走那顆的 scope 內容不再含這兩者）。
  {
    file: 'web/templates/showcase.html', kind: 'structure-count',
    pattern: /\bjs-open-folder\b/,
    count: 2,
    note: '[lint-guard:108-T4] G4a：js-open-folder marker 須恰好出現在 2 顆按鈕（卡片格 + 燈箱），不多不少',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ['openLocal(', 'bi-folder2-open'],
    scope: /<button class="btn-glass-circle js-open-folder"[\s\S]*?<\/button>/,
    note: '[lint-guard:108-T4] G4b：卡片格 .js-open-folder 按鈕須綁 openLocal( 且圖示為 bi-folder2-open（element-scoped，非全檔字串存在）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: ['playVideo(', 'enrichVideo(', 'bi-play-fill', 'enrich-btn'],
    scope: /<button class="btn-glass-circle js-open-folder"[\s\S]*?<\/button>/,
    note: '[lint-guard:108-T4] G4b-neg：卡片格 .js-open-folder 按鈕不得混進 play/enrich 的 handler 或圖示（誤搬 class 的反向鎖）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ['openLocal(', 'bi-folder2-open'],
    scope: /<button class="lb-action-btn js-open-folder"[\s\S]*?<\/button>/,
    note: '[lint-guard:108-T4] G4c：燈箱 .js-open-folder 按鈕須綁 openLocal( 且圖示為 bi-folder2-open（element-scoped，非全檔字串存在）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: ['playVideo(', 'enrichVideo(', 'bi-play-fill', 'enrich-btn'],
    scope: /<button class="lb-action-btn js-open-folder"[\s\S]*?<\/button>/,
    note: '[lint-guard:108-T4] G4c-neg：燈箱 .js-open-folder 按鈕不得混進 play/enrich 的 handler 或圖示（誤搬 class 的反向鎖）',
  },

  // ---- [lint-guard:113d-T4] showcase toast 語意修正（四鍵 lookup map，禁動態拼接）----
  // showcase.html:1484/1485 原本是二元判斷（error : success），'info'/'warning' 落到
  // else → 綠色打勾/裸樣式（spec §4.4）。改成 static lookup map 而非 `alert-${type}`
  // 動態拼接是刻意的（CD-113d-6）：Tailwind 官方明文列動態拼接為反模式，本庫其餘四頁
  // 的動態拼接現在能動純屬僥倖（靠別的檔案剛好有完整字面字串被掃進編譯產物）。
  // class map／icon map 兩條鎖的是「每個 class 與它對應的條件」，不是「四個字串存在」
  // ——單純字串存在性測不出 warning 被錯映成 info 這種對應錯誤（Codex plan review P2）。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      "'alert-success': $store.toast.type === 'success'",
      "'alert-error':   $store.toast.type === 'error'",
      "'alert-warning': $store.toast.type === 'warning'",
      "'alert-info':    $store.toast.type === 'info'",
    ],
    scope: /<div class="alert fluent-toast"[\s\S]*?<\/div>/,
    note: '[lint-guard:113d-T4] showcase toast class map 四鍵逐字對應（鎖住每個 class 與它的條件，不是字串存在性）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      "'bi-check-circle':         $store.toast.type === 'success'",
      "'bi-exclamation-circle':   $store.toast.type === 'error'",
      "'bi-exclamation-triangle': $store.toast.type === 'warning'",
      "'bi-info-circle':          $store.toast.type === 'info'",
    ],
    scope: /<div class="alert fluent-toast"[\s\S]*?<\/div>/,
    note: '[lint-guard:113d-T4] showcase toast icon map 四鍵逐字對應',
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: 'alert-${',
    note: '[lint-guard:113d-T4] showcase toast 禁止動態拼接 class（`` `alert-${type}` ``；Tailwind 官方反模式，purge 會靜默漏掉未以完整字面出現的 class）',
  },
  {
    file: { dir: 'web/static/js/pages/showcase', ext: ['.js'], recursive: true },
    kind: 'forbidden-string',
    // JS 字串值 'warn' 逐字比對，quote 風格中立（'warn' / "warn" / `warn` 都要抓）。
    // backreference 鎖「同一款引號包住恰好 warn 四個字」：
    // - 不誤抓 console.warn( / logger.warn(（warn 前是 `.` 不是引號）
    // - 不誤抓 'warning'（warn 後緊接的是 i 不是同款引號，backreference 對不上）
    // （Codex PR review P2：原本只鎖單引號字面，"warn"/`warn` 逃過此守衛）
    pattern: /(['"`])warn\1/,
    note: "[lint-guard:113d-T4] showcase toast type 不得使用 warn 字面（任何引號風格；CSS 只有 alert-warning；toastType 唯一合法拼寫是 'warning'）",
  },

  // ---- [lint-guard:114a-T2] access_gate.html 偽裝頁靜態結構契約 ----
  // 偽裝頁必須是零外部資源、不透露品牌、無按鈕/label 的獨立文件（spec §2.3、
  // TASK-114a-T2 決策清單）；四碼 + 不自動大寫則是正向存在性檢查。
  {
    file: 'web/templates/access_gate.html', kind: 'forbidden-string',
    pattern: '/static',
    note: '[lint-guard:114a-T2] 偽裝頁禁止引用 /static（零外部資源，避免被靜態檔案請求洩漏「這裡有東西」）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'forbidden-string',
    pattern: 'OpenAver',
    note: '[lint-guard:114a-T2] 偽裝頁禁止出現品牌字面（不透露這是 OpenAver）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'forbidden-string',
    pattern: '<button',
    note: '[lint-guard:114a-T2] 偽裝頁禁止 <button>（spec §2.3：無按鈕，輸滿自動送出）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'forbidden-string',
    pattern: '<label',
    note: '[lint-guard:114a-T2] 偽裝頁禁止 <label>（spec §2.3：無文字節點）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'required-string',
    pattern: 'autocapitalize="off"',
    note: '[lint-guard:114a-T2/T7fix] 偽裝頁輸入框必須是 autocapitalize="off"。密碼是 4 位 ASCII 英數且比對區分大小寫，手機鍵盤預設會把第一個字母自動大寫——設的是 abcd、打出去的是 Abcd，而這頁依設計不顯示任何錯誤訊息，使用者只會看到畫面重刷、永遠進不去。（原本這條鎖 inputmode="numeric"，T7fix 把密碼放寬成英數後那個契約反而會讓手機打不出字母，故整條換掉。）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'required-string',
    pattern: 'maxlength="4"',
    note: '[lint-guard:114a-T2] 偽裝頁輸入框必須是 maxlength="4"（四碼契約）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'forbidden-string',
    pattern: 'type="password"',
    note: '[lint-guard:114a-T2] 偽裝頁輸入框禁止 type="password"（會召喚瀏覽器密碼管理員 UI，當場自曝這是登入框；Opus 審核補充，不得回退）',
  },
  {
    file: 'web/templates/access_gate.html', kind: 'forbidden-string',
    pattern: '<!--',
    note: '[lint-guard:114a-T2] 偽裝頁禁止 HTML 註解（<!-- -->）：這頁是伺服器端渲染，任何 HTML 註解逐字送到瀏覽器，view-source 就讀得到——零成本的洩漏管道。要留註解一律用 Jinja 註解 {# #}（伺服器端渲染時就被剝掉，不進 response body）。<!DOCTYPE html> 字面不同，不會誤中。',
  },

  // ---- [lint-guard:114a-T5] 存取密碼保護欄位薄守衛（owner 未驗收 UI，僅鎖「不得回退到已知壞值」）----
  // scope window 只從 anchor.start 往後切：錨點必須落在被守屬性「之前」。
  // 卡面 skeleton 的 PIN/眼睛錨點落在屬性之後，會變成永遠不紅（死守衛）或 anchor 後找不到 required，
  // 故改錨到同區塊更早的 Alpine 綁定（仍不焊 class / 版位）。
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: 'type="text"',
    scope: { anchor: /x-show="accessAuthEnabled"/, window: 400 },
    note: '[lint-guard:114a-T5] PIN 輸入框不得回退成常駐明碼 type="text"，必須維持 :type 動態綁定於遮罩/明碼之間',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ':disabled="!accessAuthPinRevealed"',
    scope: { anchor: /x-model="accessAuthPin"/, window: 400 },
    note: '[lint-guard:114a-T5] 眼睛按鈕必須保持依 accessAuthPinRevealed disabled——遠端使用者（伺服器未回真值）按了也不能求得明碼',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ':disabled="!serverMode || accessAuthSaving"',
    scope: { anchor: /x-model="accessAuthEnabled"/, window: 500 },
    note: '[lint-guard:114a-T5+T7fix] 勾選框必須同時依 serverMode 與 accessAuthSaving disabled。前者：spec §2.1，它是伺服器模式的子選項，關閉時不可獨立切換。後者（round-3 P2）：儲存請求還在飛的時候若能改勾選框，送出去的值與事後記成「已生效」的值就不是同一個——使用者可以送出「關閉保護」、在回應到達前把框重新勾起來，畫面於是宣稱有密碼保護而後端是全開的。PIN 欄本來就鎖在同一個旗標上，兩者一起鎖才一致。',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'accessAuthEnabledSaved',
    // scope 用 RegExp 形式整段圈住那個 x-text 運算式（window 只能往後切，而被守的
    // 識別字在 i18n key **之前**，用 anchor+window 會是永遠找不到的死守衛）。
    // 前綴刻意寫 `accessAuthEnabled`：草稿名是已生效名的前綴，所以改回草稿時 scope
    // 仍然匹配得到、required 卻缺席 → 轉紅。整段被改名／刪掉則 anchor 找不到，
    // 引擎會另外報「scope anchor 找不到」——兩個方向都 fail-closed。
    scope: /x-text="accessAuthEnabled[\s\S]{0,200}?settings\.server_info\.warning_auth/,
    note: '[lint-guard:114a-T7fix] 「?」說明的 warning_auth 分支必須由 accessAuthEnabledSaved（後端已生效值）決定，不得改讀草稿 accessAuthEnabled。那句話對使用者做安全宣稱（「其他裝置需要輸入密碼才能連線」）——讀草稿的話，勾下去還沒存檔就開始說謊，存檔失敗更會一路說到重新整理為止，使用者以為區網有保護、實際上全開。（Codex PR#129 P2）',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'accessAuthEnabledSaved',
    scope: /x-text="serverModeConfirmValue[\s\S]{0,300}?settings\.server_mode_confirm\.body_on_auth/,
    note: '[lint-guard:114a-T7fix] 伺服器模式確認框的 body_on_auth 分支同上——「已設定密碼保護」是安全宣稱，只准讀 accessAuthEnabledSaved。（Codex PR#129 P2）',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: "normalize('NFKC')",
    scope: { anchor: /x-model="accessAuthPin"/, window: 200 },
    note: '[lint-guard:114a-T7fix] PIN 欄必須在 input 當下做 NFKC 折疊，與後端 _canonical_pin() 同步。拿掉它 → 中文輸入法全形模式打出的 ａＢ９２ 不匹配前端的 ASCII 正規式，儲存鈕永遠不亮且不說明原因（Codex Stage-2 P2；與 T7fix 修掉的「打英文得到一顆灰按鈕」同一個病）。折在 input 上而非只放寬 disabled 判斷，欄位顯示的才會是實際存進去的值。',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'autocapitalize="off"',
    // 錨點刻意用 class 而非 x-model：autocapitalize 寫在 x-model **之前**，而 scope
    // 視窗只往後切——錨在 x-model 會變成永遠找不到的死守衛（T5 踩過同一個坑）。
    scope: { anchor: /class="settings-access-auth-pin-input"/, window: 400 },
    note: '[lint-guard:114a-T7fix] 設定頁 PIN 欄必須 autocapitalize="off"（與偽裝頁同一條不變式）：密碼區分大小寫，行動裝置鍵盤預設自動大寫首字母會讓使用者設出一組自己在別台裝置打不出來的密碼。',
  },
  {
    file: { dir: 'core', ext: ['.py'], recursive: true, exclude: ['access_auth.py'] },
    kind: 'forbidden-string',
    pattern: 'access_tickets',
    note: '[lint-guard:114b-T6] access_tickets 票表的寫入只能出現在 core/access_auth.py（單一所有者，CD-114b-12）。若 core/ 底下別的模組直接寫這張表，就繞過了 access_auth 那把 threading.Lock——改密碼／關閉認證時 revoke_all() 撤不到那一筆，使用者以為已經把一台裝置踢下線，其實那張憑證仍然有效，是 plan-114a.md §0 v4 修掉的 TOCTOU 窗口重新打開。',
  },
  {
    file: { dir: 'web', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: 'access_tickets',
    note: '[lint-guard:114b-T6] access_tickets 票表的寫入只能出現在 core/access_auth.py（單一所有者，CD-114b-12）。若某支 web/ 底下的 router 直接寫這張表，就繞過了 access_auth 那把 threading.Lock——改密碼／關閉認證時 revoke_all() 撤不到那一筆，使用者以為已經把一台裝置踢下線，其實那張憑證仍然有效，是 plan-114a.md §0 v4 修掉的 TOCTOU 窗口重新打開。',
  },
  {
    // windows/ 今天零 DB 存取，這條掃不到任何東西——刻意的。它擋的是一個具體且
    // 合理的未來動作：系統匣加一顆「登出所有裝置」，而最短的實作路徑正是在
    // windows/pywebview_api.py 裡直接 DELETE 這張表（那條路繞過鎖、也繞過
    // revoke_all 的快取同步）。三個 production Python 目錄裡少掃一個，等於留一
    // 個只有寫的人知道存在的缺口。
    file: { dir: 'windows', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: 'access_tickets',
    note: '[lint-guard:114b-T6] access_tickets 票表的寫入只能出現在 core/access_auth.py（單一所有者，CD-114b-12）。windows/（系統匣／pywebview 層）直接寫這張表會繞過 access_auth 那把 threading.Lock——改密碼／關閉認證時 revoke_all() 撤不到那一筆，使用者以為已經把一台裝置踢下線，其實那張憑證仍然有效。',
  },

  // ==== [117-T3] 從片庫加入女優面板：薄守衛（不得回退到已知壞值）====
  // owner 真機驗收前只鎖契約字面；完整視覺守衛排到驗收後。

  // AC-1.1 → 117b-T10：+ 在 .search-actions-right 內；全檔 exact 1 防搬出又補
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      'openActressAddPanel()',
      'x-show="libAddBtnVisible()"',
    ],
    scope: { anchor: /class="search-actions-right"/, window: 2170 },
    note: '[117-T3→117b-T10] AC-1.1/AC-10.1/CD-117b-8：openActressAddPanel() 必須在 .search-actions-right 內，且 x-show 走 libAddBtnVisible()（不得字面鏈、不得搬回 toolbar-controls）。破了＝冷啟動入口又埋進排序列，或顯示條件回到跨模式旗標',
  },
  {
    file: 'web/templates/showcase.html', kind: 'structure-count',
    pattern: 'openActressAddPanel()',
    count: 1,
    note: '[117-T3] AC-1.1：openActressAddPanel() 全檔恰好 1 次（防搬出區塊又在別處補一顆）',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'forbidden-string',
    pattern: 'showcaseHasSearch',
    scope: { anchor: /x-ref="actressAddBtn"/, window: 350 },
    note: '[117b-T10] CD-117b-8/AC-10.8：actressAddBtn 按鈕 markup 不得出現 showcaseHasSearch 字面（跨模式聯集旗標會讓影片殘留篩選把 + 藏起來）。破了＝AC-10.8 可達回歸',
  },

  // AC-1.2：Esc／點外／關閉鈕三路
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '@click.self="closeActressAddPanel()"',
    note: '[117-T3] AC-1.2：點 backdrop 關閉（@click.self）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '@keydown.escape.window="actressAddPanelOpen && closeActressAddPanel()"',
    note: '[117-T3] AC-1.2：Esc 關閉',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '@click="closeActressAddPanel()"',
    scope: { anchor: /class="actress-add-x"/, window: 200 },
    note: '[117-T3] AC-1.2：關閉鈕綁 closeActressAddPanel()',
  },

  // AC-1.4：焦點／捲動契約（禁回退到手刻 $nextTick focus）
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-trap.inert.noscroll="actressAddPanelOpen"',
    note: '[117-T3] AC-1.4：x-trap.inert.noscroll 焦點鎖 + 背景禁捲（.noscroll 不得被拿掉只留 .inert）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'autofocus',
    scope: { anchor: /class="actress-add-search"/, window: 120 },
    note: '[117-T3] AC-1.4：搜尋框必須帶 autofocus（外掛先找 [autofocus]；不寫則焦點落在 ✕）',
  },

  // AC-2.3 / CD-117-6：三欄 minmax(0,1fr)（FE-CSS-12 不得退回裸 1fr）
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'required-string',
    pattern: 'grid-template-columns: auto minmax(0, 1fr) auto',
    note: '[117-T3] AC-2.3/CD-117-6：grid-template-columns 必須 auto minmax(0,1fr) auto（裸 1fr 會讓 ellipsis 失效）',
  },

  // AC-2.4：ellipsis 三件套
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'required-string',
    pattern: ['min-width: 0', 'overflow: hidden', 'text-overflow: ellipsis', 'white-space: nowrap'],
    scope: { anchor: /\.actress-add-name\s*\{/, braceBalanced: true },
    note: '[117-T3] AC-2.4：名字欄 ellipsis 三件套 + min-width:0（與 minmax(0,…) 成對）',
  },

  // AC-2.5：列表 flex 自適應內部捲動；禁固定 px 高
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'required-string',
    pattern: ['flex: 1 1 auto', 'min-height: 0', 'overflow-y: auto'],
    scope: { anchor: /\.actress-add-list\s*\{/, braceBalanced: true },
    note: '[117-T3] AC-2.5：.actress-add-list 必須 flex:1 1 auto + min-height:0 + overflow-y:auto',
  },
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'forbidden-string',
    pattern: /(?:max-)?height:\s*\d+px/,
    scope: { anchor: /\.actress-add-list\s*\{/, braceBalanced: true },
    note: '[117-T3] AC-2.5：.actress-add-list 不得寫死 height/max-height px（禁預設固定可見列數）',
  },

  // AC-4.1：已收藏用 <span> 非 <button> + cursor/pointer-events
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '<span class="actress-add-heart is-favorite"',
    note: '[117-T3] AC-4.1：已收藏愛心必須是 <span class="actress-add-heart is-favorite">（非 button）',
  },
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'required-string',
    pattern: ['cursor: default', 'pointer-events: none'],
    scope: { anchor: /\.actress-add-heart\.is-favorite\s*\{/, braceBalanced: true },
    note: '[117-T3] AC-4.1：.is-favorite 必須 cursor:default + pointer-events:none（無 hover 反應）',
  },

  // AC-4.2 / CD-117-7：降透明度只在 @media (hover: hover)；命中區 44×44
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'required-string',
    pattern: 'opacity: 0.55',
    scope: { anchor: /@media \(hover: hover\)\s*\{/, window: 400 },
    note: '[117-T3] AC-4.2/CD-117-7：降透明度 opacity:0.55 必須寫在 @media (hover: hover) 內（不得移到常駐規則）',
  },
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'required-string',
    pattern: ['width: 44px', 'height: 44px'],
    scope: { anchor: /\.actress-add-heart\s*\{/, braceBalanced: true },
    note: '[117-T3] AC-4.2：愛心命中區 ≥44×44',
  },

  // CD-117-13：CSS 接線進 base.html
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: '/static/css/components/actress-add-panel.css',
    note: '[117-T3] CD-117-13：actress-add-panel.css 必須接線進 base.html（緊接 rescrape-modal）',
  },

  // CD-117-11：新檔禁止 pill 造型
  {
    file: 'web/static/css/components/actress-add-panel.css', kind: 'forbidden-string',
    pattern: ['999px', '--radius-pill'],
    note: '[117-T3] CD-117-11：actress-add-panel.css 禁止 999px / --radius-pill（§1 白名單不動）',
  },

  // 舊 dropdown 不得復活
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: '_addDropdownOpen',
    note: '[117-T3] 舊 + dropdown 的 _addDropdownOpen 不得在 showcase.html 復活',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string',
    pattern: '_addDropdownOpen',
    note: '[117-T3] _addDropdownOpen 宣告與賦值必須拔除（state-actress.js 不得殘留）',
  },

  // ==== [117-T4] 直接新增列接線契約（取代原 TestShowcaseActressCRUD 2 條 HTML 斷言）====
  // T3 刪掉 _addActressName / addFavoriteActress() 的 pytest HTML 半場；
  // 契約改錨定新「直接新增」列：markup 綁 libDirectAdd()，JS 寫入 _addActressName 並走既有路徑。

  // R1 AC-5.4：直接新增列必須存在且綁 libDirectAdd()（取代原 pytest _addActressName 的 HTML 半場）
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'libDirectAdd()',
    scope: { anchor: /class="actress-add-direct"/, window: 400 },
    note: '[117-T4] AC-5.4：直接新增列必須存在且綁 libDirectAdd()（取代 TestShowcaseActressCRUD _addActressName HTML 半場；破了＝庫內 0 片女優永遠加不進來）',
  },
  // R2 防「搬走又在別處補一顆」
  {
    file: 'web/templates/showcase.html', kind: 'structure-count',
    pattern: 'libDirectAdd()',
    count: 1,
    note: '[117-T4] AC-5.4：libDirectAdd() 全檔恰好 1 次（防搬走又在別處補一顆）',
  },
  // R3 直接新增必須把使用者打的字寫進既有 _addActressName（取代原 pytest 同名斷言）
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: '_addActressName',
    scope: { anchor: /libDirectAdd\(\)\s*\{/, braceBalanced: true },
    note: '[117-T4] AC-5.4：libDirectAdd 必須寫入 _addActressName（取代 TestShowcaseActressCRUD 同名斷言）',
  },
  // R4 必須走既有新增路徑（取代原 pytest addFavoriteActress() 斷言）
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'addFavoriteActress()',
    scope: { anchor: /libDirectAdd\(\)\s*\{/, braceBalanced: true },
    note: '[117-T4] AC-5.4：libDirectAdd 必須呼叫 addFavoriteActress()（取代 TestShowcaseActressCRUD 同名斷言）',
  },
  // R5 不得在 libDirectAdd 內另寫第二套 POST
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string',
    pattern: 'fetch(',
    scope: { anchor: /libDirectAdd\(\)\s*\{/, braceBalanced: true },
    note: '[117-T4] AC-5.4：libDirectAdd 內不得另寫 fetch(（409/404/504 分支與 toast 全在 addFavoriteActress）',
  },

  // AC-1.6：開面板不得等網路。同步斷言在第一個 await yield 前就跑完，測不出 async 化；只能用字面守衛。
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string',
    pattern: ['async openActressAddPanel', 'await this._loadLibraryActresses'],
    note: '[117-T4] AC-1.6：開面板不得等網路；同步斷言測不出 async 化，只能用字面守衛',
  },

  // ==== [117b-T8] 清單自動展開 sentinel：字面契約（取代 .actress-add-more 按鈕）====

  // R1 AC-8.1/8.2：sentinel 必須 x-intersect 綁 libExpandMore()（預取由 sentinel 高度表達）
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: 'x-intersect="libExpandMore()"',
    scope: { anchor: /class="actress-add-sentinel"/, window: 300 },
    note: '[117b-T8] AC-8.1/8.2：sentinel 必須 x-intersect 綁 libExpandMore()（預取距離由 sentinel 高度表達，不得加 .margin）。破了＝清單永遠停在首批 40',
  },
  // R2 AC-8.3：.actress-add-more 不得回歸
  {
    file: 'web/templates/showcase.html',
    kind: 'forbidden-string',
    pattern: 'actress-add-more',
    note: '[117b-T8] AC-8.3：.actress-add-more 按鈕已退場。破了＝自動展開與手動按鈕並存，使用者又被打斷節奏（spec-117b 覆蓋 F6 的決策被默默撤回）',
  },
  // R3 AC-8.2：預取帶＝sentinel 自己的高度（rootMargin 對捲動容器內部無效）
  {
    file: 'web/static/css/components/actress-add-panel.css',
    kind: 'required-string',
    pattern: ['height: 400px', 'margin-top: -400px', 'pointer-events: none'],
    scope: { anchor: /\.actress-add-sentinel\s*\{/, braceBalanced: true },
    note: '[117b-T8] AC-8.2：預取帶＝sentinel 自己的高度（rootMargin 對捲動容器內部無效）。少了 height/負 margin ＝ 要真的捲到底才展開、或清單尾端多出 400px 空白；少了 pointer-events:none ＝ 最後幾列的愛心按不下去',
  },

  // ==== [117-T5] 逐列收藏 queue：接線 ＋ 併發計數契約（不鎖視覺，owner/T7 真機驗收前的薄守衛）====

  // L1 AC-4.3：空心愛心必須接上 queue（破了＝點愛心毫無反應，面板變成唯讀清單）
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'libEnqueueFavorite(row)',
    scope: { anchor: /class="actress-add-heart"/, window: 400 },
    note: '[117-T5] AC-4.3：空心愛心必須接上 queue。破了＝點愛心毫無反應，面板變成唯讀清單',
  },
  // L2 防「搬走又在別處補一顆」
  {
    file: 'web/templates/showcase.html', kind: 'structure-count',
    pattern: 'libEnqueueFavorite(row)',
    count: 1,
    note: '[117-T5] AC-4.3：libEnqueueFavorite(row) 全檔恰好 1 次（防搬走又在別處補一顆）',
  },
  // L3 AC-4.3③：queue 不得用直接新增的全域旗標（第一個入口）
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string',
    pattern: '_addingActress',
    scope: { anchor: /libEnqueueFavorite\(row\)\s*\{/, braceBalanced: true },
    note: '[117-T5] AC-4.3③：queue 不得用直接新增的全域旗標。破了＝收藏一列時「直接新增」被鎖住，且併發上限被壓成 1',
  },
  // L4 同上，第二個入口
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string',
    pattern: '_addingActress',
    scope: { anchor: /_libFavoriteRequest\(name\)\s*\{/, braceBalanced: true },
    note: '[117-T5] AC-4.3③：queue 不得用直接新增的全域旗標（第二個入口，同 L3）',
  },
  // L5 CD-117-8①：計數器唯一增點
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: '_libInFlight++',
    count: 1,
    note: '[117-T5] CD-117-8①：計數器唯一增點。破了＝計數漂移，queue 要嘛永久卡死（愛心按了永遠排隊中）、要嘛上限失效',
  },
  // L6 同上，唯一減點
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: '_libInFlight--',
    count: 1,
    note: '[117-T5] CD-117-8①：計數器唯一減點（同 L5）',
  },

  // ==== [117-T6] TestShowcaseActressCRUD 等價遷移（CD-117-10 第三刀）====
  // pytest class 同 commit 移除。對帳表見 TASK-117-T6.md。
  // #10/#11 已由 [117-T4] R3/R4 承接，本區塊不重複。
  // #1–#5 錨定方法定義形狀（非裸字面）：裸字面會被 JS 注釋／console.warn 字串餵飽而 fail-open。
  // 代價：async 關鍵字焊死，日後合法去 async 化會誤紅——fail-closed，可接受。

  // R1 ← TestShowcaseActressCRUD #1：assert "addFavoriteActress" in js
  // 粒度：原 whole-file 裸子字串 → 收緊為 method-definition 形狀（fail-closed）
  // 與 [117-T4] R4 不重複：R4 鎖 libDirectAdd(){} 內 call site；函式被刪而呼叫還在時 R4 仍綠，本條才紅。
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'async addFavoriteActress() {',
    note: '[117-T6] R1 ← TestShowcaseActressCRUD #1 "addFavoriteActress" in js；粒度收緊 method-definition（非裸字面，防注釋餵飽）；定義端——[117-T4] R4 鎖 libDirectAdd call site，函式刪而呼叫還在時那條仍綠，本條才紅',
  },
  // R2 ← #2：assert "openRemoveActressModal" in js
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'openRemoveActressModal() {',
    note: '[117-T6] R2 ← TestShowcaseActressCRUD #2 "openRemoveActressModal" in js；粒度收緊 method-definition（非裸字面，防注釋餵飽）',
  },
  // R3 ← #3：assert "confirmRemoveActress" in js
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'async confirmRemoveActress() {',
    note: '[117-T6] R3 ← TestShowcaseActressCRUD #3 "confirmRemoveActress" in js；粒度收緊 method-definition（非裸字面，防注釋餵飽；async 焊死）',
  },
  // R4 ← #4：assert "cancelRemoveActressModal" in js
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'cancelRemoveActressModal() {',
    note: '[117-T6] R4 ← TestShowcaseActressCRUD #4 "cancelRemoveActressModal" in js；粒度收緊 method-definition（非裸字面，防注釋餵飽）',
  },
  // R5 ← #5：assert "searchActressFilms" in js
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'async searchActressFilms(',
    note: '[117-T6] R5 ← TestShowcaseActressCRUD #5 "searchActressFilms" in js；粒度收緊 method-definition（非裸字面；:737 注釋與 console.warn 字串足以餵飽裸字面）',
  },
  // R6 ← #6：assert "rescrapeActress" not in js（反向，整檔；不加 stripLineComments——注釋也算命中＝fail-closed）
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string',
    pattern: 'rescrapeActress',
    note: '[117-T6] R6 ← TestShowcaseActressCRUD #6 "rescrapeActress" not in js；粒度等價 whole-file 反向；不加 stripLineComments（注釋命中仍紅＝fail-closed）；女優重刮已刻意移除不得回流',
  },
  // R7 ← #7：assert "openRemoveActressModal()" in html
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'openRemoveActressModal()',
    note: '[117-T6] R7 ← TestShowcaseActressCRUD #7 "openRemoveActressModal()" in html；粒度等價 whole-file 帶括號字面',
  },
  // R8 ← #8：assert html.count("searchActressFilms(") >= 2
  // 用 min:2 非 count:2——原斷言是下界；exact 會誤傷合法的第三個 call site
  {
    file: 'web/templates/showcase.html', kind: 'structure-count',
    pattern: 'searchActressFilms(',
    min: 2,
    note: '[117-T6] R8 ← TestShowcaseActressCRUD #8 count("searchActressFilms(") >= 2；粒度等價 whole-file structure-count min:2（非 exact count）',
  },
  // R9 ← #9：assert "rescrapeActress()" not in html（反向，整檔）
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: 'rescrapeActress()',
    note: '[117-T6] R9 ← TestShowcaseActressCRUD #9 "rescrapeActress()" not in html；粒度等價 whole-file 反向；女優重刮已刻意移除不得回流',
  },

  // ==== [117b-T9] 女優燈箱刪除鈕搬到名字行行末（CD-117b-5/6/7）====
  // R1：delete 必須在 .actress-lb-header 內且綁 openRemoveActressModal()、:title=
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      'class="lb-delete-btn"',
      'x-show="showFavoriteActresses && !_maskVisible"',
      '@click.stop="openRemoveActressModal()"',
      ':title="t(\'showcase.actress.remove\')"',
    ],
    scope: { anchor: /<div class="actress-lb-header">/, window: 3200 },
    note: '[117b-T9] AC-9.1/9.2/CD-117b-5：刪除鈕必須在 .actress-lb-header 內、綁 openRemoveActressModal()、且用 :title= 提示。破了＝刪除又回到照片浮層（破壞性操作混進常用 hover 列）、點擊死掉、或 hover 沒有任何提示。`!_maskVisible` 掉了＝使用者正在拖曳調整女優頭像對焦時，刪除鈕仍可按，可在遮罩編輯中途開啟移除確認，破壞既有互斥流程（原 R3「header 內禁 :data-tooltip=」已於 Codex PR#133 review 後移除：真故障模式由本條的 :title= 覆蓋，R3 只剩無害的加法場景卻有 scope 假紅風險）',
  },
  // R2：.cover-actions 區不得再出現 openRemoveActressModal()
  {
    file: 'web/templates/showcase.html',
    kind: 'forbidden-string',
    pattern: 'openRemoveActressModal()',
    scope: {
      anchor: /<div class="cover-actions"\s*\n\s*:data-picker-open="_pickerOpen"/,
      window: 3000,
    },
    note: '[117b-T9] AC-9.1：.cover-actions 不得再呼叫 openRemoveActressModal()（必須真搬走，不是複製一份）。破了＝照片浮層與名字行各一顆刪除，或搬走失敗',
  },

  // ==== [122 / Codex PR#147 P2] 刪除確認要明示「刪的是整組」 ====
  // 合併卡的「從收藏移除」刪的是整組 DB 列，既有文案只說「這筆紀錄」＝破壞性彈窗
  // 沒有明示授權（prd「破壞性 modal 明示授權」）。state 那一半由
  // showcase/__tests__/delete-modal-multipart.test.mjs 鎖，這條鎖 HTML 綁定。
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      'x-show="_pendingDeleteParts.length > 1"',
      "t('showcase.video.delete_modal.body_multipart')",
      'formatPartLabel(_pendingDeleteParts)',
    ],
    scope: { anchor: /delete_modal\.body'\)/, window: 700 },
    note: '[122/PR147-P2] 刪除確認彈窗必須在多段時補一段「會一併移除全部 N 段」，且只在 _pendingDeleteParts.length > 1 時顯示',
  },
  // ==== [122-T3] 分集標記四處插入點（AC-7）＋ hover 隔離（AC-17）＋ CD-122-5 ====
  // 四處各一條 scoped required-string：破壞該處 DOM 必須獨立轉紅（mutation 自驗）。
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '<template x-if="(video.part_tokens || []).length">',
      'class="cover-badges-part"',
      'formatPartLabel(video.part_tokens)',
    ],
    scope: { anchor: /:data-flip-id="video\.path"/, window: 3200 },
    note: '[122-T3] AC-7 grid/poster：封面卡必須以 <template x-if> 掛 .cover-badges-part，消費 formatPartLabel(video.part_tokens)',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '<template x-if="(video.part_tokens || []).length">',
      'formatPartLabel(video.part_tokens)',
    ],
    scope: { anchor: /class="table-cell-number"/, window: 600 },
    note: '[122-T3] AC-7 table：番號欄必須以 <template x-if> 掛 formatPartLabel(video.part_tokens)。[123-T5] window 400→600：table-cell-number 內插入唯讀 .pick-star-mark 後把 formatPartLabel 目標往後推，實測距離 513，取 600。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '<template x-if="(video.part_tokens || []).length">',
      'formatPartLabel(video.part_tokens)',
    ],
    scope: { anchor: /class="list-number" x-text="video\.number"/, window: 400 },
    note: '[122-T3] AC-7 list：番號後必須以 <template x-if> 掛 formatPartLabel(video.part_tokens)',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '!!currentLightboxVideo?.path && !_maskVisible && (currentLightboxVideo.part_tokens || []).length',
      'class="cover-badges-part"',
      'formatPartLabel(currentLightboxVideo.part_tokens)',
    ],
    scope: { anchor: /<div class="lightbox-cover" :class="\{'has-cover': !!currentLightboxVideo\?\.cover_url\}">/, window: 4000 },
    note: '[122-T3] AC-7/AC-17 燈箱：封面必須以 <template x-if> 掛 .cover-badges-part（含 !_maskVisible），消費 formatPartLabel(currentLightboxVideo.part_tokens)',
  },

  // ==== [123-T5] CD-123-13：三個唯讀表面 + 燈箱既有插入點的粗顆粒守衛（AC-4/5/6） ====
  // [Codex review BLOCKER 修正] 前一版把 anchor 錨在「自己要驗的那段字面」上
  // （/<span class="pick-star-mark...[\s\S]{0,300}class="av-num"/ 這類）。anchor.exec()
  // 對整份檔案是非 global 搜尋：只要檔案裡任何位置（含頂部中文說明註解）殘留同樣的複合
  // 字面，即使真正實作被整段刪掉，window 仍會在殘留文字裡「找到」要求的 pattern → false-
  // green。review 已實測重現：三處星標全刪＋頂部塞一段含完整複合字面的 HTML 註解，
  // 6 條全數轉綠。
  // 修法：anchor 一律錨在「不含 payload 字面本身、且結構上必然唯一存在」的容器 class——
  // 照抄同一個 RULES 陣列裡 122-T3 三條既有規則的做法（grid 錨 :data-flip-id="video.path"、
  // table 錨 class="table-cell-number"），不發明新寫法：
  //   grid  → class="footer-num-group"（pick-star-mark 的直接父層，全檔僅 1 處）
  //   table → class="table-cell-number"（與 122-T3 table 規則共用同一個既驗證過的唯一 anchor）
  //   list  → class="list-item"（<li> 開標籤，全檔僅 1 處）
  // 三個 anchor 均以 grep -c 驗證全檔僅出現 1 次，且字面本身不含 pick-star-mark/av-num/
  // table-number-highlight/list-number 任何一段 payload，故不會被同風格的中文說明註解
  // 意外命中。window 數值已實測校準（node 量測 anchor.index 到 aria-hidden="true" 結尾的
  // 實際字元距離，取整數進位加緩衝）：grid 197→250、table 206→260、list 228→280。
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '<span class="pick-star-mark bi bi-star-fill"',
      'x-show="(video.user_rating || 0) > 0"',
      'aria-hidden="true"',
    ],
    scope: { anchor: /class="footer-num-group"/, window: 250 },
    note: '[123-T5] AC-4/5 grid/poster（共用同一份 markup）：.footer-num-group 內、.av-num 前必須有唯讀 .pick-star-mark（x-show 條件渲染，不佔位）。anchor 改錨 .footer-num-group（全檔唯一容器，不含 payload 字面，修 Codex review BLOCKER：舊 anchor 自我參照可被殘留註解假綠）。window 實測 197，取 250。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '<span class="pick-star-mark bi bi-star-fill"',
      'x-show="(video.user_rating || 0) > 0"',
      'aria-hidden="true"',
    ],
    scope: { anchor: /class="table-cell-number"/, window: 260 },
    note: '[123-T5] AC-4/5 table：.table-cell-number 內、.table-number-highlight 前必須有唯讀 .pick-star-mark。anchor 與 122-T3 table 規則共用同一個既驗證唯一的容器 class（修 Codex review BLOCKER：舊 anchor 自我參照可被殘留註解假綠）。window 實測 206，取 260。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      '<span class="pick-star-mark bi bi-star-fill"',
      'x-show="(video.user_rating || 0) > 0"',
      'aria-hidden="true"',
    ],
    scope: { anchor: /class="list-item"/, window: 280 },
    note: '[123-T5] AC-4/5 list：.list-item 內、.list-number 前必須有唯讀 .pick-star-mark。anchor 改錨 .list-item（<li> 開標籤，全檔唯一，不含 payload 字面，修 Codex review BLOCKER：舊 anchor 自我參照可被殘留註解假綠）。window 實測 228，取 280。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: ['class="pick-star"', 'pick-star-outline', 'pick-star-fill'],
    scope: { anchor: /class="lb-title"/, window: 800 },
    note: '[123-T5] AC-1 燈箱（anchor 於 123-T8 由 lb-details 改為 lb-title）：可切換的 .pick-star 必須在標題行內、與標題文字同一個 inline 脈絡——它是精選的唯一切換入口，且該處是對齊正確性的承重位置（見 showcase.css .lb-title .pick-star 註解）。anchor 全檔僅 1 次且不含 payload 字面（FE-GUARD-11）。window 實測（lb-title 到 pick-star-fill 結尾）698，取 800。',
  },

  // AC-6：三個唯讀表面不得被掛上 click（誤觸代價是取消精選、牆上無任何確認，spec §4.1）。
  // resolveScopeRaw 的 anchor.exec() 非 global，單一 anchor 只會抓到「檔案中第一個」符合
  // 的位置——不存在「occurrence: 'each'」這個 scope 選項（引擎未實作，若三條共用同一個
  // anchor 只會實際檢查第一條命中的表面，其餘會是沒有鎖到的假安全)。改成三條各自 anchor
  // 到自己表面的容器 class（與上面 required-string 三條同一組 anchor：
  // footer-num-group / table-cell-number / list-item，[Codex review BLOCKER 修正] 同理換掉
  // 舊版自我參照的 pick-star-mark 複合字面 anchor），window 收窄到只覆蓋星标自身這個
  // <span>（實測 anchor 到 </span> 結尾 205/214/236），不重用 required-string 較寬的
  // window——避免不小心把表面本身既有、合法的 @click（grid 卡片整體 @click="openLightbox"
  // 在插入點之前；table <tr>／list <li> 的 @click 也都在插入點之前，理論上已被 anchor
  // 位置排除，但仍收窄以防未來版面調整把合法 @click 移到窗口內）。
  {
    file: 'web/templates/showcase.html',
    kind: 'forbidden-string',
    pattern: '@click',
    scope: { anchor: /class="footer-num-group"/, window: 230 },
    note: '[123-T5] AC-6 grid：.pick-star-mark 是唯讀標記，不得掛 @click（唯一切換入口在燈箱）。anchor 改錨 .footer-num-group（修 Codex review BLOCKER）。window 實測（anchor 到 </span> 結尾）205，取 230。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'forbidden-string',
    pattern: '@click',
    scope: { anchor: /class="table-cell-number"/, window: 240 },
    note: '[123-T5] AC-6 table：.pick-star-mark 是唯讀標記，不得掛 @click（唯一切換入口在燈箱）。anchor 改錨 .table-cell-number（修 Codex review BLOCKER）。window 實測（anchor 到 </span> 結尾）214，取 240。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'forbidden-string',
    pattern: '@click',
    scope: {
      anchor: /(?<=<li class="list-item" @click="openLightbox\(getCurrentFilteredIndex\(index\)\)">)/,
      window: 190,
    },
    note: '[123-T5] AC-6 list：.pick-star-mark 是唯讀標記，不得掛 @click（唯一切換入口在燈箱）。anchor 不能直接用 class="list-item"（同一個 <li> 開標籤自己就掛著合法的 @click="openLightbox(...)"，window 從 anchor 起點往後切一定會把這段合法 @click 也切進去、恆假紅）；改用零寬 lookbehind 錨在該 <li> 開標籤結尾的 ">" 之後，把合法 @click 排除在 window 之外。window 實測（anchor 到 </span> 結尾）164，取 190。',
  },

  {
    file: 'web/static/css/pages/showcase/08-remainder.css',
    kind: 'required-string',
    pattern: [
      'position: absolute',
      'bottom: 0.5rem',
      'left: 0.5rem',
      'pointer-events: none',
      'var(--fluent-duration-fast)',
      'var(--fluent-ease-standard)',
    ],
    scope: { anchor: /\.cover-badges-part\s*\{/, braceBalanced: true },
    note: '[122-T3] AC-5：.cover-badges-part 必須左下定位、pointer-events:none、transition 走 Fluent token',
  },
  // ==== [123-T6] AC-7：漏斗選單「只看精選」項＋分隔線＋勾選態；AC-11：漏斗按鈕 active 態 ====
  // anchor 錨在 sortOpen 專屬 .toolbar-dropdown-wrap 的 @click.outside="sortOpen = false"
  // （全檔僅 1 次；mode/actress 兩個姊妹 dropdown 各自用 modeOpen/actressSortOpen，不會誤命中）。
  // 字面本身不含本規則要驗的任何 payload —— 比照 T5 修正後的 anchor 慣例（FE-GUARD-11：
  // anchor 不可自我參照，否則殘留註解可造成 false-green）。
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: [
      "t('showcase.filter.pick_only')",
      "'is-checked': _hasPickPill()",
      '@click.prevent="togglePickPill(); sortOpen = false"',
    ],
    scope: { anchor: /@click\.outside="sortOpen = false"/, window: 900 },
    note: '[123-T6] AC-7：選單最上方「只看精選」項存在（i18n key）＋ :class 綁 _hasPickPill()（勾選態，非排序項那種 .active 單選高亮）＋ @click 綁 togglePickPill()。window 實測 822，取 900。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: '<div class="dropdown-divider"></div>',
    scope: { anchor: /@click\.outside="sortOpen = false"/, window: 1200 },
    note: '[123-T6] AC-7：「只看精選」與下面八條排序項之間有分隔線（.dropdown-divider）。window 實測 1063，取 1200。',
  },
  {
    file: 'web/templates/showcase.html',
    kind: 'required-string',
    pattern: "'active': sortOpen || _hasPickPill()",
    scope: { anchor: /@click\.outside="sortOpen = false"/, window: 350 },
    note: '[123-T6] AC-11：漏斗按鈕本身在精選開啟時呈 active（不必打開選單就知道掛著條件）。window 實測 331，取 350。',
  },

  {
    file: 'web/static/css/pages/showcase/08-remainder.css',
    kind: 'required-string',
    pattern: '.av-card-preview:hover .cover-badges-part { opacity: 0; }',
    note: '[122-T3] AC-5：卡片 hover 淡出必須掛在 .av-card-preview:hover（不得改成通用 :hover，否則燈箱會誤中）',
  },
  {
    file: { dir: 'web/static/css/pages/showcase', ext: ['.css'], recursive: false },
    kind: 'forbidden-string',
    pattern: '.lightbox-cover:hover .cover-badges-part',
    note: '[122-T3] AC-17：燈箱 .cover-badges-part 不得掛 :hover 淡出',
  },

  // ---- [lint-guard 126-T3] search.html 劇照三處 proxy-image 綁定必須吃 preview 優先 ----
  // **三條獨立規則，各釘一個位置**——刻意不用單一條 `count: 3`。
  // 理由（T3 Sonnet review MAJOR，已在 /tmp 沙盒實證）：`required-string` 的 count 是**下限**
  // （`if (n < rule.count) err(...)`）且不剝註解，所以「刪掉三處之一 ＋ 別處多出兩次同樣指紋
  // （含註解裡）」會靜默維持綠燈。**使用者流程**：日後有人動這支模板漏改一處 → CI 綠 →
  // 那一格劇照又變回 403 破圖，而且沒人會去查，因為守衛回報過關。
  // 指紋各自帶「誰的 index」，所以三處不會互相冒充。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'currentLightboxVideo()?.preview_sample_images?.[i]',
    note: '[lint-guard 126-T3a] 燈箱劇照按鈕的 /api/proxy-image 必須吃 preview_sample_images?.[i] || raw（CD-126-3；FE-JS-01 用 || 不用 ??）',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'current().preview_sample_images?.[i]',
    note: '[lint-guard 126-T3b] detail 縮圖點擊開燈箱的 map 必須吃 preview_sample_images?.[i] || raw（CD-126-3）',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'current().preview_sample_images?.[idx]',
    note: '[lint-guard 126-T3c] detail 縮圖 :src 必須吃 preview_sample_images?.[idx] || raw（CD-126-3）',
  },

  // ==== [TASK-128-T2] 共用「選擇資料夾」彈窗：掛載點 / include / markup / 無 script / 無 init ====
  // 掛載點（CD-128-4）：三頁 main.js 各自 import + 併入 mergeState（只做 {% include %} 不會註冊 state）
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: "from '@/shared/state-browse-dir.js'", note: '[TASK-128-T2] search main.js 必須 import browseDirState' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: /browseDirState\s*\(/, note: '[TASK-128-T2] search main.js mergeState 鏈必須呼叫 browseDirState()' },
  { file: 'web/static/js/pages/settings/main.js', kind: 'required-string', pattern: "from '@/shared/state-browse-dir.js'", note: '[TASK-128-T2] settings main.js 必須 import browseDirState' },
  { file: 'web/static/js/pages/settings/main.js', kind: 'required-string', pattern: /browseDirState\s*\(/, note: '[TASK-128-T2] settings main.js mergeState 鏈必須呼叫 browseDirState()' },
  { file: 'web/static/js/pages/scanner/main.js', kind: 'required-string', pattern: "from '@/shared/state-browse-dir.js'", note: '[TASK-128-T2] scanner main.js 必須 import browseDirState' },
  { file: 'web/static/js/pages/scanner/main.js', kind: 'required-string', pattern: /browseDirState\s*\(/, note: '[TASK-128-T2] scanner main.js mergeState 鏈必須呼叫 browseDirState()' },

  // 三頁模板 include（block content 內）
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "{% include '_browse_dir_modal.html' %}", note: '[TASK-128-T2] search.html 必須 include _browse_dir_modal.html' },
  { file: 'web/templates/settings.html', kind: 'required-string', pattern: "{% include '_browse_dir_modal.html' %}", note: '[TASK-128-T2] settings.html 必須 include _browse_dir_modal.html' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: "{% include '_browse_dir_modal.html' %}", note: '[TASK-128-T2] scanner.html 必須 include _browse_dir_modal.html' },

  // base.html CSS link
  { file: 'web/templates/base.html', kind: 'required-string', pattern: '/static/css/components/browse-dir-modal.css', note: '[TASK-128-T2] base.html 必須 <link> browse-dir-modal.css' },

  // partial：fluent-modal 開關、禁 .showModal()、零 <script>、單擊導覽、常駐選取鍵
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: 'class="modal fluent-modal browse-dir-dialog"', note: '[TASK-128-T2] partial 必須沿用 modal fluent-modal browse-dir-dialog' },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: "{ 'modal-open': browseDirOpen }", note: "[TASK-128-T2] partial 必須 :class=\"{ 'modal-open': browseDirOpen }\" 開關" },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'forbidden-string', pattern: '.showModal()', note: '[TASK-128-T2] partial 不得使用原生 .showModal()' },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'forbidden-string', pattern: '<script', note: '[TASK-128-T2] partial 不得含 <script>（FE-TIMING-01；state 由三頁 main.js 掛載）' },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: '@click="navigateBrowseDir(e.path)"', note: '[TASK-128-T2] 資料夾列必須單擊即導覽 navigateBrowseDir(e.path)' },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: ':disabled="!browseDirCanSelect()"', note: '[TASK-128-T2] 「選取此資料夾」必須 :disabled="!browseDirCanSelect()"' },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: '@click.self="closeBrowseDir()"', note: '[TASK-128-T2] 點外面關閉必須 @click.self="closeBrowseDir()"' },
  // 導覽入口在請求飛行中必須 disabled —— 讓「select 的二次 fetch 還沒回來就跳走」在時序上不可能發生
  // （sonnet review 2026-08-24 MAJOR；選 UI 鎖而不是在 select 裡再加一把 generation guard）
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: ':disabled="browseDirParentPath === null || browseDirLoading"', note: '[TASK-128-T2] 「上一層」在 browseDirLoading 時必須 disabled（select 二次 fetch 期間不得跳走）' },
  { file: 'web/templates/_browse_dir_modal.html', kind: 'required-string', pattern: /class="browse-dir-crumb"\s*\n\s*:disabled="browseDirLoading"/, note: '[TASK-128-T2] 麵包屑在 browseDirLoading 時必須 disabled（同上）' },

  // FE-ALPINE-05：browseDirState 不得定義 init()
  { file: 'web/static/js/shared/state-browse-dir.js', kind: 'forbidden-string', pattern: /(?:^|\n)\s*init\s*\(/, note: '[TASK-128-T2] browseDirState 不得定義 init()（FE-ALPINE-05 mergeState last-wins）' },

  // ==== [130a-T6] windows/ 底下 HTTP 請求不得用裸 urllib.request.urlopen ====
  {
    file: { dir: 'windows', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    // regex（非純字串）：同一行若在 urlopen( 之前先出現 #，視為註解不比對。
    // 理由見 PR #157 Codex P2——純 raw text 比對會把「說明為什麼不要用它」的註解也擋掉，
    // 讓 npm run lint／CI 為了一行文件紅燈。docstring 仍是殘留缺口（字串比對 linter 的結構性限制）。
    // \burlopen\( 同時涵蓋 `urllib.request.urlopen(` 與 `from urllib.request import urlopen` 之後的裸呼叫。
    pattern: /^(?:(?!#).)*\burlopen\(/m,
    note: '[lint-guard:130a-T6] 探活／任何 windows/ 底下的 HTTP 請求不得用 urlopen（含 urllib.request.urlopen 與 from-import 後的裸呼叫）—— 它的預設 opener 會讀系統代理（Linux 環境變數／Windows 登錄檔）且不排除 127.0.0.1，使用者開著 Clash／v2rayN 時連自己 loopback 的請求會被送去代理並遭 RST，App 啟動直接崩出 traceback（0.14.10 修的就是這個）。一律用 urllib.request.build_opener(urllib.request.ProxyHandler({}))。',
  },

  // ==== [130a-T6 / PR#157 Codex P3] 探活的時鐘與 opener —— 原本是 test_health_probe_boundary.py 的
  // 全檔字串斷言，依 CLAUDE.md lint 守衛 north-star（能用 lint 機械處理的不該進 pytest）搬過來，
  // 避免同一份契約有兩個真理來源。AST 語意那幾條仍留在 pytest（lint 表達不了）。 ====
  {
    file: 'windows/health_probe.py',
    kind: 'required-string',
    pattern: 'ProxyHandler({})',
    note: '[lint-guard:130a-T6] 探活 opener 必須顯式帶 ProxyHandler({})（＝官方文件定義的「明確關閉代理自動偵測」寫法）。少了它，build_opener() 會讀系統代理，連 127.0.0.1 也會被送去代理。',
  },
  {
    file: 'windows/health_probe.py',
    kind: 'required-string',
    pattern: 'time.monotonic()',
    note: '[lint-guard:130a-T6] 探活的逾時計算必須用 time.monotonic()（量「經過時間」的正確 API，不受 NTP 校時／DST 跳時影響）。',
  },
  {
    file: 'windows/health_probe.py',
    kind: 'forbidden-string',
    pattern: /^(?:(?!#).)*\btime\.time\(\)/m,
    note: '[lint-guard:130a-T6] 探活不得用 time.time() 算逾時 —— 啟動那 30 秒剛好撞上系統校時，使用者會看到一句假的「啟動逾時」。用 time.monotonic()。',
  },

  // ==== [131b-T1] 全螢幕層 x-trap.inert 焦點鎖 ====
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'x-trap.inert="lightboxOpen && !sampleGalleryOpen && !rescrapeOpen && !browseDirOpen && !duplicateModalOpen"',
    note: '[131b-T1] 搜尋頁燈箱開著時若沒這條，Tab 會跑到底下看不見的搜尋列與卡片上',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'x-trap.inert="sampleGalleryOpen && !rescrapeOpen && !browseDirOpen && !duplicateModalOpen"',
    note: '[131b-T1] 搜尋頁劇照集開著時若沒這條，Tab 會跑到燈箱與頁面背景的按鈕上',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-trap.inert="sampleGalleryOpen && !rescrapeOpen && !removeActressModalOpen && !deleteVideoModalOpen"',
    note: '[131b-T1] 瀏覽頁劇照集開著時若沒這條，Tab 會跑到燈箱與頁面背景，等於這層焦點鎖沒做',
  },

  // ==== [131b-T4] Help Popover 共用元件掛載 ====
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'components/help-popover.js',
    note: '[131b-T4] 少這一行，設定頁與掃描頁 8 個 ? 按鈕全部點不出東西——x-data="helpPopover" 找不到定義，Alpine 只會在 console 抱怨，畫面上就是「按了沒反應」',
  },
  // ==== [155b-T2] Number Drilldown 共用元件掛載 ====
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'components/number-drilldown.js',
    note: '[155b-T2] 少這一行，掃描頁數字按了沒反應——x-data="numberDrilldown" 找不到定義，Alpine 只會在 console 抱怨',
  },
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'components/number-drilldown.css',
    note: '[155b-T2] 少這一行，數字清單浮層無樣式——結構在、看起來像沒套 CSS 的裸 HTML',
  },
  // 9 個掛載點逐一鎖住（既有 :1175-1179 的 help-popover / help-popover-btn 是 min，
  // 拆掉其中一顆仍會過；count 讓「少一顆」直接紅）。131b branch review P3。
  {
    file: 'web/templates/settings.html', kind: 'structure-count',
    pattern: 'x-data="helpPopover"', count: 9,
    note: '[131b-T4] settings 的 9 個 ? 說明浮層各自掛一份 helpPopover——少一顆＝那顆點下去沒反應（console ReferenceError，畫面無事發生）。133b-T1 新增第 7 顆（顯示表格與清單）時同步 +1；152c-T9 新增第 8 顆（人臉自動對焦狀態）時同步 +1；154b-T4 新增 NFO 標題格式說明浮層 +1',
  },
  {
    file: 'web/templates/scanner.html', kind: 'structure-count',
    pattern: 'x-data="helpPopover"', count: 2,
    note: '[131b-T4] scanner 的 2 個 ? 說明浮層各自掛一份 helpPopover——少一顆＝那顆點下去沒反應',
  },

  // ==== [131b-T3] Toast store 全站掛載 ====
  // branch review P2：全站載入的模組每一支都有 required-string（ghost-fly / burst-picker /
  // path-utils / motion-* / page-lifecycle / gsap / alpine），T4 也照著加了——只有這支漏了。
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'components/toast-store.js',
    note: '[131b-T3] 少這一行，$store.toast 是 undefined：五頁的 toast 容器綁定當場 TypeError，而且 this.showToast(...) 會往呼叫端拋——使用者按「重新刮削」「複製路徑」「儲存設定」不但沒有提示，那個函式後面那半段也不會跑',
  },

  // ---- [lint-guard 137-T1] showcase.html 三條假綠接線補守衛（plan-137 CD-3/CD-4） ----
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="part.clickable"',
    scope: { anchor: /:class="\{'has-info': _actressInfoParts\(actress\)\.length\}"/, window: 600 },
    note: '[lint-guard 137-T1 #1] 拔掉這條 → 女優卡資訊區「不該可點」的欄位（如空白年齡）同時出現純文字和一個可點連結，點下去篩出空結果（來源 TASK-136a-T4.md:106-113）。**anchor 於 138-T2 改精確**：原本錨 `<div class="card-info actress-card-info"` 是 first-match，138-T2 讓 hero 卡也用同一組 class 之後會先命中 hero 卡區塊（那裡依 CD-B3 刻意不可點）⇒ 誤報。改錨女優牆獨有的 `_actressInfoParts(actress)`（hero 卡傳的是 `_matchedActress`），守的區塊與 pattern 一字未變（anchor 距 target 約 408 字元，window=600）。**anchor 於 148b-T5 再次 repoint**：模式 A 改造把女優卡 `.card-info` 的顯示從 `x-show="infoVisible && _actressInfoParts(actress).length"` 換成 `:class="{\'has-info\': _actressInfoParts(actress).length}"`（顯示改由 `.info-open` 容器 class 驅動），舊 anchor 字面消失。**守的區塊、pattern、window 一字未變**；沿用同一個區辨性質——女優牆傳 `actress`、hero 卡傳 `_matchedActress`，所以新 anchor 仍然只命中女優牆那一塊',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="part.clickable"',
    scope: { anchor: /<div class="lb-actress-core"/, window: 600 },
    note: '[lint-guard 137-T1 #2] 拔掉這條 → 女優燈箱 metadata「不該可點」的欄位同時出現純文字和一個可點連結，重複顯示（來源 TASK-136a-T4.md:106-113），scope 錨到 .lb-actress-core 區塊（anchor 距 target 499 字元，window=600，與 #1 的 anchor 相距 12812 字元，不重疊）',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '@input.debounce.300ms="onSearchChange()"',
    note: '[lint-guard 137-T1 #5] 拔掉這條 → 瀏覽頁搜尋框打字完全不篩選（來源 TASK-136a-T4.md:106-113）',
  },

  // ---- [lint-guard 137-T2] search.html / chip-editor.js / scanner.html 三條假綠接線補守衛（plan-137 CD-3/CD-4） ----
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: '@error="handleHeroLightboxError($event)"',
    note: '[lint-guard 137-T2 #8] 拔掉這條 → 搜尋頁燈箱封面載入失敗時，破圖救援不啟動（來源 TASK-136a-T4.md:106-113）',
  },
  {
    file: 'web/static/js/pages/settings/chip-editor.js', kind: 'required-string',
    pattern: 'tokenize(text, this.whitelist)',
    scope: { anchor: /_onPaste\s*\(\s*e\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 137-T2 #12] 拔掉這條 → 設定頁命名格式貼上文字沒有反應（來源 TASK-136a-T4.md:106-113），scope 錨到 _onPaste 方法體（同字面 tokenize(text, this.whitelist) 在 drop handler :185 也有一份，scope 外，不 scope 會 fail-open）',
  },
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: '@drop.document.prevent="handleDrop($event)"',
    note: '[lint-guard 137-T2 #13] 拔掉這條 → 掃描頁拖放資料夾整個失效（同層 @dragover.document.prevent 還在，看起來像可以拖，放開卻沒事；.prevent 修飾詞被單拔也會紅，來源 TASK-136a-T4.md:106-113）',
  },

  // ---- [lint-guard 138-T2] showcase.html hero 卡展開資訊區純文字渲染反向鎖（TASK-138-T2 CD-B7） ----
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: ['class="info-link"', '_onActressCardMetadataClick'],
    scope: { anchor: /<div class="av-card-preview hero-card"/, window: 6000 },
    note: '[lint-guard 138-T2] 拔掉這條 → hero 卡的年齡／身高變成可點，使用者點了沒有任何反應（window 實測：anchor→hero 卡區塊結束 3782 字元、anchor→下游第一個合法 class="info-link" 9532 字元（該處是**影片卡** metadata 連結；女優牆的在 23570）⇒ 安全區間 (3782, 9532)，取 6000 兩側各留 2218／3532 餘裕；太小會漏掉區塊尾端的違規＝fail-open，太大會誤抓下游的合法字面）',
  },

  // ---- [lint-guard 138-T4] showcase.html hero 卡補白標籤列資料來源正向鎖（TASK-138-T4 CD-D5） ----
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '_heroCardTagParts(_matchedActress)', count: 3,
    scope: { anchor: /<div class="av-card-preview hero-card"/, window: 7000 },
    note: '[lint-guard 138-T4] 拔掉這條 → hero 卡標籤補白列被接到別的函式（或整段被刪），使用者展開資訊時看到的是垃圾資料或空白（window 實測：anchor→hero 卡區塊結束 4385 字元、同字面下游無第二處；以同錨點下游第一個 class="info-link"（影片卡 metadata）10135 字元為上界參考 ⇒ 安全區間 (4385, 10135)，取 7000 兩側各留 2615／3135 餘裕；太小會漏掉外層 x-show／補白列 x-show／x-for 三處之一＝假綠，太大只是 scope 變寬）',
  },

  // ---- [lint-guard 138-T5] showcase.html hero 卡焦點裁切接線正向鎖（TASK-138-T5 CD-E5） ----
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'applyCellFocal($el, _matchedActress', count: 3,
    scope: { anchor: /<div class="av-card-preview hero-card"/, window: 7500 },
    note: '[lint-guard 138-T5] 拔掉這條 → 使用者在直式海報格拖完對焦按確認，hero 卡的圖一動也不動（window 實測：anchor→hero 卡區塊結束 5040 字元、同字面下游無第二處；以同錨點下游第一個 class="info-link"（影片卡 metadata）10790 字元為上界參考 ⇒ 安全區間 (5040, 10790)，取 7500 兩側各留 2460／3290 餘裕；count:3 鎖 @load＋兩條 $watch，只拔 @load 也會紅；太小會漏掉三件套之一＝假綠，太大只是 scope 變寬）',
  },

  // ---- [lint-guard 138-T6] 缺口 F：模式切換歸零捲動（TASK-138-T6 CD-F4） ----
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'window.scrollTo(0, 0)',
    scope: { anchor: /async\s+searchActressFilms\s*\(\s*actressName\s*,\s*fromEl\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 138-T6-F1] 缺口F正向：searchActressFilms() 缺少 window.scrollTo(0, 0) → 使用者從女優牆按「搜尋相關影片」切到影片牆，畫面落在最底部，要自己捲回去才看得到 hero 卡與第一排影片',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: 'window.scrollTo(0, 0)',
    scope: { anchor: /flipAndFadeIn\s*=\s*function\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 138-T6-F2] 缺口F反向：toggleActressMode()/flipAndFadeIn 缺少 window.scrollTo(0, 0) → 使用者從影片牆按「女優模式」切回女優牆，畫面落在女優牆最底部，要自己捲回去才看得到熟悉的第一排女優',
  },

  // ---- [lint-guard 139-T7] 錯誤頁「使用番號進階搜尋」膠囊接線正向鎖（TASK-139-T7 D6） ----
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'rescrapeNumber = (currentQuery',
    scope: { anchor: /<div id="errorState"/, window: 2000 },
    note: '[lint-guard 139-T7] 錯誤頁「使用番號進階搜尋」膠囊的接線斷掉 → 使用者搜尋查無結果時，畫面上不再有任何可以自己挑來源重試的入口，只剩一句「請稍後再試」的死路',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: "t('search.error.advanced_search_cta')",
    scope: { anchor: /<div id="errorState"/, window: 2000 },
    note: '[lint-guard 139-T7] 同上：膠囊文字的 i18n key 被改掉或膠囊被移除',
  },

  // ---- [TASK-140-T7] wishlist badge x-show（F2 驗收1） ----
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'x-show="wishlistCount > 0"',
    note: '[TASK-140-T7] wishlist badge 只在 wishlistCount>0 時顯示（F2 驗收1，那一段本身仍要顯示）',
  },

  // ---- [TASK-140-T8] wishlist 封面端點（F4 驗收2／F6 驗收5）——已入手角標那三條已隨 141a-T6 退場 ----
  // window 實測：.wishlist-grid 開標 class= 錨點 → 閉合 </div> 共 2415 字元；+ 安全邊際 → 3000。
  {
    file: 'web/templates/search.html',
    kind: 'forbidden-string',
    pattern: 'resolveCoverUrl(item)',
    scope: { anchor: /class="wishlist-grid[^"]*"/, window: 3000 },
    note: '[TASK-140-T8] wishlist 封面必須走本地 /api/wishlist/cover 端點，不得用 resolveCoverUrl（F4 驗收2／F6 驗收5）',
  },
  // 🔴 branch review P2-2（2026-09-02）：上面只有反向鎖（不得用 resolveCoverUrl），
  // 少了正向鎖 ⇒ 把 :src 改成打 /api/proxy-image 時 static_guard 1217 條、css-guard 52 條
  // **全綠**（reviewer 在乾淨樹沙盒實測過）。燈箱那側本來就有這條正向鎖，卡片這側漏了。
  // 兩處字面相距 6 萬字元、各自有 scope，不會互相餵飽（FE-GUARD-22）。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: '/api/wishlist/cover?number=',
    scope: { anchor: /class="wishlist-grid[^"]*"/, window: 3000 },
    note: '[branch review P2-2] 書籤格卡封面必須走本地端點：退回打外站會破壞 F6 驗收5「零對外請求」，且 javbus 圖床沒有 Referer 會回 403 ＝ T9 修過的那個整頁破圖',
  },
  // Opus 補（T8 Step 6 自驗發現原稿這條 SURVIVED）：三個狀態頁必須排除 wishlist。
  // 沒有這條的話，把 `&& listMode !== 'wishlist'` 刪掉不會有任何東西轉紅，而後果是
  // 「請輸入番號」那類提示文案疊在書籤清單上面（pageState 與 listMode 是正交的兩個閘，
  // T1 那張 29 列 listMode 對帳表結構上看不到 pageState）。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `x-show="pageState === 'empty' && listMode !== 'wishlist'"`,
    note: '[TASK-140-T8] #emptyState 必須排除 wishlist（否則空狀態提示會疊在書籤清單上）',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `x-show="pageState === 'loading' && listMode !== 'wishlist'"`,
    note: '[TASK-140-T8] #loadingState 必須排除 wishlist',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `x-show="pageState === 'error' && listMode !== 'wishlist'"`,
    note: '[TASK-140-T8] #errorState 必須排除 wishlist',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `x-show="pageState === 'result' && listMode !== 'wishlist'"`,
    note: '[TASK-140-T9] #resultCard 必須排除 wishlist（否則搜尋結果會與書籤清單並排顯示）',
  },

  // ---- [TASK-140-T11a] 書籤燈箱掛載與封面/按鈕守衛（F5 驗收 1-5，承重段第 11 條） ----
  // window 實測：class="showcase-lightbox wishlist-lightbox" 錨點 → 閉合 </div> 共 5659 字元；+ 安全邊際 → 7000。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'class="showcase-lightbox wishlist-lightbox"',
    note: '[TASK-140-T11a] 書籤燈箱區塊必須存在（沿用 .showcase-lightbox 視覺，加 wishlist-lightbox modifier，見設計決策 #1）',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `:class="{ 'show': wishlistLightboxOpen }"`,
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 200 },
    note: '[TASK-140-T11a] 書籤燈箱必須綁 wishlistLightboxOpen，不得與既有 lightboxOpen 共用（研究題結論 #1、gotcha FE-ALPINE-04）',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: '@touchstart.passive="_wishlistLbTouchStart($event)"',
    // window 實測（Opus 2026-09-03）：anchor → @touchstart 241 字元、→ @touchend 306、
    // → 開頭標籤閉合 `>` 367。取 450＝涵蓋整個開頭標籤 ＋ 小幅邊際；刻意**不用** 7000
    // （同 anchor 其他 8 條用的那個窗 headroom 只剩約 114 字元，見 plan 陷阱段）。
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 450 },
    note: '[TASK-141b-T5] 書籤燈箱的觸控接線：拿掉這個綁定，手機／平板上滑動換片整個失效，而 node:test（測 JS 處理器）與其餘守衛全部照樣綠',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: '@touchend.passive="_wishlistLbTouchEnd($event)"',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 450 },
    note: '[TASK-141b-T5] 同上，touchend 那半。兩個綁定缺任一都會讓滑動失效',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: '/api/wishlist/cover?number=',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7000 },
    note: '[TASK-140-T11a] 書籤燈箱封面必須走本地 /api/wishlist/cover 端點，不得用 resolveCoverUrl／proxy-image（承重段第4條；退回打外站會破壞 F6 驗收5「零對外請求」，且 javbus 圖床沒有 Referer 會回 403，正是 T9 修的那個破圖）',
  },
  // Opus 抽驗（T11a 第 2 輪）：拔掉卡片上的 @click 入口後 lint/test 全綠——燈箱寫得再好
  // 也永遠開不了。window 實測：.wishlist-grid 開標 class= 錨點 → 閉合 </div> 共 2482 字元；
  // + 安全邊際 → 3000（與 T8 同錨同窗）。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: '@click="openWishlistLightbox(index)"',
    scope: { anchor: /class="wishlist-grid[^"]*"/, window: 3000 },
    note: '[TASK-140-T11a] 書籤卡片必須綁 @click="openWishlistLightbox(index)"——這是開燈箱的唯一入口；拔掉它使用者點卡片完全沒反應、燈箱永遠開不了，而其餘守衛與測試都照樣綠（v0.12.1 同形事故）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-arrow-return-left',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a] 書籤燈箱不得出現返回詳情鈕（spec F5 驗收4，書籤沒有本地檔案可返回）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-folder2-open',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a] 書籤燈箱不得出現開資料夾鈕（書籤沒有本地檔案）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-play-fill',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a] 書籤燈箱不得出現播放鈕（書籤沒有本地檔案）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-bookmark-plus',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a] 書籤燈箱不得出現加入書籤鈕（本身就在書籤清單裡）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-bookmark-fill',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a→141b-T7 訂正] 書籤燈箱不得出現 `bi-bookmark-fill` 這顆「書籤圖示」的移除鈕。⚠️ 原 note 寫「唯一下游動作是開原站，移除走 grid 卡的垃圾桶」——**那個意圖已被 spec F8.4／CD-9 取代**：141b-T7 起燈箱裡就有移除鈕了（用 `bi-trash3`，與牆上卡片同一個圖示語彙）。本條**仍然有效**，但守的是「別用書籤圖示當移除鈕」——那會與『加入書籤』的圖示混淆',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-pencil',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a] 書籤燈箱不得出現編輯鈕（spec F5 驗收4：那些需要本地檔案）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'bi-translate',
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 7500 },
    note: '[TASK-140-T11a] 書籤燈箱不得出現翻譯鈕（spec F5 驗收4：那些需要本地檔案）',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: '@click.stop="removeFromWishlistInLightbox()"',
    // window 實測（Opus 2026-09-03）：anchor → 本字面距離 2860 字元；訂 3200（約 340 字元安全邊際，
    // 見「現況分析」F 段完整量測過程）。不得抄旁邊 7000 那個窗——那是給區塊「頭部」規則用的預算，
    // 本規則的目標字面在區塊中段，用 7000 雖然也能過但會虛耗窗口、也會誤導未來的人以為這是頭部規則。
    scope: { anchor: /class="showcase-lightbox wishlist-lightbox"/, window: 3200 },
    note: '[TASK-141b-T7] 書籤燈箱移除鈕的接線鎖：這顆鈕是燈箱裡唯一的移除入口（spec F8.4），字面被改掉或刪掉的話，燈箱裡就再也移除不了、而 node:test（測 JS 函式）與其餘守衛全部照樣綠。`.stop` 一併鎖住：它在目前 DOM 下是防禦性冗餘（祖先 .lightbox-content 已有無條件 @click.stop 攔截冒泡），但與同容器既有那顆鈕寫法一致；若日後有人拿掉 .lightbox-content 那道攔截，這裡就是唯一的防線',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'x-transition:enter-end="opacity-100"',
    count: 6,
    note: '[TASK-141b-T8] F8.3 三處（搜尋燈箱/單片大卡/搜尋格牆卡）加入鈕與移除鈕共 6 顆，各帶一組 x-transition:enter* 過渡（CD-18）。全域無 scope——這個精確字面（不含 translate 尾碼）在改動前全檔 0 筆命中，是本卡獨有，不與既有 toast 容器的 "opacity-100 translate-y-0" 衝突。count 掉到 6 以下代表有鈕的 enter 過渡被拿掉了。',
  },
  // 🔴 branch review P3-2（Opus 2026-09-03）：上面那條只鎖 enter-end，是三分之一。
  // `x-transition:enter*` 是三件一組——拿掉 **enter-start** 之後過渡實際失效（沒有起始
  // opacity，等於從 1 到 1），而 lint 與 node:test **全綠**：正是上面那條 note 說要擋的東西。
  // 三個字面在改動前全檔各 0 筆命中，是本卡獨有，全域無 scope 安全。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'x-transition:enter-start="opacity-0"',
    count: 6,
    note: '[branch review P3-2] 同上 6 顆鈕的 enter 起始狀態。少了它 opacity 從 1 到 1，過渡靜默失效。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'x-transition:enter="transition ease-out duration-150"',
    count: 6,
    note: '[branch review P3-2] 同上 6 顆鈕的 enter 過渡本體（時長對齊 OpenAver.motion.DURATION.fast）。少了它就沒有 transition class，起訖狀態瞬間切換。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'forbidden-string',
    pattern: 'x-transition:leave',
    scope: { anchor: /@click="addToWishlistFromLightbox\(currentLightboxVideo\(\)\)"/, window: 1600 },
    note: '[TASK-141b-T8] CD-18：搜尋燈箱這對加入/移除鈕只寫 enter、不寫 leave（雙向 crossfade 會讓兩顆鈕同時 display，overlay 變雙寬）。window 實測（Opus）：anchor → 移除鈕 </button> 距離 1377 字元，訂 1600（約 220 字元邊際）。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'forbidden-string',
    pattern: 'x-transition:leave',
    scope: { anchor: /@click="addToWishlistFromDetail\(current\(\)\)"/, window: 1500 },
    note: '[TASK-141b-T8] CD-18，同上，單片大卡這對鈕。window 實測：anchor → 移除鈕 </button> 距離 1163 字元，訂 1500（約 340 字元邊際）。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'forbidden-string',
    pattern: 'x-transition:leave',
    scope: { anchor: /@click\.stop="addToWishlistFromGrid\(result, \$event\)"/, window: 1600 },
    note: '[TASK-141b-T8] CD-18，同上，搜尋格牆卡這對鈕。window 實測：anchor → 移除鈕 </button> 距離 1362 字元，訂 1600（約 240 字元邊際）。',
  },
  // ---- [TASK-140-T12] 書籤面板三層容器結構（原「頂部批次清理鈕 F7 驗收1-3」那三條已隨 141a-T6 退場） ----
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'class="wishlist-panel"',
    note: '[TASK-140-T12] 三層分工 wrapper 必須存在（plan「容器結構寫死」，Codex Phase 2 P2-3）——沒有它，書籤格的尺寸宣告會退回掛在會 shrink 的層，重現 T9 的 110×727',
  },
  // Opus 抽驗（T12 Step 6）：把 wrapper 的 listMode 閘拿掉之後 lint 與 npm test 全綠——
  // 而後果是 wrapper 在搜尋模式下仍是 .result-area 的 flex item，與 #resultCard 並排搶寬度，
  // 搜尋結果被擠成半邊（＝T9 那個 owner 一眼看到的並排缺陷，換一個容器重演一次）。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `<div class="wishlist-panel" x-show="listMode === 'wishlist'"`,
    note: '[TASK-140-T12] 書籤 wrapper 必須自帶 listMode 閘——少了它，wrapper 在搜尋模式下仍是 .result-area 的 flex item，會與搜尋結果並排搶寬度把結果擠成半邊（T9 修過的同一種缺陷）',
  },

  // ---- [lint-guard 141a-T5] 對帳呼叫點逐檔計數（spec F2／設計決策 5）----
  // 鎖 scanner/scraper/wishlist 三個已知檔案的 reconcile_wishlist( 出現次數。
  // 多掛會把通知 buffer 灌爆；少掛會讓該觸發點形同虛設。不是全庫白名單——
  // 全新第四個檔案掛對帳不會被這三條攔下（見 TASK-141a-T5 DoD 8 邊界）。
  { file: 'web/routers/scanner.py', kind: 'structure-count', pattern: 'reconcile_wishlist(', count: 1,
    note: '[lint-guard 141a-T5] 對帳呼叫點逐檔計數：scanner.py 恰 1 處（generate_avlist 收尾），多一處或少一處代表未來 branch 順手多掛/漏掛觸發點' },
  // scraper.py 的兩個出口共用 helper `_reconcile_wishlist_after_write()`（ruff C901 逼出來的抽取，
  // 見該函式 docstring），所以這一檔要兩條規則才數得對：
  //   · `reconcile_wishlist(` 恰 1 處 —— 只在 helper 內部（少一處＝對帳被拔掉）
  //   · `_reconcile_wishlist_after_write(` 恰 3 處 —— 1 個 def ＋ 2 個呼叫點（多一處＝順手多掛觸發點）
  { file: 'web/routers/scraper.py', kind: 'structure-count', pattern: 'reconcile_wishlist(', count: 1,
    note: '[lint-guard 141a-T5] 對帳呼叫點逐檔計數：scraper.py 的 reconcile_wishlist( 恰 1 處（只在 _reconcile_wishlist_after_write helper 內），少一處代表對帳被拔掉' },
  { file: 'web/routers/scraper.py', kind: 'structure-count', pattern: '_reconcile_wishlist_after_write(', count: 3,
    note: '[lint-guard 141a-T5] 對帳觸發點逐檔計數：scraper.py 的 _reconcile_wishlist_after_write( 恰 3 處（1 個 def ＋ enrich_single_endpoint 唯讀/一般分支各 1 個呼叫），多一處代表未來 branch 順手多掛觸發點（scrape-single／batch-enrich 也住這一檔）' },
  { file: 'web/routers/wishlist.py', kind: 'structure-count', pattern: 'reconcile_wishlist(', count: 1,
    note: '[lint-guard 141a-T5] 對帳呼叫點逐檔計數：wishlist.py 恰 1 處（T4 落地的 GET 載入前對帳）' },

  // ---- [lint-guard 141a-T7] 格牆／大卡切換鈕顯示條件（spec F4／設計決策 1、5）----
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: `x-show="listMode === 'search' && pageState === 'result' && (searchResults.length > 1 || actressProfile) && !isComposing()"`,
    note: '[lint-guard 141a-T7] 格牆／大卡切換鈕顯示條件必須為「結果模式＋(結果數>1 或有女優 hero 卡)＋非組合輸入」（CD-9，spec F4 驗收 2/2b/3；`|| actressProfile` 是 branch review P2 補的，見 search.html 該行上方註解）',
  },
  {
    file: 'web/static/js/pages/search/wishlist-aging.js',
    kind: 'forbidden-string',
    pattern: ['Date.parse(', 'new Date('],
    note: '[TASK-141b-T9] CD-6/CD-124a-2：禁止對日期字串做跨瀏覽器不保證一致的解析。全檔零合法場景需要這兩種字面——「現在時刻」一律由呼叫端以 Date.now() 注入，本檔自己不建構 Date 物件（與 release-window.js 不同，本檔不需要「取得當下時刻」的情境）。無 scope：全新檔案，全檔皆守備範圍。',
  },
  {
    file: 'web/static/css/pages/search.css',
    kind: 'required-string',
    pattern: 'position: absolute',
    scope: { anchor: /\.wishlist-aging\s*\{/, braceBalanced: true },
    note: '[TASK-141b-T9] .wishlist-aging 必須是 position:absolute（CD-17 零佔位）——少了它，元素會進文件流撐高卡片，而 node:test 與既有 lint 全部是綠的。scope 用 braceBalanced 精準扣住這條規則本體（CSS 宣告區塊無巢狀 {}，anchor 到對應 } 之間即為完整規則），不靠猜測字元距離。',
  },
  {
    file: 'web/static/css/pages/search.css',
    kind: 'required-string',
    pattern: 'var(--color-warning)',
    scope: { anchor: /\.wishlist-aging--stage2\s*\{/, braceBalanced: true },
    note: '[TASK-141b-T9] 第 2 階必須用既有註冊 token var(--color-warning)（owner 拍板，設計決策 1），不得手寫十六進位、不得用 --color-error。scope 用 braceBalanced 精準扣住這條規則本體。',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'item._imgError',
    scope: /<template x-for="\(item, index\) in wishlistItems"[\s\S]*?<\/template>/,
    note: '[TestWishlistCoverFadeGuard] TASK-141b-T10／CD-19：書籤卡封面狀態禁止掛在 item._imgError（loadWishlist() 整包覆蓋物件會讓封面消失）',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string', pattern: 'item._imgLoaded',
    scope: /<template x-for="\(item, index\) in wishlistItems"[\s\S]*?<\/template>/,
    note: '[TestWishlistCoverFadeGuard] TASK-141b-T10／CD-19：同上，禁止 item._imgLoaded 形狀',
  },

  // ---- [Codex PR review BLOCKER 2026-09-03] T10 的五條純字串掃描由 pytest 搬來這裡 ----
  // CLAUDE.md north-star：「能用 lint 機械處理的，就不該進 pytest、也不該耗 Codex 審」。
  // plan NC-3 只裁定了「既有那支 scope 守衛維持 pytest」，**沒有**授權新增的這幾條；
  // 實作端把那個授權就地擴大套用，且連 [lint-guard: pytest-justified] 標記都沒補。
  // 三條 required-string 的目標字面在 search.html 全檔各只出現一次（已量測），
  // 故不需要 scope——沒有任何兄弟元素能餵飽它們（FE-GUARD-22 的假綠風險為零）。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: ":loading=\"index < 8 ? 'eager' : 'lazy'\"",
    note: '[TASK-141b-T10 DoD5] 書籤卡首屏前 8 張 eager、其餘 lazy（閾值逐字抄自瀏覽頁）。少了它整面牆都是 lazy，冷載時首屏封面要等捲動才開始下載。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: ":fetchpriority=\"index < 8 ? 'high' : 'auto'\"",
    note: '[TASK-141b-T10 DoD5] 同上的 fetchpriority 那一半；兩個屬性要成對，只留一個等於沒做首屏優先。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'forbidden-string',
    pattern: 'loading="lazy"',
    scope: /<template x-for="\(item, index\) in wishlistItems"[\s\S]*?<\/template>/,
    note: '[TASK-141b-T10 DoD5] 書籤卡不得寫死 loading="lazy"（要走 :loading 綁定）。必須 scope：這個字面在搜尋結果牆那側是合法的、且出現在本區塊之前三次，裸鎖會恆紅。scope 用 template 邊界的完整 regex 而非固定字元窗——窗貼齊區塊邊界正是 T5/T7 踩過的靜默失效類別。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: 'x-show="!_wishlistCoverLoaded[item.number] && !_wishlistCoverError[item.number]"',
    note: '[TASK-141b-T10 DoD1] 骨架的三態 gate（未載入且未破圖才顯示 shimmer）。gate 寫錯會讓骨架與封面同時在場或永遠不消失。',
  },
  {
    file: 'web/static/js/pages/search/state/wishlist.js',
    kind: 'required-string',
    pattern: ['_wishlistCoverLoaded: {}', '_wishlistCoverError: {}'],
    stripLineComments: true,   // [branch review P3-3] 本 codebase 兩次踩過「註解餵飽守衛」（search.html:271 / wishlist.js:449 的註解都明文寫著這件事）——宣告被刪掉、字面只留在註解裡時，沒有這個旗標守衛照樣綠
    note: '[TASK-141b-T10 CD-19] 封面載入狀態必須是「番號為 key」的 state 宣告，且掛在 wishlist.js 的 state 上（loadWishlist() 內部不碰）。這是 CD-19 落點的另一半——模板側的兩條 forbidden 只擋得住「退回 item._imgLoaded」，擋不住「宣告整個被刪掉」。',
  },
  // 🔴 這兩條刻意拆成「一條規則扣一個 CSS 規則本體」，不是把整個 @media 當一袋字串掃。
  // 被取代的那支 pytest 是後者（`".wishlist-grid" in body and "opacity: 1" in body`），
  // 而 `.wishlist-empty` 自己也有一份 `opacity: 1` ⇒ **把封面那份刪掉照樣全綠**（fail-open）。
  // 這個洞是搬家時做反向驗證才量出來的：舊測試也有，不是本次新引入的，但不該原樣搬過來。
  // anchor 收在各自規則的 `{`，braceBalanced 從那裡起算 ⇒ scope 就是那一條規則的宣告區塊。
  {
    file: 'web/static/css/pages/search.css',
    kind: 'required-string',
    pattern: ['transition: none', 'opacity: 1'],
    scope: { anchor: /@media \(prefers-reduced-motion:\s*reduce\)\s*\{\s*:is\([^)]*\)\.wishlist-grid[^{]*\{/, braceBalanced: true },
    note: '[TASK-141b-T10 DoD7] PRM 下書籤封面淡入退化成「瞬間到位」：transition 關掉 ＋ opacity 直接是 1。少了 opacity:1 會留下一整面 opacity:0 的空白卡——「不執行動畫」與「瞬間到最終狀態」是兩件事（CD-11）。',
  },
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    pattern: ['item.created_at ? `/api/wishlist/cover?number=', '_wishlistCoverRetry[item.number] ? `&r='],
    note: '[branch review P2-1] 書籤卡封面的 :src 必須用 item.created_at 當閘。樂觀 unshift 的那一筆（addToWishlist 在 POST 之前就 unshift）沒有這個伺服器端欄位；沒有這道閘，它會在封面檔還沒寫完時就發 GET ⇒ 必定 404 ⇒ @error 寫進 _wishlistCoverError，而那張表依 CD-19 刻意不被 loadWishlist() 清掉 ⇒ 剛加的片在書籤牆上永遠是灰底「無圖」，只有 F5 才會好。事後清旗標不是解法：實測清了也不會重新請求（naturalWidth 仍 0），只會把占位換成破圖 icon。第二個字面是 Codex PR#177 第 2 輪 P2 補的重試 token：端點是「先 commit 那一列、才下載封面」（routers/wishlist.py:69→90），使用者按下加入後馬上切到書籤分頁（真瀏覽器實測 100ms 就撞得到）會拿到有 created_at 但封面還沒寫完的列 ⇒ 404 ⇒ 旗標永久。token 讓 :src 在 POST 回報 cover_available 之後變一次——**光清旗標不會讓瀏覽器重新請求**。',
  },
  {
    file: 'web/static/css/pages/search.css',
    kind: 'required-string',
    pattern: ['opacity: 1', 'animation: none'],
    scope: { anchor: /@media \(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\.wishlist-empty\s*\{/, braceBalanced: true },
    note: '[TASK-141b-T10 DoD7] PRM 下空狀態同理：animation 關掉 ＋ opacity 直接是 1。keyframes 的起始狀態是 opacity:0，只關 animation 不補 opacity:1 會讓「書籤是空的」那段字永遠不出現。',
  },

  // ---- [TASK-142-T1 CD-13] source_reachability 探測只碰根路徑，禁止目錄遍歷／開檔 ----
  // 陣列語意：任一命中即報錯。探測手段封閉清單只有 TCP 445 與「開根目錄本身」。
  // 159-T10a（CD-159-9）：exists 換成 `with os.scandir(root):` 開了就關、不迭代——
  // 權限不足時才分得出來。仍禁止的是「列出內容」：把 scandir 綁成迭代器（`as it`）或 for 迭代。
  {
    file: 'core/source_reachability.py',
    kind: 'forbidden-string',
    pattern: ['listdir', /scandir\([^)]*\)\s+as\b/, /\bin\s+os\.scandir/, '.walk(', 'open('],
    note: '[TASK-142-T1 CD-13／159-T10a] core/source_reachability.py 不得列出來源夾內容（listdir／scandir 迭代／.walk(／open(；只准 `with os.scandir(root):` 開了就關，spec-142 F1 驗收 7）',
  },

  // ---- [TASK-143-T6 CD-143-7] readonly_producer 番號表單一來源，禁止自建 NUM_PATTERNS ----
  {
    file: 'core/readonly_producer.py',
    kind: 'forbidden-string',
    // 定義形狀正則，不是 raw 子字串：evalForbiddenString 是全文比對、**不剝** Python
    // 註解與 docstring（本檔的 stripPythonNoise() 只接在 evalStructureCount 上），而
    // core/readonly_producer.py 的 wrapper docstring 本來就含 NUM_PATTERNS 這個字面
    // ⇒ raw 子字串守衛落地當下就會誤判自己人。
    // 涵蓋三種**自然寫法**（T6 sonnet review P2）：裸賦值 / 型別註記 / self 屬性。
    // 刻意不涵蓋改名（`_NUM_PATTERNS`、`PATTERNS`）與 setattr —— 那是刻意規避，
    // 屬粗顆粒守衛已接受的代價（CD-143-7：只擋形狀，不做對帳矩陣）。
    pattern: /^\s*(?:self\.)?NUM_PATTERNS\s*(?::[^=\n]*)?=/m,
    note: '[TASK-143-T6 CD-143-7] core/readonly_producer.py 不得自建 NUM_PATTERNS 表（CD-143-2 單一來源是 core/gallery_scanner.py）',
  },

  // ==== [TASK-144-T7] Auto Organize Panel 掛載 ====
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'type="module" src="/static/js/components/auto-organize-panel.js"',
    note: '[TASK-144-T7] base.html 缺少 auto-organize-panel.js 的 module script tag——元件沒被載入，按鈕點了沒反應',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'x-data="autoOrganizePanel"',
    note: '[TASK-144-T7] search.html 缺少 x-data="autoOrganizePanel"——Alpine 找不到元件，面板永遠不出現',
  },
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'href="/static/css/components/auto-organize-panel.css"',
    note: '[TASK-144-T7] base.html 缺少 auto-organize-panel.css 的 link——面板 surface 樣式不會載入',
  },

  // ---- [TASK-144 Codex 四審] 自動整理開關的 :disabled 綁定不得退回成只看 !folderIsSet ----
  // scope 錨定「:checked="enabled"」後緊接的 :disabled="..." 屬性值本身（regex 第一個
  // capture group 當 scopedText），只鎖這顆 checkbox、不影響下面 runNow 按鈕自己的
  // :disabled="!folderIsSet || loading"。清空最愛資料夾後 folderIsSet 會變 false，
  // 若綁定只看 !folderIsSet，開著的開關會變成「打勾但灰掉」永遠關不掉。
  {
    file: 'web/templates/search.html',
    kind: 'required-string',
    scope: /:checked="enabled"\s+:disabled="([^"]*)"/,
    pattern: '!enabled',
    note: '[TASK-144 Codex 四審] search.html 自動整理開關的 :disabled 綁定必須含 !enabled（只看 !folderIsSet 會讓清空最愛資料夾後這顆開關關不掉）',
  },

  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'favoriteScannerLinked === false', note: '[TestSearchEmptyFavoriteLinkedStrict] CD-146a-16／FE-JS-01：三態嚴格比較不得精簡成 !favoriteScannerLinked' },

  // ---- [pre-merge / grok-4.6 branch review P3 第 2 條] 空狀態的設定相依列必須等 appConfig 載入 ----
  // appConfig 初值是 null，而 Alpine 不 await async init()：第一幀 favoriteConfigured() 回 false、
  // buildNamingPreview() 退回預設格式 ⇒ 已設最愛的人先被叫去「指定一個資料夾」、改過檔名格式的人
  // 先看到別人的範例。實測本機 4/4 冷載 /api/config 都在 FCP 前 10–41ms 到（看不到），
  // 但那是本機餘裕；靜態資源已快取而 API 慢時先後會反過來。
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'appConfig !== null && !favoriteConfigured()', note: '[pre-merge] 空狀態「未設定最愛」那一列必須等 appConfig 載入（否則已設定的人先看到叫他去設定）' },
  // 命名範例列改由 empty-explainer.js 的 namingPreviewReady() 回答「準備好了沒」
  // （CodeRabbit PR#187：樣板只鎖 appConfig，漏了平行載入的 formatVariables）。
  // 樣板這條只鎖「有沒有問那個函式」，**不再鎖它問了哪幾個輸入**——輸入清單歸下面兩條，
  // 與消費端同檔，下次多一個輸入時改的人看得到。
  { file: 'web/templates/search.html', kind: 'required-string', pattern: 'x-show="namingPreviewReady()"', note: '[CodeRabbit PR#187] 空狀態命名範例那一列的 gating 必須走 namingPreviewReady()，不要在樣板列舉輸入' },
  { file: 'web/static/js/pages/search/state/empty-explainer.js', kind: 'required-string', pattern: 'this.appConfig !== null', note: '[CodeRabbit PR#187] namingPreviewReady() 必須把 appConfig 算進去' },
  { file: 'web/static/js/pages/search/state/empty-explainer.js', kind: 'required-string', pattern: '(this.formatVariables || []).length > 0', note: '[CodeRabbit PR#187] namingPreviewReady() 必須把 formatVariables 算進去（length>0 而非 !==null：回應缺 variables 時會寫成 []）' },

  // ---- [TASK-146a-T5] errorKind snapshot/restore pairing ----
  {
    file: 'web/static/js/pages/search/state/search-flow.js', kind: 'paired-string',
    ifPresent: 'errorKind: this.errorKind', thenRequire: 'this.errorKind = snap.errorKind',
    note: 'errorKind pairing: _searchSnapshot 有 errorKind 但 cancelSearch() 未還原',
  },

  // ---- [TASK-147b-T3 / CD-147b-5b] state-batch.js 三欄判準接線守衛 ----
  // ① result-item handler 必須真的呼叫 didEnrichSomething（node:test 證明不了接線）
  // ② didEnrichSomething 本體必須含 fields_filled（擋判準退回兩欄動畫那一套）
  // 兩條各自獨立轉紅：註解呼叫行只紅①；拿掉 fields_filled 分支只紅②。
  {
    file: 'web/static/js/pages/scanner/state-batch.js', kind: 'required-string',
    pattern: 'didEnrichSomething(',
    scope: { anchor: /else if \(event\.type === 'result-item'\) \{/, braceBalanced: true },
    stripLineComments: true,
    note: '[TASK-147b-T3 CD-147b-5b] result-item handler 必須呼叫 didEnrichSomething(（接線守衛）',
  },
  {
    file: 'web/static/js/pages/scanner/state-batch.js', kind: 'required-string',
    pattern: 'fields_filled',
    scope: { anchor: /export function didEnrichSomething\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[TASK-147b-T3 CD-147b-5b] didEnrichSomething 本體必須含 fields_filled（三欄判準不得退回兩欄）',
  },

  // ---- [TASK-150b-T3 / CD-150b-7] viewport gate：封面 _coverRequested ＋ x-intersect ＋ shim ----
  // 規則 1：showcase 影片卡 <img> 的 :src 表達式必須逐字如此（完整屬性值，非裸 _coverRequested）。
  // scope 錨在唯一字首 `<img :src="((index < 8`；window 實測 862（錨 → x-init 收尾 `">`），取 900。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: ':src="((index < 8 && mode === \'grid\') || video._coverRequested) ? video.cover_url : null"',
    scope: { anchor: /<img :src="\(\(index < 8/, window: 900 },
    note: '[TASK-150b-T3 CD-150b-7 #1] showcase 影片卡 <img> 的 :src 表達式必須逐字如此（鎖完整屬性值，不是裸 _coverRequested——裸字面會被同一個 scope window 內 x-intersect 那行供應，Codex PR review P3 實測：只把 :src 裡的 video._coverRequested 改成 false，1348 條全綠而整牆只剩前 8 張圖）',
  },
  // 規則 2：禁止退回舊的裸 :src="video.cover_url"（完整舊屬性字串，不可裸識別字——
  // 新表達式合法含 video.cover_url，裸字面會誤傷；掃描粒度＝屬性值，避開 FE-GUARD-20）。
  // scope 與規則 1 同一個 anchor／window。
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: ':src="video.cover_url"',
    scope: { anchor: /<img :src="\(\(index < 8/, window: 900 },
    note: '[TASK-150b-T3 CD-150b-7 #2] showcase 影片卡的加閘 <img> 區塊內不得另外出現未加閘的裸 :src="video.cover_url"（半退回／重複 img）。⚠️ 完整退回成裸 :src 的情形不是由本規則的 pattern 比對抓到的——那會讓本規則與規則 1／3 共用的 scope.anchor 一起消失，三條都以「anchor 找不到」fail-closed 轉紅；本規則自己的 matches() 只在「anchor 還在、但區塊內多了一個裸 :src」時才會執行到（已實測）',
  },
  // 規則 3：骨架 shimmer x-show 必須含 `!video._imgLoaded && video._coverRequested` 片段。
  // 同 anchor；window 實測 1170（錨 → shimmer </div>），取 1200。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '!video._imgLoaded && video._coverRequested',
    scope: { anchor: /<img :src="\(\(index < 8/, window: 1200 },
    note: '[TASK-150b-T3 CD-150b-7 #3] 骨架 shimmer x-show 必須含 !video._imgLoaded && video._coverRequested',
  },
  // 規則 4：base.html AC-2 fallback 必須真的「賦值」替代建構子（非裸 IntersectionObserver），
  // 且守門條件必須是 !ok（IO 不可用才 fallback），不是 ok（IO 可用才 fallback，語意反轉）。
  // scope 錨在唯一的 Alpine.store('ui'；window 實測 768（錨 → shim IIFE `})();`），取 800。
  // pattern 逐字含 `if (!ok) {` 到賦值那行（含實際縮排／換行），結尾距 anchor 仍在 800 內。
  // 沙盒實測（150b-T3 修正）：只鎖裸 `window.IntersectionObserver = function (cb) {` 時，
  // 把 `if (!ok) {` 改成 `if (ok) {` 不動賦值字面本身 ⇒ 1349 條全綠，而 shim 在 IO 正常的
  // 瀏覽器上會被換成 pass-through，viewport 閘門靜默失效退回全量請求。改成含守門條件的
  // 完整字面後，翻轉 !ok/ok 會讓這條字面消失 ⇒ 規則必須紅。
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'if (!ok) {\n              window.IntersectionObserver = function (cb) {',
    scope: { anchor: /Alpine\.store\('ui'/, window: 800 },
    note: '[TASK-150b-T3 CD-150b-7 #4] base.html 的 AC-2 fallback 必須真的「賦值」一個替代建構子，且守門條件必須是 !ok 不是 ok（語意反轉會讓 shim 在 IO 正常瀏覽器上把它換成 pass-through，viewport 閘門靜默失效）。鎖「守門條件 ＋ 賦值」同一個完整字面，不是裸 IntersectionObserver 或裸 !ok——裸字面在同 window 內各自還有其他供應者，只鎖其一擋不住「賦值還在、但條件被反轉」這種掏空（沙盒實測，見 150b-T3 修正）',
  },
  // 規則 5：viewport gate 的「寫入端」——x-intersect directive 本身必須存在且 N 正確。
  // 規則 1/2/3 守的都是讀取端（:src 表達式、骨架 shimmer），刪掉 x-intersect 整行時
  // `_coverRequested` 這個字面仍留在 :src 裡 ⇒ 四條全綠而功能全毀（實測）。這條補寫入端。
  // window 與規則 1 同 900：搬家後 x-intersect 在 @error 後，pattern 結尾距 anchor 實測 664，仍在 900 內。
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-intersect.once.margin.690px="video._coverRequested = true"',
    scope: { anchor: /<img :src="\(\(index < 8/, window: 900 },
    note: '[TASK-150b-T3 CD-150b-7 #5] viewport gate 的寫入端：x-intersect directive 本身 ＋ N=690 ＋ 設 _coverRequested 三者一體，逐字鎖住。刪掉這一行會讓 _coverRequested 永遠是 false ⇒ 整面封面牆只剩前 8 張、其餘永久空白且捲動不補，而規則 1/2/3 全部照樣綠（它們守的是讀取端，_coverRequested 字面仍在 :src 裡）',
  },
  // 規則 6：pass-through 的行為契約——fallback 的 observe() 必須「立刻回報已相交」。
  // 只鎖賦值存在（規則 4）擋不住「賦值了但 observe() 是空函式」這種掏空。
  // isIntersecting: true 全檔唯一（grep -c = 1）；結尾距 anchor 實測 523，仍在 800 內。
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'isIntersecting: true',
    scope: { anchor: /Alpine\.store\('ui'/, window: 800 },
    note: '[TASK-150b-T3 CD-150b-7 #6] fallback 的 observe() 必須同步回報 isIntersecting: true（pass-through 語意）。規則 4 只鎖「有沒有賦值」，這條鎖「賦值的東西會不會真的讓卡片載圖」——兩者缺一都會讓 shim 在 IO 不可用時變成擺設',
  },
  // ---- [TestInsightsESMGuard] insights.html pre_alpine_module wiring (156a-T2) ----
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: 'pre_alpine_module', note: '[TestInsightsESMGuard] test_insights_html_has_pre_alpine_module (block)' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: 'insights/main.js', note: '[TestInsightsESMGuard] test_insights_html_has_pre_alpine_module (main.js script)' },

  // ---- [TestInsightsSidebarGuard] 側欄「片庫分析」連結與頒獎台 icon (156a-T4, CD-156-7) ----
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'href="/insights"', count: 2, note: '[TestInsightsSidebarGuard] test_sidebar_insights_link_present — offcanvas 與 desktop sidebar 各一處' },
  { file: 'web/templates/base.html', kind: 'required-string', pattern: 'M6 2.5A.5.5 0 0 1 6.5 2h3a.5.5 0 0 1 .5.5V14H6z', count: 2, note: '[TestInsightsSidebarGuard] test_sidebar_insights_icon_svg_present — 頒獎台 icon 的 path 資料，兩處插入點逐字相同' },
  { file: 'web/templates/base.html', kind: 'forbidden-string', pattern: 'stroke=', note: '[TestInsightsSidebarGuard] test_sidebar_insights_icon_is_filled_not_stroked — CD-156-7：頒獎台 icon 必須是 fill=currentColor 實心路徑，不是 stroke 線條（base.html 目前全檔零既有 stroke= 用法，已用 grep -c "stroke=" web/templates/base.html 確認為 0，此規則對全檔有效、不需 scope）' },

  // ---- [TestInsightsVendorGuard] insights.html 載入 ECharts UMD (156a-T5, CD-156-6) ----
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: 'src="/static/vendor/echarts/echarts.min.js"', note: '[TestInsightsVendorGuard] test_insights_html_loads_echarts_script' },
  { file: 'web/templates/insights.html', kind: 'forbidden-string', pattern: '<script type="module" src="/static/vendor/echarts/echarts.min.js"', note: '[TestInsightsVendorGuard] test_insights_echarts_script_not_module — UMD build 不能用 type=module 載入' },

  // ---- [161a-T5a] 單一 sel 狀態貫穿分析頁 ----
  { file: 'web/static/js/pages/insights/state.js', kind: 'structure-count', pattern: "this.$watch('sel',", count: 1, note: "[161a-T5a] state.js 重繪入口只有一個 $watch('sel')（CD-161a-3）：兩個以上＝某個條件的變更會重繪兩次，零個＝點女優／片商不重繪任何一張卡" },
  { file: 'web/static/js/pages/insights/state.js', kind: 'forbidden-string', pattern: "$watch('period'", note: "[161a-T5a] state.js 重繪入口只有一個 $watch('sel')：不得殘留舊的 $watch('period')" },
  { file: 'web/static/js/pages/insights/state.js', kind: 'forbidden-string', pattern: "$watch('focus'", note: "[161a-T5a] state.js 重繪入口只有一個 $watch('sel')：不得殘留舊的 $watch('focus')" },
  { file: 'web/static/js/pages/insights/charts.js', kind: 'required-string', pattern: '_donutCallbacks.toggleMaker(name)', note: '[161a-T5a] charts.js 圓餅點擊寫 sel.maker：點圓餅必須經 toggleMaker 回呼設到那家片商' },
  { file: 'web/static/js/pages/insights/charts.js', kind: 'required-string', pattern: 'const opacity = _opacityForIndex(dimmed, i);', note: '[161a-T5a] charts.js 年份長條單 series 的淡化吃 agg.dimmed（range 可用）：改成固定 1 ＝選了年份（或範圍）後範圍外的欄不再淡化' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: `x-show="sel.period.type !== 'all'"`, scope: { anchor: /id="tileYear"/, window: 600 }, note: '[161a-T5a] #tileYear 期間非 all（含範圍）就顯示年份值與 ×：只認 year 會讓範圍選取後年份格變回「全部年份」、× 消失' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: 'periodTileLabel()', note: '[161a-T5a] 模板消費的新接線：年份格顯示值（periodTileLabel）' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: 'cardEmptyKey(', count: 5, note: '[161a-T5a] 模板消費的新接線：五張卡的空狀態文字都走 cardEmptyKey（模板現有 5 處，下限）' },

  // ---- [161a-T5b] 頂排拆女優格／片商格、兩條件疊加 ----
  { file: 'web/static/js/pages/insights/state.js', kind: 'required-string', pattern: '#tileActress .insights-focus-avatar:not(.mk)', count: 2, note: '[161a-T5b] state.js 頭像飛行目標是 #tileActress（清除分支與 _flyAvatarToFocusTile 各一處）：指到別格＝替身飛不到頭像、卡在半空' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: '@click="clearMaker()"', scope: { anchor: /id="tileMaker"/, window: 2500 }, note: '[161a-T5b] #tileMaker 的 × 接 clearMaker：接成別的＝按片商格的 × 清掉別的條件' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: '@click="clearActress()"', scope: { anchor: /id="tileActress"/, window: 2500 }, note: '[161a-T5b] #tileActress 的 × 接 clearActress：接成別的＝按女優格的 × 清掉別的條件' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: "t('insights.all_maker')", scope: { anchor: /id="tileMaker"/, window: 2500 }, note: '[161a-T5b] #tileMaker 未選時顯示淡色「全部片商」：寫成別的字＝使用者分不出兩格' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: "t('insights.all_actress')", scope: { anchor: /id="tileActress"/, window: 2500 }, note: '[161a-T5b] #tileActress 未選時顯示淡色「全部女優」：寫成別的字＝使用者分不出兩格' },
  { file: 'web/templates/insights.html', kind: 'forbidden-string', pattern: 'tileFocus', note: '[161a-T5b] 頂排無 #tileFocus（insights.html）：舊的單一焦點格已拆成 #tileActress／#tileMaker' },
  { file: 'web/static/js/pages/insights/state.js', kind: 'forbidden-string', pattern: 'tileFocus', note: '[161a-T5b] 頂排無 #tileFocus（state.js）：舊的單一焦點格已拆成 #tileActress／#tileMaker' },

  // ---- [161a-T6b] 年份拖曳：預覽蓋板、年表淡化、觸控降級、dispose 清理 ----
  { file: 'web/static/js/pages/insights/charts.js', kind: 'forbidden-string', pattern: "getZr().on('click'", note: '[161a-T6b] charts.js 年份圖不得有 click 監聽：單點與範圍都由 mousedown→mouseup 手勢提交，加回 click 會在拖完範圍後多觸發一次單點、把剛選的範圍改成單年' },
  { file: 'web/static/js/pages/insights/charts.js', kind: 'required-string', pattern: "document.addEventListener('mouseup'", note: '[161a-T6b] charts.js 拖曳要掛 document 層 mouseup：沒掛則滑鼠拖出畫布才放開時收不了尾，手勢卡住' },
  { file: 'web/static/js/pages/insights/charts.js', kind: 'required-string', pattern: 'cancelYearsDrag(); // initYearsChart', note: '[161a-T6b] charts.js initYearsChart 重建前要 cancelYearsDrag：少了它，bfcache 還原重建年份圖時舊手勢與 document 監聽沒收掉' },
  { file: 'web/static/js/pages/insights/charts.js', kind: 'forbidden-string', pattern: '$action', note: "[161a-T6b] charts.js 不得用 $action:'remove'：在全新圖上 remove 會丟錯被吞掉、整頁空白（FE-JS-05），預覽只切 invisible" },
  { file: 'web/static/js/pages/insights/charts.js', kind: 'required-string', pattern: 'graphic: [buildDragPreviewGraphic(null, ', note: '[161a-T6b] updateYearsChart 每次重繪都帶預覽 graphic：少了它，重繪後預覽不會被重設成隱藏、提交範圍後高亮可能殘留' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: 'isYearInSel(', note: '[161a-T6b] insights.html 年表年份欄淡化吃範圍：模板消費 isYearInSel，沒用到則選範圍後年表沒有任何年份被標成選中' },
  { file: 'web/templates/insights.html', kind: 'forbidden-string', pattern: 'sel.period.year ===', note: '[161a-T6b] insights.html 年表年份欄淡化吃範圍：只認單年 sel.period.year 會讓範圍內的欄全被淡化' },
  // ---- [161a-T7] 片數格跳轉接線 ----
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: '@click="goBrowse()"', scope: { anchor: /id="tileCount"/, window: 1200 }, note: '[161a-T7] #tileCount 的 click 接 goBrowse：沒接＝片數格看起來可點、手形游標也有，但點下去什麼都沒發生' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: "t('insights.count_open_browse')", scope: { anchor: /id="tileCount"/, window: 1200 }, note: '[161a-T7] #tileCount tooltip 用 insights.count_open_browse：寫成別的字＝使用者不知道點了會去哪' },
  { file: 'web/templates/insights.html', kind: 'required-string', pattern: "'is-clickable': canGoBrowse", scope: { anchor: /id="tileCount"/, window: 1200 }, note: '[161a-T7] #tileCount 可點樣式只在 canGoBrowse 時：寫成恆真＝片數 0 的格子仍顯示手形與 hover 淡染' },

  // ---- [161b-T3] 響應式頒獎台人數與標題接線 ----
  { file: "web/static/js/pages/insights/state.js", kind: "forbidden-string", pattern: "rank <= 3", note: "[161b-T3] state.js 不得寫死頒獎台人數 3" },
  { file: "web/static/js/pages/insights/state.js", kind: "forbidden-string", pattern: "rank > 3", note: "[161b-T3] state.js 不得寫死頒獎台人數 3" },
  { file: "web/static/js/pages/insights/aggregate.js", kind: "forbidden-string", pattern: "rank <= 3", note: "[161b-T3] aggregate.js 不得寫死頒獎台人數 3" },
  { file: "web/static/js/pages/insights/aggregate.js", kind: "forbidden-string", pattern: "rank > 3", note: "[161b-T3] aggregate.js 不得寫死頒獎台人數 3" },
  { file: "web/static/js/pages/insights/state.js", kind: "required-string", pattern: "classifyBoardTransition(oldRows, newRows, this.podiumSize)", note: "[161b-T3] 分類要傳 podiumSize" },
  { file: "web/templates/insights.html", kind: "required-string", pattern: "podiumPositionClass(row.rank, podiumSize)", note: "[161b-T3] 頒獎台位置 class 要傳 podiumSize" },
  { file: "web/templates/insights.html", kind: "required-string", pattern: "'podium--5': podiumSize === 5", note: "[161b-T3] .podium 掛 podium--5" },
  { file: "web/templates/insights.html", kind: "required-string", pattern: "'is-podium-3': podiumSize === 3", note: "[161b-T3] 根容器掛 is-podium-3" },
  { file: "web/templates/insights.html", kind: "required-string", pattern: "<h2 x-text=\"boardRestTitle\"></h2>", note: "[161b-T3] 名單卡標題接 boardRestTitle" },

  // ---- [161b-T4] 五人頒獎台與桌面名單列數 ----
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "        --board-slot-h: calc(17rem + var(--board-rest-rows) * 2.5625rem + 0.5rem);", note: "[161b-T4] 桌面固定高度的列數吃 --board-rest-rows" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "    --board-rest-rows: 22;", note: "[161b-T4] is-podium-3 時名單列數為 22" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "    --board-rest-rows: 20;", note: "[161b-T4] 預設名單列數為 20" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "    min-width: calc(5 * var(--board-text-size) + 0.75rem);", note: "[161b-T4] 5 人槽最小寬保證 5 個全形字" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "    flex: 0 1 5.5rem;", note: "[161b-T4] 5 人槽可縮不可長" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "    column-gap: 0.5rem;", note: "[161b-T4] 5 人版台座與人員層間距 0.5rem" },

  // ---- [161b-T5] 頭像選人與 pointer hover 預覽 ----
  { file: "web/templates/insights.html", kind: "structure-count", pattern: "@click.stop=\"openPreview(", count: 2, note: "[161b-T5] 頭像 click 開預覽只剩頂排與 costar self 兩處" },
  { file: "web/templates/insights.html", kind: "structure-count", pattern: "@click.stop=\"sel.actress && openPreview(", count: 1, note: "[161b-T5] 頂排名字維持 click 開預覽" },
  { file: "web/templates/insights.html", kind: "structure-count", pattern: "@pointerenter=\"scheduleOpenPreview(row.name, $el, $event)\"", count: 9, note: "[161b-T5] 九處頭像與名字 hover 走 pointerenter 並傳 $event" },
  { file: "web/templates/insights.html", kind: "structure-count", pattern: "@pointerleave=\"cancelOpenPreview()\"", count: 9, note: "[161b-T5] 九處 pointerleave 收預覽" },
  { file: "web/templates/insights.html", kind: "forbidden-string", pattern: "@mouseenter=\"scheduleOpenPreview(row.name", note: "[161b-T5] 列表頭像不得殘留 mouseenter 排程預覽" },
  { file: "web/static/js/pages/insights/state.js", kind: "required-string", pattern: "if (!isHoverPointer(ev)) return;", note: "[161b-T5] scheduleOpenPreview 第一行以 isHoverPointer 擋觸控" },
  { file: "web/static/js/pages/insights/state.js", kind: "required-string", pattern: "this.cancelOpenPreview();", scope: { anchor: /flyAndFocusActress\(name, event/, window: 200 }, note: "[161b-T5] flyAndFocusActress 進入先 cancelOpenPreview" },

  // ---- [161b-T6] 年表格子選女優與年份 ----
  { file: "web/templates/insights.html", kind: "required-string", pattern: "@click.stop=\"ganttCellClick(row.name, cell, ganttAxis, $event)\"", note: "[161b-T6] 年表格子 click 接 ganttCellClick 並 .stop（不冒泡到列）" },
  { file: "web/static/js/pages/insights/state.js", kind: "required-string", pattern: "toggleGanttCell(this.sel, name, year)", note: "[161b-T6] 格子點擊的年份轉換走 toggleGanttCell" },
  { file: "web/static/js/pages/insights/state.js", kind: "required-string", pattern: ".closest('.gantt-row')", note: "[161b-T6] 格子點擊由所在列取得飛行來源列" },
  { file: "web/static/js/pages/insights/state.js", kind: "required-string", pattern: "flyAndFocusActress(name, event, nextSel) {", note: "[161b-T6] flyAndFocusActress 三個提交出口一律走 _commitFocusSel" },
  { file: "web/static/js/pages/insights/state.js", kind: "structure-count", pattern: "this._commitFocusSel(name, nextSel)", count: 3, note: "[161b-T6] flyAndFocusActress 三個提交出口一律走 _commitFocusSel" },
  { file: "web/static/js/pages/insights/state.js", kind: "structure-count", pattern: "this.toggleActressFocus(name);", count: 1, note: "[161b-T6] flyAndFocusActress 三個提交出口一律走 _commitFocusSel" },
  { file: "web/static/js/pages/insights/state.js", kind: "structure-count", pattern: "{ currentTarget: rowEl }", count: 2, note: "[161b-T6] 年表格子 click 接 ganttCellClick 並 .stop（不冒泡到列）" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "cursor: pointer;", scope: { anchor: /\.gantt-row:not\(\.gantt-head-row\)/, window: 80 }, note: "[161b-T6] 年表資料列（排除表頭列）游標為 pointer" },

  // ---- [161b-T9] 片數格常駐淡染與可點箭頭字色 ----
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "color-mix(in oklch, var(--color-primary) 3%, transparent),", scope: { anchor: /#tileCount\.is-clickable\.is-scoped \{/, window: 400 }, note: "[161b-T9] 片數格可點態平常就帶 3% 主色底" },
  { file: "web/static/css/pages/insights.css", kind: "required-string", pattern: "color: var(--text-primary); /* ↗ 與數字同字色 */", scope: { anchor: /#tileCount\.is-clickable\.is-scoped \.insights-open-arrow \{/, window: 200 }, note: "[161b-T9] 可點時 ↗ 用正常字色" },

  // ==== 162c：自 tests/unit/test_frontend_lint.py／frontend_contracts／散落三檔 搬入（按批分子區段）====
  // ---- 162c-B01 起 ----
  // 162c: TestSettingsCleanupBypassGuard
  // units 1/3/5 與 gate 共覆蓋同一字面 → 只留 gate min=2（涵蓋 4+6；1/3/5 收據記共覆蓋）
  { file: 'web/static/js/pages/settings/state-ui.js', kind: 'required-string', pattern: 'window.location.href', count: 2, note: '[lint-guard 162c-test_dirty_check_discard_has_location_fallback] 使用者在沒有 __leavePage 的環境按「放棄修改並離開」→ 缺 location.href fallback 就按了沒反應、離不開設定頁 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/settings/state-ui.js', kind: 'structure-count', pattern: 'if (!window.__leavePage(this.pendingNavigationUrl)) return;', min: 2, note: '[lint-guard 162c-test_dirty_check_discard_gates_on_leave_page_return] 使用者按「放棄修改並離開」／「儲存並離開」而 cleanup 回報不可離開 → 缺 !__leavePage gate 仍照跳、請求被丟 (test_dirty_check_save_gates_on_leave_page_return) — 遷自 test_frontend_lint.py' },

  // 162c: TestShowcaseKeyboardGuard
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'e.preventDefault()', scope: /\/\/ 4\. Sample Gallery 開啟時的快捷鍵[\s\S]*?return;/, note: '[lint-guard 162c-test_sample_gallery_keyboard_has_prevent_default] 使用者在劇照瀏覽按方向鍵/Esc → 沒擋預設行為時背景頁面跟著捲動、Esc/方向鍵誤作用 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'e.preventDefault()', scope: /\/\/ 5\. Lightbox 開啟時的快捷鍵[\s\S]*?return;/, note: '[lint-guard 162c-test_lightbox_keyboard_has_prevent_default] 使用者在燈箱按方向鍵/Esc → 沒擋預設行為時背景跟著捲動、Esc/方向鍵誤作用 — 遷自 test_frontend_lint.py' },

  // 162c: TestShowcaseActressState
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', pattern: [
      'var _actresses = []',
      'var _filteredActresses = []',
      'showFavoriteActresses',
      '_persistedShowcase.showFavoriteActresses = this.showFavoriteActresses',
      '_persistedShowcase.actressSort = this.actressSort',
      '_persistedShowcase.actressOrder = this.actressOrder',
      'showFavoriteActresses === true',
      'state.actressSort',
      'state.actressOrder',
    ], stripLineComments: true, note: '[lint-guard 162c-TestShowcaseActressState.test_actress_js_contains] 使用者切到女優模式/排序後重新整理 → 缺 saveState 的 persist 寫入就回到預設、每次要重切；其餘為女優模式 state/method 識別字清單 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: [
      'actressCount',
      'filteredActressCount',
      'paginatedActresses',
      'actressSearch',
      'actressSort',
      'actressOrder',
      'actressLoading',
      'actressLightboxIndex',
      'currentLightboxActress',
      '_actressChipsExpanded',
      '_addActressName',
      '_addingActress',
      'toggleActressMode',
      'loadActresses',
      'applyActressFilterAndSort',
      'onActressSearchChange',
      'onActressSortChange',
      'toggleActressOrder',
      'openActressLightbox',
      'closeActressLightbox',
      'prevActressLightbox',
      'nextActressLightbox',
      '_setActressLightboxIndex',
      'actressCupValue',
    ], stripLineComments: true, note: '[lint-guard 162c-TestShowcaseActressState.test_actress_js_contains] 使用者切到女優模式/排序後重新整理 → 缺 saveState 的 persist 寫入就回到預設、每次要重切；其餘為女優模式 state/method 識別字清單 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: [
      '_videoChipsExpanded',
      'currentLightboxActress = null',
      '_videoChipsExpanded = false',
      'this.currentLightboxActress',
      'this.prevActressLightbox()',
      'this.nextActressLightbox()',
    ], note: '[lint-guard 162c-TestShowcaseActressState.test_actress_js_contains] 使用者切到女優模式/排序後重新整理 → 缺 saveState 的 persist 寫入就回到預設、每次要重切；其餘為女優模式 state/method 識別字清單 — 遷自 test_frontend_lint.py' },

  // 162c: TestActressLightboxSourceGuard
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: /actressLightboxSource\s*:\s*null/, note: '[lint-guard 162c-test_source_state_init_and_html] 使用者從女優牆開女優燈箱 → 相機鈕(找此女優作品)要出現；缺 state 初值/x-show 綁定則鈕消失或在 hero 燈箱誤出現 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "actressLightboxSource === 'grid'", note: '[lint-guard 162c-test_source_state_init_and_html] 使用者從女優牆開女優燈箱 → 相機鈕(找此女優作品)要出現；缺 state 初值/x-show 綁定則鈕消失或在 hero 燈箱誤出現 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: /this\.actressLightboxSource\s*=\s*['"]hero['"]/, scope: { anchor: /openHeroCardLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_source_set_in_open_methods] 使用者從 hero 卡開燈箱後再關閉 → 進入路徑 state 沒設 \'hero\'/沒在關閉時歸 null，相機鈕顯隱會錯 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: /this\.actressLightboxSource\s*=\s*null/, scope: { anchor: /closeLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_source_set_in_open_methods] 使用者從 hero 卡開燈箱後再關閉 → 進入路徑 state 沒設 \'hero\'/沒在關閉時歸 null，相機鈕顯隱會錯 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count', pattern: /this\.actressLightboxSource\s*=\s*['"]grid['"]/, min: 2, scope: { anchor: /openActressLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_open_actress_lightbox_sets_grid] 使用者在女優牆開女優燈箱、或切換上/下一位 → 少一處設 \'grid\' 則相機鈕在該路徑消失、無法跳去搜該女優作品 — 遷自 test_frontend_lint.py' },

  // 162c: TestShowcasePreciseMatchState
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', pattern: 'var _actressesLoaded', note: '[lint-guard 162c-TestShowcasePreciseMatchState.test_actress_js_contains] 使用者在影片搜尋框打女優名 → 英雄卡/愛心要出現、切模式要清掉；缺 stale guard/清除則殘留錯的卡或愛心 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: [
      '_isPreciseActressMatch',
      '_matchedActress',
      '_preciseMatchSource',
      '_favoriteHeartLoading',
      '_checkPreciseActressMatch',
      '_clearPreciseMatch',
      'capturedTerm',
      'addFavoriteFromSearch',
    ], stripLineComments: true, note: '[lint-guard 162c-TestShowcasePreciseMatchState.test_actress_js_contains] 使用者在影片搜尋框打女優名 → 英雄卡/愛心要出現、切模式要清掉；缺 stale guard/清除則殘留錯的卡或愛心 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', anyOf: true, pattern: ['_actressesLoaded = true', '_setActressesLoaded(true)'], stripLineComments: true, note: '[lint-guard 162c-TestShowcasePreciseMatchState.test_actress_js_contains] 使用者在影片搜尋框打女優名 → 英雄卡/愛心要出現、切模式要清掉；缺 stale guard/清除則殘留錯的卡或愛心 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: '_favoriteHeartLoading', scope: { anchor: /addFavoriteFromSearch/, window: 2000 }, note: '[lint-guard 162c-TestShowcasePreciseMatchState.test_actress_js_contains] 使用者在影片搜尋框打女優名 → 英雄卡/愛心要出現、切模式要清掉；缺 stale guard/清除則殘留錯的卡或愛心 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'addFavoriteFromSearch()', note: '[lint-guard 162c-test_actress_html_contains] 使用者在影片搜尋框搜出女優後按愛心 → 缺 addFavoriteFromSearch() 接線則加不了收藏 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '_isPreciseActressMatch', note: '[lint-guard 162c-test_actress_html_contains] 使用者在影片搜尋框搜出女優後按愛心 → 缺 addFavoriteFromSearch() 接線則加不了收藏 — 遷自 test_frontend_lint.py' },

  // 162c: TestLoadMoreButton
  { file: 'web/templates/search.html', kind: 'required-string', pattern: /(?<![\w:-])@click="gridLoadMore\(\)"/, note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "t('search.button.load_more')", note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "hasMoreResults && displayMode === 'grid'", note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: 'hasMoreResults', note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: "await this.loadMore('lightbox')", note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: 'async loadMore(trigger', note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: 'return { loadedCount', note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: 'async gridLoadMore()', note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'playAppendCascade', note: '[lint-guard 162c-test_html_and_js_contains] 使用者在搜尋結果按「載入更多」→ 按鈕要保持顯示且接上 loadMore；缺綁定則按了沒有後續結果 — 遷自 test_frontend_lint.py' },
  // ---- 162c-B01 迄 ----
  //
  //
  //
  // ---- 162c-B02 起 ----
  // 162c: TestShowcaseActressTemplate
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'toggleActressMode()', note: '[lint-guard 162c-TestShowcaseActressTemplate.test_showcase_html_contains] 使用者在女優牆點女優卡 → 缺 openActressLightbox(index) 接線則開不了燈箱 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'openActressLightbox(index)', note: '[lint-guard 162c-TestShowcaseActressTemplate.test_showcase_html_contains] 使用者在女優牆點女優卡 → 缺 openActressLightbox(index) 接線則開不了燈箱 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'paginatedActresses', note: '[lint-guard 162c-TestShowcaseActressTemplate.test_showcase_html_contains] 使用者在女優牆點女優卡 → 缺 openActressLightbox(index) 接線則開不了燈箱 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'actressLoading', note: '[lint-guard 162c-TestShowcaseActressTemplate.test_showcase_html_contains] 使用者在女優牆點女優卡 → 缺 openActressLightbox(index) 接線則開不了燈箱 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'actressCount === 0', note: '[lint-guard 162c-TestShowcaseActressTemplate.test_showcase_html_contains] 使用者在女優牆點女優卡 → 缺 openActressLightbox(index) 接線則開不了燈箱 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '!showFavoriteActresses', note: '[lint-guard 162c-TestShowcaseActressTemplate.test_showcase_html_contains] 使用者在女優牆點女優卡 → 缺 openActressLightbox(index) 接線則開不了燈箱 — 遷自 test_frontend_lint.py' },

  // 162c: TestShowcaseLightboxSentinel
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: ['lightboxIndex = -1', 'this.currentLightboxActress'], scope: { anchor: /openHeroCardLightbox\s*\(\s*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_showcase_lightbox_js_contains] 使用者在 hero 卡燈箱(index -1)按上一部 → 缺 sentinel 擋索引則看到錯內容/越界 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: ['lightboxIndex === -1', 'is_favorite'], scope: { anchor: /prevLightboxVideo\s*\(\s*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_showcase_lightbox_js_contains] 使用者在 hero 卡燈箱(index -1)按上一部 → 缺 sentinel 擋索引則看到錯內容/越界 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: ['lightboxIndex === -1', '_setLightboxIndex'], scope: { anchor: /nextLightboxVideo\s*\(\s*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_showcase_lightbox_js_contains] 使用者在 hero 卡燈箱(index -1)按上一部 → 缺 sentinel 擋索引則看到錯內容/越界 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'showFavoriteActresses', scope: { anchor: /\/\/ 5\. Lightbox/, window: 1000 }, note: '[lint-guard 162c-test_showcase_lightbox_js_contains] 使用者在 hero 卡燈箱(index -1)按上一部 → 缺 sentinel 擋索引則看到錯內容/越界 — 遷自 test_frontend_lint.py' },

  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'showFavoriteActresses', scope: /<button\b[^>]*openRemoveActressModal\(\)[^>]*>/, note: '[lint-guard 162c-TestShowcaseLightboxSentinel.test_showcase_html_contains] 使用者在影片模式(非女優模式)開燈箱 → 「移除女優」破壞性鈕不該露出；缺 showFavoriteActresses gate 則影片燈箱出現移除女優入口 — 遷自 test_frontend_lint.py' },

  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: ['lb-delete-btn', 'bi-trash', "t('showcase.video.delete')"], scope: /<div class="lb-details">(?:(?!<\/div>)[\s\S])*?(<button\b[^>]*openDeleteVideoModal\(\)[^>]*>[\s\S]*?<\/button>)/, note: '[lint-guard 162c-test_t7_delete_trash_button_in_lightbox_details_row] 使用者在影片燈箱找刪除鈕 → 垃圾桶鈕必須在 .lb-details 行末(綁 openDeleteVideoModal，含 icon/i18n)；漂走則找不到刪除鈕 — 遷自 test_frontend_lint.py' },

  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: ['showcase.video.delete_modal.title', 'confirmDeleteVideo()', 'cancelDeleteVideo()'], scope: /<dialog\b[^>]*deleteVideoModalOpen[^>]*>([\s\S]*?)<\/dialog>/, note: '[lint-guard 162c-test_t7_delete_modal_contract] 使用者按垃圾桶 → 刪除確認視窗必須有標題/確認/取消 handler；缺了則無法完成或放棄刪除 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'fluent-modal', scope: /<dialog\b[^>]*deleteVideoModalOpen[^>]*>/, note: '[lint-guard 162c-test_t7_delete_modal_contract] 使用者按垃圾桶 → 刪除確認視窗必須有標題/確認/取消 handler；缺了則無法完成或放棄刪除 — 遷自 test_frontend_lint.py' },

  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: /(?<![\w:-])x-trap\.inert="(?=[^"]*\blightboxOpen\b)(?=[^"]*\bdeleteVideoModalOpen\b)[^"]*"/, note: '[lint-guard 162c-test_t7_xtrap_releases_on_delete_modal] 使用者在燈箱按垃圾桶開刪除視窗 → 燈箱 x-trap 必須釋放給 modal；否則焦點被拉回燈箱、modal 按鈕按不到 — 遷自 test_frontend_lint.py' },

  // 162c: TestTutorialSkipPersistsGuard
  { file: 'web/static/js/components/tutorial.js', kind: 'forbidden-string', pattern: /complete\(\s*false\s*\)/, scope: /\bskip\s*\(\s*\)\s*\{([\s\S]*?)\}/, note: '[lint-guard 162c-test_skip_persists_and_shares_entry] 使用者按教學「跳過」→ 下次進 /scanner 又彈教學、必須重按(issue #63) — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/components/tutorial.js', kind: 'required-string', anyOf: true, pattern: [/complete\(\s*true\s*\)/, 'localStorage.setItem', '/api/tutorial-completed'], scope: /\bskip\s*\(\s*\)\s*\{([\s\S]*?)\}/, note: '[lint-guard 162c-test_skip_persists_and_shares_entry] 使用者按教學「跳過」→ 下次進 /scanner 又彈教學、必須重按(issue #63) — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/components/tutorial.js', kind: 'structure-count', pattern: 'this.skip()', min: 3, note: '[lint-guard 162c-test_skip_persists_and_shares_entry] 使用者按教學「跳過」→ 下次進 /scanner 又彈教學、必須重按(issue #63) — 遷自 test_frontend_lint.py' },

  // 162c: TestMissingEnrichConfirmGuard
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'required-string', pattern: 'missingConfirmModalOpen', count: 4, note: '[lint-guard 162c-test_js_has_missing_confirm_modal_open_state] 使用者按一鍵補完且筆數>500 → 缺確認視窗開關 state 就不會跳確認、直接開跑大批量補完 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'required-string', pattern: ['skipConfirm', '> 500', 'missingConfirmModalOpen'], scope: { anchor: /async\s+runMissingEnrich\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_js_run_missing_enrich_has_threshold_check] 使用者按一鍵補完且筆數>500 → runMissingEnrich 缺 >500 門檻檢查/觸發 modal 則不經確認直接補完數百筆 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'forbidden-string', pattern: ["localStorage.removeItem('avlist_enrich_pending')", 'localStorage.removeItem("avlist_enrich_pending")'], scope: { anchor: /resumeMissingEnrich\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_js_resume_missing_enrich_uses_skip_confirm] 使用者續跑中斷的補完 → resume 若清掉 localStorage 恢復點就丟進度、或未帶 skipConfirm 又重新彈確認 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/scanner/state-batch.js', kind: 'required-string', pattern: 'skipConfirm: true', scope: { anchor: /resumeMissingEnrich\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_js_resume_missing_enrich_uses_skip_confirm] 使用者續跑中斷的補完 → resume 若清掉 localStorage 恢復點就丟進度、或未帶 skipConfirm 又重新彈確認 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'missingConfirmModalOpen', note: '[lint-guard 162c-test_html_has_missing_confirm_modal] 使用者在>500 筆確認視窗 → 取消/確認鈕必須接 cancelLargeMissingEnrich/confirmLargeMissingEnrich；缺綁定則按鈕無反應、視窗關不掉 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'cancelLargeMissingEnrich', note: '[lint-guard 162c-test_html_has_missing_confirm_modal] 使用者在>500 筆確認視窗 → 取消/確認鈕必須接 cancelLargeMissingEnrich/confirmLargeMissingEnrich；缺綁定則按鈕無反應、視窗關不掉 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/scanner.html', kind: 'required-string', pattern: 'confirmLargeMissingEnrich', note: '[lint-guard 162c-test_html_has_missing_confirm_modal] 使用者在>500 筆確認視窗 → 取消/確認鈕必須接 cancelLargeMissingEnrich/confirmLargeMissingEnrich；缺綁定則按鈕無反應、視窗關不掉 — 遷自 test_frontend_lint.py' },
  // ---- 162c-B02 迄 ----
  //
  //
  //
  // ---- 162c-B03 起 ----
  // （162c-B03 專屬子區段：只在此兩行之間追加）
  // 162c: TestMissingEnrichConfirmGuard
  // W-1：判定表自承全檔正則弱於 scanner.stats 樹；以 scope anchor `"stats": {` + window
  // 鎖在 stats 區塊內（braceBalanced 不可用：stats 值含 `{count}` 等 placeholder）。
  { file: 'locales/zh_TW.json', kind: 'required-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: [
      /"missing_enrich_confirm_title"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_prefix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_middle"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_suffix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_cancel"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_confirm"\s*:\s*"[^"]+"/,
    ], note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/zh_CN.json', kind: 'required-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: [
      /"missing_enrich_confirm_title"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_prefix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_middle"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_suffix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_cancel"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_confirm"\s*:\s*"[^"]+"/,
    ], note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/ja.json', kind: 'required-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: [
      /"missing_enrich_confirm_title"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_prefix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_middle"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_suffix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_cancel"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_confirm"\s*:\s*"[^"]+"/,
    ], note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/en.json', kind: 'required-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: [
      /"missing_enrich_confirm_title"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_prefix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_middle"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_body_suffix"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_cancel"\s*:\s*"[^"]+"/,
      /"missing_enrich_confirm_confirm"\s*:\s*"[^"]+"/,
    ], note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/zh_TW.json', kind: 'forbidden-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: /"missing_enrich_confirm_[a-z_]+"\s*:\s*"[^"]*[<>]/, note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/zh_CN.json', kind: 'forbidden-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: /"missing_enrich_confirm_[a-z_]+"\s*:\s*"[^"]*[<>]/, note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/ja.json', kind: 'forbidden-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: /"missing_enrich_confirm_[a-z_]+"\s*:\s*"[^"]*[<>]/, note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  { file: 'locales/en.json', kind: 'forbidden-string', scope: { anchor: /"stats"\s*:\s*\{/, window: 5000 }, pattern: /"missing_enrich_confirm_[a-z_]+"\s*:\s*"[^"]*[<>]/, note: '[lint-guard 162c-test_all_locales_have_missing_enrich_confirm_keys] 四語系補完確認視窗文字缺鍵/含 HTML 標籤則視窗顯示原始鍵名或標籤字樣 — 遷自 test_frontend_lint.py' },
  // ---- 162c-B03 迄 ----
  //
  //
  //
  // ---- 162c-B04 起 ----
  // （162c-B04 專屬子區段：只在此兩行之間追加）

  // 162c: TestIMEGuard
  { file: 'web/templates/search.html', kind: 'required-string', pattern: ['isComposing', 'preventDefault()'], scope: /<input\b[^>]*(?<![\w:-])id="searchQuery"[^>]*@keydown\.enter(?:\.prevent)?="([^"]*)"/, note: '[lint-guard 162c-test_search_html_ime_guard] 使用者用注音/日文輸入法在搜尋框選字按 Enter → 缺 isComposing 守衛時選字被當成送出搜尋、送出半截字 — 遷自 test_frontend_lint.py' },

  // 162c: TestGhostFlyInFlightGuard
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: /typeof\s+window\.GhostFly\??\.?playActressToHeroCard\s*!==\s*['"]function['"]/, scope: { anchor: /(?:async\s+)?searchActressFilms\s*\([^)]*\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_search_actress_films_explicit_ghost_fly_availability_check] 使用者按相機鈕搜該女優作品而 GhostFly 載入缺失 → flag 永久為 true、兩顆相機鈕永遠 disabled 按不了 — 遷自 test_frontend_lint.py' },

  // 162c: TestShowcaseSwipeGuard
  { file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag', tagName: 'div', className: 'showcase-lightbox', required: [/(?:@|x-on:)touchstart\.passive="[^"]*_lbTouchStart/, /(?:@|x-on:)touchend\.passive="[^"]*_lbTouchEnd/], note: '[lint-guard 162c-TestShowcaseSwipeGuard.test_container_has_touch_bindings] 手機使用者在影片/女優燈箱左右滑 → 容器沒掛 touch 綁定就滑不動、無法換片 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: ['similarModeOpen', 'similarModeMobileOpen', 'removeActressModalOpen', '_pickerOpen', 'rescrapeOpen', 'deleteVideoModalOpen', 'sampleGalleryOpen', 'lightboxOpen'], scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-TestShowcaseSwipeGuard.test_lb_touch_end_intercept_chain] 手機使用者開著刪除/重刮/相似等視窗時橫滑 → 缺攔截短路則滑動會誤換燈箱背後的片 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: ['showFavoriteActresses', 'prevActressLightbox', 'nextActressLightbox', 'prevLightboxVideo', 'nextLightboxVideo'], scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-TestShowcaseSwipeGuard.test_lb_touch_end_branch_split] 手機使用者在女優模式 vs 影片模式滑動 → 缺分流則女優燈箱滑動換到影片 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: "import { detectSwipe } from '@/shared/swipe.js';", note: '[lint-guard 162c-TestShowcaseSwipeGuard.test_lb_touch_end_uses_detect_swipe_with_threshold] 手機使用者在燈箱滑動 → 沒呼叫 detectSwipe(或門檻非 50)則滑動不換片/太敏感 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: ['detectSwipe(', /detectSwipe\([^)]*,\s*50\s*(?:\/\*[^*]*\*\/\s*)?\)/], scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-TestShowcaseSwipeGuard.test_lb_touch_end_uses_detect_swipe_with_threshold] 手機使用者在燈箱滑動 → 沒呼叫 detectSwipe(或門檻非 50)則滑動不換片/太敏感 — 遷自 test_frontend_lint.py' },

  // 162c: TestSearchSwipeGuard
  { file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag', tagName: 'div', className: 'showcase-lightbox', required: [/(?:@|x-on:)touchstart\.passive="[^"]*_lbTouchStart/, /(?:@|x-on:)touchend\.passive="[^"]*_lbTouchEnd/], note: '[lint-guard 162c-TestSearchSwipeGuard.test_container_has_touch_bindings] 手機使用者在搜尋頁燈箱左右滑 → 容器沒掛 touch 綁定就滑不動、無法換片 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: ['rescrapeOpen', 'sampleGalleryOpen', 'lightboxOpen'], scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-TestSearchSwipeGuard.test_lb_touch_end_intercept_chain] 手機使用者在搜尋頁開著重刮/劇照視窗時橫滑 → 缺攔截短路則誤換燈箱背後的片 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: ['prevLightboxVideo', 'nextLightboxVideo'], scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-TestSearchSwipeGuard.test_lb_touch_end_direct_dispatch] 手機使用者在搜尋頁燈箱滑動 → 沒直呼 prev/nextLightboxVideo 則滑動不換片 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: "import { detectSwipe } from '@/shared/swipe.js';", note: '[lint-guard 162c-TestSearchSwipeGuard.test_lb_touch_end_uses_detect_swipe_with_threshold] 手機使用者在搜尋頁燈箱滑動 → 沒呼叫 detectSwipe(或門檻非 50)則滑動不換片/太敏感 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: ['detectSwipe(', /detectSwipe\([^)]*,\s*50\s*(?:\/\*[^*]*\*\/\s*)?\)/], scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-TestSearchSwipeGuard.test_lb_touch_end_uses_detect_swipe_with_threshold] 手機使用者在搜尋頁燈箱滑動 → 沒呼叫 detectSwipe(或門檻非 50)則滑動不換片/太敏感 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'forbidden-string', pattern: 'showFavoriteActresses', scope: { anchor: /_lbTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_lb_touch_end_no_actress_gate] 手機使用者在搜尋頁燈箱滑動 → 若把 showcase 的 showFavoriteActresses gate 複製進來，search 無此 state 會讓滑動靜默失效 — 遷自 test_frontend_lint.py' },

  // 162c: TestDetailSwipeGuard
  { file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag', tagName: 'div', className: 'av-card-full-cover-wrapper', required: [/(?:@|x-on:)touchstart\.passive="[^"]*_dtTouchStart/, /(?:@|x-on:)touchend\.passive="[^"]*_dtTouchEnd/], note: '[lint-guard 162c-TestDetailSwipeGuard.test_container_has_touch_bindings] 手機使用者在搜尋詳情頁橫滑封面海報 → 想切到上一部／下一部卻沒反應 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag', tagName: 'div', className: 'av-card-full', forbidden: [/(?:@|x-on:)touchstart\.passive/, /(?:@|x-on:)touchend\.passive/], note: '[lint-guard 162c-test_touch_bound_on_wrapper_not_full_card] 手機使用者在詳情卡的 metadata 區上下捲動 → 被當成橫滑而誤切到另一部 — 遷自 test_frontend_lint.py' },
  // W-1：sample-strip 的 x-show 屬性值含「>」；用屬性感知 tagPattern 取代 [^>]*>，使開標籤掃描不弱於舊 bs4
  { file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag', tagName: 'div', className: 'av-card-full-cover', forbidden: [/(?:@|x-on:)touchstart\.passive/, /(?:@|x-on:)touchend\.passive/], note: '[lint-guard 162c-test_touch_not_bound_on_cover_or_sample_strip] 手機使用者橫滑劇照縮圖列 → 被當成翻頁手勢而跳到另一部 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag', tagPattern: /<div\b(?=[^>]*\bclass="[^"]*(?<![\w-])sample-strip(?![\w-])[^"]*")(?:[^>"'`]|"[^"]*"|'[^']*'|`[^`]*`)*>/, forbidden: [/(?:@|x-on:)touchstart\.passive/, /(?:@|x-on:)touchend\.passive/], note: '[lint-guard 162c-test_touch_not_bound_on_cover_or_sample_strip] 手機使用者橫滑劇照縮圖列 → 被當成翻頁手勢而跳到另一部 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: ['rescrapeOpen', 'sampleGalleryOpen', 'displayMode'], scope: { anchor: /_dtTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_dt_touch_end_intercept_chain] 使用者開著重新刮削視窗或劇照圖庫時在封面上滑動 → 背景詳情被切到另一部 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: ['navigate(1)', 'navigate(-1)'], scope: { anchor: /_dtTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_dt_touch_end_direct_dispatch] 使用者在詳情頁封面左滑／右滑 → 沒有切到下一部／上一部 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: "import { detectSwipe } from '@/shared/swipe.js';", note: '[lint-guard 162c-test_dt_touch_end_uses_detect_swipe_with_threshold] 使用者在詳情頁封面滑動 → 手勢方向判斷不運作 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: ['detectSwipe(', /detectSwipe\([^)]*,\s*50\s*(?:\/\*[^*]*\*\/\s*)?\)/], scope: { anchor: /_dtTouchEnd\(e\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_dt_touch_end_uses_detect_swipe_with_threshold] 使用者在詳情頁封面滑動 → 手勢方向判斷不運作 — 遷自 test_frontend_lint.py' },

  // 162c: TestTranslateAll
  { file: 'web/templates/search.html', kind: 'required-string', pattern: ['translateAll()', "listMode === 'search'"], note: '[lint-guard 162c-test_translate_all_infra_contains] 使用者先載入過檔案清單、之後改做番號搜尋 → 搜尋結果頁的「翻譯全部」鈕不顯示或按了沒反應 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: ['translateState', "listMode === 'search'"], note: '[lint-guard 162c-test_translate_all_infra_contains] 使用者先載入過檔案清單、之後改做番號搜尋 → 搜尋結果頁的「翻譯全部」鈕不顯示或按了沒反應 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string', pattern: 'async translateAll', note: '[lint-guard 162c-test_translate_all_infra_contains] 使用者先載入過檔案清單、之後改做番號搜尋 → 搜尋結果頁的「翻譯全部」鈕不顯示或按了沒反應 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'forbidden-string', pattern: 'fileList.length === 0 && this.searchResults.length > 0', note: '[lint-guard 162c-test_translate_all_infra_contains] 使用者先載入過檔案清單、之後改做番號搜尋 → 搜尋結果頁的「翻譯全部」鈕不顯示或按了沒反應 — 遷自 test_frontend_lint.py' },

  // ---- 162c-B04 迄 ----
  //
  //
  //
  // ---- 162c-B05 起 ----
  // （162c-B05 專屬子區段：只在此兩行之間追加）

  // 162c: TestJellyfinFrontend
  // test_jellyfin_toggle_in_settings — forbidden dead bindings（整檔）×5
  { file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: [
      /(?<![\w:-])x-model="form\.jellyfinMode"/,
      /(?<![\w:-]):checked="form\.externalManager === 'jellyfin_emby'"/,
      /(?<![\w:-])@change="form\.externalManager = \$event\.target\.checked/,
      "'is-on': form.externalManager === 'jellyfin_emby'",
      /(?<![\w:-])@click="form\.externalManager = 'jellyfin_emby'"/,
    ],
    note: '[lint-guard 162c-test_jellyfin_toggle_in_settings] 使用者在設定頁選外部管理器（Jellyfin／Emby／Kodi）→ 點了沒切換、說明文字不跟著變、或切換時沒跳破壞性確認（segmented 綁定被改回舊直寫） — 遷自 test_frontend_lint.py' },
  // segmented 容器存在（整檔；頁面另有 header／batchbar 同 class，舊守衛亦只斷存在）
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])class="settings-sources-segmented"/,
    note: '[lint-guard 162c-test_jellyfin_toggle_in_settings] 使用者在設定頁選外部管理器（Jellyfin／Emby／Kodi）→ 點了沒切換、說明文字不跟著變、或切換時沒跳破壞性確認（segmented 綁定被改回舊直寫） — 遷自 test_frontend_lint.py' },
  // 四態 is-on + requestExternalManagerChange（scope＝外部管理器 row 內首個 segmented role=group 區塊）
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      "'is-on': form.externalManager === 'off'",
      "'is-on': form.externalManager === 'jellyfin'",
      "'is-on': form.externalManager === 'emby'",
      "'is-on': form.externalManager === 'kodi'",
      /(?<![\w:-])@click="requestExternalManagerChange\('off'\)"/,
      /(?<![\w:-])@click="requestExternalManagerChange\('jellyfin'\)"/,
      /(?<![\w:-])@click="requestExternalManagerChange\('emby'\)"/,
      /(?<![\w:-])@click="requestExternalManagerChange\('kodi'\)"/,
    ],
    scope: /settings-form-row--external-manager[\s\S]*?((?<![\w:-])class="settings-sources-segmented" role="group"[\s\S]*?<\/div>)/,
    note: '[lint-guard 162c-test_jellyfin_toggle_in_settings] 使用者在設定頁選外部管理器（Jellyfin／Emby／Kodi）→ 點了沒切換、說明文字不跟著變、或切換時沒跳破壞性確認（segmented 綁定被改回舊直寫） — 遷自 test_frontend_lint.py' },
  // 禁直寫 @click form.externalManager='…'（同 scope）
  { file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: [
      /(?<![\w:-])@click="form\.externalManager = 'off'"/,
      /(?<![\w:-])@click="form\.externalManager = 'jellyfin'"/,
      /(?<![\w:-])@click="form\.externalManager = 'emby'"/,
      /(?<![\w:-])@click="form\.externalManager = 'kodi'"/,
    ],
    scope: /settings-form-row--external-manager[\s\S]*?((?<![\w:-])class="settings-sources-segmented" role="group"[\s\S]*?<\/div>)/,
    note: '[lint-guard 162c-test_jellyfin_toggle_in_settings] 使用者在設定頁選外部管理器（Jellyfin／Emby／Kodi）→ 點了沒切換、說明文字不跟著變、或切換時沒跳破壞性確認（segmented 綁定被改回舊直寫） — 遷自 test_frontend_lint.py' },
  // 四態 hint x-show（整檔）
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])x-show="form\.externalManager === 'off'"/,
      /(?<![\w:-])x-show="form\.externalManager === 'jellyfin'"/,
      /(?<![\w:-])x-show="form\.externalManager === 'emby'"/,
      /(?<![\w:-])x-show="form\.externalManager === 'kodi'"/,
    ],
    note: '[lint-guard 162c-test_jellyfin_toggle_in_settings] 使用者在設定頁選外部管理器（Jellyfin／Emby／Kodi）→ 點了沒切換、說明文字不跟著變、或切換時沒跳破壞性確認（segmented 綁定被改回舊直寫） — 遷自 test_frontend_lint.py' },
  // i18n key 引用
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ['external_manager_off_hint', 'external_manager_emby_hint'],
    note: '[lint-guard 162c-test_jellyfin_toggle_in_settings] 使用者在設定頁選外部管理器（Jellyfin／Emby／Kodi）→ 點了沒切換、說明文字不跟著變、或切換時沒跳破壞性確認（segmented 綁定被改回舊直寫） — 遷自 test_frontend_lint.py' },

  // test_jellyfin_update_in_scanner — 整檔存在 runJellyfinImageUpdate（舊弱點：定義＋log 字串皆命中）
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: 'runJellyfinImageUpdate',
    note: '[lint-guard 162c-test_jellyfin_update_in_scanner] 使用者在掃描頁按「補齊 Jellyfin 圖片」→ 按鈕按了沒反應（runJellyfinImageUpdate 函式不見，scanner.html:371 仍呼叫它） — 遷自 test_frontend_lint.py' },

  // ---- 162c-B05 迄 ----
  //
  //
  //
  // ---- 162c-B06 起 ----
  // （162c-B06 專屬子區段：只在此兩行之間追加）
  // 162c: TestPathContract
  // test_no_raw_uri_strip — forbidden-string ×4（core/web/windows/tests .py；core 排除 path_utils.py）
  {
    file: { dir: 'core', ext: ['.py'], recursive: true, exclude: ['path_utils.py'] },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:\[8:\]|\[len\(['"]file:\/\/\/['"]\):])/m,
    note: '[lint-guard 162c-test_no_raw_uri_strip] 使用者在 Windows／WSL 加入片庫資料夾 → 程式手動用 [8:] 砍 file:/// 前綴，遇 UNC／WSL 路徑砍錯 → 片庫路徑對不上、影片找不到或打不開 — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'web', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:\[8:\]|\[len\(['"]file:\/\/\/['"]\):])/m,
    note: '[lint-guard 162c-test_no_raw_uri_strip] 使用者在 Windows／WSL 加入片庫資料夾 → 程式手動用 [8:] 砍 file:/// 前綴，遇 UNC／WSL 路徑砍錯 → 片庫路徑對不上、影片找不到或打不開 — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'windows', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:\[8:\]|\[len\(['"]file:\/\/\/['"]\):])/m,
    note: '[lint-guard 162c-test_no_raw_uri_strip] 使用者在 Windows／WSL 加入片庫資料夾 → 程式手動用 [8:] 砍 file:/// 前綴，遇 UNC／WSL 路徑砍錯 → 片庫路徑對不上、影片找不到或打不開 — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'tests', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:\[8:\]|\[len\(['"]file:\/\/\/['"]\):])/m,
    note: '[lint-guard 162c-test_no_raw_uri_strip] 使用者在 Windows／WSL 加入片庫資料夾 → 程式手動用 [8:] 砍 file:/// 前綴，遇 UNC／WSL 路徑砍錯 → 片庫路徑對不上、影片找不到或打不開 — 遷自 test_frontend_lint.py',
  },
  // test_no_manual_uri_construct — forbidden-string ×4
  {
    file: { dir: 'core', ext: ['.py'], recursive: true, exclude: ['path_utils.py'] },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*f["']file:\/\/\//m,
    note: '[lint-guard 162c-test_no_manual_uri_construct] 使用者的影片路徑被程式手組成 f"file:///…" → 斜線／編碼格式與 to_file_uri 不一致 → 同一部片在 DB 裡有兩種 URI，播放或比對失敗 — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'web', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*f["']file:\/\/\//m,
    note: '[lint-guard 162c-test_no_manual_uri_construct] 使用者的影片路徑被程式手組成 f"file:///…" → 斜線／編碼格式與 to_file_uri 不一致 → 同一部片在 DB 裡有兩種 URI，播放或比對失敗 — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'windows', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*f["']file:\/\/\//m,
    note: '[lint-guard 162c-test_no_manual_uri_construct] 使用者的影片路徑被程式手組成 f"file:///…" → 斜線／編碼格式與 to_file_uri 不一致 → 同一部片在 DB 裡有兩種 URI，播放或比對失敗 — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'tests', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*f["']file:\/\/\//m,
    note: '[lint-guard 162c-test_no_manual_uri_construct] 使用者的影片路徑被程式手組成 f"file:///…" → 斜線／編碼格式與 to_file_uri 不一致 → 同一部片在 DB 裡有兩種 URI，播放或比對失敗 — 遷自 test_frontend_lint.py',
  },
  // test_no_shadow_path_helpers — forbidden-string ×4
  {
    file: { dir: 'core', ext: ['.py'], recursive: true, exclude: ['path_utils.py'] },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:def wsl_to_windows_path|def to_file_uri)/m,
    note: '[lint-guard 162c-test_no_shadow_path_helpers] 有人另寫一份 wsl_to_windows_path／to_file_uri 影子實作 → 兩份轉換規則日後分岔 → 同一路徑在不同頁面轉出不同結果（開資料夾、播放失敗） — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'web', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:def wsl_to_windows_path|def to_file_uri)/m,
    note: '[lint-guard 162c-test_no_shadow_path_helpers] 有人另寫一份 wsl_to_windows_path／to_file_uri 影子實作 → 兩份轉換規則日後分岔 → 同一路徑在不同頁面轉出不同結果（開資料夾、播放失敗） — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'windows', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:def wsl_to_windows_path|def to_file_uri)/m,
    note: '[lint-guard 162c-test_no_shadow_path_helpers] 有人另寫一份 wsl_to_windows_path／to_file_uri 影子實作 → 兩份轉換規則日後分岔 → 同一路徑在不同頁面轉出不同結果（開資料夾、播放失敗） — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'tests', ext: ['.py'], recursive: true },
    kind: 'forbidden-string',
    pattern: /^(?![^\n]*# path-contract-ok)[^\n]*(?:def wsl_to_windows_path|def to_file_uri)/m,
    note: '[lint-guard 162c-test_no_shadow_path_helpers] 有人另寫一份 wsl_to_windows_path／to_file_uri 影子實作 → 兩份轉換規則日後分岔 → 同一路徑在不同頁面轉出不同結果（開資料夾、播放失敗） — 遷自 test_frontend_lint.py',
  },
  // test_path_to_display_js_no_optional_slash — forbidden-string ×1（現行唯一 path-utils.js）
  {
    file: 'web/static/js/components/path-utils.js',
    kind: 'forbidden-string',
    pattern: /\/\?/,
    note: '[lint-guard 162c-test_path_to_display_js_no_optional_slash] 使用者在介面看到的（或複製出來的）路徑少了開頭斜線 → 貼到檔案總管／終端機打不開（pathToDisplay 的 /? regex 吃掉前導斜線） — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B06 迄 ----
  //
  //
  //
  // ---- 162c-B07 起 ----
  // （162c-B07 專屬子區段：只在此兩行之間追加）
  // 162c: TestHelpPage
  { file: 'web/templates/help.html', kind: 'required-string', pattern: ['helpPage', 'checkUpdate', 'hero-terminal', 'help.hero.ai_instruction'], note: '[lint-guard 162c-test_help_html_contains] 使用者開說明頁 → 「檢查更新」鈕或 AI 終端機卡不出現／說明頁整頁不初始化（helpPage 掛載點、hero-terminal 或 help.js script 被改壞，或 help.js 被載入兩次） — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/help.html', kind: 'structure-count', pattern: /<script[^>]*help\.js[^>]*>/, count: 1, note: '[lint-guard 162c-test_help_html_contains] 使用者開說明頁 → 「檢查更新」鈕或 AI 終端機卡不出現／說明頁整頁不初始化（helpPage 掛載點、hero-terminal 或 help.js script 被改壞，或 help.js 被載入兩次） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/help.js', kind: 'required-string', pattern: ['copyCurlCommand', 'execCommand'], note: '[lint-guard 162c-test_help_js_contains] 使用者在說明頁按「複製 curl 指令」鈕 → 沒有複製到東西（copyCurlCommand 或 execCommand 後備路徑被改壞） — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/help.html', kind: 'tag-scan', mode: 'class-tag', tagPattern: /<[a-z]+\b(?=[^>]*(?<![\w:-])class="[^"]*(?<![\w-])hero-terminal(?![\w-])[^"]*")[^>]*>/, required: ['data-capabilities-base'], note: '[lint-guard 162c-test_help_hero_terminal_has_capabilities_base] 使用者在本機開說明頁、複製 curl 給別台裝置的 AI 用 → 複製出 127.0.0.1／localhost 網址，別台連不到（server-aware base_url 來源 data-capabilities-base 被移除） — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/help.html', kind: 'tag-scan', mode: 'class-tag', tagName: 'button', className: 'terminal-copy-btn', required: [/(?<![\w-])(?::)?aria-label="[^"]*help\.hero\.copy_curl/], note: '[lint-guard 162c-test_help_copy_button_has_aria_label] 使用螢幕閱讀器的使用者在說明頁 → curl 複製鈕只有圖示、沒有可讀名稱，唸不出它是做什麼的（aria-label 被移除或改引用別 key） — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/help.html', kind: 'required-string', pattern: 'bi-clipboard', scope: /<button[^>]*terminal-copy-btn[\s\S]*?<\/button>/, note: '[lint-guard 162c-test_help_copy_button_has_aria_label] 使用螢幕閱讀器的使用者在說明頁 → curl 複製鈕只有圖示、沒有可讀名稱，唸不出它是做什麼的（aria-label 被移除或改引用別 key） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/help.js', kind: 'required-string', pattern: ['capabilitiesBase', '${base}'], note: '[lint-guard 162c-test_help_js_copy_uses_capabilities_base_dataset] 使用者在本機開說明頁複製 curl → 複製出 window.location.origin（localhost）而不是 server 給的對外網址（help.js 不再讀 data-capabilities-base） — 遷自 test_frontend_lint.py' },

  // 162c: TestStreamState
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: ['streamSlots', 'streamComplete', 'isStreaming'], stripLineComments: true, note: '[lint-guard 162c-test_base_js_core_stream_state] 使用者搜尋番號 → 骨架格／漸進結果出不來或頁面報錯（base.js 少宣告 streamSlots／streamComplete／isStreaming，Alpine 表達式取不到） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: ['streamBuffer', 'streamBurstTimer', 'streamBurstedSlots', 'stagingVisible'], stripLineComments: true, note: '[lint-guard 162c-test_base_js_staging_buffer_state] 使用者搜尋番號 → 串流來的結果進不了暫存／分批顯示，結果卡片不出現（base.js 少宣告 streamBuffer 等批次狀態） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: ['this.streamBuffer.push', 'streamBurstTimer', 'stagingCover', 'stagingNumber'], stripLineComments: true, note: '[lint-guard 162c-test_result_item_uses_stream_buffer] 使用者搜尋番號 → 串流結果沒走分批暫存而一筆筆直接塞進結果列，卡片一次次整列重畫、可能卡頓或順序亂（result-item handler 不再推入 streamBuffer） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: ["data.type === 'seed'", "data.type === 'result-item'", "data.type === 'result-complete'"], note: '[lint-guard 162c-test_search_flow_handles_seed_event] 使用者搜尋番號 → 串流事件不被處理，骨架格不出現、結果永遠載入中（seed／result-item／result-complete 任一 handler 被改掉） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', pattern: 'this.streamComplete', note: '[lint-guard 162c-test_search_flow_has_stream_guard] 使用者搜尋番號 → 串流已逐筆顯示好的結果，最後一個總結事件把整份結果列覆蓋掉，畫面上已看的結果閃一下或被換成別筆（漸進路徑 result 缺 streamComplete 守衛） — 遷自 test_frontend_lint.py' },
  // ---- 162c-B07 迄 ----
  //
  //
  //
  // ---- 162c-B08 起 ----
  // （162c-B08 專屬子區段：只在此兩行之間追加）

  // 162c: TestAnimationHookup
  { file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'prefersReducedMotion', note: '[lint-guard 162c-test_animations_js_has_reduced_motion_guard] 開啟系統「減少動態」的使用者進搜尋頁 → 仍被播放進場／轉場動畫（減少動態偏好被無視） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'av-card-full-cover', scope: { anchor: /playSlideIn: function/, window: 800 }, note: '[lint-guard 162c-test_play_slide_in_kills_child_tweens] 使用者在詳情頁連續切上一部／下一部 → 子元素殘留上一輪動畫，封面或資訊區閃爍、停在半透明位置（playSlideIn 沒一併打斷封面／資訊的子 tween） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/animations.js', kind: 'required-string', pattern: 'av-card-full-info', scope: { anchor: /playSlideIn: function/, window: 800 }, note: '[lint-guard 162c-test_play_slide_in_kills_child_tweens] 使用者在詳情頁連續切上一部／下一部 → 子元素殘留上一輪動畫，封面或資訊區閃爍、停在半透明位置（playSlideIn 沒一併打斷封面／資訊的子 tween） — 遷自 test_frontend_lint.py' },

  // 162c: TestFailedSlotC30Guard
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /navigate\s*\(/, window: 500 }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  // CD-162c-19：prev/nextLightboxVideo、canGoPrev/Next 的 window 切在真 ._failed 之前（只吃到註解）→ braceBalanced + stripLineComments
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /prevLightboxVideo\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /nextLightboxVideo\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /navIndicatorText\s*\(/, window: 500 }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /canGoPrev\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /canGoNext\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /showNavigation\s*\(/, window: 300 }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string', pattern: '_failed', scope: { anchor: /fileCountText\s*\(/, window: 500 }, stripLineComments: true, note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/templates/search.html', kind: 'required-string', pattern: ['hasVisiblePrev()', 'hasVisibleNext()'], note: '[lint-guard 162c-test_failed_slot_method_bodies_contain_failed] 使用者搜尋番號、其中某幾筆抓取失敗（空白項）→ 按上一部／下一部會停在空白項、導航箭頭與「第 N／共 M 筆」計數把失敗項也算進去 — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string', anyOf: true, pattern: ['currentResult', 'this.searchResults[this.currentIndex]'], scope: /([\s\S]{0,200}firstValid[\s\S]{0,200})/, note: '[lint-guard 162c-test_repoint_is_conditional] 使用者搜尋多筆番號、串流中途已自行點選某筆有效結果 → 串流結束時被無條件拉回第一筆（或原停在失敗空白項卻沒被導向有效項），看到錯的那一筆 — 遷自 test_frontend_lint.py' },

  // 162c: TestLightboxModeNormalization
  { file: 'web/static/js/pages/search/state/persistence.js', kind: 'required-string', pattern: ['lightboxOpen', '= false', 'actressProfile', 'lightboxIndex'], scope: { anchor: /restoreState\s*\(\s*\)/, window: 3000 }, note: '[lint-guard 162c-test_lightbox_mode_normalization_contains] 使用者在女優（hero）搜尋頁重新整理 → 還原後燈箱殘留開著，或打開女優燈箱時沒有女優資料（空白燈箱、關不掉或內容錯） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string', pattern: /if\s*\(\s*!this\.actressProfile\s*\)\s*return/, scope: { anchor: /openActressLightbox\s*\(\s*\)/, window: 300 }, note: '[lint-guard 162c-test_lightbox_mode_normalization_contains] 使用者在女優（hero）搜尋頁重新整理 → 還原後燈箱殘留開著，或打開女優燈箱時沒有女優資料（空白燈箱、關不掉或內容錯） — 遷自 test_frontend_lint.py' },

  // 162c: TestShowcaseAnimationsGuard
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'structure-count', pattern: 'gsap.getById(', count: 2, note: '[lint-guard 162c-test_core_js_no_direct_gsap_getById] showcase core 不得在 _killLightboxTimelines 之外直接呼叫 gsap.getById（整檔 exact 2＝函式體內兩處） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'structure-count', pattern: 'gsap.getById(', count: 2, scope: { anchor: /export function _killLightboxTimelines\s*\(options\)\s*\{/, braceBalanced: true }, note: '[lint-guard 162c-test_core_js_no_direct_gsap_getById] showcase core 不得在 _killLightboxTimelines 之外直接呼叫 gsap.getById（函式體內 exact 2） — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string', pattern: 'gsap.getById(', note: '[lint-guard 162c-test_core_js_no_direct_gsap_getById] showcase state-videos.js 不得直接呼叫 gsap.getById( — 遷自 test_frontend_lint.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'gsap.getById(', note: '[lint-guard 162c-test_core_js_no_direct_gsap_getById] showcase state-lightbox.js 不得直接呼叫 gsap.getById( — 遷自 test_frontend_lint.py' },

  // ---- 162c-B08 迄 ----
  //
  //
  //
  // ---- 162c-B09 起 ----
  // 162c: TestGridPerPageGuard
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /['"]grid['"]/,
    scope: { anchor: /updatePagination\s*\(\s*\)\s*\{/, window: 800 },
    note: '[lint-guard 162c-test_grid_per_page_method_bodies_contain_guard] 格狀每頁筆數保護：updatePagination 窗內須含 grid — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /perPage\s*=\s*120/,
    scope: { anchor: /updatePagination\s*\(\s*\)\s*\{/, window: 800 },
    note: '[lint-guard 162c-test_grid_per_page_method_bodies_contain_guard] 格狀每頁筆數保護：updatePagination 窗內須含 perPage = 120 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: /['"]grid['"]/,
    scope: { anchor: /restoreState\s*\(\s*\)\s*\{/, window: 2500 },
    note: '[lint-guard 162c-test_grid_per_page_method_bodies_contain_guard] 格狀每頁筆數保護：restoreState 窗內須含 grid — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: /perPage\s*=\s*120/,
    scope: { anchor: /restoreState\s*\(\s*\)\s*\{/, window: 2500 },
    note: '[lint-guard 162c-test_grid_per_page_method_bodies_contain_guard] 格狀每頁筆數保護：restoreState 窗內須含 perPage = 120 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /['"]grid['"]/,
    scope: { anchor: /switchMode\s*\(\s*m\s*\)\s*\{/, window: 600 },
    note: '[lint-guard 162c-test_grid_per_page_method_bodies_contain_guard] 格狀每頁筆數保護：switchMode 窗內須含 grid — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /perPage\s*=\s*120/,
    scope: { anchor: /switchMode\s*\(\s*m\s*\)\s*\{/, window: 600 },
    note: '[lint-guard 162c-test_grid_per_page_method_bodies_contain_guard] 格狀每頁筆數保護：switchMode 窗內須含 perPage = 120 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: /items_per_page\s*\?\?\s*\d+/,
    stripLineComments: true,
    note: '[lint-guard 162c-test_guard5_items_per_page_uses_nullish_coalescing] items_per_page 預設須用 ?? 保留 0（showcase） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: /items_per_page\s*\?\?\s*\d+/,
    stripLineComments: true,
    note: '[lint-guard 162c-test_guard5_items_per_page_uses_nullish_coalescing] items_per_page 預設須用 ?? 保留 0（settings） — 遷自 test_frontend_lint.py',
  },

  // 162c: TestScannerDeleteAliasGroupNoNativeConfirm
  {
    file: 'web/static/js/pages/scanner/state-alias.js', kind: 'required-string',
    pattern: ['openDeleteAliasGroupModal', 'confirmDeleteAliasGroup', 'cancelDeleteAliasGroupModal'],
    stripLineComments: true,
    note: '[lint-guard 162c-test_scanner_has_delete_alias_group_modal_methods] 掃描頁刪除別名組三個 modal method 須存在 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: 'deleteAliasGroupModalOpen && cancelDeleteAliasGroupModal',
    note: '[lint-guard 162c-test_scanner_html_escape_ladder_includes_delete_alias_group] scanner.html Esc 階梯須串接 deleteAliasGroupModal cancel — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSampleGalleryTemplateGuard
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: ['sampleGalleryOpen', 'sampleGalleryImages', 'sampleGalleryIndex'],
    note: '[lint-guard 162c-test_sample_gallery_template_html_contains] base.html 須含 sampleGallery* 預設 state — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: ['sampleGalleryOpen', 'sampleGalleryImages', 'sampleGalleryIndex', 'lb-header'],
    note: '[lint-guard 162c-test_sample_gallery_template_html_contains] search.html 須含 sampleGallery* state 與 lb-header — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: [/(?<![\w:-])class="sample-lightbox"/, 'lb-meta-extra'],
    note: '[lint-guard 162c-test_sample_gallery_template_html_contains] search.html 不得殘留舊 sample-lightbox／lb-meta-extra — 遷自 test_frontend_lint.py',
  },
  {
    file: { dir: 'web/templates', ext: ['.html'], recursive: true }, kind: 'forbidden-string',
    pattern: /sampleLightboxOpen|sampleLightboxIndex/,
    note: '[lint-guard 162c-test_sample_gallery_template_structure] 全模板不得殘留舊 sampleLightbox* state — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'order',
    items: [
      { pattern: 'x-data="searchPage"' },
      { pattern: /(?<![\w:-])class="sample-gallery"/ },
    ],
    note: '[lint-guard 162c-test_sample_gallery_template_structure] .sample-gallery 須在 searchPage scope 之後 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'sg-open-btn',
    scope: { anchor: /<div class="lb-header">/, window: 500 },
    note: '[lint-guard 162c-test_sample_gallery_template_structure] sg-open-btn 須在 lb-header 窗內 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestShowcaseSampleGalleryGuard
  {
    file: 'web/static/js/pages/showcase/state-lightbox-samples.js', kind: 'required-string',
    pattern: [
      'sampleGalleryOpen', 'sampleGalleryImages', 'sampleGalleryIndex',
      'openSampleGallery', 'closeSampleGallery', 'prevSampleGallery',
      'nextSampleGallery', 'jumpSampleGallery',
    ],
    note: '[lint-guard 162c-test_showcase_sample_gallery_js_contains] showcase samples state／methods 須齊全 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string',
    pattern: ['playSampleGallerySwitch', 'killTweensOf', 'gsap-animating', 'clearProps'],
    stripLineComments: true, note: '[lint-guard 162c-test_showcase_sample_gallery_js_contains] animations.js 須含 playSampleGallerySwitch 完整實作字面 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'order',
    items: [
      { pattern: 'x-data="showcase"' },
      { pattern: 'sample-gallery' },
    ],
    note: '[lint-guard 162c-test_showcase_sample_gallery_html_structure] .sample-gallery 須在 showcase scope 之後 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      'sg-open-btn',
      'openSampleGallery(',
      'lb-header',
    ],
    note: '[lint-guard 162c-test_showcase_sample_gallery_html_structure] showcase 劇照集 bindings／lb-header／縮圖高亮須存在 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'sampleGalleryOpen',
    scope: { anchor: /<div class="sample-gallery"/, window: 600 },
    note: '[lint-guard 162c-test_showcase_sample_gallery_html_structure] .sample-gallery 附近須綁 sampleGalleryOpen — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: 'lb-meta-extra',
    note: '[lint-guard 162c-test_showcase_sample_gallery_html_structure] showcase.html 不得含 lb-meta-extra — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'sg-open-btn',
    scope: { anchor: /<div class="lb-header">/, window: 5000 },
    note: '[lint-guard 162c-test_showcase_sample_gallery_html_structure] sg-open-btn 須在 lb-header 窗內（FIX6：窗由 1800 放寬到 5000，避免按鈕前合法加標記/註解誤報） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w-])sg-thumb-active(?![\w-])[^\n]{0,80}sampleGalleryIndex|sampleGalleryIndex[^\n]{0,80}(?<![\w-])sg-thumb-active(?![\w-])/,
    note: '[lint-guard 162c-test_showcase_sample_gallery_html_structure] 劇照縮圖高亮須綁 sg-thumb-active 與 sampleGalleryIndex（FIX6：放寬運算元順序／=== 與 ==） — 遷自 test_frontend_lint.py',
  },

  // 162c: TestScannerMissingPillGuard
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: ['missingPillVisible', 'resumePillVisible'],
    note: '[lint-guard 162c-test_scanner_contains] scanner.html 須含 missing／resume pill 可見綁定 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-batch.js', kind: 'required-string',
    pattern: ['missingPillVisible', 'missingItems', 'resumePillVisible', 'runMissingEnrich', 'checkMissing'],
    stripLineComments: true, note: '[lint-guard 162c-test_scanner_contains] state-batch.js 須含 missing pill 狀態與方法 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: ['enriching', 'missingPillVisible'],
    note: '[lint-guard 162c-test_scanner_contains] state-scan.js 須含 enriching／missingPillVisible — 遷自 test_frontend_lint.py',
  },

  // 162c: TestRescrapeVersionStateGuard
  {
    file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'required-string',
    pattern: /_commitSearchResults\s*\(\s*payload\s*\)\s*\{/,
    stripLineComments: true,
    note: '[lint-guard 162c-test_commit_search_results_helper_exists] advanced-picker.js 須有 _commitSearchResults(payload) { 定義 — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B09 迄 ----
  //
  //
  //
  // ---- 162c-B10 起 ----
  // （162c-B10 專屬子區段：只在此兩行之間追加）
  // 162c: TestRescrapeVersionStateGuard
  {
    file: 'web/static/js/pages/search/state/advanced-picker.js', kind: 'required-string',
    pattern: 'this._commitSearchResults(',
    scope: { anchor: /async\s+advancedSearch\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_advanced_search_delegates_to_helper] 進階搜尋成功須委派 _commitSearchResults — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: ['rescrapeCandidates: []', 'rescrapeVersionIdx: 0'],
    stripLineComments: true,
    note: '[lint-guard 162c-test_candidates_state_keys_present] 重刮多版本狀態鍵須平鋪宣告 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: ['rescrapeHasVersions', 'rescrapeVersionGo'],
    stripLineComments: true,
    note: '[lint-guard 162c-test_version_methods_present] 重刮多版本切換方法須存在 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'manual_only',
    scope: { anchor: /rescrapeEntryPoint\s*===\s*['"]search['"]/, window: 400 },
    stripLineComments: true, note: '[lint-guard 162c-test_search_javlib_does_not_early_return_advancedSearch] search 入口 early return 須依 manual_only 分流 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /rescrapeStep\s*=\s*['"]preview['"]/,
    // 判定表 if-form scope；尾加 \s*\)\s*\{ 釘在 :294 裸 switch-source){（排除 :258 auto short-circuit），
    // 使 switch-source anchor 改名／:297 分叉破壞皆紅，不落到 :348 showcase。
    scope: /rescrapeEntryPoint\s*===\s*['"]switch-source['"]\s*\)\s*\{[\s\S]*?if\s*\(\s*data\.candidates\s*&&\s*data\.candidates\.length\s*>\s*1\s*\)([\s\S]{0,900})/,
    note: '[lint-guard 162c-test_switch_source_takes_candidates_first] switch-source 多版本 if 分叉須進 preview（test_switch_source_multiversion_enters_preview） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /t\.arr\s*\[\s*t\.idx\s*\]\s*=[^=]/,
    scope: /rescrapeConfirm\s*\(\s*\)[\s\S]*?rescrapeEntryPoint\s*===\s*['"]switch-source['"]([\s\S]{0,1100})/,
    note: '[lint-guard 162c-test_switch_source_confirm_branch_present] rescrapeConfirm switch-source 須 in-place 賦值 t.arr[t.idx]= — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string',
    pattern: '_commitSearchResults',
    scope: /rescrapeConfirm\s*\(\s*\)[\s\S]*?rescrapeEntryPoint\s*===\s*['"]switch-source['"]([\s\S]{0,1100})/,
    note: '[lint-guard 162c-test_switch_source_confirm_branch_present] rescrapeConfirm switch-source 不得呼叫 _commitSearchResults — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /detail_url\s*:\s*this\.rescrapePreview\?\.url/,
    scope: { anchor: /async\s+rescrapeConfirm\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_confirm_lightbox_detail_url_from_url_field] rescrapeConfirm detail_url 須取 rescrapePreview.url — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /_commitSearchResults\s*\??\.?\s*\(/,
    scope: { anchor: /async\s+rescrapeConfirm\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_confirm_search_calls_commit_helper] rescrapeConfirm search 分支須呼叫 _commitSearchResults — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'rescrapeCandidates',
    scope: { anchor: /closeRescrape\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_close_rescrape_resets_candidates] closeRescrape 須 reset rescrapeCandidates — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'rescrapeCandidates',
    scope: { anchor: /rescrapeBackToPick\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_back_to_pick_resets_candidates] rescrapeBackToPick 須 reset rescrapeCandidates — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /rescrapeStep\s*=\s*['"]preview['"]/,
    scope: /else\s+if\s*\(\s*data\s*&&\s*data\.success\s*\)\s*\{([\s\S]*?)this\.rescrapeNotFound\s*=\s*true/,
    note: '[lint-guard 162c-test_javlib_single_version_search_falls_through_to_preview] data.success 單版本須進 preview — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string',
    pattern: /_commitSearchResults\s*\??\.?\s*\(/,
    scope: /else\s+if\s*\(\s*data\s*&&\s*data\.success\s*\)\s*\{([\s\S]*?)this\.rescrapeNotFound\s*=\s*true/,
    note: '[lint-guard 162c-test_javlib_single_version_search_falls_through_to_preview] data.success 單版本不得呼叫 _commitSearchResults — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string',
    pattern: /\bcloseRescrape\s*\(/,
    scope: /else\s+if\s*\(\s*data\s*&&\s*data\.success\s*\)\s*\{([\s\S]*?)this\.rescrapeNotFound\s*=\s*true/,
    note: '[lint-guard 162c-test_javlib_single_version_search_falls_through_to_preview] data.success 單版本不得呼叫 closeRescrape — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /\bthis\.currentQuery\s*=/,
    scope: /rescrapeConfirm\b[\s\S]*?rescrapeEntryPoint\s*===\s*['"]search['"]([\s\S]*?)_commitSearchResults/,
    note: '[lint-guard 162c-test_javlib_confirm_search_syncs_current_query] rescrapeConfirm search 採用前須同步 currentQuery — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSettingsQuickToggleGuard
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-model="form\.downloadSampleImages"/,
    scope: /(?<![\w:-])class="settings-quick-toggle-row"([\s\S]*?)(?<![\w:-])id="sec-search"/,
    note: '[lint-guard 162c-test_download_sample_images_in_quick_toggle_row] 下載劇照開關須在 quick-toggle 列內 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: [
      /(?<![\w:-])x-model="form\.advancedSearchEnabled"/,
      /(?<![\w:-])id="advancedSearchToggle"/,
    ],
    note: '[lint-guard 162c-test_advanced_search_toggle_removed_from_quick_toggle_row] 進階搜尋 toggle 已退役不得殘留 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-model="form\.thumbnailCacheEnabled"/,
    scope: /(?<![\w:-])class="settings-quick-toggle-row"([\s\S]*?)(?<![\w:-])id="sec-search"/,
    note: '[lint-guard 162c-test_thumbnail_cache_enabled_in_quick_toggle_row] 縮圖快取開關須在 quick-toggle 列內 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ['x-data="helpPopover"', /(?<![\w:-])class="help-popover"/],
    scope: /(<div class="settings-form-group popover-anchor"(?:(?!<div class="settings-form-group popover-anchor")[\s\S])*?(?<![\w:-])x-model="form\.thumbnailCacheEnabled"(?:(?!<div class="settings-form-group popover-anchor"|(?<![\w:-])id="sec-search")[\s\S])*)/,
    note: '[lint-guard 162c-test_thumbnail_cache_has_help_popover_state] 縮圖快取 wrapper 須自帶 helpPopover — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /<input\b(?=[^>]*(?<![\w:-])@change="onThumbCacheToggleChange\(\)")(?=[^>]*(?<![\w:-])x-model="form\.thumbnailCacheEnabled")[^>]*>/,
    scope: /(?<![\w:-])class="settings-quick-toggle-row"([\s\S]*?)(?<![\w:-])id="sec-search"/,
    note: '[lint-guard 162c-test_thumbnail_cache_toggle_has_change_interceptor] 縮圖快取 toggle 同 input 須綁 @change=onThumbCacheToggleChange — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      'settings.thumbnail_cache.disable_modal.title',
      'confirmThumbCacheDisable()',
      'cancelThumbCacheDisable()',
    ],
    scope: /<dialog\b[^>]*thumbCacheDisableConfirmOpen[^>]*>([\s\S]*?)<\/dialog>/,
    note: '[lint-guard 162c-test_thumb_cache_disable_modal_contract] disable modal 須含 title／confirm／cancel — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'fluent-modal',
    scope: /(<dialog\b[^>]*thumbCacheDisableConfirmOpen[^>]*>)/,
    note: '[lint-guard 162c-test_thumb_cache_disable_modal_contract] disable modal 開標籤須含 fluent-modal — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/settings/state-ui.js', kind: 'required-string',
    pattern: 'thumbCacheDisableConfirmOpen: false',
    stripLineComments: true,
    note: '[lint-guard 162c-test_thumb_cache_disable_state_stub_declared] state-ui 須宣告 thumbCacheDisableConfirmOpen stub — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: [
      '_triggerThumbClear',
      '/api/gallery/thumb/clear',
      'cancelThumbCacheDisable',
      'confirmThumbCacheDisable',
    ],
    stripLineComments: true,
    note: '[lint-guard 162c-test_thumb_cache_disable_handlers_in_state_config] disable 流程三件＋clear 端點須存在 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: /prevThumbEnabled\b[\s\S]*thumbnailCacheEnabled\s*===\s*false/,
    note: '[lint-guard 162c-test_thumb_cache_disable_clear_gated_on_save_success] clear 須綁 prevThumbEnabled→false 條件 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSettingsDmmProxyContract
  {
    file: 'web/templates/settings.html', kind: 'structure-count',
    pattern: /(?<![\w:-])x-model="form\.proxyUrl"/,
    count: 1,
    note: '[lint-guard 162c-test_proxy_url_x_model_in_sources_card] proxy x-model 恰 1 次（搬移非複製） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'order',
    items: [
      { pattern: /(?<![\w:-])id="sec-search"/ },
      { pattern: /(?<![\w:-])x-model="form\.proxyUrl"/ },
      { pattern: /(?<![\w:-])id="sec-gallery"/ },
      { pattern: /(?<![\w:-])class="collapsible-content"/ },
    ],
    pairs: [[0, 1], [1, 2], [1, 3]],
    note: '[lint-guard 162c-test_proxy_url_x_model_in_sources_card] proxy x-model 須在 sec-search 內、sec-gallery／摺疊前 — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B10 迄 ----
  //
  //
  //
  // ---- 162c-B11 起 ----
  // （162c-B11 專屬子區段：只在此兩行之間追加）

  // 162c: TestCoverLoadingUx67Guard
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      'video._imgLoaded = true',
      /(?<![\w:-]):class="\{ 'cover-loaded': video\._imgLoaded \}"/,
    ],
    scope: /<template x-for="\(video, index\) in paginatedVideos"[\s\S]*?(<img\s(?:[^>"']|"[^"]*"|'[^']*')*>)/,
    note: '[lint-guard 162c-test_grid_img_has_load_and_imgloaded_fade] 格狀牆封面 <img> 須綁 _imgLoaded 與 cover-loaded 淡入 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])@load="_heroCardImageLoaded = true/,
      /(?<![\w:-]):class="\{ 'cover-loaded': _heroCardImageLoaded \}"/,
      'fetchpriority="high"',
      'loading="eager"',
    ],
    scope: /(<img :src="_matchedActress\?\.photo_url \|\| ''"[\s\S]*?>)/,
    note: '[lint-guard 162c-test_hero_img_has_load_and_heroloaded_fade] hero 女優照片須綁 _heroCardImageLoaded 淡入與 eager+high — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-show="_matchedActress\?\.photo_url && !_heroCardImageError"/,
    scope: /(<img :src="_matchedActress\?\.photo_url \|\| ''"[\s\S]*?>)/,
    note: '[lint-guard 162c-test_hero_img_xshow_gated_on_photo_url] hero <img> x-show 須 gate by photo_url（防空 url 空白框） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: '!_matchedActress.photo_url || _heroCardImageError',
    note: '[lint-guard 162c-test_hero_img_xshow_gated_on_photo_url] hero no-cover 須對空 photo_url 或 error 顯破圖 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: '_heroCardImageLoaded: false',
    stripLineComments: true,
    note: '[lint-guard 162c-test_actress_js_declares_and_resets_heroloaded] state-actress.js 須宣告 _heroCardImageLoaded — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: 'this._heroCardImageLoaded = false',
    min: 2,
    stripLineComments: true,
    note: '[lint-guard 162c-test_actress_js_declares_and_resets_heroloaded] state-actress.js _heroCardImageLoaded 重置須 ≥2 處 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: ['has_cover = false', '_imgLoaded = true'],
    scope: { anchor: /handleCoverError\s*\(\s*video\s*,\s*event\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_handle_cover_error_marks_loaded] handleCoverError 須同時設 has_cover=false 與 _imgLoaded=true — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/components/page-lifecycle.js', kind: 'required-string',
    pattern: 'persisted',
    scope: /addEventListener\('pagehide',\s*function\s*\([^)]*\)\s*\{([\s\S]*?)\}\s*\)/,
    stripLineComments: true, note: '[lint-guard 162c-test_pagehide_skips_cleanup_on_bfcache_persist] pagehide callback 須檢查 event.persisted 跳過 cleanup — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /<img x-ref="lightboxCoverImg"(?=[^>]*(?<![\w:-]):src="currentLightboxVideo\?\.cover_url")(?=[^>]*(?<![\w:-])@error="handleCoverError\(currentLightboxVideo, \$event\)")[^>]*>/,
    scope: /<div class="lightbox-cover"[^>]*has-cover[^>]*>[\s\S]*?<\/div>[\s\S]*?<!-- Metadata Panel/,
    note: '[lint-guard 162c-test_lb_base_img_keeps_cover_url_and_error] 燈箱 base <img> 須綁 cover_url 與 handleCoverError — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'img', className: 'lb-full',
    required: [/(?<![\w:-]):src="currentLightboxVideo\?\.cover_full_url"/],
    note: '[lint-guard 162c-test_lb_overlay_img_binds_cover_full_url] overlay img.lb-full 須綁 cover_full_url — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'img', className: 'lb-full',
    required: [/(?<![\w:-])@load="_lbFullLoaded\s*=\s*true"/],
    note: '[lint-guard 162c-test_lb_overlay_img_load_sets_flag] overlay img.lb-full 須 @load 翻 _lbFullLoaded — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'img', className: 'lb-full',
    required: [/(?<![\w:-]):class="\{\s*'lb-full-shown'\s*:\s*_lbFullLoaded\s*\}"/],
    forbidden: ['x-show'],
    note: '[lint-guard 162c-test_lb_overlay_img_class_binds_shown] overlay img.lb-full 須 :class lb-full-shown 且不得 x-show — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_lbFullLoaded: false',
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_js_declares_and_resets_lbfullloaded] state-lightbox.js 須宣告 _lbFullLoaded — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'this._lbFullLoaded = false',
    scope: { anchor: /_refreshLbFullBlurUp\(\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_js_declares_and_resets_lbfullloaded] _refreshLbFullBlurUp 須重置 _lbFullLoaded — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_refreshLbFullBlurUp',
    scope: { anchor: /_setLightboxIndex\(idx\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_js_declares_and_resets_lbfullloaded] _setLightboxIndex 須委託 _refreshLbFullBlurUp — 遷自 test_frontend_lint.py',
  },

  // 162c: TestWishlistCoverFadeGuard
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: [
      '_wishlistCoverLoaded[item.number] = true',
      '_wishlistCoverError[item.number] = true',
      /(?<![\w:-]):class="\{ 'cover-loaded': _wishlistCoverLoaded\[item\.number\] \}"/,
    ],
    scope: /<template x-for="\(item, index\) in wishlistItems"(?:(?!<\/template>)[\s\S])*?(<img :src="[^"]*\/api\/wishlist\/cover\?number=[^>]*>)/,
    note: '[lint-guard 162c-test_wishlist_img_has_load_and_covererror_fade] 書籤卡 <img> 須用番號 key 的 loaded／error／cover-loaded 綁定 — 遷自 test_frontend_lint.py',
  },
  // forbidden item._imgError／item._imgLoaded 已由既有 [TestWishlistCoverFadeGuard] 涵蓋；不另加以免共覆蓋

  // 162c: TestJavlibraryCfFlowT6Guard
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'rescrapeCfWaiting',
    note: '[lint-guard 162c-test_state_rescrape_declares_rescrapeCfWaiting] state-rescrape.js 須含 rescrapeCfWaiting 識別字 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: '_cfPollHandle',
    note: '[lint-guard 162c-test_state_rescrape_declares_cfPollHandle] state-rescrape.js 須含 _cfPollHandle 識別字 — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B11 迄 ----
  //
  //
  //
  // ---- 162c-B12 起 ----
  // （162c-B12 專屬子區段：只在此兩行之間追加）
  // 162c: TestJavlibraryCfFlowT6Guard
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /^[ \t]*_pollCfThenRetry\s*\([^)]*\)\s*\{/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_state_rescrape_has_pollCfThenRetry] 使用者重刮 JavLibrary 遇 Cloudflare 驗證 → 若輪詢重試函式不存在，驗證解完後不會自動重跑重刮（呼叫處 TypeError）→ 必須關窗重來 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /^[ \t]*cancelCfPoll\s*(?:\(\s*\)\s*\{|:\s*(?:async\s*)?(?:function\b|\())/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_state_rescrape_has_cancelCfPoll] 使用者在 Cloudflare 驗證等待中按取消 → 若取消函式不存在，按了沒反應、無法取消等待 → 只能等逾時 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'order',
    items: [
      { pattern: 'data.cf_needed', occurrence: 'first' },
      { pattern: 'rescrapeNotFound = true', occurrence: 'last' },
    ],
    note: '[lint-guard 162c-test_state_rescrape_cf_needed_before_notfound] 使用者重刮 JavLibrary 遇 Cloudflare 驗證 → 若 cf_needed 處理排在「找不到」之後，看到的是「找不到」而非驗證流程 → 重刮做不下去 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'result.cf_unavailable',
    scope: { anchor: /rescrapeConfirm\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_rescrape_confirm_handles_cf] 使用者在 JavLibrary 重刮預覽停留太久、按下確認時 CF 驗證已過期 → 若 rescrapeConfirm 沒接 cf_unavailable，只看到模糊的「失敗」且驗證流程不啟動 → 重刮寫不進去 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'result.cf_needed',
    scope: { anchor: /rescrapeConfirm\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_rescrape_confirm_handles_cf] 使用者在 JavLibrary 重刮預覽停留太久、按下確認時 CF 驗證已過期 → 若 rescrapeConfirm 沒接 cf_needed，只看到模糊的「失敗」且驗證流程不啟動 → 重刮寫不進去 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'clearInterval',
    scope: { anchor: /closeRescrape\(\)\s*\{/, window: 500 },
    note: '[lint-guard 162c-test_close_rescrape_clears_interval] 使用者在 Cloudflare 驗證等待中關掉重刮視窗 → 若輪詢沒被清掉，視窗已關但背景仍輪詢到逾時，解完驗證後可能自行重跑重刮／跳通知 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'rescrapeCfWaiting',
    note: '[lint-guard 162c-test_modal_has_cf_waiting_block] 使用者重刮 JavLibrary 遇 Cloudflare 驗證 → 若彈窗缺等待區塊，看不到「驗證中」提示 → 不知道在等什麼 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'jl_cf_solving',
    note: '[lint-guard 162c-test_modal_has_cf_waiting_block] 使用者重刮 JavLibrary 遇 Cloudflare 驗證 → 若彈窗缺 jl_cf_solving i18n，看不到「驗證中」文案 → 不知道在等什麼 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'cancelCfPoll',
    note: '[lint-guard 162c-test_modal_has_cf_waiting_block] 使用者重刮 JavLibrary 遇 Cloudflare 驗證 → 若取消鈕缺 cancelCfPoll 綁定，取消不了 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'order',
    items: [
      { pattern: 'data.cf_needed' },
      { pattern: "rescrapeEntryPoint === 'switch-source') {" },
    ],
    note: '[lint-guard 162c-test_cf_needed_before_switch_source_branch] 使用者在結果面板換源（switch-source）遇 JavLibrary Cloudflare 驗證 → 若 cf_needed 處理排在 switch-source 分支之後，驗證流程不啟動、落入「找不到」→ 換源做不下去 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'order',
    stripLineComments: true,
    scope: { anchor: /async\s+rescrapeWithSource\s*\(\s*sourceId\s*\)\s*\{/, braceBalanced: true },
    items: [
      { pattern: 'data.cf_unavailable' },
      { pattern: "rescrapeEntryPoint === 'switch-source') {" },
    ],
    note: '[lint-guard 162c-test_cf_unavailable_before_switch_source_branch] 使用者在結果面板換源遇 JavLibrary Cloudflare 不可用（非桌面）→ 若 cf_unavailable 處理排在 switch-source 分支之後，看到「找不到」而非「此環境無法驗證」提示 → 以為片子不存在 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestRescrapeModalSearchHideJlPillGuard
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string',
    pattern: "s.manual_only && s.is_beta && rescrapeEntryPoint === 'search'",
    note: '[lint-guard 162c-test_modal_builtin_pill_search_gate_uses_isJlUnavailable] 使用者在搜尋頁開重刮選單 → 若舊的「search 入口隱藏 JL pill」條件復活，選不到 JavLibrary — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'isJlUnavailable',
    note: '[lint-guard 162c-test_modal_builtin_pill_search_gate_uses_isJlUnavailable] 使用者在搜尋頁開重刮選單 → 若 isJlUnavailable gate 消失，非桌面也點得到做不到的 JL 驗證流程 → 按了沒結果（test_modal_builtin_pill_jl_gate_preserves_aria_disabled） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: /(?<![\w:-]):aria-disabled=/,
    note: '[lint-guard 162c-test_modal_builtin_pill_jl_gate_preserves_aria_disabled] 使用者在非桌面環境點 JavLibrary pill → 若 aria-disabled 綁定消失，螢幕報讀不知它不可用、外觀不灰 → 以為能點卻無反應 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestRescrapeVersionSwitcherGuard
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'structure-count',
    pattern: /(?<![\w:-])x-show="rescrapeHasVersions\(\)"/,
    min: 2,
    note: '[lint-guard 162c-test_version_switcher_uses_rescrapeHasVersions] 使用者重刮到 JavLibrary 多版本片 → 若 ‹ › 鈕沒綁 rescrapeHasVersions() 顯示條件，多版本時看不到切換鈕（或單版本也亂出現）→ 無法選版本 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'rescrapeVersionGo(-1)',
    note: '[lint-guard 162c-test_version_switcher_uses_rescrapeVersionGo] 使用者在多版本預覽按 ‹ → 若沒綁 rescrapeVersionGo(-1)，按了沒反應、切不了版本 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'rescrapeVersionGo(1)',
    note: '[lint-guard 162c-test_version_switcher_uses_rescrapeVersionGo] 使用者在多版本預覽按 › → 若沒綁 rescrapeVersionGo(1)，按了沒反應、切不了版本 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: /rescrape-caption[^>]*rescrapeEntryPoint[^>]*lightbox|rescrapeEntryPoint[^>]*lightbox[^>]*rescrape-caption/,
    note: '[lint-guard 162c-test_overwrite_warning_gated_by_lightbox_entrypoint] 使用者在燈箱按重刮 → 若「不可逆覆蓋」警告沒綁 lightbox 入口，燈箱入口可能看不到覆蓋 NFO／封面的警告，或搜尋入口（不寫檔）被誤導出現警告 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'bi-check-lg',
    scope: /<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*['"]search['"][^>]*>(.*?)<\/div>/s,
    note: '[lint-guard 162c-test_search_adopt_btn_uses_check_icon] 使用者在搜尋入口重刮預覽按「採用」→ 若採用鈕退回帶文字，文字溢出 48px 圓鈕破版 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'adopt_version',
    scope: /<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*['"]search['"][^>]*>(.*?)<\/div>/s,
    note: '[lint-guard 162c-test_search_adopt_btn_uses_check_icon] 使用者在搜尋入口重刮預覽按「採用」→ 若 aria-label 缺 adopt_version，螢幕報讀唸不出鈕的作用 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string',
    pattern: 'x-text',
    scope: /<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*['"]search['"][^>]*>(.*?)<\/div>/s,
    note: '[lint-guard 162c-test_search_adopt_btn_uses_check_icon] 使用者在搜尋入口重刮預覽按「採用」→ 若採用鈕含 x-text 文字，文字溢出 48px 圓鈕破版 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/components/rescrape-modal.css', kind: 'required-string',
    pattern: 'var(--color-warning)',
    scope: { anchor: /\.rescrape-version-status\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_version_status_uses_warning_color] 使用者看多版本預覽撞號提示 → 若 .rescrape-version-status 色不是 var(--color-warning)，琥珀色「注意」語意消失（判定表流程句＝無；外觀 token） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/components/rescrape-modal.css', kind: 'required-string',
    pattern: 'var(--color-warning)',
    scope: { anchor: /\.rescrape-ver-indicator\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_version_status_uses_warning_color] 使用者看多版本預覽 N/M 指示 → 若 .rescrape-ver-indicator 色不是 var(--color-warning)，與撞號提示琥珀色不一致（判定表流程句＝無；外觀 token） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: 'bi-check-lg',
    scope: /<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*['"]switch-source['"][^>]*>(.*?)<\/div>/s,
    note: '[lint-guard 162c-test_switch_source_modal_confirm_row] 使用者在結果面板換源後的預覽按採用 → 若採用鈕不在，無法完成換源 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'forbidden-string',
    pattern: 'overwrite_warning',
    scope: /<div[^>]*rescrape-confirm-row[^>]*rescrapeEntryPoint\s*===\s*['"]switch-source['"][^>]*>(.*?)<\/div>/s,
    note: '[lint-guard 162c-test_switch_source_modal_confirm_row] 使用者在結果面板換源後的預覽按採用 → 若出現「不可逆覆蓋」警告，會被誤導以為要寫檔（其實只換結果列） — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSearchAutoSourcePill
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-show=\\?["'][^"']*isComposing\(\)/,
    scope: /source_pill\((?:[^()]|\([^()]*\))*search-auto-pill(?:[^()]|\([^()]*\))*\)/s,
    note: '[lint-guard 162c-test_auto_pill_xshow_is_composing] 使用者在搜尋頁輸入新番號 → 「自動」來源膠囊該在編輯態出現；若 x-show 少了 isComposing()，膠囊在不該出現的時候一直擋在搜尋列或根本不出現 — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B12 迄 ----
  //
  //
  //
  // ---- 162c-B13 起 ----
  // （162c-B13 專屬子區段：只在此兩行之間追加）
  // 162c: TestSearchAutoSourcePill
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /openRescrape\(null,\s*\\?'search\\?'\)/,
    scope: /source_pill\((?:[^()]|\([^()]*\))*search-auto-pill(?:[^()]|\([^()]*\))*\)/s,
    note: '[lint-guard 162c-test_auto_pill_click_opens_rescrape_with_prefill] 使用者點搜尋列「自動」膠囊挑來源 → 若沒預填番號，開窗後挑源就跳出「找不到」→ 必須重打番號 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'rescrapeNumber =',
    scope: /source_pill\((?:[^()]|\([^()]*\))*search-auto-pill(?:[^()]|\([^()]*\))*\)/s,
    note: '[lint-guard 162c-test_auto_pill_click_opens_rescrape_with_prefill] 使用者點搜尋列「自動」膠囊挑來源 → 若沒預填番號，開窗後挑源就跳出「找不到」→ 必須重打番號 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-show=\\?["'][^"']*canReopenSourcePick\(\)/,
    scope: /source_pill\((?:[^()]|\([^()]*\))*search-auto-pill(?:[^()]|\([^()]*\))*\)/s,
    note: '[lint-guard 162c-test_auto_pill_xshow_contains_can_reopen_source_pick] 使用者採用 JavLibrary 版本後想再開來源選單 → 若 x-show 少了 canReopenSourcePick()，膠囊消失、無法再換版本／來源 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string',
    pattern: ['listMode', "'search'", 'pageState', "'result'", "'exact'", 'searchQuery'],
    scope: { anchor: /canReopenSourcePick\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true, note: '[lint-guard 162c-test_can_reopen_source_pick_defined_in_search_flow_js] 使用者在檔案／批次模式看某片結果 → 若 canReopenSourcePick 少了 listMode===\'search\' 等條件，頂部膠囊會帶舊番號開窗，重刮到別的片 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestResultSourcePill
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'openSwitchSourcePicker()',
    scope: /source_pill\((?:(?!source_pill\().)*?result-source-pill.*?\)\s*\}\}/s,
    note: '[lint-guard 162c-test_result_pill_click_opens_switch_picker] 使用者點結果面板「目前來源」膠囊想換來源 → 若 @click 沒綁 openSwitchSourcePicker()，按了沒反應、換不了源 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestUS9SearchGridMobileFix
  {
    file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: ['posterCrop', 'window.innerWidth <= POSTER_CROP_MAX_W', 'hero-card', 'posterCrop: posterCrop'],
    note: '[lint-guard 162c-test_search_grid_mode_threads_poster_crop] 手機搜尋格開燈箱 → grid-mode 未把 posterCrop 傳入 playGridToLightbox，ghost 右裁與落地比例錯位 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestMobileToolbarToggle
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: [
      'alpine:init',
      "Alpine.store('ui'",
      'toolbarOpen',
      'showcaseHasSearch',
      /alpine:init['"]\s*,\s*\(\)\s*=>\s*\{\s*Alpine\.store\(\s*['"]ui['"]\s*,\s*\{\s*toolbarOpen:\s*false/,
    ],
    note: '[lint-guard 162c-test_store_registered_in_alpine_init] 使用者在手機 showcase 點 navbar 搜尋 icon → 若 $store.ui 沒註冊，icon 按了沒反應、工具列叫不出來也無法清除搜尋 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/base.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<button\b[^>]*(?<![\w:-])class="navbar-search-btn[^>]*>/,
    required: [
      // lg:hidden 限 class 屬性值（搬到 data-x 不算）
      /(?<![\w:-=\'"])class="[^"]*\blg:hidden\b[^"]*"/,
      // 三字面必須落在真 @click="…" 屬性值（舊 btn.get("@click")）；整開標籤 substring 會被 data-x 餵飽
      /(?<![\w:-=\'"])@click="[^"]*\$store\.ui\.showcaseHasSearch[^"]*"/,
      /(?<![\w:-=\'"])@click="[^"]*showcase:clear-search[^"]*"/,
      /(?<![\w:-=\'"])@click="[^"]*\$store\.ui\.toolbarOpen[^"]*"/,
    ],
    note: '[lint-guard 162c-test_navbar_search_button] 使用者在手機 showcase 點 navbar 搜尋 icon → 若 @click 的收合／清除分支缺失，icon 按了不收合工具列或有搜尋時無法一鍵清除 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/base.html', kind: 'structure-count',
    pattern: /(?<![\w:-])class="navbar-search-btn/,
    count: 1,
    note: '[lint-guard 162c-test_navbar_search_button] 使用者在手機 showcase 點 navbar 搜尋 icon → 若 @click 的收合／清除分支缺失，icon 按了不收合工具列或有搜尋時無法一鍵清除 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'bi-search',
    scope: /<button[^>]*navbar-search-btn[^>]*>(.*?)<\/button>/s,
    note: '[lint-guard 162c-test_navbar_search_button] 使用者在手機 showcase 點 navbar 搜尋 icon → 若 @click 的收合／清除分支缺失，icon 按了不收合工具列或有搜尋時無法一鍵清除 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: /\{%\s*if\s+page\s*==\s*['"]showcase['"]\s*%\}/,
    note: '[lint-guard 162c-test_navbar_search_button_jinja_gated] 使用者在手機開搜尋頁（Spotlight）→ 若 navbar 搜尋 icon 沒被限定只在 showcase 渲染，搜尋頁也出現一顆按了不會動作的 icon — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/base.html', kind: 'required-string',
    pattern: 'navbar-search-btn',
    scope: /\{%\s*if\s+page\s*==\s*['"]showcase['"]\s*%\}(.*?)\{%\s*endif\s*%\}/s,
    note: '[lint-guard 162c-test_navbar_search_button_jinja_gated] 使用者在手機開搜尋頁（Spotlight）→ 若 navbar 搜尋 icon 沒被限定只在 showcase 渲染，搜尋頁也出現一顆按了不會動作的 icon — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<div\b[^>]*(?<![\w:-])class="showcase-toolbar"[^>]*>/,
    // (?<![\w:-=\'"]) 排除 data-y=':class="…"' 把綁定字面餵進開標籤 substring
    required: [/(?<![\w:-=\'"]):class="\{\s*'mobile-toolbar-open':\s*\$store\.ui\.toolbarOpen\s*\}"/],
    note: '[lint-guard 162c-test_showcase_toolbar_class_binding] 使用者在手機 showcase 點 navbar 搜尋 icon → 若工具列沒綁 mobile-toolbar-open，點了工具列不展開、搜尋框用不到 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<div\b[^>]*(?<![\w:-])class="search-bar"[^>]*>/,
    forbidden: ['mobile-toolbar-open'],
    note: '[lint-guard 162c-test_search_bar_not_bound] 使用者在手機搜尋頁 → 若 .search-bar 被誤綁 mobile-toolbar-open，搜尋框被收進 navbar icon 內預設隱藏，搜尋頁找不到輸入框 — 遷自 test_frontend_lint.py',
  },
  // 162c: TestResultSourcePill（T5 Codex P2 補回）
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-])loading_expr\s*=\s*['"]isSwitchingSource['"]/,
    scope: /source_pill\((?:(?!source_pill\().)*?result-source-pill.*?\)\s*\}\}/s,
    note: '[lint-guard 162c-test_result_pill_loading_bound_to_switching] 自動切換來源進行中膠囊要鎖住，否則再選別的來源會被舊流程覆蓋並存檔 — 遷自 test_frontend_lint.py（T5 二審刪除後 Codex P2 補回）',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-]):disabled\s*=\s*\\?["']isSwitchingSource\\?["']/,
    scope: /source_pill\((?:(?!source_pill\().)*?result-source-pill.*?\)\s*\}\}/s,
    note: '[lint-guard 162c-test_result_pill_loading_bound_to_switching] 自動切換來源進行中膠囊要鎖住，否則再選別的來源會被舊流程覆蓋並存檔 — 遷自 test_frontend_lint.py（T5 二審刪除後 Codex P2 補回）',
  },
  // ---- 162c-B13 迄 ----
  //
  //
  //
  // ---- 162c-B14 起 ----
  // （162c-B14 專屬子區段：只在此兩行之間追加）
  // 162c: TestMobileToolbarCss
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: [/position:\s*fixed/, /transform:\s*translateY\(-100%\)/, /pointer-events:\s*none/],
    scope: { anchor: /@media[^{]*max-width:\s*480px[^{]*\{\s*(?:\/\*[\s\S]*?\*\/\s*)*\.showcase-toolbar\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_toolbar_collapsed_default] 使用者在手機 showcase → 工具列預設該收起；若收合預設壞掉（沒 fixed／沒移出畫面／沒關 pointer-events），工具列常駐蓋住封面牆且擋住點擊 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: [/transform:\s*translateY\(0\)/, /pointer-events:\s*auto/],
    scope: { anchor: /\.showcase-toolbar\.mobile-toolbar-open\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_toolbar_open_state] 使用者在手機 showcase 點 navbar 搜尋 icon → 工具列該滑出可點；若展開態缺 translateY(0)／pointer-events:auto，點了工具列仍在畫面外或點不到 → 搜尋框用不了 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: [/position:\s*fixed/, /z-index:\s*85\b/],
    scope: { anchor: /\.mobile-toolbar-backdrop\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_backdrop_css] 使用者在手機展開工具列後點外面想收起 → 若 backdrop 不是 fixed 全屏或 z 階層錯（backdrop 85 須低於工具列 90），點外面收不起、或蓋住工具列使其點不到 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: /z-index:\s*90\b/,
    scope: { anchor: /@media \(max-width: 480px\) \{\s*\.showcase-toolbar \{/, braceBalanced: true },
    note: '[lint-guard 162c-test_backdrop_css] 使用者在手機展開工具列後點外面想收起 → 若 backdrop 不是 fixed 全屏或 z 階層錯（backdrop 85 須低於工具列 90），點外面收不起、或蓋住工具列使其點不到 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'structure-count',
    pattern: /(?<![\w:-])class="mobile-toolbar-backdrop"/,
    count: 1,
    note: '[lint-guard 162c-test_backdrop_dom] 使用者在手機展開工具列後點外面 → 若 backdrop 的 x-show／@click 沒綁 store，點外面收不起來；缺 x-cloak 載入瞬間 backdrop 閃現擋住點擊 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<div\b[^>]*(?<![\w:-])class="mobile-toolbar-backdrop"[^>]*>/,
    required: [
      /(?<![\w:-])x-show="\$store\.ui\.toolbarOpen"/,
      /(?<![\w:-])@click="[^"]*\$store\.ui\.toolbarOpen\s*=\s*false[^"]*"/,
      /(?<![\w:-])x-cloak(?=[\s>\/])/,
    ],
    note: '[lint-guard 162c-test_backdrop_dom] 使用者在手機展開工具列後點外面 → 若 backdrop 的 x-show／@click 沒綁 store，點外面收不起來；缺 x-cloak 載入瞬間 backdrop 閃現擋住點擊 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: /display:\s*none/,
    scope: { anchor: /@media \(min-width: 481px\) \{\s*\.navbar-search-btn\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_navbar_search_btn_hidden_above_480] 使用者在 481–1023px（平板）看 showcase → 若 navbar 搜尋 icon 未在 >480px 隱藏，會看到一顆按了不會展開工具列的 icon（誤導控制） — 遷自 test_frontend_lint.py',
  },

  // 162c: TestMobileToolbarAutoCollapse
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<button\b[^>]*(?<![\w:-])title="\{\{ t\('showcase\.action\.search'\) \}\}"[^>]*>/,
    required: [
      /(?<![\w:-])@click="[^"]*SearchChange\(\)[^"]*"/,
      /(?<![\w:-])@click="[^"]*\$store\.ui\.toolbarOpen\s*=\s*false[^"]*"/,
    ],
    note: '[lint-guard 162c-test_submit_button_collapses_toolbar] 使用者在手機工具列按箭頭送出搜尋 → 若沒同時收合，工具列仍蓋住剛出現的搜尋結果；若丟掉送出，按了不搜尋 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: [
      /@input[.\w]*="[^"]*SearchChange[^"]*toolbarOpen/,
      /@input[.\w]*="[^"]*toolbarOpen[^"]*SearchChange/,
    ],
    note: '[lint-guard 162c-test_live_filter_input_does_not_collapse] 使用者在手機工具列打字搜尋 → 若每次輸入都觸發收合，打字途中工具列滑走，字打不完 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestLightboxModalHugContract
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: /aspect-ratio\s*:\s*var\(--lb-cover-ar/,
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_aspect_ratio_set] 使用者開影片燈箱 → 封面盒不跟圖片比例 → 封面上下留黑邊、與圖不貼合（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: /flex-shrink\s*:\s*0/,
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_flex_shrink_zero] 使用者開影片燈箱 → 封面盒被 flex 壓扁（T1 letterbox 主因）→ 封面上下留白（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: [/min-width\s*:\s*0/, /min-height\s*:\s*0/],
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_floor_zeroed] 使用者開影片燈箱 → 封面盒最小寬高地板沒歸零 → 盒尺寸被內容撐住不依比例（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: '90dvh',
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_width_formula_uses_90dvh] 使用者開影片燈箱（FHD 螢幕）→ 寬度公式用 100dvh → 燈箱比視窗高、出現整體捲動（純版面） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'forbidden-string',
    pattern: ['100dvh', '100vh'],
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_width_formula_uses_90dvh] 使用者開影片燈箱（FHD 螢幕）→ 寬度公式用 100dvh → 燈箱比視窗高、出現整體捲動（純版面） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: [/position\s*:\s*absolute/, /(?<![-\w])width\s*:\s*100%/, /(?<![-\w])height\s*:\s*100%/],
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s+img\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_img_fills_box] 使用者開影片燈箱 → 圖片沒絕對定位填滿盒 → 圖歪在盒內、留白（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: [/(?<![-\w])width\s*:\s*100%/, /(?<![-\w])height\s*:\s*100%/, /margin\s*:\s*0/],
    scope: { anchor: /\.lightbox-content\s+\.lightbox-cover\.has-cover\s+\.lb-full\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_has_cover_lb_full_fills_box] 使用者開影片燈箱 → 高解析原圖層沒填滿盒 → 原圖層歪或留白（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: ['_setCoverAspect', "closest('.lightbox-cover')", "setProperty('--lb-cover-ar'"],
    stripLineComments: true,
    note: '[lint-guard 162c-test_set_cover_aspect_js_contract] 使用者開影片燈箱 → 沒有依圖片量出比例 → 封面盒維持預設 1.5 比例、直圖/寬圖留黑邊（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: [/flex\s*:\s*1\s+1\s+auto/, /overflow-y\s*:\s*auto/],
    scope: { anchor: /\.lightbox-metadata\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_metadata_flex_distribution] 使用者開影片燈箱、資訊很長 → 資訊欄不自己捲動 → 下半段資訊被切掉看不到／整個燈箱被撐出視窗 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSearchLightboxModalHugContract
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /aspect-ratio\s*:\s*var\(--lb-cover-ar/,
    scope: { anchor: /\.search-container\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s1_has_cover_aspect_ratio] 使用者在搜尋頁開燈箱 → 封面盒不跟圖片比例 → 留黑邊（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /flex-shrink\s*:\s*0/,
    scope: { anchor: /\.search-container\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s2_has_cover_flex_shrink_zero] 使用者在搜尋頁開燈箱 → 封面盒被壓扁 → 留白（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: [/min-width\s*:\s*0/, /min-height\s*:\s*0/],
    scope: { anchor: /\.search-container\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s3_has_cover_floor_zeroed] 使用者在搜尋頁開燈箱 → 封面盒地板沒歸零 → 尺寸不依比例（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: '90dvh',
    scope: { anchor: /\.search-container\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s4_has_cover_width_formula_uses_90dvh] 使用者在搜尋頁開燈箱 → 寬度公式用 100dvh → 燈箱超出視窗整體捲動（純版面） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'forbidden-string',
    pattern: ['100dvh', '100vh'],
    scope: { anchor: /\.search-container\s+\.lightbox-cover\.has-cover\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s4_has_cover_width_formula_uses_90dvh] 使用者在搜尋頁開燈箱 → 寬度公式用 100dvh → 燈箱超出視窗整體捲動（純版面） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: [/position\s*:\s*absolute/, /(?<![-\w])width\s*:\s*100%/, /(?<![-\w])height\s*:\s*100%/],
    scope: { anchor: /\.search-container\s+\.lightbox-cover\.has-cover\s+img\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s5_has_cover_img_fills_box] 使用者在搜尋頁開燈箱 → 圖沒絕對定位填滿盒 → 圖歪在盒內（純外觀） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-])@load="_setCoverAspect\(\$event\)"/,
    note: '[lint-guard 162c-test_s6_search_html_load_handler] 使用者在搜尋頁開燈箱 → 圖載入後不量比例 → 封面盒維持預設比例留黑邊（純外觀） — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B14 迄 ----
  //
  //
  //
  // ---- 162c-B15 起 ----
  // 162c: TestSearchLightboxModalHugContract
  {
    file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: ['_setCoverAspect', "closest('.lightbox-cover')", "setProperty('--lb-cover-ar'"],
    note: '[lint-guard 162c-test_s7_grid_mode_js_set_cover_aspect] 搜尋燈箱 grid-mode 須有量比例函式與 --lb-cover-ar 設定 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /overflow-y\s*:\s*hidden/,
    scope: { anchor: /\.search-container\s+\.lightbox-content\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_s8_search_lightbox_content_overflow_hidden] 搜尋燈箱外框須 overflow-y:hidden 避免整框捲動 — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSearchDetailCoverFixContract
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /^\s*min-height:\s*0\s*;/m,
    scope: { anchor: /\.search-container\s+\.av-card-full-cover(?![-\w])\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_d1_cover_min_height_zero] 詳情封面欄須 min-height:0 清 theme 地板 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /^\s*min-height:\s*0\s*;/m,
    scope: { anchor: /\.search-container\s+\.av-card-full-cover-wrapper(?![-\w])\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_d2_wrapper_min_height_zero] 詳情封面容器須 min-height:0 清 400px 地板 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /^\s*height:\s*auto\s*;/m,
    scope: { anchor: /\.search-container\s+\.av-card-full-cover-img(?![-\w])\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_d3_cover_img_height_auto] 詳情封面圖須 height:auto 由 AR 推導 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'required-string',
    pattern: /^\s*overflow:\s*visible\s*;/m,
    scope: {
      anchor: /@media\s*\(\s*max-width\s*:\s*(?:1024|1023\.98)px\s*\)\s*\{[\s\S]*?\.search-container\s+\.av-card-full-cover(?![-\w])\s*\{/,
      braceBalanced: true,
    },
    note: '[lint-guard 162c-test_d5_mobile_cover_overflow_visible] 平板／手機 media 內封面須 overflow:visible 免截劇照列 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/search.css', kind: 'structure-count',
    pattern: /@media\s*\(\s*max-width\s*:\s*(?:1024|1023\.98)px\s*\)\s*\{(?:(?!@media)[\s\S])*?\.search-container\s+\.av-card-full-cover(?![-\w])\s*\{/,
    count: 1,
    note: '[lint-guard 162c-test_d5_mobile_cover_overflow_visible] 平板／手機 media 內封面規則恰 1 條（拒歧義） — 遷自 test_frontend_lint.py',
  },

  // 162c: TestSimilarMobilePanelT4Guard
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w:-])class="similar-mobile-play-btn"/,
    scope: /<div class="similar-mobile-stage">([\s\S]*?)<\/div>\s*<!-- 右上/,
    note: '[lint-guard 162c-test_mobile_play_btn_exists_in_stage] 相似面板 stage 內須有播放鈕 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])@click\.stop="playVideo\(currentLightboxVideo\?\.path\)"/,
      /(?<![\w:-])x-show="!!currentLightboxVideo\?\.path"/,
      /(?<![\w:-]):disabled="similarModeAnimating"/,
      /(?<![\w:-]):aria-label="t\('showcase\.action\.play'\)"/,
    ],
    scope: /<button class="similar-mobile-play-btn"[^>]*>/,
    note: '[lint-guard 162c-test_mobile_play_btn_handlers] 播放鈕須有 stop／path guard／disabled／aria-label — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: ['var(--overlay-control)', 'var(--fluent-blur-light)', '-webkit-backdrop-filter', 'border-radius: 50%'],
    scope: { anchor: /\.similar-mobile-play-btn\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_play_btn_css_tokens] 播放鈕 CSS 須用 Fluent token 與圓形 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: '.similar-mobile-play-btn',
    scope: { anchor: /@media\s*\(max-width:\s*959px\)[^{]*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_play_btn_css_tokens] 播放鈕規則須在 max-width:959px media 內 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: 'img[data-ghost-hidden] ~ .similar-mobile-play-btn',
    note: '[lint-guard 162c-test_mobile_play_btn_ghost_hide] 須有 ghost-hide 選擇器隱藏飛行中播放鈕 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/css/pages/showcase/06-responsive-and-lists.css', kind: 'required-string',
    pattern: [/opacity:\s*0\s*;/, 'pointer-events: none'],
    scope: { anchor: /img\[data-ghost-hidden\]\s*~\s*\.similar-mobile-play-btn\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_play_btn_ghost_hide] ghost-hide 塊須 opacity:0 與 pointer-events:none — 遷自 test_frontend_lint.py',
  },

  // 162c: TestDirPathHelperGuard
  {
    file: 'web/static/js/shared/dir-path.js', kind: 'required-string',
    pattern: 'export function dirPath',
    note: '[lint-guard 162c-test_dir_path_js_exists_and_exports] shared/dir-path.js 須 export function dirPath — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: "import { dirPath } from '@/shared/dir-path.js'",
    note: '[lint-guard 162c-test_state_scan_imports_dir_path] state-scan.js 須 import dirPath — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/settings/state-ui.js', kind: 'required-string',
    pattern: "import { dirPath } from '@/shared/dir-path.js'",
    note: '[lint-guard 162c-test_state_ui_imports_dir_path] state-ui.js 須 import dirPath — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: /^[ \t]+dirPath\s*(?::\s*dirPath\s*)?,/m,
    note: '[lint-guard 162c-test_state_scan_exposes_dir_path_on_state] state-scan.js 須把 dirPath 揭露成 state 屬性 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/settings/state-ui.js', kind: 'required-string',
    pattern: /^[ \t]+dirPath\s*(?::\s*dirPath\s*)?,/m,
    note: '[lint-guard 162c-test_state_ui_exposes_dir_path_on_state] state-ui.js 須把 dirPath 揭露成 state 屬性 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-text="dirPath\(dir\)"/,
    note: '[lint-guard 162c-test_scanner_html_uses_dir_path] scanner.html 資料夾列須用 dirPath(dir) — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'forbidden-string',
    pattern: /(?<![\w:-])x-text="dir"/,
    note: '[lint-guard 162c-test_scanner_html_no_bare_xtext_dir] scanner.html 不得殘留裸 x-text="dir" — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-]):key="dirPath\(dir\)"/,
    note: '[lint-guard 162c-test_settings_html_key_uses_dir_path] settings.html :key 須用 dirPath(dir) — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: /(?<![\w:-]):key="dir"/,
    note: '[lint-guard 162c-test_settings_html_no_bare_key_dir] settings.html 不得殘留裸 :key="dir" — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-]):title="dirPath\(dir\)"/,
    note: '[lint-guard 162c-test_settings_html_title_uses_dir_path] settings.html :title 須用 dirPath(dir) — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])@click="pickScannerDirectory\(dirPath\(dir\)\)"/,
    note: '[lint-guard 162c-test_settings_html_click_uses_dir_path] settings.html @click 須傳 dirPath(dir) — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-text="dirPath\(dir\)"/,
    note: '[lint-guard 162c-test_settings_html_xtext_uses_dir_path] settings.html x-text 須用 dirPath(dir) — 遷自 test_frontend_lint.py',
  },

  // 162c: TestDirReadonlyUIGuard
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-model="dir\.output_path"/,
    note: '[lint-guard 162c-test_scanner_html_output_path_input] scanner.html 輸出夾須綁 x-model="dir.output_path" — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B15 迄 ----
  //
  //
  //
  // ---- 162c-B16 起 ----
  // （162c-B16 專屬子區段：只在此兩行之間追加）
  // 162c: TestGhostFlyGuards
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /var\s+coverEl\s*=/,
    scope: { anchor: /playGridToLightbox\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_open_hide_and_restore_target_is_cover_container] 使用者點縮圖開燈箱 → 封面疊出兩張圖（重影）閃一下 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', anyOf: true,
    pattern: ["closest('.lightbox-cover')", "querySelector('.lightbox-cover')"],
    scope: { anchor: /playGridToLightbox\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_open_hide_and_restore_target_is_cover_container] 使用者點縮圖開燈箱 → 封面疊出兩張圖（重影）閃一下 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /coverEl\.setAttribute\(\s*'data-ghost-hidden'/,
    scope: { anchor: /playGridToLightbox\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_open_hide_and_restore_target_is_cover_container] 使用者點縮圖開燈箱 → 封面疊出兩張圖（重影）閃一下 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /gsap\.set\(\s*coverEl\s*,\s*\{\s*opacity:\s*0/,
    scope: { anchor: /playGridToLightbox\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_open_hide_and_restore_target_is_cover_container] 使用者點縮圖開燈箱 → 封面疊出兩張圖（重影）閃一下 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /cleanupGhost\(\s*ghost\s*,\s*coverEl/,
    scope: { anchor: /playGridToLightbox\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_open_hide_and_restore_target_is_cover_container] 使用者點縮圖開燈箱 → 封面疊出兩張圖（重影）閃一下 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /var\s+coverEl\s*=/,
    scope: { anchor: /playLightboxToGrid\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_close_hide_and_restore_target_is_cover_container] 使用者關燈箱 → 封面疊出兩張圖（重影）或殘留透明封面 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', anyOf: true,
    pattern: ["closest('.lightbox-cover')", "querySelector('.lightbox-cover')"],
    scope: { anchor: /playLightboxToGrid\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_close_hide_and_restore_target_is_cover_container] 使用者關燈箱 → 封面疊出兩張圖（重影）或殘留透明封面 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /coverEl\.setAttribute\(\s*'data-ghost-hidden'/,
    scope: { anchor: /playLightboxToGrid\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_close_hide_and_restore_target_is_cover_container] 使用者關燈箱 → 封面疊出兩張圖（重影）或殘留透明封面 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /gsap\.set\(\s*coverEl\s*,\s*\{\s*opacity:\s*0/,
    scope: { anchor: /playLightboxToGrid\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_close_hide_and_restore_target_is_cover_container] 使用者關燈箱 → 封面疊出兩張圖（重影）或殘留透明封面 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /gsap\.set\(\s*coverEl\s*,\s*\{\s*opacity:\s*1/,
    scope: { anchor: /playLightboxToGrid\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_close_hide_and_restore_target_is_cover_container] 使用者關燈箱 → 封面疊出兩張圖（重影）或殘留透明封面 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: /cleanupGhost\(\s*ghost\s*,\s*targetImg\s*,\s*coverEl/,
    scope: { anchor: /playLightboxToGrid\s*:\s*function\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_close_hide_and_restore_target_is_cover_container] 使用者關燈箱 → 封面疊出兩張圖（重影）或殘留透明封面 — 遷自 test_contract_animation.py',
  },

  // 162c: TestModeToggleFadeOutGuard
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /(?<![\w$.])onOldFadeComplete\s*:\s*flipAndFadeIn(?![\w$])/,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?toggleActressMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_toggle_actress_mode_uses_callback] 使用者按影片／女優模式切換 → 動畫存在卻找不到 onOldFadeComplete，模式旗標不翻轉，切換做不完 — 遷自 test_contract_animation.py（Codex pre-merge P2 補回）',
  },
  {
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string',
    pattern: /playModeCrossfade\s*:\s*function\s*\(\s*oldMode\s*,\s*newMode\s*,\s*params\s*,\s*callbacks\s*\)/,
    note: '[lint-guard 162c-test_play_mode_crossfade_has_callbacks_param] 使用者按「女優／影片模式」切換 → 第四參數 callbacks 被拔掉後 onOldFadeComplete 永不被呼叫（呼叫端只檢查 fade 是 function、不進 fallback），旗標翻轉不發生，模式切不過去 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: '_animGeneration',
    min: 2,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?toggleActressMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_toggle_actress_mode_animgen_guard] 使用者快速連按女優／影片模式切換 → 舊的淡出 callback 事後翻旗標，畫面停在與按鈕相反的模式（無聲的錯，只在快速連點時發生） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /(?:function\s+\w*FadeIn\w*|var\s+\w*FadeIn\w*\s*=\s*function|\w*FadeIn\w*\s*=\s*function)/,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?toggleActressMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_toggle_actress_mode_handles_animations_unavailable] 動畫腳本載入失敗時使用者按「女優模式」→ 淡出 callback 永不觸發 → 模式永遠切不過去（按了沒反應） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /(?:typeof\s+\w+\s*===\s*['"]function['"]|window\.ShowcaseAnimations\s*&&\s*window\.ShowcaseAnimations\.playModeCrossfade)/,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?toggleActressMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_toggle_actress_mode_handles_animations_unavailable] 動畫腳本載入失敗時使用者按「女優模式」→ 淡出 callback 永不觸發 → 模式永遠切不過去（按了沒反應） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: /\bflipAndFadeIn\b/,
    min: 3,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?toggleActressMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_toggle_actress_mode_handles_animations_unavailable] 動畫腳本載入失敗時使用者按「女優模式」→ 淡出 callback 永不觸發 → 模式永遠切不過去（按了沒反應） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', anyOf: true,
    pattern: ['prefersReducedMotion', 'playContainerFadeIn'],
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?toggleActressMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_toggle_actress_mode_reduced_motion_guard_on_fade_in] 開啟「減少動態」的使用者切換女優／影片模式 → 仍被播放淡入動畫（偏好被無視） — 遷自 test_contract_animation.py',
  },

  // 162c: TestDirReadonlyUIGuard
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-show="dir\.readonly &&/,
    note: '[lint-guard 162c-test_scanner_html_output_row_xshow] 使用者在掃描頁 → 輸出夾列改用 x-if 或沒綁 dir.readonly → 非唯讀來源也顯示輸出夾欄、或切換時輸入框內容丟失 — 遷自 test_frontend_lint.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: "output_path: ''",
    count: 2,
    note: '[lint-guard 162c-test_state_scan_push_has_output_path] 使用者在掃描頁新增資料夾 → push 物件缺 output_path 欄 → 之後填輸出夾時屬性延遲建立，儲存序列化鍵序不穩（dirty 判定可能誤判） — 遷自 test_frontend_lint.py',
  },

  // 162c: TestRewriteStrmConfirmGuard
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'settings.scraper.strm_mapping.rewrite_failed',
    count: 2,
    scope: /async confirmRewriteStrm\(\)[\s\S]*?(?=cancelRewriteStrm\(\))/,
    note: '[lint-guard 162c-test_config_js_confirm_calls_real_endpoint_and_toast] 使用者在設定頁改 strm 映射並確認改寫 → 改寫失敗（回 success:false 或網路例外）卻沒跳錯誤 toast → 使用者以為既有 .strm 已更新、其實沒改（無聲的錯） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: ['"title"', '"body"', '"cancel"', '"confirm"'],
    scope: { anchor: /"rewrite_confirm"\s*:\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_zh_tw_json_has_rewrite_keys] 使用者在設定頁確認改寫 .strm 時 → zh_TW 缺 rewrite_confirm／rewrite_done／rewrite_failed 字串 → 確認視窗或 toast 顯示原始鍵名（標籤文案） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: /"body"\s*:\s*"[^"]*\{count\}/,
    scope: { anchor: /"rewrite_confirm"\s*:\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_zh_tw_json_has_rewrite_keys] 使用者在設定頁確認改寫 .strm 時 → zh_TW 缺 rewrite_confirm／rewrite_done／rewrite_failed 字串 → 確認視窗或 toast 顯示原始鍵名（標籤文案） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: /"rewrite_done"\s*:\s*"[^"]*\{count\}/,
    note: '[lint-guard 162c-test_zh_tw_json_has_rewrite_keys] 使用者在設定頁確認改寫 .strm 時 → zh_TW 缺 rewrite_confirm／rewrite_done／rewrite_failed 字串 → 確認視窗或 toast 顯示原始鍵名（標籤文案） — 遷自 test_frontend_lint.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: /"rewrite_failed"\s*:\s*"[^"]+"/,
    note: '[lint-guard 162c-test_zh_tw_json_has_rewrite_keys] 使用者在設定頁確認改寫 .strm 時 → zh_TW 缺 rewrite_confirm／rewrite_done／rewrite_failed 字串 → 確認視窗或 toast 顯示原始鍵名（標籤文案） — 遷自 test_frontend_lint.py',
  },
  // ---- 162c-B16 迄 ----
  //
  //
  //
  // ---- 162c-B17 起 ----
  // （162c-B17 專屬子區段：只在此兩行之間追加）
  // 162c: TestPickerIntegrationGuard
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'bi-arrow-clockwise', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'showcase.actress.change_photo', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'currentLightboxActress?.is_favorite', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  // actress-picker-overlay 存在性改由 test_picker_overlay_is_showcase_lightbox_direct_child 的 nested-count 覆蓋（同字面剪斷會共覆蓋）
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'picker-candidates-grid', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'picker-source-badge', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'picker-loading', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: /(?<![\w:-])class="(?:[^"]*\s)?picker-empty(?:\s[^"]*)?"/, note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string', pattern: 'actress-picker-area', note: '[lint-guard 162c-test_picker_html_contains] 使用者在女優燈箱按「換照片」→ 候選面板（或按鈕）不出現，換不了照片 — 遷自 test_contract_animation.py' },
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'nested-count',
    outerAnchor: /<div class="showcase-lightbox"/,
    outerTagName: 'div', innerToken: 'actress-picker-overlay', expected: 1,
    note: '[lint-guard 162c-test_picker_overlay_is_showcase_lightbox_direct_child] 換照片面板被包進 lightbox-content 的 transform 祖先 → position:fixed 失效、面板跑位或被裁切 — 遷自 test_contract_animation.py',
  },
  // 162c: TestUS5PosterCropGhostCrossfade
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'posterCrop', note: '[lint-guard 162c-test_state_lightbox_threads_poster_crop] 手機點海報格開燈箱 → 縮圖右裁與燈箱 contain 比例不同，封面落地時硬切變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'window.innerWidth <= POSTER_CROP_MAX_W', note: '[lint-guard 162c-test_state_lightbox_threads_poster_crop] 手機點海報格開燈箱 → 縮圖右裁與燈箱 contain 比例不同，封面落地時硬切變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'showFavoriteActresses', note: '[lint-guard 162c-test_state_lightbox_threads_poster_crop] 手機點海報格開燈箱 → 縮圖右裁與燈箱 contain 比例不同，封面落地時硬切變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'hero-card', stripLineComments: true, note: '[lint-guard 162c-test_state_lightbox_threads_poster_crop] 手機點海報格開燈箱 → 縮圖右裁與燈箱 contain 比例不同，封面落地時硬切變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'posterCrop: posterCrop', note: '[lint-guard 162c-test_state_lightbox_threads_poster_crop] 手機點海報格開燈箱 → 縮圖右裁與燈箱 contain 比例不同，封面落地時硬切變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'options.posterCrop', scope: /playGridToLightbox: function([\s\S]*?)playLightboxToGrid: function/, note: '[lint-guard 162c-test_ghost_fly_consumes_and_aligns_crop] 落地前 ghost 沒對齊縮圖右裁，起飛時畫面橫向跳一下 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: "objectPosition = 'right center'", scope: /playGridToLightbox: function([\s\S]*?)playLightboxToGrid: function/, note: '[lint-guard 162c-test_ghost_fly_consumes_and_aligns_crop] 落地前 ghost 沒對齊縮圖右裁，起飛時畫面橫向跳一下 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'posterCrop && coverEl', scope: /playGridToLightbox: function([\s\S]*?)playLightboxToGrid: function/, note: '[lint-guard 162c-test_ghost_fly_landing_crossfade] 落地改回硬切，封面 cover→contain 瞬間變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'opacity: 1, duration: 0.12', scope: /playGridToLightbox: function([\s\S]*?)playLightboxToGrid: function/, note: '[lint-guard 162c-test_ghost_fly_landing_crossfade] 落地改回硬切，封面 cover→contain 瞬間變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'opacity: 0, duration: 0.12', scope: /playGridToLightbox: function([\s\S]*?)playLightboxToGrid: function/, note: '[lint-guard 162c-test_ghost_fly_landing_crossfade] 落地改回硬切，封面 cover→contain 瞬間變形 — 遷自 test_contract_animation.py' },
  { file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string', pattern: 'cleanupGhost(ghost, coverEl)', scope: /playGridToLightbox: function([\s\S]*?)playLightboxToGrid: function/, note: '[lint-guard 162c-test_ghost_fly_landing_crossfade] 落地改回硬切，封面 cover→contain 瞬間變形 — 遷自 test_contract_animation.py' },
  // 162c: TestMobileSimilarPanelContractGuard
  // class="similar-mobile-panel" 存在性改由 test_mobile_panel_has_x_trap 的 class-tag 覆蓋（刪 class 行會共覆蓋）
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'similar-mobile-panel',
    required: [/(?<![\w:-])x-trap\.inert="similarModeMobileOpen"/],
    note: '[lint-guard 162c-test_mobile_panel_has_x_trap] 鍵盤／螢幕閱讀器開手機相似面板 → Tab 跑到被遮住的燈箱按鈕 — 遷自 test_contract_animation.py',
  },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '!similarModeMobileOpen', scope: /(?<![\w:-])x-trap\.inert="([^"]*deleteVideoModalOpen[^"]*)"/, note: '[lint-guard 162c-test_mobile_panel_lightbox_trap_yields] 鍵盤開手機相似面板 → 燈箱焦點陷阱沒釋放，焦點卡在燈箱 — 遷自 test_contract_animation.py' },
  // ---- 162c-B17 迄 ----
  //
  //
  //
  // ---- 162c-B18 起 ----
  // （162c-B18 專屬子區段：只在此兩行之間追加）
  // 162c: TestMobileSimilarPanelContractGuard
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'order',
    scope: { anchor: /async\s+onMobileDrillClick\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    items: [
      { pattern: 'similarModeAnimating = true' },
      { pattern: /(?<![A-Za-z0-9_$-])\bawait\b/ },
    ],
    note: '[lint-guard 162c-test_mobile_drill_lock_before_await] 使用者在手機相似面板快速連點同一張卡兩次 → 兩個請求並發進入，面板內容錯亂或卡住（連點競態，無聲） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'forbidden-string',
    pattern: 'closeSimilarMode',
    scope: { anchor: /async\s+closeMobilePanel\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_panel_no_call_desktop_closeSimilarMode] 使用者關閉手機相似面板 → 呼叫到桌面的 closeSimilarMode，await playExit 永不 resolve，面板卡住關不掉（凍結） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'slice(0, 6)',
    scope: { anchor: /async\s+_openMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_burst_card_count_6] _openMobilePanel 須 slice(0, 6) 固定 6 張 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: ['_MOBILE_PICKER_PARAMS', /const\s+_MOBILE_PICKER_PARAMS/],
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_uses_own_picker_params] 使用者開手機相似面板 → 裸引用他檔私有 _PICKER_PARAMS 丟 ReferenceError，面板打不開（按了沒反應） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'forbidden-string',
    pattern: /(?<!_MOBILE)_PICKER_PARAMS/,
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_uses_own_picker_params] 使用者開手機相似面板 → 裸引用他檔私有 _PICKER_PARAMS 丟 ReferenceError，面板打不開（按了沒反應） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: ['matchMedia', '960', 'similarModeMobileOpen', 'closeMobilePanel'],
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_panel_matchmedia_960] 手機使用者旋轉成平板寬度（≥960px）時行動面板沒被收掉 → flag 殘留卡住燈箱焦點陷阱，鍵盤焦點出不來 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/burst-picker.js', kind: 'required-string',
    pattern: ['back.out', 'arcOvershoot'],
    note: '[lint-guard 162c-test_burst_picker_back_out_exists_no_1_7_pinned] burst-picker.js 須含 back.out 與 arcOvershoot（不 pin 1.7） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: ['similarModeMobileOpen', 'closeMobilePanel'],
    scope: { anchor: /handleKeydown\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_panel_keydown_intercept] 外接鍵盤使用者在手機相似面板開著時按 Esc／方向鍵 → 面板底下的燈箱被關掉、或影片被切到下一片（看到錯的片） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: ['closeLightbox', 'prevLightboxVideo', 'nextLightboxVideo'],
    scope: { anchor: /if\s*\(\s*this\.similarModeMobileOpen\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_panel_keydown_intercept] 外接鍵盤使用者在手機相似面板開著時按 Esc／方向鍵 → 面板底下的燈箱被關掉、或影片被切到下一片（看到錯的片） — 遷自 test_contract_animation.py',
  },
  // 162c: TestMobilePanelT3Guards
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: [
      'playMobilePanelEnter',
      'playMobilePanelExit',
      /playMobilePanelEnter\s*:\s*playMobilePanelEnter/,
      /playMobilePanelExit\s*:\s*playMobilePanelExit/,
    ],
    stripLineComments: true, note: '[lint-guard 162c-test_mobile_panel_enter_exit_functions_exported] 使用者開手機相似面板 → helper 缺失丟 TypeError，面板開不起來（按了沒反應） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: 'createCoverGhost',
    scope: { anchor: /function\s+playMobilePanelEnter\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_enter_uses_create_cover_ghost_not_constellation] playMobilePanelEnter 須直接用 createCoverGhost，不可包裝桌面禁區函式 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'forbidden-string',
    pattern: 'play56cConstellationEnter',
    scope: { anchor: /function\s+playMobilePanelEnter\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_enter_uses_create_cover_ghost_not_constellation] playMobilePanelEnter 須直接用 createCoverGhost，不可包裝桌面禁區函式 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: ['DURATION.medium', '0.333', 'fluent-decel'],
    scope: { anchor: /function\s+playMobilePanelEnter\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_transition_tokenized] playMobilePanelEnter／Exit 須用 DURATION.medium token＋fluent ease，禁裸 duration 數字 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: ['DURATION.medium', '0.333', 'fluent-accel'],
    scope: { anchor: /function\s+playMobilePanelExit\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_transition_tokenized] playMobilePanelEnter／Exit 須用 DURATION.medium token＋fluent ease，禁裸 duration 數字 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'forbidden-string',
    pattern: /\bduration\s*:\s*\d+(\.\d+)?/,
    scope: { anchor: /function\s+playMobilePanelEnter\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_transition_tokenized] playMobilePanelEnter／Exit 須用 DURATION.medium token＋fluent ease，禁裸 duration 數字 — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'forbidden-string',
    pattern: /\bduration\s*:\s*\d+(\.\d+)?/,
    scope: { anchor: /function\s+playMobilePanelExit\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_mobile_transition_tokenized] playMobilePanelEnter／Exit 須用 DURATION.medium token＋fluent ease，禁裸 duration 數字 — 遷自 test_contract_animation.py',
  },
  // ---- 162c-B18 迄 ----
  //
  //
  //
  // ---- 162c-B19 起 ----
  // （162c-B19 專屬子區段：只在此兩行之間追加）

  // 162c: TestMobilePanelT3Guards
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: /async\s+closeMobilePanel\s*\(/,
    note: '[lint-guard 162c-test_mobile_close_panel_is_async] 使用者關閉手機相似面板 → closeMobilePanel 須為 async（exit ghost await 前提） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'shouldSkip',
    scope: { anchor: /async\s+_openMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → _openMobilePanel 須含 shouldSkip（PRM 閘） — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'mobilePanelCoverImg',
    scope: { anchor: /async\s+_openMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → _openMobilePanel 須含 mobilePanelCoverImg — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'playMobilePanelEnter',
    scope: { anchor: /async\s+_openMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → _openMobilePanel 須含 playMobilePanelEnter — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'order',
    scope: { anchor: /async\s+_openMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    items: [
      { pattern: /!\s*window\.BurstPicker\.shouldSkip/ },
      { pattern: 'playMobilePanelEnter' },
    ],
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → !shouldSkip 閘須早於 playMobilePanelEnter — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'shouldSkip',
    scope: { anchor: /(?:async\s+)?closeMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → closeMobilePanel 須含 shouldSkip — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'playMobilePanelExit',
    scope: { anchor: /(?:async\s+)?closeMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → closeMobilePanel 須含 playMobilePanelExit — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'order',
    scope: { anchor: /(?:async\s+)?closeMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    items: [
      { pattern: /!\s*window\.BurstPicker\.shouldSkip/ },
      { pattern: 'playMobilePanelExit' },
    ],
    note: '[lint-guard 162c-test_mobile_transition_prm_fallback] 開啟減少動態偏好 → !shouldSkip 閘須早於 playMobilePanelExit — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'order',
    scope: { anchor: /(?:async\s+)?closeMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    items: [
      { pattern: /_mobileEnterTl\s*\.\s*kill\s*\(/ },
      { pattern: 'playMobilePanelExit' },
    ],
    note: '[lint-guard 162c-test_mobile_close_kills_enter_timeline] 中途關閉手機相似面板 → _mobileEnterTl.kill 須早於 playMobilePanelExit — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: '_mobileEnterGhost',
    scope: { anchor: /(?:async\s+)?closeMobilePanel\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_close_kills_enter_timeline] 中途關閉手機相似面板 → closeMobilePanel 須顯式 cleanup _mobileEnterGhost — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'required-string',
    pattern: '.similar-main-anchor',
    stripLineComments: true, note: '[lint-guard 162c-test_desktop_constellation_byte_identical_anchor] 桌面星座進場 → ghost-fly.js 須保留 .similar-main-anchor — 遷自 test_contract_animation.py',
  },
  {
    file: 'web/static/js/shared/ghost-fly.js', kind: 'forbidden-string',
    pattern: '.similar-main-anchor',
    scope: { anchor: /function\s+playMobilePanelEnter\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_desktop_constellation_byte_identical_anchor] 手機進場 helper 不得引用桌面 .similar-main-anchor — 遷自 test_contract_animation.py',
  },

  // 162c: TestUserTagsApiGuard
  {
    file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: [
      'user-tags',
      'async confirmAddTag()',
      'async removeUserTag(',
      'fileList[this.currentFileIndex].user_tags',
      'currentUserTags()',
      'fetchUserTagsForCurrent',
    ],
    note: '[lint-guard 162c-test_result_card_js_contains] 搜尋頁加／移除標籤 → result-card.js 須接 /api/user-tags 與 file-level user_tags — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/search/state/result-card.js', kind: 'forbidden-string',
    pattern: ['pathToFileUri', 'c.user_tags.push(tag)'],
    note: '[lint-guard 162c-test_result_card_js_contains] 搜尋頁加／移除標籤 → result-card.js 不得殘留 pathToFileUri／result-level push — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string', anyOf: true,
    pattern: [
      'fileList[this.currentFileIndex].user_tags',
      /(?=[\s\S]*file\.user_tags)(?=[\s\S]*this\.fileList\?\.\[this\.currentFileIndex\])/,
    ],
    scope: { anchor: /async fetchUserTagsForCurrent\(\)/, window: 800 },
    note: '[lint-guard 162c-test_result_card_js_contains] 搜尋頁加／移除標籤 → fetchUserTagsForCurrent 窗內須寫回 file-level user_tags — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: ['!addingTag && canEditFile()', 'currentUserTags()'],
    note: '[lint-guard 162c-test_search_html_contains] 關鍵字模式加標籤 → tags+ 鈕須經 canEditFile() 閘 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string',
    pattern: 'user_tags: []',
    note: '[lint-guard 162c-test_path_utils_and_locales] file-list 初始化須含 user_tags: []（currentUserTags 回空陣列前提） — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestEditModeCanEditFileGuard
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])x-show="editingTitle && canEditFile\(\)"/,
      /(?<![\w:-])x-show="editingChineseTitle && canEditFile\(\)"/,
      /(?<![\w:-])x-show="editingActors && canEditFile\(\)"/,
    ],
    note: '[lint-guard 162c-test_search_html_edit_divs_gated_by_can_edit_file] 編輯中切關鍵字搜尋 → 三編輯 div 須以 x-show=\"editing* && canEditFile()\" 閘 — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestDateGatingGuard
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: [
      '!canEditFile() || current().date',
      'canEditFile() && !current().date',
      ":value=\"current().date || ''\"",
    ],
    note: '[lint-guard 162c-test_search_html_date_span_and_picker_complementary_gating] 檔案模式挑發售日 → date span／picker 互補閘＋:value 反應性重設 — 遷自 test_contract_api_routes.py',
  },

  // ---- 162c-B19 迄 ----
  //
  //
  //
  // ---- 162c-B20 起 ----
  // （162c-B20 專屬子區段：只在此兩行之間追加）

  // 162c: TestDateGatingGuard
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-])@focus="startEditDate\(\)"/,
    note: '[lint-guard 162c-test_search_html_date_input_wired_to_identity_guarded_methods] 使用者打開日曆到選好日期之間候選被換掉 → 日期被寫進錯的候選 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/search.html', kind: 'required-string',
    pattern: /(?<![\w:-])@change="confirmEditDate\(\$event\.target\.value\)"/,
    note: '[lint-guard 162c-test_search_html_date_input_wired_to_identity_guarded_methods] 使用者打開日曆到選好日期之間候選被換掉 → 日期被寫進錯的候選 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/search.html', kind: 'forbidden-string',
    pattern: 'current().date = $event.target.value',
    note: '[lint-guard 162c-test_search_html_date_input_wired_to_identity_guarded_methods] 使用者打開日曆到選好日期之間候選被換掉 → 日期被寫進錯的候選 — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestShowcaseAliasGuard
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: ['var _nameToGroup = {}', '/api/actress-aliases'],
    note: '[lint-guard 162c-test_alias_js_contains] 使用者用別名搜尋女優 → 若別名表沒載入或沒展開，搜別名找不到這位女優（無聲少結果） — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: '_nameToGroup[a.name]',
    note: '[lint-guard 162c-test_alias_js_contains] 使用者用別名搜尋女優 → 若別名表沒載入或沒展開，搜別名找不到這位女優（無聲少結果） — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: '_nameToGroup[term]',
    note: '[lint-guard 162c-test_alias_js_contains] 使用者用別名搜尋女優 → 若別名表沒載入或沒展開，搜別名找不到這位女優（無聲少結果） — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: '_nameToGroup',
    scope: { anchor: /async\s+_checkPreciseActressMatch\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_alias_js_contains] 使用者用別名搜尋女優 → 若別名表沒載入或沒展開，搜別名找不到這位女優（無聲少結果） — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestRescrapeStateGuard
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /export\s+function\s+rescrapeState\s*\(/,
    note: '[lint-guard 162c-test_exports_rescrape_state_factory] 使用者開影片牆或搜尋頁 → 若 rescrapeState 沒有 export,showcase/main.js:23 與 search/main.js:10 的 ESM named import 失敗,整頁功能載不起來 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: [
      'openRescrape',
      'rescrapeWithSource',
      'rescrapeConfirm',
      'rescrapeBackToPick',
      'closeRescrape',
      'rescrapeBuiltinSources',
      'rescrapeMetatubeSources',
    ],
    stripLineComments: true, note: '[lint-guard 162c-test_defines_all_methods] 使用者在重刮彈窗預覽步驟按「回上一步」→ 若 rescrapeBackToPick 被拿掉，按鈕沒反應，只能關窗重來 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: ["'/api/enrich-single'", 'refresh_full', /overwrite_existing:\s*true/],
    note: '[lint-guard 162c-test_commit_contract] 使用者在重刮彈窗按確認 → 若沒帶 mode=refresh_full＋overwrite_existing=true，重刮看似成功但舊資料沒被覆蓋 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: "'/api/rescrape/preview'",
    note: '[lint-guard 162c-test_preview_contract] 使用者在重刮彈窗點來源 pill → 若預覽路徑與後端 /api/rescrape/preview 對不上，永遠看不到預覽 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string',
    pattern: 'currentLightboxVideo',
    note: '[lint-guard 162c-test_no_current_lightbox_video] 使用者在重刮彈窗只是預覽 → 若 mixin 動到 currentLightboxVideo，沒確認的預覽資料會直接顯示在燈箱上像已存檔，關窗後還殘留 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string',
    pattern: ["from '@/shared/state-rescrape.js'", 'rescrapeState.call(this)'],
    note: '[lint-guard 162c-test_main_js_imports_and_merges_rescrape_state] 使用者在影片牆燈箱按 ⚙ 重刮 → 若 main.js 沒接 rescrapeState，彈窗狀態不存在、按了沒反應（重刮整個不可用） — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /rescrapeNumber\s*=.*video\s*&&\s*video\.number/,
    note: '[lint-guard 162c-test_open_rescrape_reads_video_number] 使用者修正番號後再開重刮彈窗 → 預填欄若不是 video.number，會是空白或舊值，要重打番號 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'forbidden-string',
    pattern: 'longPressReset',
    note: '[lint-guard 162c-test_close_rescrape_clears_longpress_flag] 無（長壓基礎設施已退役，加回 longPressReset 呼叫畫面無差） — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /rescrapeMetatubeSources\s*\(\s*\)\s*\{[^}]*\.filter\s*\([^)]*s\.type\s*===\s*['"]metatube['"][^)]*&&[^)]*s\.routable\s*===\s*true[^)]*\)/s,
    note: '[lint-guard 162c-test_rescrape_metatube_sources_has_routable_gate] 使用者在重刮彈窗點 metatube 來源 pill → 後端沒開放路由時點下去只回「查無」，被誤導以為片子不存在 — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestServerModeToggleGuard
  {
    file: 'web/templates/settings.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<div\b[^>]*(?<![\w:-])id="settings-components"[^>]*>/,
    required: [/(?<![\w:-])data-lan-ip=/],
    note: '[lint-guard 162c-test_settings_root_has_data_lan_ip] 使用者開設定頁切到伺服器模式 → 若根節點沒帶 data-lan-ip，橫條永遠說「取不到 IP」，看不到別台裝置要連的網址 — 遷自 test_contract_api_routes.py',
  },

  // ---- 162c-B20 迄 ----
  //
  //
  //
  // ---- 162c-B21 起 ----
  // （162c-B21 專屬子區段：只在此兩行之間追加）

  // 162c: TestServerModeToggleGuard
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])@click="requestServerModeChange\(false\)"/,
      /(?<![\w:-])@click="requestServerModeChange\(true\)"/,
      /(?<![\w:-])class="settings-server-mode"/,
      '<h4',
    ],
    scope: /<div class="settings-header-left">([\s\S]*?)<div class="settings-header-actions">/,
    note: '[lint-guard 162c-test_settings_server_mode_segmented_in_header] 使用者想切伺服器模式 → 單機|伺服器 膠囊的兩顆按鈕若沒接 requestServerModeChange(false/true)，點了沒反應，無法開關區網存取 — 遷自 test_contract_api_routes.py' },
  { file: 'web/templates/settings.html', kind: 'structure-count',
    pattern: 'data-mode=', count: 2,
    scope: /<div class="settings-header-left">([\s\S]*?)<div class="settings-header-actions">/,
    note: '[lint-guard 162c-test_settings_server_mode_segmented_in_header] 使用者想切伺服器模式 → 單機|伺服器 膠囊的兩顆按鈕若沒接 requestServerModeChange(false/true)，點了沒反應，無法開關區網存取 — 遷自 test_contract_api_routes.py' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: /(?<![\w:-])class="settings-server-mode"/,
    scope: /<div class="settings-header-actions">([\s\S]*)/,
    note: '[lint-guard 162c-test_settings_server_mode_segmented_in_header] 使用者想切伺服器模式 → 單機|伺服器 膠囊的兩顆按鈕若沒接 requestServerModeChange(false/true)，點了沒反應，無法開關區網存取 — 遷自 test_contract_api_routes.py' },

  { file: 'web/templates/settings.html', kind: 'structure-count',
    pattern: /(?<![\w:-])class="settings-server-inline"/, count: 1,
    note: '[lint-guard 162c-test_settings_server_info_banner_xshow_xcloak] 使用者在單機模式 → 若區網連線橫條沒被 x-show="serverMode" 管住，會看到不該有的區網網址（誤導成已對外開放）；少 x-cloak 則開頁瞬間閃一下 — 遷自 test_contract_api_routes.py' },
  { file: 'web/templates/settings.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'settings-server-inline',
    required: [/(?<![\w:-])x-show="serverMode"/, /(?<![\w:-])x-cloak(?=[\s>=])/],
    note: '[lint-guard 162c-test_settings_server_info_banner_xshow_xcloak] 使用者在單機模式 → 若區網連線橫條沒被 x-show="serverMode" 管住，會看到不該有的區網網址（誤導成已對外開放）；少 x-cloak 則開頁瞬間閃一下 — 遷自 test_contract_api_routes.py' },

  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w.])settings\.server_info\.warning(?![\w.])/,
    note: '[lint-guard 162c-test_settings_server_info_warning_key] 使用者開啟伺服器模式 → 若安全警語被拿掉，不會被告知區網內任何裝置都連得進來 — 遷自 test_contract_api_routes.py' },

  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])@click="copyServerUrl\(\)"/,
    note: '[lint-guard 162c-test_settings_server_info_copy_button] 使用者按區網網址旁的複製鈕 → 剪貼簿要真的寫入網址 — 遷自 test_contract_api_routes.py（D-C 誤刪補回，Codex T4 P2）' },

  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      'settings.server_info.listener_down',
      /(?<![\w:-])x-if="!serverUrl\(\) && lanIp"/,
      'settings.server_info.no_lan_ip_with_port',
      /(?<![\w:-])x-if="!serverUrl\(\) && !lanIp && lanPort"/,
      /(?<![\w:-])x-if="!serverUrl\(\) && !lanIp && !lanPort"/,
    ],
    note: '[lint-guard 162c-test_settings_server_info_distinguishes_listener_down_from_no_ip] 使用者的區網 listener 沒起來（自動啟動失敗）→ 若橫條誤報「取不到 IP」，會去查網路而不是重啟，白排查 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: '/api/config/general/server_mode',
    note: '[lint-guard 162c-test_state_config_server_mode_put_endpoint] 使用者切單機|伺服器 → 若 PUT 路徑對不上後端 /api/config/general/server_mode，設定沒存下來，重開又變回去 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'this.lanPort',
    note: '[lint-guard 162c-test_state_config_server_url_uses_lan_port] 使用者要在別台裝置連進來 → 顯示的網址若用桌面本機 port 而非 LAN port，別台連不上 — 遷自 test_contract_api_routes.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string',
    pattern: 'window.location.port',
    note: '[lint-guard 162c-test_state_config_server_url_uses_lan_port] 使用者要在別台裝置連進來 → 顯示的網址若用桌面本機 port 而非 LAN port，別台連不上 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'result.lan_port',
    note: '[lint-guard 162c-test_state_config_set_server_mode_reads_lan_port] 使用者切到伺服器模式後 → 若沒讀回後端回的 lan_port，橫條不顯示網址，要重新整理才出現 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: ['result.lan_ip', 'this.lanIp = result.lan_ip'],
    note: '[lint-guard 162c-test_state_config_set_server_mode_reads_lan_ip] 使用者切到伺服器模式後 → 若沒讀回後端回的 lan_ip，橫條網址用舊值或空白 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: '/api/config/general/lan-port',
    note: '[lint-guard 162c-test_state_config_load_config_fetches_lan_port] 使用者重新整理設定頁 → 若不再補抓 lan-port，橫條網址消失，要重切模式才恢復 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: ['j.lan_ip', 'this.lanIp = j.lan_ip'],
    note: '[lint-guard 162c-test_state_config_load_config_reads_lan_ip_from_lan_port_endpoint] 使用者重新整理設定頁 → 若沒讀 lan-port 回應的 lan_ip，橫條 IP 空白或舊值 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: [
      'settings.server_info.disable_failed',
      'settings.server_info.toggle_failed',
      "val ? 'settings.server_info.toggle_failed' : 'settings.server_info.disable_failed'",
      'remote_forbidden',
      'settings.server_info.remote_only',
    ],
    note: '[lint-guard 162c-test_state_config_set_server_mode_failure_direction_aware] 使用者關閉伺服器模式失敗 → 若 toast 仍說「無法啟動」會被誤導；遠端裝置嘗試切換時只看到「請稍後再試」，不知道只有本機能切 — 遷自 test_contract_api_routes.py' },

  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'value: !!val',
    note: '[lint-guard 162c-test_state_config_set_server_mode_sends_boolean] 使用者切伺服器模式 → 若送字串而非布林，後端嚴格布林 gate 回 400，開關切不動 — 遷自 test_contract_api_routes.py' },

  // ---- 162c-B21 迄 ----
  //
  //
  //
  // ---- 162c-B22 起 ----
  // （162c-B22 專屬子區段：只在此兩行之間追加）

  // 162c: TestServerModeToggleGuard
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'result.lan_ip ?? null',
    note: '[lint-guard 162c-test_set_server_mode_lan_ip_nullish_uses_null_not_stale] 使用者開啟後偵測不到 IP → 橫條若仍顯示舊 IP，使用者複製到失效網址 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string',
    pattern: 'result.lan_ip ?? this.lanIp',
    note: '[lint-guard 162c-test_set_server_mode_lan_ip_nullish_uses_null_not_stale] 使用者開啟後偵測不到 IP → 橫條若仍顯示舊 IP，使用者複製到失效網址 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'j.lan_ip ?? null',
    note: '[lint-guard 162c-test_load_config_lan_ip_nullish_uses_null_not_stale] 使用者重新整理後偵測不到 IP → 橫條若仍顯示舊 IP，使用者複製到失效網址 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string',
    pattern: 'j.lan_ip ?? this.lanIp',
    note: '[lint-guard 162c-test_load_config_lan_ip_nullish_uses_null_not_stale] 使用者重新整理後偵測不到 IP → 橫條若仍顯示舊 IP，使用者複製到失效網址 — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestScannerClearCache
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: ['clearCache()', '/api/gallery/cache', /method:\s*'DELETE'/],
    note: '[lint-guard 162c-test_scanner_clear_cache_js_contains] 使用者在掃描頁按「清除快取」確認 → 若沒打到後端 DELETE /api/gallery/cache，快取沒清，縮圖仍是舊的要再按 — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestAliasLiveQueryGuard
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /async\s+_fetchLiveAliases\s*\([^)]*\)\s*\{/,
    note: '[lint-guard 162c-test_fetch_live_aliases_method_exists] 使用者開女優燈箱 → 別名若沒即時重抓，看到的是舊快照別名 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: '/api/actress-aliases/',
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?_fetchLiveAliases\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_fetch_live_aliases_method_exists] 使用者開女優燈箱 → 別名若沒即時重抓，看到的是舊快照別名 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: [
      /(?:resp|response)\.status\s*===\s*200/,
      /Object\.assign\s*\(/,
      /aliases\s*:/,
    ],
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?_fetchLiveAliases\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_200_branch_uses_object_assign] 使用者看別名時 live 結果回來 → 若不用 Object.assign 產生新物件，燈箱別名欄不更新（Alpine 反應性），仍是舊別名 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: [
      /\btry\s*\{/,
      /\bcatch\s*\(/,
      /if\s*\(\s*(?:resp|response)\.status\s*===\s*200\s*\)\s*\{[^}]*?Object\.assign/,
    ],
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?_fetchLiveAliases\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_fallback_preserves_snapshot_on_error] 使用者查別名逾時／404 → 若覆蓋了快照，燈箱別名欄變空，別名「不見」 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'structure-count',
    pattern: /_fetchLiveAliases\s*\(/,
    min: 2,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?openActressLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_callsites_in_open_actress_and_hero] 使用者開女優燈箱（首次進入或切換女優、或從 hero card 進）→ 若少了即時重抓呼叫，別名不更新 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /_fetchLiveAliases\s*\(/,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?openHeroCardLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_callsites_in_open_actress_and_hero] 使用者開女優燈箱（首次進入或切換女優、或從 hero card 進）→ 若少了即時重抓呼叫，別名不更新 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /_fetchLiveAliases\s*\(/,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?prevActressLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_prev_next_actress_lightbox_refetch_aliases] 使用者用方向鍵切換女優 → 若不重抓別名，看到的是上一位的舊快照 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /_fetchLiveAliases\s*\(/,
    scope: { anchor: /(?:^|\n)\s*(?:async\s+)?nextActressLightbox\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_prev_next_actress_lightbox_refetch_aliases] 使用者用方向鍵切換女優 → 若不重抓別名，看到的是上一位的舊快照 — 遷自 test_contract_api_routes.py',
  },

  // 162c: TestJellyfinCheckManualGuard
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string',
    pattern: /this\.loadStats\(\);\s*this\.checkJellyfinImages\(\)/,
    note: '[lint-guard 162c-test_no_auto_trigger_in_init] 使用者開掃描頁／生成列表完成 → 若又自動跑 Jellyfin 圖檢查，大片庫被掃一輪（慢、佔 NAS）（test_no_auto_trigger_after_generate） — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: /(?<![\w:-])@click="checkJellyfinImages\(\)"/,
    note: '[lint-guard 162c-test_trigger_button_click_handler] 使用者想補 Jellyfin 圖 → 自動觸發已拿掉，按鈕若沒接 @click 就完全無法啟動檢查，補圖功能變不可用 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<div\b(?=[^>]*(?<![\w:-])class="[^"]*\bnfo-update-row\b)(?=[^>]*(?<![\w:-])x-show="[^"]*jellyfinImageVisible)(?=[^>]*(?<![\w:-])x-show="[^"]*config)[^>]*>/,
    required: [
      /\s(?<![\w:-])x-show="[^"]*\['jellyfin', 'emby', 'kodi'\]\.includes\(config\?\.scraper\?\.external_manager\)[^"]*"/,
      /\s(?<![\w:-])x-show="[^"]*!jellyfinImageVisible[^"]*"/,
    ],
    note: '[lint-guard 162c-test_trigger_row_xshow_uses_jellyfin_image_visible] 使用者沒設 Jellyfin／Emby／Kodi（或設定尚未載入）→ 若觸發列用 fail-open 條件，仍看到「檢查 Jellyfin 圖」鈕，按下去打不存在的流程 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'forbidden-string',
    pattern: [
      "=== 'jellyfin_emby'",
      "config?.scraper?.external_manager !== 'off' && !jellyfinImageVisible",
      "config?.scraper?.jellyfin_mode && !jellyfinImageVisible",
    ],
    note: '[lint-guard 162c-test_trigger_row_xshow_uses_jellyfin_image_visible] 使用者沒設 Jellyfin／Emby／Kodi（或設定尚未載入）→ 若觸發列用 fail-open 條件，仍看到「檢查 Jellyfin 圖」鈕，按下去打不存在的流程 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: [
      'async checkJellyfinImages()',
      "!['jellyfin', 'emby', 'kodi'].includes(this.config?.scraper?.external_manager)",
    ],
    note: '[lint-guard 162c-test_check_jellyfin_method_gate_is_fail_closed] 使用者沒設外部管理器或設定尚未載入就觸發 → 若方法端 gate 是 fail-open，會對沒有 Jellyfin 的環境打 /jellyfin-check 而報錯 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/static/js/pages/scanner/state-scan.js', kind: 'forbidden-string',
    pattern: "this.config?.scraper?.external_manager === 'off'",
    note: '[lint-guard 162c-test_check_jellyfin_method_gate_is_fail_closed] 使用者沒設外部管理器或設定尚未載入就觸發 → 若方法端 gate 是 fail-open，會對沒有 Jellyfin 的環境打 /jellyfin-check 而報錯 — 遷自 test_contract_api_routes.py',
  },
  {
    file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: ["jellyfinCheckState === 'done'", 'jellyfin_check_done_ok'],
    note: '[lint-guard 162c-test_trigger_row_done_state_text_present] 使用者按檢查且全部沒問題 → 若 done 狀態沒有「已檢查沒問題」文字，畫面像沒反應，不知檢查完沒 — 遷自 test_contract_api_routes.py',
  },

  // ---- 162c-B22 迄 ----
  //
  //
  //
  // ---- 162c-B23 起 ----
  // （162c-B23 專屬子區段：只在此兩行之間追加）

  // 162c: TestJellyfinCheckManualGuard
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: [
      'this.jellyfinImageVisible = false',
      'this.jellyfinImageCount = 0',
      "this.jellyfinCheckState = 'idle'",
    ],
    scope: { anchor: /async\s+runJellyfinImageUpdate\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    note: '[lint-guard 162c-test_jellyfin_update_done_resets_check_state] 補圖完成後重設待補數量與檢查狀態 — 遷自 test_contract_api_routes.py' },

  // 162c: TestNavigateLoadMore
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string',
    pattern: 'async navigate(delta)',
    note: '[lint-guard 162c-test_navigate_js_contains] 搜尋詳情 navigate 必須是 async — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'required-string',
    pattern: ["await this.loadMore('detail')", 'this.currentIndex = result.oldLength'],
    scope: { anchor: /async navigate\(delta\) \{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_navigate_js_contains] 搜尋詳情 navigate 末頁須 loadMore 並跳到新載入首筆 — 遷自 test_contract_code_shape.py' },

  // 162c: TestNextLightboxLoadMore
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: 'async nextLightboxVideo()',
    note: '[lint-guard 162c-test_next_lightbox_js_contains] 搜尋燈箱 nextLightboxVideo 必須是 async — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: [
      "await this.loadMore('lightbox')",
      'this.currentIndex = result.oldLength',
      'this.lightboxIndex = result.oldLength',
    ],
    count: 2,
    scope: { anchor: /async nextLightboxVideo\(\) \{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_next_lightbox_js_contains] 搜尋燈箱 nextLightboxVideo 兩條越界路徑皆須 loadMore 並更新 index — 遷自 test_contract_code_shape.py' },

  // 162c: TestCoverStateGuard
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: /^[ \t]*_coverRequestId\s*:\s*0\s*,/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_base_has_cover_request_id_field] 使用者切換沿用同封面 URL 的候選 → 計數器初值遺失成 NaN，快取補救 callback 提早返回，封面一直被 loading 遮住 — 遷自 test_contract_code_shape.py（Codex pre-merge P2 補回）' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: '_coverRequestId++',
    scope: { anchor: /_resetCoverState\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_reset_cover_state_increments_request_id] _resetCoverState 必須遞增 _coverRequestId 作廢進行中回調 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: ['_clearTimer', 'coverRetry'],
    scope: { anchor: /_resetCoverState\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_reset_cover_state_calls_clear_timer] _resetCoverState 必須清掉 coverRetry 計時器 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'forbidden-string',
    pattern: /^(?!.*_resetCoverState).*\bcoverError\s*=\s*['"]['"]\s*;/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_no_bare_cover_error_reset] file-list 禁止裸 coverError = \'\' 重置（須走 _resetCoverState） — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'forbidden-string',
    pattern: /^(?!.*_resetCoverState).*\bcoverError\s*=\s*['"]['"]\s*;/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_no_bare_cover_error_reset] navigation 禁止裸 coverError = \'\' 重置（須走 _resetCoverState） — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'forbidden-string',
    pattern: /^(?!.*_resetCoverState).*\bcoverError\s*=\s*['"]['"]\s*;/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_no_bare_cover_error_reset] search-flow 禁止裸 coverError = \'\' 重置（須走 _resetCoverState） — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'structure-count',
    pattern: /\b_resetCoverState\s*\(/, min: 8,
    stripLineComments: true,
    note: '[lint-guard 162c-test_file_list_reset_cover_state_count] 使用者在搜尋頁換檔案或切換列表狀態 → 某條路徑的封面重置呼叫被刪，前一片封面的重試計時器未清、載入旗標未歸零，新片封面可能被誤標載入失敗或不顯示載入中（_resetCoverState 呼叫 ≥ 8 次） — 遷自 test_contract_code_shape.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'structure-count',
    pattern: /\b_resetCoverState\s*\(/, min: 2,
    stripLineComments: true,
    note: '[lint-guard 162c-test_navigation_reset_cover_state_count] 使用者在搜尋頁按上一個／下一個候選或載入更多 → 封面重置呼叫被刪，前一片封面的重試計時器到點把新片誤標載入失敗（_resetCoverState 呼叫 ≥ 2 次） — 遷自 test_contract_code_shape.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'structure-count',
    pattern: /\b_resetCoverState\s*\(/, min: 4,
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_flow_reset_cover_state_count] 使用者搜尋番號（含備援／fallback 結果）→ 封面重置呼叫被刪，上一次搜尋的封面狀態殘留在新結果上（_resetCoverState 呼叫 ≥ 4 次） — 遷自 test_contract_code_shape.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'structure-count',
    pattern: /\b_resetCoverState\s*\(/, min: 1,
    stripLineComments: true,
    note: '[lint-guard 162c-test_grid_mode_reset_cover_state] 使用者從網格切回詳情 → 封面重置呼叫被刪，短暫殘留前一片封面狀態（_resetCoverState 呼叫 ≥ 1 次） — 遷自 test_contract_code_shape.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'structure-count',
    pattern: /\b_resetCoverState\s*\(/, min: 1,
    stripLineComments: true,
    note: '[lint-guard 162c-test_batch_reset_cover_state] 使用者按全部刮削 → 封面重置呼叫被刪，短暫殘留前一片封面狀態（_resetCoverState 呼叫 ≥ 1 次） — 遷自 test_contract_code_shape.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/pages/search/state/persistence.js', kind: 'structure-count',
    pattern: /\b_resetCoverState\s*\(/, min: 1,
    stripLineComments: true,
    note: '[lint-guard 162c-test_persistence_reset_cover_state] 使用者重新開啟頁面還原搜尋狀態 → 封面重置呼叫被刪，短暫殘留前一片封面狀態（_resetCoverState 呼叫 ≥ 1 次） — 遷自 test_contract_code_shape.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: 'getAttribute',
    scope: { anchor: /handleCoverError\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_cover_error_has_get_attribute_guard] handleCoverError 必須用 getAttribute(\'src\') 做 stale 比對 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: 'coverUrl',
    scope: { anchor: /handleCoverError\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_cover_error_has_cover_url_comparison] handleCoverError 必須比對 coverUrl — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: '_coverRequestId',
    scope: { anchor: /handleCoverError\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_cover_error_has_request_id_guard] handleCoverError 重試回調必須核對 _coverRequestId — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: ['_setTimer', 'coverRetry'],
    stripLineComments: true,
    note: '[lint-guard 162c-test_cover_retry_uses_set_timer] cover 重試必須用 _setTimer(\'coverRetry\') 而非 raw setTimeout — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/search.html', kind: 'required-string',
    pattern: '_coverLoaded = true',
    note: '[lint-guard 162c-test_load_handler_sets_cover_loaded] 封面 @load 必須設 _coverLoaded = true — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/ui.js', kind: 'required-string',
    pattern: '_resetCoverState',
    scope: { anchor: /async function switchSource\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_switch_source_reset_cover_state] switchSource 替換結果時必須 _resetCoverState — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'order',
    items: [
      { pattern: 'if (!expected) return;' },
      { pattern: 'if (!this._coverRetried) {' },
    ],
    scope: { anchor: /handleCoverError\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_cover_error_guards_empty_cover_url] handleCoverError 空 coverUrl early return 必須在 _coverRetried 檢查之前 — 遷自 test_contract_code_shape.py' },

  // 162c: TestSearchAllRaceGuard
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'forbidden-string',
    pattern: [
      'this.currentFileIndex',
      'this.currentIndex',
      'this.displayMode',
      'window.SearchUI.showState',
      'this.searchResults',
    ],
    scope: { anchor: /_searchFileBackground\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_file_background_no_shared_state_writes] _searchFileBackground 不得寫共享 UI 狀態 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string',
    pattern: ['file.searchResults', 'file.searched'],
    scope: { anchor: /_searchFileBackground\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_file_background_no_shared_state_writes] _searchFileBackground 必須寫入 file.searchResults／file.searched — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string',
    pattern: '_searchFileBackground(',
    scope: { anchor: /async searchAll\s*\(\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_all_uses_background_search] searchAll 必須呼叫 _searchFileBackground — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'forbidden-string',
    pattern: 'switchToFile',
    scope: { anchor: /Promise\.all\(chunk\.map\(async \(file\) => \{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_all_no_direct_switch_to_file_in_promise_all] Promise.all(chunk.map) 內不得直接 switchToFile — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'forbidden-string',
    pattern: ['switchToFile(', 'showToast(', 'alert('],
    scope: { anchor: /_searchFileBackground\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_file_background_no_ui_side_effects] _searchFileBackground 不得有 UI 副作用 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/file-list.js', kind: 'required-string',
    pattern: ['settle', 'originalClose'],
    scope: { anchor: /_searchFileBackground\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_file_background_has_close_wrapper] _searchFileBackground 必須有 close-wrapper（settle／originalClose） — 遷自 test_contract_code_shape.py' },

  // 162c: TestLightboxAnimationGuard
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: ['getById', 'playLightboxSwitch'],
    note: '[lint-guard 162c-test_search_js_contains] 搜尋燈箱須有 getById 殺動畫與 playLightboxSwitch — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: /lightboxIndex\s*===\s*index/,
    scope: { anchor: /^\s*openLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_js_contains] openLightbox 同 index 必須 no-op — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'order',
    items: [
      { pattern: 'this.sampleGalleryOpen' },
      { pattern: 'closeSampleGallery' },
      { pattern: 'this.lightboxOpen' },
    ],
    scope: { anchor: /^\s*handleKeydown\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_search_js_contains] handleKeydown 須先關 sampleGallery 再處理 lightbox — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: ['_killLightboxTimelines', 'playLightboxSwitch'],
    stripLineComments: true, note: '[lint-guard 162c-test_showcase_js_contains] 影片牆燈箱須有 _killLightboxTimelines 與 playLightboxSwitch — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /lightboxIndex\s*===\s*index/,
    scope: { anchor: /^\s*openLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_showcase_js_contains] showcase openLightbox 同 index 必須 no-op — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_killLightboxTimelines',
    scope: { anchor: /^\s*searchFromMetadata\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_showcase_js_contains] searchFromMetadata 必須先 _killLightboxTimelines — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'order',
    items: [
      { pattern: '_killLightboxTimelines' },
      { pattern: 'lightboxOpen = false' },
    ],
    scope: { anchor: /^\s*searchFromMetadata\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_showcase_js_contains] searchFromMetadata 須先殺動畫再關 lightbox — 遷自 test_contract_code_shape.py' },

  // 162c: TestLightboxStateFirstGuard
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'order',
    items: [
      { pattern: /this\.lightboxIndex\s*=(?!=)/, occurrence: 'last' },
      { pattern: 'playLightboxSwitch', occurrence: 'last' },
    ],
    scope: { anchor: /^\s*(?:async\s+)?prevLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nav_state_first_search] prevLightboxVideo 必須先更新 lightboxIndex 再播動畫 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'order',
    items: [
      { pattern: /this\.lightboxIndex\s*=(?!=)/, occurrence: 'last' },
      { pattern: 'playLightboxSwitch', occurrence: 'last' },
    ],
    scope: { anchor: /^\s*(?:async\s+)?nextLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nav_state_first_search] nextLightboxVideo 必須先更新 lightboxIndex 再播動畫 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'order',
    items: [
      { pattern: /this\.lightboxIndex\s*=(?!=)|_setLightboxIndex\(/, occurrence: 'last' },
      { pattern: 'playLightboxSwitch', occurrence: 'last' },
    ],
    scope: { anchor: /^\s*(?:async\s+)?prevLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nav_state_first_showcase] showcase prevLightboxVideo 必須先更新 lightboxIndex 再播動畫 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'order',
    items: [
      { pattern: /this\.lightboxIndex\s*=(?!=)|_setLightboxIndex\(/, occurrence: 'last' },
      { pattern: 'playLightboxSwitch', occurrence: 'last' },
    ],
    scope: { anchor: /^\s*(?:async\s+)?nextLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nav_state_first_showcase] showcase nextLightboxVideo 必須先更新 lightboxIndex 再播動畫 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'forbidden-string',
    pattern: 'onMidpoint',
    scope: { anchor: /^\s*(?:async\s+)?prevLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_switch_onmidpoint_no_index_update] search prevLightboxVideo 不得含 onMidpoint — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'forbidden-string',
    pattern: 'onMidpoint',
    scope: { anchor: /^\s*(?:async\s+)?nextLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_switch_onmidpoint_no_index_update] search nextLightboxVideo 不得含 onMidpoint — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: 'onMidpoint',
    scope: { anchor: /^\s*(?:async\s+)?prevLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_switch_onmidpoint_no_index_update] showcase prevLightboxVideo 不得含 onMidpoint — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: 'onMidpoint',
    scope: { anchor: /^\s*(?:async\s+)?nextLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_switch_onmidpoint_no_index_update] showcase nextLightboxVideo 不得含 onMidpoint — 遷自 test_contract_code_shape.py' },
  // ---- 162c-B23 迄 ----
  //
  //
  //
  // ---- 162c-B24 起 ----
  // （162c-B24 專屬子區段：只在此兩行之間追加）
  // 162c: TestLightboxStateFirstGuard
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'order',
    items: [
      { pattern: 'lightboxIndex !== index' },
      { pattern: /lightboxIndex = index(?!=)|_setLightboxIndex\(index\)/ },
      { pattern: 'playLightboxSwitch' },
    ],
    scope: { anchor: /^\s*openLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_open_lightbox_switch_state_first] 使用者在燈箱開著時點另一張卡切換 → 索引要先更新再播切換動畫；順序錯會閃爍 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'order',
    items: [
      { pattern: 'lightboxIndex !== index' },
      { pattern: /lightboxIndex = index(?!=)|_setLightboxIndex\(index\)/ },
      { pattern: 'playLightboxSwitch' },
    ],
    scope: { anchor: /^\s*openLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_open_lightbox_switch_state_first] 使用者在燈箱開著時點另一張卡切換 → 索引要先更新再播切換動畫；順序錯會閃爍 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: '_lightboxGeneration',
    scope: { anchor: /^\s*openLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nexttick_has_generation_guard] 使用者關燈箱／按 ESC 之後 → 還沒執行的動畫 callback 必須失效，否則會把 _lightboxAnimating 重設成 true，燈箱按鈕全部沒反應 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: '_lightboxGeneration',
    scope: { anchor: /^\s*(?:async\s+)?prevLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nexttick_has_generation_guard] 使用者關燈箱／按 ESC 之後 → 還沒執行的動畫 callback 必須失效，否則會把 _lightboxAnimating 重設成 true，燈箱按鈕全部沒反應 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: '_lightboxGeneration',
    scope: { anchor: /^\s*(?:async\s+)?nextLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nexttick_has_generation_guard] 使用者關燈箱／按 ESC 之後 → 還沒執行的動畫 callback 必須失效，否則會把 _lightboxAnimating 重設成 true，燈箱按鈕全部沒反應 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_lightboxGeneration',
    scope: { anchor: /^\s*openLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nexttick_has_generation_guard] 使用者關燈箱／按 ESC 之後 → 還沒執行的動畫 callback 必須失效，否則會把 _lightboxAnimating 重設成 true，燈箱按鈕全部沒反應 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_lightboxGeneration',
    scope: { anchor: /^\s*(?:async\s+)?prevLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nexttick_has_generation_guard] 使用者關燈箱／按 ESC 之後 → 還沒執行的動畫 callback 必須失效，否則會把 _lightboxAnimating 重設成 true，燈箱按鈕全部沒反應 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_lightboxGeneration',
    scope: { anchor: /^\s*(?:async\s+)?nextLightboxVideo\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_nexttick_has_generation_guard] 使用者關燈箱／按 ESC 之後 → 還沒執行的動畫 callback 必須失效，否則會把 _lightboxAnimating 重設成 true，燈箱按鈕全部沒反應 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/grid-mode.js', kind: 'required-string',
    pattern: '_lightboxGeneration++',
    scope: { anchor: /^\s*closeLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_close_increments_generation] 使用者關燈箱／離開頁面／點 metadata 搜尋 → 必須讓排隊中的動畫 callback 失效，否則殘留 callback 之後把燈箱鎖死 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_lightboxGeneration++',
    scope: { anchor: /^\s*closeLightbox\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_close_increments_generation] 使用者關燈箱／離開頁面／點 metadata 搜尋 → 必須讓排隊中的動畫 callback 失效，否則殘留 callback 之後把燈箱鎖死 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_lightboxGeneration++',
    scope: { anchor: /^\s*searchFromMetadata\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_close_increments_generation] 使用者關燈箱／離開頁面／點 metadata 搜尋 → 必須讓排隊中的動畫 callback 失效，否則殘留 callback 之後把燈箱鎖死 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: '_lightboxGeneration++',
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_close_increments_generation] 使用者關燈箱／離開頁面／點 metadata 搜尋 → 必須讓排隊中的動畫 callback 失效，否則殘留 callback 之後把燈箱鎖死 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: '_lightboxGeneration++',
    scope: { anchor: /cleanup:\s*\(\)/, window: 500 },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_close_increments_generation] 使用者關燈箱／離開頁面／點 metadata 搜尋 → 必須讓排隊中的動畫 callback 失效，否則殘留 callback 之後把燈箱鎖死 — 遷自 test_contract_code_shape.py' },

  // 162c: TestShowcaseReactiveScopeGuard
  { file: { dir: 'web/static/js/pages/showcase', ext: ['.js'] }, kind: 'forbidden-string',
    pattern: /^\s*(?:videos|filteredVideos)\s*:/m,
    stripLineComments: true,
    note: '[lint-guard 162c-test_guard1_no_videos_in_return_object] 使用者開影片牆（數千部片的片庫）→ 大陣列若放進 Alpine 響應式物件，載入與篩選明顯變慢甚至卡頓 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: [/^\s*videoCount\s*:/m, /^\s*filteredCount\s*:/m],
    note: '[lint-guard 162c-test_guard2_has_count_scalars] 使用者看影片牆上方的總片數／篩選後片數 → 沒有 videoCount／filteredCount 純量就顯示 0 或不更新 — 遷自 test_contract_code_shape.py' },
  { file: { dir: 'web/static/js/pages/showcase', ext: ['.js'] }, kind: 'forbidden-string',
    pattern: 'get currentLightboxVideo()',
    note: '[lint-guard 162c-test_guard3_no_getter_currentLightboxVideo] 使用者開影片牆燈箱 → currentLightboxVideo 若是 getter 會每次讀取重算並打穿手動更新的響應式，燈箱內容不更新或卡 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /^\s*currentLightboxVideo\s*:/m,
    note: '[lint-guard 162c-test_guard3_no_getter_currentLightboxVideo] 使用者開影片牆燈箱 → currentLightboxVideo 若是 getter 會每次讀取重算並打穿手動更新的響應式，燈箱內容不更新或卡 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: ['videos.length', 'filteredVideos.length'],
    note: '[lint-guard 162c-test_guard4_no_videos_length_in_template] 使用者看影片牆頁面上的片數 → 模板若還引用已移出響應式的 videos.length，數量永遠顯示 0 或舊值 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: /(?<!showcase\.unit\.)\bvideos\b/,
    note: '[lint-guard 162c-test_guard5_no_bare_videos_in_template] 使用者看影片牆 → 模板若直接引用已不在響應式範圍的 videos／filteredVideos，畫面不會更新 — 遷自 test_contract_code_shape.py' },

  // 162c: TestExternalManagerSwitchModeGuard
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])@click="requestExternalManagerChange\('off'\)"/,
      /(?<![\w:-])@click="requestExternalManagerChange\('jellyfin'\)"/,
      /(?<![\w:-])@click="requestExternalManagerChange\('emby'\)"/,
      /(?<![\w:-])@click="requestExternalManagerChange\('kodi'\)"/,
    ],
    scope: /settings-form-row--external-manager[\s\S]*?(?<![\w:-])class="settings-sources-segmented" role="group"([\s\S]*?)<\/div>/,
    note: '[lint-guard 162c-test_segmented_buttons_call_request_method] 使用者在設定頁切換 Jellyfin／Emby／Kodi／預設模式 → 按鈕必須走攔截方法跳確認；若直接寫 form，有離線來源時不經警告就移除唯讀來源與其媒體卡 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: [
      /(?<![\w:-])@click="form\.externalManager = 'off'"/,
      /(?<![\w:-])@click="form\.externalManager = 'jellyfin'"/,
      /(?<![\w:-])@click="form\.externalManager = 'emby'"/,
      /(?<![\w:-])@click="form\.externalManager = 'kodi'"/,
    ],
    scope: /settings-form-row--external-manager[\s\S]*?(?<![\w:-])class="settings-sources-segmented" role="group"([\s\S]*?)<\/div>/,
    note: '[lint-guard 162c-test_segmented_buttons_call_request_method] 使用者在設定頁切換 Jellyfin／Emby／Kodi／預設模式 → 按鈕必須走攔截方法跳確認；若直接寫 form，有離線來源時不經警告就移除唯讀來源與其媒體卡 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /<dialog[^>]*?(?<![\w:-])@keydown\.escape\.window="(?=[^"]*\bswitchModeConfirmOpen\b)(?=[^"]*\bcancelSwitchMode\(\))[^"]*"/,
    note: '[lint-guard 162c-test_switch_mode_confirm_modal_exists] 使用者切換模式時跳出的破壞性確認框 → 缺確認／取消接線就無法確認或取消，缺 count 插值就不知道會移除幾個來源 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /<dialog[^>]*?(?<![\w:-]):class="(?=[^"]*'modal-open')(?=[^"]*\bswitchModeConfirmOpen\b)[^"]*"/,
    note: '[lint-guard 162c-test_switch_mode_confirm_modal_exists] 使用者切換模式時跳出的破壞性確認框 → 缺確認／取消接線就無法確認或取消，缺 count 插值就不知道會移除幾個來源 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ['btn-error', 'confirmSwitchMode()', 'cancelSwitchMode()', 'settings.switch_mode_confirm.body', 'pendingOfflineCount'],
    scope: /<dialog[^>]*switchModeConfirmOpen[\s\S]*?<\/dialog>/,
    note: '[lint-guard 162c-test_switch_mode_confirm_modal_exists] 使用者切換模式時跳出的破壞性確認框 → 缺確認／取消接線就無法確認或取消，缺 count 插值就不知道會移除幾個來源 — 遷自 test_contract_code_shape.py' },
  { file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: ['btn-primary', '風味'],
    scope: /<dialog[^>]*switchModeConfirmOpen[\s\S]*?<\/dialog>/,
    note: '[lint-guard 162c-test_switch_mode_confirm_modal_exists] 使用者切換模式時跳出的破壞性確認框 → 缺確認／取消接線就無法確認或取消，缺 count 插值就不知道會移除幾個來源 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: ['this.form.externalManager === val', "fetch('/api/config')", 'readonly === true'],
    scope: { anchor: /requestExternalManagerChange\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_request_method_realtime_fetch_and_guard] 使用者切換模式 → 離線來源數必須即時向後端查；讀舊快照會漏掉本該跳的破壞性確認，直接靜默移除來源 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: ['switch-external-manager', 'this.form.externalManager = val', 'this.savedState.externalManager = val', 'this.scannerDirectories'],
    scope: { anchor: /confirmSwitchMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_confirm_syncs_three_places_single_key_savedstate] 使用者確認切換模式後 → 表單、已存狀態、來源清單必須同步；若整份重拍 savedState，使用者其他尚未儲存的修改會被當成已存 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string',
    pattern: 'savedState = JSON.parse',
    scope: { anchor: /confirmSwitchMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_confirm_syncs_three_places_single_key_savedstate] 使用者確認切換模式後 → 表單、已存狀態、來源清單必須同步；若整份重拍 savedState，使用者其他尚未儲存的修改會被當成已存 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: ['generate_in_progress', 'settings.switch_mode_confirm.generate_in_progress'],
    scope: { anchor: /confirmSwitchMode\s*\([^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_confirm_generate_in_progress_specific_toast] 使用者在列表產生進行中切換模式 → 應看到「請等產生完成再切換」專屬提示；缺了只看到泛用失敗，不知道該等 — 遷自 test_contract_code_shape.py' },
  { file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: [
      /"title"\s*:\s*"[^"]+"/,
      /"body"\s*:\s*"[^"]+"/,
      /"cancel"\s*:\s*"[^"]+"/,
      /"confirm"\s*:\s*"[^"]+"/,
      /"generate_in_progress"\s*:\s*"[^"]+"/,
      /"body"\s*:\s*"[^"]*\{mode\}/,
      /"body"\s*:\s*"[^"]*\{count\}/,
    ],
    scope: { anchor: /"switch_mode_confirm"\s*:\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_zh_tw_switch_mode_confirm_keys] 使用者切換模式看確認框文字 → 缺 key 會顯示空白或原始 key；body 缺 {mode}／{count} 插值就看不到要移除幾個來源 — 遷自 test_contract_code_shape.py' },
  { file: 'locales/zh_TW.json', kind: 'forbidden-string',
    pattern: /"body"\s*:\s*"[^"]*風味/,
    scope: { anchor: /"switch_mode_confirm"\s*:\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_zh_tw_switch_mode_confirm_keys] 使用者切換模式看確認框文字 → 缺 key 會顯示空白或原始 key；body 缺 {mode}／{count} 插值就看不到要移除幾個來源 — 遷自 test_contract_code_shape.py' },

  // 162c: TestVideoApiSafetyStrings
  { file: 'web/routers/scanner.py', kind: 'required-string',
    pattern: /is_path_under_dir\(\s*\w+\s*,\s*normalized_dir_uri\s*\)/,
    note: '[lint-guard 162c-test_scanner_py_safety_strings] 使用者移除某媒體資料夾後重掃 → 該資料夾的影片應從牆上消失；scanner.py 的 is_path_under_dir 判斷是這條行為的一環 — 遷自 test_contract_code_shape.py' },
  { file: 'web/routers/gallery_media.py', kind: 'required-string',
    pattern: [
      'def get_video(',
      'os.path.normpath',
      'get_proxy_extensions(config)',
      'is_path_under_dir(request_uri, form)',
      'def video_player(',
    ],
    note: '[lint-guard 162c-test_gallery_media_py_safety_strings] 使用者在 LAN 內開影片／縮圖 proxy → 路徑必須校驗在已設定資料夾內，否則任何人可讀硬碟其他檔 — 遷自 test_contract_code_shape.py' },

  // 162c: TestWishlistLightboxDispatchOrderGuard
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'order',
    items: [
      { pattern: 'if (this.sampleGalleryOpen) {' },
      { pattern: 'if (this.wishlistLightboxOpen) {' },
      { pattern: 'if (this.lightboxOpen) {' },
    ],
    scope: { anchor: /^\s*handleKeydown\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_handle_keydown_order] 使用者在書籤燈箱疊在劇照／主燈箱之上時按 ESC 或方向鍵 → 應由最上層接走；順序錯了關掉或翻動的是被蓋住的那層 — 遷自 test_contract_code_shape.py' },
  { file: 'web/static/js/pages/search/state/navigation.js', kind: 'order',
    items: [
      { pattern: 'if (this.sampleGalleryOpen) {' },
      { pattern: 'if (this.wishlistLightboxOpen) {' },
      { pattern: 'if (this.lightboxOpen) {' },
    ],
    scope: { anchor: /^\s*handleWheel\s*\([^)]*\)\s*\{/m, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_handle_wheel_order] 使用者在書籤燈箱疊在劇照／主燈箱之上時滾滾輪 → 應由最上層接走；順序錯了被蓋住的那層在捲動 — 遷自 test_contract_code_shape.py' },
  // ---- 162c-B24 迄 ----
  //
  //
  //
  // ---- 162c-B25 起 ----
  // （162c-B25 專屬子區段：只在此兩行之間追加）
  // 162c: TestPartsBinStagedAffordanceGuard
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ['bi-plus-circle', 'plus-icn'],
    scope: /<template x-for="src in partsBinSources"[^>]*>.*?<\/template>/s,
    note: '[lint-guard 162c-test_settings_partsbin_pill_has_plus_icn] Parts Bin pill 可加入 affordance 須含 bi-plus-circle／plus-icn — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'forbidden-string',
    pattern: ['settings-mt-probe-hint', 'mt_probe_hint_title'],
    note: '[lint-guard 162c-test_settings_no_probe_hint_details] settings 不得殘留三因摺疊 probe-hint（mt_probe_hint_title 僅此守；settings-mt-probe-hint 另有 TestMetatubeB4Guard） — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ['slash-icn', 'bi-slash-circle'],
    scope: /<template x-for="src in partsBinSources"[^>]*>.*?<\/template>/s,
    note: '[lint-guard 162c-test_settings_partsbin_pill_slash_icn_retained] Parts Bin pill 不可達態須保留 slash-icn／bi-slash-circle — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/css/components/source-pill.css', kind: 'required-string',
    pattern: 'text-decoration: none',
    scope: /\.source-pill\.is-partsbin\[data-available="true"\]\s+\.pill-name\s*\{([^}]+)\}/,
    note: '[lint-guard 162c-test_css_partsbin_available_true_removes_line_through] partsbin available=true 須取消 pill-name 刪除線 — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/css/components/source-pill.css', kind: 'required-string',
    pattern: 'cursor: pointer',
    scope: /\.source-pill\.is-partsbin\s*\{([^}]+)\}/,
    note: '[lint-guard 162c-test_css_partsbin_cursor_pointer] partsbin pill 須 cursor:pointer 以支援 click-to-promote — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/templates/design_system/settings-components.html', kind: 'forbidden-string',
    pattern: ['rec-star', 'data-rec'],
    note: '[lint-guard 162c-test_ds_d13_no_rec_star_and_has_both_available_states] design-system D.13 不得殘留 rec-star／data-rec — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/templates/design_system/settings-components.html', kind: 'required-string',
    pattern: ['data-available="true"', 'data-available="false"'],
    count: 2,
    note: '[lint-guard 162c-test_ds_d13_no_rec_star_and_has_both_available_states] design-system D.13 須含 available true／false 兩態 demo（各 ≥2；HTML+code 雙份） — 遷自 test_contract_layout.py',
  },

  // 162c: TestPosterCropThresholdAlignment
  // test_showcase_lightbox_fit_covers_899 → M-3 併入 CG-PC-04（同失敗原因：modal-hug 缺 width:100%；不另寫 rule）

  // 162c: TestLightboxCoverSizeGuards
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: /^\s*height\s*:[^;\n]*;/m,
    scope: /\.lightbox-cover\s+img\s*\{([^}]+)\}/,
    note: '[lint-guard 162c-test_lightbox_cover_img_has_explicit_height] .lightbox-cover img 須有明確 height 宣告（行首錨排除註解餵飽） — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/css/pages/showcase/05-lightbox.css', kind: 'required-string',
    pattern: /^\s*height\s*:[^;\n]*;/m,
    scope: /\.lb-full\s*\{([^}]+)\}/,
    note: '[lint-guard 162c-test_lb_full_has_explicit_height] .lb-full 須有明確 height 宣告 — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: ['lightboxCoverFull', 'fullImg.complete', 'fullImg.naturalWidth', '_lbFullLoaded'],
    scope: { anchor: /_refreshLbFullBlurUp\(\) \{/, window: 600 },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_js_has_sameurl_complete_check] 同 URL 快取不重觸發 load → 封面透明：helper 須含 complete-check 四要素 — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_refreshLbFullBlurUp',
    scope: { anchor: /_setLightboxIndex\s*\([^)]*\)\s*\{/, window: 1200 },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_js_has_sameurl_complete_check] 同 URL 快取不重觸發 load → 封面透明：_setLightboxIndex 須委託 helper — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: '_refreshLbFullBlurUp',
    scope: { anchor: /this\.currentLightboxVideo = this\.similarExitVideo/, window: 300 },
    stripLineComments: true,
    note: '[lint-guard 162c-test_lightbox_js_has_sameurl_complete_check] 同 URL 快取不重觸發 load → 封面透明：slip-through 後須呼叫 helper — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: 'cover_full_url',
    scope: { anchor: /this\.similarExitVideo = \{/, window: 600 },
    stripLineComments: true,
    note: '[lint-guard 162c-test_similar_exit_video_has_cover_full_url] 相似探索退出到篩選外片 → 原圖網址缺失封面透明：similarExitVideo 須含 cover_full_url — 遷自 test_contract_layout.py',
  },

  // 162c: TestMobileSimilarDrillFallbackGuard
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /similarExitVideo\s*=\s*null/,
    scope: { anchor: /_setLightboxIndex\s*\(idx\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_set_lightbox_index_clears_similar_exit_video] 手機相似卡切回牆內片 → 獨立旗標殘留禁用上下片：_setLightboxIndex 須清 similarExitVideo — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: [/_videos\s*\.\s*findIndex/, '_similarLastDrilledItem'],
    scope: { anchor: /async\s+closeSimilarMode\s*\(\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_close_similar_mode_fallback_has_videos_tier] 關閉相似探索 → 退場降級丟 metadata：closeSimilarMode 須含 _videos.findIndex 與 _similarLastDrilledItem — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    pattern: ['_silentSwitchLightboxByNumber', /_videos\s*\.\s*findIndex/, /similarExitVideo\s*=/, '_mobileLastDrilledItem', '_refreshLbFullBlurUp'],
    scope: { anchor: /\n\s*_mobileSilentSwitch\s*\(item\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_mobile_silent_switch_three_tier] 手機點相似卡 → 主圖／metadata 不更新：_mobileSilentSwitch 須含三層 silent-switch 與 blur-up — 遷自 test_contract_layout.py',
  },

  // 162c: TestCodexFixes
  {
    file: 'web/static/js/pages/search/state/navigation.js', kind: 'forbidden-string',
    pattern: 'this.currentIndex =',
    scope: { anchor: /async\s+loadMore\s*\(trigger[^)]*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_loadmore_no_currentindex_assignment] 搜尋載入更多 → 目前那片被跳走：loadMore 不得賦值 this.currentIndex — 遷自 test_contract_layout.py',
  },
  {
    file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string',
    pattern: 'includes(this.form.geminiModel)',
    note: '[lint-guard 162c-test_gemini_model_fallback_includes_check] 測試 Gemini 連線而舊 model 已下架 → 無聲失敗：須 includes(this.form.geminiModel) allowlist 檢查 — 遷自 test_contract_layout.py',
  },
  // ---- 162c-B25 迄 ----
  //
  //
  //
  // ---- 162c-B26 起 ----
  // （162c-B26 專屬子區段：只在此兩行之間追加）

  // 162c: TestBatchIntervalGuard
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string',
    pattern: 'this._batchCheckInterval = setInterval',
    note: '[lint-guard 162c-test_batch_check_interval_assigned] 批次搜尋輪詢須具名 setInterval 賦值 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string',
    pattern: 'this._translateCheckInterval = setInterval',
    note: '[lint-guard 162c-test_translate_check_interval_assigned] 翻譯輪詢須具名 setInterval 賦值 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string',
    pattern: 'clearInterval(this._batchCheckInterval)',
    note: '[lint-guard 162c-test_batch_interval_self_clear] 批次搜尋條件成立時自清 _batchCheckInterval — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'required-string',
    pattern: 'clearInterval(this._translateCheckInterval)',
    note: '[lint-guard 162c-test_translate_interval_self_clear] 翻譯條件成立時自清 _translateCheckInterval — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string',
    pattern: 'clearInterval(this._batchCheckInterval)',
    note: '[lint-guard 162c-test_cleanup_clears_batch_interval] 離開搜尋頁須清掉批次輪詢計時器 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string',
    pattern: 'clearInterval(this._translateCheckInterval)',
    note: '[lint-guard 162c-test_cleanup_clears_translate_interval] 離開搜尋頁須清掉翻譯輪詢計時器 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: '_batchCheckInterval',
    note: '[lint-guard 162c-test_base_declares_batch_check_interval] base state 須宣告 _batchCheckInterval — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: '_translateCheckInterval',
    note: '[lint-guard 162c-test_base_declares_translate_check_interval] base state 須宣告 _translateCheckInterval — 遷自 test_contract_lifecycle.py' },

  // 162c: TestTimerListenerGuard
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: "_setTimer('updateCoverHeight'",
    note: '[lint-guard 162c-test_index_uses_set_timer_for_cover_height] searchResults watch 須用 _setTimer 更新封面高 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/main.js', kind: 'forbidden-string',
    pattern: 'setTimeout(() => this._updateCoverHeight()',
    note: '[lint-guard 162c-test_index_no_bare_settimeout_for_cover_height] 禁止裸 setTimeout 更新封面高 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: 'this._pywebviewFilesHandler =',
    note: '[lint-guard 162c-test_index_pywebview_handler_assigned] pywebview-files handler 須具名賦值 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: 'this._resizeHandler =',
    note: '[lint-guard 162c-test_index_resize_handler_assigned] resize handler 須具名賦值 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: "removeEventListener('pywebview-files', this._pywebviewFilesHandler)",
    note: '[lint-guard 162c-test_index_cleanup_removes_pywebview_listener] 離開搜尋頁須移除 pywebview-files 監聽 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string',
    pattern: "removeEventListener('resize', this._resizeHandler)",
    note: '[lint-guard 162c-test_index_cleanup_removes_resize_listener] 離開搜尋頁須移除 resize 監聽 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: '_pywebviewFilesHandler',
    note: '[lint-guard 162c-test_base_declares_pywebview_handler] base state 須宣告 _pywebviewFilesHandler — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/search/state/base.js', kind: 'required-string',
    pattern: '_resizeHandler',
    note: '[lint-guard 162c-test_base_declares_resize_handler] base state 須宣告 _resizeHandler — 遷自 test_contract_lifecycle.py' },

  // 162c: TestAutoFetchDirtyStateGuard
  { file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string',
    pattern: 'this.savedState.geminiModel',
    note: '[lint-guard 162c-test_gemini_fallback_syncs_saved_state] Gemini auto-fallback 後須同步 savedState 以免 isDirty 誤判 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string',
    pattern: 'this.savedState.openaiModel',
    note: '[lint-guard 162c-test_openai_fallback_syncs_saved_state] OpenAI auto-assign 後須同步 savedState 以免 isDirty 誤判 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'use_custom_model: this.openaiUseCustomModel',
    note: '[lint-guard 162c-test_openai_config_saves_use_custom_model] saveConfig 須持久化 use_custom_model — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'config.translate.openai?.use_custom_model',
    note: '[lint-guard 162c-test_openai_config_loads_use_custom_model] loadConfig 須還原 openaiUseCustomModel — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/settings/state-providers.js', kind: 'required-string',
    pattern: "source = 'manual'",
    note: '[lint-guard 162c-test_fetch_openai_models_has_source_param] fetchOpenAIModels 須以 source 區分 auto/manual — 遷自 test_contract_lifecycle.py' },

  // 162c: TestGalleryOutputDirEmptyFollowsDataRoot
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: "config.gallery?.output_dir ?? ''",
    note: '[lint-guard 162c-test_settings_load_preserves_empty_output_dir] loadConfig 須以 ?? \'\' 保留空 output_dir — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'output_dir: this.form.avlistOutputDir.trim(),',
    note: '[lint-guard 162c-test_settings_save_sends_trimmed_output_dir_without_fallback] saveConfig 須送出 trim 後空字串不補 output — 遷自 test_contract_lifecycle.py' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: [
      'this.resolvedGalleryOutputPath = result.resolved?.data_root',
      "resolvedGalleryOutputPath: ''",
    ],
    note: '[lint-guard 162c-test_settings_stores_resolved_gallery_output_path] loadConfig 須存 data_root 並宣告 resolvedGalleryOutputPath 初值 — 遷自 test_contract_lifecycle.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: ':placeholder="resolvedGalleryOutputPath"',
    note: '[lint-guard 162c-test_settings_html_placeholder_binds_resolved_path] 輸出目錄欄須綁 resolvedGalleryOutputPath placeholder — 遷自 test_contract_lifecycle.py' },

  // ---- 162c-B26 迄 ----
  //
  //
  //
  // ---- 162c-B27 起 ----
  // （162c-B27 專屬子區段：只在此兩行之間追加）

  // 162c: TestOpenLocalGuard
  { file: 'web/templates/search.html', kind: 'required-string',
    pattern: 'openLocal(',
    note: '[lint-guard 162c-test_open_local_in_search] 搜尋頁點資料夾圖示 → 模板沒綁 openLocal 所以沒反應 — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/shared/open-local.js', kind: 'required-string',
    pattern: /^export function openLocal\(path\)\s*\{/m,
    note: '[lint-guard 162c-test_open_local_method_exists] 點資料夾 → openLocal 須為一般 function 宣告（非 arrow）以免 this 失效（test_open_local_checks_return_value／test_open_local_cross_platform_path 共用 wired） — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: "from '@/shared/open-local.js'",
    note: '[lint-guard 162c-test_open_local_method_exists] search result-card 須 import shared/open-local.js — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: /^\s*import\s*\{\s*openLocal\s*\}\s*from\s*'@\/shared\/open-local\.js';/m,
    note: '[lint-guard 162c-test_open_local_method_exists] search result-card 須具名 import openLocal — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string',
    pattern: /^\s*openLocal,\s*$/m,
    note: '[lint-guard 162c-test_open_local_method_exists] search result-card 須 shorthand 掛載 openLocal — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: "from '@/shared/open-local.js'",
    note: '[lint-guard 162c-test_open_local_method_exists] showcase state-videos 須 import shared/open-local.js — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /^\s*import\s*\{\s*openLocal\s*\}\s*from\s*'@\/shared\/open-local\.js';/m,
    note: '[lint-guard 162c-test_open_local_method_exists] showcase state-videos 須具名 import openLocal — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /^\s*openLocal,\s*$/m,
    note: '[lint-guard 162c-test_open_local_method_exists] showcase state-videos 須 shorthand 掛載 openLocal — 遷自 test_contract_desktop.py' },
  { file: 'windows/pywebview_api.py', kind: 'required-string',
    pattern: /^\s*def open_folder\(/m,
    note: '[lint-guard 162c-test_open_folder_pywebview_api] 桌面版點資料夾 → pywebview API 須有 def open_folder — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/shared/open-local.js', kind: 'required-string',
    pattern: '.then(async (opened)',
    note: '[lint-guard 162c-test_open_local_checks_return_value] 開啟失敗仍顯示已開啟 → .then 須檢查 opened 回傳值 — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/shared/open-local.js', kind: 'required-string',
    pattern: 'displayPath',
    note: '[lint-guard 162c-test_open_local_cross_platform_path] Windows 剪貼簿路徑須走 displayPath 跨平台格式 — 遷自 test_contract_desktop.py' },

  // 162c: TestJavlibraryPickerT5Guard
  { file: 'web/templates/_advanced_search_bootstrap.html', kind: 'required-string',
    pattern: 'cf_transport_available:',
    note: '[lint-guard 162c-test_bootstrap_cf_transport_available] CF 不可用時 bootstrap 須注入 cf_transport_available — 遷自 test_contract_desktop.py' },
  { file: 'web/app.py', kind: 'required-string',
    pattern: '"cf_transport_available":',
    note: '[lint-guard 162c-test_app_py_get_common_context_cf_transport] get_common_context 須注入 cf_transport_available key — 遷自 test_contract_desktop.py' },
  { file: 'web/app.py', kind: 'required-string',
    pattern: 'get_cf_transport',
    note: '[lint-guard 162c-test_app_py_get_common_context_cf_transport] get_common_context 須查 get_cf_transport — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: /\bisJlUnavailable\s*\(s\)\s*\{/,
    note: '[lint-guard 162c-test_state_rescrape_has_isJlUnavailable] 重刮 modal 呼叫 isJlUnavailable 時 state 須定義該方法 — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/_rescrape_modal.html', kind: 'required-string',
    pattern: /(?<![\w:-]):aria-disabled="isJlUnavailable\(s\)/,
    note: '[lint-guard 162c-test_modal_builtin_pill_jl_unavailable_gate] CF 不可用時 javlibrary 膠囊須 aria-disabled 綁 isJlUnavailable — 遷自 test_contract_desktop.py' },

  // 162c: TestCfPollUnavailableGuard
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'data.unavailable',
    note: '[lint-guard 162c-test_poll_checks_data_unavailable] CF 死掉時前端須讀 data.unavailable 訊號 — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: 'cancelCfPoll',
    scope: { anchor: /data\.unavailable/, window: 200 },
    stripLineComments: true, note: '[lint-guard 162c-test_poll_calls_cancel_cf_poll_on_unavailable] unavailable 分支須呼叫 cancelCfPoll 停輪詢 — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    pattern: ['data.unavailable', 'cancelCfPoll'],
    scope: { anchor: /\b_pollCfThenRetry\s*\(\s*\w+\s*,\s*\w+\s*\)\s*\{/, braceBalanced: true },
    stripLineComments: true,
    note: '[lint-guard 162c-test_unavailable_check_present_in_poll_interval] data.unavailable 與 cancelCfPoll 須同在 _pollCfThenRetry 內 — 遷自 test_contract_desktop.py' },

  // 162c: TestSettingsCloseActionSelect
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /\{%-?\s*if\s+is_windows_desktop\s*-?%\}(?:(?!\{%-?\s*endif\b)[\s\S])*?(?<![\w:-])id="closeAction"/,
    note: '[lint-guard 162c-test_close_action_select_inside_jinja_gate] #closeAction 須在 is_windows_desktop gate 內 — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/settings.html', kind: 'structure-count',
    pattern: /(?<![\w:-])id="closeAction"/,
    count: 1,
    note: '[lint-guard 162c-test_close_action_select_not_outside_gate] #closeAction 全檔恰 1（與 gate 內 required 成對推 outside=0） — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-model="form\.closeAction"/,
    scope: /<select\b[^>]*\bid="closeAction"[^>]*>/,
    note: '[lint-guard 162c-test_close_action_select_has_x_model] #closeAction 須綁 x-model="form.closeAction" — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [/(?<![\w:-])value="ask"/, /(?<![\w:-])value="tray"/, /(?<![\w:-])value="exit"/],
    scope: /<select\b[^>]*\bid="closeAction"[^>]*>[\s\S]*?<\/select>/,
    note: '[lint-guard 162c-test_close_action_select_has_three_option_values] #closeAction 須有 ask/tray/exit 三選項 — 遷自 test_contract_desktop.py' },

  // 162c: TestAccessAuthStateWiring
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-]):disabled="accessAuthPinDisabled\(\)"/,
    scope: /<input\b[^>]*class="settings-access-auth-pin-input"[^>]*>/,
    note: '[lint-guard 162c-test_pin_input_calls_access_auth_pin_disabled] PIN input 須綁 accessAuthPinDisabled() — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /(?<![\w:-]):disabled="accessAuthSaveDisabled\(\)"/,
    scope: /<button\b[^>]*class="settings-access-auth-save-btn[^"]*"[^>]*>/,
    note: '[lint-guard 162c-test_save_button_calls_access_auth_save_disabled] 儲存鈕須綁 accessAuthSaveDisabled() — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])x-show="accessAuthStatusHintKey\(\)"/,
      /(?<![\w:-])x-text="window\.t\(accessAuthStatusHintKey\(\)\)"/,
    ],
    scope: /<div\b[^>]*class="settings-access-auth-status-hint"[^>]*>/,
    note: '[lint-guard 162c-test_status_hint_calls_access_auth_status_hint_key] 狀態提示須綁 accessAuthStatusHintKey — 遷自 test_contract_desktop.py' },

  // 162c: TestHelpUpdateButtonGuard
  { file: 'web/templates/help.html', kind: 'required-string',
    pattern: 'triggerUpdate()',
    scope: /\{%-?\s*if\s+is_desktop\s*-?%\}\s*<template x-if="checkDone && !errorMsg && hasUpdate">([\s\S]*?)<\/template>\s*\{%-?\s*endif/,
    note: '[lint-guard 162c-test_trigger_update_click_inside_desktop_gate] triggerUpdate() 須在 is_desktop gate 內 — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/help.html', kind: 'structure-count',
    pattern: 'triggerUpdate()',
    count: 1,
    note: '[lint-guard 162c-test_trigger_update_not_outside_gate] triggerUpdate() 全檔恰 1（與 gate 內 required 成對推 outside=0） — 遷自 test_contract_desktop.py' },
  { file: 'web/static/js/pages/help.js', kind: 'required-string',
    pattern: /async\s+triggerUpdate\s*\(\s*\)\s*\{/,
    note: '[lint-guard 162c-test_trigger_update_defined_in_help_js] help.js 須定義 async triggerUpdate() — 遷自 test_contract_desktop.py' },

  // 162c: TestGalleryOutputDirEmptyFollowsDataRoot
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'gallery_output_in_program_area',
    note: '[lint-guard 162c-test_settings_handles_gallery_output_in_program_area_reason] 輸出目錄在程式區被擋時前端須處理 gallery_output_in_program_area — 遷自 test_contract_lifecycle.py' },

  // 162c: (module) test_notification_url_renders_clickable_link
  { file: 'web/templates/base.html', kind: 'required-string',
    pattern: [
      /<template\s+(?<![\w:-])x-if="item\.url">\s*<a\b[^>]*(?<![\w:-]):href="item\.url"[^>]*target="_blank"[^>]*rel="noopener"/,
      /<a\b[^>]*(?<![\w:-]):href="item\.url"[^>]*>\s*<span[^>]*(?<![\w:-])x-text="item\.message"/,
    ],
    note: '[lint-guard 162c-test_notification_url_renders_clickable_link] 通知須有可點 item.url 連結且訊息用 x-text — 遷自 test_contract_notifications.py' },

  // ---- 162c-B27 迄 ----
  //
  //
  //
  // ---- 162c-B28 起 ----
  // （162c-B28 專屬子區段：只在此兩行之間追加）

  // 162c: TestHelpUpdateButtonGuard
  { file: 'web/templates/help.html', kind: 'required-string',
    pattern: 'showUpdateModal',
    note: '[lint-guard 162c-test_update_modal_x_show_binding_exists] 桌面版使用者按「更新」→ modal 沒綁 showUpdateModal 永不出現 → 看不到確認框、更新流程卡死 — 遷自 test_contract_desktop.py' },
  { file: 'web/templates/help.html', kind: 'required-string',
    pattern: ['confirmUpdate()', 'cancelUpdate()'],
    note: '[lint-guard 162c-test_update_modal_has_confirm_and_cancel] 桌面版使用者在更新確認框 → 缺確認或取消按鈕呼叫 → 沒辦法確認更新或沒辦法關掉框 — 遷自 test_contract_desktop.py' },

  // ---- 162c-B28 迄 ----
  //
  //
  //
  // ---- 162c-B29 起 ----
  // （162c-B29 專屬子區段：只在此兩行之間追加）

  // 162c: (module) test_lightbox_keydown_guards_delete_modal
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'deleteVideoModalOpen',
    scope: { anchor: /handleKeydown\s*\(\s*e\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_lightbox_keydown_guards_delete_modal] 燈箱刪除確認框開著時按 Esc／方向鍵 → handleKeydown 須參考 deleteVideoModalOpen 以免 Esc 連燈箱一起關、方向鍵換片 — 遷自 test_frontend_offline_guards.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'cancelDeleteVideo',
    scope: { anchor: /handleKeydown\s*\(\s*e\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_lightbox_keydown_guards_delete_modal] 燈箱刪除確認框開著時按 Esc → handleKeydown 須呼叫 cancelDeleteVideo 只關確認框 — 遷自 test_frontend_offline_guards.py',
  },

  // 162c: TestServerModeConfirm
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'serverModeConfirmOpen',
    note: '[lint-guard 162c-test_modal_exists_in_settings_html] 按伺服器模式開關 → settings.html 須有 serverModeConfirmOpen 確認框標記 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'confirmServerModeChange()',
    note: '[lint-guard 162c-test_modal_has_confirm_and_cancel_buttons] 確認框按確認 → 須有 confirmServerModeChange() handler — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'cancelServerModeChange()',
    note: '[lint-guard 162c-test_modal_has_confirm_and_cancel_buttons] 確認框按取消 → 須有 cancelServerModeChange() handler — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: '"title":',
    scope: /"server_mode_confirm"\s*:\s*\{([^}]*)\}/,
    note: '[lint-guard 162c-test_i18n_keys_in_zh_tw] 開伺服器模式確認框 → zh_TW server_mode_confirm 區塊須有 title 鍵 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: '"title_on":',
    scope: /"server_mode_confirm"\s*:\s*\{([^}]*)\}/,
    note: '[lint-guard 162c-test_i18n_keys_in_zh_tw] 開伺服器模式確認框 → zh_TW server_mode_confirm 區塊須有 title_on 鍵 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: '"body_on":',
    scope: /"server_mode_confirm"\s*:\s*\{([^}]*)\}/,
    note: '[lint-guard 162c-test_i18n_keys_in_zh_tw] 開伺服器模式確認框 → zh_TW server_mode_confirm 區塊須有 body_on 鍵 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: '"body_off":',
    scope: /"server_mode_confirm"\s*:\s*\{([^}]*)\}/,
    note: '[lint-guard 162c-test_i18n_keys_in_zh_tw] 開伺服器模式確認框 → zh_TW server_mode_confirm 區塊須有 body_off 鍵 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: '"confirm":',
    scope: /"server_mode_confirm"\s*:\s*\{([^}]*)\}/,
    note: '[lint-guard 162c-test_i18n_keys_in_zh_tw] 開伺服器模式確認框 → zh_TW server_mode_confirm 區塊須有 confirm 鍵 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'locales/zh_TW.json', kind: 'required-string',
    pattern: '"confirm_on":',
    scope: /"server_mode_confirm"\s*:\s*\{([^}]*)\}/,
    note: '[lint-guard 162c-test_i18n_keys_in_zh_tw] 開伺服器模式確認框 → zh_TW server_mode_confirm 區塊須有 confirm_on 鍵 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'server_mode_confirm.title_on',
    note: '[lint-guard 162c-test_modal_title_is_conditional_x_text] 確認框標題 on 分支須綁 server_mode_confirm.title_on — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: "server_mode_confirm.title'",
    note: '[lint-guard 162c-test_modal_title_is_conditional_x_text] 確認框標題 off 分支須綁 server_mode_confirm.title — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: 'server_mode_confirm.confirm_on',
    note: '[lint-guard 162c-test_modal_confirm_button_is_conditional_x_text] 確認按鈕 on 分支須綁 server_mode_confirm.confirm_on — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string',
    pattern: "server_mode_confirm.confirm'",
    note: '[lint-guard 162c-test_modal_confirm_button_is_conditional_x_text] 確認按鈕 off 分支須綁 server_mode_confirm.confirm — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/static/js/pages/settings/state-ui.js', kind: 'required-string',
    pattern: 'serverModeConfirmOpen',
    note: '[lint-guard 162c-test_state_ui_has_confirm_state] state-ui.js 須宣告 serverModeConfirmOpen — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/static/js/pages/settings/state-ui.js', kind: 'required-string',
    pattern: 'serverModeConfirmValue',
    note: '[lint-guard 162c-test_state_ui_has_confirm_state] state-ui.js 須宣告 serverModeConfirmValue — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'requestServerModeChange',
    note: '[lint-guard 162c-test_state_config_has_three_methods] 設定頁按開關 → state-config 須有 requestServerModeChange 方法 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'confirmServerModeChange',
    note: '[lint-guard 162c-test_state_config_has_three_methods] 確認框按確認 → state-config 須有 confirmServerModeChange 方法 — 遷自 test_settings_server_mode_confirm.py',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: 'cancelServerModeChange',
    note: '[lint-guard 162c-test_state_config_has_three_methods] 確認框按取消 → state-config 須有 cancelServerModeChange 方法 — 遷自 test_settings_server_mode_confirm.py',
  },

  // ---- 162c-B29 迄 ----
  //
  //
  //
  // ---- 162c-B30 起 ----
  // （162c-B30 專屬子區段：只在此兩行之間追加）

  // 162c: TestShowcaseScrollCollapse
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', anyOf: true,
    pattern: ["addEventListener('scroll'", 'addEventListener("scroll"'],
    note: '[lint-guard 162c-test_scroll_listener_registered] 手機往下捲須登記 passive scroll listener 才能自動收合工具列 — 遷自 test_showcase_mobile_search.py' },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: /Alpine\.store\('ui'\)\.toolbarOpen\b(?!\s*=(?!=))/,
    scope: { anchor: /const _scrollHandler = \(\) => \{/, braceBalanced: true },
    note: '[lint-guard 162c-test_scroll_collapse_checks_toolbar_open] scroll handler 須讀 toolbarOpen 才能在未展開時提早 return — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: 'this._hasActiveFilterForCurrentTab()',
    scope: { anchor: /const _scrollHandler = \(\) => \{/, braceBalanced: true },
    note: '[lint-guard 162c-test_scroll_collapse_checks_empty_search] 手機搜尋中往下捲 → scroll handler 須檢查啟用中篩選，否則工具列被收起但篩選仍在、使用者以為那就是全庫 — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: 'actressSearch',
    scope: { anchor: /_hasActiveFilterForCurrentTab\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_scroll_collapse_checks_actress_search] 女優牆手機搜尋後往下捲 → 判準須含 actressSearch，否則工具列被收、搜尋框不見但篩選仍在 — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: /window\.scrollY\s*-\s*_toolbarOpenY|_toolbarOpenY\s*-\s*window\.scrollY/,
    scope: { anchor: /const _scrollHandler = \(\) => \{/, braceBalanced: true },
    note: '[lint-guard 162c-test_scroll_collapse_uses_relative_threshold] 使用者已捲到下方才展開工具列 → handler 須用相對基準 _toolbarOpenY，否則一展開就被收回 — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: '_toolbarOpenY = null',
    scope: { anchor: /toolbarOpen = false/, window: 140 },
    note: '[lint-guard 162c-test_scroll_collapse_resets_baseline_on_auto_close] 自動收合後再點開 → 基準 Y 須立即重置，否則剛展開就用舊基準再度被收 — 遷自 test_showcase_mobile_search.py',
  },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: /removeEventListener\(\s*['"]scroll['"]\s*,\s*this\._scrollHideHandler/,
    note: '[lint-guard 162c-test_scroll_listener_cleanup] 離開 showcase 頁須移除 scroll 監聽，否則舊 handler 仍改 toolbarOpen — 遷自 test_showcase_mobile_search.py' },

  // 162c: TestShowcaseHeaderSearchIcon
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w:-])(?:@|x-on:)showcase:clear-search\b/,
    note: '[lint-guard 162c-test_showcase_has_window_listener] 按 header ✕ → showcase 頁須接 clear-search 事件才能清掉搜尋 — 遷自 test_showcase_mobile_search.py' },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'addPill(',
    scope: { anchor: /searchFromMetadata\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_search_from_metadata_delegates_to_add_pill] 燈箱點導演／系列／女優名 → searchFromMetadata 須委派 addPill，否則牆未依該維度篩選 — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: 'this.search = ',
    scope: { anchor: /searchFromMetadata\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_search_from_metadata_delegates_to_add_pill] 燈箱點導演／系列／女優名 → searchFromMetadata 不得直接寫 this.search（須走 addPill） — 遷自 test_showcase_mobile_search.py',
  },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', anyOf: true,
    pattern: ["$watch('search'", '$watch("search"'],
    note: '[lint-guard 162c-test_watch_search_updates_showcase_has_search] 手機輸入搜尋 → 須有 $watch(\'search\') 更新旗標，否則 header 不變 ✕、無法一鍵清除 — 遷自 test_showcase_mobile_search.py' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', anyOf: true,
    pattern: ["$watch('actressSearch'", '$watch("actressSearch"'],
    note: '[lint-guard 162c-test_watch_actress_search_updates_showcase_has_search] 女優牆輸入搜尋 → 須有 $watch(\'actressSearch\') 更新旗標，否則 header 不變 ✕ — 遷自 test_showcase_mobile_search.py' },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: 'pills.length',
    scope: { anchor: /_hasActiveFilterForCurrentTab\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_init_sync_showcase_has_search_after_watchers] 用 pill 篩選時清除 ✕ 須涵蓋 pills.length，否則看著被篩過的牆卻沒有清除鈕 — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: 'showFavoriteActresses',
    scope: { anchor: /_hasActiveFilterForCurrentTab\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162c-test_init_sync_showcase_has_search_after_watchers] 切換影片／女優分頁時判準須含 showFavoriteActresses，否則清除鈕不分頁化 — 遷自 test_showcase_mobile_search.py',
  },
  {
    file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    pattern: "Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();",
    scope: { anchor: /T2 init sync/, window: 260 },
    note: '[lint-guard 162c-test_init_sync_showcase_has_search_after_watchers] init 須同步 showcaseHasSearch 初始值，否則只靠 $watch 會漏掉 restoreState 後的清除鈕 — 遷自 test_showcase_mobile_search.py',
  },

  // ---- 162c-B30 迄 ----
  //
  //
  //

  // ---- 162c-FIX4（本地實剪驗證補回） ----
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /<div(?=[^>]*(?<![\w:-])x-show="!video\.cover_url")[^>]*\bclass="[^"]*\bav-card-no-cover\b/,
    note: '[lint-guard 162c-test_grid_has_no_cover_div] 使用者開片牆 → 無圖片佔位元素須掛 x-show="!video.cover_url"，否則每張有封面的卡都疊上「無圖片」圖示與字 — 遷自 tests/unit/test_frontend_lint.py（本地實剪驗證補回）' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: /^[ \t]*cancelSwitchMode\s*\([^)]*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_state_config_defines_methods_and_stubs] 使用者在設定頁切外部管理器模式 → 確認窗按取消／Esc／點背景須有 cancelSwitchMode，否則丟 TypeError、視窗關不掉只能重整 — 遷自 tests/unit/frontend_contracts/test_contract_code_shape.py（本地實剪驗證補回）' },
  { file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string',
    pattern: /^[ \t]*async\s+confirmSwitchMode\s*\([^)]*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_state_config_defines_methods_and_stubs] 使用者在設定頁切外部管理器模式 → 確認窗按確認須有 confirmSwitchMode，否則丟 TypeError、視窗關不掉只能重整 — 遷自 tests/unit/frontend_contracts/test_contract_code_shape.py（本地實剪驗證補回）' },
  // ---- 162c-FIX4 迄 ----

  // ---- 162c-FIX5（PR#219 Codex P2：重新刮削確認防連點） ----
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'order',
    scope: { anchor: /async\s+rescrapeConfirm\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    items: [
      { pattern: /if\s*\(\s*this\._rescraping\s*\)\s*return\b/ },
      { pattern: /this\._rescraping\s*=\s*true\b/ },
      { pattern: /await\s+fetch\(/ },
    ],
    note: '[lint-guard 162c-test_rescraping_guard_present] 使用者在重刮確認窗連點 ✓ → 入口須先擋重入、且在第一個 await 前設 _rescraping=true，否則同一片同時送兩個覆寫請求（/api/enrich-single 無鎖、封面兩條執行緒同寫一檔）→ 封面或 NFO 可能寫壞，要再重刮 — 遷自 test_contract_api_routes.py（PR#219 Codex P2 補回）' },
  { file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string',
    scope: { anchor: /async\s+rescrapeConfirm\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /finally\s*\{\s*this\._rescraping\s*=\s*false\b/,
    note: '[lint-guard 162c-test_rescraping_guard_present] 使用者重刮確認失敗後 → finally 須把 _rescraping 設回 false，否則之後再按 ✓ 永遠被入口擋掉、只能關窗重開 — 遷自 test_contract_api_routes.py（PR#219 Codex P2 補回）' },
  // ---- 162c-FIX5 迄 ----

  // ---- 162c-FIX6（本地全量實剪：無人承接守衛補回 ＋ 新誤報放寬）----
  // 甲-A（verify-del-1）
  { file: 'web/templates/scanner.html', kind: 'required-string',
    pattern: /(?<![\w:-])x-model="addingAlias\[group\.primary_name\]"/,
    note: '[lint-guard 162c-test_scanner_html_contains] 使用者在掃描頁別名卡按新增、在輸入框打字 → 輸入框須用 x-model 雙向綁 addingAlias，否則輸入不寫回、無法新增別名 — 遷自 tests/unit/test_frontend_lint.py（本地實剪驗證補回）' },
  { file: 'web/templates/scanner.html', kind: 'forbidden-string',
    pattern: /:value="addingAlias\[/,
    note: '[lint-guard 162c-test_scanner_html_contains] 使用者在掃描頁別名卡輸入新主名 → 不得改回單向 :value 綁定（輸入不寫回、無法新增別名） — 遷自 tests/unit/test_frontend_lint.py（本地實剪驗證補回）' },
  { file: 'web/static/js/pages/scanner/state-alias.js', kind: 'required-string',
    pattern: /^[ \t]*cancelAddAlias\s*\([^)]*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_scanner_alias_js_contains] 使用者在掃描頁別名卡輸入新主名後按取消／Esc → 須有 cancelAddAlias，否則取消鈕與 Esc 無效、輸入框卡在開啟 — 遷自 tests/unit/test_frontend_lint.py（本地實剪驗證補回）' },
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w.])prevActressLightbox\(\)/,
    note: '[lint-guard 162c-test_showcase_html_contains] 使用者在女優燈箱按「上一位」→ 按鈕須呼叫 prevActressLightbox()，否則按了沒反應、只能關掉重開 — 遷自 tests/unit/test_frontend_lint.py（TestShowcaseActressLightbox；本地實剪驗證補回）' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /^[ \t]*_visibleAliases\s*\([^)]*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_actress_js_contains] 使用者開女優燈箱 → 別名區 x-for 讀 _visibleAliases()，缺定義則別名 chips 空白／Alpine 報錯 — 遷自 tests/unit/test_frontend_lint.py（TestShowcaseActressLightbox；本地實剪驗證補回）' },
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w.])_actressHoverInfo\s*\(/,
    note: '[lint-guard 162c-test_actress_html_contains] 使用者把滑鼠移到女優卡 → 卡片須綁 _actressHoverInfo() 才顯示 hover 資訊 — 遷自 tests/unit/test_frontend_lint.py（TestShowcaseActressCardFooter；本地實剪驗證補回）' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /^[ \t]*_actressCardMiddle\s*\([^)]*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_actress_js_contains] 使用者看女優牆卡片 → 卡片中段文字讀 _actressCardMiddle()，缺定義則中段空白／報錯 — 遷自 tests/unit/test_frontend_lint.py（TestShowcaseActressCardFooter；本地實剪驗證補回）' },
  { file: 'web/templates/settings.html', kind: 'required-string',
    pattern: /\.replace\(\s*['"]\{mb\}['"]\s*,/,
    note: '[lint-guard 162c-test_thumb_cache_disable_modal_body_releases_mb] 使用者在設定頁關閉縮圖快取 → 確認框須把 {mb} 換成釋放容量數字，否則確認前看到字面「{mb}」、不知道會釋放多少空間 — 遷自 tests/unit/test_frontend_lint.py（本地實剪驗證補回）' },
  { file: 'web/templates/search.html', kind: 'required-string',
    pattern: /\bname="_resolveSourceName\(/,
    note: '[lint-guard 162c-test_result_pill_name_resolves_source] 使用者看搜尋結果來源膠囊 → name 須走 _resolveSourceName，否則顯示內部 source id 而非顯示名 — 遷自 tests/unit/test_frontend_lint.py（本地實剪驗證補回）' },
  // 甲-B（verify-del-2）
  { file: 'web/static/js/pages/showcase/state-similar.js', kind: 'required-string',
    scope: { anchor: /async\s+openSimilarMode\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /window\.innerWidth\s*<\s*960\b/,
    note: '[lint-guard 162c-test_open_similar_mode_threshold_960] 使用者把視窗縮到 768–959px（半螢幕）在影片燈箱按「相似探索」→ 門檻須為 <960 才走手機面板，偏離則走桌面舞台、CSS 不適用而版面跑掉（768 門檻同此條涵蓋） — 遷自 tests/unit/test_frontend_lint.py（TestSimilarJSThresholdGuard；本地實剪驗證補回）' },
  { file: 'web/static/js/shared/breakpoints.js', kind: 'required-string',
    pattern: /\bPOSTER_CROP_MAX_W\s*=\s*899\b/, stripLineComments: true,
    note: '[lint-guard 162c-test_breakpoint_const_is_899] 使用者把視窗拉到 801–899px → JS 的 POSTER_CROP_MAX_W 須與 CSS 899px 斷點一致，否則焦點 icon 不出現、飛行動畫比例對不上 — 遷自 tests/unit/test_frontend_lint.py（TestPosterCropThresholdAlignment；本地實剪驗證補回）' },
  { file: 'web/static/js/pages/scanner/state-scan.js', kind: 'required-string',
    pattern: /^[ \t]*jellyfinCheckState:\s*['\"]idle['\"]/m, stripLineComments: true,
    note: '[lint-guard 162c-test_jellyfin_check_state_declared] 使用者開掃描頁（尚未按檢查補圖）→ jellyfinCheckState 須有初值 idle，否則 idle／checking／done 三態文案求值失敗而同時顯示、主控台報錯 — 遷自 tests/unit/test_frontend_lint.py（TestJellyfinCheckManualGuard；本地實剪驗證補回）' },
  // 甲-C（verify-mov-1）
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /^[ \t]*hasVisiblePrev\s*\(\s*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_showcase_lightbox_js_contains] 使用者開影片燈箱 → 上一部箭頭 x-show 求值 hasVisiblePrev()，缺定義則 Alpine 丟 ReferenceError、箭頭消失或燈箱導航失效 — 遷自 tests/unit/test_frontend_lint.py（TestShowcaseLightboxSentinel；本地實剪驗證補回）' },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: /^[ \t]*hasVisibleNext\s*\(\s*\)\s*\{/m, stripLineComments: true,
    note: '[lint-guard 162c-test_showcase_lightbox_js_contains] 使用者開影片燈箱 → 下一部箭頭 x-show 求值 hasVisibleNext()，缺定義則 Alpine 丟 ReferenceError、箭頭消失或燈箱導航失效 — 遷自 tests/unit/test_frontend_lint.py（TestShowcaseLightboxSentinel；本地實剪驗證補回）' },
  // 甲-D（verify-mov-2：scroll 收合判準函式內須含 search 子句）
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    scope: { anchor: /_hasActiveFilterForCurrentTab\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /this\.search\s*!==\s*''/,
    note: '[lint-guard 162c-test_scroll_collapse_checks_empty_search] 使用者在影片牆搜尋框打字後往下捲 → 啟用中篩選判準須含 this.search !== \'\'，否則工具列被收起、字還在篩選卻看不到輸入框 — 遷自 test_showcase_mobile_search.py（本地實剪驗證補回）' },
  // 甲-E（Codex 第 3 輪）
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'required-string',
    pattern: /this\.videoCount\s*=\s*_videos\.length/, stripLineComments: true,
    note: '[lint-guard 162c-videoCount-assigned] 使用者開影片牆 → 載入完成後 videoCount 須由 _videos.length 賦值，否則永遠 0、牆一直顯示「沒有影片」空狀態 — 新增（舊 guard7 名存實亡）' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'structure-count',
    pattern: /this\.filteredCount\s*=\s*_filteredVideos\.length/g, min: 2, stripLineComments: true,
    note: '[lint-guard 162c-filteredCount-assigned] 使用者載入／搜尋／篩選影片牆 → filteredCount 須在初次載入與 applyFilterAndSort 兩處由 _filteredVideos.length 賦值，否則頁尾「共 N 部」計數不更新 — 新增（Codex 第 3 輪）' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string',
    scope: { anchor: /\bisComposing\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /pageState\s*!==\s*'loading'/,
    note: '[lint-guard 162c-test_is_composing_three_conditions] 使用者在搜尋進行中改打另一個字 → isComposing 須排除 loading 狀態，否則來源膠囊／切換鈕在載入期間多閃或少閃 — 遷自 tests/unit/test_frontend_lint.py（TestIsComposingGetter；本地實剪驗證補回）' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string',
    scope: { anchor: /\bisComposing\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /\bsearchQuery\b/,
    note: '[lint-guard 162c-test_is_composing_three_conditions] 使用者在搜尋框打字 → isComposing 須讀 searchQuery，否則「正在輸入」判斷失準 — 遷自 tests/unit/test_frontend_lint.py（TestIsComposingGetter；本地實剪驗證補回）' },
  { file: 'web/static/js/pages/search/state/search-flow.js', kind: 'required-string',
    scope: { anchor: /\bisComposing\s*\(\s*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /\bcurrentQuery\b/,
    note: '[lint-guard 162c-test_is_composing_three_conditions] 使用者改打字後與上次查詢比較 → isComposing 須讀 currentQuery，否則採用結果後仍誤判為輸入中 — 遷自 tests/unit/test_frontend_lint.py（TestIsComposingGetter；本地實剪驗證補回）' },
  // ---- 162c-FIX6 迄 ----

  // ==== 162e：自 web/static/js/**/__tests__ 搬入 ====
  // ---- 162e：release-pill-shell ----
  { file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'anchor-first-tag',
    anchor: /(?=<div\b[^>]*?(?<![\w:-])class="pill-editor-popover")(?<=class="pill-editor-popover"[\s\S]*)/, tagPattern: /<div\b[^>]*>/,
    required: [/(?<![\w:-])x-show="_releaseEditor && !showFavoriteActresses && _pillPopoverEnabled"/],
    note: '[lint-guard 162e-發售日浮層x-show三合取] 使用者開發售日浮層 → 浮層只該在「正在編輯發售日、影片模式、非窄螢幕」時出現；x-show 條件掉了則浮層一直蓋在搜尋列上，或在女優模式殘留 — 遷自 release-pill-shell.test.mjs' },
  { file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'anchor-first-tag',
    anchor: /(?=<div\b[^>]*?(?<![\w:-])class="pill-editor-popover")(?<=class="pill-editor-popover"[\s\S]*)/, tagPattern: /<div\b[^>]*>/,
    required: [
      /(?<![\w:-])x-cloak/,
      /(?<![\w:-])x-transition\.opacity\.duration\.150ms/,
      /(?<![\w:-])x-trap="!!_releaseEditor"/,
      /(?<![\w:-])@click\.outside="_releaseEditor && _cancelReleaseEditor\(\)"/,
      /(?<![\w:-])@click\.stop/,
      /(?<![\w:-])role="dialog"/,
      /(?<![\w:-])aria-modal="false"/,
      /(?<![\w:-])aria-labelledby="release-editor-title"/,
    ],
    note: '[lint-guard 162e-發售日浮層標籤屬性] 使用者在發售日浮層外點一下 → 浮層應收起（click.outside）、浮層內點擊不得外洩（click.stop）、鍵盤焦點應留在浮層內（x-trap）；掉了則點外面不收、或焦點跑出浮層 — 遷自 release-pill-shell.test.mjs' },

  // ---- 162e：actress-pill-popover-shell ----
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: /(?<![\w:-])class="pill-editor-popover"[^>]*(?<![\w:-])x-show="_pillEditor && showFavoriteActresses && _pillPopoverEnabled"|(?<![\w:-])x-show="_pillEditor && showFavoriteActresses && _pillPopoverEnabled"[^>]*(?<![\w:-])class="pill-editor-popover"/,
    note: '[lint-guard 162e-浮層x-show三合取] 使用者開著女優浮層時切到影片分頁，或把視窗縮到手機寬度 → 三合取 x-show 讓浮層立刻隱藏；少一項則浮層殘留在影片模式或手機畫面上、蓋住搜尋列 — 遷自 actress-pill-popover-shell.test.mjs' },
  { file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagPattern: /<div\b(?=[^>]*(?<![\w:-])aria-labelledby="pill-editor-title")[^>]*>/,
    required: [/(?<![\w:-])x-trap="!!_pillEditor"/, /(?<![\w:-])@click\.outside="_pillEditor && _cancelPillEditor\(\)"/],
    forbidden: [/x-trap\.inert/],
    note: '[lint-guard 162e-浮層x-trap與click.outside] 使用者按 Tab 或點浮層外面 → 浮層鎖住焦點(x-trap 不帶 .inert)且點外面取消編輯；缺 x-trap 焦點跑出浮層、缺 @click.outside 點外面關不掉；誤加 .inert 則背景整片不可點、點外面也關不掉 — 遷自 actress-pill-popover-shell.test.mjs' },

  // ---- 162e：presentation-wiring ----

  // ---- 162e：select-presentation ----
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string',
    pattern: /this\.mode\s*=(?!=)/,
    scope: { anchor: /selectPresentation\s*(?::\s*function)?\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162e-selectPres零mode賦值] 使用者在格狀按「表格」或在表格按「直式海報」→ 若 selectPresentation 自己賦值 this.mode 而繞過 switchMode，每頁筆數不會降級／分頁不重算 → 格狀一次畫出整個片庫（perPage=0）而卡頓、或頁碼超出範圍看到空白頁 — 遷自 select-presentation.test.mjs' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string',
    pattern: ['scrollTo', 'scrollIntoView'],
    scope: { anchor: /selectPresentation\s*(?::\s*function)?\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162e-selectPres不捲動] 使用者在瀏覽頁往下捲到某處後按右上角卡型切換 → 若切換時呼叫 scrollTo／scrollIntoView，畫面會被拉回頂端或跳位 → 使用者找不到剛看的那排片、得重新捲 — 遷自 select-presentation.test.mjs' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string',
    pattern: /shouldSkip\(\)\s*\)\s*return null/,
    scope: { anchor: /playShapeMorph\s*(?::\s*function)?\s*\([^)]*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    note: '[lint-guard 162e-playShapeMorph減動態早退] 使用者在作業系統開啟「減少動態效果」（prefers-reduced-motion）後切換封面／海報 → 若 playShapeMorph 不在 shouldSkip() 時早退，仍會播卡片 morph 動畫 → 違反使用者的無障礙設定、對動態敏感的人會不舒服 — 遷自 select-presentation.test.mjs' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'forbidden-string',
    pattern: /absolute\s*:\s*true/,
    scope: { anchor: /playShapeMorph\s*(?::\s*function)?\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[lint-guard 162e-playShapeMorph不absolute] 使用者在整頁 ~90 張卡的瀏覽頁切換封面／海報 → 若 Flip 的 absolute 被設成 true，動畫期間 grid 容器高度歸零，頁面瞬間縮短、捲動位置被瀏覽器夾回 → 看完動畫後落在跟剛才不同的位置 — 遷自 select-presentation.test.mjs' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string',
    pattern: /absolute\s*:\s*false/,
    scope: { anchor: /playShapeMorph\s*(?::\s*function)?\s*\([^)]*\)\s*\{/, braceBalanced: true }, stripLineComments: true,
    note: '[lint-guard 162e-playShapeMorph不absolute] 使用者在整頁 ~90 張卡的瀏覽頁切換封面／海報 → Flip 的 absolute 須顯式寫 false，否則動畫期間 grid 容器高度歸零、捲動位置被夾回 — 遷自 select-presentation.test.mjs' },

  // ---- 162e：pill-match ----
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'order',
    items: [
      { pattern: 'await _loadAliasMap()' },
      { pattern: 'await _loadTagAliasMap()' },
      { pattern: 'applyFilterAndSort(true)' },
    ],
    pairs: [[0, 2], [1, 2]],
    note: '[lint-guard 162e-CD7_alias_before_apply] 使用者重新進入影片牆（上次掛著別名比對的 pill）→ 若第一次篩選早於別名表載入，pill 以未展開的別名比對 → 牆上少片或空牆且沒有任何錯誤提示 → 必須手動重整 — 遷自 pill-match.test.mjs' },

  // ---- 162e：pill-clear ----
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string', stripLineComments: true,
    pattern: [
      /\$watch\(\s*['"]search['"]/,
      /\$watch\(\s*['"]actressSearch['"]/,
      /\$watch\(\s*['"]pills['"]/,
      /\$watch\(\s*['"]actressPills['"]/,
      /\$watch\(\s*['"]showFavoriteActresses['"]/,
    ],
    note: '[lint-guard 162e-ClearBtn_watch_wiring] 使用者（手機）只加 pill、或在影片／女優分頁間切換 → navbar 的清除 ✕ 沒有跟著出現或消失 → 想一鍵清掉做不到，或按了 ✕ 什麼都沒清，只能逐枚點掉 pill — 遷自 pill-clear.test.mjs' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'structure-count', count: 6,
    pattern: /Alpine\.store\('ui'\)\.showcaseHasSearch\s*=\s*this\._hasActiveFilterForCurrentTab\(\)/,
    note: '[lint-guard 162e-ClearBtn_watch_wiring] 使用者（手機）只加 pill、或在影片／女優分頁間切換 → navbar 的清除 ✕ 沒有跟著出現或消失（五個 $watch＋init sync 共 6 次寫入須恰 6 次；逐字鏡射舊 raw count，不剝註解） — 遷自 pill-clear.test.mjs' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'forbidden-string',
    pattern: "Alpine.store('ui').showcaseHasSearch = (this.search !== '' || this.actressSearch !== '')",
    note: '[lint-guard 162e-ClearBtn_watch_wiring] 使用者只加 pill 時 navbar 清除 ✕ 不出現 — init sync 不得再用舊兩欄位算式（漏掉 pills） — 遷自 pill-clear.test.mjs' },
  { file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: [
      /(?<![\w:-])(?:@|x-on:)showcase:clear-search\.window="clearAllFilters\(\)"/,
      /(?<![\w:-])@click="clearAllFilters\(\)"/,
      /(?<![\w:-])x-show="\$store\.ui\.showcaseHasSearch"/,
    ],
    note: '[lint-guard 162e-ClearBtn_clearAllFilters] 使用者按搜尋列或 navbar 的清除 ✕ → 沒有任何反應（事件沒人接或鈕沒接到 clearAllFilters）→ 只能逐枚點掉 pill、手動清字 — 遷自 pill-clear.test.mjs' },
  { file: 'web/templates/showcase.html', kind: 'forbidden-string',
    pattern: /^(?=[\s\S]*onActressSearchChange\(\))(?=[\s\S]*actressSearch = '')/,
    note: '[lint-guard 162e-ClearBtn_clearAllFilters] 使用者按搜尋列清除 ✕ → 不得再 inline 分流清 actressSearch（onActressSearchChange() 與 actressSearch = \'\' 同時存在即違規），否則 pill 與文字清不乾淨 — 遷自 pill-clear.test.mjs' },

  // ---- 162e：pill-hero ----
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'order',
    scope: { anchor: /async init\(\)[^{]*\{/, braceBalanced: true },
    items: [
      { pattern: 'this.restoreState()' },
      { pattern: '_reconcileHeroCard()' },
      { pattern: 'await this.fetchVideos()' },
      { pattern: '_awaitHeroCardWithTimeout' },
      { pattern: 'this.applyFilterAndSort(true)' },
      { pattern: 'this.page = savedPage' },
    ],
    pairs: [[0, 1], [1, 2], [3, 4], [4, 5]],
    note: '[lint-guard 162e-init_heroCard_gate_order] 使用者切頁離開再回到影片牆（掛著收藏女優 pill）→ 大卡比影片牆慢一拍才出現、格子先閃一次再補大卡；女優牆回頁則可能被影片牆大卡狀態污染 → 畫面跳動、須再操作一次才穩定 — 遷自 pill-hero.test.mjs' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'required-string',
    scope: { anchor: /async init\(\)[^{]*\{/, braceBalanced: true }, stripLineComments: true,
    pattern: /this\.showFavoriteActresses\s*\?[^\n]*:\s*this\._reconcileHeroCard\(\)/,
    note: '[lint-guard 162e-init_heroCard_gate_order] 使用者切頁離開再回到影片牆（掛著收藏女優 pill）→ 大卡比影片牆慢一拍才出現、格子先閃一次再補大卡；女優牆回頁則可能被影片牆大卡狀態污染 → 畫面跳動、須再操作一次才穩定 — 遷自 pill-hero.test.mjs' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'structure-count', count: 1,
    scope: { anchor: /async init\(\)[^{]*\{/, braceBalanced: true },
    pattern: 'this.applyFilterAndSort(true)',
    note: '[lint-guard 162e-init_heroCard_gate_order] 使用者切頁離開再回到影片牆（掛著收藏女優 pill）→ 大卡比影片牆慢一拍才出現、格子先閃一次再補大卡；女優牆回頁則可能被影片牆大卡狀態污染 → 畫面跳動、須再操作一次才穩定 — 遷自 pill-hero.test.mjs（init() 內 applyFilterAndSort(true) 恰一次；不剝註解，鏡射舊 raw count）' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'structure-count', count: 1,
    scope: { anchor: /async init\(\)[^{]*\{/, braceBalanced: true },
    pattern: 'this.page = savedPage',
    note: '[lint-guard 162e-init_heroCard_gate_order] 使用者切頁離開再回到影片牆（掛著收藏女優 pill）→ 大卡比影片牆慢一拍才出現、格子先閃一次再補大卡；女優牆回頁則可能被影片牆大卡狀態污染 → 畫面跳動、須再操作一次才穩定 — 遷自 pill-hero.test.mjs（init() 內 page = savedPage 恰一次；不剝註解）' },
  { file: 'web/static/js/pages/showcase/state-base.js', kind: 'structure-count', count: 1,
    scope: { anchor: /async init\(\)[^{]*\{/, braceBalanced: true },
    pattern: '_reconcileHeroCard()',
    note: '[lint-guard 162e-init_heroCard_gate_order] 使用者切頁離開再回到影片牆（掛著收藏女優 pill）→ 大卡比影片牆慢一拍才出現、格子先閃一次再補大卡；女優牆回頁則可能被影片牆大卡狀態污染 → 畫面跳動、須再操作一次才穩定 — 遷自 pill-hero.test.mjs（init() 內 _reconcileHeroCard() 恰一次；不剝註解）' },

];

// ---- helpers ----
let hadError = false;
function err(msg) {
  console.error(`✗ static_guard_lint: ${msg}`);
  hadError = true;
}

const fileCache = new Map();
function readTarget(relPath) {
  const full = join(ROOT, relPath);
  if (fileCache.has(full)) return fileCache.get(full);
  let text;
  try {
    text = readFileSync(full, 'utf8');
  } catch (e) {
    fileCache.set(full, null);
    return null;
  }
  fileCache.set(full, text);
  return text;
}

// 目錄掃描：預設非遞迴（複刻 pytest glob("*.html") 排除子目錄語意，NoVanillaHandlers 需要）；
// recursive:true 為 rglob 語意（NoInlineStyleDisplay 需要，含子目錄）；exclude 排除特定檔案
// （NoHardcodedColors 需要，排除 design-system.html / motion_lab.html 兩個 demo 頁）。
// exclude 比對「相對於 dir 的相對路徑」（posix '/' 分隔，非 basename）：basename-only 比對會讓
// 白名單誤放行「未來同名檔」（例如 pages/foo/animations.js），與來源 pytest 用完整相對路徑比對
// 的語意不一致，故 exclude 條目一律填相對路徑（Codex P2 fix，2026-07）。
function listDirFiles(relDir, exts, opts = {}) {
  const { recursive = false, exclude = [] } = opts;
  const full = join(ROOT, relDir);
  const results = [];
  let sawDir = false;
  function walk(dirFull, relPrefix) {
    let entries;
    try {
      entries = readdirSync(dirFull, { withFileTypes: true });
      sawDir = true;
    } catch {
      return; // 子目錄（或頂層目錄）讀取失敗，靜默跳過該分支
    }
    for (const e of entries) {
      const relPath = relPrefix ? join(relPrefix, e.name) : e.name;
      if (e.isDirectory()) {
        if (recursive) walk(join(dirFull, e.name), relPath);
        continue;
      }
      const relPathPosix = relPath.split(sep).join('/');
      if (e.isFile() && exts.some((ext) => e.name.endsWith(ext)) && !exclude.includes(relPathPosix)) {
        results.push(join(relDir, relPath));
      }
    }
  }
  walk(full, '');
  if (!sawDir) return null; // 頂層目錄本身讀取失敗
  return results;
}

function countOccurrences(haystack, pattern) {
  if (pattern instanceof RegExp) {
    const flags = pattern.flags.includes('g') ? pattern.flags : pattern.flags + 'g';
    const re = new RegExp(pattern.source, flags);
    let n = 0;
    while (re.exec(haystack) !== null) n += 1;
    return n;
  }
  let n = 0;
  let i = haystack.indexOf(pattern);
  while (i !== -1) {
    n += 1;
    i = haystack.indexOf(pattern, i + pattern.length);
  }
  return n;
}

function matches(haystack, pattern) {
  if (pattern instanceof RegExp) return pattern.test(haystack);
  return haystack.includes(pattern);
}

function patternLabel(pattern) {
  return pattern instanceof RegExp ? pattern.toString() : JSON.stringify(pattern);
}

// ---- evalRule dispatcher ----
function evalRule(rule, text, fileLabel) {
  switch (rule.kind) {
    case 'required-string':
      evalRequiredString(rule, text, fileLabel);
      break;
    case 'forbidden-string':
      evalForbiddenString(rule, text, fileLabel);
      break;
    case 'dup-id':
      evalDupId(rule, text, fileLabel);
      break;
    case 'structure-count':
      evalStructureCount(rule, text, fileLabel);
      break;
    case 'tag-scan':
      evalTagScan(rule, text, fileLabel);
      break;
    case 'inline-style-token':
      evalInlineStyleToken(rule, text, fileLabel);
      break;
    case 'order':
      evalOrder(rule, text, fileLabel);
      break;
    case 'file-absent':
      // file-absent 必須在 main loop 就地攔截（見 main 迴圈），不可能落到這裡；
      // 若真的走到此分支代表 main loop 攔截邏輯被誤刪或繞過了，明確報錯而非靜默誤判。
      throw new Error(
        'file-absent rule 不應進入 evalRule/readTarget 通用路徑——main loop 需在讀檔前攔截（見 main 迴圈頂部特殊分支）',
      );
    case 'paired-string':
      evalPairedString(rule, text, fileLabel);
      break;
    default:
      throw new Error('kind not implemented: ' + rule.kind);
  }
}

// ---- paired-string（96e-T3 新 kind，第 9 個）----
// 若 file 含 ifPresent，則同 file 必含 thenRequire（否則 err）；
// ifPresent 不存在時直接跳過（無此 API 使用，非違規，vacuous pass）。
// 用途：TestNoAlertInSearchJs::test_all_clipboard_writetext_files_have_availability_guard
// 「用了就必須有 guard」的檔級 pairing 語意（非 AST 分支、非跨檔）——required-string/
// forbidden-string 的 dir-scan 變體只能對每個匹配檔套用同一個無條件 pattern，無法表達
// 「pattern A 存在時才要求 pattern B」的條件式，故新增此 kind（CD-96e-3 授權擴 dispatcher）。
function evalPairedString(rule, text, fileLabel) {
  if (!matches(text, rule.ifPresent)) return;
  if (!matches(text, rule.thenRequire)) {
    err(`${rule.note} — ${fileLabel}: 含 ${patternLabel(rule.ifPresent)} 但缺 ${patternLabel(rule.thenRequire)}`);
  }
}

// stripLineComments（96e-T2，Opus 裁決 1）：byte-for-byte port pytest
// TestCoverCacheBustGuard._strip_line_comments —— 逐行以 (?<!:)//.*$ 剝除 `//` 注釋
// （lookbehind 保護 `https://` 等不被誤砍，單斜線 `/api` 不觸發）。套用在 resolveScope
// 抽出的 scopedText 上（scope 缺席時等同套用在全檔文字上），供 rule.stripLineComments:
// true 選用，防止「target 字串移進行內注釋」的 false-pass fail-open。
function stripLineComments(body) {
  return body
    .split('\n')
    .map((line) => line.replace(/(?<!:)\/\/.*$/, ''))
    .join('\n');
}

// scope 三種形式：單一 RegExp（T1）/ {anchor, window}（固定字元數視窗）/
// {anchor, braceBalanced}（大括號平衡方法體抽取，port Python _extract_method_body）。
// 外層 wrapper：resolveScopeRaw 算出 scopedText 後，若 rule.stripLineComments 為 true
// 則再套 stripLineComments（96e-T2 dispatcher 擴充，Opus 裁決 1）。
function resolveScope(rule, text, fileLabel) {
  const result = resolveScopeRaw(rule, text, fileLabel);
  if (result.ok && rule.stripLineComments) {
    return { scopedText: stripLineComments(result.scopedText), ok: true };
  }
  return result;
}

function resolveScopeRaw(rule, text, fileLabel) {
  if (!rule.scope) return { scopedText: text, ok: true };
  if (rule.scope instanceof RegExp) {
    const m = rule.scope.exec(text);
    if (!m) {
      err(`${rule.note} — ${fileLabel}: scope anchor 找不到（regex ${rule.scope} 無匹配，非 pattern 缺席）`);
      return { scopedText: null, ok: false };
    }
    const scopedText = m.length > 1 && m[1] !== undefined ? m[1] : m[0];
    return { scopedText, ok: true };
  }

  const { anchor, window: windowSize, braceBalanced } = rule.scope;
  const m = anchor.exec(text);
  if (!m) {
    err(`${rule.note} — ${fileLabel}: scope anchor 找不到（regex ${anchor} 無匹配，非 pattern 缺席）`);
    return { scopedText: null, ok: false };
  }

  if (windowSize !== undefined) {
    // 從 match.start() 起算含 anchor 本身的固定字元數視窗
    return { scopedText: text.slice(m.index, m.index + windowSize), ok: true };
  }

  if (braceBalanced) {
    // anchor 需匹配到含結尾 '{' 的方法簽名；逐字元計數 depth 直到平衡（非 regex 猜配對）
    const start = m.index + m[0].length;
    let depth = 1;
    let i = start;
    while (i < text.length && depth > 0) {
      const c = text[i];
      if (c === '{') depth += 1;
      else if (c === '}') depth -= 1;
      i += 1;
    }
    if (depth > 0) {
      err(`${rule.note} — ${fileLabel}: brace-balanced scope 到檔案結尾仍未平衡（depth=${depth}），視同 anchor 找不到（不可靜默回傳半截 body）`);
      return { scopedText: null, ok: false };
    }
    return { scopedText: text.slice(start, i - 1), ok: true };
  }

  err(`${rule.note} — ${fileLabel}: scope 物件格式不明（需 window 或 braceBalanced 其一）`);
  return { scopedText: null, ok: false };
}

// ---- dup-id ----
function evalDupId(rule, text, fileLabel) {
  const re = /\sid="([^"]+)"/g;
  const ids = [];
  let m;
  while ((m = re.exec(text)) !== null) ids.push(m[1]);
  const counts = new Map();
  for (const id of ids) counts.set(id, (counts.get(id) || 0) + 1);
  const dupes = [...counts.entries()]
    .filter(([, n]) => n > 1)
    .map(([id]) => id)
    .sort();
  if (dupes.length > 0) {
    err(`${rule.note} — ${fileLabel}: 含 duplicate id：${dupes.join(', ')}`);
  }
}

// stripPythonNoise（PR#176 Codex P2 修正，[lint-guard 141a-T5] 延伸）：
// structure-count 數的是「檔案原始文字」，.py 檔裡註解／docstring／trailing comment
// 只要含 pattern 字面（例如 'reconcile_wishlist('）就會讓計數跑掉。Codex 原講法是
// 「誤報造成開發摩擦」——那只是我們的成本，不足以構成必修理由。真正的理由是同一根因
// 的反向：註解裡有該字面時，若有人把「真正的呼叫」順手拔掉，計數仍是 1 ⇒ 守衛全綠而
// 對帳被拔掉 ⇒ 使用者的書籤不再自動移除（0.15.9 已拿掉手動清理鈕，使用者沒有別的辦法
// 補救）。修法採粗顆粒中間解：計數前先剝掉 Python 的行內/整行註解與三引號 docstring，
// 不解析真正的 call site（不把 AST 塞進 .mjs，那是重型守衛，專案規則明確反對），也不拿掉
// 這幾條守衛。逐行處理、剝掉的內容一律換成等量空白（保留換行數與行號），故不影響其他
// kind（forbidden-string/required-string/cross-file-equal 等）沿用的行號語意——本函式只在
// evalStructureCount 內對 .py 檔套用，其餘 kind／檔案類型完全不受影響。
// 逐字元掃描，state 只有「是否在三引號字串內」跨行延續；一般 '/" 字串在單行內用簡單
// escape-aware 掃描辨識，避免把字串字面內的 '#'（例如 URL fragment）誤判成註解起點。
function stripPythonNoise(text) {
  const lines = text.split('\n');
  const out = new Array(lines.length);
  let tripleDelim = null; // null | "'''" | '"""'（跨行 docstring 未結束時延續到下一行）
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    const n = line.length;
    let result = '';
    let i = 0;
    let inStr = null; // 目前是否在單行字串內，值為該字串的引號字元
    while (i < n) {
      if (tripleDelim) {
        const idx = line.indexOf(tripleDelim, i);
        if (idx === -1) {
          result += ' '.repeat(n - i);
          i = n;
        } else {
          result += ' '.repeat(idx + 3 - i);
          i = idx + 3;
          tripleDelim = null;
        }
        continue;
      }
      const ch = line[i];
      if (inStr) {
        result += ch;
        if (ch === '\\' && i + 1 < n) {
          result += line[i + 1];
          i += 2;
          continue;
        }
        if (ch === inStr) inStr = null;
        i += 1;
        continue;
      }
      if (ch === '#') {
        // 行內／整行註解：# 之後（不在字串內）一律視為註解，剝到行尾
        result += ' '.repeat(n - i);
        i = n;
        continue;
      }
      if (ch === "'" || ch === '"') {
        if (line.slice(i, i + 3) === ch.repeat(3)) {
          const closeIdx = line.indexOf(ch.repeat(3), i + 3);
          if (closeIdx === -1) {
            // 三引號在本行開啟但未結束 → 剝到行尾，跨行狀態延續
            result += ' '.repeat(n - i);
            tripleDelim = ch.repeat(3);
            i = n;
          } else {
            // 三引號整段落在同一行 → 連同引號一起剝除
            result += ' '.repeat(closeIdx + 3 - i);
            i = closeIdx + 3;
          }
          continue;
        }
        // 一般單/雙引號字串：不剝除內容（保留真正的字串字面，只剝註解/docstring）
        result += ch;
        inStr = ch;
        i += 1;
        continue;
      }
      result += ch;
      i += 1;
    }
    out[li] = result;
  }
  return out.join('\n');
}

// ---- structure-count：count（exact）/ min（下界）二擇一 ----
function evalStructureCount(rule, text, fileLabel) {
  const { scopedText, ok } = resolveScope(rule, text, fileLabel);
  if (!ok) return;
  // .py 檔先剝除註解/docstring 再計數（見上方 stripPythonNoise 註解：防漏報，不只是防誤報）
  const countedText = fileLabel.endsWith('.py') ? stripPythonNoise(scopedText) : scopedText;
  const n = countOccurrences(countedText, rule.pattern);
  if (rule.count !== undefined && n !== rule.count) {
    err(`${rule.note} — ${fileLabel}: 出現次數 ${n} != 要求 ${rule.count}（exact）：${patternLabel(rule.pattern)}`);
  }
  if (rule.min !== undefined && n < rule.min) {
    err(`${rule.note} — ${fileLabel}: 出現次數 ${n} < 要求 ${rule.min}（min）：${patternLabel(rule.pattern)}`);
  }
}

// ---- tag-scan：class-tag / nested-count / anchor-first-tag / window 四個 mode ----
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// port _tag_with_class 的 lookahead 寫法：<TAG\b(?=[^>]*class="[^"]*(?<![\w-])CLASS(?![\w-])[^"]*")[^>]*>
function buildTagWithClassRegex(tagName, className) {
  return new RegExp(
    `<${tagName}\\b(?=[^>]*class="[^"]*(?<![\\w-])${escapeRegExp(className)}(?![\\w-])[^"]*")[^>]*>`,
  );
}

function checkTagRequiredForbidden(rule, tag, fileLabel) {
  for (const p of rule.required || []) {
    if (!matches(tag, p)) {
      err(`${rule.note} — ${fileLabel}: tag 缺少必要內容：${patternLabel(p)}；tag=${tag.slice(0, 160)}`);
    }
  }
  // requiredAnyOf（96b-T3 新能力）：OR 語意，tag 只需命中其中之一即算通過（existing `required`
  // 陣列維持 AND-only，兩者可並存於同一 rule——目前只有 TestBurstPickerGuard 用到 requiredAnyOf）。
  if (rule.requiredAnyOf) {
    const hit = rule.requiredAnyOf.some((p) => matches(tag, p));
    if (!hit) {
      err(
        `${rule.note} — ${fileLabel}: tag 缺少必要內容之一（any-of）：` +
          `${rule.requiredAnyOf.map(patternLabel).join(' OR ')}；tag=${tag.slice(0, 160)}`,
      );
    }
  }
  for (const p of rule.forbidden || []) {
    if (matches(tag, p)) {
      err(`${rule.note} — ${fileLabel}: tag 不應含有：${patternLabel(p)}；tag=${tag.slice(0, 160)}`);
    }
  }
}

function evalTagScanClassTag(rule, text, fileLabel) {
  const tagRe = rule.tagPattern || buildTagWithClassRegex(rule.tagName, rule.className);
  if (rule.multi) {
    const flags = tagRe.flags.includes('g') ? tagRe.flags : tagRe.flags + 'g';
    const re = new RegExp(tagRe.source, flags);
    const tags = [];
    let m;
    while ((m = re.exec(text)) !== null) tags.push(m[0]);
    if (rule.expectedCount !== undefined && tags.length !== rule.expectedCount) {
      err(`${rule.note} — ${fileLabel}: 符合的開標籤數量 ${tags.length} != 預期 ${rule.expectedCount}`);
    } else if (rule.expectedCount === undefined && tags.length === 0) {
      // multi 模式無 expectedCount 時（96b-T3 BurstPickerGuard 首次用到），0 個 match 必須明確
      // 報錯——否則 for-loop 對空陣列跑 0 次，會靜默通過（pytest 原始邏輯 `assert matches` 要求
      // 至少 1 個 tag 存在）。
      err(`${rule.note} — ${fileLabel}: 找不到符合 tagPattern 的開標籤（multi 模式仍需至少 1 個）`);
    }
    for (const tag of tags) checkTagRequiredForbidden(rule, tag, fileLabel);
  } else {
    const m = tagRe.exec(text);
    if (!m) {
      err(`${rule.note} — ${fileLabel}: 找不到符合 tagPattern 的開標籤（scope-anchor-failure）`);
      return;
    }
    checkTagRequiredForbidden(rule, m[0], fileLabel);
  }
}

// port ShowcaseToolbarStructureGuard 的兩輪 tag 掃描：先找對應結尾 </TAG> 界定區塊
// （單層 depth-tracking），再在區塊內只在 depth===0 時比對 attrs 是否含目標 class token。
function evalTagScanNestedCount(rule, text, fileLabel) {
  const outerM = rule.outerAnchor.exec(text);
  if (!outerM) {
    err(`${rule.note} — ${fileLabel}: 找不到 outerAnchor（${rule.outerAnchor}）`);
    return;
  }
  const blockStart = outerM.index + outerM[0].length;
  let pos = blockStart;
  let depth = 1;
  const boundaryRe = new RegExp(`<(/?)${rule.outerTagName}[\\s>]`, 'g');
  boundaryRe.lastIndex = pos;
  let bm;
  while (depth > 0 && (bm = boundaryRe.exec(text)) !== null) {
    if (bm[1] === '/') depth -= 1;
    else depth += 1;
    pos = boundaryRe.lastIndex;
  }
  if (depth > 0) {
    err(`${rule.note} — ${fileLabel}: outer block 到檔案結尾仍未平衡（depth=${depth}），視同 anchor 找不到`);
    return;
  }
  const block = text.slice(blockStart, pos);

  let directCount = 0;
  let innerDepth = 0;
  const tagRe = /<(\/?)([a-zA-Z0-9]+)(?:\s+([^>]*))?>/g;
  let tm;
  while ((tm = tagRe.exec(block)) !== null) {
    const closing = tm[1];
    const tagName = tm[2];
    const attrs = tm[3] || '';
    if (tagName.toLowerCase() !== rule.outerTagName.toLowerCase()) continue; // 只追蹤 outerTagName 深度（faithful port，Python tag_re 只認 div）
    if (closing) {
      innerDepth -= 1;
    } else {
      if (innerDepth === 0 && attrs.includes(rule.innerToken)) directCount += 1;
      innerDepth += 1;
    }
  }
  if (directCount !== rule.expected) {
    err(`${rule.note} — ${fileLabel}: 直接子 .${rule.innerToken} 數量 ${directCount} != 預期 ${rule.expected}`);
  }
}

// anchor 之後全文的「第一個」匹配 tag（offline Guard 3：<head> 之後第一個 <script>）
function evalTagScanAnchorFirstTag(rule, text, fileLabel) {
  const anchorM = rule.anchor.exec(text);
  if (!anchorM) {
    err(`${rule.note} — ${fileLabel}: 找不到 anchor（${rule.anchor}）`);
    return;
  }
  const after = text.slice(anchorM.index + anchorM[0].length);
  const tagM = rule.tagPattern.exec(after);
  if (!tagM) {
    err(`${rule.note} — ${fileLabel}: anchor 後找不到符合 tagPattern 的 tag`);
    return;
  }
  checkTagRequiredForbidden(rule, tagM[0], fileLabel);
}

// anchor 起固定字元數視窗（HeroImageErrorGuard CD-96-20(b) 強化：整視窗 forbidden 掃描 +
// requiredAttr 存在性斷言，非僅檢查該屬性值本身，關閉「搬移到視窗內其他屬性」的假綠缺口）
function evalTagScanWindow(rule, text, fileLabel) {
  const anchorM = rule.anchor.exec(text);
  if (!anchorM) {
    err(`${rule.note} — ${fileLabel}: 找不到 anchor（${rule.anchor}），非 pattern 缺席`);
    return;
  }
  const windowText = text.slice(anchorM.index, anchorM.index + rule.window);
  if (rule.requiredAttr && !rule.requiredAttr.test(windowText)) {
    err(`${rule.note} — ${fileLabel}: window 內缺少必要屬性：${patternLabel(rule.requiredAttr)}`);
  }
  for (const p of rule.forbidden || []) {
    if (matches(windowText, p)) {
      err(`${rule.note} — ${fileLabel}: window 內不應出現（CD-96-20(b) 整視窗掃描，非僅 @error 值）：${patternLabel(p)}`);
    }
  }
}

function evalTagScan(rule, text, fileLabel) {
  switch (rule.mode) {
    case 'class-tag':
      evalTagScanClassTag(rule, text, fileLabel);
      break;
    case 'nested-count':
      evalTagScanNestedCount(rule, text, fileLabel);
      break;
    case 'anchor-first-tag':
      evalTagScanAnchorFirstTag(rule, text, fileLabel);
      break;
    case 'window':
      evalTagScanWindow(rule, text, fileLabel);
      break;
    default:
      throw new Error('tag-scan mode not implemented: ' + rule.mode);
  }
}

// ---- inline-style-token（NoInlineStyleDisplay 專用：遞迴掃描見 file.recursive）----
function evalInlineStyleToken(rule, text, fileLabel) {
  // port _parse_elements 的 tag_re：容許屬性值內有 >（跳過雙/單/反引號區段）
  const tagRe = /<[a-zA-Z](?:[^>"'`]|"[^"]*"|'[^']*'|`[^`]*`)*>/gs;
  const displayNoneRe = /style\s*=\s*(["'])(?:(?!\1).)*display:\s*none/s;
  let m;
  while ((m = tagRe.exec(text)) !== null) {
    const tag = m[0];
    if (tag.includes('x-show') && displayNoneRe.test(tag)) {
      err(`${rule.note} — ${fileLabel}: style="display:none" 與 x-show 重複：${tag.replace(/\s+/g, ' ').slice(0, 100)}`);
    }
  }
}

// ---- order（獨立 kind：純字元位置比較，非 tag-scan 子模式）----
function findOccurrence(haystack, pattern, occurrence) {
  if (pattern instanceof RegExp) {
    const flags = pattern.flags.includes('g') ? pattern.flags : pattern.flags + 'g';
    const re = new RegExp(pattern.source, flags);
    let first = -1;
    let last = -1;
    let m;
    while ((m = re.exec(haystack)) !== null) {
      if (first === -1) first = m.index;
      last = m.index;
      if (m.index === re.lastIndex) re.lastIndex += 1; // 防零寬匹配無窮迴圈
    }
    return occurrence === 'last' ? last : first;
  }
  return occurrence === 'last' ? haystack.lastIndexOf(pattern) : haystack.indexOf(pattern);
}

function evalOrder(rule, text, fileLabel) {
  const { scopedText, ok } = resolveScope(rule, text, fileLabel);
  if (!ok) return;

  const positions = rule.items.map((item) =>
    findOccurrence(scopedText, item.pattern, item.occurrence || 'first'),
  );

  let missing = false;
  rule.items.forEach((item, idx) => {
    if (positions[idx] === -1) {
      missing = true;
      err(`${rule.note} — ${fileLabel}: order item 找不到（occurrence=${item.occurrence || 'first'}）：${patternLabel(item.pattern)}`);
    }
  });
  if (missing) return; // 已回報缺席，不繼續做可能失真的 pair 比較

  const pairs = rule.pairs || rule.items.slice(0, -1).map((_, i) => [i, i + 1]);
  for (const [i, j] of pairs) {
    if (!(positions[i] < positions[j])) {
      err(
        `${rule.note} — ${fileLabel}: order 違反：items[${i}]（${patternLabel(rule.items[i].pattern)}）@${positions[i]} ` +
          `應在 items[${j}]（${patternLabel(rule.items[j].pattern)}）@${positions[j]} 之前`,
      );
    }
  }
}

function evalRequiredString(rule, text, fileLabel) {
  const { scopedText, ok } = resolveScope(rule, text, fileLabel);
  if (!ok) return; // scope anchor 錯誤已回報，不繼續誤判 pattern 缺席

  const patterns = Array.isArray(rule.pattern) ? rule.pattern : [rule.pattern];

  if (rule.anyOf) {
    const hit = patterns.some((p) => matches(scopedText, p));
    if (!hit) {
      err(`${rule.note} — ${fileLabel}: any-of 全未命中（需其一）：${patterns.map(patternLabel).join(' OR ')}`);
    }
    return;
  }

  for (const p of patterns) {
    if (rule.count !== undefined) {
      const n = countOccurrences(scopedText, p);
      if (n < rule.count) {
        err(`${rule.note} — ${fileLabel}: 出現次數 ${n} < 要求 ${rule.count}：${patternLabel(p)}`);
      }
    } else if (!matches(scopedText, p)) {
      err(`${rule.note} — ${fileLabel}: 缺少必要字串/pattern：${patternLabel(p)}`);
    }
  }
}

function evalForbiddenString(rule, text, fileLabel) {
  const { scopedText, ok } = resolveScope(rule, text, fileLabel);
  if (!ok) return; // scope anchor 錯誤已回報

  const patterns = Array.isArray(rule.pattern) ? rule.pattern : [rule.pattern];
  for (const p of patterns) {
    if (matches(scopedText, p)) {
      err(`${rule.note} — ${fileLabel}: 不應出現卻出現：${patternLabel(p)}`);
    }
  }
}

// 載入時驗證：structure-count 的 count（exact）/ min（下界）必須恰好給一個
// （CD-96b-9 mutation #10：防呆非 runtime mutation，於此一次性靜態檢查全部 RULES）。
for (const rule of RULES) {
  if (rule.kind === 'structure-count') {
    const hasCount = rule.count !== undefined;
    const hasMin = rule.min !== undefined;
    if (hasCount === hasMin) {
      throw new Error(
        `structure-count rule 必須恰好給 count 或 min 其一（不可同時給/都不給）：${rule.note}`,
      );
    }
  }
}

// ---- cross-file-equal（101c-T1 新 kind，第 10 個）----
// 跨多個來源檔各自 exec 一個 pattern、取 capture group 1、parseFloat，全部相等才通過。
// 無單一 rule.file（改用 rule.sources），故在 main 迴圈頂部特殊分支攔截、不進 evalRule
// （比照 file-absent，但更前面：file-absent 仍有 rule.file 字串、在 typeof 分支內攔；
// 本 kind 無 rule.file，若落到 else 分支會解構 undefined 而 crash，必須在 typeof 判斷之前攔）。
// fail-closed：任一 source pattern 無匹配（常數被改名/刪除）即 err，不 vacuous-pass。
// CD-4：鎖「一致」非鎖固定值——不寫死期望數值，同步改綠、單改一邊紅。
// CSS block comment `/* … */` 剝除。lazy 量詞 `*?`：greedy `[\s\S]*` 會從第一個 `/*`
// 吃到最後一個 `*/`、把中間真宣告一併吞掉。用途：m-flag `^` 錨定會匹配到註解內被停用的
// `--actress-crop-ratio:` 宣告行，`.exec` 回第一個 match → 擷到註解舊值而非 active 值（假綠，
// Codex P2）。剝除後：真宣告仍匹配；若 active 宣告整段被註解掉、無 active 宣告 → 無匹配 →
// evalCrossFileEqual 的 fail-closed err（安全方向，宣告被移除/停用必轉紅）。
function stripCssBlockComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '');
}

function evalCrossFileEqual(rule) {
  const seen = [];
  for (const src of rule.sources) {
    let text = readTarget(src.file);
    if (text === null) {
      err(`${rule.note} — ${src.file}: 檔案不存在或無法讀取`);
      return;
    }
    // CSS 來源：比對前剝除 block comment，避免 m-flag `^` 匹配註解內停用的宣告行造成假綠
    // （correct-by-default：ratio parity 永遠不該匹配 CSS 註解內容）。Python 來源不套——其
    // `^_FOCAL_DETECT_RATIO` pattern 已用 `(?:#.*)?$` 排除行尾 `#` 註解，無 block comment 語法。
    if (src.file.endsWith('.css')) {
      text = stripCssBlockComments(text);
    }
    const m = src.pattern.exec(text);
    if (!m || m[1] === undefined) {
      err(`${rule.note} — ${src.file}: pattern ${patternLabel(src.pattern)} 無匹配（常數被改名/刪除？fail-closed）`);
      return;
    }
    seen.push({ file: src.file, value: parseFloat(m[1]), raw: m[1] }); // 地雷：預設 parseFloat 會把 0.15.17 截成 0.15，多段字面（如版本號）不可用本 kind
  }
  const first = seen[0].value;
  if (!seen.every((s) => s.value === first)) {
    const detail = seen.map((s) => `${s.file}=${s.raw}`).join(' ≠ ');
    err(`${rule.note} — ${rule.label || 'cross-file-equal'}: 值不一致（${detail}）`);
  }
}

// ---- main ----
for (const rule of RULES) {
  if (rule.kind === 'cross-file-equal') { evalCrossFileEqual(rule); continue; }
  if (typeof rule.file === 'string') {
    // file-absent（96b-T3 新能力）：反向邏輯，必須在通用 readTarget/read-fail-is-error 路徑
    // 之前攔截——檔案「存在」才是違規（舊檔忘記刪除），檔案「不存在」是預期的通過狀態。
    // 不進 fileCache（關心存在與否而非內容），也不透過 readTarget（避免落入其
    // 「text===null → err()」的通用錯誤路徑，那樣會把正確刪除舊檔誤判成違規）。
    if (rule.kind === 'file-absent') {
      const full = join(ROOT, rule.file);
      if (existsSync(full)) {
        err(`${rule.note} — ${rule.file}: 舊檔應已刪除但仍存在`);
      }
      continue;
    }
    const text = readTarget(rule.file);
    if (text === null) {
      err(`${rule.note} — ${rule.file}: 檔案不存在或無法讀取`);
      continue;
    }
    evalRule(rule, text, rule.file);
  } else {
    const { dir, ext, recursive, exclude } = rule.file;
    const files = listDirFiles(dir, ext, { recursive, exclude });
    if (files === null) {
      err(`${rule.note} — ${dir}: 目錄不存在或無法讀取`);
      continue;
    }
    for (const relPath of files) {
      const text = readTarget(relPath);
      if (text === null) {
        err(`${rule.note} — ${relPath}: 檔案不存在或無法讀取`);
        continue;
      }
      evalRule(rule, text, relPath);
    }
  }
}

if (hadError) {
  process.exit(1);
}
console.log(`✓ static_guard_lint: ${RULES.length} 條規則全數通過（required-string/forbidden-string/dup-id/structure-count/tag-scan/inline-style-token/order/paired-string/file-absent/cross-file-equal）`);
