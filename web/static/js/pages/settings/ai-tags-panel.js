/**
 * ai-tags-panel.js — 設定頁「AI 標籤」分頁獨立 Alpine 元件（TASK-188c-T8b）
 *
 * Alpine.data('aiTagsPanel')；自有 key 一律 aiTags 前綴；不進 mergeState。
 * 外求恰 6（不複製父層 key）：form／isDirty／aiTab／showToast／
 *   aiTagsModelLists()／ensureProviderModels()。
 *
 * 對外名單（T9 照名單綁）：
 *   狀態：aiTagsStatus／aiTagsTestResult／aiTagsTestBusy／aiTagsBusy
 *   方法：panelMode()、modelOptions()、onProviderChange()、testDisabled()、runTest()、
 *         backfillAction()（回 {action, disabled, reason}）、startBackfill()、stopBackfill()、
 *         rebuildVisible()、rebuildDisabled()、rebuildBackfill()、statusLineText()、
 *         costLineText(kind)（kind ∈ 'backfill'|'rebuild'）、firstRunHint()
 */

import {
    panelMode,
    backfillAction,
    statusLine,
    pickTagsModel,
    costHint,
    formatUsd,
    buildTagsTestBody,
    testResultLine,
} from './ai-tags-logic.js';

const STATUS_URL = '/api/ai/tags/backfill/status';
const TEST_URL = '/api/ai/tags/test';
const BACKFILL_URL = '/api/ai/tags/backfill';
const REBUILD_URL = '/api/ai/tags/backfill/rebuild';
const STOP_URL = '/api/ai/tags/backfill/stop';
const POLL_MS = 1000;
/** 補完中 status 連續失敗上限（約 30 秒）後才停輪詢。 */
const POLL_FAIL_MAX = 30;

