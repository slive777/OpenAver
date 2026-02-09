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

            // 7. 監聽離開前儲存
            window.addEventListener('beforeunload', () => this.saveState());

            // 8. T1d: 監聽 pywebview-files 事件
            window.addEventListener('pywebview-files', async (e) => {
                await this.setFileList(e.detail.paths);
            });
        }
    };
}
