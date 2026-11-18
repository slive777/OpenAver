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

test('test_ap_cover_cleared_when_work_hidden', async () => {
    // 片庫重算（隱藏未連線硬碟、重新載入片庫失敗）後，封面那部片不在可見清單了 → 封面必須回照片，
    // 否則縮圖排（回照片的唯一入口）整排消失、大圖卻停在離線檔的封面。
    const { _setVideos, _setVideosReady, _setActressIndex, _loadAliasMap } = await import('../state-base.js');
    const { buildActressIndex } = await import('../../../shared/actress-lookup.js');
    const realFetch = globalThis.fetch;
    globalThis.fetch = async () => ({ ok: false });
    try {
        await _loadAliasMap();
        _setActressIndex(buildActressIndex([{ name: 'A' }], {}));
        const v1 = { path: 'file:///C:/a1.mp4', number: 'AAA-001', actresses: 'A', release_date: '2022-01-01' };
        const v2 = { path: 'file:///C:/a2.mp4', number: 'AAA-002', actresses: 'A', release_date: '2022-02-01' };
        // 多版本：預設版本 m1（路徑 m1），另一個版本 m1b；封面點的是非預設版本
        const m1 = { path: 'file:///C:/m1.mp4', number: 'MMM-001', actresses: 'A', release_date: '2021-01-01' };
        const m1b = { path: 'file:///C:/m1b.mp4', number: 'MMM-001', actresses: 'A', release_date: '2021-01-01' };
        m1._versions = [m1, m1b];
        m1b._versions = m1._versions;
        const fresh = () => makeComponent({ currentLightboxActress: { name: 'A' }, lbxApCoverFailed: true, lbxApCoverShown: true });

        // 封面那部片仍在可見清單 → 封面不動（含旗標）
        _setVideosReady(true);
        _setVideos([v1, v2, m1]);
        let c = fresh();
        c.lbxApCover = { path: v1.path, number: v1.number };
        c.lbxApRebuild();
        assert.equal(c.lbxApTotal, 3);
        assert.equal(c.lbxApCover?.path, v1.path, '封面那部還在 → 不動');
        assert.equal(c.lbxApCoverShown, true, '封面沒清 → 旗標也不動');

        // 多版本：封面是非預設版本、同一部作品還在 → 不動（只比 path 會誤清）
        c = fresh();
        c.lbxApCover = { path: m1b.path, number: m1b.number };
        c.lbxApRebuild();
        assert.equal(c.lbxApCover?.path, m1b.path, '同一部作品的另一個版本還在 → 不動');

        // 封面那部片被藏起來（不在可見清單）但她還有別的片 → 封面清掉、旗標回初值
        _setVideos([v2, m1]);
        c = fresh();
        c.lbxApCover = { path: v1.path, number: v1.number };
        c.lbxApRebuild();
        assert.equal(c.lbxApTotal, 2, '縮圖排還在');
        assert.equal(c.lbxApCover, null, '封面那部片消失 → 回照片');
        assert.equal(c.lbxApCoverFailed, false);
        assert.equal(c.lbxApCoverShown, false);

        // 她的片全消失（總數 0）→ 封面清掉
        _setVideos([]);
        c = fresh();
        c.lbxApCover = { path: v1.path, number: v1.number };
        c.lbxApRebuild();
        assert.equal(c.lbxApTotal, 0);
        assert.equal(c.lbxApCover, null, '她的片全沒了 → 回照片');

        // 片庫沒就緒（fetchVideos 失敗）→ 封面清掉
        _setVideos([v1, v2]);
        _setVideosReady(false);
        c = fresh();
        c.lbxApCover = { path: v1.path, number: v1.number };
        c.lbxApRebuild();
        assert.equal(c.lbxApTotal, 0);
        assert.equal(c.lbxApCover, null, '片庫沒就緒 → 回照片');
        assert.equal(c.lbxApCoverShown, false);
    } finally {
        globalThis.fetch = realFetch;
        const sb = await import('../state-base.js');
        sb._setVideos([]);
        sb._setVideosReady(false);
        sb._setActressIndex(null);
    }
});

