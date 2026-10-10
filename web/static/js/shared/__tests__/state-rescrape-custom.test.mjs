// TASK-165-T10：重刮視窗自訂來源接線（第三組膠囊、番號格式灰化、三種自訂失敗句）。
// 判斷全在後端；這裡只驗前端的世代守衛、過濾、擋點、互斥與時序。

import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (k, p) => (p && p.source ? k + '|' + p.source : k);

register(
  new URL('../../pages/search/__tests__/alias-loader.mjs', import.meta.url),
  import.meta.url,
);
const { rescrapeState } = await import('../state-rescrape.js');

const SOURCES = [
    { id: 'javbus', type: 'builtin', routable: true, order: 1 },
    { id: 'mt:x', type: 'metatube', routable: true, order: 2 },
    { id: 'custom:b', type: 'custom', routable: true, order: 2, display_name_raw: 'B' },
    { id: 'custom:a', type: 'custom', routable: true, order: 1, display_name_raw: 'A' },
    { id: 'custom:off', type: 'custom', routable: false, order: 3 },
];

function makeCtx(sources = SOURCES) {
    const ctx = rescrapeState();
    ctx.rescrapeSources = sources;
    ctx.rescrapeNumber = 'ABC-123';
    return ctx;
}

function errCount(ctx) {
    return [ctx.rescrapeNotFound, ctx.rescrapeAccessError, ctx.rescrapeCustomError].filter(Boolean).length;
}

/** 可手動 resolve 的 fetch stub。 */
function installFetch() {
    const calls = [];
    globalThis.fetch = (url, opts) => {
        let resolve;
        const p = new Promise(r => { resolve = r; });
        calls.push({
            url, body: opts && opts.body ? JSON.parse(opts.body) : null,
            respond(map, ok = true) {
                resolve({ ok, json: async () => ({ success: true, applicable: map }) });
            },
            respondRaw(obj) { resolve({ ok: true, json: async () => obj }); },
        });
        return p;
    };
    return calls;
}

async function flush(n = 6) { for (let i = 0; i < n; i++) await Promise.resolve(); }

test('rescrapeCustomSources excludes routable false and other types', () => {
    const ctx = makeCtx();
    assert.deepEqual(ctx.rescrapeCustomSources().map(s => s.id), ['custom:a', 'custom:b']);
});

test('refreshRescrapeCustomApplicable sends no request when there is no custom source', async () => {
    const ctx = makeCtx(SOURCES.filter(s => s.type !== 'custom'));
    const calls = installFetch();
    ctx.rescrapeCustomApplicable = { stale: false };
    await ctx.refreshRescrapeCustomApplicable();
    assert.equal(calls.length, 0);
    assert.deepEqual(ctx.rescrapeCustomApplicable, {});
});

test('refreshRescrapeCustomApplicable sends no request for a blank number', async () => {
    const ctx = makeCtx();
    ctx.rescrapeNumber = '   ';
    const calls = installFetch();
    await ctx.refreshRescrapeCustomApplicable();
    assert.equal(calls.length, 0);
    assert.deepEqual(ctx.rescrapeCustomApplicable, {});
});

test('refreshRescrapeCustomApplicable drops a stale response', async () => {
    const ctx = makeCtx();
    const calls = installFetch();
    ctx.rescrapeNumber = '12345';
    const p1 = ctx.refreshRescrapeCustomApplicable();
    ctx.rescrapeNumber = 'ABC-123';
    const p2 = ctx.refreshRescrapeCustomApplicable();
    assert.equal(calls.length, 2);
    calls[1].respond({ 'custom:a': true });
    await p2;
    calls[0].respond({ 'custom:a': false });
    await p1;
    assert.deepEqual(ctx.rescrapeCustomApplicable, { 'custom:a': true });
});

test('a response arriving after closeRescrape is not written', async () => {
    const ctx = makeCtx();
    const calls = installFetch();
    const p = ctx.refreshRescrapeCustomApplicable();
    ctx.closeRescrape();
    calls[0].respond({ 'custom:a': false });
    await p;
    assert.deepEqual(ctx.rescrapeCustomApplicable, {});
});

test('a failed applicable request counts as not replied (all clickable)', async () => {
    const ctx = makeCtx();
    const calls = installFetch();
    ctx.rescrapeCustomApplicable = { 'custom:a': false };
    const p = ctx.refreshRescrapeCustomApplicable();
    calls[0].respond({}, false);
    await p;
    assert.deepEqual(ctx.rescrapeCustomApplicable, {});
});

