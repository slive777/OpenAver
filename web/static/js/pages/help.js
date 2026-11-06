// Help 頁面 Alpine.js 元件
import { toastState } from '../shared/state-toast.js';
import { whenBridgeReady, callBridge, clientRouting } from '../shared/shell-client.js';
import { helpTabs } from './help/help-tabs.js';

// 168c-T5: 桌面殼 client 模式下，說明頁的更新功能走這台電腦的 bridge；缺任一個（舊殼）就退回伺服器端點。
const HELP_BRIDGE_METHODS = ['update_check', 'update_context', 'update_run'];

export function helpPage() {
    return {
        ...toastState(),
        // State
        appVersion: '',
        curlCopied: false,
        checkUpdateLoading: false,
        hasUpdate: false,
        latestVersion: '',
        downloadUrl: '',
        errorMsg: '',
        checkDone: false,
        showUpdateModal: false,
        isDefaultPath: true,
        updateLoading: false,
        autoCheckUpdate: false,
        _autoCheckSaving: false,
        _isDesktop: false,

        // 168c-T5: client 模式選路（FE-ALPINE-06：無條件宣告初值）。
        _shellMode: '',
        _bridgeMode: false,
        _bridgeUnavailable: false,  // 新殼但未就緒：這台讀不到，也不改送伺服器（同設定頁 unavailable）
        _routingReady: null,     // 選路決定的 promise（client 模式才有）
        _clientInitDone: null,   // client 模式 init 後半段（版本／自動檢查）的 promise

        // TASK-114b-T4：agent token 顯示區塊。對應 DOM 只在 show_agent_auth 為真時
        // 才會存在（Jinja {% if %}），但依 FE-ALPINE-06 仍必須無條件在此宣告初值。
        agentToken: '',             // 真值；init() 從 .help-agent-token-panel 的 dataset 讀入，
                                     // 此後全部讀寫只走這個欄位。
        agentTokenVisible: false,   // 眼睛切換：true=顯示真值，false=顯示遮罩
        agentTokenCopied: false,    // 複製 token 按鈕的 ✓ 微回饋（比照 curlCopied）
        maskedTokenDisplay: 'oav_••••••••',  // 固定遮罩字串（不依真值長度計算）

        init() {
            this._shellMode = this.$el.dataset.shellMode || '';
            if (this._shellMode === 'client') { this._initClient(); return; }
            this.loadVersion();
            this._isDesktop = this.$el.dataset.isDesktop === 'true';
            this.autoCheckUpdate = this.$el.dataset.autoCheckUpdate === 'true';
            if (this._isDesktop && this.autoCheckUpdate) this.checkUpdate();
            this.agentToken = document.querySelector('.help-agent-token-panel')?.dataset.agentToken || '';
        },

        // client 模式：先等 bridge 就緒再決定走橋或走伺服器（BE-WEBVIEW-06），決定前不打任何伺服器端點。
        _initClient() {
            this._isDesktop = this.$el.dataset.isDesktop === 'true';
            this.autoCheckUpdate = this.$el.dataset.autoCheckUpdate === 'true';
            this.agentToken = document.querySelector('.help-agent-token-panel')?.dataset.agentToken || '';
            this._routingReady = this._decideRoute();
            const ssrAutoCheck = this.autoCheckUpdate;
            this._clientInitDone = this._routingReady.then(() => this._finishClientInit(ssrAutoCheck));
        },

        async _decideRoute() {
            const ready = await whenBridgeReady();
            const bridge = window.pywebview?.api ?? null;
            const newShell = clientRouting('client', bridge, HELP_BRIDGE_METHODS) === 'bridge';
            this._bridgeMode = ready && newShell;
            this._bridgeUnavailable = !ready && newShell;
        },

        async _finishClientInit(ssrAutoCheck) {
            if (this._bridgeUnavailable) { this.appVersion = window.t('help.js.version_load_failed'); return; }
            let initialAutoCheck = ssrAutoCheck;  // 自動檢查依「初始化讀到的值」且須使用者最終仍開著
            if (!this._bridgeMode) {
                this.loadVersion();
            } else {
                const ctx = await callBridge('update_context');
                // 這台的版本讀不到就顯示未知，不拿伺服器版本冒充
                this.appVersion = ctx.ok === true && ctx.current_version
                    ? `v${ctx.current_version}`
                    : window.t('help.js.version_load_failed');
                const local = await callBridge('local_settings_get');
                // 等待期間使用者若已切換開關，以使用者的值為準，不被舊回覆蓋掉
                if (this.autoCheckUpdate === ssrAutoCheck
                    && local.ok === true && typeof local.auto_check_update === 'boolean') {
                    this.autoCheckUpdate = local.auto_check_update;
                    initialAutoCheck = local.auto_check_update;
                }
            }
            if (this._isDesktop && initialAutoCheck && this.autoCheckUpdate) this.checkUpdate();
        },

        async saveAutoCheckUpdate() {
            // x-model 已先把 autoCheckUpdate 翻到 desired；PUT 失敗必須還原本地狀態，
            // 否則 UI 顯示「關」但 config 仍「開」→ 下次啟動仍自動查 GitHub，違反 opt-out
            // （比照 settings state-config.js setServerMode 的 success-then-commit / fail-revert）。
            const desired = this.autoCheckUpdate;
            if (this._shellMode === 'client') {
                this._autoCheckSaving = true;  // 選路／初始化等待期間就上鎖，擋並行儲存
                await this._routingReady;
                await this._clientInitDone;    // 初始化的覆寫先發生，之後以 desired 為準
            }
            if (this._bridgeUnavailable) {
                this.autoCheckUpdate = !desired;
                this._autoCheckSaving = false;
                this.showToast(window.t('help.hero.this_computer_unavailable'), 'error');
                return;
            }
            if (this._bridgeMode) return this._saveAutoCheckUpdateBridge(desired);
            this._autoCheckSaving = true;  // 擋 checkbox，防兩次快速切換同時有 PUT in-flight
            // （server 寫入順序若被打亂，config 會與最後可見的 toggle 狀態相反——兩次 PUT 都
            // success:true，既有 revert-on-failure 邏輯抓不到，見 107 P2 Codex review）
            try {
                const resp = await fetch('/api/config/general/auto_check_update', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: desired }),
                });
                const result = await resp.json();
                if (!result.success) {
                    this.autoCheckUpdate = !desired;  // 還原，UI 不與持久化背離
                    this.showToast(window.t('help.hero.auto_check_save_failed'), 'error');
                }
            } catch (e) {
                this.autoCheckUpdate = !desired;  // 還原（離線/HTTP 錯）
                this.showToast(window.t('help.hero.auto_check_save_failed'), 'error');
            } finally {
                this._autoCheckSaving = false;
            }
        },

        async loadVersion() {
            try {
                const resp = await fetch('/api/version');
                const data = await resp.json();
                if (data.success) this.appVersion = `v${data.version}`;
            } catch (e) {
                this.appVersion = window.t('help.js.version_load_failed');
            }
        },

        copyCurlCommand() {
            const base = document.querySelector('.hero-terminal')?.dataset.capabilitiesBase || window.location.origin;
            const cmd = this.agentToken
                ? `curl -s -H "Authorization: Bearer ${this.agentToken}" ${base}/api/capabilities`
                : `curl -s ${base}/api/capabilities`;
            const onSuccess = () => {
                this.curlCopied = true;
                setTimeout(() => this.curlCopied = false, 800);
            };
            if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(cmd).then(onSuccess).catch(() => this._fallbackCopy(cmd, onSuccess));
            } else {
                this._fallbackCopy(cmd, onSuccess);
            }
        },

        curlDisplayText() {
            const base = document.querySelector('.hero-terminal')?.dataset.capabilitiesBase || '';
            if (!this.agentToken) return `curl -s ${base}/api/capabilities`;
            const shown = this.agentTokenVisible ? this.agentToken : this.maskedTokenDisplay;
            return `curl -s -H "Authorization: Bearer ${shown}" ${base}/api/capabilities`;
        },

        copyAgentToken() {
            const onSuccess = () => {
                this.agentTokenCopied = true;
                setTimeout(() => this.agentTokenCopied = false, 800);
            };
            if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(this.agentToken).then(onSuccess).catch(() => this._fallbackCopy(this.agentToken, onSuccess));
            } else {
                this._fallbackCopy(this.agentToken, onSuccess);
            }
        },

        toggleAgentTokenVisible() {
            this.agentTokenVisible = !this.agentTokenVisible;
        },

        // `onSuccess` 可省略——省略時維持既有（改寫前）行為：標記 curlCopied。
        // Opus 裁定：泛化必須向後相容，既有呼叫端／既有測試的行為不可變。
        _fallbackCopy(text, onSuccess) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;top:-9999px';
            document.body.appendChild(ta);
            ta.select();
            try {
                document.execCommand('copy');
                if (onSuccess) {
                    onSuccess();
                } else {
                    this.curlCopied = true;
                    setTimeout(() => this.curlCopied = false, 800);
                }
            } catch (e) {}
            ta.remove();
        },

        async _saveAutoCheckUpdateBridge(desired) {
            this._autoCheckSaving = true;
            try {
                const r = await callBridge('local_settings_save', { auto_check_update: desired });
                if (r.ok === true) {
                    this.autoCheckUpdate = desired;
                } else {
                    this.autoCheckUpdate = !desired;
                    this.showToast(window.t('help.hero.auto_check_save_failed'), 'error');
                }
            } finally {
                this._autoCheckSaving = false;
            }
        },

        async _checkUpdateBridge() {
            this.checkUpdateLoading = true;
            this.checkDone = false;
            this.errorMsg = '';
            try {
                const r = await callBridge('update_check');
                if (r.ok === true && !r.reason) {
                    this.hasUpdate = !!r.has_update;
                    this.latestVersion = r.latest_version || '';
                    this.downloadUrl = r.download_url || '';
                } else {
                    this.errorMsg = window.t('help.js.check_update_failed');
                }
            } catch (e) {
                this.errorMsg = window.t('help.js.check_update_failed');
            } finally {
                this.checkUpdateLoading = false;
                this.checkDone = true;
            }
        },

        async _triggerUpdateBridge() {
            const r = await callBridge('update_context');
            this.isDefaultPath = r.ok === true ? r.is_default_path !== false : true;
            this.showUpdateModal = true;
        },

        async _confirmUpdateBridge() {
            this.updateLoading = true;
            try {
                const r = await callBridge('update_run');
                this._showHelpToast(window.t(r.ok === true
                    ? 'help.update_modal.toast_success'
                    : 'help.update_modal.toast_error'));
            } finally {
                this.updateLoading = false;
                this.showUpdateModal = false;
            }
        },

        async checkUpdate() {
            if (this._shellMode === 'client') await this._routingReady;
            if (this._bridgeMode) return this._checkUpdateBridge();
            if (this._bridgeUnavailable) {
                this.errorMsg = window.t('help.hero.this_computer_unavailable');
                this.checkDone = true;
                return;
            }
            this.checkUpdateLoading = true;
            this.checkDone = false;
            this.errorMsg = '';
            try {
                const resp = await fetch('/api/check-update');
                const data = await resp.json();
                if (data.success) {
                    this.hasUpdate = data.has_update;
                    this.latestVersion = data.latest_version || '';
                    this.downloadUrl = data.download_url || '';
                } else {
                    this.errorMsg = window.t('help.js.check_update_failed');
                }
            } catch (e) {
                this.errorMsg = window.t('help.js.check_update_network_error');
            } finally {
                this.checkUpdateLoading = false;
                this.checkDone = true;
            }
        },

        async triggerUpdate() {
            if (this._shellMode === 'client') await this._routingReady;
            if (this._bridgeMode) return this._triggerUpdateBridge();
            if (this._bridgeUnavailable) return;
            // fetch install-context to determine default path scenario
            try {
                const resp = await fetch('/api/install-context');
                const data = await resp.json();
                this.isDefaultPath = data.is_default_path !== false;  // fallback true
            } catch (e) {
                this.isDefaultPath = true;  // 保守 fallback
            }
            this.showUpdateModal = true;
        },

        async confirmUpdate() {
            if (this._shellMode === 'client') await this._routingReady;
            if (this._bridgeMode) return this._confirmUpdateBridge();
            if (this._bridgeUnavailable) { this.showUpdateModal = false; return; }
            this.updateLoading = true;
            try {
                const resp = await fetch('/api/trigger-update', {
                    method: 'POST',
                    headers: { 'X-OpenAver-Desktop-Action': 'trigger-update' },
                });
                if (resp.ok) {
                    this._showHelpToast(window.t('help.update_modal.toast_success'));
                } else {
                    this._showHelpToast(window.t('help.update_modal.toast_error'));
                }
            } catch (e) {
                this._showHelpToast(window.t('help.update_modal.toast_error'));
            } finally {
                this.updateLoading = false;
                this.showUpdateModal = false;
            }
        },

        cancelUpdate() {
            this.showUpdateModal = false;
        },

        _showHelpToast(msg) {
            this.showToast(msg, 'info');
        },
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('helpPage', helpPage);
    Alpine.data('helpTabs', helpTabs);
});
