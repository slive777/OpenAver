/**
 * media-probe-reopen.js — 設定頁「瀏覽」分頁：影片資訊讀取提醒重開列（TASK-198a-T5）
 *
 * Alpine.data('mediaProbeReopen')；不進 mergeState；外求 0（不碰 form／showToast／PUT /api/config）。
 * 所有 key（含方法）一律 mp 前綴（巢狀 x-data 漏定義的 key 會靜默讀到父層 settings 的同名值）。
 *
 * 對外名單（模板照名單綁）：mpDismissed／mpReopened／mpBusy；mpVisible()、mpReopen()
 * 狀態只在後端 app_meta：GET／POST /api/media-probe/…。
 */

const BASE = '/api/media-probe';

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

export function mediaProbeReopen() {
    return {
        mpDismissed: false,
        mpReopened: false,
        mpBusy: false,

        async init() {
            const data = await mpRequest(BASE + '/status');
            if (data === null) {
                console.warn('[media-probe] status request failed');
                return;
            }
            this.mpDismissed = data.dismissed === true;
        },

        /** 只在「已按過不再提醒」或「剛重開成功」的當下出現。 */
        mpVisible() {
            return this.mpDismissed || this.mpReopened;
        },

        async mpReopen() {
            if (this.mpBusy) return;
            this.mpBusy = true;
            try {
                const data = await mpRequest(BASE + '/settings', { dismissed: false });
                if (data === null) {
                    console.warn('[media-probe] reopen request failed');
                    const fresh = await mpRequest(BASE + '/status');
                    if (fresh !== null) this.mpDismissed = fresh.dismissed === true;
                    return;
                }
                this.mpDismissed = data.dismissed === true;
                this.mpReopened = !this.mpDismissed;
            } finally {
                this.mpBusy = false;
            }
        },
    };
}
