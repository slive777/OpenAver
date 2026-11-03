// TASK-189a-T10: 補跑共用層（ai-backfill-logic）與三份 adapter 的映射表驅動等價測試
//
// 舊 → 新動作映射表（舊函式當 oracle 直接 import；夾具逐字取自四支舊表驅動測試的所有呼叫）
//   功能  舊函式回傳         新 actionOf  新 extraAction  新通用 rebuildVisible
//   相似  indexAction null    null          null            ＝舊 rebuildVisible
//         'stop'              'stop'        null            false
//         'continue'          resumable? 'continue' : 'start'  null  ＝舊 rebuildVisible
//         'build'             'start'       null            ＝舊 rebuildVisible
//         'retry'             null          'retry'         ＝舊 rebuildVisible
//         'rebuild'           null          null            true
//   人臉  recomputeAction 'stop'    'stop'      null        false
//         'resume'            resumable? 'continue' : 'start'  null  ＝舊 deleteRebuildVisible
//         'none'              null          null            ＝舊 deleteRebuildVisible
//   resumable（只有中途停下才叫「繼續」，其餘有待補一律「補完全庫」＝start）：
//     相似＝已定模型 ∧ 索引未 complete ∧ indexed+unreadable>0；人臉＝有 target_model ∧ pending>0 ∧ stopped_reason 有值；標籤沿用後端 resumable。
//   標籤  backfillAction {action,disabled,reason}  整物件 deepEqual  null  enabled ∧ !running ∧ total>0

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
    normalizeStatus,
    actionOf,
    extraActionOf,
    rebuildVisible,
    progressLine,
    pendingLine,
} from '../ai-backfill-logic.js';
import {
    indexAction,
    rebuildVisible as simLegacyRebuildVisible,
    statusLine as simStatusLine,
    adapter as simAdapter,
} from '../ai-similar-logic.js';
import {
    recomputeAction,
    deleteRebuildVisible as facesLegacyRebuildVisible,
    recomputeLine,
    adapter as facesAdapter,
} from '../ai-faces-logic.js';
import {
    backfillAction,
    statusLine as tagsStatusLine,
    adapter as tagsAdapter,
} from '../ai-tags-logic.js';

// 映射表的 action 可為 { resumable, fresh }：中途停下叫 continue，其餘有待補叫 start
const pickAction = (a, resumable) => (a !== null && typeof a === 'object' ? (resumable ? a.resumable : a.fresh) : a);

const SIM_MAP = {
    null: { action: null, extra: null, rebuild: 'legacy' },
    stop: { action: 'stop', extra: null, rebuild: false },
    continue: { action: { resumable: 'continue', fresh: 'start' }, extra: null, rebuild: 'legacy' },
    build: { action: 'start', extra: null, rebuild: 'legacy' },
    retry: { action: null, extra: 'retry', rebuild: 'legacy' },
    rebuild: { action: null, extra: null, rebuild: true },
};
const FACES_MAP = {
    stop: { action: 'stop', rebuild: false },
    resume: { action: { resumable: 'continue', fresh: 'start' }, rebuild: 'legacy' },
    none: { action: null, rebuild: 'legacy' },
};

// [id, status, testPassed, 期望 view.resumable]：逐字取自 ai-similar-logic.test.mjs indexAction_table 的 13 個呼叫
const SIM_INDEX_CASES = [
    ['S01', null, true, false],
    ['S02', undefined, true, false],
    ['S03', { running: true, model_changed: true, model: 'm', pending: 1, complete: false }, true, false],
    ['S04', { running: true, model_changed: false, model: null, pending: 0, complete: false }, false, false],
    ['S05', { running: false, model_changed: true, model: 'old', pending: 0, complete: true }, true, false],
    ['S06', { running: false, model_changed: false, model: 'm', pending: 3, complete: false }, true, false],
    ['S07', { running: false, model_changed: false, model: 'm', pending: 0, complete: false }, false, false],
    ['S08', { running: false, model_changed: false, model: null, pending: 0, complete: false }, true, false],
    ['S09', { running: false, model_changed: false, model: '', pending: 0, complete: false }, true, false],
    ['S10', { running: false, model_changed: false, model: null, pending: 0, complete: false }, false, false],
    ['S11', { running: false, model_changed: false, model: 'm', pending: 0, complete: true, unreadable: 0 }, true, false],
    ['S12', { running: false, model_changed: false, model: 'm', pending: 0, complete: true, unreadable: 3 }, true, false],
    ['S13', { running: false, model_changed: false, model: 'm', pending: 0, complete: true, unreadable: 0 }, false, false],
    // 新增夾具（舊 indexAction 皆回 'continue'）：中途停下（未 complete 且已有進度）→ 繼續；新片入庫（complete 且 pending>0）→ 補完全庫
    ['S14', { running: false, model_changed: false, model: 'm', pending: 3, complete: false, indexed: 5, unreadable: 0 }, false, true],
    ['S15', { running: false, model_changed: false, model: 'm', pending: 4, complete: false, indexed: 0, unreadable: 2 }, false, true],
    ['S16', { running: false, model_changed: false, model: 'm', pending: 3, complete: true, indexed: 5, unreadable: 0 }, false, false],
];

