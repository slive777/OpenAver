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
        rescrapeEntryPoint: 'lightbox',    // 'lightbox' | 'enrich' | 'search' | 'switch-source'
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
        _switchTarget: null,               // 62c-3：switch-source 入口長壓開窗當下捕捉的 target slot（{listMode,fileIndex,arr,idx,number}），async race 防覆蓋錯卡

        /**
         * 進階重刮入口 gate（62b-1，決策 #1）。各入口（⚙ / grid 長壓 / lightbox 🔍 長壓 / search 送出鈕長壓）共用，
         * 守衛可斷言、避免 template 散落 window 讀取（62c-2 起 search 長壓 enabledFn 亦統一用此）。
         * method 非 getter（規避 Alpine reactivity 凍結；CD-62-14 #0）。
         */
        rescrapeEnabled() {
            return !!(window.__ADVANCED_SEARCH__ && window.__ADVANCED_SEARCH__.enabled);
        },

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
            // Search 入口（62c-1）：無預覽卡，繞過 /api/rescrape/preview，直接走 B1 advancedSearch
            // 整包贏（GET /api/search?...&source=），結果進正常結果區，彈窗關閉（spec US5）。
            // 番號回寫 searchQuery：讓彈窗內改番號生效（advancedSearch 讀 this.searchQuery）。
            if (this.rescrapeEntryPoint === 'search') {
                this.searchQuery = this.rescrapeNumber.trim();
                this.closeRescrape();
                await this.advancedSearch(sourceId);  // 'auto' 直接傳給 /api/search（後端 merger）
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
                // 62c-3 US7：switch-source 入口（在 showcase 分支之前判斷）。找到 → 只替換捕捉的當前卡 slot
                // （不重設結果列、currentIndex 不歸零、無 ✓/✗ commit）+ seed cycle state；找不到 → 沿用 not-found。
                // 2026-05-31：番號改為可編輯（拍板放開唯讀），故 stale 比對仍用捕捉的原 t.number
                // （await 回來時 slot 尚未替換、仍持有舊番號），但 seed 改用 variant.number
                // （替換後當前卡顯示的番號 = 下次 tap 查 switchStateMap 的 key；用編輯後實際抓回的番號才對得上）。
                if (this.rescrapeEntryPoint === 'switch-source') {
                    if (data && data.success) {
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
                            // dict shape 已核對與 searchResults row 一致，僅需 strip success key
                            const { success, ...variant } = data;
                            t.arr[t.idx] = variant;                               // 整顆替換（對齊 ui.js:248）
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
                // Showcase（lightbox / enrich）：找到 → 換頁 preview；找不到 → 留 pick
                // （Search 入口已在函式開頭提早分流到 advancedSearch，不走到這裡）
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
            this._switchTarget = null;     // 62c-3：關窗清掉捕捉的 slot（switch-source 入口）
            // Codex 二輪 P3：清長壓殘留旗標，涵蓋鍵盤 / 輔助技術 click 啟用（無 mousedown 前導）
            // 繞過 longPressStart top reset 的情況。optional-chain：search 入口（62c）才合併 longPressState。
            this.longPressReset?.();
        },
    };
}
