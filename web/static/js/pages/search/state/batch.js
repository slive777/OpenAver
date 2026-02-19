/**
 * SearchState - Batch Mixin
 * 包含：批次操作（searchAll, scrapeAll, scrapeSingle）
 */
window.SearchStateMixin_Batch = {
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
            alert('沒有需要搜尋的檔案');
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
        for (let i = 0; i < currentBatch.length; i += concurrency) {
            // 支援暫停
            if (batch.isPaused) {
                await new Promise(resolve => {
                    const checkInterval = setInterval(() => {
                        if (!batch.isPaused) {
                            clearInterval(checkInterval);
                            resolve();
                        }
                    }, 100);
                });
            }

            const chunk = currentBatch.slice(i, Math.min(i + concurrency, currentBatch.length));

            // 並行處理這一組
            await Promise.all(chunk.map(async (file) => {
                const index = this.fileList.indexOf(file);
                await this.switchToFile(index, 'first', false);

                if (file.searched && file.searchResults && file.searchResults.length > 0) {
                    batch.success++;
                } else {
                    batch.failed++;
                }

                batch.processed++;
            }));
        }

        // 批次處理完成
        this.isSearchingFile = false;
        this._syncToCore();
        batch.isProcessing = false;
        batch.isPaused = false;

        // 顯示完成統計
        const totalProcessed = batch.success + batch.failed;
        alert(`批次搜尋完成！\n成功: ${batch.success}\n失敗: ${batch.failed}`);

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
            r => r.title && window.SearchCore.hasJapanese(r.title) && !r.translated_title
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

        for (const result of translatableResults) {
            if (ts.isPaused) {
                await new Promise(resolve => {
                    const checkInterval = setInterval(() => {
                        if (!ts.isPaused) {
                            clearInterval(checkInterval);
                            resolve();
                        }
                    }, 100);
                });
            }

            try {
                const response = await fetch('/api/translate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: result.title,
                        mode: 'translate',
                        actors: result.actors,
                        number: result.number
                    })
                });
                const data = await response.json();
                if (data.success && data.result && !data.skipped) {
                    result.translated_title = data.result;
                    ts.success++;
                } else {
                    ts.failed++;
                }
            } catch (err) {
                ts.failed++;
            }

            ts.processed++;

            if (isGemini && ts.processed < ts.total) {
                await new Promise(resolve => setTimeout(resolve, 300));
            }
        }

        ts.isProcessing = false;
        ts.isPaused = false;
        this.showToast(`翻譯完成：成功 ${ts.success}，失敗 ${ts.failed}`, ts.failed > 0 ? 'warning' : 'success');
        ts.total = 0;
    },

    async scrapeAll() {
        const scrapableFiles = this.fileList.filter(f =>
            f.searched && f.searchResults && f.searchResults.length > 0 && !f.scraped
        );

        if (scrapableFiles.length === 0) {
            alert('沒有可處理的檔案');
            return;
        }

        this.isScrapeAllProcessing = true;

        let successCount = 0;
        let failCount = 0;
        let duplicateCount = 0;

        for (const file of scrapableFiles) {
            const index = this.fileList.indexOf(file);

            this.currentFileIndex = index;
            this.searchResults = file.searchResults;
            this.currentIndex = 0;
            this.coverError = '';
            this._syncToCore({ skipFileList: true });  // scrape 迴圈中，fileList 不變

            const metadata = { ...file.searchResults[0] };

            // Set per-file scraping status
            file.isScraping = true;

            try {
                const chineseFromFile = file.chineseTitle;
                const appConfig = this.appConfig;
                if (appConfig?.translate?.enabled && !chineseFromFile &&
                    metadata.title && window.SearchCore.hasJapanese(metadata.title)) {
                    const tr = await window.SearchCore.translateWithOllama(metadata.title, 'translate', metadata);
                    if (tr.success) metadata.translated_title = tr.result;
                }

                const result = await window.SearchFile.scrapeFile(file, metadata);
                if (result.duplicate) {
                    file.scrapeStatus = 'duplicate';
                    file.isScraping = false;  // 必須清除，否則 spinner 永遠轉（L144 的清除被 continue 跳過）
                    duplicateCount++;
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
        }

        this.isScrapeAllProcessing = false;

        alert(`批次處理完成！\n成功: ${successCount}\n失敗: ${failCount}` +
            (duplicateCount ? `\n重複: ${duplicateCount}（請到設定 → 版本標記）` : ''));
    },

    async scrapeSingle(index) {
        const file = this.fileList[index];
        if (!file || !file.searchResults || file.searchResults.length === 0) {
            alert('此檔案沒有搜尋結果');
            return;
        }

        const metadata = { ...file.searchResults[0] };

        file.isScraping = true;
        file.scrapeStatus = null;

        try {
            const chineseFromFile = file.chineseTitle;
            const appConfig = this.appConfig;
            if (appConfig?.translate?.enabled && !chineseFromFile &&
                metadata.title && window.SearchCore.hasJapanese(metadata.title)) {
                const tr = await window.SearchCore.translateWithOllama(metadata.title, 'translate', metadata);
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
            } else {
                alert(`${file.filename} 處理失敗: ${result.error || '未知錯誤'}`);
                file.scrapeStatus = 'failed';
            }
        } catch (err) {
            alert(`${file.filename} 處理失敗: ${err.message}`);
            file.scrapeStatus = 'failed';
        }

        file.isScraping = false;
    }
};
