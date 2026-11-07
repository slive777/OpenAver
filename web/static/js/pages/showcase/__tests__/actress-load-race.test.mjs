// TASK-149b-T3 ⓪′: loadActresses() 並行 dedup／重試／三個失敗出口清理契約（CD-149b-2）
//
// 修法背景：舊版 loadActresses() 每次呼叫都無條件發一次 fetch，且三個失敗出口各自複製貼上
// 清理邏輯、卻沒有清空 _lbActorAges（尚不存在的欄位）也沒有明確呼叫 _setActressesLoaded(false)。
// 149b-T3 把它改成：① module-level in-flight promise dedup ② _setActressesLoaded(true) 從
// finally 移到成功路徑 ③ 三個失敗出口統一清理 + 明確 _setActressesLoaded(false) + 清空
// this._lbActorAges。本檔驗這三件事的 runtime 語意（node:test，非 CDP）。
//
// 範本：actress-add-panel.test.mjs（FE-GUARD-11：window stub + importmap resolve hook）

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

// open-local.js → path-utils.js 在模組頂層寫 window.pathToDisplay；
// state-base.js 模組頂層讀 localStorage。FE-GUARD-11：第一段就要有。
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
const { stateVideos } = await import('../state-videos.js');
// 117-T5：_actresses / _filteredActresses 是 module-level 共享陣列（測試間互相污染）——
// 每個測試前都要重置。_actressesLoaded 走 setter；讀取用 live binding（同一模組實例）。
const stateBase = await import('../state-base.js');
const { _actresses, _filteredActresses, _setFilteredVideos } = stateBase;
// init() factory 本體（與命名空間物件 stateBase 撞名，另取別名）——
// 頂層 `this.$persist(...)` 需要綁定一個提供 $persist 的假 this（照抄 pill-match.test.mjs）。
const stateBaseFactory = stateBase.stateBase;

function resetActresses() {
    _actresses.length = 0;
    _filteredActresses.length = 0;
}

/** 元件不合併 stateLightbox()（8+ 個既有測試檔的既有慣例，CD-149b-6：state-actress.js 的
 *  刷新點必須用 `?.`，不能裸呼叫，這裡故意不提供 _refreshLbActorAges 來驗證這一點）。
 *  $nextTick 給 no-op（不呼叫傳入的 fn）：production 進場動畫分支需要 requestAnimationFrame
 *  （Node 沒有）與 _getActiveGrid()（屬 state-videos.js，本測試不合併），與本檔驗證目標無關。
 *  _lbActorAges 預先塞一個「上一次成功算出的舊值」，驗證失敗出口會把它清空。 */
function makeComponent(overrides = {}) {
    return Object.assign({}, stateActress(), {
        showToast() {},
        showFavoriteActresses: false,
        $nextTick() {},
        _lbActorAges: { stale: 99 },
        ...overrides,
    });
}

// production loadActresses() 成功路徑會 await _loadAliasMap()（獨立 fetch('/api/actress-aliases')，
// state-base.js 冪等快取在 _aliasMapLoaded，跨測試殘留）。這支 mock 只序列化／計數 '/api/actresses'
// 那個目標端點，alias-map 端點另給一個固定的良性回應，不污染本檔要驗的計數斷言。
function mockFetchSequence(handlers) {
    const prev = globalThis.fetch;
    let i = 0;
    const calls = [];
    globalThis.fetch = async (url, opts) => {
        if (url === '/api/actress-aliases') {
            return { ok: true, status: 200, json: async () => ({ groups: [] }) };
        }
        calls.push([url, opts]);
        const h = handlers[Math.min(i, handlers.length - 1)];
        i += 1;
        return h(url, opts);
    };
    return { restore() { globalThis.fetch = prev; }, calls };
}

function okResp(actresses) {
    const list = actresses || [];
    return {
        ok: true,
        status: 200,
        json: async () => ({ success: true, actresses: list, total: list.length }),
    };
}
function notOkResp() {
    return { ok: false, status: 500, json: async () => ({}) };
}

// ── 並行 dedup ──────────────────────────────────────────────────────────


// ── settle 後清回 null，下一次呼叫要真的重試 ──────────────────

test('loadActresses retries with a second fetch after the in-flight promise settles on failure', async () => {
    resetActresses();
    const mock = mockFetchSequence([
        () => notOkResp(),
        () => okResp([{ name: 'B', birth: '1990-01-01' }]),
    ]);
    try {
        const c = makeComponent();
        await c.loadActresses(); // 第一次：失敗並 settle
        await c.loadActresses(); // in-flight promise 已在 finally 清回 null → 必須是新的 fetch
        assert.equal(mock.calls.length, 2, '第二次呼叫必須產生第二次 fetch，不能卡在已 settle 的舊 promise');
        assert.equal(_actresses.length, 1);
        assert.equal(_actresses[0].name, 'B');
    } finally {
        mock.restore();
    }
});

// ── 邊界條件 3：三個失敗出口各自的清理契約 ────────────────────────────────


// ── 邊界條件 4（Codex 149b implementation review P2）：init() 循序時序 ──────
//
// :362 的 hero-card 分支（_reconcileHeroCard → _checkPreciseActressMatch）可能在
// fetchVideos()／alias map 幾個 await 之間先行 settle 成功；若 init() 在 :374 仍
// 無條件呼叫第二次 loadActresses()，第二次若暫時失敗，統一清理會把第一次已成功
// 載入的資料清空。這裡走真正的 stateBase().init()（合併 stateVideos()/stateActress()），
// 不用推理描述時序——用 fetchVideos() stub 主動讓出足夠的 microtask，逼 hero-card
// 分支的第一次 loadActresses() 真的完整 settle（含 module-level in-flight promise
// 清空），複現 Codex 描述的「較小的女優請求先完成」情境。

