/**
 * ai-tags-panel.js — 設定頁「AI 標籤」分頁獨立 Alpine 元件（TASK-188c-T8b；補跑邏輯 189a-T11a 起改走共用 mixin）
 *
 * Alpine.data('aiTagsPanel')；面板獨有 key 一律 aiTags 前綴、補跑 key 一律 bf 前綴（展開自 ai-backfill-controls.js）；
 * 不進 mergeState。外求恰 6（不複製父層 key）：form／isDirty／aiTab／showToast／
 *   aiTagsModelLists()／ensureProviderModels()。
 *
 * 對外名單（模板照名單綁）：
 *   面板獨有：aiTagsTestResult／aiTagsTestBusy；panelMode()、modelOptions()、onProviderChange()、
 *         testDisabled()、runTest()、statusLineText()、firstRunHint()
 *   補跑（mixin）：bfStatus／bfBusy；bfAction()（回 {action, disabled, reason}）、bfStart()、bfStop()、
 *         bfRebuildVisible()、bfRebuildDisabled()、bfRebuild()
 */

import { aiBackfillControls } from './ai-backfill-controls.js';
import {
    adapter as TAGS_ADAPTER,
    panelMode,
    statusLine,
    progressExtras,
    pickTagsModel,
    costHint,
    formatUsd,
    buildTagsTestBody,
    testResultLine,
} from './ai-tags-logic.js';

const TEST_URL = '/api/ai/tags/test';

/** 該筆數的費用提示；筆數 ≤ 0 或連線家／模型不屬費用規則回 null。 */
function tagsCost(vm, n) {
    if (!(n > 0)) return null;
    return costHint(vm.form.aiTagsProvider, vm.form.aiTagsModel, n);
}

/** 補跑 mixin 的面板端 hooks：開關、POST 後 toast（判定順序不變）、進度行／待處理行尾巴、重建確認金額。 */
const TAGS_HOOKS = {
    enabled: (vm) => Boolean(vm.form.aiTagsEnabled),
    /** 跑中的 slow／waiting／skipped 句併進進度行。 */
    progressSuffix(vm) {
        return progressExtras(vm.bfStatus)
            .map((k) => window.t(k, { k: vm.bfStatus.skipped || 0 }))
            .join('');
    },
    /** 「還有 N 部沒跑」後接費用半句（金額以 pending 算）。 */
    pendingSuffix(vm) {
        const n = vm.bfStatus ? vm.bfStatus.pending : 0;
        const h = tagsCost(vm, n);
        if (!h) return '';
        return window.t('settings.ai.tags.cost_pending_tail', { total: formatUsd(h.total), label: h.label });
    },
    /** 全部重建確認：有費用規則時寫金額（以 total 算），否則回 null 沿用原文。 */
    rebuildConfirm(vm, view) {
        const h = tagsCost(vm, view.total);
        if (!h) return null;
        return {
            key: 'settings.ai.tags.rebuild_confirm_cost',
            params: { n: view.total, total: formatUsd(h.total), label: h.label },
        };
    },
    afterPost(vm, kind, { ok, data, failed }) {
        if (failed || !ok) {
            vm.showToast(window.t('settings.ai.tags.backfill_http_error'), 'error');
        } else if (data && data.status === 'not_enabled') {
            vm.showToast(window.t('settings.ai.tags.backfill_not_enabled'), 'error');
        } else if (data && data.status === 'not_configured') {
            vm.showToast(window.t('settings.ai.tags.test_not_configured'), 'error');
        }
    },
};

export function aiTagsPanel() {
    return {
        ...aiBackfillControls(TAGS_ADAPTER, TAGS_HOOKS),
        aiTagsTestResult: '',
        aiTagsTestBusy: false,

        init() {
            // 第一次打開開關：預選翻譯用的連線（載入設定時 isDirty 為 false，不動）
            this.$watch('form.aiTagsEnabled', (val) => {
                if (this.bfDestroyed) return;
                if (val !== true || this.isDirty !== true) return;
                if (this.form.aiTagsProvider !== '') return;
                const tp = this.form.translateProvider;
                if (!Object.keys(this.aiTagsModelLists()).includes(tp)) return;
                this.form.aiTagsProvider = tp;
                this.onProviderChange();
            });
            this.bfOnInit();
        },

        destroy() {
            this.bfOnDestroy();
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

        /** 舊狀態行文字；key 為 null（跑中／閒置未完成）時只串 extra 並去掉前導「・」。 */
        statusLineText() {
            const desc = statusLine(this.bfStatus);
            if (!desc) return '';
            const extras = (desc.extra || []).map((k) => window.t(k, desc.params || {}));
            if (!desc.key) return extras.join('').replace(/^\u30FB/, '');
            return window.t(desc.key, desc.params || {}) + extras.join('');
        },

        firstRunHint() {
            if (!this.bfStatus) return '';
            return window.t('settings.ai.tags.first_run_hint', { n: this.bfStatus.pending });
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
    };
}
