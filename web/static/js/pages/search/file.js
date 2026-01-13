/**
 * SearchFile - 檔案模組
 * 檔案列表、批次操作、番號解析、拖拽處理
 */

// === 檔名處理工具函數 ===

/**
 * 檢查檔名是否包含字幕標記
 */
function checkSubtitle(filename) {
    if (!filename) return false;
    const upper = filename.toUpperCase();

    const patterns = ['-C', '_C'];
    for (const p of patterns) {
        const idx = upper.indexOf(p);
        if (idx !== -1) {
            const nextIdx = idx + p.length;
            if (nextIdx >= upper.length || !/[A-Z0-9]/i.test(upper[nextIdx])) {
                return true;
            }
        }
    }

    const chinesePatterns = ['中文字幕', '字幕', '中字', '[中字]', '【中字】'];
    for (const p of chinesePatterns) {
        if (filename.includes(p)) return true;
    }

    return false;
}

/**
 * 檢查文字是否包含中文
 */
function hasChinese(text) {
    if (!text) return false;
    return /[\u4e00-\u9fff]/.test(text);
}

/**
 * 清除無意義的來源後綴
 */
function cleanSourceSuffix(text) {
    const patterns = [
        /\s*-\s*Jable\s*TV.*$/i,
        /\s*-\s*Jable.*$/i,
        /\s*-\s*Hayav\s*AV.*$/i,
        /\s*-\s*Hayav.*$/i,
        /\s*-\s*MissAV.*$/i,
        /\s*-\s*J片.*$/i,
        /\s*-\s*免費.*$/i,
        /\s*-\s*Netflav.*$/i,
        /\s*-\s*AV看到飽.*$/i,
        /\s*-\s*Free\s*Japan.*$/i,
        /\s*-\s*Streaming.*$/i,
        /\s*-\s*[A-Za-z]{1,3}\.?$/,
        /\s*-\s*$/,
        /\s+-\d+$/,
    ];
    for (const p of patterns) {
        text = text.replace(p, '');
    }
    return text.trim();
}

/**
 * 從檔名提取中文片名
 */
function extractChineseTitle(filename, number, actors = []) {
    if (!filename) return null;

    let name = filename.replace(/\.[^.]+$/, '');

    if (number) {
        const escapedNum = number.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
        name = name.replace(new RegExp(`\\[?${escapedNum}\\]?\\s*`, 'gi'), '');
    }
    name = name.replace(/\[?[A-Za-z]{2,6}-?\d{3,5}\]?\s*/g, '');

    name = cleanSourceSuffix(name);
    name = name.replace(/\s+/g, ' ').trim();
    name = name.replace(/^中文字幕\s*/, '');

    if (actors && actors.length > 0) {
        for (const actor of actors) {
            const escapedActor = actor.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
            name = name.replace(new RegExp(`^${escapedActor}\\s*-\\s*`, ''), '');
            name = name.replace(new RegExp(`\\s+${escapedActor}$`, ''), '');
        }
    }

    name = name.replace(/\s+[\u4e00-\u9fff]{2,4}$/, '');
    name = name.trim();

    if (name && hasChinese(name) && !window.SearchCore.hasJapanese(name)) {
        return name;
    }
    return null;
}

/**
 * 從檔名提取番號
 */
function extractNumber(filename) {
    const basename = filename.split(/[/\\]/).pop().replace(/\.[^.]+$/, '');

    const patterns = [
        /\b([A-Z]{1,5})-(\d{3,5})\b/i,
        /\b([A-Z]{2,5})(\d{3,5})\b/i,
        /\b(FC2-PPV)-(\d{5,7})\b/i,
    ];

    for (const pattern of patterns) {
        const match = basename.match(pattern);
        if (match) {
            const prefix = match[1].toUpperCase();
            if (prefix === 'FC2-PPV') {
                return `FC2-PPV-${match[2]}`;
            }
            return `${prefix}-${match[2]}`;
        }
    }
    return null;
}

/**
 * 格式化番號（標準化格式）
 */
function formatNumber(input) {
    if (!input) return null;
    const match = input.match(/([A-Z]{1,5})-?(\d{3,7})/i);
    if (match) {
        return `${match[1].toUpperCase()}-${match[2]}`;
    }
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
    const { state } = window.SearchCore;
    const file = state.fileList[index];
    if (!file) return;

    const number = prompt('請輸入番號（例如：T28-650）', '');
    if (!number || !number.trim()) return;

    const formatted = formatNumber(number.trim());
    file.number = formatted;
    file.searched = false;
    file.searchResults = [];

    switchToFile(index, 'first', true);
}

