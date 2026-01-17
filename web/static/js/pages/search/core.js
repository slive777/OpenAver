/**
 * SearchCore - 核心模組
 * 狀態管理、搜尋邏輯、翻譯功能
 */

// === 狀態變數 ===
let searchResults = [];
let currentIndex = 0;

// 分頁相關
let currentQuery = '';
let currentOffset = 0;
let hasMoreResults = false;
let isLoadingMore = false;
let isSearchingFile = false;
const PAGE_SIZE = 20;

// 多檔案列表狀態
let fileList = [];
let currentFileIndex = 0;
let listMode = null;  // 'file' | 'search' | null

// 批次搜尋狀態
let batchState = {
    batchSize: 20,        // 每批數量
    isProcessing: false,  // 是否正在處理批次
    isPaused: false,      // 是否暫停（Phase 9.4 使用）
    total: 0,             // 本批實際總數
    processed: 0,         // 本批已處理數量
    success: 0,           // 本批成功數量
    failed: 0             // 本批失敗數量
};

// 翻譯功能
let appConfig = null;
const translationCache = new Map();
let isTranslating = false;
let pendingTranslation = null;

// 🆕 追蹤正在批次翻譯的片索引
const batchTranslatingIndices = new Set();

// 狀態保存 Key
const STATE_KEY = 'javhelper_search_state';

// === DOM 引用（DOMContentLoaded 後初始化）===
let dom = {};

function initDOM() {
    dom = {
        form: document.getElementById('searchForm'),
        queryInput: document.getElementById('searchQuery'),
        emptyState: document.getElementById('emptyState'),
        loadingState: document.getElementById('loadingState'),
        resultCard: document.getElementById('resultCard'),
        errorState: document.getElementById('errorState'),
        btnPrev: document.getElementById('btnPrev'),
        btnNext: document.getElementById('btnNext'),
        navIndicator: document.getElementById('navIndicator'),
        currentIndexSpan: document.getElementById('currentIndex'),
        totalCountSpan: document.getElementById('totalCount'),
        errorNav: document.getElementById('errorNav'),
        errorBtnPrev: document.getElementById('errorBtnPrev'),
        errorBtnNext: document.getElementById('errorBtnNext'),
        errorNavIndicator: document.getElementById('errorNavIndicator'),
        btnClear: document.getElementById('btnClear'),
        fileListSection: document.getElementById('fileListSection'),
        fileListContainer: document.getElementById('fileList'),
        fileCountText: document.getElementById('fileCountText'),
        btnSearchAll: document.getElementById('btnSearchAll'),
        btnScrapeAll: document.getElementById('btnScrapeAll'),
        btnAddFiles: document.getElementById('btnAddFiles'),
        btnAddFolder: document.getElementById('btnAddFolder'),
        btnFavorite: document.getElementById('btnFavorite'),
        // 批次進度
        batchProgress: document.getElementById('batchProgress'),
        batchProgressBar: document.getElementById('batchProgressBar'),
        batchProgressText: document.getElementById('batchProgressText'),
        dragOverlay: document.getElementById('dragOverlay'),
        // 進度指示器
        progressQuery: document.getElementById('progressQuery'),
        progressLog: document.getElementById('progressLog'),
        detailProgress: document.getElementById('detailProgress'),
        detailBar: document.getElementById('detailBar'),
        detailText: document.getElementById('detailText'),
        // Gallery 相關
        galleryView: document.getElementById('galleryView'),
        galleryFrame: document.getElementById('galleryFrame'),
        btnBackToDetail: document.getElementById('btnBackToDetail')
    };
}

// === 載入應用設定 ===
async function loadAppConfig() {
    try {
        const resp = await fetch('/api/config');
        const data = await resp.json();
        if (data.success) {
            appConfig = data.data;

            // 更新我的最愛按鈕 tooltip
            if (dom.btnFavorite) {
                const favoriteFolder = appConfig?.search?.favorite_folder || '系統下載資料夾';
                dom.btnFavorite.title = `載入：${favoriteFolder}`;
            }
        }
    } catch (e) {
        console.error('載入設定失敗:', e);
    }
}

// === 翻譯功能 ===

/**
 * 判斷文字是否包含日文（平假名、片假名）
 */
function hasJapanese(text) {
    return /[\u3040-\u309F\u30A0-\u30FF]/.test(text);
}

/**
 * 調用 Ollama 翻譯/優化標題
 */
