/**
 * Motion Adapter — 共用 GSAP 封裝
 *
 * 規則：
 *   1. 頁面不直接寫 gsap.to() — 一律透過 adapter
 *   2. play* 建立的動畫自動歸入 context 管理（頁面離開時 revert）
 *   3. reduced-motion 開啟 → timeScale(0) 暫停；關閉 → timeScale(1) 恢復
 */
window.OpenAver = window.OpenAver || {};

// Phase 50.2.0: 註冊 Fluent CustomEase（charter §5 三角色）
// 同步 guarded register — base.html defer 順序保證 CustomEase plugin 已載入
// 必須先 gsap.registerPlugin(CustomEase) 後再 create，否則 ease 不會進入 gsap.parseEase 的查表，
// 導致 'fluent' / 'fluent-decel' / 'fluent-accel' 在純依賴 motion-adapter 的頁面（如 motion-lab）
// 全 fallback 為線性 ease，視覺差異消失。
if (typeof CustomEase !== 'undefined') {
if (typeof gsap !== 'undefined' && typeof gsap.registerPlugin === 'function') {
    gsap.registerPlugin(CustomEase);
}
CustomEase.create('fluent',       '0.33, 0, 0.67, 1');
CustomEase.create('fluent-decel', '0, 0, 0, 1');
CustomEase.create('fluent-accel', '1, 0, 1, 1');
} else {
console.warn('[motion-adapter] CustomEase plugin missing, fluent eases not registered');
}

