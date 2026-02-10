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
     * Lightbox 背景點擊處理（點擊背景關閉）
     * @param {MouseEvent} event - 點擊事件
     */
    handleLightboxBackdropClick(event) {
        if (event.target.classList.contains('showcase-lightbox')) {
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
            // Toast 提示（可選）
            if (window.SearchUI?.showToast) {
                window.SearchUI.showToast('路徑已複製');
            }
        }).catch(err => {
            console.error('[Grid] 複製失敗:', err);
        });
    }
};
