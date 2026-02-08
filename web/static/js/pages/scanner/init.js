/**
 * ScannerInit - 初始化模組
 * 事件綁定、拖曳、初始化呼叫
 */

// 離開頁面警告
window.addEventListener('beforeunload', function (e) {
    if (isGenerating) {
        e.preventDefault();
        e.returnValue = '生成正在進行中，離開將會中斷操作！';
        return e.returnValue;
    }
});

// 監聽側邊欄點擊（PyWebView 中 beforeunload 可能不觸發）
document.addEventListener('click', function (e) {
    if (isGenerating) {
        const link = e.target.closest('a[href]');
        if (link && !link.href.includes('/scanner')) {
            if (!confirm('生成正在進行中，離開將會中斷操作！確定要離開嗎？')) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
        }
    }
});

// Enter 鍵加入
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('manualPath')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addManualPath();
        }
    });
});

// === 拖曳功能 ===
const dragOverlay = document.getElementById('dragOverlay');
let dragCounter = 0;

// 拖曳進入
document.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    console.log('[AVList] dragenter, counter:', dragCounter);
    if (dragCounter === 1) {
        dragOverlay.classList.add('show');
    }
});

// 拖曳離開
document.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCounter--;
    console.log('[AVList] dragleave, counter:', dragCounter);
    if (dragCounter === 0) {
        dragOverlay.classList.remove('show');
    }
});

// 拖曳經過
document.addEventListener('dragover', (e) => {
    e.preventDefault();
});

// 放開
document.addEventListener('drop', (e) => {
    e.preventDefault();
    dragCounter = 0;
    dragOverlay.classList.remove('show');
    console.log('[AVList] drop event fired');
    // PyWebView 會自動處理並呼叫 handleFolderDrop
});

// 初始化
renderDirectories();  // 先渲染空狀態
loadConfig();
loadStats();
restoreLogs();  // 恢復上次的 logs
