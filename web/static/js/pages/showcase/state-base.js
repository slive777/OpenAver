/**
 * state-base.js — Showcase ESM foundation（54b-T1a）
 *
 * module-level exports（共用陣列、helpers）+ stateBase() factory。
 * 不含 openLightbox / closeLightbox（屬 state-lightbox.js）。
 * Picker 常數屬 stateLightbox() 閉包（OQ-54B-2 Option B），不在此模組。
 */

// 101d-T1：影片焦點 icon gate 的 page-level narrow matchMedia listener 用（init 內註冊）。
// 門檻 reuse 既有單一真理常數，不裸寫 899（plan-101d CD-1）。
import { POSTER_CROP_MAX_W } from '@/shared/breakpoints.js';
import { serializePills, deserializePills } from '@/shared/pill-filter.js';
import { computeBadges, resolveEnabledIds } from '@/shared/cover-badges.js';
import { formatPartLabel } from '@/shared/part-label.js';
import { computeActorAgesMap, singleActorAge } from '@/shared/actress-release-age.js';

// 53a codex F3: $persist 對 localStorage 壞 JSON 沒 try/catch（會在 Alpine init 階段拋錯炸整頁），
// 必須在 Alpine.data 註冊前先清掃壞值，讓 $persist fallback 走預設物件
(function _safeCleanShowcaseState() {
    try {
        var raw = localStorage.getItem('showcase_state');
        if (raw !== null) JSON.parse(raw);
    } catch (e) {
        try { localStorage.removeItem('showcase_state'); } catch (_) { /* storage unavailable */ }
        console.warn('[Showcase] cleared corrupt showcase_state from localStorage:', e);
    }
})();

// F1: 大陣列移出 Alpine reactive scope — Alpine 不追蹤
export var _videos = [];
export var _filteredVideos = [];
export var _actresses = [];
export var _filteredActresses = [];
export var _actressesLoaded = false;
export function _setActressesLoaded(v) { _actressesLoaded = v; }
export function _setVideos(v) {
    _videos.length = 0;
    for (const item of (v || [])) _videos.push(item);
}
export function _setFilteredVideos(v) {
    _filteredVideos.length = 0;
    for (const item of (v || [])) _filteredVideos.push(item);
}
export function _setActresses(v) {
    _actresses.length = 0;
    for (const item of (v || [])) _actresses.push(item);
}
export function _setFilteredActresses(v) {
    _filteredActresses.length = 0;
    for (const item of (v || [])) _filteredActresses.push(item);
}
export var _nameToGroup = {};  // { "舊名": ["新名", "舊名"], "新名": [...] } 雙向 alias map
export var _aliasMapLoaded = false;

/**
 * TASK-138-T1（CD-C3）：逾時降級包裝。逾時後立即 resolve，但不取消原 promise
 * （不得用 Promise.race 丟棄）。角色是卡死保險，不是 API 預算。
 * module-level export（比照 _loadAliasMap）——pill-hero.test.mjs 的 makeComponent
 * 不含 state-base 方法；若寫成 factory method，runInitReconcileLine eval 會 TypeError。
 */
export var HERO_CARD_RECONCILE_TIMEOUT_MS = 300;
export function _awaitHeroCardWithTimeout(promise) {
    return new Promise((resolve) => {
        const timer = setTimeout(resolve, HERO_CARD_RECONCILE_TIMEOUT_MS);
        Promise.resolve(promise).finally(() => { clearTimeout(timer); resolve(); }).catch(() => {});
    });
}

/**
 * 45-P2 fix: 獨立載入 alias map，init() 時無條件呼叫。
 * 冪等：已載入時直接 return。
 */
export async function _loadAliasMap() {
    if (_aliasMapLoaded) return;
    try {
        var resp = await fetch('/api/actress-aliases');
        if (resp.ok) {
            var data = await resp.json();
            var groups = (data && data.groups) || [];
            _nameToGroup = {};
            groups.forEach(function(g) {
                var all = [g.primary_name].concat(g.aliases || []);
                all.forEach(function(n) { _nameToGroup[n.toLowerCase()] = all; });
            });
        }
    } catch (e) {
        console.warn('[Showcase] Failed to fetch actress aliases:', e);
        _nameToGroup = {};
    }
    _aliasMapLoaded = true;
}

export var _tagToGroup = {};  // { "女僕": ["メイド", "女僕", "女傭"], ... } 雙向 tag alias map
export var _tagAliasMapLoaded = false;

/**
 * A3-4: 獨立載入 tag alias map，init() 時無條件呼叫（在 _loadAliasMap 之後）。
 * 冪等：已載入時直接 return。
 * 結構鏡射 _loadAliasMap()，API 改為 /api/tag-aliases。
 */
