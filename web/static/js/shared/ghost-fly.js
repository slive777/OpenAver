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
     *
     * 56c-T2 (CD-56C-3): 第三參數 options.cropMode 支援 'full'（預設）與
     * 'right-half'。'right-half' 時 ghostRect 取右半（left += width/2、width /= 2）
     * 且 CSS objectPosition = 'right center'，瀏覽器 GPU 層裁切（零效能損耗）。
     * 既有 caller 不傳 options → 走 default 'full' 分支零回歸。
     *
     * 56c-T4: 第三參數 options.parent 預設 `document.body`（向後相容）；
     * 56c similar mode 傳入 `.similar-stage`，讓 ghost 進入 .similar-stage 自己建立的
     * stacking context — 同 stacking context 內 main-overlay z=2001 才能正確
     * 蓋過 ghost z=2000。其他 callers 不傳 → 走 default body → 行為不變。
     *
     * @param {string} src - 圖片來源 URL
     * @param {DOMRect} rect - 來源元素的 bounding rect
     * @param {object} [options] - { cropMode: 'full' | 'right-half', parent?: Element }
     * @returns {HTMLImageElement|null} ghost element，或 null（建立失敗）
     */
    function createCoverGhost(src, rect, options) {
        if (!src || !rect || rect.width === 0 || rect.height === 0) return null;

        // 清除殘留 ghost
        cleanupStaleGhosts();

        options = options || {};
        var cropMode = options.cropMode || 'full';
        var ghostRect = rect;
        if (cropMode === 'right-half') {
            ghostRect = {
                left: rect.left + rect.width / 2,
                top: rect.top,
                width: rect.width / 2,
                height: rect.height
            };
        }

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
        if (cropMode === 'right-half') {
            // CSS 層裁切：搭配 objectFit: cover，瀏覽器只顯示右半邊（GPU 加速、零效能損耗）
            ghost.style.objectPosition = 'right center';
        }

        // 56c-T4: parent 預設 body 維持向後相容；56c 傳 .similar-stage 讓 ghost
        // 進入 .similar-stage stacking context，main-overlay z=2001 在同 context 下
        // 才能正確蓋過 ghost z=2000
        var parent = options.parent || document.body;
        parent.appendChild(ghost);

        // 以 GSAP 定位至來源位置（cropMode 'right-half' 時用裁切後 ghostRect）
        if (typeof gsap !== 'undefined') {
            gsap.set(ghost, {
                x: ghostRect.left,
                y: ghostRect.top,
                width: ghostRect.width,
                height: ghostRect.height,
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

    // ─── 56c Similar Mode 進退場 helper（plan-56c §1 CD-56C-3 / CD-56C-2 / CD-56C-11）──

    /**
     * 56c-T2 (CD-56C-3 + CD-56C-11): Lightbox cover → Constellation stage 中央 進場
     *
     * 從 lightbox cover img 起飛，飛到 stageInner design-space (480, 310) 中央
     * 200×250 box；只顯示右半邊（cropMode: 'right-half'）。
     * 動畫完成後 ghost **不 cleanup**（state-similar.js 接管 ghost ref）。
     *
     * caller 責任：呼叫前必須先 mount `.similar-stage.show`，並等 rAF 讓 stageInner
     * rect 有效（CD-56C-11 caveat）。
     *
     * @param {HTMLImageElement} coverImgEl - lightbox 內 .lightbox-cover img
     * @param {HTMLElement} stageInnerEl - .similar-stage-inner（960×620 居中容器）
     * @param {object} [opts] - { onComplete?: (ghost) => void }
     * @returns {gsap.core.Timeline|null}
     */
    function play56cConstellationEnter(coverImgEl, stageInnerEl, opts) {
        opts = opts || {};
        if (!coverImgEl || !stageInnerEl) {
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }
        if (typeof gsap === 'undefined') {
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }

        var rect = coverImgEl.getBoundingClientRect();
        var src = coverImgEl.src;

        // 1) 先建 ghost（createCoverGhost 內部 cleanupStaleGhosts() 會還原所有
        //    [data-ghost-hidden] 元素 opacity，故必須在 hide 之前呼叫；對齊
        //    playGridToLightbox 既有 pattern）
        // 56c-T4: 取 .similar-stage 作為 ghost parent，讓 ghost 進入 .similar-stage
        // stacking context → main-overlay z=2001 在 .similar-stage 內可以正確蓋過 ghost z=2000
        var stageEl = stageInnerEl.closest('.similar-stage');
        var ghost = createCoverGhost(src, rect, {
            cropMode: 'right-half',
            parent: stageEl || document.body  // fallback safety
        });
        if (!ghost) {
            if (typeof opts.onComplete === 'function') opts.onComplete(null);
            return null;
        }

        // 2) 再 hide 原 lightbox cover img（cleanupStaleGhosts 已跑完，不會被還原）
        //    避免 ghost 飛行時雙圖重疊；onInterrupt 走 cleanupGhost 還原路徑
        coverImgEl.setAttribute('data-ghost-hidden', 'true');
        gsap.set(coverImgEl, { opacity: 0 });

        // 56c-T4: single source of truth — 直接吃 .similar-main-anchor 的 native rect
        // （瀏覽器 transform: scale 後回傳 scaled rect），與 cards design-space 480/310
        // 完全同步，避免再算 480*scale 公式漂移
        var targetX, targetY, targetW, targetH;
        var anchorEl = stageInnerEl.querySelector('.similar-main-anchor');
        if (anchorEl) {
            var anchorRect = anchorEl.getBoundingClientRect();
            targetX = anchorRect.left;
            targetY = anchorRect.top;
            targetW = anchorRect.width;
            targetH = anchorRect.height;
        } else {
            // graceful fallback: 找不到 anchor（DOM 老版 / motion-lab sandbox）退回舊公式
            var stageRect = stageInnerEl.getBoundingClientRect();
            var scale = stageRect.width > 0 ? stageRect.width / 960 : 1;
            targetW = 200 * scale;
            targetH = 250 * scale;
            targetX = stageRect.left + 480 * scale - targetW / 2;
            targetY = stageRect.top + 310 * scale - targetH / 2;
        }

        // duration guard chain（與 motion-lab.js:1327-1328 既有 pattern 一致，避免 ?. 在
        // 較舊瀏覽器/lint 設定下出問題）
        var dur = (window.OpenAver && window.OpenAver.motion &&
                   window.OpenAver.motion.DURATION && window.OpenAver.motion.DURATION.medium) || 0.333;

        // race 防護：清掉同 ghost 的舊 tween
        gsap.killTweensOf(ghost);

        var tl = gsap.timeline({
            id: 'similarEnter',
            onComplete: function () {
                // ghost 留在中央給 state-similar.js 接管，**不 cleanup**
                if (typeof opts.onComplete === 'function') opts.onComplete(ghost);
            },
            onInterrupt: function () {
                // race 防護：被打斷時 cleanup ghost + 還原 coverImgEl opacity
                cleanupGhost(ghost, coverImgEl);
            }
        });

        tl.to(ghost, {
            x: targetX, y: targetY,
            width: targetW, height: targetH,
            duration: dur,
            ease: 'fluent-decel'
        }, 0);

        return tl;
    }

    /**
     * 56c-T2 (CD-56C-3): Constellation stage 中央 main img → Lightbox cover 退場
     *
     * mainImgGhost 從中央飛回 targetCoverEl 位置，同時 objectPosition 從
     * 'right center' 平滑過渡到 'center center'（GSAP duration 與 CSS transition 同步）。
     * 動畫完成（或被打斷）都 cleanup ghost + 還原 targetCoverEl opacity。
     *
     * caller 責任：呼叫前必須確保 lightbox 已還原可見（targetCoverEl rect 才有效）。
     *
     * @param {HTMLImageElement} mainImgGhost - 中央 ghost img（由 play56cConstellationEnter 留下）
     * @param {HTMLImageElement} targetCoverEl - 目標 .lightbox-cover img
     * @param {object} [opts] - { onComplete?: () => void }
     * @returns {gsap.core.Timeline|null}
     */
    function play56cConstellationExit(mainImgGhost, targetCoverEl, opts) {
        opts = opts || {};
        if (!mainImgGhost || !targetCoverEl) {
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }
        if (typeof gsap === 'undefined') {
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }

        var rect = targetCoverEl.getBoundingClientRect();
        var dur = (window.OpenAver && window.OpenAver.motion &&
                   window.OpenAver.motion.DURATION && window.OpenAver.motion.DURATION.medium) || 0.333;

        // objectPosition 平滑過渡：CSS transition 與 GSAP duration 對齊
        // （右半 crop 還原為全張呈現）
        mainImgGhost.style.transition = 'object-position ' + dur + 's ease';
        mainImgGhost.style.objectPosition = 'center center';

        // race 防護
        gsap.killTweensOf(mainImgGhost);

        var tl = gsap.timeline({
            id: 'similarExit',
            onComplete: function () {
                cleanupGhost(mainImgGhost, targetCoverEl);
                if (typeof opts.onComplete === 'function') opts.onComplete();
            },
            onInterrupt: function () {
                // race 防護：onInterrupt 也 cleanup（連點 5 次無殘留）
                cleanupGhost(mainImgGhost, targetCoverEl);
            }
        });

        tl.to(mainImgGhost, {
            x: rect.left, y: rect.top,
            width: rect.width, height: rect.height,
            duration: dur,
            ease: 'fluent-accel'
        }, 0);

        return tl;
    }

    // ─── 83b-T3: 行動相似面板 封面飛行進 / 退場 helper ──────────────────────

    /**
     * 83b-T3: Lightbox cover → Mobile panel center 進場
     *
     * 從 lightbox cover img（coverImgEl）起飛，飛到行動面板中央主圖（mobileCoverEl）
     * 位置；只顯示右半邊（cropMode: 'right-half'）。
     * 抵達時 ghost 不自 cleanup（由 caller 在 onComplete 接管：set src + cleanupGhost）。
     *
     * Correction A：飛行期間同時隱藏 destination（mobileCoverEl），讓 ghost 到達後才顯示
     * 真圖，避免「ghost 飛到已可見的目標上方 → 視覺重複」。
     *
     * P1-T3fix（中途中斷 race）：回傳的 timeline 有穩定 id 'mobilePanelEnter'，且透過
     * opts.onGhostReady 同步把 enter ghost ref 交給 caller。closeMobilePanel 中途打斷時
     * 必須先 kill 此 timeline 並（GSAP 3 .kill() 不保證 fire onInterrupt）顯式
     * cleanupGhost(enterGhost, coverImgEl, mobileCoverEl) 還原雙端 opacity，再起飛 exit ghost。
     *
     * @param {HTMLImageElement} coverImgEl   - lightbox 內 cover img（$refs.lightboxCoverImg）
     * @param {HTMLImageElement} mobileCoverEl - 行動面板中央主圖（$refs.mobilePanelCoverImg）
     * @param {object} [opts] - { onComplete?: (ghost) => void, onGhostReady?: (ghost) => void }
     * @returns {gsap.core.Timeline|null}
     */
    function playMobilePanelEnter(coverImgEl, mobileCoverEl, opts) {
        opts = opts || {};
        if (!coverImgEl || !mobileCoverEl) {
            if (typeof opts.onComplete === 'function') opts.onComplete(null);
            return null;
        }
        if (typeof gsap === 'undefined') {
            if (typeof opts.onComplete === 'function') opts.onComplete(null);
            return null;
        }

        // P2-T3fix（rect 讀取在 .show 之後）：caller 在 panelEl.classList.add('show') +
        // $nextTick 後才呼叫本函式，故此 rect 讀取在 .show 之後。安全：面板靠
        // opacity/visibility:hidden 隱藏（非 display:none），lightbox cover 的 layout
        // 幾何不受 .show 影響，source rect 與 .show 前一致。
        var rect = coverImgEl.getBoundingClientRect();
        var src = coverImgEl.src;

        // C25 順序鐵律：先建 ghost（createCoverGhost 內部 cleanupStaleGhosts() 會還原
        // 所有 [data-ghost-hidden] 元素 opacity，故必須在 hide 之前呼叫）
        var ghost = createCoverGhost(src, rect, { cropMode: 'right-half' });
        if (!ghost) {
            // rect.width === 0 or src empty → graceful skip
            if (typeof opts.onComplete === 'function') opts.onComplete(null);
            return null;
        }
        // P1-T3fix：同步把 enter ghost ref 交 caller，供中途打斷時顯式 cleanup
        if (typeof opts.onGhostReady === 'function') opts.onGhostReady(ghost);

        // 隱藏來源（lightbox cover）
        coverImgEl.setAttribute('data-ghost-hidden', 'true');
        gsap.set(coverImgEl, { opacity: 0 });

        // Correction A：同時隱藏目標（mobile center cover），防 ghost 飛抵時雙圖重疊
        mobileCoverEl.setAttribute('data-ghost-hidden', 'true');
        gsap.set(mobileCoverEl, { opacity: 0 });

        // 讀目標 rect（面板 .show 後、$nextTick 後呼叫，此時 rect 已有效）
        var targetRect = mobileCoverEl.getBoundingClientRect();

        // duration guard chain（與桌面函式 L199-200 完全一致）
        var dur = (window.OpenAver && window.OpenAver.motion &&
                   window.OpenAver.motion.DURATION && window.OpenAver.motion.DURATION.medium) || 0.333;

        // race 防護
        gsap.killTweensOf(ghost);

        var tl = gsap.timeline({
            id: 'mobilePanelEnter',
            onComplete: function () {
                // ghost 留著交 caller 接管（mirror 桌面 constellation enter L208-209 pattern）
                // caller 負責：mobileCoverEl.src = src + cleanupGhost(ghost, coverImgEl, mobileCoverEl)
                if (typeof opts.onComplete === 'function') opts.onComplete(ghost);
            },
            onInterrupt: function () {
                // race / 中途中斷：cleanup ghost + 還原 coverImgEl + mobileCoverEl opacity
                // （idempotent：closeMobilePanel 亦會顯式 cleanup，cleanupGhost 以 parentNode 守衛）
                cleanupGhost(ghost, coverImgEl, mobileCoverEl);
            }
        });

        tl.to(ghost, {
            x: targetRect.left, y: targetRect.top,
            width: targetRect.width, height: targetRect.height,
            duration: dur,
            ease: 'fluent-decel'
        }, 0);

        return tl;
    }

    /**
     * 83b-T3: Mobile panel center → Lightbox cover 退場
     *
     * mobileCoverEl（面板中央主圖）起飛，飛回 coverImgEl（lightbox cover）位置。
     * 動畫完成（或被打斷）都 cleanup ghost + 還原兩端 opacity。
     *
     * @param {HTMLImageElement} mobileCoverEl - 面板中央主圖（$refs.mobilePanelCoverImg）
     * @param {HTMLImageElement} coverImgEl    - lightbox cover img（飛回目標）
     * @param {object} [opts] - { onComplete?: () => void }
     * @returns {gsap.core.Timeline|null}
     */
    function playMobilePanelExit(mobileCoverEl, coverImgEl, opts) {
        opts = opts || {};
        if (!mobileCoverEl || !coverImgEl) {
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }
        if (typeof gsap === 'undefined') {
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }

        var exitSrc = mobileCoverEl.src;
        var exitRect = mobileCoverEl.getBoundingClientRect();

        // C25 順序鐵律：先建 ghost，再 hide source
        var ghost = createCoverGhost(exitSrc, exitRect, { cropMode: 'right-half' });
        if (!ghost) {
            // src 空 or rect.width === 0 → graceful skip
            if (typeof opts.onComplete === 'function') opts.onComplete();
            return null;
        }

        // 隱藏來源（mobile center cover）
        mobileCoverEl.setAttribute('data-ghost-hidden', 'true');
        gsap.set(mobileCoverEl, { opacity: 0 });

        // 讀目標 rect（lightbox 需已可見）
        var targetRect = coverImgEl.getBoundingClientRect();

        // objectPosition 平滑過渡（mirror play56cConstellationExit L258-259）
        var dur = (window.OpenAver && window.OpenAver.motion &&
                   window.OpenAver.motion.DURATION && window.OpenAver.motion.DURATION.medium) || 0.333;
        ghost.style.transition = 'object-position ' + dur + 's ease';
        ghost.style.objectPosition = 'center center';

        // race 防護
        gsap.killTweensOf(ghost);

        var tl = gsap.timeline({
            id: 'mobilePanelExit',
            onComplete: function () {
                cleanupGhost(ghost, mobileCoverEl, coverImgEl);
                if (typeof opts.onComplete === 'function') opts.onComplete();
            },
            onInterrupt: function () {
                // race 防護：onInterrupt 也 cleanup
                cleanupGhost(ghost, mobileCoverEl, coverImgEl);
            }
        });

        tl.to(ghost, {
            x: targetRect.left, y: targetRect.top,
            width: targetRect.width, height: targetRect.height,
            duration: dur,
            ease: 'fluent-accel'
        }, 0);

        return tl;
    }

    /**
     * 56c-T2 (CD-56C-2): Similar Scan Preview — lightbox 點 .bi-magic 時的 0.4s 預覽動畫
     *
     * 56c-T3fix: 改為 sparkle burst（10 顆四角星，stagger fade-in + scale + rotate + sine yoyo + accel fade-out）
     * 對應 magic.png 視覺隱喻；廢棄舊三層光帶（left dim / beam / right glow）。
     *
     * Timeline 0.4s 切片：
     *   0    → 0.20s: stagger fade-in + scale 0→1 + rotate +90deg
     *   0.20 → 0.30s: sine.inOut yoyo scale 1→1.15→1（閃爍感）
     *   0.25 → 0.40s: fade-out + scale 0.6（accel ease）
     *   0.40s: callback 絕對時刻觸發（與 56c-T2 契約一致）
     *
     * DOM 結構（56c-T3fix）：`coverEl` = `.lightbox-cover`，內含 `.sparkle-burst` overlay
     * （與 `<img x-ref="lightboxCoverImg">` 同層 absolute sibling）。inset:0 自動覆蓋封面區
     * 不擴及 metadata。Magic 按鈕另搬至 `.lightbox-content` 與 `.lightbox-close` 鏡射對稱。
     *
     * caller 責任：reduced-motion 由 caller 決定是否呼叫；本 helper 內**不 short-circuit**。
     *
     * @param {HTMLElement} coverEl - .lightbox-cover 容器（內含 .sparkle-burst overlay）
     * @param {Function} [onComplete] - 動畫完成 callback（缺 DOM 時也會立即觸發）
     * @returns {gsap.core.Timeline|null}
     */
    function play56cSimilarScanPreview(coverEl, onComplete) {
        var done = function () { if (typeof onComplete === 'function') onComplete(); };

        if (!coverEl) { done(); return null; }
        if (typeof gsap === 'undefined') { done(); return null; }

        // 56c-T3fix: .sparkle-burst 與 <img> 同層在 .lightbox-cover 內
        var burst = coverEl.querySelector('.sparkle-burst');
        if (!burst) { done(); return null; }
        var stars = burst.querySelectorAll('.sparkle-star');
        if (!stars || stars.length === 0) { done(); return null; }

        // race 防護（Codex P2-A 沿用）：連點時 kill 舊 timeline + reset stars，
        // 避免 fromTo 與殘留 inline style 疊加閃爍。clearProps 採精確列表（對齊既有
        // ghost-fly.js pattern），避免未來 stars 加 inline style 被誤清。
        gsap.killTweensOf([burst, stars]);
        gsap.set(stars, { clearProps: 'opacity,scale,rotation,transform' });
        gsap.set(burst, { opacity: 0 });

        var tl = gsap.timeline({ id: 'similarSparkleBurst' });
        tl.set(burst, { opacity: 1 });
        tl.set(stars, { opacity: 0, scale: 0, rotation: 'random(-30, 30)' });

        // Stagger fade-in + scale + rotate (0 → 0.20s, 10 顆 * 0.012 ≈ 0.12s 全部進場)
        tl.to(stars, {
            opacity: 1, scale: 1, rotation: '+=90',
            duration: 0.20, ease: 'fluent-decel',
            stagger: { each: 0.012, from: 'random' }
        }, 0);

        // 中段 sine.inOut yoyo (0.20 → 0.30s) — 閃爍感
        tl.to(stars, {
            scale: 1.15,
            duration: 0.05, ease: 'sine.inOut',
            yoyo: true, repeat: 1
        }, 0.20);

        // Fade-out (0.25 → 0.40s)
        tl.to(stars, {
            opacity: 0, scale: 0.6,
            duration: 0.15, ease: 'fluent-accel'
        }, 0.25);

        // Codex P3 沿用：callback 在 0.40s 絕對時刻觸發（與 56c-T2 契約一致）
        tl.call(done, null, 0.40);

        // 收尾：burst 容器 opacity 回 0（防殘留）
        tl.to(burst, { opacity: 0, duration: 0.05 }, '>');

        return tl;
    }

    /**
     * 99a-T5: Focal detect-first 星空等待迴圈 — force-detect（不定長 ~3.0-3.3s）等待期間的
     * 佔位動畫。與 play56cSimilarScanPreview（上）共用視覺語彙（.sparkle-star 四角星 shape +
     * --star-glow 香檳金 token），但型態不同：不是 0.4s 一次性、絕對時刻收尾的 timeline，而是
     * caller 可 start/stop 的 repeat:-1 loop（TASK-99a-T5 調查結論：不可直接重用
     * play56cSimilarScanPreview 或 BreathingManager，兩者型態都不合）。
     *
     * caller 責任（比照 play56cSimilarScanPreview 慣例）：
     * - PRM guard 由 caller 決定是否呼叫本函式，本 helper 內**不** short-circuit。
     * - caller 必須保留回傳值，稍後傳給 stopFocalDetectWait 對稱停止（單一啟動點 + 對稱停止點，
     *   見 state-lightbox.js openMask/_resetMask/_maskTeardown 的 _maskStopWaitAnim helper）。
     *
     * @param {HTMLElement} coverEl - .lightbox-cover 容器（內含 .lb-mask-wait-burst overlay）
     * @returns {{tl: gsap.core.Timeline, burst: Element, stars: NodeList}|null}
     */
    function playFocalDetectWait(coverEl) {
        if (!coverEl) return null;
        if (typeof gsap === 'undefined') return null;

        var burst = coverEl.querySelector('.lb-mask-wait-burst');
        if (!burst) return null;
        var stars = burst.querySelectorAll('.sparkle-star');
        if (!stars || stars.length === 0) return null;

        // race 防護（比照 play56cSimilarScanPreview 慣例）：理論上 openMask 的 session guard 已
        // 防止重入，這裡再保一層——kill 舊殘留 tween + reset stars，避免疊加閃爍。
        gsap.killTweensOf([burst, stars]);
        gsap.set(stars, { clearProps: 'opacity,scale,rotation,transform' });
        gsap.set(burst, { opacity: 1 });
        gsap.set(stars, { opacity: 0, scale: 0 });

        var tl = gsap.timeline({ id: 'focalDetectWait', repeat: -1 });

        // 進場 fade-in + scale（stagger，隨機起始製造非機械感）
        tl.to(stars, {
            opacity: 1, scale: 1,
            duration: 0.35, ease: 'fluent-decel',
            stagger: { each: 0.08, from: 'random' }
        }, 0);

        // 中段 sine.inOut yoyo 閃爍感（比照 play56cSimilarScanPreview 既有 sine.inOut yoyo 組合，
        // ui-conventions §5 不發明新 ease 曲線）
        tl.to(stars, {
            scale: 1.15,
            duration: 0.3, ease: 'sine.inOut',
            yoyo: true, repeat: 1
        }, 0.45);

        // 淡出（accel，與進場 decel 對稱），完整一輪後 repeat:-1 自然接續下一輪
        tl.to(stars, {
            opacity: 0, scale: 0,
            duration: 0.35, ease: 'fluent-accel',
            stagger: { each: 0.06, from: 'random' }
        }, 1.15);

        return { tl: tl, burst: burst, stars: stars };
    }

    /**
     * 99a-T5: 對稱停止 playFocalDetectWait（上）。kill timeline + clearProps 精確列表歸零
     * inline style（C26：不用 clearProps:'all'，只清實際動過的 props），讓容器回到 CSS 預設
     * opacity:0（下次 playFocalDetectWait 重新從乾淨狀態起）。
     *
     * idempotent：handle 為 null/undefined（尚未啟動過、或已停過一次）安全 no-op。
     *
     * @param {{tl: gsap.core.Timeline, burst: Element, stars: NodeList}|null} handle - playFocalDetectWait 回傳值
     */
    function stopFocalDetectWait(handle) {
        if (!handle) return;
        if (handle.tl && typeof handle.tl.kill === 'function') handle.tl.kill();
        if (typeof gsap === 'undefined') return;
        if (handle.stars) gsap.set(handle.stars, { clearProps: 'opacity,scale,rotation,transform' });
        if (handle.burst) gsap.set(handle.burst, { clearProps: 'opacity' });
    }

    // ─── 公開動畫函式 ──────────────────────────────────────────────────────

    var GhostFly = {
        createCoverGhost: createCoverGhost,
        cleanupGhost: cleanupGhost,
        cleanupStaleGhosts: cleanupStaleGhosts,

        // 56c-T2: Similar Mode 進退場 + scan preview helper（callsite 在 56c-T3 / T5）
        play56cConstellationEnter: play56cConstellationEnter,
        play56cConstellationExit: play56cConstellationExit,
        play56cSimilarScanPreview: play56cSimilarScanPreview,

        // 99a-T5: Focal detect-first 星空等待迴圈（start/stop 對稱，callsite 見 state-lightbox.js openMask）
        playFocalDetectWait: playFocalDetectWait,
        stopFocalDetectWait: stopFocalDetectWait,

        // 83b-T3: 行動相似面板封面飛行進 / 退場
        playMobilePanelEnter: playMobilePanelEnter,
        playMobilePanelExit: playMobilePanelExit,

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
            // US5-75b-T7 (CD-75b-12)：≤480px poster 格縮圖是「封面右半正面」cover 裁切，
            // 而 lightbox 封面是 contain 完整圖。posterCrop 旗標下：(A) ghost 對齊縮圖右裁
            // （消起飛 pan），(D) 落地以 crossfade 溶接 cover→contain（藏內容框法硬切 glitch）。
            var posterCrop = !!options.posterCrop;
            // 71b-T3 (CD-71b-5): 隱/還原對象上移到 .lightbox-cover 容器，一次蓋住
            // base img + T6 .lb-full overlay 兩層（容器 opacity 與各 img 自身 gate 正交）
            var coverEl = lbImg.closest('.lightbox-cover') ||
                lightboxEl.querySelector('.lightbox-cover');

            // C25 順序鐵律：先建 ghost（createCoverGhost 內部 cleanupStaleGhosts() 會還原
            // 所有 [data-ghost-hidden]），再 hide coverEl，否則剛 hide 立刻被還原
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) {
                if (typeof options.onComplete === 'function') options.onComplete();
                return null;
            }
            // (A) ghost 對齊縮圖的右半裁切（objectFit:cover 已由 createCoverGhost 設定）
            if (posterCrop) {
                ghost.style.objectPosition = 'right center';
            }

            // 隱藏真實 lightbox 封面容器（ghost 飛行期間，蓋 base + .lb-full 兩層）
            if (coverEl) {
                coverEl.setAttribute('data-ghost-hidden', '');
                gsap.set(coverEl, { opacity: 0 });
            }

            var dur = 0.38;
            var ease = 'power2.inOut';

            var tl = gsap.timeline({ id: 'ghostGridToLightbox' });
            tl.fromTo(ghost,
                { x: fromRect.left, y: fromRect.top, width: fromRect.width, height: fromRect.height },
                {
                    x: toRect.left, y: toRect.top, width: toRect.width, height: toRect.height,
                    duration: dur, ease: ease,
                    onComplete: function () {
                        if (posterCrop && coverEl) {
                            // (D) 溶接：contain 真圖淡入、ghost(cover,right) 淡出，
                            // 把 cover→contain 框法切換藏進 ~120ms dissolve（非硬切）。
                            coverEl.removeAttribute('data-ghost-hidden');
                            gsap.to(coverEl, { opacity: 1, duration: 0.12 });
                            gsap.to(ghost, {
                                opacity: 0, duration: 0.12,
                                onComplete: function () {
                                    if (ghost && ghost.parentNode) ghost.remove();
                                }
                            });
                        } else {
                            cleanupGhost(ghost, coverEl);
                        }
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
         * @param {object} [options] - { coverSrc, fromImg }
         * @returns {null} fire-and-forget
         */
        playLightboxToGrid: function (fromRect, targetCardEl, options) {
            options = options || {};
            if (!fromRect || !targetCardEl) return null;
            if (typeof gsap === 'undefined') return null;
            if (window.OpenAver && window.OpenAver.prefersReducedMotion) return null;

            if (!fromRect.width || fromRect.width === 0) return null;

            // 71b-T3 (CD-71b-5): 隱/還原對象上移到 .lightbox-cover 容器，一次蓋住
            // base img + T6 .lb-full overlay 兩層，避免 ghost 縮回過程與原位大圖疊圖。
            var fromImg = options.fromImg || document.querySelector('.lightbox-cover img');
            var coverEl = (fromImg && fromImg.closest('.lightbox-cover')) ||
                document.querySelector('.lightbox-cover');

            function abort() {
                // C25：hide 在 createCoverGhost 之後，abort 在 hide 之前 early-return 時
                // coverEl 尚未被 hide，gsap.set opacity:1 為 no-op，安全
                if (coverEl) {
                    gsap.set(coverEl, { opacity: 1 });
                    coverEl.removeAttribute('data-ghost-hidden');
                }
                return null;
            }

            // 判斷目標卡片是否在 viewport 內
            var targetImg = targetCardEl.querySelector('.av-card-preview-img img, .actress-card-photo img');
            if (!targetImg) return abort();

            var toRect = targetImg.getBoundingClientRect();
            if (!toRect || toRect.width === 0) return abort();

            var viewportH = window.innerHeight;
            var viewportW = window.innerWidth;
            var inViewport = (
                toRect.top < viewportH && toRect.bottom > 0 &&
                toRect.left < viewportW && toRect.right > 0
            );

            if (!inViewport) {
                // 退化：直接 fade-out（不強制 scroll）
                return abort();
            }

            var coverSrc = options.coverSrc || targetImg.src;
            // C25 順序鐵律：先建 ghost（createCoverGhost 內部 cleanupStaleGhosts() 會還原
            // 所有 [data-ghost-hidden]），再 hide coverEl，否則剛 hide 立刻被還原
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) return null;

            // 隱藏 lightbox 封面容器（蓋 base + .lb-full 兩層），與 OPEN 對稱
            // 補掛 data-ghost-hidden（舊版漏掛 → stale-cleanup 兜不到）
            if (coverEl) {
                coverEl.setAttribute('data-ghost-hidden', '');
                gsap.set(coverEl, { opacity: 0 });
            }

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
                        // 71b-T3: 多帶 coverEl，與 OPEN 對稱還原來源 .lightbox-cover 容器
                        // （修舊不對稱：CLOSE 從不還原來源容器 → 殘 opacity:0，Codex P1）
                        cleanupGhost(ghost, targetImg, coverEl);
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
         * 92b-T2 (CD-92b-3/5/6/7): 入庫飛入共用入口 — 取代 playToIcon。
         *
         * 三段：起飛 → 懸停（浮動+呼吸，給眼睛捕捉時間）→ 縮入落地（通用 scale
         * bump + glow）+ 尾段漸隱。參數化、不讀 this（D-D1：不綁 search 專屬假設，
         * 未來 scanner 可傳自己的 fromEl/coverSrc/toEl/fallback）。
         *
         * 分支矩陣（皆非 silent）：
         *   toEl 不可見           → fallback.toastFn(message)
         *   reduced-motion/no-gsap → 僅 onLanding(toEl)（無飛行、無 scale/glow）
         *   fromEl 缺/不可見        → 僅 onLanding(toEl)（無起點可飛）
         *   正常                   → 完整三段 + scale/glow + onLanding
         *
         * C21 通用性邊界（Codex F2）：落地反饋期間對 toEl 加 .gsap-animating 以停用 CSS
         * transition，但 .gsap-animating 的 transition-kill 規則目前是各元件 scoped
         * （.av-card-preview / .hero-card / .showcase-lightbox / .sg-main-img）。現行 caller
         * #sidebar-showcase-link 只 transition color/background（無 transform/filter），故不觸
         * C21、加 class 為 inert，無回歸。**未來若 caller 的 toEl 有 transition: transform/filter，
         * 須為該 target 補一條 `.<target>.gsap-animating { transition: none }` 規則**，否則落地
         * scale/glow 可能被 CSS transition 幽靈化（scanner 接線 branch 一併補、可端到端驗）。
         *
         * @param {object} options - { fromEl, coverSrc, toEl, hold=0.5, holdOffset,
         *                             endSize=40, duration=0.65, onLanding,
         *                             fallback:{ toastFn, message } }
         * @returns {gsap.core.Timeline|null}
         */
        playInboundFly: function (options) {
            options = options || {};
            var fromEl = options.fromEl;
            var toEl = options.toEl;
            var onLanding = typeof options.onLanding === 'function'
                ? options.onLanding : function () {};
            var fallback = options.fallback || {};
            var fireFallback = function () {
                if (typeof fallback.toastFn === 'function') fallback.toastFn(fallback.message);
            };

            // 終點缺 / 不可見（sidebar display:none、rect 0）→ 手機/窄螢幕 fallback
            var toRect = toEl && toEl.getBoundingClientRect();
            if (!toRect || toRect.width === 0 || toRect.height === 0) {
                fireFallback();
                return null;
            }

            // 終點可見。reduced-motion / 無 gsap → 不播飛行+scale/glow，僅輕量 onLanding
            if (typeof gsap === 'undefined' ||
                (window.OpenAver && window.OpenAver.prefersReducedMotion)) {
                onLanding(toEl);
                return null;
            }

            // 起點缺 / 不可見 → 無可飛，退化 onLanding（終點可見）
            var fromRect = fromEl && fromEl.getBoundingClientRect();
            if (!fromRect || fromRect.width === 0 || fromRect.height === 0) {
                onLanding(toEl);
                return null;
            }

            var coverSrc = options.coverSrc ||
                (fromEl.tagName === 'IMG' ? fromEl.src : '');
            var ghost = createCoverGhost(coverSrc, fromRect);
            if (!ghost) {
                onLanding(toEl);
                return null;
            }

            var duration = options.duration || 0.65;
            var hold = (options.hold != null) ? options.hold : 0.5;
            var endSize = options.endSize || 40;

            var toCenterX = toRect.left + toRect.width / 2;
            var toCenterY = toRect.top + toRect.height / 2;
            // 懸停偏移點：目標上方一點（預設沿 y 負向偏移 endSize）
            var holdOffset = (options.holdOffset != null) ? options.holdOffset : endSize;
            var holdSize = endSize * 1.6;              // 懸停比落地大、看得清封面
            var holdX = toCenterX - holdSize / 2;
            var holdY = toCenterY - holdSize / 2 - holdOffset;

            gsap.killTweensOf(ghost);

            // 落地反饋：通用 scale bump + glow（作用任意 toEl，不依賴特定 class）
            var landed = false;
            var doLanding = function () {
                if (landed) return;
                landed = true;
                // 並發序列化（Codex F1）：兩次 scrapeSingle 幾乎同時完成時，兩顆 ghost 的
                // doLanding 會對同一 toEl（#sidebar-showcase-link）各起一條 landing timeline。
                // 先 kill 任何 in-flight landing tween，讓最新一次落地勝出——舊 landing 停止
                // 寫 toEl，新 landing 每 tick 重寫 transform/filter 並由自己的 clearLanding 收尾，
                // 避免舊 landing 的 clearLanding 在新 landing 進行中清掉 transform/filter+class。
                gsap.killTweensOf(toEl);
                // C21：toEl 可能有 CSS transition:transform → gsap-animating 停用，
                //      onComplete + onInterrupt 兩路徑都清 class + clearProps（對稱契約，
                //      源 playMobilePanelEnter/Exit，非照抄 playActressToHeroCard 漏 onInterrupt）
                toEl.classList.add('gsap-animating');
                var clearLanding = function () {
                    // C21 順序：先清 inline props（transition 仍被 class 停用），再移 class
                    // 重啟 transition —— 避免對帶 base transform 的通用 toEl 觸發幽靈過渡。
                    gsap.set(toEl, { clearProps: 'transform,filter' });
                    toEl.classList.remove('gsap-animating');
                };
                gsap.timeline({ onComplete: clearLanding, onInterrupt: clearLanding })
                    .fromTo(toEl,
                        { scale: 1.18 },
                        { scale: 1.0, duration: 0.32, ease: 'power2.out' }
                    )
                    .fromTo(toEl,
                        { filter: 'drop-shadow(0 0 14px rgba(120,190,255,0.7))' },
                        { filter: 'drop-shadow(0 0 0px rgba(0,0,0,0))', duration: 0.4, ease: 'power2.out' },
                        '<'
                    );
                onLanding(toEl);
            };

            var tl = gsap.timeline({
                id: 'ghostInboundFly',
                onComplete: function () { cleanupGhost(ghost); },
                onInterrupt: function () { cleanupGhost(ghost); }
            });

            // 段 1：起飛 → 懸停偏移點（保持較大尺寸、opacity 1）
            tl.fromTo(ghost,
                { x: fromRect.left, y: fromRect.top, width: fromRect.width, height: fromRect.height, opacity: 1, borderRadius: '8px' },
                { x: holdX, y: holdY, width: holdSize, height: holdSize, opacity: 1, borderRadius: '12px', duration: duration, ease: 'power2.inOut' }
            );

            // 段 2：懸停 — 原地微浮動 + 呼吸（brightness），給眼睛捕捉時間
            if (hold > 0) {
                tl.to(ghost, {
                    y: holdY + 4,
                    filter: 'brightness(1.15)',
                    duration: hold / 2,
                    ease: 'sine.inOut',
                    yoyo: true,
                    repeat: 1
                });
            }

            // 段 3：縮入落地 — onStart 觸發落地反饋（撞擊感同步）
            var landDur = 0.34;
            tl.to(ghost, {
                x: toCenterX - endSize / 2,
                y: toCenterY - endSize / 2,
                width: endSize,
                height: endSize,
                borderRadius: '50%',
                filter: 'brightness(1)',
                duration: landDur,
                ease: 'power2.in',
                onStart: doLanding
            });
            // 尾段漸隱（疊在落地段最後 ~35%，取代 playToIcon 抵達即透明的跳變）
            tl.to(ghost, {
                opacity: 0,
                duration: landDur * 0.35,
                ease: 'power1.in'
            }, '-=' + (landDur * 0.35));

            return tl;
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
export { GhostFly };