// [id, status, enabled]：rebuildVisible_table 的 7 個呼叫（idle 取自該測試內的 const）
const SIM_IDLE = { running: false, indexed: 5, unreadable: 0 };
const SIM_REBUILD_CASES = [
    ['R01', SIM_IDLE, true],
    ['R02', { running: false, indexed: 0, unreadable: 2 }, true],
    ['R03', SIM_IDLE, false],
    ['R04', { ...SIM_IDLE, running: true }, true],
    ['R05', { running: false, indexed: 0, unreadable: 0 }, true],
    ['R06', null, true],
    ['R07', undefined, true],
];

// recomputeAction 6 個（F13~F15 為新增）＋deleteRebuildVisible 6 個
const FACES_ACTION_CASES = [
    ['F01', { running: true, pending: 0 }],
    ['F02', { running: true, pending: 5 }],
    ['F03', { running: false, pending: 3, target_model: 'm' }],
    ['F04', { running: false, pending: 3, target_model: null }],
    ['F05', { running: false, pending: 0 }],
    ['F06', null],
    // 新增夾具：上一輪因失敗／被關閉停下（舊 recomputeAction 皆回 'resume'）→ 繼續；無 target_model 仍 none
    ['F13', { running: false, pending: 3, target_model: 'm', stopped_reason: 'unreachable' }],
    ['F14', { running: false, pending: 3, target_model: 'm', stopped_reason: 'contract' }],
    ['F15', { running: false, pending: 3, target_model: null, stopped_reason: 'unreachable' }],
];
const FACES_IDLE = { running: false, rebuild_count: 7, pending: 0 };
const FACES_REBUILD_CASES = [
    ['F07', FACES_IDLE, true],
    ['F08', FACES_IDLE, false],
    ['F09', { ...FACES_IDLE, running: true }, true],
    ['F10', { running: false, rebuild_count: 0 }, true],
    ['F11', null, true],
    ['F12', undefined, true],
];

// [id, status, opts, rebuildLiteral]：backfillAction_table 的 10 個呼叫。
// 舊面板 rebuildVisible 公式 enabled ∧ !running ∧ total>0 不是匯出函式 → 期望寫成字面值（原夾具皆無 total → false）。
// T11~T13 為新增夾具（帶 total），讓重建鈕可見的分支也被守住。
const TAGS_CASES = [
    ['T01', null, undefined, false],
    ['T02', undefined, undefined, false],
    ['T03', { running: true, resumable: false, pending: 3 }, { dirty: true, enabled: false }, false],
    ['T04', { running: false, resumable: true, pending: 5 }, { dirty: false, enabled: true }, false],
    ['T05', { running: false, resumable: false, pending: 4 }, { dirty: false, enabled: true }, false],
    ['T06', { running: false, resumable: false, pending: 0 }, { dirty: false, enabled: true }, false],
    ['T07', { running: false, resumable: true, pending: 5 }, { dirty: true, enabled: true }, false],
    ['T08', { running: false, resumable: false, pending: 4 }, { dirty: true, enabled: true }, false],
    ['T09', { running: false, resumable: true, pending: 5 }, { dirty: false, enabled: false }, false],
    ['T10', { running: false, resumable: false, pending: 4 }, { dirty: false, enabled: false }, false],
    ['T11', { running: false, resumable: false, pending: 4, total: 10 }, { dirty: false, enabled: true }, true],
    ['T12', { running: true, resumable: false, pending: 4, total: 10 }, { dirty: false, enabled: true }, false],
    ['T13', { running: false, resumable: false, pending: 4, total: 10 }, { dirty: false, enabled: false }, false],
];

