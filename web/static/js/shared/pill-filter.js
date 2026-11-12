/**
 * pill-filter.js — metadata pill 正規化純函式（TASK-115-T1）
 *
 * 純函式模組，不是 Alpine state factory，不參與 main.js 的 mergeState() 合併鏈。
 * 因此不落入 plan T1「不得新增 state factory 模組」的禁令（該禁令針對會插進
 * mergeState 合併順序、可能撞 FE-ALPINE-05 覆蓋風險的模組）。
 *
 * T2 會把比對用的 predicate 加進同一個檔案。
 *
 * TASK-124a-T1：新增 release 維度的比對（expandPill/matchesReleasePill，
 * 委派給 release-window.js）＋ serializePills/deserializePills 的 op/value2 擴充。
 */

import { expandPill, matchesReleasePill, parseEndpoint } from './release-window.js';
import { tierRank } from './resolution-tier.js';

export function normalizePillValue(s) {
    if (s === null || s === undefined) return '';
    return String(s).trim().normalize('NFKC').toLowerCase();
}

/**
 * buildPillPredicate — TASK-115-T2：pill 精準比對層（純函式，D1/D2）
 *
 * 逐次呼叫（每次 applyFilterAndSort() 一次）precompute 一個 predicate，
 * 避免 per-video 重算 alias 展開（plan D2 效能理由）。
 *
 * @param {{dim: string, value: string}[]} pills
 * @param {Object} nameToGroup - state-base.js 的 _nameToGroup（女優 alias map）
 * @param {Object} tagToGroup - state-base.js 的 _tagToGroup（標籤 alias map）
 * @returns {(video: Object) => boolean}
 */
export function buildPillPredicate(pills, nameToGroup, tagToGroup) {
    if (!pills || pills.length === 0) {
        return function () { return true; };  // 空 pill 列表 = 不過濾任何影片（D2）
    }
    var matchers = pills.map(function (pill) {
        return _buildSingleMatcher(pill, nameToGroup, tagToGroup);
    });
    return function (video) {
        return matchers.every(function (m) { return m(video); });
    };
}

// dim token → video 欄位（spec §4.2 表，D3：whole-field 完全相等維度）
var WHOLE_FIELD_DIMS = { maker: 'maker', director: 'director', series: 'series', label: 'label' };

function _buildSingleMatcher(pill, nameToGroup, tagToGroup) {
    var dim = pill.dim;
    // TASK-123-T6：pick 是唯一不看 pill.value 的分支（不像下面幾支要 normalizePillValue
    // 或展開 alias set），放最前面避免下一個讀者以為它也走 WHOLE_FIELD_DIMS 的路徑。
    if (dim === 'pick') {
        return function (video) { return (video.user_rating || 0) > 0; };
    }
    // TASK-124a-T1：release 維度，展開＋比對皆委派給 release-window.js（純函式）。
    // fail-closed 沿用本檔既有風格（內嵌匿名函式，非模組級單例，與 57 行同型——
    // plan §2.2 擬碼的 `_never` 單例是 actress-pill-filter.js 獨有的寫法，見 T1 卡片
    // 「plan 與現況不符之處」，本檔預設不引入新單例）。
    if (dim === 'release') {
        var w = expandPill(pill);
        if (!w) return function () { return false; };
        return function (video) { return matchesReleasePill(video, w); };
    }
    // TASK-198a-T4：resolution 維度，依等級序比較（SD < HD < FHD < 2K < 4K < 8K）。
    // fail-closed：未知 op／未知 value／片的 resolution_tier 為 null／缺鍵／未知＝恆不符。
    if (dim === 'resolution') {
        var need = tierRank(pill.value);
        var op = pill.op;
        if (need < 0 || (op !== '=' && op !== '<=' && op !== '>=')) return function () { return false; };
        return function (video) {
            var have = tierRank(video.resolution_tier);
            if (have < 0) return false;
            if (op === '=') return have === need;
            return op === '<=' ? have <= need : have >= need;
        };
    }
    if (dim === 'actress' || dim === 'tag') {
        return _actressOrTagMatcher(dim, pill.value, nameToGroup, tagToGroup);
    }
    if (Object.prototype.hasOwnProperty.call(WHOLE_FIELD_DIMS, dim)) {
        var field = WHOLE_FIELD_DIMS[dim];
        var norm = normalizePillValue(pill.value);
        return function (video) { return normalizePillValue(video[field]) === norm; };
    }
    return function () { return false; };  // fail closed：未知維度不誤判為「全部符合」（D3）
}

// D4：正規化順序固定為「先 normalize 整欄，再 split」——全形逗號要先靠 NFKC 折成 ASCII 逗號才切得開。
export function _splitField(rawFieldValue) {
    return normalizePillValue(rawFieldValue).split(',').map(function (s) { return s.trim(); }).filter(Boolean);
}

/**
 * mergeTagTokens — TASK-121b-T1：tags（逗號字串）＋ user_tags（陣列）疊加。
 * concat 純疊加，不去重／不過濾／不交集。user_tags 非陣列視為空陣列，不拋例外。
 */
export function mergeTagTokens(video) {
    var fromTags = _splitField(video.tags);
    var fromUser = Array.isArray(video.user_tags)
        ? video.user_tags.map(function (t) { return normalizePillValue(t); }).filter(Boolean)
        : [];
    return fromTags.concat(fromUser);
}

