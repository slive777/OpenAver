// TASK-199b-T5: 女優燈箱縮圖排的兩個數字——批次標籤／繞回、發行日排序（純函式，只測 lbx-logic.js）。
// 重開第一次就有、鎖死、裁法、尺寸＝CDP／lint 判，不在這裡。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

// 199b-T6：T6 的兩支要合成 picker／ap／actress 分片，分片 import 鏈需要 alias loader 與瀏覽器全域 stub。
// 必須在動態 import 各分片之前（形狀照 mask-nav-block.test.mjs）。
globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.Alpine = globalThis.Alpine || {
    store: () => ({ toolbarOpen: false, showcaseHasSearch: false }),
};
globalThis.document = globalThis.document || {
    querySelector() { return null; },
    body: { classList: { add() {}, remove() {}, contains() { return false; } } },
};
register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

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

// ---- TASK-199b-T6：點縮圖看封面 ----
const { stateLightbox } = await import('../state-lightbox.js');
const { stateLightboxPicker } = await import('../state-lightbox-picker.js');
const { stateLightboxMask } = await import('../state-lightbox-mask.js');
const { stateLightboxAp } = await import('../state-lightbox-ap.js');
const { stateActress } = await import('../state-actress.js');
const { _setFilteredActresses } = await import('../state-base.js');

function makeComponent(overrides) {
    return Object.assign({}, stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateActress(), stateLightboxAp(), {
        lightboxOpen: true,
        showFavoriteActresses: true,
        currentLightboxActress: null,
        actressLightboxIndex: 0,
        _pickerOpen: false,
        _maskVisible: false,
        $nextTick() {},
        $refs: {},
        _fetchLiveAliases() {},
    }, overrides);
}

test('test_ap_cover_exclusive', () => {
    // 其餘五個條件全滿足：照片有、已載入、夠寬、遮罩沒開、picker 沒開
    const ready = {
        currentLightboxActress: { name: 'A', photo_url: '/a.jpg' },
        _maskVisible: false,
        _actressPhotoLoaded: true,
        _actressPhotoWideEnough: true,
        _pickerOpen: false,
    };
    const closedCover = makeComponent({ ...ready, lbxApCover: null });
    assert.equal(closedCover._focalIconVisible(), true, '封面關閉：對焦鈕放行（防「永遠 false」假綠）');
    const openCover = makeComponent({ ...ready, lbxApCover: { path: 'file:///C:/a.mp4', number: 'AAA-001' } });
    assert.equal(openCover._focalIconVisible(), false, '封面開著：對焦鈕必須收起');

    // 縮圖排鎖死：四個旗標各自單獨為真都要鎖，全假才放行
    for (const flag of ['_maskVisible', '_pickerOpen', '_pickerLoading', '_pickerSelected']) {
        const c = makeComponent({ _maskVisible: false, _pickerOpen: false, _pickerLoading: false, _pickerSelected: false, [flag]: true });
        assert.equal(c.lbxApStripLocked(), true, `${flag} 為真 → 縮圖排鎖死`);
    }
    const idle = makeComponent({ _maskVisible: false, _pickerOpen: false, _pickerLoading: false, _pickerSelected: false });
    assert.equal(idle.lbxApStripLocked(), false, '全假 → 不鎖');
});

test('test_ap_cover_reset_on_switch', () => {
    _setFilteredActresses([{ name: 'A' }, { name: 'B' }]);
    try {
        const c = makeComponent({ currentLightboxActress: { name: 'A' }, actressLightboxIndex: 0 });
        c.lbxApCover = { path: 'file:///C:/a.mp4', number: 'AAA-001' };
        c.lbxApStart = 6;
        const seen = [];
        const real = c.lbxApReset;
        c.lbxApReset = function (...args) {
            seen.push(this.currentLightboxActress?.name);
            return real.apply(this, args);
        };
        c._setActressLightboxIndex(1);
        assert.equal(c.currentLightboxActress.name, 'B', '換到下一位');
        assert.equal(c.lbxApCover, null, '換人後封面必須清掉');
        assert.equal(c.lbxApStart, 0);
        assert.deepEqual(c.lbxApBatch, []);
        assert.deepEqual(seen, ['A'], 'lbxApReset 必須在賦值之前呼叫（當下還是舊那位）');
    } finally {
        _setFilteredActresses([]);
    }
});
