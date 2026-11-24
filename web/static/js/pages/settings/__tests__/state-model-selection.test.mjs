// 驗證自訂 OpenAI 組的載入、儲存、請求隔離與標籤模型記憶。
// 瀏覽器 importmap 的 @/settings/ 指向 pages/settings/；Node 的通用 alias loader
// 無法解析此對應，因此本檔自帶與瀏覽器一致的 resolve hook。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.t = (key, _params) => key;
globalThis.document = {
  documentElement: { getAttribute: () => 'light' },
  createElement: () => ({
    className: '',
    contentEditable: 'true',
    spellcheck: false,
    dataset: {},
    childNodes: [],
    children: [],
    appendChild() {},
    setAttribute() {},
    addEventListener() {},
    removeEventListener() {},
  }),
  createTextNode: (t) => ({ nodeType: 3, textContent: t }),
  createDocumentFragment: () => ({
    nodeType: 11,
    childNodes: [],
    lastChild: null,
    appendChild() {},
  }),
};

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
const { mergeState } = await import('@/shared/merge-state.js');

const FORMAT_VARS = [
  { name: '{num}', folder_ok: true },
  { name: '{title}', folder_ok: true },
  { name: '{actor}', folder_ok: true },
  { name: '{actors}', folder_ok: true },
  { name: '{maker}', folder_ok: true },
  { name: '{date}', folder_ok: true },
  { name: '{year}', folder_ok: true },
  { name: '{month}', folder_ok: true },
  { name: '{day}', folder_ok: true },
  { name: '{suffix}', folder_ok: false },
];

async function makeFakeThis() {
  const toasts = [];
  const fake = mergeState(stateConfig(), stateProviders(), stateSecrets(), stateOpenaiGroups());
  fake.formatVariables = FORMAT_VARS.map((v) => ({ ...v }));
  fake.showToast = (msg, type) => toasts.push({ msg, type });
  fake._toasts = toasts;
  fake._loadFormatVariables = async () => {};
  fake._loadCoverBadgeRules = async () => {};
  fake._loadVideoCount = () => {};
  fake.hydrateMetatubeStatus = async () => {};
  return fake;
}

function minimalConfig(overrides = {}) {
  const { scraper: scraperOv, ...rest } = overrides;
  return {
    search: { favorite_folder: '', proxy_url: '' },
    thumbnail_cache_enabled: false,
    translate: {
      enabled: false,
      provider: 'ollama',
      ollama: { url: 'http://localhost:11434', model: '' },
      gemini: {},
      openai: {},
    },
    scraper: {
      create_folder: true,
      folder_layers: ['{num}'],
      filename_format: '[{num}][{maker}] {title}',
      nfo_title_format: '[{num}]{title}',
      max_title_length: 80,
      max_filename_length: 200,
      video_extensions: ['.mp4'],
      suffix_keywords: ['-cd1'],
      external_manager: 'off',
      download_sample_images: false,
      strm_path_mappings: {},
      ...(scraperOv || {}),
    },
    gallery: {
      default_mode: 'image',
      default_sort: 'date',
      default_order: 'descending',
      items_per_page: 90,
      min_size_mb: 0,
      output_dir: '',
      output_filename: 'gallery_output.html',
      show_table_list: false,
      cover_badges: { enabled: false, items: {} },
    },
    showcase: { player: '' },
    general: { default_page: 'search', close_action: 'ask', theme: 'light' },
    metatube: { enabled: false },
    sources: [],
    ...rest,
  };
}

/** Poll until pred(); throw on timeout so the test fails (never soft-pass). */
async function waitUntil(pred, label, ms = 2000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    if (pred()) return;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error(`timeout waiting for ${label}`);
}

