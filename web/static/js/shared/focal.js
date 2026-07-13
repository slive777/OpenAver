/**
 * focal.js — 共用 focal 座標解析 / object-position 純函式（shared ESM）
 *
 * parseFocal：逐條鏡射 Python core/focal/detector.py::parse_focal 契約
 * （falsy→null；split(',') 恰 2 段；空段/非數/非有限→null；閉區間 [0,1]²；否則 null）。
 * focalObjectPosition：crop_mode gate + parse gate + deadzone gate → CSS object-position 字串或 null。
 *
 * 由 state 模組（T3）import、經 state 屬性揭露 template；null 時退 CSS baseline right center。
 * 純函式：無 DOM、無 Alpine、無 window、無副作用（比照 dir-path.js）。
 */

/**
 * 臉已落右側舒適區的 X 門檻：x ≥ 此值 → 純右裁（不設 inline object-position）。
 * named 常數（非 inline 數字），T5 owner 真機微調。
 */
export const FOCAL_X_DEADZONE = 0.62;

/**
 * 解析 canonical "x,y" 4dp 字串為 {x, y}，鏡射 Python parse_focal。
 *
 * @param {string} s focal 字串（'' / null / undefined / 畸形 → null）
 * @returns {{x: number, y: number}|null} 通過閉區間 [0,1]² 的座標，否則 null
 */
export function parseFocal(s) {
  if (!s) {
    return null;
  }
  const parts = s.split(',');
  if (parts.length !== 2) {
    return null;
  }
  // JS Number('') === 0 / Number('  ') === 0 陷阱：空/純空白段須先擋，
  // 否則會偽裝成合法 0（Python float('') 拋錯 → None）。
  if (parts[0].trim() === '' || parts[1].trim() === '') {
    return null;
  }
  const x = Number(parts[0]);
  const y = Number(parts[1]);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  if (!(x >= 0 && x <= 1 && y >= 0 && y <= 1)) {
    return null;
  }
  return { x, y };
}

/**
 * 由 video 的 crop_mode / auto_focal 算 CSS object-position 字串（只調 X、Y 恆 center）。
 *
 * @param {{crop_mode: string, auto_focal: string}|null|undefined} video
 * @returns {string|null} 如 "38.20% center"；null/default 模式 / 無座標 / 畸形 / deadzone 內 → null
 */
export function focalObjectPosition(video) {
  // T3 imperative 呼叫端（如 _getSlotItem(anchor.id)）可能回 undefined → 優雅退 baseline，不拋。
  if (!video || video.crop_mode !== 'auto') {
    return null;
  }
  const p = parseFocal(video.auto_focal);
  if (p === null) {
    return null;
  }
  if (p.x >= FOCAL_X_DEADZONE) {
    return null;
  }
  return `${(p.x * 100).toFixed(2)}% center`;
}
