/**
 * SearchState - Wishlist Mixin（TASK-140-T5）
 * 書籤清單狀態與 API 接線。提供 loadWishlistCount 供 main.js 生命周期呼叫。
 */

import { detectSwipe } from '@/shared/swipe.js';  // TASK-141b-T5：對照 grid-mode.js:6 既有寫法
import { classifyWishlistAging, ageDaysOf } from '../wishlist-aging.js';  // TASK-141b-T9

// TASK-140-T6：三態互斥的共用 computed。grid／燈箱／detail 三處模板都只問這支，
// 不得各自重寫判斷式（spec F1「同一組三態要出現在三處」）。
export function cardActionState(result) {
    if (result?._notFound || result?._skeleton) return 'none';
    if (result?._localStatus?.exists) {
        return (result._localStatus.count > 1) ? 'play+folder' : 'play';
    }
    return result?._wishlisted ? 'bookmark-remove' : 'bookmark-add';
}

// TASK-141b-T2：測試環境的 document stub 缺 querySelector；裸呼叫會拋錯。
// 降級成 null → 觸發 switchTo* 的直通分支（與無動畫時同行為）。
function safeQuery(sel) {
    return (typeof document !== 'undefined' && typeof document.querySelector === 'function')
        ? document.querySelector(sel)
        : null;
}

// FE-ALPINE-12：listMode 與 pageState 正交。四個狀態容器同時存在於 DOM（x-show），
// 只能依 pageState 選「當前看得見」的那一個，不能 || 串（永遠短路在 #resultCard）。
var SEARCH_STATE_CONTAINERS = {
    result: '#resultCard', empty: '#emptyState', loading: '#loadingState', error: '#errorState'
};
function searchStateContainerSel(pageState) {
    return SEARCH_STATE_CONTAINERS[pageState] || '#resultCard';
}

// 既有測試環境（fakeThis）沒有 Alpine 的 $nextTick；裸呼叫會拋錯。
// 缺方法時直接同步呼叫 fn，行為等同於「animation frame 已經到了」（測試環境本來就不驗動畫時序）。
function safeNextTick(self, fn) {
    if (typeof self.$nextTick === 'function') self.$nextTick(fn);
    else fn();
}

