/**
 * state-custom-sources.js — 設定頁「自訂來源」獨立 Alpine 元件（TASK-165-T9）
 *
 * 官方獨立元件（Alpine.data('customSources')），不進 mergeState：自足、全部 key 以 customSrc 為前綴、
 * 元件內不讀父層任何 key（父層的來源清單、toast、啟用計數都不碰）。形狀照 shared/state-browse-dir.js。
 * 純函式（狀態→點／文案）在 custom-source-logic.js（T8）。
 */

import {
    customStatusToProbeState,
    customStatusIcon,
    describeCustomLine,
} from './custom-source-logic.js';

const API = '/api/custom-sources';
const POLL_MS = 2000;

function enc(id) {
    return encodeURIComponent(id);
}

export function customSources() {
    return {
        customSrcList: [],
        customSrcOpenId: null,
        customSrcBusyId: null,
        customSrcRemoveId: null,
        customSrcPollTimer: null,
        customSrcGen: 0,
        customSrcError: '',
        customSrcDestroyed: false,

        init() {
            this.customSrcRefresh();
        },

        destroy() {
            this.customSrcStopPoll();
            this.customSrcDestroyed = true;
            this.customSrcGen++;
        },

        customSrcStopPoll() {
            if (this.customSrcPollTimer !== null) {
                clearInterval(this.customSrcPollTimer);
                this.customSrcPollTimer = null;
            }
        },

        async customSrcRefresh() {
            if (this.customSrcDestroyed) return true;
            const gen = ++this.customSrcGen;
            let data = null;
            try {
                const res = await fetch(API);
                data = res.ok ? await res.json() : null;
            } catch {
                data = null;
            }
            if (gen !== this.customSrcGen) return true;
            if (!data || !Array.isArray(data.sources)) return false;
            this.customSrcList = data.sources.map((e) => ({ ...e }));
            if (this.customSrcOpenId !== null
                && !this.customSrcList.some((e) => e.id === this.customSrcOpenId)) {
                this.customSrcOpenId = null;
            }
            this.customSrcPollIfVerifying();
            return true;
        },

        customSrcPollIfVerifying() {
            const needPoll = this.customSrcList.some((e) => e.status === 'verifying');
            if (!needPoll) {
                this.customSrcStopPoll();
                return;
            }
            if (this.customSrcPollTimer === null) {
                this.customSrcPollTimer = setInterval(() => this.customSrcRefresh(), POLL_MS);
            }
        },

        customSrcStatus(entry) {
            return this.customSrcBusyId === entry.id ? 'verifying' : entry.status;
        },

        customSrcProbeState(status) {
            return customStatusToProbeState(status);
        },

        customSrcProbeIcon(status) {
            return customStatusIcon(status);
        },

        customSrcLine(entry) {
            return describeCustomLine({ ...entry, status: this.customSrcStatus(entry) }, window.t);
        },

        customSrcErrorText(reason) {
            if (reason === 'verify_busy') return window.t('settings.sources.custom_error_busy');
            if (reason === 'changed_during_verify') return window.t('settings.sources.custom_error_changed');
            return window.t('settings.sources.custom_error_generic');
        },

        /** 共用：送改動類請求，回 { ok, reason }；網路失敗 ok=false。 */
        async customSrcSend(url, init) {
            this.customSrcGen++;
            try {
                const res = await fetch(url, init);
                if (res.ok) {
                    let okBody = null;
                    try { okBody = await res.json(); } catch { okBody = null; }
                    return { ok: true, reason: '', body: okBody };
                }
                let body = null;
                try { body = await res.json(); } catch { body = null; }
                return { ok: false, reason: (body && body.reason) || '', body: null };
            } catch {
                return { ok: false, reason: '', body: null };
            }
        },

        customSrcToggleLine(id) {
            this.customSrcError = '';
            this.customSrcOpenId = this.customSrcOpenId === id ? null : id;
        },

        async customSrcToggle(id) {
            const entry = this.customSrcList.find((e) => e.id === id);
            if (!entry || this.customSrcBusyId === id || entry.status === 'verifying') return;
            if (entry.status !== 'passed') {
                this.customSrcToggleLine(id);
                return;
            }
            this.customSrcError = '';
            const r = await this.customSrcSend(`${API}/${enc(id)}/enabled`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: !entry.enabled }),
            });
            if (r.ok) {
                const on = r.body && typeof r.body.enabled === 'boolean' ? r.body.enabled : !entry.enabled;
                this.customSrcList = this.customSrcList.map((e) => (e.id !== id ? e : { ...e, enabled: on }));
            } else {
                this.customSrcOpenId = id;
                this.customSrcError = this.customSrcErrorText(r.reason === 'not_passed' ? '' : r.reason);
            }
            await this.customSrcSyncOrWarn(id);
        },

        /** 補打 GET 同步；失敗時保留已套用的結果，並在該來源說明列顯示同步失敗句（不覆蓋既有錯誤）。 */
        async customSrcSyncOrWarn(id) {
            const synced = await this.customSrcRefresh();
            if (synced === false && this.customSrcError === '') {
                this.customSrcOpenId = id;
                this.customSrcError = window.t('settings.sources.custom_error_generic');
            }
        },

        /** 以 verify 的 POST 回應整包換新該 entry（新陣列、以 id 比對）；之後的 GET 會再校正 enabled。 */
        customSrcApplyVerify(id, body) {
            if (!body || (body.status !== 'passed' && body.status !== 'failed')) return;
            this.customSrcList = this.customSrcList.map((e) => (e.id !== id ? e : {
                ...e,
                status: body.status,
                verified_at: body.verified_at,
                last_result: { total: body.total, failed: body.failed, cases: body.cases },
                enabled: typeof body.enabled === 'boolean' ? body.enabled : (body.status === 'failed' ? false : e.enabled),
            }));
        },

        async customSrcVerify(id) {
            if (this.customSrcBusyId !== null) return;
            this.customSrcBusyId = id;
            this.customSrcError = '';
            try {
                const r = await this.customSrcSend(`${API}/${enc(id)}/verify`, { method: 'POST' });
                if (r.ok) {
                    this.customSrcApplyVerify(id, r.body);
                } else {
                    this.customSrcOpenId = id;
                    this.customSrcError = this.customSrcErrorText(r.reason);
                }
            } finally {
                this.customSrcBusyId = null;
            }
            await this.customSrcSyncOrWarn(id);
        },

        customSrcOpenRemove(id) {
            this.customSrcRemoveId = id;
        },

        customSrcCloseRemove() {
            this.customSrcRemoveId = null;
        },

        customSrcRemoveBody() {
            const e = this.customSrcList.find((x) => x.id === this.customSrcRemoveId);
            return window.t('settings.sources.custom_remove_body', { name: e ? e.name : '' });
        },

        async customSrcConfirmRemove() {
            const id = this.customSrcRemoveId;
            if (id === null) return;
            this.customSrcRemoveId = null;
            this.customSrcError = '';
            const r = await this.customSrcSend(`${API}/${enc(id)}`, { method: 'DELETE' });
            if (r.ok) {
                if (this.customSrcOpenId === id) this.customSrcOpenId = null;
                this.customSrcList = this.customSrcList.filter((e) => e.id !== id);
            } else {
                this.customSrcOpenId = id;
                this.customSrcError = this.customSrcErrorText(r.reason);
            }
            await this.customSrcSyncOrWarn(id);
        },
    };
}
