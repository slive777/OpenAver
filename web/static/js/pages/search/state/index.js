/**
 * SearchPage - Alpine.js Component Factory
 * 組裝所有 state mixin 模組
 *
 * 全站最後一個 Alpine 遷移：Search 頁面狀態容器
 *
 * 設計原則：
 * - T4 完成後：SearchCore + bridge.js 已消除，所有邏輯在 Alpine mixin
 */
function searchPage() {
    return {
        // Base: data + computed + helpers
        ...window.SearchStateMixin_Base(),

        // Methods from each mixin
        ...window.SearchStateMixin_Persistence,
        ...window.SearchStateMixin_SearchFlow,
        ...window.SearchStateMixin_Navigation,
        ...window.SearchStateMixin_Batch,
        ...window.SearchStateMixin_ResultCard,
        ...window.SearchStateMixin_FileList,
        ...window.SearchStateMixin_GridMode,

        // ===== T4: 拖拽事件（從 init.js 搬移）=====
        _initDragEvents() {
            let dragCounter = 0;

            document.addEventListener('dragover', (e) => {
                e.preventDefault();
            });

            document.addEventListener('dragenter', (e) => {
                e.preventDefault();
                dragCounter++;
                if (e.dataTransfer.types.includes('Files')) {
                    this.dragActive = true;
                }
            });

            document.addEventListener('dragleave', (e) => {
                e.preventDefault();
                dragCounter--;
                if (dragCounter === 0) {
                    this.dragActive = false;
                }
            });

            document.addEventListener('drop', (e) => {
                e.preventDefault();
                dragCounter = 0;
                this.dragActive = false;
                // PyWebView 環境由 Python 端處理
                if (typeof window.pywebview === 'undefined') {
                    this.handleFileDrop(e.dataTransfer.files);
                }
            });
        },

        // ===== Lifecycle =====
        async init() {
            // 1. 載入應用設定
            await this.loadAppConfig();

            // 2. 載入來源配置（供版本切換用）
            if (window.SearchUI?.loadSourceConfig) {
                await window.SearchUI.loadSourceConfig();
            }

            // 3. 還原 sessionStorage 狀態
            this.restoreState();

            // 4. 建立拖拽事件（從 init.js 搬移）
            this._initDragEvents();

            // 5. Watch state 變化並自動儲存
            this.setupAutoSave();

            // 6. 接入 page lifecycle（取代 cleanupSearchBeforeLeave + beforeunload）
            if (window.__registerPage) {
                window.__registerPage({
                    beforeLeave: () => {
                        this.saveState();
                        return true;  // search 不阻止導航，只做保存
                    },
                    onBeforeUnload: () => {
                        this.saveState();
                        return null;  // search 不觸發原生提示
                    },
                    cleanup: () => {
                        this.cleanupForNavigation();  // 關 SSE + abort fallback + requestId++
                        this._lightboxGeneration++;   // B19: invalidate pending $nextTick lightbox callbacks
                        if (this.lightboxCloseTimer) {
                            clearTimeout(this.lightboxCloseTimer);
                            this.lightboxCloseTimer = null;
                        }
                        // T2(40b): 移除 window listeners
                        if (this._pywebviewFilesHandler) {
                            window.removeEventListener('pywebview-files', this._pywebviewFilesHandler);
                        }
                        if (this._resizeHandler) {
                            window.removeEventListener('resize', this._resizeHandler);
                        }
                    }
                });
            }

            // 7. T1d: 監聽 pywebview-files 事件
            this._pywebviewFilesHandler = async (e) => { await this.setFileList(e.detail.paths); };
            window.addEventListener('pywebview-files', this._pywebviewFilesHandler);

            // 8. Issue-2: resize / 導航時更新封面高度 CSS variable
            this._resizeHandler = () => this._updateCoverHeight();
            window.addEventListener('resize', this._resizeHandler);
            this.$watch('currentIndex', () => {
                this.$nextTick(() => this._updateCoverHeight());
            });
            this.$watch('searchResults', () => {
                this._setTimer('updateCoverHeight', () => this._updateCoverHeight(), 500);
            });
        },

    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('searchPage', searchPage);
});
