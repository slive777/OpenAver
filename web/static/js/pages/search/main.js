import { searchStateBase }        from '@/search/state/base.js';
import { searchStatePersistence } from '@/search/state/persistence.js';
import { searchStateSearchFlow }  from '@/search/state/search-flow.js';
import { searchStateNavigation }  from '@/search/state/navigation.js';
import { searchStateBatch }       from '@/search/state/batch.js';
import { searchStateResultCard }  from '@/search/state/result-card.js';
import { searchStateFileList }    from '@/search/state/file-list.js';
import { searchStateGridMode }    from '@/search/state/grid-mode.js';
import { searchStateAdvancedPicker } from '@/search/state/advanced-picker.js';
import { rescrapeState }           from '@/shared/state-rescrape.js';
import { longPressState }          from '@/shared/long-press.js';

function mergeState(...parts) {
    const target = {};
    for (const part of parts) {
        Object.defineProperties(target, Object.getOwnPropertyDescriptors(part));
    }
    return target;
}

function searchPage() {
    return mergeState(
        searchStateBase(),
        searchStatePersistence(),
        searchStateSearchFlow(),
        searchStateNavigation(),
        searchStateBatch(),
        searchStateResultCard(),
        searchStateFileList(),
        searchStateGridMode(),
        searchStateAdvancedPicker(),
        rescrapeState(),
        longPressState(),
        {
            // ===== 頁面組裝層 lifecycle（從 state/index.js 搬移）=====
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
        }
    );
}

document.addEventListener('alpine:init', () => {
    Alpine.data('searchPage', searchPage);
});
