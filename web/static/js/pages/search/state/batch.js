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
        const coreState = window.SearchCore.state;
        coreState.isSearchingFile = false;
        batch.isProcessing = false;
        batch.isPaused = false;

        // 顯示完成統計
        const totalProcessed = batch.success + batch.failed;
        alert(`批次搜尋完成！\n成功: ${batch.success}\n失敗: ${batch.failed}`);

        // 重置 total
        batch.total = 0;
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

        for (const file of scrapableFiles) {
            const index = this.fileList.indexOf(file);

            this.currentFileIndex = index;
            this.searchResults = file.searchResults;
            this.currentIndex = 0;
            this.coverError = '';

            // 同步到 core.js
            const coreState = window.SearchCore.state;
            coreState.currentFileIndex = index;
            coreState.searchResults = this.searchResults;
            coreState.currentIndex = 0;

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
                if (result.success) {
                    file.scraped = true;
                    file.scrapeStatus = 'done';
                    successCount++;
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

        alert(`批次處理完成！\n成功: ${successCount}\n失敗: ${failCount}`);
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
            if (result.success) {
                file.scraped = true;
                file.scrapeStatus = 'done';
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
