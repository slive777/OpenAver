// wheel-nav.test.mjs — createWheelNav/isHorizontalWheel 純邏輯守衛（TASK-102d-T1）。
// 零新依賴：Node 內建 node:test + node:assert/strict + 假 delta 序列（非真 DOM，比照
// focal-cell.test.mjs 的假物件手法）。時間用可注入 now() 驅動，不需要真 sleep。
//
// 守的是：
//   (a) 單次大 delta（|dx|>threshold）→ 觸發一次
//   (b) 連發 20 小 delta（同方向、事件間隔 <cooldownMs）→ 只觸發一次（冷卻窗生效）
//   (c) 方向反轉 → 立即解鎖（不等冷卻窗跑完即可再觸發，方向相反）
//   (d) |deltaX| <= |deltaY| → 不觸發（垂直捲動 / 45 度邊界不誤判）
//   (e) deltaMode=LINE（1）→ 正規化到與 PIXEL 同量級後才判門檻
//   (f) 停頓 ≥ cooldownMs（無新事件）後 → 可再觸發
//   (g) 左右對稱：dx<0 → onLeft；dx>0 → onRight
//
// 跑：npm test（glob 涵蓋本檔，package.json:13）。
//
// mutation 抓點：拿掉冷卻窗判斷（(t < cooldownUntil) return false）→ (b) 必 RED（會觸發 20 次）；
// 拿掉方向反轉重置 → (c) 必 RED；拿掉 isHorizontalWheel 判斷 → (d) 必 RED；
// 拿掉 deltaMode 正規化 → (e) 必 RED（LINE delta 遠小於門檻，不會觸發）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isHorizontalWheel, isVerticalWheel, createWheelNav } from '../wheel-nav.js';

// ── 假時鐘：手動推進，呼叫端完全掌控時間流逝（不需真 sleep）───────────────
function makeClock(startAt = 0) {
  let t = startAt;
  return {
    now: () => t,
    advance(ms) { t += ms; return t; },
  };
}

function makeSpyCallbacks() {
  const calls = [];
  return {
    calls,
    onLeft: () => calls.push('left'),
    onRight: () => calls.push('right'),
  };
}

// 102d P2b：垂直軸版 spy（onUp/onDown），供 axis:'vertical' 案例使用。
function makeVerticalSpyCallbacks() {
  const calls = [];
  return {
    calls,
    onUp: () => calls.push('up'),
    onDown: () => calls.push('down'),
  };
}

// ── isHorizontalWheel：純數值方向主導判斷 ──────────────────────────────────

test('isHorizontalWheel〔|dx|>|dy|〕橫向為主 → true', () => {
  assert.equal(isHorizontalWheel(120, 10), true);
  assert.equal(isHorizontalWheel(-120, 10), true);
});

test('isHorizontalWheel〔|dx|<=|dy|〕縱向為主或相等 → false', () => {
  assert.equal(isHorizontalWheel(10, 120), false);
  assert.equal(isHorizontalWheel(50, 50), false); // 相等：不視為橫向意圖
  assert.equal(isHorizontalWheel(0, 0), false);
});

// ── createWheelNav.feed：累積/冷卻/方向邏輯 ────────────────────────────────

test('feed〔單次大 delta〕|dx|>threshold → 立即觸發一次 onRight（dx>0）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  const triggered = nav.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cb);
  assert.equal(triggered, true);
  assert.deepEqual(cb.calls, ['right']);
});

test('feed〔單次大負 delta〕dx<0 → 觸發 onLeft（左右對稱基本案例）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  const triggered = nav.feed({ deltaX: -120, deltaY: 0, deltaMode: 0 }, cb);
  assert.equal(triggered, true);
  assert.deepEqual(cb.calls, ['left']);
});

test('feed〔垂直為主〕|deltaX|<=|deltaY| → 不觸發、不消耗累積', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  const triggered = nav.feed({ deltaX: 10, deltaY: 100, deltaMode: 0 }, cb);
  assert.equal(triggered, false);
  assert.deepEqual(cb.calls, []);
});

test('feed〔連發 20 小 delta 同方向 <200ms 間隔〕僅觸發一次（冷卻窗生效，非 20 次）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  // 20 次 tick，每次 deltaX=15（慣性捲動典型小 delta），間隔 10ms（總耗時 190ms < cooldownMs）
  for (let i = 0; i < 20; i++) {
    nav.feed({ deltaX: 15, deltaY: 0, deltaMode: 0 }, cb);
    clock.advance(10);
  }
  assert.equal(cb.calls.length, 1, '20 個 tick 應恰好觸發 1 次（累積門檻命中後冷卻窗擋住其餘）');
  assert.deepEqual(cb.calls, ['right']);
});

