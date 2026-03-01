/**
 * Motion Lab — 動畫沙盒控制器
 *
 * 此模組在 lint allowlist 內，可直接呼叫 GSAP API（C2 規格）。
 * 原因：動態座標計算（burst 從搜尋框飛出）需要 getBoundingClientRect()，
 *       無法透過 motion-adapter.js 的固定起點封裝。
 *
 * 約束：
 *   C1: GSAP onComplete 禁止改 Alpine 狀態，只 resolve Promise
 *   C4: 每個動畫開頭 gsap.killTweensOf(targets)
 *   C6: 封面禁止旋轉（不使用 rotationX/Y/Z）
 */

(function () {
    'use strict';

    /**
     * 檢查是否應跳過動畫（reduced-motion）
     * @param {object} params - Alpine state 傳入的動畫參數
     * @returns {boolean}
     */
    function shouldSkip(params) {
        return !!(
            (params && params.reducedMotionSim) ||
            (window.OpenAver && window.OpenAver.prefersReducedMotion)
        );
    }

    /**
     * Function-based stagger：依距離搜尋框遠近計算延遲
     * @param {Element} originEl - 起始元素（搜尋框）
     * @param {NodeList|Array} targets - 目標元素清單
     * @param {number} totalDelay - 最大延遲時間（秒）
     * @returns {function} GSAP stagger function
     */
    function staggerFromElement(originEl, targets, totalDelay) {
        var originRect = originEl.getBoundingClientRect();
        var originX = originRect.left + originRect.width / 2;
        var originY = originRect.top + originRect.height / 2;

        var arr = Array.from(targets);
        var distances = arr.map(function (el) {
            var rect = el.getBoundingClientRect();
            var dx = (rect.left + rect.width / 2) - originX;
            var dy = (rect.top + rect.height / 2) - originY;
            return Math.sqrt(dx * dx + dy * dy);
        });
        var maxDist = Math.max.apply(null, distances) || 1;

        return function (index) {
            return (distances[index] / maxDist) * totalDelay;
        };
    }

    var MotionLab = {

        /**
         * 卡片從搜尋框位置飛向 grid（burst 動畫）
         * @param {Element} gridEl - Grid 容器
         * @param {Element} searchBarEl - 假搜尋框（burst 起點）
         * @param {object} params - { duration, stagger, easing, reducedMotionSim }
         * @returns {gsap.core.Timeline}
         */
        playGridBurst: function (gridEl, searchBarEl, params) {
            params = params || {};
            var cards = gridEl ? gridEl.querySelectorAll('.av-card-preview') : [];

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            var tl = gsap.timeline({ id: 'burst' });

            if (!cards.length) return tl;

            // reduced-motion 降級：瞬間完成
            if (shouldSkip(params)) {
                gsap.set(cards, { opacity: 1, y: 0, scale: 1 });
                return tl;
            }

            var dur = params.duration || 0.6;
            var ease = params.easing || 'back.out(1.2)';
            var staggerVal = params.stagger || 0.05;

            // viewport 分流：可視卡片 → burst 動畫，fold 以下 → 瞬間顯示
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

            // fold 以下卡片直接顯示
            if (offscreen.length) {
                gsap.set(offscreen, { opacity: 1, x: 0, y: 0, scale: 1 });
            }

            if (!visible.length) return tl;

            // 設定初始狀態（可視卡片在搜尋框位置）
            if (searchBarEl) {
                var searchRect = searchBarEl.getBoundingClientRect();
                var originX = searchRect.left + searchRect.width / 2;
                var originY = searchRect.top + searchRect.height / 2;

                visible.forEach(function (card) {
                    var rect = card.getBoundingClientRect();
                    var cardCenterX = rect.left + rect.width / 2;
                    var cardCenterY = rect.top + rect.height / 2;
                    gsap.set(card, {
                        x: originX - cardCenterX,
                        y: originY - cardCenterY,
                        scale: 0.3,
                        opacity: 0
                    });
                });
            } else {
                gsap.set(visible, { y: -30, scale: 0.8, opacity: 0 });
            }

            tl.to(visible, {
                x: 0,
                y: 0,
                scale: 1,
                opacity: 1,
                duration: dur,
                ease: ease,
                stagger: { each: staggerVal, from: 'end' }
            });

            // 速度控制：timeScale < 1 = 慢速（便於觀察動畫細節）
            tl.timeScale(params.speed || 1);

            // 動畫結束後初始化 GSDevTools（如果可用）
            tl.eventCallback('onComplete', function () {
                MotionLab.initDevTools(tl);
            });

            return tl;
        },

        /**
         * 封面 clip-path 從底往上展開
         * @param {Element} containerEl - 包含封面的容器
         * @param {object} params - { clipRevealDur, easing, reducedMotionSim }
         * @returns {gsap.core.Tween}
         */
        playClipPathReveal: function (containerEl, params) {
            params = params || {};
            var imgs = containerEl ? containerEl.querySelectorAll('img') : [];

            // C4: 清除舊動畫
            gsap.killTweensOf(imgs);

            if (!imgs.length) return null;

            // reduced-motion 降級
            if (shouldSkip(params)) {
                gsap.set(imgs, { clipPath: 'inset(0% 0% 0% 0%)' });
                return null;
            }

            var dur = params.clipRevealDur || 0.5;
            var speed = params.speed || 1;
            var ease = params.easing || 'power3.out';

            // C6: 禁止旋轉，使用 clip-path 展開
            // 速度同步：與 burst timeline 的 timeScale 保持一致
            var tl = gsap.timeline();
            tl.fromTo(imgs,
                { clipPath: 'inset(100% 0% 0% 0%)' },
                { clipPath: 'inset(0% 0% 0% 0%)', duration: dur, ease: ease }
            );
            tl.timeScale(speed);
            return tl;
        },

        /**
         * Detail 進場：封面左滑入 + info 下淡入
         * @param {Element} detailEl - Detail 容器
         * @param {object} params - { duration, easing, reducedMotionSim }
         * @returns {gsap.core.Timeline}
         */
        playDetailEntry: function (detailEl, params) {
            params = params || {};

            var tl = gsap.timeline({ id: 'detail' });
            if (!detailEl) return tl;

            var cover = detailEl.querySelector('.av-card-full-cover');
            var info = detailEl.querySelector('.av-card-full-info');

            // C4: 清除舊動畫
            if (cover) gsap.killTweensOf(cover);
            if (info) gsap.killTweensOf(info);

            // reduced-motion 降級
            if (shouldSkip(params)) {
                if (cover) gsap.set(cover, { x: 0, opacity: 1 });
                if (info) gsap.set(info, { y: 0, opacity: 1 });
                return tl;
            }

            var dur = params.duration || 0.6;
            var ease = params.easing || 'power3.out';

            if (cover) {
                // C6: 不使用 rotationX/Y/Z，使用 x 軸位移
                tl.from(cover, { x: -40, opacity: 0, duration: dur, ease: ease });
            }
            if (info) {
                tl.from(info, { y: 30, opacity: 0, duration: dur * 0.8 },
                    cover ? ('-=' + (dur * 0.6)) : 0);
            }

            return tl;
        },

        /**
         * 滑出動畫（返回 Promise — C1 合規：onComplete 只 resolve，不改 Alpine 狀態）
         * @param {Element} containerEl - 容器
         * @param {'left'|'right'} direction - 滑出方向
         * @param {object} params - { duration, easing, reducedMotionSim }
         * @returns {Promise}
         */
        playSlideOut: function (containerEl, direction, params) {
            params = params || {};

            return new Promise(function (resolve) {
                if (!containerEl) {
                    resolve();
                    return;
                }

                // C4: 清除舊動畫
                gsap.killTweensOf(containerEl);

                // reduced-motion 降級
                if (shouldSkip(params)) {
                    resolve();  // C1: 只 resolve，不改狀態
                    return;
                }

                var dur = (params.duration || 0.6) * 0.5;
                var xTo = direction === 'left' ? '-50%' : '50%';

                gsap.to(containerEl, {
                    x: xTo,
                    opacity: 0,
                    duration: dur,
                    ease: 'power2.in',
                    onComplete: resolve  // C1: onComplete 只 resolve Promise
                });
            });
        },

        /**
         * 滑入動畫
         * @param {Element} containerEl - 容器
         * @param {'left'|'right'} direction - 來自方向
         * @param {object} params - { duration, easing, reducedMotionSim }
         * @returns {gsap.core.Tween}
         */
        playSlideIn: function (containerEl, direction, params) {
            params = params || {};

            if (!containerEl) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(containerEl);

            // reduced-motion 降級
            if (shouldSkip(params)) {
                gsap.set(containerEl, { x: 0, opacity: 1 });
                return null;
            }

            var dur = (params.duration || 0.6) * 0.5;
            var xFrom = direction === 'left' ? '-50%' : '50%';
            var ease = params.easing || 'power3.out';

            return gsap.fromTo(containerEl,
                { x: xFrom, opacity: 0 },
                { x: 0, opacity: 1, duration: dur, ease: ease }
            );
        },

        /**
         * 重置所有動畫狀態
         * @param {Element} gridEl - Grid 容器
         * @param {Element} detailEl - Detail 容器
         */
        resetAll: function (gridEl, detailEl) {
            var allTargets = [];

            if (gridEl) {
                var cards = gridEl.querySelectorAll('.av-card-preview');
                gsap.killTweensOf(cards);
                allTargets = allTargets.concat(Array.from(cards));
                // 重置卡片 transform/opacity
                gsap.set(cards, { clearProps: 'all' });
            }

            if (detailEl) {
                var cover = detailEl.querySelector('.av-card-full-cover');
                var info = detailEl.querySelector('.av-card-full-info');
                var imgs = detailEl.querySelectorAll('img');
                if (cover) { gsap.killTweensOf(cover); gsap.set(cover, { clearProps: 'all' }); }
                if (info) { gsap.killTweensOf(info); gsap.set(info, { clearProps: 'all' }); }
                if (imgs.length) { gsap.killTweensOf(imgs); gsap.set(imgs, { clearProps: 'all' }); }
            }
        },

        /**
         * 初始化 GSDevTools（只在 GSDevTools 可用時執行）
         * @param {gsap.core.Timeline} timeline - 要載入到 DevTools 的 timeline
         */
        initDevTools: function (timeline) {
            if (typeof GSDevTools === 'undefined') {
                console.warn('[MotionLab] GSDevTools 未載入，跳過 initDevTools');
                return;
            }
            GSDevTools.create({
                animation: timeline || undefined,
                id: 'sandbox',
                visibility: 'auto',
                loop: true
            });
        }
    };

    // 暴露到全域
    window.MotionLab = MotionLab;

    // 等待 GSAP 插件載入後，註冊自訂 easing（如果 CustomEase 可用）
    document.addEventListener('DOMContentLoaded', function () {
        if (typeof CustomEase !== 'undefined' && typeof CustomBounce !== 'undefined') {
            try {
                gsap.registerPlugin(CustomEase, CustomBounce);
                CustomBounce.create('cardLand', { strength: 0.3, squash: 0 });
                console.log('[MotionLab] CustomBounce 已初始化');
            } catch (e) {
                console.warn('[MotionLab] CustomBounce 初始化失敗:', e);
            }
        }
        if (typeof Flip !== 'undefined') {
            try {
                gsap.registerPlugin(Flip);
                console.log('[MotionLab] Flip 已載入');
            } catch (e) {
                console.warn('[MotionLab] Flip 初始化失敗:', e);
            }
        }
    });

})();
