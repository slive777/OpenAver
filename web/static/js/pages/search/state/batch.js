/**
 * SearchState - Batch Mixin
 * 包含：批次操作（searchAll, scrapeAll, scrapeSingle）
 */
import { isCloudTranslateProvider, translateAllSummary } from '../../../shared/translate-provider.js';
import { isDetailEmpty, shouldAutoJump } from '../batch-search-rules.js';
import { organizeState, skipAutoTranslate } from '../blank-card-rules.js';

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

// CD-106-5/CD-106-8: 純函式，讀 per-file selectedCandidateIndex（未設 fallback 0）
// T7: date 隨候選 raw 直通，不再正規化——picker 產生的已是合法 YYYY-MM-DD、scraper 契約
// 亦 YYYY-MM-DD（models.py:20），且新設計中有日期走唯讀 raw span、無日期才出 picker，
// 唯讀 span 顯示即整理送出值（顯示＝整理一致）。cand 為 undefined 時 `{...undefined}` → {} 安全。
// TASK-113c-T3b 立的規矩逐字是「**不能落磁碟**」，剝除只是當時**達成**它的手段
// （0.13.6 當下後端根本不讀 preview_*，連傳都不傳是最省的防線）。
//
// TASK-126（Codex PR review P2）把這兩件事分開：
//   「不落磁碟」＝ 不變式（**仍然成立且有守衛**：preview_* 進不了 NFO——generate_nfo()
//                 是具名參數；也進不了 DB——videos 表沒有這兩個欄位。
//                 由 tests/unit/test_organizer.py 的 TestT6PreviewNotPersisted 釘住）
//   「不傳遞」  ＝ 手段（**已不再需要**：後端現在有一個**刻意的**讀取點——
//                 organize_file() 拿它當 download_image 的 fallback_url，
//                 用完就丟。那不是 fail-open by accident，是有名字、有測試的用途）
//
// 為什麼一定要傳：搜尋後按「產生」是**最常走的入庫路徑**，而它的 metadata 由前端提供、
// 後端不會重新搜尋（web/routers/scraper.py）。不傳的話，被牆的使用者明明剛剛用 metatube
// 搜到了資料，按下產生卻因為原址 timeout 而拿不到封面與劇照——得改按「補齊資料」才行。
// 那違反 spec §3.2 對「存檔到片庫那一步」的承諾。
//
// ⚠️ 安全面沒有變大：`cover` / `sample_images` 本來就是前端可控且未經白名單的值
// （下載端沒有白名單，spec §1.2），preview_* 沒有新增任何攻擊面。
export function buildOrganizeMetadata(file) {
    if (!(file.searchResults?.length > 0) && file.blankCard) {
        // 空白卡：手填值原樣送出，去掉內部鍵；user_tags 取檔案層級（183-T4）
        const { _blank, _source, _coverUploadToken, _titleEdited, _chineseTitleEdited, ...rest } = file.blankCard;
        // 有上傳封面時，cover 是本機預覽網址不是可下載的 URL；整理時封面由 token 決定
        if (_coverUploadToken) { delete rest.cover; delete rest.preview_cover_url; }
        return { ...rest, user_tags: file.user_tags || [], manual_entry: true };
    }
    return { ...file.searchResults[file.selectedCandidateIndex ?? 0] };
}