test('feed〔方向反轉〕觸發後立即改方向 → 不等冷卻窗跑完即可再觸發（且方向正確）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  // 第一撥：向右觸發
  nav.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cb);
  clock.advance(5); // 遠小於 cooldownMs(200)，仍在冷卻窗內
  // 方向反轉：向左，理應立即解鎖並觸發（若冷卻未被方向反轉重置，這裡會是 false）
  const triggered = nav.feed({ deltaX: -120, deltaY: 0, deltaMode: 0 }, cb);
  assert.equal(triggered, true, '方向反轉應立即解鎖，不受尚未跑完的冷卻窗阻擋');
  assert.deepEqual(cb.calls, ['right', 'left']);
});

test('feed〔同方向未反轉〕觸發後 5ms 內同方向大 delta → 仍在冷卻窗內，不觸發第二次', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  nav.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cb);
  clock.advance(5);
  const triggered = nav.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cb);
  assert.equal(triggered, false, '同方向且仍在冷卻窗內，即使超過門檻也不應觸發');
  assert.deepEqual(cb.calls, ['right']);
});

test('feed〔deltaMode=LINE 正規化〕LINE 模式小數值 delta 正規化後應等效觸發（與 PIXEL 模式同量級）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  // LINE 模式下，deltaX=4（4 行）× 24px/行 = 96px > threshold(80) → 應觸發
  const triggered = nav.feed({ deltaX: 4, deltaY: 0, deltaMode: 1 }, cb);
  assert.equal(triggered, true, 'LINE 模式 4 行應正規化為 96px，超過 80px 門檻觸發');
  assert.deepEqual(cb.calls, ['right']);
});

test('feed〔deltaMode=LINE 未達門檻〕LINE 模式小數值不足以正規化超過門檻 → 不觸發（避免過度靈敏）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  // deltaX=2 行 × 24px = 48px < threshold(80) → 不應觸發
  const triggered = nav.feed({ deltaX: 2, deltaY: 0, deltaMode: 1 }, cb);
  assert.equal(triggered, false);
  assert.deepEqual(cb.calls, []);
});

test('feed〔停頓 ≥200ms 後〕觸發一次後長時間無事件，再送同方向大 delta → 可再次觸發', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  nav.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cb);
  clock.advance(250); // 停頓 ≥ cooldownMs(200)
  const triggered = nav.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cb);
  assert.equal(triggered, true, '停頓 ≥200ms 後應可再次觸發');
  assert.deepEqual(cb.calls, ['right', 'right']);
});

test('feed〔累積式：多個未達門檻的同方向小 delta 逐步加總後單次觸發〕不是每 tick 各自判門檻', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  const t1 = nav.feed({ deltaX: 30, deltaY: 0, deltaMode: 0 }, cb); // accum=30，未達門檻
  clock.advance(10);
  const t2 = nav.feed({ deltaX: 30, deltaY: 0, deltaMode: 0 }, cb); // accum=60，未達門檻
  clock.advance(10);
  const t3 = nav.feed({ deltaX: 30, deltaY: 0, deltaMode: 0 }, cb); // accum=90，超過門檻 → 觸發
  assert.deepEqual([t1, t2, t3], [false, false, true]);
  assert.deepEqual(cb.calls, ['right']);
});

test('feed〔左右對稱：連續兩次獨立長停頓觸發，方向各自正確〕', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now });
  const cb = makeSpyCallbacks();
  nav.feed({ deltaX: -100, deltaY: 0, deltaMode: 0 }, cb);
  clock.advance(250);
  nav.feed({ deltaX: 100, deltaY: 0, deltaMode: 0 }, cb);
  clock.advance(250);
  nav.feed({ deltaX: -100, deltaY: 0, deltaMode: 0 }, cb);
  assert.deepEqual(cb.calls, ['left', 'right', 'left']);
});

// ── isVerticalWheel：isHorizontalWheel 的縱向鏡像（102d P2b） ──────────────

test('isVerticalWheel〔|dy|>|dx|〕縱向為主 → true', () => {
  assert.equal(isVerticalWheel(10, 120), true);
  assert.equal(isVerticalWheel(10, -120), true);
});

