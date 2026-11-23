// TASK-206a-T5: secret field two-state machine (wire truth table + no plaintext after save)

import { test } from 'node:test';
import assert from 'node:assert/strict';

const {
  createSecretField,
  startReplace,
  requestClear,
  wireValue,
  afterSave,
} = await import('../secret-field-logic.js');

const SERVER_MASK = 'MASKED-FROM-SERVER';
const maskFn = (s) => 'M<' + [...s].length + '>';

test('wire_value_truth_table', () => {
  const configured = createSecretField(SERVER_MASK);
  assert.equal(wireValue(configured), SERVER_MASK);
  const replacingBlank = { ...startReplace(configured), input: '   \n ' };
  assert.equal(wireValue(replacingBlank), SERVER_MASK);
  const replacingTyped = { ...startReplace(configured), input: '  new-key\n' };
  assert.equal(wireValue(replacingTyped), 'new-key');
  const clearedAfterTyping = requestClear(replacingTyped);
  assert.equal(wireValue(clearedAfterTyping), '');
  assert.equal(clearedAfterTyping.input, '');
  const regretted = startReplace(clearedAfterTyping);
  assert.equal(wireValue(regretted), SERVER_MASK);
  const unsetEmpty = createSecretField('');
  assert.equal(wireValue(unsetEmpty), '');
  const unsetTyped = { ...createSecretField(''), input: ' typed ' };
  assert.equal(wireValue(unsetTyped), 'typed');
});

test('after_save_leaves_no_plaintext', () => {
  const secret = 'sk-test-PLAINTEXT-1234567890';
  const sources = [
    { ...createSecretField(''), input: '  ' + secret + '\n' },
    { ...startReplace(createSecretField(SERVER_MASK)), input: '  ' + secret + '\n' },
  ];
  for (const src of sources) {
    const out = afterSave(src, maskFn);
    const hits = [];
    const walk = (v) => {
      if (typeof v === 'string') {
        if (v.includes(secret)) hits.push(v);
        return;
      }
      if (v && typeof v === 'object') {
        for (const k of Object.keys(v)) {
          if (k.includes(secret)) hits.push(k);
          walk(v[k]);
        }
      }
    };
    walk(out);
    assert.deepEqual(hits, []);
    assert.equal(out.state, 'configured');
    assert.equal(out.mask, maskFn(secret));
    assert.equal(out.input, '');
  }
});
