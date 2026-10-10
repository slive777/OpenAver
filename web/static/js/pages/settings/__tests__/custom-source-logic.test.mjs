// TASK-165-T8: 自訂來源前端純邏輯（狀態→點／文案、失敗句只講第一條）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const {
  customStatusToProbeState, customStatusIcon, customStatusKey,
  mismatchVerbKey, formatVerifiedAt, pickFirstMismatch, describeCustomLine,
} = await import('../custom-source-logic.js');
const { PROBE_ICON_MAP } = await import('../source-probe-logic.js');

const P = 'settings.sources.';

const TWO_CASES = () => ({
  total: 2,
  failed: 2,
  cases: [
    {
      index: 1, number: 'AAA-001', passed: false,
      mismatches: [
        { key: 'title_contains', expected: 'XA', actual: 'YA', url: 'http://a/1' },
        { key: 'tags_max', expected: 3, actual: 5, url: 'http://a/2' },
      ],
    },
    {
      index: 2, number: 'BBB-002', passed: false,
      mismatches: [
        { key: 'status', expected: 'ok', actual: 'not_found', url: 'http://b/1' },
        { key: 'title', expected: 'PC', actual: 'QC', url: 'http://b/2' },
      ],
    },
  ],
});

const recorder = () => {
  const calls = [];
  const t = (k, p) => { calls.push([k, p]); return k; };
  return { calls, t };
};

test('customStatusToProbeState maps the five statuses', () => {
  assert.strictEqual(customStatusToProbeState('passed'), 'ok');
  assert.strictEqual(customStatusToProbeState('failed'), 'blocked');
  assert.strictEqual(customStatusToProbeState('load_failed'), 'unreachable');
  assert.strictEqual(customStatusToProbeState('unverified'), 'skipped');
  assert.strictEqual(customStatusToProbeState('verifying'), null);
  assert.strictEqual(customStatusToProbeState('bogus'), null);
});

test('customStatusIcon takes icons from PROBE_ICON_MAP and null for verifying/unknown', () => {
  assert.strictEqual(customStatusIcon('passed'), PROBE_ICON_MAP.ok);
  assert.strictEqual(customStatusIcon('failed'), PROBE_ICON_MAP.blocked);
  assert.strictEqual(customStatusIcon('load_failed'), PROBE_ICON_MAP.unreachable);
  assert.strictEqual(customStatusIcon('unverified'), PROBE_ICON_MAP.skipped);
  assert.strictEqual(customStatusIcon('verifying'), null);
  assert.strictEqual(customStatusIcon('toString'), null);
  assert.strictEqual(customStatusIcon(undefined), null);
});

test('customStatusKey maps the five statuses to explicit keys', () => {
  assert.equal(customStatusKey('passed'), P + 'custom_status_passed');
  assert.equal(customStatusKey('failed'), P + 'custom_status_failed');
  assert.equal(customStatusKey('load_failed'), P + 'custom_status_load_failed');
  assert.equal(customStatusKey('unverified'), P + 'custom_status_unverified');
  assert.equal(customStatusKey('verifying'), P + 'custom_status_verifying');
});

test('mismatchVerbKey maps the five suffixes to their verb keys', () => {
  assert.equal(mismatchVerbKey('status'), P + 'custom_verb_equal');
  assert.equal(mismatchVerbKey('title_contains'), P + 'custom_verb_contains');
  assert.equal(mismatchVerbKey('tags_include'), P + 'custom_verb_include');
  assert.equal(mismatchVerbKey('tags_exclude'), P + 'custom_verb_exclude');
  assert.equal(mismatchVerbKey('tags_max'), P + 'custom_verb_max');
  assert.equal(mismatchVerbKey('detail_host'), P + 'custom_verb_equal');
  assert.equal(mismatchVerbKey('weird_suffix'), P + 'custom_verb_equal');
  assert.equal(mismatchVerbKey(undefined), P + 'custom_verb_equal');
});

test('formatVerifiedAt renders local MM/DD HH:mm and empty for non-finite', () => {
  assert.equal(formatVerifiedAt(new Date(2026, 9, 10, 14, 32).getTime() / 1000), '10/10 14:32');
  assert.equal(formatVerifiedAt(new Date(2026, 0, 5, 3, 7).getTime() / 1000), '01/05 03:07');
  assert.equal(formatVerifiedAt(null), '');
  assert.equal(formatVerifiedAt(undefined), '');
  assert.equal(formatVerifiedAt(NaN), '');
});

