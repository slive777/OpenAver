// TASK-106 Option C Part 1: confirmEditTitle/confirmEditChineseTitle/confirmEditActors
// identity guard —— 本次重構的唯一權威保證。
// Codex PR#116 P2: confirmEditDate 補齊同一 pattern（date picker 原本是唯一沒有此守衛的
// 可編輯欄位，@change 在事件當下才 re-resolve current()，若候選在打開日曆到選好日期之間
// 被換掉會寫錯檔）。
//
// 根因（見 task 交付說明）：buffered edits（editingX flag + editedXValue buffer）
// 必須在「displayed candidate 已經換了」時被丟棄，唯一正確訊號是 current() 候選物件的
// 參照本身，不是任何呼叫端「猜」何時該 reset。confirmEditX 開頭一律先比對
// this.current() 是否仍是開編輯當下（startEditX）捕獲的同一個物件參照；不同就不寫、
// 關掉 editingX、直接 return——不管是 navigate/switchToFile/scrapeAll loop/grid/lightbox
// 或任何未來新增的路徑移動的 current()，一律結構性擋下。
//
// 移除 guard（或比錯欄位）→ 本檔案第一組測試（含 confirmEditDate）應轉紅（B 被誤寫）。
//
// Codex PR#115 P2 fix：三個欄位（_editSourceTitle/_editSourceChineseTitle/_editSourceActors）
// 各自獨立，不共用單一 `_editSourceCandidate`——title/chinese/actor 三個 editingX 可同時
// 開啟（各自獨立的 flag，無互斥），若共用一個欄位，後開啟的編輯器會覆蓋先開啟者捕獲的
// 來源，讓先開啟者的 guard 誤判「候選未換」而把 stale 內容寫進後開啟者當下的候選
// （data pollution）。見本檔案「跨欄位污染」測試組——若退回共用單一欄位，該測試轉紅。
//
// result-card.js 用瀏覽器 importmap 別名 `@/shared/...`，plain `node --test`
// 需掛 alias-loader resolve hook 才能 import（同 confirm-edit-actors-fetch-spy.test.mjs）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateResultCard } = await import('../state/result-card.js');

function makeFakeThis(overrides = {}) {
    return {
        ...searchStateResultCard(),
        saveState: () => {},
        ...overrides,
    };
}

// ==================== 核心：candidate 已換 → 不寫、editingX 關閉、不 saveState ====================

test('confirmEditActors: current() 已換到別的候選（B）→ B.actors 不被寫入，editingActors 關閉，不 saveState', () => {
    const A = { number: 'A-001', actors: ['原始女優'] };
    const B = { number: 'B-002', actors: ['B原始女優'] };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        editingActors: true,
        editedActorsValue: '亂寫的女優',
        _editSourceActors: A,   // startEditActors 開編輯時捕獲的是 A
        current: () => B,          // 但呼叫 confirm 時 current() 已經是 B（被別的路徑換走）
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditActors.call(fakeThis);

    assert.deepEqual(B.actors, ['B原始女優'], 'B.actors 不應被 stale 編輯寫入');
    assert.equal(fakeThis.editingActors, false, '即使 guard 擋下寫入，仍應關閉編輯態（UI 不留在編輯模式）');
    assert.equal(saveCalls, 0, 'guard 擋下時不應呼叫 saveState');
});

test('confirmEditDate: current() 已換到別的候選（B）→ B.date/A.date 都不被寫入，不 saveState（Codex PR#116 P2）', () => {
    const A = { number: 'A-001', date: '2020-01-01' };
    const B = { number: 'B-002', date: '2020-02-02' };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        _editSourceDate: A,   // startEditDate 開日曆時捕獲的是 A
        current: () => B,     // 但 @change 觸發 confirmEditDate 時 current() 已經是 B
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditDate.call(fakeThis, '2099-12-31');

    assert.equal(B.date, '2020-02-02', 'B.date 不應被 stale 編輯寫入');
    assert.equal(A.date, '2020-01-01', 'A.date（真正來源）也不應被動到，寫入目標永遠是 current()');
    assert.equal(saveCalls, 0, 'guard 擋下時不應呼叫 saveState');
});

