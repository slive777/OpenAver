// TASK-116a-T3: 燈箱三格可點——_actressCoreMetadataParts() 取代 _actressCoreMetadata()（CD-116a-6）。
//
// state-actress.js 用瀏覽器 importmap 別名；plain node --test 不認得。
// 比照 actress-pill-state.test.mjs，本檔自帶 resolve hook（FE-GUARD-11）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

// open-local.js → path-utils.js 在模組頂層寫 window.pathToDisplay；
// state-base.js 模組頂層讀 localStorage（清壞值）。
globalThis.window = globalThis;
// identity mock：測試只驗證「呼叫了哪個 key」與「join 順序/分隔符」，不驗真正翻譯字串
globalThis.window.t = (key) => key;
// 單一 mutable store：116b-T4 的 toolbarOpen 斷言要讀到寫入結果（每次 new 會丟值）
const _uiStore = { toolbarOpen: false, showcaseHasSearch: false };
globalThis.Alpine = {
    store: () => _uiStore,
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
const { _setActressWorkCounts } = await import('../state-base.js');


/**
 * 合併 harness——本檔只需要 stateActress()（_actressCoreMetadataParts /
 * _onActressMetadataClick / _actressPillDisplayText 都定義在其上），
 * closeLightbox/addActressPill 用 spy 取代（前者屬 state-lightbox.js，
 * 依卡片「不准碰」清單本檔不 import 它）。
 */
function makeComponent(overrides) {
    const actress = stateActress();
    const calls = [];
    const c = Object.assign({}, actress, {
        currentLightboxActress: null,
        actressLightboxSource: 'grid',
        closeLightbox() { calls.push(['closeLightbox']); },
        addActressPill(dim, value) { calls.push(['addActressPill', dim, value]); },
    }, overrides);
    c.__calls = calls;
    return c;
}

// ── 舊版演算法手抄對照（不 import 舊函式，它已被整段取代刪除）──────────────
// 逐字抄自 T3 之前的 state-actress.js:499-511（TASK-116a-T3.md B 項已核對）。
// 199b-T4b：作品數來源改為 _setActressWorkCounts 餵的 Map（與新函式取同一個數字來源）。
const WORK_COUNTS = new Map([['滿格優', 12], ['缺身高', 5]]);
function legacyActressCoreMetadata(a) {
    if (!a) return '';
    const parts = [];
    if (WORK_COUNTS.has(a.name)) {
        parts.push(WORK_COUNTS.get(a.name) + window.t('showcase.unit.films'));
    }
    if (a.age) parts.push(a.age + window.t('search.unit.age'));
    if (a.birth) parts.push(a.birth);
    if (a.height) parts.push(a.height);
    if (a.cup) parts.push(a.cup + window.t('search.unit.cup'));
    if (a.bust && a.waist && a.hip) parts.push(a.bust + '-' + a.waist + '-' + a.hip);
    return parts.join(' · ');
}

function joinParts(parts) {
    return parts.map((p) => p.text).join(' · ');
}

// ── AC1：六格白名單，grid 路徑逐格驗證（不是抽樣）──────────────────────────

const FULL_ACTRESS = {
    name: '滿格優',
    age: 28,
    birth: '1997-01-01',
    height: '160cm',
    cup: 'C',
    bust: 88, waist: 58, hip: 90,
};

test('grid 路徑：六格逐一驗證 clickable 白名單（作品數/生日/三圍恆 false，年齡/身高/罩杯 true）', () => {
    const c = makeComponent({ currentLightboxActress: FULL_ACTRESS, actressLightboxSource: 'grid' });
    _setActressWorkCounts(WORK_COUNTS);
    let parts;
    try { parts = c._actressCoreMetadataParts(); } finally { _setActressWorkCounts(null); }
    const byKey = Object.fromEntries(parts.map((p) => [p.key, p]));

    assert.equal(parts.length, 6, `預期 6 格，實際 ${parts.length}`);

    assert.equal(byKey.count.clickable, false, '作品數不可點');
    assert.ok(!('dim' in byKey.count), '作品數不應帶 dim');

    assert.equal(byKey.age.clickable, true, '年齡（grid 路徑）應可點');
    assert.equal(byKey.age.dim, 'age');
    assert.equal(byKey.age.value, FULL_ACTRESS.age);

    assert.equal(byKey.birth.clickable, false, '生日不可點');
    assert.ok(!('dim' in byKey.birth), '生日不應帶 dim');

    assert.equal(byKey.height.clickable, true, '身高（grid 路徑）應可點');
    assert.equal(byKey.height.dim, 'height');
    assert.equal(byKey.height.value, FULL_ACTRESS.height);

    assert.equal(byKey.cup.clickable, true, '罩杯（grid 路徑）應可點');
    assert.equal(byKey.cup.dim, 'cup');
    assert.equal(byKey.cup.value, FULL_ACTRESS.cup);

    assert.equal(byKey.bwh.clickable, false, '三圍不可點');
    assert.ok(!('dim' in byKey.bwh), '三圍不應帶 dim');
});

// ── AC2：hero 路徑，全部 part 皆不可點 ──────────────────────────────────────


// ── 116b review：extractor 解不出值 → clickable false；正常值仍 true ───────


// ── 呼叫序列：closeLightbox() 先於 addActressPill(dim, value) ──────────────

test('_onActressMetadataClick：先 closeLightbox() 再 addActressPill(dim, value)（FE-ALPINE-04）', () => {
    const c = makeComponent({ currentLightboxActress: FULL_ACTRESS, actressLightboxSource: 'grid' });
    c._onActressMetadataClick('height', '160cm');
    assert.deepEqual(c.__calls, [
        ['closeLightbox'],
        ['addActressPill', 'height', '160cm'],
    ]);
});


// ── 視覺零回歸：多組缺值組合下，join 輸出與舊版逐字相同（至少 5 組）────────

const REGRESSION_FIXTURES = [
    { name: '缺身高', actress: { name: '缺身高', age: 30, birth: '1995-05-05', height: '', cup: 'D', bust: 85, waist: 60, hip: 88 } },
];

for (const { name, actress } of REGRESSION_FIXTURES) {
    test(`視覺零回歸（${name}）：_actressCoreMetadataParts() join 與舊版逐字相同`, () => {
        const c = makeComponent({ currentLightboxActress: actress, actressLightboxSource: 'grid' });
        _setActressWorkCounts(WORK_COUNTS);
        let parts;
        try { parts = c._actressCoreMetadataParts(); } finally { _setActressWorkCounts(null); }
        assert.equal(joinParts(parts), legacyActressCoreMetadata(actress));
    });
}


// ── _actressPillDisplayText（CD-116b-11 全表 11 格）─────────────────────────


// ── `.lb-actress-core-value` 是原生 <button type="button">（機械證明，非 <span>）──

