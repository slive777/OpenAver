// TASK-207b-T0：pop 分片工廠選項（預設＝Showcase 今天／注入後讀注入值），單檔裸 node。
globalThis.window = globalThis;

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { stateLightboxPop } = await import('../state-lightbox-pop.js');

test('test_pop_factory_options_wiring', () => {
    const video = { actresses: '丙, 丁', number: 'N-1', maker: 'M' };
    const other = { actresses: '壬', director: 'D' };
    const base = { _lbActorFavs: {}, _isReleaseClickable: () => false };
    const def = { ...stateLightboxPop(), ...base, currentLightboxVideo: video };
    assert.deepEqual(def.lbxActressList.call(def), ['丙', '丁']);
    assert.equal(def.lbxInfoField.call(def, 'number').id, 'number');
    assert.equal(def.lbxInfoField.call(def, 'director'), undefined);
    const inj = { ...stateLightboxPop({ getVideo: () => other }), ...base, currentLightboxVideo: video };
    assert.deepEqual(inj.lbxActressList.call(inj), ['壬']);
    assert.equal(inj.lbxInfoField.call(inj, 'director').id, 'director');
    assert.equal(inj.lbxInfoField.call(inj, 'number'), undefined);
    const searches = [];
    const dTap = { ...stateLightboxPop(), searchFromMetadata: (...a) => searches.push(a) };
    dTap.lbxActorAvatarTap.call(dTap, { detail: 1, pointerType: 'mouse', currentTarget: {} }, '丑');
    assert.deepEqual(searches, [['丑', 'actress']]);
    const got = [], searches2 = [];
    const iTap = { ...stateLightboxPop({ avatarClick: (s, n) => got.push([s, n]) }), searchFromMetadata: (...a) => searches2.push(a) };
    iTap.lbxActorAvatarTap.call(iTap, { detail: 1, pointerType: 'mouse', currentTarget: {} }, '丑');
    assert.equal(searches2.length, 0);
    assert.deepEqual([got.length, got[0][0] === iTap, got[0][1]], [1, true, '丑']);
    const meta = { scrollTop: 99 };
    const dTop = { ...stateLightboxPop(), $refs: { lbxMeta: meta } };
    dTop.lbxMetaToTop.call(dTop);
    assert.equal(meta.scrollTop, 0);
    const myMeta = { scrollTop: 99 }, staleMeta = { scrollTop: 7 };
    const iTop = { ...stateLightboxPop({ metaRef: () => 'myMeta' }), $refs: { myMeta, lbxMeta: staleMeta } };
    iTop.lbxMetaToTop.call(iTop);
    assert.deepEqual([myMeta.scrollTop, staleMeta.scrollTop], [0, 7]);
    const target = { closest: () => null };
    const dPanel = { contains: () => false };
    const dDown = { ...stateLightboxPop(), lbxPop: { kind: 'info', mode: 'click', anchorKey: 'x', placed: false, style: {} }, $refs: { lbxPopHost: { querySelector: () => dPanel } } };
    dDown.lbxPopOnPointerDown.call(dDown, { target });
    assert.equal(dDown.lbxPop, null);
    const iPanel = { contains: () => false };
    const trapPanel = { contains: (t) => t === target };
    const iDown = { ...stateLightboxPop({ hostRef: () => 'myHost' }), lbxPop: { kind: 'info', mode: 'click', anchorKey: 'x', placed: false, style: {} }, $refs: { myHost: { querySelector: () => iPanel }, lbxPopHost: { querySelector: () => trapPanel } } };
    iDown.lbxPopOnPointerDown.call(iDown, { target });
    assert.equal(iDown.lbxPop, null);
});
