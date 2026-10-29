// TASK-140-T5：wishlist 狀態分片 ＋ listMode 對帳表 ＋ membership hydration
// TASK-140-T10：listMode/displayMode 還原不變式
//
// 覆蓋 DoD：
//   - loadMore 白名單化（M1）
//   - saveState live 取值／restoreState switchToWishlist／resolveVisibleDisplayMode（T10）
//   - addToWishlist I3 回滾（M3）
//   - switchToWishlist 設 displayMode='grid'
//   - membership hydration 三條
//   - main.js init() 呼叫 loadWishlistCount()

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.document = { addEventListener() {} };

if (typeof globalThis.requestAnimationFrame !== 'function') {
    globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);
}

// state/__tests__ → 上一層 __tests__/alias-loader.mjs（鏡射 pages/search/__tests__ 慣例）
register(new URL('../../__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

const { searchStateWishlist } = await import('../wishlist.js');
const { searchStatePersistence } = await import('../persistence.js');
const { searchStateBase } = await import('../base.js');
const { searchStateSearchFlow } = await import('../search-flow.js');

function mockFetch(handler) {
    const calls = [];
    globalThis.fetch = async (url, opts = {}) => {
        calls.push({ url: String(url), opts });
        return handler(String(url), opts, calls);
    };
    return calls;
}

function jsonResponse(data, { ok = true, status = 200 } = {}) {
    return {
        ok,
        status,
        json: async () => data,
    };
}

// ─── 對帳表 #2：loadMore 白名單化（mutation M1）───────────────────────────


// ─── TASK-140-T10：listMode/displayMode 還原不變式（DoD 4a–4f）────────────

function mockSessionStorage(initial = {}) {
    const store = { ...initial };
    globalThis.sessionStorage = {
        setItem: (k, v) => { store[k] = v; },
        getItem: (k) => store[k] ?? null,
        removeItem: (k) => { delete store[k]; },
    };
    return store;
}

function basePersistFields(overrides = {}) {
    return {
        searchResults: [],
        currentIndex: 0,
        currentQuery: '',
        currentOffset: 0,
        hasMoreResults: false,
        fileList: [],
        currentFileIndex: 0,
        listMode: null,
        searchQuery: '',
        displayMode: 'detail',
        _preWishlistDisplayMode: null,
        currentMode: '',
        actressProfile: null,
        pageState: 'result',
        ...overrides,
    };
}

// DoD 4a（mutation M1）

// DoD 4b

// DoD 4c

// DoD 4d（mutation M2）
test('restoreState: listMode恢復為wishlist時呼叫switchToWishlist並載入清單', () => {
    const STATE_KEY = 'test-t10-restore';
    mockSessionStorage({
        [STATE_KEY]: JSON.stringify({
            searchResults: [],
            currentIndex: 0,
            currentQuery: '',
            currentOffset: 0,
            hasMoreResults: false,
            fileList: [],
            currentFileIndex: 0,
            listMode: 'wishlist',
            queryValue: '',
            displayMode: 'grid',
            _preWishlistDisplayMode: 'detail',
            currentMode: '',
            actressProfile: null,
        }),
    });

    let switchCalls = 0;
    const fakeThis = {
        ...searchStatePersistence(),
        STATE_KEY,
        ...basePersistFields(),
        lightboxOpen: false,
        lightboxIndex: 0,
        _heroCardImageError: false,
        _heroLightboxImageError: false,
        _resetCoverState: () => {},
        switchToWishlist() { switchCalls += 1; },
    };

    const ret = searchStatePersistence().restoreState.call(fakeThis);
    assert.equal(fakeThis.listMode, 'wishlist');
    assert.equal(fakeThis._preWishlistDisplayMode, 'detail');
    assert.equal(switchCalls, 1, 'restoreState 必須 fire-and-forget 呼叫 switchToWishlist 一次');
    assert.equal(ret instanceof Promise, false, 'restoreState 必須維持同步，回傳值不是 Promise');
});

// DoD 4e

// DoD 4f（mutation M3）

// DoD 4f 接線：restoreState 必須真的呼叫 resolveVisibleDisplayMode（純函式測不到這層）

// ─── hydration ①：init() 呼叫 loadWishlistCount ───────────────────────────


// ─── P2-2：兩張卡交錯時計數用增量、不用快照還原 ───────────────────────────


// ─── hydration ②：checkLocalStatus 平行 membership ───────────────────────

test('checkLocalStatus: 平行呼叫 POST /api/wishlist/membership 並寫回 _wishlisted', async () => {
    const calls = mockFetch((url) => {
        if (url.includes('/api/search/local-status')) {
            return jsonResponse({ 'SSIS-001': { exists: true } });
        }
        if (url.includes('/api/wishlist/membership')) {
            return jsonResponse({ 'SSIS-001': true, 'SSIS-002': false });
        }
        return jsonResponse({});
    });

    const results = [
        { number: 'SSIS-001' },
        { number: 'SSIS-002' },
    ];
    await searchStateBase().checkLocalStatus.call({}, results);

    const membershipCalls = calls.filter((c) => c.url.includes('/api/wishlist/membership'));
    const localCalls = calls.filter((c) => c.url.includes('/api/search/local-status'));
    assert.equal(membershipCalls.length, 1, '應呼叫 membership 一次');
    assert.equal(localCalls.length, 1, '既有 local-status 仍應呼叫');
    assert.equal(membershipCalls[0].opts.method, 'POST');
    const body = JSON.parse(membershipCalls[0].opts.body);
    assert.deepEqual(body.numbers, ['SSIS-001', 'SSIS-002']);

    assert.equal(results[0]._wishlisted, true);
    assert.equal(results[1]._wishlisted, false);
    assert.deepEqual(results[0]._localStatus, { exists: true });
});


test('checkLocalStatus: 150 個番號分兩批查 local-status（每批 ≤100），兩批結果都套到對應卡', async () => {
    const calls = mockFetch((url) => {
        if (url.includes('/api/search/local-status')) {
            const nums = decodeURIComponent(url.split('numbers=')[1]).split(',');
            const body = {};
            nums.forEach((n) => { body[n] = { exists: true }; });
            return jsonResponse(body);
        }
        return jsonResponse({});
    });
    const results = Array.from({ length: 150 }, (_, i) => ({ number: `ABC-${String(i + 1).padStart(3, '0')}` }));
    const events = [];
    globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
    globalThis.dispatchEvent = (e) => events.push(e);

    await searchStateBase().checkLocalStatus.call({}, results);

    const localCalls = calls.filter((c) => c.url.includes('/api/search/local-status'));
    assert.equal(localCalls.length, 2);
    for (const c of localCalls) {
        assert.ok(decodeURIComponent(c.url.split('numbers=')[1]).split(',').length <= 100);
    }
    assert.equal(results[0]._localStatus?.exists, true);
    assert.equal(results[149]._localStatus?.exists, true);
    const matchEvents = events.filter((e) => e.type === 'search:local-match');
    assert.equal(matchEvents.length, 1);
    assert.equal(matchEvents[0].detail.numbers.length, 150);
});

test('checkLocalStatus: 任一批失敗＝整包不套用 _localStatus', async () => {
    let n = 0;
    mockFetch((url) => {
        if (url.includes('/api/search/local-status')) {
            n++;
            return n === 1
                ? jsonResponse({}, { ok: false, status: 500 })
                : jsonResponse({ 'ABC-150': { exists: true } });
        }
        return jsonResponse({});
    });
    const results = Array.from({ length: 150 }, (_, i) => ({ number: `ABC-${String(i + 1).padStart(3, '0')}` }));
    await searchStateBase().checkLocalStatus.call({}, results);
    assert.ok(results.every((r) => r._localStatus === undefined));
});

// ─── switchToWishlist displayMode ─────────────────────────────────────────


test('switchToWishlist: 已載入過也要重新對帳（T8 review P2）', async () => {
    // spec F6 的對帳時機是「開啟書籤清單時」——每一次，不是只有第一次。
    // 只在 !wishlistLoaded 時載入的話：你把書籤裡的片掃描入庫 → 切回書籤分頁 →
    // 角標不會出現、卡片也不會沉底，除非整頁重新整理。
    let loadCalls = 0;
    const fakeThis = {
        ...searchStateWishlist(),
        listMode: 'search',
        displayMode: 'grid',
        wishlistLoaded: true,          // 已經載入過
        wishlistItems: [{ number: 'OLD-001' }],
        async loadWishlist() { loadCalls++; },
    };

    await searchStateWishlist().switchToWishlist.call(fakeThis);
    assert.equal(loadCalls, 1, '已載入過仍必須重新對帳一次');
});

test('T2-DoD6b-reentry-still-loads: listMode 已經是 wishlist 時（restoreState 路徑）仍必須呼叫 loadWishlist', async () => {
    // 🔴 這條守的是 persistence.js:171-178 的硬約束，Opus 2026-09-03 補。
    // restoreState() 會**先**把 this.listMode 設成 'wishlist'（為了不讓 switchToWishlist()
    // 內部的前置記錄覆寫掉剛還原的 _preWishlistDisplayMode），**再**呼叫 switchToWishlist()
    // ——它就是靠這一呼去 loadWishlist()，因為 wishlistItems 不進 sessionStorage。
    //
    // T2 為了不對「已經在書籤牆」的重入播 crossfade，加了一條
    // `if (this.listMode === 'wishlist') return doSwitch();` 的短路。
    // 那一行看起來像一顆多餘的重入守衛，**下一個人很容易把它「簡化」成 `return;`**——
    // 而那個簡化沒有任何既有測試會轉紅（實測：改掉之後 70/70 全綠）。
    //
    // 使用者流程：停在書籤分頁 → 重新整理（或關掉再打開）→ 整面書籤牆永久空白，
    // 直到手動切去搜尋結果再切回來。本測試就是為了讓那個簡化轉紅。
    let loadCalls = 0;
    const fakeThis = {
        ...searchStateWishlist(),
        listMode: 'wishlist',          // restoreState 已經先設好
        displayMode: 'grid',
        wishlistLoaded: false,
        wishlistItems: [],
        async loadWishlist() { loadCalls++; },
    };

    await searchStateWishlist().switchToWishlist.call(fakeThis);
    assert.equal(loadCalls, 1, 'listMode 已是 wishlist 的重入路徑仍必須載入清單（persistence.js restore 靠這一呼）');
});

// ─── loadWishlistCount / loadWishlist ─────────────────────────────────────


// branch review P2（2026-09-02）：對帳在伺服器端自動刪書籤之後，前端唯一能感知
// 「權威狀態變了」的通道就是這支 GET 的回應。它以前只寫清單不寫計數 ⇒ badge 會停在
// 舊數字直到整頁重新整理。


// ─── TASK-141b-T10／CD-19：封面載入狀態不得掛在 wishlistItems 元素物件上 ───
// 不變式：同一番號、同一封面 URL，loadWishlist() 跑第二次（回傳等值但全新的物件陣列）
// 之後，該卡的封面仍為可見狀態（_wishlistCoverLoaded[番號] 仍為 true）。
// 候選 (a)：狀態掛在 wishlist.js state 上的番號→bool map，loadWishlist() 完全不碰。

// ─── hydration ③：wishlistLoaded 時同步 wishlistItems ─────────────────────

test('addToWishlist: wishlistLoaded=true 時新項目 unshift 到 wishlistItems[0]', async () => {
    mockFetch(() => jsonResponse({ success: true, cover_available: false }));
    const existing = { number: 'OLD-1' };
    const result = {
        number: 'NEW-1', title: 't', actors: [], tags: [], maker: '', director: '',
        series: '', label: '', duration: null, date: '', cover: '', preview_cover_url: '',
        sample_images: [], preview_sample_images: [], source: '', url: '',
    };
    const fakeThis = {
        ...searchStateWishlist(),
        wishlistCount: 1,
        wishlistLoaded: true,
        wishlistItems: [existing],
    };

    await searchStateWishlist().addToWishlist.call(fakeThis, result);
    assert.equal(fakeThis.wishlistItems[0].number, 'NEW-1');
    assert.equal(fakeThis.wishlistItems[1], existing);
    assert.equal(result._wishlisted, true);
    assert.equal(fakeThis.wishlistCount, 2);
});

test('removeFromWishlist: wishlistLoaded=true 時從 wishlistItems 移除', async () => {
    mockFetch(() => jsonResponse({ success: true }));
    const fakeThis = {
        ...searchStateWishlist(),
        wishlistCount: 2,
        wishlistLoaded: true,
        wishlistItems: [{ number: 'A-1' }, { number: 'B-2' }],
        searchResults: [{ number: 'A-1', _wishlisted: true }],
    };

    await searchStateWishlist().removeFromWishlist.call(fakeThis, 'A-1');
    assert.deepEqual(fakeThis.wishlistItems.map((i) => i.number), ['B-2']);
    assert.equal(fakeThis.wishlistCount, 1);
    assert.equal(fakeThis.searchResults[0]._wishlisted, false);
});

// ─── I3 不變式（mutation M3）──────────────────────────────────────────────

test('addToWishlist: POST 失敗時回滾 _wishlisted 與 wishlistCount（I3）', async () => {
    mockFetch(() => jsonResponse({}, { ok: false, status: 500 }));
    const result = { number: 'FAIL-1', title: 'x', _wishlisted: false };
    // PR#176 第 2 輪：原本 fixture 是 `wishlistCount: 5` 配 1 筆 wishlistItems，
    // 那是**生產環境不可能存在的狀態**——`loadWishlist()` 是全站唯一把 wishlistLoaded
    // 設為 true 的地方，而它整包同時寫入清單與計數，兩者必然相等。合成 fixture 把這條
    // 不變式抹平了，於是這支測試從來沒有真的驗到「計數與清單說同一件事」。
    // 改成自洽的 1／1 之後，斷言的意圖（失敗要回滾三件事）完全不變，且更嚴格。
    const fakeThis = {
        ...searchStateWishlist(),
        wishlistCount: 1,
        wishlistLoaded: true,
        wishlistItems: [{ number: 'KEEP-1' }],
    };

    await searchStateWishlist().addToWishlist.call(fakeThis, result);
    assert.equal(result._wishlisted, false, '失敗應回滾 _wishlisted');
    assert.equal(fakeThis.wishlistCount, 1, '失敗應回滾 wishlistCount');
    assert.deepEqual(
        fakeThis.wishlistItems.map((i) => i.number),
        ['KEEP-1'],
        '失敗應回滾樂觀 unshift',
    );
});


// DoD 4c（mutation M2）— 測試名必須逐字等於 mutation expect_fail

// DoD 4e

// T11a 第 2 輪：破圖 flag 殘留——看過一張 404 封面後再開別張會一直顯示占位

// Opus 2026-09-02 補（grok 自報偏離 #2）：箭頭換片也要重設，否則先看到一部沒封面的片、
// 再按箭頭切到有封面的那部，封面不會出現——畫面停在「無圖」占位。

// ─── 書籤載入與交錯（TASK-140-T12 起，141a-T4/T6 之後只剩載入端）──────────────

// 技術要點 §4：plain spread 會在展開當下求值 getter 並凍結成 0，必須保留 descriptor。
//
// Codex review P2 修正後，loadWishlist() 會用到 search-flow 的
// AbortController registry（_getAbortSignal／_clearAbort／_abortControllers）。照
// set-file-list-race.test.mjs 的既有手法**組真的 mixin**，不手抄 abort 邏輯——手抄的話
// 產品端改了機制測試不會紅。_abortControllers 由 base.js:118 宣告，這裡補上同一個初始值。
function makeWishlistThis(overrides = {}) {
    const target = {};
    Object.defineProperties(target, Object.getOwnPropertyDescriptors(searchStateSearchFlow()));
    Object.defineProperties(target, Object.getOwnPropertyDescriptors(searchStateWishlist()));
    target._abortControllers = {};
    Object.assign(target, overrides);
    return target;
}

// ─── Codex review P2（Opus 2026-09-02）：非同步 fetch 交錯 ─────────────────
//
// T12 的卡片把「背景 worker 交錯」勾成 N/A 是對的（沒有背景任務），但漏掉了另一種
// 交錯：`switchToSearchList()` 不清空 `wishlistItems`，所以切回書籤分頁的瞬間，畫面
// 會先用**上一次的舊資料**把卡片與垃圾桶鈕渲染出來，而新的 GET 還在飛。
// 使用者於是能在那個窗口裡按某張卡的垃圾桶。窗口不是理論值——
// `GET /api/wishlist` 現在**先對帳再回清單**（141a-T4），對帳要對每一筆書籤查一次片庫。
// （141a-T1 之前那支查詢的 `UPPER(number)` 吃不到索引、實測是 `SCAN videos`；
// 加了 `idx_videos_number_upper` 之後成本只跟書籤數有關，但窗口仍在：網路 ＋ 對帳 ＋ 刪封面檔。）
//
// 手法照 set-file-list-race.test.mjs：mock 尊重 AbortSignal（有 signal 才會在 abort 時
// reject），所以「產品端忘了把 signal 傳進 fetch」這個回歸也會被這兩條測出來。

function makeAbortError() {
    return new DOMException('The operation was aborted', 'AbortError');
}

test('deferred-fetch：連續兩次 loadWishlist，舊 GET 晚到不得覆蓋新結果', async () => {
    globalThis.window.t = (key) => key;
    let releaseGet1;
    const get1Released = new Promise((r) => { releaseGet1 = r; });
    const staleFromServer = [{ number: 'OWNED-1' }, { number: 'FREE-1' }];
    const freshFromServer = [{ number: 'FREE-1' }];

    let get1Signal;
    let getCall = 0;
    globalThis.fetch = async (url, opts = {}) => {
        const u = String(url);
        if (u === '/api/wishlist') {
            getCall += 1;
            if (getCall === 1) {
                return new Promise((resolve, reject) => {
                    const { signal } = opts;
                    get1Signal = signal;
                    if (signal) {
                        if (signal.aborted) { reject(makeAbortError()); return; }
                        signal.addEventListener('abort', () => reject(makeAbortError()), { once: true });
                    }
                    get1Released.then(() => resolve(jsonResponse(staleFromServer)));
                });
            }
            return jsonResponse(freshFromServer);
        }
        throw new Error(`unexpected url: ${u}`);
    };

    const state = makeWishlistThis({
        wishlistCount: 2,
        wishlistLoaded: true,
        wishlistItems: staleFromServer.map((i) => ({ ...i })),
        showToast() {},
    });

    const pendingGet1 = state.loadWishlist();
    const pendingGet2 = state.loadWishlist();
    await pendingGet2;
    releaseGet1();
    await pendingGet1;

    assert.deepEqual(
        state.wishlistItems.map((i) => i.number),
        ['FREE-1'],
        '第一次那個晚到的回應不得覆蓋 wishlistItems',
    );
    assert.ok(get1Signal instanceof AbortSignal, 'GET 必須把 AbortSignal 傳進 fetch');
    assert.equal(get1Signal.aborted, true, '第二次 loadWishlist 必須 abort 掉第一次在飛的 GET');
});


// Codex 二審 P2（改指向 T4）：對帳觸發點改成 GET /api/wishlist 後，仍要守住
// switchToSearchList → switchToWishlist 這條 tab 切換路徑上的 abort registry。

// branch review P2-1：POST 回 added:false（那個番號本來就在）時，樂觀 +1 必須收回。
// 到達路徑：切換版本把整顆結果物件換掉 ⇒ `_wishlisted` 一起沒了 ⇒ 卡片變回「加入書籤」
// ⇒ 再按一次。與 removeFromWishlist 的 success:false 是同一組對稱處置。

// Codex PR#175 P2：切進書籤前的 listMode 必須被記住並還原。
// 實測重現過：listMode:'file'（把影片檔拖進來比對）→ 點書籤 → 點回搜尋 ⇒ listMode 落在
// 'search'，fileList 資料還在記憶體裡但 #fileList 連同整理列／改番號控制項全部隱藏，
// 使用者的拖曳工作階段看起來整個不見了。
test('switchToWishlist→switchToSearchList：從 file 模式進書籤再回來，必須回到 file 而不是 search', async () => {
    mockFetch(() => jsonResponse([]));
    const state = makeWishlistThis({
        listMode: 'file',
        displayMode: 'detail',
        wishlistLoaded: true,
        fileList: [{ path: '/x/a.mp4', searchResults: [] }],
    });

    state.switchToWishlist();
    assert.equal(state.listMode, 'wishlist');

    state.switchToSearchList();
    assert.equal(state.listMode, 'file', '必須回到切進書籤前的 file 模式');
    assert.equal(state.displayMode, 'detail');
    assert.equal(state._preWishlistListMode, null, '還原後要清掉，不得殘留');
    assert.equal(state.fileList.length, 1, 'fileList 不得被動到');
});


// ─── TASK-141a-T3：加入書籤寫入點守門（already_owned）──────────────────────

test('T3-DoD3：already_owned ⇒ 回滾三件事、設 _localStatus、info toast（非 error）', async () => {
    const localStatus = {
        exists: true,
        count: 1,
        paths: ['/lib/OWNED-1.mp4'],
    };
    globalThis.fetch = async (url, opts = {}) => {
        const u = String(url);
        if (u === '/api/wishlist' && opts.method === 'POST') {
            return jsonResponse({
                success: false,
                already_owned: true,
                local_status: localStatus,
            });
        }
        throw new Error(`unexpected url: ${u}`);
    };
    globalThis.window.t = (key) => key;

    const toasts = [];
    const existing = { number: 'KEEP-1' };
    const result = { number: 'OWNED-1', title: 't', _wishlisted: false };
    // PR#176 第 2 輪：同上——wishlistLoaded:true 時計數必等於清單長度，原本的 3／1 不自洽。
    const state = makeWishlistThis({
        wishlistCount: 1,
        wishlistLoaded: true,
        wishlistItems: [existing],
        showToast(msg, type) { toasts.push({ msg, type }); },
    });

    await state.addToWishlist(result);

    assert.deepEqual(result._localStatus, localStatus,
        '_localStatus 必須等於回應的 local_status（逐欄位）');
    assert.equal(result._wishlisted, false, '_wishlisted 必須回滾成呼叫前的值');
    assert.equal(state.wishlistCount, 1, 'wishlistCount 必須回滾');
    assert.deepEqual(state.wishlistItems, [existing],
        'wishlistItems 不得含樂觀 unshift 的那筆');
    assert.equal(toasts.length, 1, '必須顯示 toast');
    assert.equal(toasts[0].type, 'info', 'toast 等級必須是 info，不是 error');
    assert.equal(toasts[0].msg, 'search.toast.wishlist_already_owned');
    assert.ok(!toasts.some((t) => t.type === 'error'), '不得顯示 error 等級 toast');
});


// ===== TASK-141b-T5: 書籤燈箱觸控滑動 =====

function makeSwipeSpies(overrides = {}) {
    const nextCalls = [];
    const prevCalls = [];
    return {
        nextCalls,
        prevCalls,
        nextWishlistLightbox() { nextCalls.push(true); },
        prevWishlistLightbox() { prevCalls.push(true); },
        ...overrides,
    };
}

test('T5-DoD1-swipe-left-calls-next-not-prev', () => {
    // 座標刻意挑選（見「技術要點」5）：同時覆蓋 DoD1（方向）與 DoD2（順序不變式）——
    // 若實作把 dir 算在「清空 state 之後」讀，detectSwipe(null, null, 100, 150, 50) 回 null，
    // 兩個 spy 都不會被呼叫，下面的 assert.equal(nextCalls.length, 1) 會失敗。
    const spies = makeSwipeSpies();
    const state = makeWishlistThis({ ...spies, wishlistLightboxOpen: true });
    searchStateWishlist()._wishlistLbTouchStart.call(state, { touches: [{ clientX: 500, clientY: 100 }] });
    searchStateWishlist()._wishlistLbTouchEnd.call(state, { changedTouches: [{ clientX: 100, clientY: 150 }] });
    assert.equal(spies.nextCalls.length, 1, '左滑必須呼叫 nextWishlistLightbox 恰好一次');
    assert.equal(spies.prevCalls.length, 0, '左滑不得呼叫 prevWishlistLightbox');
    assert.equal(state._wishlistLbTouchStartX, null, 'touchend 之後座標必須清回 null（DoD 7）');
    assert.equal(state._wishlistLbTouchStartY, null);
});


// ─── TASK-141b-T7：書籤燈箱移除鈕 ＋ 索引收斂 ──────────────────────────

function makeRemoveSpy(state) {
    // 薄封裝的測試手法：spy 取代真實 removeFromWishlist，但仍做等價的同步過濾，
    // 讓 DoD1-3 的索引收斂邏輯可以在不牽動 fetch/FLIP 的情況下被獨立驗證。
    const calls = [];
    state.removeFromWishlist = function (number, context) {
        calls.push({ number, context });
        this.wishlistItems = this.wishlistItems.filter((i) => i.number !== number);
        return Promise.resolve();
    };
    return calls;
}

test('T7-DoD1-remove-middle-keeps-index-not-close', () => {
    const state = makeWishlistThis({
        wishlistItems: [{ number: 'A' }, { number: 'B' }, { number: 'C' }, { number: 'D' }, { number: 'E' }],
        wishlistLightboxOpen: true,
        wishlistLightboxIndex: 2,
        _wishlistLbImgError: true,
    });
    const removeCalls = makeRemoveSpy(state);
    const closeCalls = [];
    state.closeWishlistLightbox = () => { closeCalls.push(1); };

    searchStateWishlist().removeFromWishlistInLightbox.call(state);

    assert.equal(removeCalls.length, 1, '必須呼叫既有 removeFromWishlist 恰好一次');
    assert.deepEqual(removeCalls[0], { number: 'C', context: 'lightbox' },
        '移除的必須是 index=2 對應的那一筆（C），context 必須是 lightbox');
    assert.equal(closeCalls.length, 0, '非最後一筆時不得呼叫 closeWishlistLightbox');
    assert.equal(state.wishlistLightboxIndex, 2, '刪中間，索引維持原值（畫面顯示遞補上來的那張）');
    assert.equal(state._wishlistLbImgError, false, '收斂後必須重設破圖旗標');
    assert.equal(state.wishlistItems.length, 4);
});


// ─── branch review P3-8（Opus 2026-09-03）：燈箱沒開時觸控不得換片 ───
// 主燈箱有三條短路（`grid-mode.js:448-455`），T5 鏡射時漏抄第三條「燈箱沒開不換片」。
// 今天碰不到是因為 `.showcase-lightbox` 關著時 `pointer-events: none`（showcase.css:857）——
// 但那是**別的檔案的樣式**在替這支 handler 擋，不是 handler 自己守住的。

// ─── Codex PR#177 第 2 輪 P2（Opus 2026-09-03）：破圖旗標要有回得來的路 ───
//
// 🔴 不變式：**封面檔從「不存在」變成「存在」的那一刻，:src 必須變一次。**
//
// 為什麼：`add_wishlist()` 是**先 commit 那一列、才下載封面**
// （web/routers/wishlist.py:69 → :90）。使用者按下加入之後馬上點書籤分頁，
// GET 拿到的列已經有 created_at、封面檔卻還沒寫完 ⇒ 404 ⇒ `_wishlistCoverError`
// 永久（CD-19 刻意不讓 loadWishlist() 碰它）⇒ 那部片在牆上是灰底占位，只有 F5 才會好。
// **真瀏覽器實測：延遲 100ms 就撞得到。**
//
// ⚠️ 光把旗標清掉沒有用——實測清了 img 也不會重新請求（naturalWidth 仍 0、complete 仍 true），
// 只會把整齊的占位換成破圖 icon。唯一有效的手段是**讓 URL 變**，所以是 token 不是布林。
//
// 上一輪（同一 artifact）的修法只治了「不要發那個必定 404 的請求」；這一條是它的另一半。
// 依 CLAUDE.md 停損 ①，這不是在同一個機制上疊補丁——兩者合起來是一條規則：
// **請求只在檔案應該存在時發出；檔案剛變成存在時讓 URL 變一次。**


// ─── Codex PR#177 第 3 輪 P3（Opus 2026-09-03）：過期回呼不得拔掉現任世代的 flip-guard ───
//
// 🔴 不變式：**最新那一次 FLIP 開始播的當下，`flip-guard` 必須在 grid 上。**
//
// rAF 回呼依註冊順序執行，所以連按兩張卡的垃圾桶時是
// A(stale) 先跑 → `remove('flip-guard')` → B(current) 才跑 ⇒ **最新那次在沒有 guard 的
// 情況下開始播**，而那個 class 存在的唯一理由就是在動畫期間把 hover 的 transform
// 從 transition list 拿掉（theme.css B15）。
//
// ⚠️ 為什麼不是改成「stale 分支不要 remove」：那會讓
// 世代不符的 stale 分支就沒人接手清理 flip-guard——那條殘留範圍比本條更廣，
// 不該為了本條把它變弱。改用**冪等的重新宣告**：
// class 已在就沒事、被上一個世代拔掉就補回來，移除的責任完全沒有改變。
//
// 這個 race 的窗口在正常裝置上只有一個 frame（≈16.7ms），但 rAF 被推遲多久窗口就變寬多少
// （這段路徑每次都強制 reflow，弱裝置上會放大）。後果是純視覺：333ms 內、且滑鼠剛好停在
// 剩下的某張卡上時會看到一下抖動。


// ─── Codex PR#177 第 3 輪窮舉盤點（Opus 2026-09-03）：三張封面表必須整組動 ───
//
// 🔴 不變式：**三張表描述的是「`:src` 這一刻算出來的那條 URL」的載入結果，
//            不是「這個番號」的歷史 ⇒ 凡是 URL／資源身分改變的事件，三張一起動。**
//
// 前兩輪各補了一角（error 旗標、retry token），第三輪的 finding 是 `loaded` 沒被算進那一組：
// 移除書籤會把封面檔一起刪掉（routers/wishlist.py:141），之後重新加入拿到的是**全新的一份**，
// 而 `_wishlistCoverLoaded[n]` 還留著上一份的 true ⇒ 新卡片跳過骨架直接顯示。
//
// 下面第二支測的是**位置**：`cover_available` 區塊必須在 `already_owned` / `added:false`
// 兩個早退**之前**。後端在 `added:false` 時一樣算好了那個欄位（檔案存不存在），
// 早退會把它丟掉——那是「吃到 404 窗口 → 切版本 → 再按一次加入」永遠灰底無圖的成因。

test('P3-cover-state-cleared-as-a-group-on-successful-add', async () => {
    mockFetch((url, opts) => {
        if (opts.method === 'POST') return jsonResponse({ success: true, added: true, cover_available: true });
        return jsonResponse([]);
    });
    const state = makeWishlistThis({ wishlistLoaded: false, wishlistCount: 0, searchResults: [] });
    // 模擬「這個番號先前被移除過，而移除前它的封面已經載入成功」
    state._wishlistCoverLoaded['RE-1'] = true;
    state._wishlistCoverError['RE-1'] = true;

    await state.addToWishlist({ number: 'RE-1' });

    assert.equal(state._wishlistCoverLoaded['RE-1'], undefined,
        'loaded 必須一起作廢——移除會刪掉封面檔，重新加入拿到的是全新的一份');
    assert.equal(state._wishlistCoverError['RE-1'], undefined, 'error 一起作廢');
    assert.ok(state._wishlistCoverRetry['RE-1'], 'token 一起 bump（讓 URL 真的變一次）');
});

