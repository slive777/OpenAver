// TASK-143-T4: readonly_no_output toast — confirmAddLbTag / removeLbUserTag
// harness 照抄 lb-full-error-pill.test.mjs（register + importmap loader）。

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

const PATH = 'file:////tmp/openaver-ro-cdp-t4-test/T4-STUB.mp4';
const TOAST_KEY = 'showcase.lightbox.tag_nfo_not_written';
const BLOCKED_KEY = 'showcase.lightbox.tag_nfo_write_blocked';

function mockFetch(payload) {
    const prev = globalThis.fetch;
    globalThis.fetch = async () => ({
        ok: true,
        status: 200,
        json: async () => payload,
    });
    return { restore() { globalThis.fetch = prev; } };
}

function makeComponent(overrides) {
    const toasts = [];
    const c = Object.assign({}, stateLightbox(), {
        addingLbTag: true,
        newLbTagValue: 'TESTTAG',
        currentLightboxVideo: {
            path: PATH,
            user_tags: ['EXISTING'],
        },
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
        $refs: {},
        toasts,
        showToast(msg, kind) { toasts.push({ msg, kind }); },
    }, overrides);
    return c;
}

test('confirmAddLbTag: readonly_no_output true → showToast(tag_nfo_not_written, info)', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: ['EXISTING', 'TESTTAG'],
        nfo_updated: false,
        readonly_no_output: true,
    });
    try {
        const c = makeComponent();
        await c.confirmAddLbTag();
        assert.ok(
            c.toasts.some((t) => t.msg === TOAST_KEY && t.kind === 'info'),
            `expected toast with ${TOAST_KEY}/info, got ${JSON.stringify(c.toasts)}`,
        );
        assert.deepEqual(c.currentLightboxVideo.user_tags, ['EXISTING', 'TESTTAG']);
    } finally {
        mock.restore();
    }
});

test('removeLbUserTag: readonly_no_output true → showToast(tag_nfo_not_written, info)', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: [],
        nfo_updated: false,
        readonly_no_output: true,
    });
    try {
        const c = makeComponent({
            currentLightboxVideo: { path: PATH, user_tags: ['EXISTING'] },
        });
        await c.removeLbUserTag('EXISTING');
        assert.ok(
            c.toasts.some((t) => t.msg === TOAST_KEY && t.kind === 'info'),
            `expected toast with ${TOAST_KEY}/info, got ${JSON.stringify(c.toasts)}`,
        );
        assert.deepEqual(c.currentLightboxVideo.user_tags, []);
    } finally {
        mock.restore();
    }
});

test('confirmAddLbTag: readonly_no_output false → 不顯示 tag_nfo_not_written toast', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: ['EXISTING', 'TESTTAG'],
        nfo_updated: true,
        readonly_no_output: false,
    });
    try {
        const c = makeComponent();
        await c.confirmAddLbTag();
        assert.equal(
            c.toasts.filter((t) => t.msg === TOAST_KEY).length,
            0,
            `unexpected toast calls: ${JSON.stringify(c.toasts)}`,
        );
    } finally {
        mock.restore();
    }
});


test('confirmAddLbTag: nfo_write_blocked true → showToast(tag_nfo_write_blocked, info)', async () => {
    const mock = mockFetch({
        success: true, user_tags: ['EXISTING', 'TESTTAG'], nfo_updated: false,
        readonly_no_output: false, nfo_write_blocked: true,
    });
    try {
        const c = makeComponent();
        await c.confirmAddLbTag();
        assert.deepEqual(c.toasts, [{ msg: BLOCKED_KEY, kind: 'info' }]);
        assert.deepEqual(c.currentLightboxVideo.user_tags, ['EXISTING', 'TESTTAG']);
    } finally {
        mock.restore();
    }
});


// TASK-188c-T10: 請求在途中換片 → 回應只改按下當下那一片（CD-188c-18）
for (const kind of ['add', 'remove']) {
    test(`switch_mid_flight_${kind}`, async () => {
        const A = { path: 'file:////tmp/t10-A.mp4', user_tags: ['EXISTING'] };
        const B = { path: 'file:////tmp/t10-B.mp4', user_tags: ['OTHER'] };
        const bBefore = structuredClone(B);
        const reply = kind === 'add' ? ['EXISTING', 'TESTTAG'] : [];
        const c = makeComponent({ currentLightboxVideo: A });
        const prev = globalThis.fetch;
        globalThis.fetch = async () => {
            c.currentLightboxVideo = B; // fetch 已發出、回應處理之前換片
            return { ok: true, status: 200, json: async () => ({ success: true, user_tags: reply }) };
        };
        try {
            if (kind === 'add') await c.confirmAddLbTag();
            else await c.removeLbUserTag('EXISTING');
            assert.equal(c.currentLightboxVideo, B, '切片必須真的發生');
            assert.deepEqual(A.user_tags, reply);
            assert.ok(Array.isArray(A._badges));
            assert.deepEqual(B, bBefore);
        } finally {
            globalThis.fetch = prev;
        }
    });
}


// ── 198b-T7b：work_user_tags —— 標籤跟作品走（燈箱停在非預設版本）─────────────────────────
const { normalizeWorkItem: normWork198 } = await import('../work-versions.js');
const { stateLightboxAiTags: aiTags198 } = await import('../state-lightbox-ai-tags.js');

test('work_user_tags：加／刪標籤與 AI 標籤 → 三個版本的標籤都換成作品聯集並重算標章', async () => {
    for (const entry of ['confirmAddLbTag', 'removeLbUserTag', 'lbAiTag']) {
        const mk = (p) => ({ path: 'file:///m/ABF-348' + p, user_tags: ['own'] });
        const list = [mk('-C.mkv'), mk('.mp4'), mk('-LTX.mkv')];
        normWork198({ ...list[0], versions: list });
        const [zh, k4, ltx] = list;
        const union = ['想看', 'own', 'x'];
        const mock = mockFetch({
            success: true, user_tags: ['own'], work_user_tags: union, added: ['x'], refused: false,
            nfo_updated: false, readonly_no_output: false, nfo_write_blocked: false,
        });
        try {
            const c = Object.assign(makeComponent({ currentLightboxVideo: ltx, paginatedVideos: [], newLbTagValue: 'x' }), aiTags198());
            if (entry === 'removeLbUserTag') await c.removeLbUserTag('own');
            else await c[entry]();
            for (const d of list) {
                assert.deepEqual(d.user_tags, union, entry + '：' + d.path + ' 要是作品聯集，不是請求那個檔自己的 [own]');
                assert.ok(Array.isArray(d._badges), entry + '：' + d.path + ' 的標章要重算');
            }
            assert.notEqual(zh.user_tags, k4.user_tags, entry + '：各版本各自一份陣列，不共用實例');
        } finally {
            mock.restore();
        }
    }
});
