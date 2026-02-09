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
    btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
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

                // T1c: 更新 searchResults，Alpine template 自動反應
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

    // 原有 .hidden 操作（保留，防 FOUC + 向後相容）
    dom.emptyState.classList.add('hidden');
    dom.loadingState.classList.add('hidden');
    dom.resultCard.classList.add('hidden');
    dom.errorState.classList.add('hidden');

    if (state === 'empty') dom.emptyState.classList.remove('hidden');
    else if (state === 'loading') dom.loadingState.classList.remove('hidden');
    else if (state === 'result') dom.resultCard.classList.remove('hidden');
    else if (state === 'error') dom.errorState.classList.remove('hidden');

    // T1a: 同步 Alpine pageState
    const el = document.querySelector('.search-container[x-data]');
    if (el && el._x_dataStack) {
        Alpine.$data(el).pageState = state;
    }
}

// === 結果顯示 ===
// T1c: displayResult 遷移至 Alpine（已由 template binding 接管）
// 保留 bridge stub 供 file.js 使用（T1d 才完全移除）

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

// T1c: updateNavigation 已遷移至 Alpine computed（showNavigation, navIndicatorText, canGoPrev, canGoNext）
// Bridge stub 在 window.SearchUI 中提供 no-op 給 file.js

// === 標題編輯功能 ===
// T1c: 所有編輯函數已遷移至 Alpine state.js
// 保留 escapeHtml 供其他模組使用

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// T1c: Removed - updateEditButtonState, startEditTitle, confirmEditTitle, cancelEditTitle, restoreTitleDisplay
// T1c: Removed - startEditChineseTitle, confirmEditChineseTitle, cancelEditChineseTitle, restoreChineseTitleDisplay
// T1c: Removed - updateChineseTitleDisplay, showTranslateError, updateTranslatedTitle, showBatchTranslatingState

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
    galleryView.classList.remove('hidden');

    // 顯示返回按鈕（在搜尋框中）
    if (btnBackToDetail) {
        btnBackToDetail.classList.remove('hidden');
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
    galleryView.classList.add('hidden');

    // 隱藏返回按鈕（在搜尋框中）
    if (btnBackToDetail) {
        btnBackToDetail.classList.add('hidden');
    }

    // 清空 iframe src（釋放資源）
    galleryFrame.src = '';

    // 移除 postMessage 監聽
    window.removeEventListener('message', handleGalleryMessage);

    // 只有需要時才顯示詳細資料卡
    if (showDetail) {
        const { searchResults, currentIndex } = window.SearchCore.state;
        if (searchResults.length > 0) {
            // T1c: Alpine template自動顯示，只需 showState
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
// T1c: 所有本地標記函數已遷移至 Alpine state.js
// Removed: showLocalBadge, copyLocalPath, showToast, hideLocalBadge, updateLocalBadges
// Note: updateLocalBadges still called by core.js checkLocalStatus(), but now no-ops via Alpine reactivity

// === 用戶標籤功能 ===
// T1c: 所有標籤函數已遷移至 Alpine state.js
// Removed: showAddTagInput, confirmAddTag, cancelAddTag, addUserTag, removeUserTag

// === 暴露介面 ===
window.SearchUI = {
    showState,
    // T1c: Bridge stub for file.js (until T1d)
    displayResult: function(data) {
        // file.js 呼叫此函數時，只需確保 Alpine state 有正確的 searchResults/currentIndex
        // Alpine template binding 會自動顯示
        // 不需要做任何事，因為 file.js 在呼叫 displayResult 前已經設定了 coreState.searchResults[idx]
    },
    updateNavigation: function() {
        // no-op — Alpine computed (showNavigation, navIndicatorText, canGoPrev, canGoNext) 自動處理
    },
    preloadImages,
    navigateResult: null,  // 在 state.js setupBridgeLayer() 設定
    escapeHtml,
    showGallery,
    hideGallery,
    loadSourceConfig,
    getSourceOrder,
    getSourceNames,
    // T1c: 以下函數被移除（已遷移到 Alpine），但保留 stub 供 core.js 使用
    updateLocalBadges: function() {
        // no-op — Alpine reactivity automatically updates badge
    }
};

// 全域函數（onclick 用）
// T1c: 所有編輯/標籤函數已在 state.js setupBridgeLayer() 中設定
window.switchSource = switchSource;
