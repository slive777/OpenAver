#!/usr/bin/env node
/**
 * css-guard.mjs — contextual/relational CSS-block guard（96c，zero-dep）
 *
 * 承接 stylelint 標準 rule 表達不了的 selector-scoped / relational / 存在性 /
 * 跨 media-block breakpoint 值對齊 / inline-style token 掃描（CD-96c-1〔b〕）。
 *
 * T1：骨架 + 兩 helper（stripCssComments / parseRuleBlocks，port 自
 * test_fluent_materials_guards.py 的 _strip_css_comments / _parse_rule_blocks）
 * + 空 RULES 表 + runner。實際規則於 T2–T4 落地（T2 fluent method、T3
 * poster-crop 家族 + handoff、T4 motion_lab inline）。
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
// 可傳 <scratch-root> 覆蓋 repo root（mutation 自驗指向 scratch 副本，不污染真檔，
// 比照 static_guard_lint.mjs <scratch-root> / i18n_lint.mjs <locale-dir> 房規）。
// 空殼 T1 下無 RULES 讀檔，故 arg 只需被接受即可（exit 0）；T2–T4 rule 透過
// CSS(rel) resolve target，scratch 副本自動生效。
const ROOT = process.argv[2] ? resolve(process.argv[2]) : join(__dirname, '..');
// rule 用此 resolve target CSS 檔（T2 起使用）
const CSS = (rel) => join(ROOT, 'web', 'static', 'css', rel);

let hadError = false;
function fail(msg) {
  console.error(`✗ css-guard: ${msg}`);
  hadError = true;
}

// ── ported helpers（忠實鏡射 Python，CD-96c-2；T2 起由 RULES 使用）──

// _strip_css_comments：移除 /* … */ 區塊註解（可跨行）
function stripCssComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '');
}

// _parse_rule_blocks：逐字元走訪追 brace depth，depth 歸 0 時收 {selector, declarations}。
// @media wrapper 自然被當 depth-1 外層、回傳最內層 rule block（忠實鏡射 Python 逐字元
// 迴圈，非 regex 猜大括號配對）。
function parseRuleBlocks(cssText) {
  const blocks = [];
  let depth = 0;
  let start = 0;
  let selector = '';
  let blockStart = 0;
  for (let i = 0; i < cssText.length; i += 1) {
    const ch = cssText[i];
    if (ch === '{') {
      if (depth === 0) {
        selector = cssText.slice(start, i).trim();
        blockStart = i + 1;
      }
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        blocks.push({ selector, declarations: cssText.slice(blockStart, i) });
        start = i + 1;
      }
    }
  }
  return blocks;
}

