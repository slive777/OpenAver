// TASK-198b-T6: work-versions.js 純函式（一部作品多版本：篩選挑版本、排序、刷新分流與整部替換）。
// 直接相對 import，零 window。fixture 一律經 normalizeWorkItem 產生（餵後端形狀）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
    normalizeWorkItem, versionsOf, pickDisplayVersion, sortSource, workMtime, refreshRoute, applyWorkUpdate,
} from '../work-versions.js';

const ver = (path, o) => ({ path, title: 'T-' + path, mtime: 0, resolution_tier: 'FHD', cover_url: '/c?p=' + path, ...o });
// 後端形狀：頂層 ＝ 預設版本 ＋ versions[]（各版本是獨立 dict）
const work = (list) => normalizeWorkItem({ ...list[0], versions: list.map((v) => ({ ...v })) });
const paths = (w) => versionsOf(w).map((v) => v.path);

test('pickDisplayVersion: 任一版本符合就挑那一版（非預設也行）、沒條件取預設、單版本不變', () => {
    const W = work([ver('A-C.mkv'), ver('A.mp4', { resolution_tier: '4K', _imgLoaded: true }), ver('A-LTX.mkv')]);
    const [a, b, c] = versionsOf(W);
    assert.equal(W, a);
    assert.deepEqual(paths(W), ['A-C.mkv', 'A.mp4', 'A-LTX.mkv']);
    // 共用同一個 _versions、不可列舉（JSON.stringify 不會因循環丟例外）、已有的初值不被覆蓋
    assert.ok(versionsOf(b) === versionsOf(a) && versionsOf(c) === versionsOf(a));
    assert.ok(![a, b, c].some((v) => Object.keys(v).includes('_versions')));
    assert.doesNotThrow(() => JSON.stringify([a, b, c]));
    assert.deepEqual([a._imgLoaded, b._imgLoaded, c._coverRequested], [false, true, false]);

    assert.ok(pickDisplayVersion(W, (v) => v.resolution_tier === '4K') === b);
    assert.ok(pickDisplayVersion(W, (v) => v.path.includes('LTX')) === c);
    assert.ok(pickDisplayVersion(W, null) === a);
    assert.equal(pickDisplayVersion(W, (v) => v.resolution_tier === '8K'), null);

    // 單版本：versions: []、缺 versions、從沒 normalize 的純物件（現有 wiring 測試的假資料）
    const plain = ver('S.mp4');
    const singles = [normalizeWorkItem({ ...ver('S1.mp4'), versions: [] }), normalizeWorkItem(ver('S2.mp4')), plain];
    for (const s of singles) {
        assert.ok(versionsOf(s).length === 1 && versionsOf(s)[0] === s);
        assert.ok(pickDisplayVersion(s, null) === s && pickDisplayVersion(s, () => true) === s);
        assert.equal(pickDisplayVersion(s, () => false), null);
        assert.ok(sortSource(s) === s);
    }
});

test('workMtime: 加入時間取各版本最新、其餘排序鍵取預設版本、單版本與今天相同', () => {
    // 最新 mtime 在索引 2；預設（索引 0）比索引 1 還舊 → 只取預設、或取 [1] 的實作都過不了
    const W = work([ver('A-C.mkv', { mtime: 100, title: 'default' }), ver('A.mp4', { mtime: 200 }), ver('A-LTX.mkv', { mtime: 900 })]);
    const S = work([ver('S.mp4', { mtime: 500 })]);
    assert.equal(workMtime(W), 900);
    assert.equal(sortSource(W).title, 'default');
    assert.ok(sortSource(W) === versionsOf(W)[0]);
    assert.deepEqual([S, W].sort((x, y) => workMtime(y) - workMtime(x)).map((v) => v.path), ['A-C.mkv', 'S.mp4']);
    assert.deepEqual([workMtime({ mtime: 50 }), workMtime({}), workMtime(S)], [50, 0, 500]);
});

test('applyWorkUpdate + refreshRoute: 同一部作品每個版本整批換新、離開作品時整牆重載', () => {
    const mk = () => work([ver('A-C.mkv'), ver('A.mp4'), ver('A-LTX.mkv')]);
    const W = mk();
    const olds = versionsOf(W).slice();
    const reply = (order, o) => ({
        ...ver(order[0], o), versions: order.map((p) => ver(p, { title: 'NEW-' + p, cover_url: '/c?p=' + p + '&t=1', ...o })),
    });

    // 路由：集合相同（含順序不同）→ patch；多／少／換／重刮改番號離開 → reload；單版本回應取頂層 path
    assert.equal(refreshRoute(W, reply(['A-LTX.mkv', 'A-C.mkv', 'A.mp4'])), 'patch');
    assert.equal(refreshRoute(W, reply(['A-C.mkv', 'A.mp4', 'A-LTX.mkv', 'D.mkv'])), 'reload');
    assert.equal(refreshRoute(W, reply(['A-C.mkv', 'A.mp4'])), 'reload');
    assert.equal(refreshRoute(W, reply(['A-C.mkv', 'A.mp4', 'D.mkv'])), 'reload');
    assert.equal(refreshRoute(W, reply(['A-LTX.mkv'])), 'reload');
    assert.equal(refreshRoute(W, { path: 'A-LTX.mkv', versions: [] }), 'reload');
    assert.equal(refreshRoute(ver('S.mp4'), { path: 'S.mp4', versions: [] }), 'patch');

    // 整部替換：write 對每個原物件恰一次、呼叫當下原物件還是舊值（Proxy 寫入才會觸發重繪）
    const seen = [];
    const write = (target, patch) => { seen.push([target.path, target.title, patch.title]); Object.assign(target, patch); };
    const { defaultDict, byPath } = applyWorkUpdate(W, reply(['A-LTX.mkv', 'A-C.mkv', 'A.mp4']), write);
    assert.deepEqual(seen.map((s) => s[0]).sort(), ['A-C.mkv', 'A-LTX.mkv', 'A.mp4']);
    assert.ok(seen.every(([p, oldTitle, newTitle]) => oldTitle === 'T-' + p && newTitle === 'NEW-' + p));
    assert.ok(olds.every((o) => byPath[o.path] === o));                  // 身分保留
    assert.ok(olds.every((o) => o.title === 'NEW-' + o.path && o._imgLoaded === false));
    assert.ok(defaultDict === olds[2] && versionsOf(olds[0])[0] === olds[2]);   // 預設版本換成回應第一個
    assert.ok(olds.every((o) => versionsOf(o) === versionsOf(olds[0]) && !Object.keys(o).includes('_versions')));
    assert.doesNotThrow(() => JSON.stringify(olds));

    // 預設 write（Object.assign）、單版本且原本沒有 _versions；回應有不屬於這部作品的 path → throw
    const plain = ver('S.mp4', { _imgLoaded: true });
    applyWorkUpdate(plain, { path: 'S.mp4', title: 'N', cover_url: '/c?p=S&t=1', versions: [] });
    assert.deepEqual([plain.title, plain._imgLoaded, Object.keys(plain).includes('_versions')], ['N', false, false]);
    assert.doesNotThrow(() => JSON.stringify(plain));
    const calls = [];
    assert.throws(() => applyWorkUpdate(mk(), reply(['A-C.mkv', 'D.mkv']), (t) => calls.push(t)));
    assert.equal(calls.length, 0);
});
