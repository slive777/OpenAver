/**
 * media-probe-reminder.js — 掃描頁「影片資訊讀取」提醒獨立元件（TASK-198a-T5）
 *
 * Alpine.data('mediaProbeReminder')；不進 mergeState；外求 0（不讀父層 key、不呼叫父層 showToast）。
 * 所有 key（含方法）一律 mp 前綴：巢狀 x-data 漏定義的 key 會靜默讀到父層 scanner 的同名值，
 * 前綴讓這種漏洞變成明顯的 undefined。
 *
 * 對外名單（模板照名單綁）：
 *   狀態：mpStatus／mpLater／mpBusy
 *   方法：mpView()、mpMessage()、mpProgressText()、mpChecked()、mpStart()、mpToggleReadonly(el)、
 *         mpDismiss()、mpLaterClick()、mpOnVisibility()
 * 數字一律用後端 GET /api/media-probe/status 給的值，前端不自算 N。
 */

import { reminderView, keepPollingAfterFailure } from './media-probe-reminder-logic.js';

const BASE = '/api/media-probe';
const POLL_MS = 2000;

async function mpRequest(url, body) {
    try {
        const res = await fetch(url, body === undefined ? undefined : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        return res.ok ? await res.json() : null;
    } catch {
        return null;
    }
}

export function mediaProbeReminder() {
    return {
        mpStatus: null,
        mpLater: false,
        mpBusy: false,
        mpPollTimer: null,
        mpGen: 0,
        mpDestroyed: false,

        init() {
            this.mpRefresh();
        },

        destroy() {
            this.mpDestroyed = true;
            this.mpGen++;
            this.mpStopPoll();
        },

        mpView() {
            return reminderView(this.mpStatus, { later: this.mpLater });
        },

        mpChecked() {
            return this.mpStatus?.include_readonly === true;
        },

        mpMessage() {
            const v = this.mpView();
            if (v.mode === 'unavailable') return window.t('scanner.media_probe.unavailable');
            if (v.mode === 'readonly_only') {
                return window.t('scanner.media_probe.readonly_only', { n: v.readonlyPending.toLocaleString() });
            }
            if (v.mode === 'running') return this.mpProgressText();
            return window.t('scanner.media_probe.reminder', { n: v.pending.toLocaleString() });
        },

        mpProgressText() {
            const v = this.mpView();
            return window.t('scanner.media_probe.progress', {
                done: v.done.toLocaleString(),
                total: v.total.toLocaleString(),
            });
        },

        mpStopPoll() {
            if (this.mpPollTimer !== null) {
                clearTimeout(this.mpPollTimer);
                this.mpPollTimer = null;
            }
        },

        /** 鏈式 setTimeout：同一時間至多一個 timer；分頁在背景時不排。 */
        mpSchedulePoll() {
            this.mpStopPoll();
            if (this.mpDestroyed || document.visibilityState === 'hidden') return;
            this.mpPollTimer = setTimeout(() => {
                this.mpPollTimer = null;
                this.mpRefresh();
            }, POLL_MS);
        },

        mpOnVisibility() {
            if (this.mpDestroyed) return;
            if (document.visibilityState === 'hidden') {
                this.mpStopPoll();
            } else if (this.mpStatus?.job?.running) {
                this.mpRefresh();
            }
        },

        mpApply(data) {
            this.mpStatus = data;
            if (data?.job?.running) {
                this.mpSchedulePoll();
            } else {
                this.mpStopPoll();
            }
        },

        /** GET status；回應世代不符或元件已銷毀就丟棄。失敗＝維持現狀、不重試。 */
        async mpRefresh() {
            if (this.mpDestroyed) return;
            const gen = ++this.mpGen;
            const data = await mpRequest(BASE + '/status');
            if (gen !== this.mpGen || this.mpDestroyed) return;
            if (data === null) {
                console.warn('[media-probe] status request failed');
                // 輪詢中的瞬斷：保留舊進度、照常排下一次；初次載入失敗不重試
                if (keepPollingAfterFailure(this.mpStatus)) {
                    this.mpSchedulePoll();
                } else {
                    this.mpStopPoll();
                }
                return;
            }
            this.mpApply(data);
        },

        /** POST 之後的共同出口：成功用回傳值；失敗重打 GET 回到後端真值。 */
        async mpPost(url, body) {
            this.mpBusy = true;
            try {
                const data = await mpRequest(url, body);
                if (data === null) {
                    console.warn('[media-probe] request failed:', url);
                }
                return data;
            } finally {
                this.mpBusy = false;
            }
        },

        async mpStart() {
            if (this.mpBusy) return;
            // 回 started／already_running／nothing_to_do／unavailable 都一律立刻重讀真值：
            // job 在跑 → mpApply 接上輪詢；其餘 → 畫面回到後端給的狀態
            await this.mpPost(BASE + '/start', {});
            await this.mpRefresh();
        },

        async mpToggleReadonly(el) {
            if (this.mpBusy) return;
            const data = await this.mpPost(BASE + '/settings', { include_readonly: el.checked });
            if (data === null) {
                await this.mpRefresh();
            } else {
                this.mpGen++;
                this.mpApply(data);
            }
            el.checked = this.mpChecked();
        },

        async mpDismiss() {
            if (this.mpBusy) return;
            const data = await this.mpPost(BASE + '/settings', { dismissed: true });
            if (data === null) {
                await this.mpRefresh();
            } else {
                this.mpGen++;
                this.mpApply(data);
            }
        },

        mpLaterClick() {
            this.mpLater = true;
        },
    };
}
