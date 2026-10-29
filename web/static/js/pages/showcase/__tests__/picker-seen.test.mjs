// picker-seen.test.mjs — 185-T4：換照片「這次看過的候選」純邏輯回歸鎖。
// 接線（首開才清、重抓不清、stale 不記）Alpine runtime 測不到，由 T5 真機判定。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { addSeen, buildCandidatesUrl } = await import('../../../shared/picker-seen.js');

test('addSeen_dedupes_without_eviction', () => {
    const a = ['x'];
    const b = addSeen(a, 'y');
    assert.deepEqual(a, ['x']);
    assert.notEqual(b, a);
    assert.deepEqual(b, ['x', 'y']);
    assert.deepEqual(addSeen(b, 'x'), ['x', 'y']);
    assert.deepEqual(addSeen(b, ''), ['x', 'y']);
    assert.deepEqual(addSeen(b, undefined), ['x', 'y']);
    let list = [];
    for (let i = 0; i < 600; i++) list = addSeen(list, `id${i}`);
    assert.equal(list.length, 600);
    assert.equal(list[0], 'id0');
});

test('buildCandidatesUrl_branches_and_cap', () => {
    const n = '三上悠亞';
    const base = `/api/actresses/${encodeURIComponent(n)}/photo-candidates`;
    assert.equal(buildCandidatesUrl(n, 0, []), base);
    assert.equal(buildCandidatesUrl(n, 2, []), `${base}?attempt=2`);
    assert.equal(buildCandidatesUrl(n, 0, ['a', 'b']), `${base}?exclude=a,b`);
    assert.equal(buildCandidatesUrl(n, 3, ['a', 'b']), `${base}?attempt=3&exclude=a,b`);
    const seen = Array.from({ length: 501 }, (_, i) => `id${i}`);
    const expected = seen.slice(1).join(',');
    assert.equal(buildCandidatesUrl(n, 0, seen), `${base}?exclude=${expected}`);
    assert.equal(seen.length, 501);
});