/**
 * 從列表中移除檔案
 */
function removeFile(index) {
    const { state } = window.SearchCore;
    if (index < 0 || index >= state.fileList.length) return;

    state.fileList.splice(index, 1);

    if (state.fileList.length === 0) {
        window.SearchCore.clearAll();
        return;
    }

    if (state.currentFileIndex >= state.fileList.length) {
        state.currentFileIndex = state.fileList.length - 1;
    } else if (state.currentFileIndex > index) {
        state.currentFileIndex--;
    }

    renderFileList();
    if (state.fileList.length > 0) {
        switchToFile(state.currentFileIndex, 'first', false);
    }
    window.SearchCore.saveState();
}

// === 列表渲染 ===

function renderFileList() {
    const { state, dom } = window.SearchCore;

    dom.fileListSection.classList.toggle('d-none', state.fileList.length === 0);
    dom.fileListContainer.innerHTML = '';
    dom.fileCountText.textContent = `檔案 ${state.currentFileIndex + 1}/${state.fileList.length}`;

    dom.btnScrapeAll.classList.remove('d-none');

    state.fileList.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'file-item' + (index === state.currentFileIndex ? ' active' : '');

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

        item.addEventListener('click', (e) => {
            if (!e.target.closest('.btn-scrape-single') &&
                !e.target.closest('.btn-enter-number') &&
                !e.target.closest('.btn-remove-file')) {
                switchToFile(index, 'first');
            }
        });

        const removeBtn = item.querySelector('.btn-remove-file');
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeFile(index);
        });

        if (canScrape) {
            const btn = item.querySelector('.btn-scrape-single');
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                scrapeSingle(index);
            });
        }

        if (needsNumber) {
            const btn = item.querySelector('.btn-enter-number');
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                enterNumber(index);
            });
        }

        dom.fileListContainer.appendChild(item);
    });
}

function renderSearchResultsList() {
    const { state, dom } = window.SearchCore;

    if (state.searchResults.length === 0) {
        dom.fileListSection.classList.add('d-none');
        return;
    }

    dom.fileListSection.classList.remove('d-none');
    dom.fileListContainer.innerHTML = '';

    const countText = state.hasMoreResults ? `${state.searchResults.length}+` : state.searchResults.length;
    dom.fileCountText.textContent = `搜尋結果 (${countText})`;

    dom.btnScrapeAll.classList.add('d-none');

    state.searchResults.forEach((result, index) => {
        const item = document.createElement('div');
        item.className = 'file-item' + (index === state.currentIndex ? ' active' : '');

        const number = result.number || '';
        const actors = (result.actors || []).slice(0, 2).join(', ') || '-';
        const title = result.title || '';

        item.innerHTML = `
            <span style="flex-shrink:0; font-weight:500; color:#0d6efd; min-width:90px;">${number}</span>
            <span style="flex-shrink:0; min-width:80px; color:#6c757d;">${actors}</span>
            <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${title}</span>
        `;
        item.addEventListener('click', () => switchToSearchResult(index));
        dom.fileListContainer.appendChild(item);
    });
}

// === 切換功能 ===

function switchToSearchResult(index) {
    const { state } = window.SearchCore;
    if (index < 0 || index >= state.searchResults.length) return;
    state.currentIndex = index;
    window.SearchUI.displayResult(state.searchResults[state.currentIndex]);
    window.SearchUI.updateNavigation();
    renderSearchResultsList();
}

async function switchToFile(index, position = 'first', showFullLoading = false) {
    const { state } = window.SearchCore;
    if (index < 0 || index >= state.fileList.length) return;

    state.currentFileIndex = index;
    const file = state.fileList[index];

    if (!file.number) {
        renderFileList();
        state.searchResults = [];
        state.hasMoreResults = false;
        state.currentIndex = 0;
        window.SearchUI.displayCoverError(`無法識別番號: ${file.filename}`);
        window.SearchUI.showState('result');
        window.SearchUI.updateNavigation();
        return;
    }

    if (!file.searched) {
        await searchForFile(file, position, showFullLoading);
    } else if (file.searchResults && file.searchResults.length > 0) {
        renderFileList();
        state.searchResults = file.searchResults;
        state.hasMoreResults = file.hasMoreResults || false;
        state.currentIndex = position === 'last' ? state.searchResults.length - 1 : 0;
        window.SearchUI.displayResult(state.searchResults[state.currentIndex]);
        window.SearchUI.updateNavigation();
        window.SearchUI.showState('result');
    } else {
        renderFileList();
        state.searchResults = [];
        state.hasMoreResults = false;
        state.currentIndex = 0;
        window.SearchUI.displayCoverError(`找不到 ${file.number} 的資料`);
        window.SearchUI.showState('result');
        window.SearchUI.updateNavigation();
    }
}

