// TASK-163b-T4b: 狀態點／原因句的檢視純函式與分片方法（fake this 用 mergeState 建，getter 才會活）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
window.t = (k, p) => k + (p ? JSON.stringify(p) : '');

register(
  new URL('../../search/__tests__/alias-loader.mjs', import.meta.url),
  import.meta.url,
);

const logic = await import('../source-probe-logic.js');
const { describeProbe, PROBE_ICON_MAP, ADVICE_KEY_MAP, STATE_KEY_MAP, REASON_KEY_MAP, REASON_KEY_GENERIC } = logic;
const { stateSourceProbe } = await import('../state-source-probe.js');
const { mergeState } = await import('@/shared/merge-state.js');

const STATES = ['ok', 'blocked', 'unreachable', 'skipped'];
const EXPECTED_ICON = {
  ok: 'bi-check-circle-fill',
  blocked: 'bi-exclamation-triangle-fill',
  unreachable: 'bi-x-octagon-fill',
  skipped: 'bi-dash-circle',
};

test('describeProbe gives each state a distinct icon', () => {
  const icons = STATES.map((s) => describeProbe({ state: s, reason: 'ok' }).icon);
  assert.deepEqual(icons, STATES.map((s) => EXPECTED_ICON[s]));
  assert.equal(new Set(icons).size, 4);
  for (const s of STATES) {
    assert.equal(describeProbe({ state: s, reason: 'ok' }).stateKey, STATE_KEY_MAP[s]);
  }
  assert.deepEqual(PROBE_ICON_MAP, EXPECTED_ICON);
});

test('describeProbe maps known reason codes', () => {
  assert.equal(describeProbe({ state: 'blocked', reason: 'cf_challenge' }).reasonKey, REASON_KEY_MAP.cf_challenge);
});

test('describeProbe falls back to the generic reason for unknown codes', () => {
  for (const reason of ['brand_new_code', undefined, '']) {
    assert.equal(describeProbe({ state: 'unreachable', reason }).reasonKey, REASON_KEY_GENERIC);
  }
});

test('describeProbe carries the advice key', () => {
  assert.equal(describeProbe({ state: 'blocked', reason: 'http_status', advice: 'jp_ip' }).adviceKey, ADVICE_KEY_MAP.jp_ip);
  assert.equal(ADVICE_KEY_MAP.jp_ip, 'settings.sources.probe_advice_jp_ip');
  assert.equal(describeProbe({ state: 'blocked', reason: 'http_status' }).adviceKey, null);
  assert.equal(describeProbe({ state: 'blocked', reason: 'http_status', advice: 'nope' }).adviceKey, null);
});

test('describeProbe returns null for unknown states without throwing', () => {
  for (const r of [{ state: 'weird' }, {}, null, undefined, { state: 'toString' }]) {
    assert.equal(describeProbe(r), null);
  }
});

function makeFake(results = {}) {
  const form = { proxyUrl: 'http://p:1', proxyScope: 'dmm' };
  const sources = [
    { id: 'dmm', display_name: 'DMM', enabled: true },
    { id: 'javlibrary', display_name: 'JavLibrary', enabled: false, manual_only: true },
  ];
  const fake = mergeState({ form, sources, showToast() {} }, stateSourceProbe());
  fake.srcProbeResults = results;
  return { fake, form, sources };
}

test('srcProbeLine and srcProbeIcon compose the view for one pill', () => {
  const { fake } = makeFake({
    dmm: { state: 'blocked', reason: 'http_status', advice: 'jp_ip' },
    javlibrary: { state: 'skipped', reason: 'windows_verifier' },
  });
  assert.equal(fake.srcProbeLine('nobody'), '');
  assert.equal(fake.srcProbeIcon('nobody'), '');
  const line = fake.srcProbeLine('dmm');
  assert.ok(line.includes('settings.sources.probe_state_blocked'));
  assert.ok(line.includes('settings.sources.probe_reason_http_status'));
  assert.ok(line.includes('settings.sources.probe_advice_jp_ip'));
  const skipLine = fake.srcProbeLine('javlibrary');
  assert.ok(!skipLine.includes('probe_advice'));
  assert.equal(fake.srcProbeIcon('dmm'), 'bi ' + EXPECTED_ICON.blocked);
  assert.notEqual(fake.srcProbeIcon('javlibrary'), 'bi ' + EXPECTED_ICON.unreachable);
  assert.equal(fake.srcProbeIcon('javlibrary'), 'bi ' + EXPECTED_ICON.skipped);
});

