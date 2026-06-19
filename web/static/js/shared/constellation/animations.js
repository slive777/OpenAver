/**
 * animations.js — Constellation Lab 三個 timeline 進出口
 * CD-56B-4/5/7: DrawSVGPlugin register guard + starSettle + 三個 play* 函數
 *
 * ESM export — 不走 window 全域
 * animations.js 不 import pickEight（防雙抽，host 傳入 nextVisible）
 */

import { ANCHORS, railEndpoint } from './anchors.js';
import { railRole, setRailCoords, railDrawIn, railDrawOut, railClickedPulse } from './rails.js';

// ---------------------------------------------------------------------------
// DrawSVGPlugin idempotent register guard（CD-56B-4）
// ---------------------------------------------------------------------------
if (typeof DrawSVGPlugin !== 'undefined' && !gsap.plugins.drawSVG) {
  gsap.registerPlugin(DrawSVGPlugin);
}

// ---------------------------------------------------------------------------
// starSettle CustomEase（CD-56B-5）
// 在 DrawSVGPlugin guard 之後，頂層執行（module init 時一次）
// fluent-decel / fluent-accel / fluent 三曲線已在 motion-adapter.js 註冊，不重複 register
// ---------------------------------------------------------------------------
if (typeof CustomEase !== 'undefined') {
  // 保留 register 供 56c 評估；無 caller（T2fix1 退役）
  // CD-T2FIX-1：clicked card 已改走 fluent-decel，starSettle 退役但保留 register
  CustomEase.create('starSettle', 'M0,0 C0,0 0.6,1.4 0.8,1.05 0.9,0.95 1,1 1,1');
}

// ---------------------------------------------------------------------------
// poster-crop 比例常數（US2，v0.10.2）
// NC#7 微調點：改此值同步更新 CSS --poster-crop-ratio（theme.css）
// poster 盒寬由 POSTER_CROP_RATIO 推導（load-bearing，NC#7 改此一處 JS 即同步）：
//   SLOT_W = round(150 * 0.71) = 107；MAIN_W = round(250 * 0.71) = 178
// 注意：state-similar.js 的 slot reset（width:107）為跨模組字面值鏡像，
//   NC#7 微調時須同步該檔 + CSS --poster-crop-ratio（三套渲染機制各自獨立）。
// ---------------------------------------------------------------------------
const POSTER_CROP_RATIO = 0.71;
const SLOT_W = Math.round(150 * POSTER_CROP_RATIO);   // 107
const MAIN_W = Math.round(250 * POSTER_CROP_RATIO);   // 178

// ---------------------------------------------------------------------------
// playInitialExpand — 8 張卡從中心滑出至 anchor 位置（CD-56B-7）
// ---------------------------------------------------------------------------
/**
 * @param {Object<string, HTMLElement>} cards   - slotId → DOM element
 * @param {Object<string, SVGLineElement>} railLines - slotId → SVG line element
 * @param {Set<string>} initSlots               - 初始 8 個 slot ids
 * @param {() => void} onComplete               - timeline 完成 callback
 * @returns {gsap.core.Timeline}
 */
export function playInitialExpand(cards, railLines, initSlots, onComplete) {
  const tl = gsap.timeline({ onComplete });
  let idx = 0;

  initSlots.forEach(id => {
    const anchor = ANCHORS.find(a => a.id === id);
    const card = cards[id];
    const line = railLines[id];
    if (!anchor || !card) return;

    card.classList.remove('slot--hidden');
    gsap.set(card, { xPercent: -50, yPercent: -50, left: 480, top: 310, opacity: 0, width: SLOT_W, height: 150, x: 0, y: 0, rotation: 0 });

    const cardT = idx * 0.06;

    // Card 從中心滑至 anchor（CD-56B-7: 0.50s fluent-decel，stagger 0.06s）
    tl.to(card, {
      left: anchor.x,
      top: anchor.y,
      opacity: 1,
      duration: 0.50,
      ease: 'fluent-decel',
    }, cardT);

    // Rail draw-in（CD-56B-7: 0.55s fluent-decel，比 card 晚 0.05s）
    if (line) {
      setRailCoords(line, anchor);
      railDrawIn(line, tl, cardT + 0.05);
    }

    idx++;
  });

  return tl;
}