export async function _loadTagAliasMap() {
    if (_tagAliasMapLoaded) return;
    try {
        var resp = await fetch('/api/tag-aliases');
        if (resp.ok) {
            var data = await resp.json();
            var groups = (data && data.groups) || [];
            _tagToGroup = {};
            groups.forEach(function(g) {
                var all = [g.primary_name].concat(g.aliases || []);
                all.forEach(function(n) { _tagToGroup[n.toLowerCase()] = all; });
            });
        }
    } catch (e) {
        console.warn('[Showcase] Failed to fetch tag aliases:', e);
        _tagToGroup = {};
    }
    _tagAliasMapLoaded = true;
}

export var _coverBadgeManifestLoaded = false;
export var _coverBadgeRules = [];

/**
 * 121c-T2: N 元 alias 群組合併。對每個成員取 map 中既有群組，與 members 自身取聯集
 * （大小寫不敏感去重、保留第一次出現的原字面），再把同一個 union 陣列指給每個成員。
 * hasOwnProperty + Array.isArray 雙重把關（121b Opus review 針對原型污染加的，不可繞過）。
 * members 內的 falsy 值直接跳過；全部跳過後 map 不變。
 */
export function _mergeAliasGroup(map, members) {
    var union = [];
    var seen = {};
    function add(val) {
        if (!val) return;
        var k = String(val).toLowerCase();
        if (Object.prototype.hasOwnProperty.call(seen, k)) return;
        seen[k] = true;
        union.push(val);
    }
    function existing(key) {
        if (Object.prototype.hasOwnProperty.call(map, key) && Array.isArray(map[key])) {
            return map[key];
        }
        return [];
    }
    members.forEach(function (member) {
        if (!member) return;
        existing(String(member).toLowerCase()).forEach(add);
        add(member);
    });
    union.forEach(function (member) {
        map[String(member).toLowerCase()] = union;
    });
}

export function _mergeAliasPair(map, a, b) {
    return _mergeAliasGroup(map, [a, b]);
}

/**
 * 121c-T2: 把 [canonical_tag, ...match_aliases] 整組併入既有 _tagToGroup（聯集疊加，不清空），
 * 並把 manifest 原文留在 _coverBadgeRules。display_name 不參與合併。
 * 失敗語意刻意不同於 _loadTagAliasMap()：catch / 非 2xx / 非陣列時不動 _tagToGroup，
 * 且 _coverBadgeRules 維持 []。
 */
export async function _loadCoverBadgeManifest() {
    if (_coverBadgeManifestLoaded) return;
    try {
        var resp = await fetch('/api/cover-badges/manifest');
        if (resp.ok) {
            var data = await resp.json();
            if (Array.isArray(data)) {
                data.forEach(function (item) {
                    if (!item) return;
                    var canonical = item.canonical_tag;
                    if (!canonical) return;
                    var aliases = Array.isArray(item.match_aliases) ? item.match_aliases : [];
                    _mergeAliasGroup(_tagToGroup, [canonical].concat(aliases));
                });
                _coverBadgeRules = data;
            }
        }
    } catch (e) {
        console.warn('[Showcase] Failed to fetch cover badge manifest:', e);
    }
    _coverBadgeManifestLoaded = true;
}

function _resolveCoverBadgeEnabledIds() {
    // window 在 node:test 不存在；沿用 restoreState 的 `window.__SHOWCASE_CONFIG__ || {}`
    var showcaseCfg = (typeof window !== 'undefined' && window.__SHOWCASE_CONFIG__) || {};
    return resolveEnabledIds(_coverBadgeRules, showcaseCfg.cover_badges);
}

/**
 * 121c-T3: 單片寫入 video._badges。enabledIds 可傳入（全量重算時只算一次）；
 * 省略則現讀 config。video 為 falsy 直接 return。
 */
export function _recomputeVideoBadges(video, enabledIds) {
    if (!video) return;
    var ids = Array.isArray(enabledIds) ? enabledIds : _resolveCoverBadgeEnabledIds();
    video._badges = computeBadges(video, _coverBadgeRules, _tagToGroup, ids);
}

/**
 * 121c-T3: 對 _videos 每一筆呼叫 _recomputeVideoBadges。enabledIds 只算一次。
 */
export function _recomputeAllBadges() {
    var enabledIds = _resolveCoverBadgeEnabledIds();
    for (var i = 0; i < _videos.length; i++) {
        _recomputeVideoBadges(_videos[i], enabledIds);
    }
}

export function _recomputeCardActorAges(video) {
    if (!video) return;
    video._cardActorAges = computeActorAgesMap(video, _actresses, _nameToGroup);
}

