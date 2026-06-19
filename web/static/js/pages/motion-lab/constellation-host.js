/**
 * pages/motion-lab/constellation-host.js — Thin host：Alpine.data('constellationLab', ...)
 *
 * 56b-T3：從 pages/clip-lab/main.js 等價搬遷至 motion-lab Constellation tab。
 * import 路徑深度多一層（../../shared/constellation/...），其餘行為與舊 host 等價。
 *
 * CD-56B-8 thin host 規範：
 *   - 只做：import shared 模組、Alpine.data 宣告、init + click dispatch
 *   - 禁做：座標計算、rail 邏輯、timeline 建構
 * 雙抽防護：host onCardClick 算 nextVisible，再傳 animations；animations 不 import pickEight
 *
 * D-4：Constellation tab panel 用 x-if，mount/destroy 觸發 Alpine init / destroy lifecycle。
 *      destroy() 內呼叫 breathingManager.stop() + _gsapCtx.revert()，避免 ticker / tween 殘留。
 */

import { ANCHORS, pickEight, nearestNeighbors, railEndpoint } from '../../shared/constellation/anchors.js';
import { setRailCoords, railSweep, resetSweepLine } from '../../shared/constellation/rails.js';
import { playInitialExpand, playSlipThrough, playExit } from '../../shared/constellation/animations.js';
import { BreathingManager } from '../../shared/constellation/breathing.js';

// T4 visual probe（56c-preflight）：本地靜態 sc-{1..N}.jpg 模擬 prod 真實封面
// spec-56.md §3 Phase 56b Non-Goals 例外允許；不接 API、不碰 Showcase
const IMAGE_BASE = '/static/img/showcase/';
const IMAGE_COUNT = 20;

// T6 (CD-T6-1)：hover corridor half-width（mockup E 量測值）
// 30px 太窄、50px 太寬；40px 下 per-rail 期望 4-6 顆，中央 dust 跨多 rail（Polaris 感）
const HOVER_DISTANCE = 40;

/**
 * pointToSegmentDist — 點到線段最短距離（T6 CD-T6-1）
 * 與 tests/unit/test_constellation_host_T6.py 內的 Python re-implement 同義
 *
 * @param {number} px - 點 x
 * @param {number} py - 點 y
 * @param {number} x1 - 線段端點 1 x
 * @param {number} y1 - 線段端點 1 y
 * @param {number} x2 - 線段端點 2 x
 * @param {number} y2 - 線段端點 2 y
 * @returns {number} 距離（px）
 */
function pointToSegmentDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

