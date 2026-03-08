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
        // 關閉進行中的 SSE 連線（防止舊事件重新填入 UI）
        if (this.activeEventSource) {
            this.activeEventSource.close();
            this._untrackConnection(this.activeEventSource);
            this.activeEventSource = null;
        }
        this.requestId++;  // 使所有殘留的 async callback 失效
        // 取消進行中的 REST fallback fetch
        if (this._fallbackAbortController) {
            this._fallbackAbortController.abort();
            this._fallbackAbortController = null;
        }
        // T4: 清除 stream state
        this.isStreaming = false;
        this.streamComplete = false;
        this.streamSlots = [];
        // U2: 清除 staging buffer + timer（C15 約束）
        if (this.streamBurstTimer !== null) {
            clearTimeout(this.streamBurstTimer);
            this.streamBurstTimer = null;
        }
        // U3: 清除 cover swap debounce timer（C15 約束）
        if (this._coverSwapTimer !== null) {
            clearTimeout(this._coverSwapTimer);
            this._coverSwapTimer = null;
        }
        this.streamBuffer = [];
        this.streamBurstedSlots = [];
        this.stagingVisible = false;
        // U3: 重置 staging display state
        this.stagingCover = '';
        this.stagingNumber = '';
        this.stagingReceivedCount = 0;
        this._stagingCardWidth = 0;
        // 同步 Alpine state
        this.searchResults = [];
        this.currentIndex = 0;
        this.currentQuery = '';
        this.searchQuery = '';  // 清空搜尋框
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
        // 1. 取得搜尋關鍵字（V1c: 優先從 Alpine state 讀取）
        if (!query) {
            query = this.searchQuery?.trim();
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
        this._resetCoverState();
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
        // T4: 重置 stream state（防競態 + 新搜尋乾淨起始）
        this.isStreaming = false;
        this.streamComplete = false;
        this.streamSlots = [];
        // U2: 重置 staging buffer state（C15 約束）
        this.streamBuffer = [];
        if (this.streamBurstTimer !== null) {
            clearTimeout(this.streamBurstTimer);
            this.streamBurstTimer = null;
        }
        // U3: 清除 cover swap debounce timer（C15 約束）
        if (this._coverSwapTimer !== null) {
            clearTimeout(this._coverSwapTimer);
            this._coverSwapTimer = null;
        }
        this.streamBurstedSlots = [];
        this.stagingVisible = false;
        // U3: 重置 staging display state
        this.stagingCover = '';
        this.stagingNumber = '';
        this.stagingReceivedCount = 0;
        this._stagingCardWidth = 0;

        // 檔案列表由 x-show 自動隱藏（listMode=null, fileList=[]）

        // 6. 建立 SSE 連線並追蹤
        this.activeEventSource = this._trackConnection(new EventSource(`/api/search/stream?q=${encodeURIComponent(query)}`));
        const eventSource = this.activeEventSource;

        eventSource.onmessage = (event) => {
            // 檢查是否已被取消
            if (currentRequestId !== this.requestId) {
                eventSource.close();
                this._untrackConnection(eventSource);
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
                // T4: seed handler（C11 約束）
                else if (data.type === 'seed') {
                    this.isStreaming = true;
                    this.streamComplete = false;
                    this.streamSlots = data.slots;
                    this.streamBurstedSlots = new Array(data.slots.length).fill(false);
                    this.searchResults = data.slots.map(num => ({ number: num, _skeleton: true }));
                    this.currentIndex = 0;
                    this.listMode = 'search';       // C11: grid 可見條件 1
                    this.displayMode = 'grid';      // C11: grid 可見條件 2
                    this.hasContent = true;
                    window.SearchUI.showState('result');  // C11: pageState='result'，正確 API
                    // T5: Progress → skeleton grid 轉場（輕量整體淡入）
                    this.$nextTick(() => {
                        requestAnimationFrame(() => {
                            const grid = document.querySelector('.search-grid');
                            if (grid) {
                                window.SearchAnimations?.playGridFadeIn?.(grid);
                                // U3: 預量 grid card 寬度，供 staging card 首次顯示時同步
                                const gridCard = grid.querySelector('.av-card-preview:not(.hero-card)');
                                if (gridCard) {
                                    this._stagingCardWidth = gridCard.getBoundingClientRect().width;
                                }
                            }
                        });
                    });
                }
                // T4: result-item handler（U2: 推入 buffer，不直接填入 grid）
                else if (data.type === 'result-item') {
                    const { slot, data: item } = data;
                    if (slot >= 0 && slot < this.searchResults.length) {
                        // U2: 推入 staging buffer（不直接修改 searchResults）
                        this.streamBuffer.push({ slot, data: item });

                        // U3: 更新 staging display state（C16 裝飾性）
                        this.stagingCover = item.cover || '';
                        this.stagingNumber = item.number || '';
                        this.stagingReceivedCount++;

                        // 首次顯示 staging 容器 → 觸發進場 morph
                        const wasHidden = !this.stagingVisible;
                        this.stagingVisible = true;

                        if (wasHidden) {
                            // 首次顯示：套用 seed 時預量的 grid card 寬度 + playStagingEntry
                            this.$nextTick(() => {
                                const stagingCardEl = this.$refs?.stagingCard;
                                if (stagingCardEl && this._stagingCardWidth > 0) {
                                    stagingCardEl.style.width = this._stagingCardWidth + 'px';
                                }
                                window.SearchAnimations?.playStagingEntry?.(stagingCardEl);
                            });
                        } else {
                            // 後續到達：playCoverSwap debounce（C20：150ms 內多筆只觸發一次）
                            if (this._coverSwapTimer !== null) {
                                clearTimeout(this._coverSwapTimer);
                            }
                            this._coverSwapTimer = setTimeout(() => {
                                this._coverSwapTimer = null;
                                const stagingImgEl = this.$refs?.stagingImg;
                                window.SearchAnimations?.playCoverSwap?.(stagingImgEl);
                            }, 150);
                        }

                        // 啟動時間窗口 timer（若尚未排程）
                        this._scheduleFlushTimer();
                    }
                }
                // T4: result-complete handler（C9 約束 — 失敗 slot 原地標記）
                else if (data.type === 'result-complete') {
                    // Issue 1 fix: 不在此關閉 EventSource，讓後端的 fallback result 能送達
                    this.streamComplete = true;
                    // U2: 清除 burst timer（C15 約束）
                    if (this.streamBurstTimer !== null) {
                        clearTimeout(this.streamBurstTimer);
                        this.streamBurstTimer = null;
                    }
                    // U3: 清除 cover swap debounce timer（C15 約束）
                    if (this._coverSwapTimer !== null) {
                        clearTimeout(this._coverSwapTimer);
                        this._coverSwapTimer = null;
                    }
                    this.$nextTick(() => { this.isStreaming = false; });
                    this.hasMoreResults = data.has_more || false;
                    this.actressProfile = data.actress_profile || null;
                    // C9: 不用 filter()，失敗 slot 原地標記
                    // C13: map 回傳新 array，觸發 Alpine reactivity
                    // 只標記「尚未 burst 的 _skeleton」（已 burst 的 slot 已填入真實資料）
                    this.searchResults = this.searchResults.map(r =>
                        r._skeleton ? { ...r, _skeleton: false, _failed: true } : r
                    );
                    // U3: flush 剩餘 streamBuffer（isFinal=true），chain exit morph
                    if (this.streamBuffer.length > 0) {
                        this._flushStreamBuffer(true);
                    } else {
                        // buffer 已空 → 直接觸發 exit morph
                        this._triggerStagingExit();
                    }
                    // U11a: repoint currentIndex only if it points to a _failed slot (Codex review fix)
                    const currentResult = this.searchResults[this.currentIndex];
                    if (currentResult && currentResult._failed) {
                        const firstValid = this.searchResults.findIndex(r => !r._failed);
                        if (firstValid !== -1) {
                            this.currentIndex = firstValid;
                        }
                    }
                    // else: user already selected a valid item during streaming, don't override
                }
                else if (data.type === 'result') {
                    // T4: Stream guard — 漸進路徑的 result 決定最終狀態後關閉連線
                    if (this.streamComplete) {
                        const allFailed = this.searchResults.every(r => r._failed);
                        if (allFailed && data.success && data.data && data.data.length > 0) {
                            // Issue 1: Fallback 路徑（actress → keyword），用 result 資料完整替換
                            this._resetCoverState();
                            this.searchResults = data.data;
                            this.currentIndex = 0;
                            this.hasMoreResults = data.has_more || false;
                            this.actressProfile = data.actress_profile || null;
                            this.listMode = 'search';
                            if (data.mode) this.currentMode = data.mode;
                            // 與傳統 result 路徑一致：尊重 gallery_mode_enabled 設定
                            if ((data.mode === 'actress' || data.mode === 'prefix') && this.appConfig?.search?.gallery_mode_enabled && data.data.length >= 10) {
                                this.displayMode = 'grid';
                            } else {
                                this.displayMode = 'detail';
                            }
                            // 重置 stream state（已不是 stream 模式）
                            this.isStreaming = false;
                            this.streamComplete = false;
                            this.streamSlots = [];
                            window.SearchUI.showState('result');
                            // U4: detail entry animation (fire-and-forget, C17)
                            this.$nextTick(() => {
                                if (this.displayMode === 'detail') {
                                    var detailEl = document.querySelector('.av-card-full');
                                    window.SearchAnimations?.playDetailEntry?.(detailEl);
                                }
                            });
                            this.hasContent = true;
                            // Issue 2: 查詢本地狀態
                            if (window.SearchCore?.checkLocalStatus) {
                                window.SearchCore.checkLocalStatus(this.searchResults);
                            }
                        } else if (allFailed && (!data.success || !data.data || data.data.length === 0)) {
                            // 全部失敗且無 fallback → 顯示 error
                            this.errorText = '找不到資料';
                            window.SearchUI.showState('error');
                        } else {
                            // 正常 stream 完成：只補充 metadata
                            this.hasMoreResults = data.has_more || false;
                            if (data.actress_profile) this.actressProfile = data.actress_profile;
                            this.hasContent = this.searchResults.length > 0;
                            // Issue 2: 查詢本地狀態（只對非 _failed 結果）
                            if (window.SearchCore?.checkLocalStatus) {
                                window.SearchCore.checkLocalStatus(this.searchResults.filter(r => !r._failed));
                            }
                        }
                        this._searchSnapshot = null;
                        eventSource.close();
                        this._untrackConnection(eventSource);
                        this.activeEventSource = null;
                        return;
                    }
                    eventSource.close();
                    this._untrackConnection(eventSource);
                    this.activeEventSource = null;

                    if (data.success && data.data && data.data.length > 0) {
                        // 修正 2: 更新 Alpine state
                        this.searchResults = data.data;
                        this.currentIndex = 0;
                        this.hasMoreResults = data.has_more || false;
                        this.actressProfile = data.actress_profile || null;  // T2d: 寫入女優資料
                        this.listMode = 'search';

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
                        // U4: detail entry animation (fire-and-forget, C17)
                        this.$nextTick(() => {
                            if (this.displayMode === 'detail') {
                                var detailEl = document.querySelector('.av-card-full');
                                window.SearchAnimations?.playDetailEntry?.(detailEl);
                            }
                        });
                        if (window.SearchUI?.preloadImages) {
                            window.SearchUI.preloadImages(1, 5);
                        }
                        this.listMode = 'search';
                        this.hasContent = this.searchResults.length > 0 || this.fileList.length > 0;
                        this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                        // Reset edit states
                        this._resetCoverState();
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
                    this._untrackConnection(eventSource);
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
                this._untrackConnection(eventSource);
                return;
            }

            eventSource.close();
            this._untrackConnection(eventSource);
            this.activeEventSource = null;
            // T4: 清除 stream state（防 stream UI 殘留到 fallback）
            this.isStreaming = false;
            this.streamComplete = false;
            this.streamSlots = [];
            // U2: 清除 staging buffer + timer（進 fallback 前必須清乾淨）
            if (this.streamBurstTimer !== null) {
                clearTimeout(this.streamBurstTimer);
                this.streamBurstTimer = null;
            }
            // U3: 清除 cover swap debounce timer
            if (this._coverSwapTimer !== null) {
                clearTimeout(this._coverSwapTimer);
                this._coverSwapTimer = null;
            }
            this.streamBuffer = [];
            this.streamBurstedSlots = [];
            this.stagingVisible = false;
            // U3: 重置 staging display state
            this.stagingCover = '';
            this.stagingNumber = '';
            this.stagingReceivedCount = 0;
        this._stagingCardWidth = 0;
            this.fallbackSearch(query, currentRequestId); // Fix 3: 傳入 requestId
        };
    },

    /**
     * 傳統 API 回退（SSE 失敗時）
     * @param {string} query - 搜尋關鍵字
     * @param {number} savedRequestId - 保存的請求 ID（防競態）
     */
    async fallbackSearch(query, savedRequestId) {
        // 建立 AbortController（離頁時可取消）
        this._fallbackAbortController = new AbortController();

        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
                signal: this._fallbackAbortController.signal
            });
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
                this.listMode = 'search';

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
                // U4: detail entry animation (fire-and-forget, C17)
                this.$nextTick(() => {
                    if (this.displayMode === 'detail') {
                        var detailEl = document.querySelector('.av-card-full');
                        window.SearchAnimations?.playDetailEntry?.(detailEl);
                    }
                });
                if (window.SearchUI?.preloadImages) {
                    window.SearchUI.preloadImages(1, 5);
                }
                this.listMode = 'search';
                this.hasContent = this.searchResults.length > 0 || this.fileList.length > 0;
                this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋成功）
                // Reset edit states
                this._resetCoverState();
                this.editingTitle = false;
                this.editingChineseTitle = false;
                this.addingTag = false;
            } else {
                this._searchSnapshot = null; // Fix 2: 清空 snapshot（搜尋失敗）
                this.errorText = data.error || '找不到資料';  // T6c: Alpine state
                window.SearchUI.showState('error');
            }
        } catch (err) {
            // AbortError：離頁或新搜尋取消，靜默忽略
            if (err.name === 'AbortError') return;
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
            this._untrackConnection(this.activeEventSource);
            this.activeEventSource = null;
        }
        this.requestId++;
        // 取消進行中的 REST fallback fetch
        if (this._fallbackAbortController) {
            this._fallbackAbortController.abort();
            this._fallbackAbortController = null;
        }

        // T4: 清除 stream state（防殘留 skeleton）
        this.isStreaming = false;
        this.streamComplete = false;
        this.streamSlots = [];
        // U2: 清除 staging buffer + timer（C15 約束）
        if (this.streamBurstTimer !== null) {
            clearTimeout(this.streamBurstTimer);
            this.streamBurstTimer = null;
        }
        // U3: 清除 cover swap debounce timer（C15 約束）
        if (this._coverSwapTimer !== null) {
            clearTimeout(this._coverSwapTimer);
            this._coverSwapTimer = null;
        }
        this.streamBuffer = [];
        this.streamBurstedSlots = [];
        this.stagingVisible = false;
        // U3: 重置 staging display state
        this.stagingCover = '';
        this.stagingNumber = '';
        this.stagingReceivedCount = 0;
        this._stagingCardWidth = 0;

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

            // 還原顯示
            window.SearchUI.showState(snap.pageState);
        } else {
            window.SearchUI.showState('empty');
        }
        this._searchSnapshot = null;
    },

    // ===== U2: Staging Buffer 私有方法 =====

    /**
     * 取出 streamBuffer 全部項目，批量填入 searchResults（單次 Alpine render）
     * 契約：幂等（buffer 為空直接 return）；C13 clone array
     * @param {boolean} [isFinal=false] - true 時 chain exit morph（result-complete 呼叫）
     */
    _flushStreamBuffer(isFinal = false) {
        if (this.streamBuffer.length === 0) {
            if (isFinal) this._triggerStagingExit();
            return;
        }

        // 取出全部項目並清空 buffer
        const items = this.streamBuffer.splice(0);
        const flushedSlots = items.map(({ slot }) => slot);

        // C13: clone array，單次更新 searchResults（避免多次 Alpine patch）
        const clonedResults = [...this.searchResults];
        for (const { slot, data } of items) {
            if (slot >= 0 && slot < clonedResults.length) {
                clonedResults[slot] = data;
                // 標記 streamBurstedSlots
                if (this.streamBurstedSlots && slot < this.streamBurstedSlots.length) {
                    this.streamBurstedSlots[slot] = true;
                }
            }
        }
        this.searchResults = clonedResults;

        // U3: playMiniBurst — 等 Alpine 渲染完成後找新卡片 DOM
        const capturedRequestId = this.requestId;
        this.$nextTick(() => {
            // requestId guard：防止新搜尋後舊 flush 動畫污染
            if (capturedRequestId !== this.requestId) return;

            const stagingEl = this.$refs?.stagingCard;
            const grid = document.querySelector('.search-grid');
            if (!grid) {
                if (isFinal) this._triggerStagingExit();
                return;
            }

            // 找本批 flush 的卡片 DOM（按 data-slot 屬性匹配）
            const cards = flushedSlots
                .map(slot => grid.querySelector(`[data-slot="${slot}"]`))
                .filter(Boolean);

            if (!cards.length) {
                if (isFinal) this._triggerStagingExit();
                return;
            }

            // 動態同步 staging card 寬度：每批 burst 前量測 cards[0]（避免首次量到 0）
            const stagingCardEl = this.$refs?.stagingCard;
            if (cards[0] && stagingCardEl) {
                const cardWidth = cards[0].getBoundingClientRect().width;
                if (cardWidth > 0) {
                    stagingCardEl.style.width = cardWidth + 'px';
                }
            }

            // 呼叫 playMiniBurst（optional chaining，SearchAnimations 未載入時功能正常）
            window.SearchAnimations?.playMiniBurst?.(cards, stagingEl, {
                onComplete: isFinal ? () => { this._triggerStagingExit(); } : undefined
            });

            // SearchAnimations 不存在時，isFinal 直接觸發 exit
            if (!window.SearchAnimations && isFinal) {
                this._triggerStagingExit();
            }
        });
    },

    /**
     * 觸發 staging exit morph（幂等）
     * 契約：if (!this.stagingVisible) return（防止重複呼叫）
     * onComplete → stagingVisible = false + 重置 staging display state
     */
    _triggerStagingExit() {
        if (!this.stagingVisible) return;

        const stagingEl = this.$refs?.stagingCard;
        const self = this;
        const capturedRequestId = this.requestId;  // A4 fix: 捕獲 searchId 防競態

        function onExitComplete() {
            self.stagingVisible = false;
            self.stagingCover = '';
            self.stagingNumber = '';
            self.stagingReceivedCount = 0;
            self._stagingCardWidth = 0;

            // A4: Grid Settle Pulse（fire-and-forget）
            // requestId guard：搜尋 A 的 exit callback 晚於搜尋 B 開始時跳過
            self.$nextTick(function () {
                if (capturedRequestId !== self.requestId) return;
                requestAnimationFrame(function () {
                    if (capturedRequestId !== self.requestId) return;
                    var grid = document.querySelector('.search-grid');
                    window.SearchAnimations?.playGridSettle?.(grid);
                });
            });
        }

        if (!window.SearchAnimations) {
            onExitComplete();
            return;
        }

        window.SearchAnimations?.playStagingExit?.(stagingEl, {
            onComplete: onExitComplete
        });

        // playStagingExit 不存在時直接設 false
        if (!window.SearchAnimations?.playStagingExit) {
            onExitComplete();
        }
    },

    /**
     * 啟動時間窗口 timer（已有 timer 時不覆蓋）
     * 混合模式：800ms 後若 buffer >= MIN_BATCH_COUNT 則 flush，否則繼續等
     */
    _scheduleFlushTimer() {
        const BURST_INTERVAL = 800;  // ms
        const MIN_BATCH_COUNT = 3;

        if (this.streamBurstTimer !== null) return;  // 已有 timer，不覆蓋

        const capturedRequestId = this.requestId;    // 捕獲到閉包（防 doSearch 競態）
        this.streamBurstTimer = setTimeout(() => {
            this.streamBurstTimer = null;
            // requestId guard：doSearch() 已啟動新搜尋 → 舊 timer 靜默放棄
            if (capturedRequestId !== this.requestId) return;
            if (this.streamBuffer.length >= MIN_BATCH_COUNT) {
                this._flushStreamBuffer();
            } else if (this.streamBuffer.length > 0) {
                // buffer 不足 MIN_BATCH_COUNT → 重新啟動等待
                this._scheduleFlushTimer();
            }
            // buffer 為空 → 不再排程（result-complete 時處理）
        }, BURST_INTERVAL);
    },

    /**
     * 離頁前清理 SSE（不還原 snapshot，因為離頁時會另外 saveState）
     */
    cleanupForNavigation() {
        // _closeAllConnections() 包含 activeEventSource 和 searchForFile() 的 ES
        this._closeAllConnections();
        this.activeEventSource = null;   // 維持單一引用清零（語義清晰）

        // 取消進行中的 REST fallback fetch
        if (this._fallbackAbortController) {
            this._fallbackAbortController.abort();
            this._fallbackAbortController = null;
        }
        this.requestId++;  // 讓進行中的 onmessage/onerror callback 失效
        // 也讓進行中的 fallbackSearch() 的 savedRequestId check 失效

        // T4: 清除 stream state
        this.isStreaming = false;
        this.streamComplete = false;
        this.streamSlots = [];
        // U2: 清除 staging buffer + timer（streamBurstTimer 不在 _timers registry，需獨立清）
        if (this.streamBurstTimer !== null) {
            clearTimeout(this.streamBurstTimer);
            this.streamBurstTimer = null;
        }
        // U3: 清除 cover swap debounce timer（C15 約束）
        if (this._coverSwapTimer !== null) {
            clearTimeout(this._coverSwapTimer);
            this._coverSwapTimer = null;
        }
        this.streamBuffer = [];
        this.streamBurstedSlots = [];
        this.stagingVisible = false;
        // U3: 重置 staging display state
        this.stagingCover = '';
        this.stagingNumber = '';
        this.stagingReceivedCount = 0;
        this._stagingCardWidth = 0;

        // T4.2: 清除所有 setTimeout timer
        this._clearAllTimers();

        // T4.3: 取消所有 fetch（loadMore / translateAll / setFileList / loadFavorite）
        this._abortAllFetches();

        // T4.2: 讓 batch/translate 的 checkInterval 自清（setPaused=false 讓條件成立）
        this.batchState.isProcessing = false;
        this.batchState.isPaused = false;
        this.translateState.isProcessing = false;
        this.translateState.isPaused = false;
    },

    // ===== T4.1: EventSource 集中追蹤方法 =====

    /**
     * 追蹤 EventSource 連線，加入 _activeConnections 陣列
     * @param {EventSource} es - 要追蹤的 EventSource 實例
     * @returns {EventSource} 回傳 es 本身，讓呼叫側可以鏈式賦值
     */
    _trackConnection(es) {
        this._activeConnections.push(es);
        return es;
    },

    /**
     * 從 _activeConnections 移除 EventSource（不關閉連線）
     * @param {EventSource} es - 要移除的 EventSource 實例
     */
    _untrackConnection(es) {
        this._activeConnections = this._activeConnections.filter(c => c !== es);
    },

    /**
     * 關閉並清空所有追蹤中的 EventSource 連線
     */
    _closeAllConnections() {
        this._activeConnections.forEach(c => {
            if (c.readyState !== EventSource.CLOSED) {
                c.close();
            }
        });
        this._activeConnections = [];
    },

    // ===== T4.2: Timer 集中追蹤方法 =====

    /**
     * 設定具名 timer（自動取代同 key 的舊 timer）
     * @param {string} key - timer 識別碼（如 'toast', 'autosave', 'loadFavorite'）
     * @param {Function} fn - 回調函數
     * @param {number} delay - 延遲毫秒
     */
    _setTimer(key, fn, delay) {
        if (this._timers[key]) clearTimeout(this._timers[key]);
        this._timers[key] = setTimeout(() => {
            delete this._timers[key];
            fn();
        }, delay);
    },

    /**
     * 清除所有 registry 中的 timer（離頁時呼叫）
     */
    _clearAllTimers() {
        Object.values(this._timers).forEach(clearTimeout);
        this._timers = {};
    },

    // U8a: single timer clear
    _clearTimer(key) {
        if (this._timers[key]) {
            clearTimeout(this._timers[key]);
            delete this._timers[key];
        }
    },

    // ===== T4.3: Fetch AbortController 集中追蹤方法 =====

    /**
     * 取得指定 key 的 AbortSignal（自動 abort 並取代同 key 的舊 controller）
     * @param {string} key - fetch 識別碼（如 'loadMore', 'translateAll', 'setFileList', 'loadFavorite'）
     * @returns {AbortSignal}
     */
    _getAbortSignal(key) {
        if (this._abortControllers[key]) this._abortControllers[key].abort();
        this._abortControllers[key] = new AbortController();
        return this._abortControllers[key].signal;
    },

    /**
     * 從 registry 移除指定 key 的 AbortController（fetch 完成後呼叫）
     * 只清除持有指定 signal 的 controller，避免刪掉新請求的 controller
     * @param {string} key - fetch 識別碼
     * @param {AbortSignal} [signal] - 呼叫 _getAbortSignal 時取得的 signal；若省略則無條件刪除
     */
    _clearAbort(key, signal) {
        if (!signal || (this._abortControllers[key] && this._abortControllers[key].signal === signal)) {
            delete this._abortControllers[key];
        }
    },

    /**
     * 取消並清空所有 registry 中的 fetch（離頁時呼叫）
     */
    _abortAllFetches() {
        Object.values(this._abortControllers).forEach(c => c.abort());
        this._abortControllers = {};
    },

    /**
     * 初始化搜尋進度顯示（T3.3: 從 bridge.js 搬移）
     * @param {string} query - 搜尋番號
     */
    initProgress(query) {
        this.progressLog = '搜尋中...';
        this.currentMode = '';
        this.detailDone = 0;
        this.detailTotal = 0;
        this.currentQuery = query;
    },

    /**
     * 更新進度記錄文字（T3.3: 從 bridge.js 搬移）
     * @param {string} msg - 進度訊息
     */
    updateLog(msg) {
        this.progressLog = msg;
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
