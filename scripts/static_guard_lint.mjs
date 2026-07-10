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
 * ESM/JS-structure 家族（`esmPages` 子表）留給 T3，本 task 不實作。
 *
 * 用法：
 *   node scripts/static_guard_lint.mjs                 # 掃真 repo
 *   node scripts/static_guard_lint.mjs <scratch-root>   # 掃 scratch 副本（供 mutation 自驗）
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

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
// recursive:true 為 rglob 語意（NoInlineStyleDisplay 需要，含子目錄）；exclude 排除特定檔名
// （NoHardcodedColors 需要，排除 design-system.html / motion_lab.html 兩個 demo 頁）。
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
      if (e.isFile() && exts.some((ext) => e.name.endsWith(ext)) && !exclude.includes(e.name)) {
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
    // ESM/JS-structure 家族（esmPages 子表）留給 T3，本 task 不實作
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
