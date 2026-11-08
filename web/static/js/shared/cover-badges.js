/**
 * cover-badges.js — 封面屬性 badge 命中計算（TASK-121c-T3）
 *
 * 純函式，零 window / Alpine / DOM。讀 config 與寫 video._badges 是
 * state-base.js glue 函式的事。
 */

import { mergeTagTokens, _buildAliasSet } from './pill-filter.js';

/**
 * @param {Array|*} manifest
 * @param {{enabled?: boolean, items?: Object}|null|undefined} coverBadgesCfg
 * @returns {string[]}
 */
export function resolveEnabledIds(manifest, coverBadgesCfg) {
    if (!coverBadgesCfg || coverBadgesCfg.enabled !== true) return [];
    if (!Array.isArray(manifest)) return [];
    var items = coverBadgesCfg.items;
    var out = [];
    for (var i = 0; i < manifest.length; i++) {
        var rule = manifest[i];
        if (!rule) continue;
        // FE-JS-01：缺 id / undefined / true 皆視為開啟；只有 === false 才關
        if (items && items[rule.id] === false) continue;
        out.push(rule.id);
    }
    return out;
}

/**
 * 收集 matched 規則宣告的 supersedes id 集合。
 * supersedes 缺鍵或非陣列視為 []（FE-JS-01）。
 * @param {Array} rules
 * @returns {Set}
 */
function _supersededIds(rules) {
    var ids = new Set();
    for (var i = 0; i < rules.length; i++) {
        var sup = Array.isArray(rules[i].supersedes) ? rules[i].supersedes : [];
        for (var k = 0; k < sup.length; k++) {
            ids.add(sup[k]);
        }
    }
    return ids;
}

/**
 * @param {Object|null|undefined} video
 * @param {Array|*} manifest
 * @param {Object} tagToGroup
 * @param {string[]|*} enabledIds
 * @returns {{id: *, display_name: *}[]}
 */
export function computeBadges(video, manifest, tagToGroup, enabledIds) {
    if (video == null) return [];
    if (!Array.isArray(manifest) || manifest.length === 0) return [];
    if (!Array.isArray(enabledIds)) return [];
    var tokens = mergeTagTokens(video);
    var enabled = new Set(enabledIds);
    var matched = [];
    for (var i = 0; i < manifest.length; i++) {
        var rule = manifest[i];
        if (!rule) continue;
        if (!enabled.has(rule.id)) continue;
        var values = [rule.canonical_tag].concat(rule.match_aliases || []);
        var aliasSet = new Set();
        for (var j = 0; j < values.length; j++) {
            _buildAliasSet(values[j], tagToGroup).forEach(function (t) {
                aliasSet.add(t);
            });
        }
        if (tokens.some(function (t) { return aliasSet.has(t); })) {
            matched.push(rule);
        }
    }
    var superseded = _supersededIds(matched);
    matched = matched.filter(function (r) { return !superseded.has(r.id); });
    matched.sort(function (a, b) { return a.display_order - b.display_order; });
    return matched.slice(0, 3).map(function (r) {
        return { id: r.id, display_name: r.display_name };
    });
}
