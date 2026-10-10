// TASK-165-T9: 設定頁自訂來源獨立元件（customSources）行為。
// 不經 Alpine：直接呼叫 factory，fetch 用可手動 resolve 的 stub。

import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
window.t = (key) => key;

register(
  new URL('../../search/__tests__/alias-loader.mjs', import.meta.url),
  import.meta.url,
);

const { customSources } = await import('../state-custom-sources.js');

const realFetch = globalThis.fetch;
const live = [];
afterEach(() => {
  globalThis.fetch = realFetch;
  while (live.length) live.pop().destroy();
});

const tick = () => new Promise((r) => setTimeout(r, 0));

function make() {
  const c = customSources();
  live.push(c);
  return c;
}

function entry(id, status, extra = {}) {
  return {
    id, source_id: `custom:${id}`, name: id.toUpperCase(), status,
    enabled: false, verified_at: null, last_result: null, load_error: null, ...extra,
  };
}

function resp(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

// 手動 resolve 的 fetch stub
function deferredFetch() {
  const calls = [];
  globalThis.fetch = (url, init) => new Promise((resolve, reject) => {
    calls.push({ url, init, resolve, reject });
  });
  return calls;
}

// 依 URL 回覆固定內容的 fetch stub
function routedFetch(routes) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const key = `${(init && init.method) || 'GET'} ${url}`;
    const r = routes[key];
    return typeof r === 'function' ? r() : r;
  };
  return calls;
}

test('factory instantiates on an empty host and init issues exactly one GET', async () => {
  const calls = deferredFetch();
  const c = make();
  assert.deepEqual(c.customSrcList, []);
  assert.equal(c.customSrcOpenId, null);
  c.init();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/custom-sources');
  assert.ok(!calls[0].init || !calls[0].init.method || calls[0].init.method === 'GET');
  calls[0].resolve(resp({ success: true, sources: [] }));
  await tick();
  assert.deepEqual(c.customSrcList, []);
  assert.equal(c.customSrcOpenId, null);
  assert.equal(c.customSrcPollTimer, null);
});

test('customSrcRefresh drops a stale response', async () => {
  const calls = deferredFetch();
  const c = make();
  c.customSrcRefresh();
  c.customSrcRefresh();
  assert.equal(calls.length, 2);
  calls[1].resolve(resp({ success: true, sources: [entry('new', 'passed')] }));
  await tick();
  calls[0].resolve(resp({ success: true, sources: [entry('old', 'failed')] }));
  await tick();
  assert.deepEqual(c.customSrcList.map((e) => e.id), ['new']);
});

test('polling starts only while a source is verifying and stops when none is', async () => {
  const bodies = [
    { success: true, sources: [entry('a', 'verifying')] },
    { success: true, sources: [entry('a', 'passed')] },
  ];
  const c = make();
  routedFetch({ 'GET /api/custom-sources': () => resp(bodies.shift()) });
  await c.customSrcRefresh();
  assert.notEqual(c.customSrcPollTimer, null, 'verifying → timer');
  await c.customSrcRefresh();
  assert.equal(c.customSrcPollTimer, null, 'no verifying → timer cleared');

  const c2 = make();
  routedFetch({ 'GET /api/custom-sources': () => resp({ success: true, sources: [entry('a', 'passed'), entry('b', 'unverified')] }) });
  await c2.customSrcRefresh();
  assert.equal(c2.customSrcPollTimer, null, 'never verifying → never a timer');
});

test('destroy clears the poll timer and invalidates in-flight requests', async () => {
  const calls = deferredFetch();
  const c = make();
  c.customSrcRefresh();
  calls[0].resolve(resp({ success: true, sources: [entry('a', 'verifying')] }));
  await tick();
  assert.notEqual(c.customSrcPollTimer, null);
  c.customSrcRefresh(); // 在途
  c.destroy();
  assert.equal(c.customSrcPollTimer, null);
  calls[1].resolve(resp({ success: true, sources: [entry('late', 'passed')] }));
  await tick();
  assert.deepEqual(c.customSrcList.map((e) => e.id), ['a'], 'late response not written');
  assert.equal(c.customSrcPollTimer, null, 'late response does not restart polling');
});