var motion = {

/** 移除替身上的 Alpine 指令與 template，避免再次初始化。 */
stripAlpine: function (root) {
    if (!root) return;
    root.querySelectorAll('template').forEach(function (el) { el.remove(); });
    [root].concat(Array.from(root.querySelectorAll('*'))).forEach(function (el) {
        Array.from(el.attributes).forEach(function (attr) {
            if (/^(x-|:|@)/.test(attr.name)) el.removeAttribute(attr.name);
        });
    });
},

/**
 * Phase 50.2.9: GSAP Duration 三角色常數（charter §5，CD-7 命名避讓既有 slow:300ms）
 *
 * 對應 input.css :root --fluent-duration-{fast,medium,emphasis}
 * 業務 GSAP duration 透過 OpenAver.motion.DURATION.fast/medium/emphasis 讀取
 * （不引入 ES module，沿用既有 IIFE / window.OpenAver pattern — CD-1）
 */
DURATION: {
    fast:     0.167,   // 微互動、hover、color/opacity 過場
    medium:   0.333,   // 中等過場（panel 展開、tag 拉開）
    emphasis: 0.5      // 強調級長過場（lightbox 主動畫、模式切換）
},

WALL_MOTION: {
    // 收合 origin／展開 stagger 兩個 key 不再保留以免誤當可調。
    STAGGER_ORIGIN:              'center',
    ENTRY_STAGGER_AMOUNT:        0.2,
    FILTER_ENTER_STAGGER_AMOUNT: 0.133,
    INFO_EXPAND_DURATION:        0.133
},

/**
 * 建立頁面級動畫 context
 *
 * 用法：Alpine init() 建立，頁面離開自動清理
 *   init() {
 *       this._gsapCtx = OpenAver.motion.createContext(this.$el);
 *   }
 *
 * 之後呼叫 play* 時傳入 ctx：
 *   OpenAver.motion.playEnter(els, { ctx: this._gsapCtx });
 */
createContext: function (containerEl) {
    var ctx = gsap.context(function () {}, containerEl);

    // SSR 全頁重載自動 GC，加 beforeunload 作為安全網
    var cleanup = function () { ctx.revert(); };
    window.addEventListener('beforeunload', cleanup);

    // 擴充 revert — 同時移除 listener
    var origRevert = ctx.revert.bind(ctx);
    ctx.revert = function () {
        window.removeEventListener('beforeunload', cleanup);
        origRevert();
    };

    return ctx;
},

/** 進場動畫（通用淡入上移） */
playEnter: function (elements, opts) {
    opts = opts || {};
    if (!this._shouldAnimate()) {
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    return this._run(opts.ctx, function () {
        return gsap.from(elements, {
            y: opts.y !== undefined ? opts.y : 20,
            opacity: 0,
            duration: opts.duration || motion.DURATION.emphasis,
            stagger: opts.stagger || 0,
            ease: opts.ease || 'fluent-decel',
            overwrite: opts.overwrite,
            onComplete: opts.onComplete || null
        });
    });
},

/** 離場動畫 */
playLeave: function (elements, opts) {
    opts = opts || {};
    if (!this._shouldAnimate()) {
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    return this._run(opts.ctx, function () {
        return gsap.to(elements, {
            y: opts.y !== undefined ? opts.y : -10,
            opacity: 0,
            duration: opts.duration || motion.DURATION.medium,
            ease: opts.ease || 'fluent-accel',
            onComplete: opts.onComplete || null
        });
    });
},

/** Stagger 序列進場（Gallery 卡片等） */
playStagger: function (elements, opts) {
    opts = opts || {};
    if (!this._shouldAnimate()) {
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    return this._run(opts.ctx, function () {
        return gsap.from(elements, {
            y: opts.y !== undefined ? opts.y : 30,
            opacity: 0,
            stagger: opts.stagger || 0.08,
            duration: opts.duration || motion.DURATION.emphasis,
            ease: opts.ease || 'fluent-decel',
            onComplete: opts.onComplete || null
        });
    });
},

/**
 * 透明度補間（fade-to）
 *
 * 用法：OpenAver.motion.playFadeTo(elements, { opacity: 0, duration: 0.2, ease: 'fluent' })
 * 若 reduced-motion 啟用則直接設定最終值不播動畫。
 * `fromOpacity`（TASK-156d-T3）：只在會播動畫時（`_shouldAnimate()===true`）於建立
 * tween 之前同步 `gsap.set(elements,{opacity:fromOpacity})` 一次，讓呼叫端能表達
 * 「先跳到起始值再淡入」；reduced-motion 時忽略，直接落到目標值（不播中間態）。
 */
playFadeTo: function (elements, opts) {
    opts = opts || {};
    var targetOpacity = opts.opacity !== undefined ? opts.opacity : 1;
    if (!this._shouldAnimate()) {
        gsap.set(elements, { opacity: targetOpacity });
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    if (opts.fromOpacity !== undefined) {
        gsap.set(elements, { opacity: opts.fromOpacity });
    }
    return this._run(opts.ctx, function () {
        return gsap.to(elements, {
            opacity: targetOpacity,
            duration: opts.duration || motion.DURATION.medium,
            ease: opts.ease || 'fluent',
            overwrite: opts.overwrite,
            onComplete: opts.onComplete || null
        });
    });
},

/**
 * 中斷指定元素上所有進行中的 GSAP tween（薄包 `gsap.killTweensOf`）。
 * TASK-156d-T3／CD-156d-2 步驟 4：快速連續觸發焦點切換時，頁面呼叫這支
 * （不直接呼叫 `gsap.killTweensOf`——承接事實 #13）清掉上一輪未播完的動畫，
 * 再重新從頭開始這一輪的淡出淡入序列。
 * @param {Element|Element[]|string} targets
 */
killTweens: function (targets) {
    if (typeof gsap === 'undefined' || !targets) return;
    gsap.killTweensOf(targets);
},

/** Modal 彈出動畫 */
playModal: function (element, opts) {
    opts = opts || {};
    if (!this._shouldAnimate()) {
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    return this._run(opts.ctx, function () {
        return gsap.from(element, {
            scale: 0.95,
            opacity: 0,
            duration: opts.duration || motion.DURATION.fast,
            ease: opts.ease || 'fluent-decel',
            onComplete: opts.onComplete || null
        });
    });
},

/**
 * 一次性強調亮起（她那列被置頂到第一列時的提示動效）
 *
 * TASK-156d-T4／CD-156d-3：一次性 `backgroundColor` 淡出強調，提示「在這裡」；
 * 純裝飾性，不影響 `.is-active` 既有、會持續套用的高亮 class。PRM 開啟時
 * `_shouldAnimate()===false` → 直接不播放，不需要任何 `gsap.set` 收尾。
 * 色票沿用既有「`fromTo(backgroundColor)` → `transparent` → `clearProps`」樣板
 * （`web/static/js/pages/search/animations.js` `playOrganizeSuccess` 的 row flash）：
 * GSAP 內建顏色解析只認 hex/rgb/rgba/hsl，不認得 `--color-primary` 實際使用的
 * `oklch()`／`color-mix()`，故用固定 rgba literal 而非 CSS 變數。
 *
 * @param {Element} element - 要強調亮起的那一列 DOM 元素
 * @param {Object} [opts]
 * @param {number} [opts.duration=0.4] - 動畫秒數（CD-156d-3：<=0.4s）
 * @param {string} [opts.color] - 起始強調色（預設克制藍，淡出至 transparent）
 * @param {string} [opts.ease='fluent']
 * @param {Object} [opts.ctx] - createContext() 回傳的 context，供頁面離開時回收
 * @param {Function} [opts.onComplete]
 */
playPulse: function (element, opts) {
    opts = opts || {};
    if (!element) return null;
    if (!this._shouldAnimate()) {
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    var fromColor = opts.color || 'rgba(96, 165, 250, 0.28)';
    return this._run(opts.ctx, function () {
        return gsap.fromTo(element,
            { backgroundColor: fromColor },
            {
                backgroundColor: 'transparent',
                duration: opts.duration || 0.4,
                ease: opts.ease || 'fluent',
                clearProps: 'backgroundColor',
                onComplete: opts.onComplete || null
            }
        );
    });
},

/**
 * 頒獎台進場動效：每個名次一組，台座＋該名次的頭像/名字/片數同時起步、依名次順序 stagger。
 * groups 陣列順序＝視覺順序（2→1→3），由呼叫端保證。
 * @param {Array<{stand: Element, items?: Element[]}>} groups - 名次組清單
 * @param {Object} [opts]
 * @param {number} [opts.duration=0.28] - 單組動畫秒數
 * @param {number} [opts.stagger=0.08] - 組間錯開秒數
 * @param {string} [opts.ease='fluent-decel']
 * @param {Object} [opts.ctx] - createContext() 回傳的 context，供頁面離開時回收
 * @param {Function} [opts.onComplete]
 */
playRise: function (groups, opts) {
    opts = opts || {};
    var list = groups && groups.length ? groups : [];
    if (!list.length) return null;
    var stands = list.map(function (g) { return g.stand; }).filter(Boolean);
    var items = [];
    list.forEach(function (g) {
        (g.items || []).forEach(function (el) { if (el) items.push(el); });
    });
    var duration = opts.duration !== undefined ? opts.duration : 0.28;
    var stagger = opts.stagger !== undefined ? opts.stagger : 0.08;
    var ease = opts.ease || 'fluent-decel';
    if (!this._shouldAnimate()) {
        gsap.set(stands, { clearProps: 'transform,transformOrigin' });
        gsap.set(items, { clearProps: 'transform,opacity' });
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    return this._run(opts.ctx, function () {
        var tl = gsap.timeline({ onComplete: opts.onComplete || null });
        list.forEach(function (g, i) {
            var startTime = i * stagger;
            if (g.stand) {
                tl.fromTo(g.stand, { scaleY: 0 }, {
                    scaleY: 1,
                    duration: duration,
                    transformOrigin: 'bottom',
                    ease: ease,
                    clearProps: 'transform,transformOrigin'
                }, startTime);
            }
            if (g.items && g.items.length) {
                tl.fromTo(g.items, { opacity: 0, y: 8 }, {
                    opacity: 1,
                    y: 0,
                    duration: duration,
                    ease: ease,
                    clearProps: 'transform,opacity'
                }, startTime);
            }
        });
        return tl;
    });
},

/**
 * 清除元素 inline GSAP props（替代直接呼叫 `gsap.set(el, { clearProps })`）。
 * 用於 timeline.kill() 後同步重置 transform/opacity 等殘留，防連點 stutter。
 * 不觸發動畫，純 sync prop 重置。
 * @param {Element} element
 * @param {string} props - GSAP clearProps 字串（如 'transform,opacity'）
 */
clearProps: function (element, props) {
    if (!element || typeof gsap === 'undefined') return;
    gsap.set(element, { clearProps: props });
},

/**
 * GSAP Flip 狀態捕捉（薄包 `Flip.getState`）。
 * TASK-156e-T1a／CD-156e-1：頁面不直接呼叫 `Flip.getState`，一律經由此 primitive。
 * `kill:true` 是 GSAP 官方預設，呼叫端不必手動傳。
 * @param {Element|Element[]|string} targets
 * @returns {*} Flip state（供後續 `flipFrom` 使用）
 */
flipCapture: function (targets) {
    if (typeof Flip === 'undefined' || !targets) return null;
    if (!this._shouldAnimate()) return null;
    return Flip.getState(targets);
},

/**
 * GSAP Flip 動畫播放（薄包 `Flip.from`）。
 * TASK-156e-T1a／CD-156e-1：`opts` 原樣透傳（`absolute`／`fade`／`nested`／
 * `duration`／`targets` 等由呼叫端決定）。PRM 開啟時跳過動畫並觸發 `onComplete`。
 * @param {*} state - `flipCapture` 回傳的 Flip state
 * @param {Object} [opts]
 * @returns {*} Flip timeline，或 PRM 時 `null`
 */
flipFrom: function (state, opts) {
    opts = opts || {};
    if (typeof Flip === 'undefined') return null;
    if (!state || !this._shouldAnimate()) {
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    return Flip.from(state, opts);
},

/**
 * 數值補間（count-up／count-down）。
 * TASK-156e-T3／CD-156e-6：`(opts)` shape（目標是 JS 數值，不是 DOM 元素）。
 * PRM 或 from===to 時同步呼叫一次 onUpdate(to)+onComplete() 後回傳 null。
 * `snap:{v:1}` 確保 onUpdate 收到的永遠是整數。
 * @param {Object} [opts]
 * @param {number} opts.from
 * @param {number} opts.to
 * @param {number} [opts.duration]
 * @param {string} [opts.ease]
 * @param {Function} [opts.onUpdate]
 * @param {Function} [opts.onComplete]
 * @param {Object} [opts.ctx]
 * @returns {*} GSAP tween，或 PRM／相等時 `null`
 */
playCountUp: function (opts) {
    opts = opts || {};
    var from = opts.from, to = opts.to;
    if (!this._shouldAnimate() || from === to) {
        if (typeof opts.onUpdate === 'function') opts.onUpdate(to);
        if (typeof opts.onComplete === 'function') opts.onComplete();
        return null;
    }
    var obj = { v: from };
    return this._run(opts.ctx, function () {
        return gsap.to(obj, {
            v: to,
            duration: opts.duration || motion.DURATION.medium,
            ease: opts.ease || 'fluent',
            snap: { v: 1 },
            onUpdate: function () {
                if (typeof opts.onUpdate === 'function') opts.onUpdate(Math.round(obj.v));
            },
            onComplete: opts.onComplete || null,
        });
    });
},

/**
 * @private 在 context 內執行動畫（確保 ctx.revert() 能回收）
 * 如果沒傳 ctx，動畫仍會播放，只是不受 context 管理
 */
_run: function (ctx, fn) {
    if (ctx) {
        var tween;
        ctx.add(function () { tween = fn(); });
        return tween;
    }
    return fn();
},

/** @private reduced-motion 檢查 */
_shouldAnimate: function () {
    return !window.OpenAver.prefersReducedMotion;
}
};

// reduced-motion 變化 → 暫停/恢復（可逆，不刪除動畫）
window.addEventListener('openaver:motion-pref-change', function (e) {
gsap.globalTimeline.timeScale(e.detail.reducedMotion ? 0 : 1);
});

window.OpenAver.motion = motion;
