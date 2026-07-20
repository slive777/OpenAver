// TASK-103-T5: handleFileDrop CD-11 abort registry 競態守衛
//
// 拖 A 後立刻拖 B：handleFileDrop 是同步 facade，fire-and-forget 呼叫私有 async
// `_resolveAndSearchDroppedFile`。同一輪 microtask 內，B 的 `_getAbortSignal('handleFileDrop')`
// 會先 abort A 手上的 controller，A 的 parseFilenames 因而 reject AbortError，A 的 catch
// 命中 `err.name === 'AbortError'` 早退，不寫任何 UI 狀態。
//
// file-list.js 是 ESM，直接 import searchStateFileList。fake `this` 不手抄
// `_getAbortSignal`/`_clearAbort`——用 Object.assign 把 search-flow.js 的真實作組進來
// （`_abortControllers` 定義在 base.js:99，不在 searchStateSearchFlow()/searchStateFileList()
// 回傳物件內，需額外補一個最小 shim 一起 Object.assign 進去）。
// 只 mock 外部依賴：window.SearchFile.parseFilenames、doSearch、showToast、window.t。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateFileList } from '../state/file-list.js';
import { searchStateSearchFlow } from '../state/search-flow.js';
import { searchStateBase } from '../state/base.js';

globalThis.window = globalThis;

function makeAbortError() {
  return new DOMException('The operation was aborted', 'AbortError');
}

// 模擬真實 fetch 對 AbortSignal 的接線：signal 已 abort 或稍後被 abort 都會 reject，
// 否則保持 pending 直到測試手動 resolve（模擬 API 回應到達）。
function makeParseFilenamesMock() {
  const calls = [];
  function parseFilenames(filenames, { signal } = {}) {
    const call = { filenames, signal };
    const promise = new Promise((resolve, reject) => {
      call.resolve = resolve;
      call.reject = reject;
      if (signal) {
        if (signal.aborted) {
          reject(makeAbortError());
        } else {
          signal.addEventListener('abort', () => reject(makeAbortError()), { once: true });
        }
      }
    });
    calls.push(call);
    return promise;
  }
  return { parseFilenames, calls };
}

function makeFakeThis(overrides = {}) {
  return Object.assign(
    {},
    searchStateBase(),      // requestId 真實初值（base.js:125）+ _abortControllers（base.js:99）
    searchStateSearchFlow(),
    searchStateFileList(),
    overrides,
  );
}

const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((r) => setTimeout(r, 0));
};

test('CD-11 mutation A：連續拖 A、B，A 因新請求被 abort → 最終 searchQuery 為 B 的番號、A 不寫入任何狀態', async () => {
  const { parseFilenames, calls } = makeParseFilenamesMock();
  window.SearchFile = { parseFilenames };
  window.t = (key) => key;

  const doSearchCalls = [];
  const toasts = [];
  const fakeThis = makeFakeThis({
    doSearch(q) { doSearchCalls.push(q); },
    showToast(msg, type) { toasts.push({ msg, type }); },
  });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'A.mp4' }]);
  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'B.mp4' }]);

  assert.equal(calls.length, 2, '兩次拖曳應各觸發一次 parseFilenames 呼叫');
  assert.equal(calls[0].signal.aborted, true, 'A 的 signal 應在 B 觸發時被 _getAbortSignal 同 key abort');

  // B 正常回應（在 A 之後才 resolve，模擬 A 回應人為延後於 B 的反序情境）
  calls[1].resolve([{ filename: 'B.mp4', number: 'B-001', has_subtitle: false }]);
  // 即使 A 的回應這時才姍姍來遲，promise 已因 abort 被 reject 過，settle 後的 resolve 是 no-op
  calls[0].resolve([{ filename: 'A.mp4', number: 'A-999', has_subtitle: false }]);
  await flush();

  assert.equal(fakeThis.searchQuery, 'B-001', '最終 searchQuery 必須是 B（A 被 abort，即使事後才 resolve 也不得覆蓋）');
  assert.deepEqual(doSearchCalls, ['B-001'], 'doSearch 只應被 B 觸發一次');
  assert.equal(fakeThis.errorText ?? '', '', 'A 被 abort 不得寫入 errorText');
  assert.equal(toasts.length, 0, 'A 被 abort 不得產生任何 toast');
});

test('CD-11 mutation B：拖 A 後立刻拖 B，A 因 abort reject → 不得產生任何 toast 或寫入 errorText，UI 只反映 B', async () => {
  const { parseFilenames, calls } = makeParseFilenamesMock();
  window.SearchFile = { parseFilenames };
  window.t = (key) => key;

  const toasts = [];
  const fakeThis = makeFakeThis({
    doSearch() {},
    showToast(msg, type) { toasts.push({ msg, type }); },
    errorText: '',
  });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'A.mp4' }]);
  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'B.mp4' }]);
  calls[1].resolve([{ filename: 'B.mp4', number: 'SONE-205', has_subtitle: false }]);
  await flush();

  assert.equal(fakeThis.errorText, '', 'A 的 AbortError catch 分支不得寫 errorText（早退是必要不是裝飾）');
  assert.equal(toasts.length, 0, 'A 的 abort 不得產生任何 toast');
  assert.equal(fakeThis.searchQuery, 'SONE-205');
});