// ---------------------------------------------------------------------------
// playSlipThrough — slip-through 連續穿透（CD-56B-7）
// host 先算 nextVisible 後傳入，此函數不 import/call pickEight
// ---------------------------------------------------------------------------
/**
 * @param {string} clickedId            - 被點擊的 slot id
 * @param {Set<string>} prevVisible     - 前一批 8 個 slot ids
 * @param {Set<string>} nextVisible     - host 算好的下一批 8 個 slot ids（不重算）
 * @param {Object<string, HTMLElement>} cards
 * @param {Object<string, SVGLineElement>} railLines
 * @param {HTMLElement} mainImg
 * @param {() => void} onComplete
 * @param {{onMainSwap?: (clickedId: string) => void, onPrevVisibleHidden?: () => void, onBeforeCardEnter?: (slotId: string) => void}} [options]
 *   - onMainSwap: t=0.30 呼叫，供 host 換主圖 src（DOM 直寫，不更新 reactive 資料）
 *   - onPrevVisibleHidden: t=0.46 clicked card 加 slot--hidden 之後同步呼叫，供 host
 *     此時才整批 swap reactive 資料（similarResults）。分離「DOM 直寫」與「reactive
 *     rebind」時機，避免 t=0.30 swap 把仍在中央的 clicked slot 重綁新批圖（rebind bug）。
 *     motion-lab 不傳此 callback → no-op，backward-compat。
 *   - onBeforeCardEnter: 每張 enter/persist slot 的 reset callback 開頭、slot--hidden
 *     移除之前同步呼叫，供 host imperative 設定該 slot img.src 為新批同 idx 的 cover_url，
 *     避免 fade-in 初期 reactive binding 仍綁舊 similarResults 顯示錯誤封面（codex-fix4）。
 *     motion-lab 不傳此 callback → no-op，backward-compat。
 * @returns {gsap.core.Timeline}
 */
export function playSlipThrough(clickedId, prevVisible, nextVisible, cards, railLines, mainImg, onComplete, options = {}) {
  const newBatch = nextVisible;
  const carryOverIds = [...prevVisible].filter(
    id => id !== clickedId && newBatch.has(id)
  );
  const pureExitIds = [...prevVisible].filter(
    id => id !== clickedId && !newBatch.has(id)
  );

  const tl = gsap.timeline({ onComplete });

  // t=0: 被點卡飛向中心 + 變大（CD-T2FIX-1: 0.46s fluent-decel，starSettle 退役）
  if (cards[clickedId]) {
    tl.to(cards[clickedId], {
      left: 480,
      top: 310,
      width: MAIN_W,
      height: 250,
      opacity: 1,
      duration: 0.46,
      ease: 'fluent-decel',
      zIndex: 150,
    }, 0);
  }

  // t=0: clicked rail 脈衝收掉（CD-T2FIX-3）
  if (railLines[clickedId]) {
    railClickedPulse(railLines[clickedId], tl, 0);
  }

  // t=0: 舊主圖 fade-out（CD-56B-7: 0.30s fluent-accel）
  if (mainImg) {
    tl.to(mainImg, { opacity: 0, duration: 0.30, ease: 'fluent-accel' }, 0);
    // T2fix3：halo expand/收回（替換 T2fix1 的 --main-flash-strength 最小版）
    // t=0.00: outer halo 擴張接收（CD-T2FIX-4 §D）
    tl.to('#main-halo-outer', { '--main-halo-opacity': 0.85, '--main-halo-scale': 1.06, duration: 0.30, ease: 'fluent-decel' }, 0);
    // t=0.30: outer halo 收回
    tl.to('#main-halo-outer', { '--main-halo-opacity': 0.55, '--main-halo-scale': 1, duration: 0.22, ease: 'fluent' }, 0.30);
    // t=0.35: main heartbeat（接收脈衝）
    tl.to(mainImg, { scale: 1.025, duration: 0.14, ease: 'fluent' }, 0.35);
    // t=0.49: heartbeat 還原
    tl.to(mainImg, { scale: 1, duration: 0.14, ease: 'fluent' }, 0.49);
  }

  // t=0: 純離場卡沿 rail 滑出（CD-56B-7: 0.55s fluent-accel）
  pureExitIds.forEach(id => {
    if (!cards[id]) return;
    const anchor = ANCHORS.find(a => a.id === id);
    if (!anchor) return;
    const ep = railEndpoint(anchor);
    tl.to(cards[id], {
      left: ep.x,
      top: ep.y,
      opacity: 0,
      duration: 0.55,
      ease: 'fluent-accel',
    }, 0);
  });

  // t=0: carry-over 卡快速 fade-out（CD-56B-7: 0.15s fluent-accel）
  carryOverIds.forEach(id => {
    if (!cards[id]) return;
    tl.to(cards[id], { opacity: 0, duration: 0.15, ease: 'fluent-accel' }, 0);
  });

  // t=0: rail exit fade（CD-56B-7: 0.35s fluent-accel）
  // Determine exit rails using railRole
  // Codex r2 F3：clicked rail 已由 railClickedPulse 獨佔處理，跳過避免 opacity tween 重疊
  ANCHORS.forEach(anchor => {
    const id = anchor.id;
    if (id === clickedId) return; // railClickedPulse 已接管，勿雙寫
    const line = railLines[id];
    if (!line) return;
    const role = railRole(id, prevVisible, newBatch);
    if (role === 'exit') {
      railDrawOut(line, tl, 0);
    }
    // persist: no-op; enter: handled in new batch section below; absent: no-op
  });

  // t=0.30: 新主圖內容置換（callback）+ fade-in at 0.35
  // 56b placeholder：把被點 slot id 寫入 #main-id-label，提供 phase 2 視覺確認
  // （56c 換真實 API 時改為 swap cover image）
  if (mainImg) {
    tl.call(() => {
      // T4: host 注入 hook 切主圖 src（56c 將以同一 hook 接真實 cover swap）
      options.onMainSwap?.(clickedId);
      const labelEl = document.getElementById('main-id-label');
      if (labelEl) labelEl.textContent = clickedId;
      gsap.set(mainImg, { opacity: 0 });
    }, null, 0.30);
    tl.to(mainImg, { opacity: 1, duration: 0.35, ease: 'fluent-decel' }, 0.35);
  }

  // t=0.46: 被點卡 hide + reset size（absorb tween 結束後立即清，避免硬截最後 60ms）
  // Codex r1 P1 修正：原 0.40 截斷 0.46 absorb 平滑收尾
  if (cards[clickedId]) {
    tl.call(() => {
      cards[clickedId].classList.add('slot--hidden');
      gsap.set(cards[clickedId], { xPercent: -50, yPercent: -50, opacity: 0, width: SLOT_W, height: 150, zIndex: 10, x: 0, y: 0, rotation: 0 });
      // T5 codex-fix3: clicked card 已 hidden，可見 slot src 不再受 reactive rebind 影響，
      // 此時 host 才安全 swap similarResults（rebind bug fix）
      options.onPrevVisibleHidden?.();
    }, null, 0.46);
  }

  // t=0.20+: 新批 8 張從中心湧出（CD-56B-7: 0.55s fluent-decel，stagger 0.05s）
  [...newBatch].forEach((id, idx) => {
    const anchor = ANCHORS.find(a => a.id === id);
    const card = cards[id];
    if (!anchor || !card) return;

    const startT = 0.20 + idx * 0.05;
    const role = railRole(id, prevVisible, newBatch);

    // Setup card at center before it enters
    tl.call(() => {
      // codex-fix4: slot 仍 hidden 時讓 host imperative 設 src，避免 fade-in 期間
      // reactive :src 還綁舊 similarResults 顯示錯誤封面
      options.onBeforeCardEnter?.(id);
      card.classList.remove('slot--hidden');
      gsap.set(card, { xPercent: -50, yPercent: -50, left: 480, top: 310, opacity: 0, width: SLOT_W, height: 150, x: 0, y: 0, rotation: 0 });
    }, null, Math.max(0, startT - 0.01));

    tl.to(card, {
      left: anchor.x,
      top: anchor.y,
      opacity: 1,
      duration: 0.55,
      ease: 'fluent-decel',
    }, startT);

    // Rail enter draw-in for new slots（CD-56B-7: t = enterCard + 0.05s）
    if (role === 'enter' && railLines[id]) {
      setRailCoords(railLines[id], anchor);
      railDrawIn(railLines[id], tl, startT + 0.05);
    }
  });

  return tl;
}

