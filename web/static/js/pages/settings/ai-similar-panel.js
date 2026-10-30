/**
 * ai-similar-panel.js — 圖片相似分頁獨立 Alpine 元件（TASK-186-T6）
 *
 * Alpine.data('aiSimilarPanel')；自有 key 一律 aiSim 前綴。
 * 外求：form／isDirty／serverUrl()／showToast／aiTab（不複製父層 key）。
 */

import { copyText } from '@/shared/clipboard.js';
import {
    panelMode,
    indexAction,
    statusLine,
    CHECK_KEYS,
} from './ai-similar-logic.js';

const STATUS_URL = '/api/ai/similar/status';
const TEST_URL = '/api/ai/similar/test';
const INDEX_URL = '/api/ai/similar/index';
const STOP_URL = '/api/ai/similar/index/stop';
const POLL_MS = 1000;

export function aiSimilarPanel() {
    return {
        aiSimStatus: null,
        aiSimTestPassed: false,
        aiSimTestResultHtml: '',
        aiSimTestBusy: false,
        aiSimIndexBusy: false,
        aiSimPollTimer: null,
        aiSimGen: 0,
        aiSimDestroyed: false,

        init() {
            this.$watch('aiTab', (val) => {
                if (this.aiSimDestroyed) return;
                if (val === 'similar') {
                    this.refreshStatus();
                } else {
                    this._aiSimStopPoll();
                }
            });
            if (this.aiTab === 'similar') {
                this.refreshStatus();
            }
        },

        destroy() {
            this._aiSimStopPoll();
            this.aiSimDestroyed = true;
            this.aiSimGen++;
        },

        _aiSimStopPoll() {
            if (this.aiSimPollTimer !== null) {
                clearTimeout(this.aiSimPollTimer);
                this.aiSimPollTimer = null;
            }
        },

        /** 鏈式 setTimeout：上一次 status 處理完才排下一次（間隔 POLL_MS）。 */
        _aiSimEnsurePoll() {
            if (this.aiSimPollTimer !== null) return;
            this.aiSimPollTimer = setTimeout(() => {
                this.aiSimPollTimer = null;
                if (this.aiSimDestroyed || this.aiTab !== 'similar') {
                    this._aiSimStopPoll();
                    return;
                }
                this.refreshStatus();
            }, POLL_MS);
        },

        panelMode() {
            return panelMode(this.form || {});
        },

        indexAction() {
            return indexAction(this.aiSimStatus, this.aiSimTestPassed);
        },

        /** 索引類按鈕是否停用。 */
        indexDisabled() {
            if (this.aiSimIndexBusy) return true;
            if (this.isDirty) return true;
            const url = (this.form && this.form.aiSimilarUrl) || '';
            if (!String(url).trim()) return true;
            return false;
        },

        testDisabled() {
            if (this.aiSimTestBusy) return true;
            const url = (this.form && this.form.aiSimilarUrl) || '';
            return !String(url).trim();
        },

        statusLineText() {
            const desc = statusLine(this.aiSimStatus, Date.now());
            if (!desc || !desc.key) return '';
            let text = window.t(desc.key, desc.params || {});
            if (desc.key === 'settings.ai.similar.status_unreachable' && !(desc.params && desc.params.time)) {
                text = window.t('settings.ai.similar.status_unreachable_no_time');
            }
            if (desc.extra) {
                text = text + window.t(desc.extra, desc.params || {});
            }
            return text;
        },

        _formatTestResult(data) {
            if (!data) {
                return window.t('settings.ai.similar.test_failed_generic');
            }
            if (data.ok) {
                return window.t('settings.ai.similar.test_ok', {
                    model: data.model || '',
                    dim: data.dim ?? '',
                });
            }
            if (data.kind === 'unreachable') {
                return window.t('settings.ai.similar.test_unreachable');
            }
            if (data.kind === 'contract') {
                const checkKey = CHECK_KEYS[data.check] ?? CHECK_KEYS.unknown;
                const checkText = window.t(checkKey);
                return window.t('settings.ai.similar.test_contract') + '\n' + checkText;
            }
            return window.t('settings.ai.similar.test_failed_generic');
        },

        async refreshStatus() {
            if (this.aiSimDestroyed) return;
            if (this.aiTab !== 'similar') {
                this._aiSimStopPoll();
                return;
            }
            const gen = ++this.aiSimGen;
            let data = null;
            try {
                const res = await fetch(STATUS_URL);
                data = res.ok ? await res.json() : null;
            } catch {
                data = null;
            }
            if (gen !== this.aiSimGen || this.aiSimDestroyed) return;
            if (!data) {
                this._aiSimStopPoll();
                return;
            }
            this.aiSimStatus = data;
            if (data.running) {
                this._aiSimEnsurePoll();
            } else {
                this._aiSimStopPoll();
            }
        },

        async runTest() {
            if (this.testDisabled()) return;
            this.aiSimTestBusy = true;
            this.aiSimTestResultHtml = '';
            try {
                const body = {
                    url: String(this.form.aiSimilarUrl || '').trim(),
                    api_key: this.form.aiSimilarApiKey || '',
                    model: this.form.aiSimilarModel || '',
                };
                const res = await fetch(TEST_URL, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                let data = null;
                try { data = await res.json(); } catch { data = null; }
                if (!res.ok) {
                    this.aiSimTestPassed = false;
                    this.aiSimTestResultHtml = window.t('settings.ai.similar.test_failed_generic');
                    this.showToast(window.t('settings.ai.similar.test_http_error'), 'error');
                } else {
                    this.aiSimTestPassed = Boolean(data && data.ok);
                    this.aiSimTestResultHtml = this._formatTestResult(data);
                }
            } catch {
                this.aiSimTestPassed = false;
                this.aiSimTestResultHtml = window.t('settings.ai.similar.test_unreachable');
            } finally {
                this.aiSimTestBusy = false;
            }
            await this.refreshStatus();
        },

        async startIndex() {
            if (this.indexDisabled()) return;
            const action = this.indexAction();
            if (action !== 'build' && action !== 'rebuild' && action !== 'continue') return;
            this.aiSimIndexBusy = true;
            try {
                const res = await fetch(INDEX_URL, { method: 'POST' });
                let data = null;
                try { data = await res.json(); } catch { data = null; }
                if (!res.ok) {
                    this.showToast(window.t('settings.ai.similar.index_http_error'), 'error');
                } else if (data && (data.status === 'started' || data.status === 'already_running')) {
                    /* 結束後統一 refreshStatus */
                } else if (data && data.status === 'test_failed') {
                    this.aiSimTestPassed = false;
                    this.aiSimTestResultHtml = this._formatTestResult(data);
                } else {
                    this.showToast(window.t('settings.ai.similar.index_http_error'), 'error');
                }
            } catch {
                this.showToast(window.t('settings.ai.similar.index_http_error'), 'error');
            } finally {
                this.aiSimIndexBusy = false;
            }
            // started／test_failed／HTTP 錯誤皆刷新，讓狀態列吃到後端觀察值
            await this.refreshStatus();
        },

        async stopIndex() {
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
            const text = window.t('settings.ai.similar.assistant_prompt', { lan_url: lan });
            copyText(text).then((ok) => {
                if (ok) {
                    this.showToast(window.t('settings.ai.similar.assistant_copied'), 'success');
                } else {
                    this.showToast(window.t('settings.ai.similar.assistant_copy_failed'), 'error');
                }
            });
        },
    };
}
