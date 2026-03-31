// Help 頁面 Alpine.js 元件
function helpPage() {
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

        init() {
            this.loadVersion();
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
            const cmd = `curl -s ${window.location.origin}/api/capabilities`;
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
    };
}