async function translateWithOllama(text, mode, metadata = {}) {
    try {
        const resp = await fetch('/api/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                mode: mode,
                actors: metadata.actors || [],
                number: metadata.number || ''
            })
        });
        return await resp.json();
    } catch (e) {
        return { success: false, error: e.message };
    }
}

/**
 * AI 翻譯按鈕點擊事件（全域函數供 onclick 調用）
 *
 * Gemini 模式：只翻譯當前片（避免 API 限制）
 * Ollama 模式：批次翻譯從當前位置開始的 10 片
 */
async function translateWithAI() {
    const btn = document.getElementById('translateBtn');
    const spinner = document.getElementById('translateSpinner');

    // 防止並發翻譯
    if (isTranslating) return;
    isTranslating = true;

    // 隱藏按鈕，顯示 spinner
    btn.classList.add('d-none');
    spinner.classList.remove('d-none');

    try {
        // === Gemini 模式：只翻譯當前片 ===
        if (appConfig?.translate?.provider === 'gemini') {
            let currentResult = null;

            if (listMode === 'file' && fileList[currentFileIndex]) {
                const results = fileList[currentFileIndex].searchResults || [];
                currentResult = results[currentIndex];
            } else {
                currentResult = searchResults[currentIndex];
            }

            if (!currentResult || !currentResult.title || !hasJapanese(currentResult.title)) {
                throw new Error('當前片無需翻譯');
            }

            console.log(`[Gemini] 單片翻譯: ${currentResult.title}`);

            // 調用單片翻譯 API
            const result = await translateWithOllama(currentResult.title, 'translate', currentResult);

            if (result.success && result.result) {
                // 更新翻譯結果
                if (listMode === 'file') {
                    fileList[currentFileIndex].searchResults[currentIndex].translated_title = result.result;
                } else {
                    searchResults[currentIndex].translated_title = result.result;
                }
                window.SearchUI.updateTranslatedTitle(result.result);
                console.log(`[Gemini] 翻譯完成: ${result.result}`);
                saveState();
            } else {
                throw new Error(result.error || '翻譯失敗');
            }

            return;  // Gemini 模式結束
        }

        // === Ollama 模式：批次翻譯 10 片 ===
        const batch = [];
        const batchMeta = [];

        if (listMode === 'file') {
            for (let fi = currentFileIndex; fi < fileList.length && batch.length < 10; fi++) {
                const file = fileList[fi];
                const results = file.searchResults || [];

                for (let ri = 0; ri < results.length && batch.length < 10; ri++) {
                    const result = results[ri];
                    if (result.title && hasJapanese(result.title) && !result.translated_title) {
                        batch.push(result);
                        batchMeta.push({ fileIndex: fi, resultIndex: ri });
                    }
                }
            }
        } else {
            for (let i = currentIndex; i < searchResults.length && batch.length < 10; i++) {
                const result = searchResults[i];
                if (result.title && hasJapanese(result.title) && !result.translated_title) {
                    batch.push(result);
                    batchMeta.push({ resultIndex: i });
                }
            }
        }

        if (batch.length === 0) {
            throw new Error('無需翻譯的日文標題');
        }

        console.log(`[Ollama Batch] 批次翻譯 ${batch.length} 片`);

        if (listMode !== 'file') {
            batchMeta.forEach(meta => {
                batchTranslatingIndices.add(meta.resultIndex);
            });
        }

        const titles = batch.map(r => r.title);
        const translations = await translateBatch(titles);

        if (translations && translations.length > 0) {
            translations.forEach((trans, i) => {
                if (!trans) return;
                const meta = batchMeta[i];

                if (listMode === 'file') {
                    fileList[meta.fileIndex].searchResults[meta.resultIndex].translated_title = trans;
                    if (meta.fileIndex === currentFileIndex && meta.resultIndex === currentIndex) {
                        window.SearchUI.updateTranslatedTitle(trans);
                    }
                } else {
                    searchResults[meta.resultIndex].translated_title = trans;
                    batchTranslatingIndices.delete(meta.resultIndex);
                    if (meta.resultIndex === currentIndex) {
                        window.SearchUI.updateTranslatedTitle(trans);
                    }
                }
            });

            console.log(`[Ollama Batch] 完成 ${translations.filter(t => t).length} 片翻譯`);
            saveState();
        }

        if (listMode !== 'file') {
            batchMeta.forEach(meta => {
                batchTranslatingIndices.delete(meta.resultIndex);
            });
        }

    } catch (error) {
        console.error('[Translate] 翻譯失敗:', error);
        alert('翻譯失敗：' + error.message);
    } finally {
        isTranslating = false;
        spinner.classList.add('d-none');

        let currentResult = null;
        if (listMode === 'file' && fileList[currentFileIndex]) {
            const results = fileList[currentFileIndex].searchResults || [];
            currentResult = results[currentIndex];
        } else {
            currentResult = searchResults[currentIndex];
        }

        if (currentResult && currentResult.title &&
            hasJapanese(currentResult.title) &&
            !currentResult.translated_title) {
            btn.classList.remove('d-none');
        }
    }
}

