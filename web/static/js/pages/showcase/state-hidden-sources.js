/**
 * state-hidden-sources.js — Showcase ESM（195b-T4）
 *
 * 「隱藏未連線硬碟」資料層：把全庫（_allVideos）切成可見（_videos）與被藏，
 * 並讓牆／片數／燈箱／相似結果跟著收斂。
 *
 * - 維持 mergeState 分片（CD-195-5）：按鈕在 footer，被影響的牆／相似／燈箱散在各處，
 *   外面（燈箱、init）需要知道開關。**不帶 init()**（FE-ALPINE-05）——初始化掛在
 *   state-base.js init() 內呼叫 _hsInit()。
 * - 大陣列 _allVideos／_videos 在 state-base.js 模組級（reactive scope 外，FE-ALPINE-18），
 *   所以衍生值（hiddenCount）一律賦值、不寫 getter。
 * - 純函式在 shared/hidden-sources.js；本檔只管 state 與時序。
 */

import { _videos, _allVideos, _filteredVideos, _setVideos } from '@/showcase/state-base.js';
import { computeHiddenIndexes, isHiddenVideo, splitVisible, hiddenNumberSet, footerNotice } from '@/shared/hidden-sources.js';
import { sameWork } from './work-versions.js';

// 首屏最多等 source-status 這麼久（開關為開時）；逾時只是不再等，請求不取消、晚到的回應照樣套用。
const STATUS_TIMEOUT_MS = 3000;

function _sameSet(a, b) {
    if (a.size !== b.size) return false;
    for (const x of a) if (!b.has(x)) return false;
    return true;
}

