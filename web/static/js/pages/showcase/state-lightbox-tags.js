/**
 * state-lightbox-tags.js — Showcase ESM（149a-T2）
 *
 * 燈箱自訂標籤（User Tags）：加一個標籤、刪掉它，唯讀來源的片走既有 toast。
 * 從 state-lightbox.js 拆出，逐字搬移，見 plan-149a.md CD-149a-1／CD-149a-2。
 */

import { _recomputeVideoBadges } from '@/showcase/state-base.js';

export function stateLightboxTags() {
    return {
        // User Tags 狀態
        addingLbTag: false,
        newLbTagValue: '',

        // 展開 inline 輸入框並 focus
        showAddLbTagInput() {
            this.addingLbTag = true;
            this.newLbTagValue = '';
            this.$nextTick(() => this.$refs.lbTagInput?.focus());
        },

        // 確認新增 tag — 呼叫 POST /api/user-tags
        async confirmAddLbTag() {
            const video = this.currentLightboxVideo;
            const tag = (this.newLbTagValue || '').trim();
            if (!tag) {
                this.addingLbTag = false;
                return;
            }
            if (!video?.path) {
                this.addingLbTag = false;
                return;
            }
            const existingTags = video.user_tags || [];
            if (existingTags.includes(tag)) {
                // 重複 tag，靜默忽略
                this.addingLbTag = false;
                this.newLbTagValue = '';
                return;
            }
            try {
                const resp = await fetch('/api/user-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: video.path,
                        add: [tag],
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success) {
                    video.user_tags = data.user_tags;
                    _recomputeVideoBadges(video);
                    if (data.readonly_no_output) {
                        this.showToast(window.t('showcase.lightbox.tag_nfo_not_written'), 'info');
                    }
                    if (data.nfo_write_blocked) {
                        this.showToast(window.t('showcase.lightbox.tag_nfo_write_blocked'), 'info');
                    }
                } else {
                    throw new Error(data.error || 'API failed');
                }
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.tag_api_failed'), 'error');
            } finally {
                this.addingLbTag = false;
                this.newLbTagValue = '';
            }
        },

        // 取消輸入框
        cancelAddLbTag() {
            this.addingLbTag = false;
            this.newLbTagValue = '';
        },

        // 刪除 user tag — 呼叫 POST /api/user-tags {remove: [tag]}
        async removeLbUserTag(tag) {
            const video = this.currentLightboxVideo;
            if (!video?.path) return;
            try {
                const resp = await fetch('/api/user-tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        file_path: video.path,
                        remove: [tag],
                    }),
                });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                if (data.success) {
                    video.user_tags = data.user_tags;
                    _recomputeVideoBadges(video);
                    if (data.readonly_no_output) {
                        this.showToast(window.t('showcase.lightbox.tag_nfo_not_written'), 'info');
                    }
                    if (data.nfo_write_blocked) {
                        this.showToast(window.t('showcase.lightbox.tag_nfo_write_blocked'), 'info');
                    }
                } else {
                    throw new Error(data.error || 'API failed');
                }
            } catch (e) {
                this.showToast(window.t('showcase.lightbox.tag_api_failed'), 'error');
            }
        },
    };
}
