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

/**
 * Footer 來源提示兩段句型（純函式；t 由呼叫端注入；每個 key 寫字面）。
 * @returns {{ offline: {text, title, button}|null, permission: {text, title}|null }}
 */
export function footerNotice(sources, hideOn, hiddenCount, t) {
    if (!Array.isArray(sources)) return { offline: null, permission: null };

    var offlineGroups = sources.filter(function (it) { return it && it.reason === 'unreachable'; });
    var permissionGroups = sources.filter(function (it) { return it && it.reason === 'no_permission'; });

    var offline = null;
    var n = offlineGroups.length;
    if (n > 0) {
        var list = offlineGroups.map(function (g) { return g.display; }).join('、');
        var text;
        var title;
        if (n <= 2) {
            text = t('showcase.status.source_offline_list', { list: list });
            title = '';
        } else {
            text = t('showcase.status.source_offline_count', { n: n });
            title = list;
        }
        var hiddenText = hideOn === true ? t('showcase.status.source_offline_hidden', { n: (hiddenCount ?? 0).toLocaleString() }) : '';
        text = text + hiddenText;
        var button;
        if (hideOn === true) {
            button = t('showcase.status.source_show_btn');
        } else {
            button = t('showcase.status.source_hide_btn');
        }
        offline = { text: text, title: title, button: button };
    }

    var permission = null;
    var pn = permissionGroups.length;
    if (pn > 0) {
        var plist = permissionGroups.map(function (g) { return g.display; }).join('、');
        var hintItem = permissionGroups.find(function (g) { return g && g.dsm_hint; });
        var hint = hintItem && hintItem.dsm_hint ? ' ' + hintItem.dsm_hint : '';
        var ptext;
        var ptitle;
        if (pn <= 2) {
            ptext = t('showcase.status.source_no_permission_list', { list: plist }) + hint;
            ptitle = '';
        } else {
            ptext = t('showcase.status.source_no_permission_count', { n: pn }) + hint;
            ptitle = plist;
        }
        permission = { text: ptext, title: ptitle };
    }

    return { offline: offline, permission: permission };
}
