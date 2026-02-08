/**
 * Showcase 核心狀態管理
 * M2a: 基本骨架 + API 載入 + Image Grid 渲染
 */

function showcaseState() {
    return {
        // --- 狀態變數 ---
        loading: true,
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
            await this.fetchVideos();
            this.applyFilterAndSort();
            this.updatePagination();
        },

        // --- API 呼叫 ---
        async fetchVideos() {
            this.loading = true;
            try {
                const resp = await fetch('/api/showcase/videos');
                const data = await resp.json();
                this.videos = data.videos || [];
                this.filteredVideos = this.videos;
            } catch (e) {
                console.error('Failed to fetch videos:', e);
            } finally {
                this.loading = false;
            }
        },

        // --- 互動邏輯 (M2a 只定義骨架，M4 才實作完整邏輯) ---
        onSearchChange() {
            // M2a 只觸發狀態更新，實際搜尋邏輯 M4 實作
            this.applyFilterAndSort();
        },

        onSortChange() {
            this.applyFilterAndSort();
        },

        toggleOrder() {
            this.order = this.order === 'asc' ? 'desc' : 'asc';
            this.applyFilterAndSort();
        },

        onPerPageChange() {
            this.page = 1;
            this.updatePagination();
        },

        switchMode(m) {
            this.mode = m;
        },

        prevPage() {
            if (this.page > 1) {
                this.page--;
                this.updatePagination();
            }
        },

        nextPage() {
            if (this.page < this.totalPages) {
                this.page++;
                this.updatePagination();
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
            } else {
                this.totalPages = Math.ceil(this.filteredVideos.length / perPage);
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
