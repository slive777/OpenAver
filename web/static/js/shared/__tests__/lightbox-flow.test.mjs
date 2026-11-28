import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
const { openLightboxFlow, settleLightboxRoot } = await import('../lightbox-flow.js');

function setup() {
  const events = [], ticks = [], timers = [];
  let opacity = '';
  const classes = new Set();
  const root = {
    style: {
      get opacity() { return opacity; },
      set opacity(value) { events.push(`opacity:${value}`); opacity = value; },
      removeProperty() { events.push('clear'); opacity = ''; }
    },
    classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value) }
  };
  const host = { open: false, gen: 0, busy: false, $nextTick: fn => ticks.push(fn) };
  const spec = { root, openKey: 'open', genKey: 'gen', busyKey: 'busy', animations: 'SearchAnimations' };
  globalThis.setTimeout = (fn, delay) => { assert.equal(delay, 800); timers.push(fn); return timers.length; };
  globalThis.clearTimeout = () => {};
  globalThis.gsap = { getById: id => { events.push(`get:${id}`); return null; } };
  globalThis.GhostFly = { playGridToLightbox: () => null };
  globalThis.SearchAnimations = { playLightboxOpen: () => ({}) };
  delete globalThis.OpenAver;
  return { root, host, spec, events, ticks, timers };
}
const realSetTimeout = globalThis.setTimeout, realClearTimeout = globalThis.clearTimeout;
function cleanup() { globalThis.setTimeout = realSetTimeout; globalThis.clearTimeout = realClearTimeout; }

test('openLightboxFlow hides the lightbox in the same tick it opens', () => {
  try {
    const s = setup();
    openLightboxFlow(s.host, s.spec);
    assert.equal(s.root.style.opacity, '0');
    assert.equal(s.host.open, true);
    assert.equal(s.root.classList.contains('gsap-animating'), true);
    for (const [animations, id] of [['ShowcaseAnimations', 'showcaseLightboxOpen'], ['SearchAnimations', 'lightboxOpen']]) {
      s.spec.animations = animations;
      globalThis.gsap.getById = key => ({ kill() { s.events.push(`kill:${key}`); settleLightboxRoot(s.root); } });
      s.events.length = 0;
      openLightboxFlow(s.host, s.spec);
      const killIndex = s.events.indexOf(`kill:${id}`);
      assert.ok(killIndex >= 0);
      assert.ok(killIndex < s.events.indexOf('opacity:0'));
      assert.equal(s.root.style.opacity, '0');
      assert.equal(s.root.classList.contains('gsap-animating'), true);
    }
  } finally { cleanup(); }
});

test('openLightboxFlow settles the root when the open animation does not take over', () => {
  try {
    for (const scenario of ['stale', 'closed', 'noGhost', 'noGsap', 'reduced', 'null', 'throw', 'timeout']) {
      const s = setup();
      let calls = 0;
      globalThis.SearchAnimations.playLightboxOpen = () => { calls++; if (scenario === 'throw') throw new Error('test error'); return scenario === 'null' || scenario === 'reduced' ? null : {}; };
      if (scenario === 'noGhost') delete globalThis.GhostFly;
      if (scenario === 'noGsap') delete globalThis.gsap;
      if (scenario === 'reduced') globalThis.OpenAver = { prefersReducedMotion: true };
      openLightboxFlow(s.host, s.spec);
      s.host.busy = true;
      if (scenario === 'stale') s.host.gen++;
      if (scenario === 'closed') s.host.open = false;
      const oldError = console.error;
      if (scenario === 'throw') console.error = () => {};
      try { (scenario === 'timeout' ? s.timers : s.ticks)[0](); } finally { console.error = oldError; }
      assert.equal(s.root.style.opacity, '', scenario);
      assert.equal(s.root.classList.contains('gsap-animating'), false, scenario);
      assert.equal(s.host.busy, false, scenario);
      if (scenario === 'closed') assert.equal(calls, 0);
    }
    const s = setup();
    let calls = 0;
    globalThis.SearchAnimations.playLightboxOpen = () => { calls++; return {}; };
    openLightboxFlow(s.host, s.spec); s.ticks[0]();
    assert.equal(calls, 1);
    const missing = setup(); missing.spec.root = null; delete missing.host.$nextTick;
    openLightboxFlow(missing.host, missing.spec);
    assert.equal(missing.host.open, true);
    const bookmark = setup(); bookmark.spec.busyKey = null;
    Object.defineProperty(bookmark.host, 'busy', { get() { throw new Error('busy read'); }, set() { throw new Error('busy write'); } });
    openLightboxFlow(bookmark.host, bookmark.spec); bookmark.ticks[0]();
  } finally { cleanup(); }
});

