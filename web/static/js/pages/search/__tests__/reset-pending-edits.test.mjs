// TASK-106 Option C: _resetPendingEdits() 存在但呼叫端已改為單一入口
//
// 舊版（T5 CD-106-6）：navigate()/switchToFile() 各自在「確定要換候選/檔」的分支主動呼叫
// _resetPendingEdits()，靠呼叫端手動判斷「什麼時候該呼叫」——結果 both over-applied（no-op
// 重選也誤清）與 under-applied（scrapeAll loop / grid / lightbox 繞過、3 處 search 完成的
// reset 漏了 editingActors）。
//
// Option C 改為身份制：
// - 唯一權威保證：result-card.js confirmEditTitle/confirmEditChineseTitle/confirmEditActors
//   開頭的 identity guard（current() !== 開編輯當下捕獲的各自欄位
//   _editSourceTitle/_editSourceChineseTitle/_editSourceActors 就不寫）。
//   見 confirm-edit-identity-guard.test.mjs。
// - UX 便利層：persistence.js setupAutoSave 內單一 `$watch`，偵測到候選位置改變
//   （currentFileIndex/currentIndex/listMode/清單長度）就呼叫 _resetPendingEdits() 清 UI flag。
//
// 本檔測試：
// 1. _resetPendingEdits() 本身：零 DOM，直接 .call(fakeThis)，仍是三個 flag 一起清空、
//    editedXValue buffer 不受影響（純函式行為不變，只是呼叫端變了）。
// 2. 迴歸守衛：navigate()（不論真的換候選或 no-op 邊界分支）與 switchToFile() 都不再
//    「自己」動 editingX——這是這次重構移除散落呼叫的直接後果。若未來有人把
//    `this._resetPendingEdits()` 加回 navigate()/switchToFile() 內部（重蹈覆轍），
//    這裡的斷言會轉紅（因為呼叫後 editingActors 會被清成 false，而非維持測試設的 true）。
//
// navigation.js 匯入瀏覽器 importmap 別名 `@/shared/...`，需掛 alias-loader.mjs
// resolve hook 才能動態 import（同 build-organize-metadata.test.mjs 慣例）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { searchStateFileList } from '../state/file-list.js';

globalThis.window = globalThis;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateNavigation } = await import('../state/navigation.js');

// ==================== Tier 1: _resetPendingEdits() 零 DOM 直測 ====================

test('_resetPendingEdits: 三個 editingX 皆 true → call 後皆 false；editedXValue buffer 不受影響', () => {
    const fakeThis = {
        editingTitle: true,
        editedTitleValue: 'pending title',
        editingChineseTitle: true,
        editedChineseTitleValue: 'pending chinese title',
        editingActors: true,
        editedActorsValue: 'pending actors',
    };

    searchStateNavigation()._resetPendingEdits.call(fakeThis);

    assert.equal(fakeThis.editingTitle, false);
    assert.equal(fakeThis.editingChineseTitle, false);
    assert.equal(fakeThis.editingActors, false);

    // 比照 result-card.js 既有 cancelEditX 慣例：只清 editingX，不清 editedXValue
    assert.equal(fakeThis.editedTitleValue, 'pending title');
    assert.equal(fakeThis.editedChineseTitleValue, 'pending chinese title');
    assert.equal(fakeThis.editedActorsValue, 'pending actors');
});

// ==================== Tier 2: 迴歸守衛 —— navigate() 不再自己碰 editingX ====================

test('navigate(-1): 第一檔第一候選（no-op return）→ editingActors 仍 true（本來就不該碰）', async () => {
    const fakeThis = {
        ...searchStateNavigation(),
        sampleGalleryOpen: false,
        currentIndex: 0,
        searchResults: [{ number: 'ABC-001' }],
        currentFileIndex: 0, // 不 >0 → 落純 return，不呼叫 switchToFile
        fileList: [{ path: '/a/x1.mp4' }],
        editingTitle: false,
        editingChineseTitle: false,
        editingActors: true,
    };

    await searchStateNavigation().navigate.call(fakeThis, -1);

    assert.equal(fakeThis.editingActors, true, 'no-op return 不得清掉未確認的編輯');
});