function searchForFile(file, position = 'first', showFullLoading = false) {
    const { state, dom } = window.SearchCore;

    return new Promise((resolve) => {
        const isGoingNext = position === 'first';
        const targetBtn = isGoingNext ? dom.btnNext : dom.btnPrev;
        const targetBtnIcon = isGoingNext ? '<i class="bi bi-chevron-right"></i>' : '<i class="bi bi-chevron-left"></i>';

        state.isSearchingFile = true;

        if (showFullLoading) {
            window.SearchUI.showState('loading');
            window.SearchCore.initProgress(file.number);
        } else {
            targetBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
            targetBtn.disabled = true;
        }

        const eventSource = new EventSource(`/api/search/stream?q=${encodeURIComponent(file.number)}`);

        eventSource.onmessage = function (event) {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'mode') {
                    state.currentMode = data.mode;
                    window.SearchCore.updateLog(`${window.SearchCore.MODE_TEXT[data.mode] || '搜尋'}...`);
                }
                else if (data.type === 'status') {
                    window.SearchCore.handleSearchStatus(data.source, data.status);
                }
                else if (data.type === 'result') {
                    eventSource.close();
                    state.isSearchingFile = false;

                    if (!showFullLoading) {
                        targetBtn.innerHTML = targetBtnIcon;
                        targetBtn.disabled = false;
                    }

                    state.listMode = 'file';

                    if (data.success && data.data && data.data.length > 0) {
                        file.searchResults = data.data;
                        file.hasMoreResults = data.has_more || false;
                        file.searched = true;

                        state.searchResults = data.data;
                        state.hasMoreResults = file.hasMoreResults;
                        state.currentIndex = position === 'last' ? state.searchResults.length - 1 : 0;
                        window.SearchUI.displayResult(state.searchResults[state.currentIndex]);
                        window.SearchUI.updateNavigation();
                        window.SearchUI.showState('result');

                        renderFileList();
                    } else {
                        file.searched = true;
                        file.searchResults = [];
                        window.SearchUI.displayCoverError(`找不到 ${file.number} 的資料`);
                        window.SearchUI.showState('result');
                        renderFileList();
                        window.SearchUI.updateNavigation();
                    }
                    resolve();
                }
                else if (data.type === 'error') {
                    eventSource.close();
                    state.isSearchingFile = false;
                    if (!showFullLoading) {
                        targetBtn.innerHTML = targetBtnIcon;
                        targetBtn.disabled = false;
                    }
                    file.searched = true;
                    file.searchResults = [];
                    window.SearchUI.displayCoverError(data.message || '搜尋失敗');
                    window.SearchUI.showState('result');
                    renderFileList();
                    window.SearchUI.updateNavigation();
                    resolve();
                }
            } catch (err) {
                console.error('Parse error:', err);
            }
        };

        eventSource.onerror = function () {
            eventSource.close();
            state.isSearchingFile = false;
            if (!showFullLoading) {
                targetBtn.innerHTML = targetBtnIcon;
                targetBtn.disabled = false;
            }
            file.searched = true;
            file.searchResults = [];
            window.SearchUI.displayCoverError('連線錯誤，請稍後再試');
            window.SearchUI.showState('result');
            renderFileList();
            window.SearchUI.updateNavigation();
            resolve();
        };
    });
}

// === 批次操作 ===

async function scrapeFile(file, metadata) {
    const response = await fetch('/api/scrape-single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file_path: file.path,
            number: metadata.number,
            metadata: metadata
        })
    });
    return await response.json();
}

