// TASK-198a-T5：提醒畫面模式的判斷順序（原生庫不可用不給無效按鈕；只有唯讀片的人仍找得到勾選入口）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reminderView, keepPollingAfterFailure } from '../media-probe-reminder-logic.js';

const base = {
    available: true, dismissed: false, include_readonly: false,
    pending: 0, readonly_pending: 0, job: { running: false, done: 0, total: 0 },
};

{
    const cases = [
        ['unavailable_beats_pending', { available: false, pending: 5 }, 'unavailable'],
        ['dismissed_hides_even_with_pending', { dismissed: true, pending: 5 }, 'hidden'],
        ['available_with_pending', { pending: 5 }, 'pending'],
        ['only_readonly_unread', { pending: 0, readonly_pending: 2 }, 'readonly_only'],
    ];
    for (const [name, patch, mode] of cases) {
        test(`reminderView_mode_by_status[${name}]`, () => {
            assert.equal(reminderView({ ...base, ...patch }, { later: false }).mode, mode);
        });
    }
}

test('keepPollingAfterFailure_only_while_job_running', () => {
    assert.equal(keepPollingAfterFailure({ ...base, job: { running: true, done: 1, total: 4 } }), true);
    assert.equal(keepPollingAfterFailure(base), false);
    assert.equal(keepPollingAfterFailure(null), false);
});
