// TASK-107-P2-T5（spec-107 功能 C / plan P2-T5，CD-106-5 漏網路徑）
//
// removeFile 移除「當前檔」時，先把 currentFileIndex 重指鄰檔（file-list.js:287-291）
// 才呼叫 switchToFile（:298）；而 switchToFile 頂部（:12-13）會做
//   fileList[currentFileIndex].selectedCandidateIndex = this.currentIndex
// 此時 currentFileIndex 已是鄰檔、currentIndex 仍是外出檔的候選值 → 把外出檔的
// 候選 index 寫進鄰檔（汙染）。鄰檔候選數 ≤ 該值時 selectedCandidateIndex 越界。
//
// 定版修法（D-C1）：switchToFile 加 skipPersist 參數，removeFile 移除當前檔那條傳
// skipPersist=true（外出檔已 splice、其候選 index 無須也不該被保存）。正常左右導航
// skipPersist 預設 false、行為零變化。
//
// 本檔跑「真的 switchToFile」（非 spy）以驗證頂部持久化的實際寫入對象——這是
// remove-file-edit-preserve.test.mjs（stub switchToFile）看不到的層。
// 註：現行碼中此汙染於「整理」時被 batch.js:363/501 的 re-sync（同步 current 檔）
// 遮蔽，故屬 latent（stored state 短暫錯誤）；skipPersist 從源頭消除汙染，使正確性
// 不再依賴每條整理入口都記得 re-sync（defense-in-depth）。守衛鎖 stored 不變式本身。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateFileList } from '../state/file-list.js';

// switchToFile 走「searched 鄰檔」分支（file-list.js:36）會碰的最小 DOM/動畫依賴
globalThis.window = globalThis;
globalThis.document = globalThis.document || { querySelector: () => null };
globalThis.window.t = globalThis.window.t || ((k) => k);
// gsap 保持 undefined（typeof gsap !== 'undefined' 分支跳過）

function makeFile(name, nCands, { searched = true, selectedCandidateIndex = 0 } = {}) {
    return {
        filename: name,
        number: name,
        searched,
        scraped: false,
        searchResults: Array.from({ length: nCands }, (_, i) => ({ title: `${name}-c${i}`, __idx: i })),
        hasMoreResults: false,
        selectedCandidateIndex,
    };
}

function makeState(files, currentFileIndex, currentIndex) {
    return {
        ...searchStateFileList(),
        fileList: files,
        currentFileIndex,
        currentIndex,
        listMode: 'file',
        displayMode: 'detail',
        searchResults: [],
        hasMoreResults: false,
        pageState: 'result',
        clearAll() { this.fileList = []; },
        saveState() {},
        _resetCoverState() {},
        $nextTick() {},
        fetchUserTagsForCurrent() {},
    };
}

test('removeFile 移除當前檔：鄰檔 selectedCandidateIndex 不被外出檔 currentIndex 汙染 (AC-C3)', () => {
    // A = 當前檔（3 候選、正在看候選 #2），B = 鄰檔（1 候選、自己的 selectedCandidateIndex=0）
    const state = makeState(
        [makeFile('A', 3), makeFile('B', 1, { selectedCandidateIndex: 0 })],
        0,   // currentFileIndex → A
        2,   // currentIndex → 正在看 A 的候選 #2
    );

    state.removeFile(0);  // 移除當前檔 A → B 成為當前檔

    const B = state.fileList[0];
    assert.equal(state.currentFileIndex, 0, 'B 應成為當前檔');
    // 核心不變式：B 保留自己的候選 index 0，不被外出檔 A 的 currentIndex(2) 汙染
    assert.equal(
        B.selectedCandidateIndex, 0,
        '鄰檔 selectedCandidateIndex 應仍為自己的 0，不得被外出檔 currentIndex(2) 覆蓋（越界會讓整理送空 metadata）',
    );
    // 越界防線：即使假設整理直接讀 stored（不 re-sync），也不得越界
    assert.ok(
        B.selectedCandidateIndex < B.searchResults.length,
        '鄰檔 selectedCandidateIndex 不得越界其候選數',
    );
});

test('反向守衛：正常左右導航（switchToFile 預設 skipPersist=false）仍持久化外出檔候選', () => {
    // 從 A（正在看候選 #2）切到 B —— 外出檔 A 的候選應被保存為 2（正常行為零變化）
    const state = makeState(
        [makeFile('A', 3), makeFile('B', 2)],
        0,   // 當前 A
        2,   // 正在看 A 候選 #2
    );

    // 預設呼叫（不傳 skipPersist）＝正常導航
    state.switchToFile(1, 'first', false);

    assert.equal(
        state.fileList[0].selectedCandidateIndex, 2,
        '正常導航離開 A 時，A 的候選 index(2) 必須被持久化（skipPersist 預設 false，行為不得回歸）',
    );
    assert.equal(state.currentFileIndex, 1, '已切到 B');
});