test('adapter_actions_equal_legacy_via_mapping_table', () => {
    // ── 相似：indexAction 13 個呼叫
    for (const [id, status, tp, resumable] of SIM_INDEX_CASES) {
        const old = String(indexAction(status, tp));
        const row = SIM_MAP[old];
        assert.ok(row, `${id}: 映射表查不到舊回傳 ${old}`);
        const view = normalizeStatus(simAdapter, status);
        const ctx = { enabled: true, testPassed: tp };
        const main = actionOf(simAdapter, view, ctx);
        const extra = extraActionOf(simAdapter, view, ctx);
        if (view) assert.equal(view.resumable, resumable, `${id}: resumable`);
        assert.equal(main.action, pickAction(row.action, resumable), `${id}: 主動作`);
        assert.equal(extra.action, row.extra, `${id}: 副動作`);
        const wantRebuild = row.rebuild === 'legacy' ? simLegacyRebuildVisible(status, true) : row.rebuild;
        assert.equal(rebuildVisible(simAdapter, view, ctx), wantRebuild, `${id}: 重建鈕`);
    }
    // ── 相似：rebuildVisible 7 個呼叫（全無 model_changed → 與舊函式逐案相同）
    for (const [id, status, enabled] of SIM_REBUILD_CASES) {
        const view = normalizeStatus(simAdapter, status);
        assert.equal(
            rebuildVisible(simAdapter, view, { enabled }),
            simLegacyRebuildVisible(status, enabled),
            id,
        );
    }
    // ── 人臉：recomputeAction 6 個呼叫
    for (const [id, status] of FACES_ACTION_CASES) {
        const old = recomputeAction(status);
        const row = FACES_MAP[old];
        assert.ok(row, `${id}: 映射表查不到舊回傳 ${old}`);
        const view = normalizeStatus(facesAdapter, status);
        const resumable = Boolean(status && status.target_model && status.pending > 0 && status.stopped_reason);
        if (view) assert.equal(view.resumable, resumable, `${id}: resumable`);
        assert.equal(
            actionOf(facesAdapter, view, { enabled: true }).action,
            pickAction(row.action, resumable),
            `${id}: 主動作`,
        );
        assert.equal(extraActionOf(facesAdapter, view, { enabled: true }).action, null, `${id}: 副動作`);
        const wantRebuild = row.rebuild === 'legacy' ? facesLegacyRebuildVisible(status, true) : row.rebuild;
        assert.equal(rebuildVisible(facesAdapter, view, { enabled: true }), wantRebuild, `${id}: 重建鈕`);
    }
    // ── 人臉：deleteRebuildVisible 6 個呼叫
    for (const [id, status, enabled] of FACES_REBUILD_CASES) {
        const view = normalizeStatus(facesAdapter, status);
        assert.equal(
            rebuildVisible(facesAdapter, view, { enabled }),
            facesLegacyRebuildVisible(status, enabled),
            id,
        );
    }
    // ── 標籤：backfillAction 整物件 deepEqual（含 dirty／not_enabled）＋重建鈕字面期望
    for (const [id, status, opts, wantRebuild] of TAGS_CASES) {
        const view = normalizeStatus(tagsAdapter, status);
        const ctx = opts || {};
        assert.deepEqual(actionOf(tagsAdapter, view, ctx), backfillAction(status, opts), id);
        assert.equal(extraActionOf(tagsAdapter, view, ctx).action, null, `${id}: 副動作`);
        assert.equal(rebuildVisible(tagsAdapter, view, ctx), wantRebuild, `${id}: 重建鈕`);
    }
    // ── 進行中：dirty／未啟用／busy 也不鎖「停止」
    const lock = { dirty: true, enabled: false, busy: true };
    for (const [adp, raw] of [
        [simAdapter, { running: true, indexed: 5, unreadable: 2, total: 20, pending: 13, model: 'm' }],
        [facesAdapter, { running: true, processed: 3, total: 9, pending: 6, target_model: 'm' }],
        [tagsAdapter, { running: true, tagged: 6, total: 10, pending: 4 }],
    ]) {
        const view = normalizeStatus(adp, raw);
        assert.deepEqual(actionOf(adp, view, lock), { action: 'stop', disabled: false, reason: null }, adp.tab);
        assert.equal(rebuildVisible(adp, view, { enabled: true }), false, `${adp.tab}: running 不顯示重建`);
    }
    // ── 通用層鎖定順序與 null 邊界
    const cont = normalizeStatus(tagsAdapter, { running: false, resumable: true, pending: 5 });
    assert.equal(actionOf(tagsAdapter, cont, { busy: true }).reason, 'busy');
    assert.equal(actionOf(tagsAdapter, cont, { blocked: 'cooling' }).reason, 'cooling');
    assert.equal(actionOf(tagsAdapter, cont, { dirty: true, busy: true }).reason, 'dirty');
    assert.deepEqual(actionOf(tagsAdapter, null, {}), { action: null, disabled: true, reason: null });
    assert.deepEqual(extraActionOf(simAdapter, null, {}), { action: null, disabled: true, reason: null });
    assert.equal(rebuildVisible(simAdapter, null, {}), false);
    assert.equal(normalizeStatus(simAdapter, null), null);
    assert.equal(normalizeStatus(simAdapter, undefined), null);
});

