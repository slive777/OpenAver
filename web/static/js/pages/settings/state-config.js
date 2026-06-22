// 同時啟用來源數上限（前端鏡像；後端真理來源 core/source_config.py:MAX_ENABLED_SOURCES）
const MAX_ENABLED_SOURCES = 10;

export function stateConfig() {
    return {
        // ===== Form State =====
        form: {
            // Search
            searchFavoriteFolder: '',
            proxyUrl: '',
            thumbnailCacheEnabled: true,   // 縮圖快取開關（feature/71 T2，top-level config 欄位）；新安裝預設開啟（0.9.11+），舊用戶 migration 維持關閉

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
            externalManager: 'off',
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

        // ===== Server Mode State (80a-T3) =====
        serverMode: false,
        lanIp: '',
        lanPort: null,

        // ===== Dirty Check State =====
        savedState: null,
        savedOpenaiUseCustomModel: false,
        pendingNavigationUrl: '',
        _configLoading: true,  // 初始 true，loadConfig 完成後 false

        // ===== 縮圖快取空間估算（71-T5）=====
        // 非 config 欄位（不入 saveConfig）；由 loadConfig() fetch /api/gallery/stats 填。
        videoCount: 0,

        // ===== Sources (61c-2) =====
        // 單一 unified scope：sources[] 容 builtin + metatube + manual_only 一個陣列，
        // cap 天然全域（design §0 + §9 B1 row）。由 loadConfig() 填、saveConfig() 序列化回。
        sources: [],
        MAX_ENABLED_SOURCES,

        // 拖曳 / 鍵盤 sortable transient state
        draggingId: null,
        dropTargetId: null,
        _grabbedId: null,        // 鍵盤 sortable 拾起中的 pill id
        showCapAlert: false,     // _flashCapAlert() 觸發 + auto-dismiss
        _capAlertTimer: null,

        // ===== Metatube connection state machine (61c-4, CD-61-11 two-boolean model) =====
        // 三狀態由兩布林推導：
        //   disabled  = !metatubeEnabled                          → Section 3 整段不渲染
        //   idle      = metatubeEnabled && !metatubeConnected     → 連線表單
        //   connected = metatubeEnabled && metatubeConnected      → 連線狀態列 + 摺疊 Parts Bin
        // B1：metatubeEnabled 維持 hardcoded false（production 不渲染 Section 3）；B3 接實際連線翻 true。
        metatubeEnabled: false,    // hydrated from config.metatube.enabled (CD-63b-3)
        metatubeConnected: false,
        partsBinExpanded: false,   // §2.8 Parts Bin 預設摺疊
        metatubeServerUrl: '',     // idle 連線表單 Server URL
        metatubeToken: '',         // idle 連線表單 Bearer Token
        metatubeConnecting: false, // true while POST /connect is in-flight (CD-63b-3)
        metatubeLanMode: false,    // allow_lan checkbox (CD-63b-3)
        probeProgress: 0,          // number of providers probed so far
        probeTotal: 30,            // total providers expected (updated from /status)
        probeDone: true,           // false while background probe is running
        _probeInterval: null,      // interval handle for probe polling

        // 無碼模式 transient off-hint（EC-2：off 不自動重開有碼，僅提示使用者手動重啟）
        showUncensoredOffHint: false,
        _uncensoredOffHintTimer: null,

        // ===== Constants =====

        // 來源分群常數（與 core/scrapers/utils.py 同步）
        CENSORED_SOURCES: ['dmm', 'javbus', 'jav321', 'javdb'],

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

        // 71-T5: 縮圖快取預估空間（MB）。每張封面縮圖 ~32KB；`|| 0` 防 NaN。
        get _thumbEstimateMb() {
            return Math.round((this.videoCount || 0) * 32 / 1024);
        },

        // 71-T11: 縮圖快取 HDD 時間估算（分鐘）。每張 ~0.25s（HDD 常數）→ 分鐘；
        // Math.ceil 確保非 0 庫至少 1 分鐘（videoCount=0 → 0）；`|| 0` 防 NaN。
        get _thumbEstimateMin() {
            return Math.ceil((this.videoCount || 0) * 0.25 / 60);
        },

        // ===== Sources computed (61c-2) =====
        // Cap basis（counter + promote/toggle 守衛）。**不看 available**（design §2.2 —
        // 斷線 metatube 仍占槽，避免重連後 cap 暴衝）。manual_only 不計入。
        get enabledCount() {
            return this.sources.filter(s => s.enabled && !s.manual_only).length;
        },

        // Zone A render 順序：builtin + enabled metatube 保留 GLOBAL 順序（一條 flat
        // orderable run）；manual_only（JavLibrary）永遠 append 末尾、固定不可拖。
        get activeRowSources() {
            // manual_only 一律排除於一般 run（即使 type==='builtin'），只走 pinned-last，
            // 否則 B4 javlibrary（manual_only=true）會在一般 run + 末尾各渲染一次（雙重渲染）。
            const inRow = this.sources.filter(
                s => !s.manual_only && (s.type === 'builtin' || (s.type === 'metatube' && s.enabled))
            );
            const manualOnly = this.sources.filter(s => s.manual_only);
            return [...inRow, ...manualOnly];
        },

        // Zone B Parts Bin：只有 enabled=false 的 metatube，依 order 排序（spread COPY，
        // 不 in-place mutate reactive 陣列）。B1 無 metatube → 空。
        get partsBinSources() {
            return this.sources
                .filter(s => s.type === 'metatube' && !s.enabled)
                .slice()
                .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        },

        // 是否無碼來源（供膠囊有碼/無碼配色）。讀後端 computed is_censored 欄位。
        isUncensored(src) {
            return !src.is_censored;
        },

        // ===== 無碼模式 computed（61c-3，CD-61-7b）=====
        // getter = sources 中所有有碼來源（CENSORED_SOURCES 4 個）全 enabled=false ⟺ true。
        // 讀 this.sources → Alpine 自動追蹤；點任一有碼 pill 重啟 → getter 反應性回 false（雙向 sync，無需 $watch）。
        // 與後端 is_uncensored_mode_effective 同口徑（all censored disabled），不加 POC 的「some uncensored enabled」條件以免 mirror 漂移。
        get allBuiltinEnabled() {
            // builtin 共 8（< cap 10），不可用 enabledCount>=cap 判斷全開。
            // 空陣列 guard：sources=[] 時 every() vacuous true，須先確認長度>0。
            const builtin = this.sources.filter(s => s.type === 'builtin' && !s.manual_only);
            return builtin.length > 0 && builtin.every(s => s.enabled);
        },

        get uncensoredMode() {
            const censored = this.sources.filter(s => this.CENSORED_SOURCES.includes(s.id));
            return censored.length > 0 && censored.every(s => !s.enabled);
        },
        // setter(true) = batch 停用 4 個有碼來源後 saveConfig。
        // setter(false) = NO-OP + transient hint（EC-2：off 不自動重開有碼，由使用者手動重啟任一有碼 pill）。
        set uncensoredMode(v) {
            if (v === true) {
                this.sources.forEach(s => {
                    if (this.CENSORED_SOURCES.includes(s.id) && !s.manual_only) {
                        s.enabled = false;
                    }
                });
                this.saveConfig();
            } else {
                this._flashUncensoredOffHint();
            }
        },
        _flashUncensoredOffHint() {
            this.showUncensoredOffHint = true;
            if (this._uncensoredOffHintTimer) clearTimeout(this._uncensoredOffHintTimer);
            this._uncensoredOffHintTimer = setTimeout(() => {
                this.showUncensoredOffHint = false;
            }, 5000);
            if (typeof this.showToast === 'function') {
                this.showToast(window.t('settings.sources.uncensored_mode_off_hint'), 'info');
            }
        },

        // promote 可行性：未啟用、非 manual_only、cap 未滿。
        canPromote(src) {
            return !!src && !src.enabled && !src.manual_only
                && this.enabledCount < MAX_ENABLED_SOURCES;
        },

        // metatube 已啟用但不可用 = 「斷線」（灰化 + 刪除線 + m 角標 + click toast；§2.4 / EC-9）。
        isDisconnectedMetatube(src) {
            return src.type === 'metatube' && src.enabled && !src.available;
        },

        // data-enabled="false"（刪除線/slash/dashed）視覺：manual_only → muted；斷線 → false。
        pillVisualEnabled(src) {
            if (src.manual_only) return false;
            if (this.isDisconnectedMetatube(src)) return false;
            return src.enabled;
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

            // 80a-T3: 讀 data-lan-ip attribute（T2 注入 template context）
            this.lanIp = this.$el?.dataset?.lanIp || '';

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
            // 71-T5 prewarm 觸發點不放 checkbox $watch：Settings 是表單式儲存，
            // toggle 當下 config.json 尚未寫入，後端 gate（load_config）讀到舊 false → disabled，
            // 且 hydrate（loadConfig false→true）會每次開 Settings 誤觸。改在 saveConfig() 成功後
            // 比對「persisted false → 現在 true」才 POST（見 saveConfig）。

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

        // 80a-T3: Server Mode methods ─────────────────────────────────────────

        serverUrl() {
            if (!this.lanIp || !this.lanPort) return null;
            return `http://${this.lanIp}:${this.lanPort}`;
        },

        // 81b-T1: 顯示用（無 http）；複製仍走 serverUrl() 完整網址
        serverUrlDisplay() {
            if (!this.lanIp || !this.lanPort) return null;
            return `${this.lanIp}:${this.lanPort}`;
        },

        async setServerMode(val) {
            try {
                const resp = await fetch('/api/config/general/server_mode', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: !!val })
                });
                const result = await resp.json();
                if (result.success) {
                    this.serverMode = !!val;
                    this.lanPort = result.lan_port ?? null;
                    this.lanIp = result.lan_ip ?? null;
                } else {
                    console.warn('[serverMode] setServerMode failed:', result.error);
                    // 遠端被拒（loopback 守衛）給專屬訊息，不用「請稍後再試」（重試無用）
                    const failKey = result.reason === 'remote_forbidden'
                        ? 'settings.server_info.remote_only'
                        : (val ? 'settings.server_info.toggle_failed' : 'settings.server_info.disable_failed');
                    this.showToast(window.t(failKey), 'error');
                }
            } catch (e) {
                console.warn('[serverMode] setServerMode error:', e);
                this.showToast(window.t(val ? 'settings.server_info.toggle_failed' : 'settings.server_info.disable_failed'), 'error');
            }
        },

        async copyServerUrl() {
            if (!this.serverUrl()) return;
            if (!navigator.clipboard?.writeText) {
                this.showToast(window.t('settings.server_info.copy'), 'info');
                return;
            }
            try {
                await navigator.clipboard?.writeText(this.serverUrl());
                this.showToast(window.t('settings.server_info.copied'), 'success');
            } catch (e) {
                console.warn('[serverMode] copyServerUrl: clipboard not available', e);
                this.showToast(window.t('settings.server_info.copy'), 'info');
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
                    // 61c-3: uncensoredMode 由 sources 段推導（computed getter），不再單獨讀 uncensored_mode_enabled。
                    this.form.searchFavoriteFolder = config.search?.favorite_folder || '';
                    this.form.proxyUrl = config.search?.proxy_url || '';
                    this.form.thumbnailCacheEnabled = config.thumbnail_cache_enabled || false;
                    // 71-T5: 載入目前片數供縮圖快取空間估算（失敗降級 0，不阻塞表單）
                    this._loadVideoCount();

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
                    this.form.externalManager = config.scraper?.external_manager || 'off';
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

                    // 80a-T3: Server Mode（?? false：缺 key→false；不用 ||，守 CD#3 慣例）
                    this.serverMode = config.general?.server_mode ?? false;
                    if (this.serverMode) {
                        try {
                            const r = await fetch('/api/config/general/lan-port');
                            const j = await r.json();
                            this.lanPort = j.lan_port ?? null;
                            this.lanIp = j.lan_ip ?? null;
                        } catch (_e) { this.lanPort = null; }
                    } else {
                        this.lanPort = null;
                    }

                    // Sources（61c-2）：讀 config.sources 段填入 unified scope。
                    // FIELD-NAME TRAP：後端用 display_name_key / display_name_raw；
                    // 前端 pill 統一用 display_name（builtin→key，其他→raw）。
                    // is_censored 是後端 computed，直接讀。依 order 排序。
                    this.sources = (config.sources || [])
                        .map(s => ({
                            id: s.id,
                            type: s.type,
                            enabled: s.enabled,
                            order: s.order,
                            manual_only: s.manual_only,
                            is_beta: s.is_beta,
                            is_censored: s.is_censored,
                            config: s.config || {},
                            display_name_key: s.display_name_key || '',
                            display_name: s.type === 'metatube'
                                ? (s.display_name_raw || '')
                                : (s.display_name_key || ''),
                            available: s.available ?? (s.type !== 'metatube'),  // builtins default available; metatube waits for /status
                            requires_proxy: s.requires_proxy ?? false,           // forward-compat for 63c-6
                        }))
                        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

                    // 建立初始快照（dirty check 基準）— 必須在解鎖前建立
                    this.savedState = JSON.parse(JSON.stringify(this.form));
                    this.savedOpenaiUseCustomModel = this.openaiUseCustomModel;
                    // 解鎖表單（config hydrate 完成）
                    this._configLoading = false;

                    // Hydrate metatube fields from config + /status (CD-63b-3)
                    this.metatubeEnabled = config.metatube?.enabled || false;
                    this.metatubeServerUrl = config.metatube?.url || '';
                    this.metatubeToken = config.metatube?.token || '';
                    this.metatubeLanMode = !!config.metatube?.allow_lan;   // hydrate LAN opt-in so re-connect doesn't fail SSRF (Codex P2)
                    try { await this.hydrateMetatubeStatus(); } catch (_e) { this.metatubeConnected = false; }

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

        // 71-T5: 載入目前片數（供縮圖快取空間估算）。失敗/缺值 → videoCount 維持 0，不阻塞表單。
        async _loadVideoCount() {
            try {
                const r = await fetch('/api/gallery/stats');
                const j = await r.json();
                this.videoCount = (j.success && j.data && typeof j.data.total === 'number')
                    ? j.data.total
                    : 0;
            } catch (e) {
                console.error('[71-T5] 載入片數失敗:', e);
                this.videoCount = 0;
            }
        },

        // 71-T5: 觸發背景全量 prewarm（由 saveConfig 在「剛開啟並已存檔」時呼叫，
        // 確保此刻 config.json 已 true、後端 gate 放行）。scan-done 亦無條件 POST，同由後端 gate。
        async _triggerThumbPrewarm() {
            try {
                // fire-and-forget：不 await（toast 立即出）；.catch 收 async rejection
                // 避免 fetch 失敗變 unhandled promise rejection（try/catch 只接同步 throw）。
                fetch('/api/gallery/thumb/prewarm', { method: 'POST' })
                    .catch((e) => console.error('[71-T5] 縮圖 prewarm POST 失敗:', e));
                this.showToast(window.t('notif.thumb_prewarm_start'), 'info');
            } catch (e) {
                console.error('[71-T5] 觸發縮圖 prewarm 失敗:', e);
            }
        },

        // 71b-T2: DB-safe 清空縮圖快取（由 saveConfig 在「剛關閉並已存檔」時呼叫，
        // 先存才清——此刻 config.json 已 false）。鏡像 _triggerThumbPrewarm。
        _triggerThumbClear() {
            try {
                // fire-and-forget：不 await；.catch 收 async rejection
                // （try/catch 只接同步 throw）。端點純 rmtree output/thumb/，不碰 DB。
                fetch('/api/gallery/thumb/clear', { method: 'POST' })
                    .catch((e) => console.error('[71b-T2] 縮圖 clear POST 失敗:', e));
            } catch (e) {
                console.error('[71b-T2] 觸發縮圖 clear 失敗:', e);
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
                // 71-T5: 存檔前的「已持久化」縮圖快取狀態（authoritative：剛從 server GET 的 config.json）。
                // 用來在 PUT 成功後判定「這次儲存是否剛把它從關打開」→ 才觸發背景 prewarm。
                const prevThumbEnabled = config.thumbnail_cache_enabled === true;

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
                    external_manager: this.form.externalManager,
                    download_sample_images: this.form.downloadSampleImages,
                };

                // 更新 search
                config.search = {
                    ...config.search,
                    uncensored_mode_enabled: this.uncensoredMode,
                    favorite_folder: this.form.searchFavoriteFolder.trim(),
                    proxy_url: this.form.proxyUrl.trim(),
                };

                config.thumbnail_cache_enabled = this.form.thumbnailCacheEnabled;

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

                // 更新 metatube enabled（CD-63b-3）：保留 url/token（GET 載入的），只更新 enabled。
                config.metatube = { ...(config.metatube || {}), enabled: this.metatubeEnabled };

                // 更新 sources（61c-2）：序列化回後端 SourceConfig 欄位形狀。
                // order 重算 = 當前陣列 index。is_censored 是後端 computed，**不回送**。
                config.sources = this.sources.map((s, i) => ({
                    id: s.id,
                    type: s.type,
                    display_name_key: s.type === 'builtin' ? s.display_name : (s.display_name_key || ''),
                    display_name_raw: s.type === 'metatube' ? s.display_name : '',
                    enabled: s.enabled,
                    order: i,
                    config: s.config || {},
                    is_beta: s.is_beta,
                    manual_only: s.manual_only,
                }));

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
                    // 71-T5: 縮圖快取「剛被開啟」(persisted false → 現在 true) 才觸發背景 prewarm。
                    // 必在 PUT 成功之後——此刻 config.json 已寫入 true，後端 gate 才會放行（非 disabled）。
                    if (!prevThumbEnabled && this.form.thumbnailCacheEnabled === true) {
                        this._triggerThumbPrewarm();
                    }
                    // 71b-T2: 縮圖快取「剛被關閉」(persisted true → 現在 false) 才清空 output/thumb/。
                    // 必在 PUT 成功之後——先存才清（config.json 已寫 false）。confirmThumbCacheDisable
                    // 自身不 POST clear，統一收斂於此（與 prewarm 對稱）。
                    if (prevThumbEnabled && this.form.thumbnailCacheEnabled === false) {
                        this._triggerThumbClear();
                    }
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

        // ===== Thumbnail Cache Confirm Modal (71-T11) =====
        // toggle @change 攔截（鏡像 onMetatubeEnabledChange）。x-model 先翻值，
        // 故進來時 this.form.thumbnailCacheEnabled 已是使用者撥到的新值。
        // 只在「真正首次開啟」（persisted 仍 false）攔截開 modal（Codex P2 #1）。
        onThumbCacheToggleChange() {
            // x-model 已先翻值 → 進來時 form.thumbnailCacheEnabled 已是使用者撥到的新值。
            if (this.form.thumbnailCacheEnabled !== true) {
                // ON→OFF：若「已持久化為啟用」（savedState true，與 enable 豁免同一變數）
                // → 還原 toggle 回 true（true 留到 confirm 才真正設 false）+ 開 disable modal。
                if (this.savedState?.thumbnailCacheEnabled === true) {
                    this.form.thumbnailCacheEnabled = true;
                    this.thumbCacheDisableConfirmOpen = true;
                }
                // 未持久化的 true 撥回 false（savedState 非 true）：照常、不開 modal
                // （對稱 enable path 的「未存後撥回」豁免）。
                return;
            }
            // persisted 已 true（未存的 OFF 後撥回 ON）：不開 modal，讓 toggle 照常變 true。
            if (this.savedState?.thumbnailCacheEnabled === true) return;
            // 真正首次開啟（persisted false）：還原 toggle + 開 confirm modal。
            // 真正的 true 留到 confirmThumbCacheEnable() 才設。
            this.form.thumbnailCacheEnabled = false;
            this.thumbCacheConfirmOpen = true;
        },

        // 取消 / ESC / backdrop 三路徑統一走此：關 modal，toggle 已在 @change 還原為
        // false，無需再動；不存檔、不 prewarm。
        cancelThumbCacheConfirm() {
            this.thumbCacheConfirmOpen = false;
        },

        // 71b-T2: 關閉確認取消 → 關 modal、toggle 維持 true（保持啟用）；不存檔、不清快取。
        cancelThumbCacheDisable() {
            this.thumbCacheDisableConfirmOpen = false;
        },

        // 71b-T2: 關閉確認 → 關 modal → set false → saveConfig()
        //（命中 saveConfig 內 prevThumbEnabled && now false 鏈 → 背景 _triggerThumbClear()；
        // 自身不 POST clear，先存才清）。
        async confirmThumbCacheDisable() {
            this.thumbCacheDisableConfirmOpen = false;
            this.form.thumbnailCacheEnabled = false;
            await this.saveConfig();
        },

        // 確認：先關 modal（移除確認鈕即防雙擊，無需 :disabled / loading flag）→
        // 設 true → saveConfig()（命中 saveConfig 內 !prevThumbEnabled && now true 鏈
        // → 背景 _triggerThumbPrewarm() + start bell；非阻塞、無頁面鎖）。
        async confirmThumbCacheEnable() {
            this.thumbCacheConfirmOpen = false;
            this.form.thumbnailCacheEnabled = true;
            await this.saveConfig();
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

        // ═══════════════════════════════════════════════════════════════
        // Sources — Active Row 互動（61c-2，移植自 POC settingsMockPage）
        // ═══════════════════════════════════════════════════════════════

        // Dispatcher：依 type / 狀態分流。B1 只命中 builtin-toggle 分支。
        clickActiveRowPill(src) {
            if (!src) return;
            // 63c-6 Surface 1：DMM requires_proxy 且 proxy 未設定 → toast + return（不 demote）
            if (src.requires_proxy && !this.isDmmAvailable()) {
                this.showToast(window.t('settings.sources.dmm_proxy_required_hint'), 'warning');
                return;
            }
            if (src.manual_only) { this.clickJavLibrary(); return; }
            // metatube Active Row 點擊 = demote（永遠允許，不論 available；demote 是可逆操作）
            if (src.type === 'metatube') { this.demoteMetatube(src.id); return; }
            // disconnect-guard 僅剩 builtin 使用（metatube 已上方 return；保留供未來擴展）
            if (this.isDisconnectedMetatube(src)) {
                this.clickDisconnectedMetatube(src.display_name);
                return;
            }
            if (src.type === 'builtin') { this.toggleBuiltin(src.id); return; }
        },

        // Builtin：原地翻轉 enabled（膠囊留 Active Row、停用 = inline 刪除線）。
        // cap 滿且要 enable → _flashCapAlert() return。翻轉後 saveConfig 即時 persist。
        toggleBuiltin(id) {
            const s = this.sources.find(x => x.id === id);
            if (!s || s.type !== 'builtin') return;
            if (!s.enabled && this.enabledCount >= MAX_ENABLED_SOURCES) {
                this._flashCapAlert();
                return;
            }
            s.enabled = !s.enabled;
            this.saveConfig();
        },

        // Promote：Parts Bin → Active Row（enabled=true）。cap 檢查。splice 移到陣列末尾
        // → 落在 metatube run 末、JavLibrary 前（EC-3）。
        promoteMetatube(id) {
            const s = this.sources.find(x => x.id === id);
            if (!s || s.type !== 'metatube' || s.enabled) return;
            // 斷線灰（US3）：整個 metatube 掉線 → 導向重連，不 promote
            if (!this.metatubeConnected) {
                this.showToast(window.t('settings.sources.mt_disconnect_toast'), 'warning');
                return;
            }
            // probe-failed 灰（US9）：connected 但此源測不到 → 非阻塞警告 + 繼續 promote（不擋）
            if (s.available === false) {
                this.showToast(window.t('settings.sources.mt_promote_unavailable_warning'), 'warning');
                // 不 return — promote 繼續（可逆操作，符合 prd 非破壞性 toast 規則）
            }
            if (this.enabledCount >= MAX_ENABLED_SOURCES) {
                this._flashCapAlert();
                return;
            }
            s.enabled = true;
            const idx = this.sources.findIndex(x => x.id === id);
            if (idx >= 0) {
                const [moved] = this.sources.splice(idx, 1);
                this.sources.push(moved);
            }
            this.saveConfig();
        },

        // Demote：Active Row → Parts Bin（enabled=false）。
        demoteMetatube(id) {
            const s = this.sources.find(x => x.id === id);
            if (!s || s.type !== 'metatube') return;
            s.enabled = false;
            this.saveConfig();
        },

        // 斷線 metatube 點擊：toast 提示重連，無 state mutation（EC-9）。
        clickDisconnectedMetatube(_name) {
            this.showToast(window.t('settings.sources.mt_disconnect_toast'), 'warning');
        },

        // Manual-Only（JavLibrary）：Active Row 內 no-op（[BETA] badge 取代 toggle，固定末尾）。
        clickJavLibrary() {
            // 進階搜尋專用 — no-op。
        },

        // ═══════════════════════════════════════════════════════════════
        // Metatube 連線狀態機 handlers（CD-63b-3）
        // ═══════════════════════════════════════════════════════════════

        async metatubeConnect() {
            if (this.metatubeConnecting) return;
            this.metatubeConnecting = true;
            try {
                const body = { url: this.metatubeServerUrl.trim(), token: this.metatubeToken.trim(), allow_lan: this.metatubeLanMode };
                const resp = await fetch('/api/settings/metatube/connect', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
                const result = await resp.json();
                if (result.success) {
                    this.sources.forEach(s => { if (s.type === 'metatube') s.available = true; });
                    await this.loadConfig();
                    this.metatubeConnected = true;
                    this.showToast(`已連線，${result.provider_count} 個 provider 已載入 Parts Bin`, 'success');
                    this.startProbePolling();
                } else {
                    this.showToast(`連線失敗：${result.error}`, 'error');
                }
            } catch (_e) {
                this.showToast(window.t('settings.sources.mt_connect_network_error'), 'error');
            } finally {
                this.metatubeConnecting = false;
            }
        },

        async metatubeDisconnect() {
            try {
                await fetch('/api/settings/metatube/disconnect', { method: 'POST' });
            } catch (_e) { /* ignore network error; proceed to local reset */ }
            this.metatubeConnected = false;
            this.sources.forEach(s => { if (s.type === 'metatube') s.available = false; });
            this.stopProbePolling();
        },

        // 編輯：回 idle 連線表單（保留 url/token 供修改），不動 enabled。
        metatubeEdit() {
            this.metatubeConnected = false;
        },

        // ─── Probe polling helpers (CD-63b-3 / CD-63b-4) ───────────────

        // Re-trigger a full probe (retest button — CD-63b-4 B1).
        async metatubeRetest() {
            try {
                await fetch('/api/settings/metatube/test', { method: 'POST' });
                this.startProbePolling();
            } catch (_e) {
                this.showToast(window.t('settings.sources.mt_connect_network_error'), 'error');
            }
        },

        startProbePolling() {
            this.probeDone = false; this.probeProgress = 0;
            if (this._probeInterval) clearInterval(this._probeInterval);
            this._probeInterval = setInterval(async () => {
                try {
                    const r = await fetch('/api/settings/metatube/status');
                    const s = await r.json();
                    this.probeProgress = s.probe_progress ?? 0;
                    this.probeTotal = s.providers?.length ?? 30;
                    this.probeDone = s.probe_done ?? false;
                    if (s.providers) {
                        s.providers.forEach(p => {
                            const src = this.sources.find(x => x.id === p.id);
                            if (src) src.available = p.available;
                        });
                    }
                    if (this.probeDone) { clearInterval(this._probeInterval); this._probeInterval = null; }
                } catch (_e) { clearInterval(this._probeInterval); this._probeInterval = null; this.probeDone = true; }
            }, 500);
        },

        stopProbePolling() {
            if (this._probeInterval) { clearInterval(this._probeInterval); this._probeInterval = null; }
            this.probeDone = true;
        },

        // ─── Hydrate metatube runtime state from /status ──────────────
        async hydrateMetatubeStatus() {
            try {
                const r = await fetch('/api/settings/metatube/status');
                const s = await r.json();
                this.metatubeConnected = !!s.connected;
                if (s.providers) {
                    s.providers.forEach(p => {
                        const src = this.sources.find(x => x.id === p.id);
                        if (src) src.available = p.available;
                    });
                }
                this.probeDone = s.probe_done ?? true;
                this.probeProgress = s.probe_progress ?? 0;
            } catch (_e) {
                this.metatubeConnected = false;
            }
        },

        // ─── Toggle callback (CD-63b-3) ───────────────────────────────
        async onMetatubeEnabledChange() {
            if (!this.metatubeEnabled && this.metatubeConnected) {
                await this.metatubeDisconnect();
            }
            await this.saveConfig();
        },

        // TODO(B4): remove metatube mock providers after B3 lands （CD-61-13）
        // 手動瀏覽器驗證用：console 呼叫 `$data._injectMetatubeMockProviders()` 注入 30 個
        // mock metatube provider（available=true，未啟用 → 全進 Parts Bin），驗證摺疊清單
        // 30-pill 渲染不爆版 + Recommended group 排序。production 不自動呼叫（metatubeEnabled
        // 維持 false）。B3 由真實 /v1/providers 列舉取代。
        _injectMetatubeMockProviders(n = 30) {
            const baseOrder = this.sources.length;
            const mock = Array.from({ length: n }, (_, i) => {
                const id = `mt_mock_${i + 1}`;
                return {
                    id,
                    type: 'metatube',
                    enabled: false,
                    available: true,
                    order: baseOrder + i,
                    manual_only: false,
                    is_beta: false,
                    is_censored: false,
                    config: {},
                    display_name_key: '',
                    display_name: `Provider ${i + 1}`,
                };
            });
            this.sources = [...this.sources, ...mock];
            this.metatubeEnabled = true;
        },

        // 全開：builtin 先（依序），到 cap 即 break；不碰 metatube / manual_only。
        enableAllToCap() {
            for (const s of this.sources) {
                if (s.manual_only || s.enabled) continue;
                if (s.type === 'metatube') continue;  // builtin first
                if (this.enabledCount >= MAX_ENABLED_SOURCES) break;
                s.enabled = true;
            }
            this.saveConfig();
        },

        _flashCapAlert() {
            this.showCapAlert = true;
            if (this._capAlertTimer) clearTimeout(this._capAlertTimer);
            this._capAlertTimer = setTimeout(() => { this.showCapAlert = false; }, 4500);
        },

        // ═══════════════════════════════════════════════════════════════
        // Sources — HTML5 native 拖曳（CD-61-4，無 Sortable）
        // 拖曳池：builtin 任一狀態 + enabled metatube。JavLibrary / Parts Bin 不可拖。
        // ═══════════════════════════════════════════════════════════════
        isDraggable(src) {
            if (!src || src.manual_only) return false;
            if (src.type === 'builtin') return true;
            return src.type === 'metatube' && src.enabled;
        },
        onDragStart(e, id) {
            this.draggingId = id;
            try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', id); } catch (_) { /* WebView 相容 */ }
        },
        onDragEnd() { this.draggingId = null; this.dropTargetId = null; },
        onDragOver(e, id) {
            // PyWebView 內 dragover 必須 preventDefault（模板 @dragover.prevent），
            // 否則 drop 不觸發（gotchas）。
            if (!this.draggingId || this.draggingId === id) return;
            const target = this.sources.find(x => x.id === id);
            if (!target || !this.isDraggable(target)) return;
            try { e.dataTransfer.dropEffect = 'move'; } catch (_) { /* WebView 相容 */ }
            this.dropTargetId = id;
        },
        onDrop(e, targetId) {
            const srcId = this.draggingId;
            const target = this.sources.find(x => x.id === targetId);
            if (!srcId || srcId === targetId || !target || !this.isDraggable(target)) {
                this.onDragEnd();
                return;
            }
            const srcIdx = this.sources.findIndex(s => s.id === srcId);
            const tgtIdx = this.sources.findIndex(s => s.id === targetId);
            if (srcIdx < 0 || tgtIdx < 0) { this.onDragEnd(); return; }
            const [moved] = this.sources.splice(srcIdx, 1);
            const insertAt = srcIdx < tgtIdx ? tgtIdx - 1 : tgtIdx;
            this.sources.splice(insertAt, 0, moved);
            this.onDragEnd();
            this.saveConfig();
        },

        // ═══════════════════════════════════════════════════════════════
        // Sources — 鍵盤 sortable（WAI-ARIA APG；POC 無，淨新增）
        // Enter = 翻轉/promote/demote（clickActiveRowPill）。
        // Space = 拾起 / 放下（grab toggle）。Arrow = grabbed 時移動位置。Escape = 取消。
        // ═══════════════════════════════════════════════════════════════

        // Space 在可拖曳 pill 上切換 grab/drop；不可拖（manual_only/disconnected）→ 視為啟用。
        onPillSpace(src) {
            if (!src) return;
            if (!this.isDraggable(src)) { this.clickActiveRowPill(src); return; }
            if (this._grabbedId === src.id) {
                // 放下 → persist
                this._grabbedId = null;
                this.saveConfig();
            } else {
                this._grabbedId = src.id;
            }
        },

        // Arrow 移動 grabbed pill 一格（dir = -1 上/左、+1 下/右）。只在 grabbed 時生效。
        onPillArrow(src, dir) {
            if (!src || this._grabbedId !== src.id) return;
            const idx = this.sources.findIndex(s => s.id === src.id);
            if (idx < 0) return;
            const targetIdx = idx + dir;
            if (targetIdx < 0 || targetIdx >= this.sources.length) return;
            // 目標位置必須仍是可拖曳區（不可越過 JavLibrary / Parts Bin pill）
            const neighbor = this.sources[targetIdx];
            if (!this.isDraggable(neighbor)) return;
            const [moved] = this.sources.splice(idx, 1);
            this.sources.splice(targetIdx, 0, moved);
        },

        // Escape 取消拾起（位置已即時移動，此處僅釋放 grab 並 persist 當前序）。
        onPillEscape() {
            if (this._grabbedId !== null) {
                this._grabbedId = null;
                this.saveConfig();
            }
        },
    };
}
