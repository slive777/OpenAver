// TASK-183-T2：空白結果卡的編輯要存得住（§3.5 原 bug：填完演員按 ✓，換片回來全沒了）。
// 呼叫真的 current()，不 override——蓋掉就測不到 `|| file.blankCard`。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateResultCard } = await import('../state/result-card.js');
const { adoptIntoBlankFile } = await import('../blank-card-rules.js');

function makeFakeThis(file) {
    return {
        listMode: 'file',
        fileList: [file],
        currentFileIndex: 0,
        currentIndex: 0,
        searchResults: [],
    };
}

test('blank-card T2: current() returns stable file.blankCard when no candidates, candidate when present', () => {
    const { current } = searchStateResultCard();

    // (a) 無候選：連兩次拿到同一個 file.blankCard，改欄位後下次讀得到
    const blank = { _blank: true, number: 'JURA-1113', actors: [] };
    const a = makeFakeThis({ searchResults: [], blankCard: blank });
    const first = current.call(a);
    assert.strictEqual(first, blank);
    assert.strictEqual(current.call(a), first);
    first.actors = ['A', 'B'];
    assert.deepEqual(current.call(a).actors, ['A', 'B']);

    // (b) 有候選：回候選，殘留的 blankCard 不會被讀到
    const R = { number: 'JURA-1113', title: 't' };
    const b = makeFakeThis({ searchResults: [R], blankCard: { _blank: true } });
    assert.strictEqual(current.call(b), R);
});

// TASK-183-T3a：進階搜尋的結果只掛到開窗那個檔；A 不在或已有正式結果就整個丟棄。
// target.fileIndex 是誘餌（產品碼不讀），讓「改用 index 認檔」的突變真的改變行為。
function mkFile(path, number, extra = {}) {
    return {
        path, number, searched: true, searchResults: [], hasMoreResults: true,
        selectedCandidateIndex: 2, blankCard: { _blank: true, title: '使用者填的' }, ...extra,
    };
}
const tgt = (file, fileIndex) => ({ blank: true, filePath: file.path, fileIndex });

test('blank-card T3a: adoptIntoBlankFile writes only the file at target.filePath, or discards', () => {
    const variant = { number: 'JURA-111', title: 'v' };

    // (a) 目前檔是 B，結果回 A：只寫 A（有番號不覆寫），X、B 逐欄不變
    {
        const X = mkFile('/x.mp4', 'XXX-1');
        const A = mkFile('/a.mp4', 'JURA-1113');
        const B = mkFile('/b.mp4', 'BBB-2', { searchResults: [{ number: 'BBB-2' }] });
        const snap = structuredClone([X, B]);
        assert.equal(adoptIntoBlankFile([X, A, B], tgt(A, 1), variant), true);
        assert.equal(A.searchResults.length, 1);
        assert.strictEqual(A.searchResults[0], variant);
        assert.equal(A.searched, true);
        assert.equal(A.selectedCandidateIndex, 0);
        assert.equal(A.hasMoreResults, false);
        assert.equal(A.blankCard, null);
        assert.equal(A.number, 'JURA-1113');
        assert.deepEqual([X, B], snap);
    }

    // (b) A 已不在清單：回 false，其餘不動
    {
        const X = mkFile('/x.mp4', 'XXX-1');
        const A = mkFile('/a.mp4', 'JURA-1113');
        const B = mkFile('/b.mp4', 'BBB-2');
        const snap = structuredClone([X, B]);
        assert.equal(adoptIntoBlankFile([X, B], tgt(A, 1), variant), false);
        assert.deepEqual([X, B], snap);
    }

    // (c) 開窗時 A 在 index 1，之後 X 被移除：仍寫 A，不寫位移後落在原 index 的 B
    {
        const A = mkFile('/a.mp4', 'JURA-1113');
        const B = mkFile('/b.mp4', 'BBB-2');
        const snap = structuredClone(B);
        assert.equal(adoptIntoBlankFile([A, B], tgt(A, 1), variant), true);
        assert.equal(A.searchResults.length, 1);
        assert.deepEqual(B, snap);
    }

    // (d) A 已有正式結果（重試先查到）：回 false，不覆蓋、blankCard 不清
    {
        const R = { number: 'JURA-1113', title: 'r' };
        const card = { _blank: true, title: '使用者填的' };
        const A = mkFile('/a.mp4', 'JURA-1113', { searchResults: [R], blankCard: card });
        assert.equal(adoptIntoBlankFile([A], tgt(A, 0), variant), false);
        assert.strictEqual(A.searchResults[0], R);
        assert.equal(A.searchResults.length, 1);
        assert.strictEqual(A.blankCard, card);
    }

    // (e) 無番號檔：採用後補號，且真的 current() 讀得到結果（切走再切回來不變回空白卡）
    {
        const A = mkFile('/a.mp4', '');
        assert.equal(adoptIntoBlankFile([A], tgt(A, 0), variant), true);
        assert.equal(A.number, variant.number);
        assert.strictEqual(searchStateResultCard().current.call(makeFakeThis(A)), variant);
    }
});

