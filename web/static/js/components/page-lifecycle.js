/**
 * Page Lifecycle Manager
 * web/static/js/components/page-lifecycle.js
 *
 * 契約：
 *   beforeLeave(href) → boolean   sidebar 導航時呼叫。gate + save，不釋放資源。
 *   onBeforeUnload() → string|null  tab 關閉/reload 時呼叫。save + 回傳 non-null 觸發原生提示。
 *   cleanup()                       釋放資源（關 SSE、清 timer、abort fetch），不做保存。
 *
 * 兩條離頁路徑：
 *   路徑 A（sidebar）：beforeLeave → cleanup → 頁面卸載
 *   路徑 B（tab close）：onBeforeUnload → [原生提示] → unload 事件 → cleanup
 */
(function () {
    var _handlers = { beforeLeave: null, onBeforeUnload: null, cleanup: null };
    var _cleanedUp = false;

    // beforeunload：只做 save + 原生提示，不做 cleanup
    // （使用者可能按「留下」→ 頁面不卸載 → hooks 必須保持完整）
    window.addEventListener('beforeunload', function (e) {
        if (_handlers.onBeforeUnload) {
            try {
                var msg = _handlers.onBeforeUnload();
                if (msg) {
                    e.preventDefault();
                    e.returnValue = msg;
                }
            } catch (err) {
                console.error('[page-lifecycle] onBeforeUnload error:', err);
            }
        }
    });

    // unload：頁面確定要卸載了，best-effort cleanup
    window.addEventListener('unload', function () {
        _doCleanup();
    });

    function registerPage(handlers) {
        _cleanedUp = false;
        _handlers = {
            beforeLeave: handlers.beforeLeave || null,
            onBeforeUnload: handlers.onBeforeUnload || null,
            cleanup: handlers.cleanup || null,
        };
    }

    /**
     * sidebar 導航入口（路徑 A）
     * @param {string} href - 目的地 URL
     * @returns {boolean} 是否允許離開（false = 阻止導航）
     */
    function leavePage(href) {
        // 若有頁面已 registerPage，走新路徑
        if (_handlers.beforeLeave !== null || _handlers.onBeforeUnload !== null || _handlers.cleanup !== null) {
            if (_handlers.beforeLeave) {
                try {
                    var allowed = _handlers.beforeLeave(href);
                    if (!allowed) return false;
                } catch (e) {
                    console.error('[page-lifecycle] beforeLeave error:', e);
                    // 例外不阻止導航
                }
            }
            _doCleanup();
            return true;
        }

        // Compatibility shim：Scanner 尚未 registerPage，走舊路徑
        // （Scanner 接入 lifecycle 後移除整個 shim）
        if (typeof window.confirmLeavingScanner === 'function' && !window.confirmLeavingScanner(href)) {
            return false;
        }
        return true;
    }

    /**
     * cleanup one-shot wrapper
     */
    function _doCleanup() {
        if (_cleanedUp) return;
        _cleanedUp = true;
        try {
            if (_handlers.cleanup) _handlers.cleanup();
        } catch (e) {
            console.error('[page-lifecycle] cleanup error:', e);
        }
        _handlers = { beforeLeave: null, onBeforeUnload: null, cleanup: null };
    }

    window.__registerPage = registerPage;
    window.__leavePage = leavePage;
})();