// ---------------------------------------------------------------------------
// playExit — 退出動畫：8 張沿 rail 外滑 + 主圖 fade（CD-56B-7）
// ---------------------------------------------------------------------------
/**
 * @param {Object<string, HTMLElement>} cards
 * @param {Object<string, SVGLineElement>} railLines
 * @param {Set<string>} visibleSlots
 * @param {HTMLElement} mainImg
 * @param {() => void} onComplete
 * @returns {gsap.core.Timeline}
 */
export function playExit(cards, railLines, visibleSlots, mainImg, onComplete) {
  const tl = gsap.timeline({ onComplete });

  // 8 張沿 rail 滑出（CD-56B-7: 0.55s fluent-accel）
  [...visibleSlots].forEach(id => {
    const anchor = ANCHORS.find(a => a.id === id);
    const card = cards[id];
    if (!anchor || !card) return;

    const ep = railEndpoint(anchor);
    tl.to(card, {
      left: ep.x,
      top: ep.y,
      opacity: 0,
      duration: 0.55,
      ease: 'fluent-accel',
    }, 0);

    // Rail fade（CD-56B-7: 0.35s fluent-accel）
    if (railLines[id]) {
      railDrawOut(railLines[id], tl, 0);
    }
  });

  // 主圖 fade + scale（CD-56B-7: 0.35s fluent-accel）
  if (mainImg) {
    tl.to(mainImg, {
      opacity: 0,
      scale: 0.95,
      duration: 0.35,
      ease: 'fluent-accel',
    }, 0);
  }

  return tl;
}
