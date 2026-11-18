// TASK-201-T6a: 精選篩選浮層的狀態機＋影片模式三浮層互斥（無畫面）。
// 檔頭（importmap resolve hook、window／document／localStorage／matchMedia 最小 stub）
// 照 __tests__/actress-pill-editor.test.mjs；makeComponent 合併 stateBase／stateVideos／
// stateLightbox／stateActress（Object.assign，覆寫清單照 actress-pill-editor）；
// window.t stub 用 (key, p) => p ? key + '|' + p.op + p.tier : key；window.scrollTo 要 stub；
// 要開浮層的測試必須自己設 c._pillPopoverEnabled = true；Esc 用真的 handleKeydown，
// 事件物件照 actress-pill-keyboard.test.mjs 的 makeKeyEvent。

import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key, p) => (p ? key + '|' + p.op + p.tier : key);
globalThis.Alpine = globalThis.Alpine || {
    store: () => ({ toolbarOpen: false, showcaseHasSearch: false }),
};
if (typeof globalThis.localStorage === 'undefined') {
    const _store = Object.create(null);
    globalThis.localStorage = {
        getItem: (k) => (k in _store ? _store[k] : null),
        setItem: (k, v) => { _store[k] = String(v); },
        removeItem: (k) => { delete _store[k]; },
    };
}
if (typeof globalThis.requestAnimationFrame !== 'function') {
    globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
}
if (typeof globalThis.window.addEventListener !== 'function') {
    globalThis.window.addEventListener = () => {};
    globalThis.window.removeEventListener = () => {};
}
if (typeof globalThis.window.scrollTo !== 'function') {
    globalThis.window.scrollTo = () => {};
}
if (typeof globalThis.document === 'undefined') {
    globalThis.document = {
        querySelector: () => null,
        body: { classList: { add() {}, remove() {} } },
    };
}
if (typeof globalThis.window.scrollY === 'undefined') {
    globalThis.window.scrollY = 0;
}
globalThis.window.location = { pathname: '/showcase', search: '' };
globalThis.window.history = { replaceState() {} };

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
const { stateBase, _setActresses } = await import('../state-base.js');
const { stateVideos } = await import('../state-videos.js');
const { stateLightbox } = await import('../state-lightbox.js');

function installMatchMedia(initialMatches) {
    const handlersByQuery = new Map();
    const mqsByQuery = new Map();

    function makeMq(query, matches) {
        const listeners = [];
        const mq = {
            matches,
            media: query,
            addEventListener(type, handler) {
                if (type === 'change') {
                    listeners.push(handler);
                    handlersByQuery.get(query)?.add.push(handler);
                }
            },
            removeEventListener(type, handler) {
                if (type === 'change') {
                    handlersByQuery.get(query)?.remove.push(handler);
                    const i = listeners.indexOf(handler);
                    if (i >= 0) listeners.splice(i, 1);
                }
            },
            _listeners: listeners,
            _dispatch(newMatches) {
                this.matches = newMatches;
                for (const h of listeners.slice()) {
                    h({ matches: newMatches, media: query });
                }
            },
        };
        return mq;
    }

    function mqFor(query) {
        if (!mqsByQuery.has(query)) {
            let matches = false;
            if (query.includes('max-width: 480') || query.includes('max-width:480')) {
                matches = initialMatches;
            }
            handlersByQuery.set(query, { add: [], remove: [] });
            mqsByQuery.set(query, makeMq(query, matches));
        }
        return mqsByQuery.get(query);
    }

    globalThis.window.matchMedia = (query) => mqFor(query);

    return {
        setMatches(m) {
            for (const [q, mq] of mqsByQuery) {
                if (q.includes('480')) mq._dispatch(m);
            }
        },
    };
}

let mm = installMatchMedia(false);

beforeEach(() => {
    mm = installMatchMedia(false);
});

function makeComponent(overrides) {
    const base = stateBase.call({ $persist: (obj) => ({ as: () => obj }) });
    const videos = stateVideos();
    const lightbox = stateLightbox();
    const actress = stateActress();
    const c = Object.assign({}, base, videos, lightbox, actress, {
        actressSearch: '',
        actressSort: 'video_count',
        actressOrder: 'desc',
        sortFlipCalls: 0,
        lightboxOpen: false,
        closeLightbox() {},
        saveState() {},
        _clearPreciseMatch() {},
        _reconcileHeroCard() {},
        _animateFilter() {},
        _getActiveGrid() { return null; },
        _resetPicker() {},
        _resetMask() {},
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
        $watch() {},
        _sortWithFlip(fn) {
            c.sortFlipCalls++;
            if (typeof fn === 'function') fn();
        },
    }, overrides);
    if (!Array.isArray(c.actressPills)) c.actressPills = [];
    if (!Array.isArray(c.pills)) c.pills = [];
    _setActresses([{ name: 'seed', is_favorite: false }]);
    return c;
}

function makeKeyEvent(key, { tagName = 'BODY', preventDefault = null } = {}) {
    let prevented = false;
    const e = {
        key,
        target: { tagName },
        preventDefault() {
            prevented = true;
            if (typeof preventDefault === 'function') preventDefault();
        },
        stopPropagation() {},
        get defaultPrevented() { return prevented; },
    };
    return e;
}

function releasePill() {
    return { dim: 'release', op: '=', value: '2020' };
}

function resolutionPill() {
    return { dim: 'resolution', op: '=', value: 'FHD' };
}

function pickPill() {
    return { dim: 'pick', value: '1' };
}