// TASK-183-T4：可整理判定。整理會搬檔，所以「不該整理的絕不送出」是核心。
// 新函式用動態 import 取，避免它還不存在時整個檔案載入失敗。
globalThis.document = globalThis.document || {
    getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
};
const { searchStateBatch } = await import('../state/batch.js');
const rules = await import('../blank-card-rules.js');

const card = (extra = {}) => ({
    _blank: true, _source: 'auto', number: '', title: '', translated_title: '', date: '',
    maker: '', actors: [], tags: [], cover: '', source: '', ...extra,
});
const bf = (path, number, blankCard, extra = {}) => ({
    path, filename: path.slice(1), number, searched: true, scraped: false, searchResults: [],
    selectedCandidateIndex: 0, chineseTitle: '', blankCard, user_tags: [], ...extra,
});

function makeBatchState(fileList, { onScrape, translate, enabled = false } = {}) {
    const calls = { scraped: [], toasts: [], metas: [], translated: 0 };
    window.SearchFile = {
        scrapeFile: async (file, metadata) => {
            calls.scraped.push(file.path); calls.metas.push(metadata);
            await onScrape?.(file, metadata);
            return { success: true };
        },
    };
    const state = {
        ...searchStateBatch(), fileList, listMode: 'file', currentFileIndex: 0, currentIndex: 0,
        searchResults: [], isScrapeAllProcessing: false,
        scrapeProgress: { total: 0, processed: 0, isProcessing: false },
        appConfig: { translate: { enabled } },
        showToast(msg) { calls.toasts.push(msg); },
        $nextTick(fn) { fn(); }, scrapePercent() { return 0; }, _resetCoverState() {},
        hasJapanese: () => true,
        async translateWithOllama() { calls.translated++; return { success: true, result: 'AI譯文' }; },
    };
    return { state, calls };
}

