/**
 * SearchState - File List Mixin
 * 包含：檔案列表操作（switchToFile, searchForFile, setFileList, addFiles, addFolder, loadFavorite）
 */
export function searchStateFileList() {
    return {
    // ===== T1d: File Methods =====

    async switchToFile(index, position = 'first', showFullLoading = false) {
        if (index < 0 || index >= this.fileList.length) return;

        this.currentFileIndex = index;
        const file = this.fileList[index];

        if (!file.number) {
            this.searchResults = [];
            this.hasMoreResults = false;
            this.currentIndex = 0;
            this._resetCoverState();
            this.coverError = window.t('search.filelist.unrecognized', { filename: file.filename });
            this.pageState = 'result';
            return;
        }

        if (!file.searched) {
            await this.searchForFile(file, position, showFullLoading);
        } else if (file.searchResults && file.searchResults.length > 0) {
            // U7b: C18 interrupt old animation
            var detailEl = document.querySelector('.av-card-full');
            if (typeof gsap !== 'undefined' && detailEl) {
                gsap.killTweensOf(detailEl);
            }

            this.searchResults = file.searchResults;
            this.hasMoreResults = file.hasMoreResults || false;
            this.currentIndex = position === 'last' ? this.searchResults.length - 1 : 0;
            this._resetCoverState();

            this.pageState = 'result';
            this.fetchUserTagsForCurrent?.();
            // U7b: slide-in animation (C22: direction from position hint)
            var direction = position === 'first' ? 'next' : 'prev';
            this.$nextTick(() => {
                var el = document.querySelector('.av-card-full');
                window.SearchAnimations?.playSlideIn?.(el, direction);
            });
        } else {
            this.searchResults = [];
            this.hasMoreResults = false;
            this.currentIndex = 0;
            this._resetCoverState();
            this.coverError = window.t('search.filelist.not_found', { number: file.number });
            this.pageState = 'result';
        }
    },

    async searchForFile(file, position = 'first', showFullLoading = false) {
        this.isSearchingFile = true;

        if (showFullLoading) {
            this.pageState = 'loading';
            this.initProgress(file.number);
        } else {
            this.isSearchingFile = true;
            this.searchingFileDirection = position === 'first' ? 'next' : 'prev';
        }

        return new Promise((resolve) => {
            const eventSource = this._trackConnection(new EventSource(`/api/search/stream?q=${encodeURIComponent(file.number)}`));

            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'mode') {
                        this.currentMode = data.mode;
                        const _modeKey1 = 'search.mode.' + data.mode;
                        const _modeTxt1 = window.t(_modeKey1);
                        this.updateLog(`${_modeTxt1.charAt(0) === '[' ? data.mode : _modeTxt1}...`);
                    }
                    else if (data.type === 'status') {
                        this.handleSearchStatus(data.source, data.status);
                    }
                    else if (data.type === 'result') {
                        eventSource.close();
                        this._untrackConnection(eventSource);
                        this.isSearchingFile = false;
                        this.searchingFileDirection = null;
                        this.listMode = 'file';
                        this.displayMode = 'detail';

                        if (data.success && data.data && data.data.length > 0) {
                            file.searchResults = data.data;
                            file.hasMoreResults = data.has_more || false;
                            file.searched = true;

                            this.searchResults = data.data;
                            this.hasMoreResults = file.hasMoreResults;
                            this.currentIndex = position === 'last' ? this.searchResults.length - 1 : 0;
                            this._resetCoverState();

                            // T4: File search 後查詢本地狀態
                            this.checkLocalStatus(this.searchResults);
                            this.fetchUserTagsForCurrent?.();

                            this.pageState = 'result';
                            // U7a: detail entry animation (same as cloud search, C17 fire-and-forget)
                            this.$nextTick(() => {
                                if (this.displayMode === 'detail') {
                                    var detailEl = document.querySelector('.av-card-full');
                                    window.SearchAnimations?.playDetailEntry?.(detailEl);
                                }
                            });
                        } else {
                            file.searched = true;
                            file.searchResults = [];
                            this._resetCoverState();
                            this.coverError = window.t('search.filelist.not_found', { number: file.number });

                            // 重置共享狀態
                            this.searchResults = [];
                            this.hasMoreResults = false;
                            this.currentIndex = 0;

                            this.pageState = 'result';
                        }
                        resolve();
                    }
                    else if (data.type === 'error') {
                        eventSource.close();
                        this._untrackConnection(eventSource);
                        this.isSearchingFile = false;
                        this.searchingFileDirection = null;
                        file.searched = true;
                        file.searchResults = [];
                        this._resetCoverState();
                        this.coverError = data.message || window.t('search.filelist.search_failed');

                        this.searchResults = [];
                        this.hasMoreResults = false;
                        this.currentIndex = 0;

                        this.pageState = 'result';
                        resolve();
                    }
                } catch (err) {
                    console.error('Parse error:', err);
                }
            };

            eventSource.onerror = () => {
                eventSource.close();
                this._untrackConnection(eventSource);
                this.isSearchingFile = false;
                this.searchingFileDirection = null;
                file.searched = true;
                file.searchResults = [];
                this._resetCoverState();
                this.coverError = window.t('search.filelist.connection_error');

                this.searchResults = [];
                this.hasMoreResults = false;
                this.currentIndex = 0;

                this.pageState = 'result';
                resolve();
            };
        });
    },

    /**
     * 背景搜尋單一檔案（不影響 UI 共享狀態）
     * 只寫入 file.searchResults / file.hasMoreResults / file.searched
     * @param {Object} file - 檔案物件（必須有 file.number）
     * @returns {Promise<void>} 保證 resolve（不 reject）
     */
    async _searchFileBackground(file) {
        if (file.searched) return;

        return new Promise((resolve) => {
            let settled = false;
            const settle = () => { if (!settled) { settled = true; resolve(); } };

            const eventSource = this._trackConnection(new EventSource(`/api/search/stream?q=${encodeURIComponent(file.number)}`));

            // Close-wrapper: 覆寫 close()，確保 _closeAllConnections() forced-close 時 Promise 也能 settle
            const originalClose = eventSource.close.bind(eventSource);
            eventSource.close = () => { originalClose(); settle(); };

            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'result') {
                        this._untrackConnection(eventSource);
                        eventSource.close();

                        if (data.success && data.data && data.data.length > 0) {
                            file.searchResults = data.data;
                            file.hasMoreResults = data.has_more || false;
                            file.searched = true;
                        } else {
                            file.searched = true;
                            file.searchResults = [];
                        }
                    }
                    else if (data.type === 'error') {
                        this._untrackConnection(eventSource);
                        eventSource.close();
                        file.searched = true;
                        file.searchResults = [];
                    }
                    // seed / result-item / status / mode: 忽略（背景模式不需要漸進 UI）
                } catch (err) {
                    console.error('Background search parse error:', err);
                    this._untrackConnection(eventSource);
                    eventSource.close();
                    file.searched = true;
                    file.searchResults = [];
                }
            };

            eventSource.onerror = () => {
                this._untrackConnection(eventSource);
                eventSource.close();
                file.searched = true;
                file.searchResults = [];
            };
        });
    },

    switchToSearchResult(index) {
        if (index < 0 || index >= this.searchResults.length) return;
        this.currentIndex = index;

        // U8b: reset cover state on switch
        this._resetCoverState();
    },

    enterNumber(index) {
        const file = this.fileList[index];
        if (!file) return;

        // eslint-disable-next-line no-alert -- inline number edit prompt, backlog migration to fluent-modal, reviewed 2026-05-03
        const number = prompt(window.t('search.filelist.enter_number_prompt'), '');
        if (!number || !number.trim()) return;

        const formatted = window.SearchFile.formatNumber(number.trim());
        file.number = formatted;
        file.searched = false;
        file.searchResults = [];

        this.switchToFile(index, 'first', true);
    },

    removeFile(index) {
        if (index < 0 || index >= this.fileList.length) return;

        this.fileList.splice(index, 1);

        if (this.fileList.length === 0) {
            this.clearAll();
            return;
        }

        if (this.currentFileIndex >= this.fileList.length) {
            this.currentFileIndex = this.fileList.length - 1;
        } else if (this.currentFileIndex > index) {
            this.currentFileIndex--;
        }

        if (this.fileList.length > 0) {
            this.switchToFile(this.currentFileIndex, 'first', false);
        }
        this.saveState();
    },

    async setFileList(paths) {
        // 呼叫過濾 API
        const setFileListSignal = this._getAbortSignal('setFileList');  // T4.3
        // Codex PR#112 P2(第3輪 revert 第2輪): file-list 替換取代任何 pending 拖檔解析——
        // abort handleFileDrop 這條線（方向 a：不動 requestId／不攪動 search 狀態機，見
        // _resolveAndSearchDroppedFile 的 signal.aborted 檢查）。直接 abort 現有 controller，
        // 不用 _getAbortSignal（那會建新 controller 留孤兒）；無 pending 拖檔時為 no-op。
        // （第2輪的 this.requestId++ 已移除：會讓進行中的 doSearch stream 誤走
        // requestId-mismatch 早退，卻不清理 _searchSnapshot/activeEventSource，見 Codex 第3輪 P2）
        this._abortControllers['handleFileDrop']?.abort();
        var hasNfoMap = {};
        try {
            try {
                const resp = await fetch('/api/search/filter-files', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paths }),
                    signal: setFileListSignal
                });
                const result = await resp.json();

                if (result.success) {
                    if (result.total_rejected > 0) {
                        const { extension, size, not_found } = result.rejected;
                        let msg = window.t('search.filelist.filtered_count', { count: result.total_rejected });
                        const details = [];
                        if (extension > 0) details.push(window.t('search.filelist.rejected_extension', { count: extension }));
                        if (size > 0) details.push(window.t('search.filelist.rejected_size', { count: size }));
                        if (not_found > 0) details.push(window.t('search.filelist.rejected_not_found', { count: not_found }));
                        if (details.length > 0) msg += `（${details.join('、')}）`;

                        // T6b: 後端過濾提示（info 類型）
                        this.showToast(msg, 'info');
                    }
                    paths = result.files.map(f => f.path);
                    result.files.forEach(f => { hasNfoMap[f.path] = !!f.has_nfo; });
                }
            } catch (err) {
                if (err.name === 'AbortError') return;  // T4.3: 新搜尋取代，靜默退出
                console.error('Filter API error:', err);
            }

            // 使用後端 API 批次解析所有檔名
            const filenames = paths.map(p => p.split(/[/\\]/).pop());
            let parseResults;
            let parseFailed = false;
            try {
                // T5 P1 fix: 傳入 setFileListSignal——filter 階段的 abort 必須貫穿到 parse 階段，
                // 否則 A 的 parse 不會被 B 取代而在事後 resolve 時覆蓋 B 已建好的 fileList
                // （last-return-wins clobber）。
                parseResults = await window.SearchFile.parseFilenames(filenames, { signal: setFileListSignal });
            } catch (err) {
                if (err.name === 'AbortError') return;   // 與上半段一致的既有語意：
                                                          // 舊請求被新一輪取代，靜默退出，不算「API 不可用」
                parseFailed = true;
                parseResults = filenames.map(f => ({ filename: f, number: null, has_subtitle: false }));
                this.showToast(window.t('search.error.number_parse_unavailable'), 'error');
            }

            // 前端過濾：檢查能否提取番號
            const validIndices = [];
            let noNumberCount = 0;

            if (parseFailed) {
                // CD-4b：API 不可用時，全部 index 視為 valid，不套用「無法識別番號」過濾——
                // filtered_no_number 的語意是「後端已回應、這些檔真的沒有番號」；API 根本沒回應時
                // 套用這套過濾是誤導。此時只該出現 number_parse_unavailable 這一個 toast，不得雙 toast。
                for (let i = 0; i < paths.length; i++) validIndices.push(i);
            } else {
                for (let i = 0; i < paths.length; i++) {
                    const result = parseResults[i];
                    if (result && result.number !== null) {
                        validIndices.push(i);
                    } else {
                        noNumberCount++;
                    }
                }
                // T6b: 前端過濾提示（warning 類型）——既有程式碼，不動
                if (noNumberCount > 0) {
                    const msg = window.t('search.filelist.filtered_no_number', { count: noNumberCount });
                    this.showToast(msg, 'warning');
                }
            }

            // 檢查空列表。正常路徑 validIndices 全空＝所有檔案都認不出番號；parseFailed 分支
            // validIndices 恆為全量，只有 paths 本身就空（filter-files 已全數濾掉）時才會落到這裡，
            // 此時 number_parse_unavailable toast 已顯示過，不再補 no_valid_files（避免雙 toast）。
            if (validIndices.length === 0) {
                if (!parseFailed) {
                    this.showToast(window.t('search.toast.no_valid_files'), 'warning');
                }
                return;
            }

            // 構建 fileList
            this.fileList = validIndices.map(i => {
                const path = paths[i];
                const filename = filenames[i];
                const result = parseResults[i];
                return {
                    path: path,
                    filename: filename,
                    number: result.number,
                    hasSubtitle: result.has_subtitle,
                    suffixes: window.SearchFile.detectSuffixes(
                        filename,
                        this.appConfig?.scraper?.suffix_keywords || []
                    ),
                    chineseTitle: window.SearchFile.extractChineseTitle(filename, result.number),
                    searchResults: [],
                    hasMoreResults: false,
                    searched: false,
                    has_nfo: hasNfoMap[path] || false,
                    user_tags: []
                };
            });
            this.currentFileIndex = 0;
            this.listMode = 'file';
            this.displayMode = 'detail';

            // 重置批次狀態
            const batch = this.batchState;
            batch.isProcessing = false;
            batch.isPaused = false;
            batch.total = 0;
            batch.processed = 0;
            batch.success = 0;
            batch.failed = 0;

            if (this.fileList.length > 0) {
                if (this.fileList[0].number) {
                    this.searchQuery = this.fileList[0].number;
                } else {
                    // Codex PR#112 P2(第4輪): fileList[0] 無番號時清掉 spotlight 殘留的舊番號。
                    // 只有 CD-4b API 失敗 fallback 會走到這裡——該路徑全員 number:null 且不套
                    // validIndices 過濾，故 fileList[0].number 可能為 null；正常路徑的 validIndices
                    // 已濾掉無番號檔，fileList[0] 必有番號、不入此分支。既有邏輯只在「有番號」時
                    // 更新 searchQuery（d75e20b6 起），漏清會讓清單要求手動輸入番號、輸入框卻殘留
                    // 上次搜尋的番號，按 Enter/搜尋鈕搜到 stale 舊標題而非新選檔案。
                    this.searchQuery = '';
                }
                await this.switchToFile(0, 'first', true);
            }
        } finally {
            // T5 P1 fix: clear 移到函式最外層——涵蓋 filter + parse 全流程；比對 signal
            // 避免 A 的 finally 誤刪 B 已建立的新 controller。
            this._clearAbort('setFileList', setFileListSignal);  // T4.3: 操作完成清除 registry（比對 signal 避免刪掉新請求）
        }
    },

    handleFileDrop(files) {                    // 維持同步，main.js:56 的 listener 契約不變
        if (!files || files.length === 0) return;
        this._resolveAndSearchDroppedFile(files[0]);   // fire-and-forget，不 await
    },

    async _resolveAndSearchDroppedFile(file) {
        const signal = this._getAbortSignal('handleFileDrop');   // 同 setFileList:280／loadFavorite:436 的既有機制
        // Codex PR#112 P2 fix: 捕獲 requestId generation——這條 async continuation 沒有共用
        // abort registry 那層（拖檔互相取代），還需要 doSearch/cancelSearch 那層「新一輪手動搜尋
        // 取代舊 async continuation」的權威機制（search-flow.js:107/602），否則拖檔 A 的 parse 在
        // 使用者已手動搜尋 B 之後才 resolve，會覆蓋 B 的 searchQuery/state（CD-11 精神：重用
        // this.requestId，不自創新 generation 欄位）。
        const capturedRequestId = this.requestId;
        try {
            const [r] = await window.SearchFile.parseFilenames([file.name], { signal });
            if (signal.aborted) return;   // Codex PR#112 P2(第3輪): file-list 替換（setFileList）已 abort 本拖檔
            if (capturedRequestId !== this.requestId) return;   // 期間使用者已手動搜尋，這輪 stale，不覆蓋
            if (!r?.number) {
                this.errorText = window.t('search.error.number_not_recognized');  // T6c: 沿用既有 key
                this.pageState = 'error';
                return;
            }
            this.searchQuery = r.number;
            this.doSearch(r.number);
        } catch (err) {
            if (err.name === 'AbortError') return;   // 舊請求被新拖曳取代，靜默退出——必要不是裝飾
            if (signal.aborted) return;   // 同上（對稱）：非 AbortError 失敗但期間已被 file-list 替換取代
            if (capturedRequestId !== this.requestId) return;   // 同上：手動搜尋期間發生的失敗不覆蓋新搜尋狀態
            this.errorText = window.t('search.error.number_parse_unavailable');   // 新 key
            this.pageState = 'error';
        } finally {
            this._clearAbort('handleFileDrop', signal);   // 比對 signal，避免刪掉新請求的 controller
        }
    },

    async addFiles() {
        if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
            this.showToast(window.t('search.toast.desktop_only'), 'info');
            return;
        }
        try {
            const paths = await window.pywebview.api.select_files();
            if (paths && paths.length > 0) {
                await this.setFileList(paths);
            }
        } catch (e) {
            console.error('選取檔案失敗:', e);
        }
    },

    async addFolder() {
        if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
            this.showToast(window.t('search.toast.desktop_only'), 'info');
            return;
        }
        try {
            const result = await window.pywebview.api.select_folder();
            const paths = result?.files || result;
            if (paths && paths.length > 0) {
                await this.setFileList(paths);
            }
        } catch (e) {
            console.error('選取資料夾失敗:', e);
        }
    },

    async loadFavorite() {
        this.isLoadingFavorite = true;
        const loadFavoriteSignal = this._getAbortSignal('loadFavorite');  // T4.3
        try {
            const resp = await fetch('/api/search/favorite-files', {
                signal: loadFavoriteSignal
            });
            const result = await resp.json();

            if (!result.success) {
                console.error('[LoadFavorite]', result.error);
                this.showToast(window.t('search.toast.load_failed'), 'error');
                return;
            }

            await this.setFileList(result.files);

            // 自動開始搜尋（T4.2: 改用 _setTimer，離頁時可統一清除）
            this._setTimer('loadFavorite', () => {
                const searchableFiles = this.fileList.filter(f => f.number && !f.searched && !f.has_nfo);
                if (searchableFiles.length > 0) {
                    this.searchAll();
                }
            }, 100);

        } catch (err) {
            if (err.name === 'AbortError') return;  // T4.3: 靜默忽略取消
            console.error('[LoadFavorite]', err);
            this.showToast(window.t('search.toast.load_failed'), 'error');
        } finally {
            this.isLoadingFavorite = false;
            this._clearAbort('loadFavorite', loadFavoriteSignal);  // T4.3: 操作完成清除 registry（比對 signal 避免刪掉新請求）
        }
    }
    };
}
