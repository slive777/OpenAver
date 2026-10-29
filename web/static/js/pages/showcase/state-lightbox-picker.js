/**
 * state-lightbox-picker.js — Showcase ESM（149a-T3）
 *
 * 女優換圖挑選器：SSE 候選卡串流、hover 預覽、選圖/上傳、per-run AbortController
 * generation guard。從 state-lightbox.js 拆出，逐字搬移，見 plan-149a.md CD-149a-1。
 */

import { waitForMount } from '@/shared/dom-timing.js';
import { computeMaskDragRoom, MASK_MIN_DRAG_ROOM } from '@/shared/mask-geometry.js';
import { syncActressFields } from '@/shared/actress-sync.js';
import { addSeen, buildCandidatesUrl } from '@/shared/picker-seen.js';

export function stateLightboxPicker() {
    // 供 BurstPicker.playPickerBurst/Float/HoverIn/HoverOut/ExitAll 使用
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

        _pickerOpen: false,
        _candidates: [],
        _pickerLoading: false,
        _pickerSelected: false,
        _pickerCurrentSource: null,
        _pickerFloatTweens: [],
        _pickerRunId: 0,
        // 🔄 輪替序號（CD-4）。歸零只在 openActressPicker 首開判別，
        // ⛔ 不進 _resetPicker——那也是 🔄 重抓路徑的一環，在 reset 清會抹掉剛 +1 的值。
        _pickerAttempt: 0,
        // 這一次換照片已看過的候選 id。只在 openActressPicker 首開分支歸零，
        // ⛔ 不進 _resetPicker（理由同 _pickerAttempt）。
        _pickerSeen: [],
        _pickerSSE: null,
        _pickerBurstFired: false,       // SSE 收齊後一次 burst（防 done/error 重複觸發）
        _pickerReadyAbort: null,        // _burstAllPickerCandidates waitForMount 的 per-run AbortController

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
        // 地方能寫。呼叫者恰為二：_refreshActressPhotoLoaded() 起手（本檔）、_resetMask()
        // （state-lightbox.js 核心）。
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

            // (CD-4)：🔴 必須在 _resetPicker()（下方會把 _pickerOpen 翻 false）
            // 之前讀 _pickerOpen 判別首開/重抓——換女優必經關→開，歸零由結構保證。
            if (this._pickerOpen) { this._pickerAttempt++; }   // 🔄 重抓（同一 picker session）
            else { this._pickerAttempt = 0; this._pickerSeen = []; }   // 首開（含換女優後首開）→ 主名重來、看過集合歸零

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

            // waitForMount 等候選卡 mount 取代 $nextTick（CD-3/CD-3a）。predicate 用
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
            // (CD-5)：0 不帶參數（首開 URL 與 0.12.3 逐位一致）；
            // 顯式 > 0 而非 truthiness（0 是合法值，gotchas「|| 吞 numeric 0」）
            const url = buildCandidatesUrl(name, this._pickerAttempt, this._pickerSeen);
            const sse = new EventSource(url);
            this._pickerSSE = sse;
            this._pickerBurstFired = false;
            // per-run readiness abort（_resetPicker / close / 換 run 時 abort → observer disconnect）
            this._pickerReadyAbort?.abort();
            this._pickerReadyAbort = new AbortController();

            sse.addEventListener('candidate', (e) => {
                if (this._pickerRunId !== runId) { sse.close(); return; }
                try {
                    const candidate = JSON.parse(e.data);
                    this._pickerSeen = addSeen(this._pickerSeen, candidate.id);
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
                // 🔴 gate：本行受上方 stale early-return 保護（「已切走 → 同步完
                // 資料就 return」），與 _uploadActressPhoto 的 #6 下半是同一個機制——上方 fetch 的
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
            // ⛔ 不清 _pickerAttempt——本函式也是 🔄 重抓路徑的一環
            // （openActressPicker 重抓分支會呼叫），在此清會抹掉剛 +1 的值。
            this._pickerOpen = false;
            this._pickerLoading = false;
            this._pickerSelected = false;
            this._candidates = [];
            this._pickerCurrentSource = null;
            this._pickerBurstFired = false;
            // (CD-3a)：abort in-flight readiness observer（冪等）。_resetPicker 是所有 teardown
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
    };
}
