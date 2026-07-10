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
import { waitForMount } from '@/shared/dom-timing.js';

export function stateLightbox() {
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

        _videoChipsExpanded: false,     // 影片 tag chips +N 展開（T4 使用）

        // 49b T4cd: Actress Photo Picker 狀態
        _pickerOpen: false,
        _candidates: [],
        _pickerLoading: false,
        _pickerSelected: false,
        _pickerCurrentSource: null,
        _pickerFloatTweens: [],
        _pickerRunId: 0,
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

            // 44b: -1 sentinel — already at leftmost, do not move
            if (this.lightboxIndex === -1) return;

            // 44b: index 0 + hero card → retreat to -1
            if (this.lightboxIndex === 0 && this._isPreciseActressMatch && this._matchedActress && this._matchedActress.is_favorite) {
                var self = this;
                // B19: state-first
                this.lightboxIndex = -1;
                this.currentLightboxActress = this._matchedActress;
                this.currentLightboxVideo = null;
                this.addingLbTag = false;
                this._videoChipsExpanded = false;

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

            // 44b: from -1 (hero card) → jump to first video
            if (this.lightboxIndex === -1) {
                if (_filteredVideos.length === 0) return;
                var self = this;
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
            if (this._candidates.length === 0) return;
            if (this._pickerBurstFired) return;     // 防 done/timeout/error 重複觸發
            this._pickerBurstFired = true;          // dedup latch 維持在等待前（位置不動）

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
            const url = `/api/actresses/${encodeURIComponent(name)}/photo-candidates`;
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
         * Helper: 換照片成功後同步 _actresses 陣列對應 entry
         */
        _syncActressesArray(name, data) {
            if (!data || !data.photo_url) return;
            const idx = this.paginatedActresses.findIndex(a => a.name === name);
            if (idx >= 0) {
                this.paginatedActresses[idx].photo_url = data.photo_url;
                this.paginatedActresses[idx].photo_source = data.photo_source;
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

    };
}
