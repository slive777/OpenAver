// TASK-191a-T5: 舞台進度的純函式（捲動位置 → 進度 → 步數）。不經 DOM、不經 Alpine。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { stepOf, stepForward, stepBack, progressOf } = await import('../stage-math.js');

test('step_follows_scroll_both_directions', () => {
    const up = [0, 0.5, 0.99, 1, 2.5, 3, 3.99, 4];
    const want = [1, 1, 1, 2, 3, 4, 4, 4];
    assert.deepEqual(up.map((v) => stepOf(v)), want);
    // 往回捲：同一組進度倒著走，步數是鏡像，不卡在較大的那一步
    assert.deepEqual([...up].reverse().map((v) => stepOf(v)), [...want].reverse());
    assert.equal(stepBack(3.5, null), 3);
    assert.equal(stepBack(3.95, null), 4);
    assert.equal(stepBack(3.5, { active: true, step: 3 }), 2);
});

test('page_down_jumps_exactly_one_step_from_rest_point', () => {
    assert.equal(stepForward(0.3, null), 1);   // 還沒到本步定格點：先到本步
    assert.equal(stepForward(0.86, null), 2);  // 已在定格點：到下一步
    assert.equal(stepForward(1.3, null), 2);
    assert.equal(stepForward(3.86, null), 5);  // 末步定格點：越界，引擎忽略
    assert.equal(stepForward(0.3, { active: true, step: 2 }), 3); // 連按走 glide.step+1
});

test('progress_is_clamped_to_track', () => {
    const m = { top: 500, h: 4455, pinH: 855, gap: 45 }; // stepPx = (4455-855)/4 = 900
    assert.equal(progressOf(m), 0);                       // pin 還沒釘住
    assert.equal(progressOf({ ...m, top: -9000 }), 4);    // 捲過尾端
    assert.equal(progressOf({ ...m, top: 45 }), 0);
    assert.equal(progressOf({ ...m, top: 45 - 2 * 900 }), 2);
});