test('confirmEditTitle: current() 已換到別的候選（B）→ B.title 不被寫入，editingTitle 關閉，不 saveState', () => {
    const A = { number: 'A-001', title: 'A 原始標題' };
    const B = { number: 'B-002', title: 'B 原始標題' };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        editingTitle: true,
        editedTitleValue: '亂寫的標題',
        _editSourceTitle: A,
        current: () => B,
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditTitle.call(fakeThis);

    assert.equal(B.title, 'B 原始標題', 'B.title 不應被 stale 編輯寫入');
    assert.equal(B._titleEdited, undefined, 'B 不應被標記 _titleEdited');
    assert.equal(fakeThis.editingTitle, false, '即使 guard 擋下寫入，仍應關閉編輯態');
    assert.equal(saveCalls, 0, 'guard 擋下時不應呼叫 saveState');
});

test('confirmEditChineseTitle: current() 已換到別的候選（B）→ B.translated_title 不被寫入，editingChineseTitle 關閉，不 saveState', () => {
    const A = { number: 'A-001', translated_title: 'A 原始中文標題' };
    const B = { number: 'B-002', translated_title: 'B 原始中文標題' };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        editingChineseTitle: true,
        editedChineseTitleValue: '亂寫的中文標題',
        _editSourceChineseTitle: A,
        current: () => B,
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditChineseTitle.call(fakeThis);

    assert.equal(B.translated_title, 'B 原始中文標題', 'B.translated_title 不應被 stale 編輯寫入');
    assert.equal(B._chineseTitleEdited, undefined, 'B 不應被標記 _chineseTitleEdited');
    assert.equal(fakeThis.editingChineseTitle, false, '即使 guard 擋下寫入，仍應關閉編輯態');
    assert.equal(saveCalls, 0, 'guard 擋下時不應呼叫 saveState');
});

// ==================== 對照組：candidate 未換 → 正常寫入（guard 不誤擋合法確認） ====================

test('confirmEditActors: current() 仍是開編輯當下的同一物件 → 正常寫入 + saveState', () => {
    const A = { number: 'A-001', actors: ['原始女優'] };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        editingActors: true,
        editedActorsValue: '新女優一, 新女優二',
        _editSourceActors: A,
        current: () => A,
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditActors.call(fakeThis);

    assert.deepEqual(A.actors, ['新女優一', '新女優二'], 'candidate 未換時應正常寫入');
    assert.equal(fakeThis.editingActors, false);
    assert.equal(saveCalls, 1, 'candidate 未換時應呼叫一次 saveState');
});

test('confirmEditDate: current() 仍是開日曆當下的同一物件 → 正常寫入 + saveState（Codex PR#116 P2）', () => {
    const A = { number: 'A-001', date: null };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        _editSourceDate: A,
        current: () => A,
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditDate.call(fakeThis, '2024-01-01');

    assert.equal(A.date, '2024-01-01', 'candidate 未換時應正常寫入');
    assert.equal(saveCalls, 1, 'candidate 未換時應呼叫一次 saveState');
});

test('confirmEditTitle: current() 仍是開編輯當下的同一物件 → 正常寫入 + saveState', () => {
    const A = { number: 'A-001', title: '原始標題' };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        editingTitle: true,
        editedTitleValue: '  新標題  ',
        _editSourceTitle: A,
        current: () => A,
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditTitle.call(fakeThis);

    assert.equal(A.title, '新標題', 'candidate 未換時應正常寫入（trim 後）');
    assert.equal(A._titleEdited, true);
    assert.equal(fakeThis.editingTitle, false);
    assert.equal(saveCalls, 1);
});

test('confirmEditChineseTitle: current() 仍是開編輯當下的同一物件 → 正常寫入 + saveState', () => {
    const A = { number: 'A-001', translated_title: '原始中文標題' };
    let saveCalls = 0;

    const fakeThis = makeFakeThis({
        editingChineseTitle: true,
        editedChineseTitleValue: '  新中文標題  ',
        _editSourceChineseTitle: A,
        current: () => A,
        saveState: () => { saveCalls++; },
    });

    searchStateResultCard().confirmEditChineseTitle.call(fakeThis);

    assert.equal(A.translated_title, '新中文標題', 'candidate 未換時應正常寫入（trim 後）');
    assert.equal(A._chineseTitleEdited, true);
    assert.equal(fakeThis.editingChineseTitle, false);
    assert.equal(saveCalls, 1);
});

// ==================== startEditX 捕獲各自的 _editSource* 欄位 ====================

