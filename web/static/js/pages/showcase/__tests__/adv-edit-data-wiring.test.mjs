import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.Alpine = globalThis.Alpine || { store: () => ({ toolbarOpen: false, showcaseHasSearch: false }) };
globalThis.document = globalThis.document || { querySelector() { return null; }, body: { classList: { add() {}, remove() {}, contains() { return false; } } } };
register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

const { stateAdvEditData } = await import('../state-adv-edit-data.js');
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
const { ADV_EDIT_DATA_ERROR_KEYS, errorKeyOf } = await import('../adv-edit-data-logic.js');
const { readFileSync } = await import('node:fs');
const VIDEOS = [{ path: 'file:///C:/a.mp4', number: 'AAA-001', actresses: 'A,B' }];
const ACTRESSES = [{ name: 'A' }, { name: 'B' }];
function makeComponent(overrides, extraSlices = []) {
    return Object.assign({}, stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateActress(), stateLightboxVersions(), stateLightboxPop(), stateLightboxTags(), stateSimilar(), stateAdvEdit(), ...extraSlices, {
        pills: [], lightboxOpen: true, showFavoriteActresses: false, currentLightboxActress: null,
        lightboxIndex: 0, actressLightboxIndex: 0, similarModeOpen: false, similarModeMobileOpen: false,
        removeActressModalOpen: false, _pickerOpen: false, rescrapeOpen: false, deleteVideoModalOpen: false,
        sampleGalleryOpen: false, _pillEditor: null, _releaseEditor: null, _maskVisible: false,
        $nextTick() {}, $refs: {}, _fetchLiveAliases() {},
    }, overrides);
}
let savedFetch;
function seed() { savedFetch = globalThis.fetch; _setFilteredVideos(VIDEOS.slice()); _setFilteredActresses(ACTRESSES.slice()); }
function cleanup() { globalThis.fetch = savedFetch; _setFilteredVideos([]); _setFilteredActresses([]); }
function keydown(c, key) { c.handleKeydown({ key, target: { tagName: 'DIV' }, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, preventDefault() {}, stopPropagation() {} }); }
const flush = () => new Promise(resolve => setImmediate(resolve));
const response = data => ({ ok: true, json: async () => data });
const view = maker => ({ success: true, state: 'ok', values: { title: 'Title', maker, actresses: ['A'], plot: 'P', plot_translation: 'T' } });
function setup() {
    const calls = [], toasts = [], pending = [], refreshes = [];
    let get = view('M1'), post = { success: true, values: {} }, refresh = { success: true }, hold = '';
    globalThis.fetch = (url, options = {}) => {
        calls.push({ url, options });
        let data = url.includes('/edit-data') ? get : url.includes('/edit-field') ? post : url.includes('/refresh') ? refresh : url.includes('/repath') ? { success: true, path: 'file:///C:/b.mp4' } : { success: true, state: 'ok' };
        if (url.includes(hold) && hold) return new Promise(resolve => pending.push(() => resolve(response(data))));
        if (data instanceof Error) return Promise.reject(data);
        return Promise.resolve(response(data));
    };
    const c = makeComponent({ currentLightboxVideo: VIDEOS[0], showToast: (...args) => toasts.push(args), refreshVideoData: async video => { refreshes.push(video); }, loadAdvEditInfo: async () => {} }, [stateAdvEditData()]);
    return { c, calls, toasts, refreshes, setGet: x => { get = x; }, setPost: x => { post = x; }, setRefresh: x => { refresh = x; }, hold: x => { hold = x; }, releaseOne: () => pending.pop()?.(), release: () => { hold = ''; pending.splice(0).reverse().forEach(fn => fn()); } };
}
test('test_adv_edit_data_load_and_confirm_success', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.openAdvEdit(); await flush();
        assert.equal(s.calls.filter(x => x.url.includes('/edit-data')).length, 1);
        assert.equal(s.calls[0].url, `/api/showcase/video/edit-data?path=${encodeURIComponent(VIDEOS[0].path)}`); assert.equal(c.advEditData.values.maker, 'M1');
        c.startAdvEditData('actresses'); c.advEditDataDraft = 'A、A,B';
        s.setPost({ success: true, values: { actresses: ['A', 'B'] } }); await c.confirmAdvEditData();
        assert.deepEqual(JSON.parse(s.calls.at(-1).options.body), { path: VIDEOS[0].path, field: 'actresses', value: ['A', 'A', 'B'] });
        assert.equal(c.advEditDataValue('actresses'), 'A、B');
        assert.equal(c._advEditCell, ''); assert.equal(c._advEditBusy, ''); assert.equal(c.advEditDataDraft, '');
        c.startAdvEditData('maker'); c.advEditDataDraft = 'S123'; s.setPost({ success: true, unchanged: true, values: { maker: 'S123' } }); await c.confirmAdvEditData();
        assert.equal(c.advEditDataValue('maker'), 'S123'); assert.equal(c._advEditCell, ''); assert.equal(c._advEditBusy, ''); assert.equal(c.advEditDataDraft, '');
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_data_write_failure_and_plot_pair', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.openAdvEdit(); await flush();
        for (const [error, key] of [['nfo_write_failed', 'err_write_failed'], ['db_write_failed', 'err_db_failed'], [null, 'err_generic']]) {
            const gets = s.calls.filter(x => x.url.includes('/edit-data')).length, refreshes = s.refreshes.length;
            if (error === null) s.setGet(view('M2'));
            c.startAdvEditData('maker'); c.advEditDataDraft = 'X'; s.setPost(error ? { success: false, error } : new Error('offline')); await c.confirmAdvEditData();
            assert.equal(s.calls.filter(x => x.url.includes('/edit-data')).length, gets + (error === null ? 1 : 0));
            assert.equal(s.refreshes.length, refreshes + (error === null ? 1 : 0));
            assert.equal(c._advEditCell, ''); assert.equal(c._advEditBusy, ''); assert.equal(c.advEditData.values.maker, error === null ? 'M2' : 'M1'); assert.deepEqual(s.toasts.at(-1), [`showcase.adv_edit.data.${key}`, 'error']);
        }
        for (const [field, draft, error] of [['release_date', '2024-02-30', 'invalid_date'], ['title', '   ', 'title_empty']]) {
            const n = s.calls.length; c.startAdvEditData(field); c.advEditDataDraft = draft; await c.confirmAdvEditData();
            assert.equal(s.calls.length, n); assert.equal(c._advEditCell, `data:${field}`); assert.equal(c.advEditDataDraft, draft); assert.equal(c.advEditDataError, error); assert.equal(c.advEditDataErrorText(), errorKeyOf(error)); c.cancelAdvEditData();
        }
        c.startAdvEditData('release_date'); c.advEditDataDraft = '2024-03-05'; s.setPost({ success: false, error: 'invalid_date' }); await c.confirmAdvEditData(); assert.equal(c._advEditCell, 'data:release_date'); assert.equal(c.advEditDataDraft, '2024-03-05'); assert.equal(c.advEditDataError, 'invalid_date'); c.cancelAdvEditData();
        c.startAdvEditData('plot'); c.advEditDataDraft = ''; s.setPost({ success: true, values: { plot: 'T', plot_translation: '' } }); await c.confirmAdvEditData();
        assert.equal(c.advEditOpen, true); assert.equal(c.advEditDataValue('plot'), 'T'); assert.equal(c.advEditDataValue('plot_translation'), '');
        const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url)));
        for (const key of Object.values(ADV_EDIT_DATA_ERROR_KEYS)) assert.ok(key.split('.').reduce((o, k) => o?.[k], locale));
        assert.equal(errorKeyOf('nope'), errorKeyOf('not_found')); assert.equal(errorKeyOf('__proto__'), errorKeyOf('not_found'));
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_data_late_responses_and_ime', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        s.hold('/edit-data'); c.openAdvEdit(); c.closeAdvEdit(); s.setGet(view('M2')); c.openAdvEdit(); s.releaseOne(); await flush(); assert.equal(c.advEditData.values.maker, 'M2'); assert.equal(c.advEditDataLoading, false); s.release(); await flush(); assert.equal(c.advEditData.values.maker, 'M2'); assert.equal(c.advEditDataLoading, false);
        c.startAdvEditData('maker'); c.advEditDataDraft = 'X'; s.hold('/edit-field'); s.setPost({ success: true, values: { maker: 'X' } }); const p = c.confirmAdvEditData(); c.closeAdvEdit(); s.release(); await p; assert.equal(c.advEditData, null); assert.equal(s.toasts.length, 0); assert.equal(s.refreshes.length, 0);
        c.openAdvEdit(); await flush(); c.startAdvEditData('maker'); const n = s.calls.length; c.onAdvEditDataEnter({ isComposing: true }); assert.equal(s.calls.length, n); c.onAdvEditDataEnter({ isComposing: false }); await flush(); assert.equal(s.calls.length, n + 1);
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_data_blocked_and_single_slot', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        s.setGet({ success: true, state: 'blocked', reason: 'borrowed' }); c.openAdvEdit(); await flush(); c.startAdvEditData('title'); assert.equal(c._advEditCell, ''); assert.equal(c.advEditDataFields().length, 6); assert.ok(!c.advEditDataFields().some(f => ['plot', 'plot_translation'].includes(f.key))); assert.equal(c.advEditDataValue('actresses'), 'A、B'); assert.equal(c.advEditDataNoteText(), 'showcase.adv_edit.data.note_borrowed');
        s.setGet(view('M1')); await c.loadAdvEditData(); for (const value of ['path', 'data:title']) { c._advEditCell = value; c.startAdvEditData('maker'); assert.equal(c._advEditCell, value); }
        c._advEditCell = ''; c._advEditBusy = 'regen'; c.startAdvEditData('maker'); assert.equal(c._advEditCell, ''); c._advEditBusy = ''; c.startAdvEditData('maker'); c.startAdvEditData('title'); assert.equal(c._advEditCell, 'data:maker'); assert.equal(c.advEditDataDraft, 'M1'); c.cancelAdvEditData(); for (const key of ['number', 'tags']) { c.startAdvEditData(key); assert.equal(c._advEditCell, ''); }
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_data_esc_layers', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.closeLightbox = () => { c.lightboxOpen = false; };
        c.openAdvEdit(); await flush(); c.startAdvEditData('maker'); c.advEditDataDraft = 'X'; c.advEditDataError = 'invalid_date'; keydown(c, 'Escape'); assert.equal(c._advEditCell, ''); assert.equal(c.advEditDataDraft, ''); assert.equal(c.advEditDataError, ''); assert.equal(c.advEditOpen, true); c.advEditDataTagDraft = {}; c.advEditDataTagInput = 'X'; keydown(c, 'Escape'); assert.equal(c.advEditOpen, false); assert.equal(c.advEditData, null); assert.equal(c.advEditDataDraft, ''); assert.equal(c.advEditDataError, ''); assert.equal(c.advEditDataTagDraft, null); assert.equal(c.advEditDataTagInput, ''); keydown(c, 'Escape'); assert.equal(c.lightboxOpen, false);
        c.lightboxOpen = true; c.openAdvEdit(); await flush(); c._advEditCell = 'path'; c.advEditPathDraft = 'X'; c.advEditPathError = 'X'; assert.equal(c.onAdvEditCellCancel(), false); keydown(c, 'Escape'); assert.equal(c.advEditPathDraft, ''); assert.equal(c.advEditPathError, ''); assert.equal(c._advEditCell, ''); assert.equal(c.advEditOpen, true);
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_data_sync_reload_and_exclusion', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.openAdvEdit(); await flush(); s.setRefresh({ success: false, error: 'no_nfo' }); await c.runAdvEditUpdate(); await flush(); assert.equal(s.calls.filter(x => x.url.includes('/edit-data')).length, 1);
        s.setRefresh({ success: true }); s.setGet(view('M2')); await c.runAdvEditUpdate(); await flush(); assert.equal(s.calls.filter(x => x.url.includes('/edit-data')).length, 2); assert.equal(c.advEditData.values.maker, 'M2');
        s.setRefresh({ success: true }); s.hold('/refresh'); const updating = c.runAdvEditUpdate(); c.closeAdvEdit(); s.release(); await updating; assert.equal(c.advEditData, null); c.openAdvEdit(); await flush();
        c._advEditCell = 'data:maker'; assert.equal(c.advEditDataEditing(), true); c._advEditCell = 'path'; assert.equal(c.advEditDataEditing(), false); c._advEditCell = ''; assert.equal(c.advEditDataEditing(), false);
        c._advEditBusy = 'update'; c.startAdvEditData('maker'); assert.equal(c._advEditCell, ''); c._advEditBusy = ''; c._advEditCell = 'path'; c.startAdvEditData('maker'); assert.equal(c._advEditCell, 'path'); c._advEditCell = ''; s.hold('/edit-data'); const loading = c.loadAdvEditData(); c.startAdvEditData('maker'); assert.equal(c._advEditCell, ''); s.release(); await loading;
        const beforePath = s.calls.filter(x => x.url.includes('/edit-data')).length; s.setGet(view('NEW')); c._advEditCell = 'path'; c.advEditPathDraft = 'C:/b.mp4'; c._reloadWallKeepLightbox = async () => { c.currentLightboxVideo = { path: 'file:///C:/b.mp4' }; }; await c.submitAdvEditPath(true); await flush(); const gets = s.calls.filter(x => x.url.includes('/edit-data')); assert.equal(gets.length, beforePath + 1); assert.equal(gets.at(-1).url, `/api/showcase/video/edit-data?path=${encodeURIComponent('file:///C:/b.mp4')}`); assert.equal(c.advEditData.values.maker, 'NEW');
        s.setGet({ success: false }); await c.loadAdvEditData(); assert.equal(c.advEditData, null); s.setGet(new Error('offline')); await c.loadAdvEditData(); assert.equal(c.advEditData, null);
    } finally { s.release(); cleanup(); }
});
