// TASK-188c-T8b: aiTagsPanel 獨立元件 — 輪詢世代守衛／離開分頁停輪詢／測試鈕 body 與結果／首次開啟預選連線。
// 驅動真的 bfRefresh／runTest／onProviderChange／init／statusLineText，只假 fetch、$watch、root 外求、window.t。

import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
window.t = (k, p) => (p && Object.keys(p).length ? `${k}|${JSON.stringify(p)}` : k);

const { aiTagsPanel } = await import('../ai-tags-panel.js');

function deferred() {
    let resolve;
    const promise = new Promise((r) => { resolve = r; });
    return { promise, resolve };
}

const resp = (data, ok = true) => ({ ok, json: async () => data });

function makePanel(over = {}) {
    const watchers = {};
    const toasts = [];
    const ensureCalls = [];
    const lists = {
        gemini: [{ name: 'gemini-x' }], claude: [], ollama: [], openai_official: [], openai: [],
    };
    const c = aiTagsPanel();
    Object.assign(c, {
        aiTab: 'translate',
        form: {},
        isDirty: false,
        showToast: (...a) => { toasts.push(a); },
        $watch(path, cb) { watchers[path] = cb; },
        aiTagsModelLists: () => lists,
        ensureProviderModels: async (p) => { ensureCalls.push(p); },
    }, over);
    return { c, watchers, toasts, ensureCalls };
}

const RUNNING = { running: false, pending: 5, total: 10, tagged: 5, skipped: 0 };

test('tags_poll_stale_response_ignored', async () => {
    const realFetch = globalThis.fetch;
    const { c } = makePanel({ aiTab: 'tags' });
    const first = deferred();
    let n = 0;
    globalThis.fetch = () => (++n === 1 ? first.promise : Promise.resolve(resp(RUNNING)));
    try {
        const p1 = c.bfRefresh();
        await c.bfRefresh();
        assert.equal(c.bfStatus.pending, 5);
        first.resolve(resp({ ...RUNNING, pending: 99 }));
        await p1;
        assert.equal(c.bfStatus.pending, 5);
    } finally {
        c.destroy();
        globalThis.fetch = realFetch;
    }
});

test('tags_poll_stops_on_leave_tab', async () => {
    const realFetch = globalThis.fetch;
    const { c, watchers } = makePanel();
    const busy = { running: true, slow: true, skipped: 2, pending: 4, total: 10, tagged: 6 };
    globalThis.fetch = async () => resp(busy);
    try {
        c.init();
        c.aiTab = 'tags';
        await c.bfRefresh();
        assert.notEqual(c.bfPollTimer, null);
        // 跑中：slow／skipped 句併進進度行；舊狀態行不再重述
        const line = c.bfProgressText();
        assert.ok(line.includes('settings.ai.tags.status_slow_extra'), line);
        assert.ok(line.includes('settings.ai.tags.status_skipped_extra'), line);
        assert.equal(c.statusLineText(), '');
        c.aiTab = 'translate';
        watchers.aiTab('translate');
        assert.equal(c.bfPollTimer, null);

        // 請求在途時離開分頁：回來的 running:true 不得再排輪詢
        c.aiTab = 'tags';
        const d = deferred();
        globalThis.fetch = () => d.promise;
        const p = c.bfRefresh();
        c.aiTab = 'translate';
        watchers.aiTab('translate');
        d.resolve(resp(busy));
        await p;
        assert.equal(c.bfPollTimer, null);
    } finally {
        c.destroy();
        globalThis.fetch = realFetch;
    }
});

test('tags_runtest_body_and_result', async () => {
    const realFetch = globalThis.fetch;
    const calls = [];
    let next;
    globalThis.fetch = async (url, opts) => { calls.push({ url, opts }); return next; };
    try {
        const claude = makePanel({
            form: { aiTagsProvider: 'claude', aiTagsModel: 'm-claude-1', claudeApiKey: '••••abcd', ollamaUrl: 'http://x' },
        });
        next = resp({ ok: true, outcome: 'ok', tags: ['絲襪', 'OL'] });
        await claude.c.runTest();
        assert.equal(calls[0].url, '/api/ai/tags/test');
        assert.equal(calls[0].opts.method, 'POST');
        assert.equal(calls[0].opts.headers['Content-Type'], 'application/json');
        assert.deepEqual(JSON.parse(calls[0].opts.body), { provider: 'claude', model: 'm-claude-1', api_key: '••••abcd' });
        assert.equal(claude.c.aiTagsTestResult, 'settings.ai.tags.test_ok|{"tags":"絲襪、OL"}');

        const ollama = makePanel({
            form: { aiTagsProvider: 'ollama', aiTagsModel: 'm-ollama', ollamaUrl: 'http://ollama.local:11434', claudeApiKey: 'LEAK' },
        });
        next = resp({ ok: false, outcome: 'unusable', detail: 'model_unsupported' });
        await ollama.c.runTest();
        const ob = JSON.parse(calls[1].opts.body);
        assert.deepEqual(ob, { provider: 'ollama', model: 'm-ollama', base_url: 'http://ollama.local:11434' });
        assert.equal('api_key' in ob, false);
        assert.equal(ollama.c.aiTagsTestResult, 'settings.ai.tags.test_unusable_model_unsupported');

        next = resp({ ok: false, outcome: 'unreachable' });
        await ollama.c.runTest();
        assert.equal(ollama.c.aiTagsTestResult, 'settings.ai.tags.test_unreachable');
        assert.equal(ollama.c.aiTagsTestBusy, false);
        assert.equal(ollama.toasts.length, 0);
        assert.equal(claude.toasts.length, 0);

        next = resp({}, false);
        await ollama.c.runTest();
        assert.equal(ollama.c.aiTagsTestResult, 'settings.ai.tags.test_failed_generic');
        assert.equal(ollama.toasts.length, 1);
        assert.deepEqual(ollama.toasts[0], ['settings.ai.tags.test_http_error', 'error']);
        assert.equal(ollama.c.aiTagsTestBusy, false);
    } finally {
        globalThis.fetch = realFetch;
    }
});

