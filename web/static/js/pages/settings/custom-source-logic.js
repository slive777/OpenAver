/**
 * custom-source-logic.js — 自訂來源的狀態→點／文案純邏輯（無 DOM、無 Alpine、無 window）
 *
 * 供設定頁自訂來源膠囊與 node:test 使用。`t` 由呼叫端注入。
 * 所有 key 表都是明確物件字面（不動態拼 key，FE-JS-06）。
 */

import { PROBE_ICON_MAP } from './source-probe-logic.js';

/** 五態 → 探測狀態點（verifying 是前端暫態，不在表內）。 */
const STATUS_STATE_MAP = {
    passed: 'ok',
    failed: 'blocked',
    load_failed: 'unreachable',
    unverified: 'skipped',
};

const STATUS_KEY_MAP = {
    passed: 'settings.sources.custom_status_passed',
    failed: 'settings.sources.custom_status_failed',
    load_failed: 'settings.sources.custom_status_load_failed',
    unverified: 'settings.sources.custom_status_unverified',
    verifying: 'settings.sources.custom_status_verifying',
};

/** 後綴 → 動詞 key；'' 是預設（不進迴圈）。 */
const VERB_KEY_MAP = {
    _contains: 'settings.sources.custom_verb_contains',
    _include: 'settings.sources.custom_verb_include',
    _exclude: 'settings.sources.custom_verb_exclude',
    _max: 'settings.sources.custom_verb_max',
};
const VERB_KEY_DEFAULT = 'settings.sources.custom_verb_equal';

export function customStatusToProbeState(status) {
    return Object.hasOwn(STATUS_STATE_MAP, status) ? STATUS_STATE_MAP[status] : null;
}

export function customStatusIcon(status) {
    const state = customStatusToProbeState(status);
    return state === null ? null : PROBE_ICON_MAP[state];
}

export function customStatusKey(status) {
    return Object.hasOwn(STATUS_KEY_MAP, status) ? STATUS_KEY_MAP[status] : null;
}

export function mismatchVerbKey(key) {
    const k = String(key ?? '');
    for (const suffix of Object.keys(VERB_KEY_MAP)) {
        if (k.endsWith(suffix)) return VERB_KEY_MAP[suffix];
    }
    return VERB_KEY_DEFAULT;
}

/** epoch 秒 → 本地時區 `MM/DD HH:mm`；非有限數字回 ''。 */
export function formatVerifiedAt(epochSec) {
    if (typeof epochSec !== 'number' || !Number.isFinite(epochSec)) return '';
    const d = new Date(epochSec * 1000);
    if (Number.isNaN(d.getTime())) return '';
    const p2 = (n) => String(n).padStart(2, '0');
    return `${p2(d.getMonth() + 1)}/${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/** 第一個失敗案的第一條沒過的檢查；remaining ＝ 所有失敗案 mismatch 總數 − 1。 */
export function pickFirstMismatch(lastResult) {
    const cases = lastResult && Array.isArray(lastResult.cases) ? lastResult.cases : [];
    const failedCases = cases.filter(
        (c) => c && c.passed === false && Array.isArray(c.mismatches) && c.mismatches.length > 0,
    );
    if (failedCases.length === 0) return null;
    const failedCase = failedCases[0];
    const first = failedCase.mismatches[0];
    const total = failedCases.reduce((sum, c) => sum + c.mismatches.length, 0);
    return {
        index: failedCase.index,
        number: failedCase.number,
        key: first.key,
        expected: first.expected,
        actual: first.actual,
        url: first.url,
        remaining: total - 1,
    };
}

function toText(v) {
    if (v === null || v === undefined) return '';
    if (Array.isArray(v)) return v.map((x) => String(x ?? '')).join('、');
    return String(v);
}

export function describeCustomLine(entry, t) {
    const e = entry || {};
    const time = formatVerifiedAt(e.verified_at);
    switch (e.status) {
        case 'passed':
            return t('settings.sources.custom_line_passed', { time });
        case 'failed': {
            const m = pickFirstMismatch(e.last_result);
            if (m === null) return t('settings.sources.custom_line_failed_bare', { time });
            const verb = t(mismatchVerbKey(m.key));
            let line = t('settings.sources.custom_line_failed', {
                time,
                n: m.index,
                number: m.number,
                key: m.key,
                verb,
                expected: toText(m.expected),
                actual: toText(m.actual),
            });
            if (m.remaining > 0) {
                line += t('settings.sources.custom_line_more', { count: m.remaining });
            }
            return line;
        }
        case 'load_failed': {
            const reason = e.load_error && e.load_error.message ? String(e.load_error.message) : '';
            return t('settings.sources.custom_line_load_failed', { reason });
        }
        case 'unverified':
        case 'verifying':
            return t(customStatusKey(e.status));
        default:
            return '';
    }
}
