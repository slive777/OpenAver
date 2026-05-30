/**
 * state-rescrape.js — 進階重新刮削 Alpine state mixin（62a-3）
 *
 * 填滿 _rescrape_modal.html partial（62a-2）的 state/method 契約：
 *   pick（番號 + 來源 pill）→ pill 點擊即搜（/api/rescrape/preview）→ loading
 *   → preview（transient）/ not-found → ✗ 回上一步 / ✓ commit（/api/enrich-single,
 *   mode=refresh_full + overwrite_existing=true）→ 成功 refreshVideoData + toast → close。
 *
 * 放 shared/ 供 Showcase（62b）+ Search（62c）共用，不需搬檔。
 *
 * 設計約束：
 *   - factory function（export function rescrapeState），透過 rescrapeState.call(this)
 *     接入 main.js mergeState（與 stateSimilar 同模式；descriptor-preserving）。
 *   - method 非 getter（規避 Alpine reactivity 凍結；CD-62-14 #0）。
 *   - transient preview 走私有 _rescrapeVideo，絕不寫 lightbox 的當前影片 state（CD-62-2）。
 *   - cover 只存端點回的遠端 URL 原值；proxy-image URL 由 partial 內聯建構（CD-62-14 #8）。
 *
 * 鏡像 enrichVideo（state-lightbox.js）的 _enriching → fetch enrich-single → 成功
 * refreshVideoData + toast → finally 釋放 guard 結構，差異：mode=refresh_full、
 * overwrite_existing=true、帶 source、guard 名 _rescraping。
 */

import { pathToDisplay } from '@/components/path-utils.js';

