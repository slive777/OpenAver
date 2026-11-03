/**
 * ai-tags-logic.js — AI tags panel pure functions (TASK-188c-T7)
 *
 * panelMode / backfillAction / statusLine / connShown / connEnabled /
 * pickTagsModel / costHint / formatUsd / buildTagsTestBody / testResultLine.
 * No DOM, no component bindings, no i18n lookup.
 */

const COST_FAMILIES = [
    { family: 'haiku', label: 'Haiku 5.5', per1000: 0.43 },
    { family: 'luna', label: 'GPT-6 Luna', per1000: 0.24 },
    { family: 'flash-lite', label: 'Gemini 3.5 Flash-Lite', per1000: 0.72 },
];

const COST_PROVIDERS = new Set(['claude', 'gemini', 'openai_official']);

const STOP_KEYS = {
    unreachable: 'settings.ai.tags.status_stopped_unreachable',
    auth: 'settings.ai.tags.status_stopped_auth',
    model_unsupported: 'settings.ai.tags.status_stopped_model_unsupported',
    quota: 'settings.ai.tags.status_stopped_quota',
    not_configured: 'settings.ai.tags.status_stopped_not_configured',
    disabled: 'settings.ai.tags.status_stopped_disabled',
};

/** Toggle decides empty / fields. */
export function panelMode(form) {
    return form.aiTagsEnabled ? 'fields' : 'empty';
}

/**
 * Backfill button action. Returns { action, disabled, reason }.
 * running -> stop (always pressable); resumable -> continue; pending>0 -> start.
 */
export function backfillAction(status, { dirty = false, enabled = true } = {}) {
    if (!status) return { action: null, disabled: true, reason: null };
    if (status.running) return { action: 'stop', disabled: false, reason: null };

    let action = null;
    if (status.resumable) action = 'continue';
    else if (status.pending > 0) action = 'start';

    if (!action) return { action: null, disabled: true, reason: null };
    if (!enabled) return { action, disabled: true, reason: 'not_enabled' };
    if (dirty) return { action, disabled: true, reason: 'dirty' };
    return { action, disabled: false, reason: null };
}

/** Connection block visibility (translate selection; ignores translateEnabled). */
export function connShown(form, p) {
    return form.translateProvider === p
        || Boolean(form.aiTagsEnabled && form.aiTagsProvider === p);
}

/** Connection block editable (translate on+selected, or tags on+selected). */
export function connEnabled(form, p) {
    const byTranslate = Boolean(form.translateEnabled && form.translateProvider === p);
    const byTags = Boolean(form.aiTagsEnabled && form.aiTagsProvider === p);
    return byTranslate || byTags;
}

/** List item name (string or {name}). */
function listName(item) {
    if (typeof item === 'string') return item;
    if (item && typeof item.name === 'string') return item.name;
    return '';
}

/**
 * Default model: keep non-empty current; else pick by provider family.
 * Empty list / not found -> ''.
 */
export function pickTagsModel(provider, current, list) {
    if (current) return current;
    const items = Array.isArray(list) ? list : [];
    const names = items.map(listName).filter(Boolean);
    if (names.length === 0) return '';
    if (provider === 'claude') {
        return names.find((n) => n.toLowerCase().includes('haiku')) || '';
    }
    if (provider === 'gemini') return 'gemini-flash-lite-latest';
    if (provider === 'openai_official') {
        return names.find((n) => n.toLowerCase().includes('luna')) || '';
    }
    return names[0];
}

/** Cost hint; returns null when family/provider do not match. */
export function costHint(provider, model, n) {
    if (!COST_PROVIDERS.has(provider)) return null;
    if (typeof model !== 'string') return null;
    const lower = model.toLowerCase();
    const hit = COST_FAMILIES.find((f) => lower.includes(f.family));
    if (!hit) return null;
    const count = (typeof n === 'number' && Number.isFinite(n) && n >= 0) ? n : 0;
    return {
        label: hit.label,
        per1000: hit.per1000,
        total: hit.per1000 * count / 1000,
    };
}

/** USD display: 0 < v < 0.01 -> '<0.01', else toFixed(2). */
export function formatUsd(v) {
    if (typeof v === 'number' && v > 0 && v < 0.01) return '<0.01';
    return Number(v).toFixed(2);
}

