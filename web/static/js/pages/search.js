// === 主程式 ===
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('searchForm');
    const queryInput = document.getElementById('searchQuery');

    const emptyState = document.getElementById('emptyState');
    const loadingState = document.getElementById('loadingState');
    const resultCard = document.getElementById('resultCard');
    const errorState = document.getElementById('errorState');

    // 導航按鈕
    const btnPrev = document.getElementById('btnPrev');
    const btnNext = document.getElementById('btnNext');
    const navIndicator = document.getElementById('navIndicator');
    const currentIndexSpan = document.getElementById('currentIndex');
    const totalCountSpan = document.getElementById('totalCount');

    // 錯誤狀態導航按鈕（多檔案模式用）
    const errorNav = document.getElementById('errorNav');
    const errorBtnPrev = document.getElementById('errorBtnPrev');
    const errorBtnNext = document.getElementById('errorBtnNext');
    const errorNavIndicator = document.getElementById('errorNavIndicator');

    // 清空按鈕
    const btnClear = document.getElementById('btnClear');

    // 搜尋結果
    let searchResults = [];
    let currentIndex = 0;

    // 分頁相關
    let currentQuery = '';
    let currentOffset = 0;
    let hasMoreResults = false;
    let isLoadingMore = false;
    let isSearchingFile = false;  // 追蹤是否正在搜尋檔案
    const PAGE_SIZE = 20;

    // === 多檔案列表狀態 ===
    let fileList = [];  // [{path, filename, number, metadata, searched}]
    let currentFileIndex = 0;
    let listMode = null;  // 'file' | 'search' | null

    // === 翻譯功能 ===
    let appConfig = null;  // 應用設定
    const translationCache = new Map();  // 快取：番號 -> {result, mode}
    let isTranslating = false;  // 防止並發翻譯
    let pendingTranslation = null;  // 待處理的翻譯請求

    // 檔案列表 DOM 元素
    const fileListSection = document.getElementById('fileListSection');
    const fileListContainer = document.getElementById('fileList');
    const fileCountText = document.getElementById('fileCountText');
    const btnSearchAll = document.getElementById('btnSearchAll');
    const btnScrapeAll = document.getElementById('btnScrapeAll');

    // === 載入應用設定 ===
    async function loadAppConfig() {
        try {
            const resp = await fetch('/api/config');
            const data = await resp.json();
            if (data.success) {
                appConfig = data.data;
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
        return /[぀-ゟ゠-ヿ]/.test(text);
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
     */
    window.translateWithAI = async function() {
        const btn = document.getElementById('translateBtn');
        const spinner = document.getElementById('translateSpinner');
        const title = btn.dataset.title;
        const actors = JSON.parse(btn.dataset.actors || '[]');
        const number = btn.dataset.number || '';

        if (!title) return;

        // 防止並發翻譯
        if (isTranslating) return;
        isTranslating = true;

        // 記住開始時的索引（避免切換後存錯位置）
        const startFileIndex = currentFileIndex;
        const startResultIndex = currentIndex;
        const startListMode = listMode;

        // 顯示 loading
        btn.classList.add('d-none');
        spinner.classList.remove('d-none');

        try {
            const result = await translateWithOllama(title, 'translate', { actors, number });

            if (result.success && result.result) {
                // 存入「原本」位置的 metadata（不管現在在哪）
                if (startListMode === 'file' && fileList[startFileIndex]) {
                    const file = fileList[startFileIndex];
                    if (file.searchResults && file.searchResults[startResultIndex]) {
                        file.searchResults[startResultIndex].translated_title = result.result;
                    }
                } else if (searchResults[startResultIndex]) {
                    searchResults[startResultIndex].translated_title = result.result;
                }

                // 只有「還在同一個位置」才更新 UI
                if (currentFileIndex === startFileIndex && currentIndex === startResultIndex) {
                    document.getElementById('resultChineseTitle').textContent = result.result;
                    document.getElementById('chineseTitleRow').classList.remove('d-none');
                    document.getElementById('chineseTitleLabel').textContent = '中文片名 (AI)';
                    // 隱藏按鈕（已翻譯完成）
                    btn.classList.add('d-none');
                }
                // 如果已切換到其他影片，不更新 UI，但資料已存好
                // 用戶切回去時 displayResult() 會正確顯示
            } else {
                // 失敗時，只有還在原位置才恢復按鈕
                if (currentFileIndex === startFileIndex && currentIndex === startResultIndex) {
                    btn.classList.remove('d-none');
                }
                alert(result.error || '翻譯失敗');
            }
        } catch (e) {
            if (currentFileIndex === startFileIndex && currentIndex === startResultIndex) {
                btn.classList.remove('d-none');
            }
            alert('Ollama 連線失敗: ' + e.message);
        } finally {
            // 翻譯完成，解除鎖定
            isTranslating = false;

            // 只有還在原位置才隱藏 spinner
            if (currentFileIndex === startFileIndex && currentIndex === startResultIndex) {
                spinner.classList.add('d-none');
            }

            // 解除當前按鈕的 disabled 狀態（不管在哪）
            btn.disabled = false;
        }
    };

    /**
     * 背景翻譯標題（不阻塞 UI）
     */
    async function translateInBackground(data, currentFile) {
        // 檢查是否啟用翻譯
        if (!appConfig?.translate?.enabled) return;

        const number = data.number;
        if (!number) return;

        // 檢查快取
        if (translationCache.has(number)) {
            const cached = translationCache.get(number);
            updateChineseTitleDisplay(cached.result, cached.mode);
            return;
        }

        // 從檔名提取的中文（如果有）
        const chineseFromFile = currentFile?.chineseTitle || null;
        const japaneseTitle = data.title;

        let textToProcess = null;
        let mode = null;

        // 判斷邏輯：日文假名優先（因為日文漢字也會被判定為中文）
        if (japaneseTitle && hasJapanese(japaneseTitle)) {
            // 標題有日文假名 → 翻譯模式
            textToProcess = japaneseTitle;
            mode = 'translate';
        } else if (chineseFromFile) {
            // 檔名有中文（且標題無日文） → 優化模式
            textToProcess = chineseFromFile;
            mode = 'optimize';
        }

        if (!textToProcess) return;

        // 調用翻譯 API
        const result = await translateWithOllama(textToProcess, mode, {
            actors: data.actors,
            number: number
        });

        if (result.success) {
            // 快取結果
            translationCache.set(number, { result: result.result, mode: mode });
            // 更新 UI（只有當前顯示的番號才更新）
            const currentNumber = document.getElementById('resultNumber').textContent;
            if (currentNumber === number) {
                updateChineseTitleDisplay(result.result, mode);
            }
        } else {
            // 顯示錯誤提示
            console.warn('翻譯失敗:', result.error);
            showTranslateError(result.error);
        }
    }

    /**
     * 更新中文標題顯示（含來源標示）
     */
    function updateChineseTitleDisplay(text, mode) {
        const chineseTitleRow = document.getElementById('chineseTitleRow');
        const chineseTitleLabel = document.getElementById('chineseTitleLabel');
        const chineseTitleEl = document.getElementById('resultChineseTitle');

        if (text) {
            chineseTitleEl.textContent = text;
            // 更新標籤
            if (mode === 'translate') {
                chineseTitleLabel.textContent = '中文片名 (翻譯)';
            } else if (mode === 'optimize') {
                chineseTitleLabel.textContent = '中文片名 (優化)';
            } else {
                chineseTitleLabel.textContent = '中文片名';
            }
            chineseTitleRow.classList.remove('d-none');
        }
    }

    /**
     * 顯示翻譯錯誤（短暫提示）
     */
    function showTranslateError(error) {
        const chineseTitleLabel = document.getElementById('chineseTitleLabel');
        const originalText = chineseTitleLabel.textContent;
        chineseTitleLabel.innerHTML = `中文片名 <span class="text-danger">(${error})</span>`;
        // 3 秒後恢復
        setTimeout(() => {
            if (chineseTitleLabel.innerHTML.includes(error)) {
                chineseTitleLabel.textContent = originalText;
            }
        }, 3000);
    }

    // === 狀態保存/還原 ===
    const STATE_KEY = 'javhelper_search_state';

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
            queryValue: queryInput.value
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
            queryInput.value = state.queryValue || '';

            // 有內容才還原顯示
            if (searchResults.length > 0) {
                displayResult(searchResults[currentIndex]);
                updateNavigation();
                showState('result');

                if (listMode === 'search') {
                    renderSearchResultsList();
                } else if (listMode === 'file') {
                    renderFileList();
                }
                updateClearButton();
                return true;
            } else if (fileList.length > 0 && listMode === 'file') {
                renderFileList();
                updateClearButton();
                // 如果當前檔案有結果，顯示它
                const currentFile = fileList[currentFileIndex];
                if (currentFile && currentFile.searchResults && currentFile.searchResults.length > 0) {
                    searchResults = currentFile.searchResults;
                    hasMoreResults = currentFile.hasMoreResults || false;
                    displayResult(searchResults[currentIndex]);
                    updateNavigation();
                    showState('result');
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
        searchResults = [];
        currentIndex = 0;
        currentQuery = '';
        currentOffset = 0;
        hasMoreResults = false;
        fileList = [];
        currentFileIndex = 0;
        listMode = null;
        queryInput.value = '';
        isSearchingFile = false;

        // 確保導航按鈕圖示正確
        btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
        btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';

        showState('empty');
        fileListSection.classList.add('d-none');
        updateClearButton();
        clearState();
    }

    function updateClearButton() {
        const hasContent = searchResults.length > 0 || fileList.length > 0;
        btnClear.classList.toggle('d-none', !hasContent);
    }

    // 離開頁面前保存狀態
    window.addEventListener('beforeunload', saveState);

    function showState(state) {
        emptyState.classList.add('d-none');
        loadingState.classList.add('d-none');
        resultCard.classList.add('d-none');
        errorState.classList.add('d-none');

        if (state === 'empty') emptyState.classList.remove('d-none');
        else if (state === 'loading') loadingState.classList.remove('d-none');
        else if (state === 'result') resultCard.classList.remove('d-none');
        else if (state === 'error') errorState.classList.remove('d-none');
    }

    function displayResult(data) {
        document.getElementById('resultNumber').textContent = data.number || '-';
        document.getElementById('resultTitle').textContent = data.title || '-';
        document.getElementById('resultActors').textContent = (data.actors || []).join(', ') || '-';
        document.getElementById('resultDate').textContent = data.date || '-';
        document.getElementById('resultMaker').textContent = data.maker || '-';

        // 更新日文標題編輯按鈕狀態
        updateEditButtonState('editTitleBtn', data._titleEdited || false);

        // 取得當前檔案資訊（如果是檔案模式）
        const currentFile = (listMode === 'file' && fileList[currentFileIndex]) ? fileList[currentFileIndex] : null;
        const hasSubtitle = currentFile ? currentFile.hasSubtitle : false;
        const chineseTitle = currentFile ? currentFile.chineseTitle : null;

        // 標籤（全部顯示）+ 字幕標籤
        const tagsContainer = document.getElementById('resultTags');
        const tags = data.tags || [];
        let tagsHtml = '';

        // 優先顯示字幕標籤（綠色）
        if (hasSubtitle) {
            tagsHtml += '<span class="badge tag-badge subtitle">中文字幕</span>';
        }

        // 其他標籤
        if (tags.length > 0) {
            tagsHtml += tags.map(tag =>
                `<span class="badge tag-badge">${tag}</span>`
            ).join('');
        }

        if (tagsHtml) {
            tagsContainer.innerHTML = tagsHtml;
        } else {
            tagsContainer.textContent = '-';
        }

        // 中文標題（優先順序：AI 翻譯 > 檔名提取）
        const chineseTitleRow = document.getElementById('chineseTitleRow');
        const chineseTitleLabel = document.getElementById('chineseTitleLabel');
        const chineseTitleEl = document.getElementById('resultChineseTitle');

        // 檢查是否有 AI 翻譯結果
        const translatedTitle = data.translated_title || null;

        if (translatedTitle) {
            // 優先顯示 AI 翻譯
            chineseTitleLabel.textContent = '中文片名 (AI)';
            chineseTitleEl.textContent = translatedTitle;
            chineseTitleRow.classList.remove('d-none');
            updateEditButtonState('editChineseTitleBtn', data._chineseTitleEdited || false);
        } else if (chineseTitle) {
            // 其次顯示檔名提取的中文
            chineseTitleLabel.textContent = '中文片名';
            chineseTitleEl.textContent = chineseTitle;
            chineseTitleRow.classList.remove('d-none');
            updateEditButtonState('editChineseTitleBtn', false);
        } else {
            chineseTitleLabel.textContent = '中文片名';
            chineseTitleRow.classList.add('d-none');
        }

        // 封面
        const coverImg = document.getElementById('resultCover');
        if (data.cover) {
            coverImg.src = `/api/proxy-image?url=${encodeURIComponent(data.cover)}`;
            coverImg.style.display = 'block';
        } else {
            coverImg.src = '';
            coverImg.style.display = 'none';
        }

        // AI 翻譯按鈕：只在沒有中文片名 + 沒有翻譯結果 + 翻譯啟用 + 日文標題時顯示
        const translateBtn = document.getElementById('translateBtn');
        const translateSpinner = document.getElementById('translateSpinner');
        translateSpinner.classList.add('d-none');  // 重置 spinner

        const shouldShowTranslateBtn = appConfig?.translate?.enabled &&
            !chineseTitle &&
            !translatedTitle &&
            data.title &&
            hasJapanese(data.title);

        if (shouldShowTranslateBtn) {
            translateBtn.classList.remove('d-none');
            translateBtn.dataset.title = data.title;
            translateBtn.dataset.actors = JSON.stringify(data.actors || []);
            translateBtn.dataset.number = data.number || '';
            // 翻譯中則 disabled（灰色）
            translateBtn.disabled = isTranslating;
        } else {
            translateBtn.classList.add('d-none');
            translateBtn.disabled = false;
        }
    }

    // 顯示封面區錯誤（用 SVG 佔位圖）
    function displayCoverError(message) {
        const coverImg = document.getElementById('resultCover');

        // 生成 SVG 錯誤圖片
        const svg = `
            <svg xmlns="http://www.w3.org/2000/svg" width="800" height="538" viewBox="0 0 800 538">
                <rect fill="#f8f9fa" width="800" height="538"/>
                <text x="400" y="230" text-anchor="middle" fill="#ffc107" font-size="80">⚠</text>
                <text x="400" y="300" text-anchor="middle" fill="#dc3545" font-size="20" font-family="sans-serif">${message.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</text>
                <text x="400" y="330" text-anchor="middle" fill="#6c757d" font-size="14" font-family="sans-serif">請檢查番號格式或稍後再試</text>
            </svg>
        `;
        coverImg.src = 'data:image/svg+xml,' + encodeURIComponent(svg);
        coverImg.style.display = 'block';

        // 清空資訊區
        document.getElementById('resultNumber').textContent = '-';
        document.getElementById('resultTitle').textContent = '-';
        document.getElementById('resultActors').textContent = '-';
        document.getElementById('resultDate').textContent = '-';
        document.getElementById('resultMaker').textContent = '-';
        document.getElementById('resultTags').textContent = '-';

        // 隱藏中文片名
        document.getElementById('chineseTitleRow').classList.add('d-none');
        document.getElementById('chineseTitleLabel').textContent = '中文片名';

        // 隱藏 AI 翻譯按鈕
        document.getElementById('translateBtn').classList.add('d-none');
        document.getElementById('translateSpinner').classList.add('d-none');

        // 重置編輯按鈕狀態
        updateEditButtonState('editTitleBtn', false);
        updateEditButtonState('editChineseTitleBtn', false);
    }

    // ========== 標題編輯功能 ========== 

    // HTML 跳脫
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 更新編輯按鈕的圖示狀態
    function updateEditButtonState(btnId, isEdited) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        const icon = btn.querySelector('i');
        if (icon) {
            if (isEdited) {
                icon.className = 'bi bi-pencil-fill text-success';
            } else {
                icon.className = 'bi bi-pencil text-muted';
            }
        }
    }

    // 開始編輯日文標題
    function startEditTitle() {
        const container = document.getElementById('titleContainer');
        const span = document.getElementById('resultTitle');
        const currentText = span.textContent;

        // 隱藏翻譯按鈕和 spinner
        const translateBtn = document.getElementById('translateBtn');
        const translateSpinner = document.getElementById('translateSpinner');
        translateBtn.classList.add('d-none');
        translateSpinner.classList.add('d-none');

        // 替換成編輯模式
        container.innerHTML = `
            <input type="text" id="editTitleInput" class="form-control form-control-sm" value="${escapeHtml(currentText)}" style="flex:1;" />
            <button class="btn btn-sm btn-link p-0 ms-1 text-success" onclick="confirmEditTitle()" title="確認">
                <i class="bi bi-check-lg"></i>
            </button>
            <button class="btn btn-sm btn-link p-0 ms-1 text-danger" onclick="cancelEditTitle()" title="取消">
                <i class="bi bi-x-lg"></i>
            </button>
        `;
        const input = document.getElementById('editTitleInput');
        input.focus();
        input.select();

        // Enter 確認, Escape 取消
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') confirmEditTitle();
            else if (e.key === 'Escape') cancelEditTitle();
        });
    }

    // 確認編輯日文標題
    function confirmEditTitle() {
        const input = document.getElementById('editTitleInput');
        const newValue = input.value.trim();

        // 更新 searchResults
        const file = fileList[currentFileIndex];
        if (file?.searchResults?.[currentIndex]) {
            file.searchResults[currentIndex].title = newValue;
            file.searchResults[currentIndex]._titleEdited = true;
        }

        restoreTitleDisplay(newValue, true);
        saveState();
    }

    // 取消編輯日文標題
    function cancelEditTitle() {
        const file = fileList[currentFileIndex];
        const result = file?.searchResults?.[currentIndex];
        const originalText = result?.title || '-';
        const isEdited = result?._titleEdited || false;
        restoreTitleDisplay(originalText, isEdited);
    }

    // 還原日文標題顯示
    function restoreTitleDisplay(text, edited) {
        const container = document.getElementById('titleContainer');
        const file = fileList[currentFileIndex];
        const result = file?.searchResults?.[currentIndex];
        const chineseTitle = file?.chineseTitle;
        const translatedTitle = result?.translated_title;

        // 決定是否顯示翻譯按鈕
        const shouldShowTranslateBtn = appConfig?.translate?.enabled &&
            !chineseTitle && !translatedTitle && text && text !== '-' && hasJapanese(text);

        container.innerHTML = `
            <span id="resultTitle" style="flex:1;">${escapeHtml(text)}</span>
            <button id="editTitleBtn" class="btn btn-sm btn-link p-0 ms-1" onclick="startEditTitle()" title="編輯標題">
                <i class="bi ${edited ? 'bi-pencil-fill text-success' : 'bi-pencil text-muted'}"></i>
            </button>
            <button id="translateBtn" class="btn btn-sm btn-link p-0 ms-1 ${shouldShowTranslateBtn ? '' : 'd-none'}"
                    onclick="translateWithAI()" title="AI 翻譯">
                <i class="bi bi-translate"></i>
            </button>
            <span id="translateSpinner" class="spinner-border spinner-border-sm ms-1 d-none"></span>
        `;

        if (shouldShowTranslateBtn) {
            const btn = document.getElementById('translateBtn');
            btn.dataset.title = text;
            btn.dataset.actors = JSON.stringify(result?.actors || []);
            btn.dataset.number = result?.number || '';
        }
    }

    // 開始編輯中文標題
    function startEditChineseTitle() {
        const container = document.getElementById('chineseTitleContainer');
        const span = document.getElementById('resultChineseTitle');
        const currentText = span.textContent;

        container.innerHTML = `
            <input type="text" id="editChineseTitleInput" class="form-control form-control-sm text-success" value="${escapeHtml(currentText)}" style="flex:1;" />
            <button class="btn btn-sm btn-link p-0 ms-1 text-success" onclick="confirmEditChineseTitle()" title="確認">
                <i class="bi bi-check-lg"></i>
            </button>
            <button class="btn btn-sm btn-link p-0 ms-1 text-danger" onclick="cancelEditChineseTitle()" title="取消">
                <i class="bi bi-x-lg"></i>
            </button>
        `;
        const input = document.getElementById('editChineseTitleInput');
        input.focus();
        input.select();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') confirmEditChineseTitle();
            else if (e.key === 'Escape') cancelEditChineseTitle();
        });
    }

    // 確認編輯中文標題
    function confirmEditChineseTitle() {
        const input = document.getElementById('editChineseTitleInput');
        const newValue = input.value.trim();

        // 更新 searchResults（存入 translated_title）
        const file = fileList[currentFileIndex];
        if (file?.searchResults?.[currentIndex]) {
            file.searchResults[currentIndex].translated_title = newValue;
            file.searchResults[currentIndex]._chineseTitleEdited = true;
        }

        restoreChineseTitleDisplay(newValue, true);
        saveState();
    }

    // 取消編輯中文標題
    function cancelEditChineseTitle() {
        const file = fileList[currentFileIndex];
        const result = file?.searchResults?.[currentIndex];
        const translatedTitle = result?.translated_title;
        const chineseTitle = file?.chineseTitle;
        const originalText = translatedTitle || chineseTitle || '-';
        const isEdited = result?._chineseTitleEdited || false;
        restoreChineseTitleDisplay(originalText, isEdited);
    }

    // 還原中文標題顯示
    function restoreChineseTitleDisplay(text, edited) {
        const container = document.getElementById('chineseTitleContainer');
        container.innerHTML = `
            <span id="resultChineseTitle" class="text-success" style="flex:1;">${escapeHtml(text)}</span>
            <button id="editChineseTitleBtn" class="btn btn-sm btn-link p-0 ms-1" onclick="startEditChineseTitle()" title="編輯中文片名">
                <i class="bi ${edited ? 'bi-pencil-fill text-success' : 'bi-pencil text-muted'}"></i>
            </button>
        `;
    }

    // 暴露編輯函數到全域（供 onclick 調用）
    window.startEditTitle = startEditTitle;
    window.confirmEditTitle = confirmEditTitle;
    window.cancelEditTitle = cancelEditTitle;
    window.startEditChineseTitle = startEditChineseTitle;
    window.confirmEditChineseTitle = confirmEditChineseTitle;
    window.cancelEditChineseTitle = cancelEditChineseTitle;

    // ========== 結束標題編輯功能 ========== 

    // ========== 手動輸入番號功能 ========== 

    /**
     * 格式化番號（標準化格式）
     */
    function formatNumber(input) {
        if (!input) return null;
        // 嘗試標準化番號格式
        const match = input.match(/([A-Z]{1,5})-?(\d{3,7})/i);
        if (match) {
            return `${match[1].toUpperCase()}-${match[2]}`;
        }
        // FC2 特殊處理
        const fc2Match = input.match(/FC2-?PPV-?(\d{5,7})/i);
        if (fc2Match) {
            return `FC2-PPV-${fc2Match[1]}`;
        }
        return input.toUpperCase();
    }

    /**
     * 手動輸入番號
     */
    function enterNumber(index) {
        const file = fileList[index];
        if (!file) return;

        const number = prompt('請輸入番號（例如：T28-650）', '');
        if (!number || !number.trim()) return;

        // 格式化番號
        const formatted = formatNumber(number.trim());
        file.number = formatted;
        file.searched = false;  // 重置搜尋狀態
        file.searchResults = [];  // 清空舊結果

        // 切換到該檔案並搜尋
        switchToFile(index, 'first', true);
    }

    /**
     * 從列表中移除檔案
     */
    function removeFile(index) {
        if (index < 0 || index >= fileList.length) return;

        // 移除檔案
        fileList.splice(index, 1);

        // 調整當前索引
        if (fileList.length === 0) {
            // 沒有檔案了，清空顯示
            clearAll();
            return;
        }

        if (currentFileIndex >= fileList.length) {
            currentFileIndex = fileList.length - 1;
        } else if (currentFileIndex > index) {
            currentFileIndex--;
        }

        // 重新渲染並切換
        renderFileList();
        if (fileList.length > 0) {
            switchToFile(currentFileIndex, 'first', false);
        }
        saveState();
    }

    // 暴露到全域
    window.enterNumber = enterNumber;
    window.removeFile = removeFile;

    // ========== 結束手動輸入番號功能 ========== 

    // 預加載圖片（避免切換時延遲）
    function preloadImages(startIndex, count = 5) {
        for (let i = startIndex; i < Math.min(startIndex + count, searchResults.length); i++) {
            if (searchResults[i] && searchResults[i].cover) {
                const img = new Image();
                img.src = `/api/proxy-image?url=${encodeURIComponent(searchResults[i].cover)}`;
            }
        }
    }

    function updateNavigation() {
        // 多檔案模式或多結果時都顯示導航
        const hasMultipleResults = searchResults.length > 1 || hasMoreResults;
        const hasMultipleFiles = fileList.length > 1;
        const showNav = hasMultipleResults || hasMultipleFiles;

        // 確保按鈕圖示正確（防止卡在 spinner 狀態）
        if (!isLoadingMore && !isSearchingFile) {
            btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
            btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';
        }

        btnPrev.classList.toggle('d-none', !showNav);
        btnNext.classList.toggle('d-none', !showNav);
        navIndicator.classList.toggle('d-none', !showNav);

        // 判斷是否可往左（有前一個結果，或有前一個檔案）
        const canGoPrev = currentIndex > 0 || currentFileIndex > 0;
        // 判斷是否可往右（有後續結果、更多結果、或後續檔案）
        const canGoNext = currentIndex < searchResults.length - 1 || hasMoreResults || currentFileIndex < fileList.length - 1;

        if (showNav) {
            // 多檔案模式：顯示檔案索引
            if (fileList.length > 1) {
                currentIndexSpan.textContent = currentFileIndex + 1;
                totalCountSpan.textContent = fileList.length;
            } else {
                // 單檔案模式：顯示搜尋結果索引
                currentIndexSpan.textContent = currentIndex + 1;
                totalCountSpan.textContent = hasMoreResults
                    ? searchResults.length + '+'
                    : searchResults.length;
            }

            btnPrev.disabled = !canGoPrev;
            btnNext.disabled = !canGoNext;
        }

        // 更新 error 狀態的導航按鈕（多檔案模式）
        if (hasMultipleFiles) {
            errorNav.classList.remove('d-none');
            errorNavIndicator.textContent = `${currentFileIndex + 1}/${fileList.length}`;
            errorBtnPrev.disabled = !canGoPrev;
            errorBtnNext.disabled = !canGoNext;
        } else {
            errorNav.classList.add('d-none');
        }
    }

    function navigateResult(delta) {
        const newIndex = currentIndex + delta;

        // 往左且已在第一個 → 切換到上一個檔案
        if (delta < 0 && newIndex < 0) {
            if (currentFileIndex > 0) {
                switchToFile(currentFileIndex - 1, 'last');  // 切到上一個檔案的最後一個結果
            }
            return;
        }

        // 往右且到最後一個
        if (delta > 0 && newIndex >= searchResults.length) {
            // 先嘗試載入更多結果
            if (hasMoreResults && !isLoadingMore) {
                loadMoreResults();
                return;
            }
            // 沒有更多結果了，切換到下一個檔案
            if (currentFileIndex < fileList.length - 1) {
                switchToFile(currentFileIndex + 1, 'first');
                return;
            }
            return;
        }

        if (newIndex >= 0 && newIndex < searchResults.length) {
            currentIndex = newIndex;
            displayResult(searchResults[currentIndex]);
            updateNavigation();
            preloadImages(currentIndex + 1, 3);
            // 搜尋模式下更新列表高亮
            if (listMode === 'search') {
                renderSearchResultsList();
            }
        }
    }

    // 載入更多結果
    async function loadMoreResults() {
        if (isLoadingMore || !hasMoreResults || !currentQuery) return;

        isLoadingMore = true;
        const newOffset = currentOffset + PAGE_SIZE;

        // 顯示載入中狀態在 Next 按鈕
        btnNext.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        btnNext.disabled = true;

        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(currentQuery)}&offset=${newOffset}&limit=${PAGE_SIZE}`);
            const data = await response.json();

            if (response.ok && data.success && data.data && data.data.length > 0) {
                // 追加新結果
                searchResults = searchResults.concat(data.data);
                currentOffset = newOffset;
                hasMoreResults = data.has_more;

                // 自動移到下一個（新載入的第一個）
                currentIndex = searchResults.length - data.data.length;
                displayResult(searchResults[currentIndex]);
                updateNavigation();

                // 預加載新圖片
                preloadImages(currentIndex + 1, 5);

                // 更新搜尋結果列表
                if (listMode === 'search') {
                    renderSearchResultsList();
                }
            } else {
                // 沒有更多結果了
                hasMoreResults = false;
                updateNavigation();
            }
        } catch (err) {
            console.error('載入更多失敗:', err);
        } finally {
            isLoadingMore = false;
            btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';
            updateNavigation();
        }
    }

    // === 進度指示器控制 ===
    const progressQuery = document.getElementById('progressQuery');
    const progressLog = document.getElementById('progressLog');
    const detailProgress = document.getElementById('detailProgress');
    const detailBar = document.getElementById('detailBar');
    const detailText = document.getElementById('detailText');

    // 搜尋模式對照
    const MODE_TEXT = {
        'exact': '完整番號搜尋',
        'partial': '部分番號搜尋',
        'prefix': '系列搜尋',
        'actress': '女優搜尋',
        'keyword': '全文搜尋'
    };

    function initProgress(query) {
        progressQuery.textContent = `"${query}"`;
        progressLog.textContent = '搜尋中...';
        detailProgress.classList.remove('show');
    }

    function updateLog(text) {
        progressLog.textContent = text;
    }

    function updateDetailProgress(done, total) {
        if (total > 0) {
            detailProgress.classList.add('show');
            const percent = Math.round((done / total) * 100);
            detailBar.style.width = `${percent}%`;
            detailText.textContent = `${done} / ${total}`;
        }
    }

    // 當前模式
    let currentMode = '';

    function handleSearchStatus(source, status) {
        // 處理模式切換
        if (source === 'mode') {
            currentMode = status;
            updateLog(`${MODE_TEXT[status] || status}...`);
            return;
        }

        // 根據來源和狀態更新日誌
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

    // 搜尋表單
    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        const query = queryInput.value.trim();
        if (!query) return;

        showState('loading');
        initProgress(query);
        searchResults = [];
        currentIndex = 0;

        // 清空多檔案列表（文字搜尋與拖檔搜尋互斥）
        fileList = [];
        currentFileIndex = 0;
        listMode = null;
        fileListSection.classList.add('d-none');

        // 重設分頁狀態
        currentQuery = query;
        currentOffset = 0;
        hasMoreResults = false;

        // 使用 SSE 串流 API
        const eventSource = new EventSource(`/api/search/stream?q=${encodeURIComponent(query)}`);

        eventSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'mode') {
                    // 設定當前模式並更新日誌
                    currentMode = data.mode;
                    updateLog(`${MODE_TEXT[data.mode] || '搜尋'}...`);
                }
                else if (data.type === 'status') {
                    // 更新進度狀態
                    handleSearchStatus(data.source, data.status);
                }
                else if (data.type === 'result') {
                    // 搜尋完成
                    eventSource.close();

                    if (data.success && data.data && data.data.length > 0) {
                        searchResults = data.data;
                        currentIndex = 0;
                        hasMoreResults = data.has_more || false;
                        displayResult(searchResults[0]);
                        updateNavigation();
                        showState('result');
                        // 預加載前 5 張圖片
                        preloadImages(1, 5);
                        // 顯示搜尋結果列表
                        listMode = 'search';
                        renderSearchResultsList();
                        updateClearButton();
                    } else {
                        document.getElementById('errorMessage').textContent = '找不到資料';
                        showState('error');
                    }
                }
                else if (data.type === 'error') {
                    // 錯誤
                    eventSource.close();
                    document.getElementById('errorMessage').textContent = data.message || '搜尋失敗';
                    showState('error');
                }
            } catch (err) {
                console.error('Parse error:', err);
            }
        };

        eventSource.onerror = function() {
            eventSource.close();
            // 如果 SSE 失敗，回退到傳統 API
            fallbackSearch(query);
        };
    });

    // 傳統 API 回退
    async function fallbackSearch(query) {
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (response.ok && data.success && data.data && data.data.length > 0) {
                searchResults = data.data;
                currentIndex = 0;
                hasMoreResults = data.has_more || false;  // 設定是否還有更多
                displayResult(searchResults[0]);
                updateNavigation();
                showState('result');
                preloadImages(1, 5);
                // 顯示搜尋結果列表
                listMode = 'search';
                renderSearchResultsList();
                updateClearButton();
            } else {
                document.getElementById('errorMessage').textContent = data.error || '找不到資料';
                showState('error');
            }
        } catch (err) {
            document.getElementById('errorMessage').textContent = '網路錯誤: ' + err.message;
            showState('error');
        }
    }

    // 導航按鈕點擊
    btnPrev.addEventListener('click', () => navigateResult(-1));
    btnNext.addEventListener('click', () => navigateResult(1));

    // Error 狀態導航按鈕點擊（多檔案模式）
    errorBtnPrev.addEventListener('click', () => navigateResult(-1));
    errorBtnNext.addEventListener('click', () => navigateResult(1));

    // 鍵盤導航
    document.addEventListener('keydown', (e) => {
        // 如果正在輸入搜尋框，不處理
        if (document.activeElement === queryInput) return;

        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            navigateResult(-1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            navigateResult(1);
        }
    });

    // 清空按鈕點擊
    btnClear.addEventListener('click', clearAll);

    // 初始化：載入設定、還原狀態
    loadAppConfig();  // 背景載入設定（用於翻譯功能）

    if (!restoreState()) {
        queryInput.focus();
    }
    updateClearButton();

    // === 檔案列表功能 ===

    // 渲染檔案列表
    function renderFileList() {
        // 顯示/隱藏檔案列表區
        fileListSection.classList.toggle('d-none', fileList.length === 0);

        fileListContainer.innerHTML = '';
        fileCountText.textContent = `檔案 ${currentFileIndex + 1}/${fileList.length}`;

        // 顯示產生按鈕（拖檔模式）
        btnScrapeAll.classList.remove('d-none');

        fileList.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'file-item' + (index === currentFileIndex ? ' active' : '');

            // 狀態圖標：✓ 有結果、✗ 無結果、? 無番號（可輸入）、空白 未搜尋
            let statusIcon = '';
            let statusClass = 'file-status';
            let canScrape = false;
            let needsNumber = false;
            if (!file.number) {
                statusIcon = '?';
                statusClass += ' text-warning';
                needsNumber = true;
            } else if (file.searched) {
                if (file.searchResults && file.searchResults.length > 0) {
                    statusIcon = '✓';
                    canScrape = true;
                } else {
                    statusIcon = '✗';
                    statusClass += ' text-danger';
                }
            }

            // 按鈕：產生 或 輸入番號
            let actionBtn = '';
            if (canScrape) {
                actionBtn = `<button class="btn btn-outline-success btn-sm btn-scrape-single" data-index="${index}" title="產生此檔案">產生</button>`;
            } else if (needsNumber) {
                actionBtn = `<button class="btn btn-outline-warning btn-sm btn-enter-number" data-index="${index}" title="手動輸入番號"><i class="bi bi-pencil"></i></button>`;
            }

            item.innerHTML = `
                <button class="btn btn-link btn-sm p-0 btn-remove-file text-muted" data-index="${index}" title="移除此檔案">
                    <i class="bi bi-x"></i>
                </button>
                <i class="bi bi-file-earmark-play file-icon"></i>
                <span class="file-name" title="${file.path}">${file.filename}</span>
                <span class="${statusClass}">${statusIcon}</span>
                ${actionBtn}
            `;

            // 點擊檔名切換（排除按鈕區域）
            item.addEventListener('click', (e) => {
                if (!e.target.closest('.btn-scrape-single') && !e.target.closest('.btn-enter-number') && !e.target.closest('.btn-remove-file')) {
                    switchToFile(index, 'first');
                }
            });

            // 移除按鈕事件
            const removeBtn = item.querySelector('.btn-remove-file');
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                removeFile(index);
            });

            // 產生按鈕事件
            if (canScrape) {
                const btn = item.querySelector('.btn-scrape-single');
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    scrapeSingle(index);
                });
            }

            // 輸入番號按鈕事件
            if (needsNumber) {
                const btn = item.querySelector('.btn-enter-number');
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    enterNumber(index);
                });
            }

            fileListContainer.appendChild(item);
        });
    }

    // 渲染搜尋結果列表（文字搜尋模式）
    function renderSearchResultsList() {
        if (searchResults.length === 0) {
            fileListSection.classList.add('d-none');
            return;
        }

        fileListSection.classList.remove('d-none');
        fileListContainer.innerHTML = '';

        // 更新標題
        const countText = hasMoreResults ? `${searchResults.length}+` : searchResults.length;
        fileCountText.textContent = `搜尋結果 (${countText})`;

        // 隱藏產生按鈕（搜尋模式不需要）
        btnScrapeAll.classList.add('d-none');

        searchResults.forEach((result, index) => {
            const item = document.createElement('div');
            item.className = 'file-item' + (index === currentIndex ? ' active' : '');

            // 格式：番號 + 演員 + 片名（CSS 自動截斷）
            const number = result.number || '';
            const actors = (result.actors || []).slice(0, 2).join(', ') || '-';
            const title = result.title || '';

            item.innerHTML = `
                <span style="flex-shrink:0; font-weight:500; color:#0d6efd; min-width:90px;">${number}</span>
                <span style="flex-shrink:0; min-width:80px; color:#6c757d;">${actors}</span>
                <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${title}</span>
            `;
            item.addEventListener('click', () => switchToSearchResult(index));
            fileListContainer.appendChild(item);
        });
    }

    // 切換到搜尋結果（文字搜尋模式）
    function switchToSearchResult(index) {
        if (index < 0 || index >= searchResults.length) return;
        currentIndex = index;
        displayResult(searchResults[currentIndex]);
        updateNavigation();
        renderSearchResultsList();  // 更新高亮
    }

    // 切換到指定檔案（懶加載搜尋）
    // position: 'first' 顯示第一個結果, 'last' 顯示最後一個結果
    // showFullLoading: true 顯示全畫面 loading（首次拖入時）
    async function switchToFile(index, position = 'first', showFullLoading = false) {
        if (index < 0 || index >= fileList.length) return;

        currentFileIndex = index;
        const file = fileList[index];

        // 無番號檔案：在封面區顯示錯誤（保留列表）
        if (!file.number) {
            renderFileList();  // 更新列表高亮
            searchResults = [];
            hasMoreResults = false;
            currentIndex = 0;
            displayCoverError(`無法識別番號: ${file.filename}`);
            showState('result');  // 顯示 resultCard 以保留列表
            updateNavigation();
            return;
        }

        // 如果還沒搜尋過，執行搜尋
        // 注意：不在此處呼叫 renderFileList()，避免 race condition
        // searchForFile() 完成後會自行呼叫 renderFileList()
        if (!file.searched) {
            await searchForFile(file, position, showFullLoading);
        } else if (file.searchResults && file.searchResults.length > 0) {
            // 已有結果，直接顯示
            renderFileList();  // 更新列表高亮
            searchResults = file.searchResults;
            hasMoreResults = file.hasMoreResults || false;
            currentIndex = position === 'last' ? searchResults.length - 1 : 0;
            displayResult(searchResults[currentIndex]);
            updateNavigation();
            showState('result');
        } else {
            // 已搜尋但無結果：在封面區顯示錯誤（保留列表）
            renderFileList();  // 更新列表高亮
            searchResults = [];
            hasMoreResults = false;
            currentIndex = 0;
            displayCoverError(`找不到 ${file.number} 的資料`);
            showState('result');  // 顯示 resultCard 以保留列表
            updateNavigation();
        }
    }

    // 為檔案執行搜尋
    // position: 'first' 顯示第一個結果, 'last' 顯示最後一個結果
    // showFullLoading: true 顯示全畫面 loading（首次拖入時）, false 只顯示箭頭轉圈
    // 返回 Promise，讓 searchAll 可以等待搜尋完成
    function searchForFile(file, position = 'first', showFullLoading = false) {
        return new Promise((resolve) => {
            // 判斷是往左還是往右切換
            const isGoingNext = position === 'first';
            const targetBtn = isGoingNext ? btnNext : btnPrev;
            const targetBtnIcon = isGoingNext ? '<i class="bi bi-chevron-right"></i>' : '<i class="bi bi-chevron-left"></i>';

            isSearchingFile = true;

            if (showFullLoading) {
                showState('loading');
                initProgress(file.number);
            } else {
                // 只在箭頭按鈕上顯示轉圈
                targetBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
                targetBtn.disabled = true;
            }

            const eventSource = new EventSource(`/api/search/stream?q=${encodeURIComponent(file.number)}`);

            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'mode') {
                        currentMode = data.mode;
                    }
                    else if (data.type === 'status') {
                        // 這裡不顯示 status，避免干擾（單檔搜尋通常很快）
                    }
                    else if (data.type === 'result') {
                        eventSource.close();
                        isSearchingFile = false;

                        // 恢復按鈕狀態
                        if (!showFullLoading) {
                            targetBtn.innerHTML = targetBtnIcon;
                            targetBtn.disabled = false;
                        }

                        // 確保維持檔案模式（防止被其他代碼覆蓋）
                        listMode = 'file';

                        if (data.success && data.data && data.data.length > 0) {
                            file.searchResults = data.data;
                            file.hasMoreResults = data.has_more || false;
                            file.searched = true;

                            // 只有當前還是這個檔案時才更新 UI
                            if (fileList[currentFileIndex] === file) {
                                searchResults = file.searchResults;
                                hasMoreResults = file.hasMoreResults;
                                currentIndex = position === 'last' ? searchResults.length - 1 : 0;
                                displayResult(searchResults[currentIndex]);
                                updateNavigation();
                                showState('result');
                                renderFileList();
                            } else {
                                // 雖然切換走了，但要更新列表狀態
                                renderFileList();
                            }
                        } else {
                            file.searchResults = [];
                            file.searched = true;
                            // 失敗處理
                            if (fileList[currentFileIndex] === file) {
                                displayCoverError(`找不到 ${file.number} 的資料`);
                                showState('result');
                                updateNavigation();
                                renderFileList();
                            } else {
                                renderFileList();
                            }
                        }
                        resolve(true); // 成功完成
                    }
                    else if (data.type === 'error') {
                        eventSource.close();
                        isSearchingFile = false;
                        if (!showFullLoading) {
                            targetBtn.innerHTML = targetBtnIcon;
                            targetBtn.disabled = false;
                        }
                        file.searchResults = [];
                        file.searched = true;
                        
                        if (fileList[currentFileIndex] === file) {
                            displayCoverError(`搜尋錯誤: ${data.message}`);
                            showState('result');
                            updateNavigation();
                            renderFileList();
                        } else {
                            renderFileList();
                        }
                        resolve(false); // 失敗完成
                    }
                } catch (err) {
                    console.error('Parse error:', err);
                    eventSource.close();
                    resolve(false);
                }
            };

            eventSource.onerror = function() {
                eventSource.close();
                isSearchingFile = false;
                if (!showFullLoading) {
                    targetBtn.innerHTML = targetBtnIcon;
                    targetBtn.disabled = false;
                }
                resolve(false);
            };
        });
    }

    // === 批次操作 ===

    // 單檔產生 NFO
    async function scrapeSingle(index) {
        const file = fileList[index];
        // 取第一個結果（通常是最準確的）
        const metadata = file.searchResults[0];
        if (!metadata) return;

        // 顯示產生中...
        const btn = document.querySelector(`.btn-scrape-single[data-index="${index}"]`);
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        }

        try {
            const resp = await fetch('/api/scrape-single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: file.path,
                    number: metadata.number,
                    metadata: metadata
                })
            });
            const result = await resp.json();

            if (result.success) {
                // 成功，從列表移除
                removeFile(index);
                showToast(`已產生 NFO: ${metadata.number}`, 'success');
            } else {
                alert('產生失敗: ' + result.error);
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '產生';
                }
            }
        } catch (e) {
            alert('系統錯誤: ' + e.message);
            if (btn) {
                btn.disabled = false;
                btn.textContent = '產生';
            }
        }
    }

    // 產生全部
    async function scrapeAll() {
        // 找出所有已搜尋且有結果的檔案
        const targets = fileList
            .map((file, index) => ({ file, index }))
            .filter(item => item.file.searched && item.file.searchResults && item.file.searchResults.length > 0);

        if (targets.length === 0) {
            alert('沒有可產生的檔案（請先搜尋）');
            return;
        }

        if (!confirm(`確定要產生 ${targets.length} 個檔案的 NFO 嗎？`)) return;

        btnScrapeAll.disabled = true;
        let successCount = 0;

        // 依序處理（為了避免 UI 卡頓，這裡用序列執行）
        // 倒序處理，因為移除檔案會改變索引
        for (let i = targets.length - 1; i >= 0; i--) {
            const { file, index } = targets[i];
            const metadata = file.searchResults[0];

            // 更新按鈕狀態
            const btn = document.querySelector(`.btn-scrape-single[data-index="${index}"]`);
            if (btn) btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

            try {
                const resp = await fetch('/api/scrape-single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: file.path,
                        number: metadata.number,
                        metadata: metadata
                    })
                });
                const result = await resp.json();
                if (result.success) {
                    removeFile(index);
                    successCount++;
                }
            } catch (e) {
                console.error(e);
            }
        }

        btnScrapeAll.disabled = false;
        showToast(`批次處理完成，成功 ${successCount} 個`, 'success');
    }

    // 搜尋全部
    async function searchAll() {
        // 找出所有未搜尋且有番號的檔案
        const targets = fileList
            .map((file, index) => ({ file, index }))
            .filter(item => !item.file.searched && item.file.number);

        if (targets.length === 0) {
            alert('沒有需要搜尋的檔案');
            return;
        }

        btnSearchAll.disabled = true;
        let successCount = 0;

        // 切換到 Loading 狀態
        showState('loading');
        progressQuery.textContent = "批次搜尋中...";
        detailProgress.classList.add('show');

        for (let i = 0; i < targets.length; i++) {
            const { file, index } = targets[i];
            
            // 更新進度條
            updateDetailProgress(i + 1, targets.length);
            updateLog(`正在搜尋 (${i+1}/${targets.length}): ${file.number}`);

            // 切換到該檔案（會顯示封面區 loading）
            currentFileIndex = index;
            renderFileList(); // 更新高亮
            
            // 執行搜尋 (await 等待完成)
            // 這裡傳入 true 顯示全畫面 loading 其實會被上面的 showState 蓋過，但沒關係
            // 重點是 searchForFile 會更新 file.searchResults
            const success = await searchForFile(file, 'first', false);
            if (success) successCount++;
            
            // 稍微延遲避免請求過快
            await new Promise(r => setTimeout(r, 500));
        }

        btnSearchAll.disabled = false;
        
        // 全部完成後，顯示最後一個檔案的結果
        if (fileList.length > 0) {
            switchToFile(currentFileIndex, 'first');
        } else {
            showState('empty');
        }
        
        showToast(`搜尋完成，成功 ${successCount}/${targets.length}`, 'success');
    }

    // 綁定批次按鈕
    btnScrapeAll.addEventListener('click', scrapeAll);
    btnSearchAll.addEventListener('click', searchAll);

    // 監聽來自 PyWebView 的檔案拖放
    window.addEventListener('pywebview-files', function(e) {
        const paths = e.detail.paths;
        if (!paths || paths.length === 0) return;

        // 切換模式
        listMode = 'file';
        fileListSection.classList.remove('d-none'); // 顯示列表

        let newFilesCount = 0;

        paths.forEach(path => {
            // 避免重複加入
            if (fileList.some(f => f.path === path)) return;

            const filename = path.split(/[/\]/).pop();
            const number = extractNumberGlobal(filename); // 使用全域提取函數

            fileList.push({
                path: path,
                filename: filename,
                number: number,
                searched: false,
                searchResults: [],
                hasMoreResults: false
            });
            newFilesCount++;
        });

        if (newFilesCount > 0) {
            // 如果是第一批檔案，切換到第一個
            if (fileList.length === newFilesCount) {
                currentFileIndex = 0;
                switchToFile(0, 'first', true); // true = 顯示全畫面 loading 並自動搜尋
            } else {
                renderFileList(); // 只更新列表
            }
            showToast(`已加入 ${newFilesCount} 個檔案`);
        }
    });

    // 初始按鈕事件
    document.getElementById('btnAddFiles').addEventListener('click', () => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.select_files();
        } else {
            alert('請在桌面應用程式中使用此功能');
        }
    });

    document.getElementById('btnAddFolder').addEventListener('click', () => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.select_folder();
        } else {
            alert('請在桌面應用程式中使用此功能');
        }
    });

});