async function scrapeSingle(index) {
    const { state, dom } = window.SearchCore;
    const file = state.fileList[index];
    if (!file || !file.searchResults || file.searchResults.length === 0) {
        alert('此檔案沒有搜尋結果');
        return;
    }

    const metadata = { ...file.searchResults[0] };

    const btn = dom.fileListContainer.querySelector(`[data-index="${index}"]`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    }

    try {
        const chineseFromFile = file.chineseTitle;
        const appConfig = state.appConfig;
        if (appConfig?.translate?.enabled && !chineseFromFile &&
            metadata.title && window.SearchCore.hasJapanese(metadata.title)) {
            const tr = await window.SearchCore.translateWithOllama(metadata.title, 'translate', metadata);
            if (tr.success) metadata.translated_title = tr.result;
        }

        const result = await scrapeFile(file, metadata);
        if (result.success) {
            file.scraped = true;
            if (btn) {
                btn.innerHTML = '<i class="bi bi-check"></i>';
                btn.classList.remove('btn-outline-success');
                btn.classList.add('btn-success');
                btn.disabled = true;
            }
        } else {
            alert(`${file.filename} 處理失敗: ${result.error || '未知錯誤'}`);
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '產生';
            }
        }
    } catch (err) {
        alert(`${file.filename} 處理失敗: ${err.message}`);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '產生';
        }
    }
}

async function searchAll() {
    const { state, dom } = window.SearchCore;
    const searchableFiles = state.fileList.filter(f => f.number && !f.searched);

    if (searchableFiles.length === 0) {
        alert('沒有需要搜尋的檔案');
        return;
    }

    dom.btnSearchAll.disabled = true;
    const originalHtml = dom.btnSearchAll.innerHTML;
    dom.btnSearchAll.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    let successCount = 0;
    let failCount = 0;

    for (const file of searchableFiles) {
        const index = state.fileList.indexOf(file);
        await switchToFile(index, 'first', false);

        if (file.searched) {
            if (file.searchResults && file.searchResults.length > 0) {
                successCount++;
            } else {
                failCount++;
            }
        } else {
            failCount++;
        }

        renderFileList();
    }

    state.isSearchingFile = false;
    dom.btnNext.innerHTML = '<i class="bi bi-chevron-right"></i>';
    dom.btnPrev.innerHTML = '<i class="bi bi-chevron-left"></i>';
    window.SearchUI.updateNavigation();

    dom.btnSearchAll.innerHTML = `<i class="bi bi-check-circle"></i> ${successCount}/${searchableFiles.length}`;

    setTimeout(() => {
        dom.btnSearchAll.innerHTML = originalHtml;
        dom.btnSearchAll.disabled = false;
    }, 2000);
}

async function scrapeAll() {
    const { state, dom } = window.SearchCore;
    const scrapableFiles = state.fileList.filter(f =>
        f.searched && f.searchResults && f.searchResults.length > 0 && !f.scraped
    );

    if (scrapableFiles.length === 0) {
        alert('沒有可處理的檔案');
        return;
    }

    dom.btnScrapeAll.disabled = true;
    const originalHtml = dom.btnScrapeAll.innerHTML;
    dom.btnScrapeAll.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

    let successCount = 0;
    let failCount = 0;

    for (const file of scrapableFiles) {
        const index = state.fileList.indexOf(file);

        state.currentFileIndex = index;
        state.searchResults = file.searchResults;
        state.currentIndex = 0;
        window.SearchUI.displayResult(state.searchResults[0]);
        renderFileList();

        const metadata = { ...file.searchResults[0] };

        const btn = dom.fileListContainer.querySelector(`[data-index="${index}"]`);
        if (btn) {
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
            btn.disabled = true;
        }

        try {
            const chineseFromFile = file.chineseTitle;
            const appConfig = state.appConfig;
            if (appConfig?.translate?.enabled && !chineseFromFile &&
                metadata.title && window.SearchCore.hasJapanese(metadata.title)) {
                const tr = await window.SearchCore.translateWithOllama(metadata.title, 'translate', metadata);
                if (tr.success) metadata.translated_title = tr.result;
            }

            const result = await scrapeFile(file, metadata);
            if (result.success) {
                file.scraped = true;
                successCount++;
                if (btn) {
                    btn.innerHTML = '<i class="bi bi-check"></i>';
                    btn.classList.remove('btn-outline-success');
                    btn.classList.add('btn-success');
                }
            } else {
                failCount++;
                if (btn) {
                    btn.innerHTML = '失敗';
                    btn.classList.remove('btn-outline-success');
                    btn.classList.add('btn-outline-danger');
                }
            }
        } catch (err) {
            failCount++;
            if (btn) {
                btn.innerHTML = '失敗';
                btn.classList.remove('btn-outline-success');
                btn.classList.add('btn-outline-danger');
            }
        }
    }

    dom.btnScrapeAll.innerHTML = '<i class="bi bi-check-circle"></i>';
    dom.btnScrapeAll.classList.remove('btn-success');
    dom.btnScrapeAll.classList.add('btn-outline-success');

    alert(`批次處理完成!\n成功: ${successCount}\n失敗: ${failCount}`);

    setTimeout(() => {
        dom.btnScrapeAll.innerHTML = originalHtml;
        dom.btnScrapeAll.classList.remove('btn-outline-success');
        dom.btnScrapeAll.classList.add('btn-success');
        dom.btnScrapeAll.disabled = false;
    }, 2000);
}

