// TASK-106-T5 CD-106-6: _resetPendingEdits() + B1 no-op gating + switchToFile 共存
//
// 三層測試（見 TASK-106-T5.md「Test Strategy」/「現況分析」逐行 trace）：
// 1. _resetPendingEdits() 本身：零 DOM，直接 .call(fakeThis)。
// 2. B1 no-op 守衛：navigate() 兩條 no-op return 分支（第一檔第一候選按 ←／
//    末檔末候選按 →）已逐行確認 return 前不碰 document/gsap/Image/$nextTick，
//    可零 stub 直接呼叫真實 navigate。
// 3. switchToFile 共存：T2' snapshot（:12-14，離開檔 selectedCandidateIndex）與
//    T5 reset（:16 後）同一次呼叫中都要發生，選 `!file.number` 分支（最小 stub）
//    驗證兩個效果都落地。
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

// ==================== Tier 2: B1 no-op 守衛（零 stub，真實 navigate） ====================

test('navigate(-1): 第一檔第一候選（no-op return :64）→ editingActors 仍 true（reset 未觸發）', async () => {
    const fakeThis = {
        ...searchStateNavigation(),
        sampleGalleryOpen: false,
        currentIndex: 0,
        searchResults: [{ number: 'ABC-001' }],
        currentFileIndex: 0, // 不 >0 → 落 :64 純 return，不呼叫 switchToFile
        fileList: [{ path: '/a/x1.mp4' }],
        editingTitle: false,
        editingChineseTitle: false,
        editingActors: true,
    };

    await searchStateNavigation().navigate.call(fakeThis, -1);

    assert.equal(fakeThis.editingActors, true, 'no-op return 不得清掉未確認的編輯');
});

test('navigate(+1): 末檔末候選、無更多結果（no-op return :84）→ editingActors 仍 true（reset 未觸發）', async () => {
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

// ==================== Tier 3: switchToFile 共存（T2' snapshot + T5 reset） ====================

test('switchToFile: 離開檔 selectedCandidateIndex 被 snapshot 且 editingActors 同時被 reset（不互相覆蓋）', async () => {
    window.t = (key) => key;

    const fakeThis = {
        ...searchStateFileList(),
        ...searchStateNavigation(), // switchToFile 跨 mixin 呼叫 _resetPendingEdits（同 _resetCoverState 慣例）
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

    // T2' snapshot（:12-14）：離開檔（index 0）的 selectedCandidateIndex 被寫成離開前的 currentIndex
    assert.equal(fakeThis.fileList[0].selectedCandidateIndex, 2, 'T2\' snapshot 應寫入離開檔的 selectedCandidateIndex');

    // T5 reset（:16 後）：三個編輯 buffer 同時被清空
    assert.equal(fakeThis.editingTitle, false);
    assert.equal(fakeThis.editingChineseTitle, false);
    assert.equal(fakeThis.editingActors, false, 'switchToFile 真的切檔應觸發 _resetPendingEdits');
});
