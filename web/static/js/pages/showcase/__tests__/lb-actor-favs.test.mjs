// TASK-199b-T1：影片燈箱女優頭像表（_lbActorFavs）與量測簽章的第三引數（favKey）。
//
// A：頭像表以「片上寫的名字」為 key、對得上人（別名／換片不殘留／資料未到為空）。
// B：favKey 進量測簽章，頭像表一變人物列與標籤列都要重新量測（I-4）。
// 範本：lb-actor-age-refresh.test.mjs（importmap resolve hook）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.document = {
    querySelector() { return null; },
    body: { classList: { remove() {}, add() {}, contains() { return false; } } },
};

const IMPORTMAP = {
    '@/settings/': 'pages/settings/',
    '@/shared/': 'shared/',
    '@/components/': 'components/',
    '@/search/': 'pages/search/',
    '@/showcase/': 'pages/showcase/',
    '@/scanner/': 'pages/scanner/',
};
const STATIC_JS_ROOT = pathToFileURL(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../') + '/',
).href;

const loaderCode = `
const IMPORTMAP = ${JSON.stringify(IMPORTMAP)};
const STATIC_JS_ROOT = ${JSON.stringify(STATIC_JS_ROOT)};
export async function resolve(specifier, context, nextResolve) {
    for (const [prefix, rel] of Object.entries(IMPORTMAP)) {
        if (specifier.startsWith(prefix)) {
            return nextResolve(STATIC_JS_ROOT + rel + specifier.slice(prefix.length), context);
        }
    }
    if (specifier.startsWith('@/')) {
        return nextResolve(STATIC_JS_ROOT + specifier.slice(2), context);
    }
    return nextResolve(specifier, context);
}
`;
register(`data:text/javascript,${encodeURIComponent(loaderCode)}`, import.meta.url);

const { stateLightbox } = await import('../state-lightbox.js');
const { stateLightboxFit } = await import('../state-lightbox-fit.js');
const { stateLightboxPop } = await import('../state-lightbox-pop.js');
const { _setActresses, _setActressIndex } = await import('@/showcase/state-base.js');
const { buildActressIndex } = await import('@/shared/actress-lookup.js');

function makeComponent(overrides = {}) {
    return Object.assign({}, stateLightbox(), {
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
        ...overrides,
    });
}

test('lbActorFavs 頭像表以片上名字為 key、首字取片上名字、換片不殘留、資料未到為空', () => {
    const PHOTO = '/api/actresses/photo/%E7%94%B2';
    const favorites = [{ name: '甲', photo_url: PHOTO }, { name: '乙' }];
    const nameToGroup = { '別名甲': ['別名甲', '甲'], '甲': ['別名甲', '甲'] };
    _setActresses(favorites);
    _setActressIndex(buildActressIndex(favorites, nameToGroup));
    try {
        const c = makeComponent({ currentLightboxVideo: { actresses: '別名甲, 乙, 路人' } });
        c._refreshLbActorAges();
        const first = c._lbActorFavs;
        // key 是片上名字（別名），entry.name 是收藏名，initial 取片上名字第一字（別 ≠ 甲）；沒收藏的不在表內
        assert.deepEqual(first, {
            '別名甲': { name: '甲', photo_url: PHOTO, initial: '別' },
            '乙': { name: '乙', photo_url: '', initial: '乙' },
        });
        assert.deepEqual(Object.keys(first).sort(), ['乙', '別名甲']);

        // 換片：新物件參照，且不殘留上一片的 key
        c.currentLightboxVideo = { actresses: '甲' };
        c._refreshLbActorAges();
        assert.notStrictEqual(c._lbActorFavs, first);
        assert.deepEqual(c._lbActorFavs, { '甲': { name: '甲', photo_url: PHOTO, initial: '甲' } });
        assert.equal('別名甲' in c._lbActorFavs, false);

        // 代理對首字不被切半
        _setActressIndex(buildActressIndex([{ name: '𠮷野' }], {}));
        c.currentLightboxVideo = { actresses: '𠮷野' };
        c._refreshLbActorAges();
        assert.equal(c._lbActorFavs['𠮷野'].initial, '𠮷');

        // 資料未到（索引為 null）／沒有目前影片 ⇒ {}
        _setActressIndex(null);
        c._refreshLbActorAges();
        assert.deepEqual(c._lbActorFavs, {});
        _setActressIndex(buildActressIndex(favorites, nameToGroup));
        c.currentLightboxVideo = null;
        c._refreshLbActorAges();
        assert.deepEqual(c._lbActorFavs, {});
    } finally {
        _setActressIndex(null);
        _setActresses([]);
    }
});

test('lbxFitSig 簽章隨頭像表（favKey）改變，不帶第三引數時與舊版逐字相同', () => {
    const fit = stateLightboxFit();
    const v = { path: 'p', actresses: 'a,b', tags: 't', user_tags: ['u1', 'u2'] };
    // 舊版字面：不帶 favKey 的簽章不得多出任何一段
    const legacy = ['p', 'a,b', 't', 'u1\u0001u2', '0'].join('\u0000');
    assert.equal(fit.lbxFitSig(v, false), legacy);
    assert.equal(fit.lbxFitSig(v, false, ''), legacy);

    const k1 = fit.lbxFitSig(v, false, 'k1');
    const k2 = fit.lbxFitSig(v, false, 'k2');
    assert.notEqual(k1, k2);
    assert.notEqual(k1, legacy);

    // 頭像表變了 ⇒ 已量完的簽章不再算「量完」，要重新量測
    const measure = () => ({ chipWidths: [100, 100], moreChipWidth: 60, available: 500, gap: 10 });
    fit.lbxFitRun(k1, {}, measure);
    assert.equal(fit.lbxFitMeasuring(k1), false);
    assert.equal(fit.lbxFitMeasuring(k2), true);

    // lbxFavKey：與鍵順序無關、隨鍵集合改變（排最後）
    const pop = stateLightboxPop();
    const ab = pop.lbxFavKey.call({ _lbActorFavs: { a: { name: 'a' }, b: { name: 'b' } } });
    const ba = pop.lbxFavKey.call({ _lbActorFavs: { b: { name: 'b' }, a: { name: 'a' } } });
    const onlyA = pop.lbxFavKey.call({ _lbActorFavs: { a: { name: 'a' } } });
    assert.equal(ab, ba);
    assert.notEqual(ab, onlyA);
    assert.equal(pop.lbxFavKey.call({ _lbActorFavs: {} }), '');
});
