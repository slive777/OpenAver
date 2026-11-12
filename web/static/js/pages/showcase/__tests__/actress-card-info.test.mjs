// TASK-124b-T1: _actressInfoTokens / _actressCardMiddle 恆回作品數 / infoVisible 持久化 / S 鍵 gate。
// TASK-124b-T4: _actressInfoTokens → _actressInfoParts（parts 物件 ＋ clickable）
//               ＋ _onActressCardMetadataClick（卡片路徑的 pill handler）。
//
// state-actress.js / state-base.js / state-lightbox.js 用瀏覽器 importmap 別名
// `@/showcase/...` 與 `@/shared/...`，plain `node --test` 不認得。比照
// card-shape-persist.test.mjs / presentation-wiring.test.mjs，本檔自帶與 base.html
// importmap 對齊的 resolve hook（不改共用 loader，FE-GUARD-11）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

// open-local.js → path-utils.js 在模組頂層寫 window.pathToDisplay；
// state-base.js 模組頂層讀 localStorage（清壞值）。比照既有 showcase 測試先 stub window。
globalThis.window = globalThis;
globalThis.window.t = (key) => key;

// 124b-T4：_onActressCardMetadataClick 會寫 Alpine.store('ui').toolbarOpen。
// 單一 mutable store（鏡射 actress-core-metadata.test.mjs:18-19）——每次 new 一個新物件
// 會讓寫入值丟失，斷言就永遠讀到初值。
const _uiStore = { toolbarOpen: false, showcaseHasSearch: false };
globalThis.Alpine = { store: () => _uiStore };

const IMPORTMAP = {
    '@/settings/': 'pages/settings/',
    '@/shared/': 'shared/',
    '@/components/': 'components/',
    '@/search/': 'pages/search/',
    '@/showcase/': 'pages/showcase/',
    '@/scanner/': 'pages/scanner/',
};
// 本檔：web/static/js/pages/showcase/__tests__/ → 上三層 = web/static/js/
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

const { stateActress } = await import('../state-actress.js');
const { stateBase, _setActressWorkCounts } = await import('../state-base.js');
const { stateLightbox } = await import('../state-lightbox.js');

// =====================================================================
// _actressInfoParts（124b-T4 取代 _actressInfoTokens）
// =====================================================================

const FULL_ACTRESS = {
    name: '滿格優',   // 199b-T4b：作品數改由 _setActressWorkCounts 以名字餵
    age: 25,
    height: '160cm',
    cup: 'C',
    bust: 88,
    waist: 58,
    hip: 88,
};

function partsOf(actress, isNarrow) {
    const c = Object.assign({}, stateActress(), { _isNarrow: isNarrow });
    return c._actressInfoParts(actress);
}

function keysOf(actress, isNarrow) {
    return partsOf(actress, isNarrow).map((p) => p.key);
}


function byKey(actress, isNarrow) {
    return Object.fromEntries(partsOf(actress, isNarrow).map((p) => [p.key, p]));
}

// ── 收留規則（CD-124b-13）──────────────────────────────────────────────


test('缺 height（null）→ 該 part 不出現，其餘不受影響', () => {
    // 162a：缺 cup（undefined）、缺 height（空字串）、三圍缺一格併入同一支（同一失敗原因：缺值不顯示殘缺欄）
    const cases = [
        [{ height: null }, ['count', 'age', 'cup', 'bwh']],
        [{ cup: undefined }, ['count', 'age', 'height', 'bwh']],
        [{ height: '' }, ['count', 'age', 'cup', 'bwh']],
        [{ bust: null }, ['count', 'age', 'height', 'cup']],
    ];
    _setActressWorkCounts(new Map([[FULL_ACTRESS.name, 12]]));
    try {
        for (const [override, expected] of cases) {
            assert.deepEqual(keysOf(Object.assign({}, FULL_ACTRESS, override), true), expected);
        }
    } finally {
        _setActressWorkCounts(null);
    }
});


// ── clickable（CD-124b-13：可點的三格 ＋ 恆不可點的兩格）──────────────


// ── fail-closed：值解析不出來就不可點，但文字仍在 ─────────────────────


// ── dim / value 傳原始欄位值，不是顯示字串 ────────────────────────────