function makeFetchMockForInit(actressesResponses) {
    const orig = globalThis.fetch;
    const calls = { actresses: 0 };
    globalThis.fetch = async (url) => {
        if (url === '/api/actresses') {
            const idx = calls.actresses;
            calls.actresses += 1;
            const handler = actressesResponses[Math.min(idx, actressesResponses.length - 1)];
            return handler();
        }
        if (url === '/api/actress-aliases') return { ok: true, json: async () => ({ groups: [] }) };
        if (url === '/api/tag-aliases') return { ok: true, json: async () => ({ groups: [] }) };
        if (url === '/api/cover-badges/manifest') return { ok: true, json: async () => [] };
        // 其餘皆 fire-and-forget（/api/showcase/source-status、/api/similar/warmup）：
        // 給良性回應，不污染本檔要驗的 '/api/actresses' 呼叫次數。
        return { ok: true, json: async () => ({}) };
    };
    return { calls, restore() { globalThis.fetch = orig; } };
}

// 合併三個 factory，比照 pill-match.test.mjs 的 cold/warm harness 建構真正的 init()。
function makeInitComponent(overrides = {}) {
    const base = stateBaseFactory.call({ $persist: (obj) => ({ as: () => obj }) });
    return Object.assign({}, base, stateVideos(), stateActress(), {
        restoreState() {},
        _hsInit: () => Promise.resolve(),   // 195b-T4：init() 呼叫分片的 _hsInit（本 harness 不 merge 該分片）
        fetchVideos: async () => {},
        applyFilterAndSort() {},
        updatePagination() {},
        $nextTick() {},
        $watch() {},
        showToast() {},
        ...overrides,
    });
}

async function withInitGlobals(fn) {
    const origRegisterPage = globalThis.window.__registerPage;
    const origAddEventListener = globalThis.window.addEventListener;
    globalThis.window.__registerPage = () => {};
    globalThis.window.addEventListener = () => {};
    try {
        return await fn();
    } finally {
        globalThis.window.__registerPage = origRegisterPage;
        globalThis.window.addEventListener = origAddEventListener;
    }
}

test('P2（Codex 149b review）：hero-card 首次 loadActresses 成功 settle 後，init() 不得再無條件發第二次請求去清掉第一次已成功載入的資料', async () => {
    resetActresses();
    stateBase._setActressesLoaded(false);
    const mock = makeFetchMockForInit([
        () => okResp([{ name: 'HeroActress', birth: '1990-01-01' }]),  // 第一次：hero-card 分支，成功
        () => notOkResp(),                                             // 第二次：若無條件重發，模擬暫時失敗
    ]);
    try {
        await withInitGlobals(async () => {
            const c = makeInitComponent({
                search: 'SampleActress',   // pills=[]（0 枚）→ _shouldShowHeroCard() 走無 pill 分支，文字非空即觸發
                fetchVideos: async () => {
                    // 逼 hero-card 分支的第一次 loadActresses() 完整 settle
                    // （含 module-level in-flight promise 清空），才讓出控制權。
                    for (let i = 0; i < 200 && !stateBase._actressesLoaded; i++) await Promise.resolve();
                    for (let i = 0; i < 50; i++) await Promise.resolve();
                },
            });
            await c.init();
            // init() 對第二次 loadActresses() 是 fire-and-forget，讓其在背景跑完再驗證。
            await new Promise((resolve) => setTimeout(resolve, 0));
        });

        assert.equal(_actresses.length, 1, '第二次失敗不該清掉第一次已成功載入的有效資料');
        assert.equal(_actresses[0].name, 'HeroActress');
    } finally {
        mock.restore();
    }
});


// ── CD-155a-4：卡片發行時年齡延遲補算與失敗清空 ───────────────────────────

function makeVideosActressComponent(overrides = {}) {
    return Object.assign({}, stateVideos(), stateActress(), {
        showToast() {},
        showFavoriteActresses: false,
        $nextTick() {},
        mode: 'grid',
        perPage: 120,
        page: 1,
        ...overrides,
    });
}

test('收藏清單延遲到位後，已在牆上的卡片經 paginatedVideos 補上年齡', async () => {
    resetActresses();
    stateBase._setActressesLoaded(false);
    const v1 = { id: 1, actresses: '明里つむぎ', release_date: '2020-06-15', duration: 60 };
    _setFilteredVideos([v1]);

    const c = makeVideosActressComponent();
    c.updatePagination();

    // 模擬 Proxy 元素替身（身分與 _filteredVideos 原始物件不同）
    const proxyElements = c.paginatedVideos.map(v => ({ ...v }));
    c.paginatedVideos = proxyElements;

    const mock = mockFetchSequence([
        () => okResp([{ name: '明里つむぎ', birth: '1990-06-15' }]),
    ]);
    try {
        await c.loadActresses();
        // 斷言：陣列參照不變
        assert.strictEqual(c.paginatedVideos, proxyElements, 'paginatedVideos 陣列參照不得被替換');
        // 斷言：替身元素寫入年齡
        assert.deepStrictEqual(c.paginatedVideos[0]._cardActorAges, { '明里つむぎ': 30 });
    } finally {
        mock.restore();
    }
});


