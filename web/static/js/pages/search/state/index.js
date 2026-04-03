/**
 * SearchPage - Alpine.js Component Factory
 * 組裝所有 state mixin 模組
 *
 * 全站最後一個 Alpine 遷移：Search 頁面狀態容器
 *
 * 設計原則：
 * - T1a 階段只建立骨架，不遷移邏輯（保持現有功能可用）
 * - Bridge Layer：Alpine state ↔ 舊 window.SearchCore namespace
 * - 逐步在 T1b-T1d 遷移各模組功能
 */
function searchPage() {
    return {
        // Base: data + computed + helpers
        ...window.SearchStateMixin_Base(),

        // Methods from each mixin
        ...window.SearchStateMixin_Persistence,
        ...window.SearchStateMixin_SearchFlow,
        ...window.SearchStateMixin_Navigation,
        ...window.SearchStateMixin_ResultCard,
        ...window.SearchStateMixin_FileList,
        ...window.SearchStateMixin_Batch,
        ...window.SearchStateMixin_Bridge,
        ...window.SearchStateMixin_GridMode,

        // ===== Lifecycle =====
        async init() {
            // 1. 初始化舊 JS 的 DOM references（必須在 DOM ready 後）
            if (window.SearchCore?.initDOM) {
                window.SearchCore.initDOM();
            }

            // 2. 載入應用設定
            await this.loadAppConfig();

            // 3. 載入來源配置（供版本切換用）
            if (window.SearchUI?.loadSourceConfig) {
                await window.SearchUI.loadSourceConfig();
            }

            // 4. 還原 sessionStorage 狀態
            this.restoreState();

            // 5. 建立 Bridge Layer：舊 JS 可透過 window.SearchCore.state 讀寫 Alpine state
            this.setupBridgeLayer();

            // 6. Watch state 變化並自動儲存
            this.setupAutoSave();

            // 7. 接入 page lifecycle（取代 cleanupSearchBeforeLeave + beforeunload）
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

            // 8. T1d: 監聽 pywebview-files 事件
            this._pywebviewFilesHandler = async (e) => { await this.setFileList(e.detail.paths); };
            window.addEventListener('pywebview-files', this._pywebviewFilesHandler);

            // 9. Issue-2: resize / 導航時更新封面高度 CSS variable
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
