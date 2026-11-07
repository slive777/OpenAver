// 195b-T4: 「隱藏未連線硬碟」資料層接線（真 stateBase/stateVideos/stateLightbox/stateSimilar/
// stateDelete/stateHiddenSources + 假 fetch + 假計時器）。純函式見 shared/__tests__/hidden-sources.test.mjs。
// FE-GUARD-11：window/document stub + importmap resolve hook 在匯入前就位。
// FE-GUARD-13：_allVideos/_videos/_filteredVideos 是模組級單例 → 每案例 resetModule()，元件每案例新建。
import { test, mock } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.Alpine = globalThis.Alpine || { store: () => ({ toolbarOpen: false, showcaseHasSearch: false }) };
globalThis.document = {
    querySelector() { return null; },
    body: { classList: { remove() {}, add() {}, contains() { return false; } } },
};

const IMPORTMAP = {
    '@/settings/': 'pages/settings/', '@/shared/': 'shared/', '@/components/': 'components/',
    '@/search/': 'pages/search/', '@/showcase/': 'pages/showcase/', '@/scanner/': 'pages/scanner/',
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
    if (specifier.startsWith('@/')) return nextResolve(STATIC_JS_ROOT + specifier.slice(2), context);
    return nextResolve(specifier, context);
}
`;
register(`data:text/javascript,${encodeURIComponent(loaderCode)}`, import.meta.url);

const base = await import('../state-base.js');
const { _videos, _allVideos, _filteredVideos, _setAllVideos, _setVideos, _setFilteredVideos,
    _recomputeAllBadges, _loadCoverBadgeManifest } = base;
const { stateVideos } = await import('../state-videos.js');
const { stateLightbox } = await import('../state-lightbox.js');
const { stateSimilar } = await import('../state-similar.js');
const { stateDelete } = await import('../state-delete.js');
const { stateHiddenSources } = await import('../state-hidden-sources.js');
const { footerNotice } = await import('@/shared/hidden-sources.js');

const SOURCES = ['D:\\電影', 'E:\\FC2'];
const OFFLINE_D = [{ reason: 'unreachable', display: 'D:', members: ['D:\\電影'] }];
const MANIFEST = [{ id: 'sub', canonical_tag: '中文字幕', match_aliases: [], display_name: '字幕', display_order: 1 }];
const mk = (n, src, extra) => {
    const v = { number: n, path: 'file:///m/' + n + '.mp4', ...extra };
    if (src !== undefined) v.src = src;
    return v;
};
// D: 離線時被藏的是 AAA／DDD／FFF（src 0）；src 缺欄位的 CCC 與 E: 的片可見。
const fixture = () => [
    mk('AAA-001', 0, { tags: '中文字幕' }), mk('BBB-002', 1), mk('CCC-003', undefined, { tags: '中文字幕' }),
    mk('DDD-004', 0), mk('EEE-005', 1, { tags: '中文字幕' }), mk('FFF-006', 0),
];
const numbers = (arr) => arr.map((v) => v.number);
const paths = (arr) => arr.map((v) => v.path);

function resetModule(vids) {
    _setAllVideos(vids); _setVideos(vids); _setFilteredVideos(vids);
}

function makeComponent(overrides = {}) {
    const c = Object.assign({}, base.stateBase.call({ $persist: (o) => ({ as: () => o }) }),
        stateVideos(), stateLightbox(), stateSimilar(), stateDelete(), stateHiddenSources(), {
            pills: [], toasts: [], filterCalls: 0,
            applyFilterAndSort() { c.filterCalls++; _setFilteredVideos(_videos); c.filteredCount = _filteredVideos.length; },
            showToast(msg, kind) { c.toasts.push({ msg, kind }); },
            _resetMask() {}, _closePicker() {}, _navBlockedByFocalEdit() { return false; },
            $nextTick(fn) { if (typeof fn === 'function') fn(); },
        }, overrides);
    return c;
}

/** 依 URL 分派的假 fetch；一律忽略 signal。回傳 { calls, restore }。 */
function stubFetch(handler) {
    const prev = globalThis.fetch;
    const calls = [];
    globalThis.fetch = (url, opts) => { calls.push({ url, method: opts && opts.method }); return handler(url, opts || {}); };
    return { calls, restore() { globalThis.fetch = prev; } };
}
const jsonResp = (body) => ({ ok: true, status: 200, json: async () => body });
const putOk = () => jsonResp({ success: true });
const tickMicro = async (n = 50) => { for (let i = 0; i < n; i++) await Promise.resolve(); };

/** 開關關、載入全庫、D: 離線，然後 hsSetHide(true)：回傳已隱藏的元件。 */
async function hiddenComponent(vids = fixture(), overrides = {}) {
    resetModule(vids);
    const c = makeComponent(overrides);
    c._hsSources = SOURCES; c._hsOfflineKeys = ['D:\\電影'];
    const fx = stubFetch(putOk);
    try { await c.hsSetHide(true); } finally { fx.restore(); }
    return c;
}

// ── 1. 往返 ＋ 封面屬性標籤 ───────────────────────────────────────────

test('開關 關→開→關往返：_videos 內容與順序、每張封面屬性標籤都跟沒隱藏過的一樣', async () => {
    const cfg = globalThis.__SHOWCASE_CONFIG__;
    globalThis.__SHOWCASE_CONFIG__ = { cover_badges: { enabled: true } };
    const fx = stubFetch(async (url) => jsonResp(MANIFEST));
    try {
        await _loadCoverBadgeManifest();
        resetModule(fixture());
        const c = makeComponent();
        c._hsSources = SOURCES; c._hsOfflineKeys = ['D:\\電影'];
        c._recomputeVisible();
        _recomputeAllBadges();
        const snapPaths = paths(_videos);
        const snapBadges = _allVideos.map((v) => JSON.stringify(v._badges));
        assert.ok(snapBadges.some((s) => s !== '[]'), 'fixture 要真的產得出標籤，否則比對是空轉');
        assert.equal(c.hiddenCount, 0);

        fx.restore();
        const put = stubFetch(putOk);
        try {
            await c.hsSetHide(true);
            assert.deepEqual(numbers(_videos), ['BBB-002', 'CCC-003', 'EEE-005']);
            assert.equal(c.hiddenCount, 3);
            _allVideos.forEach((v) => { delete v._badges; });
            _recomputeAllBadges();   // 被藏的 AAA／DDD／FFF 也要有 _badges
            assert.deepEqual(_allVideos.map((v) => JSON.stringify(v._badges)), snapBadges);
            await c.hsSetHide(false);
        } finally { put.restore(); }
        assert.deepEqual(paths(_videos), snapPaths, '關回來後內容與順序跟沒隱藏過一樣');
        assert.equal(c.hiddenCount, 0);
        assert.equal(c.hiddenSrcIdx.size, 0);
        assert.deepEqual(_allVideos.map((v) => JSON.stringify(v._badges)), snapBadges);
    } finally {
        fx.restore();
        globalThis.__SHOWCASE_CONFIG__ = cfg;
    }
});

// ── 2. 刪除 ───────────────────────────────────────────────────────────

test('刪除一筆後切換開關，已刪的片不會復活', async () => {
    const c = await hiddenComponent();
    assert.deepEqual(numbers(_videos), ['BBB-002', 'CCC-003', 'EEE-005']);
    c.closeLightbox = () => {};
    c._pendingDeletePath = 'file:///m/BBB-002.mp4';
    const fx = stubFetch(async (url, opts) => (opts.method === 'DELETE' ? jsonResp({}) : putOk()));
    try {
        await c.confirmDeleteVideo();
        assert.ok(!numbers(_videos).includes('BBB-002'));
        assert.ok(!numbers(_allVideos).includes('BBB-002'), '全庫也要同步移除');
        await c.hsSetHide(false);
    } finally { fx.restore(); }
    assert.deepEqual(numbers(_videos), ['AAA-001', 'CCC-003', 'DDD-004', 'EEE-005', 'FFF-006']);
    assert.equal(c.hiddenCount, 0);
});

test('刪除請求在飛時該片被藏：DELETE 成功後 hiddenCount 隨全庫更新，牆不動', async () => {
    resetModule(fixture());
    const c = makeComponent({ closeLightbox() {} });
    c._hsSources = SOURCES; c._hsOfflineKeys = ['D:\\電影'];
    c._pendingDeletePath = 'file:///m/AAA-001.mp4';
    const gate = makeGate();
    const fx = stubFetch(async (url, opts) => (opts.method === 'DELETE' ? (await gate.promise, jsonResp({})) : putOk()));
    try {
        const deleting = c.confirmDeleteVideo();
        await c.hsSetHide(true);
        assert.equal(c.hiddenCount, 3);
        const calls = c.filterCalls;
        gate.flush();
        await deleting;
        assert.ok(!numbers(_allVideos).includes('AAA-001'));
        assert.equal(c.hiddenCount, 2, 'AAA 刪掉後只剩 DDD／FFF 被藏');
        assert.equal(c.videoCount, 3);
        assert.equal(c.filterCalls, calls + 1, '只有 confirmDeleteVideo 自己那次 apply');
    } finally { gate.flush(); fx.restore(); }
});

// ── 3. 相似結果 ───────────────────────────────────────────────────────

test('_fetchSimilarResults：濾掉被藏番號，其餘順序不變；沒有被藏番號時與原回應逐值相同', async () => {
    const mkResp = () => ({
        query_video: { number: 'BBB-002' },
        results: ['bbb-002', 'AAA-001', 'zzz-100', 'ddd-004', 'YYY-200'].map((n) => ({ number: n, cover_url: '/c/' + n })),
    });
    const c = await hiddenComponent();
    const fx = stubFetch(async (url) => (String(url).startsWith('/api/similar-covers/by-number/') ? jsonResp(mkResp()) : putOk()));
    try {
        const out = await c._fetchSimilarResults('BBB-002');
        assert.deepEqual(numbers(out.results), ['bbb-002', 'zzz-100', 'YYY-200']);
        assert.deepEqual(out.query_video, { number: 'BBB-002' });
        await c.hsSetHide(false);
        assert.deepEqual(await c._fetchSimilarResults('BBB-002'), mkResp());
    } finally { fx.restore(); }
});

// ── 5. 燈箱開著時隱藏集合改變（plan C-1 oracle ①②③）──────────────────────

/** 7 片：p0 在 D:（開關開後被藏），p1..p6 可見。 */
const lightboxFixture = () => [mk('P0-000', 0), ...[1, 2, 3, 4, 5, 6].map((i) => mk('P' + i + '-00' + i, 1))];

function openLightboxAt(c, idx) {
    c.lightboxOpen = true;
    c.lightboxIndex = idx;
    c.currentLightboxVideo = { ..._filteredVideos[idx] };   // 物件身分不同、path 相同（Proxy 情境）
}

test('C-1 ①：燈箱開在第 5 片，前面的片被藏 → lightboxIndex 仍指原片，「下一部」落在新清單的下一片', async () => {
    resetModule(lightboxFixture());
    const c = makeComponent();
    c._hsSources = SOURCES; c._hsOfflineKeys = ['D:\\電影'];
    c._recomputeVisible();
    c.applyFilterAndSort();
    openLightboxAt(c, 4);
    assert.equal(c.currentLightboxVideo.number, 'P4-004');
    const fx = stubFetch(putOk);
    try { await c.hsSetHide(true); } finally { fx.restore(); }
    assert.equal(c.lightboxOpen, true);
    assert.equal(c.lightboxIndex, 3, '前面少一片，原片的索引要往前挪一格');
    assert.equal(_filteredVideos[c.lightboxIndex].number, 'P4-004');
    c.nextLightboxVideo();
    assert.equal(c.currentLightboxVideo.number, 'P5-005');
});

test('C-1 ②：燈箱開著的片自己被藏，lightboxOpen 變 false，250ms 後 currentLightboxVideo 清空', async () => {
    resetModule(lightboxFixture());
    const c = makeComponent();
    c._hsSources = SOURCES; c._hsOfflineKeys = ['D:\\電影'];
    c._recomputeVisible();
    c.applyFilterAndSort();
    openLightboxAt(c, 0);   // 正在看 P0（src 0）
    mock.timers.enable({ apis: ['setTimeout'] });
    const fx = stubFetch(putOk);
    try {
        await c.hsSetHide(true);
        assert.equal(c.lightboxOpen, false);
        mock.timers.tick(250);
        assert.equal(c.currentLightboxVideo, null);
    } finally {
        fx.restore();
        mock.timers.reset();
    }
});

test('C-1 ③：隱藏集合沒變 → 狀態照收，但牆與燈箱（lightboxIndex／lightboxOpen／片）逐值不動', async () => {
    const c = await hiddenComponent(lightboxFixture());
    c.applyFilterAndSort();
    openLightboxAt(c, 2);
    const shown = c.currentLightboxVideo, wall = paths(_videos), calls = c.filterCalls;
    const status = [...OFFLINE_D, { reason: 'no_permission', display: '\\\\nas', members: [] }];
    const fx = stubFetch(async () => jsonResp(status));
    try { await c._hsFetchStatus(); } finally { fx.restore(); }
    assert.deepEqual(c.unreachableSources, status);
    assert.equal(c.filterCalls, calls, '集合沒變不得重篩（會把頁碼重置為 1）');
    assert.deepEqual(paths(_videos), wall);
    assert.equal(c.lightboxIndex, 2);
    assert.equal(c.lightboxOpen, true);
    assert.equal(c.currentLightboxVideo, shown);
});

// ── 6. 首屏順序（CD-195-9 O-a／O-b）──────────────────────────────────

/** 手動放行的 gate：flush() 讓被掛住的 source-status 回應。 */
function makeGate() {
    let release; const p = new Promise((r) => { release = r; });
    return { promise: p, flush: () => release() };
}

/** 真的 stateBase.init()；fetchVideos／_hsFetchStatus 用真的，restoreState 設開關為開。 */
async function runInit({ onVideosServed, gate, status = OFFLINE_D, drive, setup }) {
    resetModule([]);
    const snaps = [];
    const c = makeComponent({
        mode: 'list',   // grid 才會碰 requestAnimationFrame（settle 動畫），與本案例無關
        restoreState() { this.hideUnreachable = true; if (setup) setup(this); },
        applyFilterAndSort() { snaps.push(numbers(_videos)); _setFilteredVideos(_videos); },
        updatePagination() {}, $watch() {}, loadActresses() {}, _reconcileHeroCard() {},
        init: base.stateBase.call({ $persist: (o) => ({ as: () => o }) }).init,
    });
    const fx = stubFetch(async (url) => {
        if (url === '/api/showcase/videos') {
            if (onVideosServed) onVideosServed();
            return jsonResp({ success: true, videos: fixture(), sources: SOURCES });
        }
        if (url === '/api/showcase/source-status') return gate.promise.then(() => jsonResp(status));
        if (url === '/api/cover-badges/manifest') return jsonResp([]);
        if (url === '/api/actress-aliases' || url === '/api/tag-aliases') return jsonResp({ groups: [] });
        return jsonResp({});
    });
    const prevReg = globalThis.window.__registerPage;
    const prevWinAdd = globalThis.window.addEventListener;
    const prevWinRemove = globalThis.window.removeEventListener;
    const prevDocAdd = globalThis.document.addEventListener;
    const prevDocRemove = globalThis.document.removeEventListener;
    globalThis.window.__registerPage = () => {};
    // 195b-T5：_hsInit 開頭會 _hsBindRecheck()；既有 O-a／O-b 不關心事件，掛空殼即可
    globalThis.window.addEventListener = () => {};
    globalThis.window.removeEventListener = () => {};
    globalThis.document.addEventListener = () => {};
    globalThis.document.removeEventListener = () => {};
    try {
        await drive(c, snaps);
    } finally {
        gate.flush();   // FE-GUARD-39：一律放行，不讓掛住的 promise 卡死 node --test
        fx.restore();
        globalThis.window.__registerPage = prevReg;
        globalThis.window.addEventListener = prevWinAdd;
        globalThis.window.removeEventListener = prevWinRemove;
        globalThis.document.addEventListener = prevDocAdd;
        globalThis.document.removeEventListener = prevDocRemove;
    }
}

test('O-a：開關開、source-status 3 秒內回 → 第一次交給牆的清單已不含離線卡', async () => {
    const gate = makeGate();
    await runInit({
        gate,
        onVideosServed: () => setTimeout(gate.flush, 10),   // 狀態比影片慢一點才到，但遠小於 3 秒
        drive: async (c, snaps) => {
            await c.init();
            assert.deepEqual(snaps[0], ['BBB-002', 'CCC-003', 'EEE-005']);
            assert.equal(c.hiddenCount, 3);
        },
    });
});

test('O-b：source-status 逾 3 秒才回 → 先畫全庫、晚到後仍被套用；3 秒內回則首屏就乾淨（對照）', async () => {
    mock.timers.enable({ apis: ['setTimeout'] });
    try {
        // 逾時：假 fetch 忽略 signal，回應要等 flush()
        const late = makeGate();
        await runInit({
            gate: late,
            drive: async (c, snaps) => {
                const done = c.init();
                await tickMicro();
                mock.timers.tick(3000);
                await done;
                assert.deepEqual(snaps[0], numbers(fixture()), '逾時降級：首屏先畫全庫');
                late.flush();
                await tickMicro();
                assert.deepEqual(numbers(_videos), ['BBB-002', 'CCC-003', 'EEE-005'], '晚到的狀態仍要套用');
                assert.equal(c.hiddenCount, 3);
                assert.deepEqual(snaps[snaps.length - 1], ['BBB-002', 'CCC-003', 'EEE-005']);
            },
        });
        // 未逾時對照：同一串回應，在 3 秒內放行
        const early = makeGate();
        await runInit({
            gate: early,
            drive: async (c, snaps) => {
                const done = c.init();
                await tickMicro();
                early.flush();
                await done;
                assert.deepEqual(snaps[0], ['BBB-002', 'CCC-003', 'EEE-005'], '3 秒內回：首屏就不含離線卡');
            },
        });
    } finally {
        mock.timers.reset();
    }
});

test('F1：init 窗口內 status 才回報燈箱所在的片離線 → init 完成後燈箱已關', async () => {
    const gate = makeGate();
    await runInit({
        gate,
        onVideosServed: () => setTimeout(gate.flush, 10),
        setup: (c) => { c.lightboxOpen = true; c.lightboxIndex = 0; c.currentLightboxVideo = mk('AAA-001', 0); },
        drive: async (c) => {
            await c.init();
            assert.equal(c.lightboxOpen, false, '窗口內略過的收斂要在 init 最終 apply 後補做');
            assert.deepEqual(numbers(_videos), ['BBB-002', 'CCC-003', 'EEE-005']);
        },
    });
});

// ── 7. 切換時 PUT 失敗 ────────────────────────────────────────────────

test('hsSetHide：PUT 失敗（reject／success:false）→ 畫面還原且只跳一次 toast', async () => {
    for (const failure of ['reject', 'success-false']) {
        resetModule(fixture());
        const c = makeComponent();
        c._hsSources = SOURCES; c._hsOfflineKeys = ['D:\\電影'];
        c._recomputeVisible();
        const wall = paths(_videos);
        const gate = makeGate();
        const fx = stubFetch(async () => {
            await gate.promise;
            if (failure === 'reject') throw new Error('network down');
            return jsonResp({ success: false, error: '操作失敗' });
        });
        try {
            const pending = c.hsSetHide(true);
            assert.equal(c.hideUnreachable, true, failure + '：樂觀更新先藏起來');
            assert.deepEqual(numbers(_videos), ['BBB-002', 'CCC-003', 'EEE-005']);
            gate.flush();
            await pending;
        } finally { gate.flush(); fx.restore(); }
        assert.equal(c.hideUnreachable, false, failure);
        assert.deepEqual(paths(_videos), wall, failure + '：內容與順序還原');
        assert.equal(c.hiddenCount, 0);
        assert.deepEqual(c.toasts, [{ msg: 'showcase.status.source_hide_save_failed', kind: 'error' }], failure);
    }
});

// ── 8. 195b-T5：切回視窗重驗（B／C／D）────────────────────────────────

/** 假事件樞紐：把 handler 存進 Map，fire 同步呼叫。 */
function makeEventHub() {
    const byTarget = new Map();
    const keyOf = (target) => target;
    return {
        add(target, type, fn) {
            let byType = byTarget.get(keyOf(target));
            if (!byType) { byType = new Map(); byTarget.set(keyOf(target), byType); }
            let set = byType.get(type);
            if (!set) { set = new Set(); byType.set(type, set); }
            set.add(fn);
        },
        remove(target, type, fn) {
            const byType = byTarget.get(keyOf(target));
            if (!byType) return;
            const set = byType.get(type);
            if (set) set.delete(fn);
        },
        fire(target, type, ev = {}) {
            const byType = byTarget.get(keyOf(target));
            if (!byType) return;
            const set = byType.get(type);
            if (!set) return;
            for (const fn of [...set]) fn(ev);
        },
        install() {
            const doc = globalThis.document;
            const win = globalThis.window;
            const prev = {
                docAdd: doc.addEventListener,
                docRemove: doc.removeEventListener,
                winAdd: win.addEventListener,
                winRemove: win.removeEventListener,
                hiddenDesc: Object.getOwnPropertyDescriptor(doc, 'hidden'),
            };
            const hub = this;
            doc.addEventListener = (type, fn) => hub.add(doc, type, fn);
            doc.removeEventListener = (type, fn) => hub.remove(doc, type, fn);
            win.addEventListener = (type, fn) => hub.add(win, type, fn);
            win.removeEventListener = (type, fn) => hub.remove(win, type, fn);
            return () => {
                doc.addEventListener = prev.docAdd;
                doc.removeEventListener = prev.docRemove;
                win.addEventListener = prev.winAdd;
                win.removeEventListener = prev.winRemove;
                if (prev.hiddenDesc) Object.defineProperty(doc, 'hidden', prev.hiddenDesc);
                else delete doc.hidden;
            };
        },
    };
}

function setDocumentHidden(value) {
    Object.defineProperty(globalThis.document, 'hidden', {
        configurable: true,
        enumerable: true,
        get() { return value; },
    });
}

function isStatusUrl(url) {
    return String(url).startsWith('/api/showcase/source-status');
}

// [lint-guard: node-justified] 求值型時序：同輪去重／在飛不重送／hidden 不送；lint 無事件求值能力
test('切回視窗：同輪兩個事件只送一次、在飛不重送、頁面隱藏不送', async () => {
    resetModule(fixture());
    const c = makeComponent();
    c._hsSources = SOURCES;
    const hub = makeEventHub();
    const uninstall = hub.install();
    setDocumentHidden(false);
    const gates = [];
    const fx = stubFetch(async (url) => {
        if (!isStatusUrl(url)) return jsonResp({});
        const g = makeGate();
        gates.push(g);
        await g.promise;
        return jsonResp(OFFLINE_D);
    });
    try {
        c._hsBindRecheck();

        // 同輪 visibilitychange + focus → 恰 1 次（斷言在 await 之前）
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(fx.calls.filter((x) => isStatusUrl(x.url)).length, 1, '同輪兩事件只送一次');

        // 在飛不重送
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(fx.calls.filter((x) => isStatusUrl(x.url)).length, 1, '在飛再觸發仍一次');

        // 放行後可再送（不是永久鎖死）
        gates.forEach((g) => g.flush());
        await tickMicro();
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(fx.calls.filter((x) => isStatusUrl(x.url)).length, 2, '回來後再觸發可再送');
        gates.forEach((g) => g.flush());
        await tickMicro();

        // document.hidden === true → 兩事件皆 0 次新增
        const before = fx.calls.filter((x) => isStatusUrl(x.url)).length;
        setDocumentHidden(true);
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(
            fx.calls.filter((x) => isStatusUrl(x.url)).length,
            before,
            'hidden 時兩事件皆不送',
        );
    } finally {
        gates.forEach((g) => g.flush());
        await tickMicro();
        fx.restore();
        uninstall();
    }
});

// [lint-guard: node-justified] 求值型：切回後套用結果＋晚到仍套用；假 fetch 忽略 signal（FE-GUARD-40）
test('切回視窗：伺服器回全部接上 → 提示清空、被藏的片回到牆上（晚到回應仍被套用）', async () => {
    async function runOnce({ delayRecheck }) {
        resetModule(fixture());
        const c = makeComponent();
        c._hsSources = SOURCES;
        c.hideUnreachable = true;
        const hub = makeEventHub();
        const uninstall = hub.install();
        setDocumentHidden(false);
        const urls = [];
        let recheckGate = null;
        const fx = stubFetch(async (url) => {
            const u = String(url);
            if (!isStatusUrl(u)) return putOk();
            urls.push(u);
            if (u.includes('recheck=1')) {
                if (delayRecheck) {
                    recheckGate = makeGate();
                    await recheckGate.promise;
                }
                return jsonResp([]);
            }
            return jsonResp(OFFLINE_D);
        });
        try {
            // 第一次離線經真的 _hsFetchStatus 套用（不手塞 _hsOfflineKeys）
            await c._hsFetchStatus();
            assert.ok(!urls[0].includes('recheck=1'), '第一次 URL 不含 recheck=1');
            assert.deepEqual(c.unreachableSources, OFFLINE_D);
            assert.equal(c.hiddenCount, 3);
            assert.deepEqual(numbers(_videos), ['BBB-002', 'CCC-003', 'EEE-005']);

            c._hsBindRecheck();
            hub.fire(globalThis.document, 'visibilitychange');
            hub.fire(globalThis.window, 'focus');
            assert.equal(urls.length, 2, '切回送出第二次');
            assert.ok(urls[1].includes('recheck=1'), '切回那次 URL 含 recheck=1');

            if (delayRecheck) {
                // 在飛期間再 dispatch → calls 不增加
                hub.fire(globalThis.document, 'visibilitychange');
                hub.fire(globalThis.window, 'focus');
                assert.equal(urls.length, 2, '晚到在飛期間不重送');
                recheckGate.flush();
            }
            await tickMicro();

            assert.deepEqual(c.unreachableSources, []);
            assert.equal(c.hiddenCount, 0);
            assert.deepEqual(numbers(_videos), numbers(fixture()), '被藏的片回到牆上且順序＝全庫');
            assert.deepEqual(
                footerNotice(c.unreachableSources, c.hideUnreachable, c.hiddenCount, (k) => k),
                { offline: null, permission: null },
            );
        } finally {
            if (recheckGate) recheckGate.flush();
            await tickMicro();
            fx.restore();
            uninstall();
        }
    }

    await runOnce({ delayRecheck: true });    // 晚到仍被套用
    await runOnce({ delayRecheck: false });   // 立即回對照（證明測試不空轉）
});

// [lint-guard: node-justified] 求值型：cleanup 拆 listener＋pageshow(persisted) 重綁；必須走真 init／cleanup
test('cleanup 後切回視窗不再送請求；bfcache 還原後重新生效', async () => {
    resetModule([]);
    const hub = makeEventHub();
    const uninstall = hub.install();
    setDocumentHidden(false);
    let cleanup = null;
    const prevReg = globalThis.window.__registerPage;
    globalThis.window.__registerPage = (h) => { cleanup = h.cleanup; };

    const c = makeComponent({
        mode: 'list',
        _resetPicker() {},
        restoreState() { this.hideUnreachable = true; },
        applyFilterAndSort() { _setFilteredVideos(_videos); this.filteredCount = _filteredVideos.length; },
        updatePagination() {}, $watch() {}, loadActresses() {}, _reconcileHeroCard() {},
        init: base.stateBase.call({ $persist: (o) => ({ as: () => o }) }).init,
    });

    const statusGates = [];
    const fx = stubFetch(async (url) => {
        if (url === '/api/showcase/videos') {
            return jsonResp({ success: true, videos: fixture(), sources: SOURCES });
        }
        if (isStatusUrl(url)) {
            const g = makeGate();
            statusGates.push(g);
            await g.promise;
            return jsonResp(OFFLINE_D);
        }
        if (url === '/api/cover-badges/manifest') return jsonResp([]);
        if (url === '/api/actress-aliases' || url === '/api/tag-aliases') return jsonResp({ groups: [] });
        if (url === '/api/similar/warmup') return jsonResp({ boosted_numbers: [] });
        return jsonResp({});
    });

    try {
        const done = c.init();
        await tickMicro();
        // 放行 init 的 source-status，讓 init 走完
        statusGates.forEach((g) => g.flush());
        await done;
        await tickMicro();

        const countStatus = () => fx.calls.filter((x) => isStatusUrl(x.url)).length;
        const afterInit = countStatus();
        assert.ok(afterInit >= 1, 'init 至少打過一次 source-status');
        assert.ok(typeof cleanup === 'function', '真的 init 必須經 __registerPage 註冊 cleanup');

        // 對照：cleanup 前事件會送
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(countStatus(), afterInit + 1, 'cleanup 前切回會送');
        statusGates.forEach((g) => g.flush());
        await tickMicro();

        // 走真的 cleanup（含 state-base 最前的 _hsUnbindRecheck）
        cleanup();
        const afterCleanup = countStatus();
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(countStatus(), afterCleanup, 'cleanup 後兩事件零次');

        hub.fire(globalThis.window, 'pageshow', { persisted: false });
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(countStatus(), afterCleanup, 'pageshow{persisted:false} 仍零次');

        hub.fire(globalThis.window, 'pageshow', { persisted: true });
        hub.fire(globalThis.document, 'visibilitychange');
        hub.fire(globalThis.window, 'focus');
        assert.equal(countStatus(), afterCleanup + 1, 'pageshow{persisted:true} 後事件恢復送出');
        statusGates.forEach((g) => g.flush());
        await tickMicro();
    } finally {
        statusGates.forEach((g) => g.flush());
        await tickMicro();
        fx.restore();
        globalThis.window.__registerPage = prevReg;
        uninstall();
    }
});
