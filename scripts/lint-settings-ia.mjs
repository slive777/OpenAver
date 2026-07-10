#!/usr/bin/env node
/**
 * lint-settings-ia.mjs — IA 位置回歸鎖（95b-T4，zero-dep）
 *
 * 鎖死 settings.html「列表生成」兩層 IA 分層（CD-95b-1/3/4）：
 *   - 顯示模式 / 輸出目錄 / 輸出檔名（avlistMode/OutputDir/OutputFilename）必在
 *     「離線 HTML 匯出」摺疊容器內（G-B3 顯示模式僅影響匯出、G-B5 輸出目錄/檔名為匯出專用）
 *   - 最小尺寸 / 排序 / 順序 / 每頁（avlistMinSize/Sort/Order/ItemsPerPage）
 *     必在摺疊外（G-B2/G-B4，閘門與雙棲顯示預設留外層）
 *   → 三內四外 = 全 7 form id 皆鎖位（防搬回常顯區的靜默回歸）
 *
 * 手段：DOM ancestry。錨定摺疊容器 `<div x-show="galleryExport" ...>`，
 * 以 div-only 平衡計數求其真正閉合位（void element 非 div、不影響 div 巢狀，
 * 故繞過通用 tag-depth scan 的 void-set 漏列風險），得容器 span；
 * 再斷言各 avlist id 落在 span 內/外。佐證交叉檢查：閉合緊鄰
 * `<!-- /collapsible-content galleryExport -->` 註解，防深度掃描與人工註解漂移。
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
// 預設驗真檔；可傳路徑 arg（供 mutation 自驗指向 scratch 副本，不污染真檔）
const HTML_PATH = process.argv[2]
  ? resolve(process.argv[2])
  : join(__dirname, '..', 'web', 'templates', 'settings.html');

const FLAG = 'galleryExport';
const CONTAINER_OPEN = `x-show="${FLAG}"`;
const CLOSE_COMMENT = `<!-- /collapsible-content ${FLAG} -->`;
const MUST_BE_INSIDE = ['avlistMode', 'avlistOutputDir', 'avlistOutputFilename'];
const MUST_BE_OUTSIDE = ['avlistMinSize', 'avlistSort', 'avlistOrder', 'avlistItemsPerPage'];

function fail(msg) {
  console.error(`✗ lint-settings-ia: ${msg}`);
  process.exit(1);
}

function countOccurrences(haystack, needle) {
  let n = 0;
  let i = haystack.indexOf(needle);
  while (i !== -1) {
    n += 1;
    i = haystack.indexOf(needle, i + needle.length);
  }
  return n;
}

const html = readFileSync(HTML_PATH, 'utf8');

// 〔c〕結構完整：容器開標籤與關閉註解各恰一個
const openCount = countOccurrences(html, CONTAINER_OPEN);
if (openCount !== 1) {
  fail(`預期恰一個 '${CONTAINER_OPEN}'，實得 ${openCount}（摺疊容器結構已改，請對照 CD-95b-7）`);
}
const commentCount = countOccurrences(html, CLOSE_COMMENT);
if (commentCount !== 1) {
  fail(`預期恰一個 '${CLOSE_COMMENT}'，實得 ${commentCount}（關閉註解遺失/重複，lint 錨點失效）`);
}

// 求容器開標籤的 '>' 結束位（屬性值內無 '>'，此模板成立）
const xShowIdx = html.indexOf(CONTAINER_OPEN);
const openTagEnd = html.indexOf('>', xShowIdx);
if (openTagEnd === -1) fail('容器開標籤未閉合（找不到 >）');

// div-only 平衡計數求容器閉合位（depth 起 1 = 容器本身這顆 div）
const tagRe = /<div\b|<\/div\s*>/g;
tagRe.lastIndex = openTagEnd + 1;
let depth = 1;
let closeStart = -1;
let m;
while ((m = tagRe.exec(html)) !== null) {
  if (m[0].startsWith('</')) {
    depth -= 1;
    if (depth === 0) {
      closeStart = m.index; // 這顆 </div> 即容器閉合
      break;
    }
  } else {
    depth += 1;
  }
}
if (closeStart === -1) fail('div 計數未歸零——容器閉合位求解失敗（HTML 可能不平衡）');

// 佐證交叉檢查：閉合 </div> 後（允許空白）緊鄰關閉註解
const afterClose = html.slice(closeStart + '</div>'.length);
if (!/^\s*<!-- \/collapsible-content galleryExport -->/.test(afterClose)) {
  fail(
    'div 深度掃描求得的容器閉合位與人工註解 ' +
    `'${CLOSE_COMMENT}' 不緊鄰——兩者漂移，IA 結構疑似已破壞（請人工核對摺疊巢狀）`,
  );
}

// span = (openTagEnd, closeStart)
const inSpan = (idx) => idx > openTagEnd && idx < closeStart;

function idIndex(id) {
  const idx = html.indexOf(`id="${id}"`);
  if (idx === -1) fail(`找不到 id="${id}"（form-id 遺失？對照 test_all_form_ids_preserved）`);
  return idx;
}

// 〔a〕顯示模式 / 輸出目錄 / 輸出檔名在摺疊內（皆離線匯出專用，G-B3/G-B5）
for (const id of MUST_BE_INSIDE) {
  if (!inSpan(idIndex(id))) {
    fail(`id="${id}" 應在離線匯出摺疊內（G-B3/G-B5：顯示模式/輸出目錄/檔名皆離線匯出專用）——實際在摺疊外`);
  }
}

// 〔b〕閘門與雙棲顯示預設在摺疊外
for (const id of MUST_BE_OUTSIDE) {
  if (inSpan(idIndex(id))) {
    fail(`id="${id}" 應在摺疊外（G-B2/G-B4：閘門與 Showcase 雙棲預設留外層）——實際在摺疊內`);
  }
}

console.log('✓ lint-settings-ia: 列表生成兩層 IA 分層正確（顯示模式在摺疊內、閘門/排序/每頁在外）');
