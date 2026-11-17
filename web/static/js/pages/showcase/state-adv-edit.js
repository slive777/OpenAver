import { formatHms, mediaInfoText, advEditFilesView, advEditActionNotice, advEditPathStem, advEditRepathError, advEditUpdateNotice, advEditThumbNotice } from './lbx-logic.js';
import { versionsOf } from './work-versions.js';

export function stateAdvEdit() {
    return {
        advEditOpen: false,
        advEditPathConfirm: false,
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
        async regenAdvEditThumb() {
            if (this._advEditBusy || !this.advEditOpen || !this.advEditFiles().canRegenThumb) return;
            const gen = this._advEditGen, video = this.currentLightboxVideo;
            this._advEditBusy = 'thumb';
            try {
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/thumb-regenerate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: video.path }) });
                    data = await resp.json();
                } catch (e) { data = null; }
                if (gen !== this._advEditGen) return;
                const notice = advEditThumbNotice(data, window.t);
                this.showToast(notice.text, notice.type);
                if (notice.reload) await this.refreshVideoData(video);
                if (gen !== this._advEditGen) return;
                await this.loadAdvEditInfo();
            } catch (e) { console.error(e); } finally {
                if (gen === this._advEditGen) this._advEditBusy = '';
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

        advEditPathDisplay() {
            const path = this.currentLightboxVideo?.path || '';
            return typeof window.pathToDisplay === 'function' ? window.pathToDisplay(path) : path;
        },
        advEditCanEditPath() { return !!this.advEditInfo && this.advEditInfo.readonly === false; },
        startAdvEditPath() {
            if (!this.advEditCanEditPath() || this._advEditBusy || this._advEditCell) return;
            this._advEditCell = 'path';
            this.advEditPathDraft = this.advEditPathDisplay();
            this.advEditPathError = '';
            this.advEditPathConfirm = false;
            this.$nextTick?.(() => { const input = this.$refs?.advEditPathInput; input?.focus(); input?.setSelectionRange(input.value.length, input.value.length); });
        },
        async submitAdvEditPath(confirmed = false) {
            if (this._advEditCell !== 'path' || this._advEditBusy) return;
            const video = this.currentLightboxVideo;
            if (!video?.path) return;
            const oldPath = video.path;
            let typed = String(this.advEditPathDraft || '').trim();
            if (typed.length >= 2 && typed[0] === '"' && typed[typed.length - 1] === '"') typed = typed.slice(1, -1);
            const nameChanged = advEditPathStem(typed) !== advEditPathStem(this.advEditPathDisplay());
            if (confirmed !== true && typed && nameChanged) {
                this.advEditPathConfirm = true;
                this.advEditPathError = '';
                this.$nextTick?.(() => this.$refs?.advEditPathConfirmYes?.focus());
                return;
            }
            const gen = this._advEditGen;
            this._advEditBusy = 'repath';
            this.advEditPathError = '';
            try {
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/repath', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: oldPath, new_path: typed, confirm_name_change: confirmed === true }) });
                    data = await resp.json().catch(() => null);
                } catch (e) { data = null; }
                if (data && data.success === true && data.path) {
                    await this._reloadWallKeepLightbox(oldPath, { reanchorTo: data.path, bustPaths: [data.path], t: Date.now() });
                    if (gen !== this._advEditGen) return;
                    this.cancelAdvEditCell();
                    await this.loadAdvEditInfo();
                    if (gen !== this._advEditGen) return;
                    const renamed = typeof data.name_changed === 'boolean' ? data.name_changed : nameChanged;
                    this.showToast(renamed ? window.t('showcase.adv_edit.path.done_renamed') : window.t('showcase.adv_edit.path.done'), 'success');
                } else {
                    if (gen !== this._advEditGen) return;
                    const error = advEditRepathError(data && data.error, window.t);
                    this.advEditPathConfirm = error.confirm;
                    this.advEditPathError = error.text;
                    if (error.confirm) this.$nextTick?.(() => this.$refs?.advEditPathConfirmYes?.focus());
                }
            } catch (e) {
                if (gen === this._advEditGen) this.advEditPathError = window.t('showcase.adv_edit.path.err_generic');
            } finally {
                if (gen === this._advEditGen) this._advEditBusy = '';
            }
        },
        async runAdvEditUpdate() {
            if (!this.advEditOpen || this._advEditBusy) return;
            const video = this.currentLightboxVideo;
            if (!video?.path) return;
            const gen = this._advEditGen;
            this._advEditBusy = 'update';
            try {
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: video.path }) });
                    data = await resp.json().catch(() => null);
                } catch (e) { data = null; }
                if (gen !== this._advEditGen) return;   // 200b-T11b：晚到的更新回應（已關窗或重開）不寫畫面、不 toast
                const notice = advEditUpdateNotice(data, window.t);
                if (notice.reload) {
                    await this.refreshVideoData(video);
                    if (gen !== this._advEditGen) return;
                    await this.loadAdvEditInfo();
                } else if (notice.sync) await this.loadAdvEditInfo();
                if (gen !== this._advEditGen) return;
                this.showToast(notice.text, notice.type);
            } catch (e) {
                if (gen === this._advEditGen) this.showToast(window.t('showcase.adv_edit.update.err_generic'), 'error');
            } finally {
                if (gen === this._advEditGen) this._advEditBusy = '';
            }
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
            this.advEditPathConfirm = false;
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
            this.advEditPathConfirm = false;
            this.onAdvEditClose?.();
        },

        cancelAdvEditCell() {
            this._advEditCell = '';
            this.advEditPathDraft = '';
            this.advEditPathError = '';
            this.advEditPathConfirm = false;
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
