// 199a-T1：垂直滾輪「交還原生捲動」判定（handleWheel 的 vertical 分支）。
// 交還：.lbx-pop 浮層內、女優 .lightbox-metadata（今天可捲），以及 .lbx-meta 在「可捲且真的溢出」時
// （overflow-y 為 auto／scroll）。不溢出時滾輪仍用於換片。
export function shouldYieldVerticalWheel(target) {
    if (target.closest(WHEEL_VERTICAL_EXCLUDE_SELECTOR)) return true;
    const meta = target.closest('.lbx-meta, .lbx-ap-meta');
    if (!meta) return false;
    const oy = getComputedStyle(meta).overflowY;
    return (oy === 'auto' || oy === 'scroll') && meta.scrollHeight > meta.clientHeight;
}

// 102d P2b（owner 拍板 2026-07-19）：overlay 內可垂直捲動的子容器——垂直滾輪命中時交還原生捲動，
// 不吃導航（僅 vertical 分支檢查，horizontal 分支不受影響、行為不變）。
// 199a-T1：女優 .lightbox-metadata（無 .lbx-meta）一律交還；影片的 .lbx-meta 排除在外，改由
// shouldYieldVerticalWheel 看實際可捲狀態決定；.lbx-pop 為影片燈箱浮層（T3 起才有此 DOM）。
// 199b-T4：女優資料區 .lbx-ap-meta 平常 overflow:hidden（捲不動）→ 與 .lbx-meta 同一套「可捲且真溢出才交還」。
const WHEEL_VERTICAL_EXCLUDE_SELECTOR = '.lightbox-metadata:not(.lbx-meta):not(.lbx-ap-meta), .lbx-pop';