test('CD-11：_getAbortSignal/_clearAbort 呼叫序——B 完成後 registry 內 handleFileDrop key 被正確清除（不被 A 的 stale finally 誤刪或誤留）', async () => {
  const { parseFilenames, calls } = makeParseFilenamesMock();
  window.SearchFile = { parseFilenames };
  window.t = (key) => key;

  const fakeThis = makeFakeThis({
    doSearch() {},
    showToast() {},
  });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'A.mp4' }]);
  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'B.mp4' }]);
  calls[1].resolve([{ filename: 'B.mp4', number: 'B-001', has_subtitle: false }]);
  await flush();

  assert.equal(
    fakeThis._abortControllers.handleFileDrop,
    undefined,
    'B 完成後應清空 registry；A 的 finally（比對舊 signal）不得覆蓋/殘留',
  );
});

test('handleFileDrop: 單檔拖曳、API 成功但無番號 → errorText 顯示 number_not_recognized（零回歸）', async () => {
  window.SearchFile = {
    parseFilenames: async () => [{ filename: 'random_clip.mp4', number: null, has_subtitle: false }],
  };
  window.t = (key) => key;
  const fakeThis = makeFakeThis({ doSearch() {}, showToast() {} });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'random_clip.mp4' }]);
  await flush();

  assert.equal(fakeThis.errorText, 'search.error.number_not_recognized');
  assert.equal(fakeThis.pageState, 'error');
});

test('handleFileDrop: API 失敗（非 AbortError）→ errorText 顯示 number_parse_unavailable（DoD #3 mutation 錨点）', async () => {
  window.SearchFile = {
    parseFilenames: async () => { throw new Error('network fail'); },
  };
  window.t = (key) => key;
  const fakeThis = makeFakeThis({ doSearch() {}, showToast() {} });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'x.mp4' }]);
  await flush();

  assert.equal(fakeThis.errorText, 'search.error.number_parse_unavailable');
  assert.equal(fakeThis.pageState, 'error');
});

// Codex PR#112 review P2：這條與上面的 CD-11 mutation A/B 是不同層的競態——CD-11 那組是
// 「拖 A 又拖 B」，靠 abort registry（_getAbortSignal 同 key abort）處理；這裡是「拖 A 途中
// 使用者改走手動搜尋 B」，abort registry 管不到（不同呼叫路徑，沒人 abort handleFileDrop 的
// controller），必須靠 doSearch/cancelSearch 共用的 requestId generation 機制守（search-flow.js
// :107 `this.requestId++` / :602 同）。

test('Codex P2: 拖檔 parse 中途使用者手動搜尋（requestId bump）→ stale continuation 不覆蓋新搜尋狀態', async () => {
  const { parseFilenames, calls } = makeParseFilenamesMock();
  window.SearchFile = { parseFilenames };
  window.t = (key) => key;

  const doSearchCalls = [];
  const fakeThis = makeFakeThis({
    doSearch(q) { doSearchCalls.push(q); },
    showToast() {},
  });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'DROP-001.mp4' }]);
  assert.equal(calls.length, 1, '應觸發一次 parseFilenames 呼叫');

  // 模擬使用者在拖檔 parse pending 期間手動搜尋 B：doSearch(B) 內部 cancelSearch()+requestId++
  // 讓 generation 前進（doSearch 本身已有獨立測試覆蓋，這裡只驗 file-list.js 的 stale-check）。
  fakeThis.requestId++;

  // 拖檔 A 的 parse 這時才回來（stale continuation）
  calls[0].resolve([{ filename: 'DROP-001.mp4', number: 'DROP-001', has_subtitle: false }]);
  await flush();

  assert.notEqual(fakeThis.searchQuery, 'DROP-001', 'stale 拖檔 continuation 不得寫入 searchQuery 覆蓋手動搜尋');
  assert.deepEqual(doSearchCalls, [], 'stale 拖檔 continuation 不得呼叫 doSearch');
  assert.equal(fakeThis.errorText ?? '', '', 'stale 拖檔 continuation 不得寫入 errorText');
});

test('Codex P2 對照（happy path）：拖檔 parse 期間 requestId 未變 → 正常寫入 searchQuery + 呼叫 doSearch（確認修法未誤殺正常拖檔）', async () => {
  const { parseFilenames, calls } = makeParseFilenamesMock();
  window.SearchFile = { parseFilenames };
  window.t = (key) => key;

  const doSearchCalls = [];
  const fakeThis = makeFakeThis({
    doSearch(q) { doSearchCalls.push(q); },
    showToast() {},
  });

  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'DROP-001.mp4' }]);
  calls[0].resolve([{ filename: 'DROP-001.mp4', number: 'DROP-001', has_subtitle: false }]);
  await flush();

  assert.equal(fakeThis.searchQuery, 'DROP-001');
  assert.deepEqual(doSearchCalls, ['DROP-001'], 'doSearch 應被拖檔 continuation 呼叫一次');
});

