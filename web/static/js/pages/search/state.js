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

        // ===== T1c: Edit State =====
        editingTitle: false,
        editedTitleValue: '',
        editingChineseTitle: false,
        editedChineseTitleValue: '',
        addingTag: false,
        newTagValue: '',
        coverError: '',

        // ===== Progress State =====
        currentMode: '',
        progressLog: '搜尋中...',
        detailDone: 0,
        detailTotal: 0,

        // ===== Search State Machine =====
        requestId: 0,              // 搜尋請求計數器（防競態）
        activeEventSource: null,   // 當前 SSE 連線
        _searchSnapshot: null,     // cancelSearch 用的狀態快照

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

            // T1b: 新增搜尋流程 bridge
            // 讓舊 JS 可以觸發 Alpine 搜尋
            if (window.SearchCore) {
                window.SearchCore.doSearch = (query) => this.doSearch(query);
            }
            if (window.SearchUI) {
                window.SearchUI.navigateResult = (delta) => this.navigate(delta);
            }

            // Fix 1: 新增 file.js 需要的進度函數 bridge
            if (window.SearchCore) {
                window.SearchCore.initProgress = (query) => {
                    this.progressLog = '搜尋中...';
                    this.currentMode = '';
                    this.detailDone = 0;
                    this.detailTotal = 0;
                    this.currentQuery = query;
                };
                window.SearchCore.updateLog = (msg) => {
                    this.progressLog = msg;
                };
                window.SearchCore.handleSearchStatus = (source, status) => {
                    this.handleSearchStatus(source, status);
                };
            }

            // T1c: 覆寫全域函數，指向 Alpine methods
            window.translateWithAI = () => this.translateWithAI();
            window.startEditTitle = () => this.startEditTitle();
            window.confirmEditTitle = () => this.confirmEditTitle();
            window.cancelEditTitle = () => this.cancelEditTitle();
            window.startEditChineseTitle = () => this.startEditChineseTitle();
            window.confirmEditChineseTitle = () => this.confirmEditChineseTitle();
            window.cancelEditChineseTitle = () => this.cancelEditChineseTitle();
            window.showAddTagInput = () => this.showAddTagInput();
            window.confirmAddTag = () => this.confirmAddTag();
            window.cancelAddTag = () => this.cancelAddTag();
            window.removeUserTag = (tag) => this.removeUserTag(tag);
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
        },

        // ===== T1b: Search Methods =====

        /**
         * 執行搜尋（SSE 串流）
         * @param {string} query - 搜尋關鍵字（可選，預設讀取 input）
         */
        async doSearch(query) {
            // 1. 取得搜尋關鍵字
            if (!query) {
                const input = document.getElementById('searchQuery');
                query = input?.value?.trim();
            }
            if (!query) return;

            // 2. 取消現有搜尋
            this.cancelSearch();

            // 3. 新搜尋請求
            this.requestId++;
            const currentRequestId = this.requestId;

            // 4. 關閉 Gallery（如果有）
            if (window.SearchUI?.hideGallery) {
                const galleryView = document.getElementById('galleryView');
                if (galleryView && !galleryView.classList.contains('hidden')) {
                    window.SearchUI.hideGallery(false);
                }
            }

            // Fix 2: 保存 snapshot（供 cancelSearch 還原）
            this._searchSnapshot = {
                searchResults: this.searchResults,
                currentIndex: this.currentIndex,
                fileList: this.fileList,
                currentFileIndex: this.currentFileIndex,
                listMode: this.listMode,
                hasMoreResults: this.hasMoreResults,
                currentQuery: this.currentQuery,
                currentOffset: this.currentOffset,
                pageState: this.pageState
            };

            // 5. 初始化狀態（修正 1: 使用 showState）
            window.SearchUI.showState('loading');
            this.progressLog = '搜尋中...';
            this.currentMode = '';
            this.detailDone = 0;
            this.detailTotal = 0;
            this.searchResults = [];
            this.currentIndex = 0;
            this.fileList = [];
            this.currentFileIndex = 0;
            this.listMode = null;
            this.currentQuery = query;
            this.currentOffset = 0;
            this.hasMoreResults = false;

            // 隱藏檔案列表
            const fileListSection = document.getElementById('fileListSection');
            if (fileListSection) {
                fileListSection.classList.add('hidden');
            }

            // 6. 建立 SSE 連線
            this.activeEventSource = new EventSource(`/api/search/stream?q=${encodeURIComponent(query)}`);
            const eventSource = this.activeEventSource;

            eventSource.onmessage = (event) => {
                // 檢查是否已被取消
                if (currentRequestId !== this.requestId) {
                    eventSource.close();
                    return;
                }

                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'mode') {
                        this.currentMode = data.mode;
                        this.progressLog = `${this.MODE_TEXT[data.mode] || data.mode}...`;
                    }
                    else if (data.type === 'status') {
                        this.handleSearchStatus(data.source, data.status);
                    }
                    else if (data.type === 'result') {
                        eventSource.close();
                        this.activeEventSource = null;

                        if (data.success && data.data && data.data.length > 0) {
                            // 修正 2: 更新 Alpine state
                            this.searchResults = data.data;
                            this.currentIndex = 0;
                            this.hasMoreResults = data.has_more || false;

                            // 同步回 core.js
                            const coreState = window.SearchCore.state;
                            coreState.searchResults = this.searchResults;
                            coreState.currentIndex = this.currentIndex;
                            coreState.hasMoreResults = this.hasMoreResults;
                            coreState.listMode = 'search';
                            coreState.currentQuery = this.currentQuery;
                            coreState.currentOffset = this.currentOffset;

                            // 查詢本地狀態（非同步）
                            if (window.SearchCore?.checkLocalStatus) {
                                window.SearchCore.checkLocalStatus(this.searchResults);
                            }

                            // 優先顯示 Gallery（如果有 gallery_url）
                            if (data.gallery_url && window.SearchUI?.showGallery) {
                                window.SearchUI.showGallery(data.gallery_url);
                                this.listMode = 'search';
                                if (window.SearchFile?.renderSearchResultsList) {
                                    window.SearchFile.renderSearchResultsList();
                                }
                                this.hasContent = true;
                                window.SearchCore.updateClearButton();
                                this.saveState();
                                this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                            } else {
                                // 原有的詳細資料卡顯示邏輯
                                window.SearchUI.showState('result');
                                if (window.SearchUI?.preloadImages) {
                                    window.SearchUI.preloadImages(1, 5);
                                }
                                this.listMode = 'search';
                                if (window.SearchFile?.renderSearchResultsList) {
                                    window.SearchFile.renderSearchResultsList();
                                }
                                this.hasContent = true;
                                window.SearchCore.updateClearButton();
                                this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                                // Reset edit states
                                this.coverError = '';
                                this.editingTitle = false;
                                this.editingChineseTitle = false;
                                this.addingTag = false;
                            }
                        } else {
                            this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋失敗）
                            window.SearchUI.showState('error');
                            const errorMsg = document.getElementById('errorMessage');
                            if (errorMsg) {
                                errorMsg.textContent = '找不到資料';
                            }
                        }
                    }
                    else if (data.type === 'error') {
                        eventSource.close();
                        this.activeEventSource = null;
                        this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋錯誤）
                        window.SearchUI.showState('error');
                        const errorMsg = document.getElementById('errorMessage');
                        if (errorMsg) {
                            errorMsg.textContent = data.message || '搜尋失敗';
                        }
                    }
                } catch (err) {
                    console.error('Parse error:', err);
                }
            };

            eventSource.onerror = () => {
                // 檢查是否已被取消
                if (currentRequestId !== this.requestId) {
                    eventSource.close();
                    return;
                }

                eventSource.close();
                this.activeEventSource = null;
                this.fallbackSearch(query, currentRequestId); // Fix 3: 傳入 requestId
            };
        },

        /**
         * 傳統 API 回退（SSE 失敗時）
         * @param {string} query - 搜尋關鍵字
         * @param {number} savedRequestId - 保存的請求 ID（防競態）
         */
        async fallbackSearch(query, savedRequestId) {
            // 關閉 Gallery（如果有）
            if (window.SearchUI?.hideGallery) {
                const galleryView = document.getElementById('galleryView');
                if (galleryView && !galleryView.classList.contains('hidden')) {
                    window.SearchUI.hideGallery(false);
                }
            }

            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                const data = await response.json();

                // Fix 3: 檢查是否已被新搜尋取代
                if (savedRequestId !== this.requestId) return;

                if (response.ok && data.success && data.data && data.data.length > 0) {
                    // 修正 2: 更新 Alpine state
                    this.searchResults = data.data;
                    this.currentIndex = 0;
                    this.hasMoreResults = data.has_more || false;

                    // 同步回 core.js
                    const coreState = window.SearchCore.state;
                    coreState.searchResults = this.searchResults;
                    coreState.currentIndex = this.currentIndex;
                    coreState.hasMoreResults = this.hasMoreResults;
                    coreState.listMode = 'search';
                    coreState.currentQuery = this.currentQuery;
                    coreState.currentOffset = this.currentOffset;

                    // 查詢本地狀態
                    if (window.SearchCore?.checkLocalStatus) {
                        window.SearchCore.checkLocalStatus(this.searchResults);
                    }

                    // 優先顯示 Gallery
                    if (data.gallery_url && window.SearchUI?.showGallery) {
                        window.SearchUI.showGallery(data.gallery_url);
                        this.listMode = 'search';
                        if (window.SearchFile?.renderSearchResultsList) {
                            window.SearchFile.renderSearchResultsList();
                        }
                        this.hasContent = true;
                        window.SearchCore.updateClearButton();
                        this.saveState();
                        this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                    } else {
                        window.SearchUI.showState('result');
                        if (window.SearchUI?.preloadImages) {
                            window.SearchUI.preloadImages(1, 5);
                        }
                        this.listMode = 'search';
                        if (window.SearchFile?.renderSearchResultsList) {
                            window.SearchFile.renderSearchResultsList();
                        }
                        this.hasContent = true;
                        window.SearchCore.updateClearButton();
                        this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                        // Reset edit states
                        this.coverError = '';
                        this.editingTitle = false;
                        this.editingChineseTitle = false;
                        this.addingTag = false;
                    }
                } else {
                    this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋失敗）
                    window.SearchUI.showState('error');
                    const errorMsg = document.getElementById('errorMessage');
                    if (errorMsg) {
                        errorMsg.textContent = data.error || '找不到資料';
                    }
                }
            } catch (err) {
                // Fix 3: 舊請求失敗不覆蓋新搜尋畫面
                if (savedRequestId !== this.requestId) return;
                this._searchSnapshot = null;
                window.SearchUI.showState('error');
                const errorMsg = document.getElementById('errorMessage');
                if (errorMsg) {
                    errorMsg.textContent = '網路錯誤: ' + err.message;
                }
            }
        },

        /**
         * 取消搜尋（Fix 2: 恢復到上一個有效狀態）
         */
        cancelSearch() {
            if (this.activeEventSource) {
                this.activeEventSource.close();
                this.activeEventSource = null;
            }
            this.requestId++;

            // 還原到搜尋前的狀態
            const snap = this._searchSnapshot;
            if (snap) {
                this.searchResults = snap.searchResults;
                this.currentIndex = snap.currentIndex;
                this.fileList = snap.fileList;
                this.currentFileIndex = snap.currentFileIndex;
                this.listMode = snap.listMode;
                this.hasMoreResults = snap.hasMoreResults;
                this.currentQuery = snap.currentQuery;
                this.currentOffset = snap.currentOffset;

                // 同步回 core.js
                const coreState = window.SearchCore.state;
                coreState.searchResults = this.searchResults;
                coreState.currentIndex = this.currentIndex;
                coreState.fileList = this.fileList;
                coreState.currentFileIndex = this.currentFileIndex;
                coreState.listMode = this.listMode;
                coreState.hasMoreResults = this.hasMoreResults;

                // 還原顯示
                window.SearchUI.showState(snap.pageState);
            } else {
                window.SearchUI.showState('empty');
            }
            this._searchSnapshot = null;
        },

        /**
         * 處理 SSE 狀態更新
         * @param {string} source - 來源（javbus/jav321）
         * @param {string} status - 狀態字串
         */
        handleSearchStatus(source, status) {
            if (source === 'mode') {
                this.currentMode = status;
                this.progressLog = `${this.MODE_TEXT[status] || status}...`;
                return;
            }

            if (source === 'javbus' || source === 'jav321') {
                if (status === 'searching') {
                    this.progressLog = `${this.MODE_TEXT[this.currentMode] || '搜尋'}...`;
                }
                else if (status.startsWith('found:')) {
                    const count = status.split(':')[1];
                    if (count === '0') {
                        this.progressLog = `${this.MODE_TEXT[this.currentMode] || '搜尋'}：無結果`;
                    } else {
                        this.progressLog = `${this.MODE_TEXT[this.currentMode] || '搜尋'}：找到 ${count} 筆`;
                    }
                }
                else if (status === 'fetching_details') {
                    this.progressLog = '抓取詳情...';
                }
                else if (status.startsWith('details:')) {
                    const parts = status.split(':')[1].split('/');
                    if (parts.length === 2) {
                        this.detailDone = parseInt(parts[0]);
                        this.detailTotal = parseInt(parts[1]);
                        this.progressLog = `抓取詳情 ${this.detailDone}/${this.detailTotal}`;
                    }
                }
                else if (status === 'failed') {
                    this.progressLog = `${this.MODE_TEXT[this.currentMode] || '搜尋'}：失敗`;
                }
            }
        },

        // ===== Navigation Methods =====

        /**
         * 導航到相對位置
         * @param {number} delta - 偏移量（-1 = 上一個，1 = 下一個）
         */
        navigate(delta) {
            const newIndex = this.currentIndex + delta;

            // 往左且已在第一個 → 切換到上一個檔案
            if (delta < 0 && newIndex < 0) {
                if (this.currentFileIndex > 0 && window.SearchFile?.switchToFile) {
                    window.SearchFile.switchToFile(this.currentFileIndex - 1, 'last');
                }
                return;
            }

            // 往右且到最後一個
            if (delta > 0 && newIndex >= this.searchResults.length) {
                if (this.hasMoreResults && !this.isLoadingMore) {
                    this.loadMore();
                    return;
                }
                if (this.currentFileIndex < this.fileList.length - 1 && window.SearchFile?.switchToFile) {
                    window.SearchFile.switchToFile(this.currentFileIndex + 1, 'first');
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

                if (window.SearchUI?.preloadImages) {
                    window.SearchUI.preloadImages(this.currentIndex + 1, 3);
                }
                if (this.listMode === 'search' && window.SearchFile?.renderSearchResultsList) {
                    window.SearchFile.renderSearchResultsList();
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
                    if (this.listMode === 'search' && window.SearchFile?.renderSearchResultsList) {
                        window.SearchFile.renderSearchResultsList();
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

            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                this.navigate(-1);
            } else if (event.key === 'ArrowRight') {
                event.preventDefault();
                this.navigate(1);
            }
        },

        // ===== T1c: Result Card Computed =====

        current() {
            if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
                const results = this.fileList[this.currentFileIndex].searchResults || [];
                return results[this.currentIndex] || {};
            }
            return this.searchResults[this.currentIndex] || {};
        },

        get hasSubtitle() {
            if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
                return this.fileList[this.currentFileIndex].hasSubtitle || false;
            }
            return false;
        },

        get chineseTitle() {
            if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
                return this.fileList[this.currentFileIndex].chineseTitle || null;
            }
            return null;
        },

        hasChineseTitle() {
            const c = this.current();
            return !!(c.translated_title || this.chineseTitle);
        },

        chineseTitleLabel() {
            const c = this.current();
            if (c.translated_title) return '中文片名 (AI)';
            return '中文片名';
        },

        chineseTitleText() {
            const c = this.current();
            return c.translated_title || this.chineseTitle || '-';
        },

        coverUrl() {
            const c = this.current();
            if (!c.cover) return '';
            return `/api/proxy-image?url=${encodeURIComponent(c.cover)}`;
        },

        canTranslate() {
            const c = this.current();
            return this.appConfig?.translate?.enabled &&
                   !this.chineseTitle &&
                   !c.translated_title &&
                   c.title &&
                   window.SearchCore?.hasJapanese(c.title) &&
                   !window.SearchCore?.isBatchTranslating(this.currentIndex);
        },

        hasLocalBadge() {
            return this.current()?._localStatus?.exists || false;
        },

        localBadgeTitle() {
            const status = this.current()?._localStatus;
            if (!status || !status.exists) return '';
            return status.count > 1
                ? `本地已有 ${status.count} 個版本（點擊複製路徑）`
                : '本地已有（點擊複製路徑）';
        },

        // ===== T1c: Title Edit Methods =====

        startEditTitle() {
            const c = this.current();
            this.editedTitleValue = c.title || '';
            this.editingTitle = true;
            this.$nextTick(() => {
                this.$refs.titleInput?.focus();
                this.$refs.titleInput?.select();
            });
        },

        confirmEditTitle() {
            const newValue = this.editedTitleValue.trim();
            const c = this.current();
            c.title = newValue;
            c._titleEdited = true;
            this.editingTitle = false;
            this.saveState();
        },

        cancelEditTitle() {
            this.editingTitle = false;
        },

        startEditChineseTitle() {
            this.editedChineseTitleValue = this.chineseTitleText() || '';
            this.editingChineseTitle = true;
            this.$nextTick(() => {
                this.$refs.chineseTitleInput?.focus();
                this.$refs.chineseTitleInput?.select();
            });
        },

        confirmEditChineseTitle() {
            const newValue = this.editedChineseTitleValue.trim();
            const c = this.current();
            c.translated_title = newValue;
            c._chineseTitleEdited = true;
            this.editingChineseTitle = false;
            this.saveState();
        },

        cancelEditChineseTitle() {
            this.editingChineseTitle = false;
        },

        // ===== T1c: Translate =====

        async translateWithAI() {
            if (this.isTranslating) return;
            this.isTranslating = true;
            try {
                // 呼叫 core.js 的實際翻譯邏輯（已去除 DOM 操作）
                await window.SearchCore._translateWithAI();
                // translated_title 已寫入 searchResult object → Alpine reactive 自動更新
            } catch (error) {
                console.error('[Translate] 翻譯失敗:', error);
                alert('翻譯失敗：' + error.message);
            } finally {
                this.isTranslating = false;
            }
        },

        // ===== T1c: User Tags =====

        showAddTagInput() {
            this.newTagValue = '';
            this.addingTag = true;
            this.$nextTick(() => {
                this.$refs.tagInput?.focus();
            });
        },

        confirmAddTag() {
            const tag = this.newTagValue.trim();
            if (!tag) {
                this.addingTag = false;
                return;
            }
            const c = this.current();
            if (!c.user_tags) c.user_tags = [];
            if (c.user_tags.includes(tag)) {
                this.addingTag = false;
                return;
            }
            c.user_tags.push(tag);
            this.addingTag = false;
            this.saveState();
        },

        cancelAddTag() {
            this.addingTag = false;
        },

        removeUserTag(tag) {
            const c = this.current();
            if (!c.user_tags) return;
            const idx = c.user_tags.indexOf(tag);
            if (idx > -1) {
                c.user_tags.splice(idx, 1);
                this.saveState();
            }
        },

        // ===== T1c: Local Badge =====

        copyLocalPath() {
            const paths = this.current()?._localStatus?.paths || [];
            if (paths.length === 0) return;
            const textToCopy = paths.length === 1 ? paths[0] : paths.join('\n');
            navigator.clipboard.writeText(textToCopy).then(() => {
                const msg = paths.length === 1 ? '已複製路徑' : `已複製 ${paths.length} 個路徑`;
                this.showToast(msg, 'success');
            }).catch(err => {
                console.error('複製失敗:', err);
                this.showToast('複製失敗', 'error');
            });
        },

        // ===== T1c: Toast =====

        showToast(message, type = 'success') {
            const iconMap = {
                success: 'bi-check-circle-fill',
                error: 'bi-exclamation-circle-fill',
                info: 'bi-info-circle-fill',
                warning: 'bi-exclamation-triangle-fill'
            };
            const toast = document.createElement('div');
            toast.className = `fluent-toast alert alert-${type}`;
            toast.innerHTML = `<i class="bi ${iconMap[type] || iconMap.success}"></i><span>${message}</span>`;
            toast.style.cssText = `position:fixed;bottom:1.5rem;right:1.5rem;z-index:2000;opacity:0;transform:translateY(20px);transition:all var(--fluent-duration-normal) var(--fluent-ease-decel);`;
            document.body.appendChild(toast);
            requestAnimationFrame(() => { toast.style.opacity='1'; toast.style.transform='translateY(0)'; });
            setTimeout(() => { toast.style.opacity='0'; toast.style.transform='translateY(20px)'; setTimeout(() => toast.remove(), 300); }, 2000);
        },

        // ===== T1c: Cover Error =====

        handleCoverError() {
            this.coverError = '封面載入失敗';
        }

        // T1d will add: renderFileList(), searchAll(), scrapeAll()
    };
}
