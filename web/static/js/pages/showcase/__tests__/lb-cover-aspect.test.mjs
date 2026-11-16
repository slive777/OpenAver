// TASK-200a-T3 F1: cover aspect follows full image; late thumbnail must not overwrite.

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

const { stateLightbox } = await import('../state-lightbox.js');

function makeContainer() {
    const props = {};
    return {
        style: {
            setProperty(k, v) { props[k] = v; },
            getPropertyValue(k) { return props[k]; },
        },
        _props: props,
    };
}

function makeImg({ nw, nh, isFull, container, complete = true }) {
    return {
        naturalWidth: nw,
        naturalHeight: nh,
        complete,
        classList: {
            contains(name) { return name === 'lb-full' && !!isFull; },
        },
        closest(sel) { return sel === '.lightbox-cover' ? container : null; },
    };
}

function makeComponent({ container, fullImg, overrides } = {}) {
    const box = container || makeContainer();
    const full = fullImg || makeImg({ nw: 600, nh: 900, isFull: true, container: box });
    return Object.assign({}, stateLightbox(), {
        _lbFullLoaded: false,
        $refs: { lightboxCoverFull: full },
        $nextTick: (fn) => fn(),
    }, overrides);
}

test('test_cover_aspect_follows_full_image_and_ignores_late_thumbnail', () => {
    const box = makeContainer();
    const thumb = makeImg({ nw: 800, nh: 600, isFull: false, container: box });
    const full = makeImg({ nw: 600, nh: 900, isFull: true, container: box });
    const expected = (600 / 900).toFixed(4);

    // (a) thumbnail first, then full image → final --lb-cover-ar follows full
    const c1 = makeComponent({ container: box, fullImg: full });
    c1._setCoverAspect({ target: thumb });
    assert.equal(box._props['--lb-cover-ar'], (800 / 600).toFixed(4));
    c1._lbFullLoaded = true;
    c1._setCoverAspect({ target: full });
    assert.equal(box._props['--lb-cover-ar'], expected);

    // (b) full already loaded → late thumbnail must not overwrite
    const box2 = makeContainer();
    const thumb2 = makeImg({ nw: 800, nh: 600, isFull: false, container: box2 });
    const full2 = makeImg({ nw: 600, nh: 900, isFull: true, container: box2 });
    const c2 = makeComponent({ container: box2, fullImg: full2, overrides: { _lbFullLoaded: true } });
    c2._setCoverAspect({ target: full2 });
    assert.equal(box2._props['--lb-cover-ar'], expected);
    c2._setCoverAspect({ target: thumb2 });
    assert.equal(box2._props['--lb-cover-ar'], expected);

    // (c) cache hit in _refreshLbFullBlurUp sets aspect from full image
    const box3 = makeContainer();
    const full3 = makeImg({ nw: 600, nh: 900, isFull: true, container: box3, complete: true });
    const c3 = makeComponent({ container: box3, fullImg: full3 });
    assert.equal(c3._lbFullLoaded, false);
    c3._refreshLbFullBlurUp();
    assert.equal(c3._lbFullLoaded, true);
    assert.equal(box3._props['--lb-cover-ar'], expected);
});
