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
            const savedPage = this.page;
            await this.fetchVideos();
            this.applyFilterAndSort();  // M4a: 套用搜尋篩選（會重置 page=1）
            this.page = savedPage;      // 恢復儲存的頁碼
            this.updatePagination();    // 重新分頁（會 clamp 超出範圍的頁碼）
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
            const savedPage = this.page;
            await this.fetchVideos();
            this.applyFilterAndSort();
            this.page = savedPage;
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
            if (!['grid', 'table', 'list'].includes(m)) return;
            this.mode = m;
            this.saveState();  // M2c: 持久化狀態
        },

        // Card Info 切換 (M3i)
        toggleInfo() {
            this.infoVisible = !this.infoVisible;
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

        // Status bar 頁面跳轉 (M3g)
        goToPage(p) {
            const num = parseInt(p);
            if (Number.isNaN(num) || num < 1 || num > this.totalPages) return;
            this.page = num;
            this.updatePagination();
            this.saveState();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        },

        // --- 資料處理 (M2a 基本實作，M4 完整化) ---
        applyFilterAndSort() {
            // --- 搜尋篩選 (M4a) ---
            if (this.search && this.search.trim()) {
                // 分割多個關鍵字（用空格分隔，過濾空字串）
                const terms = this.search.toLowerCase().trim().split(/\s+/).filter(t => t.length > 0);

                this.filteredVideos = this.videos.filter(video => {
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
            } else {
                // 空搜尋：回傳全部影片
                this.filteredVideos = [...this.videos];
            }

            // --- 排序 (M4b) ---
            this.filteredVideos.sort((a, b) => {
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
            this.page = 1;
            this.updatePagination();
        },

        updatePagination() {
            const perPage = Math.max(0, parseInt(this.perPage) || 0);
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
        },

        closeLightbox() {
            this.lightboxOpen = false;
            document.body.classList.remove('overflow-hidden');
            this.lightboxIndex = -1;
            this.lightboxStartX = 0;
            this.lightboxStartY = 0;
            if (this.lightboxMoveTimer) clearTimeout(this.lightboxMoveTimer);
            this.lightboxMoveTimer = null;
            this.lightboxMoveEnabled = false;
        },

        // Metadata 點擊搜尋 (M3f)
        searchFromMetadata(term) {
            this.closeLightbox();
            this.search = term;
            this.applyFilterAndSort();
            this.saveState();
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
                    this.closeLightbox();
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
