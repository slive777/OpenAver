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
const { stateProviders } = await import('../state-providers.js');
const { aiTagsPanel } = await import('../ai-tags-panel.js');
const { aiSimilarPanel } = await import('../ai-similar-panel.js');
const { aiFacesPanel } = await import('../ai-faces-panel.js');

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

test('buttons_send_wire_not_legacy_field', async () => {
    const realFetch = globalThis.fetch;
    const rows = [
        ['testGeminiConnection', 'gemini', '/api/gemini/test', 'aaaa••••1111', false],
        ['testGeminiTranslation', 'gemini', '/api/gemini/test-translate', 'aaaa••••1111', false],
        ['fetchOpenAIModels', 'openai', '/api/openai/models', 'bbbb••••2222', true],
        ['testOpenAITranslation', 'openai', '/api/openai/test', 'bbbb••••2222', true],
        ['fetchClaudeModels', 'claude', '/api/claude/models', 'dddd••••4444', false],
        ['testClaudeTranslation', 'claude', '/api/claude/test', 'dddd••••4444', false],
        ['fetchOpenAIOfficialModels', 'openaiOfficial', '/api/openai/official/models', 'cccc••••3333', false],
        ['testOpenAIOfficialTranslation', 'openaiOfficial', '/api/openai/official/test', 'cccc••••3333', false],
        ['gemini', 'gemini', '/api/ai/tags/test', 'aaaa••••1111', true],
        ['claude', 'claude', '/api/ai/tags/test', 'dddd••••4444', true],
        ['openai_official', 'openaiOfficial', '/api/ai/tags/test', 'cccc••••3333', true],
        ['openai', 'openai', '/api/ai/tags/test', 'bbbb••••2222', true],
        ['similar', 'aiSimilar', '/api/ai/similar/test', 'eeee••••5555', true],
        ['faces', 'aiFaces', '/api/ai/faces/test', 'ffff••••6666', true],
    ];
    try {
        for (const [entry, id, url, mask, nullable] of rows) {
            for (const mode of ['configured', 'new', 'clear']) {
                const root = mergeState(stateConfig(), stateProviders(), stateSecrets());
                root.secretsLoad(configured());
                Object.assign(root.form, { geminiApiKey: 'STALE-LEGACY-gemini-123456', claudeApiKey: 'STALE-LEGACY-claude-123456',
                    openaiApiKey: 'STALE-LEGACY-openai-123456', openaiOfficialApiKey: 'STALE-LEGACY-official-123456',
                    aiSimilarApiKey: 'STALE-LEGACY-similar-123456', aiFacesApiKey: 'STALE-LEGACY-faces-123456',
                    geminiModel: 'model', claudeModel: 'model', openaiModel: 'model', openaiOfficialModel: 'model',
                    openaiBaseUrl: 'http://example.invalid', aiSimilarUrl: 'http://example.invalid', aiFacesUrl: 'http://example.invalid',
                    aiTagsProvider: entry, aiTagsModel: 'model' });
                root.showToast = () => {};
                if (mode === 'new') { root.secretReplace(id); root.secretFields[id].input = '  sk-ant-api03-test1234567890abcd\n'; }
                if (mode === 'clear') root.secretClear(id);
                const calls = [];
                globalThis.fetch = async (target, opts) => {
                    if (target === url) calls.push(JSON.parse(opts.body));
                    return { ok: false, json: async () => ({ success: false }) };
                };
                if (entry in root) await root[entry]();
                else {
                    const panel = entry === 'similar' ? aiSimilarPanel() : entry === 'faces' ? aiFacesPanel() : aiTagsPanel();
                    Object.assign(panel, { form: root.form, showToast: () => {}, secretWire: (key) => root.secretWire(key) });
                    await panel.runTest();
                }
                const label = `${entry} ${mode}`;
                if (mode === 'clear' && !nullable) assert.ok(calls.length === 0, label);
                else {
                    assert.ok(calls.length === 1, label);
                    const expected = mode === 'configured' ? mask : mode === 'new' ? 'sk-ant-api03-test1234567890abcd' : '';
                    assert.ok(Object.hasOwn(calls[0], 'api_key') && calls[0].api_key === expected, label);
                    assert.ok(!contains(calls[0], 'STALE-LEGACY-'), label);
                }
            }
        }
    } finally { globalThis.fetch = realFetch; }
});

test('fetch_models_gate_follows_secret_state', async () => {
    const realFetch = globalThis.fetch;
    try {
        for (const [provider, id, field, url] of [
            ['gemini', 'gemini', 'geminiApiKey', '/api/gemini/test'],
            ['claude', 'claude', 'claudeApiKey', '/api/claude/models'],
            ['openai_official', 'openaiOfficial', 'openaiOfficialApiKey', '/api/openai/official/models'],
        ]) {
            for (const configuredState of [true, false]) {
                const root = mergeState(stateConfig(), stateProviders(), stateSecrets());
                root.secretsLoad(configuredState ? configured() : minimalConfig());
                root.form[field] = configuredState ? '' : 'STALE-LEGACY-gate-123456';
                let count = 0;
                globalThis.fetch = async (target) => { if (target === url) count++; return { ok: false, json: async () => ({ success: false }) }; };
                await root.ensureProviderModels(provider);
                assert.ok(count === (configuredState ? 1 : 0), `${id} ${configuredState}`);
            }
        }
    } finally { globalThis.fetch = realFetch; }
});

test('metatube_connect_sends_wire_token', async () => {
    const realFetch = globalThis.fetch;
    try {
        for (const mode of ['configured', 'new', 'clear']) {
            const root = mergeState(stateConfig(), stateProviders(), stateSecrets());
            root.secretsLoad(configured());
            root.metatubeToken = 'STALE-LEGACY-metatube-123456';
            root.metatubeServerUrl = ' http://example.invalid ';
            root.metatubeLanMode = true;
            root.showToast = () => {};
            if (mode === 'new') { root.secretReplace('metatube'); root.secretFields.metatube.input = '  sk-ant-api03-test1234567890abcd\n'; }
            if (mode === 'clear') root.secretClear('metatube');
            let body;
            globalThis.fetch = async (_url, opts) => { body = JSON.parse(opts.body); return { ok: false, json: async () => ({ success: false }) }; };
            await root.metatubeConnect();
            const expected = mode === 'configured' ? 'gggg••••7777' : mode === 'new' ? 'sk-ant-api03-test1234567890abcd' : '';
            assert.ok(body?.token === expected && body.url === 'http://example.invalid' && body.allow_lan === true, mode);
            assert.ok(!contains(body, 'STALE-LEGACY-'), mode);
        }
    } finally { globalThis.fetch = realFetch; }
});
