/**
 * SearchInit - 初始化模組
 * 事件綁定、頁面初始化入口
 */

/**
 * 載入我的最愛資料夾
 */
async function loadFavoriteFolder() {
    const { dom } = window.SearchCore;

    // 顯示載入中
    dom.btnFavorite.disabled = true;
    const originalHtml = dom.btnFavorite.innerHTML;
    dom.btnFavorite.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';

    try {
        const resp = await fetch('/api/search/favorite-files');
        const result = await resp.json();

        if (!result.success) {
            alert(result.error || '載入失敗');
            dom.btnFavorite.disabled = false;
            dom.btnFavorite.innerHTML = originalHtml;
            return;
        }

        // 顯示成功訊息
        console.log(`[Favorite] 載入 ${result.total} 個檔案：${result.folder}`);

        // 載入檔案列表（會自動過濾）
        await window.SearchFile.setFileList(result.files);

        // 自動開始搜尋前 20 個
        // 延遲 100ms 確保 UI 更新完成
        setTimeout(() => {
            const searchableFiles = window.SearchCore.state.fileList.filter(
                f => f.number && !f.searched
            );
            if (searchableFiles.length > 0) {
                window.SearchFile.searchAll();
            }
        }, 100);

    } catch (err) {
        console.error('Favorite API error:', err);
        alert('載入失敗：' + err.message);
    } finally {
        dom.btnFavorite.disabled = false;
        dom.btnFavorite.innerHTML = originalHtml;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // T1a: initDOM / loadAppConfig / loadSourceConfig / restoreState / updateClearButton
    // 已由 Alpine init() 接管，這裡只保留事件綁定（T1b-T1d 將遷移到 Alpine）

    // Fix 4: 防呆 — 如果 Alpine init() 未執行 initDOM()，這裡補救
    if (!window.SearchCore.dom.form) {
        console.warn('[Init] Alpine init() 未執行，fallback 呼叫 initDOM()');
        window.SearchCore.initDOM();
    }

    // Fix 4b: 如果 Alpine bridge 未建立，補上 no-op 防止 file.js 呼叫時拋錯
    if (!window.SearchCore.initProgress) {
        window.SearchCore.initProgress = (query) => {
            console.warn('[Init] initProgress called without Alpine bridge');
        };
    }
    if (!window.SearchCore.updateLog) {
        window.SearchCore.updateLog = (msg) => {
            console.warn('[Init] updateLog called without Alpine bridge');
        };
    }
    if (!window.SearchCore.handleSearchStatus) {
        window.SearchCore.handleSearchStatus = (source, status) => {
            console.warn('[Init] handleSearchStatus called without Alpine bridge');
        };
    }

    const { state, dom } = window.SearchCore;

    // T1b: 表單提交、導航按鈕、鍵盤導航已遷移到 Alpine（@submit.prevent, @click, @keydown.window）

    // 5.5. Gallery 返回按鈕（T2b 才遷移）
    dom.btnBackToDetail.addEventListener('click', () => {
        window.SearchUI.hideGallery();
    });

    // 7. 清空按鈕（T1c 才遷移）
    dom.btnClear.addEventListener('click', window.SearchCore.clearAll);

    // 8. 批次按鈕
    dom.btnSearchAll.addEventListener('click', window.SearchFile.searchAll);
    dom.btnScrapeAll.addEventListener('click', window.SearchFile.scrapeAll);

    // 9. 加入檔案/資料夾按鈕
    dom.btnAddFiles.addEventListener('click', async () => {
        if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
            alert('此功能需要在桌面應用程式中使用');
            return;
        }
        try {
            const paths = await window.pywebview.api.select_files();
            if (paths && paths.length > 0) {
                console.log('選取檔案:', paths.length, '個');
                window.handlePyWebViewDrop(paths);
            }
        } catch (e) {
            console.error('選取檔案失敗:', e);
        }
    });

    dom.btnAddFolder.addEventListener('click', async () => {
        if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
            alert('此功能需要在桌面應用程式中使用');
            return;
        }
        try {
            const result = await window.pywebview.api.select_folder();
            const paths = result?.files || result;
            if (paths && paths.length > 0) {
                console.log('資料夾內檔案:', paths.length, '個');
                window.handlePyWebViewDrop(paths);
            }
        } catch (e) {
            console.error('選取資料夾失敗:', e);
        }
    });

    // 10. 我的最愛按鈕
    dom.btnFavorite.addEventListener('click', loadFavoriteFolder);

    // 10. PyWebView 檔案事件
    window.addEventListener('pywebview-files', async (e) => {
        await window.SearchFile.setFileList(e.detail.paths);
    });

    // 11. 拖拽事件
    let dragCounter = 0;

    document.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    document.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        if (e.dataTransfer.types.includes('Files')) {
            dom.dragOverlay.classList.add('active');
        }
    });

    document.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            dom.dragOverlay.classList.remove('active');
        }
    });

    document.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;
        dom.dragOverlay.classList.remove('active');

        // PyWebView 環境由 Python 端處理
        if (typeof window.pywebview !== 'undefined') {
            return;
        }

        // 純瀏覽器環境
        window.SearchFile.handleFileDrop(e.dataTransfer.files);
    });

    // 12. 離開前保存狀態（已由 Alpine init() 接管）
});
