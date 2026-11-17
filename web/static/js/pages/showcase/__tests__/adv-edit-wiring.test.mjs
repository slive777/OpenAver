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

let savedFetch;
function seed() {
    savedFetch = globalThis.fetch;
    globalThis.fetch = () => new Promise(() => {});
    _setFilteredVideos(VIDEOS.slice());
    _setFilteredActresses(ACTRESSES.slice());
}
function cleanup() {
    globalThis.fetch = savedFetch;
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


test('test_adv_edit_late_responses_do_not_write', async () => {
    seed();
    try {
        for (const kind of ['files', 'regen', 'reread']) {
            let resolve;
            globalThis.fetch = () => new Promise(r => { resolve = r; });
            let toast = 0, refresh = 0;
            const c = makeComponent({ currentLightboxVideo: VIDEOS[0], showToast: () => toast++, refreshVideoData: () => refresh++ });
            c.advEditOpen = true;
            c.advEditInfo = { state: 'ok', poster: { visible: true, can_regen: true } };
            const pending = kind === 'files' ? c.loadAdvEditInfo() : kind === 'regen' ? c.regenAdvEditPoster() : c.rereadAdvEditMedia();
            c.closeAdvEdit();
            c.advEditInfo = { marker: 'new' };
            if (resolve) resolve({ ok: true, json: async () => ({ success: true, state: 'ok', poster: { status: 'updated' }, status: 'ok' }) });
            await pending;
            assert.deepEqual(c.advEditInfo, { marker: 'new' });
            assert.equal(toast, 0); assert.equal(refresh, 0);
            assert.ok(resolve, kind + ' must start a request');
        }
    } finally { cleanup(); }
});

const { stateVideos } = await import('../state-videos.js');
const { _setAllVideos, _setVideos, _filteredVideos } = await import('../state-base.js');

function wallFixture(rows) {
    return {
        page: 1, similarExitVideo: null,
        fetchVideos: async () => { _setAllVideos(rows); _setVideos(rows); _setFilteredVideos(rows); },
        applyFilterAndSort() {}, updatePagination() {},
        _refreshLbFullBlurUp() {}, _refreshLbActorAges() {},
        closeLightbox() { this.lightboxOpen = false; this.closed++; },
        closed: 0,
    };
}
function clearWall() { _setAllVideos([]); _setVideos([]); _setFilteredVideos([]); }
function response(data) { return { ok: true, json: async () => data }; }

test('test_adv_edit_error_hints_and_name_change_gate', async () => {
    seed(); const previous = globalThis.fetch;
    try {
        const c = makeComponent({ currentLightboxVideo: VIDEOS[0], advEditOpen: true, advEditInfo: { readonly: false } });
        const calls = []; let result;
        globalThis.fetch = async (url, opts) => { calls.push(JSON.parse(opts.body)); return result === null ? { json: async () => { throw Error('bad json'); } } : response(result); };
        for (const code of ['readonly', 'unchanged', 'not_video', 'not_found', 'out_of_library', 'already_in_library', 'not_scannable', 'confirm_required', 'unknown', null]) {
            c._advEditCell = 'path'; c.advEditPathDraft = 'file:///C:/a.mkv'; c.advEditPathConfirm = false; result = code === null ? null : { success: false, error: code };
            await c.submitAdvEditPath();
            assert.equal(c.advEditPathConfirm, code === 'confirm_required', String(code));
            if (code !== 'confirm_required') assert.equal(c.advEditPathError, 'showcase.adv_edit.path.err_' + (['unknown', null].includes(code) ? 'generic' : code), String(code));
            assert.equal(c._advEditCell, 'path');
        }
        calls.length = 0; result = { success: false, error: 'unchanged' };
        c.advEditPathDraft = 'file:///C:/a.mkv'; await c.submitAdvEditPath();
        assert.equal(calls.length, 1); assert.equal(calls[0].confirm_name_change, false);
        c.advEditPathDraft = '"file:///C:/a.mkv"'; await c.submitAdvEditPath();
        assert.equal(calls.length, 2); assert.equal(calls[1].new_path, 'file:///C:/a.mkv');
        c.advEditPathDraft = 'file:///C:/other.mkv'; await c.submitAdvEditPath();
        assert.equal(calls.length, 2); assert.equal(c.advEditPathConfirm, true);
        c.cancelAdvEditCell(); assert.equal(c._advEditCell, '');
        c._advEditCell = 'path'; c.advEditPathDraft = 'file:///C:/other.mkv'; await c.submitAdvEditPath(true);
        assert.equal(calls.length, 3); assert.equal(calls[2].confirm_name_change, true);
        const toasts = []; c.showToast = (text, type) => toasts.push({ text, type }); c.loadAdvEditInfo = async () => {}; c.refreshVideoData = async () => {};
        for (const code of ['unreachable', 'not_found', 'no_nfo', 'nfo_ambiguous', 'nfo_unreadable', 'unknown', null]) {
            result = code === null ? null : { success: false, error: code }; await c.runAdvEditUpdate();
            assert.equal(toasts.at(-1).text, 'showcase.adv_edit.update.err_' + (['unknown', null].includes(code) ? 'generic' : code));
        }
        result = { success: true, media_status: 'unreadable' }; await c.runAdvEditUpdate();
        assert.equal(toasts.at(-1).text, 'showcase.adv_edit.update.done_media_pending');
    } finally { globalThis.fetch = previous; clearWall(); cleanup(); }
});

test('test_adv_edit_repath_success_reanchors_lightbox_and_keeps_wall', async () => {
    seed(); const previous = globalThis.fetch;
    try {
        for (const renamed of [false, true]) {
            const old = { path: 'file:///C:/a.mp4', number: 'AAA-001' }, next = { path: renamed ? 'file:///C:/b.mkv' : 'file:///C:/a.mkv', number: 'AAA-001' };
            const toasts = []; let loads = 0;
            const c = makeComponent({ ...wallFixture([next]), currentLightboxVideo: old, advEditOpen: true, advEditInfo: { readonly: false }, showToast: text => toasts.push(text), loadAdvEditInfo: async () => { loads++; } }, [stateVideos()]);
            globalThis.fetch = async () => response({ success: true, path: next.path, name_changed: renamed });
            c._advEditCell = 'path'; c.advEditPathDraft = next.path; await c.submitAdvEditPath(renamed);
            assert.equal(c.lightboxOpen, true); assert.equal(c.closed, 0); assert.equal(c.currentLightboxVideo.path, next.path);
            assert.equal(_filteredVideos.length, 1); assert.equal(loads, 1); assert.equal(c._advEditCell, '');
            assert.equal(toasts[0], renamed ? 'showcase.adv_edit.path.done_renamed' : 'showcase.adv_edit.path.done');
            c.currentLightboxVideo = old; c.lightboxOpen = true; c.fetchVideos = wallFixture([]).fetchVideos;
            await c._reloadWallKeepLightbox(old.path, { reanchorTo: next.path }); assert.equal(c.lightboxOpen, false);
        }
    } finally { globalThis.fetch = previous; clearWall(); cleanup(); }
});

test('test_reload_wall_without_reanchor_keeps_old_semantics', async () => {
    seed();
    try {
        for (const opts of [undefined, { bustPaths: [], t: 1 }]) for (const present of [true, false]) {
            const old = { path: 'file:///C:/a.mp4', number: 'AAA-001' };
            const c = makeComponent({ ...wallFixture(present ? [old] : []), currentLightboxVideo: old }, [stateVideos()]);
            await c._reloadWallKeepLightbox(old.path, opts);
            assert.equal(c.lightboxOpen, present); assert.equal(c.closed, present ? 0 : 1);
            if (present) assert.equal(c.currentLightboxVideo.path, old.path);
        }
        // The same entry point also has to support a new path after a move.
        const old = { path: 'old' }, next = { path: 'new' };
        const c = makeComponent({ ...wallFixture([next]), currentLightboxVideo: old }, [stateVideos()]);
        await c._reloadWallKeepLightbox('old', { reanchorTo: 'new' }); assert.equal(c.currentLightboxVideo.path, 'new');
    } finally { clearWall(); cleanup(); }
});

test('test_adv_edit_busy_lock_and_late_responses_dropped', async () => {
    seed(); const previous = globalThis.fetch; const pendingResolves = [];
    try {
        for (const kind of ['update', 'failure', 'success']) {
            let resolve; let calls = 0, loads = 0, refreshes = 0, reloads = 0; const toasts = [];
            globalThis.fetch = () => { calls++; return new Promise(r => { resolve = r; pendingResolves.push(r); }); };
            const c = makeComponent({ currentLightboxVideo: VIDEOS[0], advEditOpen: true, advEditInfo: { readonly: false }, showToast: (...x) => toasts.push(x), loadAdvEditInfo: async () => { loads++; }, refreshVideoData: async () => { refreshes++; }, _reloadWallKeepLightbox: async () => { reloads++; } });
            c._advEditCell = 'path'; c.advEditPathDraft = 'file:///C:/a.mkv';
            const p = kind === 'update' ? c.runAdvEditUpdate() : c.submitAdvEditPath();
            assert.equal(calls, 1); c.startAdvEditPath(); await c.submitAdvEditPath(); await c.runAdvEditUpdate(); assert.equal(calls, 1);
            c.closeAdvEdit(); c.advEditOpen = true; c._advEditBusy = 'update'; c.advEditPathError = '';
            resolve(response(kind === 'success' ? { success: true, path: 'new' } : kind === 'failure' ? { success: false, error: 'not_found' } : { success: true }));
            await p; assert.equal(toasts.length, 0); assert.equal(loads, 0); assert.equal(refreshes, 0); assert.equal(c.advEditPathError, ''); assert.equal(c._advEditBusy, 'update');
            assert.equal(reloads, kind === 'success' ? 1 : 0);
        }
    } finally { for (const resolve of pendingResolves) resolve(response({ success: false })); globalThis.fetch = previous; clearWall(); cleanup(); }
});

test('test_adv_edit_thumb_regen_button_and_notices', async () => {
    const { advEditFilesView, advEditThumbNotice } = await import('../lbx-logic.js');
    for (const [info, expected] of [[null, false], [{cover: {exists: true}, thumb: {mode: 'cache'}}, true], [{cover: {exists: false}, thumb: {mode: 'cache'}}, false], [{cover: {exists: true}, thumb: {mode: 'cover'}}, false]]) {
        assert.equal(advEditFilesView(info).canRegenThumb, expected);
    }
    for (const [data, key, type, reload] of [
        [{success: true, cover_changed: false}, 'thumb_regen_done', 'success', true],
        [{success: true, cover_changed: true}, 'thumb_regen_done_cover', 'success', true],
        [{success: false, error: 'no_cover'}, 'thumb_no_cover', 'warning', false],
        [{success: false, error: 'unreachable'}, 'unreachable', 'warning', false],
        ...['failed', 'skipped', 'unknown'].map(error => [{success: false, error}, 'thumb_failed', 'error', false]),
        [null, 'thumb_failed', 'error', false],
    ]) assert.deepEqual(advEditThumbNotice(data, window.t), {text: 'showcase.adv_edit.files.' + key, type, reload});
});

test('test_adv_edit_thumb_regen_late_and_busy', async () => {
    seed(); const previous = globalThis.fetch;
    try {
        let resolve, requests = 0, toast = 0, refresh = 0, loads = 0;
        globalThis.fetch = () => { requests++; return new Promise(r => { resolve = r; }); };
        const c = makeComponent({currentLightboxVideo: VIDEOS[0], advEditOpen: true, advEditInfo: {cover: {exists: true}, thumb: {mode: 'cache'}}, showToast: () => toast++, refreshVideoData: async () => refresh++, loadAdvEditInfo: async () => loads++});
        const pending = c.regenAdvEditThumb();
        await c.regenAdvEditThumb();
        assert.equal(requests, 1);
        c.closeAdvEdit();
        resolve(response({success: true}));
        await pending;
        assert.equal(toast, 0); assert.equal(refresh, 0); assert.equal(loads, 0);
        c.advEditOpen = true;
        c.advEditInfo = {cover: {exists: true}, thumb: {mode: 'cache'}};
        globalThis.fetch = async () => ({ok: false, json: async () => ({success: false, error: 'no_cover'})});
        await c.regenAdvEditThumb();
        assert.equal(toast, 1); assert.equal(refresh, 0); assert.equal(loads, 1);
        globalThis.fetch = async () => response({success: true});
        await c.regenAdvEditThumb();
        assert.equal(toast, 2); assert.equal(refresh, 1); assert.equal(loads, 2);
    } finally { globalThis.fetch = previous; cleanup(); }
});