document.addEventListener('alpine:init', () => {
  Alpine.data('constellationLab', () => ({
    animating: false,
    visibleSlots: new Set(),
    mainSlot: null,
    cards: {},       // slotId -> HTMLElement
    railLines: {},   // slotId -> SVGLineElement
    sweepLines: {},  // slotId -> SVGLineElement（sweep overlay）
    breathingManager: null,
    _mainBreathTween: null,
    _activeTimeline: null,         // 當前 play* 回傳的 timeline，destroy 時 kill（Codex T3 P1）
    _activeFocusedRailId: null,    // hover focus 的 slotId（用於 _resetHoverRails cleanup）
    _activeNeighborRailIds: [],    // hover 觸發的 neighbor slotIds
    _activeHoverSlot: null,        // 當前 hover 的 slotId（防 enter→enter 殘留，T2fix5 Codex P2）
    _slotImages: {},               // T4: slotId -> imageUrl（host 自管，shared/* 不感知）
    // T5 (CD-T5-2 / round-2 P1-2)：T6/T7 替換為實作；T5 引入 NO-OP stub + state field 避 init() TypeError
    _railStarMap: {},              // T6 CD-T6-5：{ '#01': [circleEl, ...] } rail × dust 距離 pre-compute
    _idleAcknowledgeTimer: null,   // T7 CD-T7-2：setTimeout handle for 8-15s 隨機 idle pulse

    init() {
      this._gsapCtx = window.OpenAver.motion.createContext(this.$el);

      // Build DOM refs（card / rail 用 id 對應，id 格式 card-01 / rail-01）
      ANCHORS.forEach(a => {
        const num = a.id.slice(1); // '#01' → '01'
        this.cards[a.id] = document.getElementById(`card-${num}`);
        this.railLines[a.id] = document.getElementById(`rail-${num}`);
        this.sweepLines[a.id] = document.getElementById(`sweep-${num}`);

        // 設定 rail 端點座標
        if (this.railLines[a.id]) {
          setRailCoords(this.railLines[a.id], a);
        }

        // 所有卡片初始放在中心（GSAP 計算用）
        if (this.cards[a.id]) {
          gsap.set(this.cards[a.id], { left: 480, top: 310 });
        }
      });

      // 建立 BreathingManager（即使 prefers-reduced-motion 也建立，避免 hover 觸發 null 錯誤）
      this.breathingManager = new BreathingManager(this.cards, this.railLines, ANCHORS);

      // T4 visual probe：12 slot + main 全部預綁圖（含 hidden #09-#12，避免第一次 slip-through LCP 抖動）
      this._assignAllImages();

      // T5 (CD-T5-2 / round-2 P1-2)：build rail × dust corridor map（T6 用）+ 啟動 idle acknowledge timer（T7 用）
      // 兩者在 T5 都是 NO-OP stub，僅佔 method 名稱，避 T6/T7 commit 卡 method 不存在
      this._buildRailStarMap();
      this._startIdleAcknowledge();

      // prefers-reduced-motion：直接呈現終態，跳過所有 timeline（CD-56B DoD 共通 5）
      if (window.OpenAver.prefersReducedMotion) {
        this._setInitialState();
        return;
      }

      this._playInitialExpand();
    },

    // ---- T4 visual probe helpers ---------------------------------------
    /**
     * _randomImageUrl — 從 sc-{1..N}.jpg 隨機抽一張
     * 用戶確認「圖片挑選順序沒差」，無 pool / 無 reshuffle / 無排重
     */
    _randomImageUrl() {
      const n = 1 + Math.floor(Math.random() * IMAGE_COUNT);
      return `${IMAGE_BASE}sc-${n}.jpg`;
    },
    /**
     * _setSlotImage — 寫 slot 卡片內 <img> src，並更新 _slotImages map
     */
    _setSlotImage(slotId, url) {
      this._slotImages[slotId] = url;
      const num = slotId.slice(1); // '#01' → '01'
      const card = this.cards[slotId] || document.getElementById(`card-${num}`);
      const imgEl = card?.querySelector('.clip-lab-slot-img');
      if (imgEl) imgEl.src = url;
    },
    /**
     * _setMainImage — 寫中央主圖 <img> src（onMainSwap hook 與 reduced-motion 短路共用）
     */
    _setMainImage(url) {
      const mainImgEl = document.getElementById('main-img-photo');
      if (mainImgEl && url) mainImgEl.src = url;
    },
    /**
     * _assignAllImages — 12 slot + main 全部抽一張（init / x-if remount 時呼叫）
     */
    _assignAllImages() {
      ANCHORS.forEach(a => this._setSlotImage(a.id, this._randomImageUrl()));
      this._setMainImage(this._randomImageUrl());
    },
    // --------------------------------------------------------------------

    // ---- T5 NO-OP stubs（T6/T7 替換為實作）------------------------------
    // 切片獨立性（CD-T5-2 / round-2 P1-2）：T5 commit 後 init() 直接呼叫這些方法，
    // destroy() / onCardClick() / onExit() / onHoverEnter() 也呼叫 _cancelIdleAcknowledge()。
    // 若 T6/T7 才新增方法，T5 commit → motion-lab Constellation tab mount 即 TypeError。
    // T7 plan §「替換 stub 為實作」（不是「新增方法」），保留 method 名稱 stable。

    /**
     * _buildRailStarMap — T6 CD-T6-1 / CD-T6-5 實作：
     *   for each ANCHOR rail，計算 stage 內 dust circle 是否落在「rail 線段 HOVER_DISTANCE corridor」內，
     *   結果存 this._railStarMap[a.id] = [circleEl, ...]，供 hover 時 class swap 用。
     *
     *   - line segment：center (480, 310) → railEndpoint(anchor)（從 center 朝 anchor 方向延伸 1.4×）
     *   - HOVER_DISTANCE = 40 px（CD-T6-1，mockup E 量測值）
     *   - pre-compute 在 init() 末尾呼叫一次（dust DOM x-if mount 時已就位）
     *   - 不另外維護 `_currentConstellationStars` 影子欄位（CD-T6-5），cleanup 時用 _activeFocusedRailId 取
     */
    _buildRailStarMap() {
      const dustEls = [...document.querySelectorAll('.clip-lab-dust circle')];
      this._railStarMap = {};
      ANCHORS.forEach(a => {
        const ep = railEndpoint(a);
        this._railStarMap[a.id] = dustEls.filter(el => {
          const cx = parseFloat(el.getAttribute('cx'));
          const cy = parseFloat(el.getAttribute('cy'));
          return pointToSegmentDist(cx, cy, 480, 310, ep.x, ep.y) <= HOVER_DISTANCE;
        });
      });
    },

    /**
     * _startIdleAcknowledge — T7 CD-T7-2 實作：
     *   setTimeout 8-15s 隨機 → 觸發 idle pulse（dust micro-twinkle / star-of-the-moment）。
     *   PRM guard：reduced-motion 下首行 return，timer 永不啟動。
     *   遞迴重啟：pulse 結束後重新計時（無連鎖、無 stack growth — setTimeout async 排程）。
     */
    _startIdleAcknowledge() {
      if (window.OpenAver.prefersReducedMotion) return; // C4: PRM 不啟動
      this._cancelIdleAcknowledge();
      const delay = Math.random() * 7000 + 8000; // 8000-15000 ms（spec §5.2 8-15s）
      this._idleAcknowledgeTimer = setTimeout(() => {
        this._fireIdlePulse();
        this._startIdleAcknowledge(); // 遞迴重啟（pulse 結束後重新計時）
      }, delay);
    },

    /**
     * _cancelIdleAcknowledge — T7 CD-T7-2 實作：
     *   clearTimeout(this._idleAcknowledgeTimer); this._idleAcknowledgeTimer = null;
     * 在 destroy / onCardClick / onExit / onHoverEnter 共 4 處呼叫（T5 已 wire）。
     * 注意：本 method 只清下一次 setTimeout，不清正在進行的 pulse tween（pulse 0.40s
     * 短，自然跑完即可；destroy 才需主動 killTweensOf 補強保護）。
     */
    _cancelIdleAcknowledge() {
      if (this._idleAcknowledgeTimer) {
        clearTimeout(this._idleAcknowledgeTimer);
        this._idleAcknowledgeTimer = null;
      }
    },

    // ---- T7 Phase Acknowledge methods（CD-T7-1 / CD-T7-3 + plan §5.3 G）----
    /**
     * _getKeystoneStars — CD-T7-1：keystone = corridor stars 中距離 anchor 端最近的 N 顆
     * 純幾何 helper，無副作用。
     *   - anchor 端最近：spec §5.2「接近卡片那端優先」+ 視覺語義（pulse 在「視線連到的終點」）
     *   - graceful fallback：anchor 不存在 / corridor 空 → return []
     *
     * @param {string} slotId
     * @param {number} count - default 2（最多 2 顆）
     * @returns {Element[]} corridor stars，按距 anchor 升序排序前 N
     */
    _getKeystoneStars(slotId, count = 2) {
      const anchor = ANCHORS.find(a => a.id === slotId);
      if (!anchor) return [];
      const stars = this._railStarMap[slotId] || [];
      if (stars.length === 0) return [];
      return [...stars]
        .map(el => {
          const cx = parseFloat(el.getAttribute('cx'));
          const cy = parseFloat(el.getAttribute('cy'));
          const d = Math.hypot(cx - anchor.x, cy - anchor.y);
          return { el, d };
        })
        .sort((a, b) => a.d - b.d)
        .slice(0, count)
        .map(item => item.el);
    },

    /**
     * _fireKeystonePulse — CD-T7-3：slip-through 完成後，新主圖最近 rail corridor 端 1-2 顆
     * dust 套 0.40s 隱性 pulse（rise 0.20s decel + fall 0.20s accel，peak opacity 0.95 / scale 1.10）。
     *
     * P3-2: gsap.killTweensOf(el) 不限定 property — pulse 同 timeline tween opacity + scale，
     *       killTweensOf(el, 'opacity') 會留下舊 scale tween 殘留。
     * Codex round-2 P1-3: el.classList.add('dust-pulsing') 暫停 CSS twinkle，
     *       否則 GSAP inline opacity 會被 dust-twinkle keyframe 覆蓋變不可見。
     *
     * @param {string} slotId
     */
    _fireKeystonePulse(slotId) {
      const stars = this._getKeystoneStars(slotId, 2);
      if (stars.length === 0) return; // graceful fallback
      stars.forEach(el => {
        gsap.killTweensOf(el);
        el.classList.add('dust-pulsing');
        const baseSeed = parseFloat(el.style.getPropertyValue('--dust-base-seed')) || 0.08;
        gsap.timeline({
          onComplete: () => {
            gsap.set(el, { clearProps: 'opacity,scale,transform' });
            el.classList.remove('dust-pulsing'); // 還原 CSS twinkle / bright
          },
        })
          .to(el, {
            opacity: 0.95, scale: 1.10, duration: 0.20,
            ease: 'fluent-decel', transformOrigin: '50% 50%',
          })
          .to(el, {
            opacity: baseSeed, scale: 1.0, duration: 0.20,
            ease: 'fluent-accel',
          });
      });
    },

    /**
     * _fireIdlePulse — CD-T7-3：idle 期間每 8-15s 隨機抽 1 顆非 hover-bright dust 微亮
     * （peak opacity 0.95 / scale 1.08 — 比 keystone 1.10 略小，保持「不爆閃」§2.1 母約束）。
     *
     * P3-3: filter 掉 .in-constellation dust（bright 在 0.70-1.00 區間 twinkle，
     *       再蓋 0.95 idle pulse 視覺無感且會強制把 bright twinkle 暫停）。
     */
    _fireIdlePulse() {
      const dustEls = [...document.querySelectorAll('.clip-lab-dust circle')]
        .filter(el => !el.classList.contains('in-constellation'));
      if (dustEls.length === 0) return;
      const target = dustEls[Math.floor(Math.random() * dustEls.length)];
      const baseSeed = parseFloat(target.style.getPropertyValue('--dust-base-seed')) || 0.08;
      gsap.killTweensOf(target);
      target.classList.add('dust-pulsing');
      gsap.timeline({
        onComplete: () => {
          gsap.set(target, { clearProps: 'opacity,scale,transform' });
          target.classList.remove('dust-pulsing');
        },
      })
        .to(target, {
          opacity: 0.95, scale: 1.08, duration: 0.20,
          ease: 'fluent-decel', transformOrigin: '50% 50%',
        })
        .to(target, {
          opacity: baseSeed, scale: 1.0, duration: 0.20,
          ease: 'fluent-accel',
        });
    },

    /**
     * _abortActiveDustPulses — Codex round-3 P2 hover-pulse race fix：
     * onHoverEnter 在 add('in-constellation') 之前呼叫，主動清 corridor 內仍在 pulse 的 dust。
     * 若不清，bright twinkle 會凍結在 pulse inline opacity 0.95 直到 pulse fall 完。
     *
     * 範圍只限 corridor（非全 100 顆）：keystone pulse 在 slip-through onComplete 觸發，
     * 當下 hover 已被 onCardClick 開頭的 _resetHoverRails 清掉；只 idle pulse 需此處理，
     * 且 idle pulse 隨機打單顆 dust，corridor 外的 dust 即使在 pulse 中也不會被 hover 觸發疊加。
     *
     * @param {string} slotId
     */
    _abortActiveDustPulses(slotId) {
      const corridor = this._railStarMap[slotId] || [];
      corridor.forEach(el => {
        if (el.classList.contains('dust-pulsing')) {
          gsap.killTweensOf(el); // 殺 opacity / scale tween
          gsap.set(el, { clearProps: 'opacity,scale,transform' });
          el.classList.remove('dust-pulsing'); // 還原 CSS animation
        }
      });
    },

    /**
     * _abortAllActiveDustPulses — Codex review P2-2 fix：
     * spec §5.2「Slip-through 動畫進行中 | idle acknowledge 強制暫停」契約實作。
     *
     * `_cancelIdleAcknowledge()` 只清下一次 setTimeout（plan §G 既有設計），
     * 但 phase transition（slip-through / exit）開始時，正在跑的 idle / keystone
     * pulse tween 不會被打斷，導致 dust pulse 仍可動最多 0.4s（違反「強制暫停」契約）。
     *
     * 範圍：全 100 顆（不限 corridor）— phase transition 是全域事件，與 corridor-only
     * 的 `_abortActiveDustPulses(slotId)`（hover-pulse race fix）區隔。
     */
    _abortAllActiveDustPulses() {
      document.querySelectorAll('.clip-lab-dust circle.dust-pulsing').forEach(el => {
        gsap.killTweensOf(el);
        gsap.set(el, { clearProps: 'opacity,scale,transform' });
        el.classList.remove('dust-pulsing');
      });
    },
    // --------------------------------------------------------------------


    /**
     * _playInitialExpand — 啟動初始 8 顆展開（init 與 onExit 重置共用）
     * Codex T3 P1：timeline reference 存進 _activeTimeline，destroy 時 kill
     * Codex T3 P1：onComplete 內加 destroyed guard（_gsapCtx 已 null 表示 tab 已切走），
     *              避免在已銷毀 DOM 上呼叫 breathingManager.start。
     */
    _playInitialExpand() {
      const initSlots = new Set(['#01', '#02', '#03', '#04', '#05', '#06', '#07', '#08']);
      this.animating = true;
      this._activeTimeline = playInitialExpand(this.cards, this.railLines, initSlots, () => {
        if (!this._gsapCtx) return; // destroyed during animation — stop here
        this._activeTimeline = null;
        this.visibleSlots = new Set(initSlots);
        this.animating = false;
        this.breathingManager.start(initSlots);
        this._startMainBreath();
      });
    },

    /**
     * destroy — Alpine x-if mount/destroy lifecycle hook（D-4）
     * tab 切走時 x-if=false → DOM 銷毀 → Alpine 觸發 destroy()。
     * 關鍵：停 BreathingManager ticker（gsap.ticker.remove）+ revert GSAP context（清所有 tween / inline style）。
     */
    destroy() {
      // T5 (CD-T5-2)：cancel idle acknowledge timer（NO-OP in T5；T7 替換為 clearTimeout）
      this._cancelIdleAcknowledge();
      // Codex T3 P1：kill 當前 play* timeline（gsap.context 不收 host 模組層建立的 timeline，
      // 不 kill 會讓 onComplete 在 DOM 銷毀後仍重啟 breathing ticker）
      if (this._activeTimeline) {
        this._activeTimeline.kill();
        this._activeTimeline = null;
      }
      this.breathingManager?.stop();
      this._stopMainBreath();
      // Codex T3 P2 follow-up #2：createContext(this.$el) 用空 fn 建立，host 之後直呼 gsap.to() 的 tween
      // （carry-bump halo / survivor shimmer / hover card+rail / neighbor strokeWidth 等）不會被 ctx 自動收。
      // tab 切走時若有 delayed/in-flight tween，會在已銷毀 DOM 上繼續跑。
      // → 在 ctx.revert 前對所有 host 持有的 DOM 與 halo 全 killTweensOf。
      gsap.killTweensOf('#main-halo-outer');
      gsap.killTweensOf('#main-halo-inner');
      gsap.killTweensOf('#main-img');
      // 56c-T4fix7: 補清 --slot-dim-opacity inline style（ctx.revert 不清 CSS var inline）
      ANCHORS.forEach(a => {
        if (this.cards[a.id]) {
          gsap.killTweensOf(this.cards[a.id]);
          gsap.set(this.cards[a.id], { clearProps: '--slot-dim-opacity' });
        }
        if (this.railLines[a.id]) gsap.killTweensOf(this.railLines[a.id]);
        if (this.sweepLines[a.id]) gsap.killTweensOf(this.sweepLines[a.id]);
      });
      // T7 (plan §5.3 F)：補強保護 — destroy 中途若有 idle / keystone pulse 在跑，
      // host 直呼的 gsap.to / gsap.timeline 不在 _gsapCtx scope，revert 不收 →
      // 切 tab 後返回會看到 orphan inline opacity / scale 殘留。主動清所有 dust circle。
      document.querySelectorAll('.clip-lab-dust circle').forEach(el => {
        gsap.killTweensOf(el);
        gsap.set(el, { clearProps: 'opacity,scale,transform' });
        el.classList.remove('dust-pulsing');
      });
      if (this._gsapCtx) {
        this._gsapCtx.revert();
        this._gsapCtx = null;
      }
    },

    /**
     * _setInitialState — prefers-reduced-motion 終態：
     * gsap.set 直接到 anchor 位置，不建 timeline
     * 注意：不啟動 breathing（保持「無動畫」契約）
     */
    _setInitialState() {
      const initSlots = new Set(['#01', '#02', '#03', '#04', '#05', '#06', '#07', '#08']);
      initSlots.forEach(id => {
        const anchor = ANCHORS.find(a => a.id === id);
        const card = this.cards[id];
        const line = this.railLines[id];
        if (anchor && card) {
          card.classList.remove('slot--hidden');
          gsap.set(card, { left: anchor.x, top: anchor.y, opacity: 1 });
        }
        if (line) {
          line.classList.remove('rail--hidden');
          gsap.set(line, { opacity: 1 });
        }
      });
      this.visibleSlots = new Set(initSlots);
      this.animating = false;
      // 不呼叫 breathingManager.start()（prefers-reduced-motion：無動畫契約）
    },

    /**
     * onCardClick — 點擊 slot 卡片觸發 slip-through
     * animating flag 防護：避免 timeline 未完成時重複觸發
     * 雙抽防護：host 先算 nextVisible，再傳 playSlipThrough（不讓 animations 重算）
     *
     * @param {string} slotId
     */
    onCardClick(slotId) {
      if (this.animating || !this.visibleSlots.has(slotId)) return;

      // T5 (CD-T5-2)：cancel idle acknowledge timer（NO-OP in T5；T7 替換為 clearTimeout）
      this._cancelIdleAcknowledge();
      // T7 (Codex review P2-2)：spec §5.2「slip-through 期間 idle acknowledge 強制暫停」契約。
      // _cancelIdleAcknowledge 只清下一次 setTimeout，正在跑的 pulse tween 仍會動到 0.4s 結束。
      // 此處主動 abort 所有正在跑的 dust pulse（全 100 顆，不限 corridor）。
      this._abortAllActiveDustPulses();

      // CRITICAL: 在呼叫任何 animation / pickEight 之前，先捕獲 prevVisible（CD-T2FIX-4 §E）
      const prevVisible = new Set(this.visibleSlots);

      // host 算 nextVisible（防雙抽：animations.js 不 import pickEight）
      const nextVisible = pickEight(slotId, prevVisible, Math.random);

      // T4: enter slot 重抽圖（role === enter，nextVisible \ prevVisible）；persist / exit 維持原圖
      // 提前重抽安全：enter slot 上一輪 hidden（slot--hidden + opacity:0），用戶看不到 src 變更
      const enterIds = [...nextVisible].filter(id => !prevVisible.has(id));
      enterIds.forEach(id => this._setSlotImage(id, this._randomImageUrl()));
      // T4: 捕獲 clicked image（之後傳給 onMainSwap，或 reduced-motion 短路 sync 寫）
      const clickedImage = this._slotImages[slotId];

      // Reduced-motion 短路（CD-T2FIX-11）：sync state update，不播任何動畫
      // _resetHoverRails 防禦（切換 reduced-motion 後 hover 再 click 的極端情形）
      if (window.OpenAver.prefersReducedMotion) {
        if (this._activeHoverSlot !== null) {
          this._resetHoverCard(this._activeHoverSlot);
          this._activeHoverSlot = null;
        }
        this._resetHoverRails();
        // 隱藏舊批
        prevVisible.forEach(id => {
          const card = this.cards[id];
          if (card) {
            card.classList.add('slot--hidden');
            gsap.set(card, { opacity: 0 });
          }
        });
        // 顯示新批，定位至 anchor
        nextVisible.forEach(id => {
          const anchor = ANCHORS.find(a => a.id === id);
          const card = this.cards[id];
          if (anchor && card) {
            card.classList.remove('slot--hidden');
            // width 107 = round(150 * poster-crop 0.71)；NC#7 微調須同步 animations.js POSTER_CROP_RATIO + CSS --poster-crop-ratio（reduced-motion click path，繞過 animations.js gsap.set）
            gsap.set(card, { left: anchor.x, top: anchor.y, opacity: 1, width: 107, height: 150 });
          }
        });
        // Rails: nextVisible 顯示，其餘隱藏（DrawSVG 禁用，使用 classList + opacity）
        ANCHORS.forEach(a => {
          const line = this.railLines[a.id];
          if (!line) return;
          if (nextVisible.has(a.id)) {
            line.classList.remove('rail--hidden');
            // T4fix §I：strokeOpacity inline 一律清，由 CSS baseline (.clip-lab-rail) 接管
            gsap.set(line, { opacity: 1, clearProps: 'strokeOpacity' });
          } else {
            line.classList.add('rail--hidden');
            gsap.set(line, { opacity: 0, clearProps: 'strokeOpacity' });
          }
        });
        // T4: sync main image swap（reduced-motion 下無 0.30s 延遲）
        this._setMainImage(clickedImage);
        // Main label（T4 後 #main-id-label DOM 已移除，labelEl 為 null → no-op；保留供 56c reuse）
        const labelEl = document.getElementById('main-id-label');
        if (labelEl) labelEl.textContent = slotId;
        this.mainSlot = slotId;
        this.visibleSlots = nextVisible;
        // this.animating 維持 false（short-circuit 不設 true）
        return;
      }

      // T2fix3: 停止 main 自呼吸（absorb 期間無 yoyo 殘留，_stopMainBreath 強制 reset scale=1）
      this._stopMainBreath();
      // T2fix3 P2: kill 上一輪 carry-bump delayed tween，避免在新 absorb 的 0.55→0.85 expand 進行中
      // 拉回 opacity=0.55 蓋掉新 flash（race window：animating=false 後 ~1.4s 內再點）
      gsap.killTweensOf('#main-halo-outer');

      // T2fix3: carry-over ≥5 時 outer halo 略亮（CD-T2FIX-4 §E）
      // 不用 Set.intersection（ES2025 ban，ESLint Group 6 守衛）
      const carryCount = [...nextVisible].filter(id => prevVisible.has(id) && id !== slotId).length;
      if (carryCount >= 5 && !window.OpenAver.prefersReducedMotion) {
        gsap.to('#main-halo-outer', { '--main-halo-opacity': 0.65, duration: 0.45, ease: 'fluent-decel', delay: 0.6 });
        gsap.to('#main-halo-outer', { '--main-halo-opacity': 0.55, duration: 0.55, ease: 'fluent', delay: 1.4 });
      }

      // sweep / focused / neighbor rail 殘留清理（避 hover→click race，CD-T2FIX-3 + T2fix5）
      // 清 hover card 殘留（scale / opacity / icon / breathing，Codex T2fix5 P2 Finding 1）
      if (this._activeHoverSlot !== null) {
        this._resetHoverCard(this._activeHoverSlot);
        this._activeHoverSlot = null;
      }
      this._resetHoverRails();
      // 防守性 classList 掃描：清除未追蹤到的殘留（不含 tween kill，無效能疑慮）
      this.visibleSlots.forEach(id => {
        const rl = this.railLines[id];
        if (rl) rl.classList.remove('rail--bright', 'rail--neighbor');
      });

      // T4fix codex round 4 P2-1：kill 上一輪 survivor shimmer 的 untracked strokeOpacity tween
      // shimmer 啟動時 animating 已為 false（slip-through onComplete 內），其 0.14s + 0.24s tween
      // 無 class、無 _activeXxxId 追蹤，_resetHoverRails 不涵蓋。連點時新 click 的
      // railClickedPulse / railDrawOut / railDrawIn 會與舊 shimmer tween 賽跑同一條 strokeOpacity。
      // 把 §I（strokeOpacity reset contract）覆蓋範圍從 hover state 擴大到 shimmer state。
      prevVisible.forEach(id => {
        const line = this.railLines[id];
        if (line) {
          gsap.killTweensOf(line, 'strokeOpacity');
          gsap.set(line, { clearProps: 'strokeOpacity' });
        }
      });

      this.animating = true;

      // 同步清 hover 殘留 tween + 視覺 state（CD-56B-T2 codex P1）
      // 避免 mouseleave 在 slip-through 期間觸發 restore tween 與 exit/fade 打架
      // 56c-T4fix7: filter → --slot-dim-opacity（dim 路徑已改 CSS var）
      this.visibleSlots.forEach(id => {
        const card = this.cards[id];
        if (!card) return;
        gsap.killTweensOf(card, 'scale,opacity,--slot-dim-opacity');
        if (id !== slotId) gsap.set(card, { opacity: 1 });
        // clearProps: 'scale,rotation,--slot-dim-opacity' 確保所有 card 從 scale=1.0/rotation=0/dim=0 起跳
        gsap.set(card, { clearProps: 'scale,rotation,--slot-dim-opacity' });
      });

      // 停止呼吸（slip-through 期間 ticker 不殘留）
      this.breathingManager.stop();

      this._activeTimeline = playSlipThrough(
        slotId,
        prevVisible,
        nextVisible,
        this.cards,
        this.railLines,
        document.getElementById('main-img'),
        () => {
          if (!this._gsapCtx) return; // destroyed during slip-through (Codex T3 P1)
          this._activeTimeline = null;
          this.mainSlot = slotId;
          this.visibleSlots = nextVisible; // 與 animation 使用的批次完全一致
          this.animating = false;
          // slip-through 完成後重啟呼吸（新批 8 顆各自相位）
          if (!window.OpenAver.prefersReducedMotion) {
            this.breathingManager.start(nextVisible);
            // T2fix3: 重啟 main 自呼吸
            this._startMainBreath();
            // T2fix4 預埋：carry-over survivor shimmer（closure 捕獲 prevVisible，不讀 this.visibleSlots）
            const carryIds = [...prevVisible].filter(id => id !== slotId && nextVisible.has(id));
            this._playSurvivorShimmer(carryIds);
            // T5 (CD-T5-5)：slip-through enter rails 補一次 sweep feedback（hover 不再呼叫 sweep，
            // 統一收到 enter feedback 用途）。host onComplete 補呼叫，不改 animations.js 簽名。
            // 重算 enterIds（onCardClick 開頭那次已用於圖片重抽，函式 scope 仍可見，但這裡重算更明確）
            const enterRailIds = [...nextVisible].filter(id => !prevVisible.has(id));
            enterRailIds.forEach(id => {
              if (this.sweepLines[id] && this.railLines[id]) {
                railSweep(this.sweepLines[id], this.railLines[id]);
              }
            });
          }
          // T7 (CD-T7-3)：keystone pulse — 新主圖 landed 隱性節拍（最近 anchor 端 1-2 顆 dust）
          // 必須在 _startIdleAcknowledge 之前呼叫（pulse 是 keystone 事件，timer 從 keystone 後開始計時）
          this._fireKeystonePulse(slotId);
          // T5 (CD-T5-2)：重新排程 idle acknowledge timer（T7 替換為 setTimeout 8-15s）
          // PRM guard 在 _startIdleAcknowledge 首行（PRM 下 timer 不啟動）
          this._startIdleAcknowledge();
        },
        // T4 visual probe：t=0.30 同 frame 切主圖 src（與既有 main fade-out / fade-in 對齊）
        { onMainSwap: () => this._setMainImage(clickedImage) }
      );
    },

    /**
     * onHoverEnter — 滑入 slot 卡片
     * 1. 暫停此顆呼吸
     * 2. scale 1.06 微放大
     * 3. 其餘 visible slots dim 0.5
     * 4. icon overlay 浮現（classList 操作，CSS transition 處理 opacity）
     *
     * @param {string} slotId
     */
    onHoverEnter(slotId) {
      // T6 (CD-T6-4 / spec §2.6 C3)：移除 PRM 短路。
      // PRM 下 state（dust class swap / guide rail set / _activeFocusedRailId 設定）必執行；
      // motion（GSAP tween / breathing pause / scale / dim / neighbor）才條件跳過。
      if (this.animating || !this.visibleSlots.has(slotId)) return;

      const isPRM = window.OpenAver.prefersReducedMotion;

      // 防 enter→enter 直跳殘留（Codex T2fix5 P2 Finding 1）：
      // 若上一張 hover 未 leave 就直接 hover 到新張，先清舊張 card 狀態再進入
      if (this._activeHoverSlot && this._activeHoverSlot !== slotId) {
        this._resetHoverCard(this._activeHoverSlot);
        // T6 (plan §4.3 G)：同步 remove 舊 slotId 的 dust class
        // 不變式：_activeHoverSlot 與 _activeFocusedRailId 在 enter lifecycle 內同步影子（C1 釐清）；
        // 顯式 remove 保險，且讓「enter→enter 邊界」可讀性高
        (this._railStarMap[this._activeHoverSlot] || [])
          .forEach(el => el.classList.remove('in-constellation'));
      }

      // 清 rail state（focused/sweep/neighbor）— T6 內含 focused rail dust class remove + guide rail fadeout
      this._resetHoverRails();

      // T5 (CD-T5-2)：cancel idle acknowledge timer（NO-OP in T5；T7 替換為 clearTimeout）
      // user is interacting → 取消 idle pulse 排程，避免 hover 期間突然 idle pulse 干擾
      this._cancelIdleAcknowledge();

      // T7 (Codex round-3 P2)：hover-pulse race fix — 主動清 corridor 內仍在 pulse 的 dust，
      // 否則 .in-constellation bright twinkle 會被 .dust-pulsing inline opacity 0.95 凍結
      this._abortActiveDustPulses(slotId);

      // ── State 操作（PRM 下也執行，C3 契約）──────────────────────────
      // 1. Dust class swap：corridor 內 dust 切到 .in-constellation bright twinkle
      //    （bright class 走 CSS variable indirection，覆寫 --dust-base，不破壞 inline --dust-base-seed）
      (this._railStarMap[slotId] || []).forEach(el => el.classList.add('in-constellation'));

      // 2. Guide rail 終態（CD-T6-3）：strokeOpacity 0 → 0.10 浮現極淡引導線
      //    T6 不再呼叫 railFocusPulse（後者把 strokeOpacity 拉到 0.85，是 T4fix 能量感脈衝；
      //    T6 是「rail 永遠不是主角」語義 spec §2.4）。ESLint Group 5 守此契約。
      //    Codex review P3-4：plan §C / §6 釘版 stroke-width 1.0px（比 idle baseline 1.5 細，更輕盈）。
      //    inline strokeWidth 蓋過 CSS baseline 1.5；leave 時於 _resetHoverRails clearProps:'strokeWidth'。
      const guideLine = this.railLines[slotId];
      if (guideLine) {
        gsap.killTweensOf(guideLine, 'strokeOpacity,strokeWidth');
        if (isPRM) {
          gsap.set(guideLine, { strokeOpacity: 0.10, strokeWidth: 1.0 });
        } else {
          gsap.set(guideLine, { strokeWidth: 1.0 });
          gsap.to(guideLine, { strokeOpacity: 0.10, duration: 0.25, ease: 'fluent-decel' });
        }
      }

      // 追蹤 focused rail（用於 _resetHoverRails cleanup，CD-T2FIX-6）
      this._activeFocusedRailId = slotId;

      // ── Motion 操作（PRM 下跳過 / 用 gsap.set 同步終態）─────────────
      if (!isPRM) {
        // 1. 暫停此顆呼吸
        this.breathingManager.pauseOne(slotId);

        // 2. Scale up（transformOrigin 確保 hit target 不位移，CD-T2FIX-2）
        gsap.to(this.cards[slotId], { scale: 1.06, duration: 0.18, ease: 'fluent', transformOrigin: '50% 50%' });

        // 3. Dim 其餘 visible slots
        // 56c-T4fix7: 改用 _applyHoverDim 一次性設定 8 卡目標 dim 狀態，
        // 取代 filter brightness 兩段式 race + compositing layer 重建
        this._applyHoverDim(slotId);

        // Neighbor highlight（CD-T2FIX-6 / TASK-T2fix5）
        const neighbors = nearestNeighbors(slotId, [...this.visibleSlots], 3);
        neighbors.forEach(nid => {
          const nline = this.railLines[nid];
          if (nline) {
            // 56c-T4fix7: 改 fromTo 去掉 entry pulse 0.70 瞬閃，消除 set→to 兩段閃感
            gsap.killTweensOf(nline, 'strokeOpacity');
            nline.classList.add('rail--neighbor');
            gsap.fromTo(nline,
              { strokeOpacity: 0 },
              {
                strokeOpacity: 0.55,
                duration: 0.20,
                ease: 'fluent-decel',
                onComplete: () => gsap.set(nline, { clearProps: 'strokeOpacity' }),
              }
            );
          }
        });
        this._activeNeighborRailIds = neighbors;
      } else {
        // PRM：state 同步（scale / dim 用 gsap.set，不 tween）
        if (this.cards[slotId]) gsap.set(this.cards[slotId], { scale: 1.06 });
        // PRM：_applyHoverDim 內 isPRM 分支走 gsap.set
        this._applyHoverDim(slotId);
        // PRM 下不啟動 neighbor pulse（無 tween 可省）；_activeNeighborRailIds 保持空
      }

      // 追蹤當前 hover slot（防 enter→enter 殘留，Codex T2fix5 P2 Finding 1）
      this._activeHoverSlot = slotId;
    },

    /**
     * onHoverLeave — 滑出 slot 卡片
     * 1. 還原 scale 1.0
     * 2. 還原其餘 visible slots opacity 1.0
     * 3. icon overlay 消失
     * 4. 若非 animating 且非 prefers-reduced-motion：恢復此顆呼吸
     *    （animating 期間不 resume，由 slip-through onComplete 的 start() 統一負責）
     *
     * @param {string} slotId
     */
    onHoverLeave(slotId) {
      // T6 (CD-T6-4 / reviewer P2-1)：移除 PRM 短路。
      // PRM 下 onHoverEnter 已加 .in-constellation class，onHoverLeave 必須對稱 remove —
      // 否則 bright dust 永遠殘留（DoD 必 fail）。dust class remove + scale/opacity 還原走
      // _resetHoverRails / _resetHoverCard 統一執行（內部各自有 PRM 分流）。
      //
      // animating guard 保留：animating 期間 onCardClick 已同步清 hover state，restore tween 多餘
      if (this.animating || !this.visibleSlots.has(slotId)) return;

      // Stale guard（Codex T2fix5 P2 Finding 1）：瀏覽器可能延遲送出舊張的 leave 事件，
      // 此時 _activeHoverSlot 已換成新張，忽略延遲 leave 避免清掉新 hover state
      if (this._activeHoverSlot !== slotId) return;

      // 1-4: Restore card scale / opacity / icon / breathing（共用 helper，內部已處理 PRM 分流）
      this._resetHoverCard(slotId);

      // 清 focused rail + dust class + neighbor rails（CD-T2FIX-3 + T2fix5 + T6 整合）
      this._resetHoverRails();

      // 歸零 hover slot 追蹤
      this._activeHoverSlot = null;

      // T7 (CD-T7-2)：hover 結束 → idle 重新計時（user 不再互動，恢復隱性節拍排程）
      // PRM guard 在 _startIdleAcknowledge 首行（PRM 下 timer 不啟動）
      this._startIdleAcknowledge();
    },

    /**
     * onExit — 點擊主圖 / 背景觸發退出動畫
     * Codex T3 P2：原 standalone 模式 location.reload() 不適用 motion-lab tab 場景
     * （會把整頁 reload 回 default search tab）。改為退出動畫完成後本地 reset：
     * 清 visibleSlots / mainSlot，重跑 _playInitialExpand 讓 sandbox 可繼續探索。
     * Codex T3 P1：timeline reference 存 _activeTimeline，destroy 時 kill。
     */
    onExit() {
      if (this.animating) return;
      this.animating = true;

      // T5 (CD-T5-2)：cancel idle acknowledge timer（NO-OP in T5；T7 替換為 clearTimeout）
      this._cancelIdleAcknowledge();
      // T7 (Codex review P2-2)：onExit 同 slip-through 屬「phase transition」，
      // idle acknowledge 強制暫停（spec §5.2）。abort 所有正在跑的 dust pulse tween。
      this._abortAllActiveDustPulses();

      // 清 hover card 殘留（scale / opacity / icon / breathing，Codex T2fix5 P2 Finding 1）
      if (this._activeHoverSlot !== null) {
        this._resetHoverCard(this._activeHoverSlot);
        this._activeHoverSlot = null;
      }
      // 56c-T4fix7: 同步清 --slot-dim-opacity tween 殘留（_resetHoverCard 後仍可能有 overwrite: auto tween）
      this.visibleSlots.forEach(id => {
        const card = this.cards[id];
        if (!card) return;
        gsap.killTweensOf(card, '--slot-dim-opacity');
        gsap.set(card, { clearProps: '--slot-dim-opacity' });
      });
      // 清 hover rails 殘留（退出動畫期間不應殘留 neighbor strokeWidth，CD-T2FIX-6）
      this._resetHoverRails();

      // T2fix3: 停止 main 自呼吸（退出前 scale 強制 reset）
      this._stopMainBreath();

      // 停止呼吸（退出動畫期間 ticker 不殘留）
      this.breathingManager.stop();

      this._activeTimeline = playExit(
        this.cards,
        this.railLines,
        this.visibleSlots,
        document.getElementById('main-img'),
        () => {
          if (!this._gsapCtx) return; // destroyed during exit (Codex T3 P1)
          this._activeTimeline = null;
          // Reset state，重新展開（取代 standalone reload）
          // playExit 把 main-img 設為 opacity:0 / scale:0.95，須還原為初始 visible 1.0
          gsap.set('#main-img', { opacity: 1, scale: 1 });
          this.visibleSlots = new Set();
          this.mainSlot = null;
          this.animating = false;
          // Codex T3 P2 follow-up：上一輪若有 #09-#12 visible，playExit 後仍 opacity:0 但無 slot--hidden，
          // 形成隱形 hover/click 目標。_playInitialExpand 只初始化 #01-#08，需先把 12 個全 reset。
          this._resetAllSlotsToBaseline();
          this._playInitialExpand();
          // T7 (Codex review P2-1): reset expand 後重啟 idle acknowledge timer
          // onExit 開頭呼叫 _cancelIdleAcknowledge() 清掉舊 timer，但 _playInitialExpand 不重啟，
          // 導致用戶 exit 一次後 idle pulses 在該 remount session 內停止（直到下次 slip-through / hover leave）。
          // 此處 mirror init() 的「expand 前啟動 timer」順序（init 在 L99 _startIdleAcknowledge → L107 _playInitialExpand）。
          // PRM guard 在 _startIdleAcknowledge 首行（PRM 下 timer 不啟動）。
          this._startIdleAcknowledge();
        }
      );
    },

    /**
     * _startMainBreath — main 圖自呼吸（scale 1→1.018，5.6s sine.inOut yoyo）
     * reduced-motion guard：prefersReducedMotion 時直接 return，不建 tween
     */
    _startMainBreath() {
      if (window.OpenAver.prefersReducedMotion) return;
      this._mainBreathTween = gsap.to('#main-img', {
        scale: 1.018,
        duration: 5.6,
        ease: 'sine.inOut',
        yoyo: true,
        repeat: -1,
      });
    },

    /**
     * _stopMainBreath — kill main 呼吸 tween + 強制 reset scale=1
     * gsap.set 強制歸位：kill 不自動 reset，yoyo 中段被 kill 會殘留 scale
     */
    _stopMainBreath() {
      if (this._mainBreathTween) {
        this._mainBreathTween.kill();
        this._mainBreathTween = null;
      }
      gsap.set('#main-img', { scale: 1 });
    },

    /**
     * _playSurvivorShimmer — carry-over 卡片 glow 雙脈衝 + rail strokeOpacity 短脈衝
     *
     * 每張 carry-over card：`--card-glow-opacity` 0→0.85（0.25s）→0（0.40s）。
     * 每條 rail line（T4fix §C state model，shimmer peak 0.50）：
     *   strokeOpacity 0.30→0.50（0.14s）→0.30（0.24s）→ clearProps（CSS baseline 接管）
     * 連點時先 killTweensOf 清掉前一輪 pending tween，避免 `--card-glow-opacity` 殘留。
     * reduced-motion：no-op。
     *
     * @param {string[]} carryIds
     */
    _playSurvivorShimmer(carryIds) {
      if (window.OpenAver.prefersReducedMotion) return;
      carryIds.forEach(id => {
        const card = this.cards[id];
        const line = this.railLines[id];
        if (card) {
          gsap.killTweensOf(card, '--card-glow-opacity');
          gsap.to(card, { '--card-glow-opacity': 0.85, duration: 0.25, ease: 'fluent-decel' });
          gsap.to(card, { '--card-glow-opacity': 0, duration: 0.40, ease: 'fluent', delay: 0.25 });
        }
        if (line) {
          // T4fix：rail shimmer 走 strokeOpacity（§C state model peak 0.50），無 class，純脈衝後 clearProps
          gsap.killTweensOf(line, 'strokeOpacity');
          gsap.to(line, { strokeOpacity: 0.50, duration: 0.14, ease: 'fluent' });
          gsap.to(line, {
            strokeOpacity: 0.30,
            duration: 0.24,
            ease: 'fluent',
            delay: 0.14,
            onComplete: () => gsap.set(line, { clearProps: 'strokeOpacity' }),
          });
        }
      });
    },

    /**
     * _resetHoverCard — hover card 視覺還原 helper（Codex T2fix5 P2 Finding 1）
     * 還原指定 slot 的 card scale / 其餘卡片 opacity / icon overlay / breathing。
     * 供 onHoverLeave、onHoverEnter（enter→enter）、onCardClick、onExit 共用。
     * reduced-motion 下：用 gsap.set 同步歸位（不 tween），接受邊緣不處理。
     *
     * 不負責：rail 清理（由 _resetHoverRails 負責）、_activeHoverSlot 歸零（由呼叫方負責）
     *
     * @param {string} slotId
     */
    _resetHoverCard(slotId) {
      const card = this.cards[slotId];
      const useSet = window.OpenAver.prefersReducedMotion;

      // 1. Restore scale
      if (card) {
        if (useSet) {
          gsap.set(card, { scale: 1.0 });
        } else {
          gsap.to(card, { scale: 1.0, duration: 0.18, ease: 'fluent' });
        }
      }

      // 2. 還原 8 卡 --slot-dim-opacity → 0
      // 56c-T4fix7: 移除 filter brightness 路徑，改呼叫 _resetHoverDim
      this._resetHoverDim();

      // 3. 恢復呼吸（animating 期間跳過，由 slip-through onComplete 統一處理）
      if (!this.animating && !window.OpenAver.prefersReducedMotion) {
        this.breathingManager.resumeOne(slotId);
      }
    },

    /**
     * 56c-T4fix7: _applyHoverDim — 一次性設定 8 卡目標 dim 狀態
     * 取代 filter brightness 兩段式 race，消除 enter→enter 亮閃。
     * activeSlotId：hover 中的卡（dim=0）；其餘 7 卡 dim=1。
     * activeSlotId === null：reset 全還原（8 卡全部 dim=0），由 _resetHoverDim 呼叫。
     * overwrite: 'auto' 自動 stomp 前一輪同 property tween（取代 killTweensOf）。
     */
    _applyHoverDim(activeSlotId) {
      const isPRM = window.OpenAver.prefersReducedMotion;
      this.visibleSlots.forEach(id => {
        const card = this.cards[id];
        if (!card) return;
        const target = activeSlotId === null ? 0 : (id === activeSlotId ? 0 : 1);
        if (isPRM) {
          gsap.set(card, { '--slot-dim-opacity': target });
        } else {
          gsap.to(card, {
            '--slot-dim-opacity': target,
            duration: 0.20,
            ease: 'fluent',
            overwrite: 'auto',
          });
        }
      });
    },

    /**
     * 56c-T4fix7: _resetHoverDim — hover leave 全還原（8 卡 dim → 0）
     * 對稱 _applyHoverDim，由 _resetHoverCard 呼叫。
     */
    _resetHoverDim() {
      this._applyHoverDim(null);
    },

    /**
     * _resetHoverRails — hover 清理 helper（CD-T2FIX-6 / TASK-T2fix5）
     * 整合 T2fix2/3 既有 focused rail / sweep 清理 + 新增 neighbor 清理
     *
     * 不接觸：#main-img、halo DOM、breathingManager、animating flag
     */
    /**
     * _resetAllSlotsToBaseline — 把 12 個 slot / rail / sweep 全部回到「init 前」baseline
     * Codex T3 P2 follow-up：onExit 後若上一輪 visibleSlots 含 #09-#12，這些 slot 在 playExit
     * 結束後會留下 opacity:0 但無 .slot--hidden，pointer-events 仍 active；rail 同理。
     * _playInitialExpand 只初始化 #01-#08，碰不到 #09-#12 殘留 → 產生隱形 hover/click 目標。
     * 本 helper 與 init() 開頭的 DOM 建立段落同義（card 居中 + 全 hidden / rail+sweep hidden）。
     */
    _resetAllSlotsToBaseline() {
      ANCHORS.forEach(a => {
        const card = this.cards[a.id];
        const line = this.railLines[a.id];
        const sweep = this.sweepLines[a.id];
        if (card) {
          gsap.killTweensOf(card);
          card.classList.add('slot--hidden');
          card.classList.remove('rail--bright', 'rail--neighbor'); // 防呆（class 應掛 rail，不會在 card；但保險清）
          gsap.set(card, {
            left: 480,
            top: 310,
            width: 107,   // = round(150 * poster-crop 0.71)；NC#7 同步 animations.js POSTER_CROP_RATIO + CSS --poster-crop-ratio（reset baseline，繞過 animations.js gsap.set）
            height: 150,
            opacity: 0,
            zIndex: '',
            // 56c-T4fix7: 移除 filter，加 --slot-dim-opacity（C26 精確列表）
            clearProps: 'scale,rotation,transform,--card-glow-opacity,--slot-dim-opacity',
          });
        }
        if (line) {
          gsap.killTweensOf(line);
          line.classList.add('rail--hidden');
          line.classList.remove('rail--bright', 'rail--neighbor');
          // T4fix §I：strokeOpacity inline 必清，由 CSS .clip-lab-rail baseline (0.30) 接管
          // Codex review P3-4：strokeWidth inline 同清，回到 CSS baseline 1.5
          gsap.set(line, { opacity: 0, clearProps: 'strokeOpacity,strokeWidth' });
        }
        if (sweep) resetSweepLine(sweep);
      });
      this._activeFocusedRailId = null;
      this._activeNeighborRailIds = [];
    },

    _resetHoverRails() {
      // T4fix §I：所有 rail strokeOpacity inline 必清，由 CSS baseline (0) 或
      // 殘留 class 接管；class 在 leave 時一併移除，回到 baseline
      // T6 (CD-T6-3 / CD-T6-5 / plan §4.3 F)：guide rail strokeOpacity fade-out tween（避瞬切）
      //   + dust class remove（focused rail corridor 內所有 dust 還原 idle）
      if (this._activeFocusedRailId) {
        const focusedId = this._activeFocusedRailId;
        const line = this.railLines[focusedId];
        if (line) {
          gsap.killTweensOf(line, 'strokeOpacity,opacity,strokeWidth');
          line.classList.remove('rail--bright');   // 防呆保留（T6 不 add rail--bright）
          // T6: fade-out（leave 比 enter 0.25s 略快，乾淨）
          // PRM 路徑（C3 契約 / spec §2.6 C3）：「不播 tween、不註冊 ticker、不觸發 GSAP transition」，
          //   仍同步執行 state（strokeOpacity 直接落 0 + clearProps 接 CSS baseline 0）。
          // non-PRM：0.20s fluent-accel tween，結束後 clearProps。
          // Codex review P3-4：onHoverEnter 把 strokeWidth set 1.0（plan §C），此處 clearProps 還
          // CSS baseline 1.5。strokeWidth 不 tween（idle baseline 變化會擾動視線，per plan §C 設計）。
          if (window.OpenAver.prefersReducedMotion) {
            gsap.set(line, { strokeOpacity: 0, clearProps: 'strokeOpacity,strokeWidth' });
          } else {
            gsap.set(line, { clearProps: 'strokeWidth' });
            gsap.to(line, {
              strokeOpacity: 0,
              duration: 0.20,
              ease: 'fluent-accel',
              onComplete: () => gsap.set(line, { clearProps: 'strokeOpacity' }),
            });
          }
        }
        const sw = this.sweepLines[focusedId];
        if (sw) resetSweepLine(sw);

        // T6 (CD-T6-5)：dust class remove（focused rail corridor 內所有 dust 還原 idle twinkle）
        (this._railStarMap[focusedId] || [])
          .forEach(el => el.classList.remove('in-constellation'));

        this._activeFocusedRailId = null;
      }
      // 清 neighbor rails
      this._activeNeighborRailIds.forEach(nid => {
        const nline = this.railLines[nid];
        if (nline) {
          gsap.killTweensOf(nline, 'strokeOpacity');
          nline.classList.remove('rail--neighbor');
          gsap.set(nline, { clearProps: 'strokeOpacity' });
        }
      });
      this._activeNeighborRailIds = [];
    },
  }));
});
