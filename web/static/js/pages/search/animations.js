/**
 * SearchAnimations — /search 頁面動畫模組
 *
 * 暴露 window.SearchAnimations 物件，提供：
 *   - playMiniBurst(cards, stagingEl, options)  mini-burst 偏移飛行（C14）
 *   - playCoverSwap(imgEl)                       staging card 封面替換動畫
 *   - playStagingEntry(stagingEl)                staging card 進場 morph
 *   - playStagingExit(stagingEl, options)         staging card 退場 morph + onComplete
 *   - playGridFadeIn(gridEl)                     skeleton grid 整體轉場淡入（保留）
 *   - playDetailEntry(detailEl, options)          detail 進場（cover slide-in + info fade-in）
 *   - playGridToDetail(fromRect, detailEl, options)  Grid→Detail ghost 轉場
 *   - playDetailToGrid(fromRect, targetCardEl, options)  Detail→Grid ghost 飛回
 *   - playSlideIn(containerEl, direction)              detail 導航滑入動畫（C18 interrupt）
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

    // ===== U4: Ghost Helpers (private to IIFE) =====

    /**
     * 清除所有殘留的 ghost 元素（防止 re-entrant 呼叫留下殘影）
     */
    function cleanupStaleGhosts() {
        // 先還原所有被 ghost 動畫隱藏的真實封面 opacity
        var hidden = document.querySelectorAll('[data-ghost-hidden]');
        hidden.forEach(function (el) {
            el.style.opacity = '1';
            el.removeAttribute('data-ghost-hidden');
        });

        // 再移除殘留 ghost
        var stale = document.querySelectorAll('[data-search-ghost]');
        stale.forEach(function (el) { el.remove(); });
    }

    /**
     * 建立封面 ghost img 節點，append 到 body
     * 移植自 motion-lab.js L340-370，適配 /search
     * @param {string} src - 圖片來源 URL
     * @param {DOMRect} rect - 來源元素的 bounding rect
     * @returns {HTMLImageElement|null} ghost element，或 null（建立失敗）
     */
    function createCoverGhost(src, rect) {
        if (!src || !rect || rect.width === 0 || rect.height === 0) return null;

        // 清除殘留 ghost
        cleanupStaleGhosts();

        var ghost = document.createElement('img');
        ghost.src = src;
        ghost.setAttribute('data-search-ghost', 'true');
        ghost.style.position = 'fixed';
        ghost.style.left = '0';
        ghost.style.top = '0';
        ghost.style.margin = '0';
        ghost.style.pointerEvents = 'none';
        ghost.style.zIndex = '2000';
        ghost.style.willChange = 'transform, width, height';
        ghost.style.transformOrigin = 'top left';
        ghost.style.borderRadius = '8px';
        ghost.style.objectFit = 'cover';

        document.body.appendChild(ghost);

        // 以 GSAP 定位至來源位置
        if (typeof gsap !== 'undefined') {
            gsap.set(ghost, {
                x: rect.left,
                y: rect.top,
                width: rect.width,
                height: rect.height,
                boxShadow: '0 4px 16px rgba(0,0,0,0.25)'
            });
        }

        return ghost;
    }

    /**
     * 清除 ghost 並還原真實封面 opacity
     * @param {HTMLImageElement} ghost - ghost 元素
     * @param {...Element} restoreEls - 要還原 opacity 的元素
     */
    function cleanupGhost(ghost) {
        var restoreEls = Array.prototype.slice.call(arguments, 1);
        if (ghost && ghost.parentNode) {
            ghost.remove();
        }
        if (typeof gsap !== 'undefined' && restoreEls.length) {
            var valid = restoreEls.filter(Boolean);
            if (valid.length) {
                gsap.set(valid, { opacity: 1 });
                valid.forEach(function (el) {
                    el.removeAttribute('data-ghost-hidden');
                });
            }
        }
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
        },

        // ===== U4: Detail Entry + Ghost Transition =====

        /**
         * Detail 進場：封面左滑入 + info 下淡入
         * 移植自 motion-lab.js L253-296，適配 /search DOM
         *
         * @param {Element} detailEl - .av-card-full 容器
         * @param {object} [options] - { skipCover: boolean }
         * @returns {gsap.core.Timeline|null}
         */
        playDetailEntry: function (detailEl, options) {
            options = options || {};

            if (!detailEl) return null;
            if (typeof gsap === 'undefined') return null;

            // 防禦：清除前一次 ghost 動畫殘留的 opacity:0 / data-ghost-hidden
            cleanupStaleGhosts();

            var cover = detailEl.querySelector('.av-card-full-cover');
            var info = detailEl.querySelector('.av-card-full-info');

            // C4: 清除舊動畫
            if (cover) gsap.killTweensOf(cover);
            if (info) gsap.killTweensOf(info);

            // Reduced Motion 降級：瞬間到位
            if (shouldSkip()) {
                if (cover) gsap.set(cover, { x: 0, opacity: 1 });
                if (info) gsap.set(info, { y: 0, opacity: 1 });
                return null;
            }

            var dur = 0.6;
            var ease = 'power3.out';
            var skipCover = options.skipCover === true;

            var tl = gsap.timeline({ id: 'searchDetailEntry' });

            // C6: 不使用 rotationX/Y/Z
            if (cover && !skipCover) {
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

            return tl;
        },

        /**
         * Grid→Detail ghost 轉場：ghost 封面從 grid 位置飛到 detail 位置
         * 飛行完成後接 playDetailEntry(skipCover: true)
         *
         * @param {DOMRect} fromRect - 來源 grid 卡片封面的 bounding rect（state 變前捕獲）
         * @param {Element} detailEl - .av-card-full 容器（$nextTick 後取得）
         * @param {object} [options] - { coverSrc: string }
         * @returns {gsap.core.Timeline|null}
         */
        playGridToDetail: function (fromRect, detailEl, options) {
            options = options || {};

            if (!detailEl) return null;
            if (typeof gsap === 'undefined') return null;

            // Reduced Motion：跳過 ghost，直接 detail entry（也會被 skip）
            if (shouldSkip()) {
                return this.playDetailEntry(detailEl);
            }

            // 找 detail 封面 img 取得 toRect
            var detailImg = detailEl.querySelector('.av-card-full-cover-img');
            if (!detailImg) {
                // fallback: 無目標 → full detail entry
                return this.playDetailEntry(detailEl);
            }

            var toRect = detailImg.getBoundingClientRect();
            if (!toRect || toRect.width === 0 || toRect.height === 0) {
                return this.playDetailEntry(detailEl);
            }

            // 建立 ghost
            var coverSrc = options.coverSrc || detailImg.src;
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) {
                // ghost 建立失敗 → full detail entry
                return this.playDetailEntry(detailEl);
            }

            // 飛行期間隱藏 source（已消失）和 target cover
            detailImg.setAttribute('data-ghost-hidden', '');
            gsap.set(detailImg, { opacity: 0 });

            var self = this;
            var dur = 0.38;
            var ease = 'power2.inOut';

            // C4: 清除 ghost 舊動畫（re-entrant safety）
            gsap.killTweensOf(ghost);

            var tl = gsap.timeline({ id: 'searchGridToDetail' });

            // 主飛行 tween（位置 + 大小）
            tl.fromTo(ghost,
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
                    onComplete: function () {
                        // cleanup ghost + restore opacity
                        cleanupGhost(ghost, detailImg);
                        // chain: detail entry (skipCover，ghost 已處理封面動畫)
                        self.playDetailEntry(detailEl, { skipCover: true });
                    }
                }
            );

            // 陰影 keyframes：起飛 → 強化 → 落地
            gsap.to(ghost, {
                keyframes: [
                    { boxShadow: '0 12px 32px rgba(0,0,0,0.40)', duration: dur * 0.5 },
                    { boxShadow: '0 2px 8px rgba(0,0,0,0.15)', duration: dur * 0.5 }
                ],
                ease: 'none'
            });

            return tl;
        },

        /**
         * Detail→Grid ghost 飛回：ghost 封面從 detail 飛回 grid 卡片位置
         * 飛行完成後觸發 target settle
         *
         * @param {DOMRect} fromRect - 來源 detail 封面的 bounding rect（state 變前捕獲）
         * @param {Element} targetCardEl - .av-card-preview[data-slot] 元素（$nextTick 後取得）
         * @param {object} [options] - { coverSrc: string }
         */
        playDetailToGrid: function (fromRect, targetCardEl, options) {
            options = options || {};

            if (!targetCardEl) return;
            if (typeof gsap === 'undefined') return;

            // Reduced Motion：no-op（state 已翻轉）
            if (shouldSkip()) return;

            // 找 target 卡片封面 img
            var targetImg = targetCardEl.querySelector('.av-card-preview-img img');
            if (!targetImg) return;

            var toRect = targetImg.getBoundingClientRect();
            if (!toRect || toRect.width === 0 || toRect.height === 0) return;

            // 建立 ghost
            var coverSrc = options.coverSrc || targetImg.src;
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) return;

            // 飛行期間隱藏 target cover
            targetImg.setAttribute('data-ghost-hidden', '');
            gsap.set(targetImg, { opacity: 0 });

            var dur = 0.38;
            var ease = 'power2.inOut';

            // C4: 清除 ghost 舊動畫
            gsap.killTweensOf(ghost);

            // 主飛行 tween
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
                    onComplete: function () {
                        // cleanup ghost + restore target opacity
                        cleanupGhost(ghost, targetImg);
                        // target settle: micro scale pulse
                        gsap.fromTo(targetCardEl,
                            { scale: 1.02 },
                            { scale: 1, duration: 0.18, ease: 'power2.out' }
                        );
                    }
                }
            );

            // 陰影 keyframes
            gsap.to(ghost, {
                keyframes: [
                    { boxShadow: '0 12px 32px rgba(0,0,0,0.40)', duration: dur * 0.5 },
                    { boxShadow: '0 2px 8px rgba(0,0,0,0.15)', duration: dur * 0.5 }
                ],
                ease: 'none'
            });
        },

        // ===== U5: Detail Navigation Slide =====

        /**
         * Detail 導航滑入動畫（C18 interrupt 策略）
         * 移植自 motion-lab.js L546-568，適配 /search
         *
         * @param {Element} containerEl - .av-card-full 容器
         * @param {'next'|'prev'} direction - 'next' 從右滑入，'prev' 從左滑入
         * @returns {gsap.core.Tween|null}
         */
        playSlideIn: function (containerEl, direction) {
            if (!containerEl) return null;
            if (typeof gsap === 'undefined') return null;

            // 防禦：清除前一次 ghost 動畫殘留的 opacity:0 / data-ghost-hidden
            cleanupStaleGhosts();

            // C4: 清除舊動畫（C18 interrupt 核心 — 打斷殘留 tween）
            gsap.killTweensOf(containerEl);

            // C4: also kill child tweens left by playDetailEntry (cover/info have separate tweens)
            var cover = containerEl.querySelector('.av-card-full-cover');
            var info = containerEl.querySelector('.av-card-full-info');
            if (cover) gsap.killTweensOf(cover);
            if (info) gsap.killTweensOf(info);

            // Reduced Motion 降級：瞬間到位
            if (shouldSkip()) {
                gsap.set(containerEl, { x: 0, opacity: 1 });
                return null;
            }

            // C6: 不使用 rotationX/Y/Z
            var xFrom = direction === 'next' ? 40 : -40;

            return gsap.fromTo(containerEl,
                { x: xFrom, opacity: 0 },
                { x: 0, opacity: 1, duration: 0.3, ease: 'power3.out' }
            );
        }
    };
})();
