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
         * Detail→Grid 前：info 先淡出（約 120ms），讓封面轉場時 info 已消失
         * C1: onComplete 只 resolve Promise
         * C4: killTweensOf(infoEl)
         * @param {Element} detailEl - Detail 容器
         * @param {object} params - { reducedMotionSim }
         * @returns {Promise}
         */
        playInfoExit: function (detailEl, params) {
            params = params || {};
            return new Promise(function (resolve) {
                var infoEl = detailEl ? detailEl.querySelector('.av-card-full-info') : null;

                // guard：info 不存在直接 resolve
                if (!infoEl) {
                    resolve();
                    return;
                }

                // C4: 清除舊動畫
                gsap.killTweensOf(infoEl);

                // Reduced Motion 降級：瞬間設為 opacity:0 後 resolve
                if (shouldSkip(params)) {
                    gsap.set(infoEl, { opacity: 0 });
                    resolve();
                    return;
                }

                gsap.to(infoEl, {
                    opacity: 0,
                    duration: 0.12,
                    ease: 'power2.in',
                    onComplete: resolve  // C1: onComplete 只 resolve Promise
                });
            });
        },

        /**
         * Ghost 落位後目標卡輕微 settle（scale 1.02 → 1）
         * 非阻塞：fire-and-forget，不回傳 Promise
         * C4: killTweensOf(cardEl)
         * C6: 禁止旋轉
         * @param {Element} cardEl - Grid 中的 .av-card-preview 元素
         * @param {object} params - { reducedMotionSim }
         */
        playTargetSettle: function (cardEl, params) {
            params = params || {};

            // guard：元素不存在直接 return
            if (!cardEl) return;

            // Reduced Motion 降級：不播動畫，直接 return（不設任何 transform）
            if (shouldSkip(params)) return;

            // C4: 清除舊動畫
            gsap.killTweensOf(cardEl);

            // C6: 不使用旋轉，只用 scale
            gsap.fromTo(cardEl,
                { scale: 1.02 },
                { scale: 1, duration: 0.18, ease: 'power2.out' }
            );
        },

        /**
         * Detail 進場：封面左滑入 + info 下淡入
         * @param {Element} detailEl - Detail 容器
         * @param {object} params - { duration, easing, reducedMotionSim, skipCover }
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
            var detailSpeed = params.detailSpeed || 1;

            // skipCover: ghost transition 已處理封面動畫，只播 info 進場
            var skipCover = params.skipCover === true;

            if (cover && !skipCover) {
                // C6: 不使用 rotationX/Y/Z，使用 x 軸位移
                tl.from(cover, { x: -40, opacity: 0, duration: dur, ease: ease });
            }
            if (info) {
                tl.from(info, { y: 30, opacity: 0, duration: dur * 0.8, ease: ease },
                    (cover && !skipCover) ? ('-=' + (dur * 0.6)) : 0);
            }

            tl.timeScale(detailSpeed);
            return tl;
        },

        /**
         * 在容器內擷取封面元素與其 bounding rect
         * Grid 容器：.av-card-preview-img img（第 index 個）
         * Detail 容器：.av-card-full-cover img
         * @param {Element} containerEl - Grid 或 Detail 容器
         * @param {number|null} index - Grid 中的卡片索引（Detail 傳 null）
         * @returns {{ el: HTMLImageElement, rect: DOMRect }|null}
         */
        captureCoverRect: function (containerEl, index) {
            if (!containerEl) return null;

            var el = null;

            // Detail 容器
            var detailImg = containerEl.querySelector('.av-card-full-cover img');
            if (detailImg) {
                el = detailImg;
            } else {
                // Grid 容器 — 取第 index 個 .av-card-preview-img img
                var imgs = containerEl.querySelectorAll('.av-card-preview-img img');
                if (index != null && imgs[index]) {
                    el = imgs[index];
                }
            }

            if (!el) return null;

            // 圖片未完成載入則降級
            if (!el.complete) return null;

            var rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return null;

            return { el: el, rect: rect };
        },

        /**
         * 建立封面 ghost img 節點，append 到 body
         * @param {HTMLImageElement} sourceEl - 來源 img 元素
         * @param {DOMRect} rect - 來源元素的 bounding rect
         * @returns {HTMLImageElement} ghost element
         */
        createCoverGhost: function (sourceEl, rect) {
            var ghost = document.createElement('img');
            ghost.src = sourceEl.src;
            ghost.className = 'motion-lab-ghost';

            // 複製 source 的 border-radius
            var computed = window.getComputedStyle(sourceEl);
            ghost.style.position = 'fixed';
            ghost.style.left = '0';
            ghost.style.top = '0';
            ghost.style.margin = '0';
            ghost.style.pointerEvents = 'none';
            ghost.style.zIndex = '2000';
            ghost.style.willChange = 'transform, width, height';
            ghost.style.transformOrigin = 'top left';
            ghost.style.borderRadius = computed.borderRadius || '0px';
            ghost.style.objectFit = 'cover';

            document.body.appendChild(ghost);

            // 以 GSAP 定位至來源位置，初始帶輕微陰影（離地感）
            gsap.set(ghost, {
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height,
                boxShadow: '0 4px 16px rgba(0,0,0,0.25)'
            });

            return ghost;
        },

        /**
         * Ghost 封面從 fromRect 飛到 toRect
         * C1: onComplete 只 resolve，不改 Alpine 狀態
         * C4: killTweensOf(ghost)
         * C6: 禁止旋轉
         * @param {HTMLImageElement} ghost - ghost 元素
         * @param {DOMRect} fromRect - 起始位置
         * @param {DOMRect} toRect - 目標位置
         * @param {object} params - { duration, easing }
         * @returns {Promise}
         */
        playSharedCoverTransition: function (ghost, fromRect, toRect, params) {
            params = params || {};
            var dur = params.duration || 0.38;
            var ease = params.easing || 'power2.inOut';

            // C4: 清除舊動畫
            gsap.killTweensOf(ghost);

            return new Promise(function (resolve) {
                // 主飛行 tween（位置 + 大小）
                gsap.fromTo(ghost,
                    {
                        x: fromRect.left,
                        y: fromRect.top,
                        width: fromRect.width,
                        height: fromRect.height
                    },
                    {
                        x: toRect.left,
                        y: toRect.top,
                        width: toRect.width,
                        height: toRect.height,
                        duration: dur,
                        ease: ease,
                        onComplete: resolve  // C1: onComplete 只 resolve Promise
                    }
                );

                // 陰影 keyframes：起飛（0）→ 強化（50%）→ 落地（100%）
                gsap.to(ghost, {
                    keyframes: [
                        { boxShadow: '0 12px 32px rgba(0,0,0,0.40)', duration: dur * 0.5 },
                        { boxShadow: '0 2px 8px rgba(0,0,0,0.15)', duration: dur * 0.5 }
                    ],
                    ease: 'none'
                });
            });
        },

        /**
         * Crossfade 封面轉場：target 淡入放大，source 輕微淡出
         * C1: onComplete 只 resolve，不改 Alpine 狀態
         * C4: killTweensOf(sourceEl, targetEl)
         * C6: 禁止旋轉
         * @param {HTMLImageElement|null} sourceEl - 來源封面 img（可為 null）
         * @param {HTMLImageElement|null} targetEl - 目標封面 img（可為 null）
         * @param {object} params - { duration, reducedMotionSim }
         * @returns {Promise}
         */
        playCrossfadeTransition: function (sourceEl, targetEl, params) {
            params = params || {};

            return new Promise(function (resolve) {
                // C4: 清除舊動畫
                var targets = [sourceEl, targetEl].filter(Boolean);
                if (targets.length) {
                    gsap.killTweensOf(targets);
                }

                // targetEl 不存在 → 直接 resolve
                if (!targetEl) {
                    resolve();
                    return;
                }

                // Reduced Motion 降級：gsap.set 瞬間完成
                if (shouldSkip(params)) {
                    gsap.set(targetEl, { opacity: 1, scale: 1 });
                    if (sourceEl) gsap.set(sourceEl, { opacity: 1 });
                    resolve();
                    return;
                }

                var baseDur = params.duration || 0.6;
                // 保持比例感：target 0.30s base，source 0.20s base，依 params.duration 等比縮放
                var targetDur = 0.30 * (baseDur / 0.6);
                var sourceDur = 0.20 * (baseDur / 0.6);

                var tl = gsap.timeline({
                    onComplete: resolve  // C1: onComplete 只 resolve Promise
                });

                // target cover：opacity 0, scale 0.94 → opacity 1, scale 1
                // C6: 不使用 rotationX/Y/Z
                tl.fromTo(targetEl,
                    { opacity: 0, scale: 0.94 },
                    { opacity: 1, scale: 1, duration: targetDur, ease: 'power2.out' }
                );

                // source cover：輕微淡出（若 sourceEl 存在）
                if (sourceEl) {
                    tl.to(sourceEl,
                        { opacity: 0, duration: sourceDur, ease: 'power2.out' },
                        0  // 與 target 動畫同時開始
                    );
                }
            });
        },

        /**
         * 清除 ghost 並還原真實封面 opacity
         * @param {HTMLImageElement} ghost - ghost 元素
         * @param {HTMLImageElement|null} sourceEl - 來源封面 img（還原 opacity）
         * @param {HTMLImageElement|null} targetEl - 目標封面 img（還原 opacity）
         */
        cleanupCoverGhost: function (ghost, sourceEl, targetEl) {
            if (ghost && ghost.parentNode) {
                ghost.remove();
            }
            var toRestore = [];
            if (sourceEl) toRestore.push(sourceEl);
            if (targetEl) toRestore.push(targetEl);
            if (toRestore.length) {
                gsap.set(toRestore, { opacity: 1 });
            }
        },

        /**
         * 滑出動畫（返回 Promise — C1 合規：onComplete 只 resolve，不改 Alpine 狀態）
         * @param {Element} containerEl - 容器
         * @param {'next'|'prev'} direction - 語義方向：'next' 往左滑出，'prev' 往右滑出
         * @param {object} params - { duration, easing, reducedMotionSim }
         * @returns {Promise}
         */
        playSlideOut: function (containerEl, direction, params) {
            params = params || {};
            var detailSpeed = params.detailSpeed || 1;

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
                var xTo = direction === 'next' ? -40 : 40;

                gsap.to(containerEl, {
                    x: xTo,
                    opacity: 0,
                    duration: dur,
                    ease: 'power2.in',
                    onComplete: resolve  // C1: onComplete 只 resolve Promise
                }).timeScale(detailSpeed);
            });
        },

        /**
         * 滑入動畫
         * @param {Element} containerEl - 容器
         * @param {'next'|'prev'} direction - 語義方向：'next' 從右滑入，'prev' 從左滑入
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
            var xFrom = direction === 'next' ? 40 : -40;
            var ease = params.easing || 'power3.out';
            var detailSpeed = params.detailSpeed || 1;

            return gsap.fromTo(containerEl,
                { x: xFrom, opacity: 0 },
                { x: 0, opacity: 1, duration: dur, ease: ease }
            ).timeScale(detailSpeed);
        },

        /**
         * 重置所有動畫狀態
         * @param {Element} gridEl - Grid 容器
         * @param {Element} detailEl - Detail 容器
         */
        resetAll: function (gridEl, detailEl) {
            if (gridEl) {
                var cards = gridEl.querySelectorAll('.av-card-preview');
                gsap.killTweensOf(cards);
                // 重置卡片 transform/opacity
                gsap.set(cards, { clearProps: 'all' });
                // 清除 ghost 轉場中途被設為 opacity:0 的封面 img
                var gridImgs = gridEl.querySelectorAll('.av-card-preview-img img');
                if (gridImgs.length) {
                    gsap.killTweensOf(gridImgs);
                    gsap.set(gridImgs, { clearProps: 'all' });
                }
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
