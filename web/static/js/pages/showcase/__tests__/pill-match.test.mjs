// TASK-115-T2: pill 精準比對層契約。
//
// 分兩部分：
// Part A — buildPillPredicate 純函式（直接 import shared/pill-filter.js，零 DOM，
//          不需 resolve hook），涵蓋六個維度、alias 展開、正規化順序、fail-closed、
//          null 欄位、空 pill 列表，以及 CD-7 的兩條 oracle。
// Part B — applyFilterAndSort() 接線測試（比照 T1 pill-state.test.mjs 的
//          resolve hook + globalThis.window stub，import 真正的 state-videos.js /
//          state-base.js），涵蓋 pill+自由文字 AND、filteredCount 不變式、
//          自由文字既有行為零回歸（DoD ②）。
//
// state-videos.js 用瀏覽器 importmap 別名 `@/showcase/...` 與 `@/shared/...`，
// plain `node --test` 不認得。既有 search/__tests__/alias-loader.mjs 只做
// `@/` → `web/static/js/` 字首轉譯，對 `@/showcase/` 會解成錯誤路徑
// （importmap 實際指到 `pages/showcase/`）。比照 settings/save-access-auth.test.mjs /
// T1 的 pill-state.test.mjs，本檔自帶與 base.html importmap 對齊的 resolve hook
// （不改共用 loader，見 gotcha FE-GUARD-11）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

// ===== Part A の純函式 import（無 window 依賴，可靜態 import） =====
import { buildPillPredicate } from '../../../shared/pill-filter.js';

// ===== Part B 的 resolve hook + window stub（FE-GUARD-11，照抄 T1 pill-state.test.mjs） =====

// open-local.js → path-utils.js 在模組頂層寫 window.pathToDisplay；
// 比照 pill-state.test.mjs 先 stub window，在任何 state-*.js import 之前完成。
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

const { stateVideos } = await import('../state-videos.js');
const stateBaseMod = await import('../state-base.js');
const {
    _setVideos,
    _filteredVideos,
    _loadAliasMap,
    _loadTagAliasMap,
    stateBase,
} = stateBaseMod;

// ===== Part B 用的 alias map 種子資料：以 stub fetch 呼叫真正的 _loadAliasMap/_loadTagAliasMap =====
// _nameToGroup/_tagToGroup 是 state-base.js 的模組層級變數，_loadAliasMap()/_loadTagAliasMap()
// 內部整個重新指派（非 mutate），test 端 import binding 是 live binding，呼叫後即可反映新值。
// applyFilterAndSort() 內讀的是同一個 module singleton，故這裡種子的資料對 Part B 的自由文字
// alias 展開回歸測試（DoD ②）與 pill 層皆生效。
// 頂層 await（非 async IIFE 的 dangling promise）：確保在任何 test() 執行之前，
// alias map 已用種子資料填好——node:test 的 test() 只是註冊，真正執行在模組
// 評估完成之後，但若用不 await 的 IIFE，填表與模組評估完成之間仍有 race window。
{
    const ORIGINAL_FETCH = globalThis.fetch;
    globalThis.fetch = async (url) => {
        if (url === '/api/actress-aliases') {
            return {
                ok: true,
                json: async () => ({ groups: [{ primary_name: 'AliasActressA', aliases: ['AliasActressB'] }] }),
            };
        }
        if (url === '/api/tag-aliases') {
            return {
                ok: true,
                json: async () => ({ groups: [{ primary_name: '女僕', aliases: ['メイド'] }] }),
            };
        }
        // 121b-T2：cover-badge manifest 端點。這個 seed 區塊只呼叫 _loadAliasMap()/
        // _loadTagAliasMap()，目前不會打到這個 URL——留著是 fail-safe：日後若有人在此
        // seed manifest（或既有 loader 多打一次 fetch），才不會撞上下面那行 throw。
        // 刻意回空陣列：seed 階段不消耗 _coverBadgeManifestLoaded 冪等 guard，
        // 讓下面各 loader 測試自己決定要載入什麼。
        if (url === '/api/cover-badges/manifest') {
            return { ok: true, json: async () => [] };
        }
        throw new Error('pill-match.test.mjs: unexpected fetch url ' + url);
    };
    await _loadAliasMap();
    await _loadTagAliasMap();
    globalThis.fetch = ORIGINAL_FETCH;
}