test('tags_first_enable_preselect', async () => {
    const mk = (isDirty, form) => {
        const m = makePanel({ isDirty, form });
        m.c.init();
        return m;
    };
    const base = { aiTagsEnabled: true, aiTagsProvider: '', aiTagsModel: '', translateProvider: 'gemini' };
    const settle = () => new Promise((r) => setTimeout(r, 0));

    // 載入設定（isDirty=false）：不預選
    const a = mk(false, { ...base });
    a.watchers['form.aiTagsEnabled'](true);
    await settle();
    assert.equal(a.c.form.aiTagsProvider, '');
    assert.deepEqual(a.ensureCalls, []);

    // 使用者手動打開：預選翻譯的連線與模型
    const b = mk(true, { ...base });
    b.watchers['form.aiTagsEnabled'](true);
    await settle();
    assert.equal(b.c.form.aiTagsProvider, 'gemini');
    assert.equal(b.c.form.aiTagsModel, 'gemini-flash-lite-latest');
    assert.deepEqual(b.ensureCalls, ['gemini']);

    // 已有連線：不動
    const d = mk(true, { ...base, aiTagsProvider: 'claude' });
    d.watchers['form.aiTagsEnabled'](true);
    await settle();
    assert.equal(d.c.form.aiTagsProvider, 'claude');
    assert.deepEqual(d.ensureCalls, []);

    // 翻譯連線不在五家：不動
    const e = mk(true, { ...base, translateProvider: 'bogus' });
    e.watchers['form.aiTagsEnabled'](true);
    await settle();
    assert.equal(e.c.form.aiTagsProvider, '');
    assert.deepEqual(e.ensureCalls, []);
});

// 190a-T5：「還有 N 部沒跑」尾巴的金額以 pending 算、全部重建確認的金額以 total 算（兩者不同才分得出錯位）
test('pending_cost_uses_pending_and_rebuild_confirm_uses_total', async () => {
    const realConfirm = globalThis.confirm;
    const asked = [];
    globalThis.confirm = (msg) => { asked.push(msg); return false; };
    try {
        const { c } = makePanel({
            form: { aiTagsEnabled: true, aiTagsProvider: 'gemini', aiTagsModel: 'gemini-flash-lite-latest' },
        });
        c.bfStatus = { running: false, pending: 83, total: 1200, tagged: 1117, skipped: 0 };
        const pending = c.bfPendingText();
        assert.ok(pending.startsWith('settings.ai.backfill.pending_line|{"n":83}'), pending);
        assert.ok(pending.includes('settings.ai.tags.cost_pending_tail|{"total":"0.06"'), pending);
        await c.bfRebuild();
        assert.equal(asked.length, 1);
        assert.ok(asked[0].startsWith('settings.ai.tags.rebuild_confirm_cost|{"n":1200,"total":"0.86"'), asked[0]);
    } finally {
        globalThis.confirm = realConfirm;
    }
});

test('rebuild_confirm_falls_back_without_cost', async () => {
    const realConfirm = globalThis.confirm;
    const asked = [];
    globalThis.confirm = (msg) => { asked.push(msg); return false; };
    try {
        // costHint 為 null（ollama）：只有「還有 N 部沒跑」、重建用原文，不得出現 NaN／USD
        const ollama = makePanel({
            form: { aiTagsEnabled: true, aiTagsProvider: 'ollama', aiTagsModel: 'llava' },
        });
        ollama.c.bfStatus = { running: false, pending: 5, total: 10, tagged: 5, skipped: 0 };
        assert.equal(ollama.c.bfPendingText(), 'settings.ai.backfill.pending_line|{"n":5}');
        await ollama.c.bfRebuild();
        assert.equal(asked[0], 'settings.ai.tags.rebuild_confirm|{"n":10}');

        // 有費用規則但 pending=0：整行不顯示（無費用半句）
        const gem = makePanel({
            form: { aiTagsEnabled: true, aiTagsProvider: 'gemini', aiTagsModel: 'gemini-flash-lite-latest' },
        });
        gem.c.bfStatus = { running: false, pending: 0, total: 10, tagged: 10, skipped: 0 };
        assert.equal(gem.c.bfPendingText(), '');
        for (const m of asked) assert.ok(!/NaN|USD/.test(m), m);
    } finally {
        globalThis.confirm = realConfirm;
    }
});
