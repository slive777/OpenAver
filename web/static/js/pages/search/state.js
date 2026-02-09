/**
 * SearchPage - Alpine.js Component Factory
 *
 * 全站最後一個 Alpine 遷移：Search 頁面狀態容器
 *
 * 設計原則：
 * - T1a 階段只建立骨架，不遷移邏輯（保持現有功能可用）
 * - Bridge Layer：Alpine state ↔ 舊 window.SearchCore namespace
 * - 逐步在 T1b-T1d 遷移各模組功能
 */
function searchPage() {
    return {
        // ===== Page State =====
        pageState: 'empty',  // 'empty' | 'loading' | 'result' | 'error'

        // ===== Search Results State =====
        searchResults: [],
        currentIndex: 0,
        currentQuery: '',
        currentOffset: 0,
        hasMoreResults: false,
        isLoadingMore: false,
        isSearchingFile: false,

        // ===== File List State =====
        fileList: [],
        currentFileIndex: 0,
        listMode: null,  // 'file' | 'search' | null

        // ===== Batch State =====
        batchState: {
            batchSize: 20,
            isProcessing: false,
            isPaused: false,
            total: 0,
            processed: 0,
            success: 0,
            failed: 0
        },

        // ===== App Config =====
        appConfig: null,

        // ===== Translation State =====
        isTranslating: false,

        // ===== Progress State =====
        currentMode: '',
        progressLog: '搜尋中...',
        detailDone: 0,
        detailTotal: 0,

        // ===== Constants =====
        PAGE_SIZE: 20,
        MODE_TEXT: {
            'exact': '完整番號搜尋',
            'partial': '部分番號搜尋',
            'prefix': '系列搜尋',
            'actress': '模糊搜尋',
            'keyword': '全文搜尋',
            'uncensored': '無碼搜尋'
        },
        STATE_KEY: 'javhelper_search_state',

        // ===== Computed Properties =====
        // 修正 2: hasContent 改為 plain data property（由 updateClearButton() 同步）
        hasContent: false,

        // ===== Lifecycle =====
        async init() {
            // 1. 初始化舊 JS 的 DOM references（必須在 DOM ready 後）
            if (window.SearchCore?.initDOM) {
                window.SearchCore.initDOM();
            }

            // 2. 載入應用設定
            await this.loadAppConfig();

            // 3. 載入來源配置（供版本切換用）
            if (window.SearchUI?.loadSourceConfig) {
                await window.SearchUI.loadSourceConfig();
            }

            // 4. 還原 sessionStorage 狀態
            this.restoreState();

            // 5. 建立 Bridge Layer：舊 JS 可透過 window.SearchCore.state 讀寫 Alpine state
            this.setupBridgeLayer();

            // 6. Watch state 變化並自動儲存
            this.setupAutoSave();

            // 7. 監聽離開前儲存
            window.addEventListener('beforeunload', () => this.saveState());
        },

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

                // 同步回 core.js module-level vars（舊 JS 函數直接讀取這些變數）
                const coreState = window.SearchCore.state;
                coreState.searchResults = this.searchResults;
                coreState.currentIndex = this.currentIndex;
                coreState.currentQuery = this.currentQuery;
                coreState.currentOffset = this.currentOffset;
                coreState.hasMoreResults = this.hasMoreResults;
                coreState.fileList = this.fileList;
                coreState.currentFileIndex = this.currentFileIndex;
                coreState.listMode = this.listMode;

                // 還原搜尋框輸入值
                const queryInput = document.getElementById('searchQuery');
                if (queryInput && state.queryValue) {
                    queryInput.value = state.queryValue;
                }

                // 還原顯示狀態（透過舊 JS 的 showState 同時處理 .hidden + Alpine pageState）
                if (this.searchResults.length > 0) {
                    if (window.SearchUI?.displayResult) {
                        window.SearchUI.displayResult(this.searchResults[this.currentIndex]);
                    }
                    if (window.SearchUI?.updateNavigation) {
                        window.SearchUI.updateNavigation();
                    }
                    window.SearchUI.showState('result');

                    if (this.listMode === 'search' && window.SearchFile?.renderSearchResultsList) {
                        window.SearchFile.renderSearchResultsList();
                    } else if (this.listMode === 'file' && window.SearchFile?.renderFileList) {
                        window.SearchFile.renderFileList();
                    }
                } else if (this.fileList.length > 0 && this.listMode === 'file') {
                    const currentFile = this.fileList[this.currentFileIndex];
                    if (currentFile?.searchResults?.length > 0) {
                        this.searchResults = currentFile.searchResults;
                        this.hasMoreResults = currentFile.hasMoreResults || false;
                        coreState.searchResults = this.searchResults;
                        coreState.hasMoreResults = this.hasMoreResults;
                        if (window.SearchUI?.displayResult) {
                            window.SearchUI.displayResult(this.searchResults[this.currentIndex]);
                        }
                        if (window.SearchUI?.updateNavigation) {
                            window.SearchUI.updateNavigation();
                        }
                        window.SearchUI.showState('result');
                    }
                    if (window.SearchFile?.renderFileList) {
                        window.SearchFile.renderFileList();
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
                queryValue: queryInput ? queryInput.value : ''
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
        },

        // ===== Bridge Layer =====
        // 修正 2: 簡化 Bridge Layer（不覆寫 window.SearchCore.state）
        setupBridgeLayer() {
            // T1a: 最小化 bridge — 只接管 saveState/clearState
            // pageState 由 showState() 同步（見 ui.js 修改）
            // hasContent 由 updateClearButton() 同步（見 core.js 修改）

            if (window.SearchCore) {
                // 接管 saveState / clearState，讓 Alpine 的 $watch auto-save 可運作
                window.SearchCore.saveState = () => this.saveState();
                window.SearchCore.clearState = () => this.clearState();
            }
        },

        // ===== Methods (Placeholder for T1b-T1d) =====
        async loadAppConfig() {
            // 呼叫舊 JS 的 loadAppConfig（T1a 階段不重寫）
            if (window.SearchCore?.loadAppConfig) {
                await window.SearchCore.loadAppConfig();
                // 同步到 Alpine state
                const coreState = window.SearchCore.state;
                if (coreState) {
                    this.appConfig = coreState.appConfig;
                }
            }
        },

        clearAll() {
            // 呼叫舊 JS 的 clearAll（T1a 階段不重寫）
            if (window.SearchCore?.clearAll) {
                window.SearchCore.clearAll();
            }
            // 同步 Alpine state
            this.searchResults = [];
            this.currentIndex = 0;
            this.currentQuery = '';
            this.currentOffset = 0;
            this.hasMoreResults = false;
            this.fileList = [];
            this.currentFileIndex = 0;
            this.listMode = null;
            this.pageState = 'empty';
            this.hasContent = false;
        }

        // T1b will add: doSearch(), navigate(), handleKeydown()
        // T1c will add: displayResult(), editTitle()
        // T1d will add: renderFileList(), searchAll(), scrapeAll()
    };
}