export function searchStateWishlist() {
    return {
        // ===== Wishlist State =====
        wishlistItems: [],
        wishlistCount: 0,
        wishlistLoaded: false,
        _wishlistCoverLoaded: {},  // TASK-141b-T10（CD-19 候選 a）：番號為 key，loadWishlist() 不碰
        _wishlistCoverError: {},   // TASK-141b-T10（CD-19）：同上，破圖旗標
        // 🔴 Codex PR#177 第 2 輪 P2（2026-09-03）：破圖旗標**必須有一條回得來的路**。
        // 上一輪只治了「不要發那個必定 404 的請求」（:src 用 created_at 當閘），沒治根：
        // `_wishlistCoverError` 一旦設起來就永久（CD-19 刻意不讓 loadWishlist() 碰它），
        // 而它記錄的是一個**本質上短暫**的狀態。實測撞到的窗口只要 100ms：
        // `add_wishlist()` 是**先 commit 那一列、才下載封面**（routers/wishlist.py:69→90），
        // 使用者按下加入之後馬上點書籤分頁，GET 拿到的列已經有 created_at、封面檔卻還沒寫完
        // ⇒ 404 ⇒ 旗標永久 ⇒ 那部片在牆上是灰底占位，只有 F5 才會好。
        // ⚠️ 光把旗標清掉沒有用——**實測清了 img 也不會重新請求**（naturalWidth 仍 0、
        // complete 仍 true），只會把整齊的占位換成破圖 icon。唯一有效的手段是**讓 URL 變**。
        // ⇒ 這張表是重試 token：POST 回來且 `cover_available` 為真（＝檔案這一刻確定在硬碟上）
        // 時 bump 一次，`:src` 帶上它 ⇒ 瀏覽器視為新資源、重新請求一次。
        // **為什麼不在 loadWishlist() 每次都重試**：封面檔是本地檔案，404 一次之後除非重新加入
        // 否則永遠 404 ⇒ 每次切分頁都重試是純浪費。唯一**短暫**的 404 就是上面那個下載窗口，
        // 而它的結束時刻正好由 POST 的回應告訴我們。
        _wishlistCoverRetry: {},
        wishlistLightboxOpen: false,   // T11a：書籤燈箱開關（獨立狀態機，不與 lightboxOpen 共用）
        wishlistLightboxIndex: -1,     // T11a：書籤燈箱目前顯示的 wishlistItems 索引
        _wishlistLbImgError: false,    // T11a：燈箱封面破圖 flag（開燈箱時必須重設，否則殘留占位）
        // T7 review P2：切進書籤前的 displayMode，切回搜尋段時還原。
        // 沒有它的話：你在 detail 模式看著某一片 → 點書籤段 → 點回來 → 剛才那張卡
        // 不見了、變成整片 grid 牆，得自己在牆上重新找回那一筆。
        // 為什麼不能乾脆不動 displayMode：wishlist 模式下 displayMode 不得為 'detail'
        // （listMode 對帳表 #2/#3/#7/#29 的前提），所以「記住再還原」是唯一解。
        _preWishlistDisplayMode: null,
        // 🔴 Codex PR#175 P2：連 listMode 一起記。原本只記 displayMode，`switchToSearchList()`
        // 硬設 `listMode = 'search'`——但切進書籤之前可能是 `'file'`（把影片檔拖進來比對的那條
        // 流程）。實測重現：`listMode:'file'`／`fileList` 1 筆 → 點書籤 → 點回搜尋 ⇒ listMode
        // 落在 `'search'`，`fileList` 資料還在記憶體裡但 `#fileList`（search.html:1068）連同
        // 整理列、改番號那排控制項（:1014/:1020/:1036）全部隱藏 ⇒ **使用者的拖曳工作階段
        // 看起來整個不見了**，而且會被 $watch 存進 sessionStorage，重新整理也回不來。
        _preWishlistListMode: null,
        // TASK-141b-T2：連按分頁鈕時，讓上一輪 loadPromise.then 在世代不符時短路，
        // 避免對「已經不是當前檢視」的容器播 playEntry。
        _wishlistViewGeneration: 0,
        // 燈箱換片/開啟動畫的世代旗標。獨立宣告，不與 _wishlistViewGeneration（T2，分頁切換用）
        // 或主燈箱 _lightboxGeneration 共用——FE-ALPINE-04：書籤燈箱是獨立狀態機，三個世代空間互不相干。
        _wishlistLbGeneration: 0,
        _wishlistLbTouchStartX: null,  // TASK-141b-T5：書籤燈箱觸控起點 X（獨立於主燈箱 _lbTouchStartX）
        _wishlistLbTouchStartY: null,  // TASK-141b-T5：書籤燈箱觸控起點 Y
        // TASK-141b-T6：F8.1/F8.2 FLIP 收攏世代旗標。獨立宣告，不與 _wishlistViewGeneration
        // （T2，分頁切換）或 _wishlistLbGeneration（T3，燈箱開關/換片）共用——三個世代空間互不相干。
        _wishlistFlipGeneration: 0,

        // ===== Computed Properties =====
        cardActionState,

        switchToWishlist() {
            // ── 既有邏輯，逐字不動、順序不變：前置記錄必須同步，且早於 displayMode 被覆寫 ──
            if (this.listMode !== 'wishlist') {
                this._preWishlistDisplayMode = this.displayMode;
                this._preWishlistListMode = this.listMode;
            }
            var self = this;
            var gen = ++this._wishlistViewGeneration;

            // 真正的切換＋載入。無論走哪條路徑都會執行，且一定回傳 loadWishlist() 的 promise。
            // T8 review P2：**每次開啟都重新對帳**，不是只有第一次。
            // spec F6 的對帳時機明寫「開啟書籤清單時」；只在 !wishlistLoaded 時載入的話：
            // 你把書籤裡的片掃描入庫 → 切回書籤分頁 → 那筆書籤不會消失，
            // 除非整頁重新整理（owner hard-gate 第 6 條走的就是這條流程）。
            // 成本是每次切換一支**本地** SQLite 查詢，F6 驗收 5「零對外請求」不受影響。
            // `wishlistLoaded` 保留，但語意收斂成「載入過至少一次」——只用來 gate 空狀態，
            // 避免資料還沒回來就先閃一下「還沒有任何書籤」。
            var doSwitch = function () {
                // 世代守衛（Opus 2026-09-03 補，sonnet review P2 的真實可達版本）：
                // 使用者在淡出動畫（DURATION.fast=167ms）跑完之前又點了另一顆分頁鈕時，
                // 這個回呼是「上一輪的」。沒有這道守衛的話它照樣會翻 listMode ＋ 淡入 .wishlist-panel，
                // 使用者會看到書籤面閃一下淡入再被蓋掉——spec F7 驗收 3 的「連按不留半透明殘面」。
                if (self._wishlistViewGeneration !== gen) return;
                self.listMode = 'wishlist';
                self.displayMode = 'grid';
                // 🔴 branch review P2-2（2026-09-03）：先記下 FLIP 世代。
                // `loadWishlist()` **只有在真的排了差集收攏時**才會遞增 `_wishlistFlipGeneration`
                // （見該函式尾段），所以「這次載入有沒有 FLIP」用它比對就問得出來，
                // 不必動 `loadWishlist()` 內部一行。
                var flipGenBefore = self._wishlistFlipGeneration;
                var loadPromise = self.loadWishlist();
                window.SearchAnimations?.playListModeCrossfade?.(null, safeQuery('.wishlist-panel'), {});
                loadPromise.then(function () {
                    if (self._wishlistViewGeneration !== gen) return;
                    // 🔴 不變式：**同一批卡片同一次只能有一支動畫寫它的 opacity。**
                    // 實測呼叫序是 crossfade → capture → playEntry → playFlipFilter：
                    // `playEntry` 是 microtask、FLIP 派發包在 `$nextTick → rAF` 裡，所以
                    // playEntry 一定先跑，先把視窗內的卡設成 opacity 0 / y 20 再往 1 補；
                    // 一個 frame 之後 `Flip.from(state)` 帶著 `props:'opacity'`（capture 時錄到的是 1）
                    // 對同一批卡再開一條 opacity tween，兩條誰都沒 kill 誰
                    // （`Flip.killFlipsOf` 只殺 Flip、playEntry 的 `killTweensOf` 在 Flip 之前）。
                    // 差集收攏是使用者真正該看到的那一幕（spec F8.2 驗收 4「被對帳掉的卡演著離開」），
                    // 進場只是通用轉場 ⇒ **有收攏就讓收攏獨佔**。
                    if (self._wishlistFlipGeneration !== flipGenBefore) return;
                    if (!self.wishlistItems.length) return;
                    window.GridMotion?.playEntry?.(safeQuery('.wishlist-grid'));
                });
                return loadPromise;
            };

            // 重入（restoreState 還原、或重複點同一顆）：不是「切換」，沒有舊面要淡出 ⇒ 直接做、不播 crossfade。
            // ⚠️ 這裡 return 的是 doSwitch()（**會**呼叫 loadWishlist()），**不是** `return;`。
            if (this.listMode === 'wishlist') return doSwitch();

            var oldEl = safeQuery(searchStateContainerSel(this.pageState));
            var fade = window.SearchAnimations?.playListModeCrossfade;
            if (typeof fade !== 'function' || !oldEl) return doSwitch();
            return new Promise(function (resolve) {
                fade(oldEl, null, { onOldFadeComplete: function () { resolve(doSwitch()); } });
            });
        },

        switchToSearchList() {
            var self = this;
            var gen = ++this._wishlistViewGeneration;
            var doSwitch = function () {
                // 世代守衛：與 switchToWishlist() 對稱。`onOldFadeComplete` 是非同步回呼
                // （GSAP tween 完成才觸發），連按時上一輪的回呼會晚於下一輪開始才落地。
                if (self._wishlistViewGeneration !== gen) return;
                // 還原成切進書籤前的那個模式；沒記到就落回 'search'（這顆鈕的預設語意）。
                self.listMode = self._preWishlistListMode || 'search';
                self._preWishlistListMode = null;
                if (self._preWishlistDisplayMode) {
                    self.displayMode = self._preWishlistDisplayMode;
                    self._preWishlistDisplayMode = null;
                }
                var newEl = safeQuery(searchStateContainerSel(self.pageState));
                window.SearchAnimations?.playListModeCrossfade?.(null, newEl, {});
            };
            var oldEl = safeQuery('.wishlist-panel');
            var fade = window.SearchAnimations?.playListModeCrossfade;
            if (typeof fade !== 'function' || !oldEl) { doSwitch(); return; }
            fade(oldEl, null, { onOldFadeComplete: doSwitch });
        },

        async loadWishlistCount() {
            try {
                const resp = await fetch('/api/wishlist/count');
                if (!resp.ok) {
                    console.error('[Wishlist] count 請求失敗:', resp.status);
                    return;
                }
                const data = await resp.json();
                this.wishlistCount = data.count;
            } catch (err) {
                console.error('[Wishlist] count 查詢失敗:', err);
            }
        },

        // Codex review P2（Opus 2026-09-02）：這支是**整包覆蓋**（`this.wishlistItems = data`），
        // 而且沒有任何機制能分辨「這個回應是不是已經過期」。過期窗口確實存在：
        // `switchToSearchList()`（上面）不清空 `wishlistItems`，所以切回書籤分頁的那一瞬間，
        // 畫面會先用**上一次的舊資料**把卡片與垃圾桶鈕渲染出來，新的 GET 這時還在飛。
        // 使用者於是能在舊 GET 回來之前就按下某張卡的移除——舊 GET 晚回來就把剛移除的項目
        // 整包寫回畫面。
        // 窗口大小不是理論值：`GET /api/wishlist` 現在**先對帳再回清單**（141a-T4），
        // 對帳要對每一筆書籤查一次片庫。141a-T1 之前 `get_by_numbers()` 的
        // `UPPER(number)` 吃不到索引、EXPLAIN QUERY PLAN 實測是 `SCAN videos`；
        // 加了 `idx_videos_number_upper` 之後成本只跟**書籤數**有關，不再跟片庫大小成正比
        // ——但窗口仍然存在（網路 ＋ 對帳 ＋ 刪封面檔）。
        // 接上既有的 AbortController registry（`_getAbortSignal`/`_clearAbort`，
        // search-flow.js:938-955，setFileList／loadFavorite／loadMore 同一套），
        // 讓連續兩次載入變成 last-wins（晚回來的舊回應不覆蓋新清單）。
        async loadWishlist() {
            const signal = this._getAbortSignal('loadWishlist');
            try {
                const resp = await fetch('/api/wishlist', { signal });
                if (!resp.ok) {
                    console.error('[Wishlist] list 請求失敗:', resp.status);
                    return;
                }
                const data = await resp.json();

                // TASK-141b-T6（F8.2，設計決策 4）：capture 必須在資料變更之前——此時
                // this.wishlistItems 還是舊資料、data 是新資料，兩者都在手上，可以先算出
                // goneItems 再賦值。只在使用者正看著書籤牆（onWall）且已經載入過一次時才算。
                var onWall = this.listMode === 'wishlist' && !this.wishlistLightboxOpen;
                var grid = (onWall && this.wishlistLoaded) ? safeQuery('.wishlist-grid') : null;
                var flipState = null;
                var goneItems = [];
                if (grid) {
                    var newNumbers = new Set(data.map(function (i) { return i.number; }));
                    goneItems = this.wishlistItems.filter(function (i) { return !newNumbers.has(i.number); });
                    if (goneItems.length) {
                        grid.classList.add('flip-guard');
                        void grid.offsetHeight;  // force reflow
                        flipState = window.GridMotion?.captureFlipState?.(grid) || null;
                        if (!flipState) grid.classList.remove('flip-guard');
                    }
                }

                this.wishlistItems = data;
                // 🔴 branch review P2（2026-09-02）：**清單與計數在這裡一起寫**。
                // 141a 之前「已入手」是使用者按鈕觸發的，`cleanupOwnedWishlist()`
                // 同時扮演「觸發」與「把本地計數拉回權威值」兩個角色；退場時只有
                // 前者被搬到後端，後者沒有東西接手。於是：掃描完成自動移除 3 筆 →
                // 切到書籤分頁 → 牆上剩 2 張，鈕上的 badge 還是寫 5，一直錯到整頁
                // 重新整理（`loadWishlistCount()` 全站唯一呼叫點在 main.js 的初始化，
                // 分頁來回切不會重跑）。
                // 這支的回應就是權威清單，`data.length` 就是權威計數——**不再多接一條線**。
                this.wishlistCount = data.length;
                this.wishlistLoaded = true;

                // TASK-141b-T6：差集收攏播放（掛在既有整包覆蓋之後）。只驗 onLeave 路徑——
                // Alpine x-for 依 :key（番號）重用節點，F8.2 對帳只刪不增，不會有真正「新增」
                // 的節點（設計決策 6）。
                if (grid && flipState) {
                    var gen = ++this._wishlistFlipGeneration;
                    var self = this;
                    safeNextTick(this, function () { requestAnimationFrame(function () {
                        if (self._wishlistFlipGeneration !== gen) {
                            grid.classList.remove('flip-guard');
                            return;
                        }
                        // 同上（Codex PR#177 第 3 輪 P3）：對帳這條路徑與手動移除**共用同一顆
                        // `_wishlistFlipGeneration` 與同一個 class**，所以兩者交錯時症狀相同，
                        // 冪等的重新宣告也要一起補。
                        grid.classList.add('flip-guard');
                        var result = window.GridMotion?.playFlipFilter?.(grid, flipState);
                        if (!result) grid.classList.remove('flip-guard');
                    }); });
                }
            } catch (err) {
                if (err?.name === 'AbortError') return;   // 被新的載入作廢，靜默放棄
                console.error('[Wishlist] list 查詢失敗:', err);
            } finally {
                this._clearAbort('loadWishlist', signal);
            }
        },

        // TASK-141b-T9（F9，CD-5/CD-6/CD-7）：aging 分階/顯示天數。純函式委派 wishlist-aging.js，
        // 每次 render 求值讀 Date.now()（不預存進 item，CD-6；不加計時器，見設計決策 12）。
        wishlistAgingStage(item) {
            return classifyWishlistAging(item.created_at, item.release_date, Date.now());
        },
        wishlistAgingDays(item) {
            return ageDaysOf(item.created_at, Date.now());
        },

        // 🔴 PR#176 第 2 輪窮舉盤點（2026-09-02）——**唯一的計數收斂點**。
        //
        // 不變式：**任何 `await` 之後都不准用相對加減改 `wishlistCount`。**
        //
        // 為什麼上一版的相對加減曾經是對的、現在不是：`:128-131` 那段註解（sonnet
        // review P2-2，在 main 上）主張「增量回滾在任意交錯順序下都收斂」——那句話在
        // 當時成立，因為那時 `wishlistCount` 的**所有**寫入端都是相對的。branch review
        // P2-1 讓 `loadWishlist()` 開始寫**絕對值**（`data.length`）之後，前提就沒了，
        // 但沒人回去作廢那句話。5 組「樂觀更新→回滾」於是變成 3 種相對 ＋ 2 種權威。
        //
        // 可達的壞法（實測，不是理論）：使用者一邊掃描一邊按「加入書籤」→ `repo.add()`
        // 撞上 `upsert_batch` 的寫鎖、阻塞 5 秒後拋 `database is locked` → POST 回 500；
        // 這 5 秒裡使用者以為沒反應、去點了書籤分頁，`GET /api/wishlist` 在同一個持鎖
        // 期間 1 ms 就回來（WAL 讀不擋、沒有已入手書籤時零寫入）並寫入權威值 → POST
        // 才落地做 `-1` ⇒ **badge 比牆上少一張，而且不會自己好**（那顆分頁鈕
        // `listMode !== 'wishlist'` 才會重載，人已經在書籤分頁了）。
        //
        // 收斂方式**不需要新狀態也不需要多打一次網路**：回滾時 `wishlistItems` 已經先
        // 被修正過，而 `wishlistLoaded` 為真時它就是權威清單（`loadWishlist()` 整包覆蓋
        // 時兩者一起寫）⇒ 直接讓計數去對齊清單。`wishlistLoaded` 為假時清單不權威，
        // 但那時也**不可能**發生上述交錯（唯一寫絕對值的 `loadWishlist()` 必定同時把
        // `wishlistLoaded` 設為真），所以相對加減仍然正確，保留作 fallback。
        //
        // ⚠️ 呼叫端必須**先**調整好 `wishlistItems`、**再**呼叫本函式。
        _settleWishlistCountAfterAwait(fallbackDelta) {
            if (this.wishlistLoaded) {
                this.wishlistCount = this.wishlistItems.length;
                return;
            }
            this.wishlistCount = Math.max(0, this.wishlistCount + fallbackDelta);
        },

        async addToWishlist(result) {
            if (!result?.number) return;

            const prevWishlisted = result._wishlisted;
            // 計數用「增量」不用「快照還原」（sonnet review P2-2）：兩張不同卡片
            // 連點時，後者捕到的 prevCount 已經含前者的樂觀 +1；前者失敗時把
            // wishlistCount 寫回自己的 prevCount，會連後者那筆成功的一起抹掉。
            // ⚠️ 這條只管**送出之前**的樂觀 +1；`await` 之後的回滾一律走
            // `_settleWishlistCountAfterAwait()`（原本這裡寫「增量回滾在任意交錯順序下
            // 都收斂」，那句話在 `loadWishlist()` 開始寫絕對值之後就失效了，見該函式註解）。
            result._wishlisted = true;
            this.wishlistCount += 1;
            if (this.wishlistLoaded) {
                this.wishlistItems.unshift(result);
            }

            try {
                const resp = await fetch('/api/wishlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        number: result.number,
                        title: result.title || '',
                        actors: result.actors || [],
                        tags: result.tags || [],
                        maker: result.maker || '',
                        director: result.director || '',
                        series: result.series || '',
                        label: result.label || '',
                        duration: result.duration ?? null,
                        date: result.date || '',
                        cover: result.cover || '',
                        preview_cover_url: result.preview_cover_url || '',
                        sample_images: result.sample_images || [],
                        preview_sample_images: result.preview_sample_images || [],
                        source: result.source || '',
                        url: result.url || '',
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                // 🔴 branch review P2-1（2026-09-02）：端點對「這個番號本來就在」回的是
                // 200 ＋ `added:false`（不是錯誤——加入書籤是冪等的）。不看這個欄位的話，
                // 樂觀 +1 會憑空多算一筆：切換版本會把整顆結果物件換掉、連帶清掉
                // `_wishlisted`，卡片變回「加入書籤」，再按一次就重複計數。
                // 處置與 removeFromWishlist 的 `success:false` 同一套：本地計數已知與 DB
                // 對不上 ⇒ 跟伺服器要權威值；同時把樂觀 unshift 的那筆重複拿掉
                // （原本那筆還在陣列裡，留著會產生同 number 的重複 :key）。
                let data = null;
                try {
                    data = await resp.json();
                } catch (parseErr) {
                    console.error('[Wishlist] add 回應解析失敗:', parseErr);
                }
                // 🔴 不變式（PR#177 第 3 輪的窮舉盤點結論，取代前兩輪的逐個補丁）：
                // **這三張表描述的是「`:src` 這一刻算出來的那條 URL」的載入結果，
                //   不是「這個番號」的歷史 ⇒ 必須整組動。**
                // `cover_available` 為真 ＝ 封面檔這一刻確定在硬碟上，而它可能是「剛下載好」，
                // 也可能是「移除過之後重新加入、換成全新的一份」（DELETE 會把封面檔一起刪掉，
                // routers/wishlist.py:141）⇒ 兩張結果旗標一起作廢、token 一起 bump。
                // ⚠️ 只清旗標不會讓瀏覽器重抓（實測 naturalWidth 仍 0）——token 才是讓 URL 變的那一半。
                //
                // **位置在兩個早退之前是刻意的**：`added:false`（重複加入）時後端一樣算好了
                // 這個欄位（routers/wishlist.py:95 ＝ 檔案存不存在），早退會把它丟掉——
                // 那正是「吃到 404 窗口 → 切版本讓 _wishlisted 被清掉 → 再按一次加入」
                // 那條路徑會永遠灰底無圖的原因。
                // （`already_owned` 分支後端不回這個欄位，走到這裡自動 no-op。）
                //
                // 為什麼不必動 removeFromWishlist()／loadWishlist()：移除之後 `loaded` 唯一還
                // 看得見的路徑就是「同番號再被加入」，而那條路必定經過這裡。
                // loadWishlist() 更是明令不得碰（CD-19：清了整面牆每次切回都重閃骨架）。
                if (data?.cover_available) {
                    delete this._wishlistCoverError[result.number];
                    delete this._wishlistCoverLoaded[result.number];
                    this._wishlistCoverRetry[result.number] = Date.now();
                }
                if (data?.already_owned) {
                    result._wishlisted = prevWishlisted;
                    if (this.wishlistLoaded) {
                        this.wishlistItems = this.wishlistItems.filter((i) => i !== result);
                    }
                    this._settleWishlistCountAfterAwait(-1);
                    result._localStatus = data.local_status;
                    this.showToast(window.t('search.toast.wishlist_already_owned'), 'info');
                    return;
                }
                if (data?.added === false) {
                    if (this.wishlistLoaded) {
                        this.wishlistItems = this.wishlistItems.filter((i) => i !== result);
                    }
                    await this.loadWishlistCount();
                    return;
                }
            } catch (err) {
                console.error('[Wishlist] add 失敗:', err);
                result._wishlisted = prevWishlisted;
                if (this.wishlistLoaded) {
                    this.wishlistItems = this.wishlistItems.filter((i) => i !== result);
                }
                this._settleWishlistCountAfterAwait(-1);
            }
        },

        addToWishlistFromGrid(result, event) {
            var fromEl = event?.target?.closest('.av-card-preview')?.querySelector('.av-card-preview-img img') || null;
            return this._addToWishlistWithFly(result, fromEl);
        },

        addToWishlistFromLightbox(result) {
            var fromEl = safeQuery('.showcase-lightbox:not(.wishlist-lightbox) .lightbox-cover img');
            return this._addToWishlistWithFly(result, fromEl);
        },

        addToWishlistFromDetail(result) {
            var fromEl = safeQuery('.av-card-full-cover-img');
            return this._addToWishlistWithFly(result, fromEl);
        },

        _addToWishlistWithFly(result, fromEl) {
            var promise = this.addToWishlist(result);
            var toEl = safeQuery('#wishlistToggleBtn');
            window.GhostFly?.playInboundFly?.({
                fromEl: fromEl,
                toEl: toEl,
                // ⚠️ Codex PR#177 P2（2026-09-03，**已判 decline，理由留在這裡**）：
                // 這個 fallback 的文案逐字是「已加入書籤」（locales/zh_TW.json:268）——
                // 一句完成式斷言。而它是在 `await fetch` 回來**之前**就可能被說出口的。
                //
                // 為什麼今天不修：
                // ① **這條分支現在打不到。** 觸發條件是 `#wishlistToggleBtn` 的 rect 寬或高為 0
                //    （ghost-fly.js:955）。那顆鈕在 search.html 是固定佈局、無 x-show/x-if，
                //    全庫 CSS 查無任何 display:none 命中它。**320px（比任何斷點都窄）實測 32×32、
                //    visible**。
                // ② 就算打得到，它也只是**同一個樂觀斷言的文字版**：卡片按鈕在同一個同步區塊裡
                //    就已經翻成「移除書籤」、badge 也已經 +1。三個訊號同源，只把其中一個
                //    改成「等結果」並不自洽。
                // ③ 三個一起等結果 ＝ Codex 建議的做法，代價是**每一次成功加入**的第一個回饋都要
                //    等 POST 回來——而那支端點是**同步下載封面**的（routers/wishlist.py:90 →
                //    wishlist_cover_cache.py:104，兩個網址各 timeout 30s）⇒ 最壞 60 秒才有反應。
                //    為一條打不到的路徑，讓所有人的正常路徑退化，方向是反的（T8 設計決策 5）。
                //
                // 🔴 **如果哪天你要在窄螢幕把 #wishlistToggleBtn 藏起來，這條就活了**——
                // 那時要一起把這句 toast 改成「等 addToWishlist() 的結果為真的新增才說」。
                fallback: {
                    toastFn: (msg) => this.showToast(msg, 'success', 1500),
                    message: window.t('search.toast.wishlist_added_offscreen')
                }
            });
            return promise;
        },

        async removeFromWishlist(number, context = 'search') {
            if (!number) return;

            // TASK-141b-T6（設計決策 1/3/4/8）：capture 必須在資料變更之前。
            // context 由呼叫端顯式傳入（'wall'|'lightbox'|'search'）——T6 只接書籤牆這一處
            // （'wall'）；'lightbox' 由 T7 接、'search' 由 T8 接，兩者現在都不播 FLIP。
            var grid = (context === 'wall') ? safeQuery('.wishlist-grid') : null;
            var flipState = null;
            if (grid) {
                grid.classList.add('flip-guard');
                void grid.offsetHeight;  // force reflow（比照 state-videos.js _animateFilter()）
                flipState = window.GridMotion?.captureFlipState?.(grid) || null;
                if (!flipState) grid.classList.remove('flip-guard');  // capture 失敗不留殘 class
            }

            const matchedResults = (this.searchResults || []).filter((r) => r.number === number);
            const prevFlags = matchedResults.map((r) => r._wishlisted);
            const removedItem = this.wishlistLoaded
                ? this.wishlistItems.find((i) => i.number === number)
                : null;

            this.wishlistCount = Math.max(0, this.wishlistCount - 1);  // 增量，理由同 addToWishlist
            matchedResults.forEach((r) => { r._wishlisted = false; });
            if (this.wishlistLoaded) {
                this.wishlistItems = this.wishlistItems.filter((i) => i.number !== number);
            }

            // TASK-141b-T6：FLIP 播放（掛在既有樂觀更新之後，設計決策 4）。世代旗標讓連續呼叫時，
            // 前一次尚未播完的動畫世代失效——一次收攏、不逐張排隊（設計決策 4／DoD 4）。
            if (grid && flipState) {
                var gen = ++this._wishlistFlipGeneration;
                var self = this;
                safeNextTick(this, function () { requestAnimationFrame(function () {
                    if (self._wishlistFlipGeneration !== gen) {
                        grid.classList.remove('flip-guard');
                        return;
                    }
                    // 🔴 Codex PR#177 第 3 輪 P3（2026-09-03）：**重新宣告 flip-guard，不是多此一舉。**
                    // rAF 回呼依註冊順序執行，所以「連按兩張卡的垃圾桶」時是：
                    // A(stale) 先跑 → 走上面那條 `remove('flip-guard')` → B(current) 才跑。
                    // ⇒ **最新那次的 FLIP 在沒有 guard 的情況下開始播**（實測重現：flushFrames 之後
                    // class 已不在，而 playFlipFilter 照樣被呼叫）。
                    // 為什麼不改成「stale 分支不要 remove」：那會讓既有的
                    // `T6-DoD5b-generation-mismatch-no-residual-flip-guard` 轉紅——它守的是
                    // 「世代不符卻沒人接手清理」的殘留，範圍比本條更廣，不該為了本條讓它變弱。
                    // 這一行是**冪等的加法**：class 已在就沒事，被上一個世代拔掉就補回來。
                    // 移除的責任沒有改變（下面的 `!result` 分支 ＋ playFlipFilter 的 onComplete）。
                    grid.classList.add('flip-guard');
                    var result = window.GridMotion?.playFlipFilter?.(grid, flipState);
                    if (!result) grid.classList.remove('flip-guard');
                    // flip-guard 由 playFlipFilter 的 onComplete 移除（既有機制）
                }); });
            } else if (context === 'search') {
                // TASK-141b-T8（設計決策 3，F8.3）：badge 收縮反饋，卡片本身不動。
                window.SearchAnimations?.playWishlistBadgeShrink?.(safeQuery('.mode-toggle-badge'));
            }

            try {
                const resp = await fetch(`/api/wishlist/${encodeURIComponent(number)}`, {
                    method: 'DELETE',
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                // Codex review P2（Opus 2026-09-02）：端點對「那一列本來就不在」回的是
                // **HTTP 200 `{success:false}`**（wishlist.py:104），不是錯誤碼。只看 `resp.ok`
                // 的話那次會被當成刪除成功，樂觀扣掉的計數永遠補不回來——而 `loadWishlistCount()`
                // 只掛在 main.js 的生命周期初始化，書籤／搜尋分頁來回切**都不會重跑**，數字要
                // 整個離開頁面再回來才會校正。（此處刻意不寫出那支函式的字面名稱：本檔有一條
                // 「不得出現該字面」的守衛，T11a 踩過註解餵飽守衛、這次是註解踩壞守衛。）
                //
                // 這裡刻意**不**回滾。`success:false` 的語意是「伺服器上已經沒有這一列」，
                // 把它 unshift 回去等於在畫面塞一張 DB 裡不存在的幽靈卡、並讓計數高於實際，
                // 比不處理更糟。正確處置是承認本地計數已經和 DB 對不上，直接跟伺服器要
                // 權威值（`/api/wishlist/count` 是單一 COUNT(*)，不走 videos 全表掃描）。
                let data = null;
                try {
                    data = await resp.json();
                } catch (parseErr) {
                    // 2xx 但 body 不是合法 JSON：刪除本身已成功，狀態不動
                    console.error('[Wishlist] remove 回應解析失敗:', parseErr);
                }
                if (data?.success === false) {
                    await this.loadWishlistCount();
                }
            } catch (err) {
                console.error('[Wishlist] remove 失敗:', err);
                matchedResults.forEach((r, idx) => { r._wishlisted = prevFlags[idx]; });
                if (this.wishlistLoaded && removedItem
                    && !this.wishlistItems.some((i) => i.number === removedItem.number)) {
                    // 同一次窮舉盤點順手補的正向鎖：若 `loadWishlist()` 在這次 DELETE
                    // 飛的期間落地，它整包覆蓋回來的清單**已經含**這一筆（刪除失敗
                    // ⇒ 伺服器上還在），無條件 unshift 會塞出同 number 的重複 :key。
                    // 🔴 Codex PR review P2（141b-T7 引入的表面）：燈箱是**唯一**用裸陣列索引
                    // （wishlistLightboxIndex）定位的消費端。回滾把這一筆塞回陣列**開頭**（不是
                    // 原位），開頭以後的每一個索引都位移一格 ⇒ 使用者的索引沒動、底下那一片卻換了。
                    // 書籤牆不受影響：它是 :key="item.number"（keyed by identity），重排只是換位置。
                    //
                    // 🔴 不變式（delta review 後改訂，見下方「為什麼換掉上一版」）：
                    //     **回滾不得改變畫面上當下那一片。**
                    // 作法：改動陣列**之前**先記下畫面上那一筆的 number，改完之後把索引重新指回它。
                    // 這是純粹的位移補償，不做任何導航。
                    //
                    // 為什麼換掉上一版：上一版的不變式訂成「回到**被刪的**那一片」，兩個方向都錯——
                    //   ① 就算沒有競態也錯：刪 B 時畫面早就樂觀切到 C 了，把索引拉回 B 等於
                    //      多做一次使用者沒要求的換片（C→B），而不是「不要跳」。
                    //   ② 有競態時更錯（Codex delta review 抓到）：DELETE 撞 DB 鎖時是**5 秒**的
                    //      busy timeout，那 5 秒裡使用者早就按到下一張、下下一張了；晚到的失敗回應
                    //      會把他從 D 硬拉回 B。
                    // 讀「當下顯示的那一筆」而不是「當初被刪的那一筆」，同時解掉這兩個——
                    // 而且不需要世代旗標：它從來不導航，沒有「舊請求該不該生效」這個問題。
                    const shownBefore = this.wishlistLightboxOpen
                        ? this.wishlistItems[this.wishlistLightboxIndex]?.number
                        : undefined;
                    this.wishlistItems.unshift(removedItem);
                    if (shownBefore !== undefined) {
                        const stillIdx = this.wishlistItems.findIndex((i) => i.number === shownBefore);
                        if (stillIdx >= 0) this.wishlistLightboxIndex = stillIdx;
                    }
                }
                this._settleWishlistCountAfterAwait(+1);
            }
        },

        currentWishlistLightboxItem() {
            if (this.wishlistLightboxIndex < 0 || this.wishlistLightboxIndex >= this.wishlistItems.length) return undefined;
            return this.wishlistItems[this.wishlistLightboxIndex];
        },

        openWishlistLightbox(index) {
            if (this.wishlistLightboxOpen && this.wishlistLightboxIndex === index) return;
            if (this.wishlistLightboxOpen && this.wishlistLightboxIndex !== index) {
                var dir = index > this.wishlistLightboxIndex ? 'next' : 'prev';
                this._animateWishlistLightboxSwitch(index, dir);
                return;
            }

            var fromRect = null, coverSrc = null;
            var grid = safeQuery('.wishlist-grid');
            var card = grid ? grid.querySelector('[data-slot="' + index + '"]') : null;
            var img = card ? card.querySelector('.av-card-preview-img img') : null;
            if (img && img.complete && img.getBoundingClientRect().width > 0) {
                fromRect = img.getBoundingClientRect();
                coverSrc = img.src;
            }

            this._wishlistLbImgError = false;
            this.wishlistLightboxIndex = index;
            var lbEl = safeQuery('.wishlist-lightbox');
            if (lbEl) lbEl.classList.add('gsap-animating');
            this.wishlistLightboxOpen = true;

            var gen = ++this._wishlistLbGeneration;
            var self = this;
            safeNextTick(this, function () {
                if (self._wishlistLbGeneration !== gen) return;
                var el = safeQuery('.wishlist-lightbox');
                if (!el) return;
                if (fromRect && window.GhostFly?.playGridToLightbox) {
                    window.GhostFly.playGridToLightbox(fromRect, el, { coverSrc: coverSrc });
                    window.SearchAnimations?.playLightboxOpen?.(el, { skipCover: true });
                } else {
                    window.SearchAnimations?.playLightboxOpen?.(el, {});
                }
            });
        },

        closeWishlistLightbox() {
            // ★ fly-back capture（對照 grid-mode.js closeLightbox() :176-180）——
            // 🔴 必須在 wishlistLightboxOpen=false 之前抓（設計決策 2）：Alpine 一旦把燈箱
            // 隱藏，getBoundingClientRect() 就會回傳寬高皆 0，playLightboxToGrid 的
            // 「起點無效」分支（ghost-fly.js:834）會被觸發 ⇒ 封面直接消失、不拋錯。
            var closingIndex = this.wishlistLightboxIndex;
            var lbEl = safeQuery('.wishlist-lightbox');
            var lbImg = lbEl ? lbEl.querySelector('.lightbox-cover img') : null;
            var flybackFromRect = lbImg ? lbImg.getBoundingClientRect() : null;
            var flybackCoverSrc = lbImg ? lbImg.src : null;

            // 世代旗標先遞增（對照 grid-mode.js:182，順序在 kill 之前），讓 T3 懸置的
            // $nextTick 回呼（開啟／換片動畫）在關閉之後不再執行。
            this._wishlistLbGeneration++;

            // CD-20：kill 字面固定 'lightboxOpen' + 'lightboxSwitch'（與 T3 的
            // _animateWishlistLightboxSwitch、對照物 grid-mode.js:184-187 一致；
            // 訂正 plan 草稿碼只 kill 單一 id 的漏洞，見上方「Opus 訂正 plan 草稿碼」）。
            if (typeof gsap !== 'undefined') {
                gsap.getById('lightboxOpen')?.kill();
                gsap.getById('lightboxSwitch')?.kill();
            }
            if (lbEl) lbEl.classList.remove('gsap-animating');
            this.wishlistLightboxOpen = false;

            // ★ Fly-back（對照 grid-mode.js:198-206）。找不到目標卡就不呼叫——
            // 視窗外／已捲走的退化淡出交給 playLightboxToGrid 自己的 abort() 分支
            // （ghost-fly.js:842-869），T4 不寫任何 viewport 判斷（設計決策 5）。
            if (closingIndex >= 0 && flybackFromRect && window.GhostFly?.playLightboxToGrid) {
                safeNextTick(this, function () {
                    var grid = safeQuery('.wishlist-grid');
                    var cardEl = grid ? grid.querySelector('[data-slot="' + closingIndex + '"]') : null;
                    if (cardEl) {
                        window.GhostFly.playLightboxToGrid(flybackFromRect, cardEl, {
                            coverSrc: flybackCoverSrc, fromImg: lbImg
                        });
                    }
                });
            }
        },
        removeFromWishlistInLightbox() {
            var item = this.currentWishlistLightboxItem();
            if (!item) return;
            var oldIndex = this.wishlistLightboxIndex;
            this.removeFromWishlist(item.number, 'lightbox');
            // TASK-141b-T7（設計決策 4，時序前提已核對 removeFromWishlist() 現況成立，見「現況分析」B 段）：
            // 樂觀過濾 this.wishlistItems = this.wishlistItems.filter(...) 是同步執行、在
            // await fetch(...) 之前，呼叫後立即讀 this.wishlistItems.length 已經是新長度。
            var newLen = this.wishlistItems.length;
            if (newLen === 0) {
                this.closeWishlistLightbox();
            } else {
                this.wishlistLightboxIndex = Math.min(oldIndex, newLen - 1);
                this._wishlistLbImgError = false;
            }
        },

        // 三支換片的方法都要重設 _wishlistLbImgError（Opus 2026-09-02 補，grok 自報的偏離 #2）：
        // 只在 open() 重設的話，先看到一部沒封面的片、再按箭頭切到有封面的那部，
        // 封面不會出現——畫面停在「無圖」占位，使用者會以為那部也沒封面。
        // 索引沒變（滑到頭）時直接 return，不播動畫、不重設 flag（設計決策 8）。
        prevWishlistLightbox() {
            var newIndex = Math.max(0, this.wishlistLightboxIndex - 1);
            if (newIndex === this.wishlistLightboxIndex) return;
            this._animateWishlistLightboxSwitch(newIndex, 'prev');
        },

        nextWishlistLightbox() {
            var newIndex = Math.min(this.wishlistItems.length - 1, this.wishlistLightboxIndex + 1);
            if (newIndex === this.wishlistLightboxIndex) return;
            this._animateWishlistLightboxSwitch(newIndex, 'next');
        },

        // CD-20：kill 字面固定 'lightboxOpen' + 'lightboxSwitch'（對照 grid-mode.js prevLightboxVideo）。
        // 共用主搜尋燈箱那兩支 id 是安全的——兩個燈箱互斥不能同時開，且每條 timeline 的
        // onComplete/onInterrupt 都閉包持有自己的 lightboxEl。
        _animateWishlistLightboxSwitch(newIndex, direction) {
            if (typeof gsap !== 'undefined') {
                gsap.getById('lightboxOpen')?.kill();
                gsap.getById('lightboxSwitch')?.kill();
            }
            var lbEl = safeQuery('.wishlist-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            this._wishlistLbImgError = false;
            this.wishlistLightboxIndex = newIndex;
            var gen = ++this._wishlistLbGeneration;
            var self = this;
            safeNextTick(this, function () {
                if (self._wishlistLbGeneration !== gen) return;
                var content = safeQuery('.wishlist-lightbox .lightbox-content');
                window.SearchAnimations?.playLightboxSwitch?.(content, direction, {});
            });
        },

        // TASK-141b-T5：書籤燈箱觸控滑動（CD-1，對照 grid-mode.js:427-466 的 _lbTouchStart/_lbTouchEnd）。
        // 獨立一對 state／handler，不與主燈箱共用（FE-ALPINE-04：書籤燈箱是獨立狀態機）。
        _wishlistLbTouchStart(e) {
            if (e.touches && e.touches.length > 0) {
                this._wishlistLbTouchStartX = e.touches[0].clientX;
                this._wishlistLbTouchStartY = e.touches[0].clientY;
            }
        },

        _wishlistLbTouchEnd(e) {
            if (this._wishlistLbTouchStartX === null) return;
            var endX = e.changedTouches && e.changedTouches.length > 0
                ? e.changedTouches[0].clientX
                : null;
            var endY = e.changedTouches && e.changedTouches.length > 0
                ? e.changedTouches[0].clientY
                : null;
            if (endX === null || endY === null) {
                this._wishlistLbTouchStartX = null;
                this._wishlistLbTouchStartY = null;
                return;
            }
            // 攔截短路串（比照主燈箱 grid-mode.js:448-453；x-trap.inert 只管焦點/樣式，
            // 不保證 @touchend.passive 監聽器不被觸發，設計決策 5）
            if (this.sampleGalleryOpen || this.rescrapeOpen) {
                this._wishlistLbTouchStartX = null;
                this._wishlistLbTouchStartY = null;
                return;
            }
            // [branch review P3-8] 主燈箱的第三條短路（grid-mode.js:453「燈箱沒開不換片」）
            // T5 鏡射時漏抄。今天碰不到——`.showcase-lightbox` 關著時是 pointer-events:none
            // （showcase.css:857）——但那是**別的檔案的樣式**在替這支 handler 擋，
            // 哪天有人給子元素補 pointer-events:auto 就露出來。三條要齊。
            if (!this.wishlistLightboxOpen) {
                this._wishlistLbTouchStartX = null;
                this._wishlistLbTouchStartY = null;
                return;
            }
            // 🔴 順序不變式（設計決策 2）：先讀座標算 dir，再清空 state——
            // 顛倒的話 detectSwipe(null, null, endX, endY, 50) 因為 null 在算術運算會
            // 被當成 0（不是 NaN），結果會依 endX/endY 的絕對值而定，不是穩定的「沒反應」，
            // 比單純沒反應更難查。
            var dir = detectSwipe(this._wishlistLbTouchStartX, this._wishlistLbTouchStartY, endX, endY, 50);
            this._wishlistLbTouchStartX = null;
            this._wishlistLbTouchStartY = null;
            if (dir === 'left') {
                this.nextWishlistLightbox();
            } else if (dir === 'right') {
                this.prevWishlistLightbox();
            }
        },
    };
}
