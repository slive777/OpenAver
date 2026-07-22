// TASK-106 Option C Part 2: setupAutoSave() 新增的候選改變 $watch —— UX 便利層
// （非權威保證，權威保證見 confirm-edit-identity-guard.test.mjs 的 identity guard）。
//
// 這裡不能測試真正的 Alpine reactivity（$watch 底層依賴 Alpine.effect() 的 Proxy
// 依賴追蹤，Node 測試環境沒有 Alpine，$watch 是 Alpine 注入 x-data 物件的 magic method，
// 不是 persistence.js 能獨立提供的東西）——用 spy 取代 this.$watch，只驗證：
// 1. setupAutoSave() 確實多掛了一個「函式表達式」形式（非字串 key）的 $watch，且
//    callback 是呼叫 this._resetPendingEdits()。
// 2. 抽出該 watcher 的 getter 函式本身直接測試其純邏輯（不依賴 Alpine reactivity）：
//    - 候選導覽位置改變（currentIndex）→ getter 回傳值不同。
//    - 換檔（fileList 模式下當前檔案的 `path` 不同）→ getter 回傳值不同。
//    - 候選清單被整批替換（陣列參照換了、長度也不同）→ getter 回傳值不同。
//    - 只有候選物件內部欄位被直寫（模擬打字/date 變更/checkLocalStatus/translateWithAI 等
//      不透過 editingX 流程的直寫）、candidate 在陣列中的位置未變 → getter 回傳值不變
//      （deepEqual）。這證明我們選的複合表達式只讀 primitives（fileKey/index/mode/length），
//      不會像 `$watch('current()', cb)` 那樣被 Alpine 內部的 JSON.stringify 深度追蹤
//      進候選物件的巢狀欄位而在打字時誤觸發（見 persistence.js 該段落大註解 + Alpine
//      官方文件 https://alpinejs.dev/magics/watch「Deep watching」段的查證結論）。
//    - Codex PR#115 P2 fix：純 reindex（removeFile() 移除 currentFileIndex 之前的一列，
//      只遞減 currentFileIndex，同一份 file 物件、同一個 path）→ getter 回傳值不變
//      （deepEqual）。舊版鍵定 `currentFileIndex`（位置數字）會誤判成「候選換了」而
//      誤清正在編輯的內容；改鍵定 `path`（該檔案的穩定字串識別）後才正確不觸發。
//
// 「這個 getter 的回傳值有沒有變」只是必要條件，不是充分條件——Alpine 的 $watch 是否
// 真的只在回傳值變動時才觸發 callback（而非任何被讀取到的 reactive 依賴變動就觸發），
// 是 Alpine 內部機制，本測試證明不了，需真機 CDP 或 owner 手動驗證候選切換時編輯框
// 正確關閉、且打字/date 變更時編輯框不會意外關閉。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStatePersistence } from '../state/persistence.js';

function captureWatchers(fakeThisOverrides = {}) {
    const watchCalls = [];
    const fakeThis = {
        ...searchStatePersistence(),
        $watch: (keyOrGetter, cb) => watchCalls.push({ keyOrGetter, cb }),
        _setTimer: () => {},
        _resetPendingEdits: () => { fakeThis._resetPendingEditsCalls = (fakeThis._resetPendingEditsCalls || 0) + 1; },
        ...fakeThisOverrides,
    };
    searchStatePersistence().setupAutoSave.call(fakeThis);
    return { fakeThis, watchCalls };
}

test('setupAutoSave: 掛了一個函式表達式（非字串 key）的 $watch，callback 呼叫 _resetPendingEdits', () => {
    const { fakeThis, watchCalls } = captureWatchers();

    const functionWatchers = watchCalls.filter(w => typeof w.keyOrGetter === 'function');
    assert.equal(functionWatchers.length, 1, '應恰好新增一個函式表達式 $watch（候選改變偵測）');

    functionWatchers[0].cb();
    assert.equal(fakeThis._resetPendingEditsCalls, 1, '該 watcher 的 callback 應呼叫 _resetPendingEdits()');

    // 既有 4 個字串 key 的 $watch（searchResults/currentIndex/fileList/listMode，autosave 用）不受影響
    const stringWatchers = watchCalls.filter(w => typeof w.keyOrGetter === 'string');
    assert.equal(stringWatchers.length, 4, '既有 4 個 autosave 用的字串 $watch 應保留');
});

