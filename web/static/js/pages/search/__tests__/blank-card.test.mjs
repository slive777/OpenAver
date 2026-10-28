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
