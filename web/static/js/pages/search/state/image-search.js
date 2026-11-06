/**
 * SearchState - Image Search Mixin（TASK-193-T7）
 * 丟一張圖查番號：查詢期間原畫面不動；avscan 回番號就換成格狀（第一格預留給使用者的圖），
 * 逐部補上；任何其他搜尋接手結果集，圖片 session 自動失效。
 *
 * 身分比較（FE-ALPINE-14）：只有「陣列」身分走 rawOf + isSessionFor；
 * 查詢／session／迴圈一律比原始型別（url 字串、loop 正整數）。
 */
import { validateImageFile, isSessionFor, isPristine } from '../image-search-rules.js';

let _loopSeq = 0;

function rawOf(x) {
    if (x == null) return x;
    return typeof Alpine !== 'undefined' && Alpine.raw ? Alpine.raw(x) : x;
}

function failureToast(data) {
    const code = data && typeof data.error === 'string' ? data.error : 'unreachable';
    if (code === 'rate_limited') {
        const seconds = Math.max(1, Math.ceil(Number(data.retry_after) || 5));
        return { text: window.t('search.image.rate_limited', { seconds }), type: 'warning' };
    }
    if (code === 'file_too_large') return { text: window.t('search.image.too_large'), type: 'error' };
    if (code === 'unsupported_image') return { text: window.t('search.image.unsupported'), type: 'error' };
    return { text: window.t('search.image.unreachable'), type: 'error' };
}