test('pickFirstMismatch takes the first mismatch of the first failed case', () => {
  const r = pickFirstMismatch(TWO_CASES());
  assert.equal(r.index, 1);
  assert.equal(r.number, 'AAA-001');
  assert.equal(r.key, 'title_contains');
  assert.equal(r.expected, 'XA');
  assert.equal(r.actual, 'YA');
  assert.equal(r.url, 'http://a/1');
  assert.equal(r.remaining, 3);
});

test('pickFirstMismatch skips passed cases', () => {
  const lr = TWO_CASES();
  lr.cases[0].passed = true;
  lr.cases[0].mismatches = [];
  const r = pickFirstMismatch(lr);
  assert.equal(r.index, 2);
  assert.equal(r.number, 'BBB-002');
  assert.equal(r.key, 'status');
  assert.equal(r.expected, 'ok');
  assert.equal(r.actual, 'not_found');
  assert.equal(r.remaining, 1);
});

test('pickFirstMismatch returns null without throwing on empty shapes', () => {
  assert.strictEqual(pickFirstMismatch(null), null);
  assert.strictEqual(pickFirstMismatch(undefined), null);
  assert.strictEqual(pickFirstMismatch({}), null);
  assert.strictEqual(pickFirstMismatch({ cases: [] }), null);
  assert.strictEqual(pickFirstMismatch({ cases: [{ index: 1, number: 'X', passed: false, mismatches: [] }] }), null);
});

test('describeCustomLine failed names the first mismatch and appends the remaining count', () => {
  const { calls, t } = recorder();
  const when = new Date(2026, 9, 10, 14, 32).getTime() / 1000;
  const out = describeCustomLine({ status: 'failed', verified_at: when, last_result: TWO_CASES() }, t);
  const keys = calls.map((c) => c[0]);
  assert.equal(keys[0], P + 'custom_verb_contains');
  assert.ok(keys.includes(P + 'custom_line_failed'));
  const line = calls.find((c) => c[0] === P + 'custom_line_failed')[1];
  assert.equal(line.n, 1);
  assert.equal(line.number, 'AAA-001');
  assert.equal(line.key, 'title_contains');
  assert.equal(line.expected, 'XA');
  assert.equal(line.actual, 'YA');
  assert.equal(line.time, '10/10 14:32');
  assert.equal(line.verb, P + 'custom_verb_contains');
  const more = calls.filter((c) => c[0] === P + 'custom_line_more');
  assert.equal(more.length, 1);
  assert.equal(more[0][1].count, 3);
  assert.equal(out, P + 'custom_line_failed' + P + 'custom_line_more');
});

test('describeCustomLine failed omits the more-suffix when remaining is 0', () => {
  const { calls, t } = recorder();
  const lr = { cases: [{ index: 2, number: 'Z-1', passed: false, mismatches: [{ key: 'tags_exclude', expected: ['a', 'b'], actual: null }] }] };
  const out = describeCustomLine({ status: 'failed', verified_at: 1, last_result: lr }, t);
  assert.equal(calls.filter((c) => c[0] === P + 'custom_line_more').length, 0);
  const line = calls.find((c) => c[0] === P + 'custom_line_failed')[1];
  assert.equal(line.n, 2);
  assert.equal(line.expected, 'a、b');
  assert.equal(line.actual, '');
  assert.equal(line.verb, P + 'custom_verb_exclude');
  assert.equal(out, P + 'custom_line_failed');
});

test('describeCustomLine covers bare, passed, load_failed, unverified, verifying, unknown', () => {
  let r = recorder();
  assert.equal(describeCustomLine({ status: 'failed', verified_at: 1, last_result: null }, r.t), P + 'custom_line_failed_bare');
  assert.equal(r.calls[0][0], P + 'custom_line_failed_bare');
  assert.ok('time' in r.calls[0][1]);

  r = recorder();
  assert.equal(describeCustomLine({ status: 'passed', verified_at: 1 }, r.t), P + 'custom_line_passed');
  assert.ok('time' in r.calls[0][1]);

  r = recorder();
  assert.equal(describeCustomLine({ status: 'load_failed', load_error: { message: 'boom' } }, r.t), P + 'custom_line_load_failed');
  assert.equal(r.calls[0][1].reason, 'boom');

  r = recorder();
  assert.doesNotThrow(() => describeCustomLine({ status: 'load_failed', load_error: null }, r.t));
  assert.equal(r.calls[0][1].reason, '');

  r = recorder();
  assert.equal(describeCustomLine({ status: 'unverified' }, r.t), P + 'custom_status_unverified');
  assert.equal(describeCustomLine({ status: 'verifying' }, r.t), P + 'custom_status_verifying');
  assert.equal(describeCustomLine({ status: 'nope' }, r.t), '');
});
