/**
 * source-probe-logic.js — 測試連線的純邏輯（無 DOM、無 Alpine、無 window）
 *
 * 供 state-source-probe.js 分片與 node:test 使用。
 * REASON_KEY_MAP / STATE_KEY_MAP 是明確物件字面（不動態拼 key，FE-JS-06），
 * 由 tests/unit/test_source_probe_contract.py 對 core.source_probe.REASON_CODES 與 zh_TW.json 對帳。
 */

export const REASON_KEY_MAP = {
    ok: 'settings.sources.probe_reason_ok',
    cf_challenge: 'settings.sources.probe_reason_cf_challenge',
    http_status: 'settings.sources.probe_reason_http_status',
    app_rejected: 'settings.sources.probe_reason_app_rejected',
    proxy: 'settings.sources.probe_reason_proxy',
    timeout: 'settings.sources.probe_reason_timeout',
    tls: 'settings.sources.probe_reason_tls',
    dns: 'settings.sources.probe_reason_dns',
    network: 'settings.sources.probe_reason_network',
    error: 'settings.sources.probe_reason_error',
    windows_verifier: 'settings.sources.probe_reason_windows_verifier',
    self_hosted: 'settings.sources.probe_reason_self_hosted',
    unknown: 'settings.sources.probe_reason_unknown',
    unprobeable: 'settings.sources.probe_reason_unprobeable',
};

export const REASON_KEY_GENERIC = 'settings.sources.probe_reason_generic';

export const STATE_KEY_MAP = {
    ok: 'settings.sources.probe_state_ok',
    blocked: 'settings.sources.probe_state_blocked',
    unreachable: 'settings.sources.probe_state_unreachable',
    skipped: 'settings.sources.probe_state_skipped',
};

/** 回應只在「發出請求時的世代」仍是現行世代時才可寫入。 */
export function acceptProbeResponse(startGen, currentGen) {
    return startGen === currentGen;
}

/** 設定快照鍵（字串，供 $watch 按值比較）：Proxy 欄(trim)、範圍、啟用 id 集合(排序，與膠囊順序無關)。 */
export function buildProbeKey(proxyUrl, proxyScope, sources) {
    const ids = sources.filter((s) => s.enabled).map((s) => s.id).sort();
    return JSON.stringify([String(proxyUrl ?? '').trim(), proxyScope, ids]);
}

/** 送去探測的名單：亮著的膠囊＋所有 manual_only；關掉的與 Parts Bin 不送。 */
export function pickProbeIds(sources) {
    const list = Array.isArray(sources) ? sources : [];
    return list.filter((s) => s.enabled || s.manual_only).map((s) => s.id);
}

/** 摘要：分母不含 skipped；total === 0 代表不顯示。 */
export function summarizeProbe(results) {
    let ok = 0;
    let total = 0;
    for (const r of Object.values(results || {})) {
        if (r.state === 'skipped') continue;
        total += 1;
        if (r.state === 'ok') ok += 1;
    }
    return { ok, total };
}
