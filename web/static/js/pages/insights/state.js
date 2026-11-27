/**
 * state.js — 片庫分析 Alpine 狀態（TASK-156b-T3 擴充）
 *
 * records[] 存 aggregate 模組級，不進 this.*（CD-156-4）。
 * ECharts 實例只經 charts.js 模組級 Map（CD-156-4 2.1）。
 * bfcache：pageshow(persisted) 在本頁私有 listener 處理（CD-156-5）。
 */

import {
    ACTRESS_TOP_N,
    podiumSizeForViewport,
    setRecords,
    getRecords,
    buildMakerColorSlots,
    buildMainMakerYearMap,
    buildActressBoard,
    buildGanttRows,
    ganttYearAxis,
    buildGanttYearCells,
    ganttAgeEligibility,
    ganttAgeAxis,
    buildGanttAgeCells,
    buildSoloRows,
    buildCostarRows,
    podiumPositionClass,
    classifyBoardTransition,
    diffBoardCounts,
} from './aggregate.js';
import {
    emptySel,
    normalizePeriod,
    periodContainsYear,
    toggleActress,
    toggleMaker,
    toggleGanttCell,
    scopeRecords,
    periodLabel,
    suffixLabel,
    isHoverPointer,
} from './selection.js';
import {
    setMakerColorSlots,
    setMainMakerYearMap,
    initYearsChart,
    updateYearsChart,
    initDonutChart,
    updateDonutChart,
    initTagsChart,
    updateTagsChart,
    initAgeChart,
    updateAgeChart,
    initFieldBarChart,
    updateFieldBarChart,
    disposeAll,
    areChartsAlive,
    reinitYearsAfterDispose,
    reinitDonutAfterDispose,
    reinitTagsAfterDispose,
    reinitAgeAfterDispose,
    reinitFieldBarAfterDispose,
    getDonutChart,
    getTagsChart,
    getAgeChart,
    getFieldBarChart,
    resizeAll,
    colorForMakerName,
    emptyKeyForCard,
} from './charts.js';
import { applyCellFocal } from '../../shared/focal-cell.js';
import { applyHandoff, normalizeExtraPill } from '../../shared/showcase-handoff.js';
import { toastState } from '../../shared/state-toast.js';
import { classifyFavoriteResponse, buildFavoriteEntry, mergeFavorite } from './favorite-sync.js';

// TASK-177-T3b：收藏回應分類 → [提示 type, 既有 i18n key]（零新增 key）
const FAVORITE_TOAST = {
    added: ['success', 'showcase.actress.addSuccess'],
    already: ['info', 'showcase.actress.addDuplicate'],
    not_found: ['error', 'showcase.actress.addNotFound'],
    failed: ['error', 'showcase.actress.addTimeout'],
};

// goBrowse／goBrowseWith 共用：寫入 showcase_state 成功才同步導向瀏覽頁；失敗＝不導航。
function writeHandoffAndNavigate(sel, extra) {
    try {
        localStorage.setItem('showcase_state', applyHandoff(localStorage.getItem('showcase_state'), sel, extra));
    } catch (e) {
        console.warn('goBrowse: 無法寫入 showcase_state，不導航', e);
        return;
    }
    window.location.assign('/showcase');
}

let _pageshowBound = false;
let _pageAlive = false;
let _previewTimer = null;
// bfcache 還原時可能重啟一次新的 fetch（見 _onPageShow）；離頁前的舊 fetch若晚
// 回來，token 比對讓它被丟棄，不會蓋掉新那次的結果（排序優先於旗標守衛）。
let _loadToken = 0;
/** 主要片商年 map；_loadSnapshot 建一次，與 setMainMakerYearMap 同一物件參考。 */
let _mainMakerYearMap = {};
/**
 * 修正 3（第 3 輪，P2 效能回歸）：ganttView() 單筆快取。模板同一次 reactive
 * tick 內會對同一個 axis 呼叫 ganttView() 好幾次（表頭 x-for／列 x-for／
 * gantt-note 的 x-show＋x-text），每次都重新對 25 列各掃一輪全庫 records
 * 建格子——實測 6521 筆片庫一次 tick 吃 65–80ms。鍵＝axis＋this.ganttRows
 * 參考＋this.sel 參考＋favorites 參考，四者皆相同（===）才視為同一次
 * tick、直接回快取；鍵不同（sel 換了、favorites 換了、切了軸）
 * 才真的重算。存模組級變數、不進 Alpine reactive proxy——快取物件本身沒有
 * 必要被 Alpine 追蹤，包成 reactive 只會多繞一層 Proxy 開銷。
 */
let _ganttViewCache = null;
/**
 * TASK-156d-T4／CD-156d-3：上一次觸發過強調亮起的置頂名字（年表／分布表各自
 * 一份，可能不同步——例如她在年表自然排序內不觸發，但在分布表是 rank 外附加）。
 * 純粹的一次性比較用內部旗標，不是要被模板讀取的資料，故放模組級 `let`，
 * 不進 Alpine reactive 屬性。非女優焦點時歸零成 `null`（見 `_maybePlayPinPulse`
 * 註解——這保證清除焦點後重新選回同一人仍會重新觸發一次）。
 */
let _lastPinnedGanttName = null;
let _lastPinnedSoloName = null;
let _podiumEntrancePlayed = false;
/** TASK-156e-T1b／CD-156e-2：還在播的女優榜換位相關動畫（Flip／淡入／掉榜替身）。 */
let _boardActiveAnims = new Set();
/** TASK-156e-T1b／CD-156e-3：156d 淡出淡入換卡世代號與進行中鏈計數。 */
let _costarSwapGen = 0;
let _costarSwapPendingChains = 0;
/** TASK-156e-T2／CD-156e-5：同時最多一個頭像飛行替身。 */
let _activeAvatarGhost = null;
/** TASK-156e-T3／CD-156e-6：頁首片數補間 handle＋世代號（連點防護）。 */
let _scopedCountTween = null;
let _scopedCountGen = 0;
/** TASK-156e-T3／CD-156e-6：女優榜每人一份片數補間 handle＋世代號（key＝女優名）。 */
let _boardCountTweens = {};
let _boardCountGens = {};

/**
 * TASK-156e-T1b／CD-156e-2：登記／自清 wrapper。
 * kind: 'flip' | 'fade'
 */
function _playBoardTrackedAnim(kind, createFn, opts) {
    let anim;
    const userOnComplete = opts && opts.onComplete;
    const mergedOpts = Object.assign({}, opts, {
        onComplete: () => {
            _boardActiveAnims.delete(anim);
            if (userOnComplete) userOnComplete();
        },
    });
    anim = createFn(mergedOpts);
    if (anim) { anim._boardKind = kind; _boardActiveAnims.add(anim); }
    return anim;
}

/** TASK-156e-T1b／CD-156e-2 規則 1/2：新一輪換位只收斂非 Flip。 */
function _settleBoardNonFlipAnims() {
    Array.from(_boardActiveAnims).forEach(anim => {
        if (anim._boardKind === 'flip') return; // 交給下一次 flipCapture()
        if (typeof anim.progress === 'function') anim.progress(1);
    });
}

/** TASK-156e-T1b／CD-156e-2 規則 3：換卡時收斂全部（不含片數 playCountUp）。 */
function _forceSettleAllBoardAnims() {
    Array.from(_boardActiveAnims).forEach(anim => {
        if (typeof anim.progress === 'function') anim.progress(1);
    });
}

/**
 * 飛行／掉榜替身掛到 body 前剝掉 Alpine 綁定，避免 MutationObserver 在無
 * scope 下把 clone 當新元件初始化（噴 podiumPositionClass／row is not defined）。
 */
function _stripAlpineForGhost(root) {
    if (!root) return;
    root.querySelectorAll('template').forEach((t) => t.remove());
    const stripAlpineAttrs = (el) => {
        Array.from(el.attributes).forEach((attr) => {
            const n = attr.name;
            if (n.startsWith('x-') || n.startsWith(':') || n.startsWith('@')) {
                el.removeAttribute(n);
            }
        });
    };
    stripAlpineAttrs(root);
    root.querySelectorAll('*').forEach(stripAlpineAttrs);
    root.removeAttribute('data-flip-id');
}

/** 預覽浮層實測尺寸（160 寬照片 + 名字列）；與 .insights-preview CSS 對齊。 */
const PREVIEW_POPUP = { width: 160, height: 224 };
const PREVIEW_GAP = 8;
const PREVIEW_OPEN_DELAY_MS = 250;

function _photoUrl(name, favorites, opts) {
    if (!name) return '';
    const fav = favorites && favorites[name];
    if (opts && opts.avatar && fav && fav.avatarUrl) return fav.avatarUrl;
    const photoName = (fav && fav.photoName) || name;
    return '/api/actresses/photo/' + encodeURIComponent(photoName);
}

/**
 * 預覽浮層 position:fixed 座標。錨點右側優先；溢出則翻左側／上移；夾在視窗內。
 * @param {{top:number,left:number,width:number,height:number}} anchor
 * @param {{width:number,height:number}} viewport
 * @param {{width:number,height:number}} popup
 * @returns {{left:number,top:number}}
 */
export function computePreviewPosition(anchor, viewport, popup) {
    var gap = PREVIEW_GAP;
    var left = anchor.left + anchor.width + gap;
    if (left + popup.width > viewport.width) {
        left = anchor.left - popup.width - gap;
    }
    if (left < 0) {
        left = Math.max(0, viewport.width - popup.width);
    }
    var top = anchor.top;
    if (top + popup.height > viewport.height) top = viewport.height - popup.height - gap;
    if (top < 0) top = 0;
    return { left: left, top: top };
}

export function shouldPlayPodiumEntrance(alreadyPlayed, podiumRowsLength) {
    return !alreadyPlayed && podiumRowsLength > 0;
}

/**
 * TASK-156d-T9／CD-156d-10a：row3 左半格是否顯示「與她同片」卡的衍生旗標。
 * 女優焦點但零共演時仍應為 false（改顯示女優榜），避免空白的「與她同片」卡。
 */
