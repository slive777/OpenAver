/**
 * SearchState - Base Mixin
 * 包含：data 初始值、constants、computed methods、file list helpers
 */
window.SearchStateMixin_Base = function() {
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

        // ===== T1c: Edit State =====
        editingTitle: false,
        editedTitleValue: '',
        editingChineseTitle: false,
        editedChineseTitleValue: '',
        addingTag: false,
        newTagValue: '',
        coverError: '',
        _coverRetried: false,

        // ===== T6b: Toast State =====
        _toast: {
            message: '',
            type: 'success',  // 'success' | 'error' | 'warning' | 'info'
            visible: false
        },
        _toastTimer: null,  // setTimeout ID for auto-hide

        // ===== T1d: File List State =====
        dragActive: false,
        isLoadingFavorite: false,
        searchingFileDirection: null,  // 'next' | 'prev' — for searchForFile btn spinner
        isScrapeAllProcessing: false,  // scrapeAll spinner

        // ===== Progress State =====
        currentMode: '',
        progressLog: '搜尋中...',
        detailDone: 0,
        detailTotal: 0,

        // ===== Search State Machine =====
        requestId: 0,              // 搜尋請求計數器（防競態）
        activeEventSource: null,   // 當前 SSE 連線
        _searchSnapshot: null,     // cancelSearch 用的狀態快照

        // ===== T2a: Display Mode State =====
        displayMode: 'detail',     // 'detail' | 'grid'
        lightboxOpen: false,       // Lightbox 顯示狀態
        lightboxIndex: 0,          // Lightbox 當前索引
        actressLightboxMode: false, // Actress photo lightbox mode

        // ===== T2d: Actress Profile State =====
        actressProfile: null,      // { name, img, backdrop, birth, age, height, cup, bust, waist, hip, hometown, hobby }

        // ===== T4: Rotating Border State =====
        // T4: 追蹤已播放 rotating border 的番號（避免 Alpine `:class` 重複觸發動畫）
        _localBorderPlayed: {},

        // ===== T6a: Grid Image Error State =====
        // Grid 模式圖片錯誤追蹤
        _gridImageErrors: new Set(),

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
        SOURCE_NAME: {
            'javbus': 'JavBus',
            'jav321': 'Jav321',
            'javdb': 'JavDB',
            'fc2': 'FC2',
            'avsox': 'AVSOX'
        },
        STATE_KEY: 'javhelper_search_state',

        // ===== Computed Properties =====
        // 修正 2: hasContent 改為 plain data property（由 updateClearButton() 同步）
        hasContent: false,

        canGoPrev() {
            return this.currentIndex > 0 || this.currentFileIndex > 0;
        },

        canGoNext() {
            return this.currentIndex < this.searchResults.length - 1 ||
                   this.hasMoreResults ||
                   this.currentFileIndex < this.fileList.length - 1;
        },

        showNavigation() {
            const hasMultipleResults = this.searchResults.length > 1 || this.hasMoreResults;
            const hasMultipleFiles = this.fileList.length > 1;
            return hasMultipleResults || hasMultipleFiles;
        },

        navIndicatorText() {
            if (this.fileList.length > 1) {
                return `${this.currentFileIndex + 1}/${this.fileList.length}`;
            } else {
                const total = this.hasMoreResults
                    ? this.searchResults.length + '+'
                    : this.searchResults.length;
                return `${this.currentIndex + 1}/${total}`;
            }
        },

        detailProgressPercent() {
            if (this.detailTotal === 0) return 0;
            return Math.round((this.detailDone / this.detailTotal) * 100);
        },

        // ===== T1d: File List Computed =====

        fileCountText() {
            if (this.listMode === 'file') {
                return `檔案 ${this.currentFileIndex + 1}/${this.fileList.length}`;
            } else {
                const total = this.hasMoreResults
                    ? this.searchResults.length + '+'
                    : this.searchResults.length;
                return `搜尋結果 (${total})`;
            }
        },

        searchAllButtonText() {
            const searchableFiles = this.fileList.filter(f => f.number && !f.searched);
            const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0));
            const totalWithNumber = this.fileList.filter(f => f.number).length;
            const batch = this.batchState;

            if (searchableFiles.length === 0 && failedFiles.length === 0) {
                return '搜尋全部';
            }
            if (batch.isProcessing) {
                return batch.isPaused ? '繼續' : '暫停';
            }
            if (searchableFiles.length === 0 && failedFiles.length > 0) {
                return `重試失敗 (${failedFiles.length})`;
            }
            const searchedCount = totalWithNumber - searchableFiles.length;
            const start = searchedCount + 1;
            const end = Math.min(searchedCount + batch.batchSize, totalWithNumber);
            return `搜尋 ${start}-${end} / ${totalWithNumber}`;
        },

        searchAllButtonIcon() {
            const batch = this.batchState;
            if (batch.isProcessing) {
                return batch.isPaused ? 'bi-play-fill' : 'bi-pause-fill';
            }
            const searchableFiles = this.fileList.filter(f => f.number && !f.searched);
            const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0));
            if (searchableFiles.length === 0 && failedFiles.length > 0) {
                return 'bi-arrow-clockwise';
            }
            return 'bi-search';
        },

        searchAllDisabled() {
            const searchableFiles = this.fileList.filter(f => f.number && !f.searched);
            const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0));
            return searchableFiles.length === 0 && failedFiles.length === 0 && !this.batchState.isProcessing;
        },

        batchPercent() {
            const batch = this.batchState;
            if (batch.total === 0) return 0;
            return Math.round((batch.processed / batch.total) * 100);
        },

        // ===== T1d: File List Helper Methods =====

        fileStatusIcon(file) {
            if (!file.number) return '?';
            if (file.searched) {
                return (file.searchResults && file.searchResults.length > 0) ? '✓' : '✗';
            }
            return '';
        },

        fileStatusClass(file) {
            let cls = 'file-status';
            if (!file.number) cls += ' text-warning';
            else if (file.searched && (!file.searchResults || file.searchResults.length === 0)) {
                cls += ' text-error';
            }
            return cls;
        },

        canScrapeFile(file) {
            return file.searched && file.searchResults && file.searchResults.length > 0 && !file.scraped;
        },

        needsNumberInput(file) {
            return !file.number;
        },

        // ===== T4: Rotating Border Methods =====

        // T4: 檢查是否應顯示本地匹配外框（尚未播放動畫 + 本地存在）
        shouldShowLocalBorder(result) {
            return result?._localStatus?.exists && !this._localBorderPlayed[result?.number];
        },

        // T4: 標記番號已播放動畫
        markLocalBorderPlayed(number) {
            if (number) this._localBorderPlayed[number] = true;
        }
    };
};
