/**
 * SearchState - Bridge Mixin
 * 包含：舊 JS 與 Alpine 的橋接層（setupBridgeLayer）
 */
window.SearchStateMixin_Bridge = {
    // ===== Bridge Layer =====
    // 修正 2: 簡化 Bridge Layer（不覆寫 window.SearchCore.state）
    setupBridgeLayer() {
        // T1a: 最小化 bridge — 只接管 saveState/clearState
        // pageState 由 showState() 同步（見 ui.js 修改）
        // hasContent 由 updateClearButton() 同步（見 core.js 修改）

        if (window.SearchCore) {
            // 接管 saveState / clearState，讓 Alpine 的 $watch auto-save 可運作
            window.SearchCore.saveState = () => this.saveState();
            window.SearchCore.clearState = () => this.clearState();
        }

        // T1b: 新增搜尋流程 bridge
        // 讓舊 JS 可以觸發 Alpine 搜尋
        if (window.SearchCore) {
            window.SearchCore.doSearch = (query) => this.doSearch(query);
        }
        if (window.SearchUI) {
            window.SearchUI.navigateResult = (delta) => this.navigate(delta);
        }

        // T1d: file.js functions now in Alpine
        if (window.SearchFile) {
            window.SearchFile.switchToFile = (index, position, showFullLoading) =>
                this.switchToFile(index, position, showFullLoading);
            window.SearchFile.searchAll = () => this.searchAll();
            window.SearchFile.scrapeAll = () => this.scrapeAll();
            window.SearchFile.setFileList = (paths) => this.setFileList(paths);
            window.SearchFile.handleFileDrop = (files) => this.handleFileDrop(files);
            window.SearchFile.renderFileList = () => {}; // no-op
            window.SearchFile.renderSearchResultsList = () => {}; // no-op
        }

        // T6b: Toast bridge（供外部 JS 如 ui.js 的 showSourceToast 使用）
        if (window.SearchUI) {
            window.SearchUI.showToast = (message, type = 'success', duration = 2500) =>
                this.showToast(message, type, duration);
        }

        // V1c: searchQuery 雙寫策略 — Alpine state → DOM 同步（遷移期相容）
        this.$watch('searchQuery', (newValue) => {
            const dom = window.SearchCore?.dom;
            if (dom?.queryInput && dom.queryInput.value !== newValue) {
                dom.queryInput.value = newValue;
            }
        });
    }
};
