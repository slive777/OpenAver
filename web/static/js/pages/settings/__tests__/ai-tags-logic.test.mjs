// TASK-188c-T7: AI 標籤純函式四支表驅動測試（無 window.t）
const {
    costHint,
    formatUsd,
    backfillAction,
    connShown,
    connEnabled,
    statusLine,
} = await import('../ai-tags-logic.js');

import { test } from 'node:test';
import assert from 'node:assert/strict';

test('costHint_family_and_provider', () => {
    const haiku = costHint('claude', 'claude-haiku-5-5', 250);
    assert.equal(haiku.label, 'Haiku 5.5');
    assert.equal(haiku.per1000, 0.43);
    assert.ok(Math.abs(haiku.total - 0.43 * 250 / 1000) < 1e-9);

    const flashLite = costHint('gemini', 'gemini-flash-lite-latest', 250);
    assert.equal(flashLite.label, 'Gemini 3.5 Flash-Lite');
    assert.equal(flashLite.per1000, 0.72);
    assert.ok(Math.abs(flashLite.total - 0.72 * 250 / 1000) < 1e-9);

    // 大寫證明不分大小寫
    const flashLiteUpper = costHint('gemini', 'GEMINI-FLASH-LITE-LATEST', 1000);
    assert.equal(flashLiteUpper.per1000, 0.72);

    const luna = costHint('openai_official', 'gpt-6-luna', 250);
    assert.equal(luna.label, 'GPT-6 Luna');
    assert.equal(luna.per1000, 0.24);
    assert.ok(Math.abs(luna.total - 0.24 * 250 / 1000) < 1e-9);

    // Flash（非 Flash-Lite）→ null；mutation 把 flash-lite 改 flash 會在此紅
    assert.equal(costHint('gemini', 'gemini-flash-latest', 250), null);
    assert.equal(costHint('ollama', 'luna-8b', 250), null);
    assert.equal(costHint('claude', 'claude-sonnet-5', 250), null);

    // tiny total → formatUsd '<0.01'
    assert.equal(formatUsd(0.005), '<0.01');
    assert.equal(formatUsd(0.01), '0.01');
    assert.equal(formatUsd(1.234), '1.23');
});

test('backfillAction_table', () => {
    assert.deepEqual(backfillAction(null), { action: null, disabled: true, reason: null });
    assert.deepEqual(backfillAction(undefined), { action: null, disabled: true, reason: null });

    // running → stop；同時 dirty+enabled 假仍可按
    assert.deepEqual(
        backfillAction({ running: true, resumable: false, pending: 3 }, { dirty: true, enabled: false }),
        { action: 'stop', disabled: false, reason: null },
    );

    // resumable → continue
    assert.deepEqual(
        backfillAction({ running: false, resumable: true, pending: 5 }, { dirty: false, enabled: true }),
        { action: 'continue', disabled: false, reason: null },
    );

    // pending>0 → start
    assert.deepEqual(
        backfillAction({ running: false, resumable: false, pending: 4 }, { dirty: false, enabled: true }),
        { action: 'start', disabled: false, reason: null },
    );

    // pending=0 → null
    assert.deepEqual(
        backfillAction({ running: false, resumable: false, pending: 0 }, { dirty: false, enabled: true }),
        { action: null, disabled: true, reason: null },
    );

    // dirty → continue 與 start 皆鎖
    assert.deepEqual(
        backfillAction({ running: false, resumable: true, pending: 5 }, { dirty: true, enabled: true }),
        { action: 'continue', disabled: true, reason: 'dirty' },
    );
    assert.deepEqual(
        backfillAction({ running: false, resumable: false, pending: 4 }, { dirty: true, enabled: true }),
        { action: 'start', disabled: true, reason: 'dirty' },
    );

    // enabled 假 → not_enabled
    assert.deepEqual(
        backfillAction({ running: false, resumable: true, pending: 5 }, { dirty: false, enabled: false }),
        { action: 'continue', disabled: true, reason: 'not_enabled' },
    );
    assert.deepEqual(
        backfillAction({ running: false, resumable: false, pending: 4 }, { dirty: false, enabled: false }),
        { action: 'start', disabled: true, reason: 'not_enabled' },
    );
});

