// TASK-123-T3: 燈箱精選星 —— togglePickStar 飛行鎖／captured ref／_pickFilterStale／三層失敗判定
//
// 2026-08-21（自生洞立即停，換掉機制）：舊版用一個「dirty」旗標＋一個「這次是不是我設起來的」
// 輔助旗標代理「牆面是否過期」，在並發（兩個 path 同時在飛）與飛行中關燈箱下都會與真實狀態
// 脫鉤（已用腳本重現，非推理）。新機制不設旗標，改用直接觀察 _filteredVideos 的述詞
// `_pickFilterStale()`——本檔下方相關測試段落已全部改寫成驗這個述詞的行為。
//
// 零 DOM，mock global.fetch。state-lightbox.js 用瀏覽器 importmap 別名 `@/showcase/...`，
// plain `node --test` 不認得；比照 delete-modal-multipart.test.mjs／lb-full-error-pill.test.mjs
// 自帶與 base.html importmap 對齊的 resolve hook。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

// closeLightbox / searchFromMetadata 會碰 document；給最小 stub。
globalThis.document = {
    querySelector() { return null; },
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
// _pickFilterStale() 讀的是 state-base.js 的模組級單例陣列（同一個 import specifier，
// 走同一支 resolve hook，跟 state-lightbox.js 內部 `@/showcase/state-base.js` 解析到同一份
// 模組實例）——測試用它直接佈置/清空「牆上目前顯示的清單」。
const { _filteredVideos, _videos } = await import('@/showcase/state-base.js');
// 123-T8c：_pickFilterStale() 改成呼叫 _computeFilteredVideos()（state-videos.js 的
// 篩選那一半）直接算真實 membership，不再猜。所以測試元件必須把**真的那支 mixin** 併進來，
// 讓述詞走 production call path，而不是在測試裡放一個更淺的 stub 版篩選器。
const { stateVideos } = await import('../state-videos.js');

const PATH_A = 'file:///m/ABC-123.mp4';
const PATH_B = 'file:///m/DEF-456.mp4';

/** 佈置牆上目前顯示的清單 _filteredVideos ＋ 全庫 _videos（每個涉及 _pickFilterStale()
 *  的測試都要先呼叫，避免吃到前一支測試殘留）。
 *
 *  123-T8c：述詞現在會用 _videos 重算一次真實 membership 再跟 _filteredVideos 比對，
 *  所以兩個陣列都要佈置。`library` 省略時＝全庫就等於牆上這些（最常見情境）；要模擬
 *  「有一片在庫裡但不在牆上」（Codex PR review P2 的相似面板情境）就明確傳第二個參數。 */
function setFilteredVideos(arr, library) {
    _filteredVideos.length = 0;
    for (const v of arr) _filteredVideos.push(v);
    _videos.length = 0;
    for (const v of (library || arr)) _videos.push(v);
}

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
    const c = Object.assign({}, stateLightbox(), stateVideos(), {
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

// ── 飛行鎖 ──────────────────────────────────────────────────────────

// ── CD-123-15 captured ref ───────────────────────────────────────────

test('captured ref：飛行中換片，失敗時回滾的是原本那一片，不是現在顯示的那片', async () => {
    const mock = mockFetchManual();
    try {
        const videoA = { path: PATH_A, user_rating: 0, number: 'ABC-123' };
        const videoB = { path: PATH_B, user_rating: 0, number: 'DEF-456' };
        const c = makeComponent({ currentLightboxVideo: videoA });

        const p = c.togglePickStar();
        assert.equal(videoA.user_rating, 1, '樂觀更新寫到 A');

        // 飛行中滾到下一片
        c.currentLightboxVideo = videoB;

        mock.calls[0].resolve({
            ok: true,
            status: 200,
            json: async () => ({
                success: true,
                results: [{ ok: false, reason: 'not_found' }],
            }),
        });
        await p;

        assert.equal(videoA.user_rating, 0, '失敗必須回滾 A（captured）');
        assert.equal(videoB.user_rating, 0, 'B 不該被碰');
        assert.equal(c.toasts.length, 1);
        assert.equal(c.toasts[0].msg, 'showcase.pick.save_failed');
        assert.equal(c.toasts[0].kind, 'error');
    } finally {
        mock.restore();
    }
});

// ── _pickFilterStale 述詞（CD-123-14a，取代舊版的旗標機制）─────────
// 直接觀察 _filteredVideos：掛精選 pill 時，牆上清單裡只要有一片不是精選（user_rating
// 為 0），就代表牆面已過期，需要重篩。沒掛 pill 時恆不重篩。每支測試各自
// setFilteredVideos()，不依賴前一支測試殘留的內容。

test('scenario 2：掛 pick pill、取消某片的星 → 燈箱還開著時不重篩（§4.13）→ closeLightbox 剛好呼叫一次', async () => {
    const mock = mockFetchManual();
    try {
        const video = { path: PATH_A, user_rating: 1 };
        const c = makeComponent({
            currentLightboxVideo: video,
            pills: [{ dim: 'pick', value: '1' }],
            lightboxOpen: true,
        });
        setFilteredVideos([video]);

        const p = c.togglePickStar();
        assert.equal(video.user_rating, 0, '樂觀更新已生效');

        mock.calls[0].resolve(okResp());
        await p;
        assert.equal(c.applyFilterAndSortCalls, 0, '燈箱還開著，不能當場把這片從腳下抽走');

        c.closeLightbox();
        assert.equal(c.applyFilterAndSortCalls, 1, '關燈箱時牆面已過期，剛好重篩一次');
    } finally {
        mock.restore();
    }
});


// ── 三層失敗判定 ────────────────────────────────────────────────────

test('三層失敗：HTTP 200 + success:true + results[0].ok:false(not_found) 必須當失敗並回滾', async () => {
    // 162a：success:false（HTTP 仍 200）併入同一支——同一失敗原因：伺服器沒存到卻看似成功
    const cases = [
        { before: 0, optimistic: 1, body: { success: true, results: [{ ok: false, reason: 'not_found' }] } },
        { before: 1, optimistic: 0, body: { success: false } },
    ];
    for (const c of cases) {
        const mock = mockFetchManual();
        try {
            const video = { path: PATH_A, user_rating: c.before };
            const comp = makeComponent({ currentLightboxVideo: video });

            const p = comp.togglePickStar();
            assert.equal(video.user_rating, c.optimistic);

            mock.calls[0].resolve({
                ok: true,
                status: 200,
                json: async () => c.body,
            });
            await p;

            assert.equal(video.user_rating, c.before, '伺服器判定失敗必須回滾到 oldValue');
            assert.equal(comp.toasts.length, 1);
            assert.equal(comp.toasts[0].msg, 'showcase.pick.save_failed');
        } finally {
            mock.restore();
        }
    }
});

test('成功路徑：success:true + results[0].ok:true → 不 toast、不回滾', async () => {
    const mock = mockFetchManual();
    try {
        const video = { path: PATH_A, user_rating: 0 };
        const c = makeComponent({ currentLightboxVideo: video });

        const p = c.togglePickStar();
        mock.calls[0].resolve(okResp([{ ok: true }]));
        await p;

        assert.equal(video.user_rating, 1);
        assert.equal(c.toasts.length, 0);
        assert.equal(c._pickInFlight[PATH_A], undefined);
    } finally {
        mock.restore();
    }
});

// ── 飛行中關燈箱／並發（取代舊版那兩個旗標造成的 bug，見檔頭）───
// 這兩支是舊機制壞掉的地方：舊版用旗標代理「牆面過期了嗎」，在下面兩種時序下都會
// 與真實狀態脫鉤。新機制沒有旗標可以競爭，每次都直接觀察 _filteredVideos。


// ── 123-T4：取消已精選片 ＋ 飛行中關燈箱（自生洞修正，見 state-lightbox.js
// _pickHasInFlight() 註解）───────────────────────────────────────────────
// 壞掉的序列：V 已精選（rating 1）→ 取消（樂觀 → 0）→ 請求還沒回來就關燈箱 →
// closeLightbox 的述詞讀到「牆上有一片不是精選的」→ 判定過期 → 若真的重篩，V 會被
// applyFilterAndSort 移出 _filteredVideos → 請求之後回滾成 1 → 但 V 已經不在陣列裡，
// 述詞掃不到它 → 卡回不來。修法：請求還在飛時兩個呼叫點都不篩，等最後一個請求落地
// （成功或已回滾）資料成定局，再篩一次。


test('請求 body：file_path + picked 布林（冪等設值，非 toggle）', async () => {
    const mock = mockFetchManual();
    try {
        const video = { path: PATH_A, user_rating: 0 };
        const c = makeComponent({ currentLightboxVideo: video });
        const p = c.togglePickStar();
        assert.equal(mock.calls[0].url, '/api/user-rating');
        assert.equal(mock.calls[0].method, 'POST');
        assert.deepEqual(mock.calls[0].body, { file_path: PATH_A, picked: true });
        mock.calls[0].resolve(okResp());
        await p;
    } finally {
        mock.restore();
    }
});

// ── 123-T4：回滾動畫的 stale 檢查（CDP 實測重現後修正，見 state-lightbox.js
// togglePickStar() catch 區塊的 `if (this.currentLightboxVideo === video)` 註解）─────
// 燈箱裡的星是常駐 DOM 節點，不是每片各一顆。回滾發生在 await 之後：若飛行中已經滾到
// 別片，document.querySelector('.pick-star-fill') 抓到的是「現在顯示那片」的星，
// 沒有 stale 檢查就會把「已離場那片的回滾動畫」畫到「現在這片」的星上。


// ── 123-T8c：_pickFilterStale() 的雙向偵測（兩輪 review 各打中一個方向）──────────
// 舊版述詞是「掃 _filteredVideos 有沒有 rating 0」——單向，只看得到「該離開牆的」。
// 下面兩支各自鎖住一個方向；把述詞改回舊版的單向寫法，第一支會轉紅。



// ── 198b-T7b：togglePickStar 作品層（三個版本一起變，燈箱停在非預設版本）──────────────────
const { normalizeWorkItem: normalizeWork198 } = await import('../work-versions.js');

function pickWork198() {
    const mkv = (p) => ({ path: 'file:///m/ABF-348' + p, user_rating: 1, title: 'T' + p });
    const list = [mkv('-C.mkv'), mkv('.mp4'), mkv('-LTX.mkv')];
    normalizeWork198({ ...list[0], versions: list });
    return list; // [中字（預設）, 4K, LTX]，皆為原物件
}

test('togglePickStar 作品層：LTX 版取消 ★ → 三個版本一起 0、失敗一起回 1、飛行中換版本連點不發第二個請求', async () => {
    const mock = mockFetchManual();
    try {
        const [zh, k4, ltx] = pickWork198();
        const all = [zh, k4, ltx];
        const c = makeComponent({ currentLightboxVideo: ltx, paginatedVideos: [] });

        const p = c.togglePickStar();
        assert.deepEqual(all.map((d) => d.user_rating), [0, 0, 0], '樂觀更新寫到三個版本');
        assert.deepEqual(all.map((d) => !!c._pickInFlight[d.path]), [true, true, true], '飛行鎖鎖整部作品');
        assert.equal(mock.calls[0].body.file_path, ltx.path, 'body 用目前版本（LTX）的 path');

        c.currentLightboxVideo = zh;   // 飛行中切到同作品的中字版再按
        c.togglePickStar();
        assert.equal(mock.calls.length, 1, '同一部作品跨版本連點不發第二個請求');

        mock.calls[0].resolve(okResp());
        await p;
        assert.deepEqual(all.map((d) => d.user_rating), [0, 0, 0], '成功：維持樂觀值');
        assert.deepEqual(all.map((d) => d.path in c._pickInFlight), [false, false, false], '落地後三把鎖都清掉');

        // 失敗：三個版本一起回原狀
        c.currentLightboxVideo = ltx;
        const p2 = c.togglePickStar();
        assert.deepEqual(all.map((d) => d.user_rating), [1, 1, 1]);
        mock.calls[1].resolve({ ok: true, status: 200, json: async () => ({ success: true, results: [{ ok: false }] }) });
        await p2;
        assert.deepEqual(all.map((d) => d.user_rating), [0, 0, 0], '失敗：三個版本一起回到取消前的 0');
        assert.equal(c.toasts.at(-1).msg, 'showcase.pick.save_failed');
    } finally {
        mock.restore();
    }
});
