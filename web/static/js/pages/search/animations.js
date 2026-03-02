/**
 * SearchAnimations — /search 頁面動畫模組
 *
 * 暴露 window.SearchAnimations 物件，提供：
 *   - playCardStreamIn(cardEl)  單卡 SSE 漸進進場動畫
 *   - playGridFadeIn(gridEl)    skeleton grid 整體轉場淡入
 *
 * C2：此檔案是 pages/ 目錄下被允許直接呼叫 GSAP 的兩個檔案之一
 *      （另一個為 motion-lab.js）。
 * C4：每個動畫開頭 gsap.killTweensOf(target) 清舊動畫。
 * C6：不使用 rotationX / rotationY / rotationZ。
 *
 * Graceful fallback：若 GSAP 未載入，所有方法安全降級（不拋錯）。
 * search-flow.js 透過 window.SearchAnimations?.playCardStreamIn?.(card)
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

    window.SearchAnimations = {

        /**
         * 單卡 SSE 漸進進場動畫（fadeScale 風格，T2 選定）
         *
         * 動畫目標：.av-card-preview-img（圖片區域），番號 footer 保持錨定不動。
         * Reduced Motion：直接 return null，卡片已由 Alpine 填入，無需額外 set。
         *
         * @param {Element} cardEl - .av-card-preview 元素（整張卡）
         * @returns {gsap.core.Tween|null}
         */
        playCardStreamIn: function (cardEl) {
            if (!cardEl) return null;
            if (shouldSkip()) return null;
            if (typeof gsap === 'undefined') return null;

            // 動畫目標：圖片區域，番號 footer 固定不動
            var imgEl = cardEl.querySelector('.av-card-preview-img') || cardEl;

            // C4: 清除舊動畫
            gsap.killTweensOf(imgEl);

            // fadeScale 風格（T2 選定，對應 motion-lab.js L631-635）
            // C6: 不使用 rotationX/Y/Z
            return gsap.fromTo(imgEl,
                { opacity: 0, scale: 0.92 },
                { opacity: 1, scale: 1, duration: 0.3, ease: 'power2.out' }
            );
        },

        /**
         * Skeleton grid 整體轉場淡入（seed 收到後、Progress → Grid 轉場）
         *
         * 輕量整體淡入，讓 skeleton grid 出現時不突兀。
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
        }
    };
})();
