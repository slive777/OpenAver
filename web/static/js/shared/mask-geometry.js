/**
 * mask-geometry.js — 焦點裁切遮罩軸向/窗幾何 純函式（shared ESM，100b-T2a）
 *
 * 從 state-lightbox.js 抽出的兩段承重幾何邏輯，抽成純函式的唯一理由是**可測試性**——
 * state-lightbox.js 本身用 `@/showcase/...` 等 importmap alias（僅瀏覽器/base.html 的
 * importmap 認得），plain Node（node:test）無法直接 import 該檔；本檔只用相對路徑 import
 * `./focal.js` 的 clampMaskWinLeft，比照 focal-cell.js 的既有慣例，讓 node:test 可直接
 * import 驗證。
 *
 * 不動 focal.js／focal-cell.js 本體（T3 範圍）——本檔只消費 focal.js 既有 export，不修改它。
 *
 * computeMaskWinGeometry：亮窗 inline style 物件建構（G1：恆回傳 object，不可為字串——
 * `_computeMaskWinStyle()` 與 `_maskDragStart()` 的 onMove 兩個獨立 writer 皆委派本函式，
 * 讓「留一個字串 writer」這個 99a-T5 事故的 by-construction 復發面從多處收斂為一處）。
 * computeMaskDragRoom + MASK_MIN_DRAG_ROOM：CD-7（100c-T1）門檻判定——回傳橫向可拖幅度
 * （比例空間，非 px），供 T2 的 icon 顯示條件與門檻比較（本 task 只建函式、不接線）。
 */

import { clampMaskWinLeft } from './focal.js';

/**
 * 亮窗 inline style 物件建構。呼叫端（state-lightbox.js）負責讀
 * getComputedStyle/CSS var（裁決3：ratio 讀取受 static_guard_lint.mjs scope-anchor 規則
 * 錨定在 `_computeMaskWinStyle()` 本體內，不可委派），本函式只吃已解出的數字 r。
 *
 * @param {number} W render 寬（px）
 * @param {number} H render 高（px）
 * @param {number} r 裁切窗比例
 * @param {number|null|undefined} focalX raw x（[0,1]，未鉗）
 * @returns {{width: string, height: string, transform: string}} 恆為 object（G1，絕不回傳字串）
 */
export function computeMaskWinGeometry(W, H, r, focalX) {
  const winW = Math.min(W, H * r);
  const winH = Math.min(H, W / r);
  let left = (focalX !== null && focalX !== undefined) ? focalX * W - winW / 2 : W - winW;
  left = clampMaskWinLeft(left, W, winW);
  return { width: `${winW}px`, height: `${H}px`, transform: `translateX(${left}px)` };
}

/**
 * CD-7（100c-T1）門檻常數：橫向可拖幅度 >= 此值才視為「有意義的可拖空間」
 * （供 T2 的 `_actressPhotoWideEnough` 判定 icon 是否顯示，本 task 不接線）。
 */
export const MASK_MIN_DRAG_ROOM = 0.20;

/**
 * CD-7（100c-T1）：回傳橫向可拖幅度（比例空間，非 px）——`a` 為照片長寬比、`r` 為裁窗比例。
 *
 * - `a <= r`（窄圖／等比）→ 恆 `0`（X 軸零溢出，用 `<=` 分支保證精確 0，不落入除法路徑）
 * - `a > r`（寬圖）→ `1 - r / a`
 * - `a`／`r` 任一為非有限值（`NaN`/`Infinity`/`-Infinity`）或 `r <= 0` → `0`
 *   （fail-closed，絕不回 `NaN`——這是給 T2 當 fail-closed 守門員的隱性契約：下游只要用
 *   `computeMaskDragRoom(...) >= MASK_MIN_DRAG_ROOM` 比較，非有限輸入天然算出 `false`，
 *   T2 不需要再額外寫一層 NaN 特判）。
 *
 * 吃 `a` 而非 `W, H`：本函式全程只在比例空間運算，不像已移除的凍結判定曾經需要絕對 px 量，
 * 因此尺度無關（scale invariance）是簽名本身的結構保證，非巧合。
 *
 * @param {number} a 照片長寬比（naturalWidth/naturalHeight 或 render W/H，只要同源即可）
 * @param {number} r 裁切窗比例（--poster-crop-ratio / --actress-crop-ratio）
 * @returns {number} 橫向可拖幅度（[0, 1) 比例），恆為有限 number，不回傳 NaN
 */
