/**
 * ShowcaseAnimations — /showcase 頁面動畫模組
 *
 * 暴露 window.ShowcaseAnimations 物件，提供：
 *   - playEntry(gridEl, params)                B6: 初始載入進場動畫
 *   - playFlipReorder(gridEl, params)           B7: 排序洗牌 Flip 動畫
 *   - playFlipFilter(gridEl, state, params)     B8: 篩選進出場 Flip 動畫
 *   - captureFlipState(gridEl)                  B8: 捕獲 Flip 狀態快照
 *   - playPageOut(gridEl, direction, params)    B9: 分頁離場動畫
 *   - playPageIn(gridEl, direction, params)     B9: 分頁進場動畫
 *   - playModeCrossfade(outEl, inEl, params)    B10: 模式切換 crossfade
 *
 * B5 骨架：所有方法為 placeholder，return null。
 * B6-B10 逐步填入實作。
 *
 * Graceful fallback：若 GSAP 未載入，所有方法安全降級（不拋錯）。
 * core.js 透過 window.ShowcaseAnimations?.playEntry?.()
 * optional chaining 呼叫，確保此模組未載入時功能完全正常。
 */
(function () {
    'use strict';

    /**
     * 判斷是否應跳過動畫（Reduced Motion 降級）
     * @returns {boolean}
     */
    function shouldSkip() {
        return !!(window.OpenAver?.prefersReducedMotion);
    }

    // B5: 註冊 Flip plugin + CustomEase（base.html 已載入 CDN）
    document.addEventListener('DOMContentLoaded', function () {
        if (typeof gsap !== 'undefined' && typeof Flip !== 'undefined') {
            gsap.registerPlugin(Flip);
        }
        if (typeof CustomEase !== 'undefined') {
            try {
                if (typeof gsap !== 'undefined') {
                    gsap.registerPlugin(CustomEase);
                }
                CustomEase.create("showcaseSettle", "M0,0 C0.14,0 0.27,0.87 0.5,1 0.75,1 0.86,0.98 1,1");
            } catch (e) {
                // showcaseSettle ease 註冊失敗時動畫會 fallback 到 power2.out
            }
        }
    });

    /**
     * ShowcaseAnimations 物件 — B6-B10 逐步實作
     * 目前所有方法為 placeholder，return null
     */
    var ShowcaseAnimations = {
        /**
         * B6: 初始載入進場動畫
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {Object} params - 動畫參數
         * @returns {null}
         */
        playEntry: function (gridEl, params) {
            params = params || {};

            // null guard
            if (!gridEl) return null;

            // GSAP guard（CDN 故障降級）
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            // Reduced Motion 降級：瞬間顯示
            if (shouldSkip()) {
                gsap.set(cards, { opacity: 1, y: 0, scale: 1 });
                return null;
            }

            var dur = params.duration || 0.5;
            var staggerVal = params.stagger || 0.04;
            var ease = params.easing || 'power3.out';

            // Viewport 分流：fold 以下卡片瞬間顯示
            var viewportH = window.innerHeight;
            var visible = [];
            var offscreen = [];
            Array.from(cards).forEach(function (card) {
                if (card.getBoundingClientRect().top < viewportH) {
                    visible.push(card);
                } else {
                    offscreen.push(card);
                }
            });

            if (offscreen.length) {
                gsap.set(offscreen, { opacity: 1, y: 0, scale: 1 });
            }

            if (!visible.length) return null;

            // 設定初始狀態
            var fromVars = { opacity: 0, y: 20 };
            gsap.set(visible, fromVars);

            var tl = gsap.timeline({ id: 'showcaseEntry' });
            tl.to(visible, { opacity: 1, y: 0, duration: dur, ease: ease, stagger: staggerVal });

            // 動畫結束後清除 inline styles
            tl.eventCallback('onComplete', function () {
                gsap.set(visible, { clearProps: 'transform,opacity' });
            });

            return tl;
        },

        /**
         * B7: 排序洗牌 Flip 動畫
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {Object} state - captureFlipState 回傳的 Flip 狀態快照
         * @param {Object} params - 動畫參數
         * @returns {Flip|null}
         */
        playFlipReorder: function (gridEl, state, params) {
            params = params || {};

            // null guard
            if (!gridEl || !state) return null;

            // Flip guard
            if (typeof Flip === 'undefined' || typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // Reduced Motion 降級：Alpine 已完成 DOM 更新，不需額外處理
            if (shouldSkip()) return null;

            // C18: 中斷進行中的 Flip 動畫
            Flip.killFlipsOf(cards);

            var dur = params.duration || 0.5;
            var ease = params.ease || 'power2.inOut';

            // Flip.from — 從舊位置動畫到新位置
            return Flip.from(state, {
                duration: dur,
                ease: ease,
                absolute: true,
                prune: true,
                simple: true,
                onComplete: function () {
                    gsap.set(cards, { clearProps: 'transform' });
                }
            });
        },

        /**
         * B8: 篩選進出場 Flip 動畫
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {Object} state - Flip 狀態快照
         * @param {Object} params - 動畫參數
         * @returns {null}
         */
        playFlipFilter: function (gridEl, state, params) {
            params = params || {};

            // null guard
            if (!gridEl || !state) return null;

            // Flip guard
            if (typeof Flip === 'undefined' || typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // Reduced Motion 降級：Alpine 已完成 DOM 更新，不需額外處理
            if (shouldSkip()) return null;

            // C18: 中斷進行中的 Flip 動畫
            Flip.killFlipsOf(cards);

            var dur = params.duration || 0.4;

            // Flip.from — 含 onEnter/onLeave 進出場回調
            return Flip.from(state, {
                duration: dur,
                ease: 'power2.inOut',
                absolute: true,
                prune: true,
                simple: true,
                onEnter: function (els) {
                    gsap.fromTo(els,
                        { opacity: 0, scale: 0.85 },
                        { opacity: 1, scale: 1, duration: dur * 0.8, ease: 'power2.out' }
                    );
                },
                onLeave: function (els) {
                    gsap.to(els, { opacity: 0, scale: 0.85, duration: dur * 0.6, ease: 'power2.in' });
                },
                onComplete: function () {
                    gsap.set(cards, { clearProps: 'transform' });
                }
            });
        },

        /**
         * B7/B8: 捕獲 Flip 狀態快照
         * @param {Element} gridEl - .showcase-grid 容器
         * @returns {Object|null} Flip state 物件
         */
        captureFlipState: function (gridEl) {
            // null guard
            if (!gridEl) return null;

            // Flip guard
            if (typeof Flip === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            return Flip.getState(cards, { props: 'opacity', simple: true });
        },

        /**
         * B9: 分頁離場動畫
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {string} direction - 'next' | 'prev'
         * @param {Object} params - 動畫參數
         * @returns {null}
         */
        playPageOut: function (gridEl, direction, params) {
            params = params || {};

            // null guard
            if (!gridEl) return null;

            // GSAP guard（CDN 故障降級）
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            // Reduced Motion 降級：瞬間隱藏 + 立即 onComplete
            if (shouldSkip()) {
                gsap.set(cards, { opacity: 0 });
                if (params.onComplete) params.onComplete();
                return null;
            }

            var dur = params.duration || 0.3;
            var staggerVal = params.stagger || 0.02;
            // 方向邏輯：next → 向左滑出（x: -20），prev → 向右滑出（x: 20）
            var xShift = direction === 'next' ? -20 : 20;
            var staggerFrom = direction === 'next' ? 'start' : 'end';

            var tl = gsap.timeline({ id: 'showcasePageOut' });

            tl.to(cards, {
                opacity: 0,
                x: xShift,
                duration: dur * 0.6,
                ease: 'power2.in',
                stagger: { each: staggerVal, from: staggerFrom }
            });

            // 離場結束後呼叫 onComplete 供 core.js 換頁
            tl.eventCallback('onComplete', function () {
                if (params.onComplete) params.onComplete();
            });

            return tl;
        },

        /**
         * B9: 分頁進場動畫
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {string} direction - 'next' | 'prev'
         * @param {Object} params - 動畫參數
         * @returns {null}
         */
        playPageIn: function (gridEl, direction, params) {
            params = params || {};

            // null guard
            if (!gridEl) return null;

            // GSAP guard（CDN 故障降級）
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            // Reduced Motion 降級：瞬間顯示
            if (shouldSkip()) {
                gsap.set(cards, { opacity: 1, x: 0 });
                return null;
            }

            var dur = params.duration || 0.3;
            var staggerVal = params.stagger || 0.02;
            // 起始位置：反向偏移（next → 從右側 x: 20，prev → 從左側 x: -20）
            var xStart = direction === 'next' ? 20 : -20;
            var staggerFrom = direction === 'next' ? 'start' : 'end';

            // 設定起始位置
            gsap.set(cards, { x: xStart, opacity: 0 });

            var tl = gsap.timeline({ id: 'showcasePageIn' });

            tl.to(cards, {
                opacity: 1,
                x: 0,
                duration: dur,
                ease: 'power3.out',
                stagger: { each: staggerVal, from: staggerFrom },
                onComplete: function () {
                    gsap.set(cards, { clearProps: 'transform,opacity' });
                }
            });

            return tl;
        },

        /**
         * B10: 模式切換 crossfade
         * @param {Element} outEl - 離場容器
         * @param {Element} inEl - 進場容器
         * @param {Object} params - 動畫參數
         * @returns {null}
         */
        playModeCrossfade: function (outEl, inEl, params) {
            return null;
        }
    };

    // 暴露全域物件
    window.ShowcaseAnimations = ShowcaseAnimations;
})();
