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

    // Phase 50.2.0: 註冊 Fluent CustomEase（charter §5 三角色）
    // 同步 guarded register — base.html defer 順序保證 CustomEase plugin 已載入
    if (typeof CustomEase !== 'undefined') {
        CustomEase.create('fluent',       '0.33, 0, 0.67, 1');
        CustomEase.create('fluent-decel', '0, 0, 0, 1');
        CustomEase.create('fluent-accel', '1, 0, 1, 1');
    } else {
        console.warn('[motion-adapter] CustomEase plugin missing, fluent eases not registered');
    }

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
            opts = opts || {};
            if (!this._shouldAnimate()) {
                if (typeof opts.onComplete === 'function') opts.onComplete();
                return null;
            }
            return this._run(opts.ctx, function () {
                return gsap.from(elements, {
                    y: opts.y !== undefined ? opts.y : 20,
                    opacity: 0,
                    duration: opts.duration || 0.5,
                    stagger: opts.stagger || 0,
                    ease: opts.ease || 'fluent-decel',
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
                    duration: opts.duration || 0.3,
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
                    duration: opts.duration || 0.6,
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
         */
        playFadeTo: function (elements, opts) {
            opts = opts || {};
            var targetOpacity = opts.opacity !== undefined ? opts.opacity : 1;
            if (!this._shouldAnimate()) {
                gsap.set(elements, { opacity: targetOpacity });
                if (typeof opts.onComplete === 'function') opts.onComplete();
                return null;
            }
            return this._run(opts.ctx, function () {
                return gsap.to(elements, {
                    opacity: targetOpacity,
                    duration: opts.duration || 0.3,
                    ease: opts.ease || 'fluent',
                    onComplete: opts.onComplete || null
                });
            });
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
                    duration: opts.duration || 0.25,
                    ease: opts.ease || 'fluent-decel',
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
