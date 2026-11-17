/**
 * ShowcaseAnimations — /showcase 頁面動畫模組
 *
 * 暴露 window.ShowcaseAnimations 物件，提供：
 *   - playEntry(gridEl, params)                B6: 進場動畫（B13 後也用於翻頁）［TASK-141b-T1 起為委派殼］
 *   - capturePositions(gridEl)                  B12: 捕獲手動位置快照（B15 恢復 core.js 呼叫）
 *   - playFlipReorder(gridEl, positionMap, params) B12: 排序洗牌手動動畫（B15 恢復 core.js 呼叫）
 *   - playFlipFilter(gridEl, state, params)     B8: 篩選進出場 Flip 動畫（B15 恢復 core.js 呼叫）［TASK-141b-T1 起為委派殼］
 *   - captureFlipState(gridEl)                  B8: 捕獲 Flip 狀態快照（B15 恢復 core.js 呼叫）［TASK-141b-T1 起為委派殼］
 *   - playModeCrossfade(oldMode, newMode, params) B10: 模式切換 crossfade
 *   - captureShapeState(gridEl) → { state, cards }|null  TASK-133a-T1: 卡型切換 Flip 快照（視野 ±200px）
 *   - playShapeMorph(captured, gridEl) → Timeline|null   TASK-133a-T1: 卡型切換 Flip morph（只吃 captured.cards）
 *   - captureInfoState(gridEl) → { el, top, left, bottom }[]|null  資訊展開位置快照（整格非 0×0；只收位置）
 *   - playInfoExpand(captured, gridEl) → Tween|null  資訊展開 x/y 位移（舊或新在窗內才動；無 scale、無 stagger）
 *   - playPickFill(fillEl, outlineEl, wasPicked, isPicked)  123-T4: 精選灌滿／洩空
 *   - playPickRing(ringEl, starEl, frameEl)  精選外框繞線
 *   - playPickSpark(anchorEl)                   123-T4: 灌滿到頂火花
 *   - killPickSpark()                           123-T4: 清殘留火花 dot
 *   - killPickStarTweens(opts)                  123-T4b：燈箱星 teardown（kill sink 收斂，
 *     見本檔 killPickStarTweens 定義處註解）
 *
 * B5 骨架：所有方法為 placeholder，return null。
 * B6-B10 逐步填入實作。
 *
 * TASK-141b-T1：上列標「委派殼」的三支，實作已搬到 web/static/js/shared/grid-motion.js
 * （window.GridMotion），本檔只保留原名原簽章的轉發殼——書籤牆要用同一份實作，
 * 兩頁共用避免第三份動畫語彙。呼叫端與行為零改變。
 *
 * Graceful fallback：若 GSAP 未載入，所有方法安全降級（不拋錯）。
 * core.js 透過 window.ShowcaseAnimations?.playEntry?.()
 * optional chaining 呼叫，確保此模組未載入時功能完全正常。
 */