test('navigate(+1): 末檔末候選、無更多結果（no-op return）→ editingActors 仍 true（本來就不該碰）', async () => {
    const fakeThis = {
        ...searchStateNavigation(),
        sampleGalleryOpen: false,
        currentIndex: 0,
        searchResults: [{ number: 'ABC-001' }], // currentIndex 已是唯一/最後一個候選
        hasMoreResults: false, // && 短路，isLoadingMore/listMode 不會被讀到
        currentFileIndex: 0,
        fileList: [{ path: '/a/x1.mp4' }], // currentFileIndex 已是最後一檔
        editingTitle: false,
        editingChineseTitle: false,
        editingActors: true,
    };

    await searchStateNavigation().navigate.call(fakeThis, 1);

    assert.equal(fakeThis.editingActors, true, 'no-op return 不得清掉未確認的編輯');
});

test('navigate(-1): 真的換到上一個候選（正常範圍內導航）→ editingActors 仍 true（navigate 自己不再碰，交給 $watch）', async () => {
    // 迴歸守衛核心案例：這是舊版「真的換候選」會主動呼叫 _resetPendingEdits() 的分支。
    // Option C 後 navigate() 本身完全不碰 editingX——若未來把呼叫加回這個分支，
    // 本斷言會轉紅（editingActors 變 false）。
    // 正常範圍內導航分支會碰 document.querySelector（GSAP interrupt + slide-in 動畫）與
    // this.$nextTick，Node 測試環境無 DOM/Alpine，最小 stub 隔離掉（與本測試主張的
    // editingActors 迴歸守衛無關）。
    globalThis.document = { querySelector: () => null };
    const fakeThis = {
        ...searchStateNavigation(),
        sampleGalleryOpen: false,
        currentIndex: 1,
        searchResults: [{ number: 'ABC-001' }, { number: 'ABC-002' }],
        currentFileIndex: 0,
        fileList: [{ path: '/a/x1.mp4' }],
        editingTitle: false,
        editingChineseTitle: false,
        editingActors: true,
        _resetCoverState: () => {},
        preloadImages: () => {},
        $nextTick: (fn) => {},
    };

    await searchStateNavigation().navigate.call(fakeThis, -1);

    assert.equal(fakeThis.currentIndex, 0, 'sanity check: 候選真的換了');
    assert.equal(fakeThis.editingActors, true, 'navigate() 換候選的分支不再自己呼叫 _resetPendingEdits');
});

// ==================== Tier 3: 迴歸守衛 —— switchToFile() 不再自己碰 editingX ====================

test('switchToFile: 真的切檔（!file.number 早退分支）→ editingActors 仍 true（switchToFile 自己不再碰，交給 $watch）', async () => {
    window.t = (key) => key;

    const fakeThis = {
        ...searchStateFileList(),
        ...searchStateNavigation(), // 僅供 _resetPendingEdits 型別存在，非本測試呼叫對象
        _resetCoverState: () => {},
        listMode: 'file',
        currentFileIndex: 0,
        currentIndex: 2, // 離開檔（index 0）目前選到的候選
        fileList: [
            { path: '/a/x1.mp4', number: 'ABC-001', selectedCandidateIndex: 0 },
            { path: '/a/x2.mp4', number: null, filename: 'x2.mp4' }, // 目標檔無番號 → 落 !file.number 早退分支，最小 stub
        ],
        editingTitle: true,
        editingChineseTitle: true,
        editingActors: true,
    };

    await searchStateFileList().switchToFile.call(fakeThis, 1, 'first', false);

    // T2' snapshot：離開檔（index 0）的 selectedCandidateIndex 被寫成離開前的 currentIndex
    // （這部分邏輯本次未動，仍應成立）
    assert.equal(fakeThis.fileList[0].selectedCandidateIndex, 2, 'T2\' snapshot 應寫入離開檔的 selectedCandidateIndex');

    // Option C 迴歸守衛：switchToFile() 換檔本身不再直接清 editingX——若未來把
    // this._resetPendingEdits() 呼叫加回 switchToFile 內部，這裡會轉紅。
    assert.equal(fakeThis.editingTitle, true, 'switchToFile 換檔不再自己呼叫 _resetPendingEdits');
    assert.equal(fakeThis.editingChineseTitle, true, 'switchToFile 換檔不再自己呼叫 _resetPendingEdits');
    assert.equal(fakeThis.editingActors, true, 'switchToFile 換檔不再自己呼叫 _resetPendingEdits');
});
