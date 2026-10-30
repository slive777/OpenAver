// TASK-186-T6: 圖片相似純函式三支表驅動測試
globalThis.window = globalThis;
window.t = (k) => k;

const {
    panelMode,
    indexAction,
    statusLine,
} = await import('../ai-similar-logic.js');

import { test } from 'node:test';
import assert from 'node:assert/strict';

test('indexAction_table', () => {
    assert.equal(indexAction(null, true), null);
    assert.equal(indexAction(undefined, true), null);

    // running 優先於 model_changed
    assert.equal(indexAction({
        running: true, model_changed: true, model: 'm', pending: 1, complete: false,
    }, true), 'stop');
    assert.equal(indexAction({
        running: true, model_changed: false, model: null, pending: 0, complete: false,
    }, false), 'stop');

    // model_changed 單獨 → rebuild
    assert.equal(indexAction({
        running: false, model_changed: true, model: 'old', pending: 0, complete: true,
    }, true), 'rebuild');

    // model 已設且 pending>0 → continue
    assert.equal(indexAction({
        running: false, model_changed: false, model: 'm', pending: 3, complete: false,
    }, true), 'continue');
    // model 已設且 !complete → continue（pending 可為 0）
    assert.equal(indexAction({
        running: false, model_changed: false, model: 'm', pending: 0, complete: false,
    }, false), 'continue');

    // model 未設且本次測試通過 → build
    assert.equal(indexAction({
        running: false, model_changed: false, model: null, pending: 0, complete: false,
    }, true), 'build');
    assert.equal(indexAction({
        running: false, model_changed: false, model: '', pending: 0, complete: false,
    }, true), 'build');

    // 其餘 null（未測過、已完成且無 unreadable）
    assert.equal(indexAction({
        running: false, model_changed: false, model: null, pending: 0, complete: false,
    }, false), null);
    assert.equal(indexAction({
        running: false, model_changed: false, model: 'm', pending: 0, complete: true, unreadable: 0,
    }, true), null);

    // 已完成＋unreadable>0 → retry；unreadable==0 維持 null（上一列）
    assert.equal(indexAction({
        running: false, model_changed: false, model: 'm', pending: 0, complete: true, unreadable: 3,
    }, true), 'retry');
    assert.equal(indexAction({
        running: false, model_changed: false, model: 'm', pending: 0, complete: true, unreadable: 0,
    }, false), null);
});

test('statusLine_table', () => {
    const base = {
        running: false,
        model_changed: false,
        unreachable: false,
        model: null,
        indexed: 0,
        total: 0,
        pending: 0,
        unreadable: 0,
        complete: false,
        last_success_at: null,
    };

    // ① model_changed
    const r1 = statusLine({ ...base, model_changed: true, model: 'x' }, 0);
    assert.equal(r1.key, 'settings.ai.similar.status_model_changed');

    // ② running：N = indexed + unreadable
    const r2 = statusLine({
        ...base, running: true, indexed: 5, unreadable: 2, total: 20, model: 'm',
    }, 0);
    assert.equal(r2.key, 'settings.ai.similar.status_running');
    assert.equal(r2.params.n, 7);
    assert.equal(r2.params.m, 20);

    // running 優先於 model_changed（與 indexAction 一致：running 先判）
    // statusLine 優先序是 model_changed 第一——卡片寫：①model_changed ②running
    // 所以同時時顯示 model_changed 文案
    const r2b = statusLine({
        ...base, running: true, model_changed: true, indexed: 1, total: 2, model: 'm',
    }, 0);
    assert.equal(r2b.key, 'settings.ai.similar.status_model_changed');

    // ③ unreachable + last_success_at
    const ts = Date.UTC(2026, 0, 15, 6, 30, 0) / 1000; // 固定 unix
    const r3 = statusLine({
        ...base, unreachable: true, last_success_at: ts, model: 'm', indexed: 3, total: 10,
    }, 0);
    assert.equal(r3.key, 'settings.ai.similar.status_unreachable');
    assert.ok(r3.params.time);
    assert.match(r3.params.time, /^\d{2}:\d{2}$/);

    // unreachable 無 last_success_at → 時間空
    const r3b = statusLine({
        ...base, unreachable: true, last_success_at: null, model: 'm',
    }, 0);
    assert.equal(r3b.key, 'settings.ai.similar.status_unreachable');
    assert.equal(r3b.params.time, '');

    // ④ model 已設且 pending>0 或 !complete
    const r4 = statusLine({
        ...base, model: 'm', pending: 4, complete: false, indexed: 6, total: 10,
    }, 0);
    assert.equal(r4.key, 'settings.ai.similar.status_incomplete');
    assert.equal(r4.params.n, 4);

    // ⑤ model 已設且完成
    const r5 = statusLine({
        ...base, model: 'clip', pending: 0, complete: true,
        indexed: 8, total: 10, last_success_at: ts,
    }, 0);
    assert.equal(r5.key, 'settings.ai.similar.status_ready');
    assert.equal(r5.params.n, 8);
    assert.equal(r5.params.m, 10);
    assert.equal(r5.params.model, 'clip');
    assert.match(r5.params.time, /^\d{2}:\d{2}$/);

    // ⑥ model 未設
    const r6 = statusLine({ ...base }, 0);
    assert.equal(r6.key, 'settings.ai.similar.status_none');

    // unreadable extra on ③④⑤
    const rExtra = statusLine({
        ...base, model: 'm', pending: 0, complete: true,
        indexed: 8, total: 10, unreadable: 2, last_success_at: ts,
    }, 0);
    assert.equal(rExtra.extra, 'settings.ai.similar.status_unreadable_extra');
    assert.equal(rExtra.params.k, 2);

    const rNoExtra = statusLine({
        ...base, model: 'm', pending: 0, complete: true,
        indexed: 10, total: 10, unreadable: 0, last_success_at: ts,
    }, 0);
    assert.equal(rNoExtra.extra, null);

    // model_changed / running 不加 unreadable extra
    const rNoExtra2 = statusLine({
        ...base, model_changed: true, unreadable: 3, model: 'm',
    }, 0);
    assert.equal(rNoExtra2.extra, null);
});

test('panelMode_fields_when_enabled_even_if_url_empty', () => {
    assert.equal(panelMode({ aiSimilarEnabled: true, aiSimilarUrl: '' }), 'fields');
    assert.equal(panelMode({ aiSimilarEnabled: true, aiSimilarUrl: 'http://x' }), 'fields');
    assert.equal(panelMode({ aiSimilarEnabled: false, aiSimilarUrl: '' }), 'empty');
    assert.equal(panelMode({ aiSimilarEnabled: false, aiSimilarUrl: 'http://x' }), 'empty');
});
