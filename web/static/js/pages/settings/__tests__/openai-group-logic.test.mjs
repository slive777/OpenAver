// TASK-206b-T4: multiple OpenAI-compatible group rules (name gates, delete fallback, id vectors, add/trash gates)

import { test } from 'node:test';
import assert from 'node:assert/strict';

const {
  MAX_CUSTOM_GROUPS,
  NAME_MAX_LENGTH,
  openaiGroupIdOf,
  newGroupId,
  validateGroupName,
  canAdd,
  showAdd,
  showTrash,
  labelFor,
  fallbackAfterDelete,
  deleteConfirmParts,
  newGroupDraft,
} = await import('../openai-group-logic.js');

const A30 = 'a'.repeat(30);
const A31 = 'a'.repeat(31);

test('group_name_rules', () => {
  assert.equal(MAX_CUSTOM_GROUPS, 5);
  assert.equal(NAME_MAX_LENGTH, 30);
  const rows = [
    ['', [], [], { ok: false, reason: 'empty' }],
    ['  \t ', [], [], { ok: false, reason: 'empty' }],
    [A31, [], [], { ok: false, reason: 'too_long' }],
    [A30, [], [], { ok: true, name: A30 }],
    [' ' + A30 + ' ', [], [], { ok: true, name: A30 }],
    ['default', [], ['Default'], { ok: false, reason: 'reserved' }],
    ['  DEFAULT ', [], ['Default'], { ok: false, reason: 'reserved' }],
    ['openrouter', ['OpenRouter'], [], { ok: false, reason: 'duplicate' }],
    [' OpenRouter ', ['OpenRouter'], [], { ok: false, reason: 'duplicate' }],
    ['  Mine  ', [], [], { ok: true, name: 'Mine' }],
  ];
  for (const [input, existing, reserved, expected] of rows) {
    assert.deepEqual(validateGroupName(input, existing, reserved), expected);
  }
});

test('delete_fallback_never_dangles', () => {
  const deleted = 'oc0123abcd';
  const fallbackRows = [
    ['openai:oc0123abcd', 'openai'],
    ['openai:oc89abcdef', 'openai:oc89abcdef'],
    ['ollama', 'ollama'],
    ['', ''],
    ['openai', 'openai'],
  ];
  for (const [provider, expected] of fallbackRows) {
    assert.equal(fallbackAfterDelete(provider, deleted), expected);
  }
  const confirmRows = [
    ['openai:oc0123abcd', 'openai:oc0123abcd', 'settings.ai.openai_group.delete_confirm_also_used'],
    ['openai:oc0123abcd', 'openai', null],
    ['openai:oc0123abcd', '', null],
    ['openai', 'openai:oc0123abcd', null],
    ['openai:oc0123abcd', 'openai:oc89abcdef', null],
  ];
  for (const [tp, gp, expectedNote] of confirmRows) {
    const out = deleteConfirmParts('oc0123abcd', tp, gp);
    assert.equal(out.bodyKey, 'settings.ai.openai_group.delete_confirm');
    assert.equal(out.noteKey, expectedNote);
  }
});

test('group_id_vectors', () => {
  const rows = [
    ['openai', null],
    ['ollama', null],
    ['', null],
    ['openai:oc0123abcd', 'oc0123abcd'],
    ['openai:', null],
    ['openai:OC0123ABCD', null],
    ['openai:oc0123abc', null],
    ['openai:oc0123abcde', null],
    ['openai:oc0123abcd\n', null],
    ['openai:oc0123.bcd', null],
    ['openai:oc0123abcd:x', null],
  ];
  for (const [input, expected] of rows) {
    assert.equal(openaiGroupIdOf(input), expected);
  }
  assert.equal(openaiGroupIdOf(null), null);
  assert.equal(openaiGroupIdOf(123), null);
  assert.equal(newGroupId(() => 0), 'oc00000000');
  assert.equal(newGroupId(() => 0xffffffff), 'ocffffffff');
  assert.equal(newGroupId(() => 0x0a1b2c3d), 'oc0a1b2c3d');
  const fresh = newGroupId();
  assert.equal(openaiGroupIdOf('openai:' + fresh), fresh);
});

test('add_trash_gates_and_blank_draft', () => {
  assert.equal(canAdd('http://x', 0), true);
  assert.equal(canAdd('', 0), false);
  assert.equal(canAdd('   ', 0), false);
  assert.equal(canAdd('http://x', 5), false);
  assert.equal(canAdd('http://x', 4), true);
  const addRows = [
    ['openai', '', 0, false],
    ['openai', '   ', 0, false],
    ['openai', 'http://x', 5, false],
    ['ollama', 'http://x', 0, false],
    ['gemini', 'http://x', 0, false],
    ['claude', 'http://x', 0, false],
    ['openai_official', 'http://x', 0, false],
    ['', 'http://x', 0, false],
    ['openai', 'http://x', 0, true],
    ['openai:oc0123abcd', 'http://x', 4, true],
  ];
  for (const [provider, baseUrl, count, expected] of addRows) {
    assert.equal(showAdd(provider, baseUrl, count), expected);
  }
  assert.equal(showTrash('openai:oc0123abcd'), true);
  assert.equal(showTrash('openai'), false);
  assert.equal(showTrash('ollama'), false);
  assert.equal(showTrash(''), false);
  assert.equal(showTrash('openai:oc0123abc'), false);
  const a = newGroupDraft();
  const b = newGroupDraft();
  assert.notEqual(a, b);
  assert.deepEqual(a, { baseUrl: '', model: '', useCustomModel: false });
  assert.deepEqual(b, { baseUrl: '', model: '', useCustomModel: false });
  assert.deepEqual(labelFor(null, []), { key: 'settings.translate.openai_compatible', params: {} });
  const groups = [{ id: 'oc0123abcd', name: 'Mine' }];
  assert.deepEqual(labelFor(null, groups), { key: 'settings.ai.openai_group.label_default', params: {} });
  assert.deepEqual(labelFor('', groups), { key: 'settings.ai.openai_group.label_default', params: {} });
  assert.deepEqual(labelFor('oc0123abcd', groups), { key: 'settings.ai.openai_group.label_named', params: { name: 'Mine' } });
  assert.deepEqual(labelFor('oc89abcdef', groups), { key: 'settings.ai.openai_group.label_default', params: {} });
});
