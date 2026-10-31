// TASK-187b-T5a：plotFaceButtons 真值表（spec §3.3 四列＋翻譯關兩列）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { plotFaceButtons } = await import('../lb-plot-logic.js');

test('test_plot_face_buttons_truth_table', () => {
    assert.deepEqual(
        plotFaceButtons({ translateEnabled: true, hasOriginal: false, showing: 'plot' }),
        ['translate'],
    );
    assert.deepEqual(
        plotFaceButtons({ translateEnabled: false, hasOriginal: false, showing: 'plot' }),
        [],
    );
    assert.deepEqual(
        plotFaceButtons({ translateEnabled: true, hasOriginal: true, showing: 'plot' }),
        ['toggle'],
    );
    assert.deepEqual(
        plotFaceButtons({ translateEnabled: false, hasOriginal: true, showing: 'plot' }),
        ['toggle'],
    );
    assert.deepEqual(
        plotFaceButtons({ translateEnabled: true, hasOriginal: true, showing: 'original' }),
        ['toggle', 'retranslate'],
    );
    assert.deepEqual(
        plotFaceButtons({ translateEnabled: false, hasOriginal: true, showing: 'original' }),
        ['toggle'],
    );
});
