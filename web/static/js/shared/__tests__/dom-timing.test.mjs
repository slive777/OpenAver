// waitForMount 五路徑守衛（nexttick-hydrate T2 / CD-3、Codex round-3）。
// 零新依賴：Node 內建 node:test + 假 MutationObserver。跑：npm run test:dom-timing
//
// 守 waitForMount 的 settle 契約：只在 (a) predicate 通過 或 (b) abort 兩種情況 resolve；
// warn timer 逾時**不 settle、不 disconnect**（Codex round-3：終止式放棄與「無論何時
// mount 都 reveal」矛盾）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

// ── 假 MutationObserver：手動 flush 模擬 late mount ────────────────────────
let liveObservers = [];
class FakeMutationObserver {
  constructor(cb) { this.cb = cb; this.connected = false; liveObservers.push(this); }
  observe() { this.connected = true; }
  disconnect() { this.connected = false; }
  // 測試用：模擬一次 DOM mutation
  fire() { if (this.connected) this.cb(); }
}

// ── 假 timer：手動觸發 warn timer，不真的等 4s ───────────────────────────
let scheduledTimers = [];
function fakeSetTimeout(fn) { const id = scheduledTimers.length; scheduledTimers.push(fn); return id; }
function fakeClearTimeout(id) { if (id != null) scheduledTimers[id] = null; }

function withStubs(run) {
  const origMO = globalThis.MutationObserver;
  const origST = globalThis.setTimeout;
  const origCT = globalThis.clearTimeout;
  const origWarn = console.warn;
  let warnCalls = 0;
  liveObservers = [];
  scheduledTimers = [];
  globalThis.MutationObserver = FakeMutationObserver;
  globalThis.setTimeout = fakeSetTimeout;
  globalThis.clearTimeout = fakeClearTimeout;
  console.warn = () => { warnCalls += 1; };
  const fireWarnTimers = () => scheduledTimers.forEach((fn) => fn && fn());
  return Promise.resolve(run({ getWarnCalls: () => warnCalls, fireWarnTimers }))
    .finally(() => {
      globalThis.MutationObserver = origMO;
      globalThis.setTimeout = origST;
      globalThis.clearTimeout = origCT;
      console.warn = origWarn;
    });
}

// import 需在 stub 後，但 ESM import 是 hoisted static；waitForMount 內部用的是
// 「呼叫時」的 globalThis.MutationObserver/setTimeout，故 stub 於呼叫前設好即可。
const { waitForMount } = await import('../dom-timing.js');

const fakeRoot = { nodeType: 1 };  // 非 null 即可（FakeMutationObserver.observe 不讀它）

test('〔1〕already-aborted-signal-at-entry → 立即 resolve aborted，不掛 observer', async () => {
  await withStubs(async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    const res = await waitForMount(fakeRoot, () => false, { signal: ctrl.signal });
    assert.deepEqual(res, { ready: false, aborted: true });
    assert.equal(liveObservers.length, 0, 'entry 已中止不應建 observer');
  });
});

test('〔2〕initial-true → 同步 resolve ready，不掛 observer', async () => {
  await withStubs(async () => {
    const res = await waitForMount(fakeRoot, () => true, {});
    assert.deepEqual(res, { ready: true });
    assert.equal(liveObservers.length, 0, 'predicate 同步命中不應建 observer');
  });
});

test('〔3〕observer-fires-on-late-mount → mutation 後 resolve ready + disconnect', async () => {
  await withStubs(async () => {
    let mounted = false;
    const p = waitForMount(fakeRoot, () => mounted, {});
    assert.equal(liveObservers.length, 1);
    assert.equal(liveObservers[0].connected, true);
    // 尚未就緒：fire 一次 mutation（predicate 仍 false）不 resolve
    liveObservers[0].fire();
    // late mount
    mounted = true;
    liveObservers[0].fire();
    const res = await p;
    assert.deepEqual(res, { ready: true });
    assert.equal(liveObservers[0].connected, false, 'ready 後 observer 應 disconnect');
  });
});

test('〔4〕abort-settles-false → abort 後 resolve aborted + disconnect', async () => {
  await withStubs(async () => {
    const ctrl = new AbortController();
    const p = waitForMount(fakeRoot, () => false, { signal: ctrl.signal });
    assert.equal(liveObservers[0].connected, true);
    ctrl.abort();
    const res = await p;
    assert.deepEqual(res, { ready: false, aborted: true });
    assert.equal(liveObservers[0].connected, false, 'abort 後 observer 應 disconnect');
  });
});

test('〔5〕warn-timer-fires-but-does-NOT-settle → observer 續存活，之後 late mount 仍 reveal', async () => {
  await withStubs(async ({ getWarnCalls, fireWarnTimers }) => {
    let mounted = false;
    let resolved = false;
    const p = waitForMount(fakeRoot, () => mounted, { warnAfterMs: 10 }).then((r) => { resolved = true; return r; });
    // 觸發 warn timer
    fireWarnTimers();
    assert.equal(getWarnCalls(), 1, 'warn timer 應 console.warn 一次');
    assert.equal(resolved, false, 'warn 逾時不得 settle promise');
    assert.equal(liveObservers[0].connected, true, 'warn 逾時不得 disconnect observer');
    // 逾時後才 mount → observer 仍捕捉 → reveal
    mounted = true;
    liveObservers[0].fire();
    const res = await p;
    assert.deepEqual(res, { ready: true });
  });
});

test('〔6〕root=null → 靜默 resolve {ready:false}，不掛 observer', async () => {
  await withStubs(async () => {
    const res = await waitForMount(null, () => false, {});
    assert.deepEqual(res, { ready: false });
    assert.equal(liveObservers.length, 0);
  });
});
