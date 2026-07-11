#!/usr/bin/env node
/**
 * i18n_lint.mjs — i18n key 存在性 / parity / orphan / forbidden-word 建網（96a-T2，zero-dep）
 *
 * 取代 test_frontend_lint.py 的 ≥14 個手維護 i18n-key 清單 class + test_i18n.py 的
 * HELP_KEYS(345 行)——把「靜態 t() call-site ↔ locale leaf key」的機械對照移出 pytest
 * （north-star：能用 lint 機械處理的不進 pytest、不耗 Codex 審）。
 *
 * 四檢：
 *   1. used-but-missing（RED）：每個靜態 t('key') 必須 ∈ zh_TW leaf-key 集，否則 exit 1。
 *   2. parity（warn，--strict 才 fail）：zh_TW 每個 leaf key 於 zh_CN/en/ja 存在
 *      （開發期 warn、milestone 同步；沿用 test_i18n.py::TestAllLocalesKeyCompleteness 政策）。
 *   3. orphan（warn）：zh_TW 有但全 codebase 無「靜態」t() 引用的 key（動態/後端 core.i18n
 *      組的 key 靜態掃不到 → 只 warn，不誤殺）。
 *   4. forbidden-word（RED）：四語 leaf 值不得含「推薦」（PRD wording）/「風味」（scanner tone,
 *      CD-96-11）。
 *
 * 掃描標的＝靜態可解析的 t('key') / window.t('key') / w.t('key')（w = window alias）。
 * 動態/拼接 key（t(varName)、t(a ? 'x' : 'y')、t('x' + y)）一律跳過（CD-96a-2）。
 *
 * 用法：
 *   node scripts/i18n_lint.mjs                 # 掃真 repo
 *   node scripts/i18n_lint.mjs <locale-dir>    # locale 讀 scratch 副本（call-site 仍掃真 repo，供 mutation 自驗）
 *   node scripts/i18n_lint.mjs --strict        # parity/orphan 升為 fail
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..');

// ---- args：拆 flag 與 locale-dir 覆蓋 ----
const argv = process.argv.slice(2);
const STRICT = argv.includes('--strict');
const localeArg = argv.find((a) => !a.startsWith('--'));
const LOCALES_DIR = localeArg ? resolve(localeArg) : join(REPO_ROOT, 'locales');

const LOCALE_FILES = { zh_TW: 'zh_TW.json', zh_CN: 'zh_CN.json', en: 'en.json', ja: 'ja.json' };
const FORBIDDEN_WORDS = ['推薦', '風味']; // 未來擴充只改此陣列（CD-96a-4 / CD-96-11）
const ORPHAN_PREVIEW = 10;

// 「靜態掃不到但必須存在」的 key allowlist：承接自 96a-T3 刪除的 i18n pytest class 的
// existence 保證。這些 key 在 zh_TW 存在，但全 repo（web 前端 + 後端 core.i18n）實測
// 無任何靜態/動態 call-site（grep=0）＝ inherited orphan。併入 used-set 使 used-but-missing
// 續守其存在性（plan-96a DoD[a] "不留缺口"／"存疑往 KEEP 靠"）。
// 註：這些是 orphan-candidate，未來 locale orphan-cleanup（非 96a 範圍，CD-96a-4）可一併移除，
//     屆時同步從本清單移除即可。
const KNOWN_UNSCANNED_KEYS = [
  'showcase.search.video', //           ← TestShowcaseActressI18n（影片模式搜尋 placeholder）
  'showcase.unit.videos_count', //      ← TestShowcaseActressI18n（部數單位）
  'settings.sources.mt_connect_success_toast', // ← TestMetatubeB6I18n（metatube 連線 toast）
  'settings.sources.mt_probe_hint_title', //      ← TestMetatubeB6I18n
  'settings.sources.mt_probe_hint_reason1',
  'settings.sources.mt_probe_hint_reason2',
  'settings.sources.mt_probe_hint_reason3',
];

let hadError = false;
function err(msg) {
  console.error(`✗ i18n_lint: ${msg}`);
  hadError = true;
}
function warn(msg) {
  console.warn(`⚠ i18n_lint: ${msg}`);
}

// ---- locale 讀取 + leaf-key 收集（比照 test_i18n.py _get_all_leaf_keys）----
const loadErrors = new Map();
function loadLocale(name) {
  const p = join(LOCALES_DIR, LOCALE_FILES[name]);
  try {
    return JSON.parse(readFileSync(p, 'utf8'));
  } catch (e) {
    // 只記錄，不自行判 RED/warn——由 caller 依 primary/secondary 政策決定
    // （primary zh_TW 缺 = 硬 RED；secondary 缺 = warn / --strict fail，與 parity 同政策）
    loadErrors.set(name, e.message);
    return null;
  }
}

function collectLeafKeys(obj, prefix, out) {
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      collectLeafKeys(v, full, out);
    } else {
      out.add(full);
    }
  }
}

function collectLeafValues(obj, out) {
  for (const v of Object.values(obj)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      collectLeafValues(v, out);
    } else if (typeof v === 'string') {
      out.push(v);
    }
  }
}

// ---- call-site 掃描（真 repo，永遠不受 locale-dir arg 影響）----
function walk(dir, exts, out) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    if (e.name === '__tests__' || e.name === 'vendor' || e.name === 'node_modules') continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) {
      walk(full, exts, out);
    } else if (exts.includes(extname(e.name))) {
      out.push(full);
    }
  }
}

// precise：
//   - 負向 lookbehind 擋 set(/createElement(/foo.t(（t 前為 word char 或 '.'）
//   - 明確允許 window.|w.|bare t(
//   - 尾隨 lookahead (?=\s*[),]) 要求 literal 為「完整第一參數」（後接 ) 或 , 參數分隔），
//     故 t('prefix' + x)（拼接）不匹配——引號後是 '+' 非 ),（CD-96a-2 跳過動態/拼接 key）
const T_CALL_RE = /(?<![A-Za-z0-9_$.])(?:(?:window|w)\.)?t\(\s*['"]([a-zA-Z0-9_.]+)['"](?=\s*[),])/g;

// 剝註解再掃（避免 doc-comment 內的 t('key') 示例誤報）。over-strip 為安全方向：
// 最壞＝漏掉某真實 key（false-negative，不會誤 RED），orphan 為 warn 可容忍。
function stripComments(text, ext) {
  if (ext === '.html') {
    return text.replace(/\{#[\s\S]*?#\}/g, ' ').replace(/<!--[\s\S]*?-->/g, ' ');
  }
  if (ext === '.js') {
    // 行註解剝除要求 '//' 前非 ':'，避免誤砍字串內 URL（'https://…'）後同行的 t()
    // （即便誤砍也是安全方向＝漏 key，不會誤 RED；此 guard 進一步降低漏檢）
    return text.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/(?<!:)\/\/.*$/gm, ' ');
  }
  return text;
}

function scanCallSites() {
  const files = [];
  walk(join(REPO_ROOT, 'web', 'templates'), ['.html'], files);
  walk(join(REPO_ROOT, 'web', 'static', 'js'), ['.js'], files);
  const used = new Map(); // key -> [relpath, ...]
  for (const f of files) {
    const text = stripComments(readFileSync(f, 'utf8'), extname(f));
    const rel = f.slice(REPO_ROOT.length + 1);
    let m;
    T_CALL_RE.lastIndex = 0;
    while ((m = T_CALL_RE.exec(text)) !== null) {
      const key = m[1];
      if (!used.has(key)) used.set(key, []);
      used.get(key).push(rel);
    }
  }
  return used;
}

// ---- main ----
// 每個 locale 檔只讀一次（zh_TW 主 + 三 secondary），避免重複 I/O 與重複錯誤訊息
const zhTW = loadLocale('zh_TW');
if (!zhTW) {
  err(`無法讀取主 locale zh_TW.json：${loadErrors.get('zh_TW')}`);
  process.exit(1); // 無法讀主 locale = 硬失敗
}
const SECONDARY = ['zh_CN', 'en', 'ja'];
const localeData = { zh_TW: zhTW };
for (const name of SECONDARY) localeData[name] = loadLocale(name);
// secondary 讀取失敗 = warn（--strict 升 fail），與 parity 同政策（缺 key 只 warn）
for (const name of SECONDARY) {
  if (!localeData[name]) {
    const msg = `${name}.json 無法讀取/解析（milestone 前不擋）：${loadErrors.get(name)}`;
    if (STRICT) err(msg);
    else warn(msg);
  }
}

const zhTwKeys = new Set();
collectLeafKeys(zhTW, '', zhTwKeys);

const used = scanCallSites();
// 併入 allowlist：靜態掃不到但須守存在性的 inherited-orphan/dynamic key（見 KNOWN_UNSCANNED_KEYS）
for (const k of KNOWN_UNSCANNED_KEYS) {
  if (!used.has(k)) used.set(k, ['[known-unscanned allowlist]']);
}

// 檢 1：used-but-missing（RED）
const missing = [];
for (const [key, files] of used) {
  if (!zhTwKeys.has(key)) missing.push({ key, file: files[0] });
}
if (missing.length) {
  err(`${missing.length} 個 t() 引用的 key 不存在於 zh_TW.json：`);
  for (const { key, file } of missing.slice(0, 20)) {
    console.error(`    '${key}'  (${file})`);
  }
}

// 檢 4：forbidden-word（RED）— 掃四語全 leaf 值
for (const name of Object.keys(LOCALE_FILES)) {
  const data = localeData[name];
  if (!data) continue; // 讀取失敗已於上方回報；forbidden 只在讀得到時掃
  const values = [];
  collectLeafValues(data, values);
  for (const word of FORBIDDEN_WORDS) {
    const hits = values.filter((v) => v.includes(word));
    if (hits.length) {
      err(`${name}.json 有 ${hits.length} 個值含禁詞「${word}」（PRD/scanner tone 規則）：`);
      for (const h of hits.slice(0, 5)) console.error(`    "${h.slice(0, 60)}"`);
    }
  }
}

// 檢 2：parity（warn / --strict fail）
for (const name of SECONDARY) {
  const data = localeData[name];
  if (!data) continue; // 讀取失敗已回報
  const keys = new Set();
  collectLeafKeys(data, '', keys);
  const parityMissing = [...zhTwKeys].filter((k) => !keys.has(k));
  if (parityMissing.length) {
    const msg = `${name}.json 缺 ${parityMissing.length} 個 zh_TW key（milestone 同步）：${parityMissing.slice(0, 5).join(', ')}`;
    if (STRICT) err(msg);
    else warn(msg);
  }
}

// 檢 3：orphan（warn / --strict fail）
const orphans = [...zhTwKeys].filter((k) => !used.has(k));
if (orphans.length) {
  const msg = `${orphans.length} 個 zh_TW key 無靜態 t() 引用（可能後端 core.i18n / JS 動態組，非必然孤兒）：${orphans.slice(0, ORPHAN_PREVIEW).join(', ')}`;
  if (STRICT) err(msg);
  else warn(msg);
}

if (hadError) {
  process.exit(1);
}
console.log(
  `✓ i18n_lint: ${used.size} 個靜態 t() key 全存在於 zh_TW（${zhTwKeys.size} leaf）；無禁詞。` +
    (STRICT ? '' : ' (parity/orphan 為 warn，--strict 可升 fail)'),
);
