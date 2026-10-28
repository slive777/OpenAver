/**
 * SearchState - Base Mixin
 * 包含：data 初始值、constants、computed methods、file list helpers
 */
import { isFileSearching as isPathSearching } from '../batch-search-rules.js';

export function searchStateBase() {
    return {
        // ===== Page State =====
        pageState: 'empty',  // 'empty' | 'loading' | 'result' | 'error'

        // ===== Search Results State =====
        searchResults: [],
        currentIndex: 0,
        currentQuery: '',
        currentMaker: null,  // 173 CD-173-9：null | {key, label, spellings}；只經 activeMaker() 讀（惰性靠 currentMode==='maker'）
        currentCursor: null,  // 175d CD-175d-11：null | string；後端給的不透明續頁 token，只存、只送（loadMore）、不解析
        searchQuery: '',  // V1c: 對應 input 即時輸入值（x-model 綁定）
        currentOffset: 0,
        hasMoreResults: false,
        isLoadingMore: false,
        isSearchingFile: false,

        // ===== Stream 狀態（T4：actress/prefix 漸進流入） =====
        streamSlots: [],          // seed 番號列表 ['SSIS-816', 'SSIS-815', ...]
        streamComplete: false,    // result-complete 已收到
        isStreaming: false,       // seed 收到 ~ result-complete 收到期間為 true

        // ===== U2: Staging Buffer State（batching 用） =====
        streamBuffer: [],        // 待 burst 的 result-item 暫存（{slot, data}[]）
        streamBurstTimer: null,  // 時間窗口 timer ID（原生 setTimeout 回傳值）
        streamBurstedSlots: [],  // 已 burst 到 grid 的 slot index（boolean array，長度與 streamSlots 一致）
        stagingVisible: false,   // staging 容器可見性（獨立於 isStreaming）
        // isStreaming 在 result-complete 後立即 false，
        // 但 stagingVisible 等 exit morph onComplete 才 false

        // ===== U3: Staging Card 顯示 State（裝飾性，C16） =====
        stagingCover: '',           // staging card 封面 URL（最新到達的 result-item）
        stagingNumber: '',          // staging card 番號（最新到達的 result-item）
        stagingReceivedCount: 0,    // staging card 已收到計數（badge 用）
        _coverSwapTimer: null,      // cover swap debounce timer ID（C20 約束）
        _stagingCardWidth: 0,       // seed 時預量的 grid card 寬度（staging 首次顯示同步用）

        // ===== File List State =====
        fileList: [],
        currentFileIndex: 0,
        listMode: null,  // 'file' | 'search' | 'wishlist' | null

        // ===== Batch State =====
        batchState: {
            isProcessing: false,
            isPaused: false,
            total: 0,
            processed: 0,
            success: 0,
            failed: 0,
            activePaths: [],  // 正在搜尋中的 file.path（不持久化，見 CD-182-6）
            runId: 0          // searchAll 世代號：新批次開始／setFileList 重置時遞增，舊迴圈比對後自行退場（不持久化）
        },

        // ===== Translate State =====
        translateState: {
            isProcessing: false,
            isPaused: false,
            total: 0,
            processed: 0,
            success: 0,
            failed: 0,
        },

        // ===== App Config =====
        appConfig: null,
        formatVariables: [],          // SSOT: /api/config/format-variables（CD-146a-17）
        favoriteScannerLinked: null,  // null=尚未查或未設定最愛資料夾／true/false=既有端點回的 linked（CD-146a-14）

        // ===== Translation State =====
        isTranslating: false,

        // ===== T1c: Edit State =====
        editingTitle: false,
        editedTitleValue: '',
        editingChineseTitle: false,
        editedChineseTitleValue: '',
        editingActors: false,
        editedActorsValue: '',
        // TASK-183-T2：空白結果卡的番號／片商行內編輯（與 title 三件組同形）
        editingNumber: false,
        editedNumberValue: '',
        editingMaker: false,
        editedMakerValue: '',
        // TASK-106 Option C Part 1: 編輯開啟當下捕獲的候選物件參照（identity guard）。
        // confirmEditTitle/confirmEditChineseTitle/confirmEditActors 開頭都拿 this.current()
        // 與各自欄位比對，不同即代表 current() 已換到別的候選/檔——不管是被 navigate/switchToFile/
        // scrapeAll/grid/lightbox 或任何未來新增的路徑移動的，一律擋下寫入。這是本重構的唯一
        // 權威保證（見 persistence.js setupAutoSave 的 $watch，那層只是 UX 便利、非保證）。
        //
        // Codex PR#115 P2 fix：三個欄位獨立，不共用單一 `_editSourceCandidate`——title/
        // chinese/actor 三個 editingX 各自獨立、可同時開啟；若共用一個欄位，後開啟的編輯器
        // 會覆蓋先開啟者捕獲的來源，讓先開啟者的 guard 誤判「候選未換」而把已經 stale 的
        // 內容寫進後開啟者當下的候選（data pollution）。
        _editSourceTitle: null,
        _editSourceChineseTitle: null,
        _editSourceActors: null,
        _editSourceNumber: null,
        _editSourceMaker: null,
        // TASK-106 Codex PR#116 P2: date picker 的 stale-candidate 身分守衛捕獲欄位（與
        // title/chineseTitle/actors 同源 pattern，見上方 Codex PR#115 P2 段落理由）。
        _editSourceDate: null,
        // TASK-106 Codex PR#116 P2: 候選「原地替換」計數器（換源 / switch-source 流程）。
        // 換源時整顆替換 current() 候選物件（arr[idx] = variant），但 path / currentIndex /
        // listMode / length 全都不變 → pendingEditWatchKey 前四段字串不變 → _resetPendingEdits
        // 不觸發 → stale 編輯框留著。此計數器在每個原地替換點遞增，pendingEditWatchKey 併入尾段，
        // 讓哨兵偵測到「同 path/index/length 但候選被換掉」→ 關掉 stale 編輯框。
        // 短暫 UI 訊號（同 editingX 性質）：不寫進 saveState / snapshot / restoreState（不持久化）。
        _candidateReplaceSeq: 0,
        addingTag: false,
        newTagValue: '',
        coverError: '',
        _coverRetried: false,
        _coverRequestId: 0,
        _coverLoaded: false,
        // ===== Fix-1: Duplicate State =====
        duplicateTarget: '',  // duplicate modal 顯示的目標檔名
        duplicateModalOpen: false,  // Alpine state for duplicate modal
        errorText: '',  // T6c: Error message state
        errorKind: '',  // CD-146a-20: error classification for conditional UI

        _timers: {},  // Timer registry：{ [key: string]: number }（setTimeout ID）
        _batchCheckInterval: null,      // T1(40b): batch searchAll 暫停等待 interval ref
        _translateCheckInterval: null,  // T1(40b): translateAll 暫停等待 interval ref
        _pywebviewFilesHandler: null,  // T2(40b): pywebview-files listener ref
        _resizeHandler: null,          // T2(40b): resize listener ref
        _abortControllers: {},  // Fetch AbortController registry：{ [key: string]: AbortController }（T4.3）

        // ===== T1d: File List State =====
        dragActive: false,
        isLoadingFavorite: false,
        searchingFileDirection: null,  // 'next' | 'prev' — for searchForFile btn spinner
        isScrapeAllProcessing: false,  // scrapeAll spinner

        // ===== T2b: Scrape Progress State =====
        scrapeProgress: {
            processed: 0,
            total: 0,
            isProcessing: false
        },

        // ===== V1d: Source Switching State =====
        isSwitchingSource: false,      // 切換來源中（控制 spinner + disabled）
        switchSourceShake: false,      // 觸發抖動動畫（無其他版本時）

        // ===== Progress State =====
        currentMode: '',
        progressLog: '',
        detailDone: 0,
        detailTotal: 0,

        // ===== Search State Machine =====
        requestId: 0,              // 搜尋請求計數器（防競態）
        activeEventSource: null,   // 當前 SSE 連線
        _activeConnections: [],    // Array<EventSource> — 追蹤所有進行中的 SSE 連線
        _searchSnapshot: null,     // cancelSearch 用的狀態快照

        // ===== T8: Sample Gallery State =====
        sampleGalleryOpen: false,
        sampleGalleryImages: [],
        sampleGalleryIndex: 0,
        _sgTouchStartX: null,
        _lbTouchStartX: null,
        _lbTouchStartY: null,
        _dtTouchStartX: null,
        _dtTouchStartY: null,
        _sgAnimating: false,
        _sgGeneration: 0,

        // ===== T2a: Display Mode State =====
        displayMode: 'detail',     // 'detail' | 'grid'
        lightboxOpen: false,       // Lightbox 顯示狀態
        lightboxIndex: 0,          // Lightbox 當前索引（-1 = 女優頭像）
        _lightboxAnimating: false, // D2: Lightbox 動畫進行中 guard
        _lightboxGeneration: 0,    // B19: invalidation token for deferred $nextTick lightbox callbacks
        lightboxCloseTimer: null,  // F2: delayed clear timer for lightbox close

        // ===== T2d: Actress Profile State =====
        actressProfile: null,      // { name, img, backdrop, birth, age, height, cup, bust, waist, hip, hometown, hobby, is_favorite }

        // ===== T5: Actress Favorite State =====
        _actressFavoriteLoading: false,
        _actressFavoriteGen: 0,
        _actressFavoriteTimer: null,

        // ===== Phase 43 T6: Actress Chips Expanded State =====
        _actressChipsExpanded: { aliases: false, info: false },

        // ===== T6a: Grid Image Error State =====
        // Grid 模式圖片錯誤追蹤
        _gridImageErrors: new Set(),

        // ===== A6-1: Hero Card / Lightbox 圖片錯誤追蹤 =====
        _heroCardImageError: false,
        _heroLightboxImageError: false,

        // ===== A7-Prod: Hero Slot 預留 =====
        _heroSlotReserved: false,

        // ===== Constants =====
        PAGE_SIZE: 20,
        SOURCE_NAME: {
            'javbus': 'JavBus',
            'jav321': 'Jav321',
            'javdb': 'JavDB',
            'fc2': 'FC2',
            'avsox': 'AVSOX'
        },
        STATE_KEY: 'javhelper_search_state',

        // ===== Computed Properties =====
        // 92a-T2 (CD-92a-3): hasContent 改 computed getter，根治「兩組 X」——
        // loading 態恆回 false（清除鈕不與取消鈕並排），移除散落 8 處手動賦值的整類遺漏。
        // getter 惰性求值，render 時取 final pageState/results，無中間態順序問題。
        get hasContent() {
            // 173 CD-173-9：片商搜尋失敗的錯誤頁也要有 ✕（回到膠囊列）；先判 error 再呼叫 activeMaker()，
            // 既有測試用 Object.assign 組 fake this 時會先求值 getter，所以先判 pageState 再讀 activeMaker()。
            return this.pageState !== 'loading' && (this.searchResults.length > 0 || this.fileList.length > 0 || (this.pageState === 'error' && !!this.activeMaker()));
        },

        actressLightboxMode() {
            return this.lightboxIndex === -1;
        },

        canGoPrev() {
            if (this.listMode === 'file') {
                // 同層級：前方有非 _failed item
                const hasPrevVisible = this.searchResults.slice(0, this.currentIndex).some(r => !r._failed);
                // 跨檔案：可退到上一個檔案
                return hasPrevVisible || this.currentFileIndex > 0;
            }
            return this.searchResults.slice(0, this.currentIndex).some(r => !r._failed);
        },

        canGoNext() {
            if (this.listMode === 'file') {
                const hasNextVisible = this.searchResults.slice(this.currentIndex + 1).some(r => !r._failed);
                return hasNextVisible || this.currentFileIndex < this.fileList.length - 1;
            }
            return this.searchResults.slice(this.currentIndex + 1).some(r => !r._failed) || this.hasMoreResults;
        },

        canEditFile() { return this.listMode === 'file' && !!this.fileList[this.currentFileIndex]?.path; },

        hasVisiblePrev() {
            if (this.lightboxIndex === -1) return false;  // 已在 actress photo 最左
            if (this.lightboxIndex === 0) return !!this.actressProfile;  // 可跳到 actress
            // lightboxIndex > 0：前方有非 _failed item 或有 actressProfile
            const hasPrevVisible = this.searchResults.slice(0, this.lightboxIndex).some(r => !r._failed);
            return hasPrevVisible || !!this.actressProfile;
        },

        hasVisibleNext() {
            if (this.lightboxIndex === -1) {
                // 從 actress photo 看有沒有可見 item
                return this.searchResults.some(r => !r._failed);
            }
            return this.searchResults.slice(this.lightboxIndex + 1).some(r => !r._failed) || this.hasMoreResults;
        },

        showNavigation() {
            const visibleCount = this.searchResults.filter(r => !r._failed).length;
            const hasMultipleResults = visibleCount > 1 || this.hasMoreResults;
            const hasMultipleFiles = this.fileList.length > 1;
            return hasMultipleResults || hasMultipleFiles;
        },

        navIndicatorText() {
            if (this.fileList.length > 1) {
                // file 模式：維持原邏輯
                return `${this.currentFileIndex + 1}/${this.fileList.length}`;
            }
            // search 模式：排除 _failed
            const visibleItems = this.searchResults.filter(r => !r._failed);
            // position: 在 visibleItems 中，原始 index <= currentIndex 的數量
            const position = this.searchResults.slice(0, this.currentIndex + 1).filter(r => !r._failed).length;
            const total = this.hasMoreResults ? visibleItems.length + '+' : visibleItems.length;
            return `${position}/${total}`;
        },

        detailProgressPercent() {
            if (this.detailTotal === 0) return 0;
            return Math.round((this.detailDone / this.detailTotal) * 100);
        },

        // ===== T1d: File List Computed =====

        fileCountText() {
            if (this.listMode === 'file') {
                return window.t('search.filelist.file_count', {
                    current: this.currentFileIndex + 1,
                    total: this.fileList.length
                });
            }
            const visibleCount = this.searchResults.filter(r => !r._failed).length;
            const total = this.hasMoreResults ? visibleCount + '+' : visibleCount;
            return window.t('search.filelist.result_count', { count: total });
        },

        searchAllButtonText() {
            const searchableFiles = this.fileList.filter(f => f.number && !f.searched && !f.has_nfo);
            const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0) && !f.has_nfo);
            const batch = this.batchState;

            if (searchableFiles.length === 0 && failedFiles.length === 0) {
                return window.t('search.button.search_all');
            }
            if (batch.isProcessing) {
                return batch.isPaused ? window.t('search.button.continue') : window.t('search.button.pause');
            }
            if (searchableFiles.length === 0 && failedFiles.length > 0) {
                return window.t('search.button.retry_failed', { count: failedFiles.length });
            }
            return window.t('search.button.search_all');
        },

        searchAllButtonIcon() {
            const batch = this.batchState;
            if (batch.isProcessing) {
                return batch.isPaused ? 'bi-play-fill' : 'bi-pause-fill';
            }
            const searchableFiles = this.fileList.filter(f => f.number && !f.searched && !f.has_nfo);
            const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0) && !f.has_nfo);
            if (searchableFiles.length === 0 && failedFiles.length > 0) {
                return 'bi-arrow-clockwise';
            }
            return 'bi-search';
        },

        searchAllDisabled() {
            const searchableFiles = this.fileList.filter(f => f.number && !f.searched && !f.has_nfo);
            const failedFiles = this.fileList.filter(f => f.number && f.searched && (!f.searchResults || f.searchResults.length === 0) && !f.has_nfo);
            return searchableFiles.length === 0 && failedFiles.length === 0 && !this.batchState.isProcessing;
        },

        get isCloudSearchMode() {
            return this.listMode === 'search' && this.searchResults.length > 0;
        },

        hasJapanese(text) {
            return /[\u3040-\u309F\u30A0-\u30FF]/.test(text);
        },

        async checkLocalStatus(results) {
            // 收集所有有效番號
            const numberList = results
                .map(r => r.number)
                .filter(n => n);
            const numbers = numberList.join(',');

            if (!numbers) return;

            // TASK-140-T5：membership hydration。
            // 🔴 **兩件事都要獨立：發出要平行，「處理」也要平行**（Codex review P2）。
            // 第一版先 await membership 再 await local-status——即使兩個 fetch 是平行發出的，
            // **處理**仍串在同一條 async 序列上：membership 卡住不 resolve 時，local-status
            // 明明早就回來了，寫 `_localStatus` 那段也永遠不會執行。
            // 使用者後果與沒修之前一模一樣：**「本地已有」的紅框與播放鈕不會出現**，
            // 使用者以為這片沒下載過，又去整理／下載一次。
            // ⇒ 兩邊各自包成獨立的 async 任務，最後一起 await；任一邊卡住都不擋另一邊。
            const membershipTask = (async () => {
                try {
                    const membershipResp = await fetch('/api/wishlist/membership', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ numbers: numberList }),
                    });
                    if (!membershipResp.ok) {
                        console.warn('[WishlistMembership] API 請求失敗:', membershipResp.status);
                        return;
                    }
                    const membershipData = await membershipResp.json();
                    results.forEach(result => {
                        if (result.number) {
                            result._wishlisted = membershipData[result.number];
                        }
                    });
                } catch (err) {
                    console.error('[WishlistMembership] 查詢失敗:', err);
                }
            })();

            const localStatusTask = (async () => {
                try {
                    const resp = await fetch(`/api/search/local-status?numbers=${encodeURIComponent(numbers)}`);
                    if (!resp.ok) {
                        console.warn('[LocalStatus] API 請求失敗:', resp.status);
                        return;
                    }

                    const data = await resp.json();

                    // 更新搜尋結果的本地狀態
                    results.forEach(result => {
                        if (result.number) {
                            result._localStatus = data[result.number] || data[result.number?.toUpperCase()];
                        }
                    });

                    // 收集有本地匹配的番號
                    const localMatchNumbers = results
                        .filter(r => r._localStatus?.exists)
                        .map(r => r.number);

                    // 觸發跨 scope 事件（通知 sidebar + 卡片）
                    if (localMatchNumbers.length > 0) {
                        window.dispatchEvent(new CustomEvent('search:local-match', {
                            detail: { numbers: localMatchNumbers }
                        }));
                    }
                } catch (err) {
                    console.error('[LocalStatus] 查詢失敗:', err);
                }
            })();

            await Promise.all([membershipTask, localStatusTask]);
        },

        translateAllButtonText() {
            const ts = this.translateState;
            if (ts.isProcessing) {
                return ts.isPaused
                    ? window.t('search.button.continue')
                    : window.t('search.button.translating_progress', { processed: ts.processed, total: ts.total });
            }
            const count = this.searchResults.filter(r => r.title && this.hasJapanese(r.title) && !r.translated_title).length;
            return window.t('search.button.translate_all_count', { count });
        },

        translateAllButtonIcon() {
            const ts = this.translateState;
            if (ts.isProcessing) {
                return ts.isPaused ? 'bi-play-fill' : 'bi-pause-fill';
            }
            return 'bi-translate';
        },

        translateAllDisabled() {
            const ts = this.translateState;
            if (ts.isProcessing) return false;
            if (!this.appConfig?.translate?.enabled) return true;
            const count = this.searchResults.filter(r => r.title && this.hasJapanese(r.title) && !r.translated_title).length;
            return count === 0;
        },

        batchPercent() {
            const batch = this.batchState;
            if (batch.total === 0) return 0;
            return Math.round((batch.processed / batch.total) * 100);
        },

        batchProgressText() {
            const batch = this.batchState;
            const key = batch.isPaused ? 'search.filelist.paused_prefix' : 'search.filelist.processing_prefix';
            return window.t(key) + ' ' + batch.processed + '/' + batch.total;
        },

        // ===== T2b: Scrape Progress Computed =====
        scrapePercent() {
            const sp = this.scrapeProgress;
            if (sp.total === 0) return 0;
            return Math.round((sp.processed / sp.total) * 100);
        },

        // ===== T1d: File List Helper Methods =====

        fileStatusIcon(file) {
            if (!file.number) return '?';
            if (file.searched) {
                return (file.searchResults && file.searchResults.length > 0) ? '✓' : '✗';
            }
            return '';
        },

        isFileSearching(file) {
            return isPathSearching(this.batchState.activePaths, file.path);
        },

        fileStatusClass(file) {
            let cls = 'file-status';
            if (!file.number) cls += ' text-warning';
            else if (file.searched && (!file.searchResults || file.searchResults.length === 0)) {
                cls += ' text-error';
            }
            return cls;
        },

        canScrapeFile(file) {
            return file.searched && file.searchResults && file.searchResults.length > 0 && !file.scraped;
        },

        // 139b-T12：兩種「這一列需要人手介入」都給鉛筆。
        //   ① 檔名解析不出番號（file.number 空）——原本就有。
        //   ② 番號解析出來了、但八個來源都查無結果（searched 且 searchResults 空）。
        // ② 過去是死路：拖檔查無結果走 pageState='result'（file-list.js:65/132），
        //    #errorState 的「使用番號進階搜尋」不會出現；結果卡右上角的來源膠囊包在
        //    x-if="current().source"（search.html:487）裡、沒結果就整顆不渲染；而鉛筆
        //    的條件是 !file.number，番號解析成功時它也被藏起來 ⇒ 三個出口全關。
        //    典型情境：拖入 ABC-999.mp4，番號其實打錯了，卻沒有地方可以改。
        // searchResults 在 ① 可能是 undefined，但那時 searched 為 false，短路先擋掉。
        needsNumberInput(file) {
            // Boolean() 包住：file.searched 不存在時（剛建 fileList）`undefined && ...` 會回
            // undefined 而非 false。x-show 兩者等效，但守衛與測試用 strict 比較。
            return Boolean(!file.number || (file.searched && !file.searchResults?.length));
        },

        // ===== T4: Rotating Border Methods =====

        // T4: 檢查是否應顯示本地匹配外框
        shouldShowLocalBorder(result) {
            return result?._localStatus?.exists;
        },

        closeDuplicateModal() {
            this.duplicateModalOpen = false;
            this.duplicateTarget = '';
        },

        // U8a: centralized cover state reset
        _resetCoverState() {
            this._coverRequestId++;
            this._coverRetried = false;
            this._coverLoaded = false;
            this.coverError = '';
            this._clearTimer('coverRetry');

            // 防禦：若圖片已在瀏覽器快取中（同 URL 不重觸 @load），
            // 下一 tick 檢查 complete 狀態，避免 shimmer 永遠遮蓋封面
            var requestId = this._coverRequestId;
            this.$nextTick(() => {
                if (this._coverRequestId !== requestId) return;  // 已被後續重置取代
                var img = this.$refs.coverImg;
                if (img && img.complete && img.naturalWidth > 0 && !this._coverLoaded) {
                    this._coverLoaded = true;
                }
                // Issue-2: 更新封面高度 CSS variable（供 sample-thumb 高度計算）
                this._updateCoverHeight();
            });
        },

        // Issue-2: 讀取封面容器實際高度，設定 --cover-height CSS variable
        // 讓 sample-thumb 用比例縮放取代 vw 單位，在任意視窗尺寸下保持正確比例
        _updateCoverHeight() {
            var cover = this.$el.querySelector('.av-card-full-cover');
            if (!cover) return;
            var h = cover.offsetHeight;
            if (h > 0) {
                cover.style.setProperty('--cover-height', h + 'px');
            }
        },

        // ===== Phase 43 T6: Actress Chips Helpers =====

        _chipsLimit() {
            return window.innerWidth < 768 ? 6 : 10;
        },

        _allInfoChips() {
            if (!this.actressProfile) return [];
            const p = this.actressProfile;
            return [
                ...(p.tags || []),
                ...(p.hometown ? [p.hometown] : []),
                ...(p.nickname ? [p.nickname] : []),
                ...(p.agency ? [p.agency] : []),
                ...(p.hobby ? [p.hobby] : []),
                ...(p.debut_work ? [p.debut_work] : []),
            ];
        },

        _visibleAliases() {
            const aliases = this.actressProfile?.aliases || [];
            if (this._actressChipsExpanded.aliases) return aliases;
            return aliases.slice(0, this._chipsLimit());
        },

        _visibleInfoChips() {
            const chips = this._allInfoChips();
            if (this._actressChipsExpanded.info) return chips;
            return chips.slice(0, this._chipsLimit());
        },

        // ===== T5: Actress Favorite =====

        // 從 searchResults 提取片商前綴（供 /api/actresses/favorite makers 參數）
        _extractCurrentMakers() {
            const results = this.searchResults || [];
            const makers = new Set();
            results.forEach(r => {
                if (r.number) {
                    const m = r.number.match(/^([A-Za-z]+)/);
                    if (m) makers.add(m[1].toUpperCase());
                }
            });
            return Array.from(makers);
        },

        _safeUrl(url) {
            if (!url || typeof url !== 'string') return '#';
            if (!url.startsWith('http://') && !url.startsWith('https://')) return '#';
            return url;
        },

        // ===== T10: Actress Source URL =====

        _actressSourceUrl() {
            const src = this.actressProfile?.primary_text_source;
            const name = this.actressProfile?.name;
            if (!src || !name) return null;
            if (src === 'wiki') return `https://ja.wikipedia.org/wiki/${encodeURIComponent(name)}`;
            if (src === 'xcity') return `https://xcity.jp/idol/?genre=%2Fidol%2F&q=${encodeURIComponent(name)}&sg=idol`;
            if (src === 'avbase') return `https://www.avbase.net/talents/${encodeURIComponent(name)}`;
            return null;
        },

        async addFavoriteActress() {
            if (!this.actressProfile || this.actressProfile.is_favorite || this._actressFavoriteLoading) return;

            // capture reference before await — 防止 await 期間切女優的 race（同 41d pattern）
            const capturedProfile = this.actressProfile;
            const capturedName = this.actressProfile.name;

            const gen = ++this._actressFavoriteGen;
            this._actressFavoriteLoading = true;

            // 10s 前端 timeout
            const controller = new AbortController();
            this._actressFavoriteTimer = setTimeout(() => controller.abort(), 10000);

            try {
                const makers = this._extractCurrentMakers();
                const resp = await fetch('/api/actresses/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: capturedName, makers }),
                    signal: controller.signal,
                });

                clearTimeout(this._actressFavoriteTimer);
                this._actressFavoriteTimer = null;

                if (resp.status === 200) {
                    const data = await resp.json();
                    // stale-check：await 期間可能已切女優，丟棄過時結果
                    if (this.actressProfile !== capturedProfile) return;
                    const actress = data.actress || {};
                    this.actressProfile = {
                        ...capturedProfile,
                        is_favorite: true,
                        img: actress.photo_url || capturedProfile.img,
                    };
                    this.showToast(window.t('search.actress.favorite_success'), 'success');
                } else if (resp.status === 409) {
                    const data = await resp.json();
                    if (this.actressProfile !== capturedProfile) return;
                    const actress = data.actress || {};
                    this.actressProfile = {
                        ...capturedProfile,
                        is_favorite: true,
                        img: actress.photo_url || capturedProfile.img,
                    };
                } else {
                    const data = await resp.json().catch(() => ({}));
                    this.showToast(window.t('search.actress.favorite_error'), 'error');
                    console.error('[addFavoriteActress] 失敗:', resp.status, data);
                }
            } catch (err) {
                clearTimeout(this._actressFavoriteTimer);
                this._actressFavoriteTimer = null;

                if (err.name === 'AbortError') {
                    this.showToast(window.t('search.actress.favorite_timeout'), 'error');
                } else {
                    this.showToast(window.t('search.actress.favorite_error'), 'error');
                    console.error('[addFavoriteActress] 例外:', err);
                }
            } finally {
                if (this._actressFavoriteGen === gen) this._actressFavoriteLoading = false;
            }
        },
    };
}
