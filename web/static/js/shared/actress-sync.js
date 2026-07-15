/**
 * actress-sync.js — syncActressFields：純函式、女優 photo/focal 四欄 by-name 部分寫入邏輯
 * （100b-T4，抽取自 state-lightbox.js 的 `_syncActressesArray`）。
 *
 * 抽出理由（可測試性）：`state-lightbox.js` 頂層 `import ... from '@/showcase/state-base.js'`
 * 用的是 browser-only importmap alias（`base.html:696` 的 `<script type="importmap">`），
 * plain Node 的 ESM resolver 不認得，故該檔任何 export 都無法被 node:test 直接 import——
 * 同一限制已記在 `mask-geometry.js` 開頭（100b-T2a 先例）。本檔只用無 alias 的相對 import
 * （其實本函式零依賴），`state-lightbox.js` 的 `_syncActressesArray(name, data)` 保留既有
 * 呼叫契約（三個呼叫點 `this._syncActressesArray(capturedName, data)` 不變），內部委派本函式。
 *
 * 四欄擴充（100b-T4，plan-100b CD-10）：原本只寫 `photo_url`/`photo_source` 兩欄，未帶
 * `auto_focal`/`crop_mode`。`confirmMask()` 只送 `{auto_focal, crop_mode}`（不含 photo_url）
 * ⇒ 逐欄 `'key' in data` 判斷、不整包 `Object.assign(target, data)`——避免「沒傳的欄位」被
 * 覆蓋成 `undefined`（同 gotchas-frontend G5「`??`/`||` 吞合法值」的精神變體：這裡不是 falsy
 * 陷阱，而是「沒傳」≠「傳了空值」，不可用無條件整包覆蓋）。
 */

/**
 * @param {Array<{name: string}>} paginatedActresses 承重陣列（reactive，state-actress.js:17/272）
 * @param {string} name by-name 定位（await 前捕獲值，不可用當下 currentLightboxActress，防中途切走寫錯人）
 * @param {{photo_url?: string, photo_source?: string, auto_focal?: string, crop_mode?: string}|null|undefined} data
 */
export function syncActressFields(paginatedActresses, name, data) {
    if (!data) return;
    const idx = paginatedActresses.findIndex((a) => a.name === name);
    if (idx < 0) return;   // 女優已從陣列移除（篩選/刪除）→ 靜默 return，無牆格可更新
    const target = paginatedActresses[idx];
    if ('photo_url' in data) target.photo_url = data.photo_url;
    if ('photo_source' in data) target.photo_source = data.photo_source;
    if ('auto_focal' in data) target.auto_focal = data.auto_focal;
    if ('crop_mode' in data) target.crop_mode = data.crop_mode;
}
