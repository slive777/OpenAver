/**
 * state-actress.js — Showcase ESM（54b-T1b）
 *
 * 女優模式：loadActresses / filter / sort / CRUD / lightbox / chips helpers。
 * 從 state-base.js import 共用大陣列（F1：移出 Alpine reactive scope）。
 */

import { _actresses, _filteredActresses, _actressesLoaded, _nameToGroup, _loadAliasMap, _killLightboxTimelines, _setActressesLoaded, _setActresses, _setFilteredActresses } from '@/showcase/state-base.js';

export function stateActress() {
    return {

        // --- 44a: 女優模式狀態初始值 ---
        showFavoriteActresses: false,   // mode toggle，切換影片/女優 grid
        actressCount: 0,                // mirror _actresses.length
        filteredActressCount: 0,        // mirror _filteredActresses.length
        paginatedActresses: [],         // CD-9：全量 = _filteredActresses，不分頁
        actressSearch: '',              // 女優搜尋框（獨立於 search）
        actressSort: 'video_count',     // 預設排序
        actressOrder: 'desc',           // 預設降冪
        actressLoading: false,          // 載入中
        actressLightboxIndex: -1,       // 指向 _filteredActresses 的索引
        currentLightboxActress: null,   // 當前 lightbox 女優；與 currentLightboxVideo 互斥
        actressLightboxSource: null,    // T5: 'hero' | 'grid' | null — 進入路徑（CD-9）
        _ghostFlyInFlight: false,       // T7: 跨模式 ghost fly 並發保護 flag（CD-13）
        _actressChipsExpanded: { aliases: false, info: false },  // chips 展開狀態
        _addActressName: '',            // + 新增 input
        _addingActress: false,          // 新增 loading
        _addDropdownOpen: false,        // + 新增 popover 開關

        // T3.3: Remove Actress fluent-modal 狀態
        removeActressModalOpen: false,
        _removeActressLoading: false,
        _pendingRemoveActressName: null,

        // 44b: 精準匹配狀態
        _isPreciseActressMatch: false,
        _matchedActress: null,
        _preciseMatchSource: null,
        _favoriteHeartLoading: false,
        _heroCardImageError: false,
        _heroCardImageLoaded: false,   // 67-A3: hero actress photo 載入旗標（獨立於 video _imgLoaded，CD-67-4）
        _fetchSamplesLoading: false,
        _fetchSamplesFailed: {},

        // --- helpers in return {} ---

        // 44a: helper — 更新 actressLightboxIndex + currentLightboxActress 一致性
        _setActressLightboxIndex(idx) {
            this.actressLightboxIndex = idx;
            this.currentLightboxActress = (idx >= 0 && idx < _filteredActresses.length)
                ? _filteredActresses[idx] : null;
            this.currentLightboxVideo = null;    // 互斥：清除影片
            this._actressChipsExpanded = { aliases: false, info: false };
        },

        // 44b: 精準匹配 helpers
        _clearPreciseMatch() {
            this._isPreciseActressMatch = false;
            this._matchedActress = null;
            this._preciseMatchSource = null;
            this._favoriteHeartLoading = false;
            this._heroCardImageError = false;
            this._heroCardImageLoaded = false;   // 67-A3: 換命中對象要重現 skeleton
        },

        async _checkPreciseActressMatch(term, source) {
            var capturedTerm = (term || '').trim();
            if (!_actressesLoaded && _actresses.length === 0) {
                await this.loadActresses();
            }
            if (this.search.trim() !== capturedTerm) return;
            this._heroCardImageError = false;
            this._heroCardImageLoaded = false;   // 67-A3: 換命中對象要重現 skeleton
            var found = _actresses.find(function(a) {
                var group = _nameToGroup[a.name] || [a.name];
                return group.indexOf(capturedTerm) !== -1;
            });
            if (found) {
                this._isPreciseActressMatch = true;
                this._matchedActress = found;
                this._preciseMatchSource = source;
                // T5: hero card 出現動畫 — 只在 is_favorite 時觸發（card 才會 x-show=true）
                if (found.is_favorite && !this.showFavoriteActresses) {
                    var self = this;
                    this.$nextTick(function () {
                        requestAnimationFrame(function () {
                            var heroEl = document.querySelector('.hero-card');
                            window.ShowcaseAnimations?.playHeroCardAppear?.(heroEl);
                        });
                    });
                }
            } else if (source === 'metadata') {
                this._isPreciseActressMatch = true;
                this._matchedActress = { name: capturedTerm, is_favorite: false };
                this._preciseMatchSource = source;
            } else {
                this._clearPreciseMatch();
            }
        },

        // --- 44a: 女優模式核心方法 ---

        toggleActressMode() {
            if (this.lightboxOpen) this.closeLightbox();
            var self = this;
            var isEnteringActress = !this.showFavoriteActresses;
            var oldMode = isEnteringActress ? (this.mode || 'grid') : 'actress';
            var newMode = isEnteringActress ? 'actress' : (this.mode || 'grid');
            var gen = ++this._animGeneration;

            // Codex P1: 抽出 callback body 作 fallback；若 playModeCrossfade 不可用直接同步呼叫
            var flipAndFadeIn = function () {
                if (self._animGeneration !== gen) return;
                // 翻轉（觸發 x-if 重新掛載 DOM）
                self.showFavoriteActresses = isEnteringActress;
                var needEntry = false;
                if (isEnteringActress) {
                    self._clearPreciseMatch();
                    if (_actresses.length === 0) {
                        self.loadActresses();
                    } else {
                        needEntry = true;
                    }
                } else {
                    needEntry = true;
                    var searchTerm = self.search.trim();
                    if (searchTerm) {
                        self._checkPreciseActressMatch(searchTerm, 'manual');
                    }
                }
                // Phase 2: $nextTick 後 fade-in 新容器
                var gen2 = ++self._animGeneration;
                self.$nextTick(function () {
                    if (self._animGeneration !== gen2) return;
                    var newSelector = newMode === 'actress' ? '.actress-grid'
                        : newMode === 'table' ? '.showcase-table-wrapper'
                        : newMode === 'list' ? '.showcase-list-wrapper'
                        : '.showcase-grid';
                    var newEl = document.querySelector(newSelector);
                    // Codex P2: reduced-motion / gsap missing 由 helper 內 shouldSkip / typeof 守衛處理
                    window.ShowcaseAnimations?.playContainerFadeIn?.(newEl);
                    if (needEntry) {
                        var grid = self._getActiveGrid();
                        window.ShowcaseAnimations?.playEntry?.(grid);
                    }
                });
                self.saveState();
            };

            var fade = window.ShowcaseAnimations && window.ShowcaseAnimations.playModeCrossfade;
            if (typeof fade === 'function') {
                fade.call(window.ShowcaseAnimations, oldMode, null, null, {
                    onOldFadeComplete: flipAndFadeIn
                });
            } else {
                // P1 fallback: animations.js 不可用 → 直接同步翻轉 + 進入 fade-in
                flipAndFadeIn();
            }
        },

        async loadActresses() {
            this.actressLoading = true;
            try {
                var resp = await fetch('/api/actresses');
                if (!resp.ok) {
                    _actresses.splice(0, _actresses.length);
                    _filteredActresses.splice(0, _filteredActresses.length);
                    this.actressCount = 0;
                    this.filteredActressCount = 0;
                    return;
                }
                var data = await resp.json();
                if (!data.success) {
                    _actresses.splice(0, _actresses.length);
                    _filteredActresses.splice(0, _filteredActresses.length);
                    this.actressCount = 0;
                    this.filteredActressCount = 0;
                    return;
                }
                var acts = data.actresses || [];
                _setActresses(acts);
                // 45: alias map（冪等，init 可能已載入）
                await _loadAliasMap();
                this.applyActressFilterAndSort();
                // 卡片進場動畫
                var gen = ++this._animGeneration;
                var self = this;
                this.$nextTick(function () { requestAnimationFrame(function () {
                    if (self._animGeneration !== gen) return;
                    var grid = self._getActiveGrid();
                    window.ShowcaseAnimations?.playEntry?.(grid);
                }); });
            } catch (e) {
                console.error('[Showcase] Failed to fetch actresses:', e);
                _actresses.splice(0, _actresses.length);
                _filteredActresses.splice(0, _filteredActresses.length);
                this.actressCount = 0;
                this.filteredActressCount = 0;
            } finally {
                this.actressLoading = false;
                _setActressesLoaded(true);
            }
        },

        applyActressFilterAndSort() {
            // 1. Filter
            var q = this.actressSearch.trim();
            var filtered = _actresses.slice();
            if (q) {
                var ql = q.toLowerCase();
                filtered = _actresses.filter(function (a) {
                    var group = _nameToGroup[a.name] || [a.name];
                    return group.some(function(n) { return n && n.toLowerCase().includes(ql); });
                });
            }

            // 2. Sort
            var cupRank = { A:1, B:2, C:3, D:4, E:5, F:6, G:7, H:8, I:9, J:10, K:11 };
            var sort = this.actressSort;
            var order = this.actressOrder;
            filtered = filtered.slice().sort(function (a, b) {
                if (sort === 'name') {
                    var cmp = a.name.localeCompare(b.name, 'ja');
                    return order === 'asc' ? cmp : -cmp;
                }
                var va, vb;
                if (sort === 'video_count') {
                    va = a.video_count || 0;
                    vb = b.video_count || 0;
                } else if (sort === 'added_at') {
                    va = a.created_at || '';
                    vb = b.created_at || '';
                } else if (sort === 'age') {
                    va = a.age != null ? a.age : Infinity;
                    vb = b.age != null ? b.age : Infinity;
                } else if (sort === 'height') {
                    var ha = parseInt(a.height);
                    var hb = parseInt(b.height);
                    va = isNaN(ha) ? Infinity : ha;
                    vb = isNaN(hb) ? Infinity : hb;
                } else if (sort === 'cup') {
                    va = cupRank[a.cup] || Infinity;
                    vb = cupRank[b.cup] || Infinity;
                } else {
                    va = a.video_count || 0;
                    vb = b.video_count || 0;
                }
                // null-last：Infinity 值永遠排最後（不因 desc 翻轉）
                if (va === Infinity && vb === Infinity) return 0;
                if (va === Infinity) return 1;
                if (vb === Infinity) return -1;
                if (order === 'asc') {
                    return va < vb ? -1 : va > vb ? 1 : 0;
                } else {
                    return va > vb ? -1 : va < vb ? 1 : 0;
                }
            });

            // 3. Update state
            _setFilteredActresses(filtered);
            this.actressCount = _actresses.length;
            this.filteredActressCount = _filteredActresses.length;
            this.paginatedActresses = _filteredActresses.slice();  // CD-9: 全量，不分頁
        },

        onActressSearchChange() {
            this.applyActressFilterAndSort();
        },

        onActressSortChange() {
            this._sortWithFlip(() => {
                this.applyActressFilterAndSort();
            });
        },

        toggleActressOrder() {
            this._sortWithFlip(() => {
                this.actressOrder = this.actressOrder === 'asc' ? 'desc' : 'asc';
                this.applyActressFilterAndSort();
            });
        },

        // --- 44a: 女優 Lightbox 方法 ---

        openActressLightbox(index) {
            if (this.lightboxCloseTimer) {
                clearTimeout(this.lightboxCloseTimer);
                this.lightboxCloseTimer = null;
            }
            if (this._lightboxAnimating) return;
            if (this.lightboxOpen && this.actressLightboxIndex === index) return;

            // 若已開啟（切換女優）
            if (this.lightboxOpen && this.actressLightboxIndex !== index) {
                _killLightboxTimelines({ killOpen: false, killSwitch: true });
                var direction = index > this.actressLightboxIndex ? 'next' : 'prev';
                this._setActressLightboxIndex(index);
                this.actressLightboxSource = 'grid';   // T5: 切換女優分支
                // T3: fire-and-forget 即時查 aliases
                this._fetchLiveAliases(this.currentLightboxActress?.name, index);
                var lbGen = ++this._lightboxGeneration;
                var self = this;
                this.$nextTick(function () {
                    if (self._lightboxGeneration !== lbGen) return;
                    var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                    if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                        self._lightboxAnimating = true;
                        var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, direction, {
                            onComplete: function () { self._lightboxAnimating = false; }
                        });
                        if (!tl) self._lightboxAnimating = false;
                    }
                });
                return;
            }

            // ★ ghost fly — 在 state 變更前捕獲 fromRect
            var fromRect = null;
            var coverSrc = null;
            if (!this.lightboxOpen) {
                var gridEl = this._getActiveGrid();
                if (gridEl) {
                    var actress = _filteredActresses[index];
                    var cardEl = actress
                        ? gridEl.querySelector('[data-flip-id="actress:' + CSS.escape(actress.name) + '"]')
                        : null;
                    if (cardEl) {
                        var imgEl = cardEl.querySelector('.actress-card-photo img');
                        if (imgEl && imgEl.complete && imgEl.getBoundingClientRect().width > 0) {
                            fromRect = imgEl.getBoundingClientRect();
                            coverSrc = imgEl.src;
                        }
                    }
                }
            }

            this._setActressLightboxIndex(index);
            this.actressLightboxSource = 'grid';   // T5: 首次進入分支
            var lightboxElPre = document.querySelector('.showcase-lightbox');
            if (lightboxElPre) lightboxElPre.classList.add('gsap-animating');
            this.lightboxOpen = true;
            document.body.classList.add('overflow-hidden');
            // T3: fire-and-forget 即時查 aliases
            this._fetchLiveAliases(this.currentLightboxActress?.name, index);

            var self = this;
            var lbGen = ++this._lightboxGeneration;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var lightboxEl = document.querySelector('.showcase-lightbox');
                if (!lightboxEl) return;

                if (fromRect && window.GhostFly && window.GhostFly.playGridToLightbox) {
                    self._lightboxAnimating = true;
                    window.GhostFly.playGridToLightbox(fromRect, lightboxEl, {
                        coverSrc: coverSrc,
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (window.ShowcaseAnimations && window.ShowcaseAnimations.playLightboxOpen) {
                        window.ShowcaseAnimations.playLightboxOpen(lightboxEl, { skipCover: true });
                    }
                } else {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations?.playLightboxOpen?.(lightboxEl, {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        closeActressLightbox() {
            this.closeLightbox();
        },

        prevActressLightbox() {
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            if (this.actressLightboxIndex <= 0) return;
            var newIdx = this.actressLightboxIndex - 1;
            this._setActressLightboxIndex(newIdx);
            // P2 Codex: 方向鍵切換也要 fetch live alias
            this._fetchLiveAliases(this.currentLightboxActress?.name, newIdx);

            var lbGen = ++this._lightboxGeneration;
            var self = this;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'prev', {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        nextActressLightbox() {
            _killLightboxTimelines();
            this._lightboxAnimating = false;
            var lbEl = document.querySelector('.showcase-lightbox');
            if (lbEl) lbEl.classList.remove('gsap-animating');

            if (this.actressLightboxIndex >= _filteredActresses.length - 1) return;
            var newIdx = this.actressLightboxIndex + 1;
            this._setActressLightboxIndex(newIdx);
            // P2 Codex: 方向鍵切換也要 fetch live alias
            this._fetchLiveAliases(this.currentLightboxActress?.name, newIdx);

            var lbGen = ++this._lightboxGeneration;
            var self = this;
            this.$nextTick(function () {
                if (self._lightboxGeneration !== lbGen) return;
                var contentEl = document.querySelector('.showcase-lightbox .lightbox-content');
                if (contentEl && window.ShowcaseAnimations?.playLightboxSwitch) {
                    self._lightboxAnimating = true;
                    var tl = window.ShowcaseAnimations.playLightboxSwitch(contentEl, 'next', {
                        onComplete: function () { self._lightboxAnimating = false; }
                    });
                    if (!tl) self._lightboxAnimating = false;
                }
            });
        },

        // --- 44a T4: Lightbox chips + metadata helpers ---

        _chipsLimit() {
            return window.innerWidth >= 768 ? 10 : 6;
        },

        _actressCoreMetadata() {
            var a = this.currentLightboxActress; if (!a) return '';
            var parts = [];
            if (typeof a.video_count === 'number') {
                parts.push(a.video_count + window.t('showcase.unit.films'));
            }
            if (a.age) parts.push(a.age + window.t('search.unit.age'));
            if (a.birth) parts.push(a.birth);
            if (a.height) parts.push(a.height);
            if (a.cup) parts.push(a.cup + window.t('search.unit.cup'));
            if (a.bust && a.waist && a.hip) parts.push(a.bust + '-' + a.waist + '-' + a.hip);
            return parts.join(' · ');
        },

        // --- 44c T2: Actress card footer helpers ---

        _actressCardMiddle(actress) {
            if (!actress) return '';
            var sort = this.actressSort;
            if (sort === 'video_count') {
                return (actress.video_count || 0) + window.t('showcase.unit.films');
            }
            if (sort === 'cup') {
                return actress.cup ? actress.cup + window.t('search.unit.cup') : '';
            }
            if (sort === 'height') {
                return actress.height || '';
            }
            return '';
        },

        _actressHoverInfo(actress) {
            if (!actress) return '';
            var parts = [];
            if (actress.height) parts.push(actress.height);
            if (actress.cup) parts.push(actress.cup + window.t('search.unit.cup'));
            if (actress.bust && actress.waist && actress.hip) {
                parts.push(actress.bust + '-' + actress.waist + '-' + actress.hip);
            }
            return parts.join(' · ');
        },

        _allInfoChips() {
            var a = this.currentLightboxActress; if (!a) return [];
            return [].concat(a.tags || [], [a.hometown, a.nickname, a.agency, a.hobby, a.debut_work]).filter(Boolean);
        },

        _visibleAliases() {
            var all = this.currentLightboxActress?.aliases || [];
            return this._actressChipsExpanded.aliases ? all : all.slice(0, this._chipsLimit());
        },

        _aliasesOverflow() {
            return Math.max(0, (this.currentLightboxActress?.aliases || []).length - this._chipsLimit());
        },

        _visibleInfoChips() {
            var all = this._allInfoChips();
            return this._actressChipsExpanded.info ? all : all.slice(0, this._chipsLimit());
        },

        _infoChipsOverflow() {
            return Math.max(0, this._allInfoChips().length - this._chipsLimit());
        },

        _visibleVideoTags() {
            var tags = (this.currentLightboxVideo?.tags || '').split(',').filter(function(t) { return t.trim(); });
            return this._videoChipsExpanded ? tags : tags.slice(0, this._chipsLimit());
        },

        _videoTagsOverflow() {
            var tags = (this.currentLightboxVideo?.tags || '').split(',').filter(function(t) { return t.trim(); });
            return Math.max(0, tags.length - this._chipsLimit());
        },

        // --- 44a T5: Actress CRUD ---

        async addFavoriteActress() {
            if (this._addingActress || !this._addActressName.trim()) return;
            this._addingActress = true;
            try {
                const resp = await fetch('/api/actresses/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: this._addActressName.trim() }),
                });
                const data = await resp.json();
                if (resp.status === 409) {
                    this.showToast(window.t('showcase.actress.addDuplicate'), 'info');
                } else if (resp.status === 404) {
                    this.showToast(window.t('showcase.actress.addNotFound'), 'error');
                } else if (resp.status === 504) {
                    this.showToast(window.t('showcase.actress.addTimeout'), 'error');
                } else if (data.success) {
                    _actresses.push(data.actress);
                    this.applyActressFilterAndSort();
                    this._addDropdownOpen = false;
                    this.showToast(window.t('showcase.actress.addSuccess'), 'success');
                } else {
                    this.showToast(window.t('showcase.actress.addNotFound'), 'error');
                }
            } catch (e) {
                this.showToast(window.t('showcase.actress.addNotFound'), 'error');
            } finally {
                this._addingActress = false;
                this._addActressName = '';
            }
        },

        async addFavoriteFromSearch() {
            if (this._favoriteHeartLoading || this._matchedActress?.is_favorite) return;
            this._favoriteHeartLoading = true;
            var capturedName = this._matchedActress?.name;
            if (!capturedName) { this._favoriteHeartLoading = false; return; }
            try {
                var resp = await fetch('/api/actresses/favorite', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: capturedName })
                });
                if (!this._matchedActress || this._matchedActress.name !== capturedName) return;
                if (resp.status === 200 || resp.status === 409) {
                    var data = await resp.json();
                    var actress = data.actress || data;
                    actress.is_favorite = true;
                    this._matchedActress = actress;
                    if (!_actresses.find(function(a) { return a.name === actress.name; })) {
                        _actresses.push(actress);
                        this.applyActressFilterAndSort();
                    }
                    if (resp.status === 200) {
                        this.showToast(window.t('showcase.actress.addSuccess'), 'success');
                    } else {
                        this.showToast(window.t('showcase.actress.addDuplicate'), 'info');
                    }
                } else if (resp.status === 404) {
                    this.showToast(window.t('showcase.actress.addNotFound'), 'error');
                } else {
                    this.showToast(window.t('showcase.actress.addTimeout'), 'error');
                }
            } catch (err) {
                this.showToast(window.t('showcase.actress.addTimeout'), 'error');
            } finally {
                this._favoriteHeartLoading = false;
            }
        },

        // T3.3: Remove Actress fluent-modal 三段路徑
        openRemoveActressModal() {
            if (!this.currentLightboxActress) return;
            this._pendingRemoveActressName = this.currentLightboxActress.name;
            this.removeActressModalOpen = true;
        },

        cancelRemoveActressModal() {
            this.removeActressModalOpen = false;
            this._pendingRemoveActressName = null;
        },

        async confirmRemoveActress() {
            const name = this._pendingRemoveActressName;
            if (!name) {
                this.removeActressModalOpen = false;
                return;
            }
            this._removeActressLoading = true;
            try {
                const resp = await fetch(`/api/actresses/${encodeURIComponent(name)}`, {
                    method: 'DELETE',
                });
                const data = await resp.json();
                if (data.success) {
                    const idx = _actresses.findIndex(a => a.name === name);
                    if (idx >= 0) _actresses.splice(idx, 1);
                    this.applyActressFilterAndSort();
                    // stale guard: lightbox switched to a different actress during request
                    if (this.currentLightboxActress?.name !== name) {
                        this.showToast(window.t('showcase.actress.removeSuccess'), 'success');
                    } else {
                        this.closeActressLightbox();
                        this.showToast(window.t('showcase.actress.removeSuccess'), 'success');
                        var searchTerm = this.search.trim();
                        if (searchTerm) {
                            this._checkPreciseActressMatch(searchTerm, 'manual');
                        }
                    }
                } else {
                    this.showToast(data.error || 'Error', 'error');
                }
            } catch (e) {
                this.showToast('Error', 'error');
            } finally {
                this._removeActressLoading = false;
                this.removeActressModalOpen = false;
                this._pendingRemoveActressName = null;
            }
        },

        // --- 44c T7: Search actress films（49a-T7：跨模式 Ghost Fly 動畫）---
        async searchActressFilms(actressName, fromEl) {
            if (!actressName) return;
            if (this._ghostFlyInFlight) return;   // CD-13: 連點保護
            var self = this;
            var wasActressMode = this.showFavoriteActresses;

            try {
                // 捕獲來源 rect / coverSrc（必須在 closeLightbox / state 變更前）
                var fromRect = null;
                var coverSrc = null;
                if (wasActressMode && fromEl) {
                    var fromImg = fromEl.closest('.actress-card')?.querySelector('.actress-card-photo img')
                        || fromEl.closest('.showcase-lightbox')?.querySelector('.lightbox-cover img');
                    if (fromImg) {
                        fromRect = fromImg.getBoundingClientRect();
                        coverSrc = fromImg.src;
                    }
                }

                if (this.lightboxOpen) this.closeLightbox();
                if (wasActressMode) {
                    this.showFavoriteActresses = false;
                    this.actressSearch = '';
                }
                this.search = actressName;
                this._animateFilter();

                // 非女優模式 / 無 fromEl / 無 coverSrc → fallback
                if (!wasActressMode || !fromRect || !coverSrc) {
                    this._checkPreciseActressMatch(actressName, 'metadata');
                    if (wasActressMode) {
                        var gen0 = ++this._animGeneration;
                        this.$nextTick(function () {
                            if (self._animGeneration !== gen0) return;
                            window.ShowcaseAnimations?.playModeCrossfade?.('actress', self.mode);
                            if (self.mode === 'grid') {
                                var grid0 = self._getActiveGrid();
                                window.ShowcaseAnimations?.playEntry?.(grid0);
                            }
                        });
                    }
                    return;
                }

                // === Ghost Fly 主流程 ===
                this._ghostFlyInFlight = true;
                var gen = ++this._animGeneration;

                // 淡出女優 grid
                window.ShowcaseAnimations?.playModeCrossfade?.('actress', null, null, {
                    onOldFadeComplete: function () {}
                });
                // 影片 grid 淡入
                this.$nextTick(function () {
                    if (self._animGeneration !== gen) return;
                    var newEl = document.querySelector('.showcase-grid');
                    window.ShowcaseAnimations?.playContainerFadeIn?.(newEl);
                    window.ShowcaseAnimations?.playEntry?.(self._getActiveGrid());
                });

                self._isPreciseActressMatch = false;

                await self._checkPreciseActressMatch(actressName, 'metadata');

                if (self._animGeneration !== gen) {
                    self._ghostFlyInFlight = false;
                    return;
                }

                // 等 hero card DOM render（最多 500ms 輪詢）
                var heroCardEl = null;
                var TIMEOUT = 500;
                var elapsed = 0;
                var interval = 30;
                await new Promise(function (resolve) {
                    var checker = setInterval(function () {
                        elapsed += interval;
                        var hero = document.querySelector('.hero-card');
                        if (hero && hero.getBoundingClientRect().width > 0) {
                            heroCardEl = hero;
                            clearInterval(checker);
                            resolve();
                        } else if (elapsed >= TIMEOUT) {
                            clearInterval(checker);
                            resolve();
                        }
                    }, interval);
                });

                // 再次 stale 檢查
                if (self._animGeneration !== gen) {
                    self._ghostFlyInFlight = false;
                    return;
                }

                // CD-12: 降級條件
                var canMainFlow = heroCardEl
                    && self._isPreciseActressMatch
                    && self._matchedActress
                    && self._matchedActress.is_favorite !== false
                    && coverSrc;

                var doFallback = function () {
                    self._ghostFlyInFlight = false;
                    if (fromEl) {
                        var pulseTarget = fromEl.closest('.actress-card')?.querySelector('.actress-card-photo img')
                            || fromEl.closest('.showcase-lightbox')?.querySelector('.lightbox-cover img');
                        window.ShowcaseAnimations?.playSourcePulse?.(pulseTarget);
                    }
                };

                if (canMainFlow) {
                    if (typeof window.GhostFly?.playActressToHeroCard !== 'function') {
                        doFallback();
                        return;
                    }
                    window.GhostFly.playActressToHeroCard(fromRect, heroCardEl, {
                        coverSrc: coverSrc,
                        onComplete: function () { self._ghostFlyInFlight = false; },
                        onFallback: function () { self._ghostFlyInFlight = false; }
                    });
                } else {
                    doFallback();
                }
            } catch (e) {
                self._ghostFlyInFlight = false;
                console.warn('[T7][searchActressFilms]', e);
            }
        },

        // 49a-T3: 開啟 Lightbox 時 async fetch 最新 aliases（Scanner SSOT）
        async _fetchLiveAliases(name, expectedIndex) {
            if (!name) return;
            var capturedName = name;
            var self = this;
            try {
                var resp = await fetch('/api/actress-aliases/' + encodeURIComponent(capturedName), {
                    signal: AbortSignal.timeout(3000)
                });
                if (resp.status === 200) {
                    var data = await resp.json();
                    // Stale-check
                    if (!self.lightboxOpen) return;
                    if (self.currentLightboxActress?.name !== capturedName) return;
                    if (expectedIndex !== null && expectedIndex !== undefined
                        && self.actressLightboxIndex !== expectedIndex) return;
                    var newAliases = (data && data.group && data.group.aliases) || [];
                    self.currentLightboxActress = Object.assign({}, self.currentLightboxActress, {
                        aliases: newAliases
                    });
                }
                // 404 / 5xx → 保留 snapshot，靜默
            } catch (e) {
                if (window.console && console.warn) console.warn('[T3] alias live fetch failed:', e);
            }
        },

    };
}
