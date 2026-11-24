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


const A = 'oc0123abcd';
const B = 'oc89abcdef';
const C = 'oc00000001';
const P = 'openai:' + A;
const Q = 'openai:' + B;
const keyA = 'fake-key-alpha-0123456789';
const keyB = 'fake-key-bravo-0123456789';
const keyDefault = 'fake-key-default-0123456789';
const maskA = 'fake-mask-alpha-0123456789';
const maskB = 'fake-mask-bravo-0123456789';
const group = (name, url, model = '', key = '') => ({ name, base_url: url, model, use_custom_model: false, api_key: key });
const configWith = (groups = {}, provider = 'ollama', tags = '', model = '') => minimalConfig({
  translate: { enabled: true, provider, ollama: {}, gemini: {}, openai: {}, openai_custom: groups },
  ai_services: { tags: { enabled: true, provider: tags, model } },
});
const response = data => ({ ok: true, json: async () => data });
const delayTimers = () => new Promise(resolve => setTimeout(resolve, 130));
async function load(fake, config) {
  globalThis.fetch = async () => response({ success: true, data: structuredClone(config) });
  await fake.loadConfig.call(fake);
  await delayTimers();
}
async function save(fake, config) {
  let sent;
  globalThis.fetch = async (_url, opts) => {
    if (opts?.method === 'PUT') {
      sent = JSON.parse(opts.body);
      return response({ success: true });
    }
    return response({ success: true, data: structuredClone(config) });
  };
  await fake._saveServerConfig.call(fake);
  assert.ok(sent, 'PUT was sent');
  return sent;
}
async function attachPanel(root) {
  const { aiTagsPanel } = await import('../ai-tags-panel.js');
  const watches = {};
  const panel = Object.assign(Object.create(root), aiTagsPanel(), {
    $watch(path, callback) { watches[path] = callback; },
  });
  return { panel, watches };
}
async function select(root, panel, provider) {
  root.form.aiTagsProvider = provider;
  await panel.onProviderChange();
}

