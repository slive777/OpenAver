// TASK-199a-T1: shouldYieldVerticalWheel 真值表（影片固定文字區滾輪＝換片；其餘可捲區交還原生捲動）。
// harness 檔頭照 lb-full-error-pill.test.mjs；fake DOM 的 closest 真的評估模組內的 selector 字串。

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

const { shouldYieldVerticalWheel } = await import('../state-lightbox.js');

// 極小 selector 求值：逗號切多個選擇器；每個由 `.class` 與 `:not(.class)` token 組成。
function matches(node, selector) {
    return selector.split(',').some((sel) => {
        const tokens = sel.trim().match(/:not\(\.[\w-]+\)|\.[\w-]+/g) || [];
        return tokens.length > 0 && tokens.every((tok) => (tok.startsWith(':not(')
            ? !node.classes.includes(tok.slice(6, -1))
            : node.classes.includes(tok.slice(1))));
    });
}

function el(classes, parent = null, metrics = {}) {
    const node = { classes, parent, overflowY: 'visible', ...metrics };
    node.closest = (selector) => {
        for (let n = node; n; n = n.parent) if (matches(n, selector)) return n;
        return null;
    };
    return node;
}

// 模組裡以全域 getComputedStyle 讀 overflow-y；fake 讀節點上的 overflowY。
globalThis.getComputedStyle = (node) => ({ overflowY: node.overflowY });

test('shouldYieldVerticalWheel：只有「可捲且真的溢出」或女優／浮層才交還原生捲動', async (t) => {
    await t.test('影片 .lbx-meta 不溢出（閘內固定高度）→ false：滾輪換片', () => {
        const meta = el(['lightbox-metadata', 'lbx-meta'], null, { overflowY: 'auto', scrollHeight: 222, clientHeight: 222 });
        assert.equal(shouldYieldVerticalWheel(el(['lb-header'], meta)), false);
    });
    await t.test('女優 .lightbox-metadata（無 .lbx-meta）→ true：滾輪捲資料欄', () => {
        const meta = el(['lightbox-metadata'], null, { overflowY: 'auto', scrollHeight: 900, clientHeight: 300 });
        assert.equal(shouldYieldVerticalWheel(el(['lb-row'], meta)), true);
    });
    await t.test('影片 .lbx-meta 可捲且溢出（閘外矮視窗）→ true：滾輪捲文字', () => {
        const meta = el(['lightbox-metadata', 'lbx-meta'], null, { overflowY: 'auto', scrollHeight: 640, clientHeight: 180 });
        assert.equal(shouldYieldVerticalWheel(el(['lb-row'], meta)), true);
    });
    await t.test('.lbx-pop 後代 → true：滾輪捲浮層', () => {
        const pop = el(['lbx-pop'], el(['lightbox-content']));
        assert.equal(shouldYieldVerticalWheel(el(['lbx-pop-body'], pop)), true);
    });
    await t.test('影片 .lbx-meta 閘內 overflow:hidden 但內容溢出（舊內容被截）→ false：滾輪照樣換片', () => {
        const meta = el(['lightbox-metadata', 'lbx-meta'], null, { overflowY: 'hidden', scrollHeight: 700, clientHeight: 221 });
        assert.equal(shouldYieldVerticalWheel(el(['lb-row'], meta)), false);
    });
});
