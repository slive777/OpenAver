function scannerPage() {
  return {
    // ===== Data State =====
    directories: [],
    config: {},
    configDirty: false,

    // ===== Toast State =====
    _toast: {
        message: '',
        type: 'info',
        visible: false
    },
    _toastTimer: null,

    // ===== Folder Dirty Check =====
    folderSnapshot: null,
    pendingNavigationUrl: '',
    dirtyCheckModalOpen: false,

    // ===== Drag-drop State =====
    dragCounter: 0,
    showDragOverlay: false,

    // ===== Stats State =====
    statsVisible: false,
    statTotal: 0,
    statLastRun: '',
    clearCacheModalOpen: false,
    clearCacheLoading: false,

    // ===== Manual Input State =====
    manualInputVisible: false,
    manualPath: '',

    // ===== Alias State (v2) =====
    aliasCardCollapsed: true,
    aliasRecords: [],            // [{primary_name, aliases, source, created_at, updated_at}]
    aliasRecordsLoading: false,
    aliasRecordsError: '',
    aliasInput: '',              // 單一輸入：篩選 query / 新增主名

    // ===== New Group Form =====
    newGroupAdding: false,

    // ===== Add Alias Inline Input =====
    addingAlias: {},             // { [primary_name]: 'input value' }
    addingAliasLoading: {},      // { [primary_name]: bool }

    // ===== Online Search =====
    onlineSearchName: '',
    onlineSearchLoading: false,
    onlineSearchResults: [],     // suggested_aliases from API
    onlineSearchSelected: [],    // checkbox values
    onlineSearchTarget: '',      // 要加到哪個 primary_name
    onlineSearchDone: false,     // 搜尋完成旗標（用於顯示「無搜尋建議」）

    // ===== T7b: State Machine =====
    state: 'idle',  // 'idle' | 'generating' | 'nfoUpdating' | 'done' | 'error'

    // ===== T7b: Progress =====
    progressStatus: '',
    progressCurrent: 0,
    progressTotal: 0,

    // ===== T7b: Log System =====
    logHtml: '',           // 日誌 HTML（用於 restoreLogs）
    logBatch: [],          // 批次佇列
    logTimer: null,        // 批次計時器

    // ===== T7d: Log Terminal 增強 =====
    logEntries: [],        // [{level, message, timestamp}] 結構化陣列
    logFilter: 'all',      // 'all' | 'error' | 'warn' 篩選條件

    // ===== T7b: Done Actions =====
    outputPath: '',        // 輸出路徑（供複製）

    // ===== T7b: NFO Update =====
    nfoNeedUpdateCount: 0,
    nfoUpdatePaths: [],
    nfoUpdateVisible: false,

    // ===== T6d: Jellyfin Image Update =====
    jellyfinImageCount: 0,
    jellyfinImageVisible: false,
    showJellyfinHelp: false,
    jellyfinCheckState: 'idle',   // T2(40c): 'idle' | 'checking' | 'done'
    _jellyfinCheckController: null,

    // ===== T10: Missing NFO/Cover Enrich =====
    missingPillVisible: false,
    missingBothCount: 0,
    missingNfoCount: 0,
    missingCoverCount: 0,
    missingItems: [],           // [{file_path, number}]
    missingEnrichOffset: 0,     // batch offset
    missingEnrichSuccess: 0,
    missingEnrichFailed: 0,
    resumePillVisible: false,
    missingConfirmModalOpen: false,   // TASK-13: 大批量補完 confirm dialog 開關
    _enrichAbortController: null,

    // ===== T7b: EventSource 管理 =====
    eventSource: null,

    // ===== Computed Properties =====
    get isFolderDirty() {
        if (!this.folderSnapshot) return false;
        return JSON.stringify(this.directories) !== this.folderSnapshot;
    },

    get outputPathDisplay() {
        const outputDir = this.config.gallery?.output_dir || 'output';
        const outputFilename = this.config.gallery?.output_filename || 'gallery_output.html';
        return `${outputDir}/${outputFilename}`;
    },

    // ===== T7b: Computed Properties =====
    get progressPercent() {
        if (this.progressTotal === 0) return 0;
        return (this.progressCurrent / this.progressTotal) * 100;
    },

    get isGenerating() {
        return this.state === 'generating' || this.state === 'nfoUpdating'
            || this.state === 'jellyfinUpdating' || this.state === 'enriching';
    },

    get isBusy() {
        // 用於按鈕 disabled：generating/nfoUpdating 時鎖定
        return this.isGenerating;
    },

    get progressSectionVisible() {
        // state 非 idle 時顯示，或有恢復的 logs 時也顯示
        return this.state !== 'idle' || this.logHtml !== '';
    },

    get doneActionsVisible() {
        return this.state === 'done' && this.outputPath !== '';
    },

    get generateButtonText() {
        if (this.state === 'generating') {
            return '<span class="loading loading-spinner loading-sm"></span> ' + window.t('scanner.stats.generate_loading');
        }
        return '<i class="bi bi-play-fill"></i> ' + window.t('scanner.stats.generate_idle');
    },

    get nfoUpdateButtonText() {
        if (this.state === 'nfoUpdating') {
            return '<span class="loading loading-spinner loading-sm"></span> ' + window.t('scanner.stats.nfo_loading');
        }
        if (this.nfoNeedUpdateCount > 0) {
            return '<i class="bi bi-magic"></i> ' + window.t('scanner.stats.nfo_idle');
        }
        return '<i class="bi bi-check-lg"></i> ' + window.t('scanner.stats.btn_done');
    },

    get nfoUpdateButtonDisabled() {
        // generating/nfoUpdating 時鎖定；idle/done/error 時看 nfoNeedUpdateCount
        return this.isGenerating || this.nfoNeedUpdateCount === 0;
    },

    get jellyfinImageButtonText() {
        if (this.state === 'jellyfinUpdating') {
            return '<span class="loading loading-spinner loading-sm"></span> ' + window.t('scanner.stats.jellyfin_loading');
        }
        if (this.jellyfinImageCount > 0) {
            return '<i class="bi bi-images"></i> ' + window.t('scanner.stats.jellyfin_idle');
        }
        return '<i class="bi bi-check-lg"></i> ' + window.t('scanner.stats.btn_done');
    },

    // ===== T10: Missing Pill Computed =====
    get missingPillLabel() {
        const parts = [];
        if (this.missingBothCount > 0) {
            parts.push(window.t('scanner.stats.missing_both_prefix') + ' ' + this.missingBothCount + window.t('scanner.stats.missing_suffix'));
        }
        if (this.missingNfoCount > 0) {
            parts.push(window.t('scanner.stats.missing_nfo_prefix') + ' ' + this.missingNfoCount + window.t('scanner.stats.missing_suffix'));
        }
        if (this.missingCoverCount > 0) {
            parts.push(window.t('scanner.stats.missing_cover_prefix') + ' ' + this.missingCoverCount + window.t('scanner.stats.missing_suffix'));
        }
        return parts.join(' ');
    },

    get missingEnrichButtonText() {
        if (this.state === 'enriching') {
            return '<span class="loading loading-spinner loading-sm"></span> ' + window.t('scanner.stats.missing_enrich_loading');
        }
        return '<i class="bi bi-file-earmark-plus"></i> ' + window.t('scanner.stats.missing_enrich_idle');
    },

    // ===== Lifecycle =====
    async init() {
        // 覆蓋全域函數為 Alpine 版本
        const self = this;

        // 暴露 PyWebView 回調
        window.addScannerFolder = (path) => self.addFolderPath(path);

        // 初始載入
        await this.loadConfig();
        this.loadStats();

        // T7b: 恢復日誌（確保 DOM 已渲染）
        await this.$nextTick();
        this.restoreLogs();

        // T10: 觸發 missing check（loadStats 後）
        this.checkMissing();

        // T10: restore pending enrich
        const pending = localStorage.getItem('avlist_enrich_pending');
        if (pending) {
            try {
                const items = JSON.parse(pending);
                if (Array.isArray(items) && items.length > 0) {
                    this.missingItems = items;
                    this.resumePillVisible = true;
                }
            } catch { localStorage.removeItem('avlist_enrich_pending'); }
        }

        // T5.1: 接入統一 page lifecycle
        if (window.__registerPage) {
            window.__registerPage({
                beforeLeave: (href) => {
                    const guard = this.shouldWarnBeforeLeave();
                    if (guard.shouldWarn) {
                        if (guard.useModal) {
                            this.pendingNavigationUrl = href;
                            this.dirtyCheckModalOpen = true;
                            return false;
                        } else {
                            const ok = confirm(guard.message + '確定要離開嗎？');
                            if (ok) {
                                // T2(40c): 離頁確認後 abort jellyfin check
                                if (this._jellyfinCheckController) {
                                    this._jellyfinCheckController.abort();
                                    this._jellyfinCheckController = null;
                                }
                                this.jellyfinCheckState = 'idle';
                            }
                            return ok;
                        }
                    }
                    return true;
                },
                onBeforeUnload: () => {
                    const guard = this.shouldWarnBeforeLeave();
                    if (guard.shouldWarn) return guard.message;
                    return null;
                },
                cleanup: () => {
                    if (this.eventSource) { this.eventSource.close(); this.eventSource = null; }
                    clearTimeout(this._toastTimer);
                    clearTimeout(this.logTimer);
                    // T2(40c): abort jellyfin check fetch
                    if (this._jellyfinCheckController) {
                        this._jellyfinCheckController.abort();
                        this._jellyfinCheckController = null;
                    }
                    this.jellyfinCheckState = 'idle';
                    // T10: save pending enrich items on leave
                    if (this.state === 'enriching' && this.missingItems.length > this.missingEnrichOffset) {
                        localStorage.setItem('avlist_enrich_pending', JSON.stringify(this.missingItems.slice(this.missingEnrichOffset)));
                    }
                    if (this._enrichAbortController) {
                        this._enrichAbortController.abort();
                        this._enrichAbortController = null;
                    }
                }
            });
        }
    },

    // ===== Leave Guard =====
    shouldWarnBeforeLeave() {
        // T7b: 改為讀取 Alpine state，而非全域變數
        if (this.isGenerating) {
            return {
                shouldWarn: true,
                message: '生成正在進行中，離開將會中斷操作！',
                useModal: false
            };
        }
        // T2(40c): Jellyfin check 進行中觸發離頁確認
        if (this.jellyfinCheckState === 'checking') {
            return {
                shouldWarn: true,
                message: 'Jellyfin 圖片檢查進行中，離開將會中斷！',
                useModal: false
            };
        }
        if (this.isFolderDirty) {
            return {
                shouldWarn: true,
                message: '您有未儲存的資料夾變更',
                useModal: true
            };
        }
        return { shouldWarn: false };
    },

    // ===== Config Methods =====
    async loadConfig() {
        this.folderSnapshot = null;

        try {
            const resp = await fetch('/api/config');
            const result = await resp.json();
            if (result.success) {
                this.config = result.data;
                this.directories = this.config.gallery?.directories || [];

                // T7b: 不再需要同步全域變數（core.js 已刪除）

                // 建立快照
                this.folderSnapshot = JSON.stringify(this.directories);
            }
        } catch (e) {
            console.error('載入設定失敗:', e);
        }
    },

    async saveConfig() {
        try {
            this.config.gallery = this.config.gallery || {};
            this.config.gallery.directories = this.directories;

            const resp = await fetch('/api/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.config)
            });
            const result = await resp.json();
            if (result.success) {
                this.configDirty = false;
                this.folderSnapshot = JSON.stringify(this.directories);
                this.showToast('設定已儲存', 'success');
                return true;
            } else {
                this.showToast('儲存失敗: ' + (result.error || '未知錯誤'), 'error');
                return false;
            }
        } catch (e) {
            console.error('儲存失敗:', e);
            this.showToast('儲存失敗: ' + e.message, 'error');
            return false;
        }
    },

    // ===== Stats Methods =====
    async loadStats() {
        try {
            const resp = await fetch('/api/gallery/stats');
            const result = await resp.json();
            if (result.success && result.data) {
                const stats = result.data;
                if (stats.total > 0) {
                    this.statsVisible = true;
                    this.statTotal = stats.total;

                    if (stats.last_run) {
                        const lastRun = new Date(stats.last_run);
                        const timeStr = lastRun.toLocaleString('zh-TW', {
                            month: 'numeric',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                        });
                        let runInfo = window.t('scanner.stats.last_run_prefix') + timeStr;
                        if (stats.last_added !== null && stats.last_added !== undefined) {
                            runInfo += ' ' + window.t('scanner.stats.last_added', { count: stats.last_added });
                        }
                        this.statLastRun = runInfo;
                    }
                }
            }
        } catch (e) {
            console.error('載入統計失敗:', e);
        }
    },

    async clearCache() {
        this.clearCacheLoading = true;
        try {
            const resp = await fetch('/api/gallery/cache', { method: 'DELETE' });
            const result = await resp.json();
            if (result.success) {
                this.showToast(`已清除 ${result.deleted} 部影片快取`, 'success');
                this.statTotal = 0;
                this.statsVisible = false;
                this.nfoUpdateVisible = false;
                this.jellyfinImageVisible = false;
                this.jellyfinCheckState = 'idle';
                this.clearCacheModalOpen = false;
                // T10: reset missing pill state
                this.missingPillVisible = false;
                this.resumePillVisible = false;
                this.missingItems = [];
                localStorage.removeItem('avlist_enrich_pending');
            } else {
                this.showToast('清除失敗: ' + (result.error || '未知錯誤'), 'error');
            }
        } catch (e) {
            this.showToast('清除失敗: ' + e.message, 'error');
        } finally {
            this.clearCacheLoading = false;
        }
    },

    // ===== T6d: Jellyfin Image Check =====
    async checkJellyfinImages() {
        if (!this.config?.scraper?.jellyfin_mode) return;

        // T2(40c): 取消上一次未完成的請求（防重複點擊）
        if (this._jellyfinCheckController) {
            this._jellyfinCheckController.abort();
        }
        const controller = new AbortController();
        this._jellyfinCheckController = controller;
        this.jellyfinCheckState = 'checking';

        try {
            const resp = await fetch('/api/gallery/jellyfin-check', {
                signal: controller.signal
            });
            const data = await resp.json();
            if (!data.success) {
                console.error('Jellyfin check API error:', data.error);
                this.jellyfinCheckState = 'idle';
                return;
            }
            if (data.data.need_update > 0) {
                this.jellyfinImageCount = data.data.need_update;
                this.jellyfinImageVisible = true;
            } else {
                this.jellyfinImageCount = 0;
                this.jellyfinImageVisible = false;
            }
            this.jellyfinCheckState = 'done';
        } catch (e) {
            if (e.name === 'AbortError') {
                this.jellyfinCheckState = 'idle';
                return;
            }
            console.error('Jellyfin check failed:', e);
            this.jellyfinCheckState = 'idle';
        } finally {
            if (this._jellyfinCheckController === controller) {
                this._jellyfinCheckController = null;
            }
        }
    },

    // ===== Folder Management =====
    async selectFolder() {
        if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
            this.toggleManualInput();
            alert('此功能需要在桌面應用程式中使用');
            return;
        }

        try {
            const result = await window.pywebview.api.select_folder();

            if (result && result.folder) {
                this.addFolderPath(result.folder);
            } else if (Array.isArray(result) && result.length > 0) {
                const firstFile = result[0];
                const lastSep = Math.max(firstFile.lastIndexOf('\\'), firstFile.lastIndexOf('/'));
                const folderPath = lastSep > 0 ? firstFile.substring(0, lastSep) : null;
                if (folderPath) {
                    this.addFolderPath(folderPath);
                }
            }
        } catch (e) {
            console.error('[AVList] 選取資料夾失敗:', e);
        }
    },

    addFolderPath(folderPath) {
        if (!this.directories.includes(folderPath)) {
            this.directories.push(folderPath);
            this.configDirty = true;
        } else {
            alert('此資料夾已在列表中');
        }
    },

    toggleManualInput() {
        this.manualInputVisible = !this.manualInputVisible;
        if (this.manualInputVisible) {
            this.$nextTick(() => {
                this.$refs.manualPathInput.focus();
            });
        }
    },

    addManualPath() {
        const path = this.manualPath.trim();
        if (!path) return;

        if (this.directories.includes(path)) {
            alert('此資料夾已在列表中');
            return;
        }

        this.directories.push(path);
        this.configDirty = true;
        this.manualPath = '';
    },

    removeDirectory(idx) {
        this.directories.splice(idx, 1);
        this.configDirty = true;
    },

    // ===== Drag-drop Methods =====
    handleDragEnter(e) {
        e.preventDefault();
        this.dragCounter++;
        if (this.dragCounter === 1) {
            this.showDragOverlay = true;
        }
    },

    handleDragLeave(e) {
        e.preventDefault();
        this.dragCounter--;
        if (this.dragCounter === 0) {
            this.showDragOverlay = false;
        }
    },

    handleDrop(e) {
        e.preventDefault();
        this.dragCounter = 0;
        this.showDragOverlay = false;
    },

    // ===== Dirty Check Modal Actions =====
    dirtyCheckCancel() {
        this.dirtyCheckModalOpen = false;
        this.pendingNavigationUrl = '';
    },

    async dirtyCheckDiscard() {
        await this.loadConfig();
        this.dirtyCheckModalOpen = false;
        if (this.pendingNavigationUrl) {
            const url = this.pendingNavigationUrl;
            // dirty state cleared by loadConfig(); beforeLeave will now return true
            // → __leavePage triggers _doCleanup (closes eventSource + clears timers)
            if (window.__leavePage) {
                window.__leavePage(url);
            }
            window.location.href = url;
        }
    },

    async dirtyCheckSave() {
        const saved = await this.saveConfig();
        if (saved) {
            this.dirtyCheckModalOpen = false;
            if (this.pendingNavigationUrl) {
                const url = this.pendingNavigationUrl;
                // dirty state cleared by saveConfig(); beforeLeave will now return true
                // → __leavePage triggers _doCleanup (closes eventSource + clears timers)
                if (window.__leavePage) {
                    window.__leavePage(url);
                }
                window.location.href = url;
            }
        }
        // If save failed, modal stays open, user sees toast error
    },

    // ===== Utility Methods =====
    showToast(msg, type = 'info', duration = 2500) {
        this._toast.message = msg;
        this._toast.type = type;
        this._toast.visible = true;

        if (this._toastTimer) {
            clearTimeout(this._toastTimer);
        }

        this._toastTimer = setTimeout(() => {
            this._toast.visible = false;
            this._toastTimer = null;
        }, duration);
    },

    escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    },

    // ===== T7b: Log System =====
    /**
     * Log 系統效能設計說明
     *
     * 使用 insertAdjacentHTML（而非 Alpine x-for）的原因：
     * 1. Scanner 典型場景會產生 200-3000 條 log
     * 2. Alpine x-for 重渲染在大量 log 時慢 10x（100-300ms vs 20-40ms）
     * 3. 批次處理 + insertAdjacentHTML 可維持流暢體驗（< 40ms）
     *
     * 實作特性：
     * - 100ms debounce 批次插入（減少 DOM 操作）
     * - CSS-only 篩選（filter-all/error/warn class，零 JS 開銷）
     * - 雙重儲存：logEntries（結構化）+ logHtml（快速恢復）
     */
    addLog(level, message) {
        // T7d: 加入結構化陣列
        this.logEntries.push({ level, message, timestamp: Date.now() });

        const cls = level === 'error' ? 'log-error' :
                    level === 'warn' ? 'log-warn' : 'log-info';
        const escaped = this.escapeHtml(message);
        this.logBatch.push(`<div class="${cls}" data-level="${level}">${escaped}</div>`);

        if (!this.logTimer) {
            this.logTimer = setTimeout(() => this.flushLogs(), 100);
        }
    },

    flushLogs() {
        if (this.logBatch.length === 0) {
            this.logTimer = null;
            return;
        }

        const logOutput = this.$refs.logOutput;
        logOutput.insertAdjacentHTML('beforeend', this.logBatch.join(''));
        logOutput.scrollTop = logOutput.scrollHeight;

        // 更新 Alpine state（供 restoreLogs 使用）
        this.logHtml = logOutput.innerHTML;

        // 儲存到 localStorage
        localStorage.setItem('avlist_logs', this.logHtml);

        this.logBatch = [];
        this.logTimer = null;
    },

    restoreLogs() {
        const savedLogs = localStorage.getItem('avlist_logs');
        const wasGenerating = localStorage.getItem('avlist_generating') === 'true';

        if (savedLogs) {
            const logOutput = this.$refs.logOutput;
            logOutput.innerHTML = savedLogs;
            this.logHtml = savedLogs;

            // T7d: 解析 HTML，重建 logEntries（相容舊格式無 data-level）
            this.logEntries = [];
            const logDivs = logOutput.querySelectorAll('.log-info, .log-warn, .log-error');
            logDivs.forEach(div => {
                let level = div.getAttribute('data-level');
                if (!level) {
                    if (div.classList.contains('log-error')) level = 'error';
                    else if (div.classList.contains('log-warn')) level = 'warn';
                    else level = 'info';
                }
                this.logEntries.push({ level, message: div.textContent, timestamp: Date.now() });
            });

            if (wasGenerating) {
                this.addLog('warn', '⚠ 生成被中斷（離開頁面）');
                this.flushLogs();
                localStorage.setItem('avlist_generating', 'false');
            }

            const lastStatus = localStorage.getItem('avlist_last_status');
            if (lastStatus) {
                this.progressStatus = lastStatus;
            }

            // 如果有未完成的任務，顯示 progress section
            if (wasGenerating || savedLogs) {
                this.state = 'idle';  // 重置狀態為 idle（已中斷）
            }
        }
    },

    clearLogs() {
        localStorage.removeItem('avlist_logs');
        localStorage.removeItem('avlist_generating');
        localStorage.removeItem('avlist_last_status');
        this.logHtml = '';
        this.logEntries = [];
        this.$refs.logOutput.innerHTML = '';
    },

    // ===== T7d: Log Terminal 增強 =====
    clearLogsDisplay() {
        this.logHtml = '';
        this.logEntries = [];
        this.$refs.logOutput.innerHTML = '';
    },

    copyLogs() {
        if (this.logEntries.length === 0) {
            this.showToast('目前沒有日誌');
            return;
        }

        const text = this.logEntries.map(entry => entry.message).join('\n');

        navigator.clipboard.writeText(text).then(() => {
            this.showToast(`已複製 ${this.logEntries.length} 筆日誌`, 'success');
        }).catch(() => {
            alert('複製失敗，日誌內容：\n\n' + text.substring(0, 500) + '...');
        });
    },

    confirmClearAll() {
        const hasLogs = this.logEntries.length > 0 || localStorage.getItem('avlist_logs');
        if (!hasLogs) {
            this.showToast('目前沒有日誌');
            return;
        }

        if (confirm('確定要清除所有日誌嗎？（包含歷史紀錄）')) {
            this.clearLogs();
            this.showToast('已清除所有日誌', 'success');
        }
    },

    // ===== T7b: Generate Flow =====
    async generate() {
        // 互斥鎖定：generating/nfoUpdating 時不可再次執行
        if (this.isGenerating) return;

        if (this.directories.length === 0) {
            this.showToast('請先加入至少一個資料夾');
            return;
        }

        // 自動儲存設定
        if (this.configDirty) {
            await this.saveConfig();
        }

        // 重置狀態
        this.state = 'generating';
        this.progressStatus = '準備中...';
        this.progressCurrent = 0;
        this.progressTotal = 0;
        this.outputPath = '';
        this.nfoUpdateVisible = false;
        this.clearLogs();

        // 設置 localStorage 標記
        localStorage.setItem('avlist_generating', 'true');

        try {
            this.eventSource = new EventSource('/api/gallery/generate');

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === 'progress') {
                    this.progressStatus = data.status;
                    this.progressCurrent = data.current;
                    this.progressTotal = data.total;
                    localStorage.setItem('avlist_last_status', data.status);
                } else if (data.type === 'log') {
                    this.addLog(data.level, data.message);
                } else if (data.type === 'done') {
                    this.eventSource.close();
                    this.eventSource = null;
                    this.state = 'done';
                    this.progressStatus = `完成！${data.video_count} 部影片`;
                    this.progressCurrent = this.progressTotal;
                    this.outputPath = data.output_path;

                    localStorage.setItem('avlist_generating', 'false');
                    localStorage.setItem('avlist_last_status', '完成');
                    localStorage.removeItem('avlist_state');  // 清除 viewer 狀態

                    // 處理 NFO 更新提示
                    if (data.session_update && data.session_update.count > 0) {
                        this.nfoNeedUpdateCount = data.session_update.count;
                        this.nfoUpdatePaths = data.session_update.paths;
                        this.nfoUpdateVisible = true;
                    } else {
                        this.nfoNeedUpdateCount = 0;
                        this.nfoUpdatePaths = [];
                        this.nfoUpdateVisible = false;
                    }

                    this.showToast(`成功產生 ${data.video_count} 部影片列表`, 'success');

                    // a5: Windows 長路徑警告
                    if (data.long_paths && data.long_paths.length > 0) {
                        this.showToast(
                            `本次掃描發現 ${data.long_paths.length} 個路徑超過 260 字元，可能無法讀取，詳細清單見 debug.log`,
                            'warn',
                            6000
                        );
                    }

                    this.flushLogs();

                    // 刷新統計（不含 NFO 檢查）
                    this.loadStats();

                    // T10: 掃描完成後檢查缺失 NFO/封面
                    this.checkMissing();

                    // 更新資料夾快照（generate 成功視為儲存）
                    this.folderSnapshot = JSON.stringify(this.directories);
                } else if (data.type === 'error') {
                    this.eventSource.close();
                    this.eventSource = null;
                    this.state = 'error';
                    this.addLog('error', '錯誤: ' + data.message);
                    this.flushLogs();
                    localStorage.setItem('avlist_generating', 'false');
                }
            };

            this.eventSource.onerror = () => {
                if (this.state === 'done') return;
                this.eventSource.close();
                this.eventSource = null;
                this.state = 'error';
                this.addLog('error', '連線中斷');
                this.flushLogs();
                localStorage.setItem('avlist_generating', 'false');
            };
        } catch (e) {
            this.state = 'error';
            localStorage.setItem('avlist_generating', 'false');
            alert('發生錯誤: ' + e.message);
        }
    },

    // ===== T7b: NFO Update Flow =====
    async runNfoUpdate() {
        // 互斥鎖定
        if (this.isGenerating) return;

        if (this.nfoNeedUpdateCount === 0) {
            this.showToast('沒有需要更新的影片');
            return;
        }

        // 重置狀態
        this.state = 'nfoUpdating';
        this.progressStatus = '準備中...';
        this.progressCurrent = 0;
        this.progressTotal = 0;
        this.clearLogs();

        localStorage.setItem('avlist_generating', 'true');

        try {
            this.eventSource = new EventSource('/api/gallery/update');

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === 'progress') {
                    this.progressStatus = data.status;
                    this.progressCurrent = data.current;
                    this.progressTotal = data.total;
                    localStorage.setItem('avlist_last_status', data.status);
                } else if (data.type === 'log') {
                    this.addLog(data.level, data.message);
                } else if (data.type === 'done') {
                    this.eventSource.close();
                    this.eventSource = null;
                    this.state = 'done';
                    this.progressStatus = data.message || '完成';
                    this.progressCurrent = this.progressTotal;

                    localStorage.setItem('avlist_generating', 'false');
                    localStorage.setItem('avlist_last_status', data.message || '完成');

                    this.showToast('補全完成！請重新產生列表以更新', 'success');
                    if (data.message) {
                        this.addLog('info', data.message);
                    }
                    this.flushLogs();

                    // 隱藏 NFO 更新按鈕（已完成）
                    this.nfoNeedUpdateCount = 0;
                    this.nfoUpdateVisible = false;
                } else if (data.type === 'error') {
                    this.eventSource.close();
                    this.eventSource = null;
                    this.state = 'error';
                    this.addLog('error', '錯誤: ' + data.message);
                    this.flushLogs();
                    localStorage.setItem('avlist_generating', 'false');
                }
            };

            this.eventSource.onerror = () => {
                if (this.state === 'done') return;
                this.eventSource.close();
                this.eventSource = null;
                this.state = 'error';
                this.addLog('error', '連線中斷');
                this.flushLogs();
                localStorage.setItem('avlist_generating', 'false');
            };
        } catch (e) {
            this.state = 'error';
            localStorage.setItem('avlist_generating', 'false');
            alert('發生錯誤: ' + e.message);
        }
    },

    // ===== T6d: Jellyfin Image Update Flow =====
    async runJellyfinImageUpdate() {
        if (this.isGenerating) return;

        if (this.jellyfinImageCount === 0) {
            this.showToast('沒有需要補齊的影片');
            return;
        }

        this.state = 'jellyfinUpdating';
        this.progressStatus = '準備中...';
        this.progressCurrent = 0;
        this.progressTotal = 0;
        this.clearLogs();

        localStorage.setItem('avlist_generating', 'true');

        try {
            this.eventSource = new EventSource('/api/gallery/jellyfin-update');

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === 'progress') {
                    this.progressStatus = data.status;
                    this.progressCurrent = data.current;
                    this.progressTotal = data.total;
                    localStorage.setItem('avlist_last_status', data.status);
                } else if (data.type === 'log') {
                    this.addLog(data.level, data.message);
                } else if (data.type === 'done') {
                    this.eventSource.close();
                    this.eventSource = null;
                    this.state = 'done';
                    this.progressStatus = data.message || '完成';
                    this.progressCurrent = this.progressTotal;

                    localStorage.setItem('avlist_generating', 'false');
                    localStorage.setItem('avlist_last_status', data.message || '完成');

                    // T3(40c) Codex fix: update 完成後重設 jellyfin check 狀態，讓觸發列重新出現
                    this.jellyfinImageVisible = false;
                    this.jellyfinImageCount = 0;
                    this.jellyfinCheckState = 'idle';

                    this.showToast('補齊完成！', 'success');
                    if (data.message) {
                        this.addLog('info', data.message);
                    }
                    this.flushLogs();
                } else if (data.type === 'error') {
                    this.eventSource.close();
                    this.eventSource = null;
                    this.state = 'error';
                    this.addLog('error', '錯誤: ' + data.message);
                    this.flushLogs();
                    localStorage.setItem('avlist_generating', 'false');
                }
            };

            this.eventSource.onerror = () => {
                if (this.state === 'done') return;
                this.eventSource.close();
                this.eventSource = null;
                this.state = 'error';
                this.addLog('error', '連線中斷');
                this.flushLogs();
                localStorage.setItem('avlist_generating', 'false');
            };
        } catch (e) {
            this.state = 'error';
            localStorage.setItem('avlist_generating', 'false');
            alert('發生錯誤: ' + e.message);
        }
    },

    // ===== T10: Missing NFO/Cover Enrich Methods =====
    async checkMissing() {
        try {
            const resp = await fetch('/api/gallery/missing-check');
            const result = await resp.json();
            if (!result.success) return;
            const d = result.data;
            if (d.total_missing > 0) {
                // TASK-13: 後端永遠回傳完整 items 清單；前端於 runMissingEnrich 內做 > 500 confirm gate
                this.missingBothCount = d.missing_both || 0;
                this.missingNfoCount = d.missing_nfo || 0;
                this.missingCoverCount = d.missing_cover || 0;
                this.missingItems = Array.isArray(d.items) ? d.items : [];
                this.missingPillVisible = true;
            } else {
                this.missingPillVisible = false;
            }
        } catch (e) {
            console.error('checkMissing failed:', e);
        }
    },

    async runMissingEnrich({ skipConfirm = false } = {}) {
        if (this.isGenerating || this.missingItems.length === 0) return;

        // TASK-13: 大批量 confirm gate — > 500 筆彈 modal，等用戶按確認才繼續
        if (!skipConfirm && this.missingItems.length > 500) {
            this.missingConfirmModalOpen = true;
            return;
        }

        this.state = 'enriching';
        this.missingEnrichOffset = 0;
        this.missingEnrichSuccess = 0;
        this.missingEnrichFailed = 0;
        this.progressStatus = window.t('scanner.stats.missing_enrich_loading');
        this.progressCurrent = 0;
        this.progressTotal = this.missingItems.length;
        this.clearLogs();

        const controller = new AbortController();
        this._enrichAbortController = controller;

        const items = this.missingItems.slice();  // snapshot

        try {
            while (this.missingEnrichOffset < items.length) {
                const batch = items.slice(this.missingEnrichOffset, this.missingEnrichOffset + 20);

                // Save remaining items to localStorage before each batch
                localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));

                let resp;
                try {
                    resp = await fetch('/api/batch-enrich', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ items: batch, mode: 'fill_missing' }),
                        signal: controller.signal,
                    });
                } catch (fetchErr) {
                    if (fetchErr.name === 'AbortError') {
                        // cleanup() already saved remaining items
                        return;
                    }
                    this.addLog('error', '連線失敗: ' + fetchErr.message);
                    this.flushLogs();
                    this.state = 'error';
                    // Save remaining
                    localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                    this.showToast(window.t('scanner.stats.missing_enrich_disconnect'), 'error');
                    return;
                }

                if (!resp.ok) {
                    const errText = await resp.text().catch(() => '');
                    this.addLog('error', window.t('scanner.stats.missing_enrich_batch_fail', { status: resp.status, error: errText }));
                    this.flushLogs();
                    this.state = 'error';
                    localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                    this.showToast(window.t('scanner.stats.missing_enrich_error'), 'error');
                    return;
                }

                // Read SSE stream
                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let batchDone = false;

                while (!batchDone) {
                    let readResult;
                    try {
                        readResult = await reader.read();
                    } catch (readErr) {
                        if (readErr.name === 'AbortError') return;
                        break;
                    }
                    const { done, value } = readResult;
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();  // keep incomplete last line

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        let event;
                        try {
                            event = JSON.parse(line.slice(6));
                        } catch { continue; }

                        if (event.type === 'progress') {
                            this.progressStatus = event.status || window.t('scanner.stats.missing_enrich_loading');
                            this.progressCurrent = this.missingEnrichOffset + (event.current || 0);
                            this.progressTotal = items.length;
                        } else if (event.type === 'result-item') {
                            if (event.success) {
                                this.missingEnrichSuccess++;
                            } else {
                                this.missingEnrichFailed++;
                                this.addLog('warn', `失敗: ${event.number || ''} — ${event.error || ''}`);
                            }
                        } else if (event.type === 'log') {
                            this.addLog(event.level || 'info', event.message || '');
                        } else if (event.type === 'done') {
                            batchDone = true;
                        } else if (event.type === 'error') {
                            this.addLog('error', '錯誤: ' + (event.message || ''));
                            this.flushLogs();
                            this.state = 'error';
                            localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                            this.showToast(window.t('scanner.stats.missing_enrich_stream_error'), 'error');
                            return;
                        }
                    }
                }

                // P1 fix: only advance offset if batch actually completed (got 'done' SSE event)
                if (!batchDone) {
                    this.state = 'error';
                    localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                    this.showToast(window.t('scanner.stats.missing_enrich_disconnect'), 'error');
                    return;
                }

                this.missingEnrichOffset += batch.length;
                this.progressCurrent = this.missingEnrichOffset;
            }

            // All batches complete
            localStorage.removeItem('avlist_enrich_pending');
            this.state = 'done';
            this.progressStatus = window.t('scanner.stats.missing_enrich_done');
            const summary = this.missingEnrichFailed > 0
                ? window.t('scanner.stats.missing_enrich_toast_mixed', { success: this.missingEnrichSuccess, failed: this.missingEnrichFailed })
                : window.t('scanner.stats.missing_enrich_toast_success', { success: this.missingEnrichSuccess });
            this.showToast(summary, this.missingEnrichFailed > 0 ? 'warn' : 'success');
            this.flushLogs();
            this.checkMissing();

        } catch (e) {
            if (e.name === 'AbortError') return;
            console.error('runMissingEnrich error:', e);
            this.state = 'error';
            localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
            this.showToast(window.t('scanner.stats.missing_enrich_interrupted'), 'error');
        } finally {
            if (this._enrichAbortController === controller) {
                this._enrichAbortController = null;
            }
        }
    },

    resumeMissingEnrich() {
        // TASK-13: 不在此清 localStorage；交由 runMissingEnrich 成功完成時統一清除。
        // 若補完途中失敗或用戶取消，pending 保留、下次 reload 仍可恢復。
        // skipConfirm:true — 用戶前一次已明確按過「一鍵補完」，resume 視為延續既有意圖。
        this.resumePillVisible = false;
        this.runMissingEnrich({ skipConfirm: true });
    },

    // TASK-13: confirm modal 的確認按鈕 — 跳過 confirm gate、直接啟動補完
    async confirmLargeMissingEnrich() {
        this.missingConfirmModalOpen = false;
        await this.runMissingEnrich({ skipConfirm: true });
    },

    // TASK-13: confirm modal 的取消按鈕 — 只關 modal，不清 localStorage（保留 resume 恢復點）
    cancelLargeMissingEnrich() {
        this.missingConfirmModalOpen = false;
    },

    dismissResume() {
        this.resumePillVisible = false;
        localStorage.removeItem('avlist_enrich_pending');
        // P2 fix: re-fetch DB state to repopulate missingItems (不清空，讓 pill 按鈕可用)
        this.checkMissing();
    },

    // ===== T7b: Utility =====
    copyOutputPath() {
        if (!this.outputPath) return;

        navigator.clipboard.writeText(this.outputPath).then(() => {
            this.showToast('已複製: ' + this.outputPath, 'success');
        }).catch(() => {
            alert('複製失敗，路徑：' + this.outputPath);
        });
    },

    // ===== Alias v2: Card Toggle =====
    toggleAliasCard() {
        this.aliasCardCollapsed = !this.aliasCardCollapsed;

        // 首次展開時載入別名列表
        if (!this.aliasCardCollapsed && this.aliasRecords.length === 0) {
            this.loadAliasRecords();
        }
    },

    // ===== Alias v2: Load Records =====
    async loadAliasRecords() {
        this.aliasRecordsLoading = true;
        this.aliasRecordsError = '';

        try {
            const resp = await fetch('/api/actress-aliases');
            const result = await resp.json();

            if (result.success) {
                this.aliasRecords = result.groups || [];
            } else {
                this.aliasRecordsError = '載入失敗: ' + (result.error || '未知錯誤');
            }
        } catch (e) {
            this.aliasRecordsError = '載入失敗: ' + e.message;
        } finally {
            this.aliasRecordsLoading = false;
        }
    },

    // ===== Alias v2: Filtered Records (前端 filter) =====
    filteredAliasRecords() {
        const q = this.aliasInput.trim().toLowerCase();
        if (!q) return this.aliasRecords;
        return this.aliasRecords.filter(group => {
            if (group.primary_name.toLowerCase().includes(q)) return true;
            return (group.aliases || []).some(a => a.toLowerCase().includes(q));
        });
    },

    // ===== Alias v2: Create Group =====
    async createAliasGroup() {
        const name = this.aliasInput.trim();
        if (!name) return;

        this.newGroupAdding = true;
        try {
            const resp = await fetch('/api/actress-aliases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ primary_name: name })
            });
            const result = await resp.json();

            if (result.success) {
                this.showToast('已新增別名組：' + name, 'success');
                this.aliasInput = '';
                await this.loadAliasRecords();
            } else {
                this.showToast('新增失敗: ' + (result.error || '未知錯誤'), 'error');
            }
        } catch (e) {
            this.showToast('新增失敗: ' + e.message, 'error');
        } finally {
            this.newGroupAdding = false;
        }
    },

    // ===== Alias v2: Delete Group =====
    async deleteAliasGroup(name) {
        if (!confirm(`確定要刪除「${name}」的整筆別名組嗎？`)) return;

        try {
            const resp = await fetch(`/api/actress-aliases/${encodeURIComponent(name)}`, {
                method: 'DELETE'
            });
            const result = await resp.json();

            if (result.success) {
                this.showToast('已刪除：' + name, 'success');
                await this.loadAliasRecords();
            } else {
                this.showToast('刪除失敗: ' + (result.error || '未知錯誤'), 'error');
            }
        } catch (e) {
            this.showToast('刪除失敗: ' + e.message, 'error');
        }
    },

    // ===== Alias v2: Show Add Alias Inline Input =====
    showAddAliasInput(primary) {
        this.addingAlias = { ...this.addingAlias, [primary]: '' };
    },

    // ===== Alias v2: Cancel Add Alias Inline Input =====
    cancelAddAlias(primary) {
        const updated = { ...this.addingAlias };
        delete updated[primary];
        this.addingAlias = updated;
    },

    // ===== Alias v2: Add Alias to Group (Enter key) =====
    async addAlias(primary) {
        const alias = (this.addingAlias[primary] || '').trim();
        if (!alias) return;

        this.addingAliasLoading = { ...this.addingAliasLoading, [primary]: true };
        try {
            const resp = await fetch(`/api/actress-aliases/${encodeURIComponent(primary)}/alias`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ alias })
            });
            const result = await resp.json();

            if (result.success) {
                // 清除 inline input
                const updated = { ...this.addingAlias };
                delete updated[primary];
                this.addingAlias = updated;
                await this.loadAliasRecords();
            } else {
                this.showToast(result.error || '新增別名失敗', 'error');
            }
        } catch (e) {
            this.showToast('新增別名失敗: ' + e.message, 'error');
        } finally {
            const loading = { ...this.addingAliasLoading };
            delete loading[primary];
            this.addingAliasLoading = loading;
        }
    },

    // ===== Alias v2: Remove Alias from Group =====
    async removeAlias(primary, alias) {
        try {
            const resp = await fetch(
                `/api/actress-aliases/${encodeURIComponent(primary)}/alias/${encodeURIComponent(alias)}`,
                { method: 'DELETE' }
            );
            const result = await resp.json();

            if (result.success) {
                await this.loadAliasRecords();
            } else {
                this.showToast('移除失敗: ' + (result.error || '未知錯誤'), 'error');
            }
        } catch (e) {
            this.showToast('移除失敗: ' + e.message, 'error');
        }
    },

    // ===== Alias v2: Start Online Search =====
    async startOnlineSearch() {
        const name = this.aliasInput.trim();
        if (!name) {
            this.showToast('請先輸入主名稱再進行線上搜尋');
            return;
        }

        this.onlineSearchTarget = name;
        this.onlineSearchLoading = true;
        this.onlineSearchResults = [];
        this.onlineSearchSelected = [];
        this.onlineSearchDone = false;

        try {
            const resp = await fetch('/api/actress-aliases/search-online', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name })
            });
            if (resp.status === 504) {
                this.showToast('線上搜尋逾時', 'error');
                return;
            }
            const result = await resp.json();

            if (result.success) {
                this.onlineSearchResults = result.suggested_aliases || [];
            } else {
                this.showToast('線上搜尋失敗: ' + (result.error || '未知錯誤'), 'error');
            }
        } catch (e) {
            this.showToast('線上搜尋失敗: ' + e.message, 'error');
        } finally {
            this.onlineSearchLoading = false;
            this.onlineSearchDone = true;
        }
    },

    // ===== Alias v2: Confirm Online Search Selection =====
    async confirmOnlineSearch(primary) {
        const selected = [...this.onlineSearchSelected];
        if (selected.length === 0) return;

        // 確保 primary group 存在
        const exists = this.aliasRecords.some(g => g.primary_name === primary);
        if (!exists) {
            // 先建立 group
            const createResp = await fetch('/api/actress-aliases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ primary_name: primary })
            });
            const createResult = await createResp.json();
            if (!createResult.success) {
                this.showToast('建立別名組失敗: ' + (createResult.error || '未知錯誤'), 'error');
                return;
            }
        }

        // 逐一加入選中的 alias
        for (const alias of selected) {
            try {
                const resp = await fetch(`/api/actress-aliases/${encodeURIComponent(primary)}/alias`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alias })
                });
                const result = await resp.json();
                if (!result.success) {
                    this.showToast(result.error || `加入 ${alias} 失敗`, 'error');
                }
            } catch (e) {
                this.showToast(`加入 ${alias} 失敗: ` + e.message, 'error');
            }
        }

        // 清空線上搜尋結果
        this.onlineSearchResults = [];
        this.onlineSearchSelected = [];
        this.onlineSearchTarget = '';
        this.onlineSearchDone = false;
        await this.loadAliasRecords();
    },

  };
}

// PyWebView 拖曳處理
window.handleFolderDrop = function (folderPaths) {
    if (!folderPaths || folderPaths.length === 0) {
        return;
    }

    if (typeof window.addScannerFolder !== 'function') {
        console.error('[AVList] Alpine not ready, addScannerFolder not available');
        return;
    }

    for (const folderPath of folderPaths) {
        window.addScannerFolder(folderPath);
    }
};

document.addEventListener('alpine:init', () => {
    Alpine.data('scannerPage', scannerPage);
});
