// TASK-193-T7：以圖搜番號的前端流程（state/image-search.js ＋ doSearch／saveState 掛勾）
//
// 守住的行為（使用者面）：
//   img_search_object_url_lifecycle   連換圖／失敗／取消／✕／離頁，圖片記憶體不累積；文字搜尋在飛時丟圖，取消回來比對列仍回得來
//   img_search_late_response_dropped  比對進行中換做別的搜尋或按停止，晚到結果不改新畫面；停止後不留永遠補不上的骨架
//   img_search_never_persisted        圖片結果（含骨架）不會被重新整理還原；文字結果照常還原
//
// 假 fetch 刻意忽略 signal（FE-GUARD-40）：不因 abort 自行 reject，否則 token／live 守衛變死碼。回應一律由測試手動放行。
// 假回應只用我們自己的協定（/api/image-search 信封、/api/search 的 {success,data}）。
// Proxy 替身（FE-ALPINE-14）：searchResults 與 imgSearchSession 兩欄改 accessor，讀回來是深層 Proxy、
// Alpine.raw 以 WeakMap 查表，讓「讀回不是同一個物件」在 node 也成立。
// merge() 用 descriptor 版（FE-ALPINE-21）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.document = { addEventListener() {}, querySelector() { return null; } };
window.t = (k, p) => (p ? k + JSON.stringify(p) : k);

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);

const { searchStateBase } = await import('../state/base.js');
const { searchStateSearchFlow } = await import('../state/search-flow.js');
const { searchStatePersistence } = await import('../state/persistence.js');
const { searchStateImageSearch } = await import('../state/image-search.js');

class FakeES {
    static instances = [];
    constructor(url) { this.url = url; this.closed = false; this.onmessage = null; this.onerror = null; FakeES.instances.push(this); }
    close() { this.closed = true; }
}
FakeES.CLOSED = 2;
globalThis.EventSource = FakeES;

const tick = () => new Promise((r) => setImmediate(r));

function merge(...parts) {
    const target = {};
    for (const part of parts) Object.defineProperties(target, Object.getOwnPropertyDescriptors(part));
    return target;
}

// ── Proxy 替身 ────────────────────────────────────────────────────────
const RAW_OF = new WeakMap();
const PROXY_OF = new WeakMap();
const unwrap = (x) => RAW_OF.get(x) ?? x;
function wrap(raw) {
    if (raw === null || typeof raw !== 'object') return raw;
    let p = PROXY_OF.get(raw);
    if (!p) {
        p = new Proxy(raw, {
            get(t, k, r) { const v = Reflect.get(t, k, r); return v && typeof v === 'object' ? wrap(v) : v; },
            set(t, k, v) { t[k] = unwrap(v); return true; },
        });
        PROXY_OF.set(raw, p);
        RAW_OF.set(p, raw);
    }
    return p;
}
globalThis.Alpine = { raw: unwrap };
function reactive(page, key, init) {
    let raw = unwrap(init);
    Object.defineProperty(page, key, { configurable: true, enumerable: true, get: () => wrap(raw), set: (v) => { raw = unwrap(v); } });
}

// ── object URL spy ────────────────────────────────────────────────────
const blobs = { alive: new Set(), bad: [], max: 0, seq: 0 };
URL.createObjectURL = () => { const u = `blob:fake/${++blobs.seq}`; blobs.alive.add(u); blobs.max = Math.max(blobs.max, blobs.alive.size); return u; };
URL.revokeObjectURL = (u) => { if (!blobs.alive.delete(u)) blobs.bad.push(u); };

// ── 假網路（忽略 signal）──────────────────────────────────────────────
const isUpload = (c) => c.url === '/api/image-search';
const isLookup = (c) => c.url.startsWith('/api/search?q=');
const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const bad = (status, body) => ({ ok: false, status, json: async () => body });
const cand = (i, searchable = true) => ({ rank: i + 1, code: `AAA-00${i + 1}`, number: `AAA-00${i + 1}`, searchable, similarity: 0.9, match: { kind: 'frame' }, in_library: false });
const envelope = (n) => ok({ success: true, source: 'avscan', clear_hit: false, lead: null, candidates: Array.from({ length: n }, (_, i) => cand(i)) });
const lookupOk = (url) => { const q = decodeURIComponent(url.split('q=')[1].split('&')[0]); return ok({ success: true, data: [{ number: q, title: `T-${q}`, cover: '' }] }); };
const mkFile = (name = 'a.png') => ({ name, type: 'image/png', size: 1000 });

