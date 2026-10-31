// TASK-187b-T5a：CD-187b-10 oracle 1–5（Esc 兩段式／過期讀取＋重開重讀／翻譯鎖＋捕獲＋復原＋已是中文）。
// 組合 component 用 mergeState（保留 getter descriptor）。
// _filteredVideos 是 state-base 的 module singleton，每支測試 try/finally 清乾淨（FE-GUARD-13）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;
globalThis.window.__SHOWCASE_TRANSLATE__ = { enabled: true };
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.Alpine = globalThis.Alpine || {
    store: () => ({ toolbarOpen: false, showcaseHasSearch: false }),
};
globalThis.document = globalThis.document || {
    querySelector() { return null; },
    body: { classList: { add() {}, remove() {}, contains() { return false; } } },
};

register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

const { stateLightbox } = await import('../state-lightbox.js');
const { stateLightboxPicker } = await import('../state-lightbox-picker.js');
const { stateLightboxMask } = await import('../state-lightbox-mask.js');
const { stateLightboxPlot } = await import('../state-lightbox-plot.js');
const { mergeState } = await import('@/shared/merge-state.js');
const { _setFilteredVideos } = await import('../state-base.js');

function makeVideos() {
    return [
        { path: 'file:///C:/a.mp4', number: 'AAA-001', title: 'あいう', actresses: 'X, Y', has_plot: true },
        { path: 'file:///C:/b.mp4', number: 'BBB-002', title: 'えおか', actresses: '', has_plot: true },
    ];
}

function makeComponent(toasts) {
    return mergeState(stateLightbox(), stateLightboxPicker(), stateLightboxMask(), stateLightboxPlot(), {
        lightboxOpen: true,
        showFavoriteActresses: false,
        currentLightboxActress: null,
        lightboxIndex: 0,
        actressLightboxIndex: 0,
        similarModeOpen: false,
        similarModeMobileOpen: false,
        removeActressModalOpen: false,
        actressAddPanelOpen: false,
        _pickerOpen: false,
        rescrapeOpen: false,
        deleteVideoModalOpen: false,
        sampleGalleryOpen: false,
        _pillEditor: null,
        _releaseEditor: null,
        _maskVisible: false,
        $nextTick() {},
        $refs: {},
        _fetchLiveAliases() {},
        showToast(...args) { toasts.push(args); },
    });
}

// 依 URL＋method 分流的假 fetch：GET 無 body；每個請求回可手動放行的 Promise
function installFetch() {
    const calls = [];
    const pending = { translate: [], plotGet: [], plotPost: [] };
    const original = globalThis.fetch;
    globalThis.fetch = (url, opts) => {
        const method = (opts?.method || 'GET').toUpperCase();
        let kind;
        let body = null;
        if (url === '/api/translate') {
            kind = 'translate';
            body = JSON.parse(opts.body);
        } else if (typeof url === 'string' && url.startsWith('/api/showcase/video/plot?')) {
            kind = 'plotGet';
        } else if (url === '/api/showcase/video/plot' && method === 'POST') {
            kind = 'plotPost';
            body = JSON.parse(opts.body);
        } else {
            throw new Error(`unexpected fetch ${method} ${url}`);
        }
        calls.push({ url, method, kind, body });
        return new Promise((resolve) => {
            pending[kind].push((payload, ok = true) => resolve({
                ok,
                status: ok ? 200 : 500,
                json: async () => payload,
            }));
        });
    };
    return {
        calls,
        pending,
        flush() {
            for (const k of Object.keys(pending)) {
                for (const r of pending[k]) r({ success: true, skipped: true });
            }
        },
        count: (kind) => calls.filter((c) => c.kind === kind).length,
        restore() { globalThis.fetch = original; },
    };
}

const tick = () => new Promise((r) => setImmediate(r));

function escEvent() {
    return {
        key: 'Escape',
        target: { tagName: 'DIV' },
        ctrlKey: false, altKey: false, shiftKey: false, metaKey: false,
        preventDefault() {}, stopPropagation() {},
    };
}

async function withEnv(fn) {
    const [A, B] = makeVideos();
    _setFilteredVideos([A, B]);
    const toasts = [];
    const c = makeComponent(toasts);
    c._setLightboxIndex(0);
    const f = installFetch();
    try {
        await fn({ A, B, c, f, toasts });
    } finally {
        f.flush();
        f.restore();
        _setFilteredVideos([]);
    }
}

test('test_esc_closes_plot_before_lightbox', async () => {
    await withEnv(async ({ c }) => {
        c.lbPlotOpen = true;
        let closeCount = 0;
        c.closeLightbox = () => { closeCount++; };

        c.handleKeydown(escEvent());
        assert.equal(c.lbPlotOpen, false);
        assert.equal(closeCount, 0, 'Esc 先關簡介，不呼叫 closeLightbox');

        c.handleKeydown(escEvent());
        assert.equal(closeCount, 1, '再按一次 Esc 才關燈箱');
    });
});

