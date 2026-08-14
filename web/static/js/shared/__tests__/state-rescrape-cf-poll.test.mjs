// TASK-118a-T4：_pollCfThenRetry / cancelCfPoll 依 sourceId 查表，
// 以及 search 入口改查 manual_only（含「查不到來源」邊界）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
if (typeof globalThis.window.t !== 'function') {
    globalThis.window.t = (k) => k;
}

register(
  new URL('../../pages/search/__tests__/alias-loader.mjs', import.meta.url),
  import.meta.url,
);
const { rescrapeState } = await import('../state-rescrape.js');

function withGlobals({ fetchImpl, setIntervalImpl, clearIntervalImpl }, fn) {
    const origFetch = globalThis.fetch;
    const origSet = globalThis.setInterval;
    const origClear = globalThis.clearInterval;
    if (fetchImpl) globalThis.fetch = fetchImpl;
    if (setIntervalImpl) globalThis.setInterval = setIntervalImpl;
    if (clearIntervalImpl) globalThis.clearInterval = clearIntervalImpl;
    return Promise.resolve()
        .then(fn)
        .finally(() => {
            globalThis.fetch = origFetch;
            globalThis.setInterval = origSet;
            globalThis.clearInterval = origClear;
        });
}

test('CD-118a-7: poll ready 後自動重試的來源是觸發者 fc-javten（不是 javlibrary）', async () => {
    const fetchUrls = [];
    const retried = [];
    let intervalFn = null;
    await withGlobals({
        setIntervalImpl: (fn) => { intervalFn = fn; return 7; },
        clearIntervalImpl: () => {},
        fetchImpl: async (url) => {
            fetchUrls.push(String(url));
            return { json: async () => ({ ready: true }) };
        },
    }, async () => {
        const ctx = {
            ...rescrapeState(),
            _cfPollHandle: null,
            rescrapeCfWaiting: true,
            async rescrapeWithSource(id) { retried.push(id); },
        };
        rescrapeState()._pollCfThenRetry.call(ctx, 'FC2-PPV-1234567', 'fc-javten');
        assert.equal(ctx._cfPollSourceId, 'fc-javten');
        assert.ok(intervalFn, '_pollCfThenRetry 必須啟動 setInterval');
        await intervalFn();
        assert.ok(
            fetchUrls.some((u) => u.includes('/api/cf/status?key=fc-javten')),
            `status poll 必須帶 fc-javten key，實際: ${fetchUrls.join(',')}`,
        );
        assert.deepEqual(retried, ['fc-javten']);
    });
});

test('javlibrary 路徑：poll ready 後仍重試 javlibrary（零回歸）', async () => {
    const fetchUrls = [];
    const retried = [];
    let intervalFn = null;
    await withGlobals({
        setIntervalImpl: (fn) => { intervalFn = fn; return 7; },
        clearIntervalImpl: () => {},
        fetchImpl: async (url) => {
            fetchUrls.push(String(url));
            return { json: async () => ({ ready: true }) };
        },
    }, async () => {
        const ctx = {
            ...rescrapeState(),
            _cfPollHandle: null,
            rescrapeCfWaiting: true,
            async rescrapeWithSource(id) { retried.push(id); },
        };
        rescrapeState()._pollCfThenRetry.call(ctx, 'SONE-205', 'javlibrary');
        await intervalFn();
        assert.ok(fetchUrls.some((u) => u.includes('/api/cf/status?key=javlibrary')));
        assert.deepEqual(retried, ['javlibrary']);
    });
});

test('F-2: cancelCfPoll 零參數，abandon 用 _cfPollSourceId', async () => {
    const fetchCalls = [];
    await withGlobals({
        fetchImpl: async (url, opts) => {
            fetchCalls.push({ url: String(url), method: opts && opts.method });
            return { json: async () => ({ ok: true }) };
        },
        clearIntervalImpl: () => {},
    }, async () => {
        const ctx = {
            ...rescrapeState(),
            _cfPollHandle: 1,
            _cfPollSourceId: 'fc-javten',
            rescrapeCfWaiting: true,
        };
        rescrapeState().cancelCfPoll.call(ctx);
        assert.equal(ctx.rescrapeCfWaiting, false);
        assert.equal(ctx._cfPollSourceId, null);
        assert.equal(fetchCalls.length, 1);
        assert.ok(fetchCalls[0].url.includes('/api/cf/abandon?key=fc-javten'));
        assert.equal(fetchCalls[0].method, 'POST');
    });
});

test('F-2: _cfPollSourceId 沒有值時只 clearInterval，不送 abandon POST', async () => {
    const fetchCalls = [];
    await withGlobals({
        fetchImpl: async (url) => {
            fetchCalls.push(String(url));
            return { json: async () => ({}) };
        },
        clearIntervalImpl: () => {},
    }, async () => {
        const ctx = {
            ...rescrapeState(),
            _cfPollHandle: 1,
            _cfPollSourceId: null,
            rescrapeCfWaiting: true,
        };
        rescrapeState().cancelCfPoll.call(ctx);
        assert.equal(ctx.rescrapeCfWaiting, false);
        assert.equal(fetchCalls.length, 0);
    });
});