function env() {
    FakeES.instances.length = 0;
    blobs.alive.clear(); blobs.bad.length = 0; blobs.max = 0;
    const net = { pending: [], find: (pred) => net.pending.find(pred) };
    net.release = (pred, resp) => {
        const i = net.pending.findIndex(pred);
        assert.ok(i >= 0, 'expected a pending request');
        const [e] = net.pending.splice(i, 1);
        e.resolve(typeof resp === 'function' ? resp(e) : resp);
    };
    globalThis.fetch = (url, opts) => new Promise((resolve) => net.pending.push({ url, opts, resolve }));
    const log = { toasts: [], toggle: 0, cls: [] };
    const page = merge(searchStateBase(), searchStateSearchFlow(), searchStatePersistence(), searchStateImageSearch(), {
        $nextTick(fn) { if (fn) queueMicrotask(fn); },
        _resetCoverState() {},
        switchToWishlist() {},
        checkLocalStatus(arr) { log.cls.push(arr); },
        showToast(text, type) { log.toasts.push({ text, type }); },
        toggleDisplayMode() { log.toggle++; this.displayMode = this.displayMode === 'grid' ? 'detail' : 'grid'; },
    });
    reactive(page, 'searchResults', []);
    reactive(page, 'imgSearchSession', null);
    return { page, net, log };
}

async function drainLookups(net) {
    for (;;) {
        await tick();
        const e = net.find(isLookup);
        if (!e) return;
        net.release(isLookup, lookupOk(e.url));
    }
}
// 啟動並放行候選回應；回 { p }（包一層避免 async 吃掉 promise）
async function startWithCandidates(e, n, name) {
    const p = e.page.imgSearchStart(mkFile(name));
    await tick();
    e.net.release(isUpload, envelope(n));
    await tick();
    return { p };
}
async function complete(e, n = 2) {
    const { p } = await startWithCandidates(e, n);
    await drainLookups(e.net);
    await p;
}
const skeletons = (page) => unwrap(page.searchResults).filter((r) => r._skeleton).length;
const snap = (page) => JSON.stringify(page.searchResults);

// ── 1 ─────────────────────────────────────────────────────────────────
test('img_search_object_url_lifecycle', async () => {
    // why: 使用者連換圖、失敗、取消、✕、離頁後，瀏覽器不能累積未釋放的圖片記憶體；文字搜尋還在飛時丟圖，取消回來後比對列仍要回得來
    const e = env();
    const { page, net, log } = e;
    const live = () => blobs.alive.size;

    await complete(e, 2);                                   // A
    assert.equal(live(), 1);
    const pB = page.imgSearchStart(mkFile('b.png'));        // B：查詢中存活 2
    await tick();
    assert.equal(live(), 2);
    net.release(isUpload, envelope(2));
    await tick();
    assert.equal(live(), 1, 'B 替換後 A 立刻回收');
    await drainLookups(net);
    await pB;

    const pC = page.imgSearchStart(mkFile());               // C：rate_limited
    await tick();
    assert.equal(live(), 2);
    net.release(isUpload, bad(429, { success: false, error: 'rate_limited', retry_after: 3 }));
    await pC;
    assert.equal(live(), 1);
    assert.deepEqual(log.toasts, [{ text: 'search.image.rate_limited{"seconds":3}', type: 'warning' }]);

    const pD = page.imgSearchStart(mkFile());               // D：零候選
    await tick();
    net.release(isUpload, envelope(0));
    await pD;
    assert.equal(live(), 1);
    assert.deepEqual(log.toasts[1], { text: 'search.image.unreachable', type: 'error' });

    const urlBeforeE = page.imgSearchSession.url;           // E：查詢中按 ✕ 只撤掉查詢
    const pE = page.imgSearchStart(mkFile());
    await tick();
    assert.equal(live(), 2);
    page.imgSearchOnClear();
    assert.equal(live(), 1);
    assert.equal(page.imgSearchPhase, 'idle');
    net.release(isUpload, envelope(1));                     // 假 fetch 忽略 signal，晚到
    await pE;
    assert.equal(live(), 1);
    assert.equal(page.imgSearchSession.url, urlBeforeE, '晚到的查詢不得換掉 session');
    page.imgSearchOnClear();                                // 真 ✕：清畫面＋回收
    assert.equal(live(), 0);
    assert.equal(page.imgSearchSession, null);

    await complete(e, 2);                                   // 文字搜尋取代，session 無主
    page.searchResults = [{ number: 'TXT-1' }];
    const pF = page.imgSearchStart(mkFile());
    await tick();
    assert.equal(live(), 1, '開始時先回收無主 session');
    net.release(isUpload, envelope(2));
    await tick();
    await drainLookups(net);
    await pF;
    assert.equal(live(), 1);

    const fArr = unwrap(page.searchResults);                // G：文字搜尋在飛（真 doSearch 抓 snapshot）
    await page.doSearch('TXT-2');
    assert.equal(page.imgSearchHeld, true);
    assert.equal(page.imgSearchActive, false);
    const pG = page.imgSearchStart(mkFile());
    await tick();
    assert.equal(live(), 2, '被 snapshot 握著的 session 不回收');
    net.release(isUpload, bad(502, { success: false, error: 'unreachable' }));
    await pG;
    assert.equal(live(), 1);
    page.cancelSearch();
    assert.equal(page.imgSearchActive, true);
    assert.equal(unwrap(page.searchResults), fArr);
    page.imgSearchStopLookup();
    assert.equal(live(), 1, '停止後不回收');

    const pH = page.imgSearchStart(mkFile('h.png'));        // H、I、J 連換三張
    await tick();
    const pI = page.imgSearchStart(mkFile('i.png'));
    await tick();
    const pJ = page.imgSearchStart(mkFile('j.png'));
    await tick();
    assert.equal(live(), 2);
    const [h, i, j] = net.pending.filter(isUpload);
    net.pending.splice(net.pending.indexOf(h), 1); h.resolve(envelope(2));
    net.pending.splice(net.pending.indexOf(i), 1); i.resolve(envelope(2));
    await tick();
    assert.equal(unwrap(page.searchResults), fArr, 'H、I 晚到被丟棄');
    assert.equal(live(), 2);
    net.pending.splice(net.pending.indexOf(j), 1); j.resolve(envelope(2));
    await tick();
    assert.equal(live(), 1);
    await drainLookups(net);
    await Promise.all([pH, pI, pJ]);

    page.imgSearchCleanup();
    assert.equal(live(), 0);
    assert.equal(page.imgSearchSession, null);
    assert.ok(blobs.max <= 2, `存活數最大值 ${blobs.max}`);
    assert.deepEqual(blobs.bad, [], 'revoke 從未對不存活的 URL 呼叫');
});

