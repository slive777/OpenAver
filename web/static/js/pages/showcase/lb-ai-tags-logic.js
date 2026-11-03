/**
 * lb-ai-tags-logic.js — lightbox AI tags pure helpers (188c-T11)
 *
 * aiTagsProviderName / aiTagsFailureToast / aiTagsSuccessToasts
 * relative import only (FE-GUARD-11); pure helpers only (no browser globals / network).
 */

const PROVIDER_NAMES = {
    ollama: 'Ollama',
    gemini: 'Gemini',
    claude: 'Claude',
    openai: 'OpenAI-compatible',
    openai_official: 'OpenAI',
};

/** @param {string} provider */
export function aiTagsProviderName(provider) {
    if (Object.prototype.hasOwnProperty.call(PROVIDER_NAMES, provider)) {
        return PROVIDER_NAMES[provider];
    }
    return provider;
}

/**
 * @param {string} reason
 * @param {string} [detail]
 * @param {string} [provider]
 * @returns {{ key: string, params: object }}
 */
export function aiTagsFailureToast(reason, detail, provider) {
    const name = aiTagsProviderName(provider || '');
    if (reason === 'unreachable' && detail === 'rate_limited') {
        return { key: 'showcase.lightbox.ai_tags_rate_limited', params: { provider: name } };
    }
    if (reason === 'unreachable') {
        return { key: 'showcase.lightbox.ai_tags_unreachable', params: { provider: name } };
    }
    if (reason === 'model_unsupported') {
        return { key: 'showcase.lightbox.ai_tags_model_unsupported', params: {} };
    }
    if (reason === 'bad_response') {
        return { key: 'showcase.lightbox.ai_tags_bad_response', params: {} };
    }
    if (reason === 'not_configured' || reason === 'disabled') {
        return { key: 'showcase.lightbox.ai_tags_not_configured', params: {} };
    }
    return { key: 'showcase.lightbox.ai_tags_failed', params: {} };
}

/**
 * @param {{ refused?: boolean, added?: unknown, readonly_no_output?: boolean, nfo_write_blocked?: boolean }} data
 * @returns {Array<{ key: string, params: object, type: string }>}
 */
export function aiTagsSuccessToasts(data) {
    // Order: NFO flags → refused → added non-empty → none (flags win; single toast slot)
    if (data.readonly_no_output === true) {
        return [{ key: 'showcase.lightbox.tag_nfo_not_written', params: {}, type: 'info' }];
    }
    if (data.nfo_write_blocked === true) {
        return [{ key: 'showcase.lightbox.tag_nfo_write_blocked', params: {}, type: 'info' }];
    }
    if (data.refused === true) {
        return [{ key: 'showcase.lightbox.ai_tags_refused', params: {}, type: 'info' }];
    }
    const added = Array.isArray(data.added) ? data.added : [];
    if (added.length > 0) {
        return [{ key: 'showcase.lightbox.ai_tags_added', params: { n: added.length }, type: 'success' }];
    }
    return [{ key: 'showcase.lightbox.ai_tags_none', params: {}, type: 'info' }];
}
