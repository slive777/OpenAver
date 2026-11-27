// libraryInsightsState 契約（預覽開關、年表點擊、選取條件、去瀏覽頁）。
// state.js 會連帶載入 charts.js，故先掛最小 window／document stub。

import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.window.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
});
globalThis.window.addEventListener = () => {};
globalThis.window.removeEventListener = () => {};
globalThis.document = globalThis.document || {
    addEventListener() {},
    removeEventListener() {},
    querySelector() { return null; },
    getElementById() { return null; },
    createElement() {
        return {
            style: {},
            appendChild() {},
        };
    },
    body: {
        appendChild() {},
        classList: { add() {}, remove() {}, contains() { return false; } },
    },
};

const { libraryInsightsState } = await import('../state.js');
const { setRecords } = await import('../aggregate.js');

// 測試用手組 sel（三條件，預設全空）
function selOf(over) {
    return { period: { type: 'all' }, actress: null, maker: null, ...over };
}

function rec(opts) {
    return {
        year: opts.year === undefined ? 2020 : opts.year,
        month: opts.month === undefined ? null : opts.month,
        actresses: opts.actresses === undefined ? ['Alice'] : opts.actresses,
        maker: opts.maker === undefined ? 'SOD' : opts.maker,
        tags: opts.tags === undefined ? [] : opts.tags,
        date: opts.date === undefined ? null : opts.date,
        duration: opts.duration === undefined ? null : opts.duration,
    };
}


// ── topDisplayCount (TASK-156e-T3) ───────────────────────────────────


// ── canGoBrowse / goBrowse (TASK-161a-T7) ────────────────────────────

// 安裝 localStorage／location／console.warn 的記錄器，回傳 { calls, warns, restore }
function installBrowseStubs({ stored = null, setItemThrows = false } = {}) {
    const calls = [];
    const warns = [];
    const lsDesc = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
    const locDesc = Object.getOwnPropertyDescriptor(globalThis, 'location');
    const origWarn = console.warn;
    const fake = {
        getItem(k) { calls.push(['getItem', k]); return stored; },
        setItem(k, v) {
            if (setItemThrows) throw new Error('quota');
            calls.push(['setItem', k, v]);
        },
    };
    Object.defineProperty(globalThis, 'localStorage', { value: fake, configurable: true, writable: true });
    Object.defineProperty(globalThis, 'location', {
        value: { assign(url) { calls.push(['assign', url]); } },
        configurable: true,
        writable: true,
    });
    console.warn = (...args) => { warns.push(args); };
    const restore = () => {
        console.warn = origWarn;
        if (lsDesc) Object.defineProperty(globalThis, 'localStorage', lsDesc);
        else delete globalThis.localStorage;
        if (locDesc) Object.defineProperty(globalThis, 'location', locDesc);
        else delete globalThis.location;
    };
    return { calls, warns, restore };
}


test('goBrowse: 先寫入 showcase_state 再導向 /showcase，保留既有排序與卡型、整組換成目前條件', () => {
    const old = JSON.stringify({
        sort: 'x', cardShape: 'poster', infoVisible: true, search: 'abc',
        pills: [{ dim: 'actress', value: '舊' }],
    });
    const stub = installBrowseStubs({ stored: old });
    try {
        const state = libraryInsightsState();
        state.snapshotError = null;
        state.scopedCount = 12;
        state.sel = { period: { type: 'year', year: 2023 }, actress: 'A', maker: 'M' };
        state.goBrowse();
        const writes = stub.calls.filter((c) => c[0] === 'setItem' || c[0] === 'assign');
        assert.equal(writes.length, 2);
        assert.equal(writes[0][0], 'setItem');
        assert.equal(writes[0][1], 'showcase_state');
        assert.deepEqual(writes[1], ['assign', '/showcase']);
        const saved = JSON.parse(writes[0][2]);
        assert.equal(saved.pills.length, 3);
        const dims = saved.pills.map((p) => p.dim).sort();
        assert.deepEqual(dims, ['actress', 'maker', 'release']);
        const rel = saved.pills.find((p) => p.dim === 'release');
        assert.equal(rel.op, '=');
        assert.equal(rel.value, '2023');
        assert.equal(saved.search, '');
        assert.equal(saved.page, 1);
        assert.equal(saved.showFavoriteActresses, false);
        assert.equal(saved.sort, 'x');
        assert.equal(saved.cardShape, 'poster');
        assert.equal(saved.infoVisible, true);
    } finally {
        stub.restore();
    }

    // 無條件也能跳
    const stub2 = installBrowseStubs({ stored: old });
    try {
        const state = libraryInsightsState();
        state.snapshotError = null;
        state.scopedCount = 2103;
        state.sel = selOf({});
        state.goBrowse();
        const set = stub2.calls.find((c) => c[0] === 'setItem');
        assert.deepEqual(JSON.parse(set[2]).pills, []);
        assert.equal(stub2.calls.filter((c) => c[0] === 'assign').length, 1);
    } finally {
        stub2.restore();
    }
});

