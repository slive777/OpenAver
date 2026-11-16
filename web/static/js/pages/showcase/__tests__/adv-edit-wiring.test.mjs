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

const { stateAdvEdit } = await import('../state-adv-edit.js');
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

function makeComponent(overrides, extraSlices = []) {
    return Object.assign({}, stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateActress(), stateLightboxVersions(), stateLightboxPop(), stateLightboxTags(), stateSimilar(), stateAdvEdit(), ...extraSlices, {
        pills: [],
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


test('test_adv_edit_esc_layers_hooks_and_lightbox_close', () => {
    seed();
    try {
        for (const cell of ['path', 'data:title']) {
            const c = makeComponent({ currentLightboxVideo: VIDEOS[0] });
            let opened = 0, closed = 0;
            c.onAdvEditOpen = () => opened++; c.onAdvEditClose = () => closed++;
            c.openAdvEdit();
            assert.equal(c.advEditOpen, true);
            c._advEditCell = cell; c.advEditPathDraft = 'draft'; c.advEditPathError = 'error';
            // The third Escape uses a spy because the real lightbox close uses GSAP.
            c.closeLightbox = () => { c.lightboxOpen = false; };
            keydown(c, 'Escape');
            assert.equal(c._advEditCell, ''); assert.equal(c.advEditPathDraft, ''); assert.equal(c.advEditPathError, '');
            assert.equal(c.advEditOpen, true); assert.equal(c.lightboxOpen, true);
            keydown(c, 'Escape');
            assert.equal(c.advEditOpen, false); assert.equal(c.lightboxOpen, true);
            assert.equal(opened, 1); assert.equal(closed, 1);
            keydown(c, 'Escape'); assert.equal(c.lightboxOpen, false);
        }
        const c = makeComponent({ currentLightboxVideo: VIDEOS[0] });
        c.openAdvEdit(); c.closeAdvEdit(); c.openAdvEdit();
        let closed = 0; c.onAdvEditClose = () => closed++;
        // Real close is needed here to verify it closes the dialog; document is stubbed above.
        c.closeLightbox();
        assert.equal(c.advEditOpen, false); assert.equal(closed, 1);
        clearTimeout(c.lightboxCloseTimer); c.closeLightbox(); clearTimeout(c.lightboxCloseTimer);
        assert.equal(closed, 1);
    } finally { cleanup(); }
});

test('test_adv_edit_open_blocks_slide_entries', () => {
    seed();
    try {
        const cases = [
            { index: 0, run: c => keydown(c, 'ArrowRight'), after: 1 },
            { index: 1, run: c => keydown(c, 'ArrowLeft'), after: 0 },
            { index: 0, run: c => c.handleWheel({ deltaX: 300, deltaY: 0, target: { closest: () => null }, preventDefault() {} }), after: 1 },
            { index: 0, run: c => swipeLeft(c), after: 1 },
        ];
        for (const row of cases) {
            for (const open of [true, false]) {
                const c = makeComponent({ advEditOpen: open, lightboxIndex: row.index, currentLightboxVideo: VIDEOS[row.index] });
                const n = withIndexSpy(c);
                row.run(c);
                assert.equal(n.video, open ? 0 : 1);
                assert.equal(c.lightboxIndex, open ? row.index : row.after);
                assert.equal(c.currentLightboxVideo, VIDEOS[open ? row.index : row.after]);
            }
        }
    } finally { cleanup(); }
});