test('blank-card T4: only ready files reach scrapeFile; none and needs_number never do', async () => {
    const { organizeState } = rules;
    const R = { number: 'JURA-1', title: 'r' };
    // 真值表
    assert.equal(organizeState(bf('/a', 'A-1', card({ number: 'A-1', title: 'T' }))), 'ready');
    assert.equal(organizeState(bf('/a', '', card({ number: 'A-1', title: 'T' }))), 'ready');
    assert.equal(organizeState(bf('/a', 'A-1', null, { searchResults: [R] })), 'ready');
    assert.equal(organizeState(bf('/a', 'A-1', card({ number: '', title: 'T' }))), 'needs_number');
    assert.equal(organizeState(bf('/a', 'A-1', card({ number: '  ', title: 'T' }))), 'needs_number');
    assert.equal(organizeState(bf('/a', 'A-1', card({ number: 'A-1', title: '' }))), 'none');
    assert.equal(organizeState(bf('/a', 'A-1', card({ number: 'A-1', title: '   ' }))), 'none');
    assert.equal(organizeState(bf('/a', 'A-1', card({ number: 'A-1', actors: ['x'], date: '2024-01-01', tags: ['t'] }))), 'none');
    assert.equal(organizeState(bf('/a', 'A-1', null)), 'none');
    assert.equal(organizeState({ number: 'A-1' }), 'none');

    // 批次：ready（空白卡）＋T3a 採用後的 ready 才送；none／needs_number 不送；needs_number 只一則 toast
    {
        const files = [
            bf('/none.mp4', 'JURA-9', card({ number: 'JURA-9' }), { user_tags: ['只填標籤'] }),
            bf('/need1.mp4', '', card({ title: '標題一' })),
            bf('/ready.mp4', 'JURA-1113', card({ number: 'JURA-1113', title: '手動標題' })),
            bf('/need2.mp4', '', card({ title: '標題二' })),
            bf('/adopted.mp4', 'JURA-111', null, { searchResults: [R] }),
        ];
        const { state, calls } = makeBatchState(files);
        await state.scrapeAll();
        assert.deepEqual(calls.scraped, ['/ready.mp4', '/adopted.mp4']);
        assert.equal(calls.toasts.filter(m => m === 'search.toast.number_required').length, 1);
        assert.equal(files[0].scraped, false);
        assert.equal(files[1].scraped, false);
        assert.equal(calls.metas[1].manual_entry, undefined);
    }
    // 批次進行中：第一片的 scrapeFile 掛起時，使用者把第二張 ready 空白卡的標題清空 → 第二片不送出
    {
        const A = bf('/a.mp4', 'JURA-1', card({ number: 'JURA-1', title: 'A' }));
        const B = bf('/b.mp4', 'JURA-2', card({ number: 'JURA-2', title: 'B' }));
        let release;
        const gate = new Promise(r => { release = r; });
        const { state, calls } = makeBatchState([A, B], { onScrape: (f) => (f === A ? gate : undefined) });
        const run = state.scrapeAll();
        try {
            await Promise.resolve();
            B.blankCard.title = '';
        } finally {
            release();
        }
        await run;
        assert.deepEqual(calls.scraped, ['/a.mp4']);
        assert.equal(B.scraped, false);
        assert.deepEqual(calls.toasts, ['search.toast.scrape_complete']);
    }
    // 整批只有 none → 沿用 no_scrapable_files；整批只有 needs_number → 只跳 number_required
    {
        const { state, calls } = makeBatchState([bf('/none.mp4', 'J-1', card({ number: 'J-1' }))]);
        await state.scrapeAll();
        assert.deepEqual(calls.scraped, []);
        assert.deepEqual(calls.toasts, ['search.toast.no_scrapable_files']);
    }
    {
        const { state, calls } = makeBatchState([bf('/need.mp4', '', card({ title: 'T' }))]);
        await state.scrapeAll();
        assert.deepEqual(calls.scraped, []);
        assert.deepEqual(calls.toasts, ['search.toast.number_required']);
    }
    // 單片
    {
        const files = [bf('/none.mp4', 'J-1', card({ number: 'J-1' })), bf('/need.mp4', '', card({ title: 'T' }))];
        const { state, calls } = makeBatchState(files);
        await state.scrapeSingle(0);
        await state.scrapeSingle(1);
        assert.deepEqual(calls.scraped, []);
        assert.deepEqual(calls.toasts, ['search.toast.no_search_results', 'search.toast.number_required']);
        assert.equal(files[1].isScraping, undefined);
    }
});

test("blank-card T4: batch sends a ready blank card's own number/title/user_tags with manual_entry and no internal keys", async () => {
    const f = bf('/ready.mp4', '', card({
        number: 'JURA-1113', title: '手動標題', translated_title: '手填中文', actors: ['某演員'],
        _titleEdited: true, _chineseTitleEdited: true, _coverUploadToken: 'tok',
    }), { user_tags: ['我的標籤'] });
    const { state, calls } = makeBatchState([f]);
    await state.scrapeAll();
    assert.equal(calls.metas.length, 1);
    const m = calls.metas[0];
    assert.equal(m.number, 'JURA-1113');
    assert.equal(m.title, '手動標題');
    assert.equal(m.translated_title, '手填中文');
    assert.deepEqual(m.actors, ['某演員']);
    assert.deepEqual(m.user_tags, ['我的標籤']);
    assert.equal(m.manual_entry, true);
    for (const k of ['_blank', '_source', '_titleEdited', '_chineseTitleEdited', '_coverUploadToken']) {
        assert.equal(k in m, false, k);
    }
    assert.equal(Object.values(m).includes(undefined), false);
    assert.equal(f.scraped, true);
});

