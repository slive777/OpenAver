/**
 * media-probe-reminder-logic.js — 影片資訊讀取區塊的畫面判斷（TASK-a205-T6a）
 *
 * 純函式：無 DOM／Alpine／window。數字一律用後端給的值，這裡不自算 N。
 */

/**
 * 判斷順序固定：dismissed → unavailable → running → pending → null。
 * `later` 只影響 pending 這一格（「稍後」只收起這次的「N 部＋開始讀取」）。
 */
export function probeBlockView(status, { later = false } = {}) {
    if (status == null) {
        return { show: false, line1: null, showToggle: false, toggleChecked: false, readonlyHint: null, pending: 0, done: 0, total: 0, percent: 0, etaS: null };
    }
    const s = status;
    const job = s.job || {};
    const pending = Number(s.pending) || 0;
    const readonlyPending = Number(s.readonly_pending) || 0;
    const done = Number(job.done) || 0;
    const total = Number(job.total) || 0;
    let line1 = null;
    if (s.dismissed) {
        line1 = null;
    } else if (s.available === false) {
        line1 = 'unavailable';
    } else if (job.running) {
        line1 = 'running';
    } else if (pending > 0 && !later) {
        line1 = 'pending';
    } else {
        line1 = null;
    }
    const showToggle = s.available !== false && s.has_readonly_source === true;
    const toggleChecked = s.include_readonly === true;
    const readonlyHint = (s.include_readonly !== true && readonlyPending > 0) ? readonlyPending : null;
    const show = line1 !== null || showToggle;
    const etaS = Number.isFinite(job.eta_s) ? job.eta_s : null;
    return {
        show, line1, showToggle, toggleChecked, readonlyHint,
        pending, done, total,
        percent: total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0,
        etaS,
    };
}

/**
 * 完成提示判定（CD-205a-8，I-F2）：寫入新狀態前，以舊 mpStatus 當 prev、
 * 本次套用的 data 當 next。短 job 在第一次查詢前就讀完靠 startedHere 補上。
 */
export function shouldToastFinish(prev, next, { startedHere = false } = {}) {
    return Boolean((prev?.job?.running || startedHere) && !next?.job?.running && next?.job?.last_result);
}

/**
 * 輪詢中某次 GET /status 失敗（瞬斷／5xx）後要不要照常排下一次：
 * 只看「最後已知狀態」job 是否在跑；從未載入成功（null）＝初次載入失敗，不重試。
 */
export function keepPollingAfterFailure(lastStatus) {
    return Boolean(lastStatus && lastStatus.job && lastStatus.job.running);
}
