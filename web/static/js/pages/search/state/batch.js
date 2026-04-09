/**
 * SearchState - Batch Mixin
 * 包含：批次操作（searchAll, scrapeAll, scrapeSingle）
 */

// T4: 追蹤正在批次翻譯的片索引（從 core.js 搬移）
const batchTranslatingIndices = new Set();

/**
 * 批次翻譯（調用 /api/translate-batch）— 從 core.js 搬移
 * @param {Array<string>} titles - 日文標題列表
 * @returns {Promise<Array<string>>} 繁體中文翻譯列表
 */
async function translateBatchHelper(titles) {
    try {
        const resp = await fetch('/api/translate-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                titles: titles,
                batch_size: 1
            })
        });

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }

        const data = await resp.json();
        return data.translations || [];

    } catch (error) {
        console.error('[Progressive] 批次翻譯失敗:', error);
        return [];
    }
}

window.SearchStateMixin_Batch = {
    isBatchTranslating(index) {
        return batchTranslatingIndices.has(index);
    },

    _addBatchTranslatingIndex(index) {
        batchTranslatingIndices.add(index);
    },

    _deleteBatchTranslatingIndex(index) {
        batchTranslatingIndices.delete(index);
    },

    async translateBatch(titles) {
        return translateBatchHelper(titles);
    },

    async translateWithOllama(text, mode, metadata = {}) {
        try {
            const resp = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    mode: mode,
                    actors: metadata.actors || [],
                    number: metadata.number || ''
                })
            });
            return await resp.json();
        } catch (e) {
            return { success: false, error: e.message };
        }
    },


    async searchAll() {
        const batch = this.batchState;

        // 繼續模式：從暫停中恢復
        if (batch.isPaused) {
            batch.isPaused = false;
            return;
        }

        // 暫停模式：切換為暫停狀態
        if (batch.isProcessing) {
            batch.isPaused = true;
            return;
        }

        // === 新的批次開始 ===
        const searchableFiles = this.fileList.filter(f => f.number && !f.searched);
        const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0));

        let targetFiles;
        if (searchableFiles.length > 0) {
            targetFiles = searchableFiles;
        } else if (failedFiles.length > 0) {
            // 重試失敗：重置 searched 狀態
            failedFiles.forEach(f => { f.searched = false; f.searchResults = []; });
            targetFiles = failedFiles;
        } else {
            this.showToast(window.t('search.toast.no_searchable_files'), 'info');
            return;
        }

        const currentBatch = targetFiles.slice(0, batch.batchSize);

        // 更新狀態
        batch.isProcessing = true;
        batch.total = currentBatch.length;
        batch.processed = 0;
        batch.success = 0;
        batch.failed = 0;

        // 並行處理，一次 2 個
        const concurrency = 2;
        let aborted = false;
        for (let i = 0; i < currentBatch.length; i += concurrency) {
            // 支援暫停
            if (batch.isPaused) {
                await new Promise(resolve => {
                    this._batchCheckInterval = setInterval(() => {
                        if (!batch.isPaused) {
                            clearInterval(this._batchCheckInterval);
                            this._batchCheckInterval = null;
                            resolve();
                        }
                    }, 100);
                });
            }
            // cleanup 已設 isProcessing=false → 中斷 loop，不繼續發新工作
            if (!batch.isProcessing) { aborted = true; break; }

            const chunk = currentBatch.slice(i, Math.min(i + concurrency, currentBatch.length));

            // U10b fix: 當前顯示的 file 在 chunk 中 → 預清理 cover state
            // 防止 _searchFileBackground 寫入 file.searchResults 觸發 Alpine 被動更新時 cover 狀態不一致
            if (this.listMode === 'file') {
                const currentFile = this.fileList[this.currentFileIndex];
                if (currentFile && chunk.includes(currentFile) && !currentFile.searched) {
                    this._resetCoverState();
                }
            }

            // U10b: 背景搜尋（不碰共享 UI 狀態）
            await Promise.all(chunk.map(async (file) => {
                await this._searchFileBackground(file);

                if (file.searched && file.searchResults && file.searchResults.length > 0) {
                    batch.success++;
                } else {
                    batch.failed++;
                }
                batch.processed++;
            }));

            // cleanup 在 chunk 執行中發生 → SSE 被關掉，Promise.all resolve 後檢查
            if (!batch.isProcessing) { aborted = true; break; }

            // U10b: chunk 完成後，將 UI 指向最後一個搜到結果的 file（序列化 UI 更新）
            const lastSuccessFile = [...chunk].reverse().find(f => f.searchResults?.length > 0);
            if (lastSuccessFile) {
                const lastIdx = this.fileList.indexOf(lastSuccessFile);
                await this.switchToFile(lastIdx, 'first', false);
            }
        }

        // 批次處理完成
        this.isSearchingFile = false;
        batch.isProcessing = false;
        batch.isPaused = false;

        // 顯示完成統計（cleanup 中斷時不顯示）
        if (!aborted) {
            const type = (batch.failed > 0) ? 'warning' : 'success';
            this.showToast(window.t('search.toast.search_complete', { success: batch.success, failed: batch.failed }), type, 4000);
        }

        // 重置 total
        batch.total = 0;
    },

    async translateAll() {
        const ts = this.translateState;

        if (ts.isPaused) {
            ts.isPaused = false;
            return;
        }

        if (ts.isProcessing) {
            ts.isPaused = true;
            return;
        }

        const translatableResults = this.searchResults.filter(
            r => r.title && this.hasJapanese(r.title) && !r.translated_title
        );

        if (translatableResults.length === 0) {
            this.showToast('沒有需要翻譯的標題', 'info');
            return;
        }

        ts.isProcessing = true;
        ts.isPaused = false;
        ts.total = translatableResults.length;
        ts.processed = 0;
        ts.success = 0;
        ts.failed = 0;

        const isGemini = this.appConfig?.translate?.provider === 'gemini';
        let aborted = false;

        for (const result of translatableResults) {
            if (ts.isPaused) {
                await new Promise(resolve => {
                    this._translateCheckInterval = setInterval(() => {
                        if (!ts.isPaused) {
                            clearInterval(this._translateCheckInterval);
                            this._translateCheckInterval = null;
                            resolve();
                        }
                    }, 100);
                });
            }
            // cleanup 已設 isProcessing=false → 中斷 loop，不繼續發新 fetch
            if (!ts.isProcessing) { aborted = true; break; }

            try {
                const response = await fetch('/api/translate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: result.title,
                        mode: 'translate',
                        actors: result.actors,
                        number: result.number
                    }),
                    signal: this._getAbortSignal('translateAll')  // T4.3
                });
                const data = await response.json();
                if (data.success && data.result && !data.skipped) {
                    result.translated_title = data.result;
                    ts.success++;
                } else {
                    ts.failed++;
                }
            } catch (err) {
                if (err.name === 'AbortError') { aborted = true; break; }  // T4.3: 離頁 abort → 結束 loop
                ts.failed++;
            }

            ts.processed++;

            if (isGemini && ts.processed < ts.total) {
                await new Promise(resolve => setTimeout(resolve, 300));
            }
        }

        this._clearAbort('translateAll');  // T4.3: 清除 registry（與其他 fetch 的 finally 一致）
        ts.isProcessing = false;
        ts.isPaused = false;
        if (!aborted) {  // T4.3: abort 時不顯示 toast（DOM 可能已不可用）
            this.showToast(`翻譯完成：成功 ${ts.success}，失敗 ${ts.failed}`, ts.failed > 0 ? 'warning' : 'success');
        }
        ts.total = 0;
    },

    async scrapeAll() {
        const scrapableFiles = this.fileList.filter(f =>
            f.searched && f.searchResults && f.searchResults.length > 0 && !f.scraped
        );

        if (scrapableFiles.length === 0) {
            this.showToast(window.t('search.toast.no_scrapable_files'), 'info');
            return;
        }

        this.isScrapeAllProcessing = true;

        // T2b: 初始化 scrape progress
        this.scrapeProgress.total = scrapableFiles.length;
        this.scrapeProgress.processed = 0;
        this.scrapeProgress.isProcessing = true;

        let successCount = 0;
        let failCount = 0;
        let duplicateCount = 0;

        for (const file of scrapableFiles) {
            const index = this.fileList.indexOf(file);

            this.currentFileIndex = index;
            this.searchResults = file.searchResults;
            this.currentIndex = 0;
            this._resetCoverState();

            const metadata = { ...file.searchResults[0] };

            // Set per-file scraping status
            file.isScraping = true;

            try {
                const chineseFromFile = file.chineseTitle;
                const appConfig = this.appConfig;
                if (appConfig?.translate?.enabled && !chineseFromFile &&
                    metadata.title && this.hasJapanese(metadata.title)) {
                    const tr = await this.translateWithOllama(metadata.title, 'translate', metadata);
                    if (tr.success) metadata.translated_title = tr.result;
                }

                const result = await window.SearchFile.scrapeFile(file, metadata);
                if (result.duplicate) {
                    file.scrapeStatus = 'duplicate';
                    file.isScraping = false;  // 必須清除，否則 spinner 永遠轉（L144 的清除被 continue 跳過）
                    duplicateCount++;
                    // T2b: duplicate 仍算已處理（不播動畫）
                    this.scrapeProgress.processed++;
                    const dupePercent = this.scrapePercent();
                    this.$nextTick(() => {
                        const barEl = document.getElementById('scrapeProgressBar');
                        window.SearchAnimations?.playProgressUpdate?.(barEl, dupePercent);
                    });
                    continue;
                }
                if (result.success) {
                    file.scraped = true;
                    file.scrapeStatus = 'done';
                    successCount++;
                    // 新增：fallback 提示
                    if (result.used_fallbacks?.length) {
                        const fields = result.used_fallbacks.join('、');
                        this.showToast(`⚠️ ${fields} 資訊未取得，已使用預設值`, 'warning');
                    }
                } else {
                    file.scrapeStatus = 'failed';
                    failCount++;
                }
            } catch (err) {
                file.scrapeStatus = 'failed';
                failCount++;
            }

            file.isScraping = false;

            // T2b: 每輪完成後更新進度條 + per-file row 動畫
            this.scrapeProgress.processed++;
            const percent = this.scrapePercent();
            this.$nextTick(() => {
                const barEl = document.getElementById('scrapeProgressBar');
                window.SearchAnimations?.playProgressUpdate?.(barEl, percent);
                // per-file row 動畫（複用 T2a）
                const rows = document.querySelectorAll('#fileList .file-item');
                const rowEl = rows[this.fileList.indexOf(file)];
                if (rowEl) {
                    const btn = [...rowEl.querySelectorAll('.btn-scrape-single')]
                        .find(b => b.offsetParent !== null);
                    if (file.scrapeStatus === 'done') {
                        window.SearchAnimations?.playOrganizeSuccess?.(btn, rowEl);
                    } else if (file.scrapeStatus === 'failed') {
                        window.SearchAnimations?.playOrganizeFail?.(btn);
                    }
                    // duplicate：不播動畫（已在 duplicate 路徑處理）
                }
            });
        }

        this.isScrapeAllProcessing = false;
        this.scrapeProgress.isProcessing = false;

        const scrapeType = (failCount > 0) ? 'warning' : 'success';
        if (duplicateCount > 0) {
            this.showToast(window.t('search.toast.scrape_complete_dup', { success: successCount, failed: failCount, duplicate: duplicateCount }), scrapeType, 4000);
        } else {
            this.showToast(window.t('search.toast.scrape_complete', { success: successCount, failed: failCount }), scrapeType, 4000);
        }
    },

    async scrapeSingle(index) {
        const file = this.fileList[index];
        if (!file || !file.searchResults || file.searchResults.length === 0) {
            this.showToast(window.t('search.toast.no_search_results'), 'info');
            return;
        }

        const metadata = { ...file.searchResults[0] };

        file.isScraping = true;
        file.scrapeStatus = null;

        try {
            const chineseFromFile = file.chineseTitle;
            const appConfig = this.appConfig;
            if (appConfig?.translate?.enabled && !chineseFromFile &&
                metadata.title && this.hasJapanese(metadata.title)) {
                const tr = await this.translateWithOllama(metadata.title, 'translate', metadata);
                if (tr.success) metadata.translated_title = tr.result;
            }

            const result = await window.SearchFile.scrapeFile(file, metadata);
            if (result.duplicate) {
                this.duplicateTarget = result.duplicate_target || '';
                this.duplicateModalOpen = true;
                file.scrapeStatus = 'duplicate';
                file.isScraping = false;
                return;
            }
            if (result.success) {
                file.scraped = true;
                file.scrapeStatus = 'done';
                // 新增：fallback 提示
                if (result.used_fallbacks?.length) {
                    const fields = result.used_fallbacks.join('、');
                    this.showToast(`⚠️ ${fields} 資訊未取得，已使用預設值`, 'warning');
                }
                // 動畫：成功 pop-in + row flash
                this.$nextTick(() => {
                    const rows = document.querySelectorAll('#fileList .file-item');
                    const rowEl = rows[index];
                    if (!rowEl) return;
                    const btn = [...rowEl.querySelectorAll('.btn-scrape-single')]
                        .find(b => b.offsetParent !== null);
                    window.SearchAnimations?.playOrganizeSuccess?.(btn, rowEl);
                });
            } else {
                console.error('[Scrape]', file.filename, result.error);
                this.showToast(window.t('search.toast.scrape_failed', { filename: file.filename }), 'error');
                file.scrapeStatus = 'failed';
                // 動畫：失敗 shake
                this.$nextTick(() => {
                    const rows = document.querySelectorAll('#fileList .file-item');
                    const rowEl = rows[index];
                    if (!rowEl) return;
                    const btn = [...rowEl.querySelectorAll('.btn-scrape-single')]
                        .find(b => b.offsetParent !== null);
                    window.SearchAnimations?.playOrganizeFail?.(btn);
                });
            }
        } catch (err) {
            console.error('[Scrape]', file.filename, err);
            this.showToast(window.t('search.toast.scrape_failed', { filename: file.filename }), 'error');
            file.scrapeStatus = 'failed';
            // 動畫：失敗 shake
            this.$nextTick(() => {
                const rows = document.querySelectorAll('#fileList .file-item');
                const rowEl = rows[index];
                if (!rowEl) return;
                const btn = [...rowEl.querySelectorAll('.btn-scrape-single')]
                    .find(b => b.offsetParent !== null);
                window.SearchAnimations?.playOrganizeFail?.(btn);
            });
        }

        file.isScraping = false;
    }
};