test('toggle on a non-passed source opens the line and sends no request', async () => {
  const calls = routedFetch({});
  const c = make();
  c.customSrcList = [entry('u', 'unverified'), entry('f', 'failed')];
  await c.customSrcToggle('u');
  assert.equal(calls.length, 0);
  assert.equal(c.customSrcOpenId, 'u');
  await c.customSrcToggle('u');
  assert.equal(c.customSrcOpenId, null, 'second click closes');
  await c.customSrcToggle('f');
  assert.equal(c.customSrcOpenId, 'f');
  assert.equal(calls.length, 0);
});

test('toggle on a passed source POSTs the flipped enabled with the bare id, then swaps the list', async () => {
  const c = make();
  c.customSrcList = [entry('p', 'passed', { enabled: false })];
  const calls = routedFetch({
    'POST /api/custom-sources/p/enabled': resp({ success: true }),
    'GET /api/custom-sources': resp({ success: true, sources: [entry('p', 'passed', { enabled: true })] }),
  });
  await c.customSrcToggle('p');
  assert.equal(calls[0].url, '/api/custom-sources/p/enabled');
  assert.deepEqual(JSON.parse(calls[0].init.body), { enabled: true });
  assert.equal(c.customSrcList[0].enabled, true);
  assert.equal(c.customSrcOpenId, null);
});

test('toggle 409 not_passed opens the line with an error', async () => {
  const c = make();
  c.customSrcList = [entry('p', 'passed')];
  routedFetch({
    'POST /api/custom-sources/p/enabled': resp({ success: false, reason: 'not_passed' }, 409),
    'GET /api/custom-sources': resp({ success: true, sources: [entry('p', 'failed')] }),
  });
  await c.customSrcToggle('p');
  assert.equal(c.customSrcOpenId, 'p');
  assert.equal(c.customSrcError, 'settings.sources.custom_error_generic');
});

test('verify is single-flight; 409 verify_busy shows the busy text and clears busy id', async () => {
  const c = make();
  c.customSrcList = [entry('a', 'unverified'), entry('b', 'unverified')];
  const calls = deferredFetch();
  const p = c.customSrcVerify('a');
  assert.equal(c.customSrcBusyId, 'a');
  assert.equal(c.customSrcStatus(c.customSrcList[0]), 'verifying');
  await c.customSrcVerify('b'); // 忽略
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/custom-sources/a/verify');
  assert.equal(calls[0].init.method, 'POST');
  calls[0].resolve(resp({ success: false, reason: 'verify_busy' }, 409));
  await tick();
  assert.equal(c.customSrcBusyId, null);
  assert.equal(calls.length, 2, 'follow-up GET');
  assert.equal(calls[1].url, '/api/custom-sources');
  calls[1].resolve(resp({ success: true, sources: [entry('a', 'unverified'), entry('b', 'unverified')] }));
  await p;
  assert.equal(c.customSrcError, 'settings.sources.custom_error_busy');
  assert.equal(c.customSrcOpenId, 'a', 'line stays open');
  assert.equal(c.customSrcPollTimer, null, 'no extra polling');
});

test('verify success: network failure maps to generic error and still refreshes', async () => {
  const c = make();
  c.customSrcList = [entry('a', 'unverified')];
  const calls = routedFetch({
    'POST /api/custom-sources/a/verify': () => { throw new Error('net'); },
    'GET /api/custom-sources': resp({ success: true, sources: [entry('a', 'unverified')] }),
  });
  await c.customSrcVerify('a');
  assert.equal(c.customSrcError, 'settings.sources.custom_error_generic');
  assert.equal(c.customSrcBusyId, null);
  assert.equal(calls.length, 2);
});

test('verify changed_during_verify maps to the changed text', async () => {
  const c = make();
  c.customSrcList = [entry('a', 'unverified')];
  routedFetch({
    'POST /api/custom-sources/a/verify': resp({ success: false, reason: 'changed_during_verify' }, 409),
    'GET /api/custom-sources': resp({ success: true, sources: [entry('a', 'unverified')] }),
  });
  await c.customSrcVerify('a');
  assert.equal(c.customSrcError, 'settings.sources.custom_error_changed');
});

