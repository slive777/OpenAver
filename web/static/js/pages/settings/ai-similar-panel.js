/**
 * ai-similar-panel.js — 圖片相似分頁獨立 Alpine 元件（TASK-186-T6；補跑邏輯 189a-T11b 起改走共用 mixin）
 *
 * Alpine.data('aiSimilarPanel')；面板獨有 key 一律 aiSim 前綴、補跑 key 一律 bf 前綴（展開自 ai-backfill-controls.js）；
 * 不進 mergeState。外求：form／isDirty／serverUrl()／showToast／aiTab（不複製父層 key）。
 */

import { copyText } from '@/shared/clipboard.js';
import { aiBackfillControls } from './ai-backfill-controls.js';
import {
    adapter as SIMILAR_ADAPTER,
    panelMode,
    statusLine,
    rebuildOutcome,
    CHECK_KEYS,
} from './ai-similar-logic.js';

const TEST_URL = '/api/ai/similar/test';

/** 補跑 mixin 的面板端 hooks：開關、網址空擋、本次測試通過、POST 後 toast／回填。 */
const SIMILAR_HOOKS = {
    enabled: (vm) => Boolean(vm.form && vm.form.aiSimilarEnabled),
    testPassed: (vm) => vm.aiSimTestPassed,
    blocked: (vm) => (String((vm.form && vm.form.aiSimilarUrl) || '').trim() ? null : 'no_url'),
    afterPost(vm, kind, { ok, data, failed }) {
        if (kind === 'start') {
            if (failed || !ok) {
                vm.showToast(window.t('settings.ai.similar.index_http_error'), 'error');
            } else if (data && (data.status === 'started' || data.status === 'already_running')) {
                /* 結束後統一 bfRefresh */
            } else if (data && data.status === 'test_failed') {
                vm.aiSimTestPassed = false;
                vm.aiSimTestResultHtml = vm._formatTestResult(data);
            } else {
                vm.showToast(window.t('settings.ai.similar.index_http_error'), 'error');
            }
            return;
        }
        if (kind === 'rebuild') {
            const outcome = rebuildOutcome(ok, data);
            if (outcome === 'error') {
                vm.showToast(window.t('settings.ai.similar.index_http_error'), 'error');
            } else if (outcome === 'test_failed') {
                vm.aiSimTestPassed = false;
                vm.aiSimTestResultHtml = vm._formatTestResult(data);
            }
        }
    },
};

export function aiSimilarPanel() {
    return {
        ...aiBackfillControls(SIMILAR_ADAPTER, SIMILAR_HOOKS),
        aiSimTestPassed: false,
        aiSimTestResultHtml: '',
        aiSimTestBusy: false,

        init() {
            this.bfOnInit();
        },

        destroy() {
            this.bfOnDestroy();
        },

        panelMode() {
            return panelMode(this.form || {});
        },

        testDisabled() {
            if (this.aiSimTestBusy) return true;
            const url = (this.form && this.form.aiSimilarUrl) || '';
            return !String(url).trim();
        },

        statusLineText() {
            const desc = statusLine(this.bfStatus, Date.now());
            if (!desc) return '';
            // key 為 null（跑中／閒置未完成）：只留 extra，去掉前導「・」
            if (!desc.key) {
                return desc.extra ? window.t(desc.extra, desc.params || {}).replace(/^\u30FB/, '') : '';
            }
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
            await this.bfRefresh();
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
