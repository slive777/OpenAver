// 199b 修正：女優燈箱開著時牆被重排（例如隱藏未連線硬碟後片數變了），
// actressLightboxIndex 要跟著「目前那位」走，上一位／下一位才不會指到別人。
// 載入方式比照 actress-sort.test.mjs（自帶 importmap resolve hook）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.Alpine = globalThis.Alpine || {
    store: () => ({ toolbarOpen: false, showcaseHasSearch: false }),
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

const { stateActress } = await import('../state-actress.js');
const { _setActresses, _setActressWorkCounts, _filteredActresses } = await import('../state-base.js');

const counts = (o) => _setActressWorkCounts(new Map(Object.entries(o)));
const LIST = [{ name: 'A' }, { name: 'B' }, { name: 'C' }];

function makeOpenHarness(overrides = {}) {
    return Object.assign({}, stateActress(), {
        actressSort: 'video_count', actressOrder: 'desc', actressSearch: '',
        lightboxOpen: true, showFavoriteActresses: true, actressLightboxSource: 'grid',
    }, overrides);
}

test('test_actress_index_follows_resort：燈箱開著時牆重排，索引跟著目前女優換位置', () => {
    _setActresses(LIST);
    counts({ A: 9, B: 5, C: 1 });
    const c = makeOpenHarness();
    c.applyActressFilterAndSort();
    assert.deepEqual(_filteredActresses.map((a) => a.name), ['A', 'B', 'C']);
    // 開著 A（第 1 位）
    c.actressLightboxIndex = 0;
    c.currentLightboxActress = _filteredActresses[0];

    // A 的片數掉到 B 之後 → 牆重排成 B, A, C
    counts({ A: 3, B: 5, C: 1 });
    c.applyActressFilterAndSort();
    assert.deepEqual(_filteredActresses.map((a) => a.name), ['B', 'A', 'C']);
    assert.equal(c.actressLightboxIndex, 1);
    assert.equal(c.currentLightboxActress.name, 'A');

    // currentLightboxActress 被換成副本（_fetchLiveAliases）時仍靠 name 找得回
    c.currentLightboxActress = Object.assign({}, c.currentLightboxActress, { aliases: ['x'] });
    counts({ A: 0, B: 5, C: 1 });
    c.applyActressFilterAndSort();
    assert.deepEqual(_filteredActresses.map((a) => a.name), ['B', 'C', 'A']);
    assert.equal(c.actressLightboxIndex, 2);
});

test('燈箱沒開／來源不是女優牆／目前女優不在新清單：索引不動', () => {
    _setActresses(LIST);
    counts({ A: 9, B: 5, C: 1 });
    const closed = makeOpenHarness({ lightboxOpen: false, actressLightboxIndex: 0, currentLightboxActress: LIST[0] });
    counts({ A: 3, B: 5, C: 1 });
    closed.applyActressFilterAndSort();
    assert.equal(closed.actressLightboxIndex, 0);

    const hero = makeOpenHarness({ actressLightboxSource: 'hero', actressLightboxIndex: 0, currentLightboxActress: LIST[0] });
    hero.applyActressFilterAndSort();
    assert.equal(hero.actressLightboxIndex, 0);

    const gone = makeOpenHarness({ actressLightboxIndex: 2, currentLightboxActress: { name: 'Z' } });
    gone.applyActressFilterAndSort();
    assert.equal(gone.actressLightboxIndex, 2);
});
