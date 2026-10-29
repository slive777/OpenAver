// TASK-184-T4：「常收女優」入口與 recent_region_empty 錯誤頁
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.document = { addEventListener() {}, querySelector() { return null; } };
window.t = (k) => k;
register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);

const { searchStateBase } = await import('../state/base.js');
const { searchStateSearchFlow } = await import('../state/search-flow.js');
const { searchStateMakerLatest } = await import('../state/maker-latest.js');

function merge(...parts) {
    const target = {};
    for (const part of parts) Object.defineProperties(target, Object.getOwnPropertyDescriptors(part));
    return target;
}

test('recent_region_empty 錯誤頁：空結果不被畫成查無結果、不隱藏膠囊，其他 code 仍為 no_data', () => {
    const run = (data, recentKey) => {
        const hidden = [];
        const s = merge(searchStateBase(), searchStateSearchFlow());
        s.currentMode = 'maker';
        s.currentMaker = { key: 'k1', label: 'L1', spellings: [] };
        s.hideMakerCapsule = (k) => hidden.push(k);
        if (recentKey) s._recentActressKey = recentKey;
        s._applyMakerError(data);
        return { s, hidden };
    };
    const r = run({ error_code: 'recent_region_empty' });
    assert.equal(r.s.errorKind, 'recent_region_empty');
    assert.equal(r.s.errorText, 'search.error.recent_region_empty');
    assert.equal(r.s.pageState, 'error');
    assert.deepEqual(r.hidden, []);
    const rn = run({ error_code: 'recent_none' });
    assert.equal(rn.s.errorKind, 'recent_none');
    assert.equal(rn.s.errorText, 'search.error.recent_none');
    assert.deepEqual(rn.hidden, []);
    const ru = run({ error_code: 'maker_unreachable' }, 'k1');
    assert.equal(ru.s.errorKind, 'recent_unreachable');
    assert.equal(ru.s.errorText, 'search.error.recent_unreachable');
    assert.deepEqual(ru.hidden, []);
    // 一般片商膠囊的 maker_unreachable、以及無 code，仍為 no_data
    for (const code of ['maker_unreachable', undefined]) {
        const x = run(code ? { error_code: code } : {});
        assert.equal(x.s.errorKind, 'no_data', String(code));
        assert.equal(x.s.errorText, 'search.error.no_data');
        assert.deepEqual(x.hidden, []);
    }
    const nf = run({ error_code: 'maker_not_found' });
    assert.equal(nf.s.errorKind, 'maker_not_found');
    assert.deepEqual(nf.hidden, ['k1']);
});

test('常收女優入口：鍵與可用性來自後端回應，失敗一律不顯示且不拋', async () => {
    const load = async (impl) => {
        const s = searchStateMakerLatest();
        const calls = [];
        s.doSearch = (...a) => { calls.push(a); };
        globalThis.fetch = impl;
        await s.loadRecentActressCapsule();
        return { s, calls };
    };
    const ok = await load(async () => ({ json: async () => ({ success: true, available: true, key: 'k-from-backend' }) }));
    assert.equal(ok.s.recentActressAvailable, true);
    ok.s.startRecentActressSearch();
    assert.deepEqual(ok.calls, [['', { maker: { key: 'k-from-backend', label: 'search.recent_actresses.label', spellings: [] } }]]);
    const bad = [
        async () => ({ json: async () => ({ success: true, available: false, key: 'x' }) }),
        async () => ({ json: async () => ({ success: false, available: true, key: 'x' }) }),
        async () => { throw new Error('net'); },
        async () => ({ json: async () => { throw new Error('not json'); } }),
    ];
    for (const f of bad) {
        const r = await load(f);
        assert.equal(r.s.recentActressAvailable, false);
    }
});