test('openLightboxFlow falls back to the full open animation when the ghost cannot be built', () => {
  try {
    const s = setup(); s.spec.fromRect = {};
    let options;
    globalThis.GhostFly.playGridToLightbox = (rect, root, opts) => { opts.onComplete(); return null; };
    globalThis.SearchAnimations.playLightboxOpen = (root, opts) => { options = opts; return {}; };
    openLightboxFlow(s.host, s.spec); s.ticks[0]();
    assert.equal('skipCover' in options, false);
    assert.equal(s.host.busy, true);
    options.onComplete(); assert.equal(s.host.busy, false);
    const g = setup(); g.spec.fromRect = {};
    let ghostDone;
    globalThis.GhostFly.playGridToLightbox = (rect, root, opts) => { ghostDone = opts.onComplete; return {}; };
    globalThis.SearchAnimations.playLightboxOpen = (root, opts) => { assert.equal(opts.skipCover, true); return null; };
    openLightboxFlow(g.host, g.spec); g.ticks[0]();
    assert.equal(g.root.style.opacity, ''); assert.equal(g.host.busy, true);
    ghostDone(); assert.equal(g.host.busy, false);
  } finally { cleanup(); }
});


const { armCloseTeardown, cancelCloseTeardown } = await import('../lightbox-flow.js');

function closeHarness() {
  const listeners = new Set(), timers = new Map();
  let now = 0, id = 0;
  const root = {
    addEventListener(type, fn) { if (type === 'transitionend') listeners.add(fn); },
    removeEventListener(type, fn) { if (type === 'transitionend') listeners.delete(fn); },
    dispatch(event) { for (const fn of [...listeners]) fn(event); },
    listenerCount(type) { return type === 'transitionend' ? listeners.size : 0; }
  };
  globalThis.setTimeout = (fn, delay) => { const key = ++id; timers.set(key, { fn, at: now + delay }); return key; };
  globalThis.clearTimeout = key => timers.delete(key);
  return { root, advance(ms) {
    now += ms;
    for (const [key, timer] of timers) if (timer.at <= now) { timers.delete(key); timer.fn(); }
  } };
}

test('armCloseTeardown does not tear the content down before the root opacity fade ends', () => {
  try {
    const { root, advance } = closeHarness(); let calls = 0;
    armCloseTeardown(root, () => calls++);
    advance(249); assert.equal(calls, 0);
    advance(1); assert.equal(calls, 0);
    root.dispatch({ target: {}, propertyName: 'opacity' });
    root.dispatch({ target: root, propertyName: 'transform' });
    root.dispatch({ target: root, propertyName: 'visibility' });
    assert.equal(calls, 0);
    root.dispatch({ target: root, propertyName: 'opacity' }); assert.equal(calls, 1);
    root.dispatch({ target: root, propertyName: 'opacity' }); advance(550); assert.equal(calls, 1);
  } finally { globalThis.setTimeout = realSetTimeout; globalThis.clearTimeout = realClearTimeout; }
});

test('armCloseTeardown still tears the content down when the fade event never arrives', () => {
  try {
    const { root, advance } = closeHarness(); let calls = 0, nullCalls = 0;
    assert.notEqual(armCloseTeardown(root, () => calls++), undefined);
    assert.notEqual(armCloseTeardown(null, () => nullCalls++), undefined);
    advance(799); assert.equal(calls, 0); assert.equal(nullCalls, 0);
    advance(1); assert.equal(calls, 1); assert.equal(nullCalls, 1);
    advance(800); assert.equal(calls, 1); assert.equal(nullCalls, 1);
  } finally { globalThis.setTimeout = realSetTimeout; globalThis.clearTimeout = realClearTimeout; }
});

test('armCloseTeardown is cancelled by cancelCloseTeardown and replaced by a later arm', () => {
  try {
    const { root, advance } = closeHarness(); let old = 0, replaced = 0, latest = 0;
    armCloseTeardown(root, () => old++); cancelCloseTeardown(root);
    assert.equal(root.listenerCount('transitionend'), 0);
    root.dispatch({ target: root, propertyName: 'opacity' }); advance(800); assert.equal(old, 0);
    armCloseTeardown(root, () => replaced++); armCloseTeardown(root, () => latest++);
    assert.equal(root.listenerCount('transitionend'), 1);
    root.dispatch({ target: root, propertyName: 'opacity' }); advance(800);
    assert.equal(replaced, 0); assert.equal(latest, 1);
  } finally { globalThis.setTimeout = realSetTimeout; globalThis.clearTimeout = realClearTimeout; }
});
