/**
 * SearchUI - UI 模組
 * 狀態顯示、結果展示、導航、標題編輯
 */

// === 版本切換功能 ===

/**
 * 來源順序（從後端 API 載入，此為預設值）
 */
let SOURCE_ORDER = ['javbus', 'jav321', 'javdb', 'fc2', 'avsox'];

/**
 * 來源顯示名稱對照
 */
let SOURCE_NAMES = {
    'javbus': 'JavBus',
    'jav321': 'Jav321',
    'javdb': 'JavDB',
    'fc2': 'FC2',
    'avsox': 'AVSOX'
};

/**
 * 從後端載入來源配置
 * @returns {Promise<void>}
 */
async function loadSourceConfig() {
    try {
        const response = await fetch('/api/search/sources');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // 更新來源順序
        if (data.order && Array.isArray(data.order)) {
            SOURCE_ORDER = data.order;
            console.log('[SourceConfig] 已從 API 載入 SOURCE_ORDER:', SOURCE_ORDER);
        }

        // 從 sources 更新顯示名稱
        if (data.sources && Array.isArray(data.sources)) {
            const newNames = {};
            for (const source of data.sources) {
                if (source.id && source.id !== 'auto') {
                    newNames[source.id] = source.name;
                }
            }
            if (Object.keys(newNames).length > 0) {
                SOURCE_NAMES = newNames;
            }
        }
    } catch (error) {
        console.warn('[SourceConfig] 載入失敗，使用預設值:', error.message);
        // 保留預設值
    }
}

/**
 * 取得當前來源順序
 * @returns {string[]}
 */
function getSourceOrder() {
    return SOURCE_ORDER;
}

/**
 * 取得來源顯示名稱
 * @returns {Object}
 */
function getSourceNames() {
    return SOURCE_NAMES;
}

/**
 * 切換狀態結構（每個番號獨立）
 * key: 番號, value: { sourceIdx, variantIdx, cache: { source: [...variants] | [] | undefined } }
 */
const switchStateMap = new Map();

/**
 * 取得或初始化某番號的切換狀態
 */
function getSwitchState(number) {
    if (!switchStateMap.has(number)) {
        switchStateMap.set(number, {
            sourceIdx: 0,
            variantIdx: 0,
            cache: {}  // { 'javbus': [...], 'jav321': [], ... }
        });
    }
    return switchStateMap.get(number);
}

/**
 * 推進位置（同站下一版本 → 下一來源）
 * @returns {boolean} 是否切換了來源
 */
function advancePosition(state) {
    const currentSource = SOURCE_ORDER[state.sourceIdx];
    const variants = state.cache[currentSource] || [];

    // 同站有下一版本
    if (state.variantIdx < variants.length - 1) {
        state.variantIdx++;
        return false;  // 未切換來源
    }

    // 切換到下一來源
    state.sourceIdx = (state.sourceIdx + 1) % SOURCE_ORDER.length;
    state.variantIdx = 0;
    return true;  // 切換了來源
}

/**
 * 懶加載：確保指定來源已查詢過（支援多版本）
 */
async function ensureCached(state, number) {
    const source = SOURCE_ORDER[state.sourceIdx];

    // undefined = 還沒查，[] = 查過沒資料，[...] = 有資料
    if (state.cache[source] !== undefined) {
        return;
    }

    console.log(`[SwitchSource] 懶加載查詢: ${source} - ${number}`);

    try {
        const resp = await fetch(`/api/search?q=${encodeURIComponent(number)}&mode=exact&source=${source}`);
        const json = await resp.json();

        if (json.success && json.data && json.data.length > 0) {
            const firstResult = json.data[0];
            const allVariantIds = firstResult._all_variant_ids || [];
            const firstVariantId = firstResult._variant_id;

            if (allVariantIds.length <= 1) {
                // 只有 1 個版本
                state.cache[source] = [{ ...firstResult, _source: source }];
            } else {
                // 多版本：按 allVariantIds 順序獲取
                const variants = [];

                for (const variantId of allVariantIds) {
                    if (variantId === firstVariantId) {
                        // 已有的結果，直接使用
                        variants.push({ ...firstResult, _source: source });
                    } else {
                        // 需要額外獲取
                        try {
                            const vResp = await fetch(`/api/search?q=${encodeURIComponent(number)}&variant_id=${encodeURIComponent(variantId)}`);
                            const vJson = await vResp.json();
                            if (vJson.success && vJson.data?.[0]) {
                                variants.push({ ...vJson.data[0], _source: source });
                            }
                        } catch (e) {
                            console.warn(`[SwitchSource] 獲取版本 ${variantId} 失敗:`, e);
                        }
                    }
                }

                state.cache[source] = variants.length > 0 ? variants : [{ ...firstResult, _source: source }];
                console.log(`[SwitchSource] ${source} 共 ${variants.length} 個版本`);
            }
        } else {
            // 沒資料
            state.cache[source] = [];
        }
    } catch (err) {
        console.error(`[SwitchSource] 查詢 ${source} 失敗:`, err);
        state.cache[source] = [];
    }
}

