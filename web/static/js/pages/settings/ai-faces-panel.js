/**
 * ai-faces-panel.js — 人臉分頁獨立 Alpine 元件（TASK-187a-T5）
 *
 * Alpine.data('aiFacesPanel')；自有 key 一律 aiFaces 前綴。
 * 外求：form／isDirty／serverUrl()／showToast／aiTab（不複製父層 key）。
 */

import { copyText } from '@/shared/clipboard.js';
import {
    panelMode,
    statusLine,
    recomputeLine,
    recomputeAction,
    deleteRebuildVisible,
    CHECK_KEYS,
} from './ai-faces-logic.js';

const STATUS_URL = '/api/ai/faces/status';
const TEST_URL = '/api/ai/faces/test';
const RECOMPUTE_URL = '/api/ai/faces/recompute';
const REBUILD_URL = '/api/ai/faces/rebuild';
const STOP_URL = '/api/ai/faces/recompute/stop';
const POLL_MS = 1000;
/** 重算中 status 連續失敗上限（約 30 秒）後才停輪詢。 */
const POLL_FAIL_MAX = 30;

export function aiFacesPanel() {
    return {
        aiFacesStatus: null,
        aiFacesTestPassed: false,
        aiFacesTestResultHtml: '',
        aiFacesTestBusy: false,
        aiFacesBusy: false,
        aiFacesPollTimer: null,
        aiFacesSaveRefreshTimer: null,
        aiFacesGen: 0,
        aiFacesFailCount: 0,
        aiFacesDestroyed: false,

        init() {
            this.$watch('aiTab', (val) => {
                if (this.aiFacesDestroyed) return;
                if (val === 'faces') {
                    this.refreshStatus();
                } else {
                    this._aiFacesStopPoll();
                    this._aiFacesClearSaveRefresh();
                }
            });
            // 存檔成功（isDirty true→false）後後端可能自動開工；立刻取一次，
            // 若尚未 running 再於 ≤1.5s 補取一次（儲存鉤子是背景 thread）。
            this.$watch('isDirty', (dirty, prev) => {
                if (this.aiFacesDestroyed) return;
                if (dirty || prev !== true) return;
                if (this.aiTab !== 'faces') return;
                this._aiFacesAfterSaveRefresh();
            });
            if (this.aiTab === 'faces') {
                this.refreshStatus();
            }
        },

        destroy() {
            this._aiFacesStopPoll();
            this._aiFacesClearSaveRefresh();
            this.aiFacesDestroyed = true;
            this.aiFacesGen++;
        },

        _aiFacesStopPoll() {
            if (this.aiFacesPollTimer !== null) {
                clearTimeout(this.aiFacesPollTimer);
                this.aiFacesPollTimer = null;
            }
        },

        _aiFacesClearSaveRefresh() {
            if (this.aiFacesSaveRefreshTimer !== null) {
                clearTimeout(this.aiFacesSaveRefreshTimer);
                this.aiFacesSaveRefreshTimer = null;
            }
        },

        async _aiFacesAfterSaveRefresh() {
            this._aiFacesClearSaveRefresh();
            await this.refreshStatus();
            if (this.aiFacesDestroyed || this.aiTab !== 'faces') return;
            if (this.aiFacesStatus?.running) return;
            this.aiFacesSaveRefreshTimer = setTimeout(() => {
                this.aiFacesSaveRefreshTimer = null;
                if (this.aiFacesDestroyed || this.aiTab !== 'faces') return;
                this.refreshStatus();
            }, 1500);
        },

        /** 鏈式 setTimeout：上一次 status 處理完才排下一次（間隔 POLL_MS）。 */
        _aiFacesEnsurePoll() {
            if (this.aiFacesPollTimer !== null) return;
            this.aiFacesPollTimer = setTimeout(() => {
                this.aiFacesPollTimer = null;
                if (this.aiFacesDestroyed || this.aiTab !== 'faces') {
                    this._aiFacesStopPoll();
                    return;
                }
                this.refreshStatus();
            }, POLL_MS);
        },

        panelMode() {
            return panelMode(this.form || {});
        },

        recomputeAction() {
            return recomputeAction(this.aiFacesStatus);
        },

        deleteRebuildVisible() {
            return deleteRebuildVisible(
                this.aiFacesStatus,
                Boolean(this.form && this.form.aiFacesEnabled),
            );
        },

        /** 重算／刪除類按鈕是否停用。 */
        actionDisabled() {
            if (this.aiFacesBusy) return true;
            if (this.isDirty) return true;
            return false;
        },

        testDisabled() {
            if (this.aiFacesTestBusy) return true;
            const url = (this.form && this.form.aiFacesUrl) || '';
            return !String(url).trim();
        },

        statusLineText() {
            const desc = statusLine(this.aiFacesStatus);
            if (!desc || !desc.key) return '';
            let text = window.t(desc.key, desc.params || {});
            if (desc.key === 'settings.ai.faces.status_local_degraded'
                && !(desc.params && desc.params.time)) {
                text = window.t('settings.ai.faces.status_local_degraded_no_time');
            }
            if (desc.key === 'settings.ai.faces.status_external'
                && !(desc.params && desc.params.time)) {
                text = window.t('settings.ai.faces.status_external_no_time', desc.params || {});
            }
            return text;
        },

        recomputeLineText() {
            const desc = recomputeLine(this.aiFacesStatus);
            if (!desc || !desc.key) return '';
            let text = window.t(desc.key, desc.params || {});
            if (desc.extra) {
                text = text + window.t(desc.extra, desc.params || {});
            }
            return text;
        },

        _formatTestResult(data) {
            if (!data) {
                return window.t('settings.ai.faces.test_failed_generic');
            }
            if (data.ok) {
                return window.t('settings.ai.faces.test_ok', {
                    model: data.model || '',
                });
            }
            if (data.kind === 'unreachable') {
                return window.t('settings.ai.faces.test_unreachable');
            }
            if (data.kind === 'contract') {
                const checkKey = CHECK_KEYS[data.check] ?? CHECK_KEYS.unknown;
                const checkText = window.t(checkKey);
                return window.t('settings.ai.faces.test_contract') + '\n' + checkText;
            }
            return window.t('settings.ai.faces.test_failed_generic');
        },

        async refreshStatus() {
            if (this.aiFacesDestroyed) return;
            if (this.aiTab !== 'faces') {
                this._aiFacesStopPoll();
                return;
            }
            const gen = ++this.aiFacesGen;
            let data = null;
            try {
                const res = await fetch(STATUS_URL);
                data = res.ok ? await res.json() : null;
            } catch {
                data = null;
            }
            if (gen !== this.aiFacesGen || this.aiFacesDestroyed) return;
            if (!data) {
                if (this.aiFacesStatus?.running && this.aiTab === 'faces') {
                    this.aiFacesFailCount += 1;
                    if (this.aiFacesFailCount < POLL_FAIL_MAX) {
                        this._aiFacesEnsurePoll();
                        return;
                    }
                }
                this._aiFacesStopPoll();
                return;
            }
            this.aiFacesFailCount = 0;
            this.aiFacesStatus = data;
            if (data.running) {
                this._aiFacesEnsurePoll();
            } else {
                this._aiFacesStopPoll();
            }
        },

        async runTest() {
            if (this.testDisabled()) return;
            this.aiFacesTestBusy = true;
            this.aiFacesTestResultHtml = '';
            try {
                const body = {
                    url: String(this.form.aiFacesUrl || '').trim(),
                    api_key: this.form.aiFacesApiKey || '',
                    model: this.form.aiFacesModel || '',
                };
                const res = await fetch(TEST_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                let data = null;
                try { data = await res.json(); } catch { data = null; }
                if (!res.ok) {
                    this.aiFacesTestPassed = false;
                    this.aiFacesTestResultHtml = window.t('settings.ai.faces.test_failed_generic');
                    this.showToast(window.t('settings.ai.faces.test_http_error'), 'error');
                } else {
                    this.aiFacesTestPassed = Boolean(data && data.ok);
                    this.aiFacesTestResultHtml = this._formatTestResult(data);
                }
            } catch {
                this.aiFacesTestPassed = false;
                this.aiFacesTestResultHtml = window.t('settings.ai.faces.test_unreachable');
            } finally {
                this.aiFacesTestBusy = false;
            }
            await this.refreshStatus();
        },

        async resumeRecompute() {
            if (this.actionDisabled()) return;
            if (this.recomputeAction() !== 'resume') return;
            this.aiFacesBusy = true;
            try {
                const res = await fetch(RECOMPUTE_URL, { method: 'POST' });
                if (!res.ok) {
                    this.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
                }
            } catch {
                this.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
            } finally {
                this.aiFacesBusy = false;
            }
            await this.refreshStatus();
        },

        /** 刪除並重新對焦：確認後後端先測試、通過才清自動焦點並從 0 重算。 */
        async rebuildFaces() {
            if (this.actionDisabled()) return;
            const n = this.aiFacesStatus?.rebuild_count || 0;
            // eslint-disable-next-line no-alert -- rebuildFaces destructive confirm, same shape as similar rebuildIndex
            if (!confirm(window.t('settings.ai.faces.rebuild_confirm', { n }))) return;
            this.aiFacesBusy = true;
            try {
                const res = await fetch(REBUILD_URL, { method: 'POST' });
                let data = null;
                try { data = await res.json(); } catch { data = null; }
                if (!res.ok) {
                    this.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
                } else if (data && data.reason === 'test_failed') {
                    this.aiFacesTestPassed = false;
                    this.aiFacesTestResultHtml = this._formatTestResult({
                        ok: false,
                        kind: data.kind,
                        check: data.check,
                    });
                } else if (data && (data.reason === 'started' || data.reason === 'already_running')) {
                    /* 結束後統一 refreshStatus */
                } else {
                    this.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
                }
            } catch {
                this.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
            } finally {
                this.aiFacesBusy = false;
            }
            await this.refreshStatus();
        },

        async stopRecompute() {
            try {
                await fetch(STOP_URL, { method: 'POST' });
            } catch {
                /* 靜默；接著 refresh */
            }
            await this.refreshStatus();
        },

        copyAssistantPrompt() {
            const lan = (typeof this.serverUrl === 'function' && this.serverUrl())
                || window.location.origin;
            const text = window.t('settings.ai.faces.assistant_prompt', { lan_url: lan });
            copyText(text).then((ok) => {
                if (ok) {
                    this.showToast(window.t('settings.ai.faces.assistant_copied'), 'success');
                } else {
                    this.showToast(window.t('settings.ai.faces.assistant_copy_failed'), 'error');
                }
            });
        },
    };
}
