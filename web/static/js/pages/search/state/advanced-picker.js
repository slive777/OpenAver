/**
 * SearchState - Advanced Search Mixin（TASK-61c-7 / 62c-1 / 62c-2）
 *
 * 進階搜尋：長壓搜尋按鈕 → 開 62a 共用重刮彈窗上半部 → 點來源 pill 整包覆寫搜尋。
 * （62c-1：B1 radio picker 已移除，改 include _rescrape_modal.html，番號 input + 來源 pill 點擊即搜。）
 *
 * 機制重點：
 * - enabled gate / sources 清單來自 SSR 注入的 window.__ADVANCED_SEARCH__。
 * - 長壓 wiring（62c-2）已改接共用 shared/long-press.js（longPressState）：#btnSubmit 六事件 + click guard
 *   走 longPressStart/End/Cancel/ClickGuard，fire callback（openRescrape(null,'search') + 番號預填）在
 *   template arrow 傳入。US8（長壓開窗不連帶送出一般搜尋）由 longPressClickGuard 的 preventDefault 取消
 *   submit 按鈕的隱式 form 送出保護；form @submit 直接走 doSearch()（不再有 form-level submit guard）。
 * - advancedSearch(source) 走非 stream GET /api/search?q=...&mode=exact&source=<id>（stream 端點無 source param），
 *   自帶 result→Alpine state binding（整包贏由後端 search_jav_single_source 承擔；不呼叫 fallbackSearch）。
 * - OQ-3 軟提示 scaffold：metatube source + 非番號 query + 空結果 → showToast hint（B1 無 metatube source 故不觸發）。
 */

export function searchStateAdvancedPicker() {
    return {
        // ===== Helpers =====
        _advancedConfig() {
            return window.__ADVANCED_SEARCH__ || { enabled: false, sources: [] };
        },

        // ===== 進階搜尋（非 stream，整包贏）=====
        /**
         * 以指定來源覆寫搜尋（單一來源整包贏）。
         * 走非 stream GET /api/search?q=...&mode=exact&source=<id>（stream 端點無 source param）。
         * @param {string} source - 來源 id（builtin id 或 metatube:<id>）
         */
        async advancedSearch(source) {
            const query = this.searchQuery?.trim();
            if (!query || !source) return;

            // 取消現有搜尋（同 doSearch 前置）
            this.cancelSearch();
            this.requestId++;
            const currentRequestId = this.requestId;

            this.currentQuery = query;
            this.pageState = 'loading';
            this.errorText = '';

            this._fallbackAbortController = new AbortController();
            try {
                const url = `/api/search?q=${encodeURIComponent(query)}`
                    + `&mode=exact&source=${encodeURIComponent(source)}`;
                const response = await fetch(url, { signal: this._fallbackAbortController.signal });
                const data = await response.json();

                // 防競態：被新搜尋取代則丟棄
                if (currentRequestId !== this.requestId) return;

                if (response.ok && data.success && data.data && data.data.length > 0) {
                    this.currentMode = data.mode || this.currentMode;
                    this.searchResults = data.data;
                    this.currentIndex = 0;
                    this.hasMoreResults = data.has_more || false;
                    this.actressProfile = data.actress_profile || null;
                    if (this.actressProfile) this._heroCardImageError = false;
                    this.listMode = 'search';
                    this.checkLocalStatus(this.searchResults);
                    this.pageState = 'result';
                    this.preloadImages(1, 5);
                    this.hasContent = this.searchResults.length > 0 || this.fileList.length > 0;
                    this._searchSnapshot = null;
                    this._resetCoverState();
                    this.editingTitle = false;
                    this.editingChineseTitle = false;
                    this.addingTag = false;
                } else {
                    this._searchSnapshot = null;
                    this.errorText = data.error || window.t('search.error.hint');
                    this.pageState = 'error';
                    // OQ-3 軟提示 scaffold：metatube source + 非番號 query + 空結果（B1 無 metatube source 故不觸發）
                    this._advancedMaybeMetatubeHint(source, query);
                }
            } catch (err) {
                if (err.name === 'AbortError') return;
                if (currentRequestId !== this.requestId) return;
                this._searchSnapshot = null;
                console.error('[AdvancedSearch]', err);
                this.errorText = window.t('search.error.hint');
                this.pageState = 'error';
            }
        },

        // OQ-3：metatube 來源 + 非番號 + 空結果 → 軟提示（scaffold）
        _advancedMaybeMetatubeHint(source, query) {
            const isMetatube = typeof source === 'string'
                && (source.startsWith('metatube:') || this._advancedSourceIsMetatube(source));
            if (!isMetatube) return;
            // 番號格式（如 SSIS-001）→ 不提示；非番號（女優/關鍵字）→ 提示
            const looksLikeNumber = /[A-Za-z]+-?\d+/.test(query);
            if (looksLikeNumber) return;
            this.showToast(window.t('settings.advanced_search.metatube_keyword_hint'), 'info');
        },

        _advancedSourceIsMetatube(id) {
            const src = (this._advancedConfig().sources || []).find(s => s && s.id === id);
            return !!src && src.type === 'metatube';
        },
    };
}