test('test_stale_read_and_reopen_reread', async () => {
    await withEnv(async ({ A, c, f }) => {
        // (i) 對 A 開簡介（GET 掛起）→ reset → 放行：現行 _lbPlotView 不被寫入
        const pOpen = c.lbPlotToggle();
        assert.equal(c.lbPlotOpen, true);
        assert.equal(c._lbPlotView.loading, true);
        assert.equal(f.count('plotGet'), 1);

        c._lbPlotReset();
        assert.equal(c.lbPlotOpen, false);
        assert.equal(c._lbPlotView.plot, '');

        f.pending.plotGet[0]({
            success: true,
            plot: 'A舊內容',
            original_plot: '',
            has_original: false,
        });
        await pOpen;
        await tick();
        assert.equal(c._lbPlotView.plot, '', '過期讀取不得寫入現行 view');
        assert.equal(c._lbPlotView.loading, false, '過期讀取不得改寫 loading');

        // (ii) 開→放行 X→關→再開（掛起）→ loading 且不呈現 X → 放行 Y
        const p1 = c.lbPlotToggle();
        f.pending.plotGet[1]({
            success: true,
            plot: '內容X',
            original_plot: '',
            has_original: false,
        });
        await p1;
        assert.equal(c._lbPlotView.plot, '內容X');

        c.lbPlotClose();
        assert.equal(c.lbPlotOpen, false);

        const p2 = c.lbPlotToggle();
        assert.equal(c._lbPlotView.loading, true, '重開瞬間 loading');
        assert.notEqual(c._lbPlotView.plot, '內容X', '重開瞬間不呈現舊內容 X');
        assert.equal(f.count('plotGet'), 3);

        f.pending.plotGet[2]({
            success: true,
            plot: '內容Y',
            original_plot: '',
            has_original: false,
        });
        await p2;
        assert.equal(c._lbPlotView.plot, '內容Y');
        assert.equal(c._lbPlotView.path, A.path);
    });
});

test('test_translate_lock_capture_undo', async () => {
    await withEnv(async ({ A, B, c, f, toasts }) => {
        // 先把 A 的簡介載入好
        const pLoad = c.lbPlotToggle();
        f.pending.plotGet[0]({
            success: true,
            plot: '日本語あらすじ',
            original_plot: '',
            has_original: false,
        });
        await pLoad;
        const viewA = c._lbPlotView;
        assert.equal(viewA.plot, '日本語あらすじ');

        // oracle 3：同一 tick 連按兩次 → translate／writeback 各 1
        const pTr = c.lbPlotTranslate();
        c.lbPlotTranslate(); // 同 tick，不可 await 中間
        assert.equal(f.count('translate'), 1);

        // 翻譯期間切到 B
        c._setLightboxIndex(1);
        assert.equal(c.currentLightboxVideo, B);
        // 模擬 $watch 切片重置（node 繞過 Alpine）
        c._lbPlotReset();
        const viewB = c._lbPlotView;

        f.pending.translate[0]({ success: true, result: '中文簡介A' });
        await tick();
        assert.equal(f.count('plotPost'), 1);
        f.pending.plotPost[0]({
            success: true,
            plot: '中文簡介A',
            original_plot: '日本語あらすじ',
            has_original: true,
        });
        await pTr;

        assert.equal(viewA.plot, '中文簡介A', '結果落在按下當下捕獲的 A view');
        assert.equal(viewA.original, '日本語あらすじ');
        assert.equal(viewB.plot, '', 'B 的 view 不變');
        assert.equal(f.count('translate'), 1);
        assert.equal(f.count('plotPost'), 1);

        // oracle 5：切到 B 並開 B 的簡介 → 按 A 的復原 → POST 仍是 A；B 的面不被覆蓋
        const pLoadB = c.lbPlotToggle();
        f.pending.plotGet[1]({
            success: true,
            plot: 'B片簡介',
            original_plot: '',
            has_original: false,
        });
        await pLoadB;
        assert.equal(c._lbPlotView.path, B.path);
        assert.equal(c._lbPlotView.plot, 'B片簡介');

        const undoToast = toasts.find((t) => t[0] === 'showcase.lightbox.plot_translate_done');
        assert.ok(undoToast, '翻譯成功 toast');
        assert.equal(undoToast[3].label, 'showcase.lightbox.plot_translate_undo');
        const undoP = undoToast[3].onClick();
        assert.deepEqual(f.calls.filter((x) => x.kind === 'plotPost').at(-1).body, {
            file_path: A.path,
            plot: '日本語あらすじ',
            original_plot: '',
        });
        f.pending.plotPost[1]({
            success: true,
            plot: '日本語あらすじ',
            original_plot: '',
            has_original: false,
        });
        await undoP;
        assert.equal(c._lbPlotView.path, B.path, '復原不得改寫現行 path');
        assert.equal(c._lbPlotView.plot, 'B片簡介', '復原不得把 A 的 snapshot 蓋到 B 的面');
        assert.notEqual(c._lbPlotView.plot, '日本語あらすじ');

        // oracle 4：譯文空白正規化後＝來源 → 寫回零呼叫、toast already_zh
        // 重新開 A、載入後翻譯回相同文字（僅頭尾／中間空白差異）
        c.lbPlotClose();
        c._setLightboxIndex(0);
        const pReload = c.lbPlotToggle();
        f.pending.plotGet[2]({
            success: true,
            plot: '同じ  内容',
            original_plot: '',
            has_original: false,
        });
        await pReload;
        const postBefore = f.count('plotPost');
        const pSame = c.lbPlotTranslate();
        f.pending.translate[1]({ success: true, result: ' 同じ 内容 ' });
        await pSame;
        assert.equal(f.count('plotPost'), postBefore, '正規化相等不寫回');
        const lastToast = toasts[toasts.length - 1];
        assert.equal(lastToast[0], 'showcase.lightbox.plot_already_zh');
        assert.equal(lastToast[1], 'info');
    });
});
