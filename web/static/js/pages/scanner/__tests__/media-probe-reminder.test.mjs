// TASK-a205-T6a：影片資訊區塊畫面判斷／完成提示／ETA／開關連動（純邏輯）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { probeBlockView, shouldToastFinish, keepPollingAfterFailure } from '../media-probe-reminder-logic.js';
import { mediaProbeReminder } from '../media-probe-reminder.js';

const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url), 'utf8'));

const base = {
    available: true, dismissed: false, include_readonly: false,
    pending: 0, readonly_pending: 0, has_readonly_source: false,
    job: { running: false, done: 0, total: 0, eta_s: null, elapsed_s: null, last_result: null },
};

function makeHarness() {
    const toasts = [];
    const events = [];
    const saved = {
        window: globalThis.window, document: globalThis.document,
        Alpine: globalThis.Alpine, fetch: globalThis.fetch,
    };
    globalThis.window = {
        t: (key, params = {}) => {
            const value = key.split('.').reduce((obj, part) => obj?.[part], locale);
            if (typeof value !== 'string') return undefined;
            return value.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''));
        },
        dispatchEvent(ev) { events.push(ev.type); return true; },
    };
    globalThis.document = { visibilityState: 'hidden' };
    globalThis.Alpine = { store: () => ({ show: (msg, type) => toasts.push([msg, type]) }) };
    const queue = [];
    globalThis.fetch = (url, opts) => new Promise((resolve) => {
        const req = { url, method: opts?.method, resolve: (body) => resolve({ ok: true, json: async () => body }) };
        queue.push(req);
    });
    const comp = mediaProbeReminder();
    return {
        comp, toasts, events, queue,
        flush(body) { for (const r of queue.splice(0)) r.resolve(body); },
        destroy() {
            comp.destroy();
            for (const r of queue.splice(0)) r.resolve(base);
            globalThis.window = saved.window;
            globalThis.document = saved.document;
            globalThis.Alpine = saved.Alpine;
            globalThis.fetch = saved.fetch;
        },
    };
}

const truthCases = [
    ['pending_with_readonly_hint', { pending: 3, readonly_pending: 1, has_readonly_source: true }, { show: true, line1: 'pending', showToggle: true, readonlyHint: 1, pending: 3 }],
    ['only_readonly_unread', { pending: 0, readonly_pending: 1, has_readonly_source: true }, { show: true, line1: null, showToggle: true, readonlyHint: 1 }],
    ['toggle_on_all_read', { include_readonly: true, has_readonly_source: true }, { show: true, line1: null, showToggle: true, readonlyHint: null }],
    ['all_read_no_readonly_source', {}, { show: false, line1: null, showToggle: false, readonlyHint: null }],
    ['dismissed_keeps_toggle', { dismissed: true, pending: 5, readonly_pending: 1, has_readonly_source: true }, { show: true, line1: null, showToggle: true, readonlyHint: 1 }],
    ['later_without_readonly_source', { pending: 5 }, { show: false, line1: null, showToggle: false, readonlyHint: null }, { later: true }],
    ['unavailable', { available: false, pending: 5, has_readonly_source: true }, { show: true, line1: 'unavailable', showToggle: false, readonlyHint: null }],
    ['running', { pending: 1784, job: { running: true, done: 320, total: 2104, eta_s: null, elapsed_s: 10, last_result: null } }, { show: true, line1: 'running', showToggle: false, readonlyHint: null, percent: 15 }],
];

for (const [name, patch, expected, opts] of truthCases) {
    test(`test_probe_block_view_spec_8_1_truth_table[${name}]`, () => {
        const status = { ...base, ...patch, job: { ...base.job, ...(patch.job || {}) } };
        const v = probeBlockView(status, opts || {});
        assert.equal(v.show, expected.show);
        assert.equal(v.line1, expected.line1);
        assert.equal(v.showToggle, expected.showToggle);
        assert.equal(v.readonlyHint, expected.readonlyHint);
        if ('pending' in expected) assert.equal(v.pending, expected.pending);
        if ('percent' in expected) assert.equal(v.percent, expected.percent);
    });
}

test('test_toggle_on_after_dismiss_reopens_first_line', async () => {
    const h = makeHarness();
    try {
        h.comp.mpStatus = { ...base, dismissed: true, include_readonly: false, pending: 0, readonly_pending: 4, has_readonly_source: true, available: true };
        h.comp.mpLater = true;
        const p = h.comp.mpToggleReadonly({ checked: true });
        assert.equal(h.queue.length, 1);
        h.queue.shift().resolve({ ...base, dismissed: false, include_readonly: true, pending: 4, readonly_pending: 4, has_readonly_source: true, available: true });
        await p;
        assert.equal(h.comp.mpView().line1, 'pending');
        assert.equal(h.comp.mpView().pending, 4);
        assert.equal(h.comp.mpLater, false);
    } finally {
        h.flush(base);
        h.destroy();
    }
});