test('startEditActors: 應捕獲 this.current() 到 _editSourceActors（供後續 confirm 比對）', () => {
    const A = { number: 'A-001', actors: ['女優'] };
    const fakeThis = makeFakeThis({
        current: () => A,
        $nextTick: (fn) => {}, // 不執行，僅避免 undefined 呼叫炸掉（無 DOM/$refs 環境）
        $refs: {},
    });

    searchStateResultCard().startEditActors.call(fakeThis);

    assert.equal(fakeThis._editSourceActors, A, 'startEditActors 應把 this.current() 存進 _editSourceActors');
    assert.equal(fakeThis.editingActors, true);
});

test('startEditTitle: 應捕獲 this.current() 到 _editSourceTitle', () => {
    const A = { number: 'A-001', title: '標題' };
    const fakeThis = makeFakeThis({
        current: () => A,
        $nextTick: (fn) => {},
        $refs: {},
    });

    searchStateResultCard().startEditTitle.call(fakeThis);

    assert.equal(fakeThis._editSourceTitle, A);
    assert.equal(fakeThis.editingTitle, true);
});

test('startEditChineseTitle: 應捕獲 this.current() 到 _editSourceChineseTitle', () => {
    const A = { number: 'A-001', translated_title: '中文標題' };
    const fakeThis = makeFakeThis({
        current: () => A,
        chineseTitleText: () => 'x',
        $nextTick: (fn) => {},
        $refs: {},
    });

    searchStateResultCard().startEditChineseTitle.call(fakeThis);

    assert.equal(fakeThis._editSourceChineseTitle, A);
    assert.equal(fakeThis.editingChineseTitle, true);
});

test('startEditDate: 應捕獲 this.current() 到 _editSourceDate（供後續 confirmEditDate 比對，Codex PR#116 P2）', () => {
    const A = { number: 'A-001', date: null };
    const fakeThis = makeFakeThis({
        current: () => A,
    });

    searchStateResultCard().startEditDate.call(fakeThis);

    assert.equal(fakeThis._editSourceDate, A, 'startEditDate 應把 this.current() 存進 _editSourceDate');
});

// ==================== 跨欄位污染（Codex PR#115 P2）：title/actors 同時開啟編輯 ====================

test('跨欄位污染：title 編輯開在 A 未確認，actors 編輯後開在 B（覆蓋 current()）→ 確認 title 不得把 stale 內容寫入 B；只有 actors guard 通過', () => {
    const A = { number: 'A-001', title: 'A 原始標題', actors: ['A原始女優'] };
    const B = { number: 'B-002', title: 'B 原始標題', actors: ['B原始女優'] };

    // Step 1: title 編輯在 A 上開啟（同一張卡片，只是 candidate 之後被替換成 B）。
    const fakeThis = makeFakeThis({
        current: () => A,
        $nextTick: (fn) => {},
        $refs: {},
    });
    searchStateResultCard().startEditTitle.call(fakeThis);
    assert.equal(fakeThis._editSourceTitle, A, 'sanity: title 編輯捕獲 A');
    fakeThis.editedTitleValue = '亂寫的標題（stale）';

    // Step 2: current() 現在指向 B（slot 被替換），且 actors 編輯在 B 上開啟。
    fakeThis.current = () => B;
    searchStateResultCard().startEditActors.call(fakeThis);
    assert.equal(fakeThis._editSourceActors, B, 'sanity: actors 編輯捕獲 B');

    // Step 3: 確認仍開著的 title 編輯（其實已經 stale，來源是 A，但 current() 已是 B）。
    // 若退回共用單一 `_editSourceCandidate`，此欄位在 Step 2 已被 startEditActors 覆蓋成 B，
    // 讓 title 的 guard 誤判「candidate 未換」（current()===B===_editSourceCandidate）而
    // 把 stale 標題寫入 B——這正是本測試要擋下的 data pollution。per-field 修復後
    // `_editSourceTitle` 仍是 A，guard 正確判定 current()(B) !== _editSourceTitle(A)。
    searchStateResultCard().confirmEditTitle.call(fakeThis);

    assert.equal(B.title, 'B 原始標題', 'B.title 不應被 title 編輯器的 stale 內容污染');
    assert.equal(B._titleEdited, undefined, 'B 不應被誤標記 _titleEdited');
    assert.equal(fakeThis.editingTitle, false, 'title 編輯態應關閉（guard 擋下寫入後仍需退出編輯 UI）');
});
