// TASK-198a-T4: resolution pill 比對與持久化（純函式，直接 import shared/pill-filter.js，零 window）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPillPredicate, serializePills, deserializePills } from '../../../shared/pill-filter.js';

// 沒讀過的三種形狀：null、缺鍵（升級前舊 payload）、未知字串
const VIDEOS = [
    { n: 'sd', resolution_tier: 'SD' },
    { n: 'hd', resolution_tier: 'HD' },
    { n: 'fhd', resolution_tier: 'FHD' },
    { n: '2k', resolution_tier: '2K' },
    { n: '4k', resolution_tier: '4K' },
    { n: '8k', resolution_tier: '8K' },
    { n: 'null', resolution_tier: null },
    { n: 'missing' },
    { n: 'unknown', resolution_tier: '9K' },
];

function pick(pill) {
    const pred = buildPillPredicate([pill], {}, {});
    return VIDEOS.filter(pred).map((v) => v.n);
}

test('resolution pill: 比較依等級序、沒讀過的片在任何 op 下都不符', () => {
    assert.deepEqual(pick({ dim: 'resolution', op: '>=', value: 'FHD' }), ['fhd', '2k', '4k', '8k']);
    assert.deepEqual(pick({ dim: 'resolution', op: '<=', value: 'HD' }), ['sd', 'hd']);
    assert.deepEqual(pick({ dim: 'resolution', op: '=', value: '4K' }), ['4k']);
    assert.deepEqual(pick({ dim: 'resolution', op: '>=', value: 'SD' }), ['sd', 'hd', 'fhd', '2k', '4k', '8k']);
    assert.deepEqual(pick({ dim: 'resolution', op: '<=', value: '8K' }), ['sd', 'hd', 'fhd', '2k', '4k', '8k']);
    // fail-closed：未知 op、未知 value、缺 op → 一片都不符（含 null／缺鍵／未知等級的片）
    assert.deepEqual(pick({ dim: 'resolution', op: 'range', value: 'FHD' }), []);
    assert.deepEqual(pick({ dim: 'resolution', op: '>=', value: '9K' }), []);
    assert.deepEqual(pick({ dim: 'resolution', op: '=', value: '9K' }), []);
    assert.deepEqual(pick({ dim: 'resolution', value: 'FHD' }), []);
});

test('resolution pill: serialize/deserialize 往返保留 op 與 value、畸形一枚丟一枚', () => {
    const pills = [
        { dim: 'maker', value: 'S1' },
        { dim: 'resolution', op: '>=', value: 'FHD', value2: 'stale' },
        { dim: 'release', op: 'range', value: '2023-01', value2: '2023-06' },
    ];
    const ser = serializePills(pills);
    assert.deepEqual(ser[1], { dim: 'resolution', value: 'FHD', op: '>=' });   // 帶 op、不帶 value2
    assert.deepEqual(ser[2], { dim: 'release', value: '2023-01', op: 'range', value2: '2023-06' });
    assert.deepEqual(deserializePills(JSON.parse(JSON.stringify(ser))), [
        { dim: 'maker', value: 'S1' },
        { dim: 'resolution', value: 'FHD', op: '>=' },
        { dim: 'release', value: '2023-01', op: 'range', value2: '2023-06' },
    ]);
    assert.equal(deserializePills([{ dim: 'resolution', op: '<=', value: 'HD' }])[0].op, '<=');
    assert.equal(deserializePills([{ dim: 'resolution', op: '=', value: '4K' }])[0].op, '=');

    // 畸形一枚丟一枚，夾在兩枚合法 pill 中間不連坐；' FHD ' trim 後合法
    const good1 = { dim: 'maker', value: 'A' };
    const good2 = { dim: 'tag', value: 'B' };
    const bad = [
        { dim: 'resolution', value: 'FHD' },                    // 缺 op
        { dim: 'resolution', op: 'range', value: 'FHD' },       // op 不在白名單
        { dim: 'resolution', op: '>=', value: '4k' },           // value 小寫不在等級表
        { dim: 'resolution', op: '>=', value: '9K' },
    ];
    for (const b of bad) {
        assert.deepEqual(deserializePills([good1, b, good2]), [good1, good2]);
    }
    assert.deepEqual(deserializePills([{ dim: 'resolution', op: '>=', value: ' FHD ' }]), [{ dim: 'resolution', value: 'FHD', op: '>=' }]);
});
