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
    addEventListener() {},
    querySelector() { return null; },
    body: { classList: { add() {}, remove() {}, contains() { return false; } } },
};

register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

const { placePop, isOutsidePop, ghostOnClose } = await import('../lbx-logic.js');
await import('../animations.js');
const { stateLightbox } = await import('../state-lightbox.js');
const { stateLightboxPicker } = await import('../state-lightbox-picker.js');
const { stateLightboxMask } = await import('../state-lightbox-mask.js');
const { stateLightboxPop } = await import('../state-lightbox-pop.js');
const { stateLightboxTags } = await import('../state-lightbox-tags.js');
const { mergeState } = await import('@/shared/merge-state.js');
const { _setFilteredVideos } = await import('../state-base.js');

test('test_ghost_on_close_table', () => {
    for (const placed of [false, true]) for (const immediate of [false, true]) for (const prefersReducedMotion of [false, true]) {
        assert.equal(ghostOnClose({ placed, immediate, prefersReducedMotion }), placed && !immediate && !prefersReducedMotion);
    }
});

test('test_create_ghost_under_reduced_motion_adds_nothing', () => {
    window.OpenAver = { prefersReducedMotion: true, motion: { stripAlpine() {}, DURATION: { fast: 0.1, emphasis: 0.5 } } };
    globalThis.gsap = { fromTo() { return { kill() {} }; } };
    const parent = { children: [], appendChild(node) { this.children.push(node); } };
    const src = { cloneNode() { return { style: {}, setAttribute() {}, removeAttribute() {} }; } };
    const handle = window.ShowcaseAnimations.createGhost(src, { parent, kind: 'pop' });
    assert.equal(typeof handle.release, 'function');
    assert.equal(typeof handle.kill, 'function');
    assert.equal(parent.children.length, 0);
    assert.equal(window.ShowcaseAnimations.ghostCount(), 0);
});

test('test_open_second_pop_clears_old_ghost', () => {
    window.OpenAver = { prefersReducedMotion: false, motion: { stripAlpine() {}, DURATION: { fast: 0.1, emphasis: 0.5 } } };
    globalThis.gsap = { fromTo() { return { kill() {} }; } };
    const parent = { children: [], appendChild(node) { this.children.push(node); node.parent = this; } };
    const src = { cloneNode() { return { style: {}, setAttribute() {}, removeAttribute() {}, remove() { this.parent.children.splice(this.parent.children.indexOf(this), 1); } }; } };
    window.ShowcaseAnimations.createGhost(src, { parent, kind: 'pop' });
    assert.equal(window.ShowcaseAnimations.ghostCount('pop'), 1);
    stateLightboxPop().lbxPopOpen('title', {});
    assert.equal(window.ShowcaseAnimations.ghostCount('pop'), 0);
    assert.equal(parent.children.length, 0);
});

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

test('test_place_pop_right_table', () => {
    const vw = 1920;
    const vh = 1080;
    const coverBottom = 810;
    const floor = coverBottom + 4;
    const A = { left: 100, right: 140, top: 840, bottom: 880 };
    const base = { coverBottom, vw, vh, mode: 'right', shrinkMax: 80 };

    // 格 1 放得下：上緣對齊頭像、不縮、不限高
    const fit = placePop({ ...base, anchorRect: A, popSize: { w: 300, h: 200 } });
    assert.equal(fit.left, 146);
    assert.equal(fit.top, 840);
    assert.equal(fit.shrink, 0);
    assert.equal(fit.maxHeight, undefined);

    // 格 2 往上挪：仍在封面下緣之下、頭像上緣之上
    const shift = placePop({ ...base, anchorRect: A, popSize: { w: 300, h: 240 } });
    assert.equal(shift.top, 832);
    assert.ok(shift.top >= floor && shift.top < A.top);
    assert.equal(shift.shrink, 0);
    assert.equal(shift.maxHeight, undefined);

    // 格 3 挪到 floor 仍不夠→縮
    const shrunk = placePop({ ...base, anchorRect: A, popSize: { w: 300, h: 266 } });
    assert.equal(shrunk.top, floor);
    assert.equal(shrunk.shrink, 8);
    assert.equal(shrunk.maxHeight, undefined);

    // 格 4 極矮視窗縮到下限：shrink 不超過 shrinkMax，剩餘溢出回 maxHeight
    const tiny = placePop({
        ...base, vh: 700, coverBottom: 520,
        anchorRect: { left: 100, right: 140, top: 560, bottom: 600 },
        popSize: { w: 300, h: 266 },
    });
    assert.equal(tiny.top, 524);
    assert.equal(tiny.shrink, 80);
    assert.equal(tiny.maxHeight, 168);

    // 格 5 右緣夾邊；窄到放不下時左緣貼 margin
    const edge = placePop({
        ...base, anchorRect: { left: 1860, right: 1900, top: 840, bottom: 880 },
        popSize: { w: 300, h: 200 },
    });
    assert.equal(edge.left, 1612);
    const narrow = placePop({ ...base, anchorRect: A, popSize: { w: 2000, h: 200 } });
    assert.equal(narrow.left, 8);

    // 格 6 無照片：shrinkMax 傳 0 與省略各一次，皆不縮、溢出回 maxHeight
    const noPhotoZero = placePop({ ...base, shrinkMax: 0, anchorRect: A, popSize: { w: 300, h: 266 } });
    assert.equal(noPhotoZero.top, floor);
    assert.equal(noPhotoZero.shrink, 0);
    assert.equal(noPhotoZero.maxHeight, 258);
    const noPhotoOmit = placePop({ coverBottom, vw, vh, mode: 'right', anchorRect: A, popSize: { w: 300, h: 266 } });
    assert.equal(noPhotoOmit.top, floor);
    assert.equal(noPhotoOmit.shrink, 0);
    assert.equal(noPhotoOmit.maxHeight, 258);

    // 格 7 錨點在 floor 之上：上緣夾在封面下緣，不蓋封面
    const above = placePop({
        ...base, anchorRect: { left: 100, right: 140, top: 790, bottom: 830 },
        popSize: { w: 300, h: 200 },
    });
    assert.equal(above.top, floor);
    assert.equal(above.shrink, 0);

    // 其他 mode 形狀不變：below 回傳鍵集仍只有 left／top／maxHeight（無 shrink 鍵）
    assert.deepEqual(
        placePop({ anchorRect: { left: 100, top: 840, bottom: 870 }, coverBottom: 810, vw: 1920, vh: 1080, popSize: { w: 300, h: 80 }, mode: 'below' }),
        { left: 100, top: 876, maxHeight: undefined },
    );
});

