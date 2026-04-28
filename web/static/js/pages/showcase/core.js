/**
 * Showcase 核心狀態管理
 * M2a: 基本骨架 + API 載入 + Image Grid 渲染
 */

// F1: 大陣列移出 Alpine reactive scope — Alpine 不追蹤
var _videos = [];
var _filteredVideos = [];
var _actresses = [];
var _filteredActresses = [];
var _actressesLoaded = false;
var _nameToGroup = {};  // { "舊名": ["新名", "舊名"], "新名": [...] } 雙向 alias map
var _aliasMapLoaded = false;

/**
 * 45-P2 fix: 獨立載入 alias map，init() 時無條件呼叫。
 * 冪等：已載入時直接 return。
 */
async function _loadAliasMap() {
    if (_aliasMapLoaded) return;
    try {
        var resp = await fetch('/api/actress-aliases');
        if (resp.ok) {
            var data = await resp.json();
            var groups = (data && data.groups) || [];
            _nameToGroup = {};
            groups.forEach(function(g) {
                var all = [g.primary_name].concat(g.aliases || []);
                all.forEach(function(n) { _nameToGroup[n] = all; });
            });
        }
    } catch (e) {
        console.warn('[Showcase] Failed to fetch actress aliases:', e);
        _nameToGroup = {};
    }
    _aliasMapLoaded = true;
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
var _NO_COVER_PLACEHOLDER = (function () {
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
function _killLightboxTimelines(options) {
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

function showcaseState() {
    // 49b T4cd: Picker 動畫參數（T1 fix2 定案，2026-04-25）
    // 供 BurstPicker.playPickerBurst/Float/HoverIn/HoverOut/ExitAll 使用
    // 49c.T5fix.B：viewport bottom anchor 後 burst 距離增加 ~55%，timing 校正定案
    const _PICKER_PARAMS = {
        arcOvershoot: 1.3,    // V2 從 1.4 改 1.3：拉長後 overshoot 視覺強，略降
        arcDuration:  0.75,   // V2 從 0.6 改 0.75：補償距離增加 ~+55%
        floatAmplY:   8,      // Float loop Y 幅度（px）
        floatAmplRot: 2.5,    // Float loop 旋轉幅度（度）
        floatDuration: 1.5,   // Float loop 基礎週期（秒）
        hoverScale:   1.08,   // V2 從 1.12 改 1.08：大卡上不過搶戲
        exitGravity:  1200,   // 其他卡墜落重力（physics2D）
    };

    return {
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
        perPageOpen: false,

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

        // Sample Gallery 狀態 (T7)
        sampleGalleryOpen: false,
        sampleGalleryImages: [],
        sampleGalleryIndex: 0,
        _sgTouchStartX: null,
        _sgAnimating: false,      // C21 guard
        _sgGeneration: 0,         // stale callback 防護

        currentLightboxVideo: null,

        // 44a: 女優模式狀態
        showFavoriteActresses: false,   // mode toggle，切換影片/女優 grid
        actressCount: 0,                // mirror _actresses.length
        filteredActressCount: 0,        // mirror _filteredActresses.length
        paginatedActresses: [],         // CD-9：全量 = _filteredActresses，不分頁
        actressSearch: '',              // 女優搜尋框（獨立於 search）
        actressSort: 'video_count',     // 預設排序
        actressOrder: 'desc',           // 預設降冪
        actressLoading: false,          // 載入中
        actressLightboxIndex: -1,       // 指向 _filteredActresses 的索引
        currentLightboxActress: null,   // 當前 lightbox 女優；與 currentLightboxVideo 互斥
        actressLightboxSource: null,    // T5: 'hero' | 'grid' | null — 進入路徑（CD-9）
        _ghostFlyInFlight: false,       // T7: 跨模式 ghost fly 並發保護 flag（CD-13）
        _actressChipsExpanded: { aliases: false, info: false },  // chips 展開狀態
        _addActressName: '',            // + 新增 input
        _addingActress: false,          // 新增 loading
        _addDropdownOpen: false,        // + 新增 popover 開關
        _videoChipsExpanded: false,     // 影片 tag chips +N 展開（T4 使用）

        // 49b T4cd: Actress Photo Picker 狀態
        _pickerOpen: false,
        _candidates: [],
        _pickerLoading: false,
        _pickerSelected: false,
        _pickerCurrentSource: null,
        _pickerFloatTweens: [],
        _pickerRunId: 0,
        _pickerSSE: null,
        _pickerTimeoutTimer: null,

        // User Tags 狀態 (T4)
        addingLbTag: false,
        newLbTagValue: '',

        // Enrich 狀態 (T3)
        _enriching: false,

        // 44b: 精準匹配狀態
        _isPreciseActressMatch: false,
        _matchedActress: null,
        _preciseMatchSource: null,
        _favoriteHeartLoading: false,
        _heroCardImageError: false,
        _fetchSamplesLoading: false,
        _fetchSamplesFailed: {},

        // F1: helper — 更新 lightboxIndex + currentLightboxVideo 一致性
        _setLightboxIndex(idx) {
            this.lightboxIndex = idx;
            this.currentLightboxVideo = (idx >= 0 && idx < _filteredVideos.length)
                ? _filteredVideos[idx] : null;
            this.currentLightboxActress = null;   // ★ 44a 新增：video setter always clear actress
            this.addingLbTag = false;  // 切換影片時重置輸入框
            this._videoChipsExpanded = false;     // ★ 44a 新增：影片切換時 reset chips 展開
        },

        // 44a: helper — 更新 actressLightboxIndex + currentLightboxActress 一致性
        _setActressLightboxIndex(idx) {
            this.actressLightboxIndex = idx;
            this.currentLightboxActress = (idx >= 0 && idx < _filteredActresses.length)
                ? _filteredActresses[idx] : null;
            this.currentLightboxVideo = null;    // 互斥：清除影片
            this._actressChipsExpanded = { aliases: false, info: false };
        },

        // 44b: 精準匹配 helpers
        _clearPreciseMatch() {
            this._isPreciseActressMatch = false;
            this._matchedActress = null;
            this._preciseMatchSource = null;
            this._favoriteHeartLoading = false;
            this._heroCardImageError = false;
        },

        async _checkPreciseActressMatch(term, source) {
            var capturedTerm = (term || '').trim();
            if (!_actressesLoaded && _actresses.length === 0) {
                await this.loadActresses();
            }
            if (this.search.trim() !== capturedTerm) return;
            this._heroCardImageError = false;
            var found = _actresses.find(function(a) {
                var group = _nameToGroup[a.name] || [a.name];
                return group.indexOf(capturedTerm) !== -1;
            });
            if (found) {
                this._isPreciseActressMatch = true;
                this._matchedActress = found;
                this._preciseMatchSource = source;
                // T5: hero card 出現動畫 — 只在 is_favorite 時觸發（card 才會 x-show=true）
                if (found.is_favorite && !this.showFavoriteActresses) {
                    var self = this;
                    this.$nextTick(function () {
                        requestAnimationFrame(function () {
                            var heroEl = document.querySelector('.hero-card');
                            window.ShowcaseAnimations?.playHeroCardAppear?.(heroEl);
                        });
                    });
                }
            } else if (source === 'metadata') {
                this._isPreciseActressMatch = true;
                this._matchedActress = { name: capturedTerm, is_favorite: false };
                this._preciseMatchSource = source;
            } else {
                this._clearPreciseMatch();
            }
        },

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
                    }
                });
            }

            this.restoreState();        // M2c: 先恢復狀態
            const savedPage = this.page;
            await this.fetchVideos();
            await _loadAliasMap();      // 45-P2: 無條件載入 alias map（影片搜尋也需要）
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
        },

        // --- 狀態恢復 (M2c) ---
        restoreState() {
            // 1. 從 config 取得預設值
            const cfg = window.__SHOWCASE_CONFIG__ || {};
            const defaultSort = cfg.default_sort || 'date';
            const defaultOrder = cfg.default_order === 'ascending' ? 'asc' : 'desc';
            const defaultPerPage = cfg.items_per_page || 90;

            // 2. 從 localStorage 恢復（優先於 config）
            const saved = localStorage.getItem('showcase_state');
            let state = {};
            if (saved) {
                try {
                    state = JSON.parse(saved);
                } catch (e) {
                    console.warn('[Showcase] Failed to parse localStorage:', e);
                }
            }

            // 3. 從 URL params 恢復（最高優先）
            const urlParams = new URLSearchParams(window.location.search);

            // 4. 優先序：URL > localStorage > config > fallback
            //    urlNum: 取 URL 數值參數，空字串視為無值（避免 parseInt("") → NaN）
            const urlNum = (key) => { const v = urlParams.get(key); return v !== null && v !== '' ? v : undefined; };
            this.sort = urlParams.get('sort') || state.sort || defaultSort;
            this.order = urlParams.get('order') || state.order || defaultOrder;
            const rawPerPage = parseInt(urlNum('perPage') ?? state.perPage ?? defaultPerPage);
            this.perPage = Number.isNaN(rawPerPage) ? defaultPerPage : rawPerPage;
            this.page = parseInt(urlNum('page') ?? state.page ?? 1) || 1;
            this.search = urlParams.get('search') || state.search || '';
            this.mode = urlParams.get('mode') || state.mode || 'grid';
            if (!['grid', 'table', 'list'].includes(this.mode)) this.mode = 'grid';
            // F2: grid + perPage=0 組合降級 + 持久化修正值
            if (this.mode === 'grid' && this.perPage === 0) {
                this.perPage = 120;
                this.saveState();
            }
            // ★ 44a: 女優模式 — 只從 localStorage，不加 URL params（避免汙染 shareable link）
            this.showFavoriteActresses = state.showFavoriteActresses === true;  // 嚴格 === true
            this.actressSort = state.actressSort || 'video_count';
            this.actressOrder = state.actressOrder || 'desc';
        },

        // --- 狀態持久化 (M2c) ---
        saveState() {
            const state = {
                sort: this.sort,
                order: this.order,
                perPage: this.perPage,
                page: this.page,
                search: this.search,
                mode: this.mode,
                showFavoriteActresses: this.showFavoriteActresses,  // ★ 44a
                actressSort: this.actressSort,                      // ★ 44a
                actressOrder: this.actressOrder,                    // ★ 44a
            };
            localStorage.setItem('showcase_state', JSON.stringify(state));

            // 同步到 URL（方便分享連結）
            const params = new URLSearchParams();
            if (this.search) params.set('search', this.search);
            if (this.sort !== 'date') params.set('sort', this.sort);
            if (this.order !== 'desc') params.set('order', this.order);
            if (this.perPage !== 90) params.set('perPage', this.perPage);
            if (this.page !== 1) params.set('page', this.page);
            if (this.mode !== 'grid') params.set('mode', this.mode);

            const newUrl = params.toString()
                ? `${window.location.pathname}?${params}`
                : window.location.pathname;
            window.history.replaceState({}, '', newUrl);
        },

        // --- API 呼叫 ---
        async fetchVideos() {
            this.loading = true;
            this.error = '';
            try {
                const resp = await fetch('/api/showcase/videos');
                if (!resp.ok) {
                    _videos = [];
                    this.videoCount = 0;
                    _filteredVideos = [];
                    this.filteredCount = 0;
                    this.error = `伺服器錯誤 (${resp.status})`;
                    return;
                }
                const data = await resp.json();
                if (!data.success) {
                    _videos = [];
                    this.videoCount = 0;
                    _filteredVideos = [];
                    this.filteredCount = 0;
                    this.error = data.error || '載入失敗';
                    return;
                }
                _videos = data.videos || [];
                this.videoCount = _videos.length;
                _filteredVideos = _videos;
                this.filteredCount = _filteredVideos.length;
            } catch (e) {
                console.error('Failed to fetch videos:', e);
                _videos = [];
                this.videoCount = 0;
                _filteredVideos = [];
                this.filteredCount = 0;
                this.error = '無法連線到伺服器';
            } finally {
                this.loading = false;
            }
        },

        // --- 重試（async 安全） ---
        async retry() {
            this.error = '';
            const savedPage = this.page;
            await this.fetchVideos();
            this.applyFilterAndSort(true);  // 跳過 pagination，下面統一處理
            this.page = savedPage;
            this.updatePagination();
            // Settle: retry 也用 settle（不碰 opacity → 不閃）
            if (this.mode === 'grid' && !this.error) {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    var grid = this._getActiveGrid();
                    window.ShowcaseAnimations?.playSettle?.(grid);
                }); });
            }
        },

        // --- 互動邏輯 (M2a 只定義骨架，M4 才實作完整邏輯) ---
        onSearchChange() {
            // B8: 透過 _animateFilter 觸發篩選動畫
            this._animateFilter();
            var trimmed = this.search.trim();
            if (!trimmed) {
                this._clearPreciseMatch();
            } else {
                this._checkPreciseActressMatch(trimmed, 'manual');
            }
        },

        onSortChange() {
            this._sortWithFlip(() => {
                this.applyFilterAndSort();
            });
        },

        toggleOrder() {
            this._sortWithFlip(() => {
                this.order = this.order === 'asc' ? 'desc' : 'asc';
                this.applyFilterAndSort();
            });
        },

        // --- 44a: 女優模式核心方法 ---

        toggleActressMode() {
            if (this.lightboxOpen) this.closeLightbox();
            var self = this;
            var isEnteringActress = !this.showFavoriteActresses;
            var oldMode = isEnteringActress ? (this.mode || 'grid') : 'actress';
            var newMode = isEnteringActress ? 'actress' : (this.mode || 'grid');
            var gen = ++this._animGeneration;

            // Codex P1: 抽出 callback body 作 fallback；若 playModeCrossfade 不可用直接同步呼叫
            var flipAndFadeIn = function () {
                if (self._animGeneration !== gen) return;
                // 翻轉（觸發 x-if 重新掛載 DOM）
                self.showFavoriteActresses = isEnteringActress;
                var needEntry = false;
                if (isEnteringActress) {
                    self._clearPreciseMatch();
                    if (_actresses.length === 0) {
                        self.loadActresses();
                    } else {
                        needEntry = true;
                    }
                } else {
                    needEntry = true;
                    var searchTerm = self.search.trim();
                    if (searchTerm) {
                        self._checkPreciseActressMatch(searchTerm, 'manual');
                    }
                }
                // Phase 2: $nextTick 後 fade-in 新容器
                var gen2 = ++self._animGeneration;
                self.$nextTick(function () {
                    if (self._animGeneration !== gen2) return;
                    var newSelector = newMode === 'actress' ? '.actress-grid'
                        : newMode === 'table' ? '.showcase-table-wrapper'
                        : newMode === 'list' ? '.showcase-list-wrapper'
                        : '.showcase-grid';
                    var newEl = document.querySelector(newSelector);
                    // Codex P2: reduced-motion / gsap missing 由 helper 內 shouldSkip / typeof 守衛處理
                    window.ShowcaseAnimations?.playContainerFadeIn?.(newEl);
                    if (needEntry) {
                        var grid = self._getActiveGrid();
                        window.ShowcaseAnimations?.playEntry?.(grid);
                    }
                });
                self.saveState();
            };

            var fade = window.ShowcaseAnimations && window.ShowcaseAnimations.playModeCrossfade;
            if (typeof fade === 'function') {
                fade.call(window.ShowcaseAnimations, oldMode, null, null, {
                    onOldFadeComplete: flipAndFadeIn
                });
            } else {
                // P1 fallback: animations.js 不可用 → 直接同步翻轉 + 進入 fade-in（會被 reduced-motion / gsap-undef guard 自然降級）
                flipAndFadeIn();
            }
        },

        async loadActresses() {
            this.actressLoading = true;
            try {
                var resp = await fetch('/api/actresses');
                if (!resp.ok) {
                    _actresses = [];
                    _filteredActresses = [];
                    this.actressCount = 0;
                    this.filteredActressCount = 0;
                    return;
                }
                var data = await resp.json();
                if (!data.success) {
                    _actresses = [];
                    _filteredActresses = [];
                    this.actressCount = 0;
                    this.filteredActressCount = 0;
                    return;
                }
                _actresses = data.actresses || [];
                // 45: alias map（冪等，init 可能已載入）
                await _loadAliasMap();
                this.applyActressFilterAndSort();
                // 卡片進場動畫（applyActressFilterAndSort 更新 paginatedActresses，Alpine 渲染後呼叫）
                var gen = ++this._animGeneration;
                var self = this;
                this.$nextTick(function () { requestAnimationFrame(function () {
                    if (self._animGeneration !== gen) return;
                    var grid = self._getActiveGrid();
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            } catch (e) {
                console.error('[Showcase] Failed to fetch actresses:', e);
                _actresses = [];
                _filteredActresses = [];
                this.actressCount = 0;
                this.filteredActressCount = 0;
            } finally {
                this.actressLoading = false;
                _actressesLoaded = true;
            }
        },

        applyActressFilterAndSort() {
            // 1. Filter
            var q = this.actressSearch.trim();
            var filtered = _actresses;
            if (q) {
                var ql = q.toLowerCase();
                filtered = _actresses.filter(function (a) {
                    var group = _nameToGroup[a.name] || [a.name];
                    return group.some(function(n) { return n && n.toLowerCase().includes(ql); });
                });
            }

            // 2. Sort
            var cupRank = { A:1, B:2, C:3, D:4, E:5, F:6, G:7, H:8, I:9, J:10, K:11 };
            var sort = this.actressSort;
            var order = this.actressOrder;
            filtered = filtered.slice().sort(function (a, b) {
                if (sort === 'name') {
                    var cmp = a.name.localeCompare(b.name, 'ja');
                    return order === 'asc' ? cmp : -cmp;
                }
                var va, vb;
                if (sort === 'video_count') {
                    va = a.video_count || 0;
                    vb = b.video_count || 0;
                } else if (sort === 'added_at') {
                    va = a.created_at || '';
                    vb = b.created_at || '';
                } else if (sort === 'age') {
                    va = a.age != null ? a.age : Infinity;
                    vb = b.age != null ? b.age : Infinity;
                } else if (sort === 'height') {
                    var ha = parseInt(a.height);
                    var hb = parseInt(b.height);
                    va = isNaN(ha) ? Infinity : ha;
                    vb = isNaN(hb) ? Infinity : hb;
                } else if (sort === 'cup') {
                    va = cupRank[a.cup] || Infinity;
                    vb = cupRank[b.cup] || Infinity;
                } else {
                    va = a.video_count || 0;
                    vb = b.video_count || 0;
                }
                // null-last：Infinity 值永遠排最後（不因 desc 翻轉）
                if (va === Infinity && vb === Infinity) return 0;
                if (va === Infinity) return 1;
                if (vb === Infinity) return -1;
                if (order === 'asc') {
                    return va < vb ? -1 : va > vb ? 1 : 0;
                } else {
                    return va > vb ? -1 : va < vb ? 1 : 0;
                }
            });

            // 3. Update state
            _filteredActresses = filtered;
            this.actressCount = _actresses.length;
            this.filteredActressCount = _filteredActresses.length;
            this.paginatedActresses = _filteredActresses;  // CD-9: 全量，不分頁
        },

        onActressSearchChange() {
            this.applyActressFilterAndSort();
        },

        onActressSortChange() {
            this._sortWithFlip(() => {
                this.applyActressFilterAndSort();
            });
        },

        toggleActressOrder() {
            this._sortWithFlip(() => {
                this.actressOrder = this.actressOrder === 'asc' ? 'desc' : 'asc';
                this.applyActressFilterAndSort();
            });
        },

        // --- 44a: 女優 Lightbox 方法 ---

        openActressLightbox(index) {
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }
            if (this._lightboxAnimating) return;
            if (this.lightboxOpen && this.actressLightboxIndex === index) return;

            // 若已開啟（切換女優）
            if (this.lightboxOpen && this.actressLightboxIndex !== index) {
                _killLightboxTimelines({ killOpen: false, killSwitch: true });
                var direction = index > this.actressLightboxIndex ? 'next' : 'prev';
                this._setActressLightboxIndex(index);
                this.actressLightboxSource = 'grid';   // T5: 切換女優分支
                // T3: fire-and-forget 即時查 aliases
                this._fetchLiveAliases(this.currentLightboxActress?.name, index);
                var lbGen = ++this._lightboxGeneration;
                var self = this;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, direction, {
                            onComplete: function () { self._lightboxAnimating = false; }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            // ★ ghost fly — 在 state 變更前捕獲 fromRect（對齊 video mode openLightbox）
            var fromRect = null;
            var coverSrc = null;
            if (!this.lightboxOpen) {
                var gridEl = this._getActiveGrid();
                if (gridEl) {
                    var actress = _filteredActresses[index];
                    var cardEl = actress
                        ? gridEl.querySelector('[data-flip-id="actress:' + CSS.escape(actress.name) + '"]')
                        : null;
                    if (cardEl) {
                        var imgEl = cardEl.querySelector('.actress-card-photo img');
                        if (imgEl && imgEl.complete && imgEl.getBoundingClientRect().width > 0) {
                            fromRect = imgEl.getBoundingClientRect();
                            coverSrc = imgEl.src;
                        }
                    }
                }
            }

            this._setActressLightboxIndex(index);
            this.actressLightboxSource = 'grid';   // T5: 首次進入分支
            var lightboxElPre = document.querySelector('.showcase-lightbox');
            if (lightboxElPre) lightboxElPre.classList.add('gsap-animating');
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');
            // T3: fire-and-forget 即時查 aliases
            this._fetchLiveAliases(this.currentLightboxActress?.name, index);

            var self = this;
            var lbGen = ++this._lightboxGeneration;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var lightboxEl = document.querySelector('.showcase-lightbox');
                if (!lightboxEl) return;

                if (fromRect && window.GhostFly && window.GhostFly.playGridToLightbox) {
                    self._lightboxAnimating = true;
                    window.GhostFly.playGridToLightbox(fromRect, lightboxEl, {
                        coverSrc: coverSrc,
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen) {
                        window.ShowcaseAnimations.playLightboxOpen(lightboxEl, { skipCover: true });
                    }
                } else {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations?.playLightboxOpen?.(lightboxEl, {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        closeActressLightbox() {
            this.closeLightbox();
        },

        prevActressLightbox() {
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            if (this.actressLightboxIndex <= 0) return;
            var newIdx = this.actressLightboxIndex - 1;
            this._setActressLightboxIndex(newIdx);
            // P2 Codex: 方向鍵切換也要 fetch live alias，否則 SSOT 心智模型在切換時破功
            this._fetchLiveAliases(this.currentLightboxActress?.name, newIdx);

            var lbGen = ++this._lightboxGeneration;
            var self = this;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'prev', {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        nextActressLightbox() {
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            if (this.actressLightboxIndex >= _filteredActresses.length - 1) return;
            var newIdx = this.actressLightboxIndex + 1;
            this._setActressLightboxIndex(newIdx);
            // P2 Codex: 方向鍵切換也要 fetch live alias，否則 SSOT 心智模型在切換時破功
            this._fetchLiveAliases(this.currentLightboxActress?.name, newIdx);

            var lbGen = ++this._lightboxGeneration;
            var self = this;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'next', {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        // --- 44a T4: Lightbox chips + metadata helpers ---

        _chipsLimit() {
            return window.innerWidth >= 768 ? 10 : 6;
        },

        _actressCoreMetadata() {
            var a = this.currentLightboxActress; if (!a) return '';
            var parts = [];
            // T2: video_count 前置（CD-3）
            if (typeof a.video_count === 'number') {
                parts.push(a.video_count + window.t('showcase.unit.films'));
            }
            if (a.age) parts.push(a.age + window.t('search.unit.age'));
            if (a.birth) parts.push(a.birth);
            if (a.height) parts.push(a.height);
            if (a.cup) parts.push(a.cup + window.t('search.unit.cup'));
            if (a.bust && a.waist && a.hip) parts.push(a.bust + '-' + a.waist + '-' + a.hip);
            return parts.join(' · ');
        },

        // --- 44c T2: Actress card footer helpers ---

        _actressCardMiddle(actress) {
            if (!actress) return '';
            var sort = this.actressSort;
            if (sort === 'video_count') {
                return (actress.video_count || 0) + window.t('showcase.unit.films');
            }
            if (sort === 'cup') {
                return actress.cup ? actress.cup + window.t('search.unit.cup') : '';
            }
            if (sort === 'height') {
                return actress.height || '';
            }
            // 'age'、'name'、'added_at' 與左右欄重複或過長，不顯示
            return '';
        },

        _actressHoverInfo(actress) {
            if (!actress) return '';
            var parts = [];
            if (actress.height) parts.push(actress.height);
            if (actress.cup) parts.push(actress.cup + window.t('search.unit.cup'));
            if (actress.bust && actress.waist && actress.hip) {
                parts.push(actress.bust + '-' + actress.waist + '-' + actress.hip);
            }
            return parts.join(' \u00b7 ');
        },

        _allInfoChips() {
            var a = this.currentLightboxActress; if (!a) return [];
            return [].concat(a.tags || [], [a.hometown, a.nickname, a.agency, a.hobby, a.debut_work]).filter(Boolean);
        },

        _visibleAliases() {
            var all = this.currentLightboxActress?.aliases || [];
            return this._actressChipsExpanded.aliases ? all : all.slice(0, this._chipsLimit());
        },

        _aliasesOverflow() {
            return Math.max(0, (this.currentLightboxActress?.aliases || []).length - this._chipsLimit());
        },

        // 49a-T3: 開啟 Lightbox 時 async fetch 最新 aliases（Scanner SSOT）
        // 200 才覆蓋 snapshot；404 / timeout / network error 保留 snapshot（fire-and-forget）
        // §8.4 reactivity：用 Object.assign 建立新物件以觸發 Alpine deep watch
        async _fetchLiveAliases(name, expectedIndex) {
            if (!name) return;
            var capturedName = name;
            var self = this;
            try {
                var resp = await fetch('/api/actress-aliases/' + encodeURIComponent(capturedName), {
                    signal: AbortSignal.timeout(3000)   // §8.5: Chrome 103+/Firefox 100+/Safari 15.4+
                });
                if (resp.status === 200) {
                    var data = await resp.json();
                    // Stale-check：lightbox 仍在 + 還是同一個女優 + (若指定) index 一致
                    if (!self.lightboxOpen) return;
                    if (self.currentLightboxActress?.name !== capturedName) return;
                    if (expectedIndex !== null && expectedIndex !== undefined
                        && self.actressLightboxIndex !== expectedIndex) return;
                    var newAliases = (data && data.group && data.group.aliases) || [];
                    self.currentLightboxActress = Object.assign({}, self.currentLightboxActress, {
                        aliases: newAliases
                    });
                }
                // 404 / 5xx → 保留 snapshot，靜默
            } catch (e) {
                // timeout / network error → 保留 snapshot，靜默
                if (window.console && console.warn) console.warn('[T3] alias live fetch failed:', e);
            }
        },

        _visibleInfoChips() {
            var all = this._allInfoChips();
            return this._actressChipsExpanded.info ? all : all.slice(0, this._chipsLimit());
        },

        _infoChipsOverflow() {
            return Math.max(0, this._allInfoChips().length - this._chipsLimit());
        },

        _visibleVideoTags() {
            var tags = (this.currentLightboxVideo?.tags || '').split(',').filter(function(t) { return t.trim(); });
            return this._videoChipsExpanded ? tags : tags.slice(0, this._chipsLimit());
        },

        _videoTagsOverflow() {
            var tags = (this.currentLightboxVideo?.tags || '').split(',').filter(function(t) { return t.trim(); });
            return Math.max(0, tags.length - this._chipsLimit());
        },

        // --- 44a T5: Actress CRUD ---

        async addFavoriteActress() {
            if (this._addingActress || !this._addActressName.trim()) return;
            this._addingActress = true;
            try {
                const resp = await fetch('/api/actresses/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: this._addActressName.trim() }),
                });
                const data = await resp.json();
                if (resp.status === 409) {
                    this.showToast(window.t('showcase.actress.addDuplicate'), 'info');
                } else if (resp.status === 404) {
                    this.showToast(window.t('showcase.actress.addNotFound'), 'error');
                } else if (resp.status === 504) {
                    this.showToast(window.t('showcase.actress.addTimeout'), 'error');
                } else if (data.success) {
                    _actresses.push(data.actress);
                    this.applyActressFilterAndSort();
                    this._addDropdownOpen = false;
                    this.showToast(window.t('showcase.actress.addSuccess'), 'success');
                } else {
                    this.showToast(window.t('showcase.actress.addNotFound'), 'error');
                }
            } catch (e) {
                this.showToast(window.t('showcase.actress.addNotFound'), 'error');
            } finally {
                this._addingActress = false;
                this._addActressName = '';
            }
        },

        async addFavoriteFromSearch() {
            if (this._favoriteHeartLoading || this._matchedActress?.is_favorite) return;
            this._favoriteHeartLoading = true;
            var capturedName = this._matchedActress?.name;
            if (!capturedName) { this._favoriteHeartLoading = false; return; }
            try {
                var resp = await fetch('/api/actresses/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: capturedName })
                });
                if (!this._matchedActress || this._matchedActress.name !== capturedName) return;
                if (resp.status === 200 || resp.status === 409) {
                    var data = await resp.json();
                    var actress = data.actress || data;
                    actress.is_favorite = true;
                    this._matchedActress = actress;
                    if (!_actresses.find(function(a) { return a.name === actress.name; })) {
                        _actresses.push(actress);
                        this.applyActressFilterAndSort();
                    }
                    if (resp.status === 200) {
                        this.showToast(window.t('showcase.actress.addSuccess'), 'success');
                    } else {
                        this.showToast(window.t('showcase.actress.addDuplicate'), 'info');
                    }
                } else if (resp.status === 404) {
                    this.showToast(window.t('showcase.actress.addNotFound'), 'error');
                } else {
                    this.showToast(window.t('showcase.actress.addTimeout'), 'error');
                }
            } catch (err) {
                this.showToast(window.t('showcase.actress.addTimeout'), 'error');
            } finally {
                this._favoriteHeartLoading = false;
            }
        },

        async removeActress() {
            if (!this.currentLightboxActress) return;
            const name = this.currentLightboxActress.name;
            const confirmed = window.confirm(window.t('showcase.actress.removeConfirm').replace('{name}', name));
            if (!confirmed) return;
            try {
                const resp = await fetch(`/api/actresses/${encodeURIComponent(name)}`, {
                    method: 'DELETE',
                });
                const data = await resp.json();
                if (data.success) {
                    const idx = _actresses.findIndex(a => a.name === name);
                    if (idx >= 0) _actresses.splice(idx, 1);
                    this.applyActressFilterAndSort();
                    if (this.currentLightboxActress?.name !== name) {
                        // stale guard: lightbox switched to a different actress during request
                        // array cleanup already done above, but don't close lightbox
                        this.showToast(window.t('showcase.actress.removeSuccess'), 'success');
                        return;
                    }
                    this.closeActressLightbox();
                    this.showToast(window.t('showcase.actress.removeSuccess'), 'success');
                    var searchTerm = this.search.trim();
                    if (searchTerm) {
                        this._checkPreciseActressMatch(searchTerm, 'manual');
                    }
                } else {
                    this.showToast(data.error || 'Error', 'error');
                }
            } catch (e) {
                this.showToast('Error', 'error');
            }
        },

        // --- 44c T7: Search actress films（49a-T7：跨模式 Ghost Fly 動畫）---
        async searchActressFilms(actressName, fromEl) {
            if (!actressName) return;
            if (this._ghostFlyInFlight) return;   // CD-13: 連點保護
            var self = this;
            var wasActressMode = this.showFavoriteActresses;

            // §8.3: 用 IIFE try/catch 包住主流程，避免 unhandled rejection；
            //       任何 throw 也會 reset _ghostFlyInFlight 防卡死。
            try {
                // 捕獲來源 rect / coverSrc（必須在 closeLightbox / state 變更前）
                var fromRect = null;
                var coverSrc = null;
                if (wasActressMode && fromEl) {
                    var fromImg = fromEl.closest('.actress-card')?.querySelector('.actress-card-photo img')
                        || fromEl.closest('.showcase-lightbox')?.querySelector('.lightbox-cover img');
                    if (fromImg) {
                        fromRect = fromImg.getBoundingClientRect();
                        coverSrc = fromImg.src;
                    }
                }

                if (this.lightboxOpen) this.closeLightbox();
                if (wasActressMode) {
                    this.showFavoriteActresses = false;
                    this.actressSearch = '';
                }
                this.search = actressName;
                this._animateFilter();

                // 非女優模式 / 無 fromEl / 無 coverSrc → fallback 走原有同步行為
                if (!wasActressMode || !fromRect || !coverSrc) {
                    this._checkPreciseActressMatch(actressName, 'metadata');
                    if (wasActressMode) {
                        var gen0 = ++this._animGeneration;
                        this.$nextTick(function () {
                            if (self._animGeneration !== gen0) return;
                            window.ShowcaseAnimations?.playModeCrossfade?.('actress', self.mode);
                            if (self.mode === 'grid') {
                                var grid0 = self._getActiveGrid();
                                window.ShowcaseAnimations?.playEntry?.(grid0);
                            }
                        });
                    }
                    return;
                }

                // === Ghost Fly 主流程 ===
                this._ghostFlyInFlight = true;
                var gen = ++this._animGeneration;

                // 淡出女優 grid（T1 playModeCrossfade 的 fade-out 部分）
                window.ShowcaseAnimations?.playModeCrossfade?.('actress', null, null, {
                    onOldFadeComplete: function () {}
                });
                // 影片 grid 淡入（$nextTick 後）
                this.$nextTick(function () {
                    if (self._animGeneration !== gen) return;
                    var newEl = document.querySelector('.showcase-grid');
                    window.ShowcaseAnimations?.playContainerFadeIn?.(newEl);
                    window.ShowcaseAnimations?.playEntry?.(self._getActiveGrid());
                });

                // ⚠️ Gotcha：_checkPreciseActressMatch 依搜尋詞守衛 return（不重設 _isPreciseActressMatch），
                //     所以 await 前先手動 reset false，避免讀到上一次搜尋的殘留 true。
                self._isPreciseActressMatch = false;

                await self._checkPreciseActressMatch(actressName, 'metadata');

                // _animGeneration 比對：若 stale（多次點擊），中止主流程
                if (self._animGeneration !== gen) {
                    self._ghostFlyInFlight = false;
                    return;
                }

                // 等 hero card DOM render（最多 500ms 輪詢）
                var heroCardEl = null;
                var TIMEOUT = 500;
                var elapsed = 0;
                var interval = 30;
                await new Promise(function (resolve) {
                    var checker = setInterval(function () {
                        elapsed += interval;
                        var hero = document.querySelector('.hero-card');
                        if (hero && hero.getBoundingClientRect().width > 0) {
                            heroCardEl = hero;
                            clearInterval(checker);
                            resolve();
                        } else if (elapsed >= TIMEOUT) {
                            clearInterval(checker);
                            resolve();
                        }
                    }, interval);
                });

                // 再次 stale 檢查
                if (self._animGeneration !== gen) {
                    self._ghostFlyInFlight = false;
                    return;
                }

                // CD-12: 降級條件（5 條件全通過才走主流程）
                var canMainFlow = heroCardEl
                    && self._isPreciseActressMatch
                    && self._matchedActress
                    && self._matchedActress.is_favorite !== false
                    && coverSrc;

                // 降級 helper：來源圖 pulse + 釋放 flag（搜尋欄 / empty state 已自動處理）
                var doFallback = function () {
                    self._ghostFlyInFlight = false;
                    if (fromEl) {
                        var pulseTarget = fromEl.closest('.actress-card')?.querySelector('.actress-card-photo img')
                            || fromEl.closest('.showcase-lightbox')?.querySelector('.lightbox-cover img');
                        window.ShowcaseAnimations?.playSourcePulse?.(pulseTarget);
                    }
                };

                if (canMainFlow) {
                    // P1 Codex: explicit availability check — optional chaining 缺失時 silent no-op，
                    // onComplete/onFallback 都不會被呼叫，flag 永久 true → camera button 永久 disabled。
                    if (typeof window.GhostFly?.playActressToHeroCard !== 'function') {
                        doFallback();
                        return;
                    }
                    // 主流程：ghost fly（已驗證存在，直接呼叫強化 callback 契約）
                    window.GhostFly.playActressToHeroCard(fromRect, heroCardEl, {
                        coverSrc: coverSrc,
                        onComplete: function () { self._ghostFlyInFlight = false; },
                        onFallback: function () { self._ghostFlyInFlight = false; }
                    });
                } else {
                    doFallback();
                }
            } catch (e) {
                // §8.3 防禦：任何 throw 都釋放 flag 防卡死
                self._ghostFlyInFlight = false;
                console.warn('[T7][searchActressFilms]', e);
            }
        },

        // --- 44c T6: Active grid helper ---
        _getActiveGrid() {
            return this.showFavoriteActresses
                ? document.querySelector('.actress-grid')
                : document.querySelector('.showcase-grid');
        },

        /**
         * B7/B15: 排序動畫共用 helper — flip-guard → capture → change → Flip reorder
         * @param {Function} changeFn - 執行 data change 的函數
         */
        _sortWithFlip(changeFn) {
            var savedPage = this.page;
            var grid = null;
            var positionMap = null;

            // Step 0: capture（grid mode 或女優模式）
            if (this.mode === 'grid' || this.showFavoriteActresses) {
                grid = this._getActiveGrid();
                if (grid) {
                    grid.classList.add('flip-guard');
                    void grid.offsetHeight;  // force reflow
                    positionMap = window.ShowcaseAnimations?.capturePositions?.(grid) || null;
                }
            }

            // Step 1: data change
            changeFn();
            this.page = savedPage;
            this.updatePagination();
            this.saveState();

            // Step 2: animate
            if (grid && positionMap) {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) {
                        grid.classList.remove('flip-guard');
                        return;
                    }
                    var result = window.ShowcaseAnimations?.playFlipReorder?.(grid, positionMap);
                    if (!result) {
                        // fallback: Flip 回傳 null（delta 全零、reduced motion 等）
                        grid.classList.remove('flip-guard');
                        window.ShowcaseAnimations?.playEntry?.(grid);
                    }
                    // flip-guard 由 playFlipReorder 的 onComplete 移除
                }); });
            } else if (grid) {
                // capture 失敗 fallback
                grid.classList.remove('flip-guard');
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        /**
         * B8/B15: 篩選動畫共用 helper — flip-guard → capture → change → Flip filter
         * onSearchChange() 和 searchFromMetadata() 共用
         */
        _animateFilter() {
            var grid = null;
            var state = null;

            // Step 0: capture（僅 grid mode）
            if (this.mode === 'grid') {
                grid = this._getActiveGrid();
                if (grid) {
                    grid.classList.add('flip-guard');
                    void grid.offsetHeight;  // force reflow
                    state = window.ShowcaseAnimations?.captureFlipState?.(grid) || null;
                }
            }

            // Step 1: data change
            this.applyFilterAndSort();
            this.saveState();

            // Step 2: animate
            if (grid && state) {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) {
                        grid.classList.remove('flip-guard');
                        return;
                    }
                    var result = window.ShowcaseAnimations?.playFlipFilter?.(grid, state);
                    if (!result) {
                        grid.classList.remove('flip-guard');
                        window.ShowcaseAnimations?.playEntry?.(grid);
                    }
                    // flip-guard 由 playFlipFilter 的 onComplete 移除
                }); });
            } else if (grid) {
                // capture 失敗 fallback
                grid.classList.remove('flip-guard');
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        /**
         * B9/B13: 分頁動畫 — state-first + playEntry
         * @param {string} direction - 'next' | 'prev'
         * @param {number} [targetPage] - 目標頁碼（goToPage 用，prevPage/nextPage 不傳）
         */
        _animatePageChange(direction, targetPage) {
            // 清理可能殘留的 flip-guard（sort/filter 動畫被翻頁打斷時）
            var grid = document.querySelector('.showcase-grid');
            if (grid) grid.classList.remove('flip-guard');

            // 計算目標頁碼
            var newPage = targetPage;
            if (newPage === undefined) {
                newPage = direction === 'next' ? this.page + 1 : this.page - 1;
            }

            // State mutation FIRST（不再困在回調中）
            this.page = newPage;
            this.updatePagination();
            this.saveState();
            window.scrollTo(0, 0);

            // Grid mode：播放進場動畫
            if (this.mode === 'grid') {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;  // stale
                    var grid = document.querySelector('.showcase-grid');
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        onPerPageChange() {
            this.page = 1;
            this.updatePagination();
            this.saveState();  // M2c: 持久化狀態
            // B17: 切換每頁數量後播放進場動畫
            if (this.mode === 'grid') {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    var grid = document.querySelector('.showcase-grid');
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        switchMode(m) {
            if (!['grid', 'table', 'list'].includes(m)) return;
            if (m === this.mode) return;
            var oldMode = this.mode;
            this.mode = m;
            // F2: 切到 grid 時若 perPage=0 則降級
            if (m === 'grid' && this.perPage == 0) {
                this.perPage = 120;
                this.updatePagination();
            }
            this.saveState();  // M2c: 持久化狀態
            this.$nextTick(() => {
                window.ShowcaseAnimations?.playModeCrossfade?.(oldMode, m);
            });
        },

        // Card Info 切換 (M3i)
        toggleInfo() {
            this.infoVisible = !this.infoVisible;
        },

        prevPage() {
            if (this.page > 1) {
                this._animatePageChange('prev');
            }
        },

        nextPage() {
            if (this.page < this.totalPages) {
                this._animatePageChange('next');
            }
        },

        // Status bar 頁面跳轉 (M3g)
        goToPage(p) {
            const num = parseInt(p);
            if (Number.isNaN(num) || num < 1 || num > this.totalPages) return;
            if (num === this.page) return;
            var direction = num > this.page ? 'next' : 'prev';
            this._animatePageChange(direction, num);
        },

        /**
         * 49a-T4 / Codex P2: 開啟隱藏 select 的 native picker
         * 隱藏 select 用 .click() 在主流瀏覽器只 dispatch event 不會開 picker；
         * showPicker() (Chrome 99+/FF 98+/Safari 16.4+) 才會真的彈出。
         * 失敗（不支援 / non-user-gesture SecurityError）fallback 回 .click()。
         */
        openPagePicker(selectEl) {
            if (!selectEl) return;
            if (typeof selectEl.showPicker === 'function') {
                try { selectEl.showPicker(); return; } catch (e) { /* fall through */ }
            }
            selectEl.click();
        },

        // --- 資料處理 (M2a 基本實作，M4 完整化) ---
        applyFilterAndSort(skipPagination) {
            // --- 搜尋篩選 (M4a) ---
            if (this.search && this.search.trim()) {
                // 分割多個關鍵字（用空格分隔，過濾空字串）
                const terms = this.search.toLowerCase().trim().split(/\s+/).filter(t => t.length > 0);

                _filteredVideos = _videos.filter(video => {
                    // 建立所有可搜尋欄位的組合文字（對應原版 L1216）
                    // API 欄位名稱對應：otitle → original_title, actor → actresses, num → number, genre → tags, date → release_date
                    const searchable = [
                        video.title,
                        video.original_title,
                        video.actresses,
                        video.number,
                        video.maker,
                        video.tags,
                        video.release_date,
                        video.path,
                        video.director,
                        video.series,
                        video.label,
                        video.user_tags
                    ].filter(Boolean).join(' ').toLowerCase();

                    // 番號的正規化版本（移除空格和連字號）
                    const numNorm = video.number ? video.number.toLowerCase().replace(/[\s\-]/g, '') : '';

                    // 每個關鍵字都要匹配（AND 邏輯）
                    return terms.every(term => {
                        const termNorm = term.replace(/[\s\-]/g, '');
                        // 番號模糊匹配
                        if (numNorm && numNorm.includes(termNorm)) return true;
                        // alias 展開 match：搜尋詞反查 alias group，任一 alias name 命中即可
                        var termNames = _nameToGroup[term] || [term];
                        return termNames.some(function(n) { return searchable.includes(n.toLowerCase()); });
                    });
                });
                this.filteredCount = _filteredVideos.length;
            } else {
                // 空搜尋：回傳全部影片
                _filteredVideos = [..._videos];
                this.filteredCount = _filteredVideos.length;
            }

            // --- 排序 (M4b) ---
            _filteredVideos.sort((a, b) => {
                // 1. 女優卡置頂邏輯（原版 L1230-1234）
                //    備註：Showcase 頁面目前不會有 actress: 開頭的路徑（該機制屬於女優 Gallery）
                //    保留此邏輯以確保與原版行為 100% 一致，未來 24-migrate-3 若整合女優 Gallery 時需要
                const aIsHero = a.path && a.path.indexOf('actress:') === 0;
                const bIsHero = b.path && b.path.indexOf('actress:') === 0;
                if (aIsHero && !bIsHero) return -1;
                if (!aIsHero && bIsHero) return 1;

                // 2. Random 排序：立即返回（每次呼叫 applyFilterAndSort 都重新洗牌）
                if (this.sort === 'random') {
                    return Math.random() - 0.5;
                }

                // 3. 其他排序：取得比較值
                let va, vb;
                switch (this.sort) {
                    case 'title':
                        va = a.title || '';
                        vb = b.title || '';
                        break;
                    case 'actor':
                        va = a.actresses || '';
                        vb = b.actresses || '';
                        break;
                    case 'num':
                        va = a.number || '';
                        vb = b.number || '';
                        break;
                    case 'maker':
                        va = a.maker || '';
                        vb = b.maker || '';
                        break;
                    case 'date':
                        va = a.release_date || '';
                        vb = b.release_date || '';
                        break;
                    case 'size':
                        va = a.size || 0;
                        vb = b.size || 0;
                        break;
                    case 'mdate':
                        va = a.mtime || 0;
                        vb = b.mtime || 0;
                        break;
                    default:
                        // 未知排序欄位 fallback 到 path
                        va = a.path || '';
                        vb = b.path || '';
                }

                // 4. 比較邏輯（asc='asc', desc='desc'）
                if (va < vb) return this.order === 'asc' ? -1 : 1;
                if (va > vb) return this.order === 'asc' ? 1 : -1;
                return 0;
            });

            // --- 重置頁碼並更新分頁 ---
            if (!skipPagination) {
                this.page = 1;
                this.updatePagination();
            }
        },

        updatePagination() {
            // F2: grid mode 禁用「全部」— perPage=0 降級為 120
            if (parseInt(this.perPage) === 0 && this.mode === 'grid') {
                this.perPage = 120;
            }
            const perPage = Math.max(0, parseInt(this.perPage) || 0);
            if (perPage === 0) {
                this.paginatedVideos = _filteredVideos;
                this.totalPages = 1;
                this.page = 1;
            } else {
                this.totalPages = Math.max(1, Math.ceil(_filteredVideos.length / perPage));
                // clamp page 到有效範圍
                if (this.page > this.totalPages) this.page = this.totalPages;
                if (this.page < 1) this.page = 1;
                const start = (this.page - 1) * perPage;
                this.paginatedVideos = _filteredVideos.slice(start, start + perPage);
            }
        },

        // --- 播放影片 (PyWebView 整合) ---
        playVideo(path) {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.open_file(path)
                    .then(opened => {
                        if (!opened) this.showToast('播放失敗', 'error');
                    })
                    .catch(err => {
                        console.error('Failed to open file:', err);
                        this.showToast('播放失敗', 'error');
                    });
            } else {
                window.open('/api/gallery/player?path=' + encodeURIComponent(path), '_blank');
            }
        },

        // --- Lightbox (M3a) ---
        openLightbox(index) {
            // F2: cancel pending delayed clear from previous close
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // B16: 動畫進行中 guard
            if (this._lightboxAnimating) return;
            if (this.lightboxOpen && this.lightboxIndex === index) return;  // 同一張，不動作

            // Fix: lightbox 已開啟時走 switch 路徑（避免 backdrop click-through 重播 open 動畫）
            if (this.lightboxOpen && this.lightboxIndex !== index) {
                var self = this;
                // C18: interrupt — kill 舊 switch timeline（含 onComplete callback）
                _killLightboxTimelines({ killOpen: false, killSwitch: true });
                var oldIndex = this.lightboxIndex;
                var direction = index > oldIndex ? 'next' : 'prev';

                // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
                this._setLightboxIndex(index);

                // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;  // stale — lightbox was closed/interrupted
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, direction, {
                            onComplete: function () {
                                self._lightboxAnimating = false;
                            }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            // ★ C17 step 1: ghost fly — 在 state 變更前捕獲 fromRect
            var fromRect = null;
            var coverSrc = null;
            if (!this.lightboxOpen) {
                var gridEl = this._getActiveGrid();
                if (gridEl) {
                    var cardEl;
                    if (this.showFavoriteActresses) {
                        var actress = _filteredActresses[index];
                        cardEl = actress
                            ? gridEl.querySelector('[data-flip-id="actress:' + CSS.escape(actress.name) + '"]')
                            : null;
                    } else {
                        var video = _filteredVideos[index];
                        cardEl = video
                            ? gridEl.querySelector('[data-flip-id="' + CSS.escape(video.path) + '"]')
                            : null;
                    }
                    if (cardEl) {
                        var imgEl = cardEl.querySelector('.av-card-preview-img img, .actress-card-photo img');
                        if (imgEl && imgEl.complete && imgEl.getBoundingClientRect().width > 0) {
                            fromRect = imgEl.getBoundingClientRect();
                            coverSrc = imgEl.src;
                        }
                    }
                }
            }

            this._setLightboxIndex(index);
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.add('gsap-animating');
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');

            // B16: GSAP 進場動畫（fire-and-forget）
            var self = this;
            var lbGen = ++this._lightboxGeneration;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                if (!lightboxEl) return;

                if (fromRect && window.GhostFly && window.GhostFly.playGridToLightbox) {
                    self._lightboxAnimating = true;
                    window.GhostFly.playGridToLightbox(fromRect, lightboxEl, {
                        coverSrc: coverSrc,
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen) {
                        window.ShowcaseAnimations.playLightboxOpen(lightboxEl, { skipCover: true });
                    }
                } else {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen
                        ? window.ShowcaseAnimations.playLightboxOpen(lightboxEl, {
                            onComplete: function () { self._lightboxAnimating = false; }
                        })
                        : null;
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        openHeroCardLightbox() {
            if (this._lightboxAnimating) return;
            if (!this._matchedActress) return;
            this._actressChipsExpanded = { aliases: false, info: false };
            // ★ 直接賦值（不走 _setLightboxIndex(-1)）
            // 理由：_setLightboxIndex 永遠設 currentLightboxActress = null（line 140）
            // 直接賦值避免破壞 closeLightbox() 250ms delayed clear path
            this.lightboxIndex = -1;
            this.currentLightboxActress = this._matchedActress;
            this.currentLightboxVideo = null;
            this.addingLbTag = false;
            this._videoChipsExpanded = false;
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.add('gsap-animating');
            this.actressLightboxSource = 'hero';   // T5: hero card 路徑
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');
            // T3: fire-and-forget 即時查 aliases（hero card 路徑無 grid index）
            this._fetchLiveAliases(this._matchedActress?.name, null);

            // B19: 進場動畫（fire-and-forget，generation-guarded）
            var lbGen = ++this._lightboxGeneration;
            var self = this;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var el = document.querySelector('.showcase-lightbox');
                if (window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen) {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations.playLightboxOpen(el, {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        closeLightbox() {
            // F2: cancel pending delayed clear from previous close / searchFromMetadata
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // 49b T4 fix: 若 picker 開啟中，先關閉 picker（避免 SSE/timer 洩漏到隱藏狀態）
            if (this._pickerOpen) {
                this._closePicker();
            }

            this.addingLbTag = false;    // 關閉 lightbox 時重置 user tag 輸入框
            this._fetchSamplesFailed = {};

            // ★ C11: fly-back — 必須在 generation++ / lightboxOpen = false 之前捕獲
            var closingIndex = this.showFavoriteActresses
                ? this.actressLightboxIndex
                : this.lightboxIndex;
            var lbEl = document.querySelector('.showcase-lightbox');
            var lbImg = lbEl ? lbEl.querySelector('.lightbox-cover img') : null;
            var flybackFromRect = lbImg ? lbImg.getBoundingClientRect() : null;
            var flybackCoverSrc = lbImg ? lbImg.src : null;

            // 快照 fly-back 目標的 data-flip-id（在狀態變更前，避免 toggleActressMode / removeActress 翻轉後失效）
            var flybackFlipId = null;
            if (closingIndex >= 0) {
                if (this.showFavoriteActresses) {
                    var actress = _filteredActresses[closingIndex];
                    if (actress) flybackFlipId = 'actress:' + actress.name;
                } else {
                    var video = _filteredVideos[closingIndex];
                    if (video) flybackFlipId = video.path;
                }
            }

            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            // Instant close — kill any in-progress lightbox animations, then sync cleanup
            _killLightboxTimelines();
            if (lbEl) lbEl.classList.remove('gsap-animating');
            // Phase 50.x cleanup: kill timeline 後 clearProps 確保下次 open 從乾淨狀態起
            // (timeline.kill() 不觸發 onInterrupt，需在此補做；防連點關開累積 stutter)
            if (lbEl && window.OpenAver && window.OpenAver.motion) {
                var _lbContent = lbEl.querySelector('.lightbox-content');
                var _lbCoverImg = lbEl.querySelector('.lightbox-cover img');
                window.OpenAver.motion.clearProps(_lbContent, 'transform,opacity');
                window.OpenAver.motion.clearProps(_lbCoverImg, 'transform,opacity');
            }
            this._lightboxAnimating = false;
            this.lightboxOpen = false;
            this.actressLightboxSource = null;   // T5: reset 進入路徑
            document.body.classList.remove('overflow-hidden');

            // ★ Fly-back — 用快照的 flipId 在整個頁面搜尋，不依賴 mode 或活陣列
            if (flybackFlipId && flybackFromRect && window.GhostFly && window.GhostFly.playLightboxToGrid) {
                var self = this;
                this.$nextTick(function () {
                    var cardEl = document.querySelector('[data-flip-id="' + CSS.escape(flybackFlipId) + '"]');
                    if (cardEl) {
                        window.GhostFly.playLightboxToGrid(flybackFromRect, cardEl, { coverSrc: flybackCoverSrc });
                    }
                });
            }

            // F2: delay state clearing until CSS transition completes (250ms)
            // Keep currentLightboxVideo intact during fade-out, then clear after
            // Generation-guarded to prevent stale callback from clearing newly-opened lightbox
            var self = this;
            var gen = this._lightboxGeneration;  // capture current generation
            this.lightboxCloseTimer = setTimeout(() => {
                if (self._lightboxGeneration === gen && !self.lightboxOpen) {
                    self._setLightboxIndex(-1);
                }
                self.lightboxCloseTimer = null;
            }, 250);
        },

        // ==================== Sample Gallery Methods (T7) ====================

        openSampleGallery(images, startIdx) {
            if (!images || images.length === 0) return;
            this.sampleGalleryImages = images;
            this.sampleGalleryIndex = startIdx || 0;
            this._sgGeneration++;
            this.sampleGalleryOpen = true;
        },

        closeSampleGallery() {
            this.sampleGalleryOpen = false;
            // 不影響 lightboxOpen 狀態（lightbox 維持開啟）
        },

        prevSampleGallery() {
            if (this.sampleGalleryIndex <= 0) return;
            var prevIdx = this.sampleGalleryIndex - 1;
            this._sgGeneration++;
            var gen = this._sgGeneration;
            this.sampleGalleryIndex = prevIdx;
            // C17: state-first，$nextTick 後播動畫
            var self = this;
            this.$nextTick(() => {
                if (self._sgGeneration !== gen) return; // stale check
                var imgEl = document.querySelector('.sg-main-img');
                if (imgEl) {
                    window.ShowcaseAnimations?.playSampleGallerySwitch?.(imgEl, 'prev', {});
                }
            });
        },

        nextSampleGallery() {
            if (this.sampleGalleryIndex >= this.sampleGalleryImages.length - 1) return;
            var nextIdx = this.sampleGalleryIndex + 1;
            this._sgGeneration++;
            var gen = this._sgGeneration;
            this.sampleGalleryIndex = nextIdx;
            // C17: state-first，$nextTick 後播動畫
            var self = this;
            this.$nextTick(() => {
                if (self._sgGeneration !== gen) return; // stale check
                var imgEl = document.querySelector('.sg-main-img');
                if (imgEl) {
                    window.ShowcaseAnimations?.playSampleGallerySwitch?.(imgEl, 'next', {});
                }
            });
        },

        jumpSampleGallery(idx) {
            if (idx === this.sampleGalleryIndex) return;
            var direction = idx > this.sampleGalleryIndex ? 'next' : 'prev';
            this._sgGeneration++;
            var gen = this._sgGeneration;
            this.sampleGalleryIndex = idx;
            // C17: state-first，$nextTick 後播動畫
            var self = this;
            this.$nextTick(() => {
                if (self._sgGeneration !== gen) return; // stale check
                var imgEl = document.querySelector('.sg-main-img');
                if (imgEl) {
                    window.ShowcaseAnimations?.playSampleGallerySwitch?.(imgEl, direction, {});
                }
            });
        },

        _sgTouchStart(e) {
            if (e.touches && e.touches.length > 0) {
                this._sgTouchStartX = e.touches[0].clientX;
            }
        },

        _sgTouchEnd(e) {
            if (this._sgTouchStartX === null) return;
            var endX = e.changedTouches && e.changedTouches.length > 0
                ? e.changedTouches[0].clientX
                : null;
            if (endX === null) { this._sgTouchStartX = null; return; }
            var delta = endX - this._sgTouchStartX;
            this._sgTouchStartX = null;
            if (Math.abs(delta) < 50) return; // swipe threshold
            if (delta < 0) {
                this.nextSampleGallery(); // swipe left → next
            } else {
                this.prevSampleGallery(); // swipe right → prev
            }
        },

        // ==================== End Sample Gallery Methods ====================

        // Metadata 點擊搜尋 (M3f)
        searchFromMetadata(term, type) {
            // F2: cancel pending delayed clear from previous close
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // 同步關閉 lightbox（跳過動畫，後面馬上做 filter 動畫）
            _killLightboxTimelines();
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.remove('gsap-animating');
            this._lightboxAnimating = false;
            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            this.lightboxOpen = false;
            document.body.classList.remove('overflow-hidden');

            // F2: delay state clearing until CSS transition completes (250ms)
            // Keep currentLightboxVideo intact during fade-out, then clear after
            // Generation-guarded to prevent stale callback from clearing newly-opened lightbox
            var self = this;
            var gen = this._lightboxGeneration;  // capture current generation
            this.lightboxCloseTimer = setTimeout(() => {
                // Only proceed if:
                // 1. Generation hasn't changed (lightbox wasn't reopened)
                // 2. lightboxOpen is false (lightbox is actually closed)
                if (self._lightboxGeneration === gen && !self.lightboxOpen) {
                    self._setLightboxIndex(-1);
                }
                self.lightboxCloseTimer = null;
            }, 250);

            this.search = term;
            this._animateFilter();
            if (type === 'actress') {
                this._checkPreciseActressMatch(term, 'metadata');
            } else {
                this._clearPreciseMatch();
            }
        },

        // 44b-T4: Nav arrow visibility computed（同 /search base.js lines 205-219）
        hasVisiblePrev() {
            if (this.showFavoriteActresses) return this.actressLightboxIndex > 0;
            if (this.lightboxIndex === -1) return false;
            if (this.lightboxIndex === 0) {
                return this._isPreciseActressMatch && !!this._matchedActress && !!this._matchedActress.is_favorite;
            }
            return this.lightboxIndex > 0;
        },

        hasVisibleNext() {
            if (this.showFavoriteActresses) return this.actressLightboxIndex < this.filteredActressCount - 1;
            if (this.lightboxIndex === -1) {
                return _filteredVideos.length > 0;
            }
            return this.lightboxIndex < _filteredVideos.length - 1;
        },

        prevLightboxVideo() {
            // C18: interrupt — kill open + switch timeline（進場動畫未完也要打斷）
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            // 44b: -1 sentinel — already at leftmost, do not move
            if (this.lightboxIndex === -1) return;

            // 44b: index 0 + hero card → retreat to -1
            if (this.lightboxIndex === 0 && this._isPreciseActressMatch && this._matchedActress && this._matchedActress.is_favorite) {
                var self = this;
                // B19: state-first（直接賦值設 -1 sentinel state）
                this.lightboxIndex = -1;
                this.currentLightboxActress = this._matchedActress;
                this.currentLightboxVideo = null;
                this.addingLbTag = false;
                this._videoChipsExpanded = false;

                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'prev', {
                            onComplete: function () { self._lightboxAnimating = false; }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            if (this.lightboxIndex > 0) {
                var self = this;
                var newIdx = this.lightboxIndex - 1;

                // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
                this._setLightboxIndex(newIdx);

                // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;  // stale — lightbox was closed/interrupted
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'prev', {
                            onComplete: function () {
                                self._lightboxAnimating = false;
                            }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
            }
        },

        nextLightboxVideo() {
            // C18: interrupt — kill open + switch timeline（進場動畫未完也要打斷）
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            // 44b: from -1 (hero card) → jump to first video
            if (this.lightboxIndex === -1) {
                if (_filteredVideos.length === 0) return;
                var self = this;
                // B19: state-first（呼叫 _setLightboxIndex 設 video + 清 actress）
                this._setLightboxIndex(0);

                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'next', {
                            onComplete: function () { self._lightboxAnimating = false; }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            if (this.lightboxIndex < _filteredVideos.length - 1) {
                var self = this;
                var newIdx = this.lightboxIndex + 1;

                // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
                this._setLightboxIndex(newIdx);

                // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;  // stale — lightbox was closed/interrupted
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'next', {
                            onComplete: function () {
                                self._lightboxAnimating = false;
                            }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
            }
        },

        /**
         * Known Limitation: Click-Through Detection 技巧
         *
         * 此方法使用 style.display 暫時隱藏 lightbox（而非 Alpine :class）
         *
         * 原因：
         * - elementFromPoint() 需要元素真正從 DOM 層級消失才能穿透到下方卡片
         * - Alpine :class / x-show 在檢測瞬間仍會阻擋 elementFromPoint()
         * - 執行時間極短（< 16ms），使用者無感知
         *
         * 替代方案：無（Web API 限制）
         *
         * 功能：點擊 lightbox 背景時
         * - 如果下方是圖片卡片 → click-through 切換到該影片
         * - 如果不是卡片 → 關閉 lightbox
         */
        handleLightboxBackdropClick(e) {
            // 如果點擊的是 lightbox-content 內部，不處理
            if (e.target.closest('.lightbox-content')) return;

            // 暫時隱藏 lightbox 來檢測下方元素
            const lightbox = e.currentTarget;
            lightbox.style.display = 'none';

            // 找到點擊位置下的元素
            const elementBelow = document.elementFromPoint(e.clientX, e.clientY);

            // 恢復 lightbox
            lightbox.style.display = '';

            // 檢查是否是卡片
            const cardEl = elementBelow
                ? (elementBelow.closest('.av-card-preview') || elementBelow.closest('.actress-card'))
                : null;
            if (cardEl) {
                // Click-through: 觸發該卡片的 click（切換到該影片）
                cardEl.click();
            } else {
                // 不是卡片，關閉 lightbox
                this.closeLightbox();
            }
        },

        // 工具方法：從 paginatedVideos 的 index 映射到 filteredVideos 的 index
        getCurrentFilteredIndex(paginatedIndex) {
            const perPage = parseInt(this.perPage);
            return perPage === 0 ? paginatedIndex : (this.page - 1) * perPage + paginatedIndex;
        },

        // 開啟資料夾（複製路徑到剪貼簿 + PyWebView 桌面模式額外開啟資料夾）
        openLocal(path) {
            if (!path) return;

            // 1. 擷取資料夾路徑
            const lastSlash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
            const folder = lastSlash >= 0 ? path.substring(0, lastSlash) : path;
            const displayPath = pathToDisplay(folder);

            // 2. 複製到剪貼簿
            const clipboardOk = navigator.clipboard.writeText(displayPath)
                .then(() => true)
                .catch(() => false);

            // 3. PyWebView 桌面模式：額外開啟資料夾
            if (window.pywebview?.api?.open_folder) {
                window.pywebview.api.open_folder(path)
                    .then(async (opened) => {
                        const ok = await clipboardOk;
                        if (opened) {
                            this.showToast(ok ? '已開啟資料夾（路徑已複製）' : '已開啟資料夾', 'success');
                        } else {
                            this.showToast(ok ? '已複製: ' + displayPath : '開啟資料夾失敗', ok ? 'success' : 'error');
                        }
                    })
                    .catch(async () => {
                        const ok = await clipboardOk;
                        this.showToast(ok ? '已複製: ' + displayPath : '開啟資料夾失敗', ok ? 'success' : 'error');
                    });
            } else {
                clipboardOk.then(ok => {
                    this.showToast(ok ? '已複製: ' + displayPath : '複製失敗', ok ? 'success' : 'error');
                });
            }
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

        // ==================== User Tags in Lightbox (T4) ====================

        // 展開 inline 輸入框並 focus
        showAddLbTagInput() {
            this.addingLbTag = true;
            this.newLbTagValue = '';
            this.$nextTick(() => this.$refs.lbTagInput?.focus());
        },

        // 確認新增 tag — 呼叫 POST /api/user-tags
        async confirmAddLbTag() {
            const tag = (this.newLbTagValue || '').trim();
            if (!tag) {
                this.addingLbTag = false;
                return;
            }
            if (!this.currentLightboxVideo?.path) {
                this.addingLbTag = false;
                return;
            }
            const existingTags = this.currentLightboxVideo.user_tags || [];
            if (existingTags.includes(tag)) {
                // 重複 tag，靜默忽略
                this.addingLbTag = false;
                this.newLbTagValue = '';
                return;
            }
            try {
                const resp = await fetch('/api/user-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: this.currentLightboxVideo.path,
                        add: [tag],
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success) {
                    this.currentLightboxVideo.user_tags = data.user_tags;
                } else {
                    throw new Error(data.error || 'API failed');
                }
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.tag_api_failed'), 'error');
            } finally {
                this.addingLbTag = false;
                this.newLbTagValue = '';
            }
        },

        // 取消輸入框
        cancelAddLbTag() {
            this.addingLbTag = false;
            this.newLbTagValue = '';
        },

        // 刪除 user tag — 呼叫 POST /api/user-tags {remove: [tag]}
        async removeLbUserTag(tag) {
            if (!this.currentLightboxVideo?.path) return;
            try {
                const resp = await fetch('/api/user-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: this.currentLightboxVideo.path,
                        remove: [tag],
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success) {
                    this.currentLightboxVideo.user_tags = data.user_tags;
                } else {
                    throw new Error(data.error || 'API failed');
                }
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.tag_api_failed'), 'error');
            }
        },

        // --- Enrich 補資料 (T3) ---
        async enrichVideo(video) {
            if (this._enriching) return;
            if (!video || !video.path) return;
            this._enriching = true;
            try {
                const mode = !video.has_cover ? 'refresh_full' : 'fill_missing';
                const resp = await fetch('/api/enrich-single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: video.path,
                        number: video.number,
                        mode: mode,
                        write_nfo: true,
                        write_cover: true,
                        overwrite_existing: false,
                    }),
                });
                const result = await resp.json();
                if (result.success) {
                    await this.refreshVideoData(video);
                    this.showToast(window.t('showcase.enrich.success'), 'success');
                } else {
                    this.showToast(result.error || window.t('showcase.enrich.failed'), 'error');
                }
            } catch (e) {
                this.showToast(window.t('showcase.enrich.failed'), 'error');
            } finally {
                this._enriching = false;
            }
        },

        async fetchSamples(video) {
            if (!video || !video.path || !video.number) return;
            this._fetchSamplesLoading = true;
            try {
                const res = await fetch('/api/scraper/fetch-samples', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: video.path, number: video.number })
                });
                const data = await res.json();
                if (data.success) {
                    await this.refreshVideoData(video);
                    this.showToast(window.t('showcase.samples.success'), 'success');
                } else if (data.error === 'multi_video_folder') {
                    this.showToast(window.t('showcase.samples.multi_video_error'), 'warn');
                } else {
                    this.showToast(window.t('showcase.samples.fetch_failed'), 'error');
                    this._fetchSamplesFailed[video.path] = true;
                }
            } catch (e) {
                this.showToast(window.t('showcase.samples.fetch_failed'), 'error');
                this._fetchSamplesFailed[video.path] = true;
            } finally {
                this._fetchSamplesLoading = false;
            }
        },

        async refreshVideoData(video) {
            try {
                const resp = await fetch(`/api/showcase/video?path=${encodeURIComponent(video.path)}`);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.success && data.video) {
                    if (data.video.cover_url) {
                        data.video.cover_url = data.video.cover_url + '&t=' + Date.now();
                    }
                    Object.assign(video, data.video);
                }
            } catch (e) {
                // refresh 失敗不顯示額外 toast，enrich 成功本體已顯示
            }
        },

        // Stale cover handler — 圖片載入失敗時 downgrade has_cover，
        // 觸發 Alpine reactive：enrich icon 自動出現、missing-cover class 套用、
        // 點 enrich 後自動走 refresh_full 補封面。
        handleCoverError(video, event) {
            if (!video) return;
            video.has_cover = false;  // 觸發 reactive — enrich icon 自動出現 + missing-cover class 套用
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

        // --- 49b T4cd: Actress Photo Picker methods ---
        /**
         * 開啟候選卡 picker — async，遞增 runId，啟動 SSE，淡出 metadata
         * 若已開且按 🔄：reset + 重抓
         */
        async openActressPicker() {
            const name = this.currentLightboxActress?.name;
            if (!name) return;

            // Tear down any in-flight SSE/timer before starting a new one (refresh-while-open)
            if (this._pickerSSE) { this._pickerSSE.close(); this._pickerSSE = null; }
            if (this._pickerTimeoutTimer) { clearTimeout(this._pickerTimeoutTimer); this._pickerTimeoutTimer = null; }

            if (this._pickerOpen) {
                this._resetPicker();
            }

            this._pickerOpen = true;
            this._pickerLoading = true;
            this._pickerCurrentSource = this.currentLightboxActress?.photo_source || null;

            // metadata 淡出（Row 1 actress-lb-header 保留）
            this._fadeMetadataPanel(true);

            this._pickerRunId++;
            const runId = this._pickerRunId;

            this._startPickerSSE(name, runId);
        },

        /**
         * 啟動 EventSource，處理 candidate / done / error 事件 + 3s no-event timeout
         */
        _startPickerSSE(name, runId) {
            const url = `/api/actresses/${encodeURIComponent(name)}/photo-candidates`;
            const sse = new EventSource(url);
            this._pickerSSE = sse;

            const scheduleTimeout = () => {
                clearTimeout(this._pickerTimeoutTimer);
                this._pickerTimeoutTimer = setTimeout(() => {
                    if (this._pickerRunId !== runId) return;
                    sse.close();
                    this._pickerLoading = false;
                }, 3000);
            };
            scheduleTimeout();

            sse.addEventListener('candidate', async (e) => {
                if (this._pickerRunId !== runId) { sse.close(); return; }
                try {
                    const candidate = JSON.parse(e.data);
                    // ⚠️ Race fix：必須在 push 後同步 capture myIndex，再 await。
                    // 否則 SSE 一次連發多筆（local_crop 緊接 yield）時，所有 handler 在
                    // await $nextTick 後 resume 看到的 _candidates.length 都是 N（最終值），
                    // 會全部 pick cards[N-1]，導致中間 candidate 沒有 burst（停留 opacity: 0）。
                    this._candidates = [...this._candidates, candidate];
                    const myIndex = this._candidates.length - 1;
                    await this.$nextTick();
                    if (this._pickerRunId !== runId) return;

                    const grid = this.$refs.pickerGrid;
                    if (grid && typeof window.BurstPicker !== 'undefined') {
                        const cards = grid.querySelectorAll('.picker-candidate-card');
                        const newCard = cards[myIndex];
                        if (newCard) {
                            // 用 $refs.pickerCoverImg 而非 $el.querySelector：在 @click handler 內
                            // $el 是按鈕本身、不是 component root，querySelector 會 miss → cards 留 opacity:0
                            const coverEl = this.$refs.pickerCoverImg;
                            if (coverEl) {
                                window.BurstPicker.playPickerBurst([newCard], coverEl, _PICKER_PARAMS, {
                                    streamMode: 'instant',
                                    streamInterval: 300,
                                    floatTimerSink: this._pickerFloatTweens,
                                    runId: runId,
                                    getRunId: () => this._pickerRunId
                                });
                            }
                        }
                    }
                } catch (err) {
                    console.warn('[Picker] Failed to parse candidate:', err);
                }
                scheduleTimeout();
            });

            sse.addEventListener('done', () => {
                if (this._pickerRunId !== runId) return;
                sse.close();
                this._pickerSSE = null;
                this._pickerLoading = false;
                clearTimeout(this._pickerTimeoutTimer);
            });

            sse.onerror = () => {
                if (this._pickerRunId !== runId) return;
                sse.close();
                this._pickerLoading = false;
                if (this._candidates.length === 0) {
                    this._closePicker();
                    if (typeof this.showToast === 'function') {
                        this.showToast(window.t('showcase.actress.picker.error'), 'error');
                    }
                }
            };
        },

        /**
         * Hover in：放大 + glow（settled 後才生效）
         */
        _onPickerHoverIn(el, i) {
            if (this._pickerSelected) return;
            if (typeof window.BurstPicker !== 'undefined') {
                window.BurstPicker.playPickerHoverIn(el, _PICKER_PARAMS);
            }
        },

        /**
         * Hover out：縮回原始尺寸 → 等待縮回完成後 restart float
         * Codex P2 fix：playPickerFloat 內 killTweensOf 會殺掉同步啟動的 hover-out tween，
         * 必須 await playPickerHoverOut 完成後再 startfloat，否則卡片停留在放大/glow 狀態。
         */
        async _onPickerHoverOut(el, i) {
            if (this._pickerSelected) return;
            if (typeof window.BurstPicker === 'undefined') return;
            // Capture the card so a later mutation (cancel/select clearing _candidates) can't break us
            const targetEl = el;
            await window.BurstPicker.playPickerHoverOut(targetEl, _PICKER_PARAMS);
            // Stale-check：hover-out 動畫期間若 picker 已關閉 / 已選中，不重啟 float
            if (this._pickerSelected || !this._pickerOpen) return;
            // 同樣防護：卡片可能已被 reset 從 DOM 移除
            if (!targetEl.isConnected) return;
            const tl = window.BurstPicker.playPickerFloat(targetEl, _PICKER_PARAMS);
            if (tl) this._pickerFloatTweens.push(tl);
        },

        /**
         * 選中卡片 — T4e 完整流程
         * Race lock → POST /photo → Alpine 狀態同步 → FlipReplace + ExitAll → cache-bust src 同步 → toast
         */
        async _onPickerSelect(candidate, i) {
            // AC-13 race lock：第一次 click 鎖定，其餘忽略
            if (this._pickerSelected) return;
            this._pickerSelected = true;

            // 41d captured-reference pattern：在 await 前抓快照，await 後比對偵測 lightbox 切換
            const capturedName = this.currentLightboxActress?.name;
            if (!capturedName) {
                this._pickerSelected = false;
                return;
            }

            // DOM 節點解析：必須在 await 前取得（await 後可能已被 close/重繪）
            const grid = this.$refs.pickerGrid;
            const allCards = grid ? Array.from(grid.querySelectorAll('.picker-candidate-card')) : [];
            const selectedCard = allCards[i] || null;
            const otherCards = allCards.filter((_, j) => j !== i);
            const coverImg = this.$refs.pickerCoverImg;

            // Reduced-motion 偵測（系統層 + simulator）
            const reduceMotion = (typeof window.matchMedia === 'function' &&
                                  window.matchMedia('(prefers-reduced-motion: reduce)').matches);

            try {
                const body = {
                    source: candidate.source,
                    url: candidate.full_url,
                    video_path: candidate.video_path || null,
                    crop_spec: 'v1',
                };
                const resp = await fetch(`/api/actresses/${encodeURIComponent(capturedName)}/photo`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!resp.ok) throw new Error('replace_failed_' + resp.status);
                const data = await resp.json();

                // Stale check：await 期間用戶切換了 lightbox actress
                if (!this.currentLightboxActress || this.currentLightboxActress.name !== capturedName) {
                    // 仍同步背景 _actresses 陣列，但不再動 UI / 動畫
                    this._syncActressesArray(capturedName, data);
                    this._pickerSelected = false;
                    return;
                }

                // Sync via _syncActressesArray (in-place mutation propagates to currentLightboxActress
                // since it shares the _actresses[idx] reference per line 208-209).
                this._syncActressesArray(capturedName, data);
                // Defensive: if currentLightboxActress somehow holds a different object (e.g. cache),
                // also mutate it in place to ensure :src / photo_source bindings update.
                if (this.currentLightboxActress && this.currentLightboxActress.name === capturedName) {
                    this.currentLightboxActress.photo_url = data.photo_url;
                    this.currentLightboxActress.photo_source = data.photo_source;
                }

                // Reduced-motion 或 BurstPicker 未載入 → 直接更新 src + 關閉
                if (reduceMotion || typeof window.BurstPicker === 'undefined') {
                    if (coverImg && data.photo_url) {
                        coverImg.src = data.photo_url;
                    }
                    this._closePicker();
                    this.showToast(window.t('showcase.actress.picker.replaced'), 'success');
                    return;
                }

                // 完整動畫：FlipReplace（await）→ src 同步至 backend persistent URL → ExitAll（fire-and-forget）
                try {
                    if (selectedCard && coverImg) {
                        await window.BurstPicker.playPickerFlipReplace(selectedCard, coverImg, _PICKER_PARAMS);
                        // FlipReplace 內部以 selectedImg.src 作為 ghost / 新 cover src（candidate 來源 URL）。
                        // 動畫完成後覆蓋為後端 persistent endpoint（含 ?t= cache-bust），確保刷新後 cover 仍正確。
                        if (data.photo_url) {
                            coverImg.src = data.photo_url;
                        }
                    } else if (coverImg && data.photo_url) {
                        coverImg.src = data.photo_url;
                    }
                    if (otherCards.length > 0) {
                        await window.BurstPicker.playPickerExitAll(otherCards, _PICKER_PARAMS);
                    }
                } catch (animErr) {
                    // 動畫失敗不應阻塞 success 路徑
                    console.warn('[Picker] animation error', animErr);
                    if (coverImg && data.photo_url) coverImg.src = data.photo_url;
                }

                this._closePicker();
                this.showToast(window.t('showcase.actress.picker.replaced'), 'success');

            } catch (e) {
                this._pickerSelected = false;  // 失敗時解除鎖定
                this._closePicker();
                this.showToast(window.t('showcase.actress.picker.error'), 'error');
            }
        },

        /**
         * Helper: 換照片成功後同步 _actresses 陣列對應 entry
         */
        _syncActressesArray(name, data) {
            if (!data || !data.photo_url) return;
            // 透過 this.paginatedActresses（Alpine proxy）mutation，觸發 grid card :src 重渲染。
            // 因 paginatedActresses[idx] 與 _actresses[idx]/_filteredActresses[idx] 共用 object
            // reference（line 555/607/610），proxy mutation 會同步反映到三個陣列。
            const idx = this.paginatedActresses.findIndex(a => a.name === name);
            if (idx >= 0) {
                this.paginatedActresses[idx].photo_url = data.photo_url;
                this.paginatedActresses[idx].photo_source = data.photo_source;
            }
        },

        /**
         * 關閉 picker：停止 SSE、reset 狀態、metadata 淡入
         */
        _closePicker() {
            this._pickerRunId++;   // invalidate any in-flight SSE callbacks
            if (this._pickerSSE) {
                this._pickerSSE.close();
                this._pickerSSE = null;
            }
            clearTimeout(this._pickerTimeoutTimer);
            this._pickerTimeoutTimer = null;
            this._resetPicker();
            this._fadeMetadataPanel(false);
        },

        /**
         * 取消 picker（Esc / outside-click）— 播放 reverse 動畫後關閉
         * 與 _closePicker() 區別：本方法走 motion-lab T1 reverse 視覺，封閉性更佳
         */
        async _cancelPicker() {
            if (!this._pickerOpen || this._pickerSelected) return;  // 已選中走 _closePicker；避免重入
            // Codex P2 fix：reverse 動畫期間（300ms）卡片仍可見，必須鎖住 _onPickerSelect 不被觸發
            this._pickerSelected = true;
            // 鎖住 SSE/timer 不再觸發
            this._pickerRunId++;
            if (this._pickerSSE) { this._pickerSSE.close(); this._pickerSSE = null; }
            clearTimeout(this._pickerTimeoutTimer);
            this._pickerTimeoutTimer = null;
            // 抓現有候選卡，播 reverse 動畫
            const grid = this.$refs?.pickerGrid;
            const cards = grid ? Array.from(grid.querySelectorAll('.picker-candidate-card')) : [];
            const coverImg = this.$refs.pickerCoverImg;
            if (cards.length > 0 && typeof window.BurstPicker !== 'undefined' && window.BurstPicker.playPickerReverseAll) {
                await new Promise((resolve) => {
                    window.BurstPicker.playPickerReverseAll(cards, coverImg, _PICKER_PARAMS, resolve);
                });
            }
            // 動畫完成後 reset 狀態（含解除 _pickerSelected lock）+ 淡入 metadata
            this._resetPicker();
            this._fadeMetadataPanel(false);
        },

        /**
         * 內部 reset：清空候選 + kill float tweens
         */
        _resetPicker() {
            this._pickerOpen = false;
            this._pickerLoading = false;
            this._pickerSelected = false;
            this._candidates = [];
            this._pickerCurrentSource = null;
            this._pickerFloatTweens.forEach(t => t && t.kill && t.kill());
            this._pickerFloatTweens = [];
        },

        /**
         * Metadata panel 淡出/淡入（Row 1 actress-lb-header 用 :not() 排除）
         */
        _fadeMetadataPanel(out) {
            const meta = this.$el?.querySelector?.('.actress-lightbox-meta');
            if (!meta || typeof gsap === 'undefined') return;
            const rows = meta.querySelectorAll(':scope > :not(.actress-lb-header)');
            if (rows.length === 0) return;
            OpenAver.motion.playFadeTo(rows, {
                opacity: out ? 0 : 1,
                duration: OpenAver.motion.DURATION.fast,
                ease: out ? 'fluent-accel' : 'fluent-decel'
            });
        },

        // --- 快捷鍵 (M4c 完整實作) ---
        handleKeydown(e) {
            // 1. 輸入框中不處理快捷鍵
            if (e.target.tagName === 'INPUT') return;

            // 49b T4cd: Picker 開啟時，Esc 優先關閉 picker（不冒泡到 lightbox close）
            if (e.key === 'Escape' && this._pickerOpen) {
                this._cancelPicker();
                e.preventDefault();
                e.stopPropagation();
                return;
            }

            // 2. modifier keys 停用（原版 L1667）
            if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;

            // 3. 轉大寫統一處理
            const key = e.key.toUpperCase();

            // 4. Sample Gallery 開啟時的快捷鍵（最高優先，在 lightbox 之前攔截）(T7)
            if (this.sampleGalleryOpen) {
                if (key === 'ESCAPE') {
                    e.preventDefault();
                    this.closeSampleGallery();
                } else if (key === 'ARROWLEFT') {
                    e.preventDefault();
                    this.prevSampleGallery();
                } else if (key === 'ARROWRIGHT') {
                    e.preventDefault();
                    this.nextSampleGallery();
                }
                return; // Sample Gallery 開啟時阻止其他快捷鍵（包括 lightbox 導航）
            }

            // 5. Lightbox 開啟時的快捷鍵（按 content type 分發）
            if (this.lightboxOpen) {
                if (this.currentLightboxActress && this.showFavoriteActresses) {
                    // 女優 lightbox（優先級高）
                    if (key === 'ESCAPE') {
                        e.preventDefault();
                        this.closeLightbox();
                    } else if (key === 'ARROWLEFT') {
                        e.preventDefault();
                        this.prevActressLightbox();
                    } else if (key === 'ARROWRIGHT') {
                        e.preventDefault();
                        this.nextActressLightbox();
                    }
                } else {
                    // 影片 lightbox（現有）
                    if (key === 'ESCAPE') {
                        e.preventDefault();
                        this.closeLightbox();  // closeLightbox handles kill + cleanup + generation++
                    } else if (key === 'ARROWLEFT') {
                        e.preventDefault();
                        this.prevLightboxVideo();
                    } else if (key === 'ARROWRIGHT') {
                        e.preventDefault();
                        this.nextLightboxVideo();
                    }
                }
                return; // Lightbox 開啟時阻止其他快捷鍵
            }

            // 6. 非 Lightbox 狀態的快捷鍵
            if (key === 'S' && this.mode === 'grid') {
                // S 鍵：切換 Card Info（僅 Grid 模式，已完成於 M3i）
                this.toggleInfo();
            } else if (key === 'A') {
                // A 鍵：循環切換模式 Grid → List → Table → Grid
                const modeOrder = ['grid', 'list', 'table'];
                const currentIndex = modeOrder.indexOf(this.mode);
                const nextIndex = (currentIndex + 1) % 3;
                this.switchMode(modeOrder[nextIndex]);
            } else if (key === 'ARROWLEFT') {
                // ← 鍵：上一頁（需檢查 page > 1）
                if (this.page > 1) {
                    this.prevPage();
                }
            } else if (key === 'ARROWRIGHT') {
                // → 鍵：下一頁（需檢查 page < totalPages）
                if (this.page < this.totalPages) {
                    this.nextPage();
                }
            }
        }
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('showcaseState', showcaseState);
});
