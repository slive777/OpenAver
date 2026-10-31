// TASK-187a-T5: 人臉分頁純函式兩支表驅動測試
globalThis.window = globalThis;
window.t = (k) => k;

const {
    statusLine,
    recomputeLine,
    recomputeAction,
    deleteRebuildVisible,
} = await import('../ai-faces-logic.js');

import { test } from 'node:test';
import assert from 'node:assert/strict';

test('statusLine_table', () => {
    const base = {
        running: false,
        job_kind: null,
        processed: 0,
        total: 0,
        pending: 0,
        unreadable: 0,
        stopped_reason: null,
        target_model: null,
        rebuild_count: 0,
        using: 'local',
        observed: false,
        last_success_at: null,
    };

    // ① degraded → 本機（端點連不上）
    const ts = Date.UTC(2026, 0, 15, 6, 30, 0) / 1000;
    const r1 = statusLine({
        ...base,
        using: 'local',
        degraded: true,
        degraded_kind: 'unreachable',
        last_success_at: ts,
        target_model: 'buffalo_l',
    });
    assert.equal(r1.key, 'settings.ai.faces.status_local_degraded');
    assert.match(r1.params.time, /^\d{2}:\d{2}$/);

    // degraded 無時間
    const r1b = statusLine({
        ...base, using: 'local', degraded: true, last_success_at: null,
    });
    assert.equal(r1b.key, 'settings.ai.faces.status_local_degraded');
    assert.equal(r1b.params.time, '');

    // ② 自架・有成功紀錄
    const r2 = statusLine({
        ...base,
        using: 'external',
        observed: true,
        target_model: 'buffalo_l',
        last_success_at: ts,
    });
    assert.equal(r2.key, 'settings.ai.faces.status_external');
    assert.equal(r2.params.model, 'buffalo_l');
    assert.match(r2.params.time, /^\d{2}:\d{2}$/);

    // ③ 自架・尚未有成功紀錄
    const r3 = statusLine({
        ...base, using: 'external', observed: false, target_model: null,
    });
    assert.equal(r3.key, 'settings.ai.faces.status_external_unobserved');

    // ④ 本機（開關關／未存）
    const r4 = statusLine({ ...base, using: 'local' });
    assert.equal(r4.key, 'settings.ai.faces.status_local');

    // —— recomputeLine ——
    // running
    const rr1 = recomputeLine({
        ...base, running: true, processed: 3, total: 10, pending: 7,
    });
    assert.equal(rr1.key, 'settings.ai.faces.recompute_running');
    assert.equal(rr1.params.n, 3);
    assert.equal(rr1.params.m, 10);

    // stopped_reason 優先於 pending（需有 target_model）
    const rr2 = recomputeLine({
        ...base, pending: 5, stopped_reason: 'unreachable', target_model: 'm',
    });
    assert.equal(rr2.key, 'settings.ai.faces.recompute_stopped_unreachable');

    const rr2b = recomputeLine({
        ...base, pending: 5, stopped_reason: 'contract', target_model: 'm',
    });
    assert.equal(rr2b.key, 'settings.ai.faces.recompute_stopped_contract');

    // disabled（重算中關掉人臉）→ 不顯示「已停止」句，走未完成＋繼續
    const rr2c = recomputeLine({
        ...base, pending: 5, stopped_reason: 'disabled', target_model: 'm',
    });
    assert.equal(rr2c.key, 'settings.ai.faces.recompute_incomplete');
    assert.equal(rr2c.params.n, 5);

    // 無 target_model（開關剛開未存）→ 即使 pending>0 也不顯示未完成
    const rr3 = recomputeLine({ ...base, pending: 4, unreadable: 0, target_model: null });
    assert.equal(rr3, null);

    // 未完成＋封面讀不到
    const rr4 = recomputeLine({ ...base, pending: 4, unreadable: 2, target_model: 'm' });
    assert.equal(rr4.key, 'settings.ai.faces.recompute_incomplete');
    assert.equal(rr4.extra, 'settings.ai.faces.recompute_unreadable_extra');
    assert.equal(rr4.params.k, 2);

    // 無事可報
    assert.equal(recomputeLine({ ...base }), null);
    assert.equal(recomputeLine(null), null);
});

test('recomputeAction_deleteRebuildVisible_table', () => {
    assert.equal(recomputeAction({ running: true, pending: 0 }), 'stop');
    assert.equal(recomputeAction({ running: true, pending: 5 }), 'stop');
    assert.equal(recomputeAction({ running: false, pending: 3, target_model: 'm' }), 'resume');
    assert.equal(recomputeAction({ running: false, pending: 3, target_model: null }), 'none');
    assert.equal(recomputeAction({ running: false, pending: 0 }), 'none');
    assert.equal(recomputeAction(null), 'none');

    const idle = { running: false, rebuild_count: 7, pending: 0 };
    assert.equal(deleteRebuildVisible(idle, true), true);
    assert.equal(deleteRebuildVisible(idle, false), false);
    assert.equal(deleteRebuildVisible({ ...idle, running: true }, true), false);
    assert.equal(deleteRebuildVisible({ running: false, rebuild_count: 0 }, true), false);
    assert.equal(deleteRebuildVisible(null, true), false);
    assert.equal(deleteRebuildVisible(undefined, true), false);
});
