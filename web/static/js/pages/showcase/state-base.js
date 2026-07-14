/**
 * state-base.js — Showcase ESM foundation（54b-T1a）
 *
 * module-level exports（共用陣列、helpers）+ stateBase() factory。
 * 不含 openLightbox / closeLightbox（屬 state-lightbox.js）。
 * Picker 常數屬 stateLightbox() 閉包（OQ-54B-2 Option B），不在此模組。
 */

// 53a codex F3: $persist 對 localStorage 壞 JSON 沒 try/catch（會在 Alpine init 階段拋錯炸整頁），
// 必須在 Alpine.data 註冊前先清掃壞值，讓 $persist fallback 走預設物件
(function _safeCleanShowcaseState() {
    try {
        var raw = localStorage.getItem('showcase_state');
        if (raw !== null) JSON.parse(raw);
    } catch (e) {
        try { localStorage.removeItem('showcase_state'); } catch (_) { /* storage unavailable */ }
        console.warn('[Showcase] cleared corrupt showcase_state from localStorage:', e);
    }
})();

// F1: 大陣列移出 Alpine reactive scope — Alpine 不追蹤
export var _videos = [];
export var _filteredVideos = [];
export var _actresses = [];
export var _filteredActresses = [];
export var _actressesLoaded = false;
export function _setActressesLoaded(v) { _actressesLoaded = v; }
export function _setVideos(v) {
    _videos.length = 0;
    for (const item of (v || [])) _videos.push(item);
}
export function _setFilteredVideos(v) {
    _filteredVideos.length = 0;
    for (const item of (v || [])) _filteredVideos.push(item);
}
export function _setActresses(v) {
    _actresses.length = 0;
    for (const item of (v || [])) _actresses.push(item);
}
export function _setFilteredActresses(v) {
    _filteredActresses.length = 0;
    for (const item of (v || [])) _filteredActresses.push(item);
}
export var _nameToGroup = {};  // { "舊名": ["新名", "舊名"], "新名": [...] } 雙向 alias map
export var _aliasMapLoaded = false;

/**
 * 45-P2 fix: 獨立載入 alias map，init() 時無條件呼叫。
 * 冪等：已載入時直接 return。
 */
export async function _loadAliasMap() {
    if (_aliasMapLoaded) return;
    try {
        var resp = await fetch('/api/actress-aliases');
        if (resp.ok) {
            var data = await resp.json();
            var groups = (data && data.groups) || [];
            _nameToGroup = {};
            groups.forEach(function(g) {
                var all = [g.primary_name].concat(g.aliases || []);
                all.forEach(function(n) { _nameToGroup[n.toLowerCase()] = all; });
            });
        }
    } catch (e) {
        console.warn('[Showcase] Failed to fetch actress aliases:', e);
        _nameToGroup = {};
    }
    _aliasMapLoaded = true;
}

export var _tagToGroup = {};  // { "女僕": ["メイド", "女僕", "女傭"], ... } 雙向 tag alias map
export var _tagAliasMapLoaded = false;

/**
 * A3-4: 獨立載入 tag alias map，init() 時無條件呼叫（在 _loadAliasMap 之後）。
 * 冪等：已載入時直接 return。
 * 結構鏡射 _loadAliasMap()，API 改為 /api/tag-aliases。
 */
export async function _loadTagAliasMap() {
    if (_tagAliasMapLoaded) return;
    try {
        var resp = await fetch('/api/tag-aliases');
        if (resp.ok) {
            var data = await resp.json();
            var groups = (data && data.groups) || [];
            _tagToGroup = {};
            groups.forEach(function(g) {
                var all = [g.primary_name].concat(g.aliases || []);
                all.forEach(function(n) { _tagToGroup[n.toLowerCase()] = all; });
            });
        }
    } catch (e) {
        console.warn('[Showcase] Failed to fetch tag aliases:', e);
        _tagToGroup = {};
    }
    _tagAliasMapLoaded = true;
}

