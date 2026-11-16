import { formatHms, mediaInfoText, advEditFilesView, advEditActionNotice } from './lbx-logic.js';
import { versionsOf } from './work-versions.js';

export function stateAdvEdit() {
    return {
        advEditOpen: false,
        advEditInfo: null,
        advEditLoading: false,
        advEditLoadError: false,
        advEditImgFail: { cover: false, poster: false, thumb: false },
        _advEditBusy: '',
        _advEditCell: '',
        advEditPathDraft: '',
        advEditPathError: '',
        _advEditGen: 0,

        async loadAdvEditInfo() {
            const gen = this._advEditGen;
            this.advEditLoading = true;
            try {
                const resp = await fetch(`/api/showcase/video/files?path=${encodeURIComponent(this.currentLightboxVideo.path)}`);
                const data = await resp.json();
                if (gen !== this._advEditGen) return;   // 200b-T11a：晚到的檔案資訊（已關窗或重開）不寫畫面
                if (resp.ok && data?.success === true) {
                    this.advEditInfo = data;
                    this.advEditLoadError = false;
                    this.advEditImgFail = { cover: false, poster: false, thumb: false };
                } else this.advEditLoadError = true;
            } catch (e) {
                if (gen === this._advEditGen) this.advEditLoadError = true;
            } finally {
                if (gen === this._advEditGen) this.advEditLoading = false;
            }
        },
        async regenAdvEditPoster() {
            if (this._advEditBusy || !this.advEditOpen || !this.advEditFiles().canRegen) return;
            const gen = this._advEditGen, video = this.currentLightboxVideo;
            this._advEditBusy = 'regen';
            try {
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/poster-regenerate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: video.path }) });
                    data = await resp.json();
                } catch (e) { data = null; }
                if (gen !== this._advEditGen) return;
                const notice = advEditActionNotice('regen', data, window.t);
                this.showToast(notice.text, notice.type);
                if (notice.reload) {
                    await this.refreshVideoData(video);
                    if (gen !== this._advEditGen) return;
                    await this.loadAdvEditInfo();
                }
            } catch (e) { console.error(e); } finally {
                if (gen === this._advEditGen) this._advEditBusy = '';
            }
        },
        async rereadAdvEditMedia() {
            if (this._advEditBusy || !this.advEditOpen || !this.advEditFiles().canReread) return;
            const gen = this._advEditGen, video = this.currentLightboxVideo;
            this._advEditBusy = 'reprobe';
            try {
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/reprobe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: video.path }) });
                    data = await resp.json();
                } catch (e) { data = null; }
                if (gen !== this._advEditGen) return;
                const notice = advEditActionNotice('reread', data, window.t);
                this.showToast(notice.text, notice.type);
                if (notice.reload) {
                    await this.refreshVideoData(video);
                    if (gen !== this._advEditGen) return;
                    await this.loadAdvEditInfo();
                }
            } catch (e) { console.error(e); } finally {
                if (gen === this._advEditGen) this._advEditBusy = '';
            }
        },
        advEditFiles() {
            return advEditFilesView(this.advEditInfo, { borrowed: !!this.currentLightboxVideo?.borrowed_from, imgFail: this.advEditImgFail });
        },
        advEditMediaText() {
            return mediaInfoText(this.advEditInfo?.media, { formatSize: (b) => this.formatSize(b), formatHms, t: window.t });
        },

        openAdvEdit() {
            if (this._navBlockedByFocalEdit?.()) return;
            if (!this.currentLightboxVideo?.path) return;
            this._advEditGen++;
            this.advEditInfo = null;
            this.advEditLoading = false;
            this.advEditLoadError = false;
            this.advEditImgFail = { cover: false, poster: false, thumb: false };
            this._advEditBusy = '';
            this._advEditCell = '';
            this.advEditPathDraft = '';
            this.advEditPathError = '';
            this.advEditOpen = true;
            this.loadAdvEditInfo();
            this.onAdvEditOpen?.();
        },

        closeAdvEdit() {
            if (!this.advEditOpen) return;
            this._advEditGen++;
            this.advEditOpen = false;
            this.advEditInfo = null;
            this.advEditLoading = false;
            this.advEditLoadError = false;
            this.advEditImgFail = { cover: false, poster: false, thumb: false };
            this._advEditBusy = '';
            this._advEditCell = '';
            this.advEditPathDraft = '';
            this.advEditPathError = '';
            this.onAdvEditClose?.();
        },

        cancelAdvEditCell() {
            this._advEditCell = '';
            this.advEditPathDraft = '';
            this.advEditPathError = '';
        },

        advEditTitle() {
            const video = this.currentLightboxVideo;
            const versions = versionsOf(video);
            const parts = [window.t('showcase.adv_edit.title'), video?.number || ''];
            if (versions.length > 1) {
                parts.push(this.lbVersionCapsules()[versions.findIndex((v) => v.path === video.path)] || '');
            }
            return parts.join(' · ');
        },
    };
}
