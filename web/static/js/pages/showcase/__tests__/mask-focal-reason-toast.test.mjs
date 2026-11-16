// TASK-D4 reason → toast（CD-152d-4b）+ TASK-D6 停用自動對焦後仍可存裁切回歸。
// harness 照抄 lb-tag-readonly-toast.test.mjs；另 stub DOM 幾何 API（假綠陷阱②③）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
// openMask 在 detect 路徑會掛 resize listener；node:test 無 DOM EventTarget。
if (typeof globalThis.window.addEventListener !== 'function') {
    globalThis.window.addEventListener = () => {};
}
if (typeof globalThis.window.removeEventListener !== 'function') {
    globalThis.window.removeEventListener = () => {};
}

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

const { stateLightboxMask } = await import('../state-lightbox-mask.js');

const AUTO_DISABLED_KEY = 'showcase.lightbox.mask_focal_too_slow_auto_disabled';
const HINT_KEY = 'showcase.lightbox.mask_focal_too_slow_hint';
const SAVE_FAILED_KEY = 'showcase.lightbox.mask_save_failed';

function mockFetch(payload) {
    const calls = [];
    const prev = globalThis.fetch;
    globalThis.fetch = async (...args) => {
        calls.push(args);
        return {
            ok: true,
            status: 200,
            json: async () => payload,
        };
    };
    return {
        calls,
        restore() { globalThis.fetch = prev; },
    };
}

function makeComponent(overrides = {}) {
    const toasts = [];
    const imgEl = {
        naturalWidth: 100,
        getBoundingClientRect: () => ({ width: 100, height: 150 }),
        closest: () => null,
    };
    const c = Object.assign({}, stateLightboxMask(), {
        _lbFullLoaded: true,
        currentLightboxVideo: { path: 'file:///test.mp4' },
        currentLightboxActress: null,
        $refs: { lightboxCoverFull: imgEl },
        toasts,
        showToast(msg, kind) { toasts.push({ msg, kind }); },
    }, overrides);
    return c;
}

function withGeometryStub(fn) {
    const prev = globalThis.getComputedStyle;
    globalThis.getComputedStyle = () => ({ getPropertyValue: () => '0.667' });
    return (async () => {
        try {
            return await fn();
        } finally {
            if (prev === undefined) {
                delete globalThis.getComputedStyle;
            } else {
                globalThis.getComputedStyle = prev;
            }
        }
    })();
}

test('停用自動對焦後：openMask 仍取得 cover token，confirmMask 存得進去（152d-T-D6 回歸鎖）', async () => {
    await withGeometryStub(async () => {
        const COVER = 'file:///fake/cover.jpg';
        const calls = [];
        const prevFetch = globalThis.fetch;
        globalThis.fetch = async (...args) => {
            calls.push(args);
            const url = String(args[0] || '');
            if (url.includes('/api/showcase/video/detect-focal')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        success: true,
                        reason: 'device_disabled',
                        auto_focal: '',
                        cover_path: COVER,
                    }),
                };
            }
            if (url.includes('/api/showcase/video/save-focal')) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({ success: true, auto_focal: '0.5000,0.5000' }),
                };
            }
            assert.fail(`unexpected fetch URL: ${url}`);
        };
        try {
            const c = makeComponent();
            await c.openMask();
            assert.equal(
                c._maskExpectedCoverPath,
                COVER,
                'detect-focal（device_disabled）必須帶回 cover token，否則 confirmMask fail-closed',
            );

            await c.confirmMask();

            const saveCall = calls.find(([url]) => String(url).includes('/api/showcase/video/save-focal'));
            assert.ok(saveCall, '必須 POST /api/showcase/video/save-focal');
            const saveOpts = saveCall[1] || {};
            assert.equal(saveOpts.method, 'POST');
            const body = JSON.parse(saveOpts.body);
            assert.equal(body.expected_cover_path, COVER);
            assert.equal(
                c.toasts.filter((t) => t.msg === SAVE_FAILED_KEY).length,
                0,
                `不得出現 mask_save_failed，got ${JSON.stringify(c.toasts)}`,
            );
        } finally {
            globalThis.fetch = prevFetch;
        }
    });
});

test('openMask: reason=too_slow_auto_disabled shows auto-disabled toast', async () => {
    await withGeometryStub(async () => {
        const mock = mockFetch({
            success: true,
            auto_focal: '',
            reason: 'too_slow_auto_disabled',
            cover_path: 'file:///cover.jpg',
        });
        try {
            const c = makeComponent();
            await c.openMask();
            assert.ok(
                c.toasts.some((t) => t.msg === AUTO_DISABLED_KEY && t.kind === 'info'),
                `expected ${AUTO_DISABLED_KEY}/info, got ${JSON.stringify(c.toasts)}`,
            );
            assert.equal(
                c.toasts.filter((t) => t.msg === HINT_KEY).length,
                0,
                'must not also show the suggestion toast',
            );
        } finally {
            mock.restore();
        }
    });
});

test('test_confirm_mask_toast_follows_poster_status_for_video_only', async () => {
    await withGeometryStub(async () => {
        const saveWith = async (overrides, payload) => {
            const prev = globalThis.fetch;
            globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({ success: true, auto_focal: '0.4000,0.5000', ...payload }) });
            try {
                const c = makeComponent(overrides);
                await c.confirmMask();
                return c.toasts;
            } finally {
                globalThis.fetch = prev;
            }
        };
        const videoBase = { _maskKind: 'video', _maskFocalX: 0.4, _maskSession: 1, _maskVisible: true, _maskExpectedCoverPath: 'file:///cover.jpg' };
        assert.deepEqual(await saveWith(videoBase, { poster: { status: 'failed' } }), [{ msg: 'showcase.lightbox.focal_saved_poster_failed', kind: 'error' }]);
        assert.deepEqual(await saveWith(videoBase, {}), [{ msg: 'showcase.lightbox.focal_saved', kind: 'success' }]);
        const actressToasts = await saveWith({ _maskKind: 'actress', _maskFocalX: 0.4, _maskSession: 1, _maskVisible: true, currentLightboxVideo: null, currentLightboxActress: { name: 'ActressA' }, _syncActressesArray() {} }, { poster: { status: 'updated' } });
        assert.deepEqual(actressToasts, []);
    });
});


