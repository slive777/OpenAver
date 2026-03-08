/**
 * SearchState - Grid Mode Mixin
 * 包含：Grid 模式切換、Lightbox 控制
 */
window.SearchStateMixin_GridMode = {
    // ===== Display Mode Toggle =====

    /**
     * 切換 Detail ↔ Grid 模式（U4: C17 三步動畫）
     */
    toggleDisplayMode() {
        var wasDetail = this.displayMode === 'detail';

        // C17 step 1: capture BEFORE state change
        var fromRect = null;
        var coverSrc = null;
        if (wasDetail) {
            var detailEl = document.querySelector('.av-card-full');
            var detailImg = detailEl ? detailEl.querySelector('.av-card-full-cover-img') : null;
            if (detailImg && detailImg.complete && detailImg.getBoundingClientRect().width > 0) {
                fromRect = detailImg.getBoundingClientRect();
                coverSrc = detailImg.src;
            }
        }

        // C17 step 2: state change (Alpine render)
        this.displayMode = wasDetail ? 'grid' : 'detail';
        this.saveState();

        // C17 step 3: animate (fire-and-forget)
        this.$nextTick(() => {
            if (wasDetail && fromRect && coverSrc) {
                // Detail -> Grid: ghost fly-back
                var grid = document.querySelector('.search-grid');
                var targetCard = grid ? grid.querySelector('[data-slot="' + this.currentIndex + '"]') : null;
                window.SearchAnimations?.playDetailToGrid?.(fromRect, targetCard, { coverSrc: coverSrc });
            } else if (!wasDetail) {
                // Grid -> Detail: detail entry
                var newDetailEl = document.querySelector('.av-card-full');
                window.SearchAnimations?.playDetailEntry?.(newDetailEl);
            }
        });
    },

    // ===== Lightbox Control =====

    /**
     * 開啟 Lightbox
     * @param {number} index - 搜尋結果索引
     */
    openLightbox(index) {
        this.lightboxIndex = index;
        this.lightboxOpen = true;
        // 同步 currentIndex（讓 Detail 與 Grid 保持一致）
        this.currentIndex = index;
    },

    /**
     * 關閉 Lightbox
     */
    closeLightbox() {
        this.lightboxOpen = false;
    },

    /**
     * 開啟 Actress Lightbox（Hero Card 專用）
     */
    openActressLightbox() {
        this.lightboxIndex = -1;
        this.lightboxOpen = true;
    },

    /**
     * Lightbox 上一部
     */
    prevLightboxVideo() {
        if (this.lightboxIndex === -1) {
            // Already at actress photo (leftmost) — do nothing
            return;
        }
        if (this.lightboxIndex === 0 && this.actressProfile) {
            // At first cover and actress profile exists → go to actress photo
            this.lightboxIndex = -1;
            return;
        }
        if (this.lightboxIndex > 0) {
            // U11b: skip _failed items going backwards
            let newIdx = this.lightboxIndex - 1;
            while (newIdx >= 0 && this.searchResults[newIdx]._failed) {
                newIdx--;
            }
            if (newIdx >= 0) {
                this.lightboxIndex = newIdx;
                this.currentIndex = newIdx;
            } else if (this.actressProfile) {
                // all items before current are _failed, jump to actress photo
                this.lightboxIndex = -1;
            }
            // else: no valid items and no actress → don't move
        }
    },

    /**
     * Lightbox 下一部
     */
    nextLightboxVideo() {
        if (this.lightboxIndex === -1) {
            // U11b: from actress photo, find first non-_failed item
            const firstValid = this.searchResults.findIndex(r => !r._failed);
            if (firstValid !== -1) {
                this.lightboxIndex = firstValid;
                this.currentIndex = firstValid;
            }
            // else: no valid items → don't move
            return;
        }
        if (this.lightboxIndex < this.searchResults.length - 1) {
            // U11b: skip _failed items going forward
            let newIdx = this.lightboxIndex + 1;
            while (newIdx < this.searchResults.length && this.searchResults[newIdx]._failed) {
                newIdx++;
            }
            if (newIdx < this.searchResults.length) {
                this.lightboxIndex = newIdx;
                this.currentIndex = newIdx;
            }
            // else: no more valid items → don't move
        }
    },

    /**
     * Lightbox 背景點擊處理（點擊背景關閉 / 點擊卡片切換）
     * @param {MouseEvent} event - 點擊事件
     */
    handleLightboxBackdropClick(event) {
        // T5: 對齊 showcase.js L420-446 的 Click-through 邏輯

        // 如果點擊的是 lightbox-content 內部，不處理（對齊 showcase）
        if (event.target.closest('.lightbox-content')) return;

        // 暫時隱藏 lightbox 來檢測下方元素
        const lightbox = event.currentTarget;
        lightbox.style.display = 'none';

        // 找到點擊位置下的元素
        const elementBelow = document.elementFromPoint(event.clientX, event.clientY);

        // 恢復 lightbox
        lightbox.style.display = '';

        // 檢查是否是卡片 → 觸發卡片自身的 @click handler（hero card / 普通卡片都適用）
        const cardEl = elementBelow?.closest('.search-grid .av-card-preview') || null;
        if (cardEl) {
            cardEl.click();
        } else {
            this.closeLightbox();
        }
    },

    /**
     * 取得當前 Lightbox 影片
     * @returns {Object|null} 當前影片資料
     */
    currentLightboxVideo() {
        if (this.lightboxIndex < 0) return null;
        return this.searchResults[this.lightboxIndex] || null;
    },

    // ===== Grid ↔ Detail 切換 =====

    /**
     * 從 Grid 切換到 Detail 模式（U4: C17 三步 ghost 轉場）
     * @param {number} index - 搜尋結果索引
     */
    switchToDetail(index) {
        // 防禦：若 Lightbox 仍開啟，先關閉（避免覆蓋層影響 grid 卡片座標）
        if (this.lightboxOpen) {
            this.lightboxOpen = false;
        }

        // C17 step 1: capture source rect BEFORE state change
        var grid = document.querySelector('.search-grid');
        var card = grid ? grid.querySelector('[data-slot="' + index + '"]') : null;
        var img = card ? card.querySelector('.av-card-preview-img img') : null;
        var fromRect = (img && img.complete && img.getBoundingClientRect().width > 0)
            ? img.getBoundingClientRect() : null;
        var coverSrc = img ? img.src : null;

        // C17 step 2: state change (Alpine render)
        this.displayMode = 'detail';
        this.currentIndex = index;
        this._resetCoverState();
        this.saveState();

        // C17 step 3: animate (fire-and-forget)
        this.$nextTick(() => {
            var detailEl = document.querySelector('.av-card-full');
            if (fromRect && coverSrc) {
                window.SearchAnimations?.playGridToDetail?.(fromRect, detailEl, { coverSrc: coverSrc });
            } else {
                // Ghost fallback: full detail entry
                window.SearchAnimations?.playDetailEntry?.(detailEl);
            }
        });
    },

    /**
     * 標記 Grid 圖片載入失敗
     * @param {number} index - 卡片索引
     */
    markImageError(index) {
        this._gridImageErrors = new Set([...this._gridImageErrors, index]);
    }
};
