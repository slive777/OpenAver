import { ChipEditor, normalizeFolderLayers } from '@/settings/chip-editor.js';

// 同時啟用來源數上限（前端鏡像；後端真理來源 core/source_config.py:MAX_ENABLED_SOURCES）
const MAX_ENABLED_SOURCES = 10;

export function stateConfig() {
    // 命名區 ChipEditor 實例與非響應狀態存**閉包 holder**（不進 Alpine x-data）：
    // ChipEditor 持 contentEditable DOM ref，被 reactive proxy 包裹有風險；folderLayerList
    // 與 formatVariables 才需響應（x-for + isDirty / 選單），留在 return 物件（CD-95a-9/12）。
    const naming = {
        filenameEditor: null,   // ChipEditor（檔名格式）
        layerEditors: {},       // { [layerId]: ChipEditor } 各資料夾層
        layerSeq: 0,            // 穩定遞增 id 計數器（禁用 index/value 當 key，CD-95a-12）
        ready: false,           // formatVariables 就緒後才 hydrate 膠囊
        filenameHydrated: false, // one-shot：filename editor 是否已完成首次 hydrate（95a-T8，防重載打斷游標）
    };
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
            // 資料夾層級：{id,value}[] 動態清單（外→內，上到下）。load 時 slice(0,3) 正規化
            // （後端只用前 3 層，CD-95a-7/12）。id 走 naming.layerSeq，x-for :key="layer.id"。
            folderLayerList: [],
            filenameFormat: '[{num}][{maker}] {title}',
            maxTitleLength: 80,
            maxFilenameLength: 200,
            videoExtensions: '.mp4, .avi, .mkv, .wmv, .rmvb, .flv, .mov, .m4v, .ts',
            suffixKeywords: [],
            externalManager: 'off',
            downloadSampleImages: false,
            strmRules: [],   // strm 路徑映射編輯狀態（array of {local, remote}）；load/save 兩端與 dict 對稱轉換

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
            closeAction: 'ask'
        },

        // ===== i18n State =====
        locale: (window.__locale || 'zh-TW'),

        // ===== Server Mode State (80a-T3) =====
        serverMode: false,
        lanIp: '',
        lanPort: null,

        // ===== 全域模式切換破壞性 confirm State (90c-T5) =====
        switchModeConfirmOpen: false,
        pendingExternalManager: null,
        pendingOfflineCount: 0,
        _pendingWritableDirs: null,

        // ===== strm 改寫確認 State (90c-T6) =====
        // 存規則後：若映射變更 && media-server && 有既有 strm → heads-up 確認再改寫既有 .strm
        rewriteStrmConfirmOpen: false,
        pendingRewriteCount: 0,

        // ===== Dirty Check State =====
        savedState: null,
        savedOpenaiUseCustomModel: false,
        pendingNavigationUrl: '',
        _configLoading: true,  // 初始 true，loadConfig 完成後 false
        // 95a-T8: filename 膠囊編輯器收斂式 hydrate 就緒旗標（響應式鏡像，供 x-effect 追蹤；
        // naming.ready 是 closure 布林、非響應式，x-effect 追不到）。loadConfig 開頭重設 false、
        // form 設妥後翻 true；由 hydrateFilenameEditor() 讀取觸發 reactive 補載。
        namingConfigReady: false,

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

        // 變數清單單一真理來源（SSOT）：loadConfig 由 /api/config/format-variables fetch。
        // stub `[]` 供 async resolve 前 template binding 不丟 ReferenceError（CD-95a-8）。
        // 每項形 { name:'{num}', description, example, folder_ok }；label 走 i18n（_labelFor）。
        formatVariables: [],
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

        // 命名預覽（依 data 套範例值）。誠實反映後端空值行為（U-A2）：空變數 → 空字串，
        // 殘留分隔符照實呈現、不美化（folderPreviewTextEmpty 用空 actor/suffix 展示）。
        _previewWith(data) {
            const applyTokens = (str) => {
                let out = str;
                for (const [key, val] of Object.entries(data)) {
                    out = out.replace(new RegExp(`\\{${key}\\}`, 'g'), val);
                }
                return out;
            };
            const filenamePreview = applyTokens(this.form.filenameFormat || '{num} {title}');
            if (!this.form.createFolder) return filenamePreview + '.mp4';
            // 剝除資料夾排除 token（{suffix}）後再預覽，與 save 端（saveConfig normalizeFolderLayers）
            // 及 organizer 實際落地一致——否則使用者手打 {suffix} 進資料夾層時，preview 會顯示一層
            // 存檔後其實不會建的 suffix 資料夾（Codex PR #99 P2 連帶：preview 須與 save 同誠實）。
            const folderExcluded = new Set(
                this.formatVariables.filter(v => v.folder_ok === false).map(v => v.name)
            );
            const folderPreview = normalizeFolderLayers(
                this.form.folderLayerList.map(l => l.value.trim()),
                folderExcluded
            )
                .map(applyTokens)
                .join('/');
            const folder = folderPreview ? folderPreview + '/' : '';
            return folder + filenamePreview + '.mp4';
        },

        get folderPreviewText() {
            return this._previewWith(this.FOLDER_PREVIEW_DATA);
        },

        // 空值範例（無演員/無 suffix）：誠實呈現殘留分隔符（U-A2 / CD-95a-11）。
        get folderPreviewTextEmpty() {
            return this._previewWith({ ...this.FOLDER_PREVIEW_DATA, actor: '', actors: '', suffix: '' });
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
            // 資料夾層級改動態清單後，「逐層 enable 級聯清空」邏輯淘汰（增減層直接改陣列，
            // 不需內層有值才解鎖外層）——原 form.folderLayer3/2 兩個 $watch 一併移除（CD-95a-3）。
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

        requestServerModeChange(val) {
            if (this.serverMode === val) return;  // 同模式不觸發確認
            this.serverModeConfirmValue = val;
            this.serverModeConfirmOpen = true;
        },
        async confirmServerModeChange() {
            const val = this.serverModeConfirmValue;  // capture before clearing（防 await 期間再次觸發覆蓋）
            this.serverModeConfirmOpen = false;
            this.serverModeConfirmValue = null;
            await this.setServerMode(val);
        },
        cancelServerModeChange() {
            this.serverModeConfirmOpen = false;
            this.serverModeConfirmValue = null;
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

        // 90c-T5: 全域模式切換破壞性 confirm ─────────────────────────────────────
        // 攔截 external_manager segmented button：即時 fetch 判離線來源 → 有則跳破壞性
        // confirm（消費 T4 POST /api/config/switch-external-manager）→ 成功後同步三處。
        async requestExternalManagerChange(val) {
            if (this.form.externalManager === val) return;  // 同值 no-op（不 fetch、不彈窗）
            let dirs;
            try {
                // 即時 fetch（非快取）：settings 頁 scannerDirectories 只是一次性快照、
                // 無 resync；讀快照會漏觸發本該跳的破壞性 confirm（CD-90b-11 ②）。
                const resp = await fetch('/api/config');
                const result = await resp.json();
                dirs = (result.data && result.data.gallery && result.data.gallery.directories) || [];
            } catch (e) {
                // 保守：fetch 失敗不切換（不 fail-open，避免漏 purge）
                console.warn('[switchMode] requestExternalManagerChange fetch failed:', e);
                return;
            }
            const offline = dirs.filter(d => d && d.readonly === true);
            const writable = dirs.filter(d => !(d && d.readonly === true));
            if (offline.length > 0) {
                // 有離線來源 → 開破壞性 confirm；先不寫 form（按鈕 is-on 仍指舊值＝天然停舊值）
                this.pendingExternalManager = val;
                this.pendingOfflineCount = offline.length;
                this._pendingWritableDirs = writable;
                this.switchModeConfirmOpen = true;
            } else {
                // 無離線來源 → 靜默切換（既有行為，隨後照常按儲存落盤，不呼叫 endpoint）
                this.form.externalManager = val;
            }
        },
        async confirmSwitchMode() {
            const val = this.pendingExternalManager;  // capture before clearing（防 await 期間覆蓋）
            this.switchModeConfirmOpen = false;
            this.pendingExternalManager = null;
            this.pendingOfflineCount = 0;
            const writable = this._pendingWritableDirs;
            this._pendingWritableDirs = null;
            try {
                const resp = await fetch('/api/config/switch-external-manager', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ external_manager: val })
                });
                const result = await resp.json();
                if (result.success === true) {
                    // 同步三處（缺一則前後端不一致，CD-90b-11 / Codex P3）：
                    // ① form.externalManager
                    this.form.externalManager = val;
                    // ② savedState 單 key（externalManager 在 form 內 → 不同步會令 isDirty 誤判；
                    //    只改這一 key，不整份 re-snapshot，保留其他未存 form 編輯的 dirty 態）
                    if (this.savedState) this.savedState.externalManager = val;
                    // ③ 回填 scannerDirectories（非 readonly 子集跨 purge 不變 → 免二次 fetch），
                    //    使 strmTemplateDirs 不再列已 purge 離線來源、無需重載
                    this.scannerDirectories = writable;
                } else {
                    console.warn('[switchMode] confirmSwitchMode failed:', result.error);
                    // Finding 2：產生進行中被擋 → 專屬提示指路（比照 setServerMode 依 reason 分流）。
                    const failKey = result.reason === 'generate_in_progress'
                        ? 'settings.switch_mode_confirm.generate_in_progress'
                        : 'settings.switch_mode_confirm.failed';
                    this.showToast(window.t(failKey), 'error');
                }
            } catch (e) {
                console.warn('[switchMode] confirmSwitchMode error:', e);
                this.showToast(window.t('settings.switch_mode_confirm.failed'), 'error');
            }
        },
        cancelSwitchMode() {
            // 未寫 form → 按鈕自然停舊值、零變更（endpoint 未被呼叫）
            this.switchModeConfirmOpen = false;
            this.pendingExternalManager = null;
            this.pendingOfflineCount = 0;
            this._pendingWritableDirs = null;
        },

        // 90c-T6: 確認 → 呼叫端點實際改寫既有 .strm，toast 顯示端點回的精確 rewritten 數。
        async confirmRewriteStrm() {
            this.rewriteStrmConfirmOpen = false;
            try {
                const resp = await fetch('/api/config/rewrite-strm', { method: 'POST' });
                const result = await resp.json();
                if (result.success) {
                    this.showToast(
                        window.t('settings.scraper.strm_mapping.rewrite_done', { count: result.rewritten }),
                        'success'
                    );
                } else {
                    // 使用者已確認、新映射也已落盤，但既有 .strm 未改寫 → 明確 toast，
                    // 否則使用者誤以為「改規則即改寫」已發生（Codex P2）。可再存一次觸發重試。
                    console.warn('[rewriteStrm] confirmRewriteStrm failed:', result.error);
                    this.showToast(window.t('settings.scraper.strm_mapping.rewrite_failed'), 'error');
                }
            } catch (e) {
                console.warn('[rewriteStrm] confirmRewriteStrm error:', e);
                this.showToast(window.t('settings.scraper.strm_mapping.rewrite_failed'), 'error');
            }
            this.pendingRewriteCount = 0;
        },
        // 取消：規則已存（PUT 已落盤），僅不改寫既有 strm；清狀態即可。
        cancelRewriteStrm() {
            this.rewriteStrmConfirmOpen = false;
            this.pendingRewriteCount = 0;
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
            // 95a-T8: 對稱重設 hydrate 旗標（reset 設定 / 重跑 loadConfig 時需重新 hydrate，
            // 否則 one-shot 會擋住 filename editor 的重新載入）。
            this.namingConfigReady = false;
            naming.filenameHydrated = false;

            try {
                // 命名區變數 SSOT（含 folder_ok 情境旗標）——須在設 folderLayerList（觸發層
                // x-for render + 膠囊 mount）前就緒，故先 await（CD-95a-8）。
                await this._loadFormatVariables();
                naming.ready = true;

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
                    // 資料夾層級 → {id,value}[] 動態清單（外→內序）。folder_layers 陣列語序即
                    // organizer 疊資料夾順序（第 0=最外）。無 folder_layers 時從 folder_format 拆遷。
                    let rawLayers = config.scraper.folder_layers || [];
                    if (rawLayers.length === 0 && config.scraper.folder_format) {
                        rawLayers = config.scraper.folder_format
                            .replace(/\\/g, '/').split('/').filter(p => p.trim());
                    }
                    // 正規化資料夾層（CD-95a-7 保留後端有效前 3 層 + D-A6 移除 {suffix}）。
                    // ⚠ 順序：normalizeFolderLayers 內部**先 slice(0,3) 再剝 {suffix}**——避免前導
                    // suffix-only 層被濾掉後把原第 4 層以上提升成有效層（Codex PR P1）。folderExcluded
                    // 由 SSOT 的 folder_ok===false 推導（fetch 失敗 → 空集合 → 不剝除）。filenameFormat 不動。
                    if (rawLayers.length > 3) {
                        console.debug(`[settings] folder_layers 有 ${rawLayers.length} 層，已正規化為前 3 層（第 4 層以上為後端未使用的死資料）`);
                    }
                    const folderExcluded = new Set(
                        this.formatVariables.filter(v => v.folder_ok === false).map(v => v.name)
                    );
                    this.form.folderLayerList = normalizeFolderLayers(rawLayers, folderExcluded)
                        .map(v => ({ id: naming.layerSeq++, value: v }));

                    this.form.filenameFormat = config.scraper.filename_format;
                    this.form.maxTitleLength = config.scraper.max_title_length;
                    this.form.maxFilenameLength = config.scraper.max_filename_length;
                    this.form.videoExtensions = config.scraper.video_extensions.join(', ');
                    this.form.suffixKeywords = config.scraper?.suffix_keywords || ['-cd1', '-cd2', '-4k', '-uc'];
                    this.form.externalManager = config.scraper?.external_manager || 'off';
                    this.form.downloadSampleImages = config.scraper?.download_sample_images || false;
                    // strm 路徑映射：dict → array（唯一編輯狀態）
                    this.form.strmRules = Object.entries(config.scraper?.strm_path_mappings || {})
                        .map(([local, remote]) => ({ local, remote }));

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
                    this.form.closeAction = config.general?.close_action || 'ask';
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

                    // 命名區膠囊 hydrate（95a-T8）：
                    // - filename：namingConfigReady 翻 true 觸發 #filenameFormat host 的
                    //   x-effect="hydrateFilenameEditor()"（reactive 路徑，覆蓋「mount 早於
                    //   ready」的冷載時序）；mountFilenameEditor 尾端亦呼叫同方法（imperative
                    //   路徑，覆蓋「mount 晚於 ready」）。one-shot（naming.filenameHydrated）
                    //   保證只載一次，避免打斷編輯游標。
                    // - folder：層 editor 於 folderLayerList 設後 x-for render 時，mountLayerEditor
                    //   的 if(naming.ready) 同步 self-hydrate（naming.ready 早在 :574 已 true）。
                    // nexttick-hydrate T4.3：移除既有 $nextTick(_hydrateNamingEditors) 死備援——
                    //   filename 有 x-effect + mountFilenameEditor 兩活觸發、folder 有 mount 時
                    //   self-hydrate，此 tick（及其 _hydrateNamingEditors）全冗餘且複現 95a-T8 冷載
                    //   $nextTick 不 fire 的隱患，故整條移除。
                    this.namingConfigReady = true;

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
                // 90c-T6: 存前「已持久化」的 strm 映射（authoritative：剛 GET 的 config.json）。
                // PUT 成功後與新映射比對，判定「這次儲存是否改動了路徑規則」→ 才提示改寫既有 strm。
                const prevStrmMappings = JSON.stringify(config.scraper?.strm_path_mappings || {});

                // 更新 scraper：動態清單 → string[]（去空層、防禦性再 slice(0,3)；load 已 slice、
                // 此處保險，與後端 layers[:3] 一致，CD-95a-7）。序列化回 config.json 純字串陣列（後端零改）。
                // 剝除資料夾排除 token（{suffix}，Codex PR #99 P2）：chip whitelist 只擋 chip 化，
                // 使用者手打/貼上的 `{suffix}` 仍會以純文字留在 l.value；若原樣存檔，
                // core/organizer.py 的 format_string()（:461 `{suffix}` replace，於 :928 資料夾層
                // 格式化呼叫）仍會消費它，繞過 folder_ok=false 契約建出 suffix-specific 資料夾。
                // load 端（:628-630）已用 normalizeFolderLayers 剝除，此處對齊同一 helper +
                // 同一 folderExcluded 推導（SSOT this.formatVariables），避免兩條剝除邏輯漂移。
                const folderExcluded = new Set(
                    this.formatVariables.filter(v => v.folder_ok === false).map(v => v.name)
                );
                let folderLayers = normalizeFolderLayers(
                    this.form.folderLayerList.map(l => l.value.trim()),
                    folderExcluded
                );
                // Codex PR #99 第二個 P2 fix — 空層 materialize：organizer.py（:914-919）
                // create_folder=true 下若 folder_layers 為空，會 fallback 用 folder_format
                // 拆層、預設 '{num}'。這裡把同一語意在存檔前顯性做掉（folderLayers=['{num}']），
                // 讓 payload 的 folder_layers / folder_format 保持一致、不再依賴後端的隱形 fallback，
                // 也讓下面的 form 回寫（reconcile）有一個非空值可比對/顯示。
                if (folderLayers.length === 0) {
                    folderLayers = ['{num}'];
                }
                // 把 payload 用的正規化/materialize 後 folderLayers 回寫可見 form（與 loadConfig
                // :622-638 的 rawLayers→normalizeFolderLayers→folderLayerList pattern 對稱）。
                // 不回寫會讓 saveConfig 存進 config.json 的值（folder_layers）與使用者仍看到的
                // form.folderLayerList 不同步：
                //   - {suffix} 案：手打 `{maker}{suffix}` 存成 `{maker}`，form 卻還顯示原字串。
                //   - 空層案：清空層存成 `{num}`，form 卻顯示空/無層。
                // 兩案都會讓 savedState（下面於 PUT 成功後從 form 複製）與實際持久化值分岔，
                // dirty=false 但 display≠persisted，要到 reload 才追上。
                // 僅在值序列真的不同才寫回：常見案（乾淨多層、無 {suffix}、非空）不重建
                // chip editor，避免無謂 destroy/remount 造成閃爍或打斷編輯焦點。
                const currentLayerValues = this.form.folderLayerList.map(l => l.value.trim());
                if (JSON.stringify(folderLayers) !== JSON.stringify(currentLayerValues)) {
                    // x-for :key="layer.id"（settings.html:859）換一批新 id 才會讓 Alpine teardown
                    // 舊 chip-editor host、重新掛載 mountLayerEditor（naming.ready 已 true → 掛載時
                    // 立即以新值 self-hydrate，同 loadConfig 側 pattern，見 :637-638 註解）。先
                    // destroy 現有 layerEditors 並清空 naming.layerEditors，避免殘留舊 id 的無主
                    // ChipEditor 實例（不 destroy 的話 naming.layerEditors 會跟 DOM 脫鉤）。
                    for (const ed of Object.values(naming.layerEditors)) ed.destroy();
                    naming.layerEditors = {};
                    this.form.folderLayerList = folderLayers.map(v => ({ id: naming.layerSeq++, value: v }));
                }

                config.scraper = {
                    ...config.scraper,
                    create_folder: this.form.createFolder,
                    folder_layers: folderLayers,
                    folder_format: folderLayers.join('/'),
                    filename_format: this.form.filenameFormat,
                    max_title_length: this.form.maxTitleLength,
                    max_filename_length: this.form.maxFilenameLength,
                    video_extensions: this.form.videoExtensions
                        .split(',').map(s => s.trim()).filter(s => s),
                    suffix_keywords: this.form.suffixKeywords,
                    external_manager: this.form.externalManager,
                    download_sample_images: this.form.downloadSampleImages,
                    // strm 路徑映射：array → dict；local/remote 皆 trim（去貼上殘留空白）。
                    // 兩欄都非空才存（PR #93 P2）：半填規則 {local: ""}（如按範本「填入左欄」
                    // 後未填播放端就存）會讓後端把前綴剝掉只剩後綴、破壞 strm 內容 → 丟棄。
                    strm_path_mappings: Object.fromEntries(
                        this.form.strmRules
                            .filter(r => r.local.trim() && (r.remote || '').trim())
                            .map(r => [r.local.trim(), r.remote.trim()])
                    ),
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
                    close_action: this.form.closeAction,
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
                    // 90c-T6: strm 路徑規則「實際變更」且為 media-server 模式 → dry-run 計數；
                    // 有既有 .strm（count>0）才跳 heads-up 確認。off 模式 / 無映射變更 / 無產出片
                    //（count==0）→ 不提示（規則已存，僅未改寫既有 strm）。
                    const strmChanged =
                        prevStrmMappings !== JSON.stringify(config.scraper?.strm_path_mappings || {});
                    if (strmChanged && ['jellyfin', 'emby', 'kodi'].includes(this.form.externalManager)) {
                        try {
                            const dryResp = await fetch('/api/config/rewrite-strm?dry_run=true', { method: 'POST' });
                            const dryResult = await dryResp.json();
                            if (dryResult.success) {
                                if (dryResult.count > 0) {
                                    this.pendingRewriteCount = dryResult.count;
                                    this.rewriteStrmConfirmOpen = true;
                                }
                            } else {
                                // 規則已落盤但無法檢查既有 .strm → 明確告知（否則使用者不知道改寫流程沒啟動）。
                                console.warn('[rewriteStrm] dry-run failed:', dryResult.error);
                                this.showToast(window.t('settings.scraper.strm_mapping.rewrite_failed'), 'error');
                            }
                        } catch (e) {
                            console.warn('[rewriteStrm] dry-run failed:', e);
                            this.showToast(window.t('settings.scraper.strm_mapping.rewrite_failed'), 'error');
                        }
                    }
                } else if (result.reason === 'generate_in_progress_strm_mapping') {
                    // PR #93 五審三次 P2：掃描/產生進行中改到 strm 播放映射被後端擋下。
                    // 直接顯示後端訊息（非「儲存失敗」誤導前綴）——這是「稍後再試」而非錯誤。
                    this.showToast(result.error, 'warning');
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

        // ===== 命名區膠囊編輯器（feature/95 Part A）=====
        // 舊 insertVariable/appendVariable/formatPreviewHtml（raw input + tag-badge 預覽）由
        // ChipEditor 承接（CD-95a-1/9）。以下為 T6 DOM 掛接的 API。

        // SSOT fetch：/api/config/format-variables → this.formatVariables（含 folder_ok）。
        async _loadFormatVariables() {
            try {
                const resp = await fetch('/api/config/format-variables');
                const data = await resp.json();
                this.formatVariables = Array.isArray(data.variables) ? data.variables : [];
            } catch (e) {
                console.error('[settings] format-variables 載入失敗，命名區變數暫缺', e);
                this.formatVariables = [];
            }
        },

        // 變數 label 走 i18n；端點 name 帶大括號（{num}），key 無括號（settings.var.num），
        // 故 slice(1,-1) 剝括號（Codex P1；膠囊插入/序列化仍用完整 {token}）。
        _labelFor(name) {
            return window.t('settings.var.' + name.slice(1, -1));
        },

        _chipDeleteAria(name) {
            return window.t('settings.scraper.chip_delete') + ' ' + this._labelFor(name);
        },

        // 情境變數集：folder 無 {suffix}（folder_ok=false，CD-95a-6/8）；filename 全集。
        _contextVars(context) {
            return context === 'folder'
                ? this.formatVariables.filter(v => v.folder_ok)
                : this.formatVariables;
        },

        _whitelistFor(context) {
            return new Set(this._contextVars(context).map(v => v.name));
        },

        // T6 變數選單用（name + i18n label）。
        namingMenuVars(context) {
            return this._contextVars(context).map(v => ({ name: v.name, label: this._labelFor(v.name) }));
        },

        // 95a-T8: filename 膠囊編輯器收斂式一次性 hydrator——收斂「editor 已 mount」與
        // 「config 已載入（namingConfigReady）」兩事件，與其先後順序無關；成功一次後 one-shot
        // 擋住重載（避免打斷編輯游標，見 chip-editor.js:108 註解的 hazard）。雙觸發：
        //   ① mountFilenameEditor 尾端 imperative 呼叫（覆蓋 mount 晚於 ready）
        //   ② #filenameFormat host 的 x-effect="hydrateFilenameEditor()"（覆蓋 mount 早於 ready；
        //      namingConfigReady flip true 時 effect 重跑補載）
        // guard 順序刻意：filenameHydrated 必須在讀 form.filenameFormat 之前 return，否則 x-effect
        // 會追蹤 form.filenameFormat、之後每次編輯 onChange 改該欄位都會讓 effect 重跑重載。
        hydrateFilenameEditor() {
            if (!this.namingConfigReady) return;
            if (!naming.filenameEditor) return;
            if (naming.filenameHydrated) return;
            naming.filenameHydrated = true;
            naming.filenameEditor.whitelist = this._whitelistFor('filename');
            naming.filenameEditor.load(this.form.filenameFormat);
        },

        // 檔名格式膠囊編輯器 mount（T6 x-init）。onChange serialize 寫回 form.filenameFormat。
        mountFilenameEditor(hostEl) {
            naming.filenameEditor = new ChipEditor(hostEl, {
                whitelist: this._whitelistFor('filename'),
                labelFor: (n) => this._labelFor(n),
                deleteAriaFor: (n) => this._chipDeleteAria(n),
                onChange: () => { this.form.filenameFormat = naming.filenameEditor.serialize(); },
                placeholder: '[{num}][{maker}] {title}{suffix}',
            });
            // 95a-T8: 觸發點一（imperative）——ready 已 true 時（mount 晚於 ready）直接補載；
            // ready 仍 false 時 hydrateFilenameEditor() 內部早退，交給觸發點二（x-effect）補上。
            this.hydrateFilenameEditor();
        },

        // 資料夾層膠囊編輯器 mount（T6 x-init per layer）。onChange 以 layer.id find 寫回 value
        // （非位置索引，CD-95a-12）。
        mountLayerEditor(hostEl, layerId) {
            const ed = new ChipEditor(hostEl, {
                whitelist: this._whitelistFor('folder'),
                labelFor: (n) => this._labelFor(n),
                deleteAriaFor: (n) => this._chipDeleteAria(n),
                onChange: () => {
                    const l = this.form.folderLayerList.find(x => x.id === layerId);
                    if (l) l.value = ed.serialize();
                },
                placeholder: window.t('settings.scraper.layer_placeholder'),
            });
            naming.layerEditors[layerId] = ed;
            if (naming.ready) {
                const l = this.form.folderLayerList.find(x => x.id === layerId);
                ed.whitelist = this._whitelistFor('folder');
                ed.load(l ? l.value : '');
                ed.setDisabled(!this.form.createFolder);
            }
        },

        insertFilenameVar(name) { naming.filenameEditor?.insertVar(name); },
        insertLayerVar(layerId, name) { naming.layerEditors[layerId]?.insertVar(name); },

        // 動態層增減（CD-95a-3/7/12）。硬上限 3；刪層 destroy 該 editor + 移除 id 物件（keyed teardown）。
        addFolderLayer() {
            if (this.form.folderLayerList.length >= 3) return;
            this.form.folderLayerList.push({ id: naming.layerSeq++, value: '' });
        },
        removeFolderLayer(layerId) {
            naming.layerEditors[layerId]?.destroy();
            delete naming.layerEditors[layerId];
            this.form.folderLayerList = this.form.folderLayerList.filter(l => l.id !== layerId);
        },

        // create_folder gating（T6 x-effect 綁 form.createFolder）：整段 folder 編輯 disabled。
        setFolderEditingDisabled(disabled) {
            for (const ed of Object.values(naming.layerEditors)) ed.setDisabled(disabled);
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
        // strm 路徑映射（spec 90a）— array 短狀態編輯器，dict 於 load/save 對稱轉換
        // ═══════════════════════════════════════════════════════════════

        // 範本回顯：唯讀 media-server 來源的掃描路徑（顯示形，可預填左欄）。
        // scannerDirectories 由 state-ui.js _initB1() 載入；dirPath / window.pathToDisplay 為既有共用純函式。
        get strmTemplateDirs() {
            return (this.scannerDirectories || [])
                .filter(d => d && d.readonly === true)
                .map(d => window.pathToDisplay(this.dirPath(d)))
                .filter(p => p);
        },

        addStrmRule() {
            this.form.strmRules.push({ local: '', remote: '' });
        },

        removeStrmRule(idx) {
            this.form.strmRules.splice(idx, 1);
        },

        // 範本「填入左欄」：填最近的空 local 行，否則 push 新行
        useTemplate(pathStr) {
            const empty = this.form.strmRules.find(r => !r.local.trim());
            if (empty) {
                empty.local = pathStr;
            } else {
                this.form.strmRules.push({ local: pathStr, remote: '' });
            }
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
