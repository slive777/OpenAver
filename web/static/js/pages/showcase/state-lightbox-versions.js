/**
 * state-lightbox-versions.js — Showcase ESM（198b-T7a，CD-198b-8／10）
 *
 * 燈箱版本膠囊：多版本作品在封面 hover 層的規格帶左側有一排膠囊（199a-T2 自資訊列搬來），點哪顆整個燈箱就換成那個版本。
 * mergeState 分片：只有方法、沒有資料鍵、不帶 init()（FE-ALPINE-05／06）。
 * 所有狀態就是 currentLightboxVideo（＝燈箱目前版本）；切換不動 lightboxIndex、不動牆上卡。
 */

import { _coverBadgeRules } from '@/showcase/state-base.js';
import { versionsOf, versionCapsules } from './work-versions.js';
import { bandParts, formatRuntime } from './lbx-logic.js';

export function stateLightboxVersions() {
    return {
        // 多版本 → 該作品全部版本（預設在 [0]）；單版本／空 → []（膠囊列不顯示）
        lbVersions() {
            const cur = this.currentLightboxVideo;
            if (!cur) return [];
            const list = versionsOf(cur);
            return list.length > 1 ? list : [];
        },

        // 與 lbVersions() 同序同長的膠囊文字。類型名取封面標章 manifest 的 display_name（不受標章開關影響）；
        // 查無該 id 退回 id 字串。
        lbVersionCapsules() {
            const kindName = (id) => {
                const rule = _coverBadgeRules.find((r) => r && r.id === id);
                return (rule && rule.display_name) || id;
            };
            return versionCapsules(this.currentLightboxVideo, kindName, window.t, (b) => this.formatSize(b));
        },

        // 199a-T2：封面規格帶項目（等級 · 編碼 · 實際片長 · 大小）；純函式在 lbx-logic.js，這裡只接資料
        lbBandParts() {
            return bandParts(this.currentLightboxVideo, { formatSize: (b) => this.formatSize(b), formatRuntime });
        },

        // 以 path 找目標版本（FE-ALPINE-14）；找不到或就是目前這個 → 不動
        switchLightboxVersion(path) {
            const target = versionsOf(this.currentLightboxVideo).find((x) => x.path === path);
            if (!target || target.path === this.currentLightboxVideo?.path) return;
            this.currentLightboxVideo = target;
            this.addingLbTag = false;
            this._videoChipsExpanded = false;
            this._refreshLbFullBlurUp();
            this._refreshLbActorAges();
        },

        // 這個版本沒有自己的資料、顯示的是同作品其他版本的 → 片名旁標「沿用」
        lbIsBorrowed() {
            return !!this.currentLightboxVideo?.borrowed_from;
        },
    };
}
