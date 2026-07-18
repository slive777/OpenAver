/**
 * SearchState - Navigation Mixin
 * 包含：導航邏輯（navigate, loadMore, handleKeydown）
 */
import { detectSwipe } from '@/shared/swipe.js';
import { isHorizontalWheel, isVerticalWheel, createWheelNav } from '@/shared/wheel-nav.js';

// 排除清單容器（橫向捲動列表/表格）：命中即整條 wheel handler 提早 return，
// 讓原生橫向捲動不受影響（見 TASK-102d-T1.md「技術要點」排除清單段）。
const WHEEL_EXCLUDE_SELECTOR = '.sample-strip, .sg-thumbs, .picker-candidates-grid, .table-scroll-container, .overflow-x-auto';
// 102d P2b（owner 拍板 2026-07-19）：overlay 內可垂直捲動的子容器（lightbox metadata 面板，
// search.css:949 `.lightbox-metadata{overflow-y:auto}`）——垂直滾輪命中時交還原生捲動，
// 不吃導航。Search detail 頁（`.av-card-full-info`）不在此清單：detail 不是 overlay，
// vertical 分支在 handleWheel 頂端就已對非 overlay 狀態早退，不會走到本排除檢查。
const WHEEL_VERTICAL_EXCLUDE_SELECTOR = '.lightbox-metadata';