function makeComponent(overrides) {
    return Object.assign({}, stateVideos(), {
        pills: [],
        search: '',
        sort: 'title',
        order: 'asc',
        page: 1,
        perPage: 0,
        mode: 'list',
        filteredCount: 0,
    }, overrides);
}

// =====================================================================
// Part A — buildPillPredicate 純函式
// =====================================================================

test('spec AC11：片商 pill S1 → 標題含 "S1" 但 maker 不等於 S1 的影片不在結果中', () => {
    const predicate = buildPillPredicate([{ dim: 'maker', value: 'S1' }], {}, {});
    assert.equal(predicate({ title: 'S1 NO.1 STYLE 精選', maker: 'Some Other Maker' }), false);
    assert.equal(predicate({ title: 'random', maker: 'S1' }), true);
});

test('spec AC12：標籤 pill 痴女 → 只有 tags 含 痴女系（不含 痴女）的影片不 match', () => {
    const predicate = buildPillPredicate([{ dim: 'tag', value: '痴女' }], {}, {});
    assert.equal(predicate({ tags: '痴女系' }), false);
    assert.equal(predicate({ tags: '痴女, 中出' }), true);
});

test('alias 正向命中：pill 值為別名 A，影片 actresses 含同 group 的別名 B（A≠B）→ match', () => {
    const nameToGroup = { 'a': ['A', 'B'] };
    const predicate = buildPillPredicate([{ dim: 'actress', value: 'A' }], nameToGroup, {});
    assert.equal(predicate({ actresses: 'B' }), true);
});


test('"A, B" 形式的 actresses 欄位，pill 值 B 命中（trim 驗證，D4）', () => {
    const predicate = buildPillPredicate([{ dim: 'actress', value: 'B' }], {}, {});
    // 半形逗號＋空白、全形逗號（D4 normalize-then-split 順序）兩種欄位字面
    for (const field of ['A, B', 'A，B']) {
        assert.equal(predicate({ actresses: field }), true, field);
    }
});

test('user_tags 參與：tags 不含 X、user_tags 含 X → tag pill X match 該影片（D7 反轉）', () => {
    // 這裡曾經鎖 user_tags 不參與的舊行為（spec-115 §4.3），121b 刻意行為升級
    const predicate = buildPillPredicate([{ dim: 'tag', value: 'X' }], {}, {});
    assert.equal(predicate({ tags: 'Y', user_tags: ['X'] }), true);
});


test('TASK-124a-T1：release pill 與既有維度混用取交集（AND）', () => {
    const predicate = buildPillPredicate(
        [{ dim: 'release', op: '=', value: '2024-09' }, { dim: 'maker', value: 'S1' }],
        {},
        {},
    );
    assert.equal(predicate({ release_date: '2024-09-09', maker: 'S1' }), true);
    assert.equal(predicate({ release_date: '2024-09-09', maker: 'Other' }), false);
    assert.equal(predicate({ release_date: '2024-08-01', maker: 'S1' }), false);
});


test('TASK-124a-T1：release pill range 命中／不命中邊界（含端點）', () => {
    const predicate = buildPillPredicate(
        [{ dim: 'release', op: 'range', value: '2023', value2: '2024-06' }],
        {},
        {},
    );
    assert.equal(predicate({ release_date: '2023-01-01' }), true);
    assert.equal(predicate({ release_date: '2024-06-30' }), true);
    assert.equal(predicate({ release_date: '2022-12-31' }), false);
    assert.equal(predicate({ release_date: '2024-07-01' }), false);
});

// =====================================================================
// Part B — 透過真正的 applyFilterAndSort() 接線測試
// =====================================================================

test('pill 與自由文字同時作用：一枚片商 pill ＋ 自由文字關鍵字 → 結果同時滿足兩者（AND，CD-6）', () => {
    _setVideos([
        { title: 'Alpha', maker: 'Moodyz', tags: '', actresses: '', number: 'ABC-001' },
        { title: 'Beta', maker: 'Moodyz', tags: '', actresses: '', number: 'ABC-002' },
        { title: 'Alpha Extra', maker: 'S1', tags: '', actresses: '', number: 'XYZ-003' },
    ]);
    const c = makeComponent({
        pills: [{ dim: 'maker', value: 'Moodyz' }],
        search: 'alpha',
    });
    c.applyFilterAndSort(true);
    assert.equal(_filteredVideos.length, 1);
    assert.equal(_filteredVideos[0].title, 'Alpha');
});