// re.escape port（token 名含 `-`，CG-FLU-12 需精確 escape，CD-96c-2）
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// @media (min-width:1024px) body 抽取（CG-FLU-09/10 11b；用 ctx.raw，鏡射 pytest css_raw）。
// parseRuleBlocks 對 @media wrapper 只回一個 depth-0 block，故需先 regex 抽 body 再 re-parse。
function extractDesktopMediaBodies(raw) {
  return [
    ...raw.matchAll(
      /@media\s*\(\s*min-width\s*:\s*1024px\s*\)\s*\{([\s\S]*?)\}(?=\s*(?:\/\*|@|[\[\.\#a-zA-Z]|$))/g,
    ),
  ].map((m) => m[1]);
}

// @media (max-width:480px) body 抽取（CG-FLU-14/15；手工 brace-walk，鏡射 pytest —
// 不用 parseRuleBlocks，否則抓到整個 @media body 而非單一 inner rule block）。
// 回傳 { body } 或 { err } — err 供 rule 決定失敗訊息。
function extractMobileMediaBody(css) {
  const m = css.match(/@media\s*\(\s*max-width\s*:\s*480px\s*\)\s*\{/);
  if (!m) return { err: 'no-media' };
  const braceIdx = m.index + m[0].length - 1; // '{' 位置（鏡射 pytest m.end()-1）
  let depth = 0;
  let end = null;
  for (let i = braceIdx; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    else if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === null) return { err: 'unbalanced' };
  return { body: css.slice(braceIdx + 1, end) }; // 鏡射 pytest css[m.end():end]
}

// 泛化 extractDesktopMediaBodies（T3）：對每個 @media，若 header 符合 condRegex（非-global）
// 則 balanced-brace 掃出 body。忠實 port TestPosterCropExtended._media_blocks（live L11679-11697）
// 與 TestSettingsHelpMobilePatch._media_480_block（live L11597）的平衡括號法（CD-96c-2），取代
// 各 pytest 脆弱的 `@media (...) {(.*?)\n\}` 收尾。condRegex 錨定（^...$）即等同 pytest 的字面 header
// 比對；condRegex 放鬆（如 /min-width:\s*481px/）即等同 _media_blocks 的子字串比對。
function extractMediaBodies(css, condRegex) {
  const blocks = [];
  const mediaRe = /@media\b([^{]*)\{/g;
  let m;
  while ((m = mediaRe.exec(css)) !== null) {
    if (!condRegex.test(m[1])) continue;
    let depth = 1;
    let i = mediaRe.lastIndex;
    while (i < css.length && depth > 0) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') depth -= 1;
      i += 1;
    }
    blocks.push(css.slice(mediaRe.lastIndex, i - 1));
    // 不 reset lastIndex — 忠實鏡射 python re.finditer（含 nested @media 亦會被獨立掃描）
  }
  return blocks;
}

// port `re.search(r'([^{}]*)\{[^{}]*<value>[^{}]*\}', block, DOTALL)` → 回「含某宣告值的那條規則
// 自身的 selector 文字」（US5/US9/US11 silent-no-op 守衛核心，live L10156-10164）。回 null 表未命中。
function ruleBoundSelector(block, valueRegex) {
  const combined = new RegExp(`([^{}]*)\\{[^{}]*(?:${valueRegex.source})[^{}]*\\}`, 's');
  const m = block.match(combined);
  return m ? m[1] : null;
}

// port `_rule_body`：回傳第一個匹配 selector 的規則 body（單層，不含巢狀）。回 null 表未命中。
function ruleBody(css, selectorSource) {
  const m = css.match(new RegExp(`${selectorSource}\\s*\\{([^}]*)\\}`));
  return m ? m[1] : null;
}

// port TestRescrapeModalGuard._zindex_of（live）：抽 `selector { … z-index: N }` 的整數。
// selector 是 rule head 的字面子字串（escapeRegExp 後比對），忠實鏡射 pytest 的
// `re.escape(selector) + r"\s*\{[^}]*?z-index:\s*(\d+)"`（DOTALL；[^}] 已界定 block 邊界）。
// 回 null 表未命中（rule 據此 fail，對應 pytest 的 assert m）。
function zindexOf(css, selector) {
  const m = css.match(new RegExp(`${escapeRegExp(selector)}\\s*\\{[^}]*?z-index:\\s*(\\d+)`, 's'));
  return m ? parseInt(m[1], 10) : null;
}

// T4 inline-style scan mode：抽 motion_lab.html 所有 <style>…</style> block 內容合併（忠實鏡射
// TestMotionLabHtmlHardcoded/TestMotionLabObjectPositionGuard 的 _style_blocks：
// `re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL)` join `\n`；`[\s\S]*?` = Python DOTALL `.*?`）。
function extractStyleBlocks(html) {
  return [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n');
}

// T3 poster-crop 家族 @media header 錨定條件（^...$ ⇔ pytest 字面 `@media (max-width: Npx) {`，
// 排除 compound / coarse / comment 內 @media 誤命中）。
const MW480 = /^\s*\(\s*max-width\s*:\s*480px\s*\)\s*$/;
const MW899 = /^\s*\(\s*max-width\s*:\s*899px\s*\)\s*$/;
const MW899_COARSE = /^\s*\(\s*max-width\s*:\s*899px\s*\)\s+and\s+\(\s*pointer\s*:\s*coarse\s*\)\s*$/;
const MW1024 = /^\s*\(\s*max-width\s*:\s*1024px\s*\)\s*$/;
const MIN481_MAX899 = /^\s*\(\s*min-width\s*:\s*481px\s*\)\s+and\s+\(\s*max-width\s*:\s*899px\s*\)\s*$/;
const IS_SCOPE = ':is(#ds-gallery-components, .ds-gallery-composition)';

// ── kind dispatcher（宣告式 selector-forbid / selector-require + fn escape-hatch）──
const KINDS = {
  // selector-block 負向屬性禁令：markers 全命中的 block 內 pattern 必不存在
  'selector-forbid': (rule, ctx) => {
    for (const { selector, declarations } of ctx.blocks) {
      if (!rule.markers.every((mk) => selector.includes(mk))) continue;
      if (rule.pattern.test(declarations)) ctx.fail(`${rule.id}: ${rule.msg} — ${selector}`);
    }
  },
  // selector-block 正向值斷言：markers block 必存在 + pattern 必命中（缺 block 亦違規）
  'selector-require': (rule, ctx) => {
    let found = false;
    for (const { selector, declarations } of ctx.blocks) {
      if (!rule.markers.every((mk) => selector.includes(mk))) continue;
      found = true;
      if (!rule.pattern.test(declarations)) ctx.fail(`${rule.id}: ${rule.msg} — ${selector}`);
    }
    if (!found) ctx.fail(`${rule.id}: ${rule.msg} — block 不存在`);
  },
  // bespoke relational escape-hatch
  fn: (rule, ctx) => rule.check(ctx),
};

const UNSCOPED_SHELL_TOPBARS = ['.search-bar', '.settings-header', '.avlist-header', '.showcase-toolbar'];
const SHELL_TOKENS = [
  '--glass-shell-gradient',
  '--glass-shell-fill',
  '--glass-shell-saturate',
  '--glass-shell-edge-top',
  '--glass-shell-edge-bottom',
  '--glass-shell-border',
];
const NON_SHELL_ROLE_MARKERS = {
  panel: '.help-card',
  caption: '.av-card-preview-footer',
  overlay: '.lightbox-content',
  'media-frame': '.similar-slot',
};

// ── 表驅動 rule-set（fluent 家族 14 條，忠實 port test_fluent_materials_guards.py，CD-96c-2）──
const RULES = [
  // CG-FLU-01 ← test_non_shell_backdrop_filter_dim_scoped
  {
    id: 'CG-FLU-01',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      for (const { selector, declarations } of ctx.blocks) {
        const bfValues = [
          ...declarations.matchAll(/(?<!-webkit-)backdrop-filter\s*:\s*([^;}]+)/g),
        ].map((m) => m[1]);
        if (bfValues.length === 0) continue;
        // 全部 backdrop-filter 值皆 explicit `none` → 例外（literal，不會 IACVT-fail）
        if (bfValues.every((v) => v.replace(/!important/g, '').trim() === 'none')) continue;
        const clean = selector.replace(/@media\s*\([^)]*\)\s*/g, '').trim();
        if (clean.includes('[data-theme="dim"]')) continue;
        if (UNSCOPED_SHELL_TOPBARS.some((cls) => clean.includes(cls))) continue;
        ctx.fail(
          `CG-FLU-01: backdrop-filter outside [data-theme="dim"] scope (not a whitelisted 77d chrome top-bar) — ${selector}`,
        );
      }
    },
  },

  // CG-FLU-02 ← test_no_hardcoded_blur_literal（whole-text, property-agnostic — Codex PR P2: 補
  // custom-property/非-filter 屬性缺口。stylelint 的 declaration-property-value-disallowed-list
  // 只掃 filter/backdrop-filter 宣告值，會漏 --custom-blur: blur(8px) 這類存在自訂屬性裡、之後
  // 才被 var() 消費的字面值。此 rule 對整份 comment-stripped 檔案做逐字掃描，忠實鏡射被刪的
  // pytest test_no_hardcoded_blur_literal 的 re.search(r"blur\(\s*\.?\d", css_no_comments)。）
  {
    id: 'CG-FLU-02',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      if (/blur\(\s*\.?\d/.test(ctx.text)) {
        ctx.fail(
          'CG-FLU-02: fluent-materials.css hardcoded blur literal — 用 blur(var(--fluent-blur...))；' +
            'whole-text scan（含 custom property），忠實 port test_no_hardcoded_blur_literal',
        );
      }
    },
  },

  // CG-FLU-03 ← test_webkit_backdrop_filter_pairing（line-adjacency，用 ctx.text）
  {
    id: 'CG-FLU-03',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const lines = ctx.text.split('\n');
      let i = 0;
      while (i < lines.length) {
        const line = lines[i].trim();
        const m = line.match(/^(?<!-webkit-)backdrop-filter\s*:\s*(.+)/);
        if (m && !line.startsWith('-webkit-')) {
          const value = m[1].replace(/;+$/, '').trim();
          let j = i + 1;
          while (j < lines.length && lines[j].trim() === '') j += 1;
          if (j < lines.length) {
            const nextLine = lines[j].trim();
            const wm = nextLine.match(/^-webkit-backdrop-filter\s*:\s*(.+)/);
            if (wm) {
              const webkitValue = wm[1].replace(/;+$/, '').trim();
              if (value !== webkitValue) {
                ctx.fail(
                  `CG-FLU-03: backdrop-filter ${JSON.stringify(value)} but -webkit- has ${JSON.stringify(webkitValue)} (line ${i + 1})`,
                );
              }
            } else {
              ctx.fail(
                `CG-FLU-03: backdrop-filter ${JSON.stringify(value)} not followed by -webkit-backdrop-filter (line ${i + 1}, got ${JSON.stringify(nextLine)})`,
              );
            }
          }
        }
        i += 1;
      }
    },
  },

  // CG-FLU-04 ← test_caption_footer_no_backdrop_filter（selector-scoped 負向）
  {
    id: 'CG-FLU-04',
    file: 'components/fluent-materials.css',
    kind: 'selector-forbid',
    markers: ['.av-card-preview-footer'],
    pattern: /backdrop-filter\s*:/,
    msg: '.av-card-preview-footer must not have backdrop-filter (90-card perf)',
  },

  // CG-FLU-05 ← test_lightbox_metadata_hairline（selector-scoped 正向值）
  {
    id: 'CG-FLU-05',
    file: 'components/fluent-materials.css',
    kind: 'selector-require',
    markers: ['.lightbox-metadata', '[data-theme="dim"]'],
    pattern: /background\s*:\s*transparent/,
    msg: '[data-theme="dim"] .lightbox-metadata must set background: transparent',
  },

  // CG-FLU-06 ← test_modal_box_not_solid（正向 has-overlay + 負向 not-surface-2 複合）
  {
    id: 'CG-FLU-06',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      let found = false;
      for (const { selector, declarations } of ctx.blocks) {
        if (!(selector.includes('.fluent-modal-box') && selector.includes('[data-theme="dim"]'))) continue;
        found = true;
        const hasOverlay = /--glass-overlay-modal-fill/.test(declarations)
          || /--glass-overlay-fill-gradient/.test(declarations)
          || /border-box/.test(declarations);
        if (!hasOverlay) {
          ctx.fail(
            `CG-FLU-06: [data-theme="dim"] .fluent-modal-box must reference --glass-overlay-modal-fill or border-box gradient — ${selector}`,
          );
        }
        if (/background\s*:\s*var\(--surface-2\)/.test(declarations)) {
          ctx.fail(
            `CG-FLU-06: [data-theme="dim"] .fluent-modal-box must NOT set background: var(--surface-2) (solid breaks overlay glass) — ${selector}`,
          );
        }
      }
      if (!found) ctx.fail('CG-FLU-06: [data-theme="dim"] .fluent-modal-box block 不存在');
    },
  },

  // CG-FLU-07 ← test_similar_main_static_no_transition_transform（逐 transition 宣告檢 transform）
  {
    id: 'CG-FLU-07',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      for (const { selector, declarations } of ctx.blocks) {
        if (!(selector.includes('.similar-main-static') && selector.includes('[data-theme="dim"]'))) continue;
        const transitions = declarations.match(/transition\s*:[^;]+/g) || [];
        for (const t of transitions) {
          if (t.includes('transform')) {
            ctx.fail(
              `CG-FLU-07: [data-theme="dim"] .similar-main-static must NOT reference transform in a transition (C21 GSAP guard): ${JSON.stringify(t)}`,
            );
          }
        }
      }
    },
  },

  // CG-FLU-08 ← test_gsap_animating_guard_exists_in_theme_css（跨檔 theme.css 存在 + 值）
  {
    id: 'CG-FLU-08',
    file: 'theme.css',
    kind: 'selector-require',
    markers: ['.av-card-preview.gsap-animating'],
    pattern: /transition\s*:\s*none\s*!important/,
    msg: 'theme.css .av-card-preview.gsap-animating must contain transition: none !important (B-T1 GSAP pre-flight)',
  },

  // CG-FLU-09 ← test_77d_search_bar_float_theme_agnostic（@media≥1024px re-parse，用 ctx.raw）
  {
    id: 'CG-FLU-09',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const searchBarBlocks = [];
      for (const mb of extractDesktopMediaBodies(ctx.raw)) {
        for (const { selector, declarations } of parseRuleBlocks(mb)) {
          if (selector.includes('.search-bar')) searchBarBlocks.push({ selector, declarations });
        }
      }
      if (searchBarBlocks.length === 0) {
        ctx.fail('CG-FLU-09: no .search-bar rule inside @media (min-width:1024px) — CD-D1 (Rule 45) missing');
        return;
      }
      for (const { selector, declarations } of searchBarBlocks) {
        if (selector.includes('[data-theme="dim"]')) {
          ctx.fail(`CG-FLU-09: .search-bar @media 1024px float rule must be theme-agnostic — ${selector}`);
        }
        if (!/border-radius\s*:/.test(declarations)) ctx.fail('CG-FLU-09: .search-bar @media 1024px block missing border-radius');
        if (!/\bborder\s*:/.test(declarations)) ctx.fail('CG-FLU-09: .search-bar @media 1024px block missing border');
        if (!/\bmargin\s*:/.test(declarations)) ctx.fail('CG-FLU-09: .search-bar @media 1024px block missing margin');
      }
    },
  },

  // CG-FLU-10 ← test_77d_headers_float_theme_agnostic（11a all-widths padding + 11b @media float）
  {
    id: 'CG-FLU-10',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      // 11a: all-widths padding rule（用 ctx.text/blocks，鏡射 css_no_comments）
      let paddingFound = false;
      for (const { selector, declarations } of ctx.blocks) {
        if (
          selector.includes('.settings-header')
          && selector.includes('.avlist-header')
          && !selector.includes('@media')
        ) {
          if (/padding\s*:/.test(declarations)) {
            paddingFound = true;
            if (selector.includes('[data-theme="dim"]')) {
              ctx.fail(`CG-FLU-10: :is(.settings-header, .avlist-header) padding rule must be theme-agnostic — ${selector}`);
            }
            if (!/padding\s*:\s*1rem\s+1\.5rem/.test(declarations)) {
              ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) padding should be 1rem 1.5rem (flush-left fix)');
            }
          }
        }
      }
      if (!paddingFound) ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) all-widths padding rule not found (Rule 46)');

      // 11b: desktop-gated floating rule（用 ctx.raw @media≥1024px）
      const desktopHeaderBlocks = [];
      for (const mb of extractDesktopMediaBodies(ctx.raw)) {
        for (const { selector, declarations } of parseRuleBlocks(mb)) {
          if (selector.includes('.settings-header') && selector.includes('.avlist-header')) {
            desktopHeaderBlocks.push({ selector, declarations });
          }
        }
      }
      if (desktopHeaderBlocks.length === 0) {
        ctx.fail('CG-FLU-10: no :is(.settings-header, .avlist-header) rule inside @media (min-width:1024px) — Rule 47 missing');
        return;
      }
      for (const { selector, declarations } of desktopHeaderBlocks) {
        if (selector.includes('[data-theme="dim"]')) {
          ctx.fail(`CG-FLU-10: :is(.settings-header, .avlist-header) @media float rule must be theme-agnostic — ${selector}`);
        }
        if (!/border-radius\s*:/.test(declarations)) ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) @media 1024px block missing border-radius');
        if (!/\bborder\s*:/.test(declarations)) ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) @media 1024px block missing border');
      }
    },
  },

  // CG-FLU-11 ← test_77c_t3_vt_name_regression_anchor（字面錨用 ctx.raw + block 值用 ctx.text）
  {
    id: 'CG-FLU-11',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      if (!ctx.raw.includes('.page-search #main-content:has(.showcase-lightbox.show)')) {
        ctx.fail('CG-FLU-11: regression anchor .page-search #main-content:has(.showcase-lightbox.show) not found — 77c-T3 per-card blur bug returns');
      }
      let found = false;
      for (const { selector, declarations } of ctx.blocks) {
        if (
          selector.includes('.page-search')
          && selector.includes('#main-content')
          && selector.includes('.showcase-lightbox')
        ) {
          found = true;
          if (!/view-transition-name\s*:\s*none/.test(declarations)) {
            ctx.fail(`CG-FLU-11: regression anchor rule must set view-transition-name: none — ${selector}`);
          }
        }
      }
      if (!found) ctx.fail('CG-FLU-11: regression anchor rule block not found after parsing');
    },
  },

  // CG-FLU-12 ← test_light_shell_tokens_complete（token-set 完整性，精確 selector 比對）
  {
    id: 'CG-FLU-12',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      let dimDecls = null;
      let lightDecls = null;
      for (const { selector, declarations } of ctx.blocks) {
        const sel = selector.trim();
        if (sel === '[data-theme="dim"]') dimDecls = declarations;
        else if (sel === '[data-theme="light"]') lightDecls = declarations;
      }
      if (dimDecls === null) ctx.fail('CG-FLU-12: [data-theme="dim"] token block not found');
      if (lightDecls === null) {
        ctx.fail('CG-FLU-12: [data-theme="light"] token block not found — light chrome top-bars would IACVT');
      }
      if (dimDecls !== null) {
        const missing = SHELL_TOKENS.filter((t) => !new RegExp(`${escapeRegExp(t)}\\s*:`).test(dimDecls));
        if (missing.length) ctx.fail(`CG-FLU-12: [data-theme="dim"] token block missing shell token(s): ${missing.join(', ')}`);
      }
      if (lightDecls !== null) {
        const missing = SHELL_TOKENS.filter((t) => !new RegExp(`${escapeRegExp(t)}\\s*:`).test(lightDecls));
        if (missing.length) {
          ctx.fail(`CG-FLU-12: [data-theme="light"] token block missing shell token(s): ${missing.join(', ')} (IACVT risk — CD-D2(a))`);
        }
      }
    },
  },

  // CG-FLU-13 ← test_non_shell_roles_stay_dim_scoped（4 role marker 存在 + dim-scoped）
  {
    id: 'CG-FLU-13',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      for (const [role, marker] of Object.entries(NON_SHELL_ROLE_MARKERS)) {
        const matched = ctx.blocks.filter((b) => b.selector.includes(marker));
        if (matched.length === 0) {
          ctx.fail(`CG-FLU-13: ${role} marker ${marker} not found (selector renamed? update NON_SHELL_ROLE_MARKERS)`);
          continue;
        }
        for (const { selector } of matched) {
          const clean = selector.replace(/@media\s*\([^)]*\)\s*/g, '').trim();
          if (!clean.includes('[data-theme="dim"]')) {
            ctx.fail(`CG-FLU-13: ${role} rule ${selector} (marker ${marker}) is not dim-scoped — S-2 violation`);
          }
        }
      }
    },
  },

  // CG-FLU-14 ← test_notification_drawer_mobile_sheet（@media(max-width:480px) 手工 brace-walk）
  {
    id: 'CG-FLU-14',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const ext = extractMobileMediaBody(ctx.text);
      if (ext.err === 'no-media') {
        ctx.fail('CG-FLU-14: no @media (max-width:480px) block found (81c-T6 mobile sheet missing)');
        return;
      }
      if (ext.err === 'unbalanced') {
        ctx.fail('CG-FLU-14: unbalanced @media (max-width:480px) block');
        return;
      }
      const mediaBody = ext.body;
      if (!mediaBody.includes('.notification-drawer')) {
        ctx.fail('CG-FLU-14: @media (max-width:480px) must contain a .notification-drawer rule');
        return;
      }
      const dm = mediaBody.match(/\.notification-drawer\s*\{([^}]*)\}/);
      if (!dm) {
        ctx.fail('CG-FLU-14: .notification-drawer rule not parseable inside @media (max-width:480px)');
        return;
      }
      const decls = dm[1];
      for (const prop of ['position', 'left', 'right', 'top', 'width']) {
        if (!new RegExp(`\\b${prop}\\s*:[^;]*!important`).test(decls)) {
          ctx.fail(`CG-FLU-14: mobile .notification-drawer must set ${prop} with !important`);
        }
      }
      if (!/background\s*:\s*var\(--surface-2\)[^;]*!important/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must set background: var(--surface-2) !important (solid fill, G2)');
      }
      if (/#[0-9a-fA-F]{3,8}\b/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must not use a hex color literal (token-only)');
      }
      if (decls.includes('rgb(') || decls.includes('rgba(')) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must not use rgb()/rgba() (token-only)');
      }
      if (!/(?<!-webkit-)backdrop-filter\s*:\s*none\s*!important/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must set backdrop-filter: none !important (G2)');
      }
      if (!/-webkit-backdrop-filter\s*:\s*none\s*!important/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must set -webkit-backdrop-filter: none !important (macOS WKWebView pairing)');
      }
    },
  },

  // CG-FLU-15 ← test_rescrape_preview_mobile_stack（rescrape-modal.css @media(max-width:480px)）
  {
    id: 'CG-FLU-15',
    file: 'components/rescrape-modal.css',
    kind: 'fn',
    check(ctx) {
      const ext = extractMobileMediaBody(ctx.text);
      if (ext.err === 'no-media') {
        ctx.fail('CG-FLU-15: no @media (max-width:480px) block found (81c-T7 mobile stack missing)');
        return;
      }
      if (ext.err === 'unbalanced') {
        ctx.fail('CG-FLU-15: unbalanced @media (max-width:480px) block');
        return;
      }
      const mediaBody = ext.body;
      const pm = mediaBody.match(/\.rescrape-preview\s*\{([^}]*)\}/);
      if (!pm) {
        ctx.fail('CG-FLU-15: @media (max-width:480px) must contain a .rescrape-preview rule');
        return;
      }
      if (!/flex-direction\s*:\s*column/.test(pm[1])) {
        ctx.fail('CG-FLU-15: mobile .rescrape-preview must set flex-direction: column (AC-22 stack)');
      }
      const im = mediaBody.match(/\.rescrape-preview\s+\.pv-cover\s+img\s*\{([^}]*)\}/);
      if (!im) {
        ctx.fail('CG-FLU-15: @media (max-width:480px) must contain a .rescrape-preview .pv-cover img rule');
        return;
      }
      const coverDecls = im[1];
      const mw = coverDecls.match(/max-width\s*:\s*([^;]+)/);
      if (!mw) {
        ctx.fail('CG-FLU-15: mobile cover img must set max-width (widen off 38vw)');
        return;
      }
      if (mw[1].includes('38vw')) {
        ctx.fail('CG-FLU-15: mobile cover img max-width must be widened off 38vw (AC-22 cramp culprit)');
      }
      if (!mw[1].includes('100%')) {
        ctx.fail('CG-FLU-15: mobile cover img max-width should be 100% (structural value)');
      }
      if (/#[0-9a-fA-F]{3,8}\b/.test(coverDecls)) {
        ctx.fail('CG-FLU-15: mobile cover img rule must not use a hex color (token-only)');
      }
    },
  },

  // ══ T3 sub-commit 3a：poster-crop / 響應式家族（A 組 13 條，忠實 port，CD-96c-2）══

  // CG-PC-01 ← TestPosterCropCSSGuard（theme.css token + showcase.css selector-bound）
  {
    id: 'CG-PC-01',
    file: 'theme.css',
    kind: 'fn',
    check(ctx) {
      // theme.css：--poster-crop-ratio token + .poster-crop block
      if (!ctx.raw.includes('--poster-crop-ratio: 0.71')) {
        ctx.fail('CG-PC-01: theme.css missing --poster-crop-ratio: 0.71');
      }
      const pm = ctx.raw.match(/\.poster-crop\s*\{([^}]+)\}/);
      if (!pm) ctx.fail('CG-PC-01: theme.css .poster-crop selector not found');
      else {
        const b = pm[1];
        if (!b.includes('var(--poster-crop-ratio)')) ctx.fail('CG-PC-01: .poster-crop must contain var(--poster-crop-ratio)');
        if (!b.includes('right center')) ctx.fail('CG-PC-01: .poster-crop must contain object-position: right center');
        if (b.includes('71/100')) ctx.fail('CG-PC-01: .poster-crop must not hardcode 71/100 (use var)');
      }
      // showcase.css：.similar-slot-img / .similar-main-static
      const sc = ctx.load('pages/showcase.css').raw;
      const sm = sc.match(/\.similar-slot-img\s*\{([^}]+)\}/);
      if (!sm) ctx.fail('CG-PC-01: showcase.css .similar-slot-img not found');
      else {
        if (sm[1].includes('100% 20%')) ctx.fail('CG-PC-01: .similar-slot-img must not contain 100% 20%');
        if (!sm[1].includes('right center')) ctx.fail('CG-PC-01: .similar-slot-img must contain right center');
      }
      const mm = sc.match(/\.similar-main-static\s*\{([^}]+)\}/);
      if (!mm) ctx.fail('CG-PC-01: showcase.css .similar-main-static not found');
      else {
        if (!mm[1].includes('width: 178px')) ctx.fail('CG-PC-01: .similar-main-static must contain width: 178px');
        if (mm[1].includes('width: 200px')) ctx.fail('CG-PC-01: .similar-main-static must not contain width: 200px');
      }
    },
  },

  // CG-PC-02 ← TestPosterCropExtended（showcase ↔ search 雙檔 parity，_media_blocks 放鬆比對）
  {
    id: 'CG-PC-02',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      // stripped text（extractMediaBodies 用 loose `@media\b` regex，raw 上前置 comment 內的 @media
      // 會吞掉真實 media header；斷言全落在真宣告值，去註解不失真且更穩健）
      const showcase = ctx.text;
      const search = ctx.load('pages/search.css').text;
      const re4col = /grid-template-columns:\s*repeat\(\s*4\s*,\s*1fr\s*\)/;
      const re2col = /grid-template-columns:\s*repeat\(\s*2\s*,\s*1fr\s*\)/;
      const bodies481 = (css) => extractMediaBodies(css, /min-width:\s*481px/);
      // 481–899 四欄（showcase）
      const scJoin = bodies481(showcase).join('\n');
      if (!bodies481(showcase).length) ctx.fail('CG-PC-02: showcase.css no min-width:481px @media (481–899 grid)');
      else {
        if (!/\.showcase-grid\b/.test(scJoin)) ctx.fail('CG-PC-02: showcase.css 481–899 段未含 .showcase-grid');
        if (!re4col.test(scJoin)) ctx.fail('CG-PC-02: showcase.css 481–899 .showcase-grid 未改為 repeat(4, 1fr)');
        if (re2col.test(scJoin)) ctx.fail('CG-PC-02: showcase.css 481–899 段殘留 repeat(2, 1fr)');
      }
      // 481–899 四欄（search）
      const seJoin = bodies481(search).join('\n');
      if (!bodies481(search).length) ctx.fail('CG-PC-02: search.css no min-width:481px @media (481–899 grid)');
      else {
        if (!/\.search-grid\b/.test(seJoin)) ctx.fail('CG-PC-02: search.css 481–899 段未含 .search-grid');
        if (!re4col.test(seJoin)) ctx.fail('CG-PC-02: search.css 481–899 .search-grid 未改為 repeat(4, 1fr)');
        if (re2col.test(seJoin)) ctx.fail('CG-PC-02: search.css 481–899 段殘留 repeat(2, 1fr)');
      }
      // parity：兩檔皆有 481–899 → repeat(4,1fr)
      for (const [css, name] of [[showcase, 'showcase.css'], [search, 'search.css']]) {
        if (!re4col.test(bodies481(css).join('\n'))) ctx.fail(`CG-PC-02: ${name} 缺 481–899 → repeat(4, 1fr)（CD-11 parity）`);
      }
      // poster-crop 擴 ≤899（兩檔）
      for (const [css, name] of [[showcase, 'showcase.css'], [search, 'search.css']]) {
        const j899 = extractMediaBodies(css, /max-width:\s*899px/).join('\n');
        if (!j899) ctx.fail(`CG-PC-02: ${name} no @media (max-width: 899px)（poster-crop 未擴）`);
        if (!/aspect-ratio:\s*var\(--poster-crop-ratio/.test(j899)) ctx.fail(`CG-PC-02: ${name} @≤899 缺 aspect-ratio: var(--poster-crop-ratio)`);
        if (!/object-position:\s*right\s+center/.test(j899)) ctx.fail(`CG-PC-02: ${name} @≤899 缺 object-position: right center`);
      }
      // 非回歸 ≤480 仍 3-col（兩檔）
      const re3colBody = (grid) => new RegExp(`\\.${grid}\\b[^}]*repeat\\(\\s*3\\s*,\\s*1fr\\s*\\)`, 's');
      if (!extractMediaBodies(showcase, /max-width:\s*480px/).some((b) => re3colBody('showcase-grid').test(b))) {
        ctx.fail('CG-PC-02: showcase.css ≤480 .showcase-grid 不再是 repeat(3, 1fr)');
      }
      if (!extractMediaBodies(search, /max-width:\s*480px/).some((b) => re3colBody('search-grid').test(b))) {
        ctx.fail('CG-PC-02: search.css ≤480 .search-grid 不再是 repeat(3, 1fr)');
      }
      // 非回歸 900–1099 仍 3-col（兩檔）
      for (const [css, grid, name] of [[showcase, 'showcase-grid', 'showcase.css'], [search, 'search-grid', 'search.css']]) {
        const j = extractMediaBodies(css, /min-width:\s*900px\s*\)\s*and\s*\(\s*max-width:\s*1099px/).join('\n');
        if (!j) ctx.fail(`CG-PC-02: ${name} 找不到 900–1099 @media 段`);
        else if (!re3colBody(grid).test(j)) ctx.fail(`CG-PC-02: ${name} 900–1099 段 .${grid} 不再是 repeat(3, 1fr)`);
      }
    },
  },

  // CG-PC-03 ← TestUS5PosterCropScoped（rule-bound :is() scope silent-no-op 守衛）
  {
    id: 'CG-PC-03',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      // aspect-ratio / object-position 用 stripped text（防 selector 說明註解騙過）
      const target = extractMediaBodies(ctx.text, MW899).filter((b) => b.includes('.av-card-preview-img'));
      if (!target.length) ctx.fail('CG-PC-03: 找不到含 .av-card-preview-img 的 ≤899 block');
      else {
        const block = target[0];
        const sel = ruleBoundSelector(block, /aspect-ratio: var\(--poster-crop-ratio/);
        if (sel === null) ctx.fail('CG-PC-03: 找不到 aspect-ratio: var(--poster-crop-ratio) 規則');
        else {
          if (!sel.includes(IS_SCOPE)) ctx.fail('CG-PC-03: aspect-ratio 規則 selector 缺 :is() scope（silent no-op）');
          if (!sel.includes(':not(.hero-card)')) ctx.fail('CG-PC-03: aspect-ratio 規則 selector 缺 :not(.hero-card)');
        }
        const sel2 = ruleBoundSelector(block, /object-position: right center/);
        if (sel2 === null) ctx.fail('CG-PC-03: 找不到 object-position: right center 規則');
        else if (!(sel2.includes(IS_SCOPE) && sel2.includes(':not(.hero-card)'))) ctx.fail('CG-PC-03: object-position 規則 selector 缺 :is() scope + :not(.hero-card)');
      }
      // caption：用 stripped text（pytest 用 raw + 字面 regex；extractMediaBodies loose regex 在 raw 上
      // 會被前置 comment-@media 吞 header，改 text 去註解得同結果且穩健）
      const capTarget = extractMediaBodies(ctx.text, MW899).filter((b) => b.includes('.footer-default') && b.includes('.av-actress'));
      if (!capTarget.length) ctx.fail('CG-PC-03: 找不到含 caption 的 ≤899 block');
      else {
        const cb = capTarget[0];
        const am = cb.match(/\.footer-default \.av-actress \{([^}]*)\}/);
        if (!am) ctx.fail('CG-PC-03: 找不到 .footer-default .av-actress 規則');
        else if (!am[1].includes('display: none')) ctx.fail('CG-PC-03: .av-actress 應 display: none');
        const nm = cb.match(/\.footer-default \.av-num \{([^}]*)\}/);
        if (!nm) ctx.fail('CG-PC-03: 找不到 .footer-default .av-num 規則');
        else if (!nm[1].includes('text-overflow: ellipsis')) ctx.fail('CG-PC-03: .av-num 應 text-overflow: ellipsis');
      }
      // coarse 交集用 stripped text
      const coarse = extractMediaBodies(ctx.text, MW899_COARSE);
      if (!coarse.length) ctx.fail('CG-PC-03: 找不到 ≤899 ∩ coarse block');
      else {
        const cblock = coarse[0];
        const md = cblock.match(/([^{}]*\.footer-default)\s*\{([^}]*)\}/s);
        if (!md) ctx.fail('CG-PC-03: coarse block 內找不到 .footer-default 規則');
        else {
          if (!(md[1].includes(IS_SCOPE) && md[1].includes(':not(.hero-card)'))) ctx.fail('CG-PC-03: coarse .footer-default selector 缺 :is()+:not(.hero-card)');
          if (!md[2].includes('opacity: 1')) ctx.fail('CG-PC-03: coarse .footer-default 應 opacity: 1');
        }
        const mh = cblock.match(/\.footer-hover\s*\{([^}]*)\}/);
        if (!mh) ctx.fail('CG-PC-03: coarse block 內找不到 .footer-hover 規則');
        else if (!mh[1].includes('opacity: 0')) ctx.fail('CG-PC-03: coarse .footer-hover 應 opacity: 0');
      }
    },
  },

  // CG-PC-04 ← TestUS9SearchGridMobileFix（僅 6 CSS 子測；posterCrop 穿線子測留 pytest）
  {
    id: 'CG-PC-04',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      // (1) ≤480 .search-grid = repeat(3,1fr)（stripped，避 comment-@media 吞 header）
      const t480 = extractMediaBodies(ctx.text, MW480).filter((b) => /\.search-grid \{/.test(b));
      if (!t480.length) ctx.fail('CG-PC-04: 找不到含 .search-grid 的 ≤480 block');
      else {
        const m = t480[0].match(/\.search-grid \{([^}]*)\}/);
        if (!m) ctx.fail('CG-PC-04: ≤480 block 內找不到 .search-grid 規則');
        else {
          if (!m[1].includes('repeat(3, 1fr)')) ctx.fail('CG-PC-04: ≤480 .search-grid 應為 repeat(3, 1fr)');
          if (m[1].includes('grid-template-columns: 1fr;')) ctx.fail('CG-PC-04: ≤480 .search-grid 殘留單欄 1fr');
        }
      }
      // (2) ≤899 poster-crop scoped（stripped）
      const t899 = extractMediaBodies(ctx.text, MW899).filter((b) => b.includes('.av-card-preview-img') && b.includes('.search-grid'));
      if (!t899.length) ctx.fail('CG-PC-04: 找不到含 .av-card-preview-img + .search-grid 的 ≤899 block');
      else {
        const block = t899[0];
        const sel = ruleBoundSelector(block, /aspect-ratio: var\(--poster-crop-ratio/);
        if (sel === null) ctx.fail('CG-PC-04: 找不到 aspect-ratio: var(--poster-crop-ratio) 規則');
        else {
          if (!sel.includes(IS_SCOPE)) ctx.fail('CG-PC-04: aspect-ratio 規則 selector 缺 :is() scope');
          if (!sel.includes(':not(.hero-card)')) ctx.fail('CG-PC-04: aspect-ratio 規則 selector 缺 :not(.hero-card)');
        }
        const sel2 = ruleBoundSelector(block, /object-position: right center/);
        if (sel2 === null) ctx.fail('CG-PC-04: 找不到 object-position: right center 規則');
        else if (!(sel2.includes(IS_SCOPE) && sel2.includes(':not(.hero-card)'))) ctx.fail('CG-PC-04: object-position 規則 selector 缺 :is()+:not(.hero-card)');
        const m3 = block.match(/\.footer-default \.av-actress \{([^}]*)\}/);
        if (!m3) ctx.fail('CG-PC-04: 找不到 .footer-default .av-actress 規則');
        else if (!m3[1].includes('display: none')) ctx.fail('CG-PC-04: .av-actress 應 display: none');
        const m4 = block.match(/\.footer-default \.av-num \{([^}]*)\}/);
        if (!m4) ctx.fail('CG-PC-04: 找不到 .footer-default .av-num 規則');
        else if (!m4[1].includes('text-overflow: ellipsis')) ctx.fail('CG-PC-04: .av-num 應 text-overflow: ellipsis');
      }
      // (3) compound vs descendant（stripped whole css）
      if (!ctx.text.includes(`${IS_SCOPE}.search-grid`)) ctx.fail('CG-PC-04: .search-grid scope 須用複合 :is(…).search-grid');
      if (ctx.text.includes(`${IS_SCOPE} .search-grid`)) ctx.fail('CG-PC-04: 不得用後代 :is(…) .search-grid（silent no-op）');
      // (4) coarse footer 還原（stripped）
      const coarse = extractMediaBodies(ctx.text, MW899_COARSE);
      if (!coarse.length) ctx.fail('CG-PC-04: 找不到 ≤899 ∩ coarse block');
      else {
        const cblock = coarse[0];
        if (!cblock.includes('.search-grid')) ctx.fail('CG-PC-04: coarse block 應 scope 到 .search-grid');
        const md = cblock.match(/([^{}]*\.footer-default)\s*\{([^}]*)\}/s);
        if (!md) ctx.fail('CG-PC-04: coarse block 內找不到 .footer-default 規則');
        else {
          if (!(md[1].includes(IS_SCOPE) && md[1].includes(':not(.hero-card)'))) ctx.fail('CG-PC-04: coarse .footer-default selector 缺 :is()+:not(.hero-card)');
          if (!md[2].includes('opacity: 1')) ctx.fail('CG-PC-04: coarse .footer-default 應 opacity: 1');
        }
        const mh = cblock.match(/\.footer-hover\s*\{([^}]*)\}/);
        if (!mh) ctx.fail('CG-PC-04: coarse block 內找不到 .footer-hover 規則');
        else if (!mh[1].includes('opacity: 0')) ctx.fail('CG-PC-04: coarse .footer-hover 應 opacity: 0');
      }
      // (5) ≤899 lightbox cover-fit（stripped，避 comment-@media 吞 header）
      const tcov = extractMediaBodies(ctx.text, MW899).filter((b) => b.includes('.search-container .lightbox-cover'));
      if (!tcov.length) ctx.fail('CG-PC-04: 找不到含 .search-container .lightbox-cover 的 ≤899 block');
      else {
        const block = tcov[0];
        const mc = block.match(/\.search-container \.lightbox-cover\.has-cover \{([^}]*)\}/);
        if (!mc) ctx.fail('CG-PC-04: 容器規則須為 .search-container .lightbox-cover.has-cover');
        else {
          if (!mc[1].includes('min-height: 0')) ctx.fail('CG-PC-04: 容器須 min-height: 0');
          if (!mc[1].includes('min-width: 0')) ctx.fail('CG-PC-04: 容器須 min-width: 0');
        }
        const mi = block.match(/\.search-container \.lightbox-cover\.has-cover img \{([^}]*)\}/);
        if (!mi) ctx.fail('CG-PC-04: img 規則須為 .search-container .lightbox-cover.has-cover img');
        else {
          if (!mi[1].includes('height: auto')) ctx.fail('CG-PC-04: img 須 height: auto');
          if (!mi[1].includes('width: 100%')) ctx.fail('CG-PC-04: img 須 width: 100%');
        }
        if (/\.search-container \.lightbox-cover(?!\.has-cover) img \{/.test(block)) {
          ctx.fail('CG-PC-04: block 不得含裸 .search-container .lightbox-cover img（無 .has-cover gate）');
        }
      }
      // (6) showcase.css modal-hug 回歸護欄（stripped showcase）
      const scText = ctx.load('pages/showcase.css').text;
      const mh2 = scText.match(/\.lightbox-content\s+\.lightbox-cover\.has-cover\s+img\s*\{([^}]+)\}/);
      if (!mh2) ctx.fail('CG-PC-04: showcase.css modal-hug img 規則應保留');
      else if (!mh2[1].includes('width: 100%')) ctx.fail('CG-PC-04: showcase.css modal-hug img 缺 width: 100%');
    },
  },

  // CG-PC-05 ← TestUS11HeroCardMobileFix（showcase ↔ search 雙檔 hero）
  {
    id: 'CG-PC-05',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      const showcaseText = ctx.text;
      const searchText = ctx.load('pages/search.css').text;
      const heroMarker = '.av-card-preview.hero-card .av-card-preview-img';
      // showcase hero aspect-ratio + object-fit
      const scTgt = extractMediaBodies(showcaseText, MW899).filter((b) => b.includes(heroMarker));
      if (!scTgt.length) ctx.fail('CG-PC-05: showcase.css 找不到含 hero-card .av-card-preview-img 的 ≤899 block');
      else {
        const block = scTgt[0];
        const sel = ruleBoundSelector(block, /aspect-ratio: var\(--poster-crop-ratio/);
        if (sel === null) ctx.fail('CG-PC-05: showcase hero 找不到 aspect-ratio 規則');
        else {
          if (!sel.includes(IS_SCOPE)) ctx.fail('CG-PC-05: showcase hero aspect-ratio selector 缺 :is() scope');
          if (!sel.includes('.showcase-grid')) ctx.fail('CG-PC-05: showcase hero aspect-ratio selector 缺 .showcase-grid');
          if (!sel.includes('.hero-card')) ctx.fail('CG-PC-05: showcase hero aspect-ratio selector 缺 .hero-card');
        }
        const oel = ruleBoundSelector(block, /object-fit: cover/);
        if (oel === null) ctx.fail('CG-PC-05: showcase hero 找不到 object-fit: cover 規則');
        else if (!oel.includes('.hero-card')) ctx.fail('CG-PC-05: showcase object-fit: cover selector 缺 .hero-card');
      }
      // search hero aspect-ratio + compound-not-descendant + object-fit
      const seTgt = extractMediaBodies(searchText, MW899).filter((b) => b.includes(heroMarker));
      if (!seTgt.length) ctx.fail('CG-PC-05: search.css 找不到含 hero-card .av-card-preview-img 的 ≤899 block');
      else {
        const block = seTgt[0];
        const sel = ruleBoundSelector(block, /aspect-ratio: var\(--poster-crop-ratio/);
        if (sel === null) ctx.fail('CG-PC-05: search hero 找不到 aspect-ratio 規則');
        else {
          if (!sel.includes(IS_SCOPE)) ctx.fail('CG-PC-05: search hero aspect-ratio selector 缺 :is() scope');
          if (!sel.includes('.hero-card')) ctx.fail('CG-PC-05: search hero aspect-ratio selector 缺 .hero-card');
        }
        const oel = ruleBoundSelector(block, /object-fit: cover/);
        if (oel === null) ctx.fail('CG-PC-05: search hero 找不到 object-fit: cover 規則');
        else if (!oel.includes('.hero-card')) ctx.fail('CG-PC-05: search object-fit: cover selector 缺 .hero-card');
      }
      if (!searchText.includes(`${IS_SCOPE}.search-grid .av-card-preview.hero-card`)) {
        ctx.fail('CG-PC-05: search.css hero 規則須用複合 :is(…).search-grid .av-card-preview.hero-card');
      }
      if (searchText.includes(`${IS_SCOPE} .search-grid .av-card-preview.hero-card`)) {
        ctx.fail('CG-PC-05: search.css 不得有後代 :is(…) .search-grid .av-card-preview.hero-card（silent no-op）');
      }
    },
  },

  // CG-PC-06 ← TestUS1SearchCssLayout（require-presence，search.css）
  {
    id: 'CG-PC-06',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      const info = ruleBody(css, '\\.search-container \\.av-card-full-info');
      if (info === null) ctx.fail('CG-PC-06: 找不到 .search-container .av-card-full-info 規則');
      else if (!info.includes('flex: 0 0 390px')) ctx.fail('CG-PC-06: 右欄應 flex: 0 0 390px');
      const body = ruleBody(css, '\\.search-container \\.av-card-full-body');
      if (body === null) ctx.fail('CG-PC-06: 找不到 .search-container .av-card-full-body 規則');
      else if (!body.includes('flex: none')) ctx.fail('CG-PC-06: body 應 flex: none（top-pack）');
      const pair = ruleBody(css, '\\.search-container \\.av-card-full-body \\.info-grid-pair');
      if (pair === null) ctx.fail('CG-PC-06: 找不到 .info-grid-pair 桌面規則');
      else if (!pair.includes('grid-template-columns: 1fr 1fr')) ctx.fail('CG-PC-06: 桌面 .info-grid-pair 應 1fr 1fr');
      const b1024 = extractMediaBodies(ctx.text, MW1024);
      if (!b1024.length) ctx.fail('CG-PC-06: 找不到 @media (max-width: 1024px) block');
      else {
        const collapse = ruleBody(b1024[0], '\\.info-grid-pair');
        if (collapse === null) ctx.fail('CG-PC-06: ≤1024px 內找不到 .info-grid-pair collapse 規則');
        else if (!collapse.includes('grid-template-columns: 1fr;')) ctx.fail('CG-PC-06: ≤1024px .info-grid-pair 應 collapse 回 grid-template-columns: 1fr;');
      }
    },
  },

  // CG-PC-07 ← TestUS5ShowcaseGridIs3Col（≤480 showcase-grid = repeat(3,1fr)）
  {
    id: 'CG-PC-07',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      const target = extractMediaBodies(ctx.text, MW480).filter((b) => /\.showcase-grid \{/.test(b));
      if (!target.length) ctx.fail('CG-PC-07: 找不到含 .showcase-grid 的 ≤480 block');
      else {
        const m = target[0].match(/\.showcase-grid \{([^}]*)\}/);
        if (!m) ctx.fail('CG-PC-07: ≤480 block 內找不到 .showcase-grid 規則');
        else {
          if (!m[1].includes('repeat(3, 1fr)')) ctx.fail('CG-PC-07: ≤480 .showcase-grid 應為 repeat(3, 1fr)');
          if (m[1].includes('grid-template-columns: 1fr;')) ctx.fail('CG-PC-07: ≤480 .showcase-grid 殘留單欄 1fr');
        }
      }
    },
  },

  // CG-PC-08 ← TestSimilarCssSafetyAndGridGuard（960 安全網 + .similar-slot 寬度）
  {
    id: 'CG-PC-08',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      let found = false;
      for (const m of css.matchAll(/@media\s*\(\s*min-width\s*:\s*960px\s*\)/g)) {
        if (css.slice(m.index, m.index + 500).includes('similar-mobile-panel')) { found = true; break; }
      }
      if (!found) ctx.fail('CG-PC-08: @media (min-width: 960px) block 須含 .similar-mobile-panel（桌面 display:none 安全網）');
      const slot = css.match(/\.similar-slot\s*\{([^}]+)\}/);
      if (!slot) ctx.fail('CG-PC-08: 找不到 .similar-slot 規則');
      else {
        if (!slot[1].includes('width: 107px')) ctx.fail('CG-PC-08: .similar-slot 應 width: 107px');
        if (slot[1].includes('width: 120px')) ctx.fail('CG-PC-08: .similar-slot 不應 width: 120px');
      }
    },
  },

  // CG-PC-09 ← TestGridActionBtnSize（theme.css token + 主規則 + 兩斷點尺寸 + overlay wrap）
  {
    id: 'CG-PC-09',
    file: 'theme.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      if (!/--grid-action-btn-size:\s*48px/.test(css)) ctx.fail('CG-PC-09: :root 缺 --grid-action-btn-size: 48px');
      const main = css.match(/:is\(#ds-gallery-components,\s*\.ds-gallery-composition\)\s+\.btn-glass-circle\s*\{([\s\S]*?)\}/);
      if (!main) ctx.fail('CG-PC-09: 找不到 :is(…) .btn-glass-circle 主規則');
      else {
        const r = main[1];
        if (!/flex-shrink:\s*0/.test(r)) ctx.fail('CG-PC-09: .btn-glass-circle 缺 flex-shrink: 0');
        if (!/width:\s*var\(--grid-action-btn-size/.test(r)) ctx.fail('CG-PC-09: .btn-glass-circle width 未讀 var(--grid-action-btn-size)');
        if (!/height:\s*var\(--grid-action-btn-size/.test(r)) ctx.fail('CG-PC-09: .btn-glass-circle height 未讀 var(--grid-action-btn-size)');
      }
      const collectSizes = (bodies) => {
        const sizes = [];
        for (const b of bodies) for (const mm of b.matchAll(/--grid-action-btn-size:\s*(\d+)px/g)) sizes.push(parseInt(mm[1], 10));
        return sizes;
      };
      const mobileSizes = collectSizes(extractMediaBodies(ctx.text, MW480));
      if (!mobileSizes.length) ctx.fail('CG-PC-09: @media (max-width: 480px) 內未重宣告 --grid-action-btn-size');
      else if (!mobileSizes.every((s) => s <= 48)) ctx.fail(`CG-PC-09: ≤480 --grid-action-btn-size 未縮小（應 ≤48px）：${mobileSizes}`);
      const tabletSizes = collectSizes(extractMediaBodies(ctx.text, MIN481_MAX899));
      if (!tabletSizes.length) ctx.fail('CG-PC-09: @media (min-width: 481px) and (max-width: 899px) 內未重宣告 --grid-action-btn-size');
      else if (!tabletSizes.every((s) => s < 36)) ctx.fail(`CG-PC-09: 481–899 --grid-action-btn-size 未 < 36：${tabletSizes}`);
      const overlay = css.match(/:is\(#ds-gallery-components,\s*\.ds-gallery-composition\)\s+\.av-card-preview-overlay\s*\{([\s\S]*?)\}/);
      if (!overlay) ctx.fail('CG-PC-09: 找不到 :is(…) .av-card-preview-overlay 主規則');
      else {
        if (!/flex-wrap:\s*wrap/.test(overlay[1])) ctx.fail('CG-PC-09: .av-card-preview-overlay 缺 flex-wrap: wrap');
        if (!/align-content:\s*flex-end/.test(overlay[1])) ctx.fail('CG-PC-09: .av-card-preview-overlay 缺 align-content: flex-end');
      }
    },
  },

  // CG-PC-10 ← TestShowcaseCssTransitionTokens（正向存在，raw includes）
  {
    id: 'CG-PC-10',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      if (!ctx.raw.includes('transition: opacity var(--fluent-duration-fast) var(--fluent-ease-standard)')) {
        ctx.fail('CG-PC-10: showcase.css 缺 transition: opacity var(--fluent-duration-fast) var(--fluent-ease-standard)');
      }
      if (!ctx.raw.includes('transition: all var(--fluent-duration-fast) var(--fluent-ease-standard)')) {
        ctx.fail('CG-PC-10: showcase.css 缺 transition: all var(--fluent-duration-fast) var(--fluent-ease-standard)');
      }
    },
  },

  // CG-PC-11 ← TestUserTagCSSGuard（雙檔 --text-inverse 負向，search + showcase）
  {
    id: 'CG-PC-11',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      const searchBlock = ruleBody(ctx.raw, '\\.tag-badge\\.user-tag');
      if (searchBlock === null) ctx.fail('CG-PC-11: search.css 找不到 .tag-badge.user-tag 規則');
      else if (searchBlock.includes('--text-inverse')) ctx.fail('CG-PC-11: .tag-badge.user-tag 應用 --color-primary-content，非 --text-inverse');
      const scRaw = ctx.load('pages/showcase.css').raw;
      const scBlock = ruleBody(scRaw, '\\.lb-user-tag');
      if (scBlock === null) ctx.fail('CG-PC-11: showcase.css 找不到 .lb-user-tag 規則');
      else if (scBlock.includes('--text-inverse')) ctx.fail('CG-PC-11: .lb-user-tag 應用 --color-primary-content，非 --text-inverse');
    },
  },

  // CG-PC-12 ← TestSettingsHelpMobilePatch（settings.css ≤480 + base + help.css hero-terminal）
  {
    id: 'CG-PC-12',
    file: 'pages/settings.css',
    kind: 'fn',
    check(ctx) {
      const settings = ctx.raw;
      const ext = extractMobileMediaBody(settings);
      if (ext.err) ctx.fail('CG-PC-12: settings.css 找不到 @media (max-width: 480px) block');
      else {
        const seg = ruleBody(ext.body, '\\.settings-form-row--external-manager\\s+\\.settings-sources-segmented');
        if (seg === null) ctx.fail('CG-PC-12: ≤480 找不到 external-manager .settings-sources-segmented 規則');
        else if (!/flex-shrink:\s*0/.test(seg)) ctx.fail('CG-PC-12: ≤480 segmented 須含 flex-shrink: 0');
        const hint = ruleBody(ext.body, '\\.settings-form-row--external-manager\\s+\\.settings-hint');
        if (hint === null) ctx.fail('CG-PC-12: ≤480 找不到 external-manager .settings-hint 規則');
        else {
          if (!/flex-basis:\s*100%/.test(hint)) ctx.fail('CG-PC-12: ≤480 hint 須含 flex-basis: 100%');
          if (!/white-space:\s*normal/.test(hint)) ctx.fail('CG-PC-12: ≤480 hint 須含 white-space: normal');
        }
      }
      const code = ruleBody(settings, '\\.settings-mt-connect-status\\s+code');
      if (code === null) ctx.fail('CG-PC-12: 找不到 .settings-mt-connect-status code 規則');
      else {
        if (!/word-break:\s*break-all/.test(code)) ctx.fail('CG-PC-12: .settings-mt-connect-status code 須含 word-break: break-all');
        if (!/overflow-wrap:\s*anywhere/.test(code)) ctx.fail('CG-PC-12: .settings-mt-connect-status code 須含 overflow-wrap: anywhere');
      }
      const help = ctx.load('pages/help.css').raw;
      const term = ruleBody(help, '(?<![\\w-])\\.hero-terminal');
      if (term === null) ctx.fail('CG-PC-12: help.css 找不到 .hero-terminal 規則');
      else {
        if (!/overflow-x:\s*auto/.test(term)) ctx.fail('CG-PC-12: .hero-terminal 須含 overflow-x: auto');
        if (!/word-break:\s*break-all/.test(term)) ctx.fail('CG-PC-12: .hero-terminal 須含 word-break: break-all');
      }
    },
  },

  // CG-PC-13 ← TestSearchCssHardcoded（B1/B2 line-scan，context predicate 取代行號 allowlist）
  {
    id: 'CG-PC-13',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      const lines = ctx.raw.split('\n'); // 用 raw 保留 optical marker（寫在註解）
      const rgbaRe = /rgba\(\s*0\s*,\s*0\s*,\s*0\s*,/g;
      const sixRe = /[:\s]6px(?:\s|;|$)/;
      const intrinsicRe = /\b(?:min-|max-)?height\s*:|\bwidth\s*:/;
      // 移除行內 /* … */，避免註解裡的 var(/drop-shadow(/6px 造成誤判（review CG-PC-13 false-negative 修）
      const stripInlineComment = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '');
      // rgba(0,0,0…) 例外僅當它**真的落在** drop-shadow(…) 或 var(…) 呼叫內（開括號後、對應閉括號前）；
      // 只是同行「共現」var(/drop-shadow( 不算（例：box-shadow 硬編 rgba 後面接無關 var(--border)）。
      const insideAllowedCall = (code, idx) => {
        for (const opener of ['drop-shadow(', 'var(']) {
          const p = code.lastIndexOf(opener, idx);
          if (p === -1) continue;
          const span = code.slice(p + opener.length, idx);
          const opens = (span.match(/\(/g) || []).length;
          const closes = (span.match(/\)/g) || []).length;
          if (opens >= closes) return true; // 該呼叫尚未關閉 → rgba 在其中
        }
        return false;
      };
      const rgbaViol = [];
      const sixViol = [];
      for (let i = 0; i < lines.length; i += 1) {
        const line = lines[i];
        const stripped = line.replace(/^\s+/, '');
        if (stripped.startsWith('/*') || stripped.startsWith('*')) continue; // 跳過純註解行
        const code = stripInlineComment(line);
        rgbaRe.lastIndex = 0;
        let m;
        while ((m = rgbaRe.exec(code)) !== null) {
          if (!insideAllowedCall(code, m.index)) { rgbaViol.push([i + 1, line.trimEnd()]); break; }
        }
        if (sixRe.test(code)) {
          const prev = i > 0 ? lines[i - 1] : '';
          // 例外：intrinsic dimension（height/width）/ 該行或緊鄰上一行 comment 含 optical marker
          const ok = intrinsicRe.test(code) || line.includes('optical') || prev.includes('optical');
          if (!ok) sixViol.push([i + 1, line.trimEnd()]);
        }
      }
      if (rgbaViol.length) {
        ctx.fail(`CG-PC-13: search.css 新 rgba(0,0,0,…) 硬編碼違規 (${rgbaViol.length} 處)：`
          + rgbaViol.map(([n, l]) => `\n  L${n}: ${l.slice(0, 100)}`).join('')
          + `\n  → 改用 var(--overlay-*) token；drop-shadow/var() fallback 例外請用 drop-shadow( 或 var( 語法`);
      }
      if (sixViol.length) {
        ctx.fail(`CG-PC-13: search.css 新 6px layout 違規 (${sixViol.length} 處)：`
          + sixViol.map(([n, l]) => `\n  L${n}: ${l.slice(0, 100)}`).join('')
          + `\n  → 改 8pt grid / micro 4px；optical 例外請於該行或上一行加 /* … optical 6px … */ 註記`);
      }
    },
  },

  // ══ T3 sub-commit 3b：handoff CSS 半邊（B 組 CG-RO-01..03）+ §B 散檔（C 組 CG-SB-01..03）══
  // B 組 = handoff receiver own-half（net+tag；整-class delete defer→96d，CD-96-12）。
  // C 組 = §B standalone 檔（CG-SB-01/02 整檔 delete；CG-SB-03 切 CSS 半邊）。忠實 port（CD-96c-2）。

  // CG-RO-01 ← TestReadonlyDisabledStateGuard CSS 半邊（showcase.css；正向 + 負守衛）
  {
    id: 'CG-RO-01',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      // .is-readonly-disabled block：cursor: not-allowed + opacity（用 raw，鏡射 pytest _css()）
      const m = ctx.raw.match(/\.is-readonly-disabled\b[^{]*\{([^}]*)\}/s);
      if (!m) ctx.fail('CG-RO-01: showcase.css 缺 .is-readonly-disabled class');
      else {
        const body = m[1];
        if (!(body.includes('cursor:') && body.includes('not-allowed'))) ctx.fail('CG-RO-01: .is-readonly-disabled 應含 cursor: not-allowed');
        if (!body.includes('opacity')) ctx.fail('CG-RO-01: .is-readonly-disabled 應含 opacity（停用淺色）');
        // 負守衛：block 起點後 600 字元 region（含 :hover 群組）不得出現刪除線
        const region = ctx.raw.slice(m.index, m.index + 600);
        if (region.includes('line-through')) ctx.fail('CG-RO-01: .is-readonly-disabled 不應含 line-through（spec：無刪除線）');
        if (region.includes('text-decoration')) ctx.fail('CG-RO-01: .is-readonly-disabled 不應含 text-decoration（spec：無刪除線）');
      }
      // 齒輪 hover gating：須 :not(:disabled):hover，不得殘留未 gate 的裸 :hover
      if (!/\.lightbox-metadata\s+\.lb-rescrape-gear:not\(:disabled\):hover\b/.test(ctx.raw)) {
        ctx.fail('CG-RO-01: .lb-rescrape-gear:hover 應改為 :not(:disabled):hover（否則 disabled 齒輪仍變色）');
      }
      if (/\.lightbox-metadata\s+\.lb-rescrape-gear:hover\b/.test(ctx.raw)) {
        ctx.fail('CG-RO-01: 不應殘留未 gate 的 .lb-rescrape-gear:hover（specificity 會蓋過 .is-readonly-disabled）');
      }
    },
  },

  // CG-RO-02 ← TestDmmProxyRequiredGuard CSS 半邊（source-pill.css；opacity + hover no-lift）
  {
    id: 'CG-RO-02',
    file: 'components/source-pill.css',
    kind: 'fn',
    check(ctx) {
      const m = ctx.raw.match(/\.source-pill\[data-proxy-required="true"\]\s*\{([^}]+)\}/s);
      if (!m) ctx.fail('CG-RO-02: source-pill.css 缺 .source-pill[data-proxy-required="true"] rule block');
      else if (!m[1].includes('opacity')) ctx.fail('CG-RO-02: [data-proxy-required="true"] rule 缺 opacity 設定（灰化機制）');
      const hm = ctx.raw.match(/\.source-pill\[data-proxy-required="true"\]:hover\s*\{([^}]+)\}/s);
      if (!hm) ctx.fail('CG-RO-02: source-pill.css 缺 [data-proxy-required="true"]:hover rule（hover 不亮回）');
      else if (!hm[1].includes('transform')) ctx.fail('CG-RO-02: :hover rule 缺 transform: none（防 lift）');
    },
  },

  // CG-RO-03 ← TestPicker64aThreeStateGuard offline CSS 半邊（source-pill.css；specificity-aware 全域守衛）
  {
    id: 'CG-RO-03',
    file: 'components/source-pill.css',
    kind: 'fn',
    check(ctx) {
      // picker offline 去刪除線（雙 class 0,4,0 勝全域）
      const om = ctx.raw.match(/\.source-pill\.source-pill--action\[data-enabled="false"\]\s+\.pill-name\s*\{([^}]+)\}/s);
      if (!om) ctx.fail('CG-RO-03: source-pill.css 缺 .source-pill.source-pill--action[data-enabled="false"] .pill-name 規則');
      else if (!om[1].includes('text-decoration: none')) ctx.fail('CG-RO-03: picker offline .pill-name 應 text-decoration: none');
      // 全域不動守衛：忠實 port lookbehind (?<!--action)（區分全域 vs picker-scoped）
      const gm = ctx.raw.match(/(?<!--action)\.source-pill\[data-enabled="false"\]\s+\.pill-name\s*\{([^}]+)\}/s);
      if (!gm) ctx.fail('CG-RO-03: 全域 .source-pill[data-enabled="false"] .pill-name 規則不應被移除');
      else if (!gm[1].includes('line-through')) ctx.fail('CG-RO-03: 全域 line-through 不應被改動（CD-64-A3：只在 picker scope 加法覆寫）');
      // offline 膠囊 cursor: not-allowed
      const cm = ctx.raw.match(/\.source-pill--action\[aria-disabled="true"\]\s*\{([^}]+)\}/s);
      if (!cm) ctx.fail('CG-RO-03: source-pill.css 缺 .source-pill--action[aria-disabled="true"] cursor 規則');
      else if (!cm[1].includes('not-allowed')) ctx.fail('CG-RO-03: offline 膠囊 cursor 應 not-allowed');
    },
  },

  // CG-SB-01 ← test_css_spotlight_scoping.py（showcase.css + theme.css；4 檢查皆存在性/scope）
  {
    id: 'CG-SB-01',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      // .spotlight-search--mode-toggle variant + --spotlight-left-slot token 存在
      if (!/\.spotlight-search--mode-toggle\s*\{[^}]*--spotlight-left-slot/.test(ctx.raw)) {
        ctx.fail('CG-SB-01: showcase.css 缺 .spotlight-search--mode-toggle { --spotlight-left-slot: … }');
      }
      // 負守衛：裸 .spotlight-search input { padding-left: 5.5rem } 不得存在（會漏進 /search）
      if (/(?:^|\n)\s*\.spotlight-search\s+input\s*\{[^}]*padding-left\s*:\s*5\.5rem/.test(ctx.raw)) {
        ctx.fail('CG-SB-01: showcase.css 有裸 .spotlight-search input { padding-left: 5.5rem }（會漏進 /search，改用 variant class）');
      }
      // theme.css --spotlight-width token 存在
      if (!ctx.load('theme.css').raw.includes('--spotlight-width')) {
        ctx.fail('CG-SB-01: theme.css 缺 --spotlight-width（T8a）');
      }
      // showcase-toolbar 用 grid
      if (!(ctx.raw.includes('display: grid') && ctx.raw.includes('grid-template-columns'))) {
        ctx.fail('CG-SB-01: showcase-toolbar 須用 CSS grid（display: grid + grid-template-columns）');
      }
    },
  },

  // CG-SB-02 ← test_settings_mobile_toast.py（settings.css；@media(max-width:480px) media-scope）
  {
    id: 'CG-SB-02',
    file: 'pages/settings.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      if (!css.includes('max-width: 480px')) ctx.fail('CG-SB-02: settings.css 缺 max-width: 480px media query');
      if (!css.includes('.toast.toast-top')) ctx.fail('CG-SB-02: settings.css media query 缺 .toast.toast-top');
      if (!css.includes('bottom')) ctx.fail('CG-SB-02: settings.css 缺 bottom 屬性');
      // bottom 須在 @media (max-width: 480px) 區塊內（桌面不受影響）。settings.css 有多個 480 block，
      // toast bottom 落在其一 → 掃全部 480 body（extractMobileMediaBody 只回第一個，會漏掉 toast block）。
      const bodies480 = extractMediaBodies(css, MW480);
      if (!bodies480.length) ctx.fail('CG-SB-02: settings.css 找不到 @media (max-width: 480px) block');
      else if (!bodies480.some((b) => b.includes('bottom'))) ctx.fail('CG-SB-02: bottom 設定須落在 @media (max-width: 480px) 區塊內');
    },
  },

  // CG-SB-03 ← test_search_icon_mutex.py CSS 半邊（search.css；in-block line scan）
  {
    id: 'CG-SB-03',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      // 忠實 port pytest 逐行 in-block 掃描：.spotlight-search .btn-icon block 內含 flex-shrink
      const lines = ctx.raw.split('\n');
      let inBlock = false;
      let found = false;
      for (const line of lines) {
        if (line.includes('.spotlight-search .btn-icon')) inBlock = true;
        if (inBlock && line.includes('}')) inBlock = false;
        if (inBlock && line.includes('flex-shrink')) { found = true; break; }
      }
      if (!found) ctx.fail('CG-SB-03: .spotlight-search .btn-icon 區塊須含 flex-shrink: 0');
    },
  },

  // ══ T3 sub-commit 3c：跨-PR 混合 CSS 半邊（D 組 CG-XP-01..05；net+tag only，DO NOT delete，
  //    CD-96-12）。96c 只建自己承接的 CSS 半邊替代網 + 標 [lint-guard: migrate→<primary>]；
  //    整 class 最終刪除由 primary（96d/96e）在所有半邊網皆綠後執行。忠實 port（CD-96c-2）。══

  // CG-XP-01 ← TestRescrapeModalGuard CSS/asset 半邊（primary=96d；z-index-order 跨檔 + backdrop-token
  //           + selector-exists + no-hardcoded-token + base.html link）
  {
    id: 'CG-XP-01',
    file: 'components/rescrape-modal.css',
    kind: 'fn',
    check(ctx) {
      const modalCss = ctx.raw; // rescrape-modal.css
      const showcaseRaw = ctx.load('pages/showcase.css').raw;
      const themeRaw = ctx.load('theme.css').raw;
      const sourcePillRaw = ctx.load('components/source-pill.css').raw;

      // ── test_rescrape_modal_css_exists：rescrape-modal.css 專屬 class ──
      for (const sel of ['.rescrape-modal-box', '.rescrape-x', '.rescrape-num-input', '.rescrape-preview', '.rescrape-confirm-btn']) {
        if (!modalCss.includes(sel)) ctx.fail(`CG-XP-01: rescrape-modal.css 缺少 ${sel}`);
      }

      // ── test_rescrape_modal_css_no_hardcoded_tokens：hex 白名單 #fff / 無 px radius ──
      const badHex = (modalCss.match(/#[0-9a-fA-F]{3,8}\b/g) || []).filter((h) => !['#fff', '#ffffff'].includes(h.toLowerCase()));
      if (badHex.length) ctx.fail(`CG-XP-01: rescrape-modal.css 含硬編碼 hex 色 ${JSON.stringify(badHex)}（僅 #fff 白名單）`);
      const radiusPx = modalCss.match(/border-radius:\s*\d+px/g) || [];
      if (radiusPx.length) ctx.fail(`CG-XP-01: rescrape-modal.css border-radius 用 px 字面 ${JSON.stringify(radiusPx)}（應用 --fluent-radius-* token）`);

      // ── test_source_pill_css_has_action_loading_modifiers ──
      for (const sel of ['.source-pill--action', '.source-pill.is-loading', '.pill-spin', '.source-pill:disabled']) {
        if (!sourcePillRaw.includes(sel)) ctx.fail(`CG-XP-01: source-pill.css 缺少 ${sel} modifier`);
      }
      // ── test_source_pill_base_drag_rules_untouched ──
      if (!sourcePillRaw.includes('cursor: grab')) ctx.fail('CG-XP-01: source-pill.css base drag 規則（cursor: grab）遭破壞');

      // ── test_base_html_links_rescrape_modal_css（asset linkage 半邊）──
      let baseHtml;
      try {
        baseHtml = ctx.loadWeb('templates/base.html');
      } catch {
        ctx.fail('CG-XP-01: 讀取 web/templates/base.html 失敗');
        baseHtml = '';
      }
      if (!baseHtml.includes('/static/css/components/rescrape-modal.css')) {
        ctx.fail('CG-XP-01: base.html 未 <link> rescrape-modal.css');
      }

      // ── test_rescrape_dialog_zindex_above_lightbox_stack_below_toast（跨檔 z-index order）──
      const rescrapeZ = zindexOf(modalCss, '.rescrape-dialog.modal');
      const lightboxZ = zindexOf(showcaseRaw, '.showcase-lightbox');
      const similarZ = zindexOf(showcaseRaw, '.similar-stage');
      const toastZ = zindexOf(themeRaw, '.fluent-toast-container');
      if (rescrapeZ === null) ctx.fail('CG-XP-01: 無法在 rescrape-modal.css 找到 .rescrape-dialog.modal 的 z-index');
      if (lightboxZ === null) ctx.fail('CG-XP-01: 無法在 showcase.css 找到 .showcase-lightbox 的 z-index');
      if (similarZ === null) ctx.fail('CG-XP-01: 無法在 showcase.css 找到 .similar-stage 的 z-index');
      if (toastZ === null) ctx.fail('CG-XP-01: 無法在 theme.css 找到 .fluent-toast-container 的 z-index');
      if (rescrapeZ !== null && lightboxZ !== null && !(rescrapeZ > lightboxZ)) {
        ctx.fail(`CG-XP-01: rescrape z-index ${rescrapeZ} 未高於 .showcase-lightbox ${lightboxZ}（會渲染在 lightbox 下方）`);
      }
      if (rescrapeZ !== null && similarZ !== null && !(rescrapeZ > similarZ)) {
        ctx.fail(`CG-XP-01: rescrape z-index ${rescrapeZ} 未高於 .similar-stage ${similarZ}`);
      }
      if (rescrapeZ !== null && toastZ !== null && !(rescrapeZ < toastZ)) {
        ctx.fail(`CG-XP-01: rescrape z-index ${rescrapeZ} 未低於 .fluent-toast-container ${toastZ}（成功 toast 會被彈窗蓋住）`);
      }

      // ── test_fluent_modal_zindex_above_showcase_lightbox ──
      const fluentModalZ = zindexOf(themeRaw, '.fluent-modal');
      if (fluentModalZ === null) ctx.fail('CG-XP-01: 無法在 theme.css 找到 .fluent-modal 的 z-index');
      else if (lightboxZ !== null && !(fluentModalZ > lightboxZ)) {
        ctx.fail(`CG-XP-01: base .fluent-modal z-index ${fluentModalZ} 未高於 .showcase-lightbox ${lightboxZ}（確認 modal 會渲染在燈箱下方）`);
      }

      // ── test_fluent_modal_class_open_backdrop_uses_tokens（theme.css .fluent-modal.modal-open）──
      const bm = themeRaw.match(/\.fluent-modal\.modal-open\s*\{([^}]*)\}/s);
      if (!bm) ctx.fail('CG-XP-01: theme.css 缺少 .fluent-modal.modal-open class-open 玻璃 backdrop 規則');
      else {
        const rule = bm[1];
        if (!rule.includes('blur(var(--fluent-blur-light))')) ctx.fail('CG-XP-01: backdrop blur 未走 --fluent-blur-light token');
        if (/blur\(\s*\d+px/.test(rule)) ctx.fail('CG-XP-01: backdrop 含硬編碼 blur(Npx)，應用 --fluent-blur-light token');
        if (!rule.includes('var(--overlay-modal)')) ctx.fail('CG-XP-01: backdrop dim 未走 --overlay-modal token');
        if (!rule.includes('-webkit-backdrop-filter: blur(var(--fluent-blur-light))')) ctx.fail('CG-XP-01: backdrop 缺少 -webkit-backdrop-filter 配對（Safari/iOS）');
        if (!rule.includes('background: var(--overlay-modal)')) ctx.fail('CG-XP-01: dim 應 paint 在 dialog 本體（background: var(--overlay-modal)）');
      }
    },
  },

  // CG-XP-02 ← TestSourcePillSharedComponentGuard CSS 半邊（primary=96d；selector-exists + unscoped 負守衛
  //           + settings.css 不再定義 pill）
  {
    id: 'CG-XP-02',
    file: 'components/source-pill.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw; // source-pill.css
      // ── test_source_pill_css_exists_with_selectors：全部 7 selector ──
      for (const sel of [
        '.source-pill',
        '.source-pill--uncensored',
        '.source-pill--manual-only',
        '.source-pill-mt-badge',
        '.source-pill-badge',
        '.source-pill.is-partsbin',
        '.source-pill[data-enabled="false"] .pill-name',
      ]) {
        if (!css.includes(sel)) ctx.fail(`CG-XP-02: source-pill.css 缺少選擇器 ${sel}`);
      }
      // ── test_source_pill_css_is_unscoped：不得含 #settings-components（cross-page unscoped，負守衛）──
      if (css.includes('#settings-components')) ctx.fail('CG-XP-02: source-pill.css 不應含 #settings-components scope（cross-page unscoped）');
      // ── test_settings_css_no_longer_defines_pill：容器 settings-sources-pills 保留，排除後不得殘留 pill 本體 ──
      const settingsCss = ctx.load('pages/settings.css').raw;
      const stripped = settingsCss.replace(/settings-sources-pills\b/g, '');
      if (stripped.includes('settings-sources-pill')) {
        ctx.fail('CG-XP-02: settings.css 仍含 settings-sources-pill（pill 規則應已搬至 source-pill.css）');
      }
    },
  },

  // CG-XP-03 ← TestT4FooterStructure CSS 半邊（primary=96e；footer selectors + 640px media-value）。
  // ⚠ pytest 主 regex `@media\'s*…640px…` 有 `\'s` typo，僅靠 fallback 命中——此處 port fallback 語意
  //   （extractMediaBodies(css, /640px/)），不搬壞掉的主 regex（見 card §4 CG-XP-03）。
  {
    id: 'CG-XP-03',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw; // showcase.css
      for (const sel of ['.showcase-footer', '.footer-left', '.footer-center', '.footer-right', '.footer-pager']) {
        if (!css.includes(sel)) ctx.fail(`CG-XP-03: showcase.css 缺少 ${sel}`);
      }
      const bodies = extractMediaBodies(css, /640px/);
      if (!bodies.length) ctx.fail('CG-XP-03: showcase.css 缺少 @media (max-width: 640px)');
      else {
        const ok = bodies.some((b) => b.includes('.footer-left') && b.includes('.footer-center')
          && (b.includes('display: none') || b.includes('display:none')));
        if (!ok) {
          const hasSel = bodies.some((b) => b.includes('.footer-left') && b.includes('.footer-center'));
          if (!hasSel) ctx.fail('CG-XP-03: @media (max-width: 640px) 缺少 .footer-left 與 .footer-center');
          else ctx.fail('CG-XP-03: @media (max-width: 640px) 缺少 display: none');
        }
      }
    },
  },

  // CG-XP-04 ← TestPageTransitionDomGuard CSS 半邊（primary=96e；theme.css view-transition anchors，用 raw）
  {
    id: 'CG-XP-04',
    file: 'theme.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw; // theme.css
      // ── test_theme_css_view_transition_opt_in ──
      if (!css.includes('@view-transition')) ctx.fail('CG-XP-04: theme.css 缺少 @view-transition at-rule');
      if (!/@view-transition\s*\{\s*navigation:\s*auto/.test(css)) ctx.fail('CG-XP-04: theme.css @view-transition 缺少 navigation: auto');
      // ── test_theme_css_named_elements ──
      if (!css.includes('view-transition-name: sidebar')) ctx.fail('CG-XP-04: theme.css 缺少 view-transition-name: sidebar');
      if (!css.includes('view-transition-name: main-content')) ctx.fail('CG-XP-04: theme.css 缺少 view-transition-name: main-content');
      // ── test_theme_css_showcase_optout ──
      if (!/\.page-showcase\s+#main-content\s*\{\s*view-transition-name:\s*none/.test(css)) {
        ctx.fail('CG-XP-04: theme.css 缺少 .page-showcase #main-content { view-transition-name: none }');
      }
      // ── test_theme_css_theme_toggle_denames_named_groups ──
      if (!/html\.theme-transition-active\s+#sidebar\s*,\s*html\.theme-transition-active\s+#main-content\s*\{\s*view-transition-name:\s*none/.test(css)) {
        ctx.fail('CG-XP-04: theme.css 缺少 theme-transition-active 期間 de-name sidebar/main-content');
      }
    },
  },

  // CG-XP-05 ← TestPageTransitionSettingsScopeGuard CSS 半邊（primary=96e；settings.css root VT 規則
  //           作用域化：positive + EXHAUSTIVE negative——每個 ::view-transition-*(root) 出現點的緊鄰
  //           前綴須恰為 html.theme-transition-active，封「錯誤前綴」盲區，非只查裸規則）
  {
    id: 'CG-XP-05',
    file: 'pages/settings.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw; // settings.css
      const REQUIRED_PREFIX = 'html.theme-transition-active';
      // ── test_settings_root_rules_scoped（positive）──
      if (!css.includes(`${REQUIRED_PREFIX}::view-transition-old(root)`)) {
        ctx.fail('CG-XP-05: settings.css root 規則未作用域化（缺 html.theme-transition-active 前綴）');
      }
      // ── test_settings_all_root_rules_scoped（exhaustive negative；先 stripComments）──
      const cssNc = stripCssComments(css);
      const rootRe = /::view-transition-(?:old|new|group|image-pair)\(root\)/g;
      let m;
      while ((m = rootRe.exec(cssNc)) !== null) {
        const prefix = cssNc.slice(0, m.index);
        if (!prefix.endsWith(REQUIRED_PREFIX)) {
          const ctxStr = cssNc.slice(Math.max(0, m.index - 40), m.index + m[0].length);
          ctx.fail(`CG-XP-05: settings.css 有未以 html.theme-transition-active 作用域化的 root VT 規則: …${JSON.stringify(ctxStr)}`);
        }
      }
    },
  },

  // ══ T4：motion_lab.html <style>-block CSS-token 遷移（inline-style scan mode，CD-96c-3；
  //    忠實 port TestMotionLabHtmlHardcoded/TestMotionLabObjectPositionGuard，CD-96c-2）。
  //    NOTE：live pytest 掃 <style>…</style> block（非 style="…" attr）——docstring 明載「不掃
  //    HTML style 屬性」（demo 區合法 inline style 不納守衛）。故 port <style> scan，不 broaden。
  //    rule.html 指向 web-rel 檔 → runner 用 loadWebFile 讀 raw + extractStyleBlocks → ctx.styleCss。══

  // CG-ML-01 ← TestMotionLabHtmlHardcoded（blur/hex/radius/duration 4 子測，<style> block）
  {
    id: 'CG-ML-01',
    html: 'templates/motion_lab.html',
    kind: 'fn',
    check(ctx) {
      const css = ctx.styleCss;
      // (1) test_no_hardcoded_blur_px：全文 findall blur(Npx)（不 skip 註解，鏡射 re.findall on whole css）
      const blurMatches = css.match(/blur\(\d+px\)/g) || [];
      if (blurMatches.length) {
        ctx.fail(`CG-ML-01: motion_lab.html <style> 仍有 hardcoded blur(Npx)（改用 var(--fluent-blur-*)）：${JSON.stringify(blurMatches)}`);
      }
      // (2)(3)(4) 逐行掃 hex / border-radius px / transition（各自 comment-skip，鏡射三獨立 method）
      const lines = css.split('\n');
      const phase2Whitelist = new Set(['transition: background 0.15s;', 'transition: opacity 0.15s;']);
      const hexViol = [];
      const radiusViol = [];
      const transViol = [];
      for (let i = 0; i < lines.length; i += 1) {
        const line = lines[i];
        const stripped = line.trim();
        // 跳過純註釋行（行首 /* // *）
        if (stripped.startsWith('/*') || stripped.startsWith('//') || stripped.startsWith('*')) continue;
        // (2) 裸 hex（先移除所有 var(…) fallback；/g 鏡射 re.sub 全換）
        const lineNoVar = line.replace(/var\([^)]*\)/g, '');
        if (/#[0-9a-fA-F]{3,8}\b/.test(lineNoVar)) hexViol.push(`L${i + 1}: ${stripped}`);
        // (3) border-radius 裸 px（50% 及 var() 內 fallback 除外）
        if (line.includes('border-radius') && !/border-radius\s*:\s*50%/.test(line)) {
          const lnv = line.replace(/var\([^)]*\)/g, '');
          if (/border-radius\s*:[^;]*\d+px/.test(lnv)) radiusViol.push(`L${i + 1}: ${stripped}`);
        }
        // (4) transition 裸秒數 / 非 fluent 前綴 alias（phase2 whitelist 只 gate 此分支）
        if (!phase2Whitelist.has(stripped) && line.includes('transition:')) {
          if (/transition:[^;]*\b0?\.\d+s\b/.test(line) && !line.includes('var(--')) {
            transViol.push(`L${i + 1}: ${stripped}`);
          } else if (/var\(--(?:duration|ease)-/.test(line)) {
            transViol.push(`L${i + 1}: ${stripped}`);
          }
        }
      }
      if (hexViol.length) {
        ctx.fail(`CG-ML-01: motion_lab.html <style> 殘留裸 hex 硬編碼（改用 token；var() 內 fallback 除外）：\n  ${hexViol.join('\n  ')}`);
      }
      if (radiusViol.length) {
        ctx.fail(`CG-ML-01: motion_lab.html <style> border-radius 殘留裸 px（改用 var(--fluent-radius-*)；50%/var() fallback 除外）：\n  ${radiusViol.join('\n  ')}`);
      }
      if (transViol.length) {
        ctx.fail(`CG-ML-01: motion_lab.html <style> transition 殘留裸秒數或非 fluent 前綴 alias（改用 var(--fluent-duration-*)/var(--fluent-ease-*)；picker 兩處 0.15s 已 whitelist）：\n  ${transViol.join('\n  ')}`);
      }
    },
  },

  // CG-ML-02 ← TestMotionLabObjectPositionGuard（clip-lab object-position + slot width 2 子測）
  {
    id: 'CG-ML-02',
    html: 'templates/motion_lab.html',
    kind: 'fn',
    check(ctx) {
      const css = ctx.styleCss;
      // _style_blocks 另 assert 非空
      if (!css) {
        ctx.fail('CG-ML-02: motion_lab.html has no <style> blocks');
        return;
      }
      // test_clip_lab_img_object_position_right_center
      const m = css.match(/\.clip-lab-slot-img\s*,\s*\.clip-lab-main-img\s*\{([^}]+)\}/);
      if (!m) {
        ctx.fail('CG-ML-02: motion_lab.html <style>: .clip-lab-slot-img, .clip-lab-main-img rule not found');
      } else {
        const block = m[1];
        if (!block.includes('right center')) ctx.fail('CG-ML-02: .clip-lab-slot-img,.clip-lab-main-img block must contain object-position: right center');
        if (block.includes('100% 20%')) ctx.fail('CG-ML-02: .clip-lab-slot-img,.clip-lab-main-img block must not contain 100% 20%');
      }
      // test_clip_lab_slot_no_120（.clip-lab-slot 不誤命中 .clip-lab-slot-img：slot 後為 -，非 \s*{）
      const m2 = css.match(/\.clip-lab-slot\s*\{([^}]+)\}/);
      if (!m2) {
        ctx.fail('CG-ML-02: motion_lab.html <style>: .clip-lab-slot rule not found');
      } else if (m2[1].includes('width: 120px')) {
        ctx.fail('CG-ML-02: .clip-lab-slot block must not contain width: 120px (should be 107px)');
      }
    },
  },

  // ══ 98b-T3：focal inline-wins 前提守衛 ══
  // CG-FOCAL-01 ← TASK-98b-T3 no-`!important` 不變式：web/static/css/** 任何 CSS 檔的
  // object-position 宣告不得帶 !important。98b-T3 的 inline `:style="focalStyle(...)"` /
  // imperative `el.style.objectPosition` 靠自然 specificity 勝過 CSS baseline `right center`；
  // 若某 focal-aware 站的 CSS object-position 加了 !important，inline 會被壓過 → focal 失效。
  // 註：css-guard 既有 rule 皆單檔 selector-block 導向，表達不了「全目錄任一檔的宣告級 forbidden」，
  // 故用 fn escape-hatch + 遞迴 readdir 掃全 css 目錄（去註解後逐檔 regex：object-position + !important
  // 同一宣告），最貼近「object-position + !important on same declaration」語意（file: 'theme.css'
  // 僅為佔位滿足 runner loadFile，實際掃描在 check 內遞迴 CSS('')；ROOT 覆蓋 → scratch 副本自動生效）。
  {
    id: 'CG-FOCAL-01',
    file: 'theme.css',
    kind: 'fn',
    check(ctx) {
      const cssDir = CSS('');
      const files = [];
      const walk = (dir) => {
        for (const ent of readdirSync(dir, { withFileTypes: true })) {
          const full = join(dir, ent.name);
          if (ent.isDirectory()) walk(full);
          else if (ent.isFile() && ent.name.endsWith('.css')) files.push(full);
        }
      };
      walk(cssDir);
      const re = /object-position\s*:[^;}]*!important/;
      for (const f of files) {
        const m = stripCssComments(readFileSync(f, 'utf-8')).match(re);
        if (m) {
          ctx.fail(`CG-FOCAL-01: ${f} 含 object-position + !important（${JSON.stringify(m[0].trim())}）— 破壞 98b-T3 focal inline-wins 前提（inline :style/el.style 會被 !important 壓過）`);
        }
      }
    },
  },

  // CG-FOCAL-02 ← 99a-T3：拖曳中停用 .lb-mask-window transition，防與連續 pointermove 打架
  // （橡皮筋延遲手感，違反 spec §3.3「拖曳即時預覽」）。若被移除，視覺上不會立即崩潰（只是拖曳
  // 手感變差），純靠人眼不易發現，值得一條結構守衛鎖住。
  {
    id: 'CG-FOCAL-02',
    file: 'pages/showcase.css',
    kind: 'selector-require',
    markers: ['.lb-mask-window--dragging'],
    pattern: /transition\s*:\s*none/,
    msg: '.lb-mask-window--dragging must keep transition:none — 99a-T3 拖曳跟手；移除會讓 .lb-mask-window 的 333ms ease-out 與連續 pointermove 打架（橡皮筋延遲）',
  },

  // CG-FOCAL-03 ← 99a-T3：.lb-action-btn--success 刻意採 token-based color-mix(var(--color-success))
  // 而非像既有 --danger 那樣硬編 rgba（--danger 是 44c-T3 遺留、早於 6-role 材質系統，touched-
  // when-modified 才修，非本規則管轄）。鎖住「不要把新 modifier 也走回硬編老路」。
  {
    id: 'CG-FOCAL-03',
    file: 'pages/showcase.css',
    kind: 'selector-forbid',
    markers: ['.lb-action-btn--success'],
    pattern: /rgba\(/,
    msg: '.lb-action-btn--success must stay token-based (color-mix(in oklch, var(--color-success) ...)), not hardcoded rgba — unlike legacy .lb-action-btn--danger (pre-dates 6-role material system, out of scope here)',
  },

  // CG-FOCAL-04 ← TASK-99a-T5 Bug 2 修正：.cover-actions--focal-edit z-index 數值必須 >
  // .lb-mask-overlay，否則 ✓/✗ 46×46 hit box 的 elementFromPoint 落在 overlay 而非按鈕本身
  // （overlay 的 @click.self="cancelMask()" 攔截點擊，✓ 100% 靜默變 ✗，見 TASK-99a-T5 根因分析
  // 實測數據）。注意：z-index 數值關係正確 ≠ hit-test 正確（stacking context 邊界另有 rule，
  // 這只是必要非充分條件）——真正的證明只有 T6 e2e 的 elementFromPoint 斷言，本規則不宣稱
  // 涵蓋 hit-test 本身，只鎖住這個數值前提不會被未來改動悄悄破壞。
  {
    id: 'CG-FOCAL-04',
    file: 'pages/showcase.css',
    kind: 'fn',
    check(ctx) {
      const focalEditZ = zindexOf(ctx.raw, '.cover-actions.cover-actions--focal-edit');
      const overlayZ = zindexOf(ctx.raw, '.lb-mask-overlay');
      if (focalEditZ === null) {
        ctx.fail('CG-FOCAL-04: 無法在 showcase.css 找到 .cover-actions.cover-actions--focal-edit 的 z-index');
        return;
      }
      if (overlayZ === null) {
        ctx.fail('CG-FOCAL-04: 無法在 showcase.css 找到 .lb-mask-overlay 的 z-index');
        return;
      }
      if (!(focalEditZ > overlayZ)) {
        ctx.fail(`CG-FOCAL-04: .cover-actions--focal-edit z-index ${focalEditZ} 未高於 .lb-mask-overlay ${overlayZ}（✓/✗ hit-test 會被 overlay 攔截，見 TASK-99a-T5 根因分析）`);
      }
    },
  },
];

