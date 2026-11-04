// TASK-188c-T7: AI 標籤純函式四支表驅動測試（無 window.t）
const {
    costHint,
    formatUsd,
    backfillAction,
    connShown,
    connEnabled,
    statusLine,
    progressExtras,
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
    const mk = (over) => ({
        translateEnabled: true,
        translateProvider: 'ollama',
        aiTagsEnabled: true,
        aiTagsProvider: 'gemini',
        ...over,
    });
    const SAME = mk({ translateProvider: 'gemini' });
    const DIFF = mk({});

    // 翻譯分頁：恆只列翻譯選的那家（不管標籤選誰；翻譯關著也列）
    assert.equal(connShown(DIFF, 'ollama', 'translate'), true);
    assert.equal(connShown(DIFF, 'gemini', 'translate'), false);
    assert.equal(connShown(SAME, 'gemini', 'translate'), true);
    assert.equal(connShown(mk({ translateEnabled: false }), 'ollama', 'translate'), true);

    // 標籤分頁：恆只列標籤選的那家（不管翻譯選誰）；標籤關著一家都不列
    assert.equal(connShown(DIFF, 'gemini', 'tags'), true);
    assert.equal(connShown(DIFF, 'ollama', 'tags'), false);
    assert.equal(connShown(SAME, 'gemini', 'tags'), true);
    assert.equal(connShown(mk({ aiTagsEnabled: false }), 'gemini', 'tags'), false);

    // 相似／人臉（及未知）分頁：整區不列
    for (const tab of ['similar', 'faces', undefined]) {
        assert.equal(connShown(DIFF, 'ollama', tab), false);
        assert.equal(connShown(SAME, 'gemini', tab), false);
    }

    // 可編輯規則不變：翻譯開且選中、或標籤開且選中
    assert.equal(connEnabled(mk({ translateEnabled: false }), 'gemini'), true);
    assert.equal(connEnabled(mk({ translateEnabled: false }), 'ollama'), false);
    assert.equal(connEnabled(mk({ aiTagsEnabled: false }), 'gemini'), false);
    assert.equal(connEnabled(mk({ translateProvider: 'gemini', aiTagsEnabled: false }), 'gemini'), true);
    assert.equal(connEnabled(mk({ translateEnabled: false, translateProvider: 'gemini', aiTagsEnabled: false }), 'gemini'), false);
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
    // 跑中：重述主句交給進度行，舊狀態行 key 為 null（params 仍帶 n／m 供對照）
    assert.equal(running.key, null);
    assert.equal(running.params.n, 2);
    assert.equal(running.params.m, 10);
    assert.deepEqual(running.extra, []);

    // slow／waiting／skipped 的 extra 陣列
    const slowWaitSkip = statusLine({
        ...base, running: true, slow: true, waiting: true, skipped: 2, tagged: 1, total: 5,
    });
    assert.equal(slowWaitSkip.key, null);
    assert.deepEqual(slowWaitSkip.extra, []);
    assert.equal(slowWaitSkip.params.k, 2);
    // slow／waiting／skipped 三句改由 progressExtras 提供（併進進度行）
    assert.deepEqual(progressExtras({ running: true, slow: true, waiting: true, skipped: 2 }), [
        'settings.ai.tags.status_slow_extra',
        'settings.ai.tags.status_waiting_extra',
        'settings.ai.tags.status_skipped_extra',
    ]);
    assert.deepEqual(progressExtras({ running: true }), []);
    assert.deepEqual(progressExtras(null), []);

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
    // 閒置未完成：重述主句由「還有 N 部沒跑」取代，只留非重述 extra
    assert.equal(incomplete.key, null);
    assert.equal(incomplete.params.n, 6);
    assert.equal(incomplete.params.m, 9);
    assert.deepEqual(incomplete.extra, []);
    const incompleteSkipped = statusLine({ ...base, resumable: true, skipped: 3 });
    assert.equal(incompleteSkipped.key, null);
    assert.deepEqual(incompleteSkipped.extra, ['settings.ai.tags.status_skipped_extra']);

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
