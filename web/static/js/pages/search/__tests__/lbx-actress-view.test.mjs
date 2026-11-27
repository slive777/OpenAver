import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateBase } = await import('../state/base.js');
const { searchStateLbxView } = await import('../state/lbx-view.js');

test('test_lbx_actress_chips_and_core_parts', () => {
    globalThis.window = { t: k => k };
    const s = { ...searchStateBase(), ...searchStateLbxView(), actressProfile: { aliases: ['A'], tags: ['T'], age: 36, birth: '2000', height: '163cm', cup: 'F', bust: 88 }, _actressChipsExpanded: { aliases: false, info: true } };
    assert.deepEqual(s._actressLbChips(), [{ kind: 'alias', text: 'A' }, { kind: 'info', text: 'T' }]);
    assert.deepEqual(s._actressCoreMetadataParts(), [
        { key: 'age', text: '36search.unit.age', clickable: false }, { key: 'birth', text: '2000', clickable: false },
        { key: 'height', text: '163cm', clickable: false }, { key: 'cup', text: 'Fsearch.unit.cup', clickable: false },
        { key: 'bwh', text: '88', clickable: false },
    ]);
    assert.equal(s._actressChipsIsExpanded(), true);
    s._actressChipsExpanded.info = false;
    assert.equal(s._actressChipsIsExpanded(), false);
    s.actressProfile = null;
    assert.deepEqual(s._actressLbChips(), []);
    assert.deepEqual(s._actressCoreMetadataParts(), []);
});
