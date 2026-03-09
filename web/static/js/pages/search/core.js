/**
 * SearchCore - 核心模組
 * 狀態管理、搜尋邏輯、翻譯功能
 */

// === 狀態變數 ===
// T3.2 Step 4: 14 個 module vars 已刪除（searchResults, currentIndex, currentQuery,
// currentOffset, hasMoreResults, isLoadingMore, isSearchingFile, fileList,
// currentFileIndex, listMode, batchState, appConfig, isTranslating, currentMode）
// 狀態現由 Alpine reactive proxy 管理（透過 SearchCore.state getter 存取）
const PAGE_SIZE = 20;

// 🆕 追蹤正在批次翻譯的片索引（T3.3 再處理）
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
        detailText: document.getElementById('detailText')
    };
}

// === 載入應用設定 ===
async function loadAppConfig() {
    const state = window.SearchCore.state;
    try {
        const resp = await fetch('/api/config');
        const data = await resp.json();
        if (data.success) {
            state.appConfig = data.data;

            // 更新我的最愛按鈕 tooltip
            if (dom.btnFavorite) {
                const favoriteFolder = state.appConfig?.search?.favorite_folder || '系統下載資料夾';
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
    const state = window.SearchCore.state;
    // T1c: isTranslating now managed by Alpine wrapper
    try {
        // === Gemini 模式：只翻譯當前片 ===
        if (state.appConfig?.translate?.provider === 'gemini') {
            let currentResult = null;

            if (state.listMode === 'file' && state.fileList[state.currentFileIndex]) {
                const results = state.fileList[state.currentFileIndex].searchResults || [];
                currentResult = results[state.currentIndex];
            } else {
                currentResult = state.searchResults[state.currentIndex];
            }

            if (!currentResult || !currentResult.title || !hasJapanese(currentResult.title)) {
                throw new Error('當前片無需翻譯');
            }


            // 調用單片翻譯 API
            const result = await translateWithOllama(currentResult.title, 'translate', currentResult);

            if (result.success && result.result) {
                // 更新翻譯結果
                if (state.listMode === 'file') {
                    state.fileList[state.currentFileIndex].searchResults[state.currentIndex].translated_title = result.result;
                } else {
                    state.searchResults[state.currentIndex].translated_title = result.result;
                }
                // T1c: Alpine reactive will update UI automatically

                window.SearchCore.saveState();
            } else {
                throw new Error(result.error || '翻譯失敗');
            }

            return;  // Gemini 模式結束
        }

        // === Ollama 模式：批次翻譯 10 片 ===
        const batch = [];
        const batchMeta = [];

        if (state.listMode === 'file') {
            for (let fi = state.currentFileIndex; fi < state.fileList.length && batch.length < 1; fi++) {
                const file = state.fileList[fi];
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
            for (let i = state.currentIndex; i < state.searchResults.length && batch.length < 1; i++) {
                const result = state.searchResults[i];
                if (result.title && hasJapanese(result.title) && !result.translated_title) {
                    batch.push(result);
                    batchMeta.push({ resultIndex: i });
                }
            }
        }

        if (batch.length === 0) {
            throw new Error('無需翻譯的日文標題');
        }


        if (state.listMode !== 'file') {
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

                if (state.listMode === 'file') {
                    state.fileList[meta.fileIndex].searchResults[meta.resultIndex].translated_title = trans;
                    // T1c: Alpine reactive will update UI automatically
                } else {
                    state.searchResults[meta.resultIndex].translated_title = trans;
                    batchTranslatingIndices.delete(meta.resultIndex);
                    // T1c: Alpine reactive will update UI automatically
                }
            });


            window.SearchCore.saveState();
        }

        if (state.listMode !== 'file') {
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

function clearAll() {
    const state = window.SearchCore.state;
    state.searchResults = [];
    state.currentIndex = 0;
    state.currentQuery = '';
    state.currentOffset = 0;
    state.hasMoreResults = false;
    state.fileList = [];
    state.currentFileIndex = 0;
    state.listMode = null;
    if (dom.queryInput) dom.queryInput.value = '';
    state.isSearchingFile = false;

    // 確保導航按鈕圖示正確
    if (dom.btnPrev) dom.btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
    if (dom.btnNext) dom.btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';

    window.SearchUI.showState('empty');
    updateClearButton();
    sessionStorage.removeItem(STATE_KEY);
}

function updateClearButton() {
    const state = window.SearchCore.state;
    const hasContent = state.searchResults.length > 0 || state.fileList.length > 0;
    // Alpine x-show 控制顯示/隱藏（classList 操作已移除）
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

// T3.2 Step 4: let currentMode = '' 已刪除（改由 Alpine state 管理）

// === 搜尋邏輯 ===
// T1b: doSearch, fallbackSearch 已遷移到 Alpine state.js

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

        // T4: 收集有本地匹配的番號
        const localMatchNumbers = results
            .filter(r => r._localStatus?.exists)
            .map(r => r.number);

        // T4: 觸發跨 scope 事件（通知 sidebar + 卡片）
        if (localMatchNumbers.length > 0) {
            window.dispatchEvent(new CustomEvent('search:local-match', {
                detail: { numbers: localMatchNumbers }
            }));
        }

        // 更新 UI
        if (window.SearchUI?.updateLocalBadges) {
            window.SearchUI.updateLocalBadges();
        }

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
    // Alpine 未 boot 時的安全 fallback（穩定形狀，避免 TypeError）
    _legacyState: {
        searchResults: [],
        currentIndex: 0,
        currentQuery: '',
        currentOffset: 0,
        hasMoreResults: false,
        isLoadingMore: false,
        isSearchingFile: false,
        fileList: [],
        currentFileIndex: 0,
        listMode: null,
        appConfig: null,
        isTranslating: false,
        currentMode: '',
        batchState: {},
        PAGE_SIZE: 20
    },
    // 狀態（供其他模組讀寫）— T3.2: 代理 Alpine reactive proxy
    get state() {
        const el = document.querySelector('.search-container[x-data]');
        if (el && el._x_dataStack) {
            return Alpine.$data(el);  // 直接回傳 Alpine reactive proxy
        }
        // Alpine 未 boot 時回傳 _legacyState（穩定形狀，不報錯）
        return this._legacyState;
    },
    // DOM 引用
    get dom() { return dom; },
    // 初始化
    initDOM,
    // 函數
    loadAppConfig,
    clearAll,
    updateClearButton,
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
