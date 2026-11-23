import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.t = (key) => key;
const root = pathToFileURL(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../') + '/').href;
const loader = `
const root = ${JSON.stringify(root)};
export async function resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('@/settings/')) return nextResolve(root + 'pages/settings/' + specifier.slice(11), context);
    if (specifier.startsWith('@/')) return nextResolve(root + specifier.slice(2), context);
    return nextResolve(specifier, context);
}`;
register(`data:text/javascript,${encodeURIComponent(loader)}`, import.meta.url);
const { stateConfig } = await import('../state-config.js');
const { stateSecrets } = await import('../state-secrets.js');
const { mergeState } = await import('@/shared/merge-state.js');

function minimalConfig() {
    return {
        search: {}, translate: { enabled: false, provider: 'ollama', ollama: {}, gemini: {}, openai: {} },
        scraper: { create_folder: true, folder_layers: ['{num}'], filename_format: '{num}', nfo_title_format: '{num}',
            video_extensions: ['.mp4'], suffix_keywords: [], external_manager: 'off', strm_path_mappings: {} },
        gallery: { cover_badges: { enabled: false, items: {} } }, showcase: {}, general: { theme: 'light' },
        ai_services: {}, metatube: {}, sources: [],
    };
}
function setup(config = minimalConfig(), success = true) {
    const state = mergeState(stateConfig(), stateSecrets());
    state._loadFormatVariables = async () => {};
    state._loadCoverBadgeRules = async () => {};
    state._loadVideoCount = () => {};
    state.hydrateMetatubeStatus = async () => {};
    state.showToast = () => {};
    state.theme = 'light';
    state._configLoading = false;
    state.savedState = JSON.parse(JSON.stringify(state.form));
    let body;
    globalThis.fetch = async (_url, options) => {
        if (options?.method === 'PUT') { body = JSON.parse(options.body); return { json: async () => ({ success }) }; }
        return { json: async () => ({ success: true, data: structuredClone(config) }) };
    };
    return { state, body: () => body };
}
function configured() {
    const config = minimalConfig();
    config.translate.gemini.api_key = 'aaaa••••1111';
    config.translate.openai.api_key = 'bbbb••••2222';
    config.translate.openai_official = { api_key: 'cccc••••3333' };
    config.translate.claude = { api_key: 'dddd••••4444' };
    config.ai_services = { image_similar: { api_key: 'eeee••••5555' }, faces: { api_key: 'ffff••••6666' } };
    config.metatube.token = 'gggg••••7777';
    return config;
}
function contains(value, needle, visited = new Set()) {
    if (typeof value === 'string') return value.includes(needle);
    if (!value || typeof value !== 'object' || visited.has(value)) return false;
    visited.add(value);
    return Object.entries(value).some(([key, child]) => key.includes(needle) || contains(child, needle, visited));
}

test('secrets_load_marks_configured_vs_unset', async () => {
    const { state } = setup(configured());
    await state.loadConfig();
    for (const [id, expected] of Object.entries({ gemini: 'aaaa••••1111', openai: 'bbbb••••2222',
        openaiOfficial: 'cccc••••3333', claude: 'dddd••••4444', aiSimilar: 'eeee••••5555',
        aiFaces: 'ffff••••6666', metatube: 'gggg••••7777' })) {
        assert.equal(state.secretFields[id].state, 'configured');
        assert.equal(state.secretWire(id), expected);
    }
    const config = minimalConfig();
    config.translate.gemini.api_key = 42;
    config.translate.openai.api_key = '';
    const empty = setup(config).state;
    await empty.loadConfig();
    for (const field of Object.values(empty.secretFields)) assert.equal(field.state, 'unset');
});

test('save_payload_routes_each_field_wire', async () => {
    const fixture = setup(configured());
    await fixture.state.loadConfig();
    fixture.state.secretReplace('openai');
    fixture.state.secretFields.openai.input = '  sk-ant-api03-test1234567890abcd\n';
    fixture.state.secretClear('claude');
    await fixture.state._saveServerConfig();
    const body = fixture.body();
    assert.equal(body.translate.gemini.api_key, 'aaaa••••1111');
    assert.equal(body.translate.openai.api_key, 'sk-ant-api03-test1234567890abcd');
    assert.equal(body.translate.openai_official.api_key, 'cccc••••3333');
    assert.equal(body.translate.claude.api_key, '');
    assert.equal(body.ai_services.image_similar.api_key, 'eeee••••5555');
    assert.equal(body.ai_services.faces.api_key, 'ffff••••6666');
    assert.equal(body.metatube.token, 'gggg••••7777');
    assert.equal(body.translate.provider, 'ollama');
});

test('save_success_clears_plaintext_failure_keeps_it', async () => {
    const key = 'sk-ant-api03-test1234567890abcd';
    const failed = setup(configured(), false);
    await failed.state.loadConfig();
    failed.state.secretReplace('openai');
    failed.state.secretFields.openai.input = key;
    await failed.state._saveServerConfig();
    assert.equal(failed.state.secretFields.openai.state, 'replacing');
    assert.equal(failed.state.secretFields.openai.input, key);
    assert.equal(failed.state.secretsDirty, true);
    const saved = setup(configured());
    await saved.state.loadConfig();
    saved.state.secretReplace('openai');
    saved.state.secretFields.openai.input = key;
    await saved.state._saveServerConfig();
    assert.equal(saved.state.secretFields.openai.state, 'configured');
    assert.equal(saved.state.secretFields.openai.mask, 'sk-a••••abcd');
    assert.equal(saved.state.secretFields.openai.input, '');
    assert.equal(contains(saved.state, key), false);
    assert.equal(saved.state.isDirty, false);
});

test('dirty_covers_input_replace_and_clear', async () => {
    const config = configured();
    delete config.translate.gemini.api_key;
    const { state } = setup(config);
    await state.loadConfig();
    assert.equal(state.isDirty, false);
    state.secretFields.gemini.input = 'invented-value-123456789';
    assert.equal(state.isDirty, true);
    state.secretFields.gemini.input = '';
    state.secretReplace('openai');
    assert.equal(state.isDirty, false);
    state.secretFields.openai.input = '   ';
    assert.equal(state.isDirty, false);
    state.secretFields.openai.input = 'another-value-123456789';
    assert.equal(state.isDirty, true);
    state.secretClear('openai');
    assert.equal(state.isDirty, true);
});
