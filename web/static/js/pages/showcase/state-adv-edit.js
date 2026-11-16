import { versionsOf } from './work-versions.js';

export function stateAdvEdit() {
    return {
        advEditOpen: false,
        advEditInfo: null,
        advEditLoading: false,
        _advEditBusy: '',
        _advEditCell: '',
        advEditPathDraft: '',
        advEditPathError: '',
        _advEditGen: 0,

        openAdvEdit() {
            if (this._navBlockedByFocalEdit?.()) return;
            if (!this.currentLightboxVideo?.path) return;
            this._advEditGen++;
            this.advEditInfo = null;
            this.advEditLoading = false;
            this._advEditBusy = '';
            this._advEditCell = '';
            this.advEditPathDraft = '';
            this.advEditPathError = '';
            this.advEditOpen = true;
            this.onAdvEditOpen?.();
        },

        closeAdvEdit() {
            if (!this.advEditOpen) return;
            this._advEditGen++;
            this.advEditOpen = false;
            this.advEditInfo = null;
            this.advEditLoading = false;
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
