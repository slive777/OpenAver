// TASK-200c-T5: parseActorsInput 純函式邊界（已搬至 shared/ 單一擁有者）
//
// parseActorsInput 是 shared/parse-actors-input.js 的 module-level 純函式
// （零依賴、不依賴 this），直接 import 測試，不需 alias-loader、不需 window。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { parseActorsInput } = await import('../../../shared/parse-actors-input.js');


test('parseActorsInput: 三種分隔符混用 "、/,/，" → 4 筆', () => {
  assert.deepEqual(parseActorsInput('A、B,C，D'), ['A', 'B', 'C', 'D']);
});
