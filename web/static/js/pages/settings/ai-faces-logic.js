/**
 * ai-faces-logic.js — 人臉分頁純函式（TASK-187a-T5）
 *
 * panelMode／statusLine／recomputeLine／recomputeAction／deleteRebuildVisible＋CHECK_KEYS。
 * 無 DOM、無 Alpine、無 window.t。
 */

/** check 值 → i18n key（含未知值的通用文案）。 */
export const CHECK_KEYS = {
    auth: 'settings.ai.faces.check_auth',
    http_4xx: 'settings.ai.faces.check_http_4xx',
    http_5xx: 'settings.ai.faces.check_http_5xx',
    not_json: 'settings.ai.faces.check_not_json',
    shape: 'settings.ai.faces.check_shape',
    no_model: 'settings.ai.faces.check_no_model',
    no_face: 'settings.ai.faces.check_no_face',
    center_off: 'settings.ai.faces.check_center_off',
    unknown: 'settings.ai.faces.check_unknown',
};

/** 開關決定 empty／fields；網址空仍為 fields。 */
export function panelMode(form) {
    return form.aiFacesEnabled ? 'fields' : 'empty';
}

/** 重算鈕動作：stop／resume／none。target_model 空時不顯示繼續（後端會 no_target）。 */
export function recomputeAction(status) {
    if (!status) return 'none';
    if (status.running) return 'stop';
    if ((status.pending || 0) > 0 && status.target_model) return 'resume';
    return 'none';
}

/** 「刪除並重新對焦」鈕可見：開關開 ∧ rebuild_count>0 ∧ 沒有工作在跑。 */
export function deleteRebuildVisible(status, enabled) {
    if (!enabled || !status || status.running) return false;
    return (status.rebuild_count || 0) > 0;
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
 * 「目前使用」狀態列。回傳 { key, params, extra }；函式不呼叫 window.t。
 * 模型名取 target_model（T4b 實作欄位；無 observed_model）。
 */
export function statusLine(status) {
    if (!status) {
        return { key: 'settings.ai.faces.status_local', params: {}, extra: null };
    }
    if (status.degraded) {
        return {
            key: 'settings.ai.faces.status_local_degraded',
            params: { time: formatHm(status.last_success_at) },
            extra: null,
        };
    }
    if (status.using === 'external') {
        if (!status.observed) {
            return {
                key: 'settings.ai.faces.status_external_unobserved',
                params: {},
                extra: null,
            };
        }
        return {
            key: 'settings.ai.faces.status_external',
            params: {
                model: status.target_model || '',
                time: formatHm(status.last_success_at),
            },
            extra: null,
        };
    }
    return { key: 'settings.ai.faces.status_local', params: {}, extra: null };
}

/**
 * 重算進度列。無事可報回 null；stopped_reason 優先於「未完成」。
 */
export function recomputeLine(status) {
    if (!status) return null;
    if (status.running) {
        return {
            key: 'settings.ai.faces.recompute_running',
            params: { n: status.processed || 0, m: status.total || 0 },
            extra: null,
        };
    }
    // 尚未有目標模型（開關剛開未存）時 pending 會是全部候選——不顯示未完成／已停止。
    if (!status.target_model) return null;
    // 只有 contract／unreachable 顯示「已停止」句；disabled（使用者關端點）走下方未完成。
    if (status.stopped_reason === 'contract') {
        return {
            key: 'settings.ai.faces.recompute_stopped_contract',
            params: {},
            extra: null,
        };
    }
    if (status.stopped_reason === 'unreachable') {
        return {
            key: 'settings.ai.faces.recompute_stopped_unreachable',
            params: {},
            extra: null,
        };
    }
    if ((status.pending || 0) > 0) {
        const unreadable = status.unreadable || 0;
        return {
            key: 'settings.ai.faces.recompute_incomplete',
            params: { n: status.pending || 0, k: unreadable },
            extra: unreadable > 0 ? 'settings.ai.faces.recompute_unreadable_extra' : null,
        };
    }
    return null;
}
