// Settings 頁面 Alpine.js 元件
function settingsPage() {
    return {
        // ===== Form State =====
        form: {
            // Search
            galleryModeEnabled: false,
            uncensoredModeEnabled: false,
            searchFavoriteFolder: '',
            proxyUrl: '',

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
            suffixKeywords: [],
            jellyfinMode: false,

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

        // ===== UI State =====
        newSuffixInput: '',
        showPathHelp: false,
        ollamaStatus: '',
        modelStatus: '',
        geminiStatus: '',
        geminiModelStatus: '',
        ollamaModels: [],
        geminiModels: [],
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

        // ===== Dirty Check State =====
        savedState: null,
        pendingNavigationUrl: '',

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

        formatVariables: [
            { name: '{num}', label: '番號' },
            { name: '{title}', label: '標題' },
            { name: '{actor}', label: '女優' },
            { name: '{actors}', label: '女優(全)' },
            { name: '{maker}', label: '片商' },
            { name: '{date}', label: '日期' },
            { name: '{year}', label: '年份' },
            { name: '{suffix}', label: '後綴' },
        ],
        folderVariables: [
            { name: '{num}', label: '番號' },
            { name: '{actor}', label: '女優' },
            { name: '{maker}', label: '片商' },
            { name: '{title}', label: '標題' },
            { name: '{year}', label: '年份' },
            { name: '{suffix}', label: '後綴' },
        ],
        FOLDER_PREVIEW_DATA: {
            num: 'SSNI-618',
            maker: 'SOD',
            actor: '三上悠亞',
            actors: '三上悠亞, 明日花',
            title: '絕對領域',
            date: '2024-01-15',
            year: '2024',
            suffix: '-4k',
        },

        // ===== Computed Properties =====
        get isDirty() {
            if (!this.savedState) return false;
            return JSON.stringify(this.form) !== JSON.stringify(this.savedState);
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

            // 暴露全域檢查函式（供 base.html sidebar 使用）
            window.confirmLeavingSettings = (targetUrl) => {
                if (this.isDirty) {
                    this.pendingNavigationUrl = targetUrl;
                    this.dirtyCheckModalOpen = true;
                    return false;  // 阻止導航
                }
                return true;  // 允許導航
            };
        },

        // ===== Methods =====
        async loadConfig() {
            // 清空快照（載入期間不判定 dirty）
            this.savedState = null;

            try {
                const resp = await fetch('/api/config');
                const result = await resp.json();
                if (result.success) {
                    const config = result.data;

                    // Search
                    this.form.galleryModeEnabled = config.search?.gallery_mode_enabled || false;
                    this.form.uncensoredModeEnabled = config.search?.uncensored_mode_enabled || false;
                    this.form.searchFavoriteFolder = config.search?.favorite_folder || '';
                    this.form.proxyUrl = config.search?.proxy_url || '';

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
                    this.form.suffixKeywords = config.scraper?.suffix_keywords || ['-cd1', '-cd2', '-4k', '-uc'];
                    this.form.jellyfinMode = config.scraper?.jellyfin_mode || false;

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
                    // sidebar_collapsed 已移除（由 Alpine $persist + localStorage 驅動）

                    // 自動載入 Ollama 模型列表
                    const ollamaUrl = config.translate.ollama?.url || config.translate.ollama_url;
                    const ollamaModel = config.translate.ollama?.model || config.translate.ollama_model;
                    if (ollamaUrl && config.translate.provider === 'ollama') {
                        await this.loadOllamaModels(ollamaUrl, ollamaModel);
                    }

                    // 建立初始快照（dirty check 基準）
                    this.savedState = JSON.parse(JSON.stringify(this.form));
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
                        .split(',').map(s => s.trim()).filter(s => s),
                    suffix_keywords: this.form.suffixKeywords,
                    jellyfin_mode: this.form.jellyfinMode,
                };

                // 更新 search
                config.search = {
                    ...config.search,
                    gallery_mode_enabled: this.form.galleryModeEnabled,
                    uncensored_mode_enabled: this.form.uncensoredModeEnabled,
                    favorite_folder: this.form.searchFavoriteFolder.trim(),
                    proxy_url: this.form.proxyUrl.trim()
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

            this.ollamaStatus = '<span class="text-base-content/50">載入模型中...</span>';

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

        async testProxy() {
            if (!this.form.proxyUrl.trim()) return;

            this.testProxyLoading = true;
            this.proxyStatusOk = false;
            this.proxyStatus = '測試中...';

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
                this.proxyStatus = '✗ 網路錯誤，請稍後再試';
            } finally {
                this.testProxyLoading = false;
            }
        },

        async testOllamaConnection() {
            const url = this.form.ollamaUrl.trim();

            if (!url) {
                this.ollamaStatus = '<span class="text-error">請輸入 URL</span>';
                return;
            }

            this.testOllamaLoading = true;
            this.ollamaStatus = '<span class="text-base-content/50">連線中...</span>';

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
                this.testOllamaLoading = false;
            }
        },

        async testModel() {
            const url = this.form.ollamaUrl.trim();
            const model = this.form.ollamaModel;

            if (!url || !model) {
                this.modelStatus = '<span class="text-error">請先選擇模型</span>';
                return;
            }

            this.testModelLoading = true;
            this.modelStatus = '<span class="text-base-content/50">測試中...</span>';

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
                this.geminiStatus = '<span class="text-error"><i class="bi bi-x-circle"></i> 請輸入 API Key</span>';
                return;
            }

            this.testGeminiLoading = true;
            this.geminiStatus = '<span class="text-base-content/50">連線中...</span>';

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
                this.testGeminiLoading = false;
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

            this.testGeminiTranslateLoading = true;
            this.geminiModelStatus = '<span class="text-base-content/50">測試翻譯中...</span>';

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
                this.testGeminiTranslateLoading = false;
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
                // 儲存成功，跳轉
                this.dirtyCheckModalOpen = false;
                window.location.href = this.pendingNavigationUrl;
            }
            // 儲存失敗：modal 保持開啟，toast 已顯示錯誤
            // 用戶可選「不儲存」離開或「取消」留下
        },

        // Dirty check modal — 不儲存直接離開
        dirtyCheckDiscard() {
            this.savedState = null;  // 防止殘留
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
