import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.t = (key) => key;

const IMPORTMAP = {
    '@/settings/': 'pages/settings/',
    '@/shared/': 'shared/',
    '@/components/': 'components/',
    '@/search/': 'pages/search/',
    '@/showcase/': 'pages/showcase/',
    '@/scanner/': 'pages/scanner/',
};
const STATIC_JS_ROOT = pathToFileURL(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../') + '/',
).href;

const loaderCode = `
const IMPORTMAP = ${JSON.stringify(IMPORTMAP)};
const STATIC_JS_ROOT = ${JSON.stringify(STATIC_JS_ROOT)};
export async function resolve(specifier, context, nextResolve) {
    for (const [prefix, rel] of Object.entries(IMPORTMAP)) {
        if (specifier.startsWith(prefix)) {
            return nextResolve(STATIC_JS_ROOT + rel + specifier.slice(prefix.length), context);
        }
    }
    if (specifier.startsWith('@/')) {
        return nextResolve(STATIC_JS_ROOT + specifier.slice(2), context);
    }
    return nextResolve(specifier, context);
}
`;
register(`data:text/javascript,${encodeURIComponent(loaderCode)}`, import.meta.url);

const { stateConfig } = await import('../state-config.js');
const { stateSecrets } = await import('../state-secrets.js');
const { stateOpenaiGroups } = await import('../state-openai-groups.js');
const { stateProviders } = await import('../state-providers.js');

function makeFakeThis() {
    return {
        ...stateConfig(),
        ...stateProviders(),
        ...stateSecrets(),
        ...stateOpenaiGroups(),
        serverMode: true,
        accessAuthPin: '1234',
        accessAuthSaving: false,
        _loadFormatVariables: async () => {},
        _loadCoverBadgeRules: async () => {},
        _loadVideoCount: () => {},
        hydrateMetatubeStatus: async () => {},
        loadOllamaModels: () => {},
    };
}

function minimalConfig() {
    return {
        search: {},
        translate: { enabled: false, provider: 'ollama', ollama: {}, gemini: {}, openai: {} },
        scraper: {
            create_folder: true,
            folder_layers: ['{num}'],
            filename_format: '[{num}][{maker}] {title}',
            nfo_title_format: '[{num}]{title}',
            max_title_length: 80,
            max_filename_length: 200,
            video_extensions: ['.mp4'],
            suffix_keywords: [],
            external_manager: 'off',
            download_sample_images: false,
            strm_path_mappings: {},
        },
        gallery: {
            default_mode: 'image', default_sort: 'date', default_order: 'descending',
            items_per_page: 90, min_size_mb: 0, output_dir: '', output_filename: 'gallery_output.html',
            show_table_list: false, cover_badges: { enabled: false, items: {} },
        },
        showcase: { player: '' },
        general: { default_page: 'search', close_action: 'ask', theme: 'light', server_mode: false },
        metatube: { enabled: false },
        sources: [],
    };
}


test('loadConfig 讀入 GET 回應的 can_edit 存進 accessAuthCanEdit', async () => {
    const fakeThis = makeFakeThis();
    fakeThis.accessAuthCanEdit = true;
    globalThis.fetch = async (url) => {
        if (url === '/api/access/settings') {
            return { json: async () => ({ success: true, enabled: true, pin: '', pin_revealed: false, can_edit: false }) };
        }
        if (url === '/api/config') {
            return { json: async () => ({ success: true, data: minimalConfig() }) };
        }
        return { json: async () => ({ success: true, data: {} }) };
    };
    await fakeThis.loadConfig.call(fakeThis);
    assert.equal(fakeThis.accessAuthCanEdit, false);
});
