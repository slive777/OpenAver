/**
 * ai-backfill-logic.js — 三個 AI 補跑分頁（圖片相似／人臉／AI 標籤）共用純函式（TASK-189a-T10）
 *
 * normalizeStatus／actionOf／extraActionOf／rebuildVisible／progressLine／pendingLine。
 * 簽名一律 adapter 在前：adapter 由各 ai-*-logic.js 匯出，負責「功能獨有的那一半」。
 * 純函式：不碰頁面節點、不碰前端框架、不查翻譯表；描述子只放 key。
 *
 * view ＝ adapter.normalize(raw) 的回傳：
 *   { running, processed, total, pending, resumable, lastSuccessAt, unreachable, stopReason, raw }
 *
 * 舊 → 新動作映射表（測試以此表驅動）
 *   功能  舊函式回傳         新 actionOf  新 extraAction  新通用 rebuildVisible
 *   相似  indexAction null    null          null            ＝舊 rebuildVisible
 *         'stop'              'stop'        null            false
 *         'continue'          resumable? 'continue' : 'start'  null  ＝舊 rebuildVisible
 *         'build'             'start'       null            ＝舊 rebuildVisible
 *         'retry'             null          'retry'         ＝舊 rebuildVisible
 *         'rebuild'           null          null            true
 *   人臉  recomputeAction 'stop'    'stop'      null        false
 *         'resume'            resumable? 'continue' : 'start'  null  ＝舊 deleteRebuildVisible
 *         'none'              null          null            ＝舊 deleteRebuildVisible
 *   只有中途停下（view.resumable）才叫 'continue'；沒在中途停下但有待補一律 'start'。
 *   標籤  backfillAction {action,disabled,reason}  整物件相同  null  enabled ∧ !running ∧ total>0
 */

/** unix 秒 → 本地 HH:MM；無效回 ''。 */
function formatHm(epochSec) {
    if (typeof epochSec !== 'number' || !Number.isFinite(epochSec)) return '';
    const d = new Date(epochSec * 1000);
    if (Number.isNaN(d.getTime())) return '';
    const p2 = (n) => String(n).padStart(2, '0');
    return `${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/** 補齊 ctx 預設值（不 mutate 傳入物件）。 */
function fullCtx(ctx) {
    const c = ctx || {};
    const { enabled = true, dirty = false, busy = false, blocked = null, testPassed = false } = c;
    return { enabled, dirty, busy, blocked, testPassed };
}

/** 意圖 → { action, disabled, reason }。stop 永不鎖。 */
function gate(intent, c) {
    if (!intent) return { action: null, disabled: true, reason: null };
    if (intent === 'stop') return { action: 'stop', disabled: false, reason: null };
    if (!c.enabled) return { action: intent, disabled: true, reason: 'not_enabled' };
    if (c.dirty) return { action: intent, disabled: true, reason: 'dirty' };
    if (c.busy) return { action: intent, disabled: true, reason: 'busy' };
    if (typeof c.blocked === 'string' && c.blocked) {
        return { action: intent, disabled: true, reason: c.blocked };
    }
    return { action: intent, disabled: false, reason: null };
}

/** raw 狀態 → view；raw 為 null／undefined 回 null。 */
export function normalizeStatus(adapter, raw) {
    if (raw === null || raw === undefined) return null;
    return adapter.normalize(raw);
}

/** 主動作：{ action: 'stop'|'start'|'continue'|null, disabled, reason }。 */
export function actionOf(adapter, view, ctx) {
    if (!view) return { action: null, disabled: true, reason: null };
    const c = fullCtx(ctx);
    return gate(adapter.actionOf(view, c), c);
}

/** 副動作（目前只有相似的 'retry'）：{ action: 'retry'|null, disabled, reason }。 */
export function extraActionOf(adapter, view, ctx) {
    if (!view) return { action: null, disabled: true, reason: null };
    const c = fullCtx(ctx);
    return gate(adapter.extraAction(view, c), c);
}

/** 「刪除並重建」鈕可見：共同前綴（有狀態、沒在跑、功能已開）∧ 功能獨有條件。 */
export function rebuildVisible(adapter, view, ctx) {
    if (!view || view.running) return false;
    const c = fullCtx(ctx);
    if (c.enabled === false) return false;
    return Boolean(adapter.rebuildVisible(view, c));
}

/** 進行中進度列描述子；非進行中回 null。 */
export function progressLine(view) {
    if (!view || !view.running) return null;
    const time = formatHm(view.lastSuccessAt);
    return {
        key: 'settings.ai.backfill.progress_running',
        params: { n: view.processed, m: view.total, time },
        extra: time ? 'settings.ai.backfill.progress_last_success' : null,
    };
}

/** 「還有 N 部沒跑」描述子；進行中或沒有待補回 null。 */
export function pendingLine(view) {
    if (!view || view.running || !(view.pending > 0)) return null;
    return { key: 'settings.ai.backfill.pending_line', params: { n: view.pending } };
}
