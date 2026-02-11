/**
 * SearchState - File List Mixin
 * 包含：檔案列表操作（switchToFile, searchForFile, setFileList, addFiles, addFolder, loadFavorite）
 */
window.SearchStateMixin_FileList = {
    // ===== T1d: File Methods =====

    async switchToFile(index, position = 'first', showFullLoading = false) {
        if (index < 0 || index >= this.fileList.length) return;

        this.currentFileIndex = index;
        const file = this.fileList[index];
        this._syncToCore({ skipFileList: true });  // 只切換索引

        if (!file.number) {
            this.searchResults = [];
            this.hasMoreResults = false;
            this.currentIndex = 0;
            this.coverError = `無法識別番號: ${file.filename}`;
            this._syncToCore({ skipFileList: true });
            window.SearchUI.showState('result');
            return;
        }

        if (!file.searched) {
            await this.searchForFile(file, position, showFullLoading);
        } else if (file.searchResults && file.searchResults.length > 0) {
            this.searchResults = file.searchResults;
            this.hasMoreResults = file.hasMoreResults || false;
            this.currentIndex = position === 'last' ? this.searchResults.length - 1 : 0;
            this.coverError = '';
            this._syncToCore({ skipFileList: true });

            window.SearchUI.showState('result');
        } else {
            this.searchResults = [];
            this.hasMoreResults = false;
            this.currentIndex = 0;
            this.coverError = `找不到 ${file.number} 的資料`;
            this._syncToCore({ skipFileList: true });
            window.SearchUI.showState('result');
        }
    },

    async searchForFile(file, position = 'first', showFullLoading = false) {
        this.isSearchingFile = true;
        this._syncToCore({ skipFileList: true });

        if (showFullLoading) {
            window.SearchUI.showState('loading');
            window.SearchCore.initProgress(file.number);
        } else {
            this.isSearchingFile = true;
            this.searchingFileDirection = position === 'first' ? 'next' : 'prev';
        }

        return new Promise((resolve) => {
            const eventSource = new EventSource(`/api/search/stream?q=${encodeURIComponent(file.number)}`);

            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'mode') {
                        window.SearchCore.state.currentMode = data.mode;
                        window.SearchCore.updateLog(`${window.SearchCore.MODE_TEXT[data.mode] || '搜尋'}...`);
                    }
                    else if (data.type === 'status') {
                        window.SearchCore.handleSearchStatus(data.source, data.status);
                    }
                    else if (data.type === 'result') {
                        eventSource.close();
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
                            this.coverError = '';
                            this._syncToCore();

                            // T4: File search 後查詢本地狀態
                            if (window.SearchCore?.checkLocalStatus) {
                                window.SearchCore.checkLocalStatus(this.searchResults);
                            }

                            window.SearchUI.showState('result');
                        } else {
                            file.searched = true;
                            file.searchResults = [];
                            this.coverError = `找不到 ${file.number} 的資料`;

                            // 重置共享狀態
                            this.searchResults = [];
                            this.hasMoreResults = false;
                            this.currentIndex = 0;
                            this._syncToCore();

                            window.SearchUI.showState('result');
                        }
                        resolve();
                    }
                    else if (data.type === 'error') {
                        eventSource.close();
                        this.isSearchingFile = false;
                        this.searchingFileDirection = null;
                        file.searched = true;
                        file.searchResults = [];
                        this.coverError = data.message || '搜尋失敗';

                        this.searchResults = [];
                        this.hasMoreResults = false;
                        this.currentIndex = 0;
                        this._syncToCore();

                        window.SearchUI.showState('result');
                        resolve();
                    }
                } catch (err) {
                    console.error('Parse error:', err);
                }
            };

            eventSource.onerror = () => {
                eventSource.close();
                this.isSearchingFile = false;
                this.searchingFileDirection = null;
                file.searched = true;
                file.searchResults = [];
                this.coverError = '連線錯誤，請稍後再試';

                this.searchResults = [];
                this.hasMoreResults = false;
                this.currentIndex = 0;
                this._syncToCore();

                window.SearchUI.showState('result');
                resolve();
            };
        });
    },

    switchToSearchResult(index) {
        if (index < 0 || index >= this.searchResults.length) return;
        this.currentIndex = index;
        this._syncToCore({ skipFileList: true });

        // Reset cover error on switch
        this.coverError = '';
    },

    enterNumber(index) {
        const file = this.fileList[index];
        if (!file) return;

        const number = prompt('請輸入番號（例如：T28-650）', '');
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
        this._syncToCore();

        if (this.fileList.length > 0) {
            this.switchToFile(this.currentFileIndex, 'first', false);
        }
        this.saveState();
    },

    async setFileList(paths) {
        // 呼叫過濾 API
        try {
            const resp = await fetch('/api/search/filter-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paths })
            });
            const result = await resp.json();

            if (result.success) {
                if (result.total_rejected > 0) {
                    const { extension, size, not_found } = result.rejected;
                    let msg = `已過濾 ${result.total_rejected} 個檔案`;
                    const details = [];
                    if (extension > 0) details.push(`${extension} 個非影片檔`);
                    if (size > 0) details.push(`${size} 個小於最小尺寸`);
                    if (not_found > 0) details.push(`${not_found} 個不存在`);
                    if (details.length > 0) msg += `（${details.join('、')}）`;

                    // T6b: 後端過濾提示（info 類型）
                    this.showToast(msg, 'info');
                }
                paths = result.files;
            }
        } catch (err) {
            console.error('Filter API error:', err);
        }

        // 使用後端 API 批次解析所有檔名
        const filenames = paths.map(p => p.split(/[/\\]/).pop());
        const parseResults = await window.SearchFile.parseFilenames(filenames);

        // 前端過濾：檢查能否提取番號
        const validIndices = [];
        let noNumberCount = 0;

        for (let i = 0; i < paths.length; i++) {
            const result = parseResults[i];
            if (result && result.number !== null) {
                validIndices.push(i);
            } else {
                noNumberCount++;
            }
        }

        // T6b: 前端過濾提示（warning 類型）
        if (noNumberCount > 0) {
            const msg = `已過濾 ${noNumberCount} 個無法識別番號的檔案`;
            this.showToast(msg, 'warning');
        }

        // 檢查空列表
        if (validIndices.length === 0) {
            alert('無有效影片檔案（無法識別番號）');
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
                chineseTitle: window.SearchFile.extractChineseTitle(filename, result.number),
                searchResults: [],
                hasMoreResults: false,
                searched: false
            };
        });
        this.currentFileIndex = 0;
        this.listMode = 'file';
        this.displayMode = 'detail';
        this._syncToCore();

        // 重置批次狀態
        const batch = this.batchState;
        batch.isProcessing = false;
        batch.isPaused = false;
        batch.total = 0;
        batch.processed = 0;
        batch.success = 0;
        batch.failed = 0;

        window.SearchCore.updateClearButton();

        if (this.fileList.length > 0) {
            if (this.fileList[0].number) {
                this.searchQuery = this.fileList[0].number;
            }
            await this.switchToFile(0, 'first', true);
        }
    },

    handleFileDrop(files) {
        if (!files || files.length === 0) return;

        const file = files[0];
        const filename = file.name;
        const number = window.SearchFile.extractNumber(filename);

        if (!number) {
            this.errorText = '無法從檔名識別番號';  // T6c: Alpine state
            window.SearchUI.showState('error');
            return;
        }

        this.searchQuery = number;
        this.doSearch(number);
    },

    async addFiles() {
        if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
            alert('此功能需要在桌面應用程式中使用');
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
            alert('此功能需要在桌面應用程式中使用');
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
        try {
            const resp = await fetch('/api/search/favorite-files');
            const result = await resp.json();

            if (!result.success) {
                alert(result.error || '載入失敗');
                return;
            }

            await this.setFileList(result.files);

            // 自動開始搜尋
            setTimeout(() => {
                const searchableFiles = this.fileList.filter(f => f.number && !f.searched);
                if (searchableFiles.length > 0) {
                    this.searchAll();
                }
            }, 100);

        } catch (err) {
            alert('載入失敗：' + err.message);
        } finally {
            this.isLoadingFavorite = false;
        }
    }
};
