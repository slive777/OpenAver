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
    // TASK-106 Option C: switchToFile 不再呼叫 this._resetPendingEdits()（改由
    // persistence.js setupAutoSave 的 $watch 統一處理，見 reset-pending-edits.test.mjs），
    // 故本檔不再需要 _resetPendingEdits no-op 隔離 stub。
    { _resetCoverState() {}, _ensureBlankCard() {} },
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


