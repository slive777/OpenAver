export function stateBatch() {
    return {
        // ===== T10: Missing NFO/Cover Enrich =====
        missingPillVisible: false,
        missingBothCount: 0,
        missingNfoCount: 0,
        missingCoverCount: 0,
        missingItems: [],           // [{file_path, number}]
        missingEnrichOffset: 0,     // batch offset
        missingEnrichSuccess: 0,
        missingEnrichFailed: 0,
        resumePillVisible: false,
        missingConfirmModalOpen: false,   // TASK-13: 大批量補完 confirm dialog 開關
        _enrichAbortController: null,

        // ===== TASK-94-T3: Scanner Enrich Fly 進度卡 + badge =====
        currentCard: null,          // {number, status, source, reason, coverSrc} | null
        enrichBadgeCount: 0,
        // ===== TASK-94-T8: 兩格待命位 + 延後飛 =====
        onDeckCard: null,           // {number, coverSrc} | null — 左待命格停駐的前一片命中封面
        _onDeckParkedAt: 0,         // TASK-94 Codex P1：onDeckCard park 時的 performance.now()，供最後一片 flush dwell 判斷
        _flushTimer: null,          // TASK-94 Codex P1：最後一片補足 dwell 的 setTimeout handle（cleanup/run-start 清）

        // ===== T10: Missing Pill Computed =====
        get missingPillLabel() {
            const parts = [];
            if (this.missingBothCount > 0) {
                parts.push(window.t('scanner.stats.missing_both_prefix') + ' ' + this.missingBothCount + window.t('scanner.stats.missing_suffix'));
            }
            if (this.missingNfoCount > 0) {
                parts.push(window.t('scanner.stats.missing_nfo_prefix') + ' ' + this.missingNfoCount + window.t('scanner.stats.missing_suffix'));
            }
            if (this.missingCoverCount > 0) {
                parts.push(window.t('scanner.stats.missing_cover_prefix') + ' ' + this.missingCoverCount + window.t('scanner.stats.missing_suffix'));
            }
            return parts.join(' ');
        },

        get missingEnrichButtonText() {
            if (this.state === 'enriching') {
                return '<span class="loading loading-spinner loading-sm"></span> ' + window.t('scanner.stats.missing_enrich_loading');
            }
            return '<i class="bi bi-file-earmark-plus"></i> ' + window.t('scanner.stats.missing_enrich_idle');
        },

        // ===== T10: Missing NFO/Cover Enrich Methods =====
        async checkMissing() {
            try {
                const resp = await fetch('/api/gallery/missing-check');
                const result = await resp.json();
                if (!result.success) return;
                const d = result.data;
                if (d.total_missing > 0) {
                    // TASK-13: 後端永遠回傳完整 items 清單；前端於 runMissingEnrich 內做 > 500 confirm gate
                    this.missingBothCount = d.missing_both || 0;
                    this.missingNfoCount = d.missing_nfo || 0;
                    this.missingCoverCount = d.missing_cover || 0;
                    this.missingItems = Array.isArray(d.items) ? d.items : [];
                    this.missingPillVisible = true;
                } else {
                    this.missingPillVisible = false;
                }
            } catch (e) {
                console.error('checkMissing failed:', e);
            }
        },

        async runMissingEnrich({ skipConfirm = false } = {}) {
            if (this.isGenerating || this.missingItems.length === 0) return;

            // TASK-13: 大批量 confirm gate — > 500 筆彈 modal，等用戶按確認才繼續
            if (!skipConfirm && this.missingItems.length > 500) {
                this.missingConfirmModalOpen = true;
                return;
            }

            this.state = 'enriching';
            this.missingEnrichOffset = 0;
            this.missingEnrichSuccess = 0;
            this.missingEnrichFailed = 0;
            this.enrichBadgeCount = 0;
            this.currentCard = null;
            this.onDeckCard = null;  // TASK-94-T8：run 開始 reset 待命格
            this._onDeckParkedAt = 0;
            this._clearFlushTimer();  // TASK-94 Codex P1：清掉上一個 run 殘留的 flush dwell timer
            this.progressStatus = window.t('scanner.stats.missing_enrich_loading');
            this.progressCurrent = 0;
            this.progressTotal = this.missingItems.length;
            this.clearLogs();

            const controller = new AbortController();
            this._enrichAbortController = controller;

            const items = this.missingItems.slice();  // snapshot

            try {
                while (this.missingEnrichOffset < items.length) {
                    const batch = items.slice(this.missingEnrichOffset, this.missingEnrichOffset + 20);

                    // Save remaining items to localStorage before each batch
                    localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));

                    let resp;
                    try {
                        resp = await fetch('/api/batch-enrich', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ items: batch, mode: 'fill_missing' }),
                            signal: controller.signal,
                        });
                    } catch (fetchErr) {
                        if (fetchErr.name === 'AbortError') {
                            // cleanup() already saved remaining items
                            return;
                        }
                        this.addLog('error', window.t('scanner.stats.missing_enrich_connection_failed', { message: fetchErr.message }));
                        this.flushLogs();
                        this.state = 'error';
                        this.currentCard = null;
                        this.onDeckCard = null;  // TASK-94-T8：error 路徑不殘留待命封面
                        // Save remaining
                        localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                        this.showToast(window.t('scanner.stats.missing_enrich_disconnect'), 'error');
                        return;
                    }

                    if (!resp.ok) {
                        const errText = await resp.text().catch(() => '');
                        this.addLog('error', window.t('scanner.stats.missing_enrich_batch_fail', { status: resp.status, error: errText }));
                        this.flushLogs();
                        this.state = 'error';
                        this.currentCard = null;
                        this.onDeckCard = null;  // TASK-94-T8：error 路徑不殘留待命封面
                        localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                        this.showToast(window.t('scanner.stats.missing_enrich_error'), 'error');
                        return;
                    }

                    // Read SSE stream
                    const reader = resp.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    let batchDone = false;

                    while (!batchDone) {
                        let readResult;
                        try {
                            readResult = await reader.read();
                        } catch (readErr) {
                            if (readErr.name === 'AbortError') return;
                            break;
                        }
                        const { done, value } = readResult;
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop();  // keep incomplete last line

                        for (const line of lines) {
                            if (!line.startsWith('data: ')) continue;
                            let event;
                            try {
                                event = JSON.parse(line.slice(6));
                            } catch { continue; }

                            if (event.type === 'progress') {
                                this.progressStatus = event.status || window.t('scanner.stats.missing_enrich_loading');
                                this.progressCurrent = this.missingEnrichOffset + (event.current || 0);
                                this.progressTotal = items.length;
                                this.currentCard = { number: event.number, status: 'searching', source: '', reason: '', coverSrc: '' };
                            } else if (event.type === 'result-item') {
                                // badge 在 handler 本體算，與動畫（T5 playInboundFly）解耦（G-5）
                                if (event.nfo_written || event.cover_written) {
                                    this.enrichBadgeCount++;
                                }
                                if (this.currentCard) {
                                    const status = this._resolveCardStatus(event.reason, event.success);
                                    this.currentCard.status = status;
                                    this.currentCard.reason = event.reason || '';
                                    if (status === 'hit' || status === 'no_cover') {
                                        this.currentCard.source = event.source_used || '';
                                    }
                                    if (status === 'hit') {
                                        this.currentCard.coverSrc = `/api/gallery/thumb?path=${encodeURIComponent(event.file_path)}&t=${Date.now()}`;
                                    }
                                    // TASK-94-T8：延後飛 — hit 且這輪真補了東西（CD-94-5）才進待命位；hit 但 no-op 不動待命格
                                    if (status === 'hit' && (event.nfo_written || event.cover_written)) {
                                        // 前一片待命格存在 → 先飛前一片（容器恆渲染、rect 恆有效，免 $nextTick，Codex T8-plan P1）
                                        if (this.onDeckCard) {
                                            this._flyOnDeck();
                                        }
                                        // 本片接手待命格；首次命中（onDeckCard 原為 null）不飛，僅塞待命格
                                        this.onDeckCard = { number: event.number, coverSrc: this.currentCard.coverSrc };
                                        this._onDeckParkedAt = performance.now();  // TASK-94 Codex P1：記 park 時間，供最後一片 flush dwell 判斷
                                    }
                                }
                                if (event.success) {
                                    this.missingEnrichSuccess++;
                                } else {
                                    this.missingEnrichFailed++;
                                }
                                // log reason-gate（U-2）：only error 記詳情，not_found/readonly 安靜不記
                                if (event.reason === 'error') {
                                    this.addLog('error', window.t('scanner.stats.missing_enrich_item_failed', { number: event.number || '', error: event.error || '' }));
                                }
                            } else if (event.type === 'log') {
                                this.addLog(event.level || 'info', event.message || '');
                            } else if (event.type === 'done') {
                                batchDone = true;
                            } else if (event.type === 'error') {
                                this.addLog('error', window.t('scanner.stats.missing_enrich_error_prefix', { message: event.message || '' }));
                                this.flushLogs();
                                this.state = 'error';
                                this.currentCard = null;
                                this.onDeckCard = null;  // TASK-94-T8：error 路徑不殘留待命封面
                                localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                                this.showToast(window.t('scanner.stats.missing_enrich_stream_error'), 'error');
                                return;
                            }
                        }
                    }

                    // P1 fix: only advance offset if batch actually completed (got 'done' SSE event)
                    if (!batchDone) {
                        this.state = 'error';
                        this.currentCard = null;
                        this.onDeckCard = null;  // TASK-94-T8：error 路徑不殘留待命封面
                        localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                        this.showToast(window.t('scanner.stats.missing_enrich_disconnect'), 'error');
                        return;
                    }

                    this.missingEnrichOffset += batch.length;
                    this.progressCurrent = this.missingEnrichOffset;
                }

                // All batches complete
                localStorage.removeItem('avlist_enrich_pending');
                // TASK-94-T8 / Codex P1：最後一片 flush 前補足可感知 dwell。
                // result-item(last) 與 done 常在同一 SSE chunk、client 同步處理（中間無
                // await reader.read() paint 邊界），若立即 _flyOnDeck 則最後封面「沒被 paint
                // 進左待命格就飛走」。以 performance.now() 記 park 時間，不足 MIN 則保持卡片
                // 可見（state 維持 'enriching'）用 setTimeout 補足後再飛＋收尾。
                // 飛用顯式 coverSrc（timer 觸發時 onDeckCard 可能已被清），故先 capture。
                const MIN_ONDECK_DWELL_MS = 550;
                const lastCover = this.onDeckCard ? this.onDeckCard.coverSrc : null;
                const finalizeRun = () => {
                    if (lastCover) {
                        this._flyCover(lastCover);  // 待命格容器恆渲染（state 仍 'enriching'）→ rect 有效
                    }
                    this.state = 'done';
                    this.onDeckCard = null;
                    this.currentCard = null;
                    this.enrichBadgeCount = 0;
                    this.progressStatus = window.t('scanner.stats.missing_enrich_done');
                    const summary = this.missingEnrichFailed > 0
                        ? window.t('scanner.stats.missing_enrich_toast_mixed', { success: this.missingEnrichSuccess, failed: this.missingEnrichFailed })
                        : window.t('scanner.stats.missing_enrich_toast_success', { success: this.missingEnrichSuccess });
                    this.showToast(summary, this.missingEnrichFailed > 0 ? 'warn' : 'success');
                    this.flushLogs();
                    this.checkMissing();
                };
                const parkedElapsed = this._onDeckParkedAt ? (performance.now() - this._onDeckParkedAt) : Infinity;
                if (lastCover && parkedElapsed < MIN_ONDECK_DWELL_MS) {
                    // dwell 不足：保持最後封面可見，補足剩餘時間後 finalize（timer 由 cleanup/run-start 清）
                    this._clearFlushTimer();
                    this._flushTimer = setTimeout(() => {
                        this._flushTimer = null;
                        finalizeRun();
                    }, MIN_ONDECK_DWELL_MS - parkedElapsed);
                } else {
                    finalizeRun();
                }

            } catch (e) {
                if (e.name === 'AbortError') return;
                console.error('runMissingEnrich error:', e);
                this._clearFlushTimer();  // TASK-94 Codex P1：防禦性清 flush timer（正常路徑 timer 只在 try 尾排程）
                this.state = 'error';
                this.currentCard = null;
                this.onDeckCard = null;  // TASK-94-T8：error 路徑不殘留待命封面
                localStorage.setItem('avlist_enrich_pending', JSON.stringify(items.slice(this.missingEnrichOffset)));
                this.showToast(window.t('scanner.stats.missing_enrich_interrupted'), 'error');
            } finally {
                if (this._enrichAbortController === controller) {
                    this._enrichAbortController = null;
                }
            }
        },

        // TASK-94-T3: reason enum → currentCard.status 純函式（供結構/單元驗證映射完整性）
        // reason 缺失（舊後端/未知值）fallback：success→'hit'、!success→'error'（防 undefined 卡在 searching）
        _resolveCardStatus(reason, success) {
            switch (reason) {
                case 'hit': return 'hit';
                case 'no_cover': return 'no_cover';
                case 'not_found': return 'not_found';
                case 'error': return 'error';
                case 'readonly': return 'readonly';
                default: return success ? 'hit' : 'error';
            }
        },

        // TASK-94-T8：飛出目前停在左待命格的封面（呼叫前必須先確認 this.onDeckCard 存在）。
        _flyOnDeck() {
            this._flyCover(this.onDeckCard.coverSrc);
        },

        // TASK-94-T8 / Codex P1：以顯式 coverSrc 飛出左待命格封面（不讀 onDeckCard，故最後一片
        // flush timer 觸發時即使 onDeckCard 已被清仍能飛正確封面）。fromEl 讀恆渲染固定尺寸容器
        // （enrichOnDeckCover，非內層 img）→ rect 與 coverSrc 皆與 Alpine reactive patch 時序無關，
        // 免 $nextTick（Codex T8-plan P1）。
        _flyCover(coverSrc) {
            const fromEl = this.$refs.enrichOnDeckCover;
            const toEl = document.getElementById('sidebar-showcase-link');
            if (window.GhostFly && typeof window.GhostFly.playInboundFly === 'function') {
                window.GhostFly.playInboundFly({
                    fromEl, coverSrc, toEl,
                    hold: 0, duration: 0.45,  // CD-94-9 bulk 變體
                    onLanding: () => this._pulseShowcaseLink(toEl),
                    // CD-94-13：不傳 fallback.toastFn（批次數百片 showToast 單槽會刷屏＋蓋真錯誤）
                });
            } else {
                this._pulseShowcaseLink(toEl);
            }
        },

        // TASK-94 Codex P1：清最後一片 flush dwell timer（run 開始 / 離頁 cleanup / 錯誤路徑呼叫，冪等）。
        _clearFlushTimer() {
            if (this._flushTimer) {
                clearTimeout(this._flushTimer);
                this._flushTimer = null;
            }
        },

        // TASK-94-T5：落地微光，比照 search/state/batch.js:97-102（純 class toggle，不跨頁 import）
        _pulseShowcaseLink(toEl) {
            if (!toEl) return;
            toEl.classList.remove('pulse-once');
            void toEl.offsetWidth; // force reflow
            toEl.classList.add('pulse-once');
        },

        resumeMissingEnrich() {
            // TASK-13: 不在此清 localStorage；交由 runMissingEnrich 成功完成時統一清除。
            // 若補完途中失敗或用戶取消，pending 保留、下次 reload 仍可恢復。
            // skipConfirm:true — 用戶前一次已明確按過「一鍵補完」，resume 視為延續既有意圖。
            this.resumePillVisible = false;
            this.runMissingEnrich({ skipConfirm: true });
        },

        // TASK-13: confirm modal 的確認按鈕 — 跳過 confirm gate、直接啟動補完
        async confirmLargeMissingEnrich() {
            this.missingConfirmModalOpen = false;
            await this.runMissingEnrich({ skipConfirm: true });
        },

        // TASK-13: confirm modal 的取消按鈕 — 只關 modal，不清 localStorage（保留 resume 恢復點）
        cancelLargeMissingEnrich() {
            this.missingConfirmModalOpen = false;
        },

        dismissResume() {
            this.resumePillVisible = false;
            localStorage.removeItem('avlist_enrich_pending');
            // P2 fix: re-fetch DB state to repopulate missingItems (不清空，讓 pill 按鈕可用)
            this.checkMissing();
        },
    };
}
