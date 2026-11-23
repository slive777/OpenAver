// TASK-154b-T4：NFO 標題格式 state-config 接線
//   - namingMenuVars('nfo_title') 排除 {suffix}；filename／folder 零回歸
//   - form.nfoTitleFormat loadConfig／saveConfig 接線
//   - saveConfig() 對 nfo_title_format_invalid 的 toast 分支
//   - 非本卡 reason 仍落最終 else（零回歸）
//
// state-config.js 匯入瀏覽器 importmap 別名 `@/settings/...`（base.html 把
// `@/settings/` 指到 `/static/js/pages/settings/`，不是 `/static/js/settings/`）。
// 既有 alias-loader.mjs 只做 `@/` → `web/static/js/` 字首轉譯，對 `@/settings/`
// 會解成錯誤路徑；此檔自帶與 importmap 對齊的 resolve hook（不改共用 loader）。

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
  const base = { ...stateConfig(), ...stateSecrets() };
  return {
    ...base,
    formatVariables: FORMAT_VARS.map((v) => ({ ...v })),
    showToast: (msg, type) => toasts.push({ msg, type }),
    _toasts: toasts,
    _loadFormatVariables: async () => {},
    _loadCoverBadgeRules: async () => {},
    _loadVideoCount: () => {},
    hydrateMetatubeStatus: async () => {},
    loadOllamaModels: () => {},
  };
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


test('loadConfig 讀入 scraper.nfo_title_format', async () => {
  const fakeThis = makeFakeThis();
  globalThis.fetch = async (url) => {
    if (String(url).includes('/api/config')) {
      return {
        json: async () => ({
          success: true,
          data: minimalConfig({
            scraper: { nfo_title_format: '{num}-{title}-{actor}' },
          }),
        }),
      };
    }
    return { json: async () => ({ success: true, data: {} }) };
  };
  await fakeThis.loadConfig.call(fakeThis);
  assert.equal(fakeThis.form.nfoTitleFormat, '{num}-{title}-{actor}');
});

test('saveConfig PUT body 含 scraper.nfo_title_format', async () => {
  const fakeThis = makeFakeThis();
  fakeThis.form.nfoTitleFormat = '{num}-{title}';
  let putBody = null;
  globalThis.fetch = async (url, opts) => {
    if (opts && opts.method === 'PUT') {
      putBody = JSON.parse(opts.body);
      return { json: async () => ({ success: true }) };
    }
    return {
      json: async () => ({
        success: true,
        data: minimalConfig(),
      }),
    };
  };
  await fakeThis.saveConfig.call(fakeThis);
  assert.ok(putBody, '應送出 PUT');
  assert.equal(putBody.scraper.nfo_title_format, '{num}-{title}');
});


