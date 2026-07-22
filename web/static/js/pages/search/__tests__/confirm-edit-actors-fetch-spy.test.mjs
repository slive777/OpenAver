// TASK-106-T3 AC5: confirmEditActors() deferred（無即時 API）
//
// confirmEditActors 是 searchStateResultCard() mixin method（this-bound，讀
// this.current()/this.editedActorsValue，寫 this.editingActors/this.saveState()），
// 用 .call(fakeThis) 呼叫（同 can-edit-file.test.mjs 慣例）。
//
// AC5 硬性要求：confirmEditActors() 全程不得呼叫 fetch（不可照抄
// confirmAddTag/removeUserTag 打 /api/user-tags 那套即時寫）。用 global.fetch
// spy 斷言呼叫數 = 0（同 build-organize-metadata.test.mjs loadMore fetch spy 慣例）。
//
// result-card.js 用瀏覽器 importmap 別名 `@/shared/...`，plain `node --test`
// 需掛 alias-loader resolve hook才能 import 本檔（同 parse-actors-input.test.mjs）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateResultCard } = await import('../state/result-card.js');

test('confirmEditActors: 全程不呼叫 fetch（deferred，AC5），且 current().actors 寫入 parseActorsInput 後的陣列', () => {
  let fetchCalls = 0;
  globalThis.fetch = async () => { fetchCalls++; return { ok: true, json: async () => ({}) }; };

  const candidate = { number: 'ABC-123', actors: [] };
  let savedCalls = 0;

  const fakeThis = {
    ...searchStateResultCard(),
    editedActorsValue: '橋本ありな，蒼井そら',
    editingActors: true,
    current: () => candidate,
    saveState: () => { savedCalls++; },
  };

  searchStateResultCard().confirmEditActors.call(fakeThis);

  assert.equal(fetchCalls, 0, 'confirmEditActors() 不應呼叫任何 fetch（AC5 deferred）');
  assert.deepEqual(candidate.actors, ['橋本ありな', '蒼井そら'], 'current().actors 應寫入 parseActorsInput 解析後的陣列');
  assert.equal(fakeThis.editingActors, false, 'confirm 後應關閉編輯態');
  assert.equal(savedCalls, 1, 'confirmEditActors() 應呼叫一次 saveState()');
});
