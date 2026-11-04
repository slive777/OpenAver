// TASK-189a-T11a: 補跑 mixin — 銷毀後輪詢停、有未存變更或忙碌時按鈕不送 POST（輪詢世代／離開分頁見 ai-tags-panel.test.mjs）。
import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
window.t = (k) => k;

const { aiTagsPanel } = await import('../ai-tags-panel.js');

const resp = (data, ok = true) => ({ ok, json: async () => data });

function makePanel(over = {}) {
    const c = aiTagsPanel();
    Object.assign(c, {
        aiTab: 'tags', form: { aiTagsEnabled: true }, isDirty: false,
        showToast() {}, $watch() {},
    }, over);
    return c;
}

test('backfill_destroy_stops_poll', async () => {
    const realFetch = globalThis.fetch;
    const c = makePanel();
    let calls = 0;
    globalThis.fetch = async () => { calls++; return resp({ running: true, pending: 4, total: 10, tagged: 6 }); };
    try {
        await c.bfRefresh();
        assert.notEqual(c.bfPollTimer, null);
        c.destroy();
        assert.equal(c.bfPollTimer, null);
        const before = calls;
        await c.bfRefresh();
        assert.equal(calls, before);
        // 在途回應於銷毀後 resolve：不得改 bfStatus
        const snapshot = c.bfStatus;
        let release;
        const gate = new Promise((r) => { release = r; });
        const c2 = makePanel();
        globalThis.fetch = () => gate;
        const p = c2.bfRefresh();
        c2.destroy();
        release(resp({ running: true, pending: 1, total: 1, tagged: 0 }));
        await p;
        assert.equal(c2.bfStatus, null);
        assert.equal(c.bfStatus, snapshot);
    } finally {
        clearTimeout(c.bfPollTimer);
        globalThis.fetch = realFetch;
    }
});

test('backfill_start_blocked_when_dirty_or_busy', async () => {
    const realFetch = globalThis.fetch;
    const posts = [];
    globalThis.fetch = async (url, opts) => {
        if (opts && opts.method === 'POST') posts.push(url);
        return resp({ running: false, pending: 5, total: 10, tagged: 5, resumable: false });
    };
    const mk = (over) => {
        const c = makePanel(over);
        c.bfStatus = { running: false, pending: 5, total: 10, tagged: 5, resumable: false };
        return c;
    };
    try {
        await mk({ isDirty: true }).bfStart();
        assert.equal(posts.length, 0);
        const busy = mk();
        busy.bfBusy = true;
        await busy.bfStart();
        assert.equal(posts.length, 0);
        const clean = mk();
        await clean.bfStart();
        assert.deepEqual(posts, ['/api/ai/tags/backfill']);
    } finally {
        globalThis.fetch = realFetch;
    }
});