// === 狀態保存/還原 ===

function saveState() {
    const state = {
        searchResults,
        currentIndex,
        currentQuery,
        currentOffset,
        hasMoreResults,
        fileList,
        currentFileIndex,
        listMode,
        queryValue: dom.queryInput ? dom.queryInput.value : ''
    };
    sessionStorage.setItem(STATE_KEY, JSON.stringify(state));
}

function restoreState() {
    const saved = sessionStorage.getItem(STATE_KEY);
    if (!saved) return false;

    try {
        const state = JSON.parse(saved);
        searchResults = state.searchResults || [];
        currentIndex = state.currentIndex || 0;
        currentQuery = state.currentQuery || '';
        currentOffset = state.currentOffset || 0;
        hasMoreResults = state.hasMoreResults || false;
        fileList = state.fileList || [];
        currentFileIndex = state.currentFileIndex || 0;
        listMode = state.listMode || null;
        if (dom.queryInput) {
            dom.queryInput.value = state.queryValue || '';
        }

        // 有內容才還原顯示
        if (searchResults.length > 0) {
            window.SearchUI.displayResult(searchResults[currentIndex]);
            window.SearchUI.updateNavigation();
            window.SearchUI.showState('result');

            if (listMode === 'search') {
                window.SearchFile.renderSearchResultsList();
            } else if (listMode === 'file') {
                window.SearchFile.renderFileList();
            }
            updateClearButton();
            return true;
        } else if (fileList.length > 0 && listMode === 'file') {
            window.SearchFile.renderFileList();
            updateClearButton();
            const currentFile = fileList[currentFileIndex];
            if (currentFile && currentFile.searchResults && currentFile.searchResults.length > 0) {
                searchResults = currentFile.searchResults;
                hasMoreResults = currentFile.hasMoreResults || false;
                window.SearchUI.displayResult(searchResults[currentIndex]);
                window.SearchUI.updateNavigation();
                window.SearchUI.showState('result');
                return true;
            }
        }
    } catch (e) {
        console.error('還原狀態失敗:', e);
        sessionStorage.removeItem(STATE_KEY);
    }
    return false;
}

function clearState() {
    sessionStorage.removeItem(STATE_KEY);
}

function clearAll() {
    // 先關閉 Gallery（如果有顯示）- 不自動顯示詳細資料卡
    if (window.SearchUI.hideGallery) {
        const galleryView = dom.galleryView;
        if (galleryView && !galleryView.classList.contains('d-none')) {
            window.SearchUI.hideGallery(false);
        }
    }

    searchResults = [];
    currentIndex = 0;
    currentQuery = '';
    currentOffset = 0;
    hasMoreResults = false;
    fileList = [];
    currentFileIndex = 0;
    listMode = null;
    if (dom.queryInput) dom.queryInput.value = '';
    isSearchingFile = false;

    // 確保導航按鈕圖示正確
    if (dom.btnPrev) dom.btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
    if (dom.btnNext) dom.btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';

    window.SearchUI.showState('empty');
    if (dom.fileListSection) dom.fileListSection.classList.add('d-none');
    updateClearButton();
    clearState();
}

function updateClearButton() {
    const hasContent = searchResults.length > 0 || fileList.length > 0;
    if (dom.btnClear) {
        dom.btnClear.classList.toggle('d-none', !hasContent);
    }
}

// === 進度指示器 ===

const MODE_TEXT = {
    'exact': '完整番號搜尋',
    'partial': '部分番號搜尋',
    'prefix': '系列搜尋',
    'actress': '女優搜尋',
    'keyword': '全文搜尋'
};

let currentMode = '';

