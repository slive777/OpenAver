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
let isTranslating = false;

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
 * [FRONTEND UTIL] 翻譯功能的即時判斷，必須保留在前端
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
 * T1c: Internal translate function (called by Alpine wrapper)
 *
 * Gemini 模式：只翻譯當前片（避免 API 限制）
 * Ollama 模式：批次翻譯從當前位置開始的 10 片
 *
 * NOTE: isTranslating state is managed by Alpine wrapper in state.js
 */
async function _translateWithAI() {
    // T1c: isTranslating now managed by Alpine wrapper
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
                // T1c: Alpine reactive will update UI automatically
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
            for (let fi = currentFileIndex; fi < fileList.length && batch.length < 1; fi++) {
                const file = fileList[fi];
                const results = file.searchResults || [];

                for (let ri = 0; ri < results.length && batch.length < 1; ri++) {
                    const result = results[ri];
                    if (result.title && hasJapanese(result.title) && !result.translated_title) {
                        batch.push(result);
                        batchMeta.push({ fileIndex: fi, resultIndex: ri });
                    }
                }
            }
        } else {
            for (let i = currentIndex; i < searchResults.length && batch.length < 1; i++) {
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
                    // T1c: Alpine reactive will update UI automatically
                } else {
                    searchResults[meta.resultIndex].translated_title = trans;
                    batchTranslatingIndices.delete(meta.resultIndex);
                    // T1c: Alpine reactive will update UI automatically
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
        // T1c: Re-throw for Alpine wrapper to handle
        throw error;
    } finally {
        // T1c: isTranslating cleanup handled by Alpine wrapper
        // T1c: UI updates handled by Alpine reactive
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
        if (galleryView && !galleryView.classList.contains('hidden')) {
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
    if (dom.fileListSection) dom.fileListSection.classList.add('hidden');
    updateClearButton();
    clearState();
}

function updateClearButton() {
    const hasContent = searchResults.length > 0 || fileList.length > 0;
    if (dom.btnClear) {
        dom.btnClear.classList.toggle('hidden', !hasContent);
    }
    // T1a: 同步 Alpine hasContent
    const el = document.querySelector('.search-container[x-data]');
    if (el && el._x_dataStack) {
        Alpine.$data(el).hasContent = hasContent;
    }
}

// === 進度指示器 ===
// T1b: initProgress, updateLog, updateDetailProgress, handleSearchStatus 已遷移到 Alpine state.js

const MODE_TEXT = {
    'exact': '完整番號搜尋',
    'partial': '部分番號搜尋',
    'prefix': '系列搜尋',
    'actress': '模糊搜尋',
    'keyword': '全文搜尋',
    'uncensored': '無碼搜尋'
};

let currentMode = '';

// === 搜尋邏輯 ===
// T1b: doSearch, fallbackSearch 已遷移到 Alpine state.js
// 保留 module-level vars 供舊 JS 讀取

// === 本地狀態查詢 ===

/**
 * 查詢搜尋結果在本地庫的存在狀態
 * @param {Array} results - 搜尋結果陣列
 */
async function checkLocalStatus(results) {
    // 收集所有有效番號
    const numbers = results
        .map(r => r.number)
        .filter(n => n)
        .join(',');

    if (!numbers) return;

    try {
        const resp = await fetch(`/api/search/local-status?numbers=${encodeURIComponent(numbers)}`);
        if (!resp.ok) {
            console.warn('[LocalStatus] API 請求失敗:', resp.status);
            return;
        }

        const data = await resp.json();

        // 更新搜尋結果的本地狀態
        results.forEach(result => {
            if (result.number) {
                // 嘗試原始大小寫和大寫
                result._localStatus = data[result.number] || data[result.number?.toUpperCase()];
            }
        });

        // 更新 UI
        window.SearchUI.updateLocalBadges();

    } catch (err) {
        console.error('[LocalStatus] 查詢失敗:', err);
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
                batch_size: 1
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
    // T1b: 這些函數已遷移到 Alpine，保留 bridge 指向（在 state.js setupBridgeLayer() 設定）
    doSearch: null,
    initProgress: null,      // bridge 在 state.js 設定
    updateLog: null,         // bridge 在 state.js 設定
    handleSearchStatus: null, // bridge 在 state.js 設定
    hasJapanese,
    translateWithOllama,
    // T1c: Internal translate function (called by Alpine wrapper)
    _translateWithAI,
    translateBatch,
    // 檢查是否正在批次翻譯
    isBatchTranslating: (index) => batchTranslatingIndices.has(index),
    MODE_TEXT,
    // 本地狀態查詢
    checkLocalStatus
};

// T1c: 全域函數已在 state.js setupBridgeLayer() 中設定
