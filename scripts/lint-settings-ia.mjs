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
 * 190a-T3 擴充（設定頁改分頁後）：
 *   - 〔b〕再鎖 videoExtensions／data-focal-auto-pill／thumbnailCacheEnabled 在摺疊外
 *     （被收進預設收合的離線匯出，使用者就找不到影片副檔名／封面自動對焦／縮圖快取的開關）
 *   - 歸屬：控件必須在對的分頁卡（`data-settings-panel`），掉到別張卡，使用者在該分頁找不到
 *   - 組內序：命名預覽須在命名格式之前（改命名時要看得到即時結果）、瀏覽顯示各組順序
 *   所有新規則靠 ANCHOR 表（每個錨點在檔內必須恰命中 1 次，否則規則自己紅，不靜默取第一個）。
 *   檢查順序固定：〔c〕結構 → 〔a〕 → 〔b〕 → 歸屬 → 序（fail-fast，每次只印一條 ✗）。
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
// 190a-T3：新增的摺疊外控件（走 ANCHOR）
const MUST_BE_OUTSIDE_ANCHORED = ['videoExtensions', 'data-focal-auto-pill', 'thumbnailCacheEnabled'];

// 錨點表：一 key 一行；regex 帶前導邊界（FE-GUARD-36），檔內必須恰命中 1 次
const ANCHOR = {
  proxyUrl: /(?<![\w:-])x-model="form\.proxyUrl"/g,
  searchFavoriteFolder: /(?<![\w:-])id="searchFavoriteFolder"/g,
  createFolder: /(?<![\w:-])id="createFolder"/g,
  maxTitleLength: /(?<![\w:-])id="maxTitleLength"/g,
  maxFilenameLength: /(?<![\w:-])id="maxFilenameLength"/g,
  avlistSort: /(?<![\w:-])id="avlistSort"/g,
  avlistOrder: /(?<![\w:-])id="avlistOrder"/g,
  avlistItemsPerPage: /(?<![\w:-])id="avlistItemsPerPage"/g,
  avlistMinSize: /(?<![\w:-])id="avlistMinSize"/g,
  videoExtensions: /(?<![\w:-])id="videoExtensions"/g,
  avlistMode: /(?<![\w:-])id="avlistMode"/g,
  avlistOutputDir: /(?<![\w:-])id="avlistOutputDir"/g,
  avlistOutputFilename: /(?<![\w:-])id="avlistOutputFilename"/g,
  defaultPage: /(?<![\w:-])id="defaultPage"/g,
  viewerPlayer: /(?<![\w:-])id="viewerPlayer"/g,
  downloadSampleImages: /(?<![\w:-])x-model="form\.downloadSampleImages"/g,
  thumbnailCacheEnabled: /(?<![\w:-])x-model="form\.thumbnailCacheEnabled"/g,
  coverBadgesEnabled: /(?<![\w:-])x-model="form\.coverBadgesEnabled"/g,
  filenameFormat: /(?<![\w:-])x-init="mountFilenameEditor\(\$el\)"/g,
  'data-focal-auto-pill': /(?<![\w:-])data-focal-auto-pill(?![\w-])/g,
  namingPreview: /(?<![\w:-])x-text="folderPreviewText"/g,
  externalManager: /(?<![\w:-])settings-form-row--external-manager/g,
};

// 分頁歸屬表：分頁卡 → 其內必有的控件
const PANEL_OWNS = {
  sources: ['proxyUrl'],
  scraping: ['searchFavoriteFolder', 'createFolder', 'downloadSampleImages', 'filenameFormat', 'maxTitleLength', 'maxFilenameLength'],
  gallery: [
    'avlistSort', 'avlistOrder', 'avlistItemsPerPage', 'avlistMinSize', 'videoExtensions',
    'thumbnailCacheEnabled', 'data-focal-auto-pill', 'avlistMode', 'avlistOutputDir', 'avlistOutputFilename',
  ],
  system: ['defaultPage', 'viewerPlayer'],
};
const PANEL_NAMES = ['sources', 'scraping', 'gallery', 'ai', 'system'];