test('goBrowseWith: 無效 extra 不寫入也不導航', () => {
    const stub = installBrowseStubs();
    try {
        const state = libraryInsightsState();
        state.snapshotError = null;
        state.scopedCount = 5;
        for (const bad of [{ dim: 'tag', value: '' }, { dim: 'tag', value: '   ' },
            { dim: 'actress', value: 'X' }, undefined, 'tag']) {
            assert.doesNotThrow(() => state.goBrowseWith(bad));
        }
        assert.equal(stub.calls.filter((c) => c[0] === 'setItem' || c[0] === 'assign').length, 0);
        state.goBrowseWith({ dim: 'tag', value: 'T' });
        assert.equal(stub.calls.filter((c) => c[0] === 'assign').length, 1);
    } finally {
        stub.restore();
    }
});

test('goBrowseWith: 寫入 sel 條件加 extra 於最後且不改動 sel', () => {
    const old = JSON.stringify({ sort: 'x', cardShape: 'poster', search: 'abc', pills: [] });
    for (const dim of ['tag', 'director', 'series']) {
        const stub = installBrowseStubs({ stored: old });
        try {
            const state = libraryInsightsState();
            state.snapshotError = null;
            state.scopedCount = 12;
            state.sel = { period: { type: 'year', year: 2023 }, actress: 'A', maker: 'M' };
            const before = structuredClone(state.sel);
            state.goBrowseWith({ dim, value: 'X' });
            assert.deepEqual(state.sel, before);
            const w = stub.calls.filter((c) => c[0] === 'setItem' || c[0] === 'assign');
            assert.deepEqual(w.map((c) => c[0]), ['setItem', 'assign']);
            assert.deepEqual(w[1], ['assign', '/showcase']);
            const saved = JSON.parse(w[0][2]);
            assert.deepEqual(saved.pills, [
                { dim: 'actress', value: 'A' }, { dim: 'maker', value: 'M' },
                { dim: 'release', op: '=', value: '2023' }, { dim, value: 'X' },
            ]);
            assert.equal(saved.search, '');
            assert.equal(saved.page, 1);
            assert.equal(saved.showFavoriteActresses, false);
            assert.equal(saved.sort, 'x');
            assert.equal(saved.cardShape, 'poster');
        } finally {
            stub.restore();
        }
    }
});

// ---- TASK-177-T3b：收藏請求狀態機 helper（模組層純函式，T3c 共用）----

function makeFavFetch(favs) {
    const pending = [];
    const calls = [];
    const fn = (url, init) => {
        if (String(url).includes('/api/insights/snapshot')) {
            return Promise.resolve({
                ok: true,
                json: async () => ({
                    records: [], logicalTitles: 5, physicalRows: 5, years: [],
                    actressFavorites: favs || {},
                }),
            });
        }
        calls.push({ url, init });
        return new Promise((resolve, reject) => { pending.push({ resolve, reject }); });
    };
    fn.favoriteCalls = () => calls;
    fn.flush = (status, body) => {
        const p = pending.shift();
        p.resolve({
            status,
            ok: status < 400,
            json: async () => {
                if (body === undefined) throw new Error('bad json');
                return body;
            },
        });
    };
    fn.rejectNext = (err) => { pending.shift().reject(err); };
    fn.flushAll = () => { while (pending.length) fn.flush(500, null); };
    return fn;
}

