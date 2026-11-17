import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = key => key;
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.Alpine = globalThis.Alpine || { store: () => ({ toolbarOpen: false, showcaseHasSearch: false }) };
globalThis.document = globalThis.document || { querySelector() { return null; }, body: { classList: { add() {}, remove() {}, contains() { return false; } } } };
register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

const { stateAdvEditData } = await import('../state-adv-edit-data.js');
const { errorKeyOf } = await import('../adv-edit-data-logic.js');
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
const { normalizeWorkItem } = await import('../work-versions.js');
const { readFileSync } = await import('node:fs');
const VIDEOS = [{ path: 'file:///C:/a.mp4', number: 'AAA-001', actresses: 'A,B', tags: 'A,B', user_tags: ['U1', 'U2'] }];
const ACTRESSES = [{ name: 'A' }, { name: 'B' }];
function makeComponent(overrides, extraSlices = []) {
    return Object.assign({}, stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateActress(), stateLightboxVersions(), stateLightboxPop(), stateLightboxTags(), stateSimilar(), stateAdvEdit(), ...extraSlices, {
        pills: [], lightboxOpen: true, showFavoriteActresses: false, currentLightboxActress: null,
        lightboxIndex: 0, actressLightboxIndex: 0, similarModeOpen: false, similarModeMobileOpen: false,
        removeActressModalOpen: false, _pickerOpen: false, rescrapeOpen: false, deleteVideoModalOpen: false,
        sampleGalleryOpen: false, _pillEditor: null, _releaseEditor: null, _maskVisible: false,
        $nextTick() {}, $refs: {}, _fetchLiveAliases() {}, paginatedVideos: [],
    }, overrides);
}
let savedFetch;
function seed() { savedFetch = globalThis.fetch; _setFilteredVideos(VIDEOS.slice()); _setFilteredActresses(ACTRESSES.slice()); }
function cleanup() { globalThis.fetch = savedFetch; _setFilteredVideos([]); _setFilteredActresses([]); }
function keydown(c, key) { c.handleKeydown({ key, target: { tagName: 'DIV' }, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, preventDefault() {}, stopPropagation() {} }); }
const flush = () => new Promise(resolve => setImmediate(resolve));
const response = data => ({ ok: true, json: async () => data });
const view = () => ({ success: true, state: 'ok', values: {}, tags: [{ text: 'A', from_filename: false }, { text: 'B', from_filename: false }, { text: 'SUB-FN', from_filename: true }] });
function setup() {
    const calls = [], toasts = [], pending = [], refreshes = [];
    let get = view(), post = { success: true, tags: [] }, user = { success: true, user_tags: ['U2', 'N1'], work_user_tags: ['U2', 'N1'] }, hold = '';
    globalThis.fetch = (url, options = {}) => {
        calls.push({ url, options });
        const data = url.includes('/edit-data') ? get : url.includes('/edit-field') ? post : url.includes('/api/user-tags') ? user : { success: true };
        if (url.includes(hold) && hold) return new Promise(resolve => pending.push(() => resolve(response(data))));
        if (data instanceof Error) return Promise.reject(data);
        return Promise.resolve(response(data));
    };
    const c = makeComponent({ currentLightboxVideo: { ...VIDEOS[0], user_tags: ['U1', 'U2'] }, showToast: (...args) => toasts.push(args), refreshVideoData: async video => { refreshes.push(video); }, loadAdvEditInfo: async () => {} }, [stateAdvEditData()]);
    return { c, calls, toasts, refreshes, setGet: x => { get = x; }, setPost: x => { post = x; }, setUser: x => { user = x; }, hold: x => { hold = x; }, release: () => { hold = ''; pending.splice(0).reverse().forEach(fn => fn()); } };
}
test('test_adv_edit_tags_draft_zero_requests_and_net_diff', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.openAdvEdit(); await flush();
        for (const [kind, first, second] of [['tags', 'A', 'B'], ['utags', 'U1', 'U2']]) {
            const n = s.calls.length; c.startAdvEditTags(kind); c.removeAdvEditTag(kind, first); c.removeAdvEditTag(kind, second);
            c.startAdvEditTagInput(kind); c.advEditDataTagInput = second; c.commitAdvEditTagInput(kind);
            c.startAdvEditTagInput(kind); c.advEditDataTagInput = 'TEMP'; c.commitAdvEditTagInput(kind); c.removeAdvEditTag(kind, 'TEMP');
            c.startAdvEditTagInput(kind); c.advEditDataTagInput = 'N1'; c.onAdvEditTagInputEnter(kind, { isComposing: true }); assert.equal(c._advEditCell, `data:${kind}+`);
            assert.equal(s.calls.length, n); await c.confirmAdvEditTags(kind); assert.equal(s.calls.length, n + 1);
            const body = JSON.parse(s.calls.at(-1).options.body);
            assert.deepEqual(body, kind === 'tags' ? { path: VIDEOS[0].path, field: 'tags', add: ['N1'], remove: [first] } : { file_path: VIDEOS[0].path, add: ['N1'], remove: [first] });
        }
        const n = s.calls.length; c.startAdvEditTags('tags'); await c.confirmAdvEditTags('tags'); assert.equal(s.calls.length, n);
        c.startAdvEditTags('tags'); c.startAdvEditTagInput('tags'); c.advEditDataTagInput = 'A,B'; await c.confirmAdvEditTags('tags'); assert.equal(s.calls.length, n); assert.equal(c.advEditDataError, 'tag_invalid');
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_tags_esc_and_cancel_layers', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        for (const kind of ['tags', 'utags']) {
            c.openAdvEdit(); await flush(); const n = s.calls.length; c.startAdvEditTags(kind); c.removeAdvEditTag(kind, kind === 'tags' ? 'A' : 'U1'); c.startAdvEditTagInput(kind);
            keydown(c, 'Escape'); assert.equal(c._advEditCell, `data:${kind}`); assert.equal(c.advEditDataTagDraft.removed.length, 1);
            keydown(c, 'Escape'); assert.equal(c._advEditCell, ''); assert.equal(c.advEditDataTagDraft, null); keydown(c, 'Escape'); assert.equal(c.advEditOpen, false); assert.equal(s.calls.length, n);
        }
        c.openAdvEdit(); await flush(); c.startAdvEditTags('tags'); c.cancelAdvEditTags(); assert.equal(c._advEditCell, ''); c._advEditCell = 'path'; assert.equal(c.onAdvEditCellCancel(), false);
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_tags_from_filename_not_removable_and_keys', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.openAdvEdit(); await flush(); const fixed = c.advEditTagsView('tags').find(x => x.text === 'SUB-FN'); assert.equal(c.advEditTagRemovable(fixed), false); assert.equal(c.advEditTagRemovable({ text: 'A' }), true);
        c.startAdvEditTags('tags'); c.removeAdvEditTag('tags', 'SUB-FN'); c.startAdvEditTagInput('tags'); c.advEditDataTagInput = 'SUB-FN'; c.commitAdvEditTagInput('tags'); assert.equal(c.advEditTagsView('tags').filter(x => x.text === 'SUB-FN').length, 1); c.cancelAdvEditTags();
        c.advEditData = { state: 'blocked' }; assert.deepEqual(c.advEditTagKinds(), ['tags', 'utags']); assert.equal(c.advEditTagsCanEdit('tags'), false); assert.equal(c.advEditTagsCanEdit('utags'), true); c.advEditData = null; c.advEditDataLoading = true; assert.deepEqual(c.advEditTagKinds(), []); c.advEditDataLoading = false; assert.deepEqual(c.advEditTagKinds(), ['utags']);
        const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url))); for (const key of ['label_tags', 'label_utags', 'ph_tag', 'tag_from_filename', 'tag_remove', 'tag_add']) assert.ok(locale.showcase.adv_edit.data[key]);
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_utags_shared_method', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.newLbTagValue = 'N1'; await c.confirmAddLbTag(); assert.deepEqual(JSON.parse(s.calls.at(-1).options.body), { file_path: VIDEOS[0].path, add: ['N1'] });
        await c.removeLbUserTag('U1'); assert.deepEqual(JSON.parse(s.calls.at(-1).options.body), { file_path: VIDEOS[0].path, remove: ['U1'] });
        const versions = [{ ...VIDEOS[0], user_tags: ['U1', 'U2'] }, { ...VIDEOS[0], path: 'file:///C:/b.mp4', user_tags: ['U1', 'U2'] }];
        c.currentLightboxVideo = normalizeWorkItem({ versions }); s.setUser({ success: true, user_tags: ['wrong'], work_user_tags: ['U2', 'N1'], readonly_no_output: true });
        c.openAdvEdit(); await flush(); const n = s.calls.length; c.startAdvEditTags('utags'); c.removeAdvEditTag('utags', 'U1'); c.startAdvEditTagInput('utags'); c.advEditDataTagInput = 'N1'; await c.confirmAdvEditTags('utags');
        assert.equal(s.calls.length, n + 1); assert.deepEqual(JSON.parse(s.calls.at(-1).options.body), { file_path: VIDEOS[0].path, add: ['N1'], remove: ['U1'] });
        for (const version of versions) assert.deepEqual(version.user_tags, ['U2', 'N1']);
        assert.deepEqual(s.toasts.at(-1), ['showcase.lightbox.tag_nfo_not_written', 'info']);
        s.setUser({ success: false }); assert.equal(await c._applyUserTagsChange({ add: ['N1'], remove: ['U1'] }), false);
    } finally { s.release(); cleanup(); }
});
test('test_adv_edit_tags_failure_classes', async () => {
    seed(); const s = setup(), { c } = s;
    try {
        c.openAdvEdit(); await flush(); c.startAdvEditTags('tags'); c.removeAdvEditTag('tags', 'A'); s.setPost({ success: false, error: 'tag_hidden' }); await c.confirmAdvEditTags('tags'); assert.equal(c.advEditDataError, 'tag_hidden'); assert.equal(c._advEditCell, 'data:tags'); assert.equal(s.toasts.length, 0);
        s.setPost({ success: false, error: 'nfo_write_failed' }); await c.confirmAdvEditTags('tags'); assert.equal(c._advEditCell, ''); assert.deepEqual(c.advEditData.tags.map(tag => tag.text), ['A', 'B', 'SUB-FN']); assert.deepEqual(s.toasts.at(-1), [errorKeyOf('nfo_write_failed'), 'error']);
        const newView = view(); newView.tags[0].text = 'Z'; s.setGet(newView); const gets = s.calls.filter(x => x.url.includes('/edit-data')).length;
        c.startAdvEditTags('tags'); c.removeAdvEditTag('tags', 'A'); s.setPost(new Error('net')); await c.confirmAdvEditTags('tags'); assert.equal(s.calls.filter(x => x.url.includes('/edit-data')).length, gets + 1); assert.equal(c._advEditCell, ''); assert.equal(c._advEditBusy, ''); assert.equal(c.advEditDataTagDraft, null); assert.deepEqual(c.advEditData.tags.map(tag => tag.text), ['Z', 'B', 'SUB-FN']); assert.deepEqual(s.toasts.at(-1), [errorKeyOf(undefined), 'error']);
        c.startAdvEditTags('utags'); c.removeAdvEditTag('utags', 'U1'); s.setUser({ success: false }); await c.confirmAdvEditTags('utags'); assert.equal(c._advEditCell, ''); assert.equal(s.toasts.at(-1)[0], 'showcase.lightbox.tag_api_failed');
        c.startAdvEditTags('tags'); c.removeAdvEditTag('tags', 'Z'); s.hold('/edit-field'); const pending = c.confirmAdvEditTags('tags'); c.closeAdvEdit(); s.release(); await pending; assert.equal(c.advEditData, null); assert.equal(s.refreshes.length, 1);
    } finally { s.release(); cleanup(); }
});
