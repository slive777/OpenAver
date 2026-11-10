/**
 * media-probe-reminder-logic.js — 影片資訊讀取提醒的畫面判斷（TASK-198a-T5）
 *
 * 純函式：無 DOM／Alpine／window。數字一律用後端給的值，這裡不自算 N。
 */

/**
 * 判斷順序固定：dismissed → unavailable → running → pending → readonly_only。
 * `later` 只影響 pending 這一格（「稍後」只收起這次的「N 部＋開始讀取」）。
 */
export function reminderView(status, { later = false } = {}) {
    const s = status || {};
    const job = s.job || {};
    const pending = Number(s.pending) || 0;
    const readonlyPending = Number(s.readonly_pending) || 0;
    const done = Number(job.done) || 0;
    const total = Number(job.total) || 0;
    const view = {
        mode: 'hidden',
        pending,
        readonlyPending,
        done,
        total,
        percent: total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0,
    };
    if (s.dismissed) return view;
    if (s.available === false) return { ...view, mode: 'unavailable' };
    if (job.running) return { ...view, mode: 'running' };
    if (pending > 0) return { ...view, mode: later ? 'hidden' : 'pending' };
    if (s.include_readonly === false && readonlyPending > 0) return { ...view, mode: 'readonly_only' };
    return view;
}

/**
 * 輪詢中某次 GET /status 失敗（瞬斷／5xx）後要不要照常排下一次：
 * 只看「最後已知狀態」job 是否在跑；從未載入成功（null）＝初次載入失敗，不重試。
 */
export function keepPollingAfterFailure(lastStatus) {
    return Boolean(lastStatus && lastStatus.job && lastStatus.job.running);
}