test('progress_line_xy_matches_legacy_running_lines', () => {
    const ts = Date.UTC(2026, 0, 15, 6, 30, 0) / 1000;
    const cases = [
        [simAdapter, { running: true, indexed: 5, unreadable: 2, total: 20, pending: 13, model: 'm' },
            (r) => simStatusLine(r, 0).params, 7, 20],
        [tagsAdapter, { running: true, tagged: 6, total: 10, pending: 4 },
            (r) => tagsStatusLine(r).params, 6, 10],
        [facesAdapter, { running: true, processed: 3, total: 9, pending: 6, target_model: 'm' },
            (r) => recomputeLine(r).params, 3, 9],
    ];
    for (const [adp, raw, legacyParams, n, m] of cases) {
        const line = progressLine(normalizeStatus(adp, raw));
        const legacy = legacyParams(raw);
        assert.ok(line, `${adp.tab}: running 必須有進度列`);
        assert.equal(line.key, 'settings.ai.backfill.progress_running', adp.tab);
        assert.equal(line.params.n, legacy.n, `${adp.tab}: n 同舊列`);
        assert.equal(line.params.m, legacy.m, `${adp.tab}: m 同舊列`);
        assert.equal(line.params.n, n, `${adp.tab}: n`);
        assert.equal(line.params.m, m, `${adp.tab}: m`);
        assert.equal(line.params.time, '', `${adp.tab}: 無成功時間`);
        assert.equal(line.extra, null, `${adp.tab}: 無時間不帶 extra`);

        const withTime = progressLine(normalizeStatus(adp, { ...raw, last_success_at: ts }));
        assert.ok(withTime, `${adp.tab}: 帶成功時間仍有進度列`);
        assert.match(withTime.params.time, /^\d{2}:\d{2}$/, `${adp.tab}: time`);
        assert.equal(withTime.extra, 'settings.ai.backfill.progress_last_success', `${adp.tab}: extra`);

        // 非 running → null
        assert.equal(progressLine(normalizeStatus(adp, { ...raw, running: false })), null, `${adp.tab}: idle`);
    }
    assert.equal(progressLine(null), null);
    assert.equal(progressLine(normalizeStatus(simAdapter, undefined)), null);
});

test('pending_line_and_rebuild_confirm_use_each_features_own_n', () => {
    // 相似：pending 13（indexed 5＋unreadable 2 → 確認框 n=7）
    const simIdle = { running: false, model: 'm', complete: false, indexed: 5, unreadable: 2, total: 20, pending: 13 };
    const simView = normalizeStatus(simAdapter, simIdle);
    assert.deepEqual(pendingLine(simView), { key: 'settings.ai.backfill.pending_line', params: { n: 13 } });
    assert.deepEqual(simAdapter.rebuildConfirm(simView), {
        key: 'settings.ai.similar.rebuild_confirm', params: { n: 7 },
    });
    // model_changed：過期的「還有 N 部」不顯示（pending>0、indexed>0 夾具）
    assert.equal(pendingLine(normalizeStatus(simAdapter, { ...simIdle, model_changed: true })), null);
    // running：不顯示
    assert.equal(pendingLine(normalizeStatus(simAdapter, { ...simIdle, running: true })), null);

    // 人臉：pending 6、rebuild_count 11
    const facesIdle = { running: false, processed: 3, total: 9, pending: 6, rebuild_count: 11, target_model: 'm' };
    const facesView = normalizeStatus(facesAdapter, facesIdle);
    assert.deepEqual(pendingLine(facesView), { key: 'settings.ai.backfill.pending_line', params: { n: 6 } });
    assert.deepEqual(facesAdapter.rebuildConfirm(facesView), {
        key: 'settings.ai.faces.rebuild_confirm', params: { n: 11 },
    });
    // 無 target_model 而 pending>0：不顯示、也不給繼續
    const noTarget = normalizeStatus(facesAdapter, { ...facesIdle, target_model: null });
    assert.equal(pendingLine(noTarget), null);
    assert.equal(actionOf(facesAdapter, noTarget, {}).action, null);
    assert.equal(pendingLine(normalizeStatus(facesAdapter, { ...facesIdle, running: true })), null);

    // 標籤：pending 4、total 10
    const tagsIdle = { running: false, tagged: 6, total: 10, pending: 4 };
    const tagsView = normalizeStatus(tagsAdapter, tagsIdle);
    assert.deepEqual(pendingLine(tagsView), { key: 'settings.ai.backfill.pending_line', params: { n: 4 } });
    assert.deepEqual(tagsAdapter.rebuildConfirm(tagsView), {
        key: 'settings.ai.tags.rebuild_confirm', params: { n: 10 },
    });
    assert.equal(pendingLine(normalizeStatus(tagsAdapter, { ...tagsIdle, running: true })), null);

    // 沒有待補或無狀態
    assert.equal(pendingLine(normalizeStatus(tagsAdapter, { ...tagsIdle, pending: 0 })), null);
    assert.equal(pendingLine(null), null);
});
