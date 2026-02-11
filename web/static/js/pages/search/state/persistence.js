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
            this._syncToCore();

            // 還原搜尋框輸入值
            const queryInput = document.getElementById('searchQuery');
            if (queryInput && state.queryValue) {
                queryInput.value = state.queryValue;
            }

            // Fix 1: 清除封面錯誤（防止還原時殘留舊狀態）
            this.coverError = '';
            this._coverRetried = false;

            // 還原顯示狀態（透過舊 JS 的 showState 同時處理 .hidden + Alpine pageState）
            if (this.searchResults.length > 0) {
                window.SearchUI.showState('result');
            } else if (this.fileList.length > 0 && this.listMode === 'file') {
                const currentFile = this.fileList[this.currentFileIndex];
                if (currentFile?.searchResults?.length > 0) {
                    this.searchResults = currentFile.searchResults;
                    this.hasMoreResults = currentFile.hasMoreResults || false;
                    this._syncToCore();
                    window.SearchUI.showState('result');
                }
            }

            // 同步 clear button（.hidden toggling + Alpine hasContent）
            window.SearchCore.updateClearButton();

            console.log('[Alpine] State restored from sessionStorage');
        } catch (e) {
            console.error('[Alpine] 還原狀態失敗:', e);
            sessionStorage.removeItem(this.STATE_KEY);
        }
    },

    saveState() {
        // T1a: 從 core.js module vars 讀取（它們是 source of truth）
        // Alpine state 可能是 stale（core.js 函數直接改 module vars，不經過 Alpine）
        const coreState = window.SearchCore?.state;
        const queryInput = document.getElementById('searchQuery');
        const state = {
            searchResults: coreState?.searchResults ?? this.searchResults,
            currentIndex: coreState?.currentIndex ?? this.currentIndex,
            currentQuery: coreState?.currentQuery ?? this.currentQuery,
            currentOffset: coreState?.currentOffset ?? this.currentOffset,
            hasMoreResults: coreState?.hasMoreResults ?? this.hasMoreResults,
            fileList: coreState?.fileList ?? this.fileList,
            currentFileIndex: coreState?.currentFileIndex ?? this.currentFileIndex,
            listMode: coreState?.listMode ?? this.listMode,
            queryValue: queryInput ? queryInput.value : '',
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
        let saveTimeout;
        const debouncedSave = () => {
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(() => this.saveState(), 100);
        };

        this.$watch('searchResults', debouncedSave);
        this.$watch('currentIndex', debouncedSave);
        this.$watch('fileList', debouncedSave);
        this.$watch('listMode', debouncedSave);
    }
};
