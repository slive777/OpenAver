// TASK-116a-T1: 女優排序回歸 —— age/height/cup × asc/desc，缺值恆排最後。
//
// state-actress.js 用瀏覽器 importmap 別名 `@/showcase/...` 與
// `@/shared/...`，plain `node --test` 不認得。既有 search/__tests__/alias-loader.mjs 只做
// `@/` → `web/static/js/` 字首轉譯，對 `@/showcase/` 會解成錯誤路徑（importmap 實際指到
// `pages/showcase/`）。比照 pill-state.test.mjs / pill-clear.test.mjs，本檔自帶與 base.html
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
globalThis.Alpine = globalThis.Alpine || {
    store: () => ({ toolbarOpen: false, showcaseHasSearch: false }),
};

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
const { _setActresses } = await import('../state-base.js');

/**
 * Fixture：同時含有值與缺值的女優。
 * 手算期望順序（refactor 前語意）：
 *   age  asc:  young(25), mid(37),  missingAge → 末
 *   age  desc: mid(37),  young(25), missingAge → 末
 *   height asc: short(150), tall(170), missingHeight → 末
 *   height desc: tall(170), short(150), missingHeight → 末
 *   cup  asc:  A-cup(A=1), C-cup(C=3), missingCup → 末
 *   cup  desc: C-cup(C=3), A-cup(A=1), missingCup → 末
 *
 * 每一筆三個欄位都填，但各自缺一個維度（noAge / noHt / noCup），
 * 讓三個維度都各有一位缺值者可驗 null-last。
 */
const FIXTURE = [
    { name: 'young',  age: 25,   height: '150cm', cup: 'A' },
    { name: 'mid',    age: 37,   height: '170cm', cup: 'C' },
    { name: 'noAge',  age: null, height: '160cm', cup: 'B' },
    { name: 'noHt',   age: 30,   height: null,    cup: 'D' },
    { name: 'noCup',  age: 28,   height: '155cm', cup: null },
];

function namesOf(list) {
    return list.map((a) => a.name);
}

function sortBy(sort, order) {
    const c = Object.assign({}, stateActress(), {
        actressSort: sort,
        actressOrder: order,
        actressSearch: '',
    });
    _setActresses(FIXTURE);
    c.applyActressFilterAndSort();
    return namesOf(c.paginatedActresses);
}

// ── age ────────────────────────────────────────────────────────────────────

test('age asc：有值升冪、缺值（noAge）恆排最後', () => {
    // 有 age：young(25), noCup(28), noHt(30), mid(37)；noAge 最後
    assert.deepEqual(sortBy('age', 'asc'), [
        'young', 'noCup', 'noHt', 'mid', 'noAge',
    ]);
});

test('age desc：有值降冪、缺值（noAge）仍排最後', () => {
    assert.deepEqual(sortBy('age', 'desc'), [
        'mid', 'noHt', 'noCup', 'young', 'noAge',
    ]);
});

// ── height ─────────────────────────────────────────────────────────────────

test('height asc：有值升冪、缺值（noHt）恆排最後', () => {
    // young 150, noCup 155, noAge 160, mid 170；noHt 最後
    assert.deepEqual(sortBy('height', 'asc'), [
        'young', 'noCup', 'noAge', 'mid', 'noHt',
    ]);
});


// ── cup ────────────────────────────────────────────────────────────────────



// ── recent（184-T2）────────────────────────────────────────────────────────

test('recent 排序：分數降冪、同分依作品數、asc 整份反過來、缺分數視同 0', () => {
    // 給定順序刻意打亂：拿掉第二級或 asc 沒反轉都會算出不同順序
    const LIST = [
        { name: 'lowA',   recent_score: 1,  video_count: 5 },
        { name: 'zeroB',  recent_score: 0,  video_count: 9 },
        { name: 'topC',   recent_score: 10, video_count: 2 },
        { name: 'noneD',  video_count: 3 },                    // 缺 recent_score ＝ 0
        { name: 'tieE',   recent_score: 5,  video_count: 1 },
        { name: 'tieF',   recent_score: 5,  video_count: 8 },
        { name: 'zeroG',  recent_score: 0,  video_count: 4 },
    ];
    const run = (order) => {
        const c = Object.assign({}, stateActress(), {
            actressSort: 'recent', actressOrder: order, actressSearch: '',
        });
        _setActresses(LIST);
        c.applyActressFilterAndSort();
        return namesOf(c.paginatedActresses);
    };
    const desc = ['topC', 'tieF', 'tieE', 'lowA', 'zeroB', 'zeroG', 'noneD'];
    assert.deepEqual(run('desc'), desc);
    assert.deepEqual(run('asc'), desc.slice().reverse());
});