// === 拖拽處理 ===

async function setFileList(paths) {
    const { state, dom } = window.SearchCore;

    // 呼叫過濾 API
    try {
        const resp = await fetch('/api/search/filter-files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths })
        });
        const result = await resp.json();

        if (result.success) {
            if (result.total_rejected > 0) {
                const { extension, size, not_found } = result.rejected;
                let msg = `已過濾 ${result.total_rejected} 個檔案`;
                const details = [];
                if (extension > 0) details.push(`${extension} 個非影片檔`);
                if (size > 0) details.push(`${size} 個小於最小尺寸`);
                if (not_found > 0) details.push(`${not_found} 個不存在`);
                if (details.length > 0) msg += `（${details.join('、')}）`;

                // 顯示過濾結果提示（使用短暫 alert 或 Toast）
                console.log('[Filter]', msg);

                // 使用一個短暫的浮動提示
                const toast = document.createElement('div');
                toast.className = 'filter-toast';
                toast.textContent = msg;
                toast.style.cssText = `
                    position: fixed;
                    bottom: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: rgba(0,0,0,0.85);
                    color: white;
                    padding: 12px 24px;
                    border-radius: 8px;
                    z-index: 9999;
                    font-size: 14px;
                    opacity: 1;
                    transition: opacity 0.5s ease;
                `;
                document.body.appendChild(toast);
                setTimeout(() => { toast.style.opacity = '0'; }, 2500);
                setTimeout(() => toast.remove(), 3000);
            }
            paths = result.files;
        }
    } catch (err) {
        console.error('Filter API error:', err);
        // 降級：保留原 paths
    }

    // 檢查空列表
    if (paths.length === 0) {
        alert('無有效影片檔案');
        return;
    }

    state.fileList = paths.map(path => {
        const filename = path.split(/[/\\]/).pop();
        const number = extractNumber(path);
        return {
            path: path,
            filename: filename,
            number: number,
            hasSubtitle: checkSubtitle(filename),
            chineseTitle: extractChineseTitle(filename, number),
            searchResults: [],
            hasMoreResults: false,
            searched: false
        };
    });
    state.currentFileIndex = 0;
    state.listMode = 'file';

    renderFileList();
    window.SearchCore.updateClearButton();

    if (state.fileList.length > 0) {
        if (state.fileList[0].number) {
            dom.queryInput.value = state.fileList[0].number;
        }
        switchToFile(0, 'first', true);
    }
}

function handleFileDrop(files) {
    const { dom } = window.SearchCore;
    if (!files || files.length === 0) return;

    const file = files[0];
    const filename = file.name;
    const number = extractNumber(filename);

    if (!number) {
        document.getElementById('errorMessage').textContent = '無法從檔名識別番號';
        window.SearchUI.showState('error');
        return;
    }

    dom.queryInput.value = number;
    dom.form.dispatchEvent(new Event('submit'));
}

// === 暴露介面 ===
window.SearchFile = {
    // 工具函數
    checkSubtitle,
    hasChinese,
    cleanSourceSuffix,
    extractChineseTitle,
    extractNumber,
    formatNumber,
    // 列表渲染
    renderFileList,
    renderSearchResultsList,
    // 切換
    switchToFile,
    switchToSearchResult,
    searchForFile,
    // 批次操作
    scrapeFile,
    scrapeSingle,
    searchAll,
    scrapeAll,
    // 拖拽
    setFileList,
    handleFileDrop
};

// 全域函數（onclick 用）
window.enterNumber = enterNumber;
window.removeFile = removeFile;