test('toggleSrcProbeTip opens, switches, and closes the tip', () => {
  const { fake } = makeFake({ dmm: { state: 'ok', reason: 'ok' } });
  fake.toggleSrcProbeTip('dmm');
  assert.equal(fake.srcProbeTipId, 'dmm');
  fake.toggleSrcProbeTip('javlibrary');
  assert.equal(fake.srcProbeTipId, 'javlibrary');
  fake.toggleSrcProbeTip('javlibrary');
  assert.equal(fake.srcProbeTipId, null);
});

test('srcProbeTipText is empty without a target and carries the source name otherwise', () => {
  const { fake, form, sources } = makeFake({
    dmm: { state: 'blocked', reason: 'http_status', advice: 'jp_ip' },
  });
  const formBefore = JSON.stringify(form);
  const sourcesBefore = JSON.stringify(sources);
  const resultsRef = fake.srcProbeResults;
  const gen = fake.srcProbeGen;

  assert.equal(fake.srcProbeTipText, '');
  fake.toggleSrcProbeTip('javlibrary');
  assert.equal(fake.srcProbeTipText, '');
  fake.toggleSrcProbeTip('dmm');
  assert.ok(fake.srcProbeTipText.includes('DMM'));
  assert.ok(fake.srcProbeTipText.includes('settings.sources.probe_reason_http_status'));

  fake.clearSrcProbe();
  assert.equal(fake.srcProbeTipText, '');

  assert.equal(JSON.stringify(form), formBefore);
  assert.equal(JSON.stringify(sources), sourcesBefore);
  assert.equal(fake.srcProbeGen, gen + 1);
  assert.notEqual(fake.srcProbeResults, resultsRef);
});

test('view methods never write results or generation', () => {
  const { fake } = makeFake({ dmm: { state: 'ok', reason: 'ok' } });
  const resultsRef = fake.srcProbeResults;
  fake.srcProbeLine('dmm'); fake.srcProbeIcon('dmm'); fake.toggleSrcProbeTip('dmm'); void fake.srcProbeTipText;
  assert.equal(fake.srcProbeResults, resultsRef);
  assert.equal(fake.srcProbeGen, 0);
});

test('srcProbeLine names the host only for blocked or unreachable results', () => {
  const { fake } = makeFake({
    dmm: { state: 'blocked', reason: 'http_status', host: 'caribbeancom.com' },
    javlibrary: { state: 'ok', reason: 'ok', host: 'javlibrary.com' },
  });
  fake.srcProbeResults = {
    ...fake.srcProbeResults,
    a: { state: 'unreachable', reason: 'timeout', host: 'h2.example', advice: 'jp_ip' },
    b: { state: 'skipped', reason: 'self_hosted', host: 'x.example' },
    c: { state: 'blocked', reason: 'http_status' },
    d: { state: 'blocked', reason: 'http_status', host: '' },
  };
  assert.ok(fake.srcProbeLine('dmm').includes('caribbeancom.com'));
  assert.ok(fake.srcProbeLine('a').includes('h2.example'));
  assert.ok(fake.srcProbeLine('a').includes('probe_advice_jp_ip'));
  assert.ok(!fake.srcProbeLine('javlibrary').includes('javlibrary.com'));
  assert.ok(!fake.srcProbeLine('b').includes('x.example'));
  for (const id of ['c', 'd']) {
    const line = fake.srcProbeLine(id);
    assert.ok(!line.includes('undefined') && !line.includes('null') && !line.includes('host'));
  }
});
