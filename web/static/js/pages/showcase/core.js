/**
 * Showcase 核心狀態管理
 * M2a: 基本骨架 + API 載入 + Image Grid 渲染
 */

function showcaseState() {
    return {
        // --- 狀態變數 ---
        loading: true,
        error: '',           // 錯誤訊息（API 失敗時顯示）
        videos: [],           // 全部影片資料（從 API 載入）
        filteredVideos: [],   // 搜尋/排序後的結果
        paginatedVideos: [],  // 當前頁顯示的影片

        search: '',
        sort: 'date',         // M2a 先用硬編碼，M4 才從 config/localStorage 恢復
        order: 'desc',
        mode: 'grid',
        page: 1,
        perPage: 90,
        totalPages: 1,

        // --- 生命週期 ---
        async init() {
            this.restoreState();        // M2c: 先恢復狀態
            await this.fetchVideos();
            // init 時不呼叫 applyFilterAndSort()（會重置 page=1），
            // 直接設定 filteredVideos + updatePagination 保留恢復的頁碼
            this.filteredVideos = [...this.videos];
            this.updatePagination();
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
            this.perPage = parseInt(urlNum('perPage') ?? state.perPage ?? defaultPerPage);
            this.page = parseInt(urlNum('page') ?? state.page ?? 1);
            this.search = urlParams.get('search') || state.search || '';
            this.mode = urlParams.get('mode') || state.mode || 'grid';
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
                    this.videos = [];
                    this.filteredVideos = [];
                    this.error = `伺服器錯誤 (${resp.status})`;
                    return;
                }
                const data = await resp.json();
                if (!data.success) {
                    this.videos = [];
                    this.filteredVideos = [];
                    this.error = data.error || '載入失敗';
                    return;
                }
                this.videos = data.videos || [];
                this.filteredVideos = this.videos;
            } catch (e) {
                console.error('Failed to fetch videos:', e);
                this.videos = [];
                this.filteredVideos = [];
                this.error = '無法連線到伺服器';
            } finally {
                this.loading = false;
            }
        },

        // --- 重試（async 安全） ---
        async retry() {
            this.error = '';
            await this.fetchVideos();
            this.filteredVideos = [...this.videos];
            this.updatePagination();
        },

        // --- 互動邏輯 (M2a 只定義骨架，M4 才實作完整邏輯) ---
        onSearchChange() {
            // M2a 只觸發狀態更新，實際搜尋邏輯 M4 實作
            this.applyFilterAndSort();
            this.saveState();  // M2c: 持久化狀態
        },

        onSortChange() {
            this.applyFilterAndSort();
            this.saveState();  // M2c: 持久化狀態
        },

        toggleOrder() {
            this.order = this.order === 'asc' ? 'desc' : 'asc';
            this.applyFilterAndSort();
            this.saveState();  // M2c: 持久化狀態
        },

        onPerPageChange() {
            this.page = 1;
            this.updatePagination();
            this.saveState();  // M2c: 持久化狀態
        },

        switchMode(m) {
            this.mode = m;
            this.saveState();  // M2c: 持久化狀態
        },

        prevPage() {
            if (this.page > 1) {
                this.page--;
                this.updatePagination();
                this.saveState();  // M2c: 持久化狀態
            }
        },

        nextPage() {
            if (this.page < this.totalPages) {
                this.page++;
                this.updatePagination();
                this.saveState();  // M2c: 持久化狀態
            }
        },

        // --- 資料處理 (M2a 基本實作，M4 完整化) ---
        applyFilterAndSort() {
            // M2a 簡單版：只複製原始資料
            // M4 才實作搜尋關鍵字、多欄位排序等
            this.filteredVideos = [...this.videos];
            this.page = 1;
            this.updatePagination();
        },

        updatePagination() {
            const perPage = parseInt(this.perPage);
            if (perPage === 0) {
                this.paginatedVideos = this.filteredVideos;
                this.totalPages = 1;
                this.page = 1;
            } else {
                this.totalPages = Math.max(1, Math.ceil(this.filteredVideos.length / perPage));
                // clamp page 到有效範圍
                if (this.page > this.totalPages) this.page = this.totalPages;
                if (this.page < 1) this.page = 1;
                const start = (this.page - 1) * perPage;
                this.paginatedVideos = this.filteredVideos.slice(start, start + perPage);
            }
        },

        // --- 播放影片 (PyWebView 整合) ---
        playVideo(path) {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.open_file(path)
                    .catch(err => {
                        console.error('Failed to open file:', err);
                        window.open(path, '_blank');
                    });
            } else {
                window.open(path, '_blank');
            }
        },

        // --- 快捷鍵 (M2a 只定義骨架，M4 完整實作) ---
        handleKeydown(e) {
            // M2a 只處理基本按鍵，M4 才加入完整快捷鍵
            if (e.key === 'Escape') {
                // M3 Lightbox 用
            }
        }
    };
}
