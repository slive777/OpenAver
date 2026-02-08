// Settings 頁面 Alpine.js 元件
function settingsPage() {
    return {
        // ===== Form State =====
        form: {
            // Search
            galleryModeEnabled: false,
            uncensoredModeEnabled: false,
            searchFavoriteFolder: '',

            // Translate
            translateEnabled: false,
            translateProvider: 'ollama',
            ollamaUrl: 'http://localhost:11434',
            ollamaModel: '',
            geminiApiKey: '',
            geminiModel: '',

            // Scraper
            createFolder: true,
            folderLayer1: '',
            folderLayer2: '',
            folderLayer3: '{num}',
            filenameFormat: '[{num}][{maker}] {title}',
            maxTitleLength: 80,
            maxFilenameLength: 200,
            videoExtensions: '.mp4, .avi, .mkv, .wmv, .rmvb, .flv, .mov, .m4v, .ts',

            // Gallery
            avlistMode: 'image',
            avlistSort: 'date',
            avlistOrder: 'descending',
            avlistItemsPerPage: 90,
            avlistMinSize: 0,
            avlistOutputDir: 'output',
            avlistOutputFilename: 'gallery_output.html',

            // Showcase
            viewerPlayer: '',

            // General
            defaultPage: 'search',
            sidebarCollapsed: false
        },

        // ===== UI State =====
        ollamaStatus: '',
        modelStatus: '',
        geminiStatus: '',
        geminiModelStatus: '',
        ollamaModels: [],
        geminiModels: [],
        appVersion: '載入中...',
        updateStatus: '',

        // ===== Constants =====
        formatVariables: [
            { name: '{num}', description: '番號', example: 'SONE-205' },
            { name: '{title}', description: '標題', example: '新人出道...' },
            { name: '{actor}', description: '演員（第一位）', example: '三上悠亜' },
            { name: '{actors}', description: '所有演員', example: '三上悠亜, 明日花' },
            { name: '{maker}', description: '片商', example: 'S1' },
            { name: '{date}', description: '發行日期', example: '2024-01-15' },
            { name: '{year}', description: '年份', example: '2024' }
        ],
        folderVariables: [
            { name: '{num}' },
            { name: '{actor}' },
            { name: '{maker}' },
            { name: '{title}' },
            { name: '{year}' }
        ],
        FOLDER_PREVIEW_DATA: {
            num: 'SSNI-618',
            maker: 'SOD',
            actor: '三上悠亞',
            actors: '三上悠亞, 明日花',
            title: '絕對領域',
            date: '2024-01-15',
            year: '2024'
        },

        // ===== Computed Properties =====
        get layer3Enabled() {
            return this.form.createFolder;
        },
        get layer2Enabled() {
            return this.form.createFolder && !!this.form.folderLayer3.trim();
        },
        get layer1Enabled() {
            return this.form.createFolder && !!this.form.folderLayer2.trim();
        },
        get folderPreviewText() {
            const filenameFormat = this.form.filenameFormat || '{num} {title}';
            let filenamePreview = filenameFormat;
            for (const [key, val] of Object.entries(this.FOLDER_PREVIEW_DATA)) {
                filenamePreview = filenamePreview.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
            }

            if (!this.form.createFolder) {
                return filenamePreview + '.mp4';
            }

            const layers = [
                this.form.folderLayer1.trim(),
                this.form.folderLayer2.trim(),
                this.form.folderLayer3.trim()
            ].filter(v => v);

            let folderPreview = layers.map(layer => {
                let part = layer;
                for (const [key, val] of Object.entries(this.FOLDER_PREVIEW_DATA)) {
                    part = part.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
                }
                return part;
            }).join('/');

            const folder = folderPreview ? folderPreview + '/' : '';
            return folder + filenamePreview + '.mp4';
        },

        // ===== Lifecycle =====
        init() {
            this.loadConfig();
            this.loadVersion();

            // Watch for form changes
            this.$watch('form.translateEnabled', () => this.updateTranslateOptions());
            this.$watch('form.translateProvider', () => this.onTranslateProviderChange());
            this.$watch('form.folderLayer3', (newVal, oldVal) => {
                if (!newVal.trim() && oldVal && oldVal.trim()) {
                    this.form.folderLayer2 = '';
                    this.form.folderLayer1 = '';
                }
            });
            this.$watch('form.folderLayer2', (newVal, oldVal) => {
                if (!newVal.trim() && oldVal && oldVal.trim()) {
                    this.form.folderLayer1 = '';
                }
            });
        },

        // ===== Methods =====
        async loadConfig() {
            try {
                const resp = await fetch('/api/config');
                const result = await resp.json();
                if (result.success) {
                    const config = result.data;

                    // Search
                    this.form.galleryModeEnabled = config.search?.gallery_mode_enabled || false;
                    this.form.uncensoredModeEnabled = config.search?.uncensored_mode_enabled || false;
                    this.form.searchFavoriteFolder = config.search?.favorite_folder || '';

                    // Translate
                    this.form.translateEnabled = config.translate.enabled;
                    this.form.translateProvider = config.translate.provider || 'ollama';
                    this.form.ollamaUrl = config.translate.ollama?.url || config.translate.ollama_url || 'http://localhost:11434';
                    this.form.geminiApiKey = config.translate.gemini?.api_key || '';

                    // Gemini model 預設填入
                    if (config.translate.gemini?.model) {
                        this.geminiModels = [{ name: config.translate.gemini.model }];
                        this.form.geminiModel = config.translate.gemini.model;
                    }

                    // 自動測試 Gemini（如果有 API Key 且是 gemini provider）
                    if (config.translate.gemini?.api_key && config.translate.provider === 'gemini') {
                        setTimeout(() => this.testGeminiConnection(), 100);
                    }

                    // Scraper
                    this.form.createFolder = config.scraper.create_folder;
                    const layers = config.scraper.folder_layers || [];
                    if (layers.length >= 1) this.form.folderLayer3 = layers[layers.length - 1] || '';
                    if (layers.length >= 2) this.form.folderLayer2 = layers[layers.length - 2] || '';
                    if (layers.length >= 3) this.form.folderLayer1 = layers[layers.length - 3] || '';
                    // 向後兼容：沒有 folder_layers 時從 folder_format 讀取
                    if (layers.length === 0 && config.scraper.folder_format) {
                        this.form.folderLayer3 = config.scraper.folder_format;
                    }

                    this.form.filenameFormat = config.scraper.filename_format;
                    this.form.maxTitleLength = config.scraper.max_title_length;
                    this.form.maxFilenameLength = config.scraper.max_filename_length;
                    this.form.videoExtensions = config.scraper.video_extensions.join(', ');

                    // Gallery
                    this.form.avlistMode = config.gallery?.default_mode || 'image';
                    this.form.avlistSort = config.gallery?.default_sort || 'date';
                    this.form.avlistOrder = config.gallery?.default_order || 'descending';
                    this.form.avlistItemsPerPage = config.gallery?.items_per_page || 90;
                    this.form.avlistMinSize = config.gallery?.min_size_mb || 0;
                    this.form.avlistOutputDir = config.gallery?.output_dir || 'output';
                    this.form.avlistOutputFilename = config.gallery?.output_filename || 'gallery_output.html';

                    // Showcase
                    this.form.viewerPlayer = config.showcase?.player || '';

                    // General
                    let defaultPage = config.general?.default_page || 'search';
                    if (defaultPage === 'gallery') defaultPage = 'scanner';  // 向後兼容
                    this.form.defaultPage = defaultPage;
                    this.form.sidebarCollapsed = config.general?.sidebar_collapsed || false;

                    // 自動載入 Ollama 模型列表
                    const ollamaUrl = config.translate.ollama?.url || config.translate.ollama_url;
                    const ollamaModel = config.translate.ollama?.model || config.translate.ollama_model;
                    if (ollamaUrl && config.translate.provider === 'ollama') {
                        await this.loadOllamaModels(ollamaUrl, ollamaModel);
                    }
                }
            } catch (e) {
                console.error('載入設定失敗:', e);
            }
        },

        async saveConfig() {
            try {
                // 先載入現有設定
                const currentResp = await fetch('/api/config');
                const currentResult = await currentResp.json();
                if (!currentResult.success) {
                    this.showToast('載入現有設定失敗', 'error');
                    return;
                }
                const config = currentResult.data;

                // 更新 scraper
                const folderLayers = [
                    this.form.folderLayer1.trim(),
                    this.form.folderLayer2.trim(),
                    this.form.folderLayer3.trim()
                ].filter(v => v);

                config.scraper = {
                    ...config.scraper,
                    create_folder: this.form.createFolder,
                    folder_layers: folderLayers,
                    folder_format: folderLayers.join('/') || '{num}',
                    filename_format: this.form.filenameFormat,
                    max_title_length: this.form.maxTitleLength,
                    max_filename_length: this.form.maxFilenameLength,
                    video_extensions: this.form.videoExtensions
                        .split(',').map(s => s.trim()).filter(s => s)
                };

                // 更新 search
                config.search = {
                    ...config.search,
                    gallery_mode_enabled: this.form.galleryModeEnabled,
                    uncensored_mode_enabled: this.form.uncensoredModeEnabled,
                    favorite_folder: this.form.searchFavoriteFolder.trim()
                };

                // 更新 translate
                config.translate = {
                    ...config.translate,
                    enabled: this.form.translateEnabled,
                    provider: this.form.translateProvider,
                    ollama: {
                        url: this.form.ollamaUrl,
                        model: this.form.ollamaModel
                    },
                    gemini: {
                        api_key: this.form.geminiApiKey,
                        model: this.form.geminiModel || 'gemini-flash-lite-latest'
                    }
                };

                // 更新 gallery
                config.gallery = {
                    ...config.gallery,
                    default_mode: this.form.avlistMode,
                    default_sort: this.form.avlistSort,
                    default_order: this.form.avlistOrder,
                    items_per_page: this.form.avlistItemsPerPage,
                    min_size_mb: this.form.avlistMinSize || 0,
                    output_dir: this.form.avlistOutputDir.trim() || 'output',
                    output_filename: this.form.avlistOutputFilename.trim() || 'gallery_output.html'
                };

                // 更新 showcase
                config.showcase = {
                    ...config.showcase,
                    player: this.form.viewerPlayer.trim()
                };

                // 更新 general
                config.general = {
                    ...config.general,
                    default_page: this.form.defaultPage,
                    theme: this.theme || localStorage.getItem('theme') || 'light',
                    sidebar_collapsed: this.form.sidebarCollapsed
                };

                const resp = await fetch('/api/config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                const result = await resp.json();
                if (result.success) {
                    this.showToast('設定已儲存', 'success');
                } else {
                    this.showToast('儲存失敗: ' + result.error, 'error');
                }
            } catch (e) {
                this.showToast('儲存失敗: ' + e.message, 'error');
            }
        },

        updateTranslateOptions() {
            if (this.form.translateEnabled) {
                this.onTranslateProviderChange();
            }
        },

        onTranslateProviderChange() {
            // x-show already handles visibility logic
        },

        async loadOllamaModels(url, savedModel = '') {
            if (!url) return;

            this.ollamaStatus = '<span style="color: var(--text-muted);">載入模型中...</span>';

            try {
                const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
                const result = await resp.json();

                if (result.success && result.models && result.models.length > 0) {
                    this.ollamaModels = result.models;

                    // 設定儲存的模型
                    if (savedModel && result.models.includes(savedModel)) {
                        this.form.ollamaModel = savedModel;
                    } else if (result.models.length > 0) {
                        this.form.ollamaModel = result.models[0];
                    }

                    this.ollamaStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${result.models.length} 個模型</span>`;
                } else {
                    this.ollamaStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${result.error || '無法連線'}</span>`;
                }
            } catch (e) {
                this.ollamaStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> 無法連線</span>`;
            }
        },

        async testOllamaConnection() {
            const url = this.form.ollamaUrl.trim();

            if (!url) {
                this.ollamaStatus = '<span class="text-error">請輸入 URL</span>';
                return;
            }

            const btn = document.getElementById('testOllamaBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
            this.ollamaStatus = '<span style="color: var(--text-muted);">連線中...</span>';

            try {
                const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
                const result = await resp.json();

                if (result.success && result.models && result.models.length > 0) {
                    this.ollamaModels = result.models;
                    this.form.ollamaModel = this.ollamaModels.includes(this.form.ollamaModel)
                        ? this.form.ollamaModel
                        : result.models[0];

                    this.ollamaStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> 已連線，${result.models.length} 個模型</span>`;
                } else {
                    this.ollamaStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error || '無可用模型'}</span>`;
                    this.ollamaModels = [];
                }
            } catch (e) {
                this.ollamaStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
                this.ollamaModels = [];
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-plug"></i> 測試';
            }
        },

        async testModel() {
            const url = this.form.ollamaUrl.trim();
            const model = this.form.ollamaModel;

            if (!url || !model) {
                this.modelStatus = '<span class="text-error">請先選擇模型</span>';
                return;
            }

            const btn = document.getElementById('testModelBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
            this.modelStatus = '<span style="color: var(--text-muted);">測試中...</span>';

            try {
                const resp = await fetch('/api/ollama/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, model })
                });
                const result = await resp.json();

                if (result.success) {
                    this.modelStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${result.result}</span>`;
                } else {
                    this.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error}</span>`;
                }
            } catch (e) {
                this.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-chat-dots"></i> 測試';
            }
        },

        async testGeminiConnection() {
            const apiKey = this.form.geminiApiKey;

            if (!apiKey) {
                this.geminiStatus = '<span class="text-error"><i class="bi bi-x-circle"></i> 請輸入 API Key</span>';
                return;
            }

            const testBtn = document.getElementById('testGeminiBtn');
            testBtn.disabled = true;
            testBtn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
            this.geminiStatus = '<span style="color: var(--text-muted);">連線中...</span>';

            try {
                const response = await fetch('/api/gemini/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });

                const data = await response.json();

                if (data.success) {
                    this.geminiStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> 找到 ${data.count} 個 Flash 模型</span>`;
                    this.geminiModels = data.models;

                    // Set first model as default if none selected
                    if (!this.form.geminiModel && data.models.length > 0) {
                        this.form.geminiModel = data.models[0].name;
                    }
                } else {
                    this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${data.error || '連接失敗'}</span>`;
                    this.geminiModels = [];
                    this.geminiModelStatus = '';
                }
            } catch (error) {
                this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${error.message}</span>`;
            } finally {
                testBtn.disabled = false;
                testBtn.innerHTML = '<i class="bi bi-plug"></i> 測試';
            }
        },

        async testGeminiTranslation() {
            const apiKey = this.form.geminiApiKey;
            const model = this.form.geminiModel;

            if (!apiKey) {
                this.geminiModelStatus = '<span class="text-error"><i class="bi bi-x-circle"></i> 請先輸入 API Key</span>';
                return;
            }

            if (!model) {
                this.geminiModelStatus = '<span class="text-error"><i class="bi bi-x-circle"></i> 請先選擇模型</span>';
                return;
            }

            const testBtn = document.getElementById('testGeminiTranslateBtn');
            testBtn.disabled = true;
            testBtn.innerHTML = '<span class="loading loading-spinner loading-sm"></span>';
            this.geminiModelStatus = '<span style="color: var(--text-muted);">測試翻譯中...</span>';

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
                    this.geminiModelStatus = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> 翻譯測試成功！ (${data.translation})</span>`;
                } else {
                    this.geminiModelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${data.error}</span>`;
                }
            } catch (error) {
                this.geminiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> 測試失敗: ${error.message}</span>`;
            } finally {
                testBtn.disabled = false;
                testBtn.innerHTML = '<i class="bi bi-chat-dots"></i> 測試';
            }
        },

        async selectOutputFolder() {
            if (typeof window.pywebview === 'undefined' || !window.pywebview.api) {
                alert('此功能需要在桌面應用程式中使用');
                return;
            }

            try {
                const result = await window.pywebview.api.select_folder();
                if (result && result.folder) {
                    this.form.avlistOutputDir = result.folder;
                }
            } catch (e) {
                console.error('選擇資料夾失敗:', e);
            }
        },

        async resetConfig() {
            if (confirm('確定要重置所有設定嗎？此操作將刪除所有自訂設定。')) {
                try {
                    const resp = await fetch('/api/config', { method: 'DELETE' });
                    const result = await resp.json();
                    if (result.success) {
                        await this.loadConfig();
                        this.showToast('已恢復預設設定', 'success');
                    } else {
                        this.showToast('重置失敗: ' + result.error, 'error');
                    }
                } catch (e) {
                    this.showToast('重置失敗: ' + e.message, 'error');
                }
            }
        },

        restartTutorial() {
            window.location.href = '/search?tutorial=restart';
        },

        async checkUpdate() {
            const btn = document.getElementById('btnCheckUpdate');

            btn.disabled = true;
            btn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i> 檢查中...';
            this.updateStatus = '';

            try {
                const resp = await fetch('/api/check-update');
                const data = await resp.json();

                if (data.success) {
                    if (data.has_update) {
                        this.updateStatus = `<a href="${data.download_url}" target="_blank" class="text-success">
                            <i class="bi bi-download"></i> 新版本 ${data.latest_version} 可用
                        </a>`;
                    } else {
                        this.updateStatus = '<span style="color: var(--text-muted);"><i class="bi bi-check-circle"></i> 已是最新版本</span>';
                    }
                } else {
                    this.updateStatus = `<span class="text-error"><i class="bi bi-exclamation-circle"></i> ${data.error || '檢查失敗'}</span>`;
                }
            } catch (e) {
                this.updateStatus = '<span class="text-error"><i class="bi bi-exclamation-circle"></i> 網路錯誤</span>';
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-cloud-download"></i> 檢查更新';
            }
        },

        async loadVersion() {
            try {
                const resp = await fetch('/api/version');
                const data = await resp.json();
                if (data.success) {
                    this.appVersion = `v${data.version}`;
                }
            } catch (e) {
                this.appVersion = '無法載入';
            }
        },

        insertVariable(targetField, varName) {
            const input = document.getElementById(targetField);
            const cursorPos = input.selectionStart;
            const textBefore = this.form[targetField].substring(0, cursorPos);
            const textAfter = this.form[targetField].substring(cursorPos);
            this.form[targetField] = textBefore + varName + textAfter;

            this.$nextTick(() => {
                input.focus();
                input.setSelectionRange(cursorPos + varName.length, cursorPos + varName.length);
            });
        },

        appendVariable(targetField, varName) {
            this.form[targetField] += varName;
        },

        showToast(message, type = 'success') {
            const toastContainer = document.getElementById('toastContainer');
            if (!toastContainer) {
                console.warn('Toast container not found');
                return;
            }

            const toast = document.createElement('div');
            toast.className = `alert alert-${type}`;
            toast.innerHTML = `
                <div class="flex items-center gap-2">
                    <span class="flex-1">${message}</span>
                    <button type="button" class="btn btn-sm btn-circle btn-ghost" onclick="this.parentElement.parentElement.remove()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            `;

            toastContainer.appendChild(toast);

            // 3 秒後自動移除
            setTimeout(() => {
                if (toast.parentElement) {
                    toast.remove();
                }
            }, 3000);
        }
    };
}