export function aiTagsPanel() {
    return {
        aiTagsStatus: null,
        aiTagsTestResult: '',
        aiTagsTestBusy: false,
        aiTagsBusy: false,
        aiTagsPollTimer: null,
        aiTagsGen: 0,
        aiTagsFailCount: 0,
        aiTagsDestroyed: false,

        init() {
            this.$watch('aiTab', (val) => {
                if (this.aiTagsDestroyed) return;
                if (val === 'tags') {
                    this.refreshStatus();
                } else {
                    this._aiTagsStopPoll();
                }
            });
            // 第一次打開開關：預選翻譯用的連線（載入設定時 isDirty 為 false，不動）
            this.$watch('form.aiTagsEnabled', (val) => {
                if (this.aiTagsDestroyed) return;
                if (val !== true || this.isDirty !== true) return;
                if (this.form.aiTagsProvider !== '') return;
                const tp = this.form.translateProvider;
                if (!Object.keys(this.aiTagsModelLists()).includes(tp)) return;
                this.form.aiTagsProvider = tp;
                this.onProviderChange();
            });
            if (this.aiTab === 'tags') {
                this.refreshStatus();
            }
        },

        destroy() {
            this._aiTagsStopPoll();
            this.aiTagsDestroyed = true;
            this.aiTagsGen++;
        },

        _aiTagsStopPoll() {
            if (this.aiTagsPollTimer !== null) {
                clearTimeout(this.aiTagsPollTimer);
                this.aiTagsPollTimer = null;
            }
        },

        /** 鏈式 setTimeout：上一次 status 處理完才排下一次（間隔 POLL_MS）。 */
        _aiTagsEnsurePoll() {
            if (this.aiTagsPollTimer !== null) return;
            this.aiTagsPollTimer = setTimeout(() => {
                this.aiTagsPollTimer = null;
                if (this.aiTagsDestroyed || this.aiTab !== 'tags') {
                    this._aiTagsStopPoll();
                    return;
                }
                this.refreshStatus();
            }, POLL_MS);
        },

        panelMode() {
            return panelMode(this.form);
        },

        /** 模型下拉選項＝該家既有清單 ∪ 目前已存的 aiTagsModel（清單元素為字串或 {name}）。 */
        modelOptions() {
            const provider = this.form.aiTagsProvider;
            if (!provider) return [];
            const list = this.aiTagsModelLists()[provider];
            const names = [];
            for (const item of Array.isArray(list) ? list : []) {
                const name = typeof item === 'string' ? item : (item && item.name);
                if (typeof name === 'string' && name && !names.includes(name)) names.push(name);
            }
            const cur = this.form.aiTagsModel;
            if (cur && !names.includes(cur)) names.push(cur);
            return names;
        },

        async onProviderChange() {
            const provider = this.form.aiTagsProvider;
            if (provider === '') {
                this.form.aiTagsModel = '';
            } else {
                const lists = this.aiTagsModelLists();
                // 換連線時 current 一律傳空字串，避免舊家模型名帶到新家
                this.form.aiTagsModel = pickTagsModel(provider, '', lists[provider] || []);
            }
            await this.ensureProviderModels(provider);
        },

        testDisabled() {
            return this.aiTagsTestBusy || this.form.aiTagsProvider === '';
        },

        backfillAction() {
            const r = backfillAction(this.aiTagsStatus, {
                dirty: Boolean(this.isDirty),
                enabled: Boolean(this.form.aiTagsEnabled),
            });
            if (this.aiTagsBusy && r.action !== 'stop') {
                return { ...r, disabled: true };
            }
            return r;
        },

        rebuildVisible() {
            const s = this.aiTagsStatus;
            return Boolean(this.form.aiTagsEnabled && s && !s.running && s.total > 0);
        },

        rebuildDisabled() {
            return Boolean(this.aiTagsBusy || this.isDirty);
        },

        statusLineText() {
            const desc = statusLine(this.aiTagsStatus);
            if (!desc || !desc.key) return '';
            let text = window.t(desc.key, desc.params || {});
            for (const extraKey of desc.extra || []) {
                text += window.t(extraKey, desc.params || {});
            }
            return text;
        },

        /** kind：'backfill'（還沒跑的 pending 部）或 'rebuild'（全庫 total 部）。 */
        costLineText(kind) {
            const s = this.aiTagsStatus;
            const n = s ? (kind === 'rebuild' ? s.total : s.pending) : 0;
            if (!(n > 0)) return '';
            const h = costHint(this.form.aiTagsProvider, this.form.aiTagsModel, n);
            if (!h) return '';
            return window.t('settings.ai.tags.cost_per1000', { per1000: formatUsd(h.per1000) })
                // eslint-disable-next-line local/no-cjk-literal -- [cjk-exempt: 兩句費用提示之間的中點分隔符，非 UI 文案]
                + '・'
                + window.t('settings.ai.tags.cost_total', { total: formatUsd(h.total), label: h.label });
        },

        firstRunHint() {
            if (!this.aiTagsStatus) return '';
            return window.t('settings.ai.tags.first_run_hint', { n: this.aiTagsStatus.pending });
        },

        async refreshStatus() {
            if (this.aiTagsDestroyed) return;
            if (this.aiTab !== 'tags') {
                this._aiTagsStopPoll();
                return;
            }
            const gen = ++this.aiTagsGen;
            let data = null;
            try {
                const res = await fetch(STATUS_URL);
                data = res.ok ? await res.json() : null;
            } catch {
                data = null;
            }
            if (gen !== this.aiTagsGen || this.aiTagsDestroyed) return;
            if (!data) {
                // 補完中短暫斷線：保留舊狀態，繼續排下一次；連續失敗滿 POLL_FAIL_MAX 才停
                if (this.aiTagsStatus?.running && this.aiTab === 'tags') {
                    this.aiTagsFailCount += 1;
                    if (this.aiTagsFailCount < POLL_FAIL_MAX) {
                        this._aiTagsEnsurePoll();
                        return;
                    }
                }
                this._aiTagsStopPoll();
                return;
            }
            this.aiTagsFailCount = 0;
            this.aiTagsStatus = data;
            // 請求在途時離開分頁：只更新狀態，不再排下一次
            if (data.running && this.aiTab === 'tags') {
                this._aiTagsEnsurePoll();
            } else {
                this._aiTagsStopPoll();
            }
        },

        async runTest() {
            if (this.testDisabled()) return;
            this.aiTagsTestBusy = true;
            this.aiTagsTestResult = '';
            try {
                const body = buildTagsTestBody(this.form);
                const res = await fetch(TEST_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!res.ok) {
                    this.aiTagsTestResult = window.t('settings.ai.tags.test_failed_generic');
                    this.showToast(window.t('settings.ai.tags.test_http_error'), 'error');
                } else {
                    let data = null;
                    try { data = await res.json(); } catch { data = null; }
                    const line = testResultLine(data);
                    this.aiTagsTestResult = window.t(line.key, line.params);
                }
            } catch {
                this.aiTagsTestResult = window.t('settings.ai.tags.test_failed_generic');
                this.showToast(window.t('settings.ai.tags.test_http_error'), 'error');
            } finally {
                this.aiTagsTestBusy = false;
            }
        },

        /** start／rebuild 共用：POST 後依回應 status 對應 toast，結束一律 refreshStatus。 */
        async _aiTagsPostAction(url) {
            this.aiTagsBusy = true;
            try {
                const res = await fetch(url, { method: 'POST' });
                let data = null;
                try { data = await res.json(); } catch { data = null; }
                if (!res.ok) {
                    this.showToast(window.t('settings.ai.tags.backfill_http_error'), 'error');
                } else if (data && data.status === 'not_enabled') {
                    this.showToast(window.t('settings.ai.tags.backfill_not_enabled'), 'error');
                } else if (data && data.status === 'not_configured') {
                    this.showToast(window.t('settings.ai.tags.test_not_configured'), 'error');
                }
            } catch {
                this.showToast(window.t('settings.ai.tags.backfill_http_error'), 'error');
            } finally {
                this.aiTagsBusy = false;
            }
            await this.refreshStatus();
        },

        /** 「補完全庫」與「繼續」是同一個端點，後端自己承接。 */
        async startBackfill() {
            const a = this.backfillAction();
            if (a.disabled || (a.action !== 'start' && a.action !== 'continue')) return;
            await this._aiTagsPostAction(BACKFILL_URL);
        },

        async stopBackfill() {
            try {
                await fetch(STOP_URL, { method: 'POST' });
            } catch {
                /* 靜默；接著 refresh */
            }
            await this.refreshStatus();
        },

        async rebuildBackfill() {
            if (this.rebuildDisabled()) return;
            const n = this.aiTagsStatus?.total || 0;
            // eslint-disable-next-line no-alert -- rebuildBackfill cost confirm, same shape as rebuildIndex confirm
            if (!confirm(window.t('settings.ai.tags.rebuild_confirm', { n }))) return;
            await this._aiTagsPostAction(REBUILD_URL);
        },
    };
}
