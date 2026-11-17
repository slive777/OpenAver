// TASK-201-T3: pick-tier 純函式（循環表）＋ pick pill 持久化往返（直接 import
// shared/pill-filter.js，零 window，不 stub 任何全域）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PICK_TIERS, PICK_OPS, pickTierRank, pickTierName, nextPickValue } from '../pick-tier.js';
import { buildPillPredicate, serializePills, deserializePills } from '../pill-filter.js';

const VIDEOS = [
    { n: 'gold', user_rating: 3 },
    { n: 'silver', user_rating: 2 },
    { n: 'bronze', user_rating: 1 },
    { n: 'zero', user_rating: 0 },
    { n: 'missing' },
    { n: 'null', user_rating: null },
];

test('nextPickValue: 循環 0→3→2→1→0、非法值先收斂', () => {
    assert.equal(nextPickValue(0), 3);
    assert.equal(nextPickValue(3), 2);
    assert.equal(nextPickValue(2), 1);
    assert.equal(nextPickValue(1), 0);
    assert.equal(nextPickValue(5), 2);
    assert.equal(nextPickValue(null), 3);
    assert.equal(nextPickValue(NaN), 3);
    assert.equal(pickTierRank(5), 3);
    assert.equal(pickTierName(0), null);
    assert.equal(pickTierName(1), 'bronze');
    assert.equal(pickTierName(2), 'silver');
    assert.equal(pickTierName(3), 'gold');
    assert.deepEqual(PICK_TIERS, ['bronze', 'silver', 'gold']);
    assert.deepEqual(PICK_OPS, ['>=', '=', '<=']);
});

test('pick pill persist roundtrip: 往返保留 op、舊 {pick,\'1\'} 載入＝≥銅', () => {
    const pills = [
        { dim: 'maker', value: 'S1' },
        { dim: 'pick', value: '2', op: '>=' },
    ];
    const ser = serializePills(pills);
    assert.deepEqual(ser[1], { dim: 'pick', value: '2', op: '>=' });
    const back = deserializePills(JSON.parse(JSON.stringify(ser)));
    assert.deepEqual(back, pills);
    const legacy = deserializePills([{ dim: 'pick', value: '1' }]);
    assert.deepEqual(legacy, [{ dim: 'pick', value: '1' }]);
    const names = VIDEOS.filter(buildPillPredicate(legacy, {}, {})).map((v) => v.n);
    assert.deepEqual(names, ['gold', 'silver', 'bronze']);
});

test('pick pill persist malformed: 畸形一枚丟一枚、相鄰 pill 保留', () => {
    const good1 = { dim: 'maker', value: 'A' };
    const good2 = { dim: 'tag', value: 'B' };
    const bad = [
        { dim: 'pick', value: '9' },
        { dim: 'pick', value: '0' },
        { dim: 'pick', value: '1', op: '~' },
        { dim: 'pick', value: '2', op: null },
    ];
    for (const b of bad) {
        assert.deepEqual(deserializePills([good1, b, good2]), [good1, good2]);
    }
    assert.deepEqual(deserializePills([{ dim: 'pick', value: '2' }]), [{ dim: 'pick', value: '2' }]);
    assert.deepEqual(deserializePills([{ dim: 'pick', value: '2', op: '<=' }]), [{ dim: 'pick', value: '2', op: '<=' }]);
});