test('isVerticalWheel〔|dy|<=|dx|〕橫向為主或相等 → false（與 isHorizontalWheel 互斥不互補）', () => {
  assert.equal(isVerticalWheel(120, 10), false);
  assert.equal(isVerticalWheel(50, 50), false); // 相等：isHorizontalWheel/isVerticalWheel 皆 false
  assert.equal(isVerticalWheel(0, 0), false);
});

// ── createWheelNav({ axis: 'vertical' }).feed：垂直軸累積/冷卻/方向邏輯 ────
// 與水平軸案例一一對應（門檻/冷卻/方向反轉解鎖邏輯共用，僅軸別與 callback 命名不同：
// onUp/onDown 取代 onLeft/onRight，dy<0→onUp、dy>0→onDown）。

test('feed〔垂直軸：單次大 deltaY〕|dy|>threshold → 立即觸發一次 onDown（dy>0，滾下=next）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now, axis: 'vertical' });
  const cb = makeVerticalSpyCallbacks();
  const triggered = nav.feed({ deltaX: 0, deltaY: 120, deltaMode: 0 }, cb);
  assert.equal(triggered, true);
  assert.deepEqual(cb.calls, ['down']);
});

test('feed〔垂直軸：單次大負 deltaY〕dy<0 → 觸發 onUp（滾上=prev）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now, axis: 'vertical' });
  const cb = makeVerticalSpyCallbacks();
  const triggered = nav.feed({ deltaX: 0, deltaY: -120, deltaMode: 0 }, cb);
  assert.equal(triggered, true);
  assert.deepEqual(cb.calls, ['up']);
});

test('feed〔垂直軸：水平為主〕|deltaY|<=|deltaX| → 不觸發、不消耗累積（軸向獨立於水平判斷）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now, axis: 'vertical' });
  const cb = makeVerticalSpyCallbacks();
  const triggered = nav.feed({ deltaX: 100, deltaY: 10, deltaMode: 0 }, cb);
  assert.equal(triggered, false);
  assert.deepEqual(cb.calls, []);
});

test('feed〔垂直軸：連發 20 小 deltaY 同方向 <200ms 間隔〕僅觸發一次（冷卻窗對垂直同樣生效）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now, axis: 'vertical' });
  const cb = makeVerticalSpyCallbacks();
  for (let i = 0; i < 20; i++) {
    nav.feed({ deltaX: 0, deltaY: 15, deltaMode: 0 }, cb);
    clock.advance(10);
  }
  assert.equal(cb.calls.length, 1, '20 個 tick 應恰好觸發 1 次（累積門檻命中後冷卻窗擋住其餘）');
  assert.deepEqual(cb.calls, ['down']);
});

test('feed〔垂直軸：方向反轉〕觸發後立即改方向 → 不等冷卻窗跑完即可再觸發（方向反轉解鎖對垂直同樣適用）', () => {
  const clock = makeClock();
  const nav = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now, axis: 'vertical' });
  const cb = makeVerticalSpyCallbacks();
  nav.feed({ deltaX: 0, deltaY: 120, deltaMode: 0 }, cb); // 滾下觸發
  clock.advance(5); // 遠小於 cooldownMs(200)，仍在冷卻窗內
  const triggered = nav.feed({ deltaX: 0, deltaY: -120, deltaMode: 0 }, cb); // 反轉滾上
  assert.equal(triggered, true, '方向反轉應立即解鎖，不受尚未跑完的冷卻窗阻擋');
  assert.deepEqual(cb.calls, ['down', 'up']);
});

test('feed〔垂直軸：軸向獨立〕水平版與垂直版分屬兩個獨立實例，互不干擾冷卻/累積狀態', () => {
  const clock = makeClock();
  const navH = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now }); // 預設 axis:'horizontal'
  const navV = createWheelNav({ threshold: 80, cooldownMs: 200, now: clock.now, axis: 'vertical' });
  const cbH = makeSpyCallbacks();
  const cbV = makeVerticalSpyCallbacks();
  // 水平版觸發並進入冷卻窗
  navH.feed({ deltaX: 120, deltaY: 0, deltaMode: 0 }, cbH);
  clock.advance(5);
  // 垂直版（獨立實例）不受水平版冷卻窗影響，同樣可立即觸發
  const triggeredV = navV.feed({ deltaX: 0, deltaY: 120, deltaMode: 0 }, cbV);
  assert.equal(triggeredV, true, '垂直版累積器與水平版累積器互相獨立，不共用冷卻窗');
  assert.deepEqual(cbH.calls, ['right']);
  assert.deepEqual(cbV.calls, ['down']);
});