test('remove: open → confirm sends DELETE with bare id, closes, swaps list', async () => {
  const c = make();
  c.customSrcList = [entry('x', 'failed')];
  c.customSrcOpenId = 'x';
  c.customSrcOpenRemove('x');
  assert.equal(c.customSrcRemoveId, 'x');
  const calls = routedFetch({
    'DELETE /api/custom-sources/x': resp({ success: true }),
    'GET /api/custom-sources': resp({ success: true, sources: [] }),
  });
  await c.customSrcConfirmRemove();
  assert.equal(calls[0].url, '/api/custom-sources/x');
  assert.equal(c.customSrcRemoveId, null);
  assert.equal(c.customSrcOpenId, null);
  assert.deepEqual(c.customSrcList, []);
  c.customSrcOpenRemove('x');
  c.customSrcCloseRemove();
  assert.equal(c.customSrcRemoveId, null);
});

test('zero custom sources: list empty, open id null, line text per status', () => {
  const c = make();
  assert.deepEqual(c.customSrcList, []);
  assert.equal(c.customSrcOpenId, null);
  assert.equal(c.customSrcLine(entry('a', 'unverified')), 'settings.sources.custom_status_unverified');
  assert.equal(c.customSrcProbeState('passed'), 'ok');
  assert.equal(c.customSrcProbeState('verifying'), null);
});

test('verify POST ok then GET fails: entry keeps the POST status, line shows a sync error, no spinner', async () => {
  const c = make();
  c.customSrcList = [entry('a', 'unverified', { enabled: true })];
  const cases = [{ index: 1, number: 'AAA-001', passed: false, mismatches: [] }];
  routedFetch({
    'POST /api/custom-sources/a/verify': resp({ success: true, id: 'a', status: 'failed', verified_at: 1700000000, total: 1, failed: 1, cases }),
    'GET /api/custom-sources': () => { throw new Error('net'); },
  });
  await c.customSrcVerify('a');
  const e = c.customSrcList[0];
  assert.equal(e.status, 'failed');
  assert.equal(e.verified_at, 1700000000);
  assert.deepEqual(e.last_result, { total: 1, failed: 1, cases });
  assert.equal(e.enabled, false);
  assert.equal(c.customSrcOpenId, 'a');
  assert.equal(c.customSrcError, 'settings.sources.custom_error_generic');
  assert.equal(c.customSrcBusyId, null);
  assert.notEqual(c.customSrcStatus(e), 'verifying');
  assert.equal(c.customSrcPollTimer, null);
});

test('verify passed response enabled is adopted by the capsule', async () => {
  const c = make();
  c.customSrcList = [entry('a', 'unverified', { enabled: false })];
  const cases = [{ index: 1, number: 'AAA-001', passed: true, mismatches: [] }];
  routedFetch({
    'POST /api/custom-sources/a/verify': resp({ success: true, id: 'a', status: 'passed', enabled: true, verified_at: 1700000000, total: 1, failed: 0, cases }),
    'GET /api/custom-sources': () => { throw new Error('net'); },
  });
  await c.customSrcVerify('a');
  assert.equal(c.customSrcList[0].status, 'passed');
  assert.equal(c.customSrcList[0].enabled, true);
});

test('toggle POST ok then GET fails: entry shows the POST enabled, line shows a sync error, no spinner', async () => {
  const c = make();
  c.customSrcList = [entry('p', 'passed', { enabled: false })];
  routedFetch({
    'POST /api/custom-sources/p/enabled': resp({ success: true, id: 'p', enabled: true }),
    'GET /api/custom-sources': () => { throw new Error('net'); },
  });
  await c.customSrcToggle('p');
  const e = c.customSrcList[0];
  assert.equal(e.enabled, true);
  assert.equal(c.customSrcOpenId, 'p');
  assert.equal(c.customSrcError, 'settings.sources.custom_error_generic');
  assert.notEqual(c.customSrcStatus(e), 'verifying');
  assert.equal(c.customSrcPollTimer, null);
});

test('remove DELETE ok then GET fails: entry is gone, line shows a sync error, no spinner', async () => {
  const c = make();
  c.customSrcList = [entry('x', 'failed'), entry('y', 'passed')];
  c.customSrcOpenRemove('x');
  routedFetch({
    'DELETE /api/custom-sources/x': resp({ success: true }),
    'GET /api/custom-sources': () => { throw new Error('net'); },
  });
  await c.customSrcConfirmRemove();
  assert.deepEqual(c.customSrcList.map((e) => e.id), ['y']);
  assert.equal(c.customSrcRemoveId, null);
  assert.equal(c.customSrcError, 'settings.sources.custom_error_generic');
  assert.equal(c.customSrcBusyId, null);
  assert.equal(c.customSrcPollTimer, null);
});
