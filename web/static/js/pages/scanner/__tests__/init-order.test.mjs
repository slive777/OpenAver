// Tier 1 結構回歸鎖（nexttick-hydrate T1/T5、CD-2/CD-6）。
// 零新依賴：Node 內建 node:test。跑：npm run test:scanner-order（或 npm test）
//
// 守 state-scan.js init() 的「__registerPage 註冊必須在第一個 await 之前」時序契約——
// 若退回把 lifecycle 註冊放到 await/$nextTick 之後（冷載 tick 不 fire → 離頁 dirty-guard /
// cleanup 永不註冊，SCAN HIGH #1），本測試 RED。
//
// 依 gotchas-frontend「字串存在性 ≠ contract」：先 brace-match 抽出 init() body 再斷言
// 兩者在 body 內的相對位置，而非全檔 grep 字串。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../state-scan.js', import.meta.url), 'utf8');

// 移除 // 行註解與 /* */ 塊註解（防「await」等關鍵字出現在中文註解裡造成偽命中）。
// init() 內無正則字面 / 含 // 的字串，簡易剝除即足。
function stripComments(code) {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '');
}

// 抽 init() body：從 `async init() {` 的 `{` 起，brace-match 到對應 `}`，再剝註解。
function extractInitBody(code) {
  const sig = code.indexOf('async init()');
  assert.ok(sig >= 0, 'state-scan.js 應有 async init()');
  const open = code.indexOf('{', sig);
  assert.ok(open >= 0, 'init() 應有 {');
  let depth = 0;
  for (let i = open; i < code.length; i++) {
    const ch = code[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return stripComments(code.slice(open + 1, i));
    }
  }
  throw new Error('init() 大括號未閉合（brace-match 失敗）');
}

test('__registerPage 註冊在 init() 第一個 await 之前（Tier 1 時序鎖）', () => {
  const body = extractInitBody(src);

  const regIdx = body.indexOf('window.__registerPage');
  assert.ok(regIdx >= 0, 'init() 內應呼叫 window.__registerPage');

  const awaitIdx = body.search(/\bawait\b/);
  assert.ok(awaitIdx >= 0, 'init() 內應至少有一個 await（loadConfig）');

  assert.ok(
    regIdx < awaitIdx,
    'window.__registerPage 必須在 init() 第一個 await 之前註冊；'
    + '否則冷載 tick/loadConfig 卡住時離頁 dirty-guard / cleanup 永不註冊（SCAN HIGH #1 回歸）。',
  );
});

test('init() 內不得殘留 await this.$nextTick()（多餘 tick 已移除）', () => {
  const body = extractInitBody(src);
  assert.ok(
    !/await\s+this\.\$nextTick\s*\(/.test(body),
    'init() 不應有 await this.$nextTick()（logOutput 為靜態元素，restoreLogs 直接同步還原）。',
  );
});
