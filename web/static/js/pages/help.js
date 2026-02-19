// Help 頁面 Alpine.js 元件
function helpPage() {
    return {
        // State（結構化，不用 x-html — CR-3）
        appVersion: '',
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
                this.appVersion = '無法載入';
            }
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
                    this.errorMsg = '檢查失敗，請稍後再試';
                }
            } catch (e) {
                this.errorMsg = '無法連線，請稍後再試';
            } finally {
                this.checkUpdateLoading = false;
                this.checkDone = true;
            }
        },
    };
}
