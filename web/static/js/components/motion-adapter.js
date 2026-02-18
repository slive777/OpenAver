/**
 * Motion Adapter — 共用 GSAP 封裝
 *
 * 規則：
 *   1. 頁面不直接寫 gsap.to() — 一律透過 adapter
 *   2. play* 建立的動畫自動歸入 context 管理（頁面離開時 revert）
 *   3. reduced-motion 開啟 → timeScale(0) 暫停；關閉 → timeScale(1) 恢復
 */
(function () {
    window.OpenAver = window.OpenAver || {};

    var motion = {

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
            if (!this._shouldAnimate()) return null;
            opts = opts || {};
            return this._run(opts.ctx, function () {
                return gsap.from(elements, {
                    y: opts.y !== undefined ? opts.y : 20,
                    opacity: 0,
                    duration: opts.duration || 0.5,
                    stagger: opts.stagger || 0,
                    ease: opts.ease || 'power3.out',
                    onComplete: opts.onComplete || null
                });
            });
        },

        /** 離場動畫 */
        playLeave: function (elements, opts) {
            if (!this._shouldAnimate()) return null;
            opts = opts || {};
            return this._run(opts.ctx, function () {
                return gsap.to(elements, {
                    y: opts.y !== undefined ? opts.y : -10,
                    opacity: 0,
                    duration: opts.duration || 0.3,
                    ease: opts.ease || 'power2.in',
                    onComplete: opts.onComplete || null
                });
            });
        },

        /** Stagger 序列進場（Gallery 卡片等） */
        playStagger: function (elements, opts) {
            if (!this._shouldAnimate()) return null;
            opts = opts || {};
            return this._run(opts.ctx, function () {
                return gsap.from(elements, {
                    y: opts.y !== undefined ? opts.y : 30,
                    opacity: 0,
                    stagger: opts.stagger || 0.08,
                    duration: opts.duration || 0.6,
                    ease: opts.ease || 'power3.out',
                    onComplete: opts.onComplete || null
                });
            });
        },

        /** Modal 彈出動畫 */
        playModal: function (element, opts) {
            if (!this._shouldAnimate()) return null;
            opts = opts || {};
            return this._run(opts.ctx, function () {
                return gsap.from(element, {
                    scale: 0.95,
                    opacity: 0,
                    duration: opts.duration || 0.25,
                    ease: opts.ease || 'power2.out',
                    onComplete: opts.onComplete || null
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
})();
