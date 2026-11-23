// TASK-206a-T2: maskSecret parity with Python mask_secret (shared vectors, BE-TEST-14)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const { maskSecret } = await import('../secret-mask.js');

const vectors = JSON.parse(readFileSync(
  new URL('../../../../../tests/data/secret_mask_vectors.json', import.meta.url), 'utf8')).vectors;

test('mask_secret_vectors_parity', () => {
  assert.ok(vectors.length >= 12);
  for (const v of vectors) {
    assert.strictEqual(maskSecret(v.input), v.expected, JSON.stringify(v.input));
  }
});
