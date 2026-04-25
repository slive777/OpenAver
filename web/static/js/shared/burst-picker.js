(function () {
    'use strict';

    /**
     * BurstPicker — Photo Picker 候選卡共用動畫模組（49b-T4a）
     *
     * 從 motion-lab.js 抽出 7 個 playPicker* 方法，
     * 供 motion-lab 頁面與展示櫥窗（T4b+）共用。
     *
     * 使用方式：
     *   window.BurstPicker.playPickerBurst(candidateEls, coverEl, params, opts)
     *   window.BurstPicker.playPickerHoverIn(el, params)
     *   window.BurstPicker.playPickerHoverOut(el, params)
     *   window.BurstPicker.playPickerFloat(el, params)
     *   window.BurstPicker.playPickerExitAll(els, params)
     *   window.BurstPicker.playPickerFlipReplace(selectedEl, coverEl, params, onComplete)
     *   window.BurstPicker.playPickerReverseAll(els, coverEl, params, onComplete)
     *
     * 約束：
     *   C1: GSAP onComplete 禁止改 Alpine 狀態，只 resolve Promise
     *   C4: 每個動畫開頭 gsap.killTweensOf(targets)
     *   C6: 封面禁止旋轉（不使用 rotationX/Y/Z）
     */

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

    var BurstPicker = {

        /**
         * 候選卡從封面中心爆射展開
         * @param {Element[]} candidateEls - 候選卡元素陣列
         * @param {Element} coverEl - 封面元素（爆射起點）
         * @param {object} params - pickerParams
         * @param {object} opts - { streamMode, streamInterval, floatTimerSink, runId, getRunId }
         * @returns {Promise}
         */
        playPickerBurst: function (candidateEls, coverEl, params, opts) {
            opts = opts || {};
            var els = Array.from(candidateEls || []);
            if (!els.length) return Promise.resolve();

            // C4: 清除舊動畫；P2-3: 清除舊 settled flag（新一輪 burst 開始）
            gsap.killTweensOf(els);
            els.forEach(function (el) { delete el.dataset.pickerSettled; });

            // Reduced Motion 降級：瞬間分散排列，立即標記 settled
            if (shouldSkip(params)) {
                els.forEach(function (el, i) {
                    gsap.set(el, { opacity: 1, x: (i - 2) * 80, y: 0, scale: 1 });
                    el.dataset.pickerSettled = '1';
                });
                return Promise.resolve();
            }

            var coverRect = coverEl ? coverEl.getBoundingClientRect() : { left: 0, top: 0, width: 0, height: 0 };
            var coverCX = coverRect.left + coverRect.width / 2;
            var coverCY = coverRect.top + coverRect.height / 2;

            var arcOvershoot = (params.arcOvershoot !== undefined) ? params.arcOvershoot : 1.4;
            var arcDuration = (params.arcDuration !== undefined) ? params.arcDuration : 0.6;
            var streamMode = opts.streamMode || 'instant';
            var streamInterval = opts.streamInterval || 300;
            var floatTimerSink = opts.floatTimerSink || [];
            var runId = opts.runId;
            var getRunId = opts.getRunId || function () { return runId; };

            function burstOne(el, index) {
                var elRect = el.getBoundingClientRect();
                var elCX = elRect.left + elRect.width / 2;
                var elCY = elRect.top + elRect.height / 2;
                // 起始偏移：相對封面中心
                var startX = coverCX - elCX;
                var startY = coverCY - elCY;

                gsap.set(el, { x: startX, y: startY, scale: 0.5, opacity: 0.5, rotation: 0 });

                var onBurstComplete = function () {
                    // race token 檢查
                    if (getRunId() !== runId) return;
                    // P2-3: 標記已落定，允許 hover 互動
                    el.dataset.pickerSettled = '1';
                    var tl = BurstPicker.playPickerFloat(el, params);
                    if (tl) floatTimerSink.push(tl);
                };

                try {
                    gsap.to(el, {
                        x: 0,
                        y: 0,
                        scale: 1,
                        opacity: 1,
                        rotation: 0,
                        ease: 'back.out(' + arcOvershoot + ')',
                        duration: arcDuration,
                        onComplete: onBurstComplete
                    });
                } catch (e) {
                    // fallback：直接歸位
                    gsap.set(el, { x: 0, y: 0, scale: 1, opacity: 1, rotation: 0 });
                    onBurstComplete();
                }
            }

            return new Promise(function (resolve) {
                if (streamMode === 'stagger') {
                    var i = 0;
                    var timer = setInterval(function () {
                        if (getRunId() !== runId) { clearInterval(timer); resolve(); return; }
                        if (i >= els.length) { clearInterval(timer); resolve(); return; }
                        burstOne(els[i], i);
                        i++;
                    }, streamInterval);
                } else {
                    // instant: 全部一次觸發
                    els.forEach(function (el, index) {
                        burstOne(el, index);
                    });
                    resolve();
                }
            });
        },

        /**
         * Float loop：候選卡抵達後持續漂浮
         * @param {Element} el
         * @param {object} params - pickerParams
         * @returns {gsap.core.Timeline}
         */
        playPickerFloat: function (el, params) {
            gsap.killTweensOf(el);

            if (shouldSkip(params)) return null;

            var amplY = params.floatAmplY || 8;
            var amplRot = params.floatAmplRot || 2.5;
            var baseDur = params.floatDuration || 1.5;
            var dur = baseDur + Math.random() * 0.4;
            var sign = Math.random() > 0.5 ? 1 : -1;

            var tl = gsap.timeline({ repeat: -1, yoyo: true });
            tl.to(el, {
                y: '+=' + (amplY * sign),
                rotation: amplRot * sign,
                duration: dur,
                ease: 'sine.inOut'
            });
            return tl;
        },

        /**
         * Hover in：放大 + 發光
         * @param {Element} el
         * @param {object} params - pickerParams
         */
        playPickerHoverIn: function (el, params) {
            // P2-3: burst 飛行中不接受 hover，避免 killTweensOf 中斷 physics tween
            if (!el || el.dataset.pickerSettled !== '1') return;
            gsap.killTweensOf(el);

            if (shouldSkip(params)) {
                gsap.set(el, { scale: params.hoverScale || 1.12, boxShadow: '0 0 12px rgba(255,255,255,0.6)' });
                return;
            }

            gsap.to(el, {
                scale: params.hoverScale || 1.12,
                boxShadow: '0 0 12px rgba(255,255,255,0.6)',
                duration: 0.2,
                ease: 'power2.out'
            });
        },

        /**
         * Hover out：縮回原始尺寸（float 由 caller 重啟）
         * @param {Element} el
         * @param {object} params - pickerParams
         */
        playPickerHoverOut: function (el, params) {
            // P2-3: burst 飛行中不接受 hover out
            if (!el || el.dataset.pickerSettled !== '1') return;
            gsap.killTweensOf(el);

            if (shouldSkip(params)) {
                gsap.set(el, { scale: 1, boxShadow: 'none' });
                return;
            }

            gsap.to(el, {
                scale: 1,
                boxShadow: 'none',
                duration: 0.2,
                ease: 'power2.out'
            });
        },

        /**
         * Ghost-fly 飛回封面：選中卡以 ghost img 飛向封面，抵達後替換封面 src + glow pulse
         * @param {Element} selectedEl - 選中的候選卡 .picker-candidate-card
         * @param {Element} coverEl    - 封面 img（.picker-cover-img）
         * @param {object} params      - pickerParams
         * @param {function} [onComplete]
         * @returns {Promise}
         */
        playPickerFlipReplace: function (selectedEl, coverEl, params, onComplete) {
            // ── 降級：gsap 不存在或應跳過 ──────────────────
            if (typeof gsap === 'undefined' || shouldSkip(params)) {
                // P1-2: reduced-motion 路徑也要替換封面 src，否則封面保持原圖不變
                var _selImg = selectedEl ? selectedEl.querySelector('img') : null;
                var _covImg = coverEl && coverEl.tagName === 'IMG' ? coverEl : (coverEl ? coverEl.querySelector('img') : null);
                if (_selImg && _covImg && _selImg.src) {
                    _covImg.src = _selImg.src;
                }
                if (typeof onComplete === 'function') onComplete();
                return Promise.resolve();
            }

            // ── 取來源 img + 目標 img ────────────────────────
            var selectedImg = selectedEl ? selectedEl.querySelector('img') : null;
            var coverImg    = (coverEl && coverEl.tagName === 'IMG') ? coverEl : null;
            if (!selectedImg || !coverImg) {
                if (typeof onComplete === 'function') onComplete();
                return Promise.resolve();
            }

            return new Promise(function (resolve) {
                var cb = function () {
                    if (typeof onComplete === 'function') onComplete();
                    resolve();
                };

                var fromRect = selectedImg.getBoundingClientRect();
                var toRect   = coverImg.getBoundingClientRect();

                if (!fromRect || fromRect.width === 0 || !toRect || toRect.width === 0) {
                    cb();
                    return;
                }

                // ── 1. 建立 picker 專用 ghost element ───────────────
                var ghost = document.createElement('img');
                ghost.src = selectedImg.src;
                ghost.setAttribute('data-picker-ghost', 'true');
                ghost.style.position       = 'fixed';
                ghost.style.left           = '0';
                ghost.style.top            = '0';
                ghost.style.margin         = '0';
                ghost.style.pointerEvents  = 'none';
                ghost.style.zIndex         = '1000';
                ghost.style.willChange     = 'transform, width, height';
                ghost.style.transformOrigin = 'top left';
                ghost.style.borderRadius   = '6px';
                ghost.style.objectFit      = 'cover';
                document.body.appendChild(ghost);

                gsap.set(ghost, {
                    x: fromRect.left, y: fromRect.top,
                    width: fromRect.width, height: fromRect.height,
                    boxShadow: '0 4px 16px rgba(0,0,0,0.25)'
                });

                // ── 2. 選中卡 fade out（避免重影），封面 img 隱藏讓 ghost 接手 ──
                gsap.to(selectedEl, { opacity: 0, duration: 0.15 });
                coverImg.classList.add('gsap-animating');
                gsap.set(coverImg, { opacity: 0 });

                // ── 3. ghost fromTo 飛向封面 ─────────
                var dur  = 0.55;
                var ease = 'power2.inOut';

                gsap.fromTo(ghost,
                    { x: fromRect.left, y: fromRect.top, width: fromRect.width, height: fromRect.height },
                    {
                        x: toRect.left, y: toRect.top, width: toRect.width, height: toRect.height,
                        duration: dur, ease: ease,
                        onComplete: function () {
                            // ── 4. 移除 ghost ─────────
                            if (ghost && ghost.parentNode) { ghost.remove(); }

                            // ── 5. 替換封面 src，等 load 後顯示並做 glow pulse ──
                            var newSrc = selectedImg.src + '?t=' + Date.now();
                            coverImg.onload = function () {
                                coverImg.onload = null;
                                coverImg.classList.add('gsap-animating');
                                gsap.timeline({
                                    onComplete: function () {
                                        coverImg.classList.remove('gsap-animating');
                                    }
                                })
                                    .set(coverImg, { opacity: 1 })
                                    .fromTo(coverImg,
                                        { scale: 1.02 },
                                        { scale: 1.0, duration: 0.3, ease: 'power2.out', clearProps: 'transform' }
                                    )
                                    .fromTo(coverImg,
                                        { filter: 'drop-shadow(0 0 12px rgba(255,255,200,0.6))' },
                                        { filter: 'drop-shadow(0 0 0px rgba(0,0,0,0))', duration: 0.3, ease: 'power2.out', clearProps: 'filter' },
                                        '<'
                                    );
                                cb();
                            };
                            // onerror fallback
                            coverImg.onerror = function () {
                                coverImg.onerror = null;
                                coverImg.classList.remove('gsap-animating');
                                gsap.set(coverImg, { opacity: 1 });
                                cb();
                            };
                            coverImg.src = newSrc;
                        }
                    }
                );

                // box-shadow 起降弧線（離地重、抵達輕）
                gsap.to(ghost, {
                    keyframes: [
                        { boxShadow: '0 12px 32px rgba(0,0,0,0.40)', duration: dur * 0.5 },
                        { boxShadow: '0 2px 8px rgba(0,0,0,0.15)',  duration: dur * 0.5 }
                    ],
                    ease: 'none'
                });
            });
        },

        /**
         * Exit：其他候選卡 gravity 下墜 fade
         * @param {Element[]} els
         * @param {object} params - pickerParams
         */
        playPickerExitAll: function (els, params) {
            if (!els || !els.length) return;
            gsap.killTweensOf(els);

            if (shouldSkip(params)) {
                gsap.set(els, { opacity: 0 });
                return;
            }

            var exitGravity = params.exitGravity || 1200;
            var usePhysics = (typeof Physics2DPlugin !== 'undefined');

            if (usePhysics) {
                gsap.to(els, {
                    physics2D: { velocity: 0, angle: 90, gravity: exitGravity },
                    opacity: 0,
                    stagger: 0.03,
                    duration: 0.8,
                    ease: 'none'
                });
            } else {
                gsap.to(els, {
                    y: '+=300',
                    opacity: 0,
                    stagger: 0.03,
                    duration: 0.5,
                    ease: 'power2.in'
                });
            }
        },

        /**
         * Reverse：取消時所有候選卡縮回封面中心
         * @param {Element[]} els
         * @param {Element} coverEl
         * @param {object} params - pickerParams
         * @param {function} [onComplete]
         */
        playPickerReverseAll: function (els, coverEl, params, onComplete) {
            if (!els || !els.length) {
                if (typeof onComplete === 'function') onComplete();
                return;
            }
            gsap.killTweensOf(els);

            if (shouldSkip(params)) {
                gsap.set(els, { opacity: 0, scale: 0 });
                if (typeof onComplete === 'function') onComplete();
                return;
            }

            var coverRect = coverEl ? coverEl.getBoundingClientRect() : { left: window.innerWidth / 2, top: window.innerHeight / 2 };
            var promises = Array.from(els).map(function (el) {
                var elRect = el.getBoundingClientRect();
                return new Promise(function (resolve) {
                    gsap.to(el, {
                        x: '+=' + (coverRect.left - elRect.left),
                        y: '+=' + (coverRect.top - elRect.top),
                        scale: 0,
                        opacity: 0,
                        duration: 0.3,
                        ease: 'power2.in',
                        onComplete: resolve
                    });
                });
            });

            Promise.all(promises).then(function () {
                if (typeof onComplete === 'function') onComplete();
            });
        },

        // 暴露 shouldSkip 供測試與外部使用
        shouldSkip: shouldSkip
    };

    window.BurstPicker = BurstPicker;
})();