// 41c B-lite: 無封面 placeholder SVG (cover 載入失敗時 handleCoverError 換上)
// viewBox 800x600 對齊 lightbox 4:3，grid card aspect-ratio:3/2 會 crop 上下少許但不影響 icon 居中
// 設計：暗色漸層背景 + 中央 image-frame icon (邊框+太陽+山形)
//
// 41d-T4: 純圖示 empty state，不含文字。
// 理由：_NO_COVER_PLACEHOLDER 是 module-level IIFE，JS 載入時 window.t() i18n 函數
// 尚未就緒，無法呼叫；hardcoded 中文違反 i18n 規則。image-frame icon 是業界通用的
// no-image pattern，視覺語意已足夠清晰，互動 CTA 交給既有的 enrich icon。
// 若未來必須加文字說明，需改為 lazy generation function（延遲至 i18n 初始化後呼叫）。
export var _NO_COVER_PLACEHOLDER = (function () {
    var svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 600'>"
        + "<defs><linearGradient id='bg' x1='0' y1='0' x2='0' y2='1'>"
        + "<stop offset='0%' stop-color='#1c1c1e'/>"
        + "<stop offset='100%' stop-color='#0a0a0c'/>"
        + "</linearGradient></defs>"
        + "<rect width='800' height='600' fill='url(#bg)'/>"
        + "<rect x='0.5' y='0.5' width='799' height='599' fill='none' stroke='rgba(255,255,255,0.06)'/>"
        + "<g transform='translate(280,170)' stroke='rgba(255,255,255,0.22)' stroke-width='6' fill='none' stroke-linejoin='round' stroke-linecap='round'>"
        + "<rect x='0' y='0' width='240' height='180' rx='14'/>"
        + "<circle cx='68' cy='56' r='18' fill='rgba(255,255,255,0.18)' stroke='none'/>"
        + "<path d='M 26 158 L 100 84 L 156 134 L 218 78 L 218 174 L 26 174 Z' fill='rgba(255,255,255,0.10)'/>"
        + "</g>"
        + "</svg>";
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
})();

/**
 * T20 fallback helper — Lightbox timeline kill
 *
 * 優先委派給 ShowcaseAnimations.killLightboxAnimations（animations.js 已封裝 C18 邏輯）。
 * 若 animations.js 未載入但 gsap 仍可用（例如 CDN 載入時序差異），直接用 gsap.getById 清理
 * 進行中的 timeline，避免 stale callback 在 lightbox 關閉後繼續操作 DOM / state。
 *
 * @param {Object} [options={}]
 * @param {boolean} [options.killOpen=true]   是否 kill showcaseLightboxOpen timeline
 * @param {boolean} [options.killSwitch=true] 是否 kill showcaseLightboxSwitch timeline
 */
export function _killLightboxTimelines(options) {
    if (window.ShowcaseAnimations?.killLightboxAnimations) {
        window.ShowcaseAnimations.killLightboxAnimations(options);
    } else if (typeof gsap !== 'undefined') {
        var opts = options || {};
        var killOpen  = opts.killOpen  !== false;
        var killSwitch = opts.killSwitch !== false;
        if (killOpen)   gsap.getById('showcaseLightboxOpen')?.kill();
        if (killSwitch) gsap.getById('showcaseLightboxSwitch')?.kill();
    }
}