test('togglePickPill 非預設等級下仍能關掉', () => {
    const c = makeComponent();
    c.pills = [{ dim: 'pick', op: '>=', value: '2' }];
    c.togglePickPill();
    assert.deepEqual(c.pills, []);
    c.togglePickPill();
    assert.deepEqual(c.pills, [{ dim: 'pick', value: '1' }]);
    assert.ok(!('op' in c.pills[0]));
});

test('精選浮層互斥: 影片模式三浮層至多一個、真 toggleActressMode 後四 slot 全 null、removePill 關浮層、Esc 只取消浮層', () => {
    const openers = [
        ['release', (c) => c._toggleReleaseEditor(releasePill()), '_releaseEditor'],
        ['resolution', (c) => c._toggleResolutionEditor(resolutionPill()), '_resolutionEditor'],
        ['pick', (c) => c._togglePickEditor(pickPill()), '_pickEditor'],
    ];
    for (let i = 0; i < openers.length; i++) {
        for (let j = 0; j < openers.length; j++) {
            if (i === j) continue;
            const c = makeComponent();
            c._pillPopoverEnabled = true;
            openers[i][1](c);
            assert.ok(c[openers[i][2]], `${openers[i][0]} 先開應非 null`);
            openers[j][1](c);
            assert.equal(c[openers[i][2]], null, `開 ${openers[j][0]} 後 ${openers[i][0]} 應為 null`);
            assert.ok(c[openers[j][2]], `${openers[j][0]} 應非 null`);
        }
    }
    for (const [, open, slot] of openers) {
        const c = makeComponent();
        c._pillPopoverEnabled = true;
        open(c);
        c._pillEditor = { dim: 'age', op: '=', value: '37' };
        c.toggleActressMode();
        assert.equal(c._pillEditor, null, `${slot} 開著切模式後 _pillEditor 全 null`);
        assert.equal(c._releaseEditor, null);
        assert.equal(c._resolutionEditor, null);
        assert.equal(c._pickEditor, null);
    }
    {
        const c = makeComponent();
        c._pillPopoverEnabled = true;
        c.pills = [{ dim: 'pick', value: '2' }];
        c._togglePickEditor({ dim: 'pick', value: '2' });
        assert.ok(c._pickEditor);
        c.removePill('pick', '2');
        assert.equal(c._pickEditor, null);
    }
    {
        const c = makeComponent();
        c._pillPopoverEnabled = true;
        c.pills = [{ dim: 'pick', value: '1' }];
        c._togglePickEditor({ dim: 'pick', value: '1' });
        assert.ok(c._pickEditor);
        c.lightboxOpen = true;
        const e = makeKeyEvent('Escape');
        c.handleKeydown(e);
        assert.equal(c._pickEditor, null);
        assert.equal(c.lightboxOpen, true);
        assert.equal(e.defaultPrevented, true);
    }
});

test('_setPickPill 改 op 與等級: 新參照、浮層關閉、chip 文字隨之變、下排金銀銅對照', () => {
    const c = makeComponent();
    c._pillPopoverEnabled = true;
    c._setPickPill({ value: '1' });
    const oldPills = c.pills;
    const oldPill = c.pills[0];
    c._setPickPill({ value: '1', op: '=' });
    assert.ok(c.pills !== oldPills);
    assert.ok(c.pills[0] !== oldPill);
    c._togglePickEditor({ dim: 'pick', value: '1' });
    assert.deepEqual(c._pickEditor, { op: '>=', value: '1' });
    c._applyPickOp('>=');
    assert.deepEqual(c.pills[0], { dim: 'pick', op: '>=', value: '1' });
    c._togglePickEditor(c.pills[0]);
    c._applyPickTier('2');
    assert.deepEqual(c.pills[0], { dim: 'pick', op: '>=', value: '2' });
    assert.equal(c._pickEditor, null);
    assert.equal(c.pickPillText({ dim: 'pick', value: '1' }), 'showcase.pick.chip_label');
    const gte = c.pickPillText({ dim: 'pick', op: '>=', value: '2' });
    const eq = c.pickPillText({ dim: 'pick', op: '=', value: '2' });
    assert.ok(gte !== 'showcase.pick.chip_label');
    assert.ok(eq !== 'showcase.pick.chip_label');
    assert.ok(gte !== eq);
    const list = c.pickTierList();
    assert.deepEqual(list.map((x) => x.value), ['3', '2', '1']);
    assert.deepEqual(list.map((x) => x.tier), ['gold', 'silver', 'bronze']);
    assert.deepEqual(list.map((x) => x.label), ['showcase.pick.tier.gold', 'showcase.pick.tier.silver', 'showcase.pick.tier.bronze']);
    assert.equal(c.pickPillText({ dim: 'pick', op: '<=', value: '2' }), 'showcase.pick.chip_tier|≤showcase.pick.tier.silver');
    assert.equal(c.pickPillText({ dim: 'pick', op: '>=', value: '2' }), 'showcase.pick.chip_tier|≥showcase.pick.tier.silver');
    assert.equal(c.pickPillText({ dim: 'pick', op: '=', value: '2' }), 'showcase.pick.chip_tier|=showcase.pick.tier.silver');
    assert.equal(c.pickPillText({ dim: 'pick', op: '>=', value: '3' }), 'showcase.pick.chip_tier|≥showcase.pick.tier.gold');
});

test('窄螢幕不開精選浮層', () => {
    const c = makeComponent();
    c._pillPopoverEnabled = false;
    c._releaseEditor = { op: '=', value: '2020' };
    c._resolutionEditor = { op: '=', value: 'FHD' };
    c._pickEditor = null;
    c._togglePickEditor({ dim: 'pick', value: '1' });
    assert.equal(c._pickEditor, null);
    assert.deepEqual(c._releaseEditor, { op: '=', value: '2020' });
    assert.deepEqual(c._resolutionEditor, { op: '=', value: 'FHD' });
});
