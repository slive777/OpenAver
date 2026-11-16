/**
 * clipboard.js — 剪貼簿三層降級（168b-T7）
 *
 * copyText(text) -> Promise<boolean>：
 *   ① PyWebView bridge copy_text（回 {ok:true} 才算成功）
 *   ② navigator.clipboard 的非同步寫入
 *   ③ execCommand 備援
 * 成功即停（不碰後面層）；全失敗回 false；永不丟例外。
 * 零 import；navigator／window／document 一律在呼叫當下讀。
 * 不在此顯示 toast，由呼叫端決定文案。
 */

async function tryBridge(text) {
    try {
        const fn = window.pywebview?.api?.copy_text;
        if (typeof fn !== 'function') return false;
        const result = await fn(text);
        return result?.ok === true;
    } catch (e) {
        return false;
    }
}

async function tryNavigatorClipboard(text) {
    try {
        if (!navigator.clipboard?.writeText) return false;
        await navigator.clipboard.writeText(text);
        return true;
    } catch (e) {
        return false;
    }
}

// 回傳 execCommand('copy') 是否真的成功；例外一律視為失敗。
// textarea 一定移除（finally），不因例外殘留在 DOM 上。
export function execCommandCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;top:-9999px';
    const prev = document.activeElement;
    const host = (prev && prev !== document.body && prev.parentElement) || document.body;
    host.appendChild(ta);
    ta.select();
    let ok = false;
    try {
        ok = document.activeElement === ta && ta.selectionEnd > ta.selectionStart && document.execCommand('copy');
    } catch (e) {
        ok = false;
    } finally {
        ta.remove();
        try { if (prev && prev.focus) prev.focus({ preventScroll: true }); } catch (e) {}
    }
    return ok;
}

function tryExecCommand(text) {
    try {
        return execCommandCopy(text) === true;
    } catch (e) {
        return false;
    }
}

export async function copyText(text) {
    if (await tryBridge(text)) return true;
    if (await tryNavigatorClipboard(text)) return true;
    if (tryExecCommand(text)) return true;
    return false;
}