// ── 2 ─────────────────────────────────────────────────────────────────
test('img_search_late_response_dropped', async () => {
    // why: 比對進行中換做別的搜尋或按停止，晚到的結果不能改掉新畫面；停止後不留永遠補不上的骨架
    // (a) 對照組：沒取消，同一串回應確實改了 state
    {
        const e = env();
        const { page, net, log } = e;
        await complete(e, 3);
        assert.equal(skeletons(page), 0);
        assert.deepEqual(unwrap(page.searchResults).map((r) => r.title), ['T-AAA-001', 'T-AAA-002', 'T-AAA-003']);
        assert.equal(log.toggle, 1, '第一名補上且沒動過 → 自動轉詳細');
        assert.equal(log.cls.length, 3);
        assert.notStrictEqual(log.cls[0][0], unwrap(log.cls[0][0]), 'checkLocalStatus 收到讀回的 Proxy，不是 raw item');
        assert.equal(unwrap(log.cls[0][0]), unwrap(page.searchResults)[0]);
        assert.equal(page.imgSearchLooking, false);
        assert.equal(net.pending.length, 0);
    }
    // (b) StopLookup 之後晚到
    {
        const e = env();
        const { page, net, log } = e;
        const { p } = await startWithCandidates(e, 4);
        net.release(isLookup, lookupOk(net.find(isLookup).url));
        await tick();
        assert.equal(page.imgSearchLooking, true);
        const stale = net.find(isLookup);
        page.imgSearchStopLookup();
        assert.equal(skeletons(page), 0);
        assert.equal(page.imgSearchLooking, false);
        assert.equal(page.imgSearchActive, true);
        const r = unwrap(page.searchResults);
        assert.equal(r[0].title, 'T-AAA-001');
        assert.deepEqual(r.slice(1).map((x) => [x.number, x._notFound, x.cover]), [['AAA-002', true, ''], ['AAA-003', true, ''], ['AAA-004', true, '']]);
        assert.equal(page.imgSearchSession.matches.length, r.length);
        const frozen = snap(page);
        const cls = log.cls.length; const tg = log.toggle;
        net.release((c) => c === stale, lookupOk(stale.url));
        await tick();
        assert.equal(snap(page), frozen);
        assert.equal(log.cls.length, cls);
        assert.equal(log.toggle, tg);
        assert.equal(net.find(isLookup), undefined, '不再發新查詢');
        await drainLookups(net);
        await p;
    }
    // (c) 陣列被換成新陣列後晚到
    {
        const e = env();
        const { page, net, log } = e;
        const { p } = await startWithCandidates(e, 3);
        const bound = unwrap(page.imgSearchSession.bound);
        net.release(isLookup, lookupOk(net.find(isLookup).url));
        await tick();
        const tg = log.toggle; const cls = log.cls.length;
        const other = [{ number: 'OTHER' }];
        page.searchResults = other;
        net.release(isLookup, lookupOk(net.find(isLookup).url));
        await tick();
        assert.deepEqual(unwrap(page.searchResults), [{ number: 'OTHER' }]);
        assert.equal(log.toggle, tg);
        assert.equal(log.cls.length, cls);
        assert.equal(net.find(isLookup), undefined);
        assert.equal(bound[1]._skeleton, true, '舊陣列沒被寫入');
        await drainLookups(net);
        await p;
    }
    // (d) 候選還有骨架時 doSearch：snapshot 無 _skeleton；取消後回到圖片結果
    {
        const e = env();
        const { page, net } = e;
        const { p } = await startWithCandidates(e, 3);
        net.release(isLookup, lookupOk(net.find(isLookup).url));
        await tick();
        const arr = unwrap(page.searchResults);
        const stale = net.find(isLookup);
        await page.doSearch('TXT-3');
        assert.equal(unwrap(page._searchSnapshot.searchResults).filter((x) => x._skeleton).length, 0);
        assert.equal(page.imgSearchLooking, false);
        page.cancelSearch();
        assert.equal(page.pageState, 'result');
        assert.equal(unwrap(page.searchResults), arr);
        assert.equal(page.imgSearchActive, true);
        net.release((c) => c === stale, lookupOk(stale.url));
        await tick();
        await p;
        assert.equal(skeletons(page), 0);
    }
    // (f) 圖片查詢還在飛時改打文字搜尋 → 圖片回應晚到不得蓋掉文字搜尋
    {
        const e = env();
        const { page, net } = e;
        const pImg = page.imgSearchStart(mkFile());
        await tick();
        assert.equal(blobs.alive.size, 1);
        await page.doSearch('ABC-123');
        assert.equal(blobs.alive.size, 0, '查詢被撤掉、URL 回收');
        assert.equal(page.imgSearchPhase, 'idle');
        net.release(isUpload, envelope(2));                 // 假 fetch 忽略 signal，晚到
        await tick();
        await pImg;
        assert.equal(page.pageState, 'loading');
        assert.equal(page.currentQuery, 'ABC-123');
        assert.deepEqual(unwrap(page.searchResults), []);
        assert.equal(page.imgSearchSession, null);
        assert.equal(blobs.alive.size, 0);
        assert.equal(FakeES.instances.at(-1).closed, false, '文字搜尋的 SSE 沒被 cancelSearch 關掉');
    }
    // (e) 使用者先動過檢視 → 第一名補上不轉
    {
        const e = env();
        const { log } = e;
        const { p } = await startWithCandidates(e, 2);
        e.page.imgSearchNoteMove();
        await drainLookups(e.net);
        await p;
        assert.equal(log.toggle, 0);
        assert.equal(e.page.displayMode, 'grid');
    }
});