test('dim/value：height 傳原始 \'160cm\'（單位由 _setActressPill 剝），不是 160', () => {
    // 162a：cup 原始 'C'、age 原始 25 併入同一支（同一失敗原因：pill 值為顯示字串）
    const m = byKey(FULL_ACTRESS, true);
    assert.equal(m.height.dim, 'height');
    assert.equal(m.height.value, '160cm');
    assert.equal(m.cup.dim, 'cup');
    assert.equal(m.cup.value, 'C');
    assert.notEqual(m.cup.value, m.cup.text, 'value 不得等於顯示字串');
    assert.equal(m.age.dim, 'age');
    assert.equal(m.age.value, 25);
});

// =====================================================================
// _onActressCardMetadataClick（124b-T4 / CD-124b-15）
// =====================================================================


// =====================================================================
// _actressCardMiddle
// =====================================================================


// =====================================================================
// infoVisible 持久化
// =====================================================================

function makeBaseComponent(overrides) {
    const c = stateBase.call({ $persist: (obj) => ({ as: () => obj }) });
    return Object.assign(c, overrides);
}

function stubWindow(opts) {
    const pathname = (opts && opts.pathname) || '/showcase';
    const search = (opts && opts.search) || '';
    globalThis.window.location = { pathname, search };
    globalThis.window.history = {
        replaceState() {},
    };
    globalThis.window.__SHOWCASE_CONFIG__ = (opts && opts.config) || {};
}

const RESTORE_CASES = [
    { input: true, expected: true, label: 'true → true' },
];

for (const { input, expected, label } of RESTORE_CASES) {
    test(`restoreState()：infoVisible ${label}`, () => {
        stubWindow({ search: '' });
        const persisted = {
            sort: 'date',
            order: 'desc',
            page: 1,
            search: '',
            mode: 'grid',
            cardShape: 'cover',
        };
        if (input !== undefined) persisted.infoVisible = input;
        const c = makeBaseComponent({ _persistedShowcase: persisted, infoVisible: !expected });
        c.restoreState();
        assert.equal(c.infoVisible, expected);
    });
}

// =====================================================================
// S 鍵 gate
// =====================================================================

function makeKeydownComponent(overrides) {
    const base = stateBase.call({ $persist: (obj) => ({ as: () => obj }) });
    const c = Object.assign({}, base, stateLightbox(), {
        mode: 'grid',
        showFavoriteActresses: false,
        infoVisible: false,
        _persistedShowcase: { infoVisible: false },
        // handleKeydown 在第 6 段之前的 guard 全部關死，讓按鍵落到第 6 段
        _pillEditor: null,
        _releaseEditor: null,
        similarModeOpen: false,
        similarModeMobileOpen: false,
        removeActressModalOpen: false,
        actressAddPanelOpen: false,
        _pickerOpen: false,
        rescrapeOpen: false,
        deleteVideoModalOpen: false,
        sampleGalleryOpen: false,
        lightboxOpen: false,
    }, overrides);
    // toggleInfo 定義在 state-base，Object.assign 展開的是自身屬性快照，
    // 但物件方法皆為一般函式屬性，assign 後仍指向同一份 this-bound-free 實作，
    // 呼叫時 this 綁定到 c 本身，行為與原本一致。
    return c;
}

function pressS(c) {
    c.handleKeydown({
        key: 'S',
        target: { tagName: 'BODY' },
        preventDefault() {},
        stopPropagation() {},
        ctrlKey: false,
        altKey: false,
        shiftKey: false,
        metaKey: false,
    });
}


// T1 review 補測：gate 放寬成 `|| this.showFavoriteActresses` 之後，「女優燈箱開著時
// 按 S 不得切換資訊區」靠的是 handleKeydown 第 5 段（lightboxOpen 分支，
// state-lightbox.js:2476-2494）在第 6 段之前 return —— 保護來自**順序**而非旗標，
// 所以用測試把那個順序釘住（排序優先於旗標守衛）。
test('S 鍵：女優燈箱開啟時（lightboxOpen + currentLightboxActress + 女優模式）不得觸發 toggleInfo', () => {
    // 162a：影片燈箱開啟時同樣不得切換併入同一支
    const cases = [
        { mode: 'table', showFavoriteActresses: true, lightboxOpen: true, currentLightboxActress: { name: 'x' } },
        { mode: 'grid', showFavoriteActresses: false, lightboxOpen: true, currentLightboxActress: null },
    ];
    for (const over of cases) {
        const c = makeKeydownComponent(over);
        const before = c.infoVisible;
        pressS(c);
        assert.equal(c.infoVisible, before);
    }
});