async function bootInsights(router, favs) {
    let cleanup = null;
    globalThis.window.__registerPage = (h) => { cleanup = h.cleanup; };
    const state = libraryInsightsState();
    state.$watch = () => {};
    await state.init();
    state.sel = selOf({ actress: 'Alice' });
    const spies = { toasts: [], redraws: 0 };
    state.redrawAge = () => { spies.redraws += 1; };
    state.showToast = (...a) => { spies.toasts.push(a); };
    return { state, cleanup, spies };
}

async function withFavFetch(favs, body) {
    const originalFetch = globalThis.fetch;
    const router = makeFavFetch(favs);
    globalThis.fetch = router;
    try {
        const ctx = await bootInsights(router, favs);
        await body({ router, ...ctx });
    } finally {
        router.flushAll();
        globalThis.fetch = originalFetch;
        delete globalThis.window.__registerPage;
    }
}

const tick = () => new Promise((r) => setImmediate(r));
const actressBody = (name, extra) => ({ success: true, actress: { name, birth: null, photo_url: '', ...extra } });

test('addFocusedFavorite: 同一位連點只送一次，完成後不再送，失敗後可再送（I-1）', async () => {
    await withFavFetch({}, async ({ state, router }) => {
        state.addFocusedFavorite();
        state.addFocusedFavorite();
        state.addFocusedFavorite();
        await tick();
        assert.equal(router.favoriteCalls().length, 1);
        const { init } = router.favoriteCalls()[0];
        assert.equal(init.method, 'POST');
        assert.deepEqual(JSON.parse(init.body), { name: 'Alice' });
        assert.equal(state.favoriteBusyFor('Alice'), true);
        router.flush(200, actressBody('Alice', { photo_url: '/p.jpg' }));
        await tick(); await tick();
        assert.equal(state.favoriteBusyFor('Alice'), false);
        // 對照格：同一串回應確實把她寫進 favs
        assert.equal(state.isFavoriteActress('Alice'), true);
        state.addFocusedFavorite();
        await tick();
        assert.equal(router.favoriteCalls().length, 1);
        // 失敗後可再送
        state.sel = selOf({ actress: 'Bob' });
        state.addFocusedFavorite();
        await tick();
        assert.equal(router.favoriteCalls().length, 2);
        router.flush(500, null);
        await tick(); await tick();
        state.addFocusedFavorite();
        await tick();
        assert.equal(router.favoriteCalls().length, 3);
    });
});

test('addFocusedFavorite: 請求中切換女優，完成只更新請求的那位且不動別人的 busy（I-2）', async () => {
    await withFavFetch({}, async ({ state, router }) => {
        state.addFocusedFavorite(); // A
        await tick();
        state.sel = selOf({ actress: 'Bob' });
        router.flush(200, actressBody('Alice'));
        await tick(); await tick();
        assert.equal(state.isFavoriteActress('Alice'), true);
        assert.equal(state.isFavoriteActress('Bob'), false);
    });
    await withFavFetch({}, async ({ state, router }) => {
        state.sel = selOf({ actress: 'Bob' });
        state.addFocusedFavorite(); // B 掛起
        state.sel = selOf({ actress: 'Alice' });
        state.addFocusedFavorite(); // A 掛起
        await tick();
        router.flush(200, actressBody('Bob')); // 放行最舊＝B
        await tick(); await tick();
        // 重新對照：B 已完成、A 仍 busy（busy 以名字為單位）
        assert.equal(state.favoriteBusyFor('Bob'), false);
        assert.equal(state.favoriteBusyFor('Alice'), true);
        router.flush(200, actressBody('Alice'));
        await tick(); await tick();
        assert.equal(state.favoriteBusyFor('Alice'), false);
    });
    await withFavFetch({}, async ({ state, router }) => {
        state.addFocusedFavorite(); // A（最舊）
        state.sel = selOf({ actress: 'Bob' });
        state.addFocusedFavorite(); // B 掛起
        await tick();
        router.flush(200, actressBody('Alice')); // A 完成
        await tick(); await tick();
        assert.equal(state.favoriteBusyFor('Bob'), true, 'B 的 busy 不受 A 完成影響');
        assert.equal(state.isFavoriteActress('Bob'), false);
    });
});

