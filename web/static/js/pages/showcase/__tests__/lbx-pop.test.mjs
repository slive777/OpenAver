// TASK-199a-T3: lbxPop base (placement pure function, Esc closes the pop before the lightbox, outside-click test).
// Timing-class behaviour (hover timer, generation guard, resize / switch-video collapse) is covered by CDP end-state checks, not here.

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

const { placePop, isOutsidePop } = await import('../lbx-logic.js');
const { stateLightbox } = await import('../state-lightbox.js');
const { stateLightboxPicker } = await import('../state-lightbox-picker.js');
const { stateLightboxMask } = await import('../state-lightbox-mask.js');
const { stateLightboxPop } = await import('../state-lightbox-pop.js');
const { stateLightboxTags } = await import('../state-lightbox-tags.js');
const { mergeState } = await import('@/shared/merge-state.js');
const { _setFilteredVideos } = await import('../state-base.js');

test('test_place_pop_never_covers_cover_or_leaves_viewport', () => {
    const vw = 1920;
    const vh = 1080;
    const margin = 8;
    const gap = 6;
    const coverBottom = 810;
    const popSize = { w: 300, h: 80 };
    const base = { coverBottom, vw, vh, popSize, mode: 'below', interactive: false };

    // (a) anchor inside the cover: pop sits below the cover bottom, never covers it
    const inCover = placePop({ ...base, anchorRect: { left: 100, top: 760, bottom: 790 } });
    assert.equal(inCover.top, coverBottom + 4);

    // (b) anchor below the cover with room to spare: anchor bottom + gap, no max height
    const below = placePop({ ...base, anchorRect: { left: 100, top: 840, bottom: 870 } });
    assert.equal(below.top, 870 + gap);
    assert.equal(below.maxHeight, undefined);

    // (c) interactive pop without room: never above the cover floor; max height reaches the viewport bottom
    const tall = { w: 300, h: 400 };
    const click = placePop({ ...base, popSize: tall, interactive: true, anchorRect: { left: 100, top: 840, bottom: 870 } });
    assert.ok(click.top >= coverBottom + 4);
    assert.equal(click.maxHeight, vh - margin - click.top);

    // (c2) interactive pop WITH room still gets a max height (content may grow after open): reaches the viewport bottom
    const clickRoom = placePop({ ...base, interactive: true, anchorRect: { left: 100, top: 840, bottom: 870 } });
    assert.equal(clickRoom.maxHeight, vh - margin - clickRoom.top);

    // (d) read-only pop without room: no max height (no inner scroll)
    const read = placePop({ ...base, popSize: tall, interactive: false, anchorRect: { left: 100, top: 840, bottom: 870 } });
    assert.equal(read.maxHeight, undefined);

    // horizontal: clamped into [margin, vw - popW - margin]
    const leftEdge = placePop({ ...base, anchorRect: { left: -50, top: 840, bottom: 870 } });
    assert.equal(leftEdge.left, margin);
    const rightEdge = placePop({ ...base, anchorRect: { left: 1900, top: 840, bottom: 870 } });
    assert.equal(rightEdge.left, vw - popSize.w - margin);
});

test('test_is_outside_pop_anchor_click_is_not_outside', () => {
    const inner = { closest: (sel) => (sel === '[data-lbx-anchor]' ? {} : null) };
    const stranger = { closest: () => null };
    const insidePanel = { closest: () => null };
    const panel = { contains: (t) => t === insidePanel };

    assert.equal(isOutsidePop(inner, panel, '[data-lbx-anchor]'), false);
    assert.equal(isOutsidePop(insidePanel, panel, '[data-lbx-anchor]'), false);
    assert.equal(isOutsidePop(stranger, panel, '[data-lbx-anchor]'), true);
});

function escEvent() {
    return {
        key: 'Escape',
        target: { tagName: 'DIV' },
        ctrlKey: false, altKey: false, shiftKey: false, metaKey: false,
        preventDefault() { this.prevented = true; }, stopPropagation() {},
    };
}

test('test_esc_closes_pop_before_lightbox', () => {
    _setFilteredVideos([{ path: 'file:///C:/a.mp4', number: 'AAA-001', title: 'x', actresses: '' }]);
    try {
        const c = mergeState(stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateLightboxPop(), {
            lightboxOpen: true,
            showFavoriteActresses: false,
            currentLightboxActress: null,
            lightboxIndex: 0,
            actressLightboxIndex: 0,
            similarModeOpen: false,
            similarModeMobileOpen: false,
            removeActressModalOpen: false,
            actressAddPanelOpen: false,
            _pickerOpen: false,
            rescrapeOpen: false,
            deleteVideoModalOpen: false,
            sampleGalleryOpen: false,
            _pillEditor: null,
            _releaseEditor: null,
            _maskVisible: false,
            $nextTick() {},
            $refs: {},
        });
        let closeCount = 0;
        c.closeLightbox = () => { closeCount++; };

        c.lbxPopOpen('verTip', {}, { mode: 'hover' });
        assert.ok(c.lbxPop, 'pop opened');

        const first = escEvent();
        c.handleKeydown(first);
        assert.equal(c.lbxPop, null);
        assert.equal(closeCount, 0, 'first Esc only closes the pop');
        assert.equal(first.prevented, true);

        c.handleKeydown(escEvent());
        assert.equal(closeCount, 1, 'second Esc closes the lightbox');
    } finally {
        _setFilteredVideos([]);
    }
});