test('自由文字回歸（DoD ②）：番號模糊比對（ABC-123 打 abc123 命中），零 pill', () => {
    _setVideos([{ title: 'X', number: 'ABC-123', maker: '', tags: '', actresses: '' }]);
    const c = makeComponent({ search: 'abc123' });
    c.applyFilterAndSort(true);
    assert.equal(_filteredVideos.length, 1);
});


test('自由文字回歸（DoD ②）：女優 alias 展開，零 pill', () => {
    _setVideos([{ title: 'Z', maker: '', tags: '', actresses: 'AliasActressB', number: 'A-3' }]);
    const c = makeComponent({ search: 'aliasactressa' });
    c.applyFilterAndSort(true);
    assert.equal(_filteredVideos.length, 1);
});

test('自由文字回歸（DoD ②）：tag alias 展開，零 pill', () => {
    _setVideos([{ title: 'W', maker: '', tags: 'メイド', actresses: '', number: 'A-4' }]);
    const c = makeComponent({ search: '女僕' });
    c.applyFilterAndSort(true);
    assert.equal(_filteredVideos.length, 1);
});

// =====================================================================
// TASK-121b-T3 — B1／B4 端到端（真正的 applyFilterAndSort 接線）
// =====================================================================
//
// 假設（測試順序敏感）：本區塊註冊在 Part B、早於檔尾 121b-T2 的
// CoverBadgeManifest 測試。跑到這裡時：
//   - `_tagToGroup` 只有頂層 seed 的 女僕/メイド（不得覆寫）
//   - `_coverBadgeManifestLoaded` 仍為 false
// 因此就地改屬性併入短名對，不呼叫 `_loadCoverBadgeManifest()`——
// 若改走 loader 會吃掉冪等 guard，T2 cold/warm 的 init() 就變成 no-op。

test('B1 端到端：燈箱手貼 user_tags 中字 → 瀏覽頁標籤篩 中文字幕 命中', () => {
    // 就地 seed：T2 併入 manifest 短名對之後的狀態（中字 ↔ 中文字幕 同組）。
    // 先把「這兩個 key 在我寫入前是空的」這個隱含假設變成可執行斷言——下面的 finally
    // 是無條件 delete，若哪天有人把本區塊搬到已經載入過 manifest 的測試之後，
    // delete 會砍掉別人載入的真值而不是還原，這條斷言會先一步紅給你看。
    assert.equal(stateBaseMod._tagToGroup['中文字幕'], undefined, '本區塊必須是第一個寫入這兩個 key 的測試');
    assert.equal(stateBaseMod._tagToGroup['中字'], undefined, '本區塊必須是第一個寫入這兩個 key 的測試');
    const b1ShortPair = ['中文字幕', '中字'];
    stateBaseMod._tagToGroup['中文字幕'] = b1ShortPair;
    stateBaseMod._tagToGroup['中字'] = b1ShortPair;

    // ⚠ 用完必須清掉（Opus 復驗抓到）：這兩個 key 若留在共享 _tagToGroup 裡，
    // 檔尾 121b-T2 的 cold/warm 測試就會在 init() 根本沒合併 manifest 的情況下也綠
    // ——實測：拿掉 init() 內那行 await 時，原本轉紅的 cold/warm 會退化成綠，
    // 只剩字面錨點那條抓得到。清掉才維持「測試順序無關」。
    try {
        _setVideos([
            { number: 'B1-HAND', title: 'HandTagged', maker: '', tags: '', actresses: '', user_tags: ['中字'] },
            { number: 'B1-MISS', title: 'NoTags', maker: '', tags: '', actresses: '', user_tags: [] },
            { number: 'B1-OTHER', title: 'Unrelated', maker: '', tags: '痴女', actresses: '', user_tags: ['重看'] },
        ]);
        const c = makeComponent({ pills: [{ dim: 'tag', value: '中文字幕' }] });
        c.applyFilterAndSort(true);
        const numbers = _filteredVideos.map((v) => v.number);
        assert.ok(numbers.includes('B1-HAND'), '手貼 中字 的片必須命中 中文字幕 pill');
        assert.ok(!numbers.includes('B1-MISS'), '無標籤對照片不得命中');
        assert.ok(!numbers.includes('B1-OTHER'), '無關標籤對照片不得命中');
        assert.equal(numbers.length, 1);
        assert.equal(_filteredVideos[0].number, 'B1-HAND');
    } finally {
        delete stateBaseMod._tagToGroup['中文字幕'];
        delete stateBaseMod._tagToGroup['中字'];
    }
});