test('group_add_keeps_ids_order_and_blank_fields', async () => {
  const f = await makeFakeThis();
  assert.equal(f.openaiGroupAdd('A', 'translate', () => 0x0123abcd), A);
  assert.equal(f.openaiGroupAdd('B', 'tags', () => 0x89abcdef), B);
  assert.equal(f.openaiGroupAdd('C', 'translate', () => 1), C);
  assert.deepEqual(f.form.openaiGroups.map(g => g.id), [A, B, C]);
  for (const id of [A, B, C]) {
    const entry = f.openaiGroupById(id);
    assert.ok(entry.baseUrl === '' && entry.model === '' && entry.useCustomModel === false);
    assert.equal(Object.hasOwn(f.secretFields, id), true);
    assert.equal(f.secretWire(id) === '', true);
  }
  f.openaiGroupById(A).baseUrl = 'https://a.invalid';
  f.openaiGroupById(A).model = 'model-a';
  for (const id of [B, C]) {
    assert.ok(f.openaiGroupById(id).baseUrl === '' && f.openaiGroupById(id).model === '');
  }
  await f.openaiGroupRemove(B);
  assert.deepEqual(f.form.openaiGroups.map(g => g.id), [A, C]);
});
test('group_models_never_cross_tabs_or_groups', async () => {
  const f = await makeFakeThis();
  f.openaiGroupAdd('A', 'translate', () => 0x0123abcd);
  f.openaiGroupAdd('B', 'tags', () => 0x89abcdef);
  f.openaiGroupById(A).model = 'translate-a';
  f.openaiGroupById(B).model = 'x';
  f.openaiGroupById(B).useCustomModel = true;
  f.openaiGroupRt[A].models = ['m1', 'm2'];
  f.openaiGroupRt[B].models = ['b1', 'b2'];
  const { panel } = await attachPanel(f);
  await select(f, panel, P);
  f.setTagsModel(P, 'm1');
  assert.ok(f.openaiGroupById(A).model === 'translate-a', 'tags does not change translation');
  f.openaiGroupById(A).model = 'translate-a2';
  assert.ok(f.form.aiTagsModel === 'm1', 'translation does not change tags');
  await select(f, panel, Q); f.setTagsModel(Q, 'x');
  assert.ok(f.form.aiTagsModel === 'x' && f.openaiGroupById(B).useCustomModel === true);
  await select(f, panel, P);
  assert.ok(f.form.aiTagsModel === 'm1' && f.openaiGroupById(A).useCustomModel === false);
  await select(f, panel, Q);
  assert.ok(f.form.aiTagsModel === 'x' && f.openaiGroupById(B).useCustomModel === true);
  await select(f, panel, P);
  assert.ok(f.form.aiTagsModel === 'm1' && f.openaiGroupById(A).model === 'translate-a2');
  await select(f, panel, Q);
  assert.ok(f.form.aiTagsModel === 'x' && f.openaiGroupById(B).model === 'x' && f.openaiGroupById(B).useCustomModel === true);
});
test('group_delete_never_leaves_dangling_provider', async () => {
  const f = await makeFakeThis();
  f.openaiGroupAdd('A', 'translate', () => 0x0123abcd);
  f.form.aiTagsProvider = P; f.setTagsModel(P, 'm1');
  f.openaiModels = ['default-a', 'default-b']; f.form.openaiModel = 'default-b';
  const remove = f.secretFieldRemove;
  f.secretFieldRemove = function(id) {
    assert.equal(this.form.openaiGroups.some(g => g.id === id), false);
    assert.equal(Object.hasOwn(this.secretFields, id), true);
    remove.call(this, id);
  };
  await f.openaiGroupRemove(A);
  assert.ok(f.form.translateProvider === 'openai' && f.form.aiTagsProvider === 'openai');
  assert.ok(f.form.openaiModel === 'default-b');
  assert.equal(Object.hasOwn(f.secretFields, A), false);
  assert.equal(Object.hasOwn(f.openaiGroupRt, A), false);
  assert.equal(Object.hasOwn(f.tagsModelMemo, P), false);
  const { labelFor } = await import('../openai-group-logic.js');
  assert.equal(labelFor(null, f.form.openaiGroups).key, 'settings.translate.openai_compatible');
  f.openaiGroupAdd('A', 'translate', () => 0x0123abcd);
  f.form.aiTagsProvider = 'gemini'; f.setTagsModel('gemini', 'gem-model');
  await f.openaiGroupRemove(A);
  assert.ok(f.form.translateProvider === 'openai' && f.form.aiTagsProvider === 'gemini' && f.form.aiTagsModel === 'gem-model');
  for (const invalid of [Q, 'openai:zzz']) {
    await load(f, configWith({}, invalid, invalid, 'stale'));
    assert.ok(f.form.translateProvider === 'openai', 'invalid translate provider');
    assert.ok(f.form.aiTagsProvider === 'openai' && f.form.aiTagsModel === '', 'invalid tags provider');
  }
  await load(f, configWith({ 'ocABCDEF12': group('bad', ''), 'oc000000.1': group('bad', '') }));
  assert.equal(f.form.openaiGroups.length, 0);
});
test('group_save_payload_and_dirty', async () => {
  const f = await makeFakeThis();
  const config = configWith({ [A]: group('A', '', 'model-a', maskA), [B]: group('B', '', 'model-b', maskB) }, P, Q, 'tags-b');
  await load(f, config);
  assert.equal(f.isDirty, false, 'loaded snapshot');
  const baseline = structuredClone(f.form);
  f.openaiGroupAdd('C', 'translate', () => 1);
  assert.equal(f.isDirty, true, 'add');
  f.form = structuredClone(baseline); f.secretFieldRemove(C);
  assert.equal(f.isDirty, false, 'restore after add');
  await f.openaiGroupRemove(B);
  assert.equal(f.isDirty, true, 'delete');
  await load(f, config);
  for (const [field, value] of [['name', 'changed'], ['baseUrl', 'https://changed.invalid'], ['model', 'changed'], ['useCustomModel', true]]) {
    f.openaiGroupById(A)[field] = value;
    assert.equal(f.isDirty, true, 'edit ' + field);
    f.form = structuredClone(f.savedState);
    assert.equal(f.isDirty, false, 'restore ' + field);
  }
  f.form.translateProvider = Q;
  assert.equal(f.isDirty, true, 'translate selection');
  f.form = structuredClone(f.savedState);
  f.form.aiTagsProvider = P;
  assert.equal(f.isDirty, true, 'tags selection');
  f.form = structuredClone(f.savedState);
  assert.equal(f.isDirty, false, 'restore snapshot');
  f.openaiGroupById(A).baseUrl = ' https://a.invalid ';
  f.openaiGroupById(B).baseUrl = ' https://b.invalid ';
  // 使用者貼上帶尾空白的模型名，存檔後翻譯仍用得了。
  f.openaiGroupById(A).model = ' model-a ';
  let sent = await save(f, config);
  assert.equal(sent.translate.openai_custom[A].model, 'model-a');
  assert.deepEqual(Object.keys(sent.translate.openai_custom), [A, B]);
  for (const id of [A, B]) {
    assert.deepEqual(Object.keys(sent.translate.openai_custom[id]), ['name', 'base_url', 'model', 'use_custom_model', 'api_key']);
  }
  assert.ok(sent.translate.openai_custom[A].name === 'A'
    && sent.translate.openai_custom[A].base_url === 'https://a.invalid'
    && sent.translate.openai_custom[A].model === 'model-a'
    && sent.translate.openai_custom[A].use_custom_model === false, 'A payload fields');
  assert.ok(sent.translate.openai_custom[B].name === 'B'
    && sent.translate.openai_custom[B].base_url === 'https://b.invalid'
    && sent.translate.openai_custom[B].model === 'model-b'
    && sent.translate.openai_custom[B].use_custom_model === false, 'B payload fields');
  assert.ok(sent.translate.provider === P && sent.ai_services.tags.provider === Q);
  assert.ok(sent.translate.openai_custom[A].api_key === maskA, 'configured mask preserved');
  assert.ok(sent.translate.openai_custom[B].api_key === maskB, 'second mask preserved');
  f.secretReplace(A); f.secretFields[A].input = keyA; f.secretClear(B);
  sent = await save(f, config);
  assert.ok(sent.translate.openai_custom[A].api_key === keyA, 'replacement wire');
  assert.ok(sent.translate.openai_custom[B].api_key === '', 'clearing wire');
});
test('group_requests_go_to_their_own_group', async () => {
  const f = await makeFakeThis();
  f.form.openaiBaseUrl = 'https://default.invalid'; f.form.openaiModel = 'default-model';
  f.secretFields.openai.input = keyDefault;
  f.openaiGroupAdd('A', 'translate', () => 0x0123abcd);
  f.openaiGroupAdd('B', 'tags', () => 0x89abcdef);
  f.openaiGroupById(A).baseUrl = ' https://a.invalid '; f.openaiGroupById(A).model = 'custom-a';
  f.openaiGroupById(B).baseUrl = 'https://b.invalid'; f.openaiGroupById(B).model = 'custom-b';
  f.secretFields[A].input = keyA; f.secretFields[B].input = keyB;
  const bodies = [];
  globalThis.fetch = async (_url, opts) => {
    bodies.push(JSON.parse(opts.body));
    return response({ success: true, models: ['m1', 'm2'], translation: 'ja_skip' });
  };
  await f.fetchOpenAIModels({ groupId: A, source: 'manual' });
  assert.deepEqual(Object.keys(bodies[0]), ['base_url', 'api_key', 'group_id']);
  assert.ok(bodies[0].base_url === 'https://a.invalid' && bodies[0].group_id === A && bodies[0].api_key === keyA, 'A models body');
  assert.ok(bodies[0].base_url !== 'https://b.invalid' && bodies[0].api_key !== keyB && bodies[0].api_key !== keyDefault, 'A is isolated');
  assert.equal(f.openaiGroupById(A).useCustomModel, true);
  f.openaiGroupById(A).useCustomModel = false;
  await f.fetchOpenAIModels({ groupId: A, source: 'auto' });
  assert.equal(f.openaiGroupById(A).useCustomModel, false);
  await f.testOpenAITranslation({ groupId: A });
  assert.ok(bodies[2].base_url === 'https://a.invalid' && bodies[2].api_key === keyA && bodies[2].group_id === A && bodies[2].model === 'custom-a', 'unsaved A test body');
  await f.fetchOpenAIModels();
  assert.deepEqual(Object.keys(bodies[3]), ['base_url', 'api_key']);
  assert.ok(bodies[3].base_url === 'https://default.invalid' && bodies[3].api_key === keyDefault);
  await f.testOpenAITranslation();
  assert.deepEqual(Object.keys(bodies[4]), ['base_url', 'api_key', 'model']);
  assert.ok(bodies[4].base_url === 'https://default.invalid' && bodies[4].api_key === keyDefault && bodies[4].model === 'default-model');
  const loaded = await makeFakeThis();
  await load(loaded, configWith({ [A]: group('A', 'https://a.invalid') }, 'ollama'));
  assert.equal(loaded.isDirty, false);
  globalThis.fetch = async () => response({ success: true, models: ['m1', 'm2'] });
  await loaded.fetchOpenAIModels({ groupId: A, source: 'auto' });
  assert.ok(loaded.openaiGroupById(A).model === 'm1');
  assert.ok(loaded.savedState.openaiGroups.find(g => g.id === A).model === 'm1');
  assert.equal(loaded.isDirty, false);
});
test('removed_group_not_resurrected_by_server_copy', async () => {
  const f = await makeFakeThis();
  const config = configWith({ [A]: group('A', ''), [B]: group('B', '') }, P, Q, 'm1');
  await load(f, config);
  await f.openaiGroupRemove(A);
  let sent = await save(f, config);
  assert.deepEqual(Object.keys(sent.translate.openai_custom), [B]);
  assert.equal(Object.hasOwn(sent.translate.openai_custom, A), false, 'deleted group not rebuilt');
  const partial = configWith({ [A]: { api_key: '' }, [B]: group('B', '') }, 'ollama');
  sent = await save(f, partial);
  assert.deepEqual(Object.keys(sent.translate.openai_custom), [B], 'partial deleted group not rebuilt');
  await f.openaiGroupRemove(B);
  sent = await save(f, partial);
  assert.deepEqual(sent.translate.openai_custom, {});
});
test('custom_provider_value_is_known_everywhere', async () => {
  const f = await makeFakeThis();
  f.openaiGroupAdd('A', 'translate', () => 0x0123abcd);
  f.openaiGroupById(A).baseUrl = ' https://a.invalid ';
  f.secretFields[A].input = keyA;
  f.openaiGroupRt[A].models = ['m1', 'm2'];
  f.form.openaiBaseUrl = ' https://default.invalid '; f.form.ollamaUrl = 'http://ollama.invalid';
  f.secretFields.openai.input = keyDefault; f.secretFields.gemini.input = keyB;
  f.form.aiTagsEnabled = true; f.form.aiTagsProvider = P; f.form.aiTagsModel = 'm1';
  const { buildTagsTestBody, connShown, connEnabled } = await import('../ai-tags-logic.js');
  const wire = id => f.secretWire(id);
  const custom = buildTagsTestBody(f.form, wire);
  assert.deepEqual(Object.keys(custom), ['provider', 'model', 'base_url', 'api_key']);
  assert.ok(custom.provider === P && custom.model === 'm1' && custom.base_url === 'https://a.invalid' && custom.api_key === keyA, 'buildTagsTestBody custom');
  for (const [provider, expected] of [
    ['openai', { provider: 'openai', model: 'm1', base_url: 'https://default.invalid', api_key: keyDefault }],
    ['gemini', { provider: 'gemini', model: 'm1', api_key: keyB }],
    ['ollama', { provider: 'ollama', model: 'm1', base_url: 'http://ollama.invalid' }],
  ]) {
    f.form.aiTagsProvider = provider;
    assert.ok(JSON.stringify(buildTagsTestBody(f.form, wire)) === JSON.stringify(expected), 'buildTagsTestBody ' + provider);
  }
  f.form.aiTagsProvider = P;
  assert.deepEqual(f.aiTagsModelLists()[P], ['m1', 'm2'], 'aiTagsModelLists');
  assert.equal(connShown(f.form, P, 'tags'), true, 'connShown');
  assert.equal(connEnabled(f.form, P), true, 'connEnabled');
  let count = 0; let request;
  const config = configWith({ [A]: group('A', 'https://a.invalid', 'm1', maskA) }, P, P, 'm1');
  globalThis.fetch = async (url, opts) => {
    if (String(url) === '/api/config') return response({ success: true, data: structuredClone(config) });
    if (String(url) === '/api/openai/models') {
      count++; request = JSON.parse(opts.body);
      return response({ success: true, models: ['m1', 'm2'] });
    }
    return response({ success: true, data: {} });
  };
  await f.loadConfig.call(f);
  await waitUntil(() => count === 1 && f.openaiGroupRt[A].models.length === 2, 'loadConfig custom fetch');
  await delayTimers();
  assert.equal(count, 1, 'loadConfig fetch count');
  assert.equal(request.group_id, A, 'loadConfig group_id');
  const first = await makeFakeThis();
  await load(first, configWith());
  first.openaiGroupAdd('A', 'translate', () => 0x0123abcd);
  first.openaiGroupRt[A].models = ['m1', 'm2'];
  first.form.aiTagsProvider = '';
  first.form.aiTagsEnabled = false;
  const { panel, watches } = await attachPanel(first);
  first.savedState = structuredClone(first.form);
  first.form.aiTagsEnabled = true;
  panel.init();
  watches['form.aiTagsEnabled'](true);
  assert.equal(first.form.aiTagsProvider, P, 'panel init preselect');
  panel.destroy();
});
test('tags_model_memo_survives_switch_reload_and_fill', async () => {
  const groups = { [A]: group('A', ''), [B]: group('B', '') };
  const f = await makeFakeThis();
  await load(f, configWith(groups, 'ollama', P, 'm2'));
  f.openaiGroupRt[A].models = ['m1', 'm2']; f.openaiGroupRt[B].models = ['b1', 'b2'];
  const { panel } = await attachPanel(f);
  await select(f, panel, Q); await select(f, panel, P);
  assert.ok(f.form.aiTagsModel === 'm2', 'cold load');
  f.setTagsModel(P, 'm1');
  await select(f, panel, Q); await select(f, panel, P);
  assert.ok(f.form.aiTagsModel === 'm1', 'change event memo');
  await select(f, panel, Q); f.setTagsModel(Q, 'b2');
  await select(f, panel, P);
  const stored = configWith(groups, 'ollama', P, 'm1');
  await save(f, stored);
  await load(f, stored);
  await select(f, panel, Q);
  assert.ok(f.form.aiTagsModel === 'b2', 'same-page reload preserves other provider');
  f.setTagsModel(Q, '');
  assert.ok(f.tagsModelMemo[Q] === 'b2', 'empty model does not erase memo');
  f.tagsMemoClear();
  f.openaiModels = ['m2', 'later'];
  f.form.aiTagsProvider = Q;
  await f.openaiGroupRemove(B);
  assert.ok(f.form.aiTagsProvider === 'openai' && f.form.aiTagsModel === 'm2', 'delete fills default model');
  await select(f, panel, P);
  f.openaiModels = ['m1', 'm2'];
  await select(f, panel, 'openai');
  assert.ok(f.form.aiTagsModel === 'm2', 'fill is remembered after list changes');
  await select(f, panel, P); f.setTagsModel(P, 'm2');
  f.openaiGroupAdd('new B', 'tags', () => 0x89abcdef);
  assert.ok(f.form.aiTagsProvider === Q && f.form.aiTagsModel === '', 'add selects blank new group');
  await select(f, panel, P);
  assert.ok(f.form.aiTagsModel === 'm2', 'add preserves A memo');
  f.tagsMemoClear();
  assert.deepEqual(f.tagsModelMemo, {}, 'clear');
  f.setTagsModel(P, 'm1');
  const reset = configWith({}, 'ollama', '', '');
  globalThis.fetch = async (_url, opts) => opts?.method === 'DELETE'
    ? response({ success: true })
    : response({ success: true, data: structuredClone(reset) });
  await f.confirmResetConfig();
  await delayTimers();
  assert.deepEqual(f.tagsModelMemo, {}, 'confirm reset clears memo');
  await load(f, configWith({}, 'ollama', Q, 'stale'));
  assert.ok(f.form.aiTagsProvider === 'openai' && f.form.aiTagsModel === '', 'missing provider fallback');
});
