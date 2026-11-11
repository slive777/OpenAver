/**
 * lbx-logic.js — 影片燈箱規格帶純函式（199a-T2）
 *
 * formatRuntime：實際片長（分鐘）→ h:mm。
 * bandParts：規格帶項目（等級 · 編碼 · 實際片長 · 大小）；缺的項目直接省略。
 * 只用相對 import（FE-GUARD-11）；本檔零 Alpine、零 window。
 */

export function formatRuntime(min) {
    const total = Math.round(Number(min));
    if (!Number.isFinite(total) || total < 1) return '';
    return Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0');
}

export function bandParts(video, { formatSize, formatRuntime }) {
    if (!video) return [];
    const parts = [];
    if (video.resolution_tier) parts.push({ id: 'tier', text: video.resolution_tier });
    if (video.media_codec) parts.push({ id: 'codec', text: video.media_codec });
    const runtime = formatRuntime(video.media_duration_min);
    if (runtime) parts.push({ id: 'runtime', text: runtime });
    if (video.size) parts.push({ id: 'size', text: formatSize(video.size) });
    return parts;
}

/**
 * placePop：浮層位置（199a-T3，CD-199a-4）。
 * mode 是「位置模式」：'below'＝錨點下緣＋gap；'inplace'＝錨點上緣−4（T4 的片名／原文才用）。
 * 恆不低於封面下緣＋4（浮層不蓋封面）；超出視窗底就上移；interactive（點開類）才回 maxHeight 內捲，純閱讀類不內捲。
 * align：'left'（預設）左緣對齊錨點；'right' 右緣對齊錨點（⋯ 選單）。
 */
export function placePop({ anchorRect, coverBottom, vw, vh, popSize, mode, align = 'left', interactive = false, margin = 8, gap = 6 }) {
    const floor = coverBottom + 4;
    const bottomLimit = vh - margin;
    let top = mode === 'inplace' ? anchorRect.top - 4 : anchorRect.bottom + gap;
    top = Math.max(top, floor);
    if (top + popSize.h > bottomLimit) top = Math.max(floor, bottomLimit - popSize.h);
    const maxHeight = interactive && top + popSize.h > bottomLimit ? Math.max(0, bottomLimit - top) : undefined;
    const anchorX = align === 'right' ? anchorRect.right - popSize.w : anchorRect.left;
    const left = Math.min(Math.max(anchorX, margin), Math.max(margin, vw - popSize.w - margin));
    return { left, top, maxHeight };
}

/** isOutsidePop：pointerdown 的目標是否在浮層與其錨點之外（錨點內的點擊不算外面，免得「先收再重開」）。 */
export function isOutsidePop(target, panelEl, anchorSel) {
    if (!target || typeof target.closest !== 'function') return true;
    if (panelEl && panelEl.contains(target)) return false;
    return !target.closest(anchorSel);
}

/**
 * menuItems：⋯ 選單項目（199a-T4，CD-199a-11）。順序固定 samples → translate → rescrape → delete。
 * 沒有對應檔（hasPath 假）只剩 rescrape；有劇照不出 samples；翻譯條件不成立不出 translate。
 */
export function menuItems(video, { sampleCount, trVisible, hasPath }) {
    const items = [];
    if (hasPath && sampleCount === 0) items.push({ id: 'samples' });
    if (hasPath && trVisible) items.push({ id: 'translate' });
    items.push({ id: 'rescrape' });
    if (hasPath) items.push({ id: 'delete' });
    return items;
}

/** popPlacement：各 kind 的位置模式與水平對齊（199a-T4）。 */
export function popPlacement(kind) {
    if (kind === 'title' || kind === 'otitle') return { mode: 'inplace', align: 'left' };
    if (kind === 'menu') return { mode: 'below', align: 'right' };
    return { mode: 'below', align: 'left' };
}

/** hasDistinctOtitle：有原文且與片名不同才畫第 2 列。 */
export function hasDistinctOtitle(video) {
    const o = String(video?.original_title || '').trim();
    return !!o && o !== String(video?.title || '').trim();
}