// ── per-file read+parse cache（同檔多 rule 共用，讀一次 → stripCssComments → parseRuleBlocks）──
const fileCache = new Map();
function loadFile(rel) {
  if (fileCache.has(rel)) return fileCache.get(rel);
  const raw = readFileSync(CSS(rel), 'utf-8');
  const text = stripCssComments(raw);
  const entry = { raw, text, blocks: parseRuleBlocks(text) };
  fileCache.set(rel, entry);
  return entry;
}

// web/ 相對檔（非 css 目錄）raw 讀取＋cache——供 asset-linkage 半邊（如 base.html <link> 存在性，
// CG-XP-01 承接 test_base_html_links_rescrape_modal_css）。ROOT 覆蓋 → scratch 副本自動生效。
const WEB = (rel) => join(ROOT, 'web', rel);
const webCache = new Map();
function loadWebFile(rel) {
  if (webCache.has(rel)) return webCache.get(rel);
  const raw = readFileSync(WEB(rel), 'utf-8');
  webCache.set(rel, raw);
  return raw;
}

// ── runner（read-fail try/catch → fail+continue；全 rule 跑完才 exit(1)，i18n_lint 累積器範式）──
for (const rule of RULES) {
  let ctx;
  if (rule.html) {
    // T4 inline-style scan mode：rule.html 指 web-rel（非 CSS）檔，用 loadWebFile 讀 raw +
    // extractStyleBlocks 抽 <style> block → ctx.styleCss。ROOT 覆蓋 → scratch 副本自動生效。
    let raw;
    try {
      raw = loadWebFile(rule.html);
    } catch {
      fail(`${rule.id}: 讀檔失敗 ${rule.html}`);
      continue;
    }
    ctx = { html: raw, styleCss: extractStyleBlocks(raw), fail, rel: rule.html, load: loadFile, loadWeb: loadWebFile };
  } else {
    let entry;
    try {
      entry = loadFile(rule.file);
    } catch {
      fail(`${rule.id}: 讀檔失敗 ${rule.file}`);
      continue;
    }
    ctx = { text: entry.text, raw: entry.raw, blocks: entry.blocks, fail, rel: rule.file, load: loadFile, loadWeb: loadWebFile };
  }
  KINDS[rule.kind](rule, ctx);
}

if (hadError) process.exit(1);
console.log(`✓ css-guard: ${RULES.length} 條 CSS-block guard 全過`);
