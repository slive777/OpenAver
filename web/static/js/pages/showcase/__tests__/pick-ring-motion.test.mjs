import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key, p) => (p ? key + '|' + p.tier + '>' + p.next : key);

// closeLightbox / searchFromMetadata 會碰 document；給最小 stub。
globalThis.document = {
    querySelector() { return null; },
    querySelectorAll() { return { length: 0 }; },
    addEventListener() {},
    body: {
        classList: {
            remove() {},
            add() {},
            contains() { return false; },
        },
    },
};

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

const { stateLightbox } = await import('../state-lightbox.js');
const { stateVideos } = await import('../state-videos.js');
const { statePickTier } = await import('../state-pick-tier.js');
await import('../animations.js');

const PATH_A = 'file:///m/ABC-123.mp4';
/** 手動 resolve 的 fetch mock：可量測飛行中再呼叫、可精準控制落地時機。 */
function mockFetchManual() {
    const prev = globalThis.fetch;
    const calls = [];
    globalThis.fetch = (url, opts) => {
        const body = opts && opts.body ? JSON.parse(opts.body) : {};
        return new Promise((resolve, reject) => {
            calls.push({
                url,
                method: opts && opts.method,
                body,
                resolve: (respLike) => resolve(respLike),
                reject: (err) => reject(err),
            });
        });
    };
    return {
        restore() { globalThis.fetch = prev; },
        calls,
    };
}

function okResp(results) {
    return {
        ok: true,
        status: 200,
        json: async () => ({
            success: true,
            results: results || [{ ok: true }],
        }),
    };
}

function makeComponent(overrides) {
    const c = Object.assign({}, stateLightbox(), stateVideos(), statePickTier(), {
        pills: [],
        lightboxOpen: true,
        applyFilterAndSortCalls: 0,
        applyFilterAndSort() { c.applyFilterAndSortCalls++; },
        toasts: [],
        showToast(msg, kind) { c.toasts.push({ msg, kind }); },
        _resetMask() {},
        _closePicker() {},
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
    }, overrides);
    return c;
}


test('按星繞線: 精選三態各播一次、取消不播', async () => {
    const mock = mockFetchManual();
    const previous = window.ShowcaseAnimations.playPickRing;
    let count = 0;
    window.ShowcaseAnimations.playPickRing = () => { count++; };
    try {
        const video = { path: PATH_A, user_rating: 0 };
        const c = makeComponent({ currentLightboxVideo: video });
        for (const expected of [1, 2, 3, 3]) {
            const promise = c.togglePickStar();
            mock.calls.at(-1).resolve(okResp());
            await promise;
            assert.equal(count, expected);
        }
    } finally { window.ShowcaseAnimations.playPickRing = previous; mock.restore(); }
});

test('按星繞線: 失敗回滾階段不新增播放', async () => {
    const mock = mockFetchManual();
    const previous = window.ShowcaseAnimations.playPickRing;
    let count = 0;
    window.ShowcaseAnimations.playPickRing = () => { count++; };
    try {
        const video = { path: PATH_A, user_rating: 0 };
        const c = makeComponent({ currentLightboxVideo: video });
        const promise = c.togglePickStar();
        assert.equal(count, 1);
        mock.calls[0].resolve({ ok: false, status: 500 });
        await promise;
        assert.equal(count, 1);
        assert.equal(video.user_rating, 0);
        assert.equal(c.toasts.length, 1);
    } finally { window.ShowcaseAnimations.playPickRing = previous; mock.restore(); }
});

test('按星繞線: 減少動態不建補間', () => {
    const saved = Object.fromEntries(['gsap', 'DrawSVGPlugin', 'getComputedStyle', 'OpenAver'].map(k => [k, globalThis[k]]));
    const calls = { timeline: 0, fromTo: 0, to: 0, set: 0, killTweensOf: 0 };
    const tl = { fromTo() { calls.fromTo++; return tl; }, to() { calls.to++; return tl; }, kill() {} };
    const paths = [{ setAttribute() {} }, { setAttribute() {} }];
    const ring = { querySelectorAll() { return paths; }, setAttribute() {} };
    const frame = { clientWidth: 400, clientHeight: 300, getBoundingClientRect() { return { left: 0, width: 400 }; } };
    const star = { getBoundingClientRect() { return { left: 190, width: 20 }; } };
    try {
        globalThis.DrawSVGPlugin = {};
        globalThis.getComputedStyle = () => ({ borderTopLeftRadius: '12px' });
        globalThis.gsap = { plugins: { drawSVG: true }, registerPlugin() {},
            timeline() { calls.timeline++; return tl; }, set() { calls.set++; }, killTweensOf() { calls.killTweensOf++; } };
        globalThis.OpenAver = { prefersReducedMotion: false };
        window.ShowcaseAnimations.playPickRing(ring, star, frame);
        assert.ok(calls.timeline >= 1);
        for (const key of Object.keys(calls)) calls[key] = 0;
        globalThis.OpenAver.prefersReducedMotion = true;
        assert.equal(window.ShowcaseAnimations.playPickRing(ring, star, frame), null);
        assert.deepEqual(calls, { timeline: 0, fromTo: 0, to: 0, set: 0, killTweensOf: 0 });
    } finally { for (const [key, value] of Object.entries(saved)) globalThis[key] = value; }
});
