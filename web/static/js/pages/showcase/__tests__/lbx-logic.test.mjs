// TASK-199a-T2：影片燈箱規格帶純函式（formatRuntime／bandParts）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { formatRuntime, bandParts } = await import('../lbx-logic.js');

test('test_format_runtime_hours_minutes', () => {
    assert.equal(formatRuntime(123), '2:03');
    assert.equal(formatRuntime(59), '0:59');
    assert.equal(formatRuntime(60), '1:00');
    for (const v of [0, null, undefined, NaN]) {
        assert.equal(formatRuntime(v), '');
    }
});

test('test_band_parts_omit_missing_fixed_order', () => {
    const fmt = { formatSize: (b) => 'S' + b, formatRuntime };
    const ids = (v, f = fmt) => bandParts(v, f).map((p) => p.id);

    // (a) 全欄位 → 固定順序：等級、編碼、片長、大小
    const full = { resolution_tier: '1080p', media_codec: 'HEVC', media_duration_min: 123, size: 5 };
    assert.deepEqual(ids(full), ['tier', 'codec', 'runtime', 'size']);
    assert.equal(bandParts(full, fmt).find((p) => p.id === 'runtime').text, '2:03');

    // (b) 只有大小 → 只剩大小；size 為假值時不呼叫 formatSize（其「未知」字樣不得出現）
    assert.deepEqual(ids({ size: 7 }), ['size']);
    let called = 0;
    const spy = { formatSize: () => { called += 1; return 'UNKNOWN'; }, formatRuntime };
    for (const size of [0, null, undefined]) {
        assert.deepEqual(bandParts({ size }, spy), []);
    }
    assert.equal(called, 0);
    assert.deepEqual(bandParts(null, fmt), []);

    // (c) 分集版本：media_duration_min 為 null 但來源片長有值 → 不顯示片長
    assert.deepEqual(ids({ media_duration_min: null, duration: 125, size: 7 }), ['size']);
});

// TASK-199a-T4：⋯ 選單項目條件（menuItems）。
test('test_menu_items_follow_path_samples_and_translate_gate', async () => {
    const { menuItems } = await import('../lbx-logic.js');
    const ids = (o) => menuItems({}, o).map((i) => i.id);

    // (a) 全條件成立 → 依序 samples、translate、rescrape、delete
    assert.deepEqual(ids({ sampleCount: 0, trVisible: true, hasPath: true }), ['samples', 'translate', 'rescrape', 'delete']);
    // (b) 沒有對應檔 → 只剩 rescrape（即使翻譯條件成立、沒劇照）
    assert.deepEqual(ids({ sampleCount: 0, trVisible: true, hasPath: false }), ['rescrape']);
    // (c) 已有劇照 → 不出 samples
    assert.deepEqual(ids({ sampleCount: 3, trVisible: true, hasPath: true }), ['translate', 'rescrape', 'delete']);
    // (d) 翻譯條件不成立 → 不出 translate
    assert.deepEqual(ids({ sampleCount: 0, trVisible: false, hasPath: true }), ['samples', 'rescrape', 'delete']);
});