const { coverSwapPlan } = await import('../lbx-logic.js');

function withCoverGhosts(run) {
    const oldAnimations = window.ShowcaseAnimations, oldOpenAver = window.OpenAver;
    const registry = [];
    let builds = 0, releases = 0;
    window.OpenAver = { prefersReducedMotion: false };
    window.ShowcaseAnimations = {
        createGhost(_panel, { kind }) {
            builds++;
            const entry = { kind, released: false };
            registry.push(entry);
            return {
                release() { entry.released = true; releases++; },
                kill() { const i = registry.indexOf(entry); if (i >= 0) registry.splice(i, 1); },
            };
        },
        killGhosts(kind) { for (let i = registry.length - 1; i >= 0; i--) if (!kind || registry[i].kind === kind) registry.splice(i, 1); },
        ghostCount(kind) { return registry.filter((entry) => !kind || entry.kind === kind).length; },
    };
    const component = (cover = { path: 'a', cover_url: 'a' }) => makeComponent({
        lbxApCover: cover, lbxApCoverShown: true,
        $refs: { pickerCoverImg: { parentElement: { querySelector: () => ({}) } } },
    });
    try { run({ registry, component, builds: () => builds, releases: () => releases }); }
    finally { window.ShowcaseAnimations = oldAnimations; window.OpenAver = oldOpenAver; }
}

test('test_cover_swap_plan_table', () => {
    const base = { hadCover: true, toPhoto: false, prefersReducedMotion: false, sameSrc: false, bothNoImage: false };
    for (const [change, expected] of [[{ hadCover: false }, 'none'], [{}, 'swap'], [{ sameSrc: true }, 'none'], [{ bothNoImage: true }, 'none'], [{ toPhoto: true }, 'out'], [{ prefersReducedMotion: true }, 'none'], [{ toPhoto: true, prefersReducedMotion: true }, 'none']]) {
        assert.equal(coverSwapPlan({ ...base, ...change }), expected);
    }
});

test('test_cover_ghost_waits_for_image_event', () => withCoverGhosts(({ component, builds, releases }) => {
    const c = component({ path: 'a' });
    c.lbxApOpenCover({ path: 'b', cover_url: 'b' });
    assert.equal(builds(), 1);
    assert.equal(releases(), 0);
    c.lbxApOpenCover({ path: 'c', cover_url: 'c' });
    assert.equal(builds(), 1);
    c.lbxApCoverLoaded(null);
    assert.equal(releases(), 1);
    c.lbxApCoverLoaded(null);
    assert.equal(releases(), 1);
    c.lbxApOpenCover({ path: 'f', cover_url: 'f' });
    c.lbxApCoverError();
    assert.equal(releases(), 2);
    const same = builds();
    c.lbxApOpenCover({ path: 'g', cover_url: 'f' });
    assert.equal(builds(), same);
    c.lbxApOpenCover({ path: 'd' });
    assert.equal(releases(), 3);
    const before = builds();
    c.lbxApOpenCover({ path: 'e' });
    assert.equal(builds(), before);
}));

test('test_cover_reset_clears_ghost_without_building', () => withCoverGhosts(({ component, registry, builds, releases }) => {
    const c = component();
    c.lbxApOpenCover({ path: 'b', cover_url: 'b' });
    assert.equal(registry.length, 1, '前置：登記表有 1 個');
    c.lbxApReset();
    assert.equal(registry.length, 0);
    assert.equal(builds(), 1);
    c.lbxApCoverLoaded(null);
    assert.equal(releases(), 0);
}));