export function stateBase() {
    return {

        // 56c-fix: similar exit standalone video — 當 _similarLastDrilledNumber 不在 _filteredVideos 時，
        // closeSimilarMode 直接把 similarResults 的最後鑽入 item 包成 standalone lightbox source。
        // null = 非 standalone 模式（既有 _filteredVideos 路徑）；
        // non-null = standalone 模式：currentLightboxVideo 顯示此物件，prev/next 暫禁。
        similarExitVideo: null,

        // 186-T6: warmup 回傳的可融合番號（大寫去重陣列；整個重新賦值）
        boostedNumbers: [],

        // 53a-T2: 持久化容器（$persist 自動同步 localStorage 的 'showcase_state' key）
        // sort/order/actressSort/actressOrder 用 null sentinel，讓 restoreState 走 URL > _persisted > config > fallback 優先序
        _persistedShowcase: this.$persist({
            sort: null,
            order: null,
            page: 1,
            search: '',
            mode: 'grid',
            showFavoriteActresses: false,
            actressSort: null,
            actressOrder: null,
            actressSortVersion: 0,
            actressSearch: '',
            pills: [],
            cardShape: 'cover',
            infoVisible: false,
        }).as('showcase_state'),

        // --- 狀態變數 ---
        loading: true,
        error: '',           // 錯誤訊息（API 失敗時顯示）
        videoCount: 0,        // _videos.length 的 reactive scalar
        filteredCount: 0,     // _filteredVideos.length 的 reactive scalar
        paginatedVideos: [],  // 當前頁顯示的影片
        unreachableSources: [],  // /api/showcase/source-status（unreachable / no_permission）

        // Card Info 展開狀態 (M3i)
        infoVisible: false,

        // Toolbar Dropdown 狀態
        sortOpen: false,
        modeOpen: false,

        search: '',
        pills: [],  // TASK-115-T1: metadata pill filter（reactive only；持久化屬 T3）
        actressPills: [],  // TASK-116a-T2: 女優數值 pill（reactive only；不持久化 CD-116a-5）
        // TASK-116b-T2：浮層草稿（null=關閉）與桌機閘門（CD-116b-5 / CD-116b-8）
        // factory 初值比照 state-lightbox.js _isNarrow：就地求值一次；init() re-sync 是第二次。
        _pillEditor: null,
        // TASK-124a-T2：發售日 pill 浮層草稿獨立 slot（CD-124a-4，不與 _pillEditor 共用一個欄位）。
        _releaseEditor: null,
        _pillPopoverEnabled: (typeof window.matchMedia === 'function')
            ? !window.matchMedia('(max-width: 480px)').matches
            : (window.innerWidth > 480),
        sort: 'date',         // M2a 先用硬編碼，M4 才從 config/localStorage 恢復
        order: 'desc',
        mode: 'grid',
        cardShape: 'cover',   // TASK-119-T3: 'cover' | 'poster'；只走 localStorage
        page: 1,
        perPage: 90,
        totalPages: 1,
        _animGeneration: 0,  // B13: 防止 stale deferred callback
        _heroCardReconcilePending: false,  // TASK-138-T1（CD-C5）：init first-frame 窗口；非 $persist

        // --- 生命週期 ---
        async init() {
            // TASK-142-T4: fire-and-forget 來源可達性；失敗靜默，不進 await 鏈。
            fetch('/api/showcase/source-status')
                .then(r => r.ok ? r.json() : [])
                .then(list => { this.unreachableSources = Array.isArray(list) ? list : []; })
                .catch(() => {});

            // 接入 page lifecycle：清理 lightbox timer 和 body class
            if (window.__registerPage) {
                window.__registerPage({
                    cleanup: () => {
                        this._animGeneration++;       // B13: 使 pending deferred callback 失效
                        this._lightboxGeneration++;   // B19: invalidate pending $nextTick lightbox callbacks
                        if (this.lightboxCloseTimer) clearTimeout(this.lightboxCloseTimer);  // F2: cleanup delayed clear timer
                        window.Alpine?.store?.('toast')?.hide?.();   // 131b-T3：cleanup 不得拋錯（拋了會跳過後面所有 teardown）
                        if (this.lightboxOpen) document.body.classList.remove('overflow-hidden');
                        this._resetPicker();                                  // 53a-T1: 清場 picker 狀態（含 abort _pickerReadyAbort）
                        // nexttick-hydrate P2-2：離頁時 mobile 面板不走 closeMobilePanel（僅 matchMedia
                        // 960 觸發），故其 in-flight waitForMount observer 不會被 abort → 顯式收（與
                        // _resetPicker 對稱，冪等）。
                        this._mobileReadyAbort?.abort();
                        this._mobileReadyAbort = null;
                        window.GhostFly?.cleanupStaleGhosts?.();              // 53a-T1: 移除殘留 ghost（沿 v0.8.1 T4 optional-chaining pattern）
                        if (this._scrollHideHandler) window.removeEventListener('scroll', this._scrollHideHandler);  // T1: cleanup scroll collapse listener
                        if (this._narrowMq && this._narrowHandler) this._narrowMq.removeEventListener('change', this._narrowHandler);  // 101d-T1: page-level narrow gate listener（與 init 註冊對稱）
                        if (this._pillMq && this._pillHandler) this._pillMq.removeEventListener('change', this._pillHandler);  // 116b-T2: pill 浮層桌機閘門（與 init 註冊對稱）
                    }
                });
            }

            this.restoreState();        // M2c: 先恢復狀態
            const savedPage = this.page;

            // TASK-138-T1（CD-C1）：提前啟動 hero 卡判斷，與 fetchVideos() 平行。
            // 保留 promise，稍後在 applyFilterAndSort 之前 await——不是 fire-and-forget。
            this._heroCardReconcilePending = true;   // CD-C5：init 作用域旗標，非持久化
            var heroCardPromise = this.showFavoriteActresses ? Promise.resolve() : this._reconcileHeroCard();  // 單行：pill-hero.test.mjs 以單行 regex 擷取本行並 eval，勿換行

            await this.fetchVideos();
            // 57e hotfix：fire-and-forget warm-up SimilarRankerCache，避免 magic icon 首次點擊 cold-start race。
            // 186-T6：讀 boosted_numbers（缺欄／失敗 → []）；仍 fire-and-forget，不拖慢 init。
            fetch('/api/similar/warmup')
                .then((res) => (res.ok ? res.json() : null))
                .then((data) => {
                    const raw = data && Array.isArray(data.boosted_numbers)
                        ? data.boosted_numbers : [];
                    const seen = new Set();
                    const out = [];
                    for (const n of raw) {
                        const u = String(n || '').toUpperCase();
                        if (!u || seen.has(u)) continue;
                        seen.add(u);
                        out.push(u);
                    }
                    this.boostedNumbers = out;
                })
                .catch(() => {
                    this.boostedNumbers = [];
                });
            await _loadAliasMap();      // 45-P2: 無條件載入 alias map（影片搜尋也需要）
            await _loadTagAliasMap();   // A3-4: 無條件載入 tag alias map
            await _loadCoverBadgeManifest();
            _recomputeAllBadges();
            // 149b-T3 CD-149b-2：燈箱女優列的發行時年齡（_refreshLbActorAges）需要
            // _actresses/_nameToGroup 就緒，不能只在「女優模式」開著時才載入。
            // Codex review（149b P2）：above 的 hero-card 分支（:362）可能已經在
            // fetchVideos()／alias map 幾個 await 之間 settle 成功；若這裡仍無條件
            // 再發一次請求，第二次若暫時失敗，統一清理會把第一次已成功載入的資料清空。
            // 改成只在「還沒成功載入」時才呼叫——失敗時 _actressesLoaded 會被
            // _clearActressesOnLoadFailure() 明確設回 false（CD-149b-2 第 3 項），
            // 這個閘不會擋住重試路徑。
            if (!_actressesLoaded) this.loadActresses();

            // CD-C3：逾時降級，不取消 in-flight 判斷
            await _awaitHeroCardWithTimeout(heroCardPromise);
            this._heroCardReconcilePending = false;   // CD-C5：first-frame 窗口結束

            this.applyFilterAndSort(true);  // M4a: 套用搜尋篩選（跳過 pagination，下面統一處理）
            // 129-T3 的回頁重算已提前到 restoreState 之後平行啟動（見上），此處不再呼叫
            this.page = savedPage;          // 恢復儲存的頁碼
            this.updatePagination();        // 單次分頁（會 clamp 超出範圍的頁碼）

            // Settle: 初次載入用 settle（不碰 opacity → 不閃）
            if (this.mode === 'grid') {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;  // stale
                    var grid = this._getActiveGrid();
                    window.ShowcaseAnimations?.playSettle?.(grid);
                }); });
            }

            // 83b-T1 (D12 / R7): 跨 960 breakpoint reset 行動相似面板。
            // CSS @media (min-width:960px) display:none 藏面板，但 flag 殘留會卡住
            // lightbox trap 的 `&& !similarModeMobileOpen`（iPad 旋轉）→ 強制 closeMobilePanel。
            // 註冊在合併 init（單一 lifecycle，不另開競爭 hook）；closeMobilePanel 屬 state-similar
            // 同一 Alpine 元件可達（main.js mergeState）。
            if (typeof window.matchMedia === 'function') {
                const mq = window.matchMedia('(min-width: 960px)');
                mq.addEventListener('change', (e) => {
                    if (e.matches && this.similarModeMobileOpen) {
                        this.closeMobilePanel();
                    }
                });
            }

            // 101d-T1：影片焦點 icon gate 的 page-level narrow listener（plan-101d §3.2）。
            // 掛在頁面 component 生命週期（此 init + __registerPage cleanup），**不掛 lightbox 開關**——
            // showcase component 關燈箱後仍存活，若在 closeLightbox 移除，reopen 後 resize 就不再更新
            // gate。門檻 reuse POSTER_CROP_MAX_W（CD-1，不裸寫 899）。_isNarrow 宣告在 state-lightbox.js，
            // 經 mergeState 合併為同一 reactive 屬性（見該檔 _isNarrow 註解）。缺 matchMedia 的嵌入
            // 環境無 listener 可掛也無妨（那類環境本就寬螢幕桌面、非 ≤899 目標情境）。
            // 🔴 101d P1（Codex 2026-07-18）：本 init 是 async，listener 註冊在多個 await
            // （fetchVideos/loadAliasMap/loadTagAliasMap）之後；而 _isNarrow 的初值是在 component
            // 建立（factory）當下取樣的。若載入期間視窗跨過 899（例如桌面開頁、載入中縮到窄），該
            // change 事件落在 listener 尚未存在時 → 永久遺失、_isNarrow 卡舊值直到下次跨界 resize。
            // 修法：addEventListener 後立刻用 mq.matches 重新同步一次（與 addEventListener 同步相鄰、
            // 無 await 夾在中間 → 零殘留窗）。
            if (typeof window.matchMedia === 'function') {
                this._narrowMq = window.matchMedia('(max-width: ' + POSTER_CROP_MAX_W + 'px)');
                this._narrowHandler = (e) => { this._isNarrow = e.matches; };
                this._narrowMq.addEventListener('change', this._narrowHandler);
                this._isNarrow = this._narrowMq.matches;   // re-sync：補回 factory 初值到本行之間的跨界事件
            }

            // 116b-T2：pill 浮層桌機閘門（CD-116b-8 / CD-116b-8b）。
            // 比照上方 _narrowMq 的 101d P1 re-sync：addEventListener 後立刻再讀 matches，
            // 兩行相鄰、中間不得夾 await。跨進 ≤480 時與更新 _pillPopoverEnabled 同一次求值
            // 做 _pillEditor teardown（不另開第二個 listener）。
            if (typeof window.matchMedia === 'function') {
                this._pillMq = window.matchMedia('(max-width: 480px)');
                this._pillHandler = (e) => {
                    this._pillPopoverEnabled = !e.matches;
                    // TASK-124a-T2：跨切面 teardown 收斂到單一函式（_teardownPillEditors，
                    // state-videos.js），同時清 _pillEditor 與 _releaseEditor 兩個 slot。
                    if (e.matches) this._teardownPillEditors();
                };
                this._pillMq.addEventListener('change', this._pillHandler);
                this._pillPopoverEnabled = !this._pillMq.matches;   // re-sync：補回 factory 初值到本行之間的跨界事件
                if (this._pillMq.matches) this._teardownPillEditors();
            }

            // T1: Mobile scroll-to-collapse — 往下滾超過 50px（相對 toolbar 展開當下 Y）自動收合
            // （≤480px，**沒有任何啟用中篩選時**）
            let _toolbarOpenY = null
            const COLLAPSE_THRESHOLD = 50
            const _scrollHandler = () => {
                if (!window.matchMedia('(max-width: 480px)').matches) return
                const isOpen = Alpine.store('ui').toolbarOpen
                if (!isOpen) { _toolbarOpenY = null; return }
                if (_toolbarOpenY === null) _toolbarOpenY = window.scrollY
                // 115 PR#131 P3／129-T1a：改用 _hasActiveFilterForCurrentTab()（含 pills、分頁感知），
                // 與 showcaseHasSearch 同一個判準。兩者必須同步，否則自相矛盾：navbar 那顆鈕在
                // showcaseHasSearch 為真時變成 ✕，按下去是 clear-search 全清、**不再是展開工具列**
                // （base.html:502-505）。手機上只用 pill 篩選（沒打字）時，若這裡仍只看文字欄位，
                // 捲動就會把裝著 pill 的工具列收掉，而唯一的重新開啟入口已經變成「全部清掉」——
                // 使用者再也無法只移除其中一枚 pill。
                // （actressSearch 來自 state-actress.js merge，pills 來自本檔）
                if (this._hasActiveFilterForCurrentTab()) return
                if (window.scrollY - _toolbarOpenY > COLLAPSE_THRESHOLD) {
                    Alpine.store('ui').toolbarOpen = false
                    _toolbarOpenY = null  // reset: 下次 reopen 從新基準計，防 stale baseline 立即再收
                }
            }
            window.addEventListener('scroll', _scrollHandler, { passive: true })
            this._scrollHideHandler = _scrollHandler

            // T2/115-T7／129-T1a：有效搜尋（含 pill）時 header icon 切換為 X。五個 $watch 與 init
            // 同步都呼叫同一個 _hasActiveFilterForCurrentTab()（CD-12／CD-129-1：不寫兩份判準）。
            this.$watch('search', () => {
                Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();
            })
            this.$watch('actressSearch', () => {
                Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();
            })
            // 115-T7：pills 依 CD-3 慣例整包替換，$watch 對此可靠觸發（見 TASK-115-T7 現況分析）。
            this.$watch('pills', () => {
                Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();
            })
            // 116a-T2：actressPills 同慣例整包替換，$watch 對此可靠觸發（CD-116a-2d）。
            this.$watch('actressPills', () => {
                Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();
            })
            // 129-T1a：判準改成依分頁二選一之後，切分頁本身也要重算——切分頁不會改動
            // search/actressSearch/pills/actressPills 任何一個，上面四個 watcher 一個都不會 fire，
            // 而 toggleActressMode()（state-actress.js:200）也沒有碰 showcaseHasSearch。
            this.$watch('showFavoriteActresses', () => {
                Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();
            })
            // T2 init sync：restoreState() 在 $watch 前執行，初始值不會觸發上面任何一個 watcher
            Alpine.store('ui').showcaseHasSearch = this._hasActiveFilterForCurrentTab();

            // 98b-T4：換片 reset 遮罩（結構性涵蓋四條換片路徑——皆最終改 currentLightboxVideo）。
            // A 片開遮罩翻 auto → 不關直接換 B → 舊片未提交態不落 B 的 DB（_maskSession guard + 此 reset）。
            this.$watch('currentLightboxVideo?.path', () => { if (this._maskVisible) this._resetMask(); })
            // 100b-T2a（§B-1c 姊妹 watcher）：actress→actress 切換用（x-if 不重新掛載，watcher
            // 夠用）。video→actress／actress→video 的掛載瞬間已由 _setActressLightboxIndex()／
            // prevLightboxVideo()／nextLightboxVideo() 內的同步 _resetMask() 擋住（gotchas-frontend
            // §8b：watcher 是非同步 effect flush，對掛載那一幀擋不住），本 watcher 是 actress→actress
            // 場景的主力 + 其餘場景的 defense-in-depth。既有 gate 寫法照抄，不「修正」
            // （state-lightbox.js:1027-1029 一類註解落差屬影片路徑既有碼，範圍外）。
            this.$watch('currentLightboxActress?.name', () => { if (this._maskVisible) this._resetMask(); })
        },

        // 129-T1a / CD-129-1：分頁感知的「是否有啟用中篩選」判準——只看當前分頁。
        // 影片牆看 search/pills，女優牆看 actressSearch/actressPills，互不干涉。
        _hasActiveFilterForCurrentTab() {
            if (this.showFavoriteActresses) {
                return this.actressSearch !== '' || this.actressPills.length > 0;
            }
            return this.search !== '' || this.pills.length > 0;
        },

        // --- 狀態恢復 (M2c) ---
        restoreState() {
            // 1. 從 config 取得預設值
            const cfg = window.__SHOWCASE_CONFIG__ || {};
            // TASK-133b-T2：嚴格 === true（FE-JS-01；宣告在 state-videos.js）
            this.showTableList = cfg.show_table_list === true;
            const defaultSort = cfg.default_sort || 'date';
            const defaultOrder = cfg.default_order === 'ascending' ? 'asc' : 'desc';
            // T3.2 P2 fix: `??` 而非 `||` — Settings 允許 items_per_page=0（"全部"語意），
            // 必須保留 numeric 0 讓下方 grid+perPage=0→120 降級邏輯有機會觸發。
            const defaultPerPage = cfg.items_per_page ?? 90;

            // 2. 從 _persistedShowcase（$persist 自動讀的 localStorage 'showcase_state'）取
            //    53a-T2: 取代手寫 localStorage.getItem + JSON.parse，格式向後相容
            const state = this._persistedShowcase || {};

            // 3. 從 URL params 恢復（最高優先）
            const urlParams = new URLSearchParams(window.location.search);

            // 4. 優先序：URL > _persistedShowcase > config > fallback
            //    sort/order/actressSort/actressOrder 在 _persisted 用 null sentinel，新用戶會透下到 config
            //    urlNum: 取 URL 數值參數，空字串視為無值（避免 parseInt("") → NaN）
            const urlNum = (key) => { const v = urlParams.get(key); return v !== null && v !== '' ? v : undefined; };
            this.sort = urlParams.get('sort') || state.sort || defaultSort;
            this.order = urlParams.get('order') || state.order || defaultOrder;
            // T3.2 (CD-52-3): perPage 只從 cfg.items_per_page，URL params + localStorage 不再參與
            // 既有 user 的 localStorage state.perPage / URL ?perPage=N 被 silently 忽略（CD-52-4）
            this.perPage = defaultPerPage;
            this.page = parseInt(urlNum('page') ?? state.page ?? 1) || 1;
            this.search = urlParams.get('search') || state.search || '';
            this.pills = deserializePills(state.pills);
            this.mode = urlParams.get('mode') || state.mode || 'grid';
            if (!['grid', 'table', 'list'].includes(this.mode)) this.mode = 'grid';
            if (!this.showTableList && this.mode !== 'grid') this.mode = 'grid';
            // F2: grid + perPage=0 組合降級（settings 若存 items_per_page=0 之防呆）
            if (this.mode === 'grid' && this.perPage === 0) {
                this.perPage = 120;
            }
            // ★ 44a: 女優模式 — 只從 _persistedShowcase，不加 URL params（避免汙染 shareable link）
            this.showFavoriteActresses = state.showFavoriteActresses === true;  // 嚴格 === true
            // 184: 一次性切換到「最近常收」。`|| 0` 是刻意（舊存檔缺旗標 ＝ undefined，FE-JS-01 勿改 ??）
            const migrated = (state.actressSortVersion || 0) >= 1;
            this.actressSort = migrated ? (state.actressSort || 'recent') : 'recent';
            this.actressOrder = migrated ? (state.actressOrder || 'desc') : 'desc';
            // 同步段立刻寫回，不等使用者動作（FE-TIMING-12）；旗標只在此與 saveState 寫、只寫 1
            this._persistedShowcase.actressSort = this.actressSort;
            this._persistedShowcase.actressOrder = this.actressOrder;
            this._persistedShowcase.actressSortVersion = 1;
            // 129-T2 / CD-129-6：女優分頁的搜尋字比照影片分頁持久化（spec S5）。
            // 不走 URL params（與 showFavoriteActresses/actressSort/actressOrder 一致，
            // 避免污染分享連結）；也**不**還原 actressPills——CD-116a-5 不翻案。
            this.actressSearch = state.actressSearch || '';
            // TASK-119-T3: 只走 localStorage，白名單比對（FE-JS-01：不可 || fallback）
            this.cardShape = state.cardShape === 'poster' ? 'poster' : 'cover';
            // TASK-124b-T1: 嚴格 === true（鏡射 showFavoriteActresses 慣例，FE-JS-01：不可 || fallback）
            this.infoVisible = state.infoVisible === true;
        },

        // --- 狀態持久化 (M2c) ---
        saveState() {
            // 53a-T2: 寫入 reactive _persistedShowcase，$persist 自動同步 localStorage 'showcase_state'
            // T3.2 (CD-52-3): perPage 不寫入（每次 init 重讀 cfg.items_per_page）
            this._persistedShowcase.sort = this.sort;
            this._persistedShowcase.order = this.order;
            this._persistedShowcase.page = this.page;
            this._persistedShowcase.search = this.search;
            this._persistedShowcase.mode = this.mode;
            this._persistedShowcase.showFavoriteActresses = this.showFavoriteActresses;  // ★ 44a
            this._persistedShowcase.actressSort = this.actressSort;                      // ★ 44a
            this._persistedShowcase.actressOrder = this.actressOrder;                    // ★ 44a
            this._persistedShowcase.actressSortVersion = 1;                              // ★ 184
            this._persistedShowcase.actressSearch = this.actressSearch;                  // ★ 129-T2
            this._persistedShowcase.pills = serializePills(this.pills);
            this._persistedShowcase.cardShape = this.cardShape;

            // 同步到 URL（方便分享連結）
            const params = new URLSearchParams();
            if (this.search) params.set('search', this.search);
            if (this.sort !== 'date') params.set('sort', this.sort);
            if (this.order !== 'desc') params.set('order', this.order);
            // T3.2 (CD-52-3): perPage 不再寫入 URL params（每次 init 重讀 cfg.items_per_page）
            if (this.page !== 1) params.set('page', this.page);
            if (this.mode !== 'grid') params.set('mode', this.mode);

            const newUrl = params.toString()
                ? `${window.location.pathname}?${params}`
                : window.location.pathname;
            window.history.replaceState({}, '', newUrl);
        },

        // Card Info 切換 (M3i) — 原型 B：先寫眼睛 → capture 舊位 → 同步 .info-open → x/y 位移
        toggleInfo() {
            var toVisible = !this.infoVisible;
            this.infoVisible = toVisible;                      // ★ 第一行就寫，眼睛立刻回饋
            this._persistedShowcase.infoVisible = toVisible;
            var grid = this._getActiveGrid?.();
            var captured = window.ShowcaseAnimations?.captureInfoState?.(grid) || null;
            grid?.classList?.toggle('info-open', toVisible);   // ★ 同步改版面
            try {
                window.ShowcaseAnimations?.playInfoExpand?.(captured, grid);
            } catch (err) {
                console.error('playInfoExpand failed (資訊區仍會切換):', err);
            }
        },

        formatPartLabel,
        singleActorAge,

        // 格式化檔案大小（bytes → GB/MB）
        formatSize(bytes) {
            if (!bytes || bytes === 0) return window.t('showcase.grid.unknown_size');
            const gb = bytes / (1024 * 1024 * 1024);
            if (gb >= 1) {
                return `${gb.toFixed(2)} GB`;
            }
            const mb = bytes / (1024 * 1024);
            return `${mb.toFixed(2)} MB`;
        },

        // Stale cover handler — 圖片載入失敗時 downgrade has_cover，
        // 觸發 Alpine reactive：enrich icon 自動出現、missing-cover class 套用、
        // 點 enrich 後自動走 refresh_full 補封面。
        handleCoverError(video, event) {
            if (!video) return;
            video.has_cover = false;  // 觸發 reactive — enrich icon 自動出現 + missing-cover class 套用
            // 67/Codex P2（broken cover）：grid 三態淡入讓 .av-card-preview-img img 預設 opacity:0、靠
            // .cover-loaded(=_imgLoaded) 才可見。stale/404 換 placeholder 後，可見性原本只依賴 placeholder
            // 二次 @load 觸發（脆弱）→ 直接設 _imgLoaded=true，確定性顯示 placeholder（不依賴 @load）。
            video._imgLoaded = true;
            event.target.onerror = null;  // 防止 placeholder 失敗無限迴圈
            event.target.src = _NO_COVER_PLACEHOLDER;
        },

    };
}