test('候選改變 watcher 的 getter：純數值/字串複合值，位置改變時不同、僅內部欄位直寫時相同', () => {
    const watchCalls = [];
    const fakeThis = {
        ...searchStatePersistence(),
        $watch: (keyOrGetter, cb) => watchCalls.push({ keyOrGetter, cb }),
        _setTimer: () => {},
        _resetPendingEdits: () => {},
        listMode: 'search',
        currentFileIndex: 0,
        currentIndex: 0,
        searchResults: [{ number: 'A', title: 'orig' }, { number: 'B', title: 'orig-b' }],
        fileList: [],
    };
    searchStatePersistence().setupAutoSave.call(fakeThis);
    const getter = watchCalls.find(w => typeof w.keyOrGetter === 'function').keyOrGetter;

    const snapshot1 = getter();

    // 模擬「打字」/「date @change」/「checkLocalStatus」/「translateWithAI」等不透過
    // editingX 流程、直接 mutate 候選物件內部欄位的既有寫法——候選在陣列中的位置不變。
    fakeThis.searchResults[0].title = 'mutated during typing';
    fakeThis.searchResults[0].date = '2026-01-01';
    fakeThis.searchResults[0]._localStatus = { exists: true };

    const snapshot2 = getter();
    assert.deepEqual(snapshot2, snapshot1, '候選內部欄位直寫、位置未變 → 複合表達式回傳值應相同（只讀 primitives，不因巢狀欄位變動而改變）');

    // 候選真的換位（currentIndex 改變）→ 回傳值應不同
    fakeThis.currentIndex = 1;
    const snapshot3 = getter();
    assert.notDeepEqual(snapshot3, snapshot1, 'currentIndex 改變 → 複合表達式回傳值應不同');

    // 清單被整批替換（長度改變）→ 回傳值應不同（即使 currentIndex/currentFileIndex/listMode 都改回原值）
    fakeThis.currentIndex = 0;
    fakeThis.searchResults = [{ number: 'C', title: 'new' }];
    const snapshot4 = getter();
    assert.notDeepEqual(snapshot4, snapshot1, '清單被整批替換（長度改變）→ 複合表達式回傳值應不同');
});

// Codex PR#115 P2 fix：file 模式下鍵定 `path`（穩定字串識別）而非 `currentFileIndex`
// （位置數字）—— removeFile() 移除目前檢視檔案「之前」的一列時，只會遞減
// currentFileIndex（見 file-list.js removeFile 的 removingCurrent gate 註解：目前
// 檢視的檔沒變，只是它在陣列中的位置往前移一格），舊版鍵定 currentFileIndex 會被這個
// 純 reindex 誤觸發、把使用者正在編輯、尚未確認的內容清掉；改鍵定 path 後純 reindex
// 不再誤觸發，真正換檔（path 不同）才觸發。
test('候選改變 watcher 的 getter（file 模式）：鍵定 path 而非 currentFileIndex —— 純 reindex（同 path）不變、換檔（不同 path）才變', () => {
    const watchCalls = [];
    const fileB = { path: '/a/fileB.mp4', searchResults: [{ number: 'B', title: 'B 原始標題' }] };
    const fakeThis = {
        ...searchStatePersistence(),
        $watch: (keyOrGetter, cb) => watchCalls.push({ keyOrGetter, cb }),
        _setTimer: () => {},
        _resetPendingEdits: () => {},
        listMode: 'file',
        currentFileIndex: 1,
        currentIndex: 0,
        searchResults: [],
        fileList: [
            { path: '/a/fileA.mp4', searchResults: [{ number: 'A', title: 'A 原始標題' }] },
            fileB, // 目前檢視的檔案（index 1）
        ],
    };
    searchStatePersistence().setupAutoSave.call(fakeThis);
    const getter = watchCalls.find(w => typeof w.keyOrGetter === 'function').keyOrGetter;

    const snapshot1 = getter();
    assert.deepEqual(snapshot1, ['/a/fileB.mp4', 0, 'file', 1], 'sanity: getter 回傳 [path, currentIndex, listMode, length]');

    // 模擬 removeFile(0)（移除目前檢視檔案「之前」的一列）：fileList[0] 被 splice 掉，
    // currentFileIndex 遞減成 0——同一份 fileB 物件，仍是目前檢視的檔案，path 不變。
    fakeThis.fileList = [fileB];
    fakeThis.currentFileIndex = 0;
    const snapshot2 = getter();
    assert.deepEqual(snapshot2, snapshot1, '純 reindex（同一份 file 物件、path 不變）→ 複合表達式回傳值應相同，不誤觸發 watcher（不得清掉正在編輯的內容）');

    // 真的換檔（path 不同）→ 回傳值應不同
    fakeThis.fileList = [fileB, { path: '/a/fileC.mp4', searchResults: [{ number: 'C' }] }];
    fakeThis.currentFileIndex = 1;
    const snapshot3 = getter();
    assert.notDeepEqual(snapshot3, snapshot1, '換檔（path 不同）→ 複合表達式回傳值應不同');
});
