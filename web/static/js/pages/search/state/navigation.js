/**
 * SearchState - Navigation Mixin
 * 包含：導航邏輯（navigate, loadMore, handleKeydown）
 */
window.SearchStateMixin_Navigation = {
    // ===== Navigation Methods =====

    /**
     * 導航到相對位置
     * @param {number} delta - 偏移量（-1 = 上一個，1 = 下一個）
     */
    navigate(delta) {
        const newIndex = this.currentIndex + delta;

        // 往左且已在第一個 → 切換到上一個檔案
        if (delta < 0 && newIndex < 0) {
            if (this.currentFileIndex > 0) {
                this.switchToFile(this.currentFileIndex - 1, 'last');
            }
            return;
        }

        // 往右且到最後一個
        if (delta > 0 && newIndex >= this.searchResults.length) {
            if (this.hasMoreResults && !this.isLoadingMore) {
                this.loadMore();
                return;
            }
            if (this.currentFileIndex < this.fileList.length - 1) {
                this.switchToFile(this.currentFileIndex + 1, 'first');
                return;
            }
            return;
        }

        // 正常範圍內導航
        if (newIndex >= 0 && newIndex < this.searchResults.length) {
            this.currentIndex = newIndex;

            // 修正 2: 同步回 core.js
            const coreState = window.SearchCore?.state;
            if (coreState) {
                coreState.currentIndex = this.currentIndex;
            }

            // Reset cover error on navigation
            this.coverError = '';
            this._coverRetried = false;

            if (window.SearchUI?.preloadImages) {
                window.SearchUI.preloadImages(this.currentIndex + 1, 3);
            }
        }
    },

    /**
     * 載入更多結果
     */
    async loadMore() {
        if (this.isLoadingMore || !this.hasMoreResults || !this.currentQuery) return;

        this.isLoadingMore = true;
        const newOffset = this.currentOffset + this.PAGE_SIZE;

        try {
            const response = await fetch(
                `/api/search?q=${encodeURIComponent(this.currentQuery)}&offset=${newOffset}&limit=${this.PAGE_SIZE}`
            );
            const data = await response.json();

            if (response.ok && data.success && data.data && data.data.length > 0) {
                this.searchResults = this.searchResults.concat(data.data);
                this.currentOffset = newOffset;
                this.hasMoreResults = data.has_more;
                this.currentIndex = this.searchResults.length - data.data.length;

                // 修正 2: 同步回 core.js
                const coreState = window.SearchCore?.state;
                if (coreState) {
                    coreState.searchResults = this.searchResults;
                    coreState.currentOffset = this.currentOffset;
                    coreState.hasMoreResults = this.hasMoreResults;
                    coreState.currentIndex = this.currentIndex;
                }

                if (window.SearchUI?.preloadImages) {
                    window.SearchUI.preloadImages(this.currentIndex + 1, 5);
                }

                // T4: Load more 後查詢本地狀態
                if (window.SearchCore?.checkLocalStatus) {
                    window.SearchCore.checkLocalStatus(this.searchResults);
                }
            } else {
                this.hasMoreResults = false;
            }
        } catch (err) {
            console.error('載入更多失敗:', err);
        } finally {
            this.isLoadingMore = false;

            // 同步回 core.js
            const coreState = window.SearchCore?.state;
            if (coreState) {
                coreState.isLoadingMore = this.isLoadingMore;
            }
        }
    },

    /**
     * 處理鍵盤導航
     * @param {KeyboardEvent} event - 鍵盤事件
     */
    handleKeydown(event) {
        // 忽略在搜尋框內的按鍵
        const queryInput = document.getElementById('searchQuery');
        if (document.activeElement === queryInput) return;

        // T2a: Lightbox 鍵盤導航（優先）
        if (this.lightboxOpen) {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.closeLightbox();
                return;
            }
            // Block arrow keys in actress lightbox mode (single photo, no navigation)
            if (this.actressLightboxMode) {
                event.preventDefault();
                return;
            }
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                this.prevLightboxVideo();
                return;
            }
            if (event.key === 'ArrowRight') {
                event.preventDefault();
                this.nextLightboxVideo();
                return;
            }
        }

        // Detail 模式導航（Grid 模式不觸發）
        if (this.displayMode !== 'detail') return;

        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            this.navigate(-1);
        } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            this.navigate(1);
        }
    }
};
