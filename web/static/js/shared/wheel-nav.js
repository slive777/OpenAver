/**
 * wheel-nav.js — 共用滑鼠橫向滾輪 → 離散 left/right 導航純邏輯（shared ESM，TASK-102d-T1）
 *
 * 把「wheel 事件流 → 離散 onLeft/onRight 呼叫」這件事抽成不碰 DOM class 名 / Alpine 的
 * 可測純函式 + 一層薄的事件正規化（讀 event.deltaX/deltaY/deltaMode，不觸碰 target/closest）。
 * 比照 `shared/swipe.js::detectSwipe` 的純度慣例：無 DOM class 依賴、無 Alpine、無 window 全域
 * 依賴（`now()` 時間來源可注入，供 node:test 用假時鐘驅動、不需真 sleep）。
 *
 * 三個匯出：
 * - `isHorizontalWheel(deltaX, deltaY)`：純數值方向主導判斷（`|deltaX| > |deltaY|`），
 *   給呼叫端當 handler 第一行用（Opus 審核註記 #1：非 passive 監聽器每個 tick 都同步跑，
 *   handler 第一行必須是純數值判斷、DOM 走訪（`event.target.closest(...)`）排在其後）。
 * - `isVerticalWheel(deltaX, deltaY)`：`isHorizontalWheel` 的縱向鏡像（`|deltaY| > |deltaX|`），
 *   102d P2b（owner 拍板 2026-07-19，overlay 垂直滾輪=上/下一張）新增。與 `isHorizontalWheel`
 *   互斥但非互補——`|deltaX| === |deltaY|`（含 `0,0`）時兩者皆 false，呼叫端視為無方向意圖。
 * - `createWheelNav(options)`：狀態化累積器（門檻/冷卻/方向反轉解鎖），回傳
 *   `{ feed(event, callbacks) => boolean }`。每個接線點（呼叫端）各自建立一個實例（閉包持有
 *   accum/cooldown 狀態，不進 Alpine reactive data），避免不同 UI 狀態（sample gallery /
 *   lightbox / detail...）共用同一組冷卻計時器互相干擾。
 *   102d P2b：`options.axis`（`'horizontal'`預設 | `'vertical'`）決定累積器讀哪一軸的 delta
 *   當主軸、哪一軸當交叉軸（門檻/冷卻/方向反轉解鎖邏輯完全共用，僅軸別不同）；`axis:'horizontal'`
 *   時 `callbacks` 用 `{ onLeft, onRight }`（`dx<0`→`onLeft`），`axis:'vertical'` 時用
 *   `{ onUp, onDown }`（`dy<0`→`onUp`）。一個實例只服務一個軸——呼叫端需要「同一個 overlay
 *   接線點兩軸都吃」時建兩個實例（各自獨立累積/冷卻，見呼叫端 handleWheel 的
 *   `wheelNav*` / `wheelNav*V` 命名慣例）。
 *
 * 排除清單（`.sample-strip` 等容器）與 guard chain（modal 疊層優先序）皆由呼叫端負責——
 * 本檔保持零 DOM class 名依賴、零產品知識（見 TASK-102d-T1.md「技術要點」）。
 *
 * ⚠️ `onLeft`/`onRight` 只是幾何方向的命名（`deltaX<0`→`onLeft`、`deltaX>0`→`onRight`），
 * 不預設對應「上一個/下一個」的產品語意——那是呼叫端的映射決定，且**呼叫端刻意選了與
 * `shared/swipe.js::detectSwipe` 相反的映射**：swipe 是「拖內容」隱喻（手指往左拖 = 內容
 * 跟著往左移出、露出下一張，`dX<0`→`'left'`→next）；wheel 是「方向指令」隱喻（同
 * ArrowLeft/ArrowRight/scrollbar——往右撥 = 與 ArrowRight 同路徑 = next，往左撥 = 與
 * ArrowLeft 同路徑 = prev，owner 拍板 2026-07-19）。所有 7 個接線點一律
 * `onLeft → prev*()`、`onRight → next*()`——不要因為「同一個 util」就把 wheel 呼叫端的
 * 映射「統一」回 swipe 那套，兩者語意本來就相反。
 */

/** DOM_DELTA_LINE 正規化係數：慣用瀏覽器單行滾動約 16-40px，取中間值。 */
const LINE_HEIGHT_PX = 24;

/**
 * 純數值方向主導判斷：橫向位移是否大於縱向位移。
 * 不讀 deltaMode（PIXEL/LINE/PAGE 下 dx/dy 的相對比例不受單位影響，比較安全且免正規化開銷），
 * 供呼叫端 handler 第一行使用（零 DOM 走訪成本）。
 *
 * @param {number} deltaX
 * @param {number} deltaY
 * @returns {boolean}
 */
export function isHorizontalWheel(deltaX, deltaY) {
  return Math.abs(deltaX) > Math.abs(deltaY);
}

/**
 * 純數值方向主導判斷：縱向位移是否大於橫向位移（`isHorizontalWheel` 的鏡像，102d P2b）。
 * `|deltaX| === |deltaY|`（含 `0,0`）時與 `isHorizontalWheel` 一樣回傳 false——兩者互斥但
 * 不互補，45 度邊界視為無方向意圖，呼叫端不處理。
 *
 * @param {number} deltaX
 * @param {number} deltaY
 * @returns {boolean}
 */
