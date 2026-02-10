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
        this.errorText = '';  // T6c: 清空錯誤訊息
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

        // T4: 重置 rotating border 動畫追蹤（新搜尋允許重新觸發）
        this._localBorderPlayed = {};

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
            pageState: this.pageState,
            actressProfile: this.actressProfile,
            displayMode: this.displayMode,      // T3 fix: 還原 Grid 狀態
            currentMode: this.currentMode,      // T3 fix: 還原搜尋模式（toggle 顯示依賴）
            errorText: this.errorText            // T6c fix: 還原錯誤訊息
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
        this.actressProfile = null;  // T2d: 清空上次的女優資料
        this.displayMode = 'detail';  // T3a: 新搜尋重置顯示模式
        this._gridImageErrors = new Set();  // T6a: 清空 Grid 圖片錯誤記錄
        this.errorText = '';  // T6c: 清空上次的錯誤訊息

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
                        this.actressProfile = data.actress_profile || null;  // T2d: 寫入女優資料

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

                        // T2b/T3a: 模糊搜尋自動切 Grid（actress/prefix ≥10 筆）
                        if ((this.currentMode === 'actress' || this.currentMode === 'prefix') && this.appConfig?.search?.gallery_mode_enabled && data.data.length >= 10) {
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
                        this.errorText = '找不到資料';  // T6c: Alpine state
                        window.SearchUI.showState('error');
                    }
                }
                else if (data.type === 'error') {
                    eventSource.close();
                    this.activeEventSource = null;
                    this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋錯誤）
                    this.errorText = data.message || '搜尋失敗';  // T6c: Alpine state
                    window.SearchUI.showState('error');
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
        // T4: 重置 rotating border 動畫追蹤
        this._localBorderPlayed = {};

        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            // Fix 3: 檢查是否已被新搜尋取代
            if (savedRequestId !== this.requestId) return;

            if (response.ok && data.success && data.data && data.data.length > 0) {
                // 更新 currentMode 從 response
                this.currentMode = data.mode || this.currentMode;

                // 修正 2: 更新 Alpine state
                this.searchResults = data.data;
                this.currentIndex = 0;
                this.hasMoreResults = data.has_more || false;
                this.actressProfile = data.actress_profile || null;  // T2d: 寫入女優資料

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

                // T2b/T3a: 模糊搜尋自動切 Grid（actress/prefix ≥10 筆）
                if ((data.mode === 'actress' || data.mode === 'prefix') && this.appConfig?.search?.gallery_mode_enabled && data.data.length >= 10) {
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
                this.errorText = data.error || '找不到資料';  // T6c: Alpine state
                window.SearchUI.showState('error');
            }
        } catch (err) {
            // Fix 3: 舊請求失敗不覆蓋新搜尋畫面
            if (savedRequestId !== this.requestId) return;
            this._searchSnapshot = null;
            this.errorText = '網路錯誤: ' + err.message;  // T6c: Alpine state
            window.SearchUI.showState('error');
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
            this.actressProfile = snap.actressProfile;
            this.displayMode = snap.displayMode || 'detail';
            this.currentMode = snap.currentMode || '';
            this.errorText = snap.errorText || '';

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
     * 處理 SSE 狀態更新（T3b: 豐富化進度文字，顯示來源名稱）
     * @param {string} source - 來源（javbus/jav321/javdb/fc2/avsox/mode/done）
     * @param {string} status - 狀態字串
     */
    handleSearchStatus(source, status) {
        // Mode 切換事件（不變）
        if (source === 'mode') {
            this.currentMode = status;
            this.progressLog = `${this.MODE_TEXT[status] || status}...`;
            return;
        }

        // T3b: 忽略 'done' 事件（後端搜尋完成標記，前端由 result 事件處理）
        if (source === 'done') return;

        // T3b: 接受所有 source（移除 javbus/jav321 的限制）
        const sourceName = this.SOURCE_NAME[source] || source;

        if (status === 'searching') {
            this.progressLog = `${sourceName} 搜尋中...`;
        }
        else if (status.startsWith('found:')) {
            const count = status.split(':')[1];
            if (count === '0') {
                this.progressLog = `${sourceName} 無結果`;
            } else {
                this.progressLog = `${sourceName} 找到 ${count} 筆`;
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
            this.progressLog = `${sourceName} 失敗`;
        }
    }
};
