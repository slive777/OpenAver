/**
 * dir-path.js — 共用目錄路徑萃取純函式（shared ESM）
 *
 * dirPath：從「字串」或「DirectoryConfig 物件（{path, ...}）」兩種形態
 * 安全萃取路徑字串。T-2 資料仍純字串，T-3+ 型別翻轉後對物件同樣有效。
 *
 * 被 scanner / settings 兩頁 state 模組 import，template 經 state 屬性揭露。
 * 純函式：無 DOM、無 Alpine、無 window、無副作用。
 * 由 tests/unit/test_frontend_lint.py::TestDirPathHelperGuard 鎖死。
 */

/**
 * 從 directory 元素（字串或物件）萃取路徑字串。
 *
 * @param {string|{path: string}|any} dir 目錄元素
 * @returns {string} 路徑字串；無法解析時回空字串
 */
export function dirPath(dir) {
  return typeof dir === 'string' ? dir : (dir?.path ?? '');
}
