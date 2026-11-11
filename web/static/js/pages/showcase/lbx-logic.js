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