test('test_status_generation_rule_late_responses', async () => {
    const h = makeHarness();
    try {
        const p0 = h.comp.mpRefresh();
        h.queue.shift().resolve({ ...base, pending: 5 });
        await p0;
        assert.equal(h.comp.mpStatus.pending, 5);
        const pA = h.comp.mpRefresh();
        const pB = h.comp.mpRefresh();
        assert.equal(h.queue.length, 2);
        const [reqA, reqB] = h.queue.splice(0);
        reqB.resolve({ ...base, pending: 2 });
        reqA.resolve({ ...base, pending: 9 });
        await Promise.all([pA, pB]);
        assert.equal(h.comp.mpStatus.pending, 2);
        const pC = h.comp.mpRefresh();
        const pD = h.comp.mpRefresh();
        const [reqC, reqD] = h.queue.splice(0);
        reqC.resolve({ ...base, pending: 7 });
        reqD.resolve({ ...base, pending: 3 });
        await Promise.all([pC, pD]);
        assert.equal(h.comp.mpStatus.pending, 3);
        const pG = h.comp.mpRefresh();
        const reqG = h.queue.shift();
        const pS = h.comp.mpToggleReadonly({ checked: true });
        const reqS = h.queue.shift();
        reqS.resolve({ ...base, include_readonly: true, pending: 4 });
        reqG.resolve({ ...base, pending: 1 });
        await Promise.all([pG, pS]);
        assert.equal(h.comp.mpStatus.pending, 4);
    } finally {
        h.flush(base);
        h.destroy();
    }
});

const tick = () => new Promise((r) => setImmediate(r));

test('test_finish_toast_and_event_exactly_once', async () => {
    const stop2 = { ...base, job: { running: false, done: 3, total: 3, eta_s: null, elapsed_s: 5, last_result: { read: 2, failed: 1, unreachable: 0, total: 3, duration_s: 5 } } };
    const run = { ...base, job: { running: true, done: 1, total: 3, eta_s: null, elapsed_s: 1, last_result: null } };
    const h = makeHarness();
    try {
        const p1 = h.comp.mpRefresh();
        h.queue.shift().resolve(run);
        await p1;
        const p2 = h.comp.mpRefresh();
        h.queue.shift().resolve(stop2);
        await p2;
        assert.equal(h.toasts.length, 1);
        assert.equal(h.toasts[0][0], '影片資訊讀取完成：讀了 2 部，1 部讀不出');
        assert.equal(h.toasts[0][1], 'success');
        assert.deepEqual(h.events, ['media-probe-finished']);
        const p3 = h.comp.mpRefresh();
        h.queue.shift().resolve(stop2);
        await p3;
        assert.equal(h.toasts.length, 1);
        assert.equal(h.events.length, 1);
    } finally {
        h.flush(base);
        h.destroy();
    }
    const h3 = makeHarness();
    try {
        const f1 = h3.comp.mpRefresh();
        h3.queue.shift().resolve(stop2);
        await f1;
        assert.equal(h3.toasts.length, 0);
        assert.equal(h3.events.length, 0);
    } finally {
        h3.flush(base);
        h3.destroy();
    }
    const h4 = makeHarness();
    try {
        const s = h4.comp.mpStart();
        h4.queue.shift().resolve({ status: 'already_running' });
        await tick();
        h4.queue.shift().resolve(stop2);
        await s;
        assert.equal(h4.toasts.length, 0);
        assert.equal(h4.events.length, 0);
    } finally {
        h4.flush(base);
        h4.destroy();
    }
    const h5 = makeHarness();
    try {
        const s = h5.comp.mpStart();
        h5.queue.shift().resolve({ status: 'started' });
        await tick();
        h5.queue.shift().resolve({ ...base, job: { running: false, done: 7, total: 7, eta_s: null, elapsed_s: 5, last_result: { read: 5, failed: 0, unreachable: 2, total: 7, duration_s: 5 } } });
        await s;
        assert.equal(h5.toasts.length, 1);
        assert.equal(h5.toasts[0][0], '影片資訊讀取完成：讀了 5 部，2 部連不到');
        assert.deepEqual(h5.events, ['media-probe-finished']);
    } finally {
        h5.flush(base);
        h5.destroy();
    }
});

test('test_eta_text_by_remaining_seconds', () => {
    const h = makeHarness();
    try {
        h.comp.mpStatus = { ...base, job: { ...base.job } };
        h.comp.mpStatus.job.eta_s = null;
        assert.equal(h.comp.mpEtaText(), '');
        h.comp.mpStatus.job.eta_s = 59;
        assert.equal(h.comp.mpEtaText(), '快好了');
        h.comp.mpStatus.job.eta_s = 60;
        assert.equal(h.comp.mpEtaText(), '約剩 1 分鐘');
        h.comp.mpStatus.job.eta_s = 125;
        assert.equal(h.comp.mpEtaText(), '約剩 3 分鐘');
        let prevMin = Infinity;
        for (const s of [600, 541, 540, 61, 60, 59]) {
            h.comp.mpStatus.job.eta_s = s;
            const text = h.comp.mpEtaText();
            assert.ok(!text.includes('約剩 0'));
            const m = text.match(/約剩 (\d+) 分鐘/);
            if (m) {
                const cur = Number(m[1]);
                assert.ok(cur <= prevMin);
                prevMin = cur;
            }
        }
    } finally {
        h.flush(base);
        h.destroy();
    }
});

test('keepPollingAfterFailure_only_while_job_running', () => {
    assert.equal(keepPollingAfterFailure({ ...base, job: { running: true, done: 1, total: 4 } }), true);
    assert.equal(keepPollingAfterFailure(base), false);
    assert.equal(keepPollingAfterFailure(null), false);
});
