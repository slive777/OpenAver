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
        // T7: nav-btn 點擊觸發 navigate 時，自動關閉 Sample Lightbox
        if (this.sampleLightboxOpen) this.closeSampleLightbox();

        let newIndex = this.currentIndex + delta;

        // U11b: skip _failed items (C30)
        while (newIndex >= 0 && newIndex < this.searchResults.length && this.searchResults[newIndex]._failed) {
            newIndex += delta;
        }

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
            // C18: interrupt 舊動畫（不用 isNavigating lock，每次按鍵都立即回應）
            var detailEl = document.querySelector('.av-card-full');
            if (typeof gsap !== 'undefined' && detailEl) {
                gsap.killTweensOf(detailEl);
            }

            // State change（Alpine re-render）
            this.currentIndex = newIndex;

            // U8b: reset cover state on navigation
            this._resetCoverState();

            // U5: fire-and-forget slide-in 動畫（$nextTick 確保 Alpine patch 新內容後再動畫，C17 一致）
            var direction = delta > 0 ? 'next' : 'prev';
            this.$nextTick(() => {
                var el = document.querySelector('.av-card-full');
                window.SearchAnimations?.playSlideIn?.(el, direction);
            });

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
        const loadMoreSignal = this._getAbortSignal('loadMore');

        try {
            const response = await fetch(
                `/api/search?q=${encodeURIComponent(this.currentQuery)}&offset=${newOffset}&limit=${this.PAGE_SIZE}`,
                { signal: loadMoreSignal }
            );
            const data = await response.json();

            if (response.ok && data.success && data.data && data.data.length > 0) {
                this.searchResults = this.searchResults.concat(data.data);
                this.currentOffset = newOffset;
                this.hasMoreResults = data.has_more;
                this.currentIndex = this.searchResults.length - data.data.length;
                this._resetCoverState();

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
            if (err.name === 'AbortError') return;  // T4.3: 靜默忽略取消
            console.error('載入更多失敗:', err);
        } finally {
            this.isLoadingMore = false;
            this._clearAbort('loadMore', loadMoreSignal);  // T4.3: 操作完成清除 registry（比對 signal 避免刪掉新請求）
        }
    },

    /**
     * 處理鍵盤導航
     * @param {KeyboardEvent} event - 鍵盤事件
     */
    handleKeydown(event) {
        // 忽略在搜尋框內的按鍵
        const queryInput = this.$refs.searchQuery;
        if (document.activeElement === queryInput) return;

        // T2a: Lightbox 鍵盤導航（優先）
        if (this.lightboxOpen) {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.closeLightbox();  // closeLightbox handles kill + cleanup + generation++
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

        // T7: Sample Lightbox 鍵盤導航（Grid Lightbox 已排除後處理，兩者不同時為 true）
        if (this.sampleLightboxOpen) {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.closeSampleLightbox();
                return;
            }
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                this.prevSample();
                return;
            }
            if (event.key === 'ArrowRight') {
                event.preventDefault();
                this.nextSample();
                return;
            }
            return;
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
