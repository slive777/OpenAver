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
  ...[
    ['web/static/js/shared/burst-picker.js', 'window.BurstPicker', '/static/js/shared/burst-picker.js'],
    ['web/static/js/components/motion-adapter.js', 'window.OpenAver.motion', '/static/js/components/motion-adapter.js'],
    ['web/static/js/components/page-lifecycle.js', 'window.__registerPage', '/static/js/components/page-lifecycle.js'],
    ['web/static/js/components/motion-prefs.js', 'window.OpenAver', '/static/js/components/motion-prefs.js'],
  ].flatMap(([file, bridge, scriptPath]) => ([
    { file, kind: 'required-string', pattern: 'export', note: `[TestESMExportGuard] ${file} export` },
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
  { file: 'web/static/js/pages/settings/main.js', kind: 'required-string', pattern: 'getOwnPropertyDescriptors', note: '[TestSettingsESMGuard] test_main_js_uses_descriptor_merge (required half)' },
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
    file: 'web/static/js/pages/scanner/main.js', kind: 'required-string', anyOf: true,
    pattern: ['getOwnPropertyDescriptors', 'defineProperties'],
    note: '[TestScannerESMGuard] test_main_js_has_descriptor_merge — OR（非 AND，與 settings 頁只有 required 半邊不同）',
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
    file: 'web/static/js/pages/showcase/main.js', kind: 'required-string', anyOf: true,
    pattern: ['getOwnPropertyDescriptors', 'defineProperties'],
    note: '[TestShowcaseESMGuard] test_main_js_has_descriptor_merge — OR',
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
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: 'Object.getOwnPropertyDescriptors', note: '[TestSearchESMGuard] test_main_js_uses_merge_state_not_spread — AND 半邊 1/2（與 settings/scanner/showcase 頁「OR 或未檢查」不同，search 是唯一 AND 兩者皆要）' },
  { file: 'web/static/js/pages/search/main.js', kind: 'required-string', pattern: 'Object.defineProperties', note: '[TestSearchESMGuard] test_main_js_uses_merge_state_not_spread — AND 半邊 2/2' },
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
  // 7 檔白名單（動態座標計算 / adapter 本體 / per-host lifecycle 合法呼叫，與來源 pytest
  // allowed_files 完全對齊）：
  //   components/motion-adapter.js、pages/motion-lab.js、pages/motion-lab-state.js、
  //   pages/search/animations.js、pages/showcase/animations.js、
  //   pages/motion-lab/constellation-host.js、pages/showcase/state-similar.js。
  // exclude 比對「相對於 dir 的相對路徑」（非 basename）：basename 比對會讓未來新增的同名檔
  // （如 pages/foo/animations.js）被誤放行，故改用完整相對路徑，與來源 pytest 語意一致
  // （Codex P2 fix，2026-07）。
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
    note: '[TestMotionInfra] test_no_direct_gsap_calls_in_pages — pages/**/*.js 禁直接 GSAP/ScrollTrigger 呼叫（白名單 6 檔 exclude by-relpath）',
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
    default:
      throw new Error('kind not implemented: ' + rule.kind);
  }
}

// scope 三種形式：單一 RegExp（T1）/ {anchor, window}（固定字元數視窗）/
// {anchor, braceBalanced}（大括號平衡方法體抽取，port Python _extract_method_body）。
function resolveScope(rule, text, fileLabel) {
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

// ---- main ----
for (const rule of RULES) {
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
console.log(`✓ static_guard_lint: ${RULES.length} 條規則全數通過（required-string/forbidden-string/dup-id/structure-count/tag-scan/inline-style-token/order）`);
