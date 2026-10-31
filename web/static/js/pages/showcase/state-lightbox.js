/**
 * state-lightbox.js — Showcase ESM（54b-T1b，149a 拆檔後為核心）
 *
 * 燈箱核心：開／關（影片＋女優）、上一/下一片導航、封面比例／blur-up、
 * 鍵盤／滾輪／觸控手勢、metadata 搜尋連結。
 * 焦點裁切遮罩、女優換圖挑選器、燈箱自訂標籤、樣本劇照廊已拆成獨立分片
 * （state-lightbox-mask.js / state-lightbox-picker.js / state-lightbox-tags.js /
 * state-lightbox-samples.js），見 plan-149a.md CD-149a-1。
 *
 * 從 state-base.js import 共用大陣列（F1：移出 Alpine reactive scope）。
 */

import { _filteredVideos, _filteredActresses, _killLightboxTimelines, _NO_COVER_PLACEHOLDER, _recomputeVideoBadges, _recomputeCardActorAges, _actresses, _nameToGroup } from '@/showcase/state-base.js';
import { POSTER_CROP_MAX_W } from '@/shared/breakpoints.js';
import { detectSwipe } from '@/shared/swipe.js';
import { isHorizontalWheel, isVerticalWheel, createWheelNav } from '@/shared/wheel-nav.js';
import { shouldShowEnrichButton } from '@/shared/enrich-gate.js';
import { computeActorAgesMap } from '@/shared/actress-release-age.js';


