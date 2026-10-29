/**
 * picker-seen.js — 換照片畫面「這次看過的候選」純邏輯（185-T4，CD-185-13）。
 * 抽出理由同 actress-sync.js：state-lightbox-picker.js 用 `@/` alias，plain Node 無法 import。
 */

export const MAX_SENT = 500;

/** 去重、不淘汰、回新陣列（供 Alpine 賦值觸發 reactivity）；空 id 忽略。 */
export function addSeen(list, id) {
    if (!id || list.includes(id)) return list.slice();
    return [...list, id];
}

/** 組 photo-candidates 網址：首開（attempt 0 且無 seen）與舊網址逐位相同；exclude 只送最新 MAX_SENT 個。 */
export function buildCandidatesUrl(name, attempt, seen) {
    const base = `/api/actresses/${encodeURIComponent(name)}/photo-candidates`;
    const sent = seen.slice(-MAX_SENT);
    if (attempt === 0 && sent.length === 0) return base;
    const q = [];
    if (attempt > 0) q.push(`attempt=${attempt}`);
    if (sent.length > 0) q.push(`exclude=${sent.join(',')}`);
    return `${base}?${q.join('&')}`;
}
