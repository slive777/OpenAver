import { toLbxVideo, lbxItemKey } from '../lbx-view-rules.js';

function currentItem(state) {
    const wishlist = state.lbxOwner() === 'wishlist';
    return [wishlist ? 'wishlist' : 'result', wishlist ? state.currentWishlistLightboxItem() : state.currentLightboxVideo()];
}

export function searchStateLbxView() {
    return {
        lbxOwner() {
            if (this.wishlistLightboxOpen) return 'wishlist';
            if (this.lightboxOpen) return 'search';
            if (this.lightboxCloseTimer != null) return 'search';
            if (this.wishlistLightboxIndex >= 0) return 'wishlist';
            return 'search';
        },
        lbxView() {
            const [kind, item] = currentItem(this);
            return toLbxVideo(item, kind);
        },
        lbxViewKey() {
            const [kind, item] = currentItem(this);
            return lbxItemKey(kind, item);
        },
        _isReleaseClickable() { return false; },
        lbxOpenSamples() {
            const video = this.lbxView();
            if (!video) return;
            const urls = video.sample_images.map((url, i) =>
                '/api/proxy-image?url=' + encodeURIComponent(video.preview_sample_images?.[i] || url));
            this.openSampleGallery(urls, 0);
        },
        _actressLbChips() {
            const aliases = (this.actressProfile?.aliases || []).map(text => ({ kind: 'alias', text }));
            const info = this._allInfoChips().map(text => ({ kind: 'info', text }));
            return aliases.concat(info);
        },
        _actressChipsIsExpanded() {
            const aliases = this._actressChipsExpanded.aliases;
            const info = this._actressChipsExpanded.info;
            return aliases || info;
        },
        _actressCoreMetadataParts() {
            const a = this.actressProfile;
            if (!a) return [];
            const parts = [];
            if (a.age) parts.push({ key: 'age', text: a.age + window.t('search.unit.age'), clickable: false });
            if (a.birth) parts.push({ key: 'birth', text: a.birth, clickable: false });
            if (a.height) parts.push({ key: 'height', text: a.height, clickable: false });
            if (a.cup) parts.push({ key: 'cup', text: a.cup + window.t('search.unit.cup'), clickable: false });
            const bwh = [a.bust, a.waist, a.hip].filter(Boolean).join('-');
            if (bwh) parts.push({ key: 'bwh', text: bwh, clickable: false });
            return parts;
        },
        lbxPlotTap(e) {
            const text = e?.currentTarget?.querySelector('.lbx-plot-text');
            if (!text || !(text.scrollHeight > text.clientHeight + 1)) return;
            this.lbxPopToggle('plot', e.currentTarget, { mode: 'click', anchorKey: 'plot' });
        },
    };
}
