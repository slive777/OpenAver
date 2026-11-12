// TASK-199b-T5: 女優燈箱縮圖排的兩個數字——批次標籤／繞回、發行日排序（純函式，只測 lbx-logic.js）。
// 重開第一次就有、鎖死、裁法、尺寸＝CDP／lint 判，不在這裡。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { batchLabel, nextBatchStart, sortWorksByRelease } = await import('../lbx-logic.js');

test('test_ap_batch_label_wrap', () => {
    // 28 部：中間批、最後一批不湊滿（25–28，to 要 clamp 到 total）
    assert.deepEqual(batchLabel(0, 6, 28), { from: 1, to: 6, total: 28 });
    assert.deepEqual(batchLabel(12, 6, 28), { from: 13, to: 18, total: 28 });
    assert.deepEqual(batchLabel(24, 6, 28), { from: 25, to: 28, total: 28 });
    // 8 部：第二批只有 2 部
    assert.deepEqual(batchLabel(0, 6, 8), { from: 1, to: 6, total: 8 });
    assert.deepEqual(batchLabel(6, 6, 8), { from: 7, to: 8, total: 8 });
    // 只剩 1 部：from===to，模板靠這個改用 films_next_one
    assert.deepEqual(batchLabel(24, 6, 25), { from: 25, to: 25, total: 25 });

    // 走完 28 部五批後繞回 0
    const seen = [];
    let start = 0;
    for (let i = 0; i < 5; i += 1) {
        seen.push(start);
        start = nextBatchStart(start, 6, 28);
    }
    assert.deepEqual(seen, [0, 6, 12, 18, 24]);
    assert.equal(start, 0);
    // 8 部：6 → 繞回
    assert.equal(nextBatchStart(0, 6, 8), 6);
    assert.equal(nextBatchStart(6, 6, 8), 0);
    // 整除的 total 也要繞回（30 部：24 → 30 不存在）
    assert.equal(nextBatchStart(24, 6, 30), 0);
    assert.equal(nextBatchStart(18, 6, 30), 24);
});

test('test_ap_sort_release_desc', () => {
    const A = { id: 'A', release_date: '2022-01-05' };
    const B = { id: 'B', release_date: '' };
    const C = { id: 'C', release_date: '2022-12-22' };
    const D = { id: 'D' };
    const E = { id: 'E', release_date: '2022-01-05' };
    const input = [A, B, C, D, E];
    const out = sortWorksByRelease(input);
    // 新→舊；同日維持輸入順序（A 在 E 前）；空字串與缺值排最後、維持輸入順序（B 在 D 前）
    assert.deepEqual(out.map((w) => w.id), ['C', 'A', 'E', 'B', 'D']);
    assert.equal(out[0], C);
    // 不改輸入
    assert.deepEqual(input.map((w) => w.id), ['A', 'B', 'C', 'D', 'E']);
    assert.notEqual(out, input);
});
