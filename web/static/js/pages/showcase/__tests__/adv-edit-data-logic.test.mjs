import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { readFileSync } from 'node:fs';

register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);

const {
    ADV_EDIT_DATA_FIELDS,
    validateDate,
    tagRemovable,
    isComposingEnter,
    tagDraftNew,
    tagDraftRemove,
    tagDraftAdd,
    tagDraftView,
    tagDraftPayload,
    validateNfoTagInput,
} = await import('../adv-edit-data-logic.js');

function field(key) {
    return ADV_EDIT_DATA_FIELDS.find((f) => f.key === key);
}

test('test_field_table_validation_and_values', () => {
    assert.equal(ADV_EDIT_DATA_FIELDS.map((f) => f.key).join(','), 'title,original_title,actresses,maker,series,release_date,plot,plot_translation');
    assert.equal(ADV_EDIT_DATA_FIELDS.filter((f) => f.required).map((f) => f.key).join(','), 'title');
    const dateCases = [
        ['2024-02-30', 'invalid_date'],
        ['2024-13-01', 'invalid_date'],
        ['24-1-1', 'invalid_date'],
        ['2024-02-29', null],
        ['', null],
        ['   ', null],
    ];
    for (const [raw, expected] of dateCases) {
        assert.equal(validateDate(raw), expected);
        assert.equal(field('release_date').validate(raw), expected);
    }
    assert.equal(field('title').validate('   '), 'title_empty');
    assert.equal(field('title').validate('A'), null);
    assert.deepEqual(field('actresses').toValue('A、B,C，D'), ['A', 'B', 'C', 'D']);
    assert.equal(field('title').toValue('  A  '), 'A');
    assert.equal(field('release_date').toValue(' 2024-01-02 '), '2024-01-02');
    assert.equal(field('actresses').read({ actresses: ['A', 'B'] }), 'A、B');
    assert.equal(field('title').read(null), '');
    assert.equal(field('title').read({}), '');
    assert.equal(field('title').read({ title: null }), '');
    assert.equal(field('title').read({ title: 'A' }), 'A');
    assert.equal(isComposingEnter({ isComposing: true }), true);
    assert.equal(isComposingEnter({}), false);
    assert.equal(isComposingEnter(null), false);
});

test('test_field_table_i18n_keys_exist', () => {
    const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url), 'utf8'));
    const data = locale.showcase.adv_edit.data;
    const prefix = 'showcase.adv_edit.data.';
    for (const f of ADV_EDIT_DATA_FIELDS) {
        assert.ok(f.labelKey, `${f.key}: missing labelKey`);
        for (const key of [f.labelKey, f.placeholderKey].filter(Boolean)) {
            assert.ok(key.startsWith(prefix), `${f.key}: invalid key ${key}`);
            assert.ok(Object.hasOwn(data, key.slice(prefix.length)), `${f.key}: missing translation ${key}`);
        }
    }
    for (const key of ['actresses', 'release_date']) assert.ok(field(key).placeholderKey, `${key}: missing placeholderKey`);
});

function draftDisjoint(draft) {
    return draft.added.every((t) => !draft.removed.includes(t));
}

// Every tagDraft* call must return a fresh draft object with fresh arrays and must
// leave its inputs untouched (FE-ALPINE-20). An in-place push that returns the same
// object would leave the rendered view stale after the user clicks remove.
function assertFreshDraft(name, draft, base, call) {
    const draftSnap = structuredClone(draft);
    const baseSnap = structuredClone(base);
    const out = call(draft, base);
    assert.deepEqual(draft, draftSnap, `${name}: input draft mutated`);
    assert.deepEqual(base, baseSnap, `${name}: input base mutated`);
    assert.notEqual(out, draft, `${name}: returned the input draft object`);
    assert.notEqual(out.added, draft.added, `${name}: added array not fresh`);
    assert.notEqual(out.removed, draft.removed, `${name}: removed array not fresh`);
    return out;
}

