/**
 * ai-backfill-controls.js — 三個 AI 補跑分頁共用的補跑 mixin（TASK-189a-T11a）
 *
 * 用法：面板工廠的回傳物件最前面展開 `...aiBackfillControls(adapter, hooks)`。
 * 這不是新元件：不進 mergeState、不註冊 Alpine.data；鍵名固定 bf 前綴，不帶功能名。
 * 生命週期由面板自己掛：面板的初始化方法末行呼叫 bfOnInit()，銷毀方法呼叫 bfOnDestroy()
 *（mixin 本身不定義這兩個生命週期方法）。
 *
 * 外求（面板 this 上由父層提供）只有 aiTab、isDirty；功能獨有的讀取（開關、表單、toast）經 hooks 傳 vm。
 * hooks（皆收 vm＝面板 this）：enabled(vm)（缺省 true）、testPassed(vm)（缺省 false）、
 *   blocked(vm)（缺省 null）、afterPost(vm, kind, {ok, data, failed})（缺省不做事；kind ∈ 'start'|'rebuild'）。
 * 可選尾巴 hooks（缺省＝無尾巴／沿用 adapter，行為逐字不變）：progressSuffix(vm)（接在進度行尾，僅進度行非空時）、
 *   pendingSuffix(vm)（接在「還有 N 部沒跑」尾，僅該行非空時）、rebuildConfirm(vm, view)（回 {key, params} 覆寫
 *   adapter.rebuildConfirm；回 null 沿用 adapter）。
 *
 * 輪詢世代守衛：每次 bfRefresh 先 ++bfGen，await 後世代不符或已銷毀就丟棄回應（用計數，不比物件身分）。
 */

import {
    normalizeStatus,
    actionOf,
    extraActionOf,
    rebuildVisible,
    progressLine,
    pendingLine,
} from './ai-backfill-logic.js';

const POLL_MS = 1000;
/** 補完中 status 連續失敗上限（約 30 秒）後才停輪詢。 */
const POLL_FAIL_MAX = 30;

function callHook(hooks, name, vm, fallback) {
    const fn = hooks && hooks[name];
    return typeof fn === 'function' ? fn(vm) : fallback;
}

/** 描述子 { key, params, extra } → 文字；null 回 ''。 */
function descText(desc) {
    if (!desc || !desc.key) return '';
    let text = window.t(desc.key, desc.params);
    if (desc.extra) text += window.t(desc.extra, desc.params);
    return text;
}