test('conn_shown_enabled_table', () => {
    // 翻譯關＋AI 標籤開選 gemini＋翻譯選 ollama → 兩區顯示；gemini 可編輯、ollama 不可
    const onlyTagsGemini = {
        translateEnabled: false,
        translateProvider: 'ollama',
        aiTagsEnabled: true,
        aiTagsProvider: 'gemini',
    };
    assert.equal(connShown(onlyTagsGemini, 'gemini'), true);
    assert.equal(connShown(onlyTagsGemini, 'ollama'), true);
    assert.equal(connEnabled(onlyTagsGemini, 'gemini'), true);
    assert.equal(connEnabled(onlyTagsGemini, 'ollama'), false);

    // AI 標籤關 → 不因它顯示／可編輯
    const tagsOff = {
        translateEnabled: false,
        translateProvider: 'ollama',
        aiTagsEnabled: false,
        aiTagsProvider: 'gemini',
    };
    assert.equal(connShown(tagsOff, 'gemini'), false);
    assert.equal(connEnabled(tagsOff, 'gemini'), false);

    // 翻譯開選 gemini → 可編輯
    const translateOnGemini = {
        translateEnabled: true,
        translateProvider: 'gemini',
        aiTagsEnabled: false,
        aiTagsProvider: '',
    };
    assert.equal(connShown(translateOnGemini, 'gemini'), true);
    assert.equal(connEnabled(translateOnGemini, 'gemini'), true);

    // 翻譯關但仍選 gemini → 顯示但不可編輯
    const translateOffStillGemini = {
        translateEnabled: false,
        translateProvider: 'gemini',
        aiTagsEnabled: false,
        aiTagsProvider: '',
    };
    assert.equal(connShown(translateOffStillGemini, 'gemini'), true);
    assert.equal(connEnabled(translateOffStillGemini, 'gemini'), false);
});

test('statusLine_stop_reason_routing', () => {
    const base = {
        running: false,
        unreachable: false,
        resumable: false,
        stop_reason: null,
        tagged: 3,
        total: 9,
        pending: 6,
        skipped: 0,
        slow: false,
        waiting: false,
        last_success_at: null,
    };

    const stopKeys = {
        unreachable: 'settings.ai.tags.status_stopped_unreachable',
        auth: 'settings.ai.tags.status_stopped_auth',
        model_unsupported: 'settings.ai.tags.status_stopped_model_unsupported',
        quota: 'settings.ai.tags.status_stopped_quota',
        not_configured: 'settings.ai.tags.status_stopped_not_configured',
        disabled: 'settings.ai.tags.status_stopped_disabled',
    };
    for (const [code, key] of Object.entries(stopKeys)) {
        const r = statusLine({ ...base, stop_reason: code });
        assert.equal(r.key, key);
        assert.deepEqual(r.extra, []);
    }
    // 六個互不相同；quota ≠ unreachable（行為④手動 mutation 會抓）
    assert.notEqual(stopKeys.quota, stopKeys.unreachable);
    const unique = new Set(Object.values(stopKeys));
    assert.equal(unique.size, 6);

    // running 優先於 stop_reason
    const running = statusLine({
        ...base, running: true, stop_reason: 'quota', tagged: 2, total: 10, skipped: 0,
    });
    assert.equal(running.key, 'settings.ai.tags.status_running');
    assert.equal(running.params.n, 2);
    assert.equal(running.params.m, 10);
    assert.deepEqual(running.extra, []);

    // slow／waiting／skipped 的 extra 陣列
    const slowWaitSkip = statusLine({
        ...base, running: true, slow: true, waiting: true, skipped: 2, tagged: 1, total: 5,
    });
    assert.equal(slowWaitSkip.key, 'settings.ai.tags.status_running');
    assert.deepEqual(slowWaitSkip.extra, [
        'settings.ai.tags.status_slow_extra',
        'settings.ai.tags.status_waiting_extra',
        'settings.ai.tags.status_skipped_extra',
    ]);
    assert.equal(slowWaitSkip.params.k, 2);

    // unreachable 旗標＋_no_time
    const unreachNoTime = statusLine({ ...base, unreachable: true, last_success_at: null });
    assert.equal(unreachNoTime.key, 'settings.ai.tags.status_unreachable_no_time');
    assert.equal(unreachNoTime.params.time, '');

    const ts = Date.UTC(2026, 0, 15, 6, 30, 0) / 1000;
    const unreach = statusLine({ ...base, unreachable: true, last_success_at: ts });
    assert.equal(unreach.key, 'settings.ai.tags.status_unreachable');
    assert.match(unreach.params.time, /^\d{2}:\d{2}$/);

    // resumable → incomplete，n 取 pending
    const incomplete = statusLine({
        ...base, resumable: true, pending: 6, tagged: 3, total: 9,
    });
    assert.equal(incomplete.key, 'settings.ai.tags.status_incomplete');
    assert.equal(incomplete.params.n, 6);
    assert.equal(incomplete.params.m, 9);
    assert.deepEqual(incomplete.extra, []);

    // ready，n 取 tagged；有 time／無 time
    const ready = statusLine({
        ...base, tagged: 8, total: 10, pending: 0, last_success_at: ts,
    });
    assert.equal(ready.key, 'settings.ai.tags.status_ready');
    assert.equal(ready.params.n, 8);
    assert.equal(ready.params.m, 10);
    assert.match(ready.params.time, /^\d{2}:\d{2}$/);

    const readyNoTime = statusLine({
        ...base, tagged: 8, total: 10, pending: 0, last_success_at: null,
    });
    assert.equal(readyNoTime.key, 'settings.ai.tags.status_ready_no_time');
    assert.equal(readyNoTime.params.time, '');

    // status 空 → status_none；extra 空陣列
    const none = statusLine(null);
    assert.equal(none.key, 'settings.ai.tags.status_none');
    assert.deepEqual(none.extra, []);
});
