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
// ⚠️ 只收 depth-0（頂層）block：`@media (...) { .a{} .b{} }` 整塊被當**單一外層** block，
// selector=`@media (...)`、declarations=整段內文——內層 .a/.b **不會**被拆成獨立 block。
// 要看 @media 內的規則，需另對其 body 重新 parse（見 flattenRuleBlocks / extractMediaBodies）；
// 只掃頂層 block 的檢查對巢狀在 @media 內的規則會 fail-open（CG-GRID-ALIGN 108-T6 曾踩）。
// 忠實鏡射 Python 逐字元迴圈，非 regex 猜大括號配對。
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

// 遞迴展平 at-rule（@media/@supports/…）block，取得所有「真實」style rule（selector+declarations）。
// parseRuleBlocks 只在 brace depth 歸 0 時收 block，故 `@media (...) { .a{} .b{} }` 只會回一個
// selector=`@media (...)`、declarations=整段內文的 block —— 內層 `.a` / `.b` 規則不會被拆開，
// 任何只掃 ctx.blocks 頂層的 rule 會漏看巢狀在 @media 裡的規則（CG-GRID-ALIGN 108-T6 fail-open 之因）。
// 此函式對 selector 以 `@` 開頭的 block，於其 declarations 上重新 parseRuleBlocks 取內層規則並遞迴
// （支援巢狀 @media），非 at-rule 則視為真實 style rule 直接收下。CG-GRID-ALIGN 起使用；其餘既有
// rule 已各自用 extractDesktopMediaBodies/extractMediaBodies/extractMobileMediaBody 手工處理 @media，
// 不受影響、不重構（避免波及已驗證行為）。
function flattenRuleBlocks(blocks) {
  const out = [];
  for (const { selector, declarations } of blocks) {
    if (selector.trim().startsWith('@')) {
      out.push(...flattenRuleBlocks(parseRuleBlocks(declarations)));
    } else {
      out.push({ selector, declarations });
    }
  }
  return out;
}

// flattenRuleBlocks 的帶-上下文版（108-T5fix2）：額外累積祖先 at-rule 條件鏈，讓白名單型負向規則
// 能問「這條規則在哪個 @media 底下」。條件 = at-rule prelude 去掉開頭關鍵字後 trim
//（`@media (min-width: 900px) and (max-width: 1099px)` → `(min-width: 900px) and (max-width: 1099px)`）。
// top-level 規則 media=[]；巢狀 @media 之規則 media.length>1 → 白名單一律不認（fail-closed）。
function flattenWithMedia(blocks, media = []) {
  const out = [];
  for (const { selector, declarations } of blocks) {
    const sel = selector.trim();
    if (sel.startsWith('@')) {
      const cond = sel.replace(/^@[\w-]+/, '').trim();
      out.push(...flattenWithMedia(parseRuleBlocks(declarations), [...media, cond]));
    } else {
      out.push({ media, selector, declarations });
    }
  }
  return out;
}