export function aiBackfillControls(adapter, hooks = {}) {
    return {
        bfStatus: null,
        bfBusy: false,
        bfGen: 0,
        bfFailCount: 0,
        bfPollTimer: null,
        bfDestroyed: false,

        /** 統一視角（每次重算，不存進 state）。 */
        bfView() {
            return normalizeStatus(adapter, this.bfStatus);
        },

        bfCtx() {
            return {
                enabled: Boolean(callHook(hooks, 'enabled', this, true)),
                dirty: Boolean(this.isDirty),
                busy: this.bfBusy,
                blocked: callHook(hooks, 'blocked', this, null) ?? null,
                testPassed: Boolean(callHook(hooks, 'testPassed', this, false)),
            };
        },

        bfAction() {
            return actionOf(adapter, this.bfView(), this.bfCtx());
        },

        bfExtraAction() {
            return extraActionOf(adapter, this.bfView(), this.bfCtx());
        },

        bfRebuildVisible() {
            return rebuildVisible(adapter, this.bfView(), this.bfCtx());
        },

        bfRebuildDisabled() {
            return Boolean(this.bfBusy || this.isDirty || callHook(hooks, 'blocked', this, null));
        },

        bfProgressText() {
            const text = descText(progressLine(this.bfView()));
            return text ? text + (callHook(hooks, 'progressSuffix', this, '') || '') : '';
        },

        bfPendingText() {
            const text = descText(pendingLine(this.bfView()));
            return text ? text + (callHook(hooks, 'pendingSuffix', this, '') || '') : '';
        },

        bfOnInit() {
            this.$watch('aiTab', (val) => {
                if (this.bfDestroyed) return;
                if (val === adapter.tab) {
                    this.bfRefresh();
                } else {
                    this._bfStopPoll();
                }
            });
            if (this.aiTab === adapter.tab) {
                this.bfRefresh();
            }
        },

        bfOnDestroy() {
            this._bfStopPoll();
            this.bfDestroyed = true;
            this.bfGen++;
        },

        _bfStopPoll() {
            if (this.bfPollTimer !== null) {
                clearTimeout(this.bfPollTimer);
                this.bfPollTimer = null;
            }
        },

        /** 鏈式 setTimeout：上一次 status 處理完才排下一次（間隔 POLL_MS）。 */
        _bfEnsurePoll() {
            if (this.bfPollTimer !== null) return;
            this.bfPollTimer = setTimeout(() => {
                this.bfPollTimer = null;
                if (this.bfDestroyed || this.aiTab !== adapter.tab) {
                    this._bfStopPoll();
                    return;
                }
                this.bfRefresh();
            }, POLL_MS);
        },

        async bfRefresh() {
            if (this.bfDestroyed) return;
            if (this.aiTab !== adapter.tab) {
                this._bfStopPoll();
                return;
            }
            const gen = ++this.bfGen;
            let data = null;
            try {
                const res = await fetch(adapter.urls.status);
                data = res.ok ? await res.json() : null;
            } catch {
                data = null;
            }
            if (gen !== this.bfGen || this.bfDestroyed) return;
            if (!data) {
                // 補完中短暫斷線：保留舊狀態，繼續排下一次；連續失敗滿 POLL_FAIL_MAX 才停
                if (this.bfStatus?.running && this.aiTab === adapter.tab) {
                    this.bfFailCount += 1;
                    if (this.bfFailCount < POLL_FAIL_MAX) {
                        this._bfEnsurePoll();
                        return;
                    }
                }
                this._bfStopPoll();
                return;
            }
            this.bfFailCount = 0;
            this.bfStatus = data;
            // 請求在途時離開分頁：只更新狀態，不再排下一次
            if (data.running && this.aiTab === adapter.tab) {
                this._bfEnsurePoll();
            } else {
                this._bfStopPoll();
            }
        },

        /** start／rebuild 共用單一出口：POST → bfBusy 歸位 → afterPost hook → bfRefresh。 */
        async _bfPost(kind) {
            const url = kind === 'rebuild' ? adapter.urls.rebuild : adapter.urls.start;
            let result = { ok: false, data: null, failed: true };
            this.bfBusy = true;
            try {
                const res = await fetch(url, { method: 'POST' });
                let data = null;
                try { data = await res.json(); } catch { data = null; }
                result = { ok: res.ok, data, failed: false };
            } catch {
                result = { ok: false, data: null, failed: true };
            } finally {
                this.bfBusy = false;
            }
            if (hooks && typeof hooks.afterPost === 'function') hooks.afterPost(this, kind, result);
            await this.bfRefresh();
        },

        /** 「補完全庫」與「繼續」是同一個端點，後端自己承接。 */
        async bfStart() {
            const a = this.bfAction();
            if (a.disabled || (a.action !== 'start' && a.action !== 'continue')) return;
            await this._bfPost('start');
        },

        async bfRetry() {
            const a = this.bfExtraAction();
            if (a.disabled || a.action !== 'retry') return;
            await this._bfPost('start');
        },

        async bfStop() {
            try {
                await fetch(adapter.urls.stop, { method: 'POST' });
            } catch {
                /* 靜默；接著 refresh */
            }
            await this.bfRefresh();
        },

        async bfRebuild() {
            if (this.bfRebuildDisabled()) return;
            const view = this.bfView();
            if (!view) return;
            const over = hooks && typeof hooks.rebuildConfirm === 'function'
                ? hooks.rebuildConfirm(this, view) : null;
            const desc = over || adapter.rebuildConfirm(view);
            // eslint-disable-next-line no-alert -- 全庫重建費用確認，與 rebuildIndex 的 confirm 同形
            if (!confirm(window.t(desc.key, desc.params))) return;
            await this._bfPost('rebuild');
        },
    };
}
