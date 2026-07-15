/**
 * focal-cell.js — applyCellFocal：imperative、load-gated 小格 object-position 套用（99a-T2）。
 *
 * focal.js 是純函式模組（docstring 明文承諾無 DOM/無副作用，比照 dir-path.js）；applyCellFocal
 * 要讀 el.naturalWidth/naturalHeight + getComputedStyle + 掛 load listener + 寫 el.style，是
 * impure DOM 副作用 util，故獨立成檔（比照 dom-timing.js 與 dir-path.js 的分離慣例，見
 * TASK-99a-T2 §0）。import path 走目錄級 `@/shared/`（base.html importmap），新增此檔不需改 importmap。
 *
 * load-gate（Codex P1-3）：naturalWidth 在 `.src=` 賦值後、圖片真正 decode 完成前恆為 0，且
 * load 事件不是 Alpine reactive 依賴、不會讓 `:style` binding 重跑（98b-T6 姊妹案例，見 card §4）。
 * 故一律 `el.complete && el.naturalWidth` 才同步算，否則掛 `load` listener 延後算。
 *
 * expected-src guard（Codex P1-3 延伸）：`.similar-slot-img` 等可重用 DOM 元素會被連續 `.src=`
 * 賦新值多次；若 A 的 load listener 因排程延遲在 B 的 src 已賦值後才 fire，需放棄（不可用 A 的
 * aspect 算出的 object-position 覆寫已顯示 B 封面的 img）。
 */

import { focalCellObjectPosition } from './focal.js';

// ratioVar 預設值（100b-T3 CD-6）：既有三處呼叫點（state-videos.js / state-similar.js /
// showcase.html 三個 @load）皆 2-arg 呼叫，JS 預設參數只在傳入 undefined 時生效（不吃任何其他
// falsy 值），故零回歸。女優小格（T4）將傳 '--actress-crop-ratio'。
const DEFAULT_RATIO_VAR = '--poster-crop-ratio';

function computeAndApply(el, video, ratioVar = DEFAULT_RATIO_VAR) {
  const a = el.naturalWidth / el.naturalHeight;
  const r = parseFloat(getComputedStyle(el).getPropertyValue(ratioVar));
  if (!Number.isFinite(r) || r <= 0) {
    el.style.objectPosition = '';
    return;
  }
  const result = focalCellObjectPosition(video, a, r);
  el.style.objectPosition = result || ''; // null → 清 inline，退 CSS baseline，不殘留舊值（換片 A→B 契約）
}

/**
 * ⚠️ 前置條件：`el` 必須**已連接 DOM**（Codex PR#107 P2）。computeAndApply 讀的 ratioVar
 * 掛在 `:root`，detached element 沒有連到 `:root` 的 inheritance chain → `getComputedStyle`
 * 回空字串 → `parseFloat` NaN → 誤判「無比例」清掉 objectPosition。已快取的封面尤其危險：
 * `.src=` 後 `el.complete && el.naturalWidth` **同步**即為真（實測 complete=true/
 * naturalWidth=1），當場走同步分支、不經 load 事件，所以連「等 load 時已 append 了」的僥倖
 * 都沒有。imperative 建 img 時務必 `appendChild` 後再呼叫本函式。
 *
 * @param {HTMLImageElement|null} el 小格 <img>（grid / similar slot / mobile drill / 女優卡 四站共用）；須已 in-DOM
 * @param {{crop_mode: string, auto_focal: string}|null|undefined} video
 * @param {string} [ratioVar] 讀取的 CSS var 名稱，預設 '--poster-crop-ratio'；女優小格（T4）傳 '--actress-crop-ratio'
 */
export function applyCellFocal(el, video, ratioVar = DEFAULT_RATIO_VAR) {
  if (!el) return;
  if (el.complete && el.naturalWidth) {
    computeAndApply(el, video, ratioVar);
    return;
  }
  // 未載入（或 broken image：complete=true 但 naturalWidth=0）→ 掛 load listener 延後算。
  const expectedSrc = el.src;
  el.addEventListener(
    'load',
    () => {
      // 換過圖了（同一元素被重用、.src= 換成新值）→ 放棄，不覆寫新圖的 objectPosition。
      if (el.currentSrc !== expectedSrc && el.src !== expectedSrc) return;
      computeAndApply(el, video, ratioVar);
    },
    { once: true },
  );
}