// =====================================================================
// TASK-121b-T2 — CoverBadgeManifest / mergeAliasPair
// =====================================================================
//
// 冪等 guard `_coverBadgeManifestLoaded` 是 module-level 的：一旦某條測試把它
// 設為 true，同 module instance 後續再呼叫 loader 就是 no-op。失敗分支必須能
// 在成功分支之前真正跑到 catch，而 cold/warm 又要走 shared module 的 init()。
// 因此 loader 的成功／失敗／空陣列測試用 query-string 獨立 instance（不依賴
// 重複呼叫 shared loader）；cold/warm 才打 shared 的 init()。

const COVER_BADGE_MANIFEST_FIVE = [
    { id: 'zh-sub', canonical_tag: '中文字幕', display_name: '中字', match_aliases: ['中文字幕', '中字', '字幕'], display_order: 1, i18n_key: 'cover.zh_sub' },
    { id: 'uncen-crack', canonical_tag: '無碼破解', display_name: '破解', match_aliases: ['無碼破解', '破解', '克破', 'AI'], display_order: 2, i18n_key: 'cover.crack' },
    { id: 'uncen-leak', canonical_tag: '無碼流出', display_name: '流出', match_aliases: ['無碼流出', '流出', 'leak'], display_order: 3, i18n_key: 'cover.leak' },
    { id: '4k', canonical_tag: '4K', display_name: '4K', match_aliases: ['4K'], display_order: 4, i18n_key: 'cover.4k' },
    { id: 'vr', canonical_tag: 'VR', display_name: 'VR', match_aliases: ['VR'], display_order: 5, i18n_key: 'cover.vr' },
];

async function importFreshStateBase(tag) {
    return import(`../state-base.js?coverBadge=${encodeURIComponent(tag)}`);
}

async function withStubFetch(handler, fn) {
    const orig = globalThis.fetch;
    globalThis.fetch = handler;
    try {
        return await fn();
    } finally {
        globalThis.fetch = orig;
    }
}

function manifestFetch(payload, { ok = true, throwError = null } = {}) {
    return async (url) => {
        if (url !== '/api/cover-badges/manifest') {
            throw new Error('pill-match.test.mjs: unexpected fetch url ' + url);
        }
        if (throwError) throw throwError;
        return { ok, json: async () => payload };
    };
}

test('CoverBadgeManifest 失敗分支：fetch 拋錯時既有 DB alias 群組原封不動', async () => {
    const fresh = await importFreshStateBase('fail');
    assert.equal(typeof fresh._loadCoverBadgeManifest, 'function', '_loadCoverBadgeManifest 必須存在');
    fresh._tagToGroup['女僕'] = ['女僕', 'メイド'];
    await assert.doesNotReject(() =>
        withStubFetch(
            manifestFetch(null, { throwError: new Error('network down') }),
            () => fresh._loadCoverBadgeManifest(),
        ),
    );
    assert.deepEqual(fresh._tagToGroup['女僕'], ['女僕', 'メイド']);
    assert.deepEqual(fresh._coverBadgeRules, []);
});

