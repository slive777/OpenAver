// TASK-188c-T11: 燈箱 AI 鈕——換片捕獲／失敗分流／成功分流（CD-188c-17）
// harness 照 lb-tag-readonly-toast（alias loader）＋ lb-translate-flow（deferred fetch）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key, params) => ({ key, params });

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

const { stateLightboxAiTags } = await import('../state-lightbox-ai-tags.js');

function makeComponent(overrides) {
    const toasts = [];
    const c = Object.assign({}, stateLightboxAiTags(), {
        currentLightboxVideo: null,
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
        $refs: {},
        toasts,
        showToast(msg, type) { toasts.push({ msg, type }); },
    }, overrides);
    return c;
}

function installDeferredFetch() {
    const calls = [];
    const pending = [];
    const original = globalThis.fetch;
    globalThis.fetch = (url, opts) => {
        calls.push({ url, opts });
        return new Promise((resolve, reject) => {
            pending.push({ resolve, reject });
        });
    };
    return {
        calls,
        pending,
        release(i, payload, { ok = true, status = 200 } = {}) {
            pending[i].resolve({
                ok,
                status,
                json: async () => payload,
            });
        },
        restore() { globalThis.fetch = original; },
    };
}

test('lb_ai_capture_switch_mid_flight', async () => {
    const A = { path: 'file:////tmp/t11-A.mp4', user_tags: ['EXISTING'], has_cover: true };
    const B = { path: 'file:////tmp/t11-B.mp4', user_tags: ['OTHER'], has_cover: true };
    const bBefore = structuredClone(B);
    const replyTags = ['AI_ONE', 'AI_TWO'];
    const c = makeComponent({ currentLightboxVideo: A });
    const f = installDeferredFetch();
    try {
        const p = c.lbAiTag();
        assert.equal(c.lbAiIsBusy(), true, 'A in-flight → busy');
        // 同片再按一次應被忽略
        c.lbAiTag();
        assert.equal(f.calls.length, 1, '同片飛行中再按只發一次請求');

        c.currentLightboxVideo = B;
        assert.equal(c.currentLightboxVideo, B, '切片必須真的發生');
        assert.equal(c.lbAiIsBusy(), false, '切到 B：B 不在 in-flight');

        f.release(0, {
            success: true,
            added: replyTags,
            refused: false,
            user_tags: replyTags,
            readonly_no_output: false,
            nfo_write_blocked: false,
        });
        await p;

        assert.deepEqual(A.user_tags, replyTags);
        assert.ok(Array.isArray(A._badges), 'A._badges 被重算');
        assert.deepEqual(B, bBefore, 'B 整物件逐字不變');
        assert.equal(c.lbAiIsBusy(), false, '放行後鎖已清（對目前片 B）');

        // 放行後再按（現在在 B）應再發第二個請求
        const p2 = c.lbAiTag();
        assert.equal(f.calls.length, 2, '鎖清掉後再按會再發');
        f.release(1, {
            success: true,
            added: [],
            refused: false,
            user_tags: ['OTHER'],
            readonly_no_output: false,
            nfo_write_blocked: false,
        });
        await p2;
    } finally {
        f.restore();
    }
});

