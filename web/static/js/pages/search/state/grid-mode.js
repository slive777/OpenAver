/**
 * SearchState - Grid Mode Mixin
 * 包含：Grid 模式切換、Lightbox 控制
 */
window.SearchStateMixin_GridMode = {
    // ===== Display Mode Toggle =====

    /**
     * 切換 Detail ↔ Grid 模式（U4: C17 三步動畫）
     */
    toggleDisplayMode() {
        var wasDetail = this.displayMode === 'detail';

        // C17 step 1: capture BEFORE state change
        var fromRect = null;
        var coverSrc = null;
        if (wasDetail) {
            var detailEl = document.querySelector('.av-card-full');
            var detailImg = detailEl ? detailEl.querySelector('.av-card-full-cover-img') : null;
            if (detailImg && detailImg.complete && detailImg.getBoundingClientRect().width > 0) {
                fromRect = detailImg.getBoundingClientRect();
                coverSrc = detailImg.src;
            }
        }

        // C17 step 2: state change (Alpine render)
        this.displayMode = wasDetail ? 'grid' : 'detail';
        this.saveState();

        // C17 step 3: animate (fire-and-forget)
        this.$nextTick(() => {
            if (wasDetail && fromRect && coverSrc) {
                // Detail -> Grid: ghost fly-back
                var grid = document.querySelector('.search-grid');
                var targetCard = grid ? grid.querySelector('[data-slot="' + this.currentIndex + '"]') : null;
                window.SearchAnimations?.playDetailToGrid?.(fromRect, targetCard, { coverSrc: coverSrc });
            } else if (!wasDetail) {
                // Grid -> Detail: detail entry
                var newDetailEl = document.querySelector('.av-card-full');
                window.SearchAnimations?.playDetailEntry?.(newDetailEl);
            }
        });
    },

    // ===== Lightbox Control =====

    /**
     * 開啟 Lightbox
     * @param {number} index - 搜尋結果索引
     */
    openLightbox(index) {
        // F2: cancel pending delayed clear from previous close
        if (this.lightboxCloseTimer) {
            clearTimeout(this.lightboxCloseTimer);
            this.lightboxCloseTimer = null;
        }
        if (this._lightboxAnimating) return;  // D2: guard
        if (this.lightboxOpen && this.lightboxIndex === index) return;  // 同一張，不動作

        // Fix: lightbox 已開啟時走 switch 路徑（避免 backdrop click-through 重播 open 動畫）
        if (this.lightboxOpen && this.lightboxIndex !== index) {
            // C18: interrupt — kill 舊 switch timeline（含 onComplete callback）
            if (typeof gsap !== 'undefined') {
                gsap.getById('lightboxSwitch')?.kill();
            }
            var oldIndex = this.lightboxIndex;
            var direction = index > oldIndex ? 'next' : 'prev';

            // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
            this._heroLightboxImageError = false;
            this.lightboxIndex = index;
            this.currentIndex = index;

            // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
            var lbGen = ++this._lightboxGeneration;
            this.$nextTick(() => {
                if (this._lightboxGeneration !== lbGen) return;  // stale — lightbox was closed/interrupted
                var content = document.querySelector('.lightbox-content');
                if (content && window.SearchAnimations?.playLightboxSwitch) {
                    this._lightboxAnimating = true;
                    var tl = window.SearchAnimations.playLightboxSwitch(content, direction, {
                        onComplete: () => { this._lightboxAnimating = false; }
                    });
                    if (!tl) this._lightboxAnimating = false;
                }
            });
            return;
        }

        this._heroLightboxImageError = false;  // A6-1: 重置圖片錯誤狀態
        this.lightboxIndex = index;
        this.lightboxOpen = true;
        // 同步 currentIndex（讓 Detail 與 Grid 保持一致）
        this.currentIndex = index;

        // D2: 進場動畫（fire-and-forget）
        var lbGen = ++this._lightboxGeneration;
        this.$nextTick(() => {
            if (this._lightboxGeneration !== lbGen) return;  // B19: stale
            var el = document.querySelector('.showcase-lightbox');
            if (window.SearchAnimations?.playLightboxOpen) {
                this._lightboxAnimating = true;
                var tl = window.SearchAnimations.playLightboxOpen(el, {
                    onComplete: () => { this._lightboxAnimating = false; }
                });
                if (!tl) this._lightboxAnimating = false;
            }
        });
    },

    /**
     * 關閉 Lightbox
     */
    closeLightbox() {
        // F2: cancel pending delayed clear from previous close
        if (this.lightboxCloseTimer) {
            clearTimeout(this.lightboxCloseTimer);
            this.lightboxCloseTimer = null;
        }

        // T8: 若 gallery 開啟中一併關閉（外部直接關 lightbox 時 gallery 不應殘留）
        if (this.sampleGalleryOpen) this.closeSampleGallery();

        this._lightboxGeneration++;  // B19: invalidate pending $nextTick lightbox callbacks
        // Instant close — kill any in-progress lightbox animations, then sync close
        if (typeof gsap !== 'undefined') {
            gsap.getById('lightboxOpen')?.kill();
            gsap.getById('lightboxSwitch')?.kill();
        }
        var lbEl = document.querySelector('.showcase-lightbox');
        if (lbEl) lbEl.classList.remove('gsap-animating');
        this._lightboxAnimating = false;
        this.lightboxOpen = false;

        // F2: delay state clearing until CSS transition completes (250ms)
        // Keep currentLightboxVideo intact during fade-out, then clear after
        // Generation-guarded to prevent stale callback from clearing newly-opened lightbox
        var self = this;
        var gen = this._lightboxGeneration;  // capture current generation
        this.lightboxCloseTimer = setTimeout(() => {
            if (self._lightboxGeneration === gen && !self.lightboxOpen) {
                self.lightboxIndex = -1;
            }
            self.lightboxCloseTimer = null;
        }, 250);
    },

    /**
     * 開啟 Actress Lightbox（Hero Card 專用）
     */
    openActressLightbox() {
        if (this._lightboxAnimating) return;  // D2: guard
        if (!this.actressProfile) return;  // A6-2: 無女優資料時不開啟 lightbox
        this._heroLightboxImageError = false;  // A6-1: 重置圖片錯誤狀態
        this.lightboxIndex = -1;
        this.lightboxOpen = true;

        // D2: 進場動畫（fire-and-forget）
        var lbGen = ++this._lightboxGeneration;
        this.$nextTick(() => {
            if (this._lightboxGeneration !== lbGen) return;  // B19: stale
            var el = document.querySelector('.showcase-lightbox');
            if (window.SearchAnimations?.playLightboxOpen) {
                this._lightboxAnimating = true;
                var tl = window.SearchAnimations.playLightboxOpen(el, {
                    onComplete: () => { this._lightboxAnimating = false; }
                });
                if (!tl) this._lightboxAnimating = false;
            }
        });
    },

    /**
     * Lightbox 上一部
     */
    prevLightboxVideo() {
        // C18: interrupt — kill open + switch timeline（進場動畫未完也要打斷）
        if (typeof gsap !== 'undefined') {
            gsap.getById('lightboxOpen')?.kill();
            gsap.getById('lightboxSwitch')?.kill();
        }
        this._lightboxAnimating = false;
        var lbEl = document.querySelector('.showcase-lightbox');
        if (lbEl) lbEl.classList.remove('gsap-animating');

        if (this.lightboxIndex === -1) {
            // Already at actress photo (leftmost) — do nothing
            return;
        }

        // D2: 計算目標 index（不立即更新 state）
        var newIdx;
        if (this.lightboxIndex === 0 && this.actressProfile) {
            newIdx = -1;  // go to actress photo
        } else if (this.lightboxIndex > 0) {
            // U11b: skip _failed items going backwards
            newIdx = this.lightboxIndex - 1;
            while (newIdx >= 0 && this.searchResults[newIdx]._failed) {
                newIdx--;
            }
            if (newIdx < 0 && this.actressProfile) {
                newIdx = -1;  // all items before current are _failed, jump to actress photo
            } else if (newIdx < 0) {
                return;  // no valid items and no actress → don't move
            }
        } else {
            return;  // lightboxIndex === 0 && no actress → don't move
        }

        // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
        this._heroLightboxImageError = false;
        this.lightboxIndex = newIdx;
        if (newIdx >= 0) this.currentIndex = newIdx;

        // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
        var lbGen = ++this._lightboxGeneration;
        this.$nextTick(() => {
            if (this._lightboxGeneration !== lbGen) return;  // stale — lightbox was closed/interrupted
            var content = document.querySelector('.lightbox-content');
            if (content && window.SearchAnimations?.playLightboxSwitch) {
                this._lightboxAnimating = true;
                var tl = window.SearchAnimations.playLightboxSwitch(content, 'prev', {
                    onComplete: () => { this._lightboxAnimating = false; }
                });
                if (!tl) this._lightboxAnimating = false;
            }
        });
    },

    /**
     * Lightbox 下一部
     */
    async nextLightboxVideo() {
        // C18: interrupt — kill open + switch timeline（進場動畫未完也要打斷）
        if (typeof gsap !== 'undefined') {
            gsap.getById('lightboxOpen')?.kill();
            gsap.getById('lightboxSwitch')?.kill();
        }
        this._lightboxAnimating = false;
        var lbEl = document.querySelector('.showcase-lightbox');
        if (lbEl) lbEl.classList.remove('gsap-animating');

        // D2: 計算目標 index（不立即更新 state）
        var newIdx;
        if (this.lightboxIndex === -1) {
            // U11b: from actress photo, find first non-_failed item
            newIdx = this.searchResults.findIndex(r => !r._failed);
            if (newIdx === -1) return;  // no valid items → don't move
        } else if (this.lightboxIndex < this.searchResults.length - 1) {
            // U11b: skip _failed items going forward
            newIdx = this.lightboxIndex + 1;
            while (newIdx < this.searchResults.length && this.searchResults[newIdx]._failed) {
                newIdx++;
            }
            if (newIdx >= this.searchResults.length) {
                // T3c: await loadMore + state-first crossfade（skip _failed 後越界）
                if (this.hasMoreResults && !this.isLoadingMore) {
                    const result = await this.loadMore('lightbox');
                    if (!result || result.loadedCount === 0) return;
                    // C17 state-first
                    this._heroLightboxImageError = false;
                    this.currentIndex = result.oldLength;
                    this.lightboxIndex = result.oldLength;
                    // generation guard（await 期間 lightbox 可能被關閉）
                    var lbGen = ++this._lightboxGeneration;
                    this.$nextTick(() => {
                        if (this._lightboxGeneration !== lbGen) return;
                        var content = document.querySelector('.lightbox-content');
                        if (content && window.SearchAnimations?.playLightboxSwitch) {
                            this._lightboxAnimating = true;
                            var tl = window.SearchAnimations.playLightboxSwitch(content, 'next', {
                                onComplete: () => { this._lightboxAnimating = false; }
                            });
                            if (!tl) this._lightboxAnimating = false;
                        }
                    });
                }
                return;
            }
        } else {
            // T3c: await loadMore + state-first crossfade（已在最後一片）
            if (this.hasMoreResults && !this.isLoadingMore) {
                const result = await this.loadMore('lightbox');
                if (!result || result.loadedCount === 0) return;
                // C17 state-first
                this._heroLightboxImageError = false;
                this.currentIndex = result.oldLength;
                this.lightboxIndex = result.oldLength;
                // generation guard（await 期間 lightbox 可能被關閉）
                var lbGen = ++this._lightboxGeneration;
                this.$nextTick(() => {
                    if (this._lightboxGeneration !== lbGen) return;
                    var content = document.querySelector('.lightbox-content');
                    if (content && window.SearchAnimations?.playLightboxSwitch) {
                        this._lightboxAnimating = true;
                        var tl = window.SearchAnimations.playLightboxSwitch(content, 'next', {
                            onComplete: () => { this._lightboxAnimating = false; }
                        });
                        if (!tl) this._lightboxAnimating = false;
                    }
                });
            }
            return;  // at last item → don't move
        }

        // B19: state-first — 立即更新 state，避免 C18 interrupt 吞掉 index mutation
        this._heroLightboxImageError = false;
        this.lightboxIndex = newIdx;
        this.currentIndex = newIdx;

        // B19: 動畫（state 已更新，$nextTick 後 Alpine 已 patch DOM）
        var lbGen = ++this._lightboxGeneration;
        this.$nextTick(() => {
            if (this._lightboxGeneration !== lbGen) return;  // stale — lightbox was closed/interrupted
            var content = document.querySelector('.lightbox-content');
            if (content && window.SearchAnimations?.playLightboxSwitch) {
                this._lightboxAnimating = true;
                var tl = window.SearchAnimations.playLightboxSwitch(content, 'next', {
                    onComplete: () => { this._lightboxAnimating = false; }
                });
                if (!tl) this._lightboxAnimating = false;
            }
        });
    },

    /**
     * Lightbox 背景點擊處理（點擊背景關閉 / 點擊卡片切換）
     * @param {MouseEvent} event - 點擊事件
     */
    handleLightboxBackdropClick(event) {
        // T5: 對齊 showcase.js L420-446 的 Click-through 邏輯

        // 如果點擊的是 lightbox-content 內部，不處理（對齊 showcase）
        if (event.target.closest('.lightbox-content')) return;

        // 暫時隱藏 lightbox 來檢測下方元素
        const lightbox = event.currentTarget;
        lightbox.style.display = 'none';

        // 找到點擊位置下的元素
        const elementBelow = document.elementFromPoint(event.clientX, event.clientY);

        // 恢復 lightbox
        lightbox.style.display = '';

        // 檢查是否是卡片 → 觸發卡片自身的 @click handler（hero card / 普通卡片都適用）
        const cardEl = elementBelow?.closest('.search-grid .av-card-preview') || null;
        if (cardEl) {
            cardEl.click();
        } else {
            this.closeLightbox();
        }
    },

    /**
     * 取得當前 Lightbox 影片
     * @returns {Object|null} 當前影片資料
     */
    currentLightboxVideo() {
        if (this.lightboxIndex < 0) return null;
        return this.searchResults[this.lightboxIndex] || null;
    },

    // ===== Grid ↔ Detail 切換 =====

    /**
     * 從 Grid 切換到 Detail 模式（U4: C17 三步 ghost 轉場）
     * @param {number} index - 搜尋結果索引
     */
    switchToDetail(index) {
        // 防禦：若 Lightbox 仍開啟，先關閉（避免覆蓋層影響 grid 卡片座標）
        if (this.lightboxOpen) {
            this.lightboxOpen = false;
        }

        // C17 step 1: capture source rect BEFORE state change
        var grid = document.querySelector('.search-grid');
        var card = grid ? grid.querySelector('[data-slot="' + index + '"]') : null;
        var img = card ? card.querySelector('.av-card-preview-img img') : null;
        var fromRect = (img && img.complete && img.getBoundingClientRect().width > 0)
            ? img.getBoundingClientRect() : null;
        var coverSrc = img ? img.src : null;

        // C17 step 2: state change (Alpine render)
        this.displayMode = 'detail';
        this.currentIndex = index;
        this._resetCoverState();
        this.saveState();

        // C17 step 3: animate (fire-and-forget)
        this.$nextTick(() => {
            var detailEl = document.querySelector('.av-card-full');
            if (fromRect && coverSrc) {
                window.SearchAnimations?.playGridToDetail?.(fromRect, detailEl, { coverSrc: coverSrc });
            } else {
                // Ghost fallback: full detail entry
                window.SearchAnimations?.playDetailEntry?.(detailEl);
            }
        });
    },

    /**
     * 標記 Grid 圖片載入失敗
     * @param {number} index - 卡片索引
     */
    markImageError(index) {
        this._gridImageErrors = new Set([...this._gridImageErrors, index]);
    },

    // ==================== T8: Sample Gallery Methods ====================

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
            if (self._sgGeneration !== gen) return; // stale check
            var imgEl = document.querySelector('.sg-main-img');
            if (imgEl) {
                window.SearchAnimations?.playSampleGallerySwitch?.(imgEl, 'prev', {});
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
            if (self._sgGeneration !== gen) return; // stale check
            var imgEl = document.querySelector('.sg-main-img');
            if (imgEl) {
                window.SearchAnimations?.playSampleGallerySwitch?.(imgEl, 'next', {});
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
            if (self._sgGeneration !== gen) return; // stale check
            var imgEl = document.querySelector('.sg-main-img');
            if (imgEl) {
                window.SearchAnimations?.playSampleGallerySwitch?.(imgEl, direction, {});
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
    }

    // ==================== End Sample Gallery Methods ====================
};
