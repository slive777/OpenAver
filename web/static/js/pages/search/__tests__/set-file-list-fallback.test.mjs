// TASK-103-T5 CD-4b: setFileList 批次失敗不吞檔案守衛
//
// parseFilenames 改 fail-loud 後，setFileList:316 的呼叫會 throw。若只是包
// `try { ... } catch { showToast(...); return; }`，使用者拖進來的 N 個檔案會在
// 建 fileList 之前就 return——已選檔案憑空消失。CD-4b 的方案是在 catch 內合成一個
// 「全員 number:null」的 parseResults，讓程式流原封不動走進既有的 validIndices 過濾
// 迴圈與既有的 fileList 建構，兩條路徑physically 共用同一份建構程式碼。
//
// file-list.js 是 ESM，直接 import。fake `this` 用 searchStateBase()（真正的
// needsNumberInput / _resetCoverState / _abortControllers 初值）+ searchStateSearchFlow()
// （_getAbortSignal/_clearAbort）+ searchStateFileList()（setFileList/loadFavorite/switchToFile
// 本體）組裝，只 mock 外部依賴：window.SearchFile.*、showToast、window.t、fetch、searchAll。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateFileList } from '../state/file-list.js';
import { searchStateSearchFlow } from '../state/search-flow.js';
import { searchStateBase } from '../state/base.js';

globalThis.window = globalThis;

function makeFakeThis(overrides = {}) {
  return Object.assign(
    {},
    searchStateBase(),
    searchStateSearchFlow(),
    searchStateFileList(),
    // switchToFile()（number:null 分支）呼叫的既有 _resetCoverState() 依賴 Alpine 注入的
    // this.$nextTick，Node 測試環境沒有 Alpine——不測 _resetCoverState 本身（非本卡範圍），
    // 用 no-op 隔離掉，避免與 CD-4b 邏輯無關的 TypeError 污染斷言。
    { _resetCoverState() {} },
    overrides,
  );
}

// filter-files 端點回 success:false → setFileList 保留原始 paths 不做重寫（測試不關心此分支）
function stubFilterFilesFetch() {
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ success: false }),
  });
}

test('CD-4b: parseFilenames reject（非 AbortError）→ 已選檔案不憑空消失，全員 number:null + needsNumberInput() 為 true + 僅一則 toast', async () => {
  stubFilterFilesFetch();
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async () => { throw new Error('API down'); },
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };

  const paths = ['/a/x1.mp4', '/a/x2.mp4', '/a/x3.mp4'];
  const toasts = [];
  const fakeThis = makeFakeThis({
    showToast(msg, type) { toasts.push({ msg, type }); },
  });

  await searchStateFileList().setFileList.call(fakeThis, paths);

  assert.equal(fakeThis.fileList.length, paths.length, 'CD-4b: N 個已選檔案不得憑空消失');
  for (const entry of fakeThis.fileList) {
    assert.equal(entry.number, null, 'fallback entry number 恆為 null');
    assert.equal(fakeThis.needsNumberInput(entry), true, '每列都應出現「手動輸入番號」逃生口');
  }
  assert.equal(toasts.length, 1, 'CD-4b: 有且僅有一則 toast（不得與 filtered_no_number 雙 toast）');
  assert.equal(toasts[0].msg, 'search.error.number_parse_unavailable');
  assert.equal(toasts[0].type, 'error');
});

test('CD-4b: fallback 路徑建出的 fileList entry 欄位集合與正常路徑逐欄相同（防未來分岔，DoD #5）', async () => {
  stubFilterFilesFetch();
  window.t = (key) => key;

  // 正常路徑（switchToFile 會走 searched 分支，避免真的觸發 EventSource，先 no-op 掉）
  window.SearchFile = {
    parseFilenames: async (filenames) => filenames.map((f) => ({ filename: f, number: 'ABC-123', has_subtitle: false })),
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  const normalThis = makeFakeThis({ showToast() {}, switchToFile: async () => {} });
  await searchStateFileList().setFileList.call(normalThis, ['/a/x1.mp4']);
  const normalKeys = Object.keys(normalThis.fileList[0]).sort();

  // fallback 路徑
  window.SearchFile = {
    parseFilenames: async () => { throw new Error('API down'); },
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  const fallbackThis = makeFakeThis({ showToast() {}, switchToFile: async () => {} });
  await searchStateFileList().setFileList.call(fallbackThis, ['/a/x1.mp4']);
  const fallbackKeys = Object.keys(fallbackThis.fileList[0]).sort();

  assert.deepEqual(fallbackKeys, normalKeys, 'fallback 與正常路徑的 entry 欄位集合必須逐欄相同');
});

test('CD-4b + loadFavorite: fallback 觸發時，自動搜尋 timer 不誤發空批次請求（searchAll 不被呼叫）', async () => {
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async () => { throw new Error('API down'); },
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  globalThis.fetch = async (url) => {
    if (String(url).includes('/api/search/favorite-files')) {
      return { ok: true, json: async () => ({ success: true, files: ['/a/x1.mp4', '/a/x2.mp4'] }) };
    }
    return { ok: true, json: async () => ({ success: false }) };
  };

  let searchAllCalls = 0;
  let scheduledFn = null;
  const fakeThis = makeFakeThis({
    showToast() {},
    searchAll() { searchAllCalls++; },
    _setTimer(key, fn) { scheduledFn = fn; }, // T4.2：不真的排程，讓測試手動觸發
  });

  await searchStateFileList().loadFavorite.call(fakeThis);

  assert.equal(fakeThis.fileList.length, 2, 'fallback 仍應建出檔案清單（不吞檔案）');
  assert.ok(typeof scheduledFn === 'function', '_setTimer 應被呼叫排程自動搜尋 callback');
  scheduledFn();
  assert.equal(searchAllCalls, 0, 'fallback 全員 number:null → 篩選結果應為空 → searchAll 不應被誤發');
});

test('CD-4b: parseFilenames reject 是 AbortError → 與 setFileList 既有語意一致，靜默 return，不建 fallback fileList', async () => {
  stubFilterFilesFetch();
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async () => { throw new DOMException('The operation was aborted', 'AbortError'); },
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };

  const toasts = [];
  const fakeThis = makeFakeThis({
    showToast(msg, type) { toasts.push({ msg, type }); },
  });

  await searchStateFileList().setFileList.call(fakeThis, ['/a/x1.mp4']);

  assert.deepEqual(fakeThis.fileList, [], 'AbortError 是「被新請求取代」語意，不應建立 fallback fileList');
  assert.equal(toasts.length, 0, 'AbortError 不應顯示任何 toast');
});

test('CD-4b(第4輪 Codex P2): fallback 全員 number:null → 清掉 spotlight 殘留的舊 searchQuery（避免按 Enter 搜到 stale 番號）', async () => {
  stubFilterFilesFetch();
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async () => { throw new Error('API down'); },
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };

  const fakeThis = makeFakeThis({
    showToast() {},
    switchToFile: async () => {},
    searchQuery: 'OLD-999',   // 上一次搜尋殘留在 spotlight 輸入框
  });

  await searchStateFileList().setFileList.call(fakeThis, ['/a/x1.mp4', '/a/x2.mp4']);

  assert.equal(fakeThis.fileList.length, 2, 'CD-4b: 已選檔案仍保留');
  assert.equal(fakeThis.searchQuery, '', 'fallback 後 searchQuery 必須清空——否則清單要求手動輸入番號、輸入框卻殘留 OLD-999，按 Enter 會搜到 stale 番號');
});