test('test_pop_placement_table', async () => {
    const { popPlacement } = await import('../lbx-logic.js');
    const cases = [
        ['title', 'inplace', 'left'],
        ['otitle', 'inplace', 'left'],
        ['actorCard', 'right', 'left'],
        ['menu', 'below', 'right'],
        ['info', 'below', 'right'],
        ['actresses', 'below', 'left'],
        ['plot', 'below', 'left'],
        ['verTip', 'below', 'left'],
        ['__unknown__', 'below', 'left'],
    ];
    for (const [kind, mode, align] of cases) {
        assert.deepEqual(popPlacement(kind), { mode, align });
    }
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
        c.lbxPopOpen('info', {}, { mode: 'click' });
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

test('test_actor_card_shrink_two_pass_and_stale_settle_noop', () => {
    const prevW = globalThis.innerWidth;
    const prevH = globalThis.innerHeight;
    globalThis.innerWidth = 1920;
    globalThis.innerHeight = 1080;
    try {
        const calls = [];
        const photo = { offsetHeight: 200 };
        const panel = {
            offsetWidth: 300, offsetHeight: 266,
            style: { removeProperty(name) { calls.push(name); } },
            querySelector: (sel) => (sel === '.lbx-actor-card__photo' ? photo : null),
        };
        const content = { querySelector: () => ({ getBoundingClientRect: () => ({ bottom: 810 }) }) };
        const anchor = { getBoundingClientRect: () => ({ left: 100, right: 140, top: 840, bottom: 880 }), closest: () => content };
        const c = popComponent();
        c.$refs = { lbxPopHost: { querySelector: () => panel } };
        let scheduled = 0;
        c.$nextTick = () => { scheduled++; };

        c.lbxPopOpen('actorCard', anchor, { mode: 'hover', anchorKey: 'a' });
        assert.equal(scheduled, 1);
        const gen = c._lbxPopGen;
        c._lbxPopPlace(gen);
        assert.equal(c.lbxPop.style['--lbx-card-photo-h'], '192px');
        assert.equal(c.lbxPop.placed, false);
        assert.ok(parseFloat(c.lbxPop.style.left) > 140);
        assert.ok(calls.includes('--lbx-card-photo-h'));
        assert.equal(scheduled, 2);

        panel.offsetHeight = 258;
        c._lbxPopPlace(gen, true);
        assert.equal(c.lbxPop.placed, true);
        assert.equal(c.lbxPop.style['--lbx-card-photo-h'], '192px');
        assert.equal(c.lbxPop.style.top, '814px');
        assert.equal(c.lbxPop.style.maxHeight, undefined);
        assert.equal(scheduled, 2);

        panel.offsetHeight = 200;
        panel.querySelector = () => null;
        scheduled = 0;
        c.lbxPopOpen('actorCard', anchor, { mode: 'hover', anchorKey: 'a' });
        assert.equal(scheduled, 1);
        c._lbxPopPlace(c._lbxPopGen);
        assert.equal(c.lbxPop.placed, true);
        assert.equal('--lbx-card-photo-h' in c.lbxPop.style, false);
        assert.equal(c.lbxPop.style.top, '840px');
        assert.equal(scheduled, 1);

        panel.offsetHeight = 266;
        panel.querySelector = (sel) => (sel === '.lbx-actor-card__photo' ? photo : null);
        c.lbxPopOpen('actorCard', anchor, { mode: 'hover', anchorKey: 'a' });
        const staleGen = c._lbxPopGen;
        c._lbxPopPlace(staleGen);
        assert.equal(c.lbxPop.placed, false);
        c.lbxPopClose();
        c._lbxPopPlace(staleGen, true);
        assert.equal(c.lbxPop, null);
    } finally {
        globalThis.innerWidth = prevW;
        globalThis.innerHeight = prevH;
    }
});

test('test_ghost_preserves_scroll_after_append', () => {
    window.OpenAver = { prefersReducedMotion: false, motion: { stripAlpine() {}, DURATION: { fast: 0.1, emphasis: 0.5 } } };
    globalThis.gsap = { fromTo() { return { kill() {} }; } };
    let clone;
    const parent = { appendChild(node) { node.attached = true; } };
    const src = { scrollTop: 37, cloneNode() {
        let scroll = 0;
        clone = { style: {}, setAttribute() {}, removeAttribute() {}, remove() {},
            get scrollTop() { return scroll; },
            set scrollTop(value) { if (this.attached) scroll = value; },
        };
        return clone;
    } };
    const handle = window.ShowcaseAnimations.createGhost(src, { parent, kind: 'pop' });
    try { assert.equal(clone.scrollTop, 37); } finally { handle.kill(); }
});
