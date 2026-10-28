/**
 * batch-search-rules.js — 批次搜尋的純函式規則（TASK-182）。
 * 純函式、零 window／DOM 依賴、無 module 級可變狀態。
 */

/**
 * isFileSearching(activePaths, path) → boolean
 * 該片是否正在批次搜尋中（路徑在 activePaths 內）。比對字串，不比物件身分（FE-ALPINE-14）。
 */
export function isFileSearching(activePaths, path) {
    return Array.isArray(activePaths) && activePaths.includes(path);
}

/**
 * isDetailEmpty(file) → boolean
 * 詳細區是否沒東西可看：沒有該片、沒有番號、或沒有任何搜尋結果（含尚未搜、查無）；有空白結果卡（file.blankCard）的片除外。
 */
export function isDetailEmpty(file) {
    if (file && file.blankCard) return false;   // TASK-183：停在空白卡上（可能有未按 ✓ 的編輯）視為非空，不 arm follow
    return !file || !file.number || !(file.searchResults && file.searchResults.length > 0);
}

/**
 * shouldAutoJump({ armed, anchorPath, currentPath }) → boolean
 * 批次搜尋是否該自動帶使用者去第一個有結果的片：開始時詳細區空白（armed），
 * 且使用者仍停在按下時那片。比 path 字串不比物件身分（FE-ALPINE-14）。
 */
export function shouldAutoJump({ armed, anchorPath, currentPath }) {
    return armed && currentPath === anchorPath;
}