export function stateHiddenSources() {
    return {

        // --- 無條件宣告初值（FE-ALPINE-06）---
        hideUnreachable: false,         // 設定值（restoreState 從 config 讀；hsSetHide 切換）
        hiddenCount: 0,                 // 被藏片數；一律重新賦值（FE-ALPINE-18）
        hiddenSrcIdx: new Set(),        // 被藏來源的索引；整個重新賦值、不原地改；開關為關時恆空
        _hsStatusInFlight: null,        // 飛中的 source-status promise（去重）
        _hsSources: [],                 // 最近一次 /api/showcase/videos 的 sources
        _hsOfflineKeys: [],             // 最近一次 source-status 中 reason==='unreachable' 各項 members 合併
        _hsHiddenNumbers: new Set(),    // 被藏片的大寫番號（相似結果濾除用）
        _hsVisibilityHandler: null,     // visibilitychange handler（FE-ALPINE-06）
        _hsFocusHandler: null,          // window focus handler
        _hsPageshowHandler: null,       // pageshow（頁面存活期只掛一次，cleanup 不拆）

        // 由 hideUnreachable／_hsSources／_hsOfflineKeys 算出可見清單與片數；不呼叫 applyFilterAndSort。
        _recomputeVisible() {
            const idx = this.hideUnreachable === true
                ? computeHiddenIndexes(this._hsSources, this._hsOfflineKeys)
                : new Set();
            const { visible, hidden } = splitVisible(_allVideos, idx);
            this.hiddenSrcIdx = idx;
            _setVideos(visible);
            this.videoCount = _videos.length;
            this.hiddenCount = _allVideos.length - _videos.length;
            this._hsHiddenNumbers = hiddenNumberSet(hidden, visible);
        },

        // 隱藏集合沒變就整段 no-op（applyFilterAndSort 會把頁碼重置為 1）；有變才重篩並收斂燈箱。
        _hsRefresh() {
            const before = this.hiddenSrcIdx;
            this._recomputeVisible();
            if (_sameSet(before, this.hiddenSrcIdx)) return;
            // init 窗口內（_heroCardReconcilePending）init() 自己緊接著會 applyFilterAndSort(true)，這裡不先畫一次；
            // 被略過的燈箱收斂由 init() 在最終 apply 後補做（state-base.js）。
            if (this._heroCardReconcilePending === true) return;
            this.applyFilterAndSort();
            this._hsConvergeLightbox();
        },

        // GET /api/showcase/source-status。失敗／非 ok／非陣列 ⇒ 完全不改既有 state（FE-TIMING-12）。
        // opts.timeout（ms）：回傳逾時降級包裝——到時 resolve、不取消原請求，晚到的回應照樣套用。
        _hsFetchStatus(opts) {
            if (!this._hsStatusInFlight) {
                const run = (async () => {
                    let list = null;
                    try {
                        const resp = await fetch('/api/showcase/source-status' + (opts && opts.recheck ? '?recheck=1' : ''));
                        if (resp.ok) {
                            const data = await resp.json();
                            if (Array.isArray(data)) list = data;
                        }
                    } catch (_e) { /* 保留舊值 */ }
                    if (list === null) return;
                    this.unreachableSources = list;
                    this._hsOfflineKeys = list
                        .filter((it) => it && it.reason === 'unreachable')
                        .flatMap((it) => (Array.isArray(it.members) ? it.members : []));
                    this._hsRefresh();
                })();
                this._hsStatusInFlight = run;
                run.then(
                    () => { this._hsStatusInFlight = null; },
                    (e) => { this._hsStatusInFlight = null; console.error('[Showcase] hidden-sources status apply failed:', e); },
                );
            }
            const inflight = this._hsStatusInFlight;
            const ms = opts && opts.timeout;
            if (!(ms > 0)) return inflight;
            return new Promise((resolve) => {
                const timer = setTimeout(resolve, ms);
                const done = () => { clearTimeout(timer); resolve(); };
                inflight.then(done, done);
            });
        },

        // init() 呼叫：開關為關 ⇒ fire-and-forget（今天的路徑）；為開 ⇒ 回逾時降級 promise 讓 init 最多等 3 秒。
        _hsInit() {
            this._hsBindRecheck();
            if (this.hideUnreachable !== true) {
                this._hsFetchStatus();
                return Promise.resolve();
            }
            return this._hsFetchStatus({ timeout: STATUS_TIMEOUT_MS });
        },

        // C-1 不變式：燈箱開著時隱藏集合改變 → 燈箱不能停在被藏的片上，也不能讓「下一部」跳錯片。
        _hsConvergeLightbox() {
            const cur = this.currentLightboxVideo;
            if (!this.lightboxOpen || !cur) return;
            if (isHiddenVideo(cur, this.hiddenSrcIdx)) {
                this.closeLightbox();
                return;
            }
            // standalone 相似退出時 lightboxIndex 本來就是舊值（R-10 不納入），不重新對位
            if (this.similarExitVideo) return;
            // 198b-T6：燈箱可能停在非顯示版本，以「該作品含有 cur 這個 path」對位（FE-ALPINE-14：path 比對）
            const idx = _filteredVideos.findIndex((v) => sameWork(v, cur));
            if (idx >= 0 && idx !== this.lightboxIndex) this.lightboxIndex = idx;
        },

        // 樂觀切換 → PUT 存檔；存檔失敗（reject／非 ok／success:false）還原並跳一次 toast。
        async hsSetHide(next) {
            if (typeof next !== 'boolean' || next === this.hideUnreachable) return;
            const prev = this.hideUnreachable;
            this.hideUnreachable = next;
            this._hsRefresh();
            let saved = false;
            try {
                const resp = await fetch('/api/config/gallery/hide-unreachable-sources', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: next }),
                });
                if (resp.ok) {
                    const data = await resp.json();
                    saved = !!data && data.success === true;
                }
            } catch (_e) { saved = false; }
            if (saved) return;
            if (this.hideUnreachable === next) {   // 沒被後一次切換蓋過才還原
                this.hideUnreachable = prev;
                this._hsRefresh();
            }
            this.showToast(window.t('showcase.status.source_hide_save_failed'), 'error');
        },

        // 模板多次呼叫：純讀、無副作用。
        hsNotice() {
            return footerNotice(this.unreachableSources, this.hideUnreachable, this.hiddenCount, window.t);
        },

        // 切回視窗重驗：I-4 同輪／在飛去重；document.hidden 單獨一行（mutation M1）。
        _hsRecheck() {
            if (document.hidden === true) return;
            if (this._hsStatusInFlight) return;
            this._hsFetchStatus({ recheck: true });
        },

        // 冪等：已綁 visibility／focus 就 return；pageshow 頁面存活期只掛一次、cleanup 不拆（FE-TIMING-14）。
        _hsBindRecheck() {
            if (this._hsVisibilityHandler) return;
            this._hsVisibilityHandler = () => { this._hsRecheck(); };
            this._hsFocusHandler = () => { this._hsRecheck(); };
            document.addEventListener('visibilitychange', this._hsVisibilityHandler);
            window.addEventListener('focus', this._hsFocusHandler);
            if (!this._hsPageshowHandler) {
                this._hsPageshowHandler = (event) => {
                    if (event && event.persisted === true) this._hsBindRecheck();
                };
                window.addEventListener('pageshow', this._hsPageshowHandler);
            }
        },

        // 拆 visibility／focus；handler 欄位設回 null。pageshow 不拆。
        _hsUnbindRecheck() {
            if (this._hsVisibilityHandler) {
                document.removeEventListener('visibilitychange', this._hsVisibilityHandler);
                this._hsVisibilityHandler = null;
            }
            if (this._hsFocusHandler) {
                window.removeEventListener('focus', this._hsFocusHandler);
                this._hsFocusHandler = null;
            }
        },

    };
}
