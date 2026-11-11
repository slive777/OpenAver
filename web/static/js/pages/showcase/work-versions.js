/**
 * work-versions.js — 牆上「一部作品多個版本」的純函式（198b-T6，CD-198b-8／9）
 *
 * 資料模型：_videos／_allVideos 每格 ＝ 一部作品的預設版本 dict；所有版本 dict 共用同一個不可列舉
 * `_versions` 陣列。缺 `_versions` 一律當單版本（假資料、女優 hero 卡、5 欄 snapshot 都走這條）。
 * 不得用番號自己分組——分組完全是後端 version_group 的事（spec-122 §4.1）。
 * 零 import、零 window、零 Alpine（FE-GUARD-11）；比對一律用 path，不比物件身分（FE-ALPINE-14）。
 */

// 回傳這部作品所有版本 dict（預設版本在 [0]）；缺 _versions 或為空 ＝ 單版本。
export function versionsOf(v) {
    if (!v) return [];
    const list = v._versions;
    return (Array.isArray(list) && list.length > 0) ? list : [v];
}

// 後端一部作品 ＝ 頂層預設版本 ＋ versions[]。回傳預設版本 dict，並讓所有版本共用同一個 _versions。
// versions 缺或 [] ＝ 單版本，回 item 自己。
export function normalizeWorkItem(item) {
    if (!item) return item;
    const multi = Array.isArray(item.versions) && item.versions.length > 0;
    const vers = multi ? item.versions : [item];
    if (multi) {
        vers.forEach((ver) => _defineVersions(ver, vers));
    }
    vers.forEach((ver) => {
        if (ver._imgLoaded === undefined) ver._imgLoaded = false;
        if (ver._coverRequested === undefined) ver._coverRequested = false;
    });
    return vers[0];
}

// path 比對：a 這部作品是否含有 b 這個版本。b 缺或沒有 path（5 欄 snapshot）→ false。
export function sameWork(a, b) {
    if (!a || !b || !b.path) return false;
    return versionsOf(a).some((x) => x.path === b.path);
}

// 篩選：predicate 非函式 ＝ 沒有任何篩選條件 → 預設版本；否則依 _versions 順序第一個符合者，都不符 → null。
export function pickDisplayVersion(w, predicate) {
    const list = versionsOf(w);
    if (typeof predicate !== 'function') return list[0] || null;
    return list.find((ver) => predicate(ver)) || null;
}

// 排序比較值來源：預設版本（唯一例外是加入時間，見 workMtime）。
export function sortSource(v) {
    return versionsOf(v)[0];
}

// 加入時間：整部作品所有版本裡最新的 mtime。
export function workMtime(v) {
    return versionsOf(v).reduce((m, x) => Math.max(m, x.mtime || 0), 0);
}

// 單筆刷新回應的版本集合與原作品的版本集合完全相同 → 'patch'；多／少／換 → 'reload'（整牆重載）。
export function refreshRoute(video, newItem) {
    const oldPaths = new Set(versionsOf(video).map((v) => v.path));
    const newPaths = _incomingOf(newItem).map((v) => v.path);
    return (newPaths.length === oldPaths.size && newPaths.every((p) => oldPaths.has(p))) ? 'patch' : 'reload';
}

// 整部作品替換：回應裡每個版本寫回原作品裡 path 相同的那個「原物件」（保留身分）。
// 每個原物件恰呼叫一次 write(原物件, patch)，呼叫前不改動它——由呼叫端決定經誰寫
// （已渲染的卡／燈箱要經 Proxy 寫才會重繪；raw 先寫、Proxy 再寫同值是 no-op，FE-ALPINE-20）。
// 回應有原作品沒有的 path → throw（呼叫端應先用 refreshRoute 分流）。
export function applyWorkUpdate(oldDict, newItem, write = Object.assign) {
    const olds = versionsOf(oldDict);
    const incoming = _incomingOf(newItem);
    const targets = incoming.map((nv) => {
        const hit = olds.find((o) => o.path === nv.path);
        if (!hit) throw new Error('applyWorkUpdate: path not in work: ' + nv.path);
        return hit;
    });
    const nextVersions = targets.slice();
    targets.forEach((t) => { if (!Object.prototype.hasOwnProperty.call(t, '_versions')) _defineVersions(t, [t]); });
    const byPath = {};
    incoming.forEach((nv, i) => {
        const target = targets[i];
        write(target, _patchOf(nv, nextVersions));
        byPath[nv.path] = target;
    });
    return { defaultDict: targets[0], byPath };
}

function _incomingOf(newItem) {
    if (!newItem) return [];
    return (Array.isArray(newItem.versions) && newItem.versions.length > 0) ? newItem.versions : [newItem];
}

// 不可列舉：任何版本 dict 事後 JSON.stringify 都不會因循環參照丟例外。
function _defineVersions(dict, list) {
    Object.defineProperty(dict, '_versions', { value: list, enumerable: false, writable: true, configurable: true });
}

function _patchOf(nv, nextVersions) {
    const patch = Object.assign({}, nv);
    delete patch.versions;
    if (nv.cover_url) patch._imgLoaded = false;
    patch._versions = nextVersions;
    return patch;
}

// 版本膠囊文字（198b-T7a，CD-198b-10）：與 versionsOf(v) 同序同長；單版本回 []。
// 每顆 ＝ 等級 ＋ 類型（類型取 kindName、依 version_kinds 陣列序；空 ＝ 原版）；
// 文字（補大小之前）出現 2 次以上的那幾顆才補 formatSize(size)。
export function versionCapsules(v, kindName, t, formatSize) {
    const vs = versionsOf(v);
    if (vs.length < 2) return [];
    const texts = vs.map((ver) => {
        const kinds = Array.isArray(ver.version_kinds) ? ver.version_kinds : [];
        const typeText = kinds.length ? kinds.map((id) => kindName(id)).join(' ') : t('showcase.lightbox.version_original');
        return ver.resolution_tier ? ver.resolution_tier + ' ' + typeText : typeText;
    });
    const dupCount = new Map();
    texts.forEach((text) => dupCount.set(text, (dupCount.get(text) || 0) + 1));
    return texts.map((text, i) => (dupCount.get(text) > 1 ? text + ' ' + formatSize(vs[i].size) : text));
}
