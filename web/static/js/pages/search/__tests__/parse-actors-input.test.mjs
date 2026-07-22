// TASK-106-T3 CD-106-3/CD-106-8: parseActorsInput 純函式邊界
//
// parseActorsInput 是 result-card.js 的 module-level 純函式（不依賴 this），
// 直接 import 測試，不需 .call(fakeThis)（同 build-organize-metadata.test.mjs 慣例）。
//
// result-card.js 用瀏覽器 importmap 別名 `@/shared/...`（見
// web/templates/base.html:697 `"@/shared/": "/static/js/shared/"`）匯入
// openLocal，plain `node --test` 不認得這個別名，需掛 alias-loader resolve
// hook（同 build-organize-metadata.test.mjs 慣例）才能 import 本檔。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { parseActorsInput } = await import('../state/result-card.js');

test('parseActorsInput: 全形逗號 "，"（U+FF0C）→ 2 筆（非漏抓成 1 筆）', () => {
  assert.deepEqual(parseActorsInput('橋本ありな，蒼井そら'), ['橋本ありな', '蒼井そら']);
});

test('parseActorsInput: 三種分隔符混用 "、/,/，" → 4 筆', () => {
  assert.deepEqual(parseActorsInput('A、B,C，D'), ['A', 'B', 'C', 'D']);
});

test('parseActorsInput: 前後/中間空白逐片段 trim', () => {
  assert.deepEqual(parseActorsInput(' A , B '), ['A', 'B']);
});

test('parseActorsInput: 空字串 → []', () => {
  assert.deepEqual(parseActorsInput(''), []);
});

test('parseActorsInput: 全空白 → []', () => {
  assert.deepEqual(parseActorsInput('   '), []);
});

test('parseActorsInput: 尾隨分隔符 "A、" → ["A"]（尾端空片段被過濾）', () => {
  assert.deepEqual(parseActorsInput('A、'), ['A']);
});

test('parseActorsInput: 括號不觸發拆分（CD-106-3 不做括號偵測）', () => {
  assert.deepEqual(parseActorsInput('橋本ありな (新ありな)'), ['橋本ありな (新ありな)']);
});
