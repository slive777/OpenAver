/**
 * image-search-rules.js — 以圖搜番號的前端純規則（TASK-193-T6）。
 * 純函式、零全域依賴、無模組級可變狀態；呼叫端在 T7／T8 接線。
 */

export const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

const SUPPORTED_MIME = ['image/jpeg', 'image/png', 'image/webp'];
const SUPPORTED_EXT = ['jpg', 'jpeg', 'png', 'webp'];

function imageKindOf(file) {
    const t = String((file && file.type) || '').toLowerCase();
    if (SUPPORTED_MIME.includes(t)) return 'supported';
    if (t === '') {
        const name = String((file && file.name) || '').toLowerCase();
        const dot = name.lastIndexOf('.');
        const ext = dot === -1 ? '' : name.slice(dot + 1);
        return SUPPORTED_EXT.includes(ext) ? 'supported' : 'none';
    }
    if (t.startsWith('image/')) return 'unsupported';
    return 'none';
}

/**
 * classifyDrop(files) → { kind, file, multiple }。
 * 先掃全部：任一項非圖片即 'other'；否則看第一項是三種之一還是其他圖片格式。
 */
export function classifyDrop(files) {
    const list = Array.from(files || []);
    if (list.length === 0) return { kind: 'none', file: null, multiple: false };
    for (const f of list) {
        if (imageKindOf(f) === 'none') return { kind: 'other', file: null, multiple: false };
    }
    const first = list[0];
    if (imageKindOf(first) === 'supported') return { kind: 'image', file: first, multiple: list.length > 1 };
    return { kind: 'unsupported', file: first, multiple: list.length > 1 };
}

/**
 * dragKindOf(items) → 'image'｜'other'。只看第一項的型別，讀不到一律當 'other'。
 */
export function dragKindOf(items) {
    const t = String((items && items[0] && items[0].type) || '').toLowerCase();
    return t.startsWith('image/') ? 'image' : 'other';
}

function isImageFileItem(it) {
    return !!it && it.kind === 'file' && SUPPORTED_MIME.includes(it.type);
}

/**
 * firstImageItem(items) → 第一個圖片檔案項或 null。
 */
export function firstImageItem(items) {
    const list = Array.from(items || []);
    return list.find(isImageFileItem) || null;
}

/**
 * pasteIntent(items) → 'image'｜'text'。
 * 有圖片檔案項且沒有純文字項才算圖片；其餘一律走原本的文字貼上。
 */
export function pasteIntent(items) {
    const list = Array.from(items || []);
    const hasText = list.some((it) => !!it && it.type === 'text/plain');
    if (hasText) return 'text';
    return firstImageItem(list) ? 'image' : 'text';
}

/**
 * shouldSkipPaste(target, searchEl, flags) → 是否略過攔截。
 * 任一彈窗開著即略過；焦點在搜尋框以外的可編輯欄位也略過。
 */
export function shouldSkipPaste(target, searchEl, flags) {
    const f = flags || {};
    if (f.rescrapeOpen || f.browseDirOpen || f.sampleGalleryOpen || f.lightboxOpen || f.duplicateModalOpen) return true;
    if (!target) return false;
    const tag = target.tagName || '';
    const editable = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || !!target.isContentEditable;
    return editable && target !== searchEl;
}

/**
 * validateImageFile(file) → { ok: true } 或 { ok: false, reason: 'too_large' }。
 * 只檢查大小（嚴格大於才擋），格式以後端為準。
 */
export function validateImageFile(file) {
    const size = (file && file.size) || 0;
    if (size > MAX_IMAGE_BYTES) return { ok: false, reason: 'too_large' };
    return { ok: true };
}

/**
 * isSessionFor(rawResults, rawBound) → 是否為同一比對工作階段。
 * 只比原始陣列參照，不做深比對；沒有工作階段一律 false。
 */
export function isSessionFor(rawResults, rawBound) {
    return rawBound != null && rawResults === rawBound;
}
