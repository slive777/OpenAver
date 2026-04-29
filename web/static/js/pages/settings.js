// Settings 頁面 Alpine.js 元件
function settingsPage() {
    return {
        // ===== Form State =====
        form: {
            // Search
            uncensoredModeEnabled: false,
            searchFavoriteFolder: '',
            proxyUrl: '',
            primarySource: 'javbus',

            // Translate
            translateEnabled: false,
            translateProvider: 'ollama',
            ollamaUrl: 'http://localhost:11434',
            ollamaModel: '',
            geminiApiKey: '',
            geminiModel: '',
            openaiBaseUrl: '',
            openaiApiKey: '',
            openaiModel: 'gpt-4o-mini',

            // Scraper
            createFolder: true,
            folderLayer1: '',
            folderLayer2: '',
            folderLayer3: '{num}',
            filenameFormat: '[{num}][{maker}] {title}',
            maxTitleLength: 80,
            maxFilenameLength: 200,
            videoExtensions: '.mp4, .avi, .mkv, .wmv, .rmvb, .flv, .mov, .m4v, .ts',
            suffixKeywords: [],
            jellyfinMode: false,
            downloadSampleImages: false,

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
            defaultPage: 'search'
        },

        // ===== i18n State =====
        locale: (window.__locale || 'zh-TW'),

        // ===== UI State =====
        newSuffixInput: '',
        showPathHelp: false,
        showSampleImagesHelp: false,
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
        // Toast state
        _toast: { message: '', type: 'success', visible: false },
        _toastTimer: null,

        // Test buttons loading state
        testOllamaLoading: false,
        testModelLoading: false,
        testGeminiLoading: false,
        testGeminiTranslateLoading: false,
        proxyStatus: '',
        proxyStatusOk: false,
        testProxyLoading: false,

        // Dirty Check Modal State
        dirtyCheckModalOpen: false,

        // Reset Config Modal State (T3.4)
        resetConfigModalOpen: false,
        _resetConfigLoading: false,

        // ===== Dirty Check State =====
        savedState: null,
        savedOpenaiUseCustomModel: false,
        pendingNavigationUrl: '',
        _configLoading: true,  // 初始 true，loadConfig 完成後 false

        // ===== Constants =====

        // 來源分群常數（與 core/scrapers/utils.py 同步）
        CENSORED_SOURCES: ['dmm', 'javbus', 'jav321', 'javdb'],
        UNCENSORED_SOURCES: ['d2pass', 'heyzo', 'fc2', 'avsox'],
        SOURCE_NAMES: {
            'dmm':     'DMM',
            'javbus':  'JavBus',
            'jav321':  'Jav321',
            'javdb':   'JavDB',
            'd2pass':  'D2Pass',
            'heyzo':   'HEYZO',
            'fc2':     'FC2',
            'avsox':   'AVSOX',
        },

        get formatVariables() {
            return [
                { name: '{num}', label: window.t('settings.var.num') },
                { name: '{title}', label: window.t('settings.var.title') },
                { name: '{actor}', label: window.t('settings.var.actor') },
                { name: '{actors}', label: window.t('settings.var.actors') },
                { name: '{maker}', label: window.t('settings.var.maker') },
                { name: '{date}', label: window.t('settings.var.date') },
                { name: '{year}', label: window.t('settings.var.year') },
                { name: '{month}', label: window.t('settings.var.month') },
                { name: '{day}', label: window.t('settings.var.day') },
                { name: '{suffix}', label: window.t('settings.var.suffix') },
            ];
        },
        get folderVariables() {
            return [
                { name: '{num}', label: window.t('settings.var.num') },
                { name: '{actor}', label: window.t('settings.var.actor') },
                { name: '{maker}', label: window.t('settings.var.maker') },
                { name: '{title}', label: window.t('settings.var.title') },
                { name: '{date}', label: window.t('settings.var.date') },
                { name: '{year}', label: window.t('settings.var.year') },
                { name: '{month}', label: window.t('settings.var.month') },
                { name: '{day}', label: window.t('settings.var.day') },
                { name: '{suffix}', label: window.t('settings.var.suffix') },
            ];
        },
        FOLDER_PREVIEW_DATA: {
            num: 'SSNI-618',
            maker: 'SOD',
            actor: '三上悠亞',
            actors: '三上悠亞, 明日花',
            title: '絕對領域',
            date: '2024-01-15',
            year: '2024',
            month: '01',
            day: '15',
            suffix: '-4k',
        },

        // ===== Computed Properties =====
        get isDirty() {
            if (this._configLoading) return false;
            if (!this.savedState) return false;
            return JSON.stringify(this.form) !== JSON.stringify(this.savedState)
                || this.openaiUseCustomModel !== this.savedOpenaiUseCustomModel;
        },

        /**
         * 來源是否啟用（決定 badge 亮度）
         * - 有碼來源：無碼模式關閉時啟用
         * - 無碼來源：無碼模式開啟時啟用
         * - DMM：有碼模式 + proxy 有值才亮
         */
        isSourceActive(src) {
            const isUncensored = this.UNCENSORED_SOURCES.includes(src);
            if (isUncensored) {
                return this.form.uncensoredModeEnabled;
            }
            if (src === 'dmm') {
                return !this.form.uncensoredModeEnabled && !!this.form.proxyUrl.trim();
            }
            return !this.form.uncensoredModeEnabled;
        },

        /**
         * DMM 是否可用（proxy_url 非空）
         * 控制 source-dmm-disabled class（刪除線樣式）
         */
        isDmmAvailable() {
            return !!this.form.proxyUrl.trim();
        },

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

            // 接入 page lifecycle（取代 window.confirmLeavingSettings）
            if (window.__registerPage) {
                window.__registerPage({
                    beforeLeave: (href) => {
                        if (!this.isDirty) return true;
                        this.pendingNavigationUrl = href;
                        this.dirtyCheckModalOpen = true;
                        return false;
                    },
                    onBeforeUnload: () => {
                        if (this.isDirty) return '您有未儲存的設定變更';
                        return null;
                    },
                    cleanup: () => {
                        if (this._toastTimer) clearTimeout(this._toastTimer);
                    }
                });
            }
        },

        // ===== Methods =====
        async cycleLocale() {
            if (this.isDirty) {
                if (!confirm('您有未儲存的變更，切換語系後將遺失。確定繼續？')) return;
            }
            const order = ['zh-TW', 'zh-CN', 'ja', 'en'];
            const idx = order.indexOf(this.locale);
            const next = order[(idx + 1) % order.length];
            try {
                const resp = await fetch('/api/config/general/locale', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: next })
                });
                const result = await resp.json();
                if (result.success) {
                    location.reload();
                } else {
                    console.warn('[i18n] cycleLocale failed:', result.error);
                }
            } catch (e) {
                console.error('[i18n] cycleLocale error:', e);
            }
        },

        async loadConfig() {
            // 鎖定表單（載入期間不可操作）
            this._configLoading = true;
            // 清空快照（載入期間不判定 dirty）
            this.savedState = null;

            try {
                const resp = await fetch('/api/config');
                const result = await resp.json();
                if (result.success) {
                    const config = result.data;

                    // Search
                    this.form.uncensoredModeEnabled = config.search?.uncensored_mode_enabled || false;
                    this.form.searchFavoriteFolder = config.search?.favorite_folder || '';
                    this.form.proxyUrl = config.search?.proxy_url || '';
                    this.form.primarySource = config.search?.primary_source || 'javbus';

                    // Translate
                    this.form.translateEnabled = config.translate.enabled;
                    this.form.translateProvider = config.translate.provider || 'ollama';
                    this.form.ollamaUrl = config.translate.ollama?.url || config.translate.ollama_url || 'http://localhost:11434';
                    this.form.ollamaModel = config.translate.ollama?.model || config.translate.ollama_model || '';
                    this.form.geminiApiKey = config.translate.gemini?.api_key || '';

                    // Gemini model 預設填入
                    if (config.translate.gemini?.model) {
                        this.geminiModels = [{ name: config.translate.gemini.model }];
                        this.form.geminiModel = config.translate.gemini.model;
                    }

                    // OpenAI Compatible
                    this.form.openaiBaseUrl = config.translate.openai?.base_url || '';
                    this.form.openaiApiKey = config.translate.openai?.api_key || '';
                    this.form.openaiModel = config.translate.openai?.model || 'gpt-4o-mini';
                    this.openaiUseCustomModel = config.translate.openai?.use_custom_model || false;

                    // 自動測試 Gemini（如果有 API Key 且是 gemini provider）
                    if (config.translate.gemini?.api_key && config.translate.provider === 'gemini') {
                        setTimeout(() => this.testGeminiConnection(), 100);
                    }

                    // 自動 fetch OpenAI models（如果有 base_url 且是 openai provider）
                    if (config.translate.openai?.base_url && config.translate.provider === 'openai') {
                        setTimeout(() => this.fetchOpenAIModels({ source: 'auto' }), 100);
                    }

                    // Scraper
                    this.form.createFolder = config.scraper.create_folder;
                    const layers = config.scraper.folder_layers || [];
                    if (layers.length >= 1) this.form.folderLayer3 = layers[layers.length - 1] || '';
                    if (layers.length >= 2) this.form.folderLayer2 = layers[layers.length - 2] || '';
                    if (layers.length >= 3) this.form.folderLayer1 = layers[layers.length - 3] || '';
                    // 向後兼容：沒有 folder_layers 時從 folder_format 拆分讀取
                    if (layers.length === 0 && config.scraper.folder_format) {
                        const parts = config.scraper.folder_format.replace(/\\/g, '/').split('/').filter(p => p.trim());
                        if (parts.length >= 1) this.form.folderLayer3 = parts[parts.length - 1];
                        if (parts.length >= 2) this.form.folderLayer2 = parts[parts.length - 2];
                        if (parts.length >= 3) this.form.folderLayer1 = parts[parts.length - 3];
                    }

                    this.form.filenameFormat = config.scraper.filename_format;
                    this.form.maxTitleLength = config.scraper.max_title_length;
                    this.form.maxFilenameLength = config.scraper.max_filename_length;
                    this.form.videoExtensions = config.scraper.video_extensions.join(', ');
                    this.form.suffixKeywords = config.scraper?.suffix_keywords || ['-cd1', '-cd2', '-4k', '-uc'];
                    this.form.jellyfinMode = config.scraper?.jellyfin_mode || false;
                    this.form.downloadSampleImages = config.scraper?.download_sample_images || false;

                    // Gallery
                    this.form.avlistMode = config.gallery?.default_mode || 'image';
                    this.form.avlistSort = config.gallery?.default_sort || 'date';
                    this.form.avlistOrder = config.gallery?.default_order || 'descending';
                    // T3.2 P2 fix: `??` 而非 `||` — items_per_page=0 是 "全部" 合法選項，
                    // 用 `||` 會把 0 吞掉變 90，導致存檔後重開 settings 顯示錯誤。
                    this.form.avlistItemsPerPage = config.gallery?.items_per_page ?? 90;
                    this.form.avlistMinSize = config.gallery?.min_size_mb || 0;
                    this.form.avlistOutputDir = config.gallery?.output_dir || 'output';
                    this.form.avlistOutputFilename = config.gallery?.output_filename || 'gallery_output.html';

                    // Showcase
                    this.form.viewerPlayer = config.showcase?.player || '';

                    // General
                    let defaultPage = config.general?.default_page || 'search';
                    if (defaultPage === 'gallery') defaultPage = 'scanner';  // 向後兼容
                    this.form.defaultPage = defaultPage;
                    // sidebar_collapsed 已移除（由 Alpine $persist + localStorage 驅動）

                    // 建立初始快照（dirty check 基準）— 必須在解鎖前建立
                    this.savedState = JSON.parse(JSON.stringify(this.form));
                    this.savedOpenaiUseCustomModel = this.openaiUseCustomModel;
                    // 解鎖表單（config hydrate 完成）
                    this._configLoading = false;

                    // 背景載入 Ollama 模型列表（不阻塞表單）
                    const ollamaUrl = config.translate.ollama?.url || config.translate.ollama_url;
                    const ollamaModel = config.translate.ollama?.model || config.translate.ollama_model;
                    if (ollamaUrl && config.translate.provider === 'ollama') {
                        this.loadOllamaModels(ollamaUrl, ollamaModel);  // 不 await
                    }
                }
            } catch (e) {
                console.error('載入設定失敗:', e);
            } finally {
                this._configLoading = false;
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
                        .split(',').map(s => s.trim()).filter(s => s),
                    suffix_keywords: this.form.suffixKeywords,
                    jellyfin_mode: this.form.jellyfinMode,
                    download_sample_images: this.form.downloadSampleImages,
                };

                // 更新 search
                config.search = {
                    ...config.search,
                    uncensored_mode_enabled: this.form.uncensoredModeEnabled,
                    favorite_folder: this.form.searchFavoriteFolder.trim(),
                    proxy_url: this.form.proxyUrl.trim(),
                    primary_source: this.form.primarySource,
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
                    },
                    openai: {
                        base_url: this.form.openaiBaseUrl.trim(),
                        api_key: this.form.openaiApiKey,
                        model: this.form.openaiModel.trim() || 'gpt-4o-mini',
                        use_custom_model: this.openaiUseCustomModel
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
                    theme: this.theme || document.documentElement.getAttribute('data-theme') || 'light'
                    // theme / sidebar_collapsed 由 base.html $watch 即時同步，此處僅隨整體設定一併寫入
                };

                const resp = await fetch('/api/config', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                const result = await resp.json();
                if (result.success) {
                    this.showToast('設定已儲存', 'success');
                    // 更新快照（避免儲存後仍為 dirty）
                    this.savedState = JSON.parse(JSON.stringify(this.form));
                    this.savedOpenaiUseCustomModel = this.openaiUseCustomModel;
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

            this.ollamaStatus = `<span class="text-base-content/50">${window.t('settings.status.loading_models')}</span>`;

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

                    this.ollamaStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.n_models', {count: result.models.length})}</span>`;
                } else {
                    this.ollamaStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${result.error || window.t('settings.status.connection_failed')}</span>`;
                }
            } catch (e) {
                this.ollamaStatus = `<span class="text-warning"><i class="bi bi-exclamation-circle"></i> ${window.t('settings.status.connection_failed')}</span>`;
            }
        },

        async testProxy() {
            if (!this.form.proxyUrl.trim()) return;

            this.testProxyLoading = true;
            this.proxyStatusOk = false;
            this.proxyStatus = window.t('settings.status.testing');

            try {
                const resp = await fetch('/api/proxy/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ proxy_url: this.form.proxyUrl.trim() })
                });
                const result = await resp.json();

                if (result.success === true) {
                    this.proxyStatusOk = true;
                    this.proxyStatus = `✓ ${result.message}`;
                } else {
                    this.proxyStatus = `✗ ${result.message}`;
                }
            } catch (e) {
                this.proxyStatus = window.t('settings.status.network_error');
            } finally {
                this.testProxyLoading = false;
            }
        },

        async testOllamaConnection() {
            const url = this.form.ollamaUrl.trim();

            if (!url) {
                this.ollamaStatus = `<span class="text-error">${window.t('settings.status.enter_url')}</span>`;
                return;
            }

            this.testOllamaLoading = true;
            this.ollamaStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const resp = await fetch(`/api/ollama/models?url=${encodeURIComponent(url)}`);
                const result = await resp.json();

                if (result.success && result.models && result.models.length > 0) {
                    this.ollamaModels = result.models;
                    this.form.ollamaModel = this.ollamaModels.includes(this.form.ollamaModel)
                        ? this.form.ollamaModel
                        : result.models[0];

                    this.ollamaStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${window.t('settings.status.connected_n_models', {count: result.models.length})}</span>`;
                } else {
                    this.ollamaStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error || window.t('settings.status.no_models')}</span>`;
                    this.ollamaModels = [];
                }
            } catch (e) {
                this.ollamaStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
                this.ollamaModels = [];
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
                    this.modelStatus = `<span class="text-success"><i class="bi bi-check-circle"></i> ${result.result}</span>`;
                } else {
                    this.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${result.error}</span>`;
                }
            } catch (e) {
                this.modelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${e.message}</span>`;
            } finally {
                this.testModelLoading = false;
            }
        },

        async testGeminiConnection() {
            const apiKey = this.form.geminiApiKey;

            if (!apiKey) {
                this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_api_key')}</span>`;
                return;
            }

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

                    // 如果當前 model 不在 allowlist，自動選第一個
                    const modelNames = data.models.map(m => m.name);
                    if (data.models.length > 0 && !modelNames.includes(this.form.geminiModel)) {
                        this.form.geminiModel = data.models[0].name;
                        // auto-fallback 不算用戶修改，同步快照避免 isDirty 誤判
                        if (this.savedState) this.savedState.geminiModel = this.form.geminiModel;
                    }
                } else {
                    this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${data.error || window.t('settings.status.connect_failed')}</span>`;
                    this.geminiModels = [];
                    this.geminiModelStatus = '';
                }
            } catch (error) {
                this.geminiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${error.message}</span>`;
            } finally {
                this.testGeminiLoading = false;
            }
        },

        async testGeminiTranslation() {
            const apiKey = this.form.geminiApiKey;
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
                    this.geminiModelStatus = `<span class="text-success"><i class="bi bi-check-circle-fill"></i> ${window.t('settings.status.translation_success', {translation: data.translation})}</span>`;
                } else {
                    this.geminiModelStatus = `<span class="text-error"><i class="bi bi-exclamation-triangle-fill"></i> ${data.error}</span>`;
                }
            } catch (error) {
                this.geminiModelStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.test_failed', {msg: error.message})}</span>`;
            } finally {
                this.testGeminiTranslateLoading = false;
            }
        },

        async fetchOpenAIModels({ source = 'manual' } = {}) {
            const baseUrl = this.form.openaiBaseUrl.trim();

            if (!baseUrl) {
                this.openaiStatus = `<span class="text-error"><i class="bi bi-x-circle"></i> ${window.t('settings.status.enter_url')}</span>`;
                return;
            }

            this.fetchingOpenaiModels = true;
            this.openaiStatus = `<span class="text-base-content/50">${window.t('settings.status.connecting')}</span>`;

            try {
                const response = await fetch('/api/openai/models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        base_url: baseUrl,
                        api_key: this.form.openaiApiKey
                    })
                });

                const data = await response.json();

                if (data.success && data.models && data.models.length > 0) {
                    this.openaiModels = data.models;
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

        async testOpenAITranslation() {
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
                        api_key: this.form.openaiApiKey,
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

        // ===== Reset Config Modal (T3.4: confirm → fluent-modal + i18n) =====
        openResetConfigModal() {
            this.resetConfigModalOpen = true;
        },

        cancelResetConfigModal() {
            this.resetConfigModalOpen = false;
        },

        async confirmResetConfig() {
            this._resetConfigLoading = true;
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
            } finally {
                this._resetConfigLoading = false;
                this.resetConfigModalOpen = false;
            }
        },

        async resetConfig() {
            // Thin wrapper：保留向後相容，template @click="resetConfig()" 不需改
            this.openResetConfigModal();
        },

        insertVariable(targetField, varName) {
            const input = this.$refs[targetField];
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

        formatPreviewHtml(formatStr) {
            if (!formatStr) return '';
            // Escape HTML to prevent XSS via x-html
            let html = formatStr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            // Build a map from token name to label
            const allVars = [...this.formatVariables, ...this.folderVariables];
            const seen = new Set();
            for (const v of allVars) {
                if (seen.has(v.name)) continue;
                seen.add(v.name);
                html = html.replaceAll(v.name, `<span class="tag-badge">${v.label}</span>`);
            }
            return html;
        },

        addSuffix() {
            let kw = this.newSuffixInput.trim().toLowerCase();
            if (!kw) return;
            if (!kw.startsWith('-') && !kw.startsWith('_')) {
                kw = '-' + kw;
            }
            if (!this.form.suffixKeywords.includes(kw)) {
                this.form.suffixKeywords.push(kw);
            }
            this.newSuffixInput = '';
        },

        removeSuffix(idx) {
            this.form.suffixKeywords.splice(idx, 1);
        },

        // Dirty check modal — 儲存更改後離開
        async dirtyCheckSave() {
            await this.saveConfig();
            // saveConfig 成功會更新 savedState，isDirty 變 false
            if (!this.isDirty) {
                // 儲存成功，透過 lifecycle API 執行 cleanup 再跳轉
                this.dirtyCheckModalOpen = false;
                if (window.__leavePage) {
                    if (!window.__leavePage(this.pendingNavigationUrl)) return;
                }
                window.location.href = this.pendingNavigationUrl;
            }
            // 儲存失敗：modal 保持開啟，toast 已顯示錯誤
            // 用戶可選「不儲存」離開或「取消」留下
        },

        // Dirty check modal — 不儲存直接離開
        dirtyCheckDiscard() {
            this.savedState = null;  // 防止殘留
            // T3(40b): 透過 lifecycle API 執行 cleanup 再跳轉
            // __leavePage 回傳 false 表示 cleanup 阻止導航（例如仍有進行中請求）
            if (window.__leavePage) {
                if (!window.__leavePage(this.pendingNavigationUrl)) return;
            }
            window.location.href = this.pendingNavigationUrl;
        },

        // Dirty check modal — 取消（留在 settings）
        dirtyCheckCancel() {
            this.pendingNavigationUrl = '';
            this.dirtyCheckModalOpen = false;
        },

        showToast(message, type = 'success', duration = 2500) {
            this._toast.message = message;
            this._toast.type = type;
            this._toast.visible = true;
            if (this._toastTimer) clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(() => {
                this._toast.visible = false;
                this._toastTimer = null;
            }, duration);
        }
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('settingsPage', settingsPage);
});