// D5：alias 展開的雙 key 查表 + 值正規化。
export function _buildAliasSet(pillValue, groupMap) {
    var norm = normalizePillValue(pillValue);
    var set = new Set([norm]);  // pill 自身的正規化值恆在集合內（即使查無 alias group）
    var candidateKeys = [norm, String(pillValue).trim().toLowerCase()];
    for (var i = 0; i < candidateKeys.length; i++) {
        // Opus review：`groupMap` 是普通物件字面（state-base.js:64/92），帶著 Object.prototype。
        // 裸的 `groupMap[key]` 對 'tostring'／'constructor'／'valueof' 這類 key 會取到繼承來的
        // 函式（truthy），下一行 `.forEach` 就 TypeError，而這個例外會從 applyFilterAndSort
        // 一路往上炸掉整次篩選 → 封面牆空白。用 hasOwnProperty + Array.isArray 雙重把關。
        var group = Object.prototype.hasOwnProperty.call(groupMap || {}, candidateKeys[i])
            ? groupMap[candidateKeys[i]]
            : null;
        if (Array.isArray(group)) {
            group.forEach(function (member) { set.add(normalizePillValue(member)); });
            break;
        }
    }
    return set;
}

function _actressOrTagMatcher(dim, pillValue, nameToGroup, tagToGroup) {
    var groupMap = dim === 'actress' ? nameToGroup : tagToGroup;
    var valueSet = _buildAliasSet(pillValue, groupMap);
    return function (video) {
        var tokens = dim === 'tag' ? mergeTagTokens(video) : _splitField(video.actresses);
        return tokens.some(function (t) { return valueSet.has(t); });
    };
}

/**
 * serializePills / deserializePills — TASK-115-T3：pill 持久化深拷貝與容錯
 *
 * serializePills：切斷陣列與元素參照（CD-3），供 saveState 寫入 _persistedShowcase。
 * deserializePills：fail-safe 形狀檢查，舊格式（鍵不存在）與畸形元素皆不 throw。
 * 不做去重／正規化——那是 addPill 的職責。
 *
 * ⚠ 已知且刻意的不對稱：`deserializePills` 會 trim `dim`/`value`，而 `addPill`（T1）
 * 存的是點擊當下的原始字面（spec §4.1 第 4 條：pill 顯示點擊當下的字面值）。因此若某個
 * metadata 值真的帶著前後空白，reload 前後顯示的字面會差那幾個空白。**不要為了「對稱」
 * 把這裡的 trim 拿掉**——比對與去重都走 `normalizePillValue()`（自己就 trim），所以
 * 篩選結果與去重 key 在 reload 前後恆等；拿掉 trim 只會讓「全空白的 value」有機會存活成
 * 一枚看不見的 pill。空白字面的顯示差異是可接受的殘留，空白 pill 不是。
 *
 * TASK-124a-T1：release pill 額外帶 op/value2 兩鍵（非 release pill 逐鍵逐值不變，
 * 恰 dim/value 兩鍵，CD-124a-11 + AC16）。deserializePills 對 release pill 額外做
 * 四條形狀 fail-safe（見下方函式內註解），畸形一枚丟一枚，不連坐相鄰元素。
 */
export function serializePills(pills) {
    if (!Array.isArray(pills)) return [];
    return pills.map(function (p) {
        var out = { dim: p.dim, value: p.value };
        if (p.dim === 'release' || p.dim === 'resolution') {
            if (p.op !== undefined) out.op = p.op;
        }
        if (p.dim === 'release') {
            if (p.value2 !== undefined) out.value2 = p.value2;
        }
        return out;
    });
}

export function deserializePills(raw) {
    if (!Array.isArray(raw)) return [];
    var out = [];
    for (var i = 0; i < raw.length; i++) {
        var p = raw[i];
        if (!p || typeof p !== 'object') continue;
        var dim = typeof p.dim === 'string' ? p.dim.trim() : '';
        var value = typeof p.value === 'string' ? p.value.trim() : '';
        if (!dim || !value) continue;
        if (dim === 'release') {
            // CD-124a-11 四條形狀 fail-safe，任一條不過就整枚丟棄：
            var op = p.op;
            if (op !== '=' && op !== '<=' && op !== '>=' && op !== 'range') continue;      // ① op 白名單
            if (parseEndpoint(value) === null) continue;                                   // ③ value 形狀
            var value2 = typeof p.value2 === 'string' ? p.value2.trim() : '';
            if (op === 'range') {
                if (!value2) continue;                                                      // ② range 缺 value2
                if (parseEndpoint(value2) === null) continue;                               // ④ value2 形狀
            }
            var releasePill = { dim: dim, value: value, op: op };
            if (op === 'range') releasePill.value2 = value2;
            out.push(releasePill);
            continue;
        }
        if (dim === 'resolution') {
            // TASK-198a-T4：op ∈ =／<=／>=（無 range）且 value ∈ RESOLUTION_TIERS，畸形一枚丟一枚。
            if (p.op !== '=' && p.op !== '<=' && p.op !== '>=') continue;
            if (tierRank(value) < 0) continue;
            out.push({ dim: dim, value: value, op: p.op });
            continue;
        }
        out.push({ dim: dim, value: value });
    }
    return out;
}