test('blank-card T4: hand-filled translated_title skips auto translate; empty one still translates', async () => {
    const run = async (translated_title) => {
        const f = bf('/r.mp4', 'JURA-1113', card({ number: 'JURA-1113', title: 'テストタイトル', translated_title }));
        const { state, calls } = makeBatchState([f], { enabled: true });
        await state.scrapeSingle(0);
        return { sent: calls.metas[0].translated_title, translated: calls.translated };
    };
    assert.deepEqual(await run('手填中文'), { sent: '手填中文', translated: 0 });
    assert.deepEqual(await run(''), { sent: 'AI譯文', translated: 1 });
});

// TASK-183-T5b：上傳封面只掛到按下當下那個檔；token 只隨「採用的空白卡」送出。
// 假 fetch 是自家端點（/api/scrape-cover/upload、/api/scrape-single）的協定 mock，可掛起、finally flush。
const { searchStateBlankCard } = await import('../state/blank-card.js');

function deferredFetch() {
    const pending = [];
    const calls = [];
    return {
        calls,
        fetch: (url, opts) => { calls.push({ url, opts }); return new Promise(r => pending.push(r)); },
        settleNext(resp) { pending.shift()(resp); },
        flush() { while (pending.length) pending.shift()({ ok: false, status: 500, json: async () => ({}) }); },
    };
}
const okUpload = { ok: true, status: 200, json: async () => ({ token: 'tok-A', url: '/api/scrape-cover/tok-A' }) };
const evFor = () => ({ target: { files: [new Blob(['x'], { type: 'image/jpeg' })], value: 'C:\\fake.jpg' } });
const uploadState = (fileList) => ({
    ...searchStateBlankCard(), fileList, currentFileIndex: 0, _uploadingCover: false,
    showToast() {}, saveState() {}, _resetCoverState() {},
});

test('blank-card T5b: upload lands on the file it started from; token rides only with the blank card it came from', async () => {
    const prevFetch = globalThis.fetch;
    const prevSF = window.SearchFile;
    await import('../file.js');
    const realScrapeFile = window.SearchFile.scrapeFile;
    window.SearchFile = prevSF;
    const df = deferredFetch();
    globalThis.fetch = df.fetch;
    try {
        // (a) U1：A 上傳中切到 B → 只有 A 拿到 token 與預覽圖
        {
            const A = bf('/a.mp4', 'A-1', card());
            const B = bf('/b.mp4', 'B-2', card());
            const state = uploadState([A, B]);
            const p = state.uploadBlankCover(evFor());
            state.currentFileIndex = 1;
            df.settleNext(okUpload);
            await p;
            assert.equal(A.blankCard._coverUploadToken, 'tok-A');
            assert.equal(A.blankCard.cover, '/api/scrape-cover/tok-A');
            assert.ok(!B.blankCard._coverUploadToken);
            assert.equal(B.blankCard.cover, '');
        }
        // (b) U2：上傳中整份 fileList 換成同 path 的新物件 → 新物件沒有 token，舊物件有（請求真的落地）
        {
            const oldA = bf('/a.mp4', 'A-1', card());
            const newA = bf('/a.mp4', 'A-1', card());
            const state = uploadState([oldA]);
            const p = state.uploadBlankCover(evFor());
            state.fileList = [newA];
            df.settleNext(okUpload);
            await p;
            assert.equal(oldA.blankCard._coverUploadToken, 'tok-A');
            assert.ok(!newA.blankCard._coverUploadToken);
        }
        // (c) U3：scrapeFile 只在 manual_entry===true 時帶殘留 token（正向格＋兩個負向格）
        {
            const bodyOf = async (file, metadata) => {
                const n = df.calls.length;
                const p = realScrapeFile(file, metadata);
                df.settleNext({ ok: true, json: async () => ({ success: true }) });
                await p;
                return JSON.parse(df.calls[n].opts.body);
            };
            const withTok = bf('/a.mp4', 'A-1', card({ _coverUploadToken: 'tok-X' }));
            assert.equal('cover_upload_token' in await bodyOf(withTok, { number: 'A-1' }), false);
            assert.equal((await bodyOf(withTok, { number: 'A-1', manual_entry: true })).cover_upload_token, 'tok-X');
            const noTok = bf('/a.mp4', 'A-1', card());
            assert.equal('cover_upload_token' in await bodyOf(noTok, { number: 'A-1', manual_entry: true }), false);
        }
    } finally {
        df.flush();
        globalThis.fetch = prevFetch;
        window.SearchFile = prevSF;
    }
});