// ── 3 ─────────────────────────────────────────────────────────────────
test('img_search_never_persisted', async () => {
    // why: 圖片搜尋後（或文字搜尋還沒完成時）重新整理，不能還原出殘缺／含骨架的圖片結果；文字搜尋接手後重新整理，文字結果仍在
    const store = {};
    globalThis.sessionStorage = {
        setItem: (k, v) => { store[k] = v; },
        getItem: (k) => store[k] ?? null,
        removeItem: (k) => { delete store[k]; },
    };
    const e = env();
    const { page, net } = e;
    const KEY = page.STATE_KEY;
    const seedText = () => { store[KEY] = JSON.stringify({ searchResults: [{ number: 'TXT-OLD' }], listMode: 'search' }); };

    seedText();
    const { p } = await startWithCandidates(e, 3);          // 骨架還在，不放行逐部查詢
    assert.ok(skeletons(page) > 0);
    page.saveState();
    assert.equal(sessionStorage.getItem(KEY), null, '① session live');

    seedText();                                             // ② live 空、snapshot 握圖片結果、載入中
    page._searchSnapshot = { searchResults: page.searchResults, currentIndex: 0, pageState: 'result', listMode: 'search', displayMode: 'grid' };
    page.searchResults = [];
    page.pageState = 'loading';
    page.saveState();
    assert.equal(sessionStorage.getItem(KEY), null, '② snapshot 握著');

    const fresh = merge(searchStateBase(), searchStatePersistence(), { _resetCoverState() {}, switchToWishlist() {} });
    fresh.restoreState();                                   // ③
    assert.equal(fresh.searchResults.length, 0);

    page._searchSnapshot = null;                            // ④ 合法放行
    page.pageState = 'result';
    page.searchResults = [{ number: 'TXT-1' }];
    page.saveState();
    assert.equal(JSON.parse(sessionStorage.getItem(KEY)).searchResults[0].number, 'TXT-1');

    page.imgSearchCleanup();
    net.release(isLookup, lookupOk(net.find(isLookup).url));
    await p;
});