export function searchStateNavigation() {
    // 三個獨立累積器（Search Detail / Search 劇照 / Search Lightbox）——各自閉包狀態，
    // 避免不同 UI 分支的冷卻窗互相干擾（見 wheel-nav.js 頂部說明）。
    const wheelNavDetail = createWheelNav();
    const wheelNavSampleGallery = createWheelNav();
    const wheelNavLightbox = createWheelNav();
    // 102d P2b（owner 拍板 2026-07-19）：overlay 垂直滾輪＝上/下一張。獨立軸別累積器
    // （sample gallery / lightbox 各自水平+垂直兩個實例）。Search detail 絕對不碰
    // （spec 明文：垂直滾輪＝捲頁面），故無 wheelNavDetailV。
    const wheelNavSampleGalleryV = createWheelNav({ axis: 'vertical' });
    const wheelNavLightboxV = createWheelNav({ axis: 'vertical' });

    return {
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
    async navigate(delta) {
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
                const result = await this.loadMore('detail');
                if (!result || result.loadedCount === 0) return;
                // C17 state-first：先改 index，再 $nextTick 播動畫
                this.currentIndex = result.oldLength;
                this.$nextTick(() => {
                    var el = document.querySelector('.av-card-full');
                    window.SearchAnimations?.playSlideIn?.(el, 'next');
                });
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

    // ==================== Detail Cover Swipe (81c-T4) ====================

    _dtTouchStart(e) {
        if (e.touches && e.touches.length > 0) {
            this._dtTouchStartX = e.touches[0].clientX;
            this._dtTouchStartY = e.touches[0].clientY;
        }
    },

    _dtTouchEnd(e) {
        if (this._dtTouchStartX === null) return;
        var endX = e.changedTouches && e.changedTouches.length > 0
            ? e.changedTouches[0].clientX
            : null;
        var endY = e.changedTouches && e.changedTouches.length > 0
            ? e.changedTouches[0].clientY
            : null;
        if (endX === null || endY === null) {
            this._dtTouchStartX = null;
            this._dtTouchStartY = null;
            return;
        }
        // 攔截短路串（比照 handleKeydown detail 路徑前置條件，僅 3 條）
        if (this.rescrapeOpen) {          // 比照 navigation.js handleKeydown rescrape gate
            this._dtTouchStartX = null; this._dtTouchStartY = null; return;
        }
        if (this.sampleGalleryOpen) {     // 劇照由 _sgTouchEnd 處理（sibling 容器）
            this._dtTouchStartX = null; this._dtTouchStartY = null; return;
        }
        if (this.displayMode !== 'detail') {  // 比照 handleKeydown detail gate
            this._dtTouchStartX = null; this._dtTouchStartY = null; return;
        }
        var dir = detectSwipe(this._dtTouchStartX, this._dtTouchStartY, endX, endY, 50);
        this._dtTouchStartX = null;
        this._dtTouchStartY = null;
        // CD-3 直呼 navigate（CD-4 方向；無女優分流、無 wrap，邊界由 navigate 內部處理）
        if (dir === 'left') {             // 左滑 → 下一
            this.navigate(1);             // async，fire-and-forget，不 await
        } else if (dir === 'right') {     // 右滑 → 上一
            this.navigate(-1);
        }
    },

    // ==================== End Detail Cover Swipe ====================

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

        // rescrape 彈窗開啟時鎖所有快捷鍵（番號 input 可編輯，箭頭鍵須留給游標；
        // Escape 由 _rescrape_modal 的 @keydown.escape.window 自理，不在此重複關閉）
        if (this.rescrapeOpen) return;

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
    },

    /**
     * 滑鼠橫向滾輪導航（TASK-102d-T1，接線 ①②③）。
     * 單一進入點（`@wheel` 掛在 `.search-container` 根節點，非 passive），內部逐條 if
     * 分流——guard chain 優先序逐條比照 `handleKeydown`（rescrapeOpen → sampleGalleryOpen →
     * lightboxOpen → displayMode），不得拆成多層各自綁定（Opus 審核註記 #2）。
     * @param {WheelEvent} event
     */
    handleWheel(event) {
        // Opus 審核註記 #1：非 passive 監聽器每個 tick 都同步等 handler 跑完，
        // 第一行必須是純數值方向判斷，DOM 走訪（closest）排在其後。
        // 102d P2b（owner 拍板 2026-07-19）：軸向化——horizontal/vertical 互斥判斷，
        // |dx|===|dy|（含 0,0）兩者皆 false，視為無方向意圖，不處理。
        const horizontal = isHorizontalWheel(event.deltaX, event.deltaY);
        const vertical = !horizontal && isVerticalWheel(event.deltaX, event.deltaY);
        if (!horizontal && !vertical) return;

        // overlay 判斷（純布林讀取，無 DOM 走訪，維持 Opus #1 效能要求）：只有
        // sample gallery / lightbox 這兩種「垂直捲動無意義的全螢幕 overlay」吃垂直滾輪。
        // Search detail 頁垂直捲動＝捲頁面（spec 明文絕對不碰）——非 overlay 狀態下垂直
        // 滾輪在此零成本早退，不觸發 closest()/feed()，效能特性與 102d-T1 原版一致。
        const isOverlay = this.sampleGalleryOpen || this.lightboxOpen;
        if (vertical && !isOverlay) return;

        // 排除清單容器：原生橫向捲動優先，不吃導航。
        if (event.target.closest(WHEEL_EXCLUDE_SELECTOR)) return;
        // overlay 內可垂直捲動的子容器（metadata 面板）：垂直滾輪交還原生捲動。
        if (vertical && event.target.closest(WHEEL_VERTICAL_EXCLUDE_SELECTOR)) return;

        // rescrape 彈窗開啟時鎖所有快捷輸入（比照 handleKeydown）
        if (this.rescrapeOpen) return;

        // 水平方向映射（owner 拍板，Opus 審核修正）：滾輪是「方向指令」隱喻（同 ArrowLeft/
        // ArrowRight/scrollbar），不是觸控 detectSwipe 的「拖內容」隱喻——刻意與
        // detectSwipe 的 dX<0→'left'→next 相反。往右撥（deltaX>0，util 回呼 onRight）
        // 對應 ArrowRight 路徑（next）；往左撥（deltaX<0，onLeft）對應 ArrowLeft 路徑（prev）。
        // 不要「統一」回 swipe 那套映射。
        // 垂直方向映射（102d P2b，owner 拍板 2026-07-19）：圖片瀏覽器慣例——滾下
        // （deltaY>0，onDown）＝下一張；滾上（deltaY<0，onUp）＝上一張。

        // ② Search 劇照（最高優先：gallery 疊在 lightbox 之上）
        if (this.sampleGalleryOpen) {
            if (horizontal) {
                const triggered = wheelNavSampleGallery.feed(event, {
                    onLeft: () => this.prevSampleGallery(),
                    onRight: () => this.nextSampleGallery(),
                });
                if (triggered) event.preventDefault();
            } else {
                // Codex P2（102d 三審）：overlay 垂直分支一律 preventDefault，未達門檻的
                // sub-threshold tick 也吞——search lightbox/sample gallery 沒有 body-lock，
                // 漏一 tick 給底層頁面就會被 Firefox LINE-mode delta（3 行正規化 72px<80
                // 門檻）捲走，overlay 關閉後頁面位置已改變。水平分支刻意不比照（見下方
                // wheelNavSampleGallery/wheelNavLightbox 分支，未觸發不擋)。
                wheelNavSampleGalleryV.feed(event, {
                    onUp: () => this.prevSampleGallery(),
                    onDown: () => this.nextSampleGallery(),
                });
                event.preventDefault();
            }
            return;
        }

        // ③ Search Lightbox（sampleGalleryOpen 已排除後處理）
        if (this.lightboxOpen) {
            if (horizontal) {
                const triggered = wheelNavLightbox.feed(event, {
                    onLeft: () => this.prevLightboxVideo(),
                    onRight: () => this.nextLightboxVideo(),
                });
                if (triggered) event.preventDefault();
            } else {
                // Codex P2：同上，overlay 垂直分支一律 preventDefault（見 sample gallery
                // 垂直分支註解）。
                wheelNavLightboxV.feed(event, {
                    onUp: () => this.prevLightboxVideo(),
                    onDown: () => this.nextLightboxVideo(),
                });
                event.preventDefault();
            }
            return;
        }

        // ① Detail 模式導航（Grid 模式不觸發，比照 handleKeydown）。vertical 已在頂端
        // isOverlay 早退排除（此處恆為 horizontal，`if (!horizontal) return;` 僅作結構性
        // 防呆，非預期執行路徑）。
        if (!horizontal) return;
        if (this.displayMode !== 'detail') return;

        const triggered = wheelNavDetail.feed(event, {
            onLeft: () => this.navigate(-1),
            onRight: () => this.navigate(1),
        });
        if (triggered) event.preventDefault();
    }
    };
}
