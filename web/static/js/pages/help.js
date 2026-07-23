// Help 頁面 Alpine.js 元件
export function helpPage() {
    return {
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
        _toast: { message: '', type: 'info', visible: false },
        _toastTimer: null,

        init() {
            this.loadVersion();
            this._isDesktop = this.$el.dataset.isDesktop === 'true';
            this.autoCheckUpdate = this.$el.dataset.autoCheckUpdate === 'true';
            if (this._isDesktop && this.autoCheckUpdate) this.checkUpdate();
        },

        async saveAutoCheckUpdate() {
            // x-model 已先把 autoCheckUpdate 翻到 desired；PUT 失敗必須還原本地狀態，
            // 否則 UI 顯示「關」但 config 仍「開」→ 下次啟動仍自動查 GitHub，違反 opt-out
            // （比照 settings state-config.js setServerMode 的 success-then-commit / fail-revert）。
            const desired = this.autoCheckUpdate;
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
            const cmd = `curl -s ${base}/api/capabilities`;
            const onSuccess = () => {
                this.curlCopied = true;
                setTimeout(() => this.curlCopied = false, 800);
            };
            if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(cmd).then(onSuccess).catch(() => this._fallbackCopy(cmd));
            } else {
                this._fallbackCopy(cmd);
            }
        },

        _fallbackCopy(text) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;top:-9999px';
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy'); this.curlCopied = true; setTimeout(() => this.curlCopied = false, 800); } catch(e) {}
            ta.remove();
        },

        async checkUpdate() {
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
            this.updateLoading = true;
            try {
                const resp = await fetch('/api/trigger-update', { method: 'POST' });
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

        showToast(message, type = 'info', duration = 2500) {
            this._toast.message = message;
            this._toast.type = type;
            this._toast.visible = true;
            if (this._toastTimer) clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(() => {
                this._toast.visible = false;
                this._toastTimer = null;
            }, duration);
        },

        _showHelpToast(msg) {
            this.showToast(msg, 'info');
        },
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('helpPage', helpPage);
});