test('click on a not-applicable custom pill sends no preview request', async () => {
    const ctx = makeCtx();
    const calls = installFetch();
    ctx.rescrapeCustomApplicable = { 'custom:a': false };
    const p = ctx.rescrapeWithSource('custom:a');
    const sent = calls.length;
    calls.forEach(c => c.respondRaw({ success: false }));
    await p;
    assert.equal(sent, 0);
    assert.equal(ctx.rescrapeLoadingSource, null);
    assert.equal(errCount(ctx), 0);
});

test('applicable true or unknown key still sends the preview request', async () => {
    for (const map of [{ 'custom:a': true }, {}]) {
        const ctx = makeCtx();
        const calls = installFetch();
        ctx.rescrapeCustomApplicable = map;
        const p = ctx.rescrapeWithSource('custom:a');
        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, '/api/rescrape/preview');
        calls[0].respondRaw({ success: false });
        await p;
    }
});

test('openRescrape from the search entry sends the number written after it returns', async () => {
    const ctx = makeCtx();
    ctx.rescrapeSources = SOURCES;
    globalThis.window.__ADVANCED_SEARCH__ = { sources: SOURCES };
    const calls = installFetch();
    try {
        ctx.openRescrape(null, 'search');
        ctx.rescrapeNumber = 'ABC-123';
        await flush();
        assert.equal(calls.length, 1);
        assert.equal(calls[0].body.number, 'ABC-123');
        calls[0].respond({});
        await flush();
    } finally {
        delete globalThis.window.__ADVANCED_SEARCH__;
    }
});

test('typing debounces to one applicable request with the last number', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    try {
        const ctx = makeCtx();
        const calls = installFetch();
        ctx.rescrapeNumber = 'A';
        ctx.onRescrapeNumberInput();
        mock.timers.tick(200);
        ctx.rescrapeNumber = '12345';
        ctx.onRescrapeNumberInput();
        mock.timers.tick(299);
        assert.equal(calls.length, 0);
        mock.timers.tick(1);
        assert.equal(calls.length, 1);
        assert.equal(calls[0].body.number, '12345');
        calls[0].respond({});
        await flush();
    } finally {
        mock.timers.reset();
    }
});

test('parse_empty shows the site-changed sentence not the unreachable one', () => {
    const ctx = makeCtx();
    ctx._applyRescrapeFailure({ success: false, custom_error: 'parse_empty', source: 'custom:a' }, 'custom:a');
    const msg = ctx.rescrapeCustomMessage(ctx.rescrapeCustomError);
    assert.ok(msg.includes('custom_parse_failed'));
    assert.ok(!msg.includes('access_unreachable'));
    assert.ok(msg.includes('A'));
});

test('refused shows the backend sentence and falls back when it is empty', () => {
    const ctx = makeCtx();
    ctx._applyRescrapeFailure({ success: false, custom_error: 'refused', error: '這個番號不符合' }, 'custom:a');
    assert.equal(ctx.rescrapeCustomMessage(ctx.rescrapeCustomError), '這個番號不符合');
    ctx._applyRescrapeFailure({ success: false, custom_error: 'refused', error: '' }, 'custom:a');
    assert.ok(ctx.rescrapeCustomMessage(ctx.rescrapeCustomError).includes('custom_refused|A'));
});

test('not_found shows custom_not_found', () => {
    const ctx = makeCtx();
    ctx._applyRescrapeFailure({ success: false, custom_error: 'not_found', source: 'custom:b' }, 'custom:b');
    assert.ok(ctx.rescrapeCustomMessage(ctx.rescrapeCustomError).includes('custom_not_found|B'));
});

test('the three error states are mutually exclusive', () => {
    const ctx = makeCtx();
    const feeds = [
        { custom_error: 'not_found', source: 'custom:a' },
        { access_error: 'unreachable', source: 'javbus' },
        { custom_error: 'parse_empty', source: 'custom:a' },
        { access_error: 'refused', source: 'javbus' },
        { custom_error: 'refused', error: 'x' },
        {},
        { custom_error: 'not_found', source: 'custom:a' },
    ];
    for (const f of feeds) {
        ctx._applyRescrapeFailure({ success: false, ...f }, 'custom:a');
        assert.equal(errCount(ctx), 1, JSON.stringify(f));
    }
    ctx._applyRescrapeFailure({ success: false, custom_error: 'not_found', source: 'custom:a' }, 'custom:a');
    ctx.onRescrapeNumberInput();
    assert.equal(errCount(ctx), 0);
    ctx._applyRescrapeFailure({ success: false, custom_error: 'not_found', source: 'custom:a' }, 'custom:a');
    ctx.closeRescrape();
    assert.equal(errCount(ctx), 0);
});
