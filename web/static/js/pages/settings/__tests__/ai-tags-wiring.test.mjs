// TASK-188c-T8a：AI 標籤 form 三欄／載入儲存／自動抓取接線
//
// state-config.js 匯入瀏覽器 importmap 別名 `@/settings/...`（base.html 把
// `@/settings/` 指到 `/static/js/pages/settings/`）。既有 alias-loader.mjs 只做
// `@/` → `web/static/js/` 字首轉譯，對 `@/settings/` 會解成錯誤路徑；此檔自帶
// 與 importmap 對齊的 resolve hook（與 nfo-title-format-wiring.test.mjs 同形）。

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

function makeFakeThis() {
  const toasts = [];
  const fake = mergeState(stateConfig(), stateProviders());
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

async function assertClaudeTagsPreselect(translateProvider) {
  const fakeThis = makeFakeThis();
  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes('/api/claude/models')) {
      return {
        json: async () => ({
          success: true,
          models: ['claude-sonnet-5', 'claude-haiku-9-9'],
          latest_haiku: 'claude-haiku-9-9',
          default_model: 'claude-sonnet-5',
        }),
      };
    }
    if (u.includes('/api/config') && opts && opts.method === 'PUT') {
      return { json: async () => ({ success: true }) };
    }
    if (u.includes('/api/config')) {
      return {
        json: async () => ({
          success: true,
          data: minimalConfig({
            translate: {
              enabled: false,
              provider: translateProvider,
              ollama: { url: 'http://localhost:11434', model: '' },
              gemini: {},
              openai: {},
              claude: { api_key: 'k' },
            },
            ai_services: {
              tags: { enabled: true, provider: 'claude', model: '' },
            },
          }),
        }),
      };
    }
    return { json: async () => ({ success: true, data: {} }) };
  };

  await fakeThis.loadConfig.call(fakeThis);
  await waitUntil(
    () => typeof fakeThis.form.aiTagsModel === 'string' && fakeThis.form.aiTagsModel !== '',
    `aiTagsModel preselect (translate=${translateProvider})`,
  );
  await new Promise((r) => setTimeout(r, 0));

  assert.equal(fakeThis.form.aiTagsModel, 'claude-haiku-9-9');
  assert.equal(fakeThis.isDirty, false);
  return fakeThis;
}

test('tags_load_not_dirty_claude_preselect', async () => {
  // tags-only：翻譯 gemini、tags claude → ensureProviderModels 路徑
  const tagsOnly = await assertClaudeTagsPreselect('gemini');
  tagsOnly.form.aiTagsModel = 'x';
  assert.equal(tagsOnly.isDirty, true);

  // 同家：翻譯與 tags 都是 claude → 翻譯分支抓完後也要預選（P2 修正）
  await assertClaudeTagsPreselect('claude');
});

test('tags_load_not_dirty_ollama_untouched', async () => {
  const fakeThis = makeFakeThis();
  const ollamaList = ['llava', 'm2'];
  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes('/api/ollama/models')) {
      return {
        json: async () => ({ success: true, models: ollamaList }),
      };
    }
    if (u.includes('/api/config') && opts && opts.method === 'PUT') {
      return { json: async () => ({ success: true }) };
    }
    if (u.includes('/api/config')) {
      return {
        json: async () => ({
          success: true,
          data: minimalConfig({
            translate: {
              enabled: false,
              provider: 'gemini',
              ollama: { url: 'http://localhost:11434', model: '' },
              gemini: {},
              openai: {},
            },
            ai_services: {
              tags: { enabled: true, provider: 'ollama', model: '' },
            },
          }),
        }),
      };
    }
    return { json: async () => ({ success: true, data: {} }) };
  };

  await fakeThis.loadConfig.call(fakeThis);
  await waitUntil(
    () => typeof fakeThis.form.aiTagsModel === 'string' && fakeThis.form.aiTagsModel !== '',
    'aiTagsModel preselect',
  );
  await new Promise((r) => setTimeout(r, 0));

  assert.equal(fakeThis.form.ollamaModel, '');
  assert.deepEqual(fakeThis.ollamaModels, ollamaList);
  assert.equal(fakeThis.isDirty, false);
});

test('tags_save_roundtrip_keeps_siblings', async () => {
  const fakeThis = makeFakeThis();
  let putBody = null;
  const imageSimilar = {
    enabled: true,
    url: 'http://sim',
    api_key: '',
    model: 'sim-m',
    future_sim: 1,
  };
  const faces = {
    enabled: false,
    url: '',
    api_key: '',
    model: '',
    future_faces: 2,
  };
  const otherSection = { a: 1 };

  globalThis.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes('/api/ollama/models') || u.includes('/api/claude/models')) {
      return { json: async () => ({ success: true, models: [] }) };
    }
    if (u.includes('/api/config') && opts && opts.method === 'PUT') {
      putBody = JSON.parse(opts.body);
      return { json: async () => ({ success: true }) };
    }
    if (u.includes('/api/config')) {
      return {
        json: async () => ({
          success: true,
          data: minimalConfig({
            translate: {
              enabled: false,
              provider: 'gemini',
              ollama: { url: 'http://localhost:11434', model: '' },
              gemini: {},
              openai: {},
            },
            ai_services: {
              image_similar: imageSimilar,
              faces,
              other_section: otherSection,
              tags: { enabled: false, provider: '', model: '', future_tags: 7 },
            },
          }),
        }),
      };
    }
    return { json: async () => ({ success: true, data: {} }) };
  };

  await fakeThis.loadConfig.call(fakeThis);
  assert.equal(fakeThis.form.aiTagsEnabled, false);
  assert.equal(fakeThis.form.aiTagsProvider, '');
  assert.equal(fakeThis.form.aiTagsModel, '');

  fakeThis.form.aiTagsEnabled = true;
  fakeThis.form.aiTagsProvider = 'gemini';
  fakeThis.form.aiTagsModel = 'gem-x';
  await fakeThis.saveConfig.call(fakeThis);

  assert.ok(putBody, '應送出 PUT');
  assert.deepEqual(putBody.ai_services.tags, {
    enabled: true,
    provider: 'gemini',
    model: 'gem-x',
    future_tags: 7,
  });
  assert.deepEqual(putBody.ai_services.image_similar, imageSimilar);
  assert.deepEqual(putBody.ai_services.faces, faces);
  assert.deepEqual(putBody.ai_services.other_section, otherSection);
});
