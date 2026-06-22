/**
 * swipe.js — 共用觸控 swipe 方向判別純函式（shared ESM）
 *
 * detectSwipe：依起訖座標判定水平 swipe 方向（'left' / 'right'）或 null。
 * threshold 來源沿用劇照 Sample Gallery `_sgTouchEnd` 確值 = 50px
 * （web/static/js/pages/showcase/state-lightbox.js:419 → `Math.abs(delta) < 50`），
 * 由呼叫端傳入（T2–T4 一律傳 50），helper 內不寫死以保持純度與可測性。
 * 相對既有 `_sgTouchEnd` 的唯一邏輯增量：新增 `|dX| > |dY|` 軸判別，
 * 避免垂直捲動誤觸（plan-81c CD-2）。
 *
 * 被 search/showcase 燈箱與 detail 導覽 import（T2–T4：
 * pages/showcase/state-lightbox.js / pages/search/state/grid-mode.js / navigation.js）。
 * 純函式：無 DOM、無 Alpine、無 window、無副作用，不 preventDefault
 * （passive 由掛載端 `@touch*.passive` 負責）。
 * 由 tests/unit/test_frontend_lint.py::TestSwipeHelperGuard 鎖死。
 */

/**
 * 判定一次觸控 swipe 的方向。
 *
 * 觸發條件：水平位移為主（`|dX| > |dY|`）且超過 threshold（`|dX| > threshold`）。
 * 左滑（dX < 0）→ 'left'（下一片）；右滑（dX > 0）→ 'right'（上一片，CD-4）。
 * 否則回 null（讓垂直捲動 / 點擊正常，CD-2）。
 *
 * @param {number} startX touchstart X 座標
 * @param {number} startY touchstart Y 座標
 * @param {number} endX touchend X 座標
 * @param {number} endY touchend Y 座標
 * @param {number} threshold 觸發門檻（像素；掛載端傳入 50）
 * @returns {('left'|'right'|null)} swipe 方向或 null
 */
export function detectSwipe(startX, startY, endX, endY, threshold) {
  const dX = endX - startX;
  const dY = endY - startY;
  if (Math.abs(dX) > Math.abs(dY) && Math.abs(dX) > threshold) {
    return dX < 0 ? 'left' : 'right';
  }
  return null;
}
