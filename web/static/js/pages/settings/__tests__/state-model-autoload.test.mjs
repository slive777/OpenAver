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



const key = 'fake-secret-alpha-1234567890';
const groupId = 'oc0123abcd';
const response = data => ({ ok: true, json: async () => data });
const tick = () => new Promise(resolve => setTimeout(resolve, 150));
function config(provider = 'none', tags = '', withKey = true) {
  return minimalConfig({
    translate: {
      enabled: true, provider, ollama: { url: 'http://localhost:11434' },
      gemini: { api_key: withKey ? key : '' }, claude: { api_key: key },
      openai: { base_url: 'http://localhost:1234' },
      openai_custom: { [groupId]: { name: 'Example', base_url: 'http://localhost:4321', api_key: '' } },
    },
    ai_services: { tags: { enabled: true, provider: tags, model: '' } },
  });
}
function installFetch(cfg, outcome = 'multi', hold = false) {
  const original = globalThis.fetch;
  const calls = [];
  const pending = [];
  const models = outcome === 'multi' ? ['haiku-a', 'model-b'] : ['haiku-a'];
  globalThis.fetch = (url, options = {}) => {
    if (url === '/api/config') return Promise.resolve(response({ success: true, data: structuredClone(cfg) }));
    if (!url.startsWith('/api/gemini/test') && !url.startsWith('/api/claude/models') &&
        !url.startsWith('/api/openai/models') && !url.startsWith('/api/ollama/models') &&
        !url.startsWith('/api/openai/official/models')) return Promise.resolve(response({ success: true }));
    const group = options.body ? (JSON.parse(options.body).group_id || null) : null;
    calls.push({ url, group });
    const data = outcome === 'failed' ? { success: false } : {
      success: true, models: url === '/api/gemini/test' ? models.map(name => ({ name })) : models,
    };
    if (!hold) return Promise.resolve(response(data));
    return new Promise(resolve => pending.push(() => resolve(response(data))));
  };
  return {
    count(url, group) { return calls.filter(c => c.url.startsWith(url) && (group === undefined || c.group === group)).length; },
    flush() { for (const resolve of pending.splice(0)) resolve(); },
    restore() { globalThis.fetch = original; },
  };
}
async function withEnv(cfg, fn, outcome = 'multi', hold = false) {
  const fake = await makeFakeThis();
  const f = installFetch(cfg, outcome, hold);
  try { await fn(fake, f); } finally { f.flush(); await tick(); f.restore(); }
}
async function load(fake) { await fake.loadConfig(); }
function change(fake, provider) {
  fake.form.translateProvider = provider;
  fake.onTranslateProviderChange();
}
for (const outcome of ['multi', 'single', 'failed']) {
  test(`autoload_once_per_page_across_outcomes[${outcome}]`, async () => {
    await withEnv(config(), async (fake, f) => {
      await load(fake);
      for (let i = 0; i < 4; i++) {
        change(fake, 'gemini');
        await fake.ensureProviderModels('gemini');
        change(fake, 'claude');
        await fake.ensureProviderModels('claude');
      }
      await tick();
      assert.equal(f.count('/api/gemini/test'), 1);
      assert.equal(f.count('/api/claude/models'), 1);
    }, outcome);
  });
}
test('autoload_open_page_same_provider_one_request', async () => {
  for (const provider of ['gemini', 'claude']) {
    await withEnv(config(provider, provider), async (fake, f) => {
      const original = fake.openaiGroupsLoad;
      fake.openaiGroupsLoad = function (cfg) {
        original.call(this, cfg);
        assert.equal(this._configLoading, true);
        this.onTranslateProviderChange();
      };
      await load(fake);
      assert.equal(fake._configLoading, false);
      fake.onTranslateProviderChange();
      await waitUntil(() => f.count(provider === 'gemini' ? '/api/gemini/test' : '/api/claude/models') >= 1, 'model request');
      assert.equal(f.count(provider === 'gemini' ? '/api/gemini/test' : '/api/claude/models'), 1);
      f.flush();
      await waitUntil(() => Boolean(fake.form.aiTagsModel), 'tag preselection');
      assert.equal(fake.form.aiTagsModel, provider === 'gemini' ? 'gemini-flash-lite-latest' : 'haiku-a');
      assert.equal(fake.savedState.aiTagsModel, '');
      assert.equal(fake.isDirty, true);
    }, 'multi', true);
  }
});
test('autoload_open_page_openai_compat_one_request', async () => {
  for (const provider of ['openai', 'openai:' + groupId]) {
    for (const position of ['translate', 'tags']) {
      await withEnv(config(position === 'translate' ? provider : 'none', position === 'tags' ? provider : ''), async (fake, f) => {
        await load(fake);
        await tick();
        assert.equal(f.count('/api/openai/models', provider === 'openai' ? null : groupId), 1);
      });
    }
  }
});
test('manual_test_always_sends_request', async () => {
  await withEnv(config(), async (fake, f) => {
    await load(fake);
    change(fake, 'gemini');
    await tick();
    await fake.testGeminiConnection();
    assert.equal(f.count('/api/gemini/test'), 2);
    await fake.fetchClaudeModels();
    await fake.ensureProviderModels('claude');
    assert.equal(f.count('/api/claude/models'), 1);
  });
});
test('reload_resets_autoload_gate', async () => {
  await withEnv(config('gemini', 'claude'), async (fake, f) => {
    await load(fake);
    await tick();
    await load(fake);
    await tick();
    assert.equal(f.count('/api/gemini/test'), 2);
    assert.equal(f.count('/api/claude/models'), 2);
  });
});
test('unset_key_does_not_consume_autoload', async () => {
  await withEnv(config('none', '', false), async (fake, f) => {
    await load(fake);
    change(fake, 'gemini');
    assert.equal(f.count('/api/gemini/test'), 0);
    assert.equal(Boolean(fake.modelAutoLoad?.attempted.gemini), false);
    fake.secretFields.gemini.input = key;
    change(fake, 'gemini');
    await tick();
    change(fake, 'gemini');
    await tick();
    assert.equal(f.count('/api/gemini/test'), 1);
  });
});