// Codex PR#112 review 第 2 輪 P2：拖檔 parse pending 期間，使用者改走「載入我的最愛」等
// file-list 替換操作（setFileList，loadFavorite/addFiles/addFolder 共用出口）。這條路徑
// 不共用 handleFileDrop 的 abort registry key（不同 key，_getAbortSignal 互相 abort 不到），
// 上面 CD-11/requestId 那組測試都堵不住這個洞。
//
// 第2輪修法（改 requestId bump）已在第 3 輪 revert——Codex 指出它會讓進行中的 doSearch
// stream 誤走 requestId-mismatch 早退卻不清理 _searchSnapshot/activeEventSource，點掉
// loading cancel 按鈕會用舊 snapshot 蓋掉剛載入的清單。現改為方向 (a)：setFileList 直接
// abort handleFileDrop 的 controller（`this._abortControllers['handleFileDrop']?.abort()`），
// 不動 requestId、不碰 search 狀態機；_resolveAndSearchDroppedFile 靠新增的
// `signal.aborted` 檢查早退（同 key controller 被 abort 後 signal.aborted 同步變 true，
// 不需要 mock 端接線 abort 事件監聽）。

test('Codex P2(第3輪 revert 第2輪，改走 abort registry 方向 a): 拖檔 parse pending 期間 setFileList 替換清單（模擬 loadFavorite）→ 拖檔的 stale continuation 不得覆蓋新清單', async () => {
  const dropCalls = [];
  const favCalls = [];
  // 拖檔與 setFileList 共用同一個 window.SearchFile.parseFilenames，用 filenames 內容區分
  // 「這通是拖檔的呼叫」還是「這通是 setFileList 的呼叫」，讓拖檔那次刻意晚 resolve。
  window.SearchFile = {
    parseFilenames: (filenames) => {
      const entry = { filenames };
      const promise = new Promise((resolve) => { entry.resolve = resolve; });
      if (filenames[0] === 'DROP-001.mp4') {
        dropCalls.push(entry);
      } else {
        favCalls.push(entry);
      }
      return promise;
    },
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  window.t = (key) => key;
  // filter-files 端點：success:false → setFileList 保留原始 paths，直接走到 parseFilenames。
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ success: false }) });

  const doSearchCalls = [];
  const fakeThis = makeFakeThis({
    doSearch(q) { doSearchCalls.push(q); },
    showToast() {},
    switchToFile: async () => {},   // 隔離掉真 EventSource，非本測試焦點
    _resetCoverState() {},
  });

  // 1. 拖檔 A：parse 還 pending（capturedRequestId 捕獲的是 bump 前的 requestId）
  searchStateFileList().handleFileDrop.call(fakeThis, [{ name: 'DROP-001.mp4' }]);
  assert.equal(dropCalls.length, 1, '拖檔應觸發一次 parseFilenames 呼叫');

  // 2. 使用者改按「我的最愛」→ setFileList 清單替換（loadFavorite/addFiles/addFolder 共用出口）
  const pSetFileList = fakeThis.setFileList(['/fav/FAV-001.mp4']);
  await flush();
  assert.equal(favCalls.length, 1, 'setFileList 應觸發一次 parseFilenames 呼叫（與拖檔那次分開計數）');

  // setFileList 的 parse 先回應，正常建出 favorites 清單
  favCalls[0].resolve([{ filename: 'FAV-001.mp4', number: 'FAV-001', has_subtitle: false }]);
  await flush();
  await pSetFileList;

  assert.equal(fakeThis.fileList.length, 1, 'setFileList 應正常建出清單');
  assert.equal(fakeThis.fileList[0].path, '/fav/FAV-001.mp4', 'fileList 應是 favorites 的內容');
  assert.equal(fakeThis.searchQuery, 'FAV-001', 'searchQuery 應是 setFileList 寫入的 FAV-001');

  // 3. 拖檔 A 的 parse 這時才姍姍來遲 resolve（stale continuation）
  dropCalls[0].resolve([{ filename: 'DROP-001.mp4', number: 'DROP-001', has_subtitle: false }]);
  await flush();

  assert.equal(fakeThis.fileList.length, 1, 'stale 拖檔 continuation 不得清空/覆蓋 setFileList 剛建好的清單');
  assert.equal(fakeThis.fileList[0].path, '/fav/FAV-001.mp4', 'fileList 仍應是 favorites，不被拖檔覆蓋');
  assert.notEqual(fakeThis.searchQuery, 'DROP-001', 'stale 拖檔 continuation 不得把 searchQuery 改回 DROP-001');
  assert.equal(fakeThis.searchQuery, 'FAV-001', 'searchQuery 應維持 setFileList 寫入的 FAV-001');
  assert.deepEqual(doSearchCalls, [], 'stale 拖檔 continuation 不得呼叫 doSearch（會拿 stale 番號清掉剛載入的清單）');
});