// 41c B-lite: 無封面 placeholder SVG (cover 載入失敗時 handleCoverError 換上)
// viewBox 800x600 對齊 lightbox 4:3，grid card aspect-ratio:3/2 會 crop 上下少許但不影響 icon 居中
// 設計：暗色漸層背景 + 中央 image-frame icon (邊框+太陽+山形)
//
// 41d-T4: 純圖示 empty state，不含文字。
// 理由：_NO_COVER_PLACEHOLDER 是 module-level IIFE，JS 載入時 window.t() i18n 函數
// 尚未就緒，無法呼叫；hardcoded 中文違反 i18n 規則。image-frame icon 是業界通用的
// no-image pattern，視覺語意已足夠清晰，互動 CTA 交給既有的 enrich icon。
// 若未來必須加文字說明，需改為 lazy generation function（延遲至 i18n 初始化後呼叫）。
export var _NO_COVER_PLACEHOLDER = (function () {
    var svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 600'>"
        + "<defs><linearGradient id='bg' x1='0' y1='0' x2='0' y2='1'>"
        + "<stop offset='0%' stop-color='#1c1c1e'/>"
        + "<stop offset='100%' stop-color='#0a0a0c'/>"
        + "</linearGradient></defs>"
        + "<rect width='800' height='600' fill='url(#bg)'/>"
        + "<rect x='0.5' y='0.5' width='799' height='599' fill='none' stroke='rgba(255,255,255,0.06)'/>"
        + "<g transform='translate(280,170)' stroke='rgba(255,255,255,0.22)' stroke-width='6' fill='none' stroke-linejoin='round' stroke-linecap='round'>"
        + "<rect x='0' y='0' width='240' height='180' rx='14'/>"
        + "<circle cx='68' cy='56' r='18' fill='rgba(255,255,255,0.18)' stroke='none'/>"
        + "<path d='M 26 158 L 100 84 L 156 134 L 218 78 L 218 174 L 26 174 Z' fill='rgba(255,255,255,0.10)'/>"
        + "</g>"
        + "</svg>";
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
})();

/**
 * T20 fallback helper — Lightbox timeline kill
 *
 * 優先委派給 ShowcaseAnimations.killLightboxAnimations（animations.js 已封裝 C18 邏輯）。
 * 若 animations.js 未載入但 gsap 仍可用（例如 CDN 載入時序差異），直接用 gsap.getById 清理
 * 進行中的 timeline，避免 stale callback 在 lightbox 關閉後繼續操作 DOM / state。
 *
 * @param {Object} [options={}]
 * @param {boolean} [options.killOpen=true]   是否 kill showcaseLightboxOpen timeline
 * @param {boolean} [options.killSwitch=true] 是否 kill showcaseLightboxSwitch timeline
 */
export function _killLightboxTimelines(options) {
    if (window.ShowcaseAnimations?.killLightboxAnimations) {
        window.ShowcaseAnimations.killLightboxAnimations(options);
    } else if (typeof gsap !== 'undefined') {
        var opts = options || {};
        var killOpen  = opts.killOpen  !== false;
        var killSwitch = opts.killSwitch !== false;
        if (killOpen)   gsap.getById('showcaseLightboxOpen')?.kill();
        if (killSwitch) gsap.getById('showcaseLightboxSwitch')?.kill();
    }
}

