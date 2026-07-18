/**
 * state-lightbox.js — Showcase ESM（54b-T1b）
 *
 * Lightbox / Sample Gallery / Picker / User Tags / Keyboard 邏輯。
 * state-lightbox.js 超 700 行例外：picker 是動畫密集型邏輯，與 lightbox 業務不可分割。
 * 詳見 plan-54b.md CD-54B-1。
 *
 * 從 state-base.js import 共用大陣列（F1：移出 Alpine reactive scope）。
 */

import { _filteredVideos, _filteredActresses, _killLightboxTimelines, _NO_COVER_PLACEHOLDER } from '@/showcase/state-base.js';
import { POSTER_CROP_MAX_W } from '@/shared/breakpoints.js';
import { detectSwipe } from '@/shared/swipe.js';
import { isHorizontalWheel, isVerticalWheel, createWheelNav } from '@/shared/wheel-nav.js';
import { waitForMount } from '@/shared/dom-timing.js';
import { parseFocal, clampMaskWinLeft } from '@/shared/focal.js';
// 100b-T2a：CD-2 軸向/凍結判定 + 亮窗幾何純函式抽至 shared/mask-geometry.js（可測試性——
// 本檔的 `@/showcase/...` importmap alias 只有瀏覽器認得，node:test 無法直接 import 本檔；
// mask-geometry.js 只用相對路徑 import，node:test 可直接驗證，見該檔開頭說明）。
import { computeMaskWinGeometry, computeMaskDragRoom, MASK_MIN_DRAG_ROOM, computeMaskSettleGeometry } from '@/shared/mask-geometry.js';
import { syncActressFields } from '@/shared/actress-sync.js';

// 排除清單容器（橫向捲動列表/表格）：命中即整條 wheel handler 提早 return，
// 讓原生橫向捲動不受影響（見 TASK-102d-T1.md「技術要點」排除清單段）。
const WHEEL_EXCLUDE_SELECTOR = '.sample-strip, .sg-thumbs, .picker-candidates-grid, .table-scroll-container, .overflow-x-auto';
// 102d P2b（owner 拍板 2026-07-19）：overlay 內可垂直捲動的子容器（lightbox metadata 面板，
// showcase.css:785/946 `.lightbox-metadata{overflow-y:auto}`）——垂直滾輪命中時交還原生捲動，
// 不吃導航（僅 vertical 分支檢查，horizontal 分支不受影響、行為不變）。
const WHEEL_VERTICAL_EXCLUDE_SELECTOR = '.lightbox-metadata';

