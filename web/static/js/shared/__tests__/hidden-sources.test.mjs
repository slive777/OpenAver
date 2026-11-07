// 195b-T4: 「隱藏未連線硬碟」純函式（computeHiddenIndexes／splitVisible／hiddenNumberSet）。
// 純函式、無 DOM／Alpine／importmap 別名，plain node --test 直接 import。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { computeHiddenIndexes, splitVisible, hiddenNumberSet } = await import('../hidden-sources.js');

test('splitVisible：藏的是離線硬碟的片，沒有 src 的片視為可見，可見片順序不變', () => {
    const sources = ['D:\\電影', 'E:\\FC2', 'F:\\x'];
    const hiddenIdx = computeHiddenIndexes(sources, ['D:\\電影']);
    assert.deepEqual([...hiddenIdx], [0], 'D: 離線 → 只有索引 0 被藏');
    // 離線成員不在 sources 內、或沒有離線 → 什麼都不藏
    assert.deepEqual([...computeHiddenIndexes(sources, ['Z:\\nope'])], []);
    assert.deepEqual([...computeHiddenIndexes(sources, [])], []);

    // src === 0 是合法索引（不得用 truthy 判斷）；缺 src／非整數 src 一律可見（fail-open）
    const all = [
        { number: 'aaa-001', src: 0 },
        { number: 'bbb-002', src: 1 },
        { number: 'ccc-003' },
        { number: 'ddd-004', src: 0 },
        { number: 'eee-005', src: 2 },
        { number: 'fff-006', src: '0' },
        { number: 'ggg-007', src: null },
        { number: '', src: 0 },
    ];
    const { visible, hidden } = splitVisible(all, hiddenIdx);
    assert.deepEqual(visible.map((v) => v.number), ['bbb-002', 'ccc-003', 'eee-005', 'fff-006', 'ggg-007']);
    assert.deepEqual(hidden.map((v) => v.number), ['aaa-001', 'ddd-004', '']);
    assert.ok(visible[0] === all[1] && hidden[0] === all[0], '同一物件 ref，不複製');

    // 被藏番號集合：轉大寫、空番號略過
    assert.deepEqual([...hiddenNumberSet(hidden)].sort(), ['AAA-001', 'DDD-004']);
    // 空集合 → 全部可見、順序不變
    assert.deepEqual(splitVisible(all, new Set()).visible.map((v) => v.number), all.map((v) => v.number));
});
