// TASK-205c-T3: extractChineseTitle 前後端共用向量（BE-TEST-14）。
// 向量是取樣，只證明這些類別一致，不證明所有輸入一致。
// file.js 是 classic script（掛到 window.SearchFile），沿用 parse-filenames.test.mjs
// 的 `globalThis.window = globalThis; await import('../file.js')` 手法（FE-GUARD-11）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

globalThis.window = globalThis;
await import('../file.js');
const { extractChineseTitle } = globalThis.window.SearchFile;

// 從 web/static/js/pages/search/__tests__/ 往上六層到 repo 根
const vectors = JSON.parse(readFileSync(
  new URL('../../../../../../tests/data/extract_chinese_title_vectors.json', import.meta.url), 'utf8')).vectors;

test('extractChineseTitle 符合共用向量檔（與 Python extract_chinese_title 同表）', () => {
  assert.ok(vectors.length > 0);
  for (const v of vectors) {
    assert.strictEqual(extractChineseTitle(v.filename, v.number, v.actors), v.expected, JSON.stringify(v.filename));
  }
});