test('addFocusedFavorite: 404／504／500／200 無 actress／fetch 例外／JSON 解析失敗都清 busy、不寫快照、不重繪、可重試（I-3）', async () => {
    const rows = [
        ['404', (r) => r.flush(404, { detail: 'x' }), 'showcase.actress.addNotFound'],
        ['504', (r) => r.flush(504, { detail: 'x' }), 'showcase.actress.addTimeout'],
        ['500', (r) => r.flush(500, null), 'showcase.actress.addTimeout'],
        ['200 無 actress', (r) => r.flush(200, { success: true }), 'showcase.actress.addTimeout'],
        ['fetch 例外', (r) => r.rejectNext(new Error('net')), 'showcase.actress.addTimeout'],
        ['JSON 解析失敗', (r) => r.flush(200, undefined), 'showcase.actress.addTimeout'],
    ];
    for (const [label, act, key] of rows) {
        await withFavFetch({}, async ({ state, router, spies }) => {
            const before = state.snapshot.actressFavorites;
            state.addFocusedFavorite();
            await tick();
            assert.equal(state.favoriteBusyFor('Alice'), true, label);
            act(router);
            await tick(); await tick();
            assert.equal(state.favoriteBusyFor('Alice'), false, label);
            assert.deepEqual(Object.keys(state.snapshot.actressFavorites), [], label);
            assert.equal(state.snapshot.actressFavorites, before, label);
            assert.equal(spies.redraws, 0, label);
            assert.equal(spies.toasts.length, 1, label);
            assert.deepEqual(spies.toasts[0], [key, 'error'], label);
            state.addFocusedFavorite();
            await tick();
            assert.equal(router.favoriteCalls().length, 2, label);
        });
    }
});

test('addFocusedFavorite: 200 有圖／200 無圖／409 都落地成已收藏，換新身分、redrawAge 一次、年表含她（I-4）', async () => {
    const cases = [
        ['Alice', 200, actressBody('Alice', { photo_url: '/p.jpg' }), 'success', true, 'showcase.actress.addSuccess'],
        ['Bob', 200, actressBody('Bob'), 'success', false, 'showcase.actress.addSuccess'],
        ['Cara', 409, { actress: { name: 'Cara', birth: null, photo_url: '/c.jpg' } }, 'info', true, 'showcase.actress.addDuplicate'],
    ];
    for (const [name, status, body, type, hasPhoto, key] of cases) {
        await withFavFetch({}, async ({ state, router, spies }) => {
            state.sel = selOf({ actress: name });
            const old = state.snapshot.actressFavorites;
            state.addFocusedFavorite();
            await tick();
            router.flush(status, body);
            await tick(); await tick();
            assert.notEqual(state.snapshot.actressFavorites, old);
            const entry = state.snapshot.actressFavorites[name];
            assert.equal(entry.photoName, body.actress.name);
            assert.equal(entry.hasPhoto, hasPhoto);
            assert.equal(spies.redraws, 1);
            assert.equal(spies.toasts.length, 1);
            assert.deepEqual(spies.toasts[0], [key, type]);
            assert.equal(state.photoFailed[name], false);
        });
    }
    // 年表格：先暖快取再收藏，完成後年表含她
    try {
        setRecords([rec({ actresses: ['Alice'], date: '2020-06-01', duration: 120 })]);
        await withFavFetch({}, async ({ state, router }) => {
            state.ganttRows = [{ name: 'Alice' }];
            assert.equal(state.ganttView('age').rows.length, 0);
            state.addFocusedFavorite();
            await tick();
            router.flush(200, actressBody('Alice', { birth: '1995-01-01', photo_url: '/p.jpg' }));
            await tick(); await tick();
            const v = state.ganttView('age');
            assert.deepEqual(v.rows.map((r) => r.name), ['Alice']);
        });
    } finally {
        setRecords([]);
    }
});

