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
        lbxPlotTap(e) {
            const text = e?.currentTarget?.querySelector('.lbx-plot-text');
            if (!text || !(text.scrollHeight > text.clientHeight + 1)) return;
            this.lbxPopToggle('plot', e.currentTarget, { mode: 'click', anchorKey: 'plot' });
        },
    };
}
