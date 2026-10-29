// TASK-184-T2: 女優排序「最近常收」一次性切換（actressSortVersion 旗標）。
// loader / stub 樣板抄 card-shape-persist.test.mjs（自帶 importmap resolve hook）。

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

const { stateBase } = await import('../state-base.js');

function restoreWith(saved) {
    globalThis.window.location = { pathname: '/showcase', search: '' };
    globalThis.window.history = { replaceState() {} };
    globalThis.window.__SHOWCASE_CONFIG__ = {};
    const c = stateBase.call({ $persist: (obj) => ({ as: () => obj }) });
    c._persistedShowcase = Object.assign({}, c._persistedShowcase, saved);
    c.restoreState();
    return c;
}

test('一次性切換：舊存檔切到 recent、旗標 1 原樣還原、空存檔為 recent', () => {
    // 舊存檔（無旗標）：使用者原本選作品數/asc → 切到 recent/desc，且當下同步寫回
    const old = restoreWith({ actressSort: 'video_count', actressOrder: 'asc' });
    assert.equal(old.actressSort, 'recent');
    assert.equal(old.actressOrder, 'desc');
    assert.equal(old._persistedShowcase.actressSort, 'recent');
    assert.equal(old._persistedShowcase.actressOrder, 'desc');
    assert.equal(old._persistedShowcase.actressSortVersion, 1);

    // 旗標 1：使用者自己選的值原樣還原，不再被切回
    const kept = restoreWith({ actressSort: 'video_count', actressOrder: 'asc', actressSortVersion: 1 });
    assert.equal(kept.actressSort, 'video_count');
    assert.equal(kept.actressOrder, 'asc');
    assert.equal(kept._persistedShowcase.actressSortVersion, 1);

    // 空存檔（新使用者）
    const fresh = restoreWith({ actressSort: null, actressOrder: null });
    assert.equal(fresh.actressSort, 'recent');
    assert.equal(fresh.actressOrder, 'desc');
});
