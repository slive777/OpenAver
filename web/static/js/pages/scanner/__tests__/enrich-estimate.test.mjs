import { test } from 'node:test';
import assert from 'node:assert/strict';
import { estimateEnrichMinutes } from '../state-batch.js';

test('estimate_enrich_minutes_weights_and_ceil', () => {
    const rows = [[300, 300, 55], [1, 0, 1], [501, 0, 9]];
    for (const [a, b, expected] of rows) {
        const actual = estimateEnrichMinutes(a, b);
        assert.equal(actual, expected, `(${a},${b})`);
    }
});
