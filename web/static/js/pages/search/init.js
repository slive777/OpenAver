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
    // 初始化 DOM 引用
    window.SearchCore.initDOM();

    const { state, dom } = window.SearchCore;

    // 1. 載入設定
    window.SearchCore.loadAppConfig();

    // 載入來源配置
    window.SearchUI.loadSourceConfig();

    // 2. 還原狀態
    if (!window.SearchCore.restoreState()) {
        dom.queryInput.focus();
    }
    window.SearchCore.updateClearButton();

    // 3. 表單提交
    dom.form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = dom.queryInput.value.trim();
        if (query) {
            window.SearchCore.doSearch(query);
        }
    });

    // 4. 導航按鈕
    dom.btnPrev.addEventListener('click', () => window.SearchUI.navigateResult(-1));
    dom.btnNext.addEventListener('click', () => window.SearchUI.navigateResult(1));

    // 5. Error 狀態導航按鈕
    dom.errorBtnPrev.addEventListener('click', () => window.SearchUI.navigateResult(-1));
    dom.errorBtnNext.addEventListener('click', () => window.SearchUI.navigateResult(1));

    // 5.5. Gallery 返回按鈕
    dom.btnBackToDetail.addEventListener('click', () => {
        window.SearchUI.hideGallery();
    });

    // 6. 鍵盤導航
    document.addEventListener('keydown', (e) => {
        if (document.activeElement === dom.queryInput) return;

        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            window.SearchUI.navigateResult(-1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            window.SearchUI.navigateResult(1);
        }
    });

    // 7. 清空按鈕
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

    // 12. 離開前保存狀態
    window.addEventListener('beforeunload', window.SearchCore.saveState);
});