export function searchStateImageSearch() {
    return {
    // ===== State =====
    imgSearchPhase: 'idle',      // 'idle' | 'querying'
    imgSearchMoveSeq: 0,         // 使用者動過檢視的計數（T10 切換鈕接線）
    imgSearchPending: null,      // null | { url }：進行中查詢的 object URL
    imgSearchSession: null,      // null | { url, bound, matches, clearHit, lead, loop }
    imgThumbVisible: false,

    // ===== Getters =====
    get imgSearchActive() {
        return isSessionFor(rawOf(this.searchResults), rawOf(this.imgSearchSession?.bound));
    },

    get imgSearchHeld() {
        const session = this.imgSearchSession;
        if (!session) return false;
        return this.imgSearchActive
            || isSessionFor(rawOf(this._searchSnapshot?.searchResults), rawOf(session.bound));
    },

    get imgSearchLooking() {
        return !!this.imgSearchSession?.loop && this.imgSearchActive;
    },

    get imgSearchShown() {
        return this.imgSearchActive && this.listMode === 'search';
    },

    get imgThumbSrc() {
        if (this.imgSearchPending?.url) return this.imgSearchPending.url;
        return this.imgSearchShown && this.imgThumbVisible ? this.imgSearchSession.url : '';
    },

    get searchBoxFilled() {
        return (this.searchQuery || '').trim() !== '' || this.imgThumbSrc !== '';
    },

    get showClearBtn() {
        return !this.imgSearchLooking && (this.hasContent || (this.pageState !== 'loading' && this.searchBoxFilled));
    },

    get showImageBtn() {
        return !this.showClearBtn && this.pageState !== 'loading' && !this.imgSearchLooking;
    },

    // ===== Methods =====
    currentMatch() {
        if (!this.imgSearchShown) return null;
        return this.imgSearchSession.matches[this.currentIndex] ?? null;
    },

    _imgSearchOwns(arr) {
        return isSessionFor(rawOf(arr), rawOf(this.imgSearchSession?.bound));
    },

    imgSearchNoteMove() {
        this.imgSearchMoveSeq++;
    },

    imgSearchOnInput() {
        this.imgThumbVisible = false;
    },

    imgSearchOnClear() {
        if (this.imgSearchPhase === 'querying') {
            this.imgSearchAbortQuery();
            return;
        }
        this._abortControllers.imgSearchLookup?.abort();
        this.clearAll();
        this._imgSearchDropSession();
    },

    imgSearchOnCancel() {
        if (this.imgSearchLooking) {
            this.imgSearchStopLookup();
        } else {
            this.cancelSearch();
        }
    },

    imgSearchAbortQuery() {
        const pending = this.imgSearchPending;
        if (!pending) return;
        this._abortControllers.imgSearchUpload?.abort();
        URL.revokeObjectURL(pending.url);
        this.imgSearchPending = null;
        this.imgSearchPhase = 'idle';
    },

    imgSearchStopLookup() {
        if (!this.imgSearchLooking) return;
        this._abortControllers.imgSearchLookup?.abort();
        this.imgSearchSession.loop = null;
        const n = this.searchResults.length;
        for (let idx = 0; idx < n; idx++) {
            const r = this.searchResults[idx];
            if (r && r._skeleton) {
                this._imgSearchSettle(idx, { number: r.number, _notFound: true, cover: '' });
            }
        }
    },

    _imgSearchDropSession() {
        const session = this.imgSearchSession;
        if (!session) return;
        URL.revokeObjectURL(session.url);
        this.imgSearchSession = null;
        this.imgThumbVisible = false;
    },

    imgSearchCleanup() {
        this.imgSearchAbortQuery();
        this._abortControllers.imgSearchLookup?.abort();
        this._imgSearchDropSession();
    },

    // 全分片唯一寫 searchResults[idx] 的地方；呼叫端負責在呼叫前確認 session 仍存活
    _imgSearchSettle(idx, item) {
        this.searchResults[idx] = item;
        this._candidateReplaceSeq++;
        this.checkLocalStatus([this.searchResults[idx]]);
        this.$nextTick(() => {
            if (!(this.imgSearchActive && this.displayMode === 'grid')) return;
            const cardEl = document.querySelector(`.search-grid [data-slot="${idx}"]`);
            if (cardEl) window.SearchAnimations?.playMiniBurst?.([cardEl], null);
        });
    },

    async imgSearchStart(file) {
        // A. 前置（同步）
        if (!file) return;
        if (!validateImageFile(file).ok) {
            this.showToast(window.t('search.image.too_large'), 'error');
            return;
        }
        if (this.imgSearchSession && !this.imgSearchActive && !this.imgSearchHeld) {
            this._imgSearchDropSession();
        }
        this.imgSearchAbortQuery();
        const url = URL.createObjectURL(file);
        this.imgSearchPending = { url };
        this.imgSearchPhase = 'querying';

        // B. 查詢階段：不碰原畫面
        const mine = () => this.imgSearchPending?.url === url;
        const signal = this._getAbortSignal('imgSearchUpload');
        let data = null;
        try {
            const fd = new FormData();
            fd.append('file', file);
            const resp = await fetch('/api/image-search', { method: 'POST', body: fd, signal });
            if (!mine()) return;
            try { data = await resp.json(); } catch { data = null; }
            if (!mine()) return;
        } catch {
            if (!mine()) return;
            data = null;
        } finally {
            this._clearAbort('imgSearchUpload', signal);
        }
        const candidates = data?.success === true && Array.isArray(data.candidates) ? data.candidates : [];
        if (candidates.length === 0) {
            URL.revokeObjectURL(url);
            this.imgSearchPending = null;
            this.imgSearchPhase = 'idle';
            const { text, type } = failureToast(data);
            this.showToast(text, type);
            return;
        }

        // C. 終局替換（同步一次做完，中間不得有 await）
        const oldUrl = this.imgSearchSession?.url;
        if (this._isSearchInFlight()) this.cancelSearch();
        this.clearAll();
        this._gridImageErrors = new Set();
        this._actressFavoriteLoading = false;
        this._resetCoverState();
        this._searchSnapshot = null;
        const loopId = ++_loopSeq;
        const arr = candidates.map((c) => ({ number: c.number, _skeleton: true }));
        const session = { url, bound: arr, matches: candidates, clearHit: data.clear_hit, lead: data.lead, loop: loopId };
        this.searchResults = arr;
        this.imgSearchSession = session;
        this.imgSearchPending = null;
        this.imgSearchPhase = 'idle';
        this.imgThumbVisible = true;
        this.listMode = 'search';
        this.displayMode = 'grid';
        this.pageState = 'result';
        this.currentIndex = 0;
        this.currentMode = 'exact';
        this.hasMoreResults = false;
        this.currentCursor = null;
        this.actressProfile = null;
        this._heroSlotReserved = false;
        const baseline = { lightboxGen: this._lightboxGeneration, moveSeq: this.imgSearchMoveSeq };
        if (oldUrl) URL.revokeObjectURL(oldUrl);

        // D. 逐部查詢（循序）
        const alive = () => this.imgSearchSession?.url === url
            && this.imgSearchSession.loop === loopId
            && isSessionFor(rawOf(this.searchResults), arr);
        const notFound = (c) => ({ number: c.number, _notFound: true, cover: '' });
        for (let i = 0; i < candidates.length; i++) {
            if (!alive()) return;
            const c = candidates[i];
            let item;
            if (!c.searchable) {
                item = notFound(c);
            } else {
                const sig = this._getAbortSignal('imgSearchLookup');
                try {
                    const r = await fetch('/api/search?q=' + encodeURIComponent(c.number) + '&mode=auto&limit=1', { signal: sig });
                    if (!alive()) return;
                    const body = r.ok ? await r.json() : null;
                    if (!alive()) return;
                    item = body?.success === true && body.data?.[0] ? body.data[0] : notFound(c);
                } catch {
                    if (!alive()) return;
                    item = notFound(c);
                } finally {
                    this._clearAbort('imgSearchLookup', sig);
                }
            }
            if (!alive()) return;
            this._imgSearchSettle(i, item);
            if (i === 0) {
                const now = {
                    active: this.imgSearchActive,
                    listMode: this.listMode,
                    displayMode: this.displayMode,
                    currentIndex: this.currentIndex,
                    lightboxOpen: this.lightboxOpen,
                    lightboxGen: this._lightboxGeneration,
                    moveSeq: this.imgSearchMoveSeq,
                };
                if (isPristine(baseline, now)) this.toggleDisplayMode();
            }
        }
        if (alive()) this.imgSearchSession.loop = null;
    },
    };
}