test('test_tag_draft_rules', () => {
    const base = ['A', { text: 'B', from_filename: true }, 'C'];
    const texts = (view) => view.map((x) => x.text);
    const empty = () => tagDraftNew('tags');
    assert.deepEqual(empty(), { kind: 'tags', added: [], removed: [] });

    const draftCases = [
        ['remove base tag into removed', { kind: 'tags', added: [], removed: [] }, (d, b) => tagDraftRemove(d, b, 'A'), { kind: 'tags', added: [], removed: ['A'] }],
        ['remove pending add from added', { kind: 'tags', added: ['D'], removed: [] }, (d, b) => tagDraftRemove(d, b, 'D'), { kind: 'tags', added: [], removed: [] }],
        ['add undoes a removal', { kind: 'tags', added: [], removed: ['A'] }, (d, b) => tagDraftAdd(d, b, 'A'), { kind: 'tags', added: [], removed: [] }],
        ['add new tag into added', { kind: 'tags', added: [], removed: ['A'] }, (d, b) => tagDraftAdd(d, b, 'D'), { kind: 'tags', added: ['D'], removed: ['A'] }],
    ];
    for (const [name, draft, call, expected] of draftCases) {
        const out = assertFreshDraft(name, draft, base, call);
        assert.deepEqual(out, expected, name);
        assert.equal(draftDisjoint(out), true, `${name}: added and removed overlap`);
    }

    const pending = assertFreshDraft('add pending tag', empty(), base, (d, b) => tagDraftAdd(d, b, 'D'));
    assert.deepEqual(pending, { kind: 'tags', added: ['D'], removed: [] });
    const dropped = assertFreshDraft('remove pending tag', pending, base, (d, b) => tagDraftRemove(d, b, 'D'));
    assert.deepEqual(dropped, { kind: 'tags', added: [], removed: [] });
    assert.equal(tagDraftPayload(dropped), null);

    // Refused operations (filename tag, duplicate, blank) still hand back a fresh object.
    const afterFile = assertFreshDraft('remove filename tag refused', empty(), base, (d, b) => tagDraftRemove(d, b, 'B'));
    assert.deepEqual(afterFile, empty());
    const afterDup = assertFreshDraft('add existing tag refused', empty(), base, (d, b) => tagDraftAdd(d, b, 'C'));
    assert.deepEqual(afterDup, empty());
    const afterBlank = assertFreshDraft('remove blank tag refused', empty(), base, (d, b) => tagDraftRemove(d, b, '  '));
    assert.deepEqual(afterBlank, empty());

    let chain = tagDraftNew('tags');
    chain = tagDraftRemove(chain, base, 'A');
    assert.equal(draftDisjoint(chain), true, 'remove A: added and removed overlap');
    chain = tagDraftAdd(chain, base, 'D');
    assert.equal(draftDisjoint(chain), true, 'add D: added and removed overlap');
    chain = tagDraftRemove(chain, base, 'D');
    assert.equal(draftDisjoint(chain), true, 'remove D: added and removed overlap');
    assert.deepEqual(tagDraftPayload(chain), { add: [], remove: ['A'] });
    assert.deepEqual(texts(tagDraftView(base, chain)), ['B', 'C']);

    let undone = tagDraftNew('tags');
    undone = tagDraftRemove(undone, base, 'A');
    undone = tagDraftAdd(undone, base, 'A');
    assert.equal(tagDraftPayload(undone), null);
    assert.deepEqual(texts(tagDraftView(base, undone)), ['A', 'B', 'C']);

    const viewDraft = { kind: 'tags', added: ['D'], removed: ['A'] };
    const viewBaseSnap = structuredClone(base);
    const viewDraftSnap = structuredClone(viewDraft);
    const view = tagDraftView(base, viewDraft);
    assert.deepEqual(base, viewBaseSnap, 'tagDraftView: base mutated');
    assert.deepEqual(viewDraft, viewDraftSnap, 'tagDraftView: draft mutated');
    assert.notEqual(view, viewDraft.added, 'tagDraftView: returned draft.added array');
    assert.notEqual(view, viewDraft.removed, 'tagDraftView: returned draft.removed array');
    assert.deepEqual(texts(view), ['B', 'C', 'D']);

    const payloadDraft = structuredClone(viewDraft);
    const payloadSnap = structuredClone(payloadDraft);
    const payload = tagDraftPayload(payloadDraft);
    assert.deepEqual(payloadDraft, payloadSnap, 'tagDraftPayload: draft mutated');
    assert.deepEqual(payload, { add: ['D'], remove: ['A'] });
    assert.notEqual(payload, payloadDraft, 'tagDraftPayload: returned the input draft');
    assert.notEqual(payload.add, payloadDraft.added, 'tagDraftPayload: add array not fresh');
    assert.notEqual(payload.remove, payloadDraft.removed, 'tagDraftPayload: remove array not fresh');

    assert.equal(tagRemovable({ text: 'B', from_filename: true }), false);
    assert.equal(tagRemovable({ text: 'A', from_filename: false }), true);
    assert.equal(validateNfoTagInput('a,b'), 'tag_invalid');
    assert.equal(validateNfoTagInput('  '), 'empty');
    assert.equal(validateNfoTagInput('ok'), null);
});
