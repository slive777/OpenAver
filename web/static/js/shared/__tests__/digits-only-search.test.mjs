// TASK-195-T9（195d）：isDigitsOnlySearch 純函式真值表。
// 經真的 isDigitsOnlySearch（不自寫正規化）；true 陣列含全形與頭尾空白，證明有走 normalizePillValue。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { isDigitsOnlySearch } = await import('../digits-only-search.js');

test('isDigitsOnlySearch：只有純數字（含全形與頭尾空白）算，含字母／連字號／多詞一律不算', () => {
    const truthy = ['199', '001', '1991', '1723984', '2024', '１９９', ' 199 '];
    for (const input of truthy) {
        assert.equal(isDigitsOnlySearch(input), true, JSON.stringify(input));
    }
    const falsy = ['三上', '三上悠亞', 'Yua', 'NTR', '中出', '出差三天兩夜', 'S1', '199 三上', '三上 NTR', 'SSIS-001', 'ipx-1', 'SSIS', 'fc2', '2024-05', '', '   '];
    for (const input of falsy) {
        assert.equal(isDigitsOnlySearch(input), false, JSON.stringify(input));
    }
});
