#!/usr/bin/env node
/**
 * i18n_lint.mjs — i18n key 存在性 / parity / orphan / forbidden-word 建網（96a-T2，zero-dep）
 *
 * 取代 test_frontend_lint.py 的 ≥14 個手維護 i18n-key 清單 class + test_i18n.py 的
 * HELP_KEYS(345 行)——把「靜態 t() call-site ↔ locale leaf key」的機械對照移出 pytest
 * （north-star：能用 lint 機械處理的不進 pytest、不耗 Codex 審）。
 *
 * 五檢：
 *   1. used-but-missing（RED）：每個靜態 t('key') 必須 ∈ zh_TW leaf-key 集，否則 exit 1。
 *   2. parity（warn，--strict 才 fail）：zh_TW 每個 leaf key 於 zh_CN/en/ja 存在
 *      （開發期 warn、milestone 同步；沿用 test_i18n.py::TestAllLocalesKeyCompleteness 政策）。
 *   3. orphan（warn）：zh_TW 有但全 codebase 無「靜態」t() 引用的 key（動態/後端 core.i18n
 *      組的 key 靜態掃不到 → 只 warn，不誤殺）。
 *   4. forbidden-word（RED）：四語 leaf 值不得含「推薦」（PRD wording）/「風味」（scanner tone,
 *      CD-96-11）。另有 focal 語氣規則的 key-scoped 禁詞（見 SCOPED_FORBIDDEN_*）。
 *   5. backend-title-key（RED）：web/routers/*.py 傳給通知中心的 notif.* title_key 必須 ∈ zh_TW leaf-key 集。
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
// FORBIDDEN_WORDS = 全產品詞彙禁令（PRD 拒絕清單）：掃四語全部 leaf value。
// SCOPED_FORBIDDEN_WORDS = focal 這組文案的語氣規則（CD-152d-4b），只掃 SCOPED_FORBIDDEN_KEYS。
// 兩套不可以合併——合併就會擋下「尋找燦爛的演出片段」這類合法用詞（「爛」是「燦爛」子字串）。
// spec-180：舊頁名／舊詞回流守衛（CD-180-14）；不禁單獨的「最愛」「Favorite」（女優收藏要用）
const FORBIDDEN_WORDS = ['推薦', '熱門', '熱度', '風味', '列表生成', '產生網頁', '生成网页', '产生网页', 'リスト生成', 'ページ生成', '最愛資料夾', '最爱文件夹', 'お気に入りフォルダ', 'Favorite Folder', 'Favorite folder', 'favorite folder', 'Scanner']; // 未來擴充只改此陣列（CD-96a-4 / CD-96-11）
const SCOPED_FORBIDDEN_WORDS = ['太慢', '爛', '跑不動', '效能不足'];
const SCOPED_FORBIDDEN_KEYS = [
  'settings.scraper.focal_help',
  'notif.focal_auto_disabled',
  'showcase.lightbox.mask_focal_too_slow_auto_disabled',
  'showcase.lightbox.mask_focal_too_slow_hint',
];
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
  'settings.sources.mt_probe_hint_title', //      ← TestMetatubeB6I18n
  'settings.sources.mt_probe_hint_reason1',
  'settings.sources.mt_probe_hint_reason2',
  'settings.sources.mt_probe_hint_reason3',
  // 118a-T9：CF 來源「為什麼不能按」的兩句文案。模板改成 window.t(cfUnavailableMessageKey())
  // 之後是 dynamic key，掃描器看不見（CD-96a-2 直接跳過動態 key）——遷移前那句靜態
  // window.t('…jl_desktop_only') 本來是被檢 1 機械守著存在性的，不補進來就是淨損失。
  'showcase.rescrape.jl_desktop_only', //   ← 沒有 transport（dev／區網伺服器）
  'showcase.rescrape.cf_window_restart', // ← 有 transport 但這個站的視窗沒起來／已被摧毀
  'showcase.rescrape.cf_window_preparing', // ← 168d-fix-T2：殼回報這個站的視窗還在準備
  'showcase.rescrape.cf_window_not_built', // ← 168e-T14：App 內但驗證視窗沒建成（SSR in_shell）
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

// 葉節點走訪只有這一份：檢 4（全域禁詞，只要值）與檢 4b（key-scoped 禁詞，要 key＋值）
// 共用它，免得兩支各自演化出不一樣的「什麼算葉節點」。
function collectLeafEntries(obj, prefix, out) {
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      collectLeafEntries(v, full, out);
    } else if (typeof v === 'string') {
      out.push([full, v]);
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

const NOTIF_KEY_RE = /["'](notif\.[a-zA-Z0-9_]+)["']/g;

// stripPythonNoiseLines（PR#176 Codex P2 修正）：NOTIF_KEY_RE 掃的是 web/routers/*.py 的
// 全部原始文字，註解或無關常數裡巧合出現的 "notif.xxx" 字面也會被要求要有 zh_TW 翻譯——
// 這是純粹的開發摩擦（不是 static_guard_lint 那條「守衛全綠而對帳被拔掉」的漏報風險：真正
// 傳給 _emit_notif(...) 的 title_key 是程式碼裡的字串字面，不在註解/docstring 內，剝除註解
// 不會讓它從掃描結果消失）。做法與 static_guard_lint.mjs 的 stripPythonNoise 同形狀：逐行
// 剝掉整行/行尾註解與三引號 docstring，剝掉的內容換成等量空白——**逐行處理、輸出與輸入
// 行數一一對應**，故呼叫端仍可用原始行索引 i 組出 `${rel}:${i + 1}` 的正確行號（硬需求，
// 不可剝成一整坨讓行號漂掉）。字串字面內的 '#'（例如 URL fragment）不會被誤剝成註解起點。
function stripPythonNoiseLines(lines) {
  const out = new Array(lines.length);
  let tripleDelim = null; // null | "'''" | '"""'（跨行 docstring 未結束時延續到下一行）
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    const n = line.length;
    let result = '';
    let i = 0;
    let inStr = null;
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
        result += ' '.repeat(n - i);
        i = n;
        continue;
      }
      if (ch === "'" || ch === '"') {
        if (line.slice(i, i + 3) === ch.repeat(3)) {
          const closeIdx = line.indexOf(ch.repeat(3), i + 3);
          if (closeIdx === -1) {
            result += ' '.repeat(n - i);
            tripleDelim = ch.repeat(3);
            i = n;
          } else {
            result += ' '.repeat(closeIdx + 3 - i);
            i = closeIdx + 3;
          }
          continue;
        }
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
  return out;
}

function scanBackendTitleKeys() {
  const files = [];
  walk(join(REPO_ROOT, 'web', 'routers'), ['.py'], files);
  const used = new Map(); // key -> ['file:line', ...]
  for (const f of files) {
    const rawLines = readFileSync(f, 'utf8').split('\n');
    const lines = stripPythonNoiseLines(rawLines); // 剝除註解/docstring，行數與 rawLines 一一對應
    const rel = f.slice(REPO_ROOT.length + 1);
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let m;
      NOTIF_KEY_RE.lastIndex = 0;
      while ((m = NOTIF_KEY_RE.exec(line)) !== null) {
        const key = m[1];
        if (!used.has(key)) used.set(key, []);
        used.get(key).push(`${rel}:${i + 1}`);
      }
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

// 檢 5：backend-title-key（RED）— 驗證 web/routers/*.py 傳給通知中心的 notif.* title_key
const backendUsed = scanBackendTitleKeys();
const backendMissing = [];
for (const [key, locs] of backendUsed) {
  if (!zhTwKeys.has(key)) backendMissing.push({ key, locs });
}
if (backendMissing.length) {
  err(
    `[i18n-lint backend-title-key] ${backendMissing.length} 個後端 notif.* title_key 不存在於 zh_TW.json：`,
  );
  for (const { key, locs } of backendMissing) {
    console.error(`    '${key}'  (${locs.join(', ')})`);
  }
}

// 檢 4：forbidden-word（RED）— 掃四語全 leaf 值（全產品詞彙禁令）
for (const name of Object.keys(LOCALE_FILES)) {
  const data = localeData[name];
  if (!data) continue; // 讀取失敗已於上方回報；forbidden 只在讀得到時掃
  const values = [];
  const leafEntries = [];
  collectLeafEntries(data, '', leafEntries);
  for (const [, v] of leafEntries) values.push(v);
  for (const word of FORBIDDEN_WORDS) {
    const hits = values.filter((v) => v.includes(word));
    if (hits.length) {
      err(`${name}.json 有 ${hits.length} 個值含禁詞「${word}」（PRD/scanner tone 規則）：`);
      for (const h of hits.slice(0, 5)) console.error(`    "${h.slice(0, 60)}"`);
    }
  }
}

// 檢 4b：focal 語氣規則（RED）— 只掃 SCOPED_FORBIDDEN_KEYS；錯誤訊息印 key
{
  const scopedKeySet = new Set(SCOPED_FORBIDDEN_KEYS);
  for (const name of Object.keys(LOCALE_FILES)) {
    const data = localeData[name];
    if (!data) continue;
    const entries = [];
    collectLeafEntries(data, '', entries);
    for (const [key, value] of entries) {
      if (!scopedKeySet.has(key)) continue;
      for (const word of SCOPED_FORBIDDEN_WORDS) {
        if (value.includes(word)) {
          err(
            `${name}.json key '${key}' 含 focal 語氣禁詞「${word}」：\"${value.slice(0, 60)}\"`,
          );
        }
      }
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
