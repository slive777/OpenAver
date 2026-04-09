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
 *   - playLightboxOpen(lightboxEl, options)             lightbox 進場動畫（backdrop + content + cover）
 *   - playLightboxSwitch(contentEl, direction, options) lightbox 導航 crossfade + micro slide
 *   - playSampleGallerySwitch(imgEl, direction, options) sample gallery 圖片切換 fade+slide（C18/C21）
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

    // A4: 註冊 CustomEase "settle" 曲線（與 motion-lab.js 相同，重複 create 無害）
    // A7-Prod: 註冊 Flip plugin（base.html L452 已載入 CDN）
    document.addEventListener('DOMContentLoaded', function () {
        if (typeof gsap !== 'undefined' && typeof Flip !== 'undefined') {
            gsap.registerPlugin(Flip);
        }
        if (typeof CustomEase !== 'undefined') {
            try {
                if (!CustomEase._initted && typeof gsap !== 'undefined') {
                    gsap.registerPlugin(CustomEase);
                }
                CustomEase.create("settle", "M0,0 C0.14,0 0.27,0.87 0.5,1 0.75,1 0.86,0.98 1,1");
            } catch (e) {
                // settle ease 註冊失敗時 playGridSettle 會 fallback 到 power2.out
            }
        }
    });

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
        },

        /**
         * A7-Prod: Hero Slot Flip 移除 — actressProfile 為 null 時平滑補位
         *
         * Fire-and-forget，不回傳 Promise。
         * 參考 motion-lab.js L929-944，簡化版。
         *
         * @param {object} flipState - Flip.getState() 的回傳值（DOM 變更前捕獲）
         * @param {object} [options] - { duration, ease }
         */
        playHeroRemove: function (flipState, options) {
            options = options || {};
            if (!flipState) return;
            if (typeof Flip === 'undefined') return;
            if (shouldSkip()) return;
            var dur = options.duration || 0.4;
            var ease = options.ease || 'power2.out';
            Flip.from(flipState, {
                duration: dur,
                ease: ease
            });
        },

        /**
         * Grid Settle Pulse：staging exit 完成後，對前 N 排 grid 卡片做極輕微 scale pulse
         * 營造「結果穩定落位」的收尾感。
         *
         * 動畫目標是 .av-card-preview-img（不是 .av-card-preview），
         * 避免覆蓋 .av-card-preview:hover 的 CSS transform。
         * Row bucketing 使用 2px tolerance（Math.round(top/2)*2）。
         *
         * C4：開頭 gsap.killTweensOf 清舊動畫。
         * C6：不使用 rotation，只用 scale。
         *
         * @param {Element} gridEl - .search-grid 容器
         * @param {object} [options] - { duration, scale, ease, rows }
         * @returns {gsap.core.Timeline|null}
         */
        playGridSettle: function (gridEl, options) {
            options = options || {};
            if (!gridEl) return null;
            if (typeof gsap === 'undefined') return null;

            var allCards = gridEl.querySelectorAll('.av-card-preview');
            if (!allCards.length) return null;

            // A4 fix: 過濾 display:none 的卡片（_failed slot），
            // 避免 getBoundingClientRect() 回傳 0-size rect 污染 row bucketing
            var cards = [];
            allCards.forEach(function (card) {
                if (card.offsetHeight > 0) cards.push(card);
            });
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
            if (shouldSkip()) {
                gsap.set(imgTargets, { scale: 1 });
                return null;
            }

            var dur = options.duration || 0.8;
            var scaleVal = options.scale || 1.06;
            var ease = options.ease || 'settle';
            var rowCount = options.rows || 3;

            // CustomEase fallback：若 settle ease 未註冊，fallback 到 power2.out
            if (ease === 'settle' && typeof CustomEase === 'undefined') {
                ease = 'power2.out';
            }

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

            // C6: 不使用 rotationX/Y/Z，只用 scale

            // C21: clearProps 防護 — 清除 inline transform，避免與 CSS transition 衝突
            tl.eventCallback('onComplete', function () {
                targetKeys.forEach(function (key) {
                    gsap.set(rowMap[key], { clearProps: 'transform' });
                });
            });

            // C18: onInterrupt — killTweensOf 打斷時 onComplete 不會觸發，
            // 需要同樣清除 inline transform 避免殘留
            tl.eventCallback('onInterrupt', function () {
                targetKeys.forEach(function (key) {
                    gsap.set(rowMap[key], { clearProps: 'transform' });
                });
            });

            return tl;
        },

        // ===== D2: Lightbox Animations =====

        /**
         * Lightbox 進場動畫：backdrop 淡入 + content scale pop-in + cover 上滑淡入
         *
         * C4：開頭 killTweensOf 清舊動畫。
         * C6：不使用 rotation。
         * C21：用 .gsap-animating class 暫時關掉 CSS transition。
         *
         * @param {Element} lightboxEl - .showcase-lightbox 元素
         * @param {object} [options] - { onComplete }
         * @returns {gsap.core.Timeline|null}
         */
        playLightboxOpen: function (lightboxEl, options) {
            options = options || {};

            if (!lightboxEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (shouldSkip()) return null;

            var content = lightboxEl.querySelector('.lightbox-content');
            var coverImg = lightboxEl.querySelector('.lightbox-cover img');

            // C4: 清除舊動畫
            gsap.killTweensOf(lightboxEl);
            if (content) gsap.killTweensOf(content);
            if (coverImg) gsap.killTweensOf(coverImg);

            // C21: 暫時關掉 CSS transition
            lightboxEl.classList.add('gsap-animating');

            var tl = gsap.timeline({
                id: 'lightboxOpen',
                onComplete: function () {
                    lightboxEl.classList.remove('gsap-animating');
                    if (typeof options.onComplete === 'function') options.onComplete();
                },
                onInterrupt: function () {
                    lightboxEl.classList.remove('gsap-animating');
                }
            });

            // 1. Backdrop fade-in
            tl.fromTo(lightboxEl,
                { opacity: 0 },
                { opacity: 1, duration: 0.16, ease: 'power2.out' }
            );

            // 2. Content card scale pop-in
            if (content) {
                tl.fromTo(content,
                    { scale: 0.92, opacity: 0 },
                    { scale: 1, opacity: 1, duration: 0.18, ease: 'back.out(1.2)' },
                    0.03
                );
            }

            // 3. Cover image slide-up fade-in
            if (coverImg) {
                tl.fromTo(coverImg,
                    { y: 12, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.16, ease: 'power2.out' },
                    '-=0.08'
                );
            }

            return tl;
        },

        /**
         * Lightbox 導航切換動畫：crossfade + micro slide
         *
         * direction: 'next' 從右進，'prev' 從左進（對齊 playSlideIn 方向感）。
         * B19: 單相 slide-in（state-first 後 DOM 已是新內容，fade-out 會造成反向閃爍）。
         *
         * C4：開頭 killTweensOf 清舊動畫。
         * C6：不使用 rotation。
         * C21：用 .gsap-animating class 暫時關掉 CSS transition。
         *
         * @param {Element} contentEl - .lightbox-content 元素
         * @param {'next'|'prev'} direction - 切換方向
         * @param {object} [options] - { onComplete }
         * @returns {gsap.core.Timeline|null}
         */
        playLightboxSwitch: function (contentEl, direction, options) {
            options = options || {};

            if (!contentEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (shouldSkip()) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(contentEl);

            // C21: 暫時關掉 CSS transition（contentEl 的 x 映射到 transform）
            var lightboxEl = contentEl.closest('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.add('gsap-animating');

            var xIn = direction === 'next' ? 20 : -20;

            var tl = gsap.timeline({
                id: 'lightboxSwitch',
                onComplete: function () {
                    if (lightboxEl) lightboxEl.classList.remove('gsap-animating');
                    if (typeof options.onComplete === 'function') options.onComplete();
                },
                onInterrupt: function () {
                    if (lightboxEl) lightboxEl.classList.remove('gsap-animating');
                }
            });

            // B19: 單相 slide-in（state-first 後 DOM 已是新內容，fade-out 會造成反向閃爍）
            tl.fromTo(contentEl,
                { opacity: 0, x: xIn },
                { opacity: 1, x: 0, duration: 0.25, ease: 'power2.out' }
            );

            return tl;
        },

        /**
         * T8: Sample Gallery 圖片切換動畫（fade + micro slide）
         *
         * C18: killTweensOf 打斷舊動畫（不用 isNavigating lock）
         * C21: .gsap-animating class 暫時關掉 CSS transition
         *
         * @param {Element} imgEl - .sg-main-img 元素
         * @param {'next'|'prev'} direction - 切換方向
         * @param {object} [options] - { onComplete }
         * @returns {gsap.core.Tween|null}
         */
        playSampleGallerySwitch: function (imgEl, direction, options) {
            options = options || {};

            if (!imgEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (shouldSkip()) return null;

            // C18: 打斷舊動畫
            gsap.killTweensOf(imgEl);

            // C21: 暫時關掉 imgEl 的 CSS transition
            imgEl.classList.add('gsap-animating');

            var xIn = direction === 'next' ? 30 : -30;

            var tween = gsap.fromTo(imgEl,
                { opacity: 0, x: xIn },
                {
                    opacity: 1,
                    x: 0,
                    duration: 0.22,
                    ease: 'power2.out',
                    clearProps: 'transform,opacity',
                    onComplete: function () {
                        imgEl.classList.remove('gsap-animating');
                        if (typeof options.onComplete === 'function') options.onComplete();
                    },
                    onInterrupt: function () {
                        imgEl.classList.remove('gsap-animating');
                    }
                }
            );

            return tween;
        },

        /**
         * T2a: 單片整理成功動畫 — checkmark pop-in + row 綠色 flash
         *
         * C4/C18: killTweensOf 先打斷舊動畫
         * shouldSkip() guard: prefers-reduced-motion 時直接 return null
         *
         * @param {Element|null} btnEl - 可見的 .btn-scrape-single 按鈕元素
         * @param {Element|null} rowEl - .file-item row 元素
         * @returns {null}
         */
        playOrganizeSuccess: function (btnEl, rowEl) {
            if (typeof gsap === 'undefined') return null;
            gsap.killTweensOf(btnEl);
            if (rowEl) gsap.killTweensOf(rowEl);
            if (shouldSkip()) return null;

            // checkmark pop-in
            if (btnEl) {
                gsap.fromTo(btnEl,
                    { scale: 0, opacity: 0 },
                    { scale: 1, opacity: 1, duration: 0.35, ease: 'back.out(1.7)', clearProps: 'transform,opacity' }
                );
            }

            // row green flash
            if (rowEl) {
                gsap.fromTo(rowEl,
                    { backgroundColor: 'rgba(0, 200, 100, 0.15)' },
                    { backgroundColor: 'transparent', duration: 0.8, ease: 'power2.out', clearProps: 'backgroundColor' }
                );
            }
        },

        /**
         * T2a: 單片整理失敗動畫 — 按鈕 shake
         *
         * C4/C18: killTweensOf 先打斷舊動畫
         * shouldSkip() guard: prefers-reduced-motion 時直接 return null
         *
         * @param {Element|null} btnEl - 可見的 .btn-scrape-single 按鈕元素
         * @returns {null}
         */
        playOrganizeFail: function (btnEl) {
            if (typeof gsap === 'undefined') return null;
            gsap.killTweensOf(btnEl);
            if (shouldSkip()) return null;

            if (btnEl) {
                gsap.fromTo(btnEl,
                    { x: -4 },
                    { x: 4, duration: 0.08, repeat: 3, yoyo: true, ease: 'power1.inOut', clearProps: 'transform' }
                );
            }
        }
    };
})();
