(function () {
    'use strict';

    /**
     * GhostFly — 跨頁面共用的封面 ghost 飛行動畫模組
     *
     * 提供 Grid ↔ Lightbox 封面飛行動畫，
     * 以及底層 ghost 節點管理工具函式。
     *
     * 使用方式：
     *   window.GhostFly.playGridToLightbox(fromRect, lightboxEl, options)
     *   window.GhostFly.playLightboxToGrid(fromRect, targetCardEl, options)
     */

    // ─── Ghost 節點管理工具 ────────────────────────────────────────────────

    /**
     * 還原所有被 ghost 動畫隱藏的真實封面，並移除殘留 ghost 節點
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

    // ─── 公開動畫函式 ──────────────────────────────────────────────────────

    var GhostFly = {
        createCoverGhost: createCoverGhost,
        cleanupGhost: cleanupGhost,
        cleanupStaleGhosts: cleanupStaleGhosts,

        /**
         * Grid → Lightbox ghost fly
         * @param {DOMRect} fromRect - grid 卡片封面的 bounding rect（state 變前捕獲）
         * @param {Element} lightboxEl - .showcase-lightbox 元素（$nextTick 後）
         * @param {object} [options] - { coverSrc, onComplete }
         * @returns {gsap.Timeline|null}
         */
        playGridToLightbox: function (fromRect, lightboxEl, options) {
            options = options || {};
            if (!lightboxEl || !fromRect) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }
            if (typeof gsap === 'undefined') {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }
            if (window.OpenAver && window.OpenAver.prefersReducedMotion) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            var lbImg = lightboxEl.querySelector('.lightbox-cover img');
            if (!lbImg) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            var toRect = lbImg.getBoundingClientRect();
            if (!toRect || toRect.width === 0) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            var coverSrc = options.coverSrc || lbImg.src;
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }

            // 隱藏真實 lightbox 封面（ghost 飛行期間）
            lbImg.setAttribute('data-ghost-hidden', '');
            gsap.set(lbImg, { opacity: 0 });

            var dur = 0.38;
            var ease = 'power2.inOut';

            var tl = gsap.timeline({ id: 'ghostGridToLightbox' });
            tl.fromTo(ghost,
                { x: fromRect.left, y: fromRect.top, width: fromRect.width, height: fromRect.height },
                {
                    x: toRect.left, y: toRect.top, width: toRect.width, height: toRect.height,
                    duration: dur, ease: ease,
                    onComplete: function () {
                        cleanupGhost(ghost, lbImg);
                        if (typeof options.onComplete === 'function') options.onComplete();
                    }
                }
            );
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
         * Lightbox → Grid ghost fly-back
         * @param {DOMRect} fromRect - lightbox 封面的 bounding rect（lightboxOpen = false 前捕獲）
         * @param {Element} targetCardEl - 目標 grid 卡片元素
         * @param {object} [options] - { coverSrc }
         * @returns {null} fire-and-forget
         */
        playLightboxToGrid: function (fromRect, targetCardEl, options) {
            options = options || {};
            if (!fromRect || !targetCardEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (window.OpenAver && window.OpenAver.prefersReducedMotion) return null;

            if (!fromRect.width || fromRect.width === 0) return null;

            // 判斷目標卡片是否在 viewport 內
            var targetImg = targetCardEl.querySelector('.av-card-preview-img img, .actress-card-photo img');
            if (!targetImg) return null;

            var toRect = targetImg.getBoundingClientRect();
            if (!toRect || toRect.width === 0) return null;

            var viewportH = window.innerHeight;
            var viewportW = window.innerWidth;
            var inViewport = (
                toRect.top < viewportH && toRect.bottom > 0 &&
                toRect.left < viewportW && toRect.right > 0
            );

            if (!inViewport) {
                // 退化：直接 fade-out（不強制 scroll）
                return null;
            }

            var coverSrc = options.coverSrc || targetImg.src;
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) return null;

            // 隱藏 target cover 直到 ghost 到達
            targetImg.setAttribute('data-ghost-hidden', '');
            gsap.set(targetImg, { opacity: 0 });

            var dur = 0.38;
            var ease = 'power2.inOut';

            gsap.killTweensOf(ghost);
            gsap.fromTo(ghost,
                { x: fromRect.left, y: fromRect.top, width: fromRect.width, height: fromRect.height },
                {
                    x: toRect.left, y: toRect.top, width: toRect.width, height: toRect.height,
                    duration: dur, ease: ease,
                    onComplete: function () {
                        cleanupGhost(ghost, targetImg);
                        gsap.fromTo(targetCardEl,
                            { scale: 1.02 },
                            { scale: 1, duration: 0.18, ease: 'power2.out' }
                        );
                    }
                }
            );
            gsap.to(ghost, {
                keyframes: [
                    { boxShadow: '0 12px 32px rgba(0,0,0,0.40)', duration: dur * 0.5 },
                    { boxShadow: '0 2px 8px rgba(0,0,0,0.15)', duration: dur * 0.5 }
                ],
                ease: 'none'
            });
            return null;  // fire-and-forget
        },

        /**
         * 49a-T7: 女優 → 影片跨模式 ghost fly（CD-11）
         *
         * 從女優卡片（grid 或 lightbox 封面）飛往影片模式 hero card 位置，
         * 抵達時 hero card 做 glow pulse + scale settle（UX B3）。
         *
         * @param {DOMRect} fromRect - 來源元素 bounding rect（state 變前 / closeLightbox 前捕獲）
         * @param {Element} heroCardEl - 目標 .hero-card 元素（render 完成後取得）
         * @param {object} [options] - { coverSrc, onComplete, onFallback }
         * @returns {gsap.Timeline|null}
         */
        playActressToHeroCard: function (fromRect, heroCardEl, options) {
            options = options || {};
            if (!fromRect || !heroCardEl) {
                if (typeof options.onFallback === 'function') options.onFallback();
                return null;
            }
            if (typeof gsap === 'undefined') {
                if (typeof options.onFallback === 'function') options.onFallback();
                return null;
            }
            if (window.OpenAver && window.OpenAver.prefersReducedMotion) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }
            var heroImg = heroCardEl.querySelector('.av-card-preview-img img');
            if (!heroImg) {
                if (typeof options.onFallback === 'function') options.onFallback();
                return null;
            }
            var toRect = heroImg.getBoundingClientRect();
            if (!toRect || toRect.width === 0) {
                if (typeof options.onFallback === 'function') options.onFallback();
                return null;
            }
            var coverSrc = options.coverSrc || fromRect._src;
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) {
                if (typeof options.onFallback === 'function') options.onFallback();
                return null;
            }

            // 隱藏真實 hero img（ghost 飛行期間）
            heroImg.setAttribute('data-ghost-hidden', '');
            gsap.set(heroImg, { opacity: 0 });

            var dur = 0.55;
            var ease = 'power2.inOut';
            var tl = gsap.timeline({ id: 'ghostActressToHeroCard' });
            tl.fromTo(ghost,
                { x: fromRect.left, y: fromRect.top, width: fromRect.width, height: fromRect.height },
                {
                    x: toRect.left, y: toRect.top, width: toRect.width, height: toRect.height,
                    duration: dur, ease: ease,
                    onComplete: function () {
                        cleanupGhost(ghost, heroImg);
                        // UX B3: hero card glow pulse + scale settle
                        // ⚠️ Gotcha C21：.av-card-preview 有 CSS transition: transform，
                        // GSAP scale tween 完成後 clearProps 會觸發幽靈動畫。
                        // 解法：tween 期間加 gsap-animating class 停用 CSS transition。
                        var heroCard = heroCardEl;
                        heroCard.classList.add('gsap-animating');
                        gsap.timeline({
                            onComplete: function () { heroCard.classList.remove('gsap-animating'); }
                        })
                            .fromTo(heroCard,
                                { scale: 1.02 },
                                { scale: 1.0, duration: 0.3, ease: 'power2.out', clearProps: 'transform' }
                            )
                            .fromTo(heroCard,
                                { filter: 'drop-shadow(0 0 12px rgba(255,255,200,0.6))' },
                                { filter: 'drop-shadow(0 0 0px rgba(0,0,0,0))', duration: 0.3, ease: 'power2.out', clearProps: 'filter' },
                                '<'
                            );
                        if (typeof options.onComplete === 'function') options.onComplete();
                    }
                }
            );
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
         * 已收藏愛心 Floating Hearts 粒子效果
         * 點擊 is-favorite 按鈕時，從按鈕位置噴出浮動愛心粒子，向上漂移並淡出。
         * 純裝飾，不改變收藏狀態。
         *
         * @param {Element} buttonEl - 按鈕 DOM 元素（$el from Alpine 模板）
         */
        floatingHearts: function (buttonEl) {
            // Early return guard
            if (!buttonEl || !buttonEl.getBoundingClientRect) return;

            var reducedMotion = window.OpenAver && window.OpenAver.prefersReducedMotion;
            var hasGsap = typeof gsap !== 'undefined';

            // ── 1. Button pulse（C21 防幽靈動畫）────────────────────────────
            if (hasGsap) {
                // C21 race fix: kill any in-progress pulse before starting a new one.
                // This ensures only one active pulse exists at a time, so the guard
                // class lifecycle remains clean (add before, remove in onComplete).
                gsap.killTweensOf(buttonEl);
                // C21: 加 guard class 暫時關掉 CSS transform transition
                buttonEl.classList.add('no-transform-transition');
                gsap.fromTo(buttonEl,
                    { scale: 1 },
                    {
                        scale: 1.3,
                        duration: 0.15,
                        ease: 'power2.out',
                        yoyo: true,
                        repeat: 1,
                        onComplete: function () {
                            buttonEl.classList.remove('no-transform-transition');
                        }
                    }
                );
            } else {
                // CSS fallback pulse: force animation restart on rapid clicks.
                // If the class is already present, remove it, trigger a reflow to
                // flush the browser's style engine, then re-add it so the keyframe
                // animation restarts from the beginning.
                buttonEl.classList.remove('btn-heart-pulse');
                void buttonEl.offsetWidth; // reflow
                buttonEl.classList.add('btn-heart-pulse');
                setTimeout(function () {
                    buttonEl.classList.remove('btn-heart-pulse');
                }, 300);
            }

            // ── 2. 粒子生成（reduced-motion 時跳過）─────────────────────────
            if (reducedMotion) return;

            var rect = buttonEl.getBoundingClientRect();
            var centerX = rect.left + rect.width / 2;
            var centerY = rect.top + rect.height / 2;

            var count = Math.floor(Math.random() * 2) + 1; // 1–2 顆

            for (var i = 0; i < count; i++) {
                (function (delay) {
                    setTimeout(function () {
                        // ── 3. 粒子樣式與動畫 ─────────────────────────────
                        var el = document.createElement('i');
                        el.className = 'bi bi-heart-fill floating-heart-particle';

                        var fontSize = Math.floor(Math.random() * 13) + 20; // 20–32px
                        el.style.cssText = [
                            'position:fixed',
                            'left:' + centerX + 'px',
                            'top:' + centerY + 'px',
                            'pointer-events:none',
                            'color:var(--color-favorite)',
                            'font-size:' + fontSize + 'px',
                            'z-index:9999',
                            'opacity:1'
                        ].join(';');

                        document.body.appendChild(el);

                        var yOffset = -(Math.random() * 40 + 80); // -80 to -120
                        var xOffset = (Math.random() * 60 + 30) * (Math.random() < 0.5 ? 1 : -1); // ±30–90
                        var duration = Math.random() * 0.3 + 0.8; // 0.8–1.1s

                        if (hasGsap) {
                            gsap.fromTo(el,
                                { y: 0, x: 0, opacity: 1, scale: 0.8 },
                                {
                                    y: yOffset,
                                    x: xOffset,
                                    opacity: 0,
                                    scale: 1.4,
                                    duration: duration,
                                    ease: 'power1.out',
                                    onComplete: function () { el.remove(); }
                                }
                            );
                        } else {
                            // CSS fallback
                            el.style.setProperty('--dx', xOffset + 'px');
                            el.classList.add('floating-heart-fallback');
                            el.addEventListener('animationend', function () { el.remove(); }, { once: true });
                        }
                    }, delay);
                }(i * (Math.random() * 80))); // 0–80ms stagger
            }
        },

        /**
         * Lightbox open 三段共用動畫（Phase 51 Phase 4 共用化）
         *
         * showcase / search 兩邊 caller 透過 delegate 呼叫本函式。
         * 三段 ease/duration 內部 hardcode（與 ui-conventions §5 white-list
         * playLightboxOpen 三段一致；CD-51-9 確認與 ghost-fly playGridToLightbox
         * 0.38s power2.inOut 並行段不可改 fluent-decel，否則「最後一小段卡」）。
         *
         * Cleanup 契約採 showcase 版完整 clearProps（CD-51-14）：onComplete /
         * onInterrupt 均對 content / coverImg 做 clearProps: transform,opacity，
         * 防連點觸發 interrupt 後殘留 inline style 造成 stutter。
         *
         * @param {Element} lightboxEl - .showcase-lightbox / .search-lightbox 根元素
         * @param {object} [opts] - { skipCover, onComplete, timelineId }
         * @param {boolean} [opts.skipCover] - true 時跳過第三段 cover slide-up（ghost-fly 接 lightbox 場景用）
         * @param {Function} [opts.onComplete] - timeline onComplete 回調
         * @param {string} [opts.timelineId='lightboxOpen'] - timeline ID（showcase delegate 傳 'showcaseLightboxOpen'）
         * @returns {gsap.core.Timeline|null}
         */
        playLightboxOpen: function (lightboxEl, opts) {
            opts = opts || {};

            if (!lightboxEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (window.OpenAver && window.OpenAver.prefersReducedMotion) return null;

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

            var timelineId = opts.timelineId || 'lightboxOpen';

            var tl = gsap.timeline({
                id: timelineId,
                onComplete: function () {
                    lightboxEl.classList.remove('gsap-animating');
                    // CD-51-14 cleanup：清掉動畫過程中累積的 inline transform/opacity，
                    // 避免被打斷時殘留半路狀態（用戶連點關開造成累積 stutter）
                    if (content) gsap.set(content, { clearProps: 'transform,opacity' });
                    if (coverImg && !opts.skipCover) gsap.set(coverImg, { clearProps: 'transform,opacity' });
                    if (typeof opts.onComplete === 'function') opts.onComplete();
                },
                onInterrupt: function () {
                    lightboxEl.classList.remove('gsap-animating');
                    // CD-51-14 cleanup：kill 中斷時 clearProps，避免殘留半路 transform/opacity
                    if (content) gsap.set(content, { clearProps: 'transform,opacity' });
                    if (coverImg && !opts.skipCover) gsap.set(coverImg, { clearProps: 'transform,opacity' });
                }
            });

            // ui-conventions §5 white-list（playLightboxOpen 三段）：
            // 與 ghost-fly playGridToLightbox (0.38s power2.inOut) 並行段，
            // 保留 power 系曲線族避免「最後一小段卡」（fix 50.2 經驗）。

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
            if (coverImg && !opts.skipCover) {
                tl.fromTo(coverImg,
                    { y: 12, opacity: 0 },
                    { y: 0, opacity: 1, duration: 0.16, ease: 'power2.out' },
                    '-=0.08'
                );
            }

            return tl;
        }
    };

    window.GhostFly = GhostFly;
})();
