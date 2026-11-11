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
            lbPlotOpen: false,
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