export function isVerticalWheel(deltaX, deltaY) {
  return Math.abs(deltaY) > Math.abs(deltaX);
}

/**
 * deltaMode 正規化：把 LINE/PAGE 模式的 delta 換算成與 PIXEL 模式同一量級。
 * PAGE 模式（罕見，多數瀏覽器滑鼠/觸控板不會回傳）用 window.innerWidth/innerHeight 換算；
 * 呼叫端若在無 window 環境（node:test）觸發 PAGE 模式，退化用固定值避免拋錯。
 *
 * @param {number} delta
 * @param {number} deltaMode 0=PIXEL, 1=LINE, 2=PAGE
 * @param {number} pageSizePx PAGE 模式換算基準（呼叫端可傳 window.innerWidth）
 * @returns {number}
 */
function normalizeDelta(delta, deltaMode, pageSizePx) {
  if (deltaMode === 1) return delta * LINE_HEIGHT_PX; // DOM_DELTA_LINE
  if (deltaMode === 2) return delta * (pageSizePx || 800); // DOM_DELTA_PAGE
  return delta; // DOM_DELTA_PIXEL
}

/**
 * 建立一個 wheel → 離散導航累積器。
 *
 * @param {object} [options]
 * @param {number} [options.threshold=80] 累積門檻（px，PIXEL 模式量級）
 * @param {number} [options.cooldownMs=200] 觸發後冷卻窗（ms）
 * @param {() => number} [options.now] 時間來源（預設 `Date.now`），測試可注入假時鐘
 * @param {number} [options.pageSizePx] DOM_DELTA_PAGE 換算基準（預設 800）
 * @param {'horizontal'|'vertical'} [options.axis='horizontal'] 102d P2b：本實例讀哪一軸
 *   當主軸。`'horizontal'`→ `callbacks.onLeft/onRight`；`'vertical'`→ `callbacks.onUp/onDown`。
 * @returns {{ feed: (event: { deltaX: number, deltaY: number, deltaMode?: number }, callbacks: object) => boolean }}
 */
export function createWheelNav(options = {}) {
  const threshold = options.threshold ?? 80;
  const cooldownMs = options.cooldownMs ?? 200;
  const now = options.now ?? (() => Date.now());
  const pageSizePx = options.pageSizePx;
  const axis = options.axis ?? 'horizontal';

  let accum = 0;
  let dir = null; // 'neg' | 'pos' | null — 目前累積/冷卻中的方向（沿主軸）
  let cooldownUntil = 0;
  let lastEventAt = null;

  /**
   * 餵入一個 wheel 事件。回傳是否本次呼叫觸發了方向 callback，供呼叫端決定要不要
   * `event.preventDefault()`——預設建議只在真的觸發導航時擋、未達門檻的 tick 放行；但這只是
   * 建議，不是強制契約。102d P2（Codex 三審）：overlay 垂直分支（search/showcase 的
   * lightbox/sample gallery）沒有可靠的底層捲動鎖存在時，呼叫端可以不看回傳值、一律
   * `preventDefault()`（含未達門檻的 sub-threshold tick）——回傳值仍照實反映「這次呼叫是否
   * 觸發了 callback」，是否 preventDefault 完全是呼叫端的判斷，本函式不對此有意見。
   */
  function feed(event, callbacks = {}) {
    const dx = normalizeDelta(event.deltaX, event.deltaMode, pageSizePx);
    const dy = normalizeDelta(event.deltaY, event.deltaMode, pageSizePx);

    // 102d P2b：主軸/交叉軸依 axis 選定；門檻/冷卻/方向反轉解鎖邏輯完全共用，只換軸別
    // （等效於 axis==='horizontal' 時沿用原本 isHorizontalWheel 判斷、'vertical' 時鏡像
    // isVerticalWheel 判斷——兩者皆用 `|主軸| <= |交叉軸|` 提早 return，含相等/(0,0) 邊界）。
    const primary = axis === 'vertical' ? dy : dx;
    const cross = axis === 'vertical' ? dx : dy;
    if (Math.abs(primary) <= Math.abs(cross)) return false;

    const t = now();
    const newDir = primary < 0 ? 'neg' : 'pos';

    // 停頓 ≥ cooldownMs（事件流中斷）視為全新一撥：重置累積 + 冷卻
    const stalled = lastEventAt !== null && (t - lastEventAt) >= cooldownMs;
    // 方向反轉：立即解鎖（不等冷卻窗跑完）
    const reversed = dir !== null && newDir !== dir;

    if (stalled || reversed) {
      accum = 0;
      cooldownUntil = 0;
    }
    dir = newDir;
    lastEventAt = t;

    if (t < cooldownUntil) return false; // 冷卻中：吃掉這次 delta，不累積、不觸發

    accum += primary;
    if (Math.abs(accum) < threshold) return false;

    accum = 0;
    cooldownUntil = t + cooldownMs;

    if (axis === 'vertical') {
      if (newDir === 'neg') callbacks.onUp?.();
      else callbacks.onDown?.();
    } else {
      if (newDir === 'neg') callbacks.onLeft?.();
      else callbacks.onRight?.();
    }
    return true;
  }

  return { feed };
}
