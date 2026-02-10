/**
 * SearchInit - 初始化模組
 * 事件綁定、頁面初始化入口
 */

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
    // T1d: 清空、批次、加入檔案/資料夾、我的最愛、pywebview-files 已遷移到 Alpine（@click, init()）

    // 11. 拖拽事件（document 級別，呼叫 Alpine）
    let dragCounter = 0;

    document.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    document.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        if (e.dataTransfer.types.includes('Files')) {
            const el = document.querySelector('.search-container[x-data]');
            if (el && el._x_dataStack) {
                Alpine.$data(el).dragActive = true;
            }
        }
    });

    document.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            const el = document.querySelector('.search-container[x-data]');
            if (el && el._x_dataStack) {
                Alpine.$data(el).dragActive = false;
            }
        }
    });

    document.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;
        const el = document.querySelector('.search-container[x-data]');
        if (el && el._x_dataStack) {
            Alpine.$data(el).dragActive = false;
            // PyWebView 環境由 Python 端處理
            if (typeof window.pywebview === 'undefined') {
                Alpine.$data(el).handleFileDrop(e.dataTransfer.files);
            }
        }
    });

    // 12. 離開前保存狀態（已由 Alpine init() 接管）
});