(function () {
    'use strict';

    var pickRingTl = null;

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
            return window.GridMotion?.playEntry?.(gridEl, params) ?? null;
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

            var dur = params.duration || OpenAver.motion.DURATION.emphasis;
            var ease = params.ease || 'fluent';

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
            return window.GridMotion?.playFlipFilter?.(gridEl, state, params) ?? null;
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
            return window.GridMotion?.captureFlipState?.(gridEl) ?? null;
        },

        /**
         * TASK-133a-T1: 卡型切換（cover ↔ poster）用的 Flip 快照。
         *
         * 刻意與上面的 captureFlipState() 分立、不共用實作：後者服務篩選進出場，帶
         * { props: 'opacity', simple: true }；本函式服務卡型 morph，只帶 { simple: true }——
         * 共用會讓兩個用途互相綁架。
         *
         * CD-133a-1：只收視野上下各外擴 200px 內的卡；回傳 { state, cards }，把快照與
         * 這批卡綁在一起。動畫端不得重新挑卡——新版面下海報卡較高、可見集合不同，
         * 重挑會讓快照與動畫對到兩批不同的卡。
         *
         * @param {Element} gridEl - .showcase-grid / .actress-grid 容器
         * @returns {{ state: Object, cards: Element[] }|null} （AC-6.4：selector 已涵蓋
         *   hero 卡，因為 hero 卡的 class 是 `av-card-preview hero-card`）
         */
        captureShapeState: function (gridEl) {
            // null guard
            if (!gridEl) return null;

            // Flip guard
            if (typeof Flip === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview');
            if (!cards.length) return null;

            // CD-133a-1：量測前先停掉進場動畫（playEntry 會對卡片本身設 y 位移），
            // 並拿掉 gsap-animating（kill 後 timeline 不會跑 onComplete／onInterrupt）。
            if (typeof gsap !== 'undefined') {
                gsap.killTweensOf(cards);
                Array.from(cards).forEach(function (c) {
                    c.classList.remove('gsap-animating');
                });
                gsap.set(cards, { clearProps: 'transform,opacity' });
            }

            var VIEWPORT_MARGIN = 200;   // CD-133a-1：視野上下各外擴 200px
            var viewportH = window.innerHeight;
            var picked = Array.from(cards).filter(function (card) {
                var rect = card.getBoundingClientRect();
                return rect.bottom > -VIEWPORT_MARGIN && rect.top < viewportH + VIEWPORT_MARGIN;
            });
            if (!picked.length) return null;

            return { state: Flip.getState(picked, { simple: true }), cards: picked };
        },

        /**
         * TASK-133a-T1: 卡型切換（cover ↔ poster）的 Flip morph 動畫。
         *
         * 兩階段 API 的第二階段：呼叫端先 captureShapeState() 取得 { state, cards }，
         * 再呼叫本函式。本函式只准用 capturedState.cards，不得重新挑卡——新版面下
         * 海報卡較高、可見集合不同，重挑會讓快照與動畫對到兩批不同的卡。
         *
         * @param {{ state: Object, cards: Element[] }|null} capturedState - captureShapeState() 的回傳值
         * @param {Element} gridEl - .showcase-grid / .actress-grid 容器
         * @returns {gsap.core.Timeline|null}
         */
        playShapeMorph: function (capturedState, gridEl) {
            // null guard
            if (!capturedState || !gridEl) return null;

            // Flip guard
            if (typeof Flip === 'undefined' || typeof gsap === 'undefined') return null;

            // Reduced Motion 降級：class 已套上，畫面本來就正確，直接到位（AC-8.2）
            if (shouldSkip()) return null;

            var cards = capturedState.cards;
            if (!cards || !cards.length) return null;

            // C18: 中斷進行中的 Flip（連點）
            Flip.killFlipsOf(cards);

            var dur = OpenAver.motion.DURATION.medium;

            // CD-119-8: absolute 顯式寫成 false（依賴預設值但不寫死會失去這條契約的可讀性）。
            // 一次 morph 整頁 ~90 張卡，若把 absolute 設成 true 會讓 grid 容器高度在動畫期間歸零。
            return Flip.from(capturedState.state, {
                duration: dur,
                ease: 'fluent',
                absolute: false,
                prune: true,
                onComplete: function () {
                    gsap.set(cards, { clearProps: 'transform,width,height' });
                }
            });
        },

        /**
         * 資訊展開兩階段 — capture 階段（只收位置，不動尺寸）。
         *
         * 選卡 selector：'.av-card-preview, .actress-card'。量測前對完整集合
         * killTweensOf → 移除 gsap-animating → clearProps transform,opacity，
         * 再收集整個 grid 內非 0×0 的卡（視口過濾改在 play），回傳 { el, top, left, bottom }。
         * 不呼叫 Flip.getState / Flip.from。
         *
         * @param {Element} gridEl - .showcase-grid / .actress-grid 容器
         * @returns {{ el: Element, top: number, left: number, bottom: number }[]|null}
         */
        captureInfoState: function (gridEl) {
            if (!gridEl) return null;

            if (typeof gsap === 'undefined') return null;

            var cards = gridEl.querySelectorAll('.av-card-preview, .actress-card');
            if (!cards.length) return null;

            // capture 四步驟（對完整 cards，量測之前 — FE-MOTION-06）
            gsap.killTweensOf(cards);
            Array.from(cards).forEach(function (c) {
                c.classList.remove('gsap-animating');
            });
            gsap.set(cards, { clearProps: 'transform,opacity' });

            var captured = [];
            Array.from(cards).forEach(function (card) {
                var rect = card.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                captured.push({
                    el: card,
                    top: rect.top,
                    left: rect.left,
                    bottom: rect.bottom
                });
            });
            if (!captured.length) return null;

            return captured;
        },

        /**
         * 資訊展開兩階段 — play 階段（只做 x/y 位移，無 scale、無 stagger）。
         *
         * 兩趟：先一次讀完全部新 rect（不寫 style），過濾「舊或新位置落在
         * 視口 ±200px」的卡；再只對這批 gsap.set 反轉，ticker.tick() 對齊時基後
         * gsap.to 歸零。
         *
         * @param {{ el: Element, top: number, left: number, bottom: number }[]|null} captured
         * @param {Element} gridEl
         * @returns {gsap.core.Tween|null}
         */
        playInfoExpand: function (captured, gridEl) {
            if (!captured || !gridEl) return null;

            if (typeof gsap === 'undefined') return null;

            if (shouldSkip()) return null;

            if (!captured.length) return null;

            var VIEWPORT_MARGIN = 200;
            var viewportH = window.innerHeight;
            function inBand(top, bottom) {
                return bottom > -VIEWPORT_MARGIN && top < viewportH + VIEWPORT_MARGIN;
            }

            // 第一趟：只讀新 rect（中間不寫任何 style，避免 layout thrashing）
            var afterRects = captured.map(function (item) {
                return item.el.getBoundingClientRect();
            });

            // 舊位置或新位置任一落在視窗內才 animate（收合時界外卡跳進視口也要補間）
            var animateItems = [];
            var i;
            for (i = 0; i < captured.length; i++) {
                var item = captured[i];
                var after = afterRects[i];
                var oldIn = inBand(item.top, item.bottom);
                var newIn = inBand(after.top, after.bottom);
                if (oldIn || newIn) {
                    animateItems.push({ item: item, after: after });
                }
            }
            if (!animateItems.length) return null;

            var els = animateItems.map(function (a) { return a.item.el; });

            // C21/B15：關掉卡片 CSS transition:transform，否則會跟 gsap.set 反轉搶控制權
            var classesReleased = false;
            function releaseMotionClasses() {
                if (classesReleased) return;
                classesReleased = true;
                // onComplete／onInterrupt／catch 共用；clearProps 冪等，重複呼叫無害
                gsap.set(els, { clearProps: 'transform' });
                els.forEach(function (c) { c.classList.remove('gsap-animating'); });
                gridEl.classList.remove('flip-guard');
            }
            gridEl.classList.add('flip-guard');
            els.forEach(function (c) { c.classList.add('gsap-animating'); });

            try {
                gsap.killTweensOf(els);
                // 第二趟：只寫反轉（不再讀 rect）
                animateItems.forEach(function (a) {
                    gsap.set(a.item.el, {
                        x: a.item.left - a.after.left,
                        y: a.item.top - a.after.top
                    });
                });
                // gsap.to 的 _start 取上一次 ticker 時間；同步準備耗時會被記成已播進度。
                // 建 tween 前先 tick 一次，把時基推到「現在」。
                gsap.ticker.tick();
                return gsap.to(els, {
                    x: 0,
                    y: 0,
                    duration: OpenAver.motion.WALL_MOTION.INFO_EXPAND_DURATION,
                    ease: 'fluent',
                    onComplete: function () {
                        releaseMotionClasses();
                    },
                    onInterrupt: function () {
                        releaseMotionClasses();
                    }
                });
            } catch (err) {
                // 建 tween 中途拋錯時 kill 不會跑 onInterrupt；必須同步卸 class，否則 pointer-events:none 殘留
                releaseMotionClasses();
                throw err;
            }
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
                        duration: OpenAver.motion.DURATION.fast,
                        ease: 'fluent-accel',
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
                    { opacity: 1, duration: OpenAver.motion.DURATION.fast, ease: 'fluent-decel', clearProps: 'opacity' }
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
            // Phase 51 Phase 4 (T4.2): delegate to GhostFly.playLightboxOpen 共用實作。
            // timelineId 維持 'showcaseLightboxOpen' 以保留既有 killLightboxAnimations
            // (animations.js: this.killLightboxAnimations) 對 gsap.getById('showcaseLightboxOpen') 的查找。
            // typeof guard（codex T4-P3）：window.GhostFly 存在但 playLightboxOpen
            // method 缺（cache invalidation 場景：舊 ghost-fly.js + 新 animations.js）
            // 時 fallback null，避免 TypeError 直接炸掉 lightbox open。
            return typeof window.GhostFly?.playLightboxOpen === 'function'
                ? window.GhostFly.playLightboxOpen(
                    lightboxEl,
                    Object.assign({ timelineId: 'showcaseLightboxOpen' }, options || {})
                )
                : null;
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
                { opacity: 1, x: 0, duration: OpenAver.motion.DURATION.fast, ease: 'fluent' }
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
                    ease: 'fluent-decel',
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
                    duration: OpenAver.motion.DURATION.fast,
                    ease: 'fluent',
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
            var dur = (typeof options.duration === 'number') ? options.duration : OpenAver.motion.DURATION.fast;
            var ease = options.ease || 'fluent-decel';
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
                ease: 'fluent'
            });
        },

        /**
         * 按星時沿燈箱外框畫一圈，減少動態或缺少插件時略過。
         * @param {Element} ringEl - SVG
         * @param {Element} starEl - 星按鈕
         * @param {Element} frameEl - 燈箱框
         * @returns {gsap.core.Timeline|null}
         */
        playPickRing: function (ringEl, starEl, frameEl) {
            if (shouldSkip()) { return null; }
            if (!ringEl || !frameEl) return null;
            if (typeof gsap === 'undefined' || typeof DrawSVGPlugin === 'undefined') return null;
            if (!gsap.plugins.drawSVG) gsap.registerPlugin(DrawSVGPlugin);

            var paths = ringEl.querySelectorAll('path');
            if (pickRingTl) pickRingTl.kill();
            gsap.killTweensOf(paths);
            gsap.set(paths, { clearProps: 'strokeDasharray,strokeDashoffset,opacity' });
            var w = frameEl.clientWidth;
            var h = frameEl.clientHeight;
            var INSET = 2;
            var R = parseFloat(getComputedStyle(frameEl).borderTopLeftRadius) - INSET;
            if (isNaN(R) || R < 0) R = 10;
            var sx = w / 2;
            if (starEl) {
                var starRect = starEl.getBoundingClientRect();
                var frameRect = frameEl.getBoundingClientRect();
                sx = (starRect.left + starRect.width / 2 - frameRect.left) / frameRect.width * w;
            }
            sx = Math.max(INSET + R, Math.min(w - INSET - R, sx));
            var d = 'M ' + sx + ',' + (h - INSET) +
                ' L ' + (INSET + R) + ',' + (h - INSET) +
                ' A ' + R + ' ' + R + ' 0 0 1 ' + INSET + ',' + (h - INSET - R) +
                ' L ' + INSET + ',' + (INSET + R) +
                ' A ' + R + ' ' + R + ' 0 0 1 ' + (INSET + R) + ',' + INSET +
                ' L ' + (w - INSET - R) + ',' + INSET +
                ' A ' + R + ' ' + R + ' 0 0 1 ' + (w - INSET) + ',' + (INSET + R) +
                ' L ' + (w - INSET) + ',' + (h - INSET - R) +
                ' A ' + R + ' ' + R + ' 0 0 1 ' + (w - INSET - R) + ',' + (h - INSET) + ' Z';
            ringEl.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
            paths.forEach(function (path) { path.setAttribute('d', d); });
            var tl = gsap.timeline({ onComplete: function () {
                if (pickRingTl === tl) {
                    gsap.set(paths, { clearProps: 'strokeDasharray,strokeDashoffset,opacity' });
                    pickRingTl = null;
                }
            } });
            pickRingTl = tl;
            tl.fromTo(paths, { drawSVG: '0% 0%', opacity: 1 }, { drawSVG: '0% 100%', duration: 0.475, ease: 'fluent' }, 0);
            tl.to(paths, { opacity: 0, duration: 0.361, ease: 'fluent-decel' }, 0.589);
            return tl;
        },

        /**
         * 123-T4：燈箱精選星灌滿／洩空。
         * Alpine :style 已把 --pick-fill 寫成終值；$nextTick 之後 fromTo
         * （immediateRender: true）把值拉回起點再補到同一個終點。
         * overshoot 與火花只在灌滿方向（isPicked === true）。
         *
         * @param {Element} fillEl - .pick-star-fill
         * @param {Element} outlineEl - .pick-star-outline（kill 對稱；scale 做在按鈕上）
         * @param {boolean} wasPicked
         * @param {boolean} isPicked
         * @returns {gsap.core.Tween|null}
         */
        playPickFill: function (fillEl, outlineEl, wasPicked, isPicked) {
            if (!fillEl) return null;
            if (typeof gsap === 'undefined') return null;

            var pickStarEl = (fillEl.closest) ? fillEl.closest('.pick-star') : null;
            if (!pickStarEl && outlineEl && outlineEl.closest) {
                pickStarEl = outlineEl.closest('.pick-star');
            }

            // 先 kill 再 tween：flight lock 不擋「補間還沒放完但 fetch 已 resolve」的第二次點擊
            // GSAP 3.14.2 實測：killTweensOf(target, '--custom-prop') 對 CSS 自訂屬性
            // **完全無效**（tween 照跑到底），必須不帶 props 才殺得掉。見 CDP 實測紀錄。
            gsap.killTweensOf(fillEl);
            if (outlineEl) gsap.killTweensOf(outlineEl);
            if (pickStarEl) {
                gsap.killTweensOf(pickStarEl);
                gsap.set(pickStarEl, { clearProps: 'transform' });
            }
            ShowcaseAnimations.killPickSpark();

            var fromPct = wasPicked ? '0%' : '100%';
            var toPct = isPicked ? '0%' : '100%';

            if (shouldSkip()) {
                gsap.set(fillEl, { '--pick-fill': toPct });
                return null;
            }

            return gsap.fromTo(fillEl,
                { '--pick-fill': fromPct },
                {
                    '--pick-fill': toPct,
                    duration: isPicked ? 0.18 : 0.16,
                    ease: isPicked ? 'fluent-decel' : 'fluent-accel',
                    immediateRender: true,
                    onComplete: (isPicked && pickStarEl) ? function () {
                        gsap.to(pickStarEl, {
                            scale: 1.15,
                            duration: 0.12,
                            ease: 'back.out(1.7)',
                            yoyo: true,
                            repeat: 1
                        });
                        ShowcaseAnimations.playPickSpark(pickStarEl);
                    } : undefined
                }
            );
        },

        /**
         * 123-T4：灌滿到頂火花。動態建立 4–6 顆 .pick-spark-dot，散開後淡出並 .remove()。
         * 不使用 .sparkle-star（語意是自動對焦處理中）。
         *
         * @param {Element} anchorEl - .pick-star（position: relative）
         * @returns {null}
         */
        playPickSpark: function (anchorEl) {
            if (!anchorEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (shouldSkip()) return null;

            ShowcaseAnimations.killPickSpark();

            var count = Math.floor(4 + Math.random() * 3);
            var box = Math.max(anchorEl.offsetWidth || 0, anchorEl.offsetHeight || 0, 28);
            var i;
            for (i = 0; i < count; i++) {
                (function () {
                    var dot = document.createElement('span');
                    dot.className = 'pick-spark-dot';
                    anchorEl.appendChild(dot);

                    var angle = Math.random() * Math.PI * 2;
                    var dist = box * (0.55 + Math.random() * 0.35);
                    var dx = Math.cos(angle) * dist;
                    var dy = Math.sin(angle) * dist;

                    var tl = gsap.timeline({
                        onComplete: function () {
                            if (dot.parentNode) dot.remove();
                        }
                    });
                    tl.fromTo(dot,
                        { x: 0, y: 0, opacity: 0 },
                        { x: dx, y: dy, opacity: 1, duration: 0.12, ease: 'fluent-decel' }
                    );
                    tl.to(dot, { opacity: 0, duration: 0.18, ease: 'fluent-accel' });
                })();
            }
            return null;
        },

        /**
         * 123-T4：清掉殘留火花 dot。idempotent。
         * gsap 未載入時仍移除 DOM；shouldSkip 不擋 teardown（與 play* 入口的
         * 「不開動畫」相反，kill 是收尾）。
         *
         * @returns {null}
         */
        killPickSpark: function () {
            if (typeof document === 'undefined') return null;
            var dots = document.querySelectorAll('.pick-spark-dot');
            if (!dots.length) return null;
            var gsapReady = typeof gsap !== 'undefined';
            if (shouldSkip() && !gsapReady) {
                Array.prototype.forEach.call(dots, function (el) { el.remove(); });
                return null;
            }
            Array.prototype.forEach.call(dots, function (el) {
                if (gsapReady) gsap.killTweensOf(el);
                el.remove();
            });
            return null;
        },

        /**
         * 123-T4b：燈箱精選星 teardown — 三個呼叫端（state-lightbox.js 的 _setLightboxIndex /
         * closeLightbox / searchFromMetadata）共用的 kill sink，原先各自直接呼叫 gsap.*，
         * 撞上 static_guard_lint 的 TestMotionInfra 守衛（state-lightbox.js 不在白名單，見
         * scripts/static_guard_lint.mjs:1705-1709）。三個呼叫端的收尾強度不同，逐一保留：
         *   - _setLightboxIndex：{ clearTransform: true }（不清 --pick-fill）
         *   - closeLightbox：    { clearFill: true, clearTransform: true }（完整 teardown）
         *   - searchFromMetadata：{}（只止血，teardown 留給 closeLightbox）
         * gsap 未載入時整條（含 killPickSpark）不執行，與搬移前三處呼叫端行為一致
         * （原本 killPickSpark() 呼叫都包在 `typeof gsap !== 'undefined'` 判斷式內）。
         * 存在性 guard（querySelector 有命中才 gsap.set）：常見路徑上該選擇器 0 命中
         * （切換到女優燈箱、或 .pick-star-fill 只在影片燈箱裡），guard 避免 gsap.set(null, ...)
         * 洗版 console.warn（沿用搬移前三處呼叫端的既有 guard）。
         *
         * @param {Object} [opts]
         * @param {boolean} [opts.clearFill] - 是否對 .pick-star-fill clearProps '--pick-fill'
         * @param {boolean} [opts.clearTransform] - 是否對 .pick-star clearProps 'transform'
         * @returns {null}
         */
        killPickStarTweens: function (opts) {
            if (typeof gsap === 'undefined') return null;
            opts = opts || {};

            // 不帶 props：GSAP 3.14.2 的 props 過濾對 CSS 自訂屬性無效（實測）
            gsap.killTweensOf('.pick-star-fill');
            gsap.killTweensOf('.pick-star');

            if (opts.clearFill) {
                var fillEl = document.querySelector('.pick-star-fill');
                if (fillEl) gsap.set(fillEl, { clearProps: '--pick-fill' });
            }
            if (opts.clearTransform) {
                var starEl = document.querySelector('.pick-star');
                if (starEl) gsap.set(starEl, { clearProps: 'transform' });
            }

            ShowcaseAnimations.killPickSpark();
            return null;
        }
    };

    // 暴露全域物件
    window.ShowcaseAnimations = ShowcaseAnimations;
})();