test('test_back_to_photo_ghost_survives_teardown', () => withCoverGhosts(({ component, registry, builds }) => {
    const c = component();
    c.lbxApBackToPhoto();
    assert.equal(registry.length, 1);
    assert.equal(registry[0].kind, 'cover');
    assert.equal(registry[0].released, true);
    window.ShowcaseAnimations.killGhosts();
    const waiting = component();
    waiting.lbxApOpenCover({ path: 'b', cover_url: 'b' });
    const before = builds();
    waiting.lbxApBackToPhoto();
    assert.equal(builds(), before);
    assert.equal(registry.length, 1);
    assert.equal(registry[0].released, true);
    window.ShowcaseAnimations.killGhosts();
    window.OpenAver.prefersReducedMotion = true;
    component().lbxApBackToPhoto();
    assert.equal(registry.length, 0);
}));

const { stripRevealPlan } = await import('../lbx-logic.js');

test('test_strip_reveal_plan_table', () => {
    assert.equal(stripRevealPlan({ trigger: 'switch', lightboxOpen: true }).play, true);
    const all = { play: true, photo: true, films: true, next: true };
    const none = { play: false, photo: false, films: false, next: false };
    const base = { lightboxOpen: true, lightboxAnimating: false };
    for (const [change, expected] of [
        [{ trigger: 'switch' }, all],
        [{ trigger: 'next' }, { play: true, photo: false, films: true, next: false }],
        [{ trigger: 'appear' }, all], [{ trigger: 'appear', lightboxAnimating: true }, none],
        ...['switch', 'next', 'appear', 'unknown'].map((trigger) => [{ trigger, lightboxOpen: false }, none]),
        [{ trigger: 'unknown' }, none],
    ]) assert.deepEqual(stripRevealPlan({ ...base, ...change }), expected);
});

test('test_strip_reveal_wiring_targets_and_counts', async () => {
    const sb = await import('../state-base.js');
    const oldFetch = globalThis.fetch, oldAnimations = window.ShowcaseAnimations, oldQuery = document.querySelector;
    const calls = [], strip = {};
    globalThis.fetch = async () => ({ ok: false });
    window.ShowcaseAnimations = { playApStripReveal(el, opts) { assert.equal(el, strip); calls.push(opts); } };
    document.querySelector = (selector) => selector === '.showcase-lightbox .lbx-ap-strip' ? strip : null;
    try {
        await sb._loadAliasMap();
        sb._setActresses([{ name: 'A' }]);
        sb._setActressesLoaded(false);
        const videos = Array.from({ length: 14 }, (_, i) => ({ path: `video-${i}`, number: `AAA-${i}`, actresses: 'A' }));
        sb._setVideos(videos);
        sb._setVideosReady(true);
        const c = makeComponent({ $nextTick(fn) { fn(); }, lightboxOpen: true, _lightboxAnimating: false, actressLightboxSource: 'grid', currentLightboxActress: { name: 'A' } });
        c._refreshActressDerived();
        calls.length = 0;
        c.lbxApNext();
        assert.equal(calls.length, 1, '前置：下一批呼叫動畫一次');
        assert.equal(c.lbxApStart, 6);
        assert.deepEqual(c.lbxApBatch, videos.slice(6, 12));
        for (const [start, length] of [[12, 2], [0, 6], [6, 6], [12, 2]]) {
            c.lbxApNext();
            assert.equal(c.lbxApStart, start);
            assert.equal(c.lbxApBatch.length, length);
            assert.deepEqual(c.lbxApBatch, videos.slice(start, start + 6));
        }
        assert.equal(calls.length, 5);
        for (const opts of calls) assert.deepEqual(opts, { photo: false, films: true, next: false });
        sb._setVideosReady(false);
        c.lbxApRebuild();
        assert.equal(c.lbxApStripVisible(), false);
        calls.length = 0;
        sb._setVideosReady(true);
        c._refreshActressDerived();
        assert.equal(calls.length, 1);
        assert.deepEqual(calls[0], { photo: true, films: true, next: true });
        c._refreshActressDerived();
        assert.equal(calls.length, 1);
    } finally {
        globalThis.fetch = oldFetch; window.ShowcaseAnimations = oldAnimations; document.querySelector = oldQuery;
        sb._setVideos([]); sb._setVideosReady(false); sb._setActressIndex(null); sb._setActresses([]); sb._setActressesLoaded(false);
    }
});