function initProgress(query) {
    if (dom.progressQuery) dom.progressQuery.textContent = `"${query}"`;
    if (dom.progressLog) dom.progressLog.textContent = '搜尋中...';
    if (dom.detailProgress) dom.detailProgress.classList.remove('show');
}

function updateLog(text) {
    if (dom.progressLog) dom.progressLog.textContent = text;
}

function updateDetailProgress(done, total) {
    if (total > 0 && dom.detailProgress) {
        dom.detailProgress.classList.add('show');
        const percent = Math.round((done / total) * 100);
        if (dom.detailBar) dom.detailBar.style.width = `${percent}%`;
        if (dom.detailText) dom.detailText.textContent = `${done} / ${total}`;
    }
}

function handleSearchStatus(source, status) {
    if (source === 'mode') {
        currentMode = status;
        updateLog(`${MODE_TEXT[status] || status}...`);
        return;
    }

    if (source === 'javbus' || source === 'jav321') {
        if (status === 'searching') {
            updateLog(`${MODE_TEXT[currentMode] || '搜尋'}...`);
        }
        else if (status.startsWith('found:')) {
            const count = status.split(':')[1];
            if (count === '0') {
                updateLog(`${MODE_TEXT[currentMode] || '搜尋'}：無結果`);
            } else {
                updateLog(`${MODE_TEXT[currentMode] || '搜尋'}：找到 ${count} 筆`);
            }
        }
        else if (status === 'fetching_details') {
            updateLog('抓取詳情...');
        }
        else if (status.startsWith('details:')) {
            const parts = status.split(':')[1].split('/');
            if (parts.length === 2) {
                const done = parseInt(parts[0]);
                const total = parseInt(parts[1]);
                updateLog(`抓取詳情 ${done}/${total}`);
                updateDetailProgress(done, total);
            }
        }
        else if (status === 'failed') {
            updateLog(`${MODE_TEXT[currentMode] || '搜尋'}：失敗`);
        }
    }
}

// === 搜尋邏輯 ===

/**
 * 執行搜尋（SSE 串流）
 */
function doSearch(query) {
    if (!query) return;

    // 先關閉現有的 Gallery（如果有顯示）
    if (window.SearchUI.hideGallery) {
        const galleryView = dom.galleryView;
        if (galleryView && !galleryView.classList.contains('d-none')) {
            window.SearchUI.hideGallery(false);
        }
    }

    window.SearchUI.showState('loading');
    initProgress(query);
    searchResults = [];
    currentIndex = 0;

    // 清空多檔案列表
    fileList = [];
    currentFileIndex = 0;
    listMode = null;
    if (dom.fileListSection) dom.fileListSection.classList.add('d-none');

    // 重設分頁狀態
    currentQuery = query;
    currentOffset = 0;
    hasMoreResults = false;

    const eventSource = new EventSource(`/api/search/stream?q=${encodeURIComponent(query)}`);

    eventSource.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'mode') {
                currentMode = data.mode;
                updateLog(`${MODE_TEXT[data.mode] || '搜尋'}...`);
            }
            else if (data.type === 'status') {
                handleSearchStatus(data.source, data.status);
            }
            else if (data.type === 'result') {
                eventSource.close();

                if (data.success && data.data && data.data.length > 0) {
                    searchResults = data.data;
                    currentIndex = 0;
                    hasMoreResults = data.has_more || false;

                    // 優先顯示 Gallery（如果有 gallery_url）
                    if (data.gallery_url) {
                        window.SearchUI.showGallery(data.gallery_url);
                        listMode = 'search';
                        window.SearchFile.renderSearchResultsList();
                        updateClearButton();
                        window.SearchCore.saveState();
                    } else {
                        // 原有的詳細資料卡顯示邏輯
                        window.SearchUI.displayResult(searchResults[0]);
                        window.SearchUI.updateNavigation();
                        window.SearchUI.showState('result');
                        window.SearchUI.preloadImages(1, 5);
                        listMode = 'search';
                        window.SearchFile.renderSearchResultsList();
                        updateClearButton();
                    }
                } else {
                    document.getElementById('errorMessage').textContent = '找不到資料';
                    window.SearchUI.showState('error');
                }
            }
            else if (data.type === 'error') {
                eventSource.close();
                document.getElementById('errorMessage').textContent = data.message || '搜尋失敗';
                window.SearchUI.showState('error');
            }
        } catch (err) {
            console.error('Parse error:', err);
        }
    };

    eventSource.onerror = function () {
        eventSource.close();
        fallbackSearch(query);
    };
}

