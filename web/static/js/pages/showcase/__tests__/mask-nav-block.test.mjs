// TASK-124c-T3：對焦編輯進行中，換片的每一個入口都不作用（spec-124c §3.4）。
//
// 為什麼是這個形狀（plan-124c §2.5）：
//   ① oracle spy 的是 _setLightboxIndex / _setActressLightboxIndex——兩個分支唯一的
//      狀態寫入點。不 spy 四個 chokepoint 本身：guard 在函式**內部**，「函式有被呼叫」
//      在 mask 開與關兩種狀態下都成立，spy 在那一層永遠驗不出東西。
//   ② 影片與女優各驗一次（8 格矩陣）。兩邊的 chokepoint 是兩份獨立的碼，只驗影片
//      等於女優那兩行沒有守衛（Codex plan review P3）。
//   ③ 用合成 component（stateLightbox() + stateActress()）而不是各自單獨呼叫函式——
//      _lbTouchEnd 是靠 this.showFavoriteActresses 分流到女優函式的，拆開驗就驗不到
//      那條分流。
//   ④ 方向映射兩套不同：左滑 = next / 右滑 = prev；ArrowLeft = prev / ArrowRight = next。
//   ⑤ _filteredVideos / _filteredActresses 是 state-base 的 module singleton，
//      每支測試 try/finally 清乾淨（FE-GUARD-13）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

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

const { stateLightbox } = await import('../state-lightbox.js');
const { stateLightboxPicker } = await import('../state-lightbox-picker.js');
const { stateLightboxMask } = await import('../state-lightbox-mask.js');
const { stateActress } = await import('../state-actress.js');
const { stateLightboxVersions } = await import('../state-lightbox-versions.js');
const { stateLightboxPop } = await import('../state-lightbox-pop.js');
const { stateLightboxTags } = await import('../state-lightbox-tags.js');
const { stateSimilar } = await import('../state-similar.js');
const { _setFilteredVideos, _setFilteredActresses } = await import('../state-base.js');

const VIDEOS = [
    { path: 'file:///C:/a.mp4', number: 'AAA-001' },
    { path: 'file:///C:/b.mp4', number: 'BBB-002' },
];
const ACTRESSES = [{ name: 'A' }, { name: 'B' }];

function makeComponent(overrides) {
    return Object.assign({}, stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateActress(), stateLightboxVersions(), stateLightboxPop(), stateLightboxTags(), stateSimilar(), {
        lightboxOpen: true,
        showFavoriteActresses: false,
        currentLightboxActress: null,
        lightboxIndex: 0,
        actressLightboxIndex: 0,
        // _lbTouchEnd / handleKeydown 的攔截串——任一為 true 都會提早 return（假綠）
        similarModeOpen: false,
        similarModeMobileOpen: false,
        removeActressModalOpen: false,
        _pickerOpen: false,
        rescrapeOpen: false,
        deleteVideoModalOpen: false,
        sampleGalleryOpen: false,
        _pillEditor: null,
        _releaseEditor: null,
        _maskVisible: false,
        $nextTick() {},
        $refs: {},          // _resetMask() → _maskTarget() 會讀 this.$refs.lightboxCoverFull
        _fetchLiveAliases() {},
    }, overrides);
}

// 包一層計數再呼叫真實實作——保留真副作用，讓「沒被擋時真的換到下一格」也一起驗到
function withIndexSpy(c) {
    const counts = { video: 0, actress: 0 };
    const realVideo = c._setLightboxIndex;
    const realActress = c._setActressLightboxIndex;
    c._setLightboxIndex = function (...args) { counts.video++; return realVideo.apply(this, args); };
    c._setActressLightboxIndex = function (...args) { counts.actress++; return realActress.apply(this, args); };
    return counts;
}

function seed() {
    _setFilteredVideos(VIDEOS.slice());
    _setFilteredActresses(ACTRESSES.slice());
}
function cleanup() {
    _setFilteredVideos([]);
    _setFilteredActresses([]);
}

// 左滑（dX < -50）→ next
function swipeLeft(c) {
    c._lbTouchStartX = 300;
    c._lbTouchStartY = 400;
    c._lbTouchEnd({ changedTouches: [{ clientX: 100, clientY: 405 }] });
}

function keydown(c, key) {
    c.handleKeydown({
        key,
        target: { tagName: 'DIV' },
        ctrlKey: false, altKey: false, shiftKey: false, metaKey: false,
        preventDefault() {}, stopPropagation() {},
    });
}

// ---- 影片模式 ----

test('影片模式：對焦編輯開著時左滑不換片', () => {
    seed();
    try {
        const c = makeComponent({ _maskVisible: true });
        const n = withIndexSpy(c);
        swipeLeft(c);
        assert.equal(n.video, 0, '_setLightboxIndex 不該被呼叫');
        assert.equal(c.lightboxIndex, 0, 'lightboxIndex 不該動');
    } finally { cleanup(); }
});

