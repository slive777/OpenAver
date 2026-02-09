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

        // Fix 1: 新增 file.js 需要的進度函數 bridge
        if (window.SearchCore) {
            window.SearchCore.initProgress = (query) => {
                this.progressLog = '搜尋中...';
                this.currentMode = '';
                this.detailDone = 0;
                this.detailTotal = 0;
                this.currentQuery = query;
            };
            window.SearchCore.updateLog = (msg) => {
                this.progressLog = msg;
            };
            window.SearchCore.handleSearchStatus = (source, status) => {
                this.handleSearchStatus(source, status);
            };
        }

        // T1c: 覆寫全域函數，指向 Alpine methods
        window.translateWithAI = () => this.translateWithAI();
        window.startEditTitle = () => this.startEditTitle();
        window.confirmEditTitle = () => this.confirmEditTitle();
        window.cancelEditTitle = () => this.cancelEditTitle();
        window.startEditChineseTitle = () => this.startEditChineseTitle();
        window.confirmEditChineseTitle = () => this.confirmEditChineseTitle();
        window.cancelEditChineseTitle = () => this.cancelEditChineseTitle();
        window.showAddTagInput = () => this.showAddTagInput();
        window.confirmAddTag = () => this.confirmAddTag();
        window.cancelAddTag = () => this.cancelAddTag();
        window.removeUserTag = (tag) => this.removeUserTag(tag);

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
    }
};
