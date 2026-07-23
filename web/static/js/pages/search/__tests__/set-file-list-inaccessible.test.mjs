// TASK-107-P2-T6（spec-107 功能 D）: setFileList 桌面拖檔 path_inaccessible 表面化守衛
//
// 桌面 pywebview 拖入未掛載/UNC/無權限檔 → filter-files 回 rejected.inaccessible。
// setFileList 應：
//   (1) inaccessible-only → 只顯示 path_inaccessible（error），不出通用「已過濾」toast、
//       不出 no_valid_files、明確中止（fileList 空）。
//   (2) 無 inaccessible、全員抽不出番號 → 正常顯示 no_valid_files，不誤出 path_inaccessible。
//   (3) mixed（inaccessible + 其他桶如副檔名）→ 通用 toast 涵蓋其他桶 + path_inaccessible 皆出。
//
// 組裝方式沿用 set-file-list-fallback.test.mjs：真 setFileList 本體，只 mock 外部依賴。

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
    { _resetCoverState() {} },
    overrides,
  );
}

// filter-files 回指定 result；其餘 URL 回 success:false（本檔不觸發）
function stubFilterFiles(result) {
  globalThis.fetch = async (url) => {
    if (String(url).includes('/api/search/filter-files')) {
      return { ok: true, json: async () => result };
    }
    return { ok: true, json: async () => ({ success: false }) };
  };
}

test('D(1) inaccessible-only：只顯示 path_inaccessible、無通用 toast、無 no_valid_files、中止', async () => {
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async (fs) => fs.map((f) => ({ filename: f, number: null, has_subtitle: false })),
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  // 桌面拖單一未掛載檔 → filter-files 全濾（files 空）、只有 inaccessible
  stubFilterFiles({
    success: true,
    files: [],
    rejected: { extension: 0, size: 0, not_found: 0, inaccessible: 1 },
    total_rejected: 1,
  });

  const toasts = [];
  const fakeThis = makeFakeThis({ showToast(msg, type) { toasts.push({ msg, type }); } });

  await searchStateFileList().setFileList.call(fakeThis, ['/mnt/z/lan/vid.mp4']);

  const keys = toasts.map((t) => t.msg);
  assert.deepEqual(fakeThis.fileList, [], 'inaccessible-only 應中止、不建 fileList');
  assert.ok(keys.includes('search.error.path_inaccessible'), '應顯示 path_inaccessible');
  assert.equal(
    toasts.find((t) => t.msg === 'search.error.path_inaccessible').type, 'error',
    'path_inaccessible 為 error 類型',
  );
  assert.ok(!keys.includes('search.filelist.filtered_count'), 'inaccessible-only 不應出通用「已過濾」toast');
  assert.ok(!keys.includes('search.toast.no_valid_files'), 'inaccessible-only 不應補 no_valid_files（已 path_inaccessible 中止）');
});

test('D(2) 反向：無 inaccessible、全員抽不出番號 → 正常 no_valid_files、不誤出 path_inaccessible', async () => {
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async (fs) => fs.map((f) => ({ filename: f, number: null, has_subtitle: false })),
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  stubFilterFiles({
    success: true,
    files: [{ path: '/a/no_number.mp4', has_nfo: false }],
    rejected: { extension: 0, size: 0, not_found: 0, inaccessible: 0 },
    total_rejected: 0,
  });

  const toasts = [];
  const fakeThis = makeFakeThis({ showToast(msg, type) { toasts.push({ msg, type }); } });

  await searchStateFileList().setFileList.call(fakeThis, ['/a/no_number.mp4']);

  const keys = toasts.map((t) => t.msg);
  assert.ok(!keys.includes('search.error.path_inaccessible'), '無 inaccessible 不得誤出 path_inaccessible');
  assert.ok(keys.includes('search.toast.no_valid_files'), '全員無番號應正常顯示 no_valid_files');
});

test('D(3) mixed：inaccessible + 副檔名 → 通用 toast（涵蓋副檔名）與 path_inaccessible 皆出、有效檔仍建', async () => {
  window.t = (key) => key;
  window.SearchFile = {
    parseFilenames: async (fs) => fs.map((f) => ({ filename: f, number: 'ABC-123', has_subtitle: false })),
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
  // 一個有效檔 + 一個副檔名被濾 + 一個 inaccessible
  stubFilterFiles({
    success: true,
    files: [{ path: '/a/ABC-123.mp4', has_nfo: false }],
    rejected: { extension: 1, size: 0, not_found: 0, inaccessible: 1 },
    total_rejected: 2,
  });

  const toasts = [];
  const fakeThis = makeFakeThis({
    showToast(msg, type) { toasts.push({ msg, type }); },
    switchToFile: async () => {},
  });

  await searchStateFileList().setFileList.call(fakeThis, ['/a/ABC-123.mp4', '/a/note.txt', '/mnt/z/lan/x.mp4']);

  const keys = toasts.map((t) => t.msg);
  assert.equal(fakeThis.fileList.length, 1, 'mixed：有效檔仍建入 fileList');
  // 通用 toast 的 msg 會把細項附在後面（filtered_count（副檔名 1）），故用 startsWith
  assert.ok(keys.some((k) => k.startsWith('search.filelist.filtered_count')), 'mixed：通用 toast 應出（涵蓋副檔名等非-inaccessible 桶）');
  assert.ok(keys.includes('search.error.path_inaccessible'), 'mixed：path_inaccessible 亦應出');
});
