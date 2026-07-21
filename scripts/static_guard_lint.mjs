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
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: "searchFromMetadata(currentLightboxVideo?.director)", note: '[TestShowcaseMetadataGuard] searchFromMetadata call' },
  {
    file: 'web/templates/showcase.html', kind: 'required-string', anyOf: true,
    pattern: ["searchFromMetadata(video.series)", "searchFromMetadata(currentLightboxVideo?.series)"],
    note: '[TestShowcaseMetadataGuard] series searchFromMetadata call (grid panel or lightbox, OR)',
  },

  // ---- [lint-guard 101d-T2] 焦點適用邊界就地註解不得被順手刪（spec-101 §7.3-2 要求就地註解；plan-101d §5.2/§5.3）----
  // 錨四處「刻意不同/刻意不接」設計意圖註解的唯一關鍵句。刪任一句即紅（mutation 自驗）。
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: 'per-image 門檻刻意不同', note: '[lint-guard 101d-T2] 影片 gate≠女優 gate 就地註解（plan-101d §2.2）' },
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '與影片 _posterModeActive() 刻意不同', note: '[lint-guard 101d-T2] 女優側反向指引註解（plan-101d §2.2）' },
  { file: 'web/static/css/pages/showcase.css', kind: 'required-string', pattern: '相似卡刻意固定右裁（桌面', note: '[lint-guard 101d-T2] 桌面 similar 卡固定右裁註解（plan-101d §5.3）' },
  { file: 'web/static/css/pages/showcase.css', kind: 'required-string', pattern: '相似卡刻意固定右裁（手機 burst', note: '[lint-guard 101d-T2] 手機 burst similar 卡固定右裁註解（plan-101d §5.3）' },

  // ---- [TestMaskToggleGuard] 98b-T4 起家、99a-T3 沿用：遮罩綁定 / 生命週期 guard / no-硬編-ratio / endpoint URL ----
  { file: 'web/templates/showcase.html', kind: 'required-string', pattern: '@click="openMask', note: '[TestMaskToggleGuard] mask toggle icon button 綁 openMask' },
  // 98b P2 fix（Codex）：commit/re-check guard 由 path 比對（_maskVideoPath/sessionPath）
  // 升級為單調遞增 session id（_maskSession）——path 比對在「同片重開」邊界不夠精確。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'this._maskSession++',
    scope: { anchor: /openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] openMask 遞增 _maskSession（每次開啟即新 session，Codex P2）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'this._maskSession++',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _resetMask 遞增 _maskSession（換片/關燈箱使舊 session 失效，Codex P2）',
  },
  // 98b P2 fix(二)（Codex）：新 session 起手/invalidate 必須清 _maskDetecting——舊 detect await 的
  // finally 因 session 不符會跳過清 spinner，不在此重置則新遮罩頂著卡死 spinner。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'this._maskDetecting = false',
    scope: { anchor: /openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] openMask 清 _maskDetecting（新 session 起手非偵測中，防舊 spinner 漏入，Codex P2）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'this._maskDetecting = false',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _resetMask 清 _maskDetecting（invalidate 時防偵測態漏進下個 session，Codex P2）',
  },
  // 99a-T3：原本錨定 `async toggleMaskMode()` / `async closeMask()` 的兩條 session-recheck 規則
  // 因該兩函式整條移除而 anchor-not-found（引擎不變式：硬錯，阻斷 npm run lint）。改錨定承接
  // 相同語意的新函式——toggleMaskMode 的「翻頁後 session recheck」併入 openMask 自身的
  // force-detect await；closeMask 的「async 存檔前後 session recheck」由 confirmMask 承接。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'session === this._maskSession',
    scope: { anchor: /async\s+openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] openMask force-detect await 後 session re-check（不誤動已切走的別片 UI；99a-T3 承接原 toggleMaskMode 語意）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'session === this._maskSession',
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] confirmMask await 後 session re-check（不誤存已切走的別片；99a-T3 承接原 closeMask 語意）',
  },
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: '_maskVideoPath', note: '[TestMaskToggleGuard] 舊 path-based guard 變數不得復活（已由 _maskSession 取代，Codex P2）' },
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
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '/api/showcase/video/detect-focal', note: '[TestMaskToggleGuard] detect-focal endpoint fetch URL' },
  // [lint-guard 101d-T3] 影片對焦存檔端點不得復名為 `/api/showcase/video/focal`——該路徑「video/ 緊接 focal」
  // 像影片廣告 beacon，會被 ad/privacy 過濾清單（uBlock/AdGuard/Brave/Pi-hole）在瀏覽器端 net::ERR_FAILED
  // 秒殺，✓ 存檔請求根本到不了 server（2026-07-18 owner 實測 + CDP/Network 診斷）。正名 video/save-focal。
  // 註：`video/detect-focal`/`video/save-focal` 皆不含子字串 `video/focal`（video/ 後非恰為 focal）→ 不誤觸。
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: '/api/showcase/video/focal', note: '[lint-guard 101d-T3] 影片對焦存檔端點禁復名 video/focal（撞廣告過濾清單），用 video/save-focal' },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'getComputedStyle',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 讀 CSS var（getComputedStyle）非 JS 硬編比例',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '--poster-crop-ratio',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 讀 --poster-crop-ratio（單一真理）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: '0.71',
    scope: { anchor: /_computeMaskWinStyle\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] _computeMaskWinStyle 不得硬編 0.71（比例讀 CSS var）',
  },
  {
    // 99a Gemini P2 回歸鎖：拖曳起手的 startLeft 必須 clamp（否則臉貼邊時窗子停在界內、
    // 拖曳從界外起算＝死區）。刻意鎖「const startLeft = clampMaskWinLeft(」整串而非裸的
    // Math.max/Math.min——後者在 _maskDragStart 的 brace scope 內另有 onMove 也在用，
    // 會 fail-open（拔掉起手 clamp 仍綠）。
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'const startLeft = clampMaskWinLeft(',
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a：_maskDragStart 起手 startLeft 須經 clampMaskWinLeft 鉗進封面邊界',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: /2\s*\/\s*3/,
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: '_maskDragStart(evt) {',
    note: '[TestMaskToggleGuard] 99a-T4：拖曳起手函式定義存在',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'toggleMaskMode',
    note: '[TestMaskToggleGuard] 99a-T4：退役 toggle handler 不得復活（thorough-cleanup lock）',
  },

  // §2 退役識別字 forbidden-string（3，比照既有 _maskVideoPath 先例 :136）：_maskMode/closeMask
  // 全域零殘留，本 task 補鎖住這個「巧合乾淨」的狀態，防未來以舊名復活。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: '_maskMode',
    note: '[TestMaskToggleGuard] 99a-T4：退役 default⇄auto toggle 狀態不得復活（thorough-cleanup lock）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'closeMask',
    note: '[TestMaskToggleGuard] 99a-T4：退役「點窗外隱式存」函式不得以舊名復活（confirmMask/cancelMask 已取代）',
  },
  {
    file: 'web/templates/_macros/focal_mask.html', kind: 'forbidden-string', pattern: 'closeMask',
    note: '[TestMaskToggleGuard] 99a-T4：overlay @click.self 不得指回舊 closeMask（現為 cancelMask）',
  },

  // §3 拖曳 listener 對稱 add/remove（6，scope-anchored——flat required-string 驗不出「掛在對的
  // 函式、解在對的函式」，見 TASK-99a-T4 技術要點 §3 的「錯位置」反例）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "document.addEventListener('pointermove'",
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskDragStart 掛 pointermove（拖曳跟手核心）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "document.addEventListener('pointerup'",
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskDragStart 掛 pointerup（放開結束拖曳）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "document.addEventListener('pointercancel'",
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskDragStart 掛 pointercancel（系統中斷手勢時仍收尾，防洩漏）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "document.removeEventListener('pointermove'",
    scope: { anchor: /_maskRemoveDragListeners\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskRemoveDragListeners 對稱移除 pointermove（防洩漏）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "document.removeEventListener('pointerup'",
    scope: { anchor: /_maskRemoveDragListeners\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T4：_maskRemoveDragListeners 對稱移除 pointerup（防洩漏）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'cancelMask() {',
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
    pattern: 'x-show="(!currentLightboxVideo?.has_cover || !currentLightboxVideo?.has_nfo) && !_maskVisible"',
    note: '[TestMaskToggleGuard] 99a-T4：補缺鈕編輯中暫隱（CD-6，錨完整值防 has_cover/has_nfo 條件被誤刪只剩 !_maskVisible）',
  },

  // ---- [TestMaskToggleGuard] 99a-T5：detect-first 重新設計（Bug 1 修法）+ 星空等待動畫 lifecycle ----
  // 舊 race 旗標退役（比照既有 _maskVideoPath/_maskMode/closeMask 先例 :136/193/197/201）。
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: '_maskUserAdjusted', note: '[TestMaskToggleGuard] 99a-T5：detect-first 重新設計後 race 在結構上不可能，舊自查補強旗標不得復活（thorough-cleanup lock）' },

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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'playFocalDetectWait',
    scope: { anchor: /async\s+openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：openMask 啟動星空等待動畫（單一入口）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'prefersReducedMotion',
    scope: { anchor: /async\s+openMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：openMask 啟動星空動畫前 PRM guard（C23 per-callsite，比照 state-similar.js isPRM pattern）',
  },

  // _maskStopWaitAnim 對稱停止 helper：定義存在 + 內部呼叫 GhostFly.stopFocalDetectWait +
  // 三個生命週期端點（openMask finally / _resetMask / _maskTeardown）都呼叫它（比照既有
  // _maskRemoveDragListeners 的「定義一次、多處對稱呼叫」寫法）。
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopWaitAnim() {', note: '[TestMaskToggleGuard] 99a-T5：星空等待動畫對稱停止 helper 函式定義存在' },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'stopFocalDetectWait',
    scope: { anchor: /_maskStopWaitAnim\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：_maskStopWaitAnim 呼叫 GhostFly.stopFocalDetectWait',
  },
  {
    // 101b-T2（§A-5 修訂框）改鎖：_maskStopWaitAnim() 隨 fallback 分支搬進 _maskStartSettle
    // （openMask finally 現在只呼叫 _maskStartSettle(sawFace)，不再直呼 _maskStopWaitAnim()）
    // ⇒ 該字面字串離開 openMask 的 brace scope，anchor 必須跟著改指 _maskStartSettle。
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopWaitAnim()',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'handoffFocalDetectWait(this._maskWaitTl)',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T2（CD-4b）：_maskStartSettle 正常路徑呼叫 GhostFly.handoffFocalDetectWait(this._maskWaitTl) 交棒星空（不 clearProps）',
  },
  {
    // 101b-T2（CD-4c）：C23 per-callsite PRM guard 隨 gate 搬進 _maskStartSettle（比照既有 :344
    // openMask 內的同名 required rule——canAnimate 的組成之一）。
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'prefersReducedMotion',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '&& this._maskWaitTl',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'hasFace ? g0',
    scope: { anchor: /_maskStartSettle\s*\(\s*hasFace\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T5：_maskStartSettle 步驟③ no-face 落基準幾何（hasFace ? g0 : _computeMaskWinStyle()），不永久停在全幅',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopWaitAnim()',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 99a-T5：_resetMask 呼叫 _maskStopWaitAnim（換片/關燈箱/ESC 中斷路徑）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopWaitAnim()',
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
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopSettleAnim() {',
    note: '[TestMaskToggleGuard] 101b-T3：收斂補間對稱停止 helper 函式定義存在' },

  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopSettleAnim()',
    scope: { anchor: /_maskDragStart\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T3（CD-10）：_maskDragStart 拖曳接管呼叫 _maskStopSettleAnim' },

  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopSettleAnim()',
    scope: { anchor: /_maskTeardown\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T3（§A-5）：_maskTeardown 防禦性再保險呼叫 _maskStopSettleAnim' },

  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_maskStopSettleAnim()',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 101b-T3（§A-5）：_resetMask 中斷路徑（換片/關燈箱/ESC）呼叫 _maskStopSettleAnim' },

  { file: 'web/templates/_macros/focal_mask.html', kind: 'required-string', pattern: "'lb-mask-window--settling': _maskSettling",
    note: '[TestMaskToggleGuard] 101b-T3（CD-5）：.lb-mask-window :class 綁 --settling guard class' },

  { file: 'web/static/css/pages/showcase.css', kind: 'required-string', pattern: '.lb-mask-window--settling',
    note: '[TestMaskToggleGuard] 101b-T3（CD-5/C21）：--settling class 停用 transition 規則存在' },

  // 101b-T6：修 spinner 靜止不轉——CDP 像素驗證證實根因是 <i class="bi spin"> 預設
  // display:inline（Bootstrap Icons 只把 .bi::before 偽元素設 inline-block），CSS transform
  // 對 non-replaced inline box 不產生視覺效果，animation 確實在跑（computed transform 逐
  // frame 變化）卻視覺靜止——這正是前兩次修法都沒解到、CDP 只量 computed transform 會被騙的
  // 病灶。只鎖 animation 字串仍可能假綠（拿掉 display:inline-block 那行，animation 字串仍在，
  // 但視覺照樣不轉）——兩條都鎖，anchor scope 到 .lb-mask-spinner .bi.spin 規則本體，
  // braceBalanced 防止改到其他規則的同名字串。
  { file: 'web/static/css/pages/showcase.css', kind: 'required-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
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
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'async _uploadActressPhoto(evt) {', note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 函式定義存在' },

  // 必踩點 #1（mutation 反向驗：拿掉這行 → 必紅）：同一檔案連選兩次 change 不會再觸發，
  // 排在 await（fetch）之前——scope 內若把這行搬到 fetch 之後，本規則仍會通過字面存在性
  // 檢查，但「排序」語意已由函式本體 review + CDP ⓪ 實測把關（lint 只鎖存在性）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "evt.target.value = '';",
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 必須清空 evt.target.value（同檔重選需要 change 再次觸發，spec §3.1 禁「點了沒反應」）',
  },
  // 必踩點 #6 上半（改資料無條件執行）：_syncActressesArray by-name 呼叫存在。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'this._syncActressesArray(capturedName, data);',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 上傳成功後同步 _syncActressesArray（stale-success #6 上半，改資料無條件做）',
  },
  // §B-2b 第三呼叫點：上傳成功後刷新 _actressPhotoLoaded（新圖需重新等載入/快取判定）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'this._refreshActressPhotoLoaded();',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 成功且仍是同一位女優時呼叫 _refreshActressPhotoLoaded（§B-2b 第三呼叫點）',
  },
  // CD-9：錯誤分流依 HTTP status，不依 body code；無 409。鎖 413/415 兩個字面分支存在，
  // 證明「依 status 分流」這個決策點沒被改寫成單一籠統 catch。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'resp.status === 413',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：CD-9 413→upload_too_large 分支存在',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'resp.status === 415',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：CD-9 415→upload_bad_format 分支存在',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'resp.status === 409',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：CD-9 明訂上傳無 409（v3 砍了 compare token），不得復活',
  },
  // 必踩點 #3（mutation 反向驗：把這行改成 this._closePicker() → 必紅）：失敗分支刻意
  // 與既有候選換圖的 catch（_onPickerSelect 呼叫 _closePicker()）分歧，不可關 picker。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'this._closePicker();',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'detect-focal',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'this.currentLightboxActress.photo_url = data.photo_url;',
    scope: { anchor: /async\s+_uploadActressPhoto\s*\(\s*evt\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T2b：_uploadActressPhoto 成功後顯式同步 currentLightboxActress.photo_url（CD-10 訂正：_fetchLiveAliases 的 Object.assign 讓「同物件」前提失效，缺此行燈箱主圖不換）',
  },
  // §B-2b 第四呼叫點（Opus 2026-07-16 裁決）：換候選成功換 URL 後亦須刷新，與上傳同形。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "this._syncActressesArray(targetObj.name, { auto_focal: data.auto_focal, crop_mode: 'manual' });",
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：confirmMask 女優分支補上 paginatedActresses[idx] 陣列側寫入（Opus 裁決 1）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: "if (kind === 'actress') {",
    scope: { anchor: /async\s+confirmMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4／Fix C 修正：confirmMask 陣列側寫入須 gate 在 kind===actress（video 分支沒有 paginatedActresses 可查，兩者是正交資料，不得誤觸發）——Fix B 把即時值 this._maskKind 改為 await 前捕獲的 kind 區域變數，pattern 同步更新',
  },
  // 🔴 防止已被推翻的錯誤前提復活：舊註解主張 actress 分支的 targetObj 與
  // paginatedActresses[idx] 恆為同一物件參考（本 branch 稱其為「CD-10 同物件參考」）——
  // 已被 CDP 實測推翻三次，本 branch 已為它付出代價（錯的理由比沒有理由更危險）。
  // 全檔禁止再出現這句字面舊註解。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: 'CD-10 同物件參考',
    note: '[TestMaskToggleGuard] 100b-T4：禁止復活已被 CDP 實測推翻的舊註解（currentLightboxActress 與 paginatedActresses[idx] 不保證同一物件，見 plan-100b.md CD-10 訂正框）',
  },

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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'if (this._pickerSelected) return;',
    scope: { anchor: /_onPickerHoverIn\s*\(\s*el\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：_onPickerHoverIn 互斥 guard 回歸鎖（裁決 5——.picker-candidate-card 是 div，:disabled 無效，改走此 @click guard）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'if (this._pickerSelected) return;',
    scope: { anchor: /async\s+_onPickerHoverOut\s*\(\s*el\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T4：_onPickerHoverOut 互斥 guard 回歸鎖（裁決 5，同上）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'order',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '--actress-crop-ratio',
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
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: '_maskExpectedFp',
    note: '[TestMaskToggleGuard] 100b-T5：v2 殘留識別字 _maskExpectedFp 不得復活（v3 無 token，CD-9/§B-1b 明訂）',
  },

  // spec §3.7-7「零偵測成本」：_uploadActressPhoto 已有同型規則（100b-T2b，:457-459）；
  // _onPickerSelect（換候選）是另一個不該觸發偵測的入口，同一責任、同一 scope 寫法，
  // T2b 當時刻意留給本 task（TASK-100b-T2.md 裁決 3）。
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string', pattern: 'detect-focal',
    scope: { anchor: /async\s+_onPickerSelect\s*\(\s*candidate\s*,\s*i\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100b-T5：spec §3.7-7 零偵測成本——_onPickerSelect scope 內不得出現 detect-focal',
  },

  {
    // 100c-T3a：軸向 modifier 已移除（CD-6：唯一可拖方向恆為橫向），cursor: ew-resize 契約
    // 搬進 .lb-mask-window 基礎規則——scope-anchored（非裸 required-string）：本檔附近仍可能
    // 有規劃註解字面提到「ew-resize」，裸的 required-string 會被那類註解假綠掉（本 branch
    // 已踩過三次的 fail-open 形狀）。錨定實際 CSS rule block，只在該 block 內斷言。
    file: 'web/static/css/pages/showcase.css', kind: 'required-string', pattern: 'ew-resize',
    scope: { anchor: /\.lb-mask-window\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T3a：.lb-mask-window 基礎規則的 cursor: ew-resize（Y 軸砍除後唯一可拖方向併回基礎規則，取代舊 grab；scope 錨定防同檔規劃註解假綠）',
  },

  // ---- [TestMaskToggleGuard] 100c-T3a：CD-11 Y 軸/軸向判定/凍結模式不得復活 ----
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: ['this._maskFocalY', 'this._maskAxis', 'this._maskFrozen', 'computeMaskAxis('],
    note: '[TestMaskToggleGuard] 100c-T3a／CD-11：Y 軸/軸向判定/凍結模式不得復活（spec-100c §3.3 廢止）——鎖程式碼形式（this. 前綴/呼叫括號），散文註解仍可提及裸名',
  },
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'const notEditing = !this._maskVisible;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件① !_maskVisible 無條件讀取',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'const hasPhoto = !!this.currentLightboxActress?.photo_url;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件② photo_url 無條件讀取',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'const loaded = this._actressPhotoLoaded;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件③ _actressPhotoLoaded 無條件讀取',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'const wideEnough = this._actressPhotoWideEnough;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1/CD-7）：_focalIconVisible 條件④ _actressPhotoWideEnough 無條件讀取（20% 門檻）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'const pickerClosed = !this._pickerOpen;',
    scope: { anchor: /_focalIconVisible\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-1）：_focalIconVisible 條件⑤ !_pickerOpen 無條件讀取（picker 開啟保護，搬出 .cover-actions 後 CSS gate 不再涵蓋，必須顯式擋）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'this._clearActressPhotoState()',
    scope: { anchor: /_refreshActressPhotoLoaded\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-5）：_refreshActressPhotoLoaded() 起手呼叫 _clearActressPhotoState()（切換/開啟女優先清兩旗標）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
    pattern: 'this._clearActressPhotoState()',
    scope: { anchor: /_resetMask\s*\(\s*\)\s*\{/, braceBalanced: true },
    note: '[TestMaskToggleGuard] 100c-T2（CD-5）：_resetMask() 呼叫 _clearActressPhotoState()（換片/關燈箱清兩旗標，其後必經 _refreshActressPhotoLoaded 重新判定）',
  },
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string',
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
  { file: 'web/static/js/pages/search/state/result-card.js', kind: 'required-string', pattern: "_setTimer('toast'", note: '[TestTimerTracking] result-card.js timer' },
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

  // ---- [TestStatePageCloakGuard] div.state-page 全 x-cloak（tag-scan class-tag multi） ----
  {
    file: 'web/templates/showcase.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'state-page', multi: true, expectedCount: 5,
    required: ['x-cloak'],
    note: '[TestStatePageCloakGuard] test_showcase_state_pages_cloaked — showcase.html 5 個 div.state-page 皆 x-cloak',
  },
  {
    file: 'web/templates/search.html', kind: 'tag-scan', mode: 'class-tag',
    tagName: 'div', className: 'state-page', multi: true, expectedCount: 2,
    required: ['x-cloak'],
    note: '[TestStatePageCloakGuard] test_search_state_pages_cloaked — search.html 2 個 div.state-page 皆 x-cloak',
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
  { file: 'web/templates/search.html', kind: 'required-string', pattern: "'has-cover': !actressLightboxMode() && !!currentLightboxVideo()?.cover && !_heroLightboxImageError", note: '[TestUS9SearchGridMobileFix] test_search_lightbox_has_cover_class' },

  // ---- [TestSkippedNfoMultipartToastGuard]（structure-count min，handoff 已解除留置 AD-96b-2） ----
  { file: 'web/static/js/pages/search/state/batch.js', kind: 'structure-count', pattern: 'skipped_nfo_multipart', min: 2, note: '[TestSkippedNfoMultipartToastGuard] test_skipped_nfo_multipart_flag_referenced — batch.js >=2 次（scrapeAll+scrapeSingle）' },

  // ---- [TestActressCoreMetadataVideoCount]（order + required，brace-balanced scope，handoff 已解除留置 AD-96b-2） ----
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: 'video_count',
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadata\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestActressCoreMetadataVideoCount] test_video_count_pushed_first — 方法體含 video_count',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string', pattern: 'showcase.unit.films',
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadata\s*\([^)]*\)\s*\{/, braceBalanced: true },
    note: '[TestActressCoreMetadataVideoCount] test_video_count_pushed_first — 方法體含 showcase.unit.films i18n key',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'order',
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadata\s*\([^)]*\)\s*\{/, braceBalanced: true },
    items: [
      { pattern: /parts\.push\([^)]*video_count[^)]*\)/ },
      { pattern: /parts\.push\([^)]*\.age[^)]*\)/ },
    ],
    note: '[TestActressCoreMetadataVideoCount] test_video_count_pushed_first — video_count push 必須在 age push 之前（前置，brace-balanced scope）',
  },
  {
    file: 'web/static/js/pages/showcase/state-actress.js', kind: 'required-string',
    pattern: /typeof\s+\w+\.video_count\s*===\s*['"]number['"]/,
    scope: { anchor: /(?:^|\n)\s*_actressCoreMetadata\s*\([^)]*\)\s*\{/, braceBalanced: true },
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
  ...['stateBase()', 'stateVideos()', 'stateActress()', 'stateLightbox()'].map((fn) => ({
    file: 'web/static/js/pages/showcase/main.js', kind: 'forbidden-string', pattern: `...${fn}`,
    note: '[TestShowcaseESMGuard] test_main_js_no_plain_spread_merge — 4 factory 全禁',
  })),
  ...['stateBase', 'stateVideos', 'stateActress', 'stateLightbox'].map((fn) => ({
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: `${fn}.call(this)`,
    note: '[TestShowcaseESMGuard] test_main_js_factory_calls_use_call_this — 唯一有此斷言的頁（settings/scanner/search 皆未檢查）',
  })),
  { file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', pattern: 'window.showcaseState', note: '[TestShowcaseESMGuard] test_main_js_has_window_showcase_state_bridge — 唯一有 window bridge 斷言的頁' },
  ...['state-videos.js', 'state-actress.js', 'state-lightbox.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string',
    pattern: /^\s*import\b[^\n]*\b(?:stateBase|stateVideos|stateActress|stateLightbox)\b/m,
    note: `[TestShowcaseESMGuard] test_no_circular_state_factory_imports — ${file} 頂層 import 不可含 4 個 factory 函式名（判斷單位是 factory 名非檔名；state-base.js 本身不驗）`,
  })),
  { file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: '_killLightboxTimelines', note: '[TestShowcaseESMGuard] test_state_lightbox_imports_kill_timelines' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string', pattern: 'loadActresses', note: '[TestShowcaseESMGuard] test_state_videos_no_actress_functions' },
  { file: 'web/static/js/pages/showcase/state-videos.js', kind: 'forbidden-string', pattern: 'addFavoriteActress', note: '[TestShowcaseESMGuard] test_state_videos_no_actress_functions' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string', pattern: /^\s+openLightbox\s*\(/m, note: '[TestShowcaseESMGuard] test_state_actress_no_lightbox_functions — 方法定義 regex（行首縮排+openLightbox(，防誤殺 this.openLightbox(...) 呼叫）' },
  { file: 'web/static/js/pages/showcase/state-actress.js', kind: 'forbidden-string', pattern: /^\s+closeLightbox\s*\(/m, note: '[TestShowcaseESMGuard] test_state_actress_no_lightbox_functions' },
  ...['state-base.js', 'state-videos.js', 'state-actress.js', 'state-lightbox.js', 'main.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string',
    pattern: /^(?!\s)(?!\/\/)(?!\*)[^\n]*window\.gsap/m,
    note: `[TestShowcaseESMGuard] test_no_gsap_at_module_top_level — ${file} 頂層非註解行不可含 window.gsap`,
  })),
  ...['state-base.js', 'state-videos.js', 'state-actress.js', 'state-lightbox.js', 'main.js'].map((file) => ({
    file: `web/static/js/pages/showcase/${file}`, kind: 'forbidden-string',
    pattern: /^gsap\b/m,
    note: `[TestShowcaseESMGuard] test_no_gsap_at_module_top_level — ${file} 頂層行不可以 gsap 識別字開頭`,
  })),
  ...['state-base.js', 'state-videos.js', 'state-actress.js', 'state-lightbox.js'].map((file) => ({
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
  {
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'forbidden-string',
    pattern: /objectPosition[^\n]*right/,
    note: '[TestGhostFlyCropModeBoundary] test_caller_scope_no_object_position_right (state-lightbox.js) — 禁自算 objectPosition: right，須走 createCoverGhost(..., { cropMode })',
  },
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

  // ---- [TestMetatubePickerWiringGuard] 63c-3：進階 picker 接 metatube 真資料（proxy_configured 注入 / routable gate / metatube 分組未刪，5 個斷言） ----
  { file: 'web/templates/_advanced_search_bootstrap.html', kind: 'required-string', pattern: 'proxy_configured:', note: '[TestMetatubePickerWiringGuard] test_bootstrap_injects_proxy_configured' },
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

  // ---- [TestDmmProxyRequiredGuard] 63c-6：DMM requires_proxy 灰化，非-CSS 半邊（CSS 半邊已由 96c css-guard CG-RO-02 覆蓋，本段不重建）----
  // Scope A：clickActiveRowPill 函數體。⚠ Python 原始 regex 用 \Z（Python string-end anchor）+ re.DOTALL；
  // JS 無 \Z（\Z 在 JS regex 是字面 "Z"），faithful port 用 $（配合僅 's' flag、無 'm' flag，JS $ 即絕對字串結尾，等價 Python \Z）。
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'requires_proxy',
    scope: /clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|$)/s,
    note: '[TestDmmProxyRequiredGuard] test_click_active_row_pill_has_requires_proxy_intercept — Scope A（\\Z→$ port）',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'isDmmAvailable',
    scope: /clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|$)/s,
    note: '[TestDmmProxyRequiredGuard] test_click_active_row_pill_has_requires_proxy_intercept — Scope A（\\Z→$ port）',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'required-string', pattern: 'dmm_proxy_required_hint',
    scope: /clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|$)/s,
    note: '[TestDmmProxyRequiredGuard] test_click_active_row_pill_has_requires_proxy_intercept — Scope A（\\Z→$ port）',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js', kind: 'forbidden-string', pattern: 'window.confirm',
    scope: /clickActiveRowPill\s*\([^)]*\)\s*\{(.+?)(?=\n\s{8}\w|$)/s,
    note: '[TestDmmProxyRequiredGuard] test_click_active_row_pill_no_window_confirm — Scope A（\\Z→$ port）',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: ':data-proxy-required',
    scope: /x-for="s in activeRowSources"[^>]*>.*?<div\s+class="source-pill"(.*?)role="option"/s,
    note: '[TestDmmProxyRequiredGuard] test_settings_active_row_pill_has_data_proxy_required_binding — Scope B',
  },
  {
    file: 'web/templates/settings.html', kind: 'required-string', pattern: 'isDmmAvailable',
    scope: /x-for="s in activeRowSources"[^>]*>.*?<div\s+class="source-pill"(.*?)role="option"/s,
    note: '[TestDmmProxyRequiredGuard] test_settings_active_row_pill_proxy_required_uses_is_dmm_available — Scope B',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: /isSourceProxyBlocked\s*\([^)]*\)\s*\{/,
    note: '[TestDmmProxyRequiredGuard] test_state_rescrape_has_is_source_proxy_blocked — unscoped method-definition regex（同 T1 test_open_switch_source_picker_method_present 慣例）',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'proxy_configured',
    scope: /isSourceProxyBlocked\s*\([^)]*\)\s*\{([^}]+)\}/s,
    note: '[TestDmmProxyRequiredGuard] test_state_rescrape_is_source_proxy_blocked_reads_proxy_configured — Scope C',
  },
  {
    file: 'web/static/js/shared/state-rescrape.js', kind: 'required-string', pattern: 'requires_proxy',
    scope: /isSourceProxyBlocked\s*\([^)]*\)\s*\{([^}]+)\}/s,
    note: '[TestDmmProxyRequiredGuard] test_state_rescrape_is_source_proxy_blocked_reads_proxy_configured — Scope C',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: ':data-proxy-required',
    scope: /x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestDmmProxyRequiredGuard] test_rescrape_modal_builtin_pill_has_data_proxy_required — Scope D（與 Picker64a Scope E 同一 regex，同一 target）',
  },
  {
    file: 'web/templates/_rescrape_modal.html', kind: 'required-string', pattern: 'isSourceProxyBlocked',
    scope: /x-for="s in rescrapeBuiltinSources\(\)"[^>]*>.*?<button\s+([^>]+)>/s,
    note: '[TestDmmProxyRequiredGuard] test_rescrape_modal_builtin_pill_click_uses_is_source_proxy_blocked — Scope D',
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
    file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'OpenAver.motion.DURATION.', count: 8,
    note: '[TestMotionDurationConstants] test_animations_callers_use_duration_constants — js.count("OpenAver.motion.DURATION.") >= 8（min-bound；現況恰貼齊門檻，mutation 高風險列）',
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
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: "params.easing || 'fluent-decel'", note: '[TestShowcaseAnimationsFluent] test_animations_js_contains — playEntry' },
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
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'onEnter', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'onLeave', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'clearProps', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'return gsap.fromTo', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8 playFlipFilter returns tweens' },
  { file: 'web/static/js/pages/showcase/animations.js', kind: 'required-string', pattern: 'return gsap.to', note: '[TestShowcaseAnimationsGuard] test_animations_js_contains — B8' },
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
    file: 'web/static/js/pages/showcase/state-lightbox.js', kind: 'required-string', pattern: 'fetchSamples',
    note: '[TestFetchSamplesButton] test_core_js_contains — fetchSamples method（pin 到實際所在檔 state-lightbox.js）',
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
    pattern: 'x-show="showFavoriteActresses ? (!_pickerOpen && actressLightboxIndex > 0) : hasVisiblePrev()"',
    scope: { anchor: /<button class="lightbox-nav lightbox-nav-prev"/, window: 400 },
    note: '[nit-1 nav-arrow-picker] PR#108：picker 開啟時隱藏女優「上一位」箭頭（防死點擊）；影片分支 hasVisiblePrev() 維持零改動',
  },
  {
    file: 'web/templates/showcase.html', kind: 'required-string',
    pattern: 'x-show="showFavoriteActresses ? (!_pickerOpen && actressLightboxIndex < filteredActressCount - 1) : hasVisibleNext()"',
    scope: { anchor: /<button class="lightbox-nav lightbox-nav-next"/, window: 400 },
    note: '[nit-1 nav-arrow-picker] PR#108：picker 開啟時隱藏女優「下一位」箭頭（防死點擊）；影片分支 hasVisibleNext() 維持零改動',
  },
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

// ---- structure-count：count（exact）/ min（下界）二擇一 ----
function evalStructureCount(rule, text, fileLabel) {
  const { scopedText, ok } = resolveScope(rule, text, fileLabel);
  if (!ok) return;
  const n = countOccurrences(scopedText, rule.pattern);
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
    seen.push({ file: src.file, value: parseFloat(m[1]), raw: m[1] });
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