export function rescrapeState() {
    return {
        // ── 彈窗狀態（平鋪，對齊 partial 綁定 + mockup） ──
        rescrapeOpen: false,
        rescrapeStep: 'pick',              // 'pick' | 'preview'
        rescrapeEntryPoint: 'lightbox',    // 'lightbox' | 'enrich' | 'search'
        rescrapeNumber: '',
        rescrapeOriginalFilename: '',
        rescrapeSources: [],
        rescrapeLoadingSource: null,       // string | null（明確，:disabled 純 boolean）
        rescrapePreview: null,             // transient（CD-62-2）
        rescrapeNotFound: false,

        // ── private ──
        _rescraping: false,                // commit 連點 guard（鏡像 _enriching）
        _rescrapeVideo: null,              // commit 時 refreshVideoData 對象（私有，非 lightbox 當前 state）
        _rescrapeCommitSource: null,       // 進 preview 用的 source（commit 沿用，auto→null 映射前原值）

        /**
         * 開啟彈窗（62b-1 wire ⚙ / 🔍 長壓呼叫；search 入口傳 video=null）。
         */
        openRescrape(video, entryPoint = 'lightbox') {
            this.rescrapeOpen = true;
            this.rescrapeStep = 'pick';
            this.rescrapeEntryPoint = entryPoint;
            this.rescrapeNumber = (video && video.number) || '';
            this.rescrapeOriginalFilename = (video && video.path)
                ? pathToDisplay(video.path).split(/[\\/]/).pop()
                : '';
            this.rescrapeSources = (window.__ADVANCED_SEARCH__ && window.__ADVANCED_SEARCH__.sources) || [];
            this.rescrapePreview = null;
            this.rescrapeLoadingSource = null;
            this.rescrapeNotFound = false;
            this._rescrapeVideo = video;
        },

        /**
         * builtin pill 清單（method 非 getter；enabled-first + order）。鏡像 mockup builtinSources。
         */
        rescrapeBuiltinSources() {
            return this.rescrapeSources
                .filter(s => s.type === 'builtin')
                .sort((a, b) => (b.enabled - a.enabled) || (a.order - b.order));
        },

        /**
         * 解析 preview 卡的來源顯示名（落差#1：端點回 source id，partial 綁 sourceName）。
         */
        _resolveSourceName(sourceId) {
            if (sourceId === 'auto') return window.t('showcase.rescrape.auto_source');
            const s = this.rescrapeSources.find(x => x.id === sourceId);
            if (s) return s.display_name_raw || s.display_name_key || s.id;
            return sourceId;
        },

        /**
         * pill 點擊即搜（POST /api/rescrape/preview）。
         */
        async rescrapeWithSource(sourceId) {
            if (this.rescrapeLoadingSource !== null) return;          // 連點防護
            if (!this.rescrapeNumber.trim()) { this.rescrapeNotFound = true; return; }
            this.rescrapeNotFound = false;
            this.rescrapeLoadingSource = sourceId;
            try {
                const resp = await fetch('/api/rescrape/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        number: this.rescrapeNumber.trim(),
                        source: sourceId,
                    }),
                });
                const data = await resp.json();
                if (this.rescrapeEntryPoint === 'search') {
                    // Search 入口：62c-1 接結果區；本 task 先 close（成功）/ 標 not-found（失敗）
                    if (data && data.success) {
                        this.closeRescrape();
                    } else {
                        this.rescrapeNotFound = true;
                    }
                    return;
                }
                // Showcase（lightbox / enrich）：找到 → 換頁 preview；找不到 → 留 pick
                if (data && data.success) {
                    this.rescrapePreview = { ...data, sourceName: this._resolveSourceName(sourceId) };
                    this._rescrapeCommitSource = sourceId;
                    this.rescrapeStep = 'preview';
                } else {
                    this.rescrapeNotFound = true;
                }
            } catch (e) {
                this.rescrapeNotFound = true;
            } finally {
                this.rescrapeLoadingSource = null;
            }
        },

        /**
         * 回上一步（保留 number + sources，清 preview 讓用戶重選源）。
         */
        rescrapeBackToPick() {
            this.rescrapeStep = 'pick';
            this.rescrapePreview = null;
            this.rescrapeNotFound = false;
        },

        /**
         * ✓ commit — 自包含覆蓋寫入（POST /api/enrich-single）。鏡像 enrichVideo。
         */
        async rescrapeConfirm() {
            if (this._rescraping) return;                            // 連點防護
            if (!this._rescrapeVideo || !this._rescrapeVideo.path) return;  // commit 需既有檔（對齊 enrichVideo guard；search 入口無檔不 commit）
            this._rescraping = true;
            try {
                const commitSource = (this._rescrapeCommitSource === 'auto') ? null : this._rescrapeCommitSource;
                const resp = await fetch('/api/enrich-single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: this._rescrapeVideo.path,
                        number: this.rescrapeNumber.trim(),
                        source: commitSource,                        // auto→null 映射
                        mode: 'refresh_full',                        // CD-62-0/4：固定覆蓋
                        overwrite_existing: true,                    // CD-62-4：唯一合法組合
                        write_nfo: true,
                        write_cover: true,
                    }),
                });
                const result = await resp.json();
                if (result.success) {
                    await this.refreshVideoData?.(this._rescrapeVideo);   // CD-62-5（showcase 有、search 無）
                    this.showToast(window.t('showcase.rescrape.success'), 'success');
                    this.closeRescrape();
                } else {
                    this.showToast(result.error || window.t('showcase.rescrape.fail'), 'error');
                }
            } catch (e) {
                this.showToast(window.t('showcase.rescrape.fail'), 'error');
            } finally {
                this._rescraping = false;
            }
        },

        /**
         * 關閉彈窗（reset transient；_rescrapeVideo/_rescrapeCommitSource 下次 open 覆寫）。
         */
        closeRescrape() {
            this.rescrapeOpen = false;
            this.rescrapeStep = 'pick';
            this.rescrapePreview = null;
            this.rescrapeNotFound = false;
            this.rescrapeLoadingSource = null;
        },
    };
}
