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
            var ease = params.easing || 'fluent';
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
            var ease = params.easing || 'fluent-decel';

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
                    ease: 'fluent-accel',
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
                { scale: 1, duration: 0.18, ease: 'fluent-decel' }
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
            var ease = params.easing || 'fluent-decel';
            var detailSpeed = params.detailSpeed || 1;

            // skipCover: ghost transition 已處理封面動畫，只播 info 進場
            var skipCover = params.skipCover === true;

            if (cover && !skipCover) {
                // C6: 不使用 rotationX/Y/Z，使用 x 軸位移
                // fromTo 明確指定終值，避免 playInfoExit 殘留 opacity:0 造成目標值錯誤
                tl.fromTo(cover,
                    { x: -40, opacity: 0 },
                    { x: 0, opacity: 1, duration: dur, ease: ease });
            }
            if (info) {
                tl.fromTo(info,
                    { y: 30, opacity: 0 },
                    { y: 0, opacity: 1, duration: dur * 0.8, ease: ease },
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
            var ease = params.easing || 'fluent';

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
                    { opacity: 1, scale: 1, duration: targetDur, ease: 'fluent-decel' }
                );

                // source cover：輕微淡出（若 sourceEl 存在）
                if (sourceEl) {
                    tl.to(sourceEl,
                        { opacity: 0, duration: sourceDur, ease: 'fluent-decel' },
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
                    ease: 'fluent-accel',
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
            var ease = params.easing || 'fluent-decel';
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
         * 單卡 Stream-in 進場動畫
         * 動畫目標為卡片內的圖片區域（.av-card-preview-img），番號 footer 固定不動。
         * C1: onComplete 只 resolve Promise（此函數不返回 Promise，但不改 Alpine 狀態）
         * C4: 開頭 killTweensOf(imgEl)
         * C6: 不使用 rotationX/Y/Z
         * @param {Element} cardEl - .av-card-preview 元素（整張卡）
         * @param {'fadeScale'|'fadeUp'|'reveal'} style - 動畫風格
         * @param {object} params - Alpine 傳入的 params 物件（含 reducedMotionSim）
         * @returns {gsap.core.Tween|null} - reduced-motion 時返回 null
         */
        playCardStreamIn: function (cardEl, style, params) {
            params = params || {};

            // null guard
            if (!cardEl) return null;

            // 動畫目標：圖片區域，番號 footer 保持錨定不動
            var imgEl = cardEl.querySelector('.av-card-preview-img') || cardEl;

            // C4: 清除舊動畫
            gsap.killTweensOf(imgEl);

            // Reduced Motion 降級：瞬間顯示，不播動畫
            if (shouldSkip(params)) {
                gsap.set(imgEl, { opacity: 1, scale: 1, clipPath: 'none', y: 0 });
                return null;
            }

            style = style || 'fadeScale';

            if (style === 'fadeScale') {
                return gsap.fromTo(imgEl,
                    { opacity: 0, scale: 0.92 },
                    { opacity: 1, scale: 1, duration: 0.3, ease: 'fluent-decel' }
                );
            }

            if (style === 'fadeUp') {
                return gsap.fromTo(imgEl,
                    { opacity: 0, y: 20 },
                    { opacity: 1, y: 0, duration: 0.35, ease: 'fluent-decel' }
                );
            }

            if (style === 'reveal') {
                // C6: clip-path 展開，無旋轉、無位移
                return gsap.fromTo(imgEl,
                    { clipPath: 'inset(100% 0 0 0)' },
                    { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.4, ease: 'fluent-decel' }
                );
            }

            // 未知 style 降級為 fadeScale
            return gsap.fromTo(imgEl,
                { opacity: 0, scale: 0.92 },
                { opacity: 1, scale: 1, duration: 0.3, ease: 'fluent-decel' }
            );
        },

        /**
         * Staging Burst：一批卡片從 staging card 位置飛到 grid slot
         * 複用 playGridBurst 的 viewport 分流邏輯
         * C4: killTweensOf(cards)
         * C6: 不使用 rotationX/Y/Z
         * C19: 飛行期間設高 zIndex（options.batchZ * 10 + 100），完成後重置
         *
         * @param {Element[]} cards   - 要 burst 的 grid 卡片 DOM 元素陣列
         * @param {Element} stagingEl - staging card 元素（飛行起點）
         * @param {object} options    - {
         *     duration: 0.6,
         *     ease: 'back.out(1.2)',
         *     stagger: 0.05,
         *     batchZ: 0,            // 批次 z-index 基底（C19）
         *     reducedMotionSim: false
         * }
         * @returns {gsap.core.Timeline}
         */
        playStagingBurst: function (cards, stagingEl, options) {
            options = options || {};
            var tl = gsap.timeline({ id: 'stagingBurst' });

            if (!cards || !cards.length) return tl;

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            // Reduced Motion 降級：瞬間到位
            if (shouldSkip(options)) {
                gsap.set(cards, { opacity: 1, x: 0, y: 0, scale: 1, zIndex: 'auto' });
                return tl;
            }

            // null guard: staging card 不存在時 fallback
            var stagingRect = stagingEl ? stagingEl.getBoundingClientRect() : null;

            // staging card 已被隱藏（rect 歸零）時 fallback 到畫面中心
            if (stagingRect && stagingRect.width === 0 && stagingRect.height === 0) {
                stagingRect = null;
            }

            var dur = options.duration || options.burstDuration || 0.6;
            var ease = options.ease || options.burstEase || 'back.out(1.2)'; // §5 white-list: Burst Picker
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

            if (!visible.length) return tl;

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

                // C6: 不使用旋轉，只用 x/y/scale/opacity
                tl.fromTo(card,
                    { x: dx, y: dy, scale: 0.8, opacity: 0 },
                    {
                        x: 0,
                        y: 0,
                        scale: 1,
                        opacity: 1,
                        duration: dur,
                        ease: ease,
                        delay: i * staggerVal,
                        onComplete: (function (c) {
                            return function () {
                                gsap.set(c, { zIndex: 'auto' });
                            };
                        }(card))
                    },
                    0  // 所有卡片同時開始（個別 delay 控制 stagger）
                );
            });

            return tl;
        },

        /**
         * 封面 crossfade swap：imgEl opacity 0 → 1（快速淡入）
         * C4: killTweensOf(imgEl)
         * C6: 不使用旋轉
         * @param {Element} imgEl - 封面 img 元素
         * @param {object} options - { reducedMotionSim }
         * @returns {gsap.core.Tween|null}
         */
        playCoverSwap: function (imgEl, options) {
            options = options || {};

            if (!imgEl) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(imgEl);

            // Reduced Motion 降級：瞬間顯示
            if (shouldSkip(options)) {
                gsap.set(imgEl, { opacity: 1 });
                return null;
            }

            return gsap.fromTo(imgEl,
                { opacity: 0 },
                { opacity: 1, duration: 0.15, ease: 'power2.out' }
            );
        },

        /**
         * Staging Card 入場 morph：從縮小/透明展開（back.out 彈性感）
         * C4: killTweensOf（入場是第一個動畫，無前序 tween 需保護）
         * @param {Element} stagingCardEl - staging card DOM 元素
         * @param {object} options - { reducedMotionSim }
         */
        playStagingEntry: function (stagingCardEl, options) {
            options = options || {};
            if (!stagingCardEl) return;
            gsap.killTweensOf(stagingCardEl);
            if (shouldSkip(options)) {
                gsap.set(stagingCardEl, { scale: 1, opacity: 1 });
                return;
            }
            gsap.fromTo(stagingCardEl,
                { scale: 0.6, opacity: 0 },
                { scale: 1, opacity: 1, duration: 0.35, ease: 'back.out(1.4)' }
            );
        },

        /**
         * 第一張 result-item 到達時的蓄能 pop
         * 不用 killTweensOf：允許和入場動畫並存（入場 0.35s，pop 0.24s，重疊可接受）
         * @param {Element} stagingCardEl - staging card DOM 元素
         * @param {object} options - { reducedMotionSim }
         */
        playStagingPop: function (stagingCardEl, options) {
            options = options || {};
            if (!stagingCardEl) return;
            if (shouldSkip(options)) return;
            // 不 killTweensOf：允許和入場動畫並存
            gsap.to(stagingCardEl, {
                scale: 1.08, duration: 0.12, ease: 'power2.out',
                yoyo: true, repeat: 1,
                onComplete: function () {
                    gsap.set(stagingCardEl, { scale: 1 });
                }
            });
        },

        /**
         * 第 2 張起的 micro-pulse（150ms debounce 由 Alpine 側負責）
         * 不用 killTweensOf：exit tween 若在進行中不能打斷
         * Alpine 側的 _stagingExiting guard 為第一道防線
         * @param {Element} stagingCardEl - staging card DOM 元素
         * @param {object} options - { reducedMotionSim }
         */
        playStagingPulse: function (stagingCardEl, options) {
            options = options || {};
            if (!stagingCardEl) return;
            if (shouldSkip(options)) return;
            // 不 killTweensOf：exit tween 若在進行中不能打斷
            gsap.to(stagingCardEl, {
                scale: 1.04, duration: 0.08, ease: 'power2.out',
                yoyo: true, repeat: 1
            });
        },

        /**
         * Staging Card exit morph：縮小 + 淡出
         * C4: killTweensOf（exit 是最終動畫，需清場）
         * C1: onComplete 是純動畫回調，state 由呼叫方 _triggerStagingExit 管理
         * @param {Element} stagingCardEl - staging card DOM 元素
         * @param {object} options - { reducedMotionSim }
         * @param {Function} onComplete - 動畫完成後的回調
         */
        playStagingExit: function (stagingCardEl, options, onComplete) {
            options = options || {};
            if (!stagingCardEl) {
                if (typeof onComplete === 'function') onComplete();
                return;
            }
            gsap.killTweensOf(stagingCardEl);
            if (shouldSkip(options)) {
                gsap.set(stagingCardEl, { scale: 0.7, opacity: 0 });
                if (typeof onComplete === 'function') onComplete();
                return;
            }
            gsap.to(stagingCardEl, {
                scale: 0.7, opacity: 0, duration: 0.3, ease: 'power2.in',
                onComplete: function () {
                    if (typeof onComplete === 'function') onComplete();
                }
            });
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
        },

        /**
         * Hero Slot: skeleton → 封面圖填充動畫
         * C4: killTweensOf(img)
         * C6: 不使用旋轉
         * @param {Element} heroEl - hero placeholder DOM
         * @param {object} options - { duration, ease, reducedMotionSim }
         * @returns {gsap.core.Tween|null}
         */
        playHeroFill: function (heroEl, options) {
            options = options || {};
            if (!heroEl) return null;
            var img = heroEl.querySelector('.av-card-preview-img img');
            if (!img) return null;
            // C4: 清除舊動畫
            gsap.killTweensOf(img);
            if (shouldSkip(options)) {
                gsap.set(img, { opacity: 1, scale: 1 });
                return null;
            }
            var dur = options.duration || 0.5;
            var ease = options.ease || 'fluent-decel';
            return gsap.fromTo(img,
                { opacity: 0, scale: 1.05 },
                { opacity: 1, scale: 1, duration: dur, ease: ease }
            );
        },

        /**
         * Hero Slot: Flip 補位動畫
         * 呼叫端負責：getState → DOM 變更 → 確認 DOM 更新後呼叫此方法
         *
         * @param {Flip.FlipState} flipState - Flip.getState() 的結果（DOM 變更前捕獲）
         * @param {object} options - { duration, ease, reducedMotionSim }
         * @returns {Promise}
         */
        playHeroRemove: function (flipState, options) {
            options = options || {};
            return new Promise(function (resolve) {
                if (!flipState) { resolve(); return; }
                if (typeof Flip === 'undefined') { resolve(); return; }
                if (shouldSkip(options)) { resolve(); return; }

                var dur = options.duration || 0.4;
                var ease = options.ease || 'fluent';
                Flip.from(flipState, {
                    duration: dur,
                    ease: ease,
                    onComplete: resolve
                });
            });
        },

        /**
         * Grid Settle Pulse：staging exit 完成後，前幾行卡片極輕微 scale pulse
         * 營造「結果穩定落位」的收尾感
         *
         * @param {Element} gridEl - grid 容器
         * @param {object} [options] - { duration, scale, ease, rows, reducedMotionSim }
         * @returns {gsap.core.Timeline|null}
         */
        playGridSettle: function (gridEl, options) {
            options = options || {};
            if (!gridEl) return null;
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // 動畫目標是 .av-card-preview-img（不是 .av-card-preview），
            // 因為 .av-card-preview:hover 有 CSS transform（theme.css），
            // GSAP 寫 inline scale 會覆蓋 hover 效果
            var imgTargets = [];
            cards.forEach(function (card) {
                var img = card.querySelector('.av-card-preview-img');
                if (img) imgTargets.push(img);
            });
            if (!imgTargets.length) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(imgTargets);

            // Reduced Motion 降級
            if (shouldSkip(options)) {
                gsap.set(imgTargets, { scale: 1 });
                return null;
            }

            var dur = options.duration || 0.8;
            var scaleVal = options.scale || 1.06;
            var ease = options.ease || 'settle';
            var rowCount = options.rows || 2;

            // Row bucketing：2px tolerance，避免子像素差異
            var rowMap = {};
            imgTargets.forEach(function (img, i) {
                var card = cards[i];
                var top = card.getBoundingClientRect().top;
                var rowKey = Math.round(top / 2) * 2;
                if (!rowMap[rowKey]) rowMap[rowKey] = [];
                rowMap[rowKey].push(img);
            });

            // 按 rowKey 升序排列
            var sortedKeys = Object.keys(rowMap).map(Number).sort(function (a, b) { return a - b; });

            // 只取前 N 行
            var targetKeys = sortedKeys.slice(0, rowCount);
            if (!targetKeys.length) return null;

            // 建立 timeline
            var tl = gsap.timeline({ id: 'gridSettle' });

            targetKeys.forEach(function (key, rowIdx) {
                var rowImgs = rowMap[key];
                // 同行卡片同時，跨行 0.06s 延遲
                tl.fromTo(rowImgs,
                    { scale: scaleVal },
                    { scale: 1, duration: dur, ease: ease },
                    rowIdx * 0.06  // position parameter
                );
            });

            // C6: 不使用 rotationX/Y/Z，只用 scale ✓

            return tl;
        },

        /**
         * Showcase Grid Flip 排序洗牌動畫
         * C18: Flip.killFlipsOf 中斷進行中動畫
         * @param {Element} gridEl - .showcase-grid 容器（x-ref="showcaseGrid"）
         * @param {function} sortFn - Array.sort 比較函數
         * @param {object} params - { duration, ease, prune, reducedMotionSim }
         * @returns {Flip|null}
         */
        playFlipReorder: function (gridEl, sortFn, params) {
            params = params || {};
            if (!gridEl) return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // Reduced Motion 降級：DOM reorder 仍執行，不播動畫
            if (shouldSkip(params)) {
                var reordered = sortFn === 'reverse'
                    ? Array.from(cards).reverse()
                    : Array.from(cards).sort(sortFn);
                reordered.forEach(function (card) { gridEl.appendChild(card); });
                return null;
            }

            // C18: 中斷進行中的 Flip 動畫
            Flip.killFlipsOf(cards);

            // 1. Capture state BEFORE DOM reorder
            var state = Flip.getState(cards, {
                props: 'opacity',
                simple: true
            });

            // 2. Reorder DOM（直接操作，不用 Alpine x-for）
            var sorted = sortFn === 'reverse'
                ? Array.from(cards).reverse()
                : Array.from(cards).sort(sortFn);
            sorted.forEach(function (card) {
                gridEl.appendChild(card);
            });

            // 3. Flip.from — 動畫從舊位置到新位置
            var dur = params.duration || 0.5;
            var ease = params.ease || 'fluent';

            return Flip.from(state, {
                duration: dur,
                ease: ease,
                absolute: true,
                prune: params.prune !== false,
                simple: true,
                onComplete: function () {
                    // 清除 inline transform，恢復 CSS hover
                    gsap.set(cards, { clearProps: 'transform' });
                }
            });
        },

        /**
         * Showcase Grid 篩選動畫：Flip onEnter/onLeave
         * C18: Flip.killFlipsOf 中斷進行中的 Flip
         * @param {Element} gridEl - .showcase-grid 容器（x-ref="showcaseGrid"）
         * @param {function} filterFn - 接收 card element，回傳 boolean（true=顯示）
         * @param {object} params - { duration, enterStyle, leaveStyle, reducedMotionSim }
         * @returns {gsap.core.Timeline|null}
         */
        playFlipFilter: function (gridEl, filterFn, params) {
            params = params || {};
            if (!gridEl) return null;

            var allCards = gridEl.querySelectorAll('.av-card-preview');
            if (!allCards.length) return null;

            // Reduced Motion 降級
            if (shouldSkip(params)) {
                Array.from(allCards).forEach(function (card) {
                    card.style.display = filterFn(card) ? '' : 'none';
                });
                return null;
            }

            // C18: 中斷進行中的 Flip
            Flip.killFlipsOf(allCards);

            // 1. Capture state
            var state = Flip.getState(allCards, { props: 'opacity' });

            // 2. 套用 filter（toggle display）
            Array.from(allCards).forEach(function (card) {
                card.style.display = filterFn(card) ? '' : 'none';
            });

            // 3. Flip.from with onEnter/onLeave
            var dur = params.duration || 0.4;
            var enterStyle = params.enterStyle || 'opacityScale';
            var leaveStyle = params.leaveStyle || 'opacityScale';

            return Flip.from(state, {
                duration: dur,
                ease: 'fluent',
                absolute: true,
                prune: true,
                simple: true,
                onEnter: function (els) {
                    // enterStyle branching
                    if (enterStyle === 'fadeUp') {
                        return gsap.fromTo(els,
                            { opacity: 0, y: 20 },
                            { opacity: 1, y: 0, duration: dur * 0.8, ease: 'fluent-decel' });
                    }
                    // default: opacityScale
                    return gsap.fromTo(els,
                        { opacity: 0, scale: 0.85 },
                        { opacity: 1, scale: 1, duration: dur * 0.8, ease: 'fluent-decel' });
                },
                onLeave: function (els) {
                    // leaveStyle branching
                    if (leaveStyle === 'opacityOnly') {
                        return gsap.to(els,
                            { opacity: 0, duration: dur * 0.6, ease: 'fluent-accel' });
                    }
                    // default: opacityScale
                    return gsap.to(els,
                        { opacity: 0, scale: 0.85, duration: dur * 0.6, ease: 'fluent-accel' });
                },
                onComplete: function () {
                    var visible = gridEl.querySelectorAll(
                        '.av-card-preview:not([style*="display: none"])');
                    gsap.set(visible, { clearProps: 'transform' });
                }
            });
        },

        /**
         * 分頁切換動畫：stagger-out 舊頁 + stagger-in 新頁
         * C4: killTweensOf(cards)
         * C18: interrupt 策略（不 lock）
         * @param {Element} gridEl - .showcase-grid 容器（x-ref="showcaseGrid"）
         * @param {string} direction - 'prev' | 'next'
         * @param {object} params - { duration, stagger, reducedMotionSim }
         * @returns {gsap.core.Timeline|null}
         */
        playPageTransition: function (gridEl, direction, params) {
            params = params || {};

            // null guard
            if (!gridEl) return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // Reduced Motion 降級：瞬間顯示
            if (shouldSkip(params)) {
                gsap.set(cards, { opacity: 1, x: 0 });
                return null;
            }

            // C4: 清除舊動畫（含被中斷的上一次分頁動畫）
            gsap.killTweensOf(cards);

            var dur = params.duration || 0.3;
            var staggerVal = params.stagger || 0.02;
            var xShift = direction === 'next' ? -20 : 20;
            var staggerFrom = direction === 'next' ? 'start' : 'end';

            var tl = gsap.timeline({ id: 'pageTransition' });

            // Phase 1: stagger-out
            tl.to(cards, {
                opacity: 0,
                x: xShift,
                duration: dur * 0.6,
                ease: 'power2.in',
                stagger: { each: staggerVal, from: staggerFrom }
            });

            // Phase 2: set 反向起始位置 + stagger-in
            tl.set(cards, { x: -xShift });
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
         * Showcase Grid 入場動畫：stagger 依序淡入
         * C4: killTweensOf(cards)
         * C6: 不使用 rotationX/Y/Z
         * @param {Element} gridEl - .showcase-grid 容器（x-ref="showcaseGrid"）
         * @param {object} params - { duration, stagger, easing, style, reducedMotionSim }
         * @returns {gsap.core.Timeline|null}
         */
        playShowcaseEntry: function (gridEl, params) {
            params = params || {};

            // null guard
            if (!gridEl) return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            // Reduced Motion 降級：瞬間顯示
            if (shouldSkip(params)) {
                gsap.set(cards, { opacity: 1, y: 0, scale: 1 });
                return null;
            }

            var dur = params.duration || 0.5;
            var staggerVal = params.stagger || 0.04;
            var ease = params.easing || 'power3.out';
            var style = params.style || 'stagger';

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

            // 依 style 決定動畫參數
            var fromVars, toVars;
            if (style === 'fadeScale') {
                // C6: 不使用旋轉
                fromVars = { opacity: 0, scale: 0.85 };
                toVars = { opacity: 1, scale: 1, duration: dur, ease: ease, stagger: staggerVal };
            } else if (style === 'fadeUp') {
                fromVars = { opacity: 0, y: 40 };
                toVars = { opacity: 1, y: 0, duration: dur, ease: ease, stagger: staggerVal };
            } else {
                // 預設 stagger
                fromVars = { opacity: 0, y: 20 };
                toVars = { opacity: 1, y: 0, duration: dur, ease: ease, stagger: staggerVal };
            }

            // 設定初始狀態
            gsap.set(visible, fromVars);

            var tl = gsap.timeline({ id: 'showcaseEntry' });
            tl.to(visible, toVars);

            // 動畫結束後清除 inline styles 並初始化 GSDevTools
            tl.eventCallback('onComplete', function () {
                gsap.set(visible, { clearProps: 'transform,opacity' });
                MotionLab.initDevTools(tl);
            });

            return tl;
        },

        /**
         * §5 Ease Roles 並排對比 Demo
         * 三個 box 同時以 fluent / fluent-decel / fluent-accel 播放，讓開發者直觀比較三角色差異。
         * C4: killTweensOf(boxEls)
         * C6: 不使用旋轉
         * C23: shouldSkip reduced-motion guard
         * @param {Element[]} boxEls - 三個 .ease-role-box DOM 元素陣列
         * @param {object} params - Alpine 傳入的 params 物件（含 reducedMotionSim）
         */
        playEaseRolesDemo: function (boxEls, params) {
            params = params || {};

            if (!boxEls || boxEls.length < 3 || boxEls.some(function (el) { return !el; })) return;

            // C4: 清除舊動畫
            gsap.killTweensOf(boxEls);

            // P3 #1: 動態計算 targetX，避免 box 在窄 viewport 跑出 lane 邊界
            // lane.offsetWidth − box width(80px) − start left(12px) − gutter(12px)
            var lane = boxEls[0].parentElement;
            var targetX = lane ? Math.max(0, lane.offsetWidth - 80 - 24) : 200;

            // CSS .ease-role-box 用 transform: translateY(-50%) 做垂直居中。
            // GSAP 寫 inline transform for x 會覆蓋 CSS transform，必須補 yPercent: -50
            // 一起寫進 GSAP 的 transform cache，否則動畫期間 box 會掉到 lane 底邊被裁切。
            // C23: reduced-motion 降級 — 直接跳最終狀態（P2 #2: 改為跳 targetX，非 clearProps）
            if (shouldSkip(params)) {
                gsap.set(boxEls, { x: targetX, yPercent: -50 });
                return;
            }

            // 重播前清乾淨 leftover transform / will-change / opacity，再回起點
            gsap.set(boxEls, { clearProps: 'all' });
            gsap.set(boxEls, { x: 0, yPercent: -50 });

            var dur = window.OpenAver && window.OpenAver.motion && window.OpenAver.motion.DURATION
                ? window.OpenAver.motion.DURATION.emphasis
                : 0.5;

            // 三條同時觸發（Standard / Enter / Exit）
            // yPercent 已在 gsap.set 寫進 transform cache，tween 只動 x 會自動保留 yPercent
            gsap.to(boxEls[0], { x: targetX, duration: dur, ease: 'fluent' });
            gsap.to(boxEls[1], { x: targetX, duration: dur, ease: 'fluent-decel' });
            gsap.to(boxEls[2], { x: targetX, duration: dur, ease: 'fluent-accel' });
        },

        /**
         * §5 Duration Buckets 並排對比 demo
         * 四個 box 同時播放相同 ease（fluent standard），只改 duration
         * C4: killTweensOf(boxEls)
         * C23: shouldSkip reduced-motion guard
         * @param {Element[]} boxEls - 四個 .duration-bucket-box DOM 元素陣列
         * @param {object} params - Alpine 傳入的 params 物件（含 reducedMotionSim）
         */
        playDurationBucketsDemo: function (boxEls, params) {
            params = params || {};

            if (!boxEls || boxEls.length < 4 || boxEls.some(function (el) { return !el; })) return;

            // C4: 清除舊動畫
            gsap.killTweensOf(boxEls);

            var lane = boxEls[0].parentElement;
            var targetX = lane ? Math.max(0, lane.offsetWidth - 60 - 24) : 200;

            if (shouldSkip(params)) {
                gsap.set(boxEls, { x: targetX, yPercent: -50 });
                return;
            }

            gsap.set(boxEls, { clearProps: 'all' });
            gsap.set(boxEls, { x: 0, yPercent: -50 });

            var D = window.OpenAver && window.OpenAver.motion && window.OpenAver.motion.DURATION;
            var fast     = D ? D.fast     : 0.167;
            var medium   = D ? D.medium   : 0.333;
            var emphasis = D ? D.emphasis : 0.5;
            var slow     = 0.3;

            gsap.to(boxEls[0], { x: targetX, duration: fast,     ease: 'fluent' });
            gsap.to(boxEls[1], { x: targetX, duration: medium,   ease: 'fluent' });
            gsap.to(boxEls[2], { x: targetX, duration: emphasis, ease: 'fluent' });
            gsap.to(boxEls[3], { x: targetX, duration: slow,     ease: 'fluent' });
        },
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
        if (typeof CustomEase !== 'undefined') {
            try {
                if (!CustomEase._initted) gsap.registerPlugin(CustomEase);
                CustomEase.create("settle", "M0,0 C0.14,0 0.27,0.87 0.5,1 0.75,1 0.86,0.98 1,1");
                console.log('[MotionLab] CustomEase "settle" 已初始化');
            } catch (e) {
                console.warn('[MotionLab] CustomEase "settle" 初始化失敗:', e);
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
        if (typeof Physics2DPlugin !== 'undefined') {
            try {
                gsap.registerPlugin(Physics2DPlugin, Flip);
                console.log('[MotionLab] Physics2DPlugin 已載入');
            } catch (e) {
                console.warn('[MotionLab] Physics2DPlugin 初始化失敗:', e);
            }
        } else {
            console.warn('[MotionLab] Physics2DPlugin 未載入，picker burst 將降級為純 GSAP tween');
        }
    });

})();