test('CoverBadgeManifest cold/warm：pill 中文字幕 vs user_tags 中字（B1）', async () => {
    const videos = [{ tags: '', user_tags: ['中字'] }];
    const pills = [{ dim: 'tag', value: '中文字幕' }];
    const cold = videos.filter(buildPillPredicate(pills, {}, {}));
    assert.equal(cold.length, 0);

    // warm 必須走 init() 才鎖得住「第一次 applyFilterAndSort 前已併入短名」。
    // 若只餵本地 loaded map，init 漏 await 這條仍會綠——mutation A 就測不紅。
    const c = stateBase.call({ $persist: (obj) => ({ as: () => obj }) });
    c.restoreState = () => {};
    c.fetchVideos = async () => {};
    c.applyFilterAndSort = () => {};
    c.updatePagination = () => {};
    c.loadActresses = () => {};
    // 129-T3：init() 新增了一個 _reconcileHeroCard() 呼叫，而它定義在 state-videos.js。
    // 本 harness 刻意只建 stateBase（不 merge stateVideos）以縮小 cold/warm 的變因，
    // 所以比照上面每一條 init 依賴的既有做法，補一個 stub。
    c._reconcileHeroCard = () => {};
    c._hsInit = () => Promise.resolve();   // 195b-T4：init() 呼叫分片的 _hsInit（本 harness 不 merge 該分片）
    c.$watch = () => {};
    c.$nextTick = () => {};
    c.mode = 'list';
    const origAlpine = globalThis.Alpine;
    const origAddEventListener = globalThis.window.addEventListener;
    globalThis.Alpine = { store: () => ({ toolbarOpen: false, showcaseHasSearch: false }) };
    globalThis.window.__registerPage = () => {};
    globalThis.window.addEventListener = () => {};
    try {
        await withStubFetch(async (url) => {
            if (url === '/api/cover-badges/manifest') {
                return { ok: true, json: async () => COVER_BADGE_MANIFEST_FIVE };
            }
            return { ok: true, json: async () => ({ groups: [] }) };
        }, () => c.init());
    } finally {
        // 全域 stub 必須無條件還原：init() 若因未來的回歸拋例外，殘留的 Alpine /
        // addEventListener stub 會污染同檔後續測試，讓失敗訊息指向錯誤的地方。
        globalThis.Alpine = origAlpine;
        globalThis.window.addEventListener = origAddEventListener;
        delete globalThis.window.__registerPage;
    }

    const warm = videos.filter(buildPillPredicate(pills, {}, stateBaseMod._tagToGroup));
    assert.equal(warm.length, 1);
});


// =====================================================================
// TASK-121c-T2 — mergeAliasGroup / loader 併整組 / _coverBadgeRules
// =====================================================================

test('mergeAliasGroup 與既有 DB alias 群組相交時取聯集', async () => {
    const { _mergeAliasGroup } = await import('../state-base.js');
    assert.equal(typeof _mergeAliasGroup, 'function', '_mergeAliasGroup 必須存在');
    const map = {};
    const dbGroup = ['無碼破解', '裏'];
    for (const member of dbGroup) map[member.toLowerCase()] = dbGroup;
    _mergeAliasGroup(map, ['無碼破解', '破解', '克破', 'AI']);
    const got = map['裏'.toLowerCase()];
    assert.ok(Array.isArray(got), '裏 必須仍是陣列');
    assert.ok(got.includes('克破'), '裏 必須查得到 克破');
    assert.ok(got.includes('無碼破解') && got.includes('破解') && got.includes('AI'));
    assert.equal(map['克破'.toLowerCase()], got, '克破 與 裏 必須指到同一組陣列');
});

test('CoverBadgeManifest 接線：loader 讀 match_aliases 後 破解 與 無碼破解 同組', async () => {
    const fresh = await importFreshStateBase('wiring-match-aliases');
    assert.equal(typeof fresh._loadCoverBadgeManifest, 'function', '_loadCoverBadgeManifest 必須存在');
    // display_name 用 T1 真值 AI，讓 破解 只出現在 match_aliases——
    // 這樣 loader 若只併 canonical + display_name，_tagToGroup['破解'] 就查不到 無碼破解。
    const payload = COVER_BADGE_MANIFEST_FIVE.map((item) => (
        item.id === 'uncen-crack' ? { ...item, display_name: 'AI' } : item
    ));
    await withStubFetch(manifestFetch(payload), () => fresh._loadCoverBadgeManifest());
    const byCrack = fresh._tagToGroup['破解'];
    const byCanonical = fresh._tagToGroup['無碼破解'];
    assert.ok(Array.isArray(byCrack), '_tagToGroup[破解] 應為陣列');
    assert.ok(Array.isArray(byCanonical), '_tagToGroup[無碼破解] 應為陣列');
    assert.ok(byCrack.includes('破解') && byCrack.includes('無碼破解'));
    assert.ok(byCanonical.includes('破解') && byCanonical.includes('無碼破解'));
    assert.equal(byCrack, byCanonical, '兩個 key 必須指到同一組陣列');
    assert.equal(fresh._coverBadgeRules.length, 5);
    assert.equal(fresh._coverBadgeRules[0].display_name, '中字');
});
