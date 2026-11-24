import { pickClaudeModel } from './claude-model-pick.js';
import { connShown, connEnabled, pickTagsModel, modelNamesWith } from '@/settings/ai-tags-logic.js';
import { openaiGroupIdOf } from './openai-group-logic.js';

export function stateProviders() {
    return {
        modelAutoLoad: { attempted: {}, inflight: {}, seeded: {} },
        // ===== Provider Status State =====
        ollamaStatus: '',
        modelStatus: '',
        geminiStatus: '',
        geminiModelStatus: '',
        ollamaModels: [],
        geminiModels: [],
        openaiStatus: '',
        openaiModelStatus: '',
        openaiModels: [],
        openaiUseCustomModel: false,
        fetchingOpenaiModels: false,
        testingOpenaiTranslate: false,
        claudeStatus: '',
        claudeModelStatus: '',
        claudeModels: [],
        fetchingClaudeModels: false,
        testingClaudeTranslate: false,
        openaiOfficialStatus: '',
        openaiOfficialModelStatus: '',
        openaiOfficialModels: [],
        fetchingOpenaiOfficialModels: false,
        testingOpenaiOfficialTranslate: false,

        // Test buttons loading state
        testOllamaLoading: false,
        testModelLoading: false,
        testGeminiLoading: false,
        testGeminiTranslateLoading: false,

        // ===== Methods =====
        async loadOllamaModels(url) {
            if (!url) return;

            this.ollamaStatus = `<span class="text-base-content/50">${window.t('settings.status.loading_models')}</span>`;

            try {
                const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
                const result = await resp.json();

                if (result.success && result.models && result.models.length > 0) {
                    this.ollamaModels = result.models;
                    this.modelsArrived('ollama');

                    this.ollamaStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.n_models', {count: result.models.length})}</span>`;
                } else {
                    this.ollamaStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${result.error || window.t('settings.status.connection_failed')}</span>`;
                }
            } catch (e) {
                this.ollamaStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${window.t('settings.status.connection_failed')}</span>`;
            }
        },

        async testOllamaConnection() {
            const url = this.form.ollamaUrl.trim();

            if (!url) {
                this.ollamaStatus = `<span class="text-error">${window.t('settings.status.enter_url')}</span>`;
                return;
            }

            this.modelAutoLoad.attempted.ollama = true;
            this.testOllamaLoading = true;
            this.ollamaStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
                const result = await resp.json();

                if (result.success && result.models && result.models.length > 0) {
                    this.ollamaModels = result.models;
                    this.modelsArrived('ollama');
                    this.form.ollamaModel = this.ollamaModels.includes(this.form.ollamaModel)
                        ? this.form.ollamaModel
                        : result.models[0];

                    this.ollamaStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: result.models.length})}</span>`;
                } else {
                    this.ollamaStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error || window.t('settings.status.no_models')}</span>`;
                }
            } catch (e) {
                this.ollamaStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
            } finally {
                this.testOllamaLoading = false;
            }
        },

        async testModel() {
            const url = this.form.ollamaUrl.trim();
            const model = this.form.ollamaModel;

            if (!url || !model) {
                this.modelStatus = `<span class="text-error">${window.t('settings.status.select_model')}</span>`;
                return;
            }

            this.testModelLoading = true;
            this.modelStatus = `<span class="text-base-content/50">${window.t('settings.status.testing')}</span>`;

            try {
                const resp = await fetch('/api/ollama/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, model })
                });
                const result = await resp.json();

                if (result.success) {
                    const escapeHtml = (text) => {
                        const div = document.createElement('div');
                        div.textContent = text;
                        return div.innerHTML;
                    };
                    if (result.result === 'ja_skip') {
                        this.modelStatus = `<span class="text-info"><i class="bi bi-info-circle"></i> ${window.t('settings.status.ja_skip')}</span>`;
                    } else {
                        this.modelStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${escapeHtml(result.result)}</span>`;
                    }
                } else {
                    this.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error}</span>`;
                }
            } catch (e) {
                this.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
            } finally {
                this.testModelLoading = false;
            }
        },

        async testGeminiConnection({ source = 'manual' } = {}) {
            const apiKey = this.secretWire('gemini');

            if (!apiKey) {
                this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key')}</span>`;
                return;
            }

            this.modelAutoLoad.attempted.gemini = true;
            this.testGeminiLoading = true;
            this.geminiStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const response = await fetch('/api/gemini/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });

                const data = await response.json();

                if (data.success) {
                    this.geminiStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: data.count})}</span>`;
                    this.geminiModels = data.models;
                    this.modelsArrived('gemini');

                    const modelNames = data.models.map(m => m.name);
                    const wasBlank = !this.form.geminiModel;
                    if ((source === 'manual' || wasBlank) && data.models.length > 0 && !modelNames.includes(this.form.geminiModel)) {
                        this.form.geminiModel = data.models[0].name;
                        if (wasBlank && this.savedState) this.savedState.geminiModel = this.form.geminiModel;
                    }
                } else {
                    const failClass = source === 'manual' ? 'text-error' : 'text-warning';
                    const failIcon = source === 'manual' ? 'bi-x-circle' : 'bi-exclamation-circle';
                    this.geminiStatus = `<span class="${failClass}"><i class="bi ${failIcon}"></i> ${data.error || window.t('settings.status.connect_failed')}</span>`;
                    if (source === 'manual') this.geminiModelStatus = '';
                }
            } catch (error) {
                this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${error.message}</span>`;
            } finally {
                this.testGeminiLoading = false;
            }
        },

        async testGeminiTranslation() {
            const apiKey = this.secretWire('gemini');
            const model = this.form.geminiModel;

            if (!apiKey) {
                this.geminiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key_first')}</span>`;
                return;
            }

            if (!model) {
                this.geminiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.select_model')}</span>`;
                return;
            }

            this.testGeminiTranslateLoading = true;
            this.geminiModelStatus = `<span class="text-base-content/50">${window.t('settings.status.testing_translation')}</span>`;

            try {
                const response = await fetch('/api/gemini/test-translate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        api_key: apiKey,
                        model: model
                    })
                });

                const data = await response.json();

                if (data.success) {
                    const escapeHtml = (text) => {
                        const div = document.createElement('div');
                        div.textContent = text;
                        return div.innerHTML;
                    };
                    if (data.translation === 'ja_skip') {
                        this.geminiModelStatus = `<span class="text-info"><i class="bi bi-info-circle"></i> ${window.t('settings.status.ja_skip')}</span>`;
                    } else {
                        this.geminiModelStatus = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> ${window.t('settings.status.translation_success', {translation: escapeHtml(data.translation)})}</span>`;
                    }
                } else {
                    const errorKey = `settings.status.gemini_${data.error || 'translate_failed'}`;
                    this.geminiModelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                this.geminiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.gemini_translate_failed')}</span>`;
            } finally {
                this.testGeminiTranslateLoading = false;
            }
        },

        async fetchOpenAIModels({ source = 'manual', groupId = '' } = {}) {
            if (groupId) {
                const group = this.openaiGroupById(groupId);
                const rt = this.openaiGroupRt[groupId];
                if (!group || !rt) return;
                const baseUrl = group.baseUrl.trim();
                if (!baseUrl) {
                    rt.status = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_url')}</span>`;
                    return;
                }
                this.modelAutoLoad.attempted['openai:' + groupId] = true;
                rt.fetching = true;
                rt.status = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;
                try {
                    const response = await fetch('/api/openai/models', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ base_url: baseUrl, api_key: this.secretWire(groupId), group_id: groupId })
                    });
                    const data = await response.json();
                    if (data.success && data.models && data.models.length > 0) {
                        rt.models = data.models;
                        this.modelsArrived('openai:' + groupId);
                        rt.status = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: data.models.length})}</span>`;
                        if (!data.models.includes(group.model)) {
                            if (group.model) {
                                if (source === 'manual') group.useCustomModel = true;
                            } else {
                                group.model = data.models[0];
                                const saved = this.savedState?.openaiGroups?.find(item => item.id === groupId);
                                if (saved) saved.model = group.model;
                            }
                        }
                    } else {
                        const errorKey = `settings.status.openai_${data.error || 'connection_failed'}`;
                        rt.status = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${window.t(errorKey)}</span>`;
                    }
                } catch (error) {
                    rt.status = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.openai_connection_failed')}</span>`;
                } finally {
                    rt.fetching = false;
                }
                return;
            }
            const baseUrl = this.form.openaiBaseUrl.trim();

            if (!baseUrl) {
                this.openaiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_url')}</span>`;
                return;
            }

            this.modelAutoLoad.attempted.openai = true;
            this.fetchingOpenaiModels = true;
            this.openaiStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const response = await fetch('/api/openai/models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        base_url: baseUrl,
                        api_key: this.secretWire('openai')
                    })
                });

                const data = await response.json();

                if (data.success && data.models && data.models.length > 0) {
                    this.openaiModels = data.models;
                    this.modelsArrived('openai');
                    this.openaiStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: data.models.length})}</span>`;

                    // model 不在清單中 → 切換到自訂模式（保留用戶的 custom model）
                    if (!this.openaiModels.includes(this.form.openaiModel)) {
                        if (this.form.openaiModel) {
                            if (source === 'manual') {
                                // 手動 Fetch：model 不在清單 → 切換 custom 模式（維持現有行為）
                                this.openaiUseCustomModel = true;
                            }
                            // source === 'auto'：不動 openaiUseCustomModel，保持 loadConfig 從 config 設的值
                        } else {
                            this.form.openaiModel = this.openaiModels[0];
                            // auto-assign 不算用戶修改，同步快照避免 isDirty 誤判
                            if (this.savedState) this.savedState.openaiModel = this.form.openaiModel;
                        }
                    }
                } else {
                    // 不清空 openaiModels — 保留舊清單
                    const errorKey = `settings.status.openai_${data.error || 'connection_failed'}`;
                    this.openaiStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                // 不清空 openaiModels — 保留舊清單
                this.openaiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.openai_connection_failed')}</span>`;
            } finally {
                this.fetchingOpenaiModels = false;
            }
        },

        async testOpenAITranslation({ groupId = '' } = {}) {
            if (groupId) {
                const group = this.openaiGroupById(groupId);
                const rt = this.openaiGroupRt[groupId];
                if (!group || !rt) return;
                const baseUrl = group.baseUrl.trim();
                const model = group.model.trim();
                if (!baseUrl || !model) {
                    const key = !baseUrl ? 'settings.status.enter_url' : 'settings.status.select_model';
                    rt.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t(key)}</span>`;
                    return;
                }
                rt.testing = true;
                rt.modelStatus = `<span class="text-base-content/50">${window.t('settings.status.testing_translation')}</span>`;
                try {
                    const response = await fetch('/api/openai/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ base_url: baseUrl, api_key: this.secretWire(groupId), group_id: groupId, model })
                    });
                    const data = await response.json();
                    if (data.success) {
                        const div = document.createElement('div');
                        div.textContent = data.translation;
                        rt.modelStatus = data.translation === 'ja_skip'
                            ? `<span class="text-info"><i class="bi bi-info-circle"></i> ${window.t('settings.status.ja_skip')}</span>`
                            : `<span class="text-success"><i class="bi bi-check-circle-fill"></i> ${div.innerHTML}</span>`;
                    } else {
                        const errorKey = `settings.status.openai_${data.error || 'translate_failed'}`;
                        rt.modelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${window.t(errorKey)}</span>`;
                    }
                } catch (error) {
                    rt.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.openai_translate_failed')}</span>`;
                } finally {
                    rt.testing = false;
                }
                return;
            }
            const baseUrl = this.form.openaiBaseUrl.trim();
            const model = this.form.openaiModel.trim();

            if (!baseUrl) {
                this.openaiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_url')}</span>`;
                return;
            }

            if (!model) {
                this.openaiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.select_model')}</span>`;
                return;
            }

            this.testingOpenaiTranslate = true;
            this.openaiModelStatus = `<span class="text-base-content/50">${window.t('settings.status.testing_translation')}</span>`;

            try {
                const response = await fetch('/api/openai/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        base_url: baseUrl,
                        api_key: this.secretWire('openai'),
                        model: model
                    })
                });

                const data = await response.json();

                if (data.success) {
                    const escapeHtml = (text) => {
                        const div = document.createElement('div');
                        div.textContent = text;
                        return div.innerHTML;
                    };
                    if (data.translation === 'ja_skip') {
                        this.openaiModelStatus = `<span class="text-info"><i class="bi bi-info-circle"></i> ${window.t('settings.status.ja_skip')}</span>`;
                    } else {
                        this.openaiModelStatus = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> ${escapeHtml(data.translation)}</span>`;
                    }
                } else {
                    const errorKey = `settings.status.openai_${data.error || 'translate_failed'}`;
                    this.openaiModelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                this.openaiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.openai_translate_failed')}</span>`;
            } finally {
                this.testingOpenaiTranslate = false;
            }
        },

        async fetchClaudeModels({ source = 'manual' } = {}) {
            const apiKey = this.secretWire('claude');

            if (!apiKey) {
                this.claudeStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key')}</span>`;
                return;
            }

            this.modelAutoLoad.attempted.claude = true;
            this.fetchingClaudeModels = true;
            this.claudeStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const response = await fetch('/api/claude/models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });

                const data = await response.json();

                if (data.success && data.models && data.models.length > 0) {
                    this.claudeModels = data.models;
                    this.modelsArrived('claude');
                    this.claudeStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: data.models.length})}</span>`;

                    if (source === 'manual') {
                        const wasBlank = !this.form.claudeModel;
                        const picked = pickClaudeModel(
                            this.form.claudeModel,
                            data.models,
                            data.latest_haiku,
                            data.default_model
                        );
                        if (picked !== this.form.claudeModel) {
                            this.form.claudeModel = picked;
                            if (wasBlank && this.savedState) this.savedState.claudeModel = this.form.claudeModel;
                        }
                    }
                } else {
                    // 不清空 claudeModels — 保留舊清單
                    const failClass = source === 'manual' ? 'text-error' : 'text-warning';
                    const failIcon = source === 'manual' ? 'bi-x-circle' : 'bi-exclamation-circle';
                    const errorKey = `settings.status.claude_${data.error || 'connection_failed'}`;
                    this.claudeStatus = `<span class="${failClass}"><i class="bi ${failIcon}"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                // 不清空 claudeModels — 保留舊清單
                this.claudeStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.claude_connection_failed')}</span>`;
            } finally {
                this.fetchingClaudeModels = false;
            }
        },

        async testClaudeTranslation() {
            const apiKey = this.secretWire('claude');
            const model = this.form.claudeModel;

            if (!apiKey) {
                this.claudeModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key_first')}</span>`;
                return;
            }

            if (!model) {
                this.claudeModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.select_model')}</span>`;
                return;
            }

            this.testingClaudeTranslate = true;
            this.claudeModelStatus = `<span class="text-base-content/50">${window.t('settings.status.testing_translation')}</span>`;

            try {
                const response = await fetch('/api/claude/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        api_key: apiKey,
                        model: model
                    })
                });

                const data = await response.json();

                if (data.success) {
                    const escapeHtml = (text) => {
                        const div = document.createElement('div');
                        div.textContent = text;
                        return div.innerHTML;
                    };
                    if (data.translation === 'ja_skip') {
                        this.claudeModelStatus = `<span class="text-info"><i class="bi bi-info-circle"></i> ${window.t('settings.status.ja_skip')}</span>`;
                    } else {
                        this.claudeModelStatus = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> ${window.t('settings.status.translation_success', {translation: escapeHtml(data.translation)})}</span>`;
                    }
                } else {
                    const errorKey = `settings.status.claude_${data.error || 'translate_failed'}`;
                    this.claudeModelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                this.claudeModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.claude_translate_failed')}</span>`;
            } finally {
                this.testingClaudeTranslate = false;
            }
        },

        async fetchOpenAIOfficialModels({ source = 'manual' } = {}) {
            const apiKey = this.secretWire('openaiOfficial');

            if (!apiKey) {
                this.openaiOfficialStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key')}</span>`;
                return;
            }

            this.modelAutoLoad.attempted.openai_official = true;
            this.fetchingOpenaiOfficialModels = true;
            this.openaiOfficialStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const response = await fetch('/api/openai/official/models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });

                const data = await response.json();

                if (data.success && data.models && data.models.length > 0) {
                    this.openaiOfficialModels = data.models;
                    this.modelsArrived('openai_official');
                    this.openaiOfficialStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: data.models.length})}</span>`;

                    const wasBlank = !this.form.openaiOfficialModel;
                    if (source === 'manual' || wasBlank) {
                        const picked = pickClaudeModel(
                            this.form.openaiOfficialModel,
                            data.models,
                            data.default_model,
                            ''
                        );
                        if (picked !== this.form.openaiOfficialModel) {
                            this.form.openaiOfficialModel = picked;
                            if (wasBlank && this.savedState) this.savedState.openaiOfficialModel = this.form.openaiOfficialModel;
                        }
                    }
                } else {
                    // 不清空 openaiOfficialModels — 保留舊清單
                    const failClass = source === 'manual' ? 'text-error' : 'text-warning';
                    const failIcon = source === 'manual' ? 'bi-x-circle' : 'bi-exclamation-circle';
                    const errorKey = `settings.status.openai_official_${data.error || 'connection_failed'}`;
                    this.openaiOfficialStatus = `<span class="${failClass}"><i class="bi ${failIcon}"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                // 不清空 openaiOfficialModels — 保留舊清單
                this.openaiOfficialStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.openai_official_connection_failed')}</span>`;
            } finally {
                this.fetchingOpenaiOfficialModels = false;
            }
        },

        async testOpenAIOfficialTranslation() {
            const apiKey = this.secretWire('openaiOfficial');
            const model = this.form.openaiOfficialModel;

            if (!apiKey) {
                this.openaiOfficialModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key_first')}</span>`;
                return;
            }

            if (!model) {
                this.openaiOfficialModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.select_model')}</span>`;
                return;
            }

            this.testingOpenaiOfficialTranslate = true;
            this.openaiOfficialModelStatus = `<span class="text-base-content/50">${window.t('settings.status.testing_translation')}</span>`;

            try {
                const response = await fetch('/api/openai/official/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        api_key: apiKey,
                        model: model
                    })
                });

                const data = await response.json();

                if (data.success) {
                    const escapeHtml = (text) => {
                        const div = document.createElement('div');
                        div.textContent = text;
                        return div.innerHTML;
                    };
                    if (data.translation === 'ja_skip') {
                        this.openaiOfficialModelStatus = `<span class="text-info"><i class="bi bi-info-circle"></i> ${window.t('settings.status.ja_skip')}</span>`;
                    } else {
                        this.openaiOfficialModelStatus = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> ${window.t('settings.status.translation_success', {translation: escapeHtml(data.translation)})}</span>`;
                    }
                } else {
                    const errorKey = `settings.status.openai_official_${data.error || 'translate_failed'}`;
                    this.openaiOfficialModelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${window.t(errorKey)}</span>`;
                }
            } catch (error) {
                this.openaiOfficialModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.openai_official_translate_failed')}</span>`;
            } finally {
                this.testingOpenaiOfficialTranslate = false;
            }
        },

        // ===== AI tags（188c-T8a）=====
        modelsArrived(provider) {
            delete this.modelAutoLoad.seeded[provider];
            this.tagsPreselect(provider);
        },

        tagsPreselect(provider) {
            if (this.form.aiTagsProvider === provider && !this.form.aiTagsModel) {
                this.setTagsModel(provider, pickTagsModel(provider, '', this.aiTagsModelLists()[provider] || []));
            }
        },

        aiTagsModelLists() {
            const lists = this.allModelLists();
            for (const provider of Object.keys(this.modelAutoLoad.seeded)) lists[provider] = [];
            return lists;
        },

        allModelLists() {
            return {
                ollama: this.ollamaModels,
                gemini: this.geminiModels,
                claude: this.claudeModels,
                openai_official: this.openaiOfficialModels,
                openai: this.openaiModels,
                ...this.openaiGroupModelLists(),
            };
        },

        translateModelOptions(provider) {
            const values = {
                ollama: this.form.ollamaModel,
                gemini: this.form.geminiModel,
                claude: this.form.claudeModel,
                openai_official: this.form.openaiOfficialModel,
                openai: this.form.openaiModel,
            };
            const groupId = openaiGroupIdOf(provider);
            const current = groupId ? this.openaiGroupById(groupId)?.model : (Object.hasOwn(values, provider) ? values[provider] : undefined);
            return modelNamesWith(this.allModelLists()[provider], current);
        },

        // tab 由模板傳入（aiTab 住在巢狀 aiServicesCard，root 讀不到）
        aiConnShown(p, tab) {
            return connShown(this.form, p, tab);
        },

        aiConnEnabled(p) {
            return connEnabled(this.form, p);
        },

        async autoLoadModels(provider) {
            if (this.modelAutoLoad.attempted[provider]) return this.modelAutoLoad.inflight[provider];
            const groupId = openaiGroupIdOf(provider);
            const group = groupId && this.openaiGroupById(groupId);
            let fetchModels;
            if (groupId && group?.baseUrl.trim()) {
                fetchModels = () => this.fetchOpenAIModels({ source: 'auto', groupId });
            } else if (provider === 'ollama' && this.form.ollamaUrl.trim()) {
                fetchModels = () => this.loadOllamaModels(this.form.ollamaUrl);
            } else if (provider === 'gemini' && this.secretHasValue('gemini')) {
                fetchModels = () => this.testGeminiConnection({ source: 'auto' });
            } else if (provider === 'claude' && this.secretHasValue('claude')) {
                fetchModels = () => this.fetchClaudeModels({ source: 'auto' });
            } else if (provider === 'openai_official' && this.secretHasValue('openaiOfficial')) {
                fetchModels = () => this.fetchOpenAIOfficialModels({ source: 'auto' });
            } else if (provider === 'openai' && this.form.openaiBaseUrl.trim()) {
                fetchModels = () => this.fetchOpenAIModels({ source: 'auto' });
            }
            if (!fetchModels) return;
            this.modelAutoLoad.attempted[provider] = true;
            this.modelAutoLoad.inflight[provider] = Promise.resolve().then(fetchModels).catch(() => {});
            return this.modelAutoLoad.inflight[provider];
        },

        async ensureProviderModels(provider) {
            await this.autoLoadModels(provider);

            // FE-TIMING-16：await 後再讀 form；provider 已換或 model 已有 → 不寫。
            // 已存 model 空時預選不進 savedState：畫面 isDirty=true，引導使用者存一次（CD-188c-14）。
            this.tagsPreselect(provider);
        },
    };
}
