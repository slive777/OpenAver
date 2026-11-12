// TASK-199b-T4b：女優片數統一（I-1 同一把尺、I-2 ready gate）。
//
// 本檔自帶與 base.html importmap 對齊的 resolve hook（比照 actress-sort.test.mjs，FE-GUARD-11）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

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

const { buildActressIndex, countWorksByActress, worksOfActress } = await import('@/shared/actress-lookup.js');
const { buildPillPredicate } = await import('@/shared/pill-filter.js');
const { normalizeWorkItem, pickDisplayVersion } = await import('../work-versions.js');
const { stateActress } = await import('../state-actress.js');
const base = await import('../state-base.js');

// 作品 fixture：字串＝單版本；陣列＝多版本（每個元素是該版本的 actresses 欄），經 normalizeWorkItem 掛上 _versions。
let _seq = 0;
function work(spec) {
    const id = 'w' + (++_seq);
    if (Array.isArray(spec)) {
        return normalizeWorkItem({
            path: id + '-v0',
            actresses: spec[0],
            versions: spec.map((acts, i) => ({ path: id + '-v' + i, actresses: acts })),
        });
    }
    return normalizeWorkItem({ path: id, actresses: spec });
}

const FAVORITES = [
    { name: '三上悠亜', video_count: 99 },     // 有別名組
    { name: 'RION', video_count: 99 },         // 全形／大小寫
    { name: '橋本ありな', video_count: 99 },   // 有別名組 ＋ 全形逗號
    { name: '天使もえ', video_count: 99 },
    { name: 'Kana', video_count: 99 },         // 與下一位 token 衝突（NFKC＋小寫後相同）
    { name: 'KANA', video_count: 99 },
    { name: '誰も出ない', video_count: 99 },   // 0 部
];
const NAME_TO_GROUP = {
    '三上悠亜': ['三上悠亜', 'Yua Mikami'], 'yua mikami': ['三上悠亜', 'Yua Mikami'],
    '橋本ありな': ['橋本ありな', '新ありな'], '新ありな': ['橋本ありな', '新ありな'],
};
const WORKS = [
    work('Yua Mikami'),                         // 別名 → 三上
    work('ＲＩＯＮ'),                              // 全形英數 → RION
    work('rion, 三上悠亜'),                       // 兩位
    work('橋本ありな，天使もえ'),                    // 全形逗號切欄 → 兩位
    work('三上悠亜, Yua Mikami'),                 // 同一部寫了她的兩個名字 → 只算 1 部
    work(['橋本ありな', '']),                      // 多版本，只有 A 版寫她
    work(['橋本ありな', '橋本ありな, 天使もえ']),     // 多版本，兩版都寫她 → 只算 1 部
    work('新ありな, 橋本ありな'),                    // 她的兩個名字
    work('Kana'),                               // token 衝突
    work('路人甲'),
    work(''),
];

test('countWorksByActress：每位收藏女優的數字 ＝ 牆上只下她一個 pill 的「共 N 部」（I-1）', () => {
    const index = buildActressIndex(FAVORITES, NAME_TO_GROUP);
    const counts = countWorksByActress(WORKS, index);

    // 期望值一律由牆的實作（buildPillPredicate ＋ pickDisplayVersion）算，不由被測物自己算。
    const wall = (a) => {
        const pred = buildPillPredicate([{ dim: 'actress', value: a.name }], NAME_TO_GROUP, {});
        return WORKS.filter((w) => pickDisplayVersion(w, pred) !== null);
    };
    assert.equal(counts.size, FAVORITES.length, '每位收藏女優都有 key（含 0 部者）');
    for (const a of FAVORITES) {
        const expected = wall(a);
        assert.equal(counts.get(a.name), expected.length, a.name + ' 的片數');
        assert.deepEqual(worksOfActress(WORKS, index, a), expected, a.name + ' 的作品清單（含順序）');
    }
    // 固定值：fixture 本身要真的涵蓋到邊界（避免整表都是 0 也綠）
    assert.deepEqual(
        FAVORITES.map((a) => counts.get(a.name)),
        [3, 2, 4, 2, 1, 1, 0],
    );

    // lookup 口徑＝牆上 pill：期望「第一位其 pill 會命中這個名字的收藏女優」，由牆的 predicate 算
    const probes = ['Yua Mikami', 'yua mikami', ' ＲＩＯＮ ', 'rion', '新ありな', '橋本ありな', '天使もえ', 'ＫＡＮＡ', 'kana', '路人甲', '', '誰も出ない'];
    for (const raw of probes) {
        const hit = FAVORITES.find((a) => buildPillPredicate([{ dim: 'actress', value: a.name }], NAME_TO_GROUP, {})({ actresses: raw })) || null;
        assert.equal(index.lookup(raw), hit, 'lookup(' + JSON.stringify(raw) + ')');
    }
    assert.equal(index.lookup('kana'), FAVORITES[4], '同一 token 多位收藏時先到的贏');
    assert.equal(index.lookup(null), null);
});