test('lb_ai_failure_toast_routing', async () => {
    const rows = [
        {
            name: 'unreachable+connection_failed',
            payload: { success: false, reason: 'unreachable', detail: 'connection_failed' },
            expectKey: 'showcase.lightbox.ai_tags_unreachable',
            expectProvider: 'Gemini',
        },
        {
            name: 'unreachable+rate_limited',
            payload: { success: false, reason: 'unreachable', detail: 'rate_limited' },
            expectKey: 'showcase.lightbox.ai_tags_rate_limited',
            expectProvider: 'Gemini',
        },
        {
            name: 'model_unsupported',
            payload: { success: false, reason: 'model_unsupported' },
            expectKey: 'showcase.lightbox.ai_tags_model_unsupported',
            expectProvider: undefined,
        },
        {
            name: 'bad_response',
            payload: { success: false, reason: 'bad_response' },
            expectKey: 'showcase.lightbox.ai_tags_bad_response',
            expectProvider: undefined,
        },
        {
            name: 'not_configured',
            payload: { success: false, reason: 'not_configured' },
            expectKey: 'showcase.lightbox.ai_tags_not_configured',
            expectProvider: undefined,
        },
        {
            name: 'disabled',
            payload: { success: false, reason: 'disabled' },
            expectKey: 'showcase.lightbox.ai_tags_not_configured',
            expectProvider: undefined,
        },
        {
            name: 'no_cover',
            payload: { success: false, reason: 'no_cover' },
            expectKey: 'showcase.lightbox.ai_tags_failed',
            expectProvider: undefined,
        },
        {
            name: 'HTTP 500',
            http: { ok: false, status: 500, body: {} },
            expectKey: 'showcase.lightbox.ai_tags_failed',
            expectProvider: undefined,
        },
    ];

    const prevFlag = globalThis.__SHOWCASE_AI_TAGS__;
    globalThis.__SHOWCASE_AI_TAGS__ = { enabled: true, provider: 'gemini' };
    try {
        for (const row of rows) {
            const A = { path: 'file:////tmp/t11-fail.mp4', user_tags: ['EXISTING'], has_cover: true };
            const tagsBefore = [...A.user_tags];
            const c = makeComponent({ currentLightboxVideo: A });
            const f = installDeferredFetch();
            try {
                const p = c.lbAiTag();
                if (row.http) {
                    f.release(0, row.http.body, { ok: row.http.ok, status: row.http.status });
                } else {
                    f.release(0, row.payload);
                }
                await p;

                assert.equal(c.lbAiIsBusy(), false, `${row.name}: 鎖已清`);
                assert.deepEqual(A.user_tags, tagsBefore, `${row.name}: user_tags 不變`);
                assert.equal(c.toasts.length, 1, `${row.name}: 恰一則 toast`);
                const t = c.toasts[0];
                assert.equal(t.type, 'error', `${row.name}: type error`);
                assert.equal(t.msg.key, row.expectKey, `${row.name}: key`);
                if (row.expectProvider !== undefined) {
                    assert.equal(t.msg.params?.provider, row.expectProvider, `${row.name}: provider`);
                }
            } finally {
                f.restore();
            }
        }
    } finally {
        if (prevFlag === undefined) delete globalThis.__SHOWCASE_AI_TAGS__;
        else globalThis.__SHOWCASE_AI_TAGS__ = prevFlag;
    }
});

test('lb_ai_success_toast_routing', async () => {
    const rows = [
        {
            name: 'added 2',
            payload: {
                success: true,
                added: ['a', 'b'],
                refused: false,
                user_tags: ['EXISTING', 'a', 'b'],
                readonly_no_output: false,
                nfo_write_blocked: false,
            },
            expect: [{ key: 'showcase.lightbox.ai_tags_added', type: 'success', n: 2 }],
        },
        {
            name: 'added empty',
            payload: {
                success: true,
                added: [],
                refused: false,
                user_tags: ['EXISTING'],
                readonly_no_output: false,
                nfo_write_blocked: false,
            },
            expect: [{ key: 'showcase.lightbox.ai_tags_none', type: 'info' }],
        },
        {
            name: 'refused',
            payload: {
                success: true,
                added: [],
                refused: true,
                user_tags: ['EXISTING'],
                readonly_no_output: false,
                nfo_write_blocked: false,
            },
            expect: [{ key: 'showcase.lightbox.ai_tags_refused', type: 'info' }],
        },
        {
            name: 'readonly_no_output',
            payload: {
                success: true,
                added: ['a'],
                refused: false,
                user_tags: ['EXISTING', 'a'],
                readonly_no_output: true,
                nfo_write_blocked: false,
            },
            expect: [{ key: 'showcase.lightbox.tag_nfo_not_written', type: 'info' }],
            noAddedToast: true,
        },
        {
            name: 'nfo_write_blocked',
            payload: {
                success: true,
                added: ['a'],
                refused: false,
                user_tags: ['EXISTING', 'a'],
                readonly_no_output: false,
                nfo_write_blocked: true,
            },
            expect: [{ key: 'showcase.lightbox.tag_nfo_write_blocked', type: 'info' }],
            noAddedToast: true,
        },
    ];

    for (const row of rows) {
        const A = { path: 'file:////tmp/t11-ok.mp4', user_tags: ['EXISTING'], has_cover: true };
        const c = makeComponent({ currentLightboxVideo: A });
        const f = installDeferredFetch();
        try {
            const p = c.lbAiTag();
            f.release(0, row.payload);
            await p;

            assert.deepEqual(A.user_tags, row.payload.user_tags, `${row.name}: user_tags 寫回`);
            assert.equal(c.toasts.length, row.expect.length, `${row.name}: toast 數`);
            for (let i = 0; i < row.expect.length; i++) {
                const exp = row.expect[i];
                const got = c.toasts[i];
                assert.equal(got.msg.key, exp.key, `${row.name}: key`);
                assert.equal(got.type, exp.type, `${row.name}: type`);
                if (exp.n !== undefined) {
                    assert.equal(got.msg.params?.n, exp.n, `${row.name}: n`);
                }
            }
            if (row.noAddedToast) {
                assert.equal(
                    c.toasts.filter((t) => String(t.msg?.key || '').includes('ai_tags_added')).length,
                    0,
                    `${row.name}: 無 added toast`,
                );
            }
        } finally {
            f.restore();
        }
    }
});