const groupId = 'oc0123abcd';
const keys = { gemini: 'fake-gemini-key-123456789', claude: 'fake-claude-key-123456789', official: 'fake-official-key-123456789' };
const response = data => ({ ok: true, json: async () => data });
const endpoints = { gemini: '/api/gemini/test', claude: '/api/claude/models', openai_official: '/api/openai/official/models', ollama: '/api/ollama/models', openai: '/api/openai/models', group: '/api/openai/models' };
const fields = { gemini: 'geminiModel', claude: 'claudeModel', openai_official: 'openaiOfficialModel', ollama: 'ollamaModel', openai: 'openaiModel' };
const saved = { gemini: 'saved-gemini-x', claude: 'claude-haiku-5-5', openai_official: 'saved-gpt-x', ollama: 'saved-ollama-x', openai: 'saved-compatible-x', group: 'saved-group-x' };
function config(provider, blank = false) {
  return minimalConfig({ translate: {
    enabled: true, provider: provider === 'group' ? `openai:${groupId}` : provider,
    ollama: { url: 'http://localhost:11434', model: saved.ollama },
    gemini: { api_key: keys.gemini, ...(blank && provider === 'gemini' ? {} : { model: saved.gemini }) },
    claude: { api_key: keys.claude, model: saved.claude },
    openai_official: { api_key: keys.official, model: blank && provider === 'openai_official' ? '' : saved.openai_official },
    openai: { base_url: 'http://localhost:1234', model: saved.openai },
    openai_custom: { [groupId]: { name: 'Example', base_url: 'http://localhost:4321', api_key: '', model: saved.group } },
  }, ai_services: { tags: { enabled: false, provider: '', model: '' } } });
}
function installFetch(cfg, outcome = 'success', hold = false) {
  const original = globalThis.fetch;
  const pending = [];
  const calls = [];
  globalThis.fetch = (url) => {
    if (url === '/api/config') return Promise.resolve(response({ success: true, data: structuredClone(cfg) }));
    if (!Object.values(endpoints).some(endpoint => url.startsWith(endpoint))) return Promise.resolve(response({ success: true }));
    calls.push(url);
    const data = outcome === 'failed' ? { success: false, error: 'failed' } : url.startsWith(endpoints.gemini)
      ? { success: true, models: [{ name: 'gemini-a' }, { name: 'gemini-b' }] }
      : url.startsWith(endpoints.claude)
        ? { success: true, default_model: 'claude-haiku-5-5', latest_haiku: 'claude-haiku-6', models: ['claude-haiku-6', 'claude-sonnet-6'] }
        : { success: true, default_model: 'gpt-luna-x', models: ['model-a', 'model-b'] };
    const complete = () => outcome === 'reject' ? Promise.reject(new Error('fake failure')) : Promise.resolve(response(data));
    if (!hold) return complete();
    return new Promise((resolve, reject) => pending.push(() => complete().then(resolve, reject)));
  };
  return { count: () => calls.length, flush() { for (const release of pending.splice(0)) release(); }, restore() { globalThis.fetch = original; } };
}
async function withEnv(cfg, fn, outcome = 'success', hold = false) {
  const fake = await makeFakeThis();
  const f = installFetch(cfg, outcome, hold);
  try { await fn(fake, f); } finally { f.flush(); await new Promise(resolve => setTimeout(resolve, 0)); f.flush(); f.restore(); }
}
async function load(fake) { await fake.loadConfig(); }

for (const provider of ['gemini', 'claude', 'openai_official', 'ollama', 'openai', 'group']) {
  test(`auto_load_keeps_saved_model[${provider}]`, async () => {
    for (const outcome of ['success', 'failed']) {
      await withEnv(config(provider), async (fake, f) => {
        await load(fake);
        await waitUntil(() => f.count() > 0, 'model request');
        const form = JSON.stringify(fake.form);
        const state = JSON.stringify(fake.savedState);
        assert.equal(fake.isDirty, false);
        f.flush();
        await waitUntil(() => Object.keys(fake.modelAutoLoad.inflight).length > 0, 'inflight');
        await Promise.all(Object.values(fake.modelAutoLoad.inflight));
        assert.equal(JSON.stringify(fake.form) === form, true);
        assert.equal(JSON.stringify(fake.savedState) === state, true);
        assert.equal(fake.isDirty, false);
      }, outcome, true);
    }
  });
}
for (const provider of ['gemini', 'ollama']) {
  test(`failed_manual_test_keeps_model_list[${provider}]`, async () => {
    for (const outcome of ['failed', 'reject']) {
      await withEnv(config('none'), async fake => {
        await load(fake);
        const list = provider === 'gemini' ? [{ name: 'old-a' }, { name: 'old-b' }] : ['old-a', 'old-b'];
        fake[`${provider}Models`] = structuredClone(list);
        await (provider === 'gemini' ? fake.testGeminiConnection() : fake.testOllamaConnection());
        assert.deepEqual(fake[`${provider}Models`], list);
      }, outcome);
    }
  });
}
for (const provider of ['gemini', 'openai_official']) {
  test(`blank_model_preselected_without_dirty[${provider}]`, async () => {
    await withEnv(config(provider, true), async (fake, f) => {
      await load(fake);
      await waitUntil(() => f.count() > 0, 'model request');
      f.flush();
      await Promise.all(Object.values(fake.modelAutoLoad.inflight));
      const field = fields[provider];
      const expected = provider === 'gemini' ? 'gemini-a' : 'gpt-luna-x';
      assert.equal(fake.form[field], expected);
      assert.equal(fake.savedState[field], expected);
      assert.equal(fake.isDirty, false);
    }, 'success', true);
  });
}
for (const provider of ['gemini', 'claude', 'openai_official', 'ollama']) {
  test(`manual_test_replacing_saved_model_shows_unsaved[${provider}]`, async () => {
    await withEnv(config('none'), async fake => {
      await load(fake);
      const field = fields[provider];
      assert.equal(fake.form[field], saved[provider]);
      if (provider === 'gemini') await fake.testGeminiConnection();
      if (provider === 'claude') await fake.fetchClaudeModels();
      if (provider === 'openai_official') await fake.fetchOpenAIOfficialModels();
      if (provider === 'ollama') await fake.testOllamaConnection();
      assert.equal(fake.form[field], { gemini: 'gemini-a', claude: 'claude-haiku-6', openai_official: 'gpt-luna-x', ollama: 'model-a' }[provider]);
      assert.equal(fake.savedState[field], saved[provider]);
      assert.equal(fake.isDirty, true);
    });
  });
}