/** Test-button body: secrets as-is; omit absent fields. */
export function buildTagsTestBody(form) {
    const body = {
        provider: form.aiTagsProvider,
        model: form.aiTagsModel,
    };
    const p = form.aiTagsProvider;
    if (p === 'ollama') {
        body.base_url = form.ollamaUrl;
    } else if (p === 'gemini') {
        body.api_key = form.geminiApiKey;
    } else if (p === 'claude') {
        body.api_key = form.claudeApiKey;
    } else if (p === 'openai_official') {
        body.api_key = form.openaiOfficialApiKey;
    } else if (p === 'openai') {
        body.base_url = typeof form.openaiBaseUrl === 'string'
            ? form.openaiBaseUrl.trim()
            : form.openaiBaseUrl;
        body.api_key = form.openaiApiKey;
    }
    return body;
}

/** Test-result line. Returns { key, params }. */
export function testResultLine(data) {
    if (!data) {
        return { key: 'settings.ai.tags.test_failed_generic', params: {} };
    }
    if (data.ok) {
        const tags = Array.isArray(data.tags) ? data.tags : [];
        if (tags.length > 0) {
            return {
                key: 'settings.ai.tags.test_ok',
                params: { tags: tags.join('\u3001') },
            };
        }
        return { key: 'settings.ai.tags.test_ok_no_tags', params: {} };
    }
    if (data.outcome === 'unreachable') {
        return { key: 'settings.ai.tags.test_unreachable', params: {} };
    }
    if (data.outcome === 'unusable') {
        const detail = data.detail;
        if (detail === 'model_unsupported') {
            return { key: 'settings.ai.tags.test_unusable_model_unsupported', params: {} };
        }
        if (detail === 'bad_response') {
            return { key: 'settings.ai.tags.test_unusable_bad_response', params: {} };
        }
        if (detail === 'refused') {
            return { key: 'settings.ai.tags.test_unusable_refused', params: {} };
        }
        if (detail === 'no_tags') {
            return { key: 'settings.ai.tags.test_unusable_no_tags', params: {} };
        }
        return { key: 'settings.ai.tags.test_failed_generic', params: {} };
    }
    if (data.outcome === 'not_configured') {
        return { key: 'settings.ai.tags.test_not_configured', params: {} };
    }
    return { key: 'settings.ai.tags.test_failed_generic', params: {} };
}

/** unix seconds -> local HH:MM; invalid -> ''. */
function formatHm(epochSec) {
    if (typeof epochSec !== 'number' || !Number.isFinite(epochSec)) return '';
    const d = new Date(epochSec * 1000);
    if (Number.isNaN(d.getTime())) return '';
    const p2 = (n) => String(n).padStart(2, '0');
    return `${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/**
 * Status-line descriptor. Returns { key, params, extra }; extra is a key array.
 * Does not call i18n lookup.
 */
export function statusLine(status) {
    if (!status) {
        return {
            key: 'settings.ai.tags.status_none',
            params: { n: 0, m: 0, k: 0, time: '' },
            extra: [],
        };
    }

    const tagged = status.tagged || 0;
    const total = status.total || 0;
    const pending = status.pending || 0;
    const skipped = status.skipped || 0;
    const time = formatHm(status.last_success_at);

    const baseParams = { n: tagged, m: total, k: skipped, time };

    if (status.running) {
        const extra = [];
        if (status.slow) extra.push('settings.ai.tags.status_slow_extra');
        if (status.waiting) extra.push('settings.ai.tags.status_waiting_extra');
        if (skipped > 0) extra.push('settings.ai.tags.status_skipped_extra');
        return {
            key: 'settings.ai.tags.status_running',
            params: baseParams,
            extra,
        };
    }

    if (status.stop_reason && STOP_KEYS[status.stop_reason]) {
        const extra = skipped > 0 ? ['settings.ai.tags.status_skipped_extra'] : [];
        return {
            key: STOP_KEYS[status.stop_reason],
            params: baseParams,
            extra,
        };
    }

    if (status.unreachable) {
        const extra = skipped > 0 ? ['settings.ai.tags.status_skipped_extra'] : [];
        return {
            key: time
                ? 'settings.ai.tags.status_unreachable'
                : 'settings.ai.tags.status_unreachable_no_time',
            params: baseParams,
            extra,
        };
    }

    if (status.resumable) {
        const extra = skipped > 0 ? ['settings.ai.tags.status_skipped_extra'] : [];
        return {
            key: 'settings.ai.tags.status_incomplete',
            params: { n: pending, m: total, k: skipped, time },
            extra,
        };
    }

    const extra = skipped > 0 ? ['settings.ai.tags.status_skipped_extra'] : [];
    return {
        key: time
            ? 'settings.ai.tags.status_ready'
            : 'settings.ai.tags.status_ready_no_time',
        params: baseParams,
        extra,
    };
}
