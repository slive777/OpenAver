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
        rescrapeEntryPoint: 'lightbox',    // 'lightbox' | 'search' | 'switch-source'
        rescrapeNumber: '',
        rescrapeOriginalFilename: '',
        // 74a US2：init 即從 SSR bootstrap 灌入（rescrapeState() 在 mergeState 時呼叫，
        // 早於此的 _advanced_search_bootstrap.html 已設好 window.__ADVANCED_SEARCH__）。
        // 結果面板來源膠囊在 picker 開啟前就要 _resolveSourceName，故不能等 openRescrape 才填，
        // 否則膠囊顯示 raw id（'javbus'）而非顯示名（'JavBus'）。openRescrape 仍每次重灌（belt-and-suspenders）。
        rescrapeSources: (window.__ADVANCED_SEARCH__ && window.__ADVANCED_SEARCH__.sources) || [],
        rescrapeLoadingSource: null,       // string | null（明確，:disabled 純 boolean）
        rescrapePreview: null,             // transient（CD-62-2）
        rescrapeNotFound: false,
        rescrapeCandidates: [],            // CD-86-6：多版本候選陣列；單版本/非 javlib 為 []
        rescrapeVersionIdx: 0,             // 當前 preview 游標
        rescrapeCfWaiting: false,          // 70-T6: CF 等待態（polling 中）
        _cfPollHandle: null,               // 70-T6: setInterval handle；null = 未 polling

        // ── private ──
        _rescraping: false,                // commit 連點 guard（鏡像 _enriching）
        _rescrapeVideo: null,              // commit 時 refreshVideoData 對象（私有，非 lightbox 當前 state）
        _rescrapeCommitSource: null,       // 進 preview 用的 source（commit 沿用，auto→null 映射前原值）
        _switchTarget: null,               // 62c-3：switch-source 入口長壓開窗當下捕捉的 target slot（{listMode,fileIndex,arr,idx,number}），async race 防覆蓋錯卡

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
            this.rescrapeCandidates = [];
            this.rescrapeVersionIdx = 0;
            this.rescrapeLoadingSource = null;
            this.rescrapeNotFound = false;
            this._rescrapeVideo = video;
            this._switchTarget = null;     // 62c-3：每次開窗先清；switch-source 入口由 openSwitchSourcePicker 隨後捕捉
        },

        /**
         * 62c-3 US7：結果面板 🔄 長壓開來源 picker（entryPoint 'switch-source'）。
         *
         * 在開窗的同一同步 tick 捕捉 target slot 的「容器 + 定位資訊」到 _switchTarget，
         * 供 rescrapeWithSource 的 switch-source 分支 await 回來後判 stale + 寫回（race 防覆蓋錯卡）。
         * 捕「陣列 object reference + index + 番號」而非單一元素 ref —— switchSource 是整顆替換 slot
         * （t.arr[t.idx] = variant），必須寫回該元素所在位置（差異於 result-card.js:168 captured-ref 範本的「改屬性」）。
         *
         * current() / listMode / fileList / currentFileIndex / currentIndex 為 search 元件 state，
         * 經 mergeState 後綁元件 this（result-card.js current() / navigation 既有）。
         * 番號預填當前那一筆，且可編輯（2026-05-31 放開唯讀：拖入解析錯時可在當前卡改正番號重抓）。
         */
        openSwitchSourcePicker() {
            this.openRescrape(null, 'switch-source');
            this.rescrapeNumber = (this.current()?.number || '');
            // 捕捉 target slot：file / 非-file 兩 listMode 都捕（鏡射 current() 二分支）。
            // 強化 1（Opus 審核）：連 listMode + fileIndex 一起捕，await 回來 re-resolve live array 顯式 identity 比對（情境 B）。
            const arr = (this.listMode === 'file' && this.fileList[this.currentFileIndex])
                ? this.fileList[this.currentFileIndex].searchResults
                : this.searchResults;
            this._switchTarget = {
                listMode: this.listMode,
                fileIndex: this.currentFileIndex,
                arr,
                idx: this.currentIndex,
                number: this.current()?.number,
            };
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
         * metatube pill 清單（method 非 getter；鏡射 rescrapeBuiltinSources，只改 filter）。
         * 62c-5：metatube 分組 data-driven（B3 註冊 metatube SourceConfig rows 後彈窗自動長出 pill）。
         *
         * routable gate（Codex PR#47 round-2 P2-B）：metatube sources 目前後端無路由
         * （validate_source_id / search_jav dispatch 只認 auto + builtin SOURCE_ORDER）；
         * 點下去只會 not-found。B3 接 metatube route/validator 時，於來源資料補 routable=true
         * （或改用 backend-disclosed 可路由清單），pill 才長出；直到 B3 前全部 metatube 隱藏
         * （empty note 照顯示，符合 spec §5 「分組預留但空」）。
         * 不動 builtin pill 渲染（rescrapeBuiltinSources）。
         */
        rescrapeMetatubeSources() {
            return this.rescrapeSources
                .filter(s => s.type === 'metatube' && s.routable === true)
                .sort((a, b) => (b.enabled - a.enabled) || (a.order - b.order));
        },

        /**
         * 63c-6 Surface 2：來源是否因 proxy 未設定而被封鎖。
         * 使用 SSR bootstrap 注入的 proxy_configured（CD-63c-9），
         * 不依賴 Settings Alpine scope 的 isDmmAvailable()（兩者 scope 隔離）。
         */
        isSourceProxyBlocked(s) {
            return !!(s && s.requires_proxy && !(window.__ADVANCED_SEARCH__ && window.__ADVANCED_SEARCH__.proxy_configured));
        },

        /**
         * 70-T5: JavLibrary 不可用 gate（desktop-only / standalone 限定）。
         * manual_only && is_beta = javlibrary（目前唯一）；cf_transport_available = standalone 已 register。
         * dev / server 環境：cf_transport_available=false → 此 helper 回 true → pill 灰化不可點。
         */
        isJlUnavailable(s) {
            return !!(s && s.manual_only && s.is_beta && !(window.__ADVANCED_SEARCH__ && window.__ADVANCED_SEARCH__.cf_transport_available));
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
            if (this.rescrapeCfWaiting) return;                       // 等待態不可重入（防 re-entry + UX）
            if (!this.rescrapeNumber.trim()) { this.rescrapeNotFound = true; return; }
            // Search 入口（62c-1）：無預覽卡，繞過 /api/rescrape/preview，直接走 B1 advancedSearch
            // 整包贏（GET /api/search?...&source=），結果進正常結果區，彈窗關閉（spec US5）。
            // CD-86-8：javlibrary 例外——不早 return，繼續走 fetch preview（多版本候選支援）。
            // 番號回寫 searchQuery：讓彈窗內改番號生效（advancedSearch 讀 this.searchQuery）。
            if (this.rescrapeEntryPoint === 'search') {
                if (sourceId !== 'javlibrary') {
                    // 其他 source：維持原路（advancedSearch 整包贏）
                    this.searchQuery = this.rescrapeNumber.trim();
                    this.closeRescrape();
                    await this.advancedSearch(sourceId);  // 'auto' 直接傳給 /api/search（後端 merger）
                    return;
                }
                // javlib：不早 return，繼續走 fetch preview（CD-86-8）
            }
            // 74a US2：switch-source 入口點「自動」= 直接 cycle（picker 關閉 + switchSource 循環）
            // spec-74 §US2：picker「自動」= 原本 🔄 tap 的「換到下一個來源」循環功能。
            // 必須在 POST /api/rescrape/preview fetch 之前短路（DROP：switch-source + auto 不再打 preview）；
            // 具體 source pick 不受影響，繼續走下面 fetch + in-place replace 分支。
            if (this.rescrapeEntryPoint === 'switch-source' && sourceId === 'auto') {
                this.closeRescrape();
                await this.switchSource();
                return;
            }
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
                // 70-T6（P2 fix）: cf_needed / cf_unavailable 統一在所有入口分支之前處理——
                // 原本只在 showcase 分支處理，導致 switch-source 入口收到 {cf_needed:true} 時
                // 因 data.success falsy 而落入 rescrapeNotFound=true，CF flow 從未觸發。
                // 上移後：search 已在函式頂端 early-return，不受影響；switch-source / showcase
                // 兩條路徑皆能正確進入 CF flow。finally 確保 rescrapeLoadingSource=null，retry 可進行。
                if (data && data.cf_needed) {
                    this.rescrapeCfWaiting = true;
                    this._pollCfThenRetry(this.rescrapeNumber.trim());
                    return;
                }
                if (data && data.cf_unavailable) {
                    this.showToast(window.t('showcase.rescrape.jl_desktop_only'), 'warning');
                    return;
                }
                // 62c-3 US7：switch-source 入口（在 showcase 分支之前判斷）。找到 → 只替換捕捉的當前卡 slot
                // （不重設結果列、currentIndex 不歸零、無 ✓/✗ commit）+ seed cycle state；找不到 → 沿用 not-found。
                // 2026-05-31：番號改為可編輯（拍板放開唯讀），故 stale 比對仍用捕捉的原 t.number
                // （await 回來時 slot 尚未替換、仍持有舊番號），但 seed 改用 variant.number
                // （替換後當前卡顯示的番號 = 下次 tap 查 switchStateMap 的 key；用編輯後實際抓回的番號才對得上）。
                if (this.rescrapeEntryPoint === 'switch-source') {
                    if (data && data.success) {
                        // T7: 多版本 → 進 preview + 切換器（不靜默取 [0]）
                        if (data.candidates && data.candidates.length > 1) {
                            const previewSourceId = sourceId === 'auto' ? (data._source || data.source || sourceId) : sourceId;
                            const _previewSrc = this.rescrapeSources.find(x => x.id === previewSourceId);
                            this.rescrapeCandidates = data.candidates;
                            this.rescrapeVersionIdx = 0;
                            this.rescrapePreview = {
                                ...data.candidates[0],
                                sourceName: this._resolveSourceName(previewSourceId),
                                sourceCensored: _previewSrc?.is_censored ?? true,
                            };
                            this._rescrapeCommitSource = sourceId;
                            this.rescrapeStep = 'preview';   // 不關窗
                            return;
                        }
                        // 單版本 → 現有靜默 in-place 替換（race/stale 檢查保留）
                        // ── race 防覆蓋錯卡：await 回來判 slot 是否還在原位（強化 1：含 liveArr 顯式 identity 比對）──
                        const t = this._switchTarget;
                        const liveArr = (t && t.listMode === 'file' && this.fileList[t.fileIndex])
                            ? this.fileList[t.fileIndex].searchResults
                            : this.searchResults;
                        const stale = !t
                            || liveArr !== t.arr                                   // 情境 B：結果列被新搜尋整包換掉 → 顯式丟棄
                            || !Array.isArray(t.arr)
                            || t.idx < 0 || t.idx >= t.arr.length
                            || (t.arr[t.idx] && t.arr[t.idx].number !== t.number);  // 番號比對：防同位置已被別筆佔據
                        if (!stale) {
                            // T7：單版本 fallback——多版本（length>1）已於上方提前 return 進 preview，
                            // 此處只處理單版本（candidates 無或 length===1）→ 取唯一筆替換。
                            const variant = (() => {
                                if (data.candidates && data.candidates.length > 0) {
                                    const { success: _s, ...c } = { success: true, ...data.candidates[0] };
                                    return c;
                                }
                                const { success, ...v } = data;
                                return v;
                            })();
                            t.arr[t.idx] = variant;                               // 整顆替換（對齊 ui.js:248）
                            this._candidateReplaceSeq++;                          // 訊號給 pendingEditWatchKey 偵測原地替換 → 觸發哨兵關 stale 編輯框（PR#116 P2）
                            this._resetCoverState?.();                            // cover 可能變（對齊 ui.js:250）
                            this.saveState?.();                                   // 持久化寫回（對齊 ui.js:259 tap 路徑；防 session restore 回舊卡）。optional-chain：mixin 共用 showcase，switch-source 僅 search 觸發
                            window.SearchUI?.seedSwitchState?.(variant.number || t.number, sourceId, variant);  // 鎖定#4：下次 tap 從選定來源接續（用替換後實際番號 key，對齊編輯番號後的當前卡）
                        }
                        // stale → 靜默丟棄（不寫 detached 陣列、不誤 seed）；非 stale → 已寫回。一律關窗。
                        this.closeRescrape();
                        return;
                    }
                    this.rescrapeNotFound = true;
                    return;
                }
                // Showcase（lightbox）/ search+javlib：找到 → 換頁 preview；找不到 → 留 pick
                // （cf_needed / cf_unavailable 已在上方統一提前處理，此處不再重複）
                if (data && data.candidates && data.candidates.length > 1) {
                    // CD-86-6：多版本——填 candidates 短狀態 + 進 preview（含 search 入口，CD-86-8）
                    const previewSourceId = sourceId === 'auto' ? (data._source || data.source || sourceId) : sourceId;
                    const _previewSrc = this.rescrapeSources.find(x => x.id === previewSourceId);
                    this.rescrapeCandidates = data.candidates;
                    this.rescrapeVersionIdx = 0;
                    this.rescrapePreview = {
                        ...data.candidates[0],
                        sourceName: this._resolveSourceName(previewSourceId),
                        sourceCensored: _previewSrc?.is_censored ?? true,
                    };
                    this._rescrapeCommitSource = sourceId;
                    this.rescrapeStep = 'preview';
                } else if (data && data.success) {
                    // 單版本：search / lightbox 共用 preview 邏輯（CD-86-8 對齊）。
                    // 86 修正：search 單版本不再於此靜默 _commitSearchResults + closeRescrape
                    // （一閃就關，使用者回報「直接跳過」），改 fall through 進 preview 卡（無切換器、
                    // 有 T4「採用此版本」✓ 鈕，x-show="rescrapeEntryPoint==='search'"）。採用由
                    // rescrapeConfirm 的 search 分支處理（已含 searchQuery/currentQuery 同步 + _commitSearchResults）。
                    // lightbox（現況）：74b US3：預覽膠囊顯示「實際刮到的源」+ 有碼/無碼上色。
                    // lightbox + auto 也會進 preview（無 early return）→ auto 時用後端
                    // 回傳的實際源（data._source）解析，否則顯示「自動」+藍 fallback、無法辨識
                    // 實際源（違背 US3「截圖辨識用了哪個源」）。
                    const previewSourceId = sourceId === 'auto' ? (data._source || data.source || sourceId) : sourceId;
                    const _previewSrc = this.rescrapeSources.find(x => x.id === previewSourceId);
                    this.rescrapePreview = {
                        ...data,
                        sourceName: this._resolveSourceName(previewSourceId),
                        sourceCensored: _previewSrc?.is_censored ?? true,  // 找不到 → fallback 有碼藍（同 US2 安全預設）
                    };
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
         * CD-86-6：是否有多版本候選（切換器顯示條件）。
         */
        rescrapeHasVersions() {
            return this.rescrapeCandidates.length > 1;
        },

        /**
         * CD-86-6：切換版本游標（clamp + 重綁 preview/sourceName/sourceCensored）。
         * @param {number} delta - +1 下一版 / -1 上一版
         */
        rescrapeVersionGo(delta) {
            const len = this.rescrapeCandidates.length;
            if (len <= 1) return;
            const newIdx = Math.max(0, Math.min(len - 1, this.rescrapeVersionIdx + delta));
            if (newIdx === this.rescrapeVersionIdx) return;
            this.rescrapeVersionIdx = newIdx;
            const candidate = this.rescrapeCandidates[newIdx];
            const previewSourceId = this._rescrapeCommitSource === 'auto'
                ? (candidate._source || candidate.source || this._rescrapeCommitSource)
                : this._rescrapeCommitSource;
            const _previewSrc = this.rescrapeSources.find(x => x.id === previewSourceId);
            this.rescrapePreview = {
                ...candidate,
                sourceName: this._resolveSourceName(previewSourceId),
                sourceCensored: _previewSrc?.is_censored ?? true,
            };
        },

        /**
         * 回上一步（保留 number + sources，清 preview 讓用戶重選源）。
         */
        rescrapeBackToPick() {
            this.rescrapeStep = 'pick';
            this.rescrapePreview = null;
            this.rescrapeCandidates = [];
            this.rescrapeVersionIdx = 0;
            this.rescrapeNotFound = false;
        },

        /**
         * ✓ commit — 自包含覆蓋寫入（POST /api/enrich-single）。鏡像 enrichVideo。
         * CD-86-9/14：search 入口採用選定版本進搜尋結果，不打 enrich-single，不顯示不可逆警告。
         */
        async rescrapeConfirm() {
            if (this._rescraping) return;                            // 連點防護
            if (this.rescrapeCfWaiting) return;                      // P2-2：CF 等待中不可重入（鏡射 rescrapeWithSource :161）
            this._rescraping = true;
            try {
                if (this.rescrapeEntryPoint === 'search') {
                    // CD-86-9/14：採用選定版本進搜尋結果，不打 enrich-single，不顯示不可逆警告
                    if (!this.rescrapePreview) { return; }
                    // CD-86-P2：同步 searchQuery / currentQuery（對齊非 javlib 路徑 :167 + advancedSearch :38）
                    this.searchQuery = this.rescrapeNumber.trim();
                    this.currentQuery = this.rescrapeNumber.trim();
                    // strip preview-only extras（success/sourceName/sourceCensored）不讓其流入 result row
                    const { success: _s, sourceName: _sn, sourceCensored: _sc, ...adopted } = this.rescrapePreview;
                    this._commitSearchResults?.({ data: [adopted], mode: 'exact', has_more: false, actress_profile: null });
                    this.closeRescrape();
                    return;
                }
                // T7: switch-source 入口採用選定版本做 in-place 替換（不打 enrich-single，不 _commitSearchResults）
                if (this.rescrapeEntryPoint === 'switch-source') {
                    if (!this.rescrapePreview) { return; }
                    const t = this._switchTarget;
                    // 採用當下重驗 stale（鏡射 rescrapeWithSource :220-228）
                    const liveArr = (t && t.listMode === 'file' && this.fileList[t.fileIndex])
                        ? this.fileList[t.fileIndex].searchResults : this.searchResults;
                    const stale = !t || liveArr !== t.arr || !Array.isArray(t.arr)
                        || t.idx < 0 || t.idx >= t.arr.length
                        || (t.arr[t.idx] && t.arr[t.idx].number !== t.number);
                    if (!stale) {
                        const { success: _s, sourceName: _sn, sourceCensored: _sc, ...variant } = this.rescrapePreview;
                        t.arr[t.idx] = variant;                          // in-place 替換選定版本
                        this._candidateReplaceSeq++;                     // 訊號給 pendingEditWatchKey 偵測原地替換 → 觸發哨兵關 stale 編輯框（PR#116 P2）
                        this._resetCoverState?.();
                        this.saveState?.();
                        window.SearchUI?.seedSwitchState?.(variant.number || t.number, this._rescrapeCommitSource, variant);
                    }
                    this.closeRescrape();                                 // stale 靜默丟棄；非 stale 已替換。一律關窗
                    return;
                }
                // lightbox（現況）：需既有檔
                if (!this._rescrapeVideo || !this._rescrapeVideo.path) return;
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
                        detail_url: this.rescrapePreview?.url || null,  // CD-86-13: 取 .url 非 .detail_url
                        readonly_action: 'rescrape',                    // T4: 無條件送（非唯讀端後端忽略，CD-104-5）
                    }),
                });
                const result = await resp.json();
                // P2-2（Codex PR#89）：confirm 寫檔分支也接 CF——T2 後 javlibrary && detail_url 會走後端
                // detail 重抓分支，若預覽→確認之間 CF session 過期，後端回 {cf_needed} / {cf_unavailable}
                // （已 begin_solve）。鏡射 preview（rescrapeWithSource :203-211）：不接 → 卡在模糊「失敗」
                // 且 CF flow 不啟動。cf_needed 啟動既有等待輪詢（_pollCfThenRetry 解完 CF 後重跑 preview，
                // 使用者再按確認）——對不可逆寫檔，CF 後強制重新確認比靜默自動寫入更安全。
                // 在判 success/失敗之前處理。順序對齊 preview（cf_needed 先、cf_unavailable 後）。
                if (result.cf_needed) {
                    this.rescrapeCfWaiting = true;
                    this._pollCfThenRetry(this.rescrapeNumber.trim());
                    return;
                }
                if (result.cf_unavailable) {
                    this.showToast(window.t('showcase.rescrape.jl_desktop_only'), 'warning');
                    return;
                }
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
         * 70-T6: poll /api/cf/status 直到就緒，再 auto-retry 同番號。
         * MAX_POLLS=150（150 × 2s = 300s = 5 分鐘）。
         */
        _pollCfThenRetry(number) {
            if (this._cfPollHandle !== null) {   // 防覆寫洩漏：清掉任何既有 poll
                clearInterval(this._cfPollHandle);
                this._cfPollHandle = null;
            }
            const MAX_POLLS = 150;          // 150 × 2s = 300s = 5 分鐘
            let pollCount = 0;
            this._cfPollHandle = setInterval(async () => {
                pollCount++;
                if (pollCount >= MAX_POLLS) {
                    this.cancelCfPoll();    // 逾時走 cancel 流程
                    return;
                }
                try {
                    const resp = await fetch('/api/cf/status?key=javlibrary');
                    const data = await resp.json();
                    if (data && data.unavailable) {   // CD-70c-3: transport dead/unavailable → stop polling now
                        this.cancelCfPoll();           // clearInterval + POST /api/cf/abandon (emits 通知)
                        return;
                    }
                    if (data && data.ready) {
                        clearInterval(this._cfPollHandle);
                        this._cfPollHandle = null;
                        this.rescrapeCfWaiting = false;
                        // retry 同番號
                        await this.rescrapeWithSource('javlibrary');
                    }
                } catch (_) { /* network 暫時失敗，繼續 poll */ }
            }, 2000);
        },

        /**
         * 70-T6: 取消 CF poll（clearInterval + POST /api/cf/abandon）。
         * 用於：逾時、用戶點 Cancel 鈕、番號 input 改動。
         * 注意：closeRescrape 只做 clearInterval，不 POST abandon（關窗 ≠ 顯式取消）。
         */
        cancelCfPoll() {
            if (this._cfPollHandle !== null) {
                clearInterval(this._cfPollHandle);
                this._cfPollHandle = null;
            }
            this.rescrapeCfWaiting = false;
            // POST /api/cf/abandon（非阻塞 fire-and-forget；通知中心由後端寫）
            fetch('/api/cf/abandon?key=javlibrary', { method: 'POST' }).catch(() => {});
        },

        /**
         * 關閉彈窗（reset transient；_rescrapeVideo/_rescrapeCommitSource 下次 open 覆寫）。
         */
        closeRescrape() {
            // 70-T6: 清 CF poll handle（關窗不 POST abandon，語意不同）
            if (this._cfPollHandle !== null) {
                clearInterval(this._cfPollHandle);
                this._cfPollHandle = null;
                this.rescrapeCfWaiting = false;
            }
            this.rescrapeOpen = false;
            this.rescrapeStep = 'pick';
            this.rescrapePreview = null;
            this.rescrapeCandidates = [];
            this.rescrapeVersionIdx = 0;
            this.rescrapeNotFound = false;
            this.rescrapeLoadingSource = null;
            this._switchTarget = null;     // 62c-3：關窗清掉捕捉的 slot（switch-source 入口）
        },
    };
}
