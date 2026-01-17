/**
 * SearchUI - UI 模組
 * 狀態顯示、結果展示、導航、標題編輯
 */

// === 狀態切換 ===

function showState(state) {
    const { dom } = window.SearchCore;

    dom.emptyState.classList.add('d-none');
    dom.loadingState.classList.add('d-none');
    dom.resultCard.classList.add('d-none');
    dom.errorState.classList.add('d-none');

    if (state === 'empty') dom.emptyState.classList.remove('d-none');
    else if (state === 'loading') dom.loadingState.classList.remove('d-none');
    else if (state === 'result') dom.resultCard.classList.remove('d-none');
    else if (state === 'error') dom.errorState.classList.remove('d-none');
}

// === 結果顯示 ===

function displayResult(data) {
    const { state } = window.SearchCore;

    document.getElementById('resultNumber').textContent = data.number || '-';
    document.getElementById('resultTitle').textContent = data.title || '-';
    document.getElementById('resultActors').textContent = (data.actors || []).join(', ') || '-';
    document.getElementById('resultDate').textContent = data.date || '-';
    document.getElementById('resultMaker').textContent = data.maker || '-';

    // 更新日文標題編輯按鈕狀態
    updateEditButtonState('editTitleBtn', data._titleEdited || false);

    // 取得當前檔案資訊
    const currentFile = (state.listMode === 'file' && state.fileList[state.currentFileIndex])
        ? state.fileList[state.currentFileIndex] : null;
    const hasSubtitle = currentFile ? currentFile.hasSubtitle : false;
    const chineseTitle = currentFile ? currentFile.chineseTitle : null;

    // 標籤（全部顯示）+ 字幕標籤
    const tagsContainer = document.getElementById('resultTags');
    const tags = data.tags || [];
    let tagsHtml = '';

    if (hasSubtitle) {
        tagsHtml += '<span class="badge tag-badge subtitle">中文字幕</span>';
    }

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

    // 中文標題
    const chineseTitleRow = document.getElementById('chineseTitleRow');
    const chineseTitleLabel = document.getElementById('chineseTitleLabel');
    const chineseTitleEl = document.getElementById('resultChineseTitle');
    const translatedTitle = data.translated_title || null;

    if (translatedTitle) {
        chineseTitleLabel.textContent = '中文片名 (AI)';
        chineseTitleEl.textContent = translatedTitle;
        chineseTitleRow.classList.remove('d-none');
        updateEditButtonState('editChineseTitleBtn', data._chineseTitleEdited || false);
    } else if (chineseTitle) {
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

    // AI 翻譯按鈕
    const translateBtn = document.getElementById('translateBtn');
    const translateSpinner = document.getElementById('translateSpinner');
    translateSpinner.classList.add('d-none');

    const appConfig = state.appConfig;
    const shouldShowTranslateBtn = appConfig?.translate?.enabled &&
        !chineseTitle &&
        !translatedTitle &&
        data.title &&
        window.SearchCore.hasJapanese(data.title);

    // 🆕 檢查是否正在批次翻譯中
    const isBatchTranslating = window.SearchCore.isBatchTranslating(state.currentIndex);

    if (shouldShowTranslateBtn) {
        if (isBatchTranslating) {
            // 🆕 正在批次翻譯中 → 顯示 spinner
            translateBtn.classList.add('d-none');
            translateSpinner.classList.remove('d-none');
        } else {
            // 未翻譯 → 顯示翻譯按鈕
            translateBtn.classList.remove('d-none');
            translateBtn.dataset.title = data.title;
            translateBtn.dataset.actors = JSON.stringify(data.actors || []);
            translateBtn.dataset.number = data.number || '';
            translateBtn.disabled = state.isTranslating;
        }
    } else {
        translateBtn.classList.add('d-none');
        translateBtn.disabled = false;
    }
}

function displayCoverError(message) {
    const coverImg = document.getElementById('resultCover');

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

    document.getElementById('resultNumber').textContent = '-';
    document.getElementById('resultTitle').textContent = '-';
    document.getElementById('resultActors').textContent = '-';
    document.getElementById('resultDate').textContent = '-';
    document.getElementById('resultMaker').textContent = '-';
    document.getElementById('resultTags').textContent = '-';

    document.getElementById('chineseTitleRow').classList.add('d-none');
    document.getElementById('chineseTitleLabel').textContent = '中文片名';

    document.getElementById('translateBtn').classList.add('d-none');
    document.getElementById('translateSpinner').classList.add('d-none');

    updateEditButtonState('editTitleBtn', false);
    updateEditButtonState('editChineseTitleBtn', false);
}

// === 導航 ===

function preloadImages(startIndex, count = 5) {
    const { state } = window.SearchCore;
    for (let i = startIndex; i < Math.min(startIndex + count, state.searchResults.length); i++) {
        if (state.searchResults[i] && state.searchResults[i].cover) {
            const img = new Image();
            img.src = `/api/proxy-image?url=${encodeURIComponent(state.searchResults[i].cover)}`;
        }
    }
}

function updateNavigation() {
    const { state, dom } = window.SearchCore;

    const hasMultipleResults = state.searchResults.length > 1 || state.hasMoreResults;
    const hasMultipleFiles = state.fileList.length > 1;
    const showNav = hasMultipleResults || hasMultipleFiles;

    // 確保按鈕圖示正確
    if (!state.isLoadingMore && !state.isSearchingFile) {
        dom.btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
        dom.btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';
    }

    dom.btnPrev.classList.toggle('d-none', !showNav);
    dom.btnNext.classList.toggle('d-none', !showNav);
    dom.navIndicator.classList.toggle('d-none', !showNav);

    const canGoPrev = state.currentIndex > 0 || state.currentFileIndex > 0;
    const canGoNext = state.currentIndex < state.searchResults.length - 1 ||
        state.hasMoreResults ||
        state.currentFileIndex < state.fileList.length - 1;

    if (showNav) {
        if (state.fileList.length > 1) {
            dom.currentIndexSpan.textContent = state.currentFileIndex + 1;
            dom.totalCountSpan.textContent = state.fileList.length;
        } else {
            dom.currentIndexSpan.textContent = state.currentIndex + 1;
            dom.totalCountSpan.textContent = state.hasMoreResults
                ? state.searchResults.length + '+'
                : state.searchResults.length;
        }

        dom.btnPrev.disabled = !canGoPrev;
        dom.btnNext.disabled = !canGoNext;
    }

    // 更新 error 狀態的導航按鈕
    if (hasMultipleFiles) {
        dom.errorNav.classList.remove('d-none');
        dom.errorNavIndicator.textContent = `${state.currentFileIndex + 1}/${state.fileList.length}`;
        dom.errorBtnPrev.disabled = !canGoPrev;
        dom.errorBtnNext.disabled = !canGoNext;
    } else {
        dom.errorNav.classList.add('d-none');
    }
}

function navigateResult(delta) {
    const { state } = window.SearchCore;
    const newIndex = state.currentIndex + delta;

    // 往左且已在第一個 → 切換到上一個檔案
    if (delta < 0 && newIndex < 0) {
        if (state.currentFileIndex > 0) {
            window.SearchFile.switchToFile(state.currentFileIndex - 1, 'last');
        }
        return;
    }

    // 往右且到最後一個
    if (delta > 0 && newIndex >= state.searchResults.length) {
        if (state.hasMoreResults && !state.isLoadingMore) {
            loadMoreResults();
            return;
        }
        if (state.currentFileIndex < state.fileList.length - 1) {
            window.SearchFile.switchToFile(state.currentFileIndex + 1, 'first');
            return;
        }
        return;
    }

    if (newIndex >= 0 && newIndex < state.searchResults.length) {
        state.currentIndex = newIndex;
        displayResult(state.searchResults[state.currentIndex]);
        updateNavigation();
        preloadImages(state.currentIndex + 1, 3);
        if (state.listMode === 'search') {
            window.SearchFile.renderSearchResultsList();
        }
    }
}

async function loadMoreResults() {
    const { state, dom } = window.SearchCore;

    if (state.isLoadingMore || !state.hasMoreResults || !state.currentQuery) return;

    state.isLoadingMore = true;
    const newOffset = state.currentOffset + state.PAGE_SIZE;

    dom.btnNext.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    dom.btnNext.disabled = true;

    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(state.currentQuery)}&offset=${newOffset}&limit=${state.PAGE_SIZE}`);
        const data = await response.json();

        if (response.ok && data.success && data.data && data.data.length > 0) {
            state.searchResults = state.searchResults.concat(data.data);
            state.currentOffset = newOffset;
            state.hasMoreResults = data.has_more;

            state.currentIndex = state.searchResults.length - data.data.length;
            displayResult(state.searchResults[state.currentIndex]);
            updateNavigation();

            preloadImages(state.currentIndex + 1, 5);

            if (state.listMode === 'search') {
                window.SearchFile.renderSearchResultsList();
            }
        } else {
            state.hasMoreResults = false;
            updateNavigation();
        }
    } catch (err) {
        console.error('載入更多失敗:', err);
    } finally {
        state.isLoadingMore = false;
        dom.btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';
        updateNavigation();
    }
}

// === 標題編輯功能 ===

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

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

function startEditTitle() {
    const { state } = window.SearchCore;
    const container = document.getElementById('titleContainer');
    const span = document.getElementById('resultTitle');
    const currentText = span.textContent;

    const translateBtn = document.getElementById('translateBtn');
    const translateSpinner = document.getElementById('translateSpinner');
    translateBtn.classList.add('d-none');
    translateSpinner.classList.add('d-none');

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

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') confirmEditTitle();
        else if (e.key === 'Escape') cancelEditTitle();
    });
}

function confirmEditTitle() {
    const { state } = window.SearchCore;
    const input = document.getElementById('editTitleInput');
    const newValue = input.value.trim();

    const file = state.fileList[state.currentFileIndex];
    if (file?.searchResults?.[state.currentIndex]) {
        file.searchResults[state.currentIndex].title = newValue;
        file.searchResults[state.currentIndex]._titleEdited = true;
    }

    restoreTitleDisplay(newValue, true);
    window.SearchCore.saveState();
}

function cancelEditTitle() {
    const { state } = window.SearchCore;
    const file = state.fileList[state.currentFileIndex];
    const result = file?.searchResults?.[state.currentIndex];
    const originalText = result?.title || '-';
    const isEdited = result?._titleEdited || false;
    restoreTitleDisplay(originalText, isEdited);
}

function restoreTitleDisplay(text, edited) {
    const { state } = window.SearchCore;
    const container = document.getElementById('titleContainer');
    const file = state.fileList[state.currentFileIndex];
    const result = file?.searchResults?.[state.currentIndex];
    const chineseTitle = file?.chineseTitle;
    const translatedTitle = result?.translated_title;

    const appConfig = state.appConfig;
    const shouldShowTranslateBtn = appConfig?.translate?.enabled &&
        !chineseTitle && !translatedTitle && text && text !== '-' &&
        window.SearchCore.hasJapanese(text);

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

function confirmEditChineseTitle() {
    const { state } = window.SearchCore;
    const input = document.getElementById('editChineseTitleInput');
    const newValue = input.value.trim();

    const file = state.fileList[state.currentFileIndex];
    if (file?.searchResults?.[state.currentIndex]) {
        file.searchResults[state.currentIndex].translated_title = newValue;
        file.searchResults[state.currentIndex]._chineseTitleEdited = true;
    }

    restoreChineseTitleDisplay(newValue, true);
    window.SearchCore.saveState();
}

function cancelEditChineseTitle() {
    const { state } = window.SearchCore;
    const file = state.fileList[state.currentFileIndex];
    const result = file?.searchResults?.[state.currentIndex];
    const translatedTitle = result?.translated_title;
    const chineseTitle = file?.chineseTitle;
    const originalText = translatedTitle || chineseTitle || '-';
    const isEdited = result?._chineseTitleEdited || false;
    restoreChineseTitleDisplay(originalText, isEdited);
}

function restoreChineseTitleDisplay(text, edited) {
    const container = document.getElementById('chineseTitleContainer');
    container.innerHTML = `
        <span id="resultChineseTitle" class="text-success" style="flex:1;">${escapeHtml(text)}</span>
        <button id="editChineseTitleBtn" class="btn btn-sm btn-link p-0 ms-1" onclick="startEditChineseTitle()" title="編輯中文片名">
            <i class="bi ${edited ? 'bi-pencil-fill text-success' : 'bi-pencil text-muted'}"></i>
        </button>
    `;
}

// === 翻譯顯示 ===

function updateChineseTitleDisplay(text, mode) {
    const chineseTitleRow = document.getElementById('chineseTitleRow');
    const chineseTitleLabel = document.getElementById('chineseTitleLabel');
    const chineseTitleEl = document.getElementById('resultChineseTitle');

    if (text) {
        chineseTitleEl.textContent = text;
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

function showTranslateError(error) {
    const chineseTitleLabel = document.getElementById('chineseTitleLabel');
    const originalText = chineseTitleLabel.textContent;
    chineseTitleLabel.innerHTML = `中文片名 <span class="text-danger">(${error})</span>`;
    setTimeout(() => {
        if (chineseTitleLabel.innerHTML.includes(error)) {
            chineseTitleLabel.textContent = originalText;
        }
    }, 3000);
}

/**
 * 更新翻譯標題（供漸進式翻譯調用）
 *
 * 用途：當後台批次翻譯完成時，如果用戶正在查看該片，立即更新 UI
 *
 * @param {string} translatedTitle - 翻譯後的標題
 */
function updateTranslatedTitle(translatedTitle) {
    // 更新中文標題顯示
    const chineseTitleRow = document.getElementById('chineseTitleRow');
    const chineseTitleLabel = document.getElementById('chineseTitleLabel');
    const chineseTitleEl = document.getElementById('resultChineseTitle');

    if (chineseTitleEl && translatedTitle) {
        chineseTitleEl.textContent = translatedTitle;
        chineseTitleLabel.textContent = '中文片名 (AI)';
        chineseTitleRow.classList.remove('d-none');
    }

    // 隱藏翻譯按鈕（已有翻譯）
    const translateBtn = document.getElementById('translateBtn');
    if (translateBtn) {
        translateBtn.classList.add('d-none');
    }

    // 隱藏載入中指示器
    const translateSpinner = document.getElementById('translateSpinner');
    if (translateSpinner) {
        translateSpinner.classList.add('d-none');
    }
}

/**
 * 🆕 顯示批次翻譯中狀態
 */
function showBatchTranslatingState() {
    const translateBtn = document.getElementById('translateBtn');
    const translateSpinner = document.getElementById('translateSpinner');

    if (translateBtn && translateSpinner) {
        translateBtn.classList.add('d-none');
        translateSpinner.classList.remove('d-none');
    }
}

// === Gallery 視圖 ===

/**
 * 顯示 Gallery 視圖
 * @param {string} url - Gallery HTML 的 URL
 */
function showGallery(url) {
    const { galleryView, galleryFrame, btnBackToDetail } = window.SearchCore.dom;

    // 設定 iframe src
    galleryFrame.src = url;

    // 顯示 Gallery 容器
    galleryView.classList.remove('d-none');

    // 顯示返回按鈕（在搜尋框中）
    if (btnBackToDetail) {
        btnBackToDetail.classList.remove('d-none');
    }

    // 監聽 iframe 的 postMessage
    window.addEventListener('message', handleGalleryMessage);

    console.log('[Gallery] Showing gallery view:', url);
}

/**
 * 隱藏 Gallery 視圖，返回詳細資料卡
 */
function hideGallery(showDetail = true) {
    const { galleryView, galleryFrame, btnBackToDetail } = window.SearchCore.dom;

    // 隱藏 Gallery 容器
    galleryView.classList.add('d-none');

    // 隱藏返回按鈕（在搜尋框中）
    if (btnBackToDetail) {
        btnBackToDetail.classList.add('d-none');
    }

    // 清空 iframe src（釋放資源）
    galleryFrame.src = '';

    // 移除 postMessage 監聽
    window.removeEventListener('message', handleGalleryMessage);

    // 只有需要時才顯示詳細資料卡
    if (showDetail) {
        const { searchResults, currentIndex } = window.SearchCore.state;
        if (searchResults.length > 0) {
            displayResult(searchResults[currentIndex]);
            updateNavigation();
            showState('result');
        } else {
            showState('empty');
        }
    }

    console.log('[Gallery] Hiding gallery view');
}

/**
 * 處理來自 Gallery iframe 的 postMessage
 * @param {MessageEvent} event
 */
function handleGalleryMessage(event) {
    // 安全檢查：確保訊息來自我們的 iframe
    if (!event.origin.includes(window.location.origin)) {
        return;
    }

    const message = event.data;

    // 處理「點擊影片」事件
    if (message.type === 'videoClick') {
        console.log('[Gallery] Video clicked:', message.number);

        // 在 searchResults 中找到對應的影片
        const { searchResults } = window.SearchCore.state;
        const index = searchResults.findIndex(r => r.number === message.number);

        if (index !== -1) {
            // 切換到該影片的詳細資料
            window.SearchCore.state.currentIndex = index;
            hideGallery();
        } else {
            console.warn('[Gallery] Video not found in search results:', message.number);
        }
    }

    // 處理「查看更多」事件
    if (message.type === 'loadMore') {
        console.log('[Gallery] Load more requested');

        // 關閉 Gallery，切換到大圖模式
        hideGallery();

        // 用戶可以用 ← → 箭頭瀏覽，到第 20 片按 → 會自動載入 21-40
    }
}

// === 暴露介面 ===
window.SearchUI = {
    showState,
    displayResult,
    displayCoverError,
    preloadImages,
    updateNavigation,
    navigateResult,
    loadMoreResults,
    escapeHtml,
    updateEditButtonState,
    updateChineseTitleDisplay,
    showTranslateError,
    updateTranslatedTitle,
    // 🆕 新增
    showBatchTranslatingState,
    showGallery,
    hideGallery
};

// 全域函數（onclick 用）
window.startEditTitle = startEditTitle;
window.confirmEditTitle = confirmEditTitle;
window.cancelEditTitle = cancelEditTitle;
window.startEditChineseTitle = startEditChineseTitle;
window.confirmEditChineseTitle = confirmEditChineseTitle;
window.cancelEditChineseTitle = cancelEditChineseTitle;
