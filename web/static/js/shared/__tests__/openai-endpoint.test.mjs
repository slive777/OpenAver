// TASK-206b-T1: openaiEndpointPreview parity with Python (shared vectors, BE-TEST-14)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const { normalizeOpenaiBaseUrl, openaiEndpointPreview } = await import('../openai-endpoint.js');

const vectors = JSON.parse(readFileSync(
  new URL('../../../../../tests/data/openai_base_url_vectors.json', import.meta.url), 'utf8')).vectors;

test('openai_endpoint_vectors_parity', () => {
  assert.ok(vectors.length >= 16);
  for (const v of vectors) {
    assert.strictEqual(normalizeOpenaiBaseUrl(v.input), v.normalized, JSON.stringify(v.input));
    assert.strictEqual(openaiEndpointPreview(v.input), v.preview, JSON.stringify(v.input));
  }
});