// 120a-T1：.lb-full @error 的遲到事件判定。比較對象是 Alpine :src 寫入的相對路徑
// 字串（getAttribute('src')），不是 IDL .src（瀏覽器已解析成絕對 URL）。
// expectedSrc 為空沿用 isStaleCoverError 短路：不當 stale，交給呼叫端既有分支。
export function isStaleLbFullError(actualSrc, expectedSrc) {
    if (!expectedSrc || !actualSrc) return false;
    return actualSrc !== expectedSrc;
}

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

    return {

        // --- Lightbox 狀態初始值 ---
        // 131a-T4：下面這五個（lightboxOpen / lightboxIndex / lightboxCloseTimer /
        // _lightboxAnimating / _lightboxGeneration）的正本在此。state-base.js 曾有一份
        // 逐字相同的宣告，但 mergeState 順序 base(0) 在前、lightbox(3) 在後，那份從未生效
        // ——改它的人會看到「我改了但沒作用」。該份已於 131a-T4 移除，跨貢獻者撞名由
        // scripts/state_key_guard.mjs 守著。
        lightboxOpen: false,
        lightboxIndex: -1,              // 指向 filteredVideos 的索引
        lightboxCloseTimer: null,       // F2: generation-guarded delayed clear timer

        _lightboxAnimating: false,      // B16: Lightbox 動畫進行中 guard
        _lightboxGeneration: 0,         // B19: invalidation token for deferred $nextTick lightbox callbacks

        // 燈箱觸控狀態
        _lbTouchStartX: null,
        _lbTouchStartY: null,

        currentLightboxVideo: null,

        // 123-T3：精選星 per-path 飛行鎖（keyed by video.path）。
        // 「牆面是否需要重篩」不再用旗標代理（見 _pickFilterStale()，Codex review 抓到
        // 舊版靠兩個旗標代理「牆面是否過期」，並發下會脫鉤——直接觀察真實資料，見下方）。
        _pickInFlight: {},

        _lbFullLoaded: false,           // 71-T6 blur-up：原圖（cover_full_url）@load 後翻 true → overlay opacity 淡入
        _lbFullErrorPill: false,        // 120a-T1：.lb-full @error 通過判定後顯示提示 pill

        // 149b-T3 CD-149b-3：{ 女優名: 發行時年齡 } 對照表。明確重新賦值（見 _refreshLbActorAges），
        // 不是 getter——_actresses/_nameToGroup 是模組層級純陣列/物件（state-base.js:29 F1
        // 註解），Alpine 的 proxy-only 依賴追蹤讀不到它們的變化，getter 會卡死在資料還沒到位
        // 時算出的值。
        _lbActorAges: {},

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
        // 99a-T5：detect-first 重新設計——force-detect 先跑完（星空等待動畫佔位），偵測完成
        // （成功或失敗皆算）才揭露可拖曳的 .lb-mask-window（gate 見 openMask/_computeMaskWinStyle
        // 呼叫點與 showcase.html x-show="_maskVisible && !_maskDetecting"）。拖曳入口只在 detect
        // 已 resolve 後才存在，「detect 還沒回來但已經可以拖」的時間窗在結構上不再存在——原本
        // 99a-T3 為了防這個 race 而加的「使用者已手動調整」旗標因此整條移除（不留殭屍旗標；
        // 舊識別字已由 static_guard_lint.mjs forbidden-string 鎖住不得復活）。

        _videoChipsExpanded: false,     // 影片 tag chips +N 展開（T4 使用）


        // Enrich 狀態 (T3)
        _enriching: false,
        shouldShowEnrichButton,  // CD-149b-9：物件簡寫，import 自 @/shared/enrich-gate.js

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
            this._lbFullErrorPill = false;
            var self = this;
            this.$nextTick(function () {
                var fullImg = self.$refs && self.$refs.lightboxCoverFull;
                if (fullImg && fullImg.complete && fullImg.naturalWidth > 0) {
                    self._lbFullLoaded = true;
                }
            });
        },

        // 149b-T3（CD-149b-3）：燈箱女優列「發行時年齡」重算——規則是「_refreshLbFullBlurUp()
        // 出現在哪，這個就出現在哪」（六個刷新點，見 plan-149b §9 陷阱②）。對 currentLightboxVideo
        // 的女優列每個 trim 過的名字呼叫一次 resolveFavoriteActressAge()，組出
        // { 名字: 年齡 }（算不出來的名字直接跳過，不寫入 null），整份**明確重新賦值**給
        // this._lbActorAges（新物件參照——Alpine 的 proxy set 攔截靠參照變化，原地 mutate 偵測
        // 不到，見 mutation 點①）。
        _refreshLbActorAges() {
            this._lbActorAges = { ...computeActorAgesMap(this.currentLightboxVideo, _actresses, _nameToGroup) };
        },

        // 120a-T1：.lb-full 原圖載入失敗。第一行 AC-A6 短路（DB 無封面 cover_full_url
        // 恆為空字串，<img :src=""> 的 error 不是「拿不到」）。$refs 防呆後用
        // getAttribute('src') 對當下 cover_full_url 做 stale 判定（AC-A4），通過才設旗標。
        // 不呼叫 handleCoverError、不改 has_cover（AC-A5）。
        _handleLbFullError(event) {
            if (!this.currentLightboxVideo?.cover_full_url) return;
            const target = event && event.target;
            if (target !== this.$refs.lightboxCoverFull) return;
            const actualSrc = (target && target.getAttribute('src')) || '';
            if (isStaleLbFullError(actualSrc, this.currentLightboxVideo.cover_full_url)) return;
            this._lbFullErrorPill = true;
        },


        // 101d-T1：影片焦點 icon 顯示 gate（CD-4）。語意旗標 method——只在畫面真的以 poster 裁切
        // 呈現時才顯示 icon。x-show 以 () 呼叫，理由是比照 _focalIconVisible() 慣例／可讀性／
        // 未來相容性——**保留括號**。⚠️ 但別把「漏括號」當 runtime bug：Alpine 3 對 x-show
        // **尾端**求值為 function 者會 auto-invoke（101d-T1 CDP 實測），故
        // `A && B && _posterModeActive` 在當前版本其實等效帶括號、非 gate 失效（見 gotchas-frontend
        // 「Alpine methods 必須加 ()」節精確化）。119-T5 已 landed：body 為
        // `return this._isNarrow || this.cardShape === 'poster'`，不動 icon x-show、不動任何呼叫端
        // （plan-101d CD-4，spec §7.2 Non-Goal #14）。
        // 本 method **只服務燈箱焦點鈕**。選單條數與 A 鍵段數絕不可讀它（CD-119-4／§0.1）。
        // 影片 gate 與女優 _focalIconVisible() 的 per-image 門檻刻意不同（影片只 ≤899px 裁、女優牆
        // 全寬度都裁，plan-101d §2.2）——此不對稱是有原則的，勿「對齊」成同一套。
        _posterModeActive() {
            return this._isNarrow || this.cardShape === 'poster';
        },

        // F1: helper — 更新 lightboxIndex + currentLightboxVideo 一致性
        _setLightboxIndex(idx) {
            // 123-T4 / C27：燈箱星是常駐節點，切換影片必須先殺掉進行中的 --pick-fill
            // 與 scale tween，否則下一幀 GSAP 會把上一片的中間值蓋回來。
            // 123-T4b：GSAP 呼叫收斂進 animations.js（TestMotionInfra 守衛，見該檔
            // killPickStarTweens 註解）。不清 --pick-fill（沿用搬移前行為）。
            window.ShowcaseAnimations?.killPickStarTweens?.({ clearTransform: true });
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
            this._refreshLbActorAges();
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
            this._lbPlotReset?.();       // 187b-T5a：關燈箱清簡介面（defense-in-depth）
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
            // 123-T4 / CD-123-12：關燈箱是獨立於 _setLightboxIndex 的第三個 kill sink
            // （_setLightboxIndex(-1) 要等 250ms delayed timer）。完整 teardown（含 --pick-fill）。
            // 123-T4b：GSAP 呼叫收斂進 animations.js（TestMotionInfra 守衛，見該檔
            // killPickStarTweens 註解）。
            window.ShowcaseAnimations?.killPickStarTweens?.({ clearFill: true, clearTransform: true });
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
            // 123-T3 / CD-123-14a：掛精選 pill 期間若切過星，關燈箱才重篩（不當場抽走當前卡）。
            // 直接觀察真實資料（_pickFilterStale()），不再靠旗標代理。
            // 123-T4（自生洞修正）：有精選請求還在飛時，_filteredVideos 裡看到的是尚未確認的
            // 樂觀值——這時候重篩可能把「等一下要回滾」的卡移出清單，回滾後述詞掃不到它，
            // 卡就回不來了。等最後一個請求落地（成功或已回滾）再判定，見 _pickHasInFlight()。
            if (!this._pickHasInFlight() && this._pickFilterStale()) this.applyFilterAndSort();
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

        // Metadata 點擊搜尋 (M3f)
        // TASK-115-T4（CD-2）：本函式只負責步驟 1–5（同步關燈箱 + 250ms 延遲清 index，
        // 逐字保留、不可改動順序）。步驟 6–10（正規化／去重／篩選／動畫／hero reconciliation）
        // 全部收斂進 state-videos.js 的 addPill（T1 已落地）——本函式不得再自行呼叫
        // _animateFilter/_checkPreciseActressMatch/_clearPreciseMatch 等舊職責，未來新增
        // pill 相關行為請改 addPill 那個方法，不要在這裡加回分支。
        searchFromMetadata(value, dim) {
            // F2: cancel pending delayed clear from previous close
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }

            // 同步關閉 lightbox（跳過動畫，後面馬上做 filter 動畫）
            _killLightboxTimelines();
            // 123-T4 review M1：這裡是第 4 條 kill sink（不走 closeLightbox()，_setLightboxIndex(-1)
            // 要等 250ms delayed timer）。只止血不 clearProps——teardown 留給 closeLightbox()。
            // 123-T4b：GSAP 呼叫收斂進 animations.js（TestMotionInfra 守衛，見該檔
            // killPickStarTweens 註解）。
            window.ShowcaseAnimations?.killPickStarTweens?.({});
            var lightboxEl = document.querySelector('.showcase-lightbox');
            if (lightboxEl) lightboxEl.classList.remove('gsap-animating');
            this._lightboxAnimating = false;
            this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
            this.lightboxOpen = false;
            // 123-T3 / CD-123-14a：這條路徑本來就會經 addPill 重篩一次，述詞式不需要事先清任何東西。
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

            // TASK-124a-T2（CD-124a-6）：release 維度改走發售日入口 adapter，不經 addPill
            // （addPill 的正規化/去重路徑不適用 release 的 op/value2 結構）。
            if (dim === 'release') {
                this._setReleasePillFromDate(value);
            } else {
                this.addPill(dim, value);
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
            // 124c-T3（spec-124c §3.4）：對焦編輯進行中不換片。必須是第一行——下面的
            // _killLightboxTimelines()／清 gsap-animating／_closePicker() 都是副作用，
            // 插在它們之後＝「不換片但靜靜把 picker 關掉」，那是半套。
            // 切片會 _resetMask()，正在調的對焦位置就沒了。
            if (this._navBlockedByFocalEdit()) return;
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
            // 124c-T3（spec-124c §3.4）：對焦編輯進行中不換片。必須是第一行——下面的
            // _killLightboxTimelines()／清 gsap-animating／_closePicker() 都是副作用，
            // 插在它們之後＝「不換片但靜靜把 picker 關掉」，那是半套。
            // 切片會 _resetMask()，正在調的對焦位置就沒了。
            if (this._navBlockedByFocalEdit()) return;
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





        // ==================== Pick Star (123-T3) ====================
        // 樂觀更新 + per-path 飛行鎖 + CD-123-15 captured ref + 三層失敗判定。
        // 成功不提示；失敗回滾 captured video + showToast。
        // T4：樂觀更新／回滾後 $nextTick 接 playPickFill（Alpine :style 先寫終值）。

        // 「自生洞立即停」（2026-08-08 起）：舊版用一個「dirty」旗標＋一個「這次是不是我設起來
        // 的」輔助旗標代理「成員關係變了嗎」，在並發（兩個 path 同時在飛）與飛行中關燈箱下都會
        // 與真實狀態脫鉤——旗標本身就是上一輪為修別的問題而加的機制，這次不再 fix-forward
        // 同一個機制，改成直接觀察真實資料的述詞。
        //
        // 述詞：牆上顯示的清單，與「精選」這個條件現在是否還一致？掛著精選 pill 時，
        // _filteredVideos 裡的每一片理應都是精選的；只要有一片不是，就代表牆面已經過期。
        _pickFilterStale() {
            var hasPickPill = this.pills.some(function (p) { return p.dim === 'pick'; });
            if (!hasPickPill) return false;      // 沒掛精選 pill → 永遠不重篩（CD-123-14a）

            // 123-T8c：算一次真實 membership 跟現況比對，**不猜**。
            //
            // 舊版是「掃 _filteredVideos 有沒有 rating 0」——那是單向的猜法，只看得到
            // 「該離開牆的」，看不到「該回到牆上的」。兩輪 review 各從不同入口打中同一個洞：
            //   · grok Stage 1 P2：飛行中被外部重篩把卡移出清單 → 回滾後述詞掃不到它 → 卡不回來
            //   · Codex PR review P2：從相似面板點進一部**不在清單裡**的未精選片、給它按星
            //                          → 述詞掃不到它 → 新精選的卡不會出現在牆上
            // 補「另一邊」修不好：membership 還同時受其他 pill 與搜尋字影響（某片是精選但被
            // 女優 pill 排除，補了就變成每次關燈箱都重篩、隨機排序整牆重洗）。
            // 所以改成直接呼叫篩選那一半（_computeFilteredVideos()，不排序不寫 state）比對
            // path 集合 —— 兩個方向都準，且沒有「其他篩選條件」的盲點。
            //
            // 成本：一次 O(N) 篩選 + Set 比對，只在關燈箱／精選請求落地時各跑一次。
            var next = this._computeFilteredVideos();
            if (next.length !== _filteredVideos.length) return true;
            var current = new Set(_filteredVideos.map(function (v) { return v.path; }));
            return next.some(function (v) { return !current.has(v.path); });
        },

        // 還有精選請求在路上時，樂觀值尚未確認——這時候重篩會用「可能等一下就要回滾的資料」
        // 去移除牆上的卡，而回滾之後述詞掃不到已經被移出清單的那片，卡就回不來了。
        // 等最後一個請求落地再篩（那時資料已經是定局，不論成功或已回滾）。
        _pickHasInFlight() {
            for (var k in this._pickInFlight) { if (this._pickInFlight[k]) return true; }
            return false;
        },

        async togglePickStar() {
            var video = this.currentLightboxVideo;
            if (!video || !video.path) return;
            var path = video.path;
            if (this._pickInFlight[path]) return;

            var oldValue = video.user_rating || 0;
            var newValue = oldValue > 0 ? 0 : 1;

            this._pickInFlight[path] = true;
            video.user_rating = newValue;
            this.$nextTick(() => {
                window.ShowcaseAnimations?.playPickFill?.(
                    document.querySelector('.pick-star-fill'),
                    document.querySelector('.pick-star-outline'),
                    oldValue > 0,
                    newValue > 0
                );
            });

            try {
                var resp = await fetch('/api/user-rating', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: path, picked: newValue > 0 }),
                });
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                var data = await resp.json();
                if (data.success !== true) throw new Error('API failed');
                if (data.results?.[0]?.ok !== true) throw new Error('not_found');
                // 成功：樂觀更新已是最終狀態，什麼都不做
            } catch (e) {
                video.user_rating = oldValue;
                // CD-123-15 在動畫層的同一個坑：回滾發生在 await 之後，燈箱裡那顆星是**常駐節點**，
                // 這時候可能已經在顯示別片了。不檢查就會把「這一片的回滾動畫」畫到「另一片的星」
                // 上——實測過：取消已精選的 A、飛行中滾到未精選的 B、A 失敗回滾 → B 的
                // aria-pressed 還是 false，星卻被畫成滿金色。只有還停在同一片時才播回滾動畫；
                // 換片的話 Alpine 的 :style 綁定本來就已經把星畫成新片該有的樣子了。
                if (this.currentLightboxVideo === video) {
                    this.$nextTick(() => {
                        window.ShowcaseAnimations?.playPickFill?.(
                            document.querySelector('.pick-star-fill'),
                            document.querySelector('.pick-star-outline'),
                            newValue > 0,
                            oldValue > 0
                        );
                    });
                }
                this.showToast(window.t('showcase.pick.save_failed'), 'error');
            } finally {
                delete this._pickInFlight[path];   // 本次的鎖先解掉，_pickHasInFlight() 才不會被自己擋住
                // 燈箱還開著就不重篩（spec §4.13：不能把使用者正在看的那片從腳下抽走）；
                // 已經關了才補一次——這條涵蓋「點完馬上關燈箱、請求之後才回來（或失敗回滾）」，
                // 以及「兩個不同 path 同時在飛，其中一個成功改變了成員關係」（沒有旗標可競爭，
                // 每次都重新觀察真實資料）。
                // 123-T4：仍有其他 path 的請求在飛時也不篩（同 closeLightbox 的理由，見
                // _pickHasInFlight() 註解）——等最後一個落地才篩一次。
                if (!this.lightboxOpen && !this._pickHasInFlight() && this._pickFilterStale()) this.applyFilterAndSort();
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
                        readonly_action: 'ingest',
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
                    this.showToast(window.t('showcase.samples.multi_video_error'), 'warning');
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
                    _recomputeVideoBadges(video);
                    _recomputeCardActorAges(video);
                    // BUGfix-lightbox-cover-stale: 若燈箱正開在這支影片，重置 blur-up overlay，
                    // 讓 cover_full_url（已 bust）重新觸發 @load → _lbFullLoaded 淡入。
                    // 用 === video 守住：燈箱開在別支影片時不誤 reset。
                    // 必須在 Object.assign 之後呼叫（src 已更新，$nextTick complete-check 才讀到新 URL）。
                    if (this.currentLightboxVideo === video) {
                        this._refreshLbFullBlurUp();
                        this._refreshLbActorAges();
                    }
                }
            } catch (e) {
                // refresh 失敗不顯示額外 toast
            }
        },


        // --- 快捷鍵 (M4c 完整實作) ---
        handleKeydown(e) {
            // 116b：浮層開啟時最高優先（必須在 INPUT early-return 之前——區間的 number input
            // 取得焦點時 e.target.tagName === 'INPUT'，放在後面 ESC 永遠到不了這裡）。
            // TASK-124a-T2：新增 _releaseEditor 分支（兩個 slot 依 §3.5 不變式恆不同時非
            // null，三元式安全）。
            if (this._pillEditor || this._releaseEditor) {
                if (e.key === 'Escape') { e.preventDefault(); this._pillEditor ? this._cancelPillEditor() : this._cancelReleaseEditor(); return; }
                return;                       // 第二段：鎖其餘鍵。不得 preventDefault
            }
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

            // 面板開啟時全域快捷鍵必須隔離——x-trap 只在 Tab／Esc 攔截，其餘按鍵照樣冒泡到
            // @keydown.window，不擋的話焦點在愛心／關閉鈕時按 A／S／左右鍵會改動背後
            // showcase 的檢視模式與頁碼（Codex PR#133 P3）。
            if (e.key === 'Escape' && this.actressAddPanelOpen) {
                this.closeActressAddPanel();
                e.preventDefault();
                e.stopPropagation();
                return;
            }
            if (this.actressAddPanelOpen) return;

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
                        if (this.lbPlotOpen) { e.preventDefault(); this.lbPlotClose(); return; }
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
            if (key === 'S' && (this.mode === 'grid' || this.showFavoriteActresses)) {
                this.toggleInfo();
            } else if (key === 'A') {
                if (this.showFavoriteActresses) return;          // AC-5.3：女優牆整條早退
                const order = this._presentationOrder();
                const idx = order.indexOf(this._currentPresentation());
                this.selectPresentation(order[(idx + 1) % order.length]);
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
