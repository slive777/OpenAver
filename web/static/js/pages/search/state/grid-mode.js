/**
 * SearchState - Grid Mode Mixin
 * 包含：Grid 模式切換、Lightbox 控制
 */
window.SearchStateMixin_GridMode = {
    // ===== Display Mode Toggle =====

    /**
     * 切換 Detail ↔ Grid 模式
     */
    toggleDisplayMode() {
        this.displayMode = this.displayMode === 'detail' ? 'grid' : 'detail';
        this._localBorderPlayed = {};  // T4: 切換模式時重置，讓動畫在新佈局重新標示
        this.saveState();
    },

    // ===== Lightbox Control =====

    /**
     * 開啟 Lightbox
     * @param {number} index - 搜尋結果索引
     */
    openLightbox(index) {
        this.lightboxIndex = index;
        this.lightboxOpen = true;
        this.actressLightboxMode = false;  // 從 actress 模式切回普通模式
        // 同步 currentIndex（讓 Detail 與 Grid 保持一致）
        this.currentIndex = index;
        const coreState = window.SearchCore?.state;
        if (coreState) {
            coreState.currentIndex = this.currentIndex;
        }
    },

    /**
     * 關閉 Lightbox
     */
    closeLightbox() {
        this.lightboxOpen = false;
        this.actressLightboxMode = false;
    },

    /**
     * 開啟 Actress Lightbox（Hero Card 專用）
     */
    openActressLightbox() {
        this.lightboxOpen = true;
        this.actressLightboxMode = true;
    },

    /**
     * Lightbox 上一部
     */
    prevLightboxVideo() {
        if (this.lightboxIndex > 0) {
            this.lightboxIndex--;
            this.currentIndex = this.lightboxIndex;
            const coreState = window.SearchCore?.state;
            if (coreState) {
                coreState.currentIndex = this.currentIndex;
            }
        }
    },

    /**
     * Lightbox 下一部
     */
    nextLightboxVideo() {
        if (this.lightboxIndex < this.searchResults.length - 1) {
            this.lightboxIndex++;
            this.currentIndex = this.lightboxIndex;
            const coreState = window.SearchCore?.state;
            if (coreState) {
                coreState.currentIndex = this.currentIndex;
            }
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
        return this.searchResults[this.lightboxIndex] || null;
    },

    // ===== Grid ↔ Detail 切換 =====

    /**
     * 從 Grid 切換到 Detail 模式
     * @param {number} index - 搜尋結果索引
     */
    switchToDetail(index) {
        this.displayMode = 'detail';
        this.currentIndex = index;
        const coreState = window.SearchCore?.state;
        if (coreState) {
            coreState.currentIndex = this.currentIndex;
        }
        this.saveState();
    },

    /**
     * 複製本地路徑
     * @param {string} path - 檔案路徑
     */
    copyPath(path) {
        if (!path) return;
        navigator.clipboard.writeText(path).then(() => {
            console.log('[Grid] 路徑已複製:', path);
            // T6b: 統一 toast
            this.showToast('路徑已複製', 'success');
        }).catch(err => {
            console.error('[Grid] 複製失敗:', err);
            this.showToast('複製失敗', 'error');
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