export function computeMaskDragRoom(a, r) {
  if (!Number.isFinite(a) || !Number.isFinite(r) || r <= 0) {
    return 0;
  }
  if (a <= r) {
    return 0;
  }
  return 1 - r / a;
}

/**
 * 收斂幾何純函式（101b-T1，CD-2/CD-3/CD-3a/CD-6/CD-11a/CD-11b）：把「全幅 → 偵測終值」
 * 的收斂過程表達成對 `computeMaskWinGeometry` 兩個入參（`r`、`focalX`）的 lerp，
 * **不重寫任何幾何**——內插區的唯一出口是呼叫既有 `computeMaskWinGeometry`。
 *
 * - `t<=0`：全幅（手搭物件，CD-3a 的唯一允許例外——理由是浮點不收斂，§A-1a 實測整數
 *   fixture 8/8 假綠、小數 fuzz 3.929% 漂移）。
 * - `t>=1`：終值 by construction（直接轉呼叫既有函式，CD-2「終點即真值」的結構保證）。
 * - `0<t<1`：precise lerp `(1-t)*a + t*b`（非 `a+(b-a)*t`——§A-1a 實測 focal=0.1 反例）。
 * - fail-closed（CD-11a）：`W/H/r/t/focalX` 任一非有限，或 `r<=0`/`W<=0`/`H<=0` → `null`。
 *   `focalX` 納入本 gate 是 Opus 裁決（見 TASK-101b-T1.md「Opus 裁決」段）：忠於 CD-11a
 *   結語「絕不倒向壞幾何」，且避免同一個 `focalX=null` 在 t=1 端點（右裁語意）與內插區
 *   （JS 算術強制轉型為 0＝最左語意）產生兩套矛盾語意。
 *
 * @param {number} W render 寬（px）
 * @param {number} H render 高（px）
 * @param {number} r 裁切窗終值比例
 * @param {number} focalX 偵測終值 x（[0,1]，未鉗；本函式要求恆為有限值，不同於
 *   `computeMaskWinGeometry` 可接受 null/undefined 的右裁 fallback 語意）
 * @param {number} t 收斂進度 [0,1]（越界值不 clamp，`>=1`/`<=0` 直接落對應端點分支）
 * @returns {{width: string, height: string, transform: string}|null} 恆為 object（三鍵
 *   `width`/`height`/`transform`）或 `null`（fail-closed），絕不回傳字串（CD-11b）
 */
export function computeMaskSettleGeometry(W, H, r, focalX, t) {
  // CD-11a fail-closed（第一道 gate，早於任何 short-circuit——順序本身是承重的：
  // 若先判 t>=1/t<=0，t=NaN 會因兩個比較皆為 false 而穿透到內插區產生 NaN 字串）。
  if (!Number.isFinite(W) || !Number.isFinite(H) || !Number.isFinite(r) || !Number.isFinite(t)
      || !Number.isFinite(focalX)
      || r <= 0 || W <= 0 || H <= 0) {
    return null;
  }
  // CD-3a 端點：t>=1 → 終值 by construction（呼叫既有函式，不重算）
  if (t >= 1) {
    return computeMaskWinGeometry(W, H, r, focalX);
  }
  // CD-3a 端點：t<=0 → 全幅（手搭物件，唯一允許的例外，理由見 §A-1a）
  if (t <= 0) {
    return { width: `${W}px`, height: `${H}px`, transform: 'translateX(0px)' };
  }
  // 內插區：precise lerp (1-t)*a + t*b，非 a+(b-a)*t（§A-1a 實測 focal=0.1 反例）
  const r_t = (1 - t) * (W / H) + t * r;
  const focal_t = (1 - t) * 0.5 + t * focalX;
  return computeMaskWinGeometry(W, H, r_t, focal_t);
}
