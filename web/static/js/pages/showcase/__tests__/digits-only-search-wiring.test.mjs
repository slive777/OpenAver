// TASK-195-T9（195d）：搜尋框純數字 → 點 metadata 新增 pill 後自動清除的接線測試。
// 檔頭（importmap resolve hook、window／document stub、_setActresses fixture）照
// pill-entry.test.mjs；stateActress 合併亦照 pill-entry（addPill 內部會呼叫
// _clearPreciseMatch／_checkPreciseActressMatch）。入口一律經 searchFromMetadata／
// togglePickPill，不直接呼叫 _clearDigitsOnlySearch。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

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

const { stateVideos } = await import('../state-videos.js');
const { stateLightbox } = await import('../state-lightbox.js');
const { stateActress } = await import('../state-actress.js');
const { stateBase, _setActresses } = await import('../state-base.js');

_setActresses([{ name: 'Yui Hatano', is_favorite: false }]);

globalThis.window.location = { pathname: '/showcase', search: '' };
globalThis.window.history = { replaceState() {} };
globalThis.document = {
    querySelector: () => null,
    body: { classList: { add() {}, remove() {} } },
};

function makeComponent() {
    const base = stateBase.call({ $persist: (obj) => ({ as: () => obj }) });
    const c = Object.assign({}, base, stateVideos(), stateLightbox(), stateActress(), {
        pills: [], search: '', mode: 'table', sort: 'date', order: 'desc', page: 1,
        animLog: [], heroCalls: 0,
    });
    c.$nextTick = (fn) => fn();
    c._animateFilter = function () { c.animLog.push({ search: c.search, pills: c.pills.length }); };
    c._reconcileHeroCard = function () { c.heroCalls++; };
    return c;
}

function click(c, value, dim) {
    c.searchFromMetadata(value, dim);
    if (c.lightboxCloseTimer) { clearTimeout(c.lightboxCloseTimer); c.lightboxCloseTimer = null; }
}

test('搜尋框是純數字時，點七種 metadata 新增 pill 就清文字（清在動畫前、動畫只 1 次）', () => {
    const inputs = ['199', '001', '1991', '１９９', ' 199 ', '2024'];
    const dims = [
        ['三上悠亞', 'actress'],
        ['S1', 'maker'],
        ['Madonna', 'series'],
        ['某導演', 'director'],
        ['Premium', 'label'],
        ['NTR', 'tag'],
        ['2023-05-12', 'release'],
    ];
    for (const search of inputs) {
        for (const [value, dim] of dims) {
            const c = makeComponent();
            c.search = search;
            click(c, value, dim);
            const tag = JSON.stringify({ search, value, dim });
            assert.equal(c.search, '', tag);
            assert.equal(c.pills.length, 1, tag);
            assert.equal(c.animLog.length, 1, tag);
            assert.equal(c.animLog[0].search, '', tag);
            assert.equal(c.heroCalls, 1, tag);
        }
    }
});

test('搜尋框不是純數字時，點 metadata 疊加並保留文字', () => {
    const inputs = ['三上', 'SSIS-001', 'SSIS', '2024-05', '199 三上', '三上 NTR'];
    for (const search of inputs) {
        const c = makeComponent();
        c.search = search;
        click(c, 'NTR', 'tag');
        assert.equal(c.search, search, JSON.stringify(search));
        assert.equal(c.pills.length, 1, JSON.stringify(search));
        assert.equal(c.animLog.length, 1, JSON.stringify(search));
    }
});

test('沒有新增 pill（重複點／發售日同值／發售日解析不出／漏斗）時文字不被清', () => {
    {
        const c = makeComponent();
        c.search = '199';
        click(c, '三上悠亞', 'actress');
        c.search = '199';
        const n = c.animLog.length;
        click(c, '三上悠亞', 'actress');
        assert.equal(c.search, '199', 'repeat actress');
        assert.equal(c.pills.length, 1, 'repeat actress');
        assert.equal(c.animLog.length, n, 'repeat actress');
    }
    {
        const c = makeComponent();
        c.search = '199';
        click(c, '2023-05-12', 'release');
        const n = c.animLog.length;
        c.search = '199';
        click(c, '2023-05-12', 'release');
        assert.equal(c.search, '199', 'release same value');
        assert.equal(c.animLog.length, n + 1, 'release same value');
    }
    {
        const c = makeComponent();
        c.search = '199';
        click(c, '無效日期', 'release');
        assert.equal(c.search, '199', 'release unparsable');
        assert.equal(c.pills.length, 0, 'release unparsable');
        assert.equal(c.animLog.length, 0, 'release unparsable');
    }
    {
        const c = makeComponent();
        c.search = '199';
        c.togglePickPill();
        assert.equal(c.search, '199', 'pick funnel');
        assert.equal(c.pills.length, 1, 'pick funnel');
        assert.equal(c.pills[0].dim, 'pick', 'pick funnel');
        assert.equal(c.animLog.length, 1, 'pick funnel');
    }
});
