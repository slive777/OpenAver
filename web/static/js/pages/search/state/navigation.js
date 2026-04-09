/**
 * SearchState - Navigation Mixin
 * 包含：導航邏輯（navigate, loadMore, handleKeydown）
 */
window.SearchStateMixin_Navigation = {
    // ===== Navigation Methods =====

    /**
     * 預載下幾張圖片（從 ui.js 搬移）
     */
    preloadImages(startIndex, count = 5) {
        for (let i = startIndex; i < Math.min(startIndex + count, this.searchResults.length); i++) {
            if (this.searchResults[i]?.cover) {
                const img = new Image();
                img.src = `/api/proxy-image?url=${encodeURIComponent(this.searchResults[i].cover)}`;
            }
        }
    },

    /**
     * 導航到相對位置
     * @param {number} delta - 偏移量（-1 = 上一個，1 = 下一個）
     */
    navigate(delta) {
        // T8: nav-btn 點擊觸發 navigate 時，自動關閉 Sample Gallery
        if (this.sampleGalleryOpen) this.closeSampleGallery();

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

            this.preloadImages(this.currentIndex + 1, 3);
        }
    },

    /**
     * 載入更多結果
     * @param {string} trigger - 呼叫入口（'detail' | 'grid' | 'lightbox'），預設 'detail'
     * @returns {{ loadedCount: number, oldLength: number }|null}
     */
    async loadMore(trigger = 'detail') {
        if (this.isLoadingMore || !this.hasMoreResults || !this.currentQuery) return null;

        this.isLoadingMore = true;
        const oldLength = this.searchResults.length;
        const newOffset = this.currentOffset + this.PAGE_SIZE;
        const loadMoreSignal = this._getAbortSignal('loadMore');

        try {
            const response = await fetch(
                `/api/search?q=${encodeURIComponent(this.currentQuery)}&offset=${newOffset}&limit=${this.PAGE_SIZE}`,
                { signal: loadMoreSignal }
            );
            const data = await response.json();

            if (response.ok && data.success && data.data && data.data.length > 0) {
                const loadedCount = data.data.length;
                this.searchResults = this.searchResults.concat(data.data);
                this.currentOffset = newOffset;
                this.hasMoreResults = data.has_more;
                this._resetCoverState();

                this.preloadImages(oldLength + 1, 5);

                // T4: Load more 後查詢本地狀態
                this.checkLocalStatus(this.searchResults);

                // 不動 currentIndex — 由呼叫端根據 trigger 自行處理
                return { loadedCount, oldLength };
            } else {
                this.hasMoreResults = false;
                return null;
            }
        } catch (err) {
            if (err.name === 'AbortError') return null;  // T4.3: 靜默忽略取消
            console.error('載入更多失敗:', err);
            return null;
        } finally {
            this.isLoadingMore = false;
            this._clearAbort('loadMore', loadMoreSignal);  // T4.3: 操作完成清除 registry（比對 signal 避免刪掉新請求）
        }
    },

    /**
     * T3a: Grid 按鈕入口 — await loadMore 後播 append cascade 動畫
     * 不動 currentIndex（保留用戶目前選取）
     */
    async gridLoadMore() {
        const result = await this.loadMore('grid');
        if (!result || result.loadedCount === 0) return;
        // Grid: 不動 currentIndex — 保留用戶目前選取
        this.$nextTick(() => {
            const gridEl = document.querySelector('.search-grid');
            if (!gridEl) return;
            const newCards = Array.from(gridEl.querySelectorAll('[data-slot]'))
                .filter(el => parseInt(el.getAttribute('data-slot'), 10) >= result.oldLength);
            window.SearchAnimations?.playAppendCascade?.(newCards);
        });
    },

    /**
     * 處理鍵盤導航
     * @param {KeyboardEvent} event - 鍵盤事件
     */
    handleKeydown(event) {
        // 忽略在搜尋框內的按鍵
        const queryInput = this.$refs.searchQuery;
        if (document.activeElement === queryInput) return;

        // T8: Sample Gallery 鍵盤導航（最高優先：gallery 疊在 lightbox 之上，ESC 先關 gallery）
        if (this.sampleGalleryOpen) {
            if (event.key === 'Escape') {
                event.preventDefault();
                this.closeSampleGallery();
                return;
            }
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                this.prevSampleGallery();
                return;
            }
            if (event.key === 'ArrowRight') {
                event.preventDefault();
                this.nextSampleGallery();
                return;
            }
            return;
        }

        // T2a: Lightbox 鍵盤導航（sampleGalleryOpen 已排除後處理）
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