// @media (min-width:1024px) body 抽取（CG-FLU-09/10 11b；用 ctx.raw，鏡射 pytest css_raw）。
// parseRuleBlocks 對 @media wrapper 只回一個 depth-0 block，故需先抽 body 再 re-parse。
//
// 🔴 129-T4：原本這裡是非貪婪 regex `\{([\s\S]*?)\}(?=\s*(?:\/\*|@|...))`，
//   **在 @media body 內只有一條規則時才正確**。一旦 body 內有第二條規則，第一條的 `}`
//   後面接著註解或選擇器，lookahead 就命中 → body 被切在第一條規則中間 → 括號不平衡 →
//   parseRuleBlocks 抽不到完整規則 → 守衛謊報「Rule 45 missing」。
//   （T4 要在 Rule 45 的 media 區塊內加第二條規則時實際撞到，grok 回報、未自行改守衛。）
//   改為委派給同檔既有的 balanced-brace `extractMediaBodies()`——**選中的 @media 集合完全相同**
//   （condRegex 錨定 ^...$，等價於舊 regex 的字面 header 比對），只是 body 這次是完整的。
//   ⇒ 不是放寬守衛，是修好它的解析器；等價性驗證見 commit 訊息。
function extractDesktopMediaBodies(raw) {
  return extractMediaBodies(raw, /^\s*\(\s*min-width\s*:\s*1024px\s*\)\s*$/);
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
const MW1024 = /^\s*\(\s*max-width\s*:\s*1023\.98px\s*\)\s*$/;
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

// checkLayerInsetHorizontalPadding — 146b-T7：抽出 CG-LAYER-01/02 的共用檢查邏輯，
// 只給新規則用（CG-LAYER-01/02 本身不retrofit，理由見 TASK-146b-T7.md 現況分析第 6 節）。
// 樣板＝ CG-LAYER-01/02 原始邏輯逐字保留，只把 id/selector 抽成參數。
// 0/1/≥2 三岔樣板＝ CG-FLU-16（FE-GUARD-14）。
function checkLayerInsetHorizontalPadding(ctx, { id, selector }) {
  const norm = (s) => s.replace(/\s+/g, ' ').trim();
  const hits = ctx.blocks.filter((b) => norm(b.selector) === selector);
  if (hits.length === 0) {
    ctx.fail(`${id}: 找不到頂層 \`${selector}\` block（水平內距契約消失）`);
    return;
  }
  if (hits.length > 1) {
    ctx.fail(
      `${id}: 找到 ${hits.length} 個頂層 \`${selector}\` block，cascade 無法機械驗證——`
      + `命中：${hits.map((b) => JSON.stringify(b.declarations.trim().slice(0, 60))).join(' | ')}`,
    );
    return;
  }
  const { declarations } = hits[0];
  const padDecls = [...declarations.matchAll(/(?<![-\w])(padding(?:-inline)?)\s*:\s*([^;]+)/gi)];
  if (padDecls.length === 0) {
    ctx.fail(`${id}: \`${selector}\` 缺少 padding / padding-inline 宣告`);
    return;
  }
  for (const m of padDecls) {
    const prop = m[1];
    const val = m[2].trim();
    if (prop.toLowerCase() === 'padding-inline') {
      if ((/^(?:1\.5rem|24px)\b/.test(val) || /\b(?:1\.5rem|24px)\b/.test(val))
          && !/var\(\s*--layer-inset\s*\)/.test(val)) {
        ctx.fail(`${id}: \`${selector}\` 的 ${prop} 殘留字面水平內距 \`${val}\`——必須吃 var(--layer-inset)`);
      }
    } else {
      const parts = val.trim().split(/\s+/);
      const horizontal = parts.length === 1 ? parts[0] : parts[1];
      if (/^(?:1\.5rem|24px)$/.test(horizontal)) {
        ctx.fail(
          `${id}: \`${selector}\` 的 ${prop} 水平分量是字面 \`${horizontal}\`——`
          + '必須改吃 var(--layer-inset)（不能靠與 token 數值巧合相等）',
        );
      }
    }
  }
  if (!/var\(\s*--layer-inset\s*\)/.test(declarations)) {
    ctx.fail(`${id}: \`${selector}\` 的 declarations 未出現 var(--layer-inset)`);
  }
}

// checkContainerMinHeightUsesMobileTopbar — 146b-T8：CG-LAYER-04/05 共用檢查。
// 為什麼抽 helper 而不是直接寫兩條：兩規則只差 id／selector／file，檢查的是同一個
// min-height 契約（必須吃 var(--mobile-topbar-height)、不得殘留任何字面 px/rem）。
// checkLayerInsetHorizontalPadding 管的是 padding，套不上；再抽一層把 min-height
// 的 0/1/≥2 三岔＋字面偵測寫一次，比近逐字複製兩份清楚，也避免日後第三頁複製時
// 又多出一份 drift。樣板＝ CG-FLU-16 的 0/1/≥2（FE-GUARD-14：單檔單 selector，
// 不用 .find()/[0]/last/join() 聚合挑「其中一個」）。
function checkContainerMinHeightUsesMobileTopbar(ctx, { id, selector }) {
  const hits = ctx.blocks.filter((b) => b.selector.trim() === selector);
  if (hits.length === 0) {
    ctx.fail(`${id}: 找不到頂層 \`${selector}\` block（min-height 契約消失）`);
    return;
  }
  if (hits.length > 1) {
    ctx.fail(
      `${id}: 找到 ${hits.length} 個頂層 \`${selector}\` block，cascade 無法機械驗證——`
      + `命中：${hits.map((b) => JSON.stringify(b.declarations.trim().slice(0, 60))).join(' | ')}`,
    );
    return;
  }
  const { declarations } = hits[0];
  const mhDecls = [...declarations.matchAll(/(?<![-\w])min-height\s*:\s*([^;]+)/gi)];
  if (mhDecls.length === 0) {
    ctx.fail(`${id}: \`${selector}\` 缺少 min-height 宣告`);
    return;
  }
  if (mhDecls.length > 1) {
    ctx.fail(
      `${id}: \`${selector}\` 的 min-height 宣告出現 ${mhDecls.length} 次 — cascade 歧義`,
    );
    return;
  }
  const val = mhDecls[0][1].trim();
  if (!/var\(\s*--mobile-topbar-height\s*\)/.test(val)) {
    ctx.fail(
      `${id}: \`${selector}\` 的 min-height 未吃 var(--mobile-topbar-height)，實際為 \`${val}\`——`
      + '必須與 .main-content 手機 padding-top 共用同一個 token（146b-T8 / T2 配對）',
    );
  }
  // 擋任何字面 px/rem（不限 56px）——防「手改成另一個巧合數字」；與 CG-LAYER-01
  // 對 1.5rem/24px 巧合值的態度一致。
  if (/\d+(?:\.\d+)?(?:px|rem)\b/.test(val)) {
    ctx.fail(
      `${id}: \`${selector}\` 的 min-height 殘留字面單位 \`${val}\`——`
      + '必須改吃 var(--mobile-topbar-height)（不能靠與 token 數值巧合相等）',
    );
  }
}

// ── 表驅動 rule-set（fluent 家族 14 條，忠實 port test_fluent_materials_guards.py，CD-96c-2）──
// 虛擬路徑：CD-148a-6/7 的反向鎖／跨 part 規則需要「8 個 part 串接後的全文」，不是單一實體檔。
// 讓 loadFile 認得這個字面（刻意不是合法相對路徑，不會撞到真檔案），runner／ctx 組裝完全不用改，
// 10 條 callsite 各自只需把 `'pages/showcase.css'` 換成 SHOWCASE_FULL 這個常數。
const SHOWCASE_FULL = 'virtual:showcase-full';

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
      // 129-T4：兩個不變式的作用域**不同**，不能混在同一個迴圈裡（原本混在一起，
      // 於是 media 區塊內只要多一條後代規則就會被要求也帶 margin/radius/border）。
      //   ① theme-agnostic：**所有**含 .search-bar 的規則都不得被 dim scope 綁死 → 維持廣掃
      //   ② 浮動幾何三宣告：只有 **Rule 45 本體**（選擇器恰好是 .search-bar）該帶 → 精確匹配
      // 兩者都**沒有放寬**：刪掉 Rule 45、拿掉其中任一宣告、或把它 dim-scope 化，
      // 三種破壞都仍然轉紅（commit 前已逐一 mutation 驗過）。
      for (const { selector } of searchBarBlocks) {
        if (selector.includes('[data-theme="dim"]')) {
          ctx.fail(`CG-FLU-09: .search-bar @media 1024px float rule must be theme-agnostic — ${selector}`);
        }
      }
      const floatRules = searchBarBlocks.filter((b) => b.selector.trim() === '.search-bar');
      if (floatRules.length === 0) {
        ctx.fail('CG-FLU-09: no bare `.search-bar` float rule inside @media (min-width:1024px) — CD-D1 (Rule 45) missing');
        return;
      }
      // 🔴 三輪 review 之後的收斂（sonnet T4 BLOCKER ＋ PR#156 Codex 第 2／3 輪 P2）：
      //   前三個版本全部在數「**規則條數**」——取第一條 → 裸規則不准超過一條 →
      //   帶幾何宣告的規則不准超過一條。但 CSS cascade 是逐「**屬性**」結算的，
      //   單位不一致 ⇒ 每一版不是漏放就是過寬：
      //     · `.find()` 取第一條   → 第二條 `margin: 0` 中和掉浮動，守衛靜默（fail-open）
      //     · 裸規則不准超過一條   → 另開一條只設 `color` 的裸規則被連坐擋下
      //     · 帶幾何的不准超過一條 → 合法地把三宣告拆成兩條寫也被擋，訊息還謊報「缺屬性」
      //   ⇒ 改成**逐屬性數宣告次數**，三個問題一次消掉：
      //     0 次  = Rule 45 形同消失
      //     >1 次 = 後面那次在 cascade 上蓋掉前面那次（正是 fail-open 要擋的）
      //     拆條寫 → 每個屬性仍各 1 次 → 綠；只設 color/gap 的裸規則 → 不碰這三個屬性 → 綠
      //   驗證改用**雙向矩陣**（8 破壞必紅 ＋ 14 合法改寫必綠），不再只驗破壞那一半
      //   ——過寬的守衛在只有破壞案例的矩陣裡，定義上一定 100% 通過（見 FE-GUARD-17）。
      const allDecls = floatRules
        .map((b) => b.declarations)
        .join(';')
        .replace(/\/\*[\s\S]*?\*\//g, '');  // 剝區塊內註解，避免註解裡的 `margin:` 被算進來
      for (const [name, re] of [
        ['border-radius', /border-radius\s*:/g],
        ['border', /(?<![-\w])border\s*:/g],      // 不吃 border-radius / border-color …
        // 146b-T6：margin 那格從「只認 `margin` 簡寫」擴成「任何設定水平 margin 的宣告」
        // （`margin` / `margin-inline` / `margin-left` / `margin-right`；仍不吃 `margin-top` /
        // `margin-bottom`——垂直不屬 Rule 45 浮動幾何不變式）。原因：Rule 45 的內縮改吃
        // `var(--layer-inset)` 走 `margin-inline`，與 Rule 13b `.showcase-toolbar` 同一寫法；
        // 不變式沒變（浮動幾何存在），變的只是表達方式 ⇒ **對帳，不是放寬**。
        // 等價性已用雙向矩陣驗過（11 格：6 破壞必紅 ＋ 5 合法改寫必綠），關鍵一格是
        // 「改回舊寫法 `margin: 0 1rem` 仍然綠」＝新版沒擋得比舊版少。
        // 已知的過嚴邊界：`margin-left` + `margin-right` 分開寫會被算 2 次而轉紅——兩者設的
        // 是不同的邊、不是 cascade 覆蓋，但錯誤訊息仍會說「後面那次會在 cascade 上蓋掉
        // Rule 45」（在這個情況下是假的）。**刻意維持 fail-closed**：撞到的人改用
        // `margin-inline` 即可；把計數器改成「左右各一次算同一個邏輯單位」換來的使用者
        // 價值是零，而本 repo 兩條平行浮動規則本來就統一走 `margin-inline`。
        ['水平 margin（margin / margin-inline / margin-left|right）',
          /(?<![-\w])margin(?:-inline|-left|-right)?\s*:/g],
      ]) {
        const n = (allDecls.match(re) || []).length;
        if (n === 0) {
          ctx.fail(`CG-FLU-09: 裸 \`.search-bar\` 沒有宣告 ${name} — CD-D1 (Rule 45) 形同消失`);
        } else if (n > 1) {
          ctx.fail(`CG-FLU-09: 裸 \`.search-bar\` 宣告了 ${n} 次 ${name} — 後面那次會在 cascade 上蓋掉 Rule 45`);
        }
      }
    },
  },

  // CG-FLU-10 ← 146b-T3b：Rule 46/47 回復（CD-146b-15/16），11a/11b 改 exact-selector 0/1/≥2
  // 146b-T7：11a 對帳從字面 `1rem 1.5rem` 改成 `1rem var(--layer-inset)`（不變式沒變，
  // 表達方式變了——水平內距仍是 24px，只是改由 token 表達）。這是刻意收緊，不是放寬：
  // 舊字面 `1rem 1.5rem` 在本條與 CG-LAYER-03 會同時轉紅（兩條訊息都會出現），那是刻意的
  // 雙重保險，不是重複告警的 bug——「字面值巧合等於 token」正是這支 branch 要擋的事。
  // 維護耦合：本條現在寫死了 `--layer-inset` 這個 token 名字；日後若重新命名，CG-FLU-10
  // 與 CG-LAYER-03 兩處都要跟著改，否則會變成「改名後守衛靜默通過」。
  {
    id: 'CG-FLU-10',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const SEL = ':is(.settings-header, .avlist-header)';
      // 11a: all-widths padding fix（Rule 46，146b-T3b 從 `.settings-header` 復原回
      // `:is(.settings-header, .avlist-header)`）。原本用 `.includes('.settings-header')`
      // 只認子字串——`.avlist-header` 忘了放回去也會照樣通過（子字串仍含 .settings-header），
      // 這條不變式其實沒真的被守到。改成整段選擇器逐字比對 + 0/1/≥2 三岔拒絕歧義。
      const paddingBlocks = ctx.blocks.filter(
        (b) => b.selector.trim() === SEL && /padding\s*:/.test(b.declarations),
      );
      if (paddingBlocks.length === 0) {
        ctx.fail(`CG-FLU-10: ${SEL} all-widths padding rule not found (Rule 46)`);
      } else if (paddingBlocks.length > 1) {
        ctx.fail(`CG-FLU-10: 找到 ${paddingBlocks.length} 個 ${SEL} padding block，cascade 無法機械驗證`);
      } else {
        const { selector, declarations } = paddingBlocks[0];
        if (selector.includes('[data-theme="dim"]')) {
          ctx.fail(`CG-FLU-10: padding rule must be theme-agnostic — ${selector}`);
        }
        if (!/padding\s*:\s*1rem\s+var\(\s*--layer-inset\s*\)/.test(declarations)) {
          ctx.fail('CG-FLU-10: padding should be 1rem var(--layer-inset) (flush-left fix)');
        }
      }

      // 11b: desktop B-floating geometry（Rule 47，146b-T3b 從整條刪除復原）。巢狀在
      // @media (min-width: 1024px) 內，ctx.blocks 只在頂層收 block（FE-GUARD-14 同型坑：
      // @media wrapper 被當成一個不透明 block），改用 flattenRuleBlocks 展平後再比對。
      const floatBlocks = flattenRuleBlocks(ctx.blocks).filter(
        (b) => b.selector.trim() === SEL
          && (/border-radius\s*:/.test(b.declarations) || /(?<![-\w])border\s*:/.test(b.declarations)),
      );
      if (floatBlocks.length === 0) {
        ctx.fail(`CG-FLU-10: ${SEL} desktop B-floating rule not found (Rule 47)`);
      } else if (floatBlocks.length > 1) {
        ctx.fail(`CG-FLU-10: 找到 ${floatBlocks.length} 個 desktop B-floating block，cascade 無法機械驗證`);
      } else {
        const { declarations } = floatBlocks[0];
        if (!/border-radius\s*:\s*var\(\s*--fluent-radius-xl\s*\)/.test(declarations)) {
          ctx.fail('CG-FLU-10: Rule 47 缺 border-radius: var(--fluent-radius-xl)');
        }
        if (!/(?<![-\w])border\s*:\s*1px\s+solid\s+var\(\s*--glass-shell-border\s*\)/.test(declarations)) {
          ctx.fail('CG-FLU-10: Rule 47 缺 border: 1px solid var(--glass-shell-border)');
        }
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

  // CG-FLU-16 ← 129-T5 / CD-129-3：scrollbar-gutter 全站保留溝寬（spec S3 驗收條件 6）
  // 為什麼要這支守衛：這條規則在無頭環境「看不見」——刪掉它，CDP 目視、截圖、既有 lint
  // 全都不會有任何反應，只有 owner 在傳統捲軸的真機上才會發現兩頁搜尋列又錯開 7.5px。
  // 本檔其他規則都有視覺表面，唯獨這條沒有 → 這就是它值得一支存在性守衛的理由。
  {
    id: 'CG-FLU-16',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      // 只認**頂層 `html` 區塊**裡的宣告（PR#156 Codex P2）：本規則守的是「文件層級的溝寬」這個
      // 對齊契約。日後若有獨立捲動的元件在本檔自己宣告 scrollbar-gutter，它與 html 不在同一個
      // cascade 上競爭，不該被這條擋下——整檔計數會把那種合法寫法誤判成「cascade 歧義」。
      // selector 對巢狀在 @media 內的規則會帶 `@media (...)` 前綴，所以 === 'html' 同時也擋住
      // 「被包進 media query」（那會讓只有寬螢幕有溝寬，窄桌機仍然錯位）。
      // ctx.blocks / ctx.text 皆已 stripCssComments ⇒ 說明註解不會被算進來。
      const htmlBlocks = ctx.blocks.filter((b) => b.selector.trim() === 'html');
      const hits = htmlBlocks.flatMap(
        (b) => [...b.declarations.matchAll(/scrollbar-gutter\s*:\s*([^;}]+)/g)],
      );
      if (hits.length === 0) {
        const elsewhere = ctx.blocks
          .filter((b) => /scrollbar-gutter/.test(b.declarations))
          .map((b) => b.selector.trim());
        ctx.fail(elsewhere.length
          ? `CG-FLU-16: 頂層 \`html\` 區塊裡沒有 scrollbar-gutter 宣告（另有 ${elsewhere.length} 筆掛在 `
            + `\`${elsewhere.join('` / `')}\`）— 129-T5 要的是文件層級的溝寬，文件層級才是視窗捲軸的擁有者`
          : 'CG-FLU-16: fluent-materials.css 缺 scrollbar-gutter 宣告（129-T5 / CD-129-3）— '
            + '少了它，搜尋頁右側不再保留捲軸溝寬，兩頁搜尋列在真機上會差 7.5px');
        return;
      }
      if (hits.length > 1) {
        ctx.fail(`CG-FLU-16: 頂層 \`html\` 的 scrollbar-gutter 宣告出現 ${hits.length} 次 — cascade 歧義，`
          + '實際生效的是最後一條；請收斂成單一宣告');
      }
      for (const h of hits) {
        const v = h[1].replace(/!important/g, '').trim();
        if (v !== 'stable') {
          ctx.fail(`CG-FLU-16: scrollbar-gutter 值必須是 \`stable\`（單邊），實際為 \`${v}\``);
        }
      }
    },
  },

  // CG-FLU-17 ← 146b-T3b CD-146b-16 §1：.page-layer 降為純契約，全檔材質宣告一律禁止
  {
    id: 'CG-FLU-17',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      // 146b-T3b：owner 真機驗收撤銷了 Rule 49 的材質（雙圈圓角/雙 hairline 疊在恢復的
      // chrome 上）。不變式反轉——今天要守的是「.page-layer 不得再畫任何東西」。
      // 用 flattenRuleBlocks 掃全檔（含 [data-theme="dim"] 與任何 @media 巢狀），對
      // 「每一個」命中的 block 都檢查，不挑第一個/最後一個（FE-GUARD-14：挑一個 = fail-open，
      // 這裡改成「逐一檢查、任何一個違規就 fail」，天生不會漏看第二個 block）。
      const FORBIDDEN = [
        ['background', /(?<![-\w])background(-color|-image)?\s*:/i],
        ['border', /(?<![-\w])border(-radius|-color|-width|-style|-top|-bottom|-left|-right)?\s*:/i],
        ['overflow', /(?<![-\w])overflow(-x|-y)?\s*:/i],
        ['backdrop-filter', /(-webkit-)?backdrop-filter\s*:/i],
        ['filter', /(?<![-\w])filter\s*:/i],
        ['transform', /(?<![-\w])transform\s*:/i],
        ['contain', /(?<![-\w])contain\s*:/i],
      ];
      // pre-merge（grok-4.6 branch review P3 第 3 條）：契約的另一半是「padding-inline 恆 0」，
      // 而**沒有任何機械閘守得到它**——對齊 e2e 比的是兩個「子元素」的左緣，父層 .page-layer
      // 被加上 padding-inline 時兩個子元素一起內縮，相對差仍是 0（FE-CSS-21 形狀 2 的鏡像）；
      // test_layer_itself_no_blur 只讀 backdrop-filter。這裡補上：水平 padding 只准是 0。
      const HORIZ_PAD = /(?<![-\w])padding(?:-inline(?:-start|-end)?|-left|-right)?\s*:\s*([^;]+)/gi;
      const isZero = (v) => /^0(?:px|rem|em|%)?$/i.test(v.trim());
      for (const { selector, declarations } of flattenRuleBlocks(ctx.blocks)) {
        if (!selector.includes('.page-layer')) continue;
        for (const m of [...declarations.matchAll(HORIZ_PAD)]) {
          const parts = m[1].trim().split(/\s+/);
          // padding: A            → 水平 = A
          // padding: A B [C [D]]  → 水平 = B
          // padding-inline/-left/-right: A → 水平 = A
          const horizontal = /(?<![-\w])padding\s*:/i.test(m[0]) && parts.length > 1 ? parts[1] : parts[0];
          if (!isZero(horizontal)) {
            ctx.fail(
              `CG-FLU-17: ${selector} 的水平內距是 \`${horizontal}\` — .page-layer 的契約是 `
              + 'padding-inline 恆 0，--layer-inset 只出現在**直接子區塊**（CD-146b-7）。'
              + '把內距加在 Layer 自己身上，四頁內容會一起再內縮，而工具列與內容仍然對齊'
              + '⇒ 對齊 e2e 與其餘守衛全綠，切頁看起來「整體變窄」卻查不到是哪條規則。',
            );
          }
        }
        for (const [name, re] of FORBIDDEN) {
          if (re.test(declarations)) {
            ctx.fail(
              `CG-FLU-17: ${selector} 宣告了 ${name} — .page-layer 已降為純契約`
              + '（CD-146b-16 §1），不得再畫材質；.page-layer 只是四頁共用的掛載點與'
              + 'padding-inline:0/no-containing-block 契約，視覺一律交給各自的 chrome',
            );
          }
        }
      }
      // 掃描結果 0 筆命中是本卡完成後的合法終態（.page-layer 目前沒有任何 CSS 規則，只剩
      // Rule 49 的契約註解）——這不是錯誤，這條守衛守的是「不存在材質宣告」，規則整個
      // 不存在時這個不變式自動成立，不需要另外判斷「規則存不存在」。
    },
  },

  // CG-LAYER-01 ← 146b-T4：.showcase-grid/.actress-grid 水平內距必須真吃 var(--layer-inset)
  // 樣板：CG-FLU-17 的「0/1/≥2 三岔拒絕歧義」＋頂層 block 掃描（FE-GUARD-14）。
  // getComputedStyle 分不出字面 1.5rem 與 --layer-inset（同為 24px）——e2e 對此無鑑別力。
  {
    id: 'CG-LAYER-01',
    file: 'pages/showcase/02-image-grid.css',
    kind: 'fn',
    check(ctx) {
      const SEL = '.showcase-grid, .actress-grid';
      // 檔案寫成 `.showcase-grid,\n.actress-grid`（換行 co-list）；正規化空白後再比對，
      // 避免字面 === 因換行假紅（CG-PC-07 註解已記錄同一寫法）。
      const norm = (s) => s.replace(/\s+/g, ' ').trim();
      const hits = ctx.blocks.filter((b) => norm(b.selector) === SEL);
      if (hits.length === 0) {
        ctx.fail(`CG-LAYER-01: 找不到頂層 \`${SEL}\` block（水平內距契約消失）`);
        return;
      }
      if (hits.length > 1) {
        ctx.fail(
          `CG-LAYER-01: 找到 ${hits.length} 個頂層 \`${SEL}\` block，cascade 無法機械驗證——`
          + `命中：${hits.map((b) => JSON.stringify(b.declarations.trim().slice(0, 60))).join(' | ')}`,
        );
        return;
      }
      const { declarations } = hits[0];
      // 只盯 padding / padding-inline 開頭的宣告，避免誤傷 gap: 1.5rem
      const padDecls = [...declarations.matchAll(/(?<![-\w])(padding(?:-inline)?)\s*:\s*([^;]+)/gi)];
      if (padDecls.length === 0) {
        ctx.fail(`CG-LAYER-01: \`${SEL}\` 缺少 padding / padding-inline 宣告`);
        return;
      }
      for (const m of padDecls) {
        const prop = m[1];
        const val = m[2].trim();
        // 水平分量不得殘留字面 1.5rem / 24px（padding: V H 取第二個；padding-inline 整值；
        // padding: X 單值會同時作用於水平——同樣禁止字面）
        if (prop.toLowerCase() === 'padding-inline') {
          if (/^(?:1\.5rem|24px)\b/.test(val) || /\b(?:1\.5rem|24px)\b/.test(val)) {
            if (!/var\(\s*--layer-inset\s*\)/.test(val)) {
              ctx.fail(
                `CG-LAYER-01: \`${SEL}\` 的 ${prop} 殘留字面水平內距 \`${val}\`——`
                + '必須吃 var(--layer-inset)',
              );
            }
          }
        } else {
          // padding: 可能是 1 值、2 值、3/4 值；水平 = 單值本身，或 2/3/4 值的第 2 個
          const parts = val.trim().split(/\s+/);
          const horizontal = parts.length === 1 ? parts[0] : parts[1];
          if (/^(?:1\.5rem|24px)$/.test(horizontal)) {
            ctx.fail(
              `CG-LAYER-01: \`${SEL}\` 的 ${prop} 水平分量是字面 \`${horizontal}\`——`
              + '必須改吃 var(--layer-inset)（不能靠與 token 數值巧合相等）',
            );
          }
        }
      }
      if (!/var\(\s*--layer-inset\s*\)/.test(declarations)) {
        ctx.fail(
          `CG-LAYER-01: \`${SEL}\` 的 declarations 未出現 var(--layer-inset)`,
        );
      }
    },
  },

  // CG-LAYER-02 ← 146b-T6：.search-bar 水平內距必須真吃 var(--layer-inset)
  // 樣板：CG-FLU-16 的「0/1/≥2 三岔拒絕歧義」＋頂層 block 掃描（FE-GUARD-14）。
  // getComputedStyle 分不出字面 1.5rem 與 --layer-inset（同為 24px）——e2e 對此無鑑別力。
  {
    id: 'CG-LAYER-02',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      const SEL = '.search-bar';
      // 單一 selector，無換行 co-list；trim 即可（對照 CG-LAYER-01 的 norm）。
      const hits = ctx.blocks.filter((b) => b.selector.trim() === SEL);
      if (hits.length === 0) {
        ctx.fail(`CG-LAYER-02: 找不到頂層 \`${SEL}\` block（水平內距契約消失）`);
        return;
      }
      if (hits.length > 1) {
        ctx.fail(
          `CG-LAYER-02: 找到 ${hits.length} 個頂層 \`${SEL}\` block，cascade 無法機械驗證——`
          + `命中：${hits.map((b) => JSON.stringify(b.declarations.trim().slice(0, 60))).join(' | ')}`,
        );
        return;
      }
      const { declarations } = hits[0];
      // 只盯 padding / padding-inline 開頭的宣告，避免誤傷 gap: 1.5rem
      const padDecls = [...declarations.matchAll(/(?<![-\w])(padding(?:-inline)?)\s*:\s*([^;]+)/gi)];
      if (padDecls.length === 0) {
        ctx.fail(`CG-LAYER-02: \`${SEL}\` 缺少 padding / padding-inline 宣告`);
        return;
      }
      for (const m of padDecls) {
        const prop = m[1];
        const val = m[2].trim();
        // 水平分量不得殘留字面 1.5rem / 24px（padding: V H 取第二個；padding-inline 整值；
        // padding: X 單值會同時作用於水平——同樣禁止字面）
        if (prop.toLowerCase() === 'padding-inline') {
          if (/^(?:1\.5rem|24px)\b/.test(val) || /\b(?:1\.5rem|24px)\b/.test(val)) {
            if (!/var\(\s*--layer-inset\s*\)/.test(val)) {
              ctx.fail(
                `CG-LAYER-02: \`${SEL}\` 的 ${prop} 殘留字面水平內距 \`${val}\`——`
                + '必須吃 var(--layer-inset)',
              );
            }
          }
        } else {
          // padding: 可能是 1 值、2 值、3/4 值；水平 = 單值本身，或 2/3/4 值的第 2 個
          const parts = val.trim().split(/\s+/);
          const horizontal = parts.length === 1 ? parts[0] : parts[1];
          if (/^(?:1\.5rem|24px)$/.test(horizontal)) {
            ctx.fail(
              `CG-LAYER-02: \`${SEL}\` 的 ${prop} 水平分量是字面 \`${horizontal}\`——`
              + '必須改吃 var(--layer-inset)（不能靠與 token 數值巧合相等）',
            );
          }
        }
      }
      if (!/var\(\s*--layer-inset\s*\)/.test(declarations)) {
        ctx.fail(
          `CG-LAYER-02: \`${SEL}\` 的 declarations 未出現 var(--layer-inset)`,
        );
      }
    },
  },

  // CG-LAYER-03 ← 146b-T7：Rule 46（.settings-header/.avlist-header）水平內距必須真吃
  // var(--layer-inset)。樣板：checkLayerInsetHorizontalPadding（CG-LAYER-01/02 抽出；
  // 0/1/≥2 三岔＝ CG-FLU-16）。
  {
    id: 'CG-LAYER-03',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      checkLayerInsetHorizontalPadding(ctx, {
        id: 'CG-LAYER-03',
        selector: ':is(.settings-header, .avlist-header)',
      });
    },
  },

  // CG-LAYER-06/07/08 ← pre-merge（grok-4.6 branch review P3 第 1 條）：
  // 對齊測試比的是「chrome 左緣 vs 內容左緣」的**差**。只要兩側的字面都恰好等於 token 值，
  // 即使兩側都沒有真的吃 var()，差仍然是 0 ⇒ e2e 照樣綠（FE-CSS-21 形狀 1）。
  // T4-T7 只補了 chrome 側（CG-LAYER-02 .search-bar、CG-LAYER-03 兩個 header）與瀏覽頁的
  // 內容側（CG-LAYER-01 .showcase-grid），**其餘三頁的內容側沒有守衛**——本輪補齊。
  // 樣板一律 checkLayerInsetHorizontalPadding（0/1/≥2 三岔＝ CG-FLU-16，FE-GUARD-14）。
  // ⚠️ 說明頁 .help-cards 刻意不在此列：它的水平內距在 base 是 1rem、只有 @media ≥1024
  // 才是 var(--layer-inset)（CD-146b-20 手機內距不強制統一），而本 helper 只掃頂層 block。
  // 那一格是已接受的 residual，不是遺漏。
  {
    id: 'CG-LAYER-06',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      checkLayerInsetHorizontalPadding(ctx, { id: 'CG-LAYER-06', selector: '.result-area' });
    },
  },
  {
    id: 'CG-LAYER-07',
    file: 'pages/settings.css',
    kind: 'fn',
    check(ctx) {
      checkLayerInsetHorizontalPadding(ctx, { id: 'CG-LAYER-07', selector: '#settingsForm' });
    },
  },
  {
    id: 'CG-LAYER-08',
    file: 'pages/scanner.css',
    kind: 'fn',
    check(ctx) {
      checkLayerInsetHorizontalPadding(ctx, { id: 'CG-LAYER-08', selector: '.avlist-container' });
    },
  },

  // CG-LAYER-04 ← 146b-T8：.search-container 的 min-height 必須吃 var(--mobile-topbar-height)
  // （與 T2 改成 token 的 .main-content padding-top 配對；字面 56px 是本 branch 引入的幻影捲動回歸）。
  // 樣板：checkContainerMinHeightUsesMobileTopbar（CG-FLU-16 的 0/1/≥2；FE-GUARD-14 單檔單 selector）。
  {
    id: 'CG-LAYER-04',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      checkContainerMinHeightUsesMobileTopbar(ctx, {
        id: 'CG-LAYER-04',
        selector: '.search-container',
      });
    },
  },

  // CG-LAYER-05 ← 146b-T8：.showcase-container 同上（瀏覽頁那一半）。
  // 樣板同 CG-LAYER-04；各自獨立、不跨檔聚合（刻意不抄 CG-PC-02 的 join 形狀）。
  {
    id: 'CG-LAYER-05',
    file: 'pages/showcase/01-toolbar.css',
    kind: 'fn',
    check(ctx) {
      checkContainerMinHeightUsesMobileTopbar(ctx, {
        id: 'CG-LAYER-05',
        selector: '.showcase-container',
      });
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
      const sc = ctx.load(SHOWCASE_FULL).raw;
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
  // ── 146b-T8（2026-09-11；第 2 輪訂正事實主張）重判註記：維持現狀，不改本 rule 邏輯 ──
  // 掃描機制：extractMediaBodies(css, condRegex)（本檔 :159-176）用條件 regex 掃**全檔**
  // 所有符合的 @media block，再 .join('\n') 成一段做 .test()——屬 FE-GUARD-14 聚合形狀。
  // 「掃描範圍」不是單一區間，而是全檔所有命中該條件 regex 的 block。
  // 今天 showcase.css 命中 /max-width:\s*899px/ 的 @media 完整清單（grep -n 核對）：
  //   :366-372  (min-width: 481px) and (max-width: 899px)   ← 481–899 四欄
  //   :387-448  (max-width: 899px)                          ← poster-crop 擴 ≤899
  //   :595-606  (max-width: 899px)                          ← 工具列/網格手機 gutter
  //   :1632-1640 (max-width: 899px) and (pointer: coarse)   ← touch footer 反轉
  // 事實訂正：146b-T4（f0b53db9 / CD-146b-17）**確實改過**其中一個命中 block
  // （:596-599 `.showcase-toolbar/.showcase-grid/.actress-grid { padding-inline:
  // var(--layer-inset-mobile) }`）。search.css 那半（:860-935 附近的斷點段）經查無此問題。
  // 為什麼今天沒有假綠：本 rule 對聚合字串做的都是「必須包含 X」的正向存在性斷言——
  // 混進無關 block 不會讓它變綠、也不會變紅；T4 那次改動也沒有觸發假綠。
  // 維持現狀：依「守衛的退場」，答案仍是「我們得再收斂一次」（工程成本，非使用者損失），
  // 且它既沒擋住我們、也沒有要跟著改——不修。
  // 下次重判的真正觸發條件（語意，不用行號——行號會漂移）：
  //   (a) 本 rule 的任何一個斷言從正向存在性改成需要判斷最終 cascade 勝出者；或
  //   (b) 有人回報它該紅卻沒紅。
  // 那時才是重判的當下；不要只因「改到某個行號附近」就自動重寫本 rule。
  {
    id: 'CG-PC-02',
    file: SHOWCASE_FULL,
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
    file: SHOWCASE_FULL,
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
      const scText = ctx.load(SHOWCASE_FULL).text;
      const mh2 = scText.match(/\.lightbox-content\s+\.lightbox-cover\.has-cover\s+img\s*\{([^}]+)\}/);
      if (!mh2) ctx.fail('CG-PC-04: showcase.css modal-hug img 規則應保留');
      else if (!mh2[1].includes('width: 100%')) ctx.fail('CG-PC-04: showcase.css modal-hug img 缺 width: 100%');
    },
  },

  // CG-PC-05 ← TestUS11HeroCardMobileFix（showcase ↔ search 雙檔 hero）
  {
    id: 'CG-PC-05',
    file: 'pages/showcase/02-image-grid.css',
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
      // FE-GUARD-14：同條件可能有多個 @media body（T2 把 991.98 與 1024 都收成 1023.98
      // 後出現兩個）；不可寫死 [0]。遍歷全部 matching bodies，找含 .info-grid-pair 的那些。
      // 語意：至少一個 body 必須含 .info-grid-pair（fail-closed）；若有多個，**全部**都要
      // collapse 成 1fr（比「任一個即可」更強——避免後寫的錯誤宣告靠 cascade 蓋掉正確的）。
      const b1024 = extractMediaBodies(ctx.text, MW1024);
      if (!b1024.length) ctx.fail('CG-PC-06: 找不到 @media (max-width: 1023.98px) block');
      else {
        const withPair = b1024
          .map((body) => ({ body, collapse: ruleBody(body, '\\.info-grid-pair') }))
          .filter(({ collapse }) => collapse !== null);
        if (!withPair.length) {
          ctx.fail('CG-PC-06: ≤1023.98px 內找不到 .info-grid-pair collapse 規則');
        } else {
          for (const { collapse } of withPair) {
            if (!collapse.includes('grid-template-columns: 1fr;')) {
              ctx.fail('CG-PC-06: ≤1023.98px .info-grid-pair 應 collapse 回 grid-template-columns: 1fr;');
              break;
            }
          }
        }
      }
    },
  },

  // CG-PC-07 ← TestUS5ShowcaseGridIs3Col（≤480 showcase-grid = repeat(3,1fr)）
  {
    id: 'CG-PC-07',
    file: 'pages/showcase/02-image-grid.css',
    kind: 'fn',
    check(ctx) {
      // 108-T5：selector 由 .showcase-grid 擴為 .showcase-grid,\n.actress-grid（co-listed）→ 放寬 anchor 容納併列選擇器
      const target = extractMediaBodies(ctx.text, MW480).filter((b) => /\.showcase-grid\b[^{}]*\{/.test(b));
      if (!target.length) ctx.fail('CG-PC-07: 找不到含 .showcase-grid 的 ≤480 block');
      else {
        const m = target[0].match(/\.showcase-grid\b[^{}]*\{([^}]*)\}/);
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
    file: SHOWCASE_FULL,
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
    file: 'pages/showcase/08-remainder.css',
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
      const scRaw = ctx.load(SHOWCASE_FULL).raw;
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

  // CG-PC-14 ← test_card_shape_media_aspect_ratio_has_height_auto（119-PR Codex P1：純單檔 CSS
  // 機械檢查應搬 lint、不進 pytest，CLAUDE.md「lint 守衛規則」north-star）。
  // 定位 showcase.css 卡型 @media (min-width: 900px) 區塊——body 同時含 .showcase-grid.shape-poster
  // 與 aspect-ratio、且條件不含 max-width（排除 900-1099 等純欄數階梯區塊；忠實鏡射被刪 pytest
  // TestPosterCropThresholdAlignment._card_shape_media_min_width 的定位邏輯：brace-balance 掃全部
  // @media，篩 body 同時命中兩個 marker）。找不到／找到不止一個 → fail（不得 fail-open 回預設值）。
  // 判準逐條配對計數：aspect-ratio 出現次數 == aspect-ratio…;height:auto 配對次數（FE-CSS-08：
  // width/height 都寫死時 aspect-ratio 會被完全忽略）—— 只驗「文字裡出現過 height: auto」是
  // fail-open，刪掉其中一條仍會綠，故不可用 body.includes('height: auto')。
  {
    id: 'CG-PC-14',
    file: 'pages/showcase/02-image-grid.css',
    kind: 'fn',
    check(ctx) {
      // ctx.text 已由 loadFile 用 stripCssComments 去除 /* */ 註解（該區塊上方註解本身含
      // "aspect-ratio" 字樣，未去註解會誤判 marker 命中或計數膨脹）。
      const css = ctx.text;
      const matches = [];
      for (const m of css.matchAll(/@media\s*([^{]*?)\s*\{/g)) {
        const cond = m[1];
        let depth = 1;
        let i = m.index + m[0].length;
        while (i < css.length && depth > 0) {
          if (css[i] === '{') depth += 1;
          else if (css[i] === '}') depth -= 1;
          i += 1;
        }
        const body = css.slice(m.index + m[0].length, i - 1);
        if (body.includes('.showcase-grid.shape-poster') && body.includes('aspect-ratio')) {
          matches.push({ cond, body });
        }
      }
      if (matches.length !== 1) {
        ctx.fail(
          `CG-PC-14: showcase.css 卡型 @media 應恰好一個（body 含 .showcase-grid.shape-poster `
            + `且 aspect-ratio），實得 ${matches.length}——找不到目標區塊，不得 fail-open`,
        );
        return;
      }
      const { cond, body } = matches[0];
      if (/max-width/.test(cond)) {
        ctx.fail(`CG-PC-14: 卡型 @media 條件不得含 max-width（抓到欄數階梯區塊？）: ${cond.trim()}`);
        return;
      }
      const arCount = (body.match(/aspect-ratio\s*:/g) || []).length;
      const pairedCount = (body.match(/aspect-ratio\s*:[^;]+;\s*height:\s*auto/g) || []).length;
      if (arCount !== pairedCount) {
        ctx.fail(
          `CG-PC-14: showcase.css 卡型區塊（@media ${cond.trim()}）內每個 aspect-ratio 旁必須有 `
            + `height: auto（FE-CSS-08：width/height 都寫死時 aspect-ratio 會被完全忽略）—— `
            + `${arCount} 個 aspect-ratio、僅 ${pairedCount} 個與 height: auto 配對`,
        );
      }
    },
  },

  // ══ T3 sub-commit 3b：handoff CSS 半邊（B 組 CG-RO-01..03）+ §B 散檔（C 組 CG-SB-01..03）══
  // B 組 = handoff receiver own-half（net+tag；整-class delete defer→96d，CD-96-12）。
  // C 組 = §B standalone 檔（CG-SB-01/02 整檔 delete；CG-SB-03 切 CSS 半邊）。忠實 port（CD-96c-2）。

  // CG-RO-01（TestReadonlyDisabledStateGuard CSS 半邊）已隨 TASK-104-T4 移除——四鈕唯讀停用態
  // 整套拔除（HTML 半邊見 static_guard_lint.mjs、JS payload 半邊見 web/routers/showcase.py），
  // .is-readonly-disabled class 定義本身已從 showcase.css 刪除、.lb-rescrape-gear:not(:disabled):hover
  // 簡化回 :hover（gear 已無任何 :disabled 綁定，:not(:disabled) 恆真、為死權重）。整條規則（含正向
  // opacity/cursor 斷言與負向 hover-gating 斷言）皆針對此已死功能，無其他可留用部分，故整條移除。

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
    file: SHOWCASE_FULL,
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

  // CG-SB-03 ← 原 test_search_icon_mutex.py 的 CSS 半邊（search.css；in-block line scan）。
  //           該支 pytest 已於 141a 全數退場——HTML 半邊由 static_guard_lint [lint-guard 141a-T7] 承接。
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
      const showcaseRaw = ctx.load(SHOWCASE_FULL).raw;
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
      // ── test_source_pill_css_exists_with_selectors：全部 6 selector ──
      // 118a-T7（spec F3）：`.source-pill-badge` 從清單移除——該元件已刪除（唯一使用者是
      // BETA 標記）。這條正向鎖與 static_guard_lint 的 [118a-T7] 反向鎖直接衝突，
      // 兩者必須同時處置；保留其餘 6 條不變（`.source-pill-mt-badge` 是不同元件，仍在用）。
      for (const sel of [
        '.source-pill',
        '.source-pill--uncensored',
        '.source-pill--manual-only',
        '.source-pill-mt-badge',
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
    file: 'pages/showcase/08-remainder.css',
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
    file: 'pages/showcase/05-lightbox.css',
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
    file: SHOWCASE_FULL,
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
    file: 'pages/showcase/05-lightbox.css',
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

  // ══ 108-T4：touch overlay 移除（T2）+ folder touch-hide（T3）回歸鎖 [lint-guard:108-T4] ══
  // 兩個相鄰 @media (pointer: coarse) { } block（showcase.css:1126 / :1133）長得幾乎一樣，
  // 若只用整檔字串比對會被第一個（.lightbox-cover .cover-actions，不在 T4 範圍）或註解裡的
  // 舊字面誤命中（fail-open）。CG-TOUCH-01 一律先錨定 `75a-US3c` 註解 + 緊接的 @media 開頭，
  // 手工 brace-walk 切出「那一個」block 才做斷言（比照 extractMobileMediaBody 的手法）。

  // CG-TOUCH-01 ← T2：touch 裝置 overlay force-show（item 1/3）已刪、item 2（footer-hover 常駐）
  // 仍在。用 75a-US3c 註解錨定唯一 block（防撞到 :1126 的 .lightbox-cover .cover-actions 或
  // :1155 提到 75a-US3c 字面的另一段註解）。
  {
    id: 'CG-TOUCH-01',
    file: 'pages/showcase/05-lightbox.css',
    kind: 'fn',
    check(ctx) {
      const raw = ctx.raw;
      const anchorRe = /\/\*\s*75a-US3c:[\s\S]*?\*\/\s*@media\s*\(\s*pointer\s*:\s*coarse\s*\)\s*\{/;
      const m = anchorRe.exec(raw);
      if (!m) {
        ctx.fail('CG-TOUCH-01 [lint-guard:108-T4]: 找不到 75a-US3c 註解緊接的 @media (pointer: coarse) block（G1 anchor 遺失，selector/註解被改名？）');
        return;
      }
      const braceStart = m.index + m[0].length - 1; // '{' 位置
      let depth = 0;
      let end = null;
      for (let i = braceStart; i < raw.length; i += 1) {
        if (raw[i] === '{') depth += 1;
        else if (raw[i] === '}') {
          depth -= 1;
          if (depth === 0) { end = i; break; }
        }
      }
      if (end === null) {
        ctx.fail('CG-TOUCH-01 [lint-guard:108-T4]: 75a-US3c @media (pointer: coarse) block 未平衡（brace 不對稱）');
        return;
      }
      const block = stripCssComments(raw.slice(braceStart + 1, end));
      // 正向 sanity：item(2) footer-hover/footer-default 仍在此 block 內（確認錨對了正確 block）
      if (!/\.av-card-preview\s+\.footer-hover\s*\{/.test(block)) {
        ctx.fail('CG-TOUCH-01 [lint-guard:108-T4]: 75a-US3c block 缺 .av-card-preview .footer-hover（item(2) 應保留）');
      }
      if (!/\.av-card-preview\s+\.footer-default\s*\{/.test(block)) {
        ctx.fail('CG-TOUCH-01 [lint-guard:108-T4]: 75a-US3c block 缺 .av-card-preview .footer-default（item(2) 應保留）');
      }
      // 負向鎖：T2 已刪除的 item(1)/item(3) overlay force-show 不得在此 block 內重新出現
      if (/\.av-card-preview-overlay\s*\{[^}]*opacity\s*:\s*1/.test(block)) {
        ctx.fail('CG-TOUCH-01 [lint-guard:108-T4]: 75a-US3c block 內重新出現 .av-card-preview-overlay opacity:1（T2 已刪除的 touch overlay force-show 回歸）');
      }
      if (/\.actress-card-overlay\s*\{[^}]*opacity\s*:\s*1/.test(block)) {
        ctx.fail('CG-TOUCH-01 [lint-guard:108-T4]: 75a-US3c block 內重新出現 .actress-card-overlay opacity:1（T2 已刪除的 touch overlay force-show 回歸）');
      }
    },
  },

  // CG-TOUCH-02 ← T2：無封面卡片（.missing-cover）overlay 常駐顯示例外規則須保留（:2677 一帶）。
  // 這條與 CG-TOUCH-01 刪的 force-show 長得像（都設 opacity:1），差別是 scope 精準綁
  // .missing-cover（無封面才需要常駐可點），非 CG-TOUCH-01 鎖的「touch 裝置全域」force-show。
  {
    id: 'CG-TOUCH-02',
    file: 'pages/showcase/08-remainder.css',
    kind: 'selector-require',
    markers: ['.missing-cover', '.av-card-preview-overlay'],
    pattern: /(?=[\s\S]*?opacity\s*:\s*1)(?=[\s\S]*?pointer-events\s*:\s*auto)/,
    msg: '[lint-guard:108-T4] .missing-cover .av-card-preview-overlay 例外規則須含 opacity:1 + pointer-events:auto（T2 保留：無封面卡片必須常駐可點）',
  },

  // CG-TOUCH-03 ← T3：folder 觸控隱藏 gate 須維持 any-hover:none（真‧純觸控），不可收窄回裸
  // pointer:coarse（會誤藏 2-in-1 裝置的 folder，Codex#1 P1 抓到的回歸）。用 @media header/body
  // 雙向綁定：反向從含 .js-open-folder 的 block 找其 header 斷言（防「narrow gate」型 mutation），
  // 而非正向從 any-hover:none 找 body（防「gate 對但綁錯 selector」漏檢）。
  {
    id: 'CG-TOUCH-03',
    file: 'pages/showcase/05-lightbox.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.text; // 去註解，避免註解內字面 any-hover:none / .js-open-folder 假陽性
      const mediaRe = /@media\b([^{]*)\{/g;
      let m;
      let found = false;
      while ((m = mediaRe.exec(css)) !== null) {
        let depth = 1;
        let i = mediaRe.lastIndex;
        while (i < css.length && depth > 0) {
          if (css[i] === '{') depth += 1;
          else if (css[i] === '}') depth -= 1;
          i += 1;
        }
        const body = css.slice(mediaRe.lastIndex, i - 1);
        if (!/\.js-open-folder\b/.test(body)) continue;
        found = true;
        const header = m[1];
        if (!/any-hover\s*:\s*none/.test(header)) {
          ctx.fail(`CG-TOUCH-03 [lint-guard:108-T4]: .js-open-folder 所在 @media 條件缺 any-hover:none（gate 被收窄回裸 pointer:coarse，2-in-1 裝置會誤藏 folder，Codex#1 P1 回歸）— header=${header.trim()}`);
        }
        const rm = body.match(/\.js-open-folder\s*\{([^}]*)\}/);
        if (!rm) {
          ctx.fail('CG-TOUCH-03 [lint-guard:108-T4]: .js-open-folder 所在 @media block 內找不到 .js-open-folder 規則本體');
        } else {
          if (!/display\s*:\s*none/.test(rm[1])) ctx.fail('CG-TOUCH-03 [lint-guard:108-T4]: .js-open-folder 應 display: none');
          if (!/!important/.test(rm[1])) ctx.fail('CG-TOUCH-03 [lint-guard:108-T4]: .js-open-folder display:none 應帶 !important');
        }
      }
      if (!found) {
        ctx.fail('CG-TOUCH-03 [lint-guard:108-T4]: 找不到含 .js-open-folder 規則的 @media block（folder touch-hide gate 消失）');
      }
    },
  },

  // CG-TOUCH-04 ← T7：純觸控（any-hover:none）裝置合成 hover 時壓住卡片 overlay（AC-B1/B7 硬化，
  // Codex pre-merge P2 + PR#117 二審 P2）。反向從「裸 @media (any-hover: none)」（排除 T3 folder 的
  // 三條件 gate）且含 .av-card-preview-overlay 的 block 找，逐 rule 對 **selector 文字** 斷言：
  // 影片/女優壓制 selector 須含 :hover（sticky-hover 是 :hover 現象；只驗宣告 fail-open）、**不得含
  // :focus-within**（會藏鍵盤/Switch 聚焦控制、a11y 違規）、影片帶 :not(.missing-cover)（保破圖卡例外）；
  // 宣告須 opacity:0（女優另補 pointer-events:none，其 show 規則帶 pointer-events:auto）。
  {
    id: 'CG-TOUCH-04',
    file: 'pages/showcase/05-lightbox.css',
    kind: 'fn',
    check(ctx) {
      const css = ctx.text;
      const mediaRe = /@media\b([^{]*)\{/g;
      let m;
      let found = false;
      while ((m = mediaRe.exec(css)) !== null) {
        const header = m[1];
        // 只取 T7 的裸 any-hover:none block（排除 T3 folder 的 pointer:coarse and hover:none and any-hover:none）
        if (!/any-hover\s*:\s*none/.test(header) || /pointer\s*:\s*coarse/.test(header)) continue;
        let depth = 1;
        let i = mediaRe.lastIndex;
        while (i < css.length && depth > 0) {
          if (css[i] === '{') depth += 1;
          else if (css[i] === '}') depth -= 1;
          i += 1;
        }
        const body = css.slice(mediaRe.lastIndex, i - 1);
        if (!/\.av-card-preview-overlay\b/.test(body)) continue; // 確認是 overlay 壓制 block
        found = true;
        // 逐 rule 拆 selector + declarations（selector 無 braces）→ 對「selector 文字」斷言，
        // 非只驗宣告（否則拿掉 :hover 只留 :focus-within 仍匹配宣告塊 → fail-open，Codex PR#117 二審 P2-1）。
        const rules = [...body.matchAll(/([^{}]+)\{([^}]*)\}/g)].map((mm) => ({ sel: mm[1].trim(), decl: mm[2] }));
        const vRule = rules.find((r) => /\.av-card-preview-overlay\b/.test(r.sel));
        const aRule = rules.find((r) => /\.actress-card-overlay\b/.test(r.sel));
        if (!vRule) {
          ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 找不到影片卡 .av-card-preview-overlay 觸控壓制規則');
        } else {
          if (!/:hover\b/.test(vRule.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片卡 overlay 壓制 selector 須含 :hover（sticky-hover 是 :hover 現象；只驗宣告會 fail-open，Codex PR#117 二審 P2-1）');
          if (/:focus-within\b/.test(vRule.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片卡 overlay 壓制不得含 :focus-within（會藏聚焦控制、鍵盤/Switch a11y 違規，Codex PR#117 二審 P2-2）');
          if (!/:not\(\.missing-cover\)/.test(vRule.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片 overlay 壓制須帶 :not(.missing-cover)（保破圖卡例外常駐）');
          if (!/:not\(\.always-visible\)/.test(vRule.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片 overlay opacity 壓制須帶 :not(.always-visible)（hero 收藏愛心常駐、不得被合成 hover 壓透明，PR#117 四審 P2）');
          if (!/opacity\s*:\s*0/.test(vRule.decl)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片卡 overlay 壓制應含 opacity:0（保 AC-B1 觸控封面乾淨）');
        }
        if (!aRule) {
          ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 找不到女優卡 .actress-card-overlay 觸控壓制規則');
        } else {
          if (!/:hover\b/.test(aRule.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 女優卡 overlay 壓制 selector 須含 :hover（fail-open 防護，Codex PR#117 二審 P2-1）');
          if (/:focus-within\b/.test(aRule.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 女優卡 overlay 壓制不得含 :focus-within（會藏聚焦的 searchActressFilms、鍵盤/Switch a11y 違規，Codex PR#117 二審 P2-2）');
          if (!/opacity\s*:\s*0/.test(aRule.decl)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 女優卡 overlay 壓制應含 opacity:0（AC-B7）');
          else if (!/pointer-events\s*:\s*none/.test(aRule.decl)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 女優卡 overlay 壓制須補 pointer-events:none（其 show 規則帶 pointer-events:auto，只壓 opacity 會留隱形 tap target）');
        }
        // T7-fix（PR#117 三審 P2）：overlay 動作鈕須 pointer-events:none——.btn-glass-circle base
        // pointer-events:auto（theme.css:1148）在 REST 態就覆蓋 overlay 的 none，看不見的 play/enrich/搜尋鈕
        // 仍可被誤觸（非 tap 進 lightbox）。鎖「有壓鈕」且影片帶 :not(.missing-cover)+:not(.always-visible)。
        const vBtn = rules.find((r) => /\.av-card-preview\b/.test(r.sel) && /\.btn-glass-circle\b/.test(r.sel));
        const aBtn = rules.find((r) => /\.actress-card-overlay\b/.test(r.sel) && /\.btn-glass-circle\b/.test(r.sel));
        if (!vBtn) {
          ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 找不到影片卡 overlay 動作鈕壓制規則（.av-card-preview … .btn-glass-circle，三審 P2：看不見的鈕仍可誤觸）');
        } else {
          if (!/pointer-events\s*:\s*none/.test(vBtn.decl)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片卡 overlay 動作鈕須 pointer-events:none（否則觸控下看不見的 play/enrich 被誤觸、非 tap 進 lightbox）');
          if (!/:not\(\.missing-cover\)/.test(vBtn.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片鈕壓制須帶 :not(.missing-cover)（破圖卡補資料鈕須可點）');
          if (!/:not\(\.always-visible\)/.test(vBtn.sel)) ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 影片鈕壓制須帶 :not(.always-visible)（hero 收藏愛心常駐須可點）');
        }
        if (!aBtn || !/pointer-events\s*:\s*none/.test((aBtn || {}).decl || '')) {
          ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 女優卡 overlay 動作鈕須 pointer-events:none（.actress-card-overlay .btn-glass-circle，三審 P2 誤觸）');
        }
      }
      if (!found) {
        ctx.fail('CG-TOUCH-04 [lint-guard:108-T7]: 找不到 @media (any-hover: none) 的卡片 overlay 觸控壓制 block（T7 sticky-hover 硬化消失）');
      }
    },
  },

  // ══ 108-T6：G5 — 女優 grid（.actress-grid）必須與影片 grid（.showcase-grid）共用同一套響應式欄數
  //    系統：base + 5 個固定斷點的 grid-template-columns 一律 co-listed `.showcase-grid, .actress-grid`，
  //    外加 T1 行動 gutter 規則（@media max-width:899）亦 co-listed。鎖 108-T5 不變式（AC-C1：女優卡與
  //    影片卡在每個斷點同寬）。三道檢查合起來對「base+5 斷點+T1 全 co-listed」契約 fail-closed：
  //      (A) 正向存在表（hard-coded 斷點表，reviewer 認可/期望）：base + 5 欄數斷點 + T1 gutter 各自
  //          必須存在一條 co-listed 且宣告錨屬性的規則。抓三類 fail-open：整塊 @media 被刪 / 斷點條件
  //          被改（如 1500→1400）/ 某斷點拿掉 .actress-grid（只剩 showcase-only）—— 原正向 .some() 只要
  //          任一斷點還在就綠、對「刪整塊」與「改斷點條件」全漏。斷點條件寫死＝功能契約，重構斷點本身
  //          即契約變更，本表故意會紅逼迫有意識更新守衛（reviewer 明確認可/期望）。
  //      (B) 負向：.actress-grid 單獨規則不得宣告任何寬度決定屬性（女優偷加自有 override，top-level 或
  //          巢狀於 @media 皆抓）。
  //      (C) 負向（對稱）：.showcase-grid 自身規則宣告寬度屬性卻未併列 .actress-grid（影片端在任意——含
  //          非-canonical——斷點偷加 showcase-only 分歧，女優 grid 於該斷點悄悄回落 base auto-fill）。
  //    欄數「值」（repeat(5)/repeat(4)/repeat(3)…）由 CG-PC-02/05/07 各自擁有；本 rule 只鎖「存在＋
  //    co-listed」不重複值斷言（分工：G5 owns「每個 canonical 斷點 actress 有併列」，CG-PC-* owns 欄數值）。
  //    ctx.text 已 stripCssComments → 天生排除註解內字面 `.actress-grid`；co-listed / 自身規則判定一律
  //    用 comma-split exact-part 比對 → 天生排除後代選擇器（`.showcase-grid .av-card…`）與 z-index
  //    sibling 規則（`.showcase-status-bar, .showcase-grid, …`：宣告 position/z-index，無寬度屬性）。 ══

  // CG-GRID-ALIGN ← 108-T6 G5，108-T5fix2 改寫：≤899 共用 co-listed + ≥900 女優階梯/影片斷點雙白名單。
  // 契約變更史：T6 版鎖「女優與影片同欄同寬」（spec-108 AC-C1）；T5fix1 推翻該標的——≥900px 影片切橫式
  // fanart、女優恆為直式 0.75，同寬 ⇒ 女優列高 1.77 倍（1920px 實測列距 284 vs 502）。新契約＝
  // 「≤899 同欄同寬（比例相近）／≥900 各走各的斷點、女優欄數 ≥ 影片欄數」。
  {
    id: 'CG-GRID-ALIGN',
    file: SHOWCASE_FULL,
    kind: 'fn',
    check(ctx) {
      // 「最終 subject」判定（Codex 四審 P2 + 五審 P2）：判斷 selector 某逗號段是否以 class `cls`
      // 為最終 subject（最後一個 combinator ` `/`>`/`+`/`~` 之後那截 compound）。
      // 認得 parent scope / 附加 class·pseudo / attribute 的同一 grid 規則
      //（`.showcase-container .showcase-grid.compact`、`.showcase-grid:has(> .x)`、
      //  `.showcase-grid[data-label="wide grid"]` 最終 subject 仍是 .showcase-grid），
      // 排除「最終 subject 是後代元素」（`.showcase-grid .av-card…`）與「grid 只出現在
      // functional pseudo 參數內」（`.foo:has(.showcase-grid)` subject 其實是 .foo）。
      // ⚠️ CSS-aware：combinator / comma 這些字元在 :has()/:not()/:is()、attribute value、字串內
      // 皆可能合法出現，naive split 會誤切（Codex 五審）。故先 stripNested 剝掉 ()/[]/引號內容
      //（追 depth + escape），使殘留的 comma/combinator 必為頂層，再切。
      const stripNested = (s) => {
        let out = '';
        let paren = 0;
        let bracket = 0;
        let quote = '';
        for (let i = 0; i < s.length; i += 1) {
          const ch = s[i];
          if (quote) {
            if (ch === '\\') i += 1; // 跳過 escape 的下一字元
            else if (ch === quote) quote = '';
            continue;
          }
          if (ch === '"' || ch === "'") { quote = ch; continue; }
          if (ch === '(') { paren += 1; continue; }
          if (ch === ')') { paren = Math.max(0, paren - 1); continue; }
          if (ch === '[') { bracket += 1; continue; }
          if (ch === ']') { bracket = Math.max(0, bracket - 1); continue; }
          if (paren === 0 && bracket === 0) out += ch;
        }
        return out;
      };
      const subjectTargets = (strippedPart, cls) => {
        const compounds = strippedPart.split(/[\s>+~]+/).filter(Boolean);
        const last = compounds[compounds.length - 1] || '';
        return new RegExp(`\\.${escapeRegExp(cls)}(?![\\w-])`).test(last);
      };
      // 先 stripNested 全 selector（()/[]/引號內容剝除）→ 殘留 comma 必為頂層 selector-list 分隔，
      // 殘留 combinator 必為頂層 → 切段後判每段最終 subject。
      const selHasSubject = (selector, cls) => stripNested(selector)
        .split(',')
        .some((part) => subjectTargets(part.trim(), cls));
      // co-listed 判定：某段最終 subject 是 .showcase-grid、且某段最終 subject 是 .actress-grid
      //（排除後代選擇器與 z-index sibling；支援 scoped / state 併列變體）
      const isCoListed = (selector) => selHasSubject(selector, 'showcase-grid')
        && selHasSubject(selector, 'actress-grid');
      const hasCoListedAnchor = (blocks, anchorRe) => blocks.some(
        ({ selector, declarations }) => isCoListed(selector) && anchorRe.test(declarations),
      );
      // 「寬度決定屬性」清單（108-T6 原表逐字保留）：任一出現即代表該規則在決定卡片寬度。
      // 逐屬性用 (行首|`;`|`{`|空白) + 屬性名 + 可選空白 + `:` 錨定，避免 padding 誤配 padding-inline
      // 之類的前綴子字串（`\s*:` 要求屬性名後直接接冒號，中間不可再有 `-xxx`）。
      const forbiddenWidthProps = [
        'grid-template-columns',
        'gap',
        'column-gap',
        'padding',
        'padding-inline',
        'padding-left',
        'padding-right',
        'padding-inline-start',
        'padding-inline-end',
        'margin-inline',
        'margin-left',
        'margin-right',
        'margin-inline-start',
        'margin-inline-end',
        'width',
        'min-width',
        'max-width',
        'inline-size',
        'min-inline-size',
        'max-inline-size',
        'box-sizing',
      ];
      // 108-T5fix2：回傳**全部**命中的屬性（舊版 .find() 只回第一個），白名單需判「命中集合 ⊆ {grid-template-columns}」。
      const declaredWidthProps = (declarations) => forbiddenWidthProps.filter(
        (prop) => new RegExp(`(^|[;{]|\\s)${escapeRegExp(prop)}\\s*:`).test(declarations),
      );

      // ── 期望表（鏡射 showcase.css，108-T5fix1 定版）───────────────────────────
      // 共用區間（≤899px）：影片走直式 poster 0.71 ≈ 女優 0.75 → 同寬即同高 → **必須 co-listed**。
      const COLS = /grid-template-columns\s*:/;
      // T2：.main-content 水平 padding 於 <1024 已歸零，負 margin-inline 補償已移除；
      // 定位錨改為仍存在的 padding-inline（12px gutter）。co-listed 不變式不變。
      const GUTTER = /padding-inline\s*:/;
      const SHARED = [
        { label: 'base grid（top-level 非-@media）', cond: null, anchor: COLS, prop: 'grid-template-columns' },
        { label: '@media (min-width: 481px) and (max-width: 899px) → 4 欄（共用）', cond: MIN481_MAX899, anchor: COLS, prop: 'grid-template-columns' },
        { label: '@media (max-width: 480px) → 3 欄（共用）', cond: MW480, anchor: COLS, prop: 'grid-template-columns' },
        { label: 'T1 行動 gutter @media (max-width: 899px)', cond: MW899, anchor: GUTTER, prop: 'padding-inline' },
      ];
      // ≥900px：影片切橫式 fanart（~3:2）、女優恆為直式 0.75 → 同寬會讓女優列高 1.77 倍。
      // 故女優改走**專屬 5 段階梯**（列高/密度對齊），影片維持自己的三段（showcase-only）。
      // 條件以 ^…$ 字面錨定 + 驗欄數值 → 斷點漂移（1350→1400）或欄數漂移（6→5）皆報紅。
      const LADDER = [
        { cond: /^\s*\(\s*min-width\s*:\s*1850px\s*\)\s*$/, cols: 7, label: '(min-width: 1850px) → 7 欄' },
        { cond: /^\s*\(\s*min-width\s*:\s*1600px\s*\)\s+and\s+\(\s*max-width\s*:\s*1849px\s*\)\s*$/, cols: 6, label: '(min-width: 1600px) and (max-width: 1849px) → 6 欄' },
        { cond: /^\s*\(\s*min-width\s*:\s*1350px\s*\)\s+and\s+\(\s*max-width\s*:\s*1599px\s*\)\s*$/, cols: 5, label: '(min-width: 1350px) and (max-width: 1599px) → 5 欄' },
        { cond: /^\s*\(\s*min-width\s*:\s*1100px\s*\)\s+and\s+\(\s*max-width\s*:\s*1349px\s*\)\s*$/, cols: 4, label: '(min-width: 1100px) and (max-width: 1349px) → 4 欄' },
        { cond: /^\s*\(\s*min-width\s*:\s*900px\s*\)\s+and\s+\(\s*max-width\s*:\s*1099px\s*\)\s*$/, cols: 3, label: '(min-width: 900px) and (max-width: 1099px) → 3 欄' },
      ];
      const VIDEO = [
        { cond: /^\s*\(\s*min-width\s*:\s*1500px\s*\)\s*$/, cols: 5, label: '(min-width: 1500px) → 5 欄' },
        { cond: /^\s*\(\s*min-width\s*:\s*1100px\s*\)\s+and\s+\(\s*max-width\s*:\s*1499px\s*\)\s*$/, cols: 4, label: '(min-width: 1100px) and (max-width: 1499px) → 4 欄' },
        { cond: /^\s*\(\s*min-width\s*:\s*900px\s*\)\s+and\s+\(\s*max-width\s*:\s*1099px\s*\)\s*$/, cols: 3, label: '(min-width: 900px) and (max-width: 1099px) → 3 欄' },
      ];
      const FIX = '若確為有意重構斷點，請同步更新本守衛的 SHARED / LADDER / VIDEO 期望表';
      // exact selector 判定：stripNested 後字面等於單一 class（擋 sidebar-state 前綴 `body.sidebar-collapsed .actress-grid`
      // 與 co-listed 回退；未來若真要 scoped 變體，改守衛而非放行 — fail-closed）。
      const isExactly = (selector, cls) => stripNested(selector).trim() === `.${cls}`;
      // 119-T1：卡型變體 `.showcase-grid.shape-poster`（直式海報，spec-119 F2）。
      // 它是「只有影片牆掛得上的 opt-in class」，結構上不可能命中 .actress-grid，
      // 故不屬於 VIDEO 三段階梯的管轄範圍（本守衛的不變式是「女優不得悄悄脫鉤」）。
      // 刻意**不驗欄數值**：plan-119 §7 允許 owner 真機驗收後只調 grid-template-columns 的數字，
      // 把數字焊進期望表會讓那條逃生口變貴。守的是「形狀」不是「數值」：
      // exact `.showcase-grid.shape-poster` + 只宣告 grid-template-columns + 單一 ≥900px media 條件。
      const isPosterVariant = (selector) => stripNested(selector).trim() === '.showcase-grid.shape-poster';
      // 單一 media 條件、以 (min-width: Npx) 起頭且 N ≥ 900，可選再接 and (max-width: Mpx)。
      const POSTER_MEDIA = /^\s*\(\s*min-width\s*:\s*(\d+)px\s*\)(?:\s+and\s+\(\s*max-width\s*:\s*\d+px\s*\))?\s*$/;
      const isPosterMedia = (media) => {
        if (media.length !== 1) return false;
        const m = POSTER_MEDIA.exec(media[0]);
        return !!m && Number(m[1]) >= 900;
      };
      // 同一 media 條件可能有多個 block（本檔 900-1099 現有兩個：影片區一個、女優階梯區一個）→ 一律掃全部。
      const rulesUnder = (cond) => extractMediaBodies(ctx.text, cond).flatMap((body) => parseRuleBlocks(body));
      // Codex T5fix2 三審 P1：同一 rule 內可重複宣告同 property（cascade 取最後者），故不能只問
      // 「有沒有出現正確值」→ 抽出**全部** grid-template-columns 宣告值，白名單要求「恰好一次且該值正確」。
      const colsDecls = (declarations) => [
        ...declarations.matchAll(/(?:^|[;{]|\s)grid-template-columns\s*:\s*([^;}]*)/g),
      ].map((m) => m[1].trim());
      const colsValueRe = (n) => new RegExp(`^repeat\\(\\s*${n}\\s*,\\s*1fr\\s*\\)$`);
      // 回傳 null=合格，否則回傳失敗原因字串
      const colsFault = (declarations, n) => {
        const decls = colsDecls(declarations);
        if (decls.length !== 1) {
          return `宣告了 ${decls.length} 次 grid-template-columns（同 rule 內重複宣告時 cascade 取最後者 \`${decls[decls.length - 1] || ''}\`，`
            + `「其中一次正確」不代表生效的那次正確）—— 每條規則只允許宣告一次`;
        }
        if (!colsValueRe(n).test(decls[0])) return `欄數不符（實際 \`${decls[0]}\`，應為 repeat(${n}, 1fr)）`;
        return null;
      };

      // ── (A) 正向・共用區間（≤899）必須 co-listed ──
      for (const { label, cond, anchor, prop } of SHARED) {
        let ok;
        if (cond === null) {
          // base：ctx.blocks 未展平，@media wrapper 的 selector 以 @ 開頭 → 濾掉只留真 top-level 規則
          const topLevel = ctx.blocks.filter(({ selector }) => !selector.trim().startsWith('@'));
          ok = hasCoListedAnchor(topLevel, anchor);
        } else {
          ok = extractMediaBodies(ctx.text, cond).some((body) => hasCoListedAnchor(parseRuleBlocks(body), anchor));
        }
        if (!ok) {
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: 共用區間缺少「${label}」的 co-listed `
              + `.showcase-grid, .actress-grid 規則（須宣告 ${prop}）—— ≤899px 影片走直式 poster 0.71 `
              + `≈ 女優 0.75，同寬即同高，兩者必須同欄同寬；整塊被刪 / 斷點條件被改 / 拿掉 .actress-grid 皆違反。${FIX}`,
          );
        }
      }

      // ── (B) 正向・女優 ≥900 五段階梯（條件字面 + 欄數 + exact selector）──
      for (const { cond, cols, label } of LADDER) {
        const hits = rulesUnder(cond).filter(({ selector }) => selHasSubject(selector, 'actress-grid'));
        if (!hits.length) {
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: 女優階梯缺少 ${label} 的 .actress-grid 規則 —— `
              + `≥900px 女優以專屬 5 段階梯對齊「列高/密度」（非卡寬），少一段即回到 T5 的過大卡片。${FIX}`,
          );
          continue;
        }
        const exact = hits.filter(({ selector }) => isExactly(selector, 'actress-grid'));
        if (!exact.length) {
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: 女優階梯 ${label} 的 selector 必須 exact \`.actress-grid\` —— `
              + `禁 sidebar-state 前綴（owner 2026-07-25 拍板：斷點 sidebar-state agnostic，側欄展開變小是全站既有性質、`
              + `女優/影片一起縮）、禁 co-listed 回退（那是 T5 的同欄同寬）。實際 selector=`
              + `${hits.map(({ selector }) => selector.replace(/\s+/g, ' ').trim()).join(' / ')}`,
          );
        } else if (exact.length > 1) {
          // Codex T5fix2 二審 P1：只驗「至少一條對」會被同 media 的第二條錯欄數 override 繞過
          //（cascade 取後者）→ 改為 canonical media 下 exact grid 規則**恰好一條**。
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: 女優階梯 ${label} 有 ${exact.length} 條 .actress-grid 規則 —— `
              + `同一斷點只允許一條（多條時 cascade 取最後者，「至少一條欄數對」不代表實際生效的那條對）。${FIX}`,
          );
        } else {
          const fault = colsFault(exact[0].declarations, cols);
          if (fault) ctx.fail(`CG-GRID-ALIGN [lint-guard:108-T5fix2]: 女優階梯 ${label} ${fault}。${FIX}`);
        }
      }

      // ── (C) 正向・影片 ≥900 三段維持 showcase-only（不得再 co-listed = 不得回退 T5）──
      for (const { cond, cols, label } of VIDEO) {
        // 119-T1：卡型變體不計入「同一斷點只允許一條」的計數——它是另一套獨立階梯（見 isPosterVariant）。
        const hits = rulesUnder(cond).filter(
          ({ selector }) => selHasSubject(selector, 'showcase-grid') && !isPosterVariant(selector),
        );
        if (!hits.length) {
          ctx.fail(`CG-GRID-ALIGN [lint-guard:108-T5fix2]: 影片 grid 缺少 ${label} 的 .showcase-grid 規則。${FIX}`);
          continue;
        }
        const coListed = hits.filter(({ selector }) => isCoListed(selector));
        if (coListed.length) {
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: 影片斷點 ${label} 不得與 .actress-grid 併列 —— `
              + `≥900px 影片是橫式 fanart、女優是直式 0.75，同寬會讓女優列高 1.77 倍（正是 T5 被推翻的原因）。${FIX}`,
          );
        } else if (hits.length > 1) {
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: 影片斷點 ${label} 有 ${hits.length} 條 .showcase-grid 規則 —— `
              + `同一斷點只允許一條（多條時 cascade 取最後者）。${FIX}`,
          );
        } else {
          const fault = colsFault(hits[0].declarations, cols);
          if (fault) ctx.fail(`CG-GRID-ALIGN [lint-guard:108-T5fix2]: 影片斷點 ${label} ${fault}。${FIX}`);
        }
      }

      // ── (D) 負向・白名單制：任何宣告「寬度決定屬性」的 grid 容器規則，必須落在上述三張表之一 ──
      //    （舊版 108-T6 是「actress-only / showcase-only 一律禁止」，會擋住 T5fix1 的階梯本身；
      //      改為精確白名單後，既保留「不得悄悄脫鉤」的原意圖，又能鎖住 sidebar-state 分岔與屬性種類。）
      //    需要 media 上下文 → flattenWithMedia（top-level media=[]；巢狀 @media 條件鏈 >1 一律不在白名單）。
      // Codex T5fix2 二審 P1：白名單放行的每一條規則，其欄數值也必須等於該 media 的期望值
      //（否則「合法 media + exact selector + 只宣告 columns」的第二條 override 會整條溜過）。
      const tableEntry = (media, table) => (media.length === 1
        ? table.find(({ cond }) => cond.test(media[0])) || null
        : null);
      const isSharedMedia = (media) => media.length === 0
        || (media.length === 1 && [MIN481_MAX899, MW480, MW899].some((re) => re.test(media[0])));
      for (const { media, selector, declarations } of flattenWithMedia(ctx.blocks)) {
        const onActress = selHasSubject(selector, 'actress-grid');
        const onShowcase = selHasSubject(selector, 'showcase-grid');
        if (!onActress && !onShowcase) continue;
        const props = declaredWidthProps(declarations);
        if (!props.length) continue;
        const where = `selector=${selector.replace(/\s+/g, ' ').trim()}${media.length ? ` @media ${media.join(' / ')}` : '（top-level）'}`;
        const onlyCols = props.length === 1 && props[0] === 'grid-template-columns';
        if (onActress && onShowcase) {
          // co-listed：只允許出現在共用區間（base / 481-899 / ≤480 / T1 gutter）
          if (!isSharedMedia(media)) {
            ctx.fail(
              `CG-GRID-ALIGN [lint-guard:108-T5fix2]: co-listed .showcase-grid, .actress-grid 規則宣告寬度決定屬性 `
                + `\`${props.join(', ')}\`，但不在共用區間（≤899px / base）—— ≥900px 兩者刻意分家。${FIX} — ${where}`,
            );
          }
        } else if (onActress) {
          const entry = tableEntry(media, LADDER);
          if (!(onlyCols && entry && isExactly(selector, 'actress-grid') && colsFault(declarations, entry.cols) === null)) {
            ctx.fail(
              `CG-GRID-ALIGN [lint-guard:108-T5fix2]: .actress-grid 單獨規則宣告寬度決定屬性 \`${props.join(', ')}\` `
                + `卻不在女優階梯白名單 —— 只允許「五段階梯條件之一 + exact \`.actress-grid\` + grid-template-columns 恰好宣告一次且欄數等於該段期望值 + 只宣告 `
                + `grid-template-columns」（gap/padding/max-width 須續由 co-listed base 提供，否則卡寬算式與影片脫鉤；`
                + `sidebar-state 前綴一律禁止）。${FIX} — ${where}`,
            );
          }
        } else if (!(() => {
          if (onlyCols && isPosterVariant(selector) && isPosterMedia(media)) return true;   // 119-T1 卡型變體階梯
          const entry = tableEntry(media, VIDEO);
          return onlyCols && entry && isExactly(selector, 'showcase-grid') && colsFault(declarations, entry.cols) === null;
        })()) {
          ctx.fail(
            `CG-GRID-ALIGN [lint-guard:108-T5fix2]: .showcase-grid 單獨規則宣告寬度決定屬性 \`${props.join(', ')}\` `
              + `卻不在影片斷點白名單（三段 ≥900 條件 + exact \`.showcase-grid\` + grid-template-columns 恰好宣告一次且欄數等於該段期望值）`
              + `或卡型變體白名單（exact \`.showcase-grid.shape-poster\` + 只宣告 grid-template-columns + 單一 (min-width: ≥900px) 條件）—— `
              + `共用區間的寬度屬性必須 co-listed，否則女優在該情境悄悄脫鉤。${FIX} — ${where}`,
          );
        }
      }
    },
  },
  {
    id: 'CG-WISH-01',
    file: 'pages/search.css',
    kind: 'fn',
    check(ctx) {
      // TASK-140-T12：三層分工搬家（不刪）。wrapper（.wishlist-panel）現在扛
      // width:100%／max-height:100%／min-height:0；.wishlist-grid 改吃 flex:1／
      // min-height:0，overflow-y:auto／align-content:start 兩條原本就在 grid 身上，
      // 沒有搬動。兩段都沿用 T9 的「整條 selector 等於 class 本身（不含逗號）＋
      // filter 取最後一個」邏輯（FE-GUARD-14：.find() 取第一個是 fail-open；D4
      // 合併後 `.wishlist-grid, .search-grid` 這種 comma-list block 必須被排除）。
      const findStandalone = (cls) => {
        const matches = ctx.blocks.filter(({ selector }) => selector.trim() === cls);
        return matches[matches.length - 1];
      };

      const panel = findStandalone('.wishlist-panel');
      if (!panel) {
        ctx.fail('CG-WISH-01: .wishlist-panel 專屬（非合併）規則區塊不存在');
      } else {
        const panelRequired = [
          [/width\s*:\s*100%/, 'width: 100%'],
          [/max-height\s*:\s*100%/, 'max-height: 100%'],
          [/min-height\s*:\s*0/, 'min-height: 0'],
        ];
        for (const [re, label] of panelRequired) {
          if (!re.test(panel.declarations)) {
            ctx.fail(`CG-WISH-01: .wishlist-panel 專屬區塊缺少 ${label}（wrapper 不再是 .result-area 撐滿版面的那一層，窄欄會重現 T9 的 110×727）`);
          }
        }
      }

      // branch review P1-1：第三層。.wishlist-empty 與 .wishlist-panel 是**兄弟**
      // flex item（不是巢狀），所以上面兩段的檢查完全罩不到它；它的子元素是
      // position:absolute ⇒ 內在寬度 0，少了寬度宣告就被 flex 壓成 0 寬。
      const empty = findStandalone('.wishlist-empty');
      if (!empty) {
        ctx.fail('CG-WISH-01: .wishlist-empty 專屬（非合併）規則區塊不存在');
      } else {
        if (!/width\s*:\s*100%/.test(empty.declarations)) {
          ctx.fail('CG-WISH-01: .wishlist-empty 專屬區塊缺少 width: 100%（子元素是 absolute ⇒ 內在寬度 0，會被 flex 壓成 0 寬的直排字，實測 w=0）');
        }
        // [Codex PR review BLOCKER 2026-09-03] TASK-141b-T10 DoD6 的空狀態淡入由 pytest 搬來這裡
        // （CLAUDE.md north-star：純字串掃描不進 pytest）。掛在同一個 findStandalone 結果上
        // 是刻意的——T10 的卡片明文要求這兩個宣告必須加進**既有那條** .wishlist-empty 規則本體，
        // 另開第二個頂層規則會讓 findStandalone 取到沒有 width:100% 的那一個而轉紅。
        const emptyFade = [
          [/opacity\s*:\s*0/, 'opacity: 0'],
          [/animation\s*:\s*wishlistEmptyFadeIn/, 'animation: wishlistEmptyFadeIn'],
        ];
        for (const [re, label] of emptyFade) {
          if (!re.test(empty.declarations)) {
            ctx.fail(`CG-WISH-01: .wishlist-empty 專屬區塊缺少 ${label}（書籤 0 筆時的空狀態會硬跳出來而不是淡入，DoD 6）`);
          }
        }
      }

      const grid = findStandalone('.wishlist-grid');
      if (!grid) {
        ctx.fail('CG-WISH-01: .wishlist-grid 專屬（非合併）規則區塊不存在');
      } else {
        const gridRequired = [
          [/flex\s*:\s*1\b/, 'flex: 1'],
          [/min-height\s*:\s*0/, 'min-height: 0'],
          [/overflow-y\s*:\s*auto/, 'overflow-y: auto'],
          [/align-content\s*:\s*start/, 'align-content: start'],
        ];
        for (const [re, label] of gridRequired) {
          if (!re.test(grid.declarations)) {
            ctx.fail(`CG-WISH-01: .wishlist-grid 專屬區塊缺少 ${label}（flex-child 版面會壞，實測回歸為 110×727 窄直行）`);
          }
        }
      }
    },
  },

  // CG-148A-URL-01 ← CD-148a-15：part 檔的 url() 只允許 data: URI 與根相對路徑（/ 開頭）或絕對 URL
  // （http(s):）——粗顆粒防呆，只問「有沒有相對 url()」，不驗路徑正確性（CD-148a-15 的刻意取捨）。
  // @import/@charset/@namespace/@layer 零出現——part 檔換了子目錄層級後，相對 url() 的解析基準會差一層。
  {
    id: 'CG-148A-URL-01',
    file: 'theme.css', // 佔位滿足 runner loadFile；實際掃描在 check() 內用 readdirSync 遍歷 pages/showcase/（比照 CG-FOCAL-01 既有形狀）
    kind: 'fn',
    check(ctx) {
      const dir = CSS('pages/showcase');
      for (const name of readdirSync(dir).filter((n) => n.endsWith('.css'))) {
        const raw = readFileSync(join(dir, name), 'utf-8');
        let text = stripCssComments(raw);                                     // 步驟 1：去註解
        text = text.replace(/url\(\s*(?:(['"])data:[\s\S]*?\1|data:[^)]*)\s*\)/gi, '');   // 步驟 2：去 data URI（含無引號形式）
        const urlRe = /url\(\s*(['"]?)([^'")]+)\1\s*\)/gi;                     // 步驟 3：查剩餘 url()
        let m;
        while ((m = urlRe.exec(text))) {
          const val = m[2];
          if (!(val.startsWith('/') || /^https?:/i.test(val))) {
            ctx.fail(`CG-148A-URL-01: pages/showcase/${name} 出現非法 url() 值（須以 / 或 http 開頭）：${val}`);
          }
        }
        if (/@import\b|@charset\b|@namespace\b|@layer\b/i.test(text)) {        // 步驟 4：查四種 at-rule
          ctx.fail(`CG-148A-URL-01: pages/showcase/${name} 出現位置敏感 at-rule（@import/@charset/@namespace/@layer 之一）`);
        }
      }
    },
  },

  // CG-148A-PARTS-01 ← T5 第 2 輪：_showcase_css.html 的 part 清單必須與 pages/showcase/ 目錄
  // 內容完全一致（同集合、同順序）。拆檔後「層疊順序」變成 template 行序這個獨立自由度，
  // 而 T9 刪掉原檔之後就再也沒有「串接 == 原檔」可以對——這條是它唯一的長期鎖。
  // 順序錯 → 瀏覽器層疊結果改變；漏掛 → 那個 part 的樣式整段不載入；兩者 lint 都不會自己紅。
  {
    id: 'CG-148A-PARTS-01',
    file: 'theme.css', // 佔位滿足 runner loadFile；實際比對在 check() 內
    kind: 'fn',
    check(ctx) {
      // 行格式檢查先於清單比對：把表示形式收斂成單一正典，讓下游 hrefRe 不必追著合法 HTML
      // 的各種等價寫法跑（屬性對調／單引號／自閉合……）。不符正典 → 大聲報行號，不會靜默少讀。
      // 格式已紅就 return，避免再跑清單比對被 parser 靜默少讀後誤報成「少了某個 part」。
      const html = loadWebFile('templates/_showcase_css.html');
      const canonicalLine = /^\s*<link href="\/static\/css\/pages\/showcase\/[^"]+\.css" rel="stylesheet">\s*$/;
      const lines = html.split(/\r?\n/);
      let formatBad = false;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (/^\s*$/.test(line)) continue;
        if (!canonicalLine.test(line)) {
          formatBad = true;
          ctx.fail(
            `CG-148A-PARTS-01: _showcase_css.html 第 ${i + 1} 行不符正典行格式：${JSON.stringify(line)}。` +
            `_showcase_css.html 只接受單一正典行格式（href 在前、雙引號、一行一個 <link>）——` +
            `這是刻意把表示形式收斂成契約，讓下游 parser 不必追著合法 HTML 的各種等價寫法跑。` +
            `等價但不同形的寫法（屬性對調、單引號、自閉合）一律在這裡擋下，不會讓 parser 靜默少讀一個 part。`
          );
        }
      }
      if (formatBad) return;

      const fromTemplate = showcasePartsFromTemplate();
      const names = readdirSync(CSS('pages/showcase')).filter((n) => n.endsWith('.css'));
      // 兩位數補零是 .sort()（字典序）能代表 A→H 數字序的**前提**，不是命名潔癖：
      // 一個沒補零的 `9-x.css` 會讓字典序把 `10-` 排到它前面，本規則就會安靜地開始說謊。
      const bad = names.filter((n) => !/^\d{2}-/.test(n));
      if (bad.length) {
        ctx.fail(
          `CG-148A-PARTS-01: pages/showcase/ 底下的 part 檔名必須是兩位數補零前綴（NN-）：${bad.join(', ')}。` +
          `本規則用字典序代表 CD-148a-1 的 A→H 順序，沒補零會讓字典序與數字序分岔。`
        );
      }
      const onDisk = names.sort().map((n) => `pages/showcase/${n}`);
      if (fromTemplate.join('|') !== onDisk.join('|')) {
        ctx.fail(
          `CG-148A-PARTS-01: _showcase_css.html 的 part 清單與 pages/showcase/ 目錄不一致——` +
          `template=[${fromTemplate.join(', ')}] vs 目錄排序=[${onDisk.join(', ')}]。` +
          `順序錯會改變瀏覽器層疊結果，漏掛會讓該 part 樣式整段不載入，兩者都不會被其他守衛抓到。`
        );
      }
    },
  },
  // ==== 162c：自 frontend_contracts／test_frontend_lint.py 搬入（按批分子區段）====
  // ---- 162c-B11 起 ----
  // （162c-B11 專屬子區段：只在此兩行之間追加）

  // 162c: TestCoverLoadingUx67Guard — fade / PRM / lb-full CSS
  {
    id: 'CG-162C-B11-01',
    file: SHOWCASE_FULL,
    kind: 'fn',
    check(ctx) {
      const pat = /([^{}]*?\.av-card-preview-img img)\s*\{[^}]*opacity:\s*0[^}]*\}/g;
      const scNc = ctx.text;
      const scMatches = [...scNc.matchAll(pat)];
      if (!scMatches.length) {
        ctx.fail('CG-162C-B11-01: showcase 找不到 opacity:0 的 .av-card-preview-img img 淡入規則 — 遷自 test_fade_rule_scoped_to_showcase_container');
        return;
      }
      for (const m of scMatches) {
        if (!m[1].includes('.showcase-container')) {
          ctx.fail(`CG-162C-B11-01: showcase 淡入規則未 compound .showcase-container：${m[1].trim()} — 遷自 test_fade_rule_scoped_to_showcase_container`);
        }
      }
      const searchNc = ctx.load('pages/search.css').text;
      const seMatches = [...searchNc.matchAll(pat)];
      if (!seMatches.length) {
        ctx.fail('CG-162C-B11-01: search.css 找不到書籤封面 opacity:0 淡入規則 — 遷自 test_fade_rule_scoped_to_showcase_container');
        return;
      }
      for (const m of seMatches) {
        if (!m[1].includes('.wishlist-grid')) {
          ctx.fail(`CG-162C-B11-01: search.css 書籤淡入規則未 compound .wishlist-grid：${m[1].trim()} — 遷自 test_fade_rule_scoped_to_showcase_container`);
        }
        if (!m[1].includes(':is(#ds-gallery-components')) {
          ctx.fail(`CG-162C-B11-01: search.css 書籤淡入規則未 compound :is(#ds-gallery-components)：${m[1].trim()} — 遷自 test_fade_rule_scoped_to_showcase_container`);
        }
      }
    },
  },
  {
    id: 'CG-162C-B11-02',
    file: SHOWCASE_FULL,
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      if (!css.includes('prefers-reduced-motion: reduce')) {
        ctx.fail('CG-162C-B11-02: showcase.css 缺 @media (prefers-reduced-motion: reduce) — 遷自 test_prm_degrades_shimmer_and_fade');
      }
      const shimmerRules = [...css.matchAll(/(?<![\w-])\.shimmer\s*\{([^}]*)\}/g)].map((m) => m[1]);
      if (!shimmerRules.some((b) => b.includes('animation: shimmer'))) {
        ctx.fail('CG-162C-B11-02: showcase.css 缺 .shimmer 基礎 animation — 遷自 test_prm_degrades_shimmer_and_fade');
      }
      if (!shimmerRules.some((b) => b.includes('animation: none'))) {
        ctx.fail('CG-162C-B11-02: showcase.css PRM 缺 .shimmer { animation: none } — 遷自 test_prm_degrades_shimmer_and_fade');
      }
      const fadeRules = [...css.matchAll(/\.av-card-preview-img img\s*\{([^}]*)\}/g)].map((m) => m[1]);
      if (!fadeRules.some((b) => b.includes('transition: none') && b.includes('opacity: 1'))) {
        ctx.fail('CG-162C-B11-02: showcase.css PRM 缺淡入退化（transition: none; opacity: 1） — 遷自 test_prm_degrades_shimmer_and_fade');
      }
    },
  },
  {
    id: 'CG-162C-B11-03',
    file: SHOWCASE_FULL,
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      const m = css.match(/\.lb-full\s*\{([^}]*)\}/);
      if (!m) {
        ctx.fail('CG-162C-B11-03: showcase.css 缺 .lb-full 規則 — 遷自 test_lb_full_css_opacity_transition_with_token');
        return;
      }
      const body = m[1];
      if (!body.includes('position: absolute') || !body.includes('opacity: 0')) {
        ctx.fail('CG-162C-B11-03: .lb-full 須 position:absolute + opacity:0 — 遷自 test_lb_full_css_opacity_transition_with_token');
      }
      if (!body.includes('pointer-events: none')) {
        ctx.fail('CG-162C-B11-03: .lb-full 須 pointer-events:none — 遷自 test_lb_full_css_opacity_transition_with_token');
      }
      if (!/transition:\s*opacity\s+var\(--fluent-duration-/.test(body)) {
        ctx.fail('CG-162C-B11-03: .lb-full transition 須用 fluent duration token — 遷自 test_lb_full_css_opacity_transition_with_token');
      }
      if (!/var\(--fluent-ease-(decel|standard)\)/.test(body)) {
        ctx.fail('CG-162C-B11-03: .lb-full transition 須用 fluent ease token — 遷自 test_lb_full_css_opacity_transition_with_token');
      }
      const shown = css.match(/\.lb-full-shown\s*\{([^}]*)\}/);
      if (!shown || !shown[1].includes('opacity: 1')) {
        ctx.fail('CG-162C-B11-03: showcase.css 缺 .lb-full-shown { opacity: 1 } — 遷自 test_lb_full_css_opacity_transition_with_token');
      }
    },
  },
  {
    id: 'CG-162C-B11-04',
    file: SHOWCASE_FULL,
    kind: 'fn',
    check(ctx) {
      const css = ctx.raw;
      const prmBlocks = [...css.matchAll(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(.*?)\n\}/gs)].map((m) => m[1]);
      if (!prmBlocks.some((b) => /\.lb-full\s*\{[^}]*transition:\s*none/.test(b))) {
        ctx.fail('CG-162C-B11-04: PRM 缺 .lb-full { transition: none } — 遷自 test_lb_full_reduced_motion_no_transition');
      }
    },
  },
  // ---- 162c-B11 迄 ----
  //
  //
  //
  // ---- 162c-B17 起 ----
  // （162c-B17 專屬子區段：只在此兩行之間追加）
  // 162c: TestMobileSimilarPanelContractGuard
  {
    id: 'CG-162C-B17-01',
    file: SHOWCASE_FULL,
    kind: 'fn',
    msg: '[lint-guard 162c-test_mobile_panel_default_hidden] 手機開燈箱 → 相似面板預設蓋住且擋住點擊 — 遷自 test_contract_animation.py',
    check(ctx) {
      const css = ctx.text;
      const mPanel = css.match(/\.similar-mobile-panel\s*\{([^}]+)\}/);
      if (!mPanel) {
        ctx.fail('CG-162C-B17-01: 找不到 .similar-mobile-panel default-hidden block');
        return;
      }
      const block = mPanel[1];
      if (!block.includes('opacity: 0')) ctx.fail('CG-162C-B17-01: .similar-mobile-panel block 缺 opacity: 0');
      if (!block.includes('visibility: hidden')) ctx.fail('CG-162C-B17-01: .similar-mobile-panel block 缺 visibility: hidden');
      if (!block.includes('pointer-events: none')) ctx.fail('CG-162C-B17-01: .similar-mobile-panel block 缺 pointer-events: none');
      const mShow = css.match(/\.similar-mobile-panel\.show\s*\{([^}]+)\}/);
      if (!mShow) {
        ctx.fail('CG-162C-B17-01: 找不到 .similar-mobile-panel.show block');
        return;
      }
      const showBlock = mShow[1];
      if (!showBlock.includes('opacity: 1')) ctx.fail('CG-162C-B17-01: .similar-mobile-panel.show 缺 opacity: 1');
      if (!showBlock.includes('visibility: visible')) ctx.fail('CG-162C-B17-01: .similar-mobile-panel.show 缺 visibility: visible');
      if (!showBlock.includes('pointer-events: auto')) ctx.fail('CG-162C-B17-01: .similar-mobile-panel.show 缺 pointer-events: auto');
    },
  },
  {
    id: 'CG-162C-B17-02',
    file: SHOWCASE_FULL,
    kind: 'fn',
    msg: '[lint-guard 162c-test_mobile_panel_desktop_safety_net] 桌面 @media(min-width:960px) 須含 similar-mobile-panel + display:none 安全網 — 遷自 test_contract_animation.py',
    check(ctx) {
      const css = ctx.raw;
      let found = false;
      for (const m of css.matchAll(/@media\s*\(\s*min-width\s*:\s*960px\s*\)/g)) {
        const window = css.slice(m.index, m.index + 500);
        if (window.includes('similar-mobile-panel') && window.includes('display: none')) {
          found = true;
          break;
        }
      }
      if (!found) {
        ctx.fail('CG-162C-B17-02: 視窗缺 display: none（@media min-width:960px 含 similar-mobile-panel 的桌面安全網）');
      }
    },
  },
  // ---- 162c-B17 迄 ----
  //
  //
  //
  // ---- 162c-B18 起 ----
  // （162c-B18 專屬子區段：只在此兩行之間追加）
  // 162c: TestMobileSimilarPanelContractGuard
  {
    id: 'CG-162C-B18-01',
    file: SHOWCASE_FULL,
    kind: 'fn',
    msg: '[lint-guard 162c-test_mobile_burst_card_class_exists] .similar-mobile-burst-card 須含 opacity:0／position:relative／transition:none — 遷自 test_contract_animation.py',
    check(ctx) {
      const css = ctx.text;
      const m = css.match(/\.similar-mobile-burst-card\s*\{([^}]+)\}/);
      if (!m) {
        ctx.fail('CG-162C-B18-01: 找不到 .similar-mobile-burst-card block');
        return;
      }
      const block = m[1];
      if (!block.includes('opacity: 0')) ctx.fail('CG-162C-B18-01: block 缺 opacity: 0');
      if (!block.includes('position: relative')) ctx.fail('CG-162C-B18-01: block 缺 position: relative');
      if (!block.includes('transition: none')) ctx.fail('CG-162C-B18-01: block 缺 transition: none');
    },
  },
  {
    id: 'CG-162C-B18-02',
    file: SHOWCASE_FULL,
    kind: 'fn',
    msg: '[lint-guard 162c-test_mobile_burst_card_img_poster_crop] .similar-mobile-burst-card img 須用 var(--poster-crop-ratio)＋右裁，禁硬編碼 4/5 — 遷自 test_contract_animation.py',
    check(ctx) {
      const css = ctx.text;
      const m = css.match(/\.similar-mobile-burst-card\s+img\s*\{([^}]+)\}/);
      if (!m) {
        ctx.fail('CG-162C-B18-02: 找不到 .similar-mobile-burst-card img block');
        return;
      }
      const block = m[1];
      if (!block.includes('aspect-ratio: var(--poster-crop-ratio)')) {
        ctx.fail('CG-162C-B18-02: img block 缺 aspect-ratio');
      }
      if (block.includes('4/5')) ctx.fail('CG-162C-B18-02: img block 不得含硬編碼 4/5');
      if (!block.includes('object-position: right center')) {
        ctx.fail('CG-162C-B18-02: img block 缺 object-position: right center');
      }
    },
  },
  {
    id: 'CG-162C-B18-03',
    file: SHOWCASE_FULL,
    kind: 'fn',
    msg: '[lint-guard 162c-test_mobile_panel_scrim_blur_token] .similar-mobile-scrim 須用 var(--fluent-blur) 並含 -webkit-backdrop-filter — 遷自 test_contract_animation.py',
    check(ctx) {
      const css = ctx.text;
      const m = css.match(/\.similar-mobile-scrim\s*\{([^}]+)\}/);
      if (!m) {
        ctx.fail('CG-162C-B18-03: 找不到 .similar-mobile-scrim block');
        return;
      }
      const block = m[1];
      if (!block.includes('var(--fluent-blur)')) {
        ctx.fail('CG-162C-B18-03: scrim block 缺 var(--fluent-blur)');
      }
      if (!block.includes('-webkit-backdrop-filter')) {
        ctx.fail('CG-162C-B18-03: scrim block 缺 -webkit-backdrop-filter');
      }
    },
  },
  // ---- 162c-B18 迄 ----
  // ---- 162c-FIX2 起（Codex branch review P2）----
  {
    id: 'CG-162C-FIX2-01',
    file: 'pages/search.css',
    kind: 'fn',
    msg: '[lint-guard 162c-test_d4_error_placeholder_min_height_fallback] 使用者看無封面／封面失敗的搜尋詳情 → placeholder 與導航指示消失；:has(error) 第一個匹配的規則須非零 min-height fallback（先剝 CSS 註解，註解掉的宣告不算） — 遷自 test_frontend_lint.py（Codex pre-merge P2 補回）',
    check(ctx) {
      // 逐字鏡射舊 pytest：_css() 已剝註解（ctx.text）→ 第一個匹配（無 g）→ 對 group(1) 斷言
      const m = ctx.text.match(/\.search-container\s+\.av-card-full-cover-wrapper:has\([^{]*cover-error-placeholder[^{]*\)\s*\{([^}]*)\}/);
      if (!m) {
        ctx.fail('CG-162C-FIX2-01: 找不到 wrapper:has(.cover-error-placeholder) fallback 規則');
        return;
      }
      if (!/min-height\s*:\s*[1-9]\d*/.test(m[1])) {
        ctx.fail('CG-162C-FIX2-01: :has(.cover-error-placeholder) 第一個匹配規則缺非零 min-height（placeholder 會塌成零高）');
      }
    },
  },
  {
    id: 'CG-162C-FIX2-02',
    file: 'pages/search.css',
    kind: 'fn',
    msg: '[lint-guard 162c-test_d4b_loading_placeholder_min_height_fallback] 使用者看載入中的搜尋詳情 → shimmer 與導航指示消失；:has(loading) 第一個匹配的規則須非零 min-height fallback（先剝 CSS 註解，註解掉的宣告不算） — 遷自 test_frontend_lint.py（Codex pre-merge P2 補回）',
    check(ctx) {
      // 逐字鏡射舊 pytest：_css() 已剝註解（ctx.text）→ 第一個匹配（無 g）→ 對 group(1) 斷言
      const m = ctx.text.match(/\.search-container\s+\.av-card-full-cover-wrapper:has\([^{]*cover-loading-placeholder[^{]*\)\s*\{([^}]*)\}/);
      if (!m) {
        ctx.fail('CG-162C-FIX2-02: 找不到 wrapper:has(.cover-loading-placeholder) fallback 規則');
        return;
      }
      if (!/min-height\s*:\s*[1-9]\d*/.test(m[1])) {
        ctx.fail('CG-162C-FIX2-02: :has(.cover-loading-placeholder) 第一個匹配規則缺非零 min-height（placeholder 會塌成零高）');
      }
    },
  },
  // ---- 162c-FIX2 迄 ----
  // ---- 162c-FIX6 起（本地全量實剪補回）----
  {
    id: 'CG-162C-FIX6-01',
    file: 'pages/showcase/08-remainder.css',
    kind: 'fn',
    msg: '[lint-guard 162c-test_picker_css_rules_present] 使用者在女優燈箱開候選挑選器 → .actress-picker-overlay 頂層規則須 position: fixed，否則浮層掉進頁面流、被裁掉或蓋不住，挑不到候選要關掉重來 — 遷自 test_frontend_lint.py（TestPickerIntegrationGuard；本地實剪驗證補回）',
    check(ctx) {
      // 逐字鏡射舊 pytest（同 FIX2 作法）：_css() 已剝註解（ctx.text）→ \.actress-picker-overlay\s*\{[^}]*\} 第一個匹配 → 含 position: fixed
      const m = ctx.text.match(/\.actress-picker-overlay\s*\{[^}]*\}/);
      if (!m) {
        ctx.fail('CG-162C-FIX6-01: 找不到 .actress-picker-overlay 規則');
        return;
      }
      if (!m[0].includes('position: fixed')) {
        ctx.fail('CG-162C-FIX6-01: .actress-picker-overlay 第一個匹配規則缺 position: fixed');
      }
    },
  },
  // ---- 162c-FIX6 迄 ----
  //
  //
  //
];

// 解析 _showcase_css.html 的 <link href> 出現順序——單一來源＝ CD-148a-3 的 template，
// 本檔零硬編清單。未來再拆出第 9 個 part，template 一改，這裡自動跟著讀到。
// CG-148A-PARTS-01 的行格式檢查已把 template 收斂成單一正典形狀，所以這裡的 hrefRe
// 不必再追著合法 HTML 的各種等價寫法跑；測試端改讀目錄，本函式是唯一還 parse template 的地方。
function showcasePartsFromTemplate() {
  const html = loadWebFile('templates/_showcase_css.html');
  const hrefRe = /<link\b[^>]*\bhref="\/static\/css\/(pages\/showcase\/[^"]+\.css)"[^>]*>/g;
  const parts = [];
  let m;
  while ((m = hrefRe.exec(html))) parts.push(m[1]);
  if (parts.length === 0) {
    throw new Error('showcasePartsFromTemplate: _showcase_css.html 內找不到任何 pages/showcase/*.css <link>（template 格式被改了？）');
  }
  return parts;
}

// 依 template 給的順序，把 8 個 part 的 raw 內容串接成一份完整字串（等價於拆檔前的 showcase.css）。
// 依序呼叫 loadFile(p) 讀各 part（共用同一份 fileCache，不重複讀檔）。
function readShowcaseFull() {
  return showcasePartsFromTemplate().map((p) => loadFile(p).raw).join('');
}

// ── per-file read+parse cache（同檔多 rule 共用，讀一次 → stripCssComments → parseRuleBlocks）──
const fileCache = new Map();
function loadFile(rel) {
  if (fileCache.has(rel)) return fileCache.get(rel);
  const raw = rel === SHOWCASE_FULL ? readShowcaseFull() : readFileSync(CSS(rel), 'utf-8');
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
  // check() 內 ctx.load(...) 也可能丟 ENOENT（例如 template 幽靈 part）；與上方 read-fail
  // 同形：轉成 fail+continue，讓後續規則（含 CG-148A-PARTS-01）仍能跑完再累積 exit。
  try {
    KINDS[rule.kind](rule, ctx);
  } catch (e) {
    fail(`${rule.id}: 執行失敗 — ${e && e.message ? e.message : e}`);
  }
}

if (hadError) process.exit(1);
console.log(`✓ css-guard: ${RULES.length} 條 CSS-block guard 全過`);
