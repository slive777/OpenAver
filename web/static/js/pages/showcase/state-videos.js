/**
 * state-videos.js — Showcase ESM（54b-T1b）
 *
 * 影片資料流：fetchVideos / filter / sort / paginate / animate。
 * 無 data 初始值（全部在 stateBase 已有）。
 * 從 state-base.js import 共用大陣列（F1：移出 Alpine reactive scope）。
 */

import { _videos, _allVideos, _filteredVideos, _nameToGroup, _tagToGroup, _setVideos, _setAllVideos, _setFilteredVideos, _recomputeAllBadges, _recomputeCardActorAges } from '@/showcase/state-base.js';
import { applyCellFocal } from '@/shared/focal-cell.js';
import { openLocal } from '@/shared/open-local.js';
import { playVideo } from '@/shared/play-video.js';
import { normalizePillValue, buildPillPredicate } from '@/shared/pill-filter.js';
import { isDigitsOnlySearch } from '@/shared/digits-only-search.js';
// TASK-124a-T2：發售日 pill 浮層狀態機直接呼叫的 T1 六支純函式中的五支
// （matchesReleasePill 屬 pill-filter.js 內部使用，state 層不直接呼叫）。
import { parseReleaseKey, parseEndpoint, expandPill, composeEndpoint, videoYearRange } from '@/shared/release-window.js';

// TASK-195-T9（195d／CD-195-16）：純數字搜尋自動清除的白名單，不含 pick。
const CLEAR_SEARCH_DIMS = ['actress', 'maker', 'series', 'director', 'label', 'tag'];
// TASK-124a-T2：鏡射 state-actress.js 的 _trimOrNull（模組私有，無法 import，各自一份）。
function _trimOrNull(v) {
    if (v == null) return null;
    var s = String(v).trim();
    return s === '' ? null : s;
}

// TASK-124a-T2：鏡射 state-actress.js 的 _pillFieldValue：isBad 來自 markup @input 寫入的
// validity.badInput，有字但取不到值 ≠ 空（has 涵蓋 badInput）。
function _releaseFieldValue(rawText, isBad) {
    if (isBad) return { has: true, raw: null };
    var t = _trimOrNull(rawText);
    return { has: t != null, raw: t };
}

