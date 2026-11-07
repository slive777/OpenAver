/**
 * hidden-sources.js — 「隱藏未連線硬碟」純函式（195b-T4）
 *
 * 無 DOM／Alpine／`@/` 別名，node:test 零 loader 可測。
 * `sources[i]` 與離線成員做字串全等：兩邊的 key 都是後端同一個 `uri_to_fs_path`，
 * 這裡不重寫任何路徑正規化。
 */

/**
 * @param {string[]} sources  最近一次 /api/showcase/videos 回的 sources（索引即 video.src）
 * @param {string[]} offlineMembers  /api/showcase/source-status 中 reason==='unreachable' 各項 members 合併
 * @returns {Set<number>}
 */
export function computeHiddenIndexes(sources, offlineMembers) {
    var out = new Set();
    if (!Array.isArray(sources) || !Array.isArray(offlineMembers) || offlineMembers.length === 0) return out;
    var offline = new Set(offlineMembers);
    for (var i = 0; i < sources.length; i++) {
        if (offline.has(sources[i])) out.add(i);
    }
    return out;
}

/**
 * splitVisible 與燈箱收斂共用的單一判斷式。
 * `src` 缺欄位或非整數 ＝ 可見（fail-open）；`src === 0` 是合法索引，不得用 truthy 判斷（FE-JS-01）。
 */
export function isHiddenVideo(v, hiddenIdx) {
    return v != null && Number.isInteger(v.src) && hiddenIdx.has(v.src);
}

/** 保序切成可見／被藏；元素維持同一物件 ref。 */
export function splitVisible(all, hiddenIdx) {
    var visible = [];
    var hidden = [];
    var list = all || [];
    for (var i = 0; i < list.length; i++) {
        if (isHiddenVideo(list[i], hiddenIdx)) hidden.push(list[i]);
        else visible.push(list[i]);
    }
    return { visible: visible, hidden: hidden };
}

/** 被藏片的大寫番號集合（空番號略過），供相似結果濾除。 */
export function hiddenNumberSet(hiddenVideos) {
    var out = new Set();
    var list = hiddenVideos || [];
    for (var i = 0; i < list.length; i++) {
        var n = list[i] && list[i].number;
        if (n) out.add(String(n).toUpperCase());
    }
    return out;
}
