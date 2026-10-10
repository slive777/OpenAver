// TASK-163b-T4a: 測試連線純邏輯（世代作廢、設定快照鍵、送出名單、摘要口徑）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const {
  acceptProbeResponse, buildProbeKey, summarizeProbe,
} = await import('../source-probe-logic.js');

const SRC = () => [
  { id: 'dmm', type: 'builtin', enabled: true, manual_only: false },
  { id: 'javbus', type: 'builtin', enabled: false, manual_only: false },
  { id: 'javlibrary', type: 'builtin', enabled: false, manual_only: true },
  { id: 'mt-a', type: 'metatube', enabled: true, manual_only: false },
  { id: 'mt-b', type: 'metatube', enabled: false, manual_only: false },
];

test('acceptProbeResponse accepts only the generation that started the request', () => {
  for (const [start, cur, want] of [[1, 1, true], [1, 2, false], [3, 1, false], [0, 0, true]]) {
    assert.equal(acceptProbeResponse(start, cur), want, `${start} vs ${cur}`);
  }
});

test('buildProbeKey ignores pill order', () => {
  const a = SRC();
  const b = SRC().reverse();
  assert.equal(buildProbeKey('p', 'dmm', a), buildProbeKey('p', 'dmm', b));
});

test('buildProbeKey ignores trailing whitespace in proxy url', () => {
  assert.equal(buildProbeKey('http://x ', 'dmm', SRC()), buildProbeKey('http://x', 'dmm', SRC()));
});

test('buildProbeKey reacts to metatube and manual_only toggles', () => {
  const base = buildProbeKey('p', 'dmm', SRC());
  for (const id of ['dmm', 'javbus', 'javlibrary', 'mt-a', 'mt-b']) {
    const s = SRC();
    const t = s.find((x) => x.id === id);
    t.enabled = !t.enabled;
    assert.notEqual(buildProbeKey('p', 'dmm', s), base, `toggle ${id}`);
  }
});

test('summarizeProbe excludes skipped from the denominator', () => {
  const r = {
    a: { state: 'ok' }, b: { state: 'ok' }, c: { state: 'blocked' },
    d: { state: 'unreachable' }, e: { state: 'skipped' }, f: { state: 'skipped' },
  };
  assert.deepEqual(summarizeProbe(r), { ok: 2, total: 4 });
});

test('summarizeProbe returns total 0 for empty or all-skipped results', () => {
  assert.equal(summarizeProbe({}).total, 0);
  assert.equal(summarizeProbe({ a: { state: 'skipped' } }).total, 0);
});
