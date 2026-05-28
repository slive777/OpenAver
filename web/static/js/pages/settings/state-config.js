export function stateConfig() {
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

        // ===== Dirty Check State =====
        savedState: null,
        savedOpenaiUseCustomModel: false,
        pendingNavigationUrl: '',
        _configLoading: true,  // 初始 true，loadConfig 完成後 false

        // 61c-1 inert stubs — replaced by real state/computed in 61c-2 (sources/enabledCount),
        // 61c-3 (uncensoredMode getter/setter), 61c-4 (metatubeEnabled). Declared so the
        // sources-panel bindings don't throw ReferenceError before those tasks land.
        sources: [],
        enabledCount: 0,
        uncensoredMode: false,
        metatubeEnabled: false,
        showCapAlert: false,

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

        // ===== Lifecycle =====
        init() {
            // 61b-5: 頁面級 GSAP context（tab 切換 fade 用）。
            // 缺 OpenAver.motion / gsap 時跳過，動畫退化為直接顯示（x-show 本就會顯示）。
            if (window.OpenAver && window.OpenAver.motion) {
                this._gsapCtx = window.OpenAver.motion.createContext(this.$el);
            }

            this.loadConfig().then(() => {
                // B1: init scanner link state after config loaded
                if (typeof this._initB1 === 'function') this._initB1();
            });

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
                        // 61b-5: 回收 GSAP inline props（frontend-stack-roles 共存規則 3）
                        this._gsapCtx?.revert();
                    }
                });
            }

            // 61b-3: activeTab / URL hash / localStorage（活在 stateUI，禁加 stateUI.init）
            if (typeof this._initActiveTab === 'function') this._initActiveTab();
        },

        // ===== Methods =====
        async cycleLocale() {
            if (this.isDirty) {
                // eslint-disable-next-line no-alert -- cycleLocale dirty-check confirm, backlog migration to fluent-modal, reviewed 2026-05-03
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
    };
}
