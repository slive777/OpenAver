import { dirPath } from '@/shared/dir-path.js';

export function stateUI() {
    return {
        dirPath,
        // ===== UI State =====
        newSuffixInput: '',
        showPathHelp: false,
        showSampleImagesHelp: false,
        showCounterHelp: false,
        showThumbCacheHelp: false,
        showServerWarning: false,  // 81b-T1: 伺服器模式警語 ? popover（沿用 show*Help disclosure 模式）

        // 64b-1: 進階摺疊開關（x-collapse 驅動）
        scraperAdvanced: false,
        galleryExport: false,   // 95b-T2: 離線 HTML 匯出摺疊（預設收合，CD-95b-7）

        // Toast state
        _toast: { message: '', type: 'success', visible: false },
        _toastTimer: null,

        // Dirty Check Modal State
        dirtyCheckModalOpen: false,

        // Reset Config Modal State (T3.4)
        resetConfigModalOpen: false,
        _resetConfigLoading: false,

        // 71-T11: 開啟封面縮圖快取 Confirm Modal State
        thumbCacheConfirmOpen: false,

        // 71b-T2: 關閉封面縮圖快取 Confirm Modal State
        thumbCacheDisableConfirmOpen: false,

        // T4: 伺服器模式切換 Confirm Modal State
        serverModeConfirmOpen: false,
        serverModeConfirmValue: null,

        // B1: Scanner directory link state
        favoriteScannerLink: null,   // null=隱藏, {linked, matched_directory}=已查
        showDirDropdown: false,
        scannerDirectories: [],

        // ===== Methods =====
        showToast(message, type = 'success', duration = 2500) {
            this._toast.message = message;
            this._toast.type = type;
            this._toast.visible = true;
            if (this._toastTimer) clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(() => {
                this._toast.visible = false;
                this._toastTimer = null;
            }, duration);
        },

        async selectOutputFolder() {
            if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
                this.showToast(window.t('settings.toast.desktop_only'), 'info');
                return;
            }

            try {
                const result = await window.pywebview.api.select_folder();
                if (result && result.folder) {
                    this.form.avlistOutputDir = result.folder;
                }
            } catch (e) {
                console.error('選擇資料夾失敗:', e);
            }
        },

        // Dirty check modal — 儲存更改後離開
        async dirtyCheckSave() {
            await this.saveConfig();
            // saveConfig 成功會更新 savedState，isDirty 變 false
            if (!this.isDirty) {
                // 儲存成功，透過 lifecycle API 執行 cleanup 再跳轉
                this.dirtyCheckModalOpen = false;
                if (window.__leavePage) {
                    if (!window.__leavePage(this.pendingNavigationUrl)) return;
                }
                window.location.href = this.pendingNavigationUrl;
            }
            // 儲存失敗：modal 保持開啟，toast 已顯示錯誤
            // 用戶可選「不儲存」離開或「取消」留下
        },

        // Dirty check modal — 不儲存直接離開
        dirtyCheckDiscard() {
            this.savedState = null;  // 防止殘留
            // T3(40b): 透過 lifecycle API 執行 cleanup 再跳轉
            // __leavePage 回傳 false 表示 cleanup 阻止導航（例如仍有進行中請求）
            if (window.__leavePage) {
                if (!window.__leavePage(this.pendingNavigationUrl)) return;
            }
            window.location.href = this.pendingNavigationUrl;
        },

        // Dirty check modal — 取消（留在 settings）
        dirtyCheckCancel() {
            this.pendingNavigationUrl = '';
            this.dirtyCheckModalOpen = false;
        },

        // ─── B1: Scanner directory link ───────────────────────────────────────

        async _initB1() {
            try {
                const cfg = await fetch('/api/config').then(r => r.json());
                // response 結構：{success, data: {gallery: {directories}}}
                this.scannerDirectories =
                    (cfg.data && cfg.data.gallery && cfg.data.gallery.directories) || [];
            } catch (e) {
                console.error('[B1] _initB1: fetch /api/config failed', e);
                this.scannerDirectories = [];
            }
            // $watch 在 Alpine init() hook 內才能呼叫（由 state-config.js init() 呼叫 _initB1 後掛）
            this.$watch('form.searchFavoriteFolder', () => this.refreshScannerLink());
            // 初始刷新一次（反映 loadConfig 填好的值）
            await this.refreshScannerLink();
        },

        async refreshScannerLink() {
            const fav = (this.form && this.form.searchFavoriteFolder) || '';
            if (!fav.trim()) {
                this.favoriteScannerLink = null;
                return;
            }
            try {
                const resp = await fetch(
                    '/api/settings/favorite-scanner-link?favorite=' + encodeURIComponent(fav)
                );
                this.favoriteScannerLink = await resp.json();
            } catch (e) {
                console.error('[B1] refreshScannerLink failed', e);
                this.favoriteScannerLink = null;
            }
        },

        pickScannerDirectory(dir) {
            if (this.form) this.form.searchFavoriteFolder = dir;
            this.showDirDropdown = false;
            this.refreshScannerLink();
        },
    };
}