// 組內序（indexOf 嚴格遞增）；'@galleryExport' = 離線匯出摺疊容器開標籤
const ORDER_GROUPS = [
  ['externalManager', 'searchFavoriteFolder', 'createFolder', 'namingPreview', 'filenameFormat'],
  ['avlistSort', 'coverBadgesEnabled', 'thumbnailCacheEnabled', 'data-focal-auto-pill', 'avlistMinSize', 'videoExtensions', '@galleryExport'],
];

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

// 〔b〕續：190a-T3 新增三項（走 ANCHOR）也在摺疊外
function anchorIdx(key) {
  const ms = [...html.matchAll(ANCHOR[key])];
  if (ms.length !== 1) {
    fail(`[ia-anchor] ${key} 命中 ${ms.length} 次（錨點必須恰 1 次；模板改了或錨點撞名，請對照 CD-190a-6）`);
  }
  return ms[0].index;
}
for (const key of MUST_BE_OUTSIDE_ANCHORED) {
  if (inSpan(anchorIdx(key))) {
    fail(`[ia-outside] ${key} 應在離線匯出摺疊外——實際被收進預設收合的區塊，使用者會找不到這個設定`);
  }
}

// 歸屬：求五張分頁卡 span（自 data-settings-panel 往回找最近 <div，div 平衡計數至閉合）
const panelSpan = {};
for (const name of PANEL_NAMES) {
  const attr = `data-settings-panel="${name}"`;
  const n = countOccurrences(html, attr);
  if (n !== 1) fail(`[ia-panel] ${name} 的 '${attr}' 預期恰 1 個，實得 ${n}`);
  const at = html.indexOf(attr);
  const start = html.lastIndexOf('<div', at);
  if (start === -1 || html.slice(start, at).includes('>')) fail(`[ia-panel] ${name} 的屬性不在 <div> 開標籤內`);
  const re = /<div\b|<\/div\s*>/g;
  re.lastIndex = start + 1;
  let d = 1;
  let end = -1;
  let mm;
  while ((mm = re.exec(html)) !== null) {
    if (mm[0].startsWith('</')) {
      d -= 1;
      if (d === 0) { end = mm.index; break; }
    } else {
      d += 1;
    }
  }
  if (end === -1) fail(`[ia-panel] ${name} 的 div 計數未歸零（HTML 可能不平衡）`);
  panelSpan[name] = [start, end];
}
for (let i = 0; i < PANEL_NAMES.length; i += 1) {
  for (let j = i + 1; j < PANEL_NAMES.length; j += 1) {
    const [a1, b1] = panelSpan[PANEL_NAMES[i]];
    const [a2, b2] = panelSpan[PANEL_NAMES[j]];
    if (a1 < b2 && a2 < b1) fail(`[ia-panel] ${PANEL_NAMES[i]} 與 ${PANEL_NAMES[j]} 兩張分頁卡範圍重疊（巢狀或不平衡）`);
  }
}
const panelOf = (idx) => PANEL_NAMES.find((n) => idx > panelSpan[n][0] && idx < panelSpan[n][1]) || null;

let ownedCount = 0;
for (const [panel, keys] of Object.entries(PANEL_OWNS)) {
  for (const key of keys) {
    const got = panelOf(anchorIdx(key));
    if (got !== panel) {
      const hint = (key === 'videoExtensions' || key === 'data-focal-auto-pill') && got === 'scraping'
        ? '（它屬於「瀏覽顯示」，掉進「整理與命名」使用者會找不到）' : '';
      fail(`[ia-panel] ${key} 應在 '${panel}' 分頁卡內——實際在 '${got}'${hint}`);
    }
    ownedCount += 1;
  }
}

// 組內序
for (const group of ORDER_GROUPS) {
  const pos = group.map((k) => (k === '@galleryExport' ? xShowIdx : anchorIdx(k)));
  for (let i = 1; i < group.length; i += 1) {
    if (pos[i - 1] >= pos[i]) {
      fail(`[ia-order] ${group[i - 1]} 應在 ${group[i]} 之前（組內順序已破壞）`);
    }
  }
}

console.log(
  `✓ lint-settings-ia: 〔a〕${MUST_BE_INSIDE.length} 內、〔b〕${MUST_BE_OUTSIDE.length}＋${MUST_BE_OUTSIDE_ANCHORED.length} 外、` +
  `〔c〕2 結構、歸屬 ${ownedCount} 項、序 ${ORDER_GROUPS.length} 組`,
);
