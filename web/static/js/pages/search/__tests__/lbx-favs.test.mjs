import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateLbxFavs } = await import('../state/lbx-favs.js');
const { toLbxVideo } = await import('../lbx-view-rules.js');
const realFetch = globalThis.fetch;
const actress = { name: '新名', photo_url: '/photo', birth: '2000-01-01' };
const groups = [{ primary_name: '新名', aliases: ['舊名'] }];
const response = (body, ok = true) => ({ ok, json: async () => body });
function setup() {
    const pending = [];
    globalThis.fetch = (url) => new Promise((resolve, reject) => pending.push({ url, resolve, reject }));
    const s = { ...searchStateLbxFavs(), video: toLbxVideo({ actors: ['舊名', '路人'], date: '2020-01-01' }, 'result'), lbxView() { return this.video; } };
    return { s, pending };
}
function settle(pending, offset, actresses = [actress]) {
    assert.deepEqual(pending.slice(offset, offset + 2).map((p) => p.url), ['/api/actresses', '/api/actress-aliases']);
    pending[offset].resolve(response({ success: true, actresses }));
    pending[offset + 1].resolve(response({ success: true, groups }));
}

test('test_lbx_favs_alias_hit_and_miss', async () => {
    const { s, pending } = setup();
    const load = s.lbxFavsLoad();
    assert.equal(pending.length, 2); settle(pending, 0); await load;
    assert.equal(s._lbActorFavs['舊名'].name, '新名'); assert.equal(s._lbActorAges['舊名'], 20);
    assert.equal('路人' in s._lbActorFavs, false); assert.equal(s.lbxActorEntity('舊名').name, '新名');
    assert.equal(s.lbxActorEntity('路人'), null); assert.equal(s.actressWorkCount(), null);
    s.video = toLbxVideo({ actors: ['路人'], date: '2020-01-01' }, 'result'); s._refreshLbActorAges();
    assert.deepEqual(s._lbActorFavs, {}); assert.deepEqual(s._lbActorAges, {});
    s.video = null; s._refreshLbActorAges(); assert.deepEqual(s._lbActorFavs, {}); assert.deepEqual(s._lbActorAges, {});
});

test('test_lbx_favs_load_lifecycle', async () => {
    const { s, pending } = setup();
    const first = s.lbxFavsLoad(); s.lbxFavsLoad(); assert.equal(pending.length, 2);
    settle(pending, 0); await first;
    const failed = s.lbxFavsReload(); assert.equal(pending.length, 4);
    pending[2].resolve(response({}, false)); pending[3].reject(new Error('offline')); await failed;
    assert.equal(s.lbxActorEntity('舊名').name, '新名'); assert.equal(s._lbActorFavs['舊名'].name, '新名');
    const older = s.lbxFavsReload(); const newer = s.lbxFavsReload(); assert.equal(pending.length, 8);
    settle(pending, 6); await newer; settle(pending, 4, []); await older;
    assert.equal(s.lbxActorEntity('舊名').name, '新名'); assert.equal(s._lbActorFavs['舊名'].name, '新名');
    const race = setup(); const oldLoad = race.s.lbxFavsLoad(); const failedReload = race.s.lbxFavsReload();
    assert.equal(race.pending.length, 4); race.pending[2].resolve(response({}, false)); race.pending[3].resolve(response({ groups })); await failedReload;
    settle(race.pending, 0); await oldLoad;
    assert.equal(race.s.lbxActorEntity('舊名')?.name, '新名'); assert.equal(race.s._lbActorFavs['舊名']?.name, '新名');
    const fresh = setup(); const failFirst = fresh.s.lbxFavsLoad(); assert.equal(fresh.pending.length, 2);
    fresh.pending[0].resolve(response({}, false)); fresh.pending[1].reject(new Error('offline')); await failFirst;
    assert.deepEqual(fresh.s._lbActorFavs, {}); assert.deepEqual(fresh.s._lbActorAges, {});
    assert.equal(fresh.s.lbxActorEntity('舊名'), null); fresh.s.lbxFavsLoad(); assert.equal(fresh.pending.length, 2);
});

after(() => { globalThis.fetch = realFetch; });