/**
 * 顯示 Toast 提示「來自 {source}」（在 ⟳ 按鈕右側）
 */
function showSourceToast(source) {
    const name = SOURCE_NAMES[source] || source;
    const btn = document.getElementById('switchSourceBtn');

    // 移除舊的 toast
    const oldToast = document.getElementById('sourceToast');
    if (oldToast) oldToast.remove();

    // 建立 Toast
    const toast = document.createElement('span');
    toast.id = 'sourceToast';
    toast.className = 'source-toast-inline';
    toast.textContent = `來自 ${name}`;

    // 插入到按鈕右側
    if (btn && btn.parentNode) {
        btn.parentNode.insertBefore(toast, btn.nextSibling);
    } else {
        document.body.appendChild(toast);
    }

    // 動畫顯示
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    // 2 秒後消失
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

/**
 * 按鈕抖動效果（無其他版本時）
 */
function shakeButton(btn) {
    btn.classList.add('shake');
    setTimeout(() => btn.classList.remove('shake'), 300);
}

/**
 * 多來源循環切換
 *
 * 邏輯流程：
 * 1. 先在同站搜尋其他版本
 * 2. 同站沒有 → 去下一個來源搜尋
 * 3. 來源循環：javbus → jav321 → javdb → javbus...
 * 4. 自動跳過沒有資料的來源
 * 5. 跨來源切換時顯示 Toast
 */
async function switchSource() {
    const btn = document.getElementById('switchSourceBtn');
    if (!btn) return;

    const number = btn.dataset.number;
    if (!number) {
        console.warn('[SwitchSource] 無番號資訊');
        return;
    }

    // 取得切換狀態
    const state = getSwitchState(number);

    // 記錄起始位置（用於檢測循環回起點）
    const startPos = `${state.sourceIdx}:${state.variantIdx}`;

    // 顯示載入中
    const originalHtml = btn.innerHTML;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    btn.disabled = true;

    try {
        // 先確保當前來源已快取（避免第一次按 ⟳ 跳過當前來源）
        await ensureCached(state, number);

        while (true) {
            // 推進位置
            const changedSource = advancePosition(state);

            // 檢查是否循環回起點
            const currentPos = `${state.sourceIdx}:${state.variantIdx}`;
            if (currentPos === startPos) {
                console.log('[SwitchSource] 循環完畢，回到起點');
                shakeButton(btn);  // 抖動提示無其他版本
                return;
            }

            // 懶加載查詢
            await ensureCached(state, number);

            // 取得當前來源的版本列表
            const source = SOURCE_ORDER[state.sourceIdx];
            const variants = state.cache[source] || [];

            // 檢查是否有資料
            if (variants.length > state.variantIdx) {
                const variant = variants[state.variantIdx];

                // 更新顯示
                displayResult(variant);
                updateNavigation();

                // 更新 searchResults
                const { state: coreState } = window.SearchCore;
                if (coreState.searchResults.length > 0) {
                    coreState.searchResults[coreState.currentIndex] = variant;
                }

                // 更新按鈕資料
                btn.dataset.currentVariantId = variant._variant_id || '';

                // 跨來源時顯示 Toast
                if (changedSource) {
                    showSourceToast(source);
                }

                // 保存狀態
                window.SearchCore.saveState();

                console.log(`[SwitchSource] 切換到 ${source} 第 ${state.variantIdx + 1} 版`);
                return;
            }

            // 沒資料，繼續下一個位置
            console.log(`[SwitchSource] ${source} 無資料，繼續...`);
        }
    } catch (err) {
        console.error('[SwitchSource] 切換失敗:', err);
    } finally {
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    }
}

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

    // 標籤（全部顯示）+ 字幕標籤 + 用戶標籤
    const tagsContainer = document.getElementById('resultTags');
    const tags = data.tags || [];
    const userTags = data.user_tags || [];
    let tagsHtml = '';

    if (hasSubtitle) {
        tagsHtml += '<span class="badge tag-badge subtitle">中文字幕</span>';
    }

    if (tags.length > 0) {
        tagsHtml += tags.map(tag =>
            `<span class="badge tag-badge">${escapeHtml(tag)}</span>`
        ).join('');
    }

    // 用戶標籤（可刪除）
    if (userTags.length > 0) {
        tagsHtml += userTags.map(tag =>
            `<span class="badge tag-badge user-tag">${escapeHtml(tag)} <span class="tag-remove" onclick="removeUserTag('${escapeHtml(tag)}')">&times;</span></span>`
        ).join('');
    }

    // 新增按鈕
    tagsHtml += '<button class="btn btn-sm tag-add-btn" onclick="showAddTagInput()" title="新增標籤">+</button>';

    tagsContainer.innerHTML = tagsHtml;

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

    // 更新切換版本按鈕的資料
    const switchSourceBtn = document.getElementById('switchSourceBtn');
    if (switchSourceBtn) {
        const allVariantIds = data._all_variant_ids || [];
        const currentVariantId = data._variant_id || '';

        // 更新按鈕資料
        switchSourceBtn.dataset.allVariantIds = JSON.stringify(allVariantIds);
        switchSourceBtn.dataset.currentVariantId = currentVariantId;
        switchSourceBtn.dataset.number = data.number || '';

        // 更新 title
        if (allVariantIds.length > 1) {
            const currentIndex = allVariantIds.indexOf(currentVariantId);
            switchSourceBtn.title = `切換版本 (${currentIndex + 1}/${allVariantIds.length})`;
        } else {
            switchSourceBtn.title = '切換版本';
        }
    }

    // 更新本地標記
    if (data._localStatus) {
        showLocalBadge(data._localStatus);
    } else {
        hideLocalBadge();
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
        <textarea id="editTitleInput" class="form-control form-control-sm" rows="3" style="flex:1; min-width:0; resize:none;">${escapeHtml(currentText)}</textarea>
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
        <textarea id="editChineseTitleInput" class="form-control form-control-sm text-success" rows="2" style="flex:1; min-width:0; resize:none;">${escapeHtml(currentText)}</textarea>
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

// === 本地標記功能 ===

/**
 * 顯示本地標記 badge
 * @param {Object} localStatus - 本地狀態 { exists: true, count: 2, paths: [...] }
 */
function showLocalBadge(localStatus) {
    const badge = document.getElementById('localBadge');
    if (!badge) return;

    if (localStatus && localStatus.exists) {
        badge.classList.remove('d-none');

        // 儲存路徑供點擊複製用
        badge.dataset.paths = JSON.stringify(localStatus.paths || []);

        if (localStatus.count > 1) {
            badge.title = `本地已有 ${localStatus.count} 個版本（點擊複製路徑）`;
        } else {
            badge.title = '本地已有（點擊複製路徑）';
        }

        // 設定點擊事件（只設定一次）
        if (!badge.dataset.clickBound) {
            badge.addEventListener('click', copyLocalPath);
            badge.dataset.clickBound = 'true';
        }
    } else {
        badge.classList.add('d-none');
    }
}

/**
 * 複製本地路徑到剪貼簿
 */
function copyLocalPath() {
    const badge = document.getElementById('localBadge');
    if (!badge) return;

    try {
        const paths = JSON.parse(badge.dataset.paths || '[]');
        if (paths.length === 0) return;

        // 複製第一個路徑（如果有多個，用換行分隔全部）
        const textToCopy = paths.length === 1 ? paths[0] : paths.join('\n');

        navigator.clipboard.writeText(textToCopy).then(() => {
            // 顯示成功提示
            const msg = paths.length === 1 ? '已複製路徑' : `已複製 ${paths.length} 個路徑`;
            showToast(msg, 'success');
        }).catch(err => {
            console.error('複製失敗:', err);
            showToast('複製失敗', 'danger');
        });
    } catch (err) {
        console.error('解析路徑失敗:', err);
    }
}

/**
 * 顯示 Toast 提示
 */
function showToast(message, type = 'info') {
    // 檢查是否有現有的 toast 容器
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    container.appendChild(toast);

    const bsToast = new bootstrap.Toast(toast, { delay: 2000 });
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

/**
 * 隱藏本地標記 badge
 */
function hideLocalBadge() {
    const badge = document.getElementById('localBadge');
    if (badge) {
        badge.classList.add('d-none');
    }
}

/**
 * 更新搜尋結果的本地標記（批次更新）
 * 在 checkLocalStatus() 完成後調用
 */
function updateLocalBadges() {
    const { state } = window.SearchCore;
    const currentResult = state.searchResults[state.currentIndex];

    if (currentResult && currentResult._localStatus) {
        showLocalBadge(currentResult._localStatus);
    } else {
        hideLocalBadge();
    }
}

// === 用戶標籤功能 ===

/**
 * 顯示新增標籤輸入框
 */
function showAddTagInput() {
    const container = document.getElementById('resultTags');
    const addBtn = container.querySelector('.tag-add-btn');
    if (!addBtn) return;

    // 建立輸入框
    const inputWrapper = document.createElement('span');
    inputWrapper.className = 'tag-input-wrapper';
    inputWrapper.innerHTML = `
        <input type="text" class="tag-input" placeholder="標籤名稱" maxlength="20">
        <button class="btn btn-sm tag-confirm" onclick="confirmAddTag()" title="確認">✓</button>
        <button class="btn btn-sm tag-cancel" onclick="cancelAddTag()" title="取消">✕</button>
    `;

    // 替換按鈕為輸入框
    addBtn.replaceWith(inputWrapper);

    // 自動聚焦
    const input = inputWrapper.querySelector('.tag-input');
    input.focus();

    // Enter 確認，Escape 取消
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') confirmAddTag();
        else if (e.key === 'Escape') cancelAddTag();
    });
}

/**
 * 確認新增標籤
 */
function confirmAddTag() {
    const input = document.querySelector('.tag-input');
    if (!input) return;

    const tag = input.value.trim();
    if (tag) {
        addUserTag(tag);
    } else {
        cancelAddTag();
    }
}

/**
 * 取消新增標籤
 */
function cancelAddTag() {
    const { state } = window.SearchCore;
    const currentResult = state.searchResults[state.currentIndex];
    if (currentResult) {
        displayResult(currentResult);
    }
}

/**
 * 新增用戶標籤
 */
function addUserTag(tag) {
    const { state } = window.SearchCore;
    const currentResult = state.searchResults[state.currentIndex];
    if (!currentResult) return;

    // 初始化 user_tags
    if (!currentResult.user_tags) {
        currentResult.user_tags = [];
    }

    // 避免重複
    if (currentResult.user_tags.includes(tag)) {
        cancelAddTag();
        return;
    }

    currentResult.user_tags.push(tag);
    displayResult(currentResult);
    window.SearchCore.saveState();
}

/**
 * 移除用戶標籤
 */
function removeUserTag(tag) {
    const { state } = window.SearchCore;
    const currentResult = state.searchResults[state.currentIndex];
    if (!currentResult || !currentResult.user_tags) return;

    const idx = currentResult.user_tags.indexOf(tag);
    if (idx > -1) {
        currentResult.user_tags.splice(idx, 1);
        displayResult(currentResult);
        window.SearchCore.saveState();
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
    hideGallery,
    loadSourceConfig,
    getSourceOrder,
    getSourceNames,
    // 本地標記功能
    showLocalBadge,
    hideLocalBadge,
    updateLocalBadges
};

// 全域函數（onclick 用）
window.startEditTitle = startEditTitle;
window.confirmEditTitle = confirmEditTitle;
window.cancelEditTitle = cancelEditTitle;
window.startEditChineseTitle = startEditChineseTitle;
window.confirmEditChineseTitle = confirmEditChineseTitle;
window.cancelEditChineseTitle = cancelEditChineseTitle;
window.switchSource = switchSource;
// 用戶標籤
window.showAddTagInput = showAddTagInput;
window.confirmAddTag = confirmAddTag;
window.cancelAddTag = cancelAddTag;
window.addUserTag = addUserTag;
window.removeUserTag = removeUserTag;
