// TASK-199a-T6：plotPopButtons 真值表（翻譯開／關 × 有／無原文）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { plotPopButtons } = await import('../lb-plot-logic.js');

test('test_plot_pop_buttons_truth_table', () => {
    assert.deepEqual(plotPopButtons({ translateEnabled: true, hasOriginal: false }), ['translate']);
    assert.deepEqual(plotPopButtons({ translateEnabled: true, hasOriginal: true }), ['retranslate']);
    assert.deepEqual(plotPopButtons({ translateEnabled: false, hasOriginal: false }), []);
    assert.deepEqual(plotPopButtons({ translateEnabled: false, hasOriginal: true }), []);
});