export function stateLightbox() {
    // TASK-102d-T1：四個獨立累積器（Lightbox 影片 / Lightbox 女優 / 劇照 / 牆翻頁）——
    // 各自閉包狀態，避免不同 UI 分支的冷卻窗互相干擾（見 wheel-nav.js 頂部說明）。
    const wheelNavLightboxVideo = createWheelNav();
    const wheelNavLightboxActress = createWheelNav();
    const wheelNavSampleGallery = createWheelNav();
    const wheelNavPage = createWheelNav();
    // 102d P2b（owner 拍板 2026-07-19）：overlay 垂直滾輪＝上/下一張。獨立軸別累積器
    // （非取代上面三個水平版——同一接線點兩軸各自累積/冷卻，見 wheel-nav.js 頂部說明）。
    // 牆翻頁（wheelNavPage）無垂直版：牆是「垂直捲動有意義」的頁面主體，不吃垂直滾輪。
    const wheelNavLightboxVideoV = createWheelNav({ axis: 'vertical' });
    const wheelNavLightboxActressV = createWheelNav({ axis: 'vertical' });
    const wheelNavSampleGalleryV = createWheelNav({ axis: 'vertical' });

    // 49b T4cd: Picker 動畫參數（T1 fix2 定案，2026-04-25）
    // 供 BurstPicker.playPickerBurst/Float/HoverIn/HoverOut/ExitAll 使用
    // 49c.T5fix.B：viewport bottom anchor 後 burst 距離增加 ~55%，timing 校正定案
    const _PICKER_PARAMS = {
        arcOvershoot: 1.3,    // V2 從 1.4 改 1.3：拉長後 overshoot 視覺強，略降
        arcDuration:  0.75,   // V2 從 0.6 改 0.75：補償距離增加 ~+55%
        floatAmplY:   8,      // Float loop Y 幅度（px）
        floatAmplRot: 2.5,    // Float loop 旋轉幅度（度）
        floatDuration: 1.5,   // Float loop 基礎週期（秒）
        hoverScale:   1.08,   // V2 從 1.12 改 1.08：大卡上不過搶戲
        exitGravity:  1200,   // 其他卡墜落重力（physics2D）
    };

    return {

        // --- Lightbox 狀態初始值 ---
        lightboxOpen: false,
        lightboxIndex: -1,              // 指向 filteredVideos 的索引
        lightboxCloseTimer: null,       // F2: generation-guarded delayed clear timer

        _lightboxAnimating: false,      // B16: Lightbox 動畫進行中 guard
        _lightboxGeneration: 0,         // B19: invalidation token for deferred $nextTick lightbox callbacks

        // Sample Gallery 狀態 (T7)
        sampleGalleryOpen: false,
        sampleGalleryImages: [],
        sampleGalleryIndex: 0,
        _sgTouchStartX: null,
        _lbTouchStartX: null,
        _lbTouchStartY: null,
        _sgAnimating: false,            // C21 guard
        _sgGeneration: 0,               // stale callback 防護

        currentLightboxVideo: null,

        _lbFullLoaded: false,           // 71-T6 blur-up：原圖（cover_full_url）@load 後翻 true → overlay opacity 淡入

        // 100b-T2a（§B-2b）：女優封面 img 快取命中/@load 就緒旗標，平行 _lbFullLoaded（video）。
        // openMask() 的 `if (!this._maskTarget().loaded) return;` 門檻直接消費本欄。lifecycle
        // 契約見 _refreshActressPhotoLoaded()——女優牆與燈箱同 URL，開燈箱時圖幾乎必然已快取，
        // 只靠 @load 會讓 focal 按鈕在最常見路徑上永久打不開（[[feedback_guards_cant_prove_usable]]）。
        _actressPhotoLoaded: false,

        // 100c-T2（CD-5/CD-7）：橫向可拖幅度 ≥ MASK_MIN_DRAG_ROOM（20%）門檻旗標，生命週期
        // 與 _actressPhotoLoaded 完全鏡射（同一對「清空/就緒」helper 同步設值/清除，見下方
        // 兩 helper 定義）。openMask() 的 focal icon x-show 五條件之一：窄圖（無意義的可拖
        // 空間）恆 false，icon 不顯示。
        _actressPhotoWideEnough: false,

        // 99a-T3：焦點裁切遮罩 — 一律 force-detect 預覽 + 左右拖曳微調 + ✓/✗ 提交（Alpine 短狀態，
        // 單一提交生命週期 CD-98b-8 沿用）。98b 的 default⇄auto toggle 已整條移除（見 CHANGELOG）。
        // _maskSession 為單調遞增 session id（98b P2 fix 沿用，Codex）：openMask()/_resetMask() 遞增，
        // confirmMask()/_maskDragStart() 的 pointermove 在 await/事件前捕捉、之後比對，不符即代表
        // 已換片/關燈箱，跳過該次的共用 UI 狀態寫入。
        // 100b-T1：_maskKind 是本 task 唯一新增的 state（CD-4/§B-1b dispatch key）。openMask()
        // 起手第一行凍結一次（'video'|'actress'，依 currentLightboxActress 是否有值），
        // _maskTarget() 內部不得重新判斷（G4：actress/video 各自獨立 state，需在觸發點凍結，
        // 不可逐次重判）。T1 階段 openMask 唯一觸發入口（.lb-mask-btn）只在 video 分支渲染，
        // 故本欄此刻恆解析為 'video'——這正是 T1 DoD ③「女優路徑仍不可達」的結構性保證，
        // 非約定俗成。_resetMask()/_maskTeardown() 收尾時重置（見兩函式末尾，裁決 D-3：
        // 排在最後，防先清 kind 再做依賴 _maskTarget() 的收尾查到錯的分支/元素）。
        _maskKind: null,                // 'video' | 'actress'，dispatch key（100b-T1）
        _maskVisible: false,            // 遮罩 overlay 是否顯示
        _maskSession: 0,                // 單調遞增 session id（openMask/_resetMask 遞增）
        _maskDetecting: false,          // force-detect 進行中（spinner）
        // 101d-T1：影片焦點 icon gate（CD-1/CD-3）。「窄」＝畫面正以 poster（0.71 直式）裁切呈現，
        // 今天＝ ≤899px（grid 小格的 poster-crop 只在 @media (max-width:899px) 套，plan-101d §2.1）。
        // 用 matchMedia 非 innerWidth：裁切由 CSS media query 驅動 → matchMedia 與裁切逐像素同步
        // （innerWidth 在有捲軸時差一個捲軸寬）。門檻 reuse 既有 POSTER_CROP_MAX_W 常數（已被
        // TestPosterCropThresholdAlignment 鎖常數↔CSS），不裸寫 899、不新建常數（CD-1/§6 Non-Goal #13）。
        // reactive：state-base.init() 掛 page-level matchMedia change listener 改此值（同一 Alpine
        // component，mergeState 合併 → 同一屬性）；x-show 讀 _posterModeActive() → 訂閱本 data → 即時翻。
        _isNarrow: (typeof window.matchMedia === 'function')
            ? window.matchMedia('(max-width: ' + POSTER_CROP_MAX_W + 'px)').matches
            : (window.innerWidth <= POSTER_CROP_MAX_W),   // 無 matchMedia 的嵌入環境 → 一次性 fallback
        // 98b-T6：亮窗幾何 reactive data（openMask/drag 同步 imperative 算，非量測-in-binding）。
        // 99a-T5：型別恆為 object（非 string）——headless self-verify 實測抓到：Alpine `:style`
        // 綁 STRING 值時走 `el.setAttribute('style', ...)` 整串覆寫（Alpine 內部 `Xn()`），會把
        // `x-show` 剛設的 inline `display:none` 一併洗掉；`x-show` 本身又會快取「上次算出的布林值」，
        // 布林值沒變就不重跑 show/hide（Alpine 內部 x-show 的 `f===l` 短路），兩者疊加＝窗子在
        // `_maskDetecting` 為真期間仍卡在 `display:block`（baseline flash 不會消失，一路卡到
        // detect resolve）。物件值改走 `el.style.setProperty(key, val)` 逐屬性設值（Alpine 內部
        // `Yn()`），不觸碰 `display`，與 x-show 互不干擾。永遠回傳/賦值 object，不可再退回 string。
        _maskWinStyle: {},
        _maskResizeHandler: null,       // 98b-T6：開遮罩時綁 window resize 重算，teardown/reset 時解
        // 99a-T3：手動焦點編輯狀態。_maskFocalX 恆為具體數字（geometry 已知後）——僅在 openMask
        // 幾何尚未解出的極短暫態為 null（見 openMask 內註解，Opus correction B）。
        _maskFocalX: null,
        // Codex PR#107 第二輪 P2：使用者開遮罩當下觀察到的 cover_path（server 端 DB-key
        // file:/// URI 原樣值，由 /detect-focal 回應帶回，非前端反解/推算）。null＝尚未
        // 從 server 取得任何值（openMask 起手重置、或本次 detect 連 JSON body 都沒拿到，
        // 見 openMask 內 try/catch 註解）——confirmMask 见 null 一律 fail-closed 拒存，
        // 不送 POST，避免用「猜的」cover_path 打穿 compare-and-store 守衛的保護意圖。
        _maskExpectedCoverPath: null,
        _maskDragging: false,           // 拖曳中（停用 CSS transition，跟手不打架，見 showcase.css）
        // 101b-T2（CD-4a/CD-5）：收斂補間進行中旗標——只在 _maskDetecting 翻 false 之後才可能為
        // true（結構上不與 _maskDetecting 重疊，見 _maskStartSettle 步驟④⑤順序）。x-show 驅動
        // .lb-mask-wait-burst/.lb-mask-spinner 延壽 + .lb-mask-window--settling class（CD-5，
        // 停用 CSS transition，防與 GSAP 逐 tick 寫 Alpine :style 雙重 easing）。
        _maskSettling: false,
        _maskDragMoveHandler: null,     // document pointermove listener 參照（成對 add/remove）
        _maskDragUpHandler: null,       // document pointerup/pointercancel listener 參照（成對 add/remove）
        // 99a-T5：detect-first 重新設計——force-detect 先跑完（星空等待動畫佔位），偵測完成
        // （成功或失敗皆算）才揭露可拖曳的 .lb-mask-window（gate 見 openMask/_computeMaskWinStyle
        // 呼叫點與 showcase.html x-show="_maskVisible && !_maskDetecting"）。拖曳入口只在 detect
        // 已 resolve 後才存在，「detect 還沒回來但已經可以拖」的時間窗在結構上不再存在——原本
        // 99a-T3 為了防這個 race 而加的「使用者已手動調整」旗標因此整條移除（不留殭屍旗標；
        // 舊識別字已由 static_guard_lint.mjs forbidden-string 鎖住不得復活）。
        _maskWaitTl: null,              // 99a-T5：星空等待動畫 handle（{tl,burst,stars}），detect
                                         // 期間播放；openMask 啟動，finally/_resetMask/_maskTeardown
                                         // 三處對稱停止（_maskStopWaitAnim helper，idempotent）。
                                         // 101b-T2：正常（收斂）路徑改由 _maskStartSettle 交棒
                                         // （handoffFocalDetectWait，不置 null），fallback 分支
                                         // 仍走 _maskStopWaitAnim 全停清空（CD-4b）。
        _maskSettleTl: null,            // 101b-T2：收斂 GSAP timeline handle（id:'focalSettle'），
                                         // _maskStopSettleAnim（拖曳接管/中斷路徑）與 onComplete/
                                         // onInterrupt（正常結束）對稱清空，見 _maskClearSettleProps。

        _videoChipsExpanded: false,     // 影片 tag chips +N 展開（T4 使用）

        // 49b T4cd: Actress Photo Picker 狀態
        _pickerOpen: false,
        _candidates: [],
        _pickerLoading: false,
        _pickerSelected: false,
        _pickerCurrentSource: null,
        _pickerFloatTweens: [],
        _pickerRunId: 0,
        // 102b T2: 🔄 輪替序號。歸零只在 openActressPicker 首開判別（CD-4），
        // ⛔ 不進 _resetPicker——那也是 🔄 重抓路徑的一環，在 reset 清會抹掉剛 +1 的值。
        _pickerAttempt: 0,
        _pickerSSE: null,
        _pickerBurstFired: false,       // SSE 收齊後一次 burst（防 done/error 重複觸發）
        _pickerReadyAbort: null,        // T3: _burstAllPickerCandidates waitForMount 的 per-run AbortController

        // User Tags 狀態 (T4)
        addingLbTag: false,
        newLbTagValue: '',

        // Enrich 狀態 (T3)
        _enriching: false,

        // --- helper in return {} ---

        // 83a-T1 M1：比例 hook — 縮圖 base img @load 讀 naturalWidth/naturalHeight，
        // 在最近 .lightbox-cover 容器設 --lb-cover-ar custom property。
        // 不寫 inline aspect-ratio；不 removeProperty（換片 / close / similar-open enter/exit 皆不清）。
        // 破圖/空 src（naturalWidth === 0）→ skip，保留前值撐盒（禁止任何清除路徑）。
        // 目標掛點：.lightbox-content（縮圖載入即定，原圖未到也不塌、不閃）。
        _setCoverAspect(e) {
            var img = e && e.target;
            if (!img) return;
            var nw = img.naturalWidth;
            var nh = img.naturalHeight;
            if (!nw || !nh) return;  // 破圖/空 src → skip，保留前值
            var ar = (nw / nh).toFixed(4);
            var containerEl = img.closest('.lightbox-cover');
            if (containerEl) {
                containerEl.style.setProperty('--lb-cover-ar', ar);
            }
        },

        // 71c-P2: helper — blur-up state reset + same-URL complete-check（DRY；供 _setLightboxIndex 與
        // slip-through 路徑（state-similar.js closeSimilarMode）共用，避免兩處邏輯漂移）。
        // 呼叫時機：currentLightboxVideo 已更新、Alpine reactive patch 尚未跑完（$nextTick 前）。
        // $nextTick 後 lightboxCoverFull img.complete && naturalWidth > 0 → 瀏覽器已快取 → 直接翻 true，
        // 跳過 @load 等待；否則等 @load 觸發翻 true。
        _refreshLbFullBlurUp() {
            this._lbFullLoaded = false;
            var self = this;
            this.$nextTick(function () {
                var fullImg = self.$refs && self.$refs.lightboxCoverFull;
                if (fullImg && fullImg.complete && fullImg.naturalWidth > 0) {
                    self._lbFullLoaded = true;
                }
            });
        },

        // 100b-T2a（§B-2b）：女優版 _refreshLbFullBlurUp 平行實作——女優牆與燈箱用同一個
        // /api/actresses/photo/{name} URL，開燈箱時圖幾乎必然已快取（瀏覽器快取命中是常態，
        // 非邊角）。快取圖 .src= 後同步即 complete，@load 不會觸發；只加 @load 會讓
        // openMask() 的 `if (!this._maskTarget().loaded) return;` 在最常見路徑上永久擋下、
        // focal 按鈕點了沒反應且無任何錯誤訊息（[[feedback_guards_cant_prove_usable]] 原型，
        // v0.12.1 全綠但功能不可用）。$refs.pickerCoverImg 在 <template x-if="currentLightboxActress">
        // 內（G3），切走後可能已 undefined，null-safe。identity 凍結（captured）防 await 後
        // 已切走的女優誤寫本次結果。
        // 100c-T2（CD-5）：兩旗標（_actressPhotoLoaded / _actressPhotoWideEnough）的完整生命
        // 週期收成兩個 helper，結構上不可能只寫其中一個——不是「記得兩邊都寫」，是只有一個
        // 地方能寫。呼叫者恰為二：_refreshActressPhotoLoaded() 起手（本檔）、_resetMask()（本檔）。
        // 🔴 _maskTeardown() 絕不可呼叫本 helper（Fix A 病灶：confirm/cancel 收尾不等於「這張
        // 燈箱照片」的生命週期，見 _maskTeardown 內既有註解）。
        _clearActressPhotoState() {
            this._actressPhotoLoaded = false;
            this._actressPhotoWideEnough = false;
        },

        // 100c-T2（CD-5/CD-7）：從已載入的 img 同時算出兩旗標並寫入 this。呼叫者恰為二：
        // showcase.html 的 @load（未快取路徑，$el 即已觸發 load 事件的 img）、
        // _refreshActressPhotoLoaded() 的 $nextTick（已快取路徑，下方）。imgEl 必須是已連接
        // DOM 的元素——detached 元素 getComputedStyle 讀 CSS var 回空字串，parseFloat 得
        // NaN，computeMaskDragRoom 對非有限輸入 fail-closed 回 0（mask-geometry.js），
        // 0 >= MASK_MIN_DRAG_ROOM 為 false，讀不到 ratio 時 _actressPhotoWideEnough 自然
        // 落在 false，不需額外 NaN 特判（CD-7 內建 fail-closed 契約）。
        _readyActressPhotoState(imgEl) {
            const a = imgEl.naturalWidth / imgEl.naturalHeight;
            const r = parseFloat(getComputedStyle(imgEl).getPropertyValue('--actress-crop-ratio'));
            this._actressPhotoLoaded = imgEl.complete && imgEl.naturalWidth > 0;
            this._actressPhotoWideEnough = Number.isFinite(r) && r > 0 && computeMaskDragRoom(a, r) >= MASK_MIN_DRAG_ROOM;
        },

        _refreshActressPhotoLoaded() {
            this._clearActressPhotoState();
            var self = this;
            var captured = this.currentLightboxActress?.name;
            this.$nextTick(function () {
                if (self.currentLightboxActress?.name !== captured) return;
                var img = self.$refs && self.$refs.pickerCoverImg;
                if (img && img.complete && img.naturalWidth > 0) {
                    self._readyActressPhotoState(img);
                }
            });
        },

        // 100c-T2：女優 focal icon 的五條件判斷收成 method，不在 showcase.html 直接寫
        // `x-show="a && b && c && d && e"` 字面 && 鏈。病灶：Alpine 的 effect 依賴收集是
        // 「這次求值實際讀了哪些屬性」，JS `&&` 短路時，一旦前段某條件為 false，後段條件
        // **完全不會被讀取**，Alpine 因此不會訂閱它們的變化——之後那些漏訂閱的旗標翻真時
        // effect 不會重跑，icon 可能卡在錯的顯示狀態。
        // 修法：method 內用獨立陳述式**無條件**讀出全部 5 個旗標存成區域變數，讓 Alpine 的
        // effect 每次呼叫本 method 都保證訂閱到全部依賴，不受 && 短路影響——回傳值仍是同一個
        // && 鏈，語意不變，只是把「讀取」與「短路組合」拆開兩步。showcase.html 仍用 x-show
        // 綁定本 method（與影片版一致）。
        _focalIconVisible() {
            const notEditing = !this._maskVisible;
            const hasPhoto = !!this.currentLightboxActress?.photo_url;
            const loaded = this._actressPhotoLoaded;
            const wideEnough = this._actressPhotoWideEnough;
            const pickerClosed = !this._pickerOpen;
            return notEditing && hasPhoto && loaded && wideEnough && pickerClosed;
        },

        // 101d-T1：影片焦點 icon 顯示 gate（CD-4）。語意旗標 method——只在畫面真的以 poster 裁切
        // 呈現時才顯示 icon（今天＝窄螢幕，讀 reactive _isNarrow）。x-show 以 () 呼叫，理由是比照
        // _focalIconVisible() 慣例／可讀性／未來相容性——**保留括號**。⚠️ 但別把「漏括號」當 runtime
        // bug：Alpine 3 對 x-show **尾端**求值為 function 者會 auto-invoke（101d-T1 CDP 實測），故
        // `A && B && _posterModeActive` 在當前版本其實等效帶括號、非 gate 失效（見 gotchas-frontend
        // 「Alpine methods 必須加 ()」節精確化）。未來「完整/poster 模式」toggle landed 後只改此 body
        // 為 `return this._isNarrow || this._userPosterModeOn`，不動 icon x-show、不動任何呼叫端
        // （plan-101d CD-4，spec §7.2 Non-Goal #14）。
        // 影片 gate 與女優 _focalIconVisible() 的 per-image 門檻刻意不同（影片只 ≤899px 裁、女優牆
        // 全寬度都裁，plan-101d §2.2）——此不對稱是有原則的，勿「對齊」成同一套。
        _posterModeActive() {
            return this._isNarrow;
        },

        // F1: helper — 更新 lightboxIndex + currentLightboxVideo 一致性
        _setLightboxIndex(idx) {
            this.lightboxIndex = idx;
            this.currentLightboxVideo = (idx >= 0 && idx < _filteredVideos.length)
                ? _filteredVideos[idx] : null;
            this.currentLightboxActress = null;   // video setter always clear actress
            this.addingLbTag = false;             // 切換影片時重置輸入框
            this._videoChipsExpanded = false;     // 影片切換時 reset chips 展開
            // BUGfix-mobile-similar-stale-cover P2b: in-grid 切換後清除 standalone 旗標，
            // 確保連點 tier2/3 再 tier1 時 prev/next + fly-back 恢復正常（不殘留 standalone）
            this.similarExitVideo = null;
            // 71c-P2: 抽至 _refreshLbFullBlurUp helper（slip-through 路徑共用）
            this._refreshLbFullBlurUp();
        },

        // --- Lightbox (M3a) ---
        openLightbox(index) {
            // F2: cancel pending delayed clear from previous close
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // B16: 動畫進行中 guard
            if (this._lightboxAnimating) return;
            if (this.lightboxOpen && this.lightboxIndex === index) return;  // 同一張，不動作

            // Fix: lightbox 已開啟時走 switch 路徑
            if (this.lightboxOpen && this.lightboxIndex !== index) {
                var self = this;
                // C18: interrupt — kill 舊 switch timeline（含 onComplete callback）
                _killLightboxTimelines({ killOpen: false, killSwitch: true });
                var oldIndex = this.lightboxIndex;
                var direction = index > oldIndex ? 'next' : 'prev';

                // B19: state-first — 立即更新 state
                this._setLightboxIndex(index);

                // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, direction, {
                            onComplete: function () {
                                self._lightboxAnimating = false;
                            }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            // ★ C17 step 1: ghost fly — 在 state 變更前捕獲 fromRect
            var fromRect = null;
            var coverSrc = null;
            var posterCrop = false;
            if (!this.lightboxOpen) {
                var gridEl = this._getActiveGrid();
                if (gridEl) {
                    var cardEl;
                    if (this.showFavoriteActresses) {
                        var actress = _filteredActresses[index];
                        cardEl = actress
                            ? gridEl.querySelector('[data-flip-id="actress:' + CSS.escape(actress.name) + '"]')
                            : null;
                    } else {
                        var video = _filteredVideos[index];
                        cardEl = video
                            ? gridEl.querySelector('[data-flip-id="' + CSS.escape(video.path) + '"]')
                            : null;
                    }
                    if (cardEl) {
                        var imgEl = cardEl.querySelector('.av-card-preview-img img, .actress-card-photo img');
                        if (imgEl && imgEl.complete && imgEl.getBoundingClientRect().width > 0) {
                            fromRect = imgEl.getBoundingClientRect();
                            coverSrc = imgEl.src;
                            // US5-T7 (CD-75b-12) / US-10 (CD-10)：≤899px 影片卡縮圖走 poster-crop（封面右半正面）。
                            // 非女優模式、非 hero 卡時通知 ghost 對齊裁切 + 落地溶接，
                            // 避免 cover→contain 內容框法切換的硬切 glitch。裁切細節封裝在 ghost-fly.js。
                            // 門檻 POSTER_CROP_MAX_W 對齊 CSS poster-grid / 燈箱貼合斷點（守衛鎖死）。
                            posterCrop = !this.showFavoriteActresses
                                && window.innerWidth <= POSTER_CROP_MAX_W
                                && !cardEl.classList.contains('hero-card');
                        }
                    }
                }
            }

            this._setLightboxIndex(index);
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.add('gsap-animating');
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');

            // B16: GSAP 進場動畫（fire-and-forget）
            var self = this;
            var lbGen = ++this._lightboxGeneration;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                if (!lightboxEl) return;

                if (fromRect && window.GhostFly && window.GhostFly.playGridToLightbox) {
                    self._lightboxAnimating = true;
                    window.GhostFly.playGridToLightbox(fromRect, lightboxEl, {
                        coverSrc: coverSrc,
                        posterCrop: posterCrop,
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen) {
                        window.ShowcaseAnimations.playLightboxOpen(lightboxEl, { skipCover: true });
                    }
                } else {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen
                        ? window.ShowcaseAnimations.playLightboxOpen(lightboxEl, {
                            onComplete: function () { self._lightboxAnimating = false; }
                        })
                        : null;
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        openHeroCardLightbox() {
            if (this._lightboxAnimating) return;
            if (!this._matchedActress) return;
            this._actressChipsExpanded = { aliases: false, info: false };
            // ★ 直接賦值（不走 _setLightboxIndex(-1)）
            this.lightboxIndex = -1;
            this.currentLightboxActress = this._matchedActress;
            this.currentLightboxVideo = null;
            this.addingLbTag = false;
            this._videoChipsExpanded = false;
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.add('gsap-animating');
            this.actressLightboxSource = 'hero';   // T5: hero card 路徑
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');
            // T3: fire-and-forget 即時查 aliases（hero card 路徑無 grid index）
            this._fetchLiveAliases(this._matchedActress?.name, null);
            // 100b-T2a（§B-2b，實作者判斷新增）：hero card 是繞過 _setActressLightboxIndex()
            // 的第三種「actress 變為可見」入口（直接賦值，非經 helper）——若不在此呼叫，快取
            // 命中時 _actressPhotoLoaded 可能殘留上一次瀏覽的值，讓 focal 按鈕在 hero card
            // 路徑上行為不可預期。呼叫本身冪等、無副作用風險。
            this._refreshActressPhotoLoaded();

            // B19: 進場動畫（fire-and-forget，generation-guarded）
            var lbGen = ++this._lightboxGeneration;
            var self = this;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var el = document.querySelector('.showcase-lightbox');
                if (window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen) {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations.playLightboxOpen(el, {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        closeLightbox() {
            // F2: cancel pending delayed clear from previous close / searchFromMetadata
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // 49b T4 fix: 若 picker 開啟中，先關閉 picker
            if (this._pickerOpen) {
                this._closePicker();
            }

            this.addingLbTag = false;    // 關閉 lightbox 時重置 user tag 輸入框
            this._resetMask();           // 98b-T4：關燈箱丟棄未提交遮罩態（不 commit）
            this._fetchSamplesFailed = {};

            // ★ C11: fly-back — 必須在 generation++ / lightboxOpen = false 之前捕獲
            // 56c-fix-v3: standalone similar-exit（similarExitVideo set，lightboxIndex 仍是進 similar mode 前舊值）
            // → closingIndex 設 -1 跳過 fly-back，避免新影片封面飛回舊 alice 卡片
            var isSimilarExitStandalone = !!this.similarExitVideo;
            var closingIndex = isSimilarExitStandalone
                ? -1
                : (this.showFavoriteActresses
                    ? this.actressLightboxIndex
                    : this.lightboxIndex);
            var lbEl = document.querySelector('.showcase-lightbox');
            var lbImg = lbEl ? lbEl.querySelector('.lightbox-cover img') : null;
            var flybackFromRect = lbImg ? lbImg.getBoundingClientRect() : null;
            var flybackCoverSrc = lbImg ? lbImg.src : null;

            // 快照 fly-back 目標的 data-flip-id
            var flybackFlipId = null;
            if (closingIndex >= 0) {
                if (this.showFavoriteActresses) {
                    var actress = _filteredActresses[closingIndex];
                    if (actress) flybackFlipId = 'actress:' + actress.name;
                } else {
                    var video = _filteredVideos[closingIndex];
                    if (video) flybackFlipId = video.path;
                }
            }

            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            // Instant close — kill any in-progress lightbox animations
            _killLightboxTimelines();
            if (lbEl) lbEl.classList.remove('gsap-animating');
            // Phase 50.x cleanup: kill timeline 後 clearProps 確保下次 open 從乾淨狀態起
            if (lbEl && window.OpenAver && window.OpenAver.motion) {
                var _lbContent = lbEl.querySelector('.lightbox-content');
                var _lbCoverImg = lbEl.querySelector('.lightbox-cover img');
                window.OpenAver.motion.clearProps(_lbContent, 'transform,opacity');
                window.OpenAver.motion.clearProps(_lbCoverImg, 'transform,opacity');
            }
            this._lightboxAnimating = false;
            this.lightboxOpen = false;
            this.actressLightboxSource = null;   // T5: reset 進入路徑
            document.body.classList.remove('overflow-hidden');

            // ★ Fly-back — 用快照的 flipId 在整個頁面搜尋
            if (flybackFlipId && flybackFromRect && window.GhostFly && window.GhostFly.playLightboxToGrid) {
                var self = this;
                this.$nextTick(function () {
                    var cardEl = document.querySelector('[data-flip-id="' + CSS.escape(flybackFlipId) + '"]');
                    if (cardEl) {
                        window.GhostFly.playLightboxToGrid(flybackFromRect, cardEl, { coverSrc: flybackCoverSrc, fromImg: lbImg });
                    }
                });
            }

            // 56c-T7：手機路徑 lightbox close 時 reset similarModeMobileOpen，避免下次開 lightbox 殘留展開
            if (typeof this.similarModeMobileOpen !== 'undefined') {
                this.similarModeMobileOpen = false;
            }
            // 83b-T1fix2 (1a)：維持「body.similar-mobile-active class 存在 ⟺ 面板開」不變量。
            // closeLightbox 直接 reset flag（非經 closeMobilePanel）時也清 class，防殘留卡住
            // 後續 [data-picker-ghost] z-index（女優 picker ghost）。class 不存在時 remove 為 no-op。
            document.body.classList.remove('similar-mobile-active');

            // 56c-fix: standalone similar-exit mode — lightbox 關閉時清 similarExitVideo，
            // 回到原 alice 搜尋結果不動（currentLightboxVideo 在 250ms timer 內由 _setLightboxIndex(-1) 清除）
            if (this.similarExitVideo) {
                this.similarExitVideo = null;
            }

            // F2: delay state clearing until CSS transition completes (250ms)
            var self = this;
            var gen = this._lightboxGeneration;  // capture current generation
            this.lightboxCloseTimer = setTimeout(() => {
                if (self._lightboxGeneration === gen && !self.lightboxOpen) {
                    self._setLightboxIndex(-1);
                }
                self.lightboxCloseTimer = null;
            }, 250);
        },

        // ==================== Sample Gallery Methods (T7) ====================

        openSampleGallery(images, startIdx) {
            if (!images || images.length === 0) return;
            this.sampleGalleryImages = images;
            this.sampleGalleryIndex = startIdx || 0;
            this._sgGeneration++;
            this.sampleGalleryOpen = true;
        },

        closeSampleGallery() {
            this.sampleGalleryOpen = false;
            // 不影響 lightboxOpen 狀態（lightbox 維持開啟）
        },

        prevSampleGallery() {
            if (this.sampleGalleryIndex <= 0) return;
            var prevIdx = this.sampleGalleryIndex - 1;
            this._sgGeneration++;
            var gen = this._sgGeneration;
            this.sampleGalleryIndex = prevIdx;
            // C17: state-first，$nextTick 後播動畫
            var self = this;
            this.$nextTick(() => {
                if (self._sgGeneration !== gen) return;
                var imgEl = document.querySelector('.sg-main-img');
                if (imgEl) {
                    window.ShowcaseAnimations?.playSampleGallerySwitch?.(imgEl, 'prev', {});
                }
            });
        },

        nextSampleGallery() {
            if (this.sampleGalleryIndex >= this.sampleGalleryImages.length - 1) return;
            var nextIdx = this.sampleGalleryIndex + 1;
            this._sgGeneration++;
            var gen = this._sgGeneration;
            this.sampleGalleryIndex = nextIdx;
            // C17: state-first，$nextTick 後播動畫
            var self = this;
            this.$nextTick(() => {
                if (self._sgGeneration !== gen) return;
                var imgEl = document.querySelector('.sg-main-img');
                if (imgEl) {
                    window.ShowcaseAnimations?.playSampleGallerySwitch?.(imgEl, 'next', {});
                }
            });
        },

        jumpSampleGallery(idx) {
            if (idx === this.sampleGalleryIndex) return;
            var direction = idx > this.sampleGalleryIndex ? 'next' : 'prev';
            this._sgGeneration++;
            var gen = this._sgGeneration;
            this.sampleGalleryIndex = idx;
            // C17: state-first，$nextTick 後播動畫
            var self = this;
            this.$nextTick(() => {
                if (self._sgGeneration !== gen) return;
                var imgEl = document.querySelector('.sg-main-img');
                if (imgEl) {
                    window.ShowcaseAnimations?.playSampleGallerySwitch?.(imgEl, direction, {});
                }
            });
        },

        _sgTouchStart(e) {
            if (e.touches && e.touches.length > 0) {
                this._sgTouchStartX = e.touches[0].clientX;
            }
        },

        _sgTouchEnd(e) {
            if (this._sgTouchStartX === null) return;
            var endX = e.changedTouches && e.changedTouches.length > 0
                ? e.changedTouches[0].clientX
                : null;
            if (endX === null) { this._sgTouchStartX = null; return; }
            var delta = endX - this._sgTouchStartX;
            this._sgTouchStartX = null;
            if (Math.abs(delta) < 50) return; // swipe threshold
            if (delta < 0) {
                this.nextSampleGallery(); // swipe left → next
            } else {
                this.prevSampleGallery(); // swipe right → prev
            }
        },

        // ==================== End Sample Gallery Methods ====================

        // Metadata 點擊搜尋 (M3f)
        searchFromMetadata(term, type) {
            // F2: cancel pending delayed clear from previous close
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // 同步關閉 lightbox（跳過動畫，後面馬上做 filter 動畫）
            _killLightboxTimelines();
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.remove('gsap-animating');
            this._lightboxAnimating = false;
            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            this.lightboxOpen = false;
            document.body.classList.remove('overflow-hidden');

            // F2: delay state clearing until CSS transition completes (250ms)
            var self = this;
            var gen = this._lightboxGeneration;  // capture current generation
            this.lightboxCloseTimer = setTimeout(() => {
                if (self._lightboxGeneration === gen && !self.lightboxOpen) {
                    self._setLightboxIndex(-1);
                }
                self.lightboxCloseTimer = null;
            }, 250);

            this.search = term;
            this._animateFilter();
            if (type === 'actress') {
                this._checkPreciseActressMatch(term, 'metadata');
            } else {
                this._clearPreciseMatch();
            }
        },

        // 44b-T4: Nav arrow visibility computed
        hasVisiblePrev() {
            // 56c-fix: standalone similar-exit mode — 沒有 list context，暫禁 prev/next
            if (this.similarExitVideo) return false;
            if (this.showFavoriteActresses) return this.actressLightboxIndex > 0;
            if (this.lightboxIndex === -1) return false;
            if (this.lightboxIndex === 0) {
                return this._isPreciseActressMatch && !!this._matchedActress && !!this._matchedActress.is_favorite;
            }
            return this.lightboxIndex > 0;
        },

        hasVisibleNext() {
            // 56c-fix: standalone similar-exit mode — 沒有 list context，暫禁 prev/next
            if (this.similarExitVideo) return false;
            if (this.showFavoriteActresses) return this.actressLightboxIndex < this.filteredActressCount - 1;
            if (this.lightboxIndex === -1) {
                return _filteredVideos.length > 0;
            }
            return this.lightboxIndex < _filteredVideos.length - 1;
        },

        prevLightboxVideo() {
            // C18: interrupt — kill open + switch timeline
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            // 101b-T4: 影片箭頭導覽時若換照片 picker 仍開著（hero-card → picker → 箭頭
            // 這條路徑，見 showcase.html:1091-1108 既有註解），排序讓壞狀態不可能發生——
            // 用 sync 的 _closePicker() 而非 async _cancelPicker()，不製造多一拍等待。
            if (this._pickerOpen) this._closePicker();

            // 44b: -1 sentinel — already at leftmost, do not move
            if (this.lightboxIndex === -1) return;

            // 44b: index 0 + hero card → retreat to -1
            if (this.lightboxIndex === 0 && this._isPreciseActressMatch && this._matchedActress && this._matchedActress.is_favorite) {
                var self = this;
                // B19: state-first
                this.lightboxIndex = -1;
                // 100b-T2a（發現1 橋接點①，裁決2）：video→actress 橋接不經 _setActressLightboxIndex()，
                // 是這裡的直接賦值。x-if="currentLightboxActress" 分支即將由 false 翻 true（重新
                // 掛載），必須在賦值前同步 _resetMask()——姊妹 $watch 是非同步 effect flush，
                // 對掛載那一幀擋不住（gotchas-frontend §8b／T1 CDP 2/2 重現）。
                this._resetMask();
                this.currentLightboxActress = this._matchedActress;
                this.currentLightboxVideo = null;
                this.addingLbTag = false;
                this._videoChipsExpanded = false;
                this._refreshActressPhotoLoaded();   // §B-2b：hero card 橋接同樣是 actress 變為可見的入口

                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'prev', {
                            onComplete: function () { self._lightboxAnimating = false; }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            if (this.lightboxIndex > 0) {
                var self = this;
                var newIdx = this.lightboxIndex - 1;

                // B19: state-first
                this._setLightboxIndex(newIdx);

                // B19: 動畫
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'prev', {
                            onComplete: function () {
                                self._lightboxAnimating = false;
                            }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
            }
        },

        nextLightboxVideo() {
            // C18: interrupt — kill open + switch timeline
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            // 101b-T4: 影片箭頭導覽時若換照片 picker 仍開著（hero-card → picker → 箭頭
            // 這條路徑，見 showcase.html:1091-1108 既有註解），排序讓壞狀態不可能發生——
            // 用 sync 的 _closePicker() 而非 async _cancelPicker()，不製造多一拍等待。
            if (this._pickerOpen) this._closePicker();

            // 44b: from -1 (hero card) → jump to first video
            if (this.lightboxIndex === -1) {
                if (_filteredVideos.length === 0) return;
                var self = this;
                // 100b-T2a（發現1 橋接點②，裁決2）：actress→video 橋接。_setLightboxIndex(0)
                // 內部賦值 currentLightboxVideo + 清 currentLightboxActress=null，讓
                // video 分支 x-if="currentLightboxVideo && !currentLightboxActress" 由 false
                // 翻 true（重新掛載）。同上，reset 必須排在賦值（此呼叫）之前同步執行。
                this._resetMask();
                // B19: state-first
                this._setLightboxIndex(0);

                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'next', {
                            onComplete: function () { self._lightboxAnimating = false; }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            if (this.lightboxIndex < _filteredVideos.length - 1) {
                var self = this;
                var newIdx = this.lightboxIndex + 1;

                // B19: state-first
                this._setLightboxIndex(newIdx);

                // B19: 動畫
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'next', {
                            onComplete: function () {
                                self._lightboxAnimating = false;
                            }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
            }
        },

        // ==================== Lightbox Swipe (81c-T2) ====================
        // 置於 prev/nextLightboxVideo 定義之後：避免本 handler 內的 this.*LightboxVideo()
        // 呼叫點搶在方法定義前出現，誤導以 first-occurrence 定位方法體的既有 sentinel 守衛。

        _lbTouchStart(e) {
            if (e.touches && e.touches.length > 0) {
                this._lbTouchStartX = e.touches[0].clientX;
                this._lbTouchStartY = e.touches[0].clientY;
            }
        },

        _lbTouchEnd(e) {
            if (this._lbTouchStartX === null) return;
            var endX = e.changedTouches && e.changedTouches.length > 0
                ? e.changedTouches[0].clientX
                : null;
            var endY = e.changedTouches && e.changedTouches.length > 0
                ? e.changedTouches[0].clientY
                : null;
            if (endX === null || endY === null) {
                this._lbTouchStartX = null;
                this._lbTouchStartY = null;
                return;
            }
            // CD-5 攔截短路串（比照 handleKeydown 優先序）
            if (this.similarModeOpen || this.similarModeMobileOpen) {
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            if (this.removeActressModalOpen) {
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            if (this._pickerOpen) {
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            if (this.rescrapeOpen) {
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            if (this.deleteVideoModalOpen) {
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            if (this.sampleGalleryOpen) {   // 劇照由 _sgTouchEnd 處理
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            if (!this.lightboxOpen) {        // 燈箱沒開不換片
                this._lbTouchStartX = null; this._lbTouchStartY = null; return;
            }
            var dir = detectSwipe(this._lbTouchStartX, this._lbTouchStartY, endX, endY, 50);
            this._lbTouchStartX = null;
            this._lbTouchStartY = null;
            // CD-3 分流（CD-4 方向）
            if (dir === 'left') {           // 左滑 → 下一
                this.showFavoriteActresses ? this.nextActressLightbox() : this.nextLightboxVideo();
            } else if (dir === 'right') {   // 右滑 → 上一
                this.showFavoriteActresses ? this.prevActressLightbox() : this.prevLightboxVideo();
            }
        },

        /**
         * Known Limitation: Click-Through Detection 技巧
         */
        handleLightboxBackdropClick(e) {
            // 如果點擊的是 lightbox-content 內部，不處理
            if (e.target.closest('.lightbox-content')) return;

            // 暫時隱藏 lightbox 來檢測下方元素
            const lightbox = e.currentTarget;
            lightbox.style.display = 'none';

            // 找到點擊位置下的元素
            const elementBelow = document.elementFromPoint(e.clientX, e.clientY);

            // 恢復 lightbox
            lightbox.style.display = '';

            // 檢查是否是卡片
            const cardEl = elementBelow
                ? (elementBelow.closest('.av-card-preview') || elementBelow.closest('.actress-card'))
                : null;
            if (cardEl) {
                // Click-through: 觸發該卡片的 click（切換到該影片）
                cardEl.click();
            } else {
                // 不是卡片，關閉 lightbox
                this.closeLightbox();
            }
        },

        // ==================== 焦點裁切遮罩 — force-detect + 拖曳 + ✓/✗ (99a-T3) ====================
        // Alpine 短狀態；亮窗滑動用 CSS transition on transform（宣告式，非 GSAP），拖曳中停用
        // （見 showcase.css .lb-mask-window--dragging，跟手不打架）。
        // 生命週期對稱：openMask（遞增 _maskSession，內建 force-detect）↔ confirmMask/cancelMask
        // （經共用 _maskTeardown 收尾）↔ _resetMask（換片 / 關燈箱，遞增 session、丟棄未提交態）。

        // 100b-T1（CD-4/§B-1b）：video/actress 兩分支識別資訊統一出口。_maskKind 已由 openMask()
        // 起手凍結（G4，不在此重判）。actress 分支目前結構性不可達（T1 DoD ③：女優分支無 focal
        // icon，openMask 永不在 currentLightboxActress 有值時觸發），此處仍完整定義兩分支欄位
        // 供 T2 銜接（§B-1b 表）。detectEndpoint/focalEndpoint 各自完整字面 URL（Opus 裁決 C：
        // 不可拼接 base，否則 static_guard_lint.mjs:147 的 detect-focal 規則因字面字串消失而
        // 靜默 RED）。imgEl 對 actress 分支须 null-safe（G3：$refs.pickerCoverImg 在 x-if 內）。
        _maskTarget() {
            if (this._maskKind === 'actress') {
                return {
                    obj: this.currentLightboxActress,
                    imgEl: this.$refs && this.$refs.pickerCoverImg,   // G3：x-if 內，null-safe
                    loaded: this._actressPhotoLoaded,   // T2 才宣告；未宣告的 this.xxx property access 回 undefined，非 ReferenceError
                    identity: this.currentLightboxActress?.name,
                    ratio: '--actress-crop-ratio',
                    detectEndpoint: `/api/actresses/${encodeURIComponent(this.currentLightboxActress?.name || '')}/detect-focal`,
                    focalEndpoint: `/api/actresses/${encodeURIComponent(this.currentLightboxActress?.name || '')}/focal`,
                    focalBody: (focal) => ({ focal }),   // v3：無 token，只此一欄
                    handles409: false,   // spec §3.5：女優無背景 writer、無 409
                };
            }
            return {
                obj: this.currentLightboxVideo,
                imgEl: this.$refs.lightboxCoverFull,
                loaded: this._lbFullLoaded,
                identity: this.currentLightboxVideo?.path,
                ratio: '--poster-crop-ratio',
                detectEndpoint: '/api/showcase/video/detect-focal',
                focalEndpoint: '/api/showcase/video/save-focal',
                focalBody: (focal) => ({
                    path: this.currentLightboxVideo?.path,
                    focal,
                    expected_cover_path: this._maskExpectedCoverPath,
                }),
                handles409: true,   // 封面已變更時的 compare-and-store 409
            };
        },

        async openMask() {
            if (this._maskVisible) return;   // 98b-T6：re-entry guard——按鈕在遮罩開啟時仍可見，
                                             // 再點不重複裝 resize listener。
            // 100b-T1（CD-4/§B-1b，G4）：凍結 kind，_maskTarget() 內部不得重判。
            // 🔴 位置是承重的，必須夾在 re-entry guard 之後、第一個 _maskTarget() 消費者之前：
            //   • 排 re-entry guard「之前」→ 遮罩已開時再次進入會覆寫 in-flight session 的 kind，
            //     才 return——「凍結」語意當場破功（T1 恆 'video' 故無影響，但 T2 女優可達後，
            //     kind 被改成別的分支會讓後續 _maskDragStart 抓到錯的 $refs 元素）。
            //   • 排 `_maskTarget().identity` 之後 → helper 讀到未凍結的 kind，dispatch 到錯分支。
            // 用排序讓該類 race 結構上不可能發生，而非事後補旗標（feedback_order_over_flag_guards）。
            // T1 階段唯一觸發入口（.lb-mask-btn）只在 video 分支渲染，故此刻恆為 'video'。
            this._maskKind = this.currentLightboxActress ? 'actress' : 'video';
            if (!this._maskTarget().identity) return;
            // 98b-T6 防线：圖未就緒不開（按鈕也 gate _lbFullLoaded，此為 defense-in-depth）。
            if (!this._maskTarget().loaded) return;

            // 99a-T3：_maskFocalX 暫時設 null（幾何尚未解出的極短暫態，見 state 宣告處註解）。
            // _computeMaskWinStyle 讀到 null 即貼右裁基準（D2）——99a-T5：此值只作為「detect
            // 失敗/無臉」時的終值 fallback，不會先畫出來再滑走（.lb-mask-window 在 _maskDetecting
            // 為真時不渲染，見 showcase.html x-show）。
            this._maskFocalX = null;
            // Codex PR#107 第二輪 P2：新 session 起手先清舊 token，防止「這次 detect 連
            // JSON body 都沒拿到」時沿用上一支影片/上一個 session 殘留的 cover_path
            // 誤配到這支影片（confirmMask 的 fail-closed 判斷才有意義）。
            this._maskExpectedCoverPath = null;

            // 初始焦點基準在此一次性解出並凍結，_computeMaskWinStyle()/pointermove 內不得
            // 重判。el/rect/r 的讀取與 _computeMaskWinStyle 內部刻意重複（Opus correction B
            // 既有註解：ratio 讀取受 static guard 錨定在 _computeMaskWinStyle 本體內，不可
            // 抽成共用 helper）。
            const gEl = this._maskTarget().imgEl;
            if (!gEl || !gEl.naturalWidth) {
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }
            const gRect = gEl.getBoundingClientRect();
            if (!gRect.width || !gRect.height) {
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }
            const gR = parseFloat(getComputedStyle(gEl).getPropertyValue(this._maskTarget().ratio));
            if (!Number.isFinite(gR) || gR <= 0) {
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }
            if (this._maskKind === 'actress') {
                // spec §3.4/§3.7-6：女優基準恆 3/4 置中（非右裁）。
                this._maskFocalX = 0.5;
            } else {
                // Opus correction B：幾何一旦解出，_maskFocalX 收斂為具體數字（右裁基準 x），
                // 不留 null 終態；`s` 成功即代表 el/rect/r 皆已驗證合法，這裡不需再驗一次。
                const winW = Math.min(gRect.width, gRect.height * gR);
                this._maskFocalX = (gRect.width - winW / 2) / gRect.width;
            }

            const s = this._computeMaskWinStyle();
            if (!s) {
                // 幾何算不出（rect=0 / naturalWidth=0 / ratio CSS var 讀不到 → NaN）→ 不開、
                // 不留「全灰無窗」死態，toast 提示。兩個 ratio var（--poster-crop-ratio /
                // --actress-crop-ratio）皆已定義於 theme.css :root，此處為防禦性 fallback。
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }

            this._maskSession++;         // 98b P2 fix：新開 session，讓任何舊 session 的 await 後寫入失效
            this._maskDetecting = false; // 98b P2 fix(二)：清舊 session 遺留的偵測態——舊 detect await 的
                                         // finally 因 session 不符會**跳過**清 spinner，若不在此重置，新遮罩
                                         // 會頂著卡死的 spinner（Codex）。新 session 起手一律非偵測中。
            this._maskWinStyle = s;      // 先設幾何（右裁基準，detect resolve 前 / 無臉時的 fallback 終值）

            // D1（CD-1）：一律 force-detect，僅預覽、不寫 DB。偵測完成後若有臉，_maskFocalX 更新為
            // 偵測 x；無臉則維持右裁基準不變。99a-T5：.lb-mask-window 在 _maskDetecting 為真時不
            // 渲染（showcase.html x-show="_maskVisible && !_maskDetecting"），故偵測完成翻 false
            // 那一刻起才第一次畫出來，畫出來就已是終值——不再有「先貼右裁基準再滑到偵測位置」的
            // 過渡態，拖曳入口（@pointerdown）在 detect 完成前也不存在，Bug 1 的 race 結構性消失。
            const session = this._maskSession;
            // 101b-T2（CD-4a/CD-8）：try 之外宣告，finally 讀得到。不可從 _maskFocalX 反推
            // （無臉時 _maskFocalX 停在起手基準，與 pigo 真的回同值的基準無法區分——女優基準
            // 恆 0.5，pigo 也可能回 0.5；video 基準是右裁算式，pigo 也可能剛好回同值）。
            let sawFace = false;
            const targetVideo = this._maskTarget().obj;   // 100b-T1：identity 統一走 helper（video 分支＝currentLightboxVideo）
            // 100b-T2a：actress 分支 targetVideo = currentLightboxActress（無 .path）——下方
            // fetch body 的 `targetVideo.path` 對 actress 恆 undefined，JSON.stringify 會直接
            // drop 該 key（body 變 {}）。女優 detect-focal 端點簽名為
            // `async def detect_actress_focal(name: str)`（web/routers/actress.py:950），無
            // request body model，name 全靠 URL path segment（detectEndpoint 已含編碼後的
            // name），送空 body 不影響行為，故此處沿用 T1 既有寫法、不需 kind-aware 分流。
            // 99a-T5（headless self-verify 實測抓到，非理論推測）：_maskDetecting 必須先翻 true，
            // 才能設 _maskVisible=true——Alpine 的 x-show reactive effect 對每次同步賦值都立即
            // 重新求值（非批次到下個 microtask 才跑），若順序顛倒（先 _maskVisible=true，
            // _maskDetecting 還停在上面剛重置的 false），x-show="_maskVisible && !_maskDetecting"
            // 會在兩行賦值之間的中繼態被評估為 true，短暫畫出「貼右裁基準」的窗（baseline
            // flash），違反本卡「畫出來就已是終值」的核心承諾。實測：START-525 這支影片 100%
            // 重現（baseline 144.30px ≠ 最終偵測值 0px，flash 全程持續到 detect resolve 為止）。
            this._maskDetecting = true;
            this._maskVisible = true;    // 再顯示 overlay（此刻 _maskDetecting 已是 true，無空窗閃）
            // 開啟期間 window resize 重算（開時綁、teardown/reset 時解，lifecycle 對稱）。
            // 99a-T5：`|| this._maskWinStyle` fallback——_computeMaskWinStyle 失敗時回傳 null，
            // 不可讓 null 流進 :style 綁定（見 _maskWinStyle 宣告處註解），保留前一次的合法幾何。
            this._maskResizeHandler = () => {
                if (this._maskVisible) this._maskWinStyle = this._computeMaskWinStyle() || this._maskWinStyle;
            };
            window.addEventListener('resize', this._maskResizeHandler);

            // 99a-T5：星空等待動畫（detect 期間佔位）。單一入口——只在這裡啟動；停止見下方
            // finally（正常結束）與 _resetMask/_maskTeardown（中斷路徑），_maskStopWaitAnim 對稱。
            // C23 per-callsite PRM guard（比照 state-similar.js isPRM pattern）：PRM 為真時整段
            // 跳過 GSAP，唯一等待指示回退成 .lb-mask-spinner（純 CSS animation，PRM blanket 規則
            // 保證仍渲染不轉，不留死白）。
            const isPRM = !!(window.OpenAver && window.OpenAver.prefersReducedMotion);
            if (!isPRM) {
                const coverEl = this._maskTarget().imgEl?.closest('.lightbox-cover');
                if (coverEl && window.GhostFly && window.GhostFly.playFocalDetectWait) {
                    this._maskWaitTl = window.GhostFly.playFocalDetectWait(coverEl);
                }
            }

            try {
                const resp = await fetch(this._maskTarget().detectEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: targetVideo.path }),
                });
                // Codex PR#107 第二輪 P2：先嘗試解 body 拿 cover_path，不管 resp.ok——
                // server 在成功偵測與「找到 row 但封面檔缺失」兩個分支都帶 cover_path
                // （見 web/routers/showcase.py detect_video_focal），拖到下面 !resp.ok
                // 才 throw 會漏接後者。真正的網路層失敗（fetch reject / body 非 JSON）
                // 才會讓 data 維持 null，此時 _maskExpectedCoverPath 停在 openMask 起手
                // 清空的 null，confirmMask 見 null 一律 fail-closed 拒存（不可用猜的值）。
                let data = null;
                try { data = await resp.json(); } catch (_jsonErr) { data = null; }
                if (data && typeof data.cover_path === 'string' && session === this._maskSession) {
                    this._maskExpectedCoverPath = data.cover_path;
                }
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                if (!data || !data.success) throw new Error((data && data.error) || 'API failed');
                if (session === this._maskSession) {
                    const parsed = parseFocal(data.auto_focal);   // '' / 畸形 → null，維持起手基準
                    if (parsed) {
                        // 女優基準恆 3/4 置中（spec §3.4）：僅更新 X 焦點，Y 分量已無讀寫點
                        // （恆 0.5000，見 CD-11／confirmMask 硬編 ,0.5000）。
                        sawFace = true;   // 101b-T2（CD-8）：找到臉，_maskStartSettle 據此掛收斂 tween
                        this._maskFocalX = parsed.x;
                        // 101b-T2（CD-4a）：這行原本在此重算終值——現整行移除，終值改由收斂
                        // timeline 的 t=1 端點產生（computeMaskSettleGeometry），由構造保證
                        // 「首次可見幀＝全幅」不被本行的終值寫入破壞。
                    }
                    // else：無臉——維持起手基準（video：右裁 x；actress：3/4 置中 0.5，
                    // openMask 起手已算好），不動它。逃生口仍可拖曳 + ✓ 存入（spec §3.7-6）。
                }
            } catch (e) {
                // 偵測失敗只 toast，_maskFocalX 維持右裁基準，不讓 UI 卡在半套態。
                if (session === this._maskSession) {
                    this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                }
            } finally {
                // session guard 同時包住 _maskDetecting 與停星空動畫：若這期間已被 _resetMask
                // 中斷（換片/關燈箱），_resetMask 早已呼叫過 _maskStopWaitAnim 並清空
                // this._maskWaitTl；此處若不 session-gate，會誤殺「新 session 剛啟動的星空」
                // （見本 task 的「等待期間快速連續開關」邊界案例）。
                // 101b-T2（CD-4a/CD-4b）：原本這裡直呼 _maskDetecting=false + _maskStopWaitAnim()
                // ——那是「硬切」本體，本 Part 要消滅的正是這個。改呼叫 _maskStartSettle(sawFace)，
                // 由它接手決定全幅預寫→_maskDetecting 解禁→交棒星空→掛收斂 timeline 的完整順序
                // （或 g0/canAnimate 不成立時走 fallback 原路）。finally 是 timeline 的起跑點，
                // 不是收尾點——_maskStopSettleAnim() 刻意不放在這裡（§A-5）。
                if (session === this._maskSession) {
                    this._maskStartSettle(sawFace);
                }
            }
        },

        // 拖曳起手（pointerdown，同步非 async）：drag-start 當下一次性讀取 W/H/winW，全程不在
        // pointermove 內呼叫 getBoundingClientRect（效能 + 98b-T6 量測-in-binding gotcha 同型陷阱）。
        _maskDragStart(evt) {
            if (!this._maskVisible) return;
            // 再入防線（自查補強）：拖曳進行中若再來一個 pointerdown（如觸控第二指落在窗上），
            // 直接忽略——否則會覆寫 _maskDragMoveHandler/_maskDragUpHandler 參考，讓第一組
            // document listener 永遠移不掉（洩漏 + 並發 stale 寫入）。
            if (this._maskDragging) return;
            // 101b-T2（CD-10）：收斂補間進行中被拖曳接管——kill 收斂 tween 讓使用者的手勝出
            // （比照 killTweensOf「最新的勝出」慣例）。插入點在兩個 early-return 之後、第一次
            // 取樣之前，不放首行（放首行會在早退情境誤 kill）。
            this._maskStopSettleAnim();
            const el = this._maskTarget().imgEl;   // 100b-T1：G3 null-safe（x-if 內 $refs 可能 undefined）
            if (!el || !el.naturalWidth) return;
            const rect = el.getBoundingClientRect();
            const W = rect.width;
            const H = rect.height;
            if (!W || !H) return;
            const r = parseFloat(getComputedStyle(el).getPropertyValue(this._maskTarget().ratio));
            if (!Number.isFinite(r) || r <= 0) return;
            const winW = Math.min(W, H * r);
            const startClientX = evt.clientX;
            // 101b-T2 P2（Codex PR review）：拖曳接管「收斂中」的窗——_maskStopSettleAnim() 已 kill
            // timeline，但 _maskFocalX 仍是偵測終值，而視覺上的窗還停在收斂中的**中間**幾何（settle
            // onUpdate 每 tick 寫 _maskWinStyle 的內插值：中間寬度 + 中間中心 focal_t）。若直接用終值
            // 算 startLeft，首次 pointermove 會把窗從當前可見中心瞬跳到終值中心（X snap）。修法：交棒
            // 當下把 _maskFocalX 同步成「當前可見窗的中心焦點」（從 _maskWinStyle 反解），讓終寬窗以
            // **當前中心**落定——中心不跳、只有寬度收到終值（WYSIWYG 必需：存的裁窗恆為終比例），
            // 再從那裡跟手。非收斂態時可見窗中心本就 == _maskFocalX（同一 computeMaskWinGeometry
            // writer），此步為 no-op。解析失敗（_maskWinStyle 尚未成幾何）→ 保留 _maskFocalX（防禦）。
            const curWin = this._maskWinStyle;
            if (curWin && typeof curWin.width === 'string' && typeof curWin.transform === 'string') {
                const curWinW = parseFloat(curWin.width);
                const curLeftMatch = /translateX\(\s*(-?[\d.]+)px\s*\)/.exec(curWin.transform);
                const curLeft = curLeftMatch ? parseFloat(curLeftMatch[1]) : NaN;
                if (Number.isFinite(curWinW) && Number.isFinite(curLeft)) {
                    this._maskFocalX = (curLeft + curWinW / 2) / W;
                }
            }
            // 101b P2（Codex PR#110 二審）：交棒當下立刻把窗重算成「終比例窗、以當前中心落定」，
            // 不等 onMove。否則「收斂中按下→未拖曳即放開（tap／aborted drag）」時 _maskWinStyle 仍卡在
            // _maskStopSettleAnim 凍結的中間寬度，比 confirmMask 會存的終窗更寬 → WYSIWYG 破。與 onMove
            // 同一 writer（computeMaskWinGeometry），第一次 pointermove 再算一次亦一致；非收斂態 no-op。
            this._maskWinStyle = computeMaskWinGeometry(W, H, r, this._maskFocalX);
            // 起手左緣必須與「視覺上看到的窗位置」一致＝比照 _computeMaskWinStyle 一樣 clamp
            // （99a Gemini P2）。raw _maskFocalX 貼邊時未鉗的 start 值會落在邊界外，窗子停在
            // 邊界但拖曳從界外起算 → 反向拖曳有死區、不跟手。clampMaskWinLeft 是數學軸無關的純量
            // clamp（B-4：只改 JSDoc 參數名，不改實作），(left,W,winW) 傳法完全正確。
            const startLeft = clampMaskWinLeft(
                (this._maskFocalX !== null && this._maskFocalX !== undefined)
                    ? this._maskFocalX * W - winW / 2
                    : W - winW,
                W,
                winW,
            );
            const session = this._maskSession;   // 拖曳中途換片/關燈箱防線（雙保險，見下）

            this._maskDragging = true;

            const onMove = (e) => {
                // 防禦性早退：正常路徑 _resetMask 已同步移除本 listener，此處只防「移除時序」邊界。
                if (session !== this._maskSession) return;
                e.preventDefault();
                const dx = e.clientX - startClientX;
                const left = clampMaskWinLeft(startLeft + dx, W, winW);   // clamp 進封面邊界
                this._maskFocalX = (left + winW / 2) / W;
                // 99a-T5：恆 object——委派 computeMaskWinGeometry（同 _computeMaskWinStyle 的
                // writer 來源，見 _maskWinStyle 宣告處註解與 shared/mask-geometry.js 開頭說明）。
                this._maskWinStyle = computeMaskWinGeometry(W, H, r, this._maskFocalX);
            };
            const onUp = () => {
                if (session === this._maskSession) this._maskDragging = false;
                this._maskRemoveDragListeners();
            };
            this._maskDragMoveHandler = onMove;
            this._maskDragUpHandler = onUp;
            document.addEventListener('pointermove', onMove, { passive: false });
            document.addEventListener('pointerup', onUp);
            document.addEventListener('pointercancel', onUp);
            evt.preventDefault();
        },

        // 成對移除 document 上的拖曳 listener：pointerup/pointercancel 正常路徑會自呼叫；
        // _maskTeardown/_resetMask 異常路徑（拖曳中途換片/關燈箱、確認/取消）兜底，防洩漏。
        _maskRemoveDragListeners() {
            if (this._maskDragMoveHandler) {
                document.removeEventListener('pointermove', this._maskDragMoveHandler);
                this._maskDragMoveHandler = null;
            }
            if (this._maskDragUpHandler) {
                document.removeEventListener('pointerup', this._maskDragUpHandler);
                document.removeEventListener('pointercancel', this._maskDragUpHandler);
                this._maskDragUpHandler = null;
            }
        },

        // ✓ 確認：存手動焦點 → POST /video/save-focal，同參考 mutate targetVideo（lightbox + grid 即時對臉）。
        async confirmMask() {
            // _maskFocalX null 只應發生在極短暫態（geometry 尚未解出）；openMask 一旦幾何解出即收斂
            // 為具體值（correction B），此處 null-guard 純防禦（幾何失敗 / identity 遺失等異常態才會觸發）。
            if (this._maskFocalX === null || this._maskFocalX === undefined || !this._maskTarget().identity) {
                this._maskTeardown();
                return;
            }
            // 100b-T2a（§B-1b）：token guard 只在 handles409（video）成立時檢查——女優無 token、
            // 無 409（v3 契約），不得因缺 token 被 fail-closed 擋下。await 前捕獲：_maskKind 若
            // 因中途換片被 _resetMask 清空，_maskTarget() 之後會 dispatch 回預設（video）分支，
            // 捕獲值才能忠實反映「這次送出的到底是哪個 kind 的請求」。
            const handlesToken = this._maskTarget().handles409;
            // Codex PR#107 第二輪 P2 fail-closed guard（video-only）：從未拿到 server 端
            // cover_path token（openMask 的 /detect-focal 連 JSON body 都沒解析成功，例如
            // 純網路層失敗）→ 拒絕送出，不可用猜的 cover_path 打穿 compare-and-store 守衛的
            // 保護意圖（寧可這次存不進、逼使用者重開遮罩，也不可能誤配錯封面）。
            if (handlesToken && (this._maskExpectedCoverPath === null || this._maskExpectedCoverPath === undefined)) {
                this.showToast(window.t('showcase.lightbox.mask_save_failed'), 'error');
                this._maskTeardown();
                return;
            }
            const session = this._maskSession;
            const targetObj = this._maskTarget().obj;   // 捕獲：await 期間可能已換片/切走
            // Codex 本地 review 修正（Fix B）：與 targetObj 同時捕獲 kind——本函式下方所有對
            // 「這次送出的到底是哪個 kind」的判斷（含下面組 focal 字串、下方 _syncActressesArray
            // 的 gate）一律讀這個捕獲值，不讀 this._maskKind 即時值。換片路徑
            // （nextActressLightbox → _setActressLightboxIndex → _resetMask）會把 this._maskKind
            // 清空，若 await 之後才判斷即時值，使用者在存檔 request resolve 前切走女優就會讓判斷
            // 誤判成 video 分支、跳過牆格同步。
            const kind = this._maskKind;
            // Y 分量恆 0.5000（video 恆右裁 X 定基準，render 只用 X，spec §3.3；actress 恆
            // 3/4 置中，Y 軸讀寫已移除，見 CD-11）。
            const focal = `${this._maskFocalX.toFixed(4)},0.5000`;
            try {
                const resp = await fetch(this._maskTarget().focalEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    // Codex PR#107 第二輪 P2：video 分支原樣帶回 openMask 期間 server 給的
                    // cover_path，讓 update_manual_focal 的 compare-and-store 守衛比對「使用者
                    // 觀察當下」與「存檔當下」的封面是否一致，擋掉 rescan/rescrape 換封面的
                    // race；actress 分支只送 {focal}（v3：無 token，_maskTarget().focalBody 內
                    // 已 dispatch，此處統一呼叫不裸組 body）。
                    body: JSON.stringify(this._maskTarget().focalBody(focal)),
                });
                const data = await resp.json().catch(() => null);
                if (handlesToken && resp.status === 409) {
                    // 封面已變更（compare-and-store 守衛擋下）：與一般失敗分開給更明確的提示。
                    // actress 無此分支（handlesToken=false，v3 無 409，spec §3.5）。
                    if (session === this._maskSession) {
                        this.showToast(window.t('showcase.lightbox.mask_cover_changed'), 'error');
                    }
                    return;
                }
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                if (!data || !data.success) throw new Error((data && data.error) || 'API failed');
                // 燈箱主圖：video 走 T2 既有 applyCellFocal $watch 接手；actress 直接寫
                // targetObj（= 這次送出時捕獲的 currentLightboxActress，await 前已凍結）。
                targetObj.auto_focal = data.auto_focal;
                targetObj.crop_mode = 'manual';
                // 100b-T4（Opus 審核裁決 1，CDP 實測背書）：牆上小格側寫入。
                // 🔴 上面兩行原本的舊註解主張「actress 分支的 targetObj 與 paginatedActresses[idx]
                // 恆為同一物件參考、改一邊即改兩邊」——這個前提已被推翻，此處曾經是全函式唯一的
                // 缺口：`_fetchLiveAliases`（state-actress.js:791-793）
                // 在 alias fetch resolve 時，若該女優 alias 端點回 200（21 位中 3 位），會執行
                // `currentLightboxActress = Object.assign({}, currentLightboxActress, {aliases})`
                // ——把 currentLightboxActress 換成脫鉤副本、不寫回 paginatedActresses。此時只寫
                // 上面的 targetObj 只改到脫鉤副本，牆上小格永遠停在存檔前的裁法（必須重載才會
                // 更新，違反 spec §3.4「✓ 存入後焦點立即生效」）。alias 回 404 的 18 位因前提
                // 僥倖成立而正常 ⇒ 資料相依的間歇失敗，抽測/CDP 抽樣都可能整批放行。詳見
                // plan-100b.md 的 CD-10 訂正框。
                // 與 _uploadActressPhoto／_onPickerSelect 對稱：改資料一律 by-name 呼叫
                // _syncActressesArray；用 targetObj.name（await 前捕獲值）而非
                // this.currentLightboxActress?.name，防使用者在 await 期間切走女優時寫錯格。
                // gate 在 kind 為 'actress' 時才做：video 分支 targetObj 是 currentLightboxVideo，
                // 沒有 paginatedActresses 可查（那是 paginatedVideos），video/actress 是正交的
                // 兩條資料，不可讓這段在 video 分支被誤觸發。
                // Codex 本地 review 修正（Fix B）：gate 讀上方捕獲的 kind（await 前凍結值），不讀
                // this._maskKind 的即時值——切走 → _resetMask 清掉 kind 欄位 → 若讀即時值會誤判
                // 成 video 分支而跳過本次同步，牆格停在存檔前的裁法。與 _onPickerSelect／
                // _uploadActressPhoto 一致：改資料（by captured name）無條件做，只有「改當前畫面」
                // 才需要 gate 在使用者還留在原處。
                if (kind === 'actress') {
                    this._syncActressesArray(targetObj.name, { auto_focal: data.auto_focal, crop_mode: 'manual' });
                }
            } catch (e) {
                if (session === this._maskSession) {
                    this.showToast(window.t('showcase.lightbox.mask_save_failed'), 'error');   // 沿用既有 key
                }
            } finally {
                if (session === this._maskSession) this._maskTeardown();
            }
        },

        // ✗ 取消：純同步收尾，不寫 DB——force-detect 本就沒寫，✗ 天然無殘留（CD-2）。
        cancelMask() {
            this._maskTeardown();
        },

        // confirmMask/cancelMask 共用收尾：收 overlay + 解 resize listener + 解拖曳 listener。
        _maskTeardown() {
            this._maskVisible = false;
            this._maskDragging = false;
            if (this._maskResizeHandler) {
                window.removeEventListener('resize', this._maskResizeHandler);
                this._maskResizeHandler = null;
            }
            this._maskRemoveDragListeners();   // 防禦性：理論上 pointerup 已先清，這裡再保險一次。
            // 99a-T5：防禦性再保險——理論上 confirmMask/cancelMask 觸發時 detect 早已 resolve
            // （✓/✗ 只在 _maskDetecting===false 才可見/可點），星空動畫應該已由 openMask 的
            // finally 停過；比照上面 _maskRemoveDragListeners 的「再保險一次」寫法補一次 kill。
            this._maskStopWaitAnim();
            // 101b-T2（§A-5）：收斂補間對稱再保險——理論上 ✓/✗ 觸發時收斂早已播完，比照上面
            // 「再保險一次」寫法補一次 kill（idempotent，收斂已結束時安全 no-op）。
            this._maskStopSettleAnim();
            // Codex 本地 review 修正（Fix A）：本函式刻意**不**在此清女優圖已載入旗標。
            // 該旗標的生命週期屬於「燈箱這張照片」（writer 只有 @load handler +
            // _refreshActressPhotoLoaded() 的 4 個呼叫點），不屬於「這次遮罩編輯 session」。
            // confirmMask/cancelMask 收尾走到本函式之後，沒有任何路徑會把它重新判定回真值
            // ——URL 未變的已載入 img 不會重觸發 @load——在此清掉會讓 showcase.html 的
            // focal 按鈕 x-show 判斷永久失效（confirm/cancel 各一次即消失），直到關燈箱重開
            // 或切換女優才恢復。真正該清（且會被重新判定）的收尾路徑是換片/關燈箱的
            // _resetMask()（下方）——其後必經 _setActressLightboxIndex 呼叫
            // _refreshActressPhotoLoaded() 重新判定，兩者語意不同，不可為了對稱一併刪除。
            // 100b-T1（裁決 D-3）：kind 收尾排最後——本函式內以上收尾皆不依賴 _maskTarget()（皆
            // 直接操作 handler/listener 參考），故順序本身不影響現有行為；仍照裁決排最後，
            // 避免未來新增依賴 _maskTarget() 的收尾時誤踩「先清 kind 查到錯元素」。
            this._maskKind = null;
        },

        // 換片 / 關燈箱：丟棄未提交態（不 commit，不把前片焦點帶到下一片）。
        _resetMask() {
            // 98b P2 fix：換片/關燈箱一律使舊 session 失效（即使當下沒開新遮罩），
            // 讓仍在途的舊 await 回應之後必被 session gate 擋下，不依賴 _maskVisible 的
            // x-show 巢狀結構作為唯一防線（defense-in-depth，同時涵蓋「切 B 但沒開 B 遮罩」）。
            this._maskSession++;
            this._maskDetecting = false; // 98b P2 fix(二)：invalidate 時清偵測態，防舊 detect 的 spinner 漏進下個 session（Codex）
            this._maskVisible = false;
            this._maskWinStyle = {};     // 98b-T6：清窗幾何避免殘留閃（下次 open 同步重算覆蓋）。
                                          // 99a-T5：恆 object，不可退回 '' string（見宣告處註解）。
            this._maskFocalX = null;     // 99a-T3：清 component-state 焦點，防下一片沿用上一片的拖曳結果
            this._maskExpectedCoverPath = null;   // Codex PR#107 P2：防下一片沿用上一片的 cover token
            this._maskDragging = false;  // 99a-T3：防拖曳中途換片，dragging class 卡死在 true
            this._maskRemoveDragListeners();   // 99a-T3：拖曳中途換片/關燈箱兜底，移除 document listener
            this._maskStopWaitAnim();    // 99a-T5：detect 期間中斷（換片/關燈箱/ESC）對稱停星空動畫，
                                          // 防「舊 session 星空還在跑、新 session 又疊一份」
            this._maskStopSettleAnim();  // 101b-T2（§A-5）：收斂期間中斷（換片/關燈箱/ESC）對稱停止，
                                          // 防「舊 session 收斂還在跑、新 session 又疊一份」
            if (this._maskResizeHandler) {
                window.removeEventListener('resize', this._maskResizeHandler);
                this._maskResizeHandler = null;
            }
            // 100c-T2（CD-5）：兩旗標同步清除收斂進 helper，語意不變（換片/關燈箱必須清，
            // 之後必經 _refreshActressPhotoLoaded() 重新判定）。
            this._clearActressPhotoState();
            // 100b-T1（裁決 D-3）：kind 收尾排最後，理由同 _maskTeardown。
            this._maskKind = null;
        },

        // 99a-T5：星空等待動畫對稱停止 helper——openMask finally（正常結束，session-gated）、
        // _resetMask（中斷：換片/關燈箱/ESC）、_maskTeardown（防禦性再保險）三處對稱呼叫。
        // idempotent：this._maskWaitTl 已 null 時安全 no-op（GhostFly.stopFocalDetectWait 內部
        // 亦對 null handle 安全 no-op，belt-and-suspenders）。
        _maskStopWaitAnim() {
            if (this._maskWaitTl && window.GhostFly && window.GhostFly.stopFocalDetectWait) {
                window.GhostFly.stopFocalDetectWait(this._maskWaitTl);
            }
            this._maskWaitTl = null;
        },

        // 101b-T2（CD-4a/CD-4b/CD-4c/CD-5/CD-7/CD-8/CD-9/CD-11a，§A-3a 權威步驟表）：由 openMask
        // finally 呼叫（已 session-gated），取代舊有的「_maskDetecting=false + _maskStopWaitAnim()」
        // 硬切。決定「偵測完成 → 星空淡出 → 亮窗收斂到終值」是否以單一 GSAP timeline overlap 播放，
        // 或退化成今天的瞬現路徑（g0 為 null / PRM / 動畫層不可用）。
        //
        // hasFace：CD-8——找到臉才掛第 4 條 proxy tween（收斂），無臉/偵測失敗仍走同一條 timeline
        // （星空/spinner 淡出＋窗淡入），只是窗停在起手基準不收斂。
        _maskStartSettle(hasFace) {
            // ① 取樣一次（比照 _maskDragStart 首次取樣，刻意不逐 tick 量測）。coverEl 是
            // openMask 內 `if (!isPRM)` block 的區域變數，離開該 block 即不可見，此處需自己重取。
            const el = this._maskTarget().imgEl;
            const coverEl = el?.closest('.lightbox-cover');
            let W, H, r;
            if (el && el.naturalWidth) {
                const rect = el.getBoundingClientRect();
                W = rect.width;
                H = rect.height;
                r = parseFloat(getComputedStyle(el).getPropertyValue(
                    this._maskKind === 'actress' ? '--actress-crop-ratio' : '--poster-crop-ratio'
                ));
            }

            // ② gate（CD-11a fail-closed 幾何 + CD-4c 動畫層可用性，同一個 fallback 分支）。
            const g0 = computeMaskSettleGeometry(W, H, r, this._maskFocalX, 0);
            const isPRM = !!(window.OpenAver && window.OpenAver.prefersReducedMotion);
            // 🔴 Codex PR review P2 修正：canAnimate 必須連 gate `this._maskWaitTl`——
            // wait handle 是 :1386 handoffFocalDetectWait(this._maskWaitTl) 交棒的前提，
            // 缺它（burst/star DOM 不在場，即使 gsap 存在）_maskWaitTl 恆為 null，
            // handoffFocalDetectWait(null) 回 null，解構 `{ stars, burst }` 會拋
            // TypeError，此時 _maskSettling 已設 true 卻無 cleanup，卡死 spinner/遮罩。
            // gate 掉後走既有 fallback 分支（瞬現、_maskStopWaitAnim 對 null 安全 no-op），
            // 不是 belt-and-suspenders 式 null-safe 解構——單一決策點，結構上不可能再拿到 null。
            const canAnimate = !isPRM
                && typeof gsap !== 'undefined'
                && window.GhostFly && typeof window.GhostFly.handoffFocalDetectWait === 'function'
                && this._maskWaitTl;
            if (!g0 || !canAnimate) {
                // 既有 :1043 原路——不得用已知無效的 W/H/r 重算終值（那組值已知不合法，
                // computeMaskSettleGeometry 才會回 null）；合法 fallback 恆存在（openMask
                // pre-flight 已擋掉不合法幾何，_maskWinStyle 此刻必為合法值）。
                this._maskWinStyle = this._computeMaskWinStyle() || this._maskWinStyle;
                this._maskStopWaitAnim();   // CD-4b：不呼叫 → repeat:-1 loop 整條洩漏
                this._maskDetecting = false;
                return;
            }

            // ③ 全幅，同步寫在 x-show 翻真之前（CD-4a 核心不變式）——但這只是 hasFace（收斂）
            // 路徑的起點約定：no-face 沒有步驟⑥掛收斂 tween，寫「全幅」給它既非「起點」也非
            // spec §4.2 要求的「終點」（基準）。101b-T5：hasFace 分支一字不動（g0），!hasFace
            // 直接落基準幾何（與既有 PRM fallback 分支 :1380 呼叫同一個 _computeMaskWinStyle()）
            // ——CD-8「找到／沒找到的差別＝收斂 vs 不收斂，只此一項」的直接編碼。
            this._maskWinStyle = hasFace ? g0 : (this._computeMaskWinStyle() || this._maskWinStyle);
            // ④ 必須晚於 ② 的 gate（CD-4c：早於它＝動畫層不可用時永久卡 true）。
            this._maskSettling = true;
            // ⑤ x-show 此刻才放行；首次 paint 讀到步驟③寫入的值——hasFace＝全幅（g0，收斂起點）、
            //    no-face＝基準（右裁/置中，直接落定不收斂，spec §4.2）。
            this._maskDetecting = false;

            // ⑥ 交棒星空（CD-4b，不 clearProps）+ 建立單一 timeline（overlap 由 timeline 保證）。
            const { stars, burst } = window.GhostFly.handoffFocalDetectWait(this._maskWaitTl);
            const win = coverEl?.querySelector('.lb-mask-window');
            const spinner = coverEl?.querySelector('.lb-mask-spinner');
            const cleanup = () => this._maskClearSettleProps();
            // 101b-T2 / Codex PR#110 P2-2：GSAP 編排移入 GhostFly（shared/，不被 pages 守衛掃描，
            // 已是 focal 動畫家族的家）。tween 結構／ease／duration 一字不動，此處只注入
            // onConverge（每 tick 寫收斂中間幾何）與 onDone（收尾）兩個副作用。
            const tl = window.GhostFly.buildFocalSettleTimeline({
                stars, spinner, win, hasFace,
                onConverge: (t) => { this._maskWinStyle = computeMaskSettleGeometry(W, H, r, this._maskFocalX, t) || this._maskWinStyle; },
                onDone: cleanup,
            });
            this._maskSettleTl = tl;
        },

        // 101b-T2（§A-5）：收斂 tween 對稱停止 helper，逐字比照 _maskStopWaitAnim 的形狀
        // （idempotent、單一 helper、多處對稱呼叫）。呼叫點：_maskDragStart（CD-10 拖曳接管）、
        // _maskTeardown／_resetMask（中斷路徑再保險）。openMask finally 刻意不呼叫——那是
        // timeline 的起跑點，kill 等於自殺。
        _maskStopSettleAnim() {
            if (this._maskSettleTl && typeof this._maskSettleTl.kill === 'function') this._maskSettleTl.kill();
            // 顯式呼叫，不依賴 kill() 觸發 onInterrupt（ghost-fly.js 既有註解：GSAP 3 .kill()
            // 不保證 fire onInterrupt）。_maskClearSettleProps 本身冪等，onInterrupt 若仍另外
            // 觸發一次亦安全。
            this._maskClearSettleProps();
        },

        // 101b-T2（CD-9a）：settle timeline 的 onComplete/onInterrupt 共用收尾（比照
        // ghost-fly.js clearLanding「一個 closure、兩路徑共用」先例）。單一清理真理，供
        // _maskStopSettleAnim 與 timeline 自身收尾兩處呼叫，必須冪等（clearProps 對已無 inline
        // style 的元素是 no-op；clearFocalDetectWait 對 null handle 亦 no-op）。
        _maskClearSettleProps() {
            if (window.GhostFly && window.GhostFly.clearFocalDetectWait) {
                window.GhostFly.clearFocalDetectWait(this._maskWaitTl);   // 星空 clearProps 延到此刻
            }
            const el = this._maskTarget().imgEl;
            const coverEl = el?.closest('.lightbox-cover');
            if (coverEl && window.GhostFly?.clearFocalSettleProps) {
                // 101b-T2 (CD-9a) / Codex PR#110 P2-2：clearProps 移入 GhostFly（DOM lookup 仍在此）。
                const win = coverEl.querySelector('.lb-mask-window');
                const spinner = coverEl.querySelector('.lb-mask-spinner');
                window.GhostFly.clearFocalSettleProps({ win, spinner });
            }
            this._maskWaitTl = null;
            this._maskSettleTl = null;
            this._maskSettling = false;   // burst/spinner 此刻才被 x-show 收掉（兩者已 opacity 0）
        },

        // 亮窗幾何：讀 CSS var --poster-crop-ratio（非硬編）+ _maskFocalX 解焦點 x（component state，
        // 非 video.auto_focal——編輯態顯示真實落點，不套 focalObjectPosition 的 deadzone）。
        // 回傳 inline style OBJECT（width/height + transform translateX）供 template :style 綁定
        // （99a-T5：不可回傳 string，見 _maskWinStyle 宣告處註解——string 值會被 Alpine `:style`
        // 整串覆寫 style attribute，洗掉 x-show 設的 display:none）。失敗（rect=0 / ratio 讀不到）
        // 回傳 null，呼叫端（openMask）以 `if (!s)` 判斷；resize handler 呼叫端已知 null 會 fallback
        // 保留前值（見 openMask 內 _maskResizeHandler 定義）。
        // 亮窗以外由 CSS box-shadow spotlight 壓暗；transform 變化時 CSS transition 左右滑動（拖曳中停用，見 showcase.css）。
        // 98b-T6：純 compute（原 _maskWindowStyle 邏輯不變），由 openMask/drag/resize imperative 呼叫。
        // 100b-T2a（§B-3）：el 改走 _maskTarget().imgEl（G3 null-safe，dispatch 兩分支）；
        // 窗幾何建構（winW/winH）委派 computeMaskWinGeometry（shared/mask-geometry.js，
        // 可測試性 + G1 收斂單一 writer 來源，見該檔開頭說明）——ratio 讀取仍留在本函式體內
        // （裁決3，見下）。
        _computeMaskWinStyle() {
            const el = this._maskTarget().imgEl;
            // C17/#10：圖 render 前 rect=0 → 不畫（naturalWidth 未就緒）
            if (!el || !el.naturalWidth) return null;
            const rect = el.getBoundingClientRect();
            const W = rect.width;
            const H = rect.height;
            if (!W || !H) return null;
            // 100b-T2a（裁決3）：兩個字面 CSS var 名保留在本函式體內、不委派 _maskTarget().ratio——
            // static_guard_lint.mjs 有 4 條 scope-anchor 規則錨定本函式本體（getComputedStyle
            // required／--poster-crop-ratio required／兩條硬編比例常數 forbidden）。改成
            // getComputedStyle(el).getPropertyValue(this._maskTarget().ratio) 會讓
            // --poster-crop-ratio 字面字串離開此函式 scope，required 規則靜默 RED（T5-② 才是
            // 調整這 4 條 scope rule 的正式責任 task，T2 不搶做）。三元式是刻意重複，不可「清理」
            // 成委派寫法。
            const r = parseFloat(getComputedStyle(el).getPropertyValue(
                this._maskKind === 'actress' ? '--actress-crop-ratio' : '--poster-crop-ratio'
            ));
            if (!Number.isFinite(r) || r <= 0) return null;
            return computeMaskWinGeometry(W, H, r, this._maskFocalX);
        },

        // ==================== User Tags in Lightbox (T4) ====================

        // 展開 inline 輸入框並 focus
        showAddLbTagInput() {
            this.addingLbTag = true;
            this.newLbTagValue = '';
            this.$nextTick(() => this.$refs.lbTagInput?.focus());
        },

        // 確認新增 tag — 呼叫 POST /api/user-tags
        async confirmAddLbTag() {
            const tag = (this.newLbTagValue || '').trim();
            if (!tag) {
                this.addingLbTag = false;
                return;
            }
            if (!this.currentLightboxVideo?.path) {
                this.addingLbTag = false;
                return;
            }
            const existingTags = this.currentLightboxVideo.user_tags || [];
            if (existingTags.includes(tag)) {
                // 重複 tag，靜默忽略
                this.addingLbTag = false;
                this.newLbTagValue = '';
                return;
            }
            try {
                const resp = await fetch('/api/user-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: this.currentLightboxVideo.path,
                        add: [tag],
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success) {
                    this.currentLightboxVideo.user_tags = data.user_tags;
                } else {
                    throw new Error(data.error || 'API failed');
                }
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.tag_api_failed'), 'error');
            } finally {
                this.addingLbTag = false;
                this.newLbTagValue = '';
            }
        },

        // 取消輸入框
        cancelAddLbTag() {
            this.addingLbTag = false;
            this.newLbTagValue = '';
        },

        // 刪除 user tag — 呼叫 POST /api/user-tags {remove: [tag]}
        async removeLbUserTag(tag) {
            if (!this.currentLightboxVideo?.path) return;
            try {
                const resp = await fetch('/api/user-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: this.currentLightboxVideo.path,
                        remove: [tag],
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success) {
                    this.currentLightboxVideo.user_tags = data.user_tags;
                } else {
                    throw new Error(data.error || 'API failed');
                }
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.tag_api_failed'), 'error');
            }
        },

        // --- Enrich 補資料 (T3) ---
        async enrichVideo(video) {
            if (this._enriching) return;
            if (!video || !video.path) return;
            this._enriching = true;
            try {
                const mode = !video.has_cover ? 'refresh_full' : 'fill_missing';
                const resp = await fetch('/api/enrich-single', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: video.path,
                        number: video.number,
                        mode: mode,
                        write_nfo: true,
                        write_cover: true,
                        overwrite_existing: false,
                    }),
                });
                const result = await resp.json();
                if (result.success) {
                    await this.refreshVideoData(video);
                    this.showToast(window.t('showcase.enrich.success'), 'success');
                } else {
                    this.showToast(result.error || window.t('showcase.enrich.failed'), 'error');
                }
            } catch (e) {
                this.showToast(window.t('showcase.enrich.failed'), 'error');
            } finally {
                this._enriching = false;
            }
        },

        async fetchSamples(video) {
            if (!video || !video.path || !video.number) return;
            this._fetchSamplesLoading = true;
            try {
                const res = await fetch('/api/scraper/fetch-samples', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: video.path, number: video.number })
                });
                const data = await res.json();
                if (data.success) {
                    await this.refreshVideoData(video);
                    this.showToast(window.t('showcase.samples.success'), 'success');
                } else if (data.error === 'multi_video_folder') {
                    this.showToast(window.t('showcase.samples.multi_video_error'), 'warn');
                } else {
                    this.showToast(window.t('showcase.samples.fetch_failed'), 'error');
                    this._fetchSamplesFailed[video.path] = true;
                }
            } catch (e) {
                this.showToast(window.t('showcase.samples.fetch_failed'), 'error');
                this._fetchSamplesFailed[video.path] = true;
            } finally {
                this._fetchSamplesLoading = false;
            }
        },

        async refreshVideoData(video) {
            try {
                const resp = await fetch(`/api/showcase/video?path=${encodeURIComponent(video.path)}`);
                if (!resp.ok) return;
                const data = await resp.json();
                if (data.success && data.video) {
                    // BUGfix-lightbox-cover-stale: 共用同一個 timestamp，確保 grid 與 lightbox overlay 同步 bust。
                    const _t = Date.now();
                    if (data.video.cover_url) {
                        data.video.cover_url = data.video.cover_url + '&t=' + _t;
                    }
                    // cover_full_url 恆為 /api/gallery/image（max-age=86400），URL 不變瀏覽器吃舊快取。
                    // 同步追加 &t= cache-bust，確保 lightbox overlay（.lb-full）顯示新封面。
                    if (data.video.cover_full_url) {
                        data.video.cover_full_url = data.video.cover_full_url + '&t=' + _t;
                    }
                    // 67-A2/CD-67-3b: data.video 不帶 _imgLoaded → 舊 true 殘留會讓新封面跳過 skeleton/fade。
                    // Object.assign 前 reset，讓補封面/重抓的新 cover_url（含上面 &t= cache-bust）重走 skeleton→@load→淡入。
                    if (data.video.cover_url) video._imgLoaded = false;
                    Object.assign(video, data.video);
                    // BUGfix-lightbox-cover-stale: 若燈箱正開在這支影片，重置 blur-up overlay，
                    // 讓 cover_full_url（已 bust）重新觸發 @load → _lbFullLoaded 淡入。
                    // 用 === video 守住：燈箱開在別支影片時不誤 reset。
                    // 必須在 Object.assign 之後呼叫（src 已更新，$nextTick complete-check 才讀到新 URL）。
                    if (this.currentLightboxVideo === video) {
                        this._refreshLbFullBlurUp();
                    }
                }
            } catch (e) {
                // refresh 失敗不顯示額外 toast
            }
        },

        // --- 49b T4cd: Actress Photo Picker methods ---
        /**
         * 開啟候選卡 picker — async，遞增 runId，啟動 SSE，淡出 metadata
         * 若已開且按 🔄：reset + 重抓
         */
        async openActressPicker() {
            const name = this.currentLightboxActress?.name;
            if (!name) return;

            // 100b Codex P2-3 fix：_pickerSelected===true 代表換候選／上傳照片正在等 fetch
            // resolve（CD-8 承重前提：_pickerOpen 全程恆 true，見 _uploadActressPhoto #4 註解）。
            // 此時真正可達的入口是 .picker-refresh-btn（showcase.html :picker-refresh-btn，
            // 原本只用 :disabled="_pickerLoading" 擋，未含 _pickerSelected——burst 完成後
            // loading=false 但 selected=true 的視窗內仍可點；CDP 實測 2026-07-16 重現：點擊後
            // _resetPicker() 把正在等待中的 fetch 變孤兒 callback，與新一輪 SSE 競爭改寫
            // _pickerOpen/_candidates，原 fetch resolve 時的 _closePicker() 會把使用者剛開的
            // 新 picker session 一併關掉）。guard 放在此處（函式唯一入口）覆蓋兩個既有
            // callsite，沿用既有互斥鎖慣例（_onPickerHoverIn／_onPickerHoverOut／
            // _onPickerSelect 皆同款 early-return，裁決 5）。
            if (this._pickerSelected) return;

            // 102b T2 (CD-4)：🔴 必須在 _resetPicker()（下方會把 _pickerOpen 翻 false）
            // 之前讀 _pickerOpen 判別首開/重抓——換女優必經關→開，歸零由結構保證。
            if (this._pickerOpen) { this._pickerAttempt++; }   // 🔄 重抓（同一 picker session）
            else { this._pickerAttempt = 0; }                  // 首開（含換女優後首開）→ 主名重來

            // Tear down any in-flight SSE before starting a new one
            if (this._pickerSSE) { this._pickerSSE.close(); this._pickerSSE = null; }

            if (this._pickerOpen) {
                this._resetPicker();
            }

            this._pickerOpen = true;
            this._pickerLoading = true;
            this._pickerCurrentSource = this.currentLightboxActress?.photo_source || null;

            // metadata 淡出（Row 1 actress-lb-header 保留）
            this._fadeMetadataPanel(true);

            this._pickerRunId++;
            const runId = this._pickerRunId;

            this._startPickerSSE(name, runId);
        },

        /**
         * SSE 收齊後一次 burst 全部候選卡
         */
        async _burstAllPickerCandidates(runId) {
            if (this._pickerRunId !== runId) return;
            if (this._pickerBurstFired) return;     // 防 done/timeout/error 重複觸發
            this._pickerBurstFired = true;          // dedup latch 維持在等待前（位置不動）
            // Codex PR#111 一審 P2：0 候選（改名女優主名 0 命中的典型情境）也要落 latch，
            // 否則 🔄（x-show="_pickerBurstFired"，showcase.html:1064）永遠不出現，
            // 用戶卡死在 attempt 0 無法換別名重抓。_pickerLoading 已在呼叫端（done/onerror
            // handler）設為 false，此處不需重複處理。
            if (this._candidates.length === 0) return;

            // T3（CD-3/CD-3a）：waitForMount 等候選卡 mount 取代 $nextTick。predicate 用
            // expected（burst 時 _candidates 已定，SSE 已 close 不再增）非硬編；observer root =
            // 恆掛載的 pickerGrid（overlay x-show）。ready===false 只來自 abort（_resetPicker /
            // close / 換 run）→ 靜默 bail；不做任何 timeout give-up（observer 承擔 late-mount）。
            const expected = this._candidates.length;
            const grid = this.$refs.pickerGrid;
            const { ready } = await waitForMount(
                grid,
                () => (grid?.querySelectorAll('.picker-candidate-card').length || 0) >= expected,
                { signal: this._pickerReadyAbort?.signal },
            );
            if (!ready) return;
            if (this._pickerRunId !== runId) return;

            const coverEl = this.$refs.pickerCoverImg;
            if (!grid || !coverEl || typeof window.BurstPicker === 'undefined') return;

            const cards = Array.from(grid.querySelectorAll('.picker-candidate-card'));
            if (!cards.length) return;

            grid.style.setProperty('--picker-cols', cards.length);

            window.BurstPicker.playPickerBurst(cards, coverEl, _PICKER_PARAMS, {
                streamMode: 'stagger',
                streamInterval: 80,
                floatTimerSink: this._pickerFloatTweens,
                runId: runId,
                getRunId: () => this._pickerRunId
            });
        },

        /**
         * 啟動 EventSource，處理 candidate / done / error 事件
         *
         * 不設 no-event timeout：本地影片在 UNC / 網路磁碟時，ffmpeg crop 之間的 gap 可能
         * 超過數秒，誤殺會讓用戶只看到雲端那張。連線中斷由 EventSource onerror 兜底。
         */
        _startPickerSSE(name, runId) {
            // 102b T2 (CD-5)：0 不帶參數（首開 URL 與 0.12.3 逐位一致）；
            // 顯式 > 0 而非 truthiness（0 是合法值，gotchas「|| 吞 numeric 0」）
            const url = `/api/actresses/${encodeURIComponent(name)}/photo-candidates`
                + (this._pickerAttempt > 0 ? `?attempt=${this._pickerAttempt}` : '');
            const sse = new EventSource(url);
            this._pickerSSE = sse;
            this._pickerBurstFired = false;
            // T3: per-run readiness abort（_resetPicker / close / 換 run 時 abort → observer disconnect）
            this._pickerReadyAbort?.abort();
            this._pickerReadyAbort = new AbortController();

            sse.addEventListener('candidate', (e) => {
                if (this._pickerRunId !== runId) { sse.close(); return; }
                try {
                    const candidate = JSON.parse(e.data);
                    this._candidates = [...this._candidates, candidate];
                } catch (err) {
                    console.warn('[Picker] Failed to parse candidate:', err);
                }
            });

            sse.addEventListener('done', () => {
                if (this._pickerRunId !== runId) return;
                sse.close();
                this._pickerSSE = null;
                this._pickerLoading = false;
                this._burstAllPickerCandidates(runId);
            });

            sse.onerror = () => {
                if (this._pickerRunId !== runId) return;
                sse.close();
                this._pickerLoading = false;
                if (this._candidates.length === 0) {
                    this._closePicker();
                    if (typeof this.showToast === 'function') {
                        this.showToast(window.t('showcase.actress.picker.error'), 'error');
                    }
                } else {
                    // 已收到部分候選，仍 burst 給用戶選
                    this._burstAllPickerCandidates(runId);
                }
            };
        },

        /**
         * Hover in：放大 + glow（settled 後才生效）
         */
        _onPickerHoverIn(el, i) {
            if (this._pickerSelected) return;
            if (!el || el.dataset.pickerSettled !== '1') return;
            if (typeof window.BurstPicker !== 'undefined') {
                window.BurstPicker.playPickerHoverIn(el, _PICKER_PARAMS);
            }
        },

        /**
         * Hover out：縮回原始尺寸 → 等待縮回完成後 restart float
         */
        async _onPickerHoverOut(el, i) {
            if (this._pickerSelected) return;
            if (typeof window.BurstPicker === 'undefined') return;
            const targetEl = el;
            await window.BurstPicker.playPickerHoverOut(targetEl, _PICKER_PARAMS);
            // Stale-check
            if (this._pickerSelected || !this._pickerOpen) return;
            if (!targetEl.isConnected) return;
            const tl = window.BurstPicker.playPickerFloat(targetEl, _PICKER_PARAMS);
            if (tl) this._pickerFloatTweens.push(tl);
        },

        /**
         * 選中卡片 — T4e 完整流程
         */
        async _onPickerSelect(candidate, i) {
            // AC-13 race lock：第一次 click 鎖定，其餘忽略
            if (this._pickerSelected) return;
            this._pickerSelected = true;

            const capturedName = this.currentLightboxActress?.name;
            if (!capturedName) {
                this._pickerSelected = false;
                return;
            }

            // DOM 節點解析：必須在 await 前取得
            const grid = this.$refs.pickerGrid;
            const allCards = grid ? Array.from(grid.querySelectorAll('.picker-candidate-card')) : [];
            const selectedCard = allCards[i] || null;
            const otherCards = allCards.filter((_, j) => j !== i);
            const coverImg = this.$refs.pickerCoverImg;

            // Reduced-motion 偵測
            const reduceMotion = (typeof window.matchMedia === 'function' &&
                                  window.matchMedia('(prefers-reduced-motion: reduce)').matches);

            try {
                const body = {
                    source: candidate.source,
                    url: candidate.full_url,
                    video_path: candidate.video_path || null,
                    crop_spec: 'v1',
                };
                const resp = await fetch(`/api/actresses/${encodeURIComponent(capturedName)}/photo`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!resp.ok) throw new Error('replace_failed_' + resp.status);
                const data = await resp.json();

                // Stale check：await 期間用戶切換了 lightbox actress
                if (!this.currentLightboxActress || this.currentLightboxActress.name !== capturedName) {
                    this._syncActressesArray(capturedName, data);
                    this._pickerSelected = false;
                    return;
                }

                this._syncActressesArray(capturedName, data);
                if (this.currentLightboxActress && this.currentLightboxActress.name === capturedName) {
                    this.currentLightboxActress.photo_url = data.photo_url;
                    this.currentLightboxActress.photo_source = data.photo_source;
                }

                // 100b-T2b（§B-2b 第四呼叫點，Opus 2026-07-16 裁決）：換候選成功換 URL 後
                // 亦須刷新 _actressPhotoLoaded——photo_url 一變就要重新等載入，與上傳同形
                // （同一個 lifecycle 契約的另一個入口）。
                // 🔴 gate：本行受上方 :1673-1677 的 stale early-return 保護（「已切走 → 同步完
                // 資料就 return」），與 _uploadActressPhoto 的 #6 下半是同一個機制——1670 的
                // await 之後到此處無任何 await，故執行到這裡即保證「仍是同一位女優」。依
                // §B-1f #6 判別法：本函式碰的是當前畫面（$refs.pickerCoverImg），屬「改當前
                // 畫面 ⇒ 要 gate」，不可挪到 early-return 之上變成無條件執行。
                // 位置在兩條成功子路徑（reduce-motion 直接關 / 完整動畫）之前，兩者共用；
                // 此刻 photo_url 已 mutate 完 → Alpine 已排程 :src patch → helper 內的
                // $nextTick 讀到的是新 URL（不依賴下方 imperative 的 coverImg.src 賦值）。
                this._refreshActressPhotoLoaded();

                // Reduced-motion 或 BurstPicker 未載入 → 直接更新 src + 關閉
                if (reduceMotion || typeof window.BurstPicker === 'undefined') {
                    if (coverImg && data.photo_url) {
                        coverImg.src = data.photo_url;
                    }
                    this._closePicker();
                    this.showToast(window.t('showcase.actress.picker.replaced'), 'success');
                    return;
                }

                // 完整動畫：FlipReplace（await）→ src 同步至 backend persistent URL → ExitAll
                try {
                    if (selectedCard && coverImg) {
                        await window.BurstPicker.playPickerFlipReplace(selectedCard, coverImg, _PICKER_PARAMS);
                        if (data.photo_url) {
                            coverImg.src = data.photo_url;
                        }
                    } else if (coverImg && data.photo_url) {
                        coverImg.src = data.photo_url;
                    }
                    if (otherCards.length > 0) {
                        await window.BurstPicker.playPickerExitAll(otherCards, _PICKER_PARAMS);
                    }
                } catch (animErr) {
                    console.warn('[Picker] animation error', animErr);
                    if (coverImg && data.photo_url) coverImg.src = data.photo_url;
                }

                this._closePicker();
                this.showToast(window.t('showcase.actress.picker.replaced'), 'success');

            } catch (e) {
                this._pickerSelected = false;  // 失敗時解除鎖定
                this._closePicker();
                this.showToast(window.t('showcase.actress.picker.error'), 'error');
            }
        },

        /**
         * Helper: by-name 同步 `paginatedActresses[idx]`（100b-T4 擴四欄）。
         * ⚠️ docstring 更正（CD-10）：舊版寫「同步 `_actresses` 陣列」是錯的——`_actresses`/
         * `_filteredActresses` 是 `state-base.js:24-25` 的 module-level 純陣列、非 Alpine
         * reactive prop，寫它們不會觸發任何重算（絕不可去「同步」那兩個）。本函式改的一律是
         * `this.paginatedActresses[idx]`（reactive）。
         * 四欄邏輯已抽至 `shared/actress-sync.js`（node:test 可測，見 __tests__/
         * sync-actress-fields.test.mjs；本檔用 `@/showcase/...` importmap alias，plain Node
         * 無法直接 import，同 mask-geometry.js 先例）。呼叫契約不變：三個呼叫點
         * （confirmMask／_uploadActressPhoto／_onPickerSelect）皆 by-name 傳入部分欄位。
         */
        _syncActressesArray(name, data) {
            syncActressFields(this.paginatedActresses, name, data);
        },

        /**
         * 100b-T2b（§B-1f，spec §2 故事 1／§3.1）：上傳女優自己的照片，直接變主圖
         * （唯一入口，全程不跑偵測——spec §3.7-7「零偵測成本」by-construction：本函式
         * 不呼叫任何 detect-focal 端點；全程不碰 `_candidates`，故上傳的圖不進候選列，
         * spec §3.7-1 同樣 by-construction）。
         *
         * 互斥鎖沿用既有 `_pickerSelected`（CD-8，不發明新機制）——:disabled 綁定／
         * G2 boolean coercion 是 T4 的 DoD（picker 內兩入口互斥 UI 側），本函式只需
         * 正確接上同一個 flag。
         *
         * 六個必踩點（§B-1f）：
         * #1 evt.target.value = '' 排在 await 之前——同一檔案連選兩次 change 不會
         *    再觸發，await 後 evt.target 可能已被拆掉。
         * #2 fetch 帶 FormData 絕不手動設 Content-Type（會蓋掉 boundary → 後端一律 415）。
         * #3 失敗時 picker 不關、只解鎖——🔴 刻意與既有候選換圖的 catch（_onPickerSelect）
         *    分歧（後者呼叫 _closePicker()），spec §3.1+§C 明訂失敗要留在 picker 顯示 toast。
         * #4 成功才關 picker，且關在 _syncActressesArray 之後（CD-8 承重前提：_pickerOpen
         *    在 resolve 前恆 true，本函式不主動關，_cancelPicker() 既有 guard 已擋住
         *    Esc／outside-click）。
         * #5 capturedName 在 await 前凍結（比照全檔既有 captured* 慣例）。
         * #6 stale-success 兩層拆：_syncActressesArray（改資料）無條件執行（by captured
         *    name，與當前 lightbox 是誰無關）；currentLightboxActress 兩欄顯式同步／
         *    _refreshActressPhotoLoaded／關 picker／成功 toast（改當前畫面）僅在仍是同一位
         *    女優時執行。
         *    ⚠️ 「currentLightboxActress 顯式同步是冗餘」的舊說法已作廢（CD-10 前提被
         *    _fetchLiveAliases 的 Object.assign 打破，CDP 實測證實）——理由見函式內註解。
         */
        async _uploadActressPhoto(evt) {
            const file = evt.target.files?.[0];
            if (!file) return;             // 使用者取消 → 什麼都不做
            evt.target.value = '';         // #1：必須在 await 之前，見上方註解

            if (this._pickerSelected) return;
            this._pickerSelected = true;

            const capturedName = this.currentLightboxActress?.name;   // #5：identity 凍結
            if (!capturedName) {
                this._pickerSelected = false;
                return;
            }

            const fd = new FormData();
            fd.append('file', file);

            try {
                const resp = await fetch(`/api/actresses/${encodeURIComponent(capturedName)}/photo/upload`, {
                    method: 'POST',
                    body: fd,   // #2：不可自設 Content-Type，見上方註解
                });

                if (!resp.ok) {
                    // CD-9：依 HTTP status 分流，不依 body code（無 409）。413/415 共用桶
                    // 見 HANDOFF status 分流表，其餘（400/404/500）統一走 upload_failed。
                    let key = 'showcase.actress.picker.upload_failed';
                    if (resp.status === 413) key = 'showcase.actress.picker.upload_too_large';
                    else if (resp.status === 415) key = 'showcase.actress.picker.upload_bad_format';
                    this.showToast(window.t(key), 'error');
                    this._pickerSelected = false;   // #3：失敗時只解鎖，不關 picker
                    return;
                }

                const data = await resp.json();

                // #6 上半：改資料，無條件執行（by-name 定位，與當前 lightbox 是誰無關）
                this._syncActressesArray(capturedName, data);

                if (!this.currentLightboxActress || this.currentLightboxActress.name !== capturedName) {
                    // 已切走：牆上已同步完畢，不碰當前這位（B），僅解鎖
                    this._pickerSelected = false;
                    return;
                }

                // #6 下半：改當前畫面，僅在仍是同一位女優時執行（gate ＝上方 early-return）

                // 🔴 這不是冗餘同步，是承重的——沒有它，燈箱主圖不會換（CDP 2026-07-16 實測）。
                // Why：`_syncActressesArray` 改的是 `paginatedActresses[idx]`（by-name 定位陣列
                // 元素）。CD-10 原本主張「它與 currentLightboxActress 是同一個物件、改一邊即改
                // 兩邊」，但 `_fetchLiveAliases`（state-actress.js:791）在 alias fetch resolve 後
                // 執行 `currentLightboxActress = Object.assign({}, currentLightboxActress, {aliases})`
                // ——把 currentLightboxActress 換成**脫鉤的新副本**且不寫回陣列。CDP 實測該同一性
                // 在開燈箱後 **+17ms** 就翻 false（與 aliases 落地同一幀）⇒ 該前提實務上恆不成立。
                // 此後 `_syncActressesArray` 只碰得到牆上小格，碰不到燈箱主圖：實測 alias 回 200
                // 的女優（21 位中 3 位）上傳後「牆上換了、燈箱主圖沒換」＝ DoD ⓪ 失敗；alias 回
                // 404 的 18 位則因前提僥倖成立而正常 ⇒ **資料相依的間歇失敗**，這正是它躲過所有
                // 先前驗證的原因。詳見 plan-100b.md 的 CD-10 訂正框。
                // ⚠️ 只同步這兩欄，非漏改：燈箱大圖（spec §3.4）恆顯示完整原圖、不裁，
                // currentLightboxActress.auto_focal/.crop_mode 不影響這裡的 render，只有
                // 牆上小格（paginatedActresses[idx]）的 applyCellFocal 會消費這兩欄——已由
                // 上方 _syncActressesArray（100b-T4 擴四欄）處理。
                this.currentLightboxActress.photo_url = data.photo_url;
                this.currentLightboxActress.photo_source = data.photo_source;

                // 順序＝比照 _onPickerSelect 的既有前例（顯式同步 → 刷新旗標），與鄰居一致。
                // ⚠️ 這個順序是否「承重」（＝反轉會不會壞）**未經實測，不要據此宣稱因果**：
                // 直覺說法是「$nextTick 要讀到 Alpine 已 patch 的新 :src」，但兩行之間無 await、
                // 同屬一個同步區塊，Alpine 3.15.12 的 microtask 批次 flush 下**可能等價**。
                // 而「讀源碼推論 flush 時機」在本 branch 已被實證打臉過一次——CDP 實測發現
                // x-show(display) 走 rAF flush、:style 走 microtask flush，**兩者並不同步**
                // （gotchas-frontend §8d）⇒ Alpine 的 flush 時機不是統一的，源碼推論不可靠。
                // 要動這個順序 → 先用 CDP 實測，別靠推理。
                this._refreshActressPhotoLoaded();   // §B-2b 第三呼叫點
                this._closePicker();                 // #4：成功才關，且排在同步之後
                this.showToast(window.t('showcase.actress.picker.replaced'), 'success');
            } catch (e) {
                this._pickerSelected = false;
                this.showToast(window.t('showcase.actress.picker.upload_failed'), 'error');
            }
        },

        /**
         * 關閉 picker：停止 SSE、reset 狀態、metadata 淡入
         */
        _closePicker() {
            this._pickerRunId++;   // invalidate any in-flight SSE callbacks
            if (this._pickerSSE) {
                this._pickerSSE.close();
                this._pickerSSE = null;
            }
            this._resetPicker();
            this._fadeMetadataPanel(false);
        },

        /**
         * 取消 picker（Esc / outside-click）— 播放 reverse 動畫後關閉
         */
        async _cancelPicker() {
            if (!this._pickerOpen || this._pickerSelected) return;
            // Codex P2 fix：reverse 動畫期間鎖住 _onPickerSelect 不被觸發
            this._pickerSelected = true;
            // 鎖住 SSE 不再觸發
            this._pickerRunId++;
            if (this._pickerSSE) { this._pickerSSE.close(); this._pickerSSE = null; }
            // 抓現有候選卡，播 reverse 動畫
            const grid = this.$refs?.pickerGrid;
            const cards = grid ? Array.from(grid.querySelectorAll('.picker-candidate-card')) : [];
            const coverImg = this.$refs.pickerCoverImg;
            if (cards.length > 0 && typeof window.BurstPicker !== 'undefined' && window.BurstPicker.playPickerReverseAll) {
                await new Promise((resolve) => {
                    window.BurstPicker.playPickerReverseAll(cards, coverImg, _PICKER_PARAMS, resolve);
                });
            }
            // 動畫完成後 reset 狀態 + 淡入 metadata
            this._resetPicker();
            this._fadeMetadataPanel(false);
        },

        /**
         * 內部 reset：清空候選 + kill float tweens
         */
        _resetPicker() {
            // 102b T2: ⛔ 不清 _pickerAttempt——本函式也是 🔄 重抓路徑的一環
            // （openActressPicker :1727 會呼叫），在此清會抹掉剛 +1 的值。
            this._pickerOpen = false;
            this._pickerLoading = false;
            this._pickerSelected = false;
            this._candidates = [];
            this._pickerCurrentSource = null;
            this._pickerBurstFired = false;
            // T3（CD-3a）：abort in-flight readiness observer（冪等）。_resetPicker 是所有 teardown
            // 路徑（_closePicker / _cancelPicker / re-open / lightbox cleanup）的共同匯流點。
            this._pickerReadyAbort?.abort();
            this._pickerReadyAbort = null;
            this._pickerFloatTweens.forEach(t => t && t.kill && t.kill());
            this._pickerFloatTweens = [];
            // 清掉 _burstAllPickerCandidates 設的 --picker-cols
            const grid = this.$refs?.pickerGrid;
            if (grid) grid.style.removeProperty('--picker-cols');
        },

        /**
         * Metadata panel 淡出/淡入（Row 1 actress-lb-header 用 :not() 排除）
         */
        _fadeMetadataPanel(out) {
            const meta = this.$el?.querySelector?.('.actress-lightbox-meta');
            if (!meta || typeof gsap === 'undefined') return;
            const rows = meta.querySelectorAll(':scope > :not(.actress-lb-header)');
            if (rows.length === 0) return;
            OpenAver.motion.playFadeTo(rows, {
                opacity: out ? 0 : 1,
                duration: OpenAver.motion.DURATION.fast,
                ease: out ? 'fluent-accel' : 'fluent-decel'
            });
        },

        // --- 快捷鍵 (M4c 完整實作) ---
        handleKeydown(e) {
            // 1. 輸入框中不處理快捷鍵
            if (e.target.tagName === 'INPUT') return;

            // 56c-T4 (codex P1-1)：similar mode 最高優先（高於 sample-gallery / lightbox）
            // ESC → closeSimilarMode；其他鍵在 similar mode 期間獨佔（不傳給 lightbox），
            // 避免箭頭鍵在 constellation 底下偷偷 navigate 隱藏的 lightbox（plan-56c §1 CD-56C-4）
            if (this.similarModeOpen) {
                const similarKey = (e.key || '').toUpperCase();
                if (similarKey === 'ESCAPE') {
                    e.preventDefault();
                    this.closeSimilarMode();
                }
                return;
            }

            // 83b-T1：行動相似面板開啟時鍵盤獨佔（高於 lightbox keydown 路由）。
            // x-trap.inert 只陷焦點，全域 window keydown 仍觸發 → 必須在此攔截，
            // 否則 Esc 穿透到 lightbox 分支關 lightbox、左右箭頭切底層影片（違反 AC-5/AC-8）。
            // closeMobilePanel 屬 state-similar，main.js mergeState 同 this 可達。
            if (this.similarModeMobileOpen) {
                const mobileKey = (e.key || '').toUpperCase();
                if (mobileKey === 'ESCAPE') {
                    e.preventDefault();
                    this.closeMobilePanel();
                }
                // ArrowLeft/Right 及其他鍵：面板無 prev/next → 吞掉，防底層 lightbox 切片
                return;
            }

            // T3.3: Remove Actress modal 開啟時，Esc 優先關閉 modal
            if (e.key === 'Escape' && this.removeActressModalOpen) {
                this.cancelRemoveActressModal();
                e.preventDefault();
                e.stopPropagation();
                return;
            }
            // T3.3: Remove Actress modal 開啟期間鎖其他鍵
            if (this.removeActressModalOpen) return;

            // 49b T4cd: Picker 開啟時，Esc 優先關閉 picker
            if (e.key === 'Escape' && this._pickerOpen) {
                this._cancelPicker();
                e.preventDefault();
                e.stopPropagation();
                return;
            }

            // 62b/62c: rescrape 彈窗蓋在 lightbox 之上時最高優先 —— Esc 關彈窗 + 其餘鍵全鎖
            // （箭頭鍵不得切底層影片；番號 input 已由 #1061 INPUT 擋，但來源 pill 是 BUTTON 不在 INPUT
            // 擋範圍，故仍需此 guard）。鏡射 removeActressModalOpen pattern。
            // 防底層 lightbox 被同一輪 Esc 關掉，靠的是這裡 closeRescrape() 後立刻 return（不進下方 lightbox 區）
            // ＋ _rescrape_modal @keydown.escape.window 的 `rescrapeOpen && closeRescrape()` 短路
            // （此 handler 先註冊先跑、已把 rescrapeOpen 設 false，modal listener 隨後短路成 no-op）。
            // stopPropagation 對「同為 window target 的另一個 listener」其實無效（非 load-bearing），
            // 僅與 removeActressModal/picker 既有寫法對齊；真正擋雙關的是上述 return + 短路。
            if (e.key === 'Escape' && this.rescrapeOpen) {
                this.closeRescrape();
                e.preventDefault();
                e.stopPropagation();
                return;
            }
            if (this.rescrapeOpen) return;

            // C-1: 刪除確認框開啟時，Esc 只關刪除框、其餘鍵不穿透到燈箱（鏡像 removeActressModalOpen）
            if (e.key === 'Escape' && this.deleteVideoModalOpen) {
                this.cancelDeleteVideo();
                e.preventDefault();
                e.stopPropagation();
                return;
            }
            if (this.deleteVideoModalOpen) return;

            // 2. modifier keys 停用
            if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) return;

            // 3. 轉大寫統一處理
            const key = e.key.toUpperCase();

            // 4. Sample Gallery 開啟時的快捷鍵（最高優先）(T7)
            if (this.sampleGalleryOpen) {
                if (key === 'ESCAPE') {
                    e.preventDefault();
                    this.closeSampleGallery();
                } else if (key === 'ARROWLEFT') {
                    e.preventDefault();
                    this.prevSampleGallery();
                } else if (key === 'ARROWRIGHT') {
                    e.preventDefault();
                    this.nextSampleGallery();
                }
                return;
            }

            // 5. Lightbox 開啟時的快捷鍵（按 content type 分發）
            if (this.lightboxOpen) {
                if (this.currentLightboxActress && this.showFavoriteActresses) {
                    // 女優 lightbox（優先級高）
                    if (key === 'ESCAPE') {
                        e.preventDefault();
                        this.closeLightbox();
                    } else if (key === 'ARROWLEFT') {
                        e.preventDefault();
                        this.prevActressLightbox();
                    } else if (key === 'ARROWRIGHT') {
                        e.preventDefault();
                        this.nextActressLightbox();
                    }
                } else {
                    // 影片 lightbox
                    if (key === 'ESCAPE') {
                        e.preventDefault();
                        this.closeLightbox();
                    } else if (key === 'ARROWLEFT') {
                        e.preventDefault();
                        this.prevLightboxVideo();
                    } else if (key === 'ARROWRIGHT') {
                        e.preventDefault();
                        this.nextLightboxVideo();
                    }
                }
                return;
            }

            // 6. 非 Lightbox 狀態的快捷鍵
            if (key === 'S' && this.mode === 'grid') {
                this.toggleInfo();
            } else if (key === 'A') {
                const modeOrder = ['grid', 'list', 'table'];
                const currentIndex = modeOrder.indexOf(this.mode);
                const nextIndex = (currentIndex + 1) % 3;
                this.switchMode(modeOrder[nextIndex]);
            } else if (key === 'ARROWLEFT') {
                if (this.page > 1) {
                    this.prevPage();
                }
            } else if (key === 'ARROWRIGHT') {
                if (this.page < this.totalPages) {
                    this.nextPage();
                }
            }
        },

        /**
         * 滑鼠橫向滾輪導航（TASK-102d-T1，接線 ④⑤⑥⑦）。
         * 單一進入點（`@wheel` 掛在 `.showcase-container` 根節點，非 passive），內部逐條
         * if 分流——guard chain 優先序逐條比照 `handleKeydown`（similarModeOpen/
         * similarModeMobileOpen → removeActressModalOpen → _pickerOpen → rescrapeOpen →
         * deleteVideoModalOpen → sampleGalleryOpen → lightboxOpen(女優/影片分流) →
         * 非 lightbox 狀態的牆翻頁 page 邊界），不得拆成多層各自綁定（Opus 審核註記 #2）。
         * @param {WheelEvent} event
         */
        handleWheel(event) {
            // Opus 審核註記 #1：非 passive 監聽器每個 tick 都同步等 handler 跑完，
            // 第一行必須是純數值方向判斷，DOM 走訪（closest）排在其後。
            // 102d P2b（owner 拍板 2026-07-19）：軸向化——horizontal/vertical 互斥判斷，
            // |dx|===|dy|（含 0,0）兩者皆 false，視為無方向意圖，不處理。
            const horizontal = isHorizontalWheel(event.deltaX, event.deltaY);
            const vertical = !horizontal && isVerticalWheel(event.deltaX, event.deltaY);
            if (!horizontal && !vertical) return;

            // overlay 判斷（純布林讀取，無 DOM 走訪，維持 Opus #1 效能要求）：只有
            // sample gallery / lightbox 這兩種「垂直捲動無意義的全螢幕 overlay」吃垂直滾輪。
            // 牆頁本身垂直捲動是主要瀏覽方式——非 overlay 狀態下垂直滾輪在此零成本早退，
            // 不觸發 closest()/feed()，效能特性與 102d-T1 原版一致。
            const isOverlay = this.sampleGalleryOpen || this.lightboxOpen;
            if (vertical && !isOverlay) return;

            // 排除清單容器：原生橫向捲動優先，不吃導航。
            if (event.target.closest(WHEEL_EXCLUDE_SELECTOR)) return;
            // overlay 內可垂直捲動的子容器（metadata 面板）：垂直滾輪交還原生捲動。
            if (vertical && event.target.closest(WHEEL_VERTICAL_EXCLUDE_SELECTOR)) return;

            // 1. similar mode 最高優先（比照 handleKeydown 段 1）：獨佔，滾輪不穿透
            if (this.similarModeOpen || this.similarModeMobileOpen) return;

            // 2. Remove Actress modal 開啟時鎖
            if (this.removeActressModalOpen) return;

            // 3. Picker 開啟時不接導航（owner 拍板「不接」第 4 項；疊在 lightbox 之上時
            // 由本層 _pickerOpen guard 涵蓋）
            if (this._pickerOpen) return;

            // 4. rescrape 彈窗開啟時鎖
            if (this.rescrapeOpen) return;

            // 5. 刪除確認框開啟時鎖
            if (this.deleteVideoModalOpen) return;

            // 水平方向映射（owner 拍板，Opus 審核修正）：滾輪是「方向指令」隱喻（同
            // ArrowLeft/ArrowRight/scrollbar），不是觸控 detectSwipe 的「拖內容」隱喻——
            // 刻意與 detectSwipe 的 dX<0→'left'→next 相反。往右撥（deltaX>0，util 回呼
            // onRight）對應 ArrowRight 路徑（next）；往左撥（deltaX<0，onLeft）對應
            // ArrowLeft 路徑（prev）。不要「統一」回 swipe 那套映射。
            // 垂直方向映射（102d P2b，owner 拍板 2026-07-19）：圖片瀏覽器慣例——滾下
            // （deltaY>0，onDown）＝下一張；滾上（deltaY<0，onUp）＝上一張。與水平方向
            // 的 prev/next 映射一致（onDown≈onRight≈next、onUp≈onLeft≈prev）。

            // ⑥ Showcase 劇照（最高優先：gallery 疊在 lightbox 之上）
            if (this.sampleGalleryOpen) {
                if (horizontal) {
                    const triggered = wheelNavSampleGallery.feed(event, {
                        onLeft: () => this.prevSampleGallery(),
                        onRight: () => this.nextSampleGallery(),
                    });
                    if (triggered) event.preventDefault();
                } else {
                    // Codex P2（102d 三審）：overlay 垂直分支一律 preventDefault，未達門檻
                    // 的 sub-threshold tick 也吞。showcase 這裡雖有 body-lock
                    // （`overflow-hidden`，見本檔 396/441 行），漏一 tick 理論上捲不動頁面，
                    // 但兩頁 handler 保持同構、防未來 lock 行為改變（例如改 CSS 變數方案不
                    // 再鎖 body）——與 search 版一致收斂為一律擋。水平分支不動。
                    wheelNavSampleGalleryV.feed(event, {
                        onUp: () => this.prevSampleGallery(),
                        onDown: () => this.nextSampleGallery(),
                    });
                    event.preventDefault();
                }
                return;
            }

            // ④⑤ Showcase Lightbox（按 content type 分發，比照 handleKeydown 段 5）
            if (this.lightboxOpen) {
                if (this.currentLightboxActress && this.showFavoriteActresses) {
                    // ⑤ 女優模式
                    if (horizontal) {
                        const triggered = wheelNavLightboxActress.feed(event, {
                            onLeft: () => this.prevActressLightbox(),
                            onRight: () => this.nextActressLightbox(),
                        });
                        if (triggered) event.preventDefault();
                    } else {
                        // Codex P2：同上，overlay 垂直分支一律 preventDefault。
                        wheelNavLightboxActressV.feed(event, {
                            onUp: () => this.prevActressLightbox(),
                            onDown: () => this.nextActressLightbox(),
                        });
                        event.preventDefault();
                    }
                } else {
                    // ④ 影片模式
                    if (horizontal) {
                        const triggered = wheelNavLightboxVideo.feed(event, {
                            onLeft: () => this.prevLightboxVideo(),
                            onRight: () => this.nextLightboxVideo(),
                        });
                        if (triggered) event.preventDefault();
                    } else {
                        // Codex P2：同上，overlay 垂直分支一律 preventDefault。
                        wheelNavLightboxVideoV.feed(event, {
                            onUp: () => this.prevLightboxVideo(),
                            onDown: () => this.nextLightboxVideo(),
                        });
                        event.preventDefault();
                    }
                }
                return;
            }

            // ⑦ 非 Lightbox 狀態：牆翻頁。vertical 已在頂端 isOverlay 早退排除（此處恆為
            // horizontal，`if (!horizontal) return;` 僅作結構性防呆，非預期執行路徑）。
            if (!horizontal) return;
            // Codex P2 修正：邊界（page=1 左撥 / page=totalPages 右撥）在 feed() 之前提早
            // return——不觸發 util、不消耗累積、不 preventDefault、不進冷卻窗，原生捲動/
            // 後續正常滾動不受影響（比照 handleKeydown 段 6 的邊界 guard，但提早到 feed 前）。
            if (event.deltaX < 0 && this.page <= 1) return;
            if (event.deltaX > 0 && this.page >= this.totalPages) return;
            const triggered = wheelNavPage.feed(event, {
                onLeft: () => this.prevPage(),
                onRight: () => this.nextPage(),
            });
            if (triggered) event.preventDefault();
        },

    };
}