export function computeCostarVisible(isActressFocused, costarRowsLength) {
    return isActressFocused && costarRowsLength > 0;
}

export function libraryInsightsState() {
    let podiumResizeHandler = null;
    let resizePending = false;
    let resizeFrame = null;
    return {
        snapshot: null,
        snapshotError: null,
        // TASK-161a-T5a／CD-161a-1：期間＋女優＋片商三個條件合成單一 reactive 欄位；
        // 每次變更整個物件換新（不 mutate），$watch('sel') 才會觸發。
        sel: emptySel(),
        scopedCount: 0,
        // TASK-156e-T3／CD-156e-6：顯示層（補間只碰這裡；真相欄位 scopedCount／row.count 不變）
        displayScopedCount: 0,
        boardDisplayCounts: {},
        boardRows: [],
        podiumSize: podiumSizeForViewport(typeof window !== 'undefined' ? window.innerWidth : undefined),
        // TASK-156d-T3／CD-156d-2：row3 左半格＋row7 三個可切換顯示旗標（不用 x-show，
        // FE-ALPINE-17——vendored Alpine 的 x-show 晚一幀且一翻轉就立即 display:none，
        // 淡出播不完）。初始狀態＝無焦點：副本 A 顯示、與她同片／row7 副本 B 隱藏。
        showBoardInRow3: true,
        showCostar: false,
        showBoardInRow7: false,
        ganttRows: [],
        // 修正 1（第 2 輪）：圖例名單存進 reactive 欄位，見 ganttLegendMakers() 註解。
        ganttLegend: [],
        soloRows: [],
        costarRows: [],
        previewActress: null,
        previewAnchorRect: null,
        // 模板色點／格子塗色直接呼叫（charts.js 匯出）
        colorForMakerName,
        // P3-3：以女優名為 key，記錄該人頭像照片曾經載入失敗——取代舊版
        // @error 直接改寫 DOM textContent 的寫法（會把 x-if 錨點一併砍掉，
        // Alpine 之後永遠無法再插回新內容）。女優格與女優榜共用同一份。
        photoFailed: {},
        // TASK-177-T3b／CD-177-5：收藏請求進行中的名字表（鍵＝captured name、值 true）
        favoriteBusy: {},

        ...toastState(),

        // 模板 @load / $watch 呼叫（同 showcase 揭露慣例）
        applyCellFocal,

        markPhotoFailed(name) {
            if (!name) return;
            this.photoFailed[name] = true;
        },

        isFavoriteActress(name) {
            const favs = this.snapshot && this.snapshot.actressFavorites;
            return !!(favs && favs[name]);
        },

        favoriteBusyFor(name) {
            return !!this.favoriteBusy[name];
        },

        // TASK-177-T3b：收藏焦點女優。寫入一律用點擊當下的 name，不再讀 this.sel.actress。
        async addFocusedFavorite() {
            const name = this.sel && this.sel.actress;
            if (!name || !this.snapshot) return;
            if (this.favoriteBusyFor(name)) return;
            if (this.isFavoriteActress(name)) return;
            this.favoriteBusy[name] = true;
            let kind = 'failed';
            let data = null;
            try {
                const res = await fetch('/api/actresses/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name }),
                });
                try { data = await res.json(); } catch (e) { data = null; }
                kind = classifyFavoriteResponse(res.status, data);
            } catch (e) {
                kind = 'failed';
            } finally {
                delete this.favoriteBusy[name];
            }
            if (!_pageAlive) return;
            if (!this.snapshot) return;
            if (kind === 'added' || kind === 'already') {
                this.snapshot.actressFavorites = mergeFavorite(this.snapshot.actressFavorites, name, buildFavoriteEntry(data.actress));
                this.photoFailed[name] = false;
                this.redrawAge(); // I-4：年齡圖命令式重繪
                this.playFavoriteReveal(name);
            }
            const [type, key] = FAVORITE_TOAST[kind];
            this.showToast(window.t(key), type);
        },

        // TASK-177-T4：收藏成功後頭像淡入（焦點已切到別人就不動；node 測試無 $nextTick／motion 時直接略過）
        playFavoriteReveal(name) {
            if (typeof this.$nextTick !== 'function') return;
            const motion = window.OpenAver && window.OpenAver.motion;
            if (!motion) return;
            if (!this.sel || this.sel.actress !== name) return;
            this.$nextTick(() => {
                const els = document.querySelectorAll('#tileActress .insights-focus-avatar:not(.mk) img');
                if (!els.length) return;
                motion.playFadeTo(els, {
                    fromOpacity: 0,
                    opacity: 1,
                    duration: motion.DURATION.fast,
                    overwrite: 'auto',
                    onComplete: () => motion.clearProps(els, 'opacity'),
                });
            });
        },

        recomputeScopedCount() {
            this.scopedCount = scopeRecords(
                getRecords(),
                this.sel,
                null,
            ).length;
        },

        get hasScope() {
            return normalizePeriod(this.sel.period).type !== 'all' || Boolean(this.sel.actress || this.sel.maker);
        },

        /**
         * TASK-161a-T7：片數格可點判定（唯一一處）。
         * 讀真相欄位 scopedCount，不讀補間中的 displayScopedCount。
         */
        get canGoBrowse() {
            return !this.snapshotError && this.scopedCount > 0;
        },

        /**
         * TASK-161a-T7／CD-161a-5：把目前 sel 寫進 showcase_state 後同步導向瀏覽頁。
         * 寫入失敗＝不導航，只 console.warn（I-handoff-1：寫入必須先於導航完成）。
         */
        goBrowse() {
            if (!this.canGoBrowse) return;
            writeHandoffAndNavigate(this.sel);
        },

        /** 帶一枚一次性 extra pill（tag／director／series）跳瀏覽頁；extra 無效＝不寫入不導航。 */
        goBrowseWith(extra) {
            const pill = normalizeExtraPill(extra);
            if (pill === null) return;
            if (!this.canGoBrowse) return;
            writeHandoffAndNavigate(this.sel, pill);
        },

        /**
         * TASK-156e-T3／CD-156e-6：女優榜片數顯示值。
         * 補間進行中讀 boardDisplayCounts；否則 fallback 真相值 row.count。
         */
        topDisplayCount(row) {
            if (!row) return '';
            const v = this.boardDisplayCounts[row.name];
            return v === undefined ? row.count : v;
        },

        /**
         * 空狀態文字 key。skipDim＝該卡「不吃」的那一維（見 CD-161a-2 逐卡表）；
         * 快照失敗／無快照／全庫 0 部一律 no_data。count 的來源只走
         * emptyKeyForCard（該卡範圍內的片數），不傳聚合後的筆數。
         */
        cardEmptyKey(skipDim) {
            if (
                this.snapshotError ||
                !this.snapshot ||
                !(this.snapshot.logicalTitles > 0)
            ) {
                return 'insights.no_data';
            }
            return emptyKeyForCard(getRecords(), this.sel, skipDim);
        },

        redrawYears() {
            updateYearsChart({ sel: this.sel });
        },

        redrawDonut() {
            updateDonutChart({ sel: this.sel });
        },

        redrawTags() {
            updateTagsChart({ sel: this.sel });
        },

        redrawAge() {
            updateAgeChart({
                sel: this.sel,
                favorites: this.snapshot && this.snapshot.actressFavorites,
            });
        },

        redrawDirector() {
            updateFieldBarChart(
                { sel: this.sel },
                'director',
            );
        },

        redrawSeries() {
            updateFieldBarChart(
                { sel: this.sel },
                'series',
            );
        },

        /**
         * §4.2：Top N 誰上榜＝期間∩片商（女優條件不縮榜，只影響置頂附加列）。
         */
        _computeBoardRows() {
            const records = scopeRecords(getRecords(), this.sel, 'actress');
            return buildActressBoard(records, this.sel).rows;
        },

        recomputeBoard() {
            this.boardRows = this._computeBoardRows();
        },

        recomputeGantt() {
            this.ganttRows = buildGanttRows(
                getRecords(),
                _mainMakerYearMap,
                this.sel,
            );
        },

        /**
         * TASK-156c-T4／CD-156c-1／2／5：女優片商分布列表。
         * 呼叫順序在 recomputeGantt() 之後——ganttNames 依賴這次剛算好的
         * this.ganttRows（互斥名單），不是上一輪殘留的舊值。
         * `this.ganttLegend` 是全庫前 8 色票名稱陣列（reactive，T3 存好），
         * 不是舊版模組級 `_makerColorSlots` 物件——避免重建非 reactive 變數
         * 讓模板讀到 stale 資料（見 T3「圖例不渲染」的教訓）。
         * segments 一次算好存進 soloRows，模板只讀結果（FE perf 慣例同 T3）。
         */
        recomputeSolo() {
            const ganttNames = (this.ganttRows || []).map(function (r) {
                return r.name;
            });
            this.soloRows = buildSoloRows(
                getRecords(),
                _mainMakerYearMap,
                this.sel,
                ganttNames,
                this.ganttLegend,
            );
        },

        /**
         * TASK-156d-T4／CD-156d-3：她那列置頂後的一次性強調亮起。掛在既有三個
         * `recomputeGantt()+recomputeSolo()` 呼叫點之後（`_loadSnapshot` 成功、
         * `$watch('sel')`）。年表／分布表各自獨立判斷、
         * 各自獨立比對 `_lastPinnedGanttName`/`_lastPinnedSoloName`（她可能在
         * 其中一張卡是自然排序內置頂、另一張是 rank 外附加置頂，兩者不必同步）。
         * 沒選女優時視為「無置頂」，把記錄值歸零成 `null`——這保證
         * 「清除焦點後重新選回同一人」仍會重新觸發一次強調亮起（同一人連續兩次
         * 被置頂才不重播）。
         *
         * review P2（定稿輪數 2）：年表切到「年齡」軸時，`ganttView('age')` 會用
         * `ganttAgeEligibility` 濾掉沒生日的女優——她若無生日，`this.ganttRows[0]`
         * 仍是她（`pinned===true`，資料層置頂沒問題），但 DOM 實際渲染出來的第一列
         * 會是別人。**`ganttAxis` 是 `.gantt-card` 自己巢狀 `x-data="{ ganttAxis:
         * 'year' }"` 的子層狀態，不在這個父層元件上**——`this.ganttAxis` 在這裡
         * 讀不到值（恆為 `undefined`），呼叫 `this.ganttView(this.ganttAxis)` 只會
         * 一直落到年份分支，驗不出年齡軸的過濾（definite 輪 1 的錯誤修法，已改正）。
         * 改成直接讀 DOM 實際渲染出來的第一列名字（瀏覽器已經套用了不論哪個軸的
         * 過濾結果，不需要重新猜是哪個軸），核對是否等於這次要置頂的名字，不符合
         * 就跳過年表那一條 `playPulse`（不對 DOM 第一列動手，那是別人的列），
         * 分布表（`soloRows` 沒有年齡篩選）不受影響、照常播放。
         */
        _maybePlayPinPulse() {
            const isActress = this.sel.actress != null;
            const ganttFirst = (this.ganttRows || [])[0];
            const soloFirst = (this.soloRows || [])[0];
            const ganttName =
                isActress && ganttFirst && ganttFirst.pinned === true
                    ? ganttFirst.name
                    : null;
            const soloName =
                isActress && soloFirst && soloFirst.pinned === true
                    ? soloFirst.name
                    : null;

            const ganttChanged = ganttName !== _lastPinnedGanttName;
            const soloChanged = soloName !== _lastPinnedSoloName;
            _lastPinnedGanttName = ganttName;
            _lastPinnedSoloName = soloName;

            if (!ganttChanged && !soloChanged) return;
            this.$nextTick(() => {
                const motion = window.OpenAver.motion;
                if (ganttChanged && ganttName) {
                    const el = document.querySelector(
                        '.gantt-table .gantt-row:not(.gantt-head-row)',
                    );
                    const nameEl = el && el.querySelector('.gantt-name');
                    const renderedName = nameEl
                        ? nameEl.textContent.trim()
                        : null;
                    if (el && renderedName === ganttName) motion.playPulse(el);
                }
                if (soloChanged && soloName) {
                    const el = document.querySelector('#soloList .solo-row');
                    if (el) motion.playPulse(el);
                }
            });
        },

        // TASK-156e-T1a：供 macro `:class` 綁定（aggregate 純函式）
        podiumPositionClass,

        _playPodiumEntrance() {
            // TASK-156e-T1a／CD-156e-1 v3：台座層與人員層分離後，依視覺順序
            // 依三人／五人台座視覺順序組 {stand, items} 傳給 playRise（簽名不變）。
            const wrap = this.$refs.boardRow3El;
            if (!wrap) return;
            const visualRanks = this.podiumSize === 5 ? [4, 2, 1, 3, 5] : [2, 1, 3];
            const groups = [];
            for (let i = 0; i < visualRanks.length; i++) {
                const rank = visualRanks[i];
                const stand = wrap.querySelector('.podium-stand--' + rank);
                if (!stand) continue;
                const row = (this.podiumRows || []).find(function (r) {
                    return r.rank === rank;
                });
                let items = [];
                if (row && row.name) {
                    const flipId = 'podium-' + row.name;
                    const person = Array.from(wrap.querySelectorAll('.podium-slot')).find(
                        function (el) { return el.getAttribute('data-flip-id') === flipId; },
                    );
                    if (person) {
                        items = Array.from(
                            person.querySelectorAll('.podium-avatar, .podium-name, .podium-count'),
                        );
                    }
                }
                groups.push({ stand: stand, items: items });
            }
            if (!groups.length) return;
            window.OpenAver.motion.playRise(groups);
        },

        /**
         * TASK-156c-T5 / CD-156c-1 / 6：與她同片搭檔列表。
         * 呼叫順序在 recomputeSolo() 之後。
         */
        recomputeCostar() {
            const focusName = this.sel.actress != null ? this.sel.actress : '';
            this.costarRows = buildCostarRows(
                getRecords(),
                this.sel,
            ).map(function (row) {
                return { name: row.name, count: row.count, self: focusName };
            });
        },

        /**
         * 年表顯示組裝。axis==='age' 時從 ganttRows 再濾沒生日的列。
         * 修正 3（第 3 輪）：同一次 tick 內對同一 axis 的重複呼叫共用
         * `_ganttViewCache`（見該模組級變數註解）；`this.ganttRows`／
         * `this.sel` 仍要在快取判斷之前讀出來，讓 Alpine 對這個 getter
         * 的依賴追蹤不因為加了快取而漏掉條件變動。
         */
        ganttView(axis) {
            const rowsRef = this.ganttRows;
            const selRef = this.sel;
            const favs =
                (this.snapshot && this.snapshot.actressFavorites) || {};
            if (
                _ganttViewCache &&
                _ganttViewCache.axis === axis &&
                _ganttViewCache.rowsRef === rowsRef &&
                _ganttViewCache.selRef === selRef &&
                _ganttViewCache.favs === favs
            ) {
                return _ganttViewCache.result;
            }
            const all = getRecords();
            let result;
            if (axis === 'age') {
                const names = (this.ganttRows || []).map(function (r) {
                    return r.name;
                });
                const elig = ganttAgeEligibility(names, all, favs);
                const ageAxis = ganttAgeAxis(elig.eligibleNames, all, favs);
                const eligSet = new Set(elig.eligibleNames);
                const rows = (this.ganttRows || [])
                    .filter(function (r) {
                        return eligSet.has(r.name);
                    })
                    .map(function (r) {
                        return {
                            name: r.name,
                            appended: !!r.appended,
                            cells: buildGanttAgeCells(
                                r.name,
                                all,
                                favs,
                                _mainMakerYearMap,
                                ageAxis,
                            ),
                        };
                    });
                result = {
                    axis: ageAxis,
                    rows: rows,
                    skippedCount: elig.skippedCount,
                };
            } else {
                const yearAxis = ganttYearAxis(all);
                const yearRows = (this.ganttRows || []).map(function (r) {
                    return {
                        name: r.name,
                        appended: !!r.appended,
                        cells: buildGanttYearCells(
                            r.name,
                            all,
                            _mainMakerYearMap,
                            yearAxis,
                        ),
                    };
                });
                result = { axis: yearAxis, rows: yearRows, skippedCount: 0 };
            }
            _ganttViewCache = {
                axis: axis,
                rowsRef: rowsRef,
                selRef: selRef,
                favs: favs,
                result: result,
            };
            return result;
        },

        ganttCellTitle(cell, axis) {
            if (!cell || cell.state === 'empty') return '';
            const tFn =
                typeof window !== 'undefined' && typeof window.t === 'function'
                    ? window.t
                    : null;
            const label =
                axis === 'age'
                    ? tFn
                        ? tFn('insights.gantt.age_label', { age: cell.age })
                        : String(cell.age)
                    : String(cell.year);
            if (cell.state === 'main') {
                return tFn
                    ? tFn('insights.gantt.tooltip_main', {
                        label: label,
                        total: cell.filmCount,
                        maker: cell.maker,
                        count: cell.makerCount,
                    })
                    : label;
            }
            return tFn
                ? tFn('insights.gantt.tooltip_dot', {
                    label: label,
                    total: cell.filmCount,
                })
                : label;
        },

        /**
         * 修正 1（第 2 輪，真瀏覽器重現）：舊版直接讀模組級非 reactive
         * 變數 `_makerColorSlots`——模板首次渲染（快照載完前）算出 []，
         * 之後 `_loadSnapshot` 寫入 `_makerColorSlots` 不是 Alpine 追蹤的
         * 依賴，x-for 永遠不會重跑，圖例恆空（0 個 .gantt-legend-item）。
         * 改讀 reactive 欄位 `this.ganttLegend`（`_loadSnapshot` 寫入時
         * 觸發依賴），排序改在 `_loadSnapshot` 算好存進去，這裡只回傳。
         */
        ganttLegendMakers() {
            return this.ganttLegend;
        },

        /**
         * 修正 3（第 3 輪，P2 效能回歸）：年份模式只需要欄數，不該經由
         * ganttView() 取（那會連 25 列的格子都建一次）。直接用
         * ganttYearAxis() 算橫軸長度——全庫只需算一次（不隨條件
         * 變，`getRecords()` 整個 session 內只在換快照時變）。
         *
         * 修正 4（第 4 輪，P3 效能回歸）：年齡模式當初也比照年份模式自己
         * 重跑 ganttAgeEligibility／ganttAgeAxis 避開 ganttView()，但這個
         * 顧慮在 ganttView() 加了單筆 tick 快取（`_ganttViewCache`，見該
         * 模組級變數註解）之後已經過時——同一次 tick 內模板本來就會經
         * 表頭／列 x-for 呼叫 ganttView(axis) 把格子建一次，這裡改讀
         * `this.ganttView(axis).axis.length` 只是把那次計算提前觸發，
         * 命中同一把快取、不會多花一次全庫掃描。實測 6521 筆真實片庫、
         * 真實 actressFavorites（23/25 頂尖女優落在年齡合格名單）：改前
         * 切到年齡軸一次完整 tick 約 31–41ms，改後約 5–9ms。
         */
        ganttGridStyle(axis) {
            let n;
            if (axis === 'age') {
                n = this.ganttView(axis).axis.length;
            } else {
                n = ganttYearAxis(getRecords()).length;
            }
            return (
                'grid-template-columns: var(--gantt-name-w) repeat(' +
                n +
                ', minmax(var(--gantt-cell-min-w), 1fr))'
            );
        },

        /**
         * 設女優條件（再點同一位清掉）。寫 this.sel（整個換新），由 $watch('sel') 重繪。
         * 業務鍵字串比對（FE-ALPINE-14）。女優與片商各自獨立、可同時有值（疊加）。
         */
        toggleActressFocus(name) {
            if (!name) return;
            this.sel = toggleActress(this.sel, name);
        },

        /**
         * 設片商條件（圓餅點擊；再點同一家清掉）。不動女優條件（疊加）。
         */
        toggleMakerFocus(name) {
            if (!name) return;
            this.sel = toggleMaker(this.sel, name);
        },

        _commitFocusSel(name, nextSel) {
            if (nextSel) { this.sel = nextSel; return; }
            this.toggleActressFocus(name);
        },

        ganttCellClick(name, cell, axis, event) {
            this.cancelOpenPreview(); // 格子點擊先收預覽（四分支皆適用）
            const year = (axis === 'year' && cell && cell.filmCount > 0) ? cell.year : null;
            if (year === null && this.sel.actress === name) return;
            const rowEl = event.currentTarget.closest('.gantt-row');
            if (year === null) {
                this.flyAndFocusActress(name, { currentTarget: rowEl });
                return;
            }
            const nextSel = toggleGanttCell(this.sel, name, year);
            if (this.sel.actress === name) {
                this.sel = nextSel;
                return;
            }
            this.flyAndFocusActress(name, { currentTarget: rowEl }, nextSel);
        },

        /**
         * TASK-156e-T2／CD-156e-5：五入口共用——設女優焦點並從頭像起飛到女優格（#tileActress）。
         * 清除焦點／找不到頭像時只走 toggle，不飛。
         */
        flyAndFocusActress(name, event, nextSel) {
            this.cancelOpenPreview();
            const isClearing = this.sel.actress === name;
            if (isClearing) {
                if (_activeAvatarGhost) {
                    // 字面與 _flyAvatarToFocusTile 開頭的 remove 分開，mutation from 才唯一
                    const staleGhost = _activeAvatarGhost.el;
                    staleGhost.remove();
                    _activeAvatarGhost = null;
                }
                const clearingTarget = document.querySelector('#tileActress .insights-focus-avatar:not(.mk)');
                if (clearingTarget) {
                    clearingTarget.removeAttribute('data-avatar-fly-hidden');
                    clearingTarget.style.opacity = '1';
                }
                this._commitFocusSel(name, nextSel);
                return;
            }
            let sourceEl = null;
            const currentTarget = event && event.currentTarget;
            if (currentTarget && typeof currentTarget.querySelector === 'function') {
                let selector = null;
                if (currentTarget.matches('.podium-slot')) selector = '.podium-avatar';
                else if (currentTarget.matches('.board-rest-row')) selector = '.board-avatar';
                else if (currentTarget.matches('.gantt-row')) selector = '.gantt-avatar';
                else if (currentTarget.matches('.solo-row')) selector = '.solo-avatar';
                else if (currentTarget.matches('.costar-row')) selector = '[data-costar-role="other"]';
                if (selector) sourceEl = currentTarget.querySelector(selector);
            }
            if (!sourceEl) { this._commitFocusSel(name, nextSel); return; }
            const sourceRect = sourceEl.getBoundingClientRect();
            // getComputedStyle 回傳 live CSSStyleDeclaration；toggle 後 Alpine 可能拆掉
            // 來源節點，之後讀屬性會變空字串。toggle 前拍成純物件快照。
            const liveStyle = getComputedStyle(sourceEl);
            const sourceStyle = {
                borderRadius: liveStyle.borderRadius,
                backgroundColor: liveStyle.backgroundColor,
                color: liveStyle.color,
                fontSize: liveStyle.fontSize,
                fontWeight: liveStyle.fontWeight,
                lineHeight: liveStyle.lineHeight,
                fontFamily: liveStyle.fontFamily,
                display: liveStyle.display,
                alignItems: liveStyle.alignItems,
                justifyContent: liveStyle.justifyContent,
                overflow: liveStyle.overflow,
                boxSizing: liveStyle.boxSizing,
            };
            // TASK-156e-F2：ghost 改掛 .insights-container（document.querySelector，
            // 不用 this.$root——見 _flyAvatarToFocusTile 內註解）而非 body，座標從
            // 「文件相對」改成「容器相對」——減容器 getBoundingClientRect()，不受
            // window 捲動影響，容器又是 position:relative 的定位祖先。
            const container = document.querySelector('.insights-container');
            const containerRect = container.getBoundingClientRect();
            const sourceContainerRect = {
                top: sourceRect.top - containerRect.top,
                left: sourceRect.left - containerRect.left,
                width: sourceRect.width,
                height: sourceRect.height,
            };
            // TASK-156e-F2：來源 <img>（若有）的 object-fit/object-position 快照——
            // ghost 掛回 .insights-container 後雖然能吃到 XXX-avatar img 的 class
            // 規則，但飛行途中 ghost 尺寸由 GSAP 直接 tween 根節點的 inline
            // top/left/width/height，這裡另外把 img 對應值直接套上，雙重保險
            // 確保裁切／置中與來源一致，不依賴 class 規則的載入時序。
            const sourceImgEl = sourceEl.querySelector('img');
            const sourceImgStyle = sourceImgEl
                ? (() => {
                    const imgLiveStyle = getComputedStyle(sourceImgEl);
                    return {
                        objectFit: imgLiveStyle.objectFit,
                        objectPosition: imgLiveStyle.objectPosition,
                    };
                })()
                : null;
            // 必須在 toggle 前 clone：焦點一變，與她同片列會重算重繪，
            // 來源節點在 $nextTick 時可能已被 Alpine 拆掉／清空。
            const sourceClone = sourceEl.cloneNode(true);
            this._commitFocusSel(name, nextSel);
            // 雙 rAF：等 Alpine 插入女優格頭像 + 一幀 layout（costar 進場等）後再量終點，
            // 避免 targetContainerRect 與真實落點差幾 px。
            this.$nextTick(() => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        this._flyAvatarToFocusTile(sourceClone, sourceContainerRect, sourceStyle, sourceImgStyle);
                    });
                });
            });
        },

        /**
         * TASK-156e-T2／CD-156e-5／F2：建立容器相對（.insights-container，見下方
         * 「不用 this.$root」註解）的 ghost，飛向女優格頭像。sourceRect 是點擊當下
         * 換算好的容器相對座標。
         */
        _flyAvatarToFocusTile(sourceEl, sourceRect, sourceStyle, sourceImgStyle) {
            if (_activeAvatarGhost) {
                _activeAvatarGhost.el.remove();
                _activeAvatarGhost = null;
            }

            const target = document.querySelector('#tileActress .insights-focus-avatar:not(.mk)');
            if (!target) return;

            const motion = window.OpenAver && window.OpenAver.motion;
            if (!motion || !motion._shouldAnimate()) {
                target.removeAttribute('data-avatar-fly-hidden');
                target.style.opacity = '1';
                return;
            }
            if (!window.AvatarFly || typeof window.AvatarFly.playFlyToFocus !== 'function') {
                return;
            }
            // TASK-156e-F2：不用 this.$root——Alpine 的 $root magic 綁在「觸發這次
            // expression 求值的 el」，事件來源若在焦點切換當下被 Alpine 重繪／拆掉
            // （costar-row 的 x-if 分支），later async 再讀 this.$root 會是
            // undefined（實測：costar 入口重現，podium/rest/gantt/solo 不會，
            // 因為它們的來源列不會在同一輪條件變更中被整段換掉）。改用
            // document.querySelector 拿穩定 DOM 參照，跟 state.js:1755 既有寫法一致。
            const container = document.querySelector('.insights-container');
            if (!container) return;

            target.setAttribute('data-avatar-fly-hidden', 'true');
            target.style.opacity = '0';

            // sourceEl 可能已是 flyAndFocusActress 預先做好的 clone。
            const ghost = sourceEl.cloneNode(true);
            // 去掉 Alpine <template x-if> 殘留與 x-/:/@ 屬性——ghost 掛回
            // .insights-container 後若被 Alpine 再評估，row 未定義會把已渲染的
            // <img>/<span> 清掉，留下空白替身。
            _stripAlpineForGhost(ghost);
            ghost.setAttribute('data-avatar-fly-ghost', 'true');
            ghost.style.position = 'absolute';
            ghost.style.top = sourceRect.top + 'px';
            ghost.style.left = sourceRect.left + 'px';
            ghost.style.width = sourceRect.width + 'px';
            ghost.style.height = sourceRect.height + 'px';
            ghost.style.margin = '0';
            ghost.style.pointerEvents = 'none';
            ghost.style.zIndex = '2000';
            ghost.style.willChange = 'top, left, width, height';
            ghost.style.opacity = '1';
            ghost.style.borderRadius = sourceStyle.borderRadius;
            ghost.style.backgroundColor = sourceStyle.backgroundColor;
            ghost.style.fontSize = sourceStyle.fontSize;
            ghost.style.fontWeight = sourceStyle.fontWeight;
            ghost.style.color = sourceStyle.color;
            ghost.style.display = sourceStyle.display;
            ghost.style.alignItems = sourceStyle.alignItems;
            ghost.style.justifyContent = sourceStyle.justifyContent;
            ghost.style.overflow = sourceStyle.overflow;
            ghost.style.boxSizing = sourceStyle.boxSizing;
            // TASK-156e-F2：巢狀 <img> 的裁切規則（object-fit/object-position）與
            // 100% 滿版尺寸直接套到 img 本身——不能只靠 ghost 根節點吃 class
            // 規則，因為 XXX-avatar img 的 width/height:100% 需要「父層當下的
            // tween 尺寸」才會對，這裡明寫成 inline style 雙重保險。
            const ghostImgEl = ghost.querySelector('img');
            if (ghostImgEl && sourceImgStyle) {
                ghostImgEl.style.width = '100%';
                ghostImgEl.style.height = '100%';
                ghostImgEl.style.objectFit = sourceImgStyle.objectFit;
                ghostImgEl.style.objectPosition = sourceImgStyle.objectPosition;
            }
            container.appendChild(ghost);

            const containerRectForTarget = container.getBoundingClientRect();
            const targetViewport = target.getBoundingClientRect();
            const targetContainerRect = {
                top: targetViewport.top - containerRectForTarget.top,
                left: targetViewport.left - containerRectForTarget.left,
                width: targetViewport.width,
                height: targetViewport.height,
            };

            const focusName = this.sel.actress != null ? this.sel.actress : null;
            _activeAvatarGhost = { el: ghost, name: focusName };
            window.AvatarFly.playFlyToFocus(ghost, targetContainerRect, {
                onComplete: () => {
                    if (!(_activeAvatarGhost && _activeAvatarGhost.el === ghost)) return;
                    // 補間結束後對齊到「此刻」女優格（layout 可能在飛行中微移），
                    // 留一幀給取樣再移除，滿足落地誤差 <2px。
                    // 用 inline style（不直呼 gsap——pages/insights 禁令）。
                    const live = target.getBoundingClientRect();
                    const liveContainerRect = document.querySelector('.insights-container').getBoundingClientRect();
                    ghost.style.top = (live.top - liveContainerRect.top) + 'px';
                    ghost.style.left = (live.left - liveContainerRect.left) + 'px';
                    ghost.style.width = live.width + 'px';
                    ghost.style.height = live.height + 'px';
                    requestAnimationFrame(() => {
                        if (!(_activeAvatarGhost && _activeAvatarGhost.el === ghost)) return;
                        ghost.remove();
                        target.removeAttribute('data-avatar-fly-hidden');
                        target.style.opacity = '1';
                        _activeAvatarGhost = null;
                    });
                },
            });
        },

        /**
         * TASK-156d-T3／CD-156d-2：`$watch('sel')` 的唯一動效/捲動 sink。
         * TASK-156d-T9／CD-156d-10b：`costarVisible` 翻轉時才觸發 row3 左半格
         * 佔用者循序淡出淡入＋row7 副本 B 獨立淡出淡入（女優焦點但零共演時
         * `costarVisible` 維持 false，不播放）；捲動邏輯仍依 `isActressFocused`
         * 翻轉（CD-156d-10e，不變）。
         * 讀 `this.sel`（reactive）而非把它複製成本地閉包變數跨 `$nextTick` 使用
         * ——CD-156d-2 步驟 4 逐字要求，快速連續觸發時才能永遠依「當下最新」值判斷。
         *
         * `oldCostarRowsLength`：呼叫方（`$watch('sel')`）在 `recomputeCostar()`
         * 覆寫 `this.costarRows` 之前先讀出來的舊值長度。**不能改用 `this.showCostar`
         * 當 `wasCostarVisible` 的代理值**——`showCostar` 只在動畫 `onComplete` 才被
         * 寫入，若同一位女優被快速連點兩次、第二次點擊發生在第一次進場動畫的
         * onComplete 觸發之前，`showCostar` 仍是 stale 的舊值（false），會讓這次
         * 翻轉被誤判成「沒有翻轉」而略過 killTweens／leave 序列，導致第一次動畫
         * 的 onComplete 之後仍把畫面切成「顯示與她同片」——即使焦點已經被第二次
         * 點擊清除。這個迴歸由 `test_interrupt_during_fade_out_matches_direct_set`
         * 抓到（100% 重現，非計時抖動）。改用「當下這輪 `$watch` 開始時、尚未被
         * 覆寫的 `costarRows.length`」＋`wasActress` 算 `wasCostarVisible`，兩者
         * 都是同步值，不受動畫完成時機影響。
         *
         * TASK-156d-T9 round 3：捲動判斷（`wasActress`/`isNowActress`/
         * `switchedActress`）只在這裡：女優格換人才捲，只換期間／片商、
         * 清掉女優都不捲（CD-156d-6）。`oldValue` 是舊的 sel 形狀。
         */
        _handleActressFocusChange(oldValue, oldCostarRowsLength) {
            const wasActress = !!(oldValue && oldValue.actress != null);
            const isNowActress = this.isActressFocused;
            const switchedActress =
                isNowActress &&
                wasActress &&
                oldValue.actress !== this.sel.actress;

            // CD-156d-6：false→true，或維持 true 但換成不同的人 → 捲回頂端。
            // true→false（含清除）不捲動。
            if (isNowActress && (!wasActress || switchedActress)) {
                window.scrollTo({
                    top: 0,
                    behavior: window.OpenAver.prefersReducedMotion ? 'auto' : 'smooth',
                });
            }

            this._syncCostarVisibility(computeCostarVisible(wasActress, oldCostarRowsLength));
        },

        /**
         * TASK-156d-T9 round 3：`costarVisible` 翻轉時的淡出淡入本體，從
         * `_handleActressFocusChange` 抽出——女優格換人與只換期間／片商
         * 共用同一份（CD-156d-10b 的 kill-tweens／
         * 依當下最新值重新開始／不變式 2 全部照舊，不因為呼叫方是誰而不同）。
         * 呼叫方只需要傳「翻轉前」的 `costarVisible`（用當下已知的
         * `isActressFocused` ＋翻轉前的 `costarRows.length` 算出），不捲動——
         * 捲動邏輯留在 `_handleActressFocusChange`，因為 CD-156d-6 明確只認
         * 女優格換人，期間／片商改變不捲動。
         */
        _syncCostarVisibility(wasCostarVisible) {
            const isNowCostarVisible = this.costarVisible;
            if (wasCostarVisible === isNowCostarVisible) return;

            this._forceSettleAllBoardAnims();
            const motion = window.OpenAver.motion;
            const boardEl = this.$refs.boardRow3El;
            const costarEl = this.$refs.costarEl;
            const row7El = this.$refs.row7El;
            // CD-156d-2 步驟 4：每次新觸發前先對這次牽涉到的全部元素 killTweens，
            // 再永遠依當下最新 isActressFocused 從步驟 1/2 重新開始。
            motion.killTweens([boardEl, costarEl, row7El].filter(Boolean));
            const gen = ++_costarSwapGen;
            _costarSwapPendingChains = 2;
            const chainDone = () => {
                if (gen !== _costarSwapGen) return;
                _costarSwapPendingChains -= 1;
            };

            if (isNowCostarVisible) {
                // 步驟 1：進入焦點——costarEl 先淡出既有的 row3 副本 A。
                motion.playFadeTo(boardEl, {
                    opacity: 0,
                    duration: 0.25,
                    onComplete: () => {
                        // CD-156d-5 不變式 2：隱藏後清掉殘留 inline opacity:0，
                        // 讓 style.opacity 回到 ''（下次淡入前用 fromOpacity 強制起始值）。
                        motion.clearProps(boardEl, 'opacity');
                        this.showBoardInRow3 = false;
                        this.showCostar = true;
                        this.$nextTick(() => {
                            motion.playFadeTo(costarEl, {
                                fromOpacity: 0,
                                opacity: 1,
                                duration: 0.25,
                                onComplete: chainDone,
                            });
                        });
                    },
                });
                // row7 副本 B 同時獨立處理：立即顯示、$nextTick 內淡入。
                this.showBoardInRow7 = true;
                this.$nextTick(() => {
                    motion.playFadeTo(row7El, {
                        fromOpacity: 0,
                        opacity: 1,
                        duration: 0.5,
                        onComplete: chainDone,
                    });
                });
            } else {
                // 步驟 2：離開焦點（含清除）——對稱：costarEl 先完全淡出才切回
                // 副本 A 並淡入。
                motion.playFadeTo(costarEl, {
                    opacity: 0,
                    duration: 0.25,
                    onComplete: () => {
                        // CD-156d-5 不變式 2：隱藏後清掉殘留 inline opacity:0。
                        motion.clearProps(costarEl, 'opacity');
                        this.showCostar = false;
                        this.showBoardInRow3 = true;
                        this.$nextTick(() => {
                            motion.playFadeTo(boardEl, {
                                fromOpacity: 0,
                                opacity: 1,
                                duration: 0.25,
                                onComplete: chainDone,
                            });
                        });
                    },
                });
                // row7 副本 B 同時獨立淡出後才隱藏。
                motion.playFadeTo(row7El, {
                    opacity: 0,
                    duration: 0.5,
                    onComplete: () => {
                        // CD-156d-5 不變式 2：隱藏後清掉殘留 inline opacity:0。
                        motion.clearProps(row7El, 'opacity');
                        this.showBoardInRow7 = false;
                        chainDone();
                    },
                });
            }
        },

        /**
         * TASK-156e-T3／CD-156e-6：頁首片數＋女優榜片數顯示層補間（連點防護）。
         * `$watch('sel')` 呼叫；呼叫方在既有 Flip if/else
         * 之後傳入更新前的 `oldBoardRows` 快照。
         */
        _playCountUps(oldBoardRows) {
            const oldDisplay = this.displayScopedCount;
            this.recomputeScopedCount();
            if (_scopedCountTween) { _scopedCountTween.kill(); _scopedCountTween = null; }
            const target = this.scopedCount;
            if (oldDisplay === target) {
                this.displayScopedCount = target;
            } else {
                const gen = ++_scopedCountGen;
                const motion = window.OpenAver.motion;
                _scopedCountTween = motion.playCountUp({
                    from: oldDisplay,
                    to: target,
                    onUpdate: (v) => { this.displayScopedCount = v; },
                    onComplete: () => {
                        if (gen !== _scopedCountGen) return;
                        _scopedCountTween = null;
                    },
                });
            }
            {
                const diffs = diffBoardCounts(oldBoardRows, this.boardRows);
                const newNames = new Set(this.boardRows.map((r) => r.name));
                Object.keys(this.boardDisplayCounts).forEach((name) => {
                    if (newNames.has(name)) return; // 還在榜上，不動她
                    if (_boardCountTweens[name]) {
                        _boardCountTweens[name].kill();
                        delete _boardCountTweens[name];
                    }
                    delete _boardCountGens[name];
                    delete this.boardDisplayCounts[name];
                });
                diffs.forEach((d) => {
                    if (!(d.name in this.boardDisplayCounts)) {
                        this.boardDisplayCounts[d.name] = d.from;
                    }
                });
                const motion = window.OpenAver.motion;
                this.$nextTick(() => {
                    diffs.forEach((d) => {
                        if (_boardCountTweens[d.name]) {
                            _boardCountTweens[d.name].kill();
                        }
                        const gen = (_boardCountGens[d.name] || 0) + 1;
                        _boardCountGens[d.name] = gen;
                        const fromVal = this.boardDisplayCounts[d.name];
                        _boardCountTweens[d.name] = motion.playCountUp({
                            from: fromVal,
                            to: d.to,
                            duration: motion.DURATION.medium,
                            onUpdate: (v) => { this.boardDisplayCounts[d.name] = v; },
                            onComplete: () => {
                                if (_boardCountGens[d.name] !== gen) return;
                                delete this.boardDisplayCounts[d.name];
                                delete _boardCountTweens[d.name];
                            },
                        });
                    });
                });
            }
        },

        isCostarSwapInProgress() {
            return _costarSwapPendingChains > 0;
        },

        _forceSettleAllBoardAnims() {
            _forceSettleAllBoardAnims();
        },

        _settleBoardNonFlipAnims() {
            _settleBoardNonFlipAnims();
        },

        /**
         * TASK-156e-T1b／CD-156e-2：女優榜換位——三個 Flip＋分類手動淡入淡出。
         * 呼叫前呼叫方已確認 costarVisible 未翻轉且 isCostarSwapInProgress()===false。
         */
        _playBoardReorder(visibleWrap) {
            this._settleBoardNonFlipAnims();
            const motion = window.OpenAver.motion;
            if (!visibleWrap) {
                this.recomputeBoard();
                return;
            }

            const oldRows = (this.boardRows || []).slice();
            const newRows = this._computeBoardRows();
            const classified = classifyBoardTransition(oldRows, newRows, this.podiumSize);

            const rowStayerEls = classified.rowStayers
                .map((r) => visibleWrap.querySelector(`[data-flip-id="rest-${CSS.escape(r.name)}"]`))
                .filter(Boolean);
            const podiumReshuffleEls = classified.podiumReshuffle
                .map((r) => visibleWrap.querySelector(`[data-flip-id="podium-${CSS.escape(r.name)}"]`))
                .filter(Boolean);
            const crossStructureEls = classified.crossStructureMovers
                .map((r) => visibleWrap.querySelector(`[data-flip-id="avatar-${CSS.escape(r.name)}"]`))
                .filter(Boolean);

            // TASK-156e-F2：掛回 .insights-container（document.querySelector，不用
            // this.$root——見 _flyAvatarToFocusTile 內註解：$watch('sel') 觸發的
            // 重繪可能讓 Alpine 對這輪 expression 求值綁的 $root 變 undefined）而非
            // document.body，讓替身繼續吃得到 insights.css 全部以 .insights-container
            // 為前綴的規則（圓角／尺寸／字級／flex 版面）；宣告在最外層，下面
            // dropoutClones.forEach 的 container.appendChild 也要用同一個參照。
            const container = document.querySelector('.insights-container');
            const dropoutClones = [];
            if (!window.OpenAver.prefersReducedMotion) {
                const containerRect = container.getBoundingClientRect();
                classified.droppedOut.forEach((d) => {
                    const sel = d.wasPodium
                        ? `[data-flip-id="podium-${CSS.escape(d.name)}"]`
                        : `[data-flip-id="rest-${CSS.escape(d.name)}"]`;
                    const el = visibleWrap.querySelector(sel);
                    if (!el) return;
                    const rect = el.getBoundingClientRect();
                    const clone = el.cloneNode(true);
                    _stripAlpineForGhost(clone);
                    clone.setAttribute('data-board-dropout-ghost', d.name);
                    clone.style.position = 'absolute';
                    clone.style.left = (rect.left - containerRect.left) + 'px';
                    clone.style.top = (rect.top - containerRect.top) + 'px';
                    clone.style.width = rect.width + 'px';
                    clone.style.height = rect.height + 'px';
                    clone.style.margin = '0';
                    clone.style.pointerEvents = 'none';
                    clone.style.zIndex = '40';
                    dropoutClones.push(clone);
                });
            }

            const rowState = motion.flipCapture(rowStayerEls);
            const podiumState = motion.flipCapture(podiumReshuffleEls);
            const avatarState = motion.flipCapture(crossStructureEls);
            const costarSwapGenAtCapture = _costarSwapGen;
            this.recomputeBoard();
            this.$nextTick(() => {
                if (_costarSwapGen !== costarSwapGenAtCapture) return;
                const flipDur = 0.4;
                _playBoardTrackedAnim('flip', (o) => motion.flipFrom(rowState, o), {
                    targets: visibleWrap.querySelectorAll('[data-flip-id^="rest-"]'),
                    nested: true,
                    duration: flipDur,
                });
                _playBoardTrackedAnim('flip', (o) => motion.flipFrom(podiumState, o), {
                    targets: visibleWrap.querySelectorAll('[data-flip-id^="podium-"]'),
                    nested: true,
                    duration: flipDur,
                });
                // absolute:true 只鎖在跨結構移動者——若 targets 用
                // [data-flip-id^="avatar-"] 全選，Flip 會把名單裡所有頭像抽成
                // absolute，390 單欄容器高度瞬間塌陷（CD-156e-7 不變式 6）。
                const avatarTargets = classified.crossStructureMovers
                    .map((r) => visibleWrap.querySelector(`[data-flip-id="avatar-${CSS.escape(r.name)}"]`))
                    .filter(Boolean);
                _playBoardTrackedAnim('flip', (o) => motion.flipFrom(avatarState, o), {
                    targets: avatarTargets,
                    nested: true,
                    absolute: true,
                    fade: true,
                    duration: flipDur,
                });

                classified.brandNewEntrants.forEach((r) => {
                    const el = visibleWrap.querySelector(`[data-flip-id="rest-${CSS.escape(r.name)}"]`);
                    if (!el) return;
                    _playBoardTrackedAnim('fade', (o) => motion.playEnter(el, o), {
                        y: 0,
                        overwrite: 'auto',
                        onComplete: () => motion.clearProps(el, 'opacity'),
                    });
                });
                classified.podiumNewEntrants.forEach((r) => {
                    const el = visibleWrap.querySelector(`[data-flip-id="podium-${CSS.escape(r.name)}"]`);
                    if (!el) return;
                    _playBoardTrackedAnim('fade', (o) => motion.playEnter(el, o), {
                        y: 0,
                        overwrite: 'auto',
                        onComplete: () => motion.clearProps(el, 'opacity'),
                    });
                });

                const newByName = new Map(newRows.map((r) => [r.name, r]));
                classified.crossStructureMovers.forEach((r) => {
                    const newRow = newByName.get(r.name);
                    if (!newRow) return;
                    if (newRow.rank <= this.podiumSize) {
                        const slot = visibleWrap.querySelector(`[data-flip-id="podium-${CSS.escape(r.name)}"]`);
                        if (!slot) return;
                        const els = slot.querySelectorAll('.podium-name, .podium-count');
                        _playBoardTrackedAnim('fade', (o) => motion.playFadeTo(els, o), {
                            fromOpacity: 0,
                            opacity: 1,
                            duration: motion.DURATION.fast,
                            overwrite: 'auto',
                            onComplete: () => motion.clearProps(els, 'opacity'),
                        });
                    } else {
                        const row = visibleWrap.querySelector(`[data-flip-id="rest-${CSS.escape(r.name)}"]`);
                        if (!row) return;
                        const els = row.querySelectorAll('.board-rank, .board-name, .board-count');
                        _playBoardTrackedAnim('fade', (o) => motion.playFadeTo(els, o), {
                            fromOpacity: 0,
                            opacity: 1,
                            duration: motion.DURATION.fast,
                            overwrite: 'auto',
                            onComplete: () => motion.clearProps(els, 'opacity'),
                        });
                    }
                });

                dropoutClones.forEach((clone) => {
                    container.appendChild(clone);
                    _playBoardTrackedAnim('fade', (o) => motion.playFadeTo(clone, o), {
                        opacity: 0,
                        duration: motion.DURATION.fast,
                        onComplete: () => clone.remove(),
                    });
                });
            });
        },

        _hasPreviewPhoto(name) {
            // 收藏存在不代表本機有照片檔（來源沒圖／下載失敗時收藏仍會落地，
            // 見 web/routers/insights.py favorites_by_primary 的 hasPhoto 計算）；
            // spec §3.4.1「只有收藏女優有照片；沒照片的人只顯示首字，不出現預覽」
            // 要看後端算好的 hasPhoto，不能只看「是不是收藏」。
            const favs = this.snapshot && this.snapshot.actressFavorites;
            const fav = favs && name && favs[name];
            return !!(fav && fav.hasPhoto);
        },

        openPreview(name, anchorEl) {
            if (!this._hasPreviewPhoto(name)) return;
            if (_previewTimer) {
                clearTimeout(_previewTimer);
                _previewTimer = null;
            }
            let rect = null;
            if (anchorEl && typeof anchorEl.getBoundingClientRect === 'function') {
                const r = anchorEl.getBoundingClientRect();
                rect = {
                    top: r.top,
                    left: r.left,
                    width: r.width,
                    height: r.height,
                };
            }
            this.previewActress = name;
            this.previewAnchorRect = rect;
        },

        scheduleOpenPreview(name, anchorEl, ev) {
            if (!isHoverPointer(ev)) return;
            if (!this._hasPreviewPhoto(name)) return;
            if (_previewTimer) {
                clearTimeout(_previewTimer);
                _previewTimer = null;
            }
            const self = this;
            const el = anchorEl;
            _previewTimer = setTimeout(() => {
                _previewTimer = null;
                self.openPreview(name, el);
            }, PREVIEW_OPEN_DELAY_MS);
        },

        cancelOpenPreview() {
            if (_previewTimer) {
                clearTimeout(_previewTimer);
                _previewTimer = null;
            }
            this.closePreview();
        },

        closePreview() {
            this.previewActress = null;
            this.previewAnchorRect = null;
        },

        previewPhotoUrl() {
            if (!this.previewActress) return '';
            return _photoUrl(
                this.previewActress,
                this.snapshot && this.snapshot.actressFavorites,
            );
        },

        previewFavorite() {
            return (
                this.previewActress &&
                this.snapshot &&
                this.snapshot.actressFavorites &&
                this.snapshot.actressFavorites[this.previewActress]
            );
        },

        previewPositionStyle() {
            if (!this.previewAnchorRect) return '';
            // 用 clientWidth/Height（不含捲軸）夾限，與 CDP oracle #19 同一基準；
            // innerWidth 含捲軸時會讓浮層右緣看起來「在視窗內」卻超出 clientWidth。
            const de =
                typeof document !== 'undefined' ? document.documentElement : null;
            const viewport = {
                width: de ? de.clientWidth : 0,
                height: de ? de.clientHeight : 0,
            };
            const pos = computePreviewPosition(
                this.previewAnchorRect,
                viewport,
                PREVIEW_POPUP,
            );
            return {
                position: 'fixed',
                left: pos.left + 'px',
                top: pos.top + 'px',
            };
        },

        actressPhotoUrl(name) {
            return _photoUrl(
                name,
                this.snapshot && this.snapshot.actressFavorites,
                { avatar: true },
            );
        },

        actressHasPhoto(name) {
            return this._hasPreviewPhoto(name);
        },

        /**
         * spec §3.1 片數格：主數字下方小字「全庫 N 部」——固定用 logicalTitles
         * （全庫邏輯片數，不隨期間／女優／片商條件縮），不是 scopedCount。
         */
        totalCountLabel() {
            const n = this.snapshot ? this.snapshot.logicalTitles : 0;
            const nStr = Number(n).toLocaleString();
            return typeof window !== 'undefined' && typeof window.t === 'function'
                ? window.t('insights.total_count', { n: nStr })
                : 'insights.total_count';
        },

        clearPeriod() {
            // 只改 reactive 欄位（整個換新）；$watch('sel') 是唯一重繪入口
            this.sel = { ...this.sel, period: { type: 'all' } };
        },

        // 女優格的 ×：只清女優，保留期間與片商
        clearActress() {
            this.sel = { ...this.sel, actress: null };
        },

        // 片商格的 ×：只清片商，保留期間與女優
        clearMaker() {
            this.sel = { ...this.sel, maker: null };
        },

        /**
         * CD-156c-8／CD-161a-2：suffixDims 內任一維有條件時加期間後綴
         * （全庫／單年／範圍），後綴文字由 selection.js 的 suffixLabel 產生。
         */
        _titleWithPeriod(baseKey, suffixDims, params) {
            const tFn =
                typeof window !== 'undefined' && typeof window.t === 'function'
                    ? window.t
                    : null;
            const base = tFn ? tFn(baseKey, params) : baseKey;
            const allLabel = tFn
                ? tFn('insights.donut.library_wide')
                : 'insights.donut.library_wide';
            return base + suffixLabel(this.sel, suffixDims, allLabel);
        },

        /**
         * D156-12：選了片商時標題後綴＝期間標籤（全庫／該年／範圍）；其餘不加後綴。
         */
        donutTitle() {
            return this._titleWithPeriod('insights.row.makers', ['maker']);
        },

        /**
         * D156-12：選了女優時標題後綴＝期間標籤（全庫／該年／範圍）；其餘不加後綴。
         */
        get boardTitle() {
            return this._titleWithPeriod(
                'insights.row.actress_top',
                ['actress'],
                { n: ACTRESS_TOP_N },
            );
        },

        get boardRestTitle() {
            return window.t('insights.row.actress_top_rest', {
                from: this.podiumSize + 1,
                to: ACTRESS_TOP_N,
            });
        },

        /** 頒獎台人數由視窗欄位決定，焦點女優按真實名次自然分流。 */
        get podiumRows() {
            return (this.boardRows || []).filter((r) => r.rank <= this.podiumSize);
        },

        /** 精簡名單包含頒獎台以外的榜內列與榜外焦點女優附加列。 */
        get restRows() {
            return (this.boardRows || []).filter((r) => r.rank > this.podiumSize);
        },

        /**
         * TASK-156d-T3／CD-156d-2：row3 左半格佔用者切換（頒獎台＋名單 ↔ 與她同片）
         * 只在女優焦點時觸發；片商焦點與無焦點視覺上相同（顯示頒獎台＋名單）。
         */
        get isActressFocused() {
            return this.sel.actress != null;
        },

        /**
         * TASK-156d-T9／CD-156d-10a：命名可讀性用 getter，模板不需要直接綁定。
         */
        get costarVisible() {
            return computeCostarVisible(this.isActressFocused, this.costarRows.length);
        },

        get ganttTitle() {
            return this._titleWithPeriod('insights.row.gantt', ['actress']);
        },

        /**
         * CD-156c-8：女優或片商焦點都加期間後綴（`_titleWithPeriod` 第二參數
         * 已設計成接受陣列）。
         */
        get soloTitle() {
            return this._titleWithPeriod('insights.row.actress_distribution', [
                'actress',
                'maker',
            ]);
        },

        /**
         * CD-156c-5：尾端「N 部 · M 家」。M＝相異具名 maker 個數（不含未知），
         * 即使被併進 other 段也算一家（見 aggregate.js buildSoloRows 註解）。
         */
        soloRowLabel(row) {
            const tFn =
                typeof window !== 'undefined' && typeof window.t === 'function'
                    ? window.t
                    : null;
            return tFn
                ? tFn('insights.solo.count_label', {
                    n: row.total,
                    m: row.namedMakerCount,
                })
                : row.total + ' / ' + row.namedMakerCount;
        },

        /**
         * CD-156c-5：「其他」段 tooltip，列出被併入的具名片商（最多 15 家）。
         */
        soloOtherTitle(seg) {
            const tFn =
                typeof window !== 'undefined' && typeof window.t === 'function'
                    ? window.t
                    : null;
            const others = seg.others || [];
            const list =
                others
                    .slice(0, 15)
                    .map(function (o) {
                        return o.maker;
                    })
                    .join('、') + (others.length > 15 ? '…' : '');
            return tFn
                ? tFn('insights.solo.other_title', { n: others.length, list: list })
                : list;
        },

        /**
         * CD-156c-6：尾端「N 部」。
         */
        costarRowLabel(row) {
            const tFn =
                typeof window !== 'undefined' && typeof window.t === 'function'
                    ? window.t
                    : null;
            return tFn
                ? tFn('insights.costar.count_label', { n: row.count })
                : String(row.count);
        },

        focusPhotoUrl() {
            if (this.sel.actress == null) return '';
            return _photoUrl(
                this.sel.actress,
                this.snapshot && this.snapshot.actressFavorites,
                { avatar: true },
            );
        },

        focusMakerColor() {
            if (this.sel.maker == null) return '';
            return colorForMakerName(this.sel.maker);
        },

        focusInitial() {
            const name = this.sel.actress;
            if (!name) return '';
            return String(name).charAt(0);
        },

        // 年份格顯示值：單年 2023、範圍 2019–2023、全部＝空字串（模板另顯示淡色「全部年份」）
        periodTileLabel() {
            return periodLabel(this.sel.period, '');
        },

        // 年表年份欄淡化：年份在目前期間內（單年／範圍含兩端；all 恆 true）
        isYearInSel(year) {
            return periodContainsYear(this.sel.period, Number(year));
        },

        _yearsCallbacks() {
            const self = this;
            return {
                getSel: () => self.sel,
                setPeriod: (next) => {
                    // $watch('sel') 會接 recompute + 重繪
                    self.sel = { ...self.sel, period: normalizePeriod(next) };
                },
            };
        },

        _donutCallbacks() {
            const self = this;
            return {
                getSel: () => self.sel,
                toggleMaker: (name) => {
                    // 與 toggleActressFocus 同一 sink：寫 sel，$watch('sel') 重繪
                    self.toggleMakerFocus(name);
                },
            };
        },

        _tagsCallbacks() {
            const self = this;
            return {
                getSel: () => self.sel,
                goBrowseWith: (extra) => self.goBrowseWith(extra),
            };
        },

        _ageCallbacks() {
            const self = this;
            return {
                getSel: () => self.sel,
                getFavorites: () =>
                    self.snapshot && self.snapshot.actressFavorites,
            };
        },

        _fieldCallbacks() {
            const self = this;
            return {
                getSel: () => self.sel,
                goBrowseWith: (extra) => self.goBrowseWith(extra),
            };
        },

        _onPageShow(event) {
            if (!event || event.persisted !== true) return;
            _pageAlive = true; // bfcache 還原後復活（I-5③）
            // 側欄離頁已 cleanup；bfcache 不重跑 init，還原監聽及下次離頁的 hooks。
            if (this._bindPodiumResize()) this._registerInsightsCleanup();
            const size = podiumSizeForViewport(window.innerWidth);
            if (size !== this.podiumSize) this.podiumSize = size;
            // 快照失敗時從未建圖——不要在 bfcache 還原時建空圖表
            if (this.snapshotError) return;
            // Finding 2：離頁前快照尚未載完（fetch 仍在飛）時，cleanup 已把
            // _pageAlive 設 false，該次回應會被 _loadSnapshot 丟棄——bfcache 還原
            // 回這頁不會自動重跑 init()，此時 this.snapshot 仍是 null 且非
            // snapshotError，要在這裡重新發起一次載入，否則永遠停在空畫面。
            if (this.snapshot === null) {
                _pageAlive = true;
                return this._loadSnapshot();
            }
            if (!areChartsAlive()) {
                const el = document.getElementById('yearsChart');
                if (el) {
                    // callbacks 在 dispose 後仍由 charts 模組保留；若無則重掛
                    reinitYearsAfterDispose();
                    // 若 reinit 因 callbacks 空而沒做事，用目前 this 再掛一次
                    if (!areChartsAlive()) {
                        initYearsChart(el, this._yearsCallbacks());
                        updateYearsChart({
                            sel: this.sel,
                        });
                    }
                }
                const donutEl = document.getElementById('donutChart');
                if (donutEl) {
                    reinitDonutAfterDispose();
                    const donut = getDonutChart();
                    if (!donut || donut.isDisposed()) {
                        initDonutChart(donutEl, this._donutCallbacks());
                        updateDonutChart({
                            sel: this.sel,
                        });
                    }
                }
                const tagsEl = document.getElementById('tagsChart');
                if (tagsEl) {
                    reinitTagsAfterDispose();
                    const tags = getTagsChart();
                    if (!tags || tags.isDisposed()) {
                        initTagsChart(tagsEl, this._tagsCallbacks());
                        updateTagsChart({
                            sel: this.sel,
                        });
                    }
                }
                const ageEl = document.getElementById('ageChart');
                if (ageEl) {
                    reinitAgeAfterDispose();
                    const age = getAgeChart();
                    if (!age || age.isDisposed()) {
                        initAgeChart(ageEl, this._ageCallbacks());
                        updateAgeChart({
                            sel: this.sel,
                            favorites:
                                this.snapshot &&
                                this.snapshot.actressFavorites,
                        });
                    }
                }
                const directorEl = document.getElementById('directorChart');
                if (directorEl) {
                    reinitFieldBarAfterDispose('director');
                    const director = getFieldBarChart('director');
                    if (!director || director.isDisposed()) {
                        initFieldBarChart(
                            directorEl,
                            'director',
                            this._fieldCallbacks(),
                        );
                        this.redrawDirector();
                    }
                }
                const seriesEl = document.getElementById('seriesChart');
                if (seriesEl) {
                    reinitFieldBarAfterDispose('series');
                    const series = getFieldBarChart('series');
                    if (!series || series.isDisposed()) {
                        initFieldBarChart(
                            seriesEl,
                            'series',
                            this._fieldCallbacks(),
                        );
                        this.redrawSeries();
                    }
                }
            } else {
                resizeAll();
            }
        },

        /**
         * 抓快照＋建圖，供 init() 首次載入與 _onPageShow() bfcache 還原後重載共用。
         * token 是這次呼叫的序號；resolve 時序號被後一次呼叫蓋過（或 _pageAlive
         * 已被 cleanup 設 false）就丟棄，不寫入 this.*（Finding 2 的競態修法）。
         */
        async _loadSnapshot() {
            const token = ++_loadToken;
            try {
                const resp = await fetch('/api/insights/snapshot');
                if (!_pageAlive || token !== _loadToken) return;
                if (!resp.ok) {
                    this.snapshotError = true;
                    this.snapshot = null;
                    this.scopedCount = 0;
                    this.displayScopedCount = 0;
                    return;
                }
                const data = await resp.json();
                if (!_pageAlive || token !== _loadToken) return;

                const records = data.records || [];
                const rest = { ...data };
                delete rest.records;

                setRecords(records);
                var slots = buildMakerColorSlots(getRecords());
                setMakerColorSlots(slots);
                this.ganttLegend = Object.keys(slots)
                    .map(function (name) {
                        return { name: name, slot: slots[name] };
                    })
                    .sort(function (a, b) {
                        return a.slot - b.slot || (a.name < b.name ? -1 : 1);
                    })
                    .map(function (e) {
                        return e.name;
                    });
                var mmMap = buildMainMakerYearMap(getRecords());
                setMainMakerYearMap(mmMap);
                _mainMakerYearMap = mmMap;
                this.snapshot = rest;
                this.snapshotError = null;
                // P3-3：新快照可能代表照片檔已落地（或 bfcache 還原後重試機會）；
                // 舊的失敗記錄不該永久卡住，讓 x-if 有機會重新嘗試載入。
                this.photoFailed = {};
                this.recomputeScopedCount();
                this.displayScopedCount = this.scopedCount;
                this.recomputeBoard();
                this.recomputeGantt();
                this.recomputeSolo();
                this._maybePlayPinPulse();
                this.recomputeCostar();
                // TASK-156d-T9 round 3 audit：這裡不需要呼叫 _syncCostarVisibility()
                // ——this.sel 只能被 toggleActressFocus()／clearActress()／clearMaker()／donut 片商
                // 點擊回呼／年份圖點擊寫入，都要點擊已渲染的 UI 才觸發，而這些 UI 在首次快照成功
                // 前不存在，所以 _loadSnapshot() 執行到這裡時 this.sel 必為初始
                // 值（未選女優），costarVisible 恆 false，跟預設顯示旗標（showBoardInRow3:
                // true／showCostar:false）已經一致，沒有「翻轉」可同步。
                if (shouldPlayPodiumEntrance(_podiumEntrancePlayed, this.podiumRows.length)) {
                    _podiumEntrancePlayed = true;
                    this.$nextTick(() => this._playPodiumEntrance());
                }

                const el = document.getElementById('yearsChart');
                if (el) {
                    initYearsChart(el, this._yearsCallbacks());
                    updateYearsChart({
                        sel: this.sel,
                    });
                }
                const donutEl = document.getElementById('donutChart');
                if (donutEl) {
                    initDonutChart(donutEl, this._donutCallbacks());
                    updateDonutChart({
                        sel: this.sel,
                    });
                }
                const tagsEl = document.getElementById('tagsChart');
                if (tagsEl) {
                    initTagsChart(tagsEl, this._tagsCallbacks());
                    updateTagsChart({
                        sel: this.sel,
                    });
                }
                const ageEl = document.getElementById('ageChart');
                if (ageEl) {
                    initAgeChart(ageEl, this._ageCallbacks());
                    updateAgeChart({
                        sel: this.sel,
                        favorites:
                            this.snapshot && this.snapshot.actressFavorites,
                    });
                }
                const directorEl = document.getElementById('directorChart');
                if (directorEl) {
                    initFieldBarChart(
                        directorEl,
                        'director',
                        this._fieldCallbacks(),
                    );
                    this.redrawDirector();
                }
                const seriesEl = document.getElementById('seriesChart');
                if (seriesEl) {
                    initFieldBarChart(
                        seriesEl,
                        'series',
                        this._fieldCallbacks(),
                    );
                    this.redrawSeries();
                }
            } catch {
                if (!_pageAlive || token !== _loadToken) return;
                this.snapshotError = true;
                this.snapshot = null;
                this.scopedCount = 0;
                this.displayScopedCount = 0;
            }
        },

        _bindPodiumResize() {
            if (podiumResizeHandler) return false;
            podiumResizeHandler = () => {
                if (resizePending) return;
                resizePending = true;
                const frame = requestAnimationFrame(() => {
                    resizePending = false;
                    resizeFrame = null;
                    const size = podiumSizeForViewport(window.innerWidth);
                    if (size !== this.podiumSize) this.podiumSize = size;
                });
                resizeFrame = frame;
            };
            window.addEventListener('resize', podiumResizeHandler, { passive: true });
            return true;
        },

        _unbindPodiumResize() {
            if (podiumResizeHandler) window.removeEventListener('resize', podiumResizeHandler);
            podiumResizeHandler = null;
            if (resizeFrame !== null) cancelAnimationFrame(resizeFrame);
            resizePending = false;
            resizeFrame = null;
        },

        _registerInsightsCleanup() {
            if (window.__registerPage) {
                window.__registerPage({
                    cleanup: () => {
                        this._unbindPodiumResize();
                        _pageAlive = false;
                        disposeAll();
                    },
                });
            }
        },

        async init() {
            this._bindPodiumResize();
            // pageshow：模組生命週期內只註冊一次；不進 __registerPage cleanup
            if (!_pageshowBound) {
                _pageshowBound = true;
                window.addEventListener('pageshow', (event) => {
                    // 透過目前頁面 Alpine 實例處理；若頁面已卸載則 no-op
                    const root = document.querySelector('.insights-container');
                    if (!root || !window.Alpine) return;
                    const data = window.Alpine.$data(root);
                    if (data && typeof data._onPageShow === 'function') {
                        data._onPageShow(event);
                    }
                });
            }

            _pageAlive = true;

            // $watch('sel') 是期間／女優／片商任一條件變更後唯一的 recompute + 重繪入口
            // （CD-161a-3：原本分開的期間、女優兩份監看本體合併，差異由 old／new 推得）。
            this.$watch('sel', (value, oldValue) => {
                // TASK-156d-T9／CD-156d-10b：在 recomputeCostar() 覆寫 this.costarRows
                // 之前先記錄舊值長度，供 _handleActressFocusChange 算 wasCostarVisible
                // 用（見該函式內部註解——讀 this.showCostar 當代理值在「同一位女優
                // 快速二連點、第二次點擊發生在第一次動畫 onComplete 之前」的情境會
                // 是 stale 的，因為 showCostar 只在 onComplete 才寫入）。
                // 同一位女優換期間／片商時 buildCostarRows() 重新過濾，costarVisible
                // 可能翻轉，一樣要跑淡出淡入——wasActress 與現在相同、只差舊 costarRows。
                const oldCostarRowsLength = this.costarRows.length;
                const wasActress = !!(oldValue && oldValue.actress != null);
                const wasCostarVisible = computeCostarVisible(
                    wasActress,
                    oldCostarRowsLength,
                );
                this.redrawYears();
                this.redrawDonut();
                this.redrawTags();
                this.redrawAge();
                this.redrawDirector();
                this.redrawSeries();
                this.recomputeCostar();
                // TASK-156e-T3：女優榜片數補間——先快照舊榜，再跑既有 Flip if/else
                const oldBoardRows = this.boardRows;
                if (
                    wasCostarVisible === this.costarVisible &&
                    !this.isCostarSwapInProgress()
                ) {
                    const visibleWrap = this.costarVisible
                        ? this.$refs.row7El
                        : this.$refs.boardRow3El;
                    this._playBoardReorder(visibleWrap);
                } else {
                    this.recomputeBoard();
                }
                this._playCountUps(oldBoardRows);
                this.recomputeGantt();
                this.recomputeSolo();
                this._maybePlayPinPulse();
                this._handleActressFocusChange(oldValue, oldCostarRowsLength);
            });

            this._registerInsightsCleanup();

            await this._loadSnapshot();
        },
    };
}