export function stateBase() {
    return {

        // 56c-fix: similar exit standalone video — 當 _similarLastDrilledNumber 不在 _filteredVideos 時，
        // closeSimilarMode 直接把 similarResults 的最後鑽入 item 包成 standalone lightbox source。
        // null = 非 standalone 模式（既有 _filteredVideos 路徑）；
        // non-null = standalone 模式：currentLightboxVideo 顯示此物件，prev/next 暫禁。
        similarExitVideo: null,

        // 53a-T2: 持久化容器（$persist 自動同步 localStorage 的 'showcase_state' key）
        // sort/order/actressSort/actressOrder 用 null sentinel，讓 restoreState 走 URL > _persisted > config > fallback 優先序
        _persistedShowcase: this.$persist({
            sort: null,
            order: null,
            page: 1,
            search: '',
            mode: 'grid',
            showFavoriteActresses: false,
            actressSort: null,
            actressOrder: null,
        }).as('showcase_state'),

        // --- 狀態變數 ---
        loading: true,
        error: '',           // 錯誤訊息（API 失敗時顯示）
        videoCount: 0,        // _videos.length 的 reactive scalar
        filteredCount: 0,     // _filteredVideos.length 的 reactive scalar
        paginatedVideos: [],  // 當前頁顯示的影片

        // Lightbox 狀態 (M3a)
        lightboxOpen: false,
        lightboxIndex: -1,              // 指向 filteredVideos 的索引
        lightboxCloseTimer: null,       // F2: generation-guarded delayed clear timer

        // Toast 狀態 (M3h)
        toastVisible: false,
        toastMessage: '',
        toastType: 'success',
        toastTimer: null,

        // Card Info 展開狀態 (M3i)
        infoVisible: false,

        // Toolbar Dropdown 狀態
        sortOpen: false,
        modeOpen: false,

        search: '',
        sort: 'date',         // M2a 先用硬編碼，M4 才從 config/localStorage 恢復
        order: 'desc',
        mode: 'grid',
        page: 1,
        perPage: 90,
        totalPages: 1,
        _animGeneration: 0,  // B13: 防止 stale deferred callback
        _lightboxAnimating: false,  // B16: Lightbox 動畫進行中 guard
        _lightboxGeneration: 0,    // B19: invalidation token for deferred $nextTick lightbox callbacks

        // --- 生命週期 ---
        async init() {
            // 接入 page lifecycle：清理 lightbox timer 和 body class
            if (window.__registerPage) {
                window.__registerPage({
                    cleanup: () => {
                        this._animGeneration++;       // B13: 使 pending deferred callback 失效
                        this._lightboxGeneration++;   // B19: invalidate pending $nextTick lightbox callbacks
                        if (this.lightboxCloseTimer) clearTimeout(this.lightboxCloseTimer);  // F2: cleanup delayed clear timer
                        if (this.toastTimer) clearTimeout(this.toastTimer);
                        if (this.lightboxOpen) document.body.classList.remove('overflow-hidden');
                        this._resetPicker();                                  // 53a-T1: 清場 picker 狀態（含 abort _pickerReadyAbort）
                        // nexttick-hydrate P2-2：離頁時 mobile 面板不走 closeMobilePanel（僅 matchMedia
                        // 960 觸發），故其 in-flight waitForMount observer 不會被 abort → 顯式收（與
                        // _resetPicker 對稱，冪等）。
                        this._mobileReadyAbort?.abort();
                        this._mobileReadyAbort = null;
                        window.GhostFly?.cleanupStaleGhosts?.();              // 53a-T1: 移除殘留 ghost（沿 v0.8.1 T4 optional-chaining pattern）
                        if (this._scrollHideHandler) window.removeEventListener('scroll', this._scrollHideHandler);  // T1: cleanup scroll collapse listener
                    }
                });
            }

            this.restoreState();        // M2c: 先恢復狀態
            const savedPage = this.page;
            await this.fetchVideos();
            // 57e hotfix：fire-and-forget warm-up SimilarRankerCache，避免 magic icon 首次點擊 cold-start race。
            // 失敗靜默（端點不存在的舊 server / 網路斷線都不影響 showcase 主流程）。
            fetch('/api/similar/warmup').catch(() => {});
            await _loadAliasMap();      // 45-P2: 無條件載入 alias map（影片搜尋也需要）
            await _loadTagAliasMap();   // A3-4: 無條件載入 tag alias map
            if (this.showFavoriteActresses) { this.loadActresses(); }
            this.applyFilterAndSort(true);  // M4a: 套用搜尋篩選（跳過 pagination，下面統一處理）
            this.page = savedPage;          // 恢復儲存的頁碼
            this.updatePagination();        // 單次分頁（會 clamp 超出範圍的頁碼）

            // Settle: 初次載入用 settle（不碰 opacity → 不閃）
            if (this.mode === 'grid') {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;  // stale
                    var grid = this._getActiveGrid();
                    window.ShowcaseAnimations?.playSettle?.(grid);
                }); });
            }

            // 83b-T1 (D12 / R7): 跨 960 breakpoint reset 行動相似面板。
            // CSS @media (min-width:960px) display:none 藏面板，但 flag 殘留會卡住
            // lightbox trap 的 `&& !similarModeMobileOpen`（iPad 旋轉）→ 強制 closeMobilePanel。
            // 註冊在合併 init（單一 lifecycle，不另開競爭 hook）；closeMobilePanel 屬 state-similar
            // 同一 Alpine 元件可達（main.js mergeState）。
            if (typeof window.matchMedia === 'function') {
                const mq = window.matchMedia('(min-width: 960px)');
                mq.addEventListener('change', (e) => {
                    if (e.matches && this.similarModeMobileOpen) {
                        this.closeMobilePanel();
                    }
                });
            }

            // T1: Mobile scroll-to-collapse — 往下滾超過 50px（相對 toolbar 展開當下 Y）自動收合（≤480px，搜尋空白時）
            let _toolbarOpenY = null
            const COLLAPSE_THRESHOLD = 50
            const _scrollHandler = () => {
                if (!window.matchMedia('(max-width: 480px)').matches) return
                const isOpen = Alpine.store('ui').toolbarOpen
                if (!isOpen) { _toolbarOpenY = null; return }
                if (_toolbarOpenY === null) _toolbarOpenY = window.scrollY
                if (this.search !== '' || this.actressSearch !== '') return  // actressSearch 來自 state-actress.js merge
                if (window.scrollY - _toolbarOpenY > COLLAPSE_THRESHOLD) {
                    Alpine.store('ui').toolbarOpen = false
                    _toolbarOpenY = null  // reset: 下次 reopen 從新基準計，防 stale baseline 立即再收
                }
            }
            window.addEventListener('scroll', _scrollHandler, { passive: true })
            this._scrollHideHandler = _scrollHandler

            // T2: 有效搜尋時 header icon 切換為 X
            this.$watch('search', val => {
                Alpine.store('ui').showcaseHasSearch = (val !== '' || this.actressSearch !== '')
            })
            this.$watch('actressSearch', val => {
                Alpine.store('ui').showcaseHasSearch = (this.search !== '' || val !== '')
            })
            // T2 init sync: restoreState() 在 $watch 前執行，初始 search/actressSearch 不觸發 watcher
            Alpine.store('ui').showcaseHasSearch = (this.search !== '' || this.actressSearch !== '')

            // 98b-T4：換片 reset 遮罩（結構性涵蓋四條換片路徑——皆最終改 currentLightboxVideo）。
            // A 片開遮罩翻 auto → 不關直接換 B → 舊片未提交態不落 B 的 DB（_maskSession guard + 此 reset）。
            this.$watch('currentLightboxVideo?.path', () => { if (this._maskVisible) this._resetMask(); })
        },

        clearSearch() {
            this.search = ''
            this.actressSearch = ''
            this.onSearchChange()
            this.onActressSearchChange()
            Alpine.store('ui').toolbarOpen = false
        },

        // --- 狀態恢復 (M2c) ---
        restoreState() {
            // 1. 從 config 取得預設值
            const cfg = window.__SHOWCASE_CONFIG__ || {};
            const defaultSort = cfg.default_sort || 'date';
            const defaultOrder = cfg.default_order === 'ascending' ? 'asc' : 'desc';
            // T3.2 P2 fix: `??` 而非 `||` — Settings 允許 items_per_page=0（"全部"語意），
            // 必須保留 numeric 0 讓下方 grid+perPage=0→120 降級邏輯有機會觸發。
            const defaultPerPage = cfg.items_per_page ?? 90;

            // 2. 從 _persistedShowcase（$persist 自動讀的 localStorage 'showcase_state'）取
            //    53a-T2: 取代手寫 localStorage.getItem + JSON.parse，格式向後相容
            const state = this._persistedShowcase || {};

            // 3. 從 URL params 恢復（最高優先）
            const urlParams = new URLSearchParams(window.location.search);

            // 4. 優先序：URL > _persistedShowcase > config > fallback
            //    sort/order/actressSort/actressOrder 在 _persisted 用 null sentinel，新用戶會透下到 config
            //    urlNum: 取 URL 數值參數，空字串視為無值（避免 parseInt("") → NaN）
            const urlNum = (key) => { const v = urlParams.get(key); return v !== null && v !== '' ? v : undefined; };
            this.sort = urlParams.get('sort') || state.sort || defaultSort;
            this.order = urlParams.get('order') || state.order || defaultOrder;
            // T3.2 (CD-52-3): perPage 只從 cfg.items_per_page，URL params + localStorage 不再參與
            // 既有 user 的 localStorage state.perPage / URL ?perPage=N 被 silently 忽略（CD-52-4）
            this.perPage = defaultPerPage;
            this.page = parseInt(urlNum('page') ?? state.page ?? 1) || 1;
            this.search = urlParams.get('search') || state.search || '';
            this.mode = urlParams.get('mode') || state.mode || 'grid';
            if (!['grid', 'table', 'list'].includes(this.mode)) this.mode = 'grid';
            // F2: grid + perPage=0 組合降級（settings 若存 items_per_page=0 之防呆）
            if (this.mode === 'grid' && this.perPage === 0) {
                this.perPage = 120;
            }
            // ★ 44a: 女優模式 — 只從 _persistedShowcase，不加 URL params（避免汙染 shareable link）
            this.showFavoriteActresses = state.showFavoriteActresses === true;  // 嚴格 === true
            this.actressSort = state.actressSort || 'video_count';
            this.actressOrder = state.actressOrder || 'desc';
        },

        // --- 狀態持久化 (M2c) ---
        saveState() {
            // 53a-T2: 寫入 reactive _persistedShowcase，$persist 自動同步 localStorage 'showcase_state'
            // T3.2 (CD-52-3): perPage 不寫入（每次 init 重讀 cfg.items_per_page）
            this._persistedShowcase.sort = this.sort;
            this._persistedShowcase.order = this.order;
            this._persistedShowcase.page = this.page;
            this._persistedShowcase.search = this.search;
            this._persistedShowcase.mode = this.mode;
            this._persistedShowcase.showFavoriteActresses = this.showFavoriteActresses;  // ★ 44a
            this._persistedShowcase.actressSort = this.actressSort;                      // ★ 44a
            this._persistedShowcase.actressOrder = this.actressOrder;                    // ★ 44a

            // 同步到 URL（方便分享連結）
            const params = new URLSearchParams();
            if (this.search) params.set('search', this.search);
            if (this.sort !== 'date') params.set('sort', this.sort);
            if (this.order !== 'desc') params.set('order', this.order);
            // T3.2 (CD-52-3): perPage 不再寫入 URL params（每次 init 重讀 cfg.items_per_page）
            if (this.page !== 1) params.set('page', this.page);
            if (this.mode !== 'grid') params.set('mode', this.mode);

            const newUrl = params.toString()
                ? `${window.location.pathname}?${params}`
                : window.location.pathname;
            window.history.replaceState({}, '', newUrl);
        },

        // Card Info 切換 (M3i)
        toggleInfo() {
            this.infoVisible = !this.infoVisible;
        },

        // 格式化檔案大小（bytes → GB/MB）
        formatSize(bytes) {
            if (!bytes || bytes === 0) return window.t('showcase.grid.unknown_size');
            const gb = bytes / (1024 * 1024 * 1024);
            if (gb >= 1) {
                return `${gb.toFixed(2)} GB`;
            }
            const mb = bytes / (1024 * 1024);
            return `${mb.toFixed(2)} MB`;
        },

        // Stale cover handler — 圖片載入失敗時 downgrade has_cover，
        // 觸發 Alpine reactive：enrich icon 自動出現、missing-cover class 套用、
        // 點 enrich 後自動走 refresh_full 補封面。
        handleCoverError(video, event) {
            if (!video) return;
            video.has_cover = false;  // 觸發 reactive — enrich icon 自動出現 + missing-cover class 套用
            // 67/Codex P2（broken cover）：grid 三態淡入讓 .av-card-preview-img img 預設 opacity:0、靠
            // .cover-loaded(=_imgLoaded) 才可見。stale/404 換 placeholder 後，可見性原本只依賴 placeholder
            // 二次 @load 觸發（脆弱）→ 直接設 _imgLoaded=true，確定性顯示 placeholder（不依賴 @load）。
            video._imgLoaded = true;
            event.target.onerror = null;  // 防止 placeholder 失敗無限迴圈
            event.target.src = _NO_COVER_PLACEHOLDER;
        },

        // --- Toast 通知 (M3h) ---
        showToast(msg, type = 'success', duration = 2500) {
            this.toastMessage = msg;
            this.toastType = type;
            this.toastVisible = true;
            if (this.toastTimer) clearTimeout(this.toastTimer);
            this.toastTimer = setTimeout(() => {
                this.toastVisible = false;
            }, duration);
        },
    };
}
