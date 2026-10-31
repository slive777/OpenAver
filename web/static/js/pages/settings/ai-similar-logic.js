/**
 * ai-similar-logic.js — 圖片相似分頁純函式（TASK-186-T6）
 *
 * panelMode／indexAction／statusLine／rebuildVisible／rebuildOutcome＋CHECK_KEYS。無 DOM、無 Alpine、無 window.t。
 */

/** check 值 → i18n key（含未知值的通用文案）。 */
export const CHECK_KEYS = {
    auth: 'settings.ai.similar.check_auth',
    http_4xx: 'settings.ai.similar.check_http_4xx',
    http_5xx: 'settings.ai.similar.check_http_5xx',
    not_json: 'settings.ai.similar.check_not_json',
    shape: 'settings.ai.similar.check_shape',
    no_model: 'settings.ai.similar.check_no_model',
    not_numeric: 'settings.ai.similar.check_not_numeric',
    dim_range: 'settings.ai.similar.check_dim_range',
    zero_norm: 'settings.ai.similar.check_zero_norm',
    dim_mismatch: 'settings.ai.similar.check_dim_mismatch',
    unstable: 'settings.ai.similar.check_unstable',
    not_discriminative: 'settings.ai.similar.check_not_discriminative',
    model_flapping: 'settings.ai.similar.check_model_flapping',
    unknown: 'settings.ai.similar.check_unknown',
};

/** 開關決定 empty／fields；網址空仍為 fields。 */
export function panelMode(form) {
    return form.aiSimilarEnabled ? 'fields' : 'empty';
}

/** 索引鈕動作：stop／rebuild／continue／build／retry／null。 */
export function indexAction(status, testPassedThisSession) {
    if (!status) return null;
    if (status.running) return 'stop';
    if (status.model_changed) return 'rebuild';
    const hasModel = Boolean(status.model);
    if (hasModel && (status.pending > 0 || !status.complete)) return 'continue';
    if (!hasModel && testPassedThisSession) return 'build';
    // 已完成但有讀不到的封面：NAS 接回後可重試（後端會清 unreadable 再算）
    if (hasModel && status.unreadable > 0) return 'retry';
    return null;
}

/** 「刪除並重建」鈕可見：開關開 ∧ 已有向量或讀不到的片 ∧ 沒有工作在跑。 */
export function rebuildVisible(status, enabled) {
    if (!enabled || !status || status.running) return false;
    return (status.indexed || 0) + (status.unreadable || 0) > 0;
}

/** 重建回應對應：started／busy（already_running）／test_failed／error。 */
export function rebuildOutcome(httpOk, data) {
    if (!httpOk || !data) return 'error';
    if (data.status === 'started') return 'started';
    if (data.status === 'already_running') return 'busy';
    if (data.status === 'test_failed') return 'test_failed';
    return 'error';
}

/** unix 秒 → 本地 HH:MM；無效回 ''。 */
function formatHm(epochSec) {
    if (typeof epochSec !== 'number' || !Number.isFinite(epochSec)) return '';
    const d = new Date(epochSec * 1000);
    if (Number.isNaN(d.getTime())) return '';
    const p2 = (n) => String(n).padStart(2, '0');
    return `${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/**
 * 狀態列文案描述。回傳 { key, params, extra }；函式不呼叫 window.t。
 * now 保留簽名（CD-186-17）但不使用。
 */
export function statusLine(status, now) {
    void now;
    if (!status) {
        return { key: 'settings.ai.similar.status_none', params: {}, extra: null };
    }
    if (status.model_changed) {
        return { key: 'settings.ai.similar.status_model_changed', params: {}, extra: null };
    }
    if (status.running) {
        const n = (status.indexed || 0) + (status.unreadable || 0);
        return {
            key: 'settings.ai.similar.status_running',
            params: { n, m: status.total || 0 },
            extra: null,
        };
    }
    if (status.unreachable) {
        const time = formatHm(status.last_success_at);
        const unreadable = status.unreadable || 0;
        return {
            key: 'settings.ai.similar.status_unreachable',
            params: { time, k: unreadable },
            extra: unreadable > 0 ? 'settings.ai.similar.status_unreadable_extra' : null,
        };
    }
    const hasModel = Boolean(status.model);
    if (hasModel && (status.pending > 0 || !status.complete)) {
        const unreadable = status.unreadable || 0;
        return {
            key: 'settings.ai.similar.status_incomplete',
            params: { n: status.pending || 0, k: unreadable },
            extra: unreadable > 0 ? 'settings.ai.similar.status_unreadable_extra' : null,
        };
    }
    if (hasModel) {
        const unreadable = status.unreadable || 0;
        return {
            key: 'settings.ai.similar.status_ready',
            params: {
                n: status.indexed || 0,
                m: status.total || 0,
                model: status.model,
                time: formatHm(status.last_success_at),
                k: unreadable,
            },
            extra: unreadable > 0 ? 'settings.ai.similar.status_unreadable_extra' : null,
        };
    }
    return { key: 'settings.ai.similar.status_none', params: {}, extra: null };
}
