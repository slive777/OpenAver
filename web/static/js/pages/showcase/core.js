/**
 * Showcase 核心狀態管理
 * M2a: 基本骨架 + API 載入 + Image Grid 渲染
 */

// F1: 大陣列移出 Alpine reactive scope — Alpine 不追蹤
var _videos = [];
var _filteredVideos = [];

function showcaseState() {
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
        lightboxMoveEnabled: false,     // Smart Close: 延遲啟用
        lightboxMoveTimer: null,
        lightboxStartX: 0,
        lightboxStartY: 0,

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

        currentLightboxVideo: null,

        // F1: helper — 更新 lightboxIndex + currentLightboxVideo 一致性
        _setLightboxIndex(idx) {
            this.lightboxIndex = idx;
            this.currentLightboxVideo = (idx >= 0 && idx < _filteredVideos.length)
                ? _filteredVideos[idx] : null;
        },

        // --- 生命週期 ---
        async init() {
            // 接入 page lifecycle：清理 lightbox timer 和 body class
            if (window.__registerPage) {
                window.__registerPage({
                    cleanup: () => {
                        this._animGeneration++;       // B13: 使 pending deferred callback 失效
                        this._lightboxGeneration++;   // B19: invalidate pending $nextTick lightbox callbacks
                        if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
                        if (this.toastTimer) clearTimeout(this.toastTimer);
                        if (this.lightboxOpen) document.body.classList.remove('overflow-hidden');
                    }
                });
            }

            this.restoreState();        // M2c: 先恢復狀態
            const savedPage = this.page;
            await this.fetchVideos();
            this.applyFilterAndSort(true);  // M4a: 套用搜尋篩選（跳過 pagination，下面統一處理）
            this.page = savedPage;          // 恢復儲存的頁碼
            this.updatePagination();        // 單次分頁（會 clamp 超出範圍的頁碼）

            // Settle: 初次載入用 settle（不碰 opacity → 不閃）
            if (this.mode === 'grid') {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;  // stale
                    var grid = document.querySelector('.showcase-grid');
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
                    var grid = document.querySelector('.showcase-grid');
                    window.ShowcaseAnimations?.playSettle?.(grid);
                }); });
            }
        },

        // --- 互動邏輯 (M2a 只定義骨架，M4 才實作完整邏輯) ---
        onSearchChange() {
            // B8: 透過 _animateFilter 觸發篩選動畫
            this._animateFilter();
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

        /**
         * B7/B15: 排序動畫共用 helper — flip-guard → capture → change → Flip reorder
         * @param {Function} changeFn - 執行 data change 的函數
         */
        _sortWithFlip(changeFn) {
            var savedPage = this.page;
            var grid = null;
            var positionMap = null;

            // Step 0: capture（僅 grid mode）
            if (this.mode === 'grid') {
                grid = document.querySelector('.showcase-grid');
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
                grid = document.querySelector('.showcase-grid');
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
                        video.path
                    ].filter(Boolean).join(' ').toLowerCase();

                    // 番號的正規化版本（移除空格和連字號）
                    const numNorm = video.number ? video.number.toLowerCase().replace(/[\s\-]/g, '') : '';

                    // 每個關鍵字都要匹配（AND 邏輯）
                    return terms.every(term => {
                        const termNorm = term.replace(/[\s\-]/g, '');
                        // 番號模糊匹配 OR 一般欄位匹配
                        return (numNorm && numNorm.includes(termNorm)) || searchable.includes(term);
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
            // B16: 動畫進行中 guard
            if (this._lightboxAnimating) return;
            if (this.lightboxOpen && this.lightboxIndex === index) return;  // 同一張，不動作

            // Fix: lightbox 已開啟時走 switch 路徑（避免 backdrop click-through 重播 open 動畫）
            if (this.lightboxOpen && this.lightboxIndex !== index) {
                var self = this;
                // C18: interrupt — kill 舊 switch timeline（含 onComplete callback）
                if (typeof gsap !== 'undefined') {
                    gsap.getById('showcaseLightboxSwitch')?.kill();
                }
                var oldIndex = this.lightboxIndex;
                var direction = index > oldIndex ? 'next' : 'prev';

                // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
                this._setLightboxIndex(index);

                // Smart Close 重置
                this.lightboxMoveEnabled = false;
                if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
                this.lightboxMoveTimer = setTimeout(function () {
                    self.lightboxMoveEnabled = true;
                }, 1000);
                this.lightboxStartX = 0;
                this.lightboxStartY = 0;

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

            this._setLightboxIndex(index);
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');

            // Smart Close: 延遲 1000ms 後才啟用滑鼠關閉
            this.lightboxMoveEnabled = false;
            if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
            this.lightboxMoveTimer = setTimeout(() => {
                this.lightboxMoveEnabled = true;
            }, 1000);

            // 重置起始位置
            this.lightboxStartX = 0;
            this.lightboxStartY = 0;

            // B16: GSAP 進場動畫（fire-and-forget）
            var self = this;
            var lbGen = ++this._lightboxGeneration;
            this.$nextTick(() => {
                if (self._lightboxGeneration !== lbGen) return;  // B19: stale
                var lightboxEl = document.querySelector('.showcase-lightbox');
                if (!lightboxEl) return;
                self._lightboxAnimating = true;
                var tl = window.ShowcaseAnimations?.playLightboxOpen?.(lightboxEl, {
                    onComplete: function () {
                        self._lightboxAnimating = false;
                    }
                });
                if (!tl) {
                    self._lightboxAnimating = false;
                }
            });
        },

        closeLightbox() {
            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            // Instant close — kill any in-progress lightbox animations, then sync cleanup
            if (typeof gsap !== 'undefined') {
                gsap.getById('showcaseLightboxOpen')?.kill();
                gsap.getById('showcaseLightboxSwitch')?.kill();
            }
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');
            this._lightboxAnimating = false;
            this.lightboxOpen = false;
            this._setLightboxIndex(-1);
            document.body.classList.remove('overflow-hidden');
            if (this.lightboxMoveTimer) {
                clearTimeout(this.lightboxMoveTimer);
                this.lightboxMoveTimer = null;
            }
            this.lightboxMoveEnabled = false;
            this.lightboxStartX = 0;
            this.lightboxStartY = 0;
        },

        // Metadata 點擊搜尋 (M3f)
        searchFromMetadata(term) {
            // 同步關閉 lightbox（跳過動畫，後面馬上做 filter 動畫）
            if (typeof gsap !== 'undefined') {
                gsap.getById('showcaseLightboxOpen')?.kill();
                gsap.getById('showcaseLightboxSwitch')?.kill();
            }
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.remove('gsap-animating');
            this._lightboxAnimating = false;
            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            this.lightboxOpen = false;
            this._setLightboxIndex(-1);
            document.body.classList.remove('overflow-hidden');
            if (this.lightboxMoveTimer) {
                clearTimeout(this.lightboxMoveTimer);
                this.lightboxMoveTimer = null;
            }
            this.lightboxMoveEnabled = false;
            this.lightboxStartX = 0;
            this.lightboxStartY = 0;

            this.search = term;
            this._animateFilter();
        },

        prevLightboxVideo() {
            // C18: interrupt — kill open + switch timeline（進場動畫未完也要打斷）
            if (typeof gsap !== 'undefined') {
                gsap.getById('showcaseLightboxOpen')?.kill();
                gsap.getById('showcaseLightboxSwitch')?.kill();
            }
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            if (this.lightboxIndex > 0) {
                var self = this;
                var newIdx = this.lightboxIndex - 1;

                // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
                this._setLightboxIndex(newIdx);

                /** Smart Close 重置邏輯 */
                function resetSmartClose() {
                    self.lightboxMoveEnabled = false;
                    if (self.lightboxMoveTimer) clearTimeout(self.lightboxMoveTimer);
                    self.lightboxMoveTimer = setTimeout(function () {
                        self.lightboxMoveEnabled = true;
                    }, 1000);
                    self.lightboxStartX = 0;
                    self.lightboxStartY = 0;
                }
                resetSmartClose();

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
            if (typeof gsap !== 'undefined') {
                gsap.getById('showcaseLightboxOpen')?.kill();
                gsap.getById('showcaseLightboxSwitch')?.kill();
            }
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            if (this.lightboxIndex < _filteredVideos.length - 1) {
                var self = this;
                var newIdx = this.lightboxIndex + 1;

                // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
                this._setLightboxIndex(newIdx);

                /** Smart Close 重置邏輯 */
                function resetSmartClose() {
                    self.lightboxMoveEnabled = false;
                    if (self.lightboxMoveTimer) clearTimeout(self.lightboxMoveTimer);
                    self.lightboxMoveTimer = setTimeout(function () {
                        self.lightboxMoveEnabled = true;
                    }, 1000);
                    self.lightboxStartX = 0;
                    self.lightboxStartY = 0;
                }
                resetSmartClose();

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
            // Smart Close: 只有點擊到 backdrop 且已啟用時才處理
            if (!this.lightboxMoveEnabled) return;

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
            const cardEl = elementBelow ? elementBelow.closest('.av-card-preview') : null;
            if (cardEl) {
                // Click-through: 觸發該卡片的 click（切換到該影片）
                cardEl.click();
            } else {
                // 不是卡片，關閉 lightbox
                this.closeLightbox();
            }
        },

        // Smart Close: 滑鼠移動距離檢測
        handleLightboxMousemove(e) {
            if (!this.lightboxOpen) return;
            if (!this.lightboxMoveEnabled) return;

            // 如果滑鼠在 .lightbox-content 或 nav 按鈕上，不關閉
            if (e.target.closest('.lightbox-content') || e.target.closest('.lightbox-nav')) return;

            // 記錄起始位置（第一次離開內容區）
            if (this.lightboxStartX === 0 && this.lightboxStartY === 0) {
                this.lightboxStartX = e.clientX;
                this.lightboxStartY = e.clientY;
                return;
            }

            // 檢查移動距離，需超過 200px 才關閉
            const dist = Math.sqrt(
                Math.pow(e.clientX - this.lightboxStartX, 2) +
                Math.pow(e.clientY - this.lightboxStartY, 2)
            );
            if (dist < 200) return;

            // 滑鼠在背景區域移動超過 200px，關閉 Lightbox
            this.closeLightbox();
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
            if (!bytes || bytes === 0) return '未知';
            const gb = bytes / (1024 * 1024 * 1024);
            if (gb >= 1) {
                return `${gb.toFixed(2)} GB`;
            }
            const mb = bytes / (1024 * 1024);
            return `${mb.toFixed(2)} MB`;
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

        // --- 快捷鍵 (M4c 完整實作) ---
        handleKeydown(e) {
            // 1. 輸入框中不處理快捷鍵
            if (e.target.tagName === 'INPUT') return;

            // 2. modifier keys 停用（原版 L1667）
            if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;

            // 3. 轉大寫統一處理
            const key = e.key.toUpperCase();

            // 4. Lightbox 開啟時的快捷鍵（優先處理）
            if (this.lightboxOpen) {
                if (key === 'ESCAPE') {
                    this.closeLightbox();  // closeLightbox handles kill + cleanup + generation++
                } else if (key === 'ARROWLEFT') {
                    this.prevLightboxVideo();
                } else if (key === 'ARROWRIGHT') {
                    this.nextLightboxVideo();
                }
                return; // Lightbox 開啟時阻止其他快捷鍵
            }

            // 5. 非 Lightbox 狀態的快捷鍵
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
