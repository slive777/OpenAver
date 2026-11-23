import { openaiGroupIdOf, newGroupId, newGroupDraft, fallbackAfterDelete } from './openai-group-logic.js';

const newRuntime = () => ({ models: [], status: '', modelStatus: '', fetching: false, testing: false });
const text = value => typeof value === 'string' ? value : '';

export function stateOpenaiGroups() {
    return {
        tagsModelMemo: {},
        openaiGroupRt: {},
        openaiGroupById(gid) {
            return this.form.openaiGroups.find(group => group.id === gid) || null;
        },
        openaiGroupAdd(name, tab, rand) {
            const gid = newGroupId(rand);
            this.form.openaiGroups.push({ id: gid, name, ...newGroupDraft() });
            this.secretFieldAdd(gid);
            this.openaiGroupRt[gid] = newRuntime();
            const provider = 'openai:' + gid;
            if (tab === 'translate') this.form.translateProvider = provider;
            if (tab === 'tags') {
                this.form.aiTagsProvider = provider;
                this.setTagsModel(provider, '');
            }
            return gid;
        },
        async openaiGroupRemove(gid) {
            const selected = this.form.aiTagsProvider === 'openai:' + gid;
            this.form.openaiGroups = this.form.openaiGroups.filter(group => group.id !== gid);
            this.form.translateProvider = fallbackAfterDelete(this.form.translateProvider, gid);
            if (selected) {
                this.form.aiTagsProvider = 'openai';
                this.setTagsModel('openai', this.tagsModelMemo.openai ?? '');
            }
            delete this.tagsModelMemo['openai:' + gid];
            delete this.openaiGroupRt[gid];
            this.secretFieldRemove(gid);
            if (selected) await this.ensureProviderModels('openai');
        },
        openaiGroupsLoad(config) {
            const custom = config.translate?.openai_custom;
            const entries = custom && typeof custom === 'object' && !Array.isArray(custom) ? Object.entries(custom) : [];
            this.form.openaiGroups = entries.filter(([id, value]) =>
                openaiGroupIdOf('openai:' + id) === id && value && typeof value === 'object' && !Array.isArray(value)
            ).map(([id, value]) => ({
                id, name: text(value.name), baseUrl: text(value.base_url), model: text(value.model),
                useCustomModel: value.use_custom_model === true,
            }));
            const ids = new Set(this.form.openaiGroups.map(group => group.id));
            for (const id of Object.keys(this.openaiGroupRt)) if (!ids.has(id)) delete this.openaiGroupRt[id];
            for (const id of Object.keys(this.secretFields)) {
                if (openaiGroupIdOf('openai:' + id) && !ids.has(id)) this.secretFieldRemove(id);
            }
            for (const id of ids) {
                if (!this.openaiGroupRt[id]) this.openaiGroupRt[id] = newRuntime();
                if (!this.secretFields[id]) this.secretFieldAdd(id);
            }
            let translateProvider = config.translate?.provider || 'ollama';
            let tagsProvider = config.ai_services?.tags?.provider || '';
            let tagsModel = config.ai_services?.tags?.model || '';
            if (translateProvider.startsWith('openai:') && !ids.has(openaiGroupIdOf(translateProvider))) translateProvider = 'openai';
            if (tagsProvider.startsWith('openai:') && !ids.has(openaiGroupIdOf(tagsProvider))) {
                tagsProvider = 'openai';
                tagsModel = '';
            }
            this.form.translateProvider = translateProvider;
            this.tagsMemoPrune(Object.keys(this.aiTagsModelLists()));
            this.form.aiTagsProvider = tagsProvider;
            this.setTagsModel(tagsProvider, tagsModel);
        },
        openaiGroupsPayload() {
            return Object.fromEntries(this.form.openaiGroups.map(group => [group.id, {
                name: group.name, base_url: group.baseUrl.trim(), model: group.model,
                use_custom_model: group.useCustomModel, api_key: '',
            }]));
        },
        async openaiGroupsAutoFetch() {
            const translateId = openaiGroupIdOf(this.form.translateProvider);
            const tagsId = openaiGroupIdOf(this.form.aiTagsProvider);
            const translate = this.openaiGroupById(translateId);
            const tags = this.openaiGroupById(tagsId);
            if (translate?.baseUrl) {
                await this.fetchOpenAIModels({ source: 'auto', groupId: translateId });
                if (tagsId === translateId) await this.ensureProviderModels('openai:' + tagsId);
            } else if (tags?.baseUrl && tagsId === translateId) {
                await this.ensureProviderModels('openai:' + tagsId);
            }
            if (tags?.baseUrl && tagsId !== translateId) await this.ensureProviderModels('openai:' + tagsId);
        },
        openaiGroupModelLists() {
            return Object.fromEntries(this.form.openaiGroups.map(group => ['openai:' + group.id, this.openaiGroupRt[group.id]?.models || []]));
        },
        setTagsModel(provider, model) {
            this.form.aiTagsModel = model;
            if (provider && model) this.tagsModelMemo[provider] = model;
        },
        tagsMemoPrune(validProviders) {
            for (const provider of Object.keys(this.tagsModelMemo)) {
                if (!validProviders.includes(provider)) delete this.tagsModelMemo[provider];
            }
        },
        tagsMemoClear() {
            this.tagsModelMemo = {};
        },
    };
}
