import { test } from 'node:test';
import assert from 'node:assert/strict';
import { aiTagsProviderName, aiTagsFailureToast } from '../lb-ai-tags-logic.js';

test('ai_tags_provider_name_hides_group_id', () => {
    assert.equal(aiTagsProviderName('openai:oc0123abcd'), 'OpenAI-compatible');
    assert.equal(aiTagsProviderName('openai'), 'OpenAI-compatible');
    assert.equal(aiTagsProviderName('gemini'), 'Gemini');
    assert.equal(aiTagsProviderName('other'), 'other');
    const result = aiTagsFailureToast('unreachable', '', 'openai:oc0123abcd');
    assert.equal(result.params.provider, 'OpenAI-compatible');
    assert.equal(JSON.stringify(result).includes('oc0123abcd'), false);
});
