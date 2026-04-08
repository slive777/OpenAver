/**
 * SearchState - Persistence Mixin
 * 包含：狀態持久化（restoreState, saveState, clearState, setupAutoSave）
 */
window.SearchStateMixin_Persistence = {
    // ===== State Persistence =====
    restoreState() {
        const saved = sessionStorage.getItem(this.STATE_KEY);
        if (!saved) return;

        try {
            const state = JSON.parse(saved);
            this.searchResults = state.searchResults || [];
            this.currentIndex = state.currentIndex || 0;
            this.currentQuery = state.currentQuery || '';
            this.currentOffset = state.currentOffset || 0;
            this.hasMoreResults = state.hasMoreResults || false;
            this.fileList = state.fileList || [];
            this.currentFileIndex = state.currentFileIndex || 0;
            this.listMode = state.listMode || null;
            this.displayMode = state.displayMode || 'detail';
            this.currentMode = state.currentMode || '';  // T3 fix: 還原搜尋模式
            this.actressProfile = state.actressProfile || null;  // T5: 恢復女優資料

            // gallery_mode_enabled=false → 強制 detail mode
            if (this.appConfig?.search?.gallery_mode_enabled === false) {
                this.displayMode = 'detail';
            }

            // 還原搜尋框輸入值
            if (state.queryValue) {
                this.searchQuery = state.queryValue;
            }

            // U8b: 清除封面狀態（防止還原時殘留舊狀態）
            this._resetCoverState();
            // A6-1: 還原時清除舊 hero image error state
            this._heroCardImageError = false;
            this._heroLightboxImageError = false;

            // 還原顯示狀態（透過舊 JS 的 showState 同時處理 .hidden + Alpine pageState）
            var hasResult = false;
            if (this.searchResults.length > 0) {
                this.pageState = 'result';
                hasResult = true;
            } else if (this.fileList.length > 0 && this.listMode === 'file') {
                const currentFile = this.fileList[this.currentFileIndex];
                if (currentFile?.searchResults?.length > 0) {
                    this.searchResults = currentFile.searchResults;
                    this.hasMoreResults = currentFile.hasMoreResults || false;
                    this.pageState = 'result';
                    hasResult = true;
                }
            }

            // 同步 clear button（直接計算 hasContent）
            this.hasContent = this.searchResults.length > 0 || this.fileList.length > 0;

            // A6-2: Lightbox 狀態正規化 — 還原後 lightbox 不應開著
            this.lightboxOpen = false;
            if (this.actressProfile) {
                this.lightboxIndex = -1;
            }

            // F4: grid 模式返回時觸發 settle 動畫（C17 時序：$nextTick + rAF）
            if (hasResult && this.displayMode === 'grid') {
                this.$nextTick(function () {
                    requestAnimationFrame(function () {
                        var grid = document.querySelector('.search-grid');
                        window.SearchAnimations?.playGridSettle?.(grid);
                    });
                });
            }


        } catch (e) {
            console.error('[Alpine] 還原狀態失敗:', e);
            sessionStorage.removeItem(this.STATE_KEY);
        }
    },

    saveState() {
        // 搜尋進行中：用 _searchSnapshot 保存（上一輪完整一致狀態）
        // 條件：snapshot 存在 + pageState 仍是 loading（覆蓋 SSE 和 REST fallback 兩條路徑）
        if (this._searchSnapshot && this.pageState === 'loading') {
            const snap = this._searchSnapshot;
            const state = {
                searchResults: snap.searchResults,
                currentIndex: snap.currentIndex,
                currentQuery: snap.currentQuery,
                currentOffset: snap.currentOffset,
                hasMoreResults: snap.hasMoreResults,
                fileList: snap.fileList,
                currentFileIndex: snap.currentFileIndex,
                listMode: snap.listMode,
                queryValue: snap.currentQuery,    // 上一輪的 query
                displayMode: snap.displayMode,
                currentMode: snap.currentMode,
                actressProfile: snap.actressProfile
            };
            sessionStorage.setItem(this.STATE_KEY, JSON.stringify(state));
            return;
        }

        // T3.2 Step 3: SearchCore.state 已代理 Alpine，直接用 Alpine state
        const state = {
            searchResults: this.searchResults,
            currentIndex: this.currentIndex,
            currentQuery: this.currentQuery,
            currentOffset: this.currentOffset,
            hasMoreResults: this.hasMoreResults,
            fileList: this.fileList,
            currentFileIndex: this.currentFileIndex,
            listMode: this.listMode,
            queryValue: this.searchQuery,
            displayMode: this.displayMode,
            currentMode: this.currentMode,  // T3 fix: 持久化搜尋模式
            actressProfile: this.actressProfile  // T5: 持久化女優資料
        };
        sessionStorage.setItem(this.STATE_KEY, JSON.stringify(state));
    },

    clearState() {
        sessionStorage.removeItem(this.STATE_KEY);
    },

    setupAutoSave() {
        // Watch 主要狀態變化並自動儲存（debounce 100ms）
        // T4.2: 改用 _setTimer 取代 local debounce variable，支援離頁統一清除
        const debouncedSave = () => {
            this._setTimer('autosave', () => this.saveState(), 100);
        };

        this.$watch('searchResults', debouncedSave);
        this.$watch('currentIndex', debouncedSave);
        this.$watch('fileList', debouncedSave);
        this.$watch('listMode', debouncedSave);
    }
};