test('closeRescrape 清掉 _cfPollSourceId，且不 POST abandon', async () => {
    const fetchCalls = [];
    await withGlobals({
        fetchImpl: async (url) => {
            fetchCalls.push(String(url));
            return { json: async () => ({}) };
        },
        clearIntervalImpl: () => {},
    }, async () => {
        const ctx = {
            ...rescrapeState(),
            rescrapeOpen: true,
            _cfPollHandle: 1,
            _cfPollSourceId: 'fc-javten',
            rescrapeCfWaiting: true,
        };
        rescrapeState().closeRescrape.call(ctx);
        assert.equal(ctx._cfPollSourceId, null);
        assert.equal(fetchCalls.length, 0);
    });
});

test('rescrapeConfirm 的 cf_needed 把 _rescrapeCommitSource 傳給 _pollCfThenRetry', async () => {
    const pollArgs = [];
    await withGlobals({
        fetchImpl: async () => ({
            json: async () => ({ cf_needed: true, cf_source: 'fc-javten' }),
        }),
    }, async () => {
        const ctx = {
            ...rescrapeState(),
            _rescraping: false,
            rescrapeCfWaiting: false,
            rescrapeEntryPoint: 'lightbox',
            _rescrapeVideo: { path: 'file:///x.mp4' },
            _rescrapeCommitSource: 'fc-javten',
            rescrapeNumber: 'FC2-PPV-1234567',
            rescrapePreview: { url: null },
            _pollCfThenRetry(number, sourceId) { pollArgs.push([number, sourceId]); },
        };
        await rescrapeState().rescrapeConfirm.call(ctx);
        assert.deepEqual(pollArgs, [['FC2-PPV-1234567', 'fc-javten']]);
    });
});

function makeSearchCtx({ advanced, previewPosted }) {
    return {
        ...rescrapeState(),
        rescrapeEntryPoint: 'search',
        rescrapeNumber: 'FC2-PPV-1234567',
        rescrapeLoadingSource: null,
        rescrapeCfWaiting: false,
        rescrapeSources: [
            { id: 'javlibrary', manual_only: true },
            { id: 'fc-javten', manual_only: true },
            { id: 'javbus', manual_only: false },
        ],
        searchQuery: '',
        async advancedSearch(id) { advanced.push(id); },
        closeRescrape() {},
    };
}

test('search 入口：manual_only 來源（fc-javten）不早 return advancedSearch', async () => {
    const advanced = [];
    const previewPosted = [];
    await withGlobals({
        fetchImpl: async (url) => {
            if (String(url).includes('/api/rescrape/preview')) {
                previewPosted.push(url);
                return { json: async () => ({ success: false }) };
            }
            return { json: async () => ({}) };
        },
    }, async () => {
        const ctx = makeSearchCtx({ advanced, previewPosted });
        await rescrapeState().rescrapeWithSource.call(ctx, 'fc-javten');
        assert.deepEqual(advanced, []);
        assert.equal(previewPosted.length, 1);
    });
});

test('search 入口：javlibrary 仍走 preview（零回歸）', async () => {
    const advanced = [];
    const previewPosted = [];
    await withGlobals({
        fetchImpl: async (url) => {
            if (String(url).includes('/api/rescrape/preview')) {
                previewPosted.push(url);
                return { json: async () => ({ success: false }) };
            }
            return { json: async () => ({}) };
        },
    }, async () => {
        const ctx = makeSearchCtx({ advanced, previewPosted });
        ctx.rescrapeNumber = 'SONE-205';
        await rescrapeState().rescrapeWithSource.call(ctx, 'javlibrary');
        assert.deepEqual(advanced, []);
        assert.equal(previewPosted.length, 1);
    });
});

test('search 入口：查不到來源（.find 回 undefined）走 advancedSearch', async () => {
    const advanced = [];
    const previewPosted = [];
    await withGlobals({
        fetchImpl: async (url) => {
            previewPosted.push(String(url));
            return { json: async () => ({}) };
        },
    }, async () => {
        const ctx = makeSearchCtx({ advanced, previewPosted });
        await rescrapeState().rescrapeWithSource.call(ctx, 'not-a-real-source');
        assert.deepEqual(advanced, ['not-a-real-source']);
        assert.equal(previewPosted.length, 0);
    });
});

test('search 入口：非 manual_only 來源走 advancedSearch', async () => {
    const advanced = [];
    const previewPosted = [];
    await withGlobals({
        fetchImpl: async (url) => {
            previewPosted.push(String(url));
            return { json: async () => ({}) };
        },
    }, async () => {
        const ctx = makeSearchCtx({ advanced, previewPosted });
        await rescrapeState().rescrapeWithSource.call(ctx, 'javbus');
        assert.deepEqual(advanced, ['javbus']);
        assert.equal(previewPosted.length, 0);
    });
});
