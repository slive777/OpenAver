// sync-actress-fields.test.mjs — 100b-T4 DoD③（邏輯半層）：syncActressFields 四欄部分
// 寫入邏輯的回歸鎖。
//
// state-lightbox.js 用 `@/showcase/state-base.js` 等 browser-only importmap alias
// （base.html:696 的 `<script type="importmap">`，只有瀏覽器認得），plain Node 的 ESM
// resolver 無法直接 import 該檔——同一限制已記在 shared/mask-geometry.js 開頭
// （100b-T2a 先例）。承重欄位寫入邏輯已抽至 shared/actress-sync.js（純函式、只用相對
// import，零外部依賴），本檔直接 import 該檔測試；state-lightbox.js 的
// `_syncActressesArray(name, data)` 只是薄委派層，呼叫契約（by-name 寫
// paginatedActresses[idx]）不變，三個呼叫點（confirmMask／_uploadActressPhoto／
// _onPickerSelect）皆維持既有寫法。
//
// ⚠️ 本測試只鎖得住「陣列那一半」（node:test 能測的純資料邏輯）——鎖不住「
// currentLightboxActress 有沒有跟上」，那一半的正確性依賴呼叫端（confirmMask 等）有沒有
// 記得同時處理兩邊，`_fetchLiveAliases` 的 Object.assign 讓兩者不保證同一物件，只有
// CDP 對 alias-200 與 alias-404 各驗一位才驗得出來（plan-100b.md DoD③ 重寫段；
// gotchas-frontend.md §8c：「非同步 resolve 後寫回 state」那幾行不在任何人的 diff 裡）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { syncActressFields } = await import('../../../shared/actress-sync.js');

test('syncActressFields〔四欄皆傳，upload/pick 回應形狀〕四欄全部落地到 paginatedActresses[idx]', () => {
  const paginatedActresses = [
    { name: 'A', photo_url: 'old', photo_source: 'cloud', auto_focal: '0.3,0.5', crop_mode: 'manual' },
  ];
  syncActressFields(paginatedActresses, 'A', {
    photo_url: 'new', photo_source: 'upload', auto_focal: '', crop_mode: 'auto',
  });
  assert.deepEqual(paginatedActresses[0], {
    name: 'A', photo_url: 'new', photo_source: 'upload', auto_focal: '', crop_mode: 'auto', avatar_url: '',
  });
});

test('syncActressFields〔confirmMask 回應形狀，只傳 auto_focal/crop_mode〕未傳欄位不可被覆蓋成 undefined', () => {
  const paginatedActresses = [
    { name: 'A', photo_url: 'unchanged', photo_source: 'cloud', auto_focal: '0.2,0.5', crop_mode: 'auto' },
  ];
  syncActressFields(paginatedActresses, 'A', { auto_focal: '0.4,0.6', crop_mode: 'manual' });
  assert.equal(paginatedActresses[0].photo_url, 'unchanged');
  assert.equal(paginatedActresses[0].photo_source, 'cloud');
  assert.equal(paginatedActresses[0].auto_focal, '0.4,0.6');
  assert.equal(paginatedActresses[0].crop_mode, 'manual');
});


test('syncActressFields〔by-name 定位，非 index 0〕在多筆陣列中找對 entry，不動其他人的資料', () => {
  const paginatedActresses = [
    { name: 'X', photo_url: 'x-orig' },
    { name: 'A', photo_url: 'a-orig' },
    { name: 'Y', photo_url: 'y-orig' },
  ];
  syncActressFields(paginatedActresses, 'A', { photo_url: 'a-new' });
  assert.equal(paginatedActresses[0].photo_url, 'x-orig');
  assert.equal(paginatedActresses[1].photo_url, 'a-new');
  assert.equal(paginatedActresses[2].photo_url, 'y-orig');
});

test('syncActressFields〔換照片〕舊特寫被清掉、只動焦點的不清，影片頭像表改吃新原圖', async () => {
  const { actorFavsOf } = await import('../lbx-logic.js');
  const { buildActressIndex } = await import('../../../shared/actress-lookup.js');
  const arr = [
    { name: 'A', photo_url: '/old', avatar_url: '/face-crop/A?v=1' },
    { name: 'B', photo_url: '/b', avatar_url: '/face-crop/B?v=1', auto_focal: '0.5,0.5', crop_mode: 'auto' },
  ];
  const index = buildActressIndex(arr, {});
  const video = { actresses: 'A,B' };
  assert.equal(actorFavsOf(video, index).A.photo_url, '/face-crop/A?v=1');
  assert.equal(actorFavsOf(video, index).B.photo_url, '/face-crop/B?v=1');
  syncActressFields(arr, 'A', { photo_url: '/new' });
  syncActressFields(arr, 'B', { auto_focal: '0.4,0.6', crop_mode: 'manual' });
  assert.equal(arr[0].avatar_url, '');
  assert.equal(arr[1].avatar_url, '/face-crop/B?v=1');
  const out = actorFavsOf(video, index);
  assert.equal(out.A.photo_url, '/new');
  assert.equal(out.B.photo_url, '/face-crop/B?v=1');
});
