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
import { browseDirState }          from '@/shared/state-browse-dir.js';
import { toastState }              from '@/shared/state-toast.js';
import { searchStateWishlist }    from '@/search/state/wishlist.js';
import { searchStateEmptyExplainer } from '@/search/state/empty-explainer.js';
import { searchStateMakerLatest }    from '@/search/state/maker-latest.js';
import { searchStateBlankCard }      from '@/search/state/blank-card.js';
import { mergeState }              from '@/shared/merge-state.js';

let _dragTimeoutHandle = null;

// TASK-138-T3（CD-A2）：逾時門檻需 > 瀏覽器原生 dragover 心跳間隔（WHATWG 規範值 350ms）。
// 目前實測值與安全餘裕見 plan-138.md「CD-A2」。兩頁常數值與本注解必須逐字相同（CD-A5）。
// 必須 export——測試要 import 這個常數本身去驅動 mock.timers.tick()，不得在測試檔裡另抄一份數字。
export const DRAG_OVERLAY_TIMEOUT_MS = 1200; // 待 T3 實測覆核（見「驗證方式」CD-A2 量測步驟）

export function searchPage() {
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
        browseDirState(),
        toastState(),
        searchStateWishlist(),
        searchStateEmptyExplainer(),
        searchStateMakerLatest(),
        searchStateBlankCard(),
        {
            // ===== 頁面組裝層 lifecycle（從 state/index.js 搬移）=====
            _armDragHeartbeat(e) {
                if (!e.dataTransfer.types.includes('Files')) return;
                if (!this.dragActive) this.dragActive = true;   // CD-A4：值沒變就不寫
                clearTimeout(_dragTimeoutHandle);
                _dragTimeoutHandle = setTimeout(() => this._onDragTimeout(), DRAG_OVERLAY_TIMEOUT_MS);
            },

            _onDragTimeout() {
                if (this.dragActive) this.dragActive = false;   // CD-A4
                _dragTimeoutHandle = null;
            },

            _onDrop(e) {
                clearTimeout(_dragTimeoutHandle);
                _dragTimeoutHandle = null;
                if (this.dragActive) this.dragActive = false;
                if (typeof window.pywebview === 'undefined') {
                    this.handleFileDrop(e.dataTransfer.files);
                }
            },

            _initDragEvents() {
                document.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    this._armDragHeartbeat(e);
                });
                document.addEventListener('drop', (e) => {
                    e.preventDefault();
                    this._onDrop(e);
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
                this.loadMakerCapsules();   // 不 await：吞錯在方法內，膠囊晚到不擋 init

                // 4. 載入書籤數量（badge；失敗不擋後續 init）
                await this.loadWishlistCount();

                // 5. 建立拖拽事件（從 init.js 搬移）
                this._initDragEvents();

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
        }
    );
}

document.addEventListener('alpine:init', () => {
    Alpine.data('searchPage', searchPage);
});
