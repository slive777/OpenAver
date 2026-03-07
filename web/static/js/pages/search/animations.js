/**
 * SearchAnimations — /search 頁面動畫模組
 *
 * 暴露 window.SearchAnimations 物件，提供：
 *   - playMiniBurst(cards, stagingEl, options)  mini-burst 偏移飛行（C14）
 *   - playCoverSwap(imgEl)                       staging card 封面替換動畫
 *   - playStagingEntry(stagingEl)                staging card 進場 morph
 *   - playStagingExit(stagingEl, options)         staging card 退場 morph + onComplete
 *   - playGridFadeIn(gridEl)                     skeleton grid 整體轉場淡入（保留）
 *
 * C2：此檔案是 pages/ 目錄下被允許直接呼叫 GSAP 的兩個檔案之一
 *      （另一個為 motion-lab.js）。
 * C4：每個動畫開頭 gsap.killTweensOf(target) 清舊動畫。
 * C6：不使用 rotationX / rotationY / rotationZ。
 * C14：Mini-burst 用 gsap.fromTo 偏移量模式（不搬 DOM）。
 * C19：burst 飛行期間 z-index 保護。
 *
 * Graceful fallback：若 GSAP 未載入，所有方法安全降級（不拋錯）。
 * search-flow.js 透過 window.SearchAnimations?.playMiniBurst?.()
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

    window.SearchAnimations = {

        /**
         * Mini-burst：一批卡片從 staging 位置飛到 grid slot（C14 gsap.fromTo 偏移飛行）
         *
         * 不搬移 DOM（Alpine 管 grid），用座標偏移量模擬從 staging 位置飛出的動畫。
         * Viewport 分流：可視卡片 → gsap.fromTo 動畫；fold 以下 → gsap.set 瞬間到位。
         * C19：飛行期間卡片 zIndex 高於已定位的 grid 卡片，定位後重置。
         *
         * @param {Element[]} cards - 要 burst 的卡片 DOM 元素（新填入的 grid 卡片）
         * @param {Element} stagingEl - staging card 元素（飛行起點）
         * @param {object} [options] - { duration, ease, stagger, batchZ, onComplete }
         * @returns {gsap.core.Timeline|null}
         */
        playMiniBurst: function (cards, stagingEl, options) {
            options = options || {};

            if (!cards || !cards.length) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            if (typeof gsap === 'undefined') {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            // Reduced Motion 降級：瞬間到位
            if (shouldSkip()) {
                gsap.set(cards, { opacity: 1, x: 0, y: 0, scale: 1, zIndex: 'auto' });
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            // staging card 不存在或已被隱藏（rect 歸零）時 fallback
            var stagingRect = stagingEl ? stagingEl.getBoundingClientRect() : null;
            if (stagingRect && stagingRect.width === 0 && stagingRect.height === 0) {
                stagingRect = null;
            }

            var dur = options.duration || 0.6;
            var ease = options.ease || 'back.out(1.2)';
            var staggerVal = options.stagger || 0.05;
            var batchZ = ((options.batchZ || 0) * 10) + 100;

            // Viewport 分流：可視卡片 → burst 動畫，fold 以下 → 瞬間顯示
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

            // fold 以下卡片直接顯示（gsap.set 瞬間到位）
            if (offscreen.length) {
                gsap.set(offscreen, { opacity: 1, x: 0, y: 0, scale: 1, zIndex: 'auto' });
            }

            if (!visible.length) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            var tl = gsap.timeline({ id: 'miniBurst' });

            // 對每張可見卡片計算從 staging 位置的偏移
            visible.forEach(function (card, i) {
                var cardRect = card.getBoundingClientRect();
                var dx = 0;
                var dy = 0;
                if (stagingRect) {
                    dx = stagingRect.left - cardRect.left;
                    dy = stagingRect.top - cardRect.top;
                }

                // C19: 飛行期間設高 z-index
                gsap.set(card, { zIndex: batchZ });

                var isLast = (i === visible.length - 1);

                // C6: 不使用旋轉，只用 x/y/scale/opacity
                // C14: gsap.fromTo 偏移量模式（從 staging 位置飛到 grid 自然位置）
                tl.fromTo(card,
                    { x: dx, y: dy, scale: 0.96, opacity: 0 },
                    {
                        x: 0,
                        y: 0,
                        scale: 1,
                        opacity: 1,
                        duration: dur,
                        ease: ease,
                        delay: i * staggerVal,
                        onComplete: (function (c, last) {
                            return function () {
                                gsap.set(c, { zIndex: 'auto' });
                                // 最後一張完成後呼叫 onComplete
                                if (last && typeof options.onComplete === 'function') {
                                    options.onComplete();
                                }
                            };
                        }(card, isLast))
                    },
                    0  // 所有卡片同時開始（個別 delay 控制 stagger）
                );
            });

            return tl;
        },

        /**
         * Staging card 封面替換動畫（快速 crossfade）
         *
         * @param {Element} imgEl - staging card 的 img 元素
         * @returns {gsap.core.Tween|null}
         */
        playCoverSwap: function (imgEl) {
            if (!imgEl) return null;
            if (typeof gsap === 'undefined') return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(imgEl);

            // Reduced Motion 降級：瞬間顯示
            if (shouldSkip()) {
                gsap.set(imgEl, { opacity: 1 });
                return null;
            }

            // 快速 crossfade（opacity 0→1，0.15s）
            return gsap.fromTo(imgEl,
                { opacity: 0 },
                { opacity: 1, duration: 0.15, ease: 'power2.out' }
            );
        },

        /**
         * Staging card 進場 morph（scale 0.6→1 + opacity 0→1 + back.out 彈性感）
         *
         * @param {Element} stagingEl - staging card DOM 元素
         */
        playStagingEntry: function (stagingEl) {
            if (!stagingEl) return;
            if (typeof gsap === 'undefined') return;

            // C4: 清除舊動畫
            gsap.killTweensOf(stagingEl);

            // Reduced Motion 降級：瞬間到位
            if (shouldSkip()) {
                gsap.set(stagingEl, { scale: 1, opacity: 1 });
                return;
            }

            // C6: 不使用旋轉
            gsap.fromTo(stagingEl,
                { scale: 0.6, opacity: 0 },
                { scale: 1, opacity: 1, duration: 0.35, ease: 'back.out(1.4)' }
            );
        },

        /**
         * Staging card 退場 morph（scale→0.7 + opacity→0 + onComplete callback）
         *
         * @param {Element} stagingEl - staging card DOM 元素
         * @param {object} [options] - { onComplete }
         */
        playStagingExit: function (stagingEl, options) {
            options = options || {};

            if (!stagingEl) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return;
            }

            if (typeof gsap === 'undefined') {
                if (typeof options.onComplete === 'function') options.onComplete();
                return;
            }

            // C4: 清除舊動畫（exit 是最終動畫，需清場）
            gsap.killTweensOf(stagingEl);

            // Reduced Motion 降級：瞬間到達最終狀態
            if (shouldSkip()) {
                gsap.set(stagingEl, { scale: 0.7, opacity: 0 });
                if (typeof options.onComplete === 'function') options.onComplete();
                return;
            }

            // C6: 不使用旋轉
            gsap.to(stagingEl, {
                scale: 0.7,
                opacity: 0,
                duration: 0.3,
                ease: 'power2.in',
                onComplete: function () {
                    if (typeof options.onComplete === 'function') options.onComplete();
                }
            });
        },

        /**
         * Skeleton grid 整體轉場淡入（seed 收到後、Progress → Grid 轉場）
         *
         * 輕量整體淡入，讓 skeleton grid 出現時不突兀。（保留不改）
         *
         * @param {Element} gridEl - .search-grid 元素
         * @returns {gsap.core.Tween|null}
         */
        playGridFadeIn: function (gridEl) {
            if (!gridEl) return null;
            if (shouldSkip()) return null;
            if (typeof gsap === 'undefined') return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(gridEl);

            return gsap.from(gridEl, {
                opacity: 0,
                duration: 0.25,
                ease: 'power1.out'
            });
        }
    };
})();