test('test_esc_cancels_tag_input_before_closing_lightbox', () => {
    _setFilteredVideos([{ path: 'file:///C:/a.mp4', number: 'AAA-001', title: 'x', actresses: '' }]);
    try {
        const c = mergeState(stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateLightboxPop(), stateLightboxTags(), {
            lightboxOpen: true,
            showFavoriteActresses: false,
            currentLightboxActress: null,
            lightboxIndex: 0,
            actressLightboxIndex: 0,
            similarModeOpen: false,
            similarModeMobileOpen: false,
            removeActressModalOpen: false,
            actressAddPanelOpen: false,
            _pickerOpen: false,
            rescrapeOpen: false,
            deleteVideoModalOpen: false,
            sampleGalleryOpen: false,
            _pillEditor: null,
            _releaseEditor: null,
            _maskVisible: false,
            $nextTick() {},
            $refs: {},
        });
        let closeCount = 0;
        c.closeLightbox = () => { closeCount++; };

        c.addingLbTag = true;
        c.lbxPopOpen('moreTags', {}, { mode: 'click' });
        assert.ok(c.lbxPop, 'pop opened');

        // 1st Esc: only the pop closes; the tag input stays open
        const first = escEvent();
        c.handleKeydown(first);
        assert.equal(c.lbxPop, null);
        assert.equal(c.addingLbTag, true);
        assert.equal(closeCount, 0);

        // 2nd Esc: cancels the tag input; lightbox stays open
        const second = escEvent();
        c.handleKeydown(second);
        assert.equal(c.addingLbTag, false);
        assert.equal(closeCount, 0, 'second Esc only cancels the input');
        assert.equal(second.prevented, true);

        // 3rd Esc: now the lightbox closes
        c.handleKeydown(escEvent());
        assert.equal(closeCount, 1, 'third Esc closes the lightbox');
    } finally {
        _setFilteredVideos([]);
    }
});

// pre-merge fix 1: title pop starts at the title TEXT's left edge (the star in front of it stays visible)
function popComponent() {
    return mergeState(stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateLightboxPop(), {
        lightboxOpen: true,
        showFavoriteActresses: false,
        currentLightboxActress: null,
        lightboxIndex: 0,
        actressLightboxIndex: 0,
        similarModeOpen: false,
        similarModeMobileOpen: false,
        removeActressModalOpen: false,
        actressAddPanelOpen: false,
        _pickerOpen: false,
        rescrapeOpen: false,
        deleteVideoModalOpen: false,
        sampleGalleryOpen: false,
        _pillEditor: null,
        _releaseEditor: null,
        _maskVisible: false,
        $nextTick() {},
        $refs: { lbxPopHost: { querySelector: () => ({ offsetWidth: 300, offsetHeight: 60, contains: () => false }) } },
    });
}

test('test_title_pop_left_edge_starts_at_title_text_not_star', () => {
    const prevW = globalThis.innerWidth;
    const prevH = globalThis.innerHeight;
    globalThis.innerWidth = 1920;
    globalThis.innerHeight = 1080;
    try {
        const rect = (left) => ({ left, right: left + 400, top: 700, bottom: 730 });
        const content = { querySelector: () => ({ getBoundingClientRect: () => ({ bottom: 600 }) }) };
        const mkAnchor = (textLeft) => ({
            getBoundingClientRect: () => rect(377.5),
            closest: () => content,
            querySelector: (sel) => (sel === ':scope > span' ? { getBoundingClientRect: () => rect(textLeft) } : null),
        });

        const c = popComponent();
        c.lbxPopOpen('title', mkAnchor(401.5), { mode: 'hover', anchorKey: 'title' });
        c._lbxPopPlace(c._lbxPopGen);
        assert.equal(c.lbxPop.placed, true);
        assert.equal(c.lbxPop.style.left, '401.5px', 'title pop left = title text left, not the star-including anchor left');

        // other kinds keep the whole anchor rect
        c.lbxPopOpen('otitle', mkAnchor(401.5), { mode: 'hover', anchorKey: 'otitle' });
        c._lbxPopPlace(c._lbxPopGen);
        assert.equal(c.lbxPop.style.left, '377.5px');
    } finally {
        globalThis.innerWidth = prevW;
        globalThis.innerHeight = prevH;
    }
});

// pre-merge fix 2: the pointerdown that closes a pop must not also close the lightbox via the backdrop click
test('test_outside_pointerdown_closing_pop_swallows_backdrop_click', () => {
    const c = popComponent();
    let closeCount = 0;
    c.closeLightbox = () => { closeCount++; };
    const outside = { closest: () => null };
    const backdropClick = () => ({
        target: { closest: () => null },
        currentTarget: { style: {} },
        clientX: 1,
        clientY: 1,
    });
    const prevDoc = globalThis.document;
    globalThis.document = { ...prevDoc, elementFromPoint: () => null };
    try {
        // pop open → outside pointerdown closes it → the click that follows must not close the lightbox
        c.lbxPopOpen('verTip', {}, { mode: 'click' });
        c.lbxPopOnPointerDown({ target: outside });
        assert.equal(c.lbxPop, null);
        c.handleLightboxBackdropClick(backdropClick());
        assert.equal(closeCount, 0, 'click that closed the pop does not close the lightbox');

        // control: no pop open → backdrop click closes the lightbox as before
        c.lbxPopOnPointerDown({ target: outside });
        c.handleLightboxBackdropClick(backdropClick());
        assert.equal(closeCount, 1, 'without an open pop the backdrop click still closes the lightbox');
    } finally {
        globalThis.document = prevDoc;
    }
});