/**
 * 傳統 API 回退
 */
async function fallbackSearch(query) {
    // 先關閉現有的 Gallery（如果有顯示）
    if (window.SearchUI.hideGallery) {
        const galleryView = dom.galleryView;
        if (galleryView && !galleryView.classList.contains('d-none')) {
            window.SearchUI.hideGallery(false);
        }
    }

    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (response.ok && data.success && data.data && data.data.length > 0) {
            searchResults = data.data;
            currentIndex = 0;
            hasMoreResults = data.has_more || false;

            // 優先顯示 Gallery（如果有 gallery_url）
            if (data.gallery_url) {
                window.SearchUI.showGallery(data.gallery_url);
                listMode = 'search';
                window.SearchFile.renderSearchResultsList();
                updateClearButton();
                window.SearchCore.saveState();
            } else {
                // 原有的詳細資料卡顯示邏輯
                window.SearchUI.displayResult(searchResults[0]);
                window.SearchUI.updateNavigation();
                window.SearchUI.showState('result');
                window.SearchUI.preloadImages(1, 5);
                listMode = 'search';
                window.SearchFile.renderSearchResultsList();
                updateClearButton();
            }
        } else {
            document.getElementById('errorMessage').textContent = data.error || '找不到資料';
            window.SearchUI.showState('error');
        }
    } catch (err) {
        document.getElementById('errorMessage').textContent = '網路錯誤: ' + err.message;
        window.SearchUI.showState('error');
    }
}

// === 翻譯功能 ===

/**
 * 批次翻譯（調用 /api/translate-batch）
 *
 * @param {Array<string>} titles - 日文標題列表
 * @returns {Promise<Array<string>>} 繁體中文翻譯列表
 */
async function translateBatch(titles) {
    try {
        const resp = await fetch('/api/translate-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                titles: titles,
                batch_size: 10
            })
        });

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }

        const data = await resp.json();
        return data.translations || [];

    } catch (error) {
        console.error('[Progressive] 批次翻譯失敗:', error);
        return [];
    }
}

// === 暴露介面 ===
window.SearchCore = {
    // 狀態（供其他模組讀寫）
    get state() {
        return {
            get searchResults() { return searchResults; },
            set searchResults(v) { searchResults = v; },
            get currentIndex() { return currentIndex; },
            set currentIndex(v) { currentIndex = v; },
            get currentQuery() { return currentQuery; },
            set currentQuery(v) { currentQuery = v; },
            get currentOffset() { return currentOffset; },
            set currentOffset(v) { currentOffset = v; },
            get hasMoreResults() { return hasMoreResults; },
            set hasMoreResults(v) { hasMoreResults = v; },
            get isLoadingMore() { return isLoadingMore; },
            set isLoadingMore(v) { isLoadingMore = v; },
            get isSearchingFile() { return isSearchingFile; },
            set isSearchingFile(v) { isSearchingFile = v; },
            get fileList() { return fileList; },
            set fileList(v) { fileList = v; },
            get currentFileIndex() { return currentFileIndex; },
            set currentFileIndex(v) { currentFileIndex = v; },
            get listMode() { return listMode; },
            set listMode(v) { listMode = v; },
            get appConfig() { return appConfig; },
            get isTranslating() { return isTranslating; },
            set isTranslating(v) { isTranslating = v; },
            get translationCache() { return translationCache; },
            get currentMode() { return currentMode; },
            set currentMode(v) { currentMode = v; },
            get batchState() { return batchState; },
            set batchState(v) { batchState = v; },
            PAGE_SIZE
        };
    },
    // DOM 引用
    get dom() { return dom; },
    // 初始化
    initDOM,
    // 函數
    loadAppConfig,
    saveState,
    restoreState,
    clearState,
    clearAll,
    updateClearButton,
    initProgress,
    updateLog,
    updateDetailProgress,
    handleSearchStatus,
    doSearch,
    fallbackSearch,
    hasJapanese,
    translateWithOllama,
    translateWithAI,
    translateBatch,
    // 檢查是否正在批次翻譯
    isBatchTranslating: (index) => batchTranslatingIndices.has(index),
    MODE_TEXT
};

// 全域函數（onclick 用）
window.translateWithAI = translateWithAI;