export function searchStateBatch() {
    return {
    isBatchTranslating(index) {
        return batchTranslatingIndices.has(index);
    },

    _addBatchTranslatingIndex(index) {
        batchTranslatingIndices.add(index);
    },

    _deleteBatchTranslatingIndex(index) {
        batchTranslatingIndices.delete(index);
    },

    _dbSyncCoverSrc(file, fromEl) {
        // 封面身份永遠綁被整理那片自己的 metadata（CD-92b-1）；
        // 只有該片缺 cover 時才 fallback 到起點元素 src / 目前顯示片封面。
        // TASK-113c-T3b: preview_cover_url 恆為字串（Video 欄位預設 ""），空字串
        // fallback 回 cover 正是要的行為（FE-JS-01，用 || 不用 ??）。
        const own = file?.searchResults?.[0];
        const ownCover = own?.preview_cover_url || own?.cover;
        if (ownCover) {
            return `/api/proxy-image?url=${encodeURIComponent(ownCover)}`;
        }
        if (fromEl && fromEl.tagName === 'IMG' && fromEl.src) {
            return fromEl.src;
        }
        const c = this.current();
        const cover = c?.preview_cover_url || c?.cover || '';
        return cover ? `/api/proxy-image?url=${encodeURIComponent(cover)}` : '';
    },

    _isVisibleDbSyncSource(el) {
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    },

    _findDbSyncSourceEl(rowEl, index) {
        // 全域 detail/grid 封面僅在「目前顯示中的片正是被整理那片」時才可當起飛位置（CD-92b-1）；
        // 否則直接退到 rowEl 範圍內元素，避免借用別片的封面位置。
        const displaysScrapedFile = this.currentFileIndex === index;
        if (displaysScrapedFile) {
            const detailCover = this.$refs?.coverImg || document.getElementById('resultCover');
            if (this._isVisibleDbSyncSource(detailCover)) return detailCover;

            const gridImg = document.querySelector(
                `.search-grid .av-card-preview[data-slot="${this.currentIndex}"] .av-card-preview-img img`
            );
            if (this._isVisibleDbSyncSource(gridImg)) return gridImg;
        }

        const rowButton = rowEl
            ? [...rowEl.querySelectorAll('.btn-scrape-single')].find(b => b.offsetParent !== null)
            : null;
        if (this._isVisibleDbSyncSource(rowButton)) return rowButton;

        const rowIcon = rowEl?.querySelector('.file-icon');
        if (this._isVisibleDbSyncSource(rowIcon)) return rowIcon;

        return this._isVisibleDbSyncSource(rowEl) ? rowEl : null;
    },

    _pulseShowcaseLink(toEl) {
        if (!toEl) return;
        toEl.classList.remove('pulse-once');
        void toEl.offsetWidth; // force reflow
        toEl.classList.add('pulse-once');
    },

    _handleDbSyncFeedback(result, file, rowEl, index) {
        const syncStatus = result?.db_sync_status;
        if (syncStatus === 'synced') {
            const toEl = document.getElementById('sidebar-showcase-link');
            const fromEl = this._findDbSyncSourceEl(rowEl, index);
            const coverSrc = this._dbSyncCoverSrc(file, fromEl);
            if (window.GhostFly &&
                typeof window.GhostFly.playInboundFly === 'function') {
                // playInboundFly 內部分支矩陣處理缺 fromEl/toEl（缺 toEl→fallback toast、
                // 缺 fromEl→onLanding），故不再前置 fromEl && toEl guard。
                window.GhostFly.playInboundFly({
                    fromEl: fromEl,
                    coverSrc: coverSrc,
                    toEl: toEl,
                    onLanding: () => this._pulseShowcaseLink(toEl),
                    fallback: {
                        toastFn: (msg) => this.showToast(msg, 'success', 1500),
                        message: window.t('search.toast.db_synced_mobile')
                    }
                });
            } else {
                this._pulseShowcaseLink(toEl);
            }
        } else if (syncStatus === 'not_linked') {
            this.showToast(window.t('search.toast.db_not_synced'), 'info', 1500);
        } else if (syncStatus === 'failed') {
            this.showToast(window.t('search.toast.db_sync_failed'), 'warning', 2000);
        }
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
        const searchableFiles = this.fileList.filter(f => f.number && !f.searched && !f.has_nfo && !f.skipReason);
        const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0) && !f.has_nfo && !f.skipReason && organizeState(f) !== 'ready');

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

        const currentBatch = targetFiles;

        // 更新狀態
        batch.isProcessing = true;
        batch.total = currentBatch.length;
        batch.processed = 0;
        batch.success = 0;
        batch.failed = 0;
        batch.activePaths = [];
        const myRun = ++batch.runId;
        const superseded = () => myRun !== batch.runId;  // 較舊的迴圈看到號碼不同就退場，不碰 batchState

        // 182-T4: 只在按下時詳細區空白時，於第一個有結果的那一輪帶使用者過去一次
        const startFile = this.fileList[this.currentFileIndex];
        let followArmed = isDetailEmpty(startFile);
        const anchorPath = startFile?.path;

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
            // 被新批次／清單重置取代 → 不再發新工作，也不碰共享的 batchState
            if (superseded()) return;
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
                try {
                    batch.activePaths.push(file.path);
                    await this._searchFileBackground(file);
                } finally {
                    if (!superseded()) batch.activePaths = batch.activePaths.filter(p => p !== file.path);
                }

                if (superseded()) return;

                if (file.searched && file.searchResults && file.searchResults.length > 0) {
                    batch.success++;
                } else {
                    batch.failed++;
                }
                batch.processed++;
            }));

            // cleanup 在 chunk 執行中發生 → SSE 被關掉，Promise.all resolve 後檢查
            if (superseded()) return;
            if (!batch.isProcessing) { aborted = true; break; }

            // 182-T4: 只在一開始詳細區空白時跳一次（本 chunk 列表順序最前、有結果的片）；之後不再自動切片
            const jumpTarget = chunk.find(f => f.searchResults?.length > 0);
            if (jumpTarget && shouldAutoJump({ armed: followArmed, anchorPath, currentPath: this.fileList[this.currentFileIndex]?.path })) {
                followArmed = false;
                await this.switchToFile(this.fileList.indexOf(jumpTarget), 'first', false);
            }
        }

        if (superseded()) return;  // 最後一次 switchToFile 期間被取代

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
            this.showToast(window.t('search.toast.no_translatable_titles'), 'info');
            return;
        }

        ts.isProcessing = true;
        ts.isPaused = false;
        ts.total = translatableResults.length;
        ts.processed = 0;
        ts.success = 0;
        ts.failed = 0;

        const isCloud = isCloudTranslateProvider(this.appConfig?.translate?.provider);
        let aborted = false;
        let blocked = 0;
        let limited = 0;

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
                    if (data.reason === 'blocked') blocked++;
                    else if (data.reason === 'rate_limited') limited++;
                }
            } catch (err) {
                if (err.name === 'AbortError') { aborted = true; break; }  // T4.3: 離頁 abort → 結束 loop
                ts.failed++;
            }

            ts.processed++;

            if (isCloud && ts.processed < ts.total) {
                await new Promise(resolve => setTimeout(resolve, 300));
            }
        }

        this._clearAbort('translateAll');  // T4.3: 清除 registry（與其他 fetch 的 finally 一致）
        ts.isProcessing = false;
        ts.isPaused = false;
        if (!aborted) {  // T4.3: abort 時不顯示 toast（DOM 可能已不可用）
            this.showToast(translateAllSummary((k, p) => window.t(k, p), { success: ts.success, failed: ts.failed, blocked, limited }), ts.failed > 0 ? 'warning' : 'success');
        }
        ts.total = 0;
    },

    async scrapeAll() {
        // CD-106-5 snapshot 點 (2)：整理觸發時存目前檢視檔的候選 index（迴圈前，僅一次）
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            this.fileList[this.currentFileIndex].selectedCandidateIndex = this.currentIndex;
        }

        const scrapableFiles = this.fileList.filter(f => organizeState(f) === 'ready' && !f.scraped);
        // 只填標題、沒番號的檔不整理；整批只彙整成一則提示
        const needsNumberFiles = this.fileList.filter(f => organizeState(f) === 'needs_number' && !f.scraped);

        if (scrapableFiles.length === 0) {
            if (needsNumberFiles.length > 0) {
                this.showToast(window.t('search.toast.number_required'), 'info');
            } else {
                this.showToast(window.t('search.toast.no_scrapable_files'), 'info');
            }
            return;
        }
        if (needsNumberFiles.length > 0) {
            this.showToast(window.t('search.toast.number_required'), 'info');
        }

        this.isScrapeAllProcessing = true;

        // T2b: 初始化 scrape progress
        this.scrapeProgress.total = scrapableFiles.length;
        this.scrapeProgress.processed = 0;
        this.scrapeProgress.isProcessing = true;

        // 重設 progress bar 初始寬度（GSAP 上次殘留的 inline style）
        this.$nextTick(() => {
            const barEl = document.getElementById('scrapeProgressBar');
            if (barEl) barEl.style.width = '0%';
        });

        let successCount = 0;
        let failCount = 0;
        let duplicateCount = 0;

        for (const file of scrapableFiles) {
            // 批次進行中使用者可能清掉後面某張空白卡的標題／番號：輪到時再判一次，不再可整理就不送出
            if (organizeState(file) !== 'ready') {
                this.scrapeProgress.processed++;
                continue;
            }
            const index = this.fileList.indexOf(file);
            let dbSyncResult = null;

            this.currentFileIndex = index;
            this.searchResults = file.searchResults;
            // Codex PR#115 P3：顯示要與「實際整理的候選」一致，避免批次時卡片顯示第一個來源、
            // 後端卻整理另一個來源（buildOrganizeMetadata 用 selectedCandidateIndex）。界限保護
            // 防越界（selectedCandidateIndex 在 T2' loadMore 硬關＋fresh-baseline 後恆在界內，
            // 此 clamp 為防禦性；scrapableFiles 已濾掉空 searchResults，length ≥ 1）。
            this.currentIndex = Math.max(0, Math.min(file.selectedCandidateIndex ?? 0, file.searchResults.length - 1));
            this._resetCoverState();

            const metadata = { ...buildOrganizeMetadata(file) };

            // Set per-file scraping status
            file.isScraping = true;

            try {
                const chineseFromFile = file.chineseTitle;
                const appConfig = this.appConfig;
                if (appConfig?.translate?.enabled && !chineseFromFile &&
                    metadata.title && this.hasJapanese(metadata.title) && !skipAutoTranslate(metadata)) {
                    const tr = await this.translateWithOllama(metadata.title, 'translate', metadata);
                    if (tr.success) metadata.translated_title = tr.result;
                }

                const result = await window.SearchFile.scrapeFile(file, metadata);
                if (result.duplicate) {
                    file.scrapeStatus = 'duplicate';
                    file.duplicateTarget = result.duplicate_target || '';
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
                    dbSyncResult = result;
                    file.scraped = true;
                    file.scrapeStatus = 'done';
                    successCount++;
                    // 新增：fallback 提示
                    if (result.used_fallbacks?.length) {
                        const fields = result.used_fallbacks.join('、');
                        this.showToast(window.t('search.toast.fields_defaulted', { fields }), 'warning');
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
                        this._handleDbSyncFeedback(dbSyncResult, file, rowEl, index);
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
        const state = file ? organizeState(file) : 'none';
        if (state === 'needs_number') {
            this.showToast(window.t('search.toast.number_required'), 'info');
            return;
        }
        if (state !== 'ready') {
            this.showToast(window.t('search.toast.no_search_results'), 'info');
            return;
        }

        // CD-106-5 snapshot 點 (2)：LOAD-BEARING — 用 this.currentFileIndex（目前檢視檔），
        // 絕不是參數 index（per-row @click.stop 不會先切到該 row，index 可能是別的檔）
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            this.fileList[this.currentFileIndex].selectedCandidateIndex = this.currentIndex;
        }

        const metadata = { ...buildOrganizeMetadata(file) };

        file.isScraping = true;
        file.scrapeStatus = null;

        try {
            const chineseFromFile = file.chineseTitle;
            const appConfig = this.appConfig;
            if (appConfig?.translate?.enabled && !chineseFromFile &&
                metadata.title && this.hasJapanese(metadata.title) && !skipAutoTranslate(metadata)) {
                const tr = await this.translateWithOllama(metadata.title, 'translate', metadata);
                if (tr.success) metadata.translated_title = tr.result;
            }

            const result = await window.SearchFile.scrapeFile(file, metadata);
            if (result.duplicate) {
                this.duplicateTarget = result.duplicate_target || '';
                this.duplicateModalOpen = true;
                file.scrapeStatus = 'duplicate';
                // 122-T6：單片路徑也要把 target 寫進 file 物件。這條路本來就會設
                // scrapeStatus='duplicate'，而 T6 讓列表對這個值長出持久標記——
                // 只寫單例 this.duplicateTarget 的話，使用者關掉彈窗後再點那顆標記，
                // 讀到的是 undefined（單例已被 closeDuplicateModal 清空），彈窗會直接
                // 顯示「undefined」而不是檔名。兩條路寫同一個欄位才對稱。
                file.duplicateTarget = result.duplicate_target || '';
                file.isScraping = false;
                return;
            }
            if (result.success) {
                file.scraped = true;
                file.scrapeStatus = 'done';
                // 新增：fallback 提示
                if (result.used_fallbacks?.length) {
                    const fields = result.used_fallbacks.join('、');
                    this.showToast(window.t('search.toast.fields_defaulted', { fields }), 'warning');
                }
                // 動畫：成功 pop-in + row flash
                this.$nextTick(() => {
                    const rows = document.querySelectorAll('#fileList .file-item');
                    const rowEl = rows[index];
                    if (!rowEl) return;
                    const btn = [...rowEl.querySelectorAll('.btn-scrape-single')]
                        .find(b => b.offsetParent !== null);
                    window.SearchAnimations?.playOrganizeSuccess?.(btn, rowEl);
                    this._handleDbSyncFeedback(result, file, rowEl, index);
                });
            } else {
                console.error('[Scrape]', file.filename, result.error);
                const message = result.error
                    ? window.t('search.toast.scrape_failed_reason', { filename: file.filename, reason: result.error })
                    : window.t('search.toast.scrape_failed', { filename: file.filename });
                this.showToast(message, 'error');
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
}
