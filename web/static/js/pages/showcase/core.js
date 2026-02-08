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

        // Lightbox 狀態 (M3a)
        lightboxOpen: false,
        lightboxIndex: -1,              // 指向 filteredVideos 的索引
        lightboxMoveEnabled: false,     // Smart Close: 延遲啟用
        lightboxMoveTimer: null,
        lightboxStartX: 0,
        lightboxStartY: 0,

        search: '',
        sort: 'date',         // M2a 先用硬編碼，M4 才從 config/localStorage 恢復
        order: 'desc',
        mode: 'grid',
        page: 1,
        perPage: 90,
        totalPages: 1,

        // --- Computed ---
        get currentLightboxVideo() {
            if (this.lightboxIndex >= 0 && this.lightboxIndex < this.filteredVideos.length) {
                return this.filteredVideos[this.lightboxIndex];
            }
            return null;
        },

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

        sortBy(field) {
            if (this.sort === field) {
                this.toggleOrder();  // 同欄位 → 切換方向
            } else {
                this.sort = field;
                this.onSortChange(); // 不同欄位 → 切換排序欄位
            }
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

        // --- Lightbox (M3a) ---
        openLightbox(index) {
            this.lightboxIndex = index;
            this.lightboxOpen = true;
            document.body.style.overflow = 'hidden';

            // Smart Close: 延遲 1000ms 後才啟用滑鼠關閉
            this.lightboxMoveEnabled = false;
            if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
            this.lightboxMoveTimer = setTimeout(() => {
                this.lightboxMoveEnabled = true;
            }, 1000);

            // 重置起始位置
            this.lightboxStartX = 0;
            this.lightboxStartY = 0;
        },

        closeLightbox() {
            this.lightboxOpen = false;
            document.body.style.overflow = '';
            this.lightboxIndex = -1;
            this.lightboxStartX = 0;
            this.lightboxStartY = 0;
        },

        prevLightboxVideo() {
            if (this.lightboxIndex > 0) {
                this.lightboxIndex--;
                // 重置 Smart Close 狀態
                this.lightboxMoveEnabled = false;
                if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
                this.lightboxMoveTimer = setTimeout(() => {
                    this.lightboxMoveEnabled = true;
                }, 1000);
                this.lightboxStartX = 0;
                this.lightboxStartY = 0;
            }
        },

        nextLightboxVideo() {
            if (this.lightboxIndex < this.filteredVideos.length - 1) {
                this.lightboxIndex++;
                // 重置 Smart Close 狀態
                this.lightboxMoveEnabled = false;
                if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
                this.lightboxMoveTimer = setTimeout(() => {
                    this.lightboxMoveEnabled = true;
                }, 1000);
                this.lightboxStartX = 0;
                this.lightboxStartY = 0;
            }
        },

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

        // 複製路徑到剪貼簿
        async copyPath(path) {
            if (!path) return;
            try {
                await navigator.clipboard.writeText(path);
                // TODO: M5 Toast 通知「已複製路徑」
                console.log('Path copied:', path);
            } catch (err) {
                console.error('Failed to copy path:', err);
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

        // --- 快捷鍵 (M2a 只定義骨架，M4 完整實作) ---
        handleKeydown(e) {
            // 輸入框中不處理快捷鍵
            if (e.target.tagName === 'INPUT') return;

            // Lightbox 開啟時的快捷鍵
            if (this.lightboxOpen) {
                if (e.key === 'Escape') {
                    this.closeLightbox();
                } else if (e.key === 'ArrowLeft') {
                    this.prevLightboxVideo();
                } else if (e.key === 'ArrowRight') {
                    this.nextLightboxVideo();
                }
                return;
            }

            // TODO: M4 才加入頁面級快捷鍵（模式切換、翻頁等）
        }
    };
}
