/**
 * SearchState - Base Mixin
 * 包含：data 初始值、constants、computed methods、file list helpers
 */
window.SearchStateMixin_Base = function () {
    return {
        // ===== Page State =====
        pageState: 'empty',  // 'empty' | 'loading' | 'result' | 'error'

        // ===== Search Results State =====
        searchResults: [],
        currentIndex: 0,
        currentQuery: '',
        searchQuery: '',  // V1c: 對應 input 即時輸入值（x-model 綁定）
        currentOffset: 0,
        hasMoreResults: false,
        isLoadingMore: false,
        isSearchingFile: false,

        // ===== Stream 狀態（T4：actress/prefix 漸進流入） =====
        streamSlots: [],          // seed 番號列表 ['SSIS-816', 'SSIS-815', ...]
        streamComplete: false,    // result-complete 已收到
        isStreaming: false,       // seed 收到 ~ result-complete 收到期間為 true

        // ===== U2: Staging Buffer State（batching 用） =====
        streamBuffer: [],        // 待 burst 的 result-item 暫存（{slot, data}[]）
        streamBurstTimer: null,  // 時間窗口 timer ID（原生 setTimeout 回傳值）
        streamBurstedSlots: [],  // 已 burst 到 grid 的 slot index（boolean array，長度與 streamSlots 一致）
        stagingVisible: false,   // staging 容器可見性（獨立於 isStreaming）
        // isStreaming 在 result-complete 後立即 false，
        // 但 stagingVisible 等 exit morph onComplete 才 false

        // ===== U3: Staging Card 顯示 State（裝飾性，C16） =====
        stagingCover: '',           // staging card 封面 URL（最新到達的 result-item）
        stagingNumber: '',          // staging card 番號（最新到達的 result-item）
        stagingReceivedCount: 0,    // staging card 已收到計數（badge 用）
        _coverSwapTimer: null,      // cover swap debounce timer ID（C20 約束）
        _stagingCardWidth: 0,       // seed 時預量的 grid card 寬度（staging 首次顯示同步用）

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

        // ===== Translate State =====
        translateState: {
            isProcessing: false,
            isPaused: false,
            total: 0,
            processed: 0,
            success: 0,
            failed: 0,
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
        _coverRequestId: 0,
        _coverLoaded: false,
        // ===== Fix-1: Duplicate State =====
        duplicateTarget: '',  // duplicate modal 顯示的目標檔名
        duplicateModalOpen: false,  // Alpine state for duplicate modal
        errorText: '',  // T6c: Error message state

        // ===== T6b: Toast State =====
        _toast: {
            message: '',
            type: 'success',  // 'success' | 'error' | 'warning' | 'info'
            visible: false
        },
        _timers: {},  // Timer registry：{ [key: string]: number }（setTimeout ID）
        _abortControllers: {},  // Fetch AbortController registry：{ [key: string]: AbortController }（T4.3）

        // ===== T1d: File List State =====
        dragActive: false,
        isLoadingFavorite: false,
        searchingFileDirection: null,  // 'next' | 'prev' — for searchForFile btn spinner
        isScrapeAllProcessing: false,  // scrapeAll spinner

        // ===== V1d: Source Switching State =====
        isSwitchingSource: false,      // 切換來源中（控制 spinner + disabled）
        switchSourceShake: false,      // 觸發抖動動畫（無其他版本時）

        // ===== Progress State =====
        currentMode: '',
        progressLog: '搜尋中...',
        detailDone: 0,
        detailTotal: 0,

        // ===== Search State Machine =====
        requestId: 0,              // 搜尋請求計數器（防競態）
        activeEventSource: null,   // 當前 SSE 連線
        _activeConnections: [],    // Array<EventSource> — 追蹤所有進行中的 SSE 連線
        _searchSnapshot: null,     // cancelSearch 用的狀態快照

        // ===== T2a: Display Mode State =====
        displayMode: 'detail',     // 'detail' | 'grid'
        lightboxOpen: false,       // Lightbox 顯示狀態
        lightboxIndex: 0,          // Lightbox 當前索引（-1 = 女優頭像）

        // ===== T2d: Actress Profile State =====
        actressProfile: null,      // { name, img, backdrop, birth, age, height, cup, bust, waist, hip, hometown, hobby }

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

        actressLightboxMode() {
            return this.lightboxIndex === -1;
        },

        canGoPrev() {
            if (this.listMode === 'file') {
                // 同層級：前方有非 _failed item
                const hasPrevVisible = this.searchResults.slice(0, this.currentIndex).some(r => !r._failed);
                // 跨檔案：可退到上一個檔案
                return hasPrevVisible || this.currentFileIndex > 0;
            }
            return this.searchResults.slice(0, this.currentIndex).some(r => !r._failed);
        },

        canGoNext() {
            if (this.listMode === 'file') {
                const hasNextVisible = this.searchResults.slice(this.currentIndex + 1).some(r => !r._failed);
                return hasNextVisible || this.hasMoreResults || this.currentFileIndex < this.fileList.length - 1;
            }
            return this.searchResults.slice(this.currentIndex + 1).some(r => !r._failed) || this.hasMoreResults;
        },

        hasVisiblePrev() {
            if (this.lightboxIndex === -1) return false;  // 已在 actress photo 最左
            if (this.lightboxIndex === 0) return !!this.actressProfile;  // 可跳到 actress
            // lightboxIndex > 0：前方有非 _failed item 或有 actressProfile
            const hasPrevVisible = this.searchResults.slice(0, this.lightboxIndex).some(r => !r._failed);
            return hasPrevVisible || !!this.actressProfile;
        },

        hasVisibleNext() {
            if (this.lightboxIndex === -1) {
                // 從 actress photo 看有沒有可見 item
                return this.searchResults.some(r => !r._failed);
            }
            return this.searchResults.slice(this.lightboxIndex + 1).some(r => !r._failed);
        },

        showNavigation() {
            const visibleCount = this.searchResults.filter(r => !r._failed).length;
            const hasMultipleResults = visibleCount > 1 || this.hasMoreResults;
            const hasMultipleFiles = this.fileList.length > 1;
            return hasMultipleResults || hasMultipleFiles;
        },

        navIndicatorText() {
            if (this.fileList.length > 1) {
                // file 模式：維持原邏輯
                return `${this.currentFileIndex + 1}/${this.fileList.length}`;
            }
            // search 模式：排除 _failed
            const visibleItems = this.searchResults.filter(r => !r._failed);
            // position: 在 visibleItems 中，原始 index <= currentIndex 的數量
            const position = this.searchResults.slice(0, this.currentIndex + 1).filter(r => !r._failed).length;
            const total = this.hasMoreResults ? visibleItems.length + '+' : visibleItems.length;
            return `${position}/${total}`;
        },

        detailProgressPercent() {
            if (this.detailTotal === 0) return 0;
            return Math.round((this.detailDone / this.detailTotal) * 100);
        },

        // ===== T1d: File List Computed =====

        fileCountText() {
            if (this.listMode === 'file') {
                return `檔案 ${this.currentFileIndex + 1}/${this.fileList.length}`;
            }
            const visibleCount = this.searchResults.filter(r => !r._failed).length;
            const total = this.hasMoreResults ? visibleCount + '+' : visibleCount;
            return `搜尋結果 (${total})`;
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

        get isCloudSearchMode() {
            return this.listMode === 'search' && this.searchResults.length > 0;
        },

        translateAllButtonText() {
            const ts = this.translateState;
            if (ts.isProcessing) {
                return ts.isPaused ? '繼續' : `翻譯中 ${ts.processed}/${ts.total}`;
            }
            const count = this.searchResults.filter(r => r.title && window.SearchCore?.hasJapanese(r.title) && !r.translated_title).length;
            return `翻譯全部 (${count})`;
        },

        translateAllButtonIcon() {
            const ts = this.translateState;
            if (ts.isProcessing) {
                return ts.isPaused ? 'bi-play-fill' : 'bi-pause-fill';
            }
            return 'bi-translate';
        },

        translateAllDisabled() {
            const ts = this.translateState;
            if (ts.isProcessing) return false;
            if (!this.appConfig?.translate?.enabled) return true;
            const count = this.searchResults.filter(r => r.title && window.SearchCore?.hasJapanese(r.title) && !r.translated_title).length;
            return count === 0;
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

        // T4: 檢查是否應顯示本地匹配外框
        shouldShowLocalBorder(result) {
            return result?._localStatus?.exists;
        },

        closeDuplicateModal() {
            this.duplicateModalOpen = false;
            this.duplicateTarget = '';
        },

        // U8a: centralized cover state reset
        _resetCoverState() {
            this._coverRequestId++;
            this._coverRetried = false;
            this._coverLoaded = false;
            this.coverError = '';
            this._clearTimer('coverRetry');

            // 防禦：若圖片已在瀏覽器快取中（同 URL 不重觸 @load），
            // 下一 tick 檢查 complete 狀態，避免 shimmer 永遠遮蓋封面
            var requestId = this._coverRequestId;
            this.$nextTick(() => {
                if (this._coverRequestId !== requestId) return;  // 已被後續重置取代
                var img = this.$refs.coverImg;
                if (img && img.complete && img.naturalWidth > 0 && !this._coverLoaded) {
                    this._coverLoaded = true;
                }
            });
        },
    };
};
