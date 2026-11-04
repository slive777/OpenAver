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
        // 跑中：進度行已有「已處理 n／m」，這裡不重述（params 保留供對照）
        return {
            key: null,
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
        // 閒置未完成：「還有 N 部沒跑」已表示待處理，這裡只留非重述的「封面讀不到」
        return {
            key: null,
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

/** 補跑共用層 adapter（TASK-189a-T10）：只放功能獨有的那一半。 */
export const adapter = {
    tab: 'similar',
    urls: {
        status: '/api/ai/similar/status',
        start: '/api/ai/similar/index',
        rebuild: '/api/ai/similar/index/rebuild',
        stop: '/api/ai/similar/index/stop',
    },
    normalize(raw) {
        return {
            running: Boolean(raw.running),
            processed: (raw.indexed || 0) + (raw.unreadable || 0),
            total: raw.total || 0,
            pending: raw.model_changed ? 0 : (raw.pending || 0),
            // 上一輪建索引中途停下：已定模型、索引未 complete（begin/reset 寫 '0'、跑完才 '1'）、已有進度
            resumable: Boolean(raw.model) && !raw.complete && !raw.model_changed
                && (raw.indexed || 0) + (raw.unreadable || 0) > 0,
            lastSuccessAt: raw.last_success_at ?? null,
            unreachable: Boolean(raw.unreachable),
            stopReason: null,
            raw,
        };
    },
    actionOf(view, ctx) {
        const s = view.raw;
        if (view.running) return 'stop';
        if (s.model_changed) return null;
        const hasModel = Boolean(s.model);
        if (hasModel && (s.pending > 0 || !s.complete)) return view.resumable ? 'continue' : 'start';
        if (!hasModel && ctx.testPassed) return 'start';
        return null;
    },
    extraAction(view) {
        const s = view.raw;
        if (view.running || s.model_changed || !s.model) return null;
        if ((s.pending || 0) > 0 || !s.complete) return null;
        return (s.unreadable || 0) > 0 ? 'retry' : null;
    },
    rebuildVisible(view) {
        const s = view.raw;
        return Boolean(s.model_changed) || (s.indexed || 0) + (s.unreadable || 0) > 0;
    },
    rebuildConfirm(view) {
        const s = view.raw;
        return {
            key: 'settings.ai.similar.rebuild_confirm',
            params: { n: (s.indexed || 0) + (s.unreadable || 0) },
        };
    },
};
