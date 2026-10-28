// TASK-183-T2：空白結果卡的編輯要存得住（§3.5 原 bug：填完演員按 ✓，換片回來全沒了）。
// 呼叫真的 current()，不 override——蓋掉就測不到 `|| file.blankCard`。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateResultCard } = await import('../state/result-card.js');

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
