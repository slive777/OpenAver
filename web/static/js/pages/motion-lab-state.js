function motionLabPage() {
    return {
        tab: 'search',
        mode: 'grid',
        selectedIndex: 0,
        params: {
            duration: 0.6,
            stagger: 0.05,
            clipRevealDur: 0.5,
            easing: 'back.out(1.2)',
            flipMode: 'Flip',
            reducedMotionSim: false,
            speed: 0.5,
            detailSpeed: 1.5,
            streamStyle: 'fadeScale',
            streamInterval: 300
        },
        videos: [],
        loading: true,
        isNavigating: false,
        isTransitioning: false,
        streamCards: Array(12).fill(null),
        streamRunning: false,
        _streamTimers: [],

        // Staging Burst 沙盒 state
        stagingParams: {
            batchInterval: 800,
            minBatchCount: 3,
            burstEase: 'back.out(1.2)',
            burstDuration: 0.6,
            coverInterval: 300,
        },
        stagingBuffer: [],
        stagingFilled: 0,
        stagingTotal: 12,
        stagingRunning: false,
        _stagingTimers: [],
        _stagingBurstTimer: null,
        _burstBatchIndex: 0,
        _stagingRunId: 0,
        stagingCards: Array(12).fill(null),
        stagingCurrentCover: null,
        stagingCurrentNum: null,
        stagingOverlayVisible: false,   // overlay staging card 是否存在於畫面（控制 x-show）
        _allItemsArrived: false,        // 所有 result-item 已推入 buffer（消除 final flush timer）
        _stagingExiting: false,         // exit 動畫進行中（防止 pulse killTweensOf 殺死 exit）
        _pulseDebounceTimer: null,      // micro-pulse debounce timer（150ms）

        // Settle Pulse 沙盒 state
        settleParams: {
            ease: 'settle',
            duration: 0.8,
            scale: 1.06,
            rows: 2,
        },

        // Hero Slot 沙盒 state
        heroParams: {
            heroDelay: 2000,
            heroResult: 'found',
            heroReserved: true,
        },
        _heroSlotReserved: false,
        _heroFilled: false,
        _heroRunning: false,
        _heroTimers: [],
        heroActressProfile: null,
        heroCards: Array(12).fill(null),

        // Showcase 沙盒 state
        showcaseParams: {
            style: 'stagger',
            duration: 0.5,
            stagger: 0.04,
            flipDuration: 0.5,
            flipEase: 'power2.inOut',
            flipPrune: true,
            filterQuery: '',
            filterEnterStyle: 'opacityScale',
            filterLeaveStyle: 'opacityScale',
            filterDuration: 0.4,
            pageDuration: 0.3,
            pageStagger: 0.02,
        },

        init() {
            this.fetchVideos();
            // 鍵盤 ←/→ 快捷鍵
            this._onKeyDown = (e) => {
                if (this.mode !== 'detail') return;
                // 排除表單元素，避免劫持 slider/select/input 的方向鍵
                const tag = e.target.tagName;
                if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || tag === 'BUTTON' || e.target.isContentEditable) return;
                if (e.key === 'ArrowLeft') this.onPrev();
                if (e.key === 'ArrowRight') this.onNext();
            };
            window.addEventListener('keydown', this._onKeyDown);
        },

        destroy() {
            if (this._onKeyDown) {
                window.removeEventListener('keydown', this._onKeyDown);
            }
        },

        async fetchVideos() {
            try {
                const resp = await fetch('/api/motion-lab/data');
                const data = await resp.json();
                if (data.success) {
                    this.videos = data.videos;
                }
            } catch (e) {
                console.error('[MotionLab] fetchVideos 失敗:', e);
            } finally {
                this.loading = false;
            }
        },

        get hasVideos() {
            return this.videos.length > 0;
        },

        get selectedVideo() {
            return this.videos[this.selectedIndex] || this.videos[0] || null;
        },

        formatActresses(actresses) {
            if (Array.isArray(actresses)) return actresses.slice(0, 2).join(', ');
            return actresses || '';
        },

        formatActressesDetail(actresses) {
            if (Array.isArray(actresses)) return actresses.join(', ');
            return actresses || '';
        },

        onPlayBurst() {
            if (!this.hasVideos || typeof window.MotionLab === 'undefined') return;
            const gridEl = this.$refs.grid;
            const searchBarEl = this.$refs.searchBar;
            if (gridEl && searchBarEl) {
                const tl = window.MotionLab.playGridBurst(gridEl, searchBarEl, this.params);
                // 串接 clip-path reveal（burst 尾端重疊）
                if (tl) {
                    window.MotionLab.playClipPathReveal(gridEl, this.params);
                }
            }
        },

        async onDetailEntry() {
            if (!this.hasVideos || typeof window.MotionLab === 'undefined') return;
            if (this.isTransitioning) return;
            this.isTransitioning = true;

            var ghost = null;
            var fromEl = null;
            var toEl = null;

            try {
                // reducedMotionSim 或系統 prefers-reduced-motion 時走降級路徑（無 ghost）
                const skipAnim = this.params.reducedMotionSim ||
                    !!(window.OpenAver && window.OpenAver.prefersReducedMotion);
                const flipMode = this.params.flipMode || 'Flip';

                // Level 2（skipAnim 或 flipMode=None）：量測前就能短路，不嘗試 ghost
                if (skipAnim || flipMode === 'None') {
                    this.mode = 'detail';
                    await this.$nextTick();
                    await new Promise(r => requestAnimationFrame(r));
                    const detailElL2 = this.$refs.detail;
                    if (detailElL2) {
                        // 預隱藏 info，避免 nextTick+rAF 到 playDetailEntry 之間閃現
                        var l2InfoEl = detailElL2.querySelector('.av-card-full-info');
                        if (l2InfoEl) gsap.set(l2InfoEl, { opacity: 0 });
                        window.MotionLab.playDetailEntry(detailElL2, Object.assign({}, this.params, { skipCover: true }));
                    }
                    return;
                }

                // flipMode === 'Crossfade'：強制走 Crossfade，不嘗試建 ghost
                if (flipMode === 'Crossfade') {
                    const gridEl = this.$refs.grid;
                    var cfFromCapture = window.MotionLab.captureCoverRect(gridEl, this.selectedIndex);
                    var cfFromEl = cfFromCapture ? cfFromCapture.el : null;

                    this.mode = 'detail';
                    await this.$nextTick();
                    await new Promise(r => requestAnimationFrame(r));

                    const detailElCF = this.$refs.detail;
                    if (!detailElCF) return;

                    // 預隱藏 info，避免轉場期間閃現
                    var cfInfoEl = detailElCF.querySelector('.av-card-full-info');
                    if (cfInfoEl) gsap.set(cfInfoEl, { opacity: 0 });

                    var cfToCapture = window.MotionLab.captureCoverRect(detailElCF, null);
                    var cfToEl = cfToCapture ? cfToCapture.el : null;

                    await window.MotionLab.playCrossfadeTransition(cfFromEl, cfToEl, this.params);
                    // source 封面還原（grid 已不顯示，防殘留）
                    if (cfFromEl) gsap.set(cfFromEl, { opacity: 1 });

                    window.MotionLab.playDetailEntry(detailElCF, Object.assign({}, this.params, { skipCover: true }));
                    return;
                }

                // flipMode === 'Flip'：嘗試 ghost 主路徑
                var fromCapture = null;
                {
                    const gridEl = this.$refs.grid;
                    fromCapture = window.MotionLab.captureCoverRect(gridEl, this.selectedIndex);
                    if (fromCapture) fromEl = fromCapture.el;
                }

                // 切換到 detail 模式
                this.mode = 'detail';

                await this.$nextTick();
                // 等待瀏覽器繪製完成
                await new Promise(r => requestAnimationFrame(r));

                const detailEl = this.$refs.detail;
                if (!detailEl) return;

                // 預隱藏 info，避免轉場期間閃現
                var infoEl = detailEl.querySelector('.av-card-full-info');
                if (infoEl) gsap.set(infoEl, { opacity: 0 });

                if (fromCapture) {
                    // 量測 to rect（detail 封面）
                    var toCapture = window.MotionLab.captureCoverRect(detailEl, null);

                    if (toCapture) {
                        toEl = toCapture.el;
                        // 建 ghost、隱藏真實封面
                        ghost = window.MotionLab.createCoverGhost(fromCapture.el, fromCapture.rect);
                        gsap.set(fromCapture.el, { opacity: 0 });
                        gsap.set(toEl, { opacity: 0 });

                        // 執行 ghost 飛行動畫
                        await window.MotionLab.playSharedCoverTransition(
                            ghost, fromCapture.rect, toCapture.rect, this.params
                        );

                        // cleanup ghost、還原封面
                        window.MotionLab.cleanupCoverGhost(ghost, fromEl, toEl);
                        ghost = null;

                        // 只播 info 進場
                        window.MotionLab.playDetailEntry(detailEl, Object.assign({}, this.params, { skipCover: true }));
                        return;
                    }
                }

                // Flip 主路徑 ghost 量測失敗 → 降級到 Level 1 Crossfade
                {
                    var fbFromEl = fromCapture ? fromCapture.el : null;
                    var fbToCapture = window.MotionLab.captureCoverRect(detailEl, null);
                    var fbToEl = fbToCapture ? fbToCapture.el : null;
                    await window.MotionLab.playCrossfadeTransition(fbFromEl, fbToEl, this.params);
                    if (fbFromEl) gsap.set(fbFromEl, { opacity: 1 });
                    window.MotionLab.playDetailEntry(detailEl, Object.assign({}, this.params, { skipCover: true }));
                }

            } finally {
                // 確保 ghost 被清除（例外時）
                if (ghost) {
                    window.MotionLab.cleanupCoverGhost(ghost, fromEl, toEl);
                }
                this.isTransitioning = false;
            }
        },

        async onPrev() {
            if (!this.hasVideos || typeof window.MotionLab === 'undefined') return;
            if (this.mode !== 'detail' || this.selectedIndex <= 0) return;
            if (this.isTransitioning) return;
            if (this.isNavigating) return;
            this.isNavigating = true;
            try {
                const detailEl = this.$refs.detail;
                const cardEl = detailEl ? detailEl.querySelector('.av-card-full') : null;
                if (!cardEl) return;
                await window.MotionLab.playSlideOut(cardEl, 'prev', this.params);
                this.selectedIndex--;
                await this.$nextTick();
                const tweenPrev = window.MotionLab.playSlideIn(cardEl, 'prev', this.params);
                if (tweenPrev) await tweenPrev;
            } finally {
                this.isNavigating = false;
            }
        },

        async onNext() {
            if (!this.hasVideos || typeof window.MotionLab === 'undefined') return;
            if (this.mode !== 'detail' || this.selectedIndex >= this.videos.length - 1) return;
            if (this.isTransitioning) return;
            if (this.isNavigating) return;
            this.isNavigating = true;
            try {
                const detailEl = this.$refs.detail;
                const cardEl = detailEl ? detailEl.querySelector('.av-card-full') : null;
                if (!cardEl) return;
                await window.MotionLab.playSlideOut(cardEl, 'next', this.params);
                this.selectedIndex++;
                await this.$nextTick();
                const tweenNext = window.MotionLab.playSlideIn(cardEl, 'next', this.params);
                if (tweenNext) await tweenNext;
            } finally {
                this.isNavigating = false;
            }
        },

        async onToggleMode() {
            if (!this.hasVideos || typeof window.MotionLab === 'undefined') return;

            if (this.mode === 'grid') {
                // Grid → Detail: 走 onDetailEntry() 主流程
                await this.onDetailEntry();
                return;
            }

            // Detail → Grid
            if (this.isTransitioning) return;
            this.isTransitioning = true;

            var ghost = null;
            var fromEl = null;
            var toEl = null;

            try {
                const skipAnim = this.params.reducedMotionSim ||
                   !!(window.OpenAver && window.OpenAver.prefersReducedMotion);
                const flipMode = this.params.flipMode || 'Flip';

                // Level 2（skipAnim 或 flipMode=None）：量測前短路，不嘗試 ghost 或 crossfade
                if (skipAnim || flipMode === 'None') {
                    this.mode = 'grid';
                    // 無動畫，直接結束
                    return;
                }

                // 先淡出 info（約 120ms），只在 Flip(Ghost) 路徑
                if (flipMode === 'Flip') {
                    const detailElForExit = this.$refs.detail;
                    await window.MotionLab.playInfoExit(detailElForExit, this.params);
                }

                // 量測 from rect（Detail 側封面）
                var fromCapture = null;
                {
                    const detailEl = this.$refs.detail;
                    fromCapture = window.MotionLab.captureCoverRect(detailEl, null);
                    if (fromCapture) fromEl = fromCapture.el;
                }

                // 切換回 grid 模式
                this.mode = 'grid';

                await this.$nextTick();
                await new Promise(r => requestAnimationFrame(r));

                // flipMode === 'Flip'：嘗試 ghost 主路徑
                if (flipMode === 'Flip' && fromCapture) {
                    const gridEl = this.$refs.grid;
                    // 找到目標卡片的封面，先 scrollIntoView 確保可量測
                    const targetCards = gridEl ? gridEl.querySelectorAll('.av-card-preview') : [];
                    const targetCard = targetCards[this.selectedIndex];
                    if (targetCard) {
                        targetCard.scrollIntoView({ block: 'nearest' });
                        // 等一個 rAF 讓 scroll settle
                        await new Promise(r => requestAnimationFrame(r));
                    }

                    var toCapture = window.MotionLab.captureCoverRect(gridEl, this.selectedIndex);

                    if (toCapture) {
                        toEl = toCapture.el;

                        // 驗證目標 rect 在 viewport 內（負值或超出視口則降級）
                        var tr = toCapture.rect;
                        var vw = window.innerWidth;
                        var vh = window.innerHeight;
                        var rectValid = tr.right > 0 && tr.bottom > 0 && tr.left < vw && tr.top < vh;

                        if (rectValid) {
                            ghost = window.MotionLab.createCoverGhost(fromCapture.el, fromCapture.rect);
                            gsap.set(fromCapture.el, { opacity: 0 });
                            gsap.set(toEl, { opacity: 0 });

                            await window.MotionLab.playSharedCoverTransition(
                                ghost, fromCapture.rect, toCapture.rect, this.params
                            );

                            window.MotionLab.cleanupCoverGhost(ghost, fromEl, toEl);
                            ghost = null;
                            // 目標卡落位 settle（非阻塞）
                            if (targetCard) {
                                window.MotionLab.playTargetSettle(targetCard, this.params);
                            }
                            return;
                        }
                    }
                }

                // Crossfade 路徑（flipMode=Crossfade，或 flipMode=Flip 且 ghost 量測失敗）
                {
                    const gridEl = this.$refs.grid;
                    // scrollIntoView 讓目標可量測
                    const targetCards = gridEl ? gridEl.querySelectorAll('.av-card-preview') : [];
                    const targetCard = targetCards[this.selectedIndex];
                    if (targetCard) {
                        targetCard.scrollIntoView({ block: 'nearest' });
                        await new Promise(r => requestAnimationFrame(r));
                    }

                    var cfFromEl = fromCapture ? fromCapture.el : null;
                    var cfToCapture = window.MotionLab.captureCoverRect(gridEl, this.selectedIndex);
                    var cfToEl = cfToCapture ? cfToCapture.el : null;

                    await window.MotionLab.playCrossfadeTransition(cfFromEl, cfToEl, this.params);
                    // 還原 source（detail 封面，grid 模式已不顯示，防殘留）
                    if (cfFromEl) gsap.set(cfFromEl, { opacity: 1 });
                }

            } finally {
                if (ghost) {
                    window.MotionLab.cleanupCoverGhost(ghost, fromEl, toEl);
                }
                this.isTransitioning = false;
            }
        },

        onReset() {
            if (typeof window.MotionLab === 'undefined') return;
            const gridEl = this.$refs.grid;
            const detailEl = this.$refs.detail;
            window.MotionLab.resetAll(gridEl, detailEl);
            this.mode = 'grid';
            this.isNavigating = false;
            this.isTransitioning = false;
            // 清除殘留 ghost 節點
            document.querySelectorAll('.motion-lab-ghost').forEach(function (el) {
                el.remove();
            });
        },

        onResetStream() {
            // 清除所有待執行的 setTimeout
            this._streamTimers.forEach(function (handle) {
                clearTimeout(handle);
            });
            this._streamTimers = [];
            // 重置 streamCards 為 12 個 null（觸發 Alpine reactivity）
            this.streamCards = Array(12).fill(null);
            this.streamRunning = false;
            // 清除 GSAP 殘留（stream grid）
            if (typeof window.MotionLab !== 'undefined') {
                const streamGridEl = this.$refs.streamGrid;
                if (streamGridEl) {
                    window.MotionLab.resetAll(streamGridEl, null);
                }
            }
        },

        async onStreamIn() {
            // guard：防重複觸發
            if (this.streamRunning) return;
            if (!this.videos.length) return;

            // 先 reset 確保乾淨狀態
            this.onResetStream();

            this.streamRunning = true;

            const count = Math.min(12, this.videos.length);
            const baseInterval = this.params.streamInterval;

            for (let i = 0; i < count; i++) {
                const videoObj = this.videos[i];
                // 隨機間隔：baseInterval ± 30%
                const jitter = baseInterval * 0.3;
                const delay = Math.max(0, i * baseInterval + (Math.random() * jitter * 2 - jitter));

                const handle = setTimeout(async () => {
                    // Alpine reactivity：clone 後重新賦值
                    const updated = [...this.streamCards];
                    updated[i] = videoObj;
                    this.streamCards = updated;

                    // 等待 Alpine 更新 DOM，再觸發動畫
                    await this.$nextTick();
                    await new Promise(r => requestAnimationFrame(r));

                    const streamGridEl = this.$refs.streamGrid;
                    if (!streamGridEl) return;
                    const cardEl = streamGridEl.querySelectorAll('.av-card-preview')[i];
                    if (!cardEl) return;

                    if (typeof window.MotionLab !== 'undefined') {
                        window.MotionLab.playCardStreamIn(cardEl, this.params.streamStyle, this.params);
                    }

                    // 最後一張填入後解除 streamRunning
                    if (i === count - 1) {
                        this.streamRunning = false;
                    }
                }, delay);

                this._streamTimers.push(handle);
            }

            // 若 videos 不足 12 筆，最後一個 timer 完成後解除 running
            // （count < 12 時，count-1 的 setTimeout 已在上面設 streamRunning=false）
            // 若 count === 0，確保 streamRunning 解除（已在 guard return 前處理）
        },

        onResetStaging() {
            // 清除所有 staging timers
            this._stagingTimers.forEach(function (handle) {
                clearTimeout(handle);
            });
            this._stagingTimers = [];
            if (this._stagingBurstTimer !== null) {
                clearTimeout(this._stagingBurstTimer);
                this._stagingBurstTimer = null;
            }
            // 清 micro-pulse debounce timer
            if (this._pulseDebounceTimer !== null) {
                clearTimeout(this._pulseDebounceTimer);
                this._pulseDebounceTimer = null;
            }
            // 生成 token 遞增：使所有飛行中的 async callback 失效
            this._stagingRunId++;
            // 重置 staging state
            this.stagingCards = Array(12).fill(null);
            this.stagingBuffer = [];
            this.stagingFilled = 0;
            this.stagingTotal = 12;
            this.stagingRunning = false;
            this._burstBatchIndex = 0;
            this.stagingCurrentCover = null;
            this.stagingCurrentNum = null;
            this.stagingOverlayVisible = false;
            this._allItemsArrived = false;
            this._stagingExiting = false;
            // 重置 staging card 寬度（由 onStagingBurst 動態量測設定）
            const stagingCardResetEl = this.$refs.stagingCard;
            if (stagingCardResetEl) {
                stagingCardResetEl.style.width = '';
            }
            // 清除 GSAP 殘留
            if (typeof window.MotionLab !== 'undefined') {
                const stagingGridEl = this.$refs.stagingGrid;
                if (stagingGridEl) {
                    window.MotionLab.resetAll(stagingGridEl, null);
                }
                // 清理 staging anchor 內 staging card 的 GSAP 殘留
                const stagingCardEl = this.$refs.stagingCard;
                if (stagingCardEl) {
                    gsap.killTweensOf(stagingCardEl);
                    gsap.set(stagingCardEl, { clearProps: 'transform,opacity,zIndex' });
                    const stagingImgEl = this.$refs.stagingImg;
                    if (stagingImgEl) {
                        gsap.killTweensOf(stagingImgEl);
                        gsap.set(stagingImgEl, { clearProps: 'opacity' });
                    }
                }
            }
        },

        // ===== Hero Slot 沙盒 methods =====

        onResetHero() {
            // 清除所有 hero timers
            this._heroTimers.forEach(function (handle) {
                clearTimeout(handle);
            });
            this._heroTimers = [];
            // 重置 hero state
            this._heroSlotReserved = false;
            this._heroFilled = false;
            this._heroRunning = false;
            this.heroActressProfile = null;
            this.heroCards = Array(12).fill(null);
            // 清除 GSAP 殘留
            if (typeof window.MotionLab !== 'undefined') {
                const heroGridEl = this.$refs.heroGrid;
                if (heroGridEl) {
                    window.MotionLab.resetAll(heroGridEl, null);
                }
                const heroPlaceholderEl = this.$refs.heroPlaceholder;
                if (heroPlaceholderEl) {
                    heroPlaceholderEl.style.display = '';
                    gsap.killTweensOf(heroPlaceholderEl);
                    gsap.set(heroPlaceholderEl, { clearProps: 'all' });
                    const heroImg = heroPlaceholderEl.querySelector('img');
                    if (heroImg) {
                        gsap.killTweensOf(heroImg);
                        gsap.set(heroImg, { clearProps: 'all' });
                    }
                }
            }
        },

        async onPlayHero() {
            if (this._heroRunning) return;
            if (!this.hasVideos) return;
            this.onResetHero();

            this._heroRunning = true;
            const self = this;
            const heroDelay = this.heroParams.heroDelay;
            const heroResult = this.heroParams.heroResult;
            const heroReserved = this.heroParams.heroReserved;

            // 填充 heroCards（瞬間填入，焦點是 hero 預留/移除）
            const cardCount = Math.min(12, this.videos.length);
            // 用 videos[1..12] 當卡片（留 videos[0] 給 hero profile）
            const cardVideos = this.videos.slice(1, cardCount + 1);

            if (heroReserved) {
                // === 路徑 A：預留 Hero Slot ===
                this._heroSlotReserved = true;
                // 填入卡片
                for (let i = 0; i < cardVideos.length; i++) {
                    this.heroCards[i] = cardVideos[i];
                }

                // Grid 淡入
                await this.$nextTick();
                const heroGridEl = this.$refs.heroGrid;
                if (heroGridEl && typeof gsap !== 'undefined') {
                    gsap.from(heroGridEl, { opacity: 0, duration: 0.25, ease: 'power1.out' });
                }

                // 延遲後處理 hero
                await new Promise(function (resolve) {
                    const t = setTimeout(resolve, heroDelay);
                    self._heroTimers.push(t);
                });

                if (!this._heroRunning) return; // guard: reset during delay

                if (heroResult === 'found') {
                    // Hero found: 填充封面
                    this.heroActressProfile = this.videos[0];
                    this._heroFilled = true;
                    await this.$nextTick();
                    const heroEl = this.$refs.heroPlaceholder;
                    if (heroEl && typeof window.MotionLab !== 'undefined') {
                        window.MotionLab.playHeroFill(heroEl, {
                            reducedMotionSim: this.params.reducedMotionSim
                        });
                    }
                } else {
                    // Hero not found: Flip 移除（呼叫端控制時序）
                    const gridEl = this.$refs.heroGrid;
                    if (gridEl && typeof window.MotionLab !== 'undefined' && typeof Flip !== 'undefined') {
                        // 1. 捕獲佈局（DOM 變更前）
                        var gridChildren = gridEl.querySelectorAll('.av-card-preview');
                        gsap.killTweensOf(gridChildren);  // C4
                        var flipState = Flip.getState(gridChildren);

                        // 2. Alpine state 驅動移除
                        self._heroSlotReserved = false;

                        // 3. 等 Alpine DOM patch 完成後 Flip 動畫
                        await new Promise(function(resolve) {
                            self.$nextTick(function() {
                                window.MotionLab.playHeroRemove(flipState, {
                                    reducedMotionSim: self.params.reducedMotionSim
                                }).then(resolve);
                            });
                        });
                    } else {
                        this._heroSlotReserved = false;
                    }
                }
            } else {
                // === 路徑 B：不預留（A/B 對比：重現 bug） ===
                // 直接填入 12 張卡（無 hero slot）
                for (let i = 0; i < cardVideos.length; i++) {
                    this.heroCards[i] = cardVideos[i];
                }

                // Grid 淡入
                await this.$nextTick();
                const heroGridEl = this.$refs.heroGrid;
                if (heroGridEl && typeof gsap !== 'undefined') {
                    gsap.from(heroGridEl, { opacity: 0, duration: 0.25, ease: 'power1.out' });
                }

                // 延遲後處理 hero
                await new Promise(function (resolve) {
                    const t = setTimeout(resolve, heroDelay);
                    self._heroTimers.push(t);
                });

                if (!this._heroRunning) return; // guard: reset during delay

                if (heroResult === 'found') {
                    // Hero 突然插入第一格（無 Flip — 重現 bug）
                    this.heroActressProfile = this.videos[0];
                    this._heroFilled = true;
                    this._heroSlotReserved = true;
                }
                // not-found 時不做任何事
            }

            this._heroRunning = false;
        },

        async triggerMiniBurst(batch, runId, isFinalBurst) {
            if (!batch || !batch.length) return;
            if (typeof window.MotionLab === 'undefined') return;
            // Race-safety: bail out if a reset happened before we started
            if (runId !== undefined && this._stagingRunId !== runId) return;

            // C13: clone + reassign for Alpine reactivity
            const updated = [...this.stagingCards];
            batch.forEach(function (item) {
                updated[item.slot] = item.video;
            });
            this.stagingCards = updated;

            // 等待 Alpine DOM 更新
            await this.$nextTick();
            await new Promise(r => requestAnimationFrame(r));

            // Race-safety: bail out if a reset happened during await
            if (runId !== undefined && this._stagingRunId !== runId) return;

            const stagingGridEl = this.$refs.stagingGrid;
            const stagingCardEl = this.$refs.stagingCard;
            if (!stagingGridEl) return;

            // 取本批填入的 slot 對應 DOM 元素（排除 staging card 本身）
            const allCards = stagingGridEl.querySelectorAll('.av-card-preview');
            const newCardEls = batch.map(function (item) {
                return allCards[item.slot] || null;
            }).filter(Boolean);

            if (!newCardEls.length) return;

            const batchZ = this._burstBatchIndex++;
            const tl = window.MotionLab.playStagingBurst(newCardEls, stagingCardEl, {
                duration: this.stagingParams.burstDuration,
                ease: this.stagingParams.burstEase,
                stagger: 0.05,
                batchZ: batchZ,
                reducedMotionSim: this.params.reducedMotionSim
            });

            if (isFinalBurst) {
                tl.then(() => {
                    this._triggerStagingExit(runId);
                });
            }
            // isFinalBurst === false 時：fire-and-forget，不做額外處理
        },

        _triggerStagingExit(runId) {
            if (this._stagingRunId !== runId) return;
            // 清 pulse debounce：避免 exit 期間觸發 pulse
            if (this._pulseDebounceTimer !== null) {
                clearTimeout(this._pulseDebounceTimer);
                this._pulseDebounceTimer = null;
            }
            // 標記 exit 進行中（雙重保護：playStagingPulse 開頭也會 check）
            this._stagingExiting = true;
            // 先停 rotating border（stagingRunning → false）
            this.stagingRunning = false;
            // 播 exit morph；onComplete 才設 stagingOverlayVisible = false
            const cardEl = this.$refs.stagingCard;
            const capturedRunId = runId;
            window.MotionLab.playStagingExit(cardEl, {
                reducedMotionSim: this.params.reducedMotionSim
            }, () => {
                // C1：onComplete 只做最終 state 收尾
                if (this._stagingRunId !== capturedRunId) return;
                this.stagingOverlayVisible = false;
                this._stagingExiting = false;
            });
        },

        async onStagingBurst() {
            // guard: 防重複觸發
            if (this.stagingRunning || this._stagingExiting) return;
            if (typeof window.MotionLab === 'undefined') return;

            // reset first（會遞增 _stagingRunId，使舊 async callbacks 失效）
            this.onResetStaging();

            if (!this.videos.length) return;

            this.stagingRunning = true;
            this.stagingOverlayVisible = true;

            // 動態量測 grid 卡片寬度，套到 staging card（§8）
            await this.$nextTick();
            const firstGridCard = this.$refs.stagingGrid.querySelector('.av-card-preview');
            if (firstGridCard && this.$refs.stagingCard) {
                const cardWidth = firstGridCard.getBoundingClientRect().width;
                this.$refs.stagingCard.style.width = cardWidth + 'px';
            }
            // 播入場動畫
            window.MotionLab.playStagingEntry(this.$refs.stagingCard, {
                reducedMotionSim: this.params.reducedMotionSim
            });

            // 捕獲本次執行的 run token
            const runId = this._stagingRunId;

            const total = Math.min(this.stagingTotal, this.videos.length);
            this.stagingTotal = total;
            const coverInterval = this.stagingParams.coverInterval;
            const batchInterval = this.stagingParams.batchInterval;
            const minBatchCount = this.stagingParams.minBatchCount;

            // 逐張推入 stagingBuffer（模擬 SSE result-item 到達）
            for (let i = 0; i < total; i++) {
                const videoObj = this.videos[i];
                const delay = i * coverInterval;

                const handle = setTimeout(async () => {
                    // Race-safety: 若 reset 已發生則放棄
                    if (this._stagingRunId !== runId) return;

                    // 推入 buffer
                    this.stagingBuffer = [...this.stagingBuffer, { slot: i, video: videoObj }];
                    this.stagingFilled = this.stagingFilled + 1;

                    // 更新 staging card 顯示（最新封面 + 番號）— 立即執行
                    this.stagingCurrentNum = videoObj.number || null;
                    this.stagingCurrentCover = videoObj.cover_url || null;

                    // 等 Alpine 更新 DOM 再播封面 swap 動畫（立即，每次到達都播）
                    await this.$nextTick();
                    await new Promise(r => requestAnimationFrame(r));

                    // Race-safety: 再次確認 await 後未被 reset
                    if (this._stagingRunId !== runId) return;

                    const imgEl = this.$refs.stagingImg;
                    if (imgEl && this.stagingCurrentCover) {
                        window.MotionLab.playCoverSwap(imgEl, { reducedMotionSim: this.params.reducedMotionSim });
                    }

                    // 第一張 pop，後續 micro-pulse（150ms debounce）
                    if (i === 0) {
                        window.MotionLab.playStagingPop(this.$refs.stagingCard, {
                            reducedMotionSim: this.params.reducedMotionSim
                        });
                    } else {
                        if (this._pulseDebounceTimer !== null) clearTimeout(this._pulseDebounceTimer);
                        const capturedRunId = runId;
                        this._pulseDebounceTimer = setTimeout(() => {
                            if (this._stagingRunId !== capturedRunId) return;
                            if (this._stagingExiting) return;  // exit 進行中，不觸發
                            window.MotionLab.playStagingPulse(this.$refs.stagingCard, {
                                reducedMotionSim: this.params.reducedMotionSim
                            });
                            this._pulseDebounceTimer = null;
                        }, 180);
                    }

                    // 最後一張到達：設 _allItemsArrived，讓 scheduleBurstTimer 統一處理
                    if (i === total - 1) {
                        this._allItemsArrived = true;
                        // 不排 final flush timer！scheduleBurstTimer 是唯一 flush owner
                    }
                }, delay);

                this._stagingTimers.push(handle);
            }

            // 時間窗口 timer：定期 flush stagingBuffer（唯一 flush owner）
            const scheduleBurstTimer = () => {
                if (this._stagingBurstTimer !== null) {
                    clearTimeout(this._stagingBurstTimer);
                }
                this._stagingBurstTimer = setTimeout(async () => {
                    // Race-safety: 若 reset 已發生則停止排程
                    if (this._stagingRunId !== runId) return;

                    if (!this._allItemsArrived) {
                        // 未全部到齊：只在達到 minBatchCount 時 flush
                        if (this.stagingBuffer.length >= minBatchCount) {
                            const batch = [...this.stagingBuffer];
                            this.stagingBuffer = [];
                            await this.triggerMiniBurst(batch, runId, false);
                        }
                        // 繼續排程
                        if (this._stagingRunId === runId) scheduleBurstTimer();
                    } else {
                        // 全部已到齊
                        if (this.stagingBuffer.length > 0) {
                            // 有剩餘：flush 全部（不管 minBatchCount），isFinalBurst = true
                            const batch = [...this.stagingBuffer];
                            this.stagingBuffer = [];
                            await this.triggerMiniBurst(batch, runId, true);
                        } else {
                            // buffer 已空：所有卡片已被之前的 flush 處理，直接 exit
                            this._triggerStagingExit(runId);
                        }
                        // _allItemsArrived 路徑不再繼續排程（由 _triggerStagingExit 或 tl.then 接手）
                    }
                }, batchInterval);
            };
            scheduleBurstTimer();
        }
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('motionLabPage', motionLabPage);
});