test('影片模式：對焦編輯沒開時左滑照樣換片（守衛沒有擋錯人）', () => {
    seed();
    try {
        const c = makeComponent({ _maskVisible: false });
        const n = withIndexSpy(c);
        swipeLeft(c);
        assert.equal(n.video, 1);
        assert.equal(c.lightboxIndex, 1);
    } finally { cleanup(); }
});

test('影片模式：對焦編輯開著時 ← / → 不換片', () => {
    seed();
    try {
        const cNext = makeComponent({ _maskVisible: true });
        const nNext = withIndexSpy(cNext);
        keydown(cNext, 'ArrowRight');
        assert.equal(nNext.video, 0);
        assert.equal(cNext.lightboxIndex, 0);

        const cPrev = makeComponent({ _maskVisible: true, lightboxIndex: 1 });
        const nPrev = withIndexSpy(cPrev);
        keydown(cPrev, 'ArrowLeft');
        assert.equal(nPrev.video, 0);
        assert.equal(cPrev.lightboxIndex, 1);
    } finally { cleanup(); }
});


// ---- 女優模式（另一份獨立的碼，不能只驗影片）----

test('女優模式：對焦編輯開著時左滑不換人', () => {
    seed();
    try {
        const c = makeComponent({
            _maskVisible: true,
            showFavoriteActresses: true,
            currentLightboxActress: ACTRESSES[0],
        });
        const n = withIndexSpy(c);
        swipeLeft(c);
        assert.equal(n.actress, 0, '_setActressLightboxIndex 不該被呼叫');
        assert.equal(c.actressLightboxIndex, 0);
    } finally { cleanup(); }
});


test('女優模式：對焦編輯開著時 ← / → 不換人', () => {
    seed();
    try {
        const cNext = makeComponent({
            _maskVisible: true,
            showFavoriteActresses: true,
            currentLightboxActress: ACTRESSES[0],
        });
        const nNext = withIndexSpy(cNext);
        keydown(cNext, 'ArrowRight');
        assert.equal(nNext.actress, 0);
        assert.equal(cNext.actressLightboxIndex, 0);

        const cPrev = makeComponent({
            _maskVisible: true,
            showFavoriteActresses: true,
            currentLightboxActress: ACTRESSES[1],
            actressLightboxIndex: 1,
        });
        const nPrev = withIndexSpy(cPrev);
        keydown(cPrev, 'ArrowLeft');
        assert.equal(nPrev.actress, 0);
        assert.equal(cPrev.actressLightboxIndex, 1);
    } finally { cleanup(); }
});

test('test_esc_cancels_focal_edit_before_closing_lightbox', () => {
    seed();
    try {
        for (const actress of [false, true]) {
            const c = makeComponent({ _maskVisible: true, showFavoriteActresses: actress, currentLightboxActress: actress ? ACTRESSES[0] : null });
            let closes = 0;
            // 真正的關閉流程需要 GSAP 與 DOM；此處只觀察是否關燈箱。
            c.closeLightbox = () => { closes++; c.lightboxOpen = false; };
            keydown(c, 'Escape');
            assert.equal(c.lightboxOpen, true);
            assert.equal(c._maskVisible, false);
            assert.equal(closes, 0);
            keydown(c, 'Escape');
            assert.equal(c.lightboxOpen, false);
            assert.equal(closes, 1);
        }
    } finally { cleanup(); }
});

test('test_focal_edit_blocks_overlay_version_tag_similar_and_switch_entries', () => {
    seed();
    try {
        const a = { path: 'a', number: 'A' };
        const b = { path: 'b', number: 'B' };
        a._versions = [a, b];
        const cases = [
            { call: c => c.switchLightboxVersion('b'), value: c => c.currentLightboxVideo, before: a, after: b },
            { call: c => c.lbxPopOpen('info'), value: c => !!c.lbxPop, before: false, after: true },
            { call: c => c.showAddLbTagInput(), value: c => c.addingLbTag, before: false, after: true },
            { call: c => c.openSimilarMode().catch(() => {}), value: c => c.similarModeAnimating, before: false, after: true },
            { call: c => c.openLightbox(1), value: (_c, n) => n.video, before: 0, after: 1 },
            { actress: true, call: c => c.openActressLightbox(1), value: (_c, n) => n.actress, before: 0, after: 1 },
            { call: c => { c._matchedActress = ACTRESSES[0]; c._refreshActressPhotoLoaded = () => {}; c.openHeroCardLightbox(); },
                value: c => JSON.stringify([c.currentLightboxVideo?.number ?? null, c.currentLightboxActress?.name ?? null, c._maskVisible]),
                before: JSON.stringify(['A', null, true]), after: JSON.stringify([null, 'A', false]) },
        ];
        for (const row of cases) {
            for (const visible of [true, false]) {
                const c = makeComponent({ _maskVisible: visible, currentLightboxVideo: a, addingLbTag: false,
                    showFavoriteActresses: !!row.actress, currentLightboxActress: row.actress ? ACTRESSES[0] : null,
                    _fetchSimilarResults: () => new Promise(() => {}) });
                const n = withIndexSpy(c);
                row.call(c);
                assert.equal(row.value(c, n), visible ? row.before : row.after);
            }
        }
    } finally { cleanup(); }
});

