/**
 * actress-lookup.js — 收藏女優查找與作品計數純函式（TASK-199b-T4b，CD-199b-4／6）
 *
 * 純函式模組：零 Alpine、零 window。
 * 唯一目的是讓「女優卡片／燈箱／資訊區上的片數」和「牆上只下她這一個女優 pill 的『共 N 部』」
 * 永遠用同一把尺——切欄與正規化只有 pill-filter.js 那一份（_splitField／normalizePillValue／_buildAliasSet），
 * 這裡不自己切字串（static_guard_lint 的 lookup-no-split 守著）。
 *
 * 不變式 I-1：對任一收藏女優 a 與任一片，「lookup(片上名字) === a」⇔「牆上只下 pill a.name 時這部片出現」
 * （同一 token 多位收藏時先到的贏，只影響 lookup，不影響各自的計數）。
 *
 * 作品＝牆上一格（多版本共用 _versions）；任一版本命中即整部算一次，同一部寫了她的兩個名字也只算一次。
 */

import { normalizePillValue, _splitField, _buildAliasSet } from './pill-filter.js';
import { versionsOf } from '../pages/showcase/work-versions.js';

/**
 * @param {Object[]} actresses - 收藏女優陣列（每筆至少有 name）
 * @param {Object} nameToGroup - state-base.js 的 _nameToGroup
 * @returns {{actresses: Object[], lookup: (rawName: string) => (Object|null), valueSetOf: (actress: Object) => Set<string>}}
 */
export function buildActressIndex(actresses, nameToGroup) {
    const list = Array.isArray(actresses) ? actresses.slice() : [];
    const valueSets = new Map();    // 收藏女優名 → Set<正規化 token>（本名＋別名組）
    const byToken = new Map();      // 正規化 token → 收藏女優（先到的贏）
    for (const a of list) {
        const set = _buildAliasSet(a.name, nameToGroup);
        valueSets.set(a.name, set);
        for (const tok of set) {
            if (tok && !byToken.has(tok)) byToken.set(tok, a);
        }
    }
    return {
        actresses: list,
        lookup(rawName) {
            const key = normalizePillValue(rawName);
            return key ? (byToken.get(key) || null) : null;
        },
        valueSetOf(actress) {
            return (actress && valueSets.get(actress.name)) || new Set();
        },
    };
}

/**
 * 一次掃 works，回 Map<收藏女優名, 作品數>。index 裡每一位收藏女優都有 key（0 部者值 0）。
 * @param {Object[]} works - 牆上的作品陣列（_videos，可見子集）
 */
export function countWorksByActress(works, index) {
    // 正規化 token → 含有該 token 的作品序號集合（逐版本切欄，任一版本命中即整部算）
    const byToken = new Map();
    const list = works || [];
    for (let w = 0; w < list.length; w++) {
        const vers = versionsOf(list[w]);
        for (let v = 0; v < vers.length; v++) {
            const toks = _splitField(vers[v].actresses);
            for (let t = 0; t < toks.length; t++) {
                let hits = byToken.get(toks[t]);
                if (!hits) { hits = new Set(); byToken.set(toks[t], hits); }
                hits.add(w);
            }
        }
    }
    const out = new Map();
    for (const a of index.actresses) {
        const union = new Set();
        for (const tok of index.valueSetOf(a)) {
            const hit = byToken.get(tok);
            if (hit) for (const i of hit) union.add(i);
        }
        out.set(a.name, union.size);
    }
    return out;
}

/**
 * 命中該收藏女優的作品陣列（保持 works 原順序）。與 countWorksByActress 同口徑。
 */
export function worksOfActress(works, index, actress) {
    const valueSet = index.valueSetOf(actress);
    return (works || []).filter((w) => versionsOf(w).some(
        (ver) => _splitField(ver.actresses).some((tok) => valueSet.has(tok)),
    ));
}