export function stateVideos() {
    return {

        // --- 99a-T2: 揭露 applyCellFocal 供 F1 grid template @load / $watch 呼叫（load-gated，
        // aspect-aware object-position；取代舊 focalStyle 的 reactive :style binding，見 98b-T6 姊妹
        // gotcha：naturalWidth 在 decode 完成前恆為 0，reactive binding 不會因 load 事件重跑）---
        applyCellFocal,

        // --- API 呼叫 ---
        async fetchVideos() {
            this.loading = true;
            this.error = '';
            try {
                const resp = await fetch('/api/showcase/videos');
                if (!resp.ok) {
                    _videos.length = 0;
                    _allVideos.length = 0;      // 195b-T4：全庫與被藏片數同步歸零
                    this.hiddenCount = 0;
                    this.videoCount = 0;
                    _filteredVideos.length = 0;
                    this.filteredCount = 0;
                    this.error = window.t('showcase.error.server_error', { status: resp.status });
                    return;
                }
                const data = await resp.json();
                if (!data.success) {
                    _videos.length = 0;
                    _allVideos.length = 0;      // 195b-T4：全庫與被藏片數同步歸零
                    this.hiddenCount = 0;
                    this.videoCount = 0;
                    _filteredVideos.length = 0;
                    this.filteredCount = 0;
                    this.error = data.error || window.t('showcase.error.load_failed');
                    return;
                }
                // Re-assign module-level var via splice/push to keep the same reference
                // (core.js uses direct assignment; ESM re-exports work because we read
                // _videos/_filteredVideos at call time, not at import time)
                var vids = data.videos || [];
                // 67-A2: per-card 三態旗標。video 物件由此唯一來源流穿整條 render 鏈
                // （_videos → _filteredVideos → paginatedVideos slice，皆同 ref），故初始化一處即涵蓋
                // 初次載入/retry/翻頁/搜尋/排序；後端不回此欄位。補封面走 refreshVideoData reset。
                vids.forEach(function (v) { if (v._imgLoaded === undefined) v._imgLoaded = false; if (v._coverRequested === undefined) v._coverRequested = false; });
                // 195b-T4：全庫存 _allVideos；_videos ＝ 扣掉被「隱藏未連線硬碟」藏起來的片（同一物件 ref）。
                // _recomputeVisible 不呼叫 applyFilterAndSort；下面 _setFilteredVideos 與其後 init/retry 的重篩接手。
                _setAllVideos(vids);
                this._hsSources = Array.isArray(data.sources) ? data.sources : [];
                this._recomputeVisible();
                this.videoCount = _videos.length;
                _setFilteredVideos(_videos);
                this.filteredCount = _filteredVideos.length;
            } catch (e) {
                console.error('Failed to fetch videos:', e);
                _videos.splice(0, _videos.length);
                _allVideos.splice(0, _allVideos.length);    // 195b-T4
                this.hiddenCount = 0;
                this.videoCount = 0;
                _filteredVideos.splice(0, _filteredVideos.length);
                this.filteredCount = 0;
                this.error = window.t('showcase.error.cannot_connect');
            } finally {
                this.loading = false;
            }
        },

        // --- 重試（async 安全） ---
        async retry() {
            this.error = '';
            const savedPage = this.page;
            await this.fetchVideos();
            _recomputeAllBadges();
            this.applyFilterAndSort(true);  // 跳過 pagination，下面統一處理
            this.page = savedPage;
            this.updatePagination();
            // Settle: retry 也用 settle（不碰 opacity → 不閃）
            if (this.mode === 'grid' && !this.error) {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    var grid = this._getActiveGrid();
                    window.ShowcaseAnimations?.playSettle?.(grid);
                }); });
            }
        },

        // --- 互動邏輯 ---
        onSearchChange() {
            // B8: 透過 _animateFilter 觸發篩選動畫
            this._animateFilter();
            // TASK-115-T8：改走單一判斷點（CD-8），無 pill 時行為逐位元組不變
            // （_reconcileHeroCard 的「無 pill 分支」就是這裡原本的 if/else）。
            this._reconcileHeroCard();
        },

        // TASK-115-T1: metadata pill filter mutations（UI 殼屬 T5；比對屬 T2）
        normalizePillValue,

        addPill(dim, value) {
            var norm = normalizePillValue(value);
            if (!dim || !norm) return;
            var key = dim + '::' + norm;
            var exists = this.pills.some(p => p.dim + '::' + normalizePillValue(p.value) === key);
            if (exists) return;  // 靜默去重：不重跑 _animateFilter/_reconcileHeroCard
            this.pills = [...this.pills, { dim: dim, value: value }];  // value 存原始字面（CD-3）
            if (CLEAR_SEARCH_DIMS.includes(dim)) this._clearDigitsOnlySearch();
            this._animateFilter();
            this._reconcileHeroCard();
        },

        removePill(dim, value) {
            var key = dim + '::' + normalizePillValue(value);
            var next = this.pills.filter(p => (p.dim + '::' + normalizePillValue(p.value)) !== key);
            if (next.length === this.pills.length) return;  // 沒命中：不重跑
            this.pills = next;
            this._animateFilter();
            this._reconcileHeroCard();
            // TASK-124a-T2（§3.3）：移除的正是編輯中的 release pill → teardown 浮層草稿。
            // 移除其他維度不影響 _releaseEditor（release pill 恆 0/1 枚，dim 比對即可）。
            if (dim === 'release' && this._releaseEditor) this._releaseEditor = null;
        },

        // TASK-123-T6：「只看精選」漏斗選單項 ＋ pill chip 的一組讀寫入口（CD-123-9：
        // addPill()/removePill() 本體一行都不改，togglePickPill() 完全複用它們既有的（195d 起 addPill 多一行白名單清文字；pick 不在白名單，行為不變）
        // _animateFilter()/_reconcileHeroCard()/持久化副作用鏈）。
        _hasPickPill() {
            return this.pills.some(p => p.dim === 'pick');
        },

        togglePickPill() {
            if (this._hasPickPill()) {
                this.removePill('pick', '1');
            } else {
                this.addPill('pick', '1');
            }
        },

        // TASK-123-T6：pill chip 文案分流層。只有 pick 這一個特例（value 是 '1'，直接顯示
        // 會變成一顆寫著「1」的 chip）——其餘 dim 逐字回傳 pill.value，不做成 dim→formatter
        // 對應表（plan §4 風險表：超過 2 個特例才升級）。
        pillLabel(pill) {
            if (pill.dim === 'pick') return window.t('showcase.pick.chip_label');
            if (pill.dim === 'release') return this.releasePillText(pill);
            return pill.value;
        },

        // ── TASK-124a-T2：發售日 pill 浮層狀態機（無 markup；鏡射 state-actress.js 的
        // 116b-T2/116c-T2 浮層狀態機，但不共用程式碼，只共用「同一套手勢」的設計）──

        // 開啟：pill（op/value/value2）→ 草稿（四格 lo/hi 年月）映射；同一枚再點＝關閉。
        // release pill 恆 0/1 枚，不需要像女優版那樣比對 dim。
        _toggleReleaseEditor(pill) {
            if (!this._pillPopoverEnabled) return;               // 第二層防禦（斷點閘門）
            if (this._releaseEditor) { this._releaseEditor = null; return; }  // 同一枚再點＝關閉
            var loParsed = pill.op === 'range' ? parseEndpoint(pill.value) : null;
            var hiParsed = pill.op === 'range' ? parseEndpoint(pill.value2) : null;
            this._releaseEditor = {
                op: pill.op,
                value: pill.value,      // 態①操作數來源，不論原 op 為何一律照抄 pill.value
                value2: pill.value2,    // （鏡射 _openPillEditor 對 value/value2 的處理：兩欄位
                                         //  永遠照抄，不因 op 分支而省略）
                loYear: loParsed ? String(loParsed.y) : null,
                loMonth: loParsed && loParsed.m != null ? (loParsed.m < 10 ? '0' + loParsed.m : String(loParsed.m)) : null,
                hiYear: hiParsed ? String(hiParsed.y) : null,
                hiMonth: hiParsed && hiParsed.m != null ? (hiParsed.m < 10 ? '0' + hiParsed.m : String(hiParsed.m)) : null,
                badLoY: false, badLoM: false, badHiY: false, badHiM: false,
            };
        },

        // 單一端點（lo 或 hi）的完整取值語意：年格＋月格合起來算一個端點。
        // has=true 代表「這個端點有沒有被動過」（含 badInput），與「token 合不合法」是兩件事。
        _releaseEndpoint(which) {
            var d = this._releaseEditor;
            if (!d) return { has: false, token: null };           // 安全回傳（x-show 求值前提）
            var yRaw = which === 'lo' ? d.loYear : d.hiYear;
            var mRaw = which === 'lo' ? d.loMonth : d.hiMonth;
            var yBad = which === 'lo' ? d.badLoY : d.badHiY;
            var mBad = which === 'lo' ? d.badLoM : d.badHiM;
            var y = _releaseFieldValue(yRaw, yBad);
            var m = _releaseFieldValue(mRaw, mBad);
            if (!y.has && !m.has) return { has: false, token: null };   // 該端點沒填：has=false
            if (y.raw == null) return { has: true, token: null };       // 有月無年 / 年格壞輸入
            var yearNum = Number(y.raw);
            if (!m.has) return { has: true, token: composeEndpoint(yearNum, null) };  // 只有年
            if (m.raw == null) return { has: true, token: null };       // 月格壞輸入
            // ⚠ 刻意選擇 composeEndpoint() 的數值範圍檢查（year>=1000 && year<=9999），不是
            // parseEndpoint() 的純字元數判法——兩者對 '0230' 這類「四字元但數值 <1000」的
            // 字串判法不同（見 release-window.js 檔頭與本 task 檔「⚠ 一條需要測試鎖住的落差」）。
            // 理由：composeEndpoint() 是 T1 專為「提交時組字」設計的函式，同時做掉 zero-pad 與
            // 月份 1–12 檢查；UI 產生的 token 永遠先過這關，不會有畸形字串流出，不必另寫第二套
            // 年份判斷（parseEndpoint 的寬鬆只服務手改 localStorage 的容錯路徑）。
            //
            // ⚠ 同一條數值範圍判準的延伸後果（Codex PR review P2，2026-08-21 提過此條，
            // 判定為 accepted residual）：上面這行判準是「Number(y.raw) 之後落在 1000–9999
            // 的整數」，不是字元形狀 ^\d{4}$。所以指數記法或多餘小數點寫法（例如 '1e3'、
            // '1000.0'）會被 Number() 當成同一個數字的另一種寫法而正規化成 '1000' 照樣套用——
            // 這是刻意的，屬於 CD-124a-10 允許的「同一個數字的另一種寫法」正規化，不是夾回。
            // CD-124a-15 真正要擋的是「打字中途的短數字」（'2' → '20' → '202' 這種還沒打完的
            // 中間態），那類數值範圍本來就落在 1000 以外，仍然被這行判準擋下、不受影響。
            // 別把這行改成字元形狀檢查來「順便」擋掉指數記法——會連帶動到 CD-124a-10/15 的
            // 既定行為，改之前先回去讀那兩條決策。
            return { has: true, token: composeEndpoint(yearNum, Number(m.raw)) };
        },

        // spec §5.2 三態表（比照 _pillOperandFor 但省一層——release 的合法性判斷已內嵌在
        // _releaseEndpoint() 的 token 計算裡，composeEndpoint() 回 null 就代表不合法，不需要
        // 第二支 _releaseOperandOk）。
        _releaseOperandFor(op) {
            var d = this._releaseEditor;
            if (!d) return null;
            var lo = this._releaseEndpoint('lo');
            var hi = this._releaseEndpoint('hi');
            if (!lo.has && !hi.has) return d.value;                    // 態①：pill 目前的值
            if (!hi.has) return lo.token;                               // 態②：只有左端
            if (!lo.has) return hi.token;                               // 態②：只有右端
            return (op === '<=') ? hi.token : lo.token;                 // 態③：≤ 取右，≥/= 取左
        },

        // 三顆鈕（=／≤／≥）唯一提交路徑。operand 為 null（不合法/無法判定）→ 不寫入、不關閉。
        _applyReleaseOp(op) {
            if (!this._releaseEditor) return;
            var operand = this._releaseOperandFor(op);
            if (operand == null) return;                 // early return：不寫入、不關閉（AC12）
            this._setReleasePill({ dim: 'release', op: op, value: operand });
            this._releaseEditor = null;                   // 成功路徑：立刻關閉（AC8）
        },

        // ✓ 提交：單邊有值時委派給 _applyReleaseOp（同一段程式碼路徑求值兩次，結構性保證
        // AC10「✓ 與按對應運算子鈕逐欄位相同」，不是兩份平行邏輯剛好寫得一樣）。
        _commitReleaseEditor() {
            if (!this._releaseEditor) return;
            var lo = this._releaseEndpoint('lo');
            var hi = this._releaseEndpoint('hi');
            if (!lo.has && !hi.has) return;                          // 兩端皆空：✓ 不存在，防禦性 return
            if (!hi.has) return this._applyReleaseOp('>=');           // 只有左端 → 委派
            if (!lo.has) return this._applyReleaseOp('<=');           // 只有右端 → 委派
            if (lo.token == null || hi.token == null) return;         // 任一端形不成條件 → fail-safe（AC12）
            var loTok = lo.token, hiTok = hi.token;
            // 對調（AC11）：借用 expandPill({op:'=', value: token}).lo/.hi 取「該 token 代表的
            // 最早／最晚時點」當可比較的整數 key——下端點取 .lo、上端點取 .hi（不是兩側統一用
            // .lo），因為真正該問的是「下端的最早時點是否晚於上端的最晚時點」，那才是區間真的
            // 反了；純粹是排序 key，不涉及展開語意（展開語意在 expandPill() 對整枚 pill 求值時
            // 才發生，那是既有邏輯，不動）。零重複：借用已 export 的函式，不在本檔另寫一份
            // 「YYYYMM 整數化」邏輯。
            //
            // ⚠ 兩側不可都用 .lo：年份-only 的端點代表整年，其「最晚時點」是 12 月（.hi），
            // 若上端也用 .lo 會把它讀成 1 月，導致「下端 6 月 > 上端（誤讀成）1 月」被誤判為
            // 反轉而錯誤對調。例如使用者填 lo=2024-06、hi=2024（月份留空＝整年結尾 12 月），
            // 原意是「2024 年 6 月～12 月」；用 .hi 才會得到 202406 <= 202412（不反轉，不對
            // 調）；若誤用 .lo 得到 202406 > 202401（誤判反轉）會把 pill 錯組成
            // 2024~2024-06，展開後變成 1～6 月，恰好是使用者原意的反面。
            var loKey = expandPill({ op: '=', value: loTok }).lo;
            var hiKey = expandPill({ op: '=', value: hiTok }).hi;
            if (loKey > hiKey) { var tmp = loTok; loTok = hiTok; hiTok = tmp; }
            this._setReleasePill({ dim: 'release', op: 'range', value: loTok, value2: hiTok });
            this._releaseEditor = null;
        },

        // ✗ 取消：只丟棄草稿，不碰 pills（函式體不得引用 pills，鏡射 _cancelPillEditor 的同一條規定）
        _cancelReleaseEditor() {
            this._releaseEditor = null;
        },

        // ✓✗ 顯示條件：四格任一格（不分年月、不分左右端）有字即為 true——只看有沒有打字，
        // 不看打得對不對（打錯也要讓 ✗ 出現，使用者才點得到清掉或改對）。
        _releaseEditorHasInput() {
            var d = this._releaseEditor;
            if (!d) return false;                                     // 安全回傳（x-show 求值前提）
            return _trimOrNull(d.loYear) != null || _trimOrNull(d.loMonth) != null
                || _trimOrNull(d.hiYear) != null || _trimOrNull(d.hiMonth) != null;
        },

        // 資料範圍提示（spec §4.9）：全庫，不是 _filteredVideos。
        _releaseYearHint() {
            if (!this._releaseEditor) return '';                       // 安全回傳
            var range = videoYearRange(_videos);
            if (range == null) return '';                                // 一部片都解析不出年月：不印
            return '（' + range.min + ' ~ ' + range.max + '）';
        },

        // pill 顯示文字（spec §5.4）：無單位後綴（release 沒有單位）；顯示原字面，不重新展開
        // （op:'=', value:'2023' 顯示 =2023，不是 =2023-01~2023-12，AC21）。
        releasePillText(pill) {
            if (pill.op === 'range') return pill.value + '~' + pill.value2;   // U+007E，不加空白
            var prefix = pill.op === '<=' ? '≤' : pill.op === '>=' ? '≥' : '=';
            return prefix + pill.value;
        },

        // 入口 markup 的唯一判準（T3 引用）：一行 adapter，內部直呼 T1 的 parseReleaseKey()
        // （spec §4.1 明文「不得另寫第二份日期判斷」）。
        _isReleaseClickable(video) {
            return parseReleaseKey(video && video.release_date) != null;
        },

        // 唯一寫入者：一律建構全新物件、非 range 不帶 value2 鍵（避免沿用同一物件在 op 之間
        // 切換時殘留 value2，被 pill-filter.js 的 serializePills 靜默寫出——plan §8.1 陷阱）。
        _setReleasePill(pill) {
            var next = this.pills.filter(function (p) { return p.dim !== 'release'; });
            var built = { dim: 'release', op: pill.op, value: pill.value };
            if (pill.op === 'range') built.value2 = pill.value2;    // 非 range 不帶 value2 鍵
            next.push(built);
            this.pills = next;
            this._animateFilter();      // ⚠ 不是 applyFilterAndSort()（CD-124a-14，saveState 只在 _animateFilter 裡）
            this._reconcileHeroCard();
        },

        // 入口 adapter（燈箱 metadata 點擊 / searchFromMetadata 分派用）：dateStr 切前 7 字
        // （與 parseReleaseKey() 內部 RELEASE_KEY_RE 判定「解析得出」的同一段字元，不會有落差）。
        _clearDigitsOnlySearch() {
            if (isDigitsOnlySearch(this.search)) this.search = '';
        },
        _setReleasePillFromDate(dateStr) {
            var key = parseReleaseKey(dateStr);
            if (key == null) return;                       // 解析不出年月：不產生 pill（spec §4.4）
            var month = dateStr.slice(0, 7);
            var same = this.pills.some(function (p) { return p.dim === 'release' && p.op === '=' && p.value === month; });
            if (!same) this._clearDigitsOnlySearch();      // 同值＝沒新增：不清，仍照常委派（動畫 1 次，與今天相同）
            this._setReleasePill({ dim: 'release', op: '=', value: month });
        },

        // 跨切面 teardown 唯一實作（四個呼叫點：state-base.js 斷點 handler ×2、
        // toggleActressMode()、hero 橋接、clearAllFilters()）。無條件覆寫兩個 slot，冪等。
        _teardownPillEditors() {
            this._pillEditor = null;
            this._releaseEditor = null;
        },

        // TASK-115-T9: 搜尋框 Backspace 刪最後一枚 pill（IME 組字中一律不刪）
        onSearchBackspace(event) {
            if (event.isComposing) return;
            // 有字：交給瀏覽器原生刪字，不 preventDefault、不動 pill
            if (event.target.value !== '') return;
            // 游標必須在最左且選取為 collapsed；非 collapsed 選取不得刪 pill
            if (!(event.target.selectionStart === 0 && event.target.selectionEnd === 0)) return;
            if (this.pills.length === 0) return;
            var last = this.pills[this.pills.length - 1];
            this.removePill(last.dim, last.value);
        },

        clearAllFilters() {
            // 129-T1b / CD-129-1：只清當前分頁。另一分頁的搜尋狀態原封不動保留。
            // CD-116b-8b：teardown 維持無條件（本身冪等，release-pill-state.test.mjs:871 已鎖）——
            // 兩個浮層編輯器分屬兩個分頁，但「站在 A 分頁時 B 分頁的草稿還開著」本來就不可達，
            // 無條件收比分流安全，也讓既有兩支 DoD 守衛不必跟著改。
            this._teardownPillEditors();
            if (this.showFavoriteActresses) {
                this.actressSearch = '';
                this.actressPills = [];
                this.applyActressFilterAndSort(); // 對應 onActressSearchChange() 的行為，不經 _animateFilter
                // ⚠ 影片牆那條的 saveState() 埋在 _animateFilter() 裡（state-videos.js:517）；
                // 本分支不走 _animateFilter，必須顯式補一次，否則「按 ✕ 清掉、重整又跑回來」。
                this.saveState();
                // ⚠ 不呼叫 _reconcileHeroCard()：它只判斷 pill／文字、不判斷 showFavoriteActresses
                //   （見本檔 :376-391 的明文不變式），在女優牆呼叫會拿影片牆還留著的 pill
                //   算出一張不該出現的資料卡。
            } else {
                this.search = '';
                this.pills = [];
                this._animateFilter();            // 影片格：CD-2 步驟 7-9（唯一一次），內含 applyFilterAndSort() + saveState()
                this._reconcileHeroCard();        // TASK-115-T8 / RULING 3：清 hero 狀態的單一判斷點
            }
            Alpine.store('ui').toolbarOpen = false;
            // 無條件執行：使用者主動按下的清除鈕，即使已空跑一次也無害，且維持「按下必清」的誠實承諾
        },

        // TASK-115-T8：hero card（女優資料卡＋搜尋列愛心鈕）唯一判斷點（CD-8）。
        // 無 pill：完全不限制，交給下面「無 pill 分支」的既有邏輯判斷（逐位元組保留
        // onSearchChange 舊有的 if/else 語意）。有 pill：僅當恰好一枚女優 pill 且
        // 自由文字為空才顯示（spec §4.8）。
        _shouldShowHeroCard() {
            if (this.pills.length === 0) return true;
            return this.pills.length === 1
                && this.pills[0].dim === 'actress'
                && this.search.trim() === '';
        },

        // 七個既有觸發點（CD-8 原列六個＋RULING 1 併入 searchActressFilms）全部間接透過
        // 本方法，不再各自決定。
        //
        // ⚠ 一個刻意的例外，新增呼叫點前先讀：`_shouldShowHeroCard()` 只判斷 pill／文字，
        // **不判斷 showFavoriteActresses**。因此 toggleActressMode() 進入女優模式那條
        // （state-actress.js）仍直接呼叫 _clearPreciseMatch() 而不走本方法——若走本方法，
        // 帶著一枚持久化的女優 pill 切進女優牆會把 _isPreciseActressMatch 設成 true，
        // 在女優牆上顯示一張不該出現的資料卡。**在 showFavoriteActresses 為 true 時可達的
        // 新程式碼，不要無條件呼叫本方法**；要讓它變成真正的單一判斷點，正解是把
        // !showFavoriteActresses 併進 _shouldShowHeroCard()，再把那個 bypass 收回來。
        //
        // 回傳 _checkPreciseActressMatch() 的 promise（若有呼叫），
        // 讓 searchActressFilms() 的 ghost-fly 主流程可以 await 到真正的比對結果；
        // 其餘呼叫端維持既有的 fire-and-forget 用法，忽略回傳值不影響行為。
        _reconcileHeroCard() {
            if (!this._shouldShowHeroCard()) {
                this._clearPreciseMatch();
                return;
            }
            if (this.pills.length === 1) {
                // 有 pill 分支：唯一一枚女優 pill、文字為空（_shouldShowHeroCard 已保證）
                return this._checkPreciseActressMatch(this.pills[0].value, 'pill');
            }
            // 無 pill 分支：逐位元組保留現況（onSearchChange 舊有的 if/else）
            var trimmed = this.search.trim();
            if (trimmed) {
                return this._checkPreciseActressMatch(trimmed, 'manual');
            }
            this._clearPreciseMatch();
        },

        onSortChange() {
            this._sortWithFlip(() => {
                this.applyFilterAndSort();
            });
        },

        toggleOrder() {
            this._sortWithFlip(() => {
                this.order = this.order === 'asc' ? 'desc' : 'asc';
                this.applyFilterAndSort();
            });
        },

        // --- 44c T6: Active grid helper ---
        _getActiveGrid() {
            return this.showFavoriteActresses
                ? document.querySelector('.actress-grid')
                : document.querySelector('.showcase-grid');
        },

        /**
         * B7/B15: 排序動畫共用 helper — flip-guard → capture → change → Flip reorder
         * @param {Function} changeFn - 執行 data change 的函數
         */
        _sortWithFlip(changeFn) {
            var savedPage = this.page;
            var grid = null;
            var positionMap = null;

            // Step 0: capture（grid mode 或女優模式）
            if (this.mode === 'grid' || this.showFavoriteActresses) {
                grid = this._getActiveGrid();
                if (grid) {
                    grid.classList.add('flip-guard');
                    void grid.offsetHeight;  // force reflow
                    positionMap = window.ShowcaseAnimations?.capturePositions?.(grid) || null;
                }
            }

            // Step 1: data change
            changeFn();
            this.page = savedPage;
            this.updatePagination();
            this.saveState();

            // Step 2: animate
            if (grid && positionMap) {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) {
                        grid.classList.remove('flip-guard');
                        return;
                    }
                    var result = window.ShowcaseAnimations?.playFlipReorder?.(grid, positionMap);
                    if (!result) {
                        // fallback: Flip 回傳 null（delta 全零、reduced motion 等）
                        grid.classList.remove('flip-guard');
                        window.ShowcaseAnimations?.playEntry?.(grid);
                    }
                    // flip-guard 由 playFlipReorder 的 onComplete 移除
                }); });
            } else if (grid) {
                // capture 失敗 fallback
                grid.classList.remove('flip-guard');
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        /**
         * B8/B15: 篩選動畫共用 helper — flip-guard → capture → change → Flip filter
         * onSearchChange() 和 searchFromMetadata() 共用
         */
        _animateFilter() {
            var grid = null;
            var state = null;

            // Step 0: capture（僅 grid mode，且僅影片模式）
            //
            // 115-T7 review：`showFavoriteActresses` 為真時**一律不碰 DOM 動畫**。
            // 本函式是「影片側篩選」的動畫，而 `captureFlipState()` 只認得 `.av-card-preview`；
            // 餵它一面 `.actress-card` 會回 null → 掉進下面的 capture-failed fallback →
            // 對整面女優牆重播一次 playEntry 入場動畫。使用者看到的是：在女優模式按清除，
            // 每張女優卡無故閃一下（淡出↓20px 再淡回），而既有的 onActressSearchChange()
            // 那條路本來就是零動畫。
            //
            // 修在這裡而不是在 clearAllFilters() 加旗標：這是「任何呼叫端在女優模式下走到
            // _animateFilter 都會中」的類別問題，不是單一呼叫點的問題。onSearchChange() /
            // searchFromMetadata() 兩條既有路徑只在影片模式可達，故行為逐位元組不變。
            if (this.mode === 'grid' && !this.showFavoriteActresses) {
                grid = this._getActiveGrid();
                if (grid) {
                    grid.classList.add('flip-guard');
                    void grid.offsetHeight;  // force reflow
                    state = window.ShowcaseAnimations?.captureFlipState?.(grid) || null;
                }
            }

            // Step 1: data change
            this.applyFilterAndSort();
            this.saveState();

            // Step 2: animate
            if (grid && state) {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) {
                        grid.classList.remove('flip-guard');
                        return;
                    }
                    var result = window.ShowcaseAnimations?.playFlipFilter?.(grid, state);
                    if (!result) {
                        grid.classList.remove('flip-guard');
                        window.ShowcaseAnimations?.playEntry?.(grid);
                    }
                    // flip-guard 由 playFlipFilter 的 onComplete 移除
                }); });
            } else if (grid) {
                // capture 失敗 fallback
                grid.classList.remove('flip-guard');
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        /**
         * B9/B13: 分頁動畫 — state-first + playEntry
         * @param {string} direction - 'next' | 'prev'
         * @param {number} [targetPage] - 目標頁碼（goToPage 用，prevPage/nextPage 不傳）
         */
        _animatePageChange(direction, targetPage) {
            // 清理可能殘留的 flip-guard（sort/filter 動畫被翻頁打斷時）
            var grid = document.querySelector('.showcase-grid');
            if (grid) grid.classList.remove('flip-guard');

            // 計算目標頁碼
            var newPage = targetPage;
            if (newPage === undefined) {
                newPage = direction === 'next' ? this.page + 1 : this.page - 1;
            }

            // State mutation FIRST（不再困在回調中）
            this.page = newPage;
            this.updatePagination();
            this.saveState();
            window.scrollTo(0, 0);

            // Grid mode：播放進場動畫
            if (this.mode === 'grid') {
                var gen = ++this._animGeneration;
                this.$nextTick(() => { requestAnimationFrame(() => {
                    if (this._animGeneration !== gen) return;  // stale
                    var grid = document.querySelector('.showcase-grid');
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            }
        },

        switchMode(m) {
            if (!['grid', 'table', 'list'].includes(m)) return;
            if (m === this.mode) return;
            var oldMode = this.mode;
            this.mode = m;
            // F2: 切到 grid 時若 perPage=0 則降級
            if (m === 'grid' && this.perPage == 0) {
                this.perPage = 120;
                this.updatePagination();
            }
            this.saveState();  // M2c: 持久化狀態
            this.$nextTick(() => {
                window.ShowcaseAnimations?.playModeCrossfade?.(oldMode, m);
            });
        },

        /**
         * TASK-119-T4 (CD-119-11): 四條選單項與 A 鍵的唯一可執行入口。
         * target ∈ {'cover','poster','table','list'}，其餘一律早退（fail-closed；
         * FE-JS-01：用白名單查表，不用 `target || 'cover'` 這種寫法吃掉合法空值/0）。
         *
         * CD-119-14：換模式一律委派給 switchMode()（perPage 降級／updatePagination／
         * saveState／crossfade 的唯一所有者）——本函式內零 `this.mode = ` 賦值。
         * ~~CD-119-12 / §0.3：capture 必須在 cardShape 寫入之前；playShapeMorph 必須在
         * $nextTick 之後～～~~ ← 2026-08-28 TASK-133a-T2 作廢
         * 作廢理由：$nextTick 保證的是「Alpine 的 DOM 更新已套用」，**不保證瀏覽器還沒上色**。
         * 那個空隙裡瀏覽器會先畫一幀新版面（spec §1.1 的 t=491ms），Flip 之後才把舊位置貼上 ⇒ 閃兩次。
         * 「同一 tick 會量到舊幾何」的顧慮不成立：Flip.from / getBoundingClientRect 呼叫當下
         * 會強制同步 layout，只要 class 已寫進 DOM 就量得到新幾何。
         * 取代它的是 CD-133a-2：capture → 同步切 class → 同步 morph → 最後寫 state。
         */
        selectPresentation(target) {
            const PRESENTATIONS = {
                cover: { mode: 'grid', shape: 'cover' },
                poster: { mode: 'grid', shape: 'poster' },
                table: { mode: 'table', shape: null },   // shape: null = 卡型不變
                list: { mode: 'list', shape: null },
            };
            const next = PRESENTATIONS[target];
            if (!next) return;  // 未知 target：零副作用早退

            const nextMode = next.mode;
            const nextShape = next.shape === null ? this.cardShape : next.shape;

            if (nextMode === this.mode && nextShape === this.cardShape) return;  // 點自己：零副作用

            if (nextMode !== this.mode) {
                this.cardShape = nextShape;   // 先落卡型（此路徑不播 morph）
                this.switchMode(nextMode);    // 既有所有者：perPage 降級 + updatePagination + saveState + crossfade
                return;
            }

            // 走到這裡 ＝ grid → grid，只有卡型變 → 同一工作單元完成（CD-133a-2 取代 CD-119-12）
            const gridEl = this._getActiveGrid();  // CD-119-15 ⑤：用既有 helper，不自己 querySelector
            const captured = window.ShowcaseAnimations?.captureShapeState?.(gridEl) || null;  // ★ 必須在寫入之前
            // ★ 同步套用新版面，不等 Alpine：$nextTick 只保證「Alpine 已改 DOM」，
            //   不保證「瀏覽器還沒上色」，舊做法就是在那個空隙裡多畫了一幀（spec §1.1）。
            gridEl?.classList?.toggle('shape-poster', nextShape === 'poster');
            // ★ 同步建動畫：Flip.from 會強制同步 layout，此時量到的就是真正的新幾何
            // try/catch 的理由（T2 review P3）：morph 現在排在 state 寫入**之前**，
            // 它若拋錯就會吃掉下面兩行 ⇒ 使用者按了鈕但畫面完全沒反應。重排之前它在
            // $nextTick 回呼裡、天生擋不到 state 寫入——這道 try/catch 是把那個保護補回來。
            try {
                window.ShowcaseAnimations?.playShapeMorph?.(captured, gridEl);
            } catch (err) {
                console.error('playShapeMorph failed (卡型仍會切換):', err);
            }
            // ★ 最後才寫 state：Alpine 的 :class 稍後算出同一個值，不會再動一次 DOM
            this.cardShape = nextShape;
            this.saveState();
        },

        // TASK-133b-T2：設定「顯示表格／清單」；預設關。hydrate 在 state-base restoreState。
        showTableList: false,

        // TASK-119-T5：選單「圖片」與 A 鍵窄序列共用的 grid target。
        // 窄螢幕不得寫死 'cover'——會把使用者在桌面選的 poster 靜默洗掉（AC-3.2）。
        _gridTarget() {
            return this.cardShape === 'poster' ? 'poster' : 'cover';
        },
        _currentPresentation() {
            if (this.mode === 'grid') return this._gridTarget();
            return this.mode === 'list' ? 'list' : 'table';
        },
        _presentationOrder() {
            if (!this.showTableList) {
                return this._isNarrow ? [this._gridTarget()] : ['cover', 'poster'];
            }
            return this._isNarrow
                ? [this._gridTarget(), 'list', 'table']
                : ['cover', 'poster', 'list', 'table'];
        },

        prevPage() {
            if (this.page > 1) {
                this._animatePageChange('prev');
            }
        },

        nextPage() {
            if (this.page < this.totalPages) {
                this._animatePageChange('next');
            }
        },

        // Status bar 頁面跳轉 (M3g)
        goToPage(p) {
            const num = parseInt(p);
            if (Number.isNaN(num) || num < 1 || num > this.totalPages) return;
            if (num === this.page) return;
            var direction = num > this.page ? 'next' : 'prev';
            this._animatePageChange(direction, num);
        },

        /**
         * 49a-T4 / Codex P2: 開啟隱藏 select 的 native picker
         */
        openPagePicker(selectEl) {
            if (!selectEl) return;
            if (typeof selectEl.showPicker === 'function') {
                try { selectEl.showPicker(); return; } catch (e) { /* fall through */ }
            }
            selectEl.click();
        },

        // --- 資料處理 ---
        // 123-T8c（Codex PR review P2 ＋ grok Stage 1 P2，同一 artifact 連兩輪 → 重評方向）：
        // 把 applyFilterAndSort() 的**篩選那一半**原封不動抽成純函式。
        //
        // Why：`_pickFilterStale()` 原本用「掃 _filteredVideos 有沒有 rating 0」去**猜**
        // 牆面過期了沒。那個猜法天生單向（只看得到「該離開的」，看不到「該回來的」），
        // 而且 membership 同時受其他 pill 與搜尋字影響 —— 任何「補另一邊」的猜法都還有盲點
        // （例：某片是精選但被女優 pill 排除，補了就變成每次關燈箱都重篩）。
        // 方向改成**不猜、直接算**：算一次真實 membership 跟現況比對，兩個方向都準、沒有盲點。
        //
        // ⚠️ 本函式是 applyFilterAndSort() 第一半的**逐字搬移**，不得在此加入排序、分頁或
        //    任何寫入 state 的動作 —— 它的唯一用途就是「不動 state 地問：現在該是哪些片」。
        _computeFilteredVideos() {
            // --- Stage 1: pill 精準比對（TASK-115-T2, CD-6）---
            var pillPredicate = buildPillPredicate(this.pills, _nameToGroup, _tagToGroup);
            var pillFiltered = _videos.filter(pillPredicate);

            // --- Stage 2: 自由文字模糊比對 (M4a)（現況邏輯，body 逐字保留，僅改輸入來源陣列）---
            if (this.search && this.search.trim()) {
                // 分割多個關鍵字（用空格分隔，過濾空字串）
                const terms = this.search.toLowerCase().trim().split(/\s+/).filter(t => t.length > 0);

                var filtered = pillFiltered.filter(video => {
                    const searchable = [
                        video.title,
                        video.original_title,
                        video.actresses,
                        video.number,
                        video.maker,
                        video.tags,
                        video.release_date,
                        video.path,
                        video.director,
                        video.series,
                        video.label,
                        video.user_tags
                    ].filter(Boolean).join(' ').toLowerCase();

                    // 番號的正規化版本（移除空格和連字號）
                    const numNorm = video.number ? video.number.toLowerCase().replace(/[\s\-]/g, '') : '';

                    // 每個關鍵字都要匹配（AND 邏輯）
                    return terms.every(term => {
                        const termNorm = term.replace(/[\s\-]/g, '');
                        // 番號模糊匹配
                        if (numNorm && numNorm.includes(termNorm)) return true;
                        // alias 展開 match：搜尋詞反查 alias group，任一 alias name 命中即可
                        var termNames = _nameToGroup[term] || [term];
                        if (termNames.some(function(n) { return searchable.includes(n.toLowerCase()); })) return true;
                        // tag alias 展開：搜尋詞反查 tag alias group，任一同義 tag 命中即可（A3-4）
                        var termTagNames = _tagToGroup[term] || null;
                        if (termTagNames) {
                            if (termTagNames.some(function(tn) { return searchable.includes(tn.toLowerCase()); })) return true;
                        }
                        return false;
                    });
                });
                return filtered;
            }
            // 空搜尋：pill 篩選結果即為最終結果
            return pillFiltered;
        },

        applyFilterAndSort(skipPagination) {
            _setFilteredVideos(this._computeFilteredVideos());
            this.filteredCount = _filteredVideos.length;

            // --- 排序 (M4b) ---
            _filteredVideos.sort((a, b) => {
                // 1. 女優卡置頂邏輯
                const aIsHero = a.path && a.path.indexOf('actress:') === 0;
                const bIsHero = b.path && b.path.indexOf('actress:') === 0;
                if (aIsHero && !bIsHero) return -1;
                if (!aIsHero && bIsHero) return 1;

                // 2. Random 排序
                if (this.sort === 'random') {
                    return Math.random() - 0.5;
                }

                // 3. 其他排序：取得比較值
                let va, vb;
                switch (this.sort) {
                    case 'title':
                        va = a.title || '';
                        vb = b.title || '';
                        break;
                    case 'actor':
                        va = a.actresses || '';
                        vb = b.actresses || '';
                        break;
                    case 'num':
                        va = a.number || '';
                        vb = b.number || '';
                        break;
                    case 'maker':
                        va = a.maker || '';
                        vb = b.maker || '';
                        break;
                    case 'date':
                        va = a.release_date || '';
                        vb = b.release_date || '';
                        break;
                    case 'size':
                        va = a.size || 0;
                        vb = b.size || 0;
                        break;
                    case 'mdate':
                        va = a.mtime || 0;
                        vb = b.mtime || 0;
                        break;
                    default:
                        va = a.path || '';
                        vb = b.path || '';
                }

                // 4. 比較邏輯
                if (va < vb) return this.order === 'asc' ? -1 : 1;
                if (va > vb) return this.order === 'asc' ? 1 : -1;
                return 0;
            });

            // --- 重置頁碼並更新分頁 ---
            if (!skipPagination) {
                this.page = 1;
                this.updatePagination();
            }
        },

        updatePagination() {
            // F2: grid mode 禁用「全部」— perPage=0 降級為 120
            if (parseInt(this.perPage) === 0 && this.mode === 'grid') {
                this.perPage = 120;
            }
            const perPage = Math.max(0, parseInt(this.perPage) || 0);
            var slice;
            if (perPage === 0) {
                slice = _filteredVideos.slice();
                this.totalPages = 1;
                this.page = 1;
            } else {
                this.totalPages = Math.max(1, Math.ceil(_filteredVideos.length / perPage));
                if (this.page > this.totalPages) this.page = this.totalPages;
                if (this.page < 1) this.page = 1;
                const start = (this.page - 1) * perPage;
                slice = _filteredVideos.slice(start, start + perPage);
            }
            slice.forEach(_recomputeCardActorAges);
            this.paginatedVideos = slice;
        },

        // 155a CD-155a-4：收藏清單變動後補算「已經在牆上」的卡片年齡。必須經由 this.paginatedVideos
        // 讀出的 Proxy 元素寫入（Proxy set 才會觸發已渲染卡片重繪）；不可改呼叫 updatePagination()——
        // 同 key 的原始物件重新賦值不會讓 keyed x-for 重跑卡片內的 binding（主 session 實測）。
        _refreshCardActorAges() {
            (this.paginatedVideos || []).forEach(_recomputeCardActorAges);
        },

        // --- 播放影片 (PyWebView 整合；實作在 shared/play-video.js，搜尋頁共用) ---
        playVideo,

        // 工具方法：從 paginatedVideos 的 index 映射到 filteredVideos 的 index
        getCurrentFilteredIndex(paginatedIndex) {
            const perPage = parseInt(this.perPage);
            return perPage === 0 ? paginatedIndex : (this.page - 1) * perPage + paginatedIndex;
        },

        // 開啟資料夾（複製路徑到剪貼簿 + PyWebView 桌面模式額外開啟資料夾）
        openLocal,

    };
}
