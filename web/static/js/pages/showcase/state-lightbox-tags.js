/**
 * state-lightbox-tags.js — Showcase ESM（149a-T2）
 *
 * 燈箱自訂標籤（User Tags）：加一個標籤、刪掉它，唯讀來源的片走既有 toast。
 * 從 state-lightbox.js 拆出，逐字搬移，見 plan-149a.md CD-149a-1／CD-149a-2。
 */

import { _recomputeVideoBadges } from '@/showcase/state-base.js';
import { versionsOf, writeWorkFields } from './work-versions.js';
import { parseWorkTags } from './lbx-logic.js';

export function stateLightboxTags() {
    return {
        // User Tags 狀態
        addingLbTag: false,
        newLbTagValue: '',

        // 199a-T7 第 5 列：作品標籤／你的標籤清單與露出數（lbxFit 量測寫入；非整數＝全露）
        lbxWorkTags() { return parseWorkTags(this.currentLightboxVideo); },
        lbxUserTags() { return this.currentLightboxVideo?.user_tags || []; },
        lbxTagShown(kind) {
            const v = kind === 'user' ? this.lbxFit?.userTagShown : this.lbxFit?.workTagShown;
            return Number.isInteger(v) ? v : Infinity;
        },
        lbxTagMoreCount() {
            return Math.max(0, this.lbxWorkTags().length - this.lbxTagShown('work')) + Math.max(0, this.lbxUserTags().length - this.lbxTagShown('user'));
        },
        _lbTagFocusPlus() { this.$nextTick?.(() => this.$refs?.lbTagPlus?.focus?.()); },

        // 展開 inline 輸入框並 focus
        showAddLbTagInput() {
            this.addingLbTag = true;
            this.newLbTagValue = '';
            this.$nextTick(() => this.$refs.lbTagInput?.focus());
        },

        // 確認新增 tag — 呼叫 POST /api/user-tags
        async confirmAddLbTag() {
            const video = this.currentLightboxVideo;
            const dicts = versionsOf(video).slice();   // 198b-T7b：標籤是作品層的帳；第一個 await 前取快照（FE-TIMING-16）
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
                    const list = Array.isArray(data.work_user_tags) ? data.work_user_tags : data.user_tags;
                    writeWorkFields(dicts, { user_tags: list }, this.paginatedVideos, this.currentLightboxVideo).forEach((d) => _recomputeVideoBadges(d));
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
            this._lbTagFocusPlus();
        },

        // 刪除 user tag — 呼叫 POST /api/user-tags {remove: [tag]}
        async removeLbUserTag(tag) {
            const video = this.currentLightboxVideo;
            const dicts = versionsOf(video).slice();
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
                    const list = Array.isArray(data.work_user_tags) ? data.work_user_tags : data.user_tags;
                    writeWorkFields(dicts, { user_tags: list }, this.paginatedVideos, this.currentLightboxVideo).forEach((d) => _recomputeVideoBadges(d));
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