test('actressWorkCount：片庫或別名表任一未就緒時恆為 null（不讀伺服器舊值），就緒後等於當下片庫算出的數字（I-2）', async () => {
    const origFetch = globalThis.fetch;
    const c = Object.assign({}, stateActress(), { $nextTick() {}, showToast() {} });
    const mine = FAVORITES[0];
    const zero = FAVORITES[6];
    const reset = () => {
        base._setVideosReady(false);
        base._setVideos([]);
        base._setActresses([]);
        base._setActressWorkCounts(null);
        base._setActressIndex(null);
        base._setActressesLoaded(false);
        globalThis.fetch = origFetch;
    };
    const okJson = (body) => ({ ok: true, status: 200, json: async () => body });
    try {
        base._setActresses(FAVORITES.map((a) => ({ ...a })));
        base._setVideos(WORKS);
        // （1）別名表尚未載入（_aliasMapLoaded 是單向閂鎖，必須先測）：片庫就緒與否都是 null
        assert.equal(base._aliasMapLoaded, false);
        c._refreshActressDerived();
        assert.equal(c.actressWorkCount(mine), null, '兩者皆未就緒 → null');
        base._setVideosReady(true);
        c._refreshActressDerived();
        assert.equal(c.actressWorkCount(mine), null, '片庫先到、別名表未載 → null');
        assert.equal(c.actressWorkCount(zero), null);

        // （2）女優後到（載入別名表的是 loadActresses）、但片庫尚未就緒 → 仍是 null，不是伺服器的 99
        base._setVideosReady(false);
        globalThis.fetch = async (url) => {
            if (String(url).startsWith('/api/actress-aliases')) {
                return okJson({ groups: [{ primary_name: '三上悠亜', aliases: ['Yua Mikami'] }, { primary_name: '橋本ありな', aliases: ['新ありな'] }] });
            }
            if (String(url).startsWith('/api/actresses')) {
                return okJson({ success: true, actresses: FAVORITES.map((a) => ({ ...a })) });
            }
            throw new Error('unexpected fetch ' + url);
        };
        await c.loadActresses();
        assert.equal(base._aliasMapLoaded, true);
        assert.equal(c.actressWorkCount(mine), null, '女優先到、片庫未就緒 → null');

        // （3）片庫就緒（#7 / fetchVideos 成功路徑的刷新）→ 當下片庫算出的數字，0 部是合法的 0
        base._setVideosReady(true);
        c._refreshActressDerived();
        assert.equal(c.actressWorkCount(mine), 3);
        assert.equal(c.actressWorkCount(FAVORITES[2]), 4);
        assert.strictEqual(c.actressWorkCount(zero), 0);
        const rev = c.actressWorkRev;

        // （4）片庫載入失敗 → 不殘留上一次的數字
        base._setVideosReady(false);
        c._refreshActressDerived();
        assert.equal(c.actressWorkCount(mine), null);
        assert.ok(c.actressWorkRev > rev, '版本號遞增，讀它的 binding 才會重算');

        // （5）片庫先到、女優後到：載入完成那一刻（#1）數字已是最終值
        base._setVideosReady(true);
        base._setActressWorkCounts(null);
        base._setActressesLoaded(false);
        await c.loadActresses();
        assert.equal(c.actressWorkCount(mine), 3);
        assert.strictEqual(c.actressWorkCount(zero), 0);
    } finally {
        reset();
    }
});