// 測試行數大於產品碼：plan I-5 定死四格 oracle（各自隔離一道閘／一個復活點）
test('addFocusedFavorite: 頁面已死或快照為空時晚到回應不寫入不提示，bfcache 還原後恢復運作（I-5）', async () => {
    const okBody = actressBody('Alice', { photo_url: '/p.jpg' });
    // ① snapshot=null、不 cleanup：只隔離 snapshot 閘
    await withFavFetch({}, async ({ state, router, spies }) => {
        state.addFocusedFavorite();
        await tick();
        state.snapshot = null;
        router.flush(200, okBody);
        await tick(); await tick();
        assert.equal(state.favoriteBusyFor('Alice'), false);
        assert.equal(spies.toasts.length, 0);
        assert.equal(spies.redraws, 0);
    });
    // ② cleanup、保留非空 snapshot：只隔離 _pageAlive 閘
    await withFavFetch({}, async ({ state, router, spies, cleanup }) => {
        const before = state.snapshot.actressFavorites;
        state.addFocusedFavorite();
        await tick();
        cleanup();
        router.flush(200, okBody);
        await tick(); await tick();
        assert.equal(state.favoriteBusyFor('Alice'), false, '離頁後仍清 busy');
        assert.equal(state.snapshot.actressFavorites, before);
        assert.equal(spies.toasts.length, 0);
        assert.equal(spies.redraws, 0);
    });
    // ③ cleanup 後 bfcache 還原（persisted:true）再收藏：恢復運作
    await withFavFetch({}, async ({ state, router, spies, cleanup }) => {
        cleanup();
        state._onPageShow({ persisted: true });
        state.addFocusedFavorite();
        await tick();
        router.flush(200, okBody);
        await tick(); await tick();
        assert.equal(state.isFavoriteActress('Alice'), true);
        assert.equal(spies.redraws, 1);
        assert.equal(spies.toasts.length, 1);
        assert.deepEqual(spies.toasts[0], ['showcase.actress.addSuccess', 'success']);
    });
    // ④ persisted:false 不復活：回應在其後抵達仍零寫入
    await withFavFetch({}, async ({ state, router, spies, cleanup }) => {
        const before = state.snapshot.actressFavorites;
        state.addFocusedFavorite();
        await tick();
        cleanup();
        state._onPageShow({ persisted: false });
        router.flush(200, okBody);
        await tick(); await tick();
        assert.equal(state.snapshot.actressFavorites, before);
        assert.equal(spies.toasts.length, 0);
        assert.equal(spies.redraws, 0);
    });
});

test('actressPhotoUrl／focusPhotoUrl 有特寫用特寫、沒有退原圖；previewPhotoUrl 恆原圖', () => {
    const s = libraryInsightsState();
    s.snapshot = {
        actressFavorites: {
            A: { photoName: 'A', hasPhoto: true, avatarUrl: '/api/actresses/face-crop/A?v=1' },
            B: { photoName: 'B 名', hasPhoto: true, avatarUrl: '' },
        },
    };
    assert.equal(s.actressPhotoUrl('A'), '/api/actresses/face-crop/A?v=1');
    assert.equal(s.actressPhotoUrl('B'), '/api/actresses/photo/' + encodeURIComponent('B 名'));
    assert.equal(s.actressPhotoUrl('C'), '/api/actresses/photo/C');
    s.sel = { ...s.sel, actress: 'A' };
    assert.equal(s.focusPhotoUrl(), '/api/actresses/face-crop/A?v=1');
    s.sel = { ...s.sel, actress: 'B' };
    assert.equal(s.focusPhotoUrl(), '/api/actresses/photo/' + encodeURIComponent('B 名'));
    s.previewActress = 'A';
    assert.equal(s.previewPhotoUrl(), '/api/actresses/photo/A');
});
