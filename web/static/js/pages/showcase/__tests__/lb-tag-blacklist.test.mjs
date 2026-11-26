import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

const IMPORTMAP = {
    '@/settings/': 'pages/settings/',
    '@/shared/': 'shared/',
    '@/components/': 'components/',
    '@/search/': 'pages/search/',
    '@/showcase/': 'pages/showcase/',
    '@/scanner/': 'pages/scanner/',
};
const STATIC_JS_ROOT = pathToFileURL(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../') + '/',
).href;
const loaderCode = `
const IMPORTMAP = ${JSON.stringify(IMPORTMAP)};
const STATIC_JS_ROOT = ${JSON.stringify(STATIC_JS_ROOT)};
export async function resolve(specifier, context, nextResolve) {
    for (const [prefix, rel] of Object.entries(IMPORTMAP)) {
        if (specifier.startsWith(prefix)) {
            return nextResolve(STATIC_JS_ROOT + rel + specifier.slice(prefix.length), context);
        }
    }
    if (specifier.startsWith('@/')) {
        return nextResolve(STATIC_JS_ROOT + specifier.slice(2), context);
    }
    return nextResolve(specifier, context);
}
`;
register(`data:text/javascript,${encodeURIComponent(loaderCode)}`, import.meta.url);

const { stateLightboxTags: stateLightbox } = await import('../state-lightbox-tags.js');
const { _setHiddenTagKeys } = await import('../state-base.js');
const { isTagHidden, workTagsOf } = await import('@/shared/tag-display.js');
const PATH = 'file:////tmp/openaver-tag-test/video.mp4';

function mockFetch(payload) {
    const prev = globalThis.fetch;
    const calls = [];
    globalThis.fetch = async (...args) => {
        calls.push(args);
        return { ok: true, status: 200, json: async () => payload };
    };
    return { calls, restore() { globalThis.fetch = prev; } };
}

function makeComponent(overrides) {
    const toasts = [];
    return Object.assign({}, stateLightbox(), {
        addingLbTag: true,
        newLbTagValue: 'TESTTAG',
        currentLightboxVideo: { path: PATH, user_tags: [] },
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
        $refs: {},
        toasts,
        showToast(msg, kind) { toasts.push({ msg, kind }); },
    }, overrides);
}

test('test_lightbox_work_tag_dedup_with_user_tag', () => {
    try {
        const video = { tags: '舊字', tags_display: '女僕,巨乳', user_tags: ['女僕'] };
        const c = makeComponent({ currentLightboxVideo: video });
        assert.deepEqual(c.lbxWorkTags(), ['巨乳']);
        assert.deepEqual(c.lbxUserTags(), ['女僕']);
        video.user_tags = [];
        assert.deepEqual(c.lbxWorkTags(), ['女僕', '巨乳']);
        assert.deepEqual(workTagsOf({ tags: '舊字', tags_display: '' }), []);
    } finally { _setHiddenTagKeys([]); }
});

test('test_lightbox_user_tags_masked_not_renamed', () => {
    try {
        _setHiddenTagKeys(['高畫質']);
        const c = makeComponent({ currentLightboxVideo: {
            tags_display: '女僕', user_tags: ['メイド', '高畫質'],
        } });
        assert.deepEqual(c.lbxUserTags(), ['メイド']);
    } finally { _setHiddenTagKeys([]); }
});

for (const [name, tag, hidden] of [['hidden', ' Blu-Ray ', true], ['visible', 'メイド', false]]) {
    test(`test_confirm_add_hidden_tag_blocked: ${name}`, async () => {
        const mock = mockFetch({ success: true, user_tags: ['メイド'], nfo_updated: true });
        try {
            _setHiddenTagKeys(['blu-ray']);
            const c = makeComponent({ newLbTagValue: tag });
            await c.confirmAddLbTag();
            if (hidden) {
                assert.equal(mock.calls.length, 0);
                assert.deepEqual(c.toasts, [{ msg: 'showcase.lightbox.tag_blacklisted', kind: 'info' }]);
                assert.equal(c.addingLbTag, false);
                assert.equal(c.newLbTagValue, '');
                assert.equal(isTagHidden('  Blu-Ray ', ['blu-ray']), true);
            } else {
                assert.equal(mock.calls.length, 1);
                assert.deepEqual(JSON.parse(mock.calls[0][1].body).add, ['メイド']);
                assert.equal(c.toasts.some((t) => t.msg === 'showcase.lightbox.tag_blacklisted'), false);
            }
        } finally { mock.restore(); _setHiddenTagKeys([]); }
    });
}
