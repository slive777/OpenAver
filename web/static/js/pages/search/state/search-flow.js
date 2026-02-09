/**
 * SearchState - Search Flow Mixin
 * 包含：搜尋流程（doSearch, fallbackSearch, cancelSearch, handleSearchStatus）
 */
window.SearchStateMixin_SearchFlow = {
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

        // 檔案列表由 x-show 自動隱藏（listMode=null, fileList=[]）

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

                        // T2b: 女優搜尋自動切 Grid（前端判斷取代舊 gallery_url 信號）
                        if (this.currentMode === 'actress' && this.appConfig?.search?.gallery_mode_enabled && data.data.length > 10) {
                            this.displayMode = 'grid';
                        }

                        // 顯示結果
                        window.SearchUI.showState('result');
                        if (window.SearchUI?.preloadImages) {
                            window.SearchUI.preloadImages(1, 5);
                        }
                        this.listMode = 'search';
                        this.hasContent = true;
                        window.SearchCore.updateClearButton();
                        this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                        // Reset edit states
                        this.coverError = '';
                        this.editingTitle = false;
                        this.editingChineseTitle = false;
                        this.addingTag = false;
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

                // T2b: 女優搜尋自動切 Grid（前端判斷取代舊 gallery_url 信號）
                if (this.currentMode === 'actress' && this.appConfig?.search?.gallery_mode_enabled && data.data.length > 10) {
                    this.displayMode = 'grid';
                }

                // 顯示結果
                window.SearchUI.showState('result');
                if (window.SearchUI?.preloadImages) {
                    window.SearchUI.preloadImages(1, 5);
                }
                this.listMode = 'search';
                this.hasContent = true;
                window.SearchCore.updateClearButton();
                this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                // Reset edit states
                this.coverError = '';
                this.editingTitle = false;
                this.editingChineseTitle = false;
                this.addingTag = false;
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
    }
};
