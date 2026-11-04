/**
 * ai-faces-panel.js — 人臉分頁獨立 Alpine 元件（TASK-187a-T5；補跑邏輯 189a-T11b 起改走共用 mixin）
 *
 * Alpine.data('aiFacesPanel')；面板獨有 key 一律 aiFaces 前綴、補跑 key 一律 bf 前綴（展開自 ai-backfill-controls.js）；
 * 不進 mergeState。外求：form／isDirty／serverUrl()／showToast／aiTab（不複製父層 key）。
 * 存檔後補查留在面板；輪詢由 mixin 負責。兩個 $watch('aiTab') 並存是對的。
 */

import { copyText } from '@/shared/clipboard.js';
import { aiBackfillControls } from './ai-backfill-controls.js';
import {
    adapter as FACES_ADAPTER,
    panelMode,
    statusLine,
    recomputeLine,
    CHECK_KEYS,
} from './ai-faces-logic.js';

const TEST_URL = '/api/ai/faces/test';

/** 補跑 mixin 的面板端 hooks：開關、POST 後 toast／回填（不提供 testPassed／blocked）。 */
const FACES_HOOKS = {
    enabled: (vm) => Boolean(vm.form && vm.form.aiFacesEnabled),
    afterPost(vm, kind, { ok, data, failed }) {
        if (kind === 'start') {
            if (failed || !ok) {
                vm.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
            }
            return;
        }
        if (kind === 'rebuild') {
            if (failed || !ok) {
                vm.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
            } else if (data && data.reason === 'test_failed') {
                vm.aiFacesTestPassed = false;
                vm.aiFacesTestResultHtml = vm._formatTestResult({
                    ok: false,
                    kind: data.kind,
                    check: data.check,
                });
            } else if (data && (data.reason === 'started' || data.reason === 'already_running')) {
                /* 結束後統一 bfRefresh */
            } else {
                vm.showToast(window.t('settings.ai.faces.recompute_http_error'), 'error');
            }
        }
    },
};

export function aiFacesPanel() {
    return {
        ...aiBackfillControls(FACES_ADAPTER, FACES_HOOKS),
        aiFacesTestPassed: false,
        aiFacesTestResultHtml: '',
        aiFacesTestBusy: false,
        aiFacesSaveRefreshTimer: null,

        init() {
            // 離開人臉分頁時清存檔後補查；輪詢停止由 mixin 的 $watch('aiTab') 負責
            this.$watch('aiTab', (val) => {
                if (this.bfDestroyed) return;
                if (val !== 'faces') {
                    this._aiFacesClearSaveRefresh();
                }
            });
            // 存檔成功（isDirty true→false）後後端可能先暖機測試再開工；
            // 立刻取一次，若尚未 running 則每 1.5s 補查，最多 8 次（約 12s）。
            this.$watch('isDirty', (dirty, prev) => {
                if (this.bfDestroyed) return;
                if (dirty || prev !== true) return;
                if (this.aiTab !== 'faces') return;
                this._aiFacesAfterSaveRefresh();
            });
            this.bfOnInit();
        },

        destroy() {
            this._aiFacesClearSaveRefresh();
            this.bfOnDestroy();
        },

        _aiFacesClearSaveRefresh() {
            if (this.aiFacesSaveRefreshTimer !== null) {
                clearTimeout(this.aiFacesSaveRefreshTimer);
                this.aiFacesSaveRefreshTimer = null;
            }
        },

        async _aiFacesAfterSaveRefresh() {
            this._aiFacesClearSaveRefresh();
            await this.bfRefresh();
            if (this.bfDestroyed || this.aiTab !== 'faces') return;
            if (this.bfStatus?.running) return;
            this._aiFacesScheduleSaveRefresh(1);
        },

        /** 存檔後補查：每 1.5s 一次，最多 8 次；見 running 交既有輪詢並停。 */
        _aiFacesScheduleSaveRefresh(attempt) {
            if (attempt > 8) return;
            this.aiFacesSaveRefreshTimer = setTimeout(async () => {
                this.aiFacesSaveRefreshTimer = null;
                if (this.bfDestroyed || this.aiTab !== 'faces') return;
                await this.bfRefresh();
                if (this.bfDestroyed || this.aiTab !== 'faces') return;
                if (this.bfStatus?.running) return;
                this._aiFacesScheduleSaveRefresh(attempt + 1);
            }, 1500);
        },

        panelMode() {
            return panelMode(this.form || {});
        },

        testDisabled() {
            if (this.aiFacesTestBusy) return true;
            const url = (this.form && this.form.aiFacesUrl) || '';
            return !String(url).trim();
        },

        statusLineText() {
            const desc = statusLine(this.bfStatus);
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
            const desc = recomputeLine(this.bfStatus);
            if (!desc) return '';
            // key 為 null（跑中／閒置未完成）：只留 extra，去掉前導「・」
            if (!desc.key) {
                return desc.extra ? window.t(desc.extra, desc.params || {}).replace(/^\u30FB/, '') : '';
            }
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
            await this.bfRefresh();
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
