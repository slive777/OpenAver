/**
 * state-lightbox-ai-tags.js — Showcase ESM (188c-T11)
 *
 * Lightbox AI tag button: POST /api/ai/tags/videos → write captured video.user_tags → toast.
 * mergeState slice (plan-188c CD-188c-17): no init method (FE-ALPINE-05); keys use lbAi / _lbAi prefix.
 * Timing: set _lbAiInFlight[path] before any await; after await only mutate the captured video object.
 */

import { _recomputeVideoBadges } from '@/showcase/state-base.js';
import { aiTagsFailureToast, aiTagsSuccessToasts } from './lb-ai-tags-logic.js';

export function stateLightboxAiTags() {
    return {
        // path → true; same shape as _lbTrInFlight (per-path lock; switch does not clear)
        _lbAiInFlight: {},

        // AI tags flag: read showcase.html inject {enabled, provider}
        get lbAiTagsEnabled() {
            return typeof window !== 'undefined' && window.__SHOWCASE_AI_TAGS__?.enabled === true;
        },

        lbAiVisible() {
            return this.lbAiTagsEnabled
                && !!this.currentLightboxVideo?.path
                && !!this.currentLightboxVideo?.has_cover;
        },

        lbAiIsBusy() {
            return !!this._lbAiInFlight[this.currentLightboxVideo?.path];
        },

        async lbAiTag() {
            const video = this.currentLightboxVideo;
            if (!video?.path) return;
            const path = video.path;
            if (this._lbAiInFlight[path]) return;
            this._lbAiInFlight[path] = true;
            try {
                let data;
                try {
                    const resp = await fetch('/api/ai/tags/videos', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file_path: path }),
                    });
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    data = await resp.json();
                } catch (e) {
                    const toast = aiTagsFailureToast('failed');
                    this.showToast(window.t(toast.key, toast.params), 'error');
                    return;
                }
                if (data.success !== true) {
                    const provider = (typeof window !== 'undefined' && window.__SHOWCASE_AI_TAGS__?.provider) || '';
                    const toast = aiTagsFailureToast(data.reason, data.detail, provider);
                    this.showToast(window.t(toast.key, toast.params), 'error');
                    return;
                }
                video.user_tags = data.user_tags;
                _recomputeVideoBadges(video);
                for (const toast of aiTagsSuccessToasts(data)) {
                    this.showToast(window.t(toast.key, toast.params), toast.type);
                }
            } finally {
                delete this._lbAiInFlight[path];
            }
        },
    };
}
