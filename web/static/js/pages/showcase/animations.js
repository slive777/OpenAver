/**
 * ShowcaseAnimations — /showcase 頁面動畫模組
 *
 * 暴露 window.ShowcaseAnimations 物件，提供：
 *   - playEntry(gridEl, params)                B6: 進場動畫（B13 後也用於翻頁）
 *   - capturePositions(gridEl)                  B12: 捕獲手動位置快照（B15 恢復 core.js 呼叫）
 *   - playFlipReorder(gridEl, positionMap, params) B12: 排序洗牌手動動畫（B15 恢復 core.js 呼叫）
 *   - playFlipFilter(gridEl, state, params)     B8: 篩選進出場 Flip 動畫（B15 恢復 core.js 呼叫）
 *   - captureFlipState(gridEl)                  B8: 捕獲 Flip 狀態快照（B15 恢復 core.js 呼叫）
 *   - playModeCrossfade(oldMode, newMode, params) B10: 模式切換 crossfade
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
        /**
         * 初次載入 settle 動畫 — 卡片 scale 脈衝「落定」
         * 不碰 opacity → 不閃。用於 init() / retry() 等已 paint 的場景。
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {Object} params - { duration, scale, rows }
         * @returns {gsap.core.Timeline|null}
         */
        playSettle: function (gridEl, params) {
            params = params || {};

            if (!gridEl) return null;
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(cards);

            if (shouldSkip()) return null;

            var dur = params.duration || 0.8;
            var scaleVal = params.scale || 1.06;
            var maxRows = params.rows || 3;
            var ease = (typeof CustomEase !== 'undefined' && gsap.parseEase('showcaseSettle'))
                ? 'showcaseSettle' : 'power2.out';

            // Row bucketing：依 top 位置分組（2px 容差）
            var viewportH = window.innerHeight;
            var buckets = [];
            Array.from(cards).forEach(function (card) {
                var rect = card.getBoundingClientRect();
                if (rect.top >= viewportH) return;  // fold 以下跳過
                var img = card.querySelector('.av-card-preview-img');
                if (!img) return;
                var top = Math.round(rect.top);
                var found = false;
                for (var b = 0; b < buckets.length; b++) {
                    if (Math.abs(buckets[b].top - top) < 2) {
                        buckets[b].imgs.push(img);
                        found = true;
                        break;
                    }
                }
                if (!found) buckets.push({ top: top, imgs: [img] });
            });

            // 依 top 排序
            buckets.sort(function (a, b) { return a.top - b.top; });

            // 只取前 maxRows 行
            var rows = buckets.slice(0, maxRows);
            if (!rows.length) return null;

            var tl = gsap.timeline({ id: 'showcaseSettle' });

            rows.forEach(function (row, rowIdx) {
                // C4: 清除 img 上的舊動畫
                gsap.killTweensOf(row.imgs);
                tl.fromTo(row.imgs,
                    { scale: scaleVal },
                    { scale: 1, duration: dur, ease: ease },
                    rowIdx * 0.06  // 行間 stagger 60ms
                );
            });

            tl.eventCallback('onComplete', function () {
                rows.forEach(function (row) {
                    gsap.set(row.imgs, { clearProps: 'transform' });
                });
            });

            return tl;
        },

        playEntry: function (gridEl, params) {
            params = params || {};

            // null guard
            if (!gridEl) return null;

            // GSAP guard（CDN 故障降級）
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview, .actress-card');
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
                gsap.set(offscreen, { clearProps: 'transform,opacity' });
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
         * B12: 排序洗牌手動動畫（取代 Flip reorder）
         * @param {Element} gridEl - .showcase-grid 容器
         * @param {Map} positionMap - capturePositions 回傳的位置快照
         * @param {Object} params - 動畫參數
         * @returns {gsap.core.Timeline|null}
         */
        playFlipReorder: function (gridEl, positionMap, params) {
            params = params || {};

            // null guard
            if (!gridEl || !positionMap) return null;

            // GSAP guard
            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview, .actress-card');
            if (!cards.length) return null;

            // Reduced Motion 降級
            if (shouldSkip()) return null;

            // C18: 中斷進行中的動畫
            gsap.killTweensOf(cards);

            var dur = params.duration || 0.5;
            var ease = params.ease || 'power2.inOut';

            // 計算 delta 並收集需要動畫的卡片
            var tweens = [];
            Array.from(cards).forEach(function (card) {
                var id = card.getAttribute('data-flip-id');
                if (!id) return;
                var oldRect = positionMap.get(id);
                if (!oldRect) return;
                var newRect = card.getBoundingClientRect();
                var dx = oldRect.left - newRect.left;
                var dy = oldRect.top - newRect.top;
                // delta 為 0 跳過
                if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return;
                tweens.push({ card: card, dx: dx, dy: dy });
            });

            if (!tweens.length) return null;

            var tl = gsap.timeline({
                id: 'showcaseReorder',
                onComplete: function () {
                    gridEl.classList.remove('flip-guard');
                }
            });
            tweens.forEach(function (t) {
                tl.fromTo(t.card,
                    { x: t.dx, y: t.dy },
                    { x: 0, y: 0, duration: dur, ease: ease, clearProps: 'transform' },
                    0  // all start at time 0
                );
            });

            return tl;
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

            var cards = gridEl.querySelectorAll('.av-card-preview, .actress-card');
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
                    // B18: 大量新卡片同時進場 → 純 fade + stagger（無 scale，降低視覺混亂）
                    if (els.length > 10) {
                        return gsap.fromTo(els,
                            { opacity: 0 },
                            { opacity: 1, duration: dur * 0.6, stagger: 0.02, ease: 'power2.out' }
                        );
                    }
                    // 預設：scale + fade（少量卡片進場時效果好）
                    return gsap.fromTo(els,
                        { opacity: 0, scale: 0.85 },
                        { opacity: 1, scale: 1, duration: dur * 0.8, ease: 'power2.out' }
                    );
                },
                onLeave: function (els) {
                    return gsap.to(els, { opacity: 0, scale: 0.85, duration: dur * 0.6, ease: 'power2.in' });
                },
                onComplete: function () {
                    gsap.set(cards, { clearProps: 'transform' });
                    gridEl.classList.remove('flip-guard');
                }
            });
        },

        /**
         * B12: 捕獲手動位置快照（排序用，取代 Flip reorder）
         * @param {Element} gridEl - .showcase-grid 容器
         * @returns {Map|null} Map<string, DOMRect>
         */
        capturePositions: function (gridEl) {
            if (!gridEl) return null;
            var cards = gridEl.querySelectorAll('.av-card-preview, .actress-card');
            if (!cards.length) return null;
            var map = new Map();
            Array.from(cards).forEach(function (card) {
                var id = card.getAttribute('data-flip-id');
                if (id) {
                    map.set(id, card.getBoundingClientRect());
                }
            });
            return map.size ? map : null;
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
         * B10: 模式切換 crossfade
         * @param {string} oldMode - 離場模式名稱 ('grid'|'table'|'list')
         * @param {string} newMode - 進場模式名稱 ('grid'|'table'|'list')
         * @param {Object} params - 動畫參數（保留擴展性）
         * @returns {gsap.core.Tween|null}
         */
        playModeCrossfade: function (oldMode, newMode, params, callbacks) {
            var hasCb = !!(callbacks && callbacks.onOldFadeComplete);
            if (shouldSkip()) {
                if (hasCb) callbacks.onOldFadeComplete();
                return null;
            }
            if (typeof gsap === 'undefined') {
                if (hasCb) callbacks.onOldFadeComplete();
                return null;
            }

            var selectors = {
                grid: '.showcase-grid',
                actress: '.actress-grid',
                table: '.showcase-table-wrapper',
                list: '.showcase-list-wrapper'
            };

            var oldEl = oldMode ? document.querySelector(selectors[oldMode]) : null;
            var newEl = newMode ? document.querySelector(selectors[newMode]) : null;

            var tl = gsap.timeline();
            // Phase 1: oldEl fade-out（只在有 callback 時觸發，避免破壞舊 caller 行為）
            if (hasCb) {
                if (oldEl) {
                    tl.to(oldEl, {
                        opacity: 0,
                        duration: 0.15,
                        ease: 'power2.in',
                        clearProps: 'opacity',
                        onComplete: function () { callbacks.onOldFadeComplete(); }
                    });
                } else {
                    callbacks.onOldFadeComplete();
                }
            }
            // Phase 2: newEl fade-in（舊 caller 行為保留）
            if (newEl) {
                tl.fromTo(newEl,
                    { opacity: 0 },
                    { opacity: 1, duration: 0.2, ease: 'power2.out', clearProps: 'opacity' }
                );
            }
            return tl;
        },

        /**
         * B16: Lightbox 進場動畫 — backdrop 淡入 + content scale pop-in + cover slide-up
         *
         * C4: killTweensOf 清舊動畫
         * C6: 不使用 rotation
         * C21: .gsap-animating class 暫時關掉 CSS transition
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
            if (!lightboxEl.classList.contains('gsap-animating')) {
                lightboxEl.classList.add('gsap-animating');
            }

            var tl = gsap.timeline({
                id: 'showcaseLightboxOpen',
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
                    { scale: 0.95, opacity: 0, transformOrigin: 'center center' },
                    { scale: 1, opacity: 1, duration: 0.18, ease: 'power2.out', transformOrigin: 'center center' },
                    0.03
                );
            }

            // 3. Cover image slide-up fade-in（ghost fly 時跳過）
            if (coverImg && !options.skipCover) {
                tl.fromTo(coverImg,
                    { y: 12, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.16, ease: 'power2.out' },
                    '-=0.08'
                );
            }

            return tl;
        },

        /**
         * B19: Lightbox 導航切換動畫 — 單相 slide-in
         *
         * direction: 'next' 從右進，'prev' 從左進。
         * State-first 後 DOM 已是新內容，fade-out 會造成反向閃爍，故改為單相 slide-in。
         *
         * C4: killTweensOf 清舊動畫
         * C6: 不使用 rotation
         * C21: .gsap-animating class 暫時關掉 CSS transition
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
                id: 'showcaseLightboxSwitch',
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
         * T20: C18 interrupt — kill lightbox timelines
         *
         * 封裝 lightboxOpen / lightboxSwitch 兩條 timeline 的 kill 邏輯，
         * 確保 core.js 不直接依賴 GSAP 內部 timeline ID。
         *
         * @param {object} [options] - { killOpen: true, killSwitch: true }
         */
        killLightboxAnimations: function (options) {
            options = options || {};
            var killOpen = options.killOpen !== false;
            var killSwitch = options.killSwitch !== false;
            if (typeof gsap === 'undefined') return;
            if (killOpen) gsap.getById('showcaseLightboxOpen')?.kill();
            if (killSwitch) gsap.getById('showcaseLightboxSwitch')?.kill();
        },

        /**
         * T5: Hero Card 出現動畫 — fade-in + slide-down from above
         *
         * Graceful fallback: GSAP 未載入或 shouldSkip() → return null，Alpine x-show 維持正常顯示。
         * C4: killTweensOf 清舊動畫（避免重複搜尋時堆疊）
         * clearProps: 動畫結束後清除 inline style（不污染 Alpine x-show 控制的 opacity/transform）
         *
         * @param {Element} el - .hero-card 元素
         * @returns {gsap.core.Tween|null}
         */
        playHeroCardAppear: function (el) {
            if (!el) return null;
            if (typeof gsap === 'undefined') return null;

            // C4: 清除舊動畫
            gsap.killTweensOf(el);

            if (shouldSkip()) return null;

            return gsap.fromTo(el,
                { opacity: 0, y: -20 },
                {
                    opacity: 1,
                    y: 0,
                    duration: 0.3,
                    ease: 'power2.out',
                    clearProps: 'transform,opacity'
                }
            );
        },

        /**
         * T7: Sample Gallery 圖片切換動畫
         *
         * C18: killTweensOf — 打斷舊動畫
         * C21: gsap-animating guard — 動畫期間禁用 CSS transition
         * Reduced Motion: shouldSkip() 降級（無動畫，state 已更新，圖片立即切換）
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

            // C21: 暫時關掉 imgEl 的 CSS transition（imgEl 本身有 transition）
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
         * 49a-T1/T7：容器 fade-in（opacity 0 → 1）
         * 用途：x-if 重新掛載新容器後在 $nextTick 內呼叫，與 playModeCrossfade
         * 的 oldEl fade-out 階段配對。caller 必須是被新掛載到 DOM 的元素。
         * reduced-motion 與 gsap undefined 時直接 no-op。
         */
        playContainerFadeIn: function (el, options) {
            options = options || {};
            if (!el) return null;
            if (typeof gsap === 'undefined') return null;
            if (shouldSkip()) return null;
            var dur = (typeof options.duration === 'number') ? options.duration : 0.2;
            var ease = options.ease || 'power2.out';
            return gsap.fromTo(el,
                { opacity: 0 },
                { opacity: 1, duration: dur, ease: ease, clearProps: 'opacity' }
            );
        },

        /**
         * 49a-T7 降級：來源圖輕微 pulse（scale 1.05 yoyo）
         * 用途：ghost fly 降級時對來源圖做視覺回饋，告知用戶點擊已被處理。
         * gsap undefined 或 reduced-motion 時直接 no-op。
         */
        playSourcePulse: function (el, options) {
            options = options || {};
            if (!el) return null;
            if (typeof gsap === 'undefined') return null;
            if (shouldSkip()) return null;
            var scale = (typeof options.scale === 'number') ? options.scale : 1.05;
            var dur = (typeof options.duration === 'number') ? options.duration : 0.1;
            return gsap.to(el, {
                scale: scale,
                duration: dur,
                yoyo: true,
                repeat: 1,
                ease: 'power2.inOut'
            });
        }
    };

    // 暴露全域物件
    window.ShowcaseAnimations = ShowcaseAnimations;
})();
