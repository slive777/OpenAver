import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readFileSync } from 'node:fs';

register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);
const { stateBatch, formatAttemptedDate } = await import('../state-batch.js');
const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url), 'utf8'));
const harness = () => {
  globalThis.window = globalThis;
  window.t = (key, params = {}) => {
    const value = key.split('.').reduce((obj, part) => obj?.[part], locale);
    return typeof value === 'string' ? value.replace(/\{(\w+)\}/g, (_, name) => params[name]) : value;
  };
  return Object.defineProperties({}, Object.getOwnPropertyDescriptors(stateBatch()));
};

test('test_attempted_probe_failed_rows_visibility', async () => {
  const state = harness();
  const respond = async (data) => {
    globalThis.fetch = async () => ({ json: async () => ({ success: true, data }) });
    await state.checkMissing();
  };
  await respond({ total_missing: 0, attempted_count: 1, attempted_items: [{ number: 'A' }], probe_failed_count: 0, probe_failed_items: [] });
  assert.equal(state.attemptedPillVisible, true);
  assert.equal(state.probeFailedPillVisible, false);
  assert.equal(state.missingPillVisible, false);
  await respond({ total_missing: 0, attempted_count: 0, attempted_items: [], probe_failed_count: 1, probe_failed_items: [{ number: '' }] });
  assert.equal(state.attemptedPillVisible, false);
  assert.equal(state.probeFailedPillVisible, true);
  await respond({ total_missing: 0 });
  assert.equal(state.attemptedPillVisible, false);
  assert.equal(state.probeFailedPillVisible, false);
  assert.deepEqual(state.attemptedItems, []);
  assert.deepEqual(state.probeFailedItems, []);
});

test('test_attempted_reason_by_category', () => {
  const state = harness();
  const epoch = new Date(2026, 10, 20, 12).getTime() / 1000;
  assert.equal(formatAttemptedDate(epoch), '2026-11-20');
  state.attemptedItems = ['both', 'nfo', 'cover'].map(category => ({ number: 'A', file_path: '/video', category, attempted_at: epoch }));
  const expected = ['試過仍缺 NFO 與封面（2026-11-20）', '試過仍缺 NFO（2026-11-20）', '試過仍缺封面（2026-11-20）'];
  assert.deepEqual(state.attemptedDrilldownItems.map(item => item.reason), expected);
  assert.deepEqual(state.attemptedDrilldownItems.map(item => item.note), expected);
  state.probeFailedItems = [{ number: '', file_path: '/video' }];
  assert.deepEqual(state.probeFailedDrilldownItems, [{ number: '', path: '/video', note: '讀不出影片資訊', reason: '讀不出影片資訊' }]);
});
