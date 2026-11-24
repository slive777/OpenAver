import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.t = (key) => key;
globalThis.document = {
    documentElement: { getAttribute: () => 'light' },
    createElement: () => ({
        className: '', contentEditable: 'true', spellcheck: false, dataset: {},
        childNodes: [], children: [], appendChild() {}, setAttribute() {},
        addEventListener() {}, removeEventListener() {},
    }),
    createTextNode: (t) => ({ nodeType: 3, textContent: t }),
    createDocumentFragment: () => ({ nodeType: 11, childNodes: [], lastChild: null, appendChild() {} }),
};
const root = pathToFileURL(path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../') + '/').href;
const loader = `
const root = ${JSON.stringify(root)};
export async function resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('@/settings/')) return nextResolve(root + 'pages/settings/' + specifier.slice(11), context);
    if (specifier.startsWith('@/')) return nextResolve(root + specifier.slice(2), context);
    return nextResolve(specifier, context);
}`;
register(`data:text/javascript,${encodeURIComponent(loader)}`, import.meta.url);
const { stateProviders } = await import('../state-providers.js');
const { stateOpenaiGroups } = await import('../state-openai-groups.js');

const cases = [
    ['ollama', 'ollama', 'ollamaModels', ['ollama-list', 'ollama-saved']],
    ['gemini', 'gemini', 'geminiModels', ['gemini-list', 'gemini-saved']],
    ['claude', 'claude', 'claudeModels', ['claude-list', 'claude-saved']],
    ['openai_official', 'openai_official', 'openaiOfficialModels', ['official-list', 'official-saved']],
    ['openai', 'openai', 'openaiModels', ['openai-list', 'openai-saved']],
    ['group', 'openai:oc12345678', null, ['group-list', 'group-saved']],
];
for (const [label, provider, listKey, expected] of cases) {
    test(`translate_model_options_pick_list_and_saved_per_provider[${label}]`, () => {
        const vm = Object.assign({}, stateProviders(), stateOpenaiGroups(), {
            form: {
                ollamaModel: 'ollama-saved', geminiModel: 'gemini-saved',
                claudeModel: 'claude-saved', openaiOfficialModel: 'official-saved',
                openaiModel: 'openai-saved', openaiGroups: [{ id: 'oc12345678', model: 'group-saved' }],
            },
            ollamaModels: ['ollama-list'], geminiModels: [{ name: 'gemini-list' }],
            claudeModels: ['claude-list'], openaiOfficialModels: ['official-list'],
            openaiModels: ['openai-list'], openaiGroupRt: { oc12345678: { models: ['group-list'] } },
        });
        const list = listKey ? vm[listKey] : vm.openaiGroupRt.oc12345678.models;
        const before = structuredClone(list);
        assert.deepEqual(vm.translateModelOptions(provider), expected);
        assert.deepEqual(list, before);
    });
}
